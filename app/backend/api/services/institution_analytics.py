"""Serviços de prontidão por banca (Empirical Bayes), radar comparativo e intervalo de Wilson."""
from __future__ import annotations

import math
from urllib.parse import urlencode

from ..cache import SimpleTTLCache
from ..candidate_benchmarks import calculate_competitive_analysis, get_institution_benchmark
from ..edital_profiles import (
    ALLOWED_ANALYSIS_INSTITUTIONS,
    CANONICAL_AREAS,
    get_canonical_institution,
    get_edital_profile,
    resolve_institution_codes,
)
from ..observability import emit
from .psychometrics import calculate_bayesian_readiness
from .stats_rollup import (
    CANONICAL_AREA_ORDER,
    CANONICAL_INSTITUTION_LABELS,
    _db_cache_scope,
    _get_cached_raw_subtema_counts,
    _use_catalog_cache,
)

_institution_area_totals_cache = SimpleTTLCache(21600)

_WILSON_Z_CACHE = {
    0.80: 1.281552,
    0.90: 1.644854,
    0.95: 1.959964,
    0.99: 2.575829,
}


def _normal_ppf(confidence: float) -> float:
    """Retorna o z-score bilateral para nível de confiança (0 < confidence < 1)."""
    rounded = round(float(confidence), 4)
    if rounded in _WILSON_Z_CACHE:
        return _WILSON_Z_CACHE[rounded]
    target = 0.5 + (max(0.01, min(0.9999, float(confidence))) / 2.0)
    lo, hi = 0.0, 6.0
    sqrt2 = math.sqrt(2.0)
    for _ in range(50):
        mid = (lo + hi) * 0.5
        cdf = 0.5 * (1.0 + math.erf(mid / sqrt2))
        if cdf < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) * 0.5


def calculate_wilson_ci(k: int, n: int, confidence: float = 0.95) -> tuple[float | None, float | None]:
    """Calcula o Intervalo de Confiança de Wilson para uma proporção binomial."""
    if n <= 0:
        return None, None

    z = _normal_ppf(confidence)
    p_hat = k / n
    z2 = z * z
    denominator = 1.0 + (z2 / n)
    center = (p_hat + (z2 / (2.0 * n))) / denominator
    margin = (z / denominator) * math.sqrt((p_hat * (1.0 - p_hat) / n) + (z2 / (4.0 * n * n)))

    lower = max(0.0, round(center - margin, 4))
    upper = min(1.0, round(center + margin, 4))
    return lower, upper


def get_sample_status(attempts: int) -> str:
    """Classifica a robustez estatística da amostra (<20 insufficient, 20-49 forming, >=50 reliable)."""
    if attempts < 20:
        return "insufficient"
    if attempts < 50:
        return "forming"
    return "reliable"


def _get_available_questions_by_area(
    db, institution_code: str | None = None, *, catalog_cache_fn=None
) -> dict[str, int]:
    use_cache = _use_catalog_cache(catalog_cache_fn)
    cache_key = (institution_code or "__all__", _db_cache_scope())
    if use_cache:
        cached = _institution_area_totals_cache.get(cache_key)
        if cached is not None:
            return cached

    aliases = resolve_institution_codes(institution_code) if institution_code else []
    if aliases:
        placeholders = ",".join("?" * len(aliases))
        clause = f"AND institution_code IN ({placeholders})"
        params = list(aliases)
    else:
        clause = ""
        params = []

    rows = db.execute(f"""
        SELECT area, COUNT(id) AS available
        FROM questions
        WHERE missing_alts = 0 AND area IS NOT NULL AND area != ''
              {clause}
        GROUP BY area
    """, params).fetchall()

    totals = {row["area"]: row["available"] for row in rows}
    if use_cache:
        _institution_area_totals_cache.set(cache_key, totals)
    return totals


