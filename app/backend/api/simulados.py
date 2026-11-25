"""Blueprint de Simulados: geração de provas USP/personalizadas, editais oficiais, sessões e TRI."""
from __future__ import annotations

import json
import random
from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, request

from .db import db_transaction, get_db
from .edital_profiles import get_canonical_institution, resolve_institution_codes
from .idempotency import complete_active_lease, idempotent
from .observability import record_domain_event
from .schemas import SimuladoCustomIn, SimuladoSessionIn, ValidationError, validation_errors
from .services.questions_service import _sample_ids
from .tri_engine import evaluate_tri_performance

bp = Blueprint("simulados", __name__)

_AREA_GROUPS = (
    ("Cirurgia",),
    ("Clínica Médica",),
    ("Pediatria",),
    ("Ginecologia e Obstetrícia",),
    ("Medicina Preventiva", "Medicina Preventiva e Social"),
)

_INSTITUTION_META = {
    "USP-SP": {
        "name": "USP - São Paulo",
        "full_name": "Universidade de São Paulo (Capital)",
        "standard_duration": 300,
        "badge_color": "blue",
        "typical_questions": 120,
    },
    "USP-RP": {
        "name": "USP - Ribeirão Preto",
        "full_name": "Faculdade de Medicina de Ribeirão Preto (USP)",
        "standard_duration": 240,
        "badge_color": "indigo",
        "typical_questions": 100,
    },
    "UNICAMP": {
        "name": "UNICAMP",
        "full_name": "Universidade Estadual de Campinas",
        "standard_duration": 240,
        "badge_color": "rose",
        "typical_questions": 80,
    },
    "UNIFESP": {
        "name": "UNIFESP",
        "full_name": "Escola Paulista de Medicina (EPM / UNIFESP)",
        "standard_duration": 240,
        "badge_color": "cyan",
        "typical_questions": 100,
    },
    "SUS-SP": {
        "name": "SUS-SP",
        "full_name": "Secretaria de Estado da Saúde de São Paulo",
        "standard_duration": 240,
        "badge_color": "emerald",
        "typical_questions": 100,
    },
    "ENARE": {
        "name": "ENARE",
        "full_name": "Exame Nacional de Residência",
        "standard_duration": 300,
        "badge_color": "amber",
        "typical_questions": 100,
    },
    "FAMEMA": {
        "name": "FAMEMA",
        "full_name": "Faculdade de Medicina de Marília",
        "standard_duration": 240,
        "badge_color": "sky",
        "typical_questions": 100,
    },
    "FAMERP": {
        "name": "FAMERP",
        "full_name": "Faculdade de Medicina de São José do Rio Preto",
        "standard_duration": 240,
        "badge_color": "teal",
        "typical_questions": 80,
    },
    "HSL": {
        "name": "Sírio-Libanês",
        "full_name": "Hospital Sírio-Libanês",
        "standard_duration": 240,
        "badge_color": "purple",
        "typical_questions": 100,
    },
    "EINSTEIN": {
        "name": "Einstein",
        "full_name": "Hospital Israelita Albert Einstein",
        "standard_duration": 240,
        "badge_color": "slate",
        "typical_questions": 75,
    },
    "IAMSPE": {
        "name": "IAMSPE",
        "full_name": "Instituto de Assistência Médica ao Servidor Público Estadual",
        "standard_duration": 240,
        "badge_color": "orange",
        "typical_questions": 100,
    },
    "SCMSP": {
        "name": "Santa Casa SP",
        "full_name": "Irmandade da Santa Casa de Misericórdia de São Paulo",
        "standard_duration": 240,
        "badge_color": "pink",
        "typical_questions": 100,
    },
}


