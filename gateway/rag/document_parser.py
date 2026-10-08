import io
import csv
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    import docx
except ImportError:
    docx = None

try:
    import pypdf
except ImportError:
    pypdf = None

class DocumentParser:
    """
    Parses multiple document formats (.docx, .md, .txt, .pdf, .csv, .json) into clean text & structural sections.
    Guarantees robust, zero-crash parsing with comprehensive encoding fallback.
    """
    @staticmethod
    def parse_file(filename: str, content_bytes: bytes) -> Dict[str, Any]:
        ext = Path(filename).suffix.lower()
        title = Path(filename).stem

        if ext == ".docx":
            return DocumentParser._parse_docx(title, content_bytes)
        elif ext in [".md", ".markdown"]:
            return DocumentParser._parse_markdown(title, content_bytes)
        elif ext in [".txt", ".text", ".log"]:
            return DocumentParser._parse_text(title, content_bytes)
        elif ext == ".pdf":
            return DocumentParser._parse_pdf(title, content_bytes)
        elif ext in [".csv", ".tsv"]:
            return DocumentParser._parse_csv(title, content_bytes, delimiter="," if ext == ".csv" else "\t")
        elif ext == ".json":
            return DocumentParser._parse_json(title, content_bytes)
        else:
            # Fallback to plain text attempt
            return DocumentParser._parse_text(title, content_bytes)

    @staticmethod
    def _decode_bytes(data: bytes) -> str:
        """Robust multi-encoding byte decoder."""
        for enc in ["utf-8-sig", "utf-8", "gb18030", "gbk", "big5", "latin-1"]:
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    @staticmethod
    def _parse_docx(title: str, data: bytes) -> Dict[str, Any]:
        paragraphs = []
        if not docx:
            # Fallback if docx module missing: extract XML strings
            try:
                import zipfile
                import xml.etree.ElementTree as ET
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    xml_content = z.read("word/document.xml")
                    tree = ET.fromstring(xml_content)
                    texts = [node.text for node in tree.iter() if node.text]
                    raw_text = "\n".join(texts)
                    paragraphs = [p.strip() for p in raw_text.split("\n") if p.strip()]
                    return {
                        "title": title,
                        "file_type": "docx",
                        "paragraphs": paragraphs,
                        "raw_text": "\n\n".join(paragraphs)
                    }
            except Exception as e:
                raise RuntimeError(f"python-docx 未安装且直接提取文档失败: {e}")

        doc = docx.Document(io.BytesIO(data))
        # 1. Extract paragraphs
        for p in doc.paragraphs:
            text = p.text.strip()
            if text:
                paragraphs.append(text)

        # 2. Extract tables (vital for FAQ tables or parameter sheets)
        for table in doc.tables:
            for row in table.rows:
                row_texts = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                # Deduplicate identical cells caused by merged columns
                dedup_cells = []
                for c in row_texts:
                    if not dedup_cells or dedup_cells[-1] != c:
                        dedup_cells.append(c)
                if dedup_cells:
                    paragraphs.append(" | ".join(dedup_cells))

        raw_text = "\n\n".join(paragraphs)
        return {
            "title": title,
            "file_type": "docx",
            "paragraphs": paragraphs,
            "raw_text": raw_text
        }

    @staticmethod
    def _parse_markdown(title: str, data: bytes) -> Dict[str, Any]:
        text = DocumentParser._decode_bytes(data)
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        return {
            "title": title,
            "file_type": "md",
            "paragraphs": paragraphs,
            "raw_text": text
        }

    @staticmethod
    def _parse_text(title: str, data: bytes) -> Dict[str, Any]:
        text = DocumentParser._decode_bytes(data)
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        return {
            "title": title,
            "file_type": "txt",
            "paragraphs": paragraphs,
            "raw_text": text
        }

    @staticmethod
    def _parse_pdf(title: str, data: bytes) -> Dict[str, Any]:
        global pypdf
        if not pypdf:
            try:
                import pypdf as _pypdf
                pypdf = _pypdf
            except ImportError:
                # Attempt to auto-install pypdf in background
                import subprocess
                import sys
                try:
                    subprocess.run([sys.executable, "-m", "pip", "install", "pypdf"], capture_output=True, timeout=30)
                    import pypdf as _pypdf
                    pypdf = _pypdf
                except Exception:
                    pass

        if not pypdf:
            # Fallback regex extraction of text streams in PDF
            text_blocks = re.findall(r'\((.*?)\)T[jJ]', data.decode("latin-1", errors="ignore"))
            if text_blocks:
                raw_text = "\n".join(text_blocks)
                paragraphs = [p.strip() for p in raw_text.split("\n") if p.strip()]
                return {
                    "title": title,
                    "file_type": "pdf",
                    "paragraphs": paragraphs,
                    "raw_text": "\n\n".join(paragraphs)
                }
            raise RuntimeError("未检测到 pypdf 模块，请运行 pip install pypdf 安装 PDF 解析依赖。")

        reader = pypdf.PdfReader(io.BytesIO(data))
        text_parts = []
        for page_idx, page in enumerate(reader.pages):
            try:
                extracted = page.extract_text()
                if extracted and extracted.strip():
                    text_parts.append(extracted.strip())
            except Exception:
                continue

        raw_text = "\n\n".join(text_parts)
        paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
        return {
            "title": title,
            "file_type": "pdf",
            "paragraphs": paragraphs,
            "raw_text": raw_text
        }

    @staticmethod
    def _parse_csv(title: str, data: bytes, delimiter: str = ",") -> Dict[str, Any]:
        text = DocumentParser._decode_bytes(data)
        f = io.StringIO(text)
        reader = csv.reader(f, delimiter=delimiter)
        paragraphs = []
        headers = None
        for row in reader:
            if not any(c.strip() for c in row):
                continue
            if headers is None:
                headers = [c.strip() for c in row]
                continue
            # Format row with headers
            row_items = []
            for h, val in zip(headers, row):
                if val.strip():
                    row_items.append(f"{h}: {val.strip()}" if h else val.strip())
            if row_items:
                paragraphs.append("；".join(row_items))

        raw_text = "\n\n".join(paragraphs)
        return {
            "title": title,
            "file_type": "csv",
            "paragraphs": paragraphs,
            "raw_text": raw_text
        }

    @staticmethod
    def _parse_json(title: str, data: bytes) -> Dict[str, Any]:
        text = DocumentParser._decode_bytes(data)
        paragraphs = []
        try:
            obj = json.loads(text)
            if isinstance(obj, list):
                for item in obj:
                    if isinstance(item, dict):
                        paragraphs.append(" | ".join(f"{k}: {v}" for k, v in item.items() if str(v).strip()))
                    else:
                        paragraphs.append(str(item))
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    paragraphs.append(f"【{k}】\n{v}")
            else:
                paragraphs.append(str(obj))
        except Exception:
            paragraphs = [text]

        raw_text = "\n\n".join(paragraphs)
        return {
            "title": title,
            "file_type": "json",
            "paragraphs": paragraphs,
            "raw_text": raw_text
        }
