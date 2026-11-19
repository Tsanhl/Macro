"""Oil tracking for the local board's 油價 page (user request 2026-10-23; local board only, never published).

Automated blocks, each kept from the previous oil.json with its own dates when its source fails (a source outage never
stalls the board):
  curve      NYMEX Brent financial futures by contract (Yahoo BZ<month><yy>.NYM; they settle on ICE Brent) and the WTI
             front, with a stored daily history of the curve (each contract's daily close, backfilled from Yahoo's
             three-month history and kept for 400 days) for the latest, week-earlier and month-earlier curves, and the
             four spreads now and a week earlier on the same pair of contracts
  dated      Dated Brent spot (FRED DCOILBRENTEU, the EIA copy; lags a few days) against the Brent front-month close
  ovx        CBOE crude-oil volatility index (FRED OVXCLS): the last 400 days for the chart, and the latest reading's
             percentile in the whole FRED history (from May 2007)
  eia        EIA weekly stocks: crude excl. SPR, total gasoline, distillate (diesel), Cushing, SPR, with the same-week
             five-year average and year-ago level (EIA history pages)
  cot        ICE Brent futures managed money (ICE public COT file) and WTI managed money (the board's CFTC positioning.json)
  positions  managed-money long and short summed over five oil contracts in million barrels, weekly from January 2011
             (the first ICE file): ICE Brent and ICE Gasoil (ICE COTHist<year>.csv), WTI on NYMEX and ICE Europe, RBOB and
             ULSD (CFTC disaggregated futures-only report, publicreporting.cftc.gov). A contract that cannot be fetched
             keeps its stored series; one never fetched is left out and named in `missing`.
Manual dated readings (ETF flows, freight and war-risk insurance, Middle East physical prices, export volumes, EIA
expectations, event odds, and the war events and escalation ladder under `war`) live in evidence/oil_tracking.json
and are merged by build_site.py. Writes data/oil.json as one row. No trading instruction."""
import csv
import html
import io
import json
import math
import re
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone

import pandas as pd

MONTHS = "FGHJKMNQUVXZ"
UA = {"User-Agent": "Mozilla/5.0 (personal research board)"}
EIA = "https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=PET&s={}&f=W"
EIA_SERIES = [("crude", "WCESTUS1", "原油（不含戰略儲備）", "Crude excl. SPR"),
              ("gasoline", "WGTSTUS1", "汽油", "Gasoline"),
              ("distillate", "WDISTUS1", "餾分油（柴油）", "Distillate (diesel)"),
              ("cushing", "W_EPC0_SAX_YCUOK_MBBL", "Cushing原油", "Cushing crude"),
              ("spr", "WCSSTUS1", "戰略儲備", "Strategic reserve")]
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}&cosd={}"
ICE_COT = "https://www.ice.com/publicdocs/futures/COTHist{}.csv"
CFTC_DISAGG = "https://publicreporting.cftc.gov/resource/72hh-3qpy.json"  # disaggregated, futures only
CURVE_KEEP_DAYS = 400
OVX_START = "2007-01-01"  # FRED OVXCLS starts 2007-05-10
POS_START = "2011-01-01"  # the first ICE COTHist file is 2011
GASOIL_BBL_PER_TONNE = 7.45  # ICE Gasoil: 100 tonnes a lot; 7.45 barrels a tonne, the usual gasoil (diesel) factor
# key, label, source ("ice": market name in the ICE file; "cftc": contract code), barrels per lot
POS_CONTRACTS = [
    ("brent", "ICE Brent", "ice", "ICE Brent Crude Futures - ICE Futures Europe", 1000),
    ("wti_nymex", "WTI（紐約商品交易所）", "cftc", "067651", 1000),
    ("wti_ice", "WTI（ICE 歐洲）", "cftc", "067411", 1000),
    ("rbob", "美國汽油 RBOB", "cftc", "111659", 1000),  # 42,000 US gallons = 1,000 barrels
    ("ulsd", "美國柴油 ULSD", "cftc", "022651", 1000),  # 42,000 US gallons = 1,000 barrels
    ("gasoil", "歐洲柴油 ICE Gasoil", "ice", "ICE Gasoil Futures - ICE Futures Europe", 100 * GASOIL_BBL_PER_TONNE),
]


