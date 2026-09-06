"""
Validation script for Phase 1: Embedding Generation, Local Persistence, and Cosine Similarity Retrieval.

Steps:
1. Load current OKF documents.
2. Use existing heading-aware chunker to generate chunks.
3. Generate embeddings using local SentenceTransformer.
4. Save embeddings into embedding/ with mirrored paths.
5. Reload embeddings from local files.
6. Run representative test queries with cosine similarity matching.
7. Print Top-K matching results and similarity scores.
"""

import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from embedding_service.embedder import get_embedder
from embedding_service.search import search_by_similarity
from embedding_service.service import EmbeddingService


def run_validation():
    print("=" * 70)
    print(" Phase 1 Validation: OKF -> Chunks -> Embeddings -> Persistence -> Cosine Similarity")
    print("=" * 70)

    okf_dir = PROJECT_ROOT / "generated"
    embedding_dir = PROJECT_ROOT / "embedding"

    print(f"\n[1] Initializing EmbeddingService...")
    print(f"    - OKF Directory: {okf_dir}")
    print(f"    - Embedding Directory: {embedding_dir}")

    embedder = get_embedder()
    service = EmbeddingService(okf_dir=okf_dir, embedding_dir=embedding_dir, embedder=embedder)

    # Step 1 & 2: Load and Chunk
    print("\n[2] Loading documents & chunking with existing heading-aware chunker...")
    chunks = service.build_chunks_for_all_docs()
    print(f"    -> Generated {len(chunks)} chunks from OKF documents.")
    for i, c in enumerate(chunks[:3]):
        print(f"       Chunk #{i+1}: [{c.chunk_id}] (Heading: {c.heading}) Title: {c.title[:30]}...")

    # Step 3 & 4: Embed & Persist
    print("\n[3] Generating embeddings & saving to mirrored paths in embedding/...")
    persisted_chunks = service.embed_and_persist_all()
    print(f"    -> Generated and saved {len(persisted_chunks)} embeddings.")

    # Check created files for OKF documents
    docs = service.repo.list_documents()
    persisted_files = [
        service.get_embedding_path_for_okf(Path(doc.file_path) if doc.file_path else okf_dir / f"{doc.document_id}.yaml")
        for doc in docs
    ]
    print(f"    -> OKF Persisted files count: {len(persisted_files)}")
    for f in persisted_files:
        if f.exists():
            print(f"       - {f.relative_to(PROJECT_ROOT)}")

    # Step 5: Reload from local files
    print("\n[4] Reloading embeddings from disk...")
    reloaded_chunks = service.load_embeddings_for_okf_docs()
    print(f"    -> Successfully reloaded {len(reloaded_chunks)} embedded chunks for OKF documents.")

    assert len(reloaded_chunks) == len(persisted_chunks), "Mismatch between saved and reloaded chunks count!"
    if reloaded_chunks:
        first = reloaded_chunks[0]
        print(f"       Sample chunk verification: chunk_id={first.chunk_id}, embedding_dim={len(first.embedding)}")
        assert len(first.embedding) == embedder.dimension, f"Expected dim {embedder.dimension}, got {len(first.embedding)}"

    # Also load all persisted embeddings from storage
    all_chunks = service.load_all_persisted_embeddings()
    print(f"    -> Total embedded chunks available in storage: {len(all_chunks)} across all indexed files.")

    # Step 6 & 7: Test Queries & Cosine Similarity Search
    test_queries = [
        "What are the ASC 606 revenue recognition principles?",
        "Who is the primary contact and owner for budgeting and forecasting?",
        "What are the controls and approval matrices for procurement vendor contracts?",
    ]

    print("\n[5] Executing Cosine Similarity Queries against reloaded embeddings...")
    for idx, query in enumerate(test_queries, 1):
        print("\n" + "-" * 60)
        print(f"Query {idx}: \"{query}\"")
        print("-" * 60)

        query_vec = embedder.embed_query(query)
        results = search_by_similarity(query_vec, all_chunks if all_chunks else reloaded_chunks, top_k=3)

        if not results:
            print("  No matching chunks found.")
            continue

        for rank, res in enumerate(results, 1):
            print(f"  Rank #{rank} | Similarity Score: {res.score:.4f}")
            print(f"    Document ID: {res.document_id}")
            print(f"    Chunk ID:    {res.chunk_id}")
            print(f"    Heading:     {res.heading}")
            print(f"    Source:      {res.source_path}")
            snippet = res.content.replace("\n", " ")[:150]
            print(f"    Content:     {snippet}...")

    print("\n" + "=" * 70)
    print(" Phase 1 Validation PASSED! Pipeline verified successfully.")
    print("=" * 70)


if __name__ == "__main__":
    run_validation()
