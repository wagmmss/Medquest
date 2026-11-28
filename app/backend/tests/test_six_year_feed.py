"""Testes do feed JSON e ICS por token, rotação, revogação, CORS (C2) e eventos RFC 5545 (C4)."""
from __future__ import annotations

from api.db import get_db


def _create_token(client) -> dict:
    res = client.post("/api/six-year/feed-token")
    assert res.status_code == 200
    return res.get_json()


def test_feed_json_valid_invalid_revoked_rotated_and_no_pii(app, client):
    # Popular currículo e marcos para provar que NÃO vazam no feed.json
    assert client.patch("/api/six-year/plan", json={"routine_mode_enabled": True}).status_code == 200
    assert client.put(
        "/api/six-year/curriculum/ic_cnpq",
        json={"value": 1, "proof_status": "pdf_pronto", "note": "Sigiloso"},
    ).status_code == 200
    assert client.post(
        "/api/six-year/milestones",
        json={"id": "ms_priv", "titulo": "Marco Privado", "data_iso": "2027-10-15"},
    ).status_code == 201

    tok1 = _create_token(client)
    raw1 = tok1["token"]
    assert f"/api/six-year/feed.json?token={raw1}" in tok1["feed_url"]
    assert f"/api/planner/calendar/feed?token={raw1}" in tok1["ics_url"]

    # Conferir que apenas o hash SHA-256 foi salvo no banco (nunca o token em plaintext)
    with app.app_context():
        db = get_db()
        row = db.execute(
            "SELECT feed_token_hash FROM user_six_year_plan WHERE user_id = '1'"
        ).fetchone()
        assert row is not None
        assert row["feed_token_hash"] != raw1
        assert len(row["feed_token_hash"]) == 64

    # Token válido -> 200 com shape exato e sem currículo/marcos/e-mail
    res_ok = client.get(f"/api/six-year/feed.json?token={raw1}")
    assert res_ok.status_code == 200
    assert "no-store" in res_ok.headers.get("Cache-Control", "")
    payload = res_ok.get_json()
    assert set(payload.keys()) == {
        "version",
        "generated_at",
        "timezone",
        "routine_mode_enabled",
        "rodizio_today",
        "days",
        "weeks",
    }
    assert payload["version"] == 1
    assert payload["timezone"] == "America/Sao_Paulo"
    assert payload["routine_mode_enabled"] is True
    assert len(payload["days"]) == 29  # hoje-14 .. hoje+14
    serialized = str(payload)
    assert "ic_cnpq" not in serialized
    assert "Marco Privado" not in serialized
    assert "Sigiloso" not in serialized

    # Token inválido -> 404
    assert client.get("/api/six-year/feed.json?token=token_invalido_1234567890").status_code == 404

    # Rotacionar token invalida o anterior
    tok2 = _create_token(client)
    raw2 = tok2["token"]
    assert raw2 != raw1
    assert client.get(f"/api/six-year/feed.json?token={raw1}").status_code == 404
    assert client.get(f"/api/six-year/feed.json?token={raw2}").status_code == 200

    # Revogar token -> 204 e 404 na leitura
    assert client.delete("/api/six-year/feed-token").status_code == 204
    assert client.get(f"/api/six-year/feed.json?token={raw2}").status_code == 404


def test_feed_without_token_requires_auth_when_not_testing(app, client):
    app.config["TESTING"] = False
    try:
        res_json = client.get("/api/six-year/feed.json")
        assert res_json.status_code == 401

        res_ics = client.get("/api/planner/calendar/feed")
        assert res_ics.status_code == 401
    finally:
        app.config["TESTING"] = True


def test_feed_cors_allows_github_pages_only_and_blocks_other_origins(app, client):
    tok = _create_token(client)["token"]

    # GET de https://wagmmss.github.io -> permitido
    res_get_ok = client.get(
        f"/api/six-year/feed.json?token={tok}",
        headers={"Origin": "https://wagmmss.github.io"},
    )
    assert res_get_ok.status_code == 200
    assert res_get_ok.headers.get("Access-Control-Allow-Origin") == "https://wagmmss.github.io"

    # OPTIONS preflight de https://wagmmss.github.io -> permitido
    res_opt_ok = client.options(
        "/api/six-year/feed.json",
        headers={
            "Origin": "https://wagmmss.github.io",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res_opt_ok.status_code in (200, 204)
    assert res_opt_ok.headers.get("Access-Control-Allow-Origin") == "https://wagmmss.github.io"

    # Origem não autorizada -> NÃO recebe Access-Control-Allow-Origin
    res_get_evil = client.get(
        f"/api/six-year/feed.json?token={tok}",
        headers={"Origin": "https://evil.example.com"},
    )
    assert res_get_evil.status_code == 200
    assert res_get_evil.headers.get("Access-Control-Allow-Origin") is None

    # https://wagmmss.github.io NÃO deve vazar CORS para outras rotas de /api/*
    res_other = client.get(
        "/api/six-year/summary",
        headers={"Origin": "https://wagmmss.github.io"},
    )
    assert res_other.headers.get("Access-Control-Allow-Origin") is None


def test_ics_feed_with_token_emits_rfc5545_shift_events_without_planner_config(app, client):
    # Cadastrar um plantão SEM configurar planner_config (C4)
    assert client.post(
        "/api/six-year/shifts/batch",
        json={"add": [{"date_iso": "2027-02-04", "kind": "plantao_noturno", "note": "PS Cirurgia"}]},
    ).status_code == 200
    tok = _create_token(client)["token"]

    # Token inválido -> 404
    assert client.get("/api/planner/calendar/feed?token=nao_existe_1234567890").status_code == 404

    # Token válido (simulando acesso público sem sessão Clerk com TESTING=False)
    app.config["TESTING"] = False
    try:
        res = client.get(f"/api/planner/calendar/feed?token={tok}")
        assert res.status_code == 200
        assert "text/calendar" in res.content_type
        ics = res.get_data(as_text=True)
        assert "UID:shift-2027-02-04-plantao_noturno@medquest" in ics
        assert "DTSTART;VALUE=DATE:20270204" in ics
        assert "DTEND;VALUE=DATE:20270205" in ics  # RFC 5545 DTEND exclusivo
        assert "SUMMARY:Plantão noturno" in ics
        assert "Observação: PS Cirurgia" in ics
    finally:
        app.config["TESTING"] = True
