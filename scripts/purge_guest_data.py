#!/usr/bin/env python3
"""Remove linhas órfãs de sessões de visitante (user_id LIKE 'guest:%').

Por padrão roda em modo --dry-run (somente leitura) imprimindo a contagem por tabela.
Com --apply, executa a remoção atômica via api/db.py (compatível com SQLite local e Turso).
Nunca toca na tabela `explanations`.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "app" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from api.db import db_transaction, get_db  # noqa: E402

SAFE_TABLE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PROTECTED_TABLES = frozenset({"explanations", "questions", "alternatives", "question_images", "schema_migrations"})


def discover_user_tables(db) -> list[str]:
    """Descobre dinamicamente tabelas de usuário que possuem coluna `user_id`."""
    rows = db.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    tables: list[str] = []
    for row in rows:
        name = str(row["name"])
        if name in PROTECTED_TABLES or not SAFE_TABLE_RE.fullmatch(name):
            continue
        cols = db.execute(f"PRAGMA table_info({name})").fetchall()
        if any(str(col["name"]) == "user_id" for col in cols):
            tables.append(name)
    return tables


def count_guest_rows(db, tables: list[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in tables:
        row = db.execute(f"SELECT COUNT(*) AS cnt FROM {table} WHERE user_id LIKE 'guest:%'").fetchone()
        counts[table] = int(row["cnt"] or 0) if row else 0
    return counts


def purge_guest_rows(db, *, apply: bool = False) -> tuple[dict[str, int], dict[str, int]]:
    tables = discover_user_tables(db)
    before = count_guest_rows(db, tables)
    if not apply:
        return before, before

    with db_transaction(db, immediate=True):
        for table in tables:
            if before.get(table, 0) > 0:
                db.execute(f"DELETE FROM {table} WHERE user_id LIKE 'guest:%'")

    after = count_guest_rows(db, tables)
    return before, after


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Limpa registros legados com user_id LIKE 'guest:%'.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Executa a exclusão de fato. Sem esta flag, roda apenas em modo dry-run.",
    )
    args = parser.parse_args(argv)

    db = get_db()
    before, after = purge_guest_rows(db, apply=args.apply)
    mode = "APPLY" if args.apply else "DRY-RUN"
    total_before = sum(before.values())
    total_after = sum(after.values())

    print(f"[purge_guest_data] Modo: {mode}")
    print(f"{'Tabela':<36} {'Antes':>8} {'Depois':>8}")
    print("-" * 54)
    for table in sorted(before):
        print(f"{table:<36} {before[table]:>8} {after[table]:>8}")
    print("-" * 54)
    print(f"{'TOTAL':<36} {total_before:>8} {total_after:>8}")
    if not args.apply and total_before > 0:
        print("Nenhuma linha foi removida. Execute com --apply para efetivar a limpeza.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
