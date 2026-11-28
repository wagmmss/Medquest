"""Blueprint HTTP do Planejador de Estudos, Blocos do Internato e Calendário ICS."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from flask import Blueprint, Response, g, jsonify, request

from .adaptive import get_adaptive_signals_by_topic
from .db import db_transaction, get_db
from .observability import record_domain_event
from .questions import invalidate_user_caches
from .schemas import (
    GeneratePlanIn,
    InternatoBlocksUpdateIn,
    PlannerConfigIn,
    PlannerMoveTopicIn,
    PlannerResetIn,
    PlannerRevisionIn,
    PlannerStudyIn,
    PlannerTopicProgressIn,
    ValidationError,
    validation_errors,
)
from .services.planner_ics import _generate_calendar_ics_content
from .services.planner_scheduler import build_plan_from_schedule, generate_annual_plan
from .services.planner_store import (
    _fetch_plan_data,
    _get_completed_subtemas,
    _get_planner_config,
    _get_user_internato_blocks,
    _parse_mode_parts,
    _resolve_schedule_mode,
    get_planner_config_data,
    get_planner_progress_data,
    get_planner_topic_progress_data,
)

bp = Blueprint("plan", __name__)


@bp.route("/planner/config/reset", methods=["POST"])
def planner_config_reset():
    raw_body = request.get_json(silent=True) or {}
    try:
        data = PlannerResetIn.model_validate(raw_body)
    except ValidationError as e:
        return jsonify({"error": "invalid input", "details": validation_errors(e)}), 400

    db = get_db()
    with db_transaction(db, immediate=True):
        if data.scope == "schedule":
            if data.mode:
                db.execute("DELETE FROM planner_schedule WHERE user_id = ? AND mode = ?", (g.user_id, data.mode))
            else:
                db.execute("DELETE FROM planner_schedule WHERE user_id = ?", (g.user_id,))
        elif data.scope == "progress":
            db.execute("DELETE FROM planner_progress WHERE user_id = ?", (g.user_id,))
            db.execute("DELETE FROM planner_topic_progress WHERE user_id = ?", (g.user_id,))
            db.execute("DELETE FROM planner_schedule WHERE user_id = ?", (g.user_id,))
        else:
            db.execute("DELETE FROM planner_config WHERE user_id = ?", (g.user_id,))
            db.execute("DELETE FROM planner_progress WHERE user_id = ?", (g.user_id,))
            db.execute("DELETE FROM planner_topic_progress WHERE user_id = ?", (g.user_id,))
            db.execute("DELETE FROM planner_schedule WHERE user_id = ?", (g.user_id,))
    invalidate_user_caches(g.user_id)
    return jsonify({"success": True, "scope": data.scope})


def _blocks_schedule_signature(blocks: list[dict]) -> list[tuple]:
    return sorted(
        (
            str(b.get("start") or ""),
            str(b.get("end") or ""),
            str(b.get("area") or ""),
            float(b["hours_per_week"]) if b.get("hours_per_week") is not None else None,
        )
        for b in blocks
    )


@bp.route("/planner/internato-blocks", methods=["PUT", "POST"])
def planner_internato_blocks():
    try:
        data = InternatoBlocksUpdateIn.model_validate(request.get_json(force=True) or {})
    except ValidationError as e:
        return jsonify({"error": "invalid input", "details": validation_errors(e)}), 400

    blocks_payload = [b.model_dump(exclude_none=True) for b in data.blocks]
    blocks_json = json.dumps(blocks_payload, ensure_ascii=False)
    now_iso = datetime.now(timezone.utc).isoformat()
    db = get_db()
    with db_transaction(db, immediate=True):
        existing = db.execute(
            "SELECT user_id, internato_blocks FROM planner_config WHERE user_id = ?",
            (g.user_id,),
        ).fetchone()
        prev_blocks = _get_user_internato_blocks(db, g.user_id, config_row=existing) if existing else []
        schedule_changed = _blocks_schedule_signature(prev_blocks) != _blocks_schedule_signature(blocks_payload)

        if existing:
            db.execute(
                "UPDATE planner_config SET internato_blocks = ?, updated_at = ? WHERE user_id = ?",
                (blocks_json, now_iso, g.user_id),
            )
        else:
            db.execute(
                "INSERT INTO planner_config (user_id, internato_blocks, updated_at) VALUES (?, ?, ?)",
                (g.user_id, blocks_json, now_iso),
            )
        if schedule_changed:
            db.execute(
                "DELETE FROM planner_schedule WHERE user_id = ? AND mode LIKE 'internato_%'",
                (g.user_id,),
            )
    invalidate_user_caches(g.user_id)
    return jsonify({"success": True, "internato_blocks": blocks_payload})


@bp.route("/planner/config", methods=["GET", "POST"])
def planner_config():
    db = get_db()
    if request.method == "POST":
        try:
            cfg = PlannerConfigIn.model_validate(request.get_json(force=True) or {})
        except ValidationError as e:
            return jsonify({"error": "invalid input", "details": validation_errors(e)}), 400
        
        target_inst = cfg.target_institution
        if not target_inst and cfg.target_institutions:
            target_inst = ", ".join(cfg.target_institutions)

        existing_row = db.execute("SELECT * FROM planner_config WHERE user_id = ?", (g.user_id,)).fetchone()
        existing_keys = existing_row.keys() if existing_row and hasattr(existing_row, "keys") else []
        org_mode = cfg.organization_mode or (
            existing_row["organization_mode"] if existing_row and "organization_mode" in existing_keys and existing_row["organization_mode"] else "geral"
        )
        existing_blocks_json = (
            existing_row["internato_blocks"] if existing_row and "internato_blocks" in existing_keys else None
        )
        blocks_json = (
            json.dumps([b.model_dump(exclude_none=True) for b in cfg.internato_blocks], ensure_ascii=False)
            if cfg.internato_blocks is not None
            else existing_blocks_json
        )

        # Só limpa planner_schedule se parâmetros estruturais de tempo/data, bancas ou blocos realmente mudarem
        existing_inst = (
            existing_row["target_institution"]
            if existing_row and "target_institution" in existing_keys
            else None
        )
        inst_changed = (existing_inst or "").strip() != (target_inst or "").strip()
        timing_changed = (
            not existing_row
            or existing_row["exam_date"] != cfg.exam_date
            or existing_row["start_date"] != cfg.start_date
            or existing_row["days_per_week"] != cfg.days_per_week
            or (existing_row["hours_per_day"] if "hours_per_day" in existing_keys else None) != cfg.hours_per_day
        )
        blocks_changed = cfg.internato_blocks is not None and blocks_json != existing_blocks_json

        with db_transaction(db, immediate=True):
            if timing_changed or inst_changed:
                db.execute("DELETE FROM planner_schedule WHERE user_id = ?", (g.user_id,))
            elif blocks_changed:
                db.execute("DELETE FROM planner_schedule WHERE user_id = ? AND mode LIKE 'internato_%'", (g.user_id,))

            db.execute("""
                INSERT INTO planner_config (
                    user_id, exam_date, start_date, days_per_week, questions_per_day,
                    hours_per_day, updated_at, target_score, target_institution,
                    target_specialty, organization_mode, internato_blocks
                )
                VALUES (?, ?, ?, ?, 30, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    exam_date = excluded.exam_date, start_date = excluded.start_date,
                    days_per_week = excluded.days_per_week, hours_per_day = excluded.hours_per_day,
                    updated_at = excluded.updated_at, target_score = excluded.target_score,
                    target_institution = excluded.target_institution, target_specialty = excluded.target_specialty,
                    organization_mode = excluded.organization_mode, internato_blocks = excluded.internato_blocks
            """, (
                g.user_id, cfg.exam_date, cfg.start_date, cfg.days_per_week, cfg.hours_per_day,
                datetime.now(timezone.utc).isoformat(), cfg.target_score, target_inst,
                cfg.target_specialty, org_mode, blocks_json,
            ))
        invalidate_user_caches(g.user_id)
        return jsonify({"success": True})

    return jsonify(get_planner_config_data(db, g.user_id) or {})



@bp.route("/planner")
def get_planner():
    db = get_db()
    return jsonify(get_planner_progress_data(db, g.user_id))


@bp.route("/planner/topics")
def get_planner_topics():
    db = get_db()
    return jsonify(get_planner_topic_progress_data(db, g.user_id))


@bp.route("/planner/<int:week>/topic", methods=["POST"])
def planner_topic(week):
    try:
        data = PlannerTopicProgressIn.model_validate(request.get_json(force=True) or {})
    except ValidationError as e:
        return jsonify({"error": "invalid input", "details": validation_errors(e)}), 400
    completed = 1 if data.completed else 0
    completed_at = datetime.now(timezone.utc).isoformat() if completed else None
    db = get_db()
    with db_transaction(db, immediate=True):
        if completed:
            db.execute("""INSERT INTO planner_topic_progress (week, subtema, completed, completed_at, user_id)
                          VALUES (?, ?, ?, ?, ?)
                          ON CONFLICT(week, subtema, user_id) DO UPDATE SET completed = excluded.completed, completed_at = excluded.completed_at""",
                       (week, data.subtema, completed, completed_at, g.user_id))
        else:
            # Desmarcar apaga/desmarca em todas as semanas para manter consistência global entre modos
            db.execute(
                "DELETE FROM planner_topic_progress WHERE user_id = ? AND subtema = ?",
                (g.user_id, data.subtema),
            )
    invalidate_user_caches(g.user_id)
    if completed:
        record_domain_event("planner_topic_completed", user_id=g.user_id, week=week, subtema=data.subtema)
    return jsonify({"success": True, "completed": bool(completed)})


@bp.route("/planner/move-topic", methods=["POST"])
def planner_move_topic():
    try:
        data = PlannerMoveTopicIn.model_validate(request.get_json(force=True) or {})
    except ValidationError as e:
        return jsonify({"error": "invalid input", "details": validation_errors(e)}), 400

    db = get_db()
    schedule_rows = db.execute(
        "SELECT week, subtema, display_order FROM planner_schedule WHERE user_id = ? AND mode = ? ORDER BY week ASC, display_order ASC",
        (g.user_id, data.mode)
    ).fetchall()

    now_iso = datetime.now(timezone.utc).isoformat()

    # Se ainda não houver schedule salvo, popula a partir do plano gerado
    if not schedule_rows:
        start_date, exam_date, days, hours_per_week = _get_planner_config(db, g.user_id)
        rows, answered_map, use_bank_incidence = _fetch_plan_data(db, g.user_id)
        adaptive_signals = get_adaptive_signals_by_topic(db, g.user_id)
        completed_subtemas = _get_completed_subtemas(db, g.user_id)
        internato_blocks = _get_user_internato_blocks(db, g.user_id)
        org_mode, is_intensive = _parse_mode_parts(data.mode)
        plan = generate_annual_plan(
            rows, start_date, exam_date, hours_per_week,
            intensive=is_intensive, user_progress=answered_map,
            adaptive_signals=adaptive_signals,
            organization=org_mode,
            internato_blocks=internato_blocks,
            completed_subtemas=completed_subtemas,
            use_bank_incidence=use_bank_incidence,
        )
        if isinstance(plan, dict) and plan.get("plan"):
            insert_records = []
            for w in plan["plan"]:
                week_num = int(w["week"])
                for order_idx, t in enumerate(w.get("topics", [])):
                    insert_records.append((g.user_id, data.mode, week_num, t["subtema"], order_idx, now_iso))
            if insert_records:
                with db_transaction(db, immediate=True):
                    db.execute("DELETE FROM planner_schedule WHERE user_id = ? AND mode = ?", (g.user_id, data.mode))
                    db.executemany("""
                        INSERT INTO planner_schedule (user_id, mode, week, subtema, display_order, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, insert_records)
            schedule_rows = db.execute(
                "SELECT week, subtema, display_order FROM planner_schedule WHERE user_id = ? AND mode = ? ORDER BY week ASC, display_order ASC",
                (g.user_id, data.mode)
            ).fetchall()

    if not schedule_rows:
        return jsonify({"error": "Cronograma não encontrado"}), 404

    weeks_map = {}
    for r in schedule_rows:
        w_num = int(r["week"])
        weeks_map.setdefault(w_num, []).append(r["subtema"])

    source_week = data.source_week
    target_week = data.target_week
    subtema = data.subtema

    # Se o subtema não estiver exatamente na source_week indicada pelo cliente, procurar onde ele está
    found_week = None
    for w_num, topics in weeks_map.items():
        if subtema in topics:
            found_week = w_num
            break

    if found_week is not None:
        source_week = found_week
        weeks_map[source_week].remove(subtema)
    else:
        return jsonify({"error": f"Subtema '{subtema}' não encontrado no cronograma"}), 404

    if target_week not in weeks_map:
        weeks_map[target_week] = []

    if data.target_index is not None and 0 <= data.target_index <= len(weeks_map[target_week]):
        weeks_map[target_week].insert(data.target_index, subtema)
    else:
        weeks_map[target_week].append(subtema)

    affected_weeks = {source_week, target_week}
    with db_transaction(db, immediate=True):
        placeholders = ",".join("?" * len(affected_weeks))
        db.execute(
            f"DELETE FROM planner_schedule WHERE user_id = ? AND mode = ? AND week IN ({placeholders})",
            (g.user_id, data.mode, *affected_weeks)
        )
        insert_records = []
        for w_num in affected_weeks:
            for order_idx, s in enumerate(weeks_map.get(w_num, [])):
                insert_records.append((g.user_id, data.mode, w_num, s, order_idx, now_iso))
        if insert_records:
            db.executemany("""
                INSERT INTO planner_schedule (user_id, mode, week, subtema, display_order, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, insert_records)

        # Atualizar planner_topic_progress para a nova semana evitando IntegrityError em conflito de PK
        if source_week != target_week:
            db.execute("""
                INSERT INTO planner_topic_progress (week, subtema, completed, completed_at, user_id)
                SELECT ?, subtema, completed, completed_at, user_id
                FROM planner_topic_progress
                WHERE user_id = ? AND subtema = ? AND week = ?
                ON CONFLICT(week, subtema, user_id) DO UPDATE SET
                    completed = MAX(planner_topic_progress.completed, excluded.completed),
                    completed_at = COALESCE(planner_topic_progress.completed_at, excluded.completed_at)
            """, (target_week, g.user_id, subtema, source_week))
            db.execute("""
                DELETE FROM planner_topic_progress
                WHERE user_id = ? AND subtema = ? AND week = ?
            """, (g.user_id, subtema, source_week))

    invalidate_user_caches(g.user_id)
    record_domain_event(
        "planner_topic_moved",
        user_id=g.user_id,
        subtema=subtema,
        source_week=source_week,
        target_week=target_week,
        target_index=data.target_index
    )

    return jsonify({
        "success": True,
        "subtema": subtema,
        "source_week": source_week,
        "target_week": target_week,
        "target_index": data.target_index
    })


@bp.route("/planner/<int:week>/study", methods=["POST"])
def planner_study(week):
    db = get_db()
    try:
        data = PlannerStudyIn.model_validate(request.get_json(force=True) or {})
    except ValidationError as e:
        return jsonify({"error": "invalid input", "details": validation_errors(e)}), 400
    studied = 1 if data.studied else 0
    if studied:
        studied_at = datetime.now(timezone.utc).isoformat()
        with db_transaction(db, immediate=True):
            db.execute("""
                INSERT INTO planner_progress (week, studied, studied_at, rev24h, rev7d, rev30d, user_id)
                VALUES (?, 1, ?, 0, 0, 0, ?)
                ON CONFLICT(week, user_id) DO UPDATE SET studied = 1, studied_at = excluded.studied_at
            """, (week, studied_at, g.user_id))
    else:
        studied_at = None
        with db_transaction(db, immediate=True):
            db.execute("""
                INSERT INTO planner_progress (week, studied, studied_at, rev24h, rev7d, rev30d, user_id)
                VALUES (?, 0, NULL, 0, 0, 0, ?)
                ON CONFLICT(week, user_id) DO UPDATE SET studied = 0, studied_at = NULL, rev24h = 0, rev7d = 0, rev30d = 0
            """, (week, g.user_id))
    invalidate_user_caches(g.user_id)
    return jsonify({"success": True, "studied": bool(studied), "studied_at": studied_at})


@bp.route("/planner/<int:week>/revision", methods=["POST"])
def planner_revision(week):
    db = get_db()
    try:
        data = PlannerRevisionIn.model_validate(request.get_json(force=True) or {})
    except ValidationError as e:
        return jsonify({"error": "invalid input", "details": validation_errors(e)}), 400
        
    allowed_columns = {'rev24h', 'rev7d', 'rev30d'}
    if data.type not in allowed_columns:
        return jsonify({'error': 'invalid type'}), 400
        
    checked = 1 if data.checked else 0
    with db_transaction(db, immediate=True):
        db.execute(f"""
            INSERT INTO planner_progress (week, {data.type}, user_id) VALUES (?, ?, ?)
            ON CONFLICT(week, user_id) DO UPDATE SET {data.type} = excluded.{data.type}
        """, (week, checked, g.user_id))
    invalidate_user_caches(g.user_id)
    return jsonify({"success": True, "type": data.type, "checked": bool(checked)})


@bp.route("/generate_plan", methods=["POST"])
def generate_plan():
    try:
        data = GeneratePlanIn.model_validate(request.get_json(force=True) or {})
    except ValidationError as e:
        return jsonify({"error": "invalid input", "details": validation_errors(e)}), 400
    start_date = data.start_date or datetime.now(timezone.utc).isoformat()
    mode = _resolve_schedule_mode(data.organization, data.intensive)

    db = get_db()
    rows, answered_map, use_bank_incidence = _fetch_plan_data(db, g.user_id)
    adaptive_signals = get_adaptive_signals_by_topic(db, g.user_id)
    completed_subtemas = _get_completed_subtemas(db, g.user_id)
    internato_blocks = _get_user_internato_blocks(db, g.user_id)

    if not data.regenerate:
        schedule_rows = db.execute(
            "SELECT week, subtema, display_order FROM planner_schedule WHERE user_id = ? AND mode = ? ORDER BY week ASC, display_order ASC",
            (g.user_id, mode)
        ).fetchall()
        if schedule_rows:
            plan = build_plan_from_schedule(
                schedule_rows, start_date, data.hours_per_week,
                exam_date_str=data.exam_date,
                rows=rows, user_progress=answered_map,
                adaptive_signals=adaptive_signals, intensive=data.intensive,
                completed_subtemas=completed_subtemas,
                organization=data.organization,
                internato_blocks=internato_blocks,
                use_bank_incidence=use_bank_incidence,
            )
            if plan:
                return jsonify(plan)

    plan = generate_annual_plan(
        rows, start_date, data.exam_date, data.hours_per_week,
        intensive=data.intensive, user_progress=answered_map,
        adaptive_signals=adaptive_signals,
        organization=data.organization,
        internato_blocks=internato_blocks,
        completed_subtemas=completed_subtemas,
        use_bank_incidence=use_bank_incidence,
    )

    if isinstance(plan, dict) and plan.get("plan"):
        now_iso = datetime.now(timezone.utc).isoformat()
        with db_transaction(db, immediate=True):
            db.execute("DELETE FROM planner_schedule WHERE user_id = ? AND mode = ?", (g.user_id, mode))
            insert_records = []
            for w in plan["plan"]:
                week_num = int(w["week"])
                for order_idx, t in enumerate(w.get("topics", [])):
                    insert_records.append((g.user_id, mode, week_num, t["subtema"], order_idx, now_iso))
            if insert_records:
                db.executemany("""
                    INSERT INTO planner_schedule (user_id, mode, week, subtema, display_order, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, insert_records)
        invalidate_user_caches(g.user_id)

    return jsonify(plan)



@bp.route("/planner/export/ics", methods=["GET"])
def export_ics():
    db = get_db()
    content = _generate_calendar_ics_content(db, g.user_id)
    return Response(
        content,
        mimetype="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=medquest_cronograma.ics"
        }
    )


@bp.route("/planner/calendar/feed", methods=["GET"])
def calendar_feed():
    from .rate_limit import check_rate_limit
    from .services.six_year_routine import resolve_feed_token_user

    db = get_db()
    raw_token = request.args.get("token")
    if raw_token is not None:
        rl_resp = check_rate_limit("six_year_ics_feed", auth_limit=30, window_seconds=60, ip_limit=30)
        if rl_resp is not None:
            return rl_resp
        target_user_id = resolve_feed_token_user(db, raw_token)
        if not target_user_id:
            return jsonify({"error": "Not Found"}), 404
    else:
        target_user_id = getattr(g, "user_id", None)
        if not target_user_id:
            return jsonify({"error": "Unauthorized"}), 401

    content = _generate_calendar_ics_content(db, target_user_id)
    return Response(
        content,
        mimetype="text/calendar; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Content-Disposition": "inline; filename=medquest_feed.ics"
        }
    )


__all__ = [
    "bp",
    "get_planner_config_data",
    "get_planner_progress_data",
    "get_planner_topic_progress_data",
]
