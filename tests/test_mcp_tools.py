"""
Tests for MCP Server tools.

These tests verify that MCP tools correctly invoke the shared
KnowledgeService and return properly formatted responses.

Tests use the MCP SDK's in-memory transport (Client with server object),
so no HTTP server needs to be running.

Note: The MCP Client's teardown has a known anyio cancel-scope issue
in pytest. The teardown ERRORs are cosmetic and don't affect test results.
"""

import json

import pytest
import pytest_asyncio

from mcp import Client

from doc_service.mcp.server import mcp


@pytest_asyncio.fixture
async def mcp_client(set_test_okf_dir):
    """Create an MCP client connected to the server via in-memory transport."""
    async with Client(mcp) as client:
        yield client


@pytest.mark.asyncio
async def test_list_tools(mcp_client):
    """MCP server exposes exactly three tools."""
    result = await mcp_client.list_tools()
    tool_names = sorted(t.name for t in result.tools)
    assert tool_names == ["get_document", "list_documents", "query_documents"]


@pytest.mark.asyncio
async def test_list_documents(mcp_client):
    """list_documents returns a JSON response with documents array."""
    result = await mcp_client.call_tool("list_documents", {})
    assert not result.is_error

    data = json.loads(result.content[0].text)
    assert "documents" in data
    assert "total" in data
    assert isinstance(data["documents"], list)
    assert data["total"] >= 1

    # Check document structure
    doc = data["documents"][0]
    assert "document_id" in doc
    assert "title" in doc
    assert "author" in doc
    assert "tags" in doc
    assert "source_path" in doc


@pytest.mark.asyncio
async def test_list_documents_with_tag_filter(mcp_client):
    """list_documents can filter by tag."""
    result = await mcp_client.call_tool("list_documents", {"tag": "security"})
    data = json.loads(result.content[0].text)

    # All results should have the security tag
    for doc in data["documents"]:
        assert "security" in doc["tags"]


@pytest.mark.asyncio
async def test_list_documents_with_keyword_filter(mcp_client):
    """list_documents can filter by keyword that exists in fixture titles."""
    # First list all documents to get a known title
    all_result = await mcp_client.call_tool("list_documents", {})
    all_data = json.loads(all_result.content[0].text)
    assert all_data["total"] >= 1

    # Use part of the first document's title as keyword
    first_title = all_data["documents"][0]["title"]
    keyword = first_title[:5]  # use first 5 chars

    result = await mcp_client.call_tool("list_documents", {"keyword": keyword})
    data = json.loads(result.content[0].text)
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_query_documents(mcp_client):
    """query_documents returns search results with scores."""
    # Use a query that's likely to match fixture content
    result = await mcp_client.call_tool(
        "query_documents", {"query": "policy", "top_k": 3}
    )
    assert not result.is_error

    data = json.loads(result.content[0].text)
    assert data["query"] == "policy"
    assert "results" in data
    assert isinstance(data["results"], list)

    # If there are results, check structure
    if len(data["results"]) > 0:
        chunk = data["results"][0]
        assert "chunk_id" in chunk
        assert "document_id" in chunk
        assert "title" in chunk
        assert "content" in chunk
        assert "score" in chunk
        assert "source_path" in chunk
        assert chunk["score"] > 0


@pytest.mark.asyncio
async def test_query_documents_respects_top_k(mcp_client):
    """query_documents respects the top_k parameter."""
    result = await mcp_client.call_tool(
        "query_documents", {"query": "policy", "top_k": 2}
    )
    data = json.loads(result.content[0].text)
    assert len(data["results"]) <= 2


@pytest.mark.asyncio
async def test_get_document_found(mcp_client):
    """get_document returns full document content when found."""
    # First, get a document_id from list
    list_result = await mcp_client.call_tool("list_documents", {})
    list_data = json.loads(list_result.content[0].text)
    doc_id = list_data["documents"][0]["document_id"]

    # Now get full document
    result = await mcp_client.call_tool("get_document", {"document_id": doc_id})
    assert not result.is_error

    data = json.loads(result.content[0].text)
    assert data["document_id"] == doc_id
    assert "title" in data
    assert "content" in data
    assert len(data["content"]) > 0


@pytest.mark.asyncio
async def test_get_document_not_found(mcp_client):
    """get_document returns an error message for non-existent document."""
    result = await mcp_client.call_tool(
        "get_document", {"document_id": "nonexistent-doc-id"}
    )
    data = json.loads(result.content[0].text)
    assert "error" in data
    assert "not found" in data["error"].lower()


@pytest.mark.asyncio
async def test_mcp_shares_same_data_as_rest(mcp_client):
    """
    MCP tools share the same KnowledgeService as the REST API.

    Verifies that list_documents via MCP returns the same document_ids
    that the REST API would serve (same repository, same data).
    """
    from doc_service.api.dependencies import get_knowledge_service

    # Get data via MCP
    mcp_result = await mcp_client.call_tool("list_documents", {})
    mcp_data = json.loads(mcp_result.content[0].text)
    mcp_ids = {doc["document_id"] for doc in mcp_data["documents"]}

    # Get data directly from KnowledgeService (same as REST API uses)
    service = get_knowledge_service()
    docs, _ = service.list_documents(page=1, page_size=100)
    service_ids = {doc.document_id for doc in docs}

    assert mcp_ids == service_ids
