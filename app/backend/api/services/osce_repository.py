"""Repositório de estações OSCE, seed idempotente, catálogo e persistência de sessão."""
from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

from ..db import db_transaction
from ..osce_data import CANONICAL_STATIONS
from ..osce_physiology import _build_auscultation_foci, _build_physiology_engine

_OSCE_SEED_VERIFIED_SCOPES: set[tuple[str, int]] = set()


def ensure_osce_stations_seeded(db, *, seed_fn=None) -> int:
    """Garante estações semeadas em DB vazio/incompleto sem escrever em todo GET."""
    from flask import current_app

    is_testing = bool(current_app and current_app.config.get("TESTING"))
    db_scope = os.environ.get("MEDQUEST_DB") or os.environ.get("TURSO_DATABASE_URL") or "default"
    cache_key = (db_scope, len(CANONICAL_STATIONS))
    if not is_testing and cache_key in _OSCE_SEED_VERIFIED_SCOPES:
        return 0

    row = db.execute("SELECT COUNT(*) as total FROM osce_stations").fetchone()
    total = int(row["total"] if hasattr(row, "keys") else row[0]) if row else 0
    if total >= len(CANONICAL_STATIONS):
        if not is_testing:
            _OSCE_SEED_VERIFIED_SCOPES.add(cache_key)
        return 0

    inserted = (seed_fn or seed_osce_stations)(db)
    if not is_testing:
        _OSCE_SEED_VERIFIED_SCOPES.add(cache_key)
    return inserted


