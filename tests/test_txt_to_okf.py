"""
Tests for TXT -> OKF conversion and structural preservation.

Covers:
- Plain text preservation
- Document title and multiple heading levels
- Ordered and unordered lists
- Markdown tables
- Code blocks (including special chars and indentation)
- Mixed document structures
- Metadata generation (document_id, title, author, created_at, updated_at, source_path, source_type)
- document_id consistency with OKFDocumentRepository
- Ambiguous line handling (remains normal text, no guessing)
"""

from pathlib import Path
import pytest
import yaml

from doc_service.repositories.okf_document_repository import OKFDocumentRepository
from import_raw_doc_to_okf import (
    build_metadata,
    compute_document_id,
    convert_file,
    extract_title,
    generate_okf,
    get_default_config,
    normalize_txt_structure,
)


@pytest.fixture
def sample_config():
    config = get_default_config()
    config["tag_rules"] = [
        {"match_path": "security", "tags": ["security", "compliance"]},
        {"match_path": "finance", "tags": ["finance"]},
    ]
    return config


def test_plain_text_preservation(tmp_path, sample_config):
    """Test that plain text content and paragraphs are preserved without modification."""
    txt_content = (
        "Enterprise Knowledge Base Overview\n\n"
        "This is the first paragraph with simple statements.\n\n"
        "This is the second paragraph containing detailed explanations."
    )
    input_file = tmp_path / "overview.txt"
    input_file.write_text(txt_content, encoding="utf-8")
    output_dir = tmp_path / "generated"

    success = convert_file(
        file_path=input_file,
        input_root=tmp_path,
        output_dir=output_dir,
        config=sample_config,
        mirror=True,
    )
    assert success is True

    okf_file = output_dir / "overview.yaml"
    assert okf_file.exists()

    content = okf_file.read_text(encoding="utf-8")
    assert "Enterprise Knowledge Base Overview" in content
    assert "This is the first paragraph with simple statements." in content
    assert "This is the second paragraph containing detailed explanations." in content


def test_title_and_heading_levels(tmp_path, sample_config):
    """Test that document title and various markdown heading levels are preserved."""
    txt_content = (
        "# System Architecture\n\n"
        "## Component Overview\n\n"
        "Details about components.\n\n"
        "### Ingestion Subsystem\n\n"
        "Details about ingestion.\n\n"
        "#### TXT Converter\n\n"
        "Details about TXT converter."
    )
    input_file = tmp_path / "architecture.txt"
    input_file.write_text(txt_content, encoding="utf-8")
    output_dir = tmp_path / "generated"

    convert_file(input_file, tmp_path, output_dir, sample_config, mirror=True)
    okf_file = output_dir / "architecture.yaml"
    content = okf_file.read_text(encoding="utf-8")

    assert "# System Architecture" in content
    assert "## Component Overview" in content
    assert "### Ingestion Subsystem" in content
    assert "#### TXT Converter" in content


def test_setext_heading_normalization():
    """Test that Setext underline headings are normalized to standard Markdown headings."""
    raw_text = (
        "Main Title\n"
        "===\n\n"
        "Intro text.\n\n"
        "Section Subtitle\n"
        "---\n\n"
        "Section text."
    )
    normalized = normalize_txt_structure(raw_text)
    assert "# Main Title" in normalized
    assert "## Section Subtitle" in normalized


def test_ambiguous_lines_kept_as_normal_text(tmp_path, sample_config):
    """Test that ambiguous lines are not guessed as headings and remain normal text."""
    txt_content = (
        "Project Status Notes\n\n"
        "Important Note 1: This is not a heading but a long descriptive sentence.\n"
        "Note 2: Another regular sentence that should stay as paragraph text.\n"
    )
    input_file = tmp_path / "notes.txt"
    input_file.write_text(txt_content, encoding="utf-8")
    output_dir = tmp_path / "generated"

    convert_file(input_file, tmp_path, output_dir, sample_config, mirror=True)
    okf_file = output_dir / "notes.yaml"
    content = okf_file.read_text(encoding="utf-8")

    assert "# Project Status Notes" in content
    assert "Important Note 1: This is not a heading" in content
    assert "# Important Note 1" not in content


def test_ordered_and_unordered_lists(tmp_path, sample_config):
    """Test that ordered and unordered lists are preserved."""
    txt_content = (
        "Checklist and Requirements\n\n"
        "Unordered items:\n"
        "- Item Alpha\n"
        "- Item Beta\n"
        "  * Subitem Beta 1\n"
        "  * Subitem Beta 2\n\n"
        "Ordered steps:\n"
        "1. Step One: Initialize environment\n"
        "2. Step Two: Run ingestion\n"
        "3. Step Three: Verify repository"
    )
    input_file = tmp_path / "checklist.txt"
    input_file.write_text(txt_content, encoding="utf-8")
    output_dir = tmp_path / "generated"

    convert_file(input_file, tmp_path, output_dir, sample_config, mirror=True)
    okf_file = output_dir / "checklist.yaml"
    content = okf_file.read_text(encoding="utf-8")

    assert "- Item Alpha" in content
    assert "- Item Beta" in content
    assert "* Subitem Beta 1" in content
    assert "1. Step One: Initialize environment" in content
    assert "2. Step Two: Run ingestion" in content
    assert "3. Step Three: Verify repository" in content


