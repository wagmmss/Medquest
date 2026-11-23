"""Testes do conjunto de calibração (golden set) e do Juiz com IA do OSCE (Bloco 1)."""
from __future__ import annotations

import json
from pathlib import Path

from api import gemini_pool, osce, osce_judge
from api.db import get_db
from api.osce_data import CANONICAL_STATIONS

GOLDEN_PATH = Path(__file__).resolve().parent.parent / "data" / "osce" / "grading_golden.json"


def _load_golden() -> dict:
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        return json.load(f)


def test_grading_golden_schema_and_station_coverage():
    """Valida o schema do golden set, cobertura das 16 estações e 4 tipos de caso por estação."""
    golden = _load_golden()
    assert golden["schema_version"] == "1.0"
    assert "baseline_keyword_report" in golden
    stations = golden["stations"]
    assert len(stations) == len(CANONICAL_STATIONS) == 16

    expected_priority = [
        "USP-RP-2024-CM-CAD",
        "UNIFESP-2023-PREV-SPIKES",
        "USP-RP-2023-CG-FAST",
        "REVALIDA-2023-GO-PEP",
    ]
    assert [s["code"] for s in stations[:4]] == expected_priority

    canonical_map = {s["code"]: s for s in CANONICAL_STATIONS}
    for st in stations:
        code = st["code"]
        assert code in canonical_map
        canonical_items = canonical_map[code]["checklist_barema"]
        canonical_ids = [it["id"] for it in canonical_items]

        cases = st["cases"]
        assert len(cases) == 4
        assert {c["case_type"] for c in cases} == {
            "correct_paraphrased",
            "partial",
            "negated",
            "omitted",
        }
        for case in cases:
            assert case["case_id"] == f"{code}__{case['case_type']}"
            assert isinstance(case["conduct_notes"], str) and len(case["conduct_notes"].strip()) > 0
            exp_ids = [ei["id"] for ei in case["expected_items"]]
            assert exp_ids == canonical_ids
            for ei in case["expected_items"]:
                assert ei["expected_status"] in ("FULL", "PARTIAL", "NONE")
                assert ei["expected_score"] >= 0.0
                assert ei["tolerance"] >= 0.0


def test_baseline_keyword_scorer_recorded_on_golden_set():
    """Executa o avaliador por palavra-chave do Bloco 0 no golden set e confere o baseline registrado."""
    golden = _load_golden()
    canonical_map = {s["code"]: s for s in CANONICAL_STATIONS}

    total_cases = 0
    total_items = 0
    within_tol = 0
    by_type_tot = {"correct_paraphrased": 0, "partial": 0, "negated": 0, "omitted": 0}
    by_type_ok = {"correct_paraphrased": 0, "partial": 0, "negated": 0, "omitted": 0}
    negated_fps = 0

    for st in golden["stations"]:
        items = canonical_map[st["code"]]["checklist_barema"]
        for case in st["cases"]:
            total_cases += 1
            ctype = case["case_type"]
            transcript = [{"sender": "candidato", "message": case["conduct_notes"], "elapsed_seconds": 120}]
            ev = osce.collect_candidate_evidence(transcript, [])
            scored_map = {s["id"]: s for s in osce.score_checklist_items(items, ev)}

            for exp in case["expected_items"]:
                total_items += 1
                by_type_tot[ctype] += 1
                actual = float(scored_map[exp["id"]]["awarded_score"])
                if abs(actual - exp["expected_score"]) <= exp["tolerance"]:
                    within_tol += 1
                    by_type_ok[ctype] += 1
                if ctype == "negated" and actual > 0:
                    negated_fps += 1

    recorded = golden["baseline_keyword_report"]
    assert recorded["total_cases"] == total_cases == 64
    assert recorded["total_items"] == total_items
    assert recorded["items_within_tolerance"] == within_tol
    assert recorded["overall_accuracy_pct"] == round((within_tol / total_items) * 100, 1)
    assert recorded["negated_false_positives"] == negated_fps
    assert recorded["accuracy_by_case_type"]["correct_paraphrased"] < 70.0


