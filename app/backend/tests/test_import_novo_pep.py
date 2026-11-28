"""Testes do importador CLI scripts/import_novo_pep.py (fixture sintética sem dados pessoais)."""
from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

from api.db import get_db

_SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "import_novo_pep.py"
_SPEC = importlib.util.spec_from_file_location("import_novo_pep", _SCRIPT_PATH)
assert _SPEC and _SPEC.loader
import_novo_pep = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = import_novo_pep
_SPEC.loader.exec_module(import_novo_pep)


def _synthetic_backup_v2() -> dict:
    return {
        "version": 2,
        "exportedAt": "2027-02-01T12:00:00Z",
        "clinicalTheme": "light",
        "favoriteIds": ["proto_sepse"],
        "habChecklists": {"logbook": ["ignored"]},
        "central6AnoState": {
            "curriculumEnamedConcept": 4,
            "marchaId": "2_pesada",
            "weeklySchedule": {"ter": "plantao_noturno"},
            "focoSemanalAncora70": "Foco customizado sintético",
            "focoSemanalTrilha30": "",
            "ritualDomingoCycleIso": "2027-01-30",
            "ritualDomingoDoneIds": ["ritual_1", "ritual_2"],
            "curriculumEntries": {
                "inst_docentes_cr": {
                    "value": 1,
                    "proofStatus": "pdf_pronto",
                    "notes": "Comprovante sintético",
                },
                "ic_cnpq": {
                    "value": 2,
                    "proofStatus": "em_andamento",
                    "notes": "Projeto teste",
                },
            },
            "r1Milestones": [
                {
                    "id": "ms_prova_1",
                    "titulo": "Prova Teste R1",
                    "dateIso": "2027-10-18",
                    "categoria": "prova",
                    "nota": "Simulação",
                }
            ],
            "shiftSchedule": [
                {"dateIso": "2026-10-01", "mode": "plantao_12h"},  # antes de --since -> ignorado
                {"dateIso": "2027-02-02", "mode": "plantao_12h", "note": "Diurno"},
                {"dateIso": "2027-02-03", "mode": "pos_plantao"},
                {"dateIso": "2027-02-04", "mode": "dia_cheio"},
                {"dateIso": "2027-02-05", "mode": "pe_vespera"},
                {"dateIso": "2027-02-06", "mode": "fds"},  # ignorado
                {"dateIso": "2027-01-10", "mode": "ferias_4h"},  # ignorado
            ],
            "dailyTasks": [{"id": "ignored_task"}],
            "weeklyHistory": [{"week": "ignored"}],
        },
        "treinoClinico": {
            "internato": {
                "posPlantaoByDate": {
                    "2026-11-01": True,  # antes de --since -> ignorado
                    "2027-02-08": True,
                    "2027-02-09": False,
                }
            }
        },
    }


def test_import_dry_run_writes_nothing_and_reports_warnings(app):
    payload = _synthetic_backup_v2()
    with app.app_context():
        db = get_db()
        report = import_novo_pep.import_novo_pep_payload(
            db,
            "user_synth",
            payload,
            since_iso="2026-11-30",
            apply=False,
            today_local=date(2027, 2, 1),
        )
        assert report.applied is False
        assert report.diffs["plan"].novos == 1
        assert report.diffs["marcha"].novos == 1
        assert report.diffs["shifts"].novos == 1
        assert report.diffs["overrides"].novos == 4  # 02-03, 02-04, 02-05, 02-08
        assert report.diffs["curriculum"].novos == 2
        assert report.diffs["milestones"].novos == 1
        assert any("plantao_noturno" in w for w in report.warnings)

        # Nenhuma tabela recebeu escrita no dry-run
        for tbl in (
            "user_six_year_plan",
            "user_week_marcha",
            "user_shifts",
            "user_day_overrides",
            "user_curriculum_entries",
            "user_r1_milestones",
        ):
            cnt = db.execute(f"SELECT COUNT(*) AS c FROM {tbl} WHERE user_id = 'user_synth'").fetchone()["c"]
            assert cnt == 0


def test_import_apply_is_idempotent_and_migrates_curriculum_id(app):
    payload = _synthetic_backup_v2()
    with app.app_context():
        db = get_db()
        r1 = import_novo_pep.import_novo_pep_payload(
            db,
            "user_synth",
            payload,
            since_iso="2026-11-30",
            apply=True,
            today_local=date(2027, 2, 1),
        )
        assert r1.applied is True
        assert r1.diffs["curriculum"].novos == 2

        # Verificar migração de inst_docentes_cr -> inst_sus_rede
        curr_ids = {
            r["item_id"]: (r["value"], r["proof_status"], r["note"])
            for r in db.execute(
                "SELECT item_id, value, proof_status, note FROM user_curriculum_entries WHERE user_id = 'user_synth'"
            ).fetchall()
        }
        assert "inst_docentes_cr" not in curr_ids
        assert curr_ids["inst_sus_rede"] == (1.0, "pdf_pronto", "Comprovante sintético")
        assert curr_ids["ic_cnpq"] == (2.0, "em_andamento", "Projeto teste")

        # Verificar shift e overrides mapeados corretamente
        shifts = db.execute(
            "SELECT date_iso, kind, note FROM user_shifts WHERE user_id = 'user_synth'"
        ).fetchall()
        assert [(s["date_iso"], s["kind"], s["note"]) for s in shifts] == [
            ("2027-02-02", "plantao_12h_dia", "Diurno")
        ]

        overrides = {
            r["date_iso"]: r["mode"]
            for r in db.execute(
                "SELECT date_iso, mode FROM user_day_overrides WHERE user_id = 'user_synth'"
            ).fetchall()
        }
        assert overrides == {
            "2027-02-03": "pos_plantao",
            "2027-02-04": "integral",
            "2027-02-05": "meio_periodo",
            "2027-02-08": "pos_plantao",
        }

        # Segunda execução com mesmo payload -> 0 novos e 0 alterados em todas as entidades
        r2 = import_novo_pep.import_novo_pep_payload(
            db,
            "user_synth",
            payload,
            since_iso="2026-11-30",
            apply=True,
            today_local=date(2027, 2, 1),
        )
        for name, diff in r2.diffs.items():
            assert diff.novos == 0, f"{name} teve novos na 2ª execução"
            assert diff.alterados == 0, f"{name} teve alterados na 2ª execução"


def test_import_rejects_unsupported_version(app):
    with app.app_context():
        db = get_db()
        with pytest.raises(ValueError, match="Versão de backup não suportada"):
            import_novo_pep.import_novo_pep_payload(
                db, "user_synth", {"version": 1, "central6AnoState": {}}
            )
