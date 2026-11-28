"""Blueprint HTTP da Central do 6º Ano & R1 (Rotina, Plantões, Currículo, Marcos e Feed)."""
from __future__ import annotations

import json
import re
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from flask import Blueprint, g, jsonify, make_response, request

from .db import db_transaction, get_db
from .questions import invalidate_user_caches
from .rate_limit import check_rate_limit
from .schemas import (
    CurriculumEntryIn,
    DayOverrideIn,
    MarchaIn,
    MilestoneIn,
    MilestonePatchIn,
    ShiftsBatchIn,
    SixYearPlanPatchIn,
    ValidationError,
    validation_errors,
)
from .services.planner_ics import _get_base_url
from .services.six_year_routine import (
    block_for_date,
    compute_7030_balance,
    effective_marcha,
    hash_feed_token,
    load_plan_row,
    load_routine_context,
    local_today,
    resolve_day,
    resolve_feed_token_user,
    resolve_ferias_week_id,
    resolve_range,
    ritual_cycle_key,
    summarize_week,
    week_iso_of,
)
from .timezones import DEFAULT_TZ

bp = Blueprint("six_year", __name__)

_ITEM_ID_RE = re.compile(r"^[a-z0-9_]{1,80}$")
_MILESTONE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_MAX_PREVIEW_DAYS = 62


def _parse_iso_date(raw: str | None) -> date | None:
    if not raw or not isinstance(raw, str) or len(raw) != 10:
        return None
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == raw else None


def _default_plan_payload(plan: dict[str, Any] | None) -> dict[str, Any]:
    if not plan:
        return {
            "routine_mode_enabled": False,
            "enamed_concept": 5,
            "foco_override": {},
            "ritual_done": {},
            "has_feed_token": False,
            "feed_token_created_at": None,
        }
    return {
        "routine_mode_enabled": bool(plan["routine_mode_enabled"]),
        "enamed_concept": int(plan["enamed_concept"]),
        "foco_override": dict(plan["foco_override"]),
        "ritual_done": dict(plan["ritual_done"]),
        "has_feed_token": bool(plan["has_feed_token"]),
        "feed_token_created_at": plan["feed_token_created_at"],
    }


def _find_next_block(today_date: date, blocks: list[dict[str, Any]]) -> dict[str, Any] | None:
    today_iso = today_date.isoformat()
    upcoming = [
        b for b in blocks
        if isinstance(b, dict) and str(b.get("start") or "") > today_iso
    ]
    if not upcoming:
        return None
    upcoming.sort(key=lambda b: str(b.get("start") or ""))
    nxt = upcoming[0]
    return {
        "id": nxt.get("id"),
        "label": nxt.get("label") or nxt.get("area"),
        "start": nxt.get("start"),
        "end": nxt.get("end"),
    }


def _serialize_milestone(row: Any) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "titulo": str(row["titulo"]),
        "data_iso": str(row["data_iso"]),
        "categoria": str(row["categoria"]),
        "done": bool(row["done"]),
        "note": str(row["note"] or ""),
        "updated_at": str(row["updated_at"]),
    }


