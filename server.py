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

# HTML (served to browser) - [Your existing HTML remains exactly the same]
HTML = '''<!DOCTYPE html>
... [your existing HTML code] ...
</html>'''

# Download worker with improvements for YouTube Shorts
def run_download(job_id, url, quality):
    # Clean the URL
    url = url.strip()
    
    # Fix common YouTube URL issues
    if 'youtube.com/shorts/' in url or 'youtu.be/' in url:
        # Ensure proper URL format
        if '?si=' in url:
            # Remove tracking parameters
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
            'no_warnings': False,  # Show warnings to debug
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
            
            # Log available formats for debugging
            if 'formats' in info:
                formats = info['formats']
                jobs[job_id]['logs'].append(f"Found {len(formats)} available formats")
                
                # Try to find a good format
                if quality != 'audio':
                    # For video, try to find a format with video and audio combined first
                    has_combined = False
                    for f in formats:
                        if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                            height = f.get('height', 0)
                            if quality == 'best' or (height and height <= int(quality.replace('p',''))):
                                jobs[job_id]['logs'].append(f"Found combined format: {height}p with {f.get('acodec')}")
                                has_combined = True
                                break
                    
                    if not has_combined:
                        jobs[job_id]['logs'].append("No combined video+audio format found, will merge separately")
    except Exception as e:
        jobs[job_id]['logs'].append(f"Metadata fetch warning: {str(e)}")
        # Continue anyway - download might still work

    # Build command with better options for YouTube
    base_cmd = [sys.executable, '-m', 'yt_dlp',
                '--no-playlist',
                '--no-check-certificates',
                '--geo-bypass',
                '--user-agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
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
        # For YouTube, try to get the best available format
        if 'youtube.com' in url or 'youtu.be' in url:
            # YouTube specific format selection
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
            '--embed-thumbnail',  # Add thumbnail
            '--embed-metadata',    # Add metadata
            url
        ]

    jobs[job_id]['logs'].append(f"Starting download with format: {format_spec if 'format_spec' in locals() else fmt}")
    
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
                # Extract filename without job_id prefix
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
            jobs[job_id]['logs'].append(f"Download failed: {err}")
    except Exception as e:
        jobs[job_id].update({'status': 'error', 'error': str(e)})
        jobs[job_id]['logs'].append(f"Exception: {str(e)}")

# [Rest of your HTTP Handler and Main code remains exactly the same]

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
            body = HTML.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

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
