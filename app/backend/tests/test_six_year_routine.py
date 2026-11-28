"""Testes unitários do motor puro de rotina do 6º ano (api/services/six_year_routine.py)."""
from __future__ import annotations

from datetime import UTC, date, datetime

from api.internato_config import RODIZIOS_TURMA_J
from api.services.six_year_routine import (
    RoutineContext,
    local_today,
    resolve_day,
    ritual_cycle_key,
    round5_half_up,
    suggested_marcha,
    week_iso_of,
)


def _ctx(
    *,
    blocks=None,
    shifts=None,
    overrides=None,
    marchas=None,
) -> RoutineContext:
    return RoutineContext(
        blocks=blocks if blocks is not None else RODIZIOS_TURMA_J,
        shifts=shifts or {},
        overrides=overrides or {},
        marchas=marchas or {},
    )


def test_round5_half_up_matches_js_math_round():
    assert round5_half_up(12.5) == 15
    assert round5_half_up(7.5) == 10
    assert round5_half_up(2.5) == 5
    assert round5_half_up(55 * 1.5) == 85
    assert round5_half_up(25 * 0.72) == 20
    assert round5_half_up(25 * 0.4) == 10
    assert round5_half_up(10 * 0.4) == 5


def test_week_iso_of_and_ritual_cycle_key():
    # 2027-02-01 é segunda-feira; 2027-02-06 é sábado; 2027-02-07 é domingo
    assert week_iso_of(date(2027, 2, 1)) == "2027-02-01"
    assert week_iso_of(date(2027, 2, 4)) == "2027-02-01"
    assert week_iso_of(date(2027, 2, 7)) == "2027-02-01"

    # Sábado = ele mesmo; domingo -> sábado anterior; sexta -> sábado anterior
    assert ritual_cycle_key(date(2027, 2, 6)) == "2027-02-06"
    assert ritual_cycle_key(date(2027, 2, 7)) == "2027-02-06"
    assert ritual_cycle_key(date(2027, 2, 5)) == "2027-01-30"
    assert ritual_cycle_key(date(2027, 2, 1)) == "2027-01-30"


def test_suggested_marcha_weights():
    w = "2027-02-01"
    assert suggested_marcha(w, {}) == "3_normal"  # peso 0
    assert suggested_marcha(w, {"2027-02-03": ["plantao_noturno"]}) == "3_normal"  # peso 1
    assert suggested_marcha(w, {"2027-02-03": ["plantao_24h"]}) == "2_pesada"  # peso 2
    assert (
        suggested_marcha(
            w,
            {
                "2027-02-02": ["plantao_12h_dia"],
                "2027-02-04": ["plantao_noturno"],
            },
        )
        == "2_pesada"
    )  # peso 2
    assert (
        suggested_marcha(
            w,
            {
                "2027-02-02": ["plantao_24h"],
                "2027-02-05": ["plantao_noturno"],
            },
        )
        == "1_sobrevivencia"
    )  # peso 3


def test_timezone_boundary_2330_brt_is_local_day():
    # 2027-02-04 23:30 BRT (-03:00) == 2027-02-05 02:30 UTC
    utc_dt = datetime(2027, 2, 5, 2, 30, tzinfo=UTC)
    assert local_today(utc_dt) == date(2027, 2, 4)


def test_edge_1_consecutive_night_shifts_wednesday_is_pos_plantao():
    ctx = _ctx(
        shifts={
            "2027-02-02": ["plantao_noturno"],  # terça
            "2027-02-03": ["plantao_noturno"],  # quarta
        }
    )
    wed = resolve_day(date(2027, 2, 3), ctx)
    assert wed.mode == "pos_plantao"
    assert wed.source == "pos_plantao"
    assert wed.is_pos_plantao is True
    assert wed.goal_questions == 0
    assert wed.reviews_optional is True


def test_edge_2_24h_saturday_protects_saturday_and_sunday():
    ctx = _ctx(shifts={"2027-02-06": ["plantao_24h"]})
    sat = resolve_day(date(2027, 2, 6), ctx)
    sun = resolve_day(date(2027, 2, 7), ctx)
    assert sat.mode == "plantao_24h"
    assert sat.goal_questions == 0
    assert sat.reviews_optional is True
    assert sun.mode == "pos_plantao"
    assert sun.goal_questions == 0
    assert sun.reviews_optional is True