def _get_cached_institution_subtemas(
    db, institution_code: str | None, aliases: list[str] | None = None, *, catalog_cache_fn=None
) -> list[tuple[str, str, int]]:
    """Retorna contagens de subtemas por área para uma banca, com cache de catálogo."""
    if not aliases:
        return _get_cached_raw_subtema_counts(db, catalog_cache_fn=catalog_cache_fn)

    use_cache = _use_catalog_cache(catalog_cache_fn)
    cache_key = ("inst_subtemas", institution_code or "__all__", _db_cache_scope())
    if use_cache:
        cached = _institution_area_totals_cache.get(cache_key)
        if cached is not None:
            return cached

    placeholders = ",".join("?" * len(aliases))
    rows = db.execute(f"""
        SELECT q.area, q.subtema, COUNT(q.id) AS sub_available
        FROM questions q
        WHERE q.missing_alts = 0 AND q.area IS NOT NULL AND q.area != ''
              AND q.institution_code IN ({placeholders})
              AND q.subtema IS NOT NULL AND q.subtema != ''
        GROUP BY q.area, q.subtema
    """, list(aliases)).fetchall()
    counts = [(r["area"], r["subtema"], int(r["sub_available"] or 0)) for r in rows]
    if use_cache:
        _institution_area_totals_cache.set(cache_key, counts)
    return counts


def _get_user_area_attempts(db, user_id: str, institution_code: str | None = None) -> dict[str, dict]:
    aliases = resolve_institution_codes(institution_code) if institution_code else []
    if aliases:
        placeholders = ",".join("?" * len(aliases))
        clause = f"AND q.institution_code IN ({placeholders})"
        params = [user_id] + list(aliases)
    else:
        clause = ""
        params = [user_id]

    rows = db.execute(f"""
        SELECT q.area,
               COUNT(DISTINCT a.question_id) AS answered,
               COUNT(a.id) AS attempts,
               COALESCE(SUM(a.is_correct), 0) AS correct
        FROM attempts a
        JOIN questions q ON q.id = a.question_id
        WHERE a.user_id = ? AND q.missing_alts = 0 AND q.area IS NOT NULL AND q.area != ''
              {clause}
        GROUP BY q.area
    """, params).fetchall()

    return {row["area"]: dict(row) for row in rows}


def _fetch_area_records(
    db, user_id: str, institution_code: str | None = None, *, catalog_cache_fn=None
) -> list[dict]:
    avail_map = _get_available_questions_by_area(db, institution_code, catalog_cache_fn=catalog_cache_fn)
    user_map = _get_user_area_attempts(db, user_id, institution_code)

    all_areas = set(avail_map.keys()) | set(user_map.keys()) | set(CANONICAL_AREAS)
    records = []
    for area in all_areas:
        u = user_map.get(area, {})
        records.append({
            "area": area,
            "available": avail_map.get(area, 0),
            "answered": u.get("answered", 0),
            "attempts": u.get("attempts", 0),
            "correct": u.get("correct", 0),
        })
    records.sort(key=lambda r: r["available"], reverse=True)
    return records