@bp.route("/six-year/summary", methods=["GET"])
def six_year_summary():
    db = get_db()
    user_id = g.user_id
    today_date = local_today()

    plan_row = load_plan_row(db, user_id)
    plan_payload = _default_plan_payload(plan_row)

    window_from = today_date - timedelta(days=3)
    window_to = today_date + timedelta(days=10)
    ctx = load_routine_context(db, user_id, window_from, window_to)

    today_status = resolve_day(today_date, ctx)
    days_payload = [d.to_dict() for d in resolve_range(db, user_id, window_from, window_to, ctx=ctx)]
    week_payload = summarize_week(week_iso_of(today_date), ctx)

    rodizio_active = block_for_date(today_date, ctx.blocks)
    next_block = _find_next_block(today_date, ctx.blocks)
    rodizio_payload: dict[str, Any] | None = None
    if rodizio_active is not None:
        rid = rodizio_active.get("id")
        ov = (plan_payload["foco_override"].get(rid) or {}) if rid else {}
        ancora_eff = ov.get("ancora70") or rodizio_active.get("ancora70") or ""
        trilha_eff = ov.get("trilha30") or rodizio_active.get("trilha30") or ""
        rodizio_payload = {
            **rodizio_active,
            "foco_effective": {
                "ancora70": ancora_eff,
                "trilha30": trilha_eff,
                "is_override": bool(ov.get("ancora70") or ov.get("trilha30")),
            },
            "next": next_block,
        }

    balance_7030 = compute_7030_balance(db, user_id, today_date, rodizio_active)

    cycle_key = ritual_cycle_key(today_date)
    raw_cycle_done = plan_payload["ritual_done"].get(cycle_key)
    cycle_done = {k: bool(v) for k, v in raw_cycle_done.items()} if isinstance(raw_cycle_done, dict) else {}

    curr_rows = db.execute(
        """
        SELECT item_id, value, proof_status, note, updated_at
        FROM user_curriculum_entries
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchall()
    curriculum_entries = {
        str(r["item_id"]): {
            "value": float(r["value"]),
            "proof_status": str(r["proof_status"]),
            "note": str(r["note"] or ""),
            "updated_at": str(r["updated_at"]),
        }
        for r in curr_rows
    }

    ms_rows = db.execute(
        """
        SELECT id, titulo, data_iso, categoria, done, note, updated_at
        FROM user_r1_milestones
        WHERE user_id = ?
        ORDER BY data_iso ASC, id ASC
        """,
        (user_id,),
    ).fetchall()
    milestones = [_serialize_milestone(r) for r in ms_rows]

    undone = [m for m in milestones if not m["done"]]
    upcoming_undone = [m for m in undone if m["data_iso"] >= today_date.isoformat()]
    chosen_next = upcoming_undone[0] if upcoming_undone else (undone[0] if undone else None)
    next_milestone = None
    if chosen_next is not None:
        m_date = _parse_iso_date(chosen_next["data_iso"])
        days_left = (m_date - today_date).days if m_date else None
        next_milestone = {
            "id": chosen_next["id"],
            "titulo": chosen_next["titulo"],
            "data_iso": chosen_next["data_iso"],
            "categoria": chosen_next["categoria"],
            "days_left": days_left,
        }

    return jsonify({
        "today": today_status.to_dict(),
        "plan": plan_payload,
        "rodizio": rodizio_payload,
        "next_rodizio": next_block,
        "week": week_payload,
        "days": days_payload,
        "balance_7030": balance_7030,
        "ritual": {
            "cycle_key": cycle_key,
            "done": cycle_done,
        },
        "ferias": {
            "current_week_id": resolve_ferias_week_id(today_date),
        },
        "curriculum_entries": curriculum_entries,
        "milestones": milestones,
        "next_milestone": next_milestone,
    })


@bp.route("/six-year/plan", methods=["PATCH"])
def patch_six_year_plan():
    raw_body = request.get_json(silent=True)
    if not isinstance(raw_body, dict):
        return jsonify({"error": "invalid input"}), 400
    try:
        data = SixYearPlanPatchIn.model_validate(raw_body)
    except ValidationError as e:
        return jsonify({"error": "invalid input", "details": validation_errors(e)}), 400

    db = get_db()
    user_id = g.user_id
    now_iso = datetime.now(UTC).isoformat()

    with db_transaction(db, immediate=True):
        existing = load_plan_row(db, user_id)
        routine_enabled = (
            bool(data.routine_mode_enabled)
            if data.routine_mode_enabled is not None
            else (bool(existing["routine_mode_enabled"]) if existing else False)
        )
        enamed_concept = (
            int(data.enamed_concept)
            if data.enamed_concept is not None
            else (int(existing["enamed_concept"]) if existing else 5)
        )
        foco_override: dict[str, dict[str, str]] = {}
        if existing and isinstance(existing["foco_override"], dict):
            for rid, val in existing["foco_override"].items():
                if isinstance(val, dict):
                    foco_override[str(rid)] = {
                        str(k): str(v) for k, v in val.items() if v is not None
                    }
        if data.foco_override is not None:
            for rid, updates in data.foco_override.items():
                current = dict(foco_override.get(rid, {}))
                for field_key, field_val in updates.items():
                    if field_val is None or not str(field_val).strip():
                        current.pop(field_key, None)
                    else:
                        current[field_key] = str(field_val).strip()
                if current:
                    foco_override[rid] = current
                else:
                    foco_override.pop(rid, None)

        ritual_done: dict[str, dict[str, bool]] = {}
        if existing and isinstance(existing["ritual_done"], dict):
            for ck, val in existing["ritual_done"].items():
                if isinstance(val, dict):
                    ritual_done[str(ck)] = {
                        str(k): True for k, v in val.items() if bool(v)
                    }
        if data.ritual_done is not None:
            for ck, items in data.ritual_done.items():
                current_cycle = dict(ritual_done.get(ck, {}))
                for item_key, checked in items.items():
                    if checked:
                        current_cycle[item_key] = True
                    else:
                        current_cycle.pop(item_key, None)
                if current_cycle:
                    ritual_done[ck] = current_cycle
                else:
                    ritual_done.pop(ck, None)

        db.execute(
            """
            INSERT INTO user_six_year_plan (
                user_id, routine_mode_enabled, enamed_concept,
                foco_override_json, ritual_done_json, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                routine_mode_enabled = excluded.routine_mode_enabled,
                enamed_concept = excluded.enamed_concept,
                foco_override_json = excluded.foco_override_json,
                ritual_done_json = excluded.ritual_done_json,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                1 if routine_enabled else 0,
                enamed_concept,
                json.dumps(foco_override, ensure_ascii=False),
                json.dumps(ritual_done, ensure_ascii=False),
                now_iso,
            ),
        )
        updated = load_plan_row(db, user_id)

    invalidate_user_caches(user_id)
    return jsonify({"plan": _default_plan_payload(updated)})


