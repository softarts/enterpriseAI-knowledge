# 设计决策与 seed taxonomy 设计稿

本文件记录已经想清楚但还没落成代码的设计。**新机器可以直接照抄，不需要重新推导。**

---

## A. 已确定的技术决策及理由

| 决策点 | 选择 | 理由 |
|---|---|---|
| HDBSCAN 实现 | `sklearn.cluster.HDBSCAN`（sklearn ≥1.3） | 环境里 sklearn 1.9.0 已自带，不必额外装 `hdbscan` 包，少一个编译依赖 |
| 截断长度 | `max_seq_length=512`，正文取前 2000 字符 | bge-m3 标称 8192，但注意力开销随长度超线性增长；主题分类的信号几乎全在标题+开头几段，runbook/邮件长尾多是流程细节，反而模糊主题质心。512 是检索模型标准操作点 |
| 标题加权 | 标题重复 1 次再接正文 | 标题是最具区分度的字段，重复一次即可廉价上权，无需自定义 pooling |
| 向量存储 dtype | fp16 落盘，float32 计算 | 省一半磁盘（51 万×1024×2B ≈ 1.05 GB）；读回后**重新归一化**，因为 fp16 往返会轻微破坏单位范数，而下游是用点积当余弦相似度 |
| 归一化 | `normalize_embeddings=True` | 之后点积即余弦，且 HDBSCAN 用 euclidean 在单位球上与余弦距离单调等价，可走快路径 |
| 锚点文本 | `"<面包屑>: <desc>"` | 纯 desc 无法区分同名兄弟节点，例如 `Treasury > Cash Management` vs `Corporate Banking > Cash Management Services`。带父级面包屑可消歧 |
| 抽样策略 | 比例分层 + 每层保底 3 篇 | 纯比例会让占比 <0.01% 的小 stratum 抽到 0 篇，其主题对缺口发现完全不可见；纯保底又会让 slack（55.8%）和一个 40 篇的小目录同权 |
| 分层粒度 | `<source>/<subdir>`，depth=2 | 即 `slack/eng-ml`、`gmail/david_kim` 这一级。保证每个频道/邮箱/space 都有代表 |
| GMM 单峰判定 | 两分量均值差 < 1.0 倍合并标准差，或任一分量权重 < 0.05 | 原 prompt 只说"单峰用 P30 fallback"但没定义单峰。用**分量间隔**（合并标准差为单位）+ **分量权重下限**两个判据；权重极小的分量是拟合假象而非真实总体。触发时日志和 `thresholds.json` 里都标 `p30_fallback` |
| 阈值兜底钳制 | 钳到 [0.15, 0.80] | 防止退化拟合产生"全归类"或"全不归类"的阈值 |
| HDBSCAN `min_cluster_size` | `max(5, min(1% × 池大小, 400))` | 原 prompt 建议 5，但 5 对一个 4 万篇的池会碎出几百个 5 篇的节点。按池大小自适应放大 |
| 每父节点新增节点上限 | 8 个，按 cluster 大小取前 8 | 保证产出的 taxonomy 人类可读 |
| 超大池处理 | >20,000 篇先抽样聚类，其余按最近质心归入 | HDBSCAN 内存吃紧 |

---

## B. Seed taxonomy 设计稿（完整树，直接照抄）

### B.1 结构与写法

拆成 3 个文件，避免单文件过大：
- `config/taxonomy_seed_business.py` → `BUSINESS_SEED`（9 个业务线 L1）
- `config/taxonomy_seed_functions.py` → `FUNCTION_SEED`（8 个职能 L1，含新增的 Product Management）
- `config/taxonomy_seed.py` → `SEED_TAXONOMY = {**BUSINESS_SEED, **FUNCTION_SEED}`

用已写好的 `config/_node.py`：

```python
from ._node import node

BUSINESS_SEED = {
    "retail_banking": node(
        "Retail Banking",
        "Products and services sold to individual consumers through branches and "
        "digital channels, covering everyday accounts, personal borrowing and "
        "personal card products.",
        {
            "deposit_accounts": node(
                "Deposit Accounts",
                "Personal savings, current and checking accounts including account "
                "opening, interest accrual, statements, overdraft handling and closure.",
                {
                    "savings_accounts": node(
                        "Savings Accounts",
                        "Interest-bearing personal savings and time deposit products, "
                        "including rate tiers, term deposits, certificates of deposit "
                        "and maturity rollover."),
                    # ... 其余 L3
                },
            ),
        },
    ),
}
```

