"""Blueprint de Tentativas e Motor FSRS v6 (/attempt, /review, /attempt/batch)."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from flask import Blueprint, g, jsonify, request

from . import srs
from .db import db_transaction, get_db
from .idempotency import complete_active_lease, idempotent
from .observability import record_domain_event
from .schemas import AttemptIn, BatchAttemptIn, ReviewIn, ValidationError, validation_errors
from .services.questions_service import (
    _defer_question_review,
    _defer_questions_batch,
    _fetch_batch_metadata_with_counts,
    _fetch_srs_map,
    _resolve_answered_at,
    check_is_correct,
)

logger = logging.getLogger(__name__)

bp = Blueprint("attempts", __name__)


def _parse_utc_dt(value: str | None) -> datetime | None:
    """Converte timestamp ISO-8601 em datetime UTC aware para comparação segura."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip())
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return None


def _card_last_review_dt(card_json: str | None) -> datetime | None:
    """Extrai o datetime UTC de `last_review` de um card FSRS serializado."""
    if not card_json:
        return None
    try:
        payload = json.loads(card_json)
        if isinstance(payload, dict):
            return _parse_utc_dt(payload.get("last_review"))
    except (ValueError, TypeError):
        return None
    return None


def _upsert_spaced_repetition(db, qid: int, user_id: int, next_review: str, card_json: str) -> None:
    db.execute(
        """
        INSERT INTO spaced_repetition (question_id, next_review_date, fsrs_card, user_id)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(question_id, user_id) DO UPDATE SET
            next_review_date = excluded.next_review_date, fsrs_card = excluded.fsrs_card
        """,
        (qid, next_review, card_json, user_id),
    )


def _apply_fsrs(
    db,
    qid: int,
    user_id: int,
    is_correct,
    confidence,
    assisted: bool,
    now: datetime,
    srs_map: dict | None = None,
) -> tuple[str | None, str, str]:
    """Aplica FSRS a partir do estado atual, persiste o novo card e retorna (card_before, next_review, now_iso)."""
    if srs_map is not None:
        card_before = srs_map.get(qid)
    else:
        sr = db.execute(
            "SELECT fsrs_card FROM spaced_repetition WHERE question_id = ? AND user_id = ?",
            (qid, user_id),
        ).fetchone()
        card_before = sr["fsrs_card"] if sr else None

    try:
        card_json, next_review = srs.review(
            card_before,
            is_correct,
            confidence,
            now=now,
            assisted=bool(assisted),
        )
    except Exception:
        logger.error("Erro ao calcular FSRS (question_id=%s, user_id=%s)", qid, user_id)
        raise

    _upsert_spaced_repetition(db, qid, user_id, next_review, card_json)
    if srs_map is not None:
        srs_map[qid] = card_json
    now_iso = now.astimezone(UTC).isoformat()
    return card_before, next_review, now_iso


def _save_attempt_fsrs_snapshot(
    db,
    attempt_id: int | None,
    user_id: int,
    card_before: str | None,
    reviewed_at: str,
    twin_card_before: str | None = None,
    twin_reviewed_at: str | None = None,
) -> None:
    if not attempt_id:
        return
    if twin_reviewed_at is not None:
        db.execute(
            """UPDATE attempts
               SET fsrs_card_before = ?, fsrs_reviewed_at = ?, twin_card_before = ?, twin_reviewed_at = ?
               WHERE id = ? AND user_id = ?""",
            (card_before, reviewed_at, twin_card_before, twin_reviewed_at, attempt_id, user_id),
        )
    else:
        db.execute(
            """UPDATE attempts
               SET fsrs_card_before = ?, fsrs_reviewed_at = ?
               WHERE id = ? AND user_id = ?""",
            (card_before, reviewed_at, attempt_id, user_id),
        )


