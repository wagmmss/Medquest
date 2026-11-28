"""Testes de streak protegido por plantão/pós-plantão (regressivos A1, A2 e C1)."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from api.db import get_db
from api.services.stats_rollup import _get_streak_and_target_info, responsible_streak


def test_a1_pos_plantao_yesterday_preserves_streak_today_and_tomorrow():
    # Estudou seg..qua; quinta teve pós-plantão (sem estudar); sexta estudou.
    today = date(2027, 2, 5)  # sexta
    studied = {
        "2027-02-01",
        "2027-02-02",
        "2027-02-03",
        "2027-02-05",
    }
    protected = {"2027-02-04"}  # quinta protegida
    res_today = responsible_streak(studied, today, days_per_week=6, protected_dates=protected)
    assert res_today["days"] == 4
    assert res_today["policy"] == "rest_days_and_protected_shifts_preserve_continuity"

    # No dia seguinte (sábado), mesmo com domingo/outro dia de folga no orçamento, o pós-plantão não consumiu rest_budget
    tomorrow = date(2027, 2, 6)
    res_tomorrow = responsible_streak(
        studied | {"2027-02-06"},
        tomorrow,
        days_per_week=6,
        protected_dates=protected,
    )
    assert res_tomorrow["days"] == 5


def test_a2_new_shift_does_not_retroactively_protect_past_days_without_shift(app):
    with app.app_context():
        db = get_db()
        # Usuário estudou 01/02 e 05/02 (gap de 3 dias: 02, 03, 04 sem plantão).
        # Cadastrou plantão somente para 06/02 (hoje/futuro) — não pode proteger 02..04!
        now = datetime(2027, 2, 5, 15, 0, tzinfo=UTC)
        db.execute(
            "INSERT INTO user_six_year_plan (user_id, routine_mode_enabled, updated_at) VALUES ('u1', 1, ?)",
            (now.isoformat(),),
        )
        db.execute(
            "INSERT INTO user_shifts (user_id, date_iso, kind, note, updated_at) VALUES ('u1', '2027-02-06', 'plantao_noturno', '', ?)",
            (now.isoformat(),),
        )
        db.execute(
            "INSERT INTO attempts (question_id, selected_letter, is_correct, answered_at, user_id) VALUES (1, 'B', 1, '2027-02-01T15:00:00+00:00', 'u1')"
        )
        db.execute(
            "INSERT INTO attempts (question_id, selected_letter, is_correct, answered_at, user_id) VALUES (2, 'A', 1, '2027-02-05T15:00:00+00:00', 'u1')"
        )
        db.commit()

        info = _get_streak_and_target_info(db, "u1", now, -180)
        assert info["streak_days"] == 1


def test_c1_studying_on_protected_day_does_not_double_count_rest_days_available():
    # Semana com 6 dias/semana (rest_budget = 1).
    # Últimos 7 dias: estudou em 5 dias (incluindo 2027-02-04 que TAMBÉM é protegido!),
    # faltou em 2 dias não protegidos (2027-02-01 e 2027-02-02) -> rests_used_last_7 = 2 -> available = 0.
    # Se houvesse bug de dupla contagem (7 - active - protected = 7 - 5 - 1 = 1), devolveria 0 mas em
    # outro cenário (5 ativos + 1 protegido que é um dos ativos + 1 falta não protegida):
    # rests_used_last_7 = |{falta}| = 1 -> rest_days_available = 0 (enquanto a fórmula com bug daria 1!).
    today = date(2027, 2, 7)
    last_7 = [today - timedelta(days=i) for i in range(7)]
    # Estudou em 6 dias, faltou apenas em last_7[5] (não protegido).
    # E last_7[2] é simultaneamente active E protected!
    studied = {str(d) for idx, d in enumerate(last_7) if idx != 5}
    protected = {str(last_7[2])}

    res = responsible_streak(studied, today, days_per_week=6, protected_dates=protected)
    assert res["days"] == 6
    assert res["active_days_last_7"] == 6
    # A falta em last_7[5] consumiu o único rest_budget (1 - 1 = 0).
    assert res["rest_days_available"] == 0


def test_routine_off_keeps_legacy_streak_behavior(app):
    with app.app_context():
        db = get_db()
        now = datetime(2027, 2, 5, 15, 0, tzinfo=UTC)
        # Mesmo com plantão gravado, routine_mode_enabled=0 não protege o streak
        db.execute(
            "INSERT INTO user_shifts (user_id, date_iso, kind, note, updated_at) VALUES ('u1', '2027-02-03', 'plantao_noturno', '', ?)",
            (now.isoformat(),),
        )
        db.execute(
            "INSERT INTO attempts (question_id, selected_letter, is_correct, answered_at, user_id) VALUES (1, 'B', 1, '2027-02-02T15:00:00+00:00', 'u1')"
        )
        db.execute(
            "INSERT INTO attempts (question_id, selected_letter, is_correct, answered_at, user_id) VALUES (2, 'A', 1, '2027-02-05T15:00:00+00:00', 'u1')"
        )
        db.commit()

        info = _get_streak_and_target_info(db, "u1", now, -180)
        assert info["streak"]["policy"] == "rest_days_preserve_continuity"
        assert info["streak_days"] == 1
