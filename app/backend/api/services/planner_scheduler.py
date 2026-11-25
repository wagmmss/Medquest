"""Algoritmos de distribuição semanal, internato e reconstrução de cronograma do Planner."""
from __future__ import annotations

import math
from datetime import datetime, timedelta

from ..internato_config import RODIZIOS_TURMA_J
from .planner_catalog import (
    BALANCED_ROTATION_CYCLE,
    _build_meta_dict,
    _build_topic_item,
    _compute_empirical_incidence,
    _consolidate_row_stats,
    _load_catalogs,
    _prepare_topics,
)
from .taxonomy import get_normalized_area

def _parse_dates_and_weeks(start_date_str, exam_date_str):
    try:
        start_date = datetime.fromisoformat(start_date_str.replace("Z", "+00:00"))
        exam_date = datetime.fromisoformat(exam_date_str.replace("Z", "+00:00"))
    except ValueError:
        return None, None, {"error": "Formato de data inválido."}

    # Normaliza para naive: exam_date costuma vir só com a data (sem timezone),
    # enquanto start_date pode vir com timezone (ex.: default gerado no backend).
    if start_date.tzinfo is not None:
        start_date = start_date.replace(tzinfo=None)
    if exam_date.tzinfo is not None:
        exam_date = exam_date.replace(tzinfo=None)

    total_weeks = math.ceil((exam_date - start_date).days / 7)
    if total_weeks <= 0:
        return None, None, {"error": "A data da prova deve ser no futuro."}

    # Cap at 5 years to prevent memory/rendering issues in frontend
    total_weeks = min(total_weeks, 260)
    return start_date, total_weeks, None



WEEK_OVERFLOW_TOLERANCE_HOURS = 1.0
INTERNATO_ANCHOR_RATIO = 0.70


def _normalize_internato_area(raw_area):
    if not raw_area:
        return None
    lower = raw_area.lower().strip()
    if lower in ("geral", "equilibrado", "férias", "ferias", "misto", "todas"):
        return None
    if "intensiva" in lower or "anestes" in lower or "especialidades" in lower or "oftalmo" in lower or "orl" in lower:
        return "Clínica Médica"
    if "mfc" in lower:
        return "Preventiva"
    if "emerg" in lower or "trauma" in lower:
        return "Cirurgia"
    norm = get_normalized_area(raw_area)
    return None if norm == "Outros" else norm


