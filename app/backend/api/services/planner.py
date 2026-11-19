import json
import math
import os
from datetime import datetime, timedelta
from functools import lru_cache
from api.internato_config import RODIZIOS_TURMA_J

USP_WEIGHTS = {
    "Clínica Médica": 0.30,
    "Cirurgia": 0.20,
    "Pediatria": 0.15,
    "Ginecologia e Obstetrícia": 0.15,
    "Preventiva": 0.20
}

DEFAULT_PRACTICE_HOURS_PER_SUBTEMA = 2.0


def _resolve_data_path(filename):
    """Resolve o caminho de um arquivo JSON procurando em data/ e scripts/."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    candidate_data = os.path.join(base_dir, "data", filename)
    if os.path.exists(candidate_data):
        return candidate_data
    candidate_scripts = os.path.join(base_dir, "scripts", filename)
    if os.path.exists(candidate_scripts):
        return candidate_scripts
    return candidate_data


def get_normalized_area(raw_area):
    if not raw_area:
        return "Outros"
    # Using substrings to avoid encoding issues with the SQLite output
    if "Cirurgia" in raw_area:
        return "Cirurgia"
    if "nica" in raw_area:
        return "Clínica Médica"
    if "Ginecologia" in raw_area:
        return "Ginecologia e Obstetrícia"
    if "Preventiva" in raw_area:
        return "Preventiva"
    if "Pediatria" in raw_area:
        return "Pediatria"
    return "Outros"


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


@lru_cache(maxsize=1)
def _load_catalogs():
    # Carrega o mesmo catálogo pedagógico exibido no frontend.
    planner_data_path = _resolve_data_path("plannerData.json")
    try:
        with open(planner_data_path, "r", encoding="utf-8") as f:
            planner_meta = json.load(f)
    except Exception:
        planner_meta = []

    duration_catalog_path = _resolve_data_path("katomartCourseDurations.json")
    try:
        with open(duration_catalog_path, "r", encoding="utf-8") as f:
            duration_catalog = json.load(f)
    except Exception:
        duration_catalog = {}

    katomart_subtemas = duration_catalog.get("subtemas", {})
    practice_hours_per_subtema = duration_catalog.get("source", {}).get(
        "practice_hours_per_subtema",
        DEFAULT_PRACTICE_HOURS_PER_SUBTEMA,
    )
    return planner_meta, katomart_subtemas, practice_hours_per_subtema


def _build_meta_dict(planner_meta, katomart_subtemas):
    # Cria o catálogo canônico de subtemas para fácil acesso. O banco pode
    # conter classificações históricas, incompletas ou ainda não migradas; ele
    # só deve complementar as estatísticas dos temas, nunca definir o edital.
    meta_dict = {}
    for area_group in planner_meta:
        canonical_area = get_normalized_area(area_group.get("area"))
        for macro in area_group.get("macroThemes", []):
            is_high_yield = macro.get("highYield", False)
            # Fallback pedagógico para subtemas sem correspondência segura no
            # catálogo local de aulas do Katomart.
            fallback_theory_hours = max(1.0, len(macro.get("details", [])) * 0.25)

            for db_subtema in macro.get("dbSubtemas", []):
                course_match = katomart_subtemas.get(db_subtema)
                meta_dict[db_subtema] = {
                    "area": canonical_area,
                    "highYield": is_high_yield,
                    "theory_hours": (
                        course_match.get("theory_hours", fallback_theory_hours)
                        if course_match
                        else fallback_theory_hours
                    ),
                    "theory_source": "curriculum" if course_match else "pedagogical_estimate",
                    "course_module": course_match.get("module") if course_match else None,
                }
    return meta_dict


def _consolidate_row_stats(rows, meta_dict):
    # Consolida as estatísticas do banco apenas para os 170 temas do catálogo.
    # Isso também protege contra a mesma classificação aparecer em mais de uma
    # área durante uma migração de dados.
    row_stats = {
        subtema: {"q_count": 0, "subtopics": []}
        for subtema in meta_dict
    }
    for row in rows:
        subtema = row["subtema"]
        if subtema not in row_stats:
            continue
        stats = row_stats[subtema]
        try:
            stats["q_count"] += int(row["q_count"] or 0)
        except (TypeError, ValueError):
            pass
        topics = row.get("topics") if isinstance(row, dict) else (row["topics"] if "topics" in row.keys() else None)
        if topics:
            stats["subtopics"].extend(topic for topic in str(topics).split(",") if topic)
    return row_stats


def _build_topic_item(
    subtema,
    meta,
    stats,
    prog,
    practice_hours_per_subtema,
    adaptive_signals=None,
    completed_subtemas=None,
):
    norm_area = meta["area"]
    q_count = stats["q_count"] if stats else 0

    prog_dict = dict(prog) if prog else {}
    ans_count = prog_dict.get("ans_count") or 0
    attempts = prog_dict.get("attempts") or 0
    correct_count = prog_dict.get("correct_count") or 0
    acc = (correct_count / attempts) if attempts > 0 else 0

    remaining_q = max(0, q_count - ans_count)

    theory_hours = meta["theory_hours"]
    practice_hours = practice_hours_per_subtema
    total_topic_hours = theory_hours + practice_hours

    # Priority score: High Yield = 100, plus area weight
    weight = USP_WEIGHTS.get(norm_area, 0.1)
    priority = 100 if meta["highYield"] else 0
    priority += weight * 10

    priority_reasons = []
    if adaptive_signals is not None:
        sig = adaptive_signals.get(subtema)
        if sig:
            reasons = sig.get("reasons", [])
            if reasons:
                # Sinais adaptativos com evidências reais de dificuldade ou revisão pendente
                score = float(sig.get("priority_score", 0.0) or 0.0)
                priority += round(score * 50.0, 2)
                priority_reasons = list(reasons)
    else:
        # Fallback retrocompatível para chamadas sem sinais adaptativos
        if attempts >= 3 and acc < 0.6:
            priority += 50
            priority_reasons.append("low_accuracy")

    # Tier and explanation
    if priority >= 130:
        priority_tier = "Diamante"
    elif priority >= 100:
        priority_tier = "Alta"
    elif priority >= 50:
        priority_tier = "Média"
    else:
        priority_tier = "Normal"

    explanation_parts = []
    if meta["highYield"]:
        explanation_parts.append("é de alto rendimento nas provas")
    if "low_accuracy" in priority_reasons:
        explanation_parts.append("houve baixo desempenho recente")
    if "reviews_due" in priority_reasons:
        explanation_parts.append("há revisões vencidas")
    if "memory_at_risk" in priority_reasons:
        explanation_parts.append("há risco de esquecimento")
    if "low_coverage" in priority_reasons:
        explanation_parts.append("você ainda não cobriu este assunto")

    if explanation_parts:
        if len(explanation_parts) > 1:
            exp = ", ".join(explanation_parts[:-1]) + " e " + explanation_parts[-1]
        else:
            exp = explanation_parts[0]
        priority_explanation = f"Recomendado porque {exp}."
    else:
        priority_explanation = "Recomendado para cobrir o edital equilibradamente."

    topic_obj = {
        "area": norm_area,
        "subtema": subtema,
        "subtopics": stats["subtopics"] if stats else [],
        "questions_available": remaining_q,
        "estimated_theory_hours": round(theory_hours, 2),
        "estimated_practice_hours": round(practice_hours, 2),
        "estimated_hours": round(total_topic_hours, 2),
        "theory_source": meta["theory_source"],
        "course_module": meta["course_module"],
        "priority": round(priority, 2),
        "priority_reasons": priority_reasons,
        "priority_tier": priority_tier,
        "priority_explanation": priority_explanation,
        "completed": bool(completed_subtemas and subtema in completed_subtemas),
    }
    return topic_obj, total_topic_hours


def _prepare_topics(
    meta_dict,
    row_stats,
    user_progress,
    intensive,
    practice_hours_per_subtema,
    adaptive_signals=None,
    completed_subtemas=None,
):
    # Prepara exatamente os tópicos canônicos, calculando as horas de cada um.
    all_topics = []
    total_required_hours = 0.0
    pending_required_hours = 0.0

    if user_progress is None:
        user_progress = {}

    for subtema, meta in meta_dict.items():
        if intensive and not meta["highYield"]:
            continue

        stats = row_stats[subtema]
        prog = user_progress.get(subtema)
        topic_obj, topic_hours = _build_topic_item(
            subtema,
            meta,
            stats,
            prog,
            practice_hours_per_subtema,
            adaptive_signals,
            completed_subtemas=completed_subtemas,
        )
        total_required_hours += topic_hours
        if not topic_obj["completed"]:
            pending_required_hours += topic_hours
        all_topics.append(topic_obj)

    # Sort topics by priority (descending)
    all_topics.sort(key=lambda x: x["priority"], reverse=True)
    return all_topics, total_required_hours, pending_required_hours


def _normalize_internato_area(raw_area):
    if not raw_area:
        return None
    lower = raw_area.lower()
    if "intensiva" in lower or "especialidades" in lower:
        return "Clínica Médica"
    norm = get_normalized_area(raw_area)
    return None if norm == "Outros" else norm


def get_area_for_date(date_obj, internato_blocks=None):
    blocks = internato_blocks if internato_blocks is not None else RODIZIOS_TURMA_J
    for bloco in blocks:
        try:
            inicio = datetime.strptime(bloco["start"], "%Y-%m-%d")
            fim = datetime.strptime(bloco["end"], "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        except (KeyError, ValueError, TypeError):
            continue
        if inicio <= date_obj <= fim:
            return _normalize_internato_area(bloco.get("area"))
    return None


def _pick_first_fitting_topic(area_topics, current_week_hours, hours_per_week):
    for idx, t in enumerate(area_topics):
        if current_week_hours == 0 or (current_week_hours + t["estimated_hours"]) <= (hours_per_week + 1.0):
            return idx
    return -1


def _distribute_completed_topics(plan, completed_topics, organization, internato_blocks, hours_per_week):
    """Insere aulas já concluídas nas semanas sem consumir horas pendentes."""
    if not plan or not completed_topics:
        return

    num_weeks = len(plan)
    completed_hours_per_week = [0.0] * num_weeks

    # No modo internato, tenta posicionar cada aula concluída em uma semana cujo bloco corresponda à sua área
    week_area_cache = [
        get_area_for_date(datetime.fromisoformat(w["date"]), internato_blocks)
        if organization == "internato" else None
        for w in plan
    ]

    for idx_t, topic in enumerate(completed_topics):
        target_week_idx = None

        if organization == "internato":
            matching_indices = [i for i, a in enumerate(week_area_cache) if a == topic["area"]]
            if matching_indices:
                # Escolhe a semana do bloco com menor carga de concluídos até agora
                target_week_idx = min(matching_indices, key=lambda i: (completed_hours_per_week[i], i))

        if target_week_idx is None:
            # Distribuição equilibrada pelas semanas (preferindo semanas abaixo da carga e com menos concluídos)
            start_cursor = idx_t % num_weeks
            ordered_indices = [
                (start_cursor + offset) % num_weeks for offset in range(num_weeks)
            ]
            under_cap = [i for i in ordered_indices if completed_hours_per_week[i] < hours_per_week]
            candidates = under_cap if under_cap else ordered_indices
            target_week_idx = min(candidates, key=lambda i: completed_hours_per_week[i])

        plan[target_week_idx]["topics"].append(topic)
        completed_hours_per_week[target_week_idx] += topic["estimated_hours"]


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

    plan = []
    area_rotation_cursor = 0

    for week in range(1, total_weeks + 1):
        week_topics = []
        current_week_hours = 0.0
        week_date = start_date + timedelta(weeks=week - 1)

        area_foco = (
            get_area_for_date(week_date, internato_blocks)
            if organization == "internato"
            else None
        )

        while current_week_hours < hours_per_week:
            active_areas = [a for a, t_list in topics_by_area.items() if len(t_list) > 0]
            if not active_areas:
                break

            selected_area = None
            if organization == "internato" and area_foco and area_foco in active_areas:
                selected_area = area_foco
            else:
                # Modo geral (ou fallback sem bloco): intercala áreas proporcionalmente ao volume pendente,
                # priorizando áreas com tópicos de alto rendimento para evitar concentração no fim.
                hy_active_areas = [a for a in active_areas if topics_by_area[a][0]["priority"] >= 100]
                candidates = hy_active_areas if hy_active_areas else active_areas
                candidates.sort(key=lambda a: len(topics_by_area[a]), reverse=True)
                selected_area = candidates[0]

            candidate_area = None
            candidate_idx = _pick_first_fitting_topic(
                topics_by_area[selected_area], current_week_hours, hours_per_week
            )
            if candidate_idx != -1:
                candidate_area = selected_area
            else:
                for a in active_areas:
                    if a == selected_area:
                        continue
                    idx = _pick_first_fitting_topic(
                        topics_by_area[a], current_week_hours, hours_per_week
                    )
                    if idx != -1:
                        candidate_area = a
                        candidate_idx = idx
                        break

            if candidate_area is not None:
                topic = topics_by_area[candidate_area].pop(candidate_idx)
                week_topics.append(topic)
                current_week_hours += topic["estimated_hours"]
            else:
                break

        plan.append({
            "week": week,
            "date": week_date.isoformat(),
            "topics": week_topics,
            "recommended_hours": hours_per_week,
            "allocated_hours": round(current_week_hours, 1),
        })

    _distribute_completed_topics(plan, completed_topics, organization, internato_blocks, hours_per_week)
    return plan


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

    all_topics, _total_required_hours, pending_required_hours = _prepare_topics(
        meta_dict,
        row_stats,
        user_progress,
        intensive,
        practice_hours_per_subtema,
        adaptive_signals=adaptive_signals,
        completed_subtemas=completed_subtemas,
    )

    plan = _build_weekly_plan(
        all_topics,
        start_date,
        total_weeks,
        hours_per_week,
        organization=organization,
        internato_blocks=internato_blocks,
    )

    total_available_hours = total_weeks * hours_per_week
    scheduled_pending_count = sum(
        1 for w in plan for t in w.get("topics", []) if not t.get("completed")
    )
    target_pending_count = sum(1 for t in all_topics if not t.get("completed"))
    warning_msg = None
    if scheduled_pending_count < target_pending_count and pending_required_hours > total_available_hours:
        warning_msg = f"Você tem {total_available_hours} horas disponíveis, mas precisa de {round(pending_required_hours)} horas para cobrir {'este plano' if intensive else 'todo o edital'}."

    result = {"plan": plan}
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
    )

    weeks_map = {}
    for r in schedule_rows:
        w_num = int(r["week"])
        weeks_map.setdefault(w_num, []).append(r["subtema"])

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
        for subtema in weeks_map.get(week_num, []):
            meta = meta_dict.get(subtema)
            if not meta:
                continue
            stats = row_stats.get(subtema, {"q_count": 0, "subtopics": []})
            prog = user_progress.get(subtema)
            topic_obj, topic_hours = _build_topic_item(
                subtema,
                meta,
                stats,
                prog,
                practice_hours_per_subtema,
                adaptive_signals,
                completed_subtemas=completed_subtemas,
            )
            if not topic_obj["completed"]:
                current_week_hours += topic_hours
            week_topics.append(topic_obj)

        plan.append({
            "week": week_num,
            "date": (start_date + timedelta(weeks=week_num - 1)).isoformat(),
            "topics": week_topics,
            "recommended_hours": hours_per_week,
            "allocated_hours": round(current_week_hours, 1),
        })

    total_available_hours = None
    if exam_date_str:
        _, total_weeks, err = _parse_dates_and_weeks(start_date_str, exam_date_str)
        if not err and total_weeks:
            total_available_hours = total_weeks * hours_per_week
    if total_available_hours is None:
        total_available_hours = len(plan) * hours_per_week

    scheduled_pending_count = sum(
        1 for w in plan for t in w.get("topics", []) if not t.get("completed")
    )
    target_pending_count = sum(1 for t in all_topics if not t.get("completed"))
    warning_msg = None
    if scheduled_pending_count < target_pending_count and pending_required_hours > total_available_hours:
        warning_msg = f"Você tem {total_available_hours} horas disponíveis, mas precisa de {round(pending_required_hours)} horas para cobrir {'este plano' if intensive else 'todo o edital'}."

    result = {"plan": plan}
    if warning_msg:
        result["warning"] = warning_msg
        result["total_required_hours"] = round(pending_required_hours)
        result["total_available_hours"] = round(total_available_hours)

    return result

