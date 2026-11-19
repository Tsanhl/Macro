"""Institutional positioning board: builds data/*.json for the 今日 and 本週 pages. No AI calls.

  cftc.json       CFTC weekly positions by trader category, with 52-week z-scores and weekly changes.
  cta.json        Trend-following model: signal, distance to the flip, entry date, five-day signal change.
  vc.json         Volatility-control model on the S&P 500 and, per $10bn of capital, on the Nasdaq 100.
  vol.json        Asset managers' VIX futures position, VVIX against VIX, VIX against the S&P move, realised vs implied.
  nondealer.json  Non-dealer net position in S&P and Nasdaq E-minis, in dollars.
  levels.json     Key levels for NQ, ES and VIX; one-sd daily moves (ES: VIX1D only; NQ: VXN) and straddle prices; the
                  strikes with the most option open interest; leveraged-ETF rebalancing; the volatility strip (with
                  one-year high, low, median and percentile); the ^GSPC and SPY closes; the S&P's realised move
                  against the VIX1D move priced the evening before; upcoming earnings dates as Yahoo lists them.
  level_log.json  The levels of each session, kept so they can be scored later.

Everything except the CFTC numbers and observed prices/open interest is a model estimate: it assumes how these funds
trade; it is not their orders. Dollar amounts depend on stated assumptions; read direction, turns and trigger levels.

Run: python3 build.py   (writes data/ atomically; a failed market is skipped and listed in meta.json)
"""
import io
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
WARN = []


def warn(msg):
    print("  WARNING", msg)
    WARN.append(msg)


def r(x, n=1):
    return None if x is None or pd.isna(x) else round(float(x), n)


def write(name, obj):
    DATA.mkdir(exist_ok=True)
    tmp = DATA / f".{name}.json.tmp"
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
    os.replace(tmp, DATA / f"{name}.json")


def get_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")


# =====================================================================================================================
# 1. CFTC
# =====================================================================================================================
CFTC = "https://publicreporting.cftc.gov/resource/{ds}.json"
TFF, DIS = "gpe5-46if", "72hh-3qpy"
# category key: (label, long field, short field)
TFF_CATS = {"am": ("資產管理", "asset_mgr_positions_long", "asset_mgr_positions_short"),
            "lev": ("槓桿基金", "lev_money_positions_long", "lev_money_positions_short"),
            "dealer": ("交易商", "dealer_positions_long_all", "dealer_positions_short_all"),
            "other": ("其他申報", "other_rept_positions_long", "other_rept_positions_short")}
DIS_CATS = {"prod": ("生產商", "prod_merc_positions_long", "prod_merc_positions_short"),
            "mm": ("管理資金", "m_money_positions_long_all", "m_money_positions_short_all"),
            "swap": ("掉期交易商", "swap_positions_long_all", "swap__positions_short_all"),
            "other": ("其他申報", "other_rept_positions_long", "other_rept_positions_short")}
# code: (name, group, dataset)
CFTC_MARKETS = {
    "13874A": ("標普500", "股票", "tff"), "209742": ("納指100", "股票", "tff"), "124603": ("道指", "股票", "tff"),
    "239742": ("羅素2000", "股票", "tff"), "33874A": ("標普中型400", "股票", "tff"),
    "244042": ("MSCI新興市場", "股票", "tff"), "244041": ("MSCI EAFE", "股票", "tff"), "1170E1": ("VIX", "股票", "tff"),
    "042601": ("2年期美債", "定息", "tff"), "044601": ("5年期美債", "定息", "tff"), "043602": ("10年期美債", "定息", "tff"),
    "043607": ("超長10年期美債", "定息", "tff"), "020601": ("長期美債", "定息", "tff"), "020604": ("超長期美債", "定息", "tff"),
    "134741": ("3個月SOFR", "短期利率", "tff"), "045601": ("聯邦基金利率", "短期利率", "tff"),
    "098662": ("美元指數", "外匯", "tff"), "099741": ("歐元", "外匯", "tff"), "097741": ("日圓", "外匯", "tff"),
    "096742": ("英鎊", "外匯", "tff"), "232741": ("澳元", "外匯", "tff"), "090741": ("加元", "外匯", "tff"),
    "092741": ("瑞士法郎", "外匯", "tff"), "095741": ("墨西哥披索", "外匯", "tff"), "133741": ("比特幣", "加密貨幣", "tff"),
    "067651": ("WTI原油", "商品", "dis"), "023651": ("天然氣", "商品", "dis"), "111659": ("汽油", "商品", "dis"),
    "022651": ("取暖油", "商品", "dis"), "088691": ("黃金", "商品", "dis"), "084691": ("白銀", "商品", "dis"),
    "085692": ("銅", "商品", "dis"), "076651": ("鉑金", "商品", "dis"), "002602": ("粟米", "商品", "dis"),
    "005602": ("大豆", "商品", "dis"), "001602": ("小麥", "商品", "dis"),
}


def cftc_market(code, ds, since):
    dsid = TFF if ds == "tff" else DIS
    q = (f"?$limit=5000&$order=report_date_as_yyyy_mm_dd&cftc_contract_market_code={code}"
         f"&$where=report_date_as_yyyy_mm_dd>='{since}'")
    raw = pd.DataFrame(json.loads(get_text(CFTC.format(ds=dsid) + q.replace(" ", "%20").replace("'", "%27"))))
    num = lambda c: pd.to_numeric(raw[c], errors="coerce")
    df = pd.DataFrame({"date": pd.to_datetime(raw["report_date_as_yyyy_mm_dd"]), "oi": num("open_interest_all")})
    cats = TFF_CATS if ds == "tff" else DIS_CATS
    for k, (_, lo, sh) in cats.items():
        df[k] = num(lo) - num(sh)
    return df.drop_duplicates("date").sort_values("date").set_index("date"), cats


def cat_stats(s):
    """Latest net, its 52-week z, w/w change and that change in units of the 52-week sd of weekly changes, 4-week
    change, and the 3-year percentile of the net."""
    s = s.dropna()
    w52, d = s.iloc[-52:], s.diff()
    d52 = d.iloc[-52:]
    z = (s.iloc[-1] - w52.mean()) / w52.std() if w52.std() else np.nan
    dz = d.iloc[-1] / d52.std() if d52.std() else np.nan
    s3 = s[s.index > s.index[-1] - pd.DateOffset(years=3)]
    return {"net": int(s.iloc[-1]), "z": r(z), "chg": int(d.iloc[-1]), "chg_z": r(dz),
            "chg4": int(s.iloc[-1] - s.iloc[-5]) if len(s) > 4 else None,
            "pct3y": r((s3 < s.iloc[-1]).mean() * 100, 0)}


