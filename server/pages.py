"""The 新聞與連接 and AI 追蹤 pages of the local board (http://localhost:8770/news/ and /ai/). No AI calls.

Both are rendered from the local build's data, which macro/build_site.py writes: macro/site_private/data/
news_connect.json (the hand-written issues of evidence/news_connect.json plus the headlines news_feed.py fetched
into macro/data/news_feed.json) and macro/site_private/data/ai_tracker.json (evidence/ai_tracker.json with
its "live" rows filled from board data). The headlines themselves are read from macro/data/news_feed.json on every
page load (live_feed), so the 30-minute background fetch of serve.py shows without a rebuild. The pages take the institutional board's palette (light and dark, chosen by
prefers-color-scheme or data-theme on <html>).
"""
from datetime import date, datetime
from html import escape
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent   # dashboard/
DATA = ROOT / "macro" / "site_private" / "data"
STOCKS = ROOT / "macro" / "data" / "stocks.json"   # S&P 500 members and basket names, local only (not in site_private)
WATCHLIST = ROOT.parent / "valuation and research" / "watchlist.md"   # local only; read for the coverage line only when news_page(local=True)
HOLDINGS = ROOT.parent / "valuation and research" / "holdings.json"   # local only; same
NEWS_FEED = ROOT / "macro" / "data" / "news_feed.json"  # local only

# The institutional board's palette (institutional/index.html), shared with macro_view.STYLE
LIGHT = ("--surface: #fcfcfb; --surface-2: #f4f3f0; --line: #e2e1dc; --grid: #ecebe7; --ink: #0b0b0b; --ink-2: #52514e; "
         "--ink-3: #7c7b76; --link: #2a78d6;")
DARK = ("--surface: #1a1a19; --surface-2: #232321; --line: #383835; --grid: #2c2c2a; --ink: #f0efec; --ink-2: #c3c2b7; "
        "--ink-3: #8f8e86; --link: #6ea8f0;")
CSS = """
:root { color-scheme: light; __LIGHT__ }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { color-scheme: dark; __DARK__ } }
:root[data-theme="dark"] { color-scheme: dark; __DARK__ }
* { box-sizing: border-box; }
body { margin: 0; background: var(--surface); color: var(--ink);
  font: 14px/1.6 -apple-system, BlinkMacSystemFont, "PingFang TC", "Noto Sans TC", "Helvetica Neue", sans-serif; }
main { max-width: 1400px; margin: 0 auto; padding: 20px 16px 40px; }
h1 { font-size: 24px; font-weight: 500; margin: 0 0 4px; }
h2 { font-size: 16px; font-weight: 600; margin: 0 0 8px; }
.sub { color: var(--ink-2); font-size: 13px; margin: 4px 0 8px; }
.card { border: 1px solid var(--line); border-radius: 8px; padding: 12px 14px; margin: 14px 0; }
.box { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { text-align: left; vertical-align: top; padding: 5px 8px; border-bottom: 1px solid var(--grid); }
th { font-size: 12px; font-weight: 500; color: var(--ink-2); white-space: nowrap; }
td.nowrap { white-space: nowrap; }
td.muted, .muted { color: var(--ink-3); }
ul, ol { margin: 4px 0; padding-left: 20px; } li { margin: 2px 0; }
a { color: var(--link); }
.chip { display: inline-block; background: var(--ink); color: var(--surface); border-radius: 4px; padding: 0 6px;
  font-size: 12px; font-weight: 600; line-height: 1.6; white-space: nowrap; }
.chip.out { background: transparent; color: var(--ink); border: 1px solid var(--ink); }
.tag { font-size: 11px; color: var(--ink-2); border: 1px solid var(--line); border-radius: 4px; padding: 0 4px; margin-left: 4px; white-space: nowrap; }
.tag.weak { border-style: dashed; }
h3 { font-size: 14px; font-weight: 600; margin: 12px 0 4px; }
h2.layer { font-size: 18px; font-weight: 500; margin: 22px 0 0; }
.count { font-size: 12px; font-weight: 400; color: var(--ink-3); margin-left: 8px; }
.cite { color: var(--ink-2); }
.lead { background: var(--surface-2); }
.issue { padding: 16px 20px 18px; }
.issue h2 { font-size: 18px; font-weight: 600; margin: 0; }
.issue .meta { color: var(--ink-3); font-size: 12px; margin: 2px 0 0; }
.issue .blk { margin-top: 18px; }
.issue .blk h3 { font-size: 12px; font-weight: 600; color: var(--ink-2); letter-spacing: .04em; margin: 0 0 6px; }
.issue .blk h3 .basis { font-weight: 400; color: var(--ink-3); letter-spacing: 0; margin-left: 6px; }
.issue p, .issue li { max-width: 110ch; }
.issue p.nowtext { font-size: 15px; line-height: 1.7; margin: 0; }
.issue ol.facts, .issue ul.meaning, .issue ul.watch { margin: 0; padding-left: 22px; }
.issue ol.facts li, .issue ul.meaning li, .issue ul.watch li { margin: 6px 0; }
.src { color: var(--ink-3); font-size: 12px; white-space: normal; }
.lab { display: inline-block; border: 1px solid var(--ink); border-radius: 4px; padding: 0 6px; font-size: 12px; font-weight: 600; white-space: nowrap; }
.lab.bad { border-width: 2px; border-style: double; } .lab.na { border-style: dashed; border-color: var(--ink-3); color: var(--ink-2); font-weight: 400; }
.px { white-space: nowrap; font-size: 12px; margin: 1px 0; } .px.nodata { color: var(--ink-3); }
.tk { color: var(--ink-3); font-size: 12px; display: block; }
.hint { color: var(--ink-2); font-size: 12px; display: block; margin-top: 2px; }
.issue ul.links, .issue ul.breaks { margin: 0; padding-left: 22px; } .issue ul.links li, .issue ul.breaks li { margin: 6px 0; }
.issue .conf { font-weight: 600; }
.issue table.log td:nth-child(1) { white-space: nowrap; }
.chip.n { text-decoration: none; margin-right: 4px; }
.strip { border-style: dashed; } .strip p { margin: 4px 0; }
.cover { font-size: 13px; }
.src a { color: var(--ink-3); text-decoration: underline; text-decoration-color: var(--line); }
.watch .when { font-weight: 600; margin-right: 6px; white-space: nowrap; }
table.impact { max-width: 1100px; }
table.impact td:nth-child(1) { min-width: 11rem; } table.impact td:nth-child(2) { min-width: 9rem; }
table.news td:nth-child(2) { min-width: 18rem; }
.note { display: block; color: var(--ink-2); font-size: 12px; margin-top: 1px; }
.now { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
.now > div { border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; background: var(--surface-2); }
@media (max-width: 600px) { th, td { padding: 4px 5px; } table { font-size: 12px; } .card { padding: 10px; } .now { grid-template-columns: 1fr; }
  /* long-text tables become one block per row on a phone: no sideways scrolling */
  table.stack, table.stack tbody, table.stack tr, table.stack td { display: block; width: auto; }
  table.stack tr:first-child { display: none; } table.stack tr { padding: 6px 0; border-bottom: 1px solid var(--line); }
  table.stack td { border: 0; padding: 1px 0; white-space: normal; } }
""".replace("__LIGHT__", LIGHT).replace("__DARK__", DARK)


