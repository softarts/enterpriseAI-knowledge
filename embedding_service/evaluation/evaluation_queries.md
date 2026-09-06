# Embedding Retrieval Evaluation Queries

> Ground-truth query evaluation dataset generated strictly from `generated/` OKF documents.

- **Version**: 1.0
- **Query Count**: 20
- **Unique Documents Covered**: 8

---

## Q001

Query:
How does the organization recognize customer revenue and allocate transaction prices across deliverables?

Category:
direct_semantic

Expected Document:
confluence-finance-and-legal-dsid-135ae39cdcd342e5b9c65190c87dd6ae-procurement-contracts-and-revrec-playbook-2025

Expected Source:
confluence/finance-and-legal/dsid_135ae39cdcd342e5b9c65190c87dd6ae__procurement-contracts-and-revrec-playbook-2025.txt

Expected Heading:
Revenue Recognition and Billing Policies

Difficulty:
medium

Reason:
Tests natural semantic retrieval for revenue recognition governance and ASC 606 obligation allocation principles without using exact accounting boilerplate in the query.

---

## Q002

Query:
What criteria and scoring dimensions are used to evaluate operational runbooks during simulated recovery game days?

Category:
direct_semantic

Expected Document:
confluence-people-ops-onboarding-dsid-95aaab5e5a6640ffaceadee4bcdb5f76-runbook-retention-and-responder-onboarding-handbook-2026

Expected Source:
confluence/people-ops/onboarding/dsid_95aaab5e5a6640ffaceadee4bcdb5f76__runbook-retention-and-responder-onboarding-handbook-2026.txt

Expected Heading:
Game Day Integration and Scoring Rubric:

Difficulty:
easy

Reason:
Tests retrieval for game day drills and the 80+ point scoring rubric covering readability, execution clarity, instrumentation, evidence collection, and stabilization time.

---

## Q003

Query:
What mandatory metadata attributes must be emitted on request spans to comply with telemetry observability guarantees?

Category:
direct_semantic

Expected Document:
confluence-people-ops-onboarding-dsid-b6c9e2f26e644b15b5be1eed43ed7149-tiered-priority-commitments-and-telemetry-stability-standard-2026

Expected Source:
confluence/people-ops/onboarding/dsid_b6c9e2f26e644b15b5be1eed43ed7149__tiered-priority-commitments-and-telemetry-stability-standard-2026.txt

Expected Heading:
Operational behaviors (detailed):

Difficulty:
medium

Reason:
Tests retrieval for span instrumentation requirements (rw.priority, rw.client_tier, rw.request_nonce, rw.model_variant) based on telemetry emission semantics.

---

## Q004

Query:
What is the end-to-end nomination, calibration, and timeline workflow for employee promotions and role transitions?

Category:
direct_semantic

Expected Document:
confluence-people-ops-onboarding-dsid-2588273815bf4475a35ea5c78f246fa2-cross-functional-onboarding-and-career-support-compass-2026

Expected Source:
confluence/people-ops/onboarding/dsid_2588273815bf4475a35ea5c78f246fa2__cross-functional-onboarding-and-career-support-compass-2026.txt

Expected Heading:
Role transition and promotion process (summary):

Difficulty:
medium

Reason:
Tests direct semantic retrieval for the 4-step promotion process (Nomination, Calibration, Business & Comp review, Decision) and required packet artifacts.

---

## Q005

Query:
What mandatory fields and digital signature components must be included in a compliance evidence bundle manifest?

Category:
direct_semantic

Expected Document:
confluence-people-ops-onboarding-dsid-fe4f3a98cd9642afa7f9a150de313c5c-authn-audit-evidence-correlation-playbook-2028

Expected Source:
confluence/people-ops/onboarding/dsid_fe4f3a98cd9642afa7f9a150de313c5c__authn-audit-evidence-correlation-playbook-2028.txt

Expected Heading:
Evidence bundle manifest (fields)

