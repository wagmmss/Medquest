"""Blueprint: metadados, listagem/fila de estudo, detalhe e favoritos."""
import json
import logging
import random

from flask import Blueprint, g, jsonify, request

logger = logging.getLogger(__name__)

from .cache import SimpleTTLCache
from .adaptive import rank_adaptive_candidates
from .remediation import generate_remediation_queue
from .db import db_transaction, get_db
from .edital_profiles import get_canonical_institution
from .filters import get_user_target_institutions, question_filter_clauses
from .services.questions_service import (
    _bounded_int,
    _sample_prioritized_ids,
    compute_meta_from_catalog,
    count_questions_from_catalog,
    get_question_batch_columns,
    invalidate_service_caches,
    supports_catalog_filters,
)
from .idempotency import complete_active_lease, idempotent
from .schemas import (
    FavoriteIn,
    QuestionBatchIn,
    ValidationError,
    validation_errors,
)


meta_cache = SimpleTTLCache(60)
count_cache = SimpleTTLCache(60, max_size=1000)

bp = Blueprint("questions", __name__)


def invalidate_user_caches(user_id):
    """Invalidate every derived per-user view after a successful mutation."""
    meta_cache.clear_user(user_id)
    count_cache.clear_user(user_id)
    from .filters import target_institutions_cache
    target_institutions_cache.clear_user(user_id)
    from .stats import overview_cache
    overview_cache.clear_user(user_id)
    from .adaptive import _profile_cache, clear_user_last_known_profile
    _profile_cache.clear_user(user_id)
    clear_user_last_known_profile(user_id)


def invalidate_global_question_caches():
    """Invalidate global question metadata and totals caches after curator edits."""
    meta_cache.clear()
    count_cache.clear()
    invalidate_service_caches()
    from .stats import _area_totals_cache, _institution_area_totals_cache, _q_totals_cache
    _q_totals_cache.clear()
    _area_totals_cache.clear()
    _institution_area_totals_cache.clear()
    from .adaptive import _question_topics_cache
    _question_topics_cache.clear()
    from .services.focus_radar import _focus_radar_catalog_cache
    _focus_radar_catalog_cache.clear()