@bp.route("/six-year/marcha/<week_iso>", methods=["PUT"])
def put_six_year_marcha(week_iso: str):
    parsed = _parse_iso_date(week_iso)
    if parsed is None or parsed.weekday() != 0:
        return jsonify({"error": "week_iso must be a valid Monday in YYYY-MM-DD format"}), 400

    raw_body = request.get_json(silent=True)
    if not isinstance(raw_body, dict):
        return jsonify({"error": "invalid input"}), 400
    try:
        data = MarchaIn.model_validate(raw_body)
    except ValidationError as e:
        return jsonify({"error": "invalid input", "details": validation_errors(e)}), 400

    db = get_db()
    user_id = g.user_id
    now_iso = datetime.now(UTC).isoformat()

    with db_transaction(db, immediate=True):
        if data.marcha_id is None:
            db.execute(
                "DELETE FROM user_week_marcha WHERE user_id = ? AND week_iso = ?",
                (user_id, week_iso),
            )
        else:
            db.execute(
                """
                INSERT INTO user_week_marcha (user_id, week_iso, marcha_id, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, week_iso) DO UPDATE SET
                    marcha_id = excluded.marcha_id,
                    updated_at = excluded.updated_at
                """,
                (user_id, week_iso, data.marcha_id, now_iso),
            )

    invalidate_user_caches(user_id)
    ctx = load_routine_context(db, user_id, parsed, parsed + timedelta(days=6))
    eff_id, eff_src = effective_marcha(week_iso, ctx)
    return jsonify({
        "week_iso": week_iso,
        "marcha_id": eff_id,
        "marcha_source": eff_src,
    })