_ATTEMPTS_FULL_SQL = (
    "INSERT INTO attempts (question_id, selected_letter, is_correct, answered_at, time_spent_ms, confidence, "
    "user_id, assisted, fsrs_card_before, fsrs_reviewed_at, twin_card_before, twin_reviewed_at) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
)
_ATTEMPTS_ASSISTED_SQL = (
    "INSERT INTO attempts (question_id, selected_letter, is_correct, answered_at, time_spent_ms, confidence, user_id, assisted) "
    "VALUES (?,?,?,?,?,?,?,?)"
)
_ATTEMPTS_LEGACY_SQL = (
    "INSERT INTO attempts (question_id, selected_letter, is_correct, answered_at, time_spent_ms, confidence, user_id) "
    "VALUES (?,?,?,?,?,?,?)"
)
_SRS_UPSERT_SQL = """
    INSERT INTO spaced_repetition (question_id, next_review_date, fsrs_card, user_id)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(question_id, user_id) DO UPDATE SET
        next_review_date = excluded.next_review_date, fsrs_card = excluded.fsrs_card
"""


def _insert_attempts_rows(db, rows: list[tuple], *, bulk: bool = False):
    """Insere uma ou mais tentativas já com snapshot FSRS, com fallback seguro para schemas sem colunas opcionais."""
    if not rows:
        return None
    fn = db.executemany if bulk else db.execute
    args = rows if bulk else rows[0]
    try:
        return fn(_ATTEMPTS_FULL_SQL, args)
    except Exception as exc:
        err_lower = str(exc).lower()
        if "no such column" not in err_lower and "has no column named" not in err_lower:
            raise
    assisted_rows = [r[:8] for r in rows]
    try:
        return fn(_ATTEMPTS_ASSISTED_SQL, assisted_rows if bulk else assisted_rows[0])
    except Exception as exc:
        err_lower = str(exc).lower()
        if "no such column" not in err_lower and "has no column named" not in err_lower:
            raise
    legacy_rows = [r[:7] for r in rows]
    return fn(_ATTEMPTS_LEGACY_SQL, legacy_rows if bulk else legacy_rows[0])


def _upsert_spaced_repetition_batch(db, rows: list[tuple]) -> None:
    if not rows:
        return
    if len(rows) == 1:
        db.execute(_SRS_UPSERT_SQL, rows[0])
    else:
        db.executemany(_SRS_UPSERT_SQL, rows)


def _compute_attempt_srs_outcome(
    *,
    qid: int,
    user_id: int,
    selected: str,
    correct_letter: str | None,
    correct_alts,
    is_discursive: bool,
    explicit_is_correct,
    confidence: str,
    is_assisted: bool,
    twin_id: int | None,
    now: datetime,
    srs_map: dict[int, str | None],
) -> tuple[int, str | None, str | None, str | None, str | None, str | None, dict[int, tuple]]:
    """Calcula correção e próximo snapshot FSRS (principal + espelho) sem I/O de banco."""
    if is_discursive and explicit_is_correct is not None:
        is_correct = 1 if explicit_is_correct else 0
    elif is_discursive and confidence == "defer":
        is_correct = 0
    else:
        is_correct = check_is_correct(selected, correct_letter, correct_alts)

    next_review = None
    card_before = None
    reviewed_at = None
    twin_card_before = None
    twin_reviewed_at = None
    srs_upserts: dict[int, tuple] = {}

    if confidence != "defer":
        reviewed_at = now.astimezone(UTC).isoformat()
        card_before = srs_map.get(qid)
        card_json, next_review = srs.review(
            card_before, is_correct, confidence, now=now, assisted=is_assisted
        )
        srs_map[qid] = card_json
        srs_upserts[qid] = (qid, next_review, card_json, user_id)

        if twin_id:
            twin_card_before = srs_map.get(twin_id)
            twin_card_json, twin_next_review = srs.review(
                twin_card_before, is_correct, confidence, now=now, assisted=is_assisted
            )
            srs_map[twin_id] = twin_card_json
            twin_reviewed_at = reviewed_at
            srs_upserts[twin_id] = (twin_id, twin_next_review, twin_card_json, user_id)

    return is_correct, next_review, card_before, reviewed_at, twin_card_before, twin_reviewed_at, srs_upserts


