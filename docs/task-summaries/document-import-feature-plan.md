# Document Import Feature — Task Prompt & Implementation Plan

> Status: **Backend implemented (verification paused mid-way). UI not started.**
> Saved to continue later. Date: 2026-08-31.

This document captures (1) the agreed scope/decisions, (2) the backend
implementation already done in `chat_service`, (3) verification status, and
(4) the frontend plan not yet started.

---

## 1. Confirmed scope & decisions

Two-phase feature: **Backend first, then UI.** MVP only.

### Locked decisions (from the user)
1. **Backend location:** `chat_service/` (not doc_service).
2. **No auth / no login** — no user model, no permission checks.
3. **Synchronous, single file** — upload → parse → classify → return in one
   request. No async jobs, no batch upload in this phase.
4. **SQLite lives in `chat_service`** — raw `sqlite3` (no ORM/SQLAlchemy),
   matching the style of `kb_classifier/common/vector_store.py`.
5. **No manual correction / no new taxonomy** — the confirm endpoint is
   "confirm-to-proceed" only; it accepts the automatic classification as-is.
   `classification_source` is always `automatic` in this phase.
6. **No unit tests** this phase — code first.
7. **Do NOT convert to OKF** — store the **original file as-is**. `extract_text`
   is only used to feed the classifier; no `.yaml`/OKF output is written.
8. **Lazy-load** the `TaxonomyClassifier` singleton (first import request pays
   the model-load cost; app startup and `/api/chat` stay light).
