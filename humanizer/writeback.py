"""Write humanized text back out to .txt or a clean .docx.

Building a minimal but *valid* .docx by hand (again, stdlib only) means the
tool can hand a user back a Word document without depending on python-docx.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

_DOC_HEAD = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
"""

_DOC_TAIL = """  </w:body>
</w:document>"""


def _paragraph_xml(text: str) -> str:
    """Render one line of text as a WordprocessingML paragraph."""
    if not text.strip():
        return "    <w:p/>\n"
    # xml:space=preserve keeps leading/trailing spaces intact.
    body = escape(text)
    return (
        "    <w:p><w:r><w:t xml:space=\"preserve\">"
        f"{body}"
        "</w:t></w:r></w:p>\n"
    )


def write_docx(text: str, path: str | Path) -> Path:
    """Write ``text`` (newline-separated paragraphs) to a valid .docx file."""
    path = Path(path)
    paragraphs = "".join(_paragraph_xml(line) for line in text.split("\n"))
    document = _DOC_HEAD + paragraphs + _DOC_TAIL

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr("_rels/.rels", _RELS)
        zf.writestr("word/document.xml", document)
    return path


def write_text(text: str, path: str | Path) -> Path:
    """Write plain text out as UTF-8."""
    path = Path(path)
    path.write_text(text, encoding="utf-8")
    return path


def write_output(text: str, path: str | Path) -> Path:
    """Dispatch on the requested output extension."""
    path = Path(path)
    if path.suffix.lower() == ".docx":
        return write_docx(text, path)
    return write_text(text, path)
