"""Text for the local board's 宏觀 view, built only from the board's data on every page load (no AI analysis):
the 每日摘要 with its 關鍵數據 and 之後要看 lists, the TGA, MOVE and net-liquidity readings, the 美債 section (latest
auctions, 2-year and 10-year yields, the 10Y−2Y spread and its shape change by definition), the credit table with a short
description, the 市寬與輪動摘要 card above the rotation and breadth charts, the AI and semiconductor relative-strength
section, and on the 油價 page the 油市總結, the Brent curve card with its spread sentences, the OVX line, the
five-contract managed-money card and the 戰事最新進展 card (the newest war headlines from macro/data/news_feed.json,
which the board's background fetch updates every 30 minutes, above the hand-kept events and escalation ladder).

Every line states levels, dates, direction and size. The only tested statistic is the market-state line, from
Backtests/results/29_market_state_bounce.txt (R29, data from June 2007), stated as a historical rate; the 美債 section
adds one historical sentence from R10/R32 on the curve shapes. No line adds a
cut-off of its own, gives advice or makes a forecast. A reading that is missing or older than expected is said so.
"""
from datetime import date, datetime, timedelta
from html import escape
import json
from pathlib import Path
import time
import urllib.request
from zoneinfo import ZoneInfo

PROJECT = Path(__file__).resolve().parent.parent
DATA = PROJECT / "macro" / "site_private" / "data"
NEWS_FEED = PROJECT / "macro" / "data" / "news_feed.json"  # read on every page load
WAR_HEADLINES = 10  # automatic war headlines shown on the card, newest first
UPCOMING = "https://www.treasurydirect.gov/TA_WS/securities/upcoming?format=json"
AUCTION_DAYS = 5  # results this recent are listed in 關鍵數據
WATCH_DAYS = 21
_cache = {"t": 0.0, "rows": []}
# From Backtests/results/29_market_state_bounce.txt: chance of a further 5% fall within 60 sessions, by state ("normal":
# the all-days rate, because the test names a state only once the S&P is 3% or more off its 60-day high).
ALL_DAYS_RISK = "34%"
STATE_RISK = {"normal": ALL_DAYS_RISK, "rotation": "29%", "narrow_weak": "49%", "broad": "42%", "worse": "48%"}
STATE_NAME = {"rotation": "輪動", "narrow_weak": "指數弱", "broad": "大市下跌", "worse": "大市惡化"}
STATE_MEAN = {"rotation": "跌幅集中在大型股", "narrow_weak": "一般股份比大型股弱", "broad": "跌勢擴散到大部分股份，信用未轉弱",
              "worse": "跌勢擴散到大部分股份，同時信用轉弱"}


def load(name):
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


def first(name):
    try:
        return load(name)[0]
    except (OSError, ValueError, IndexError):
        return None


def pct3y(s):
    """Share of a series' readings at or below its latest, in whole per cent (rates.json holds three years; the same
    definition as funding_market.pct, so every row of the credit table agrees)."""
    return round(sum(v <= s[-1] for v in s) / len(s) * 100)


def rate_series(rates, key):
    return [x[key] * 100 for x in rates if x.get(key) is not None]


def sg(x, d=0):
    s = f"{x:+,.{d}f}".replace("-", "−")
    return s[1:] if float(s[1:].replace(",", "")) == 0 else s  # no sign on zero


def md(s):
    return f"{int(s[5:7])}月{int(s[8:10])}日" if s else "日期未確認"


def move(chg, unit="基點", up="擴闊", down="收窄", d=0):
    """A change stated as direction and size, with no judgement attached."""
    if chg is None:
        return "變化未確認"
    return "持平" if round(chg, d) == 0 else f"{up if chg > 0 else down} {abs(chg):,.{d}f} {unit}".rstrip()


def rise(chg, unit="", d=0):
    return move(chg, unit, "上升", "下降", d)


def more(chg, unit="", d=0):
    return move(chg, unit, "增加", "減少", d)


def weekdays_between(a, b):
    """Weekdays after date a up to and including date b (ISO strings)."""
    d, end, n = date.fromisoformat(a), date.fromisoformat(b), 0
    while d < end:
        d += timedelta(days=1)
        n += d.weekday() < 5
    return n


def p(text, cls="rb-sub", style="color:var(--color-fg)"):
    return f'<p class="{cls}" style="{style}">{escape(text)}</p>'


def note(text):
    return f'<p class="rb-sub">{escape(text)}</p>'


# ---------- readings ----------

def tga():
    mw = first("macro_watch") or {}
    return mw.get("tga"), mw.get("move"), mw.get("errors") or []


def liquidity():
    rows = [r for r in load("liquidity") if r.get("net_liq") is not None]
    if not rows:
        return None
    last = rows[-1]
    base = rows[-5] if len(rows) > 4 else None
    return {"last": last, "base": base, "chg4w": None if base is None else last["net_liq"] - base["net_liq"],
            "chg1w": last["net_liq"] - rows[-2]["net_liq"] if len(rows) > 1 else None}


def market():
    """The inputs of the R29 market state."""
    S = {x["ticker"]: x for x in load("sectors")}
    R = {x["pair"]: x for x in load("ratio_summary")}
    spx = [x["spx"] for x in load("flowmodel") if x.get("spx")]
    return {"dd60": (spx[-1] / max(spx[-60:]) - 1) * 100, "ew_dd": S["RSP"]["off_hi60"], "ew_rel20": R["RSP_SPY"]["chg20d"],
            "credit_below_50": R["HYG_IEF"]["vs_50d"] < 0}


def state_of(m):
    """Market state, as tested in Backtests/results/29_market_state_bounce.txt."""
    if m["dd60"] > -3:
        return "normal"
    if m["ew_dd"] > -5:
        return "rotation" if m["ew_rel20"] > 0 else "narrow_weak"
    return "broad" if not m["credit_below_50"] else "worse"


def line_state():
    m = market()
    st = state_of(m)
    if st == "normal":
        return (f"市場狀態（2007 年以來的回測）：標普距 60 日高 {sg(m['dd60'], 1)}%，未到區分狀態的 3%，不屬任何狀態；"
                f"以所有交易日計，歷史上之後 60 日內再跌 5% 的比率約 {ALL_DAYS_RISK}，這是歷史比率，不是預測。")
    return (f"市場狀態（2007 年以來的回測）：今日屬「{STATE_NAME[st]}」（{STATE_MEAN[st]}），歷史上這狀態之後 60 日內再跌 5% 的比率約 "
            f"{STATE_RISK[st]}（所有交易日約 {ALL_DAYS_RISK}），這是歷史比率，不是預測。")


# ---------- 每日摘要 ----------

def daily_summary(session, today=None):
    """Three to five sentences on what the latest readings show together, then the direction count. Each sentence states
    levels and direction only; the last sentence sorts the five groups by the direction of their latest change."""
    today = today or date.today().isoformat()
    out, up, down = [], [], []  # up: pointing to tighter or weaker; down: looser or stronger
    lag = weekdays_between(session, today) - 1
    stale = (f"看板最新收市數據是 {md(session)}，其後已有 {lag} 個平日沒有數據；如非假期，即數據未更新。" if lag > 0 else "")
    T, M, _ = tga()
    L = liquidity()
    parts = []
    if L and L["chg4w"] is not None:
        parts.append(f"聯儲淨流動性四週{more(L['chg4w'] * 10, '億美元')}（至 {md(L['last']['date'])}）")
        if L["chg4w"]:
            (up if L["chg4w"] < 0 else down).append("流動性（淨流動性四週）")
    if T and T.get("chg_1w"):
        parts.append(f"TGA 一週{more(T['chg_1w']['bn'] * 10, '億美元')}（至 {md(T['latest']['date'])}）")
    f = first("funding") or {}
    sp = (f.get("spread") or [None])[-1]
    if sp:
        parts.append(f"SOFR 對 IORB {sg(sp['bp'])} 基點（{md(sp['date'])}）")
    if parts:
        out.append("流動性：" + "；".join(parts) + "。")
    r = first("rates_now") or {}
    parts = []
    if r.get("nominal10_1w") is not None:
        parts.append(f"10 年期孳息一週{rise(r['nominal10_1w'], '基點')}至 {r['nominal10']:.2f}%")
        if r.get("nominal2_1w") is not None and r.get("nominal2") is not None and r.get("curve") is not None:
            parts.append(f"2 年期一週{rise(r['nominal2_1w'], '基點')}至 {r['nominal2']:.2f}%，10 年減 2 年息差 {sg(r['curve'] * 100)} 基點"
                         f"（一週{curve_shape(r['nominal2_1w'], r['nominal10_1w'])}）")
    if M and M.get("chg_1w"):
        parts.append(f"MOVE 一週{rise(M['chg_1w']['v'], '', 1)} 至 {M['latest']['v']:.1f}，在一年讀數中第 {M['pct1y']} 百分位")
        if M["chg_1w"]["v"]:
            (up if M["chg_1w"]["v"] > 0 else down).append("債市波動（MOVE 一週）")
    elif not M:
        parts.append("MOVE 沒有數據")
    if parts:
        out.append("利率及債市波動：" + "；".join(parts) + "。")
    parts = []
    if r.get("hy_oas_1w") is not None:
        parts.append(f"HY 息差一週{move(r['hy_oas_1w'])}、IG {move(r.get('ig_oas_1w'))}（至 {md(r.get('hy_oas_date'))}）")
        if r["hy_oas_1w"]:
            (up if r["hy_oas_1w"] > 0 else down).append("信用（HY 息差一週）")
    if parts:
        out.append("信用：" + "；".join(parts) + "。")
    S = {x["ticker"]: x for x in load("sectors")}
    smh, mem = S.get("SMH") or {}, S.get("AI_MEM") or {}
    b = first("breadth_now") or {}
    parts = []
    if smh.get("rel1m") is not None:
        parts.append(f"SMH 一個月{'跑贏' if smh['rel1m'] > 0 else '跑輸'}標普 {abs(smh['rel1m']):.1f} 個百分點")
        if smh["rel1m"]:
            (up if smh["rel1m"] < 0 else down).append("AI／半導體（SMH 一個月相對）")
    if mem.get("rel1m") is not None:
        parts.append(f"記憶體籃子{'跑贏' if mem['rel1m'] > 0 else '跑輸'} {abs(mem['rel1m']):.1f} 個百分點")
    if b.get("pct50") is not None and b.get("pct50_1w") is not None:
        parts.append(f"市寬方面，{b['pct50']:.0f}% 標普成份股高於 50 日線，一週前 {b['pct50_1w']:.0f}%")
        if b["pct50"] != b["pct50_1w"]:
            (up if b["pct50"] < b["pct50_1w"] else down).append("市寬（50 日線比例一週）")
    if parts:
        out.append("AI 與半導體：" + "；".join(parts) + "。")
    if up or down:
        out.append("合起來看：" + "；".join(x for x in (
            f"{'、'.join(up)}指向收緊或轉弱" if up else "", f"{'、'.join(down)}指向放鬆或轉強" if down else "") if x)
            + "（按各項最近一次變化的方向，不設門檻）。")
    return ([stale] if stale else []) + out


