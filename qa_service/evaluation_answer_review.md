# QA 问答系统评估报告

**版本日期**：2026-09-10  
**评估问题**：Q001  
**Query**：
> How does the organization recognize customer revenue and allocate transaction prices across deliverables?

**评估范围**：Retrieval、Answer、Citation、Evaluation/Reflection  
**性能评估**：本版本暂不纳入判断

---

# 1. Executive Summary

本次对 Q001 的评估表明，该问题是一个**End-to-End 高质量成功案例**。

系统能够：

1. 在 Top 1 即召回正确业务文档；
2. Top 3 均来自正确的 `Procurement, Contract Lifecycle, and Revenue Controls Playbook`；
3. Q001 Ground Truth 中定义的 4 项核心 evidence 全部被回答覆盖；
4. LLM 生成的主要 revenue recognition claims 均可以在源文档中找到对应依据；
5. 回答结构清晰，并覆盖 ASC 606 五步法以及主要业务场景；
6. 没有发现明显的 unsupported claim 或与源文档矛盾的核心结论。

因此，从 **Answer Correctness + Retrieval Recall** 角度，Q001 可以判定为成功。

但是，该 Case 同时暴露出当前 Retrieval Pipeline 的一个明确问题：

> **Retriever 能够很好地找到正确答案，但 Top-K 中仍然存在明显的跨文档噪声。**

具体而言：

- Rank 1–3：全部来自正确的 Revenue / Contract / Procurement 文档；
- Rank 4–5：来自完全不同主题的 `Tiered Priority Commitments and Telemetry Stability Standard`；
- 后一个文档的主题主要涉及 request priority、telemetry、runtime scheduler、observability、SLO 等，与 Q001 的 revenue recognition / transaction price allocation 没有直接关系。

因此，当前系统更接近：

> **High-Recall Candidate Retrieval**

而不是：

> **High-Precision Final Evidence Retrieval**

这意味着当前最值得优化的方向不是简单地继续提高 Embedding Recall，而是：

**Reranking → Section-aware Retrieval → Evidence Selection → Claim-level Verification → Citation Evaluation**

---

# 2. Ground Truth 定义

Q001 的 Retrieval Ground Truth 包含三个层级：

| 层级 | Ground Truth |
|---|---|
| Expected Document | `procurement-contracts-and-revrec-playbook-2025` |
| Expected Heading | `Revenue Recognition and Billing Policies` |
| Expected Evidence | ASC 606、Identify performance obligations、Allocate price to performance obligations、Recognize revenue when performance obligations are satisfied |

Q001 的 Expected Evidence：

1. ASC 606
2. Identify performance obligations
3. Allocate price to performance obligations
4. Recognize revenue when performance obligations are satisfied

需要特别说明：

> `expected_evidence` 更适合用于评价 Retrieval 是否召回了回答所需要的证据，而不应该被直接当作 LLM 必须逐字复述的标准答案。

因此，本报告将 Retrieval Evaluation 与 Answer Evaluation 分开处理。

---

# 3. Source Document Verification

Q001 的正确源文档为：

**Procurement, Contract Lifecycle, and Revenue Controls Playbook**

该文档中的 `Revenue Recognition and Billing Policies` 部分明确包含：

### ASC 606-aligned principles

文档定义了以下五个步骤：

1. Identify the contract with a customer
2. Identify performance obligations
3. Determine transaction price
4. Allocate price to performance obligations
5. Recognize revenue when performance obligations are satisfied

此外，该 section 还定义了主要业务场景：

- Hosted API
- Dedicated capacity
- Private deployments
- Multi-element arrangements

以及：

- Billing
- Deferred revenue
- Collections
- Audit
- Revenue recognition exceptions

因此，该文档对于 Q001 是明确的 authoritative source。

---

# 4. Retrieval Evaluation

## 4.1 Retrieval Trace

本次 Retrieval 参数：

```text
top_k = 5
threshold = 0.5
top_distance = 0.395261
```

实际 Retrieval 结果：

| Rank | Document | Distance | Q001 Relevance |
|---:|---|---:|---|
| 1 | Procurement, Contract Lifecycle, and Revenue Controls Playbook | 0.395 | Relevant |
| 2 | Procurement, Contract Lifecycle, and Revenue Controls Playbook | 0.409 | Relevant |
| 3 | Procurement, Contract Lifecycle, and Revenue Controls Playbook | 0.424 | Relevant |
| 4 | Tiered Priority Commitments and Telemetry Stability Standard | 0.472 | **Irrelevant** |
| 5 | Tiered Priority Commitments and Telemetry Stability Standard | 0.493 | **Irrelevant** |

