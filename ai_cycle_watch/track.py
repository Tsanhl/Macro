"""AI cycle watch: which layer of the AI build-out is compressing, and in what order?

Market side of the weekly AI-cycle tracker (rulebook §9a "AI capex cycle, staged exit" and the §13 entry dated
2026-10-13 "five-layer compression order"). The fundamental signals (capex, cloud growth, memory margins, CFO
language, credit) are filled in by the weekly task in signals.md; this script only measures prices.

Layers, in the order the framework expects them to compress (first → last):
  5 memory            MU, SNDK, WDC, STX, SK Hynix, Samsung
  4 custom/interconn. MRVL, AVGO, CRDO, ALAB
  3 optical/network   COHR, LITE, AAOI, CIEN, ANET, NOK
  2 chip IP           ARM, CDNS, SNPS (royalty and licence models; CDNS/SNPS added by us as the same long-lag type)
  1 power/on-site     GEV, BE, VRT, ETN, PWR
Outside the layers: neoclouds (CRWV, NBIS, IREN, APLD, DOCN), the spenders (MSFT, AMZN, GOOGL, META, ORCL) and
the financing layer (alt managers BX, KKR, APO, ARES, OWL; BDC ETF BIZD; HYG/IEF).

Layer state (our trial thresholds, untested):
  正常 drawdown from the 52-week high shallower than −10%
  回調 −10% to −20%
  壓縮 −20% or deeper AND 13-week return behind SPY

Writes data/latest.json and data/report.md, and keeps one row per session in data/history.json so a daily run can
say which layer changed state since the previous session (user, 2026-10-15: the evening task runs it every weekday;
the weekly task still owns the fundamental signals). Usage: python3 ai_cycle_watch/track.py
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

HERE = Path(__file__).resolve().parent
OUT = HERE / "data"

LAYERS = {  # key: (label, expected compression rank 1 = first, tickers)
    "L5_MEM": ("第五層 記憶體", 1, ["MU", "SNDK", "WDC", "STX", "000660.KS", "005930.KS"]),
    "L4_ASIC": ("第四層 互連與定制晶片", 2, ["MRVL", "AVGO", "CRDO", "ALAB"]),
    "L3_OPT": ("第三層 光模組與網絡", 3, ["COHR", "LITE", "AAOI", "CIEN", "ANET", "NOK"]),
    "L2_IP": ("第二層 晶片 IP", 4, ["ARM", "CDNS", "SNPS"]),
    "L1_PWR": ("第一層 電力與現場發電", 5, ["GEV", "BE", "VRT", "ETN", "PWR"]),
}
OTHER = {
    "NEO": ("新雲（純租賃）", ["CRWV", "NBIS", "IREN", "APLD", "DOCN"]),
    "SPEND": ("超大型雲端（付款方）", ["MSFT", "AMZN", "GOOGL", "META", "ORCL"]),
    "ALT": ("私募信貸管理人", ["BX", "KKR", "APO", "ARES", "OWL"]),
    "BDC": ("BDC（BIZD）", ["BIZD"]),
}
BENCH = ["SPY", "SMH", "HYG", "IEF"]


def ew_index(close, tickers):
    """Equal-weight index of daily returns, rebased to 1; skips members with no data."""
    have = [t for t in tickers if t in close and close[t].dropna().size > 260]
    rets = close[have].pct_change(fill_method=None)
    return (1 + rets.mean(axis=1, skipna=True).fillna(0)).cumprod(), have


def ret(s, n):
    s = s.dropna()
    return round((s.iloc[-1] / s.iloc[-1 - n] - 1) * 100, 1) if len(s) > n else None


def dd(s):
    s = s.dropna().iloc[-252:]
    return round((s.iloc[-1] / s.max() - 1) * 100, 1)


def snapshot(close):
    """Each layer's state and drawdown on the last row of close (the same rules as main), for the daily history."""
    spy = close["SPY"]
    states, dds = {}, {}
    for k, (_, *rest) in {**LAYERS, **OTHER}.items():
        idx, _ = ew_index(close, rest[-1])
        r13, d = ret(idx, 63), dd(idx)
        states[k] = "壓縮" if d <= -20 and r13 is not None and r13 < ret(spy, 63) else "回調" if d <= -10 else "正常"
        dds[k] = d
    order = sorted(LAYERS, key=lambda k: dds[k])
    return {"asof": close.index[-1].date().isoformat(), "states": states, "dd52w": dds, "order": order}


