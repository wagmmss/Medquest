"""
Serviço de domínio para o motor de questões, amostragem, busca FTS5 e batch SRS.
Extraído de `api/questions.py` para manter os handlers HTTP finos e testáveis.
"""
import random
import re
import sys
from datetime import datetime, timedelta, timezone

from ..cache import SimpleTTLCache, catalog_cache_enabled, db_cache_scope
from ..edital_profiles import get_canonical_institution, resolve_institution_codes
from ..filters import TARGET_INSTITUTION_RATIO

_question_catalog_cache = SimpleTTLCache(21600, max_size=8)
_meta_global_cache = SimpleTTLCache(300, max_size=128)
_question_batch_cols_cache = SimpleTTLCache(21600, max_size=8)
_VALID_STATUS_TOKENS = frozenset({"unanswered", "new", "wrong", "answered", "srs_due", "favorite"})
_UNSUPPORTED_CATALOG_FILTER_KEYS = ("source", "specialty", "question_type")
_YEAR_INT_RE = re.compile(r"^-?\d+$")
_BATCH_QUESTION_COLS = (
    "id",
    "source_file",
    "source_number",
    "year",
    "institution_code",
    "institution_label",
    "topic",
    "area",
    "subtema",
    "stem",
    "correct_letter",
    "editorial_status",
    "is_verified",
    "last_updated_at",
    "technical_note",
    "clinical_case_id",
    "usp_macro",
    "usp_micro",
)


def invalidate_service_caches() -> None:
    _question_catalog_cache.clear()
    _meta_global_cache.clear()
    _question_batch_cols_cache.clear()


def get_question_batch_columns(db) -> str:
    """Retorna lista segura de colunas necessárias de `questions` (evita SELECT *)."""
    use_cache = catalog_cache_enabled()
    cache_key = ("batch_cols", db_cache_scope())
    if use_cache:
        cached = _question_batch_cols_cache.get(cache_key)
        if isinstance(cached, str) and cached:
            return cached
    try:
        existing = {r["name"] for r in db.execute("PRAGMA table_info(questions)").fetchall()}
        selected = [c for c in _BATCH_QUESTION_COLS if c in existing]
        cols_sql = ", ".join(selected) if selected else "*"
    except Exception:
        cols_sql = "*"
    if use_cache and cols_sql != "*":
        _question_batch_cols_cache.set(cache_key, cols_sql)
    return cols_sql


def check_is_correct(selected: str, correct_letter: str | None, alts_correct: set[str] | None = None) -> int:
    """Verifica se a alternativa selecionada pelo aluno é considerada correta.

    Suporta:
    - Letras únicas (ex: 'A', 'B')
    - Múltiplas alternativas válidas / aceitas pós-recurso (ex: 'B, C', 'A, B')
    - Questões anuladas pela banca (ex: 'ANULADA'), onde todos os candidatos pontuam
    - Verificação direta contra alternativas marcadas com is_correct=1
    """
    sel = (selected or "").strip().upper()
    if not sel:
        return 0
    if alts_correct and sel in alts_correct:
        return 1
    corr = (correct_letter or "").strip().upper()
    if not corr:
        return 0
    if corr == "ANULADA":
        return 1
    valid_letters = {c.strip() for c in corr.split(",") if c.strip()}
    return 1 if sel in valid_letters else 0


def _sample_ids(db, where_clause, params, limit):
    """Amostragem rápida por faixa de IDs, evitando ORDER BY RANDOM().

    Obtém min/max ID, gera candidatos aleatórios em Python e filtra.
    Fallback para ORDER BY RANDOM() se a faixa for muito esparsa.
    """
    bounds = db.execute(
        f"SELECT MIN(q.id) AS lo, MAX(q.id) AS hi, COUNT(*) AS n FROM questions q WHERE {where_clause}",
        params,
    ).fetchone()
    lo, hi, n = bounds["lo"], bounds["hi"], bounds["n"]
    if not lo or n == 0:
        return []
    effective_limit = min(limit, n)
    if n > 0 and (hi - lo + 1) / n < 5:
        sample_size = min(effective_limit * 3, hi - lo + 1, 900)
        candidates = random.sample(range(lo, hi + 1), sample_size)
        placeholders = ",".join("?" * len(candidates))
        rows = db.execute(
            f"SELECT q.id FROM questions q WHERE q.id IN ({placeholders}) AND {where_clause} LIMIT ?",
            (*candidates, *params, effective_limit),
        ).fetchall()
        ids = [r["id"] for r in rows]
        if len(ids) >= effective_limit:
            return ids[:effective_limit]
    rows = db.execute(
        f"SELECT q.id FROM questions q WHERE {where_clause} ORDER BY RANDOM() LIMIT ?",
        (*params, effective_limit),
    ).fetchall()
    return [r["id"] for r in rows]