@bp.route("/six-year/shifts/batch", methods=["POST"])
def post_shifts_batch():
    raw_body = request.get_json(silent=True)
    if not isinstance(raw_body, dict):
        return jsonify({"error": "invalid input"}), 400
    try:
        data = ShiftsBatchIn.model_validate(raw_body)
    except ValidationError as e:
        return jsonify({"error": "invalid input", "details": validation_errors(e)}), 400

    db = get_db()
    user_id = g.user_id
    now_iso = datetime.now(UTC).isoformat()

    remove_keys: list[tuple[str, str]] = list(
        dict.fromkeys((item.date_iso, item.kind) for item in data.remove)
    )
    add_map: dict[tuple[str, str], str] = {}
    for item in data.add:
        add_map[(item.date_iso, item.kind)] = item.note

    affected_dates: set[date] = set()
    added_count = 0
    removed_count = 0

    with db_transaction(db, immediate=True):
        for date_iso, kind in remove_keys:
            affected_dates.add(date.fromisoformat(date_iso))
            exists = db.execute(
                "SELECT 1 FROM user_shifts WHERE user_id = ? AND date_iso = ? AND kind = ?",
                (user_id, date_iso, kind),
            ).fetchone()
            if exists:
                db.execute(
                    "DELETE FROM user_shifts WHERE user_id = ? AND date_iso = ? AND kind = ?",
                    (user_id, date_iso, kind),
                )
                removed_count += 1

        for (date_iso, kind), note in add_map.items():
            affected_dates.add(date.fromisoformat(date_iso))
            exists = db.execute(
                "SELECT 1 FROM user_shifts WHERE user_id = ? AND date_iso = ? AND kind = ?",
                (user_id, date_iso, kind),
            ).fetchone()
            if exists:
                db.execute(
                    """
                    UPDATE user_shifts SET note = ?, updated_at = ?
                    WHERE user_id = ? AND date_iso = ? AND kind = ?
                    """,
                    (note, now_iso, user_id, date_iso, kind),
                )
            else:
                db.execute(
                    """
                    INSERT INTO user_shifts (user_id, date_iso, kind, note, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (user_id, date_iso, kind, note, now_iso),
                )
                added_count += 1

    invalidate_user_caches(user_id)

    days_out: list[dict[str, Any]] = []
    if affected_dates:
        expanded: set[date] = set()
        for d in affected_dates:
            expanded.add(d - timedelta(days=1))
            expanded.add(d)
            expanded.add(d + timedelta(days=1))
        sorted_days = sorted(expanded)
        ctx = load_routine_context(db, user_id, sorted_days[0], sorted_days[-1])
        days_out = [resolve_day(d, ctx).to_dict() for d in sorted_days]

    return jsonify({
        "added": added_count,
        "removed": removed_count,
        "days": days_out,
    })


@bp.route("/six-year/day-override/<date_iso>", methods=["PUT"])
def put_day_override(date_iso: str):
    parsed = _parse_iso_date(date_iso)
    if parsed is None:
        return jsonify({"error": "invalid date_iso"}), 400

    raw_body = request.get_json(silent=True)
    if not isinstance(raw_body, dict):
        return jsonify({"error": "invalid input"}), 400
    try:
        data = DayOverrideIn.model_validate(raw_body)
    except ValidationError as e:
        return jsonify({"error": "invalid input", "details": validation_errors(e)}), 400

    db = get_db()
    user_id = g.user_id
    now_iso = datetime.now(UTC).isoformat()

    with db_transaction(db, immediate=True):
        db.execute(
            """
            INSERT INTO user_day_overrides (user_id, date_iso, mode, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, date_iso) DO UPDATE SET
                mode = excluded.mode,
                updated_at = excluded.updated_at
            """,
            (user_id, date_iso, data.mode, now_iso),
        )

    invalidate_user_caches(user_id)
    day_status = resolve_range(db, user_id, parsed, parsed)[0]
    return jsonify({"day": day_status.to_dict()})


@bp.route("/six-year/day-override/<date_iso>", methods=["DELETE"])
def delete_day_override(date_iso: str):
    parsed = _parse_iso_date(date_iso)
    if parsed is None:
        return jsonify({"error": "invalid date_iso"}), 400

    db = get_db()
    user_id = g.user_id

    with db_transaction(db, immediate=True):
        db.execute(
            "DELETE FROM user_day_overrides WHERE user_id = ? AND date_iso = ?",
            (user_id, date_iso),
        )

    invalidate_user_caches(user_id)
    day_status = resolve_range(db, user_id, parsed, parsed)[0]
    return jsonify({"day": day_status.to_dict()})


@bp.route("/six-year/preview", methods=["GET"])
def get_six_year_preview():
    raw_from = request.args.get("from")
    raw_to = request.args.get("to")
    d_from = _parse_iso_date(raw_from)
    d_to = _parse_iso_date(raw_to)
    if d_from is None or d_to is None:
        return jsonify({"error": "query parameters 'from' and 'to' must be valid YYYY-MM-DD dates"}), 400
    if d_from > d_to:
        return jsonify({"error": "'from' must be <= 'to'"}), 400
    span_days = (d_to - d_from).days + 1
    if span_days > _MAX_PREVIEW_DAYS:
        return jsonify({"error": f"date range exceeds maximum of {_MAX_PREVIEW_DAYS} days"}), 400

    db = get_db()
    user_id = g.user_id
    ctx = load_routine_context(db, user_id, d_from, d_to)
    resolved_days = resolve_range(db, user_id, d_from, d_to, ctx=ctx)

    week_isos: list[str] = []
    seen_weeks: set[str] = set()
    for i in range(span_days):
        w_iso = week_iso_of(d_from + timedelta(days=i))
        if w_iso not in seen_weeks:
            seen_weeks.add(w_iso)
            week_isos.append(w_iso)

    weeks_out = [summarize_week(w, ctx) for w in week_isos]
    return jsonify({
        "days": [d.to_dict() for d in resolved_days],
        "weeks": weeks_out,
    })


@bp.route("/six-year/curriculum/<item_id>", methods=["PUT"])
def put_curriculum_entry(item_id: str):
    if not _ITEM_ID_RE.fullmatch(item_id):
        return jsonify({"error": "invalid item_id"}), 400

    raw_body = request.get_json(silent=True)
    if not isinstance(raw_body, dict):
        return jsonify({"error": "invalid input"}), 400
    try:
        data = CurriculumEntryIn.model_validate(raw_body)
    except ValidationError as e:
        return jsonify({"error": "invalid input", "details": validation_errors(e)}), 400

    db = get_db()
    user_id = g.user_id
    now_iso = datetime.now(UTC).isoformat()

    with db_transaction(db, immediate=True):
        db.execute(
            """
            INSERT INTO user_curriculum_entries (user_id, item_id, value, proof_status, note, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, item_id) DO UPDATE SET
                value = excluded.value,
                proof_status = excluded.proof_status,
                note = excluded.note,
                updated_at = excluded.updated_at
            """,
            (user_id, item_id, float(data.value), data.proof_status, data.note, now_iso),
        )

    invalidate_user_caches(user_id)
    return jsonify({
        "entry": {
            "item_id": item_id,
            "value": float(data.value),
            "proof_status": data.proof_status,
            "note": data.note,
            "updated_at": now_iso,
        }
    })


@bp.route("/six-year/milestones", methods=["POST"])
def post_milestone():
    raw_body = request.get_json(silent=True)
    if not isinstance(raw_body, dict):
        return jsonify({"error": "invalid input"}), 400
    try:
        data = MilestoneIn.model_validate(raw_body)
    except ValidationError as e:
        return jsonify({"error": "invalid input", "details": validation_errors(e)}), 400

    db = get_db()
    user_id = g.user_id
    milestone_id = data.id or uuid.uuid4().hex
    now_iso = datetime.now(UTC).isoformat()

    with db_transaction(db, immediate=True):
        db.execute(
            """
            INSERT INTO user_r1_milestones (
                user_id, id, titulo, data_iso, categoria, done, note, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, id) DO UPDATE SET
                titulo = excluded.titulo,
                data_iso = excluded.data_iso,
                categoria = excluded.categoria,
                done = excluded.done,
                note = excluded.note,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                milestone_id,
                data.titulo.strip(),
                data.data_iso,
                data.categoria,
                1 if data.done else 0,
                data.note,
                now_iso,
            ),
        )
        row = db.execute(
            """
            SELECT id, titulo, data_iso, categoria, done, note, updated_at
            FROM user_r1_milestones
            WHERE user_id = ? AND id = ?
            """,
            (user_id, milestone_id),
        ).fetchone()

    invalidate_user_caches(user_id)
    return jsonify({"milestone": _serialize_milestone(row)}), 201


