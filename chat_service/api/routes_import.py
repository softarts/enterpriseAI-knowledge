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

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from chat_service.import_db import CLS_UNKNOWN, STATE_IMPORTED
from chat_service.models import (
    ClassificationView,
    DocumentListResponse,
    DocumentPreviewResponse,
    DocumentSummary,
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


def _to_classification(rec: Dict[str, Any]) -> ClassificationView | None:
    if rec["classification_status"] == CLS_UNKNOWN:
        return None
    names = [rec.get("category_level_1"), rec.get("category_level_2"), rec.get("category_level_3")]
    present = [n for n in names if n]
    level_scores = None
    if rec.get("level_scores"):
        try:
            level_scores = json.loads(rec["level_scores"])
        except (json.JSONDecodeError, TypeError):
            level_scores = None
    return ClassificationView(
        level_1=rec.get("category_level_1"),
        level_2=rec.get("category_level_2"),
        level_3=rec.get("category_level_3"),
        breadcrumb=" > ".join(present),
        level_scores=level_scores,
    )


def _to_response(rec: Dict[str, Any]) -> ImportDocumentResponse:
    """Map a DB record dict to the API response model."""
    return ImportDocumentResponse(
        id=rec["id"],
        filename=rec["original_filename"],
        import_state=rec["import_state"],
        status=rec["classification_status"],
        classification=_to_classification(rec),
        taxonomy_version=rec.get("taxonomy_version"),
        storage_path=rec.get("storage_path"),
        document_body=rec.get("document_body"),
        file_size=rec.get("file_size"),
        source=rec.get("source"),
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


@router.get("/api/documents", response_model=DocumentListResponse)
def list_documents(
    category_level_1: str | None = Query(None),
    category_level_2: str | None = Query(None),
    category_level_3: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> DocumentListResponse:
    """Paginated listing of imported documents, filterable by category path."""
    rows, total = _import_service.db.list_documents(
        category_level_1=category_level_1,
        category_level_2=category_level_2,
        category_level_3=category_level_3,
        import_state=STATE_IMPORTED,
        page=page,
        page_size=page_size,
    )
    items = [
        DocumentSummary(
            id=r["id"],
            filename=r["original_filename"],
            import_state=r["import_state"],
            status=r["classification_status"],
            classification=_to_classification(r),
            file_size=r.get("file_size"),
            source=r.get("source"),
            created_at=r.get("created_at"),
            updated_at=r.get("updated_at"),
        )
        for r in rows
    ]
    return DocumentListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/api/documents/{doc_id}/preview", response_model=DocumentPreviewResponse)
def preview_document(doc_id: str) -> DocumentPreviewResponse:
    """Full extracted text of one document (for preview; UI comes later)."""
    rec = _import_service.get(doc_id)
    if rec is None:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND",
                                                     "message": f"document '{doc_id}' not found"})
    return DocumentPreviewResponse(
        id=rec["id"],
        filename=rec["original_filename"],
        file_size=rec.get("file_size"),
        source=rec.get("source"),
        classification=_to_classification(rec),
        document_body=rec.get("document_body"),
        created_at=rec.get("created_at"),
        updated_at=rec.get("updated_at"),
    )


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

    counts = _import_service.db.count_by_l3(import_state=STATE_IMPORTED)

    def build(node_map: Dict[str, Any], path: tuple = ()) -> list:
        out = []
        for key, spec in node_map.items():
            children = build(spec.get("children", {}) or {}, path + (spec.get("name", key),))
            doc_count = 0 if children else counts.get(
                (path + (spec.get("name", key),) + (None, None))[:3], 0
            )
            out.append(TaxonomyNode(
                key=key,
                name=spec.get("name", key),
                children=children,
                document_count=doc_count,
            ))
        return out

    return TaxonomyResponse(
        taxonomy_version=f"v{PINNED_TAXONOMY_VERSION}",
        nodes=build(tax),
    )