def get(url, timeout=60, tries=3, agent=UA):
    for attempt in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=agent), timeout=timeout).read()
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(3 * (attempt + 1))


def fred(series, start):
    # FRED answers a curl agent at once and stalls on browser-like agents (as in build_data.fred)
    text = get(FRED.format(series, start), agent={"User-Agent": "curl/8.7.1"}).decode()
    df = pd.read_csv(io.StringIO(text))
    df.columns = ["date", "v"]
    s = pd.to_numeric(df.set_index("date")["v"], errors="coerce").dropna()
    return {d: float(v) for d, v in s.items()}


def contracts(asof, ahead=12):
    """Contract codes from next month on, plus December of the next two years (the curve's long end)."""
    d = date.fromisoformat(asof)
    out = []
    for i in range(1, ahead + 1):
        y, m = d.year + (d.month - 1 + i) // 12, (d.month - 1 + i) % 12 + 1
        out.append((y, m))
    for y in (d.year + 1, d.year + 2):
        if (y, 12) not in out:
            out.append((y, 12))
    return [(f"BZ{MONTHS[m - 1]}{str(y)[2:]}.NYM", f"{y}-{m:02d}") for y, m in out]


def month_back(d, months=1):
    """The same day `months` calendar months earlier (clamped to the month's last day)."""
    y, m = d.year, d.month - months
    while m < 1:
        y, m = y - 1, m + 12
    last = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)).day
    return date(y, m, min(d.day, last))


def snapshot_on_or_before(history, target):
    """The stored curve snapshot with the latest date on or before `target` (ISO), or None."""
    days = [d for d in history if d <= target]
    return (max(days), history[max(days)]) if days else (None, None)


def curve_spreads(rows, history, wti_close, asof):
    """The four spreads now and a week earlier on the same pair of contracts (the week-earlier values come from the
    stored snapshot on or before the front's date minus seven days)."""
    front, nxt = rows[0], rows[1]
    dec = next((r for r in rows if r["month"] == f"{int(asof[:4]) + 1}-12"), None)
    m6 = rows[5] if len(rows) > 5 else None
    wd, wpx = snapshot_on_or_before(history, (date.fromisoformat(front["date"]) - timedelta(days=7)).isoformat())
    out = []
    for key, b in (("m1_m2", nxt), ("m1_m6", m6), ("m1_dec_next", dec), ("brent_wti", "WTI")):
        if b is None:
            continue
        bm = b if b == "WTI" else b["month"]
        if b == "WTI":
            now = None if wti_close is None or wti_close[0] != front["date"] else round(front["close"] - wti_close[1], 2)
        else:
            now = round(front["close"] - b["close"], 2) if b["date"] == front["date"] else None
        week = round(wpx[front["month"]] - wpx[bm], 2) if wpx and front["month"] in wpx and bm in wpx else None
        out.append(dict(key=key, a=front["month"], b=bm, now=now, date=front["date"], week=week, week_date=wd,
                        chg_1w=None if now is None or week is None else round(now - week, 2)))
    return out


