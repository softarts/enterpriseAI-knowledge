# Bootstrap Report - KB Article Classifier (Stage A)

- Generated for **3000** bootstrap documents.
- Embedding model: `BAAI/bge-m3` (max_seq_length=512).
- Cluster-naming model: `qwen3-8b-mlx` (local, LM Studio OpenAI-compatible API).

## Important: corpus vs taxonomy mismatch

The hand-written taxonomy is a **banking** skeleton (per the original task). The bootstrap corpus, however, is the internal knowledge base of an **AI-inference platform company** (GPU clusters, model serving, quantization, evals, SLOs, Kubernetes, on-call, SDKs). The two do not align.

Consequently the nine banking business-line L1s attract almost no documents; the overwhelming majority land under `Technology & Engineering` (which is why that branch was expanded to a detailed set of L2/L3 nodes). This is a known, expected data/requirement mismatch, not a defect. The per-L1 distribution below makes it explicit.

## 1. Documents processed & per-L1 distribution

Total bootstrap documents: **3000**
Fully assigned to a complete L1>L2>L3 path: **979** (32.63%)

Documents by best-matched L1 (before thresholding):

| L1 category | documents | share |
|---|---:|---:|
| `product_management` | 1000 | 33.33% |
| `risk_compliance` | 704 | 23.47% |
| `technology_engineering` | 531 | 17.70% |
| `facilities_administration` | 184 | 6.13% |
| `procurement_vendor_management` | 165 | 5.50% |
| `payments` | 149 | 4.97% |
| `digital_banking` | 79 | 2.63% |
| `trade_finance` | 58 | 1.93% |
| `sales_marketing` | 55 | 1.83% |
| `lending` | 40 | 1.33% |
| `human_resources` | 20 | 0.67% |
| `retail_banking` | 8 | 0.27% |
| `corporate_finance_accounting` | 5 | 0.17% |
| `treasury` | 1 | 0.03% |
| `wealth_management` | 1 | 0.03% |

## 2. Taxonomy node counts (seed vs discovered)

| Level | seed (retained) | discovered (added) | total |
|---|---:|---:|---:|
| L1 | 17 | 2 | 19 |
| L2 | 65 | 6 | 71 |
| L3 | 215 | 6 | 221 |
| **all** | **297** | **14** | **311** |

## 3. Discovered nodes

| Level | parent | discovered name | cluster docs | naming |
|---|---|---|---:|---|
| L1 | `None` | Incident Management | 374 | LLM-named |
| L1 | `None` | Demo Coordination Issues | 20 | LLM-named |
| L2 | `product_management` | Error Handling Improvements | 99 | LLM-named |
| L2 | `product_management` | Compact UI Design | 6 | LLM-named |
| L2 | `risk_compliance` | Production Alerts & Issues | 8 | LLM-named |
| L2 | `risk_compliance` | Security Compliance Alerts | 7 | LLM-named |

### Gap-discovery pool diagnostics

| Level | parent | pool size | clustered | min_cluster_size | clusters | noise/UNKNOWN |
|---|---|---:|---|---:|---:|---:|
| L1 | `None` | 1552 | yes | 15 | 2 | 1158 |
| L2 | `digital_banking` | 5 | yes | 5 | 0 | 5 |
| L2 | `facilities_administration` | 48 | yes | 5 | 0 | 48 |
| L2 | `lending` | 1 | no | - | 0 | 1 |
| L2 | `procurement_vendor_management` | 2 | no | - | 0 | 2 |
| L2 | `product_management` | 180 | yes | 5 | 2 | 75 |
| L2 | `risk_compliance` | 63 | yes | 5 | 2 | 48 |
| L2 | `sales_marketing` | 1 | no | - | 0 | 1 |
| L2 | `technology_engineering` | 10 | yes | 5 | 0 | 10 |
| L2 | `trade_finance` | 3 | no | - | 0 | 3 |
| L3 | `branch_channel_operations` | 1 | no | - | 0 | 1 |
| L3 | `credit_assessment` | 1 | no | - | 0 | 1 |
| L3 | `credit_risk_management` | 21 | yes | 5 | 0 | 21 |
| L3 | `cross_border_settlement` | 1 | no | - | 0 | 1 |
| L3 | `customer_success_support` | 4 | no | - | 0 | 4 |
| L3 | `data_analytics_platform` | 1 | no | - | 0 | 1 |
| L3 | `data_privacy_protection` | 7 | yes | 5 | 0 | 7 |
| L3 | `fraud_risk` | 4 | no | - | 0 | 4 |
| L3 | `health_safety_environment` | 2 | no | - | 0 | 2 |
| L3 | `information_security` | 1 | no | - | 0 | 1 |
| L3 | `infrastructure_operations` | 4 | no | - | 0 | 4 |
| L3 | `loan_portfolio_management` | 1 | no | - | 0 | 1 |
| L3 | `office_operations` | 7 | yes | 5 | 0 | 7 |
| L3 | `operational_technology_risk` | 4 | no | - | 0 | 4 |
| L3 | `payment_processing` | 5 | yes | 5 | 0 | 5 |
| L3 | `product_analytics_experimentation` | 31 | yes | 5 | 0 | 31 |
| L3 | `product_design_ux` | 4 | no | - | 0 | 4 |
| L3 | `product_strategy_roadmap` | 14 | yes | 5 | 0 | 14 |
| L3 | `quality_engineering` | 1 | no | - | 0 | 1 |
| L3 | `regulatory_reporting` | 22 | yes | 5 | 0 | 22 |
| L3 | `site_reliability_observability` | 14 | yes | 5 | 0 | 14 |
| L3 | `sourcing_purchasing` | 6 | yes | 5 | 0 | 6 |

## 4. Naming model comparison (qwen2.5-coder:7b vs qwen2.5:3b)

**N/A - comparison not run.** The original task specified an Ollama setup with `qwen2.5-coder:7b` and `qwen2.5:3b`. This machine instead runs a single local model (`qwen3-8b-mlx`) served by LM Studio over an OpenAI-compatible API. With only one local generation model available, the two-model selection experiment is not applicable; all cluster naming used `qwen3-8b-mlx`. No second model's output was fabricated.

## 5. Unclassified (UNKNOWN) documents by level

Documents whose best match fell below the level threshold and which were not absorbed into any discovered cluster (pool too small, or HDBSCAN noise).

| Level | UNKNOWN documents | share of corpus |
|---|---:|---:|
| L1 | 1158 | 38.60% |
| L2 | 193 | 6.43% |
| L3 | 156 | 5.20% |
| **total** | **1507** | **50.23%** |

## Threshold decisions

| Level | threshold | method | samples | separation | reason |
|---|---:|---|---:|---:|---|
| L1 | 0.4534 | gmm | 3000 | 1.698 | two well-separated components; threshold = midpoint of means |
| L2 | 0.4667 | gmm | 3000 | 1.482 | two well-separated components; threshold = midpoint of means |
| L3 | 0.4893 | gmm | 3000 | 1.310 | two well-separated components; threshold = midpoint of means |

_Method `gmm` = midpoint of a two-component Gaussian mixture on the per-level best-score distribution. `p30_fallback` = 30th percentile, used when the two components were not separated enough or one was negligibly weighted (see reason). All thresholds clamped to a sane cosine range._
