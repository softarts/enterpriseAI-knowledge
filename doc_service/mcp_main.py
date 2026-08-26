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
import socket
import sys

import uvicorn

from doc_service.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _port_in_use(host: str, port: int) -> bool:
    """Return True if a TCP port is already bound on the given host."""
    # 0.0.0.0 is not connectable on Windows; probe loopback for the check.
    probe_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((probe_host, port)) == 0


def _preflight_ports() -> None:
    """
    Fail fast with an actionable message if either port is already bound.

    Without this, uvicorn raises a long, opaque traceback via asyncio.gather
    when a server instance is already running on the same port.
    """
    conflicts = []
    if _port_in_use(settings.host, settings.port):
        conflicts.append(("REST API", settings.port, "KB_PORT"))
    if _port_in_use(settings.host, settings.mcp_port):
        conflicts.append(("MCP Server", settings.mcp_port, "KB_MCP_PORT"))

    if conflicts:
        logger.error("=" * 60)
        logger.error("Startup aborted: port(s) already in use.")
        for name, port, env_var in conflicts:
            logger.error(
                "  %s port %d is busy. A server may already be running, or set %s "
                "to a free port.",
                name,
                port,
                env_var,
            )
        logger.error(
            "If the enterprise-kb server is already running, no action is needed — "
            "use the MCP tools against the existing instance."
        )
        logger.error("=" * 60)
        sys.exit(1)


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

    _preflight_ports()

    await asyncio.gather(
        start_rest_api(),
        start_mcp_server(),
    )


if __name__ == "__main__":
    asyncio.run(main())
