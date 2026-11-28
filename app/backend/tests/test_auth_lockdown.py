"""Testes de lockdown de autenticação (PR 0: acesso fechado e remoção do modo visitante)."""
from __future__ import annotations

import sqlite3
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from api import create_app
from api.auth import configured_allowed_user_ids, create_lesson_stream_token
from tests.conftest import SCHEMA_AND_SEED

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.purge_guest_data import purge_guest_rows  # noqa: E402

PROXY_SECRET = "lockdown-test-proxy-secret"


@pytest.fixture
def lockdown_app(tmp_path, monkeypatch):
    dbfile = tmp_path / "lockdown_test.db"
    con = sqlite3.connect(dbfile)
    con.executescript(SCHEMA_AND_SEED)
    con.commit()
    con.close()

    monkeypatch.setenv("MEDQUEST_DB", str(dbfile))
    monkeypatch.setenv("FLASK_API_PROXY_SECRET", PROXY_SECRET)
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)

    app = create_app()
    app.config["TESTING"] = False
    return app


@pytest.fixture
def lockdown_client(lockdown_app):
    return lockdown_app.test_client()


def _install_fake_jwt(monkeypatch, sub: str, email: str = "owner@example.com"):
    from api import auth

    class FakeJwksClient:
        def get_signing_key_from_jwt(self, token):
            assert token == "valid-clerk-jwt"
            return SimpleNamespace(key="fake-public-key")

    monkeypatch.setattr(auth, "jwks_client", FakeJwksClient())
    monkeypatch.setattr(auth, "CLERK_ISSUER", "https://clerk.example.test")
    monkeypatch.setattr(auth, "CLERK_AUDIENCE", None)
    monkeypatch.setattr(auth.jwt, "decode", lambda *_a, **_kw: {"sub": sub, "email": email})


def test_configured_allowed_user_ids_parsing(monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_IDS", " user_abc , user_xyz ,, ")
    assert configured_allowed_user_ids() == frozenset({"user_abc", "user_xyz"})
    monkeypatch.delenv("ALLOWED_USER_IDS", raising=False)
    assert configured_allowed_user_ids() == frozenset()


def test_health_root_is_public(lockdown_client):
    resp = lockdown_client.get("/")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_unauthenticated_requests_return_401(lockdown_client):
    assert lockdown_client.get("/api/stats/overview").status_code == 401
    assert lockdown_client.get("/api/planner/config").status_code == 401
    assert lockdown_client.get("/api/auth/me").status_code == 401


def test_proxy_secret_with_guest_id_and_no_bearer_returns_401(lockdown_client, monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_IDS", "user_owner")
    resp = lockdown_client.get(
        "/api/stats/overview",
        headers={
            "X-Internal-Proxy-Token": PROXY_SECRET,
            "X-Guest-ID": str(uuid.uuid4()),
        },
    )
    assert resp.status_code == 401
    assert resp.get_json() == {"error": "Unauthorized"}


def test_valid_jwt_outside_allowlist_returns_403(lockdown_client, monkeypatch):
    _install_fake_jwt(monkeypatch, sub="user_intruder")
    monkeypatch.setenv("ALLOWED_USER_IDS", "user_owner")

    resp = lockdown_client.get(
        "/api/stats/overview",
        headers={"Authorization": "Bearer valid-clerk-jwt"},
    )
    assert resp.status_code == 403
    assert resp.get_json() == {"error": "Forbidden", "code": "ACCESS_RESTRICTED"}


def test_empty_allowlist_outside_testing_fails_closed_403(lockdown_client, monkeypatch):
    _install_fake_jwt(monkeypatch, sub="user_owner")
    monkeypatch.delenv("ALLOWED_USER_IDS", raising=False)

    resp = lockdown_client.get(
        "/api/planner/config",
        headers={"Authorization": "Bearer valid-clerk-jwt"},
    )
    assert resp.status_code == 403
    assert resp.get_json()["code"] == "ACCESS_RESTRICTED"


def test_valid_jwt_in_allowlist_returns_200(lockdown_client, monkeypatch):
    _install_fake_jwt(monkeypatch, sub="user_owner")
    monkeypatch.setenv("ALLOWED_USER_IDS", "user_owner")

    resp = lockdown_client.get(
        "/api/auth/me",
        headers={"Authorization": "Bearer valid-clerk-jwt"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["user_id"] == "user_owner"


def test_lesson_stream_token_also_enforces_allowlist(lockdown_app, lockdown_client, monkeypatch):
    monkeypatch.setenv("ALLOWED_USER_IDS", "user_owner")
    with lockdown_app.app_context():
        token_intruder = create_lesson_stream_token(1, "user_intruder", "intruder@example.com")
    assert token_intruder is not None
    resp = lockdown_client.get(f"/api/lessons/1/stream?st={token_intruder}")
    assert resp.status_code == 403


def test_purge_guest_data_dry_run_and_apply_preserves_accounts_and_explanations(app):
    from api.db import db_transaction, get_db

    with app.app_context():
        db = get_db()
        with db_transaction(db, immediate=True):
            db.execute(
                "INSERT INTO attempts (question_id, selected_letter, is_correct, answered_at, confidence, user_id) "
                "VALUES (1, 'B', 1, '2026-11-27T00:00:00Z', 'certeza', 'guest:11111111-2222-4333-8444-555555555555')"
            )
            db.execute(
                "INSERT INTO attempts (question_id, selected_letter, is_correct, answered_at, confidence, user_id) "
                "VALUES (1, 'B', 1, '2026-11-27T00:00:00Z', 'certeza', 'user_owner')"
            )
            db.execute(
                "INSERT INTO favorites (question_id, user_id) VALUES (1, 'guest:11111111-2222-4333-8444-555555555555')"
            )
            db.execute("INSERT INTO favorites (question_id, user_id) VALUES (1, 'user_owner')")

        # Dry-run não apaga nada
        before, after_dry = purge_guest_rows(db, apply=False)
        assert before["attempts"] == 1
        assert before["favorites"] == 1
        assert after_dry == before

        # Apply apaga apenas guest:* e preserva conta real e explanations
        before_apply, after_apply = purge_guest_rows(db, apply=True)
        assert before_apply["attempts"] == 1
        assert after_apply["attempts"] == 0
        assert after_apply["favorites"] == 0

        remaining_owner = db.execute(
            "SELECT COUNT(*) AS cnt FROM attempts WHERE user_id = 'user_owner'"
        ).fetchone()["cnt"]
        assert remaining_owner == 1
        remaining_expl = db.execute("SELECT COUNT(*) AS cnt FROM explanations").fetchone()["cnt"]
        assert remaining_expl >= 2
