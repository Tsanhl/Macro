"""Loopback-only server for the positioning board with a single-flight update endpoint. No AI calls.

Run: python3 serve.py   then open http://localhost:8768
"""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import subprocess
import sys
import threading
from urllib.parse import urlsplit

import live

ROOT = Path(__file__).resolve().parent
SERVED = {"/", "/index.html"}  # plus data/*.json


class Updates:
    def __init__(self):
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.state = {"state": "idle"}

    def status(self):
        with self.lock:
            return dict(self.state)

    def start(self):
        with self.lock:
            if self.state["state"] == "running":
                return dict(self.state)
            self.state = {"state": "running", "message": "正在抓取 CFTC、期貨及波動率數據，約需一分鐘…"}
        threading.Thread(target=self.worker, daemon=True).start()
        return self.status()

    def worker(self):
        p = subprocess.run([sys.executable, str(ROOT / "build.py")], cwd=ROOT, capture_output=True, text=True)
        (ROOT / "data").mkdir(exist_ok=True)
        (ROOT / "data" / ".last_build.log").write_text(p.stdout + p.stderr)
        result = ({"state": "done", "message": "已更新。"} if p.returncode == 0
                  else {"state": "failed", "message": "更新未完成，保留上一版數據；詳情見 data/.last_build.log。"})
        with self.lock:
            self.state = result


class Handler(SimpleHTTPRequestHandler):
    def json_response(self, code, value):
        data = json.dumps(value, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def local_host(self):
        return self.headers.get("Host") in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}")

    def do_GET(self):
        if not self.local_host():
            return self.json_response(403, {"error": "Invalid host"})
        path = urlsplit(self.path).path
        if path == "/api/update":
            return self.json_response(200, {**self.server.updates.status(), "token": self.server.updates.token})
        if path == "/api/live":
            try:
                return self.json_response(200, live.snapshot())
            except Exception as e:
                return self.json_response(502, {"error": f"盤中報價暫時取不到：{type(e).__name__}"})
        if path in SERVED or (path.startswith("/data/") and path.endswith(".json") and "/." not in path):
            return super().do_GET()
        self.send_error(404)

    def do_POST(self):
        if not self.local_host():
            return self.json_response(403, {"error": "Invalid host"})
        if (self.headers.get("Origin") != f'http://{self.headers.get("Host")}'
                or not secrets.compare_digest(self.headers.get("X-Refresh-Token", ""), self.server.updates.token)):
            return self.json_response(403, {"error": "Same-origin refresh token required"})
        if urlsplit(self.path).path != "/api/update":
            return self.json_response(404, {"error": "Unknown endpoint"})
        return self.json_response(202, self.server.updates.start())

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8768)
    args = ap.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(Handler, directory=str(ROOT)))
    server.updates = Updates()
    print(f"Positioning board: http://localhost:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
