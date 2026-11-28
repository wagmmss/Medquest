"""Geração e formatação de feed/exportação iCalendar (.ics) do Planner."""
from __future__ import annotations

import os
import urllib.parse
from datetime import datetime, timedelta, timezone

from flask import request

from ..adaptive import get_adaptive_signals_by_topic
from .planner_scheduler import build_plan_from_schedule, generate_annual_plan
from .planner_store import (
    _fetch_plan_data,
    _get_completed_subtemas,
    _get_planner_config,
    _get_user_internato_blocks,
    _resolve_schedule_mode,
)

def _get_base_url():
    configured = (os.environ.get("FRONTEND_URL") or "").split(",")[0].strip().rstrip("/")
    if configured:
        return configured
    try:
        host_url = (request.host_url or "").rstrip("/")
        if ":5050" in host_url:
            return "http://localhost:3000"
        return host_url
    except Exception:
        return ""


def _escape_ics_text(value: object) -> str:
    text = str(value or "")
    text = text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    text = text.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "")
    return text


def _generate_calendar_ics_content(db, user_id):
    config_row = db.execute("SELECT * FROM planner_config WHERE user_id = ?", (user_id,)).fetchone()
    start_date, exam_date, days, hours_per_week = _get_planner_config(db, user_id, config_row=config_row)
    rows, answered_map, use_bank_incidence = _fetch_plan_data(db, user_id)
    adaptive_signals = get_adaptive_signals_by_topic(db, user_id)
    completed_subtemas = _get_completed_subtemas(db, user_id)
    internato_blocks = _get_user_internato_blocks(db, user_id, config_row=config_row)
    row_keys = config_row.keys() if config_row and hasattr(config_row, "keys") else []
    org_mode = (
        config_row["organization_mode"]
        if config_row and "organization_mode" in row_keys and config_row["organization_mode"]
        else "geral"
    )
    schedule_mode = _resolve_schedule_mode(org_mode, intensive=False)

    schedule_rows = db.execute(
        "SELECT week, subtema, display_order FROM planner_schedule WHERE user_id = ? AND mode = ? ORDER BY week ASC, display_order ASC",
        (user_id, schedule_mode)
    ).fetchall()
    if schedule_rows:
        plan_result = build_plan_from_schedule(
            schedule_rows, start_date, hours_per_week,
            exam_date_str=exam_date,
            rows=rows, user_progress=answered_map,
            adaptive_signals=adaptive_signals, intensive=False,
            completed_subtemas=completed_subtemas,
            organization=org_mode,
            internato_blocks=internato_blocks,
            use_bank_incidence=use_bank_incidence,
        ) or {}
    else:
        plan_result = generate_annual_plan(
            rows, start_date, exam_date, hours_per_week,
            intensive=False, user_progress=answered_map,
            adaptive_signals=adaptive_signals,
            organization=org_mode,
            internato_blocks=internato_blocks,
            completed_subtemas=completed_subtemas,
            use_bank_incidence=use_bank_incidence,
        )

    plan_weeks = plan_result.get("plan", [])
    now_dt = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//MedQuest//Cronograma de Estudos//PT-BR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:MedQuest - Cronograma de Residência Médica",
        "X-WR-TIMEZONE:America/Sao_Paulo",
    ]

    study_days_count = max(1, min(7, days))
    base_url = _get_base_url()

    _generate_ics_events(ics_lines, plan_weeks, now_dt, study_days_count, base_url, user_id)
    _append_shift_events(db, user_id, ics_lines, now_dt, base_url)

    ics_lines.append("END:VCALENDAR")
    return "\r\n".join(ics_lines)


