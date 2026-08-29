# 进度报告与交接状态

**交接时间**：2026-08-29
**交接原因**：原机器 GPU (Quadro T1000, 4GB) 实测 embedding 吞吐仅 **0.57 docs/s**，全量语料需 251 小时，不具备可行性。
**总体完成度**：约 **35%**。三个最终产出物（`config/taxonomy.py`、`config/thresholds.json`、`bootstrap_report.md`）**均未生成**。

---

## 1. 已完成部分

### 1.1 已落盘的代码

| 文件 | 行数 | 状态 | 说明 |
|---|---|---|---|
| `config/settings.py` | ~250 | ✅ 完成 | 全部超参集中定义，含 `describe()` 打印所有超参到日志、`embedding_fingerprint()` 用于缓存校验 |
| `config/_node.py` | ~35 | ✅ 完成 | taxonomy 节点构造器，定义 `SEED`/`DISCOVERED` 常量 |
| `bootstrap/corpus.py` | ~300 | ✅ 完成 | 语料扫描、标题/正文解析、**分层抽样**、冻结 manifest、指纹计算 |
| `bootstrap/embedder.py` | ~420 | ✅ 完成 | **可中断续跑的分片式 embedding**（本次交接的核心成果） |
| `run_embed.py` | ~330 | ✅ 完成 | embedding 阶段独立 CLI：`manifest` / `status` / `embed` / `benchmark` 四个子命令 |
| `scan_corpus.py` | ~80 | ✅ 完成（一次性工具） | 语料格式探测脚本，已跑完，结果见 `_scan.txt` |
| `download_model.py` | ~30 | ✅ 完成（一次性工具） | 预拉取 bge-m3 |
| `bench_encode.py` | ~85 | ⚠️ 已写未跑 | batch/seqlen/dtype 扫描微基准，用于在新机器上选最优操作点。**新机器第一件事就跑它** |

### 1.2 已验证可用的功能

- ✅ **语料扫描 + 分层抽样**：实跑通过。扫描 511,887 篇（耗时 3 分 20 秒），按 `<source>/<subdir>` 分层抽样，落盘 `work/manifest.jsonl`。
- ✅ **manifest 冻结 + 指纹**：实跑通过，指纹 `5d13ea96b85d6c27d58c7ee72dc95aae`（600 篇抽样版，新机器会重建，此值会变）。
- ✅ **bge-m3 加载**：cuda + fp16 加载成功，dim=1024，`max_seq_length` 可设为 512。
- ✅ **分片写盘 + 原子重命名**：实跑通过。落盘 shard 校验为 `(200, 1024)` float16，读回归一化后范数 ≈ 1.0000。
- ✅ **断点续跑**：实跑验证。已有 2/3 分片时重跑，日志确认 `2/3 shards already complete (400/600 documents, 66.7%)`、`1 shard(s) remaining`，只计算缺失的那一片。
- ✅ **拒绝不兼容续跑**：`CacheStateError` 已实测三种情形——配置相同→正常续跑；`max_seq_length` 改变→拒绝；manifest 指纹改变→拒绝。
- ✅ **进度查询**：`status` 子命令实跑通过（修掉 shard_size bug 后），未完成时返回退出码 3。

### 1.3 已修掉的 2 个 bug（新机器不要再踩）

1. **`np.save` 会给不以 `.npy` 结尾的路径追加 `.npy`**，导致 `shard_x.npy.tmp` 实际被写成 `shard_x.npy.tmp.npy`，随后 `os.replace` 报 `FileNotFoundError`。
   → 已修：改为 `with open(tmp,"wb") as fh: np.save(fh, ...)`。
2. **DEBUG 级日志把 httpx/huggingface_hub 的每次请求都打出来**，进度日志被完全淹没。
   → 已修：`setup_logging` 默认 INFO，并把 9 个噪音 logger 压到 WARNING。

3. **`status` / `embed` 用 CLI 默认 `shard_size` 而不是缓存实际值，会误判进度甚至谎报 COMPLETE**。
   实测复现：缓存是用 `--shard-size 200` 建的，不带该参数跑 `status` 就用了默认 2000，输出
   `shards complete: 2 / 1`、`documents embedded: 1000 / 600 (166.67%)`、`STATUS: COMPLETE`
   —— 而真实状态是 2/3 完成。**在新机器上这会让人拿着不完整的缓存进入下游阶段。**
   → 已修：新增 `embedder.read_cached_shard_size()`，`status`/`embed`/`benchmark` 都通过
   `_adopt_cached_shard_size()` 以缓存里记录的值为准；显式传入冲突值时打 WARNING。
   同时 `status` 增加了 stale shard 检测，并在未完成时返回**退出码 3**（便于脚本判断）。
   修复后实测输出：`shards complete: 2 / 3`、`400 / 600 (66.67%)`、`STATUS: INCOMPLETE`。