**`desc` 写作要求（重要，直接决定匹配质量）**：
- 必须是**一句完整的描述性句子**，不是标签词堆砌。
- 要**主动铺开你预期会出现在匹配文档里的词汇**（这是被 embed 的文本，词汇覆盖度就是召回率）。
- 不要复述 name。`"Payment Gateway: payment gateway"` 是无效锚点。
- 长度 25~45 词较合适。

### B.2 业务线分支（9 个 L1）

```
Retail Banking
├── Deposit Accounts
│   ├── Savings Accounts
│   ├── Current & Checking Accounts
│   ├── Account Opening & KYC Onboarding
│   └── Account Servicing & Maintenance
├── Consumer Lending
│   ├── Mortgage Lending
│   ├── Auto Loans
│   ├── Personal & Unsecured Loans
│   └── Loan Servicing & Collections
├── Retail Cards
│   ├── Credit Card Issuance
│   ├── Debit & Prepaid Cards
│   ├── Card Rewards & Loyalty
│   └── Cardholder Disputes & Chargebacks
└── Branch & Channel Operations            [扩展]
    ├── Branch Operations
    ├── ATM & Self-Service Network
    └── Contact Centre Operations

Corporate Banking
├── Corporate Accounts
│   ├── Account Opening & KYB
│   ├── Account Structures & Mandates
│   └── Corporate Account Servicing
├── Cash Management Services
│   ├── Collections & Receivables
│   ├── Disbursements & Payables
│   ├── Liquidity Structures & Sweeping
│   └── Host-to-Host & ERP Integration
└── Trade Services
    ├── Documentary Collections
    ├── Bank Guarantees & Standby LCs
    └── Supply Chain Finance

Payments
├── Payment Processing
│   ├── Domestic Transfers & ACH
│   ├── Real-Time & Instant Payments
│   ├── Wire Transfers & RTGS
│   ├── Payment Clearing & Settlement
│   └── Payment Exceptions & Reconciliation
├── Payment Gateway
│   ├── Merchant Onboarding & Acquiring
│   ├── Gateway APIs & Integration
│   ├── Tokenization & Payment Security
│   └── Gateway Availability & Throughput
├── Card Payments
│   ├── Card Scheme Rules & Interchange
│   ├── Authorization & Switching
│   ├── Card Clearing & Settlement
│   └── Payment Fraud Prevention
└── Payment Regulation & Standards         [扩展]
    ├── ISO 20022 & Message Standards
    └── Payment Services Regulation

Lending
├── Corporate Lending
│   ├── Syndicated & Structured Loans
│   ├── Working Capital Facilities
│   └── Loan Documentation & Covenants
├── Credit Assessment
│   ├── Credit Scoring Models
│   ├── Underwriting Policy & Approval
│   └── Collateral & Security Valuation
└── Loan Portfolio Management              [扩展]
    ├── Portfolio Monitoring & Early Warning
    └── Non-Performing Loans & Workout

Treasury
├── Cash Management
│   ├── Nostro & Cash Position Management
│   └── Intraday Funding & Settlement
├── Liquidity Management
│   ├── Liquidity Risk & LCR/NSFR
│   └── Funding & Wholesale Borrowing
└── Markets & Asset-Liability Management   [扩展]
    ├── Interest Rate & FX Risk
    └── Investment Portfolio & Securities

Risk & Compliance
├── Anti-Money Laundering
│   ├── Transaction Monitoring & Alerts
│   ├── Sanctions & Watchlist Screening
│   ├── Customer Due Diligence & KYC Policy
│   └── Suspicious Activity Reporting
├── Regulatory Reporting
│   ├── Prudential & Capital Reporting
│   ├── Transaction & Trade Reporting
│   ├── Regulatory Change Management
│   └── Regulatory Examinations & Internal Audit
├── Credit Risk Management
│   ├── Credit Risk Models & IFRS 9 ECL
│   ├── Credit Limits & Exposure Management
│   └── Stress Testing & Capital Adequacy
├── Operational & Technology Risk           [扩展]
│   ├── Operational Risk & Control Framework
│   ├── Third-Party & Outsourcing Risk
│   ├── Business Continuity & Resilience
│   └── Incident & Loss Event Management
├── Data Privacy & Protection               [扩展]
│   ├── Privacy Policy & Data Subject Rights
│   └── Data Retention & Records Management
└── Fraud Risk                              [扩展]
    └── Fraud Detection & Investigation

Wealth Management
├── Private Banking
│   ├── HNW Client Onboarding & Coverage
│   ├── Discretionary Portfolio Management
│   └── Trust & Estate Planning
└── Investment Advisory
    ├── Investment Product Suitability
    ├── Research & Market Commentary
    └── Fund Distribution & Custody

Trade Finance
├── Letters of Credit
│   ├── LC Issuance & Advising
│   ├── Document Examination & Discrepancies
│   └── LC Amendments & Settlement
├── Cross-Border Settlement
│   ├── Correspondent Banking & SWIFT
│   ├── FX Conversion & Remittance
│   └── Cross-Border Compliance & Screening
└── Export & Import Finance                 [扩展]
    ├── Export Credit & Receivables Discounting
    └── Import Financing & Trade Loans

Digital Banking
├── Mobile Banking
│   ├── Mobile App Features & Journeys
│   ├── Mobile Authentication & Device Binding
│   └── Mobile App Release & Quality
├── Open Banking APIs
│   ├── API Products & Developer Portal
│   ├── Consent & Authorization
│   └── Third-Party Provider Management
├── Fintech Partnerships
│   ├── Embedded Finance & BaaS
│   └── Partner Integration & Certification
└── Digital Channel Experience              [扩展]
    ├── Internet Banking Platform
    ├── Digital Onboarding & eKYC
    └── Conversational & AI Assistants
```

