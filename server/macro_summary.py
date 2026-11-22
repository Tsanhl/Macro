"""Text for the local board's 宏觀 view, built only from the board's data on every page load (no AI analysis):
the 每日摘要 with its 之後要看 list, the TGA, volatility (VIX family, VXN, MOVE, GVZ) and net-liquidity readings, the 美債 section (latest
auctions, 2-year and 10-year yields, the 10Y−2Y spread and its shape change by definition), the credit table with a short
description, the AI and semiconductor relative-strength
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


# ---------- 現在要看 (the top of the 宏觀 page; replaced the 每日摘要 on 2026-11-22, user) ----------

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


def spread_state(chg):
    return "—" if chg is None else "擴闊" if chg > 0 else "收窄" if chg < 0 else "持平"


def price_state(chg):
    return "—" if chg is None else "下跌" if chg < 0 else "上升" if chg > 0 else "持平"


WORSE = {"擴闊", "下跌", "有銀行用常備回購", "全面下跌", "大部分下跌"}


def credit_highs(rates, funding):
    """Spreads whose latest reading is the highest of the board's three years (100th percentile): a record within the
    window, not a chosen cut-off."""
    out = []
    for k, n in (("hy", "HY"), ("ig", "IG"), ("ccc", "CCC"), ("bb", "BB")):
        sr = rate_series(rates, f"{k}_oas")
        if sr and pct3y(sr) == 100:
            out.append(n)
    lad = {x["id"]: x for x in funding.get("ladder", [])}
    for k, n in (("b", "B"), ("bbb", "BBB")):
        if (lad.get(k) or {}).get("pct3y") == 100:
            out.append(n)
    cb = [x - y for x, y in zip(rate_series(rates, "ccc_oas"), rate_series(rates, "bb_oas"))]
    if cb and pct3y(cb) == 100:
        out.append("CCC−BB")
    return out


def chain_nodes(session):
    """The transmission chain, left to right: AI stocks, all stocks, low-grade credit, investment grade, private credit,
    the funding market. Each node: the week's reading and its direction by definition; a spread node is red when one
    of its series is at its three-year high. When FRED's spreads are a business day behind the stock data, the same
    day's price ratios (HYG ÷ IEF, LQD ÷ IEF) are shown beside them."""
    S = {x["ticker"]: x for x in load("sectors")}
    sec = [x for x in S.values() if x.get("group") == "sector" and x["ticker"] != "GDX" and x.get("r1w") is not None]
    r, rates, f = first("rates_now") or {}, load("rates"), first("funding") or {}
    R = {x["pair"]: x for x in load("ratio_summary")}
    P = {x["t"]: x for x in (((first("cross_asset") or {}).get("proxies") or {}).get("rows") or [])}
    highs = credit_highs(rates, f)
    lag = (r.get("hy_oas_date") or "") < session
    smh = (S.get("SMH") or {}).get("r1w")
    nodes = [dict(t="AI 股", v=f"SMH 一週 {sg(smh, 1)}%" if smh is not None else "—", s="半導體 ETF", st=price_state(smh))]
    down, rsp = [x for x in sec if x["r1w"] < 0], (S.get("RSP") or {}).get("r1w")
    st = ("全面下跌" if sec and len(down) == len(sec) else "大部分下跌" if len(down) > len(sec) / 2 else "部分下跌" if down else "沒有下跌")
    b = first("breadth_now") or {}
    sub = "；".join(x for x in (f"等權標普 {sg(rsp, 1)}%" if rsp is not None else "",
                                f"高於 50 日線 {b['pct50']:.0f}%（一週前 {b['pct50_1w']:.0f}%）" if b.get("pct50") is not None and b.get("pct50_1w") is not None else "") if x)
    nodes.append(dict(t="全部股票", v=f"{len(down)}／{len(sec)} 個板塊一週下跌", s=sub, st=st))
    hy, ccc = r.get("hy_oas_1w"), (rate_series(rates, "ccc_oas") or [None])[-1]
    sub = f"CCC {ccc:,.0f} 基點" + ("，三年最高" if "CCC" in highs else "") if ccc is not None else ""
    if lag and R.get("HYG_IEF"):
        sub += f"；{md(session)} HYG÷IEF {sg(R['HYG_IEF']['chg1d'], 2)}%（同日代理）"
    nodes.append(dict(t="低評級信用", v=f"HY 一週 {sg(hy)} 基點" if hy is not None else "—", s=sub, st=spread_state(hy),
                      hot=any(x in highs for x in ("HY", "CCC", "BB", "B", "CCC−BB"))))
    ig, lq = r.get("ig_oas_1w"), P.get("LQD_IEF")
    sub = f"息差至 {md(r.get('ig_oas_date') or r.get('hy_oas_date'))}"
    if lag and lq:
        sub += f"；{md(lq['date'])} LQD÷IEF {sg(lq['chg_1'], 2)}%（同日代理）"
    nodes.append(dict(t="投資級", v=f"IG 一週 {sg(ig)} 基點" if ig is not None else "—", s=sub, st=spread_state(ig),
                      hot=any(x in highs for x in ("IG", "BBB"))))
    bz, bk = P.get("BIZD"), P.get("BKLN")
    nodes.append(dict(t="私募信貸", v=f"BIZD 一週 {sg(bz['chg_5'], 1)}%" if bz else "—",
                      s=(f"距一年高位 {sg(bz['off_high'], 1)}%" if bz else "") + (f"；槓桿貸款 BKLN {sg(bk['chg_5'], 1)}%" if bk else ""),
                      st=price_state(bz["chg_5"] if bz else None)))
    sp = (f.get("spread") or [None])[-1]
    srf = (f.get("srf") or {}).get("bn")
    nodes.append(dict(t="資金市場", v=f"SOFR−IORB {sg(sp['bp'])} 基點" if sp else "—",
                      s=(f"{md(sp['date'])}；常備回購 {srf * 10:,.0f} 億美元" if sp and srf is not None else ""),
                      st="—" if srf is None else "有銀行用常備回購" if round(srf * 10) > 0 else "常備回購沒有使用"))  # judged at the shown unit (億美元)
    return nodes


