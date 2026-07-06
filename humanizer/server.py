"""A tiny, dependency-free web UI served from the standard library.

Run it with::

    python -m humanizer --serve

then open http://localhost:8000 .  You get a text box + drag-and-drop for
.docx/.txt/.md, a live AI-likeness score before and after, and a download
button.  All processing happens locally; the only network traffic is between
this server and your own LLM (Ollama / LM Studio) on localhost.
"""

from __future__ import annotations

import base64
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import extract
from .humanize import humanize
from .llm import LLMConfig, LocalLLM
from .score import verdict

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Humanizer</title>
<style>
  :root{
    --bg:#0f1115; --panel:#171a21; --panel2:#1e222b; --line:#2a2f3a;
    --text:#e7e9ee; --muted:#9aa3b2; --accent:#7c9cff; --good:#4ade80;
    --warn:#fbbf24; --bad:#f87171; --radius:14px;
  }
  @media (prefers-color-scheme: light){
    :root{ --bg:#f4f5f8; --panel:#ffffff; --panel2:#f0f2f6; --line:#e2e5ea;
      --text:#1a1d24; --muted:#5b6472; }
  }
  *{box-sizing:border-box}
  body{margin:0;font:15px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
    background:var(--bg);color:var(--text)}
  header{padding:22px 24px;border-bottom:1px solid var(--line);display:flex;
    align-items:baseline;gap:12px;flex-wrap:wrap}
  header h1{margin:0;font-size:20px;letter-spacing:.2px}
  header .tag{color:var(--muted);font-size:13px}
  .status{margin-left:auto;font-size:13px;color:var(--muted);display:flex;
    align-items:center;gap:8px}
  .dot{width:9px;height:9px;border-radius:50%;background:var(--muted)}
  .dot.on{background:var(--good)} .dot.off{background:var(--bad)}
  main{max-width:1100px;margin:0 auto;padding:24px;display:grid;
    grid-template-columns:1fr 1fr;gap:20px}
  @media (max-width:860px){main{grid-template-columns:1fr}}
  .panel{background:var(--panel);border:1px solid var(--line);
    border-radius:var(--radius);padding:16px}
  .panel h2{margin:0 0 10px;font-size:13px;text-transform:uppercase;
    letter-spacing:.08em;color:var(--muted)}
  textarea{width:100%;min-height:300px;resize:vertical;background:var(--panel2);
    color:var(--text);border:1px solid var(--line);border-radius:10px;
    padding:12px;font:14px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace}
  .drop{margin-top:10px;border:1.5px dashed var(--line);border-radius:10px;
    padding:14px;text-align:center;color:var(--muted);font-size:13px;cursor:pointer}
  .drop.hover{border-color:var(--accent);color:var(--accent)}
  .controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:16px 0}
  select,input,button{font:inherit;color:var(--text);background:var(--panel2);
    border:1px solid var(--line);border-radius:9px;padding:9px 11px}
  button.go{background:var(--accent);color:#0b0e14;border:none;font-weight:600;
    padding:10px 20px;cursor:pointer}
  button.go:disabled{opacity:.5;cursor:not-allowed}
  button.ghost{cursor:pointer}
  .row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
  .meter{display:flex;flex-direction:column;gap:6px;margin:6px 0 14px}
  .meter .barwrap{height:10px;background:var(--panel2);border-radius:6px;overflow:hidden}
  .meter .bar{height:100%;width:0;transition:width .5s}
  .meter .lab{display:flex;justify-content:space-between;font-size:13px}
  .verdict{font-weight:600}
  .scores{display:grid;grid-template-columns:1fr 1fr;gap:16px}
  .notes{font-size:12.5px;color:var(--muted);margin:8px 0 0;padding-left:16px}
  .warn{color:var(--warn);font-size:13px;margin-top:8px}
  .foot{grid-column:1/-1;color:var(--muted);font-size:12.5px;text-align:center;
    padding:6px 0 0}
  .adv{font-size:12.5px;color:var(--muted);margin-top:10px}
  .adv summary{cursor:pointer}
  .adv .grid{display:grid;grid-template-columns:auto 1fr;gap:8px 10px;margin-top:10px;
    align-items:center}
  .spin{display:inline-block;width:14px;height:14px;border:2px solid #0b0e14;
    border-top-color:transparent;border-radius:50%;animation:s .7s linear infinite;
    vertical-align:-2px}
  @keyframes s{to{transform:rotate(360deg)}}
