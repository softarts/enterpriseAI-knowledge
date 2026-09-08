"""Persistent batch import orchestration and worker entry points."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from chat_service.config import settings
from chat_service.import_db import ImportDB
from chat_service.import_storage import sanitize_filename
from document_import import parse_okf_file, set_okf_document_id


class BatchImportService:
    """Creates/query tasks; actual processing runs in a separate worker process."""

    def __init__(self) -> None:
        self.db = ImportDB(settings.import_db_path)

    def create_task(self, files: Iterable[tuple[str, str, bytes]]) -> Dict[str, Any]:
        task_id = str(uuid.uuid4())
        items = list(files)
        if not items:
            raise ValueError("at least one file is required")
        self.db.create_task(task_id, len(items))
        task_root = settings.import_temp_dir / "tasks" / task_id
        seen_hashes: dict[str, str] = {}
        duplicate_count = 0
        for relative_path, original_name, data in items:
            safe_relative = self._safe_relative_path(relative_path, original_name)
            target = task_root / safe_relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            content_hash = hashlib.sha256(data).hexdigest()
            existing = self.db.find_by_content_hash(content_hash)
            duplicate_of = existing["id"] if existing else seen_hashes.get(content_hash)
            document_id = content_hash
            file_id = str(uuid.uuid4())
            if duplicate_of:
                duplicate_count += 1
            else:
                seen_hashes[content_hash] = document_id
            self.db.add_task_file({
                "file_id": file_id, "task_id": task_id, "document_id": document_id,
                "relative_path": relative_path or original_name,
                "original_filename": sanitize_filename(original_name),
                "temp_path": str(target),
                "status": "duplicate" if duplicate_of else "uploaded",
                "content_hash": content_hash,
                "dedup_status": "duplicate" if duplicate_of else "new",
                "duplicate_of": duplicate_of,
            })
        self.db.update_task(task_id, {
            "status": "queued", "stage": "upload", "uploaded_files": len(items),
            "processed_files": duplicate_count,
        })
        self.start_worker(task_id)
        return self.detail(task_id)

    def create_task_from_paths(self, files: Iterable[tuple[str, Path]]) -> Dict[str, Any]:
        """Create the same task as the UI upload, using server-local files."""
        items = []
        for relative_path, source_path in files:
            source = Path(source_path)
            if not source.is_file():
                raise ValueError(f"source file does not exist: {source}")
            items.append((relative_path, source.name, source.read_bytes()))
        return self.create_task(items)

    @staticmethod
    def _safe_relative_path(relative_path: str, original_name: str) -> Path:
        raw = Path(relative_path or original_name)
        parts = [sanitize_filename(part) for part in raw.parts if part not in ("", ".", "..")]
        if not parts:
            parts = [sanitize_filename(original_name)]
        return Path(*parts)

    def start_worker(self, task_id: str) -> None:
        env = os.environ.copy()
        subprocess.Popen(
            [sys.executable, "-m", "chat_service.batch_worker", "--task-id", task_id],
            cwd=str(Path(__file__).resolve().parents[2]),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def detail(self, task_id: str) -> Dict[str, Any]:
        task = self.db.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        files = self.db.get_task_files(task_id)
        total = task["total_files"] or 1
        task["progress_percent"] = round(task["processed_files"] * 100 / total, 1)
        task["files"] = files
        return task

    def list(self, limit: int = 100) -> List[Dict[str, Any]]:
        return [self._summary(task) for task in self.db.list_tasks(limit)]

    @staticmethod
    def _summary(task: Dict[str, Any]) -> Dict[str, Any]:
        total = task["total_files"] or 1
        return {**task, "progress_percent": round(task["processed_files"] * 100 / total, 1)}

    def retry_failed(self, task_id: str) -> Dict[str, Any]:
        task = self.db.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        files = self.db.get_task_files(task_id)
        failed = [f for f in files if f["status"] == "failed"]
        if not failed:
            return self.detail(task_id)
        for item in failed:
            self.db.update_task_file(item["file_id"], {"status": "uploaded", "error": None,
                                                        "retry_count": item["retry_count"] + 1})
        self.db.update_task(task_id, {"status": "queued", "stage": "processing", "error": None})
        self.start_worker(task_id)
        return self.detail(task_id)


class BatchImportWorker:
    """Single-process worker. It is intentionally restartable and queue-free."""

    def __init__(self) -> None:
        self.db = ImportDB(settings.import_db_path)

    def run(self, task_id: str) -> None:
        task = self.db.get_task(task_id)
        if task is None:
            raise ValueError(f"unknown task: {task_id}")
        from chat_service.services.import_service import ImportService
        from document_import import DocumentImportService
        from embedding_service.pipeline import EmbeddingPipelineService
        from vector_service.chroma_store import ChromaStore

        importer = DocumentImportService()
        classifier_service = ImportService()
        pipeline = EmbeddingPipelineService(model="bge_m3", vector_store=ChromaStore(model="bge_m3"))
        self.db.update_task(task_id, {"status": "running", "stage": "processing", "started_at": self._now()})
        files = self.db.get_task_files(task_id)
        for item in files:
            if item["status"] in ("completed", "duplicate"):
                continue
            try:
                self._process_file(item, importer, classifier_service, pipeline)
                self.db.update_task_file(item["file_id"], {
                    "status": "completed", "dedup_status": "completed", "error": None,
                })
            except Exception as exc:  # one bad file must not stop the batch
                self.db.update_task_file(item["file_id"], {"status": "failed", "error": str(exc)})
            self._update_progress(task_id)
        self._update_progress(task_id, finish=True)

    def _process_file(self, item: Dict[str, Any], importer: Any, classifier_service: Any, pipeline: Any) -> None:
        raw_path = Path(item["temp_path"])
        if not raw_path.exists():
            raise FileNotFoundError(raw_path)
        result = importer.convert(raw_path, input_root=raw_path.parent)
        okf_path = raw_path.with_suffix(".yaml")
        document_id = item.get("document_id") or item["file_id"]
        okf_content = set_okf_document_id(result.okf_content, document_id)
        okf_path.write_text(okf_content, encoding="utf-8")
        self.db.update_task_file(item["file_id"], {"status": "converting", "okf_path": str(okf_path)})
        title, body = classifier_service._extract_text(raw_path)
        classification = classifier_service._get_classifier().classify_text(title, body)
        metadata = classification.to_okf_metadata()
        names = metadata.get("category_path_names") or []
        self.db.update_task_file(item["file_id"], {
            "status": "embedding", "classification_status": metadata.get("classification_status"),
            "taxonomy_version": getattr(classifier_service, "_taxonomy_version", None),
            "category_level_1": names[0] if len(names) > 0 else None,
            "category_level_2": names[1] if len(names) > 1 else None,
            "category_level_3": names[2] if len(names) > 2 else None,
            "level_scores": json.dumps(metadata.get("level_scores")) if metadata.get("level_scores") else None,
        })
        pipeline.process_okf_file(okf_path)
        safe_relative = BatchImportService._safe_relative_path(item["relative_path"], item["original_filename"])
        final_path = settings.import_storage_dir / "tasks" / item["task_id"] / safe_relative.with_suffix(".yaml")
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.replace(final_path) if final_path == okf_path else okf_path.replace(final_path)
        relative = final_path.relative_to(settings.import_storage_dir).as_posix()
        document = parse_okf_file(final_path)
        self.db.insert({
            "id": document.document_id,
            "original_filename": item["original_filename"],
            "stored_filename": final_path.name,
            "storage_path": relative,
            "import_state": "imported",
            "taxonomy_version": getattr(classifier_service, "_taxonomy_version", None),
            "category_level_1": names[0] if len(names) > 0 else None,
            "category_level_2": names[1] if len(names) > 1 else None,
            "category_level_3": names[2] if len(names) > 2 else None,
            "classification_status": "classified" if metadata.get("classification_status") else "unknown",
            "classification_source": "automatic",
            "raw_status": metadata.get("classification_status"),
            "level_scores": json.dumps(metadata.get("level_scores")) if metadata.get("level_scores") else None,
            "document_body": document.content,
            "file_size": raw_path.stat().st_size,
            "content_hash": item.get("content_hash"),
            "source": "batch",
        })
        self.db.update_task_file(item["file_id"], {
            "status": "completed", "dedup_status": "completed",
            "storage_path": relative, "okf_path": str(final_path),
        })

    def _update_progress(self, task_id: str, finish: bool = False) -> None:
        files = self.db.get_task_files(task_id)
        processed = sum(f["status"] in ("completed", "failed", "duplicate") for f in files)
        failed = sum(f["status"] == "failed" for f in files)
        fields: Dict[str, Any] = {"processed_files": processed, "failed_files": failed}
        if finish or processed == len(files):
            fields.update({"status": "completed", "stage": "complete", "completed_at": self._now()})
        self.db.update_task(task_id, fields)

    @staticmethod
    def _now() -> str:
        import time
        return time.strftime("%Y-%m-%dT%H:%M:%S")