def chain_html(nodes):
    reached = [n["t"] for n in nodes if n["st"] in WORSE]
    calm = [n["t"] for n in nodes if n["st"] not in WORSE and n["st"] != "—"]
    head = (f"本週轉差的有 {'、'.join(reached) or '沒有'}" + (f"；未轉差的有 {'、'.join(calm)}" if calm else "") + "。")
    cells = "".join(
        f'<div class="rb-node{" hot" if n.get("hot") else ""}"><div class="t">{i + 1}. {escape(n["t"])}</div>'
        f'<div class="v">{escape(n["v"])}</div><div class="st{" worse" if n["st"] in WORSE else ""}">{escape(n["st"])}</div>'
        f'<div class="s">{escape(n["s"])}</div></div>' for i, n in enumerate(nodes))
    return ('<h3 class="rb-h2">傳導鏈（本週；由左至右是壓力傳導的次序）</h3>' + p(head) + f'<div class="rb-chain">{cells}</div>'
            + note("紅框＝該組有息差在三年最高；粗體＝本週轉差。只按定義：息差擴闊、價格下跌、有銀行向聯儲用常備回購借錢（以億美元計不為 0）；不設門檻。"))


def credit_line(session):
    """信用 conclusion: the credit verdict, private credit, and the same-day proxies when FRED is a day behind."""
    r, rates, f = first("rates_now") or {}, load("rates"), first("funding") or {}
    P = {x["t"]: x for x in (((first("cross_asset") or {}).get("proxies") or {}).get("rows") or [])}
    R = {x["pair"]: x for x in load("ratio_summary")}
    txt = credit_verdict(r, credit_highs(rates, f)).rstrip("。")
    bz = P.get("BIZD")
    if bz:
        txt += f"；私募信貸代理 BIZD 一週 {sg(bz['chg_5'], 1)}%（距一年高位 {sg(bz['off_high'], 1)}%）"
    if (r.get("hy_oas_date") or "") < session and R.get("HYG_IEF") and P.get("LQD_IEF"):
        txt += (f"；{md(session)} 的息差未公佈，當日價格代理 HYG÷IEF {sg(R['HYG_IEF']['chg1d'], 2)}%、"
                f"LQD÷IEF {sg(P['LQD_IEF']['chg_1'], 2)}%")
    return txt + "。"


def rates_line():
    """利率 conclusion: the week's 10-year and 2-year moves with the curve shape by definition, real yield against
    breakeven, and equity against bond volatility."""
    r = first("rates_now") or {}
    out = []
    if r.get("nominal10_1w") is not None and r.get("nominal2_1w") is not None:
        out.append(f"10 年期一週{rise(r['nominal10_1w'], '基點')}至 {r['nominal10']:.2f}%，2 年期{rise(r['nominal2_1w'], '基點')}至 "
                   f"{r['nominal2']:.2f}%（{curve_shape(r['nominal2_1w'], r['nominal10_1w'])}）")
    if r.get("real10_1w") is not None and r.get("be10_1w") is not None:
        out.append(f"10 年實質孳息{rise(r['real10_1w'], '基點')}、通脹預期{rise(r['be10_1w'], '基點')}")
    V = {x["t"]: x for x in (((first("cross_asset") or {}).get("vol") or {}).get("rows") or [])}
    vx, mv = (V.get("^VIX") or {}).get("chg_1w_pct"), (V.get("^MOVE") or {}).get("chg_1w_pct")
    if vx is not None and mv is not None:
        out.append(f"波動率一週 VIX {sg(vx, 1)}%、MOVE {sg(mv, 1)}%（" + ("股市的變化較大" if abs(vx) > abs(mv) else "債市的變化較大" if abs(mv) > abs(vx) else "變化相同") + "）")
    return "；".join(out) + "。" if out else "利率：沒有數據。"


def funds_line():
    """資金 conclusion: TGA, net liquidity, SOFR against IORB and the Standing Repo Facility."""
    T, _, _ = tga()
    L, f = liquidity(), first("funding") or {}
    out = []
    if T and T.get("chg_1w"):
        out.append(f"TGA {T['latest']['bn'] * 10:,.0f} 億美元（{md(T['latest']['date'])}，一週{more(T['chg_1w']['bn'] * 10, '億')}）")
    if L and L["chg4w"] is not None:
        out.append(f"聯儲淨流動性四週{more(L['chg4w'] * 10, '億美元')}（至 {md(L['last']['date'])}）")
    sp = (f.get("spread") or [None])[-1]
    if sp:
        out.append(f"SOFR 對 IORB {sg(sp['bp'])} 基點（{md(sp['date'])}）" + (f"，常備回購 {f['srf']['bn'] * 10:,.0f} 億美元" if f.get("srf") else ""))
    return "；".join(out) + "。" if out else "資金：沒有數據。"


