# Bootstrap Report - KB Article Classifier (Stage A)

- Generated for **50000** bootstrap documents.
- Embedding model: `BAAI/bge-m3` (max_seq_length=512).
- Cluster-naming model: `qwen3-8b-mlx` (local, LM Studio OpenAI-compatible API).

## Important: corpus vs taxonomy mismatch

The hand-written taxonomy is a **banking** skeleton (per the original task). The bootstrap corpus, however, is the internal knowledge base of an **AI-inference platform company** (GPU clusters, model serving, quantization, evals, SLOs, Kubernetes, on-call, SDKs). The two do not align.

Consequently the nine banking business-line L1s attract almost no documents; the overwhelming majority land under `Technology & Engineering` (which is why that branch was expanded to a detailed set of L2/L3 nodes). This is a known, expected data/requirement mismatch, not a defect. The per-L1 distribution below makes it explicit.

## 1. Documents processed & per-L1 distribution

Total bootstrap documents: **50000**
Fully assigned to a complete L1>L2>L3 path: **12914** (25.83%)

Documents by best-matched L1 (before thresholding):

| L1 category | documents | share |
|---|---:|---:|
| `service_latency_alerts` | 22936 | 45.87% |
| `demo_coordination` | 10175 | 20.35% |
| `product_management` | 5830 | 11.66% |
| `risk_compliance` | 3640 | 7.28% |
| `technology_engineering` | 2315 | 4.63% |
| `procurement_vendor_management` | 1403 | 2.81% |
| `facilities_administration` | 735 | 1.47% |
| `payments` | 731 | 1.46% |
| `trade_finance` | 546 | 1.09% |
| `sales_marketing` | 520 | 1.04% |
| `digital_banking` | 419 | 0.84% |
| `lending` | 344 | 0.69% |
| `human_resources` | 238 | 0.48% |
| `corporate_finance_accounting` | 82 | 0.16% |
| `retail_banking` | 55 | 0.11% |
| `legal` | 27 | 0.05% |
| `treasury` | 2 | 0.00% |
| `wealth_management` | 1 | 0.00% |
| `corporate_banking` | 1 | 0.00% |

## 2. Taxonomy node counts (seed vs discovered)

| Level | seed (retained) | discovered (added) | total |
|---|---:|---:|---:|
| L1 | 17 | 2 | 19 |
| L2 | 65 | 2 | 67 |
| L3 | 215 | 2 | 217 |
| **all** | **297** | **6** | **303** |

## 3. Discovered nodes

| Level | parent | discovered name | cluster docs | naming |
|---|---|---|---:|---|
| L1 | `None` | Release Operations | 6751 | LLM-named |
| L1 | `None` | Billing Anomalies | 1950 | LLM-named |
| L2 | `demo_coordination` | Demo Coordination Updates | 924 | LLM-named |
| L2 | `demo_coordination` | New Manager Onboarding | 21 | LLM-named |
| L2 | `service_latency_alerts` | Performance Alert Monitoring | 573 | LLM-named |
| L2 | `service_latency_alerts` | Benchmark Launch Materials | 86 | LLM-named |
| L2 | `service_latency_alerts` | Latency Benchmarking | 29 | LLM-named |
| L3 | `service_latency_alerts_general` | Model Performance Alerts | 90 | LLM-named |
| L3 | `service_latency_alerts_general` | Hosted API Integration | 16 | LLM-named |

### Gap-discovery pool diagnostics

| Level | parent | pool size | clustered | min_cluster_size | clusters | noise/UNKNOWN |
|---|---|---:|---|---:|---:|---:|
| L1 | `None` | 27056 | yes | 50 | 2 | 18355 |
| L2 | `demo_coordination` | 4034 | yes | 15 | 2 | 3089 |
| L2 | `product_management` | 10 | no | 15 | 0 | 10 |
| L2 | `service_latency_alerts` | 4834 | yes | 15 | 3 | 4146 |
| L3 | `customer_api_issues` | 51 | yes | 15 | 0 | 51 |
| L3 | `demo_coordination_general` | 87 | yes | 15 | 0 | 87 |
| L3 | `fraud_risk` | 3 | no | - | 0 | 3 |
| L3 | `launch_preparation` | 117 | yes | 15 | 0 | 117 |
| L3 | `midmarket_analytics_saas` | 97 | yes | 15 | 0 | 97 |
| L3 | `office_operations` | 3 | no | - | 0 | 3 |
| L3 | `product_analytics_experimentation` | 7 | no | 15 | 0 | 7 |
| L3 | `regulatory_reporting` | 1 | no | - | 0 | 1 |
| L3 | `release_documentation` | 56 | yes | 15 | 0 | 56 |
| L3 | `service_latency_alerts_general` | 730 | yes | 15 | 2 | 624 |

## 4. Naming model comparison (qwen2.5-coder:7b vs qwen2.5:3b)

**N/A - comparison not run.** The original task specified an Ollama setup with `qwen2.5-coder:7b` and `qwen2.5:3b`. This machine instead runs a single local model (`qwen3-8b-mlx`) served by LM Studio over an OpenAI-compatible API. With only one local generation model available, the two-model selection experiment is not applicable; all cluster naming used `qwen3-8b-mlx`. No second model's output was fabricated.

## 5. Unclassified (UNKNOWN) documents by level

Documents whose best match fell below the level threshold and which were not absorbed into any discovered cluster (pool too small, or HDBSCAN noise).

| Level | UNKNOWN documents | share of corpus |
|---|---:|---:|
| L1 | 18355 | 36.71% |
| L2 | 7245 | 14.49% |
| L3 | 1046 | 2.09% |
| **total** | **26646** | **53.29%** |

## Threshold decisions

| Level | threshold | method | samples | separation | reason |
|---|---:|---|---:|---:|---|
| L1 | 0.4853 | gmm | 50000 | 1.084 | two well-separated components; threshold = midpoint of means |
| L2 | 0.4400 | gmm | 50000 | 2.128 | two well-separated components; threshold = midpoint of means |
| L3 | 0.4491 | gmm | 50000 | 1.986 | two well-separated components; threshold = midpoint of means |

_Method `gmm` = midpoint of a two-component Gaussian mixture on the per-level best-score distribution. `p30_fallback` = 30th percentile, used when the two components were not separated enough or one was negligibly weighted (see reason). All thresholds clamped to a sane cosine range._