---

## 4.2 Document Recall

Q001 的 Expected Document 在 Rank 1 即出现。

因此：

| Metric | Result |
|---|---:|
| Document Recall@1 | **100%** |
| Document Recall@3 | **100%** |
| Document Recall@5 | **100%** |

从 document-level retrieval 来看，结果非常好。

尤其是：

> **Recall@1 = 100%**

说明 Embedding Retriever 能够直接把正确业务文档排在第一位。

---

# 5. Retrieval Evidence Coverage

Q001 Ground Truth 定义了四项核心 evidence：

| Expected Evidence | Answer 中是否体现 | Retrieval/Source 是否有依据 |
|---|---|---|
| ASC 606 | ✅ | ✅ |
| Identify performance obligations | ✅ | ✅ |
| Allocate price to performance obligations | ✅ | ✅ |
| Recognize revenue when obligations are satisfied | ✅ | ✅ |

结果：

> **Evidence Coverage = 4 / 4 = 100%**

这说明当前 Retrieval 并不是“找到了相关文档但没有找到真正答案”。

相反，正确文档的 Top 3 chunks 已经包含回答 Q001 所需要的主要证据。

因此 Q001 的核心 Retrieval 问题不是 Recall 不足。

---

# 6. Retrieval Noise Analysis

这是本次评估最值得关注的发现之一。

Rank 4 和 Rank 5 来自：

**Tiered Priority Commitments and Telemetry Stability Standard**

该文档的主要内容包括：

- Tiered request priorities
- Priority Commitment
- Telemetry Stability
- runtime scheduler
- `X-RW-Priority`
- `X-RW-Client-Tier`
- `X-RW-Priority-Nonce`
- telemetry SLO
- fidelity budget
- metrics / spans
- cardinality / privacy
- observability rollout

这些内容与 Q001：

> customer revenue recognition and transaction price allocation

属于明显不同的业务主题。

因此，在已经获得完整源文档信息之后，可以明确将 Rank 4–5 判定为：

> **Irrelevant Retrieval Noise**

而不是之前报告中较保守的“可能不相关”。

---

# 7. Top-K Precision / Noise Rate

如果将 Q001 当前 Top 5 的 chunk/document relevance 定义为：

- Rank 1–3 = relevant
- Rank 4–5 = irrelevant

那么：

**Precision@5 = 3 / 5 = 60%**

或者：

**Noise Rate@5 = 2 / 5 = 40%**

但这里必须强调：

> 这个 60% 只能称为当前 Q001、当前 relevance 定义下的 Top-5 Retrieval Precision，不能直接称为“Embedding Precision = 60%”。

因为 Precision 的统计单位必须明确：

- chunk-level
- document-level
- evidence-level
- section-level

而且单个 query 不能代表整个 benchmark。

因此，本结果适合作为：

> **Q001 的诊断信号**

而不是：

> **整个 Embedding 系统的最终指标。**

---

# 8. Distance Distribution Analysis

当前 distance：

```text
Relevant:
0.395
0.409
0.424

Irrelevant:
0.472
0.493
```

可以观察到：

```text
Relevant maximum = 0.424
Irrelevant minimum = 0.472
```

两者之间存在：

```text
0.472 - 0.424 = 0.048
```

的 separation gap。

这说明对于 Q001：

> 当前 Embedding 对正确文档和错误文档存在一定程度的距离区分能力。

但是不能据此直接得出：

> threshold 应该从 0.5 调整到 0.45。

原因是：

1. 当前只有一个 query；
2. 其他 query 的 positive distance 可能大于 0.45；
3. 如果存在 positive distance > 0.45，直接降低 threshold 会损失 Recall；
4. 不同 query 类型的 embedding distance distribution 可能不同。

因此：

> **threshold 0.5 当前只能认为是一个尚未经过完整 benchmark calibration 的配置。**

推荐通过完整 Evaluation Set 统计：

```text
Positive distance distribution
Negative distance distribution
Precision-Recall curve
Recall@K
False Positive Rate
False Negative Rate
```

之后再决定 threshold。

---

# 9. Retrieval Architecture Assessment

从 Q001 可以看到，当前 Retriever 的行为非常典型：

```text
Query
  ↓
Embedding Retrieval
  ↓
Top 5
  ↓
3 relevant + 2 irrelevant
  ↓
LLM
```