def build_cftc():
    since = (pd.Timestamp.today() - pd.DateOffset(years=5)).strftime("%Y-%m-%d")
    rows, hist = [], {}
    for code, (name, group, ds) in CFTC_MARKETS.items():
        try:
            df, cats = cftc_market(code, ds, since)
        except Exception as e:
            warn(f"CFTC {name} ({code}) failed: {e}")
            continue
        if len(df) < 60:
            warn(f"CFTC {name} ({code}) has only {len(df)} reports; skipped")
            continue
        rows.append({"code": code, "name": name, "group": group, "ds": ds, "date": df.index[-1].strftime("%Y-%m-%d"),
                     "oi": int(df["oi"].iloc[-1]),
                     "cats": {k: {"label": cats[k][0], **cat_stats(df[k])} for k in cats}})
        h = df[df.index > df.index[-1] - pd.DateOffset(years=3)]
        hist[code] = {"dates": [d.strftime("%Y-%m-%d") for d in h.index],
                      **{k: [None if pd.isna(v) else int(v) for v in h[k]] for k in cats}}
    write("cftc", {"rows": rows, "hist": hist,
                   "cats": {"tff": {k: v[0] for k, v in TFF_CATS.items()}, "dis": {k: v[0] for k, v in DIS_CATS.items()}}})
    return max((x["date"] for x in rows), default=None)


# =====================================================================================================================
# 2. CTA trend model
# =====================================================================================================================
# About 3, 6 and 12 months of sessions: the medium-term speed of the large trend funds. Tested 2026-10-31 against
# DBMF/KMLM weekly returns, 2022-24 and 2025-26 separately; dropping the 1-month lookback raised both.
LOOKBACKS = (60, 125, 250)
VOL_WIN = 60
ECB = ("https://data-api.ecb.europa.eu/service/data/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_{}"
       "?startPeriod=2007-01-01&format=csvdata")
BOE = ("https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&Datefrom=01/Jan/2007"
       "&Dateto=now&SeriesCodes={}&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N")
MOF = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/{}"


def ecb(tenor):
    df = pd.read_csv(io.StringIO(get_text(ECB.format(tenor))))
    return pd.Series(df["OBS_VALUE"].values, index=pd.to_datetime(df["TIME_PERIOD"])).astype(float)


def boe(code):
    df = pd.read_csv(io.StringIO(get_text(BOE.format(code))), header=None, names=["date", "v"])
    df = df[pd.to_numeric(df["v"], errors="coerce").notna()]
    return pd.Series(df["v"].astype(float).values, index=pd.to_datetime(df["date"], format="%d %b %Y"))


def mof(col):
    frames = []
    for f in ("historical/jgbcme_all.csv", "jgbcme.csv"):  # the history file stops at last month's end
        df = pd.read_csv(io.StringIO(get_text(MOF.format(f))), skiprows=1)
        df = df[df["Date"].astype(str).str.match(r"^\d{4}/\d{1,2}/\d{1,2}$")]
        frames.append(pd.Series(pd.to_numeric(df[col], errors="coerce").values, index=pd.to_datetime(df["Date"])))
    s = pd.concat(frames).dropna()
    return s[~s.index.duplicated(keep="last")].sort_index()


class Yld:
    """A government yield used as a market: the model trades minus the yield; P&L is priced at `dur` years."""
    def __init__(self, fn, arg, dur):
        self.fn, self.arg, self.dur = fn, arg, dur

    def __call__(self):
        return self.fn(self.arg)


# key, name, group, Yahoo ticker (display price) or Yld, and optionally an ETF whose adjusted price drives the
# signal and P&L: Yahoo's continuous futures are spliced front months with no roll yield, which misstates trends in
# steep curves (this year's backwardated crude). The ETFs roll futures (commodities) or hold deposits (FX), so their
# total return carries the roll and the carry. Flip levels are still quoted on the futures price.
# Short-rate futures (SOFR, Euribor, SONIA) have no usable free history, so 2-year yields stand in (UK: 5-year).
CTA_MARKETS = [
    ("ES", "標普500", "美股", "ES=F"), ("NQ", "納指100", "美股", "NQ=F"), ("YM", "道指", "美股", "YM=F"),
    ("RTY", "羅素2000", "美股", "RTY=F"), ("MID", "標普中型400", "美股", "^SP400"),
    ("SX5E", "歐洲斯托克50", "環球股市", "^STOXX50E"), ("DAX", "德國DAX", "環球股市", "^GDAXI"),
    ("FTSE", "英國富時100", "環球股市", "^FTSE"), ("CAC", "法國CAC", "環球股市", "^FCHI"),
    ("NKY", "日經225", "環球股市", "^N225"), ("HSI", "恒生指數", "環球股市", "^HSI"),
    ("KOSPI", "韓國KOSPI", "環球股市", "^KS11"), ("TWSE", "台灣加權", "環球股市", "^TWII"),
    ("ASX", "澳洲ASX200", "環球股市", "^AXJO"), ("NIFTY", "印度Nifty", "環球股市", "^NSEI"),
    ("ZT", "2年期美債", "美債", "ZT=F"), ("ZF", "5年期美債", "美債", "ZF=F"), ("ZN", "10年期美債", "美債", "ZN=F"),
    ("TN", "超長10年期美債", "美債", "TN=F"), ("ZB", "長期美債", "美債", "ZB=F"), ("UB", "超長期美債", "美債", "UB=F"),
    ("DE10", "德國10年（孳息）", "海外國債", Yld(ecb, "10Y", 8)), ("UK10", "英國10年（孳息）", "海外國債", Yld(boe, "IUDMNPY", 8)),
    ("JP10", "日本10年（孳息）", "海外國債", Yld(mof, "10Y", 8)),
    ("DE2", "德國2年（孳息）", "短期利率", Yld(ecb, "2Y", 2)), ("UK5", "英國5年（孳息）", "短期利率", Yld(boe, "IUDSNPY", 4.5)),
    ("JP2", "日本2年（孳息）", "短期利率", Yld(mof, "2Y", 2)),
    ("DXY", "美元指數", "外匯", "DX-Y.NYB", "UUP"), ("6E", "歐元", "外匯", "6E=F", "FXE"), ("6J", "日圓", "外匯", "6J=F", "FXY"),
    ("6B", "英鎊", "外匯", "6B=F", "FXB"), ("6A", "澳元", "外匯", "6A=F", "FXA"), ("6C", "加元", "外匯", "6C=F", "FXC"),
    ("6S", "瑞士法郎", "外匯", "6S=F", "FXF"), ("6M", "墨西哥披索", "外匯", "6M=F"),
    ("CL", "WTI原油", "能源", "CL=F", "USO"), ("BZ", "布蘭特原油", "能源", "BZ=F", "BNO"), ("HO", "取暖油", "能源", "HO=F"),
    ("RB", "汽油", "能源", "RB=F", "UGA"), ("NG", "天然氣", "能源", "NG=F", "UNG"),
    ("GC", "黃金", "金屬", "GC=F", "GLD"), ("SI", "白銀", "金屬", "SI=F", "SLV"), ("HG", "銅", "金屬", "HG=F", "CPER"),
    ("PL", "鉑金", "金屬", "PL=F", "PPLT"), ("PA", "鈀金", "金屬", "PA=F", "PALL"),
    ("ZC", "粟米", "農產品", "ZC=F", "CORN"), ("ZS", "大豆", "農產品", "ZS=F", "SOYB"), ("ZW", "小麥", "農產品", "ZW=F", "WEAT"),
    ("KC", "咖啡", "農產品", "KC=F"), ("SB", "糖", "農產品", "SB=F", "CANE"), ("CC", "可可", "農產品", "CC=F"),
    ("CT", "棉花", "農產品", "CT=F"), ("LE", "活牛", "農產品", "LE=F"),
    ("BTC", "比特幣", "加密貨幣", "BTC=F"),
]