def test_edge_3_sunday_night_shift_carries_over_week_boundary():
    # 2027-02-07 domingo (semana 2027-02-01 com 3 plantões -> sobrevivência)
    # 2027-02-08 segunda (semana 2027-02-08 sem plantões -> normal, mas pós-plantão!)
    ctx = _ctx(
        shifts={
            "2027-02-02": ["plantao_24h"],
            "2027-02-07": ["plantao_noturno"],
        }
    )
    sun = resolve_day(date(2027, 2, 7), ctx)
    mon = resolve_day(date(2027, 2, 8), ctx)
    assert sun.marcha_id == "1_sobrevivencia"
    assert mon.marcha_id == "3_normal"
    assert mon.mode == "pos_plantao"
    assert mon.goal_questions == 0


def test_edge_4_override_beats_pos_plantao():
    ctx = _ctx(
        shifts={"2027-02-03": ["plantao_noturno"]},
        overrides={"2027-02-04": "integral"},
    )
    thu = resolve_day(date(2027, 2, 4), ctx)
    assert thu.mode == "integral"
    assert thu.source == "override"
    assert thu.is_pos_plantao is False
    assert thu.goal_questions == 25


def test_edge_5_date_outside_blocks_uses_default_pattern():
    ctx = _ctx()
    # 2025-05-05 é segunda fora de qualquer bloco
    day = resolve_day(date(2025, 5, 5), ctx)
    assert day.rodizio_id is None
    assert day.mode == "integral"
    assert day.source == "pattern"
    assert day.goal_questions == 25


def test_edge_6_rotation_boundary_changes_week_pattern():
    custom_blocks = [
        {
            "id": "bloco_a",
            "start": "2027-02-01",
            "end": "2027-02-03",
            "area": "Cirurgia",
            "week_pattern": {"qua": "meio_periodo"},
        },
        {
            "id": "bloco_b",
            "start": "2027-02-04",
            "end": "2027-02-07",
            "area": "Clínica Médica",
            "week_pattern": {"qui": "folga"},
        },
    ]
    ctx = _ctx(blocks=custom_blocks)
    d_a = resolve_day(date(2027, 2, 3), ctx)
    d_b = resolve_day(date(2027, 2, 4), ctx)
    assert d_a.rodizio_id == "bloco_a"
    assert d_a.mode == "meio_periodo"
    assert d_a.goal_questions == 40
    assert d_b.rodizio_id == "bloco_b"
    assert d_b.mode == "folga"
    assert d_b.goal_questions == 55


def test_edge_7_sprint_folga_equals_85():
    ctx = _ctx(marchas={"2027-02-01": "4_sprint"})
    # 2027-02-06 é sábado (padrão folga = 55; 55 * 1.5 = 82.5 -> 85)
    sat = resolve_day(date(2027, 2, 6), ctx)
    assert sat.mode == "folga"
    assert sat.marcha_id == "4_sprint"
    assert sat.marcha_source == "confirmada"
    assert sat.goal_questions == 85


def test_edge_8_sobrevivencia_floors_at_5_and_integral_at_10():
    ctx = _ctx(
        marchas={"2027-02-01": "1_sobrevivencia"},
        shifts={"2027-02-04": ["plantao_12h_dia"]},
    )
    wed = resolve_day(date(2027, 2, 3), ctx)
    thu = resolve_day(date(2027, 2, 4), ctx)
    assert wed.mode == "integral"
    assert wed.goal_questions == 10
    assert thu.mode == "plantao_12h_dia"
    assert thu.goal_questions == 5


def test_edge_9_two_shifts_same_day_tie_breaks_by_priority():
    ctx = _ctx(shifts={"2027-02-04": ["plantao_12h_dia", "plantao_noturno"]})
    thu = resolve_day(date(2027, 2, 4), ctx)
    # Ambos têm base 10; DAY_MODE_LABEL_PRIORITY prioriza entrada_noturno sobre plantao_12h_dia
    assert thu.mode == "entrada_noturno"
    assert thu.source == "shift"
    assert thu.goal_questions == 5 or thu.goal_questions == 10
    # Com peso 2 (12h_dia=1 + noturno=1) -> 2_pesada (0.72 * 10 = 7.2 -> 5)
    assert thu.marcha_id == "2_pesada"
    assert thu.goal_questions == 5
