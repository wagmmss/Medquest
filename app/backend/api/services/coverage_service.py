"""Serviço de cobertura curricular por área e subtema (/coverage)."""
from __future__ import annotations

from .planner import _load_catalogs, get_normalized_area
from .stats_rollup import CANONICAL_AREA_ORDER, _get_cached_q_totals_map


def _get_planner_metadata():
    planner_meta, kat_subs, _ = _load_catalogs()
    return planner_meta, kat_subs


def _build_coverage_structure(planner_meta, kat_subs, q_map, u_map, summary_only: bool) -> dict:
    areas_dict: dict[str, dict] = {}
    for area_group in planner_meta:
        raw_area_name = area_group.get("area", "")
        area_name = get_normalized_area(raw_area_name)
        if area_name == "Outros":
            area_name = raw_area_name

        area_obj = areas_dict.setdefault(area_name, {
            "area": area_name,
            "n_questions": 0,
            "n_subtemas": 0,
            "answered_questions": 0,
            "attempts": 0,
            "correct": 0,
            "mastered": 0,
            "proficient": 0,
            "in_progress": 0,
            "not_started": 0,
            "subtemas": [],
            "high_yield_count": 0,
            "high_yield_mastered": 0,
        })

        for macro in area_group.get("macroThemes", []):
            theme = macro.get("theme", "")
            is_high_yield = macro.get("highYield", False)
            db_subs = macro.get("dbSubtemas", [theme])

            theme_theory = 0.0
            for s in db_subs:
                k = kat_subs.get(s, {})
                theme_theory += k.get("theory_hours", 1.5)
            theory_hours = round(theme_theory, 2)

            total_n_q = sum(q_map.get((area_name, s), 0) for s in db_subs)
            total_ans = sum(u_map.get((area_name, s), {}).get("answered", 0) for s in db_subs)
            total_att = sum(u_map.get((area_name, s), {}).get("attempts", 0) for s in db_subs)
            total_cor = sum(u_map.get((area_name, s), {}).get("correct", 0) for s in db_subs)

            accuracy = (total_cor / total_att) if total_att > 0 else None
            coverage_pct = (total_ans / total_n_q) if total_n_q > 0 else 0.0

            # Duas questões não são evidência suficiente para afirmar domínio de um tema.
            if total_ans == 0:
                status = "not_started"
            elif total_att >= 10 and accuracy is not None and accuracy >= 0.7 and coverage_pct >= 0.5:
                status = "mastered"
            elif total_att >= 5 and accuracy is not None and accuracy >= 0.7:
                status = "proficient"
            else:
                status = "in_progress"

            area_obj["n_questions"] += total_n_q
            area_obj["n_subtemas"] += 1
            area_obj["answered_questions"] += total_ans
            area_obj["attempts"] += total_att
            area_obj["correct"] += total_cor
            area_obj[status] += 1
            if is_high_yield:
                area_obj["high_yield_count"] += 1
                if status == "mastered":
                    area_obj["high_yield_mastered"] += 1

            # O resumo não devolve subtemas; evitar montar centenas de dicts reduz alocação e latência.
            if not summary_only:
                area_obj["subtemas"].append({
                    "subtema": theme,
                    "area": area_name,
                    "n_questions": total_n_q,
                    "answered": total_ans,
                    "attempts": total_att,
                    "correct": total_cor,
                    "accuracy": accuracy,
                    "coverage_pct": round(coverage_pct, 4),
                    "status": status,
                    "highYield": is_high_yield,
                    "theory_hours": theory_hours,
                })
    return areas_dict


def _format_coverage_response(areas_dict: dict, area_filter: str, summary_only: bool) -> tuple[list, list]:
    out = []
    for name in CANONICAL_AREA_ORDER:
        if name in areas_dict:
            a = areas_dict[name]
            a["accuracy"] = (a["correct"] / a["attempts"]) if a["attempts"] > 0 else None
            if not summary_only:
                a["subtemas"].sort(key=lambda s: (not s["highYield"], -s["n_questions"]))
            out.append(a)

    for k, a in areas_dict.items():
        if k not in CANONICAL_AREA_ORDER:
            a["accuracy"] = (a["correct"] / a["attempts"]) if a["attempts"] > 0 else None
            if not summary_only:
                a["subtemas"].sort(key=lambda s: (not s["highYield"], -s["n_questions"]))
            out.append(a)

    if area_filter:
        norm_filter = get_normalized_area(area_filter)
        out = [a for a in out if a["area"] == norm_filter or a["area"] == area_filter]

    summary_out = []
    if summary_only:
        for a in out:
            summary_out.append({
                "area": a["area"],
                "n_questions": a["n_questions"],
                "n_subtemas": a["n_subtemas"],
                "answered_questions": a["answered_questions"],
                "attempts": a["attempts"],
                "correct": a["correct"],
                "accuracy": a["accuracy"],
                "mastered": a["mastered"],
                "proficient": a["proficient"],
                "in_progress": a["in_progress"],
                "not_started": a["not_started"],
                "high_yield_count": a["high_yield_count"],
                "high_yield_mastered": a["high_yield_mastered"],
            })
    return out, summary_out


def _get_user_coverage_stats(db, user_id: str) -> dict[tuple[str, str], dict[str, int]]:
    user_rows = db.execute("""
        SELECT q.area, q.subtema,
               COUNT(DISTINCT a.question_id) AS answered,
               COUNT(a.id) AS attempts,
               COALESCE(SUM(a.is_correct), 0) AS correct
        FROM attempts a
        JOIN questions q ON q.id = a.question_id
        WHERE a.user_id = ? AND q.missing_alts = 0 AND q.area IS NOT NULL AND q.area != '' AND q.subtema IS NOT NULL AND q.subtema != ''
        GROUP BY q.area, q.subtema
    """, (user_id,)).fetchall()

    u_map: dict[tuple[str, str], dict[str, int]] = {}
    for r in user_rows:
        norm_a = get_normalized_area(r["area"])
        key = (norm_a, r["subtema"])
        if key not in u_map:
            u_map[key] = {
                "answered": int(r["answered"] or 0),
                "attempts": int(r["attempts"] or 0),
                "correct": int(r["correct"] or 0),
            }
        else:
            u_map[key]["answered"] += int(r["answered"] or 0)
            u_map[key]["attempts"] += int(r["attempts"] or 0)
            u_map[key]["correct"] += int(r["correct"] or 0)
    return u_map


def _get_coverage_data(
    db,
    user_id: str,
    area_filter: str = "",
    summary_only: bool = False,
    *,
    catalog_cache_fn=None,
) -> dict:
    planner_meta, kat_subs = _get_planner_metadata()
    q_map = _get_cached_q_totals_map(db, catalog_cache_fn=catalog_cache_fn)
    u_map = _get_user_coverage_stats(db, user_id)
    areas_dict = _build_coverage_structure(planner_meta, kat_subs, q_map, u_map, summary_only)
    out, summary_out = _format_coverage_response(areas_dict, area_filter, summary_only)
    if summary_only:
        return {"areas": summary_out, "summary": True}
    return {"areas": out}
