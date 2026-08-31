# Open Knowledge Format (OKF) Specification

**Version:** 1.0  
**Status:** Canonical Draft  
**Scope:** Document Ingestion & Intermediate Canonical Representation

---

## 1. Purpose of OKF

Open Knowledge Format (OKF) is the **canonical, loss-minimized, structured document format** for the Enterprise AI Knowledge Base.

When raw enterprise documents (TXT, Markdown, PDF, DOCX, HTML) enter the system, they are converted into OKF files before undergoing downstream processing (such as indexing, search, chunking, and enrichment).

### Key Design Principles:
1. **Fidelity & Loss Minimization:** Preserve original document content without summarization, omission, translation, or semantic mutation.
2. **Structural Clarity:** Represent document hierarchy, sections, paragraphs, lists, tables, and code blocks in standard GitHub Flavored Markdown (GFM).
3. **Deterministic Metadata:** Include only objective, source-verifiable provenance metadata in the YAML frontmatter.
4. **Enrichment-Free Ingestion:** OKF ingestion strictly avoids generating synthetic, speculative, or LLM-derived semantic metadata (such as topics, summaries, concepts, audience tags, or domain classifications). Semantic enrichment is decoupled and handled in subsequent pipeline stages.

---

## 2. File Structure

An OKF document consists of two distinct parts separated by standard YAML frontmatter delimiters:

```markdown
---
document_id: security-account-policy
title: 企业账号管理制度
author: IT Department
created_at: '2026-08-01T10:00:00'
updated_at: '2026-08-01T10:00:00'
source_path: security/account_policy.txt
source_type: text
tags:
  - security
---

# 企业账号管理制度

## 1. 总则

企业信息系统账号必须按照统一规范进行管理。所有员工必须使用企业分配的唯一账号。

## 2. 离职账号管理

员工离职后，应在3个工作日内关闭相关账号。部门主管负责提交账号注销申请。
```

---

## 3. YAML Frontmatter Specification

The frontmatter is defined as a YAML mapping enclosed by triple dashes (`---`). It contains only objective provenance and structural metadata.

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `document_id` | `string` | **Yes** | Deterministic, lowercase, hyphen-delimited document identifier derived from document path/identity (e.g. `security-account-policy`). |
| `title` | `string` | **Yes** | Document title extracted reliably from the document or derived from file name. |
| `author` | `string` | **Yes** | Author or creator organization. Defaults to `"unknown"` if not specified. |
| `created_at` | `string` | **Yes** | ISO 8601 creation timestamp (`YYYY-MM-DDTHH:MM:SS`). |
| `updated_at` | `string` \| `null` | **Yes** | ISO 8601 last modification timestamp, or `null` if not recorded. |
| `source_path` | `string` | **Yes** | Relative path to the original source file. |
| `source_type` | `string` | **Yes** | Source format type: `text`, `pdf`, `docx`, `html`, etc. |
| `tags` | `array[string]` | No | List of categorical tags (retained for backward compatibility with path rules; **not** a semantic enrichment field). |

### Strict Boundary on Frontmatter
The OKF ingestion process MUST NOT fabricate or infer:
- `domain`
- `topic`
- `audience`
- `concept`
- `semantic_tags`
- `summary`
- `entities`
- `llm_generated_*`

---

## 4. Markdown Body Specification

The body of the OKF file contains the structured text content in standard Markdown.

### 4.1 Document Title and Headings
- The document body starts with a Level 1 Heading (`# <Document Title>`).
- Subsections are mapped hierarchically:
  - Level 2: `## Section`
  - Level 3: `### Subsection`
  - Level 4: `#### Sub-subsection`
- **Rule on Ambiguity:** If a line cannot be deterministically and reliably identified as a heading, it MUST be preserved as normal paragraph text rather than guessed as a heading.

### 4.2 Paragraphs
- Normal narrative text is formatted into paragraphs separated by double newlines (`\n\n`).
- Original text content, spelling, punctuation, and terms must not be altered.

### 4.3 Lists
- **Unordered lists:** Preserved using `- `, `* `, or `+ `.
- **Ordered lists:** Preserved using `1. `, `2. `, etc., retaining original numbering.
- Nested sub-items retain their indentation hierarchy.

### 4.4 Tables
- Tabular data is formatted as standard Markdown pipe tables:
  ```markdown
  | Header 1 | Header 2 | Header 3 |
  | :--- | :--- | :--- |
  | Cell A1 | Cell A2 | Cell A3 |
  | Cell B1 | Cell B2 | Cell B3 |
  ```
- Cell contents and tabular alignments are preserved without loss.

### 4.5 Code Blocks
- Preformatted code and command blocks are enclosed in fenced code blocks (```` ``` ````).
- Language identifiers (e.g. ```` ```python ````, ```` ```bash ````) are preserved when present.
- Indentation, special characters, and newlines within code blocks are kept exact.

### 4.6 Links & Inline Formatting
- Hyperlinks: `[Link text](https://example.com)`
- Inline formatting: Bold (`**bold**`), Italics (`*italic*`), Inline code (`` `code` ``).
- Blockquotes: `> Quoted text`

---

## 5. TXT -> OKF Conversion Rules

For plain text and markdown-formatted text inputs:

1. **Title Extraction:** Extracted from the first non-empty heading line (`# Title`) or title line. If missing, derived from the file stem.
2. **Heading Standardization:**
   - Markdown `#`, `##`, `###` headings are preserved.
   - Setext headings (`Title\n===`, `Subtitle\n---`) are normalized to `# Title` and `## Subtitle`.
   - Clear numbered section titles (e.g. `1. Overview`, `1.1 Details`, `第1章 概述`) on their own line are recognized when unambiguous.
   - Ambiguous lines remain standard paragraph text.
3. **Content Preservation:** Original wording, casing, numbers, symbols, and formatting remain 100% intact.
4. **Deterministic Identity:** `document_id` is computed using the canonical slug algorithm to maintain seamless interoperability with the Search API, Document Service, and MCP tools.
