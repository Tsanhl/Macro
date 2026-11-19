"""Render the local build (site_private/) that the 8770 board's 宏觀 view serves; refresh.py stages and validates it.

Reads the hand-kept evidence and borrower records from the parent workspace. Writes no AI summary.
"""
import hashlib
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA, SITE = ROOT / "data", ROOT / "site_private"
# what the page, server/ and daily_summary.py read; refresh.validate requires each of them
DATASETS = ["sectors", "rrg_tails", "ratios", "ratio_summary", "breadth", "breadth_now", "rates", "rates_now", "liquidity",
            "flowmodel", "flowmodel_now", "rrg_daily", "check_prices", "brent", "data_checks"]
OIL_EVIDENCE = ROOT.parent / "evidence" / "oil_tracking.json"  # manual dated oil readings (local board only)
BORROWER_CREDIT = ROOT.parent / "evidence" / "borrower_credit.json"
AI_TRACKER = ROOT.parent / "evidence" / "ai_tracker.json"  # the AI 追蹤 page: stages, current stage, watch list, evidence (local only)
NEWS_CONNECT = ROOT.parent / "evidence" / "news_connect.json"  # the 新聞與連接 page's issues and notes (local only)


def load(name):
    """A data file's rows, or None when the file is missing (it is then left out, not fatal)."""
    path = DATA / f"{name}.json"
    if not path.exists():
        print(f"  WARNING {path.name} missing; left out")
        return None
    return json.loads(path.read_text())


def load_all():
    out = {name: rows for name in DATASETS if (rows := load(name)) is not None}
    if (DATA / 'refresh_meta.json').is_file():
        out['refresh_meta'] = load('refresh_meta')
    return out


def _md(d):
    return f"{int(d[5:7])} 月 {int(d[8:10])} 日"


def _signed(x, digits=0):
    return f"{x:+,.{digits}f}".replace("-", "−")


