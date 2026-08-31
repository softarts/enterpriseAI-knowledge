"""
Keyword-based retriever implementation.

Simple text-matching retriever for the POC phase.
Will be replaced by VectorRetriever / HybridRetriever in future phases.
"""

import re
from typing import List, Optional

from doc_service.repositories.okf_document_repository import OKFDocumentRepository
from doc_service.retrieval.chunker import Chunk, chunk_document
from doc_service.retrieval.retriever import ChunkResult


class KeywordRetriever:
    """
    Simple keyword-based retriever.

    Scoring strategy:
      - Count occurrences of query terms in chunk content + heading.
      - Normalize by chunk length to avoid bias toward long chunks.
      - Score is between 0.0 and 1.0.

    This satisfies the Retriever protocol.
    """

    def __init__(self, repository: OKFDocumentRepository) -> None:
        self._repository = repository
        self._chunks: Optional[List[Chunk]] = None

    def retrieve(self, query: str, top_k: int = 5) -> List[ChunkResult]:
        """Retrieve top-k chunks matching the query by keyword relevance."""
        if not query.strip():
            return []

        chunks = self._get_all_chunks()
        scored = self._score_chunks(query, chunks)

        # Sort by score descending, take top_k
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]

    def reload(self) -> None:
        """Invalidate chunk cache (e.g. after repository reload)."""
        self._chunks = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_all_chunks(self) -> List[Chunk]:
        """Build chunks from all documents (lazy, cached)."""
        if self._chunks is None:
            all_chunks: List[Chunk] = []
            for doc in self._repository.list_documents():
                doc_chunks = chunk_document(
                    document_id=doc.document_id,
                    title=doc.title,
                    content=doc.content,
                    source_path=doc.source_path,
                )
                all_chunks.extend(doc_chunks)
            self._chunks = all_chunks
        return self._chunks

    def _score_chunks(self, query: str, chunks: List[Chunk]) -> List[ChunkResult]:
        """Score each chunk against the query using keyword matching."""
        # Split query into individual terms for matching
        query_terms = self._tokenize(query)
        if not query_terms:
            return []

        results: List[ChunkResult] = []

        for chunk in chunks:
            score = self._compute_score(query_terms, chunk)
            if score > 0.0:
                results.append(
                    ChunkResult(
                        chunk_id=chunk.chunk_id,
                        document_id=chunk.document_id,
                        title=chunk.title,
                        heading=chunk.heading,
                        content=chunk.content,
                        score=round(score, 4),
                        source_path=chunk.source_path,
                    )
                )

        return results

    def _compute_score(self, query_terms: List[str], chunk: Chunk) -> float:
        """
        Compute relevance score for a chunk.

        Strategy:
          1. For each query term, check if it appears in the chunk text.
          2. Score = (matched_terms / total_terms) * term_frequency_boost.
          3. Heading match gets a bonus.
        """
        # Combine heading and content for matching
        text = (chunk.content or "").lower()
        heading_text = (chunk.heading or "").lower()
        full_text = f"{heading_text} {text}"

        matched_terms = 0
        total_frequency = 0

        for term in query_terms:
            count = full_text.count(term)
            if count > 0:
                matched_terms += 1
                total_frequency += count

        if matched_terms == 0:
            return 0.0

        # Base score: ratio of matched terms
        term_coverage = matched_terms / len(query_terms)

        # Frequency boost (log-like, capped)
        freq_boost = min(total_frequency / 5.0, 2.0)

        # Heading bonus: if query terms appear in heading
        heading_bonus = 0.0
        for term in query_terms:
            if term in heading_text:
                heading_bonus = 0.15
                break

        score = (term_coverage * 0.6) + (freq_boost * 0.2) + heading_bonus

        # Cap at 1.0
        return min(score, 1.0)

    def _tokenize(self, text: str) -> List[str]:
        """
        Split text into searchable tokens.

        Handles both CJK characters (each char is a token) and
        Latin/alphanumeric words.
        """
        text = text.lower().strip()
        if not text:
            return []

        tokens: List[str] = []

        # Extract CJK sequences and Latin words separately
        # CJK Unicode ranges: common Chinese/Japanese/Korean characters
        cjk_pattern = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]+")
        latin_pattern = re.compile(r"[a-z0-9]+")

        # Find CJK tokens (individual characters for Chinese)
        for match in cjk_pattern.finditer(text):
            cjk_str = match.group()
            # For Chinese text, each character or bigram can be a token
            # Use bigrams for better matching
            if len(cjk_str) >= 2:
                for i in range(len(cjk_str) - 1):
                    tokens.append(cjk_str[i : i + 2])
            if len(cjk_str) == 1:
                tokens.append(cjk_str)

        # Find Latin word tokens
        for match in latin_pattern.finditer(text):
            tokens.append(match.group())

        return tokens
