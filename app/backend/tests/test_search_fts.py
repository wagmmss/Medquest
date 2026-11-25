"""Testes de integração e regressão para o motor de busca FTS5 e filtros clínicos."""


def test_search_empty_returns_empty_list(client):
    res = client.get("/api/search")
    assert res.status_code == 200
    assert res.get_json() == []


def test_search_fts_clinical_term(client):
    res = client.get("/api/search?q=infarto")
    assert res.status_code == 200
    data = res.get_json()
    assert isinstance(data, list)
    if len(data) > 0:
        first = data[0]
        assert "id" in first
        assert "stem_snippet" in first
        assert "area" in first
        assert "institution_code" in first


def test_search_with_area_filter(client):
    res = client.get("/api/search?q=infarto&area=Cl%C3%ADnica%20M%C3%A9dica")
    assert res.status_code == 200
    data = res.get_json()
    assert isinstance(data, list)
    for item in data:
        assert item["area"] == "Clínica Médica"


def test_search_with_institution_filter(client):
    res = client.get("/api/search?q=diagnostico&institution=ENARE")
    assert res.status_code == 200
    data = res.get_json()
    assert isinstance(data, list)
    for item in data:
        assert item["institution_code"] == "ENARE"


def test_search_structured_filter_only(client):
    res = client.get("/api/search?area=Cirurgia&limit=5")
    assert res.status_code == 200
    data = res.get_json()
    assert isinstance(data, list)
    assert len(data) <= 5
    for item in data:
        assert item["area"] == "Cirurgia"


def test_search_invalid_year_is_ignored(client):
    """Um year não numérico deve ser ignorado (não gerar 500 por binding mismatch)."""
    baseline = client.get("/api/search?area=Pediatria")
    res = client.get("/api/search?area=Pediatria&year=abc")
    assert baseline.status_code == 200
    assert res.status_code == 200
    assert [item["id"] for item in res.get_json()] == [item["id"] for item in baseline.get_json()]


def test_search_semantic_calls_expand_once_and_skips_like_when_fts_populated(client, app, monkeypatch):
    with app.app_context():
        from api.db import get_db
        db = get_db()
        db.execute("INSERT OR IGNORE INTO questions_fts(rowid, stem, explanation) VALUES (1, 'Hipertensao arterial', 'explicacao')")
        db.commit()

    calls = {"n": 0}

    def fake_expand(q):
        calls["n"] += 1
        return ["termoinexistente1", "termoinexistente2"]

    monkeypatch.setattr("api.ai.expand_search_query", fake_expand)
    res = client.get("/api/search?q=inexistente&semantic=true")
    assert res.status_code == 200
    assert res.get_json() == []
    assert calls["n"] == 1


def test_search_fts_external_content_turso_schema_highlights_stem(client, app):
    with app.app_context():
        from api.db import get_db

        db = get_db()
        db.execute(
            "UPDATE questions SET topic = 'TopicoCardio', stem = 'Paciente com hipertensao arterial.' WHERE id = 1"
        )
        db.execute("DROP TABLE IF EXISTS questions_fts")
        db.execute(
            "CREATE VIRTUAL TABLE questions_fts USING fts5(topic, stem, area, subtema, content='questions', content_rowid='id')"
        )
        db.execute("INSERT INTO questions_fts(questions_fts) VALUES('rebuild')")
        db.commit()

    res = client.get("/api/search?q=hipertensao")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data) >= 1
    assert "<b>hipertensao</b>" in (data[0].get("stem_snippet") or "").lower()
    assert "TopicoCardio" not in (data[0].get("stem_snippet") or "")
    assert "<b>" not in (data[0].get("exp_snippet") or "")
