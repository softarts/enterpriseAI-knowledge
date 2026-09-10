# QA 问答评估报告

**版本日期**: 2026-09-10
**评估问题**: How does the organization recognize customer revenue and allocate transaction prices across deliverables?

---

## 评估维度

### 1. 回答准确性评估

**评估结果**: 优秀

回答内容与源文档 `Procurement, Contract Lifecycle, and Revenue Controls Playbook` (lines 94-110) 高度一致：

- **ASC 606 五步法**：完整准确（识别合同、识别履约义务、确定交易价格、分配价格、确认收入）
- **Hosted API**：准确 - 按月按交付量确认，预付时记录递延收入
- **Dedicated Capacity**：准确 - 基础预留费按承诺期摊销，超额用量按实现时确认
- **Private Deployments**：准确 - 永久许可证按指引确认，实施服务按投入法确认，支持费按期摊销
- **Multi-element Arrangements**：准确 - 按 SSP 分配，按履约义务满足时确认

**优点**:
- 结构清晰，先概述原则再分场景说明
- 关键术语准确（SSP、ratably、input method）
- 覆盖了文档中的所有主要业务场景

**具体建议改进**（针对此问题）:
- 可补充文档中提到的计费周期（Net30）和贷项/退款政策（> $5k 需 VP Finance 批准）
- 可补充审计控制要点（月度对账、季度审计准备）

---

### 2. 普适性评估

#### 2.1 检索质量分析

**Trace 数据**:
```
top_k: 5
top_distance: 0.395 (threshold: 0.5) ✓ 通过
检索到的 chunks:
  - rank 1-3: procurement-contracts-and-revrec-playbook-2025 (distance: 0.395, 0.409, 0.424)
  - rank 4-5: tiered-priority-commitments-and-telemetry-stability-standard-2026 (distance: 0.472, 0.493)
context_chars: 16645 (5 chunks)
```

**分析**:
- **相关性**: 前3个chunks高度相关（同一文档，距离<0.43），后2个chunks可能不相关（不同文档，距离接近阈值）
- **覆盖度**: 前3个chunks已覆盖回答所需的所有信息
- **噪声**: 后2个chunks可能引入噪声，但未影响回答质量

**普适性问题**:
- 对于其他问题，如果相关chunks距离较远（>0.45），可能被不相关chunks稀释
- 当前 top_k=5 固定值，对于简单问题可能过多，对于复杂问题可能不足

**改进建议**:
- **动态 top_k**: 根据问题复杂度调整（简单问题 top_k=3，复杂问题 top_k=10）
- **距离过滤**: 增加距离梯度过滤，只保留 distance < 0.45 的chunks
- **文档去重**: 同一文档的chunks优先，避免多文档混合导致的噪声

#### 2.2 Prompt 优化分析

**当前 SYSTEM_PROMPT 特点**:
- 强制只能基于 context 回答
- 统一引用格式（末尾列出）
- 避免过度结构化
- 完整性保证（列举时必须完整覆盖）

**针对此问题的表现**:
- 回答结构良好，先概述再分场景
- 引用格式统一，未打断阅读流畅性
- 完整覆盖了4个业务场景

**普适性问题**:
- 对于需要精确步骤的问题（如"如何审批流程"），当前prompt可能过于宽松
- 对于需要对比的问题（如"A和B的区别"），可能需要更结构化的输出
- 对于需要数据的问题（如"阈值是多少"），可能需要强制提取数值

**改进建议**:
- **问题类型识别**: 在 prompt 前增加问题分类（步骤类/对比类/数据类/概述类）
- **动态约束**: 根据问题类型调整约束（步骤类强制编号，数据类强制提取数值）
- **输出模板**: 为不同问题类型提供输出模板示例

#### 2.3 Agent 编排分析

**当前 Reflection 状态**:
```
reflection: passed=true, notes="占位实现，未做真实校验"
```

**针对此问题的表现**:
- 回答准确，不需要 reflection 修正
- 但无法检测潜在的幻觉或遗漏

**普适性问题**:
- 对于回答不准确的问题，当前无法检测和修正
- 对于遗漏重要信息的问题，无法补充
- 对于引用错误的问题，无法纠正

