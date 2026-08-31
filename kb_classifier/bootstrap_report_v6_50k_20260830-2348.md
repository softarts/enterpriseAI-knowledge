# Bootstrap Report - KB Article Classifier (Stage A)

- Generated for **50000** bootstrap documents.
- Embedding model: `BAAI/bge-m3` (max_seq_length=512).
- Cluster-naming model: `qwen3-8b-mlx` (local, LM Studio OpenAI-compatible API).

## v1 -> v2 comparison

- Documents: v1 **50000** -> v2 **50000**

### Node counts per level (seed + discovered = total)

| Level | v1 total | v2 total | delta | v1 discovered | v2 discovered |
|---|---:|---:|---:|---:|---:|
| L1 | 21 | 23 | +2 | 4 | 6 |
| L2 | 76 | 86 | +10 | 11 | 21 |
| L3 | 228 | 242 | +14 | 13 | 27 |

### L2/L3 growth under the heavy L1s

Sub-node counts (L2, L3) under the three L1s the brief flags as data-heavy. Growth here means gap discovery found new sub-categories the seed skeleton missed.

| L1 | v1 (L2, L3) | v2 (L2, L3) |
|---|---|---|
| `technology_engineering` | (9, 44) | (9, 44) |
| `product_management` | (3, 7) | (3, 7) |
| `risk_compliance` | (6, 18) | (6, 18) |

### Discovered clusters

- Count: v1 **11** -> v2 **14**

v1 discovered themes:
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

v2 discovered themes:
  - L1 under `None`: Model Serving Monitoring (5903 docs)
  - L1 under `None`: Redwood Demo Coordination (3560 docs)
  - L2 under `performance_monitoring`: High Latency Alerts (780 docs)
  - L2 under `performance_monitoring`: Benchmark Narrative Development (109 docs)
  - L2 under `performance_monitoring`: Streaming Latency Optimization (58 docs)
  - L2 under `performance_monitoring`: Observability Console Scope (26 docs)
  - L2 under `sdk_onboarding_issues`: Canary Deployment Monitoring (135 docs)
  - L2 under `sdk_onboarding_issues`: Onboarding Kickoff Coordination (46 docs)
  - L2 under `sdk_onboarding_issues`: SDK Documentation Updates (38 docs)
  - L2 under `sdk_onboarding_issues`: Onboarding Sample App Issues (16 docs)
  - L3 under `duplicate_webhook_events`: GPU Queue Anomalies (29 docs)
  - L3 under `duplicate_webhook_events`: Hosted API Outages (18 docs)
  - L3 under `release_window_coordination`: Release Coordination Logistics (95 docs)
  - L3 under `release_window_coordination`: Release Window Coordination (83 docs)

### Threshold values

| Level | v1 | v2 | v1 method | v2 method |
|---|---:|---:|---|---|
| L1 | 0.473086 | 0.493101 | gmm | gmm |
| L2 | 0.441168 | 0.474702 | gmm | gmm |
| L3 | 0.450724 | 0.463687 | gmm | gmm |

### UNKNOWN share by level

| Level | v1 UNKNOWN | v1 share | v2 UNKNOWN | v2 share |
|---|---:|---:|---:|---:|
| L1 | 15346 | 30.69% | 17755 | 35.51% |
| L2 | 9443 | 18.89% | 8943 | 17.89% |
| L3 | 1364 | 2.73% | 2664 | 5.33% |
| **total** | **26153** | **52.31%** | **29362** | **58.72%** |

- Fully assigned (all three levels): v1 **11876** (23.75%) -> v2 **9742** (19.48%)

## Important: corpus vs taxonomy mismatch

The hand-written taxonomy is a **banking** skeleton (per the original task). The bootstrap corpus, however, is the internal knowledge base of an **AI-inference platform company** (GPU clusters, model serving, quantization, evals, SLOs, Kubernetes, on-call, SDKs). The two do not align.

Consequently the nine banking business-line L1s attract almost no documents; the overwhelming majority land under `Technology & Engineering` (which is why that branch was expanded to a detailed set of L2/L3 nodes). This is a known, expected data/requirement mismatch, not a defect. The per-L1 distribution below makes it explicit.

## 1. Documents processed & per-L1 distribution

Total bootstrap documents: **50000**
Fully assigned to a complete L1>L2>L3 path: **9742** (19.48%)

Documents by best-matched L1 (before thresholding):

| L1 category | documents | share |
|---|---:|---:|
| `performance_monitoring` | 16313 | 32.63% |
| `sdk_onboarding_issues` | 9801 | 19.60% |
| `billing_anomalies` | 8219 | 16.44% |
| `release_operations` | 5753 | 11.51% |
| `product_management` | 3219 | 6.44% |
| `risk_compliance` | 1841 | 3.68% |
| `technology_engineering` | 1527 | 3.05% |
| `procurement_vendor_management` | 1024 | 2.05% |
| `facilities_administration` | 512 | 1.02% |
| `sales_marketing` | 446 | 0.89% |
| `payments` | 387 | 0.77% |
| `trade_finance` | 240 | 0.48% |
| `lending` | 234 | 0.47% |
| `human_resources` | 222 | 0.44% |
| `digital_banking` | 169 | 0.34% |
| `corporate_finance_accounting` | 33 | 0.07% |
| `retail_banking` | 32 | 0.06% |
| `legal` | 25 | 0.05% |
| `treasury` | 2 | 0.00% |
| `wealth_management` | 1 | 0.00% |

## 2. Taxonomy node counts (seed vs discovered)