这说明 Embedding 层已经完成了最重要的事情：

> 找到正确答案所在的文档。

但它没有完全解决：

> 哪些结果是真正回答当前问题所需要的 evidence？

因此，Embedding 不应该同时承担：

1. Candidate generation
2. Final relevance judgment

更合理的架构是：

```text
Query
  ↓
Query Classification
  ↓
Embedding Retrieval
  ↓
Top 10–20 Candidate Chunks
  ↓
Reranker
  ↓
Top 3–5 Relevant Chunks
  ↓
Section / Evidence Selection
  ↓
LLM
```

Embedding 的主要目标：

> **High Recall**

Reranker 的主要目标：

> **High Precision**

Evidence Selection 的目标：

> **只把真正回答问题所需要的证据交给 LLM**

---

# 10. Section-aware Retrieval

当前数据特别适合进一步引入 Section-aware Retrieval。

源文档具有非常清晰的层级结构：

```text
Procurement Procedures
    ├── Vendor Selection
    ├── PO and Commitment Process
    ├── Approval Matrix
    └── Emergency procurements

Contract Lifecycle Management
    ├── Request & Intake
    ├── Business Terms
    ├── Legal Review
    ├── Negotiation
    ├── Signature & Archival
    └── Post-signature Obligations

Revenue Recognition and Billing Policies
    ├── Principles
    ├── Common scenarios
    ├── Billing
    ├── Deferred revenue
    ├── Collections
    ├── Audit
    └── Exception
```

而 Ground Truth 本身也已经提供了：

```text
Q001 → Revenue Recognition and Billing Policies
Q014 → Contract Lifecycle Management
Q015 → Emergency procurements
Q020 → Approval Matrix / Strategic commitments
```

这说明数据天然支持：

```text
Query
 ↓
Document Retrieval
 ↓
Section Retrieval / Section Reranking
 ↓
Evidence Chunk Retrieval
 ↓
LLM
```

相比纯 flat chunk retrieval，这种方式更适合企业知识库。

---

# 11. 一个非常重要的 Retrieval Diagnosis

Q001 当前暴露出的核心问题可以概括为：

> **不是“找不到答案”，而是“找到答案之后没有很好地停止”。**

Top 3 已经足够回答问题。

但系统继续把另外两个明显不同主题的 chunks 加入 Context。

因此：

```text
Recall：优秀
Precision：仍有改善空间
```

这比简单地说：

> “Embedding 不够好”

更加准确。

---

# 12. Answer Evaluation

## 12.1 Overall Result

**Answer Quality：优秀**

实际回答与源文档核心内容高度一致。

回答主要包括：

1. ASC 606 五步法；
2. Hosted API；
3. Dedicated Capacity；
4. Private Deployments；
5. Multi-element Arrangements。

这些内容均可以在源文档中找到对应依据。

---

# 13. Claim-level Verification

建议将 Answer Evaluation 从“答案整体是否像正确答案”升级为：

```text
Answer
  ↓
Claim Extraction
  ↓
Claim → Evidence Mapping
  ↓
Supported / Unsupported / Contradicted
```

对于当前 Q001，可以得到：

| Claim | Source Support | Result |
|---|---|---|
| Revenue recognition follows ASC 606-aligned principles | 有 | ✅ Supported |
| Identify customer contract | 有 | ✅ Supported |
| Identify performance obligations | 有 | ✅ Supported |
| Determine transaction price | 有 | ✅ Supported |
| Allocate based on SSP / best estimate | 有 | ✅ Supported |
| Recognize revenue when obligations are satisfied | 有 | ✅ Supported |
| Hosted API recognition | 有 | ✅ Supported |
| Deferred revenue for prepayment | 有 | ✅ Supported |
| Dedicated capacity treatment | 有 | ✅ Supported |
| Overage recognition | 有 | ✅ Supported |
| Private deployment treatment | 有 | ✅ Supported |
| Implementation input method | 有 | ✅ Supported |
| Support recognized ratably | 有 | ✅ Supported |
| Multi-element allocation | 有 | ✅ Supported |

目前没有发现明显的核心 unsupported claim 或 contradiction。

---

# 14. Answer Completeness

旧报告建议回答补充：

- Net30
- Credits/refunds
- Monthly reconciliation
- Quarterly audit preparation

经过重新评估，这些内容**不应该再作为 Q001 Answer Completeness 的主要缺失项**。

原因是 Q001 问的是：

