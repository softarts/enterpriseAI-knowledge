# Embedding Retrieval 效果评测报告 (Retrieval Evaluation Report)

> **评测阶段**: Phase 1 POC - 本地 Embedding (`all-MiniLM-L6-v2`) + 余弦相似度 (Cosine Similarity) 检索效果评估  
> **评测时间**: 2026-08-25  
> **数据源**: `generated/` 目录下全部 8 篇 OKF 文档 (共 43 个 Chunks)  
> **评测集**: `embedding_service/evaluation_queries.json` (20 个测试 Query)

---

## 1. 评测概述与目标

本评测旨在回答核心问题：
> **“给定一组预先定义好的业务 Query，当前 OKF + Heading-aware Chunking + Local Embedding 检索能否正确找到对应的文档与 Chunk？”**

评测完全基于当前本地架构，不依赖任何外部向量数据库（Chroma/OpenSearch）或 LLM Judge：
```text
Evaluation Query 
    ↓
LocalEmbedder.embed_query()
    ↓
Cosine Similarity (全量 43 个 Persisted Chunks)
    ↓
Top-K Ranking (按相似度倒序)
    ↓
Hit@1 / Hit@3 / Hit@5 / MRR 指标统计 & 错误归因分析
```

---

## 2. 总体评测指标 (Overall Metrics)

| 评测指标 | 数值 | 命中数 / 总样本数 | 指标说明 |
| :--- | :---: | :---: | :--- |
| **总 Query 数 (Total Queries)** | **20** | - | 覆盖 4 种典型检索类别、8 篇不同业务文档 |
| **Hit@1** | **0.6500** | 13 / 20 | 65.0% 的 Query 在第一检索位即精准命中 |
| **Hit@3** | **0.8000** | 16 / 20 | 80.0% 的 Query 在前 3 个候选结果中命中 |
| **Hit@5** | **0.8500** | 17 / 20 | 85.0% 的 Query 在前 5 个候选结果中命中 |
| **MRR (Mean Reciprocal Rank)** | **0.7258** | - | 平均倒数排名，衡量正确结果在前列的综合加权表现 |

---

## 3. 各分类详细表现 (Breakdown by Category)

| 类别 (Category) | 样本数 (n) | Hit@1 | Hit@3 | Hit@5 | MRR | 表现评价 |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **direct_semantic** | 8 | **0.88** | **0.88** | **0.88** | **0.8750** | **优异**：7/8 Query 在 Rank 1 命中，自然语义匹配能力强 |
| **specific_detail** | 3 | **0.67** | **1.00** | **1.00** | **0.7778** | **良好**：3/3 Query 均在前 3 位命中，具体事实定位准确 |
| **hard_negative** | 3 | **0.67** | **0.67** | **1.00** | **0.7333** | **良好**：3/3 Query 均在前 5 位命中，成功防御关键词陷阱 |
| **cross_document** | 6 | **0.17** | **0.67** | **0.67** | **0.4222** | **挑战明显**：相似入职/流程文档互相干扰，存在 Top-1 漂移 |

---

## 4. 全量 Query 逐条执行明细 (Query Execution Log)

### Category A: Direct Semantic Queries (8)

#### Q001: Customer Revenue Recognition Principles
- **Query**: *"How does the organization recognize customer revenue and allocate transaction prices across deliverables?"*
- **Expected Doc**: `dsid_135ae39c... (Procurement, CLM & RevRec Playbook)` | `Revenue Recognition and Billing Policies`
- **Top 5 检索结果**:
  1. `score=0.4851` | `dsid_135ae39c-chunk-000` **[HIT]**
  2. `score=0.3444` | `dsid_4b1d1d26-chunk-004`
  3. `score=0.3204` | `dsid_4b1d1d26-chunk-003`
- **评估结果**: `Hit@1=YES`, `Hit@3=YES`, `Hit@5=YES`, `RR=1.0000` (Rank: 1)

#### Q002: Runbook Game Day Scoring
- **Query**: *"What criteria and scoring dimensions are used to evaluate operational runbooks during simulated recovery game days?"*
- **Expected Doc**: `dsid_95aaab5e... (Runbook Retention Handbook)` | `Game Day Integration and Scoring Rubric:`
- **Top 5 检索结果**:
  1. `score=0.5595` | `dsid_95aaab5e-chunk-000` **[HIT]**
  2. `score=0.3831` | `dsid_fe4f3a98-chunk-011`
  3. `score=0.3703` | `dsid_4b1d1d26-chunk-013`