@bp.route("/six-year/milestones/<milestone_id>", methods=["PATCH"])
def patch_milestone(milestone_id: str):
    if not _MILESTONE_ID_RE.fullmatch(milestone_id):
        return jsonify({"error": "invalid milestone_id"}), 400

    raw_body = request.get_json(silent=True)
    if not isinstance(raw_body, dict):
        return jsonify({"error": "invalid input"}), 400
    try:
        data = MilestonePatchIn.model_validate(raw_body)
    except ValidationError as e:
        return jsonify({"error": "invalid input", "details": validation_errors(e)}), 400

    db = get_db()
    user_id = g.user_id
    now_iso = datetime.now(UTC).isoformat()

    with db_transaction(db, immediate=True):
        existing = db.execute(
            """
            SELECT id, titulo, data_iso, categoria, done, note, updated_at
            FROM user_r1_milestones
            WHERE user_id = ? AND id = ?
            """,
            (user_id, milestone_id),
        ).fetchone()
        if not existing:
            return jsonify({"error": "Not Found"}), 404

        titulo = data.titulo.strip() if data.titulo is not None else str(existing["titulo"])
        data_iso = data.data_iso if data.data_iso is not None else str(existing["data_iso"])
        categoria = data.categoria if data.categoria is not None else str(existing["categoria"])
        done = (1 if data.done else 0) if data.done is not None else int(existing["done"])
        note = data.note if data.note is not None else str(existing["note"] or "")

        db.execute(
            """
            UPDATE user_r1_milestones
            SET titulo = ?, data_iso = ?, categoria = ?, done = ?, note = ?, updated_at = ?
            WHERE user_id = ? AND id = ?
            """,
            (titulo, data_iso, categoria, done, note, now_iso, user_id, milestone_id),
        )
        updated = db.execute(
            """
            SELECT id, titulo, data_iso, categoria, done, note, updated_at
            FROM user_r1_milestones
            WHERE user_id = ? AND id = ?
            """,
            (user_id, milestone_id),
        ).fetchone()

    invalidate_user_caches(user_id)
    return jsonify({"milestone": _serialize_milestone(updated)})


