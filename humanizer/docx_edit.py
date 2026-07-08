"""Formatting-preserving humanization of .docx files.

Regenerating a Word document from extracted plain text throws away everything
that makes it a document: headings, bold/italic, fonts, colours, lists, tables,
images, spacing. To keep all of that, we do **not** rebuild the file. Instead we:

1. Open the original .docx (a ZIP) and read ``word/document.xml``.
2. Walk it paragraph by paragraph, pull out each paragraph's visible text,
   humanize just that text, and write the result back into the paragraph's
   existing runs — putting the rewritten text into the first text run (keeping
   its formatting) and blanking the rest.
3. Re-zip the archive copying **every other part byte-for-byte**, replacing only
   ``word/document.xml``.

Because we only ever change the characters inside ``<w:t>`` elements and never
re-serialize the XML tree, all run/paragraph properties, namespaces, images and
tables survive exactly as they were.

Short paragraphs (headings, labels, table headers — anything under ``min_words``)
are left untouched so titles don't get mangled.
"""

from __future__ import annotations

import io
import re
import zipfile
from xml.sax.saxutils import escape, unescape

# Parts of a .docx that carry visible WordprocessingML paragraph text and are
# therefore worth humanizing: the body, comments, foot/endnotes, and every
# header/footer. (Text boxes live inside document.xml, so they're covered by
# the body.) Everything else - styles, numbering, settings, metadata - is left
# byte-for-byte untouched.
_TEXT_PART_RE = re.compile(
    r"^word/("
    r"document\.xml"
    r"|comments\.xml"
    r"|footnotes\.xml"
    r"|endnotes\.xml"
    r"|header\d+\.xml"
    r"|footer\d+\.xml"
    r")$"
)

# Matches, in document order:
#   * a paragraph open tag  <w:p ...>   (selfclose captured for <w:p/>)
#   * a paragraph close tag </w:p>
#   * a text element        <w:t ...>text</w:t>   (self-closing <w:t/> excluded
#     via the (?<!/) lookbehind so it isn't mistaken for an open tag)
# \b after "w:t"/"w:p" stops it matching <w:tab>, <w:tbl>, <w:pPr>, etc.
_TAG_RE = re.compile(
    r"(?P<popen><w:p\b[^>]*?(?P<selfclose>/?)>)"
    r"|(?P<pclose></w:p>)"
    r"|(?P<t><w:t\b[^>]*?(?<!/)>(?P<ttext>.*?)</w:t>)",
    re.S,
)


def _rewrite_document_xml(xml: str, rewrite_fn, min_words: int):
    """Return (new_xml, original_text, new_text).

    ``rewrite_fn`` maps one paragraph's plain text to its humanized version.
    """
    stack: list[list[tuple[int, int, str]]] = []
    paragraphs: list[list[tuple[int, int, str]]] = []

    for m in _TAG_RE.finditer(xml):
        if m.group("popen") is not None:
            if m.group("selfclose") == "/":
                continue  # <w:p/> — empty paragraph, nothing to do
            stack.append([])
        elif m.group("pclose") is not None:
            if stack:
                paragraphs.append(stack.pop())
        else:  # a <w:t> text node
            if stack:
                stack[-1].append((m.start("t"), m.end("t"), m.group("ttext")))

    replacements: list[tuple[int, int, str]] = []
    orig_parts: list[str] = []
    new_parts: list[str] = []

    for tnodes in paragraphs:
        if not tnodes:
            continue
        text = "".join(unescape(t[2]) for t in tnodes)
        orig_parts.append(text)

        if not text.strip() or len(text.split()) < min_words:
            new_parts.append(text)  # leave headings / short lines alone
            continue

        newtext = rewrite_fn(text)
        new_parts.append(newtext)

        # Put all rewritten text into the run that originally held the most
        # text (its formatting is the paragraph's dominant style), and empty
        # the rest. This avoids, e.g., a short bold lead-in word making the
        # whole rewritten paragraph bold.
        target = max(range(len(tnodes)), key=lambda i: len(tnodes[i][2]))
        for i, (s, e, _) in enumerate(tnodes):
            body = escape(newtext) if i == target else ""
            replacements.append((s, e, '<w:t xml:space="preserve">' + body + "</w:t>"))

    # Apply edits right-to-left so earlier offsets stay valid.
    replacements.sort(key=lambda r: r[0], reverse=True)
    out = xml
    for s, e, rep in replacements:
        out = out[:s] + rep + out[e:]

    return out, "\n".join(orig_parts), "\n".join(new_parts)


def humanize_docx_bytes(
    raw: bytes, rewrite_fn, *, min_words: int = 5, body_only: bool = False
):
    """Humanize a .docx (given as bytes), preserving all formatting.

    By default this rewrites the body **and** comments, footnotes, endnotes,
    headers and footers. Set ``body_only=True`` to touch only the main body.

    Returns ``(new_docx_bytes, original_text, humanized_text)``.
    """
    src = zipfile.ZipFile(io.BytesIO(raw))
    if "word/document.xml" not in src.namelist():
        src.close()
        raise ValueError("Not a valid .docx (missing word/document.xml).")

    def _is_target(name: str) -> bool:
        if body_only:
            return name == "word/document.xml"
        return bool(_TEXT_PART_RE.match(name))

    edited: dict[str, str] = {}
    orig_parts: list[str] = []
    new_parts: list[str] = []

    for name in src.namelist():
        if not _is_target(name):
            continue
        xml = src.read(name).decode("utf-8")
        new_xml, orig_text, new_text = _rewrite_document_xml(
            xml, rewrite_fn, min_words
        )
        edited[name] = new_xml
        if orig_text.strip():
            orig_parts.append(orig_text)
            new_parts.append(new_text)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename in edited:
                data = edited[item.filename].encode("utf-8")
            # Preserve each part's original ZipInfo (name, date, compression).
            dst.writestr(item, data)
    src.close()
    return buf.getvalue(), "\n".join(orig_parts), "\n".join(new_parts)
