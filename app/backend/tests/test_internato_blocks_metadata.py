"""Testes de metadados de rodízios, merge sem migração, preservação do cronograma e reset seguro (C5)."""
from __future__ import annotations

from api.db import get_db
from api.services.planner_store import merge_with_default_metadata


def test_merge_with_default_metadata_by_id_dates_and_overlap():
    # 1) Match por id preserva overrides do usuário e preenche ausentes
    by_id = merge_with_default_metadata([
        {
            "id": "cirurgia",
            "start": "2027-01-20",
            "end": "2027-02-20",
            "area": "Cirurgia",
            "ancora70": "Meu foco personalizado",
        }
    ])
    assert by_id[0]["ancora70"] == "Meu foco personalizado"
    assert by_id[0]["trilha30"]  # preenchido do default
    assert by_id[0]["ancora_areas"] == ["Cirurgia"]

    # 2) Match por (start, end) sem id
    by_dates = merge_with_default_metadata([
        {
            "start": "2027-03-22",
            "end": "2027-04-18",
            "area": "Ginecologia e Obstetrícia",
        }
    ])
    assert by_dates[0]["id"] == "go"
    assert by_dates[0]["micro_habito"]

    # 3) Match por maior sobreposição na mesma área
    by_overlap = merge_with_default_metadata([
        {
            "start": "2027-07-01",
            "end": "2027-07-28",
            "area": "Clínica Médica",
        }
    ])
    assert by_overlap[0]["id"] == "cm"
    assert by_overlap[0]["ancora_areas"] == ["Clínica Médica"]


def test_editing_only_ancora70_preserves_planner_schedule_while_changing_end_regenerates(app, client):
    initial_blocks = [
        {
            "id": "cirurgia",
            "start": "2027-01-25",
            "end": "2027-02-21",
            "area": "Cirurgia",
            "label": "Cirurgia Geral",
            "ancora70": "Foco inicial",
        }
    ]
    res = client.put("/api/planner/internato-blocks", json={"blocks": initial_blocks})
    assert res.status_code == 200

    # Inserir uma entrada de cronograma internato_* para verificar se será preservada ou limpa
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO planner_schedule (user_id, mode, week, subtema, display_order, created_at)
            VALUES ('1', 'internato_standard', 1, 'Trauma', 0, '2027-02-01T00:00:00+00:00')
            """
        )
        db.commit()

    # Alterar somente ancora70 e week_pattern -> NÃO deve deletar planner_schedule
    edited_meta = [
        {
            **initial_blocks[0],
            "ancora70": "Foco atualizado sem mudar datas",
            "week_pattern": {"seg": "meio_periodo", "sab": "folga"},
        }
    ]
    res2 = client.put("/api/planner/internato-blocks", json={"blocks": edited_meta})
    assert res2.status_code == 200
    with app.app_context():
        db = get_db()
        count = db.execute(
            "SELECT COUNT(*) AS c FROM planner_schedule WHERE user_id = '1' AND mode LIKE 'internato_%'"
        ).fetchone()["c"]
        assert count == 1

    # Alterar data de término -> DEVE invalidar planner_schedule internato_*
    edited_dates = [{**edited_meta[0], "end": "2027-02-28"}]
    res3 = client.put("/api/planner/internato-blocks", json={"blocks": edited_dates})
    assert res3.status_code == 200
    with app.app_context():
        db = get_db()
        count = db.execute(
            "SELECT COUNT(*) AS c FROM planner_schedule WHERE user_id = '1' AND mode LIKE 'internato_%'"
        ).fetchone()["c"]
        assert count == 0


def test_internato_blocks_rejects_unknown_fields_and_invalid_dates(client):
    res_extra = client.put(
        "/api/planner/internato-blocks",
        json={
            "blocks": [
                {
                    "start": "2027-01-25",
                    "end": "2027-02-21",
                    "area": "Cirurgia",
                    "campo_desconhecido": "nope",
                }
            ]
        },
    )
    assert res_extra.status_code == 400

    res_bad_date = client.put(
        "/api/planner/internato-blocks",
        json={
            "blocks": [
                {
                    "start": "2027-02-31",
                    "end": "2027-03-10",
                    "area": "Cirurgia",
                }
            ]
        },
    )
    assert res_bad_date.status_code == 400


def test_planner_config_reset_all_preserves_six_year_tables(app, client):
    # Popular todas as tabelas do 6º ano antes de resetar o planner
    assert client.patch("/api/six-year/plan", json={"routine_mode_enabled": True, "enamed_concept": 4}).status_code == 200
    assert client.put("/api/six-year/marcha/2027-02-01", json={"marcha_id": "2_pesada"}).status_code == 200
    assert client.post(
        "/api/six-year/shifts/batch",
        json={"add": [{"date_iso": "2027-02-04", "kind": "plantao_noturno"}]},
    ).status_code == 200
    assert client.put("/api/six-year/day-override/2027-02-05", json={"mode": "folga"}).status_code == 200
    assert client.put(
        "/api/six-year/curriculum/ic_cnpq",
        json={"value": 1, "proof_status": "pdf_pronto", "note": "ok"},
    ).status_code == 200
    assert client.post(
        "/api/six-year/milestones",
        json={"id": "ms1", "titulo": "Prova R1", "data_iso": "2027-10-15"},
    ).status_code == 201

    res = client.post("/api/planner/config/reset", json={"scope": "all"})
    assert res.status_code == 200

    with app.app_context():
        db = get_db()
        for tbl in (
            "user_six_year_plan",
            "user_week_marcha",
            "user_shifts",
            "user_day_overrides",
            "user_curriculum_entries",
            "user_r1_milestones",
        ):
            cnt = db.execute(f"SELECT COUNT(*) AS c FROM {tbl} WHERE user_id = '1'").fetchone()["c"]
            assert cnt == 1, f"Tabela {tbl} foi apagada indevidamente pelo reset do planner"
