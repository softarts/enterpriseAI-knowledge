# Phase 1: Embedding Service & Local Persistence Specification

## 1. 概述
本模块实现了企业知识库 POC 的 **Phase 1: Embedding 生成与本地持久化**。
在不修改当前 OKF 格式、现有导入流程、Chunker、KeywordRetriever、API Server 及 MCP Server 的前提下，独立实现了从 OKF 文档切分块到本地向量持久化与余弦相似度检索的完整最小闭环：
```text
OKF 文档 → Chunk → Embedding 生成 → 本地 JSON 镜像持久化 → 本地加载 → Cosine Similarity 检索
```

---

## 2. Embedding Model 选择与理由

- **选择的模型**: `all-MiniLM-L6-v2` (via `sentence-transformers`)
- **选择理由**:
  1. **完全本地运行**: 无需 Docker、无需外部向量数据库或远程 API Key，开箱即用。
  2. **轻量高效**: 模型大小约 80MB，推理速度极快，在 CPU/GPU 上均可毫秒级完成编码。
  3. **语义检索质量优秀**: 在标准 MTEB / sentence-embeddings 基准测试中表现优异，非常适合作为企业文档 POC 原型评估的基准模型。
  4. **零额外中间件依赖**: 与当前 Python 环境无缝衔接。

---

## 3. Embedding Dimension
- **维度**: `384` 维 (Float32 / List[float])
- **向量归一化**: 默认进行 L2 归一化（`normalize_embeddings=True`），使余弦相似度可直接高效计算。

---

## 4. Embedding 文件格式与 Metadata
每个持久化文件为 JSON 数组，记录该文档所有切块及其 Embedding 和溯源元数据：

```json
[
  {
    "chunk_id": "dsid-135ae39cdcd342e5b9c65190c87dd6ae-procurement-contracts-and-revrec-playbook-2025-chunk-000",
    "document_id": "dsid-135ae39cdcd342e5b9c65190c87dd6ae-procurement-contracts-and-revrec-playbook-2025",
    "title": "Procurement, Contract Lifecycle, and Revenue Controls Playbook",
    "heading": "Overview",
    "content": "This playbook defines the end-to-end controls...",
    "source_path": "dsid_135ae39cdcd342e5b9c65190c87dd6ae__procurement-contracts-and-revrec-playbook-2025.txt",
    "embedding": [0.0123, -0.0456, ..., 0.0789]
  }
]
```

### 保存的元数据字段说明：
- `chunk_id`: 切块唯一标识符，可回溯到具体段落。
- `document_id`: 原始 OKF 文档的稳定 ID。
- `title`: 文档标题。
- `heading`: 所属二级/三级标题章节（如无则为 `None`）。
- `content`: 切块文本正文。
- `source_path`: 原始输入文档路径。
- `embedding`: 384 维浮点数向量列表。

---

## 5. 镜像路径映射规则
所有向量文件保存在根目录下的 `embedding/` 目录中，与 `generated/`（OKF 文档目录）保持 1:1 的结构镜像关系：

- 原始 OKF 文件:
  `generated/{subpath}/{filename}.yaml`
- 对应的持久化 Embedding 文件:
  `embedding/{subpath}/{filename}.json`

示例：
- `generated/dsid_135ae39cdcd342e5b9c65190c87dd6ae__procurement-contracts-and-revrec-playbook-2025.yaml`
  ↓ 对应镜像为
- `embedding/dsid_135ae39cdcd342e5b9c65190c87dd6ae__procurement-contracts-and-revrec-playbook-2025.json`

---

## 6. 批量从 OKF 文档导入 (OKF Batch Import)

使用 `main_import.py` 从 `generated/` 目录下的 OKF 文档批量读取并切块，生成 Embeddings 保存到 `embedding/` 镜像目录：

```bash
# 1. 默认批量导入 generated/ 下的所有 OKF 文档（保持镜像层级）
python embedding_service/main_import.py

# 2. 导入某个子目录下的 OKF 文档
python embedding_service/main_import.py --input generated/confluence/people-ops

# 3. 导入单个 OKF 文件
python embedding_service/main_import.py --input generated/confluence/people-ops/onboarding/dsid_4b1d1d26a4d64f3c9f0702e7b1d2d3ef__scaled-onboarding-first-90-to-1000-playbook-2028.yaml

# 4. 指定自定义输出目录
python embedding_service/main_import.py --input generated/confluence/people-ops/onboarding/xxx.yaml --output custom_embedding/
```

---

## 7. 如何运行 Validation 验证

在项目根目录下执行验证脚本：
```bash
python embedding_service/validate.py
```

或运行自动化单元测试：
```bash
pytest tests/test_embedding_service.py tests/test_embedding_import.py -v
```

验证脚本会自动完成：
1. 从 `generated/` 读取 OKF 文档并使用现有 heading-aware chunker 切块。
2. 调用本地 embedding 模型生成向量。
3. 将包含元数据与向量的 JSON 存储到 `embedding/` 镜像目录。
4. 从本地 JSON 重新加载向量数据并验证维度。
5. 使用代表性 Query 计算余弦相似度并打印 Top-K 召回结果与分值。

---

## 8. Retrieval Evaluation 检索效果评测

本模块提供基于标准评测数据集的自动化检索质量评估工具：

```bash
# 运行默认检索评测（Top-5）
python embedding_service/evaluate_retrieval.py

# 指定评测数据集与 Top-K 截断
python embedding_service/evaluate_retrieval.py --eval embedding_service/evaluation_queries.json --top-k 5
```

- **评测数据集**: [`evaluation_queries.json`](./evaluation_queries.json) (20 个高质量评测 Query，涵盖 direct_semantic、cross_document、specific_detail 与 hard_negative)
- **评测报告与归因分析**: 参见详细报告文档 [`evaluation_report.md`](./evaluation_report.md)
- **核心指标概览**:
  - **Hit@1**: `0.6500` (13/20)
  - **Hit@3**: `0.8000` (16/20)
  - **Hit@5**: `0.8500` (17/20)
  - **MRR**: `0.7258`

