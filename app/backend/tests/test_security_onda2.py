"""Testes de regressão de segurança da Onda 2 (AppSec Backend)."""
from __future__ import annotations

import uuid

from api import osce
from api.db import get_db
from api.gemini_pool import _sanitize_error_reason
from api.observability import performance_snapshot
from api.rate_limit import check_rate_limit, reset_rate_limits


def test_rate_limit_enforces_429_and_retry_after(app):
    """Garante retorno 429 com header Retry-After quando RATE_LIMIT_ENABLED está ativo."""
    reset_rate_limits()
    app.config["RATE_LIMIT_ENABLED"] = True
    try:
        user_id = f"user_{uuid.uuid4().hex[:8]}"
        with app.test_request_context("/api/questions/1/ask_ai", environ_base={"REMOTE_ADDR": "10.10.0.1"}):
            from flask import g

            g.user_id = user_id
            assert check_rate_limit("onda2-test", auth_limit=2, window_seconds=60) is None
            assert check_rate_limit("onda2-test", auth_limit=2, window_seconds=60) is None
            blocked = check_rate_limit("onda2-test", auth_limit=2, window_seconds=60)
            assert blocked is not None
            assert blocked.status_code == 429
            assert int(blocked.headers.get("Retry-After", "0")) >= 1
    finally:
        app.config.pop("RATE_LIMIT_ENABLED", None)
        reset_rate_limits()


def test_unauthenticated_proxy_headers_rejected_with_401(app, client, monkeypatch):
    """Sem JWT Bearer válido, nem proxy secret + X-Guest-ID + X-User-Email concedem acesso."""
    monkeypatch.setenv("CURATOR_EMAILS", "curator@medquest.live")
    monkeypatch.setenv("FLASK_API_PROXY_SECRET", "test-onda2-proxy-secret")
    spoofed_headers = {
        "X-Internal-Proxy-Token": "test-onda2-proxy-secret",
        "X-Guest-ID": str(uuid.uuid4()),
        "X-User-Email": "curator@medquest.live",
    }

    prev_testing = app.config.get("TESTING", True)
    app.config["TESTING"] = False
    try:
        assert client.get("/api/auth/me", headers=spoofed_headers).status_code == 401
        assert client.get("/api/ai/health", headers=spoofed_headers).status_code == 401
        assert client.patch(
            "/api/lessons/1/mapping",
            headers=spoofed_headers,
            json={"subtema": "Cardiologia"},
        ).status_code == 401
    finally:
        app.config["TESTING"] = prev_testing


def test_non_curator_authenticated_blocked_from_curator_routes(client, monkeypatch):
    """Usuário autenticado fora de CURATOR_EMAILS recebe 403 em /api/ai/health e /mapping."""
    monkeypatch.setenv("CURATOR_EMAILS", "curator@medquest.live")
    headers = {"X-User-ID": "user_regular_123", "X-User-Email": "aluno@medquest.live"}

    assert client.get("/api/ai/health", headers=headers).status_code == 403
    assert client.patch("/api/lessons/1/mapping", headers=headers, json={"subtema": "Nefro"}).status_code == 403

    curator_headers = {"X-User-ID": "user_curator_1", "X-User-Email": "curator@medquest.live"}
    health_ok = client.get("/api/ai/health", headers=curator_headers)
    assert health_ok.status_code == 200


def test_gemini_error_sanitization_strips_project_ids_and_urls():
    """Remove project numbers e URLs internas de mensagens de cooldown."""
    raw = "Quota exceeded on projects/123456789012/locations/us-central1 at https://internal.googleapis.com/v1/models"
    cleaned = _sanitize_error_reason(raw)
    assert "123456789012" not in cleaned
    assert "https://" not in cleaned


def test_objective_is_correct_tampering_ignored_on_attempt_and_batch(app, client):
    """Questões objetivas ignoram is_correct enviado pelo cliente em /attempt e /attempt/batch."""
    headers = {"X-User-ID": "sec-tamper-user"}

    # Questão 2 tem gabarito A; enviando letra B + is_correct=True deve gravar False.
    single = client.post(
        "/api/questions/2/attempt",
        headers=headers,
        json={"selected_letter": "B", "is_correct": True, "confidence": "certeza"},
    )
    assert single.status_code == 200
    assert single.get_json()["is_correct"] is False

    batch = client.post(
        "/api/attempt/batch",
        headers=headers,
        json={
            "attempts": [
                {
                    "question_id": 2,
                    "selected_letter": "B",
                    "is_correct": True,
                    "confidence": "chutei",
                }
            ]
        },
    )
    assert batch.status_code == 200

    with app.app_context():
        rows = get_db().execute(
            "SELECT is_correct FROM attempts WHERE user_id = ? AND question_id = 2 ORDER BY id ASC",
            ("sec-tamper-user",),
        ).fetchall()
        assert len(rows) == 2
        assert all(int(r["is_correct"]) == 0 for r in rows)


