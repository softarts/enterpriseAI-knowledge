# 原始任务（逐字保存）

> 这是本项目的原始需求 prompt，未做任何改写。后续机器请以此为唯一需求来源。
> 代码放在 `kb_classifier_bootstrap/` 目录（已建立）。

---

# 任务：企业知识库文章分类器 — Bootstrap阶段（一次性全量扫描）

## 背景

这是一个个人练习项目：把一批银行企业内部文章导入知识库前，需要给每篇文章打上一个3级分类（如 `Finance > Payments > Payment Processing`），作为metadata随文档转换为OKF格式后一起入embedding库。

整个系统分两个阶段，**本次任务只做Bootstrap阶段**：

- **阶段A（本次任务）**：拿到一批初始文章，做一次全量扫描，自动生成一份三级分类taxonomy + 每级分类阈值。之后这份taxonomy和阈值会被固定下来，长期复用。
- **阶段B（不在本次任务范围）**：之后每篇文章逐篇导入时，用阶段A产出的taxonomy+阈值做规则化的逐级匹配分类，不再聚类。

**本次任务全程不允许调用云端LLM API，只允许使用本地模型。全程不需要任何人工审核步骤——所有判断（包括新分类的命名）都要由代码自动完成。**

---

## 输入

- `all_documents/` 目录下的一批文章（初始bootstrap批次，具体格式请自行探测：可能是txt/markdown/json等，读取时先扫描目录结构确认格式）
- 每篇文章至少包含标题和正文

---

## 分类体系要求：L1/L2/L3 都要预先hardcode一批锚点

跟之前"只hardcode L1"的方案不同，这次L1/L2/L3都要尽量预先写好合理的锚点骨架，聚类发现只用来补充骨架没覆盖到的地方，而不是L2/L3的主要来源（这样能大幅减少运行时的聚类计算量，也让分类结果更贴近银行实际业务术语，而不是纯数据驱动出来的、命名可能很怪的分类）。

一级分类必须同时覆盖两类内容，且命名要能区分开（避免"Finance"歧义，业务线用具体产品名如`Trade Finance`，职能类用`Corporate Finance & Accounting`）：

### 业务线锚点骨架（请在此基础上用你的银行业务知识补全L2/L3，下面给出的是最低要求，鼓励扩展更细）

```
Retail Banking
├── Deposit Accounts (储蓄/活期账户)
├── Consumer Lending (个人贷款、车贷房贷)
└── Retail Cards (个人信用卡/借记卡)

Corporate Banking
├── Corporate Accounts (企业账户管理)
├── Cash Management Services (企业现金管理服务)
└── Trade Services (企业贸易服务)

Payments
├── Payment Processing (支付处理)
├── Payment Gateway (支付网关)
└── Card Payments (卡组织支付)

Lending
├── Corporate Lending (企业贷款)
└── Credit Assessment (信用评估)

Treasury
├── Cash Management (资金管理)
└── Liquidity Management (流动性管理)

Risk & Compliance
├── Anti-Money Laundering (反洗钱)
├── Regulatory Reporting (监管报送)
└── Credit Risk Management (信用风险管理)

Wealth Management
├── Private Banking (私人银行)
└── Investment Advisory (投资顾问)

Trade Finance
├── Letters of Credit (信用证)
└── Cross-Border Settlement (跨境结算)

Digital Banking
├── Mobile Banking (手机银行)
├── Open Banking APIs (开放银行API)
└── Fintech Partnerships (金融科技合作)
```

### 通用职能锚点骨架（同样请补全L2/L3）

```
Corporate Finance & Accounting
├── Financial Reporting (财务报表)
└── Tax & Treasury Operations (税务与内部资金操作)

Human Resources
├── Recruitment (招聘)
├── Compensation & Benefits (薪酬福利)
└── Employee Relations (员工关系)

Legal
├── Contract Management (合同管理)
└── Corporate Governance (公司治理)

Technology & Engineering
├── Infrastructure & Operations (基础设施与运维)
└── Software Development (软件开发)

Sales & Marketing
├── Brand & Communications (品牌与传播)
└── Customer Acquisition (客户获取)

Procurement & Vendor Management
└── Vendor Contracts (供应商合同)

Facilities & Administration
└── Office Operations (办公运营)
```

请在此骨架基础上，用你自己对银行/企业业务的知识补全和调整（比如某些L2下面可以再细化出更多L3，或者根据bootstrap语料实际内容增删枝节），最终写入`config/taxonomy.py`。每个节点都要有`desc`（一句话语义描述，不是标签词）。

---

## 技术方案：锚点优先匹配 + 缺口发现（聚类只用于补充）

### 第1步：全量Embedding
- 使用本地模型 `BAAI/bge-m3`（通过 `sentence-transformers` 加载），对所有bootstrap文章的（标题+正文前若干字，具体截断长度按模型max_seq_length调整）做embedding
- 同时对taxonomy骨架里所有节点（L1/L2/L3）的desc文本做embedding