def _get_exam_readiness_data(
    db,
    user_id: str,
    raw_institution: str = "",
    emit_event: bool = True,
    *,
    emit_fn=None,
    catalog_cache_fn=None,
) -> dict:
    raw_institution = (raw_institution or "").strip()[:64]
    canonical = get_canonical_institution(raw_institution)
    if canonical in ALLOWED_ANALYSIS_INSTITUTIONS:
        institution = canonical
    elif raw_institution in ALLOWED_ANALYSIS_INSTITUTIONS:
        institution = raw_institution
    else:
        institution = "USP-SP"

    area_records = _fetch_area_records(db, user_id, institution, catalog_cache_fn=catalog_cache_fn)
    profile = get_edital_profile(institution)
    bayesian_calc = calculate_bayesian_readiness(area_records, profile, institution_code=institution)

    aliases = resolve_institution_codes(institution) if institution else []
    if aliases:
        placeholders = ",".join("?" * len(aliases))
        clause = f"AND q.institution_code IN ({placeholders})"
        params = [user_id] + list(aliases)
    else:
        clause = ""
        params = [user_id]

    attempts_rows = db.execute(f"""
        SELECT a.question_id, a.is_correct
        FROM attempts a
        JOIN questions q ON q.id = a.question_id
        WHERE a.user_id = ? AND q.missing_alts = 0 {clause}
    """, params).fetchall()

    attempts_records = [dict(r) for r in attempts_rows]
    competitive_analysis = calculate_competitive_analysis(attempts_records, institution)

    areas = bayesian_calc["enriched_areas"]
    total_available = sum(item["available"] for item in areas)
    total_answered = sum(item["answered"] for item in areas)

    if emit_event:
        (emit_fn or emit)(
            "exam_readiness_viewed",
            profile_status=profile.status,
            evidence_status=bayesian_calc["evidence_status"],
        )

    return {
        "institution": institution,
        "institution_label": profile.institution_label,
        "coverage": round(total_answered / total_available, 4) if total_available else 0,
        "answered": total_answered,
        "available": total_available,
        "readiness_score": bayesian_calc["readiness_score"],
        "ci_lower": bayesian_calc["ci_lower"],
        "ci_upper": bayesian_calc["ci_upper"],
        "evidence_status": bayesian_calc["evidence_status"],
        "candidate_mean": competitive_analysis.get("candidate_mean"),
        "competitive_delta": competitive_analysis.get("competitive_delta"),
        "competitive_analysis": competitive_analysis,
        "edital_profile": profile.model_dump(),
        "areas": areas,
        "key_factors": bayesian_calc["key_factors"],
        "limitations": bayesian_calc["limitations"],
        "disclaimer": "Prontidão estimada calculada via modelo Empirical Bayes ponderado por edital e calibrado na concorrência da banca.",
    }


def _get_institution_label(db, institution_code: str | None) -> str:
    """Retorna o rótulo de uma instituição."""
    if not institution_code:
        return "Desempenho Geral"

    canon = get_canonical_institution(institution_code) or institution_code
    if canon in CANONICAL_INSTITUTION_LABELS:
        return CANONICAL_INSTITUTION_LABELS[canon]

    l_row = db.execute(
        "SELECT institution_label FROM questions WHERE institution_code = ? LIMIT 1",
        (institution_code,),
    ).fetchone()
    return l_row["institution_label"] if l_row else institution_code