def get_block_for_date(date_obj, internato_blocks=None):
    blocks = internato_blocks if internato_blocks is not None else RODIZIOS_TURMA_J
    for bloco in blocks:
        try:
            inicio = datetime.strptime(bloco["start"], "%Y-%m-%d")
            fim = datetime.strptime(bloco["end"], "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        except (KeyError, ValueError, TypeError):
            continue
        if inicio <= date_obj <= fim:
            raw_area = bloco.get("area")
            norm_area = _normalize_internato_area(raw_area)
            raw_hours = bloco.get("hours_per_week")
            block_hours = None
            if raw_hours is not None:
                try:
                    val = float(raw_hours)
                    if 1.0 <= val <= 168.0:
                        block_hours = val
                except (TypeError, ValueError):
                    pass
            return {
                "area": norm_area,
                "raw_area": raw_area,
                "label": bloco.get("label") or raw_area,
                "hours_per_week": block_hours,
            }
    return None


def get_area_for_date(date_obj, internato_blocks=None):
    block = get_block_for_date(date_obj, internato_blocks)
    return block["area"] if block else None


def _pick_best_fitting_topic(area_topics, current_week_hours, target_hours, max_week_hours):
    """Escolhe o tópico ideal da área respeitando prioridade e fechando perto da meta sem passar do teto."""
    if not area_topics:
        return -1

    # Primeiro tópico da semana: sempre prioriza o mais importante disponível
    if current_week_hours == 0:
        return 0

    remaining_to_max = max_week_hours - current_week_hours
    fitting = [
        (idx, t)
        for idx, t in enumerate(area_topics)
        if t["estimated_hours"] <= remaining_to_max + 1e-6
    ]
    if not fitting:
        return -1

    # Se ainda cabe folgado mais de um tópico médio depois deste, mantém a ordem de prioridade
    first_idx, first_topic = fitting[0]
    if (current_week_hours + first_topic["estimated_hours"]) < (target_hours - 2.25):
        return first_idx

    # Perto de fechar a semana: faz best-fit para atingir [target_hours - 0.5, max_week_hours]
    # priorizando tópicos High-Yield / Essenciais do Internato dentro da faixa ideal.
    def _fit_score(item):
        idx, t = item
        new_total = current_week_hours + t["estimated_hours"]
        # Penaliza ficar muito abaixo da meta quando há alternativas que fecham melhor
        in_sweet_spot = 1 if (target_hours - 0.5) <= new_total <= (max_week_hours + 1e-6) else 0
        # Dentro da faixa boa, prefere High-Yield/Internato, depois o mais próximo da meta
        if in_sweet_spot:
            priority_band = 2 if t["priority"] >= 100 else (1 if t["priority"] >= 30 else 0)
            distance_penalty = abs(new_total - (target_hours + 0.3))
            priority_bonus = t["priority"] / 500.0
            return (2, priority_band, -distance_penalty + priority_bonus, -idx)
        # Se nenhum atinge a faixa ideal em um único passo, prefere o que melhor preenche ou permite próximo encaixe
        leaves_room_for_more = 1 if (max_week_hours - new_total) >= 2.25 else 0
        return (1 if leaves_room_for_more else 0, new_total, t["priority"], -idx)

    best_idx, _ = max(fitting, key=_fit_score)
    return best_idx


def _rank_rotation_areas(active_areas, cycle_cursor, week_area_counts, exclude_area=None):
    """Ordena áreas seguindo o ciclo ponderado contínuo a partir de cycle_cursor, evitando repetir área na semana."""
    pool = [a for a in active_areas if a != exclude_area]
    if not pool:
        pool = list(active_areas)

    cycle_len = len(BALANCED_ROTATION_CYCLE)
    distance_by_area = {}
    for offset in range(cycle_len):
        area_name = BALANCED_ROTATION_CYCLE[(cycle_cursor + offset) % cycle_len]
        if area_name not in distance_by_area:
            distance_by_area[area_name] = offset

    return sorted(
        pool,
        key=lambda area: (
            week_area_counts.get(area, 0),
            distance_by_area.get(area, cycle_len),
            area,
        ),
    )


def _advance_rotation_cursor(cycle_cursor, picked_area):
    """Avança o cursor do ciclo para a posição logo após a ocorrência usada de picked_area."""
    cycle_len = len(BALANCED_ROTATION_CYCLE)
    for offset in range(cycle_len):
        idx = (cycle_cursor + offset) % cycle_len
        if BALANCED_ROTATION_CYCLE[idx] == picked_area:
            return (idx + 1) % cycle_len
    return (cycle_cursor + 1) % cycle_len


def _try_improve_underfilled_week(
    week_topics,
    current_week_hours,
    topics_by_area,
    target_hours,
    max_week_hours,
    preferred_area=None,
):
    """Se a semana fechou curta (< target - 1.0h), tenta trocar o último tópico para fechar em [target-0.5, max]."""
    if not week_topics or current_week_hours >= (target_hours - 1.0):
        return current_week_hours

    last_topic = week_topics[-1]
    base_hours = current_week_hours - last_topic["estimated_hours"]
    best_swap = None

    # Procura um tópico único mais longo ou um par de tópicos curtos que feche melhor a semana
    candidate_areas = [a for a, lst in topics_by_area.items() if lst]
    if preferred_area and preferred_area in candidate_areas:
        candidate_areas = [preferred_area] + [a for a in candidate_areas if a != preferred_area]

    # 1) Tenta substituir o último tópico por um mais longo (priorizando mesma área)
    search_areas = [last_topic["area"]] + [a for a in candidate_areas if a != last_topic["area"]]
    for area in search_areas:
        for idx, cand in enumerate(topics_by_area.get(area, [])):
            new_h = base_hours + cand["estimated_hours"]
            if current_week_hours + 0.3 < new_h <= max_week_hours + 1e-6:
                same_area_bonus = 1 if area == last_topic["area"] else 0
                score = (same_area_bonus, new_h, cand["priority"])
                if best_swap is None or score > best_swap[0]:
                    best_swap = (score, "single", area, idx)

    if best_swap is not None:
        _, _, swap_area, swap_idx = best_swap
        replacement = topics_by_area[swap_area].pop(swap_idx)
        topics_by_area.setdefault(last_topic["area"], []).append(last_topic)
        topics_by_area[last_topic["area"]].sort(key=lambda x: x["priority"], reverse=True)
        week_topics[-1] = replacement
        return base_hours + replacement["estimated_hours"]

    return current_week_hours


def _build_weekly_plan(
    all_topics,
    start_date,
    total_weeks,
    hours_per_week,
    organization="geral",
    internato_blocks=None,
):
    pending_topics = [t for t in all_topics if not t.get("completed")]
    completed_topics = [t for t in all_topics if t.get("completed")]

    topics_by_area = {}
    for t in pending_topics:
        topics_by_area.setdefault(t["area"], []).append(t)

    cycle_cursor = 0
    plan = []

    for week in range(1, total_weeks + 1):
        week_topics = []
        current_week_hours = 0.0
        week_area_counts = {}
        week_date = start_date + timedelta(weeks=week - 1)

        block_info = (
            get_block_for_date(week_date, internato_blocks)
            if organization == "internato"
            else None
        )
        area_foco = block_info["area"] if block_info else None
        week_target_hours = (
            block_info["hours_per_week"]
            if block_info and block_info.get("hours_per_week") is not None
            else float(hours_per_week)
        )
        max_week_hours = week_target_hours + WEEK_OVERFLOW_TOLERANCE_HOURS
        anchor_target_hours = week_target_hours * INTERNATO_ANCHOR_RATIO
        anchor_hours_allocated = 0.0

        while current_week_hours < (week_target_hours - 0.5):
            active_areas = [a for a, t_list in topics_by_area.items() if len(t_list) > 0]
            if not active_areas:
                break

            ordered_areas = []
            if organization == "internato" and area_foco and area_foco in active_areas:
                other_areas = [a for a in active_areas if a != area_foco]
                # Híbrido 70/30: garante ~70% com o rodízio-âncora e ~30% com a trilha paralela.
                # Coloca 2 temas da âncora e então 1 da trilha paralela (repetindo a proporção em semanas maiores).
                parallel_hours_allocated = current_week_hours - anchor_hours_allocated
                parallel_target_hours = week_target_hours * (1.0 - INTERNATO_ANCHOR_RATIO)
                anchor_count_week = week_area_counts.get(area_foco, 0)
                parallel_count_week = len(week_topics) - anchor_count_week
                need_parallel_now = (
                    bool(other_areas)
                    and anchor_count_week >= 2
                    and (
                        parallel_count_week == 0
                        or (
                            anchor_hours_allocated >= anchor_target_hours
                            and parallel_hours_allocated < parallel_target_hours
                        )
                    )
                )
                need_anchor = not need_parallel_now and (
                    anchor_hours_allocated == 0.0
                    or anchor_hours_allocated < anchor_target_hours
                    or not other_areas
                )
                if need_anchor:
                    ordered_areas = [area_foco] + _rank_rotation_areas(
                        active_areas, cycle_cursor, week_area_counts, exclude_area=area_foco
                    )
                else:
                    ordered_areas = _rank_rotation_areas(
                        active_areas, cycle_cursor, week_area_counts, exclude_area=area_foco
                    ) + [area_foco]
            else:
                ordered_areas = _rank_rotation_areas(
                    active_areas, cycle_cursor, week_area_counts
                )

            candidate_area = None
            candidate_idx = -1
            for area in ordered_areas:
                idx = _pick_best_fitting_topic(
                    topics_by_area[area],
                    current_week_hours,
                    week_target_hours,
                    max_week_hours,
                )
                if idx != -1:
                    candidate_area = area
                    candidate_idx = idx
                    break

            if candidate_area is not None:
                topic = topics_by_area[candidate_area].pop(candidate_idx)
                week_topics.append(topic)
                current_week_hours += topic["estimated_hours"]
                week_area_counts[candidate_area] = week_area_counts.get(candidate_area, 0) + 1
                if candidate_area == area_foco:
                    anchor_hours_allocated += topic["estimated_hours"]
                else:
                    cycle_cursor = _advance_rotation_cursor(cycle_cursor, candidate_area)
            else:
                break

        # Passo de refinamento: se ainda houver temas pendentes e a semana fechou curta (< meta - 1h), tenta swap
        has_remaining = any(len(lst) > 0 for lst in topics_by_area.values())
        if has_remaining and current_week_hours < (week_target_hours - 1.0):
            current_week_hours = _try_improve_underfilled_week(
                week_topics,
                current_week_hours,
                topics_by_area,
                week_target_hours,
                max_week_hours,
                preferred_area=area_foco,
            )

        week_entry = {
            "week": week,
            "date": week_date.isoformat(),
            "topics": week_topics,
            "recommended_hours": round(week_target_hours, 1) if week_target_hours % 1 else int(week_target_hours),
            "allocated_hours": round(current_week_hours, 1),
        }
        if organization == "internato" and block_info:
            week_entry["internato_block_label"] = block_info["label"]
            week_entry["internato_block_area"] = block_info["area"] or block_info["raw_area"]
        plan.append(week_entry)

    return plan, completed_topics


def generate_annual_plan(
    rows,
    start_date_str,
    exam_date_str,
    hours_per_week,
    intensive=False,
    user_progress=None,
    adaptive_signals=None,
    organization="geral",
    internato_blocks=None,
    completed_subtemas=None,
    use_bank_incidence=False,
):
    """
    Gera um plano de estudos fatiado por semanas conforme o modo de organização
    ('geral' ou 'internato') e filtro intensivo, preservando aulas já concluídas
    sem consumir horas semanais de estudo pendente.
    """
    start_date, total_weeks, err = _parse_dates_and_weeks(start_date_str, exam_date_str)
    if err:
        return err

    planner_meta, katomart_subtemas, practice_hours_per_subtema = _load_catalogs()
    meta_dict = _build_meta_dict(planner_meta, katomart_subtemas)
    row_stats = _consolidate_row_stats(rows, meta_dict)
    incidence_map, _using_empirical = _compute_empirical_incidence(
        meta_dict, row_stats, use_bank_incidence=use_bank_incidence
    )

    all_topics, _total_required_hours, pending_required_hours = _prepare_topics(
        meta_dict,
        row_stats,
        user_progress,
        intensive,
        practice_hours_per_subtema,
        adaptive_signals=adaptive_signals,
        completed_subtemas=completed_subtemas,
        incidence_map=incidence_map or None,
    )

    plan, completed_topics = _build_weekly_plan(
        all_topics,
        start_date,
        total_weeks,
        hours_per_week,
        organization=organization,
        internato_blocks=internato_blocks,
    )

    total_available_hours = sum(float(w["recommended_hours"]) for w in plan)
    scheduled_pending_count = sum(
        1 for w in plan for t in w.get("topics", []) if not t.get("completed")
    )
    target_pending_count = sum(1 for t in all_topics if not t.get("completed"))
    warning_msg = None
    if scheduled_pending_count < target_pending_count and pending_required_hours > total_available_hours:
        warning_msg = f"Você tem {round(total_available_hours)} horas disponíveis, mas precisa de {round(pending_required_hours)} horas para cobrir {'este plano' if intensive else 'todo o edital'}."

    result = {"plan": plan, "completed_topics": completed_topics}
    if warning_msg:
        result["warning"] = warning_msg
        result["total_required_hours"] = round(pending_required_hours)
        result["total_available_hours"] = round(total_available_hours)

    return result


def build_plan_from_schedule(
    schedule_rows,
    start_date_str,
    hours_per_week,
    exam_date_str=None,
    rows=None,
    user_progress=None,
    adaptive_signals=None,
    intensive=False,
    completed_subtemas=None,
    organization="geral",
    internato_blocks=None,
    use_bank_incidence=False,
):
    """
    Reconstrói a estrutura semanal do plano a partir do cronograma congelado em banco,
    enriquecendo em tempo real os badges e motivos adaptativos de cada aula sem alterar
    a ordem ou alocação das semanas.
    """
    if not schedule_rows:
        return None

    try:
        start_date = datetime.fromisoformat(str(start_date_str).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        start_date = datetime.now()
    if start_date.tzinfo is not None:
        start_date = start_date.replace(tzinfo=None)

    planner_meta, katomart_subtemas, practice_hours_per_subtema = _load_catalogs()
    meta_dict = _build_meta_dict(planner_meta, katomart_subtemas)
    row_stats = _consolidate_row_stats(rows or [], meta_dict)
    incidence_map, _using_empirical = _compute_empirical_incidence(
        meta_dict, row_stats, use_bank_incidence=use_bank_incidence
    )

    if user_progress is None:
        user_progress = {}

    all_topics, _total_required_hours, pending_required_hours = _prepare_topics(
        meta_dict,
        row_stats,
        user_progress,
        intensive,
        practice_hours_per_subtema,
        adaptive_signals=adaptive_signals,
        completed_subtemas=completed_subtemas,
        incidence_map=incidence_map or None,
    )

    weeks_map = {}
    scheduled_subtemas = set()
    for r in schedule_rows:
        w_num = int(r["week"])
        weeks_map.setdefault(w_num, []).append(r["subtema"])
        scheduled_subtemas.add(r["subtema"])

    total_weeks = None
    if exam_date_str:
        _, total_weeks_calc, err = _parse_dates_and_weeks(start_date_str, exam_date_str)
        if not err and total_weeks_calc:
            total_weeks = total_weeks_calc

    max_scheduled_week = max([int(r["week"]) for r in schedule_rows], default=1)
    num_weeks = max(total_weeks or 0, max_scheduled_week)
    all_week_numbers = list(range(1, num_weeks + 1)) if num_weeks > 0 else sorted(weeks_map.keys())

    plan = []

    for week_num in all_week_numbers:
        week_topics = []
        current_week_hours = 0.0
        week_date = start_date + timedelta(weeks=week_num - 1)
        block_info = (
            get_block_for_date(week_date, internato_blocks)
            if organization == "internato"
            else None
        )
        week_target_hours = (
            block_info["hours_per_week"]
            if block_info and block_info.get("hours_per_week") is not None
            else float(hours_per_week)
        )
        for subtema in weeks_map.get(week_num, []):
            meta = meta_dict.get(subtema)
            if not meta:
                continue
            stats = row_stats.get(subtema, {"q_count": 0, "target_q_count": 0, "subtopics": []})
            prog = user_progress.get(subtema)
            topic_obj, topic_hours = _build_topic_item(
                subtema,
                meta,
                stats,
                prog,
                practice_hours_per_subtema,
                adaptive_signals,
                completed_subtemas=completed_subtemas,
                incidence_info=incidence_map.get(subtema) if incidence_map else None,
            )
            if not topic_obj["completed"]:
                current_week_hours += topic_hours
            week_topics.append(topic_obj)

        week_entry = {
            "week": week_num,
            "date": week_date.isoformat(),
            "topics": week_topics,
            "recommended_hours": round(week_target_hours, 1) if week_target_hours % 1 else int(week_target_hours),
            "allocated_hours": round(current_week_hours, 1),
        }
        if organization == "internato" and block_info:
            week_entry["internato_block_label"] = block_info["label"]
            week_entry["internato_block_area"] = block_info["area"] or block_info["raw_area"]
        plan.append(week_entry)

    # Tópicos concluídos que não estão alocados em nenhuma semana da grade
    completed_outside_schedule = [
        t for t in all_topics if t.get("completed") and t["subtema"] not in scheduled_subtemas
    ]

    total_available_hours = sum(float(w["recommended_hours"]) for w in plan)

    scheduled_pending_count = sum(
        1 for w in plan for t in w.get("topics", []) if not t.get("completed")
    )
    target_pending_count = sum(1 for t in all_topics if not t.get("completed"))
    warning_msg = None
    if scheduled_pending_count < target_pending_count and pending_required_hours > total_available_hours:
        warning_msg = f"Você tem {round(total_available_hours)} horas disponíveis, mas precisa de {round(pending_required_hours)} horas para cobrir {'este plano' if intensive else 'todo o edital'}."

    result = {"plan": plan, "completed_topics": completed_outside_schedule}
    if warning_msg:
        result["warning"] = warning_msg
        result["total_required_hours"] = round(pending_required_hours)
        result["total_available_hours"] = round(total_available_hours)

    return result

