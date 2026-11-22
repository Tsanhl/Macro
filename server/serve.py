"""One local web address for the boards: http://localhost:8770. No AI calls.

  /inst/   forwards to institutional/serve.py (port 8768), unchanged (機構持倉).
  /macro/  forwards to macro/serve.py (port 8766). Its page is regrouped as it is served (macro_view.py) into the 宏觀
           and 油價 pages, with rule-based text from macro_summary.py; nothing is written to macro/.
  /news/   新聞與連接, and /ai/ AI 追蹤: rendered here (pages.py) from the local build's data.
A board that is not already running is started here, and stopped again when this server exits.

News headlines: while this server runs, a background thread fetches the news feed (macro/news_feed.py, which merges
into macro/data/news_feed.json with its own de-duplication) every NEWS_EVERY seconds, and at start when the stored
feed is older than that. It skips a round while macro/refresh.py is running (that run fetches the news itself),
never blocks a page load and never raises into the server. The 新聞與連接 page and the 戰事最新進展 card read the stored
feed on every page load.
"""
import argparse
import atexit
from datetime import datetime
import fcntl
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

import macro_summary as ms
import us_economy_view
from macro_view import regroup
from guide import guide_page
from pages import VAL_VIEW, ai_page, news_page, val_page

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
BOARDS = {"inst": (8768, "institutional/serve.py"), "macro": (8766, "macro/serve.py")}
DASHBOARD = PROJECT / "macro"
NEWS_EVERY = 30 * 60  # seconds between background news fetches
children = []


