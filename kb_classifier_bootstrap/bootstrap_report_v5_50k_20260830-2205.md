# Bootstrap Report - KB Article Classifier (Stage A)

- Generated for **50000** bootstrap documents.
- Embedding model: `BAAI/bge-m3` (max_seq_length=512).
- Cluster-naming model: `qwen3-8b-mlx` (local, LM Studio OpenAI-compatible API).

## v1 -> v2 comparison

- Documents: v1 **50000** -> v2 **50000**

### Node counts per level (seed + discovered = total)

| Level | v1 total | v2 total | delta | v1 discovered | v2 discovered |
|---|---:|---:|---:|---:|---:|
| L1 | 19 | 21 | +2 | 2 | 4 |
| L2 | 67 | 76 | +9 | 2 | 11 |
| L3 | 217 | 228 | +11 | 2 | 13 |

### L2/L3 growth under the heavy L1s

Sub-node counts (L2, L3) under the three L1s the brief flags as data-heavy. Growth here means gap discovery found new sub-categories the seed skeleton missed.

| L1 | v1 (L2, L3) | v2 (L2, L3) |
|---|---|---|
| `technology_engineering` | (9, 44) | (9, 44) |
| `product_management` | (3, 7) | (3, 7) |
| `risk_compliance` | (6, 18) | (6, 18) |

### Discovered clusters

- Count: v1 **9** -> v2 **11**

v1 discovered themes:
  - L1 under `None`: Release Operations (6751 docs)
  - L1 under `None`: Billing Anomalies (1950 docs)
  - L2 under `demo_coordination`: Demo Coordination Updates (924 docs)
  - L2 under `demo_coordination`: New Manager Onboarding (21 docs)
  - L2 under `service_latency_alerts`: Performance Alert Monitoring (573 docs)
  - L2 under `service_latency_alerts`: Benchmark Launch Materials (86 docs)
  - L2 under `service_latency_alerts`: Latency Benchmarking (29 docs)
  - L3 under `service_latency_alerts_general`: Model Performance Alerts (90 docs)
  - L3 under `service_latency_alerts_general`: Hosted API Integration (16 docs)

v2 discovered themes:
  - L1 under `None`: Performance Monitoring (8766 docs)
  - L1 under `None`: SDK Onboarding Issues (670 docs)
  - L2 under `billing_anomalies`: High Latency Events (1611 docs)
  - L2 under `billing_anomalies`: Duplicate Webhook Events (36 docs)
  - L2 under `billing_anomalies`: SDK Documentation Updates (24 docs)
  - L2 under `release_operations`: Release Preparation (376 docs)
  - L2 under `release_operations`: Release Window Coordination (306 docs)
  - L2 under `release_operations`: Auditor Coordination (36 docs)
  - L2 under `release_operations`: Air-Gapped POC Requests (26 docs)
  - L3 under `billing_anomalies_general`: Gateway Performance Issues (92 docs)
  - L3 under `billing_anomalies_general`: Double Charges (28 docs)

### Threshold values

| Level | v1 | v2 | v1 method | v2 method |
|---|---:|---:|---|---|
| L1 | 0.485276 | 0.473086 | gmm | gmm |
| L2 | 0.440041 | 0.441168 | gmm | gmm |
| L3 | 0.449115 | 0.450724 | gmm | gmm |

### UNKNOWN share by level

| Level | v1 UNKNOWN | v1 share | v2 UNKNOWN | v2 share |
|---|---:|---:|---:|---:|
| L1 | 18355 | 36.71% | 15346 | 30.69% |
| L2 | 7245 | 14.49% | 9443 | 18.89% |
| L3 | 1046 | 2.09% | 1364 | 2.73% |
| **total** | **26646** | **53.29%** | **26153** | **52.31%** |

- Fully assigned (all three levels): v1 **12914** (25.83%) -> v2 **11876** (23.75%)

## Important: corpus vs taxonomy mismatch

The hand-written taxonomy is a **banking** skeleton (per the original task). The bootstrap corpus, however, is the internal knowledge base of an **AI-inference platform company** (GPU clusters, model serving, quantization, evals, SLOs, Kubernetes, on-call, SDKs). The two do not align.

Consequently the nine banking business-line L1s attract almost no documents; the overwhelming majority land under `Technology & Engineering` (which is why that branch was expanded to a detailed set of L2/L3 nodes). This is a known, expected data/requirement mismatch, not a defect. The per-L1 distribution below makes it explicit.

## 1. Documents processed & per-L1 distribution

Total bootstrap documents: **50000**
Fully assigned to a complete L1>L2>L3 path: **11876** (23.75%)

Documents by best-matched L1 (before thresholding):

| L1 category | documents | share |
|---|---:|---:|
| `billing_anomalies` | 16880 | 33.76% |
| `release_operations` | 11161 | 22.32% |
| `product_management` | 9161 | 18.32% |
| `risk_compliance` | 3965 | 7.93% |
| `technology_engineering` | 3875 | 7.75% |
| `procurement_vendor_management` | 1440 | 2.88% |
| `facilities_administration` | 736 | 1.47% |
| `sales_marketing` | 695 | 1.39% |
| `payments` | 692 | 1.38% |
| `lending` | 364 | 0.73% |
| `digital_banking` | 363 | 0.73% |
| `trade_finance` | 307 | 0.61% |
| `human_resources` | 251 | 0.50% |
| `retail_banking` | 45 | 0.09% |
| `corporate_finance_accounting` | 35 | 0.07% |
| `legal` | 25 | 0.05% |
| `treasury` | 4 | 0.01% |
| `wealth_management` | 1 | 0.00% |

