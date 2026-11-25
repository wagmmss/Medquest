"""Blueprint HTTP de estatísticas, prontidão, cobertura, dashboard e radar de bancas."""
from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request

from .adaptive import build_learning_profile
from .cache import catalog_cache_enabled
from .db import db_transaction, get_db
from .observability import emit
from .questions import invalidate_user_caches
from .remediation import calculate_blindspots
from .services import coverage_service as _coverage_svc
from .services import institution_analytics as _inst_svc
from .services import stats_rollup as _rollup_svc
from .services.institution_analytics import (
    _get_user_area_attempts,
    _institution_area_totals_cache,
    calculate_wilson_ci,
    get_sample_status,
)
from .services.psychometrics import (
    beta_credible_interval,
    beta_quantile,
    calculate_bayesian_readiness,
    regularized_incomplete_beta,
    weighted_beta_credible_interval,
)
from .services.stats_rollup import (
    ALLOWED_BREAKDOWN_COLS,
    _area_totals_cache,
    _format_planner_config_from_row,
    _get_at_risk_data,
    _get_benchmark_data,
    _get_bottlenecks_data,
    _get_distractors_data,
    _get_error_notebook_summary_data,
    _get_streak_and_target_info,
    _get_weak_topics_data,
    _q_totals_cache,
    overview_cache,
    responsible_streak,
)
from .timezones import resolve_tz_offset_minutes

bp = Blueprint("stats", __name__)


def _catalog_cache_enabled() -> bool:
    return bool(catalog_cache_enabled())


def _emit_telemetry(event: str, **fields) -> None:
    emit(event, **fields)


# Wrappers finos de compatibilidade que propagam monkeypatches de api.stats.*
def _get_cached_q_totals_map(db):
    return _rollup_svc._get_cached_q_totals_map(db, catalog_cache_fn=_catalog_cache_enabled)


def _fetch_attempt_rollup(db, user_id: str, now_utc: datetime):
    return _rollup_svc._fetch_attempt_rollup(
        db, user_id, now_utc, catalog_cache_fn=_catalog_cache_enabled
    )


def _get_overview_metrics(db, user_id: str, now_utc: datetime, rollup=None) -> dict:
    return _rollup_svc._get_overview_metrics(
        db, user_id, now_utc, rollup=rollup, catalog_cache_fn=_catalog_cache_enabled
    )


def _get_timeline_data(
    db, user_id: str, days: int | None = None, tz_offset: int = -180, now_utc: datetime | None = None
) -> list[dict]:
    return _rollup_svc._get_timeline_data(
        db,
        user_id,
        days=days,
        tz_offset=tz_offset,
        now_utc=now_utc,
        catalog_cache_fn=_catalog_cache_enabled,
    )


def _get_domain_summary_data(db, user_id: str) -> dict:
    return _rollup_svc._get_domain_summary_data(db, user_id, catalog_cache_fn=_catalog_cache_enabled)


def _get_user_coverage_stats(db, user_id):
    return _coverage_svc._get_user_coverage_stats(db, user_id)


def _get_coverage_data(db, user_id: str, area_filter: str = "", summary_only: bool = False) -> dict:
    return _coverage_svc._get_coverage_data(
        db,
        user_id,
        area_filter=area_filter,
        summary_only=summary_only,
        catalog_cache_fn=_catalog_cache_enabled,
    )


def _fetch_all_priority_topics(
    db, user_id: str, institution_code: str | None, inst_clause: str, aliases: list[str] | None = None
) -> dict[str, list[dict]]:
    return _inst_svc._fetch_all_priority_topics(
        db,
        user_id,
        institution_code,
        inst_clause,
        aliases=aliases,
        catalog_cache_fn=_catalog_cache_enabled,
    )


def _get_exam_readiness_data(
    db, user_id: str, raw_institution: str = "", emit_event: bool = True
) -> dict:
    return _inst_svc._get_exam_readiness_data(
        db,
        user_id,
        raw_institution=raw_institution,
        emit_event=emit_event,
        emit_fn=_emit_telemetry,
        catalog_cache_fn=_catalog_cache_enabled,
    )


def _get_institution_radar_data(
    db,
    user_id: str,
    raw_inst: str = "",
    raw_compare: str = "",
    emit_event: bool = True,
    config: dict | None = None,
) -> dict:
    return _inst_svc._get_institution_radar_data(
        db,
        user_id,
        raw_inst=raw_inst,
        raw_compare=raw_compare,
        emit_event=emit_event,
        config=config,
        emit_fn=_emit_telemetry,
        catalog_cache_fn=_catalog_cache_enabled,
    )