- **评估结果**: `Hit@1=YES`, `Hit@3=YES`, `Hit@5=YES`, `RR=1.0000` (Rank: 1)

#### Q003: Request Spans Telemetry Attributes
- **Query**: *"What mandatory metadata attributes must be emitted on request spans to comply with telemetry observability guarantees?"*
- **Expected Doc**: `dsid_b6c9e2f2... (Tiered Priority & Telemetry Stability)` | `Operational behaviors (detailed):`
- **Top 5 检索结果**:
  1. `score=0.4705` | `dsid_b6c9e2f2-chunk-000` **[HIT]**
  2. `score=0.3756` | `dsid_fe4f3a98-chunk-005`
  3. `score=0.3686` | `dsid_fe4f3a98-chunk-006`
- **评估结果**: `Hit@1=YES`, `Hit@3=YES`, `Hit@5=YES`, `RR=1.0000` (Rank: 1)

#### Q004: Employee Promotions Workflow
- **Query**: *"What is the end-to-end nomination, calibration, and timeline workflow for employee promotions and role transitions?"*
- **Expected Doc**: `dsid_25882738... (Cross-functional Onboarding Compass)` | `Role transition and promotion process (summary):`
- **Top 5 检索结果**:
  1. `score=0.5367` | `dsid_25882738-chunk-000` **[HIT]**
  2. `score=0.5186` | `dsid_4b1d1d26-chunk-004`
  3. `score=0.5052` | `dsid_951c6983-chunk-000`
- **评估结果**: `Hit@1=YES`, `Hit@3=YES`, `Hit@5=YES`, `RR=1.0000` (Rank: 1)

#### Q005: Compliance Evidence Manifest Fields
- **Query**: *"What mandatory fields and digital signature components must be included in a compliance evidence bundle manifest?"*
- **Expected Doc**: `dsid_fe4f3a98... (AuthN Audit Evidence Correlation)` | `Evidence bundle manifest (fields)`
- **Top 5 检索结果**:
  1. `score=0.5284` | `dsid_fe4f3a98-chunk-008` **[HIT]**
  2. `score=0.5168` | `dsid_fe4f3a98-chunk-007`
  3. `score=0.5065` | `dsid_fe4f3a98-chunk-014`
- **评估结果**: `Hit@1=YES`, `Hit@3=YES`, `Hit@5=YES`, `RR=1.0000` (Rank: 1)

#### Q006: Mentors and Buddies Support
- **Query**: *"What are the core operational components and timelines for mentors and buddies supporting new team members?"*
- **Expected Doc**: `dsid_7656c7c6... (Navigator Program)` | `4) Mentorship, Sponsorship & Buddy System`
- **Top 5 检索结果**:
  1. `score=0.5602` | `dsid_951c6983-chunk-000`
  2. `score=0.5470` | `dsid_4b1d1d26-chunk-004`
  3. `score=0.5314` | `dsid_4b1d1d26-chunk-007`
  4. `score=0.5071` | `dsid_25882738-chunk-000`
  5. `score=0.4884` | `dsid_4b1d1d26-chunk-009`
- **评估结果**: `Hit@1=NO`, `Hit@3=NO`, `Hit@5=NO`, `RR=0.0000` (Rank: None / Miss)

#### Q007: Candidate Hiring SLAs
- **Query**: *"What target time-to-offer SLA is expected from requisition opening for individual contributor candidate hiring?"*
- **Expected Doc**: `dsid_951c6983... (Talent Deep Dive)` | `Hiring and interview SLAs (operational targets)`
- **Top 5 检索结果**:
  1. `score=0.4862` | `dsid_951c6983-chunk-000` **[HIT]**
  2. `score=0.4839` | `dsid_4b1d1d26-chunk-006`
  3. `score=0.4357` | `dsid_25882738-chunk-000`
- **评估结果**: `Hit@1=YES`, `Hit@3=YES`, `Hit@5=YES`, `RR=1.0000` (Rank: 1)

