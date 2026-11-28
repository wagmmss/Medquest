"""Blueprint de Busca Textual e Semântica (/api/search)."""
from __future__ import annotations

import logging
import re

from flask import Blueprint, g, jsonify, request

from .db import get_db
from .observability import record_domain_event
from .rate_limit import check_rate_limit
from .services.questions_service import _fts5_escape, _fts5_or_query

logger = logging.getLogger(__name__)

bp = Blueprint("search", __name__)


def _clean_search_snippet(raw_text: str | None) -> str:
    """Remove tags de imagem e normaliza espaços em snippets da busca."""
    cleaned = raw_text or ""
    cleaned = re.sub(r"!\[.*?\]\(.*?\)", "", cleaned)
    cleaned = re.sub(r"<img\b[^>]*>", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned and not cleaned.endswith("..."):
        cleaned += "..."
    return cleaned


def _fts_snippet_select(db) -> tuple[str, str, str]:
    """Resolve expressões de snippet e join conforme as colunas reais de questions_fts."""
    cols = [
        (r["name"] if isinstance(r, dict) or hasattr(r, "keys") else r[1]).lower()
        for r in db.execute("PRAGMA table_info(questions_fts)").fetchall()
    ]
    if "stem" in cols:
        stem_expr = f"snippet(questions_fts, {cols.index('stem')}, '<b>', '</b>', '...', 25)"
    else:
        stem_expr = "SUBSTR(q.stem, 1, 150)"

    if "explanation" in cols:
        exp_expr = f"snippet(questions_fts, {cols.index('explanation')}, '<b>', '</b>', '...', 25)"
        exp_join = ""
    else:
        exp_expr = "SUBSTR(e.explanation_text, 1, 150)"
        exp_join = "LEFT JOIN explanations e ON q.id = e.question_id"

    return stem_expr, exp_expr, exp_join


@bp.route("/search")
def search_questions():
    db = get_db()
    q = request.args.get("q", "").strip()
    institution = request.args.get("institution", "").strip()
    area = request.args.get("area", "").strip()
    year = request.args.get("year", "").strip()
    has_images = request.args.get("has_images", "false").lower() in ("true", "1")
    try:
        limit = min(max(int(request.args.get("limit", 50)), 1), 100)
    except (ValueError, TypeError):
        limit = 50
    try:
        offset = max(int(request.args.get("offset", 0)), 0)
    except (ValueError, TypeError):
        offset = 0

    if not q and not (institution or area or year or has_images):
        return jsonify([])

    semantic = request.args.get("semantic", "false").lower() == "true"
    if semantic and q:
        rl_resp = check_rate_limit("search_semantic", auth_limit=30, window_seconds=60)
        if rl_resp is not None:
            return rl_resp

    extra_filters = []
    extra_params: list = []
    if institution:
        extra_filters.append("q.institution_code = ?")
        extra_params.append(institution)
    if area:
        if area in ("Medicina Preventiva", "Medicina Preventiva e Social"):
            extra_filters.append("q.area IN (?, ?)")
            extra_params.extend(["Medicina Preventiva", "Medicina Preventiva e Social"])
        else:
            extra_filters.append("q.area = ?")
            extra_params.append(area)
    if year:
        try:
            year_value = int(year)
        except ValueError:
            year_value = None
        if year_value is not None:
            extra_filters.append("q.year = ?")
            extra_params.append(year_value)
    if has_images:
        extra_filters.append("EXISTS (SELECT 1 FROM question_images qi WHERE qi.question_id = q.id)")

    and_clause = " AND " + " AND ".join(extra_filters) if extra_filters else ""

    rows = []
    if q:
        expanded_terms = None
        if semantic:
            from .ai import expand_search_query
            expanded_terms = expand_search_query(q)

        fts_failed = False
        fts_query = ""
        try:
            fts_query = _fts5_or_query(expanded_terms or []) if semantic else _fts5_escape(q)
            if fts_query:
                stem_expr, exp_expr, exp_join = _fts_snippet_select(db)
                try:
                    sql_fts = f"""
                        SELECT q.id, q.institution_code, q.year, q.area, q.subtema, q.source_file, q.editorial_status,
                               {stem_expr} as stem_snippet,
                               {exp_expr} as exp_snippet,
                               EXISTS (SELECT 1 FROM question_images qi WHERE qi.question_id = q.id) as has_image
                        FROM questions_fts f
                        JOIN questions q ON q.id = f.rowid
                        {exp_join}
                        WHERE questions_fts MATCH ? {and_clause}
                        ORDER BY bm25(questions_fts)
                        LIMIT ? OFFSET ?
                    """
                    rows = db.execute(sql_fts, [fts_query, *extra_params, limit, offset]).fetchall()
                except Exception:
                    sql_fts = f"""
                        SELECT q.id, q.institution_code, q.year, q.area, q.subtema, q.source_file, q.editorial_status,
                               {stem_expr} as stem_snippet,
                               {exp_expr} as exp_snippet,
                               EXISTS (SELECT 1 FROM question_images qi WHERE qi.question_id = q.id) as has_image
                        FROM questions_fts f
                        JOIN questions q ON q.id = f.rowid
                        {exp_join}
                        WHERE questions_fts MATCH ? {and_clause}
                        ORDER BY f.rowid DESC
                        LIMIT ? OFFSET ?
                    """
                    rows = db.execute(sql_fts, [fts_query, *extra_params, limit, offset]).fetchall()
        except Exception as fts_err:
            logger.warning("FTS5 indisponivel ou consulta invalida (%s), acionando fallback", fts_err)
            rows = []
            fts_failed = True

        should_fallback_like = fts_failed or not fts_query
        if not rows and not should_fallback_like:
            has_fts_rows = db.execute("SELECT 1 FROM questions_fts LIMIT 1").fetchone() is not None
            should_fallback_like = not has_fts_rows

        if not rows and should_fallback_like:
            def make_like_clauses(term_list, joiner="AND"):
                clauses = []
                params = []
                for term in term_list:
                    if not term:
                        continue
                    term_clean = term.replace("%", "").replace("_", "")
                    if len(term_clean) < 2:
                        continue
                    clauses.append("(q.stem LIKE ? OR e.explanation_text LIKE ? OR q.area LIKE ? OR q.subtema LIKE ?)")
                    like_val = f"%{term_clean}%"
                    params.extend([like_val, like_val, like_val, like_val])
                if not clauses:
                    return "", []
                return f"({f' {joiner} '.join(clauses)})", params

            if semantic:
                where_sql, params = make_like_clauses(expanded_terms or [], "OR")
            else:
                terms = re.findall(r"\w+", q, flags=re.UNICODE)[:12]
                where_sql, params = make_like_clauses(terms, "AND")

            if where_sql:
                rows = db.execute(
                    f"""
                    SELECT q.id, q.institution_code, q.year, q.area, q.subtema, q.source_file, q.editorial_status,
                           SUBSTR(q.stem, 1, 150) as stem_snippet,
                           SUBSTR(e.explanation_text, 1, 150) as exp_snippet,
                           EXISTS (SELECT 1 FROM question_images qi WHERE qi.question_id = q.id) as has_image
                    FROM questions q
                    LEFT JOIN explanations e ON q.id = e.question_id
                    WHERE {where_sql} {and_clause}
                    ORDER BY q.id DESC
                    LIMIT ? OFFSET ?
                """,
                    [*params, *extra_params, limit, offset],
                ).fetchall()
    else:
        where_pure = and_clause.replace(" AND ", "", 1) if and_clause else "1=1"
        rows = db.execute(
            f"""
            SELECT q.id, q.institution_code, q.year, q.area, q.subtema, q.source_file, q.editorial_status,
                   SUBSTR(q.stem, 1, 150) as stem_snippet,
                   SUBSTR(e.explanation_text, 1, 150) as exp_snippet,
                   EXISTS (SELECT 1 FROM question_images qi WHERE qi.question_id = q.id) as has_image
            FROM questions q
            LEFT JOIN explanations e ON q.id = e.question_id
            WHERE {where_pure}
            ORDER BY q.id DESC
            LIMIT ? OFFSET ?
        """,
            [*extra_params, limit, offset],
        ).fetchall()

    out = []
    for row in rows:
        item = dict(row)
        item["is_autoral"] = bool(
            item.get("editorial_status") == "autoral"
            or (item.get("source_file") and "AUTORAL" in str(item.get("source_file")).upper())
        )
        item["has_image"] = bool(item.get("has_image", 0))
        item["stem_snippet"] = _clean_search_snippet(item.get("stem_snippet"))
        item["exp_snippet"] = _clean_search_snippet(item.get("exp_snippet"))
        out.append(item)

    record_domain_event(
        "search_executed",
        user_id=g.user_id,
        query_length=len(q),
        query_terms=len(re.findall(r"\w+", q, flags=re.UNICODE)),
        results_count=len(out),
        semantic=semantic,
    )
    return jsonify(out)