### 第2步：逐级锚点匹配
- 每篇文章先在L1锚点里找最高相似度，再在选中L1下的L2锚点里找最高相似度，再到L3，形成一条完整路径和每级的分数
- 收集每一级的"最高分"分布，用二分GMM拟合，两个高斯分布均值中点作为该级threshold（单峰情况用P30分位数fallback，并在日志里注明）

### 第3步：缺口发现（聚类只在这里用，且只处理"分不进现有骨架"的文章）
- 对某一级匹配分数低于该级threshold的文章，收集到该级的"未分配池"（未分配池是按父节点分别维护的，比如"L1=Payments但L2分不进去"的文章，只在Payments这个L1下面找L2缺口，不会跟别的L1未分配的文章混在一起）
- 对每个未分配池（如果文章数≥5，太少则不聚类，直接标记UNKNOWN待后续处理），跑HDBSCAN（`min_cluster_size`可设为5，具体按池大小调整）
- 每个新发现的cluster用本地小模型命名（见第4步），作为新节点插入taxonomy对应位置（比如在Payments下新增一个之前没想到的L2子类）
- 这一步产生的新节点在`taxonomy.py`里用 `"source": "discovered"` 标注，跟骨架里手写的 `"source": "seed"` 区分开，方便之后追溯

### 第4步：本地小模型命名新发现的cluster

**模型选择：优先用 `qwen2.5-coder:7b`（通过本地Ollama调用）**，理由：虽然是代码特化模型，但基于Qwen2.5 base做代码增强训练，通用语言能力没有被阉割，7B参数量在"读几个标题总结出一个业务分类名"这种轻量文本理解任务上通常优于3B通用模型（`qwen2.5-3b`），参数量的影响一般比"是否代码特化"更大。

**但请先做一个小对比实验**：挑bootstrap过程中发现的3-5个cluster，分别用`qwen2.5-coder:7b`和`qwen2.5-3b`各跑一次命名prompt，把两组结果都打印到日志里，供事后人工快速扫一眼对比效果（这不算"人工介入分类流程"，只是一次性的模型选型验证，跑完之后固定选一个用于所有cluster的命名，不需要每次都跑两个模型）。

**为什么不能用bge-m3做命名**：bge-m3是纯embedding（encoder）模型，只能把文本映射成向量用于相似度计算，模型结构里没有decoder/生成文本的能力，无法完成"总结几个标题起一个新名字"这种生成式任务。bge-m3在这一步的角色是帮你找出每个cluster里离质心最近的几篇代表性文章（相似度计算，是它的本行），然后把这几篇的标题喂给Qwen做命名——两个模型分工不同。

- 对每个待命名的cluster，用bge-m3计算cluster质心，取离质心最近的5篇文章标题（正文不长可以带前100字），拼成prompt，要求模型输出一个简洁的分类名（建议英文，跟其他节点命名风格一致）+ 一句话desc
- 命名结果直接写入taxonomy结构，不做人工review

---

## 输出产物

1. **`config/taxonomy.py`** — 最终三级分类树，格式如下：
```python
TAXONOMY = {
    "node_key": {
        "name": "Display Name",
        "desc": "一句话语义描述",
        "source": "seed" | "discovered",
        "children": { ... }
    },
    ...
}
```

2. **`config/thresholds.json`** — 每级阈值：
```json
{
  "L1": 0.42,
  "L2": 0.38,
  "L3": 0.33,
  "method_used": {"L1": "gmm", "L2": "gmm", "L3": "p30_fallback"}
}
```

3. **`bootstrap_report.md`** — 简要报告，包含：
   - 参与bootstrap的文章总数
   - 最终taxonomy里各级节点数量（seed保留了多少、discovered新增了多少，按L1/L2/L3分别统计）
   - 每个discovered节点的命名 + 归属的cluster文章数
   - qwen2.5-coder:7b vs qwen2.5-3b 命名对比实验的结果样例
   - 各级未能归类（最终标记UNKNOWN）的文章数量和占比

---

## 注意事项

- 全程本地模型，不调用云端LLM API
- 不设人工审核步骤，所有判断自动完成，即使分类结果不够完美也可以接受
- 请在关键决策点（阈值选择方法、cluster数量、每级最小样本数等超参数）打印清晰的日志，方便事后追溯这次bootstrap具体是怎么跑出这个taxonomy的
- 如果发现某个环节的技术选型或超参数设置存在明显更优的替代方案，可以在代码注释里说明并采用，但不要偏离本文档描述的整体方法论（锚点优先匹配 + 缺口聚类发现 + GMM阈值 + 本地小模型命名）

本任务代码放在一个新建目录 kb_classifier_bootstrap 里面

---

## 追加的对话约束（原机器上补充的要求）

1. **embedding 进度必须能落盘、中断后可重启续跑** —— 已实现，见 `bootstrap/embedder.py`。
2. **是否做分层抽样由用户决定** —— 尚未决定，等实测数据出来后由用户拍板。已实现 `--max-docs` 开关，两种模式都支持。
