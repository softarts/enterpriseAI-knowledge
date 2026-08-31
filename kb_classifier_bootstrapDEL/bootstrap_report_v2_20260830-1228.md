# Bootstrap Report - KB Article Classifier (Stage A)

- Generated for **23000** bootstrap documents.
- Embedding model: `BAAI/bge-m3` (max_seq_length=512).
- Cluster-naming model: `qwen3-8b-mlx` (local, LM Studio OpenAI-compatible API).

## v1 -> v2 comparison

- Documents: v1 **3000** -> v2 **23000**

### Node counts per level (seed + discovered = total)

| Level | v1 total | v2 total | delta | v1 discovered | v2 discovered |
|---|---:|---:|---:|---:|---:|
| L1 | 19 | 17 | -2 | 2 | 0 |
| L2 | 71 | 77 | +6 | 6 | 12 |
| L3 | 221 | 248 | +27 | 6 | 33 |

### L2/L3 growth under the heavy L1s

Sub-node counts (L2, L3) under the three L1s the brief flags as data-heavy. Growth here means gap discovery found new sub-categories the seed skeleton missed.

| L1 | v1 (L2, L3) | v2 (L2, L3) |
|---|---|---|
| `technology_engineering` | (9, 44) | (9, 46) |
| `product_management` | (5, 9) | (8, 17) |
| `risk_compliance` | (8, 20) | (10, 32) |

### Discovered clusters

- Count: v1 **6** -> v2 **33**

v1 discovered themes:
  - L1 under `None`: Incident Management (374 docs)
  - L1 under `None`: Demo Coordination Issues (20 docs)
  - L2 under `product_management`: Error Handling Improvements (99 docs)
  - L2 under `product_management`: Compact UI Design (6 docs)
  - L2 under `risk_compliance`: Production Alerts & Issues (8 docs)
  - L2 under `risk_compliance`: Security Compliance Alerts (7 docs)

v2 discovered themes:
  - L2 under `facilities_administration`: Deployment Planning (111 docs)
  - L2 under `facilities_administration`: Candidate Scheduling (9 docs)
  - L2 under `facilities_administration`: IAM Evidence Requests (6 docs)
  - L2 under `product_management`: Release Documentation (71 docs)
  - L2 under `product_management`: Launch Preparation (47 docs)
  - L2 under `product_management`: Customer Embeddings Issues (46 docs)
  - L2 under `product_management`: MidMarket Analytics SaaS (30 docs)
  - L2 under `product_management`: SDK Version Migration (13 docs)
  - L2 under `risk_compliance`: Compliance Alerts (90 docs)
  - L2 under `risk_compliance`: Postmortem & Action Items (12 docs)
  - L2 under `risk_compliance`: SOC2 Compliance Coordination (7 docs)
  - L2 under `risk_compliance`: Financial Milestones & Compliance (5 docs)
  - L3 under `credit_risk_management`: Feature Rollout Coordination (12 docs)
  - L3 under `credit_risk_management`: KMS/HSM Controls (11 docs)
  - L3 under `credit_risk_management`: Access Control Compliance (5 docs)
  - L3 under `fraud_risk`: Fraud Detection Anomalies (10 docs)
  - L3 under `fraud_risk`: Production Incident Reports (5 docs)
  - L3 under `office_operations`: POC Scheduling & Coordination (39 docs)
  - L3 under `office_operations`: Multi-Region Operations (8 docs)
  - L3 under `operational_technology_risk`: Operational Risk Alerts (12 docs)
  - L3 under `operational_technology_risk`: Data Processing Agreements (5 docs)
  - L3 under `payment_processing`: Payment Pilot Planning (6 docs)
  - L3 under `payment_processing`: Regulated POC Migration (6 docs)
  - L3 under `product_analytics_experimentation`: UX Policy Experimentation (24 docs)
  - L3 under `product_analytics_experimentation`: API Error Handling (20 docs)
  - L3 under `product_analytics_experimentation`: Product Testing & Feedback (18 docs)
  - L3 under `product_analytics_experimentation`: Cloud Marketplace Listings (6 docs)
  - L3 under `product_analytics_experimentation`: Product UX Iterations (5 docs)
  - L3 under `regulatory_reporting`: Customer Communication Postmortems (11 docs)
  - L3 under `regulatory_reporting`: Metering Anomaly Detection (8 docs)
  - L3 under `regulatory_reporting`: Auditor Request Tracking (6 docs)
  - L3 under `site_reliability_observability`: Partner Collaboration (10 docs)
  - L3 under `site_reliability_observability`: Executive Demo Coordination (6 docs)

