"""One-off corpus probe: how many docs, what format, size distribution.

Not part of the bootstrap pipeline -- used to size the job before committing to
an embedding strategy.
"""
from __future__ import annotations

import collections
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "all_documents")
ROOT = os.path.normpath(ROOT)


def main() -> None:
    per_source: dict[str, dict[str, int]] = collections.defaultdict(
        lambda: {"n": 0, "bytes": 0}
    )
    ext_counter: collections.Counter[str] = collections.Counter()
    sizes: list[int] = []
    samples: dict[str, str] = {}

    for dirpath, _dirnames, filenames in os.walk(ROOT):
        rel = os.path.relpath(dirpath, ROOT)
        top = rel.split(os.sep)[0] if rel != "." else "."
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            ext = os.path.splitext(fn)[1].lower()
            ext_counter[ext] += 1
            per_source[top]["n"] += 1
            per_source[top]["bytes"] += size
            sizes.append(size)
            if top not in samples:
                samples[top] = full

    total = sum(v["n"] for v in per_source.values())
    print(f"TOTAL FILES: {total:,}")
    print(f"TOTAL BYTES: {sum(sizes) / 1024 / 1024:,.1f} MB")
    print()
    print("BY EXTENSION:")
    for ext, c in ext_counter.most_common():
        print(f"  {ext or '(none)':10s} {c:,}")
    print()
    print(f"{'SOURCE':22s} {'FILES':>9s} {'MB':>9s} {'AVG KB':>8s}")
    for src, v in sorted(per_source.items(), key=lambda kv: -kv[1]["n"]):
        print(
            f"{src:22s} {v['n']:>9,} {v['bytes'] / 1024 / 1024:>9,.1f} "
            f"{v['bytes'] / max(v['n'], 1) / 1024:>8.1f}"
        )
    print()
    sizes.sort()
    for p in (5, 25, 50, 75, 90, 99):
        idx = int(len(sizes) * p / 100)
        print(f"  size p{p:<3d} = {sizes[min(idx, len(sizes) - 1)]:,} bytes")
    print()
    print("=" * 70)
    for src, path in sorted(samples.items()):
        print(f"\n### SAMPLE [{src}] {os.path.relpath(path, ROOT)}")
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                head = f.read(900)
            print(head)
        except OSError as exc:  # pragma: no cover
            print(f"  <unreadable: {exc}>")
        print("-" * 70)


if __name__ == "__main__":
    sys.exit(main())