**改进建议**:
- **实现真实 reflection**: 逐句检查是否有 chunk 支持
- **多轮修正**: 如果 reflection 不通过，重新生成
- **引用验证**: 检查引用的 chunk_id 是否真实存在，且内容相关

---

### 3. 具体改进建议的普适性分析

#### 3.1 之前建议（针对此问题）

| 建议 | 普适性评估 | 说明 |
|------|-----------|------|
| 补充计费周期（Net30） | **低** | 仅与计费相关问题适用 |
| 补充贷项/退款政策（> $5k） | **低** | 仅与退款相关问题适用 |
| 补充审计控制要点 | **中** | 与流程类问题部分相关 |

**结论**: 之前的建议过于针对此特定问题，缺乏广泛适用性。

#### 3.2 普适性改进建议

| 维度 | 改进建议 | 普适性 | 优先级 |
|------|---------|--------|--------|
| **检索** | 动态 top_k + 距离过滤 | 高 | P1 |
| **检索** | 文档去重 + 同文档优先 | 高 | P1 |
| **Prompt** | 问题类型识别 + 动态约束 | 高 | P1 |
| **Prompt** | 输出模板（按问题类型） | 中 | P2 |
| **Agent** | 真实 reflection 实现 | 高 | P1 |
| **Agent** | 多轮 reflection 循环 | 中 | P2 |
| **Agent** | 引用验证（chunk_id 存在性） | 高 | P1 |

---

### 4. Trace 综合分析

**执行时间分解**:
```
总耗时: 99020.23 ms
  - 检索: 85891.57 ms (86.6%) ← 瓶颈
  - LLM: 13128.35 ms (13.3%)
  - 其他: ~0.1 ms
```

**关键发现**:
1. **检索耗时过长**: 85秒，远超正常范围（应<5秒）
   - 可能原因: embedding 模型首次加载、ChromaDB 连接慢、网络延迟
   - 影响: 用户体验差，无法实时问答

2. **置信度阈值**: 0.395 < 0.5，通过
   - 但 0.5 阈值未经校准，可能不适合所有问题

3. **Context 大小**: 16645 字符（5 chunks）
   - 对于此问题，前3个chunks已足够
   - 可能导致 LLM 处理时间增加

4. **Reflection 占位**: 未做真实校验
   - 无法保证回答质量

**改进建议**:
- **检索优化**: 实现模型预加载、连接池、缓存
- **阈值校准**: 基于评测数据调整阈值
- **Context 优化**: 动态调整 chunks 数量
- **Reflection 实装**: 优先实现真实校验逻辑

---

### 5. 下一步行动

**P1 (高优先级)**:
1. 实现真实 reflection（逐句校验）
2. 优化检索性能（预加载、缓存）
3. 实现动态 top_k + 距离过滤
4. 问题类型识别 + 动态 prompt 约束

**P2 (中优先级)**:
1. 多轮 reflection 循环
2. 输出模板（按问题类型）
3. 置信度阈值校准
4. 引用验证（chunk_id 存在性 + 内容相关性）

**P3 (低优先级)**:
1. 端到端评测用例
2. Trace 接入
3. ReAct / Plan-and-Execute

---

## 附录：完整 Trace

