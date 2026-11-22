#!/usr/bin/env python3
"""
Restauração cirúrgica e determinística de desigualdades '<' (e opcionalmente listas HTML)
perdidas durante a extração antiga em `clean_html_to_markdown` (`medquest.db`).

Modo padrão: `--dry-run` (apenas lê o banco e imprime estatísticas/amostras).
Use `--apply` para gravar com backup SHA-256 verificado em `app/backend/data/backups/`.
"""

from __future__ import annotations

import argparse
import collections
import glob
import hashlib
import html
import json
import re
import sqlite3
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent.parent
DEFAULT_DB = BACKEND_DIR / "medquest.db"
DEFAULT_RAW_DIR = BACKEND_DIR / "data" / "medway_extracted"
DEFAULT_BACKUP_DIR = BACKEND_DIR / "data" / "backups"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_medway import clean_html_to_markdown as clean_html_fixed  # noqa: E402

try:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from sanitize_medway import sanitize_text  # noqa: E402
except ImportError:
    def sanitize_text(text: str, qid: int) -> Tuple[str, bool]:
        return text, False


def _norm_stem(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", s)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean_html_buggy(raw_html: Any) -> str:
    """Reproduz exatamente o parser legado que rodou em 2026-09-26 para pareamento 1:1."""
    if not isinstance(raw_html, str) or not raw_html.strip():
        return ""
    txt = html.unescape(raw_html)
    txt = re.sub(r"</p>\s*<p[^>]*>", "\n\n", txt, flags=re.IGNORECASE)
    txt = re.sub(r"<br\s*/?>", "\n", txt, flags=re.IGNORECASE)
    txt = re.sub(r"<(strong|b)[^>]*>(.*?)</\1>", r"**\2**", txt, flags=re.DOTALL | re.IGNORECASE)
    txt = re.sub(r"<(em|i)[^>]*>(.*?)</\1>", r"*\2*", txt, flags=re.DOTALL | re.IGNORECASE)
    txt = re.sub(r'<img\b[^>]*\bsrc=["\'](https?://[^"\']+)["\'][^>]*>', r"\n\n![imagem](\1)\n\n", txt, flags=re.IGNORECASE)
    txt = re.sub(r'<a\b[^>]*\bhref=["\'](https?://[^"\']+\.(?:png|jpe?g|gif|webp|svg)(?:\?[^"\']*)?)["\'][^>]*>.*?</a>', r"\n\n![imagem](\1)\n\n", txt, flags=re.IGNORECASE)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = re.sub(r'(?<!!)(?:\[([^\]]*)\])\((https?://[^\)]+\.(?:png|jpe?g|gif|webp|svg)(?:\?[^\)]*)?)\)', r'![imagem](\2)', txt, flags=re.IGNORECASE)
    txt = re.sub(r'(?<![(\'"])(https?://(?:cdn\.medway\.com\.br|storage\.googleapis\.com)[^\s"\'<>]+\.(?:png|jpe?g|gif|webp|svg)(?:\?[^\s"\'<>]*)?)(?![)\'"])', r'\n\n![imagem](\1)\n\n', txt, flags=re.IGNORECASE)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in txt.splitlines()]
    txt = "\n".join(lines)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    return txt.strip()


def _strip_option_prefixes(text: str) -> str:
    out = re.sub(r"^[A-E]\)\s*", "", text, flags=re.IGNORECASE)
    out = re.sub(r"^(?:[-*•]\s*)?(?:Alternativa|Letra)\s+[A-E](?:\s*\([^)]*\))?\s*:?\s*", "", out, flags=re.IGNORECASE)
    out = re.sub(r"^[A-E]\s*-\s*(?:Correta|Incorreta)\.?\s*", "", out, flags=re.IGNORECASE)
    return out.strip()


def _extract_image_urls(text: str) -> List[str]:
    return re.findall(r"https?://[^\s\)\"'>]+", text or "")