### Threshold values

| Level | v1 | v2 | v1 method | v2 method |
|---|---:|---:|---|---|
| L1 | 0.453363 | 0.452088 | gmm | gmm |
| L2 | 0.466739 | 0.465386 | gmm | gmm |
| L3 | 0.489344 | 0.48702 | gmm | gmm |

### UNKNOWN share by level

| Level | v1 UNKNOWN | v1 share | v2 UNKNOWN | v2 share |
|---|---:|---:|---:|---:|
| L1 | 1158 | 38.60% | 11639 | 50.60% |
| L2 | 193 | 6.43% | 1761 | 7.66% |
| L3 | 156 | 5.20% | 867 | 3.77% |
| **total** | **1507** | **50.23%** | **14267** | **62.03%** |

- Fully assigned (all three levels): v1 **979** (32.63%) -> v2 **8053** (35.01%)

## Important: corpus vs taxonomy mismatch

The hand-written taxonomy is a **banking** skeleton (per the original task). The bootstrap corpus, however, is the internal knowledge base of an **AI-inference platform company** (GPU clusters, model serving, quantization, evals, SLOs, Kubernetes, on-call, SDKs). The two do not align.

Consequently the nine banking business-line L1s attract almost no documents; the overwhelming majority land under `Technology & Engineering` (which is why that branch was expanded to a detailed set of L2/L3 nodes). This is a known, expected data/requirement mismatch, not a defect. The per-L1 distribution below makes it explicit.

## 1. Documents processed & per-L1 distribution

Total bootstrap documents: **23000**
Fully assigned to a complete L1>L2>L3 path: **8053** (35.01%)

Documents by best-matched L1 (before thresholding):

| L1 category | documents | share |
|---|---:|---:|
| `product_management` | 8100 | 35.22% |
| `risk_compliance` | 5222 | 22.70% |
| `technology_engineering` | 3869 | 16.82% |
| `facilities_administration` | 1266 | 5.50% |
| `procurement_vendor_management` | 1258 | 5.47% |
| `payments` | 1077 | 4.68% |
| `digital_banking` | 585 | 2.54% |
| `sales_marketing` | 511 | 2.22% |
| `trade_finance` | 476 | 2.07% |
| `lending` | 344 | 1.50% |
| `human_resources` | 158 | 0.69% |
| `corporate_finance_accounting` | 56 | 0.24% |
| `retail_banking` | 50 | 0.22% |
| `legal` | 15 | 0.07% |
| `treasury` | 9 | 0.04% |
| `wealth_management` | 2 | 0.01% |
| `corporate_banking` | 2 | 0.01% |

## 2. Taxonomy node counts (seed vs discovered)

| Level | seed (retained) | discovered (added) | total |
|---|---:|---:|---:|
| L1 | 17 | 0 | 17 |
| L2 | 65 | 12 | 77 |
| L3 | 215 | 33 | 248 |
| **all** | **297** | **45** | **342** |

## 3. Discovered nodes