def test_markdown_tables(tmp_path, sample_config):
    """Test that Markdown table structures and cells are preserved intact."""
    txt_content = (
        "Performance Benchmarks\n\n"
        "| Metric | Target | Actual | Status |\n"
        "| :--- | :--- | :--- | :--- |\n"
        "| Latency | < 50ms | 12ms | Passed |\n"
        "| Accuracy | > 95% | 98.4% | Passed |\n"
    )
    input_file = tmp_path / "benchmarks.txt"
    input_file.write_text(txt_content, encoding="utf-8")
    output_dir = tmp_path / "generated"

    convert_file(input_file, tmp_path, output_dir, sample_config, mirror=True)
    okf_file = output_dir / "benchmarks.yaml"
    content = okf_file.read_text(encoding="utf-8")

    assert "| Metric | Target | Actual | Status |" in content
    assert "| Latency | < 50ms | 12ms | Passed |" in content
    assert "| Accuracy | > 95% | 98.4% | Passed |" in content


def test_code_blocks_preservation(tmp_path, sample_config):
    """Test that fenced code blocks with indentation, language tags, and symbols are preserved."""
    txt_content = (
        "Developer Guide\n\n"
        "Here is a Python example:\n\n"
        "```python\n"
        "def compute_score(query: str, doc_text: str) -> float:\n"
        "    # Count occurrences\n"
        "    count = doc_text.count(query)\n"
        "    return float(count * 1.5)\n"
        "```\n\n"
        "End of code."
    )
    input_file = tmp_path / "dev_guide.txt"
    input_file.write_text(txt_content, encoding="utf-8")
    output_dir = tmp_path / "generated"

    convert_file(input_file, tmp_path, output_dir, sample_config, mirror=True)
    okf_file = output_dir / "dev_guide.yaml"
    content = okf_file.read_text(encoding="utf-8")

    assert "```python" in content
    assert "def compute_score(query: str, doc_text: str) -> float:" in content
    assert "    count = doc_text.count(query)" in content
    assert "```" in content


def test_mixed_document_structure(tmp_path, sample_config):
    """Test a complex mixed document with headings, tables, lists, code, and links."""
    txt_content = (
        "# Enterprise Integration Manual\n\n"
        "## 1. Overview\n"
        "For documentation, see [Official Docs](https://example.com/docs).\n\n"
        "## 2. Supported Protocols\n"
        "- REST / HTTP\n"
        "- MCP (Model Context Protocol)\n\n"
        "## 3. Configuration Table\n"
        "| Key | Default | Description |\n"
        "| :--- | :--- | :--- |\n"
        "| port | 8000 | Server listening port |\n"
        "| host | 0.0.0.0 | Server host |\n\n"
        "## 4. Sample Request\n"
        "```bash\n"
        "curl -X GET http://localhost:8000/documents\n"
        "```"
    )
    input_file = tmp_path / "integration_manual.txt"
    input_file.write_text(txt_content, encoding="utf-8")
    output_dir = tmp_path / "generated"

    convert_file(input_file, tmp_path, output_dir, sample_config, mirror=True)
    okf_file = output_dir / "integration_manual.yaml"
    content = okf_file.read_text(encoding="utf-8")

    assert "# Enterprise Integration Manual" in content
    assert "[Official Docs](https://example.com/docs)" in content
    assert "- REST / HTTP" in content
    assert "| port | 8000 | Server listening port |" in content
    assert "curl -X GET http://localhost:8000/documents" in content


def test_metadata_generation(tmp_path, sample_config):
    """Test that standardized YAML frontmatter contains all required metadata fields without semantic hallucination."""
    txt_content = "Security Guidelines\n\nKeep all secrets secure."
    input_file = tmp_path / "security" / "access_policy.txt"
    input_file.parent.mkdir(parents=True, exist_ok=True)
    input_file.write_text(txt_content, encoding="utf-8")
    output_dir = tmp_path / "generated"

    convert_file(input_file, tmp_path, output_dir, sample_config, mirror=True)
    okf_file = output_dir / "security" / "access_policy.yaml"
    assert okf_file.exists()

    raw_text = okf_file.read_text(encoding="utf-8")
    parts = raw_text.split("---")
    assert len(parts) >= 3
    frontmatter = yaml.safe_load(parts[1])

    # Validate standard fields
    assert frontmatter["document_id"] == "security-access-policy"
    assert frontmatter["title"] == "Security Guidelines"
    assert frontmatter["author"] == "unknown"
    assert "created_at" in frontmatter
    assert "updated_at" in frontmatter
    assert frontmatter["source_path"] == "security/access_policy.txt"
    assert frontmatter["source_type"] == "text"
    assert "security" in frontmatter["tags"]
    assert "compliance" in frontmatter["tags"]

    # Verify semantic enrichment fields are NOT present
    for forbidden_key in ["domain", "topic", "audience", "concept", "summary", "entities", "semantic_tags"]:
        assert forbidden_key not in frontmatter


def test_document_id_consistency_with_repository(tmp_path, sample_config):
    """Test that document_id generated in OKF frontmatter matches OKFDocumentRepository get_document lookup."""
    txt_content = "Procurement Guidelines\n\nStandard procurement process."
    input_file = tmp_path / "finance" / "procurement_policy.txt"
    input_file.parent.mkdir(parents=True, exist_ok=True)
    input_file.write_text(txt_content, encoding="utf-8")
    output_dir = tmp_path / "generated"

    convert_file(input_file, tmp_path, output_dir, sample_config, mirror=True)

    expected_doc_id = "finance-procurement-policy"
    repo = OKFDocumentRepository(okf_dir=output_dir)
    doc_record = repo.get_document(expected_doc_id)

    assert doc_record is not None
    assert doc_record.document_id == expected_doc_id
    assert doc_record.title == "Procurement Guidelines"
    assert doc_record.source_path == "finance/procurement_policy.txt"
    assert "finance" in doc_record.tags
    assert "# Procurement Guidelines" in doc_record.content
