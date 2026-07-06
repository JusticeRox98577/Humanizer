"""Humanizer - rewrite AI-sounding text so it reads like a person wrote it.

Public API:

    from humanizer import humanize, LocalLLM, LLMConfig, score

    result = humanize("Furthermore, it is important to note that ...")
    print(result.humanized)
    print(result.summary())
"""

from __future__ import annotations

from .humanize import HumanizeResult, humanize
from .llm import LLMConfig, LLMError, LocalLLM
from .score import Score, score, verdict

__all__ = [
    "humanize",
    "HumanizeResult",
    "LocalLLM",
    "LLMConfig",
    "LLMError",
    "score",
    "Score",
    "verdict",
]

__version__ = "1.0.0"