def build_curve(asof, prev=None):
    """Brent contracts' latest closes, the stored daily history of the curve, the week- and month-earlier curves, and
    the spreads. prev: the previous oil.json curve block, whose stored history is kept and extended."""
    import yfinance as yf
    history = {s["date"]: dict(s["px"]) for s in ((prev or {}).get("history") or []) if s.get("date") and s.get("px")}
    rows = []
    for ticker, month in contracts(asof):
        h = yf.Ticker(ticker).history(period="3mo", auto_adjust=False)
        if h.empty:
            continue
        h.index = h.index.tz_localize(None).normalize()
        h = h.loc[:asof, "Close"].dropna()
        if h.empty:
            continue
        for d, v in h.items():  # each contract's daily closes (Yahoo) fill the stored snapshots
            history.setdefault(d.strftime("%Y-%m-%d"), {})[month] = round(float(v), 2)
        if (date.fromisoformat(asof) - h.index[-1].date()).days > 4:
            continue  # expired or not trading
        week = h.loc[:h.index[-1] - pd.Timedelta(days=7)]
        rows.append(dict(ticker=ticker, month=month, close=round(float(h.iloc[-1]), 2), date=h.index[-1].strftime("%Y-%m-%d"),
                         week_date=week.index[-1].strftime("%Y-%m-%d") if len(week) else None,
                         chg_1w=round(float(h.iloc[-1] - week.iloc[-1]), 2) if len(week) else None))
    if len(rows) < 3:
        raise ValueError("Too few Brent contracts")
    rows.sort(key=lambda r: r["month"])
    wti = yf.Ticker("CL=F").history(period="3mo", auto_adjust=False)
    wti.index = wti.index.tz_localize(None).normalize()
    wti = wti.loc[:asof, "Close"].dropna()
    for d, v in wti.items():
        history.setdefault(d.strftime("%Y-%m-%d"), {})["WTI"] = round(float(v), 2)
    wti_close = (wti.index[-1].strftime("%Y-%m-%d"), float(wti.iloc[-1])) if len(wti) else None
    front, nxt = rows[0], rows[1]
    dec = next((r for r in rows if r["month"] == f"{int(asof[:4]) + 1}-12"), None)
    m6 = rows[5] if len(rows) > 5 else None

    def spread(a, b):
        return None if not (a and b) or a["date"] != b["date"] else round(a["close"] - b["close"], 2)
    spreads = dict(m1_m2=spread(front, nxt), m1_m6=spread(front, m6), m1_dec_next=spread(front, dec),
                   brent_wti=round(front["close"] - wti_close[1], 2) if wti_close and wti_close[0] == front["date"] else None,
                   wti_front=round(wti_close[1], 2) if wti_close else None, wti_date=wti_close[0] if wti_close else None)
    cut = (date.fromisoformat(asof) - timedelta(days=CURVE_KEEP_DAYS)).isoformat()
    history = {d: px for d, px in history.items() if cut <= d <= asof}
    lines = {"latest": dict(date=front["date"], px={r["month"]: r["close"] for r in rows})}
    for key, target in (("week", date.fromisoformat(front["date"]) - timedelta(days=7)),
                        ("month", month_back(date.fromisoformat(front["date"])))):
        d, px = snapshot_on_or_before(history, target.isoformat())
        if d:
            lines[key] = dict(date=d, px={m: v for m, v in px.items() if m != "WTI"})
    return dict(rows=rows, spreads=spreads, spread_list=curve_spreads(rows, history, wti_close, asof), lines=lines,
                history=[dict(date=d, px=history[d]) for d in sorted(history)], history_from=min(history) if history else None,
                source="https://finance.yahoo.com (NYMEX Brent financial futures BZ*.NYM; WTI CL=F)")


def build_dated(asof, brent_rows):
    start = (date.fromisoformat(asof) - timedelta(days=200)).isoformat()
    dated = {d: v for d, v in fred("DCOILBRENTEU", start).items() if d <= asof}
    fut = {r["date"]: r["close"] for r in brent_rows if r.get("close") is not None}
    rows = [dict(date=d, dated=round(v, 2), fut=fut.get(d), premium=round(v - fut[d], 2) if d in fut else None)
            for d, v in sorted(dated.items())]
    if not rows:
        raise ValueError("No Dated Brent")
    return dict(rows=rows, source="https://fred.stlouisfed.org/series/DCOILBRENTEU",
                note="FRED/EIA Brent spot (Dated); futures = board's front-month close (BZ=F) on the same date")


def build_ovx(asof):
    """The last 400 days for the chart, and the latest reading's percentile (share of readings at or below it) in the
    whole FRED history."""
    full = sorted((d, v) for d, v in fred("OVXCLS", OVX_START).items() if d <= asof)
    if not full:
        raise ValueError("No OVX")
    cut = (date.fromisoformat(asof) - timedelta(days=400)).isoformat()
    vals = [v for _, v in full]
    return dict(rows=[dict(date=d, v=round(v, 2)) for d, v in full if d >= cut],
                hist=dict(first=full[0][0], n=len(vals), pct=round(sum(v <= vals[-1] for v in vals) / len(vals) * 100)),
                source="https://fred.stlouisfed.org/series/OVXCLS")


