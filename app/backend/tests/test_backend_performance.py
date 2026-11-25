"""Testes de regressão e performance para índices, caches, consolidação SQL e Preceptor IA."""
import sqlite3
from datetime import datetime, timezone
from unittest.mock import patch

from api.adaptive import _profile_cache, build_learning_profile, rank_adaptive_candidates
from api.ai import ask_preceptor_ai
from api.cache import SimpleTTLCache
from api.db import get_db
from api.filters import get_user_target_institutions, target_institutions_cache
from api.knowledge import (
    _knowledge_cache,
    _sanitize_fts_query,
    init_knowledge_schema,
    retrieve_medical_context,
)
from api.questions import invalidate_user_caches
from api.stats import _fetch_attempt_rollup, _get_overview_metrics, overview_cache


def test_migration_019_performance_indexes_created(app):
    """Garante que a migration 019_performance_indexes.sql aplicou os índices compostos."""
    with app.app_context():
        db = get_db()
        rows = db.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
        index_names = {r["name"] for r in rows}

        expected_indexes = {
            "idx_attempts_question_letter",
            "idx_attempts_user_answered",
            "idx_attempts_user_qid_latest_cov",
            "idx_attempts_user_correct_qid",
            "idx_questions_active_area_subtema",
            "idx_questions_active_inst_year",
            "idx_alternatives_qid_correct_letter",
        }
        assert expected_indexes.issubset(index_names)


def test_simple_ttl_cache_clear_user_handles_int_and_str_ids():
    """Garante isolamento por user_id e invalidação mesmo quando int e str são misturados."""
    cache = SimpleTTLCache(60, max_size=10)
    cache.set((1, "overview", 0), {"ok": True})
    cache.set(("1", "timeline", None), [1, 2, 3])
    cache.set(("2", "overview", 0), {"other": True})

    # Limpar com string "1" deve invalidar tanto (1, ...) quanto ("1", ...)
    cache.clear_user("1")
    assert cache.get((1, "overview", 0)) is None
    assert cache.get(("1", "timeline", None)) is None
    assert cache.get(("2", "overview", 0)) == {"other": True}


def test_invalidate_user_caches_clears_all_per_user_stores(app):
    """Verifica que invalidate_user_caches limpa overview, profile e target_institutions."""
    with app.app_context():
        db = get_db()
        db.execute(
            """INSERT OR REPLACE INTO planner_config
               (user_id, exam_date, start_date, days_per_week, questions_per_day, hours_per_day, target_institution)
               VALUES ('1', '2026-11-15', '2026-03-01', 6, 30, 4, 'USP-SP')"""
        )
        db.commit()

        insts = get_user_target_institutions(db, "1")
        assert "USP-SP" in insts
        profile = build_learning_profile(db, "1")
        assert profile is not None
        overview_cache.set(("1", "dashboard_summary", 0), {"cached": True})

        invalidate_user_caches(1)  # Passando int para validar normalização int/str
        assert overview_cache.get(("1", "dashboard_summary", 0)) is None
        assert _profile_cache.get(("1", None, 15)) is None
        assert _profile_cache.get(("1", "__signals__")) is None

        # Atualiza no banco e garante que target_institutions_cache foi invalidado
        db.execute(
            "UPDATE planner_config SET target_institution = 'UNICAMP' WHERE user_id = '1'"
        )
        db.commit()
        updated_insts = get_user_target_institutions(db, "1")
        assert "UNICAMP" in updated_insts
        assert "USP-SP" not in updated_insts


