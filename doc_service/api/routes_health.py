"""Health check endpoint."""

from fastapi import APIRouter

from doc_service.core.config import settings
from doc_service.schemas.common import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Service health check."""
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        version=settings.version,
    )
