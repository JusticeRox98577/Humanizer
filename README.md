# Humanizer

Rewrite AI-sounding text so it reads like a person wrote it — locally, privately,
and on your own GPU. Paste text or drop a **.docx / .txt / .md** file, get back a
humanized version plus a before/after score.

It runs in three tiers:

| Mode | Engine | Needs a GPU/model? | Quality |
|------|--------|--------------------|---------|
| `rules`  | Dependency-free Python rule engine | No | Decent |
| `llm`    | A local LLM on your GPU (Ollama / LM Studio) | Yes | High |
| `hybrid` *(default)* | LLM rewrite **+** rule cleanup | Yes | Best |

**Zero pip dependencies.** The whole thing — parsing Word docs, the web UI, the
HTTP calls to your model — is pure Python standard library. The only external
piece is the local model server (Ollama), and that's optional.

---

## ⚠️ Read this first (honest expectations)

- **No humanizer can *guarantee* it will beat any given AI detector.** Detectors
  and humanizers are in a constant arms race. Tools that claim "100% undetectable"
  are lying. This tool changes the *statistical fingerprints* detectors key on —
  it does not promise a verdict from GPTZero, Turnitin, or anyone else.
- **The built-in score is a heuristic, not a detector.** It measures the same
  surface signals detectors use (burstiness, perplexity proxy, AI-vocabulary
  density) so you can see whether a rewrite moved in the right direction. Treat it
  as a tuning gauge, not proof.
- **Use it honestly.** Good uses: making AI-assisted drafts sound natural, reducing
  false positives on genuinely human/edited writing, helping non-native speakers.
  Passing AI work off as your own where that's against the rules is on you, not the
  tool.

---

## Quick start (no GPU, works immediately)

```bash
git clone <this repo> && cd Humanizer

# Humanize a Word doc with the zero-dependency rule engine
python -m humanizer examples/sample_ai_text.txt --mode rules

# Just score how AI-like something looks
echo "Furthermore, it is important to note that we must leverage robust solutions." \
  | python -m humanizer --score
```

That's it — no `pip install` needed for rule mode.

---

## Running it on your GPU (recommended — this is the "neural net" tier)

A local instruct model does the heavy rewriting; the rule engine then scrubs any
residual tells. This is how you get quality comparable to the commercial tools,
fully offline and free. **Ollama is the easiest path for an AMD Radeon RX 7900 XT**
(officially ROCm-supported, gfx1100) on both Windows and Linux.

### 1. Install Ollama

- **Windows:** download the installer from <https://ollama.com/download>. It ships
  with ROCm and uses your 7900 XT automatically.
