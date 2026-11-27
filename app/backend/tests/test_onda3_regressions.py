"""Regressões funcionais, concorrência e performance da Onda 3."""
from datetime import UTC, datetime

from api.db import get_db


def test_migration_025_indexes_and_sync_questions_fts(app):
    from scripts.migrate_db import sync_questions_fts

    with app.app_context():
        db = get_db()
        tables = {
            r["name"]
            for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "test" not in tables

        attempt_indexes = {
            r["name"] for r in db.execute("PRAGMA index_list(attempts)").fetchall()
        }
        assert "idx_attempts_user_qid_latest_cov" in attempt_indexes
        assert "idx_attempts_user_question_latest" not in attempt_indexes
        assert "idx_attempts_user_answered_at" not in attempt_indexes

        img_indexes = {
            r["name"] for r in db.execute("PRAGMA index_list(question_images)").fetchall()
        }
        alt_indexes = {
            r["name"] for r in db.execute("PRAGMA index_list(alternatives)").fetchall()
        }
        idem_indexes = {
            r["name"] for r in db.execute("PRAGMA index_list(idempotency_keys)").fetchall()
        }
        assert "idx_question_images_qid_order" in img_indexes
        assert "idx_alternatives_qid_letter" in alt_indexes
        assert "idx_idempotency_status_created" in idem_indexes

        db.execute(
            "INSERT INTO questions_fts(rowid, stem, explanation) VALUES (999999, 'órfã', 'órfã')"
        )
        db.execute("DELETE FROM questions_fts WHERE rowid = 2")
        db.commit()

        deleted_orphans, inserted_missing = sync_questions_fts(db)
        assert deleted_orphans == 1
        assert inserted_missing >= 1
        assert db.execute("SELECT rowid FROM questions_fts WHERE rowid = 999999").fetchone() is None
        assert db.execute("SELECT rowid FROM questions_fts WHERE rowid = 2").fetchone() is not None


def test_curation_delete_cleans_fk_dependents(client, app):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT OR REPLACE INTO question_user_notes (user_id, question_id, highlights_json, note_text, updated_at)
            VALUES ('1', 1, '[]', 'nota', '2026-01-01T00:00:00Z')
            """
        )
        db.execute(
            """
            INSERT OR IGNORE INTO classification_runs (id, taxonomy_version, pipeline_version, input_hash, status, created_at)
            VALUES ('run-1', '1.0', '1.0', 'hash', 'completed', '2026-01-01T00:00:00Z')
            """
        )
        db.execute(
            """
            INSERT INTO classification_proposals
                (run_id, question_id, reviewer_role, decision, proposed_area, proposed_subtema, evidence, status, created_at)
            VALUES ('run-1', 1, 'classifier', 'classify', 'Clínica Médica', 'Cardiologia', 'evidência', 'proposed', '2026-01-01T00:00:00Z')
            """
        )
        prop_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.execute(
            """
            INSERT INTO classification_reviews
                (proposal_id, reviewer, decision, rationale, reviewed_at)
            VALUES (?, 'admin', 'accept', 'ok', '2026-01-01T00:00:00Z')
            """,
            (prop_id,),
        )
        db.commit()

    res = client.delete(
        "/api/questions/1", headers={"X-User-Email": "curator@example.com"}
    )
    assert res.status_code == 200
    assert res.get_json()["success"] is True

    with app.app_context():
        db = get_db()
        assert db.execute("SELECT 1 FROM questions WHERE id = 1").fetchone() is None
        assert (
            db.execute("SELECT 1 FROM question_user_notes WHERE question_id = 1").fetchone()
            is None
        )
        assert (
            db.execute("SELECT 1 FROM classification_reviews WHERE proposal_id = ?", (prop_id,)).fetchone()
            is None
        )
        assert (
            db.execute("SELECT 1 FROM classification_proposals WHERE question_id = 1").fetchone()
            is None
        )


def test_specialty_filter_returns_200_and_matches_subtema(client):
    res = client.get("/api/questions?specialty=Imunização%20(PNI)")
    assert res.status_code == 200
    items = res.get_json()
    assert len(items) == 1
    assert items[0]["id"] == 2


def test_batch_attempt_preserves_discursive_defaults_duvida_and_writes_snapshot(client, app):
    res = client.post(
        "/api/attempt/batch",
        json={
            "attempts": [
                {"question_id": 1, "selected_letter": "B", "time_spent_ms": 1200},
                {
                    "question_id": 3,
                    "selected_letter": "A",
                    "confidence": "defer",
                    "user_answer_text": "Deficiência de vitamina D",
                    "time_spent_ms": 2400,
                },
            ]
        },
    )
    assert res.status_code == 200
    payload = res.get_json()
    assert len(payload["results"]) == 2
    by_qid = {r["question_id"]: r for r in payload["results"]}
    assert by_qid[1]["is_correct"] is True
    assert by_qid[3]["is_correct"] is None

    with app.app_context():
        db = get_db()
        att1 = db.execute(
            "SELECT confidence, fsrs_reviewed_at FROM attempts WHERE question_id = 1 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert att1 is not None
        assert att1["confidence"] == "duvida"
        assert att1["fsrs_reviewed_at"] is not None

        att3 = db.execute(
            "SELECT confidence, is_correct FROM attempts WHERE question_id = 3 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert att3 is not None
        assert att3["confidence"] == "defer"
        assert att3["is_correct"] == 0
        assert (
            db.execute(
                "SELECT 1 FROM spaced_repetition WHERE question_id = 1 AND user_id = 1"
            ).fetchone()
            is not None
        )


def test_stats_preventiva_normalization_timeline_clamp_and_wilson_ci(client, app):
    from api.stats import calculate_wilson_ci

    low_90, high_90 = calculate_wilson_ci(10, 20, confidence=0.90)
    low_95, high_95 = calculate_wilson_ci(10, 20, confidence=0.95)
    assert (high_95 - low_95) > (high_90 - low_90)

    res_tl = client.get("/api/stats/timeline?days=999999")
    assert res_tl.status_code == 200

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO questions(id, area, subtema, stem, correct_letter, missing_alts, year, institution_code)
            VALUES
              (101, 'Medicina Preventiva', 'Bioestatística', 'Q101?', 'A', 0, 2024, 'USP-SP'),
              (102, 'Preventiva', 'Bioestatística', 'Q102?', 'A', 0, 2024, 'USP-SP')
            """
        )
        db.execute(
            "INSERT INTO alternatives(question_id, letter, text, is_correct) VALUES (101,'A','a',1),(102,'A','a',1)"
        )
        now_iso = datetime.now(UTC).isoformat()
        db.execute(
            "INSERT INTO attempts(question_id, selected_letter, is_correct, answered_at, confidence, user_id) VALUES (101,'A',1,?,'certeza',1),(102,'A',0,?,'certeza',1)",
            (now_iso, now_iso),
        )
        db.commit()

        from api.stats import (
            _get_cached_q_totals_map,
            _get_user_coverage_stats,
            _q_totals_cache,
        )

        _q_totals_cache.clear()
        q_map = _get_cached_q_totals_map(db)
        u_map = _get_user_coverage_stats(db, 1)
        assert q_map[("Preventiva", "Bioestatística")] == 2
        assert u_map[("Preventiva", "Bioestatística")]["attempts"] == 2
        assert u_map[("Preventiva", "Bioestatística")]["correct"] == 1

    res_bd_spec = client.get("/api/stats/breakdown?by=specialty")
    assert res_bd_spec.status_code == 200

    res_pred = client.get("/api/stats/predictive-score")
    assert res_pred.status_code == 200
    pred = res_pred.get_json()
    prev_pred = [a for a in pred["areas"] if a["area"] == "Preventiva"]
    assert len(prev_pred) == 1
    assert prev_pred[0]["attempts"] == 2
    assert pred["projected_score"] <= 100.0


