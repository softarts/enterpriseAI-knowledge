"""Pipeline service for converting raw documents to OKF."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from .converter import convert_path
from .converter import load_config


@dataclass(frozen=True)
class ConversionResult:
    document_id: str
    source_path: Path
    output_path: Optional[Path]
    okf_content: str


class DocumentImportService:
    """Convert raw files to OKF in memory and optionally persist the result."""

    def __init__(self, config_path: Optional[Path] = None, config: Optional[Dict[str, Any]] = None):
        self.config = config or load_config(str(config_path or Path("doc_to_okf_config.yaml")))

    def convert(self, source_path: Path, output_dir: Optional[Path] = None,
                input_root: Optional[Path] = None, mirror: bool = True) -> ConversionResult:
        source_path = Path(source_path)
        root = Path(input_root or source_path.parent)
        okf = convert_path(source_path, root, self.config, mirror=mirror)
        document_id = self._document_id(source_path, root, mirror)
        output_path = None
        if output_dir is not None:
            relative = source_path.relative_to(root) if mirror and source_path.is_relative_to(root) else Path(source_path.name)
            output_path = (Path(output_dir) / relative).with_suffix(".yaml")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(okf, encoding="utf-8")
        return ConversionResult(document_id, source_path, output_path, okf)

    @staticmethod
    def _document_id(source_path: Path, root: Path, mirror: bool) -> str:
        relative = source_path.relative_to(root) if mirror and source_path.is_relative_to(root) else Path(source_path.name)
        return relative.with_suffix("").as_posix().replace("/", "-").replace("_", "-").lower()

    def convert_bytes(self, filename: str, data: bytes, work_dir: Path) -> ConversionResult:
        work_dir.mkdir(parents=True, exist_ok=True)
        source = work_dir / Path(filename).name
        source.write_bytes(data)
        try:
            return self.convert(source, input_root=work_dir, mirror=True)
        finally:
            if source.exists():
                source.unlink()
