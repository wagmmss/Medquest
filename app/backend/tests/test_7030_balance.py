"""Testes do saldo real 70/30 nos últimos 7 dias locais."""
from __future__ import annotations

from datetime import date

from api.db import get_db
from api.services.six_year_routine import compute_7030_balance


def test_7030_balance_empty_returns_null_percentages(app):
    with app.app_context():
        db = get_db()
        block = {"id": "cirurgia", "area": "Cirurgia", "ancora_areas": ["Cirurgia"]}
        bal = compute_7030_balance(db, "u1", date(2027, 2, 4), block)
        assert bal["total"] == 0
        assert bal["anchor"] == 0
        assert bal["other"] == 0
        assert bal["anchor_pct"] is None
        assert bal["other_pct"] is None
        assert bal["target_anchor_pct"] == 70
        assert bal["window_from"] == "2027-01-29"
        assert bal["window_to"] == "2027-02-04"


def test_7030_balance_7_day_local_window_and_area_normalization(app):
    with app.app_context():
        db = get_db()
        # Criar questão de Cirurgia Geral (normaliza para Cirurgia) e Clínica Médica
        db.execute(
            """
            INSERT INTO questions (id, area, subtema, stem, correct_letter, missing_alts, year, institution_code, institution_label)
            VALUES (10, 'Cirurgia Geral', 'Trauma', 'Q10?', 'A', 0, 2025, 'USP-SP', 'USP')
            """
        )
        # Janela local para today=2027-02-04 BRT: 2027-01-29 00:00 BRT (03:00 UTC) até 2027-02-04 23:59 BRT (2027-02-05 02:59 UTC)
        # Tentativa dentro da janela: 2027-02-05 02:30 UTC == 2027-02-04 23:30 BRT (conta!)
        db.execute(
            "INSERT INTO attempts (question_id, selected_letter, is_correct, answered_at, user_id) VALUES (10, 'A', 1, '2027-02-05T02:30:00+00:00', 'u1')"
        )
        # Tentativa dentro da janela: 2027-01-29 04:00 UTC == 2027-01-29 01:00 BRT (Clínica Médica -> other)
        db.execute(
            "INSERT INTO attempts (question_id, selected_letter, is_correct, answered_at, user_id) VALUES (1, 'B', 1, '2027-01-29T04:00:00+00:00', 'u1')"
        )
        # Tentativa fora da janela: 2027-01-29 02:00 UTC == 2027-01-28 23:00 BRT (NÃO conta!)
        db.execute(
            "INSERT INTO attempts (question_id, selected_letter, is_correct, answered_at, user_id) VALUES (2, 'A', 1, '2027-01-29T02:00:00+00:00', 'u1')"
        )
        db.commit()

        block = {"id": "cirurgia", "area": "Cirurgia", "ancora_areas": ["Cirurgia"]}
        bal = compute_7030_balance(db, "u1", date(2027, 2, 4), block)
        assert bal["total"] == 2
        assert bal["anchor"] == 1
        assert bal["other"] == 1
        assert bal["anchor_pct"] == 50.0
        assert bal["other_pct"] == 50.0


def test_7030_balance_multi_area_anchor_ferias(app):
    with app.app_context():
        db = get_db()
        # Q1 = Clínica Médica, Q2 = Pediatria (ambas âncoras nas férias)
        db.execute(
            "INSERT INTO attempts (question_id, selected_letter, is_correct, answered_at, user_id) VALUES (1, 'B', 1, '2026-12-10T15:00:00+00:00', 'u1')"
        )
        db.execute(
            "INSERT INTO attempts (question_id, selected_letter, is_correct, answered_at, user_id) VALUES (2, 'A', 1, '2026-12-11T15:00:00+00:00', 'u1')"
        )
        db.commit()

        ferias_block = {
            "id": "ferias",
            "area": "Revisão Geral",
            "ancora_areas": ["Clínica Médica", "Pediatria"],
        }
        bal = compute_7030_balance(db, "u1", date(2026, 12, 12), ferias_block)
        assert bal["total"] == 2
        assert bal["anchor"] == 2
        assert bal["other"] == 0
        assert bal["anchor_pct"] == 100.0
        assert bal["other_pct"] == 0.0