## 2. Taxonomy node counts (seed vs discovered)

| Level | seed (retained) | discovered (added) | total |
|---|---:|---:|---:|
| L1 | 17 | 4 | 21 |
| L2 | 65 | 11 | 76 |
| L3 | 215 | 13 | 228 |
| **all** | **297** | **28** | **325** |

## 3. Discovered nodes

| Level | parent | discovered name | cluster docs | naming |
|---|---|---|---:|---|
| L1 | `None` | Performance Monitoring | 8766 | LLM-named |
| L1 | `None` | SDK Onboarding Issues | 670 | LLM-named |
| L2 | `billing_anomalies` | High Latency Events | 1611 | LLM-named |
| L2 | `billing_anomalies` | Duplicate Webhook Events | 36 | LLM-named |
| L2 | `billing_anomalies` | SDK Documentation Updates | 24 | LLM-named |
| L2 | `release_operations` | Release Preparation | 376 | LLM-named |
| L2 | `release_operations` | Release Window Coordination | 306 | LLM-named |
| L2 | `release_operations` | Auditor Coordination | 36 | LLM-named |
| L2 | `release_operations` | Air-Gapped POC Requests | 26 | LLM-named |
| L3 | `billing_anomalies_general` | Gateway Performance Issues | 92 | LLM-named |
| L3 | `billing_anomalies_general` | Double Charges | 28 | LLM-named |

### Gap-discovery pool diagnostics

| Level | parent | pool size | clustered | min_cluster_size | clusters | noise/UNKNOWN |
|---|---|---:|---|---:|---:|---:|
| L1 | `None` | 24782 | yes | 50 | 2 | 15346 |
| L2 | `billing_anomalies` | 7359 | yes | 22 | 3 | 5688 |
| L2 | `facilities_administration` | 6 | no | 15 | 0 | 6 |
| L2 | `product_management` | 150 | yes | 15 | 0 | 150 |
| L2 | `release_operations` | 4340 | yes | 15 | 4 | 3596 |
| L2 | `risk_compliance` | 3 | no | - | 0 | 3 |
| L3 | `architecture_technical_standards` | 1 | no | - | 0 | 1 |
| L3 | `billing_anomalies_general` | 823 | yes | 15 | 2 | 703 |
| L3 | `credit_risk_management` | 1 | no | - | 0 | 1 |
| L3 | `data_privacy_protection` | 7 | no | 15 | 0 | 7 |
| L3 | `fintech_partnerships` | 1 | no | - | 0 | 1 |
| L3 | `fraud_risk` | 4 | no | - | 0 | 4 |
| L3 | `health_safety_environment` | 1 | no | - | 0 | 1 |
| L3 | `information_security` | 1 | no | - | 0 | 1 |
| L3 | `office_operations` | 5 | no | 15 | 0 | 5 |
| L3 | `product_analytics_experimentation` | 32 | yes | 15 | 0 | 32 |
| L3 | `product_design_ux` | 3 | no | - | 0 | 3 |
| L3 | `product_strategy_roadmap` | 2 | no | - | 0 | 2 |
| L3 | `regulatory_reporting` | 1 | no | - | 0 | 1 |
| L3 | `release_operations_general` | 601 | yes | 15 | 0 | 601 |
| L3 | `site_reliability_observability` | 1 | no | - | 0 | 1 |

## 4. Naming model comparison (qwen2.5-coder:7b vs qwen2.5:3b)

**N/A - comparison not run.** The original task specified an Ollama setup with `qwen2.5-coder:7b` and `qwen2.5:3b`. This machine instead runs a single local model (`qwen3-8b-mlx`) served by LM Studio over an OpenAI-compatible API. With only one local generation model available, the two-model selection experiment is not applicable; all cluster naming used `qwen3-8b-mlx`. No second model's output was fabricated.

## 5. Unclassified (UNKNOWN) documents by level

Documents whose best match fell below the level threshold and which were not absorbed into any discovered cluster (pool too small, or HDBSCAN noise).

| Level | UNKNOWN documents | share of corpus |
|---|---:|---:|
| L1 | 15346 | 30.69% |
| L2 | 9443 | 18.89% |
| L3 | 1364 | 2.73% |
| **total** | **26153** | **52.31%** |

## Threshold decisions

| Level | threshold | method | samples | separation | reason |
|---|---:|---|---:|---:|---|
| L1 | 0.4731 | gmm | 50000 | 1.155 | two well-separated components; threshold = midpoint of means |
| L2 | 0.4412 | gmm | 50000 | 2.461 | two well-separated components; threshold = midpoint of means |
| L3 | 0.4507 | gmm | 50000 | 2.732 | two well-separated components; threshold = midpoint of means |

_Method `gmm` = midpoint of a two-component Gaussian mixture on the per-level best-score distribution. `p30_fallback` = 30th percentile, used when the two components were not separated enough or one was negligibly weighted (see reason). All thresholds clamped to a sane cosine range._