```json
{
  "trace_id": "23d0385681644e88893e13c2c9ed4efc",
  "duration": 99020.23,
  "steps": 7,
  "request": {
    "question": "How does the organization recognize customer revenue and allocate transaction prices across deliverables?",
    "question_chars": 105,
    "top_k": 5
  },
  "retrieval": {
    "top_k": 5,
    "count": 5,
    "top_distance": 0.3952610492706299,
    "chunks": [
      {
        "rank": 1,
        "chunk_id": "b7d0c39e994e21b38485cb4fac7d12107065f8068421916a650623efabaa0ed0-chunk-002-eef8e533f054",
        "document_id": "b7d0c39e994e21b38485cb4fac7d12107065f8068421916a650623efabaa0ed0",
        "source_path": "dsid_135ae39cdcd342e5b9c65190c87dd6ae__procurement-contracts-and-revrec-playbook-2025.txt",
        "heading": "Procurement, Contract Lifecycle, and Revenue Controls Playbook",
        "distance": 0.3952610492706299
      },
      {
        "rank": 2,
        "chunk_id": "b7d0c39e994e21b38485cb4fac7d12107065f8068421916a650623efabaa0ed0-chunk-001-789638844f97",
        "document_id": "b7d0c39e994e21b38485cb4fac7d12107065f8068421916a650623efabaa0ed0",
        "source_path": "dsid_135ae39cdcd342e5b9c65190c87dd6ae__procurement-contracts-and-revrec-playbook-2025.txt",
        "heading": "Procurement, Contract Lifecycle, and Revenue Controls Playbook",
        "distance": 0.40931177139282227
      },
      {
        "rank": 3,
        "chunk_id": "b7d0c39e994e21b38485cb4fac7d12107065f8068421916a650623efabaa0ed0-chunk-000-8b652425536e",
        "document_id": "b7d0c39e994e21b38485cb4fac7d12107065f8068421916a650623efabaa0ed0",
        "source_path": "dsid_135ae39cdcd342e5b9c65190c87dd6ae__procurement-contracts-and-revrec-playbook-2025.txt",
        "heading": "Procurement, Contract Lifecycle, and Revenue Controls Playbook",
        "distance": 0.42440807819366455
      },
      {
        "rank": 4,
        "chunk_id": "d3a36640a8a2e9c838da5d986ea56a60cc0f8c96cf671a5422b1cae2dfcb8adc-chunk-002-f187d13f19c1",
        "document_id": "d3a36640a8a2e9c838da5d986ea56a60cc0f8c96cf671a5422b1cae2dfcb8adc",
        "source_path": "dsid_b6c9e2f26e644b15b5be1eed43ed7149__tiered-priority-commitments-and-telemetry-stability-standard-2026.txt",
        "heading": "Tiered Priority Commitments and Telemetry Stability Standard",
        "distance": 0.47160112857818604
      },
      {
        "rank": 5,
        "chunk_id": "d3a36640a8a2e9c838da5d986ea56a60cc0f8c96cf671a5422b1cae2dfcb8adc-chunk-003-411e4d02c0d1",
        "document_id": "d3a36640a8a2e9c838da5d986ea56a60cc0f8c96cf671a5422b1cae2dfcb8adc",
        "source_path": "dsid_b6c9e2f26e644b15b5be1eed43ed7149__tiered-priority-commitments-and-telemetry-stability-standard-2026.txt",
        "heading": "Tiered Priority Commitments and Telemetry Stability Standard",
        "distance": 0.4928169250488281
      }
    ]
  },
  "confidence": {
    "passed": true,
    "threshold": 0.5,
    "top_distance": 0.3952610492706299
  },
  "context": {
    "chars": 16645,
    "chunks": 5
  },
  "llm": {
    "model": "Qwen/Qwen3.8-27B:novita",
    "max_tokens": 1024,
    "thinking_enabled": false,
    "question_chars": 105,
    "context_chars": 16645,
    "answer_chars": 1900
  },
  "reflection": {
    "passed": true,
    "notes": "占位实现，未做真实校验"
  },
  "response": {
    "answer_chars": 1900,
    "sources": [
      "b7d0c39e994e21b38485cb4fac7d12107065f8068421916a650623efabaa0ed0-chunk-002-eef8e533f054",
      "b7d0c39e994e21b38485cb4fac7d12107065f8068421916a650623efabaa0ed0-chunk-001-789638844f97",
      "b7d0c39e994e21b38485cb4fac7d12107065f8068421916a650623efabaa0ed0-chunk-000-8b652425536e",
      "d3a36640a8a2e9c838da5d986ea56a60cc0f8c96cf671a5422b1cae2dfcb8adc-chunk-002-f187d13f19c1",
      "d3a36640a8a2e9c838da5d986ea56a60cc0f8c96cf671a5422b1cae2dfcb8adc-chunk-003-411e4d02c0d1"
    ],
    "passed_reflection": true
  }
}
```
