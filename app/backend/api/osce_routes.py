"""Rotas de API para o Simulador de Prova Prática (OSCE) e 2ª Fase."""
from __future__ import annotations

import logging
from flask import Blueprint, abort, g, jsonify, request

from . import osce
from .auth import require_auth
from .db import get_db
from .idempotency import idempotent
from .rate_limit import check_rate_limit

logger = logging.getLogger(__name__)

bp = Blueprint("osce", __name__)


def _resolve_user_id() -> str:
    uid = str(getattr(g, "user_id", "") or "").strip()
    if not uid:
        abort(401)
    return uid


def _json_dict() -> dict | None:
    raw = request.get_json(silent=True)
    if raw is None:
        return {}
    return raw if isinstance(raw, dict) else None


def _parse_elapsed_seconds(val: object) -> int:
    """Extrai com segurança elapsed_seconds evitando Unhandled Exceptions para None/str."""
    if val is None:
        return 0
    try:
        parsed = int(val)  # type: ignore
        return max(0, parsed)
    except (ValueError, TypeError):
        return 0


@bp.route("/osce/stations", methods=["GET"])
def list_stations():
    db = get_db()
    user_id = _resolve_user_id()

    # Garante estações canônicas sem disparar escrita em todo GET
    osce.ensure_osce_stations_seeded(db)

    area = request.args.get("area")
    institution = request.args.get("institution")
    difficulty = request.args.get("difficulty")

    stations = osce.list_osce_stations(
        db=db,
        user_id=user_id,
        area=area,
        institution=institution,
        difficulty=difficulty
    )
    return jsonify({"stations": stations, "count": len(stations)})


@bp.route("/osce/stations/<int:station_id>", methods=["GET"])
def get_station_details(station_id: int):
    if station_id <= 0:
        return jsonify({"error": "station_id inválido"}), 404

    db = get_db()
    station = osce.get_osce_station(db, station_id, include_barema=False)
    if not station:
        return jsonify({"error": "Estação prática não encontrada"}), 404
    return jsonify(station)


@bp.route("/osce/sessions/start", methods=["POST"])
@require_auth
@idempotent(user_resolver=_resolve_user_id)
def start_session():
    db = get_db()
    user_id = _resolve_user_id()
    body = _json_dict()
    if body is None:
        return jsonify({"error": "Payload JSON inválido"}), 400
    raw_station_id = body.get("station_id")
    circuit_session_id = body.get("circuit_session_id")
    mode = body.get("mode", "blind")

    if raw_station_id is None:
        return jsonify({"error": "station_id é obrigatório"}), 400

    try:
        station_id = int(raw_station_id)
        if station_id <= 0:
            return jsonify({"error": "station_id deve ser um número inteiro positivo"}), 400
    except (ValueError, TypeError):
        return jsonify({"error": "station_id deve ser um número inteiro válido"}), 400

    try:
        session = osce.start_osce_session(
            db=db,
            station_id=station_id,
            user_id=user_id,
            circuit_session_id=circuit_session_id,
            mode=mode,
        )
        return jsonify(session), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@bp.route("/osce/sessions/<session_id>/interact", methods=["POST"])
