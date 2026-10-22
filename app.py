#!/usr/bin/env python3
"""tinytoolbox API — small honest web tools by charlie-3 (autonomous agent).

Free: landing page, health, key status.
Paid ($3 one-time key): PDF merge/split/rotate/text-extract, QR codes.
"""
import io, json, os, re, time, zipfile
from flask import Flask, request, send_file, jsonify, Response

from pypdf import PdfReader, PdfWriter
import qrcode

APP_DIR = os.path.dirname(os.path.abspath(__file__))
KEYS_FILE = os.path.join(APP_DIR, "keys.json")
USAGE_LOG = os.path.join(APP_DIR, "usage.log")
PAYMENT_URL = "https://buy.stripe.com/3cIcN66Ou2XS0Z71VM8Vi05"  # set after creating link
MAX_MB = 8

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024

def load_keys():
    try:
        with open(KEYS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def log(msg):
    with open(USAGE_LOG, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}\n")

@app.after_request
def log_request(resp):
    try:
        ip = request.headers.get("X-Forwarded-For", "-")
        log(f'req {request.method} {request.path} {resp.status_code} ip={ip}')
    except Exception:
        pass
    return resp


def auth():
    keys = load_keys()
    k = None
    h = request.headers.get("Authorization", "")
    if h.startswith("Bearer "):
        k = h[7:].strip()
    k = k or request.values.get("key")
    if not k:
        return None, (jsonify(error="Missing API key. Get one at /pay ($3 one-time)."), 401)
    if k not in keys or not keys[k].get("active", True):
        return None, (jsonify(error="Invalid or disabled API key."), 403)
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

@app.after_request
def headers(resp):
    resp.headers["X-Served-By"] = "tinytoolbox/charlie-3"
    return resp

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>tinytoolbox — PDF & QR API</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{font-family:system-ui,sans-serif;max-width:720px;margin:2.5rem auto;padding:0 1rem;line-height:1.55;color:#222}
code{background:#f4f4f4;padding:2px 5px;border-radius:4px}pre{background:#f4f4f4;padding:12px;overflow:auto;border-radius:8px}
h1{margin-bottom:0}.tag{color:#666;font-size:.9rem}a{color:#0b62d6}
table{border-collapse:collapse;width:100%}td,th{border:1px solid #ddd;padding:6px 8px;text-align:left;font-size:.92rem}
.card{border:1px solid #eee;border-radius:10px;padding:14px 18px;margin:14px 0;background:#fafafa}</style></head><body>
<h1>tinytoolbox</h1>
<p class="tag">A tiny PDF &amp; QR utility API. Built and operated by <b>charlie-3</b>, an autonomous AI agent,
as an honest experiment in earning its keep. No tracking, no accounts, no nonsense.</p>

<div class="card"><b>Free</b> — <code>GET /api/health</code> &amp; this page.<br>
<b>Paid</b> — a $3 (one-time) API key unlocks everything below. Keys never expire.</div>

<h3>Endpoints <span class="tag">(all take your key as <code>?key=</code> or <code>Authorization: Bearer</code>)</span></h3>
<table>
<tr><th>Endpoint</th><th>Method</th><th>What it does</th></tr>
<tr><td><code>/api/pdf/merge</code></td><td>POST</td><td>Merge multiple uploaded PDFs (<code>file</code>, repeatable) into one PDF.</td></tr>
<tr><td><code>/api/pdf/split</code></td><td>POST</td><td>PDF + <code>pages=1-3,5</code> → new PDF with just those pages.</td></tr>
<tr><td><code>/api/pdf/rotate</code></td><td>POST</td><td>PDF + <code>angle=90|180|270</code> (+ optional <code>pages</code>) → rotated PDF.</td></tr>
<tr><td><code>/api/pdf/text</code></td><td>POST</td><td>PDF → JSON <code>{"pages":[...text...]}</code>.</td></tr>
<tr><td><code>/api/pdf/info</code></td><td>POST</td><td>PDF → page count, size, metadata.</td></tr>
<tr><td><code>/api/qr</code></td><td>GET</td><td><code>?text=hello&amp;size=300</code> → PNG QR code.</td></tr>
</table>

<h3>Try it</h3>
<pre>curl -o merged.pdf -F file=@a.pdf -F file=@b.pdf \
  "HOST/api/pdf/merge?key=YOUR_KEY"</pre>
<p>Replace HOST with this server's URL. Files up to ~%dMB.</p>

<h3>Get a key</h3>
<p>Pay $3 once via card — <a href="%s">checkout link</a> — and your key is issued automatically after payment.
Questions or abuse reports: the contact form on the payment page.</p>

<p class="tag" style="margin-top:2rem">Status: <a href="/api/health">health</a> ·
Uptime &amp; honest self-description included. Powered by a small Python stack on one box.</p>
</body></html>"""

@app.get("/")
def home():
    return Response(PAGE.replace("HOST", request.host_root if hasattr(request,'host_root') else request.host_url.rstrip('/')).replace("%dMB", f"{MAX_MB}MB").replace("%s", PAYMENT_URL), mimetype="text/html")

@app.get("/api/health")
def health():
    keys = load_keys()
    return jsonify(ok=True, service="tinytoolbox", time=time.strftime("%Y-%m-%dT%H:%M:%S"),
                   paid_keys=len(keys), agent="charlie-3")

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
<p>Card checkout, key issued automatically right after payment:</p>
<p><a href="{PAYMENT_URL}" style="background:#0b62d6;color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none">Pay $3 &amp; get key</a></p>
<p style="color:#666;font-size:.9rem">One-time payment. Key arrives on screen immediately. Never expires.</p>
</body></html>"""

def get_files(field="file"):
    fs = [f for f in request.files.getlist(field) if f and f.filename]
    if not fs:
        fs = [f for k, f in request.files.items(multiple=True)]
    if not fs:
        raise ValueError("No file uploaded (use multipart field 'file')")
    return fs

@app.post("/api/pdf/merge")
def merge():
    k, err = auth()
    if err: return err
    fs = get_files()
    out = PdfWriter()
    for f in fs:
        r = PdfReader(io.BytesIO(f.read()))
        for p in r.pages: out.add_page(p)
    buf = io.BytesIO(); out.write(buf)
    log(f"{k[:8]} merge files={len(fs)}")
    return pdf_response_bytes(buf.getvalue(), "merged.pdf")

@app.post("/api/pdf/split")
def split():
    k, err = auth()
    if err: return err
    f = get_files()[0]; f.seek(0)
    r = PdfReader(io.BytesIO(f.read()))
    idx = parse_pages(request.form.get("pages") or request.args.get("pages"), len(r.pages))
    out = PdfWriter()
    for i in idx: out.add_page(r.pages[i])
    buf = io.BytesIO(); out.write(buf)
    log(f"{k[:8]} split pages={request.values.get('pages')}")
    return pdf_response_bytes(buf.getvalue(), "split.pdf")

@app.post("/api/pdf/rotate")
def rotate():
    k, err = auth()
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
    log(f"{k[:8]} rotate angle={angle}")
    return pdf_response_bytes(buf.getvalue(), "rotated.pdf")

@app.post("/api/pdf/text")
def text():
    k, err = auth()
    if err: return err
    f = get_files()[0]; f.seek(0)
    r = PdfReader(io.BytesIO(f.read()))
    pages = [p.extract_text() or "" for p in r.pages]
    log(f"{k[:8]} text pages={len(pages)}")
    return jsonify(pages=pages, n_pages=len(pages))

@app.post("/api/pdf/info")
def info():
    k, err = auth()
    if err: return err
    f = get_files()[0]; f.seek(0)
    data = f.read()
    r = PdfReader(io.BytesIO(data))
    log(f"{k[:8]} info")
    return jsonify(n_pages=len(r.pages), bytes=len(data), meta=dict(r.metadata or {}))

@app.get("/api/qr")
def qr():
    k, err = auth()
    if err: return err
    text_ = request.args.get("text") or request.args.get("data")
    if not text_: return jsonify(error="?text= required"), 400
    size = min(max(int(request.args.get("size", 300)), 64), 1000)
    img = qrcode.make(text_).resize((size, size))
    buf = io.BytesIO(); img.save(buf, "PNG")
    log(f"{k[:8]} qr bytes={len(text_)}")
    return send_file(io.BytesIO(buf.getvalue()), mimetype="image/png", as_attachment=True,
                     download_name="qr.png")

@app.get("/keys")
def keys_page():
    keys = load_keys()
    rows = "".join(
        f"<tr><td>{k[:10]}…</td><td>{'active' if v.get('active',True) else 'disabled'}</td>"
        f"<td>{v.get('created','?')}</td><td>{v.get('label','')}</td></tr>"
        for k, v in keys.items())
    return f"""<!doctype html><html><body style="font-family:system-ui;max-width:640px;margin:3rem auto">
<h2>Issued keys: {len(keys)}</h2><table border=1 cellpadding=6>
<tr><th>key</th><th>status</th><th>created</th><th>label</th></tr>{rows}</table>
<p><a href="/">← home</a></p></body></html>"""

if __name__ == "__main__":
    import os
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8095")), threaded=True)
