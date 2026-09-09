"""Opt-in smoke test for the OpenAI-compatible RAG LLM path.

Run directly from PowerShell through env.bat:

    cmd /c "call env.bat && python -m tests.test_llm_smoke"

Or with pytest:

    set RUN_LLM_SMOKE=1 && pytest -s chat_service/test/test_llm_smoke.py

The test deliberately prints the raw response shape.  This is useful for
models that return HTTP 200 but put text in a provider-specific field instead
of ``AIMessage.content``.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import pytest

from qa_service import llm_client, prompt_builder
from qa_service.models import RetrievedChunk
from vector_service.chroma_store import ChromaStore


QUESTION = "How does the organization recognize customer revenue and allocate transaction prices across deliverables?"
SELECTED_CHUNK_IDS = [
    "b7d0c39e994e21b38485cb4fac7d12107065f8068421916a650623efabaa0ed0-chunk-002-eef8e533f054",
    "b7d0c39e994e21b38485cb4fac7d12107065f8068421916a650623efabaa0ed0-chunk-001-789638844f97",
    "b7d0c39e994e21b38485cb4fac7d12107065f8068421916a650623efabaa0ed0-chunk-000-8b652425536e",
    "d3a36640a8a2e9c838da5d986ea56a60cc0f8c96cf671a5422b1cae2dfcb8adc-chunk-002-f187d13f19c1",
    "d3a36640a8a2e9c838da5d986ea56a60cc0f8c96cf671a5422b1cae2dfcb8adc-chunk-003-411e4d02c0d1",
]


def _json_safe(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _run_smoke() -> int:
    missing = [name for name in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY") if not os.environ.get(name)]
    if missing:
        print(f"MISSING_ENV={','.join(missing)}", file=sys.stderr)
        return 2

    collection = ChromaStore(model="bge_m3")._get_collection()
    raw = collection.get(ids=SELECTED_CHUNK_IDS, include=["documents", "metadatas"])
    chunks = []
    for rank, (chunk_id, text, metadata) in enumerate(
        zip(raw.get("ids", []), raw.get("documents", []), raw.get("metadatas", [])), start=1
    ):
        metadata = metadata or {}
        chunks.append(RetrievedChunk(
            chunk_id=chunk_id,
            document_id=str(metadata.get("document_id", "")),
            title=str(metadata.get("title", "")),
            heading=metadata.get("heading") or None,
            source_path=str(metadata.get("source_path", "")),
            text=text or "",
            distance=0.0,
            rank=rank,
        ))
    if not chunks:
        print("NO_SELECTED_CHUNKS", file=sys.stderr)
        return 3
    context = prompt_builder.build_context(chunks)
    system_prompt = prompt_builder.SYSTEM_PROMPT.format(context=context)

    print("=== smoke configuration ===")
    print(f"model={os.environ['LLM_MODEL']}")
    print(f"base_url={os.environ['LLM_BASE_URL']}")
    print(f"enable_thinking={os.environ.get('LLM_ENABLE_THINKING', '<model-default>')}")
    print(f"question_len={len(QUESTION)} context_len={len(context)}")
    print("chunk_ids=")
    for chunk in chunks:
        print(f"- {chunk.chunk_id}")

    print("=== request payload ===")
    print(_json_safe({
        "model": os.environ["LLM_MODEL"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": QUESTION},
        ],
        "temperature": 0,
        "max_tokens": os.environ.get("LLM_MAX_TOKENS", "1024"),
    }))

    print("=== raw ChatOpenAI response ===")
    try:
        raw_message = llm_client._build_llm().invoke(
            [
                ("system", system_prompt),
                ("human", QUESTION),
            ]
        )
    except Exception as exc:  # noqa: BLE001 - smoke test should explain connectivity failures
        print(f"LLM_CALL_ERROR={type(exc).__name__}: {exc}", file=sys.stderr)
        print("The request did not reach a model response; check proxy/network first.", file=sys.stderr)
        return 6
    print(f"message_type={type(raw_message).__name__}")
    print(f"content_len={len(str(getattr(raw_message, 'content', '') or ''))}")
    print(f"content={getattr(raw_message, 'content', '')!r}")
    print(f"additional_kwargs={_json_safe(getattr(raw_message, 'additional_kwargs', {}))}")
    print(f"response_metadata={_json_safe(getattr(raw_message, 'response_metadata', {}))}")
    print("=== production generate() result ===")
    try:
        answer = llm_client.generate(system_prompt, context, QUESTION)
    except Exception as exc:  # noqa: BLE001 - smoke test diagnostics
        print(f"PRODUCTION_GENERATE_ERROR={type(exc).__name__}: {exc}", file=sys.stderr)
        return 7
    print(f"answer_len={len(answer)}")
    print(f"answer={answer!r}")

    raw_content_empty = not str(getattr(raw_message, "content", "") or "").strip()
    if raw_content_empty:
        print("RAW_CONTENT_EMPTY=true")
    if not answer.strip():
        print("PRODUCTION_ANSWER_EMPTY=true")
        return 5
    if raw_content_empty:
        print("RAW_CALL_WARNING=raw diagnostic call returned empty content, but production generate() returned an answer")
    print("SMOKE_OK=true")
    return 0


def test_llm_smoke_opt_in() -> None:
    if os.environ.get("RUN_LLM_SMOKE") != "1":
        pytest.skip("set RUN_LLM_SMOKE=1 to run the live LLM smoke test")
    assert _run_smoke() == 0


if __name__ == "__main__":
    raise SystemExit(_run_smoke())
