"""Name discovered clusters with a local LLM (LM Studio, OpenAI-compatible).

Role split (brief, step 4): bge-m3 already found each cluster's centroid and the
representative documents nearest it; here a *generative* model reads those
representatives' titles and emits a short category name + one-sentence desc.
bge-m3 cannot do this -- it is an encoder with no decoder.

Environment (documented in bootstrap_report.md): a single local generation
model, qwen3-8b-mlx, served by LM Studio over an OpenAI-compatible API, so we
POST to {api_base}/chat/completions (not Ollama /api/generate).

qwen3-8b-mlx is a reasoning model; left alone it spends the token budget on a
hidden chain-of-thought and can return empty content. We suppress that with the
``/no_think`` control token (verified effective on this build) and still parse
defensively: content first, then any JSON object embedded in reasoning_content,
then retries, then a deterministic fallback name so the pipeline never stalls.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from ..config.settings import NamingSettings
from ..common.corpus import Document
from .discovery import DiscoveredCluster

log = logging.getLogger(__name__)

_JSON_OBJ_RE = re.compile(r"\{.*?\}", re.DOTALL)
_SNAKE_RE = re.compile(r"[^a-z0-9]+")


@dataclass
class NamingResult:
    name: str
    desc: str
    model: str
    raw_response: str
    node_key: str
    naming_failed: bool = False


def snake_key(name: str, existing: Optional[set] = None) -> str:
    """snake_case identifier from a display name, de-duplicated against existing."""
    base = _SNAKE_RE.sub("_", name.strip().lower()).strip("_") or "topic"
    if existing is None:
        return base
    key = base
    n = 2
    while key in existing:
        key = f"{base}_{n}"
        n += 1
    return key


def _build_prompt(cluster: DiscoveredCluster, docs: List[Document],
                  parent_breadcrumb: Optional[str], cfg: NamingSettings) -> List[dict]:
    titles = []
    for gi in cluster.representative_doc_indices:
        d = docs[gi]
        body = (d.body or "").strip().replace("\n", " ")
        snippet = body[: 100]
        titles.append(f"- {d.title.strip()}" + (f" | {snippet}" if snippet else ""))
    titles_block = "\n".join(titles) if titles else "- (no titles available)"

    where = f"It is a new subcategory under: {parent_breadcrumb}.\n" if parent_breadcrumb else \
            "It is a new top-level category.\n"

    system = (
        "You are a taxonomy naming assistant for an enterprise knowledge base. "
        "You read a few representative document titles from one cluster and "
        "output a single concise English category name plus a one-sentence "
        "description. Respond with STRICT JSON only, no prose, no markdown: "
        '{"name": "...", "desc": "..."}'
    )
    if cfg.disable_thinking:
        system += " /no_think"

    user = (
        "Here are representative documents from one cluster that did not fit any "
        "existing category.\n"
        f"{where}"
        "Representative titles:\n"
        f"{titles_block}\n\n"
        "Return a short category name (2-5 words, Title Case, consistent with a "
        "business/technology taxonomy) and a one-sentence description of what "
        'documents belong here. STRICT JSON only: {"name": "...", "desc": "..."}'
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    # Direct parse first.
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except (json.JSONDecodeError, TypeError):
        pass
    # Otherwise grab the first {...} block.
    for m in _JSON_OBJ_RE.finditer(text):
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict) and "name" in obj:
                return obj
        except json.JSONDecodeError:
            continue
    return None


def _call_llm(messages: List[dict], model: str, cfg: NamingSettings) -> str:
    """POST to the OpenAI-compatible chat endpoint; return message content.

    Falls back to reasoning_content only if content is empty (reasoning model
    edge case). Raises on transport/HTTP error so the caller can retry.
    """
    import requests

    url = f"{cfg.api_base.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": cfg.temperature,
        "max_tokens": cfg.max_tokens,
        "stream": False,
    }
    headers = {"Content-Type": "application/json"}
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"

    resp = requests.post(url, json=payload, headers=headers, timeout=cfg.request_timeout_s)
    resp.raise_for_status()
    data = resp.json()
    msg = data["choices"][0]["message"]
    content = (msg.get("content") or "").strip()
    if not content:
        # reasoning model may have leaked everything into reasoning_content
        content = (msg.get("reasoning_content") or "").strip()
    return content


def name_cluster(
    cluster: DiscoveredCluster,
    docs: List[Document],
    model: str,
    cfg: NamingSettings,
    *,
    parent_breadcrumb: Optional[str] = None,
    existing_keys: Optional[set] = None,
) -> NamingResult:
    """Name one cluster, with retries and a deterministic fallback."""
    messages = _build_prompt(cluster, docs, parent_breadcrumb, cfg)
    last_raw = ""
    for attempt in range(cfg.max_retries + 1):
        try:
            raw = _call_llm(messages, model, cfg)
            last_raw = raw
            obj = _extract_json(raw)
            if obj and str(obj.get("name", "")).strip():
                name = str(obj["name"]).strip()
                desc = str(obj.get("desc", "")).strip() or f"Documents related to {name}."
                key = snake_key(name, existing_keys)
                log.info("[naming] (L%d under %s) -> %r", cluster.level,
                         cluster.parent_key, name)
                return NamingResult(name=name, desc=desc, model=model,
                                    raw_response=raw, node_key=key)
            log.warning("[naming] attempt %d: could not parse JSON name from response",
                        attempt + 1)
        except Exception as exc:  # noqa: BLE001 - transport, HTTP, JSON all retryable
            log.warning("[naming] attempt %d failed: %s", attempt + 1, exc)

    # Deterministic fallback so the pipeline never stalls.
    parent = cluster.parent_key or "root"
    fallback_name = f"Uncategorized {parent} Topic"
    key = snake_key(fallback_name, existing_keys)
    log.warning("[naming] naming FAILED for cluster (L%d under %s); using fallback %r",
                cluster.level, cluster.parent_key, fallback_name)
    return NamingResult(
        name=fallback_name,
        desc=(f"Automatically grouped documents under {parent} that did not fit an "
              f"existing subcategory and could not be named by the local model."),
        model=model, raw_response=last_raw, node_key=key, naming_failed=True,
    )


# ---------------------------------------------------------------------------
# cache
# ---------------------------------------------------------------------------


def cluster_cache_id(cluster: DiscoveredCluster) -> str:
    """Stable id for caching a cluster's naming across reruns.

    Based on the sorted representative doc indices + parent + level; if discovery
    is deterministic (it is, given a fixed seed and embeddings), the same cluster
    reproduces the same id.
    """
    reps = ",".join(str(i) for i in sorted(cluster.representative_doc_indices))
    return f"L{cluster.level}|{cluster.parent_key}|{reps}"


def load_cache(path: str) -> Dict[str, dict]:
    import os
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_cache(path: str, cache: Dict[str, dict]) -> None:
    import os
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def name_clusters(
    clusters: List[DiscoveredCluster],
    docs: List[Document],
    cfg: NamingSettings,
    *,
    cache_path: str,
    breadcrumb_of: Optional[Dict[Optional[str], str]] = None,
) -> Dict[int, NamingResult]:
    """Name every non-UNKNOWN cluster, using and updating the on-disk cache.

    Returns a map from cluster position (index in ``clusters``) to NamingResult.
    UNKNOWN buckets are skipped (they don't become nodes).
    """
    breadcrumb_of = breadcrumb_of or {}
    cache = load_cache(cache_path)
    existing_keys: set = set()
    out: Dict[int, NamingResult] = {}
    model = cfg.primary_model

    for pos, cluster in enumerate(clusters):
        if cluster.unknown:
            continue
        cid = cluster_cache_id(cluster)
        if cid in cache:
            c = cache[cid]
            key = snake_key(c["name"], existing_keys)
            existing_keys.add(key)
            out[pos] = NamingResult(
                name=c["name"], desc=c["desc"], model=c.get("model", model),
                raw_response=c.get("raw_response", ""), node_key=key,
                naming_failed=c.get("naming_failed", False),
            )
            log.info("[naming] cache hit for cluster (L%d under %s): %r",
                     cluster.level, cluster.parent_key, c["name"])
            continue

        parent_bc = breadcrumb_of.get(cluster.parent_key)
        result = name_cluster(cluster, docs, model, cfg,
                              parent_breadcrumb=parent_bc, existing_keys=existing_keys)
        existing_keys.add(result.node_key)
        out[pos] = result
        cache[cid] = {
            "name": result.name, "desc": result.desc, "model": result.model,
            "raw_response": result.raw_response, "naming_failed": result.naming_failed,
        }
        save_cache(cache_path, cache)  # persist incrementally

    return out