> How does the organization recognize customer revenue and allocate transaction prices across deliverables?

它的核心目标是：

1. revenue recognition principle；
2. transaction price determination；
3. allocation；
4. recognition timing；
5. 不同 deliverable / arrangement 的处理。

Net30 属于 billing terms。

Credits/refunds 属于 billing control。

Monthly reconciliation / quarterly audit 属于 control / audit process。

这些信息虽然属于同一个 Revenue Recognition and Billing Policies section，但并不是回答 Q001 所必需的核心内容。

因此：

> **不能因为答案没有复述源文档中所有相关信息，就判定 Answer 不完整。**

这是企业 QA Evaluation 中一个非常重要的原则。

---

# 15. Answer Evaluation 应避免 Source Text Recall

不应该使用：

> Answer 是否覆盖了 source document 的所有内容

作为 Answer Completeness 指标。

否则会产生一个明显问题：

源文档可能包含 100 条信息，而用户只问其中 5 条。

如果系统准确回答这 5 条，却没有把另外 95 条全部复述出来，不能因此判定答案“不完整”。

更合理的模型是：

```text
User Query
     ↓
Expected Claims
     ↓
Generated Answer Claims
     ↓
Evidence Verification
```

因此建议未来为 QA Ground Truth 增加：

```json
{
  "expected_claims": [
    "Revenue recognition follows ASC 606-aligned principles",
    "Transaction price is allocated to distinct performance obligations",
    "Revenue is recognized when or as performance obligations are satisfied",
    "Hosted API revenue is recognized over the billing month",
    "Dedicated capacity base reservation is recognized over the reservation term",
    "Private deployment components have different recognition patterns",
    "Multi-element arrangements are allocated based on SSP"
  ]
}
```

这样 Retrieval GT 和 Answer GT 就能明确分离。

---

# 16. Citation Evaluation

当前 Answer 的 response sources 最终包含 5 个 chunks：

```text
Correct document:
chunk-002
chunk-001
chunk-000

Irrelevant document:
chunk-002
chunk-003
```

但实际生成的 Answer 只明确列出了两个来源 chunk：

```text
chunk-001
chunk-002
```

这一点本身**不能直接判定为 Citation 错误**。

因为：

> Citation 是否充分，取决于被引用的 chunk 是否覆盖了 Answer 中的 claims，而不是 citation 数量。

如果两个引用 chunk 已经覆盖全部核心 claims，那么两个 citation 也可能是充分的。

因此当前真正缺失的是：

> **Claim-level Citation Evaluation**

建议建立：

```text
Claim A
  ↓
Citation Chunk X
  ↓
Does X support Claim A?
```

最终统计：

### Citation Precision

被引用的 evidence 中，有多少真正支持对应 claim。

### Citation Coverage / Recall

生成答案中的多少重要 claims 有对应 evidence。

### Citation Granularity

citation 是否精确到：

- document
- section
- chunk
- paragraph
- sentence

---

# 17. Reflection / Self-Check Evaluation

当前 Trace：

```text
reflection:
    passed = true
    notes = "占位实现，未做真实校验"
```

这是当前 Evaluation Pipeline 中一个明确的问题。

虽然 Trace 显示：

```text
passed = true
```

但实际上并没有进行真实 reflection。

因此不能解释为：

> Reflection 验证通过。

准确的解释应该是：

> **Reflection 尚未实现，因此当前 Q001 的 Reflection Result 应标记为 Not Evaluated。**

这是一个重要区别。

当前状态：

| Evaluation | Status |
|---|---|
| Retrieval | Evaluated |
| Answer | Manually/externally verified |
| Citation | Partially evaluated |
| Reflection | **Not Evaluated** |

未来真正的 Reflection 应至少检查：

```text
For each claim:
    Is there evidence?
    Does evidence actually support the claim?
    Is there contradiction?
    Is important information missing?
    Is citation correct?
```

---

# 18. 推荐的 Reflection Pipeline

可以设计成：

```text
Generated Answer
       ↓
Claim Extraction
       ↓
For each Claim
       ↓
Evidence Retrieval / Matching
       ↓
 ┌───────────────┐
 │ Supported?     │
 │ Contradicted?  │
 │ Unsupported?   │
 └───────────────┘
       ↓
Coverage Check
       ↓
Citation Check
       ↓
Final Reflection
```

如果发现：

```text
Unsupported claim
```

则可以：

```text
Reflection Failed
      ↓
Regenerate / Remove unsupported claim
      ↓
Re-check
```