def test_judge_discards_non_existent_evidence_quote(monkeypatch):
    """Citação inventada que não existe literalmente no texto do candidato deve ser descartada e zerar o item."""
    station = next(s for s in CANONICAL_STATIONS if s["code"] == "USP-RP-2024-CM-CAD")
    transcript = [
        {"sender": "candidato", "message": "Paciente com cetoacidose diabética.", "elapsed_seconds": 60}
    ]

    def fake_llm_hallucinating(prompt, **kwargs):
        return {
            "text": json.dumps({
                "items": [
                    {
                        "id": "item_2",
                        "status": "FULL",
                        "evidence_quote": "Paciente com cetoacidose diabética.",
                        "rationale": "Citação literal válida.",
                    },
                    {
                        "id": "item_3",
                        "status": "FULL",
                        "evidence_quote": "Prescrevo soro fisiológico 1000 ml na primeira hora",
                        "rationale": "Alucinação: o candidato nunca disse isso.",
                    },
                ],
                "critical_errors_triggered": [],
            }),
            "source": "mock_ai",
        }

    monkeypatch.setattr(gemini_pool, "generate_content_with_fallback", fake_llm_hallucinating)

    res = osce_judge.evaluate_session_with_judge(
        station_meta=station,
        transcript=transcript,
        actions=[],
        checklist_items=station["checklist_barema"],
        critical_errors=station.get("critical_errors", []),
    )
    assert res["graded_with_ai"] is True
    by_id = {it["id"]: it for it in res["evaluated_items"]}
    assert by_id["item_2"]["status"] == "FULL"
    assert by_id["item_2"]["awarded_score"] == 1.5
    assert by_id["item_3"]["status"] == "NONE"
    assert by_id["item_3"]["awarded_score"] == 0.0
    assert by_id["item_3"]["evidence_quote"] == ""


def test_judge_falls_back_to_block0_when_llm_fails(monkeypatch):
    """Quando o LLM falha, a avaliação cai no motor determinístico do Bloco 0 e sinaliza Corrigido sem IA."""
    station = next(s for s in CANONICAL_STATIONS if s["code"] == "USP-RP-2024-CM-CAD")
    transcript = [
        {
            "sender": "candidato",
            "message": "Diagnostico cetoacidose diabética com ânion gap elevado e prescrevo soro fisiológico 0,9% 1000 ml na primeira hora.",
            "elapsed_seconds": 90,
        }
    ]

    def broken_llm(*args, **kwargs):
        raise RuntimeError("Timeout simulado do provedor Gemini")

    monkeypatch.setattr(gemini_pool, "generate_content_with_fallback", broken_llm)

    res = osce_judge.evaluate_session_with_judge(
        station_meta=station,
        transcript=transcript,
        actions=[],
        checklist_items=station["checklist_barema"],
        critical_errors=station.get("critical_errors", []),
    )
    assert res["graded_with_ai"] is False
    assert res["grading_mode"] == "deterministic_fallback"
    assert res["grading_notice"] == "Corrigido sem IA"
    by_id = {it["id"]: it for it in res["evaluated_items"]}
    assert by_id["item_2"]["awarded_score"] > 0
    assert by_id["item_3"]["awarded_score"] > 0


def test_judge_golden_set_accuracy_and_zero_negated_false_positives(monkeypatch):
    """No golden set completo (64 casos), o juiz deve atingir >= 90% dentro da tolerância e 0 FPs em negadas."""
    golden = _load_golden()
    canonical_map = {s["code"]: s for s in CANONICAL_STATIONS}

    def simulated_judge(prompt, **kwargs):
        payload = json.loads(prompt)
        text = osce_judge.simulate_llm_judge_json(
            station_meta=payload["station"],
            candidate_log=payload["candidate_timeline"],
            checklist_items=payload["checklist_items"],
            critical_errors=payload["critical_errors"],
        )
        return {"text": text, "source": "mock_osce_judge"}

    monkeypatch.setattr(gemini_pool, "generate_content_with_fallback", simulated_judge)

    total_items = 0
    within_tol = 0
    negated_fps = 0

    for st in golden["stations"]:
        station = canonical_map[st["code"]]
        for case in st["cases"]:
            transcript = [{"sender": "candidato", "message": case["conduct_notes"], "elapsed_seconds": 120}]
            res = osce_judge.evaluate_session_with_judge(
                station_meta=station,
                transcript=transcript,
                actions=[],
                checklist_items=station["checklist_barema"],
                critical_errors=station.get("critical_errors", []),
            )
            scored_map = {it["id"]: it for it in res["evaluated_items"]}
            for exp in case["expected_items"]:
                total_items += 1
                actual = float(scored_map[exp["id"]]["awarded_score"])
                if abs(actual - exp["expected_score"]) <= exp["tolerance"]:
                    within_tol += 1
                if case["case_type"] == "negated" and actual > 0:
                    negated_fps += 1

    accuracy_pct = (within_tol / total_items) * 100.0
    assert accuracy_pct >= 90.0, f"Acurácia do juiz foi {accuracy_pct:.1f}% (< 90.0%)"
    assert negated_fps == 0, f"Detectados {negated_fps} falsos positivos em respostas negadas"