def _iso(s):
    return isinstance(s, str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", s))


def ai_tracker_live(data):
    """Readings the board collects from data providers (BondTerminal bond prices and yields, FRED spreads, SOFR and IORB),
    for the AI tracker rows marked "live", as {key: {reading, date, source, url}}. Each keeps its own observation date;
    a source without a valid dated reading is simply absent."""
    out = {}
    doc = (data.get("borrower_credit") or [{}])[0]
    for issuer in doc.get("issuers", []):  # BondTerminal references, already checked by reference_reading()
        ref = issuer.get("reference_display") or {}
        last, prior = ref.get("latest"), ref.get("prior")
        if not last:
            continue
        text = f"淨價 {last['clean_price_per_100']:.2f}，YTW {last['yield_pct']:.2f}%"
        if prior and ref.get("price_change") is not None and ref.get("yield_change_bp") is not None:
            text += (f"；對 {_md(prior['price_date'])}：淨價 {_signed(ref['price_change'], 2)}，"
                     f"YTW {_signed(ref['yield_change_bp'])} 基點")
        out["bond:" + issuer.get("id", "")] = dict(reading=text, date=last["price_date"], url=last.get("source"),
                                                   source=f"{last.get('provider') or 'BondTerminal'}（延遲第三方參考，非 CDS 或 OAS）")
    now = (data.get("rates_now") or [{}])[0]
    if isinstance(now.get("hy_oas"), (int, float)) and _iso(now.get("hy_oas_date")):
        text = f"{now['hy_oas'] * 100:,.0f} 基點"
        if isinstance(now.get("hy_oas_1w"), (int, float)) and _iso(now.get("hy_oas_base_1w")):
            text += f"；一週 {_signed(now['hy_oas_1w'])} 基點（對 {_md(now['hy_oas_base_1w'])}）"
        out["hy_oas"] = dict(reading=text, date=now["hy_oas_date"], source="ICE BofA（FRED BAMLH0A0HYM2）",
                             url="https://fred.stlouisfed.org/series/BAMLH0A0HYM2")
    fund = (data.get("funding") or [{}])[0]
    b = next((r for r in fund.get("ladder", []) if r.get("id") == "b"), None)
    if b and isinstance(b.get("bp"), (int, float)) and _iso(b.get("date")):
        text = f"{b['bp']:,} 基點" + (f"，三年第 {b['pct3y']} 百分位" if b.get("pct3y") is not None else "")
        if isinstance(b.get("chg_bp"), (int, float)) and _iso(b.get("prev_date")):
            text += f"；對 {_md(b['prev_date'])} {_signed(b['chg_bp'])} 基點"
        out["b_oas"] = dict(reading=text, date=b["date"], source="ICE BofA B（FRED BAMLH0A2HYB）",
                            url="https://fred.stlouisfed.org/series/BAMLH0A2HYB")
    sp = [r for r in fund.get("spread", []) if _iso(r.get("date")) and isinstance(r.get("bp"), (int, float))]
    if sp:
        s = sp[-1]
        out["sofr_iorb"] = dict(reading=f"SOFR {s['sofr']:.2f}%，IORB {s['iorb']:.2f}%，差 {_signed(s['bp'])} 基點",
                                date=s["date"], source="FRED（SOFR、IORB）", url="https://fred.stlouisfed.org/series/SOFR")
    return out


def ai_tracker(data):
    """evidence/ai_tracker.json as one row for the AI 追蹤 page (local board only): the stages, the stage judged
    from the page's evidence ("current"), what to watch and when ("watch"), and the evidence ("indicators"). The hand rows
    hold readings verified against a primary document; rows marked "live" take the board's own latest dated reading
    from a data provider and are flagged "from_board". A row left without a dated reading is dropped, so the tab lists
    only readings it can show with their date and source."""
    if not AI_TRACKER.is_file():
        return [{"missing": True, "indicators": [], "watch": []}]
    doc = json.loads(AI_TRACKER.read_text())
    live, rows = ai_tracker_live(data), []
    for row in doc.get("indicators", []):
        if row.get("live"):
            got = live.get(row["live"])
            if not got:
                continue
            row.update(got, from_board=True)
        if row.get("reading") and _iso(row.get("date")):
            rows.append(row)
    doc["indicators"] = rows
    return [doc]


def news_connect(data):
    """The 新聞與連接 page (local only) as one row: the hand-kept evidence/news_connect.json (the one-line driver
    and the issues) plus the headlines that news_feed.py fetched into data/news_feed.json. Each headline takes the
    hand-written note (含義) and issue id kept for its link under "news" in the hand file; an issue id that names no
    issue is dropped. A missing feed gives an empty headline list, never a failed build."""
    doc = json.loads(NEWS_CONNECT.read_text()) if NEWS_CONNECT.is_file() else {"missing": True, "issues": []}
    notes = doc.pop("news", None) or {}
    ids = {i.get("id") for i in doc.get("issues", [])}
    try:
        feed = (data.get("news_feed") or [{}])[0]
        items = []
        for it in feed.get("items", []):
            n = notes.get(it.get("link")) or {}
            items.append({**it, "note": n.get("note") or "", "issue": n.get("issue") if n.get("issue") in ids else None})
        doc["feed"] = {**{k: v for k, v in feed.items() if k != "items"}, "items": items}
    except (AttributeError, TypeError, IndexError, KeyError) as e:  # never fail the build over the headlines
        print(f"  WARNING news_feed.json unreadable ({type(e).__name__}); headlines left out")
        doc["feed"] = {"items": [], "errors": ["news_feed.json unreadable"]}
    return [doc]


def news_feed_rows():
    try:
        return load("news_feed") or [{}]
    except (OSError, ValueError) as e:
        print(f"  WARNING news_feed.json unreadable ({type(e).__name__}); headlines left out")
        return [{}]


SHIM = """
(() => {
  const DATASETS = __DATASETS__;
  const store = {}, calcs = [], listeners = [];
  const params = { lang: 'zh' };
  try { const saved = localStorage.getItem('rb-lang'); if (saved) params.lang = saved; } catch (e) {}
  const fire = () => {
    for (const c of calcs) {
      const ins = c.inputs.map((id) => store[id]);
      if (ins.every((x) => x && x.status === 'ok')) {
        try { store[c.id] = { status: 'ok', data: c.fn(...ins.map((x) => x.data)) }; }
        catch (e) { store[c.id] = { status: 'error', data: [] }; console.error(c.id, e); }
      } else if (ins.some((x) => x && x.status === 'error')) store[c.id] = { status: 'error', data: [] };
    }
    for (const f of listeners) { try { f(); } catch (e) { console.error(e); } }
  };
  window.dash = {
    data: (id) => store[id] || { status: 'loading', data: [] },
    calc: (id, spec) => { calcs.push({ id, inputs: spec.inputs, fn: spec.fn }); },
    onData: (fn) => { listeners.push(fn); fn(); },
    params: () => ({ ...params }),
    setParams: (p) => { Object.assign(params, p); try { localStorage.setItem('rb-lang', params.lang); } catch (e) {} fire(); },
    resetParams: () => { params.lang = 'zh'; fire(); },
    setLink: (id) => { try { history.replaceState(null, '', '#' + id); } catch (e) {} },
    colors: [1, 2, 3, 4, 5, 6, 7, 8].map((i) => `var(--series-${i})`),
  };
  Promise.all(DATASETS.map((id) => fetch(`data/${id}.json`, { cache: 'no-cache' })
    .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then((d) => { store[id] = { status: 'ok', data: d }; })
    .catch(() => { store[id] = { status: 'error', data: [] }; }))).then(fire);
  let t;
  addEventListener('resize', () => { clearTimeout(t); t = setTimeout(fire, 150); });
})();
"""

TOKENS = """
:root {
  color-scheme: light;
  --font-anthropic-sans: "IBM Plex Sans", "Noto Sans TC", system-ui, -apple-system, "PingFang TC", sans-serif;
  --font-anthropic-serif: "Source Serif 4", "Noto Serif TC", Georgia, "Songti TC", serif;
  --cds-font-size-caption: 0.8125rem; --cds-font-size-body: 0.9375rem; --cds-font-size-heading: 1.0625rem; --cds-font-size-title: 1.75rem;
  --cds-font-weight-medium: 600;
  --cds-gap-xs: 4px; --cds-gap-sm: 8px; --cds-gap-md: 14px; --cds-gap-lg: 22px;
  --cds-pad-xs: 4px; --cds-pad-sm: 8px; --cds-pad-md: 12px; --cds-pad-lg: 18px;
  --cds-radius: 8px; --cds-dur-slow: 320ms; --cds-ease-out: cubic-bezier(.2, .7, .2, 1);
  --color-bg: #f4f6f8; --color-panel: #ffffff; --color-fg: #1a1f26; --color-fg-muted: #5d6874; --color-border-line: #dfe4ea;
  --color-ok: #17804c; --color-warn: #b0600c; --color-bad: #c0352b;
  --cds-text-secondary: #4d6a8a; --cds-border: #d3dae2; --cds-surface-popover: #ffffff; --cds-shadow-popover: 0 6px 20px rgba(20, 30, 45, .14);
  --cds-chart-grid: #e9edf1; --cds-chart-axis: #b9c2cc; --cds-chart-reference: #8e99a5; --cds-chart-muted: #a3adb8;
  --series-1: #2c6bd6; --series-2: #d9822b; --series-3: #7b5cd6; --series-4: #179c8c; --series-5: #c43f7b; --series-6: #6c8f1f; --series-7: #8d6b1c; --series-8: #4b6fa6;
}
@media (prefers-color-scheme: dark) { :root {
  color-scheme: dark;
  --color-bg: #11151a; --color-panel: #181d24; --color-fg: #e6eaef; --color-fg-muted: #9aa5b1; --color-border-line: #2a313a;
  --color-ok: #4cc28a; --color-warn: #e39a4a; --color-bad: #f0796c;
  --cds-text-secondary: #9db7d4; --cds-border: #333b45; --cds-surface-popover: #1f252d; --cds-shadow-popover: 0 6px 20px rgba(0, 0, 0, .5);
  --cds-chart-grid: #232a32; --cds-chart-axis: #46505b; --cds-chart-reference: #6f7a86; --cds-chart-muted: #5f6a76;
  --series-1: #6b9dff; --series-2: #f2a65a; --series-3: #a58cf0; --series-4: #3cc2b0; --series-5: #ea6fa5; --series-6: #9bc24a; --series-7: #c9a24a; --series-8: #86a5d6;
} }
html, body { margin: 0; background: var(--color-bg); color: var(--color-fg); font-family: var(--font-anthropic-sans); font-size: 15px; }
[hidden] { display: none !important; }
#dash-root { padding: 28px clamp(16px, 4vw, 40px) 12px; }
.dash-skeleton { position: relative; min-height: 1em; border-radius: var(--cds-radius); background: linear-gradient(90deg, var(--cds-chart-grid), var(--color-panel), var(--cds-chart-grid)); background-size: 200% 100%; animation: skel 1.4s linear infinite; color: transparent !important; }
@keyframes skel { to { background-position: -200% 0; } }
@media (prefers-reduced-motion: reduce) { .dash-skeleton { animation: none; } }
.site-foot { max-width: 80rem; margin: 0 auto; padding: 8px clamp(16px, 4vw, 40px) 32px; color: var(--color-fg-muted); font-size: 0.8125rem; line-height: 1.6; }
"""

PAGE = """<!doctype html>
<html lang="zh-Hant-HK">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>板塊輪動與市寬</title>
<meta name="theme-color" content="#f4f6f8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600&family=Source+Serif+4:wght@400&family=Noto+Sans+TC:wght@400;600&family=Noto+Serif+TC:wght@400&display=swap">
<style>__TOKENS__</style>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>
<script>__SHIM__</script>
</head>
<body>
<main id="dash-root">
__BODY__
</main>
<footer class="site-foot">
  僅供參考，不構成投資建議。數據來自 Yahoo Finance、CFTC、FRED、美國財政部、Cboe、歐洲央行、英倫銀行及日本財務省，按已完成交易日更新；此為本地完整資料版本，各來源實際觀察日期見摘要及圖表。<br>
  For information only, not investment advice. Data from Yahoo Finance, the CFTC, FRED, the US Treasury, Cboe, the ECB, the Bank of England and Japan's MoF, updated after completed sessions; this is the full local version. Source observation dates are shown in the summary and charts.
</footer>
</body>
</html>
"""


def main():
    """The local build into site_private/ (never published)."""
    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "data").mkdir(parents=True)
    data = load_all()
    for name in ("auctions", "funding", "macro_watch"):  # Treasury auctions, funding market and credit ladder, TGA and MOVE
        if (rows := load(name)) is not None:
            data[name] = rows
    data["borrower_credit"] = [json.loads(BORROWER_CREDIT.read_text())] if BORROWER_CREDIT.is_file() else [{"issuers": []}]
    from daily_summary import reference_reading
    asof = (data.get("breadth") or [{}])[-1].get("date", "")
    for issuer in data["borrower_credit"][0].get("issuers", []):
        issuer["reference_display"] = reference_reading(issuer, asof)
    # 油價 page: automated blocks from build_data (data/oil.json) plus the manual dated readings
    oil = load("oil")
    if oil or OIL_EVIDENCE.is_file():
        row = dict(oil[0]) if oil else {"errors": ["oil.json missing"]}
        row["manual"] = json.loads(OIL_EVIDENCE.read_text()) if OIL_EVIDENCE.is_file() else {"readings": []}
        data["oil"] = [row]
    # AI 追蹤 and 新聞與連接 pages: the hand-kept files, the AI tracker's live rows filled from the data above, and
    # the headlines news_feed.py fetched (data/news_feed.json, folded into news_connect and not written on its own)
    data["ai_tracker"] = ai_tracker(data)
    data["news_connect"] = news_connect({"news_feed": news_feed_rows()})
    for name, rows in data.items():
        (SITE / "data" / f"{name}.json").write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")))
    # the page asks for every dataset, so a missing file shows as 未能載入 rather than loading forever
    ids = list(dict.fromkeys(DATASETS + list(data)))
    body = (ROOT / "index.html").read_text()
    page = (PAGE.replace("__TOKENS__", TOKENS)
                .replace("__SHIM__", SHIM.replace("__DATASETS__", json.dumps(ids)))
                .replace("__BODY__", body))
    script_version = hashlib.sha256((ROOT / "refresh.js").read_bytes()).hexdigest()[:12]
    shutil.copy2(ROOT / "refresh.js", SITE / "refresh.js")
    page = page.replace("</body>", f'<script src="refresh.js?v={script_version}"></script>\n</body>')
    (SITE / "index.html").write_text(page)
    print(f"{SITE.name}/ built:", len(data), "data files")


if __name__ == "__main__":
    main()