def main():
    tickers = sorted({t for _, _, ts in LAYERS.values() for t in ts} | {t for _, ts in OTHER.values() for t in ts}
                     | set(BENCH))
    df = yf.download(tickers, period="2y", interval="1d", auto_adjust=True, progress=False, threads=True)
    close = df["Close"].ffill()  # Korean listings trade on other days; carry the last close
    if close.empty or "SPY" not in close:
        sys.exit("price download failed")
    # US sessions only: a Korean session would otherwise add a row with SPY carried forward. Before the US close,
    # leave out today's unfinished bar (or a Korea-only row for today).
    us_days = df["Close"]["SPY"].dropna().index
    now_et = pd.Timestamp.now(tz="America/New_York")
    if len(us_days) and us_days[-1].date() == now_et.date() and (now_et.hour, now_et.minute) < (16, 30):
        us_days = us_days[:-1]
    full = close.loc[close.index.isin(us_days)]
    hist_path = OUT / "history.json"
    hist = json.loads(hist_path.read_text()) if hist_path.exists() else []
    if not hist:  # first run: backfill 30 sessions so state changes have a start date
        for d in full.index[-31:-1]:
            hist.append(snapshot(full.loc[:d]))
    snap = snapshot(full)
    close = full
    asof = close.index[-1].date().isoformat()
    spy, smh = close["SPY"], close["SMH"]

    def row(label, tickers, rank=None):
        idx, have = ew_index(close, tickers)
        r13 = ret(idx, 63)
        d = dd(idx)
        state = "壓縮" if d <= -20 and r13 is not None and r13 < ret(spy, 63) else "回調" if d <= -10 else "正常"
        return {"label": label, "expected_rank": rank, "members": have, "missing": sorted(set(tickers) - set(have)),
                "r1w": ret(idx, 5), "r4w": ret(idx, 20), "r13w": r13,
                "rel4w_smh": round(ret(idx, 20) - ret(smh, 20), 1), "rel13w_spy": round(r13 - ret(spy, 63), 1),
                "dd52w": d, "state": state}

    layers = {k: row(lbl, ts, rk) for k, (lbl, rk, ts) in LAYERS.items()}
    other = {k: row(lbl, ts) for k, (lbl, ts) in OTHER.items()}
    # actual compression order: deepest drawdown first
    actual = sorted(layers, key=lambda k: layers[k]["dd52w"])
    for i, k in enumerate(actual, 1):
        layers[k]["actual_rank"] = i
    hyg_ief = close["HYG"] / close["IEF"]
    spreads = {
        "neo_minus_spend_4w": round(other["NEO"]["r4w"] - other["SPEND"]["r4w"], 1),
        "suppliers_minus_spend_4w": round(
            sum(layers[k]["r4w"] for k in layers) / len(layers) - other["SPEND"]["r4w"], 1),
        "hyg_ief_4w": ret(hyg_ief, 20),
        "alt_vs_spy_4w": round(other["ALT"]["r4w"] - ret(spy, 20), 1),
        "spy_4w": ret(spy, 20), "smh_4w": ret(smh, 20),
    }
    # previous session's states and when each current state began, from the daily history (one row per US session;
    # a rerun replaces its own row)
    OUT.mkdir(exist_ok=True)
    hist = sorted([h for h in hist if h["asof"] != asof] + [snap], key=lambda h: h["asof"])
    hist_path.write_text(json.dumps(hist, ensure_ascii=False, indent=1))
    prev = hist[-2] if len(hist) > 1 else None
    for k, v in {**layers, **other}.items():
        v["prev_state"] = (prev or {}).get("states", {}).get(k)
        since = asof
        for h in reversed(hist):
            if h["states"].get(k) != v["state"]:
                break
            since = h["asof"]
        v["since"] = since
    out = {"asof": asof, "built": datetime.now(timezone.utc).isoformat(timespec="minutes"),
           "prev_asof": prev["asof"] if prev else None, "actual_order": actual,
           "layers": layers, "other": other, "spreads": spreads,
           "order_matches_expected": actual == sorted(layers, key=lambda k: layers[k]["expected_rank"])}
    (OUT / "latest.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))

    lines = [f"# AI 週期分層讀數（價格截至 {asof}）", "",
             "| 層 | 預期壓縮次序 | 實際（按距高位） | 1週 | 4週 | 13週 | 4週 vs SMH | 13週 vs SPY | 距52週高位 | 狀態 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for k, v in layers.items():
        lines.append(f"| {v['label']} | {v['expected_rank']} | {v['actual_rank']} | {v['r1w']}% | {v['r4w']}% | "
                     f"{v['r13w']}% | {v['rel4w_smh']} | {v['rel13w_spy']} | {v['dd52w']}% | {v['state']} |")
    for v in other.values():
        lines.append(f"| {v['label']} | – | – | {v['r1w']}% | {v['r4w']}% | {v['r13w']}% | {v['rel4w_smh']} | "
                     f"{v['rel13w_spy']} | {v['dd52w']}% | {v['state']} |")
    s = spreads
    lines += ["", f"- 新雲減付款方（4週）：{s['neo_minus_spend_4w']} 個百分點；供應層平均減付款方：{s['suppliers_minus_spend_4w']}",
              f"- HYG/IEF 4週：{s['hyg_ief_4w']}%；私募信貸管理人 vs SPY 4週：{s['alt_vs_spy_4w']}",
              f"- 實際次序與預期{'一致' if out['order_matches_expected'] else '不一致'}"]
    miss = {v["label"]: v["missing"] for v in list(layers.values()) + list(other.values()) if v["missing"]}
    if miss:
        lines.append(f"- 缺數據：{miss}")
    (OUT / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
