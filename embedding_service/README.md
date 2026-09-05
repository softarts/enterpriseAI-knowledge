# Embedding Service

`embedding_service` is a model-independent local embedding pipeline:

```text
OKF document -> Markdown chunks -> configured Embedder -> JSON records -> cosine search
```

The root package contains the common protocol, registry, chunker, pipeline,
storage and search code. Model behavior is isolated in `bge_m3/` and
`minilm/`.

## Chunking

Chunking is Markdown-first and deterministic. Markdown headings are parsed to
build a section hierarchy. Each emitted chunk retains a `heading_path`, while
heading lines themselves are metadata and are not included in `content`. Text
before the first heading is a separate root section. Empty sections are
skipped; short sections are kept intact rather than being padded or forcibly
split. Content is never merged across heading-section boundaries.

The normal limits are target 700 tokens, minimum 150, and maximum 1100. The
minimum is a quality threshold; short content is still emitted when it is the
complete natural section. A section is split only when it exceeds the maximum.
The fallback order is paragraph, sentence, then token-level splitting. Token
counting defaults to a deterministic model-neutral lexical counter; callers
may inject a tokenizer/counter without changing the core algorithm.

Oversized sections are packed toward the target and use approximately 12%
overlap. Overlap is only used inside fallback splitting because short natural
sections should remain complete and overlap must never cross a heading. The
fallback uses source spans directly, so repeated text does not cause
`text.find()` offset errors. Offsets are `(start, end)` character positions in
the original Markdown `content`, and `content == original[start:end]` after
section trimming. Chunk order and IDs are deterministic. IDs hash document ID,
version, section path, source span, content hash and chunk version, so changing
the document version cannot collide with the previous version.

Each chunk includes `chunk_id`, `document_id`, `version`, `chunk_index`,
`heading_path`, `content`, `content_hash`, `source_path`, `token_count`,
`chunk_version`, and `offsets`.

## Embedding implementations

The common `Embedder` protocol requires `embed_documents(...)` and
`embed_query(...)`, and exposes `model_name`, `dimension`, and
`normalize_embeddings`. `get_embedder()` uses the registry to select a model;
the pipeline only calls the protocol and does not contain model-specific
encoding branches.

The default is `bge_m3`, implemented in `embedding_service/bge_m3/embedder.py`,
using model `BAAI/bge-m3`, dimension 1024, and normalization enabled. MiniLM
is implemented in `embedding_service/minilm/embedder.py`, using the existing
model name `all-MiniLM-L6-v2`, dimension 384, and normalization enabled. Both
implementations load `sentence-transformers` lazily and pass the configured
normalization and batch size to `encode`.

Embedding input is constructed by the common pipeline from the title, the
full heading path joined with ` > `, and the content:

```text
title + "\n" + " > ".join(heading_path) + "\n" + content
```

The default batch size is 32. The pipeline validates every returned vector
against the selected embedder dimension before creating an `EmbeddedChunk`.
Records also store the model identifier, actual vector dimension, and
normalization flag.

Select a model with `EMBEDDING_MODEL=minilm`, `get_embedder("minilm")`, or the
CLI option `--model minilm`. The importer writes new default output under
`embedding/<model>/`; an explicitly supplied output directory is respected.
Model-specific vector collections are not implemented inside this package;
the optional legacy `--vector-db` path still delegates to the external
`vector_service` and is not changed here.

## JSON storage and compatibility

JSON is an array of records, one mirrored file per source document. New files
contain the complete metadata listed above. Loading accepts old records that
only contain the original fields; missing newer fields use empty/neutral
defaults and no original metadata is fabricated. Existing JSON files and data
are not deleted.

## Commands and tests

```bash
python3 embedding_service/main_import.py --model bge_m3
python3 embedding_service/main_import.py --model minilm
python3 embedding_service/validate.py
python3 -m pytest -q tests/test_embedding_service.py tests/test_embedding_import.py
```

The unit tests inject fake models and token counters where appropriate, so
basic verification does not download either embedding model.