def test_remediation_filters_by_area_aliases(app):
    from api.remediation import calculate_blindspots, generate_remediation_queue

    with app.app_context():
        db = get_db()
        now_iso = datetime.now(UTC).isoformat()
        db.execute(
            "INSERT INTO attempts(question_id, selected_letter, is_correct, answered_at, confidence, user_id) VALUES (1,'A',0,?,'certeza',1),(2,'B',0,?,'certeza',1)",
            (now_iso, now_iso),
        )
        db.commit()

        bs = calculate_blindspots(db, 1, area="Clínica Médica")
        assert bs["summary"]["unresolved_errors_count"] == 1
        assert len(bs["blindspots"]) == 1
        assert bs["blindspots"][0]["subtema"] == "Hipertensão Arterial Sistêmica"

        queue = generate_remediation_queue(db, 1, area="Clínica Médica", limit=5)
        assert all(item["area"] == "Clínica Médica" for item in queue)
        assert len(queue) >= 1


def test_planner_ics_long_hours_and_move_topic_destination_conflict(client, app):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO planner_config (user_id, start_date, exam_date, days_per_week, hours_per_day)
            VALUES ('1', '2026-02-01', '2026-03-01', 2, 8)
            """
        )
        db.execute(
            """
            INSERT INTO planner_schedule (user_id, mode, week, subtema, display_order, created_at)
            VALUES
              ('1', 'geral_standard', 1, 'Hipertensão Arterial Sistêmica', 0, '2026-01-01T00:00:00Z'),
              ('1', 'geral_standard', 2, 'Imunização (PNI)', 0, '2026-01-01T00:00:00Z')
            """
        )
        db.execute(
            """
            INSERT INTO planner_topic_progress (week, subtema, completed, completed_at, user_id)
            VALUES
              (1, 'Hipertensão Arterial Sistêmica', 1, '2026-01-01T00:00:00Z', '1'),
              (2, 'Hipertensão Arterial Sistêmica', 0, NULL, '1')
            """
        )
        db.commit()

    res_ics = client.get("/api/planner/export/ics")
    assert res_ics.status_code == 200
    assert b"BEGIN:VCALENDAR" in res_ics.data

    res_move = client.post(
        "/api/planner/move-topic",
        json={
            "subtema": "Hipertensão Arterial Sistêmica",
            "source_week": 1,
            "target_week": 2,
            "mode": "geral_standard",
        },
    )
    assert res_move.status_code == 200
    assert res_move.get_json()["success"] is True

    with app.app_context():
        db = get_db()
        row = db.execute(
            "SELECT completed FROM planner_topic_progress WHERE user_id = '1' AND week = 2 AND subtema = 'Hipertensão Arterial Sistêmica'"
        ).fetchone()
        assert row is not None
        assert row["completed"] == 1


def test_osce_atomic_append_conduct_verbalized_and_evaluation(app):
    from api.osce import (
        _append_osce_session_entries,
        dispatch_osce_speech,
        seed_osce_stations,
        start_osce_session,
    )
    from api.osce_evaluation import (
        build_medquest_remediation,
        generate_timeline_post_mortem,
    )

    with app.app_context():
        db = get_db()
        seed_osce_stations(db)
        st_row = db.execute("SELECT id FROM osce_stations LIMIT 1").fetchone()
        assert st_row is not None

        started = start_osce_session(db, int(st_row["id"]), "1")
        sid = started["session_id"]

        t1, a1 = _append_osce_session_entries(
            db,
            sid,
            "1",
            new_transcript=[{"sender": "candidato", "message": "Olá"}],
            new_actions=[{"action_type": "vitals", "elapsed_seconds": 5}],
            elapsed_seconds=5,
        )
        t2, a2 = _append_osce_session_entries(
            db,
            sid,
            "1",
            new_transcript=[{"sender": "examinador", "message": "PA 90x60"}],
            new_actions=[{"action_type": "physical_exam", "elapsed_seconds": 10}],
            elapsed_seconds=10,
        )
        assert len(t2) == len(t1) + 1
        assert len(a2) == len(a1) + 1

        disp = dispatch_osce_speech(
            db, sid, "1", "Minha conduta é furosemida EV agora.", elapsed_seconds=30
        )
        assert any(a.get("action_type") == "conduct_verbalized" for a in disp["actions_executed"])
        assert any(
            item.get("sender") == "candidato"
            and "Minha conduta" in (item.get("message") or "")
            for item in disp["transcript"]
        )

    timeline = generate_timeline_post_mortem(
        station_meta={"institution": "USP-SP", "title": "IAM"},
        transcript=[],
        actions=[
            {
                "action_type": "prescription",
                "elapsed_seconds": 120,
                "prescription_items": [
                    {"drug_name": "Morfina", "dose": "2", "unit": "mg"}
                ],
            },
            {
                "action_type": "procedure",
                "elapsed_seconds": 180,
                "anatomical_site": "toracocentese_5eic",
            },
        ],
        evaluated_items=[],
        elapsed_seconds=200,
    )
    event_descs = [ev["description"] for ev in timeline["events"]]
    event_titles = [ev["title"] for ev in timeline["events"]]
    assert any("Morfina 2 mg" in d for d in event_descs)
    assert any("Toracocentese 5Eic" in t for t in event_titles)

    rem = build_medquest_remediation(
        {"area": "Clínica Médica", "subtema": "SCA", "station_id": "osce-iam-1"}, []
    )
    assert rem["suggested_retry_station_id"] == "osce-iam-1"
