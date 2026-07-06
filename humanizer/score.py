"""A transparent, dependency-free estimator of how "AI-written" text looks.

This is **not** an AI detector and it is not GPTZero.  It is a proxy that
scores the same surface signals real detectors lean on, so you can measure
whether a humanization pass moved the needle in the right direction:

* **Burstiness** - humans vary sentence length a lot; LLMs are metronomic.
  Low variance in sentence length reads as machine-like.
* **Lexical predictability** - LLM prose leans heavily on the few hundred most
  common words (a stand-in for low perplexity).
* **AI phrase / word density** - the "delve / furthermore / it is important to
  note" family.
* **Lexical diversity** - the type-token ratio; very repetitive vocabulary is a
  mild tell.
* **Contraction rate** - formal LLM output under-uses contractions.

The output is a 0-100 "AI-like" estimate where lower is more human.  Treat it
as a relative gauge for tuning, not a verdict.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

from . import data

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[A-Za-z']+")


@dataclass
class Score:
    """Breakdown of the AI-likeness estimate for a piece of text."""

    ai_like: float  # 0-100, lower = more human
    burstiness: float
    common_word_ratio: float
    ai_phrase_hits: int
    ai_word_hits: int
    lexical_diversity: float
    contraction_ratio: float
    sentence_count: int
    word_count: int
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "ai_like": round(self.ai_like, 1),
            "burstiness": round(self.burstiness, 3),
            "common_word_ratio": round(self.common_word_ratio, 3),
            "ai_phrase_hits": self.ai_phrase_hits,
            "ai_word_hits": self.ai_word_hits,
            "lexical_diversity": round(self.lexical_diversity, 3),
            "contraction_ratio": round(self.contraction_ratio, 3),
            "sentence_count": self.sentence_count,
            "word_count": self.word_count,
            "notes": self.notes,
        }


def _sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_SPLIT.split(text.strip()) if s.strip()]


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def score(text: str) -> Score:
    """Estimate how AI-written ``text`` looks and return the full breakdown."""
    sentences = _sentences(text)
    words = _words(text)
    n_words = len(words)
    notes: list[str] = []

    if n_words < 15:
        # Too short to say anything meaningful.
        return Score(
            ai_like=50.0,
            burstiness=0.0,
            common_word_ratio=0.0,
            ai_phrase_hits=0,
            ai_word_hits=0,
            lexical_diversity=0.0,
            contraction_ratio=0.0,
            sentence_count=len(sentences),
            word_count=n_words,
            notes=["Text too short for a reliable estimate."],
        )

    # --- Burstiness: coefficient of variation of sentence lengths ---------
    lengths = [len(_words(s)) for s in sentences] or [0]
    mean_len = statistics.mean(lengths) if lengths else 0
    stdev_len = statistics.pstdev(lengths) if len(lengths) > 1 else 0
    burstiness = (stdev_len / mean_len) if mean_len else 0.0

    # --- Lexical predictability -------------------------------------------
    common_hits = sum(1 for w in words if w in data.COMMON_WORDS)
    common_ratio = common_hits / n_words

    # --- AI phrase / word density -----------------------------------------
    low = text.lower()
    phrase_hits = sum(low.count(p) for p in data.AI_PHRASES if p)
    ai_word_set = set(data.AI_WORDS)
    word_hits = sum(1 for w in words if w in ai_word_set)

    # --- Lexical diversity (type-token ratio) -----------------------------
    diversity = len(set(words)) / n_words

    # --- Contractions ------------------------------------------------------
    contraction_hits = sum(1 for w in words if "'" in w)
    contraction_ratio = contraction_hits / n_words

    # --- Combine into a 0-100 estimate ------------------------------------
    # Each term contributes points toward "looks AI".  Weights are tuned so
    # typical raw ChatGPT output lands ~70-90 and edited human text ~15-40.
    score_val = 0.0

    # Low burstiness is the strongest single tell.
    if burstiness < 0.35:
        score_val += 34
        notes.append("Very uniform sentence lengths (low burstiness).")
    elif burstiness < 0.5:
        score_val += 20
    elif burstiness < 0.65:
        score_val += 8

    # Over-reliance on common words => low perplexity.
    if common_ratio > 0.62:
        score_val += 22
        notes.append("Vocabulary leans heavily on the most common words.")
    elif common_ratio > 0.55:
        score_val += 12
    elif common_ratio > 0.48:
        score_val += 5

    # AI phrase density.
    phrase_density = phrase_hits / max(1, len(sentences))
    if phrase_density > 0.15:
        score_val += 20
        notes.append(f"Contains {phrase_hits} stock AI phrase(s).")
    elif phrase_hits:
        score_val += min(14, phrase_hits * 4)
        notes.append(f"Contains {phrase_hits} stock AI phrase(s).")

    # AI word density.
    ai_word_density = word_hits / n_words
    if ai_word_density > 0.04:
        score_val += 16
        notes.append(f"Uses {word_hits} LLM-favored word(s) (e.g. delve, leverage).")
    elif word_hits:
        score_val += min(12, word_hits * 2)

    # Low diversity is a mild tell (but very short texts are naturally high).
    if diversity < 0.4:
        score_val += 6
        notes.append("Repetitive vocabulary.")

    # Missing contractions in a long text nudges it toward "formal AI".
    if contraction_ratio < 0.005 and n_words > 80:
        score_val += 6
        notes.append("No contractions in a fairly long passage.")

    ai_like = max(0.0, min(100.0, score_val))

    return Score(
        ai_like=ai_like,
        burstiness=burstiness,
        common_word_ratio=common_ratio,
        ai_phrase_hits=phrase_hits,
        ai_word_hits=word_hits,
        lexical_diversity=diversity,
        contraction_ratio=contraction_ratio,
        sentence_count=len(sentences),
        word_count=n_words,
        notes=notes,
    )


def verdict(ai_like: float) -> str:
    """Human-readable band for an ``ai_like`` score."""
    if ai_like >= 70:
        return "Very likely AI"
    if ai_like >= 50:
        return "Leans AI"
    if ai_like >= 32:
        return "Mixed / uncertain"
    if ai_like >= 18:
        return "Leans human"
    return "Reads human"
