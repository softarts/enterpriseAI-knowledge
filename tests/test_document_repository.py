"""Tests for OKFDocumentRepository."""

from pathlib import Path

from doc_service.repositories.okf_document_repository import OKFDocumentRepository


def test_scan_discovers_all_fixtures(fixtures_dir):
    repo = OKFDocumentRepository(okf_dir=fixtures_dir)
    docs = repo.list_documents()
    assert len(docs) == 3


def test_parse_frontmatter_correctly(fixtures_dir):
    repo = OKFDocumentRepository(okf_dir=fixtures_dir)
    doc = repo.get_document("security-account-policy")
    assert doc is not None
    assert doc.title == "企业账号管理制度"
    assert doc.author == "IT Department"
    assert doc.created_at == "2026-08-01T10:00:00"
    assert "security" in doc.tags
    assert "account" in doc.tags
    assert doc.source_path == "security/account_policy.pdf"


def test_content_is_markdown_body_without_frontmatter(fixtures_dir):
    repo = OKFDocumentRepository(okf_dir=fixtures_dir)
    doc = repo.get_document("security-account-policy")
    assert doc is not None
    # Content should NOT contain the --- frontmatter markers
    assert "---" not in doc.content.split("\n")[0]
    # Content should contain the markdown body
    assert "企业账号管理制度" in doc.content
    assert "离职账号管理" in doc.content


def test_document_id_is_stable(fixtures_dir):
    repo = OKFDocumentRepository(okf_dir=fixtures_dir)
    # Load twice, IDs must be identical
    doc1 = repo.get_document("hr-leave-policy")
    repo.reload()
    doc2 = repo.get_document("hr-leave-policy")
    assert doc1 is not None
    assert doc2 is not None
    assert doc1.document_id == doc2.document_id


def test_filter_by_keyword(fixtures_dir):
    repo = OKFDocumentRepository(okf_dir=fixtures_dir)
    docs = repo.list_documents(keyword="账号")
    assert len(docs) == 1
    assert docs[0].document_id == "security-account-policy"


def test_filter_by_tag(fixtures_dir):
    repo = OKFDocumentRepository(okf_dir=fixtures_dir)
    docs = repo.list_documents(tag="HR")
    assert len(docs) == 1
    assert docs[0].document_id == "hr-leave-policy"


def test_nonexistent_document_returns_none(fixtures_dir):
    repo = OKFDocumentRepository(okf_dir=fixtures_dir)
    doc = repo.get_document("nonexistent-doc")
    assert doc is None
