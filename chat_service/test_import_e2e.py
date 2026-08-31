"""
End-to-end verification script for Document Import backend.
"""

import os
import shutil
from pathlib import Path
from fastapi.testclient import TestClient

from chat_service.main import app
from chat_service.config import settings

client = TestClient(app)

def run_tests():
    print("=== 1. Testing GET /api/taxonomy ===")
    res = client.get("/api/taxonomy")
    assert res.status_code == 200, f"Taxonomy failed: {res.status_code} {res.text}"
    tax_data = res.json()
    assert tax_data["taxonomy_version"] == "v7"
    assert len(tax_data["nodes"]) > 0
    print(f"Taxonomy OK: version={tax_data['taxonomy_version']}, root nodes count={len(tax_data['nodes'])}")

    print("\n=== 2. Testing 404 on missing imports ===")
    missing_id = "00000000-0000-0000-0000-000000000000"
    res = client.get(f"/api/documents/import/{missing_id}")
    assert res.status_code == 404, f"Expected 404, got {res.status_code}"
    assert res.json()["detail"]["code"] == "NOT_FOUND"

    res = client.post(f"/api/documents/import/{missing_id}/confirm")
    assert res.status_code == 404, f"Expected 404, got {res.status_code}"
    assert res.json()["detail"]["code"] == "NOT_FOUND"
    print("404 missing handling OK")

    print("\n=== 3. Testing 400 validation failures ===")
    # Unsupported extension
    res = client.post(
        "/api/documents/import",
        files={"file": ("malicious.exe", b"MZ\x90\x00", "application/octet-stream")}
    )
    assert res.status_code == 400, f"Expected 400, got {res.status_code}: {res.text}"
    assert res.json()["detail"]["code"] == "UPLOAD_FAILED"

    # Empty file
    res = client.post(
        "/api/documents/import",
        files={"file": ("empty.txt", b"", "text/plain")}
    )
    assert res.status_code == 400, f"Expected 400, got {res.status_code}: {res.text}"
    assert res.json()["detail"]["code"] == "UPLOAD_FAILED"
    print("Validation handling OK")

    print("\n=== 4. Testing End-to-End Import -> Classify -> Confirm with technical document ===")
    sample_doc = (
        "# Incident Response Runbook: Kubernetes Node Eviction\n\n"
        "## Overview\n"
        "This runbook describes the alerting and triage procedures when Kubernetes cluster nodes "
        "experience memory pressure and trigger pod evictions.\n\n"
        "## Alerting and On-Call Rotation\n"
        "PagerDuty alerts are routed to the primary SRE on-call engineer. "
        "Check cluster metrics in Grafana dashboards and verify Prometheus alert rules.\n"
    ).encode("utf-8")

    res = client.post(
        "/api/documents/import",
        files={"file": ("k8s_runbook.txt", sample_doc, "text/plain")}
    )
    assert res.status_code == 200, f"Import failed: {res.status_code} {res.text}"
    doc = res.json()
    print("Import response:")
    print(doc)

    doc_id = doc["id"]
    assert doc["filename"] == "k8s_runbook.txt"
    assert doc["import_state"] == "pending"
    assert doc["status"] in ("classified", "unknown")
    assert doc["taxonomy_version"] == "v7"
    assert doc["storage_path"] is None

    if doc["status"] == "classified":
        assert doc["classification"] is not None
        assert doc["classification"]["level_1"] is not None
        assert " > " in doc["classification"]["breadcrumb"]
        print(f"Classification result: {doc['classification']['breadcrumb']}")

    # Check GET /api/documents/import/{id}
    res_get = client.get(f"/api/documents/import/{doc_id}")
    assert res_get.status_code == 200
    assert res_get.json()["id"] == doc_id
    assert res_get.json()["import_state"] == "pending"

    # Confirm
    print("\n=== 5. Confirming Document Import ===")
    res_confirm = client.post(f"/api/documents/import/{doc_id}/confirm")
    assert res_confirm.status_code == 200, f"Confirm failed: {res_confirm.status_code} {res_confirm.text}"
    confirmed_doc = res_confirm.json()
    print("Confirmed response:")
    print(confirmed_doc)

    assert confirmed_doc["import_state"] == "imported"
    storage_path = confirmed_doc["storage_path"]
    assert storage_path is not None
    assert storage_path.startswith("documents/")
    assert doc_id in storage_path

    # Verify physical file on disk
    full_storage_path = settings.import_storage_dir / storage_path
    assert full_storage_path.exists(), f"Physical storage file missing: {full_storage_path}"
    with open(full_storage_path, "rb") as f:
        stored_bytes = f.read()
    assert stored_bytes == sample_doc, "Stored bytes do not match original upload"
    print(f"Verified physical file exists and content matches at {full_storage_path}")

    # Double confirm should return 409
    print("\n=== 6. Testing Double Confirm (409) ===")
    res_double_confirm = client.post(f"/api/documents/import/{doc_id}/confirm")
    assert res_double_confirm.status_code == 409, f"Expected 409, got {res_double_confirm.status_code}"
    assert res_double_confirm.json()["detail"]["code"] == "CONFIRMATION_FAILED"
    print("Double confirm 409 OK")

    print("\n=== 7. Testing UNKNOWN Document Import ===")
    # Very short unclassifiable text or non-sense that yields UNKNOWN
    nonsense_doc = (
        "asdf qwer zxcv 12345 !@#$%^&*() random non-semantic string without meaningful language content"
    ).encode("utf-8")

    res_unknown = client.post(
        "/api/documents/import",
        files={"file": ("gibberish.txt", nonsense_doc, "text/plain")}
    )
    assert res_unknown.status_code == 200, f"Import failed: {res_unknown.status_code} {res_unknown.text}"
    unk_doc = res_unknown.json()
    print("Unknown doc import response:")
    print(unk_doc)
    unk_id = unk_doc["id"]

    # Confirm the unknown doc
    res_unk_confirm = client.post(f"/api/documents/import/{unk_id}/confirm")
    assert res_unk_confirm.status_code == 200
    assert res_unk_confirm.json()["import_state"] == "imported"
    print("Unknown doc confirmed successfully")

    print("\n=== 8. Testing Markdown and HTML Documents Import ===")
    md_content = """# Database Migration & Index Tuning

## Performance Optimization
When tuning PostgreSQL database indexes, use `EXPLAIN ANALYZE` to inspect index scans.
B-Tree indexes are effective for equality and range queries on high-cardinality columns.
""".encode("utf-8")

    res_md = client.post(
        "/api/documents/import",
        files={"file": ("postgres_tuning.md", md_content, "text/markdown")}
    )
    assert res_md.status_code == 200
    md_doc = res_md.json()
    assert md_doc["filename"] == "postgres_tuning.md"
    assert md_doc["import_state"] == "pending"
    print(f"Markdown doc import OK: status={md_doc['status']}")

    html_content = """<!DOCTYPE html>
<html>
<head><title>Annual Compliance & Anti-Money Laundering Guidelines</title></head>
<body>
<h1>Enterprise Compliance Policy</h1>
<p>All employees must adhere to Anti-Money Laundering (AML) standards and KYC verification procedures.</p>
</body>
</html>
""".encode("utf-8")

    res_html = client.post(
        "/api/documents/import",
        files={"file": ("aml_policy.html", html_content, "text/html")}
    )
    assert res_html.status_code == 200
    html_doc = res_html.json()
    assert html_doc["filename"] == "aml_policy.html"
    assert html_doc["import_state"] == "pending"
    print(f"HTML doc import OK: status={html_doc['status']}")

    print("\n===============================")
    print("ALL BACKEND IMPORT TESTS PASSED!")
    print("===============================")

if __name__ == "__main__":
    run_tests()
