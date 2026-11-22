"""Rotas privadas para videoteca do Google Drive integrada aos 170 subtemas."""
from __future__ import annotations

import unicodedata
from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request

from .auth import require_lessons_access
from .db import db_transaction, get_db
from .services.taxonomy import find_area_for_subtema
from .timezones import DEFAULT_TZ

bp = Blueprint("lessons", __name__)

VALID_STATUSES = ("not_started", "in_progress", "completed")
MAX_BOOKMARK_SECONDS = 86400
MAX_NOTES_LEN = 10000


@bp.after_request
def _add_private_no_store_headers(response):
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm_text(value: str | None) -> str:
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFD", str(value))
    without_accents = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return " ".join(without_accents.lower().split())


def _extract_progress_fields(row) -> tuple[str, int, str, str | None, str | None]:
    keys = row.keys() if hasattr(row, "keys") else []
    status = row["progress_status"] if "progress_status" in keys and row["progress_status"] else "not_started"
    bookmark = row["bookmark_seconds"] if "bookmark_seconds" in keys and row["bookmark_seconds"] is not None else 0
    notes = row["notes"] if "notes" in keys and row["notes"] is not None else ""
    completed_at = row["completed_at"] if "completed_at" in keys else None
    progress_updated_at = row["progress_updated_at"] if "progress_updated_at" in keys else None
    return status, int(bookmark or 0), notes, completed_at, progress_updated_at


def _serialize_lesson(row) -> dict:
    drive_file_id = row["drive_file_id"]
    status, bookmark, notes, completed_at, progress_updated_at = _extract_progress_fields(row)

    return {
        "id": row["id"],
        "course_key": row["course_key"],
        "course_name": row["course_name"],
        "is_extra": bool(row["is_extra"]),
        "area": row["area"],
        "specialty": row["specialty"] or "",
        "subtema": row["subtema"],
        "module_name": row["module_name"],
        "module_order": int(row["module_order"] or 0),
        "title": row["title"],
        "lesson_order": int(row["lesson_order"] or 0),
        "lesson_kind": row["lesson_kind"] or "aula",
        "is_essential": bool(row["is_essential"]),
        "media_type": row["media_type"] or "video",
        "provider": row["provider"] or "gdrive",
        "drive_file_id": drive_file_id,
        "drive_path": row["drive_path"],
        "size_bytes": int(row["size_bytes"] or 0),
        "duration_seconds": row["duration_seconds"],
        "preview_url": f"https://drive.google.com/file/d/{drive_file_id}/preview",
        "open_url": f"https://drive.google.com/file/d/{drive_file_id}/view",
        "progress": {
            "status": status,
            "bookmark_seconds": bookmark,
            "notes": notes,
            "has_notes": bool(notes.strip()),
            "completed_at": completed_at,
            "updated_at": progress_updated_at,
        },
    }


def _serialize_lesson_list_item(row) -> dict:
    """Versão enxuta para listagem (reduz payload omitindo URLs deriváveis, path e texto de notas)."""
    status, bookmark, notes, completed_at, progress_updated_at = _extract_progress_fields(row)

    return {
        "id": row["id"],
        "course_key": row["course_key"],
        "course_name": row["course_name"],
        "is_extra": bool(row["is_extra"]),
        "area": row["area"],
        "specialty": row["specialty"] or "",
        "subtema": row["subtema"],
        "module_name": row["module_name"],
        "module_order": int(row["module_order"] or 0),
        "title": row["title"],
        "lesson_order": int(row["lesson_order"] or 0),
        "lesson_kind": row["lesson_kind"] or "aula",
        "is_essential": bool(row["is_essential"]),
        "drive_file_id": row["drive_file_id"],
        "duration_seconds": row["duration_seconds"],
        "progress": {
            "status": status,
            "bookmark_seconds": bookmark,
            "has_notes": bool(notes.strip()),
            "completed_at": completed_at,
            "updated_at": progress_updated_at,
        },
    }


