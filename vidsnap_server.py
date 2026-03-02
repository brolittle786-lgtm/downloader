
import os
import re
import json
import uuid
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, quote

PORT = int(os.environ.get("PORT", 8080))
DOWNLOAD_DIR = "/tmp"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

downloads = {}

class Handler(BaseHTTPRequestHandler):

    def do_POST(self):
        if self.path == "/api/download":
            length = int(self.headers.get('Content-Length'))
            body = self.rfile.read(length)
            data = json.loads(body)

            url = data.get("url")
            quality = data.get("quality", "best")

            dl_id = str(uuid.uuid4())
            output_template = os.path.join(DOWNLOAD_DIR, f"{dl_id}.%(ext)s")

            try:
                subprocess.run([
                    "yt-dlp",
                    "-f", quality,
                    "-o", output_template,
                    url
                ], check=True)

                for f in os.listdir(DOWNLOAD_DIR):
                    if f.startswith(dl_id):
                        downloads[dl_id] = f
                        break

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"id": dl_id}).encode())

            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode())

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path.startswith("/api/file/"):
            dl_id = parsed.path.split("/")[-1]

            if dl_id not in downloads:
                self.send_response(404)
                self.end_headers()
                return

            fname = downloads[dl_id]
            filepath = os.path.join(DOWNLOAD_DIR, fname)

            if not os.path.exists(filepath):
                self.send_response(404)
                self.end_headers()
                return

            # 🔥 Unicode safe filename fix
            fname = fname.replace("/", "_").replace("\\", "_")
            ascii_name = re.sub(r'[^\x00-\x7F]+','', fname)
            ascii_name = ascii_name.replace('"', '')
            utf8_name = quote(fname)

            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header(
                "Content-Disposition",
                f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{utf8_name}'
            )
            self.end_headers()

            with open(filepath, "rb") as f:
                self.wfile.write(f.read())

def run():
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Server running on port {PORT}")
    server.serve_forever()

if __name__ == "__main__":
    run()