def key_data(session):
    """One line each: latest value, change and date."""
    out = []
    T, M, errs = tga()
    if T:
        w, m = T.get("chg_1w"), T.get("chg_1m")
        out.append(f"TGA 結餘：{T['latest']['bn'] * 10:,.0f} 億美元（{md(T['latest']['date'])}）；一週 {sg(w['bn'] * 10) if w else '—'} 億，"
                   f"一個月 {sg(m['bn'] * 10) if m else '—'} 億。")
    else:
        out.append("TGA 結餘：沒有數據。")
    if M:
        w = M.get("chg_1w")
        out.append(f"MOVE：{M['latest']['v']:.1f}（{md(M['latest']['date'])}）；一週 {sg(w['v'], 1) if w else '—'}；一年第 {M['pct1y']} 百分位。")
    else:
        out.append("MOVE：Yahoo 沒有提供 ^MOVE 數據。")
    L = liquidity()
    if L:
        out.append(f"聯儲淨流動性：{L['last']['net_liq'] * 10:,.0f} 億美元（{md(L['last']['date'])}）；四週 "
                   f"{sg(L['chg4w'] * 10) if L['chg4w'] is not None else '—'} 億。")
    r = first("rates_now") or {}
    if r.get("hy_oas") is not None:
        out.append(f"信用息差：HY {r['hy_oas'] * 100:,.0f} 基點，一週 {sg(r['hy_oas_1w']) if r.get('hy_oas_1w') is not None else '—'}；"
                   f"IG {r['ig_oas'] * 100:,.0f} 基點，一週 {sg(r['ig_oas_1w']) if r.get('ig_oas_1w') is not None else '—'}（{md(r.get('hy_oas_date'))}）。")
    if r.get("nominal10") is not None:
        out.append(f"美國 10 年期孳息：{r['nominal10']:.2f}%（{md(r.get('nominal10_date'))}）；一週 {sg(r['nominal10_1w']) if r.get('nominal10_1w') is not None else '—'} 基點。")
    if r.get("curve") is not None:
        out.append(f"10 年減 2 年息差：{sg(r['curve'] * 100)} 基點（{md(r.get('curve_date'))}）；一週 {fmt_chg(r.get('curve_1w'))}、一個月 {fmt_chg(r.get('curve_1m'))} 基點。")
    S = {x["ticker"]: x for x in load("sectors")}
    smh, mem = S.get("SMH") or {}, S.get("AI_MEM") or {}
    parts = []
    if smh.get("rel1m") is not None:
        parts.append(f"SMH 對 SPY 一個月 {sg(smh['rel1m'], 1)}、三個月 {sg(smh.get('rel3m') or 0, 1)} 個百分點")
    if mem.get("rel1m") is not None:
        parts.append(f"記憶體籃子一個月 {sg(mem['rel1m'], 1)}、三個月 {sg(mem.get('rel3m') or 0, 1)}")
    f = first("funding") or {}
    sp = (f.get("spread") or [None])[-1]
    if sp:
        out.append(f"SOFR 對 IORB：{sg(sp['bp'])} 基點（{md(sp['date'])}）。")
    out += auctions(session)
    return out


def auctions(session):
    try:
        a = load("auctions")[0]
    except (OSError, ValueError, IndexError):
        return []
    cut = (date.fromisoformat(session) - timedelta(days=AUCTION_DAYS)).isoformat()
    rows = [x for x in a["rows"] if x["date"] >= cut and x.get("btc_avg6") is not None and x.get("dealer_avg6") is not None]
    if not rows:
        return []
    return ["美債拍賣：" + "；".join(f"{md(x['date'])} {x['term']} 得標 {x['high_yield']:.3f}%，投標倍數 {x['bid_to_cover']:.2f}"
                                  f"（近六次 {x['btc_avg6']:.2f}），交易商 {x['dealer_pct']:.1f}%（近六次 {x['dealer_avg6']:.1f}%）"
                                  for x in rows) + "。"]


def upcoming_auctions():
    if time.time() - _cache["t"] > 6 * 3600:
        try:
            req = urllib.request.Request(UPCOMING, headers={"User-Agent": "Mozilla/5.0"})
            rows = json.loads(urllib.request.urlopen(req, timeout=8).read().decode())
            _cache["rows"] = sorted({(x["competitiveAuctionCloseDate"][:10], x["securityTerm"].replace("-Year", " 年期"))
                                     for x in rows if x.get("type") in ("Note", "Bond")})
        except Exception:
            pass  # the list simply omits auctions; rows from the last good fetch stay
        _cache["t"] = time.time()  # also after a failure, so a slow source cannot delay every page load
    return _cache["rows"]


def watch(session):
    today, end = max(session, date.today().isoformat()), (date.today() + timedelta(days=WATCH_DAYS)).isoformat()
    items = []
    try:
        for x in json.loads((Path(__file__).parent / "watch.json").read_text(encoding="utf-8")):
            if today <= x["date"] <= end:
                items.append((x["date"], f"{x.get('time_uk', '')} {x['text']}".strip()))
    except (OSError, ValueError):
        pass
    for d, term in upcoming_auctions():
        if today <= d <= end:
            items.append((d, f"{term}美債拍賣"))
    try:
        lv = json.loads((PROJECT / "institutional" / "data" / "levels.json").read_text(encoding="utf-8"))
        for x in lv.get("earnings", []):
            if today <= x["date"] <= end:
                items.append((x["date"], f"{x['t']} 業績（Yahoo 日期）"))
    except (OSError, ValueError):
        pass
    days = {}
    for d, t in sorted(items):
        days.setdefault(d, []).append(t)
    return [f"{md(d)}：{'、'.join(v)}" for d, v in days.items()]


def build():
    """The 每日摘要 block: the summary paragraph, 關鍵數據, the market-state line and 之後要看."""
    session = load("refresh_meta")[0]["session"]
    html = [f'<h2 class="rb-h2">每日摘要（{md(session)}收市）</h2>']
    for label, fn in (("summary", lambda: daily_summary(session)), ("key", lambda: key_data(session)),
                      ("state", lambda: [line_state()]), ("watch", lambda: watch(session))):
        try:
            rows = fn()
        except Exception as e:  # a data file changed shape: keep the other parts, say so
            print(f"summary part {label} failed:", repr(e), flush=True)
            rows = ["這部分暫時未能生成。"]
        if label == "summary":
            html.append("".join(f"<p>{escape(x)}</p>" for x in rows))
        elif label == "key":
            html.append('<p><b>關鍵數據</b></p><ul>' + "".join(f"<li>{escape(x)}</li>" for x in rows) + "</ul>")
        elif label == "state":
            html.append(f'<p class="rb-sub">{escape(rows[0])}</p>')
        elif rows:
            html.append('<p><b>之後要看</b>（英國時間）</p><ul>' + "".join(f"<li>{escape(x)}</li>" for x in rows) + "</ul>")
    return "".join(html)


# ---------- sections of the 宏觀 page ----------

def card(cid, title, body):
    return f'<div class="rb-card rb-wide" id="{cid}"><h2 class="rb-h2">{escape(title)}</h2>{body}</div>'


def tga_card():
    T, _, errs = tga()
    if not T:
        body = note("沒有 TGA 數據：財政部 fiscaldata 未能下載，或尚未建立 macro_watch.json。")
    else:
        w, m = T.get("chg_1w"), T.get("chg_1m")
        line = f"最新 {T['latest']['bn'] * 10:,.0f} 億美元（{md(T['latest']['date'])}）"
        if w:
            line += f"；一週{more(w['bn'] * 10, '億美元')}（對 {md(w['base_date'])}）"
        if m:
            line += f"；一個月{more(m['bn'] * 10, '億美元')}（對 {md(m['base_date'])}）"
        body = (p(line + "。") + note("TGA 是財政部在聯儲的現金帳戶；結餘上升時，資金由銀行體系流入這個帳戶。來源：美國財政部每日報表"
                                      "（Daily Treasury Statement）表 I「Treasury General Account (TGA) Closing Balance」，"
                                      "fiscaldata.treasury.gov；每個營業日的報表在下一個營業日公布。")
                + (note("今次下載失敗，以上是上次成功下載的數據：" + "、".join(e for e in errs if e.startswith("TGA"))) if any(e.startswith("TGA") for e in errs) else ""))
    return card("rb-tga", "TGA 最新餘額", body + '<div class="rb-chart" id="ch-rb-tga" style="min-height: 12rem"></div>')


