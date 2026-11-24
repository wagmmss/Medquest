def test_meta_endpoint(client):
    response = client.get("/api/meta")
    assert response.status_code == 200
    data = response.json
    
    assert "areas" in data
    assert "institutions" in data
    assert "years" in data
    assert "subtemas" in data
    assert "sources" in data
    assert "specialties" in data
    
    # Assert they are lists
    assert isinstance(data["areas"], list)
    assert isinstance(data["institutions"], list)
    assert isinstance(data["years"], list)
    assert isinstance(data["subtemas"], list)
    assert isinstance(data["sources"], list)
    assert isinstance(data["specialties"], list)

def test_meta_endpoint_with_filters(client):
    response1 = client.get("/api/meta?institution=USP-SP")
    assert response1.status_code == 200
    assert response1.json["total_questions"] == 1
    
    response2 = client.get("/api/meta?institution=USP-SP&institution=USP-RP")
    assert response2.status_code == 200
    assert response2.json["total_questions"] == 2


def test_meta_and_questions_support_multi_year_selection(client):
    # Selecionar 1 ano não deve ocultar os outros anos disponíveis em /api/meta
    res_single = client.get("/api/meta?year=2025")
    assert res_single.status_code == 200
    assert res_single.json["total_questions"] == 2
    assert res_single.json["years"] == [2025, 2021]

    # Múltiplos parâmetros year=...&year=...
    res_multi = client.get("/api/meta?year=2025&year=2021")
    assert res_multi.status_code == 200
    assert res_multi.json["total_questions"] == 3
    assert res_multi.json["years"] == [2025, 2021]

    # Formato separado por vírgula year=2025,2021
    res_csv = client.get("/api/meta?year=2025,2021")
    assert res_csv.status_code == 200
    assert res_csv.json["total_questions"] == 3

    # Fila de questões também respeita múltiplos anos
    res_questions = client.get("/api/questions?year=2025&year=2021")
    assert res_questions.status_code == 200
    assert len(res_questions.json) == 3
    assert {q["year"] for q in res_questions.json} == {2025, 2021}