def _fetch_all_priority_topics(
    db,
    user_id: str,
    institution_code: str | None,
    inst_clause: str,
    aliases: list[str] | None = None,
    *,
    catalog_cache_fn=None,
) -> dict[str, list[dict]]:
    """Busca em lote os tópicos prioritários para todas as áreas baseados nas estatísticas de desempenho."""
    inst_params = []
    if inst_clause and "?" in inst_clause:
        if aliases:
            inst_params.extend(aliases)
        elif institution_code:
            inst_params.append(institution_code)

    catalog_subtemas = _get_cached_institution_subtemas(
        db,
        institution_code,
        aliases or ([institution_code] if inst_params else None),
        catalog_cache_fn=catalog_cache_fn,
    )

    user_rows = db.execute(f"""
        SELECT
            q.area,
            q.subtema,
            COUNT(DISTINCT a.question_id) AS sub_answered,
            COUNT(a.id) AS sub_attempts,
            COALESCE(SUM(a.is_correct), 0) AS sub_correct
        FROM attempts a
        JOIN questions q ON q.id = a.question_id
        WHERE a.user_id = ? AND q.missing_alts = 0 AND q.area IS NOT NULL AND q.area != '' {inst_clause}
              AND q.subtema IS NOT NULL AND q.subtema != ''
        GROUP BY q.area, q.subtema
    """, [user_id, *inst_params]).fetchall()
    user_map = {
        (r["area"], r["subtema"]): (
            int(r["sub_answered"] or 0),
            int(r["sub_attempts"] or 0),
            int(r["sub_correct"] or 0),
        )
        for r in user_rows
    }

    by_area: dict[str, list[dict]] = {}
    for area_name, subtema, sub_available in catalog_subtemas:
        sub_answered, sub_attempts, sub_correct = user_map.get((area_name, subtema), (0, 0, 0))
        by_area.setdefault(area_name, []).append({
            "area": area_name,
            "subtema": subtema,
            "sub_available": sub_available,
            "sub_answered": sub_answered,
            "sub_attempts": sub_attempts,
            "sub_correct": sub_correct,
        })

    sub_rows = []
    for area_name in sorted(by_area.keys()):
        candidates = sorted(
            by_area[area_name],
            key=lambda item: (
                0 if item["sub_attempts"] == 0 else (1 if (item["sub_correct"] / item["sub_attempts"]) < 0.65 else 2),
                (item["sub_correct"] / item["sub_attempts"]) if item["sub_attempts"] > 0 else 0.0,
                -item["sub_available"],
                item["subtema"],
            ),
        )
        sub_rows.extend(candidates[:3])

    priority_map: dict[str, list[dict]] = {}
    for sr in sub_rows:
        area_name = sr["area"]
        s_att = sr["sub_attempts"]
        s_cor = sr["sub_correct"]
        s_acc = round(s_cor / s_att, 4) if s_att > 0 else None

        if s_att == 0:
            gap_type = "unanswered"
        elif s_acc is not None and s_acc < 0.65:
            gap_type = "low_accuracy"
        else:
            gap_type = "low_coverage"

        study_params = {"area": area_name, "subtema": sr["subtema"], "status": "all", "limit": 20}
        simulado_params = {"area": area_name}
        if institution_code:
            study_params["institution"] = institution_code
            simulado_params["institutions"] = institution_code

        priority_map.setdefault(area_name, []).append({
            "subtema": sr["subtema"],
            "available": sr["sub_available"],
            "answered": sr["sub_answered"],
            "attempts": s_att,
            "correct": s_cor,
            "accuracy": s_acc,
            "gap_type": gap_type,
            "study_url": f"/estudar?{urlencode(study_params)}",
            "simulado_url": f"/simulado?{urlencode(simulado_params)}",
            "review_url": "/estudar?status=srs_due",
        })

    return priority_map


