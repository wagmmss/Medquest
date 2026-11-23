"""Testes do conjunto de calibração (golden set) e do Juiz com IA do OSCE (Bloco 1)."""
from __future__ import annotations

import json
from pathlib import Path

from api import osce
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