def now_card(session, today=None):
    """現在要看: data dates, the transmission chain, four conclusions (股市, 信用, 利率, 資金), the market-state line and
    之後要看. Every sentence is built by rule from board data; nothing here is repeated in the cards below."""
    today = today or date.today().isoformat()
    r = first("rates_now") or {}
    T, _, _ = tga()
    L = liquidity()
    lag_days = weekdays_between(session, today) - 1
    parts = []
    if lag_days > 0:
        parts.append(note(f"看板最新收市數據是 {md(session)}，其後已有 {lag_days} 個平日沒有數據；如非假期，即數據未更新。"))
    late = (r.get("hy_oas_date") or "") < session
    parts.append(note(f"數據日期：股價 {md(session)}；孳息 {md(r.get('nominal10_date'))}；信用息差 {md(r.get('hy_oas_date'))}"
                      + ("（FRED 遲一個工作日，之後的日子用同日價格代理）" if late else "")
                      + (f"；TGA {md(T['latest']['date'])}" if T else "") + (f"；淨流動性 {md(L['last']['date'])}（每週）" if L else "") + "。"))
    for label, fn in (("chain", lambda: chain_html(chain_nodes(session))),):
        try:
            parts.append(fn())
        except Exception as e:  # a data file changed shape: keep the other parts, say so
            print(f"now part {label} failed:", repr(e), flush=True)
            parts.append(note("傳導鏈暫時未能生成。"))
    concl = []
    C = first("cross_asset") or {}
    H = C.get("havens") or {}
    week = {x["t"]: x["r"] for x in ((H.get("week") or {}).get("rows") or [])}
    span = f"{md((H.get('week') or {}).get('base_date'))}至{md(H.get('date'))}" if H.get("week") else None
    for label, fn in (("股市", lambda: sell_verdict(load("sectors"), week, span)), ("信用", lambda: credit_line(session)),
                      ("利率", rates_line), ("資金", funds_line)):
        try:
            txt = fn()
        except Exception as e:
            print(f"now conclusion {label} failed:", repr(e), flush=True)
            txt = "暫時未能生成。"
        if txt:
            concl.append(f"<li><b>{label}</b>：{escape(txt)}</li>")
    parts.append('<h3 class="rb-h2" style="margin-top:12px">結論</h3><ul class="rb-concl">' + "".join(concl) + "</ul>")
    try:
        parts.append(note(line_state()))
    except Exception as e:
        print("market state failed:", repr(e), flush=True)
    try:
        rows = watch(session)
    except Exception as e:
        print("watch failed:", repr(e), flush=True)
        rows = []
    if rows:
        parts.append('<h3 class="rb-h2" style="margin-top:12px">之後要看（英國時間）</h3><ul>' + "".join(f"<li>{escape(x)}</li>" for x in rows) + "</ul>")
    return card("rb-summary", f"現在要看（{md(session)}收市）", "".join(parts))


# ---------- sections of the 宏觀 page ----------

def card(cid, title, body):
    return f'<div class="rb-card rb-wide" id="{cid}"><h2 class="rb-h2">{escape(title)}</h2>{body}</div>'


def vol_card():
    """股債波動: the volatility table and its lines, then MOVE's six-month chart."""
    _, M, errs = tga()
    vol = vol_section()
    if M:
        w = M.get("chg_1w")
        mline = (f"MOVE {M['latest']['v']:.1f}（{md(M['latest']['date'])}）" + (f"；一週{rise(w['v'], '', 1)}（對 {md(w['base_date'])}）" if w else "")
                 + f"；在過去一年 {M['n1y']} 個收市讀數（{M['first1y']} 起）中第 {M['pct1y']} 百分位。")
        mtext = ("" if vol else p(mline)) + note("MOVE 是美債期權的隱含波幅（ICE BofA MOVE，Yahoo ^MOVE）；Yahoo 的 ^MOVE 通常比其他收市數據遲一日。"
                                                 + ("今次下載失敗，以上是上次成功的數據。" if any(e.startswith("MOVE") for e in errs) else ""))
    else:
        mtext = note("MOVE：Yahoo 沒有提供 ^MOVE 數據，所以本節不顯示 MOVE。")
    return card("rb-vol", "股債波動", vol + f'<h3 class="rb-h2" style="margin-top:12px">MOVE 指數（最近六個月）</h3>{mtext}'
                '<div class="rb-chart" id="ch-rb-move" style="min-height: 12rem"></div>')


def funds_card():
    """資金: the TGA and Fed net liquidity side by side (merged 2026-11-22, user)."""
    T, _, errs = tga()
    if T:
        w, m = T.get("chg_1w"), T.get("chg_1m")
        line = f"最新 {T['latest']['bn'] * 10:,.0f} 億美元（{md(T['latest']['date'])}）"
        if w:
            line += f"；一週{more(w['bn'] * 10, '億美元')}（對 {md(w['base_date'])}）"
        if m:
            line += f"；一個月{more(m['bn'] * 10, '億美元')}（對 {md(m['base_date'])}）"
        ttext = (p(line + "。") + note("TGA 是財政部在聯儲的現金帳戶；結餘上升時，資金由銀行體系流入這個帳戶。來源：美國財政部每日報表表 I，"
                                       "fiscaldata.treasury.gov；每個營業日的報表在下一個營業日公布。")
                 + (note("今次下載失敗，以上是上次成功下載的數據。") if any(e.startswith("TGA") for e in errs) else ""))
    else:
        ttext = note("沒有 TGA 數據：財政部 fiscaldata 未能下載，或尚未建立 macro_watch.json。")
    L = liquidity()
    if L:
        x = L["last"]
        lline = (f"淨流動性 {x['net_liq'] * 10:,.0f} 億美元（{md(x['date'])}，週三水平）＝聯儲總資產 {x['fed_bs'] * 10:,.0f} − TGA "
                 f"{x['tga'] * 10:,.0f} − 逆回購 {x['rrp'] * 10:,.0f}")
        if L["base"]:
            lline += f"；四週{more(L['chg4w'] * 10, '億美元')}（對 {md(L['base']['date'])}）"
        ltext = p(lline + "。") + note("公式：聯儲總資產（FRED WALCL）− 財政部一般帳戶（FRED WDTGAL）− 隔夜逆回購（FRED RRPONTSYD），"
                                       "全部用同一個週三的水平，所以這裏的 TGA 與左邊每日報表的日期不同。聯儲每週四公布截至週三的數字。")
    else:
        ltext = note("淨流動性：沒有數據。")
    return card("rb-funds", "資金：TGA 及聯儲淨流動性",
                '<div class="rb-grid">'
                f'<div><h3 class="rb-h2">TGA 最新餘額</h3>{ttext}<div class="rb-chart" id="ch-rb-tga" style="min-height: 12rem"></div></div>'
                f'<div><h3 class="rb-h2">聯儲淨流動性</h3>{ltext}<div class="rb-chart" id="ch-rb-liq" style="min-height: 12rem"></div></div></div>')


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


