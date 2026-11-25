"""Rotas privadas para videoteca do Google Drive integrada aos 170 subtemas."""
from __future__ import annotations

import requests
from flask import Blueprint, g, jsonify, request

from .auth import require_curator, require_lessons_access
from .db import db_transaction, get_db
from .services import drive_stream as _drive_svc
from .services import lessons_catalog as _catalog_svc
from .services.drive_stream import STREAM_CHUNK_BYTES
from .services.lessons_catalog import (
    DEFAULT_CYCLE_POST_QUESTIONS,
    DEFAULT_CYCLE_PRE_QUESTIONS,
    MAX_BOOKMARK_SECONDS,
    MAX_CYCLE_POST_QUESTIONS,
    MAX_CYCLE_PRE_QUESTIONS,
    VALID_CYCLE_PHASES,
    VALID_STATUSES,
    _now_iso,
    get_continue_lesson,
    get_current_planner_week_subtemas,
    get_lesson_detail_payload,
    get_lessons_by_subtema,
    get_lessons_summary_by_subtema,
    get_user_cycle_settings,
    get_user_cycles_map,
    list_notes,
    query_lessons_catalog,
    save_lesson_progress,
    upsert_cycle_entry,
)
from .services.taxonomy import find_area_for_subtema

bp = Blueprint("lessons", __name__)


def _resolve_drive_oauth_credentials() -> tuple[str, str, str] | None:
    return _drive_svc.resolve_drive_oauth_credentials()


def _get_drive_access_token(force_refresh: bool = False) -> str | None:
    return _drive_svc.get_drive_access_token(
        force_refresh=force_refresh,
        post_fn=requests.post,
        creds_resolver=_resolve_drive_oauth_credentials,
    )


def _build_stream_url(lesson_id: int) -> str | None:
    return _drive_svc.build_stream_url(
        lesson_id=lesson_id,
        user_id=str(getattr(g, "user_id", "") or ""),
        user_email=str(getattr(g, "user_email", "") or ""),
        creds_resolver=_resolve_drive_oauth_credentials,
    )


@bp.after_request
def _add_private_no_store_headers(response):
    response.headers["Cache-Control"] = "private, no-store"
    return response


@bp.route("/lessons", methods=["GET"])
@require_lessons_access
def list_lessons():
    limit_param = (request.args.get("limit") or "").strip()
    limit_val: int | None = None
    if limit_param:
        try:
            parsed_limit = int(limit_param)
            if parsed_limit > 0:
                limit_val = min(parsed_limit, 200)
        except (ValueError, TypeError):
            limit_val = None

    payload = query_lessons_catalog(
        get_db(),
        str(g.user_id),
        course=(request.args.get("course") or "all").strip(),
        area=(request.args.get("area") or "").strip(),
        subtema=(request.args.get("subtema") or "").strip(),
        q=(request.args.get("q") or "").strip(),
        status_filter=(request.args.get("status") or "all").strip(),
        essential_only=(request.args.get("essential_only") or "").strip().lower() in ("1", "true", "yes"),
        limit_val=limit_val,
    )
    return jsonify(payload)


@bp.route("/lessons/summary-by-subtema", methods=["GET"])
@require_lessons_access
def lessons_summary_by_subtema():
    return jsonify(get_lessons_summary_by_subtema(get_db(), str(g.user_id)))


@bp.route("/lessons/current-week", methods=["GET"])
@require_lessons_access
def lessons_current_week():
    mode_arg = (request.args.get("mode") or "").strip() or None
    week_num, subtemas = get_current_planner_week_subtemas(get_db(), str(g.user_id), requested_mode=mode_arg)
    return jsonify({"week": week_num, "subtemas": subtemas})


@bp.route("/lessons/continue", methods=["GET"])
@require_lessons_access
def lessons_continue():
    return jsonify(get_continue_lesson(get_db(), str(g.user_id)))


@bp.route("/lessons/notes", methods=["GET"])
@require_lessons_access
def list_lesson_notes():
    """Lista todas as anotações salvas em aulas do usuário autenticado (Caderno Inteligente)."""
    notes_out = list_notes(
        get_db(),
        str(g.user_id),
        area=(request.args.get("area") or "").strip(),
        q=(request.args.get("q") or "").strip(),
    )
    return jsonify({"notes": notes_out})


@bp.route("/lessons/by-subtema", methods=["GET"])
@require_lessons_access
def lessons_by_subtema():
    subtema = (request.args.get("subtema") or "").strip()
    if not subtema:
        return jsonify({"error": "Parâmetro 'subtema' é obrigatório."}), 400
    return jsonify(get_lessons_by_subtema(get_db(), str(g.user_id), subtema))