def page(title, body):
    return (f'<!doctype html>\n<html lang="zh-Hant-HK">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>{escape(title)}</title>\n'
            f'<style>{CSS}</style>\n</head>\n<body>\n<main>\n{body}\n</main>\n</body>\n</html>\n')


def load(name):
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))[0]


def md(s):
    return f"{int(s[5:7])}月{int(s[8:10])}日" if s and len(s) >= 10 else "—"


def link(text, url):
    if url and str(url).startswith("https://"):
        return f'<a href="{escape(url)}" target="_blank" rel="noopener noreferrer">{escape(text or "來源")}</a>'
    return escape(text or "—")


def table(head, rows, cls=""):
    h = "".join(f"<th>{escape(x)}</th>" for x in head)
    return f'<div class="box"><table class="{cls}"><tr>{h}</tr>{"".join(rows)}</table></div>'


# ---------- 新聞與連接 ----------
# Layer 1: headlines fetched by macro/news_feed.py at each local refresh; layer 2: the hand-written issues of
# evidence/news_connect.json. build_site.py folds both into site_private/data/news_connect.json.

UK = ZoneInfo("Europe/London")
# The only fact labels. Something that cannot be checked against one of these sources is not on the page.
FACT_TAGS = ("已核實（一手文件）", "報道（具名媒體）", "第三方估算", "看板數據")
STATUS = ("進行中", "已有結論")
SHOW = 10  # headlines shown per group, newest first


def uk(iso, year=False):
    """A UTC time stamp as UK local time, e.g. 11月15日 14:30."""
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(UK)
    except (TypeError, ValueError):
        return "—"
    return (f"{d.year}年" if year else "") + f"{d.month}月{d.day}日 {d:%H:%M}"


def ymd(s):
    """md() with the year added when it is not the current year."""
    return md(s) if not s or s[:4] == str(date.today().year) else f"{s[:4]}年{md(s)}"


def feed_label(it):
    return '<span class="tag">官方公告</span>' if it.get("official") else '<span class="tag">報道</span>'


def news_rows(items):
    rows = []
    for it in items:
        note = f'<span class="note">含義：{escape(it["note"])}</span>' if it.get("note") else ""
        rows.append(f'<tr><td class="nowrap">{escape(uk(it.get("published")))}</td><td>{link(it.get("title"), it.get("link"))}{note}</td>'
                    f'<td>{escape(it.get("publisher") or "—")}{feed_label(it)}</td></tr>')
    return table(["時間（英國）", "標題", "來源"], rows, "stack news")


def _iso(v):
    try:
        return date.fromisoformat(str(v)).isoformat()
    except (TypeError, ValueError):
        return ""


def earliest_fact(iss):
    """The earliest source date among an issue's facts, or '' when none is dated."""
    ds = [_iso(x.get("date")) for f in iss.get("facts") or [] if isinstance(f, dict) for x in f.get("src") or [] if isinstance(x, dict)]
    return min([d for d in ds if d], default="")


def ordered_issues(issues):
    """Issues oldest story first: by `since`, falling back to the earliest dated fact; a tie is broken by the earliest dated
    fact, then by file order (the sort is stable). An issue with neither date goes last. Every number the page shows (card
    numbers, 議題 n tags, links, driver chips, the connection table) is this order, never the order of the file."""
    def key(iss):
        first = earliest_fact(iss)
        return (_iso(iss.get("since")) or first or "9999-12-31", first or "9999-12-31")
    return sorted(issues or [], key=key)