# ---------- 避險資產、股債波動及私募信貸代理（macro/cross_asset.py → cross_asset.json） ----------

def ymd(s):
    return f"{s[:4]} 年 {int(s[5:7])} 月 {int(s[8:10])} 日" if s else "日期未確認"


def num_table(head, rows):
    """A small table: first column text, the rest numbers (right-aligned by the view's rb-num style)."""
    th = "".join(f"<th{' class=rb-left' if i == 0 else ''}>{escape(t)}</th>" for i, t in enumerate(head))
    tr = "".join("<tr>" + "".join(f"<td{' class=rb-left' if i == 0 else ''}>{escape(str(v))}</td>" for i, v in enumerate(r)) + "</tr>"
                 for r in rows)
    return f'<div class="rb-tablebox" style="max-height:none"><table class="rb-table rb-num"><tr>{th}</tr>{tr}</table></div>'


def kept_note(C, key):
    errs = [e for e in (C.get("errors") or []) if e.startswith(key) or e.startswith("download")]
    return note("今次下載失敗，以上是上次成功的數據（日期見上）。") if errs else ""


def corr_band(window=63):
    """About two standard errors of a correlation measured over `window` sessions (2 ÷ √window): a reading inside ±band
    cannot be told apart from zero. A statement of measurement precision, not a signal."""
    return round(2 / window ** 0.5, 2)


def corr_word(r, b):
    if r is None:
        return "—"
    return "同向" if r >= b else "反向" if r <= -b else "沒有可靠關係"


def haven_lines(H):
    """One summary sentence: which assets move clearly with the Nasdaq-100 and which clearly against it (outside the
    ±band, about two standard errors), and which, on SMH's worst days, rose on average and on most of those days, or
    fell on average and on most of them. Signs, the sampling band and a simple majority only; no other cut-off."""
    b = corr_band(H.get("window") or 63)
    rows = H.get("rows") or []
    names = lambda k: "、".join(r["name"] for r in rows if corr_word(r["corr"], b) == k)
    w, a, n = names("同向"), names("反向"), names("沒有可靠關係")
    parts = [f"明顯跟科技股同向的有 {w}" if w else "沒有資產明顯跟科技股同向",
             f"明顯反向的有 {a}" if a else "沒有資產明顯反向"]
    text = f"避險資產：最近 63 個交易日（至 {md(H['date'])}），" + "，".join(parts) + ("，其餘沒有可靠關係" if n else "")
    D = H.get("down") or {}
    drs = [r for r in D.get("rows") or [] if r.get("avg_pct") is not None and r["t"] != "SPY"]
    if drs:
        up = "、".join(r["name"] for r in sorted(drs, key=lambda r: -r["avg_pct"]) if r["avg_pct"] > 0 and r["up_share"] > 50)
        dn = "、".join(r["name"] for r in sorted(drs, key=lambda r: r["avg_pct"]) if r["avg_pct"] < 0 and r["up_share"] < 50)
        text += (f"；在 SMH 最差的 {D['n']} 日，平均上升而且多數日子上升的有 {up or '沒有'}，"
                 f"平均下跌而且多數日子下跌的有 {dn or '沒有'}")
    return [text + "。"]


HAVEN_CHARTS = (("黃金、美元、日圓", ("GLD", "UUP", "FXY"), "ch-rb-haven1"),
                ("短期及中期美債、必需消費", ("SHY", "IEF", "XLP"), "ch-rb-haven2"))  # macro_view.RB_JS draws them in this order


def sell_verdict(sectors, week, span=None):
    """結論 of the AI sell-off card, by definition from signs only: within equities, how many of the 11 sectors fell over
    the week (all = 全面下跌, more than half = 大部分下跌, otherwise 下跌集中在部分板塊) and whether SMH fell more than every
    sector (= 重心在 AI); across assets, whether Treasuries rose while the S&P fell (= not a sell-everything move, money
    went to Treasuries) or fell with it (= stocks and bonds sold together)."""
    S = {x["ticker"]: x for x in sectors}
    sec = [x for x in sectors if x.get("group") == "sector" and x["ticker"] != "GDX" and x.get("r1w") is not None]
    if not sec:
        return None
    down = [x for x in sec if x["r1w"] < 0]
    eq = "全面下跌" if len(down) == len(sec) else "大部分下跌" if len(down) > len(sec) / 2 else "下跌集中在部分板塊"
    rsp = (S.get("RSP") or {}).get("r1w")
    txt = (f"{f'（{span}）' if span else ''}在股票之內，{eq}（{len(sec)} 個板塊中 {len(down)} 個一週下跌"
           + (f"，等權標普 {sg(rsp, 1)}%" if rsp is not None else "") + "）")
    smh, worst = (S.get("SMH") or {}).get("r1w"), min(sec, key=lambda x: x["r1w"])
    if smh is not None and smh < worst["r1w"]:
        txt += f"，重心在 AI（SMH {sg(smh, 1)}%，跌幅大過所有板塊）"
    else:
        txt += f"，跌得最多的是{worst['name']}（{sg(worst['r1w'], 1)}%）"
    tlt, ief, spy = week.get("TLT"), week.get("IEF"), week.get("SPY")
    if None not in (tlt, ief, spy) and spy < 0:
        pair = f"TLT {sg(tlt, 1)}%、IEF {sg(ief, 1)}%"
        if tlt > 0 and ief > 0:
            txt += f"；放到所有資產來看，國債上升（{pair}），不是甚麼都賣，資金轉向國債"
        elif tlt < 0 and ief < 0:
            txt += f"；放到所有資產來看，國債也下跌（{pair}），股債同時被賣"
        else:
            txt += f"；國債方向不一（{pair}）"
    return txt + "。"