@bp.route("/meta")
def meta():
    # Preserva valores repetidos (ex.: institution=A&institution=B) e faz
    # consultas equivalentes compartilharem a mesma entrada de cache.
    normalized_args = tuple(sorted(
        (key, tuple(sorted(values)))
        for key, values in request.args.lists()
    ))
    cache_key = (g.user_id, normalized_args)
    cached = meta_cache.get(cache_key)
    if cached:
        return jsonify(cached)

    db = get_db()
    if supports_catalog_filters(request.args):
        target_insts = get_user_target_institutions(db, g.user_id)
        result = compute_meta_from_catalog(db, g.user_id, request.args, target_insts)
        meta_cache.set(cache_key, result)
        return jsonify(result)

    clauses, params = question_filter_clauses(request.args)
    
    # We must replace q. with empty or alias questions as q
    # Because question_filter_clauses assumes "q.institution_code" etc
    where = " AND ".join(clauses)

    from werkzeug.datastructures import MultiDict
    args_no_subtema = MultiDict((k, v) for k, v in request.args.items(multi=True) if k != 'subtema')
    clauses_no_subtema, params_no_subtema = question_filter_clauses(args_no_subtema)
    where_no_subtema = " AND ".join(clauses_no_subtema)

    args_no_year = MultiDict((k, v) for k, v in request.args.items(multi=True) if k != 'year')
    clauses_no_year, params_no_year = question_filter_clauses(args_no_year)
    where_no_year = " AND ".join(clauses_no_year)

    answered_params = list(params)
    answered_params.append(g.user_id)

    queries = [
        (f"SELECT q.institution_code, q.institution_label, COUNT(*) n FROM questions q WHERE {where} GROUP BY q.institution_code ORDER BY n DESC", params),
        (f"SELECT DISTINCT q.year FROM questions q WHERE q.year IS NOT NULL AND {where_no_year} ORDER BY q.year DESC", params_no_year),
        (f"SELECT q.area, COUNT(*) n FROM questions q WHERE q.area IS NOT NULL AND q.area != '' AND {where} GROUP BY q.area ORDER BY n DESC", params),
        (f"SELECT q.subtema, COUNT(*) n FROM questions q WHERE q.subtema IS NOT NULL AND q.subtema != '' AND {where_no_subtema} GROUP BY q.subtema ORDER BY n DESC LIMIT 300", params_no_subtema),
        (f"SELECT q.topic, COUNT(*) n FROM questions q WHERE q.topic IS NOT NULL AND q.topic != '' AND {where_no_subtema} GROUP BY q.topic ORDER BY n DESC LIMIT 500", params_no_subtema),
        (f"SELECT COUNT(*) n FROM questions q WHERE {where}", params),
        (f"SELECT COUNT(DISTINCT q.id) n FROM questions q WHERE {where} AND q.id IN (SELECT question_id FROM attempts WHERE user_id = ?)", answered_params)
    ]

    if hasattr(db, "batch"):
        results = db.batch(queries)
        institutions = results[0].fetchall()
        years = results[1].fetchall()
        areas = results[2].fetchall()
        subtemas = results[3].fetchall()
        topics = results[4].fetchall()
        total = results[5].fetchone()["n"]
        answered = results[6].fetchone()["n"]
    else:
        institutions = db.execute(queries[0][0], queries[0][1]).fetchall()
        years = db.execute(queries[1][0], queries[1][1]).fetchall()
        areas = db.execute(queries[2][0], queries[2][1]).fetchall()
        subtemas = db.execute(queries[3][0], queries[3][1]).fetchall()
        topics = db.execute(queries[4][0], queries[4][1]).fetchall()
        total = db.execute(queries[5][0], queries[5][1]).fetchone()["n"]
        answered = db.execute(queries[6][0], queries[6][1]).fetchone()["n"]
    
    merged_institutions: dict[str, dict] = {}
    for row in institutions:
        raw_code = row["institution_code"]
        canon_code = get_canonical_institution(raw_code) or raw_code
        if not canon_code:
            continue
        existing = merged_institutions.get(canon_code)
        if existing is None:
            merged_institutions[canon_code] = {
                "institution_code": canon_code,
                "institution_label": row["institution_label"] or canon_code,
                "n": int(row["n"] or 0),
            }
        else:
            existing["n"] += int(row["n"] or 0)
            if raw_code == canon_code and row["institution_label"]:
                existing["institution_label"] = row["institution_label"]

    deduped_institutions = sorted(
        merged_institutions.values(),
        key=lambda item: (-item["n"], item["institution_code"]),
    )

    result = {
        "institutions": deduped_institutions,
        "years": [r["year"] for r in years],
        "sources": [],
        "areas": [dict(r) for r in areas],
        "specialties": [],
        "subtemas": [dict(r) for r in subtemas],
        "topics": [dict(r) for r in topics],
        "total_questions": total,
        "answered_questions": answered,
        "target_institutions": sorted(list(get_user_target_institutions(db, g.user_id))),
    }
    
    meta_cache.set(cache_key, result)
    return jsonify(result)


