"""Cross-asset readings for the local 宏觀 view (user, 2026-11-22): how the usual havens have moved with the AI trade,
equity and bond volatility side by side, and listed price proxies for private credit and leveraged loans.

Everything comes from Yahoo daily closes (auto-adjusted for dividends and splits), downloaded here with six years of
history so that five-year medians exist; the board's main download keeps two years. Data only: no threshold, signal,
score or advice. Each block keeps its own observation dates. When the download or a block fails, the previous file's
block stays with its old dates and the failure is listed in "errors"; nothing is carried forward under a new date.

Blocks of cross_asset.json (one row):
  havens   63-session correlation of daily returns with QQQ for each asset (latest, 126 sessions earlier and the median
           of the rolling readings over five years), each asset's return over the week, and its average return and
           share of up days on the worst tenth of SMH's daily returns over the last 252 sessions.
  vol      VIX, VIX9D, VIX3M, VXN, MOVE and GVZ: latest, change over a week in points and per cent, and the percentile
           of the latest within the last year of readings (share at or below it).
  proxies  BIZD (listed business development companies, which lend to private companies) and BKLN (leveraged loans):
           latest close, changes over 1, 5, 21 and 63 sessions in per cent, and the distance from the 252-session high;
           LQD ÷ IEF (investment-grade bonds against 7–10-year Treasuries): the same changes and the distance from its
           50-session average, a same-day stand-in for the IG spread that FRED publishes a business day late.
"""
import json
from datetime import date, timedelta

import pandas as pd

HAVENS = [("GLD", "黃金（GLD）"), ("UUP", "美元（UUP）"), ("FXY", "日圓（FXY）"), ("SHY", "1–3 年美債（SHY）"),
          ("IEF", "7–10 年美債（IEF）"), ("TLT", "20 年以上美債（TLT）"), ("XLP", "必需消費（XLP）"), ("XLU", "公用事業（XLU）")]
BENCH, DOWN, MARKET = "QQQ", "SMH", "SPY"
WINDOW = 63            # sessions in each correlation (about three months)
EARLIER = 126          # the comparison reading, about six months earlier
MEDIAN_YEARS = 5       # the rolling correlations whose median is shown
DOWN_SESSIONS = 252    # the span in which SMH's worst days are taken (about one year)
DOWN_SHARE = 0.10      # the worst tenth of those sessions
CHART_SESSIONS = 252   # the rolling correlations kept for the card's charts (about one year)
VOL = [("^VIX", "VIX（標普 500，30 日）"), ("^VIX9D", "VIX9D（標普 500，9 日）"), ("^VIX3M", "VIX3M（標普 500，3 個月）"),
       ("^VXN", "VXN（納指 100）"), ("^MOVE", "MOVE（美債）"), ("^GVZ", "GVZ（黃金）")]
PROXIES = [("BIZD", "私募信貸代理 BIZD"), ("BKLN", "槓桿貸款 BKLN")]
# same-day price ratios that stand in for spreads FRED publishes a business day late (HYG ÷ IEF is in the main build)
RATIO_PROXIES = [("LQD_IEF", "LQD÷IEF（投資級同日代理）", "LQD", "IEF")]
TICKERS = sorted({BENCH, DOWN, MARKET, *(t for t, _ in HAVENS), *(t for t, _ in VOL), *(t for t, _ in PROXIES),
                  *(x for _, _, a, b in RATIO_PROXIES for x in (a, b))})
SOURCE = "https://finance.yahoo.com/"


def download(tickers=TICKERS):
    """Daily closes as a DataFrame (dates as rows, tickers as columns)."""
    import yfinance as yf
    df = yf.download(sorted(tickers), period="6y", interval="1d", auto_adjust=True, progress=False, threads=True,
                     group_by="column")
    return df["Close"]


def iso(ts):
    return pd.Timestamp(ts).strftime("%Y-%m-%d")


def r2(x, d=2):
    return None if x is None or x != x else round(float(x), d)


def week_base(index, last):
    """The last session on or before seven calendar days before `last`."""
    xs = [d for d in index if d <= last - pd.Timedelta(days=7)]
    return xs[-1] if xs else None