def trend_signal(level, lookbacks=None):
    """−100 (full short) to +100 (full long): the average over the lookbacks of tanh(z), z = the move over k sessions
    divided by the 60-session daily sd times sqrt(k). `level` is log price, or minus the yield for yield markets."""
    sd = level.diff().rolling(VOL_WIN).std()
    z = pd.concat({k: (level - level.shift(k)) / (sd * np.sqrt(k)) for k in (lookbacks or LOOKBACKS)}, axis=1)
    return np.tanh(z).mean(axis=1) * 100


def signal_after(lv, i, x):
    """Signal at session i+1 if the level moves by x from session i (lv: numpy array of levels)."""
    hist = np.append(lv[i - VOL_WIN + 1:i + 1], lv[i] + x)
    sd = np.diff(hist).std(ddof=1)
    return np.mean([np.tanh((lv[i] + x - lv[i + 1 - k]) / (sd * np.sqrt(k))) for k in LOOKBACKS]) * 100


def flip_move(lv, i):
    """The one-session move in level units at which the next session's signal crosses zero. It can lie on either side
    of today's level: the lookback windows roll forward one session, so the signal can change sign on an unchanged
    close. None when there is no sign change within 25 daily sd (effectively locked in)."""
    sd = np.diff(lv[i - VOL_WIN:i + 1]).std(ddof=1)
    lo, hi = -25 * sd, 25 * sd
    s_lo = np.sign(signal_after(lv, i, lo))
    if s_lo == np.sign(signal_after(lv, i, hi)):
        return None
    for _ in range(50):
        mid = (lo + hi) / 2
        if np.sign(signal_after(lv, i, mid)) == s_lo:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


HIST_START = "2007-01-01"  # long enough to test the model on years never used to choose its settings


def completed(df):
    """Drop today's bar until the US cash session has closed (16:15 New York): Yahoo serves a live, unfinished daily
    bar for futures and indices that would otherwise be read as a close."""
    now = pd.Timestamp.now(tz="America/New_York")
    if now.hour * 60 + now.minute < 16 * 60 + 15:
        df = df[df.index < now.normalize().tz_localize(None)]
    return df


def yahoo(ticker, adjust=False):
    px = yf.download(ticker, start=HIST_START, auto_adjust=adjust, progress=False)["Close"].squeeze().dropna()
    px.index = pd.to_datetime(px.index).tz_localize(None)
    return completed(px[px > 0])


def load_level(src, etf=None):
    """(level series for the model, display price series, duration for yields or None)."""
    if isinstance(src, Yld):
        y = src().sort_index()
        y = y[~y.index.duplicated(keep="last")].dropna()
        return -y, y, src.dur
    px = yahoo(src)
    return np.log(yahoo(etf, adjust=True) if etf else px), px, None



def build_cta(days=100):
    out = []
    for key, name, group, src, *etf in CTA_MARKETS:
        etf = etf[0] if etf else None
        try:
            lvl, px, dur = load_level(src, etf)
        except Exception as e:
            warn(f"CTA {name} ({key}) download failed: {e}")
            continue
        is_yield = dur is not None
        if len(lvl) < max(LOOKBACKS) + VOL_WIN + days:
            warn(f"CTA {name} ({key}) has too little history; skipped")
            continue
        sig = trend_signal(lvl)
        lv, n = lvl.to_numpy(), len(lvl)
        sd_daily = lvl.diff().rolling(VOL_WIN).std()
        # flip distance for the last `days` sessions, in daily sd units (comparable across markets)
        heat = []
        for i in range(n - days, n):
            m = flip_move(lv, i)
            heat.append({"sig": r(sig.iloc[i], 0), "sd": None if m is None else r(abs(m) / sd_daily.iloc[i], 2)})
        cur = np.sign(sig.iloc[-1])
        m = flip_move(lv, n - 1)
        # the flip lies on the side the model already holds: the next session flips it even on an unchanged close
        flat = bool(m is not None and cur != 0 and np.sign(m) == cur)
        flip_pct = None if m is None else (r(-m * 100, 0) if is_yield else r((np.exp(m) - 1) * 100, 2))  # bp for yields
        # quoted on the futures price; for ETF-driven markets the same percentage move is applied to it
        flip_level = None if m is None else (r(-(lv[-1] + m), 3) if is_yield else r(px.iloc[-1] * np.exp(m), 4))
        # entry: the first session of the current sign
        sgn = np.sign(sig)
        changes = sgn.ne(sgn.shift()) & sig.notna()
        entry = sig.index[changes][-1] if changes.any() else sig.index[0]
        since = lv[-1] - lvl.loc[entry]
        pnl = since * cur if not is_yield else since * cur * 100  # % (log) for prices, bp in the trade's favour for yields
        out.append({"key": key, "name": name, "group": group, "yield": is_yield, "etf": etf,
                    "ticker": None if is_yield else src,
                    "date": lvl.index[-1].strftime("%Y-%m-%d"), "last": r(px.iloc[-1], 3 if is_yield else 4),
                    "sig": r(sig.iloc[-1], 0), "sig_5d": r(sig.iloc[-1] - sig.iloc[-6], 0),
                    "pos": "LONG" if cur > 0 else "SHORT", "flip_sd": heat[-1]["sd"], "flip_move": flip_pct,
                    "flip_level": flip_level, "flat": flat, "entry": entry.strftime("%Y-%m-%d"),
                    "pnl": r(pnl * (1 if is_yield else 100), 1), "days_in": int((sig.index >= entry).sum()),
                    "heat": heat, "heat_dates": [d.strftime("%Y-%m-%d") for d in lvl.index[n - days:]]})
    write("cta", {"markets": out, "lookbacks": LOOKBACKS})
    return pd.Series([m["date"] for m in out]).mode().max() if out else None  # the usual date; crypto trades weekends