REF = re.compile(r"\{#([A-Za-z0-9_]+)\}")


def resolve_refs(obj, issues):
    """Replace {#issue_id} in every string of obj with 議題 n (n from the ordered issues), so card text refers to an issue by id
    and the number is computed at render. An id that names no issue becomes 議題（不存在）."""
    num = {i.get("id"): n for n, i in enumerate(issues, 1)}
    def walk(o):
        if isinstance(o, str):
            return REF.sub(lambda m: f"議題 {num[m.group(1)]}" if m.group(1) in num else "議題（不存在）", o)
        if isinstance(o, list):
            return [walk(x) for x in o]
        if isinstance(o, dict):
            return {k: walk(v) for k, v in o.items()}
        return o
    return walk(obj)


def groups(feed, issues):
    """The headline groups: one per feed topic that belongs to an issue, in issue order, each marked with its issue number.
    A group appears when an issue is written for it; topics with no issue are listed by unclaimed() in the
    未有議題的主題 strip instead of being dropped. At most SHOW headlines, newest first."""
    items = sorted((x for x in feed.get("items") or [] if isinstance(x, dict)), key=lambda x: x.get("published") or "", reverse=True)
    names = {t.get("id"): t.get("name") or t.get("id") for t in feed.get("topics") or []}
    owner, order = {}, []
    for n, iss in enumerate(ordered_issues(issues), 1):
        for t in iss.get("topics") or []:
            if t in names and t not in owner:
                owner[t] = n
                order.append(t)
    return [dict(id=t, name=names[t], issue=owner.get(t), items=[x for x in items if x.get("topic") == t][:SHOW]) for t in order]


def unclaimed(feed, issues):
    """The feed topics that no issue claims, in feed order: [{id, name, n, newest}] with the number of headlines in the last
    seven days and the newest headline. These used to be dropped silently; the page lists them so a gap in the issues shows."""
    claimed = {t for iss in issues for t in iss.get("topics") or []}
    items = sorted((x for x in feed.get("items") or [] if isinstance(x, dict)), key=lambda x: x.get("published") or "", reverse=True)
    out = []
    for t in feed.get("topics") or []:
        tid = t.get("id")
        if not tid or tid in claimed:
            continue
        mine = [x for x in items if x.get("topic") == tid]
        out.append(dict(id=tid, name=t.get("name") or tid, n=len(mine), newest=mine[0] if mine else None))
    return out


ELSEWHERE = {"war": "（戰事最新進展另見宏觀頁的油價子頁）"}


def unclaimed_strip(feed, issues):
    rows = unclaimed(feed, issues)
    if not rows:
        return ""
    body = []
    for r in rows:
        new = r["newest"]
        head = (f'{link(new.get("title"), new.get("link"))} <span class="muted">{escape(uk(new.get("published")))}'
                f'（{escape(new.get("publisher") or "—")}）</span>') if new else '<span class="muted">最近七日沒有標題</span>'
        body.append(f'<tr><td><b>{escape(r["name"])}</b>{escape(ELSEWHERE.get(r["id"], ""))}</td><td class="nowrap">{r["n"]}</td><td>{head}</td></tr>')
    return ('<section class="card strip"><h2>未有議題的主題</h2><p class="sub">這些主題有新聞，但還沒有人手議題把它連到股票；'
            '表示看板有盲點，不是沒有事發生。寫了議題（在 topics 填上主題 id）才會展開成一組。</p>'
            + table(["主題", "最近七日標題數", "最新一則"], body, "stack") + "</section>")


# ---------- price reaction (read from the board's own data, never written by hand) ----------

def tkey(t):
    return str(t).strip().upper().replace(".", "-")


def price_data(data_dir=None):
    """ticker -> board row (sectors.json of the built page and macro/data/stocks.json: r1d, r1w, rel1w, r1m, rel1m ...). {} when unreadable."""
    d = Path(data_dir) if data_dir else None
    rows = {}
    # sectors.json is in the built page's data; stocks.json is only in macro/data/ (site_private/ no longer carries it)
    for src in ((d or DATA) / "sectors.json", (d / "stocks.json") if d else STOCKS):
        try:
            for x in json.loads(src.read_text(encoding="utf-8")):
                rows[x["ticker"]] = x
        except (OSError, ValueError, TypeError, KeyError):
            pass
    return rows


def price_session(data_dir=None):
    """The board's last observation date (refresh_meta.json), or ''."""
    try:
        return str(json.loads(((Path(data_dir) if data_dir else DATA) / "refresh_meta.json").read_text(encoding="utf-8"))[0].get("session") or "")
    except (OSError, ValueError, TypeError, IndexError, AttributeError):
        return ""


def px_get(px, t):
    return px.get(t) or px.get(str(t).upper()) or px.get(tkey(t)) or px.get(str(t).upper().replace("-", "."))


def pct(v):
    return "—" if v is None else f"{v:+.1f}%"


