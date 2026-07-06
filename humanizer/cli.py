"""Command-line interface.

Examples
--------
    # Humanize a Word doc with your local GPU model, save a new .docx
    python -m humanizer essay.docx -o essay.humanized.docx

    # Humanize piped text, print to stdout
    echo "Furthermore, it is important to note..." | python -m humanizer

    # Just score how AI-like something looks
    python -m humanizer --score essay.docx

    # Force the zero-dependency rule engine (no GPU/model needed)
    python -m humanizer essay.txt --mode rules

    # Point at LM Studio instead of Ollama
    python -m humanizer in.txt --engine openai --base-url http://localhost:1234 --model local-model
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import extract, writeback
from .humanize import humanize
from .llm import LLMConfig, LocalLLM
from .score import score, verdict


def _read_input(source: str | None) -> str:
    if source is None or source == "-":
        return sys.stdin.read()
    return extract.extract(source)


def _print_score(label: str, text: str, stream=sys.stderr) -> None:
    s = score(text)
    print(f"\n{label}", file=stream)
    print(f"  AI-likeness : {s.ai_like:5.1f}/100  ({verdict(s.ai_like)})", file=stream)
    print(f"  Burstiness  : {s.burstiness:5.2f}   (higher = more human)", file=stream)
    print(f"  Common-word : {s.common_word_ratio:5.2f}", file=stream)
    print(f"  AI phrases  : {s.ai_phrase_hits}   AI words: {s.ai_word_hits}", file=stream)
    for note in s.notes:
        print(f"  - {note}", file=stream)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="humanizer",
        description="Rewrite AI-sounding text so it reads like a person wrote it.",
    )
    p.add_argument("input", nargs="?", help="Input file (.docx/.txt/.md) or '-' for stdin")
    p.add_argument("-o", "--output", help="Output file (.docx or .txt). Default: stdout")
    p.add_argument(
        "--mode",
        choices=["hybrid", "llm", "rules"],
        default="hybrid",
        help="hybrid = local LLM + rule cleanup (best); llm = model only; "
        "rules = zero-dependency engine, no GPU needed (default: hybrid)",
    )
    p.add_argument("--score", action="store_true", help="Only score the input, do not rewrite")

    g = p.add_argument_group("local model")
    g.add_argument("--engine", choices=["ollama", "openai"], default="ollama")
    g.add_argument("--model", default="qwen2.5:14b-instruct", help="Model name/tag")
    g.add_argument("--base-url", default=None, help="Server URL (default per engine)")
    g.add_argument("--temperature", type=float, default=0.8)

    t = p.add_argument_group("tuning")
    t.add_argument("--seed", type=int, default=None, help="Reproducible output")
    t.add_argument("--synonym-rate", type=float, default=0.35)
    t.add_argument("--burstiness", type=float, default=0.5)
    t.add_argument("--quiet", action="store_true", help="Suppress the score report")

    p.add_argument("--serve", action="store_true", help="Launch the web UI instead")
    p.add_argument("--port", type=int, default=8000, help="Port for --serve")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.serve:
        from .server import serve

        serve(port=args.port)
        return 0

    if args.input is None and sys.stdin.isatty():
        build_parser().print_help()
        return 1

    text = _read_input(args.input)
    if not text.strip():
        print("No input text.", file=sys.stderr)
        return 1

    if args.score:
        _print_score("INPUT", text, stream=sys.stdout)
        return 0

    base_url = args.base_url or (
        "http://localhost:11434" if args.engine == "ollama" else "http://localhost:1234"
    )
    llm = LocalLLM(
        LLMConfig(
            engine=args.engine,
            model=args.model,
            base_url=base_url,
            temperature=args.temperature,
        )
    )

    result = humanize(
        text,
        mode=args.mode,
        llm=llm,
        seed=args.seed,
        synonym_rate=args.synonym_rate,
        burstiness_strength=args.burstiness,
    )

    for w in result.warnings:
        print(f"! {w}", file=sys.stderr)

    if args.output:
        writeback.write_output(result.humanized, args.output)
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(result.humanized)

    if not args.quiet:
        _print_score("BEFORE", result.original)
        _print_score("AFTER", result.humanized)
        print(f"\n=> {result.summary()}  [mode: {result.mode}]", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
