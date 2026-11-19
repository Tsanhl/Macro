"""The Treasury's cash balance (TGA) and the MOVE index for the local 宏觀 view.

TGA: the Daily Treasury Statement on the US Treasury's fiscaldata API, table I (operating cash balance), the row
"Treasury General Account (TGA) Closing Balance", one reading per business day in $ millions, stored in $ billions.
MOVE: Yahoo ^MOVE daily closes, taken from the board's own price download (build_data.main passes the series).
Each block keeps its own observation dates. When a fetch fails, the block from the previous file stays with its old
dates and the failure is listed in "errors"; nothing is carried forward under a new date.
"""
import json
import urllib.parse
import urllib.request
from datetime import date, timedelta

TGA_API = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance"
TGA_ROW = "Treasury General Account (TGA) Closing Balance"
TGA_PAGE = "https://fiscaldata.treasury.gov/datasets/daily-treasury-statement/operating-cash-balance"
MOVE_PAGE = "https://finance.yahoo.com/quote/%5EMOVE/"


def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def tga_rows(payload):
    """The closing-balance rows of a fiscaldata answer as [{"date", "bn"}], oldest first. The DTS puts the closing
    balance in open_today_bal on that row (close_today_bal is "null"); either field is accepted."""
    out = {}
    for x in payload.get("data", []):
        if x.get("account_type") != TGA_ROW:
            continue
        v = _num(x.get("close_today_bal"))
        v = _num(x.get("open_today_bal")) if v is None else v
        d = x.get("record_date", "")
        if v is not None and len(d) == 10:
            out[d] = round(v / 1000, 1)  # $ millions -> $ billions
    return [{"date": d, "bn": out[d]} for d in sorted(out)]


def fetch_tga(start):
    q = {"fields": "record_date,account_type,open_today_bal,close_today_bal",
         "filter": f"record_date:gte:{start},account_type:eq:{TGA_ROW}", "sort": "record_date", "page[size]": "1000"}
    req = urllib.request.Request(TGA_API + "?" + urllib.parse.urlencode(q), headers={"User-Agent": "curl/8.7.1"})
    return tga_rows(json.loads(urllib.request.urlopen(req, timeout=60).read().decode()))


def back(rows, d, days, key="date"):
    """The last row dated on or before `days` calendar days before date d."""
    cut = (date.fromisoformat(d) - timedelta(days=days)).isoformat()
    xs = [r for r in rows if r[key] <= cut]
    return xs[-1] if xs else None


def tga_block(rows):
    """Latest balance, its change over one week and one month (against the last reading at least 7 and 30 days
    earlier) and about seven months of daily readings for the chart."""
    if not rows:
        return None
    last = rows[-1]
    out = {"latest": last, "source": TGA_PAGE, "row": TGA_ROW, "unit": "bn"}
    for k, days in (("1w", 7), ("1m", 30)):
        b = back(rows, last["date"], days)
        out["chg_" + k] = None if b is None else {"bn": round(last["bn"] - b["bn"], 1), "base_date": b["date"]}
    cut = (date.fromisoformat(last["date"]) - timedelta(days=215)).isoformat()
    out["rows"] = [r for r in rows if r["date"] >= cut]
    return out


def move_block(points):
    """points: [(iso date, close)] oldest first. Latest MOVE, change over a week (against the last close at least seven
    days earlier), its percentile within the last year of closes (share at or below the latest), and seven months of
    closes for the chart."""
    pts = [(d, float(v)) for d, v in points if v is not None and v == v]
    if not pts:
        return None
    d, v = pts[-1]
    out = {"latest": {"date": d, "v": round(v, 2)}, "source": MOVE_PAGE}
    rows = [{"date": a, "v": round(b, 2)} for a, b in pts]
    b = back(rows, d, 7)
    out["chg_1w"] = None if b is None else {"v": round(v - b["v"], 2), "base_date": b["date"]}
    start = (date.fromisoformat(d) - timedelta(days=365)).isoformat()
    year = [r for r in rows if r["date"] > start]
    out["pct1y"] = round(sum(r["v"] <= v for r in year) / len(year) * 100)
    out["n1y"], out["first1y"] = len(year), year[0]["date"]
    cut = (date.fromisoformat(d) - timedelta(days=215)).isoformat()
    out["rows"] = [r for r in rows if r["date"] >= cut]
    return out


def build_macro_watch(out_dir, move_points, today=None):
    """Write macro_watch.json into out_dir. Each block falls back to the previous file's block on failure."""
    path = out_dir / "macro_watch.json"
    try:
        prev = json.loads(path.read_text())[0]
    except (OSError, ValueError, IndexError):
        prev = {}
    today = today or date.today()
    row, errors = {"built": date.today().isoformat()}, []
    try:
        row["tga"] = tga_block(fetch_tga((today - timedelta(days=400)).isoformat()))
        if row["tga"] is None:
            raise ValueError("no TGA rows")
    except Exception as e:  # keep the previous block with its own dates
        errors.append(f"TGA: {type(e).__name__}")
        row["tga"] = prev.get("tga")
    try:
        row["move"] = move_block(move_points)
        if row["move"] is None:
            raise ValueError("no ^MOVE closes")
    except Exception as e:
        errors.append(f"MOVE: {type(e).__name__}")
        row["move"] = prev.get("move")
    row["errors"] = errors
    path.write_text(json.dumps([row], ensure_ascii=False, separators=(",", ":")))
    print(f"  macro_watch.json  TGA {(row['tga'] or {}).get('latest')}  MOVE {(row['move'] or {}).get('latest')}"
          + (f"  errors {errors}" if errors else ""))
    return row