def test_rollup_consolidates_assisted_correct_without_extra_query(app):
    """Garante que _fetch_attempt_rollup já retorna assisted_correct consolidado."""
    with app.app_context():
        db = get_db()
        now_utc = datetime.now(timezone.utc)
        now_iso = now_utc.isoformat()
        db.execute(
            """INSERT INTO attempts (question_id, selected_letter, is_correct, answered_at, confidence, user_id, assisted)
               VALUES (1, 'B', 1, ?, 'certeza', '1', 1),
                      (2, 'A', 1, ?, 'certeza', '1', 0)""",
            (now_iso, now_iso),
        )
        db.commit()

        rollup = _fetch_attempt_rollup(db, "1", now_utc)
        assert rollup["total_attempts"] == 2
        assert rollup["correct"] == 2
        assert rollup["assisted_correct"] == 1

        metrics = _get_overview_metrics(db, "1", now_utc, rollup=rollup)
        assert metrics["assisted_correct_count"] == 1
        assert metrics["unassisted_correct_count"] == 1


def test_rank_adaptive_candidates_avoids_n_plus_1_on_external_twin(app):
    """Garante que rank_adaptive_candidates reutiliza db_twin em memória sem query N+1."""
    with app.app_context():
        db = get_db()
        past_iso = "2020-01-01T00:00:00+00:00"
        # Questão 4 do mesmo subtema de Q1 mas de outra banca
        db.execute(
            """INSERT INTO questions(id, area, subtema, stem, correct_letter, missing_alts, year, institution_code, institution_label)
               VALUES (4, 'Clínica Médica', 'Hipertensão Arterial Sistêmica', 'Q4 Twin?', 'A', 0, 2025, 'UNIFESP', 'UNIFESP')"""
        )
        db.execute(
            """INSERT INTO attempts(question_id, selected_letter, is_correct, answered_at, confidence, user_id)
               VALUES (1, 'B', 1, ?, 'certeza', '1')""",
            (past_iso,),
        )
        db.execute(
            """INSERT INTO spaced_repetition(question_id, next_review_date, fsrs_card, user_id)
               VALUES (1, ?, '{}', '1')""",
            (past_iso,),
        )
        db.commit()

        # Filtra apenas USP-SP na fila principal para forçar busca de twin externo (Q4 UNIFESP)
        ranked = rank_adaptive_candidates(
            db,
            user_id="1",
            where="q.missing_alts = 0 AND q.institution_code = ?",
            params=["USP-SP"],
            limit=10,
        )
        twin_items = [item for item in ranked if item.get("is_twin")]
        assert len(twin_items) == 1
        assert twin_items[0]["id"] == 4
        assert twin_items[0]["twin_for_question_id"] == 1


def test_ask_preceptor_dica_and_foco_skip_rag_and_jurisprudence(app):
    """Garante que os modos /dica e /foco não executam FTS5 de RAG ou jurisprudência."""
    with app.app_context():
        db = get_db()
        with patch("api.ai.retrieve_medical_context") as mock_rag, patch(
            "api.ai.retrieve_jurisprudence_context"
        ) as mock_juris:
            res_dica = ask_preceptor_ai(
                stem="Paciente com dor torácica.",
                alternatives=[{"letter": "A", "text": "IAM"}],
                correct_letter="A",
                correct_text="IAM",
                user_question="/dica",
                db=db,
                user_id="1",
                question_id=1,
            )
            assert res_dica["grounding_sources"] == []
            assert res_dica["jurisprudence_sources"] == []
            mock_rag.assert_not_called()
            mock_juris.assert_not_called()

            res_foco = ask_preceptor_ai(
                stem="Paciente com dor torácica.",
                alternatives=[{"letter": "A", "text": "IAM"}],
                correct_letter="A",
                correct_text="IAM",
                user_question="/foco",
                db=db,
                user_id="1",
                question_id=1,
            )
            assert res_foco["grounding_sources"] == []
            assert res_foco["jurisprudence_sources"] == []
            assert res_foco["tool_call"]["name"] == "get_student_weak_topics"
            mock_rag.assert_not_called()
            mock_juris.assert_not_called()


