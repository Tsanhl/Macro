"""US Treasury coupon auction results (2/3/5/7/10/20/30-year nominal) from TreasuryDirect: the high yield and price
each auction cleared at, and who took the competitive awards (indirect, direct, primary dealers). The Fed's rollover
of maturing holdings (SOMA) is added on top of the offering amount, so it is shown apart and not in the shares.

TreasuryDirect posts results the same afternoon (the Fiscal Data copy lags until the issue date). The tail needs the
when-issued yield at 1pm, which no official source publishes, so it is not calculated. A failed fetch keeps the
previous file and never stops the rest of the board build.
"""
import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent / "data"
SOURCE = "https://www.treasurydirect.gov/TA_WS/securities/auctioned?format=json&type={kind}&days={days}"
TERMS = {"2-Year": "2Y", "3-Year": "3Y", "5-Year": "5Y", "7-Year": "7Y", "10-Year": "10Y", "20-Year": "20Y", "30-Year": "30Y"}
DAYS = 760  # about two years of auctions


def num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v


def fetch(kind, tries=3):
    req = urllib.request.Request(SOURCE.format(kind=kind, days=DAYS), headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(tries):
        try:
            return json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(3 * (attempt + 1))


def parse(rec):
    """One auction as a board row, or None for TIPS, FRNs, other terms and auctions without results yet."""
    term = TERMS.get(rec.get("originalSecurityTerm"))
    if not term or rec.get("inflationProtected") == "Yes" or rec.get("floatingRate") == "Yes":
        return None
    date = (rec.get("auctionDate") or rec.get("competitiveAuctionCloseDate") or "")[:10]
    hy, btc = num(rec.get("highYield")), num(rec.get("bidToCoverRatio"))
    dealer = num(rec.get("primaryDealersCompetitiveParAwarded"))
    direct = num(rec.get("directBiddersCompetitiveParAwarded"))
    indirect = num(rec.get("indirectBiddersCompetitiveParAwarded"))
    if not date or hy is None or btc is None or None in (dealer, direct, indirect):
        return None
    comp = dealer + direct + indirect
    if comp <= 0:
        return None
    soma = num(rec.get("somaNoncompetitiveParAwarded")) or num(rec.get("somaAccepted")) or 0.0
    share = lambda v: round(v / comp * 100, 1)
    return {"date": date, "term": term, "reopening": rec.get("reopening") == "Yes", "cusip": rec.get("cusip"),
            "high_yield": round(hy, 3), "high_price": num(rec.get("highPrice")), "bid_to_cover": round(btc, 2),
            "offering_bn": round((num(rec.get("offeringAmount")) or 0) / 1e9, 1),
            "indirect_pct": share(indirect), "direct_pct": share(direct), "dealer_pct": share(dealer),
            "soma_bn": round(soma / 1e9, 2)}


def with_history(rows):
    """Add the change from the previous auction of the same term and the prior six auctions' averages."""
    rows = sorted(rows, key=lambda r: (r["date"], r["term"]))
    seen = {}
    for r in rows:
        prior = seen.setdefault(r["term"], [])
        last6 = prior[-6:]
        r["chg_bp"] = round((r["high_yield"] - prior[-1]["high_yield"]) * 100, 1) if prior else None
        r["prev_date"] = prior[-1]["date"] if prior else None
        avg = lambda k: round(sum(p[k] for p in last6) / len(last6), 2) if len(last6) == 6 else None
        r["btc_avg6"], r["indirect_avg6"] = avg("bid_to_cover"), avg("indirect_pct")
        r["direct_avg6"], r["dealer_avg6"] = avg("direct_pct"), avg("dealer_pct")
        prior.append(r)
    return rows


def build_auctions():
    try:
        recs = fetch("Note") + fetch("Bond")
        rows = [r for r in (parse(x) for x in recs) if r]
        keys = {(r["date"], r["cusip"]) for r in rows}
        if len(keys) != len(rows):
            raise ValueError("duplicate auction rows")
        if not rows:
            raise ValueError("no auction results parsed")
        rows = with_history(rows)
        doc = {"asof": rows[-1]["date"], "retrieved": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
               "source": "TreasuryDirect auction results", "rows": rows}
        tmp = OUT / "auctions.json.tmp"
        tmp.write_text(json.dumps([doc], ensure_ascii=False, separators=(",", ":")))
        os.replace(tmp, OUT / "auctions.json")
        print(f"  auctions: {len(rows)} coupon auctions through {doc['asof']}")
    except Exception as e:  # keep the previous file; the auctions card shows its own date
        print(f"  WARNING Treasury auctions failed, previous file kept: {e}")


if __name__ == "__main__":
    build_auctions()