@require_auth
def interact_session(session_id: str):
    user_id = _resolve_user_id()
    rl_resp = check_rate_limit("osce_interact", auth_limit=45, window_seconds=60)
    if rl_resp is not None:
        return rl_resp

    db = get_db()
    body = _json_dict()
    if body is None:
        return jsonify({"error": "Payload JSON inválido"}), 400

    raw_msg = body.get("message") or body.get("utterance") or ""
    message = raw_msg.strip()[:1500] if isinstance(raw_msg, str) else ""
    target = body.get("target", "PATIENT")
    if not isinstance(target, str):
        target = "PATIENT"
    raw_vitals = body.get("current_vitals")
    current_vitals = raw_vitals if isinstance(raw_vitals, dict) else None
    elapsed_seconds = _parse_elapsed_seconds(body.get("elapsed_seconds"))

    if not message:
        return jsonify({"error": "Mensagem não pode ser vazia"}), 400

    try:
        result = osce.interact_osce_session(
            db=db,
            session_id=session_id,
            user_id=user_id,
            message=message,
            elapsed_seconds=elapsed_seconds,
            target=target,
            current_vitals=current_vitals
        )
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@bp.route("/osce/sessions/<session_id>/dispatch_speech", methods=["POST"])
@require_auth
def dispatch_speech(session_id: str):
    """Dispatcher unificado de voz para modo Hands-Free de alta fidelidade."""
    user_id = _resolve_user_id()
    rl_resp = check_rate_limit("osce_dispatch", auth_limit=45, window_seconds=60)
    if rl_resp is not None:
        return rl_resp

    db = get_db()
    body = _json_dict()
    if body is None:
        return jsonify({"error": "Payload JSON inválido"}), 400

    raw_msg = body.get("message", "")
    message = raw_msg.strip()[:1500] if isinstance(raw_msg, str) else ""
    elapsed_seconds = _parse_elapsed_seconds(body.get("elapsed_seconds"))

    if not message:
        return jsonify({"error": "Mensagem transcrita não pode ser vazia"}), 400

    try:
        result = osce.dispatch_osce_speech(
            db=db,
            session_id=session_id,
            user_id=user_id,
            message=message,
            elapsed_seconds=elapsed_seconds
        )
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404



@bp.route("/osce/sessions/<session_id>/action", methods=["POST"])
@require_auth
def execute_action(session_id: str):
    db = get_db()
    user_id = _resolve_user_id()
    body = _json_dict()
    if body is None:
        return jsonify({"error": "Payload JSON inválido"}), 400

    raw_type = body.get("action_type", "")
    raw_target = body.get("action_target", "")
    action_type = raw_type.strip()[:64] if isinstance(raw_type, str) else ""
    action_target = raw_target.strip()[:120] if isinstance(raw_target, str) else ""
    elapsed_seconds = _parse_elapsed_seconds(body.get("elapsed_seconds"))

    if not action_type or not action_target:
        return jsonify({"error": "action_type e action_target são obrigatórios"}), 400

    try:
        result = osce.execute_osce_action(
            db=db,
            session_id=session_id,
            user_id=user_id,
            action_type=action_type,
            action_target=action_target,
            elapsed_seconds=elapsed_seconds
        )
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@bp.route("/osce/sessions/<session_id>/finish", methods=["POST"])
@require_auth
@idempotent(user_resolver=_resolve_user_id)
def finish_session(session_id: str):
    user_id = _resolve_user_id()
    rl_resp = check_rate_limit("osce_finish", auth_limit=20, window_seconds=60)
    if rl_resp is not None:
        return rl_resp

    db = get_db()
    body = _json_dict()
    if body is None:
        return jsonify({"error": "Payload JSON inválido"}), 400
    raw_notes = body.get("conduct_notes")
    conduct_notes = raw_notes[:4000] if isinstance(raw_notes, str) else None

    try:
        result = osce.finish_osce_session(
            db=db,
            session_id=session_id,
            user_id=user_id,
            conduct_notes=conduct_notes,
        )
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@bp.route("/osce/sessions/<session_id>/report", methods=["GET"])
@require_auth
def get_report(session_id: str):
    db = get_db()
    user_id = _resolve_user_id()

    report = osce.get_osce_session_report(db, session_id, user_id)
    if not report:
        return jsonify({"error": "Relatório de sessão não encontrado"}), 404
    return jsonify(report)


@bp.route("/osce/drugs", methods=["GET"])
def get_emergency_drugs():
    """Retorna o catálogo oficial de medicamentos de emergência para autocompletion na prescrição."""
    drugs = osce.get_emergency_drugs_catalog()
    return jsonify({"drugs": drugs, "count": len(drugs)})


