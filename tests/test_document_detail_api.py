"""Tests for GET /documents/{document_id} endpoint."""


def test_get_document_detail(client):
    response = client.get("/documents/security-account-policy")
    assert response.status_code == 200
    data = response.json()
    assert data["document_id"] == "security-account-policy"
    assert data["title"] == "企业账号管理制度"
    assert data["author"] == "IT Department"
    assert "security" in data["tags"]
    assert data["source_path"] == "security/account_policy.pdf"
    # Content is included in detail
    assert "content" in data
    assert "离职账号管理" in data["content"]


def test_get_document_content_is_markdown(client):
    """Content should be Markdown body, not raw YAML frontmatter."""
    response = client.get("/documents/security-account-policy")
    data = response.json()
    content = data["content"]
    # Should start with markdown heading or body text
    assert content.startswith("#") or content[0].isalpha()
    # Should NOT contain frontmatter delimiters at the start
    assert not content.startswith("---")


def test_get_document_includes_all_summary_fields(client):
    response = client.get("/documents/hr-leave-policy")
    assert response.status_code == 200
    data = response.json()
    assert "document_id" in data
    assert "title" in data
    assert "author" in data
    assert "created_at" in data
    assert "tags" in data
    assert "source_path" in data
    assert "content" in data