@bp.route("/lessons/<int:lesson_id>", methods=["GET"])
@require_lessons_access
def get_lesson_detail(lesson_id: int):
    payload = get_lesson_detail_payload(
        get_db(), str(g.user_id), lesson_id, stream_url_builder=_build_stream_url
    )
    if payload is None:
        return jsonify({"error": "Aula não encontrada."}), 404
    return jsonify(payload)


@bp.route("/lessons/<int:lesson_id>/stream", methods=["GET"])
@require_lessons_access
def stream_lesson_video(lesson_id: int):
    """Faz proxy de streaming HTTP 206 (Range) do arquivo .mp4 original (720p/1080p) da Google Drive API v3."""
    db = get_db()
    row = db.execute(
        "SELECT id, drive_file_id, size_bytes FROM lessons WHERE id = ? AND active = 1",
        (lesson_id,),
    ).fetchone()
    if not row or not row["drive_file_id"]:
        return jsonify({"error": "Aula não encontrada."}), 404

    result, status = _drive_svc.open_drive_video_stream(
        row["drive_file_id"],
        request.headers.get("Range"),
        token_loader=_get_drive_access_token,
        http_get=requests.get,
        chunk_bytes=STREAM_CHUNK_BYTES,
    )
    if isinstance(result, dict):
        return jsonify(result), status
    return result


@bp.route("/lessons/<int:lesson_id>/progress", methods=["PUT"])
@require_lessons_access
def update_lesson_progress(lesson_id: int):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Payload JSON inválido."}), 400

    if "status" in payload and payload["status"] is not None:
        if payload["status"] not in VALID_STATUSES:
            return jsonify({"error": "Status inválido. Use not_started, in_progress ou completed."}), 400

    if "bookmark_seconds" in payload and payload["bookmark_seconds"] is not None:
        raw_bookmark = payload["bookmark_seconds"]
        if type(raw_bookmark) is not int or raw_bookmark < 0 or raw_bookmark > MAX_BOOKMARK_SECONDS:
            return jsonify({"error": "bookmark_seconds deve ser um inteiro entre 0 e 86400."}), 400

    if "notes" in payload and payload["notes"] is not None:
        if not isinstance(payload["notes"], str):
            return jsonify({"error": "notes deve ser texto."}), 400

    sync_theme_theory = payload.get("sync_theme_theory", True)
    if type(sync_theme_theory) is not bool:
        return jsonify({"error": "sync_theme_theory deve ser booleano."}), 400

    saved = save_lesson_progress(get_db(), str(g.user_id), lesson_id, payload)
    if saved is None:
        return jsonify({"error": "Aula não encontrada."}), 404
    return jsonify(saved)


@bp.route("/lessons/<int:lesson_id>/mapping", methods=["PATCH"])
@require_lessons_access
@require_curator
def update_lesson_mapping(lesson_id: int):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Payload JSON inválido."}), 400

    db = get_db()
    row = db.execute("SELECT id, area, subtema, is_essential FROM lessons WHERE id = ? AND active = 1", (lesson_id,)).fetchone()
    if not row:
        return jsonify({"error": "Aula não encontrada."}), 404

    next_subtema = row["subtema"]
    next_area = row["area"]
    if "subtema" in payload:
        raw_sub = payload["subtema"]
        if raw_sub is None or raw_sub == "":
            next_subtema = None
        elif isinstance(raw_sub, str):
            canonical_area = find_area_for_subtema(raw_sub.strip())
            if not canonical_area:
                return jsonify({"error": "Subtema não encontrado no catálogo canônico."}), 400
            next_subtema = raw_sub.strip()
            next_area = canonical_area
        else:
            return jsonify({"error": "subtema deve ser string ou null."}), 400

    next_essential = int(row["is_essential"])
    if "is_essential" in payload:
        if type(payload["is_essential"]) is not bool:
            return jsonify({"error": "is_essential deve ser booleano."}), 400
        next_essential = int(payload["is_essential"])

    now = _now_iso()
    with db_transaction(db):
        db.execute(
            "UPDATE lessons SET subtema = ?, area = ?, is_essential = ?, mapping_source = 'manual', updated_at = ? WHERE id = ?",
            (next_subtema, next_area, next_essential, now, lesson_id),
        )

    return jsonify({
        "lesson_id": lesson_id,
        "area": next_area,
        "subtema": next_subtema,
        "is_essential": bool(next_essential),
        "mapping_source": "manual",
        "updated_at": now,
    })