### B.3 职能分支（8 个 L1）

`Technology & Engineering` 被**刻意展开得最细**（9 个 L2 / ~35 个 L3）——原因见 `01_STATUS.md` §3.2：语料 95%+ 是技术内容，如果只留原 prompt 要求的 2 个 L2，几十万篇文档会全挤在两个节点下，L3 相似度会集体偏低、阈值失真、缺口聚类爆炸。

```
Corporate Finance & Accounting
├── Financial Reporting
│   ├── Month-End Close & Consolidation
│   ├── Statutory & External Reporting
│   ├── Management Reporting & MI
│   └── Accounting Policy & Standards
├── Tax & Treasury Operations
│   ├── Direct & Indirect Tax Compliance
│   ├── Transfer Pricing
│   └── Internal Funding & Intercompany
├── Planning & Performance                  [扩展]
│   ├── Budgeting & Forecasting
│   ├── Cost Allocation & Unit Economics
│   └── Revenue Recognition & Billing
└── Accounts Payable & Receivable           [扩展]
    ├── Invoice Processing & Payables
    └── Expense Management & Reimbursement

Human Resources
├── Recruitment
│   ├── Sourcing & Candidate Pipeline
│   ├── Interviewing & Assessment
│   ├── Offers & Hiring Decisions
│   └── Onboarding & New Hire Enablement
├── Compensation & Benefits
│   ├── Salary Structure & Pay Review
│   ├── Equity & Incentive Plans
│   ├── Health, Insurance & Wellbeing Benefits
│   ├── Leave & Time-Off Policy
│   └── Payroll Operations
├── Employee Relations
│   ├── Performance Management & Reviews
│   ├── Career Framework & Promotion
│   ├── Learning & Development
│   ├── Conduct, Grievance & Disciplinary
│   └── Workplace Culture & Engagement
└── Workforce Operations                    [扩展]
    ├── HR Systems & Employee Data
    ├── Workforce Planning & Headcount
    └── Offboarding & Exit

Legal
├── Contract Management
│   ├── Customer Contracts & MSAs
│   ├── Contract Templates & Playbooks
│   └── Contract Lifecycle & Renewals
├── Corporate Governance
│   ├── Board & Committee Governance
│   ├── Entity Management & Licensing
│   └── Policy Framework & Attestation
├── Disputes & Regulatory Legal             [扩展]
│   ├── Litigation & Dispute Resolution
│   └── Regulatory Liaison & Legal Opinions
└── Intellectual Property                   [扩展]
    ├── IP & Trademark Management
    └── Open Source Licensing

Technology & Engineering                    [大幅扩展]
├── Infrastructure & Operations
│   ├── Cloud Infrastructure & Capacity
│   ├── Kubernetes & Container Platform
│   ├── Networking & Connectivity
│   ├── Compute & GPU Fleet Management
│   ├── Infrastructure as Code & Provisioning
│   └── Cost & Capacity Optimization
├── Software Development
│   ├── Service & API Development
│   ├── SDKs & Client Libraries
│   ├── Code Review & Engineering Standards
│   ├── Build, CI/CD & Release Engineering
│   ├── Developer Tooling & Local Environment
│   └── Technical Documentation & Examples
├── Site Reliability & Observability        [扩展]
│   ├── Monitoring, Metrics & Dashboards
│   ├── Logging & Tracing
│   ├── Alerting & On-Call Rotation
│   ├── Incident Response & Postmortems
│   ├── SLO, SLI & Error Budgets
│   └── Performance & Load Testing
├── Information Security                    [扩展]
│   ├── Identity, Authentication & Access Control
│   ├── Encryption & Key Management
│   ├── Vulnerability & Patch Management
│   ├── Security Monitoring & Threat Detection
│   ├── Security Review & Threat Modelling
│   └── Audit Logging & Evidence
├── Data & Analytics Platform               [扩展]
│   ├── Data Pipelines & ETL
│   ├── Data Warehouse & Modelling
│   ├── BI, Dashboards & Reporting Tools
│   └── Data Quality & Lineage
├── AI & Machine Learning Platform          [扩展]
│   ├── Model Serving & Inference Runtime
│   ├── Model Registry & Lifecycle
│   ├── Model Evaluation & Benchmarking
│   ├── Prompt & Retrieval Engineering
│   ├── Model Optimization & Quantization
│   └── ML Experimentation & Feature Rollout
├── Architecture & Technical Standards      [扩展]
│   ├── Architecture Decision Records
│   ├── API Design Standards
│   └── Platform Architecture & Design Reviews
├── Quality Engineering                     [扩展]
│   ├── Test Automation & Coverage
│   ├── Test Environments & Data
│   └── Defect Triage & Regression
└── IT Service Management                   [扩展]
    ├── Change & Release Management
    ├── Service Desk & Support Requests
    ├── Access Requests & Provisioning
    └── Deployment & Environment Operations

Sales & Marketing
├── Brand & Communications
│   ├── Brand & Creative Assets
│   ├── Public Relations & Media
│   ├── Internal Communications & All-Hands
│   └── Events & Conferences
├── Customer Acquisition
│   ├── Lead Generation & Demand Gen
│   ├── Sales Pipeline & Deal Management
│   ├── Pricing, Quotes & Proposals
│   └── Competitive & Market Intelligence
├── Product Marketing                       [扩展]
│   ├── Positioning & Messaging
│   ├── Launch & Go-to-Market
│   └── Content & Thought Leadership
└── Customer Success & Support              [扩展]
    ├── Customer Onboarding & Adoption
    ├── Account Health & QBR
    ├── Support Case Handling & Escalation
    └── Renewals, Churn & Expansion

Procurement & Vendor Management
├── Vendor Contracts
│   ├── Vendor Selection & RFP
│   ├── Vendor Contract Negotiation
│   └── Vendor Performance & SLA Management
├── Sourcing & Purchasing                   [扩展]
│   ├── Purchase Requisition & PO
│   └── Software & Cloud Licensing
└── Third-Party Risk & Due Diligence        [扩展]
    ├── Vendor Security & Compliance Review
    └── Vendor Onboarding & Offboarding

Facilities & Administration
├── Office Operations
│   ├── Workplace & Office Services
│   ├── Physical Security & Access
│   ├── Travel & Expense Administration
│   └── Equipment & Asset Management
└── Health, Safety & Environment            [扩展]
    ├── Workplace Health & Safety
    └── Sustainability & Environmental

Product Management                          [新增 L1，见下方说明]
├── Product Strategy & Roadmap
│   ├── Roadmap & Prioritization
│   ├── Product Requirements & Specs
│   └── Product Discovery & Research
├── Product Analytics & Experimentation
│   ├── Usage Metrics & Adoption Analysis
│   └── A/B Testing & Experiments
└── Product Design & UX
    ├── UX Research & Usability
    └── Design System & UI Patterns
```

