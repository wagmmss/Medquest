"""Testes da migration 027_central_6ano.sql (aplicação limpa, idempotência e CHECK constraints)."""
from __future__ import annotations

import sqlite3

import pytest

from api.db import apply_pending_migrations, get_db


def test_migration_027_applied_and_idempotent(app):
    with app.app_context():
        db = get_db()
        tables = {
            r["name"]
            for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        expected = {
            "user_six_year_plan",
            "user_week_marcha",
            "user_shifts",
            "user_day_overrides",
            "user_curriculum_entries",
            "user_r1_milestones",
        }
        assert expected.issubset(tables)

        idx = db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index' AND name = 'idx_user_six_year_plan_feed_token'"
        ).fetchone()
        assert idx is not None

        # Reaplicar migrations não deve falhar nem duplicar registro em schema_migrations
        apply_pending_migrations(db)
        rows = db.execute(
            "SELECT migration_id FROM schema_migrations WHERE migration_id = '027_central_6ano.sql'"
        ).fetchall()
        assert len(rows) == 1


def test_migration_027_check_constraints_reject_invalid_values(app):
    with app.app_context():
        db = get_db()
        now = "2027-02-04T12:00:00+00:00"

        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """
                INSERT INTO user_six_year_plan (user_id, enamed_concept, updated_at)
                VALUES ('u1', 2, ?)
                """,
                (now,),
            )

        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """
                INSERT INTO user_week_marcha (user_id, week_iso, marcha_id, updated_at)
                VALUES ('u1', '2027-02-01', 'invalid_marcha', ?)
                """,
                (now,),
            )

        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """
                INSERT INTO user_shifts (user_id, date_iso, kind, updated_at)
                VALUES ('u1', '2027-02-04', 'plantao_36h', ?)
                """,
                (now,),
            )

        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """
                INSERT INTO user_day_overrides (user_id, date_iso, mode, updated_at)
                VALUES ('u1', '2027-02-04', 'ferias', ?)
                """,
                (now,),
            )

        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """
                INSERT INTO user_curriculum_entries (user_id, item_id, proof_status, updated_at)
                VALUES ('u1', 'ic_cnpq', 'invalido', ?)
                """,
                (now,),
            )

        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """
                INSERT INTO user_r1_milestones (user_id, id, titulo, data_iso, categoria, updated_at)
                VALUES ('u1', 'm1', 'Teste', '2027-10-10', 'outra', ?)
                """,
                (now,),
            )