Difficulty:
easy

Reason:
Tests semantic matching against compliance packaging specifications including evidence ID, time window, tenant list, KMS signing key, and retention policy tag.

---

## Q006

Query:
What are the core operational components and timelines for mentors and buddies supporting new team members?

Category:
direct_semantic

Expected Document:
confluence-people-ops-onboarding-dsid-7656c7c6a6ce4c3baa88c3a7cfb5d658-navigator-program-career-ops-and-tooling-2026

Expected Source:
confluence/people-ops/onboarding/dsid_7656c7c6a6ce4c3baa88c3a7cfb5d658__navigator-program-career-ops-and-tooling-2026.txt

Expected Heading:
4) Mentorship, Sponsorship & Buddy System

Difficulty:
medium

Reason:
Tests retrieval for peer mentorship structures (1:6 mentor-to-mentee ratio, 6 sessions over 3 months, preboarding buddy assignment, and senior leader sponsorship).

---

## Q007

Query:
What target time-to-offer SLA is expected from requisition opening for individual contributor candidate hiring?

Category:
direct_semantic

Expected Document:
confluence-people-ops-onboarding-dsid-951c6983787c4be28703bbb5b5e5edd9-talent-deep-dive-lifecycle-and-benchmarks-2025

Expected Source:
confluence/people-ops/onboarding/dsid_951c6983787c4be28703bbb5b5e5edd9__talent-deep-dive-lifecycle-and-benchmarks-2025.txt

Expected Heading:
Hiring and interview SLAs (operational targets)

Difficulty:
medium

Reason:
Tests retrieval of hiring benchmark metrics (28 days target time-to-offer from req open for most IC hires) in the talent lifecycle benchmark document.

---

## Q008

Query:
What continuous learning stipends, wellness allowances, and retirement benefits are provided to employees?

Category:
direct_semantic

Expected Document:
confluence-people-ops-onboarding-dsid-4b1d1d26a4d64f3c9f0702e7b1d2d3ef-scaled-onboarding-first-90-to-1000-playbook-2028

Expected Source:
confluence/people-ops/onboarding/dsid_4b1d1d26a4d64f3c9f0702e7b1d2d3ef__scaled-onboarding-first-90-to-1000-playbook-2028.txt

Expected Heading:
Benefits & Perks Quick Orientation (2028)

Difficulty:
easy

Reason:
Tests retrieval of employee total rewards benefits, 401(k) match, wellness reimbursement, and annual professional development stipend.

---

## Q009

Query:
How are newly assigned on-call engineers trained, shadowed, and certified before handling emergency production incidents independently?

Category:
cross_document

Expected Document:
confluence-people-ops-onboarding-dsid-95aaab5e5a6640ffaceadee4bcdb5f76-runbook-retention-and-responder-onboarding-handbook-2026

Expected Source:
confluence/people-ops/onboarding/dsid_95aaab5e5a6640ffaceadee4bcdb5f76__runbook-retention-and-responder-onboarding-handbook-2026.txt

Expected Heading:
Responder Onboarding Checklist (for new on-call engineer):

Difficulty:
hard

Reason:
Multiple documents discuss onboarding new team members (4b1d1d26, 25882738), but only 95aaab5e specifies on-call responder milestones (orientation, shadowing shifts, supervised incident runs, game day certification).

---

## Q010

Query:
How does the short-term micro-rotation assignment process operate for employees wishing to explore adjacent roles for a few weeks?

Category:
cross_document

Expected Document:
confluence-people-ops-onboarding-dsid-7656c7c6a6ce4c3baa88c3a7cfb5d658-navigator-program-career-ops-and-tooling-2026

Expected Source:
confluence/people-ops/onboarding/dsid_7656c7c6a6ce4c3baa88c3a7cfb5d658__navigator-program-career-ops-and-tooling-2026.txt

Expected Heading:
3) Micro-rotation and Short-term Assignment Process

Difficulty:
hard

