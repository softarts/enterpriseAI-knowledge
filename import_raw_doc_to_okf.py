#!/usr/bin/env python3
"""
import_raw_doc_to_okf.py

命令行工具：将原始文档（PDF, DOCX, HTML, TXT）转换为 OKF 格式
（Markdown + YAML frontmatter）。

用法:
    python import_raw_doc_to_okf.py --input <文件或目录> [--output <输出目录>] [--config <配置文件>]
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supported file types and extension mapping
# ---------------------------------------------------------------------------
EXTENSION_MAP = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".doc": "docx",
    ".html": "html",
    ".htm": "html",
    ".txt": "text",
    ".md": "text",
    ".rst": "text",
}


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------
def load_config(config_path: str) -> Dict[str, Any]:
    """加载并返回 YAML 配置字典。"""
    path = Path(config_path)
    if not path.exists():
        logger.warning("配置文件不存在: %s，使用默认配置", config_path)
        return get_default_config()

    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    # 合并默认值
    default = get_default_config()
    for key in default:
        if key not in config:
            config[key] = default[key]

    return config


def get_default_config() -> Dict[str, Any]:
    """返回默认配置。"""
    return {
        "metadata": {
            "defaults": {
                "author": "unknown",
                "created_at": "file_timestamp",
                "tags": [],
            }
        },
        "tag_rules": [],
        "output": {
            "format": "yaml",
            "structure": "mirror",
            "base_dir": "./generated",
        },
    }


# ---------------------------------------------------------------------------
# File type detection
# ---------------------------------------------------------------------------
def detect_file_type(file_path: Path) -> Optional[str]:
    """根据文件扩展名检测文件类型。"""
    ext = file_path.suffix.lower()
    return EXTENSION_MAP.get(ext)


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------
def extract_text(file_path: Path, file_type: str) -> str:
    """根据文件类型调用对应的解析器提取文本。"""
    extractors = {
        "pdf": extract_pdf,
        "docx": extract_docx,
        "html": extract_html,
        "text": extract_text_file,
    }

    extractor = extractors.get(file_type)
    if extractor is None:
        raise ValueError(f"不支持的文件类型: {file_type}")

    return extractor(file_path)


def extract_pdf(file_path: Path) -> str:
    """使用 pdfplumber 提取 PDF 文本。"""
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("请安装 pdfplumber: pip install pdfplumber")

    text_parts = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n\n".join(text_parts)


def extract_docx(file_path: Path) -> str:
    """使用 python-docx 提取 Word 文本。"""
    try:
        from docx import Document
    except ImportError:
        raise ImportError("请安装 python-docx: pip install python-docx")

    doc = Document(str(file_path))
    paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
    return "\n\n".join(paragraphs)


def extract_html(file_path: Path) -> str:
    """使用 BeautifulSoup 提取 HTML 正文，去掉样式，保留表格和图片占位符。"""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        raise ImportError("请安装 beautifulsoup4: pip install beautifulsoup4")

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        html_content = f.read()

    soup = BeautifulSoup(html_content, "html.parser")

    # 移除 style, script 标签
    for tag in soup(["style", "script", "link", "meta"]):
        tag.decompose()

    # 将 img 标签替换为占位符
    for img in soup.find_all("img"):
        alt = img.get("alt", "image")
        src = img.get("src", "")
        img.replace_with(f"[图片: {alt}]({src})")

    # 将 table 标签转换为简单文本表示
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            rows.append(" | ".join(cells))
        table_text = "\n".join(rows)
        table.replace_with(f"\n{table_text}\n")

    text = soup.get_text(separator="\n")
    # 清理多余空行
    lines = [line.strip() for line in text.splitlines()]
    cleaned = "\n".join(line for line in lines if line)
    return cleaned


def extract_text_file(file_path: Path) -> str:
    """直接读取纯文本文件。"""
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Metadata & tag building
# ---------------------------------------------------------------------------
def extract_title(text: str, file_path: Path) -> str:
    """从文本提取标题：取第一行非空内容；如果为空则从文件名 slug 提取。"""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            # 去掉 markdown 标题符号
            return stripped.lstrip("# ").strip()

    # Fallback: 从文件名提取
    stem = file_path.stem
    # 处理 dsid_xxx__slug 格式
    if "__" in stem:
        slug = stem.split("__", 1)[1]
    else:
        slug = stem
    return slug.replace("-", " ").replace("_", " ").title()


def apply_tag_rules(file_path: Path, tag_rules: List[Dict]) -> List[str]:
    """根据配置中的路径匹配规则自动打标签。"""
    tags = []
    path_str = str(file_path).replace("\\", "/").lower()

    for rule in tag_rules:
        match_path = rule.get("match_path", "").lower()
        if match_path and match_path in path_str:
            rule_tags = rule.get("tags", [])
            for tag in rule_tags:
                if tag not in tags:
                    tags.append(tag)

    return tags


def get_file_timestamp(file_path: Path) -> str:
    """获取文件修改时间的 ISO 格式字符串。"""
    mtime = os.path.getmtime(file_path)
    dt = datetime.fromtimestamp(mtime)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def build_metadata(
    file_path: Path, text: str, config: Dict[str, Any], input_root: Path
) -> Dict[str, Any]:
    """构建 YAML frontmatter 元数据。"""
    defaults = config.get("metadata", {}).get("defaults", {})
    tag_rules = config.get("tag_rules", [])

    title = extract_title(text, file_path)
    author = defaults.get("author", "unknown")

    # created_at
    created_at_setting = defaults.get("created_at", "file_timestamp")
    if created_at_setting == "file_timestamp":
        created_at = get_file_timestamp(file_path)
    else:
        created_at = created_at_setting

    # Tags: 默认 + 规则匹配
    default_tags = list(defaults.get("tags", []))
    rule_tags = apply_tag_rules(file_path, tag_rules)
    all_tags = default_tags + [t for t in rule_tags if t not in default_tags]

    # source_path: 相对于输入根目录的路径
    try:
        relative_source = file_path.relative_to(input_root)
    except ValueError:
        relative_source = file_path
    source_path = str(relative_source).replace("\\", "/")

    metadata = {
        "title": title,
        "author": author,
        "created_at": created_at,
        "tags": all_tags,
        "source_path": source_path,
    }

    return metadata


# ---------------------------------------------------------------------------
# OKF generation
# ---------------------------------------------------------------------------
def generate_okf(text: str, metadata: Dict[str, Any]) -> str:
    """将文本和元数据拼接为 Markdown + YAML frontmatter 格式。"""
    # 构建 frontmatter
    frontmatter = yaml.dump(
        metadata,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    ).strip()

    # 构建 markdown body
    title = metadata.get("title", "")
    body = text.strip()

    # 如果正文第一行就是标题（和 metadata 中的 title 相同），则加 # 前缀
    lines = body.splitlines()
    if lines and lines[0].strip() == title:
        lines[0] = f"# {title}"
        body = "\n".join(lines)
    else:
        body = f"# {title}\n\n{body}"

    okf_content = f"---\n{frontmatter}\n---\n\n{body}\n"
    return okf_content


# ---------------------------------------------------------------------------
# Output path computation
# ---------------------------------------------------------------------------
def compute_output_path(
    file_path: Path,
    input_root: Path,
    output_dir: Path,
    output_format: str,
    mirror: bool,
) -> Path:
    """
    计算输出文件路径。

    - mirror=True: 保持与源目录相同的层次结构 (默认行为，--output 未指定时)
    - mirror=False: 直接输出到 output_dir 下 (--output 显式指定时)
    """
    if mirror:
        try:
            relative = file_path.relative_to(input_root)
        except ValueError:
            relative = Path(file_path.name)
        out_path = output_dir / relative.with_suffix(f".{output_format}")
    else:
        out_path = output_dir / file_path.with_suffix(f".{output_format}").name

    return out_path


# ---------------------------------------------------------------------------
# Single file conversion
# ---------------------------------------------------------------------------
def convert_file(
    file_path: Path,
    input_root: Path,
    output_dir: Path,
    config: Dict[str, Any],
    mirror: bool,
) -> bool:
    """
    转换单个文件为 OKF 格式。

    返回 True 表示成功, False 表示失败。
    """
    output_format = config.get("output", {}).get("format", "yaml")

    # 检测文件类型
    file_type = detect_file_type(file_path)
    if file_type is None:
        logger.warning("跳过不支持的文件类型: %s", file_path)
        return False

    try:
        # 提取文本
        text = extract_text(file_path, file_type)

        if not text.strip():
            logger.warning("文件内容为空: %s", file_path)
            return False

        # 构建元数据
        metadata = build_metadata(file_path, text, config, input_root)

        # 生成 OKF 内容
        okf_content = generate_okf(text, metadata)

        # 计算输出路径
        out_path = compute_output_path(
            file_path, input_root, output_dir, output_format, mirror
        )

        # 确保输出目录存在
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # 写入文件
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(okf_content)

        logger.info("转换成功: %s -> %s", file_path, out_path)
        return True

    except Exception as e:
        logger.error("转换失败: %s, 错误: %s", file_path, str(e))
        return False


# ---------------------------------------------------------------------------
# Directory traversal
# ---------------------------------------------------------------------------
def collect_files(input_path: Path) -> List[Path]:
    """收集输入路径下的所有支持的文件。"""
    if input_path.is_file():
        return [input_path]

    files = []
    for root, _dirs, filenames in os.walk(input_path):
        for filename in sorted(filenames):
            fp = Path(root) / filename
            if detect_file_type(fp) is not None:
                files.append(fp)

    return files


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="将原始文档转换为 OKF 格式 (Markdown + YAML frontmatter)"
    )
    parser.add_argument(
        "--input",
        required=True,
        help="输入文件或目录路径",
    )
    parser.add_argument(
        "--output",
        required=False,
        default=None,
        help="输出目录路径。未指定时使用配置文件中的 base_dir（默认 ./generated），并保持路径镜像",
    )
    parser.add_argument(
        "--config",
        required=False,
        default="doc_to_okf_config.yaml",
        help="配置文件路径（默认: doc_to_okf_config.yaml）",
    )

    args = parser.parse_args()

    # 加载配置
    config = load_config(args.config)

    # 确定输入路径
    input_path = Path(args.input).resolve()
    if not input_path.exists():
        logger.error("输入路径不存在: %s", input_path)
        sys.exit(1)

    # 确定输入根目录（用于计算相对路径）
    if input_path.is_file():
        input_root = input_path.parent
    else:
        input_root = input_path

    # 确定输出路径和是否镜像
    if args.output is not None:
        # 显式指定了 --output：直接输出到该目录，不做路径镜像
        output_dir = Path(args.output).resolve()
        mirror = False
    else:
        # 未指定 --output：使用配置中的 base_dir，保持路径镜像
        base_dir = config.get("output", {}).get("base_dir", "./generated")
        output_dir = Path(base_dir).resolve()
        mirror = True

    # 收集文件
    files = collect_files(input_path)
    if not files:
        logger.warning("未找到可处理的文件: %s", input_path)
        sys.exit(0)

    logger.info("共发现 %d 个待转换文件", len(files))

    # 转换
    success_count = 0
    fail_count = 0

    for file_path in files:
        result = convert_file(file_path, input_root, output_dir, config, mirror)
        if result:
            success_count += 1
        else:
            fail_count += 1

    # 输出统计
    logger.info("=" * 50)
    logger.info("转换完成！成功: %d, 失败: %d, 总计: %d", success_count, fail_count, len(files))
    logger.info("输出目录: %s", output_dir)

    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
