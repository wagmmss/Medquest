"""Fachada de compatibilidade para motores determinísticos e relatórios OSCE."""
from .services.osce_reporting import (
    build_chief_preceptor_review,
    build_medquest_remediation,
    compute_competency_radar_5d,
    evaluate_osce_red_flags,
    generate_competency_radar,
    generate_timeline_post_mortem,
)
from .services.osce_safety_rules import (
    _CLAUSE_SEPARATORS,
    _NEGATION_PREFIXES,
    _clause_has_negation,
    _extract_clause_prefix,
    _find_term_matches,
    _has_affirmative_mention,
    _has_negated_mention,
    _normalize_text,
    evaluate_critical_safety_violations,
)

__all__ = [
    "_CLAUSE_SEPARATORS",
    "_NEGATION_PREFIXES",
    "_clause_has_negation",
    "_extract_clause_prefix",
    "_find_term_matches",
    "_has_affirmative_mention",
    "_has_negated_mention",
    "_normalize_text",
    "build_chief_preceptor_review",
    "build_medquest_remediation",
    "compute_competency_radar_5d",
    "evaluate_critical_safety_violations",
    "evaluate_osce_red_flags",
    "generate_competency_radar",
    "generate_timeline_post_mortem",
]
