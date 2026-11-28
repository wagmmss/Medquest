"""Testes das rotas HTTP autenticadas do blueprint api/six_year.py."""
from __future__ import annotations

from api.db import get_db


def test_summary_without_plan_row_returns_defaults_without_inserting(app, client):
    res = client.get("/api/six-year/summary")
    assert res.status_code == 200
    data = res.get_json()
    assert data["plan"]["routine_mode_enabled"] is False
    assert data["plan"]["enamed_concept"] == 5
    assert data["plan"]["has_feed_token"] is False
    assert len(data["days"]) == 14
    assert data["curriculum_entries"] == {}
    assert data["milestones"] == []
    assert data["next_milestone"] is None

    with app.app_context():
        db = get_db()
        row = db.execute("SELECT * FROM user_six_year_plan WHERE user_id = '1'").fetchone()
        assert row is None


def test_patch_plan_merges_foco_override_and_ritual_done(client):
    res1 = client.patch(
        "/api/six-year/plan",
        json={
            "routine_mode_enabled": True,
            "enamed_concept": 4,
            "foco_override": {"cirurgia": {"ancora70": "Abdome agudo"}},
            "ritual_done": {"2027-01-30": {"item_1": True, "item_2": True}},
        },
    )
    assert res1.status_code == 200
    p1 = res1.get_json()["plan"]
    assert p1["routine_mode_enabled"] is True
    assert p1["enamed_concept"] == 4
    assert p1["foco_override"] == {"cirurgia": {"ancora70": "Abdome agudo"}}
    assert p1["ritual_done"] == {"2027-01-30": {"item_1": True, "item_2": True}}

    # Merge parcial: adicionar trilha30 em cirurgia, remover item_2 e preservar rotina/enamed
    res2 = client.patch(
        "/api/six-year/plan",
        json={
            "foco_override": {"cirurgia": {"trilha30": "Revisão de HAS"}},
            "ritual_done": {"2027-01-30": {"item_2": False, "item_3": True}},
        },
    )
    assert res2.status_code == 200
    p2 = res2.get_json()["plan"]
    assert p2["routine_mode_enabled"] is True
    assert p2["enamed_concept"] == 4
    assert p2["foco_override"] == {
        "cirurgia": {"ancora70": "Abdome agudo", "trilha30": "Revisão de HAS"}
    }
    assert p2["ritual_done"] == {"2027-01-30": {"item_1": True, "item_3": True}}

    # Limpar override com None
    res3 = client.patch(
        "/api/six-year/plan",
        json={"foco_override": {"cirurgia": {"ancora70": None, "trilha30": None}}},
    )
    assert res3.status_code == 200
    assert res3.get_json()["plan"]["foco_override"] == {}


def test_marcha_requires_monday_and_supports_revert_to_suggested(client):
    # 2027-02-02 é terça-feira -> 400
    bad = client.put("/api/six-year/marcha/2027-02-02", json={"marcha_id": "4_sprint"})
    assert bad.status_code == 400

    # Data impossível -> 400
    bad2 = client.put("/api/six-year/marcha/2027-02-31", json={"marcha_id": "4_sprint"})
    assert bad2.status_code == 400

    # 2027-02-01 é segunda-feira -> 200 confirmada
    ok = client.put("/api/six-year/marcha/2027-02-01", json={"marcha_id": "4_sprint"})
    assert ok.status_code == 200
    assert ok.get_json() == {
        "week_iso": "2027-02-01",
        "marcha_id": "4_sprint",
        "marcha_source": "confirmada",
    }

    # null volta para sugerida
    rev = client.put("/api/six-year/marcha/2027-02-01", json={"marcha_id": None})
    assert rev.status_code == 200
    assert rev.get_json() == {
        "week_iso": "2027-02-01",
        "marcha_id": "3_normal",
        "marcha_source": "sugerida",
    }