def _sync_theme_theory_if_completed(db, user_id: str, subtema: str) -> bool:
    """Marca theory_completed=1 quando todas as aulas primárias essenciais do subtema forem concluídas."""
    if not subtema or not find_area_for_subtema(subtema):
        return False

    row = db.execute(
        """
        SELECT
            COUNT(*) AS total_essential,
            SUM(CASE WHEN COALESCE(lp.status, 'not_started') = 'completed' THEN 1 ELSE 0 END) AS completed_essential
        FROM lessons l
        LEFT JOIN lesson_progress lp ON lp.lesson_id = l.id AND lp.user_id = ?
        WHERE l.subtema = ? AND l.active = 1 AND l.is_extra = 0 AND l.is_essential = 1
        """,
        (user_id, subtema),
    ).fetchone()

    total = int(row["total_essential"] or 0) if row else 0
    completed = int(row["completed_essential"] or 0) if row else 0
    if total <= 0 or completed < total:
        return False

    now = _now_iso()
    db.execute(
        """
        INSERT INTO theme_progress (user_id, subtema, theory_completed, study_path, updated_at)
        VALUES (?, ?, 1, 'essential', ?)
        ON CONFLICT(user_id, subtema) DO UPDATE SET
            theory_completed = 1,
            updated_at = excluded.updated_at
        """,
        (user_id, subtema, now),
    )
    return True


_BASE_LESSON_SELECT = """
    SELECT
        l.*,
        lp.status AS progress_status,
        lp.bookmark_seconds AS bookmark_seconds,
        lp.notes AS notes,
        lp.completed_at AS completed_at,
        lp.updated_at AS progress_updated_at
    FROM lessons l
    LEFT JOIN lesson_progress lp ON lp.lesson_id = l.id AND lp.user_id = ?
"""

_LIST_LESSON_SELECT = """
    SELECT
        l.id, l.course_key, l.course_name, l.is_extra, l.area, l.specialty,
        l.subtema, l.module_name, l.module_order, l.title, l.lesson_order,
        l.lesson_kind, l.is_essential, l.drive_file_id, l.duration_seconds,
        lp.status AS progress_status,
        lp.bookmark_seconds AS bookmark_seconds,
        (CASE WHEN lp.notes IS NOT NULL AND lp.notes != '' THEN '1' ELSE '' END) AS notes,
        lp.completed_at AS completed_at,
        lp.updated_at AS progress_updated_at
    FROM lessons l
    LEFT JOIN lesson_progress lp ON lp.lesson_id = l.id AND lp.user_id = ?
"""


@bp.route("/lessons", methods=["GET"])
@require_lessons_access
def list_lessons():
    db = get_db()
    user_id = str(g.user_id)

    course = (request.args.get("course") or "all").strip()
    area = (request.args.get("area") or "").strip()
    subtema = (request.args.get("subtema") or "").strip()
    q = (request.args.get("q") or "").strip()
    status_filter = (request.args.get("status") or "all").strip()
    essential_only = (request.args.get("essential_only") or "").strip().lower() in ("1", "true", "yes")

    where = ["l.active = 1"]
    params: list = [user_id]

    if course and course != "all":
        where.append("l.course_key = ?")
        params.append(course)
    if area:
        where.append("l.area = ?")
        params.append(area)
    if subtema:
        where.append("l.subtema = ?")
        params.append(subtema)
    if essential_only:
        where.append("l.is_essential = 1")

    sql = (
        _LIST_LESSON_SELECT
        + " WHERE "
        + " AND ".join(where)
        + " ORDER BY l.is_extra ASC, l.module_order ASC, l.module_name ASC, l.lesson_order ASC, l.id ASC"
    )
    rows = db.execute(sql, tuple(params)).fetchall()

    q_norm = _norm_text(q)
    lessons_out: list[dict] = []
    areas_set: set[str] = set()
    by_course_map: dict[str, dict] = {}
    counts = {
        "total": 0,
        "completed": 0,
        "in_progress": 0,
        "not_started": 0,
        "total_duration_seconds": 0,
        "remaining_duration_seconds": 0,
    }

    for row in rows:
        item = _serialize_lesson_list_item(row)
        item_status = item["progress"]["status"]

        if q_norm:
            haystack = _norm_text(
                f"{item['title']} {item['module_name']} {item['subtema'] or ''} {item['specialty']} {item['area']}"
            )
            if q_norm not in haystack:
                continue

        if status_filter == "pending":
            if item_status == "completed":
                continue
        elif status_filter in VALID_STATUSES:
            if item_status != status_filter:
                continue

        lessons_out.append(item)
        if item["area"]:
            areas_set.add(item["area"])

        dur = int(item["duration_seconds"] or 0)
        counts["total"] += 1
        counts[item_status] = counts.get(item_status, 0) + 1
        counts["total_duration_seconds"] += dur
        if item_status != "completed":
            counts["remaining_duration_seconds"] += dur

        ckey = item["course_key"]
        if ckey not in by_course_map:
            by_course_map[ckey] = {
                "course_key": ckey,
                "course_name": item["course_name"],
                "is_extra": item["is_extra"],
                "total": 0,
                "completed": 0,
                "in_progress": 0,
            }
        by_course_map[ckey]["total"] += 1
        if item_status == "completed":
            by_course_map[ckey]["completed"] += 1
        elif item_status == "in_progress":
            by_course_map[ckey]["in_progress"] += 1

    return jsonify({
        "lessons": lessons_out,
        "summary": {
            **counts,
            "by_course": sorted(by_course_map.values(), key=lambda c: (c["is_extra"], c["course_name"])),
            "areas": sorted(areas_set),
        },
    })


