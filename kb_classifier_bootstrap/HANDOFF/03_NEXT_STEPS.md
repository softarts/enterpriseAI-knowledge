# 新机器上的操作步骤

按顺序执行。前 4 步是环境与决策，第 5 步起是写代码。

---

## 步骤 0：环境准备

```powershell
# 依赖（sklearn 1.9 自带 HDBSCAN，不要装 hdbscan 包）
pip install "sentence-transformers>=5.0" "scikit-learn>=1.3" numpy scipy requests

# torch 按新机器的 CUDA 版本装，例如 cu128：
# pip install torch --index-url https://download.pytorch.org/whl/cu128

# 预拉 bge-m3（约 2.3 GB）
python kb_classifier_bootstrap\download_model.py

# Ollama 需具备这两个模型
ollama pull qwen2.5-coder:7b
ollama pull qwen2.5:3b
ollama list
```

清掉原机器的临时产物：

```powershell
Remove-Item -Recurse -Force kb_classifier_bootstrap\work
Get-ChildItem -Path kb_classifier_bootstrap -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
```

---

## 步骤 1：先测吞吐，别急着跑全量

```powershell
# 先建一个小 manifest 给基准测试用
python -m kb_classifier_bootstrap.run_embed manifest --max-docs 600 --shard-size 200 --force
# 语料扫描约 3~4 分钟（51 万个文件）

# 微基准：扫 batch_size × seq_len × fp16 组合，找最优操作点
python kb_classifier_bootstrap\bench_encode.py
```

`bench_encode.py` 会打印每个组合的 docs/s 和峰值显存。**记下最快的 batch_size**。
原机器 `batch_size=8` 只跑出 0.57 docs/s，怀疑喂不满 GPU；显存够的话优先试 32 / 64。

然后做端到端基准：

```powershell
python -m kb_classifier_bootstrap.run_embed benchmark --shards 2 --shard-size 200 --batch-size 32
```

它会直接打印 600 / 30,000 / 50,000 / 511,963 四档规模的预计耗时。

---

## 步骤 2：定规模（唯一需要用户拍板的事）

依据步骤 1 的实测吞吐：

| 实测吞吐 | 建议 |
|---|---|
| ≥ 30 docs/s | 全量 511,887 篇（≤ 4.7 h），直接全量 |
| 5 ~ 30 docs/s | 全量需 4.7~28 h。可全量（分多次续跑），或 5 万篇抽样 |
| < 5 docs/s | 走 30,000 篇分层抽样 |

定好后重建正式 manifest（**这一步会让步骤 1 的临时 shard 失效，正常**）：

```powershell
Remove-Item -Recurse -Force kb_classifier_bootstrap\work

# 全量：
python -m kb_classifier_bootstrap.run_embed manifest --force

# 或分层抽样 3 万篇：
python -m kb_classifier_bootstrap.run_embed manifest --max-docs 30000 --force
```

也可以直接改 `config/settings.py` 里的 `CorpusSettings.max_docs` 固化下来。

---

## 步骤 3：跑 embedding（可中断续跑）

```powershell
# 一直跑到完成
python -m kb_classifier_bootstrap.run_embed embed --batch-size 32

# 或者今天只跑 2 小时，明天接着跑同一条命令
python -m kb_classifier_bootstrap.run_embed embed --batch-size 32 --time-budget-min 120

# 随时查进度（不加载模型，秒出）
python -m kb_classifier_bootstrap.run_embed status
```

**Ctrl-C 是安全的**：已完成的 shard 已落盘，半个 shard 会被丢弃重算。重跑同一条命令即续跑。

⚠️ 续跑时 `--batch-size` / `--device` 可以改（不影响结果），但 **`--shard-size` 不能改**，改了会触发 `CacheStateError`（因为它进了 embedding 指纹）。

---

## 步骤 4：验证 embedding 缓存完好

```powershell
python -m kb_classifier_bootstrap.run_embed status   # 应显示 STATUS: COMPLETE
```

---

## 步骤 5～12：写剩下的 8 个模块

按依赖顺序，每写完一个就用小 manifest（600 篇）冒烟测一遍，别攒到最后一起调。