这样 Reflection 才真正具备质量控制价值。

---

# 19. Prompt Evaluation

当前 System Prompt 的核心策略包括：

- 只能基于 context 回答；
- 使用统一 citation 格式；
- 避免过度结构化；
- 保证回答完整；
- 防止无依据扩展。

对于 Q001，该 Prompt 的表现是成功的。

回答：

- 结构清晰；
- 没有明显跑题；
- 没有受到 Rank 4–5 noise 的明显影响；
- 主要 claims 都来自正确 source。

因此，没有证据表明 Q001 当前需要大幅修改 Prompt。

---

# 20. Prompt 的普适性问题

不过，从整个 QA 系统设计角度，当前 Prompt 仍可能存在一个问题：

> 不同类型问题需要不同的回答约束。

例如：

### Step Question

> How does the contract approval process work?

更适合：

```text
1.
2.
3.
4.
```

### Comparison Question

> What is the difference between Hosted API and Dedicated Capacity?

更适合：

| Dimension | Hosted API | Dedicated Capacity |
|---|---|---|

### Numeric Question

> What approval level applies to commitments above $250k?

应该优先提取：

```text
>$250k → CFO + General Counsel
```

### Policy Question

则更适合：

```text
Policy
Exceptions
Controls
Evidence
```

因此，未来可以增加：

```text
Query Classification
```

然后根据 query type 动态调整 Answer Prompt。

但是这属于后续增强方向。

**Q001 本身没有证据表明当前 Prompt 已经失败。**

---

# 21. Overall Evaluation Matrix

| Layer | Metric | Q001 Result | Assessment |
|---|---|---:|---|
| Retrieval | Document Recall@1 | 100% | ✅ Excellent |
| Retrieval | Document Recall@3 | 100% | ✅ Excellent |
| Retrieval | Document Recall@5 | 100% | ✅ Excellent |
| Retrieval | Expected Evidence Coverage | 4/4 | ✅ Excellent |
| Retrieval | Top-5 Precision* | 3/5 = 60% | ⚠️ Noise |
| Retrieval | Top-5 Noise Rate* | 40% | ⚠️ Needs improvement |
| Retrieval | Correct doc ranking | Rank 1 | ✅ Excellent |
| Answer | Core claim coverage | High | ✅ Excellent |
| Answer | Source support | High | ✅ |
| Answer | Contradiction | Not observed | ✅ |
| Answer | Unsupported claims | No obvious issue found | ✅* |
| Citation | Source availability | Present | ✅ |
| Citation | Claim-level validation | Not fully implemented | ⚠️ |
| Reflection | Real validation | Not implemented | ❌ |
| Performance | Latency | Not evaluated | — |

\* 这里的 60% 是当前 Q001、当前 Top-5 relevance 定义下的诊断指标，不代表整个 Embedding 系统的 Precision。

\* Unsupported Claim Rate 不能写成 0%，因为目前没有自动化 claim-level verifier 完成全量验证。

---

# 22. Root Cause Analysis

综合当前证据，可以把问题分为四层。

## P0 — 当前没有发现 Q001 的核心 Answer Failure

Q001 的核心回答是正确的。

因此没有证据支持：

> 当前系统无法回答 revenue recognition 类问题。

相反，Q001 证明系统能够正确完成：

```text
Semantic Query
    ↓
Correct Document
    ↓
Relevant Evidence
    ↓
Correct Answer
```

---

## P1 — Retrieval Precision 仍然不足

已经明确看到：

```text
Top 5
├── Relevant
├── Relevant
├── Relevant
├── Irrelevant
└── Irrelevant
```

说明 Embedding Retrieval 的 candidate set 中存在明显 noise。

优先建议：

> **加入 Reranker。**

---

## P1 — Section-level Retrieval 应成为重点

由于企业文档通常较长，而且一个文档可能包含多个完全不同的业务主题：

```text
Procurement
Contract
Revenue
Audit
```

仅依赖 flat chunk similarity 容易产生：

> 同一企业 / 同一领域 / 词汇相关，但任务实际上不相关

的问题。

因此建议：

> **Document → Section → Chunk 的 hierarchical retrieval**

---

## P1 — Reflection 目前不是真正的 Evaluation

当前：

```text
passed = true
```

不能作为质量指标。

应改成：

```text
Not Evaluated
```

直到真实 verifier 实现。

---

## P1 — Ground Truth 需要拆分 Retrieval GT 与 Answer GT

