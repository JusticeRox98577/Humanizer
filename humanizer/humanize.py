"""The pipeline that ties the engines together.

Modes:

* ``hybrid``  (default, best) - rewrite with the local LLM on your GPU, then
  run the deterministic rule pass to scrub residual AI tells and boost
  burstiness.
* ``llm``     - LLM only.
* ``rules``   - dependency-free rule engine only (no GPU / model needed).

Long inputs are split on blank lines into paragraph-ish chunks so the model
stays inside its context window and each piece gets full attention.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import docx_edit, transforms
from .llm import LLMConfig, LLMError, LocalLLM
from .score import Score, score, verdict


@dataclass
class HumanizeResult:
    original: str
    humanized: str
    mode: str
    before: Score
    after: Score
    warnings: list[str] = field(default_factory=list)

    @property
    def improvement(self) -> float:
        """Drop in AI-likeness (positive = more human than the original)."""
        return round(self.before.ai_like - self.after.ai_like, 1)

    def summary(self) -> str:
        return (
            f"AI-likeness {self.before.ai_like:.0f} -> {self.after.ai_like:.0f} "
            f"({'-' if self.improvement >= 0 else '+'}{abs(self.improvement):.0f}); "
            f"now reads: {verdict(self.after.ai_like)}"
        )


def _chunk(text: str, max_chars: int = 4000) -> list[str]:
    """Split text into chunks on blank lines, keeping under ``max_chars``."""
    paragraphs = re.split(r"\n\s*\n", text)
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if not para.strip():
            continue
        if current and len(current) + len(para) + 2 > max_chars:
            chunks.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        chunks.append(current)
    return chunks or [text]


def _llm_rewrite(text: str, llm: LocalLLM, warnings: list[str]) -> str:
    """Rewrite via the LLM, chunk by chunk, falling back per-chunk on error."""
    out: list[str] = []
    for chunk in _chunk(text):
        try:
            out.append(llm.humanize(chunk))
        except LLMError as exc:
            warnings.append(f"LLM failed on a chunk, kept original: {exc}")
            out.append(chunk)
    return "\n\n".join(out)


def humanize(
    text: str,
    *,
    mode: str = "hybrid",
    llm: LocalLLM | None = None,
    llm_config: LLMConfig | None = None,
    seed: int | None = None,
    variability: float = 0.0,
    synonym_rate: float = 0.35,
    burstiness_strength: float = 0.5,
) -> HumanizeResult:
    """Humanize ``text`` and return the result plus before/after scores.

    If ``mode`` needs the LLM but no server is reachable, the pipeline falls
    back to ``rules`` and records a warning rather than failing outright.
    """
    text = text.strip()
    before = score(text)
    warnings: list[str] = []
    effective_mode = mode

    needs_llm = mode in ("hybrid", "llm")
    if needs_llm:
        llm = llm or LocalLLM(llm_config)
        if not llm.is_available():
            warnings.append(
                "No local LLM reachable - falling back to the rule engine. "
                "Start Ollama (or your OpenAI-compatible server) for best quality."
            )
            effective_mode = "rules"

    if effective_mode == "llm":
        humanized = _llm_rewrite(text, llm, warnings)
    elif effective_mode == "hybrid":
        stage1 = _llm_rewrite(text, llm, warnings)
        # Light post-pass: the LLM already handled most rewriting, so keep the
        # rule pass gentle (no synonym churn, mild burstiness) to avoid damage.
        humanized = transforms.humanize_rules(
            stage1,
            seed=seed,
            variability=variability,
            synonym_rate=0.0,
            burstiness_strength=burstiness_strength * 0.4,
            do_synonyms=False,
        )
    else:  # rules
        humanized = transforms.humanize_rules(
            text,
            seed=seed,
            variability=variability,
            synonym_rate=synonym_rate,
            burstiness_strength=burstiness_strength,
        )

    after = score(humanized)
    return HumanizeResult(
        original=text,
        humanized=humanized,
        mode=effective_mode,
        before=before,
        after=after,
        warnings=warnings,
    )


def _resolve_llm_mode(mode, llm, llm_config, warnings):
    """Return (effective_mode, llm) after checking the model is reachable."""
    if mode in ("hybrid", "llm"):
        llm = llm or LocalLLM(llm_config)
        if not llm.is_available():
            warnings.append(
                "No local LLM reachable - falling back to the rule engine. "
                "Start Ollama (or your OpenAI-compatible server) for best quality."
            )
            return "rules", llm
    return mode, llm


def _paragraph_rewriter(effective_mode, llm, warnings, seed, burstiness_strength):
    """Build a per-paragraph text->text function for the given mode."""
    def rewrite(text: str) -> str:
        if not text.strip():
            return text
        if effective_mode in ("llm", "hybrid"):
            try:
                out = llm.humanize(text)
            except LLMError as exc:
                warnings.append(f"LLM failed on a paragraph, kept original: {exc}")
                return text
            if effective_mode == "hybrid":
                out = transforms.humanize_rules(
                    out,
                    seed=seed,
                    synonym_rate=0.0,
                    burstiness_strength=burstiness_strength * 0.4,
                    do_synonyms=False,
                )
            return out
        return transforms.humanize_rules(
            text, seed=seed, burstiness_strength=burstiness_strength
        )

    return rewrite


def humanize_docx(
    raw: bytes,
    *,
    mode: str = "hybrid",
    llm: LocalLLM | None = None,
    llm_config: LLMConfig | None = None,
    seed: int | None = None,
    burstiness_strength: float = 0.5,
    min_words: int = 5,
) -> tuple[bytes, HumanizeResult]:
    """Humanize a .docx **in place**, preserving all formatting.

    Returns ``(new_docx_bytes, result)`` where ``result`` carries the
    concatenated before/after text and scores.
    """
    warnings: list[str] = []
    effective_mode, llm = _resolve_llm_mode(mode, llm, llm_config, warnings)
    rewrite = _paragraph_rewriter(
        effective_mode, llm, warnings, seed, burstiness_strength
    )

    new_bytes, orig_text, new_text = docx_edit.humanize_docx_bytes(
        raw, rewrite, min_words=min_words
    )

    result = HumanizeResult(
        original=orig_text,
        humanized=new_text,
        mode=effective_mode,
        before=score(orig_text),
        after=score(new_text),
        warnings=warnings,
    )
    return new_bytes, result
