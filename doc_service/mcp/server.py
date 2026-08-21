"""
MCP Server for the Enterprise Knowledge Base.

Exposes three tools over Streamable HTTP transport:
  - list_documents: List knowledge base documents with optional filtering.
  - query_documents: Search for relevant document chunks.
  - get_document: Get a single document by ID.

All tools share the same KnowledgeService instance used by the REST API.
No HTTP calls to FastAPI — direct service invocation.
"""

import json
from typing import Optional

from mcp.server import MCPServer

from doc_service.api.dependencies import get_knowledge_service

# ---------------------------------------------------------------------------
# MCP Server instance
# ---------------------------------------------------------------------------

mcp = MCPServer(
    name="enterprise-kb",
    instructions=(
        "Enterprise Knowledge Base MCP Server. "
        "Use these tools to search and retrieve internal company documents."
    ),
)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def list_documents(
    keyword: Optional[str] = None,
    tag: Optional[str] = None,
) -> str:
    """
    List documents in the enterprise knowledge base.

    Args:
        keyword: Filter documents by title keyword (case-insensitive).
        tag: Filter documents by tag (e.g., "finance", "legal", "HR").

    Returns:
        JSON array of document summaries with document_id, title, author,
        created_at, tags, and source_path.
    """
    service = get_knowledge_service()
    docs, total = service.list_documents(keyword=keyword, tag=tag, page=1, page_size=100)

    results = [
        {
            "document_id": doc.document_id,
            "title": doc.title,
            "author": doc.author,
            "created_at": doc.created_at,
            "tags": doc.tags,
            "source_path": doc.source_path,
        }
        for doc in docs
    ]

    return json.dumps({"documents": results, "total": total}, ensure_ascii=False)


@mcp.tool()
def query_documents(
    query: str,
    top_k: int = 5,
) -> str:
    """
    Search the enterprise knowledge base for relevant document chunks.

    Use this tool when you need to find information on a specific topic.
    Returns ranked chunks with relevance scores.

    Args:
        query: The search query (keywords or natural language question).
        top_k: Maximum number of results to return (default: 5).

    Returns:
        JSON array of search results with chunk_id, document_id, title,
        heading, content, score, and source_path.
    """
    service = get_knowledge_service()
    chunk_results = service.search(query=query, top_k=top_k)

    results = [
        {
            "chunk_id": r.chunk_id,
            "document_id": r.document_id,
            "title": r.title,
            "heading": r.heading,
            "content": r.content,
            "score": r.score,
            "source_path": r.source_path,
        }
        for r in chunk_results
    ]

    return json.dumps({"query": query, "results": results}, ensure_ascii=False)


@mcp.tool()
def get_document(
    document_id: str,
) -> str:
    """
    Get the full content of a specific document by its ID.

    Use this tool when you need the complete text of a document,
    for example after finding it via query_documents.

    Args:
        document_id: The unique document identifier (e.g., "dsid-135ae39cdcd342e5b9c65190c87dd6ae--procurement-contracts-and-revrec-playbook-2025").

    Returns:
        JSON object with document_id, title, author, created_at, tags,
        source_path, and full markdown content. Returns an error message
        if the document is not found.
    """
    service = get_knowledge_service()
    doc = service.get_document(document_id)

    if doc is None:
        return json.dumps(
            {"error": f"Document '{document_id}' not found"},
            ensure_ascii=False,
        )

    result = {
        "document_id": doc.document_id,
        "title": doc.title,
        "author": doc.author,
        "created_at": doc.created_at,
        "tags": doc.tags,
        "source_path": doc.source_path,
        "content": doc.content,
    }

    return json.dumps(result, ensure_ascii=False)
