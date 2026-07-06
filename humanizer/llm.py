"""Talk to a **local** LLM running on your own GPU.

Two protocols are supported, both over the standard library (no ``requests``,
no ``openai`` package needed):

* **Ollama native** (default) - ``http://localhost:11434``.  Best AMD/ROCm
  support for a 7900 XT on both Windows and Linux.  Install Ollama, run
  ``ollama pull qwen2.5:14b-instruct`` (or any instruct model) and you are set.
* **OpenAI-compatible** - LM Studio (``http://localhost:1234/v1``),
  llama.cpp's server, text-generation-webui, vLLM, or Ollama's own
  ``/v1`` endpoint.  Point ``base_url`` at it.

The class is engine-agnostic: it just needs a chat endpoint that returns text.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

# The instruction that turns a general model into a humanizer.  It targets the
# same signals the scorer measures: burstiness, perplexity, and AI vocabulary.
SYSTEM_PROMPT = """You rewrite text so it reads like a real person wrote it, \
not an AI. Rewrite the user's text following ALL of these rules:

1. Keep the original meaning, facts, and roughly the same length. Do not add \
new claims or drop information.
2. Vary sentence length a lot. Mix short punchy sentences with longer ones. \
Real writing is bursty; AI writing is metronomic. This is the most important rule.
3. Use contractions (it's, don't, they're) and everyday word choices.
4. Never use these AI-tell words/phrases: delve, tapestry, leverage, utilize, \
furthermore, moreover, moreover, seamless, robust, holistic, "it is important \
to note", "in today's fast-paced world", "in conclusion", "a testament to", \
"navigate the complexities", "plays a crucial role". Replace them with plain words.
5. Prefer the active voice and concrete nouns. Cut hedging and filler.
6. Keep a natural, slightly imperfect rhythm - the occasional short fragment or \
aside is good. Do not make it sound like a polished corporate memo.
7. Preserve the original language, tone target, paragraph breaks, and any \
markdown or lists.

Output ONLY the rewritten text. No preamble, no quotes, no explanation."""


@dataclass
class LLMConfig:
    engine: str = "ollama"  # "ollama" or "openai"
    model: str = "qwen2.5:14b-instruct"
    base_url: str = "http://localhost:11434"
    api_key: str = "not-needed"  # local servers ignore this
    temperature: float = 0.8
    top_p: float = 0.95
    timeout: int = 300
    num_ctx: int = 8192  # Ollama context window


class LLMError(RuntimeError):
    pass


class LocalLLM:
    """A thin client over a locally-hosted chat model."""

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or LLMConfig()

    # -- low level HTTP ----------------------------------------------------
    def _post(self, url: str, payload: dict) -> dict:
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise LLMError(
                f"Could not reach the local model at {url}. "
                f"Is your server running?  ({exc})"
            ) from exc

    def _get(self, url: str) -> dict:
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise LLMError(f"Could not reach {url}: {exc}") from exc

    # -- health / discovery ------------------------------------------------
    def is_available(self) -> bool:
        """True if the configured server responds."""
        try:
            self.list_models()
            return True
        except LLMError:
            return False

    def list_models(self) -> list[str]:
        """Return the model names the local server has loaded/available."""
        cfg = self.config
        if cfg.engine == "ollama":
            data = self._get(f"{cfg.base_url}/api/tags")
            return [m["name"] for m in data.get("models", [])]
        data = self._get(f"{cfg.base_url}/v1/models")
        return [m["id"] for m in data.get("data", [])]

    # -- generation --------------------------------------------------------
    def chat(self, system: str, user: str) -> str:
        """Send one system+user turn and return the assistant text."""
        cfg = self.config
        if cfg.engine == "ollama":
            payload = {
                "model": cfg.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "options": {
                    "temperature": cfg.temperature,
                    "top_p": cfg.top_p,
                    "num_ctx": cfg.num_ctx,
                },
            }
            data = self._post(f"{cfg.base_url}/api/chat", payload)
            msg = data.get("message", {}).get("content")
            if msg is None:
                raise LLMError(f"Unexpected Ollama response: {data}")
            return msg.strip()

        # OpenAI-compatible
        payload = {
            "model": cfg.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": cfg.temperature,
            "top_p": cfg.top_p,
            "stream": False,
        }
        data = self._post(f"{cfg.base_url}/v1/chat/completions", payload)
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected OpenAI-compatible response: {data}") from exc

    def humanize(self, text: str) -> str:
        """Rewrite ``text`` using the humanizer system prompt."""
        return self.chat(SYSTEM_PROMPT, text)