def _load_raw_index(raw_dir: Path) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, List[Dict[str, Any]]]]:
    by_track_id: Dict[str, List[Dict[str, Any]]] = {}
    by_stem: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    files = sorted(glob.glob(str(raw_dir / "**" / "*.json"), recursive=True))
    for fp in files:
        try:
            with open(fp, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        if not isinstance(d, dict) or "questions" not in d:
            continue
        tid = str(d.get("track_id") or "")
        qs = d.get("questions", [])
        if tid:
            by_track_id[tid] = qs
        for q in qs:
            det = q.get("detail") or {}
            st = re.sub(r"</?[a-zA-Z][^>]*>", " ", det.get("content") or "")
            k = _norm_stem(st)[:100]
            if k:
                by_stem[k].append(q)
    return by_track_id, by_stem


def _raw_fields(exp_dict: Dict[str, Any]) -> List[Tuple[str, str]]:
    fields = [
        ("conclusion", exp_dict.get("conclusion") or ""),
        ("intro", exp_dict.get("introduction") or exp_dict.get("actual_explanation") or exp_dict.get("full_explanation") or ""),
        ("bib", exp_dict.get("bibliography") or ""),
    ]
    for let in "abcde":
        fields.append((f"opt_{let}", exp_dict.get(f"option_{let}") or exp_dict.get(f"short_option_{let}") or ""))
    return [(k, v) for k, v in fields if isinstance(v, str) and v.strip()]


def restore_explanation_text(
    qid: int,
    current_text: str,
    candidate_questions: List[Dict[str, Any]],
    *,
    restore_lists: bool = True,
) -> Tuple[str, Dict[str, int]]:
    """
    Tenta restaurar apenas campos/parágrafos de `current_text` que batem 1:1 com `clean_html_buggy`
    de um dos JSONs candidatos, preservando gabaritos, edições manuais e sanitização MedQuest.
    """
    stats: Dict[str, int] = {"fields_lt_restored": 0, "fields_list_restored": 0, "paras_lt_restored": 0}
    if not current_text or not candidate_questions:
        return current_text, stats

    updated = current_text
    orig_urls = _extract_image_urls(current_text)

    for q in candidate_questions:
        exp = q.get("explanation")
        if not isinstance(exp, dict):
            continue

        for fname, raw_h in _raw_fields(exp):
            has_lt_risk = ("&lt;" in raw_h) or bool(re.search(r"<(?![a-zA-Z/!])", raw_h))
            has_list = restore_lists and ("<li" in raw_h.lower())
            if not has_lt_risk and not has_list:
                continue

            bug = clean_html_buggy(raw_h)
            fix = clean_html_fixed(raw_h)
            if not bug or bug == fix:
                continue

            if fname.startswith("opt_"):
                bug = _strip_option_prefixes(bug)
                fix = _strip_option_prefixes(fix)
                if not bug or bug == fix:
                    continue

            bug_san, _ = sanitize_text(bug, qid)
            fix_san, _ = sanitize_text(fix, qid)

            # 1) Match exato de campo inteiro (preferido e 100% cirúrgico)
            matched_needle: Optional[str] = None
            replacement: Optional[str] = None
            if bug_san and bug_san in updated:
                matched_needle = bug_san
                replacement = fix_san
            elif bug and bug in updated:
                matched_needle = bug
                replacement = fix_san

            if matched_needle and replacement and matched_needle != replacement:
                # Valida paridade de URLs do campo antes de substituir
                if _extract_image_urls(matched_needle) == _extract_image_urls(replacement):
                    updated = updated.replace(matched_needle, replacement, 1)
                    if has_lt_risk:
                        stats["fields_lt_restored"] += 1
                    elif has_list:
                        stats["fields_list_restored"] += 1
                    continue

            # 2) Fallback por parágrafo apenas para campos com '<' comido (quando outro parágrafo foi editado)
            if has_lt_risk:
                bug_paras = [p.strip() for p in bug_san.split("\n\n") if p.strip()]
                fix_paras = [p.strip() for p in fix_san.split("\n\n") if p.strip()]
                if len(bug_paras) == len(fix_paras):
                    for bp, fp in zip(bug_paras, fix_paras):
                        if bp != fp and len(bp) >= 25 and bp in updated:
                            if _extract_image_urls(bp) == _extract_image_urls(fp):
                                updated = updated.replace(bp, fp, 1)
                                stats["paras_lt_restored"] += 1

    # Garantia rígida: nenhuma URL de imagem pode ser alterada ou perdida
    if _extract_image_urls(updated) != orig_urls:
        return current_text, {"fields_lt_restored": 0, "fields_list_restored": 0, "paras_lt_restored": 0}

    return updated, stats


def run_restore(
    db_path: Path,
    raw_dir: Path,
    backup_dir: Path,
    *,
    apply: bool = False,
    restore_lists: bool = True,
) -> Dict[str, Any]:
    by_track_id, by_stem = _load_raw_index(raw_dir)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) if not apply else sqlite3.connect(db_path, timeout=60.0)
    try:
        rows = conn.execute(
            """
            SELECT q.id, q.source_file, q.source_number, q.stem, e.explanation_text
            FROM questions q
            JOIN explanations e ON q.id = e.question_id
            WHERE (q.status = 'active' OR q.status IS NULL)
              AND e.explanation_text IS NOT NULL
            ORDER BY q.id
            """
        ).fetchall()

        summary = collections.Counter()
        updates: List[Tuple[str, int]] = []
        samples: List[Dict[str, Any]] = []

        for qid, src, num, stem, exp_txt in rows:
            candidates: List[Dict[str, Any]] = []
            m = re.search(r"\[(\d+)\]$", src or "")
            if m and m.group(1) in by_track_id:
                qs = by_track_id[m.group(1)]
                if num and 1 <= num <= len(qs):
                    candidates.append(qs[num - 1])
            k = _norm_stem(stem)[:100]
            if k in by_stem:
                for cand in by_stem[k]:
                    if cand not in candidates:
                        candidates.append(cand)

            if not candidates:
                summary["questions_without_raw_json"] += 1
                continue

            new_txt, st = restore_explanation_text(qid, exp_txt, candidates, restore_lists=restore_lists)
            if new_txt != exp_txt:
                summary["questions_updated"] += 1
                for sk, sv in st.items():
                    summary[sk] += sv
                updates.append((new_txt, qid))
                if qid in (8512, 8617, 8620, 8923, 12788, 23346) or len(samples) < 5:
                    samples.append({"qid": qid, "stats": st, "old_len": len(exp_txt), "new_len": len(new_txt)})

        backup_path_str: Optional[str] = None
        if apply and updates:
            backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup_path = backup_dir / f"{db_path.stem}-pre-lt-restore-{stamp}.db"
            with sqlite3.connect(backup_path) as bconn:
                conn.backup(bconn)
            backup_sha = _sha256(backup_path)
            backup_path_str = f"{backup_path} (sha256={backup_sha[:12]}...)"

            now_iso = datetime.now(timezone.utc).isoformat()
            conn.execute("BEGIN TRANSACTION")
            try:
                conn.executemany(
                    "UPDATE explanations SET explanation_text = ?, reviewed_at = ? WHERE question_id = ?",
                    [(txt, now_iso, qid) for txt, qid in updates],
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

        return {
            "mode": "apply" if apply else "dry_run",
            "total_active_checked": len(rows),
            "summary": dict(summary),
            "backup": backup_path_str,
            "samples": samples,
        }
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Restaura desigualdades '<' e listas HTML perdidas em medquest.db.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR)
    parser.add_argument("--apply", action="store_true", help="Grava no banco após criar backup verificado.")
    parser.add_argument("--only-lt", action="store_true", help="Restaura apenas campos com '<' perdido (não converte listas).")
    args = parser.parse_args()

    report = run_restore(
        args.db,
        args.raw_dir,
        args.backup_dir,
        apply=args.apply,
        restore_lists=not args.only_lt,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