@bp.route("/questions/<int:qid>/attempt", methods=["POST"])
@idempotent()
def submit_attempt(qid):
    from .questions import invalidate_user_caches

    db = get_db()
    try:
        payload = AttemptIn.model_validate(request.get_json(force=True) or {})
    except ValidationError as e:
        return jsonify({"error": "invalid input", "code": "INVALID_INPUT", "details": validation_errors(e)}), 400

    q_exp_sql = """
        SELECT q.correct_letter, q.area, q.subtema, e.explanation_text
        FROM questions q
        LEFT JOIN explanations e ON e.question_id = q.id
        WHERE q.id = ?
    """
    alts_sql = "SELECT letter, is_correct FROM alternatives WHERE question_id = ?"

    if hasattr(db, "batch"):
        pre_res = db.batch([(q_exp_sql, (qid,)), (alts_sql, (qid,))])
        q = pre_res[0].fetchone()
        alts_rows = pre_res[1].fetchall()
    else:
        q = db.execute(q_exp_sql, (qid,)).fetchone()
        alts_rows = db.execute(alts_sql, (qid,)).fetchall()

    if not q:
        return jsonify({"error": "not found", "code": "QUESTION_NOT_FOUND"}), 404

    is_discursive = bool(len(alts_rows) <= 1)
    correct_alts_set = {
        r["letter"].strip().upper()
        for r in alts_rows
        if r["is_correct"] and r["letter"]
    }
    explanation_text = q["explanation_text"]

    with db_transaction(db, immediate=True):
        now = datetime.now(UTC)
        selected = (payload.selected_letter or "A").upper()
        observed_at = _resolve_answered_at(payload.answered_at, fallback_now=now)
        is_assisted = bool(getattr(payload, "assisted", False))
        assisted_flag = 1 if is_assisted else 0
        twin_id = payload.twin_for_question_id

        srs_map = {}
        if payload.confidence != "defer":
            srs_targets = [qid] + ([twin_id] if twin_id else [])
            srs_map = _fetch_srs_map(db, srs_targets, g.user_id)

        (
            is_correct,
            next_review,
            card_before,
            reviewed_at,
            twin_card_before,
            twin_reviewed_at,
            srs_upserts,
        ) = _compute_attempt_srs_outcome(
            qid=qid,
            user_id=g.user_id,
            selected=selected,
            correct_letter=q["correct_letter"],
            correct_alts=correct_alts_set,
            is_discursive=is_discursive,
            explicit_is_correct=payload.is_correct,
            confidence=payload.confidence,
            is_assisted=is_assisted,
            twin_id=twin_id,
            now=now,
            srs_map=srs_map,
        )

        cursor = _insert_attempts_rows(
            db,
            [(
                qid,
                selected,
                is_correct,
                observed_at,
                payload.time_spent_ms,
                payload.confidence,
                g.user_id,
                assisted_flag,
                card_before,
                reviewed_at,
                twin_card_before,
                twin_reviewed_at,
            )],
            bulk=False,
        )
        attempt_id = getattr(cursor, "lastrowid", None)
        if not attempt_id:
            att_row = db.execute(
                "SELECT id FROM attempts WHERE question_id = ? AND user_id = ? ORDER BY id DESC LIMIT 1",
                (qid, g.user_id),
            ).fetchone()
            attempt_id = att_row["id"] if att_row else None

        if payload.confidence == "defer":
            _defer_question_review(db, qid, g.user_id)
            if twin_id:
                _defer_question_review(db, twin_id, g.user_id)
        else:
            _upsert_spaced_repetition_batch(db, list(srs_upserts.values()))

        alt_stats = None
        if not is_discursive:
            stat_rows = db.execute(
                """SELECT UPPER(TRIM(selected_letter)) AS letter, COUNT(*) AS cnt
                   FROM attempts
                   WHERE question_id = ? AND selected_letter IS NOT NULL AND TRIM(selected_letter) != ''
                   GROUP BY UPPER(TRIM(selected_letter))""",
                (qid,),
            ).fetchall()
            total_votes = sum(int(r["cnt"] or 0) for r in stat_rows)
            if total_votes > 0:
                alt_stats = {
                    r["letter"]: round((int(r["cnt"]) / total_votes) * 100)
                    for r in stat_rows
                    if r["letter"]
                }

        reported_is_correct = (
            None
            if (is_discursive and payload.confidence == "defer" and payload.is_correct is None)
            else bool(is_correct)
        )
        resp_data = {
            "is_correct": reported_is_correct,
            "correct_letter": q["correct_letter"],
            "explanation": explanation_text,
            "next_review_date": next_review,
            "is_discursive": is_discursive,
            "attempt_id": attempt_id,
            "assisted": is_assisted,
            **({"alt_stats": alt_stats} if alt_stats else {}),
        }
        complete_active_lease(200, resp_data)

    invalidate_user_caches(g.user_id)
    record_domain_event(
        "study_attempt_completed",
        user_id=g.user_id,
        question_id=qid,
        is_correct=reported_is_correct,
        confidence=payload.confidence,
        time_spent_ms=payload.time_spent_ms,
        area=q["area"] if q else None,
        subtema=q["subtema"] if q else None,
    )
    return jsonify(resp_data)


