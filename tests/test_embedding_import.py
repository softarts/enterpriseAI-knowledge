import json
from pathlib import Path
import pytest

from embedding_service.config import EMBEDDING_DIMENSION
from embedding_service.main_import import (
    compute_document_id,
    compute_output_path,
    compute_relative_source_path,
    process_raw_document,
    resolve_input_root,
)
from embedding_service.embedder import LocalEmbedder
from embedding_service.storage import load_embeddings_from_json


def test_resolve_input_root():
    # Case 1: subpath inside all_documents
    p1 = Path("h:/work/all_documents/confluence/people-ops/onboarding/doc.txt")
    root1 = resolve_input_root(p1)
    assert root1.name == "all_documents"
    assert compute_relative_source_path(p1, root1) == "confluence/people-ops/onboarding/doc.txt"

    # Case 2: subpath inside raw_documents
    p2 = Path("h:/work/raw_documents/jira/project/ticket.txt")
    root2 = resolve_input_root(p2)
    assert root2.name == "raw_documents"
    assert compute_relative_source_path(p2, root2) == "jira/project/ticket.txt"

    # Case 3: standalone file outside candidates
    p3 = Path("h:/work/custom_folder/some_doc.txt")
    root3 = resolve_input_root(p3)
    assert root3.name == "custom_folder"
    assert compute_relative_source_path(p3, root3) == "some_doc.txt"


def test_compute_document_id():
    p = Path("h:/work/all_documents/confluence/people-ops/onboarding/dsid_abc__first-90-days.txt")
    root = Path("h:/work/all_documents")
    doc_id = compute_document_id(p, root, mirror=True)
    assert doc_id == "confluence-people-ops-onboarding-dsid-abc--first-90-days" or doc_id == "confluence-people-ops-onboarding-dsid-abc-first-90-days"


def test_process_raw_document_mirrored(tmp_path: Path):
    # Setup raw document inside fake all_documents
    all_docs = tmp_path / "all_documents"
    sub_dir = all_docs / "confluence" / "people-ops" / "onboarding"
    sub_dir.mkdir(parents=True)
    raw_file = sub_dir / "onboarding_guide.txt"
    raw_file.write_text(
        """# Onboarding Guide (2028)

## Overview
Welcome to the company.

## Day 30 Goals
Complete all setup tasks.
""",
        encoding="utf-8",
    )

    out_dir = tmp_path / "embedding"
    input_root = resolve_input_root(raw_file)
    assert input_root == all_docs

    embedder = LocalEmbedder()
    success = process_raw_document(
        file_path=raw_file,
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
    assert chunks[0].title == "Onboarding Guide (2028)"
    assert chunks[0].source_path == "confluence/people-ops/onboarding/onboarding_guide.txt"
    assert len(chunks[0].embedding) == EMBEDDING_DIMENSION


def test_process_raw_document_custom_output(tmp_path: Path):
    raw_file = tmp_path / "all_documents" / "finance" / "policy.txt"
    raw_file.parent.mkdir(parents=True)
    raw_file.write_text("# Finance Policy\n\nExpenses and limits.", encoding="utf-8")

    custom_out = tmp_path / "my_custom_embeddings"
    input_root = resolve_input_root(raw_file)

    embedder = LocalEmbedder()
    success = process_raw_document(
        file_path=raw_file,
        input_root=input_root,
        output_dir=custom_out,
        embedder=embedder,
        mirror=False,
    )
    assert success is True

    direct_json = custom_out / "policy.json"
    assert direct_json.exists()

    chunks = load_embeddings_from_json(direct_json)
    assert len(chunks) >= 1
    assert chunks[0].document_id == "policy"