@bp.route("/stats/overview")
def overview():
    now_utc = datetime.now(timezone.utc)
    tz_offset = resolve_tz_offset_minutes(request.args, now_utc)

    cache_key = (g.user_id, "overview", tz_offset)
    cached = overview_cache.get(cache_key)
    if cached:
        return jsonify(cached)

    db = get_db()
    metrics = _get_overview_metrics(db, g.user_id, now_utc)
    streak_info = _get_streak_and_target_info(db, g.user_id, now_utc, tz_offset)
    result = {**metrics, **streak_info}

    overview_cache.set(cache_key, result)
    return jsonify(result)


@bp.route("/stats/breakdown")
def breakdown():
    db = get_db()
    by = request.args.get("by", "institution")
    col_map = {
        "institution": ("institution_code", "institution_label"),
        "source": ("source_file", "source_file"),
        "year": ("year", "year"),
        "topic": ("topic", "topic"),
        "area": ("area", "area"),
        "subtema": ("subtema", "subtema"),
        "specialty": ("subtema", "subtema"),
    }
    if by not in col_map:
        return jsonify({"error": "invalid 'by'"}), 400
    col, label_col = col_map[by]
    return jsonify(_rollup_svc.breakdown_data(db, g.user_id, col, label_col))


@bp.route("/stats/timeline")
def timeline():
    days_param = request.args.get("days")
    try:
        days = max(1, min(int(days_param), 3650)) if days_param else None
    except ValueError:
        days = None
    now_utc = datetime.now(timezone.utc)
    tz_offset = resolve_tz_offset_minutes(request.args, now_utc)
    cache_key = (g.user_id, "timeline", days, tz_offset)
    cached = overview_cache.get(cache_key)
    if cached is not None:
        return jsonify(cached)
    db = get_db()
    data = _get_timeline_data(db, g.user_id, days=days, tz_offset=tz_offset, now_utc=now_utc)
    overview_cache.set(cache_key, data)
    return jsonify(data)


@bp.route("/stats/weak-topics")
def weak_topics():
    try:
        min_attempts = int(request.args.get("min_attempts", 5))
    except (TypeError, ValueError):
        min_attempts = 3
    cache_key = (g.user_id, "weak_topics", min_attempts)
    cached = overview_cache.get(cache_key)
    if cached is not None:
        return jsonify(cached)
    db = get_db()
    data = _get_weak_topics_data(db, g.user_id, min_attempts=min_attempts)
    overview_cache.set(cache_key, data)
    return jsonify(data)


@bp.route("/stats/recommendations")
def recommendations():
    user_id = g.user_id
    cache_key = (user_id, "recommendations")
    cached = overview_cache.get(cache_key)
    if cached is not None:
        return jsonify(cached)

    db = get_db()
    out = _rollup_svc.build_recommendations(
        db,
        user_id,
        now_utc=datetime.now(timezone.utc),
        catalog_cache_fn=_catalog_cache_enabled,
    )
    overview_cache.set(cache_key, out)
    return jsonify(out)


@bp.route("/stats/learning-profile")
def learning_profile():
    return jsonify(build_learning_profile(get_db(), g.user_id, subtema=request.args.get("subtema")))


@bp.route("/stats/exam-readiness")
def exam_readiness():
    """Prontidão estimada por instituição/edital com modelo bayesiano Beta-Binomial."""
    db = get_db()
    raw_institution = request.args.get("institution", "")
    return jsonify(_get_exam_readiness_data(db, g.user_id, raw_institution=raw_institution))


@bp.route("/stats/predictive-score")
def predictive_score():
    return jsonify(_rollup_svc.get_predictive_score_data(get_db(), g.user_id))


@bp.route("/stats/at-risk")
def at_risk():
    return jsonify(_get_at_risk_data(get_db(), g.user_id))


@bp.route("/stats/reset", methods=["DELETE"])
def reset_stats():
    db = get_db()
    with db_transaction(db, immediate=True):
        db.execute("DELETE FROM attempts WHERE user_id = ?", (g.user_id,))
        db.execute("DELETE FROM spaced_repetition WHERE user_id = ?", (g.user_id,))
        db.execute("DELETE FROM planner_progress WHERE user_id = ?", (g.user_id,))
        db.execute("DELETE FROM planner_topic_progress WHERE user_id = ?", (g.user_id,))
        db.execute("DELETE FROM theme_progress WHERE user_id = ?", (g.user_id,))
        db.execute("DELETE FROM favorites WHERE user_id = ?", (g.user_id,))
        db.execute("DELETE FROM planner_config WHERE user_id = ?", (g.user_id,))
        db.execute("DELETE FROM planner_schedule WHERE user_id = ?", (g.user_id,))

    invalidate_user_caches(g.user_id)
    return jsonify({"success": True})