</style>
</head>
<body>
<header>
  <h1>Humanizer</h1>
  <span class="tag">local &middot; private &middot; runs on your GPU</span>
  <div class="status"><span id="dot" class="dot"></span><span id="statusText">checking model…</span></div>
</header>
<main>
  <section class="panel">
    <h2>Input</h2>
    <textarea id="input" placeholder="Paste AI-written text here, or drop a .docx / .txt / .md file below…"></textarea>
    <div id="drop" class="drop">Drop a .docx, .txt or .md file here &middot; or click to browse</div>
    <input id="file" type="file" accept=".docx,.txt,.md,.markdown" hidden>
    <div class="controls">
      <select id="mode" title="Pipeline mode">
        <option value="hybrid">Hybrid (LLM + cleanup) — best</option>
        <option value="llm">LLM only</option>
        <option value="rules">Rules only (no model needed)</option>
      </select>
      <button id="go" class="go">Humanize</button>
      <span id="modeInfo" class="tag"></span>
    </div>
    <details class="adv">
      <summary>Model settings</summary>
      <div class="grid">
        <label>Engine</label>
        <select id="engine">
          <option value="ollama">Ollama (localhost:11434)</option>
          <option value="openai">OpenAI-compatible (LM Studio, llama.cpp…)</option>
        </select>
        <label>Model</label><input id="model" value="qwen2.5:14b-instruct">
        <label>Server URL</label><input id="baseUrl" placeholder="(default per engine)">
        <label>Temperature</label><input id="temp" type="number" step="0.05" value="0.8" style="width:90px">
      </div>
    </details>
    <div id="warns"></div>
  </section>

  <section class="panel">
    <h2>Humanized output</h2>
    <textarea id="output" placeholder="Result appears here…"></textarea>
    <div class="controls">
      <button id="copy" class="ghost">Copy</button>
      <button id="dl" class="ghost">Download .txt</button>
      <button id="dldocx" class="ghost">Download .docx</button>
    </div>
    <div class="scores">
      <div><div class="lab" style="font-size:13px;color:var(--muted)">BEFORE</div>
        <div class="meter"><div class="barwrap"><div id="bBar" class="bar"></div></div>
        <div class="lab"><span id="bScore">–</span><span id="bVerdict" class="verdict"></span></div></div></div>
      <div><div class="lab" style="font-size:13px;color:var(--muted)">AFTER</div>
        <div class="meter"><div class="barwrap"><div id="aBar" class="bar"></div></div>
        <div class="lab"><span id="aScore">–</span><span id="aVerdict" class="verdict"></span></div></div></div>
    </div>
    <ul id="notes" class="notes"></ul>
  </section>
  <div class="foot">AI-likeness is a local heuristic to gauge before/after — it is not an AI detector, and no tool can guarantee any detector's verdict.</div>
</main>
<script>
const $ = id => document.getElementById(id);
let uploaded = null; // {name, b64}

function color(v){ return v>=60?'var(--bad)':v>=35?'var(--warn)':'var(--good)'; }
function setMeter(bar, scoreEl, verdictEl, val, verdictText){
  bar.style.width = val + '%'; bar.style.background = color(val);
  scoreEl.textContent = val.toFixed(0) + ' / 100';
  verdictEl.textContent = verdictText; verdictEl.style.color = color(val);
}

async function refreshStatus(){
  const p = new URLSearchParams({engine:$('engine').value, model:$('model').value,
    base_url:$('baseUrl').value});
  try{
    const r = await fetch('/api/status?'+p); const d = await r.json();
    if(d.available){ $('dot').className='dot on';
      $('statusText').textContent = d.models.length? ('model ready — '+d.models.length+' available'):'server up';
    } else { $('dot').className='dot off'; $('statusText').textContent='no local model (rules still work)'; }
  }catch(e){ $('dot').className='dot off'; $('statusText').textContent='server error'; }
}

