# 企业知识库文章分类器 — Bootstrap 阶段（阶段 A）

仅使用**本地模型**，从一批无标注语料中自动生成一套三级分类 taxonomy 以及每一级的匹配阈值，并支持**随语料规模逐轮扩展、可版本化**的分类发现闭环。产出的 taxonomy 和阈值会被固化下来，作为长期运行的逐篇分类器（阶段 B，不在本代码库内）的元数据输入。

> **本 README 的行号对应当前源码**，是直接读源文件核对的；一旦改动某个模块，行号会偏移。
> 报告/快照/版本化 taxonomy 遵循工作区 steering 规则 `.kiro/steering/agents.md`：**从不覆盖或改名历史产物**，每一轮写新的带版本号 + 时间戳文件。

**目录**

1. [原始需求、约束与设计动因](#1-原始需求约束与设计动因)
2. [架构设计、算法与三级分类的代码实现](#2-架构设计算法与三级分类的代码实现)
3. [Taxonomy 的 T0 → T1 → T2 迭代闭环（含运行例子）](#3-taxonomy-的-t0--t1--t2-迭代闭环)
4. [当前实现（按最新代码，含行号索引）](#4-当前实现按最新代码)
5. [与其他分类/聚类算法的比较](#5-与其他分类聚类算法的比较)
6. [写给转型 AI Engineering 的后端开发者](#6-写给转型-ai-engineering-的后端开发者)
7. [运行历史与如何运行](#7-运行历史与如何运行)
8. [原始需求（逐字保存）与环境适配决策](#8-原始需求逐字保存与环境适配决策)
9. [下一阶段任务建议](#9-下一阶段任务建议)

---

## 1. 原始需求、约束与设计动因

**问题背景。** 把一批企业内部文章转成 OKF 格式、灌入基于 embedding 的知识库之前，每篇文章要挂一个三级分类（例如 `Technology & Engineering > AI & ML Platform > Model Serving & Inference Runtime`）作为 metadata。系统分两阶段，本仓库只做**阶段 A（Bootstrap）**：拿一批初始文章做一次全量扫描，自动产出一套固定的三级 taxonomy + 每级阈值。阶段 B（不在此）之后逐篇导入时，用这套固化产物做规则化的逐级匹配，不再聚类。

**塑造整个设计的硬约束——每一条都直接决定了某个技术选型：**

| 约束 | 由此推出的设计 |
|---|---|
| **没有标注数据**（不存在「文章→分类」训练集） | 不能用有监督分类器。改用**零样本锚点相似度**：把分类描述本身当作监督信号。 |
| **只允许本地模型**，禁止云端 LLM API | 向量化用本地 `bge-m3`；簇命名对接本地 LM Studio（OpenAI 兼容 API）。全程无外网调用。 |
| **全程无人工审核** | 阈值、是否算新类、新类叫什么，全部代码自动完成。结果不完美可接受，但不允许人工介入分类流程。 |
| **L1/L2/L3 锚点要预先 hardcode** | 手写 seed 骨架（17 L1 / 65 L2 / 215 L3）。聚类**只用来补骨架遗漏的缺口**，不是分类主来源——大幅减少运行时聚类量，也让命名更贴近真实业务术语。 |
| **过阈值→匹配上；欠阈值→发现新类或标 UNKNOWN** | 每级用 GMM 从分数分布自动定阈值；欠阈值文档进未分配池聚类，足够大的簇成为新节点，其余标 UNKNOWN。 |
| **命名是生成任务，向量模型做不了** | 用生成式 LLM（qwen3-8b-mlx）读代表标题起名；bge-m3 是纯 encoder，无 decoder，只负责找质心和代表文档。 |

**一个必须知道的事实（语料/taxonomy 错配）。** 原始需求要求 hardcode 一套**银行业务** taxonomy，但实际语料是一家 **AI 推理平台公司**（Redwood Inference）的内部资料：GPU 集群、模型服务、量化、eval、SLO、on-call、Kubernetes、SDK……因此 9 个银行业务线 L1 几乎不会命中，绝大多数文档落到 `Technology & Engineering`。**这不是 bug，是数据与需求的客观错配**：我们照要求把银行骨架写全，同时把 `Technology & Engineering` 展开得最细（避免几十万技术文档全挤在 2 个 L2 下、导致 L3 分数集体偏低、阈值失真），并在每份报告里明确写出这个结论 + 各 L1 分布。它也正是为什么后续的**逐轮发现闭环**会在真实数据里长出 `service_latency_alerts`、`demo_coordination`、`release_operations` 这类语料真正需要、但银行骨架里没有的分类。

---

## 2. 架构设计、算法与三级分类的代码实现

### 2.1 阶段 A（Bootstrap） vs 阶段 B（稳态）

| | 阶段 A — Bootstrap（本仓库） | 阶段 B — 逐篇（不在此） |
|---|---|---|
| 频率 | 逐轮，针对逐步扩大的语料范围 | 持续，入库时逐篇 |
| 聚类 | 有（缺口发现） | 无 |
| LLM 命名 | 有（给新簇命名） | 无 |
| 产出 | `taxonomy_v<N>.py` + `taxonomy.py` + `thresholds.json` | 每篇文档一条分类路径（OKF metadata） |
| 消费的输入 | 原始语料 | 阶段 A 的 `taxonomy.py` + `thresholds.json` |

阶段 A 决定*分类体系是什么、匹配要多高置信度*；阶段 B 复用锚点 + 阈值，对每篇新文档做廉价的逐级最近锚点匹配，欠阈值即 UNKNOWN。

### 2.2 数据流 diagram（原始文档 → 产出物）

```
all_documents/*.txt
   │  corpus.build_manifest / extend_manifest        （扫描 + 分层抽样，冻结 manifest.jsonl）
   ▼
manifest.jsonl                                        （冻结文档顺序：doc_index i 永远对应同一篇文章）
   │  embedder.embed_corpus_resumable                （bge-m3，可续跑分片 → work/embeddings/*.npy
   │                                                    + 内容寻址缓存 work/vector_store.sqlite）
   ▼
文档向量矩阵  [n_docs × 1024]，L2 归一化
   │  taxonomy_current.load_current_taxonomy         （T0 seed / 上一轮 taxonomy_v<N-1>.py）
   │  anchors.flatten_taxonomy + embed_anchors       （当前 taxonomy → 锚点向量）
   ▼
锚点矩阵  [n_anchors × 1024]
   │  matching.match_hierarchical                    （逐篇 L1→L2→L3 余弦 argmax，分层限定子节点）
   ▼
每篇文档的最佳路径 + 每级最高分
   │  thresholds.fit_threshold                       （每级二分量 GMM，单峰时回退 P30，钳制）
   ▼
L1/L2/L3 阈值
   │  discovery.build_unassigned_pools + discover    （欠阈值文档 → 按父节点分池 → HDBSCAN）
   ▼
发现的簇（+ UNKNOWN 桶）
   │  naming.name_clusters                           （LM Studio qwen3-8b-mlx 给每个簇命名，带缓存）
   ▼
命名后的簇
   │  emit.build_final_taxonomy                      （当前 taxonomy 深拷贝 + 嫁接 discovered 节点）
   │  emit.write_taxonomy_py / write_thresholds_json
   │  report.write_report                            （+ 上一轮 → 本轮对比）
   ▼
config/taxonomy_v<N>.py  +  config/taxonomy.py（最新指针）
config/thresholds.json   +  bootstrap_report_v<N>_<时间戳>.md  +  work/snapshot_v<N>.json
```

驱动整条链路的编排器是 `run_bootstrap.py:main`（第 105 行）。向量化拆成独立 CLI（`run_embed.py`），因为它是唯一昂贵、耗时、需要断点续跑的阶段。

### 2.3 用到的核心算法（速览，理由见 §5）

- **向量化**：`BAAI/bge-m3`，1024 维、多语言、通用文本 encoder，`normalize_embeddings=True` → 点积即余弦。
- **主分类：零样本锚点相似度**。每个 taxonomy 节点的书面 `desc` 被向量化成「锚点」；文档按最近锚点余弦逐级归类。手写的 `desc` **就是**监督信号，因此不需要标注数据。
- **阈值：每级二分量高斯混合（GMM）**。分数分布是双峰的（「确实属于」高分峰 + 「不太搭」低分峰），阈值取两分量均值中点；单峰/退化时回退 P30 并钳制。
- **缺口发现：HDBSCAN**（按父节点分池）。无需预设簇数，有一等公民噪声标签（真正杂项 → UNKNOWN），能应对差异极大的池规模。
- **命名：本地生成式 LLM**（qwen3-8b-mlx，`/no_think`）。

### 2.4 三级分类在代码里是怎么做到的

分类采用 **全局最优有效路径匹配（Global Leaf-First Path Matching，方案 A）**（`common.matching.match_hierarchical`）：

**背景与算法演进**：
早期版本采用自顶向下贪心匹配（L1 argmax → 选定 L1 下 L2 argmax → 选定 L2 下 L3 argmax）。但实际业务语料中，L1 作为高度抽象的总类（如 `Human Resources` 与 `Product Management`），文档中的通用管理词汇会导致各 L1 在首层的余弦相似度仅相差微弱的统计噪声（如 `0.4781` vs `0.4743`），贪心决策易过早锁死错误分支，导致高语义细粒度的 L3 真实最优解（如 `0.6105`）被遗漏。

**当前实现流程**：
1. **构建全局叶子路径**：在扁平化 Anchor 树时，提取全部分类树的合法叶子路径 $P_i = (L1, L2, L3)$。
2. **全局批量点积**：对每批文档矩阵直接计算与全部 297 个 Anchor 的余弦点积 `sims = batch @ anchor_vecs.T`。
3. **叶子优先最优路径选取**：提取所有 L3 叶子节点的相似度 `leaf_sims`，每篇文档选取全局得分最高的合法叶子节点作为候选，并回溯其绑定的父节点（L2）和祖父节点（L1），提取各级匹配得分。
4. **逐级阈值判定（`_apply_thresholds`）**：
   - 三级均过阈值（$L1 \ge t_1, L2 \ge t_2, L3 \ge t_3$）→ 判定为 `ASSIGNED` 完整三级分类；
   - $L1/L2$ 过但 $L3$ 欠阈值 → `PARTIAL`（截断至 L2）；
   - $L1$ 过但 $L2$ 欠阈值 → `PARTIAL`（截断至 L1）；
   - $L1$ 欠阈值时，自动触发 **Deep Fallback**：若任意 $L2$ 或 $L3$ 节点独立超过自身阈值，则保留其完整祖先链路，赋予 `FALLBACK` 状态；若均未过阈值则归入 `UNKNOWN`。

锚点文本包含 `"<面包屑>: <desc>"`（`anchors.anchor_text`），使每个叶子 Anchor 自身即具备全局语境消歧能力。全流程支持矩阵批量处理（默认每批 5 万篇）。

---

## 3. Taxonomy 的 T0 → T1 → T2 迭代闭环

从这里开始，Bootstrap 不是「跑一次」，而是一个**简单、可重复、可版本化的闭环**。每一轮用**当前 taxonomy** 对本轮语料范围重新分类，只把没分类上的文档送去发现新分类，然后重新生成一份**完整**的新 taxonomy 并固化为一个版本。随轮次逐步扩大语料范围（30K → 100K → 300K → 500K）。

### 3.1 闭环一图流

**默认模式（只对 UNKNOWN 做发现）：**
```
corpus scope N (--limit N)
  → 用「当前 taxonomy」对本轮 scope 内所有文档做分层锚点分类
  → 得到 UNKNOWN（没过阈值、没归类上的文档）
  → 只把 UNKNOWN 交给 HDBSCAN
  → 有效 cluster → 代表文档 → Qwen 命名
  → 生成一份完整的新 taxonomy → taxonomy_v<N>.py，且 taxonomy.py = 最新
```

**`--rediscover-all` 模式（全量重新发现）：**
```
corpus scope N (--limit N --rediscover-all)
  → 不做 UNKNOWN 过滤，整个 scope 直接进入单一 HDBSCAN 发现池
  → 有效 cluster → Qwen 命名
  → 完整新 taxonomy → taxonomy_v<N>.py，taxonomy.py = 最新
```

### 3.2 T0 / T1 / T2 分别是什么

- **T0 = 手写 seed 骨架**（`SEED_TAXONOMY`，17 L1 / 65 L2 / 215 L3）。磁盘上还没有任何生成过的 taxonomy 时（第一次跑），「当前 taxonomy」就是 T0。
- **T1、T2、… = 每一轮生成的 `taxonomy_v<N>.py`**。它成为下一轮的「当前 taxonomy」。

「当前 taxonomy」的解析顺序（`config/taxonomy_current.py:load_current_taxonomy`，第 83 行）：
1. 版本号最高的 `config/taxonomy_v<N>[_<count>].py`；
2. 否则 `config/taxonomy.py`（最新指针 / 早期运行产物）；
3. 否则 `SEED_TAXONOMY`（T0，第一次运行）。

### 3.3 运行例子：第一次 / 第二次 / 第三次

**第一次：扫描 30K，得到 T1**
```bash
# 1) 准备本轮语料 embedding（若尚未 embed 到 30K）
python -m kb_classifier_bootstrap.run_embed manifest --max-docs 30000
python -m kb_classifier_bootstrap.run_embed embed --batch-size 32
# 2) 跑一轮发现（scope = 30K）
python -m kb_classifier_bootstrap.run_bootstrap --limit 30000
```
行为：用 **T0** 对这 30K 分类 → UNKNOWN → HDBSCAN → Qwen 命名 → 生成完整 **T1**，写入 `taxonomy_v1_30k.py`，同时 `taxonomy.py` = T1。
> `--limit N` = 本轮最多用 manifest 前 N 篇。它复用冻结的 manifest 顺序（`work/manifest.jsonl`），只要覆盖前 N 篇的 embedding 分片存在即可，不要求整个语料 embed 完。

**第二次：扩大到 100K，得到 T2**
```bash
python -m kb_classifier_bootstrap.run_embed manifest --extend-to 100000   # 保前缀，复用已有向量
python -m kb_classifier_bootstrap.run_embed embed --batch-size 32
python -m kb_classifier_bootstrap.run_bootstrap --limit 100000
```
行为（**最重要的默认语义**）：**不是**「T1 + 增量节点」，而是用**当前 taxonomy（T1）** 对整整 100K 重新分类 → 本轮新的 UNKNOWN → 只有这些 UNKNOWN 进 HDBSCAN → 生成一份**完整的 T2**。T2 可以和 T1 很不同（新增/减少/改名/改层级）。这是**预期行为**：本闭环刻意不做继承 / consolidation / merge。
> 一个实现要点（`run_bootstrap.py` 第 255–265 行注释）：嫁接 discovered 节点的基底是**当前 taxonomy 而非裸 seed**。因为 discovery 是针对当前 taxonomy 跑的，某个簇的 `parent_key` 可能是上一轮才发现的节点；若嫁接到裸 seed 会「找不到父节点」而静默丢弃，破坏逐轮加深。基于当前 taxonomy 才能让某个分支「本轮发现、下一轮继续加深」。

**第三次及以后：300K、500K**
```bash
python -m kb_classifier_bootstrap.run_embed manifest --extend-to 300000
python -m kb_classifier_bootstrap.run_embed embed --batch-size 32
python -m kb_classifier_bootstrap.run_bootstrap --limit 300000        # → T3
# ...同样的闭环，scope 更大；embedding 可中断续跑，可跨多天完成
```

### 3.4 为什么默认只对 UNKNOWN 做发现；UNKNOWN 不是永久状态

已经被当前 taxonomy 高置信匹配上的文档没必要再聚类——它们已有类可归。discovery 的意义是「补当前 taxonomy 覆盖不到的缺口」，所以默认只处理 UNKNOWN，扩大 scope 时算力集中在真正没被覆盖的长尾上。

**UNKNOWN 是「某个 scope + 某个 taxonomy 版本下、这一轮没被成功分类」的状态，不是永久属性。** 因为默认模式每轮都用当前 taxonomy 对本轮完整 scope 重新分类：上一轮 30K 里 UNKNOWN 的文档，这一轮 100K 会**重新参与分类**并重新落入本轮 UNKNOWN 池，与新增 70K 的 UNKNOWN 合起来一起发现。一篇文档这轮 UNKNOWN，下一轮可能因为相似文档变多而形成 HDBSCAN cluster、被命名进新 taxonomy。代码里**没有** `UNKNOWN_FOREVER`。

### 3.5 产出物与版本化：闭环怎么形成、历史怎么保留

每一轮成功完成后（`run_bootstrap.py` 第 288–360 行）：
- 生成新版本文件 `config/taxonomy_v<N>_<count>.py`（`N` 取现有 `taxonomy_v*` / `bootstrap_report_v*` / `snapshot_v*` 三族最高版本号 + 1，`<count>` 由本轮**实际文档数**派生，如 `100k`，永不 hardcode）；
- **历史版本永不被覆盖**——`taxonomy_v1_*.py`、`taxonomy_v2_*.py` … 一直保留；
- `config/taxonomy.py` 被重写为与本轮内容一致，即**始终指向最新 taxonomy**，供阶段 B 或下一轮直接 import；
- 同一个 `N` 还对应 `bootstrap_report_v<N>_<时间戳>.md` 和 `work/snapshot_v<N>_<count>.json`，三者一一对应；报告顶部的「上一轮 → 本轮」对比区块，依据上一版本 snapshot 自动生成（`report._render_comparison`，第 121 行）。

没有数据库、没有复杂版本管理——就是按版本号命名的文件 + 一个「最新指针」`taxonomy.py`。这就是闭环：**当前 taxonomy → 分类 → 发现 → 新版本 taxonomy → 成为下一轮的当前 taxonomy**。

### 3.6 发现参数（HDBSCAN min_cluster_size，v2 后重新调优）

`config/settings.py:DiscoverySettings` + `discovery.choose_min_cluster_size`（第 102 行）：
```
min_cluster_size = max(15, min(0.003 × effective_pool_size, 50))
effective_pool_size = min(pool_size, max_pool_for_clustering)   # 默认上限 20000
```
- 旧参数（floor 5 / fraction 0.01 / cap 400）在 23k 那轮把 11.6k 的 L1 UNKNOWN 池推到 `min_cluster_size=116`，HDBSCAN(eom) 返回**零簇**（100% 噪声）。对该池做 mcs sweep 发现簇只在 `mcs ∈ [15,45]` 出现，`≥50` 全塌成噪声。新参数把 mcs 长期保持在这个有效带内。
- `--limit N` 控本轮**语料范围**；`max_pool_for_clustering` 控**单个发现池喂给 HDBSCAN 的规模**，两者互不混淆。池超上限时先抽样聚类、其余按最近质心回填。
- 池太小（`< min_pool_size` 或 `< min_cluster_size`）无法形成有效 cluster，这些文档**保持 UNKNOWN**，不强行成簇、不送 LLM。

---

## 4. 当前实现（按最新代码）

行号均对照当前源码核对。

### Seed taxonomy（T0，人手写骨架）
- **`config/_node.py`** — `node()`（第 25 行）构造节点字典（`name`/`desc`/`source="seed"`/`children`），定义 `SEED` / `DISCOVERED` 常量。
- **`config/taxonomy_seed_business.py`** — `BUSINESS_SEED`：9 个银行业务线 L1（Retail/Corporate Banking、Payments、Lending、Treasury、Risk & Compliance、Wealth Management、Trade Finance、Digital Banking）及 L2/L3。
- **`config/taxonomy_seed_functions.py`** — `FUNCTION_SEED`：8 个职能 L1（Corporate Finance & Accounting、HR、Legal、**Technology & Engineering**（刻意展开最深）、Sales & Marketing、Procurement & Vendor Management、Facilities & Administration、**Product Management**（语料实况支持的骨架扩展项））。
- **`config/taxonomy_seed.py`** — 合并为 `SEED_TAXONOMY`；`validate_taxonomy()`（第 71 行）强制 key 全局唯一、深度恰为 3、`desc` 非空；`count_by_level()`（第 83 行）统计各级节点数。校验在 import 时执行。当前骨架 **17 / 65 / 215**。

### `config/taxonomy_current.py` — 解析「当前 taxonomy」
- `load_current_taxonomy()`（第 83 行）：按 `taxonomy_v<N>.py → taxonomy.py → SEED_TAXONOMY(T0)` 顺序解析并结构校验，返回 `(taxonomy, source_label)`。
- `latest_taxonomy_version()`（第 72 行）：扫出最高版本号。兼容 `taxonomy_v3.py` 与 `taxonomy_v4_100k.py` 两种命名。

### `bootstrap/anchors.py` — taxonomy → 可向量化锚点
- `flatten_taxonomy()`（第 43 行）：深度优先拍平，顺序确定（锚点行位置稳定，匹配按位置索引）。
- `anchor_text()`（第 78 行）：被向量化的字符串 = `"<面包屑>: <desc>"`。
- `children_index()`（第 93 行）：`parent_key → 子锚点行`（`None → L1`），逐级匹配的关键。
- `embed_anchors()`（第 115 行）：向量化所有锚点，缓存到 `work/anchor_embeddings.npz`，键为锚点文本 + embedding 设置指纹（改 taxonomy 会透明重建）。

### `common/matching.py` — 全局最优叶子路径匹配（方案 A）
- `match_hierarchical()`（第 66 行）：提取全量合法叶子路径，批量矩阵乘法一次性求出全部 Anchor 相似度，全局最优选取 L3 叶子节点并绑定回溯 L2/L1 祖先路径。
- `level_scores()`（第 138 行）抽取每级最高分供定阈值；`save_match_results()`（第 146 行）落盘 `work/match_results.npz`。

### `test_classifier_regression.py` — 分类器回归测试套件
- 每次修改 `kb_classifier` 必须运行此测试进行回归：
  ```bash
  python3 -m pytest kb_classifier/test_classifier_regression.py
  # 或：
  python3 -m kb_classifier.test_classifier_regression
  ```
- 覆盖测试用例：
  1. `test_people_ops_offer_playbook_regression`: 验证 Offer 评分与 Onboarding Playbook 正确分类至 `Human Resources > Recruitment > Offers & Hiring Decisions`（避免贪心 L1 误分类）；
  2. `test_tech_infrastructure_document`: 验证 SRE/K8s 技术基础设施文档分类至 `Technology & Engineering`；
  3. `test_risk_compliance_aml_document`: 验证反洗钱/KYC 政策分类至 `Risk & Compliance`；
  4. `test_gibberish_unknown_document`: 验证无意义乱码文档正确触发 `UNKNOWN`（depth=0）；
  5. `test_hierarchical_path_consistency`: 验证分类输出严格满足父子拓扑合法性（L2 为 L1 子节点，L3 为 L2 子节点）。

### `bootstrap/thresholds.py` — 每级阈值
- `fit_threshold()`（第 56 行）：拟合二分量 GMM（`GaussianMixture`，第 85 行），阈值取两均值中点；双护栏（分离度 < 1.0 合并标准差、或某分量权重 < 0.05）触发 P30 回退；样本 < 50 直接 P30；结果钳到 `[0.15, 0.80]`。返回含完整诊断的 `ThresholdResult`（第 37 行）。

### `bootstrap/discovery.py` — 缺口发现（唯一用聚类处）
- `build_unassigned_pools()`（第 69 行）：欠阈值文档按 `(level, parent_key)` 分池，每篇恰好一个池。
- `choose_min_cluster_size()`（第 102 行）：`max(15, min(0.003×effective_pool, 50))`。
- `_cluster_one_pool()`（第 139 行）：单池跑 `sklearn.cluster.HDBSCAN`（第 198 行）；超大池先抽样再按最近质心回填；保留最大若干簇；取离质心最近的代表文档。
- `discover()`（第 265 行）：驱动所有池，返回簇 + 每池 `PoolReport`（第 56 行）。

### `bootstrap/naming.py` — 本地 LLM 命名
- `_build_prompt()`（第 60 行）：用代表标题构造 prompt，系统提示追加 `/no_think`（第 81 行）抑制推理模型思维链。
- `_call_llm()`（第 120 行）：`POST {api_base}/chat/completions`（第 128 行），解析 `content`，空则回退 `reasoning_content`，再回退首个 `{...}`。
- `name_cluster()`（第 151 行）：带重试 + 确定性回退名（`Uncategorized <parent> Topic`，标 `naming_failed`）。
- `name_clusters()`（第 231 行）：给每个非 UNKNOWN 簇命名，磁盘缓存 `work/naming_cache.json`（重跑不重复调 LLM）。

### `bootstrap/emit.py` — 写产出物
- `build_final_taxonomy()`（第 129 行）：深拷贝**当前 taxonomy**（`base_tax`），把每个命名后的簇作为 `source="discovered"` 节点嫁接到父节点下，`_unique_key`（第 61 行）保证 key 全局唯一，`_discovered_l1/_l2/_l3`（第 89–128 行）保持严格三级深。
- `write_taxonomy_py()`（第 199 行）：序列化成可 import 的 `.py`（写 `taxonomy_v<N>.py` 与 `taxonomy.py` 两份）。
- `write_thresholds_json()`（第 233 行）：`L1/L2/L3` + `method_used` + `diagnostics`。

### `bootstrap/report.py` — 写报告 + 上一轮→本轮对比
- `write_report()`（第 206 行）：处理文档数、按 L1 分布、seed/discovered 节点数、发现节点表、分池诊断、UNKNOWN 占比、阈值决策、错配结论。
- `build_snapshot()`（第 88 行）：机器可读快照；`_render_comparison()`（第 121 行）在有上一轮快照时渲染对比区块；`focus_l1_subtree_counts()`（第 74 行）跟踪数据密集 L1 之下 L2/L3 的增长。

### `run_bootstrap.py` — 编排器（一轮发现）
- `main()`（第 105 行）：定版本号 → 校验 seed → 载入当前 taxonomy → 载入本轮 scope 的 embedding → 锚点 → 匹配 → 阈值 → 发现（默认 UNKNOWN-only；`--rediscover-all` 走单一全量池）→ 命名 → 产出（版本文件 + 最新指针）→ 报告（+ 对比）。启动打印 `SETTINGS.describe()`。参数：`--limit N`、`--rediscover-all`、`--dry-run`。`_ensure_embeddings_complete()`（第 79 行）只要求覆盖前 `N` 篇的分片存在。

### 配套模块（向量化侧）
- **`config/settings.py`** — 全部超参（冻结 dataclass）+ `SETTINGS` 单例 + `describe()` + `embedding_fingerprint()`；`Paths` 提供版本化产物路径：`next_version()`、`taxonomy_version_path()`、`snapshot_path()`、`report_path_for_version()`、`sample_count_label()`、`vector_store_path`。
- **`bootstrap/corpus.py`** — 扫描、解析、分层抽样（`stratified_sample`）、manifest 冻结（`build_manifest`）与保前缀增长（`extend_manifest`）。
- **`bootstrap/embedder.py`** — 可续跑 bge-m3 向量化：`embed_corpus_resumable()`（第 393 行）、分片检查点、缓存校验、`load_all_embeddings()`；`_resolve_device()`（第 236 行）选设备 CUDA → MPS → CPU（本机 Apple M5 走 MPS）；`encode_documents_cached()`（第 325 行）接内容寻址缓存。
- **`bootstrap/vector_store.py`** — 内容寻址 embedding 缓存（SQLite，见 §4.1）。
- **`run_embed.py`** — 独立可续跑 CLI：`manifest`（含 `--extend-to`）、`status`、`embed`、`benchmark`。

### 4.1 内容寻址 embedding 缓存（跨 manifest 复用）
除按 manifest 行位置缓存的 positional shard（`work/embeddings/*.npy`），另有一层内容寻址缓存 `work/vector_store.sqlite`，用于 manifest 变化（重排/增删/fingerprint 改变）时仍复用已算向量。缓存键只由「实际送入 bge-m3 的最终文本」+「embedding 配置指纹」决定：
```
content_hash = sha256(rendered_embed_text)          # Document.embed_text(...)
cache_key    = sha256(content_hash + embedding_fingerprint)
```
文件移动/manifest 顺序变化/增删文档 → 可复用；文档内容/截断参数/repeat-title/fp16/模型改变 → 指纹变化 → 不复用。positional shard 有效时直接复用、**不查 SQLite**；缺失时才逐篇查缓存、未命中才调 bge-m3 并写回。删 `work/vector_store.sqlite` 是安全的（下轮重算未命中项）。

---

## 5. 与其他分类/聚类算法的比较

本项目实质是「**零样本锚点分类（主）+ 无监督缺口发现（辅）+ LLM 命名**」。下面把每个环节和常见替代方案对比，解释为何在**无标注 + 只用本地模型 + 无人工审核**这三条约束下当前选型更合适。

### 5.1 主分类：为什么不是 fastText / kNN / 有监督分类器

| 方案 | 需要什么 | 在本项目的问题 |
|---|---|---|
| **fastText 有监督** | 每类大量标注样本 | **没有标注数据**，直接出局。且 fastText 是词袋 + n-gram 静态表示，抓不到句级语义（「latency spiked during rollout」和「p99 regression after deploy」词面不同、语义相同，它难以对齐）。 |
| **kNN 分类** | 一个已标注向量库 | 同样需要标注。kNN 是「有邻居标签」时的好基线，但我们连一个带标签的邻居都没有。 |
| **LLM 直接逐篇分类**（把 taxonomy 塞进 prompt 让它选） | 云/本地大模型，每篇一次调用 | 违反「阶段 B 廉价、无云端」的诉求：50 万篇每篇调一次 LLM 太贵/太慢；且结果不稳定、难复现。 |
| **本项目：零样本锚点相似度** | 一段每个节点的书面 `desc` | 手写 `desc` **就是**监督信号；分类退化为一次余弦 argmax，阶段 B 每篇只需几次点积，快、稳、可复现、全本地。 |

一句话：**有标注就该上有监督（fastText/kNN/线性分类器都行），没标注时把「分类描述」向量化做零样本匹配是性价比最高的替代。** bge-m3 这类句向量模型正是让「零样本」可行的关键——静态词向量（fastText/word2vec）做不到句级语义对齐。

### 5.2 缺口发现：为什么是 HDBSCAN，不是 K-Means / ANN / Leiden

| 方案 | 特点 | 在本项目的问题 / 适配 |
|---|---|---|
| **K-Means** | 需**预设簇数 K**；每点都必被分入某簇（无噪声概念）；假设球状等方差簇 | 我们**不知道** UNKNOWN 里藏几个主题（K 未知）；且会把真正的杂项文档硬塞进最近簇，污染 taxonomy。**正是我们要避免的。** |
| **ANN（HNSW/IVF/FAISS 等）** | 近似最近邻**检索**，不是聚类 | ANN 解决的是「在百万向量里快速找 top-k 邻居」，是**加速检索**的工具，不产出簇。可作为未来给锚点匹配/大池提速的手段，但它本身不做「发现新分类」这件事。 |
| **Leiden / Louvain（图社区发现）** | 在相似度图上找社区，无需预设簇数，质量高 | **很有竞争力的替代**：先用 ANN 建 kNN 图再跑 Leiden，能得到高质量社区。代价是要自己构图 + 选分辨率参数 + 处理离群点（社区发现没有天然「噪声」标签，杂项会被塞进小社区）。属于合理演进方向。 |
| **GMM 聚类** | 软分配、椭圆簇 | 我们已用 GMM 做**阈值**（1 维分数分布），但在 1024 维上做密度聚类不如 HDBSCAN 稳健，且仍需定 K。 |
| **本项目：HDBSCAN** | 无需预设 K；一等公民**噪声**标签；容忍变密度/变大小簇 | 三点全中约束：(a) K 未知 → 自动定簇数；(b) 真正杂项 → 标噪声 → 我们记为 **UNKNOWN 不强行归类**（契合「宁可 UNKNOWN 也不错分」）；(c) 池规模从几篇到上万篇差异极大。L2 归一化向量上欧氏距离与余弦单调等价，走它的快速欧氏路径。 |

一句话：**要「不知道有几类、且允许一部分是噪声」的发现，HDBSCAN 是最省心的默认；追求更高社区质量可演进到 ANN-kNN 图 + Leiden；K-Means 因为要预设 K 且无噪声概念，不适合这里。**

### 5.3 命名：为什么必须是生成式 LLM，而不是 encoder
bge-m3 是 encoder，只能把文本映射成向量算相似度，**结构上没有 decoder**，无法完成「读五个标题、生成一个新分类名 + 一句话描述」。所以分工是：**bge-m3 找质心 + 最近代表文档（相似度，本行），LLM 把代表变成名字（生成）。** 用小到中等规模的**本地** LLM 足矣（本项目 qwen3-8b-mlx），因为这是轻量文本理解任务；`/no_think` 关掉推理链以省延迟、避免截断。

---

## 6. 写给转型 AI Engineering 的后端开发者

如果你是后端 / 平台工程师，正在学 AI Engineering、想做企业知识库 RAG，并拿这个项目找工作，下面是这份代码里**可迁移、面试能讲**的工程要点。

**这正是 RAG 的「ingestion / indexing」前半段。** 生产级企业 RAG 不是「把所有文档一股脑塞进向量库然后 top-k」。真正拉开差距的是**入库前的结构化**：给每篇文档打上可靠的分类 metadata，检索时才能做 **metadata 过滤 + 混合检索**（先按分类/权限/时间收窄，再向量召回），显著提升召回精度、降低串扰。本项目产出的 `taxonomy.py` + 每篇文档的三级路径，就是喂给下游 RAG 的 metadata 层。面试里能把「classifier → OKF metadata → 阶段 B 逐篇打标 → RAG 检索时按分类过滤」这条链路讲清楚，比只会 `embed + top-k` 高一个层次。

**值得内化的概念：**
- **Embedding = 语义的数值化**；`normalize_embeddings=True` 后**点积即余弦**，这是所有相似度检索的地基。
- **零样本分类**：没有标注时，把「类的描述」向量化做匹配。这个思路能直接迁到意图识别、路由、去重、近重复检测。
- **用分布定阈值，而不是拍脑袋常数**：GMM 双峰 + 护栏 + 回退，是「让数据自己说话」的可复现做法。面试常问「你的相似度阈值怎么定的」——答「从分数分布拟合，单峰回退分位数」远胜「试出来 0.7」。
- **聚类要能产出 UNKNOWN**：HDBSCAN 的噪声标签体现了「宁可不分类也不错分类」的工程判断，企业场景里这比「强行 100% 覆盖」更值钱。
- **encoder vs decoder 的分工**：知道什么任务该用哪种模型，是 AI engineering 的基本功。

**这份代码里的软件工程实践（后端强项，正好加分）：**
- **断点续跑 + 幂等**：`embed_corpus_resumable` 用「冻结 manifest + 分片检查点 + 原子重命名 + 指纹校验」保证 Ctrl-C 安全、可跨天续跑——这是把研究脚本变成生产管线的关键工程。
- **两级缓存**：positional shard（按位置）+ 内容寻址 SQLite（按内容），manifest 变了也能复用向量。缓存键设计（内容哈希 + 配置指纹）是可以细讲的点。
- **确定性 + 可复现**：固定随机种子、冻结文档顺序、所有超参集中在 `settings.py` 且开跑即打印。
- **无数据库的版本化**：`taxonomy_v<N>.py`（历史永不覆盖）+ `taxonomy.py`（最新指针）+ 配套 report/snapshot，闭环靠文件名 + 一个指针完成。简单、可 diff、可回溯。
- **优雅降级**：LLM 命名失败有确定性回退名，管线永不卡死；设备选择 CUDA→MPS→CPU 自适应。
- **面向错配的诚实报告**：把「语料和 taxonomy 不匹配」写进产出物而不是藏起来——工程成熟度的体现。

**能延伸的话题（面试深挖时可提）：** 用 ANN（HNSW/FAISS）给大规模锚点匹配和大池聚类提速；用 ANN-kNN 图 + Leiden 提升发现质量；给阶段 B 加上「多锚点软投票 + 温度校准」；把 taxonomy 演进接入评测（每轮对一个小 gold set 量 precision/recall）。这些正是「从能跑到生产级」的进阶方向。

---

## 7. 运行历史与如何运行

### 运行历史（同一套代码，逐步扩大规模；报告文件均保留）
所有运行都是同一条流水线（bge-m3 → 锚点匹配 → 二分量 GMM 定阈值 → 按父节点分池的 HDBSCAN → qwen3-8b-mlx 命名），区别只在语料规模与「当前 taxonomy」版本。环境：macOS，Apple M5（arm64），Python 3.9；向量化走 MPS；命名对接本地 LM Studio（`http://localhost:1234/v1`，`qwen3-8b-mlx`）。

| 报告 | 文档数 | 说明 |
|---|---:|---|
| `bootstrap_report_v1_20260830-0045.md` | 3,000 | 首轮（对 T0）。阈值 L1 0.4534 / L2 0.4667 / L3 0.4893（全 GMM，未回退）；发现并命名 6 个簇。向量化 MPS 约 7.4 docs/s（交接机器仅 0.57）。 |
| `bootstrap_report_v2_20260830-1228.md` | 23,000 | 通过 manifest 前缀扩展复用已有向量，只 embed 新增部分。阈值几乎不变（3k→23k 三级都在 ~0.002 内）。 |
| `bootstrap_report_v3_20260830-1718.md` | 23,000 | 版本化闭环轮次；含 v→v 对比区块。 |
| `bootstrap_report_v4_50k_20260830-2150.md` | 50,000 | 50K 轮。真实数据长出的 discovered L1 开始主导分布（如 `service_latency_alerts` 45.9%、`demo_coordination` 20.4%），印证语料/骨架错配与闭环的价值。 |
| `bootstrap_report_v5_50k_20260830-2205.md` | 50,000 | 又一轮：发现 `release_operations`(6751 docs)、`billing_anomalies`(1950 docs) 等新 L1，节点数逐层增长。 |

要点：**阈值是分布统计量，3k 规模就已稳定**；**UNKNOWN 占比随样本量上升**（更大样本暴露更多银行骨架外的长尾，符合错配结论，非退化）；**真实数据驱动的 discovered 分类**（service latency alerts、demo coordination、release operations、billing anomalies）正是闭环相对「只用手写骨架」的增量价值。

### 如何运行
```bash
# 1. 建（或扩展）文档 manifest
python -m kb_classifier_bootstrap.run_embed manifest --max-docs 30000
#    ……或在已有 manifest 基础上增长，复用其 embedding 缓存：
# python -m kb_classifier_bootstrap.run_embed manifest --extend-to 100000

# 2. 向量化（可续跑；Ctrl-C 安全，重跑同一命令即续跑）
python -m kb_classifier_bootstrap.run_embed embed --batch-size 32
python -m kb_classifier_bootstrap.run_embed status      # 查看进度

# 3. 跑一轮发现（需要 LM Studio 在 localhost:1234 提供 qwen3-8b-mlx）
python -m kb_classifier_bootstrap.run_bootstrap --limit 30000
#    全量重新发现（更重）：
# python -m kb_classifier_bootstrap.run_bootstrap --limit 100000 --rediscover-all
#    不调 LLM 的冒烟测试：
# python -m kb_classifier_bootstrap.run_bootstrap --limit 30000 --dry-run
```
产出物：`config/taxonomy_v<N>_<count>.py`（历史保留）+ `config/taxonomy.py`（最新指针）+ `config/thresholds.json` + `bootstrap_report_v<N>_<时间戳>.md` + `work/snapshot_v<N>_<count>.json`。依赖见 `requirements.txt`（bge-m3 需 `torch` + `sentence-transformers`；聚类需 `scikit-learn`；命名需本地 LM Studio——不调云、不用 Ollama）。

### 一句话总结
- **默认**：`scope → 当前 taxonomy 分类 → UNKNOWN → HDBSCAN → LLM → 完整新 taxonomy`。
- **`--rediscover-all`**：`scope → 全部文档 discovery → HDBSCAN → LLM → 完整新 taxonomy`。
- **UNKNOWN 是「当前 taxonomy / 当前 scope 下」的状态，不是永久状态**；扩大 scope 后重新参与分类，有机会被重新发现成新分类。
- 每轮产出 `taxonomy_v<N>.py`（历史保留）+ `taxonomy.py`（最新）+ `bootstrap_report_v<N>_*.md` + `snapshot_v<N>.json`。

---

## 8. 原始需求（逐字保存）与环境适配决策

> 本节把原 `HANDOFF/00_ORIGINAL_TASK.md` 的原始需求 prompt 合并进来（HANDOFF 目录已删除），并记录实现时因运行环境不同而做出的具体决策及其理由。**原始 prompt 是唯一需求来源**；下方「环境适配决策」是在不偏离方法论的前提下对落地细节的调整。

### 8.1 原始任务 prompt（逐字保存）

**任务：企业知识库文章分类器 — Bootstrap 阶段（一次性全量扫描）**

**背景。** 把一批银行企业内部文章导入知识库前，需要给每篇文章打上一个 3 级分类（如 `Finance > Payments > Payment Processing`），作为 metadata 随文档转换为 OKF 格式后一起入 embedding 库。系统分两个阶段，本次任务只做 Bootstrap 阶段：

- **阶段 A（本次任务）**：拿到一批初始文章，做一次全量扫描，自动生成一份三级分类 taxonomy + 每级分类阈值。之后这份 taxonomy 和阈值会被固定下来，长期复用。
- **阶段 B（不在本次任务范围）**：之后每篇文章逐篇导入时，用阶段 A 产出的 taxonomy+阈值做规则化的逐级匹配分类，不再聚类。

**本次任务全程不允许调用云端 LLM API，只允许使用本地模型。全程不需要任何人工审核步骤——所有判断（包括新分类的命名）都要由代码自动完成。**

**输入。** `all_documents/` 目录下的一批文章（格式自行探测：txt/markdown/json 等）；每篇至少含标题和正文。

**分类体系要求：L1/L2/L3 都要预先 hardcode 一批锚点。** 跟「只 hardcode L1」的方案不同，这次 L1/L2/L3 都要预先写好合理的锚点骨架，聚类发现只用来补充骨架没覆盖到的地方。一级分类必须同时覆盖两类内容且命名能区分开：**业务线**（Retail Banking / Corporate Banking / Payments / Lending / Treasury / Risk & Compliance / Wealth Management / Trade Finance / Digital Banking）与**通用职能**（Corporate Finance & Accounting / Human Resources / Legal / Technology & Engineering / Sales & Marketing / Procurement & Vendor Management / Facilities & Administration）。在骨架基础上用银行/企业业务知识补全 L2/L3，写入 `config/taxonomy.py`，每个节点都要有一句话语义 `desc`（不是标签词）。

**技术方案：锚点优先匹配 + 缺口发现（聚类只用于补充）。**
1. **全量 Embedding**：本地 `BAAI/bge-m3`（sentence-transformers），对文章（标题+正文前若干字）与所有锚点 desc 做 embedding。
2. **逐级锚点匹配**：每篇文章先在 L1 锚点里找最高相似度，再在选中 L1 下的 L2、再 L3，形成完整路径与每级分数；收集每级最高分，用二分 GMM 拟合，两个高斯均值中点作 threshold（单峰用 P30 fallback 并记日志）。
3. **缺口发现**：对某级低于阈值的文章按父节点分别维护「未分配池」；池文章数 ≥5 才跑 HDBSCAN（否则标 UNKNOWN）；新簇作为 `source:"discovered"` 节点插入 taxonomy，与手写 `source:"seed"` 区分。
4. **本地小模型命名**：原 prompt 要求优先用 `qwen2.5-coder:7b`（本地 Ollama），并先做一次 `qwen2.5-coder:7b` vs `qwen2.5-3b` 的命名对比实验（一次性选型验证，非人工介入分类）；bge-m3 只负责找质心与最近代表文档，不做命名（它是纯 encoder）。

**输出产物**：`config/taxonomy.py`（三级树，节点含 name/desc/source/children）、`config/thresholds.json`（L1/L2/L3 + method_used）、`bootstrap_report.md`（文章总数、各级 seed/discovered 节点数、每个 discovered 节点命名+簇文章数、命名对比实验样例、各级 UNKNOWN 数量与占比）。

**注意事项**：全程本地模型、不调云端；无人工审核；关键决策点（阈值方法、簇数、每级最小样本数等超参）打清晰日志；发现明显更优的替代方案可在注释中说明并采用，但不偏离整体方法论（锚点优先匹配 + 缺口聚类发现 + GMM 阈值 + 本地小模型命名）。代码放在 `kb_classifier_bootstrap/`。

**追加约束**：embedding 进度必须能落盘、中断后可重启续跑（已实现，见 `bootstrap/embedder.py`）；是否分层抽样由用户决定（`--max-docs` 两种模式都支持）。

### 8.2 环境适配决策（本机落地时的偏离及理由）

原 prompt 假设的运行环境（Windows + CUDA GPU + Ollama）与实际运行机器不同。以下决策在**不改变方法论**的前提下适配了真实环境，均已在代码注释与 `bootstrap_report_*.md` 中标注：

| 维度 | 原 prompt | 实际决策 | 理由 |
|---|---|---|---|
| 运行机器 | Windows / CUDA GPU | macOS，Apple M5（arm64），Python 3.9 | 交接机器 Quadro T1000 实测仅 0.57 docs/s（全量需 ~251h），换本机 MPS 后约 7.4 docs/s。 |
| 向量化设备 | CUDA | **MPS**（`embedder._resolve_device` 选 CUDA→MPS→CPU） | 本机无 CUDA；Apple GPU 走 MPS 明显快于 CPU。fp16 仅在 CUDA 启用，MPS/CPU 走 fp32 保稳。 |
| 命名服务 | Ollama `/api/generate` | **LM Studio，OpenAI 兼容 `/v1/chat/completions`** | 本机装的是 LM Studio，非 Ollama。`naming._call_llm` 按 OpenAI schema 调用。全程仍本地、无云端。 |
| 命名模型 | `qwen2.5-coder:7b` | **`qwen3-8b-mlx`** | LM Studio 里已加载的模型；对「读几个标题起名」这类轻量任务足够。 |
| 抑制思维链 | （无，非推理模型） | **系统提示追加 `/no_think`** | qwen3-8b 是推理模型，默认会消耗 token 做思维链、可能截断答案返回空 `content`。实测 `chat_template_kwargs {enable_thinking:false}` 在该 LM Studio 版本**无效**，`/no_think` 有效（reasoning_tokens 降到 1）。 |
| 7b vs 3b 对比实验 | 要求做 | **记为 N/A（不做）** | 本机只加载了单一生成模型，无第二个模型可比；报告如实写明 N/A，不伪造第二个模型输出。`naming.run_model_comparison` 返回空并记日志。 |
| Bootstrap 规模 | 一次性全量 | **分层抽样，逐轮扩大（3k→23k→50k…）** | CPU/MPS 上全量 51 万篇不现实；分层抽样保证每 channel/mailbox/space 有代表，且阈值是分布统计量，数千篇即稳定。embedding 可续跑，规模可逐步扩大。 |
| 语料内容 | 假设为银行文档 | **实为 AI 推理平台公司内部资料** | 见 §1 错配说明：照要求写全银行骨架，同时把 `Technology & Engineering` 展开最细，并在报告里明确错配结论。 |

> 相对原 prompt，实现还**超出**了「一次性 Bootstrap」的范围，落地成 §3 描述的**可版本化 T0→T1→T2 逐轮发现闭环**（`taxonomy_current.py` + 版本化产物 + 内容寻址缓存）。这属于「发现明显更优的替代方案可采用」允许的范围，方法论（锚点匹配 + GMM 阈值 + HDBSCAN 缺口发现 + 本地 LLM 命名）未变。

---

## 9. 下一阶段任务建议

按「先补齐闭环价值 → 再上生产化 → 再做质量与规模」的优先级排列。每条都标注了大致落点，方便直接开工。

### 9.1 最高优先：把 taxonomy 冻结并落地阶段 B（逐篇分类器）
阶段 A 的产物（`taxonomy.py` + `thresholds.json`）目前没有消费方。建议新建 `stage_b/`：
- **`stage_b/classify.py`**：输入单篇文档 → 复用 `anchors.flatten_taxonomy` + `embed_anchors`（当前 taxonomy）、`matching.match_hierarchical` 的逐级 argmax，读 `thresholds.json` 做过/欠阈值判定，欠阈值即 `UNKNOWN`。**不聚类、不调 LLM**，每篇只几次点积，契合原 prompt 阶段 B 定义。
- **产出 OKF metadata**：把三级路径 + 每级分数写成文档 metadata，供下游 RAG 做 metadata 过滤 + 混合检索。
- **批量入库脚本**：对 `all_documents/` 全量逐篇打标，落一份 `doc_id → 分类路径` 的映射（parquet/jsonl）。
- **冻结版本**：选定某一轮 `taxonomy_v<N>.py` 作为阶段 B 生产版本，写清依赖的版本号，避免阶段 B 跟着阶段 A 每轮漂移。

### 9.2 质量评测：给闭环装上「刻度」
现在每轮好坏靠人读报告。建议：
- **建一个小 gold set**（几百篇人工/半自动标注的三级标签），每轮对它量 **precision/recall/UNKNOWN 率**，写进报告的对比区块（可扩展 `report._render_comparison`）。
- **锚点 desc 的召回诊断**：统计每个 seed 节点实际吸附的文档数，长期 0 命中的银行节点可考虑降权或折叠（当前它们只是稀释分布）。
- **阈值敏感性**：对 L1/L2/L3 阈值做 ±0.02 的 sweep，看 UNKNOWN 率与错分率的权衡曲线，佐证 GMM 中点选择。

### 9.3 检索/聚类提速（规模上到 300K–500K 时）
- **锚点匹配用 ANN**：锚点虽只有几百个，但文档到 50 万时可用 FAISS/HNSW 建库加速阶段 B 的逐篇匹配。
- **大池发现用 ANN-kNN 图 + Leiden**：§5.2 提到的演进方向。当某个 L1 UNKNOWN 池到几十万时，HDBSCAN 内存吃紧，先 ANN 建 kNN 图再跑 Leiden 社区发现，质量与可扩展性更好；保留「离群点 → UNKNOWN」的语义。
- **向量存储**：当前 `work/vector_store.sqlite` 够用；上量后可换 chroma/lancedb 等，键设计（内容哈希 + 配置指纹）保持不变。

### 9.4 命名与 taxonomy 治理
- **命名一致性**：给 `naming` 加「已有兄弟节点名」上下文，避免同一父下出现语义重复的 discovered 名；可加一步「新名 vs 现有节点」的相似度去重。
- **taxonomy consolidation（可选，需谨慎）**：当前闭环刻意不做 merge。若要引入跨轮合并，应做成**显式、可审计、可回滚**的独立步骤（读两个版本 snapshot，产出 merge 提案供离线审阅），不要污染默认闭环的「完整重生成」语义。
- **discovered → seed 提升**：稳定出现多轮的 discovered 节点可考虑「固化」为 seed（人工或规则），减少每轮重复发现。

### 9.5 工程健壮性
- **matching 的非有限值**：`matching.match_hierarchical`（第 66 行）点积在 fp16 往返边界偶发 `divide/overflow/invalid` warning，结果虽正确，建议用 `np.errstate` + `np.nan_to_num` 消噪，让日志更干净。
- **naming 的并发**：LM Studio 支持并发时，可对多个簇并行命名缩短单轮时间（当前串行，带缓存）。
- **测试覆盖**：已有 `bootstrap/test_vector_store.py`；建议补 `matching`/`thresholds`/`discovery`/`emit` 的单测（用假向量，参考本次开发时的 `/tmp` 逻辑冒烟测），把「taxonomy.py 可 import + 深度恰 3 + key 唯一」做成 CI 断言。

### 9.6 一句话优先级
**先做 §9.1（阶段 B，让产物有消费方）与 §9.2（评测，让每轮有刻度）**——这两条把「能跑的 Bootstrap」变成「可度量、可交付的分类系统」；§9.3–9.5 是上规模与生产化后的进阶项。

### 9.7 Next Phase: Move Deep-Fallback Similarity Computation into Shared Matcher

> **Next Phase / Future Work — Not implemented in the current change.**

阶段 B 已实现 **Top-down + Deep Fallback** 路由（见 `taxonomy_classifier/classify.py`）：
正常 L1 通过时保持原有 top-down；当 L1 分数低于 L1 阈值时，不直接判 `UNKNOWN`，而是
在更深层寻找强匹配证据。

**当前阶段采用 Option 1**（已实现）：

```text
classifier 在 L1 fail 时
额外执行 doc_vec · all_anchor_vecs（复用已加载的向量，不重新 embedding）
在 L2/L3 中取「达到各自 level 阈值」且 raw score 最高的 candidate
用该 anchor 的 path_keys 回填完整 taxonomy path
```

**下一阶段可考虑 Option 2**（尚未实现）：

```text
修改 shared match_hierarchical
使 matcher 在 hierarchical routing 的同时
提供 all-level similarity scores
```

trade-off：

- ✅ 可以避免 classifier 层重复计算 all-anchor similarity；
- ✅ 可以让 shared matcher 统一管理 similarity results；
- ⚠️ 但 `match_hierarchical` 是 **shared component**，可能影响 Stage A（bootstrap）或
  其他调用方（它当前的 per-branch pruning 行为被多处依赖）；
- 因此当前阶段**刻意不修改它**；
- 等 Deep Fallback 在 validation corpus 上验证收益后，再评估是否值得把该能力下沉到
  shared matcher。
