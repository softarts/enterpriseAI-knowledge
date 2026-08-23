import json
from pathlib import Path
import pytest

from embedding_service.config import EMBEDDING_DIMENSION
from embedding_service.embedder import LocalEmbedder
from embedding_service.models import EmbeddedChunk
from embedding_service.search import cosine_similarity, search_by_similarity
from embedding_service.service import EmbeddingService
from embedding_service.storage import (
    load_all_embeddings,
    load_embeddings_from_json,
    save_embeddings_to_json,
)


def test_cosine_similarity():
    vec1 = [1.0, 0.0, 0.0]
    vec2 = [1.0, 0.0, 0.0]
    assert pytest.approx(cosine_similarity(vec1, vec2)) == 1.0

    vec_ortho = [0.0, 1.0, 0.0]
    assert pytest.approx(cosine_similarity(vec1, vec_ortho)) == 0.0

    vec_opposite = [-1.0, 0.0, 0.0]
    assert pytest.approx(cosine_similarity(vec1, vec_opposite)) == -1.0


def test_storage_save_and_load(tmp_path: Path):
    target_file = tmp_path / "sub" / "doc.json"
    chunks = [
        EmbeddedChunk(
            chunk_id="doc1-chunk-000",
            document_id="doc1",
            title="Sample Title",
            heading="Overview",
            content="Sample text body",
            source_path="raw/doc1.txt",
            embedding=[0.1, 0.2, 0.3],
        )
    ]

    save_embeddings_to_json(chunks, target_file)
    assert target_file.exists()

    loaded = load_embeddings_from_json(target_file)
    assert len(loaded) == 1
    assert loaded[0].chunk_id == "doc1-chunk-000"
    assert loaded[0].heading == "Overview"
    assert loaded[0].embedding == [0.1, 0.2, 0.3]

    all_loaded = load_all_embeddings(tmp_path)
    assert len(all_loaded) == 1


def test_local_embedder():
    embedder = LocalEmbedder()
    assert embedder.dimension == EMBEDDING_DIMENSION

    texts = ["Revenue recognition policy", "Procurement contracts"]
    embeddings = embedder.embed_texts(texts)

    assert len(embeddings) == 2
    assert len(embeddings[0]) == EMBEDDING_DIMENSION
    assert len(embeddings[1]) == EMBEDDING_DIMENSION

    query_emb = embedder.embed_query("Revenue policy")
    assert len(query_emb) == EMBEDDING_DIMENSION


def test_search_by_similarity():
    chunks = [
        EmbeddedChunk(
            chunk_id="chunk-finance",
            document_id="doc-finance",
            title="Finance Playbook",
            heading="Revenue Recognition",
            content="ASC 606 revenue recognition policy and rules",
            source_path="finance.txt",
            embedding=[1.0, 0.0, 0.0],
        ),
        EmbeddedChunk(
            chunk_id="chunk-security",
            document_id="doc-security",
            title="Security Policy",
            heading="Access Control",
            content="Password rotation and MFA requirements",
            source_path="security.txt",
            embedding=[0.0, 1.0, 0.0],
        ),
    ]

    query_vec = [0.9, 0.1, 0.0]
    results = search_by_similarity(query_vec, chunks, top_k=2)

    assert len(results) == 2
    assert results[0].chunk_id == "chunk-finance"
    assert results[0].score > results[1].score


def test_end_to_end_service(tmp_path: Path):
    # Setup dummy OKF
    okf_dir = tmp_path / "generated"
    okf_dir.mkdir()
    sample_okf = okf_dir / "test_doc.yaml"
    sample_okf.write_text(
        """---
title: Test Document
source_path: test.txt
---
# Test Document

## Section One
Content of section one with details.

## Section Two
Content of section two with more info.
""",
        encoding="utf-8",
    )

    embedding_dir = tmp_path / "embedding"
    service = EmbeddingService(okf_dir=okf_dir, embedding_dir=embedding_dir)

    persisted = service.embed_and_persist_all()
    assert len(persisted) >= 2

    mirrored_file = embedding_dir / "test_doc.json"
    assert mirrored_file.exists()

    reloaded = service.load_all_persisted_embeddings()
    assert len(reloaded) == len(persisted)