当前 Retrieval GT 已经比较成熟：

```text
expected_document
expected_heading
expected_evidence
```

下一步应该增加：

```text
expected_claims
```

形成：

```text
Ground Truth
│
├── Retrieval GT
│   ├── Document
│   ├── Heading
│   └── Evidence
│
└── Answer GT
    └── Claims
```

这样可以避免把：

> Retrieval 找到正确证据

和：

> LLM 正确表达证据

混成一个指标。

---

# 23. 推荐的完整 Evaluation Architecture

建议最终建立以下 Evaluation Pipeline：

```text
                    Ground Truth
                         │
             ┌───────────┴───────────┐
             │                       │
      Retrieval GT              Answer GT
             │                       │
             │                  Expected Claims
             │                       │
             ▼                       │
          Query                     │
             │                       │
             ▼                       │
        Embedding                   │
             │                       │
             ▼                       │
          Top-K                      │
             │                       │
             ▼                       │
         Reranker                    │
             │                       │
             ▼                       │
      Evidence Selection             │
             │                       │
             └──────────┬────────────┘
                        ▼
                       LLM
                        │
                        ▼
                     Answer
                        │
                        ▼
                  Claim Extraction
                        │
              ┌─────────┼─────────┐
              ▼         ▼         ▼
           Accuracy  Evidence  Citation
                        │
                        ▼
                    Reflection
                        │
                        ▼
                 Final Evaluation
```

---

# 24. 推荐 Metrics

## Retrieval Metrics

建议至少统计：

### Document Level

- Recall@1
- Recall@3
- Recall@5
- Recall@10

### Section Level

- Heading Recall@K

### Evidence Level

- Evidence Recall@K

### Precision / Noise

- Precision@K
- Noise Rate@K

其中重点应该是：

> **Evidence Recall + Precision**

而不是只看 embedding distance。

---

# 25. Answer Metrics

建议：

```text
Claim Accuracy
Evidence Coverage
Unsupported Claim Rate
Contradiction Rate
Correct Abstention Rate
```

特别是：

### Claim Accuracy

生成 claim 是否与 source 一致。

### Evidence Coverage

重要 claim 是否有 source evidence。

### Unsupported Claim Rate

回答中有多少 claims 无法从 context/source 得到支持。

### Contradiction Rate

回答是否与 source 明确冲突。

---

# 26. Citation Metrics

建议：

```text
Citation Precision
Citation Coverage
Citation Correctness
Citation Granularity
```

最终可以做到：

```text
Claim 1 → Chunk A → Supported
Claim 2 → Chunk A → Supported
Claim 3 → Chunk B → Supported
Claim 4 → No citation → Missing
```

这样才能真正评价 Citation。

---

# 27. Threshold Calibration Strategy

当前：

```text
threshold = 0.5
```

不建议仅凭 Q001 修改。

应该收集整个 benchmark：

```text
Query
Positive chunks
Negative chunks
Distance
```

然后形成：

```text
Positive Distance Distribution
          vs
Negative Distance Distribution
```

再寻找合适 operating point。

例如最终可能得到：

```text
Threshold = X
```

使：

```text
Recall ≥ target
False Positive Rate ≤ target
```

但 `X` 必须由实际 benchmark 数据决定。

当前没有足够证据确定具体数值。

---

# 28. Top-K Strategy

同样，不建议仅凭 Q001 固定：

```text
top_k = 3
```

或者：

```text
top_k = 10
```

更合理的是：

```text
Embedding Top-K
       ↓
Reranker
       ↓
Evidence Selection
       ↓
Final Context
```

也就是说：

> **Embedding K 和最终送给 LLM 的 Context K 不一定应该相同。**

例如：

```text
Embedding → Top 20
Reranker → Top 8
Evidence Selector → Top 3
LLM → 3 relevant evidence groups
```

这样可以同时兼顾 Recall 和 Precision。

---

# 29. Priority Recommendations

## P0 — 必须明确 Evaluation 状态

将当前：

```text
reflection.passed = true
```

改成真正有语义的状态，例如：

```text
NOT_EVALUATED
```

直到 Reflection 实际实现。

**原因：**

避免监控系统将 placeholder 的 `passed=true` 误认为真实质量指标。

---

## P1 — 建立 Claim-level Answer Evaluation

实现：

```text
Answer
 ↓
Claims
 ↓
Evidence
 ↓
Supported / Unsupported / Contradicted
```

这是当前 QA Evaluation 从“人工判断”走向“可量化 Evaluation”最重要的一步。