def _build_institution_stats(
    db,
    user_id: str,
    institution_code: str | None = None,
    include_priority: bool = True,
    *,
    catalog_cache_fn=None,
):
    canon = get_canonical_institution(institution_code) if institution_code else None
    target_code = canon or institution_code

    avail_map = _get_available_questions_by_area(db, target_code, catalog_cache_fn=catalog_cache_fn)
    user_map = _get_user_area_attempts(db, user_id, target_code)

    bench = get_institution_benchmark(target_code)
    bench_areas = bench.get("areas", {})
    cand_overall = bench.get("overall_candidate_accuracy", 0.695)

    aliases = resolve_institution_codes(target_code) if target_code else []
    if aliases:
        placeholders = ",".join("?" * len(aliases))
        inst_clause = f"AND q.institution_code IN ({placeholders})"
    else:
        inst_clause = ""
    label = _get_institution_label(db, target_code)
    priority_map = (
        _fetch_all_priority_topics(
            db, user_id, target_code, inst_clause, aliases=aliases, catalog_cache_fn=catalog_cache_fn
        )
        if include_priority
        else {}
    )

    areas = []
    total_available = 0
    total_answered = 0
    total_attempts = 0
    total_correct = 0

    for area_name in CANONICAL_AREA_ORDER:
        u = user_map.get(area_name, {})
        avail = avail_map.get(area_name, 0)
        ans = u.get("answered", 0)
        att = u.get("attempts", 0)
        cor = u.get("correct", 0)

        total_available += avail
        total_answered += ans
        total_attempts += att
        total_correct += cor

        acc = round(cor / att, 4) if att > 0 else None
        cov = round(ans / avail, 4) if avail > 0 else 0.0
        ci_lower, ci_upper = calculate_wilson_ci(cor, att)
        sample_status = get_sample_status(att)

        c_acc = bench_areas.get(area_name, {}).get("candidate_accuracy", 0.70)
        c_delta = round(acc - c_acc, 4) if acc is not None else None

        areas.append({
            "area": area_name,
            "available": avail,
            "answered": ans,
            "coverage": cov,
            "attempts": att,
            "correct": cor,
            "accuracy": acc,
            "candidate_accuracy": round(c_acc, 4),
            "competitive_delta": c_delta,
            "ci_lower": ci_lower,
            "ci_upper": ci_upper,
            "sample_status": sample_status,
            "priority_topics": priority_map.get(area_name, []),
        })

    overall_acc = round(total_correct / total_attempts, 4) if total_attempts > 0 else None
    overall_cov = round(total_answered / total_available, 4) if total_available > 0 else 0.0
    overall_ci_lower, overall_ci_upper = calculate_wilson_ci(total_correct, total_attempts)
    overall_sample_status = get_sample_status(total_attempts)
    overall_cand_delta = round(overall_acc - cand_overall, 4) if overall_acc is not None else None

    return {
        "code": target_code,
        "label": label,
        "total_available": total_available,
        "total_answered": total_answered,
        "coverage": overall_cov,
        "total_attempts": total_attempts,
        "total_correct": total_correct,
        "accuracy": overall_acc,
        "candidate_accuracy": round(cand_overall, 4),
        "competitive_delta": overall_cand_delta,
        "ci_lower": overall_ci_lower,
        "ci_upper": overall_ci_upper,
        "sample_status": overall_sample_status,
        "areas": areas,
    }