### 步骤 5：seed taxonomy（3 个文件）
照抄 `02_DESIGN_NOTES.md` §B 的完整树，逐节点补 `desc`。
- `config/taxonomy_seed_business.py` → `BUSINESS_SEED`
- `config/taxonomy_seed_functions.py` → `FUNCTION_SEED`
- `config/taxonomy_seed.py` → `SEED_TAXONOMY` + 一个校验函数（查 key 唯一、层级深度恰为 3、每个节点都有非空 desc）

自检：
```powershell
python -c "from kb_classifier_bootstrap.config.taxonomy_seed import SEED_TAXONOMY as T; import json; print(len(T)); print(sum(len(v['children']) for v in T.values()))"
```

### 步骤 6：`bootstrap/anchors.py`
展平 taxonomy → `Anchor` 列表；锚点文本 = `"面包屑: desc"`；embed 后缓存到 `work/anchor_embeddings.npz`（锚点只有 ~245 个，秒级，但缓存能让下游反复迭代时免加载模型）。

### 步骤 7：`bootstrap/matching.py`
逐级 argmax。**必须分批**（每批 5 万篇文档），不要构造 `[511887 × 245]` 之外更大的中间矩阵。
按 L1 分组后再算 L2，可以只对该 L1 的子锚点做点积，省算力。
结果存 `work/match_results.npz`。

### 步骤 8：`bootstrap/thresholds.py`
对 L1/L2/L3 各自的最高分分布拟合二分 GMM；按 `02_DESIGN_NOTES.md` §A 的双判据决定是否 fallback 到 P30。
日志必须打印：样本数、两个分量的均值/权重/标准差、间隔值、最终方法、最终阈值。

### 步骤 9：`bootstrap/discovery.py`
按 `(level, parent_key)` 建未分配池 → 池 <5 篇标 UNKNOWN 不聚类 → 其余跑 `sklearn.cluster.HDBSCAN` → 每父节点最多留 8 个最大 cluster → 用 bge-m3 向量算质心、取最近 5 篇代表。
日志必须打印每个池的大小、用的 `min_cluster_size`、产出 cluster 数、噪声点数。

### 步骤 10：`bootstrap/naming.py`
`POST {ollama_host}/api/generate`，`stream=false`、`format="json"`、`temperature=0.1`。
先跑 **7b vs 3b 对比实验**（4 个 cluster，两个模型各跑一次，两组结果都打日志并存进报告），之后统一用 `qwen2.5-coder:7b`。
结果缓存到 `work/naming_cache.json`，避免调参重跑时反复调用 LLM。

### 步骤 11：`bootstrap/emit.py` + `bootstrap/report.py`
生成三个产出物。`taxonomy.py` 必须是**能直接 import 的合法 Python**，写完后务必：
```powershell
python -c "from kb_classifier_bootstrap.config.taxonomy import TAXONOMY; print(len(TAXONOMY))"
```
报告必须覆盖原 prompt 要求的 5 项，外加 `01_STATUS.md` §3.2 的语料错配结论和各 L1 文章分布。

### 步骤 12：`run_bootstrap.py`
串起「加载 manifest → 加载 embedding 缓存 → 锚点 → 匹配 → 阈值 → 缺口发现 → 命名 → 产出」。
支持 `--skip-embed`（默认，假定 embedding 已完成）、`--stage` 单跑某阶段、`--dry-run`。
启动时打印 `SETTINGS.describe()` 全量超参。

---

## 最终验收清单

- [ ] `config/taxonomy.py` 存在，可 import，含 `source: "seed"` 与 `source: "discovered"` 两类节点
- [ ] `config/thresholds.json` 存在，含 `L1`/`L2`/`L3` 与 `method_used`
- [ ] `bootstrap_report.md` 存在，含全部 5 项要求内容
- [ ] 全程无云端 LLM 调用（只有 bge-m3 本地推理 + 本地 Ollama）
- [ ] 无人工审核环节
- [ ] 日志里能查到所有超参与阈值决策过程
- [ ] 7b vs 3b 对比实验结果已记入报告
