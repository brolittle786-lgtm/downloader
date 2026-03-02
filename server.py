#!/usr/bin/env python3
"""
VidSnap 2.0 — yt-dlp powered video downloader
Run: python3 server.py
"""

import subprocess, sys, os, threading, json, socket, shutil, uuid, time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# Auto-install yt-dlp
try:
    import yt_dlp
except ImportError:
    print("Installing yt-dlp...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yt-dlp",
                           "--break-system-packages", "-q"], stderr=subprocess.DEVNULL)
    import yt_dlp

# Config
PORT = int(os.environ.get("PORT", 8080))
DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "/tmp/vidsnap")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# In-memory job store
jobs = {}  # id -> {status, logs, filename, filepath, error, title, thumb}

def get_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]; s.close(); return ip
    except: return "127.0.0.1"

# HTML (served to browser)
HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>VidSnap — Video Downloader</title>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700;900&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
:root{
  --bg:#04070d;
  --card:#0a1020;
  --card2:#0f1830;
  --border:#1a2840;
  --border2:#243550;
  --cyan:#00f0ff;
  --cyan2:#00b8d4;
  --green:#00e676;
  --red:#ff1744;
  --amber:#ffc400;
  --text:#ddeeff;
  --muted:#4a6888;
  --radius:18px;
}
html{scroll-behavior:smooth}
body{
  font-family:'Outfit',sans-serif;
  background:var(--bg);
  color:var(--text);
  min-height:100vh;
  overflow-x:hidden;
}

/* Animated background */
.bg-layer{
  position:fixed;inset:0;z-index:0;
  background:
    radial-gradient(ellipse 60% 50% at 80% -10%, rgba(0,240,255,.07) 0%, transparent 60%),
    radial-gradient(ellipse 50% 60% at -10% 80%, rgba(0,230,118,.05) 0%, transparent 60%);
  pointer-events:none;
}
.grid-layer{
  position:fixed;inset:0;z-index:0;
  background-image:
    linear-gradient(rgba(0,240,255,.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0,240,255,.04) 1px, transparent 1px);
  background-size:60px 60px;
  pointer-events:none;
}

/* Layout */
.page{position:relative;z-index:1;max-width:560px;margin:0 auto;padding:0 16px 60px}

/* Header */
header{
  text-align:center;
  padding:48px 0 36px;
  animation:fadeUp .6s ease both;
}
.logo{
  display:inline-flex;align-items:center;gap:12px;
  margin-bottom:20px;
}
.logo-mark{
  width:46px;height:46px;
  background:linear-gradient(135deg,var(--cyan),var(--cyan2));
  border-radius:14px;
  display:flex;align-items:center;justify-content:center;
  font-size:20px;
  box-shadow:0 0 30px rgba(0,240,255,.3);
}
.logo-name{font-size:24px;font-weight:900;letter-spacing:-1px}
.logo-name span{color:var(--cyan)}
.tagline{
  font-size:clamp(28px,7vw,46px);
  font-weight:900;
  line-height:1.05;
  letter-spacing:-1.5px;
  margin-bottom:12px;
}
.tagline em{
  color:transparent;
  background:linear-gradient(90deg,var(--cyan),var(--green));
  -webkit-background-clip:text;background-clip:text;
  font-style:normal;
}
.sub{
  font-family:'JetBrains Mono',monospace;
  font-size:12px;color:var(--muted);
  letter-spacing:.5px;
}

/* Cards */
.card{
  background:var(--card);
  border:1px solid var(--border);
  border-radius:var(--radius);
  padding:20px;
  margin-bottom:12px;
  animation:fadeUp .5s ease both;
  transition:border-color .2s;
}
.card:hover{border-color:var(--border2)}
.card-title{
  font-family:'JetBrains Mono',monospace;
  font-size:9px;font-weight:500;
  letter-spacing:2.5px;text-transform:uppercase;
  color:var(--muted);margin-bottom:12px;
  display:flex;align-items:center;gap:8px;
}
.card-title::before{content:'';width:16px;height:1px;background:var(--border2)}