---

## 2. 未完成部分（剩余 8 个模块，全部未开始写）

| 顺序 | 文件 | 对应原始需求 | 状态 |
|---|---|---|---|
| 1 | `config/taxonomy_seed_business.py` | 9 个业务线 L1 的 seed 骨架 | ❌ 未开始（设计已完成，见 `02_DESIGN_NOTES.md`，可直接照抄） |
| 2 | `config/taxonomy_seed_functions.py` | 7~8 个职能类 L1 的 seed 骨架 | ❌ 未开始（同上） |
| 3 | `config/taxonomy_seed.py` | 合并上两者，导出 `SEED_TAXONOMY` | ❌ 未开始 |
| 4 | `bootstrap/anchors.py` | 第1步后半：锚点文本构造 + 锚点 embedding | ❌ 未开始 |
| 5 | `bootstrap/matching.py` | 第2步：L1→L2→L3 逐级匹配 | ❌ 未开始 |
| 6 | `bootstrap/thresholds.py` | 第2步后半：二分 GMM 定阈值 + P30 fallback | ❌ 未开始 |
| 7 | `bootstrap/discovery.py` | 第3步：按父节点分池 + HDBSCAN 缺口发现 | ❌ 未开始 |
| 8 | `bootstrap/naming.py` | 第4步：Ollama 命名 + 7b vs 3b 对比实验 | ❌ 未开始 |
| 9 | `bootstrap/emit.py` | 产出 `taxonomy.py` + `thresholds.json` | ❌ 未开始 |
| 10 | `bootstrap/report.py` | 产出 `bootstrap_report.md` | ❌ 未开始 |
| 11 | `run_bootstrap.py` | 主编排入口 | ❌ 未开始 |

每个模块的详细接口约定见 `03_NEXT_STEPS.md`。

---

## 3. 关键实测数据（新机器决策依据）

### 3.1 语料实况（已确认，与原 prompt 描述差异很大）

原 prompt 说"一批初始文章"，实际是：

```
总计            511,963 个文件 / 2,359.8 MB
其中 .txt       511,962      .jsonl 1 个（questions.jsonl，非语料，已排除）
过滤 <200 字节后可用：511,887 篇

按来源：
  slack         285,605   (55.8%)   平均  3.3 KB
  gmail         121,390   (23.7%)   平均  6.9 KB
  linear         35,308   ( 6.9%)   平均  5.0 KB
  google_drive   25,108   ( 4.9%)   平均  6.9 KB
  hubspot        15,017   ( 2.9%)   平均  3.0 KB
  fireflies      10,173   ( 2.0%)   平均 11.3 KB
  github          8,052   ( 1.6%)   平均  4.6 KB
  jira            6,120   ( 1.2%)   平均  5.4 KB
  confluence      5,189   ( 1.0%)   平均  9.6 KB

文件大小分位：p5=1.8KB  p50=4.3KB  p75=6.4KB  p90=8.0KB  p99=11.9KB
```

**格式（9 个来源全部一致，已逐个抽样验证）**：纯 UTF-8 `.txt`，**第 1 个非空行 = 标题，其余 = 正文**。无 front-matter、无 JSON 包装。
`google_drive` 部分文件正文里含**字面量 `\n` 两字符序列**而非真换行，`corpus.parse_document_text()` 已做归一化。

**文件名内嵌文档 ID**：形如 `dsid_<32位hex>__<slug>.txt`，`corpus._derive_doc_id()` 已提取复用为 `doc_id`（便于和 OKF 管线交叉引用）。

### 3.2 ⚠️ 语料内容与 taxonomy 的严重错配（重要，必须知道）

**语料实际内容不是银行业务文档**。这是一家叫 **Redwood Inference** 的 **AI 推理平台公司**的内部资料：GPU 集群利用率、模型服务运行时、量化配置、KV cache、eval harness、SLO/错误预算、on-call 事故复盘、Kubernetes、OpenAI 兼容 API、SDK……

客户名是虚构的（Cascade Financial Group、Northstar Health Systems、Verity Labs、Atelier Classroom AI 等）。只有极少数文档偶然涉及金融客户的合规诉求。

**后果与应对**：
- 9 个银行业务线 L1（Retail Banking / Payments / Trade Finance / ...）在这批语料上**几乎不会有文章匹配上**，绝大多数文章会落到 `Technology & Engineering`。
- 这**不是 bug**，是语料与需求的客观错配。原 prompt 要求 hardcode 银行骨架，所以**照要求写全**，同时：
  - 把 `Technology & Engineering` 的 L2/L3 展开得足够细（设计稿里已扩展到 9 个 L2、~35 个 L3），否则 40 万篇技术文档全挤在 2 个 L2 下面，L3 匹配分数会一片低、阈值失真。
  - 在 `bootstrap_report.md` 里**明确写出这个错配结论**和各 L1 的文章分布，让阅读报告的人一眼看到。