def eia_series(sid):
    t = get(EIA.format(sid)).decode("utf-8", "ignore")
    vals = {}
    for row in re.findall(r"<tr>(.*?)</tr>", t, flags=re.S):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S)]
        if not cells or not re.match(r"\d{4}-[A-Z][a-z]{2}$", cells[0]):
            continue
        year = int(cells[0][:4])
        for i in range(1, len(cells) - 1, 2):
            md, v = cells[i], cells[i + 1].replace(",", "")
            if re.match(r"\d{2}/\d{2}$", md) and re.match(r"-?\d+(\.\d+)?$", v):
                vals[f"{year}-{md[:2]}-{md[3:]}"] = float(v)
    release = re.search(r"Release Date:\s*([\d/]+)", t)
    nxt = re.search(r"Next Release Date:\s*([\d/]+)", t)
    fix = lambda m: datetime.strptime(m.group(1), "%m/%d/%Y").strftime("%Y-%m-%d") if m else None
    return dict(sorted(vals.items())), fix(release), fix(nxt)


def week_stats(vals, d):
    """Same-week five-year average (the five prior years, nearest week within 4 days) and the year-ago level."""
    t = date.fromisoformat(d)

    def near(y):
        best = None
        for k, v in vals.items():
            diff = abs((date.fromisoformat(k) - t.replace(year=y)).days) if not (t.month == 2 and t.day == 29) else 99
            if diff <= 4 and (best is None or diff < best[0]):
                best = (diff, v)
        return None if best is None else best[1]
    prior = [near(t.year - k) for k in range(1, 6)]
    prior = [p for p in prior if p is not None]
    return (round(sum(prior) / len(prior), 1) if len(prior) == 5 else None), near(t.year - 1)


def build_eia(asof):
    out = {}
    cut = (date.fromisoformat(asof) - timedelta(days=760)).isoformat()
    for key, sid, zh, en in EIA_SERIES:
        vals, release, nxt = eia_series(sid)
        vals = {d: v for d, v in vals.items() if d <= asof}
        dates = list(vals)
        if len(dates) < 2:
            raise ValueError(f"EIA {sid} empty")
        recent = [d for d in dates if d >= cut]
        rows = []
        for d in recent:
            avg5, yago = week_stats(vals, d)
            rows.append(dict(date=d, v=vals[d], avg5=avg5, yago=yago))
        last, prev = rows[-1], vals[dates[-2]]
        out[key] = dict(label=zh, label_en=en, series=sid, unit="千桶", unit_en="thousand bbl", rows=rows,
                        latest=dict(date=last["date"], v=last["v"], chg_1w=round(last["v"] - prev, 1), prev_date=dates[-2],
                                    vs_avg5=None if last["avg5"] is None else round(last["v"] - last["avg5"], 1),
                                    vs_avg5_pct=None if not last["avg5"] else round((last["v"] / last["avg5"] - 1) * 100, 1),
                                    vs_yago=None if last["yago"] is None else round(last["v"] - last["yago"], 1)),
                        release=release, next_release=nxt, source=EIA.format(sid))
    return out


def build_cot(asof, positioning_rows):
    year = int(asof[:4])
    brent = []
    for y in (year - 1, year):
        try:
            text = get(ICE_COT.format(y)).decode("utf-8-sig", "ignore")
        except Exception:
            if y == year:
                raise
            continue
        for r in csv.DictReader(io.StringIO(text)):
            if r.get("Market_and_Exchange_Names", "").strip() != "ICE Brent Crude Futures - ICE Futures Europe":
                continue
            d = datetime.strptime(r["As_of_Date_Form_MM/DD/YYYY"].strip(), "%m/%d/%Y").strftime("%Y-%m-%d")
            lo, sh = int(r["M_Money_Positions_Long_All"]), int(r["M_Money_Positions_Short_All"])
            brent.append(dict(date=d, mm_long=lo, mm_short=sh, net=lo - sh, oi=int(r["Open_Interest_All"])))
    brent = sorted({r["date"]: r for r in brent if r["date"] <= asof}.values(), key=lambda r: r["date"])
    if not brent:
        raise ValueError("No ICE Brent COT rows")
    wti = [dict(date=r["date"], net=r["lev_net"], oi=r.get("oi")) for r in positioning_rows
           if r.get("market") == "067651" and r.get("lev_net") is not None and r["date"] <= asof]
    wti.sort(key=lambda r: r["date"])
    return dict(brent=brent[-60:], wti=wti[-60:], source_brent=ICE_COT.format(year),
                source_wti="https://www.cftc.gov/dea/futures/petroleum_lf.htm (WTI 067651, managed money)")