/* URL input */
.url-field{
  display:flex;align-items:center;
  background:var(--card2);
  border:1.5px solid var(--border);
  border-radius:12px;
  overflow:hidden;
  transition:border-color .2s,box-shadow .2s;
}
.url-field:focus-within{
  border-color:var(--cyan);
  box-shadow:0 0 0 3px rgba(0,240,255,.08);
}
#urlInput{
  flex:1;min-width:0;
  background:none;border:none;outline:none;
  padding:14px 16px;
  font-family:'JetBrains Mono',monospace;
  font-size:12.5px;color:var(--text);
}
#urlInput::placeholder{color:var(--muted)}
.paste-btn{
  background:none;border:none;
  padding:14px 14px;
  color:var(--muted);font-size:18px;
  cursor:pointer;transition:color .2s;
  flex-shrink:0;
}
.paste-btn:hover,.paste-btn:active{color:var(--cyan)}

/* Platform badges */
.platforms{
  display:flex;gap:6px;flex-wrap:wrap;margin-top:10px;
}
.platform{
  font-family:'JetBrains Mono',monospace;
  font-size:10px;padding:3px 9px;
  border:1px solid var(--border2);
  border-radius:999px;color:var(--muted);
  cursor:pointer;transition:all .15s;
}
.platform:hover{border-color:var(--cyan);color:var(--cyan)}

/* Quality grid */
.quality-grid{
  display:grid;
  grid-template-columns:repeat(3,1fr);
  gap:8px;
}
.q-btn{
  background:var(--card2);
  border:1.5px solid var(--border);
  border-radius:12px;
  padding:12px 6px;
  text-align:center;
  cursor:pointer;
  transition:all .18s;
  user-select:none;
}
.q-btn:active{transform:scale(.96)}
.q-btn .q-label{
  font-weight:700;font-size:15px;
  display:block;margin-bottom:3px;
}
.q-btn .q-note{
  font-family:'JetBrains Mono',monospace;
  font-size:9px;color:var(--muted);
}
.q-btn.active{
  background:rgba(0,240,255,.08);
  border-color:var(--cyan);
}
.q-btn.active .q-label{color:var(--cyan)}
.q-btn.audio-btn.active{
  background:rgba(0,230,118,.08);
  border-color:var(--green);
}
.q-btn.audio-btn.active .q-label{color:var(--green)}

/* Download button */
.dl-btn{
  width:100%;padding:17px;
  border-radius:14px;border:none;
  background:linear-gradient(135deg,var(--cyan),var(--cyan2));
  color:#000;
  font-family:'Outfit',sans-serif;
  font-size:17px;font-weight:800;
  letter-spacing:-.3px;
  cursor:pointer;
  transition:transform .15s,box-shadow .2s,opacity .2s;
  margin-top:4px;
  display:flex;align-items:center;justify-content:center;gap:10px;
}
.dl-btn:hover{transform:translateY(-2px);box-shadow:0 10px 40px rgba(0,240,255,.25)}
.dl-btn:active{transform:translateY(0)}
.dl-btn:disabled{
  background:var(--card2);color:var(--muted);
  cursor:not-allowed;transform:none;box-shadow:none;
}
.spinner{
  width:18px;height:18px;
  border:2.5px solid rgba(0,0,0,.3);
  border-top-color:#000;
  border-radius:50%;
  animation:spin .7s linear infinite;
  display:none;
}
.dl-btn:disabled .spinner{border-color:var(--border2);border-top-color:var(--muted);display:block}
.dl-btn:disabled .dl-icon{display:none}

/* Progress bar */
.progress-wrap{
  height:3px;background:var(--card2);
  border-radius:999px;margin-top:14px;
  overflow:hidden;display:none;
}
.progress-wrap.show{display:block}
.progress-bar{
  height:100%;width:0%;
  background:linear-gradient(90deg,var(--cyan),var(--green));
  border-radius:999px;transition:width .4s;
}
.progress-bar.indeterminate{
  width:40%;
  animation:progress-slide 1.3s ease-in-out infinite;
}
@keyframes progress-slide{
  0%{transform:translateX(-150%)}
  100%{transform:translateX(350%)}
}