# =====================================================================================================================
# 3. Vol control
# =====================================================================================================================
VC_TARGET, VC_CAP = 0.10, 1.5  # 10% target vol, leverage capped at 1.5x
VC_AUM_BN = 200  # assumed capital in S&P vol-control strategies, $bn; full cap = $300bn of equity exposure


def vc_leverage(ret):
    """Leverage = target vol over the higher of 1- and 3-month realised vol, capped."""
    rv = np.maximum(ret.rolling(21).std(), ret.rolling(63).std()) * np.sqrt(252)
    return np.minimum(VC_TARGET / rv, VC_CAP)


VC_NQ_UNIT_BN = 10  # no public estimate of Nasdaq-benchmarked vol-control capital exists: quote flows per $10bn


def vc_nasdaq():
    """The same rule on the Nasdaq 100. Flows are per VC_NQ_UNIT_BN of capital, not a market total."""
    px = yf.download("^NDX", start="2015-01-01", auto_adjust=False, progress=False)["Close"].squeeze().dropna()
    px.index = pd.to_datetime(px.index).tz_localize(None)
    px = completed(px)
    ret = np.log(px).diff()
    lev = vc_leverage(ret)
    cur, nxt = lev.iloc[-1], px.index[-1] + pd.offsets.BDay(1)

    def after(moves):
        idx = pd.bdate_range(nxt, periods=len(moves))
        return vc_leverage(pd.concat([ret, pd.Series(np.log1p(moves), index=idx)])).iloc[-1]

    y3 = lev[lev.index > px.index[-1] - pd.DateOffset(years=3)]
    return {"date": px.index[-1].strftime("%Y-%m-%d"), "lev": r(cur, 3), "lev_5d": r(cur - lev.iloc[-6], 3),
            "lev_21d": r(cur - lev.iloc[-22], 3), "pct3y": r((y3 < y3.iloc[-1]).mean() * 100, 0), "unit": VC_NQ_UNIT_BN,
            "rv21": r(ret.rolling(21).std().iloc[-1] * np.sqrt(252) * 100),
            "rv63": r(ret.rolling(63).std().iloc[-1] * np.sqrt(252) * 100),
            "curve": [{"move": r(m * 100, 1), "flow": r((after([m]) - cur) * VC_NQ_UNIT_BN, 2)}
                      for m in np.round(np.arange(-0.05, 0.0501, 0.0025), 4)],
            "quiet": {n: r((after([0.0] * n) - cur) * VC_NQ_UNIT_BN, 2) for n in (1, 5, 10)}}


def build_vc():
    px = yf.download("^GSPC", start="2015-01-01", auto_adjust=False, progress=False)["Close"].squeeze().dropna()
    px.index = pd.to_datetime(px.index).tz_localize(None)
    px = completed(px)
    vix = yf.download("^VIX", start="2015-01-01", auto_adjust=False, progress=False)["Close"].squeeze().dropna()
    vix.index = pd.to_datetime(vix.index).tz_localize(None)
    vix = completed(vix)
    ret = np.log(px).diff()
    lev = vc_leverage(ret)
    expo = lev * VC_AUM_BN
    rv21 = ret.rolling(21).std() * np.sqrt(252) * 100
    rv63 = ret.rolling(63).std() * np.sqrt(252) * 100
    cur = lev.iloc[-1]
    nxt = px.index[-1] + pd.offsets.BDay(1)

    def after(moves):
        idx = pd.bdate_range(nxt, periods=len(moves))
        rr = pd.concat([ret, pd.Series(np.log1p(moves), index=idx)])
        return vc_leverage(rr).iloc[-1]

    curve = [{"move": r(m * 100, 1), "flow": r((after([m]) - cur) * VC_AUM_BN, 1)}
             for m in np.round(np.arange(-0.05, 0.0501, 0.0025), 4)]
    quiet = {n: r((after([0.0] * n) - cur) * VC_AUM_BN, 1) for n in (1, 5, 10)}
    sigma = r(vix.iloc[-1] / np.sqrt(252), 2)  # one-day 1-sd move implied by the VIX, %
    h = px.index[px.index > px.index[-1] - pd.DateOffset(years=3)]
    s3 = expo.loc[h]
    write("vc", {"nq": vc_nasdaq(), "date": px.index[-1].strftime("%Y-%m-%d"), "spx": r(px.iloc[-1], 0), "aum": VC_AUM_BN,
                 "target": VC_TARGET, "cap": VC_CAP, "lev": r(cur, 3), "expo": r(expo.iloc[-1], 0),
                 "expo_5d": r(expo.iloc[-1] - expo.iloc[-6], 1), "expo_21d": r(expo.iloc[-1] - expo.iloc[-22], 1),
                 "pct3y": r((s3 < s3.iloc[-1]).mean() * 100, 0), "max3y": r(s3.max(), 0),
                 "max3y_date": s3.idxmax().strftime("%Y-%m-%d"), "rv21": r(rv21.iloc[-1]), "rv63": r(rv63.iloc[-1]),
                 "vix": r(vix.iloc[-1], 2), "sigma": sigma, "curve": curve, "quiet": quiet,
                 "hist": {"dates": [d.strftime("%Y-%m-%d") for d in h], "expo": [r(x, 1) for x in expo.loc[h]],
                          "spx": [r(x, 0) for x in px.loc[h]], "rv21": [r(x) for x in rv21.loc[h]],
                          "rv63": [r(x) for x in rv63.loc[h]]}})
    return px.index[-1].strftime("%Y-%m-%d")


# =====================================================================================================================
# 4. Shared download helper
# =====================================================================================================================
def yclose(tickers, start, adjust=False):
    df = yf.download(tickers, start=start, auto_adjust=adjust, progress=False)["Close"]
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return completed(df)


# =====================================================================================================================
# 5. Volatility signals: asset managers' VIX futures position, vol of vol, VIX against the S&P move
# =====================================================================================================================
HORIZONS = {"+1日": 1, "+1週": 5, "+2週": 10, "+1月": 21, "+3月": 63}