def test_knowledge_sanitize_strips_slash_commands_and_caches_results(tmp_path):
    """Garante que comandos /conduta não poluem FTS5 e que retrieve_medical_context usa cache."""
    q = _sanitize_fts_query("/conduta choque séptico")
    assert "conduta" not in q
    assert "choque" in q

    db_file = str(tmp_path / "knowledge_perf.db")
    conn = sqlite3.connect(db_file)
    init_knowledge_schema(conn)
    with conn:
        conn.execute(
            """INSERT INTO knowledge_chunks (source_file, source_type, specialty, topic, subtopic, title, content, word_count)
               VALUES ('Diretriz.pdf', 'ficha_resumo', 'Clínica Médica', 'Sepse', 'Manejo', 'Choque Séptico', 'Noradrenalina 1a linha.', 4)"""
        )
    conn.close()
    _knowledge_cache.clear()

    r1 = retrieve_medical_context(
        area="Clínica Médica",
        subtema="Sepse",
        stem="Paciente com choque séptico",
        user_question="/conduta",
        db_path=db_file,
    )
    assert len(r1) == 1

    with patch("api.knowledge.get_knowledge_connection") as mock_conn:
        r2 = retrieve_medical_context(
            area="Clínica Médica",
            subtema="Sepse",
            stem="Paciente com choque séptico",
            user_question="/conduta",
            db_path=db_file,
        )
        assert len(r2) == 1
        mock_conn.assert_not_called()


class _QuerySpyDB:
    """Wrapper leve em torno de sqlite3.Connection que registra SQLs executadas."""

    def __init__(self, inner):
        self._inner = inner
        self.executed_sqls: list[str] = []

    def execute(self, sql, params=()):
        self.executed_sqls.append(sql)
        return self._inner.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def test_question_catalog_cache_avoids_repeated_questions_scans(app, monkeypatch):
    """Garante que /api/meta, /api/questions/count, domain-summary e adaptive evitam rescan de questions."""
    from werkzeug.datastructures import MultiDict

    from api.adaptive import _profile_cache, get_adaptive_signals_by_topic
    from api.questions import count_cache, invalidate_global_question_caches, meta_cache
    from api.services.focus_radar import build_focus_radar
    from api.services.questions_service import compute_meta_from_catalog, count_questions_from_catalog
    from api.stats import _fetch_all_priority_topics, _get_domain_summary_data, overview_cache

    monkeypatch.setattr("api.services.questions_service.catalog_cache_enabled", lambda: True)
    monkeypatch.setattr("api.stats.catalog_cache_enabled", lambda: True)
    monkeypatch.setattr("api.adaptive.catalog_cache_enabled", lambda: True)
    monkeypatch.setattr("api.services.focus_radar.catalog_cache_enabled", lambda: True)

    with app.app_context():
        db = get_db()
        spy = _QuerySpyDB(db)

        # 1a chamada aquece os caches globais de catalogo
        meta_u1 = compute_meta_from_catalog(spy, "user-1", MultiDict(), set())
        assert meta_u1["total_questions"] == 3
        domain_u1 = _get_domain_summary_data(spy, "user-1")
        assert domain_u1["total_subtemas"] == 3
        signals_u1 = get_adaptive_signals_by_topic(spy, "user-1")
        assert len(signals_u1) == 3
        radar_u1 = build_focus_radar(spy, "user-1")
        assert radar_u1["summary"]["total_focuses"] == 3
        prio_u1 = _fetch_all_priority_topics(spy, "user-1", None, "")
        assert len(prio_u1) >= 2

        # Limpa caches por usuario e verifica que outro usuario/filtro NAO reescaneia `questions` sozinha
        meta_cache.clear()
        count_cache.clear()
        overview_cache.clear()
        _profile_cache.clear()
        spy.executed_sqls.clear()

        args_unanswered = MultiDict([("status", "unanswered"), ("year", "2025")])
        meta_u2 = compute_meta_from_catalog(spy, "user-2", args_unanswered, set())
        assert meta_u2["total_questions"] == 2
        assert count_questions_from_catalog(spy, "user-2", args_unanswered) == 2
        _get_domain_summary_data(spy, "user-2")
        get_adaptive_signals_by_topic(spy, "user-2")
        build_focus_radar(spy, "user-2")
        _fetch_all_priority_topics(spy, "user-2", None, "")

        full_question_scans = [
            sql for sql in spy.executed_sqls
            if "FROM questions" in sql and "JOIN questions" not in sql
        ]
        assert full_question_scans == []

        # Invalida caches globais (simulando curadoria) e confirma que nova questao aparece
        db.execute(
            """INSERT INTO questions(id, area, subtema, stem, correct_letter, missing_alts, year, institution_code, institution_label)
               VALUES (99, 'Cirurgia', 'Apendicite', 'Nova Q?', 'A', 0, 2024, 'ENARE', 'ENARE')"""
        )
        db.commit()
        invalidate_global_question_caches()

        meta_after = compute_meta_from_catalog(spy, "user-2", MultiDict(), set())
        assert meta_after["total_questions"] == 4