@bp.route("/questions/<int:qid>/review", methods=["POST"])
@idempotent()
def review_fsrs(qid):
    from .questions import invalidate_user_caches

    db = get_db()
    try:
        data = ReviewIn.model_validate(request.get_json(force=True) or {})
    except ValidationError as e:
        return jsonify({"error": "invalid input", "code": "INVALID_INPUT", "details": validation_errors(e)}), 400
    confidence = data.confidence

    with db_transaction(db, immediate=True):
        now = datetime.now(UTC)
        last_attempt = None
        if getattr(data, "attempt_id", None) is not None:
            try:
                last_attempt = db.execute(
                    """SELECT id, is_correct, confidence, assisted,
                              fsrs_card_before, fsrs_reviewed_at, twin_card_before, twin_reviewed_at
                       FROM attempts WHERE id = ? AND question_id = ? AND user_id = ?""",
                    (data.attempt_id, qid, g.user_id),
                ).fetchone()
            except Exception:
                last_attempt = db.execute(
                    "SELECT id, is_correct, confidence FROM attempts WHERE id = ? AND question_id = ? AND user_id = ?",
                    (data.attempt_id, qid, g.user_id),
                ).fetchone()

        if not last_attempt:
            try:
                last_attempt = db.execute(
                    """SELECT id, is_correct, confidence, assisted,
                              fsrs_card_before, fsrs_reviewed_at, twin_card_before, twin_reviewed_at
                       FROM attempts WHERE question_id = ? AND user_id = ? ORDER BY id DESC LIMIT 1""",
                    (qid, g.user_id),
                ).fetchone()
            except Exception:
                last_attempt = db.execute(
                    "SELECT id, is_correct, confidence FROM attempts WHERE question_id = ? AND user_id = ? ORDER BY id DESC LIMIT 1",
                    (qid, g.user_id),
                ).fetchone()

        if not last_attempt:
            return jsonify({"error": "No attempt found", "code": "NO_ATTEMPT_FOUND"}), 400

        attempt_id = last_attempt["id"]
        prev_confidence = last_attempt["confidence"]
        prev_is_correct = int(bool(last_attempt["is_correct"]))
        attempt_dict = dict(last_attempt)
        is_assisted = bool(data.assisted) if data.assisted is not None else bool(attempt_dict.get("assisted", 0))
        already_applied = prev_confidence != "defer"
        is_correct_changed = (
            data.is_correct is not None
            and int(bool(data.is_correct)) != prev_is_correct
        )

        if not already_applied:
            is_correct_for_srs = int(bool(data.is_correct)) if data.is_correct is not None else prev_is_correct
            if data.is_correct is not None:
                db.execute(
                    "UPDATE attempts SET confidence = ?, is_correct = ? WHERE id = ? AND user_id = ?",
                    (confidence, is_correct_for_srs, attempt_id, g.user_id),
                )
            else:
                db.execute(
                    "UPDATE attempts SET confidence = ? WHERE id = ? AND user_id = ?",
                    (confidence, attempt_id, g.user_id),
                )
            card_before, next_review, reviewed_at = _apply_fsrs(
                db, qid, g.user_id, is_correct_for_srs, confidence, is_assisted, now
            )
            twin_card_before = None
            twin_reviewed_at = None
            if data.twin_for_question_id:
                twin_card_before, _, twin_reviewed_at = _apply_fsrs(
                    db, data.twin_for_question_id, g.user_id, is_correct_for_srs, confidence, is_assisted, now
                )
            _save_attempt_fsrs_snapshot(
                db, attempt_id, g.user_id, card_before, reviewed_at, twin_card_before, twin_reviewed_at
            )
            resp_data = {
                "success": True,
                "next_review_date": next_review,
                "is_correct": bool(is_correct_for_srs),
                "assisted": is_assisted,
            }
        elif not is_correct_changed:
            if confidence != prev_confidence:
                db.execute(
                    "UPDATE attempts SET confidence = ? WHERE id = ? AND user_id = ?",
                    (confidence, attempt_id, g.user_id),
                )
            existing_sr = db.execute(
                "SELECT next_review_date FROM spaced_repetition WHERE question_id = ? AND user_id = ?",
                (qid, g.user_id),
            ).fetchone()
            resp_data = {
                "success": True,
                "next_review_date": existing_sr["next_review_date"] if existing_sr else None,
                "is_correct": bool(prev_is_correct),
                "assisted": is_assisted,
                "warning": "Confiança atualizada, mas FSRS retido na primeira impressão para evitar avanço duplo.",
            }
        else:
            new_is_correct = int(bool(data.is_correct))
            latest_row = db.execute(
                "SELECT MAX(id) AS max_id FROM attempts WHERE question_id = ? AND user_id = ?",
                (qid, g.user_id),
            ).fetchone()
            is_latest = bool(latest_row and latest_row["max_id"] == attempt_id)
            fsrs_reviewed_at = attempt_dict.get("fsrs_reviewed_at")

            if not is_latest or not fsrs_reviewed_at:
                db.execute(
                    "UPDATE attempts SET confidence = ?, is_correct = ? WHERE id = ? AND user_id = ?",
                    (confidence, new_is_correct, attempt_id, g.user_id),
                )
                existing_sr = db.execute(
                    "SELECT next_review_date FROM spaced_repetition WHERE question_id = ? AND user_id = ?",
                    (qid, g.user_id),
                ).fetchone()
                resp_data = {
                    "success": True,
                    "next_review_date": existing_sr["next_review_date"] if existing_sr else None,
                    "is_correct": bool(new_is_correct),
                    "assisted": is_assisted,
                    "warning": "Nota retificada, mas o agendamento FSRS foi preservado.",
                }
            else:
                preserved_any = False
                sr = db.execute(
                    "SELECT fsrs_card, next_review_date FROM spaced_repetition WHERE question_id = ? AND user_id = ?",
                    (qid, g.user_id),
                ).fetchone()
                current_last_review = _card_last_review_dt(sr["fsrs_card"] if sr else None)
                attempt_reviewed_dt = _parse_utc_dt(fsrs_reviewed_at)
                if (
                    current_last_review is not None
                    and attempt_reviewed_dt is not None
                    and current_last_review == attempt_reviewed_dt
                ):
                    try:
                        new_card_json, next_review = srs.review(
                            attempt_dict.get("fsrs_card_before"),
                            new_is_correct,
                            confidence,
                            now=attempt_reviewed_dt,
                            assisted=is_assisted,
                        )
                    except Exception:
                        logger.error("Erro ao retificar FSRS (question_id=%s, user_id=%s)", qid, g.user_id)
                        raise
                    _upsert_spaced_repetition(db, qid, g.user_id, next_review, new_card_json)
                else:
                    next_review = sr["next_review_date"] if sr else None
                    preserved_any = True

                if data.twin_for_question_id:
                    orig_qid = data.twin_for_question_id
                    twin_reviewed_at = attempt_dict.get("twin_reviewed_at")
                    if twin_reviewed_at:
                        orig_sr = db.execute(
                            "SELECT fsrs_card FROM spaced_repetition WHERE question_id = ? AND user_id = ?",
                            (orig_qid, g.user_id),
                        ).fetchone()
                        twin_last_review = _card_last_review_dt(orig_sr["fsrs_card"] if orig_sr else None)
                        twin_reviewed_dt = _parse_utc_dt(twin_reviewed_at)
                        if (
                            twin_last_review is not None
                            and twin_reviewed_dt is not None
                            and twin_last_review == twin_reviewed_dt
                        ):
                            try:
                                new_twin_json, new_twin_due = srs.review(
                                    attempt_dict.get("twin_card_before"),
                                    new_is_correct,
                                    confidence,
                                    now=twin_reviewed_dt,
                                    assisted=is_assisted,
                                )
                            except Exception:
                                logger.error(
                                    "Erro ao retificar FSRS da questão espelho (question_id=%s, user_id=%s)",
                                    orig_qid,
                                    g.user_id,
                                )
                                raise
                            _upsert_spaced_repetition(db, orig_qid, g.user_id, new_twin_due, new_twin_json)
                        else:
                            preserved_any = True

                db.execute(
                    "UPDATE attempts SET confidence = ?, is_correct = ? WHERE id = ? AND user_id = ?",
                    (confidence, new_is_correct, attempt_id, g.user_id),
                )
                resp_data = {
                    "success": True,
                    "next_review_date": next_review,
                    "is_correct": bool(new_is_correct),
                    "assisted": is_assisted,
                }
                if preserved_any:
                    resp_data["warning"] = "Agendamento FSRS preservado para card revisado posteriormente."

        complete_active_lease(200, resp_data)

    invalidate_user_caches(g.user_id)
    return jsonify(resp_data)