- **Linux:** `curl -fsSL https://ollama.com/install.sh | sh`
  (For AMD, also install the ROCm packages for your distro if the installer
  doesn't pull them. Ollama detects the GPU on start-up.)

Verify the GPU is picked up:
```bash
ollama serve               # if it isn't already running as a service
ollama run llama3.1 "hi"   # watch VRAM usage; it should hit the GPU
```

### 2. Pull a model

Your 20 GB of VRAM comfortably runs a 14B-class model quantized. Good picks:

```bash
ollama pull qwen2.5:14b-instruct     # default; strong rewriter, fits easily
# alternatives:
ollama pull llama3.1:8b-instruct     # faster, lighter
ollama pull mistral-nemo:12b         # good middle ground
ollama pull gemma2:27b               # heavier, higher quality (q4)
```

### 3. Humanize

```bash
# .docx in -> .docx out, with ALL formatting preserved.
# (With no -o, it writes essay.humanized.docx next to the original.)
python -m humanizer essay.docx -o essay.humanized.docx

# Pick a different model
python -m humanizer essay.docx --model llama3.1:8b-instruct
```

### Your Word formatting is kept

When you humanize a `.docx`, the tool edits your **original document in place** —
it never rebuilds it from plain text. Headings, bold/italic, fonts, colours,
bullet/numbered lists, tables and images all survive; only the words inside each
paragraph change. Short lines (headings, labels — anything under ~5 words) are
left exactly as they were so your titles don't get reworded.

It also rewrites the text in **comments, footnotes, endnotes, headers and
footers** — not just the main body. (Comment authors, dates and threading are
left untouched; only the comment text changes.) Pass `--body-only` if you want
the body alone.

One caveat: if a single paragraph mixes formatting (say, one bold word in the
middle of a normal sentence), the rewritten paragraph takes on that paragraph's
*dominant* run formatting, since the words themselves change and can't be mapped
back one-to-one. Uniformly-formatted paragraphs come back pixel-perfect.

### Prefer LM Studio / llama.cpp / vLLM instead?

Any OpenAI-compatible server works — point the tool at it:

```bash
python -m humanizer essay.txt \
  --engine openai \
  --base-url http://localhost:1234 \
  --model your-loaded-model
```

---

## Web UI

```bash
python -m humanizer --serve            # then open http://localhost:8000
```

Drag-and-drop a `.docx`/`.txt`/`.md`, pick a mode, hit **Humanize**. You get the
rewritten text, before/after AI-likeness meters, and one-click `.txt` / `.docx`
download. Model settings (engine, model, temperature) are in the collapsible
panel. Everything stays on your machine.

---

## CLI reference

```
python -m humanizer [input] [options]

  input                 .docx/.txt/.md file, or '-'/omitted for stdin
  -o, --output FILE     write to .docx or .txt (default: stdout)
  --mode {hybrid,llm,rules}   pipeline (default: hybrid)
  --score               only score the input, don't rewrite

  local model:
  --engine {ollama,openai}    default: ollama
  --model NAME                default: qwen2.5:14b-instruct
  --base-url URL              default per engine
  --temperature FLOAT         default: 0.8

  tuning:
  --seed INT                  reproducible output
  --synonym-rate FLOAT        0-1, how often to swap synonyms (rules)
  --burstiness FLOAT          0-1, sentence-rhythm variation strength
  --body-only                 .docx: skip comments/footnotes/headers/footers
  --quiet                     suppress the score report

  --serve / --port            launch the web UI
```

---

## Python API

```python
from humanizer import humanize, LocalLLM, LLMConfig

# Rule engine only (no model)
r = humanize("Furthermore, it is important to note that...", mode="rules")
print(r.humanized)
print(r.summary())        # AI-likeness 70 -> 34 (-36); now reads: Mixed

# On your GPU
llm = LocalLLM(LLMConfig(model="qwen2.5:14b-instruct"))
r = humanize(open("essay.txt").read(), mode="hybrid", llm=llm)
```

---

## How it works

Detectors mostly score three things. Each pass targets one:

1. **Perplexity** — AI text is "too predictable." → The LLM rewrite plus synonym
   swaps raise it by using less generic phrasing.
2. **Burstiness** — humans vary sentence length wildly; AI is metronomic. → The
   burstiness pass splits over-long sentences and varies rhythm; the LLM prompt
   makes this its top priority.
3. **Vocabulary tells** — "delve, tapestry, leverage, furthermore, it is important
   to note…" → stripped and replaced with plainer words, with *varied* transitions
   so we don't trade one tell for another.

`score.py` estimates all of this so you can measure before/after. See the module
docstrings for the full breakdown.

---

## Project layout

```
humanizer/
  data.py        word/phrase/synonym maps (the rule knowledge base)
  extract.py     read .docx/.txt/.md (stdlib zip+xml, no python-docx)
  writeback.py   write a plain .docx/.txt from scratch (stdlib)
  docx_edit.py   formatting-preserving in-place .docx rewrite (stdlib)
  transforms.py  the rule engine (phrases, transitions, contractions, burstiness)
  score.py       AI-likeness heuristic (burstiness / perplexity proxy / tells)
  llm.py         local LLM client (Ollama native + OpenAI-compatible)
  humanize.py    pipeline: hybrid / llm / rules, chunking, before/after scoring
  cli.py         command line
  server.py      zero-dependency web UI
tests/           run: python tests/test_humanize.py
examples/        sample AI text to try
```

## Tests

```bash
python tests/test_humanize.py     # 10 tests, no network/model required
```