---

## P1 — 引入 Reranker

当前 Q001 已经证明：

```text
Embedding Recall 很好
Top-K Precision 有 noise
```

因此下一层最合理的是 Reranking，而不是盲目替换 Embedding Model。

---

## P1 — Section-aware / Hierarchical Retrieval

推荐：

```text
Document
   ↓
Section
   ↓
Chunk
```

利用企业文档天然存在的 heading structure。

---

## P1 — 建立完整 Retrieval Benchmark

至少覆盖：

- direct semantic
- procedural
- numeric
- comparison
- multi-hop
- no-answer
- cross-document

并统计：

```text
Recall@1/3/5/10
Heading Recall
Evidence Recall
Precision@K
Noise Rate
```

---

## P2 — Query Classification

分类：

```text
Step
Comparison
Numeric
Definition
Policy
Summary
Multi-hop
```

然后动态控制：

- Retrieval strategy
- Top-K
- Prompt
- Answer format

---

## P2 — Citation Verifier

检查：

```text
Claim
 ↓
Citation
 ↓
Does citation support claim?
```

避免出现：

```text
正确 citation
但 citation 不支持对应 claim
```

---

## P2 — Dynamic Context Compression

当 Top-K 较大时：

```text
Retrieved Chunks
       ↓
Relevant Evidence Extraction
       ↓
Compressed Context
       ↓
LLM
```

这不是为了单纯降低 token，而是为了减少：

> irrelevant evidence 对回答生成的干扰。

---

# 30. 不建议当前直接采取的措施

基于目前证据，以下做法暂时不建议直接上线：

### 1. 仅根据 Q001 把 threshold 0.5 改成 0.45

证据不足。

### 2. 直接把 top_k 从 5 改成 3

虽然 Q001 的前三个 chunk 已足够，但其他复杂问题可能需要更多 evidence。

### 3. 因为 Answer 没有 Net30 就判定回答不完整

不符合 Q001 的问题范围。

### 4. 因为 response sources 最终存在 5 个 source 就判定 Citation 错误

Citation 必须按 claim-level 验证。

### 5. 把 Reflection passed=true 计入质量得分

当前 Reflection 是 placeholder。

---

# 31. Q001 最终结论

综合 Ground Truth、原始源文档、Retrieval Trace、实际 Answer，以及后来补充验证的 Rank 4–5 文档，可以对 Q001 做出以下结论：

> **Q001 是当前系统的一个高质量 End-to-End 成功案例。**

Retrieval 层：

- 正确文档 Rank 1 命中；
- Recall@1 = 100%；
- Recall@3 = 100%；
- Ground Truth Evidence 4/4 覆盖；
- 说明核心 Retrieval Recall 良好。

但同时：

- Rank 4–5 明确来自与问题无关的 Priority / Telemetry 文档；
- 因此 Top-5 中存在 40% 的明显 noise；
- 说明当前 Embedding Retriever 在保持高 Recall 的同时，Final Candidate Precision 仍有提升空间。

Answer 层：

- ASC 606 五步法正确；
- Hosted API 正确；
- Dedicated Capacity 正确；
- Private Deployments 正确；
- Multi-element Arrangements 正确；
- 当前未发现明显 unsupported 或 contradictory core claims。

因此：

> **Q001 的主要问题不是 Answer Accuracy，也不是 Retrieval Recall，而是 Retrieval Precision / Evidence Selection。**

Evaluation 层：

> 当前最大的工程性缺口是 Reflection 尚未真正实现，以及 Answer / Citation 尚未完全建立 Claim-level 自动验证。

---

# 32. 最终系统定位

基于 Q001，目前更准确的系统定位应该是：

```text
                    Current State

Embedding
   │
   ├── Document Recall       ★★★★★
   ├── Evidence Recall       ★★★★★
   └── Top-K Precision       ★★★☆☆
            │
            ▼
        LLM Answer
            │
            ├── Core Accuracy ★★★★★
            ├── Coverage      ★★★★☆
            └── Citation Eval ★★★☆☆
            
Reflection
   └── Not Evaluated
```

因此下一阶段不应该简单理解成：

> “继续优化 Embedding。”

而应该是：

> **从“Embedding-based Retrieval QA”向“Evidence-grounded QA”演进。**

推荐目标架构：