**关于新增 `Product Management` L1**：原 prompt 的 L1 清单里没有，但明确写了"根据bootstrap语料实际内容增删枝节"。语料里 `linear/product-management`、`confluence/product-docs`、`slack/product`、`slack/design`、`linear/design` 合计体量不小；不给它独立 L1，这批文档会被硬塞进 `Technology & Engineering`，污染技术分支的质心。**在 `taxonomy.py` 里它仍标 `source: "seed"`，但要在文件头注释和 `bootstrap_report.md` 里注明这是骨架扩展项。** 如果不想偏离原 prompt，删掉这一段即可，其余逻辑不受影响。

### B.4 规模小计

| 层级 | seed 节点数（约） |
|---|---|
| L1 | 17（9 业务线 + 8 职能） |
| L2 | 56 |
| L3 | 172 |

---

## C. 待写模块的接口约定

```python
# bootstrap/anchors.py
@dataclass
class Anchor:
    key: str            # "payments"
    path_keys: tuple    # ("payments","payment_gateway","gateway_apis")
    level: int          # 1 / 2 / 3
    name: str
    desc: str
    source: str
    parent_key: str | None
    breadcrumb: str     # "Payments > Payment Gateway > Gateway APIs & Integration"

def flatten_taxonomy(tax: dict) -> list[Anchor]
def anchor_text(a: Anchor, include_breadcrumb: bool) -> str
def embed_anchors(embedder, anchors, cache_path) -> np.ndarray   # [n_anchors, 1024]，带缓存

# bootstrap/matching.py
@dataclass
class MatchResult:
    l1_key: str;  l1_score: float
    l2_key: str | None;  l2_score: float
    l3_key: str | None;  l3_score: float

def match_hierarchical(doc_vecs, anchors, anchor_vecs) -> list[MatchResult]
# L1 全局 argmax；L2 只在选中 L1 的子节点里 argmax；L3 同理。
# 分数 = 点积（两侧都已归一化，即余弦）。
# 分批处理，别一次性构造 [511887, n_anchors] 矩阵。

# bootstrap/thresholds.py
@dataclass
class ThresholdResult:
    level: str            # "L1"/"L2"/"L3"
    value: float
    method: str           # "gmm" | "p30_fallback"
    reason: str           # fallback 原因，写进日志和报告
    n_samples: int
    gmm_means: tuple | None
    gmm_weights: tuple | None
    separation: float | None

def fit_threshold(scores: np.ndarray, level: str, cfg) -> ThresholdResult

# bootstrap/discovery.py
@dataclass
class DiscoveredCluster:
    parent_key: str | None    # None 表示 L1 层缺口
    level: int
    doc_indices: np.ndarray
    centroid: np.ndarray
    representative_doc_indices: list[int]   # 离质心最近的 5 篇
    size: int

def build_unassigned_pools(matches, thresholds) -> dict[tuple[int,str|None], list[int]]
def choose_min_cluster_size(pool_size, cfg) -> int
def discover(pools, doc_vecs, cfg) -> list[DiscoveredCluster]

# bootstrap/naming.py
@dataclass
class NamingResult:
    name: str
    desc: str
    model: str
    raw_response: str
    node_key: str        # 由 name 生成的 snake_case，需去重

def name_cluster(cluster, docs, model, cfg) -> NamingResult
def run_model_comparison(clusters, docs, cfg) -> list[dict]   # 7b vs 3b 对比实验
# 要求模型输出严格 JSON: {"name": "...", "desc": "..."}；解析失败重试 max_retries 次，
# 再失败则退化为 "Uncategorized <parent> Topic N" 并在报告里记为 naming_failed。
# 通过 requests/urllib 调 POST {ollama_host}/api/generate, stream=false, format="json"。

# bootstrap/emit.py
def write_taxonomy_py(tax: dict, path: str, meta: dict) -> None   # 生成可 import 的 .py
def write_thresholds_json(results: list[ThresholdResult], path: str) -> None

# bootstrap/report.py
def write_report(path: str, stats: BootstrapStats) -> None
```

`thresholds.json` 除原 prompt 要求的字段外，建议附带诊断信息（不影响阶段 B 读取）：

```json
{
  "L1": 0.42, "L2": 0.38, "L3": 0.33,
  "method_used": {"L1": "gmm", "L2": "gmm", "L3": "p30_fallback"},
  "diagnostics": {
    "L3": {"reason": "component separation 0.62 < 1.0", "n_samples": 511887,
           "gmm_means": [0.29, 0.35], "gmm_weights": [0.4, 0.6], "percentile_used": 30}
  },
  "generated_at": "...", "n_documents": 511887,
  "embedding_model": "BAAI/bge-m3", "max_seq_length": 512
}
```