@bp.route("/osce/procedures", methods=["GET"])
def get_procedures():
    """Retorna o catálogo de procedimentos beira-leito e janelas E-FAST para o manequim 2D."""
    procedures = osce.get_procedures_catalog()
    return jsonify({"procedures": procedures, "count": len(procedures)})


@bp.route("/osce/sessions/<session_id>/prescribe", methods=["POST"])
@require_auth
def prescribe_drugs(session_id: str):
    """Assina e processa uma prescrição médica estruturada na sala de emergência."""
    db = get_db()
    user_id = _resolve_user_id()
    body = _json_dict()
    if body is None:
        return jsonify({"error": "Payload JSON inválido"}), 400

    prescription_items = body.get("prescription", [])
    elapsed_seconds = _parse_elapsed_seconds(body.get("elapsed_seconds"))

    if not isinstance(prescription_items, list) or not prescription_items:
        return jsonify({"error": "prescription deve ser uma lista com ao menos 1 item."}), 400

    try:
        result = osce.prescribe_osce_drugs(
            db=db,
            session_id=session_id,
            user_id=user_id,
            prescription_items=prescription_items,
            elapsed_seconds=elapsed_seconds
        )
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@bp.route("/osce/sessions/<session_id>/procedure", methods=["POST"])
@require_auth
def perform_procedure(session_id: str):
    """Executa um procedimento invasivo ou varredura ultrassonográfica E-FAST no manequim 2D."""
    db = get_db()
    user_id = _resolve_user_id()
    body = _json_dict()
    if body is None:
        return jsonify({"error": "Payload JSON inválido"}), 400

    raw_proc = body.get("procedure_type", "")
    raw_site = body.get("anatomical_site", "")
    procedure_type = raw_proc.strip()[:64] if isinstance(raw_proc, str) else ""
    anatomical_site = raw_site.strip()[:64] if isinstance(raw_site, str) else ""
    elapsed_seconds = _parse_elapsed_seconds(body.get("elapsed_seconds"))

    if not procedure_type or not anatomical_site:
        return jsonify({"error": "procedure_type e anatomical_site são obrigatórios."}), 400

    try:
        result = osce.perform_osce_procedure(
            db=db,
            session_id=session_id,
            user_id=user_id,
            procedure_type=procedure_type,
            anatomical_site=anatomical_site,
            elapsed_seconds=elapsed_seconds
        )
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@bp.route("/osce/sessions/<session_id>/live_feedback", methods=["GET"])
@require_auth
def get_session_live_feedback(session_id: str):
    """Consulta o progresso em tempo real do barema para o Modo Treino com Preceptor Fantasma."""
    db = get_db()
    user_id = _resolve_user_id()
    elapsed_seconds = _parse_elapsed_seconds(request.args.get("elapsed_seconds"))

    try:
        feedback = osce.get_osce_live_feedback(
            db=db,
            session_id=session_id,
            user_id=user_id,
            elapsed_seconds=elapsed_seconds
        )
        if feedback.get("mode") != "guided":
            return jsonify({"error": "Feedback ao vivo indisponível em modo prova cega."}), 403
        return jsonify(feedback)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404


@bp.route("/osce/circuits/plan", methods=["GET"])
def get_circuit_plan():
    """Retorna o plano ordenado de 5 estações do circuito misto de treino cobrindo as 5 especialidades."""
    db = get_db()
    osce.ensure_osce_stations_seeded(db)
    institution = request.args.get("institution", "USP-RP")
    user_id = _resolve_user_id()
    plan = osce.get_circuit_plan(db, institution=institution, user_id=user_id)
    return jsonify(plan)


@bp.route("/osce/circuits/<circuit_id>/summary", methods=["GET"])
@require_auth
def get_circuit_summary(circuit_id: str):
    """Retorna o espelho consolidado da 2ª fase com nota global de 0 a 50 pontos."""
    db = get_db()
    user_id = _resolve_user_id()
    summary = osce.get_circuit_summary(db, circuit_id=circuit_id, user_id=user_id)
    return jsonify(summary)