| Level | seed (retained) | discovered (added) | total |
|---|---:|---:|---:|
| L1 | 17 | 6 | 23 |
| L2 | 65 | 21 | 86 |
| L3 | 215 | 27 | 242 |
| **all** | **297** | **54** | **351** |

## 3. Discovered nodes

| Level | parent | discovered name | cluster docs | naming |
|---|---|---|---:|---|
| L1 | `None` | Model Serving Monitoring | 5903 | LLM-named |
| L1 | `None` | Redwood Demo Coordination | 3560 | LLM-named |
| L2 | `performance_monitoring` | High Latency Alerts | 780 | LLM-named |
| L2 | `performance_monitoring` | Benchmark Narrative Development | 109 | LLM-named |
| L2 | `performance_monitoring` | Streaming Latency Optimization | 58 | LLM-named |
| L2 | `performance_monitoring` | Observability Console Scope | 26 | LLM-named |
| L2 | `sdk_onboarding_issues` | Canary Deployment Monitoring | 135 | LLM-named |
| L2 | `sdk_onboarding_issues` | Onboarding Kickoff Coordination | 46 | LLM-named |
| L2 | `sdk_onboarding_issues` | SDK Documentation Updates | 38 | LLM-named |
| L2 | `sdk_onboarding_issues` | Onboarding Sample App Issues | 16 | LLM-named |
| L3 | `duplicate_webhook_events` | GPU Queue Anomalies | 29 | LLM-named |
| L3 | `duplicate_webhook_events` | Hosted API Outages | 18 | LLM-named |
| L3 | `release_window_coordination` | Release Coordination Logistics | 95 | LLM-named |
| L3 | `release_window_coordination` | Release Window Coordination | 83 | LLM-named |

### Gap-discovery pool diagnostics

| Level | parent | pool size | clustered | min_cluster_size | clusters | noise/UNKNOWN |
|---|---|---:|---|---:|---:|---:|
| L1 | `None` | 27218 | yes | 50 | 2 | 17755 |
| L2 | `billing_anomalies` | 197 | yes | 15 | 0 | 197 |
| L2 | `digital_banking` | 1 | no | - | 0 | 1 |
| L2 | `facilities_administration` | 14 | no | 15 | 0 | 14 |
| L2 | `performance_monitoring` | 6838 | yes | 20 | 4 | 5865 |
| L2 | `product_management` | 191 | yes | 15 | 0 | 191 |
| L2 | `release_operations` | 3 | no | - | 0 | 3 |
| L2 | `risk_compliance` | 22 | yes | 15 | 0 | 22 |
| L2 | `sdk_onboarding_issues` | 2885 | yes | 15 | 4 | 2650 |
| L3 | `air_gapped_poc_requests` | 55 | yes | 15 | 0 | 55 |
| L3 | `auditor_coordination` | 191 | yes | 15 | 0 | 191 |
| L3 | `data_privacy_protection` | 1 | no | - | 0 | 1 |
| L3 | `duplicate_webhook_events` | 1610 | yes | 15 | 2 | 1563 |
| L3 | `fraud_risk` | 1 | no | - | 0 | 1 |
| L3 | `high_latency_events` | 49 | yes | 15 | 0 | 49 |
| L3 | `office_operations` | 1 | no | - | 0 | 1 |
| L3 | `performance_monitoring_general` | 34 | yes | 15 | 0 | 34 |
| L3 | `product_analytics_experimentation` | 7 | no | 15 | 0 | 7 |
| L3 | `product_design_ux` | 1 | no | - | 0 | 1 |
| L3 | `release_preparation` | 205 | yes | 15 | 0 | 205 |
| L3 | `release_window_coordination` | 598 | yes | 15 | 2 | 420 |
| L3 | `sdk_documentation_updates` | 134 | yes | 15 | 0 | 134 |
| L3 | `sdk_onboarding_issues_general` | 1 | no | - | 0 | 1 |
| L3 | `sourcing_purchasing` | 1 | no | - | 0 | 1 |

## 4. Naming model comparison (qwen2.5-coder:7b vs qwen2.5:3b)

**N/A - comparison not run.** The original task specified an Ollama setup with `qwen2.5-coder:7b` and `qwen2.5:3b`. This machine instead runs a single local model (`qwen3-8b-mlx`) served by LM Studio over an OpenAI-compatible API. With only one local generation model available, the two-model selection experiment is not applicable; all cluster naming used `qwen3-8b-mlx`. No second model's output was fabricated.

## 5. Unclassified (UNKNOWN) documents by level

Documents whose best match fell below the level threshold and which were not absorbed into any discovered cluster (pool too small, or HDBSCAN noise).

| Level | UNKNOWN documents | share of corpus |
|---|---:|---:|
| L1 | 17755 | 35.51% |
| L2 | 8943 | 17.89% |
| L3 | 2664 | 5.33% |
| **total** | **29362** | **58.72%** |

## Threshold decisions

| Level | threshold | method | samples | separation | reason |
|---|---:|---|---:|---:|---|
| L1 | 0.4931 | gmm | 50000 | 1.159 | two well-separated components; threshold = midpoint of means |
| L2 | 0.4747 | gmm | 50000 | 2.234 | two well-separated components; threshold = midpoint of means |
| L3 | 0.4637 | gmm | 50000 | 1.931 | two well-separated components; threshold = midpoint of means |

_Method `gmm` = midpoint of a two-component Gaussian mixture on the per-level best-score distribution. `p30_fallback` = 30th percentile, used when the two components were not separated enough or one was negligibly weighted (see reason). All thresholds clamped to a sane cosine range._