def cftc_series(code, since, fields):
    q = (f"?$limit=5000&$order=report_date_as_yyyy_mm_dd&cftc_contract_market_code={code}"
         f"&$where=report_date_as_yyyy_mm_dd>='{since}'")
    raw = pd.DataFrame(json.loads(get_text(CFTC.format(ds=TFF) + q.replace(" ", "%20").replace("'", "%27"))))
    num = lambda c: pd.to_numeric(raw[c], errors="coerce")
    df = pd.DataFrame({k: num(lo) - num(sh) for k, (lo, sh) in fields.items()})
    df.index = pd.to_datetime(raw["report_date_as_yyyy_mm_dd"])
    return df[~df.index.duplicated()].sort_index()


def build_vix_am(vix):
    df = cftc_series("1170E1", "2010-01-01", {"am": ("asset_mgr_positions_long", "asset_mgr_positions_short")})
    am = df["am"].dropna()
    thr = am.expanding(104).quantile(0.01)  # 1st percentile of all reports up to that week
    hit = am[(am <= thr) & thr.notna()]
    vix = vix.dropna()
    dots, ep, prev = [], 0, None
    for d, net in hit.items():
        if prev is None or (d - prev).days > 8:
            ep += 1
        prev = d
        rel = d + pd.Timedelta(days=3)  # Friday release of Tuesday positions
        i = vix.index.searchsorted(rel)
        if i >= len(vix):
            continue
        base = vix.iloc[i]
        fwd = {h: (r((vix.iloc[i + n] / base - 1) * 100) if i + n < len(vix) else None) for h, n in HORIZONS.items()}
        dots.append({"date": d.strftime("%Y-%m-%d"), "net": int(net), "episode": ep, "vix": r(base, 2), "fwd": fwd})
    stats = {}
    for h in HORIZONS:
        v = [x["fwd"][h] for x in dots if x["fwd"][h] is not None]
        firsts = {}
        for x in dots:
            if x["fwd"][h] is not None:
                firsts.setdefault(x["episode"], x["fwd"][h])
        stats[h] = {"median": r(np.median(v)) if v else None, "up": r(np.mean([x > 0 for x in v]) * 100) if v else None,
                    "n": len(v), "ep_up": sum(x > 0 for x in firsts.values()), "ep_n": len(firsts),
                    "worst": r(min(v)) if v else None}
    return {"date": am.index[-1].strftime("%Y-%m-%d"), "net": int(am.iloc[-1]), "thr": r(thr.iloc[-1], 0),
            "pct": r((am < am.iloc[-1]).mean() * 100, 1), "rank": int((am < am.iloc[-1]).sum()) + 1, "n": len(am),
            "chg": int(am.iloc[-1] - am.iloc[-2]), "episodes": ep, "dots": dots, "stats": stats,
            "hist": {"dates": [d.strftime("%Y-%m-%d") for d in am.index], "net": [int(x) for x in am],
                     "thr": [r(x, 0) for x in thr]}}


def build_vvix(px):
    end = px.index[-1]
    w = px[["^VIX", "^VVIX"]].dropna()
    w = w[w.index > end - pd.DateOffset(years=3)]
    b, a = np.polyfit(w["^VIX"], w["^VVIX"], 1)
    res = w["^VVIX"] - (a + b * w["^VIX"])
    pct = res.rank(pct=True) * 100
    return {"date": w.index[-1].strftime("%Y-%m-%d"), "vix": r(w["^VIX"].iloc[-1], 2), "vvix": r(w["^VVIX"].iloc[-1], 2),
            "fit": {"a": r(a, 3), "b": r(b, 3)}, "res": r(res.iloc[-1]), "res_pct": r(pct.iloc[-1], 0),
            "vvix_pct": r((w["^VVIX"] < w["^VVIX"].iloc[-1]).mean() * 100, 0),
            "vix_pct": r((w["^VIX"] < w["^VIX"].iloc[-1]).mean() * 100, 0),
            "pts": [[r(x, 2), r(y, 2)] for x, y in zip(w["^VIX"], w["^VVIX"])],
            "dates": [d.strftime("%Y-%m-%d") for d in w.index], "res_pct_hist": [r(x, 0) for x in pct],
            "res_hist": [r(x, 2) for x in res]}  # the intraday tab ranks a live reading against these


def build_vix_beta(px):
    end = px.index[-1]
    w = pd.DataFrame({"spx": px["^GSPC"].pct_change() * 100, "dvix": px["^VIX"].diff()}).dropna()
    w = w[w.index > end - pd.DateOffset(years=2)]
    b, a = np.polyfit(w["spx"], w["dvix"], 1)
    res = w["dvix"] - (a + b * w["spx"])
    z = res / res.std()
    last = w.iloc[-10:]
    return {"date": w.index[-1].strftime("%Y-%m-%d"), "fit": {"a": r(a, 3), "b": r(b, 3)},
            "pts": [[r(x, 2), r(y, 2)] for x, y in zip(w["spx"], w["dvix"])],
            "dates": [d.strftime("%Y-%m-%d") for d in w.index],
            "res_sd": r(res.std(), 3),
            "recent": [{"date": d.strftime("%Y-%m-%d"), "spx": r(x.spx, 2), "dvix": r(x.dvix, 2),
                        "res": r(res[d], 2), "z": r(z[d], 1), "pct": r((res.abs() < abs(res[d])).mean() * 100, 0)}
                       for d, x in last.iterrows()]}


def build_rvi(px):
    """The S&P's realised daily move against the move the VIX priced the evening before: realised = |SPX_t / SPX_t-1 - 1|,
    implied = VIX_t-1 / sqrt(252), both in %. A day above the diagonal moved more than options priced. Also the volatility
    risk premium: VIX minus one-month realised vol (negative = options cheaper than the moves being delivered)."""
    w = pd.DataFrame({"spx": px["^GSPC"], "vix": px["^VIX"]}).dropna()
    d = pd.DataFrame({"real": w["spx"].pct_change().abs() * 100, "imp": w["vix"].shift(1) / np.sqrt(252)}).dropna()
    above = d["real"] > d["imp"]
    ratio = d["real"] / d["imp"]
    rv21 = np.log(w["spx"]).diff().rolling(21).std() * np.sqrt(252) * 100
    vrp = (w["vix"] - rv21).dropna()
    v3 = vrp[vrp.index > vrp.index[-1] - pd.DateOffset(years=3)]
    a20 = above.rolling(20).sum()
    last = d.index[-1]
    return {"date": last.strftime("%Y-%m-%d"), "real": r(d["real"].iloc[-1], 2), "imp": r(d["imp"].iloc[-1], 2),
            "ratio": r(ratio.iloc[-1], 2), "ratio_pct": r((ratio < ratio.iloc[-1]).mean() * 100, 0),
            "share_above": r(above.mean() * 100, 1), "n": len(d), "above_20": int(a20.iloc[-1]),
            "above_20_avg": r(a20.mean(), 1), "above_20_pct": r((a20.dropna() < a20.iloc[-1]).mean() * 100, 0),
            "vrp": r(vrp.iloc[-1], 1), "vrp_pct3y": r((v3 < v3.iloc[-1]).mean() * 100, 0),
            "pts": [[r(x, 2), r(y, 2)] for x, y in zip(d["real"], d["imp"])],
            "dates": [x.strftime("%Y-%m-%d") for x in d.index],
            "vrp_hist": {"dates": [x.strftime("%Y-%m-%d") for x in vrp.index[vrp.index >= "2010-01-01"]],
                         "vrp": [r(x, 1) for x in vrp[vrp.index >= "2010-01-01"]],
                         "above_20": [None if pd.isna(x) else int(x) for x in a20.reindex(vrp.index)[vrp.index >= "2010-01-01"]]}}