def reaction(row, px):
    """(lines, label, hint) for one stock row. label is 符合論點 / 與論點相反 / 不明, or '' when the row states no expectation.
    The comparison is the sign of the one-week return relative to the S&P 500 (rel1w, the board's own column) against `expected`;
    when the tickers of a row do not all point the same way, or the board has no data, it is 不明. No threshold is used."""
    got = [(t, px_get(px, t)) for t in row.get("tickers") or []]
    lines = [f'<div class="px"><b>{escape(t)}</b> 1日{escape(pct(x.get("r1d")))}｜一週{escape(pct(x.get("r1w")))}'
             f'（相對大市{escape(pct(x.get("rel1w")))}）｜一月相對{escape(pct(x.get("rel1m")))}</div>' if x else
             f'<div class="px nodata">{escape(t)}：看板沒有數據</div>' for t, x in got]
    have = [x for _, x in got if x]
    w = [x["rel1w"] for x in have if x.get("rel1w") is not None]
    m = [x["rel1m"] for x in have if x.get("rel1m") is not None]

    def side(v):
        return "up" if v and all(i > 0 for i in v) else "down" if v and all(i < 0 for i in v) else None
    exp, label, hint = row.get("expected"), "", ""
    if exp in ("跑贏", "跑輸"):
        sw = side(w)
        if sw is None:
            label, hint = "不明", "看板沒有這些股票的一週數據" if not w else "組內各股一週方向不一，不合併判斷"
        else:
            label = "符合論點" if (sw == "up") == (exp == "跑贏") else "與論點相反"
        sm = side(m)
        if sw and sm and sw != sm:
            hint = (hint + "；" if hint else "") + "一週與一個月的相對方向不同"
    elif exp == "無關":
        label, hint = "不明", "論點判為無關，不比較方向"
    return lines, label, hint


# ---------- watchlist coverage ----------
# The watch list is private. Which names are groups, and the board tickers that stand for each, live in a local file
# outside this repository; without it every name is its own ticker and nothing about the list is in this code.
WATCH_GROUPS_FILE = ROOT.parent / "valuation and research" / "watch_groups.json"


def watch_groups(path=None):
    """({group name: [tickers]}, {lower-case alias: group name}) from the private local file; ({}, {}) when it is absent."""
    try:
        d = json.loads(Path(path or WATCH_GROUPS_FILE).read_text(encoding="utf-8"))
        return dict(d.get("groups") or {}), {k.lower(): v for k, v in (d.get("aliases") or {}).items()}
    except (OSError, ValueError, AttributeError, TypeError):
        return {}, {}


def watch_items_list(watchlist=None, holdings=None, groups=None):
    """[(name, {ticker keys})]: the names in the first paragraph of the private watch-list file, plus any held name or
    pick in the private holdings file that is not already inside one of them. [] when the watch-list file cannot be read."""
    grp, alias = watch_groups(groups)
    try:
        text = Path(watchlist or WATCHLIST).read_text(encoding="utf-8")
    except OSError:
        return []
    m = (re.search(r"長期追蹤\s*\d+\s*項\*{0,2}（([^；）]+)", text)
         or re.search(r"Long-term list of\s*\d+\s*items\*{0,2}\s*\(([^;)]+)", text, re.I))
    names = [x.strip() for x in re.split(r"、|,\s*", m.group(1)) if x.strip()] if m else []
    names = [alias.get(n.lower(), n) for n in names]
    items = [(n, {tkey(t) for t in grp.get(n, [n])}) for n in names]
    try:
        h = json.loads(Path(holdings or HOLDINGS).read_text(encoding="utf-8"))
        for t in list(h.get("held") or []) + list(h.get("picks") or []):
            t = t if isinstance(t, str) else (t or {}).get("ticker", "")
            if t and not any(tkey(t) in ks for _, ks in items):
                items.append((t, {tkey(t)}))
    except (OSError, ValueError, AttributeError, TypeError):
        pass
    return items


def touched(issues):
    out = set()
    for iss in issues:
        for r in (iss.get("stocks") or []) + (iss.get("watch") or []):
            out |= {tkey(t) for t in r.get("tickers") or []}
    return out


def coverage_line(issues, items=None):
    """The coverage line for `items` = watch_items_list(); no line when items is None or empty. It never reads watchlist.md or
    holdings.json by itself: those are private and this page is also rendered into the public static site (export_site.py)."""
    if not items:
        return ""
    t = touched(issues)
    gaps = [n for n, ks in items if not (ks & t)]
    head = f'觀察名單覆蓋：{len(items)} 項中 {len(items) - len(gaps)} 項有議題的受影響股票或要留意涉及（按 tickers 欄位）。'
    tail = ("沒有任何議題涉及：" + "、".join(escape(n) for n in gaps) + "。") if gaps else "全部都有議題涉及。"
    return f'<p class="sub cover"><b>{escape(head)}</b>{tail}</p>'


