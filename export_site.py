"""Static copy of the local board (http://localhost:8770) for GitHub Pages: https://tsanhl.github.io/Macro/

    python3 export_site.py             # write site/ from the current local data and check it
    python3 export_site.py --publish   # the same, then replace the gh-pages branch with site/ and push it

The four pages are rendered in-process with the same code the local server uses (server/macro_view.regroup with
server/serve.macro_parts for 宏觀 and 油價, server/pages for 新聞與連接 and AI 追蹤, institutional/index.html for 機構持倉),
so the HTML, CSS and JS are the local board's own and the light/dark look is unchanged. Data JSON is copied beside each
page. Features that need the local server (the update buttons, 60-second live quotes, the 30-minute news fetch) are
hidden and one line states the snapshot time in UK time; their requests are answered "not available" in the page, so
nothing errors.

Before anything is written for publishing, check() scans every output file and stops the export if it finds personal
or private material (holdings, watch list, price alerts, local paths, e-mail addresses, webhooks, tokens). The only
file read outside this folder is the price-alert webhook, so that its exact value can be checked for; it is never
copied or printed.
"""
import argparse
from datetime import datetime
import importlib.util
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
SERVER, MACRO, INST = HERE / "server", HERE / "macro", HERE / "institutional"
OUT = HERE / "site"
WEBHOOK = HERE.parent / "valuation and research" / "price_alerts" / "webhook.txt"
SITE_URL = "https://tsanhl.github.io/Macro/"

# Requests to the local server's api/ endpoints fail at once, so each page takes its own "server not running" path.
STATIC_HEAD = """<script>(function(){var f=window.fetch;window.fetch=function(u,o){var s=typeof u==='string'?u:(u&&u.url)||'';
if(/(^|\\/)api\\//.test(s))return Promise.reject(new Error('static snapshot'));return f.apply(this,arguments);};})();</script>
<style>#all,#upd,#update-data{display:none!important}.static-note{font-size:13px;color:var(--ink-2,#52514e)}</style>
"""

FORBIDDEN = [
    (r"holdings", "holdings file or wording"),
    (r"watchlist", "watch list"),
    (r"price_alerts|check_alerts|levels\.json\b(?!\?)", "price-alert files"),
    (r"analysis_lens|rulebook_log|analyse_thoughts|valuation and research|Research and valuation", "research files"),
    (r"/Users/|/home/[a-z]|C:\\\\Users", "local path"),
    (re.escape(Path.home().name), "local user name"),
    (r"trading chat|交易群", "trading chat"),
    (r"webhook|discord(?:app)?\.com/api", "webhook"),
    (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?:com|net|org|io|co|uk|hk|gov|edu)\b", "e-mail address"),
    (r"ghp_[A-Za-z0-9]{20,}|github_pat_|gho_[A-Za-z0-9]{20,}|\bsk-[A-Za-z0-9]{20,}|xox[abpr]-|AKIA[0-9A-Z]{16}"
     r"|Bearer\s+[A-Za-z0-9._-]{20,}|X-Refresh-Token\"?\s*:\s*\"[A-Za-z0-9_-]{16,}", "token"),
]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def inject(html, extra=""):
    """The static head block (and any page-specific extra) right after <head>."""
    i = html.find("<head>")
    if i < 0:
        raise ValueError("page has no <head>")
    i += len("<head>")
    return html[:i] + "\n" + STATIC_HEAD + extra + html[i:]


def swap(text, old, new, where):
    """Replace a literal the page uses for its "server not running" message; a page change that drops it only warns."""
    if old not in text:
        print(f"note: {where}: text not found, left as is: {old[:40]}")
        return text
    return text.replace(old, new)


def snapshot_note():
    now = datetime.now(ZoneInfo("Europe/London"))
    try:
        import json
        session = json.loads((MACRO / "site_private" / "data" / "refresh_meta.json").read_text())[0]["session"]
    except Exception:
        session = None
    stamp = now.strftime("%Y-%m-%d %H:%M")
    zh = f"靜態版本：{stamp}（英國時間）匯出" + (f"，數據截至 {session} 收市" if session else "") + "；更新按鈕、盤中報價及自動新聞擷取只在本地看板運作。"
    en = f"Static snapshot exported {stamp} UK time" + (f", data through the {session} close" if session else "") + "; updates, live quotes and the news fetch run only on the local board."
    return zh, en


