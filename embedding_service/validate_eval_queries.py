"""
Validation script for embedding_service/evaluation_queries.json against generated/ OKF documents.
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from doc_service.repositories.okf_document_repository import OKFDocumentRepository


def validate():
    json_path = PROJECT_ROOT / "embedding_service" / "evaluation_queries.json"
    okf_dir = PROJECT_ROOT / "generated"

    assert json_path.exists(), f"File not found: {json_path}"
    assert okf_dir.exists(), f"Directory not found: {okf_dir}"

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Check version & query_count
    assert data.get("version") == "1.0", "Invalid version"
    queries = data.get("queries", [])
    expected_count = data.get("query_count")
    assert len(queries) == expected_count, f"query_count ({expected_count}) != actual ({len(queries)})"
    assert len(queries) == 20, f"Expected exactly 20 queries, got {len(queries)}"

    # 2. Load OKF docs
    repo = OKFDocumentRepository(okf_dir=okf_dir)
    files = list(okf_dir.rglob("*.yaml")) + list(okf_dir.rglob("*.yml"))
    doc_map = {}
    for fp in files:
        rec = repo._parse_okf_file(fp)
        if rec:
            doc_map[rec.document_id] = {
                "source_path": rec.source_path,
                "content": rec.content,
                "title": rec.title,
                "file": fp,
            }

    valid_categories = {"direct_semantic", "cross_document", "specific_detail", "hard_negative"}
    valid_difficulties = {"easy", "medium", "hard"}

    ids_seen = set()
    queries_seen = set()
    category_counts = {}
    docs_covered = set()

    for q in queries:
        qid = q["id"]
        assert qid not in ids_seen, f"Duplicate ID: {qid}"
        ids_seen.add(qid)

        qtext = q["query"]
        assert qtext not in queries_seen, f"Duplicate Query: {qtext}"
        queries_seen.add(qtext)

        cat = q["category"]
        assert cat in valid_categories, f"Invalid category: {cat}"
        category_counts[cat] = category_counts.get(cat, 0) + 1

        diff = q["difficulty"]
        assert diff in valid_difficulties, f"Invalid difficulty: {diff}"

        doc_id = q["expected_document_id"]
        assert doc_id in doc_map, f"Document ID not found in OKF repository: {doc_id}"
        docs_covered.add(doc_id)

        doc = doc_map[doc_id]
        assert q["expected_source_path"] == doc["source_path"], (
            f"Source path mismatch for {qid}: expected {doc['source_path']}, got {q['expected_source_path']}"
        )

        assert q["expected_heading"] in doc["content"], (
            f"Heading '{q['expected_heading']}' not found in document {doc_id}"
        )

        if "acceptable_documents" in q:
            for acc in q["acceptable_documents"]:
                acc_id = acc["document_id"]
                assert acc_id in doc_map, f"Acceptable document ID not found: {acc_id}"
                assert acc["heading"] in doc_map[acc_id]["content"], (
                    f"Acceptable heading '{acc['heading']}' not found in document {acc_id}"
                )

    print("================ VALIDATION SUMMARY ================")
    print(f"Total Queries: {len(queries)}")
    print("Categories breakdown:")
    for cat, count in sorted(category_counts.items()):
        print(f"  - {cat}: {count}")
    print(f"Unique OKF documents in generated/: {len(doc_map)}")
    print(f"OKF documents covered: {len(docs_covered)} / {len(doc_map)}")
    print("All validation checks PASSED successfully!")
    return True


if __name__ == "__main__":
    validate()
