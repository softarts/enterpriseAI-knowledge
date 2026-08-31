"""Micro-benchmark: is 0.57 docs/s a real GPU ceiling or a bad config?

Sweeps batch size, sequence length and dtype against real corpus text so we can
pick an operating point on evidence instead of guessing. Not part of the
pipeline.
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kb_classifier_bootstrap.bootstrap.corpus import load_manifest, read_document
from kb_classifier_bootstrap.config.settings import SETTINGS


def main() -> None:
    import torch
    from sentence_transformers import SentenceTransformer

    print(f"torch {torch.__version__}  cuda_available={torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"device: {torch.cuda.get_device_name(0)}")
        props = torch.cuda.get_device_properties(0)
        print(f"  total VRAM : {props.total_memory / 1024**3:.2f} GB")
        print(f"  SMs        : {props.multi_processor_count}")
        print(f"  capability : {props.major}.{props.minor}")

    entries = load_manifest(SETTINGS.paths.manifest_path)[:128]
    docs = [read_document(SETTINGS.corpus.root, e) for e in entries]
    texts = [d.embed_text(2000, True) for d in docs]
    print(f"\nloaded {len(texts)} real documents; "
          f"mean chars={np.mean([len(t) for t in texts]):.0f}")

    for use_fp16 in (True, False):
        model = SentenceTransformer(SETTINGS.embedding.model_name, device="cuda")
        if use_fp16:
            model = model.half()
        tok = model.tokenizer
        lens = [len(tok(t, truncation=True, max_length=8192)["input_ids"]) for t in texts[:32]]
        print(f"\n=== fp16={use_fp16} ===")
        print(f"  untruncated token lengths: p50={np.percentile(lens,50):.0f} "
              f"p90={np.percentile(lens,90):.0f} max={max(lens)}")

        for seq_len in (256, 512):
            model.max_seq_length = seq_len
            for batch in (8, 16, 32):
                sub = texts[:64]
                try:
                    # warmup so we time steady state, not CUDA init
                    model.encode(sub[:batch], batch_size=batch,
                                 convert_to_numpy=True, show_progress_bar=False)
                    torch.cuda.synchronize()
                    t0 = time.time()
                    model.encode(sub, batch_size=batch, convert_to_numpy=True,
                                 normalize_embeddings=True, show_progress_bar=False)
                    torch.cuda.synchronize()
                    dt = time.time() - t0
                    peak = torch.cuda.max_memory_allocated() / 1024**3
                    print(f"  seq={seq_len:4d} batch={batch:3d} -> "
                          f"{len(sub)/dt:6.2f} docs/s   ({dt:5.2f}s / {len(sub)} docs, "
                          f"peak VRAM {peak:.2f} GB)")
                except torch.cuda.OutOfMemoryError:
                    print(f"  seq={seq_len:4d} batch={batch:3d} -> OOM")
                    torch.cuda.empty_cache()
                torch.cuda.reset_peak_memory_stats()

        del model
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