| Level | parent | discovered name | cluster docs | naming |
|---|---|---|---:|---|
| L2 | `facilities_administration` | Deployment Planning | 111 | LLM-named |
| L2 | `facilities_administration` | Candidate Scheduling | 9 | LLM-named |
| L2 | `facilities_administration` | IAM Evidence Requests | 6 | LLM-named |
| L2 | `product_management` | Release Documentation | 71 | LLM-named |
| L2 | `product_management` | Launch Preparation | 47 | LLM-named |
| L2 | `product_management` | Customer Embeddings Issues | 46 | LLM-named |
| L2 | `product_management` | MidMarket Analytics SaaS | 30 | LLM-named |
| L2 | `product_management` | SDK Version Migration | 13 | LLM-named |
| L2 | `risk_compliance` | Compliance Alerts | 90 | LLM-named |
| L2 | `risk_compliance` | Postmortem & Action Items | 12 | LLM-named |
| L2 | `risk_compliance` | SOC2 Compliance Coordination | 7 | LLM-named |
| L2 | `risk_compliance` | Financial Milestones & Compliance | 5 | LLM-named |
| L3 | `credit_risk_management` | Feature Rollout Coordination | 12 | LLM-named |
| L3 | `credit_risk_management` | KMS/HSM Controls | 11 | LLM-named |
| L3 | `credit_risk_management` | Access Control Compliance | 5 | LLM-named |
| L3 | `fraud_risk` | Fraud Detection Anomalies | 10 | LLM-named |
| L3 | `fraud_risk` | Production Incident Reports | 5 | LLM-named |
| L3 | `office_operations` | POC Scheduling & Coordination | 39 | LLM-named |
| L3 | `office_operations` | Multi-Region Operations | 8 | LLM-named |
| L3 | `operational_technology_risk` | Operational Risk Alerts | 12 | LLM-named |
| L3 | `operational_technology_risk` | Data Processing Agreements | 5 | LLM-named |
| L3 | `payment_processing` | Payment Pilot Planning | 6 | LLM-named |
| L3 | `payment_processing` | Regulated POC Migration | 6 | LLM-named |
| L3 | `product_analytics_experimentation` | UX Policy Experimentation | 24 | LLM-named |
| L3 | `product_analytics_experimentation` | API Error Handling | 20 | LLM-named |
| L3 | `product_analytics_experimentation` | Product Testing & Feedback | 18 | LLM-named |
| L3 | `product_analytics_experimentation` | Cloud Marketplace Listings | 6 | LLM-named |
| L3 | `product_analytics_experimentation` | Product UX Iterations | 5 | LLM-named |
| L3 | `regulatory_reporting` | Customer Communication Postmortems | 11 | LLM-named |
| L3 | `regulatory_reporting` | Metering Anomaly Detection | 8 | LLM-named |
| L3 | `regulatory_reporting` | Auditor Request Tracking | 6 | LLM-named |
| L3 | `site_reliability_observability` | Partner Collaboration | 10 | LLM-named |
| L3 | `site_reliability_observability` | Executive Demo Coordination | 6 | LLM-named |

### Gap-discovery pool diagnostics