def feed_section(feed, issues):
    when = escape(uk(feed.get("fetched_at"), True)) if feed.get("fetched_at") else "未有"
    out = [f'<p class="sub">上次成功擷取：{when}（英國時間）；看板運行時每 30 分鐘擷取一次。只收官方網站（官方公告）及允許名單上的具名新聞機構（報道）；'
           f'每組顯示最新 {SHOW} 則，含義只在打開原文後才寫。</p>']
    failed = [f for f in feed.get("feeds") or [] if not f.get("ok")]
    if feed.get("attempted_at") and feed.get("attempted_at") != feed.get("fetched_at"):
        out.append(f'<p class="sub">{escape(uk(feed["attempted_at"], True))} 的擷取全部失敗，以下是上次成功擷取的標題。</p>')
    elif failed:
        out.append('<p class="sub">今次擷取失敗的來源（保留上次的標題）：' + "；".join(
            f'{escape(f.get("name") or f.get("id") or "")}（上次成功：{escape(uk(f.get("last_ok"))) if f.get("last_ok") else "未有"}）'
            for f in failed) + "。</p>")
    cards = ["".join(out)]
    gs = groups(feed, issues)
    for g in gs:
        mark = f'<span class="tag">議題 {g["issue"]}</span>' if g["issue"] else ""
        body = news_rows(g["items"]) if g["items"] else '<p class="muted">最近七日沒有擷取到這一組的標題。</p>'
        cards.append(f'<section class="card"><h2>{escape(g["name"])}{mark}</h2>{body}</section>')
    if not gs:
        cards.append('<section class="card"><p class="muted">未有擷取紀錄：執行 python3 macro/refresh.py 後會擷取標題。</p></section>')
    cards.append(unclaimed_strip(feed, issues))
    return "\n".join(c for c in cards if c)


def src_tags(src):
    """〔label：source date；source date〕 per label, each source linked when it has a URL."""
    by = {}
    for x in src or []:
        if isinstance(x, dict) and x.get("tag") in FACT_TAGS:
            by.setdefault(x["tag"], []).append(link(x.get("name"), x.get("url")) + (f" {escape(md(x['date']))}" if x.get("date") else ""))
    return "".join(f'<span class="src">〔{escape(t)}：{"；".join(v)}〕</span>' for t, v in by.items())


NEW_STOCK_KEYS = ("tickers", "channel", "expected", "reaction_note")


def stock_rows(rows, px=None, session=None):
    """The 受影響股票及影響 table. Rows that carry none of the new fields keep the old three columns; otherwise the table is
    影響項目 (channel), 按論點應 (expected), 價格反應 and 原因 (an old `effect` is put in front of it), which is read from the board's price data, with a text label
    (符合論點／與論點相反／不明) comparing it with the expectation. A hand line (reaction_note) explains a tape that disagrees."""
    if not any(k in r for r in rows for k in NEW_STOCK_KEYS):
        out = [f'<tr><td><b>{escape(r.get("who", ""))}</b></td><td>{escape(r.get("effect", ""))}</td><td>{escape(r.get("why", ""))}</td></tr>'
               for r in rows]
        return table(["公司／組別", "影響（方向）", "原因"], out, "stack impact")
    px = price_data() if px is None else px
    session = price_session() if session is None else session
    out = []
    for r in rows:
        lines, label, hint = reaction(r, px)
        tk = f'<span class="tk">{escape("、".join(r["tickers"]))}</span>' if r.get("tickers") else ""
        lab = f'<span class="lab{" bad" if label == "與論點相反" else " na" if label == "不明" else ""}">{escape(label)}</span>' if label else ""
        react = "".join(lines) + lab + (f'<span class="hint">{escape(hint)}</span>' if hint else "")
        note = f'<span class="hint">{escape(r["reaction_note"])}</span>' if r.get("reaction_note") else ""
        why = (f'{r["effect"]}：' if r.get("effect") else "") + (r.get("why") or "")
        out.append(f'<tr><td><b>{escape(r.get("who", ""))}</b>{tk}</td><td>{escape(r.get("channel") or "—")}</td>'
                   f'<td>{escape(r.get("expected") or "—")}</td><td>{react or "—"}</td>'
                   f'<td>{escape(why)}{note}</td></tr>')
    when = f"看板 {md(session)}收市" if session else "看板"
    return table(["公司／組別", "影響項目", "按論點應", f"價格反應（{when}，相對標普 500；標籤按一週）", "原因"], out, "stack impact")


def watch_items(rows, today):
    def key(w):
        return (0, w["date"]) if w.get("date") else (1, "")
    out = []
    for w in sorted(rows, key=key):
        d = w.get("date")
        when = (escape(md(d)) + ("（已過，待檢討）" if d < today else "")) if d else escape(w.get("when") or "未公佈")
        br = {"確認": "成立則確認看法", "推翻": "成立則推翻看法"}.get(w.get("breaks"))
        tag = f'<span class="tag">{br}</span>' if br else ""
        tk = f'（{escape("、".join(w["tickers"]))}）' if w.get("tickers") else ""
        out.append(f'<li><span class="when">{when}</span>{tag}如果{escape(w.get("if", ""))} → {escape(w.get("then", ""))}{tk}</li>')
    return f'<ul class="watch">{"".join(out)}</ul>'


def issue_edges(issues):
    """Which issues each issue points to: every {#id} written in its text (facts, meaning, stocks), plus the `links` of an old
    card. Computed from the unresolved text, so it must run before resolve_refs. {id: [ids]} in first-mention order."""
    ids = {i.get("id") for i in issues}
    out = {}
    for i in issues:
        found = REF.findall(json.dumps({k: v for k, v in i.items() if k != "links"}, ensure_ascii=False))
        found += [l.get("to") for l in i.get("links") or [] if isinstance(l, dict)]
        out[i.get("id")] = [t for n, t in enumerate(found) if t in ids and t != i.get("id") and t not in found[:n]]
    return out


