"""Executa o bootstrap e as migrações do banco uma única vez por release.

Use antes de iniciar workers web em produção:
    python -m scripts.migrate_db
"""

from api import create_app
from api.db import db_transaction, get_db
from api.osce import seed_osce_stations


def _row_int(row, key: str = "cnt") -> int:
    if row is None:
        return 0
    if isinstance(row, dict) or hasattr(row, "keys"):
        return int(row[key] or 0)
    return int(row[0] or 0)


def sync_questions_fts(db) -> tuple[int, int]:
    """Remove entradas órfãs e insere questões ausentes em questions_fts de forma incremental."""
    has_fts = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='questions_fts'"
    ).fetchone()
    if not has_fts:
        return 0, 0

    cols = {
        (r["name"] if isinstance(r, dict) or hasattr(r, "keys") else r[1]).lower()
        for r in db.execute("PRAGMA table_info(questions_fts)").fetchall()
    }
    if "explanation" not in cols:
        q_count = _row_int(db.execute("SELECT COUNT(*) AS cnt FROM questions").fetchone())
        docsize_exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='questions_fts_docsize'"
        ).fetchone()
        if docsize_exists:
            docsize_count = _row_int(
                db.execute("SELECT COUNT(*) AS cnt FROM questions_fts_docsize").fetchone()
            )
            if docsize_count != q_count:
                with db_transaction(db, immediate=True):
                    db.execute("INSERT INTO questions_fts(questions_fts) VALUES('rebuild')")
                return 0, max(0, q_count - docsize_count)
        return 0, 0

    with db_transaction(db, immediate=True):
        del_cur = db.execute(
            "DELETE FROM questions_fts WHERE rowid NOT IN (SELECT id FROM questions)"
        )
        deleted = int(getattr(del_cur, "rowcount", 0) or 0)
        del_cur.close()

        ins_cur = db.execute(
            """
            INSERT INTO questions_fts (rowid, stem, explanation)
            SELECT q.id, q.stem, e.explanation_text
            FROM questions q
            LEFT JOIN explanations e ON q.id = e.question_id
            WHERE q.id NOT IN (SELECT rowid FROM questions_fts)
            """
        )
        inserted = int(getattr(ins_cur, "rowcount", 0) or 0)
        ins_cur.close()

    return deleted, inserted


def main():
    app = create_app(initialize_db=True)
    with app.app_context():
        db = get_db()
        seed_osce_stations(db)
        sync_questions_fts(db)


if __name__ == "__main__":
    main()
