"""Consultas e persistência de configuração, blocos de internato e progresso do Planner."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from ..filters import get_user_target_institutions
from ..internato_config import RODIZIOS_TURMA_J

def _resolve_schedule_mode(organization: str, intensive: bool) -> str:
    org = "internato" if organization == "internato" else "geral"
    return f"{org}_{'intensive' if intensive else 'standard'}"


def _parse_mode_parts(mode: str) -> tuple[str, bool]:
    if mode in ("internato_standard", "internato_intensive"):
        return "internato", mode.endswith("_intensive")
    return "geral", mode.endswith("intensive")


def _get_completed_subtemas(db, user_id: str) -> set[str]:
    rows = db.execute(
        "SELECT DISTINCT subtema FROM planner_topic_progress WHERE user_id = ? AND completed = 1",
        (user_id,),
    ).fetchall()
    return {r["subtema"] for r in rows}


_UNSET = object()


_METADATA_FIELDS = (
    "id",
    "ancora70",
    "trilha30",
    "ancora_areas",
    "procedimentos_alvo",
    "micro_habito",
)


def _date_overlap_days(a_start: str, a_end: str, b_start: str, b_end: str) -> int:
    try:
        s1 = datetime.strptime(a_start[:10], "%Y-%m-%d").date()
        e1 = datetime.strptime(a_end[:10], "%Y-%m-%d").date()
        s2 = datetime.strptime(b_start[:10], "%Y-%m-%d").date()
        e2 = datetime.strptime(b_end[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return 0
    lo = max(s1, s2)
    hi = min(e1, e2)
    return max(0, (hi - lo).days + 1)


def merge_with_default_metadata(user_blocks: list[dict]) -> list[dict]:
    """Enriquece blocos salvos pelo usuário copiando apenas campos ausentes de RODIZIOS_TURMA_J."""
    by_id = {b["id"]: b for b in RODIZIOS_TURMA_J if b.get("id")}
    by_dates = {(b["start"], b["end"]): b for b in RODIZIOS_TURMA_J}

    merged: list[dict] = []
    for raw in user_blocks:
        blk = dict(raw)
        default_match = None
        if blk.get("id") and blk["id"] in by_id:
            default_match = by_id[blk["id"]]
        elif (blk.get("start"), blk.get("end")) in by_dates:
            default_match = by_dates[(blk.get("start"), blk.get("end"))]
        else:
            best_overlap = 0
            for candidate in RODIZIOS_TURMA_J:
                if candidate.get("area") != blk.get("area"):
                    continue
                overlap = _date_overlap_days(
                    str(blk.get("start") or ""),
                    str(blk.get("end") or ""),
                    candidate["start"],
                    candidate["end"],
                )
                if overlap > best_overlap:
                    best_overlap = overlap
                    default_match = candidate

        if default_match:
            for field in _METADATA_FIELDS:
                if blk.get(field) is None and default_match.get(field) is not None:
                    val = default_match[field]
                    blk[field] = list(val) if isinstance(val, list) else val
        merged.append(blk)
    return merged


def _get_user_internato_blocks(db, user_id: str, config_row=_UNSET) -> list[dict]:
    if config_row is _UNSET:
        row = db.execute("SELECT internato_blocks FROM planner_config WHERE user_id = ?", (user_id,)).fetchone()
    else:
        row = config_row
    if row and row["internato_blocks"]:
        try:
            parsed = json.loads(row["internato_blocks"])
            if isinstance(parsed, list) and parsed:
                return merge_with_default_metadata(parsed)
        except (ValueError, TypeError):
            pass
    return [dict(b) for b in RODIZIOS_TURMA_J]


def get_planner_config_data(db, user_id: str) -> dict | None:
    row = db.execute("SELECT * FROM planner_config WHERE user_id = ?", (user_id,)).fetchone()
    if not row:
        return None
    row_keys = row.keys() if hasattr(row, 'keys') else []
    inst_str = row["target_institution"] if "target_institution" in row_keys else None
    inst_list = [i.strip() for i in inst_str.split(",") if i.strip()] if inst_str else []
    primary_inst = None
    if inst_list and inst_list[0] not in ("Todas as Bancas", "TODAS"):
        primary_inst = inst_list[0]

    org_mode = row["organization_mode"] if "organization_mode" in row_keys and row["organization_mode"] else "geral"
    internato_blocks = _get_user_internato_blocks(db, user_id, config_row=row)

    return {
        "exam_date": row["exam_date"],
        "start_date": row["start_date"],
        "days_per_week": row["days_per_week"],
        "hours_per_day": row["hours_per_day"] if "hours_per_day" in row_keys else row["questions_per_day"],
        "target_score": row["target_score"] if "target_score" in row_keys else None,
        "target_institution": inst_str,
        "target_institutions": inst_list,
        "primary_institution": primary_inst,
        "target_specialty": row["target_specialty"] if "target_specialty" in row_keys else None,
        "organization_mode": org_mode,
        "internato_blocks": internato_blocks,
    }


def get_planner_progress_data(db, user_id: str) -> dict:
    rows = db.execute("SELECT * FROM planner_progress WHERE user_id = ?", (user_id,)).fetchall()
    return {str(r["week"]): {
        "studied": bool(r["studied"]), "studied_at": r["studied_at"],
        "rev24h": bool(r["rev24h"]), "rev7d": bool(r["rev7d"]), "rev30d": bool(r["rev30d"]),
    } for r in rows}


def get_planner_topic_progress_data(db, user_id: str) -> dict:
    rows = db.execute("SELECT week, subtema, completed FROM planner_topic_progress WHERE user_id = ?", (user_id,)).fetchall()
    res = {}
    for r in rows:
        val = bool(r["completed"])
        res[f"{r['week']}:{r['subtema']}"] = val
        if val:
            res[r["subtema"]] = True
    return res



def _get_planner_config(db, user_id, config_row=_UNSET):
    row = (
        db.execute("SELECT * FROM planner_config WHERE user_id = ?", (user_id,)).fetchone()
        if config_row is _UNSET
        else config_row
    )
    
    if not row or not row["exam_date"]:
        start_date = datetime.now(timezone.utc).isoformat()
        exam_date = (datetime.now(timezone.utc) + timedelta(days=120)).isoformat()
        hours_per_week = 24
        days = 6
    else:
        start_date = row["start_date"] or datetime.now(timezone.utc).isoformat()
        exam_date = row["exam_date"]
        days = row["days_per_week"] or 6
        row_keys = row.keys() if hasattr(row, "keys") else []
        hours = (row["hours_per_day"] if "hours_per_day" in row_keys else row["questions_per_day"]) or 4
        hours_per_week = min(168, days * hours)

    return start_date, exam_date, days, hours_per_week


def _fetch_plan_data(db, user_id):
    target_insts = get_user_target_institutions(db, user_id)
    use_bank_incidence = bool(target_insts)

    if target_insts:
        sorted_insts = sorted(target_insts)
        placeholders = ",".join("?" * len(sorted_insts))
        q_query = f"""
            SELECT area, subtema, GROUP_CONCAT(DISTINCT topic) as topics,
                   COUNT(id) as q_count,
                   SUM(CASE WHEN institution_code IN ({placeholders}) OR UPPER(institution_code) IN ({placeholders}) THEN 1 ELSE 0 END) as target_q_count
            FROM questions
            WHERE area IS NOT NULL AND subtema IS NOT NULL AND missing_alts = 0
            GROUP BY area, subtema
        """
        q_params = tuple(sorted_insts) + tuple(sorted_insts)
    else:
        q_query = """
            SELECT area, subtema, GROUP_CONCAT(DISTINCT topic) as topics,
                   COUNT(id) as q_count,
                   0 as target_q_count
            FROM questions
            WHERE area IS NOT NULL AND subtema IS NOT NULL AND missing_alts = 0
            GROUP BY area, subtema
        """
        q_params = ()

    a_query = """
        SELECT q.subtema, COUNT(DISTINCT a.question_id) as ans_count, SUM(a.is_correct) as correct_count, COUNT(a.id) as attempts
        FROM attempts a
        JOIN questions q ON q.id = a.question_id
        WHERE a.user_id = ? AND q.subtema IS NOT NULL
        GROUP BY q.subtema
    """
    if hasattr(db, "batch"):
        res = db.batch([
            (q_query, q_params),
            (a_query, (user_id,))
        ])
        rows = [dict(r) for r in res[0].fetchall()]
        answered = [dict(r) for r in res[1].fetchall()]
    else:
        rows = [dict(r) for r in db.execute(q_query, q_params).fetchall()]
        answered = [dict(r) for r in db.execute(a_query, (user_id,)).fetchall()]

    answered_map = {r["subtema"]: r for r in answered}
    return rows, answered_map, use_bank_incidence