@bp.route("/subtemas")
def subtemas():
    db = get_db()
    area = request.args.get("area")
    q = request.args.get("q", "").strip()
    clauses = ["subtema IS NOT NULL", "subtema != ''"]
    params = []
    if area:
        clauses.append("area = ?")
        params.append(area)
    if q:
        clauses.append("subtema LIKE ?")
        params.append(f"%{q}%")
    where = " AND ".join(clauses)
    rows = db.execute(
        f"SELECT subtema, COUNT(*) n FROM questions WHERE {where} GROUP BY subtema ORDER BY n DESC LIMIT 50",
        params,
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@bp.route("/questions")
def questions():
    db = get_db()
    clauses, params = question_filter_clauses(request.args)
    where = " AND ".join(clauses)
    limit = _bounded_int(request.args.get("limit"), default=500, minimum=1, maximum=2000)
    target_insts = get_user_target_institutions(db, g.user_id)
    has_explicit_inst = bool(request.args.getlist("institution"))

    if request.args.get("mode") == "adaptive":
        adaptive_focus = request.args.get("adaptive_focus", "balanced")
        return jsonify(rank_adaptive_candidates(
            db, g.user_id, where, params, limit, adaptive_focus=adaptive_focus, target_institutions=target_insts
        ))
    if request.args.get("mode") == "remediation":
        subtema = request.args.get("subtema")
        area = request.args.get("area")
        return jsonify(generate_remediation_queue(
            db, g.user_id, subtema=subtema, area=area, limit=limit, target_institutions=target_insts
        ))
    ids = _sample_prioritized_ids(db, where, params, limit, target_insts, has_explicit_inst_filter=has_explicit_inst)
    if not ids:
        return jsonify([])
    placeholders = ",".join("?" * len(ids))
    rows = db.execute(
        f"""SELECT q.id, q.source_file, q.source_number, q.year, q.institution_code,
                   q.institution_label, q.topic, q.area, q.subtema, q.editorial_status
            FROM questions q WHERE q.id IN ({placeholders})""",
        ids,
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["is_autoral"] = bool(d.get("editorial_status") == "autoral" or (d.get("source_file") and "AUTORAL" in str(d.get("source_file")).upper()))
        inst = d.get("institution_code")
        d["is_target_institution"] = bool(target_insts and (inst in target_insts or (inst and inst.upper() in target_insts)))
        out.append(d)
    random.shuffle(out)
    return jsonify(out)


@bp.route("/questions/remediation")
def questions_remediation():
    db = get_db()
    limit = _bounded_int(request.args.get("limit"), default=10, minimum=1, maximum=50)
    subtema = request.args.get("subtema")
    area = request.args.get("area")
    target_insts = get_user_target_institutions(db, g.user_id)
    return jsonify(generate_remediation_queue(db, g.user_id, subtema=subtema, area=area, limit=limit, target_institutions=target_insts))


@bp.route("/questions/count")
@bp.route("/questions/counts")
def questions_count():
    normalized_args = tuple(sorted(
        (key, tuple(sorted(values)))
        for key, values in request.args.lists()
    ))
    user_dependent_keys = ("status", "unanswered_only", "favorite")
    is_user_scoped = any(k in request.args for k in user_dependent_keys)
    cache_key = (getattr(g, "user_id", None) if is_user_scoped else None, normalized_args)

    cached = count_cache.get(cache_key)
    if cached is not None:
        return jsonify({"count": cached})

    db = get_db()
    if supports_catalog_filters(request.args):
        n = count_questions_from_catalog(db, getattr(g, "user_id", None), request.args)
    else:
        clauses, params = question_filter_clauses(request.args)
        where = " AND ".join(clauses)
        row = db.execute(f"SELECT COUNT(*) AS n FROM questions q WHERE {where}", params).fetchone()
        n = row["n"] if row else 0

    count_cache.set(cache_key, n)
    return jsonify({"count": n})


@bp.route("/questions/<int:qid>")
def question_detail(qid):
    db = get_db()
    queries = [
        ("SELECT * FROM questions WHERE id = ?", (qid,)),
        ("SELECT letter, text FROM alternatives WHERE question_id = ? ORDER BY letter", (qid,)),
        ("SELECT file_path FROM question_images WHERE question_id = ? AND file_path NOT LIKE '%question_explanation_images%' ORDER BY order_index", (qid,)),
        ("SELECT selected_letter, is_correct FROM attempts WHERE question_id = ? AND user_id = ? ORDER BY id DESC LIMIT 1", (qid, g.user_id)),
        ("SELECT COUNT(*) as n FROM attempts WHERE question_id = ? AND is_correct = 0 AND user_id = ?", (qid, g.user_id)),
        ("SELECT 1 FROM favorites WHERE question_id = ? AND user_id = ?", (qid, g.user_id))
    ]
    
    res = None
    if hasattr(db, "batch"):
        try:
            res = db.batch(queries)
        except Exception:
            res = None

    if res is not None:
        q = res[0].fetchone()
        alts = res[1].fetchall()
        imgs = res[2].fetchall()
        last_attempt = res[3].fetchone()
        times_wrong = res[4].fetchone()["n"]
        is_favorite = res[5].fetchone()
    else:
        q = db.execute(queries[0][0], queries[0][1]).fetchone()
        alts = db.execute(queries[1][0], queries[1][1]).fetchall()
        imgs = db.execute(queries[2][0], queries[2][1]).fetchall()
        last_attempt = db.execute(queries[3][0], queries[3][1]).fetchone()
        times_wrong = db.execute(queries[4][0], queries[4][1]).fetchone()["n"]
        is_favorite = db.execute(queries[5][0], queries[5][1]).fetchone()
        
    if not q:
        return jsonify({"error": "not found", "code": "QUESTION_NOT_FOUND"}), 404
    q = dict(q)
        
    cc = None
    if q.get("clinical_case_id"):
        cc_row = db.execute("SELECT stem, images FROM clinical_cases WHERE id = ?", (q["clinical_case_id"],)).fetchone()
        if cc_row:
            cc = {
                "stem": cc_row["stem"],
                "images": json.loads(cc_row["images"]) if cc_row["images"] else []
            }

    target_insts = get_user_target_institutions(db, g.user_id)
    inst = q.get("institution_code")
    is_target_inst = bool(target_insts and (inst in target_insts or (inst and inst.upper() in target_insts)))

    return jsonify({
        "id": q["id"], "source_file": q["source_file"], "source_number": q["source_number"],
        "year": q["year"], "institution_code": q["institution_code"],
        "institution_label": q["institution_label"], "topic": q["topic"],
        "area": q["area"], "subtema": q["subtema"], "stem": q["stem"],
        "is_autoral": bool(q.get("editorial_status") == "autoral" or (q.get("source_file") and "AUTORAL" in str(q.get("source_file")).upper())),
        "is_discursive": bool(len(alts) <= 1),
        "is_verified": bool(q.get("is_verified", 0)),
        "is_target_institution": is_target_inst,
        "last_updated_at": q.get("last_updated_at"),
        "technical_note": q.get("technical_note"),
        "clinical_case": cc,
        "usp_macro": q.get("usp_macro"),
        "usp_micro": q.get("usp_micro"),
        "alternatives": [dict(a) for a in alts],
        "images": [i["file_path"] for i in imgs],
        "already_answered": dict(last_attempt) if last_attempt else None,
        "is_favorite": bool(is_favorite),
        "times_wrong": times_wrong,
    })


@bp.route("/questions/<int:qid>/favorite", methods=["POST"])
@idempotent()
def toggle_favorite(qid):
    db = get_db()
    try:
        data = FavoriteIn.model_validate(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify({"error": "invalid input", "details": validation_errors(e)}), 400
    target_fav = data.is_favorite

    q = db.execute("SELECT id FROM questions WHERE id = ?", (qid,)).fetchone()
    if not q:
        return jsonify({"error": "Questão não encontrada"}), 404

    with db_transaction(db, immediate=True):
        if target_fav is not None:
            if target_fav:
                db.execute("INSERT OR IGNORE INTO favorites (question_id, user_id) VALUES (?, ?)", (qid, g.user_id))
                is_fav = True
            else:
                db.execute("DELETE FROM favorites WHERE question_id = ? AND user_id = ?", (qid, g.user_id))
                is_fav = False
        else:
            fav = db.execute("SELECT 1 FROM favorites WHERE question_id = ? AND user_id = ?", (qid, g.user_id)).fetchone()
            if fav:
                db.execute("DELETE FROM favorites WHERE question_id = ? AND user_id = ?", (qid, g.user_id))
                is_fav = False
            else:
                db.execute("INSERT OR IGNORE INTO favorites (question_id, user_id) VALUES (?, ?)", (qid, g.user_id))
                is_fav = True

        resp_data = {"success": True, "is_favorite": is_fav}
        complete_active_lease(200, resp_data)

    invalidate_user_caches(g.user_id)
    return jsonify(resp_data)


def _fetch_batch_data(db, ids, user_id, select_cols="*"):
    CHUNK = 500
    q_map = {}
    alt_map = {}
    img_map = {}
    attempt_map = {}
    wrong_map = {}
    fav_set = set()

    if not ids:
        return q_map, alt_map, img_map, attempt_map, wrong_map, fav_set

    queries = []
    for i in range(0, len(ids), CHUNK):
        chunk = ids[i:i + CHUNK]
        ph = ",".join("?" * len(chunk))
        chunk_user = list(chunk) + [user_id]

        queries.extend([
            (f"SELECT {select_cols} FROM questions WHERE id IN ({ph})", chunk),
            (f"SELECT question_id, letter, text FROM alternatives WHERE question_id IN ({ph}) ORDER BY letter", chunk),
            (f"SELECT question_id, file_path FROM question_images WHERE question_id IN ({ph}) AND file_path NOT LIKE '%question_explanation_images%' ORDER BY order_index", chunk),
            (f"""SELECT a.question_id, a.selected_letter, a.is_correct
                 FROM questions q JOIN attempts a ON a.id = (
                     SELECT latest.id FROM attempts latest
                     WHERE latest.user_id = ? AND latest.question_id = q.id
                     ORDER BY latest.id DESC LIMIT 1
                 ) WHERE q.id IN ({ph})""", [user_id] + list(chunk)),
            (f"SELECT question_id, COUNT(*) as n FROM attempts WHERE question_id IN ({ph}) AND is_correct = 0 AND user_id = ? GROUP BY question_id", chunk_user),
            (f"SELECT question_id FROM favorites WHERE question_id IN ({ph}) AND user_id = ?", chunk_user),
        ])

    if hasattr(db, "batch"):
        results = db.batch(queries)
    else:
        results = [db.execute(sql, params) for sql, params in queries]

    for c in range(0, len(results), 6):
        rows_q = results[c].fetchall()
        rows_alt = results[c + 1].fetchall()
        rows_img = results[c + 2].fetchall()
        rows_att = results[c + 3].fetchall()
        rows_wrong = results[c + 4].fetchall()
        rows_fav = results[c + 5].fetchall()

        for r in rows_q:
            q_map[r["id"]] = dict(r)

        for r in rows_alt:
            alt_map.setdefault(r["question_id"], []).append({"letter": r["letter"], "text": r["text"]})

        for r in rows_img:
            img_map.setdefault(r["question_id"], []).append(r["file_path"])

        for r in rows_att:
            if r["question_id"] not in attempt_map:
                attempt_map[r["question_id"]] = {"selected_letter": r["selected_letter"], "is_correct": bool(r["is_correct"])}

        for r in rows_wrong:
            wrong_map[r["question_id"]] = r["n"]

        for r in rows_fav:
            fav_set.add(r["question_id"])

    return q_map, alt_map, img_map, attempt_map, wrong_map, fav_set

def _fetch_clinical_cases(db, q_map):
    cc_map = {}
    cc_ids = list({q["clinical_case_id"] for q in q_map.values() if q.get("clinical_case_id")})
    if cc_ids:
        ph_cc = ",".join("?" * len(cc_ids))
        for r in db.execute(f"SELECT id, stem, images FROM clinical_cases WHERE id IN ({ph_cc})", cc_ids).fetchall():
            cc_map[r["id"]] = {
                "stem": r["stem"],
                "images": json.loads(r["images"]) if r["images"] else []
            }
    return cc_map

def _filter_alternatives(alts, correct_letter):
    incorrects = [a for a in alts if a["letter"] != correct_letter]
    if incorrects:
        # Escolhe um distrator para remover para que sobrem apenas 4 alternativas
        # Se len for 5, remove 1. Se len for N, remove N-4
        remove_count = len(alts) - 4
        to_remove = random.sample(incorrects, remove_count)
        to_remove_letters = {a["letter"] for a in to_remove}
        return [a for a in alts if a["letter"] not in to_remove_letters]
    return alts

def _format_question_dict(q, alts, imgs, attempt, wrong_count, is_favorite, cc, is_target_inst=False):
    return {
        "id": q["id"],
        "source_file": q["source_file"],
        "source_number": q["source_number"],
        "year": q["year"],
        "institution_code": q["institution_code"],
        "institution_label": q["institution_label"],
        "topic": q["topic"],
        "area": q["area"],
        "subtema": q["subtema"],
        "stem": q["stem"],
        "is_autoral": bool(q.get("editorial_status") == "autoral" or (q.get("source_file") and "AUTORAL" in str(q.get("source_file")).upper())),
        "is_discursive": bool(len(alts) <= 1),
        "is_verified": bool(q.get("is_verified", 0)),
        "is_target_institution": bool(is_target_inst),
        "last_updated_at": q.get("last_updated_at"),
        "technical_note": q.get("technical_note"),
        "clinical_case": cc,
        "usp_macro": q.get("usp_macro"),
        "usp_micro": q.get("usp_micro"),
        "alternatives": alts,
        "images": imgs,
        "already_answered": attempt,
        "is_favorite": is_favorite,
        "times_wrong": wrong_count,
    }

@bp.route("/questions/batch", methods=["POST"])
def question_batch_detail():
    """Retorna detalhes completos de múltiplas questões em uma única requisição.

    Aceita {"ids": [1, 2, ...]} com no máximo 200 IDs.
    Substitui até 120 chamadas individuais GET /questions/:id no simulado.
    """
    try:
        data = QuestionBatchIn.model_validate(request.get_json(force=True) or {})
    except ValidationError as e:
        return jsonify({"error": "invalid input", "details": validation_errors(e)}), 400

    ids = data.ids
    force_4_options = data.force_4_options
    db = get_db()
    target_insts = get_user_target_institutions(db, g.user_id)

    q_map, alt_map, img_map, attempt_map, wrong_map, fav_set = _fetch_batch_data(
        db, ids, g.user_id, select_cols=get_question_batch_columns(db)
    )
    cc_map = _fetch_clinical_cases(db, q_map)

    out = []
    for qid in ids:
        q = q_map.get(qid)
        if not q:
            continue
            
        alts = alt_map.get(qid, [])
        if force_4_options and len(alts) > 4:
            alts = _filter_alternatives(alts, q.get("correct_letter"))

        inst = q.get("institution_code")
        is_target = bool(target_insts and (inst in target_insts or (inst and inst.upper() in target_insts)))

        out.append(_format_question_dict(
            q,
            alts,
            img_map.get(qid, []),
            attempt_map.get(qid),
            wrong_map.get(qid, 0),
            qid in fav_set,
            cc_map.get(q.get("clinical_case_id")),
            is_target_inst=is_target,
        ))

    return jsonify({"questions": out})


# As rotas de IA (ask_ai, ai/health, prescribe_study, synthesize_explanation) foram
# desacopladas para api/ai_routes.py.
# As rotas de Curadoria e Taxonomia (taxonomy, classification, delete_question) foram
# desacopladas para api/curation.py.


@bp.route("/images/<path:filename>")
def serve_image(filename):
    import os
    from flask import send_from_directory
    from werkzeug.exceptions import NotFound
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static_dir = os.path.join(backend_dir, "static")

    try:
        return send_from_directory(static_dir, filename)
    except NotFound:
        return send_from_directory(os.path.join(static_dir, "images"), filename)