/* Status log */
.log-box{
  background:var(--card2);
  border:1px solid var(--border);
  border-radius:12px;
  padding:12px 14px;
  font-family:'JetBrains Mono',monospace;
  font-size:11px;line-height:1.9;
  max-height:140px;overflow-y:auto;
  margin-top:12px;display:none;
}
.log-box.show{display:block}
.l-ok{color:var(--green)}.l-er{color:var(--red)}.l-info{color:var(--muted)}.l-warn{color:var(--amber)}

/* Video info card */
.vcard{
  display:none;margin-top:12px;
  background:var(--card2);border:1px solid var(--border);
  border-radius:14px;padding:14px;
  gap:12px;align-items:center;
}
.vcard.show{display:flex}
.vcard img{
  width:96px;height:54px;
  object-fit:cover;border-radius:10px;
  flex-shrink:0;background:var(--border);
}
.vcard-title{font-size:13px;font-weight:700;line-height:1.4;margin-bottom:4px}
.vcard-meta{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--muted)}

/* Download links */
.links-section{display:none;margin-top:12px}
.links-section.show{display:block}
.links-label{
  font-family:'JetBrains Mono',monospace;
  font-size:9px;letter-spacing:2px;text-transform:uppercase;
  color:var(--green);margin-bottom:10px;
  display:flex;align-items:center;gap:8px;
}
.links-label::after{content:'';flex:1;height:1px;background:rgba(0,230,118,.2)}
.dl-link{
  display:flex;align-items:center;justify-content:space-between;
  background:var(--card2);
  border:1.5px solid rgba(0,230,118,.15);
  border-radius:12px;padding:14px 16px;
  text-decoration:none;color:var(--text);
  margin-bottom:8px;
  transition:border-color .2s,background .2s,transform .15s;
}
.dl-link:hover,.dl-link:active{
  border-color:var(--green);
  background:rgba(0,230,118,.06);
  transform:translateX(3px);
}
.dl-link-left{display:flex;flex-direction:column;gap:3px}
.dl-link-q{font-weight:700;font-size:15px}
.dl-link-m{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--muted)}
.dl-link-ico{
  font-size:22px;color:var(--green);
  flex-shrink:0;margin-left:12px;
}

/* Error box */
.err-box{
  background:rgba(255,23,68,.06);
  border:1px solid rgba(255,23,68,.2);
  border-radius:12px;padding:14px 16px;
  font-family:'JetBrains Mono',monospace;
  font-size:11.5px;color:var(--red);
  margin-top:12px;line-height:1.7;
  display:none;
}
.err-box.show{display:block}

/* Footer */
footer{
  text-align:center;
  font-family:'JetBrains Mono',monospace;
  font-size:10px;color:var(--muted);
  margin-top:40px;padding-top:20px;
  border-top:1px solid var(--border);
}

/* Scrollbar */
::-webkit-scrollbar{width:3px}
::-webkit-scrollbar-thumb{background:var(--border2);border-radius:3px}

/* Animations */
@keyframes fadeUp{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:translateY(0)}}
@keyframes spin{to{transform:rotate(360deg)}}

/* Responsive */
@media(max-width:400px){
  .quality-grid{grid-template-columns:repeat(2,1fr)}
  .tagline{font-size:28px}
}
</style>
</head>
<body>
<div class="bg-layer"></div>
<div class="grid-layer"></div>

