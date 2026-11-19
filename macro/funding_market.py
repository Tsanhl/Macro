"""Funding market and credit ladder from FRED: SOFR minus IORB (the market's overnight Treasury repo rate against the
rate the Fed pays on bank reserves), Standing Repo Facility use, discount-window primary credit, and ICE BofA
option-adjusted spreads by rating (CCC and below, B, BB, BBB, investment grade) with three-year percentiles.

Facts only: no thresholds or lamps. SOFR normally sits a few basis points below IORB; month-end, quarter-end and
Treasury settlement days can lift it for a day or two, so the current run of sessions at +3bp or more is shown next to
the latest print, with the longest runs of the past three years. FRED posts SOFR the next morning and the discount
window weekly (Wednesday level). A failed fetch keeps the previous file and never stops the rest of the board build.
"""
import http.client
import json
import os
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent / "data"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}&cosd={}"
SERIES = {"sofr": "SOFR", "iorb": "IORB", "srf": "RPONTSYD", "dw": "WLCFLPCL",
          "ccc": "BAMLH0A3HYC", "b": "BAMLH0A2HYB", "bb": "BAMLH0A1HYBB", "bbb": "BAMLC0A4CBBB", "ig": "BAMLC0A0CM"}
LADDER = ["ccc", "b", "bb", "bbb", "ig"]  # weakest rating first
YEARS = 3
CHANGE_OBS = 20  # spread change over each series' own last 20 observations (about a month); both dates are kept
RUN_BP = 3  # SOFR at least this far above IORB counts toward a run


def fetch(series_id, start, tries=4):
    """{date: value} from FRED's CSV; '.' marks a missing day and is skipped."""
    req = urllib.request.Request(FRED.format(series_id, start), headers={"User-Agent": "curl/8.7.1"})
    for attempt in range(tries):
        try:
            text = urllib.request.urlopen(req, timeout=90).read().decode()
            break
        except (TimeoutError, OSError, http.client.HTTPException):
            if attempt == tries - 1:
                raise
            time.sleep(5 * (attempt + 1))
    out = {}
    for line in text.splitlines()[1:]:
        d, _, v = line.partition(",")
        try:
            out[d] = float(v)
        except ValueError:
            pass
    if not out:
        raise ValueError(f"{series_id}: no observations")
    return out


def fetch_all(today=None):
    start = ((today or date.today()) - timedelta(days=YEARS * 366 + 40)).isoformat()
    return {k: fetch(sid, start) for k, sid in SERIES.items()}


def pct(vals, x):
    return round(sum(v <= x for v in vals) / len(vals) * 100)


def runs(rows, bp=RUN_BP):
    """Stretches of consecutive sessions with SOFR at least bp above IORB."""
    out, cur = [], []
    for r in rows + [{"date": None, "bp": None}]:
        if r["bp"] is not None and r["bp"] >= bp:
            cur.append(r)
        elif cur:
            out.append({"start": cur[0]["date"], "end": cur[-1]["date"], "days": len(cur), "max_bp": max(x["bp"] for x in cur)})
            cur = []
    return out


def compute(raw):
    last = max(raw["sofr"])
    cut = (date.fromisoformat(last) - timedelta(days=YEARS * 365)).isoformat()

    spread = [{"date": d, "sofr": raw["sofr"][d], "iorb": raw["iorb"][d], "bp": round((raw["sofr"][d] - raw["iorb"][d]) * 100)}
              for d in sorted(raw["sofr"]) if d in raw["iorb"] and d >= cut]
    stretches = runs(spread)
    current = stretches[-1]["days"] if stretches and stretches[-1]["end"] == spread[-1]["date"] else 0
    longest = sorted(stretches, key=lambda r: (-r["days"], r["start"]))[:3]

    srf = sorted((d, v) for d, v in raw["srf"].items() if d >= cut)
    srf_year = [x for x in srf if x[0] >= (date.fromisoformat(srf[-1][0]) - timedelta(days=365)).isoformat()]
    srf_peak = max(srf_year, key=lambda x: x[1])
    dw = sorted((d, v) for d, v in raw["dw"].items() if d >= cut)

    ladder = []
    for k in LADDER:
        ser = sorted((d, v) for d, v in raw[k].items() if d >= cut)
        vals = sorted(v for _, v in ser)
        (d1, v1), (d0, v0) = ser[-1], ser[-1 - CHANGE_OBS]
        ladder.append({"id": k, "date": d1, "bp": round(v1 * 100), "prev_date": d0, "chg_bp": round((v1 - v0) * 100),
                       "pct3y": pct(vals, v1), "p90_bp": round(vals[int(len(vals) * 0.9)] * 100)})
    gap_days = [d for d in raw["ccc"] if d in raw["bb"] and d >= cut]
    gaps = [raw["ccc"][d] - raw["bb"][d] for d in gap_days]
    gd = max(gap_days)
    gap = {"date": gd, "pp": round(raw["ccc"][gd] - raw["bb"][gd], 2), "pct3y": pct(gaps, raw["ccc"][gd] - raw["bb"][gd])}

    return {"asof": spread[-1]["date"], "retrieved": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": "FRED: " + ", ".join(SERIES.values()), "run_bp": RUN_BP, "change_obs": CHANGE_OBS,
            "spread": spread, "run_now": current, "longest_runs": longest,
            "srf": {"date": srf[-1][0], "bn": srf[-1][1], "peak_date": srf_peak[0], "peak_bn": srf_peak[1]},
            "dw": {"date": dw[-1][0], "bn": round(dw[-1][1] / 1000, 2), "prev_date": dw[-2][0],
                   "prev_bn": round(dw[-2][1] / 1000, 2), "pct3y": pct([v for _, v in dw], dw[-1][1])},
            "ladder": ladder, "ccc_bb": gap}


def build_funding():
    try:
        doc = compute(fetch_all())
        tmp = OUT / "funding.json.tmp"
        tmp.write_text(json.dumps([doc], ensure_ascii=False, separators=(",", ":")))
        os.replace(tmp, OUT / "funding.json")
        print(f"  funding: SOFR−IORB {doc['spread'][-1]['bp']:+d}bp on {doc['asof']}, run {doc['run_now']}")
    except Exception as e:  # keep the previous file; the funding card shows its own dates
        print(f"  WARNING funding market failed, previous file kept: {e}")


if __name__ == "__main__":
    build_funding()