9. **Confirm body is empty** (no payload; just finalizes what's stored).

### Explicit non-goals (do NOT implement)
ChromaDB, chunking, chunk embeddings, KB search, RAG, retrieval, taxonomy
algorithm changes, embedding algorithm changes, taxonomy editor, S3, testing,
async/background jobs, auth.

---

## 2. Codebase facts that shaped the design (ground truth)

- **Two FastAPI apps exist:** `doc_service` (read-only, port 8000; +MCP 8001) and
  `chat_service` (port 8100, has the only POST endpoint `/api/chat`).
  `embedding_service` / `vector_service` are libraries/CLIs, not web services.
- **No general DB layer anywhere.** The only sqlite is
  `kb_classifier/common/vector_store.py` — a bge-m3 vector cache (one
  `embeddings` table), NOT reusable for document metadata. Import metadata table
  is built from scratch.
- **No auth/user model anywhere.**
- **No file-upload handling anywhere;** `python-multipart` was not a dependency
  (now added).
- **Parsing to reuse:** `import_raw_doc_to_okf.py` (repo root, importable as a
  top-level module; `main()` is `__main__`-guarded). Functions:
  `detect_file_type(Path) -> Optional[str]`, `extract_text(Path, file_type) -> str`
  (PDF via pdfplumber, DOCX via python-docx, HTML via bs4, TXT/MD/RST plain),
  `extract_title(text, Path) -> str`. Heavy parser libs are lazy-imported inside
  each extractor and raise `ImportError` with install hints.
- **Classifier to reuse:** `kb_classifier/taxonomy_classifier/classify.py`
  - `TaxonomyClassifier()` — **expensive to construct** (bge-m3 model load +
    ~300 anchor embeddings); on CPU a single `classify_text` can take ~1–5 min.
  - `classify_text(title, body) -> Classification`.
  - `Classification.to_okf_metadata() -> dict` with keys:
    `classification_status` (ASSIGNED|PARTIAL|FALLBACK|UNKNOWN),
    `classification_depth`, `category_path_keys`, `category_path_names`,
    `category_breadcrumb`, `level_scores`, `l1_key/l2_key/l3_key`.
  - `PINNED_TAXONOMY_VERSION = 7`.
  - No existing singleton wiring — we add our own (lazy).
- **chat_service conventions:** hand-rolled `Settings` singleton
  (`chat_service/config.py`, env `CHAT_*`); routers under
  `chat_service/api/routes_*.py` included in `chat_service/main.py`; models in
  `chat_service/models.py`; CORS already configured for the Vite dev origin.

---

## 3. Backend — IMPLEMENTED

### Files added
| File | Purpose |
|---|---|
| `chat_service/import_db.py` | Raw sqlite3 `documents_import` table + CRUD (`ImportDB`). WAL mode. States: `pending` → `imported`. |
| `chat_service/import_storage.py` | `ImportStorage`: UUID sharding `int(md5(uuid))%256` → `documents/{shard}/{uuid}_{safe_filename}`; path-traversal-safe temp save + finalize move; `sanitize_filename`. Stores **original file as-is**. |
| `chat_service/services/import_service.py` | `ImportService` orchestration: validate → save temp → `extract_text` (reuse) → lazy `TaxonomyClassifier.classify_text` → persist pending row → `confirm` moves temp→permanent. `ImportError_` domain error with stable `code`. |
| `chat_service/api/routes_import.py` | 4 endpoints (below) + module-level `ImportService` singleton + error-code→HTTP mapping + record→response mapper. |

### Files modified
| File | Change |
|---|---|
| `chat_service/config.py` | Added import settings: `import_db_path`, `import_storage_dir`, `import_temp_dir`, `import_max_bytes` (`CHAT_IMPORT_MAX_MB`, default 25), `import_allowed_extensions` (.pdf/.docx/.doc/.html/.htm/.txt/.md/.rst). Root default: `chat_service/import_data/`. |
| `chat_service/models.py` | Added `ClassificationView`, `ImportDocumentResponse`, `TaxonomyNode`, `TaxonomyResponse`, `ImportErrorResponse`. |
| `chat_service/main.py` | `include_router(import_router, tags=["Document Import"])`. |
| `requirements.txt` | Added `python-multipart>=0.0.9`. |

### Endpoints
- `POST /api/documents/import` — multipart `file=<upload>`. Validates size/ext,
  saves original to temp, parses, classifies, inserts `pending` row, returns
  `ImportDocumentResponse`. **Synchronous** (blocks during classification).
- `GET /api/documents/import/{doc_id}` — fetch current record.
- `POST /api/documents/import/{doc_id}/confirm` — **empty body**; moves temp file
  → permanent sharded storage, sets state `imported`. 409 if already imported.
- `GET /api/taxonomy` — read-only taxonomy tree (pinned v7) for display. No edit.

### `documents_import` table columns
`id (uuid PK)`, `original_filename`, `storage_path` (null until confirm),
`import_state` (pending|imported), `taxonomy_version` (e.g. "v7"),
`category_level_1/2/3`, `classification_status` (classified|unknown — simplified),
`classification_source` (automatic), `raw_status` (ASSIGNED|PARTIAL|FALLBACK|UNKNOWN),
`created_at`, `updated_at`.

Status mapping: raw `ASSIGNED/PARTIAL/FALLBACK` → `classified`; `UNKNOWN` → `unknown`.

### Error codes (stable envelope `{code, message}`)
`UPLOAD_FAILED` (400), `PARSING_FAILED` (422), `CLASSIFICATION_FAILED` (500),
`CONFIRMATION_FAILED` (409), `STORAGE_FAILED` (500), `NOT_FOUND` (404).
No stack traces / internals exposed.

---

## 4. Verification status

**Done (passing):**
- `python-multipart` installed (0.0.32).
- Syntax check: all new/modified files OK.
- Fast smoke via `TestClient` (no classifier):
  - `GET /api/taxonomy` → 200, `version v7`, 17 L1 nodes.
  - `GET /api/documents/import/{missing}` → 404 `NOT_FOUND`.
  - `POST .../{missing}/confirm` → 404 `NOT_FOUND`.
  - `POST /api/documents/import` with `.exe` → 400 `UPLOAD_FAILED`
    (validation before classifier load — good).

**NOT yet done (paused here):**
- **Full end-to-end import→classify→confirm** with a real `.txt` (triggers the
  slow classifier). A smoke script was written but the run was stopped.
  - **TODO next session:** run a full import of a small text file, confirm it,
    and verify: response shape, DB row transitions pending→imported, and the
    file physically lands at
    `chat_service/import_data/storage/documents/{shard}/{uuid}_{name}`.
    Also verify double-confirm → 409, and an `UNKNOWN` document imports with
    `classification=null`, `status="unknown"`.

**Also consider:** add `chat_service/import_data/` to `.gitignore` (uploaded
files + sqlite should not be committed).

---

## 5. Frontend — NOT STARTED (plan)

Target stack = the **only** existing frontend: `chat_service/frontend/`
(React + Vite + plain `fetch` + component `useState`; no router, no UI kit,
no state-management lib). Do NOT introduce new frameworks.

### Scope
`Upload → Processing status → Classification result → Confirm import → Success/Error`.
Single file per the backend phase (UI may still show a list/cards, but each
import call is one file). No manual correction UI (backend doesn't support it).

### Planned components (under `chat_service/frontend/src/`)
- A new **Import view** + a lightweight view switch (Chat ↔ Import) instead of a
  router (avoid adding react-router).
- `ImportPage.jsx` — page shell + header.
- `UploadArea.jsx` — drag & drop + file picker (PDF/DOCX/TXT/Markdown).
- `DocumentCard.jsx` — filename, size, processing status, classification
  breadcrumb, confirm action.
- `ClassificationBreadcrumb.jsx` — `A › B › C`; special-case `UNKNOWN`
  ("暂未确定分类") as a valid state (not a normal classification).
- `importApi.js` — `POST /api/documents/import` (FormData), `GET
  /api/documents/import/{id}`, `POST /api/documents/import/{id}/confirm`,
  `GET /api/taxonomy` (for display only).

### UI states (map to backend)
`uploading → (server) classifying → classified | unknown → confirming →
imported`; plus `failed` from error responses. Because the backend is
**synchronous**, the `POST /import` call itself will block during
classification — show a "分析中…" state on that pending promise (can take
minutes on CPU). No polling needed in this phase (sync), though a `GET` is
available.

### Rules
- Frontend does NO classification/embedding/chunking/search/Chroma.
- Taxonomy (for display) comes from `GET /api/taxonomy` — never hard-coded.
- `UNKNOWN` shown as a legitimate state; user can still confirm/import it.
- Don't surface `storage_path` as primary UI info.
- Keep chat_service's existing visual style; simple cards + breadcrumb + clear
  status colors; no heavy animation/gradient.

### Frontend contract (from implemented backend)
`ImportDocumentResponse`:
```json
{
  "id": "uuid",
  "filename": "runbook.txt",
  "import_state": "pending | imported",
  "status": "classified | unknown",
  "classification": {
    "level_1": "Technology & Engineering",
    "level_2": "Site Reliability & Observability",
    "level_3": "Alerting & On-Call Rotation",
    "breadcrumb": "Technology & Engineering > Site Reliability & Observability > Alerting & On-Call Rotation"
  } | null,
  "taxonomy_version": "v7",
  "storage_path": "documents/137/{uuid}_runbook.txt | null",
  "created_at": "...",
  "updated_at": "..."
}
```
Errors: HTTP status + `{"detail": {"code": "...", "message": "..."}}`.

---

## 6. How to resume

1. (Backend) Run the full end-to-end smoke (import a small `.txt`, confirm,
   verify file on disk + DB state + 409 double-confirm + UNKNOWN path).
2. Add `chat_service/import_data/` to `.gitignore`.
3. Start the frontend per §5.
4. Manual run: `python -m chat_service.run` (or
   `uvicorn chat_service.main:app --port 8100`); Swagger at
   `http://localhost:8100/docs` to exercise the import endpoints.