<div class="page">
  <!-- Header -->
  <header>
    <div class="logo">
      <div class="logo-mark">▶</div>
      <div class="logo-name">Vid<span>Snap</span></div>
    </div>
    <h1 class="tagline">Download Any<br><em>Video Free</em></h1>
    <p class="sub">// Powered by yt-dlp · HD + Audio · 1000+ Sites</p>
  </header>

  <!-- URL Card -->
  <div class="card" style="animation-delay:.05s">
    <div class="card-title">Video URL</div>
    <div class="url-field">
      <input type="url" id="urlInput"
        placeholder="Paste YouTube, Instagram, TikTok URL..."
        inputmode="url" autocomplete="off" autocorrect="off"
        autocapitalize="off" spellcheck="false"
        oninput="onUrlInput()"/>
      <button class="paste-btn" onclick="pasteUrl()" title="Paste from clipboard">📋</button>
    </div>
    <div class="platforms">
      <span class="platform">YouTube</span>
      <span class="platform">Instagram</span>
      <span class="platform">TikTok</span>
      <span class="platform">Facebook</span>
      <span class="platform">Twitter/X</span>
      <span class="platform">+ 1000 more</span>
    </div>
  </div>

  <!-- Quality Card -->
  <div class="card" style="animation-delay:.1s">
    <div class="card-title">Quality</div>
    <div class="quality-grid" id="qualityGrid">
      <div class="q-btn" onclick="setQ(this,'144p')" data-q="144p">
        <span class="q-label">144p</span>
        <span class="q-note">🔊 w/ audio</span>
      </div>
      <div class="q-btn" onclick="setQ(this,'360p')" data-q="360p">
        <span class="q-label">360p</span>
        <span class="q-note">🔊 w/ audio</span>
      </div>
      <div class="q-btn active" onclick="setQ(this,'720p')" data-q="720p">
        <span class="q-label">720p</span>
        <span class="q-note">🔊 HD audio</span>
      </div>
      <div class="q-btn" onclick="setQ(this,'1080p')" data-q="1080p">
        <span class="q-label">1080p</span>
        <span class="q-note">🔊 Full HD</span>
      </div>
      <div class="q-btn" onclick="setQ(this,'best')" data-q="best">
        <span class="q-label">Best</span>
        <span class="q-note">🔊 Max quality</span>
      </div>
      <div class="q-btn audio-btn" onclick="setQ(this,'audio')" data-q="audio">
        <span class="q-label">Audio</span>
        <span class="q-note">🎵 MP3 only</span>
      </div>
    </div>
  </div>

  <!-- Download Button -->
  <button class="dl-btn" id="dlBtn" onclick="startDownload()">
    <div class="spinner"></div>
    <span class="dl-icon">⬇</span>
    <span id="dlBtnText">Download Now</span>
  </button>

  <!-- Progress -->
  <div class="progress-wrap" id="progressWrap">
    <div class="progress-bar indeterminate" id="progressBar"></div>
  </div>

  <!-- Log -->
  <div class="log-box" id="logBox"></div>

  <!-- Video Info -->
  <div class="vcard" id="vcard">
    <img id="vcardThumb" src="" alt=""/>
    <div>
      <div class="vcard-title" id="vcardTitle"></div>
      <div class="vcard-meta" id="vcardMeta"></div>
    </div>
  </div>

  <!-- Download Links -->
  <div class="links-section" id="linksSection">
    <div class="links-label">Ready to Download</div>
    <div id="linksList"></div>
  </div>

  <!-- Error -->
  <div class="err-box" id="errBox"></div>

  <!-- Footer -->
  <footer>
    VidSnap &nbsp;·&nbsp; Free &nbsp;·&nbsp; No ads &nbsp;·&nbsp; No limits
  </footer>
</div>

<script>
let quality = '720p';
let pollTimer = null;
let busy = false;

function setQ(el, q) {
  document.querySelectorAll('.q-btn').forEach(b => b.classList.remove('active'));
  el.classList.add('active');
  quality = q;
}

async function pasteUrl() {
  try {
    const t = await navigator.clipboard.readText();
    document.getElementById('urlInput').value = t;
  } catch {
    document.getElementById('urlInput').focus();
    document.getElementById('urlInput').select();
  }
}

