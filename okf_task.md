Task 1：重新定义 OKF 最小规范
先写一个：
docs/okf_spec.md
明确规定：
Document
├── YAML Frontmatter
└── Markdown Body
Frontmatter 只放客观、来源明确的 metadata：
document_id:
title:
author:
created_at:
updated_at:
source_path:
source_type:
明确规定：
NO domain
NO topic
NO audience
NO semantic tags
NO LLM-generated metadata
Task 2：定义结构保留规则
明确规定 importer 必须尽量保留：
Heading
Heading hierarchy
Paragraph
Ordered list
Unordered list
Table
Code block
Quote
Hyperlink
Image
Image caption
例如：
Word Heading 1
      ↓
# Heading

Word Heading 2
      ↓
## Heading

Word Table
      ↓
Markdown Table

Word Image
      ↓
assets/image-xxx.png
Task 3：增加 Document Package
不要让 OKF 只是一个 .md 文件。
建议：
generated/
└── document-id/
    ├── document.md
    └── assets/
        ├── image-001.png
        └── image-002.png
这样后面无论：
OCR
Vision
Embedding
API
MCP
都能拿到完整 document package。
Task 4：建立 Golden Test Documents
不要只测试现在这一个 procurement 文档。
至少准备：
test-documents/
├── simple.txt
├── structured.md
├── document.docx
├── document.html
├── document-with-table.docx
├── document-with-image.docx
└── document-with-table-and-image.pdf
重点不是数量，而是覆盖结构类型。
Task 5：定义转换验收标准
例如：
Text:
  内容不能丢失

Heading:
  层级必须保留

Table:
  行列关系必须保留

Image:
  图片文件必须保留

Code:
  内容必须保留

Metadata:
  来源信息必须保留

Semantic metadata:
  OKF 不生成
7. 完成这个 Task 后，再进入真正有价值的下一层
整个系统就会变成：
                 ┌──────────────┐
PDF ────────────>│              │
DOCX ───────────>│  OKF Import  │
HTML ───────────>│              │
TXT ────────────>│              │
                 └──────┬───────┘
                        │
                        v
                 ┌──────────────┐
                 │     OKF      │
                 │              │
                 │ Canonical    │
                 │ Structured   │
                 │ Loss-minimal │
                 └──────┬───────┘
                        │
                        v
              ┌─────────────────────┐
              │ Knowledge Processing│
              ├─────────────────────┤
              │ Keyword Search      │
              │ Full-text Search    │
              │ Vector Search       │
              │ Metadata            │
              │ OCR / Vision        │
              │ Reranking           │
              └──────────┬──────────┘
                         │
                         v
                    Search / RAG
                         │
                         v
                        MCP
                         │
                         v
                       Agent
所以我建议你的下一阶段不是“让 OKF 更聪明”，而是“让 OKF 更可靠”。
先把 OKF Spec + Structure Preservation + Image/Table Handling + Golden Tests 做完。
完成后，你才真正拥有一个稳定的 Canonical Layer。之后无论你面对 PDF、合同、技术文档、会议纪要、Confluence 页面还是完全不同类型的企业文档，下面的检索/索引层都不需要重新依赖某一种文档格式。