// file handling
const drop = $('drop');
drop.onclick = ()=> $('file').click();
$('file').onchange = e => { if(e.target.files[0]) loadFile(e.target.files[0]); };
['dragover','dragenter'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.add('hover');}));
['dragleave','drop'].forEach(ev=>drop.addEventListener(ev,e=>{e.preventDefault();drop.classList.remove('hover');}));
drop.addEventListener('drop', e=>{ if(e.dataTransfer.files[0]) loadFile(e.dataTransfer.files[0]); });

function loadFile(f){
  const reader = new FileReader();
  if(f.name.toLowerCase().endsWith('.docx')){
    reader.onload = () => { uploaded = {name:f.name, b64: reader.result.split(',')[1]};
      $('input').value = '(loaded '+f.name+' — click Humanize)'; $('input').dataset.file='1'; };
    reader.readAsDataURL(f);
  } else {
    reader.onload = () => { uploaded=null; $('input').value = reader.result; $('input').dataset.file=''; };
    reader.readAsText(f);
  }
}
$('input').addEventListener('input', ()=>{ uploaded=null; $('input').dataset.file=''; });

$('go').onclick = async () => {
  const btn=$('go'); const orig=btn.innerHTML;
  btn.disabled=true; btn.innerHTML='<span class="spin"></span> working…';
  $('warns').innerHTML='';
  const body = { mode:$('mode').value, engine:$('engine').value, model:$('model').value,
    base_url:$('baseUrl').value, temperature:parseFloat($('temp').value) };
  if(uploaded){ body.file_b64=uploaded.b64; body.filename=uploaded.name; }
  else { body.text = $('input').value; }
  try{
    const r = await fetch('/api/humanize', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(body)});
    const d = await r.json();
    if(d.error){ $('warns').innerHTML='<div class="warn">'+d.error+'</div>'; }
    else {
      $('output').value = d.humanized;
      setMeter($('bBar'),$('bScore'),$('bVerdict'), d.before.ai_like, d.before_verdict);
      setMeter($('aBar'),$('aScore'),$('aVerdict'), d.after.ai_like, d.after_verdict);
      $('notes').innerHTML = (d.after.notes||[]).map(n=>'<li>'+n+'</li>').join('');
      if(d.warnings && d.warnings.length)
        $('warns').innerHTML = d.warnings.map(w=>'<div class="warn">'+w+'</div>').join('');
      $('modeInfo').textContent = 'ran: '+d.mode;
    }
  }catch(e){ $('warns').innerHTML='<div class="warn">Request failed: '+e+'</div>'; }
  btn.disabled=false; btn.innerHTML=orig;
};

$('copy').onclick = ()=> navigator.clipboard.writeText($('output').value);
function download(name, blob){ const a=document.createElement('a');
  a.href=URL.createObjectURL(blob); a.download=name; a.click(); }
$('dl').onclick = ()=> download('humanized.txt', new Blob([$('output').value],{type:'text/plain'}));
$('dldocx').onclick = async ()=>{
  const r = await fetch('/api/docx',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({text:$('output').value})});
  download('humanized.docx', await r.blob());
};

['engine','model','baseUrl'].forEach(id=>$(id).addEventListener('change', refreshStatus));
refreshStatus();
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep the console quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
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

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path.startswith("/api/status"):
            from urllib.parse import parse_qs, urlparse

            q = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            llm = self._llm_from(q)
            try:
                models = llm.list_models()
                self._json(200, {"available": True, "models": models})
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
        from .writeback import write_docx
        import io
        import zipfile

        d = self._read_json()
        text = d.get("text", "")
        # Build the docx in memory.
        buf = io.BytesIO()
        # Reuse write_docx by writing to a temp path is avoided; inline zip:
        from .writeback import _CONTENT_TYPES, _RELS, _DOC_HEAD, _DOC_TAIL, _paragraph_xml

        paragraphs = "".join(_paragraph_xml(line) for line in text.split("\n"))
        document = _DOC_HEAD + paragraphs + _DOC_TAIL
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
            zf.writestr("_rels/.rels", _RELS)
            zf.writestr("word/document.xml", document)
        self._send(
            200,
            buf.getvalue(),
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
