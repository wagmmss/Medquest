"""Serviços de agregação, métricas gerais, timeline, recomendações e dashboard do MedQuest."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from ..adaptive import fsrs_metrics
from ..cache import SimpleTTLCache, catalog_cache_enabled, db_cache_scope
from ..edital_profiles import ALLOWED_ANALYSIS_INSTITUTIONS, get_canonical_institution
from ..tri_engine import evaluate_tri_performance
from .planner import USP_WEIGHTS, get_normalized_area

overview_cache = SimpleTTLCache(60)
_area_totals_cache = SimpleTTLCache(21600)
_q_totals_cache = SimpleTTLCache(21600)

_db_cache_scope = db_cache_scope

CANONICAL_AREA_ORDER = [
    "Clínica Médica",
    "Cirurgia",
    "Ginecologia e Obstetrícia",
    "Pediatria",
    "Medicina Preventiva",
]

CANONICAL_INSTITUTION_LABELS = {
    "USP-SP": "USP - São Paulo",
    "USP-RP": "USP - Ribeirão Preto",
    "UNICAMP": "Unicamp",
    "UNIFESP": "Unifesp / EPM",
    "SUS-SP": "SUS-SP",
}

ALLOWED_BREAKDOWN_COLS = {
    "institution_code",
    "institution_label",
    "source_file",
    "year",
    "topic",
    "area",
    "subtema",
}


def _use_catalog_cache(catalog_cache_fn=None) -> bool:
    fn = catalog_cache_fn or catalog_cache_enabled
    return bool(fn())


def _has_assisted_column(db, *, catalog_cache_fn=None) -> bool:
    use_cache = _use_catalog_cache(catalog_cache_fn)
    scope = _db_cache_scope()
    cache_key = ("has_assisted_col", scope)
    if use_cache:
        cached = _q_totals_cache.get(cache_key)
        if cached is not None:
            return bool(cached)
    try:
        cols = {r["name"] for r in db.execute("PRAGMA table_info(attempts)").fetchall()}
        has_col = "assisted" in cols
    except Exception:
        has_col = True
    if use_cache:
        _q_totals_cache.set(cache_key, has_col)
    return has_col


def _assisted_sql_fragments(db, *, catalog_cache_fn=None) -> tuple[str, str]:
    if _has_assisted_column(db, catalog_cache_fn=catalog_cache_fn):
        return (
            "COALESCE(assisted, 0) AS assisted",
            "COALESCE(SUM(CASE WHEN is_correct = 1 AND assisted = 1 THEN 1 ELSE 0 END), 0) AS assisted_correct",
        )
    return "0 AS assisted", "0 AS assisted_correct"


def _get_cached_total_questions(db, *, catalog_cache_fn=None) -> int:
    use_cache = _use_catalog_cache(catalog_cache_fn)
    scope = _db_cache_scope()
    cache_key = ("total_active_q", scope)
    if use_cache:
        cached = _q_totals_cache.get(cache_key)
        if cached is not None:
            return int(cached)
    row = db.execute("SELECT COUNT(*) AS n FROM questions WHERE missing_alts = 0").fetchone()
    total = int(row["n"] or 0) if row else 0
    if use_cache:
        _q_totals_cache.set(cache_key, total)
    return total


def _get_cached_area_totals(db, *, catalog_cache_fn=None):
    use_cache = _use_catalog_cache(catalog_cache_fn)
    cache_key = ("area_totals", _db_cache_scope())
    if use_cache:
        cached = _area_totals_cache.get(cache_key)
        if cached is not None:
            return cached
    totals = db.execute(
        "SELECT area, COUNT(*) n FROM questions WHERE area IS NOT NULL AND area != '' GROUP BY area"
    ).fetchall()
    if use_cache:
        _area_totals_cache.set(cache_key, totals)
    return totals


def _get_cached_raw_subtema_counts(db, *, catalog_cache_fn=None) -> list[tuple[str, str, int]]:
    """Retorna e cacheia a contagem bruta por (area, subtema) de questões ativas."""
    use_cache = _use_catalog_cache(catalog_cache_fn)
    cache_key = ("raw_subtema_counts", _db_cache_scope())
    if use_cache:
        cached = _q_totals_cache.get(cache_key)
        if cached is not None:
            return cached
    rows = db.execute("""
        SELECT area, subtema, COUNT(*) AS n_questions
        FROM questions
        WHERE missing_alts = 0 AND area IS NOT NULL AND area != '' AND subtema IS NOT NULL AND subtema != ''
        GROUP BY area, subtema
    """).fetchall()
    counts = [(r["area"], r["subtema"], int(r["n_questions"] or 0)) for r in rows]
    if use_cache:
        _q_totals_cache.set(cache_key, counts)
    return counts


def _get_cached_q_totals_map(db, *, catalog_cache_fn=None):
    use_cache = _use_catalog_cache(catalog_cache_fn)
    cache_key = ("q_totals_map", _db_cache_scope())
    if use_cache:
        cached = _q_totals_cache.get(cache_key)
        if cached is not None:
            return cached
    q_map: dict[tuple[str, str], int] = {}
    for area, sub, n_questions in _get_cached_raw_subtema_counts(db, catalog_cache_fn=catalog_cache_fn):
        norm_a = get_normalized_area(area)
        q_map[(norm_a, sub)] = q_map.get((norm_a, sub), 0) + n_questions
    if use_cache:
        _q_totals_cache.set(cache_key, q_map)
    return q_map


def responsible_streak(days_studied, today, days_per_week=6):
    """Count active days while honoring configured weekly rest days.

    Rest days preserve continuity but never inflate the displayed streak.
    """
    active = {str(day) for day in days_studied if day}
    target = max(1, min(7, int(days_per_week or 6)))
    rest_budget = 7 - target
    active_count = 0
    cursor = today
    examined = 0
    rests_in_block = 0
    while examined < 366:
        if str(cursor) in active:
            active_count += 1
        elif rests_in_block < rest_budget:
            rests_in_block += 1
        else:
            break
        examined += 1
        if examined % 7 == 0:
            rests_in_block = 0
        cursor -= timedelta(days=1)
    current_week_active = sum(str(today - timedelta(days=offset)) in active for offset in range(7))
    return {
        "days": active_count,
        "weekly_target": target,
        "active_days_last_7": current_week_active,
        "rest_days_available": max(0, rest_budget - (7 - current_week_active)),
        "policy": "rest_days_preserve_continuity",
    }


def _fetch_attempt_rollup(db, user_id: str, now_utc: datetime, *, catalog_cache_fn=None):
    last7_start = (now_utc - timedelta(days=7)).isoformat()
    prev7_start = (now_utc - timedelta(days=14)).isoformat()
    now_value = now_utc.isoformat()
    total_q = _get_cached_total_questions(db, catalog_cache_fn=catalog_cache_fn)
    assisted_col, assisted_sum = _assisted_sql_fragments(db, catalog_cache_fn=catalog_cache_fn)

    # Uma única varredura com CTE em attempts consolida métricas gerais,
    # janela de 7/14 dias, última tentativa, acertos com dica e caderno de erros.
    row = db.execute(f"""
        WITH user_attempts AS (
            SELECT
                question_id,
                is_correct,
                {assisted_col},
                answered_at,
                ROW_NUMBER() OVER (PARTITION BY question_id ORDER BY id DESC) AS rn
            FROM attempts
            WHERE user_id = ?
        )
        SELECT
            ? AS total_q,
            COUNT(*) AS total_attempts,
            COUNT(DISTINCT question_id) AS distinct_answered,
            COALESCE(SUM(is_correct), 0) AS correct,
            {assisted_sum},
            COALESCE(SUM(CASE WHEN rn = 1 AND is_correct = 1 THEN 1 ELSE 0 END), 0) AS last_correct,
            COALESCE(SUM(CASE WHEN answered_at >= ? THEN is_correct ELSE 0 END), 0) AS last7_correct,
            COALESCE(SUM(CASE WHEN answered_at >= ? THEN 1 ELSE 0 END), 0) AS last7_total,
            COALESCE(SUM(CASE WHEN answered_at >= ? AND answered_at < ? THEN is_correct ELSE 0 END), 0) AS prev7_correct,
            COALESCE(SUM(CASE WHEN answered_at >= ? AND answered_at < ? THEN 1 ELSE 0 END), 0) AS prev7_total,
            COUNT(DISTINCT CASE WHEN is_correct = 0 THEN question_id END) AS ever_wrong_count,
            COUNT(DISTINCT CASE WHEN rn = 1 AND is_correct = 0 THEN question_id END) AS currently_unresolved_count,
            (SELECT COUNT(*) FROM spaced_repetition
             WHERE next_review_date <= ? AND user_id = ?) AS srs_due_count
        FROM user_attempts
    """, (
        user_id,
        total_q,
        last7_start, last7_start,
        prev7_start, last7_start,
        prev7_start, last7_start,
        now_value, user_id,
    )).fetchone()
    return dict(row) if row else {}


def _get_overview_metrics(db, user_id: str, now_utc: datetime, rollup=None, *, catalog_cache_fn=None) -> dict:
    overview = rollup if rollup is not None else _fetch_attempt_rollup(
        db, user_id, now_utc, catalog_cache_fn=catalog_cache_fn
    )

    total_q = overview["total_q"]
    total_attempts = overview["total_attempts"]
    distinct_answered = overview["distinct_answered"]
    correct = overview["correct"]
    accuracy = (correct / total_attempts) if total_attempts else None
    last_correct = overview["last_correct"]
    accuracy_latest = (last_correct / distinct_answered) if distinct_answered else None
    coverage_pct = (distinct_answered / total_q) if total_q else None

    srs_due_count = overview["srs_due_count"]
    accuracy_last7 = (overview["last7_correct"] / overview["last7_total"]) if overview["last7_total"] else None
    accuracy_prev7 = (overview["prev7_correct"] / overview["prev7_total"]) if overview["prev7_total"] else None

    if "assisted_correct" in (overview.keys() if hasattr(overview, "keys") else {}):
        assisted_correct = int(overview["assisted_correct"] or 0)
    else:
        assisted_correct = 0

    unassisted_correct = max(0, int(correct or 0) - assisted_correct)

    return {
        "total_questions": total_q,
        "distinct_answered": distinct_answered,
        "total_attempts": total_attempts,
        "accuracy_all_attempts": accuracy,
        "accuracy_latest_attempt": accuracy_latest,
        "coverage_pct": coverage_pct,
        "srs_due_count": srs_due_count,
        "accuracy_last7": accuracy_last7,
        "accuracy_prev7": accuracy_prev7,
        "assisted_correct_count": assisted_correct,
        "unassisted_correct_count": unassisted_correct,
    }


def _get_streak_and_target_info(
    db, user_id: str, now_utc: datetime, tz_offset: int, config: dict | None = None
) -> dict:
    sign = "+" if tz_offset >= 0 else "-"
    offset_str = f"{sign}{abs(tz_offset)} minutes"

    if config is None:
        config_row = db.execute(
            "SELECT * FROM planner_config WHERE user_id = ?", (user_id,)
        ).fetchone()
        config = dict(config_row) if config_row else {}

    local_today = (now_utc + timedelta(minutes=tz_offset)).date()
    local_start = (
        datetime(local_today.year, local_today.month, local_today.day, tzinfo=UTC)
        - timedelta(minutes=tz_offset)
    )
    local_end = local_start + timedelta(days=1)

    day_rows = db.execute(
        """
        SELECT
            substr(datetime(answered_at, ?), 1, 10) AS day,
            COUNT(DISTINCT CASE WHEN answered_at >= ? AND answered_at < ? THEN question_id END) AS today_q
        FROM attempts
        WHERE user_id = ?
        GROUP BY day
        ORDER BY day DESC
        """,
        (offset_str, local_start.isoformat(), local_end.isoformat(), user_id),
    ).fetchall()
    days_studied = {r["day"] for r in day_rows if r["day"]}
    today_answered_count = sum(int(r["today_q"] or 0) for r in day_rows)

    streak = responsible_streak(days_studied, local_today, config.get("days_per_week") or 6)

    daily_target = config.get("questions_per_day") or 20
    exam_date_str = config.get("exam_date")
    days_until_exam = None
    if exam_date_str:
        try:
            ed = datetime.fromisoformat(exam_date_str.replace("Z", "+00:00")).date()
            days_until_exam = (ed - local_today).days
        except Exception:
            days_until_exam = None

    raw_inst = config.get("target_institution")
    primary_inst = None
    if raw_inst and raw_inst not in ("Todas as Bancas", "TODAS"):
        primary_inst = raw_inst.split(",")[0].strip()

    return {
        "streak_days": streak["days"],
        "streak": streak,
        "today_answered": today_answered_count,
        "daily_target": daily_target,
        "days_until_exam": days_until_exam,
        "exam_date": exam_date_str,
        "target_score": config.get("target_score"),
        "target_institution": raw_inst,
        "primary_institution": primary_inst,
    }


def breakdown_data(db, user_id: str, group_col: str, label_col: str | None = None) -> list[dict]:
    if group_col not in ALLOWED_BREAKDOWN_COLS:
        raise ValueError(f"Invalid group_col for _breakdown: {group_col}")
    if label_col and label_col not in ALLOWED_BREAKDOWN_COLS:
        raise ValueError(f"Invalid label_col for _breakdown: {label_col}")

    label_expr = label_col or group_col
    rows = db.execute(f"""
        SELECT q.{group_col} AS key, MIN(q.{label_expr}) AS label,
               COUNT(a.id) AS attempts, SUM(a.is_correct) AS correct
        FROM attempts a JOIN questions q ON q.id = a.question_id
        WHERE a.user_id = ? AND q.{group_col} IS NOT NULL AND q.{group_col} != ''
        GROUP BY q.{group_col} ORDER BY attempts DESC
    """, (user_id,)).fetchall()

    if group_col == "institution_code":
        aggregated: dict[str, dict] = {
            inst: {
                "key": inst,
                "label": CANONICAL_INSTITUTION_LABELS[inst],
                "attempts": 0,
                "correct": 0,
            }
            for inst in ALLOWED_ANALYSIS_INSTITUTIONS
        }
        for r in rows:
            canon = get_canonical_institution(r["key"])
            if canon and canon in aggregated:
                aggregated[canon]["attempts"] += r["attempts"]
                aggregated[canon]["correct"] += r["correct"]

        out = []
        for inst in ALLOWED_ANALYSIS_INSTITUTIONS:
            item = aggregated[inst]
            att = item["attempts"]
            cor = item["correct"]
            acc = (cor / att) if att > 0 else 0.0
            out.append({
                "key": item["key"],
                "label": item["label"],
                "attempts": att,
                "correct": cor,
                "accuracy": acc,
            })
        out.sort(key=lambda x: x["attempts"], reverse=True)
        return out

    out = []
    for r in rows:
        acc = (r["correct"] / r["attempts"]) if r["attempts"] else 0
        out.append({
            "key": r["key"],
            "label": r["label"],
            "attempts": r["attempts"],
            "correct": r["correct"],
            "accuracy": acc,
        })
    return out


def _get_timeline_data(
    db,
    user_id: str,
    days: int | None = None,
    tz_offset: int = -180,
    now_utc: datetime | None = None,
    *,
    catalog_cache_fn=None,
) -> list[dict]:
    sign = "+" if tz_offset >= 0 else "-"
    offset_str = f"{sign}{abs(tz_offset)} minutes"
    date_filter = ""
    params: tuple = (offset_str, offset_str, user_id)
    if days is not None:
        ref_now = now_utc if now_utc is not None else datetime.now(UTC)
        local_today = (ref_now + timedelta(minutes=tz_offset)).date()
        window_start_local = local_today - timedelta(days=days)
        window_start_utc = (
            datetime(window_start_local.year, window_start_local.month, window_start_local.day, tzinfo=UTC)
            - timedelta(minutes=tz_offset)
        ).isoformat()
        date_filter = "AND answered_at >= ?"
        params = (offset_str, offset_str, user_id, window_start_utc)

    assisted_col, assisted_sum = _assisted_sql_fragments(db, catalog_cache_fn=catalog_cache_fn)
    rows = db.execute(f"""
        WITH ranked AS (
            SELECT
                date(answered_at, ?) AS day,
                question_id,
                is_correct,
                {assisted_col},
                time_spent_ms,
                ROW_NUMBER() OVER (
                    PARTITION BY date(answered_at, ?), question_id
                    ORDER BY answered_at DESC, id DESC
                ) AS rn
            FROM attempts
            WHERE user_id = ? {date_filter}
        )
        SELECT
            day,
            COUNT(*) AS attempts,
            SUM(is_correct) AS correct,
            {assisted_sum},
            SUM(CASE WHEN rn = 1 THEN 1 ELSE 0 END) AS latest_attempts,
            SUM(CASE WHEN rn = 1 THEN is_correct ELSE 0 END) AS latest_correct,
            AVG(CASE WHEN time_spent_ms IS NOT NULL AND time_spent_ms > 0 AND time_spent_ms < 1800000 THEN time_spent_ms END) AS avg_time_ms,
            SUM(CASE WHEN time_spent_ms IS NOT NULL AND time_spent_ms > 0 AND time_spent_ms < 1800000 THEN time_spent_ms ELSE 0 END) AS total_time_ms,
            COUNT(CASE WHEN time_spent_ms IS NOT NULL AND time_spent_ms > 0 AND time_spent_ms < 1800000 THEN 1 END) AS timed_attempts
        FROM ranked
        GROUP BY day
        ORDER BY day
    """, params).fetchall()

    return [
        {
            "day": r["day"],
            "attempts": r["attempts"],
            "correct": r["correct"],
            "assisted_correct": int(r["assisted_correct"] or 0),
            "unassisted_correct": max(0, int(r["correct"] or 0) - int(r["assisted_correct"] or 0)),
            "accuracy": (r["correct"] / r["attempts"]) if r["attempts"] else 0,
            "latest_attempts": r["latest_attempts"],
            "latest_correct": r["latest_correct"],
            "latest_accuracy": (r["latest_correct"] / r["latest_attempts"]) if r["latest_attempts"] else 0,
            "avg_time_ms": round(r["avg_time_ms"]) if r["avg_time_ms"] is not None else None,
            "total_time_ms": int(r["total_time_ms"] or 0),
            "timed_attempts": int(r["timed_attempts"] or 0),
        }
        for r in rows
    ]


def _get_weak_topics_data(db, user_id: str, min_attempts: int = 5) -> list[dict]:
    min_attempts = max(5, min(min_attempts, 1000))
    rows = db.execute("""
        SELECT TRIM(COALESCE(NULLIF(TRIM(q.subtema), ''), NULLIF(TRIM(q.topic), ''))) AS topic,
               COUNT(a.id) AS attempts, SUM(a.is_correct) AS correct
        FROM attempts a JOIN questions q ON q.id = a.question_id
        WHERE a.user_id = ? AND COALESCE(NULLIF(TRIM(q.subtema), ''), NULLIF(TRIM(q.topic), '')) IS NOT NULL
        GROUP BY topic HAVING attempts >= ?
        ORDER BY (CAST(correct AS FLOAT) / attempts) ASC LIMIT 15
    """, (user_id, min_attempts)).fetchall()
    return [
        {
            "topic": r["topic"],
            "attempts": r["attempts"],
            "correct": r["correct"],
            "accuracy": (r["correct"] / r["attempts"]) if r["attempts"] else 0,
        }
        for r in rows
    ]


def _get_srs_due_recommendation(db, user_id: str, *, now_utc: datetime | None = None):
    ref_now = now_utc if now_utc is not None else datetime.now(UTC)
    srs_due = db.execute(
        "SELECT COUNT(*) n FROM spaced_repetition WHERE next_review_date <= ? AND user_id = ?",
        (ref_now.isoformat(), user_id),
    ).fetchone()["n"]
    if srs_due > 0:
        return {
            "type": "srs_due",
            "icon": "ph-alarm",
            "title": f"{srs_due} questão(ões) para revisar hoje",
            "description": "Sua repetição espaçada tem itens prontos para revisão. Reforce agora o que você já viu antes de esquecer.",
            "cta": "Revisar agora",
            "filters": {"status": "srs_due"},
        }
    return None


def _get_adaptive_recommendation(db, user_id: str):
    attempt_count = db.execute(
        "SELECT COUNT(*) n FROM attempts WHERE user_id = ?", (user_id,)
    ).fetchone()["n"]
    if attempt_count >= 3:
        return {
            "type": "adaptive",
            "icon": "ph-brain",
            "title": "Sessão adaptativa personalizada",
            "description": "Uma fila equilibrada por revisões vencidas, risco de esquecimento, erros recentes e lacunas de cobertura.",
            "cta": "Iniciar sessão",
            "filters": {"mode": "adaptive", "limit": "30"},
        }
    return None


def _get_weak_topics_recommendations(db, user_id: str):
    weak_subtemas = db.execute("""
        SELECT q.subtema AS subtema, MIN(q.area) AS area,
               COUNT(a.id) AS attempts, SUM(a.is_correct) AS correct
        FROM attempts a JOIN questions q ON q.id = a.question_id
        WHERE a.user_id = ? AND q.subtema IS NOT NULL AND q.subtema != ''
        GROUP BY q.subtema HAVING attempts >= 3
        ORDER BY (CAST(correct AS FLOAT) / attempts) ASC LIMIT 3
    """, (user_id,)).fetchall()
    recs = []
    covered_areas = set()
    for r in weak_subtemas:
        acc = r["correct"] / r["attempts"]
        if acc < 0.65:
            covered_areas.add(r["area"])
            recs.append({
                "type": "weak_topic",
                "icon": "ph-warning-circle",
                "title": f"Reforce {r['subtema']}",
                "description": f"Sua acurácia aqui é de {round(acc * 100)}% em {r['attempts']} tentativas. Vale revisar a teoria e praticar mais questões.",
                "cta": "Praticar agora",
                "filters": {"subtema": r["subtema"]},
            })
    return recs, covered_areas


def _get_weak_area_recommendations(db, user_id: str, covered_areas):
    weak_areas = db.execute("""
        SELECT q.area AS area, COUNT(a.id) AS attempts, SUM(a.is_correct) AS correct
        FROM attempts a JOIN questions q ON q.id = a.question_id
        WHERE a.user_id = ? AND q.area IS NOT NULL AND q.area != ''
        GROUP BY q.area HAVING attempts >= 5
        ORDER BY (CAST(correct AS FLOAT) / attempts) ASC LIMIT 1
    """, (user_id,)).fetchall()
    recs = []
    for r in weak_areas:
        acc = r["correct"] / r["attempts"]
        if acc < 0.65 and r["area"] not in covered_areas:
            recs.append({
                "type": "weak_area",
                "icon": "ph-chart-bar",
                "title": f"Sua acurácia em {r['area']} está baixa",
                "description": f"{round(acc * 100)}% de acerto em {r['attempts']} tentativas nessa área. Considere revisar os fundamentos antes de continuar.",
                "cta": "Estudar área",
                "filters": {"area": r["area"]},
            })
    return recs


def _get_explore_recommendation(db, user_id: str, *, catalog_cache_fn=None):
    area_totals = _get_cached_area_totals(db, catalog_cache_fn=catalog_cache_fn)
    area_answered = db.execute("""
        SELECT q.area AS area, COUNT(DISTINCT a.question_id) n
        FROM attempts a JOIN questions q ON q.id = a.question_id
        WHERE a.user_id = ? AND q.area IS NOT NULL AND q.area != '' GROUP BY q.area
    """, (user_id,)).fetchall()
    answered_map = {r["area"]: r["n"] for r in area_answered}
    least_explored = None
    for r in area_totals:
        if r["n"] < 20:
            continue
        coverage = answered_map.get(r["area"], 0) / r["n"]
        if least_explored is None or coverage < least_explored["coverage"]:
            least_explored = {"area": r["area"], "coverage": coverage, "total": r["n"]}
    if least_explored is not None and least_explored["coverage"] < 0.1:
        return {
            "type": "explore",
            "icon": "ph-compass",
            "title": f"Explore mais {least_explored['area']}",
            "description": f"Você ainda não praticou quase nada nessa área ({round(least_explored['coverage'] * 100)}% de {least_explored['total']} questões). Bom momento para começar.",
            "cta": "Começar a explorar",
            "filters": {"area": least_explored["area"], "status": "unanswered"},
        }
    return None


def _get_fallback_recommendations(db, user_id: str, has_recs: bool):
    if has_recs:
        return []
    row = db.execute("""
        WITH user_attempts AS (
            SELECT
                question_id,
                is_correct,
                ROW_NUMBER() OVER (PARTITION BY question_id ORDER BY id DESC) AS rn
            FROM attempts
            WHERE user_id = ?
        )
        SELECT
            COUNT(*) AS total_attempts,
            COUNT(DISTINCT question_id) AS distinct_answered,
            COALESCE(SUM(CASE WHEN rn = 1 AND is_correct = 1 THEN 1 ELSE 0 END), 0) AS last_correct
        FROM user_attempts
    """, (user_id,)).fetchone()
    total_attempts = int(row["total_attempts"] or 0) if row else 0
    distinct_answered = int(row["distinct_answered"] or 0) if row else 0
    last_correct = int(row["last_correct"] or 0) if row else 0
    accuracy_latest = (last_correct / distinct_answered) if distinct_answered else None

    if distinct_answered >= 10 and accuracy_latest is not None and accuracy_latest >= 0.8:
        return [{
            "type": "praise",
            "icon": "ph-trophy",
            "title": "Ótimo desempenho geral!",
            "description": f"Você está acertando {round(accuracy_latest * 100)}% das últimas tentativas. Que tal se desafiar em um simulado cronometrado?",
            "cta": "Ir para os filtros",
            "filters": {},
        }]
    if total_attempts < 10:
        return [{
            "type": "start",
            "icon": "ph-rocket-launch",
            "title": "Comece a responder questões",
            "description": "Ainda não há tentativas suficientes para gerar recomendações personalizadas. Responda algumas questões para começar.",
            "cta": "Ir para os filtros",
            "filters": {},
        }]
    return []


def build_recommendations(db, user_id: str, *, now_utc: datetime | None = None, catalog_cache_fn=None) -> list[dict]:
    recs = []
    srs_rec = _get_srs_due_recommendation(db, user_id, now_utc=now_utc)
    if srs_rec:
        recs.append(srs_rec)
    adaptive_rec = _get_adaptive_recommendation(db, user_id)
    if adaptive_rec:
        recs.append(adaptive_rec)
    weak_topics_recs, covered_areas = _get_weak_topics_recommendations(db, user_id)
    recs.extend(weak_topics_recs)
    recs.extend(_get_weak_area_recommendations(db, user_id, covered_areas))
    explore_rec = _get_explore_recommendation(db, user_id, catalog_cache_fn=catalog_cache_fn)
    if explore_rec:
        recs.append(explore_rec)
    recs.extend(_get_fallback_recommendations(db, user_id, bool(recs)))
    return recs[:5]


def get_predictive_score_data(db, user_id: str) -> dict:
    config_row = db.execute("SELECT * FROM planner_config WHERE user_id = ?", (user_id,)).fetchone()
    target_score = config_row["target_score"] if config_row and "target_score" in config_row.keys() else None

    areas_stats = db.execute("""
        SELECT q.area AS area, COUNT(a.id) AS attempts, SUM(a.is_correct) AS correct
        FROM attempts a JOIN questions q ON q.id = a.question_id
        WHERE a.user_id = ? AND q.area IS NOT NULL AND q.area != ''
        GROUP BY q.area
    """, (user_id,)).fetchall()

    if not areas_stats:
        return {
            "projected_score": 0,
            "target_score": target_score,
            "areas": [],
        }

    grouped_areas: dict[str, dict[str, int]] = {}
    for r in areas_stats:
        norm_area = get_normalized_area(r["area"])
        bucket = grouped_areas.setdefault(norm_area, {"attempts": 0, "correct": 0})
        bucket["attempts"] += int(r["attempts"] or 0)
        bucket["correct"] += int(r["correct"] or 0)

    areas_acc = []
    projected_score_weighted = 0.0
    area_attempts = {}

    for norm_area, stats_item in grouped_areas.items():
        weight = USP_WEIGHTS.get(norm_area, 0.1)
        att = stats_item["attempts"]
        cor = stats_item["correct"]

        # Penaliza acurácia se tiver menos de 5 tentativas
        acc = (cor / att) if att >= 5 else (cor / 5.0)
        acc_pct = round(acc * 100, 1)
        areas_acc.append({
            "area": norm_area,
            "accuracy": acc_pct,
            "attempts": att,
        })
        area_attempts[norm_area] = att
        projected_score_weighted += acc_pct * weight

    # A projeção só é confiável com >= 20 tentativas em cada grande área.
    projected_score = min(100.0, round(projected_score_weighted, 1))
    is_reliable = all(area_attempts.get(area, 0) >= 20 for area in USP_WEIGHTS)

    return {
        "projected_score": projected_score,
        "target_score": target_score,
        "areas": sorted(areas_acc, key=lambda x: x["accuracy"], reverse=True),
        "is_reliable": is_reliable,
        "total_attempts": sum(area_attempts.values()),
        "minimum_attempts_per_area": 20,
    }


def get_tri_readiness_data(db, user_id: str, institution_code: str = "ENARE") -> dict:
    rows = db.execute("""
        WITH latest_attempts AS (
            SELECT question_id, is_correct,
                   ROW_NUMBER() OVER (PARTITION BY question_id ORDER BY id DESC) as rn
            FROM attempts
            WHERE user_id = ?
        )
        SELECT question_id, is_correct
        FROM latest_attempts
        WHERE rn = 1
    """, (user_id,)).fetchall()
    responses = [{"question_id": r["question_id"], "is_correct": bool(r["is_correct"])} for r in rows]
    return evaluate_tri_performance(db, responses, institution_code=institution_code)


def _get_at_risk_data(db, user_id: str, preloaded_sr_rows: list | None = None) -> list[dict]:
    if preloaded_sr_rows is not None:
        rows = sorted(
            preloaded_sr_rows,
            key=lambda r: str((r["next_review_date"] if r["next_review_date"] is not None else "9999")),
        )
    else:
        rows = db.execute("""
            SELECT q.subtema, sr.fsrs_card, sr.next_review_date
            FROM spaced_repetition sr
            JOIN questions q ON sr.question_id = q.id
            WHERE sr.user_id = ? AND sr.fsrs_card IS NOT NULL
            ORDER BY sr.next_review_date ASC
        """, (user_id,)).fetchall()

    topics_risk = {}
    for r in rows:
        subtema = r["subtema"]
        if not subtema or not r["fsrs_card"]:
            continue
        metrics = fsrs_metrics(r["fsrs_card"])
        retrievability = metrics["retrievability"]
        if retrievability is None:
            continue

        if subtema not in topics_risk:
            topics_risk[subtema] = {"count": 0, "min_retrievability": retrievability}

        topics_risk[subtema]["count"] += 1
        topics_risk[subtema]["min_retrievability"] = min(topics_risk[subtema]["min_retrievability"], retrievability)

    desired_retention = 0.85
    at_risk_list = []
    for subtema, data in topics_risk.items():
        if data["min_retrievability"] < desired_retention:
            at_risk_list.append({
                "subtema": subtema,
                "items_count": data["count"],
                "retrievability": round(data["min_retrievability"], 4),
                "stability": None,
            })

    at_risk_list.sort(key=lambda x: (x["retrievability"], x["subtema"]))
    return at_risk_list[:10]


def _get_distractors_data(db, user_id: str) -> list[dict]:
    rows = db.execute("""
        SELECT q.subtema AS subtema, a.selected_letter AS letter, COUNT(*) AS n
        FROM attempts a JOIN questions q ON q.id = a.question_id
        WHERE a.user_id = ? AND a.is_correct = 0 AND q.subtema IS NOT NULL AND q.subtema != ''
        GROUP BY q.subtema, a.selected_letter
        ORDER BY q.subtema, n DESC
    """, (user_id,)).fetchall()
    by_sub: dict[str, list[dict]] = {}
    for r in rows:
        by_sub.setdefault(r["subtema"], []).append({"letter": r["letter"], "count": r["n"]})
    out = [
        {"subtema": s, "wrong_choices": v, "total_wrong": sum(x["count"] for x in v)}
        for s, v in by_sub.items()
    ]
    out.sort(key=lambda x: x["total_wrong"], reverse=True)
    return out[:20]


def _get_benchmark_data(
    db,
    user_id: str,
    now_utc: datetime,
    rollup=None,
    config: dict | None = None,
) -> dict:
    if rollup is not None:
        total_attempts = rollup["total_attempts"] or 0
        total_correct = rollup["correct"] or 0
        last7_attempts = rollup["last7_total"] or 0
        last7_correct = rollup["last7_correct"] or 0
    else:
        last7_start = (now_utc - timedelta(days=7)).isoformat()
        stats_row = db.execute("""
            SELECT
                COUNT(a.id) AS total_attempts,
                SUM(a.is_correct) AS total_correct,
                SUM(CASE WHEN a.answered_at >= ? THEN 1 ELSE 0 END) AS last7_attempts,
                SUM(CASE WHEN a.answered_at >= ? THEN a.is_correct ELSE 0 END) AS last7_correct
            FROM attempts a
            WHERE a.user_id = ?
        """, (last7_start, last7_start, user_id)).fetchone()

        total_attempts = stats_row["total_attempts"] or 0
        total_correct = stats_row["total_correct"] or 0
        last7_attempts = stats_row["last7_attempts"] or 0
        last7_correct = stats_row["last7_correct"] or 0

    accuracy_overall = (total_correct / total_attempts) if total_attempts > 0 else None
    accuracy_last7 = (last7_correct / last7_attempts) if last7_attempts > 0 else None

    if config is None:
        try:
            config_row = db.execute("SELECT * FROM planner_config WHERE user_id = ?", (user_id,)).fetchone()
            if config_row:
                config = dict(config_row)
        except Exception:
            config = None

    target_score_pct = config.get("target_score") if config and config.get("target_score") else 76.0
    target_score = target_score_pct / 100.0

    weekly_target_questions = 80
    if config and config.get("days_per_week"):
        daily_q = config.get("questions_per_day") or 15
        weekly_target_questions = max(20, config["days_per_week"] * daily_q)

    diff_pct = round((accuracy_overall - target_score) * 100, 1) if accuracy_overall is not None else None
    weekly_progress_pct = (
        min(100.0, round((last7_attempts / weekly_target_questions) * 100, 1))
        if weekly_target_questions > 0
        else 0.0
    )

    status_label = "iniciando"
    if accuracy_overall is not None:
        if diff_pct >= 0:
            status_label = "aprovado"
        elif diff_pct >= -10:
            status_label = "competitivo"
        else:
            status_label = "em_evolucao"

    return {
        "accuracy_overall": accuracy_overall,
        "accuracy_last7": accuracy_last7,
        "target_score": target_score,
        "target_score_pct": target_score_pct,
        "diff_pct": diff_pct,
        "status_label": status_label,
        "total_attempts": total_attempts,
        "total_correct": total_correct,
        "is_reliable_sample": total_attempts >= 20,
        "last7_attempts": last7_attempts,
        "weekly_target_questions": weekly_target_questions,
        "weekly_progress_pct": weekly_progress_pct,
        "competitors_average_pct": 76.0,
    }


def _get_bottlenecks_data(db, user_id: str, limit: int = 5) -> list:
    limit = max(1, min(limit, 20))
    rows = db.execute("""
        WITH latest_attempts AS (
            SELECT question_id, is_correct,
                   ROW_NUMBER() OVER (PARTITION BY question_id ORDER BY id DESC) as rn
            FROM attempts
            WHERE user_id = ?
        )
        SELECT
            q.subtema,
            MIN(q.area) AS area,
            COUNT(DISTINCT CASE WHEN la.is_correct = 0 THEN q.id END) AS unresolved_count,
            COUNT(a.id) AS attempts,
            SUM(a.is_correct) AS correct,
            SUM(CASE WHEN a.is_correct = 0 THEN 1 ELSE 0 END) AS wrong_count
        FROM attempts a
        JOIN questions q ON q.id = a.question_id
        LEFT JOIN latest_attempts la ON la.question_id = q.id AND la.rn = 1
        WHERE a.user_id = ? AND q.subtema IS NOT NULL AND q.subtema != ''
        GROUP BY q.subtema
        HAVING unresolved_count > 0
        ORDER BY
            unresolved_count DESC,
            wrong_count DESC,
            attempts DESC
        LIMIT ?
    """, (user_id, user_id, limit)).fetchall()

    out = []
    for r in rows:
        acc = (r["correct"] / r["attempts"]) if r["attempts"] > 0 else 0.0
        out.append({
            "subtema": r["subtema"],
            "area": r["area"],
            "unresolved_count": r["unresolved_count"],
            "attempts": r["attempts"],
            "correct": r["correct"],
            "wrong_count": r["wrong_count"],
            "accuracy": round(acc, 3),
            "accuracy_pct": round(acc * 100, 1),
            "practice_url": f"/estudar?subtema={quote(r['subtema'])}&status=wrong&limit=10",
        })
    return out


def _create_area_stats(area_name: str) -> dict:
    return {
        "area": area_name,
        "total_subtemas": 0,
        "mastered_subtemas": 0,
        "proficient_subtemas": 0,
        "in_progress_subtemas": 0,
        "not_started_subtemas": 0,
        "attempts": 0,
        "correct": 0,
        "accuracy": None,
        "domain_pct": 0.0,
    }


def _update_area_stats(item: dict, attempts: int, correct: int) -> None:
    item["total_subtemas"] += 1
    item["attempts"] += attempts
    item["correct"] += correct

    if attempts == 0:
        item["not_started_subtemas"] += 1
    else:
        acc = correct / attempts
        if attempts >= 15 and acc >= 0.75:
            item["mastered_subtemas"] += 1
        elif attempts >= 5 and acc >= 0.70:
            item["proficient_subtemas"] += 1
        else:
            item["in_progress_subtemas"] += 1


def _calculate_area_metrics(item: dict) -> None:
    if item["attempts"] > 0:
        item["accuracy"] = round(item["correct"] / item["attempts"], 3)
    if item["total_subtemas"] > 0:
        item["domain_pct"] = round((item["mastered_subtemas"] / item["total_subtemas"]) * 100, 1)


def _get_domain_summary_data(db, user_id: str, *, catalog_cache_fn=None) -> dict:
    raw_subtemas = _get_cached_raw_subtema_counts(db, catalog_cache_fn=catalog_cache_fn)
    user_rows = db.execute("""
        SELECT
            q.area,
            q.subtema,
            COUNT(a.id) AS attempts,
            COALESCE(SUM(a.is_correct), 0) AS correct
        FROM attempts a
        JOIN questions q ON q.id = a.question_id
        WHERE a.user_id = ?
              AND q.missing_alts = 0
              AND q.area IS NOT NULL AND q.area != ''
              AND q.subtema IS NOT NULL AND q.subtema != ''
        GROUP BY q.area, q.subtema
    """, (user_id,)).fetchall()
    user_map = {
        (r["area"], r["subtema"]): (r["attempts"] or 0, r["correct"] or 0)
        for r in user_rows
    }

    areas_map = {area_name: _create_area_stats(area_name) for area_name in CANONICAL_AREA_ORDER}

    for area, subtema, _ in raw_subtemas:
        if area not in areas_map:
            areas_map[area] = _create_area_stats(area)
        att, cor = user_map.get((area, subtema), (0, 0))
        _update_area_stats(areas_map[area], att, cor)

    result = []
    for area_name in CANONICAL_AREA_ORDER:
        if area_name in areas_map:
            item = areas_map.pop(area_name)
            _calculate_area_metrics(item)
            result.append(item)

    for item in areas_map.values():
        _calculate_area_metrics(item)
        result.append(item)

    total_subtemas_all = sum(x["total_subtemas"] for x in result)
    total_mastered_all = sum(x["mastered_subtemas"] for x in result)
    overall_domain_pct = (
        round((total_mastered_all / total_subtemas_all) * 100, 1) if total_subtemas_all > 0 else 0.0
    )

    return {
        "overall_domain_pct": overall_domain_pct,
        "total_mastered": total_mastered_all,
        "total_subtemas": total_subtemas_all,
        "areas": result,
    }


def _get_error_notebook_summary_data(db, user_id: str, rollup=None) -> dict:
    if rollup is not None:
        ever_wrong = rollup["ever_wrong_count"] or 0
        currently_unresolved = rollup["currently_unresolved_count"] or 0
    else:
        row = db.execute("""
            WITH latest_attempts AS (
                SELECT question_id, is_correct,
                       ROW_NUMBER() OVER (PARTITION BY question_id ORDER BY id DESC) as rn
                FROM attempts
                WHERE user_id = ?
            )
            SELECT
                COUNT(DISTINCT a.question_id) AS ever_wrong_count,
                COUNT(DISTINCT CASE WHEN la.is_correct = 0 THEN a.question_id END) AS currently_unresolved_count
            FROM attempts a
            LEFT JOIN latest_attempts la ON la.question_id = a.question_id AND la.rn = 1
            WHERE a.user_id = ? AND a.is_correct = 0
        """, (user_id, user_id)).fetchone()

        ever_wrong = row["ever_wrong_count"] if row and row["ever_wrong_count"] else 0
        currently_unresolved = row["currently_unresolved_count"] if row and row["currently_unresolved_count"] else 0

    return {
        "ever_wrong_count": ever_wrong,
        "currently_unresolved_count": currently_unresolved,
        "practice_url": "/estudar?status=wrong&limit=20",
    }


def _format_planner_config_from_row(raw_config: dict | None) -> dict | None:
    if not raw_config:
        return None
    inst_str = raw_config.get("target_institution")
    inst_list = [i.strip() for i in inst_str.split(",") if i.strip()] if inst_str else []
    primary_inst = None
    if inst_list and inst_list[0] not in ("Todas as Bancas", "TODAS"):
        primary_inst = inst_list[0]
    return {
        "exam_date": raw_config.get("exam_date"),
        "start_date": raw_config.get("start_date"),
        "days_per_week": raw_config.get("days_per_week"),
        "hours_per_day": raw_config.get("hours_per_day", raw_config.get("questions_per_day")),
        "target_score": raw_config.get("target_score"),
        "target_institution": inst_str,
        "target_institutions": inst_list,
        "primary_institution": primary_inst,
        "target_specialty": raw_config.get("target_specialty"),
    }


def build_dashboard_summary_data(
    db, user_id: str, now_utc: datetime, tz_offset: int, *, catalog_cache_fn=None
) -> dict:
    rollup = _fetch_attempt_rollup(db, user_id, now_utc, catalog_cache_fn=catalog_cache_fn)
    planner_queries = [
        ("SELECT * FROM planner_config WHERE user_id = ?", (user_id,)),
        ("SELECT * FROM planner_progress WHERE user_id = ?", (user_id,)),
        ("SELECT week, subtema, completed FROM planner_topic_progress WHERE user_id = ?", (user_id,)),
    ]
    batch_res = None
    if hasattr(db, "batch"):
        try:
            batch_res = db.batch(planner_queries)
        except Exception:
            batch_res = None

    if batch_res is not None:
        config_row = batch_res[0].fetchone()
        prog_rows = batch_res[1].fetchall()
        topic_rows = batch_res[2].fetchall()
        planner_prog = {
            str(r["week"]): {
                "studied": bool(r["studied"]),
                "studied_at": r["studied_at"],
                "rev24h": bool(r["rev24h"]),
                "rev7d": bool(r["rev7d"]),
                "rev30d": bool(r["rev30d"]),
            }
            for r in prog_rows
        }
        planner_topics = {}
        for r in topic_rows:
            val = bool(r["completed"])
            planner_topics[f"{r['week']}:{r['subtema']}"] = val
            if val:
                planner_topics[r["subtema"]] = True
    else:
        config_row = db.execute(planner_queries[0][0], planner_queries[0][1]).fetchone()
        from ..plan import get_planner_progress_data, get_planner_topic_progress_data

        planner_prog = get_planner_progress_data(db, user_id)
        planner_topics = get_planner_topic_progress_data(db, user_id)

    raw_config = dict(config_row) if config_row else {}

    overview = _get_overview_metrics(db, user_id, now_utc, rollup=rollup, catalog_cache_fn=catalog_cache_fn)
    overview.update(_get_streak_and_target_info(db, user_id, now_utc, tz_offset, config=raw_config))

    return {
        "stats": overview,
        "benchmark": _get_benchmark_data(db, user_id, now_utc, rollup=rollup, config=raw_config),
        "bottlenecks": _get_bottlenecks_data(db, user_id, limit=3),
        "domain_summary": _get_domain_summary_data(db, user_id, catalog_cache_fn=catalog_cache_fn),
        "error_notebook": _get_error_notebook_summary_data(db, user_id, rollup=rollup),
        "planner": {
            "config": _format_planner_config_from_row(raw_config),
            "progress": planner_prog,
            "topic_progress": planner_topics,
        },
    }