def meta_line(iss):
    return f'<p class="meta">上次檢討：{escape(md(iss.get("reviewed")))}</p>'


def fold_meaning(iss, today):
    """The 含義 list. An old card's separate breaks_if and watch entries are folded into it as two lines (推翻條件, 要看), so a
    card needs no blocks besides the three; new cards write those two lines inside `meaning` themselves."""
    items = [escape(m) for m in iss.get("meaning") or []]
    if iss.get("breaks_if") and not any(str(m).startswith("推翻條件") for m in iss.get("meaning") or []):
        items.append(f'推翻條件：{escape(iss["breaks_if"])}')
    if iss.get("watch") and not any(str(m).startswith("要看") for m in iss.get("meaning") or []):
        bits = []
        for w in sorted(iss["watch"], key=lambda w: (0, w["date"]) if w.get("date") else (1, "")):
            d = w.get("date")
            when = (md(d) + ("（已過，待檢討）" if d < today else "")) if d else (w.get("when") or "未公佈")
            bits.append(f'{when}如果{w.get("if", "")} → {w.get("then", "")}')
        items.append("要看：" + escape("；".join(bits)))
    return "".join(f"<li>{m}</li>" for m in items)


def issue_card(n, iss, today, issues=None, px=None, session=None):
    """One issue card: exactly three blocks — 事實與連接, 含義, 受影響股票及影響. (`now` of an old card is still shown above
    them when present; since, confidence and log are kept in the file but not shown.)"""
    status = iss.get("status") if iss.get("status") in STATUS else "進行中"
    chip = f'<span class="chip{"" if status == "進行中" else " out"}">{escape(status)}</span>'
    facts = "".join(f'<li>{escape(f.get("text") or "")} {src_tags(f.get("src"))}</li>' for f in iss.get("facts") or [])
    meaning = fold_meaning(iss, today)
    none = '<p class="muted">未寫。</p>'

    def blk(title, body, basis=""):
        b = f'<span class="basis">{escape(basis)}</span>' if basis else ""
        return f'<div class="blk"><h3>{escape(title)}{b}</h3>{body}</div>'
    return (f'<section class="card issue" id="issue-{escape(iss.get("id") or "")}">'
            f'<h2>{n}. {escape(iss.get("title") or "")} {chip}</h2>'
            + meta_line(iss)
            + (blk("正在發生甚麼", f'<p class="nowtext">{escape(iss["now"])}</p>') if iss.get("now") else "")
            + blk("事實與連接", f'<ol class="facts">{facts}</ol>' if facts else none, "每條：事實＋它連到哪裏")
            + blk("含義", f'<ul class="meaning">{meaning}</ul>' if meaning else none, "推論（依據上面的事實）")
            + blk("受影響股票及影響", stock_rows(iss["stocks"], px, session) if iss.get("stocks") else none, "對業務的影響，不是買賣建議")
            + "</section>")


def driver_block(doc):
    """本週主導因果. `driver` is one sentence (old shape) or a list of {line, issues: [issue ids]} that must together name every
    open issue; ids that name no issue are shown as such, and open issues no line names are listed so the top line cannot go
    out of step with the cards."""
    issues = ordered_issues(doc.get("issues"))
    num = {i.get("id"): n for n, i in enumerate(issues, 1)}
    d = doc.get("driver")
    if isinstance(d, dict):
        d = [d]
    if not isinstance(d, list):
        return ('<section class="card lead"><h2>本週主導因果（一句話）</h2>'
                f'<p>{escape(d or "未填寫。")}</p></section>')
    paras, named = [], set()
    for x in d:
        if not isinstance(x, dict):
            continue
        ids = [i for i in x.get("issues") or []]
        named |= set(ids)
        chips = "".join(f'<a class="chip out n" href="#issue-{escape(i)}">議題 {num[i]}</a>' if i in num else
                        f'<span class="chip out n">{escape(str(i))}（不存在）</span>' for i in ids)
        paras.append(f'<p>{chips} {escape(x.get("line") or "")}</p>')
    open_ids = [i.get("id") for i in issues if (i.get("status") if i.get("status") in STATUS else "進行中") == "進行中"]
    miss = [i for i in open_ids if i not in named]
    warn = ("<p class='muted'>以下進行中議題未被上面任何一行提及：" + "、".join(
        f'<a href="#issue-{escape(i)}">議題 {num[i]}</a>' for i in miss) + "。</p>") if miss else ""
    return ('<section class="card lead"><h2>本週主導因果</h2>' + "".join(paras) + warn + "</section>")