def build_vol():
    px = yclose(["^VIX", "^VVIX", "^GSPC"], "2000-01-01")
    out = {"vix_am": build_vix_am(px["^VIX"]), "vvix": build_vvix(px), "beta": build_vix_beta(px), "rvi": build_rvi(px)}
    write("vol", out)
    return out["vvix"]["date"]


# =====================================================================================================================
# 6. Non-dealer net position in S&P and Nasdaq futures, in dollars
# =====================================================================================================================
NONDEALER = {"13874A": ("標普500 E-mini", "^GSPC", 50), "209742": ("納指100 E-mini", "^NDX", 20)}
ND_FIELDS = {"am": ("asset_mgr_positions_long", "asset_mgr_positions_short"),
             "lev": ("lev_money_positions_long", "lev_money_positions_short"),
             "other": ("other_rept_positions_long", "other_rept_positions_short")}


def build_nondealer():
    idx = yclose([v[1] for v in NONDEALER.values()], "2019-06-01")
    out = []
    for code, (name, tk, mult) in NONDEALER.items():
        df = cftc_series(code, "2020-01-01", ND_FIELDS)
        px = idx[tk].dropna()
        price = px.reindex(df.index, method="ffill")
        net = df.sum(axis=1)
        usd = net * mult * price / 1e9
        y1 = usd[usd.index > usd.index[-1] - pd.DateOffset(years=1)]
        # the cash index over the same report week (Tuesday close to Tuesday close), to set the position change beside it
        week = {"px": r(price.iloc[-1], 2), "px_prev": r(price.iloc[-2], 2), "px_prev_date": df.index[-2].strftime("%Y-%m-%d"),
                "px_chg": r((price.iloc[-1] / price.iloc[-2] - 1) * 100, 2)}
        out.append({"code": code, "name": name, "date": df.index[-1].strftime("%Y-%m-%d"), **week, "contracts": int(net.iloc[-1]),
                    "usd": r(usd.iloc[-1]), "chg": r(usd.iloc[-1] - usd.iloc[-2]), "chg4": r(usd.iloc[-1] - usd.iloc[-5]),
                    "pct_all": r((usd < usd.iloc[-1]).mean() * 100, 0), "pct_1y": r((y1 < y1.iloc[-1]).mean() * 100, 0),
                    "parts": {k: r(df[k].iloc[-1] * mult * price.iloc[-1] / 1e9) for k in ND_FIELDS},
                    "hist": {"dates": [d.strftime("%Y-%m-%d") for d in usd.index], "usd": [r(x) for x in usd]}})
    write("nondealer", out)
    return max(x["date"] for x in out)


# =====================================================================================================================
# 7. Key levels, expected ranges, option walls, leveraged-ETF rebalancing, the volatility strip
# =====================================================================================================================
LEVEL_MARKETS = {"NQ": ("納指100 期貨", "NQ=F", "QQQ", "^VXN"), "ES": ("標普500 期貨", "ES=F", "SPY", "^VIX")}
# (ticker, daily leverage). Rebalance at the close = L x (L - 1) x assets x the day's return: always with the market.
LEV_ETFS = {"nq": [("TQQQ", 3), ("SQQQ", -3), ("QLD", 2), ("QID", -2), ("PSQ", -1)],
            "spx": [("UPRO", 3), ("SPXL", 3), ("SPXU", -3), ("SPXS", -3), ("SSO", 2), ("SDS", -2), ("SH", -1)],
            "chips": [("SOXL", 3), ("SOXS", -3), ("USD", 2), ("SSG", -2)]}
WATCH_EARNINGS = ["NVDA", "CRWV", "NBIS", "ORCL", "CSCO", "AMAT", "AVGO", "MU", "AMD"]
VOL_STRIP = ["^VIX1D", "^VIX", "^VIX9D", "^VIX3M", "^VXN", "^VVIX"]  # VIX1D: Cboe one-day index (next session only)
CASH = ["^GSPC", "SPY"]  # closes the next-session S&P range is given in, beside ES
VOL_START = "2023-01-01"  # VIX1D starts 2023-04-24 on Yahoo
WALL_DAYS, WALL_RANGE = 35, 0.12  # open interest of expiries within 35 days, strikes within 12% of spot


def ybars(ticker, period="2y"):
    d = yf.download(ticker, period=period, auto_adjust=False, progress=False)
    out = pd.DataFrame({k: d[k].squeeze() for k in ("High", "Low", "Close")}).dropna(subset=["Close"])
    out.index = pd.to_datetime(out.index).tz_localize(None)
    return completed(out)