def ice_rows(text, names):
    """{market name: {date: (long, short)}} of managed money, futures only, from one ICE COTHist file."""
    out = {n: {} for n in names}
    for r in csv.DictReader(io.StringIO(text)):
        name = (r.get("Market_and_Exchange_Names") or "").strip()
        if name not in out or (r.get("FutOnly_or_Combined") or "FutOnly").strip() != "FutOnly":
            continue
        try:
            d = datetime.strptime(r["As_of_Date_Form_MM/DD/YYYY"].strip(), "%m/%d/%Y").strftime("%Y-%m-%d")
            out[name][d] = (int(r["M_Money_Positions_Long_All"]), int(r["M_Money_Positions_Short_All"]))
        except (KeyError, ValueError):
            continue
    return out


def cftc_rows(code, since):
    """{date: (long, short)} of managed money, futures only, for one CFTC contract code."""
    q = (f"?$select=report_date_as_yyyy_mm_dd,futonly_or_combined,m_money_positions_long_all,m_money_positions_short_all"
         f"&$where=cftc_contract_market_code='{code}' AND report_date_as_yyyy_mm_dd>='{since}'"
         f"&$order=report_date_as_yyyy_mm_dd&$limit=5000")
    raw = json.loads(get(CFTC_DISAGG + q.replace(" ", "%20").replace("'", "%27"), agent={"User-Agent": "curl/8.7.1"}).decode())
    out = {}
    for r in raw:
        if (r.get("futonly_or_combined") or "FutOnly") != "FutOnly":
            continue
        try:
            out[r["report_date_as_yyyy_mm_dd"][:10]] = (int(float(r["m_money_positions_long_all"])), int(float(r["m_money_positions_short_all"])))
        except (KeyError, TypeError, ValueError):
            continue
    if not out:
        raise ValueError(f"CFTC {code}: no rows")
    return out


def aggregate_positions(series, contracts=POS_CONTRACTS):
    """Weekly managed-money long, short and net summed over the contracts in `series` ({key: {date: (long, short)}}),
    in million barrels, on the dates every one of them reports. Contract sizes from `contracts` (barrels per lot)."""
    size = {k: bbl for k, _, _, _, bbl in contracts}
    keys = [k for k in series if series[k]]
    if not keys:
        return []
    days = sorted(set.intersection(*(set(series[k]) for k in keys)))
    rows = []
    for d in days:
        lo = sum(series[k][d][0] * size[k] for k in keys) / 1e6
        sh = sum(series[k][d][1] * size[k] for k in keys) / 1e6
        rows.append(dict(date=d, long=round(lo, 1), short=round(sh, 1), net=round(lo - sh, 1)))
    return rows


def positions_summary(rows):
    """Latest net, its one- and four-week changes and its percentile (share of weeks at or below it) in `rows`."""
    if not rows:
        return {}
    last = rows[-1]
    out = dict(date=last["date"], long=last["long"], short=last["short"], net=last["net"], n=len(rows), first=rows[0]["date"],
               pct=round(sum(r["net"] <= last["net"] for r in rows) / len(rows) * 100))
    for k, n in (("chg_1w", 1), ("chg_4w", 4)):
        if len(rows) > n:
            out[k], out[k + "_base"] = round(last["net"] - rows[-1 - n]["net"], 1), rows[-1 - n]["date"]
    return out