def _parse_start_date_local(raw: str):
    cleaned = (raw or "").strip()
    if not cleaned:
        raise ValueError("empty start_date")
    if len(cleaned) == 10 and cleaned[4] == "-" and cleaned[7] == "-":
        return datetime.strptime(cleaned, "%Y-%m-%d").date()
    dt = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    if dt.tzinfo is not None:
        return dt.astimezone(DEFAULT_TZ).date()
    return dt.date()


def _get_current_planner_week_subtemas(
    db, user_id: str, requested_mode: str | None = None
) -> tuple[int | None, list[str]]:
    """Retorna (semana_atual, [subtemas]) no fuso America/Sao_Paulo, sem avançar para semanas futuras."""
    try:
        cfg = db.execute(
            "SELECT * FROM planner_config WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    except Exception:
        return None, []
    if not cfg:
        return None, []

    cfg_keys = cfg.keys() if hasattr(cfg, "keys") else []
    start_raw = str(cfg["start_date"] or "") if "start_date" in cfg_keys else ""
    try:
        start_dt = _parse_start_date_local(start_raw)
        today_dt = datetime.now(DEFAULT_TZ).date()
        week_num = max(1, (today_dt - start_dt).days // 7 + 1)
    except ValueError:
        week_num = 1

    org_raw = cfg["organization_mode"] if "organization_mode" in cfg_keys else "geral"
    org = "internato" if org_raw == "internato" else "geral"

    valid_modes = {"geral_standard", "geral_intensive", "internato_standard", "internato_intensive"}
    active_mode = requested_mode if requested_mode in valid_modes else f"{org}_standard"

    try:
        rows = db.execute(
            """
            SELECT subtema FROM planner_schedule
            WHERE user_id = ? AND mode = ? AND week = ?
            ORDER BY display_order ASC
            """,
            (user_id, active_mode, week_num),
        ).fetchall()

        if not rows and requested_mode not in valid_modes:
            # Fallback determinístico para o modo mais recentemente criado dentro da mesma organização
            fallback_mode_row = db.execute(
                """
                SELECT mode FROM planner_schedule
                WHERE user_id = ? AND mode LIKE ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (user_id, f"{org}_%"),
            ).fetchone()
            if not fallback_mode_row:
                fallback_mode_row = db.execute(
                    """
                    SELECT mode FROM planner_schedule
                    WHERE user_id = ?
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (user_id,),
                ).fetchone()
            if fallback_mode_row and fallback_mode_row["mode"] != active_mode:
                rows = db.execute(
                    """
                    SELECT subtema FROM planner_schedule
                    WHERE user_id = ? AND mode = ? AND week = ?
                    ORDER BY display_order ASC
                    """,
                    (user_id, fallback_mode_row["mode"], week_num),
                ).fetchall()
    except Exception:
        return week_num, []

    return week_num, [r["subtema"] for r in rows if r["subtema"]]


@bp.route("/lessons/summary-by-subtema", methods=["GET"])
@require_lessons_access
def lessons_summary_by_subtema():
    db = get_db()
    user_id = str(g.user_id)
    rows = db.execute(
        """
        SELECT
            l.id,
            l.course_key,
            l.subtema,
            l.is_extra,
            l.is_essential,
            l.duration_seconds,
            COALESCE(lp.status, 'not_started') AS progress_status
        FROM lessons l
        LEFT JOIN lesson_progress lp ON lp.lesson_id = l.id AND lp.user_id = ?
        WHERE l.active = 1 AND l.subtema IS NOT NULL AND l.subtema != ''
        ORDER BY l.is_extra ASC, l.is_essential DESC, l.module_order ASC, l.lesson_order ASC, l.id ASC
        """,
        (user_id,),
    ).fetchall()

    theme_rows = db.execute(
        "SELECT subtema, theory_completed FROM theme_progress WHERE user_id = ?",
        (user_id,),
    ).fetchall()
    theme_completed_map = {r["subtema"]: bool(r["theory_completed"]) for r in theme_rows}

    subtemas: dict[str, dict] = {}
    fallback_next_any_main: dict[str, int] = {}
    fallback_next_non_extra: dict[str, int] = {}
    fallback_next_any: dict[str, int] = {}

    for row in rows:
        sub = row["subtema"]
        entry = subtemas.setdefault(sub, {
            "total": 0,
            "completed": 0,
            "essential_total": 0,
            "essential_completed": 0,
            "medway_optional_total": 0,
            "medway_optional_completed": 0,
            "extra_total": 0,
            "extra_completed": 0,
            "total_duration_seconds": 0,
            "remaining_duration_seconds": 0,
            "theory_completed": bool(theme_completed_map.get(sub, False)),
            "essential_all_completed": False,
            "next_lesson_id": None,
        })
        is_completed = row["progress_status"] == "completed"
        is_extra = bool(row["is_extra"])
        is_essential = bool(row["is_essential"])
        is_medway = row["course_key"] == "medway_r1_2026"
        is_medway_main = is_medway and is_essential
        is_medway_optional = is_medway and not is_essential
        dur = int(row["duration_seconds"] or 0)

        entry["total"] += 1
        if is_completed:
            entry["completed"] += 1

        if sub not in fallback_next_any:
            fallback_next_any[sub] = row["id"]
        if not is_extra and sub not in fallback_next_non_extra:
            fallback_next_non_extra[sub] = row["id"]

        if is_medway_main:
            if sub not in fallback_next_any_main:
                fallback_next_any_main[sub] = row["id"]
            if not is_completed and entry["next_lesson_id"] is None:
                entry["next_lesson_id"] = row["id"]
            entry["essential_total"] += 1
            entry["total_duration_seconds"] += dur
            if is_completed:
                entry["essential_completed"] += 1
            else:
                entry["remaining_duration_seconds"] += dur
        elif is_medway_optional:
            entry["medway_optional_total"] += 1
            if is_completed:
                entry["medway_optional_completed"] += 1
        elif is_extra:
            entry["extra_total"] += 1
            if is_completed:
                entry["extra_completed"] += 1

    for sub, entry in subtemas.items():
        entry["essential_all_completed"] = bool(
            entry["essential_total"] > 0 and entry["essential_completed"] >= entry["essential_total"]
        )
        if entry["next_lesson_id"] is None:
            entry["next_lesson_id"] = (
                fallback_next_any_main.get(sub)
                or fallback_next_non_extra.get(sub)
                or fallback_next_any.get(sub)
            )

    return jsonify({"subtemas": subtemas})


@bp.route("/lessons/current-week", methods=["GET"])
@require_lessons_access
def lessons_current_week():
    db = get_db()
    requested_mode = (request.args.get("mode") or "").strip() or None
    week_num, subtemas = _get_current_planner_week_subtemas(db, str(g.user_id), requested_mode=requested_mode)
    return jsonify({"week": week_num, "subtemas": subtemas})


@bp.route("/lessons/continue", methods=["GET"])
@require_lessons_access
def lessons_continue():
    db = get_db()
    user_id = str(g.user_id)

    stats_row = db.execute(
        """
        SELECT
            COUNT(*) AS primary_total,
            SUM(CASE WHEN COALESCE(lp.status, 'not_started') = 'completed' THEN 1 ELSE 0 END) AS primary_completed,
            SUM(CASE WHEN COALESCE(lp.status, 'not_started') != 'completed' THEN COALESCE(l.duration_seconds, 0) ELSE 0 END) AS primary_remaining_seconds
        FROM lessons l
        LEFT JOIN lesson_progress lp ON lp.lesson_id = l.id AND lp.user_id = ?
        WHERE l.active = 1 AND l.course_key = 'medway_r1_2026' AND l.is_essential = 1
        """,
        (user_id,),
    ).fetchone()
    stats = {
        "primary_total": int(stats_row["primary_total"] or 0) if stats_row else 0,
        "primary_completed": int(stats_row["primary_completed"] or 0) if stats_row else 0,
        "primary_remaining_seconds": int(stats_row["primary_remaining_seconds"] or 0) if stats_row else 0,
    }

    # 1. Prioridade: última aula em andamento
    in_prog_row = db.execute(
        _BASE_LESSON_SELECT
        + " WHERE l.active = 1 AND lp.status = 'in_progress'"
        + " ORDER BY lp.updated_at DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    if in_prog_row:
        return jsonify({
            "lesson": _serialize_lesson(in_prog_row),
            "reason": "in_progress",
            "planner_week": None,
            "stats": stats,
        })

    # 2. Segunda prioridade: primeira aula essencial pendente da semana atual do Planner
    week_num, week_subtemas = _get_current_planner_week_subtemas(db, user_id)
    if week_subtemas:
        placeholders = ",".join("?" for _ in week_subtemas)
        planner_row = db.execute(
            _BASE_LESSON_SELECT
            + f" WHERE l.active = 1 AND l.is_extra = 0 AND l.is_essential = 1 AND l.subtema IN ({placeholders})"
            + " AND COALESCE(lp.status, 'not_started') != 'completed'"
            + " ORDER BY l.module_order ASC, l.lesson_order ASC, l.id ASC LIMIT 1",
            (user_id, *week_subtemas),
        ).fetchone()
        if planner_row:
            return jsonify({
                "lesson": _serialize_lesson(planner_row),
                "reason": "planner_week",
                "planner_week": week_num,
                "stats": stats,
            })

    # 3. Fallback: primeira aula essencial pendente do Extensivo R1
    next_row = db.execute(
        _BASE_LESSON_SELECT
        + " WHERE l.active = 1 AND l.is_extra = 0 AND l.is_essential = 1"
        + " AND COALESCE(lp.status, 'not_started') != 'completed'"
        + " ORDER BY l.module_order ASC, l.lesson_order ASC, l.id ASC LIMIT 1",
        (user_id,),
    ).fetchone()
    if next_row:
        return jsonify({
            "lesson": _serialize_lesson(next_row),
            "reason": "next_pending",
            "planner_week": week_num,
            "stats": stats,
        })

    return jsonify({"lesson": None, "reason": None, "planner_week": week_num, "stats": stats})


@bp.route("/lessons/by-subtema", methods=["GET"])
@require_lessons_access
def lessons_by_subtema():
    subtema = (request.args.get("subtema") or "").strip()
    if not subtema:
        return jsonify({"error": "Parâmetro 'subtema' é obrigatório."}), 400

    db = get_db()
    user_id = str(g.user_id)
    rows = db.execute(
        _BASE_LESSON_SELECT
        + " WHERE l.active = 1 AND l.subtema = ?"
        + " ORDER BY l.is_extra ASC, l.is_essential DESC, l.module_order ASC, l.lesson_order ASC, l.id ASC",
        (user_id, subtema),
    ).fetchall()

    primary: list[dict] = []
    extras: list[dict] = []
    progress = {
        "total": 0,
        "completed": 0,
        "essential_total": 0,
        "essential_completed": 0,
        "extra_total": 0,
        "extra_completed": 0,
    }

    for row in rows:
        item = _serialize_lesson(row)
        is_completed = item["progress"]["status"] == "completed"
        progress["total"] += 1
        if is_completed:
            progress["completed"] += 1

        if item["is_extra"]:
            extras.append(item)
            progress["extra_total"] += 1
            if is_completed:
                progress["extra_completed"] += 1
        else:
            primary.append(item)
            if item["is_essential"]:
                progress["essential_total"] += 1
                if is_completed:
                    progress["essential_completed"] += 1

    return jsonify({
        "subtema": subtema,
        "primary": primary,
        "extras": extras,
        "progress": progress,
    })


@bp.route("/lessons/<int:lesson_id>", methods=["GET"])
@require_lessons_access
def get_lesson_detail(lesson_id: int):
    db = get_db()
    user_id = str(g.user_id)
    row = db.execute(
        _BASE_LESSON_SELECT + " WHERE l.id = ? AND l.active = 1",
        (user_id, lesson_id),
    ).fetchone()
    if not row:
        return jsonify({"error": "Aula não encontrada."}), 404

    lesson = _serialize_lesson(row)
    if lesson["subtema"]:
        sibling_rows = db.execute(
            _BASE_LESSON_SELECT
            + " WHERE l.active = 1 AND l.subtema = ?"
            + " ORDER BY l.is_extra ASC, l.is_essential DESC, l.module_order ASC, l.lesson_order ASC, l.id ASC",
            (user_id, lesson["subtema"]),
        ).fetchall()
    else:
        sibling_rows = db.execute(
            _BASE_LESSON_SELECT
            + " WHERE l.active = 1 AND l.course_key = ? AND l.module_name = ?"
            + " ORDER BY l.module_order ASC, l.lesson_order ASC, l.id ASC",
            (user_id, lesson["course_key"], lesson["module_name"]),
        ).fetchall()

    playlist = [_serialize_lesson(r) for r in sibling_rows]
    return jsonify({"lesson": lesson, "playlist": playlist})


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

    db = get_db()
    user_id = str(g.user_id)
    now = _now_iso()
    theme_theory_completed = False

    with db_transaction(db, immediate=True):
        lesson_row = db.execute(
            "SELECT id, subtema, is_extra FROM lessons WHERE id = ? AND active = 1",
            (lesson_id,),
        ).fetchone()
        if not lesson_row:
            return jsonify({"error": "Aula não encontrada."}), 404

        existing = db.execute(
            "SELECT status, bookmark_seconds, notes, completed_at FROM lesson_progress WHERE user_id = ? AND lesson_id = ?",
            (user_id, lesson_id),
        ).fetchone()
        prev_status = existing["status"] if existing else "not_started"

        if "status" in payload and payload["status"] is not None:
            status = payload["status"]
        else:
            status = prev_status

        if "bookmark_seconds" in payload and payload["bookmark_seconds"] is not None:
            bookmark_seconds = payload["bookmark_seconds"]
        else:
            bookmark_seconds = int(existing["bookmark_seconds"] or 0) if existing else 0

        if "notes" in payload and payload["notes"] is not None:
            notes = payload["notes"][:MAX_NOTES_LEN]
        else:
            notes = existing["notes"] if existing else ""

        if status == "completed":
            completed_at = (existing["completed_at"] if existing and existing["completed_at"] else None) or now
        else:
            completed_at = None

        db.execute(
            """
            INSERT INTO lesson_progress (user_id, lesson_id, status, bookmark_seconds, notes, completed_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, lesson_id) DO UPDATE SET
                status = excluded.status,
                bookmark_seconds = excluded.bookmark_seconds,
                notes = excluded.notes,
                completed_at = excluded.completed_at,
                updated_at = excluded.updated_at
            """,
            (user_id, lesson_id, status, bookmark_seconds, notes, completed_at, now),
        )

        if (
            sync_theme_theory
            and prev_status != "completed"
            and status == "completed"
            and lesson_row["subtema"]
            and not bool(lesson_row["is_extra"])
        ):
            theme_theory_completed = _sync_theme_theory_if_completed(db, user_id, lesson_row["subtema"])

    return jsonify({
        "lesson_id": lesson_id,
        "status": status,
        "bookmark_seconds": bookmark_seconds,
        "notes": notes,
        "has_notes": bool(notes.strip()),
        "completed_at": completed_at,
        "updated_at": now,
        "theme_theory_completed": theme_theory_completed,
    })


@bp.route("/lessons/<int:lesson_id>/mapping", methods=["PATCH"])
@require_lessons_access
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
