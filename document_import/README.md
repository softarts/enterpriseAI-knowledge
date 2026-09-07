# document_import

`document_import` 负责把 PDF、DOCX、HTML、TXT、Markdown、RST 等原始文档转换为
OKF（Markdown 正文 + YAML frontmatter）中间文件，也负责解析 OKF。它只负责文档
转换和 OKF 解析，不负责 taxonomy、chunking、embedding 或 ChromaDB。

代码规模：约 736 行（包含迁移的解析与 OKF 生成实现、CLI、Service、注释和 docstring）。

## 转换流程

```text
原始文件 / 文件字节
       │
       ▼
DocumentImportService.convert()
       │
       ├── detect_file_type()         根据扩展名识别类型
       ├── extract_text()             PDF/DOCX/HTML/TXT 解析
       ├── normalize_txt_structure()  文本转 Markdown 结构
       ├── extract_title()            提取文档标题
       ├── build_metadata()           生成 document_id、source、时间、tags
       └── generate_okf()             组合 YAML frontmatter + Markdown body
       │
       ▼
OKF .yaml 文件
```

批量 CLI 流程：

```text
python -m document_import.cli
       │
       ├── 收集输入目录中的文件
       ├── 对每个文件调用 DocumentImportService.convert()
       └── 按目录结构写入输出目录的 .yaml 文件
```

## API 与代码位置

Service API 位于 `document_import/service.py`：

```python
from document_import import DocumentImportService

service = DocumentImportService()
result = service.convert(source_path, output_dir=Path("import_data/okf"))
print(result.okf_content)
```

核心转换函数位于 `document_import/converter.py:convert_path()`；当前实现主体迁移在
`document_import/legacy_converter.py`，根目录 `import_raw_doc_to_okf.py` 仅保留兼容
wrapper。配置加载使用 `doc_to_okf_config.yaml`，不存在时使用内置默认值。

## OKF 解析结果与命令行查看

OKF 解析器位于 `document_import/okf.py:parse_okf_file()`，返回
`document_import.okf.OKFDocument`。它替代了过去通过
`doc_service.repositories.okf_document_repository.OKFDocumentRepository._parse_okf_file()`
获得的 `DocumentRecord`，字段保持兼容，但不再让新的 embedding pipeline 依赖
`doc_service`。`doc_service` 当前仍保留原 repository，后续可逐步改为复用本解析器。

直接打印解析结果：

```bash
python -m document_import.inspect_okf import_data/okf/documents/000/example.yaml
```

输出是 JSON，示例：

```json
{
  "document_id": "example-document",
  "title": "Example Document",
  "author": "unknown",
  "created_at": "2026-09-06T00:00:00",
  "tags": ["policy"],
  "source_path": "policies/example.txt",
  "content": "# Example Document\n\n正文内容...",
  "file_path": "import_data/okf/documents/000/example.yaml",
  "metadata": {
    "document_id": "example-document",
    "title": "Example Document",
    "source_path": "policies/example.txt",
    "source_type": "text"
  }
}
```

字段含义：

| 字段 | 含义 |
|---|---|
| `document_id` | frontmatter 中的稳定 ID；缺失时由文件名生成 |
| `title` | 文档标题 |
| `author` | 作者，缺失时为 `unknown` |
| `created_at` | 创建时间，可为空 |
| `tags` | 文档标签列表 |
| `source_path` | 原始来源路径 |
| `content` | 去掉 frontmatter 后的 Markdown 正文 |
| `file_path` | 当前 OKF 文件的实际路径 |
| `metadata` | 完整 YAML frontmatter，保留其他未建模字段 |

因此，原来的：

```python
record = repo._parse_okf_file(Path(file_path))
```

现在可以写成：

```python
from document_import import parse_okf_file

record = parse_okf_file(Path(file_path))
print(record.document_id, record.title, record.content)
```

CLI：

```bash
python -m document_import.cli --input all_documents --output import_data/okf
```

兼容旧入口：

```bash
python import_raw_doc_to_okf.py --input all_documents --output import_data/okf
```

## Evaluation source manifest

`evaluation_manifest.py` 从 `embedding_service/evaluation/evaluation_queries.json` 提取
唯一的 `expected_source_path`，生成可重复使用的源文件清单。它只负责清单生成和文件
存在性校验；实际导入由 `chat_service.server_import_cli` 创建现有批量任务完成。

```bash
python -m document_import.evaluation_manifest \
  --queries embedding_service/evaluation/evaluation_queries.json \
  --source-root all_documents \
  --output embedding_service/evaluation/evaluation_sources.json
```

## OKF 设计

OKF 将结构化 metadata 与 Markdown 正文放在同一个文件中：

```yaml
---
document_id: example-document
title: Example Document
source_path: policies/example.txt
source_type: text
created_at: '2026-09-06T00:00:00'
tags: []
---

# Example Document

正文内容...
```

使用 OKF 作为中间形态的原因：

- 转换和后续处理解耦，embedding、taxonomy、预览和重新处理都消费同一种输入。
- YAML frontmatter 保留稳定的 document_id、标题、来源、时间和 tags。
- Markdown 保留 heading、段落、列表、表格和代码块等文档结构，便于 Markdown-first
  chunking。
- 文件可读、可审查、可版本控制，转换失败或下游失败时可以单独检查中间结果。
- 后续更换 embedding 模型时无需重新解析 PDF/DOCX，只需重新消费 OKF。

## 与其他服务的边界

```text
document_import
  └── 原始文档 -> OKF

chat_service
  └── 上传 -> OKF -> taxonomy -> embedding pipeline

embedding_service
  └── OKF -> chunk -> embedding -> vector_service
```

默认 chat 导入会把最终 OKF 写到根目录 `import_data/okf`，可通过
`CHAT_IMPORT_ROOT`、`CHAT_IMPORT_STORAGE_DIR` 等配置覆盖。taxonomy 仍由
`kb_classifier` 负责，本模块不修改 taxonomy。