def seed_osce_stations(db, force: bool = False) -> int:
    """Insere ou atualiza o catálogo canônico de estações de prova prática."""
    inserted = 0
    with db_transaction(db, immediate=True):
        for st in CANONICAL_STATIONS:
            existing = db.execute("SELECT id FROM osce_stations WHERE code = ?", (st["code"],)).fetchone()
            door_md = st["scenario_door_markdown"]
            persona_payload = {
                **st["patient_persona"],
                "actor_script": st.get("actor_script", {}),
            }
            exam_payload = {
                **st["physical_exam"],
                "examiner_cards": st.get("examiner_cards", []),
            }
            persona_json = json.dumps(persona_payload, ensure_ascii=False)
            exam_json = json.dumps(exam_payload, ensure_ascii=False)
            lab_json = json.dumps(st.get("lab_imaging", {}), ensure_ascii=False)
            barema_json = json.dumps({
                "items": st["checklist_barema"],
                "critical_errors": st.get("critical_errors", []),
                "station_kind": st.get("station_kind", "emergencia"),
                "tasks": st.get("tasks", []),
                "source": st.get("source", ""),
                "clinical_review_date": st.get("clinical_review_date", ""),
            }, ensure_ascii=False)

            if existing:
                db.execute("""
                    UPDATE osce_stations
                    SET title = ?, area = ?, subtema = ?, institution = ?, year = ?,
                        difficulty = ?, duration_seconds = ?, scenario_door_markdown = ?,
                        patient_persona_json = ?, physical_exam_json = ?,
                        lab_imaging_json = ?, checklist_barema_json = ?
                    WHERE code = ?
                """, (
                    st["title"], st["area"], st["subtema"], st["institution"], st["year"],
                    st["difficulty"], st["duration_seconds"], door_md,
                    persona_json, exam_json, lab_json, barema_json,
                    st["code"]
                ))
            else:
                db.execute("""
                    INSERT INTO osce_stations (
                        code, title, area, subtema, institution, year,
                        difficulty, duration_seconds, scenario_door_markdown,
                        patient_persona_json, physical_exam_json,
                        lab_imaging_json, checklist_barema_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    st["code"], st["title"], st["area"], st["subtema"], st["institution"], st["year"],
                    st["difficulty"], st["duration_seconds"], door_md,
                    persona_json, exam_json, lab_json, barema_json
                ))
                inserted += 1
    return inserted


def list_osce_stations(
    db,
    user_id: Optional[str] = None,
    area: Optional[str] = None,
    institution: Optional[str] = None,
    difficulty: Optional[str] = None
) -> list[dict[str, Any]]:
    """Lista as estações práticas disponíveis com histórico de tentativas do usuário."""
    query = """
        SELECT s.id, s.code, s.title, s.area, s.subtema, s.institution, s.year,
               s.difficulty, s.duration_seconds, s.scenario_door_markdown,
               s.checklist_barema_json,
               (
                   SELECT MAX(sess.final_score)
                   FROM osce_sessions sess
                   WHERE sess.station_id = s.id AND sess.user_id = ? AND sess.status = 'completed'
               ) as best_score,
               (
                   SELECT sess.final_score
                   FROM osce_sessions sess
                   WHERE sess.station_id = s.id AND sess.user_id = ? AND sess.status = 'completed'
                     AND (sess.actions_taken_json LIKE '%"mode": "blind"%' OR sess.actions_taken_json NOT LIKE '%"mode": "guided"%')
                   ORDER BY sess.start_time ASC
                   LIMIT 1
               ) as first_blind_score,
               (
                   SELECT sess.final_score
                   FROM osce_sessions sess
                   WHERE sess.station_id = s.id AND sess.user_id = ? AND sess.status = 'completed'
                   ORDER BY sess.start_time DESC
                   LIMIT 1
               ) as last_score,
               (
                   SELECT COUNT(*)
                   FROM osce_sessions sess
                   WHERE sess.station_id = s.id AND sess.user_id = ? AND sess.status = 'completed'
               ) as completed_attempts
        FROM osce_stations s
        WHERE 1=1
    """
    uid = user_id or ""
    params: list[Any] = [uid, uid, uid, uid]

    if area and area != "Todas as Áreas":
        query += " AND s.area = ?"
        params.append(area)
    if institution and institution not in ("Todas as Bancas", "TODAS"):
        query += " AND s.institution = ?"
        params.append(institution)
    if difficulty:
        query += " AND s.difficulty = ?"
        params.append(difficulty)

    query += " ORDER BY s.institution, s.area, s.id"
    rows = db.execute(query, tuple(params)).fetchall()

    result = []
    for r in rows:
        barema_meta = json.loads(r["checklist_barema_json"] or "{}")
        station_kind = barema_meta.get("station_kind", "emergencia") if isinstance(barema_meta, dict) else "emergencia"
        result.append({
            "id": r["id"],
            "code": r["code"],
            "title": r["title"],
            "area": r["area"],
            "subtema": r["subtema"],
            "institution": r["institution"],
            "year": r["year"],
            "difficulty": r["difficulty"],
            "duration_seconds": r["duration_seconds"],
            "station_kind": station_kind,
            "scenario_door_markdown": r["scenario_door_markdown"],
            "best_score": round(float(r["best_score"]), 1) if r["best_score"] is not None else None,
            "first_blind_score": round(float(r["first_blind_score"]), 1) if r["first_blind_score"] is not None else None,
            "last_score": round(float(r["last_score"]), 1) if r["last_score"] is not None else None,
            "completed_attempts": int(r["completed_attempts"] or 0),
        })
    return result


def _get_task_progress(tasks: list[dict[str, Any]], actions: list[dict[str, Any]]) -> dict[str, Any]:
    """Calcula a liberação sequencial das tarefas (tarefa N+1 só abre após declarar N concluída)."""
    ordered = sorted(tasks or [], key=lambda t: int(t.get("step", 0)))
    completed_steps: list[int] = []
    expected_next = 1

    for act in actions:
        if act.get("action_type") != "complete_task":
            continue
        if act.get("accepted", True) is False:
            continue
        raw_step = act.get("step")
        if raw_step is None:
            m = re.search(r"(\d+)", str(act.get("action_target", "")))
            raw_step = int(m.group(1)) if m else None
        if raw_step == expected_next and expected_next <= len(ordered):
            completed_steps.append(expected_next)
            expected_next += 1

    current_step = expected_next if expected_next <= len(ordered) else len(ordered) + 1
    visible_tasks: list[dict[str, Any]] = []
    for t in ordered:
        step_num = int(t.get("step", 0))
        is_completed = step_num in completed_steps
        is_locked = step_num > current_step
        visible_tasks.append({
            "id": str(t.get("id", f"task_{step_num}")),
            "step": step_num,
            "completed": is_completed,
            "locked": is_locked,
            "description": (
                "Bloqueada — conclua a tarefa anterior para liberar."
                if is_locked
                else str(t.get("description", ""))
            ),
        })

    return {
        "total_steps": len(ordered),
        "completed_steps": completed_steps,
        "current_step": min(current_step, len(ordered)) if ordered else 1,
        "all_completed": bool(ordered) and len(completed_steps) >= len(ordered),
        "visible_tasks": visible_tasks,
    }


def _sanitize_door_markdown_for_sequential_tasks(door_md: str, tasks: list[dict[str, Any]]) -> str:
    """Oculta os enunciados das tarefas 2..N na porta inicial até liberação progressiva."""
    if not door_md or len(tasks) <= 1:
        return door_md
    return re.sub(
        r"(?m)^(\s*)([2-9]|\d{2,})\.\s+.+$",
        lambda m: f"{m.group(1)}{m.group(2)}. [Bloqueada — declare a tarefa anterior concluída para liberar]",
        door_md,
    )


def get_osce_station(db, station_id: int, include_barema: bool = False) -> Optional[dict[str, Any]]:
    """Carrega detalhes de uma estação, mantendo o barema oculto durante a prova."""
    row = db.execute("""
        SELECT id, code, title, area, subtema, institution, year,
               difficulty, duration_seconds, scenario_door_markdown,
               patient_persona_json, physical_exam_json, lab_imaging_json,
               checklist_barema_json
        FROM osce_stations
        WHERE id = ?
    """, (station_id,)).fetchone()
    if not row:
        return None

    physical_exam = json.loads(row["physical_exam_json"] or "{}")
    lab_imaging = json.loads(row["lab_imaging_json"] or "{}")
    patient_persona = json.loads(row["patient_persona_json"] or "{}")
    barema = json.loads(row["checklist_barema_json"] or "{}")
    station_kind = barema.get("station_kind", "emergencia") if isinstance(barema, dict) else "emergencia"
    raw_tasks = barema.get("tasks", []) if isinstance(barema, dict) else []
    initial_task_progress = _get_task_progress(raw_tasks, [])

    station = {
        "id": row["id"],
        "code": row["code"],
        "title": row["title"],
        "area": row["area"],
        "subtema": row["subtema"],
        "institution": row["institution"],
        "year": row["year"],
        "difficulty": row["difficulty"],
        "duration_seconds": row["duration_seconds"],
        "station_kind": station_kind,
        "scenario_door_markdown": (
            row["scenario_door_markdown"]
            if include_barema
            else _sanitize_door_markdown_for_sequential_tasks(row["scenario_door_markdown"], raw_tasks)
        ),
        "tasks": raw_tasks if include_barema else initial_task_progress["visible_tasks"],
        "patient_persona": {
            "name": patient_persona.get("name"),
            "age": patient_persona.get("age"),
            "gender": patient_persona.get("gender"),
            "chief_complaint": patient_persona.get("chief_complaint"),
        },
        "physical_exam_categories": (
            list((physical_exam.get("maneuvers") or physical_exam.get("findings") or {}).keys())
            if include_barema
            else []
        ),
        "vitals_available": bool(physical_exam.get("vitals")),
        "lab_imaging_catalog": (
            [{"key": k, "title": v.get("title", k)} for k, v in lab_imaging.items()]
            if include_barema
            else []
        ),
        "physiology_engine": _build_physiology_engine(physical_exam, row["subtema"], row["title"]),
        "auscultation_foci": _build_auscultation_foci(physical_exam, row["subtema"], row["title"])
    }

    if include_barema:
        barema = json.loads(row["checklist_barema_json"] or "{}")
        station["checklist_barema"] = barema.get("items", [])
        station["critical_errors"] = barema.get("critical_errors", [])
        station["source"] = barema.get("source", "")
        station["clinical_review_date"] = barema.get("clinical_review_date", "")
        station["actor_script"] = patient_persona.get("actor_script", {})
        station["examiner_cards"] = physical_exam.get("examiner_cards", [])
        station["patient_persona_full"] = patient_persona
        station["physical_exam_full"] = physical_exam
        station["lab_imaging_full"] = lab_imaging

    return station



def _append_osce_session_entries(
    db,
    session_id: str,
    user_id: str,
    new_transcript: Optional[list[dict[str, Any]]] = None,
    new_actions: Optional[list[dict[str, Any]]] = None,
    elapsed_seconds: int = 0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Lê e anexa entradas sob lock imediato para impedir Lost Update entre TTS/IA/ações."""
    with db_transaction(db, immediate=True):
        fresh = db.execute(
            "SELECT transcript_json, actions_taken_json, elapsed_seconds FROM osce_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        ).fetchone()
        if not fresh:
            raise ValueError(f"Sessão {session_id} não encontrada.")
        cur_transcript = json.loads(fresh["transcript_json"] or "[]")
        cur_actions = json.loads(fresh["actions_taken_json"] or "[]")
        if new_transcript:
            cur_transcript.extend(new_transcript)
        if new_actions:
            cur_actions.extend(new_actions)
        next_elapsed = max(int(fresh["elapsed_seconds"] or 0), int(elapsed_seconds or 0))
        db.execute(
            """
            UPDATE osce_sessions
            SET transcript_json = ?, actions_taken_json = ?, elapsed_seconds = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                json.dumps(cur_transcript, ensure_ascii=False),
                json.dumps(cur_actions, ensure_ascii=False),
                next_elapsed,
                session_id,
                user_id,
            ),
        )
    return cur_transcript, cur_actions