def option_read(etf):
    """The strikes with the most open interest and at-the-money straddles from Yahoo's option chain, relative to the
    ETF's last completed close. Yahoo sometimes serves the chain with every open interest at 0 (not yet updated): then
    no strike is listed, since the top two would be arbitrary."""
    t = yf.Ticker(etf)
    hist = t.history(period="10d")["Close"]
    hist.index = pd.to_datetime(hist.index).tz_localize(None)
    spot = float(completed(hist).iloc[-1])  # the same session as the futures close it is scaled to
    today = pd.Timestamp.today().normalize()
    exps = [e for e in t.options if 0 <= (pd.Timestamp(e) - today).days <= WALL_DAYS]
    puts, calls, straddles = {}, {}, []
    for e in exps:
        ch = t.option_chain(e)
        for book, df in ((puts, ch.puts), (calls, ch.calls)):
            for k, oi in zip(df["strike"], df["openInterest"]):
                if abs(k / spot - 1) <= WALL_RANGE and oi == oi:
                    book[float(k)] = book.get(float(k), 0) + int(oi)
        d = pd.Timestamp(e)
        if d.dayofweek == 4 and (d - today).days >= 3 and len(straddles) < 2:
            k = ch.calls["strike"].iloc[(ch.calls["strike"] - spot).abs().argmin()]
            c, p = ch.calls[ch.calls["strike"] == k].iloc[0], ch.puts[ch.puts["strike"] == k].iloc[0]
            val = lambda o: (o["bid"] + o["ask"]) / 2 if o["bid"] > 0 and o["ask"] > 0 else o["lastPrice"]
            straddles.append({"expiry": e, "pct": r((val(c) + val(p)) / spot * 100, 2)})
    top = lambda book, keep: sorted(((k, v) for k, v in book.items() if keep(k) and v > 0), key=lambda x: -x[1])[:2]
    oi_total = sum(puts.values()) + sum(calls.values())
    if exps and not oi_total:
        warn(f"Option chain {etf}: Yahoo shows open interest 0 on every strike; open-interest strikes not listed")
    return {"spot": spot, "puts": top(puts, lambda k: k <= spot * 1.01), "calls": top(calls, lambda k: k >= spot * 0.99),
            "straddles": straddles, "expiries": len(exps), "oi_total": oi_total}


def merge_levels(rows, dp=0.03):
    """Levels within dp% of each other are one level; their labels are joined."""
    rows = sorted(rows, key=lambda x: -x["price"])
    out = []
    for x in rows:
        if out and abs(out[-1]["price"] / x["price"] - 1) * 100 < dp:
            out[-1]["label"] += "／" + x["label"]
            for side in ("up", "down"):
                if out[-1][side] == "—":
                    out[-1][side] = x[side]
                elif x[side] != "—" and x[side] not in out[-1][side]:
                    out[-1][side] += "；" + x[side]
            if x["kind"] == "cta":
                out[-1]["kind"] = "cta"
        else:
            out.append(dict(x))
    return out


def price_levels(b, ma=(50, 200)):
    """Reference prices only: no model trades on them and none is tested, so the text states the fact and nothing
    more (no support, resistance or "lost" wording)."""
    c, h, l = b["Close"], b["High"], b["Low"]
    d0, d1 = b.index[-1].strftime("%m-%d"), b.index[-2].strftime("%m-%d")
    rows = [("price", f"{d0} 高位", h.iloc[-1], "—", "—"),
            ("price", f"{d0} 低位", l.iloc[-1], "—", "—"),
            ("price", f"{d1} 收市", c.iloc[-2], "—", "—"),
            ("price", f"{d1} 低位", l.iloc[-2], "—", "—"),
            ("price", "20 日高位", h.iloc[-20:].max(), "收市高於此價即 20 日新高", "—"),
            ("price", "20 日低位", l.iloc[-20:].min(), "—", "收市低於此價即 20 日新低")]
    for n in ma:
        v = c.rolling(n).mean().iloc[-1]
        rows.append(("ma", f"{n} 日線", v, "—", "—"))
    return [{"kind": k, "label": a, "price": r(v, 2), "up": u, "down": w} for k, a, v, u, w in rows]


