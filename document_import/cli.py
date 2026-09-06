"""CLI wrapper for raw document conversion."""

import argparse
from pathlib import Path

from .service import DocumentImportService


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert raw documents to OKF")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--config", default="doc_to_okf_config.yaml")
    args = parser.parse_args()
    source = Path(args.input).resolve()
    root = source if source.is_dir() else source.parent
    service = DocumentImportService(Path(args.config))
    files = [source] if source.is_file() else sorted(p for p in source.rglob("*") if p.is_file())
    converted = 0
    for path in files:
        try:
            service.convert(path, Path(args.output), root, mirror=True)
            converted += 1
        except ValueError:
            continue
    print(f"Converted {converted} document(s) to {Path(args.output).resolve()}")


if __name__ == "__main__":
    main()
