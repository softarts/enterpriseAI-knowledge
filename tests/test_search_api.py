"""Tests for GET /search endpoint."""


def test_search_returns_results(client):
    response = client.get("/search?q=离职账号")
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "离职账号"
    assert len(data["results"]) > 0


def test_search_result_contains_required_fields(client):
    response = client.get("/search?q=离职")
    data = response.json()
    assert len(data["results"]) > 0
    result = data["results"][0]
    assert "chunk_id" in result
    assert "document_id" in result
    assert "title" in result
    assert "content" in result
    assert "score" in result
    assert "source_path" in result


def test_search_result_has_document_id(client):
    response = client.get("/search?q=password")
    data = response.json()
    for result in data["results"]:
        assert result["document_id"] != ""


def test_search_result_has_source_path(client):
    response = client.get("/search?q=code review")
    data = response.json()
    assert len(data["results"]) > 0
    for result in data["results"]:
        assert result["source_path"] != ""


def test_search_respects_top_k(client):
    response = client.get("/search?q=管理&top_k=1")
    data = response.json()
    assert len(data["results"]) <= 1


def test_search_empty_query_rejected(client):
    response = client.get("/search?q=")
    # FastAPI validates min_length=1, returns 422
    assert response.status_code == 422


def test_search_no_results_for_irrelevant_query(client):
    response = client.get("/search?q=zzzzxxxxxqqqqqunknown")
    data = response.json()
    assert data["results"] == []