@bp.route("/coverage")
def coverage():
    db = get_db()
    area_filter = request.args.get("area", "").strip()
    summary_only = request.args.get("summary_only", "false").lower() == "true"
    return jsonify(_get_coverage_data(db, g.user_id, area_filter=area_filter, summary_only=summary_only))


@bp.route("/stats/distractors")
def distractors():
    """Análise de distratores — qual alternativa errada você mais escolhe por subtema."""
    return jsonify(_get_distractors_data(get_db(), g.user_id))


@bp.route("/stats/benchmark")
def benchmark():
    """Benchmark de concorrentes e corte."""
    db = get_db()
    now_utc = datetime.now(timezone.utc)
    return jsonify(_get_benchmark_data(db, g.user_id, now_utc))


@bp.route("/stats/bottlenecks")
def bottlenecks():
    """Identifica os tópicos prioritários do Caderno de Erros."""
    db = get_db()
    try:
        limit = int(request.args.get("limit", 5))
    except (ValueError, TypeError):
        limit = 5
    return jsonify(_get_bottlenecks_data(db, g.user_id, limit))


@bp.route("/stats/blindspots")
def blindspots():
    """Diagnóstico multidimensional dos pontos cegos do aluno e métricas de superação."""
    db = get_db()
    try:
        limit = int(request.args.get("limit", 6))
    except (ValueError, TypeError):
        limit = 6
    return jsonify(calculate_blindspots(db, g.user_id, limit=limit))


@bp.route("/stats/tri-readiness")
def tri_readiness():
    """Calcula a proficiência TRI acumulada do aluno com projeção para editais."""
    institution = request.args.get("institution", "ENARE")
    return jsonify(_rollup_svc.get_tri_readiness_data(get_db(), g.user_id, institution_code=institution))


@bp.route("/stats/domain-summary")
def domain_summary():
    """Progresso de domínio de focos/subtemas por Grande Área."""
    return jsonify(_get_domain_summary_data(get_db(), g.user_id))


@bp.route("/stats/error-notebook-summary")
def error_notebook_summary():
    """Contador e resumo de questões erradas."""
    return jsonify(_get_error_notebook_summary_data(get_db(), g.user_id))


@bp.route("/dashboard/summary")
def dashboard_summary():
    """Retorna todas as métricas agregadas do Dashboard em um único round-trip com cache por usuário."""
    db = get_db()
    user_id = g.user_id
    now_utc = datetime.now(timezone.utc)
    tz_offset = resolve_tz_offset_minutes(request.args, now_utc)

    cache_key = (user_id, "dashboard_summary", tz_offset)
    cached_payload = overview_cache.get(cache_key)
    if cached_payload is not None:
        return jsonify(cached_payload)

    payload = _rollup_svc.build_dashboard_summary_data(
        db,
        user_id,
        now_utc,
        tz_offset,
        catalog_cache_fn=_catalog_cache_enabled,
    )
    overview_cache.set(cache_key, payload)
    return jsonify(payload)


@bp.route("/stats/institution-radar")
def institution_radar():
    """Radar Comparativo de Bancas por Grande Área e Incerteza Estatística."""
    db = get_db()
    raw_inst = request.args.get("institution", "")
    raw_compare = request.args.get("compare_institution", "")
    return jsonify(_get_institution_radar_data(db, g.user_id, raw_inst=raw_inst, raw_compare=raw_compare))