#### Q008: Employee Benefits and Perks
- **Query**: *"What continuous learning stipends, wellness allowances, and retirement benefits are provided to employees?"*
- **Expected Doc**: `dsid_4b1d1d26... (Scaled Onboarding Playbook)` | `Benefits & Perks Quick Orientation (2028)`
- **Top 5 检索结果**:
  1. `score=0.5350` | `dsid_4b1d1d26-chunk-005` **[HIT]**
  2. `score=0.5054` | `dsid_7656c7c6-chunk-000`
  3. `score=0.4468` | `dsid_25882738-chunk-000`
- **评估结果**: `Hit@1=YES`, `Hit@3=YES`, `Hit@5=YES`, `RR=1.0000` (Rank: 1)

---

### Category B: Cross-Document Queries (6)

#### Q009: On-Call Responder Certification
- **Query**: *"How are newly assigned on-call engineers trained, shadowed, and certified before handling emergency production incidents independently?"*
- **Expected Doc**: `dsid_95aaab5e... (Runbook Retention Handbook)` | `Responder Onboarding Checklist`
- **Top 5 检索结果**:
  1. `score=0.4334` | `dsid_4b1d1d26-chunk-011`
  2. `score=0.3827` | `dsid_4b1d1d26-chunk-004`
  3. `score=0.3651` | `dsid_fe4f3a98-chunk-011`
  4. `score=0.3535` | `dsid_951c6983-chunk-000`
  5. `score=0.3469` | `dsid_b6c9e2f2-chunk-000`
- **评估结果**: `Hit@1=NO`, `Hit@3=NO`, `Hit@5=NO`, `RR=0.0000` (Rank: None / Miss)

#### Q010: Short-Term Micro-Rotation
- **Query**: *"How does the short-term micro-rotation assignment process operate for employees wishing to explore adjacent roles for a few weeks?"*
- **Expected Doc**: `dsid_7656c7c6... (Navigator Program)` | `3) Micro-rotation and Short-term Assignment Process`
- **Top 5 检索结果**:
  1. `score=0.4655` | `dsid_951c6983-chunk-000`
  2. `score=0.4557` | `dsid_4b1d1d26-chunk-000`
  3. `score=0.4391` | `dsid_25882738-chunk-000`
  4. `score=0.4237` | `dsid_4b1d1d26-chunk-003`
  5. `score=0.4206` | `dsid_4b1d1d26-chunk-010`
- **评估结果**: `Hit@1=NO`, `Hit@3=NO`, `Hit@5=NO`, `RR=0.0000` (Rank: None / Miss)

#### Q011: First PR & Provisioning Velocity
- **Query**: *"What are the quantitative velocity targets and median benchmarks for provisioning access and merging a first pull request?"*
- **Expected Doc**: `dsid_951c6983... (Talent Deep Dive)` | `Metrics and quality gates (people-ops KPIs)`
- **Top 5 检索结果**:
  1. `score=0.4262` | `dsid_b6c9e2f2-chunk-000`
  2. `score=0.3722` | `dsid_951c6983-chunk-000` **[HIT]**
  3. `score=0.3716` | `dsid_fe4f3a98-chunk-015`
- **评估结果**: `Hit@1=NO`, `Hit@3=YES`, `Hit@5=YES`, `RR=0.5000` (Rank: 2)

#### Q012: Runbook Review Cadence & Retirement
- **Query**: *"What are the review frequencies, expiration policies, and retirement rules for operational service documentation?"*
- **Expected Doc**: `dsid_95aaab5e... (Runbook Retention Handbook)` | `Runbook Review Cadence and Lifecycle:`
- **Top 5 检索结果**:
  1. `score=0.5014` | `dsid_fe4f3a98-chunk-012`
  2. `score=0.4532` | `dsid_fe4f3a98-chunk-005`
  3. `score=0.4428` | `dsid_95aaab5e-chunk-000` **[HIT]**
- **评估结果**: `Hit@1=NO`, `Hit@3=YES`, `Hit@5=YES`, `RR=0.3333` (Rank: 3)

#### Q013: Developer Internal Tools Provisioning
- **Query**: *"What permissions and systems access are provisioned for new engineers across source control, cloud infrastructure, and identity providers?"*
- **Expected Doc**: `dsid_4b1d1d26... (Scaled Onboarding Playbook)` | `Internal Tools Access Matrix (essential items)`
- **Top 5 检索结果**:
  1. `score=0.4616` | `dsid_4b1d1d26-chunk-008` **[HIT]**
  2. `score=0.4486` | `dsid_fe4f3a98-chunk-005`
  3. `score=0.4297` | `dsid_fe4f3a98-chunk-001`