def ai_sell_card(session):
    """AI 拋售：半導體與避險資產 (the AI card and the haven card merged on 2026-11-22, user): the 結論 line, SMH against the
    S&P 500, then how the usual havens moved with the AI trade."""
    C = first("cross_asset") or {}
    H = C.get("havens") or {}
    sectors = load("sectors")
    S = {x["ticker"]: x for x in sectors}
    R = {x["pair"]: x for x in load("ratio_summary")}
    smh, mem, rr = S.get("SMH") or {}, S.get("AI_MEM") or {}, R.get("SMH_SPY") or {}
    lines = []
    if smh.get("rel1m") is not None and rr.get("vs_50d") is not None:
        lines.append(f"SMH 對標普（比率 SMH ÷ SPY 的相對變化）：一個月 {sg(smh['rel1m'], 1)}、三個月 {sg(smh.get('rel3m') or 0, 1)} 個百分點；"
                     f"比率{'高於' if rr['vs_50d'] > 0 else '低於'} 50 日均線 {abs(rr['vs_50d']):.1f}%（{md(session)}）。")
    if mem.get("rel1m") is not None:
        lines.append(f"記憶體籃子（MU、WDC、STX、SNDK，等權）對標普：一個月 {sg(mem['rel1m'], 1)}、三個月 {sg(mem.get('rel3m') or 0, 1)} 個百分點（{md(session)}）。")
    top = ('<h3 class="rb-h2">半導體相對大市（SMH ÷ SPY，一年前＝100，最近六個月）</h3>'
           + '<div class="rb-chart" id="ch-rb-smh" style="min-height: 11rem"></div>' + "".join(p(x) for x in lines)
           + note("這是股價相對標普 500 的強弱，不是資金流量數據。"))
    if not H:
        return card("rb-havens", "AI 拋售：半導體與避險資產", top + note("避險資產：沒有數據（Yahoo 未能下載，或尚未建立 cross_asset.json）。"))
    return card("rb-havens", "AI 拋售：半導體與避險資產", top + '<h3 class="rb-h2" style="margin-top:16px">避險資產</h3>' + haven_body(C, H))


def haven_body(C, H):
    b = corr_band(H.get("window") or 63)
    week = {x["t"]: x["r"] for x in ((H.get("week") or {}).get("rows") or [])}
    wdate = (H.get("week") or {}).get("base_date")
    e6 = next((r.get("corr_6m_date") for r in H["rows"] if r.get("corr_6m_date")), None)
    med_from = next((r.get("med_from") for r in H["rows"] if r.get("med_from")), None)
    D = H.get("down") or {}
    dmap = {r["t"]: r for r in D.get("rows") or []}
    bar = ('<h3 class="rb-h2" style="margin-top:12px">現時與納指 100 的相關（最近 63 個交易日）</h3>'
           '<div class="rb-legend"><span style="--sw:var(--series-2)">同向（相關為正）</span><span style="--sw:var(--series-1)">反向（相關為負）</span>'
           '<span style="--sw:var(--color-fg)">五年中位（短直線）</span></div>'
           + note(f"+1 是與納指同步升跌，−1 是完全相反，0 是沒有關係。灰色範圍是 ±{b:.2f}：條在範圍內，表示 63 日的讀數與零分不開，即沒有可靠關係。")
           + '<div class="rb-chart" id="ch-rb-havenbar" style="min-height: 15rem"></div>')
    table = num_table(["資產", "63 日相關", "與納指的關係", f"約六個月前（{md(e6)}）" if e6 else "約六個月前", "五年中位",
                       f"一週回報（對 {md(wdate)}）" if wdate else "一週回報", "SMH 最差日：平均", "上升日比例"],
                      [[r["name"], fmt_chg(r["corr"], 2), corr_word(r["corr"], b), fmt_chg(r["corr_6m"], 2), fmt_chg(r["corr_med5y"], 2),
                        f"{sg(week[r['t']], 2)}%" if week.get(r["t"]) is not None else "—",
                        f"{sg(dmap[r['t']]['avg_pct'], 2)}%" if r["t"] in dmap else "—", f"{dmap[r['t']]['up_share']}%" if r["t"] in dmap else "—"]
                       for r in H["rows"]])
    charts = ""
    if H.get("roll"):
        names = {r["t"]: r["name"] for r in H["rows"]}
        panels = []
        for title, ts, cid in HAVEN_CHARTS:
            lg = "".join(f'<span style="--sw:var(--series-{i + 1})">{escape(names.get(t, t))}</span>' for i, t in enumerate(ts))
            panels.append(f'<div><h3 class="rb-h2">{escape(title)}</h3><div class="rb-legend">{lg}</div>'
                          f'<div class="rb-chart" id="{cid}" style="min-height: 12rem"></div></div>')
        charts = ('<h3 class="rb-h2" style="margin-top:12px">最近一年的走勢（63 日相關；0 以上同向，以下反向）</h3>'
                  '<div class="rb-grid">' + "".join(panels) + "</div>")
    down_head = ""
    if D.get("rows"):
        down_head = (f"SMH 最差日：{ymd(D['from'])}至{ymd(D['to'])}的 {D['sessions']} 個交易日中最差的十分之一（{D['n']} 日），"
                     f"最近三日是 {'、'.join(md(x) for x in D.get('latest_days') or [])}。")
    body = ("".join(p(x) for x in haven_lines(H)) + bar
            + '<h3 class="rb-h2" style="margin-top:12px">數字</h3>' + table + charts
            + note(down_head + "相關係數用每日回報，每個讀數用 63 個交易日（約三個月）；約六個月前即 126 個交易日前的讀數；五年中位是"
                   + (f"{ymd(med_from)}起" if med_from else "")
                   + f"每日滾動讀數的中位數。±{b:.2f} 是約兩個標準誤（2 除以 63 的平方根），在內的讀數與零分不開，所以寫「沒有可靠關係」；這是量度的精確度，不是訊號。"
                   "SMH 最差日按每日回報選出，不設自訂跌幅。資產用 ETF 價格（已按派息及拆股調整）：美元 UUP 是美元對一籃子貨幣，"
                   "日圓 FXY 是日圓對美元。這裏只描述各資產與科技股同向或反向的程度及過去的表現，關係會隨利率環境改變，不是避險建議。"
                   "來源：Yahoo 每日收市。")
            + kept_note(C, "havens"))
    return body