@bp.route("/stats/analysis-summary")
def analysis_summary():
    """Consolida todas as métricas de Análise, Radar, Pontos Cegos, Cobertura e Prontidão em um único round-trip."""
    db = get_db()
    user_id = g.user_id
    raw_inst = request.args.get("institution", "").strip()[:64]
    raw_compare = request.args.get("compare_institution", "").strip()[:64]
    now_utc = datetime.now(timezone.utc)
    tz_offset = resolve_tz_offset_minutes(request.args, now_utc)

    cache_key = (user_id, "analysis_summary", raw_inst, raw_compare, tz_offset)
    cached = overview_cache.get(cache_key)
    if cached is not None:
        return jsonify(cached)

    rollup = _fetch_attempt_rollup(db, user_id, now_utc)
    config_row = db.execute("SELECT * FROM planner_config WHERE user_id = ?", (user_id,)).fetchone()
    raw_config = dict(config_row) if config_row else {}
    shared_sr_rows = db.execute(
        """
        SELECT q.subtema AS subtema,
               COALESCE(NULLIF(q.subtema, ''), q.topic) AS topic,
               sr.fsrs_card,
               sr.next_review_date
        FROM spaced_repetition sr
        JOIN questions q ON sr.question_id = q.id
        WHERE sr.user_id = ?
        """,
        (user_id,),
    ).fetchall()
    overview_data = {
        **_get_overview_metrics(db, user_id, now_utc, rollup=rollup),
        **_get_streak_and_target_info(db, user_id, now_utc, tz_offset, config=raw_config),
    }

    radar_data = _get_institution_radar_data(
        db, user_id, raw_inst=raw_inst, raw_compare=raw_compare, emit_event=False, config=raw_config
    )
    resolved_inst = raw_inst or radar_data["institution"]["code"]

    payload = {
        "overview": overview_data,
        "learning_profile": build_learning_profile(
            db, user_id, config_row=raw_config, preloaded_fsrs_rows=shared_sr_rows
        ),
        "exam_readiness": _get_exam_readiness_data(
            db, user_id, raw_institution=resolved_inst, emit_event=False
        ),
        "institution_radar": radar_data,
        "blindspots": calculate_blindspots(db, user_id, limit=6, preloaded_fsrs_rows=shared_sr_rows),
        "weak_topics": _get_weak_topics_data(db, user_id, min_attempts=5),
        "distractors": _get_distractors_data(db, user_id),
        "at_risk": _get_at_risk_data(db, user_id, preloaded_sr_rows=shared_sr_rows),
        "timeline_180": _get_timeline_data(db, user_id, days=180, tz_offset=tz_offset, now_utc=now_utc),
        "coverage": _get_coverage_data(db, user_id, area_filter="", summary_only=False),
    }
    overview_cache.set(cache_key, payload)
    return jsonify(payload)


ALLOWED_RADAR_ACTIONS = {"study", "simulado", "review"}


@bp.route("/stats/institution-radar/action", methods=["POST"])
def log_radar_action():
    """Registra evento de ação originada no Radar Comparativo de Bancas."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON body"}), 400
    action = data.get("action")
    if not isinstance(action, str) or action not in ALLOWED_RADAR_ACTIONS:
        return jsonify({"error": "Invalid action", "allowed": sorted(ALLOWED_RADAR_ACTIONS)}), 400

    emit("institution_radar_action_clicked", action=action)
    return jsonify({"success": True})


@bp.route("/stats/focus-radar", methods=["GET"])
def focus_radar():
    """Retorna Domínio de Focos por Prevalência e URL Sniper para a banca selecionada."""
    from .services.focus_radar import build_focus_radar

    db = get_db()
    user_id = getattr(g, "user_id", "1")
    institution = (request.args.get("institution") or "").strip()
    prevalence = (request.args.get("prevalence") or "all").strip().lower()
    if prevalence not in ("all", "prioritario", "alta", "media"):
        prevalence = "all"

    cache_key = (user_id, "focus_radar", institution, prevalence)
    cached = overview_cache.get(cache_key)
    if cached is not None:
        return jsonify(cached)

    payload = build_focus_radar(db, user_id=user_id, institution=institution, prevalence=prevalence)
    overview_cache.set(cache_key, payload)
    return jsonify(payload)


__all__ = [
    "ALLOWED_BREAKDOWN_COLS",
    "ALLOWED_RADAR_ACTIONS",
    "_area_totals_cache",
    "_fetch_all_priority_topics",
    "_fetch_attempt_rollup",
    "_format_planner_config_from_row",
    "_get_at_risk_data",
    "_get_benchmark_data",
    "_get_bottlenecks_data",
    "_get_cached_q_totals_map",
    "_get_coverage_data",
    "_get_distractors_data",
    "_get_domain_summary_data",
    "_get_error_notebook_summary_data",
    "_get_exam_readiness_data",
    "_get_institution_radar_data",
    "_get_overview_metrics",
    "_get_streak_and_target_info",
    "_get_timeline_data",
    "_get_user_area_attempts",
    "_get_user_coverage_stats",
    "_get_weak_topics_data",
    "_institution_area_totals_cache",
    "_q_totals_cache",
    "beta_credible_interval",
    "beta_quantile",
    "bp",
    "calculate_bayesian_readiness",
    "calculate_wilson_ci",
    "get_sample_status",
    "overview_cache",
    "regularized_incomplete_beta",
    "responsible_streak",
    "weighted_beta_credible_interval",
]