def build_positions(asof, prev=None):
    """Managed money in five oil contracts (Brent, WTI on NYMEX and ICE, RBOB, ULSD, gasoil). Each contract keeps its
    stored series when its source fails; a contract with no series at all is named in `missing`."""
    stored = {k: {d: (lo, sh) for d, lo, sh in v} for k, v in ((prev or {}).get("series") or {}).items()}
    series, errors = {}, []
    ice = [c for c in POS_CONTRACTS if c[2] == "ice"]
    have = [max(stored[k]) for k, *_ in ice if stored.get(k)]
    first_year = int(min(have)[:4]) if len(have) == len(ice) else int(POS_START[:4])
    fresh = {name: {} for *_, name, _ in ice}
    for y in range(first_year, int(asof[:4]) + 1):
        try:
            got = ice_rows(get(ICE_COT.format(y)).decode("utf-8-sig", "ignore"), list(fresh))
        except Exception as exc:
            errors.append(f"ICE {y}: {str(exc)[:80]}")
            continue
        for name, rows in got.items():
            fresh[name].update(rows)
    for key, label, src, ident, _ in POS_CONTRACTS:
        if src == "ice":
            new = fresh[ident]
        else:
            try:
                new = cftc_rows(ident, POS_START)
            except Exception as exc:
                errors.append(f"CFTC {ident}: {str(exc)[:80]}")
                new = {}
        merged = {**stored.get(key, {}), **new}
        merged = {d: v for d, v in merged.items() if POS_START <= d <= asof}
        if merged:
            series[key] = merged
    if not series:
        raise ValueError("No positions from CFTC or ICE: " + "; ".join(errors))
    rows = aggregate_positions(series)
    latest = max(max(v) for v in series.values())
    parts = []
    for key, label, src, ident, bbl in POS_CONTRACTS:
        s = series.get(key)
        if not s:
            continue
        ds = sorted(s)
        d = rows[-1]["date"] if rows and rows[-1]["date"] in s else ds[-1]
        prev_d = next((x for x in reversed(ds) if x < d), None)
        lo, sh = s[d]
        net_mb = (lo - sh) * bbl / 1e6
        parts.append(dict(key=key, label=label, date=d, latest=ds[-1], long=lo, short=sh, net=lo - sh, bbl=bbl,
                          net_mb=round(net_mb, 1),
                          chg_1w_mb=None if prev_d is None else round(net_mb - (s[prev_d][0] - s[prev_d][1]) * bbl / 1e6, 1)))
    return dict(rows=rows, summary=positions_summary(rows), parts=parts,
                missing=[label for key, label, *_ in POS_CONTRACTS if key not in series],
                behind=[dict(label=p["label"], latest=p["latest"]) for p in parts if p["latest"] < latest],
                errors=errors, gasoil_bbl_per_tonne=GASOIL_BBL_PER_TONNE,
                series={k: [[d, *v[d]] for d in sorted(v)] for k, v in series.items()},
                source_ice=ICE_COT.format(asof[:4]), source_cftc=CFTC_DISAGG)


def build_safe(out_dir, asof):
    """Build each block; on failure keep the previous block (with its own dates) and record the error."""
    path = out_dir / "oil.json"
    prev = {}
    if path.exists():
        try:
            prev = json.loads(path.read_text())[0]
        except Exception:
            prev = {}
    brent_rows = json.loads((out_dir / "brent.json").read_text()) if (out_dir / "brent.json").exists() else []
    pos_rows = json.loads((out_dir / "positioning.json").read_text()) if (out_dir / "positioning.json").exists() else []
    row = dict(asof=asof, built_at=datetime.now(timezone.utc).isoformat(), errors=[])
    steps = [("curve", lambda: build_curve(asof, prev.get("curve"))), ("dated", lambda: build_dated(asof, brent_rows)),
             ("ovx", lambda: build_ovx(asof)), ("eia", lambda: build_eia(asof)), ("cot", lambda: build_cot(asof, pos_rows)),
             ("positions", lambda: build_positions(asof, prev.get("positions")))]
    for key, fn in steps:
        try:
            row[key] = fn()
        except Exception as exc:
            row["errors"].append(f"{key}: {str(exc)[:160]}")
            if key in prev:
                row[key] = prev[key]
                row["errors"][-1] += " (previous block kept)"
    path.write_text(json.dumps([row], ensure_ascii=False, separators=(",", ":")))
    print(f"  oil.json  blocks={[k for k, _ in steps if k in row]} errors={len(row['errors'])}")
    return row


if __name__ == "__main__":
    import os
    import sys
    from pathlib import Path
    out = Path(__file__).resolve().parent / "data"
    asof = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("BOARD_ASOF") or json.loads((out / "breadth_now.json").read_text())[0]["asof"]
    r = build_safe(out, asof)
    print(json.dumps(r["errors"], ensure_ascii=False))