def _get_institution_radar_data(
    db,
    user_id: str,
    raw_inst: str = "",
    raw_compare: str = "",
    emit_event: bool = True,
    config: dict | None = None,
    *,
    emit_fn=None,
    catalog_cache_fn=None,
) -> dict:
    raw_inst = (raw_inst or "").strip()[:64]
    raw_compare = (raw_compare or "").strip()[:64]

    if raw_inst in ("Todas as Bancas", "TODAS") or "," in raw_inst:
        raw_inst = raw_inst.split(",")[0].strip() if "," in raw_inst else ""
    if raw_compare in ("Todas as Bancas", "TODAS") or "," in raw_compare:
        raw_compare = raw_compare.split(",")[0].strip() if "," in raw_compare else ""

    canon_inst = get_canonical_institution(raw_inst)
    institution = (
        canon_inst
        if canon_inst in ALLOWED_ANALYSIS_INSTITUTIONS
        else (raw_inst if raw_inst in ALLOWED_ANALYSIS_INSTITUTIONS else "")
    )

    canon_compare = get_canonical_institution(raw_compare)
    compare_institution = (
        canon_compare
        if canon_compare in ALLOWED_ANALYSIS_INSTITUTIONS
        else (raw_compare if raw_compare in ALLOWED_ANALYSIS_INSTITUTIONS else "")
    )

    if not institution:
        allowed_aliases = []
        for a_code in ALLOWED_ANALYSIS_INSTITUTIONS:
            allowed_aliases.extend(resolve_institution_codes(a_code))
        placeholders = ",".join("?" * len(allowed_aliases))
        top_inst_row = db.execute(f"""
            SELECT q.institution_code, COUNT(a.id) AS n
            FROM attempts a
            JOIN questions q ON q.id = a.question_id
            WHERE a.user_id = ? AND q.institution_code IN ({placeholders})
            GROUP BY q.institution_code
            ORDER BY n DESC
            LIMIT 1
        """, [user_id] + allowed_aliases).fetchone()
        if top_inst_row:
            institution = get_canonical_institution(top_inst_row["institution_code"]) or top_inst_row["institution_code"]
        else:
            if config is not None:
                target_inst_val = config.get("target_institution")
            else:
                cfg_row = db.execute("SELECT target_institution FROM planner_config WHERE user_id = ?", (user_id,)).fetchone()
                target_inst_val = cfg_row["target_institution"] if cfg_row else None
            if target_inst_val:
                planner_inst = target_inst_val.strip().split(",")[0].strip()
                canonical_planner = get_canonical_institution(planner_inst)
                institution = canonical_planner if canonical_planner in ALLOWED_ANALYSIS_INSTITUTIONS else "USP-SP"
            else:
                institution = "USP-SP"

    primary_data = _build_institution_stats(
        db, user_id, institution, include_priority=True, catalog_cache_fn=catalog_cache_fn
    )

    if raw_compare.upper() in ("CANDIDATES", "CONCORRENCIA", "BENCHMARK"):
        bench = get_institution_benchmark(institution)
        bench_areas = bench.get("areas", {})
        cand_areas = []
        for area_name in CANONICAL_AREA_ORDER:
            c_acc = bench_areas.get(area_name, {}).get("candidate_accuracy", 0.70)
            q_cnt = bench_areas.get(area_name, {}).get("question_count", 0)
            cand_areas.append({
                "area": area_name,
                "available": q_cnt,
                "answered": q_cnt,
                "coverage": 1.0,
                "attempts": q_cnt,
                "correct": int(round(c_acc * q_cnt)),
                "accuracy": round(c_acc, 4),
                "ci_lower": round(c_acc, 4),
                "ci_upper": round(c_acc, 4),
                "candidate_accuracy": round(c_acc, 4),
                "competitive_delta": 0.0,
                "sample_status": "reliable",
                "priority_topics": [],
            })
        cand_overall = bench.get("overall_candidate_accuracy", 0.695)
        total_q = bench.get("total_questions", 0)
        comparison_data = {
            "type": "candidates",
            "code": f"{institution}_CANDIDATES",
            "label": f"Média Candidatos ({primary_data['label']})",
            "total_available": total_q,
            "total_answered": total_q,
            "coverage": 1.0,
            "total_attempts": total_q,
            "total_correct": int(round(cand_overall * total_q)),
            "accuracy": round(cand_overall, 4),
            "ci_lower": round(cand_overall, 4),
            "ci_upper": round(cand_overall, 4),
            "candidate_accuracy": round(cand_overall, 4),
            "competitive_delta": 0.0,
            "sample_status": "reliable",
            "areas": cand_areas,
        }
    elif compare_institution and compare_institution.upper() != institution.upper():
        comp_stats = _build_institution_stats(
            db, user_id, compare_institution, include_priority=False, catalog_cache_fn=catalog_cache_fn
        )
        comparison_data = {"type": "institution", **comp_stats}
    else:
        comp_stats = _build_institution_stats(
            db, user_id, None, include_priority=False, catalog_cache_fn=catalog_cache_fn
        )
        comparison_data = {"type": "global", **comp_stats}

    has_comparator = bool(
        raw_compare.upper() in ("CANDIDATES", "CONCORRENCIA", "BENCHMARK")
        or (compare_institution and compare_institution.upper() != institution.upper())
    )
    if emit_event:
        (emit_fn or emit)(
            "institution_radar_viewed",
            has_comparator=has_comparator,
            sample_status=primary_data["sample_status"],
        )

    return {
        "institution": primary_data,
        "comparison": comparison_data,
        "disclaimer": "As métricas refletem exclusivamente o histórico resolvido no MedQuest. Menos de 20 tentativas por área indicam amostra limitada e incerteza elevada.",
        "sample_thresholds": {
            "insufficient": "< 20 tentativas (conclusões bloqueadas)",
            "forming": "20 a 49 tentativas",
            "reliable": "≥ 50 tentativas",
        },
    }