def _process_single_attempt(
    db,
    item,
    user_id: int,
    answered_at: str,
    q_map: dict,
    correct_alts_map: dict,
    exp_map: dict,
    srs_map: dict,
    now: datetime | None = None,
    alts_count_map: dict | None = None,
) -> dict | None:
    if item.question_id not in q_map:
        return None
    correct_letter = q_map.get(item.question_id)
    review_now = now if now is not None else datetime.now(UTC)
    selected = (item.selected_letter or "A").upper()
    is_discursive = bool((alts_count_map or {}).get(item.question_id, 2) <= 1)
    conf = item.confidence or "duvida"
    is_assisted = bool(getattr(item, "assisted", False))
    item_answered_at = (
        _resolve_answered_at(getattr(item, "answered_at", None), fallback_now=review_now)
        if getattr(item, "answered_at", None)
        else answered_at
    )
    twin_id = getattr(item, "twin_for_question_id", None)

    (
        is_correct,
        next_review,
        card_before,
        reviewed_at,
        twin_card_before,
        twin_reviewed_at,
        srs_upserts,
    ) = _compute_attempt_srs_outcome(
        qid=item.question_id,
        user_id=user_id,
        selected=selected,
        correct_letter=correct_letter,
        correct_alts=correct_alts_map.get(item.question_id),
        is_discursive=is_discursive,
        explicit_is_correct=item.is_correct,
        confidence=conf,
        is_assisted=is_assisted,
        twin_id=twin_id,
        now=review_now,
        srs_map=srs_map,
    )

    _insert_attempts_rows(
        db,
        [(
            item.question_id,
            selected,
            is_correct,
            item_answered_at,
            item.time_spent_ms,
            conf,
            user_id,
            1 if is_assisted else 0,
            card_before,
            reviewed_at,
            twin_card_before,
            twin_reviewed_at,
        )],
        bulk=False,
    )

    if conf == "defer":
        _defer_question_review(db, item.question_id, user_id)
        if twin_id:
            _defer_question_review(db, twin_id, user_id)
    else:
        _upsert_spaced_repetition_batch(db, list(srs_upserts.values()))

    return {
        "question_id": item.question_id,
        "is_correct": None if (is_discursive and conf == "defer" and item.is_correct is None) else bool(is_correct),
        "correct_letter": correct_letter,
        "explanation": exp_map.get(item.question_id),
        "next_review_date": next_review,
        "is_discursive": is_discursive,
        "assisted": is_assisted,
    }