def term_structure_line(rows):
    """VIX9D, VIX and VIX3M on one date: short above long = inverted, by definition."""
    by = {r["t"]: r for r in rows}
    a, b, c = by.get("^VIX9D"), by.get("^VIX"), by.get("^VIX3M")
    if not (a and b and c) or len({a["date"], b["date"], c["date"]}) != 1:
        return None
    vals = f"VIX9D {a['v']:.2f}、VIX {b['v']:.2f}、VIX3M {c['v']:.2f}（{md(b['date'])}）"
    if a["v"] > b["v"] > c["v"]:
        return vals + "：短期高於長期，即期限結構倒掛，期權市場為未來幾週的波動付較高價格。"
    if a["v"] < b["v"] < c["v"]:
        return vals + "：短期低於長期，即正常的向上斜率。"
    return vals + "：三個期限高低不一。"


def vol_section():
    """The volatility table and its three lines, for the top of the 波動率及聯儲淨流動性 card; empty without data."""
    C = first("cross_asset") or {}
    V = (C.get("vol") or {}).get("rows") or []
    if not V:
        return ""
    ranked = sorted((r for r in V if r.get("chg_1w_pct") is not None), key=lambda r: -r["chg_1w_pct"])
    parts = [r["name"].split("（")[0] + " " + sg(r["chg_1w_pct"], 1) + "%" for r in ranked]
    lines = ["一週變化（按百分比，由大至小）：" + "、".join(parts) + "。"] if parts else []
    by = {r["t"]: r for r in V}
    if by.get("^VIX", {}).get("chg_1w_pct") is not None and by.get("^MOVE", {}).get("chg_1w_pct") is not None:
        x, y = by["^VIX"]["chg_1w_pct"], by["^MOVE"]["chg_1w_pct"]
        lines.append(f"股市波動（VIX）一週 {sg(x, 1)}%，債市波動（MOVE）{sg(y, 1)}%："
                     + ("兩者都上升，" if x > 0 and y > 0 else "兩者都下降，" if x < 0 and y < 0 else "方向相反，")
                     + ("股市的變化較大。" if abs(x) > abs(y) else "債市的變化較大。" if abs(y) > abs(x) else "變化相同。"))
    ts = term_structure_line(V)
    if ts:
        lines.append(ts)
    table = num_table(["指數", "最新", "日期", "一週變化", "一週變化（%）", "一年百分位"],
                      [[r["name"], f"{r['v']:.2f}", md(r["date"]), fmt_chg(r.get("chg_1w"), 2),
                        f"{sg(r['chg_1w_pct'], 1)}%" if r.get("chg_1w_pct") is not None else "—", f"第 {r['pct1y']}"] for r in V])
    body = ("".join(p(x) for x in lines) + table
            + note("全部是期權的隱含波幅：VIX、VIX9D、VIX3M 是標普 500 期權對 30 日、9 日及 3 個月的定價，VXN 是納指 100，"
                   "MOVE 是美債期權（ICE BofA），GVZ 是黃金 ETF 期權。一週變化對上一個至少早七日的讀數；一年百分位是最新讀數在過去一年"
                   "讀數中的位置（等於或低於它的比例）。Yahoo 的 ^MOVE 通常遲一日，所以日期可以不同。倒掛、正常斜率只按定義，不是訊號。"
                   "來源：Yahoo（Cboe 及 ICE 指數）。")
            + kept_note(C, "vol"))
    return '<h3 class="rb-h2">股市及債市波動</h3>' + body



# ---------- headings of the rotation and breadth cards (the 市寬與輪動摘要 card was removed on 2026-11-22: it repeated the charts) ----------

QUAD = (("leading", "領先"), ("weakening", "轉弱"), ("lagging", "落後"), ("improving", "改善"))
QNAME = dict(QUAD)


def rotation_week(sectors, tails):
    """Weekly graph against the S&P 500: the sectors in each quadrant, and those that changed quadrant since last week."""
    names = {x["ticker"] for x in sectors}
    weeks = sorted({r["week"] for r in tails if r["ticker"] in names})
    week, prev = (weeks[-1], weeks[-2]) if len(weeks) > 1 else (weeks[-1] if weeks else None, None)
    by = {k: [x["name"] for x in sectors if x.get("quadrant") == k] for k, _ in QUAD}
    changes = [(x["name"], x["quadrant_1w"], x["quadrant"]) for x in sectors
               if x.get("quadrant") and x.get("quadrant_1w") and x["quadrant"] != x["quadrant_1w"]]
    text = f"截至 {md(week)}（週線，對標普 500）：" + "；".join(f"{name} {'、'.join(by[k]) or '沒有'}" for k, name in QUAD) + "。"
    moved = "、".join(f"{n}（{QNAME[a]}→{QNAME[b]}）" for n, a, b in changes)
    return text + (f"與上週比較，轉換象限的有 {moved}。" if changes else "與上週比較，沒有板塊轉換象限。")