```text
                 Query
                   │
                   ▼
           Query Classification
                   │
                   ▼
          High-Recall Retrieval
                   │
                   ▼
               Reranker
                   │
                   ▼
        Section-aware Retrieval
                   │
                   ▼
          Evidence Selection
                   │
                   ▼
                  LLM
                   │
                   ▼
            Claim Extraction
                   │
        ┌──────────┼──────────┐
        ▼          ▼          ▼
     Accuracy   Evidence   Citation
        │          │          │
        └──────────┼──────────┘
                   ▼
               Reflection
                   │
                   ▼
             Final Answer
```

---

# 33. Final Assessment

**Q001 Overall：优秀 / Successful Case**

| Area | Assessment |
|---|---|
| Correct document retrieval | **Excellent** |
| Top-1 retrieval | **Excellent** |
| Evidence recall | **Excellent** |
| Answer accuracy | **Excellent** |
| Answer completeness for the actual question | **Good–Excellent** |
| Top-K retrieval precision | **Needs improvement** |
| Context noise control | **Needs improvement** |
| Citation verification | **Needs stronger evaluation** |
| Reflection | **Not implemented / Not Evaluated** |
| Overall End-to-End result | **Successful** |

### 核心结论

**当前系统已经证明“能够正确找到并回答 Q001”，下一阶段的重点应从“能不能找到答案”转向“能不能只给模型最相关、可验证的证据，并自动证明答案中的每个 claim 都有依据”。**

因此优先级建议为：

**P0**
1. 将 placeholder Reflection 标记为 `Not Evaluated`

**P1**
2. Claim-level Answer Evaluation
3. Reranker
4. Section-aware / Hierarchical Retrieval
5. Retrieval Benchmark + Threshold Calibration
6. Citation Verification

**P2**
7. Query Classification
8. Dynamic Retrieval / Context Selection
9. Multi-pass Reflection
10. 更细粒度的 Citation / Evidence Scoring

---

# 附录 A：Q001 Retrieval Trace 摘要

```json
{
  "query": "How does the organization recognize customer revenue and allocate transaction prices across deliverables?",
  "top_k": 5,
  "threshold": 0.5,
  "top_distance": 0.395261,

  "retrieval": [
    {
      "rank": 1,
      "distance": 0.395261,
      "document": "Procurement, Contract Lifecycle, and Revenue Controls Playbook",
      "relevance": "relevant"
    },
    {
      "rank": 2,
      "distance": 0.409312,
      "document": "Procurement, Contract Lifecycle, and Revenue Controls Playbook",
      "relevance": "relevant"
    },
    {
      "rank": 3,
      "distance": 0.424408,
      "document": "Procurement, Contract Lifecycle, and Revenue Controls Playbook",
      "relevance": "relevant"
    },
    {
      "rank": 4,
      "distance": 0.471601,
      "document": "Tiered Priority Commitments and Telemetry Stability Standard",
      "relevance": "irrelevant"
    },
    {
      "rank": 5,
      "distance": 0.492817,
      "document": "Tiered Priority Commitments and Telemetry Stability Standard",
      "relevance": "irrelevant"
    }
  ],

  "retrieval_assessment": {
    "document_recall_at_1": 1.0,
    "document_recall_at_3": 1.0,
    "document_recall_at_5": 1.0,
    "expected_evidence_coverage": "4/4",
    "diagnostic_precision_at_5": "3/5",
    "diagnostic_noise_rate_at_5": "2/5"
  },

  "reflection": {
    "status": "NOT_EVALUATED",
    "reason": "Current implementation is a placeholder and does not perform real validation."
  }
}
```

# 附录 B：推荐 Evaluation Data Model

```json
{
  "query_id": "Q001",

  "retrieval_ground_truth": {
    "expected_document": "...",
    "expected_heading": "Revenue Recognition and Billing Policies",
    "expected_evidence": [
      "ASC 606",
      "Identify performance obligations",
      "Allocate price to performance obligations",
      "Recognize revenue when performance obligations are satisfied"
    ]
  },

  "answer_ground_truth": {
    "expected_claims": [
      "Revenue recognition follows ASC 606-aligned principles",
      "Transaction price is allocated to distinct performance obligations",
      "Revenue is recognized when or as performance obligations are satisfied",
      "Hosted API has usage-based recognition",
      "Dedicated capacity has reservation and overage recognition rules",
      "Private deployment components have different recognition patterns",
      "Multi-element arrangements are allocated based on SSP"
    ]
  }
}
```

这个结构可以使 Retrieval、Answer、Citation 三个 Evaluation 层真正解耦，并为后续自动化 benchmark 打基础。