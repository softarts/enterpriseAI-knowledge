# 交接包索引

企业知识库文章分类器 — Bootstrap 阶段（阶段 A）。
原机器因 GPU 过慢（Quadro T1000，实测 0.57 docs/s，全量需 251 小时）中止，转交新机器继续。

**完成度约 35%。三个最终产出物均未生成。**

## 读这些文件（按顺序）

| 文件 | 内容 |
|---|---|
| `00_ORIGINAL_TASK.md` | **原始需求 prompt，逐字保存**。唯一需求来源 |
| `01_STATUS.md` | 进度报告：已完成/未完成清单、实测数据、语料实况、已修的 bug、待决策项 |
| `02_DESIGN_NOTES.md` | 已确定的技术决策及理由 + **完整 seed taxonomy 设计稿（17 L1 / 56 L2 / 172 L3，可直接照抄）** + 待写模块接口约定 |
| `03_NEXT_STEPS.md` | **新机器上的分步操作指令**，从环境准备到最终验收清单 |
| `../_scan.txt` | 语料扫描原始输出（各来源统计 + 9 个来源的样本文件内容） |

## 三句话现状

1. **能跑的**：语料扫描、分层抽样、manifest 冻结、bge-b3 加载、**可中断续跑的分片式 embedding**（本次核心成果，已实跑验证）。
2. **没写的**：seed taxonomy 本体、锚点、逐级匹配、GMM 阈值、HDBSCAN 缺口发现、Ollama 命名、三个产出物的生成、主编排入口 —— 共 11 个文件。
3. **待拍板的**：bootstrap 用全量 511,887 篇还是分层抽样。代码两种都支持，先在新机器上测吞吐再定，见 `03_NEXT_STEPS.md` 步骤 1~2。

## 新机器最先做的三件事

```powershell
# 1. 清掉原机器的临时产物（那 600 篇基准数据没有复用价值）
Remove-Item -Recurse -Force kb_classifier_bootstrap\work
Get-ChildItem kb_classifier_bootstrap -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force

# 2. 装依赖 + 拉模型
pip install -r kb_classifier_bootstrap\requirements.txt
python kb_classifier_bootstrap\download_model.py
ollama pull qwen2.5-coder:7b; ollama pull qwen2.5:3b

# 3. 测吞吐，拿到真实 docs/s 后再决定跑多大规模
python -m kb_classifier_bootstrap.run_embed manifest --max-docs 600 --shard-size 200 --force
python kb_classifier_bootstrap\bench_encode.py
```

## 一个必须知道的坑

语料**不是银行文档**，是一家 AI 推理平台公司（Redwood Inference）的内部资料。原 prompt 要求的 9 个银行业务线 L1 在这批语料上几乎不会有文章命中，绝大多数会落到 `Technology & Engineering`。这不是 bug，是语料与需求的客观错配。应对方式见 `01_STATUS.md` §3.2。
