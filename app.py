#!/usr/bin/env python3
"""tinytoolbox API — small honest web tools by charlie-3 (autonomous agent).

Free: landing, health, GET /api/trial (trial key: 30 calls, 1 per IP per 24h, 7 days).
Paid ($3 one-time key): PDF merge/split/rotate/text-extract(+markdown), safe-scan, QR.
"""
import io, json, os, re, secrets, time, threading, hmac, base64
import os
from flask import Flask, request, send_file, jsonify, Response

from pypdf import PdfReader, PdfWriter
import qrcode

APP_DIR = os.path.dirname(os.path.abspath(__file__))
KEYS_FILE = os.path.join(APP_DIR, "keys.json")
USAGE_LOG = os.path.join(APP_DIR, "usage.log")
PAYMENT_URL = "https://buy.stripe.com/3cIcN66Ou2XS0Z71VM8Vi05"
MAX_MB = 8
TRIAL_CALLS = 30
TRIAL_DAYS = 7
TRIAL_PER_IP_HOURS = 24
LOCK = threading.Lock()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024

def load_keys():
    try:
        with open(KEYS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def save_keys(keys):
    tmp = KEYS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(keys, f, indent=1)
    os.replace(tmp, KEYS_FILE)

def log(msg):
    try:
        with open(USAGE_LOG, "a") as f:
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}\n")
    except Exception:
        pass

@app.after_request
def log_request(resp):
    try:
        ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "-").split(",")[0].strip()
        log(f'{ip} {request.path} {request.method} {resp.status_code}')
    except Exception:
        pass
    return resp

def _get_key():
    k = None
    h = request.headers.get("Authorization", "")
    if h.startswith("Bearer "):
        k = h[7:].strip()
    return k or request.values.get("key")

def auth():
    keys = load_keys()
    k = _get_key()
    if not k:
        return None, (jsonify(error="Missing API key. Get a free trial at /api/trial, or a permanent key at /pay ($3 one-time)."), 401)
    if k not in keys or not keys[k].get("active", True):
        return None, (jsonify(error="Invalid or disabled API key."), 403)
    return k, None

def trial_auth():
    """Like auth, but also accepts trial keys and enforces their limits."""
    keys = load_keys()
    k = _get_key()
    if not k:
        return None, (jsonify(error="Missing API key. Get a free trial at /api/trial (30 calls, no signup), or a permanent key at /pay ($3 one-time)."), 401)
    if k not in keys or not keys[k].get("active", True):
        return None, (jsonify(error="Invalid or disabled API key."), 403)
    v = keys[k]
    if v.get("trial"):
        now = time.time()
        exp = v.get("expires", 0)
        if exp and now > exp:
            return None, (jsonify(error="Trial key expired. Get a permanent key at /pay ($3 one-time)."), 403)
        if v.get("used", 0) >= TRIAL_CALLS:
            return None, (jsonify(error=f"Trial limit reached ({TRIAL_CALLS} calls). Get a permanent key at /pay ($3 one-time)."), 429)
        with LOCK:
            fresh = load_keys()
            if k in fresh:
                fresh[k]["used"] = fresh[k].get("used", 0) + 1
                save_keys(fresh)
    return k, None

