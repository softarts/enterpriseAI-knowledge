import json
from pathlib import Path

import pytest

from embedding_service.bge_m3.embedder import BgeM3Embedder
from embedding_service.chunker import chunk_document
from embedding_service.embedder import get_embedder
from embedding_service.minilm.embedder import MiniLMEmbedder
from embedding_service.models import EmbeddedChunk
from embedding_service.search import cosine_similarity, search_by_similarity
from embedding_service.storage import load_embeddings_from_json, save_embeddings_to_json


class FakeModel:
    def __init__(self, dimension):
        self.dimension = dimension
        self.calls = []

    def encode(self, texts, **kwargs):
        self.calls.append(kwargs)
        return [[float(i)] * self.dimension for i, _ in enumerate(texts, 1)]


def test_bge_and_minilm_share_interface_without_download():
    bge = BgeM3Embedder(model=FakeModel(1024))
    mini = MiniLMEmbedder(model=FakeModel(384))
    for embedder, dimension in [(bge, 1024), (mini, 384)]:
        assert len(embedder.embed_documents(["a"])[0]) == dimension
        assert len(embedder.embed_query("q")) == dimension
        assert embedder._model.calls[0]["normalize_embeddings"] is True


def test_registry_and_model_switching():
    assert isinstance(get_embedder("bge_m3", model=FakeModel(1024)), BgeM3Embedder)
    assert isinstance(get_embedder("minilm", model=FakeModel(384)), MiniLMEmbedder)
    with pytest.raises(ValueError):
        get_embedder("unknown")


def test_chunk_markdown_hierarchy_and_offsets():
    text = "# Title\n\n## Policy\n\nrepeat\n\n## Controls\n\nrepeat"
    chunks = chunk_document("doc", "Title", text, "source.md", version="v1")
    assert [c.heading_path for c in chunks] == [("Title", "Policy"), ("Title", "Controls")]
    assert [text[s:e] for s, e in (c.offsets for c in chunks)] == [c.content for c in chunks]
    assert all("##" not in c.content for c in chunks)


def test_short_sections_and_deterministic_ids():
    text = "# T\n\n## A\n\nshort\n\n## B\n\nshort"
    first = chunk_document("doc", "T", text, "x", version="v1")
    second = chunk_document("doc", "T", text, "x", version="v1")
    other_version = chunk_document("doc", "T", text, "x", version="v2")
    assert [(c.chunk_id, c.content, c.offsets) for c in first] == [(c.chunk_id, c.content, c.offsets) for c in second]
    assert {c.chunk_id for c in first}.isdisjoint(c.chunk_id for c in other_version)
    assert all(c.content in text for c in first)


def test_oversized_fallback_is_section_local_and_has_overlap():
    paragraphs = "\n\n".join("Paragraph %d. " % i + "word " * 90 for i in range(20))
    text = "# T\n\n## Huge\n\n" + paragraphs + "\n\n## End\n\nlast"
    chunks = chunk_document("doc", "T", text, "x", version="v1")
    huge = [c for c in chunks if c.heading == "Huge"]
    assert len(huge) > 1
    assert all(c.heading_path == ("T", "Huge") for c in huge)
    assert max(c.token_count for c in huge) <= 1100
    assert any(set(a.content.split()) & set(b.content.split()) for a, b in zip(huge, huge[1:]))
    assert chunks[-1].heading == "End"


def test_dimension_validation_is_explicit():
    embedder = MiniLMEmbedder(model=FakeModel(1))
    assert embedder.dimension == 384
    with pytest.raises(ValueError):
        if len(embedder.embed_documents(["bad"])[0]) != embedder.dimension:
            raise ValueError("Embedding dimension mismatch")


def test_storage_backward_compatibility_and_metadata(tmp_path: Path):
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps([{
        "chunk_id": "old", "document_id": "doc", "title": "T", "heading": None,
        "content": "body", "source_path": "x", "embedding": [0.1, 0.2],
    }]), encoding="utf-8")
    loaded = load_embeddings_from_json(legacy)
    assert loaded[0].chunk_version == "v1"
    assert loaded[0].heading_path == ()

    item = EmbeddedChunk("id", "doc", "T", "H", "body", "x", [1.0], version="v1",
                         heading_path=("H",), content_hash="hash", token_count=1,
                         embedding_model="test", embedding_dimension=1, normalized=True,
                         offsets=(3, 7))
    target = tmp_path / "new.json"
    save_embeddings_to_json([item], target)
    roundtrip = load_embeddings_from_json(target)[0]
    assert roundtrip.heading_path == ("H",)
    assert roundtrip.offsets == (3, 7)


def test_search_by_similarity():
    chunks = [EmbeddedChunk("a", "d", "T", None, "a", "x", [1.0, 0.0]),
              EmbeddedChunk("b", "d", "T", None, "b", "x", [0.0, 1.0])]
    assert search_by_similarity([1.0, 0.1], chunks)[0].chunk_id == "a"
    assert cosine_similarity([1, 0], [0, 1]) == 0.0
