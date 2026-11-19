"""Intraday snapshot for the 盤中 tab: live (Yahoo, delayed ~10–15 min) prices against the levels build.py set at the
last close. No AI calls.

Answers one question per signal: if the session closed at this price, what would happen?
  CTA          live futures/index price against each market's flip level (yield markets have no live quote: skipped)
  vol control  the S&P move so far, read off the flow curve
  VIX          the VIX move against the move the S&P implies (residual, in sd of the two-year fit)
  VVIX         VVIX against the VIX-level fit, ranked in its three-year residuals

The flip levels and the flow curve hold for the session after the board's last close. `board` in the reply says which
close the board should hold by now (from the S&P cash index's own bars, so market holidays are respected); when that
close is later than the board's, the board is stale and the page says so (press 更新數據 first).
"""
import json
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

DATA = Path(__file__).resolve().parent / "data"
TTL = 60  # seconds a snapshot is reused; Yahoo's quotes are delayed anyway
_cache = {"t": 0.0, "v": None}
_lock = threading.Lock()


def r(x, n=2):
    return None if x is None or pd.isna(x) else round(float(x), n)


def snapshot():
    with _lock:
        if _cache["v"] is None or time.time() - _cache["t"] > TTL:
            _cache["v"] = build()
            _cache["t"] = time.time()
        return _cache["v"]


def load(name):
    return json.loads((DATA / f"{name}.json").read_text())


def last_quotes(tickers):
    """Latest one-minute close per ticker, with its time (New York)."""
    df = yf.download(tickers, period="2d", interval="1m", prepost=True, auto_adjust=False, progress=False,
                     threads=True)["Close"]
    if isinstance(df, pd.Series):
        df = df.to_frame(tickers[0])
    df.index = pd.to_datetime(df.index)
    df.index = (df.index.tz_localize("UTC") if df.index.tz is None else df.index).tz_convert("America/New_York")
    out = {}
    for t in tickers:
        s = df[t].dropna() if t in df else pd.Series(dtype=float)
        if len(s):
            out[t] = (float(s.iloc[-1]), s.index[-1])
    return out


def prev_close(ticker, day):
    """The last daily close before `day` (a New York date)."""
    d = yf.download(ticker, period="15d", interval="1d", auto_adjust=False, progress=False)["Close"].squeeze().dropna()
    d.index = pd.to_datetime(d.index).tz_localize(None)
    d = d[d.index.date < day]
    return (float(d.iloc[-1]), d.index[-1].date()) if len(d) else (None, None)


def session_of(ts):
    """The trading session a New York timestamp belongs to: futures trading after 18:00 counts toward the next day."""
    d = ts.tz_localize(None) + pd.Timedelta(hours=6)
    return (d + pd.offsets.BDay(0)).date() if d.dayofweek >= 5 else d.date()


def build():
    cta, vc, vol = load("cta"), load("vc"), load("vol")
    markets = [m for m in cta["markets"] if m.get("ticker") and m.get("flip_level") is not None]
    idx = ["^GSPC", "^VIX", "^VVIX"]
    q = last_quotes(sorted({m["ticker"] for m in markets} | set(idx)))
    now = pd.Timestamp.now(tz="Europe/London")
    board_next = (pd.Timestamp(cta["markets"][0]["date"]) + pd.offsets.BDay(1)).date() if cta["markets"] else None

    rows = []
    for m in markets:
        if m["ticker"] not in q:
            continue
        px, ts = q[m["ticker"]]
        lvl, long_ = m["flip_level"], m["pos"] == "LONG"
        dist = (lvl / px - 1) * 100  # % move from here to the flip
        sd_pct = abs(m["flip_move"] / m["flip_sd"]) if m.get("flip_sd") and m.get("flip_move") else None
        crossed = px <= lvl if long_ else px >= lvl
        rows.append({"key": m["key"], "name": m["name"], "group": m["group"], "pos": m["pos"], "sig": m["sig"],
                     "live": r(px, 4), "time": ts.tz_convert("Europe/London").strftime("%m-%d %H:%M"),
                     "chg": r((px / m["last"] - 1) * 100), "flip_level": lvl, "dist": r(dist),
                     "dist_sd": r(abs(dist) / sd_pct, 2) if sd_pct else None, "crossed": bool(crossed),
                     "flat_flip": m.get("flat", m.get("flip_sd") == 0),  # flips even on an unchanged close
                     "session": str(session_of(ts)),  # the page uses a live price only for a session after the board's
                     "stale": bool(board_next and session_of(ts) > board_next)})
    rows.sort(key=lambda x: (not x["crossed"], x["dist_sd"] if x["dist_sd"] is not None else 99))

    out = {"asof": now.strftime("%Y-%m-%d %H:%M"), "board_date": cta["markets"][0]["date"] if cta["markets"] else None,
           "cta": rows, "skipped": [m["name"] for m in cta["markets"] if m.get("yield")]}

    if "^GSPC" in q:
        spx, ts = q["^GSPC"]
        day = ts.date()
        pc, pc_day = prev_close("^GSPC", day)
        move = (spx / pc - 1) * 100
        c = vc["curve"]
        flow = float(np.interp(move, [x["move"] for x in c], [x["flow"] for x in c]))
        out["spx"] = {"live": r(spx), "prev": r(pc), "prev_day": str(pc_day), "move": r(move),
                      "sigma": r(move / vc["sigma"], 1), "flow": r(flow, 1), "off_curve": abs(move) > 5,
                      "time": ts.tz_convert("Europe/London").strftime("%m-%d %H:%M"),
                      # live: today's move against the close the board is built on; done: this session is already
                      # in the board (the cash market has closed); stale: the board misses a close
                      "state": "done" if str(day) == vc["date"] else "live" if str(pc_day) == vc["date"] else "stale"}
        # the close the board should hold by now: the S&P cash session of the latest quote once it has ended
        # (16:15 New York, as build.py), otherwise the session before it. Holiday-proof: both come from Yahoo's bars.
        ny = pd.Timestamp.now(tz="America/New_York")
        ended = ny.date() > day or ny.hour * 60 + ny.minute >= 16 * 60 + 15
        last_close = day if ended else pc_day
        board = out["board_date"]
        if board and last_close:
            out["board"] = {"date": board, "last_close": str(last_close), "in_session": not ended,
                            "stale": str(last_close) > board}
        if "^VIX" in q:
            vix, vts = q["^VIX"]
            pv, _ = prev_close("^VIX", vts.date())
            b = vol["beta"]
            dv = vix - pv
            exp = b["fit"]["a"] + b["fit"]["b"] * move
            res = dv - exp
            hist = np.abs([p[1] - (b["fit"]["a"] + b["fit"]["b"] * p[0]) for p in b["pts"]])
            out["vix"] = {"live": r(vix), "prev": r(pv), "chg": r(dv), "expected": r(exp), "res": r(res),
                          "z": r(res / b["res_sd"], 1), "pct": r((hist < abs(res)).mean() * 100, 0),
                          "time": vts.tz_convert("Europe/London").strftime("%m-%d %H:%M")}
    if "^VVIX" in q and "^VIX" in q:
        vvix, wts = q["^VVIX"]
        vix = q["^VIX"][0]
        f = vol["vvix"]["fit"]
        res = vvix - (f["a"] + f["b"] * vix)
        hist = np.array(vol["vvix"]["res_hist"], dtype=float)
        out["vvix"] = {"live": r(vvix), "vix": r(vix), "res": r(res, 1), "pct": r((hist < res).mean() * 100, 0),
                       "time": wts.tz_convert("Europe/London").strftime("%m-%d %H:%M")}
    return out
