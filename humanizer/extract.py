"""Read plain text out of the formats a user is likely to paste or upload.

Supports ``.docx``, ``.txt`` and ``.md`` with **no third-party dependencies**.
A ``.docx`` file is just a ZIP archive containing XML, so we unzip it and pull
the text out of ``word/document.xml`` with the standard library.
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

# WordprocessingML namespace used inside word/document.xml.
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def read_docx(source: str | Path | io.BytesIO) -> str:
    """Extract paragraph text from a .docx file using only the stdlib.

    ``source`` may be a path or an in-memory file-like object (used by the web
    UI, which uploads the raw bytes).

    Each Word paragraph (``<w:p>``) becomes one line.  Runs (``<w:t>``) inside
    a paragraph are concatenated, and explicit breaks (``<w:br>`` / ``<w:tab>``)
    are honoured so the text keeps a sensible shape.
    """
    with zipfile.ZipFile(source) as zf:
        with zf.open("word/document.xml") as fh:
            tree = ET.parse(fh)

    paragraphs: list[str] = []
    for para in tree.iter(f"{_W}p"):
        parts: list[str] = []
        for node in para.iter():
            tag = node.tag
            if tag == f"{_W}t":
                parts.append(node.text or "")
            elif tag == f"{_W}tab":
                parts.append("\t")
            elif tag == f"{_W}br":
                parts.append("\n")
        paragraphs.append("".join(parts))

    # Collapse runs of blank paragraphs but keep intended paragraph breaks.
    text = "\n".join(paragraphs)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def read_text_file(path: str | Path) -> str:
    """Read a .txt or .md file, tolerating odd encodings."""
    raw = Path(path).read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return raw.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace").strip()


def extract(path: str | Path) -> str:
    """Dispatch on file extension and return the document's plain text."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return read_docx(path)
    if suffix in (".txt", ".md", ".markdown", ""):
        return read_text_file(path)
    if suffix == ".doc":
        raise ValueError(
            "Legacy .doc (Word 97-2003) is not supported. "
            "Open it in Word and 'Save As' .docx first."
        )
    # Best effort: treat anything else as UTF-8 text.
    return read_text_file(path)


def extract_bytes(raw: bytes, filename: str) -> str:
    """Extract text from raw uploaded bytes, dispatching on ``filename``."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".docx":
        return read_docx(io.BytesIO(raw))
    if suffix == ".doc":
        raise ValueError(
            "Legacy .doc (Word 97-2003) is not supported. "
            "Open it in Word and 'Save As' .docx first."
        )
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return raw.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace").strip()
