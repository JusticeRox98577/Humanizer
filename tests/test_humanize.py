"""Tests that exercise the parts that work without a GPU or a running model.

Run with:  python -m pytest   (or)   python tests/test_humanize.py
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import io  # noqa: E402
import zipfile  # noqa: E402

from humanizer import docx_edit, extract, humanize, humanize_docx, score, transforms, writeback  # noqa: E402,E501
from humanizer.data import AI_PHRASES, AI_WORDS  # noqa: E402

SAMPLE = (
    "In today's fast-paced world, it is important to note that artificial "
    "intelligence plays a crucial role in transforming how we work. "
    "Furthermore, businesses must leverage cutting-edge technologies in order "
    "to remain competitive. Moreover, it is worth noting that these robust "
    "solutions facilitate seamless workflows across a wide range of industries. "
    "Additionally, organizations should delve into the intricacies of data "
    "analytics to unlock unprecedented insights."
)


def test_scorer_flags_ai_text():
    s = score(SAMPLE)
    assert s.ai_like > 55, f"expected AI text to score high, got {s.ai_like}"
    assert s.ai_phrase_hits > 0
    assert s.ai_word_hits > 0


def test_rules_reduce_ai_score():
    out = transforms.humanize_rules(SAMPLE, seed=1)
    before = score(SAMPLE).ai_like
    after = score(out).ai_like
    assert after < before, f"rules should lower the score: {before} -> {after}"


def test_ai_phrases_removed():
    out = transforms.humanize_rules(SAMPLE, seed=1).lower()
    for phrase in ("it is important to note", "in today's fast-paced world",
                   "in conclusion", "it is worth noting"):
        assert phrase not in out, f"phrase survived: {phrase}"


def test_ai_words_replaced():
    out = transforms.humanize_rules(SAMPLE, seed=1).lower()
    for word in ("delve", "leverage", "furthermore", "moreover", "seamless"):
        assert word not in out.split(), f"word survived: {word}"


def test_contractions_applied():
    out = transforms.apply_contractions("It is clear that they are not ready.")
    assert "it's" in out.lower()
    assert "aren't" in out.lower()


def test_pipeline_rules_mode_no_model():
    # mode=rules must never touch the network.
    result = humanize(SAMPLE, mode="rules")
    assert result.mode == "rules"
    assert result.after.ai_like <= result.before.ai_like
    assert result.humanized
    assert "->" in result.summary()


def test_hybrid_falls_back_without_llm():
    # No server running here, so hybrid must degrade to rules + warn.
    from humanizer.llm import LLMConfig

    result = humanize(SAMPLE, mode="hybrid",
                      llm_config=LLMConfig(base_url="http://localhost:59999"))
    assert result.mode == "rules"
    assert any("fall" in w.lower() or "fell" in w.lower() for w in result.warnings)


def test_docx_roundtrip():
    text = "First paragraph here.\nSecond paragraph with more words in it."
    buf = Path("/tmp/_humanizer_test.docx")
    writeback.write_docx(text, buf)
    back = extract.read_docx(buf)
    assert "First paragraph" in back
    assert "Second paragraph" in back
    buf.unlink()


def test_extract_bytes_txt():
    raw = "hello world".encode("utf-8")
    assert extract.extract_bytes(raw, "note.txt") == "hello world"


def test_data_maps_are_clean():
    # keys are lowercase, no key maps to itself
    for k, v in AI_WORDS.items():
        assert k == k.lower()
        assert k != v
    for k in AI_PHRASES:
        assert k == k.lower()


def _make_formatted_docx() -> bytes:
    """Build a .docx with a Heading style, a bold run, and an extra part."""
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        # heading (short -> should be left untouched)
        '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
        "<w:r><w:t>Introduction</w:t></w:r></w:p>"
        # body paragraph: a bold lead-in run + a longer normal run
        "<w:p>"
        '<w:r><w:rPr><w:b/></w:rPr><w:t xml:space="preserve">Furthermore, </w:t></w:r>'
        "<w:r><w:t>it is important to note that we must leverage robust "
        "solutions to delve into seamless workflows across many industries.</w:t></w:r>"
        "</w:p>"
        "</w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")  # dummy but distinct part
        zf.writestr("word/styles.xml", "<styles>keep me</styles>")
        zf.writestr("word/document.xml", document)
    return buf.getvalue()


def test_docx_preserves_formatting():
    raw = _make_formatted_docx()
    rewrite = lambda t: transforms.humanize_rules(t, seed=1)  # noqa: E731
    new_bytes, orig, new = docx_edit.humanize_docx_bytes(raw, rewrite, min_words=5)

    zf = zipfile.ZipFile(io.BytesIO(new_bytes))
    doc = zf.read("word/document.xml").decode("utf-8")

    # formatting markup survives
    assert "<w:b/>" in doc, "bold run property was lost"
    assert 'w:pStyle w:val="Heading1"' in doc, "heading style was lost"
    # untouched sibling parts survive byte-for-byte
    assert zf.read("word/styles.xml").decode() == "<styles>keep me</styles>"
    # heading text (short) left alone; body text humanized
    assert "Introduction" in doc
    assert "delve" not in doc.lower()
    assert "furthermore" not in doc.lower()


def test_docx_pipeline_rules_mode():
    raw = _make_formatted_docx()
    new_bytes, result = humanize_docx(raw, mode="rules")
    assert result.mode == "rules"
    assert result.after.ai_like <= result.before.ai_like
    # still a readable docx
    text = extract.read_docx(io.BytesIO(new_bytes))
    assert "Introduction" in text
    assert new_bytes[:2] == b"PK"  # valid zip


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL {fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(fns)} tests passed")
    return passed == len(fns)


if __name__ == "__main__":
    ok = _run_all()
    sys.exit(0 if ok else 1)