def _fetch_shuffled_simulado_rows(db, all_ids: list[int]) -> list[dict]:
    if not all_ids:
        return []
    placeholders = ",".join("?" * len(all_ids))
    rows = db.execute(
        f"""SELECT q.id, q.source_file, q.source_number, q.year, q.institution_code,
                   q.institution_label, q.topic, q.area, q.subtema, q.editorial_status
            FROM questions q WHERE q.id IN ({placeholders})""",
        all_ids,
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["is_autoral"] = bool(
            d.get("editorial_status") == "autoral"
            or (d.get("source_file") and "AUTORAL" in str(d.get("source_file")).upper())
        )
        out.append(d)
    random.shuffle(out)
    return out


@bp.route("/simulado/usp")
def simulado_usp():
    db = get_db()
    all_ids: list[int] = []
    for area_aliases in _AREA_GROUPS:
        ph = ",".join("?" * len(area_aliases))
        where = f"q.institution_code IN ('USP-SP', 'USP-RP') AND q.area IN ({ph}) AND q.missing_alts = 0"
        all_ids.extend(_sample_ids(db, where, area_aliases, 24))
    return jsonify(_fetch_shuffled_simulado_rows(db, all_ids))


@bp.route("/simulado/custom", methods=["POST"])
def simulado_custom():
    db = get_db()
    try:
        data = SimuladoCustomIn.model_validate(request.get_json(force=True) or {})
    except ValidationError as e:
        return jsonify({"error": "invalid input", "details": validation_errors(e)}), 400
    raw_institutions = [value[:64] for value in data.institutions]
    institutions = []
    for inst in raw_institutions:
        institutions.extend(resolve_institution_codes(inst))
    institutions = list(dict.fromkeys(institutions))
    years = [value[:4] for value in data.years]
    q_per_area = data.questions_per_area

    base_clauses = ["q.missing_alts = 0"]
    base_params: list = []

    if institutions:
        placeholders = ",".join("?" * len(institutions))
        base_clauses.append(f"q.institution_code IN ({placeholders})")
        base_params.extend(institutions)

    if years:
        placeholders = ",".join("?" * len(years))
        base_clauses.append(f"q.year IN ({placeholders})")
        base_params.extend(years)

    all_ids: list[int] = []
    for area_aliases in _AREA_GROUPS:
        ph = ",".join("?" * len(area_aliases))
        clauses = base_clauses + [f"q.area IN ({ph})"]
        params = base_params + list(area_aliases)
        all_ids.extend(_sample_ids(db, " AND ".join(clauses), tuple(params), q_per_area))

    return jsonify(_fetch_shuffled_simulado_rows(db, all_ids))


@bp.route("/simulado/official-exams", methods=["GET"])
def simulado_official_exams():
    db = get_db()
    include_similar = request.args.get("similar_institutions") in ("1", "true", "True")
    target_institutions = ["USP-SP", "USP-RP", "UNICAMP", "UNIFESP", "SUS-SP"]
    if include_similar:
        target_institutions.extend(["ENARE", "FAMEMA", "FAMERP", "HSL", "EINSTEIN", "IAMSPE", "SCMSP"])

    inst_codes_query = []
    for inst in target_institutions:
        inst_codes_query.extend(resolve_institution_codes(inst))
    inst_codes_query = list(dict.fromkeys(inst_codes_query))
    placeholders = ",".join("?" * len(inst_codes_query))

    rows = db.execute(
        f"""
        SELECT institution_code, year, COUNT(*) as n
        FROM questions
        WHERE missing_alts = 0
          AND institution_code IN ({placeholders})
        GROUP BY institution_code, year
        ORDER BY year DESC
    """,
        inst_codes_query,
    ).fetchall()

    grouped_years: dict[str, dict] = {inst: {} for inst in target_institutions}
    for r in rows:
        canon = get_canonical_institution(r["institution_code"])
        if canon in grouped_years and r["year"]:
            grouped_years[canon][r["year"]] = grouped_years[canon].get(r["year"], 0) + r["n"]

    exams = []
    for inst in target_institutions:
        years_dict = grouped_years.get(inst, {})
        meta = _INSTITUTION_META[inst]
        typical_q = meta.get("typical_questions", 100)
        duration = meta.get("standard_duration", 240)
        editions = [
            {
                "year": y,
                "total_available": years_dict[y],
                "recommended_questions": min(years_dict[y], typical_q),
                "duration_minutes": duration,
            }
            for y in sorted(years_dict.keys(), reverse=True)
        ]
        exams.append({
            "institution_code": inst,
            "name": meta["name"],
            "full_name": meta["full_name"],
            "badge_color": meta["badge_color"],
            "editions": editions,
        })

    return jsonify({"exams": exams})


@bp.route("/simulado/sessions", methods=["GET"])
def get_simulado_sessions():
    db = get_db()
    rows = db.execute(
        """
        SELECT id, client_session_id, planned_duration_seconds, elapsed_seconds,
               total_questions, answered_count, correct_count,
               filters_json, area_results_json, completed_at
        FROM simulado_sessions
        WHERE user_id = ?
        ORDER BY completed_at DESC
        LIMIT 30
    """,
        (g.user_id,),
    ).fetchall()

    sessions = []
    for r in rows:
        d = dict(r)
        try:
            d["filters"] = json.loads(d.pop("filters_json") or "{}")
        except Exception:
            d["filters"] = {}
        try:
            d["area_results"] = json.loads(d.pop("area_results_json") or "[]")
        except Exception:
            d["area_results"] = []

        total = d.get("total_questions", 0)
        correct = d.get("correct_count", 0)
        d["accuracy_percent"] = round((correct / total) * 100, 1) if total > 0 else 0.0
        sessions.append(d)

    return jsonify({"sessions": sessions})


@bp.route("/simulado/sessions/<session_id>", methods=["DELETE"])
def delete_simulado_session(session_id):
    db = get_db()
    with db_transaction(db, immediate=True):
        res = db.execute(
            "DELETE FROM simulado_sessions WHERE client_session_id = ? AND user_id = ?",
            (session_id, g.user_id),
        )
    return jsonify({"success": True, "deleted": res.rowcount > 0})


@bp.route("/simulado/sessions", methods=["POST"])
@idempotent()
def save_simulado_session():
    db = get_db()
    try:
        data = SimuladoSessionIn.model_validate(request.get_json(force=True) or {})
    except ValidationError as e:
        return jsonify({"error": "invalid input", "details": validation_errors(e)}), 400

    completed_at = datetime.now(timezone.utc).isoformat()
    with db_transaction(db, immediate=True):
        db.execute(
            """INSERT INTO simulado_sessions
                (client_session_id, planned_duration_seconds, elapsed_seconds, total_questions, answered_count,
                 correct_count, filters_json, area_results_json, completed_at, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, client_session_id) DO UPDATE SET
                  planned_duration_seconds=excluded.planned_duration_seconds, elapsed_seconds=excluded.elapsed_seconds,
                  total_questions=excluded.total_questions, answered_count=excluded.answered_count,
                  correct_count=excluded.correct_count, filters_json=excluded.filters_json,
                  area_results_json=excluded.area_results_json, completed_at=excluded.completed_at
            """,
            (
                data.client_session_id,
                data.planned_duration_seconds,
                data.elapsed_seconds,
                data.total_questions,
                data.answered_count,
                data.correct_count,
                json.dumps(data.filters),
                json.dumps(data.area_results),
                completed_at,
                g.user_id,
            ),
        )
        resp_data = {"success": True}
        complete_active_lease(200, resp_data)

    record_domain_event(
        "simulado_completed",
        user_id=g.user_id,
        session_id=data.client_session_id,
        total_questions=data.total_questions,
        answered_count=data.answered_count,
        correct_count=data.correct_count,
        elapsed_seconds=data.elapsed_seconds,
    )
    return jsonify(resp_data)


@bp.route("/simulado/tri-evaluation", methods=["POST"])
def simulado_tri_evaluation():
    db = get_db()
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Payload JSON inválido"}), 400
    attempts = data.get("responses") if "responses" in data else data.get("attempts", [])
    if not isinstance(attempts, list):
        attempts = []
    if len(attempts) > 500:
        return jsonify({"error": "Limite máximo de 500 itens por avaliação TRI"}), 400
    institution = data.get("institution_code") or data.get("institution") or "ENARE"
    return jsonify(evaluate_tri_performance(db, attempts, institution_code=str(institution)))
