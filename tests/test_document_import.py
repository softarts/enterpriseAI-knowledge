from pathlib import Path

from document_import import DocumentImportService


def test_document_import_service_returns_and_persists_okf(tmp_path: Path):
    source = tmp_path / "source.txt"
    source.write_text("Document title\n\nBody text", encoding="utf-8")
    output = tmp_path / "import_data" / "okf"
    result = DocumentImportService().convert(source, output_dir=output)
    assert result.output_path is not None
    assert result.output_path.suffix == ".yaml"
    assert result.output_path.exists()
    assert result.okf_content.startswith("---\n")
    assert "# Document title" in result.okf_content
