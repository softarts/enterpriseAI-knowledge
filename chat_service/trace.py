"""
TraceBuilder — assembles the extensible execution trace returned with each
chat response and rendered in the UI's Verbose / Trace panel.

Design goals
------------
- Real data only: every field is populated from the actual request lifecycle.
- Extensible: today we record `request`, `llm`, and `response` sections plus a
  flat ordered `steps` list. Future stages (retrieval, context assembly,
  reranker, agent/ReAct) append more steps and sections WITHOUT changing the
  shape the UI already understands.

Resulting shape:
{
  "trace_id": "...",
  "started_at": "ISO-8601",
  "finished_at": "ISO-8601",
  "duration_ms": 123,
  "steps": [
    {"name": "request", "status": "ok", "detail": {...}, "duration_ms": 0},
    {"name": "llm", "status": "ok", "detail": {...}, "duration_ms": 120},
    {"name": "response", "status": "ok", "detail": {...}, "duration_ms": 0}
  ],
  "request":  {...},   # convenience section mirrors the "request" step detail
  "llm":      {...},
  "response": {...}
}
"""

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TraceBuilder:
    """Accumulates ordered steps and named sections for one chat request."""

    # Known top-level sections. Extend this list as the pipeline grows
    # (e.g. "retrieval", "context", "rerank", "agent").
    SECTIONS = ("request", "llm", "response")

    def __init__(self) -> None:
        self._trace_id = uuid.uuid4().hex
        self._started_at = _now_iso()
        self._start_perf = time.perf_counter()
        self._steps: List[Dict[str, Any]] = []
        self._sections: Dict[str, Any] = {}

    def add_step(
        self,
        name: str,
        detail: Dict[str, Any],
        status: str = "ok",
        duration_ms: Optional[float] = None,
    ) -> None:
        """
        Record one pipeline step.

        Args:
            name: Step name (e.g. "request", "llm", "response", and later
                  "retrieval", "rerank", "agent", ...).
            detail: Arbitrary structured detail for this step.
            status: "ok" | "error" | "skipped".
            duration_ms: Optional measured duration for the step.
        """
        self._steps.append(
            {
                "name": name,
                "status": status,
                "detail": detail,
                "duration_ms": round(duration_ms, 2) if duration_ms is not None else None,
            }
        )
        # Mirror the detail into a named section for convenient UI access.
        self._sections[name] = detail

    def build(self) -> Dict[str, Any]:
        """Finalize and return the trace dict."""
        duration_ms = round((time.perf_counter() - self._start_perf) * 1000, 2)
        trace: Dict[str, Any] = {
            "trace_id": self._trace_id,
            "started_at": self._started_at,
            "finished_at": _now_iso(),
            "duration_ms": duration_ms,
            "steps": self._steps,
        }
        trace.update(self._sections)
        return trace