Reason:
Distinguishes temporary 4-12 week micro-rotations with preserved primary roles (Navigator program) from permanent internal transfers requiring 6-month tenure (talent deep dive).

---

## Q011

Query:
What are the quantitative velocity targets and median benchmarks for provisioning access and merging a first pull request?

Category:
cross_document

Expected Document:
confluence-people-ops-onboarding-dsid-951c6983787c4be28703bbb5b5e5edd9-talent-deep-dive-lifecycle-and-benchmarks-2025

Expected Source:
confluence/people-ops/onboarding/dsid_951c6983787c4be28703bbb5b5e5edd9__talent-deep-dive-lifecycle-and-benchmarks-2025.txt

Expected Heading:
Metrics and quality gates (people-ops KPIs)

Difficulty:
hard

Reason:
Both 4b1d1d26 and 951c6983 discuss onboarding progression, but 951c6983 specifically contains the measured KPI benchmarks (median < 48 hours time-to-provision, 7 days time-to-first-PR, >=92% 90-day retention).

---

## Q012

Query:
What are the review frequencies, expiration policies, and retirement rules for operational service documentation?

Category:
cross_document

Expected Document:
confluence-people-ops-onboarding-dsid-95aaab5e5a6640ffaceadee4bcdb5f76-runbook-retention-and-responder-onboarding-handbook-2026

Expected Source:
confluence/people-ops/onboarding/dsid_95aaab5e5a6640ffaceadee4bcdb5f76__runbook-retention-and-responder-onboarding-handbook-2026.txt

Expected Heading:
Runbook Review Cadence and Lifecycle:

Difficulty:
medium

Reason:
Distinguishes operational runbook review lifecycle (quarterly for critical, 18-month deprecation) from compliance log retention policies (fe4f3a98) and contract storage retention (135ae39c).

---

## Q013

Query:
What permissions and systems access are provisioned for new engineers across source control, cloud infrastructure, and identity providers?

Category:
cross_document

Expected Document:
confluence-people-ops-onboarding-dsid-4b1d1d26a4d64f3c9f0702e7b1d2d3ef-scaled-onboarding-first-90-to-1000-playbook-2028

Expected Source:
confluence/people-ops/onboarding/dsid_4b1d1d26a4d64f3c9f0702e7b1d2d3ef__scaled-onboarding-first-90-to-1000-playbook-2028.txt

Expected Heading:
Internal Tools Access Matrix (essential items)

Difficulty:
medium

Reason:
Tests retrieval of developer tooling provisioning (Okta, GitHub, AWS staging, Jira, 1Password) against general systems mentions in other documents.

---

## Q014

Query:
What governance stages and legal redline guardrails regulate commercial vendor contracts before execution?

Category:
cross_document

Expected Document:
confluence-finance-and-legal-dsid-135ae39cdcd342e5b9c65190c87dd6ae-procurement-contracts-and-revrec-playbook-2025

Expected Source:
confluence/finance-and-legal/dsid_135ae39cdcd342e5b9c65190c87dd6ae__procurement-contracts-and-revrec-playbook-2025.txt

Expected Heading:
Contract Lifecycle Management (CLM)

Difficulty:
medium

Reason:
Focuses on commercial contract lifecycle stages and legal redline constraints, contrasting with technical SDLC deployment controls (fe4f3a98).

---

## Q015

Query:
What is the maximum dollar limit and retroactive approval window for emergency vendor spend during critical outages?

Category:
specific_detail

Expected Document:
confluence-finance-and-legal-dsid-135ae39cdcd342e5b9c65190c87dd6ae-procurement-contracts-and-revrec-playbook-2025

Expected Source:
confluence/finance-and-legal/dsid_135ae39cdcd342e5b9c65190c87dd6ae__procurement-contracts-and-revrec-playbook-2025.txt

Expected Heading:
Procurement Procedures

Difficulty:
easy