function onUrlInput() {
  // Clear results when URL changes
  if (document.getElementById('linksSection').classList.contains('show')) {
    clearResults(false);
  }
}

function log(msg, cls) {
  const box = document.getElementById('logBox');
  box.classList.add('show');
  const icons = {'l-ok':'✓','l-er':'✗','l-info':'→','l-warn':'⚠ '};
  box.innerHTML += `<div class="${cls}">${icons[cls]||''} ${msg}</div>`;
  box.scrollTop = box.scrollHeight;
}

function clearResults(clearUrl=false) {
  if(pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  if(clearUrl) document.getElementById('urlInput').value = '';
  document.getElementById('logBox').innerHTML = '';
  document.getElementById('logBox').classList.remove('show');
  document.getElementById('linksSection').classList.remove('show');
  document.getElementById('linksList').innerHTML = '';
  document.getElementById('errBox').className = 'err-box';
  document.getElementById('vcard').className = 'vcard';
  document.getElementById('progressWrap').classList.remove('show');
}

function showErr(msg) {
  const e = document.getElementById('errBox');
  e.className = 'err-box show';
  e.innerHTML = msg;
}

function setLoading(on) {
  busy = on;
  const btn = document.getElementById('dlBtn');
  const txt = document.getElementById('dlBtnText');
  btn.disabled = on;
  txt.textContent = on ? 'Downloading...' : 'Download Now';
  document.getElementById('progressWrap').classList.toggle('show', on);
}

async function startDownload() {
  if (busy) return;
  const url = document.getElementById('urlInput').value.trim();
  if (!url) { showErr('⚠️ Please enter a video URL first!'); return; }

  clearResults();
  setLoading(true);
  log('Starting download...', 'l-info');
  log('Quality: ' + quality, 'l-info');

  try {
    const res = await fetch('/api/download', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ url, quality })
    });
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'Server error');

    log('Job started: ' + data.id, 'l-info');
    pollTimer = setInterval(() => pollJob(data.id), 900);
  } catch(e) {
    setLoading(false);
    showErr('❌ ' + e.message);
  }
}