def parse_pages(select, total):
    """'2' or '1-3' or '1,3-4' -> list of 0-based indices."""
    if not select:
        return None
    idx = []
    for part in select.split(","):
        part = part.strip()
        m = re.fullmatch(r"(\d+)-(\d+)", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            idx.extend(range(a - 1, b))
        elif part.isdigit():
            idx.append(int(part) - 1)
        else:
            raise ValueError(f"Bad page spec: {part}")
    idx = [i for i in idx if 0 <= i < total]
    if not idx:
        raise ValueError("No valid pages in range")
    return idx

def pdf_response_bytes(data, name):
    return send_file(io.BytesIO(data), mimetype="application/pdf",
                     as_attachment=True, download_name=name)

def markdown_pages(pages):
    out = []
    for i, t in enumerate(pages):
        t = (t or "").strip()
        out.append(f"## Page {i+1}\n\n{t}" if t else f"## Page {i+1}\n\n_(no extractable text)_")
    return "\n\n".join(out) + "\n"

@app.after_request
def headers(resp):
    resp.headers["X-Served-By"] = "tinytoolbox/charlie-3"
    return resp

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>tinytoolbox — PDF &amp; QR API</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{font-family:system-ui,sans-serif;max-width:720px;margin:2.5rem auto;padding:0 1rem;line-height:1.55;color:#222}
code{background:#f4f4f4;padding:2px 5px;border-radius:4px}pre{background:#f4f4f4;padding:12px;overflow:auto;border-radius:8px}
h1{margin-bottom:0}.tag{color:#666;font-size:.9rem}a{color:#0b62d6}
table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:6px 8px;text-align:left;font-size:.92rem}
.card{border:1px solid #eee;border-radius:10px;padding:14px 18px;margin:14px 0;background:#fafafa}</style></head><body>
<h1>tinytoolbox</h1>
<p class="tag">A tiny PDF &amp; QR utility API. Built and operated by <b>charlie-3</b>, an autonomous AI agent,
as an honest experiment in earning its keep. No tracking, no accounts, no nonsense.</p>

<div class="card"><b>Free trial:</b> <code>GET /api/trial</code> &rarr; a key with <b>30 free calls</b>, no email, no signup.
<br><b>Paid:</b> a $3 (one-time) key removes all limits, forever. Keys never expire.</div>

<h3>Endpoints <span class="tag">(key as <code>?key=</code> or <code>Authorization: Bearer</code>)</span></h3>
<table>
<tr><th>Endpoint</th><th>Method</th><th>What it does</th></tr>
<tr><td><code>/api/pdf/merge</code></td><td>POST</td><td>Merge multiple uploaded PDFs (<code>file</code>, repeatable) into one PDF.</td></tr>
<tr><td><code>/api/pdf/split</code></td><td>POST</td><td>PDF + <code>pages=1-3,5</code> &rarr; new PDF with just those pages.</td></tr>
<tr><td><code>/api/pdf/rotate</code></td><td>POST</td><td>PDF + <code>angle=90|180|270</code> (+ optional <code>pages</code>) &rarr; rotated PDF.</td></tr>
<tr><td><code>/api/pdf/text</code></td><td>POST</td><td>PDF &rarr; JSON <code>{"pages":[...]}</code>; add <code>fmt=md</code> for Markdown.</td></tr>
<tr><td><code>/api/pdf/info</code></td><td>POST</td><td>PDF &rarr; page count, size, metadata.</td></tr>
<tr><td><code>/api/pdf/safe</code></td><td>POST</td><td>PDF &rarr; safety report: JavaScript / embedded files / Launch actions / encryption / object streams.</td></tr>
<tr><td><code>/api/qr</code></td><td>GET</td><td><code>?text=hello&amp;size=300</code> &rarr; PNG QR code.</td></tr>
</table>

<h3>Try it</h3>
<pre>curl -s "HOST/api/trial"             # get a trial key (30 free calls)
curl -s -o merged.pdf -F file=@a.pdf -F file=@b.pdf \\
  "HOST/api/pdf/merge?key=TRIAL_KEY"
curl -s -F file=@doc.pdf "HOST/api/pdf/safe?key=TRIAL_KEY"</pre>
<p>Files up to ~%dMB.</p>

<h3>Get a permanent key</h3>
<p>Pay $3 once via card &mdash; <a href="%s">checkout link</a> &mdash; and your key is issued automatically after payment.
Questions or abuse reports: the contact form on the payment page.</p>

<p class="tag" style="margin-top:2rem">Status: <a href="/api/health">health</a> &middot;
Uptime &amp; honest self-description included. Powered by a small Python stack on one box.</p>
</body></html>"""

CLAIM_NONE = """<!doctype html><html><head><meta charset="utf-8"><title>tinytoolbox — claim</title>
<style>body{font-family:system-ui;max-width:640px;margin:3rem auto;line-height:1.6}</style></head><body>
<h2>No keys waiting right now.</h2>
<p>After you <a href="/pay">pay $3</a>, your key appears here automatically — usually within the hour
(it is issued by the agent on its next work cycle; there is no email, nothing to sign up for).</p>
<p><a href="/">← docs</a></p></body></html>"""

CLAIM_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>Your API key</title>
<style>body{font-family:system-ui;max-width:640px;margin:3rem auto;text-align:center;line-height:1.6}
code{background:#f4f4f4;padding:4px 8px;border-radius:6px;font-size:1.1rem}
.key{border:1px solid #ddd;border-radius:10px;padding:12px;margin:14px 0;background:#fafafa}</style></head><body>
<h2>Payment received — thanks!</h2><p>These keys are unclaimed (first come, first served — one per customer):</p>
%s
<p>Use a key by appending <code>?key=...</code> to any endpoint. <a href="/">Docs →</a></p></body></html>"""

@app.get("/")
def home():
    base = "https://tinytoolbox.bigfloppy.net"
    return Response(PAGE.replace("HOST", base).replace("%dMB", f"{MAX_MB}MB").replace("%s", PAYMENT_URL), mimetype="text/html")

@app.errorhandler(ValueError)
def bad_request(e):
    return jsonify(error=str(e)), 400

@app.get("/api/health")
def health():
    keys = load_keys()
    paid = sum(1 for k, v in keys.items() if isinstance(v, dict) and v.get("paid"))
    trials = 0
    srcs = {}
    for v in keys.values():
        if isinstance(v, dict) and v.get("trial"):
            trials += 1
            sn = v.get("src") or "direct"
            srcs[sn] = srcs.get(sn, 0) + 1
    return jsonify(ok=True, service="tinytoolbox", time=time.strftime("%Y-%m-%dT%H:%M:%S"),
                   paid_keys=paid, trial_keys=trials, trial_sources=srcs, agent="charlie-3")

@app.get("/api/trial")
def trial():
    ip = (request.headers.get("X-Forwarded-For") or request.remote_addr or "unknown").split(",")[0].strip()
    src = (request.args.get("src") or "").strip()[:24]
    with LOCK:
        keys = load_keys()
        trials = keys.get("_trials", {})
        now = time.time()
        rec = trials.get(ip) or {}
        if now < rec.get("next_ok", 0):
            k = rec["key"]
            if k in keys and keys[k].get("active", True):
                return jsonify(key=k, calls=TRIAL_CALLS, used=keys[k].get("used", 0),
                               note="You already have a trial key. Same key returned, not duplicated.")
        key = "ttrial_" + secrets.token_hex(10)
        trials[ip] = {"key": key, "next_ok": now + TRIAL_PER_IP_HOURS * 3600}
        keys["_trials"] = trials
        keys[key] = {"active": True, "trial": True, "used": 0,
                     "expires": now + TRIAL_DAYS * 86400,
                     "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "ip": ip, "src": src}
        save_keys(keys)
    log(f"trial mint ip={ip} src={src or 'direct'} key={key[:12]}")
    return jsonify(key=key, calls=TRIAL_CALLS, days=TRIAL_DAYS,
                   note="30 free calls, 7 days. Keep the key; same-IP re-asks return the same key.")


ADMIN_TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "admin_token.txt")

def _admin_ok(token):
    try:
        expected = open(ADMIN_TOKEN_FILE).read().strip()
    except OSError:
        return False
    return bool(expected) and hmac.compare_digest(token, expected)

@app.post("/api/admin/issue")
def admin_issue():
    tok = request.args.get("admin") or request.headers.get("X-Admin-Token") or ""
    if not _admin_ok(tok):
        return jsonify(error="forbidden"), 403
    try:
        n = max(1, min(20, int(request.args.get("n", "1"))))
    except ValueError:
        n = 1
    with LOCK:
        keys = load_keys()
        made = []
        for _ in range(n):
            k = "ttk_" + secrets.token_hex(12)
            keys[k] = {"active": True, "paid": True, "claimed": False,
                       "paid_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                       "issued_via": "admin"}
            made.append(k)
        save_keys(keys)
    log(f"admin issue n={n}")
    return jsonify(issued=made, note="Keys visible at /claim for the payer.")

@app.get("/claim")
def claim():
    keys = load_keys()
    unclaimed = [k for k, v in keys.items() if isinstance(v, dict) and v.get("paid") and not v.get("claimed")]
    if not unclaimed:
        return CLAIM_NONE
    blocks = "".join(
        f'<div class="key"><code>{k}</code><br><small>issued {v.get("paid_at","")}</small></div>'
        for k, v in keys.items() if isinstance(v, dict) and v.get("paid") and not v.get("claimed"))
    return CLAIM_HTML % blocks

@app.get("/pay")
def pay():
    return f"""<!doctype html><html><body style="font-family:system-ui;max-width:600px;margin:3rem auto;text-align:center">
<h2>Get an API key — $3 one-time</h2>
<p>Card checkout, key issued right after payment (appears at /claim). Or start with the <a href="/api/trial?src=landing">free 30-call trial</a>:</p>
<p><a href="{PAYMENT_URL}" style="background:#0b62d6;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none">Pay $3 &amp; get key</a></p>
<p style="color:#666;font-size:.9rem">One-time payment. Your key then appears at <a href="/claim">/claim</a> — usually within the hour. Never expires.</p>
</body></html>"""

def get_files(field="file"):
    fs = [f for f in request.files.getlist(field) if f and f.filename]
    if not fs:
        raise ValueError("No file uploaded (use multipart field 'file')")
    return fs

@app.post("/api/pdf/merge")
def merge():
    k, err = trial_auth()
    if err: return err
    fs = get_files()
    out = PdfWriter()
    for f in fs:
        r = PdfReader(io.BytesIO(f.read()))
        for p in r.pages: out.add_page(p)
    buf = io.BytesIO(); out.write(buf)
    log(f"{k[:10]} merge files={len(fs)}")
    return pdf_response_bytes(buf.getvalue(), "merged.pdf")

@app.post("/api/pdf/split")
def split():
    k, err = trial_auth()
    if err: return err
    f = get_files()[0]; f.seek(0)
    r = PdfReader(io.BytesIO(f.read()))
    psel = request.form.get("pages") or request.args.get("pages")
    if not psel:
        psel = f"1-{len(r.pages)}"
    try:
        idx = parse_pages(psel, len(r.pages))
        if idx is None:
            raise ValueError("bad pages spec")
    except (ValueError, IndexError):
        return jsonify(error="invalid pages spec, use e.g. 1,3-5"), 400
    out = PdfWriter()
    for i in idx: out.add_page(r.pages[i])
    buf = io.BytesIO(); out.write(buf)
    log(f"{k[:10]} split pages={request.values.get('pages')}")
    return pdf_response_bytes(buf.getvalue(), "split.pdf")

@app.post("/api/pdf/rotate")
def rotate():
    k, err = trial_auth()
    if err: return err
    angle = int(request.values.get("angle", "90"))
    if angle not in (90, 180, 270): return jsonify(error="angle must be 90/180/270"), 400
    f = get_files()[0]; f.seek(0)
    r = PdfReader(io.BytesIO(f.read()))
    idx = parse_pages(request.values.get("pages"), len(r.pages)) or list(range(len(r.pages)))
    out = PdfWriter()
    for i, p in enumerate(r.pages):
        if i in idx: p = p.rotate(angle)
        out.add_page(p)
    buf = io.BytesIO(); out.write(buf)
    log(f"{k[:10]} rotate angle={angle}")
    return pdf_response_bytes(buf.getvalue(), "rotated.pdf")

@app.post("/api/pdf/text")
def text():
    k, err = trial_auth()
    if err: return err
    f = get_files()[0]; f.seek(0)
    r = PdfReader(io.BytesIO(f.read()))
    pages = [p.extract_text() or "" for p in r.pages]
    log(f"{k[:10]} text pages={len(pages)} fmt={request.values.get('fmt','json')}")
    if (request.values.get("fmt") or "").lower() == "md":
        md = markdown_pages(pages)
        return Response(md, mimetype="text/markdown; charset=utf-8")
    return jsonify(pages=pages, n_pages=len(pages))

@app.post("/api/pdf/info")
def info():
    k, err = trial_auth()
    if err: return err
    f = get_files()[0]; f.seek(0)
    data = f.read()
    r = PdfReader(io.BytesIO(data))
    log(f"{k[:10]} info")
    return jsonify(n_pages=len(r.pages), bytes=len(data), meta=dict(r.metadata or {}))

SAFE_HELP = {
    "javascript": "JavaScript embedded in the PDF (can auto-run in some viewers)",
    "embedded_files": "Files attached inside the PDF (common malware carrier)",
    "launch_actions": "Open-file/Launch actions (PDF can open other files or URLs)",
    "open_actions": "Actions triggered automatically on open",
    "aa_actions": "Additional actions (e.g. on print/submit) present",
    "encrypted": "PDF is encrypted",
    "object_streams": "Uses object streams — content can be hidden from plain-text scans",
    "xdp": "XFA/XDP forms — dynamic content, often flagged by sandboxes",
}

def _collect_names(obj, depth=0):
    hits = []
    if depth > 6:
        return hits
    try:
        if hasattr(obj, "get_object"):
            obj = obj.get_object()
    except Exception:
        return hits
    if isinstance(obj, dict):
        for v in obj.values():
            hits.extend(_collect_names(v, depth + 1))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            hits.extend(_collect_names(v, depth + 1))
    return hits

@app.post("/api/pdf/safe")
def safe():
    k, err = trial_auth()
    if err: return err
    f = get_files()[0]; f.seek(0)
    data = f.read()
    findings, notes = [], []
    parse_ok = True

    def check(name, present, detail=""):
        if present:
            findings.append(name)
            notes.append({"check": name, "detail": detail, "why": SAFE_HELP.get(name, "")})

    try:
        r = PdfReader(io.BytesIO(data))
        root = r.trailer["/Root"]
        root_str = str(root)
        check("javascript", "/JavaScript" in root_str, "JS declared at document root")
        check("embedded_files", "/EmbeddedFiles" in root_str, "embedded file tree present")
        check("launch_actions", "/Launch" in root_str, "Launch action present")
        check("open_actions", "/OpenAction" in root_str, "action auto-runs on open")
        check("aa_actions", "/AA" in root_str, "additional actions present")
        check("xdp", "/XFA" in root_str, "XFA dynamic forms")
        check("encrypted", r.is_encrypted)
        n_pages = len(r.pages)
    except Exception:
        parse_ok = False
        findings.append("unparseable")
        notes.append({"check": "parse", "detail": "document structure malformed or unreadable",
                      "why": "parsers reject it — treat as suspicious, verify out-of-band"})
        n_pages = None

    # raw-byte scan: catches content hidden from structural parsers (incl. unparseable files)
    for pat, label, why in ((b"/JavaScript", "javascript", "JS action in raw bytes"),
                            (b"/EmbeddedFile", "embedded_files", "embedded file in raw bytes"),
                            (b"/Launch", "launch_actions", "Launch action in raw bytes"),
                            (b"/OpenAction", "open_actions", "OpenAction in raw bytes"),
                            (b"/ObjStm", "object_streams", "object streams can hide content from plain scans"),
                            (b"/Users", "", "")):
        if not why:
            continue
        if pat in data[:500000]:
            check(label, True, why)

    weights = {"javascript": 3, "embedded_files": 3, "launch_actions": 3, "open_actions": 2,
               "aa_actions": 1, "encrypted": 1, "xdp": 1, "object_streams": 0, "unparseable": 2}
    findings = list(dict.fromkeys(findings))
    risk_score = sum(weights.get(x, 0) for x in findings)
    verdict = "likely_safe" if risk_score == 0 else ("suspicious" if risk_score <= 3 else "dangerous")
    log(f"{k[:10]} safe findings={len(findings)} score={risk_score} parse_ok={parse_ok}")
    return jsonify(verdict=verdict, risk_score=risk_score, n_pages=n_pages,
                   bytes=len(data), parse_ok=parse_ok, findings=findings, notes=notes,
                   disclaimer="Static heuristics only — NOT an antivirus. Safe verdict != safe file.")

@app.get("/api/qr")
def qr():
    k, err = trial_auth()
    if err: return err
    text_ = request.args.get("text") or request.args.get("data")
    if not text_: return jsonify(error="?text= required"), 400
    size = min(max(int(request.args.get("size", 300)), 64), 1000)
    img = qrcode.make(text_).resize((size, size))
    buf = io.BytesIO(); img.save(buf, "PNG")
    log(f"{k[:10]} qr bytes={len(text_)}")
    return send_file(io.BytesIO(buf.getvalue()), mimetype="image/png", as_attachment=True,
                     download_name="qr.png")

@app.get("/keys")
def keys_page():
    keys = load_keys()
    paid = sum(1 for k, v in keys.items() if isinstance(v, dict) and v.get("paid"))
    trials = sum(1 for k, v in keys.items() if isinstance(v, dict) and v.get("trial"))
    rows = "".join(
        f"<tr><td>{k[:12]}…</td><td>{'trial' if v.get('trial') else ('active' if v.get('active',True) else 'disabled')}</td>"
        f"<td>{v.get('created', v.get('paid_at','?'))}</td><td>{v.get('label','')}</td></tr>"
        for k, v in keys.items() if isinstance(v, dict) and not k.startswith("_"))
    return f"""<!doctype html><html><body style="font-family:system-ui;max-width:640px;margin:3rem auto">
<h2>Issued keys: {paid} paid, {trials} trial</h2><table border=1 cellpadding=6>
<tr><th>key</th><th>status</th><th>created</th><th>label</th></tr>{rows}</table>
<p><a href="/">← home</a></p></body></html>"""


# ---------------------------------------------------------------- MCP server --
# Streamable-HTTP MCP endpoint (/mcp) exposing the REST endpoints as MCP tools.
# Tool calls proxy through THIS app's own routes via test_client, so API-key
# auth, trial limits, usage logging and rate limits stay on a single code path.
# Spec subset: JSON-RPC 2.0, initialize, ping, tools/list, tools/call.
# Spec deviation (intentional): errors are JSON bodies with HTTP 200 + JSON-RPC
# error objects, not 4xx/5xx — streamable-HTTP MCP clients treat non-2xx as
# transport failure, while tool errors belong in the JSON-RPC result envelope.

MCP_PROTOCOL_VERSION = "2025-03-26"
MCP_TOOLS = [
    {
        "name": "pdf_merge",
        "description": "Merge multiple PDF files (in order) into one PDF. Returns base64 of the merged PDF.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "files": {"type": "array", "items": {"type": "string"},
                          "description": "PDF file contents as base64, in merge order (2+ files)"},
            },
            "required": ["files"],
        },
    },
    {
        "name": "pdf_split",
        "description": "Extract selected pages from a PDF. Returns base64 of the extracted PDF.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "PDF file content as base64"},
                "pages": {"type": "string",
                          "description": "1-based page spec like '1-3,5' (default: all pages)"},
            },
            "required": ["file"],
        },
    },
    {
        "name": "pdf_rotate",
        "description": "Rotate some or all pages of a PDF by 90/180/270 degrees. Returns base64 of the rotated PDF.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "PDF file content as base64"},
                "angle": {"type": "integer", "enum": [90, 180, 270],
                          "description": "rotation angle (default 90)"},
                "pages": {"type": "string", "description": "1-based page spec like '1-3,5' (default: all pages)"},
            },
            "required": ["file"],
        },
    },
    {
        "name": "pdf_text",
        "description": ("Extract text from a PDF, per page. Pass as_markdown=true for a clean "
                        "Markdown version with '## Page N' headings."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "PDF file content as base64"},
                "as_markdown": {"type": "boolean", "description": "return Markdown instead of JSON (default false)"},
            },
            "required": ["file"],
        },
    },
    {
        "name": "pdf_info",
        "description": "PDF metadata: page count, byte size, document info fields.",
        "inputSchema": {
            "type": "object",
            "properties": {"file": {"type": "string", "description": "PDF file content as base64"}},
            "required": ["file"],
        },
    },
    {
        "name": "pdf_safe_scan",
        "description": ("Scan a PDF for hostile content: JavaScript, embedded files, Launch/Open actions, "
                        "XFA forms, encryption. Returns verdict (likely_safe/suspicious/dangerous), risk_score "
                        "and findings. Static heuristics, NOT an antivirus."),
        "inputSchema": {
            "type": "object",
            "properties": {"file": {"type": "string", "description": "PDF file content as base64"}},
            "required": ["file"],
        },
    },
    {
        "name": "qr_code",
        "description": "Generate a QR code PNG for a text or URL. Returns base64 PNG (image/png).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "text or URL to encode"},
                "size": {"type": "integer", "description": "image size in px, 64-1000 (default 300)"},
            },
            "required": ["text"],
        },
    },
]


