---
inclusion: auto
---

# Agent Working Rules for Enterprise Knowledge Base POC

## Rule: Follow the Architecture

The canonical system architecture is defined in `enterprise_kb_poc_system_architecture.md`.

- All implementation MUST conform to the architecture document unless the user explicitly requests a deviation.
- If a proposed change conflicts with the architecture, the agent MUST:
  1. Identify the conflict clearly.
  2. Explain why the deviation is needed.
  3. Wait for explicit user approval before proceeding.
- Do NOT silently override or ignore architectural decisions.

## Rule: Plan Before Code

Any implementation plan must be presented to the user and receive explicit approval before modifying or creating code files.

- Before writing or modifying any source code (`.py`, `.yaml`, `.json`, `.ts`, `.js`, etc.), the agent MUST first present a clear plan describing:
  - What files will be created or modified
  - The high-level structure and logic of each file
  - Any dependencies or libraries required
- The agent MUST wait for the user's explicit approval (e.g., "approved", "go ahead", "ok") before proceeding with implementation.
- Documentation and steering files (like this one) are exempt from this rule.
- If the user requests changes to the plan, the agent must revise and re-present for approval.

## Rule: Protect Existing Import System

The document ingestion pipeline (`import_raw_doc_to_okf.py`) is a completed upstream module.

- **DO NOT** modify `import_raw_doc_to_okf.py` unless the API layer absolutely cannot consume its output AND the agent has explained the reason and received explicit approval.
- **DO NOT** duplicate any parser logic (PDF, DOCX, HTML, TXT).
- **DO NOT** create a second OKF converter, metadata builder, or config loader.
- **DO NOT** change the format or structure of files in `generated/`.
- **DO NOT** modify `doc_to_okf_config.yaml` semantics.
- **DO NOT** modify existing CLI behavior.
- The API Service Layer is a **consumer** of existing OKF output, not a producer.

## Rule: Ask Don't Assume

When requirements are unclear or ambiguous:

- The agent MUST ask the user for clarification rather than making assumptions.
- This is especially important for:
  - Directory structure decisions when integrating with existing code
  - API behavior edge cases
  - Configuration choices
  - Any decision that could conflict with existing modules

## Rule: Incremental Development

- Work in phases aligned with the architecture document's implementation plan.
- Each phase should be independently verifiable before moving to the next.
- Do NOT implement future-phase features prematurely (e.g., no Vector DB, no RAG, no MCP in the current API phase).
- Design interfaces that accommodate future extensions without implementing them now.

## Rule: No Over-Engineering

The current phase prohibits:

- PostgreSQL, Redis, Kafka, Celery, Milvus, Elasticsearch
- Kubernetes, Docker Compose, Microservices
- Authentication, RBAC, Multi-tenancy
- API Gateway, Service Mesh

Keep the implementation minimal and focused on the current phase's goal.

## Rule: Raw Document Root Discovery, Mirrored Paths & Source Path Normalization

All raw document ingestion pipelines (including OKF conversion and Embedding generation) MUST adhere to unified path and metadata normalization rules:

1. **Raw Document Root Discovery**:
   - The system automatically detects root directory names from candidates in priority order: `all_documents`, `raw_documents`, `documents`.
   - When `--input` points to a single file or subdirectory inside one of these candidate folders (e.g. `all_documents/confluence/people-ops/xxx.txt`), the root prefix (`all_documents`) is stripped when determining relative mirror hierarchy.
2. **Mirror Hierarchy Preservation**:
   - Default output destinations (`generated/` for OKF, `embedding/` for Embeddings) MUST replicate the source subfolder hierarchy (e.g. `embedding/confluence/people-ops/xxx.json`).
   - If `--output <dir>` is explicitly specified by the user, files are output directly to the specified destination directory without automatic mirroring.
3. **Source Path Normalization**:
   - Metadata `source_path` in both OKF and Embedded Chunk records MUST be normalized relative to the raw document root (e.g. `confluence/people-ops/xxx.txt`), using forward slashes (`/`).
4. **Deterministic Document ID**:
   - `document_id` computation MUST follow the canonical rule: replace path separators/underscores with `-`, lowercase, strip leading/trailing hyphens, and collapse consecutive hyphens.

## Rule: Embedding Service Consumes OKF Only

- `embedding_service` (including `main_import.py`, `service.py`, `validate.py`) is an OKF-downstream consumer.
- The input to `embedding_service` MUST always be generated OKF documents (`.yaml` files under `generated/`).
- `main_import.py` is strictly prohibited from directly parsing or reading raw documents (TXT/PDF/DOCX/HTML).
- Raw document conversion is exclusively handled upstream by `import_raw_doc_to_okf.py`.
- Metadata fields (`source_path`, `document_id`, `title`, etc.) MUST be inherited directly from OKF frontmatter and NEVER re-derived from raw files.
- The destination `embedding/` directory mirrors the `generated/` subfolder hierarchy (e.g. `generated/confluence/.../xxx.yaml` -> `embedding/confluence/.../xxx.json`).

## Available Skills

The following skills can be loaded for detailed implementation guidance:

- `enterprise-kb-architecture` — Full system architecture overview and principles
- `api-service-layer` — Detailed API service layer implementation requirements, constraints, endpoint specs, and verification checklist

