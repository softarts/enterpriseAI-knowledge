import json
from pathlib import Path
import pytest

from embedding_service.main_import import (
    collect_okf_files,
    compute_output_path,
    process_okf_document,
    resolve_input_root,
)
from embedding_service.minilm.embedder import MiniLMEmbedder
from embedding_service.storage import load_embeddings_from_json


class FakeModel:
    def encode(self, texts, **kwargs):
        return [[0.0] * 384 for _ in texts]


def test_resolve_input_root():
    # Case 1: subpath inside generated
    p1 = Path("h:/work/generated/confluence/people-ops/onboarding/doc.yaml")
    root1 = resolve_input_root(p1)
    assert root1.name == "generated"

    # Case 2: subpath inside okf
    p2 = Path("h:/work/okf/jira/project/ticket.yaml")
    root2 = resolve_input_root(p2)
    assert root2.name == "okf"

    # Case 3: standalone file outside candidates
    p3 = Path("h:/work/custom_folder/some_doc.yaml")
    root3 = resolve_input_root(p3)
    assert root3.name == "custom_folder"


def test_process_okf_document_mirrored(tmp_path: Path):
    # Setup OKF document inside fake generated
    gen_dir = tmp_path / "generated"
    sub_dir = gen_dir / "confluence" / "people-ops" / "onboarding"
    sub_dir.mkdir(parents=True)
    okf_file = sub_dir / "onboarding_guide.yaml"
    okf_file.write_text(
        """---
title: Onboarding Guide (2028)
author: hr-team
created_at: '2026-01-01T00:00:00Z'
tags:
- onboarding
- hr
source_path: confluence/people-ops/onboarding/onboarding_guide.txt
document_id: confluence-people-ops-onboarding-onboarding-guide
---

# Onboarding Guide (2028)

## Overview
Welcome to the company.

## Day 30 Goals
Complete all setup tasks.
""",
        encoding="utf-8",
    )

    out_dir = tmp_path / "embedding"
    input_root = resolve_input_root(okf_file)
    assert input_root == gen_dir

    embedder = MiniLMEmbedder(model=FakeModel())
    success = process_okf_document(
        file_path=okf_file,
        input_root=input_root,
        output_dir=out_dir,
        embedder=embedder,
        mirror=True,
    )
    assert success is True

    expected_json = out_dir / "confluence" / "people-ops" / "onboarding" / "onboarding_guide.json"
    assert expected_json.exists()

    chunks = load_embeddings_from_json(expected_json)
    assert len(chunks) == 2
    assert chunks[0].document_id == "confluence-people-ops-onboarding-onboarding-guide"
    assert chunks[0].title == "Onboarding Guide (2028)"
    assert chunks[0].source_path == "confluence/people-ops/onboarding/onboarding_guide.txt"
    assert chunks[0].heading == "Overview"
    assert len(chunks[0].embedding) == embedder.dimension


def test_process_okf_document_custom_output(tmp_path: Path):
    okf_file = tmp_path / "generated" / "finance" / "policy.yaml"
    okf_file.parent.mkdir(parents=True)
    okf_file.write_text(
        """---
title: Finance Policy
source_path: finance/policy.txt
document_id: finance-policy
---

# Finance Policy

## Expenses
Expenses and limits details.
""",
        encoding="utf-8",
    )

    custom_out = tmp_path / "my_custom_embeddings"
    input_root = resolve_input_root(okf_file)

    embedder = MiniLMEmbedder(model=FakeModel())
    success = process_okf_document(
        file_path=okf_file,
        input_root=input_root,
        output_dir=custom_out,
        embedder=embedder,
        mirror=False,
    )
    assert success is True

    direct_json = custom_out / "policy.json"
    assert direct_json.exists()

    chunks = load_embeddings_from_json(direct_json)
    assert len(chunks) == 1
    assert chunks[0].document_id == "finance-policy"
    assert chunks[0].source_path == "finance/policy.txt"
