# Evaluation Source Manifest and Server-side Import

## Scope

This change extracts the unique source files referenced by
`embedding_service/evaluation/evaluation_queries.json` and provides a server-local CLI
that creates the existing asynchronous batch-import task. The browser UI is not used for
these files.

## Completed

- Generated `embedding_service/evaluation/evaluation_sources.json`.
- The manifest contains 20 queries mapped to 8 unique source files.
- Added `document_import.evaluation_manifest` to rebuild and validate the manifest.
- Added `chat_service.server_import_cli` to validate server-local files and create a normal
  `import_tasks` task through `BatchImportService`.
- Added `BatchImportService.create_task_from_paths()`; the existing worker and task tables
  remain the processing path.
- Tasks page labels are English.
- Existing SHA-256 content deduplication applies to CLI imports as well as UI imports.

Relevant implementation size at completion: `evaluation_manifest.py` 78 lines,
`server_import_cli.py` 61 lines, `batch_import_service.py` 225 lines, and the Tasks page
107 lines. These counts include comments and docstrings.

## Flow

```text
evaluation_queries.json
  -> unique expected_source_path values
  -> evaluation_sources.json
  -> server_import_cli --source-root all_documents
  -> import_tasks / import_task_files
  -> existing batch worker
  -> OKF -> taxonomy -> BGE-M3 -> okf_chunks_bge_m3
```

## Commands

```bash
python -m document_import.evaluation_manifest \
  --queries embedding_service/evaluation/evaluation_queries.json \
  --source-root all_documents \
  --output embedding_service/evaluation/evaluation_sources.json
```

```bash
python -m chat_service.server_import_cli \
  --manifest embedding_service/evaluation/evaluation_sources.json \
  --source-root all_documents
```

Use `--dry-run` on the server CLI to validate source files without creating a task.

## Safety and boundaries

The CLI accepts a source root explicitly, rejects absolute paths and `..` traversal, checks
allowed extensions, and verifies file size and existence. It does not expose a new HTTP
endpoint for arbitrary server paths. It does not modify taxonomy, `vector_service`,
`doc_service`, MCP, or other external services.

## Not implemented

Document lineage is intentionally not implemented. Content changes continue to create a
new import identity and independent chunks; future lineage metadata and current-version
retrieval filters require a separate design.

## Verification

- Manifest validation: 20 queries and 8 source files.
- Server CLI dry-run: source-root and file validation path exercised.
- Python compile check passed.
- Frontend production build passed.
- Existing pytest command was unavailable in the environment, so no pytest suite was run.