def cross_section(doc, watch=None, edges=None):
    """議題之間的連接, compact: the common lever (doc["lever"] = {name, issue, text}) in one paragraph, one line saying which
    issues each issue points to (read from the {#id} references inside the cards, so there is nothing to keep in step), and the
    watchlist coverage line."""
    issues = ordered_issues(doc.get("issues"))
    num = {i.get("id"): n for n, i in enumerate(issues, 1)}
    edges = issue_edges(issues) if edges is None else edges
    out = []
    lev = doc.get("lever")
    if isinstance(lev, dict) and lev.get("name"):
        hub = lev.get("issue")
        where = f'（<a href="#issue-{escape(hub)}">議題 {num[hub]}</a>）' if hub in num else ""
        out.append(f'<p><b>共同槓桿：{escape(lev["name"])}</b>{where}。{escape(lev.get("text") or "")}</p>')
    bits = []
    for n, i in enumerate(issues, 1):
        to = [t for t in edges.get(i.get("id"), []) if t in num]
        if to:
            bits.append(f'<span class="nowrap"><a href="#issue-{escape(i.get("id") or "")}">議題 {n}</a> → '
                        + "、".join(f'<a href="#issue-{escape(t)}">{num[t]}</a>' for t in to) + "</span>")
    if bits:
        out.append('<p class="sub">卡內互相引用：' + "　".join(bits) + "</p>")
    cov = coverage_line(issues, watch)
    if not out and not cov:
        return ""
    return '<section class="card"><h2>議題之間的連接</h2>' + "".join(out) + cov + "</section>"


def news_body(doc, today=None, px=None, session=None, watch=None):
    today = today or date.today().isoformat()
    px = price_data() if px is None else px
    session = price_session() if session is None else session
    issues = ordered_issues(doc.get("issues"))
    edges = issue_edges(issues)   # read before the {#id} references are turned into numbers
    doc = resolve_refs({**doc, "issues": issues}, issues)   # numbers come from this order; {#id} in any text becomes 議題 n
    issues = doc["issues"]
    out = ['<h1>新聞與連接</h1>',
           f'<p class="sub">議題人手更新：{escape(doc.get("updated") or "—")}。{escape(doc.get("rule") or "")}</p>',
           driver_block(doc),
           cross_section(doc, watch, edges),
           '<h2 class="layer">一、最新新聞（自動擷取）</h2>',
           feed_section(doc.get("feed") or {}, issues),
           '<h2 class="layer">二、議題（人手撰寫）</h2>']
    if doc.get("missing"):
        out.append("<p class='sub'>未有 evidence/news_connect.json。</p>")
    out += [issue_card(n, i, today, issues, px, session) for n, i in enumerate(issues, 1)] or ['<p class="muted">未有議題。</p>']
    return "\n".join(x for x in out if x)


def live_feed(doc):
    """doc with its headlines taken from the stored feed (macro/data/news_feed.json, which serve.py's background fetch
    updates every 30 minutes) instead of the copy made at the last build. The hand-written 含義 and issue of a headline
    are carried over by link from the built page; when the stored feed cannot be read, the built copy stays."""
    try:
        row = json.loads(NEWS_FEED.read_text(encoding="utf-8"))[0]
        built = doc.get("feed") or {}
        if (row.get("attempted_at") or "") < (built.get("attempted_at") or ""):
            return doc
        hand = {x["link"]: x for x in built.get("items") or [] if isinstance(x, dict) and x.get("link")}
        items = [{**x, "note": (hand.get(x.get("link")) or {}).get("note") or "", "issue": (hand.get(x.get("link")) or {}).get("issue")}
                 for x in row["items"] if isinstance(x, dict)]
        return {**doc, "feed": {**{k: v for k, v in row.items() if k != "items"}, "items": items}}
    except (OSError, ValueError, IndexError, KeyError, TypeError, AttributeError):
        return doc


def news_page(local=False):
    """local=True (only server/serve.py passes it) adds the watchlist coverage line, which reads the private watchlist.md and
    holdings.json; the default has no such line, so export_site.py's static copy never carries those names."""
    try:
        body = news_body(live_feed(load("news_connect")), watch=watch_items_list() if local else None)
    except (OSError, ValueError, KeyError, IndexError, TypeError, AttributeError) as e:
        print("news page failed:", repr(e), flush=True)
        body = "<h1>新聞與連接</h1><p class='sub'>資料暫時未能載入；執行 python3 macro/refresh.py --render-only 後重新整理。</p>"
    return page("新聞與連接", body)


# ---------- AI 追蹤 ----------

def stage_chip(n, label, cls="chip"):
    return f'<span class="{cls}">階段{escape(label)}</span>' if n else ""


def if_then(x):
    then = x.get("then", "")
    verb = "則屬" if then.startswith("階段") else "則"
    return f'<li>如果{escape(x.get("if", ""))}，{verb}{escape(then)}。</li>'