| Level | parent | pool size | clustered | min_cluster_size | clusters | noise/UNKNOWN |
|---|---|---:|---|---:|---:|---:|
| L1 | `None` | 11639 | yes | 116 | 0 | 11639 |
| L2 | `corporate_finance_accounting` | 2 | no | - | 0 | 2 |
| L2 | `digital_banking` | 37 | yes | 5 | 0 | 37 |
| L2 | `facilities_administration` | 326 | yes | 5 | 3 | 200 |
| L2 | `human_resources` | 2 | no | - | 0 | 2 |
| L2 | `lending` | 13 | yes | 5 | 0 | 13 |
| L2 | `payments` | 1 | no | - | 0 | 1 |
| L2 | `procurement_vendor_management` | 16 | yes | 5 | 0 | 16 |
| L2 | `product_management` | 1287 | yes | 12 | 5 | 1080 |
| L2 | `risk_compliance` | 466 | yes | 5 | 4 | 352 |
| L2 | `sales_marketing` | 10 | yes | 5 | 0 | 10 |
| L2 | `technology_engineering` | 31 | yes | 5 | 0 | 31 |
| L2 | `trade_finance` | 17 | yes | 5 | 0 | 17 |
| L3 | `ai_ml_platform` | 4 | no | - | 0 | 4 |
| L3 | `anti_money_laundering` | 5 | yes | 5 | 0 | 5 |
| L3 | `architecture_technical_standards` | 4 | no | - | 0 | 4 |
| L3 | `branch_channel_operations` | 3 | no | - | 0 | 3 |
| L3 | `brand_communications` | 1 | no | - | 0 | 1 |
| L3 | `card_payments` | 2 | no | - | 0 | 2 |
| L3 | `corporate_lending` | 3 | no | - | 0 | 3 |
| L3 | `credit_assessment` | 2 | no | - | 0 | 2 |
| L3 | `credit_risk_management` | 105 | yes | 5 | 3 | 77 |
| L3 | `cross_border_settlement` | 13 | yes | 5 | 0 | 13 |
| L3 | `customer_success_support` | 7 | yes | 5 | 0 | 7 |
| L3 | `data_analytics_platform` | 7 | yes | 5 | 0 | 7 |
| L3 | `data_privacy_protection` | 58 | yes | 5 | 0 | 58 |
| L3 | `employee_relations` | 1 | no | - | 0 | 1 |
| L3 | `fintech_partnerships` | 8 | yes | 5 | 0 | 8 |
| L3 | `fraud_risk` | 37 | yes | 5 | 2 | 22 |
| L3 | `health_safety_environment` | 21 | yes | 5 | 0 | 21 |
| L3 | `information_security` | 7 | yes | 5 | 0 | 7 |
| L3 | `infrastructure_operations` | 19 | yes | 5 | 0 | 19 |
| L3 | `intellectual_property` | 1 | no | - | 0 | 1 |
| L3 | `letters_of_credit` | 3 | no | - | 0 | 3 |
| L3 | `loan_portfolio_management` | 8 | yes | 5 | 0 | 8 |
| L3 | `office_operations` | 64 | yes | 5 | 2 | 17 |
| L3 | `open_banking_apis` | 2 | no | - | 0 | 2 |
| L3 | `operational_technology_risk` | 40 | yes | 5 | 2 | 23 |
| L3 | `payment_processing` | 20 | yes | 5 | 2 | 8 |
| L3 | `payment_regulation_standards` | 2 | no | - | 0 | 2 |
| L3 | `product_analytics_experimentation` | 254 | yes | 5 | 5 | 181 |
| L3 | `product_design_ux` | 22 | yes | 5 | 0 | 22 |
| L3 | `product_strategy_roadmap` | 81 | yes | 5 | 0 | 81 |
| L3 | `quality_engineering` | 1 | no | - | 0 | 1 |
| L3 | `regulatory_reporting` | 156 | yes | 5 | 3 | 131 |
| L3 | `site_reliability_observability` | 93 | yes | 5 | 2 | 77 |
| L3 | `software_development` | 10 | yes | 5 | 0 | 10 |
| L3 | `sourcing_purchasing` | 31 | yes | 5 | 0 | 31 |
| L3 | `third_party_risk_due_diligence` | 1 | no | - | 0 | 1 |
| L3 | `vendor_contracts` | 3 | no | - | 0 | 3 |
| L3 | `workforce_operations` | 1 | no | - | 0 | 1 |

## 4. Naming model comparison (qwen2.5-coder:7b vs qwen2.5:3b)

**N/A - comparison not run.** The original task specified an Ollama setup with `qwen2.5-coder:7b` and `qwen2.5:3b`. This machine instead runs a single local model (`qwen3-8b-mlx`) served by LM Studio over an OpenAI-compatible API. With only one local generation model available, the two-model selection experiment is not applicable; all cluster naming used `qwen3-8b-mlx`. No second model's output was fabricated.

## 5. Unclassified (UNKNOWN) documents by level

Documents whose best match fell below the level threshold and which were not absorbed into any discovered cluster (pool too small, or HDBSCAN noise).

| Level | UNKNOWN documents | share of corpus |
|---|---:|---:|
| L1 | 11639 | 50.60% |
| L2 | 1761 | 7.66% |
| L3 | 867 | 3.77% |
| **total** | **14267** | **62.03%** |

## Threshold decisions

| Level | threshold | method | samples | separation | reason |
|---|---:|---|---:|---:|---|
| L1 | 0.4521 | gmm | 23000 | 1.577 | two well-separated components; threshold = midpoint of means |
| L2 | 0.4654 | gmm | 23000 | 1.601 | two well-separated components; threshold = midpoint of means |
| L3 | 0.4870 | gmm | 23000 | 1.475 | two well-separated components; threshold = midpoint of means |

_Method `gmm` = midpoint of a two-component Gaussian mixture on the per-level best-score distribution. `p30_fallback` = 30th percentile, used when the two components were not separated enough or one was negligibly weighted (see reason). All thresholds clamped to a sane cosine range._