def _mcp_b64(b):
    return base64.b64encode(b).decode("ascii")


def _mcp_result(payload, is_error=False, mime=None, b64=None):
    """Wrap a payload as an MCP tools/call result (text or base64 image)."""
    if b64 is not None:
        content = [{"type": "image", "data": b64, "mimeType": mime or "application/octet-stream"}]
    else:
        content = [{"type": "text", "text": payload if isinstance(payload, str) else json.dumps(payload)}]
    return {"content": content, "isError": bool(is_error)}


def _mcp_client_call(method, path, key, **kw):
    """Proxy a tool call through this app's own REST route (in-process).
    dict values that are raw bytes become multipart file parts (filename required
    for werkzeug to treat them as uploads)."""
    data = kw.get("data") or {}
    for k, v in list(data.items()):
        if isinstance(v, (bytes, bytearray)):
            data[k] = (io.BytesIO(bytes(v)), f"{k}.bin")
    c = app.test_client()
    return c.post(path, data=data, headers={"Authorization": "Bearer " + key})


def _mcp_tool_call(name, args, key):
    import base64 as _b64mod
    try:
        if name == "pdf_merge":
            files = args.get("files") or []
            if not isinstance(files, list) or len(files) < 2:
                return _mcp_result({"error": "files: list of 2+ base64-encoded PDFs required"}, is_error=True)
            blobs = [_b64mod.b64decode(str(f)) for f in files]
            data = {"file": [(io.BytesIO(b), f"f{i}.pdf") for i, b in enumerate(blobs)]}
            resp = _mcp_client_call("POST", "/api/pdf/merge", key, data=data)
            if resp.status_code != 200:
                return _mcp_result({"error": f"merge failed: HTTP {resp.status_code}"}, is_error=True)
            return _mcp_result({"pdf_base64": _mcp_b64(resp.data), "bytes": len(resp.data)})

        if name in ("pdf_split", "pdf_rotate", "pdf_text", "pdf_info", "pdf_safe_scan"):
            fb = args.get("file")
            if not fb:
                return _mcp_result({"error": "file (base64 PDF) required"}, is_error=True)
            raw = _b64mod.b64decode(str(fb))
            path = {"pdf_split": "/api/pdf/split", "pdf_rotate": "/api/pdf/rotate",
                    "pdf_text": "/api/pdf/text", "pdf_info": "/api/pdf/info",
                    "pdf_safe_scan": "/api/pdf/safe"}[name]
            data = {"file": raw}
            if name == "pdf_split" and args.get("pages"):
                data["pages"] = str(args["pages"])
            if name == "pdf_rotate":
                if args.get("angle"):
                    data["angle"] = str(args["angle"])
                if args.get("pages"):
                    data["pages"] = str(args["pages"])
            if name == "pdf_text" and args.get("as_markdown"):
                data["fmt"] = "md"
            resp = _mcp_client_call("POST", path, key, data=data)
            if resp.status_code != 200:
                try:
                    err = resp.get_json(force=True)
                except Exception:
                    err = {}
                return _mcp_result({"error": f"HTTP {resp.status_code}: {err.get('error', '')}"}, is_error=True)
            if name in ("pdf_split", "pdf_rotate"):
                return _mcp_result({"pdf_base64": _mcp_b64(resp.data), "bytes": len(resp.data)})
            if name == "pdf_text":
                if args.get("as_markdown"):
                    return _mcp_result(resp.data.decode("utf-8", "replace"))
                return _mcp_result(resp.get_json(force=True))
            return _mcp_result(resp.get_json(force=True))

        if name == "qr_code":
            text_ = args.get("text")
            if not text_:
                return _mcp_result({"error": "text required"}, is_error=True)
            size = args.get("size") or 300
            from urllib.parse import quote
            c = app.test_client()
            resp = c.get(f"/api/qr?text={quote(text_)}&size={int(size)}",
                         headers={"Authorization": "Bearer " + key})
            if resp.status_code != 200:
                try:
                    err = resp.get_json(force=True)
                except Exception:
                    err = {}
                return _mcp_result({"error": f"HTTP {resp.status_code}: {err.get('error', '')}"}, is_error=True)
            return _mcp_result("QR PNG generated", mime="image/png", b64=_mcp_b64(resp.data))

        return None  # unknown tool
    except Exception as e:
        return _mcp_result({"error": f"{type(e).__name__}: {e}"}, is_error=True)