def is_up(port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def ensure_board(name):
    port, script = BOARDS[name]
    if is_up(port):
        return
    children.append(subprocess.Popen([sys.executable, str(PROJECT / script), "--port", str(port)], cwd=PROJECT,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    for _ in range(100):
        if is_up(port):
            return
        time.sleep(0.2)
    raise RuntimeError(f"{name} board did not start on port {port}")


@atexit.register
def stop_children():
    for p in children:
        p.terminate()


def news_time(path=DASHBOARD / "data" / "news_feed.json"):
    """When the stored feed was last fetched (its attempted_at, as epoch seconds), or 0 when unknown."""
    try:
        row = json.loads(path.read_text(encoding="utf-8"))[0]
        return datetime.fromisoformat((row.get("attempted_at") or row["fetched_at"]).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def refresh_running(path=DASHBOARD / ".refresh" / "lock"):
    """True while macro/refresh.py holds its lock."""
    if not path.exists():
        return False
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(handle, fcntl.LOCK_UN)
    return False


def fetch_news():
    """One run of macro/news_feed.py in this process. Returns True when it wrote the feed; never raises."""
    try:
        if str(DASHBOARD) not in sys.path:
            sys.path.append(str(DASHBOARD))  # appended, so server's own modules keep their names
        import news_feed
        news_feed.build(DASHBOARD / "data")
        return True
    except Exception as e:
        print("background news fetch failed:", repr(e), flush=True)
        return False


def news_loop(stop, every=NEWS_EVERY, check=60, fetch=fetch_news):
    """Every `check` seconds: fetch when the stored feed (or this loop's own last try) is at least `every` seconds old and
    no data refresh is running. Uses the wall clock, so a computer waking from sleep catches up at once."""
    last_try = 0.0
    while True:
        try:
            now = time.time()
            if now - max(news_time(), last_try) >= every and not refresh_running():
                last_try = now
                fetch()
        except Exception as e:  # never let the loop die or reach the server
            print("background news loop:", repr(e), flush=True)
        if stop.wait(check):
            return


def part(name, fn, *args):
    """One card of the 宏觀 view; a data file that changed shape gives a short notice, not a broken page."""
    try:
        return fn(*args)
    except Exception as e:
        print(f"{name} failed:", repr(e), flush=True)
        return f'<div class="rb-card rb-wide"><p class="rb-sub">{name}暫時未能生成，其他部分不受影響。</p></div>'


def macro_parts():
    try:
        session = ms.load("refresh_meta")[0]["session"]
    except Exception:
        session = None
    # order (user, 2026-11-22): 現在要看, then 資金, 美債, 股債波動, 信用總表, AI 拋售; the dashboard's 市寬 and 板塊輪動 follow
    macro = [part("現在要看", ms.now_card, session), part("資金", ms.funds_card), part("美債", ms.bonds_card, session),
             part("股債波動", ms.vol_card), part("信用總表", ms.credit_table), part("AI 拋售", ms.ai_sell_card, session)]
    macro2 = []
    return {"macro": "\n".join(macro), "macro2": "\n".join(macro2), "oil": part("油市總結", ms.oil_summary),
            "oil_curve": part("Brent 期貨曲線", ms.oil_curve_card), "ovx": part("OVX 讀數", ms.ovx_html),
            "oil_positions": part("管理資金持倉", ms.oil_positions_card), "war": part("戰事最新進展", ms.war_card),
            "rotation_head": part("板塊輪動標題", ms.rotation_head, session), "breadth_head": part("市寬標題", ms.breadth_head),
            "useco": part("美國經濟", us_economy_view.page)}


def shell(view=None):
    """The tab shell. The local-only 估值 tab is added while the private view file exists (export_site.py reads
    index.html itself, so the public site never has it)."""
    html = (HERE / "index.html").read_text(encoding="utf-8")
    if not Path(view or VAL_VIEW).exists():
        return html
    return (html.replace("AI 追蹤</button>", 'AI 追蹤</button>\n  <button type="button" data-view="val" aria-pressed="false">估值</button>', 1)
                .replace('src="ai/"></iframe>', 'src="ai/"></iframe>\n  <iframe id="val" class="off" title="估值" src="val/"></iframe>', 1)
                .replace("const VIEWS = ['inst', 'macro', 'news', 'ai', 'guide']", "const VIEWS = ['inst', 'macro', 'news', 'ai', 'val', 'guide']", 1))


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, body, ctype="text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def local_host(self):
        return self.headers.get("Host") in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}")

    def forward(self, body=None):
        path = urlsplit(self.path)
        parts = path.path.split("/", 2)
        board, rest = parts[1], "/" + (parts[2] if len(parts) > 2 else "")
        port = BOARDS[board][0]
        ensure_board(board)
        headers = {"Accept": self.headers.get("Accept", "*/*")}
        if body is not None:
            headers["Origin"] = f"http://127.0.0.1:{port}"  # this server has already checked the real origin
            headers["X-Refresh-Token"] = self.headers.get("X-Refresh-Token", "")
        url = f"http://127.0.0.1:{port}{rest}" + (f"?{path.query}" if path.query else "")
        req = urllib.request.Request(url, data=body, headers=headers, method=self.command)
        try:
            with urllib.request.urlopen(req, timeout=120) as res:
                code, ctype, data = res.status, res.headers.get("Content-Type", "application/octet-stream"), res.read()
        except urllib.error.HTTPError as e:
            code, ctype, data = e.code, e.headers.get("Content-Type", "text/plain"), e.read()
        except OSError:
            return self.reply(502, json.dumps({"error": f"{board} board is not responding"}).encode(), "application/json")
        if board == "macro" and code == 200 and rest in ("/", "/index.html"):
            data = regroup(data.decode("utf-8"), macro_parts()).encode("utf-8")
        self.reply(code, data, ctype)

    def do_GET(self):
        if not self.local_host():
            return self.reply(403, b"Invalid host", "text/plain")
        path = urlsplit(self.path).path
        if path in ("/", "/index.html"):
            return self.reply(200, shell().encode("utf-8"))
        if path in ("/val/", "/val/index.html"):
            html = val_page()
            return self.reply(200, html.encode("utf-8")) if html else self.reply(404, b"Not found", "text/plain")
        if path in ("/news/", "/news/index.html"):
            return self.reply(200, news_page(local=True).encode("utf-8"))   # local only: adds the watchlist coverage line
        if path in ("/ai/", "/ai/index.html"):
            return self.reply(200, ai_page().encode("utf-8"))
        if path in ("/guide/", "/guide/index.html"):
            return self.reply(200, guide_page().encode("utf-8"))
        if path in ("/inst", "/macro", "/news", "/ai", "/val", "/guide"):
            self.send_response(302)
            self.send_header("Location", path + "/")
            self.end_headers()
            return None
        if path.startswith(("/inst/", "/macro/")):
            return self.forward()
        return self.reply(404, b"Not found", "text/plain")

    def do_POST(self):
        path = urlsplit(self.path).path
        if (not self.local_host() or self.headers.get("Origin") != f'http://{self.headers.get("Host")}'
                or not path.startswith(("/inst/", "/macro/"))):
            return self.reply(403, b"Same-origin requests only", "text/plain")
        return self.forward(body=b"")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--news-every", type=int, default=NEWS_EVERY // 60, help="minutes between background news fetches; 0 = off")
    ap.add_argument("--inst-port", type=int, default=BOARDS["inst"][0], help="port of the internal 機構持倉 source")
    ap.add_argument("--macro-port", type=int, default=BOARDS["macro"][0], help="port of the internal 宏觀 source")
    args = ap.parse_args()
    BOARDS["inst"] = (args.inst_port, BOARDS["inst"][1])
    BOARDS["macro"] = (args.macro_port, BOARDS["macro"][1])
    for name in BOARDS:
        ensure_board(name)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"One board: http://localhost:{server.server_port}", flush=True)
    if args.news_every > 0:
        threading.Thread(target=news_loop, args=(threading.Event(), args.news_every * 60), daemon=True, name="news").start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
