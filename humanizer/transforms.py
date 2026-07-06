"""The dependency-free rule engine.

Two jobs:

1. Run standalone as a lightweight humanizer when no local model is available.
2. Run as a *post-processor* after the LLM to strip any residual AI tells the
   model left behind and to nudge burstiness up.

Every pass targets a specific detector signal (see ``score.py``).  Passes are
deterministic given a seed so output is reproducible; pass ``variability`` up
to make each run differ.
"""

from __future__ import annotations

import random
import re

from . import data

_WORD_BOUNDARY = r"\b"
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])(\s+)")


def _preserve_case(original: str, replacement: str) -> str:
    """Match the capitalization of ``original`` onto ``replacement``."""
    if not replacement:
        return replacement
    if original.isupper() and len(original) > 1:
        return replacement.upper()
    if original[0].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


def strip_ai_phrases(text: str) -> str:
    """Remove or replace multi-word AI cliches (longest phrases first)."""
    for phrase in sorted(data.AI_PHRASES, key=len, reverse=True):
        replacement = data.AI_PHRASES[phrase]
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)

        def _sub(m: re.Match) -> str:
            return _preserve_case(m.group(0), replacement)

        text = pattern.sub(_sub, text)

    # Tidy artifacts left by deletions: doubled spaces, space-before-punct,
    # and leading lower-case after a phrase like "In conclusion, X" -> "X".
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([.!?])\s*,\s*", r"\1 ", text)
    text = re.sub(r"(^|[.!?]\s+),\s*", r"\1", text)
    return text


def replace_ai_words(text: str) -> str:
    """Swap single-word AI tells for plainer alternatives."""
    def _repl(m: re.Match) -> str:
        word = m.group(0)
        return _preserve_case(word, data.AI_WORDS[word.lower()])

    pattern = re.compile(
        _WORD_BOUNDARY + r"(" + "|".join(map(re.escape, data.AI_WORDS)) + r")" + _WORD_BOUNDARY,
        re.IGNORECASE,
    )
    return pattern.sub(_repl, text)


def soften_transitions(text: str, rng: random.Random) -> str:
    """Rewrite stiff sentence-initial transitions conversationally.

    Avoids picking the same replacement twice in a row so we do not trade one
    tell ("Furthermore... Moreover...") for another ("Also... Also...").
    """
    last_choice = {"value": None}

    def _repl(m: re.Match) -> str:
        lead, word = m.group(1), m.group(2)
        options = data.TRANSITION_STARTS[word.lower()]
        pool = [o for o in options if o != last_choice["value"]] or options
        choice = rng.choice(pool)
        last_choice["value"] = choice
        # Each replacement already carries its own punctuation ("Plus," has a
        # comma, "And"/"So" do not), so the original trailing comma (group 3)
        # is intentionally dropped.
        return f"{lead}{_preserve_case(word, choice)}"

    pattern = re.compile(
        r"(^|[.!?]\s+)(" + "|".join(map(re.escape, data.TRANSITION_STARTS)) + r")(,?)",
        re.IGNORECASE | re.MULTILINE,
    )
    return pattern.sub(_repl, text)


def apply_contractions(text: str) -> str:
    """Contract common word pairs the way people actually write."""
    for phrase, contracted in data.CONTRACTIONS.items():
        pattern = re.compile(_WORD_BOUNDARY + re.escape(phrase) + _WORD_BOUNDARY, re.IGNORECASE)

        def _sub(m: re.Match) -> str:
            return _preserve_case(m.group(0), contracted)

        text = pattern.sub(_sub, text)
    return text


def swap_synonyms(text: str, rng: random.Random, rate: float = 0.35) -> str:
    """Replace a fraction of eligible common words with rarer synonyms.

    Swapping only a fraction (``rate``) keeps the text natural while still
    perturbing the token distribution enough to raise perplexity.
    """
    keys = {k: v for k, v in data.SYNONYMS.items() if " " not in k}

    def _repl(m: re.Match) -> str:
        word = m.group(0)
        low = word.lower()
        if low in keys and rng.random() < rate:
            return _preserve_case(word, rng.choice(keys[low]))
        return word

    pattern = re.compile(
        _WORD_BOUNDARY + r"(" + "|".join(map(re.escape, keys)) + r")" + _WORD_BOUNDARY,
        re.IGNORECASE,
    )
    return pattern.sub(_repl, text)