@bp.route("/six-year/milestones/<milestone_id>", methods=["DELETE"])
def delete_milestone(milestone_id: str):
    if not _MILESTONE_ID_RE.fullmatch(milestone_id):
        return jsonify({"error": "invalid milestone_id"}), 400

    db = get_db()
    user_id = g.user_id

    with db_transaction(db, immediate=True):
        exists = db.execute(
            "SELECT 1 FROM user_r1_milestones WHERE user_id = ? AND id = ?",
            (user_id, milestone_id),
        ).fetchone()
        if not exists:
            return jsonify({"error": "Not Found"}), 404
        db.execute(
            "DELETE FROM user_r1_milestones WHERE user_id = ? AND id = ?",
            (user_id, milestone_id),
        )

    invalidate_user_caches(user_id)
    return "", 204


@bp.route("/six-year/feed-token", methods=["POST"])
def post_feed_token():
    db = get_db()
    user_id = g.user_id
    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_feed_token(raw_token)
    now_iso = datetime.now(UTC).isoformat()

    with db_transaction(db, immediate=True):
        db.execute(
            """
            INSERT INTO user_six_year_plan (
                user_id, routine_mode_enabled, enamed_concept,
                foco_override_json, ritual_done_json,
                feed_token_hash, feed_token_created_at, updated_at
            )
            VALUES (?, 0, 5, '{}', '{}', ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                feed_token_hash = excluded.feed_token_hash,
                feed_token_created_at = excluded.feed_token_created_at,
                updated_at = excluded.updated_at
            """,
            (user_id, token_hash, now_iso, now_iso),
        )

    base = _get_base_url().rstrip("/")
    return jsonify({
        "token": raw_token,
        "feed_url": f"{base}/api/six-year/feed.json?token={raw_token}",
        "ics_url": f"{base}/api/planner/calendar/feed?token={raw_token}",
    })