def rotation_head(session):
    try:
        line = rotation_week([x for x in load("sectors") if x.get("group") == "sector"], load("rrg_tails"))
    except (OSError, KeyError, TypeError, ValueError, IndexError):
        line = "輪動讀數暫時未能生成。"
    return '<h2 class="rb-h2">板塊輪動</h2>' + p(line)


def breadth_head():
    b = first("breadth_now") or {}
    line = ""
    if b.get("ad_1w") is not None and b.get("mcclellan") is not None:
        line = (f"{md(b.get('asof'))}：升跌線一週{rise(b['ad_1w'])}、一個月{rise(b.get('ad_1m'))}；麥克連振盪指標 {sg(b['mcclellan'], 1)}"
                f"（一週前 {sg(b.get('mcclellan_1w') or 0, 1)}，一個月前 {sg(b.get('mcclellan_1m') or 0, 1)}）。")
    return ('<h2 class="rb-h2">市寬</h2>' + (p(line) if line else "")
            + note("升跌線是每日上升減下跌股數的累計（附 SPY 比較方向）；麥克連振盪指標 0 以上＝近期上升股數佔優，0 以下＝下跌股數佔優。"))


# ---------- credit ----------

def fmt_chg(x, d=0):
    return "—" if x is None else sg(x, d)


def credit_verdict(m_now, highs):
    """One sentence: whether credit worsened over the week (all four spreads wider = 轉差, all narrower = 好轉, otherwise
    mixed), which series stand at their three-year high, and whether HY widened more than IG. Signs only."""
    tiers = (("HY", "hy"), ("IG", "ig"), ("BB", "bb"), ("CCC", "ccc"))
    chg = [(n, m_now.get(f"{k}_oas_1w")) for n, k in tiers]
    wide = [n for n, v in chg if v is not None and v > 0]
    narrow = [n for n, v in chg if v is not None and v < 0]
    head = ("信用轉差，四個息差一週全部擴闊" if len(wide) == len(tiers) else "信用好轉，四個息差一週全部收窄" if len(narrow) == len(tiers)
            else f"信用好壞參半，一週擴闊的有 {'、'.join(wide) or '沒有'}，收窄的有 {'、'.join(narrow) or '沒有'}")
    nums = "、".join(f"{n} {sg(v)}" for n, v in chg if v is not None)
    txt = f"{head}（{nums} 基點，至 {md(m_now.get('hy_oas_date'))}）"
    if highs:
        txt += f"；{'、'.join(highs)} 在三年最高"
    hy, ig = m_now.get("hy_oas_1w"), m_now.get("ig_oas_1w")
    if hy is not None and ig is not None and hy > 0:
        txt += "；HY 擴闊多過 IG，壓力仍集中在低評級" if hy > ig else "；IG 擴闊不比 HY 少，壓力已傳到投資級"
    return txt + "。"