def move_liq_card():
    _, M, errs = tga()
    if M:
        w = M.get("chg_1w")
        mline = (f"MOVE {M['latest']['v']:.1f}（{md(M['latest']['date'])}）" + (f"；一週{rise(w['v'], '', 1)}（對 {md(w['base_date'])}）" if w else "")
                 + f"；在過去一年 {M['n1y']} 個收市讀數（{M['first1y']} 起）中第 {M['pct1y']} 百分位。")
        mtext = p(mline) + note("MOVE 是美債期權的隱含波幅（ICE BofA MOVE，Yahoo ^MOVE）；Yahoo 的 ^MOVE 通常比其他收市數據遲一日。"
                                + ("今次下載失敗，以上是上次成功的數據。" if any(e.startswith("MOVE") for e in errs) else ""))
    else:
        mtext = note("MOVE：Yahoo 沒有提供 ^MOVE 數據，所以本節不顯示 MOVE。")
    L = liquidity()
    if L:
        x = L["last"]
        lline = (f"淨流動性 {x['net_liq'] * 10:,.0f} 億美元（{md(x['date'])}，週三水平）＝聯儲總資產 {x['fed_bs'] * 10:,.0f} − TGA "
                 f"{x['tga'] * 10:,.0f} − 逆回購 {x['rrp'] * 10:,.0f}")
        if L["base"]:
            lline += f"；四週{more(L['chg4w'] * 10, '億美元')}（對 {md(L['base']['date'])}）"
        ltext = p(lline + "。") + note(
            "公式：聯儲淨流動性＝聯儲總資產（FRED WALCL，週三水平）− 財政部一般帳戶（FRED WDTGAL，週三水平）− 隔夜逆回購（FRED RRPONTSYD，"
            "同一個週三）。TGA 用週三水平而不用一週平均的 WTREGEN，令三項都是同一日的水平；所以這裏的 TGA 與上面每日報表的讀數日期不同。"
            "聯儲每週四公布截至週三的數字。")
    else:
        ltext = note("淨流動性：沒有數據。")
    body = ('<div class="rb-grid">'
            f'<div><h3 class="rb-h2">MOVE 指數</h3>{mtext}<div class="rb-chart" id="ch-rb-move" style="min-height: 12rem"></div></div>'
            f'<div><h3 class="rb-h2">聯儲淨流動性</h3>{ltext}<div class="rb-chart" id="ch-rb-liq" style="min-height: 12rem"></div></div></div>')
    return card("rb-moveliq", "MOVE 指數及聯儲淨流動性", body)



# ---------- 美債 ----------

