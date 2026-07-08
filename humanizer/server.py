"""A tiny, dependency-free web server for the Humanizer UI.

Run it with::

    python -m humanizer --serve

then open http://localhost:8000 .  The front-end (an immersive single page with
a live 3D neural-network animation, drag-and-drop upload and animated score
rings) lives in ``humanizer/web/index.html`` and is served from disk.  All
processing happens locally; the only network traffic is between this server and
your own LLM (Ollama / LM Studio) on localhost.
"""

from __future__ import annotations

import base64
import io
import json
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import extract
from .humanize import humanize
from .llm import LLMConfig, LocalLLM
from .score import verdict
from .writeback import _CONTENT_TYPES, _DOC_HEAD, _DOC_TAIL, _RELS, _paragraph_xml

_WEB_DIR = Path(__file__).resolve().parent / "web"

# Minimal fallback shown only if web/index.html is somehow missing.
_FALLBACK = (
    "<!doctype html><meta charset=utf-8><title>Humanizer</title>"
    "<body style='font:16px system-ui;background:#05060e;color:#eee;padding:40px'>"
    "<h1>Humanizer</h1><p>web/index.html was not found. Use the CLI instead:</p>"
    "<pre>python -m humanizer yourfile.docx</pre></body>"
)


def _load_page() -> bytes:
    index = _WEB_DIR / "index.html"
    try:
        return index.read_bytes()
    except OSError:
        return _FALLBACK.encode("utf-8")


def _build_docx_bytes(text: str) -> bytes:
    """Assemble a valid .docx in memory from newline-separated paragraphs."""
    paragraphs = "".join(_paragraph_xml(line) for line in text.split("\n"))
    document = _DOC_HEAD + paragraphs + _DOC_TAIL
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr("_rels/.rels", _RELS)
        zf.writestr("word/document.xml", document)
    return buf.getvalue()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the console quiet
        pass

    # -- response helpers --------------------------------------------------
    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: dict):
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    def _llm_from(self, d: dict) -> LocalLLM:
        engine = d.get("engine", "ollama")
        base = d.get("base_url") or (
            "http://localhost:11434" if engine == "ollama" else "http://localhost:1234"
        )
        return LocalLLM(
            LLMConfig(
                engine=engine,
                model=d.get("model", "qwen2.5:14b-instruct"),
                base_url=base,
                temperature=float(d.get("temperature", 0.8)),
            )
        )

    # -- routes ------------------------------------------------------------
    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, _load_page(), "text/html; charset=utf-8")
        elif self.path.startswith("/api/status"):
            from urllib.parse import parse_qs, urlparse

            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            llm = self._llm_from(q)
            try:
                self._json(200, {"available": True, "models": llm.list_models()})
            except Exception:
                self._json(200, {"available": False, "models": []})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        try:
            if self.path == "/api/humanize":
                self._handle_humanize()
            elif self.path == "/api/docx":
                self._handle_docx()
            else:
                self._json(404, {"error": "not found"})
        except Exception as exc:  # never crash the server on a bad request
            self._json(500, {"error": f"{type(exc).__name__}: {exc}"})

    def _handle_humanize(self):
        d = self._read_json()
        if d.get("file_b64"):
            raw = base64.b64decode(d["file_b64"])
            text = extract.extract_bytes(raw, d.get("filename", "upload.txt"))
        else:
            text = d.get("text", "")
        if not text.strip():
            self._json(400, {"error": "No input text."})
            return

        result = humanize(text, mode=d.get("mode", "hybrid"), llm=self._llm_from(d))
        self._json(
            200,
            {
                "humanized": result.humanized,
                "mode": result.mode,
                "before": result.before.as_dict(),
                "after": result.after.as_dict(),
                "before_verdict": verdict(result.before.ai_like),
                "after_verdict": verdict(result.after.ai_like),
                "warnings": result.warnings,
                "summary": result.summary(),
            },
        )

    def _handle_docx(self):
        d = self._read_json()
        body = _build_docx_bytes(d.get("text", ""))
        self._send(
            200,
            body,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )


def serve(port: int = 8000, host: str = "127.0.0.1"):
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Humanizer UI running at http://{host}:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.shutdown()