@bp.route("/six-year/feed-token", methods=["DELETE"])
def delete_feed_token():
    db = get_db()
    user_id = g.user_id
    now_iso = datetime.now(UTC).isoformat()

    with db_transaction(db, immediate=True):
        db.execute(
            """
            UPDATE user_six_year_plan
            SET feed_token_hash = NULL, feed_token_created_at = NULL, updated_at = ?
            WHERE user_id = ?
            """,
            (now_iso, user_id),
        )

    return "", 204


@bp.route("/six-year/feed.json", methods=["GET"])
def get_six_year_feed():
    raw_token = request.args.get("token")
    if raw_token is None:
        return jsonify({"error": "Unauthorized"}), 401

    rl_resp = check_rate_limit(
        "six_year_json_feed", auth_limit=30, window_seconds=60, ip_limit=30
    )
    if rl_resp is not None:
        return rl_resp

    db = get_db()
    target_user_id = resolve_feed_token_user(db, raw_token)
    if not target_user_id:
        return jsonify({"error": "Not Found"}), 404

    plan = load_plan_row(db, target_user_id)
    now_local = datetime.now(DEFAULT_TZ)
    today_date = now_local.date()
    start_d = today_date - timedelta(days=14)
    end_d = today_date + timedelta(days=14)

    ctx = load_routine_context(db, target_user_id, start_d, end_d)
    resolved_days = resolve_range(db, target_user_id, start_d, end_d, ctx=ctx)

    rodizio_active = block_for_date(today_date, ctx.blocks)
    rodizio_today = (
        {
            "id": rodizio_active.get("id"),
            "label": rodizio_active.get("label") or rodizio_active.get("area"),
        }
        if rodizio_active is not None
        else None
    )

    week_isos: list[str] = []
    seen_weeks: set[str] = set()
    for i in range((end_d - start_d).days + 1):
        w_iso = week_iso_of(start_d + timedelta(days=i))
        if w_iso not in seen_weeks:
            seen_weeks.add(w_iso)
            week_isos.append(w_iso)

    weeks_out = []
    for w_iso in week_isos:
        w_sum = summarize_week(w_iso, ctx)
        weeks_out.append({
            "week_iso": w_sum["week_iso"],
            "marcha_id": w_sum["marcha_id"],
            "marcha_source": w_sum["marcha_source"],
            "semana_pesada": w_sum["semana_pesada"],
        })

    days_out = [
        {
            "date_iso": d.date_iso,
            "mode": d.mode,
            "goal_questions": d.goal_questions,
            "is_pos_plantao": d.is_pos_plantao,
            "shifts": list(d.shifts),
        }
        for d in resolved_days
    ]

    resp = make_response(
        jsonify({
            "version": 1,
            "generated_at": now_local.isoformat(timespec="seconds"),
            "timezone": "America/Sao_Paulo",
            "routine_mode_enabled": bool(plan["routine_mode_enabled"]) if plan else False,
            "rodizio_today": rodizio_today,
            "days": days_out,
            "weeks": weeks_out,
        })
    )
    resp.headers["Cache-Control"] = "no-store"
    return resp