def credit_table():
    """The full credit table, most telling rows first: HY, IG, CCC, BB, B, BBB, CCC−BB; then the price proxies, the
    funding market and the AI borrowers. A row whose latest reading is the highest of its three years (100th percentile)
    is shown in bold red; that is a record within the window, not a chosen cut-off."""
    m_now, r, f = load("rates_now")[0], load("rates"), load("funding")[0]
    R = {x["pair"]: x for x in load("ratio_summary")}
    series = lambda k: rate_series(r, k)
    pct = pct3y
    lad = {x["id"]: x for x in f["ladder"]}
    MEAN = {"hy": "高收益債總體", "ig": "投資級總體；擴闊代表問題不只在低質", "bb": "高收益債最好一級；開始擴闊代表壓力向上傳",
            "ccc": "最弱一級，通常最早反應"}
    rows = []

    def row(*c, hot=False):
        rows.append(f'<tr{" class=rb-hot" if hot else ""}>' + "".join(
            f'<td{" class=rb-left" if i in (0, 8) else ""}>{escape(str(v))}</td>' for i, v in enumerate(c)) + "</tr>")

    group = lambda t: rows.append(f'<tr class="rb-sep"><td colspan="9">{escape(t)}</td></tr>')
    highs = []

    def spread(k, name):
        s = series(f"{k}_oas")
        pc = pct(s)
        if pc == 100:
            highs.append(name)
        row(name, f"{s[-1]:,.0f}", fmt_chg(m_now[f"{k}_oas_1d"]), fmt_chg(m_now[f"{k}_oas_1w"]), fmt_chg(m_now[f"{k}_oas_1m"]),
            fmt_chg(m_now[f"{k}_oas_3m"]), f"第 {pc:.0f}", md(m_now["hy_date"]), MEAN[k], hot=pc == 100)

    def ladder(k, name, nt):
        x = lad[k]
        if x["pct3y"] == 100:
            highs.append(name)
        row(name, f"{x['bp']:,}", "—", "—", fmt_chg(x["chg_bp"]), "—", f"第 {x['pct3y']}", md(x["date"]), nt, hot=x["pct3y"] == 100)

    group("息差（基點，按重要性排列）")
    spread("hy", "HY")
    spread("ig", "IG")
    spread("ccc", "CCC")
    spread("bb", "BB")
    ladder("b", "B", "高收益債的中間一級：評級低於 BB、高於 CCC")
    ladder("bbb", "BBB", "投資級最低一級；擴闊代表跌出投資級的憂慮")
    cb = [a - b for a, b in zip(series("ccc_oas"), series("bb_oas"))]
    cbp = pct(cb)
    if cbp == 100:
        highs.append("CCC−BB")
    row("CCC−BB", f"{cb[-1]:,.0f}", fmt_chg(cb[-1] - cb[-2]), fmt_chg(cb[-1] - cb[-6]), fmt_chg(cb[-1] - cb[-22]), fmt_chg(cb[-1] - cb[-64]),
        f"第 {cbp:.0f}", md(m_now["hy_date"]), "差距擴闊＝壓力集中最弱一級；收窄可以是好轉，也可以是 BB 追上來", hot=cbp == 100)
    group("價格代理（當日已有，不必等息差公佈）")
    h = R["HYG_IEF"]
    row("HYG／IEF（%）", f"{sg(h['vs_50d'], 1)} 對 50 日線", sg(h["chg1d"], 2), sg(h["chg5d"], 2), sg(h["chg20d"], 2), sg(h["chg60d"], 2), "—",
        md(load("refresh_meta")[0]["session"]), "息差遲一日公布，這是當日的價格代理；低於 50 日線是惡化條件之一")
    PROXY_MEAN = {"BIZD": "上市 BDC（借錢給私人公司的貸款機構）ETF 的價格；私募信貸本身少有報價，這是價格代理，不是息差",
                  "BKLN": "槓桿貸款（浮息銀團貸款）ETF 的價格；價格代理，不是息差"}
    PROXY_MEAN["LQD_IEF"] = "投資級公司債 ETF 對中期國債；IG 息差遲一日公布，這是同日的價格代理"
    for x in ((first("cross_asset") or {}).get("proxies") or {}).get("rows", []):
        row(f"{x['name']}（%）", f"{sg(x['off_high'], 1)} 對一年高位" if "off_high" in x else f"{sg(x['vs_50d'], 1)} 對 50 日線", sg(x["chg_1"], 2), sg(x["chg_5"], 2), sg(x["chg_21"], 2),
            sg(x["chg_63"], 2), "—", md(x["date"]), PROXY_MEAN.get(x["t"], "價格代理，不是息差"))
    ys = series("ig_yield")
    row("IG 孳息（%）", f"{ys[-1] / 100:.2f}", fmt_chg(m_now["ig_yield_1d"]), fmt_chg(m_now["ig_yield_1w"]), fmt_chg(m_now["ig_yield_1m"]), fmt_chg(m_now["ig_yield_3m"]),
        f"第 {pct(ys):.0f}", md(m_now["hy_date"]), "企業借貸的實際成本（變化以基點計）")
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
    return ('<div class="rb-card rb-wide" id="rb-credit"><h2 class="rb-h2">信用總表</h2>' + note(
        "結論在頁頂「現在要看」。" + 
        "日、週、月、3 個月是變化；「—」代表這個系列沒有該期數據。紅色粗體＝最新讀數是三年內最高（第 100 百分位）。")
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

def brent_price_line(rows, bz):
    """The Brent price and its week change on one contract. The front contract of the curve (rows, from oil.json) is
    compared with the same contract a week earlier, so a roll cannot pass for a price move. Yahoo's continuous BZ=F (bz,
    from brent.json) switches to the next contract a few days before expiry; when its close on the same day equals a
    later contract, the line says so. Without the curve, the continuous series is used and named as such."""
    f = rows[0] if rows and rows[0].get("close") is not None else None
    if f:
        txt = f"Brent 近月（{f['month']} 合約）{f['close']:.2f} 美元（{md(f['date'])}）"
        if f.get("chg_1w") is not None:
            txt += f"，對 {md(f.get('week_date'))}同一合約{rise(f['chg_1w'], '美元', 2)}"
        cont = next((r for r in reversed(bz) if r["date"] == f["date"]), None)
        later = next((r for r in rows[1:] if cont and r.get("close") is not None and r.get("date") == f["date"]
                      and abs(r["close"] - cont["close"]) < 0.005), None) if cont else None
        if later and abs(f["close"] - cont["close"]) >= 0.005:
            txt += (f"；Yahoo 連續近月（BZ=F）當日 {cont['close']:.2f} 美元，已轉到 {later['month']} 合約，"
                    "所以一週變化用同一合約計，不用連續序列")
        return txt
    if bz:
        last = bz[-1]
        wk = [r for r in bz if r["date"] <= (date.fromisoformat(last["date"]) - timedelta(days=7)).isoformat()]
        return (f"Brent 連續近月（Yahoo BZ=F）{last['close']:.2f} 美元（{md(last['date'])}）"
                + (f"，對 {md(wk[-1]['date'])}{rise(last['close'] - wk[-1]['close'], '美元', 2)}（沒有曲線數據，轉倉週的變化會包括換合約）" if wk else ""))
    return None


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
    curve = oil.get("curve") or {}
    rows, sp = curve.get("rows") or [], curve.get("spreads") or {}
    line = brent_price_line(rows, [r for r in (load("brent") or []) if r.get("close") is not None])
    if line:
        priced.append(line)
    else:
        gaps.append("Brent 近月價格")
    if sp.get("wti_front") is not None:
        priced.append(f"WTI 近月 {sp['wti_front']:.2f} 美元（{md(sp.get('wti_date'))}）")
    if rows and sp.get("m1_dec_next") is not None:
        f = rows[0]
        dn = next((r for r in rows if r["month"] == f"{int(f['date'][:4]) + 1}-12"), None)
        shape = "近月高於遠月（逆價差）" if sp["m1_dec_next"] > 0 else "近月低於遠月（正價差）" if sp["m1_dec_next"] < 0 else "近月與遠月持平"
        txt = (f"期貨曲線{shape}：近月（{f['month']}）減明年 12 月合約 {sg(sp['m1_dec_next'], 2)} 美元，"
               f"近月減次月 {sg(sp.get('m1_m2') or 0, 2)} 美元")
        if dn and f.get("chg_1w") is not None and dn.get("chg_1w") is not None:
            txt += f"；一週內明年 12 月{rise(dn['chg_1w'], '美元', 2)}，與近月的差價{rise(f['chg_1w'] - dn['chg_1w'], '美元', 2)}（對 {md(f.get('week_date'))}）"
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