def render(out=OUT):
    for need in (MACRO / "site_private" / "index.html", INST / "index.html"):
        if not need.exists():
            raise SystemExit(f"missing {need.relative_to(HERE)}: run python3 macro/refresh.py --render-only "
                             "(and python3 institutional/build.py) first")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    zh, en = snapshot_note()

    # server/ modules under their own names, as the local server imports them
    sys.path.insert(0, str(SERVER))
    board = load_module("board_serve", SERVER / "serve.py")
    pages = sys.modules["pages"]
    from macro_view import regroup

    # 外殼: the four buttons and iframes; the update-all button is hidden and the note takes its place
    shell = (SERVER / "index.html").read_text(encoding="utf-8")
    shell = swap(shell, '<span id="msg" role="status"></span>', f'<span id="msg" role="status" class="static-note">{zh}</span>', "index")
    (out / "index.html").write_text(inject(shell), encoding="utf-8")

    # 機構持倉: the institutional page as served (unchanged) plus its data
    inst = (INST / "index.html").read_text(encoding="utf-8")
    inst = swap(inst, "靜態模式：用 serve.py 啟動才有盤中數據。", f"{zh}以下用上一收市。", "inst live")
    inst = swap(inst, "靜態模式：用 serve.py 啟動才可更新", zh, "inst update")
    (out / "inst").mkdir()
    (out / "inst" / "index.html").write_text(inject(inst), encoding="utf-8")
    shutil.copytree(INST / "data", out / "inst" / "data", ignore=shutil.ignore_patterns(".*"))

    # 宏觀 (with 油價): the built page regrouped exactly as server/serve.py does on each request
    macro = regroup((MACRO / "site_private" / "index.html").read_text(encoding="utf-8"), board.macro_parts())
    (out / "macro").mkdir()
    (out / "macro" / "index.html").write_text(inject(macro), encoding="utf-8")
    js = (MACRO / "site_private" / "refresh.js").read_text(encoding="utf-8")
    js = swap(js, "資料更新服務未啟動。請以 python serve.py 開啟本地看板。", zh, "macro refresh.js")
    js = swap(js, "Updater unavailable. Start the local board with python serve.py.", en, "macro refresh.js")
    (out / "macro" / "refresh.js").write_text(js, encoding="utf-8")
    shutil.copytree(MACRO / "site_private" / "data", out / "macro" / "data", ignore=shutil.ignore_patterns(".*"))

    # 新聞與連接, AI 追蹤 and 讀法: rendered by server/pages.py and server/guide.py from the same local build
    import guide
    for name, html in (("news", pages.news_page()), ("ai", pages.ai_page()), ("guide", guide.guide_page())):
        (out / name).mkdir()
        (out / name / "index.html").write_text(inject(html), encoding="utf-8")

    (out / ".nojekyll").write_text("")
    return out


def scan(folder):
    """Every forbidden match in folder, as (file, what, excerpt)."""
    secret = None
    try:
        secret = WEBHOOK.read_text().strip() or None
    except OSError:
        pass
    hits = []
    for f in sorted(p for p in Path(folder).rglob("*") if p.is_file()):
        text = f.read_text(encoding="utf-8", errors="ignore")
        if secret and secret in text:
            hits.append((f, "webhook value", "(not shown)"))
        for pattern, what in FORBIDDEN:
            for m in re.finditer(pattern, text, re.I):
                hits.append((f, what, text[max(0, m.start() - 30):m.end() + 30].replace("\n", " ")))
    return hits


def check(folder=OUT):
    """Fails (exit 1) if the output holds anything private. Also proves the scan works on a planted sample first."""
    with tempfile.TemporaryDirectory() as t:
        for sample in ("see holdings.json", "/Users/someone/x", "mail me: a.b@example.com", "token ghp_" + "a" * 30):
            Path(t, "x.html").write_text(sample)
            if not scan(t):
                raise SystemExit(f"scan self-test failed on: {sample!r}")
    hits = scan(folder)
    for f, what, excerpt in hits:
        print(f"PRIVATE? {f.relative_to(folder)}: {what}: …{excerpt}…")
    if hits:
        raise SystemExit(f"{len(hits)} possible private item(s) in {folder.name}/; nothing published")
    files = [p for p in folder.rglob("*") if p.is_file()]
    print(f"check passed: {len(files)} files, {sum(p.stat().st_size for p in files) / 1e6:.1f} MB")


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def publish(folder=OUT, message=None):
    """Replace the gh-pages branch with folder's files only (a fresh orphan commit) and push it."""
    remote = git("remote", "get-url", "origin", cwd=HERE)
    stamp = datetime.now(ZoneInfo("Europe/London")).strftime("%Y-%m-%d %H:%M")
    with tempfile.TemporaryDirectory() as t:
        work = Path(t) / "pages"
        shutil.copytree(folder, work)
        git("init", "-q", "-b", "gh-pages", cwd=work)
        git("add", "-A", cwd=work)
        git("-c", "user.name=" + git("config", "user.name", cwd=HERE), "-c", "user.email=" + git("config", "user.email", cwd=HERE),
            "commit", "-q", "-m", message or f"Board snapshot {stamp} (UK time)", cwd=work)
        git("push", "-q", "--force", remote, "gh-pages:gh-pages", cwd=work)
    print(f"published to gh-pages; live in a minute or two at {SITE_URL}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--publish", action="store_true", help="push site/ to the gh-pages branch after the check")
    ap.add_argument("--message", help="commit message for the gh-pages commit")
    args = ap.parse_args()
    folder = render()
    check(folder)
    if args.publish:
        publish(folder, args.message)
