#!/usr/bin/env python3
"""
VidSnap Server — yt-dlp powered
Chalao: python3 vidsnap_server.py
Phir phone mein open karo: http://LAPTOP_IP:8080
"""

import subprocess, sys, os, threading, json, socket, shutil, time, uuid
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote

# ── Auto-install dependencies ────────────────────────────────────────────────
def install(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", pkg,
                           "--break-system-packages", "-q"],
                          stderr=subprocess.DEVNULL)

try:
    import yt_dlp
except ImportError:
    print("⏳ yt-dlp install ho raha hai...")
    install("yt-dlp")
    import yt_dlp
    print("✓ yt-dlp ready!")

# ── Download state store ─────────────────────────────────────────────────────
downloads = {}   # id -> {status, progress, log, filename, filepath}

DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "/tmp/vidsnap")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

# ── HTML UI ──────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="hi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>VidSnap</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
:root{
  --bg:#07090f;--s1:#0e1420;--s2:#141c2a;--br:#1c2a3e;
  --ac:#00e5ff;--gr:#00e096;--er:#ff3d71;--wn:#ffaa00;
  --tx:#e4eeff;--mt:#4a6480;
}
html{scroll-behavior:smooth}
body{font-family:'Syne',sans-serif;background:var(--bg);color:var(--tx);min-height:100vh;padding:0 0 40px;overflow-x:hidden}

/* Grid bg */
body::before{content:'';position:fixed;inset:0;
  background:linear-gradient(var(--br) 1px,transparent 1px),linear-gradient(90deg,var(--br) 1px,transparent 1px);
  background-size:40px 40px;opacity:.2;pointer-events:none;z-index:0}

