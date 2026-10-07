import io
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
    Parses multiple document formats (.docx, .md, .txt, .pdf) into clean text & structural sections.
    """
    @staticmethod
    def parse_file(filename: str, content_bytes: bytes) -> Dict[str, Any]:
        ext = Path(filename).suffix.lower()
        title = Path(filename).stem

        if ext == ".docx":
            return DocumentParser._parse_docx(title, content_bytes)
        elif ext in [".md", ".markdown"]:
            return DocumentParser._parse_markdown(title, content_bytes)
        elif ext in [".txt", ".text"]:
            return DocumentParser._parse_text(title, content_bytes)
        elif ext == ".pdf":
            return DocumentParser._parse_pdf(title, content_bytes)
        else:
            # Fallback to plain text attempt
            return DocumentParser._parse_text(title, content_bytes)

    @staticmethod
    def _parse_docx(title: str, data: bytes) -> Dict[str, Any]:
        if not docx:
            raise RuntimeError("python-docx is not installed.")
        
        doc = docx.Document(io.BytesIO(data))
        paragraphs = []
        for p in doc.paragraphs:
            text = p.text.strip()
            if text:
                paragraphs.append(text)

        raw_text = "\n\n".join(paragraphs)
        return {
            "title": title,
            "file_type": "docx",
            "paragraphs": paragraphs,
            "raw_text": raw_text
        }

    @staticmethod
    def _parse_markdown(title: str, data: bytes) -> Dict[str, Any]:
        # Try UTF-8 first, fallback to GB18030/GBK
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("gb18030", errors="replace")

        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        return {
            "title": title,
            "file_type": "md",
            "paragraphs": paragraphs,
            "raw_text": text
        }

    @staticmethod
    def _parse_text(title: str, data: bytes) -> Dict[str, Any]:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("gb18030", errors="replace")

        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        return {
            "title": title,
            "file_type": "txt",
            "paragraphs": paragraphs,
            "raw_text": text
        }

    @staticmethod
    def _parse_pdf(title: str, data: bytes) -> Dict[str, Any]:
        if not pypdf:
            raise RuntimeError("pypdf is not installed.")
        
        reader = pypdf.PdfReader(io.BytesIO(data))
        text_parts = []
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text_parts.append(extracted.strip())

        raw_text = "\n\n".join(text_parts)
        paragraphs = [p.strip() for p in raw_text.split("\n\n") if p.strip()]
        return {
            "title": title,
            "file_type": "pdf",
            "paragraphs": paragraphs,
            "raw_text": raw_text
        }