@bp.route("/lessons/cycle", methods=["GET"])
@require_lessons_access
def get_lesson_cycle():
    db = get_db()
    user_id = str(g.user_id)
    subtema = (request.args.get("subtema") or "").strip() or None
    settings = get_user_cycle_settings(db, user_id)
    cycles = get_user_cycles_map(db, user_id, settings, subtema=subtema)
    return jsonify({"settings": settings, "cycles": cycles})


@bp.route("/lessons/cycle/settings", methods=["PUT"])
@require_lessons_access
def update_lesson_cycle_settings():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Payload JSON inválido."}), 400

    db = get_db()
    user_id = str(g.user_id)
    current = get_user_cycle_settings(db, user_id)

    pre_q = current["default_pre_questions"]
    post_q = current["default_post_questions"]

    if "default_pre_questions" in payload and payload["default_pre_questions"] is not None:
        raw_pre = payload["default_pre_questions"]
        if type(raw_pre) is not int or raw_pre < 0 or raw_pre > MAX_CYCLE_PRE_QUESTIONS:
            return jsonify({"error": f"default_pre_questions deve ser inteiro entre 0 e {MAX_CYCLE_PRE_QUESTIONS}."}), 400
        pre_q = raw_pre

    if "default_post_questions" in payload and payload["default_post_questions"] is not None:
        raw_post = payload["default_post_questions"]
        if type(raw_post) is not int or raw_post < 1 or raw_post > MAX_CYCLE_POST_QUESTIONS:
            return jsonify({"error": f"default_post_questions deve ser inteiro entre 1 e {MAX_CYCLE_POST_QUESTIONS}."}), 400
        post_q = raw_post

    now = _now_iso()
    with db_transaction(db, immediate=True):
        db.execute(
            """
            INSERT INTO lesson_cycle_settings (user_id, default_pre_questions, default_post_questions, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                default_pre_questions = excluded.default_pre_questions,
                default_post_questions = excluded.default_post_questions,
                updated_at = excluded.updated_at
            """,
            (user_id, pre_q, post_q, now),
        )

    return jsonify({
        "default_pre_questions": pre_q,
        "default_post_questions": post_q,
        "updated_at": now,
    })


@bp.route("/lessons/cycle", methods=["PUT"])
@require_lessons_access
def upsert_lesson_cycle():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Payload JSON inválido."}), 400

    subtema = (payload.get("subtema") or "").strip() if isinstance(payload.get("subtema"), str) else ""
    if not subtema or not find_area_for_subtema(subtema):
        return jsonify({"error": "Subtema inválido ou não encontrado no catálogo canônico."}), 400

    phase = payload.get("phase")
    if phase not in VALID_CYCLE_PHASES:
        return jsonify({"error": "phase deve ser 'pre' ou 'post'."}), 400

    max_target = MAX_CYCLE_PRE_QUESTIONS if phase == "pre" else MAX_CYCLE_POST_QUESTIONS
    min_target = 0 if phase == "pre" else 1

    raw_target = payload.get("target")
    if raw_target is not None:
        if type(raw_target) is not int or raw_target < min_target or raw_target > max_target:
            return jsonify({"error": f"target inválido para fase {phase}."}), 400

    raw_completed = payload.get("completed")
    if raw_completed is not None:
        if type(raw_completed) is not int or raw_completed < 0 or raw_completed > 500:
            return jsonify({"error": "completed deve ser inteiro entre 0 e 500."}), 400

    raw_correct = payload.get("correct")
    if raw_correct is not None:
        if type(raw_correct) is not int or raw_correct < 0 or raw_correct > 500:
            return jsonify({"error": "correct deve ser inteiro entre 0 e 500."}), 400

    raw_done = payload.get("done")
    if raw_done is not None and type(raw_done) is not bool:
        return jsonify({"error": "done deve ser booleano."}), 400

    res = upsert_cycle_entry(
        get_db(),
        str(g.user_id),
        subtema=subtema,
        phase=phase,
        raw_target=raw_target,
        raw_completed=raw_completed,
        raw_correct=raw_correct,
        raw_done=raw_done,
    )
    return jsonify(res)


__all__ = [
    "DEFAULT_CYCLE_POST_QUESTIONS",
    "DEFAULT_CYCLE_PRE_QUESTIONS",
    "_catalog_svc",
    "bp",
    "_build_stream_url",
    "_get_drive_access_token",
    "_resolve_drive_oauth_credentials",
]