def test_catalog_meta_and_count_match_sql_across_filters(app):
    """Confirma paridade exata entre o motor em memoria e question_filter_clauses."""
    from werkzeug.datastructures import MultiDict

    from api.filters import question_filter_clauses
    from api.services.questions_service import compute_meta_from_catalog, count_questions_from_catalog

    with app.app_context():
        db = get_db()
        db.execute(
            """INSERT INTO questions(id, area, subtema, topic, stem, correct_letter, missing_alts, year, institution_code, institution_label)
               VALUES (4, 'Medicina Preventiva e Social', 'Vigilância', 'Notificação', 'Q4?', 'ANULADA', 0, 2024, 'USP', 'USP')"""
        )
        db.execute("INSERT INTO question_images(id, question_id, file_path, order_index) VALUES (1, 2, 'img.png', 0)")
        db.execute(
            """INSERT INTO attempts(question_id, selected_letter, is_correct, answered_at, user_id)
               VALUES (1, 'A', 0, '2026-01-01T00:00:00Z', 'u-parity'),
                      (2, 'A', 1, '2026-01-01T00:00:00Z', 'u-parity')"""
        )
        db.execute("INSERT INTO favorites(question_id, user_id) VALUES (2, 'u-parity')")
        db.execute(
            "INSERT INTO spaced_repetition(question_id, next_review_date, user_id) VALUES (1, '2020-01-01T00:00:00Z', 'u-parity')"
        )
        db.commit()

        from flask import g

        filter_cases = [
            MultiDict(),
            MultiDict([("status", "unanswered")]),
            MultiDict([("status", "wrong")]),
            MultiDict([("status", "wrong,srs_due")]),
            MultiDict([("status", "favorite")]),
            MultiDict([("favorite", "1")]),
            MultiDict([("institution", "USP-SP"), ("year", "2025,2024")]),
            MultiDict([("area", "Medicina Preventiva")]),
            MultiDict([("has_images", "1")]),
            MultiDict([("exclude_annulled", "1")]),
            MultiDict([("subtema", "Imunização (PNI)")]),
        ]

        g.user_id = "u-parity"
        for args in filter_cases:
            clauses, params = question_filter_clauses(args)
            where = " AND ".join(clauses)
            sql_total = db.execute(f"SELECT COUNT(*) AS n FROM questions q WHERE {where}", params).fetchone()["n"]
            sql_answered = db.execute(
                f"SELECT COUNT(DISTINCT q.id) AS n FROM questions q WHERE {where} AND q.id IN (SELECT question_id FROM attempts WHERE user_id = ?)",
                [*params, "u-parity"],
            ).fetchone()["n"]

            cat_meta = compute_meta_from_catalog(db, "u-parity", args, set())
            cat_count = count_questions_from_catalog(db, "u-parity", args)

            assert cat_meta["total_questions"] == sql_total, f"Mismatch total for {args}"
            assert cat_meta["answered_questions"] == sql_answered, f"Mismatch answered for {args}"
            assert cat_count == sql_total, f"Mismatch count for {args}"