def build_levels():
    cta = {m["key"]: m for m in json.loads((DATA / "cta.json").read_text())["markets"]}
    closes = yclose(sorted(set(VOL_STRIP) | set(CASH)), VOL_START)
    strip = {}
    for t in VOL_STRIP:
        s = closes[t].dropna() if t in closes else pd.Series(dtype=float)
        s = completed(s)
        if len(s) >= 2:
            y = s[s.index > s.index[-1] - pd.DateOffset(years=1)]
            strip[t] = {"last": r(s.iloc[-1], 2), "prev": r(s.iloc[-2], 2), "date": s.index[-1].strftime("%Y-%m-%d"),
                        "pct1y": r((y < y.iloc[-1]).mean() * 100, 0) if len(y) >= 120 else None,
                        "hi1y": r(y.max(), 2), "lo1y": r(y.min(), 2), "med1y": r(y.median(), 2), "n1y": len(y),
                        "since": s.index[0].strftime("%Y-%m-%d")}
        else:
            warn(f"Volatility strip: {t} has no usable history")
    cash = {}
    for t in CASH:
        s = closes[t].dropna() if t in closes else pd.Series(dtype=float)
        if len(s) >= 2:
            cash[t] = {"close": r(s.iloc[-1], 2), "date": s.index[-1].strftime("%Y-%m-%d"),
                       "chg": r((s.iloc[-1] / s.iloc[-2] - 1) * 100, 2)}
        else:
            warn(f"Close {t} missing: next-session range shown without it")
    # the S&P's realised close-to-close move against VIX1D / sqrt(252) at the close before (R33's forecast)
    d1rv = None
    if "^GSPC" in closes and "^VIX1D" in closes:
        spx = closes["^GSPC"].dropna()
        w = pd.DataFrame({"move": spx.pct_change() * 100,
                          "imp": closes["^VIX1D"].reindex(spx.index).shift(1) / np.sqrt(252)}).dropna()
        if len(w) >= 21:
            above = w["move"].abs() > w["imp"]
            a20 = above.rolling(20).sum().dropna()
            d1rv = {"date": w.index[-1].strftime("%Y-%m-%d"), "prev_date": spx.index[spx.index < w.index[-1]][-1].strftime("%Y-%m-%d"),
                    "move": r(w["move"].iloc[-1], 2), "real": r(abs(w["move"].iloc[-1]), 2), "imp": r(w["imp"].iloc[-1], 2),
                    "above_20": int(a20.iloc[-1]), "above_20_avg": r(a20.mean(), 1), "since": w.index[0].strftime("%Y-%m-%d"),
                    "n": len(w)}
    if d1rv is None:
        warn("VIX1D realised-vs-implied: not enough ^GSPC / ^VIX1D history")
    gap = (closes["^VXN"] - closes["^VIX"]).dropna()
    gap = gap[gap.index > gap.index[-1] - pd.DateOffset(years=1)]

    markets = {}
    for key, (name, ticker, etf, volx) in LEVEL_MARKETS.items():
        b = ybars(ticker)
        close = float(b["Close"].iloc[-1])
        m = cta[key]
        rows = price_levels(b)
        # flip per horizon: tomorrow's return over k sessions is zero at the close k-1 sessions before today
        hz = [{"k": k, "level": r(b["Close"].iloc[-k], 2), "pos": "LONG" if close > b["Close"].iloc[-k] else "SHORT"}
              for k in LOOKBACKS]
        for x in hz:
            others = sum(o["pos"] == "SHORT" for o in hz if o["k"] != x["k"])
            rows.append({"kind": "cta", "label": f"CTA {x['k']} 日翻轉價", "price": x["level"],
                         "up": f"收市升穿：{x['k']} 日訊號轉 long", "down":
                         f"收市跌穿：{x['k']} 日訊號轉 short" + ("，三個週期全部 short" if others == 2 else "")})
        if m.get("flip_level") is not None:
            rows.append({"kind": "cta", "label": "CTA 綜合翻轉價", "price": r(m["flip_level"], 2),
                         "up": "收市高於此價：模型為 long（買方）", "down": "收市低於此價：模型為 short（賣方）"})
        opt = None
        try:
            opt = option_read(etf)
            ratio = close / opt["spot"]
            note = f"35 日內到期合約的未平倉分佈（{opt['spot']:.2f} 為 {etf} 收市），不是支持或阻力"
            for side, book in (("put", opt["puts"]), ("call", opt["calls"])):
                for k, oi in book:
                    rows.append({"kind": "option", "label": f"{etf} {k:g} {side} 未平倉最多（{oi:,} 張）",
                                 "price": r(k * ratio, 2), "up": note, "down": note})
        except Exception as e:
            warn(f"Option chain {etf} failed: {e}")
        rng = lambda p: None if p is None else [r(close * (1 - p / 100), 0), r(close * (1 + p / 100), 0)]
        ranges = []
        # the S&P's next session: VIX1D only (R33: lower error than VIX); Nasdaq has no one-day index, so VXN
        one_day = (("^VIX1D", "VIX1D ÷ √252：只計下一交易日"),) if volx == "^VIX" else \
                  ((volx, f"{volx[1:]} ÷ √252：未來 30 日平均折算一日"),)
        for t, basis in one_day:
            x = strip.get(t)
            if x:
                p = r(x["last"] / np.sqrt(252), 2)
                ranges.append({"label": "下一交易日", "kind": "sd", "basis": basis, "src": t[1:], "level": x["last"],
                               "date": x["date"], "pct": p, "pts": r(close * p / 100, 0), "range": rng(p)})
        for x in (opt or {}).get("straddles", []):
            ranges.append({"label": f"至 {x['expiry'][5:]}", "kind": "straddle", "basis": f"{etf} 平價跨式價格",
                           "pct": x["pct"], "range": rng(x["pct"])})
        lv = [x for x in merge_levels(rows) if abs(x["price"] / close - 1) <= 0.13]
        markets[key] = {"name": name, "ticker": ticker, "date": b.index[-1].strftime("%Y-%m-%d"), "close": r(close, 2),
                        "chg": r((close / b["Close"].iloc[-2] - 1) * 100, 2), "chg_5d": r((close / b["Close"].iloc[-6] - 1) * 100, 2),
                        "date_5d": b.index[-6].strftime("%Y-%m-%d"), "levels": lv, "horizons": hz, "ranges": ranges}

    v = ybars("^VIX")
    vc_ = float(v["Close"].iloc[-1])
    vlv = [x for x in price_levels(v, ma=(20, 50)) if "低位" not in x["label"] or x["label"].startswith(v.index[-1].strftime("%m-%d"))]
    y = v[v.index > v.index[-1] - pd.DateOffset(years=1)]
    vlv.append({"kind": "price", "label": "一年高位", "price": r(y["High"].max(), 2), "up": "收市高於此價即一年新高", "down": "—"})
    vlv = [x for x in merge_levels(vlv, dp=0.2) if 0.6 <= x["price"] / vc_ <= 1.6]
    markets["VIX"] = {"name": "VIX", "ticker": "^VIX", "date": v.index[-1].strftime("%Y-%m-%d"), "close": r(vc_, 2),
                      "chg": r(vc_ - v["Close"].iloc[-2], 2), "chg_5d": r(vc_ - v["Close"].iloc[-6], 2),
                      "date_5d": v.index[-6].strftime("%Y-%m-%d"), "levels": vlv}

    etf = {}
    for group, funds in LEV_ETFS.items():
        rows, total = [], 0.0
        for t, lev in funds:
            try:
                aum = yf.Ticker(t).info.get("totalAssets")
            except Exception:
                aum = None
            if not aum:
                warn(f"Leveraged ETF {t}: no assets figure")
                continue
            per1 = lev * (lev - 1) * aum / 1e9 / 100  # $bn sold per 1% fall
            total += per1
            rows.append({"t": t, "lev": lev, "aum": r(aum / 1e9, 1), "per1": r(per1, 2)})
        etf[group] = {"funds": rows, "per1": r(total, 2)}
    sx, nd = ybars("^SOX", "1y")["Close"], ybars("^NDX", "1y")["Close"]
    both = pd.concat([sx.pct_change(), nd.pct_change()], axis=1).dropna().iloc[-60:]
    beta = float(np.cov(both.iloc[:, 0], both.iloc[:, 1])[0, 1] / both.iloc[:, 1].var())

    earnings, today = [], pd.Timestamp.today().normalize()
    for t in WATCH_EARNINGS:
        try:
            ds = yf.Ticker(t).calendar.get("Earnings Date") or []
        except Exception:
            ds = []
        for d in ds[:1]:
            if 0 <= (pd.Timestamp(d) - today).days <= 21:
                earnings.append({"t": t, "date": str(d)})
    earnings.sort(key=lambda x: x["date"])

    write("levels", {"markets": markets, "strip": strip, "cash": cash, "vix1d_rv": d1rv, "vxn_vix": {"last": r(gap.iloc[-1], 2), "median1y": r(gap.median(), 2)},
                     "etf": etf, "sox_beta": r(beta, 2), "earnings": earnings})
    log_path = DATA / "level_log.json"
    log = json.loads(log_path.read_text()) if log_path.exists() else {}
    log[markets["NQ"]["date"]] = {k: {"close": x["close"], "levels": [[l["price"], l["label"]] for l in x["levels"]]}
                                  for k, x in markets.items()}
    write("level_log", log)
    return markets["NQ"]["date"]


def main():
    dates = {}
    for name, fn in (("cftc", build_cftc), ("cta", build_cta), ("vc", build_vc), ("vol", build_vol),
                     ("nondealer", build_nondealer), ("levels", build_levels)):
        print(f"building {name} …", flush=True)
        try:
            dates[name] = fn()
        except Exception as e:
            warn(f"{name} module failed, previous file kept: {e}")
    write("meta", {"built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "dates": dates,
                   "warnings": WARN})
    print("done", dates, f"{len(WARN)} warnings")


if __name__ == "__main__":
    main()