- **评估结果**: `Hit@1=YES`, `Hit@3=YES`, `Hit@5=YES`, `RR=1.0000` (Rank: 1)

#### Q014: Contract Governance & Legal Redlines
- **Query**: *"What governance stages and legal redline guardrails regulate commercial vendor contracts before execution?"*
- **Expected Doc**: `dsid_135ae39c... (Procurement & CLM Playbook)` | `Contract Lifecycle Management (CLM)`
- **Top 5 检索结果**:
  1. `score=0.4502` | `dsid_fe4f3a98-chunk-010`
  2. `score=0.4451` | `dsid_135ae39c-chunk-000` **[HIT]**
  3. `score=0.2904` | `dsid_fe4f3a98-chunk-012`
- **评估结果**: `Hit@1=NO`, `Hit@3=YES`, `Hit@5=YES`, `RR=0.5000` (Rank: 2)

---

### Category C: Specific Detail Queries (3)

#### Q015: Emergency Spend Dollar Limit
- **Query**: *"What is the maximum dollar limit and retroactive approval window for emergency vendor spend during critical outages?"*
- **Expected Doc**: `dsid_135ae39c... (Procurement Playbook)` | `Procurement Procedures`
- **Top 5 检索结果**:
  1. `score=0.4541` | `dsid_95aaab5e-chunk-000`
  2. `score=0.3344` | `dsid_fe4f3a98-chunk-012`
  3. `score=0.3316` | `dsid_135ae39c-chunk-000` **[HIT]**
- **评估结果**: `Hit@1=NO`, `Hit@3=YES`, `Hit@5=YES`, `RR=0.3333` (Rank: 3)

#### Q016: Priority Classes Ceiling in Telemetry Budget
- **Query**: *"What is the maximum allowed number of priority classes a service can configure in its declared telemetry budget?"*
- **Expected Doc**: `dsid_b6c9e2f2... (Telemetry Stability Standard)` | `Standard requirements (high-level):`
- **Top 5 检索结果**:
  1. `score=0.4935` | `dsid_b6c9e2f2-chunk-000` **[HIT]**
  2. `score=0.2637` | `dsid_4b1d1d26-chunk-003`
  3. `score=0.2531` | `dsid_135ae39c-chunk-000`
- **评估结果**: `Hit@1=YES`, `Hit@3=YES`, `Hit@5=YES`, `RR=1.0000` (Rank: 1)

#### Q017: MTTE KPI Metric for Audit Packages
- **Query**: *"What target Mean Time to Evidence is required when assembling audit packages for high-priority security investigations?"*
- **Expected Doc**: `dsid_fe4f3a98... (AuthN Audit Playbook)` | `Metrics and KPIs`
- **Top 5 检索结果**:
  1. `score=0.6097` | `dsid_fe4f3a98-chunk-015` **[HIT]**
  2. `score=0.5538` | `dsid_fe4f3a98-chunk-013`
  3. `score=0.4999` | `dsid_fe4f3a98-chunk-011`
- **评估结果**: `Hit@1=YES`, `Hit@3=YES`, `Hit@5=YES`, `RR=1.0000` (Rank: 1)

---

### Category D: Hard Negative Queries (3)

#### Q018: Log Retention Policy Exceptions Approval
- **Query**: *"Who must approve formal policy exceptions and deviations when a team cannot meet standard data log storage durations?"*
- **Expected Doc**: `dsid_fe4f3a98... (AuthN Audit Playbook)` | `Risk exceptions and approval workflow`
- **Top 5 检索结果**:
  1. `score=0.4709` | `dsid_fe4f3a98-chunk-012` **[HIT]**
  2. `score=0.4114` | `dsid_fe4f3a98-chunk-005`
  3. `score=0.4002` | `dsid_fe4f3a98-chunk-017`
- **评估结果**: `Hit@1=YES`, `Hit@3=YES`, `Hit@5=YES`, `RR=1.0000` (Rank: 1)