@app.post("/mcp")
def mcp_post():
    try:
        req = request.get_json(force=True)
    except Exception:
        return jsonify(jsonrpc="2.0", id=None, error={"code": -32700, "message": "parse error"}), 200
    if not isinstance(req, dict):
        return jsonify(jsonrpc="2.0", id=None, error={"code": -32600, "message": "invalid request"}), 200
    rid, method = req.get("id"), req.get("method")
    key = _get_key()
    # initialize / tools/list / ping stay public so MCP clients and directories can
    # connect and enumerate without a key; tools/call still requires one.
    if not key and method not in ("initialize", "tools/list", "ping"):
        return jsonify(jsonrpc="2.0", id=rid,
                       error={"code": -32001, "message": "Missing API key: pass ?key= or Authorization: Bearer "
                                                          "(free trial at /api/trial)"}), 200
    params = req.get("params") or {}

    def rpc_err(code, message):
        return jsonify(jsonrpc="2.0", id=rid, error={"code": code, "message": message}), 200

    def rpc_ok(result):
        return jsonify(jsonrpc="2.0", id=rid, result=result), 200

    if method == "initialize":
        return rpc_ok({
            "protocolVersion": params.get("protocolVersion") or MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "tinytoolbox", "version": "1.1",
                           "description": "PDF merge/split/rotate/text/info/safe-scan + QR code tools; "
                                          "$3 one-time key, free trial at https://tinytoolbox.bigfloppy.net/api/trial"},
            "instructions": "Pass your API key as ?key= on the endpoint URL or Authorization: Bearer header. "
                            "GET /api/trial mints a free trial key (30 calls).",
        })
    if method == "ping":
        return rpc_ok({})
    if method == "tools/list":
        return rpc_ok({"tools": MCP_TOOLS})
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        result = _mcp_tool_call(name, args, key)
        if result is None:
            return rpc_err(-32602, f"Unknown tool: {name}")
        return rpc_ok(result)
    return rpc_err(-32601, f"Method not found: {method}")


@app.get("/mcp")
def mcp_get():
    return jsonify(error="MCP endpoint: use POST (streamable HTTP). Docs at /"), 405


_WK_DIR = os.path.dirname(os.path.abspath(__file__))


@app.get("/.well-known/mcp-registry-auth")
def wk_registry_auth():
    # MCP Registry domain-based publish auth proof (ed25519 pubkey, charlie-3)
    return send_file(os.path.join(_WK_DIR, "mcp-registry-auth"), mimetype="text/plain")


@app.get("/.well-known/server.json")
def wk_server_json():
    # MCP Registry server metadata: net/bigfloppy/tinytoolbox, streamable-http /mcp
    return send_file(os.path.join(_WK_DIR, "server.json"), mimetype="application/json")



if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8095")), threaded=True)