async function pollJob(id) {
  try {
    const res = await fetch('/api/status/' + id);
    const d = await res.json();

    // Update log
    if (d.logs?.length) {
      const box = document.getElementById('logBox');
      box.classList.add('show');
      box.innerHTML = d.logs.map(l => {
        const cls = l.includes('ERROR')||l.includes('error') ? 'l-er' :
                    l.includes('Merging')||l.includes('Destination') ? 'l-ok' :
                    l.includes('%') ? 'l-warn' : 'l-info';
        return `<div class="${cls}">→ ${l}</div>`;
      }).join('');
      box.scrollTop = box.scrollHeight;
    }

    // Video info
    if (d.title || d.thumb) {
      const vc = document.getElementById('vcard');
      vc.className = 'vcard show';
      if (d.thumb) document.getElementById('vcardThumb').src = d.thumb;
      document.getElementById('vcardTitle').textContent = d.title || '';
      document.getElementById('vcardMeta').textContent = d.duration ? '⏱ ' + d.duration : '';
    }

    if (d.status === 'done') {
      clearInterval(pollTimer); pollTimer = null;
      setLoading(false);
      log('Download complete!', 'l-ok');

      // Show download link
      const list = document.getElementById('linksList');
      list.innerHTML = '';
      const a = document.createElement('a');
      a.className = 'dl-link';
      a.href = '/api/file/' + id;
      a.download = d.filename || 'video.mp4';
      a.innerHTML = `
        <div class="dl-link-left">
          <span class="dl-link-q">${d.filename || 'Download File'}</span>
          <span class="dl-link-m">Tap to save · ${d.size || ''}</span>
        </div>
        <span class="dl-link-ico">⬇</span>`;
      list.appendChild(a);
      document.getElementById('linksSection').classList.add('show');

      // Auto trigger
      setTimeout(() => a.click(), 300);

    } else if (d.status === 'error') {
      clearInterval(pollTimer); pollTimer = null;
      setLoading(false);
      log(d.error || 'Failed', 'l-er');
      showErr('❌ ' + (d.error || 'Download failed. Try a different quality or URL.'));
    }
  } catch(e) {
    // Network hiccup, keep polling
  }
}
</script>
</body>
</html>'''

# Download worker with improvements for YouTube Shorts
def run_download(job_id, url, quality):
    # Clean the URL
    url = url.strip()
    
    # Fix common YouTube URL issues
    if 'youtube.com/shorts/' in url or 'youtu.be/' in url:
        # Remove tracking parameters
        if '?si=' in url:
            url = url.split('?si=')[0]
    
    jobs[job_id]['logs'].append(f"Processing URL: {url}")
    
    fmt_map = {
        '144p':  'best[height<=144]',
        '360p':  'best[height<=360]',
        '720p':  'best[height<=720]',
        '1080p': 'best[height<=1080]',
        'best':  'best',
        'audio': 'bestaudio/best',
    }
    fmt = fmt_map.get(quality, 'best')
    
    out = os.path.join(DOWNLOAD_DIR, f'{job_id}_%(title).80s.%(ext)s')

    # First get metadata with better error handling
    try:
        ydl_opts = {
            'quiet': True, 
            'no_warnings': False,
            'extract_flat': False,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            jobs[job_id]['logs'].append("Fetching video information...")
            info = ydl.extract_info(url, download=False)
            
            if info is None:
                raise Exception("Could not extract video info")
            
            jobs[job_id]['title'] = info.get('title', '')[:80]
            thumb = info.get('thumbnail', '')
            jobs[job_id]['thumb'] = thumb
            dur = info.get('duration')
            if dur:
                m, s = divmod(int(dur), 60)
                h, m = divmod(m, 60)
                jobs[job_id]['duration'] = f'{h:02d}:{m:02d}:{s:02d}' if h else f'{m:02d}:{s:02d}'
            
            # Log available formats
            if 'formats' in info:
                formats = info['formats']
                jobs[job_id]['logs'].append(f"Found {len(formats)} available formats")
    except Exception as e:
        jobs[job_id]['logs'].append(f"Metadata fetch warning: {str(e)}")

    # Build command with better options for YouTube
    base_cmd = [sys.executable, '-m', 'yt_dlp',
                '--no-playlist',
                '--no-check-certificates',
                '--geo-bypass',
                '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                '--add-header', 'Accept-Language: en-US,en;q=0.9',
                '--extractor-retries', '3',
                '--retries', '3',
                '--fragment-retries', '3',
                '--file-access-retries', '3',
                '--output', out]
    
    if quality == 'audio':
        cmd = base_cmd + [
            '--format', 'bestaudio/best',
            '--extract-audio',
            '--audio-format', 'mp3',
            '--audio-quality', '0',
            url
        ]
    else:
        # YouTube specific format selection
        if 'youtube.com' in url or 'youtu.be' in url:
            if quality == 'best':
                format_spec = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
            else:
                height = quality.replace('p', '')
                format_spec = f'best[height<={height}][ext=mp4]/best[height<={height}]/best'
        else:
            format_spec = fmt
        
        cmd = base_cmd + [
            '--format', format_spec,
            '--merge-output-format', 'mp4',
            url
        ]

    jobs[job_id]['logs'].append(f"Starting download...")
    
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1)
        
        for line in proc.stdout:
            line = line.strip()
            if line:
                jobs[job_id]['logs'].append(line)
                if len(jobs[job_id]['logs']) > 50:
                    jobs[job_id]['logs'].pop(0)
        proc.wait()

        if proc.returncode == 0:
            # Find file
            found_files = []
            for f in sorted(os.listdir(DOWNLOAD_DIR), key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_DIR, x)), reverse=True):
                if f.startswith(job_id):
                    found_files.append(f)
            
            if found_files:
                fpath = os.path.join(DOWNLOAD_DIR, found_files[0])
                fname = found_files[0].split('_', 1)[-1] if '_' in found_files[0] else found_files[0]
                size = os.path.getsize(fpath)
                size_str = f'{size/1024/1024:.1f} MB' if size > 1024*1024 else f'{size/1024:.0f} KB'
                jobs[job_id].update({
                    'status': 'done',
                    'filepath': fpath,
                    'filename': fname,
                    'size': size_str
                })
                jobs[job_id]['logs'].append(f"Download complete! File: {fname} ({size_str})")
                return
            jobs[job_id].update({'status': 'error', 'error': 'File not found after download'})
        else:
            error_lines = [l for l in jobs[job_id]['logs'] if 'ERROR' in l]
            err = error_lines[-1] if error_lines else f'Download failed with code {proc.returncode}'
            jobs[job_id].update({'status': 'error', 'error': err})
    except Exception as e:
        jobs[job_id].update({'status': 'error', 'error': str(e)})
        jobs[job_id]['logs'].append(f"Exception: {str(e)}")

# HTTP Handler
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send_json(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path in ('/', '/index.html'):
            body = HTML.encode('utf-8')  # Explicit UTF-8 encoding
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            self.end_headers()
            self.wfile.write(body)
            return

        elif path.startswith('/api/status/'):
            job_id = path.split('/')[-1]
            if job_id in jobs:
                self.send_json(jobs[job_id])
            else:
                self.send_json({'error': 'Job not found'}, 404)

        elif path.startswith('/api/file/'):
            job_id = path.split('/')[-1]
            job = jobs.get(job_id)
            if job and job.get('filepath') and os.path.exists(job['filepath']):
                fpath = job['filepath']
                fname = job.get('filename', 'video.mp4')
                size = os.path.getsize(fpath)
                self.send_response(200)
                ct = 'audio/mpeg' if fname.endswith('.mp3') else 'video/mp4'
                self.send_header('Content-Type', ct)
                self.send_header('Content-Length', str(size))
                self.send_header('Content-Disposition', f'attachment; filename="{fname}"')
                self.end_headers()
                with open(fpath, 'rb') as f:
                    while chunk := f.read(65536):
                        try: self.wfile.write(chunk)
                        except: break
            else:
                self.send_json({'error': 'File not ready'}, 404)
        else:
            self.send_json({'error': 'Not found'}, 404)

    def do_POST(self):
        if self.path == '/api/download':
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length))
            url = body.get('url', '').strip()
            quality = body.get('quality', '720p')

            if not url:
                self.send_json({'error': 'URL is required'}, 400)
                return

            job_id = str(uuid.uuid4())[:8]
            jobs[job_id] = {
                'status': 'running',
                'logs': [],
                'title': '',
                'thumb': '',
                'duration': '',
                'filename': None,
                'filepath': None,
                'size': None,
                'error': None
            }
            threading.Thread(target=run_download, args=(job_id, url, quality), daemon=True).start()
            self.send_json({'id': job_id})
        else:
            self.send_json({'error': 'Not found'}, 404)

# Main
if __name__ == '__main__':
    ip = get_ip()
    ffmpeg_ok = bool(shutil.which('ffmpeg'))

    print(f"\n{'='*52}")
    print(f"  🎬  VidSnap 2.0 is running!")
    print(f"{'='*52}")
    print(f"\n  💻  Local:   http://localhost:{PORT}")
    print(f"  📱  Network: http://{ip}:{PORT}")
    print(f"\n  ffmpeg: {'✓ Ready (HD+audio works)' if ffmpeg_ok else '✗ Missing! Run: sudo apt install ffmpeg'}")
    print(f"  yt-dlp: ✓ Ready")
    print(f"  Downloads → {DOWNLOAD_DIR}")
    print(f"\n  Press Ctrl+C to stop")
    print(f"{'='*52}\n")

    server = HTTPServer(('0.0.0.0', PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n\n👋 VidSnap stopped!')