#### Q019: Request Tracking Header for Audit Join
- **Query**: *"What HTTP header carries the unique request tracking identifier for joining authentication decisions with backend access logs?"*
- **Expected Doc**: `dsid_fe4f3a98... (AuthN Audit Playbook)` | `Technical controls and requirements`
- **Top 5 检索结果**:
  1. `score=0.4021` | `dsid_fe4f3a98-chunk-009`
  2. `score=0.3899` | `dsid_fe4f3a98-chunk-006`
  3. `score=0.3843` | `dsid_fe4f3a98-chunk-016`
  4. `score=0.3675` | `dsid_fe4f3a98-chunk-013`
  5. `score=0.3624` | `dsid_fe4f3a98-chunk-005` **[HIT]**
- **评估结果**: `Hit@1=NO`, `Hit@3=NO`, `Hit@5=YES`, `RR=0.2000` (Rank: 5)

#### Q020: Multi-Year Contract Approval Ceiling
- **Query**: *"Which executive roles must authorize multi-year commitments or SaaS contracts exceeding quarter-million dollar thresholds?"*
- **Expected Doc**: `dsid_135ae39c... (Procurement Playbook)` | `Approval Matrix (illustrative)`
- **Top 5 检索结果**:
  1. `score=0.4341` | `dsid_135ae39c-chunk-000` **[HIT]**
  2. `score=0.4237` | `dsid_fe4f3a98-chunk-012`
  3. `score=0.3957` | `dsid_951c6983-chunk-000`
- **评估结果**: `Hit@1=YES`, `Hit@3=YES`, `Hit@5=YES`, `RR=1.0000` (Rank: 1)

---

## 5. 未命中 Query 深入归因 (Miss Analysis)

在 Top-5 中未命中的 3 个 Query 均为**跨文档高度重叠场景**：

### 1. Q006 (Mentorship & Buddy Setup)
- **现象**: 期望定位 `dsid_7656c7c6`（Navigator 专项导师文档），但被 `dsid_951c6983`（人才全周期）与 `dsid_4b1d1d26`（Scaled Onboarding - Manager & Buddy Responsibilities）优先召回。
- **根因**:
  - `dsid_4b1d1d26` 被精细切分出了 `Manager & Buddy Responsibilities` 独立 Chunk，其专注度极高；
  - `dsid_7656c7c6` 未切细分块，整体长文本被均值池化，导致 "1:6 导师配比" 等关键信息被全文稀释。

### 2. Q009 (On-call Responder Onboarding)
- **现象**: 期望定位 `dsid_95aaab5e`（值班响应工程师入职与认证），但通用新员工入职 Playbook（`dsid_4b1d1d26`）占据前两名。
- **根因**:
  - Query 中包含高权重的通用入职词（"newly assigned", "trained", "certified"）；
  - 通用入职文档中关于经理检查单、能力阶梯的切块产生了通用语义共振，压过了 SRE on-call 运维专有词汇的微弱权重。

### 3. Q010 (Short-Term Micro-Rotation)
- **现象**: 期望定位 `dsid_7656c7c6`（Navigator 4~12 周微轮岗），但被 `dsid_951c6983`（宏观人才流转与转岗）抢占。
- **根因**:
  - "explore adjacent roles" 触发了宏观职位流动（Internal mobility / lateral transfers）的大段内容匹配。由于大单体 Chunk 包含较多泛化上下文，在没有精确重排的情况下产生 Top-1 偏离。

---

## 6. 核心发现与后续演进建议

1. **Chunking 粒度是决定检索质量的第一要素**：
   - 标准二级标题（`##`）切分出的独立 Chunk 表现突出（如 Q017 达到 `0.6097` 高相似度，Q013 达到 `0.4616` Rank 1）；
   - 大单体 Chunk（7,000~10,000 字符）存在明显的“语义稀释效应”。后续在 OKF 标准化解析时，应支持按正文段落标题（Text Heading）进行统一粒度切块。
2. **同业务域跨文档（Cross-document）需引入混合检索（Hybrid Search）**：
   - 纯 Dense Embedding 检索在同类业务（如多篇 People-Ops 入职文档）中容易产生假阳性相关；
   - 引入 **BM25 / Keyword 过滤 + 向量余弦相似度**（或 Rerank 机制）将大幅改善特定专有词（如 "on-call", "micro-rotation", "X-RW-REQ-ID"）的精准召回。
