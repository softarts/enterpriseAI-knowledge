# 文档分类问题与方案总结

我们先确定了一点：不能再把 Confluence、SharePoint 或 File System 的目录路径直接当成 Knowledge Taxonomy。

例如：

```text
confluence/
  finance/
    budget/
```

这个目录结构只能说明文档来自哪里、存在哪里，并不能说明企业真正的知识分类。

所以应该把 `Source` 和 `Knowledge Taxonomy` 分开。

例如那篇 Payment Gateway 文章：

```text
Source: Medium

Knowledge Taxonomy:
Finance → Payments → Payment Gateway & Card Payment Processing
```

## 1. Template / 人工分类

一种比较直接的方法，是让 Architect、Business Analyst 按照统一的 Template 创建知识。

Template 里面本身就包含 `Domain`、`Category`、`Subcategory` 等分类字段。

例如：

```text
Finance
  → Payments
    → Payment Gateway & Card Payment Processing
```

这种方式的优点是分类从知识产生的时候就已经结构化了，而且准确性通常比较容易控制。

但是它比较依赖人工，而且对于已经存在的大量历史文档并不好处理。

## 2. Rule-based Classification

另一种方法是通过关键词、metadata 或其他 pattern 做规则分类。

例如：

```text
"payment gateway" → Payments
"loan" → Lending
"AML" → Financial Crime
```

但我们后来特别讨论到一个问题：现实中的企业知识未必存在稳定的 pattern。

所以 Rule-based 可以作为辅助机制，但不应该假设它能够解决整个分类问题。

## 3. LLM Classification

LLM 可以直接阅读文档，然后根据预先定义好的 taxonomy 判断它属于哪个类别。

例如：

```text
Document
  ↓
LLM
  ↓
Finance → Payments → Payment Gateway & Card Payment Processing
```

它的优势是灵活，对复杂文档也比较容易处理。

但问题是需要消耗 LLM API，因此对于当前这个项目，我不希望把它作为默认方案，更适合拿来做实验、benchmark，或者处理 classifier 无法判断的文档。

## 4. TF-IDF + Traditional Classifier

如果我们已经有一批带有 taxonomy label 的文档，就可以把问题转换成一个标准的 supervised classification 问题：

```text
Document → Taxonomy Label
```

例如：

```text
Document A → Finance / Payments
Document B → Finance / Lending
Document C → Technology / Infrastructure
```

一个很适合实验的方案是：

```text
TF-IDF → Logistic Regression
```

或者：

```text
TF-IDF → Linear SVM
```

这个方案不需要 LLM API，也不需要自己训练复杂的深度学习模型，而且可以直接使用 Accuracy、Precision、Recall、F1 等指标评估。

对于目前这个项目，我认为它非常值得尝试。

## 5. Embedding-based Classification

另外一个很自然的实验，是直接利用目前已经实现的 embedding。

把 document 转成 vector，然后和已经定义好的 taxonomy/class examples 做 similarity comparison，看看哪个 category 最接近。

```text
Document
   ↓
Embedding
   ↓
Similarity
   ↓
Taxonomy Category
```

这样可以把目前项目中的 embedding、Chroma 和 classification 联系起来。

同时也可以很好地和 TF-IDF classifier 做对比。

## 6. AWS Comprehend / BlazingText / Managed Services

我们还讨论到了 AWS Comprehend、BlazingText 这类成熟的 NLP/ML 服务。

这代表另一种企业实际可能采用的路线：不自己 build classifier，而是直接使用成熟的 vendor / managed service。

这其实和 Enterprise Knowledge Management 的实际场景比较吻合。

不过对于目前这个项目，没有必要马上把这些服务全部接进来，更适合作为后续实验。

## 7. 对当前项目比较合适的实验方向

因为这个项目的目标并不是现在就做出一个 production-ready 的 Knowledge RAG，而是尽可能通过实际实现去学习 Enterprise AI 中不同的技术，所以分类本身可以作为一个很好的实验场。

可以先准备一批带三级 taxonomy label 的文档，然后分别尝试：

```text
TF-IDF + Logistic Regression / Linear SVM
Embedding-based Classification
LLM Classification
```

最后比较它们的效果、成本和工程复杂度。

这样比直接选择一种方案然后不断优化，更符合这个项目目前的目标。

## 8. Payment Gateway 这篇文章作为测试样本

Payment Gateway 这篇文章其实很适合用来测试 classification。

它同时包含很多不同类型的概念，例如：

```text
Payments
PCI DSS
3D Secure
Kafka
NoSQL
JWT
Distributed Systems
```

因此它可以很好地测试 classifier 到底是在识别“文章主题”，还是仅仅在识别某些关键词。

例如，如果 Enterprise Taxonomy 是按照业务领域设计的，那么即使文章里面出现大量 Kafka、NoSQL、SSL、JWT，它的核心分类仍然应该更接近：

```text
Finance
  → Payments
    → Payment Gateway & Card Payment Processing
```

而不是：

```text
Technology
  → Infrastructure
    → Distributed Systems
```

## 9. 最终思路

所以我们现在并不是在寻找一个“最正确”的 document classification 算法。

更合适的方式是把它变成一个实验：

```text
Document
    ↓
Classification
    ↓
Domain
    ↓
Category
    ↓
Subcategory
```

然后分别用不同技术实现这个 Classification。

这样既能解决 Knowledge Base 中实际存在的分类问题，又能通过这个项目实际体验 TF-IDF、传统 classifier、Embedding、LLM classifier 以及后续的 managed service，而不是一开始就把精力花在设计一个非常复杂的 production classification framework 上。