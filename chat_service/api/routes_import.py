"""
Document Import API routes (MVP: single file, synchronous, no auth).

Endpoints:
    POST /api/documents/import              - upload one file, parse, classify,
                                              persist a pending record, return it.
    GET  /api/documents/import/{id}         - fetch a single import record.
    POST /api/documents/import/{id}/confirm - finalize (move file to permanent
                                              storage); confirm-to-proceed only,
                                              no classification changes.
    GET  /api/taxonomy                      - read-only taxonomy tree (display).

Errors are returned with a stable {code, message} envelope and an appropriate
HTTP status. Internal details / stack traces are never exposed.
"""

from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import APIRouter, File, HTTPException, UploadFile

from chat_service.import_db import CLS_UNKNOWN, STATE_IMPORTED
from chat_service.models import (
    ClassificationView,
    ImportDocumentResponse,
    TaxonomyNode,
    TaxonomyResponse,
)
from chat_service.services.import_service import ImportError_, ImportService

router = APIRouter()

# One shared service instance. Heavy deps (classifier + bge-m3) load lazily on
# the first import request, so this does not slow app startup or /api/chat.
_import_service = ImportService()

# Map domain error codes -> HTTP status.
_STATUS_FOR_CODE = {
    "UPLOAD_FAILED": 400,
    "PARSING_FAILED": 422,
    "CLASSIFICATION_FAILED": 500,
    "CONFIRMATION_FAILED": 409,
    "STORAGE_FAILED": 500,
    "DATABASE_FAILED": 500,
    "NOT_FOUND": 404,
}


def _fail(err: ImportError_) -> HTTPException:
    status = _STATUS_FOR_CODE.get(err.code, 500)
    return HTTPException(status_code=status, detail={"code": err.code, "message": err.message})


def _to_response(rec: Dict[str, Any]) -> ImportDocumentResponse:
    """Map a DB record dict to the API response model."""
    status = rec["classification_status"]
    classification = None
    if status != CLS_UNKNOWN:
        names = [rec.get("category_level_1"), rec.get("category_level_2"), rec.get("category_level_3")]
        present = [n for n in names if n]
        level_scores = None
        if rec.get("level_scores"):
            try:
                level_scores = json.loads(rec["level_scores"])
            except (json.JSONDecodeError, TypeError):
                level_scores = None
        classification = ClassificationView(
            level_1=rec.get("category_level_1"),
            level_2=rec.get("category_level_2"),
            level_3=rec.get("category_level_3"),
            breadcrumb=" > ".join(present),
            level_scores=level_scores,
        )
    return ImportDocumentResponse(
        id=rec["id"],
        filename=rec["original_filename"],
        import_state=rec["import_state"],
        status=status,
        classification=classification,
        taxonomy_version=rec.get("taxonomy_version"),
        storage_path=rec.get("storage_path"),
        document_body=rec.get("document_body"),
        created_at=rec.get("created_at"),
        updated_at=rec.get("updated_at"),
    )


@router.post("/api/documents/import", response_model=ImportDocumentResponse)
async def import_document(file: UploadFile = File(...)) -> ImportDocumentResponse:
    """Upload a single document, classify it, and store a pending record.

    The file is NOT yet moved to permanent storage; call the confirm endpoint to
    finalize. This is synchronous: the response returns after classification,
    which can take a while on CPU.
    """
    try:
        data = await file.read()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail={"code": "UPLOAD_FAILED",
                                                     "message": f"could not read upload: {exc}"})
    try:
        rec = _import_service.import_file(file.filename or "file", data)
    except ImportError_ as err:
        raise _fail(err)
    return _to_response(rec)


@router.get("/api/documents/import/{doc_id}", response_model=ImportDocumentResponse)
def get_import(doc_id: str) -> ImportDocumentResponse:
    """Fetch the current record for an import."""
    rec = _import_service.get(doc_id)
    if rec is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND",
                                                     "message": f"import '{doc_id}' not found"})
    return _to_response(rec)


@router.post("/api/documents/import/{doc_id}/confirm", response_model=ImportDocumentResponse)
def confirm_import(doc_id: str) -> ImportDocumentResponse:
    """Confirm-to-proceed: finalize the pending import into permanent storage.

    Takes no body — this phase does not support manual re-classification; it
    accepts the automatic classification as-is.
    """
    try:
        rec = _import_service.confirm(doc_id)
    except ImportError_ as err:
        raise _fail(err)
    return _to_response(rec)


@router.get("/api/taxonomy", response_model=TaxonomyResponse)
def get_taxonomy() -> TaxonomyResponse:
    """Return the read-only taxonomy tree used for classification (for display).

    Loads the same pinned taxonomy the classifier uses. No editing in this phase.
    """
    from kb_classifier.config.taxonomy_current import load_current_taxonomy
    from kb_classifier.taxonomy_classifier.classify import PINNED_TAXONOMY_VERSION

    try:
        tax, _src = load_current_taxonomy(version=PINNED_TAXONOMY_VERSION)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail={"code": "TAXONOMY_FAILED",
                                                     "message": f"could not load taxonomy: {exc}"})

    def build(node_map: Dict[str, Any]) -> list:
        out = []
        for key, spec in node_map.items():
            out.append(TaxonomyNode(
                key=key,
                name=spec.get("name", key),
                children=build(spec.get("children", {}) or {}),
            ))
        return out

    return TaxonomyResponse(
        taxonomy_version=f"v{PINNED_TAXONOMY_VERSION}",
        nodes=build(tax),
    )