TERM_ORDER = ["2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]
CORE_TERMS = {"2Y", "5Y", "10Y", "30Y"}  # always listed (latest of each); other terms only if auctioned in the last month
TERM_NAME = {t: f"{t[:-1]} 年期" for t in TERM_ORDER}


def latest_auctions(rows, session, days=31):
    """The latest auction of each term: 2, 5, 10 and 30-year always, the other terms only within `days` of the session.
    Tenor order, short to long."""
    latest = {}
    for r in rows:
        if r.get("term") in TERM_ORDER and (r["term"] not in latest or r["date"] > latest[r["term"]]["date"]):
            latest[r["term"]] = r
    cut = (date.fromisoformat(session) - timedelta(days=days)).isoformat()
    return [latest[t] for t in TERM_ORDER if t in latest and (t in CORE_TERMS or latest[t]["date"] >= cut)]


def beside(v, avg, d=1, unit=""):
    """A reading with its six-auction average in brackets."""
    return f"{v:.{d}f}{unit}（{'—' if avg is None else f'{avg:.{d}f}{unit}'}）"


def curve_shape(d2, d10):
    """The curve's shape change by definition, from the 2-year and 10-year changes (basis points). No size cut-off."""
    if d2 > 0 and d10 > 0:
        return "熊市變陡" if d10 > d2 else "熊市變平" if d2 > d10 else "兩端同幅上升，息差不變"
    if d2 < 0 and d10 < 0:
        return "牛市變陡" if d2 < d10 else "牛市變平" if d10 < d2 else "兩端同幅下降，息差不變"
    if d2 == 0 and d10 == 0:
        return "兩端持平"
    spread = "息差擴闊" if d10 > d2 else "息差收窄"
    if d2 == 0 or d10 == 0:
        return f"只有一端變動，{spread}"
    return f"兩端方向相反，{spread}"


def curve_sentence(label, d2, d10):
    """One sentence for one horizon: each end's move, which end moved more, and the shape by definition."""
    ends = f"2 年期{rise(d2, '基點')}、10 年期{rise(d10, '基點')}"
    name = curve_shape(d2, d10)
    if name in ("熊市變陡", "熊市變平", "牛市變陡", "牛市變平"):
        more_end = "長端" if abs(d10) > abs(d2) else "短端"
        return f"{label}{ends}，{more_end}變動較大，按定義屬{name}（息差{move(d10 - d2)}）。"
    if "息差不變" in name or name == "兩端持平":
        return f"{label}{ends}，{name}。"
    return f"{label}{ends}，{name} {abs(d10 - d2):,.0f} 基點。"


# From Backtests/results/10_curve_regimes.txt (R10, 2021–26) and Backtests/FINDINGS.md R32 (2003–14 re-check): a
# historical description, not a signal.
CURVE_HISTORY = ("回測（R10、R32，按一個月內 2 年及 10 年期孳息變化分類，2021–26 年及 2003–14 年）顯示，這四種形狀與同一個月"
                 "的板塊相對表現有關，但之後三個月的相對表現沒有一致方向。")


def rates_lines(r):
    """The 2-year, 10-year and 10Y−2Y readings, from rates_now (the same file as the 每日摘要)."""
    out = []
    for k, name in (("nominal2", "2 年期"), ("nominal10", "10 年期")):
        if r.get(k) is None:
            out.append(f"{name}孳息：沒有數據。")
            continue
        out.append(f"{name}孳息 {r[k]:.2f}%（{md(r.get(k + '_date'))}）；一週{rise(r.get(k + '_1w'), '基點')}（對 {md(r.get(k + '_base_1w'))}），"
                   f"一個月{rise(r.get(k + '_1m'), '基點')}（對 {md(r.get(k + '_base_1m'))}）。")
    return out


def bonds_card(session):
    """美債: who bought the latest auctions, the 2-year and 10-year yields, the 10Y−2Y spread and the shape change."""
    parts = []
    # 需求
    try:
        a = load("auctions")[0]
        rows = latest_auctions(a["rows"], session)
    except (OSError, ValueError, IndexError, KeyError):
        rows = []
    if rows:
        head = "".join(f"<th{' class=rb-left' if i < 2 else ''}>{t}</th>" for i, t in enumerate(
            ("日期", "年期", "得標孳息", "投標倍數（近六次）", "間接投標（近六次）", "直接投標（近六次）", "一級交易商（近六次）")))
        body = ""
        for x in rows:
            body += ("<tr>" + f"<td class=rb-left>{md(x['date'])}</td><td class=rb-left>{TERM_NAME[x['term']]}{'（增發）' if x.get('reopening') else ''}</td>"
                     f"<td>{x['high_yield']:.3f}%</td>"
                     + "".join(f"<td>{escape(beside(x[k], x.get(k2), d, u))}</td>" for k, k2, d, u in (
                         ("bid_to_cover", "btc_avg6", 2, ""), ("indirect_pct", "indirect_avg6", 1, "%"),
                         ("direct_pct", "direct_avg6", 1, "%"), ("dealer_pct", "dealer_avg6", 1, "%"))) + "</tr>")
        recent = [x for x in rows if x["date"] >= (date.fromisoformat(session) - timedelta(days=31)).isoformat() and x.get("btc_avg6") is not None]
        line = None
        if recent:
            hi = [TERM_NAME[x["term"]] for x in recent if x["bid_to_cover"] > x["btc_avg6"]]
            lo = [TERM_NAME[x["term"]] for x in recent if x["bid_to_cover"] < x["btc_avg6"]]
            ih = [TERM_NAME[x["term"]] for x in recent if x.get("indirect_avg6") is not None and x["indirect_pct"] > x["indirect_avg6"]]
            il = [TERM_NAME[x["term"]] for x in recent if x.get("indirect_avg6") is not None and x["indirect_pct"] < x["indirect_avg6"]]
            line = (f"近一個月 {len(recent)} 次拍賣（至 {md(max(x['date'] for x in recent))}）與近六次平均比較：投標倍數高於的有 {'、'.join(hi) or '沒有'}，"
                    f"低於的有 {'、'.join(lo) or '沒有'}；間接投標比例高於的有 {'、'.join(ih) or '沒有'}，低於的有 {'、'.join(il) or '沒有'}。")
        parts.append('<h3 class="rb-h2">需求（誰買美債）</h3>' + (p(line) if line else "")
                     + f'<div class="rb-tablebox" style="max-height:none"><table class="rb-table rb-bondt"><tr>{head}</tr>{body}</table></div>'
                     + note("每個年期最近一次拍賣：2、5、10、30 年期必列，3、7、20 年期只列最近一個月內的。括號內是同一年期之前六次拍賣（包括增發）的平均；上面一行列出高於及低於這個平均的年期。"
                            "間接投標＝經交易商遞交的外國及其他投資者，直接投標＝直接向財政部投標的機構，一級交易商＝包銷其餘部分的交易商；"
                            "三項是競爭性得標的比例，不包括聯儲（SOMA）的轉期。尾差（得標孳息減下午 1 時的 when-issued 孳息）沒有免費官方數據，所以不列。"
                            f"來源：TreasuryDirect 拍賣結果（下載於 {a.get('retrieved', '')[:10]}）。"))
    else:
        parts.append('<h3 class="rb-h2">需求（誰買美債）</h3>' + note("沒有拍賣數據：TreasuryDirect 未能下載，或尚未建立 auctions.json。"))
    # 孳息, 息差, 含義
    r = first("rates_now") or {}
    ylines = rates_lines(r)
    if r.get("curve") is not None:
        c = r["curve"] * 100
        sline = (f"10 年減 2 年 {sg(c)} 基點（{md(r.get('curve_date'))}）；一週{move(r.get('curve_1w'))}（對 {md(r.get('curve_base_1w'))}），"
                 f"一個月{move(r.get('curve_1m'))}（對 {md(r.get('curve_base_1m'))}）。")
    else:
        sline = "10 年減 2 年息差：沒有數據。"
    mean = []
    for label, h in (("一週內，", "1w"), ("一個月內，", "1m")):
        d2, d10 = r.get(f"nominal2_{h}"), r.get(f"nominal10_{h}")
        if d2 is not None and d10 is not None:
            mean.append(curve_sentence(label, d2, d10))
    if mean:
        mean.append(CURVE_HISTORY)
    src = "美國財政部每日孳息曲線（FRED DGS2、DGS10 的同一系列；財政部當晚公布，FRED 遲一日或以上）"
    parts.append('<div class="rb-grid">'
                 f'<div><h3 class="rb-h2">孳息</h3>{"".join(p(x) for x in ylines)}'
                 '<div class="rb-legend"><span style="--sw:var(--series-1)">10 年期（%）</span><span style="--sw:var(--series-2)">2 年期（%）</span></div>'
                 f'<div class="rb-chart" id="ch-rb-yields" style="min-height: 12rem"></div></div>'
                 f'<div><h3 class="rb-h2">10 年減 2 年息差</h3>{p(sline)}<p class="rb-sub">基點；虛線為 0</p><div class="rb-chart" id="ch-rb-curve" style="min-height: 12rem"></div></div></div>'
                 + note(f"來源：{src}。息差用同一日的 10 年及 2 年期孳息計算。")
                 + '<h3 class="rb-h2">含義</h3>' + ("".join(p(x) for x in mean) if mean else note("孳息變化未確認，所以沒有描述。"))
                 + note("熊市／牛市指孳息上升／下降，變陡／變平指 10 年減 2 年息差擴闊／收窄；這些名稱只按方向及哪一端變動較大定義，不設幅度門檻，不是訊號。"))
    return card("rb-bonds", "美債", "".join(parts))


def ai_card(session):
    """SMH against the S&P 500: the SMH ÷ SPY chart and readings, and the memory basket's relative return."""
    S = {x["ticker"]: x for x in load("sectors")}
    R = {x["pair"]: x for x in load("ratio_summary")}
    smh, mem, r = S.get("SMH") or {}, S.get("AI_MEM") or {}, R.get("SMH_SPY") or {}
    lines = []
    if smh.get("rel1m") is not None and r.get("vs_50d") is not None:
        lines.append(f"SMH 對標普（比率 SMH ÷ SPY 的相對變化）：一個月 {sg(smh['rel1m'], 1)}、三個月 {sg(smh.get('rel3m') or 0, 1)} 個百分點；"
                     f"比率{'高於' if r['vs_50d'] > 0 else '低於'} 50 日均線 {abs(r['vs_50d']):.1f}%（{md(session)}）。")
    else:
        lines.append("SMH ÷ SPY：沒有數據。")
    if mem.get("rel1m") is not None:
        lines.append(f"記憶體籃子（MU、WDC、STX、SNDK，等權）對標普：一個月 {sg(mem['rel1m'], 1)}、三個月 {sg(mem.get('rel3m') or 0, 1)} 個百分點（{md(session)}）。")
    else:
        lines.append("記憶體籃子對標普：沒有數據。")
    body = (note("這是股價相對標普 500 的強弱，不是資金流量數據；持續跑輸代表相對賣壓，但分不出資金流出還是買盤減少。")
            + '<h3 class="rb-h2" style="margin-top:12px">SMH ÷ SPY（一年前＝100，最近六個月）</h3><div class="rb-chart" id="ch-rb-smh" style="min-height: 11rem"></div>'
            + "".join(p(x) for x in lines))
    return card("rb-ai", "AI／半導體：相對大市強弱", body)



# ---------- 市寬與輪動摘要 (above the rotation and breadth charts) ----------

QUAD = (("leading", "領先"), ("weakening", "轉弱"), ("lagging", "落後"), ("improving", "改善"))


def breadth_line():
    """The advance-decline line with SPY and the share above the 50-day average: latest, one week and one month."""
    rows = [x for x in load("breadth") if x.get("ad_line") is not None]
    if len(rows) < 22:
        return "市寬數據不足。"
    l, w, m = rows[-1], rows[-6], rows[-22]
    spy = lambda b: (l["spy_index"] / b["spy_index"] - 1) * 100 if l.get("spy_index") and b.get("spy_index") else None
    out = (f"升跌線 {l['ad_line']:,}（{md(l['date'])}），一週{rise(l['ad_line'] - w['ad_line'])}（對 {md(w['date'])}）、"
           f"一個月{rise(l['ad_line'] - m['ad_line'])}（對 {md(m['date'])}）")
    if spy(w) is not None and spy(m) is not None:
        out += f"；同期 SPY {sg(spy(w), 1)}% 及 {sg(spy(m), 1)}%"
    if l.get("pct50") is not None:
        out += f"；高於 50 日線的成份股 {l['pct50']:.1f}%，一週前 {w['pct50']:.1f}%，一個月前 {m['pct50']:.1f}%"
    return out + "。"


def rotation_head(session):
    return ('<h2 class="rb-h2">板塊輪動</h2>'
            + note("11 個板塊及貴金屬的相對輪動圖。可選對標普 500 或對半導體（SMH）、週線或日線，以及軌跡週數；"
                   "各板塊現時所在象限及轉換見上面的「市寬與輪動摘要」。"))


def breadth_head():
    return ('<h2 class="rb-h2">市寬</h2>'
            + note("升跌線（附 SPY 作比較）看每日上升與下跌股數的累計方向，高於 50 日線的成份股比例看中期趨勢覆蓋多少股份；"
                   "最新讀數見上面的「市寬與輪動摘要」。麥克連振盪指標、等權對市值加權、52 週新高新低及半導體市寬卡與這兩項重疊，"
                   "所以不列。來源：看板的標普 500 成份股數據。"))


def quadrant_of(rr, rm):
    """The rotation graph's quadrant, as in build_data.quadrant."""
    if rr is None or rm is None:
        return None
    return "leading" if rr >= 100 and rm >= 100 else "weakening" if rr >= 100 else "improving" if rm >= 100 else "lagging"


QNAME = dict(QUAD)


def moved(changes):
    return "、".join(f"{n}（{QNAME[a]}→{QNAME[b]}）" for n, a, b in changes)


def rotation_week(sectors, tails):
    """Weekly graph against the S&P 500: the sectors in each quadrant, and those that changed quadrant since last week."""
    names = {x["ticker"] for x in sectors}
    weeks = sorted({r["week"] for r in tails if r["ticker"] in names})
    week, prev = (weeks[-1], weeks[-2]) if len(weeks) > 1 else (weeks[-1] if weeks else None, None)
    by = {k: [x["name"] for x in sectors if x.get("quadrant") == k] for k, _ in QUAD}
    changes = [(x["name"], x["quadrant_1w"], x["quadrant"]) for x in sectors
               if x.get("quadrant") and x.get("quadrant_1w") and x["quadrant"] != x["quadrant_1w"]]
    text = (f"輪動（週線，對標普 500，截至 {md(week)}）：" + "；".join(f"{name} {'、'.join(by[k]) or '沒有'}" for k, name in QUAD) + "。")
    text += (f"與上週（{md(prev)}）比較，轉換象限的有 {moved(changes)}。" if changes else f"與上週（{md(prev)}）比較，沒有板塊轉換象限。")
    return text


def rotation_day(sectors, daily):
    """Daily graph against the S&P 500: only the sectors whose quadrant changed on the latest session."""
    names = {x["ticker"]: x["name"] for x in sectors}
    pts = {}
    for r in daily:
        if r["ticker"] in names:
            pts.setdefault(r["ticker"], []).append(r)
    dates = sorted({r["date"] for v in pts.values() for r in v})
    if len(dates) < 2:
        return "日線：數據不足。"
    d1, d0 = dates[-1], dates[-2]
    changes = []
    for t, v in pts.items():
        at = {r["date"]: quadrant_of(r.get("rs_ratio"), r.get("rs_mom")) for r in v}
        if at.get(d0) and at.get(d1) and at[d0] != at[d1]:
            changes.append((names[t], at[d0], at[d1]))
    head = f"日線（對標普 500，{md(d1)}對{md(d0)}）："
    return head + (f"轉換象限的有 {moved(changes)}。" if changes else "今日沒有板塊轉換象限。")


def market_summary_card():
    """市寬與輪動摘要: breadth in one sentence, weekly rotation, and the daily quadrant changes, from the board's data."""
    out = []
    for label, fn in (("市寬", lambda: "市寬：" + breadth_line()),
                      ("週線", lambda: rotation_week([x for x in load("sectors") if x.get("group") == "sector"], load("rrg_tails"))),
                      ("日線", lambda: rotation_day([x for x in load("sectors") if x.get("group") == "sector"], load("rrg_daily")))):
        try:
            out.append(p(fn()))
        except Exception as e:  # a data file changed shape: keep the other lines, say so
            print(f"market summary {label} failed:", repr(e), flush=True)
            out.append(note(f"{label}讀數暫時未能生成。"))
    out.append(note("象限按輪動圖的定義：相對強度及其動量都高於 100＝領先；強度高於 100、動量低於 100＝轉弱；兩者都低於 100＝落後；"
                    "強度低於 100、動量高於 100＝改善。週線的強度對 10 週平均、動量對 4 週前；日線對 20 日平均及 5 日前。"
                    "只描述位置及轉換，不是訊號。"))
    return card("rb-market-summary", "市寬與輪動摘要", "".join(out))


# ---------- credit ----------

def fmt_chg(x, d=0):
    return "—" if x is None else sg(x, d)


def credit_summary(m_now, series, pct):
    """Three short sentences above the credit table: levels with percentiles, the week's change, and the CCC−BB gap."""
    tiers = (("HY", "hy"), ("IG", "ig"), ("BB", "bb"), ("CCC", "ccc"))
    when = md(m_now.get("hy_oas_date"))
    level = [f"{name} {series(f'{k}_oas')[-1]:,.0f}（第 {pct(series(f'{k}_oas')):.0f}）" for name, k in tiers]
    out = [f"息差（{when}，基點；括號內為三年百分位）：{'、'.join(level)}。"]
    wk = [(name, m_now.get(f"{k}_oas_1w")) for name, k in tiers]
    wide = "、".join(f"{n} {sg(v)}" for n, v in wk if v is not None and v > 0) or "沒有"
    narrow = "、".join(f"{n} {sg(v)}" for n, v in wk if v is not None and v < 0) or "沒有"
    base = m_now.get("hy_oas_base_1w")
    out.append(f"一週{f'（{md(base)}至{when}）' if base else ''}擴闊：{wide}；收窄：{narrow}。")
    cb = [a - b for a, b in zip(series("ccc_oas"), series("bb_oas"))]
    c1w, b1w = m_now.get("ccc_oas_1w"), m_now.get("bb_oas_1w")
    out.append(f"CCC−BB {cb[-1]:,.0f} 基點" + (f"，一週{move(c1w - b1w)}" if c1w is not None and b1w is not None else "")
               + f"，三年第 {pct(cb):.0f} 百分位。")
    return "".join(p(x) for x in out)


def credit_table():
    """The full credit table: every series the board holds, with the horizons each one really has."""
    m_now, r, f = load("rates_now")[0], load("rates"), load("funding")[0]
    R = {x["pair"]: x for x in load("ratio_summary")}
    series = lambda k: rate_series(r, k)
    pct = pct3y
    lad = {x["id"]: x for x in f["ladder"]}
    MEAN = {"hy": "高收益債總體", "ig": "投資級總體；擴闊代表問題不只在低質", "bb": "高收益債最好一級；開始擴闊代表壓力向上傳",
            "ccc": "最弱一級，通常最早反應"}
    rows, row = [], lambda *c: rows.append("<tr>" + "".join(
        f'<td{" class=rb-left" if i in (0, 8) else ""}>{escape(str(v))}</td>' for i, v in enumerate(c)) + "</tr>")
    group = lambda t: rows.append(f'<tr class="rb-sep"><td colspan="9">{escape(t)}</td></tr>')
    group("息差（基點）")
    for k, name in (("hy", "HY"), ("ig", "IG"), ("bb", "BB"), ("ccc", "CCC")):
        s = series(f"{k}_oas")
        row(name, f"{s[-1]:,.0f}", fmt_chg(m_now[f"{k}_oas_1d"]), fmt_chg(m_now[f"{k}_oas_1w"]), fmt_chg(m_now[f"{k}_oas_1m"]),
            fmt_chg(m_now[f"{k}_oas_3m"]), f"第 {pct(s):.0f}", md(m_now["hy_date"]), MEAN[k])
    for k, name, nt in (("b", "B", "高收益債的中間一級：評級低於 BB、高於 CCC"), ("bbb", "BBB", "投資級最低一級；擴闊代表跌出投資級的憂慮")):
        x = lad[k]
        row(name, f"{x['bp']:,}", "—", "—", fmt_chg(x["chg_bp"]), "—", f"第 {x['pct3y']}", md(x["date"]), nt)
    cb = [a - b for a, b in zip(series("ccc_oas"), series("bb_oas"))]
    row("CCC−BB", f"{cb[-1]:,.0f}", fmt_chg(cb[-1] - cb[-2]), fmt_chg(cb[-1] - cb[-6]), fmt_chg(cb[-1] - cb[-22]), fmt_chg(cb[-1] - cb[-64]),
        f"第 {pct(cb):.0f}", md(m_now["hy_date"]), "差距擴闊＝壓力集中最弱一級；收窄可以是好轉，也可以是 BB 追上來")
    group("孳息及價格代理")
    ys = series("ig_yield")
    row("IG 孳息（%）", f"{ys[-1] / 100:.2f}", fmt_chg(m_now["ig_yield_1d"]), fmt_chg(m_now["ig_yield_1w"]), fmt_chg(m_now["ig_yield_1m"]), fmt_chg(m_now["ig_yield_3m"]),
        f"第 {pct(ys):.0f}", md(m_now["hy_date"]), "企業借貸的實際成本（變化以基點計）")
    h = R["HYG_IEF"]
    row("HYG／IEF（%）", f"{sg(h['vs_50d'], 1)} 對 50 日線", sg(h["chg1d"], 2), sg(h["chg5d"], 2), sg(h["chg20d"], 2), sg(h["chg60d"], 2), "—",
        md(load("refresh_meta")[0]["session"]), "息差遲一日公布，這是當日的價格代理；低於 50 日線是惡化條件之一")
    group("資金市場")
    sp = f["spread"]
    row("SOFR−IORB（基點）", sg(sp[-1]["bp"]), fmt_chg(sp[-1]["bp"] - sp[-2]["bp"]), fmt_chg(sp[-1]["bp"] - sp[-6]["bp"]), fmt_chg(sp[-1]["bp"] - sp[-22]["bp"]), fmt_chg(sp[-1]["bp"] - sp[-64]["bp"]),
        "—", md(sp[-1]["date"]), "持續高於 0 代表短期資金偏緊；月底及結算日常有噪音")
    row("常備回購（億美元）", f"{f['srf']['bn'] * 10:,.0f}", "—", "—", "—", "—", "—", md(f["srf"]["date"]), f"銀行向聯儲借現金；高位 {f['srf']['peak_bn'] * 10:,.0f} 億（{f['srf']['peak_date']}）")
    row("貼現窗口（億美元）", f"{f['dw']['bn'] * 10:,.0f}", "—", fmt_chg((f["dw"]["bn"] - f["dw"]["prev_bn"]) * 10, 1), "—", "—", f"第 {f['dw']['pct3y']}", md(f["dw"]["date"]), "每週數據；偏高代表部分銀行要找後備資金")
    b = load("borrower_credit")[0]
    group("AI 借款人（第三方參考報價，非官方；日期不一）")
    for x in b.get("cds_reference", []):
        rs = sorted((q for q in x.get("readings", []) if q.get("value_bp")), key=lambda q: q["date"])
        if rs:
            prev = rs[-2]["value_bp"] if len(rs) > 1 else None
            row(f"{x['name']} CDS（基點）", f"{rs[-1]['value_bp']:,.0f}", "—", "—", "—", "—", "—", md(rs[-1]["date"]),
                f"上次 {prev:,.0f}" if prev is not None else "只有一個報價")
    for i in b.get("issuers", []):
        q = [x for x in i.get("reference_quotes", []) if not x.get("superseded") and x.get("yield_pct") is not None]
        if q:
            q = sorted(q, key=lambda x: x.get("price_date", ""))
            row(f"{i['name']} {q[-1]['instrument'][:18]} 孳息（%）", f"{q[-1]['yield_pct']:.2f}", "—", "—", "—", "—", "—", md(q[-1]["price_date"]), f"債價 {q[-1].get('clean_price_per_100', '—')}；非 CDS 或 OAS")
    head = "".join(f"<th{' class=rb-left' if i in (0, 8) else ''}>{t}</th>" for i, t in enumerate(
        ("項目", "最新", "日", "週", "月", "3 個月", "三年百分位", "數據日", "意思")))
    try:
        summary = credit_summary(m_now, series, pct)
    except (KeyError, IndexError, TypeError, ValueError) as e:  # a data file changed shape: keep the table, say so
        print("credit summary failed:", repr(e), flush=True)
        summary = note("信用現況摘要暫時未能生成。")
    return ('<div class="rb-card rb-wide" id="rb-credit"><h2 class="rb-h2">信用總表</h2>' + summary + note(
        "日、週、月、3 個月是變化。「—」代表這個系列沒有該期數據；B 和 BBB 只有約一個月的變化，貼現窗口的週欄是對上一週。")
            + f'<div class="rb-tablebox" style="max-height:none"><table class="rb-table rb-credit"><tr>{head}</tr>{"".join(rows)}</table></div></div>')


# ---------- 油價頁 ----------

def oil_row():
    try:
        return load("oil")[0]
    except (OSError, ValueError, IndexError):
        return None


def since_month(d):
    return f"{d[:4]} 年 {int(d[5:7])} 月" if d else "日期未確認"


def ovx_reading(oil):
    """The latest OVX, the reading on or before seven days earlier, and its percentile: in the whole FRED history when the
    oil data carries it, otherwise in the readings the board keeps."""
    o = (oil or {}).get("ovx") or {}
    rows = o.get("rows") or []
    if not rows:
        return None
    last = rows[-1]
    wk = [r for r in rows if r["date"] <= (date.fromisoformat(last["date"]) - timedelta(days=7)).isoformat()]
    h = o.get("hist") or {}
    if h.get("pct") is not None:
        pct, where = h["pct"], f"{since_month(h.get('first'))}以來 {h['n']:,} 個收市讀數"
    else:
        pct, where = round(sum(r["v"] <= last["v"] for r in rows) / len(rows) * 100), f"看板保存的 {len(rows)} 個讀數（{rows[0]['date']} 起）"
    return dict(last=last, week=wk[-1] if wk else None, chg=round(last["v"] - wk[-1]["v"], 2) if wk else None, pct=pct, where=where)


# ---- Brent curve and spreads ----

SPREAD_NAME = {"m1_m2": "近月對次月", "m1_m6": "近月對第 6 個月", "m1_dec_next": "近月對明年 12 月", "brent_wti": "Brent 對 WTI"}
FAR_NAME = {"m1_m2": "次月", "m1_m6": "第 6 個月", "m1_dec_next": "明年 12 月合約"}


def spread_meaning(key, now, week):
    """What a spread means by definition, and what its change over the week means. No size cut-off."""
    chg = None if now is None or week is None else round(now - week, 2)
    if key == "brent_wti":
        level = ("Brent 比 WTI 貴：按定義，海運原油（Brent）比美國內陸原油（WTI）貴" if now > 0 else
                 "Brent 比 WTI 便宜：按定義，海運原油（Brent）比美國內陸原油（WTI）便宜" if now < 0 else "Brent 與 WTI 同價")
        if chg is None:
            return level + "。"
        if chg == 0:
            return level + "；一週不變。"
        if now > 0 and week > 0:
            return level + ("；一週價差擴闊，即海運原油的定價比美國內陸原油更緊。" if chg > 0 else
                            "；一週價差收窄，即海運原油的定價相對美國內陸原油轉鬆。")
        return level + ("；一週 Brent 相對 WTI 轉貴，即海運原油的定價相對美國內陸原油轉緊。" if chg > 0 else
                        "；一週 Brent 相對 WTI 轉便宜，即海運原油的定價相對美國內陸原油轉鬆。")
    far = FAR_NAME[key]
    level = (f"近月比{far}貴，即逆價差：買家為即時供應付溢價" if now > 0 else
             f"近月比{far}便宜，即正價差：遠期交收較貴，市場沒有為即時供應付溢價" if now < 0 else f"近月與{far}同價")
    if chg is None:
        return level + "。"
    if chg == 0:
        return level + "；一週不變。"
    if now > 0 and week > 0:
        name = "溢價擴闊" if chg > 0 else "溢價收窄"
    elif now < 0 and week < 0:
        name = "正價差收窄" if chg > 0 else "正價差擴闊"
    elif now > 0:
        name = "由正價差轉為逆價差" if week < 0 else "由同價轉為逆價差"
    elif now < 0:
        name = "由逆價差轉為正價差" if week > 0 else "由同價轉為正價差"
    else:
        name = "價差歸零"
    mean = "近月相對轉貴，即市場為近期供應緊張定價更多" if chg > 0 else "近月相對轉便宜，即為近期緊張所付的溢價減少"
    return f"{level}；一週{name}：{mean}。"


def spread_line(x):
    """One spread: its value, its change over the week on the same pair of contracts, and spread_meaning."""
    name = SPREAD_NAME[x["key"]]
    pair = f"Brent {x['a']} 減 WTI 連續近月" if x["b"] == "WTI" else f"{x['a']} 減 {x['b']}"
    if x.get("now") is None:
        return f"{name}（{pair}）：兩個收市日期不同，今次不計。"
    head = f"{name}（{pair}）：{sg(x['now'], 2)} 美元（{md(x['date'])}）"
    if x.get("week") is not None:
        head += f"；一週 {sg(x['now'] - x['week'], 2)} 美元（{md(x['week_date'])}為 {sg(x['week'], 2)}）"
    else:
        head += "；一週前沒有同一對合約的收市"
    return head + "。" + spread_meaning(x["key"], x["now"], x.get("week"))


def curve_move_sentence(rows):
    """The whole curve's move over the week: front and furthest contract, how many rose and fell, and what that means by
    definition (the whole curve rising = a longer-lasting supply reduction being priced)."""
    ch = [r for r in rows if r.get("chg_1w") is not None]
    if len(ch) < 2:
        return None
    up, down = sum(r["chg_1w"] > 0 for r in ch), sum(r["chg_1w"] < 0 for r in ch)
    f, l = ch[0], ch[-1]
    text = f"一週內（對 {md(f.get('week_date'))}）近月 {f['month']} {rise(f['chg_1w'], '美元', 2)}、最遠的 {l['month']} {rise(l['chg_1w'], '美元', 2)}；"
    if up == len(ch):
        return text + f"全部 {len(ch)} 個合約上升，即整條曲線上升：連遠月也升，按定義是市場為較持久的供應減少定價。"
    if down == len(ch):
        return text + f"全部 {len(ch)} 個合約下跌，即整條曲線下跌：連遠月也跌，市場為供應減少所付的價格在各個期限都下降。"
    text += f"{len(ch)} 個合約中 {up} 個上升、{down} 個下跌，曲線各段方向不一"
    if f["chg_1w"] > 0 and l["chg_1w"] <= 0:
        return text + "：升幅在近期合約，遠月沒有同樣上升，即定價的是近期緊張，不是較持久的供應減少。"
    if f["chg_1w"] < 0 and l["chg_1w"] >= 0:
        return text + "：近月下跌而遠月沒有下跌，即近期緊張的溢價減少，較持久的定價沒有減少。"
    return text + "。"


def brent_expiry(month):
    """ICE Brent: the last business day of the second month before the delivery month (holidays not checked)."""
    y, m = int(month[:4]), int(month[5:7]) - 1
    if m < 1:
        y, m = y - 1, 12
    d = date(y, m, 1) - timedelta(days=1)
    while d.weekday() > 4:
        d -= timedelta(days=1)
    return d


def oil_curve_card():
    oil = oil_row()
    curve = (oil or {}).get("curve") or {}
    rows, lines = curve.get("rows") or [], curve.get("lines") or {}
    if not rows:
        return card("rb-oil-curve", "Brent 期貨曲線", note("沒有曲線數據：Yahoo 未能下載，或尚未建立 oil.json。"))
    f = rows[0]
    lg = [("var(--series-1)", "", f"最新（{md(lines.get('latest', {}).get('date') or f['date'])}）")]
    for key, color, cls, name in (("week", "var(--series-2)", "", "一週前"), ("month", "var(--cds-chart-muted)", "dash", "一個月前")):
        if lines.get(key):
            lg.append((color, cls, f"{name}（{md(lines[key]['date'])}）"))
    legend = '<div class="rb-legend">' + "".join(f'<span class="{c}" style="--sw:{col}">{escape(t)}</span>' for col, c, t in lg) + "</div>"
    head = (f"橫軸是合約交收月份，縱軸是每桶美元；近月 {f['month']} {f['close']:.2f} 美元、"
            f"最遠的 {rows[-1]['month']} {rows[-1]['close']:.2f} 美元（{md(f['date'])}）。")
    move = curve_move_sentence(rows)
    missing = [n for k, n in (("week", "一週前"), ("month", "一個月前")) if not lines.get(k)]
    spreads = "".join(f"<li>{escape(spread_line(x))}</li>" for x in curve.get("spread_list") or [])
    hist = curve.get("history_from")
    body = (p(head) + (p(move) if move else "") + legend + '<div class="rb-chart" id="ch-rb-oilcurve" style="min-height: 13rem"></div>'
            + '<h3 class="rb-h2" style="margin-top:8px">價差</h3>'
            + (f'<ul class="rb-spreads">{spreads}</ul>' if spreads else note("價差：沒有數據。"))
            + note("價差＝近月收市減較遠合約收市（Brent 對 WTI 用 WTI 連續近月 CL=F，兩者的交收月份可以不同）。正數即逆價差（近月較貴），"
                   "負數即正價差（遠月較貴）。一週變化用同一對合約在一週前的收市，所以近月轉倉不會令數字機械性跳動。這些名稱只按定義，不設幅度門檻，不是訊號。")
            + note(f"近月 {f['month']} 合約約於 {md(brent_expiry(f['month']).isoformat())}到期（ICE Brent 規則，未計假期），之後近月改為下一個合約。"
                   f"曲線紀錄由 {f'{hist[:4]} 年 {md(hist)}' if hist else '（未有紀錄）'}起：每次更新存入各合約當日收市，並以 Yahoo 各合約最近三個月的每日收市補足，保留 400 日"
                   + (f"；未有{'及'.join(missing)}的紀錄，所以不畫該線" if missing else "") + "。"
                   "來源：Yahoo（NYMEX Brent 金融期貨 BZ*.NYM，以 ICE Brent 結算；WTI CL=F）。"))
    return card("rb-oil-curve", "Brent 期貨曲線", body)


# ---- options ----

def option_side(r):
    k = f"{r.get('key', '')} {r.get('item', '')}".lower()
    return "put" if ("put" in k or "認沽" in k) else "call" if ("call" in k or "認購" in k) else None


def option_measure(r):
    k = f"{r.get('key', '')} {r.get('item', '')}".lower()
    return "未平倉合約" if ("_oi" in k or "open interest" in k or "未平倉" in k) else "成交"


def options_sides(readings):
    """Put against call from the hand-kept options readings, on the latest date that has both of the same kind."""
    opts = [r for r in readings or [] if r.get("group") == "options" and r.get("date") and isinstance(r.get("value"), (int, float))
            and option_side(r)]
    pairs = {}
    for r in opts:
        pairs.setdefault((option_measure(r), r["date"]), {})[option_side(r)] = r
    both = sorted((k for k, v in pairs.items() if len(v) == 2), key=lambda k: k[1])
    if both:
        what, d = both[-1]
        put, call = pairs[both[-1]]["put"], pairs[both[-1]]["call"]
        side = ("認沽（put）較多" if put["value"] > call["value"] else "認購（call）較多" if call["value"] > put["value"] else "兩者相同")
        return (f"人手紀錄：{md(d)} 認沽{what} {put['value']:,} {put.get('unit', '')}、認購{what} {call['value']:,} {call.get('unit', '')}，"
                f"{side}，來源為{put.get('provider', '')}。這只顯示市場成交或持有了甚麼，不顯示哪一方對。")
    if opts:
        r = max(opts, key=lambda r: r["date"])
        other = "認購" if option_side(r) == "put" else "認沽"
        return (f"人手紀錄只有 {md(r['date'])}的{r.get('item', '')}：{r['value']:,} {r.get('unit', '')}，來源為{r.get('provider', '')}；"
                f"沒有同日的{other}數字，所以不能說哪一方較大。這類數字只顯示市場成交了甚麼，不顯示哪一方對。")
    return None


def ovx_lines(oil=None):
    """The implication line under the OVX chart: level, percentile in its own history, the week's change and what that
    means by definition; then put against call from the hand-kept readings when they exist."""
    oil = oil if oil is not None else oil_row()
    x = ovx_reading(oil)
    if not x:
        return ["OVX：沒有數據。"]
    l, w, c = x["last"], x["week"], x["chg"]
    text = f"OVX {l['v']:.1f}（{md(l['date'])}），在 {x['where']}中第 {x['pct']} 百分位，即 {x['pct']}% 的讀數等於或低於現水平"
    if w:
        text += f"；一週{rise(c, '', 1)}（{md(w['date'])}為 {w['v']:.1f}）"
    text += "。按定義，"
    text += ("OVX 上升即期權市場為油價較大的波動定價，升或跌都包括，它不顯示方向。" if c and c > 0 else
             "OVX 下降即期權市場為油價較小的波動定價，升或跌都包括，它不顯示方向。" if c and c < 0 else
             "它量度期權市場預期的波動大小，升或跌都包括，不顯示方向。")
    out = [text]
    sides = options_sides(((oil or {}).get("manual") or {}).get("readings"))
    if sides:
        out.append(sides)
    return out


def ovx_html():
    return "".join(p(x) for x in ovx_lines())


# ---- managed money, five oil contracts ----

def short_names(parts):
    """Short names of the contracts included, with WTI's two exchanges together."""
    keys = [x["key"] for x in parts or []]
    wti = [n for k, n in (("wti_nymex", "紐約"), ("wti_ice", "ICE")) if k in keys]
    out = [n for k, n in (("brent", "Brent"),) if k in keys] + ([f"WTI〔{'及'.join(wti)}〕"] if wti else [])
    return "、".join(out + [n for k, n in (("rbob", "RBOB"), ("ulsd", "ULSD"), ("gasoil", "Gasoil")) if k in keys])

def positions_line(P, today=None):
    s = (P or {}).get("summary") or {}
    if not s:
        return None
    today = today or date.today().isoformat()
    side = f"淨 long {s['net']:,.1f}" if s["net"] >= 0 else f"淨 short {abs(s['net']):,.1f}"
    text = (f"{md(s['date'])}持倉：五個合約合計管理資金 long {s['long']:,.1f}、short {s['short']:,.1f}，{side} 百萬桶")
    if s.get("chg_1w") is not None:
        text += f"；淨額一週{more(s['chg_1w'], '百萬桶', 1)}（對 {md(s.get('chg_1w_base'))}）"
    text += f"；在 {since_month(s.get('first'))}以來 {s['n']:,} 週中第 {s['pct']} 百分位，即 {s['pct']}% 的週份淨額等於或低於現水平。"
    age = (date.fromisoformat(today) - date.fromisoformat(s["date"])).days
    if age > 10:
        text += f"持倉日距今 {age} 日，比一般的週二持倉、週五公布舊。"
    return text


def oil_positions_card():
    oil = oil_row()
    P = (oil or {}).get("positions") or {}
    line = positions_line(P)
    title = "管理資金持倉（五個石油合約合計）"
    if not line:
        return card("rb-oil-pos", title, note("沒有持倉數據：CFTC 及 ICE 都未能下載，或尚未建立 oil.json。"))
    legend = ('<div class="rb-legend"><span style="--sw:var(--series-1)">long（零線以上）</span>'
              '<span style="--sw:var(--series-2)">short（以負數畫在零線以下）</span><span style="--sw:var(--color-fg)">淨額（long 減 short）</span></div>')
    rows = ""
    for x in P.get("parts") or []:
        rows += (f"<tr><td class=rb-left>{escape(x['label'])}</td><td>{x['long']:,}</td><td>{x['short']:,}</td><td>{sg(x['net'])}</td>"
                 f"<td>{x['bbl']:,.0f}</td><td>{sg(x['net_mb'], 1)}</td><td>{'—' if x.get('chg_1w_mb') is None else sg(x['chg_1w_mb'], 1)}</td>"
                 f"<td class=rb-left>{md(x['date'])}</td></tr>")
    head = "".join(f"<th{' class=rb-left' if i in (0, 7) else ''}>{t}</th>" for i, t in enumerate(
        ("合約", "long（張）", "short（張）", "淨額（張）", "每張桶數", "淨額（百萬桶）", "一週變化（百萬桶）", "持倉日")))
    gaps = []
    if P.get("missing"):
        gaps.append("缺少：" + "、".join(P["missing"]) + "（未能下載，合計不包括）")
    if P.get("behind"):
        gaps.append("、".join(f"{b['label']}只到 {md(b['latest'])}" for b in P["behind"]) + f"，合計只計到所有合約都有數據的 {md(P['summary']['date'])}")
    body = (p(line) + legend + '<div class="rb-chart" id="ch-rb-oilpos" style="min-height: 15rem"></div>'
            + f'<div class="rb-tablebox" style="max-height:none"><table class="rb-table rb-bondt"><tr>{head}</tr>{rows}</table></div>'
            + (note("；".join(gaps) + "。") if gaps else "")
            + note("管理資金＝CFTC 及 ICE 分類持倉報告中的 managed money（基金及商品交易顧問）。只計期貨，不含期權；每週二持倉，週五公布。"
                   f"換算：ICE Brent 及 WTI（紐約商品交易所及 ICE 歐洲兩個合約）每張 1,000 桶；RBOB 及 ULSD 每張 42,000 美制加侖，即 1,000 桶；"
                   f"ICE Gasoil 每張 100 公噸，按每噸 {P.get('gasoil_bbl_per_tonne', 7.45)} 桶換算為 {100 * P.get('gasoil_bbl_per_tonne', 7.45):,.0f} 桶。"
                   "圖由 ICE 公開檔案的第一年（2011 年）起，只計六個系列都有報告的週份。"
                   "來源：CFTC 分類持倉報告（WTI、RBOB、ULSD；publicreporting.cftc.gov）及 ICE Futures Europe 持倉報告（Brent、Gasoil；ice.com COTHist 年度檔案）。"))
    return card("rb-oil-pos", title, body)


# ---- 戰事最新進展 ----

def news_row():
    """The stored headline feed (macro/data/news_feed.json), or None."""
    try:
        return json.loads(NEWS_FEED.read_text(encoding="utf-8"))[0]
    except (OSError, ValueError, IndexError, KeyError, TypeError):
        return None


UK = ZoneInfo("Europe/London")


def uk_time(iso):
    """A UTC time stamp as UK local time, e.g. 11月15日 14:30 (as on the 新聞與連接 page)."""
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(UK)
    except (TypeError, ValueError):
        return "—"
    return f"{d.month}月{d.day}日 {d:%H:%M}"


def uk_date(iso):
    """A UTC time stamp's date in the UK, as YYYY-MM-DD."""
    return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(UK).date().isoformat()


def ext_link(text, url):
    if url and str(url).startswith("https://"):
        return f'<a href="{escape(url)}" target="_blank" rel="noopener noreferrer">{escape(text or "來源")}</a>'
    return escape(text or "—")


def war_headlines(feed):
    """The automatic block: the newest WAR_HEADLINES headlines of the feed's war topic, newest first, with UK time and
    publisher. The feed keeps only official items and named established publishers (news_feed.PUBLISHERS)."""
    head = '<h3 class="rb-h2" style="margin-top:4px">最新報道（自動抓取）</h3>'
    if not feed:
        return head + note("未有自動抓取紀錄（macro/data/news_feed.json）；看板運行時每 30 分鐘自動抓取一次。")
    items = sorted((x for x in feed.get("items") or [] if isinstance(x, dict) and x.get("topic") == "war" and x.get("published")),
                   key=lambda x: x["published"], reverse=True)[:WAR_HEADLINES]
    when = (f'上次成功抓取：{uk_time(feed["fetched_at"])}（英國時間）' if feed.get("fetched_at") else "未有成功抓取")
    if feed.get("attempted_at") and feed.get("attempted_at") != feed.get("fetched_at"):
        when += f'；{uk_time(feed["attempted_at"])} 的抓取失敗，以下是上次成功抓取的標題'
    out = [head, note(f"{when}。Google News 搜尋最近兩日的戰事報道（伊朗、海灣、荷姆茲、油輪及港口、停火談判），"
                      "只保留官方網站及具名新聞機構的標題，看板運行時每 30 分鐘自動抓取；只存標題、來源及時間，"
                      "級別不由標題推斷。")]
    if items:
        rows = "".join(f"<tr><td class=rb-left>{escape(uk_time(x['published']))}</td><td class='rb-left rb-wrap'>{ext_link(x.get('title'), x.get('link'))}</td>"
                       f"<td class=rb-left>{escape(x.get('publisher') or '—')}</td></tr>" for x in items)
        out.append('<div class="rb-tablebox" style="max-height:none"><table class="rb-table rb-war"><tr><th class=rb-left>時間（英國）</th>'
                   f'<th class=rb-left>標題</th><th class=rb-left>來源</th></tr>{rows}</table></div>')
    else:
        out.append(note("最近七日沒有抓取到戰事報道。"))
    return "".join(out)


def war_card(today=None, feed=None):
    """The newest automatic war headlines (war_headlines), then the hand-kept war events and the escalation ladder
    (evidence/oil_tracking.json, key `war`) with two readings: the rung of the most recent event (the highest on
    that date) and the highest rung in the list with its latest date; no scores or probabilities. A rung is never derived
    from headlines; when the newest headline is dated (UK) after the newest hand-kept event, one line says so."""
    today = today or date.today().isoformat()
    feed = news_row() if feed is None else feed
    oil = oil_row()
    W = (((oil or {}).get("manual") or {}).get("war")) or {}
    ladder = {x["n"]: x for x in W.get("ladder") or []}
    ok = lambda e: (isinstance(e.get("date"), str) and len(e["date"]) == 10 and str(e.get("source", "")).startswith("https://")
                    and e.get("rung") in ladder and e.get("text"))
    events = sorted((e for e in W.get("events") or [] if ok(e)), key=lambda e: (e["date"], e["rung"]), reverse=True)
    auto = war_headlines(feed)
    hand = (f'<h3 class="rb-h2" style="margin-top:12px">已整理的事件及升級階梯（人手整理至 {escape(md(W.get("updated")) if W.get("updated") else "未記錄")}）</h3>')
    if not ladder or not events:
        return (f'<div class="rb-card" id="rb-war"><h2 class="rb-h2">戰事最新進展</h2>{auto}{hand}'
                + note("沒有已記錄的事件或升級階梯（evidence/oil_tracking.json 的 war）。") + "</div>")
    last = events[0]
    cur = ladder[last["rung"]]
    age = (date.fromisoformat(today) - date.fromisoformat(last["date"])).days
    top = max(e["rung"] for e in events)
    top_date = max(e["date"] for e in events if e["rung"] == top)
    since = min(e["date"] for e in events)
    now = (f"最近一宗事件：第 {cur['n']} 級「{cur['name']}」（{md(last['date'])}），距今 {age} 日；之後的事件未有紀錄。")
    peak = (f"清單期內到過的最高級別：第 {top} 級「{ladder[top]['name']}」，最近一次在 {md(top_date)}（清單由 {md(since)} 起）。")
    newest = max((x["published"] for x in (feed or {}).get("items") or [] if isinstance(x, dict) and x.get("topic") == "war" and x.get("published")), default=None)
    try:
        newer = newest is not None and uk_date(newest) > last["date"]
    except ValueError:
        newer = False
    rows = "".join(f"<tr><td class=rb-left>{e['date']}</td><td class='rb-left rb-wrap'>{escape(e['text'])}</td>"
                   f"<td class=rb-left>第 {e['rung']} 級</td><td class=rb-left><a href=\"{escape(e['source'])}\" target=\"_blank\" rel=\"noopener noreferrer\">"
                   f"{escape(e.get('provider') or '來源')}</a>{'（轉述）' if e.get('second_hand') else ''}</td></tr>" for e in events)
    steps = "".join(f"<li{' class=rb-now' if n == cur['n'] else ''}><b>第 {n} 級 {escape(x['name'])}</b>：{escape(x['means'])}"
                    f"{'（現處）' if n == cur['n'] else ''}</li>" for n, x in sorted(ladder.items()))
    body = (auto + hand + (note(W["note"]) if W.get("note") else "") + p(now) + p(peak)
            + (p("自動抓取的報道比已整理的清單新，級別未包括這些報道。") if newer else "")
            + '<div class="rb-tablebox" style="max-height:none"><table class="rb-table rb-war"><tr><th class=rb-left>日期</th><th class=rb-left>事件</th>'
            + f'<th class=rb-left>級別</th><th class=rb-left>來源</th></tr>{rows}</table></div>'
            + '<h3 class="rb-h2" style="margin-top:8px">升級階梯（由低至高，按可觀察的事件定義）</h3>'
            + f'<ol class="rb-ladder">{steps}</ol>'
            + note(W.get("rule") or "兩行讀數只按清單內已記錄事件的級別，不是評分或機率；較高級別的情況不會因此當作已經停止。"))
    return f'<div class="rb-card" id="rb-war"><h2 class="rb-h2">戰事最新進展</h2>{body}</div>'


# ---------- 油市總結 ----------

def oil_summary(today=None):
    """Three questions from the oil page's own data: what institutions are pricing (curve shape, option volatility),
    what they are doing (managed-money positions), and what the physical market shows (inventories, Dated Brent)."""
    today = today or date.today().isoformat()
    try:
        oil = load("oil")[0]
    except (OSError, ValueError, IndexError):
        return card("rb-oil-summary", "油市總結", note("油價資料未能載入，所以沒有總結。"))
    age = lambda d: (date.fromisoformat(today) - date.fromisoformat(d)).days
    priced, doing, physical, gaps = [], [], [], []
    # pricing: price, curve, OVX
    bz = [r for r in (load("brent") or []) if r.get("close") is not None]
    if bz:
        last = bz[-1]
        wk = [r for r in bz if r["date"] <= (date.fromisoformat(last["date"]) - timedelta(days=7)).isoformat()]
        priced.append(f"Brent 近月 {last['close']:.2f} 美元（{md(last['date'])}）" + (f"，對 {md(wk[-1]['date'])}{rise(last['close'] - wk[-1]['close'], '美元', 2)}" if wk else ""))
    else:
        gaps.append("Brent 近月價格")
    curve = oil.get("curve") or {}
    rows, sp = curve.get("rows") or [], curve.get("spreads") or {}
    if sp.get("wti_front") is not None:
        priced.append(f"WTI 近月 {sp['wti_front']:.2f} 美元（{md(sp.get('wti_date'))}）")
    if rows and sp.get("m1_dec_next") is not None:
        f = rows[0]
        dn = next((r for r in rows if r["month"] == f"{int(f['date'][:4]) + 1}-12"), None)
        shape = "近月高於遠月（逆價差）" if sp["m1_dec_next"] > 0 else "近月低於遠月（正價差）" if sp["m1_dec_next"] < 0 else "近月與遠月持平"
        txt = (f"期貨曲線{shape}：近月（{f['month']}）減明年 12 月合約 {sg(sp['m1_dec_next'], 2)} 美元，"
               f"近月減次月 {sg(sp.get('m1_m2') or 0, 2)} 美元")
        if dn and f.get("chg_1w") is not None and dn.get("chg_1w") is not None:
            txt += f"；一週內近月{rise(f['chg_1w'], '美元', 2)}、明年 12 月{rise(dn['chg_1w'], '美元', 2)}，差價{rise(f['chg_1w'] - dn['chg_1w'], '美元', 2)}（對 {md(f.get('week_date'))}）"
        priced.append(txt)
    else:
        gaps.append("期貨曲線")
    ox = ovx_reading(oil)
    if ox:
        priced.append(f"原油期權隱含波幅 OVX {ox['last']['v']:.1f}（{md(ox['last']['date'])}）"
                      + (f"，對 {md(ox['week']['date'])}{rise(ox['chg'], '', 1)}" if ox["week"] else "")
                      + f"，在 {ox['where']}中第 {ox['pct']} 百分位")
    else:
        gaps.append("OVX")
    # doing: managed money, five contracts together, then ICE Brent and CFTC WTI in lots
    P = oil.get("positions") or {}
    ps = P.get("summary") or {}
    if ps:
        txt = (f"管理資金在五個石油合約（{short_names(P.get('parts'))}）合計"
               + (f"淨 long {ps['net']:,.1f}" if ps["net"] >= 0 else f"淨 short {abs(ps['net']):,.1f}") + f" 百萬桶（{md(ps['date'])}持倉）")
        if ps.get("chg_1w") is not None:
            txt += f"，一週{more(ps['chg_1w'], '百萬桶', 1)}"
        if ps.get("chg_4w") is not None:
            txt += f"，四週{more(ps['chg_4w'], '百萬桶', 1)}"
        txt += f"，在 {since_month(ps.get('first'))}以來 {ps['n']:,} 週中第 {ps['pct']} 百分位"
        if P.get("missing"):
            txt += "（缺少 " + "、".join(P["missing"]) + "）"
        if age(ps["date"]) > 10:
            txt += f"；持倉日距今 {age(ps['date'])} 日，比一般的週二持倉、週五公布舊"
        doing.append(txt)
    else:
        gaps.append("五個石油合約的管理資金持倉")
    cot = oil.get("cot") or {}
    for i, (key, name) in enumerate((("brent", "ICE Brent"), ("wti", "CFTC WTI（紐約）"))):
        rs = cot.get(key) or []
        if not rs:
            gaps.append(f"{name} 管理資金持倉")
            continue
        l = rs[-1]
        side = f"淨 long {l['net']:,} 張" if l["net"] >= 0 else f"淨 short {abs(l['net']):,} 張"
        txt = (f"{'其中 ' if i == 0 else ''}{name} {side}" if ps else f"{name} 管理資金{side}（{md(l['date'])}持倉）")
        if len(rs) > 1:
            txt += f"，一週{more(l['net'] - rs[-2]['net'], '張')}"
        if len(rs) > 4:
            txt += f"，四週{more(l['net'] - rs[-5]['net'], '張')}"
        if not ps and age(l["date"]) > 10:
            txt += f"；持倉日距今 {age(l['date'])} 日，比一般的週二持倉、週五公布舊"
        doing.append(txt)
    # physical: EIA, SPR, Dated Brent
    eia = oil.get("eia") or {}
    tot = [eia[k]["latest"].get("chg_1w") for k in ("crude", "gasoline", "distillate") if eia.get(k) and eia[k].get("latest")]
    for k, name in (("crude", "商業原油（不含戰略儲備）"), ("gasoline", "汽油"), ("distillate", "餾分油（柴油）"), ("cushing", "Cushing 原油")):
        x = (eia.get(k) or {}).get("latest")
        if not x:
            gaps.append(name + "庫存")
            continue
        physical.append(f"{name} {x['v'] / 1000:,.1f} 百萬桶，一週{more(x['chg_1w'] / 1000, '百萬桶', 1)}，"
                        f"{'低於' if x['vs_avg5_pct'] < 0 else '高於'}五年同週平均 {abs(x['vs_avg5_pct']):.1f}%，"
                        f"對一年前{more(x['vs_yago'] / 1000, '百萬桶', 1)}")
    if len(tot) == 3 and None not in tot:
        physical.append(f"原油、汽油及餾分油三項合計一週{more(sum(tot) / 1000, '百萬桶', 1)}")
    spr = (eia.get("spr") or {}).get("latest")
    if spr:
        physical.append(f"戰略儲備 {spr['v'] / 1000:,.1f} 百萬桶，一週{more(spr['chg_1w'] / 1000, '百萬桶', 1)}，對一年前{more(spr['vs_yago'] / 1000, '百萬桶', 1)}")
    anyx = next((eia[k] for k in ("crude", "gasoline", "distillate") if eia.get(k)), None)
    if anyx:
        wk_end = anyx["latest"]["date"]
        nxt = anyx.get("next_release")
        stale = f"；EIA 已於 {md(nxt)} 公布新一週數據，看板未收錄" if nxt and nxt < today else ""
        physical.insert(0, f"EIA 週末 {md(wk_end)} 的庫存（{md(anyx.get('release'))} 公布{stale}）")
    prem = [r for r in ((oil.get("dated") or {}).get("rows") or []) if r.get("premium") is not None]
    if prem:
        l = prem[-1]
        wk = [r for r in prem if r["date"] <= (date.fromisoformat(l["date"]) - timedelta(days=6)).isoformat()]
        physical.append(f"Dated Brent（實貨）對期貨 {sg(l['premium'], 2)} 美元（{md(l['date'])}，FRED 遲數日）"
                        + (f"，對 {md(wk[-1]['date'])} 的 {sg(wk[-1]['premium'], 2)} 美元{rise(l['premium'] - wk[-1]['premium'], '美元', 2)}" if wk else ""))
    else:
        gaps.append("Dated Brent")
    tight = None
    if len(tot) == 3 and None not in tot:
        tight = ("以庫存變化計，本週三項合計下降，屬實貨收緊的方向" if sum(tot) < 0 else
                 "以庫存變化計，本週三項合計上升，本週沒有出現實貨收緊" if sum(tot) > 0 else "以庫存變化計，三項合計持平")
    body = (p("機構在定價甚麼：" + "；".join(priced) + "。") + p("機構在做甚麼：" + ("；".join(doing) or "沒有持倉數據") + "。")
            + p("實貨顯示甚麼：" + "；".join(physical) + "。" + (tight + "。" if tight else ""))
            + (note("缺少：" + "、".join(gaps) + "。") if gaps else "")
            + (note("自動數據問題：" + "；".join(oil["errors"]) + "。") if oil.get("errors") else "")
            + note("以上全部由看板數據按規則寫成，只描述水平、方向及大小，不設門檻，不作判斷。持倉是週二數據、週五公布；EIA 每週三公布上一週。"))
    return card("rb-oil-summary", "油市總結", body)
