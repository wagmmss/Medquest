"""Motor de rotina do 6º Ano: calendário de plantões, modos do dia, Marcha, 70/30 e meta única."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from ..internato_config import (
    DAY_MODE_BASE_GOALS,
    DAY_MODE_LABEL_PRIORITY,
    DAY_MODE_META,
    DEFAULT_WEEK_PATTERN,
    FERIAS_WEEKS,
    MARCHA_FACTORS,
    SHIFT_WEIGHT_FOR_MARCHA,
)
from ..timezones import DEFAULT_TZ, local_day_bounds_utc
from .planner_store import _get_user_internato_blocks
from .taxonomy import get_normalized_area

WEEKDAY_KEYS = ("seg", "ter", "qua", "qui", "sex", "sab", "dom")  # date.weekday(): 0=seg
VALID_PATTERN_MODES = frozenset({"integral", "meio_periodo", "folga"})
SHIFT_KIND_TO_DAY_MODE = {
    "plantao_12h_dia": "plantao_12h_dia",
    "plantao_noturno": "entrada_noturno",
    "plantao_24h": "plantao_24h",
}
DEFAULT_DAILY_GOAL_QUESTIONS = 30


def local_today(now_utc: datetime | None = None) -> date:
    """Retorna a data local vigente em America/Sao_Paulo."""
    if now_utc is None:
        return datetime.now(DEFAULT_TZ).date()
    ref = now_utc if now_utc.tzinfo is not None else now_utc.replace(tzinfo=UTC)
    return ref.astimezone(DEFAULT_TZ).date()


def week_iso_of(d: date) -> str:
    """Segunda-feira (YYYY-MM-DD) da semana que contém `d` (compatível com weekIsoOf do Novo-PEP)."""
    return (d - timedelta(days=d.weekday())).isoformat()


def ritual_cycle_key(d: date) -> str:
    """Chave do ciclo do Ritual de Domingo: sábado anterior ou o próprio sábado (YYYY-MM-DD)."""
    back = (d.weekday() + 2) % 7  # seg=0 -> 2, ..., sab=5 -> 0, dom=6 -> 1
    return (d - timedelta(days=back)).isoformat()


def round5_half_up(x: float) -> int:
    """Arredonda para o múltiplo de 5 mais próximo com half-up (compatível com Math.round JS)."""
    return int(math.floor(x / 5.0 + 0.5)) * 5


@dataclass(frozen=True)
class RoutineContext:
    blocks: list[dict[str, Any]]
    shifts: dict[str, list[str]]     # date_iso -> [kind]
    overrides: dict[str, str]        # date_iso -> mode
    marchas: dict[str, str]          # week_iso -> marcha_id confirmada


@dataclass(frozen=True)
class DayStatus:
    date_iso: str
    mode: str
    source: str                      # "override" | "shift" | "pos_plantao" | "pattern"
    shifts: tuple[str, ...]
    is_pos_plantao: bool
    goal_questions: int
    reviews_optional: bool
    rodizio_id: str | None
    marcha_id: str
    marcha_source: str               # "confirmada" | "sugerida"
    guidance: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "date_iso": self.date_iso,
            "mode": self.mode,
            "source": self.source,
            "shifts": list(self.shifts),
            "is_pos_plantao": self.is_pos_plantao,
            "goal_questions": self.goal_questions,
            "reviews_optional": self.reviews_optional,
            "rodizio_id": self.rodizio_id,
            "marcha_id": self.marcha_id,
            "marcha_source": self.marcha_source,
            "guidance": self.guidance,
        }


def block_for_date(d: date, blocks: list[dict[str, Any]]) -> dict[str, Any] | None:
    d_iso = d.isoformat()
    for blk in blocks:
        start = str(blk.get("start") or "")
        end = str(blk.get("end") or "")
        if start and end and start <= d_iso <= end:
            return blk
    return None


def pattern_mode(d: date, block: dict[str, Any] | None) -> str:
    day_key = WEEKDAY_KEYS[d.weekday()]
    raw_pattern = block.get("week_pattern") if isinstance(block, dict) else None
    if isinstance(raw_pattern, dict):
        candidate = raw_pattern.get(day_key)
        if candidate in VALID_PATTERN_MODES:
            return candidate
    return DEFAULT_WEEK_PATTERN[day_key]


def week_shift_weight(week_iso: str, shifts: dict[str, list[str]]) -> int:
    start = date.fromisoformat(week_iso)
    weight = 0
    for offset in range(7):
        day_iso = (start + timedelta(days=offset)).isoformat()
        for kind in shifts.get(day_iso, ()):
            weight += SHIFT_WEIGHT_FOR_MARCHA.get(kind, 0)
    return weight


def suggested_marcha(week_iso: str, shifts: dict[str, list[str]]) -> str:
    weight = week_shift_weight(week_iso, shifts)
    if weight <= 1:
        return "3_normal"
    if weight == 2:
        return "2_pesada"
    return "1_sobrevivencia"


def effective_marcha(week_iso: str, ctx: RoutineContext) -> tuple[str, str]:
    confirmed = ctx.marchas.get(week_iso)
    if confirmed and confirmed in MARCHA_FACTORS:
        return confirmed, "confirmada"
    return suggested_marcha(week_iso, ctx.shifts), "sugerida"


def resolve_day(d: date, ctx: RoutineContext) -> DayStatus:
    """Resolve o modo, a origem e a meta de questões para a data `d` (regra T8)."""
    d_iso = d.isoformat()
    prev_iso = (d - timedelta(days=1)).isoformat()
    block = block_for_date(d, ctx.blocks)
    w_iso = week_iso_of(d)
    marcha_id, marcha_source = effective_marcha(w_iso, ctx)

    today_shifts = tuple(ctx.shifts.get(d_iso, ()))
    prev_shifts = ctx.shifts.get(prev_iso, ())
    is_pos_from_prev = any(k in ("plantao_noturno", "plantao_24h") for k in prev_shifts)

    if d_iso in ctx.overrides:
        mode = ctx.overrides[d_iso]
        source = "override"
    else:
        candidates: list[tuple[str, str]] = [(pattern_mode(d, block), "pattern")]
        for kind in today_shifts:
            mapped = SHIFT_KIND_TO_DAY_MODE.get(kind)
            if mapped:
                candidates.append((mapped, "shift"))
        if is_pos_from_prev:
            candidates.append(("pos_plantao", "pos_plantao"))

        mode, source = min(
            candidates,
            key=lambda c: (DAY_MODE_BASE_GOALS[c[0]], DAY_MODE_LABEL_PRIORITY.index(c[0])),
        )

    base = DAY_MODE_BASE_GOALS[mode]
    goal = 0 if base == 0 else max(5, round5_half_up(base * MARCHA_FACTORS[marcha_id]))
    guidance = DAY_MODE_META[mode]["guidance"]

    return DayStatus(
        date_iso=d_iso,
        mode=mode,
        source=source,
        shifts=today_shifts,
        is_pos_plantao=(mode == "pos_plantao"),
        goal_questions=goal,
        reviews_optional=(goal == 0),
        rodizio_id=block.get("id") if isinstance(block, dict) else None,
        marcha_id=marcha_id,
        marcha_source=marcha_source,
        guidance=guidance,
    )


def resolve_ferias_week_id(d: date) -> str | None:
    d_iso = d.isoformat()
    for sem in FERIAS_WEEKS:
        if sem["start"] <= d_iso <= sem["end"]:
            return sem["id"]
    return None


def summarize_week(week_iso: str, ctx: RoutineContext) -> dict[str, Any]:
    start = date.fromisoformat(week_iso)
    days = [resolve_day(start + timedelta(days=offset), ctx) for offset in range(7)]
    marcha_id, marcha_source = effective_marcha(week_iso, ctx)
    sugg = suggested_marcha(week_iso, ctx.shifts)
    weight = week_shift_weight(week_iso, ctx.shifts)
    return {
        "week_iso": week_iso,
        "marcha_id": marcha_id,
        "marcha_source": marcha_source,
        "suggested_marcha_id": sugg,
        "shift_weight": weight,
        "weekly_goal": sum(d.goal_questions for d in days),
        "semana_pesada": marcha_id in ("2_pesada", "1_sobrevivencia"),
    }


def _safe_json_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw or not isinstance(raw, str):
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


def load_plan_row(db, user_id: str) -> dict[str, Any] | None:
    try:
        row = db.execute(
            "SELECT * FROM user_six_year_plan WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    except Exception:
        return None
    if not row:
        return None
    return {
        "user_id": row["user_id"],
        "routine_mode_enabled": bool(row["routine_mode_enabled"]),
        "enamed_concept": int(row["enamed_concept"] or 5),
        "foco_override": _safe_json_dict(row["foco_override_json"]),
        "ritual_done": _safe_json_dict(row["ritual_done_json"]),
        "has_feed_token": bool(row["feed_token_hash"]),
        "feed_token_created_at": row["feed_token_created_at"],
        "updated_at": row["updated_at"],
    }


def load_routine_context(
    db,
    user_id: str,
    date_from: date,
    date_to: date,
    *,
    blocks: list[dict[str, Any]] | None = None,
) -> RoutineContext:
    """Carrega blocos, shifts, overrides e marchas em lote (máximo 4 consultas)."""
    eff_blocks = blocks if blocks is not None else _get_user_internato_blocks(db, user_id)

    # Expandir janela para cobrir (início - 1 dia) para pós-plantão e semanas completas
    # para cálculo de peso da Marcha sugerida e summarize_week de toda semana coberta.
    first_week = date.fromisoformat(week_iso_of(date_from))
    last_week_end = date.fromisoformat(week_iso_of(date_to)) + timedelta(days=6)
    range_start = min(date_from, first_week)
    range_end = max(date_to, last_week_end)
    shift_from = (range_start - timedelta(days=1)).isoformat()
    shift_to = range_end.isoformat()

    shifts: dict[str, list[str]] = {}
    shift_rows = db.execute(
        """
        SELECT date_iso, kind FROM user_shifts
        WHERE user_id = ? AND date_iso >= ? AND date_iso <= ?
        ORDER BY date_iso ASC, kind ASC
        """,
        (user_id, shift_from, shift_to),
    ).fetchall()
    for row in shift_rows:
        shifts.setdefault(str(row["date_iso"]), []).append(str(row["kind"]))

    overrides: dict[str, str] = {}
    override_rows = db.execute(
        """
        SELECT date_iso, mode FROM user_day_overrides
        WHERE user_id = ? AND date_iso >= ? AND date_iso <= ?
        """,
        (user_id, range_start.isoformat(), range_end.isoformat()),
    ).fetchall()
    for row in override_rows:
        overrides[str(row["date_iso"])] = str(row["mode"])

    first_week_iso = first_week.isoformat()
    last_week_iso = week_iso_of(date_to)
    marchas: dict[str, str] = {}
    marcha_rows = db.execute(
        """
        SELECT week_iso, marcha_id FROM user_week_marcha
        WHERE user_id = ? AND week_iso >= ? AND week_iso <= ?
        """,
        (user_id, first_week_iso, last_week_iso),
    ).fetchall()
    for row in marcha_rows:
        marchas[str(row["week_iso"])] = str(row["marcha_id"])

    return RoutineContext(
        blocks=eff_blocks,
        shifts=shifts,
        overrides=overrides,
        marchas=marchas,
    )


def resolve_range(
    db,
    user_id: str,
    date_from: date,
    date_to: date,
    *,
    ctx: RoutineContext | None = None,
) -> list[DayStatus]:
    routine_ctx = ctx if ctx is not None else load_routine_context(db, user_id, date_from, date_to)
    total_days = (date_to - date_from).days + 1
    if total_days <= 0:
        return []
    return [resolve_day(date_from + timedelta(days=i), routine_ctx) for i in range(total_days)]


def effective_daily_goal(
    db,
    user_id: str,
    config: dict[str, Any] | None,
    today: date | None = None,
) -> dict[str, Any]:
    """Fonte única da meta diária para adaptive.py e stats_rollup.py."""
    plan = load_plan_row(db, user_id)
    configured = int((config or {}).get("questions_per_day") or DEFAULT_DAILY_GOAL_QUESTIONS)
    if not plan or not plan["routine_mode_enabled"]:
        return {
            "goal": configured,
            "reviews_optional": False,
            "routine_context": {"enabled": False},
        }
    ref_today = today if today is not None else local_today()
    day = resolve_range(db, user_id, ref_today, ref_today)[0]
    return {
        "goal": day.goal_questions,
        "reviews_optional": day.reviews_optional,
        "routine_context": {
            "enabled": True,
            "date_iso": day.date_iso,
            "day_mode": day.mode,
            "source": day.source,
            "is_pos_plantao": day.is_pos_plantao,
            "marcha_id": day.marcha_id,
            "marcha_source": day.marcha_source,
            "rodizio_id": day.rodizio_id,
            "guidance": day.guidance,
        },
    }


def compute_7030_balance(
    db,
    user_id: str,
    today_local: date,
    block: dict[str, Any] | None,
) -> dict[str, Any]:
    """Calcula o saldo real 70/30 nos últimos 7 dias locais (todas as tentativas, inclusive assisted)."""
    window_from_date = today_local - timedelta(days=6)
    start_dt_local = datetime(
        window_from_date.year, window_from_date.month, window_from_date.day, tzinfo=DEFAULT_TZ
    )
    _, end_utc = local_day_bounds_utc(
        datetime(today_local.year, today_local.month, today_local.day, 12, 0, tzinfo=DEFAULT_TZ),
        DEFAULT_TZ,
    )
    start_utc = start_dt_local.astimezone(UTC)

    raw_anchor_areas = list(block.get("ancora_areas") or []) if isinstance(block, dict) else []
    if not raw_anchor_areas and isinstance(block, dict) and block.get("area"):
        raw_anchor_areas = [str(block["area"])]

    exact_anchors = {a.strip() for a in raw_anchor_areas if isinstance(a, str) and a.strip()}
    norm_anchors = {
        get_normalized_area(a)
        for a in exact_anchors
        if get_normalized_area(a) != "Outros"
    }

    rows = db.execute(
        """
        SELECT q.area AS area, COUNT(*) AS cnt
        FROM attempts a
        JOIN questions q ON q.id = a.question_id
        WHERE a.user_id = ? AND a.answered_at >= ? AND a.answered_at < ?
        GROUP BY q.area
        """,
        (user_id, start_utc.isoformat(), end_utc.isoformat()),
    ).fetchall()

    total = 0
    anchor = 0
    for r in rows:
        cnt = int(r["cnt"] or 0)
        total += cnt
        raw_area = str(r["area"] or "").strip()
        norm_area = get_normalized_area(raw_area)
        if raw_area in exact_anchors or (norm_area != "Outros" and norm_area in norm_anchors):
            anchor += cnt

    other = max(0, total - anchor)
    anchor_pct = round((anchor / total) * 100.0, 1) if total > 0 else None
    other_pct = round((other / total) * 100.0, 1) if total > 0 else None

    return {
        "total": total,
        "anchor": anchor,
        "anchor_pct": anchor_pct,
        "other": other,
        "other_pct": other_pct,
        "target_anchor_pct": 70,
        "anchor_areas": raw_anchor_areas,
        "window_from": window_from_date.isoformat(),
        "window_to": today_local.isoformat(),
    }


def hash_feed_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def resolve_feed_token_user(db, raw_token: str | None) -> str | None:
    """Resolve user_id a partir do hash SHA-256 do feed token; retorna None se inválido."""
    token = (raw_token or "").strip()
    if not token or len(token) < 16 or len(token) > 256:
        return None
    token_hash = hash_feed_token(token)
    try:
        row = db.execute(
            "SELECT user_id FROM user_six_year_plan WHERE feed_token_hash = ?",
            (token_hash,),
        ).fetchone()
    except Exception:
        return None
    return str(row["user_id"]) if row else None