def ai_body(doc, today=None):
    if doc.get("missing"):
        return "<h1>AI 追蹤</h1><p class='sub'>未有 evidence/ai_tracker.json。</p>"
    today = today or date.today().isoformat()
    stages = {s["n"]: s for s in doc.get("stages", [])}
    cur = doc.get("current") or {}
    fr, mj = (cur.get("frontier") or {}), (cur.get("majority") or {})
    out = ['<h1>AI 追蹤</h1>',
           f'<p class="sub">人手更新：{escape(doc.get("updated") or "—")}；現處階段判斷日期：{escape(cur.get("judged_on") or "—")}。'
           f'{escape(doc.get("reading_rule") or "")}階段不用數字門檻、分數或機率。</p>']
    rows = []
    for n in sorted(stages):
        s = stages[n]
        marks = " ".join(f'<span class="chip out">{m}</span>' for m, x in (("最前沿", fr), ("多數公司所在", mj)) if x.get("stage") == n)
        rows.append(f'<tr><td class="nowrap">{stage_chip(n, s["label"])}</td><td class="nowrap"><b>{escape(s["name"])}</b></td>'
                    f'<td>{escape(s["means"])}</td><td class="nowrap">{marks}</td></tr>')
    out.append('<section class="card"><h2>1. 階段定義</h2><p class="sub">六個階段是我們自己按資金鏈上看得到的證據排列；'
               '某階段要有證據行顯示其定義證據才算。</p>' + table(["階段", "名稱", "定義證據", "現時"], rows) + "</section>")

    def block(title, x):
        s = stages.get(x.get("stage"), {})
        ev = "".join(f"<li>{escape(e)}</li>" for e in x.get("evidence", []))
        return (f'<div><h2>{escape(title)}：{stage_chip(x.get("stage"), s.get("label", ""))} {escape(s.get("name", "—"))}</h2>'
                f'<p class="sub">{escape(x.get("who") or "")}</p><ul>{ev}</ul></div>')
    miss = "".join(f"<li>{escape(m)}</li>" for m in cur.get("missing", []))
    out.append(f'<section class="card"><h2>2. 現處階段（{escape(md(cur.get("judged_on")))}判斷）</h2><div class="now">'
               + block("最前沿", fr) + block("多數公司所在", mj) + "</div>"
               + f'<h2 style="margin-top:12px">下一階段還欠甚麼證據</h2><ul>{miss}</ul></section>')

    def key(w):
        if w.get("date"):
            return (0, w["date"])
        return (1 if w.get("when") == "每次看板刷新" else 2, "")
    rows = []
    for w in sorted(doc.get("watch", []), key=key):
        d = w.get("date")
        when = escape(d) + ('<br><span class="muted">已過，待更新</span>' if d and d < today else "") if d else f'<span class="muted">{escape(w.get("when") or "未公佈")}</span>'
        basis = f'<span class="tag">{escape(w["basis"])}</span>' if w.get("basis") else ""
        rows.append(f'<tr><td class="nowrap">{when}</td><td>{escape(w.get("event", ""))}{basis}</td>'
                    f'<td><ul>{"".join(if_then(x) for x in w.get("if", []))}</ul></td></tr>')
    out.append('<section class="card"><h2>3. 之後要看</h2><p class="sub">日期只列公司或聯儲在一手來源確認的日期；其餘寫未公佈，看板數據寫每次看板刷新。'
               '「如果……則……」是結果的含意，不是預測。</p>' + table(["日期", "事件", "含義（如果……則……）"], rows, "stack") + "</section>")
    rows = []
    for r in sorted(doc.get("indicators", []), key=lambda r: r.get("date", ""), reverse=True):
        src = link(r.get("source"), r.get("url")) + ('<span class="tag">看板數據</span>' if r.get("from_board") else "")
        rows.append(f'<tr><td class="nowrap">{escape(r.get("date", ""))}</td><td><b>{escape(r.get("item", ""))}</b></td>'
                    f'<td>{escape(r.get("reading", ""))}</td><td>{escape(r.get("means") or "—")}</td><td>{src}</td></tr>')
    out.append('<section class="card"><h2>4. 現有證據</h2><p class="sub">由新至舊。只列已用一手文件核實的讀數，或由看板數據直接讀取的讀數；'
               '未核實或二手的資料不記錄。</p>' + table(["日期", "指標", "最新讀數", "含義", "來源"], rows, "stack") + "</section>")
    return "\n".join(out)


def ai_page():
    try:
        body = ai_body(load("ai_tracker"))
    except (OSError, ValueError, KeyError, IndexError, TypeError) as e:
        print("ai page failed:", repr(e), flush=True)
        body = "<h1>AI 追蹤</h1><p class='sub'>資料暫時未能載入；執行 python3 macro/refresh.py --render-only 後重新整理。</p>"
    return page("AI 追蹤", body)


# ---------- 估值 (local board only) ----------
# Read from a private file outside this repository, written by that folder's own script. The page and its tab exist
# only on the local board and only while the file exists; export_site.py never renders it.
VAL_VIEW = ROOT.parent / "valuation and research" / "board_view.json"


def val_cell(v):
    """A table cell: text, or a list of [name, https link] pairs shown as links."""
    if isinstance(v, list):
        return "<br>".join(link(x[0], x[1]) for x in v if isinstance(x, (list, tuple)) and len(x) == 2) or "—"
    return escape(str(v))


def val_page(path=None):
    """The local 估值 page: a title, then sections of heading, note and one table. None when the file is missing."""
    p = Path(path or VAL_VIEW)
    if not p.exists():
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        out = [f'<h1>{escape(doc.get("title") or "估值")}</h1><p class="sub">更新：{escape(doc.get("updated") or "—")}</p>']
        for sec in doc.get("sections", []):
            rows = ["<tr>" + "".join(f"<td>{val_cell(c)}</td>" for c in r) + "</tr>" for r in sec.get("rows", [])]
            out.append(f'<section class="card"><h2>{escape(sec.get("heading", ""))}</h2><p class="sub">{escape(sec.get("note", ""))}</p>'
                       + table(sec.get("head", []), rows, "stack") + "</section>")
        body = "\n".join(out)
    except (OSError, ValueError, TypeError, AttributeError, KeyError) as e:
        print("val page failed:", repr(e), flush=True)
        body = "<h1>估值</h1><p class='sub'>資料暫時未能載入。</p>"
    return page("估值", body)