def test_shifts_batch_idempotent_counts_and_invalid_calendar_date(client):
    # Data impossível 2027-02-31 -> 400 (C6)
    bad = client.post(
        "/api/six-year/shifts/batch",
        json={"add": [{"date_iso": "2027-02-31", "kind": "plantao_noturno"}]},
    )
    assert bad.status_code == 400

    # 1ª chamada adiciona 1 shift e retorna dias afetados ±1 (02, 03, 04) com 04 em pos_plantao
    res1 = client.post(
        "/api/six-year/shifts/batch",
        json={"add": [{"date_iso": "2027-02-03", "kind": "plantao_noturno", "note": "PS"}]},
    )
    assert res1.status_code == 200
    body1 = res1.get_json()
    assert body1["added"] == 1
    assert body1["removed"] == 0
    days_by_iso = {d["date_iso"]: d for d in body1["days"]}
    assert set(days_by_iso.keys()) == {"2027-02-02", "2027-02-03", "2027-02-04"}
    assert days_by_iso["2027-02-03"]["mode"] == "entrada_noturno"
    assert days_by_iso["2027-02-04"]["mode"] == "pos_plantao"

    # 2ª chamada idempotente com mesmo (date_iso, kind) -> added=0
    res2 = client.post(
        "/api/six-year/shifts/batch",
        json={"add": [{"date_iso": "2027-02-03", "kind": "plantao_noturno", "note": "PS2"}]},
    )
    assert res2.status_code == 200
    assert res2.get_json()["added"] == 0

    # Remover shift -> removed=1 e 04 deixa de ser pos_plantao
    res3 = client.post(
        "/api/six-year/shifts/batch",
        json={"remove": [{"date_iso": "2027-02-03", "kind": "plantao_noturno"}]},
    )
    assert res3.status_code == 200
    body3 = res3.get_json()
    assert body3["removed"] == 1
    days3 = {d["date_iso"]: d for d in body3["days"]}
    assert days3["2027-02-04"]["mode"] == "integral"


def test_day_override_put_delete_and_preview_limit(client):
    assert client.put("/api/six-year/day-override/2027-02-31", json={"mode": "folga"}).status_code == 400

    put_res = client.put("/api/six-year/day-override/2027-02-04", json={"mode": "pos_plantao"})
    assert put_res.status_code == 200
    assert put_res.get_json()["day"]["mode"] == "pos_plantao"
    assert put_res.get_json()["day"]["goal_questions"] == 0

    del_res = client.delete("/api/six-year/day-override/2027-02-04")
    assert del_res.status_code == 200
    assert del_res.get_json()["day"]["mode"] == "integral"
    assert del_res.get_json()["day"]["goal_questions"] == 25

    # Preview dentro de 62 dias -> 200
    prev_ok = client.get("/api/six-year/preview?from=2027-02-01&to=2027-03-04")
    assert prev_ok.status_code == 200
    prev_data = prev_ok.get_json()
    assert len(prev_data["days"]) == 32
    assert len(prev_data["weeks"]) >= 5

    # Preview > 62 dias -> 400
    prev_bad = client.get("/api/six-year/preview?from=2027-01-01&to=2027-04-01")
    assert prev_bad.status_code == 400


def test_curriculum_upsert_and_milestones_crud(client):
    assert client.put(
        "/api/six-year/curriculum/BAD-ID!",
        json={"value": 1, "proof_status": "falta"},
    ).status_code == 400

    c_res = client.put(
        "/api/six-year/curriculum/ic_cnpq",
        json={"value": 2, "proof_status": "pdf_pronto", "note": "Declaração assinada"},
    )
    assert c_res.status_code == 200
    assert c_res.get_json()["entry"]["proof_status"] == "pdf_pronto"

    # Criar milestone sem id (gera uuid4)
    m_create = client.post(
        "/api/six-year/milestones",
        json={"titulo": "Inscrição ENARE", "data_iso": "2027-08-15", "categoria": "prova"},
    )
    assert m_create.status_code == 201
    mid = m_create.get_json()["milestone"]["id"]
    assert len(mid) == 32

    # PATCH existente
    m_patch = client.patch(f"/api/six-year/milestones/{mid}", json={"done": True, "note": "Pago"})
    assert m_patch.status_code == 200
    assert m_patch.get_json()["milestone"]["done"] is True
    assert m_patch.get_json()["milestone"]["note"] == "Pago"

    # PATCH inexistente -> 404
    assert client.patch("/api/six-year/milestones/nao_existe", json={"done": True}).status_code == 404

    # DELETE existente -> 204; repetir -> 404
    assert client.delete(f"/api/six-year/milestones/{mid}").status_code == 204
    assert client.delete(f"/api/six-year/milestones/{mid}").status_code == 404