def _split_sentences(text: str) -> list[str]:
    """Split into sentences while keeping the whitespace that followed each."""
    parts = _SENTENCE_SPLIT.split(text)
    sentences: list[str] = []
    i = 0
    while i < len(parts):
        chunk = parts[i]
        sep = parts[i + 1] if i + 1 < len(parts) else ""
        sentences.append(chunk + sep)
        i += 2
    return [s for s in sentences if s]


def increase_burstiness(text: str, rng: random.Random, strength: float = 0.5) -> str:
    """Vary sentence rhythm so lengths are less uniform.

    * Long sentences with a natural break (``, and`` / ``, but`` / ``; ``) are
      occasionally split into two.
    * A short punchy interjection is occasionally spliced after a long
      sentence.

    ``strength`` (0-1) scales how aggressively this happens.
    """
    sentences = _split_sentences(text)
    if len(sentences) < 3:
        return text

    out: list[str] = []
    for sent in sentences:
        core = sent.rstrip()
        trailing_ws = sent[len(core):]
        words = core.split()

        # Split an over-long sentence at a coordinating conjunction.
        if len(words) > 22 and rng.random() < strength:
            m = re.search(r",\s+(and|but|so|which|while|because)\s+", core)
            if m:
                head = core[: m.start()].rstrip(", ")
                tail = core[m.end():]
                if head and tail:
                    head = head[0].upper() + head[1:]
                    tail = tail[0].upper() + tail[1:]
                    if not head.endswith((".", "!", "?")):
                        head += "."
                    out.append(head + " " + tail + trailing_ws)
                    continue

        out.append(sent)

        # Occasionally follow a long sentence with a short beat.
        if len(words) > 18 and rng.random() < strength * 0.25:
            out.append(rng.choice(data.SHORT_INTERJECTIONS) + " ")

    return "".join(out)


def _capitalize_sentences(text: str) -> str:
    """Capitalize the first letter of each sentence (fixes fallout from phrase
    deletions that leave a lowercase word at the start of a sentence)."""
    def _upper_after(m: re.Match) -> str:
        return m.group(1) + m.group(2).upper()

    # Start of the whole text, or the first letter after . ! ? followed by
    # whitespace. Leave "i" -> "I" handled naturally since it upper-cases.
    text = re.sub(r"(^|[.!?]\s+|\n\s*)([a-z])", _upper_after, text)
    return text


def normalize_whitespace(text: str) -> str:
    """Final cleanup pass."""
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" +\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = text.strip()
    text = _capitalize_sentences(text)
    return text


def humanize_rules(
    text: str,
    *,
    seed: int | None = None,
    variability: float = 0.0,
    synonym_rate: float = 0.35,
    burstiness_strength: float = 0.5,
    do_synonyms: bool = True,
    do_burstiness: bool = True,
) -> str:
    """Run the full rule-based pipeline over ``text``.

    ``seed`` makes output reproducible; leave it ``None`` (with
    ``variability`` > 0) to get a fresh variation each call.
    """
    if seed is None and variability <= 0:
        seed = hash(text) & 0xFFFFFFFF
    rng = random.Random(seed if seed is not None else random.random())

    text = strip_ai_phrases(text)
    # Soften transitions *before* word replacement so varied sentence-initial
    # transitions are chosen rather than collapsed into a repetitive "also".
    text = soften_transitions(text, rng)
    text = replace_ai_words(text)
    if do_synonyms:
        text = swap_synonyms(text, rng, rate=synonym_rate)
    text = apply_contractions(text)
    if do_burstiness:
        text = increase_burstiness(text, rng, strength=burstiness_strength)
    text = normalize_whitespace(text)
    return text