Reason:
Pinpoints the exact $100k emergency procurement ceiling and 48-hour retroactive Finance sign-off requirement.

---

## Q016

Query:
What is the maximum allowed number of priority classes a service can configure in its declared telemetry budget?

Category:
specific_detail

Expected Document:
confluence-people-ops-onboarding-dsid-b6c9e2f26e644b15b5be1eed43ed7149-tiered-priority-commitments-and-telemetry-stability-standard-2026

Expected Source:
confluence/people-ops/onboarding/dsid_b6c9e2f26e644b15b5be1eed43ed7149__tiered-priority-commitments-and-telemetry-stability-standard-2026.txt

Expected Heading:
Standard requirements (high-level):

Difficulty:
easy

Reason:
Pinpoints the specific rule stating services may declare a maximum of 5 priority buckets within their fidelity budget.

---

## Q017

Query:
What target Mean Time to Evidence is required when assembling audit packages for high-priority security investigations?

Category:
specific_detail

Expected Document:
confluence-people-ops-onboarding-dsid-fe4f3a98cd9642afa7f9a150de313c5c-authn-audit-evidence-correlation-playbook-2028

Expected Source:
confluence/people-ops/onboarding/dsid_fe4f3a98cd9642afa7f9a150de313c5c__authn-audit-evidence-correlation-playbook-2028.txt

Expected Heading:
Metrics and KPIs

Difficulty:
easy

Reason:
Pinpoints the MTTE KPI metric of <= 4 hours and >= 98% evidence completeness target for audit packages.

---

## Q018

Query:
Who must approve formal policy exceptions and deviations when a team cannot meet standard data log storage durations?

Category:
hard_negative

Expected Document:
confluence-people-ops-onboarding-dsid-fe4f3a98cd9642afa7f9a150de313c5c-authn-audit-evidence-correlation-playbook-2028

Expected Source:
confluence/people-ops/onboarding/dsid_fe4f3a98cd9642afa7f9a150de313c5c__authn-audit-evidence-correlation-playbook-2028.txt

Expected Heading:
Risk exceptions and approval workflow

Difficulty:
hard

Reason:
Uses general compliance terms like 'approval', 'exceptions', and 'policy' that abound in the finance procurement matrix (135ae39c), but specifically seeks the security audit retention exception path (Requestor -> Security -> Compliance -> Risk committee).

---

## Q019

Query:
What HTTP header carries the unique request tracking identifier for joining authentication decisions with backend access logs?

Category:
hard_negative

Expected Document:
confluence-people-ops-onboarding-dsid-fe4f3a98cd9642afa7f9a150de313c5c-authn-audit-evidence-correlation-playbook-2028

Expected Source:
confluence/people-ops/onboarding/dsid_fe4f3a98cd9642afa7f9a150de313c5c__authn-audit-evidence-correlation-playbook-2028.txt

Expected Heading:
Technical controls and requirements

Difficulty:
hard

Reason:
Strongly resembles the telemetry priority tracking standard (X-RW-Priority, X-RW-Client-Tier in b6c9e2f2), but specifically targets X-RW-REQ-ID required for authN/authZ audit correlation.

---

## Q020

Query:
Which executive roles must authorize multi-year commitments or SaaS contracts exceeding quarter-million dollar thresholds?

Category:
hard_negative

Expected Document:
confluence-finance-and-legal-dsid-135ae39cdcd342e5b9c65190c87dd6ae-procurement-contracts-and-revrec-playbook-2025

Expected Source:
confluence/finance-and-legal/dsid_135ae39cdcd342e5b9c65190c87dd6ae__procurement-contracts-and-revrec-playbook-2025.txt

Expected Heading:
Approval Matrix (illustrative)

Difficulty:
hard

Reason:
Uses keywords 'commitments', 'thresholds', and 'tiers' that are heavily present in the telemetry priority commitment standard (b6c9e2f2), but tests retrieval of the CFO + General Counsel spend approval requirement for contracts > $250k.

---
