"""Common API response schemas."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Response for GET /health."""

    status: str
    service: str
    version: str


class ErrorDetail(BaseModel):
    """Structured error detail."""

    code: str
    message: str


class ErrorResponse(BaseModel):
    """Standard error response wrapper."""

    error: ErrorDetail
