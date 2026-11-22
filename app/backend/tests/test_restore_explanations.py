import sqlite3
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = BACKEND_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from restore_explanations_from_raw import clean_html_buggy, restore_explanation_text, run_restore, sanitize_text  # noqa: E402


def test_restore_recovers_lt_and_lists_and_preserves_sanitization():
    raw_html_intro = (
        "<p>Quando RR &gt; 1 há aumento. Se RR &lt; 1, temos fator de proteção.</p>"
        "<p>Critérios:</p><ul><li>Plaquetopenia &lt; 150 mil</li><li>Ascite leve</li></ul>"
    )
    raw_html_opt_a = "<p>A alternativa da Medway cita <strong>colo &lt;25 mm</strong> e está errada.</p>"

    # Simula banco atual gerado pelo parser legado + sanitize_medway ("da Medway" -> "do MedQuest")
    buggy_intro = clean_html_buggy(raw_html_intro)
    buggy_opt_a, _ = sanitize_text(clean_html_buggy(raw_html_opt_a), 99999)

    current_db_text = (
        "**Gabarito**: Letra D\n\n"
        "**Pulo do Gato**:\nResumo revisado manualmente.\n\n"
        f"**Raciocínio Clínico**:\n{buggy_intro}\n\n"
        f"**Análise dos Distratores**:\n- **Letra A**: {buggy_opt_a}"
    )

    candidates = [
        {
            "detail": {"content": "<p>Enunciado teste</p>"},
            "explanation": {
                "conclusion": "<p>Conclusão antiga que NÃO deve sobrescrever a revisada.</p>",
                "introduction": raw_html_intro,
                "option_a": raw_html_opt_a,
            },
        }
    ]

    restored, stats = restore_explanation_text(99999, current_db_text, candidates, restore_lists=True)

    assert "Se RR < 1, temos fator de proteção." in restored
    assert "- Plaquetopenia < 150 mil" in restored
    assert "**colo <25 mm**" in restored
    # Preserva edição manual do Pulo do Gato e sanitização MedQuest
    assert "Resumo revisado manualmente." in restored
    assert "Medway" not in restored
    assert "MedQuest" in restored
    assert "**Gabarito**: Letra D" in restored
    assert stats["fields_lt_restored"] == 2


def test_restore_dry_run_and_apply_on_temp_sqlite(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    raw_html = "<p>Se pH &lt; 4,5 indica vaginite citolítica.</p>"
    buggy = clean_html_buggy(raw_html)

    (raw_dir / "track_1.json").write_text(
        '{"track_id": 1, "questions": [{"detail": {"content": "<p>Caso clínico alfa beta</p>"}, '
        '"explanation": {"introduction": "' + raw_html + '"}}]}',
        encoding="utf-8",
    )

    db_path = tmp_path / "test.db"
    backup_dir = tmp_path / "backups"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE questions (id INTEGER PRIMARY KEY, source_file TEXT, source_number INTEGER, stem TEXT, status TEXT)"
    )
    conn.execute(
        "CREATE TABLE explanations (question_id INTEGER PRIMARY KEY, explanation_text TEXT, generated_at TEXT, reviewed_at TEXT)"
    )
    conn.execute(
        "INSERT INTO questions VALUES (1, 'Prova [1]', 1, 'Caso clínico alfa beta', 'active')"
    )
    conn.execute(
        "INSERT INTO explanations VALUES (1, ?, '2026-09-26', '2026-09-26')",
        (f"**Gabarito**: Letra A\n\n**Raciocínio Clínico**:\n{buggy}",),
    )
    conn.commit()
    conn.close()

    dry = run_restore(db_path, raw_dir, backup_dir, apply=False)
    assert dry["mode"] == "dry_run"
    assert dry["summary"]["questions_updated"] == 1
    assert not backup_dir.exists()

    applied = run_restore(db_path, raw_dir, backup_dir, apply=True)
    assert applied["mode"] == "apply"
    assert applied["summary"]["questions_updated"] == 1
    assert applied["backup"] is not None
    assert len(list(backup_dir.glob("*.db"))) == 1

    conn = sqlite3.connect(db_path)
    updated_txt = conn.execute("SELECT explanation_text FROM explanations WHERE question_id = 1").fetchone()[0]
    conn.close()
    assert "Se pH < 4,5 indica vaginite citolítica." in updated_txt
