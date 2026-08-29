"""Pre-fetch BAAI/bge-m3 into the local HuggingFace cache.

Run once before the bootstrap pipeline so the pipeline itself never blocks on a
~2.3 GB download mid-run.
"""
from __future__ import annotations

import time

MODEL = "BAAI/bge-m3"


def main() -> None:
    t0 = time.time()
    print(f"[download] fetching {MODEL} ...", flush=True)
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL, device="cpu")
    print(f"[download] ok in {time.time() - t0:.1f}s", flush=True)
    print(f"[download] max_seq_length = {model.max_seq_length}", flush=True)
    print(
        f"[download] embedding dim   = {model.get_sentence_embedding_dimension()}",
        flush=True,
    )


if __name__ == "__main__":
    main()