- 建议额外加一个 seed L1 `Product Management`（语料里 `linear/product-management`、`confluence/product-docs` 量不小），理由与授权见 `02_DESIGN_NOTES.md`。

### 3.3 原机器环境（供对比）

```
OS            Windows / win32 / PowerShell
Python        3.11.9
GPU           Quadro T1000 (4 GB VRAM, Turing TU117, 无 Tensor Core, ~50W)
torch         2.10.0+cu128     cuda_available=True
sentence-transformers  6.0.0
transformers  5.15.1
scikit-learn  1.9.0      ← 自带 sklearn.cluster.HDBSCAN，不需要装 hdbscan 包
scipy         1.17.1
numpy         2.4.4
huggingface_hub 1.28.0
tokenizers    0.22.2
safetensors   0.8.0
sentencepiece 0.2.1
```

**Ollama 本地已有模型**（新机器需确认同样具备）：
```
qwen2.5-coder:7b    4.7 GB   ← 命名主模型
qwen2.5:3b          1.9 GB   ← 对比实验模型（原 prompt 写作 qwen2.5-3b，实际 tag 是 qwen2.5:3b）
qwen3-coder:30b    18 GB
qwen3:8b            5.2 GB
deepseek-r1:7b      4.7 GB
llama2:latest       3.8 GB
```

### 3.4 ⚠️ embedding 吞吐实测（交接的直接原因）

用真实语料实测，非估算：

```
配置：BAAI/bge-m3, cuda, fp16, max_seq_length=512, batch_size=8
样本：400 篇真实文档（2 个 shard × 200）
耗时：705.7 s
吞吐：0.57 docs/s
     shard[0,200)   279.8s  (0.71 docs/s)
     shard[200,400) 425.9s  (0.47 docs/s)
模型加载：7.1 s（权重已在本地 HF 缓存）
```

**外推**：

| 规模 | 预计耗时 @0.57 docs/s |
|---|---|
| 30,000 篇（分层抽样） | 14.7 小时 |
| 50,000 篇 | 24.5 小时 |
| **511,887 篇（全量）** | **251 小时 ≈ 10.5 天** |

**这个数字很可能偏低，未排除配置问题**。粗算 bge-m3（XLM-R-large，24层/hidden 1024，~303M 非 embedding 参数）在 512 token 下约 340 GFLOPs/篇，0.57 docs/s 只有 ~0.19 TFLOPS 有效算力，约为该卡可达算力的 10%。怀疑是 `batch_size=8` 太小喂不满、或 fp16 在无 Tensor Core 的 TU117 上没收益。

→ **`bench_encode.py` 就是为查清这一点写的，但还没跑成（被中断）。新机器务必先跑它。** 换成有 Tensor Core 的卡（RTX 30/40 系、A10、L4 等）后吞吐大概率是数十倍量级的提升，全量方案可能直接变可行。

---

## 4. 悬而未决的决策（需要用户拍板）

**唯一阻塞决策：bootstrap 用全量 511,887 篇，还是分层抽样？**

- 代码两种模式都已支持，**这个决定只影响跑多久，不影响任何代码逻辑**。
- 我的建议：先在新机器上跑 `bench_encode.py` + `benchmark` 拿到真实吞吐，再定。
  - 若新卡吞吐 ≥ 30 docs/s → 全量约 4.7 小时，**直接全量**。
  - 若吞吐仍 < 5 docs/s → 走 30,000 篇分层抽样（Bootstrap 阶段产出的是 taxonomy 补充节点 + 3 个阈值，都是分布统计量，3 万篇的覆盖度足够；且分层抽样保证每个 channel/mailbox/space 都有代表）。
- 无论选哪种，**embedding 都可以中断续跑**，所以全量也可以分多次、跨多天完成。

---

## 5. 交接时的 `work/` 目录状态（建议清空重建）

```
work/manifest.jsonl                    600 行（临时基准测试用的 600 篇抽样，不是正式 manifest）
work/embeddings/state.json             缓存状态
work/embeddings/shard_000000000.npy    200 × 1024 fp16
work/embeddings/shard_000000200.npy    200 × 1024 fp16
work/bootstrap_run.log                 历史运行日志
```

**新机器请先删掉整个 `work/` 目录**（这些是 600 篇临时基准数据，没有复用价值），然后按 `03_NEXT_STEPS.md` 重建正式 manifest。
`__pycache__/` 也一并删掉。