def _append_shift_events(db, user_id: str, ics_lines: list[str], now_dt: str, base_url: str) -> None:
    """Inclui plantões cadastrados em user_shifts como eventos de dia inteiro (RFC 5545 DTEND exclusivo)."""
    from ..internato_config import SHIFT_LABELS

    try:
        rows = db.execute(
            "SELECT date_iso, kind, note FROM user_shifts WHERE user_id = ? ORDER BY date_iso ASC, kind ASC",
            (user_id,),
        ).fetchall()
    except Exception:
        return

    footer_link = f"\\n\\n🔗 {base_url}/planner?tab=plano-6ano" if base_url else ""
    for row in rows:
        date_iso = str(row["date_iso"] or "")
        kind = str(row["kind"] or "")
        note = str(row["note"] or "").strip()
        try:
            start_day = datetime.strptime(date_iso[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        end_day = start_day + timedelta(days=1)
        summary = _escape_ics_text(SHIFT_LABELS.get(kind, kind))
        desc_parts = [f"Plantão registrado na rotina do 6º Ano ({summary})."]
        if note:
            desc_parts.append(f"Observação: {note}")
        description = _escape_ics_text("\n".join(desc_parts)) + footer_link
        ics_lines.extend([
            "BEGIN:VEVENT",
            f"UID:shift-{start_day.isoformat()}-{kind}@medquest",
            f"DTSTAMP:{now_dt}",
            f"DTSTART;VALUE=DATE:{start_day.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{end_day.strftime('%Y%m%d')}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{description}",
            "STATUS:CONFIRMED",
            "END:VEVENT",
        ])


def _build_consolidation_event(ics_lines, w_num, week_start_dt, w_date_str, now_dt, user_id, base_url):
    start_str = week_start_dt.strftime("%Y%m%dT080000")
    end_str = (week_start_dt + timedelta(hours=3)).strftime("%Y%m%dT110000")
    uid = f"medquest-week-consolidation-{w_num}-{user_id}-{w_date_str}@medquest"
    footer_link = f"\\n\\n🔗 {base_url}/planner" if base_url else ""
    ics_lines.extend([
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{now_dt}",
        f"DTSTART:{start_str}",
        f"DTEND:{end_str}",
        f"SUMMARY:[MedQuest] Semana {w_num}: Revisão Geral & Consolidação",
        f"DESCRIPTION:Semana reservada para consolidação de metas e simulados.{footer_link}",
        "STATUS:CONFIRMED",
        "END:VEVENT",
    ])


def _build_topic_events(ics_lines, topics, w_num, week_start_dt, study_days_count, now_dt, user_id, base_url):
    day_slot_minutes = [0] * study_days_count
    for t_idx, topic in enumerate(topics):
        subtema = topic.get("subtema", "Aula")
        area = topic.get("area", "Geral")
        theory_h = topic.get("estimated_theory_hours", 1.0)
        practice_h = topic.get("estimated_practice_hours", 2.0)
        total_h = topic.get("estimated_hours", theory_h + practice_h)

        day_offset = t_idx % study_days_count
        topic_date = week_start_dt + timedelta(days=day_offset)
        date_str = topic_date.strftime("%Y%m%d")
        topic_id_clean = urllib.parse.quote(subtema[:30]).replace("%", "")

        # Duração REAL da aula (minutos calculados com precisão)
        duration_minutes = max(30, int(round(total_h * 60)))
        start_minutes = (8 * 60) + day_slot_minutes[day_offset]
        dt_start = topic_date.replace(hour=0, minute=0, second=0) + timedelta(minutes=start_minutes)
        dt_end = dt_start + timedelta(minutes=duration_minutes)
        day_slot_minutes[day_offset] += duration_minutes + 15

        start_str = dt_start.strftime("%Y%m%dT%H%M%S")
        end_str = dt_end.strftime("%Y%m%dT%H%M%S")
        uid_lecture = f"medquest-lec-{w_num}-{t_idx}-{topic_id_clean}-{user_id}-{date_str}@medquest"

        encoded_sub = urllib.parse.quote(subtema)
        # O subtema canônico é a chave de associação estável. Não inclua
        # a área aqui: nomes de área de bases antigas podem divergir da
        # normalização exibida no planner e zerar indevidamente a fila.
        safe_subtema = _escape_ics_text(subtema)
        safe_area = _escape_ics_text(area)
        study_url_text = f"\\n\\n🔗 Questões: {base_url}/estudar?subtema={encoded_sub}&limit=25" if base_url else ""

        ics_lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid_lecture}",
            f"DTSTAMP:{now_dt}",
            f"DTSTART:{start_str}",
            f"DTEND:{end_str}",
            f"SUMMARY:[MedQuest] 📖 {safe_subtema} ({safe_area})",
            f"DESCRIPTION:📚 Carga: {total_h}h (Teoria: {theory_h}h + Questões: {practice_h}h)\\nSemana {w_num} • {safe_area}{study_url_text}",
            "STATUS:CONFIRMED",
            "END:VEVENT",
        ])


def _generate_ics_events(ics_lines, plan_weeks, now_dt, study_days_count, base_url, user_id):
    for w in plan_weeks:
        w_num = w.get("week")
        w_date_str = w.get("date", "")[:10]
        if not w_date_str:
            continue
        
        try:
            week_start_dt = datetime.strptime(w_date_str, "%Y-%m-%d")
        except Exception:
            continue

        topics = w.get("topics", [])
        if not topics:
            _build_consolidation_event(ics_lines, w_num, week_start_dt, w_date_str, now_dt, user_id, base_url)
        else:
            _build_topic_events(ics_lines, topics, w_num, week_start_dt, study_days_count, now_dt, user_id, base_url)