def haven_block(close):
    cols = [c for c in [BENCH, DOWN, MARKET] + [t for t, _ in HAVENS] if c in close]
    if BENCH not in cols or DOWN not in cols:
        return None
    px = close[cols].dropna()
    ret = px.pct_change().dropna()
    last = ret.index[-1]
    rows, chart = [], {}
    for t, name in HAVENS:
        if t not in ret:
            continue
        roll = ret[t].rolling(WINDOW).corr(ret[BENCH]).dropna()
        if roll.empty:
            continue
        chart[t] = roll.iloc[-CHART_SESSIONS:]
        five = roll[roll.index > last - pd.Timedelta(days=round(365.25 * MEDIAN_YEARS))]
        earlier = roll.iloc[-1 - EARLIER] if len(roll) > EARLIER else None
        rows.append({"t": t, "name": name, "corr": r2(roll.iloc[-1]),
                     "corr_6m": r2(earlier), "corr_6m_date": iso(roll.index[-1 - EARLIER]) if earlier is not None else None,
                     "corr_med5y": r2(five.median()), "med_from": iso(five.index[0]), "med_n": int(len(five))})
    base = week_base(px.index, px.index[-1])
    week = None
    if base is not None:
        week = {"base_date": iso(base), "rows": [{"t": t, "r": r2((px[t].iloc[-1] / px.loc[base, t] - 1) * 100)}
                                                 for t in cols]}
    span = ret.iloc[-DOWN_SESSIONS:]
    k = max(1, round(len(span) * DOWN_SHARE))
    worst = span[DOWN].nsmallest(k).index
    names = dict(HAVENS) | {MARKET: "標普 500（SPY）"}
    down = {"ref": DOWN, "from": iso(span.index[0]), "to": iso(span.index[-1]), "sessions": int(len(span)), "n": int(k),
            "cut_pct": r2(span.loc[worst, DOWN].max() * 100), "avg_ref_pct": r2(span.loc[worst, DOWN].mean() * 100),
            "latest_days": [iso(d) for d in sorted(worst)[-3:]],
            "rows": [{"t": t, "name": names[t], "avg_pct": r2(span.loc[worst, t].mean() * 100),
                      "up_share": round(float((span.loc[worst, t] > 0).mean()) * 100)}
                     for t in [MARKET] + [t for t, _ in HAVENS] if t in span]}
    roll = None
    if chart:
        frame = pd.DataFrame(chart).dropna()
        roll = {"dates": [iso(d) for d in frame.index], **{t: [round(float(v), 3) for v in frame[t]] for t in frame}}
    return {"date": iso(last), "bench": BENCH, "window": WINDOW, "earlier": EARLIER, "rows": rows, "week": week,
            "down": down, "roll": roll, "source": SOURCE}


def vol_block(close):
    rows = []
    for t, name in VOL:
        if t not in close:
            continue
        s = close[t].dropna()
        if s.empty:
            continue
        d, v = s.index[-1], float(s.iloc[-1])
        year = s[s.index > d - pd.Timedelta(days=365)]
        base = week_base(s.index, d)
        b = float(s.loc[base]) if base is not None else None
        rows.append({"t": t, "name": name, "v": r2(v), "date": iso(d), "base_date": iso(base) if base is not None else None,
                     "chg_1w": r2(v - b) if b is not None else None, "chg_1w_pct": r2((v / b - 1) * 100, 1) if b else None,
                     "pct1y": round(float((year <= v).mean()) * 100), "n1y": int(len(year))})
    return {"rows": rows, "source": SOURCE} if rows else None


def proxy_block(close):
    rows = []
    for t, name in PROXIES:
        if t not in close:
            continue
        s = close[t].dropna()
        if len(s) < 64:
            continue
        v = float(s.iloc[-1])
        chg = {f"chg_{n}": r2((v / float(s.iloc[-1 - n]) - 1) * 100) for n in (1, 5, 21, 63)}
        hi = s.iloc[-252:]
        rows.append({"t": t, "name": name, "v": r2(v), "date": iso(s.index[-1]), **chg,
                     "off_high": r2((v / float(hi.max()) - 1) * 100), "high_date": iso(hi.idxmax())})
    for t, name, a, b in RATIO_PROXIES:
        if a not in close or b not in close:
            continue
        s = (close[a] / close[b]).dropna()
        if len(s) < 64:
            continue
        v = float(s.iloc[-1])
        chg = {f"chg_{n}": r2((v / float(s.iloc[-1 - n]) - 1) * 100) for n in (1, 5, 21, 63)}
        rows.append({"t": t, "name": name, "v": round(v, 4), "date": iso(s.index[-1]), **chg,
                     "vs_50d": r2((v / float(s.iloc[-50:].mean()) - 1) * 100)})
    return {"rows": rows, "source": SOURCE} if rows else None


def build_cross_asset(out_dir, cutoff=None, fetch=download):
    """Write cross_asset.json into out_dir. A block that fails keeps the previous file's block with its own dates."""
    path = out_dir / "cross_asset.json"
    try:
        prev = json.loads(path.read_text())[0]
    except (OSError, ValueError, IndexError):
        prev = {}
    row, errors = {"built": date.today().isoformat()}, []
    try:
        close = fetch(TICKERS)
        close.index = pd.to_datetime(close.index).tz_localize(None)
        if cutoff:
            close = close.loc[:cutoff]
    except Exception as e:
        close = None
        errors.append(f"download: {type(e).__name__}")
    for key, fn in (("havens", haven_block), ("vol", vol_block), ("proxies", proxy_block)):
        try:
            if close is None:
                raise ValueError("no prices")
            row[key] = fn(close)
            if not row[key]:
                raise ValueError("empty")
        except Exception as e:  # keep the previous block with its own dates
            if close is not None:
                errors.append(f"{key}: {type(e).__name__}")
            row[key] = prev.get(key)
    row["errors"] = errors
    path.write_text(json.dumps([row], ensure_ascii=False, separators=(",", ":")))
    print(f"  cross_asset.json  havens {(row.get('havens') or {}).get('date')}  vol {len((row.get('vol') or {}).get('rows', []))}"
          f"  proxies {len((row.get('proxies') or {}).get('rows', []))}" + (f"  errors {errors}" if errors else ""))
    return row


if __name__ == "__main__":
    from pathlib import Path
    from market_clock import completed_session
    build_cross_asset(Path(__file__).resolve().parent / "data", completed_session())