@bp.route("/attempt/batch", methods=["POST"])
@idempotent()
def submit_attempt_batch():
    from .questions import invalidate_user_caches

    db = get_db()
    try:
        payload = BatchAttemptIn.model_validate(request.get_json(force=True) or {})
    except ValidationError as e:
        return jsonify({"error": "invalid input", "details": validation_errors(e)}), 400

    results = []
    now = datetime.now(UTC)
    answered_at = now.isoformat()

    q_ids = [item.question_id for item in payload.attempts]
    if not q_ids:
        return jsonify({"results": []})

    q_map, correct_alts_map, exp_map, alts_count_map = _fetch_batch_metadata_with_counts(db, q_ids)
    srs_q_ids = list(q_ids)
    for item in payload.attempts:
        twin_id = getattr(item, "twin_for_question_id", None)
        if twin_id:
            srs_q_ids.append(twin_id)

    with db_transaction(db, immediate=True):
        srs_map = _fetch_srs_map(db, srs_q_ids, g.user_id)
        attempt_rows: list[tuple] = []
        srs_upsert_map: dict[int, tuple] = {}
        defer_qids: list[int] = []

        for item in payload.attempts:
            if item.question_id not in q_map:
                continue
            correct_letter = q_map.get(item.question_id)
            selected = (item.selected_letter or "A").upper()
            is_discursive = bool(alts_count_map.get(item.question_id, 2) <= 1)
            conf = item.confidence or "duvida"
            is_assisted = bool(getattr(item, "assisted", False))
            item_answered_at = (
                _resolve_answered_at(getattr(item, "answered_at", None), fallback_now=now)
                if getattr(item, "answered_at", None)
                else answered_at
            )
            twin_id = getattr(item, "twin_for_question_id", None)

            (
                is_correct,
                next_review,
                card_before,
                reviewed_at,
                twin_card_before,
                twin_reviewed_at,
                item_srs_upserts,
            ) = _compute_attempt_srs_outcome(
                qid=item.question_id,
                user_id=g.user_id,
                selected=selected,
                correct_letter=correct_letter,
                correct_alts=correct_alts_map.get(item.question_id),
                is_discursive=is_discursive,
                explicit_is_correct=item.is_correct,
                confidence=conf,
                is_assisted=is_assisted,
                twin_id=twin_id,
                now=now,
                srs_map=srs_map,
            )

            if conf == "defer":
                defer_qids.append(item.question_id)
                if twin_id:
                    defer_qids.append(twin_id)
            else:
                srs_upsert_map.update(item_srs_upserts)

            attempt_rows.append((
                item.question_id,
                selected,
                is_correct,
                item_answered_at,
                item.time_spent_ms,
                conf,
                g.user_id,
                1 if is_assisted else 0,
                card_before,
                reviewed_at,
                twin_card_before,
                twin_reviewed_at,
            ))
            results.append({
                "question_id": item.question_id,
                "is_correct": None if (is_discursive and conf == "defer" and item.is_correct is None) else bool(is_correct),
                "correct_letter": correct_letter,
                "explanation": exp_map.get(item.question_id),
                "next_review_date": next_review,
                "is_discursive": is_discursive,
                "assisted": is_assisted,
            })

        _insert_attempts_rows(db, attempt_rows, bulk=True)
        if srs_upsert_map:
            _upsert_spaced_repetition_batch(db, list(srs_upsert_map.values()))
        if defer_qids:
            _defer_questions_batch(db, defer_qids, g.user_id)

        resp_data = {"results": results}
        complete_active_lease(200, resp_data)

    invalidate_user_caches(g.user_id)
    return jsonify(resp_data)