def test_osce_blind_mode_hides_live_feedback_and_matched_criteria(app, client):
    """Sessão OSCE em modo blind bloqueia /live_feedback (403) e oculta matched_criteria."""
    user_id = "sec-osce-blind-user"
    headers = {"X-User-ID": user_id}

    with app.app_context():
        db = get_db()
        osce.seed_osce_stations(db)
        station = db.execute("SELECT id FROM osce_stations ORDER BY id ASC LIMIT 1").fetchone()
        assert station is not None
        session = osce.start_osce_session(db, station["id"], user_id, mode="blind")
        sid = session["session_id"]

    live_resp = client.get(f"/api/osce/sessions/{sid}/live_feedback", headers=headers)
    assert live_resp.status_code == 403

    prescribe_resp = client.post(
        f"/api/osce/sessions/{sid}/prescribe",
        headers=headers,
        json={"prescription": [{"drug_id": "adrenalina", "dose": "1 mg IV"}], "elapsed_seconds": 30},
    )
    assert prescribe_resp.status_code == 200
    assert prescribe_resp.get_json().get("matched_criteria") == []


def test_push_subscribe_blocks_ssrf_endpoint(client, monkeypatch):
    """Endpoint POST /api/notifications/subscribe rejeita URL interna/SSRF com HTTP 400."""
    monkeypatch.setenv("WEB_PUSH_ALLOWED_HOSTS", "fcm.googleapis.com")
    resp = client.post(
        "/api/notifications/subscribe",
        headers={"X-User-ID": "sec-push-user"},
        json={
            "endpoint": "https://127.0.0.1/internal-webhook",
            "keys": {"p256dh": "test-p256dh-key", "auth": "test-auth-secret"},
        },
    )
    assert resp.status_code == 400


def test_observability_collapses_unmatched_404_paths(client):
    """Rotas 404 arbitrárias não criam alta cardinalidade nas métricas de observabilidade."""
    secret_slug = "secret-probe-path-999888"
    resp = client.get(f"/api/{secret_slug}")
    assert resp.status_code == 404

    snap = performance_snapshot()
    routes = snap.get("routes") or []
    route_names = [str(item.get("route") or "") for item in routes]
    assert all(secret_slug not in name for name in route_names)
    assert "<unmatched>" in route_names


def test_sessions_and_presets_reject_invalid_type_and_oversized_payloads(client):
    """Valida allowlist de session_type e limites de tamanho em /sessions e /presets."""
    headers = {"X-User-ID": "sec-payload-user"}

    bad_type = client.put("/api/sessions/../../etc/passwd", headers=headers, json={"x": 1})
    assert bad_type.status_code in (400, 404)

    bad_type_api = client.put("/api/sessions/admin_dump", headers=headers, json={"x": 1})
    assert bad_type_api.status_code == 400

    oversized_session = client.put(
        "/api/sessions/quiz",
        headers=headers,
        json={"blob": "a" * (260 * 1024)},
    )
    assert oversized_session.status_code == 413

    oversized_preset = client.post(
        "/api/presets",
        headers=headers,
        json={"name": "Grande", "filters": {"pad": "x" * (18 * 1024)}},
    )
    assert oversized_preset.status_code == 413


def test_serve_image_blocks_path_traversal(client):
    """Impede leitura de arquivos fora de static/ via /api/images/."""
    r1 = client.get("/api/images/../../api/auth.py")
    assert r1.status_code in (400, 404)
    r2 = client.get("/api/images/%2e%2e/%2e%2e/api/auth.py")
    assert r2.status_code in (400, 404)


def test_auth_fails_closed_without_credentials_when_not_testing(app, client, monkeypatch):
    """Fora do modo TESTING, requisições sem JWT ou proxy secret válido recebem 401."""
    monkeypatch.setenv("FLASK_API_PROXY_SECRET", "test-onda2-proxy-secret")
    prev_testing = app.config.get("TESTING", True)
    app.config["TESTING"] = False
    try:
        assert client.get("/api/auth/me").status_code == 401
        assert client.get(
            "/api/auth/me",
            headers={"X-User-ID": "spoofed", "X-Internal-Proxy-Token": "wrong-secret"},
        ).status_code == 401
    finally:
        app.config["TESTING"] = prev_testing

