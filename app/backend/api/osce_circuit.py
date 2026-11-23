"""
Planejamento e consolidação de Circuito Oficial de 2ª Fase (5 estações OSCE).
Extraído de `api/osce.py` para separar circuitos de sessão individual.
"""
from __future__ import annotations

import json
import random
import uuid
from typing import Any, Optional


def get_circuit_plan(
    db,
    institution: Optional[str] = "USP-RP",
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Monta um Circuito Misto de Treino com 5 estações cobrindo as 5 especialidades nucleares,
    sorteando estações com prioridade para aquelas ainda não concluídas pelo usuário.
    """
    areas_order = [
        "Clínica Médica",
        "Cirurgia Geral",
        "Pediatria",
        "Ginecologia e Obstetrícia",
        "Medicina Preventiva",
    ]
    circuit_id = f"circuit-{uuid.uuid4().hex[:10]}"
    stations_selected = []
    warnings: list[str] = []
    uid = user_id or ""
    has_inst_filter = bool(institution and institution not in ("Todas as Bancas", "TODAS"))

    for step_idx, area in enumerate(areas_order, 1):
        rows = []
        is_fallback = False

        if has_inst_filter:
            rows = db.execute(
                """
                SELECT s.id, s.code, s.title, s.area, s.subtema, s.institution, s.duration_seconds,
                       (
                           SELECT COUNT(*)
                           FROM osce_sessions sess
                           WHERE sess.station_id = s.id AND sess.user_id = ? AND sess.status = 'completed'
                       ) AS completed_attempts
                FROM osce_stations s
                WHERE s.area = ? AND s.institution = ?
                ORDER BY s.year DESC, s.id ASC
                """,
                (uid, area, institution),
            ).fetchall()

        if not rows:
            rows = db.execute(
                """
                SELECT s.id, s.code, s.title, s.area, s.subtema, s.institution, s.duration_seconds,
                       (
                           SELECT COUNT(*)
                           FROM osce_sessions sess
                           WHERE sess.station_id = s.id AND sess.user_id = ? AND sess.status = 'completed'
                       ) AS completed_attempts
                FROM osce_stations s
                WHERE s.area = ?
                ORDER BY s.year DESC, s.id ASC
                """,
                (uid, area),
            ).fetchall()
            if has_inst_filter and rows:
                is_fallback = True

        if rows:
            unseen = [r for r in rows if int(r["completed_attempts"] or 0) == 0]
            chosen = random.choice(unseen if unseen else rows)
            if is_fallback:
                warnings.append(
                    f"Sem estação de {area} para {institution}; sorteada estação da banca {chosen['institution']}."
                )
            stations_selected.append({
                "step": step_idx,
                "station_id": chosen["id"],
                "code": chosen["code"],
                "area": chosen["area"],
                "subtema": chosen["subtema"],
                "title": chosen["title"],
                "institution": chosen["institution"],
                "duration_seconds": chosen["duration_seconds"],
                "is_fallback_institution": is_fallback,
            })

    return {
        "circuit_id": circuit_id,
        "institution": institution or "USP-RP",
        "total_steps": len(stations_selected),
        "stations": stations_selected,
        "warnings": warnings,
    }


def get_circuit_summary(db, circuit_id: str, user_id: str) -> dict[str, Any]:
    """
    Consolida as notas e avaliações do Circuito de 2ª Fase de 5 estações (escala 0.0 a 50.0).
    """
    sessions = db.execute(
        """
        SELECT s.id, s.station_id, s.status, s.final_score, s.elapsed_seconds,
               s.checklist_evaluation_json, s.preceptor_feedback_json,
               st.code, st.title, st.area, st.institution
        FROM osce_sessions s
        JOIN osce_stations st ON s.station_id = st.id
        WHERE s.circuit_session_id = ? AND s.user_id = ?
        ORDER BY s.start_time ASC
        """,
        (circuit_id, user_id),
    ).fetchall()

    station_summaries = []
    total_score = 0.0
    total_completed = 0
    total_critical_errors = 0

    for idx, sess in enumerate(sessions, 1):
        score = float(sess["final_score"] or 0.0)
        is_completed = sess["status"] == "completed"
        if is_completed:
            total_completed += 1
            total_score += score

        fb = json.loads(sess["preceptor_feedback_json"] or "{}")
        crit_warns = fb.get("critical_warnings", [])
        total_critical_errors += len(crit_warns)

        station_summaries.append({
            "step": idx,
            "session_id": sess["id"],
            "station_id": sess["station_id"],
            "code": sess["code"],
            "area": sess["area"],
            "title": sess["title"],
            "institution": sess["institution"],
            "final_score": round(score, 1),
            "approved": score >= 7.0,
            "status": sess["status"],
            "critical_warnings": crit_warns,
        })

    max_score = 50.0
    avg_score = round(total_score / max(1, total_completed), 1) if total_completed > 0 else 0.0
    percentage = round((total_score / max_score) * 100, 1)
    approved = total_completed >= 5 and total_score >= 35.0

    if approved:
        board_feedback = (
            f"Desempenho acima da referência no Circuito misto de treino com {total_score:.1f}/50.0 pontos ({percentage}%). "
            "Atendimento consistente nas 5 grandes áreas (referência interna de treino: 35.0/50.0)."
        )
    elif total_completed < 5:
        board_feedback = f"Circuito misto de treino em andamento: {total_completed} de 5 estações concluídas. Total acumulado: {total_score:.1f}/50.0 pontos."
    else:
        board_feedback = (
            f"Pontuação de {total_score:.1f}/50.0 pontos ({percentage}%) abaixo da referência interna de treino (35.0/50.0). "
            f"Identificamos {total_critical_errors} alerta(s) crítico(s) de segurança clínica. Revise o espelho e pratique novamente."
        )

    return {
        "circuit_id": circuit_id,
        "user_id": user_id,
        "total_score": round(total_score, 1),
        "max_score": max_score,
        "average_score": avg_score,
        "percentage": percentage,
        "approved": approved,
        "stations_completed": total_completed,
        "total_stations": 5,
        "critical_errors_count": total_critical_errors,
        "stations": station_summaries,
        "board_feedback": board_feedback,
    }