def test_finish_osce_session_uses_judge_and_populates_evidence_quotes(app):
    """finish_osce_session deve usar o juiz (simulado no conftest), gravar evidence_quote literal e propagar no report."""
    with app.app_context():
        db = get_db()
        osce.seed_osce_stations(db)
        st = db.execute("SELECT id FROM osce_stations WHERE code = 'USP-RP-2024-CM-CAD'").fetchone()
        assert st is not None
        user_id = "judge_integration_user"
        sess = osce.start_osce_session(db, st["id"], user_id, mode="blind")
        session_id = sess["session_id"]

        conduct = (
            "Expansão volêmica inicial com soro fisiológico 0,9% 1000 ml na primeira hora em acesso venoso calibroso. "
            "Avalio o potássio sérico antes da insulina: como está em 3,1 mEq/L, abaixo de 3,3, seguro a insulinoterapia "
            "e inicio reposição de KCl endovenoso antes de prescrever insulina regular em bomba de infusão."
        )
        res = osce.finish_osce_session(db, session_id, user_id, conduct_notes=conduct)

        assert res["graded_with_ai"] is True
        assert res["grading_mode"] == "ai_judge"
        assert res["grading_notice"] == "Corrigido com IA"
        assert res["preceptor_feedback"]["graded_with_ai"] is True

        scored_with_quote = [
            it for it in res["evaluated_items"]
            if it["awarded_score"] > 0 and it.get("evidence_quote")
        ]
        assert len(scored_with_quote) >= 2
        for it in scored_with_quote:
            assert it["evidence_quote"].lower() in f"conduta e prescrição verbalizada: {conduct}".lower()

        report = osce.get_osce_session_report(db, session_id, user_id)
        assert report is not None
        assert report["graded_with_ai"] is True
        assert report["grading_notice"] == "Corrigido com IA"
        assert any(it.get("evidence_quote") for it in report["evaluated_items"])


def test_finish_osce_session_shows_corrigido_sem_ia_on_judge_failure(app, monkeypatch):
    """Se o juiz falhar dentro de finish_osce_session, aplica fallback do Bloco 0 e sinaliza 'Corrigido sem IA'."""
    def boom(*args, **kwargs):
        raise RuntimeError("Falha simulada do Gemini no finish_osce_session")

    monkeypatch.setattr(gemini_pool, "generate_content_with_fallback", boom)

    with app.app_context():
        db = get_db()
        osce.seed_osce_stations(db)
        st = db.execute("SELECT id FROM osce_stations WHERE code = 'USP-RP-2024-CM-CAD'").fetchone()
        assert st is not None
        user_id = "judge_fallback_user"
        sess = osce.start_osce_session(db, st["id"], user_id, mode="blind")
        session_id = sess["session_id"]

        res = osce.finish_osce_session(
            db,
            session_id,
            user_id,
            conduct_notes="Inicio SF 0,9% 1000ml na 1a hora e reposição de potássio com KCl antes da insulina.",
        )

        assert res["graded_with_ai"] is False
        assert res["grading_mode"] == "deterministic_fallback"
        assert res["grading_notice"] == "Corrigido sem IA"
        assert res["preceptor_feedback"]["grading_notice"] == "Corrigido sem IA"
        assert res["raw_score"] > 0

        report = osce.get_osce_session_report(db, session_id, user_id)
        assert report is not None
        assert report["graded_with_ai"] is False
        assert report["grading_notice"] == "Corrigido sem IA"