/* Glow */
.glow{position:fixed;width:400px;height:400px;border-radius:50%;filter:blur(120px);opacity:.08;pointer-events:none;z-index:0}
.g1{background:var(--ac);top:-100px;right:-80px}
.g2{background:#7b61ff;bottom:-80px;left:-80px}

.wrap{position:relative;z-index:1;max-width:480px;margin:0 auto;padding:0 16px}

/* Header */
header{text-align:center;padding:32px 0 24px}
.logo{display:inline-flex;align-items:center;gap:10px;margin-bottom:14px}
.logo-ico{width:38px;height:38px;background:var(--ac);border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:17px;color:#000;font-weight:900}
.logo-txt{font-size:20px;font-weight:800;letter-spacing:-.5px}
h1{font-size:clamp(28px,8vw,42px);font-weight:800;line-height:1.05;letter-spacing:-1.5px;margin-bottom:8px}
h1 em{color:var(--ac);font-style:normal}
.sub{font-family:'DM Mono',monospace;font-size:11px;color:var(--mt);letter-spacing:.5px}

/* Cards */
.card{background:var(--s1);border:1px solid var(--br);border-radius:18px;padding:18px;margin-bottom:12px}
.clbl{font-family:'DM Mono',monospace;font-size:9px;font-weight:500;letter-spacing:2px;color:var(--mt);text-transform:uppercase;margin-bottom:10px;display:flex;align-items:center;gap:6px}
.clbl::before{content:'';width:12px;height:1px;background:var(--mt)}

/* URL input */
.url-box{display:flex;align-items:center;background:var(--s2);border:1px solid var(--br);border-radius:12px;overflow:hidden;transition:border-color .2s}
.url-box:focus-within{border-color:var(--ac)}
#urlInput{flex:1;background:none;border:none;outline:none;padding:14px 16px;font-family:'DM Mono',monospace;font-size:13px;color:var(--tx);min-width:0}
#urlInput::placeholder{color:var(--mt)}
.paste-btn{background:var(--s2);border:none;padding:14px 14px;color:var(--mt);font-size:18px;cursor:pointer;transition:color .2s;flex-shrink:0}
.paste-btn:active{color:var(--ac)}

/* Quality pills */
.pills{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.pill{background:var(--s2);border:1px solid var(--br);border-radius:10px;padding:10px 6px;font-family:'DM Mono',monospace;font-size:12px;color:var(--mt);cursor:pointer;transition:all .18s;text-align:center;user-select:none;-webkit-user-select:none}
.pill:active{transform:scale(.97)}
.pill.on{background:rgba(0,229,255,.1);border-color:var(--ac);color:var(--ac)}
.pill.audio.on{background:rgba(123,97,255,.1);border-color:#7b61ff;color:#7b61ff}

/* Download button */
.dl-btn{width:100%;padding:16px;border-radius:14px;border:none;background:var(--ac);color:#000;font-family:'Syne',sans-serif;font-size:17px;font-weight:800;cursor:pointer;transition:opacity .2s,transform .15s;margin-top:4px;letter-spacing:-.3px}
.dl-btn:active{opacity:.85;transform:scale(.99)}
.dl-btn:disabled{background:var(--s2);color:var(--mt);cursor:not-allowed}

/* Progress */
.prog-wrap{background:var(--s2);border-radius:999px;height:4px;margin-top:14px;overflow:hidden;display:none}
.prog-wrap.show{display:block}
.prog-bar{height:100%;background:var(--ac);border-radius:999px;transition:width .3s;width:0%}
.prog-bar.indeterminate{animation:slide 1.2s ease infinite}
@keyframes slide{0%{transform:translateX(-100%);width:60%}100%{transform:translateX(200%);width:60%}}

/* Log */
.logbox{background:var(--s2);border:1px solid var(--br);border-radius:12px;padding:12px 14px;font-family:'DM Mono',monospace;font-size:11px;line-height:1.9;max-height:160px;overflow-y:auto;margin-top:12px;display:none}
.logbox.show{display:block}
.lok{color:var(--gr)}.ler{color:var(--er)}.linf{color:var(--mt)}.lwn{color:var(--wn)}

/* Video info */
.vinfo{display:none;margin-top:12px;background:var(--s2);border:1px solid var(--br);border-radius:12px;padding:12px;gap:10px;align-items:flex-start}
.vinfo.show{display:flex}
.vinfo img{width:90px;height:51px;object-fit:cover;border-radius:8px;flex-shrink:0;background:var(--br)}
.vinfo-t{font-size:12px;font-weight:700;line-height:1.4;margin-bottom:3px}
.vinfo-m{font-family:'DM Mono',monospace;font-size:10px;color:var(--mt)}

/* Download links */
.dlinks{display:none;margin-top:12px}
.dlinks.show{display:block}
.dlinks-lbl{font-family:'DM Mono',monospace;font-size:9px;letter-spacing:2px;text-transform:uppercase;color:var(--gr);margin-bottom:8px}
.dlink{display:flex;align-items:center;justify-content:space-between;background:var(--s2);border:1px solid rgba(0,224,150,.2);border-radius:11px;padding:12px 14px;text-decoration:none;color:var(--tx);margin-bottom:7px;transition:border-color .2s,background .2s}
.dlink:active{border-color:var(--gr);background:rgba(0,224,150,.05)}
.dlink-q{font-weight:700;font-size:14px}
.dlink-m{font-family:'DM Mono',monospace;font-size:10px;color:var(--mt)}
.dlink-ico{color:var(--gr);font-size:20px;flex-shrink:0}

/* Error */
.errbox{background:rgba(255,61,113,.06);border:1px solid rgba(255,61,113,.25);border-radius:12px;padding:13px 14px;font-family:'DM Mono',monospace;font-size:11px;color:var(--er);margin-top:12px;line-height:1.7;display:none}
.errbox.show{display:block}

/* Footer */
footer{text-align:center;font-family:'DM Mono',monospace;font-size:10px;color:var(--mt);margin-top:24px;padding-top:16px;border-top:1px solid var(--br)}

::-webkit-scrollbar{width:3px}
::-webkit-scrollbar-thumb{background:var(--br);border-radius:3px}
</style>
</head>
<body>
<div class="glow g1"></div>
<div class="glow g2"></div>
<div class="wrap">
  <header>
    <div class="logo">
      <div class="logo-ico">▶</div>
      <span class="logo-txt">VidSnap</span>
    </div>
    <h1>Video <em>Download</em><br>Karo Phone Se</h1>
    <p class="sub">// yt-dlp · HD+Audio · 1000+ sites</p>
  </header>

  <!-- URL -->
  <div class="card">
    <div class="clbl">Video URL</div>
    <div class="url-box">
      <input type="url" id="urlInput" placeholder="YouTube / Instagram / TikTok URL..." inputmode="url" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false"/>
      <button class="paste-btn" onclick="pasteUrl()" title="Paste">📋</button>
    </div>
  </div>

  <!-- Quality -->
  <div class="card">
    <div class="clbl">Quality</div>
    <div class="pills" id="pillsEl">
      <div class="pill" onclick="setPill(this)" data-v="144p+audio">144p 🔊</div>
      <div class="pill" onclick="setPill(this)" data-v="360p+audio">360p 🔊</div>
      <div class="pill on" onclick="setPill(this)" data-v="720p+audio">720p 🔊</div>
      <div class="pill" onclick="setPill(this)" data-v="1080p+audio">1080p 🔊</div>
      <div class="pill" onclick="setPill(this)" data-v="best+audio">Best 🔊</div>
      <div class="pill audio" onclick="setPill(this)" data-v="audio-only">Audio 🎵</div>
    </div>
  </div>

  <!-- Button -->
  <button class="dl-btn" id="dlBtn" onclick="startDl()">⬇ Download Karo</button>

  <!-- Progress -->
  <div class="prog-wrap" id="progWrap"><div class="prog-bar indeterminate" id="progBar"></div></div>

  <!-- Log -->
  <div class="logbox" id="logEl"></div>

  <!-- Video info -->
  <div class="vinfo" id="vinfoEl">
    <img id="thumbEl" src="" alt=""/>
    <div><div class="vinfo-t" id="titleEl"></div><div class="vinfo-m" id="durEl"></div></div>
  </div>

  <!-- Download links -->
  <div class="dlinks" id="dlinksEl">
    <div class="dlinks-lbl">✓ Links Ready — Tap to Download</div>
    <div id="dlistEl"></div>
  </div>

  <!-- Error -->
  <div class="errbox" id="errEl"></div>

  <footer>VidSnap · yt-dlp · sab free · koi ads nahi</footer>
</div>

<script>
let qual = '720p+audio';
let pollTimer = null;

function setPill(el) {
  document.getElementById('pillsEl').querySelectorAll('.pill').forEach(p => p.classList.remove('on'));
  el.classList.add('on');
  qual = el.dataset.v;
}

async function pasteUrl() {
  try {
    const t = await navigator.clipboard.readText();
    document.getElementById('urlInput').value = t;
  } catch(e) {
    document.getElementById('urlInput').focus();
  }
}

function log(msg, cls) {
  const el = document.getElementById('logEl');
  el.classList.add('show');
  const icons = {lok:'✓ ', ler:'✗ ', linf:'→ ', lwn:'⚠ '};
  el.innerHTML += `<div class="${cls}">${icons[cls]||''}${msg}</div>`;
  el.scrollTop = el.scrollHeight;
}

function reset() {
  if(pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  ['logEl','dlinksEl','errEl','vinfoEl'].forEach(id => {
    const el = document.getElementById(id);
    el.classList.remove('show');
  });
  document.getElementById('logEl').innerHTML = '';
  document.getElementById('dlistEl').innerHTML = '';
  document.getElementById('errEl').innerHTML = '';
  document.getElementById('progWrap').classList.remove('show');
}

function showErr(msg) {
  const el = document.getElementById('errEl');
  el.className = 'errbox show';
  el.innerHTML = '❌ ' + msg;
}

function setLoading(on) {
  const btn = document.getElementById('dlBtn');
  btn.disabled = on;
  btn.textContent = on ? '⏳ Downloading...' : '⬇ Download Karo';
  const pw = document.getElementById('progWrap');
  if(on) pw.classList.add('show'); else pw.classList.remove('show');
}

async function startDl() {
  const url = document.getElementById('urlInput').value.trim();
  if(!url) { showErr('Pehle URL daalo!'); return; }

  reset();
  setLoading(true);
  log('Request bhej rahe hain...', 'linf');
  log('Quality: ' + qual, 'linf');

  try {
    const res = await fetch('/api/download', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({url, quality: qual})
    });
    const data = await res.json();
    if(!res.ok || data.error) throw new Error(data.error || 'Server error');

    const dlId = data.id;
    log('Download shuru! ID: ' + dlId, 'linf');
    pollTimer = setInterval(() => pollStatus(dlId), 800);

  } catch(e) {
    setLoading(false);
    showErr(e.message);
  }
}

async function pollStatus(dlId) {
  try {
    const res = await fetch('/api/status/' + dlId);
    const data = await res.json();

    // Show new logs
    if(data.logs && data.logs.length) {
      const logEl = document.getElementById('logEl');
      logEl.classList.add('show');
      logEl.innerHTML = '';
      data.logs.forEach(l => {
        const cls = l.includes('ERROR')||l.includes('error') ? 'ler' :
                    l.includes('Merging')||l.includes('Destination') ? 'lok' : 'linf';
        logEl.innerHTML += `<div class="${cls}">→ ${l}</div>`;
      });
      logEl.scrollTop = logEl.scrollHeight;
    }

    if(data.status === 'done') {
      clearInterval(pollTimer); pollTimer = null;
      setLoading(false);
      log('Download complete! ✓', 'lok');

      // Show download link
      const dlistEl = document.getElementById('dlistEl');
      dlistEl.innerHTML = '';
      const a = document.createElement('a');
      a.className = 'dlink';
      a.href = '/api/file/' + dlId;
      a.download = data.filename || 'video.mp4';
      a.innerHTML = `
        <div>
          <div class="dlink-q">${data.filename || 'Video'}</div>
          <div class="dlink-m">Tap karke download karo 📲</div>
        </div>
        <span class="dlink-ico">⬇</span>`;
      dlistEl.appendChild(a);
      document.getElementById('dlinksEl').classList.add('show');

    } else if(data.status === 'error') {
      clearInterval(pollTimer); pollTimer = null;
      setLoading(false);
      showErr(data.error || 'Download fail hua!');
    }

  } catch(e) {
    // Network hiccup, keep polling
  }
}
</script>
</body>
</html>"""

# ── HTTP Handler ─────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress default logs

    def send_json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/index.html":
            body = HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)

        elif path.startswith("/api/status/"):
            dl_id = path.split("/")[-1]
            if dl_id in downloads:
                self.send_json(downloads[dl_id])
            else:
                self.send_json({"error": "Not found"}, 404)

        elif path.startswith("/api/file/"):
            dl_id = path.split("/")[-1]
            if dl_id in downloads and downloads[dl_id].get("filepath"):
                fpath = downloads[dl_id]["filepath"]
                fname = downloads[dl_id].get("filename", "video.mp4")
                if os.path.exists(fpath):
                    size = os.path.getsize(fpath)
                    self.send_response(200)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Content-Length", size)
                    self.send_header("Content-Disposition",
                                     f'attachment; filename="{fname}"')
                    self.end_headers()
                    with open(fpath, "rb") as f:
                        data = f.read()
                        self.wfile.write(data)
                else:
                    self.send_json({"error": "File not found"}, 404)
            else:
                self.send_json({"error": "Not ready"}, 404)
        else:
            self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        if self.path == "/api/download":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            url = body.get("url", "").strip()
            quality = body.get("quality", "720p+audio")

            if not url:
                self.send_json({"error": "URL nahi di!"}, 400)
                return

            dl_id = str(uuid.uuid4())[:8]
            downloads[dl_id] = {
                "status": "running",
                "logs": [],
                "filename": None,
                "filepath": None,
                "error": None
            }

            threading.Thread(target=run_download,
                             args=(dl_id, url, quality),
                             daemon=True).start()
            self.send_json({"id": dl_id})
        else:
            self.send_json({"error": "Not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

# ── Download Runner ──────────────────────────────────────────────────────────
def run_download(dl_id, url, quality):
    fmt_map = {
        "144p+audio":  "bestvideo[height<=144]+bestaudio/best[height<=144]",
        "360p+audio":  "bestvideo[height<=360]+bestaudio/best[height<=360]",
        "720p+audio":  "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "1080p+audio": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "best+audio":  "bestvideo+bestaudio/best",
        "audio-only":  "bestaudio/best",
    }
    fmt = fmt_map.get(quality, "bestvideo+bestaudio/best")
    out_tmpl = os.path.join(DOWNLOAD_DIR, f"{dl_id}_%(title).60s.%(ext)s")

    if quality == "audio-only":
        cmd = [sys.executable, "-m", "yt_dlp",
               "--format", "bestaudio/best",
               "--extract-audio", "--audio-format", "mp3",
               "--output", out_tmpl,
               "--no-playlist", url]
    else:
        cmd = [sys.executable, "-m", "yt_dlp",
               "--format", fmt,
               "--merge-output-format", "mp4",
               "--output", out_tmpl,
               "--no-playlist", url]

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True, bufsize=1)
        for line in proc.stdout:
            line = line.strip()
            if line:
                downloads[dl_id]["logs"].append(line)
                # Keep only last 30 lines
                if len(downloads[dl_id]["logs"]) > 30:
                    downloads[dl_id]["logs"].pop(0)

        proc.wait()

        if proc.returncode == 0:
            # Find the downloaded file
            for f in os.listdir(DOWNLOAD_DIR):
                if f.startswith(dl_id):
                    fpath = os.path.join(DOWNLOAD_DIR, f)
                    fname = f[len(dl_id)+1:]  # remove id prefix
                    downloads[dl_id].update({
                        "status": "done",
                        "filepath": fpath,
                        "filename": fname
                    })
                    break
            else:
                downloads[dl_id].update({"status":"error","error":"File nahi mili!"})
        else:
            downloads[dl_id].update({"status":"error","error":"yt-dlp fail hua. Log dekho."})

    except Exception as e:
        downloads[dl_id].update({"status":"error","error":str(e)})

# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    local_ip = get_local_ip()

    # Check ffmpeg
    if not shutil.which("ffmpeg"):
        print("⚠️  ffmpeg nahi mila! Chalao: sudo apt install ffmpeg")
        print("    (bina ffmpeg ke HD+audio nahi milega)")
    else:
        print("✓ ffmpeg ready")

    print(f"✓ yt-dlp ready")
    print(f"\n{'='*50}")
    print(f"  VidSnap Server Chal Raha Hai!")
    print(f"{'='*50}")
    print(f"\n  💻 Laptop pe:  http://localhost:{PORT}")
    print(f"  📱 Phone pe:   http://{local_ip}:{PORT}")
    print(f"\n  ☝️  Phone aur Laptop same WiFi pe hone chahiye!")
    print(f"  📁 Downloads: {DOWNLOAD_DIR}")
    print(f"\n  Band karne ke liye: Ctrl+C")
    print(f"{'='*50}\n")

    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\n👋 VidSnap band ho gaya!")