def _sample_prioritized_ids(db, where_clause, params, limit, target_insts, has_explicit_inst_filter=False):
    """Amostragem com proporção prioritária das bancas-alvo do aluno com fallback de diversidade."""
    if not target_insts or has_explicit_inst_filter or limit <= 0:
        return _sample_ids(db, where_clause, params, limit)

    target_quota = max(1, int(round(limit * TARGET_INSTITUTION_RATIO)))
    target_quota = min(target_quota, limit)
    placeholders = ",".join("?" * len(target_insts))
    inst_tuple = tuple(target_insts)

    where_target = f"{where_clause} AND q.institution_code IN ({placeholders})"
    target_ids = _sample_ids(db, where_target, (*params, *inst_tuple), target_quota)

    remaining_needed = limit - len(target_ids)
    if remaining_needed <= 0:
        return target_ids[:limit]

    where_other = f"{where_clause} AND (q.institution_code NOT IN ({placeholders}) OR q.institution_code IS NULL)"
    other_ids = _sample_ids(db, where_other, (*params, *inst_tuple), remaining_needed)

    combined = list(target_ids) + list(other_ids)

    shortfall = limit - len(combined)
    if shortfall > 0:
        exclude_ph = ",".join("?" * len(combined))
        where_fallback = f"{where_clause} AND q.id NOT IN ({exclude_ph})" if combined else where_clause
        fallback_params = (*params, *combined) if combined else params
        extra_ids = _sample_ids(db, where_fallback, fallback_params, shortfall)
        combined.extend(extra_ids)

    return combined[:limit]


def _bounded_int(value, default, minimum, maximum):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _fts_phrase(value):
    """Converte texto livre em uma expressão FTS5 segura e limitada."""
    words = re.findall(r"\w+", value or "", flags=re.UNICODE)[:12]
    return " ".join(words)


def _fts5_escape(query_str: str) -> str:
    tokens = re.findall(r"\w+", query_str, flags=re.UNICODE)
    valid_tokens = [t for t in tokens if len(t) >= 2]
    if not valid_tokens:
        return ""
    return " AND ".join(f'"{t}"*' for t in valid_tokens[:12])


def _fts5_or_query(terms: list[str]) -> str:
    tokens: list[str] = []
    for term in terms:
        for t in re.findall(r"\w+", term, flags=re.UNICODE):
            if len(t) >= 2 and t not in tokens:
                tokens.append(t)
    if not tokens:
        return ""
    return " OR ".join(f'"{t}"*' for t in tokens[:16])


