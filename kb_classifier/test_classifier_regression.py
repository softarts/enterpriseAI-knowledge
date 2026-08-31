"""
Regression test suite for kb_classifier (Taxonomy Classifier).

Run with:
    python3 -m pytest kb_classifier/test_classifier_regression.py
or:
    python3 -m kb_classifier.test_classifier_regression
"""

from __future__ import annotations

import os
from pathlib import Path
import pytest

from kb_classifier.taxonomy_classifier.classify import (
    TaxonomyClassifier,
    STATUS_ASSIGNED,
    STATUS_FALLBACK,
    STATUS_PARTIAL,
    STATUS_UNKNOWN,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

@pytest.fixture(scope="module")
def classifier():
    return TaxonomyClassifier()


def test_people_ops_offer_playbook_regression(classifier):
    """
    Regression Test:
    'Evidence-driven offer evaluation and onboarding trigger playbook'
    Must classify to Human Resources > Recruitment > Offers & Hiring Decisions / Onboarding,
    NOT Product Management (which was previously caused by greedy top-down L1 error).
    """
    playbook_path = (
        REPO_ROOT
        / "all_documents"
        / "confluence"
        / "people-ops"
        / "dsid_0a2cd37d53ff47d4aced289cd9a76fe8__evidence-driven-offer-evaluation-and-onboarding-trigger-playbook-2028.txt"
    )
    if not playbook_path.exists():
        pytest.skip(f"Document file not found at {playbook_path}")

    with open(playbook_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    title = lines[0].strip() if lines else ""
    body = "".join(lines[1:])

    cl = classifier.classify_text(title, body)
    md = cl.to_okf_metadata()

    assert md["l1_key"] == "human_resources", f"Expected human_resources L1, got {md['l1_key']}"
    assert md["l2_key"] == "recruitment", f"Expected recruitment L2, got {md['l2_key']}"
    assert md["l3_key"] in (
        "offers_hiring_decisions",
        "onboarding_new_hire_enablement",
    ), f"Expected offers_hiring_decisions or onboarding L3, got {md['l3_key']}"
    assert md["classification_status"] in (STATUS_ASSIGNED, STATUS_FALLBACK)
    assert "Human Resources > Recruitment" in md["category_breadcrumb"]


def test_tech_infrastructure_document(classifier):
    """
    Technical engineering document about incident response and alerting.
    Must classify under Technology & Engineering.
    """
    title = "Incident Response Runbook: Kubernetes Pod Eviction & Node Memory Pressure"
    body = (
        "This SRE runbook describes triage and alerting procedures when Kubernetes worker nodes "
        "experience OOM and memory pressure. PagerDuty alerts are routed to the on-call SRE. "
        "Inspect Prometheus metrics and Grafana cluster dashboards for container memory limits."
    )
    cl = classifier.classify_text(title, body)
    md = cl.to_okf_metadata()

    assert md["l1_key"] == "technology_engineering"
    assert md["classification_status"] in (STATUS_ASSIGNED, STATUS_FALLBACK)
    assert "Technology & Engineering" in md["category_breadcrumb"]


def test_risk_compliance_aml_document(classifier):
    """
    Compliance and anti-money laundering policy document.
    Must classify under Risk & Compliance.
    """
    title = "Anti-Money Laundering & KYC Customer Due Diligence Guidelines"
    body = (
        "Enterprise AML policy requires verifying customer identities (KYC), monitoring suspicious "
        "transaction patterns, and reporting Currency Transaction Reports (CTR) to regulatory authorities."
    )
    cl = classifier.classify_text(title, body)
    md = cl.to_okf_metadata()

    assert md["l1_key"] == "risk_compliance"
    assert md["classification_status"] in (STATUS_ASSIGNED, STATUS_FALLBACK)
    assert "Risk & Compliance" in md["category_breadcrumb"]


def test_gibberish_unknown_document(classifier):
    """
    Random non-semantic gibberish text must result in UNKNOWN classification.
    """
    title = "asdf qwer zxcv 12345 !@#$%^&*() random non-semantic string without meaningful language content"
    body = "asdf qwer zxcv 12345 !@#$%^&*() random non-semantic string without meaningful language content"
    cl = classifier.classify_text(title, body)
    md = cl.to_okf_metadata()

    assert md["classification_status"] == STATUS_UNKNOWN
    assert md["classification_depth"] == 0
    assert md["category_path_keys"] == []
    assert md["category_breadcrumb"] == ""


def test_hierarchical_path_consistency(classifier):
    """
    Verify that match_hierarchical produces strictly valid tree paths where:
    l2 is a child of l1, and l3 is a child of l2.
    """
    from kb_classifier.common.anchors import children_index
    kids = children_index(classifier.anchors)
    row_by_key = {a.key: i for i, a in enumerate(classifier.anchors)}

    title = "Quarterly Financial Statements & Balance Sheet Reconciliation"
    body = "Review of income statement, cash flow statements, journal entries and ledger reconciliation."
    cl = classifier.classify_text(title, body)
    md = cl.to_okf_metadata()

    if md["l1_key"] and md["l2_key"]:
        l2_valid_children = [classifier.anchors[r].key for r in kids.get(md["l1_key"], [])]
        assert md["l2_key"] in l2_valid_children, f"L2 {md['l2_key']} is not a child of L1 {md['l1_key']}"

    if md["l2_key"] and md["l3_key"]:
        l3_valid_children = [classifier.anchors[r].key for r in kids.get(md["l2_key"], [])]
        assert md["l3_key"] in l3_valid_children, f"L3 {md['l3_key']} is not a child of L2 {md['l2_key']}"


if __name__ == "__main__":
    print("Running kb_classifier regression tests...")
    import sys
    clf = TaxonomyClassifier()
    test_people_ops_offer_playbook_regression(clf)
    print("✓ test_people_ops_offer_playbook_regression passed")
    test_tech_infrastructure_document(clf)
    print("✓ test_tech_infrastructure_document passed")
    test_risk_compliance_aml_document(clf)
    print("✓ test_risk_compliance_aml_document passed")
    test_gibberish_unknown_document(clf)
    print("✓ test_gibberish_unknown_document passed")
    test_hierarchical_path_consistency(clf)
    print("✓ test_hierarchical_path_consistency passed")
    print("\nALL KB_CLASSIFIER REGRESSION TESTS PASSED!")
