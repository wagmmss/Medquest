"""Testes da meta diária efetiva única (adaptive.py + stats_rollup.py) e performance de resolve_range."""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from api.adaptive import build_learning_profile
from api.db import get_db
from api.services.six_year_routine import resolve_range
from api.services.stats_rollup import _get_streak_and_target_info


def test_effective_goal_routine_off_uses_configured_questions_per_day(app):
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO planner_config (user_id, questions_per_day, hours_per_day, updated_at) VALUES (?, ?, ?, ?)",
            ("u1", 42, 4, "2027-02-04T12:00:00+00:00"),
        )
        db.commit()

        now = datetime(2027, 2, 4, 15, 0, tzinfo=UTC)
        profile = build_learning_profile(db, "u1", now=now)
        streak_info = _get_streak_and_target_info(db, "u1", now, -180)

        assert profile["goal"]["questions_today"] == 42
        assert profile["goal"]["reviews_optional_today"] == 0
        assert profile["goal"]["routine_context"] == {"enabled": False}
        assert streak_info["daily_target"] == 42
        assert streak_info["daily_routine"] == {"enabled": False}
        assert streak_info["reviews_optional_today"] == 0


def test_effective_goal_routine_on_pos_plantao_zeroes_goal_and_marks_reviews_optional(app):
    with app.app_context():
        db = get_db()
        now = datetime(2027, 2, 4, 15, 0, tzinfo=UTC)  # 2027-02-04 12:00 BRT
        db.execute(
            """
            INSERT INTO user_six_year_plan (user_id, routine_mode_enabled, updated_at)
            VALUES ('u1', 1, ?)
            """,
            (now.isoformat(),),
        )
        # Plantão noturno ontem (2027-02-03) -> hoje (2027-02-04) é pos_plantao
        db.execute(
            """
            INSERT INTO user_shifts (user_id, date_iso, kind, note, updated_at)
            VALUES ('u1', '2027-02-03', 'plantao_noturno', '', ?)
            """,
            (now.isoformat(),),
        )
        # Duas questões vencidas em spaced_repetition
        due_iso = (now - timedelta(days=1)).isoformat()
        db.execute(
            """
            INSERT INTO spaced_repetition (user_id, question_id, next_review_date, fsrs_card)
            VALUES ('u1', 1, ?, '{}'), ('u1', 2, ?, '{}')
            """,
            (due_iso, due_iso),
        )
        db.commit()

        profile = build_learning_profile(db, "u1", now=now)
        streak_info = _get_streak_and_target_info(db, "u1", now, -180)

        assert profile["goal"]["questions_today"] == 0
        assert profile["goal"]["reviews_to_do_today"] == 0
        assert profile["goal"]["reviews_optional_today"] == 2
        assert profile["goal"]["backlog_pending"] == 0
        assert profile["goal"]["routine_context"]["enabled"] is True
        assert profile["goal"]["routine_context"]["day_mode"] == "pos_plantao"

        assert streak_info["daily_target"] == 0
        assert streak_info["reviews_optional_today"] == 2
        assert streak_info["daily_routine"]["day_mode"] == "pos_plantao"


def test_effective_goal_routine_on_folga_sprint_equals_85_in_both(app):
    with app.app_context():
        db = get_db()
        # 2027-02-06 é sábado (folga) na semana 2027-02-01
        now = datetime(2027, 2, 6, 15, 0, tzinfo=UTC)
        db.execute(
            """
            INSERT INTO user_six_year_plan (user_id, routine_mode_enabled, updated_at)
            VALUES ('u1', 1, ?)
            """,
            (now.isoformat(),),
        )
        db.execute(
            """
            INSERT INTO user_week_marcha (user_id, week_iso, marcha_id, updated_at)
            VALUES ('u1', '2027-02-01', '4_sprint', ?)
            """,
            (now.isoformat(),),
        )
        db.commit()

        profile = build_learning_profile(db, "u1", now=now)
        streak_info = _get_streak_and_target_info(db, "u1", now, -180)

        assert profile["goal"]["questions_today"] == 85
        assert streak_info["daily_target"] == 85
        assert profile["goal"]["routine_context"]["marcha_id"] == "4_sprint"
        assert streak_info["daily_routine"]["marcha_id"] == "4_sprint"


def test_resolve_range_366_days_uses_at_most_4_queries(app):
    with app.app_context():
        db = get_db()
        queries: list[str] = []

        class CountingDB:
            def execute(self, sql, params=()):
                queries.append(sql)
                return db.execute(sql, params)

        end = date(2027, 11, 30)
        start = end - timedelta(days=365)
        days = resolve_range(CountingDB(), "u1", start, end)
        assert len(days) == 366
        assert len(queries) <= 4
