"""Tests for GET /documents endpoint."""


def test_list_documents_returns_all(client):
    response = client.get("/documents")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3
    assert data["page"] == 1
    assert data["page_size"] == 20


def test_list_documents_filter_by_keyword(client):
    response = client.get("/documents?keyword=账号")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["document_id"] == "security-account-policy"


def test_list_documents_filter_by_tag(client):
    response = client.get("/documents?tag=engineering")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["document_id"] == "engineering-dev-standard"


def test_list_documents_pagination(client):
    response = client.get("/documents?page=1&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 2


def test_list_documents_page_2(client):
    response = client.get("/documents?page=2&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["items"]) == 1


def test_list_documents_no_content_in_summary(client):
    """Document list should NOT include full content."""
    response = client.get("/documents")
    data = response.json()
    for item in data["items"]:
        assert "content" not in item


def test_list_documents_includes_source_path(client):
    response = client.get("/documents")
    data = response.json()
    for item in data["items"]:
        assert "source_path" in item
        assert item["source_path"] != ""
