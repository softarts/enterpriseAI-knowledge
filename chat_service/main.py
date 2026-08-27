"""
chat_service FastAPI application entry point.

Start with:
    uvicorn chat_service.main:app --reload --port 8100
or:
    python -m chat_service.run
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from chat_service.api.routes_chat import router as chat_router
from chat_service.config import settings

app = FastAPI(
    title="Enterprise AI Playground — chat_service",
    description=(
        "Standalone backend for the Enterprise AI Playground UI. "
        "v1 implements a direct Ask flow: question -> Hugging Face LLM -> "
        "answer + extensible trace. No RAG / Chroma / MCP yet."
    ),
    version=settings.version,
)

# The frontend (Vite dev server) runs on a different origin, so CORS is needed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, tags=["Chat"])
