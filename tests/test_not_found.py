"""Tests for 404 error handling."""


def test_nonexistent_document_returns_404(client):
    response = client.get("/documents/nonexistent-document")
    assert response.status_code == 404


def test_404_error_format(client):
    response = client.get("/documents/does-not-exist")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    detail = data["detail"]
    assert detail["error"]["code"] == "DOCUMENT_NOT_FOUND"
    assert "does-not-exist" in detail["error"]["message"]