def _resolve_answered_at(client_iso: str | None, fallback_now: datetime | None = None) -> str:
    """Valida e aplica clamp defensivo no timestamp da tentativa contra clock skew."""
    server_now = (fallback_now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if not client_iso:
        return server_now.isoformat()
    try:
        parsed = datetime.fromisoformat(str(client_iso).strip().replace("Z", "+00:00"))
        parsed_utc = parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        min_allowed = server_now - timedelta(days=30)
        if parsed_utc > server_now or parsed_utc < min_allowed:
            parsed_utc = server_now
        return parsed_utc.isoformat()
    except (ValueError, TypeError):
        return server_now.isoformat()


def _defer_question_review(db, qid, user_id):
    """Give an unrated answer a day of rest without inventing an FSRS rating."""
    resume_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    db.execute(
        """UPDATE spaced_repetition SET next_review_date = ?
           WHERE question_id = ? AND user_id = ?
             AND (next_review_date IS NULL OR next_review_date < ?)""",
        (resume_at, qid, user_id, resume_at),
    )


def _defer_questions_batch(db, q_ids: list[int], user_id) -> None:
    """Adia em lote um conjunto de questões sem inventar rating FSRS."""
    if not q_ids:
        return
    resume_at = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    rows = [(resume_at, qid, user_id, resume_at) for qid in dict.fromkeys(q_ids)]
    sql = """UPDATE spaced_repetition SET next_review_date = ?
             WHERE question_id = ? AND user_id = ?
               AND (next_review_date IS NULL OR next_review_date < ?)"""
    if len(rows) == 1:
        db.execute(sql, rows[0])
    else:
        db.executemany(sql, rows)


def _fetch_batch_metadata_with_counts(
    db, q_ids: list[int], chunk_size: int = 500
) -> tuple[dict, dict, dict, dict]:
    q_map = {}
    correct_alts_map = {}
    exp_map = {}
    alts_count_map = {}
    unique_ids = list(dict.fromkeys(q_ids))
    if not unique_ids:
        return q_map, correct_alts_map, exp_map, alts_count_map

    for i in range(0, len(unique_ids), chunk_size):
        chunk = unique_ids[i:i + chunk_size]
        placeholders = ",".join("?" * len(chunk))
        q_exp_sql = f"""
            SELECT q.id, q.correct_letter, e.explanation_text
            FROM questions q
            LEFT JOIN explanations e ON e.question_id = q.id
            WHERE q.id IN ({placeholders})
        """
        alts_sql = (
            f"SELECT question_id, letter, is_correct FROM alternatives "
            f"WHERE question_id IN ({placeholders})"
        )

        if hasattr(db, "batch"):
            batch_res = db.batch([(q_exp_sql, chunk), (alts_sql, chunk)])
            qs = batch_res[0].fetchall()
            alts_rows = batch_res[1].fetchall()
        else:
            qs = db.execute(q_exp_sql, chunk).fetchall()
            alts_rows = db.execute(alts_sql, chunk).fetchall()

        for q in qs:
            qid = q["id"]
            q_map[qid] = q["correct_letter"]
            if q["explanation_text"] is not None:
                exp_map[qid] = q["explanation_text"]

        for a in alts_rows:
            qid = a["question_id"]
            alts_count_map[qid] = alts_count_map.get(qid, 0) + 1
            if a["is_correct"] and a["letter"]:
                correct_alts_map.setdefault(qid, set()).add(a["letter"].strip().upper())

    return q_map, correct_alts_map, exp_map, alts_count_map


def _fetch_batch_metadata(db, q_ids: list[int], chunk_size: int = 500) -> tuple[dict, dict, dict]:
    q_map, correct_alts_map, exp_map, _ = _fetch_batch_metadata_with_counts(db, q_ids, chunk_size=chunk_size)
    return q_map, correct_alts_map, exp_map


def _fetch_srs_map(db, q_ids: list[int], user_id: int, chunk_size: int = 500) -> dict:
    srs_map = {}
    unique_ids = list(dict.fromkeys(q_ids))
    for i in range(0, len(unique_ids), chunk_size):
        chunk = unique_ids[i:i + chunk_size]
        placeholders = ",".join("?" * len(chunk))
        chunk_args = [*chunk, user_id]
        srs_data = db.execute(
            f"SELECT question_id, fsrs_card FROM spaced_repetition WHERE question_id IN ({placeholders}) AND user_id = ?",
            chunk_args,
        ).fetchall()
        for card in srs_data:
            srs_map[card["question_id"]] = card["fsrs_card"]
    return srs_map


def supports_catalog_filters(args) -> bool:
    """Indica se todos os filtros da requisição podem ser resolvidos pelo catálogo leve."""
    return not any(key in args and args.getlist(key) for key in _UNSUPPORTED_CATALOG_FILTER_KEYS)


def _intern_str(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return sys.intern(value) if value else ""
    return str(value)


def _load_question_catalog(db) -> tuple[tuple, ...]:
    """Carrega e cacheia os metadados leves das questões ativas (0 leituras em hits)."""
    use_cache = catalog_cache_enabled()
    cache_key = ("question_catalog", db_cache_scope())
    if use_cache:
        cached = _question_catalog_cache.get(cache_key)
        if cached is not None:
            return cached

    q_sql = """
        SELECT id, institution_code, institution_label, year, area, subtema, topic,
               CASE WHEN UPPER(COALESCE(correct_letter, '')) = 'ANULADA' THEN 1 ELSE 0 END AS is_annulled
        FROM questions
        WHERE missing_alts = 0
    """
    img_sql = "SELECT DISTINCT question_id FROM question_images"

    batch_res = None
    if hasattr(db, "batch"):
        try:
            batch_res = db.batch([(q_sql, ()), (img_sql, ())])
        except Exception:
            batch_res = None

    if batch_res is not None:
        q_rows = batch_res[0].fetchall()
        img_rows = batch_res[1].fetchall()
    else:
        q_rows = db.execute(q_sql).fetchall()
        try:
            img_rows = db.execute(img_sql).fetchall()
        except Exception:
            img_rows = []

    image_qids = {int(r["question_id"]) for r in img_rows}
    catalog = tuple(
        (
            int(r["id"]),
            _intern_str(r["institution_code"]),
            _intern_str(r["institution_label"]),
            r["year"],
            _intern_str(r["area"]),
            _intern_str(r["subtema"]),
            _intern_str(r["topic"]),
            bool(r["is_annulled"]),
            int(r["id"]) in image_qids,
        )
        for r in q_rows
    )
    if use_cache:
        _question_catalog_cache.set(cache_key, catalog)
    return catalog


def _parse_catalog_filters(args) -> dict:
    institutions = []
    for item in args.getlist("institution"):
        if "," in item:
            for part in item.split(","):
                part_clean = part.strip()
                if part_clean:
                    institutions.extend(resolve_institution_codes(part_clean))
        elif item.strip():
            institutions.extend(resolve_institution_codes(item.strip()))
    inst_set = set(institutions) if institutions else None

    year_ints: set[int] = set()
    year_strs: set[str] = set()
    for item in args.getlist("year"):
        for part in str(item).split(","):
            part_clean = part.strip()
            if not part_clean:
                continue
            if _YEAR_INT_RE.match(part_clean):
                year_ints.add(int(part_clean))
            else:
                year_strs.add(part_clean)

    raw_areas = args.getlist("area")
    area_set = None
    if raw_areas:
        areas = []
        for a in raw_areas:
            areas.append(a)
            if a == "Medicina Preventiva":
                areas.append("Medicina Preventiva e Social")
            elif a == "Medicina Preventiva e Social":
                areas.append("Medicina Preventiva")
        area_set = set(areas)

    subtemas = args.getlist("subtema")
    subtema_set = set(subtemas) if subtemas else None

    topics = args.getlist("topic")
    topic_set = set(topics) if topics else None

    raw_status = (args.get("status") or "all").strip().lower()
    raw_tokens = [s.strip() for s in raw_status.split(",") if s.strip() and s.strip() != "all"]
    if not raw_tokens and args.get("unanswered_only") in ("true", "1"):
        raw_tokens = ["unanswered"]
    status_tokens = tuple(dict.fromkeys(tok for tok in raw_tokens if tok in _VALID_STATUS_TOKENS))

    raw_id = args.get("id")
    id_filter = None
    if raw_id:
        raw_id_str = str(raw_id).strip()
        id_filter = int(raw_id_str) if _YEAR_INT_RE.match(raw_id_str) else raw_id_str

    return {
        "inst_set": inst_set,
        "has_year_filter": bool(year_ints or year_strs),
        "year_ints": year_ints,
        "year_strs": year_strs,
        "area_set": area_set,
        "subtema_set": subtema_set,
        "topic_set": topic_set,
        "status_tokens": status_tokens,
        "favorite_only": args.get("favorite") in ("1", "true"),
        "has_images_only": args.get("has_images") in ("1", "true"),
        "exclude_annulled": args.get("exclude_annulled") in ("1", "true"),
        "id_filter": id_filter,
    }


def _fetch_user_question_sets(
    db,
    user_id,
    *,
    need_answered: bool,
    need_wrong: bool,
    need_srs_due: bool,
    need_fav: bool,
) -> dict[str, set[int]]:
    sets: dict[str, set[int]] = {
        "answered": set(),
        "wrong": set(),
        "srs_due": set(),
        "fav": set(),
    }
    if not user_id:
        return sets

    queries: list[tuple[str, tuple]] = []
    labels: list[str] = []

    if need_wrong:
        queries.append((
            """
            SELECT question_id, is_correct
            FROM (
                SELECT question_id, is_correct,
                       ROW_NUMBER() OVER (PARTITION BY question_id ORDER BY id DESC) AS rn
                FROM attempts
                WHERE user_id = ?
            )
            WHERE rn = 1
            """,
            (user_id,),
        ))
        labels.append("answered_and_wrong")
    elif need_answered:
        queries.append(("SELECT DISTINCT question_id FROM attempts WHERE user_id = ?", (user_id,)))
        labels.append("answered")

    if need_srs_due:
        now_iso = datetime.now(timezone.utc).isoformat()
        queries.append((
            "SELECT question_id FROM spaced_repetition WHERE user_id = ? AND next_review_date <= ?",
            (user_id, now_iso),
        ))
        labels.append("srs_due")

    if need_fav:
        queries.append(("SELECT question_id FROM favorites WHERE user_id = ?", (user_id,)))
        labels.append("fav")

    if not queries:
        return sets

    if hasattr(db, "batch"):
        results = db.batch(queries)
    else:
        results = [db.execute(sql, params) for sql, params in queries]

    for label, res in zip(labels, results):
        rows = res.fetchall()
        if label == "answered_and_wrong":
            answered_s = sets["answered"]
            wrong_s = sets["wrong"]
            for r in rows:
                qid = int(r["question_id"])
                answered_s.add(qid)
                if not r["is_correct"]:
                    wrong_s.add(qid)
        else:
            target = sets[label]
            for r in rows:
                target.add(int(r["question_id"]))

    return sets


def _matches_status_tokens(qid: int, status_tokens: tuple[str, ...], user_sets: dict[str, set[int]]) -> bool:
    for tok in status_tokens:
        if tok in ("unanswered", "new"):
            if qid not in user_sets["answered"]:
                return True
        elif tok == "answered":
            if qid in user_sets["answered"]:
                return True
        elif tok == "wrong":
            if qid in user_sets["wrong"]:
                return True
        elif tok == "srs_due":
            if qid in user_sets["srs_due"]:
                return True
        elif tok == "favorite":
            if qid in user_sets["fav"]:
                return True
    return False


def _matches_base_filters(row: tuple, parsed: dict, user_sets: dict[str, set[int]]) -> bool:
    qid, ic, _il, _yr, ar, _sub, top, is_annulled, has_image = row
    if parsed["id_filter"] is not None and qid != parsed["id_filter"]:
        return False
    if parsed["inst_set"] is not None and ic not in parsed["inst_set"]:
        return False
    if parsed["area_set"] is not None and ar not in parsed["area_set"]:
        return False
    if parsed["topic_set"] is not None and top not in parsed["topic_set"]:
        return False
    if parsed["has_images_only"] and not has_image:
        return False
    if parsed["exclude_annulled"] and is_annulled:
        return False
    if parsed["favorite_only"] and qid not in user_sets["fav"]:
        return False
    if parsed["status_tokens"] and not _matches_status_tokens(qid, parsed["status_tokens"], user_sets):
        return False
    return True


def _matches_year_filter(yr, parsed: dict) -> bool:
    if not parsed["has_year_filter"]:
        return True
    if yr is None:
        return False
    if isinstance(yr, int):
        return yr in parsed["year_ints"]
    return yr in parsed["year_strs"] or (isinstance(yr, str) and _YEAR_INT_RE.match(yr) and int(yr) in parsed["year_ints"])


def compute_meta_from_catalog(db, user_id, args, target_insts: set[str]) -> dict:
    """Calcula /api/meta a partir do catálogo leve em cache + índices de usuário."""
    catalog = _load_question_catalog(db)
    parsed = _parse_catalog_filters(args)
    status_tokens = parsed["status_tokens"]
    is_global_facet_query = not parsed["favorite_only"] and not status_tokens

    user_sets = _fetch_user_question_sets(
        db,
        user_id,
        need_answered=True,
        need_wrong=("wrong" in status_tokens),
        need_srs_due=("srs_due" in status_tokens),
        need_fav=parsed["favorite_only"] or ("favorite" in status_tokens),
    )
    answered_ids = user_sets["answered"]

    if is_global_facet_query and catalog_cache_enabled():
        global_key = (
            db_cache_scope(),
            tuple(sorted(parsed["inst_set"])) if parsed["inst_set"] else None,
            tuple(sorted(parsed["year_ints"])),
            tuple(sorted(parsed["year_strs"])),
            tuple(sorted(parsed["area_set"])) if parsed["area_set"] else None,
            tuple(sorted(parsed["subtema_set"])) if parsed["subtema_set"] else None,
            tuple(sorted(parsed["topic_set"])) if parsed["topic_set"] else None,
            parsed["id_filter"],
            parsed["has_images_only"],
        )
        cached_global = _meta_global_cache.get(global_key)
        if cached_global is not None:
            matching_qids, static_facets = cached_global
            return {
                **static_facets,
                "answered_questions": sum(1 for qid in matching_qids if qid in answered_ids),
                "target_institutions": sorted(target_insts),
            }
    else:
        global_key = None

    subtema_set = parsed["subtema_set"]
    raw_inst_counts: dict[str | None, list] = {}
    years_set: set = set()
    area_counts: dict[str, int] = {}
    subtema_counts: dict[str, int] = {}
    topic_counts: dict[str, int] = {}
    matching_qids: list[int] = []
    total = 0
    answered = 0

    for row in catalog:
        if not _matches_base_filters(row, parsed, user_sets):
            continue
        qid, ic, il, yr, ar, sub, top, _ann, _img = row
        year_match = _matches_year_filter(yr, parsed)
        subtema_match = subtema_set is None or sub in subtema_set

        if year_match and subtema_match:
            total += 1
            matching_qids.append(qid)
            if qid in answered_ids:
                answered += 1
            inst_entry = raw_inst_counts.get(ic)
            if inst_entry is None:
                raw_inst_counts[ic] = [il, 1]
            else:
                inst_entry[1] += 1
                if not inst_entry[0] and il:
                    inst_entry[0] = il
            if ar:
                area_counts[ar] = area_counts.get(ar, 0) + 1

        if subtema_match and yr is not None:
            years_set.add(yr)

        if year_match:
            if sub:
                subtema_counts[sub] = subtema_counts.get(sub, 0) + 1
            if top:
                topic_counts[top] = topic_counts.get(top, 0) + 1

    merged_institutions: dict[str, dict] = {}
    for raw_code, (raw_label, count) in raw_inst_counts.items():
        canon_code = get_canonical_institution(raw_code) or raw_code
        if not canon_code:
            continue
        existing = merged_institutions.get(canon_code)
        if existing is None:
            merged_institutions[canon_code] = {
                "institution_code": canon_code,
                "institution_label": raw_label or canon_code,
                "n": count,
            }
        else:
            existing["n"] += count
            if raw_code == canon_code and raw_label:
                existing["institution_label"] = raw_label

    deduped_institutions = sorted(
        merged_institutions.values(),
        key=lambda item: (-item["n"], item["institution_code"]),
    )

    static_facets = {
        "institutions": deduped_institutions,
        "years": sorted(years_set, reverse=True),
        "sources": [],
        "areas": [{"area": k, "n": v} for k, v in sorted(area_counts.items(), key=lambda x: (-x[1], x[0]))],
        "specialties": [],
        "subtemas": [{"subtema": k, "n": v} for k, v in sorted(subtema_counts.items(), key=lambda x: (-x[1], x[0]))[:300]],
        "topics": [{"topic": k, "n": v} for k, v in sorted(topic_counts.items(), key=lambda x: (-x[1], x[0]))[:500]],
        "total_questions": total,
    }
    if global_key is not None:
        _meta_global_cache.set(global_key, (tuple(matching_qids), static_facets))

    return {
        **static_facets,
        "answered_questions": answered,
        "target_institutions": sorted(target_insts),
    }


def count_questions_from_catalog(db, user_id, args) -> int:
    """Calcula /api/questions/count a partir do catálogo leve em cache."""
    catalog = _load_question_catalog(db)
    parsed = _parse_catalog_filters(args)
    status_tokens = parsed["status_tokens"]
    user_sets = _fetch_user_question_sets(
        db,
        user_id,
        need_answered=any(t in ("unanswered", "new", "answered") for t in status_tokens),
        need_wrong=("wrong" in status_tokens),
        need_srs_due=("srs_due" in status_tokens),
        need_fav=parsed["favorite_only"] or ("favorite" in status_tokens),
    )

    subtema_set = parsed["subtema_set"]
    total = 0
    for row in catalog:
        if not _matches_base_filters(row, parsed, user_sets):
            continue
        if not _matches_year_filter(row[3], parsed):
            continue
        if subtema_set is not None and row[5] not in subtema_set:
            continue
        total += 1
    return total

