"""
Unified startup script for the Enterprise Knowledge Base.

Starts both the FastAPI REST API and MCP Server in the same process,
sharing the same KnowledgeService instance.

Usage:
    python -m doc_service.mcp_main

Environment Variables:
    KB_HOST      - Bind address (default: 0.0.0.0)
    KB_PORT      - REST API port (default: 8000)
    KB_MCP_PORT  - MCP Server port (default: 8001)
    KB_OKF_DIR   - OKF documents directory (default: ./generated)
"""

import asyncio
import logging

import uvicorn

from doc_service.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def start_rest_api() -> None:
    """Start the FastAPI REST API server."""
    from doc_service.main import app as fastapi_app

    config = uvicorn.Config(
        app=fastapi_app,
        host=settings.host,
        port=settings.port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    logger.info("Starting REST API on %s:%d", settings.host, settings.port)
    await server.serve()


async def start_mcp_server() -> None:
    """Start the MCP Server with Streamable HTTP transport."""
    from doc_service.mcp.server import mcp

    mcp_app = mcp.streamable_http_app()

    config = uvicorn.Config(
        app=mcp_app,
        host=settings.host,
        port=settings.mcp_port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    logger.info("Starting MCP Server on %s:%d", settings.host, settings.mcp_port)
    await server.serve()


async def main() -> None:
    """Start both servers concurrently."""
    logger.info("=" * 60)
    logger.info("Enterprise Knowledge Base — Unified Startup")
    logger.info("REST API: http://%s:%d", settings.host, settings.port)
    logger.info("MCP Server: http://%s:%d/mcp", settings.host, settings.mcp_port)
    logger.info("OKF Directory: %s", settings.okf_dir)
    logger.info("=" * 60)

    await asyncio.gather(
        start_rest_api(),
        start_mcp_server(),
    )


if __name__ == "__main__":
    asyncio.run(main())
