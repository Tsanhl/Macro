"""US economy series for the 美國經濟 sub-page (宏觀 page of the 8770 board): growth, labour, inflation, consumers,
housing, fiscal and financial conditions, all from FRED's public CSV download (no key).

Writes data/us_economy.json. Data only: latest value, the previous observation, the value a year earlier and the
percentile of the latest value among the last ten years of observations. No thresholds, flags or scores.

A series that fails to download keeps the previous file's entry, marked stale (user, 2026-10-21: don't stall the board
on a FRED outage). `seen` is the time a new latest observation was first fetched, so the page can list what is new.

Run on its own (python3 us_economy.py) or from refresh.py, which calls it in the staging folder.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import csv
import io
import json
import os
from pathlib import Path
import time
import urllib.request

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "us_economy.json"
URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}&cosd=1999-01-01"
YEARS_KEPT = 10

SECTIONS = [("growth", "增長"), ("labour", "就業"), ("inflation", "通脹"), ("consumer", "消費者及家庭"),
            ("housing", "樓市"), ("fiscal", "財政"), ("conditions", "金融條件、美元及估值")]

# key, section, name, unit, FRED id(s), transform
#   level: as published; yoy: % change over a year; diff: change from the previous observation;
#   div1000: published value / 1000; sum12: rolling 12-month sum / 1000; ratio: id1 / id2 * 100 (with scale)
SERIES = [
    ("gdpnow", "growth", "GDPNow（亞特蘭大聯儲本季估算）", "% 年率", ["GDPNOW"], "level"),
    ("gdp", "growth", "實質 GDP", "% 年率（季度）", ["A191RL1Q225SBEA"], "level"),
    ("indpro", "growth", "工業生產", "按年 %", ["INDPRO"], "yoy"),
    ("coreorders", "growth", "核心資本財訂單（非國防，不包括飛機）", "按年 %", ["NEWORDER"], "yoy"),
    ("retail", "growth", "實質零售銷售", "按年 %", ["RRSFS"], "yoy"),
    ("cfnai", "growth", "芝加哥聯儲全國活動指數", "指數", ["CFNAI"], "level"),
    ("empire", "growth", "紐約聯儲製造業調查", "擴散指數", ["GACDINA066MNFRBNY"], "level"),
    ("philly", "growth", "費城聯儲製造業調查", "擴散指數", ["GACDFSA066MSFRBPHI"], "level"),

    ("payrolls", "labour", "非農就業（月變動）", "千人", ["PAYEMS"], "diff"),
    ("unrate", "labour", "失業率", "%", ["UNRATE"], "level"),
    ("u6", "labour", "U-6 失業率", "%", ["U6RATE"], "level"),
    ("sahm", "labour", "Sahm 實時指標", "百分點", ["SAHMREALTIME"], "level"),
    ("claims", "labour", "首次申領失業金（每週）", "千人", ["ICSA"], "div1000"),
    ("contclaims", "labour", "持續申領失業金（每週）", "千人", ["CCSA"], "div1000"),
    ("openings", "labour", "JOLTS 職位空缺", "百萬", ["JTSJOL"], "div1000"),
    ("quits", "labour", "JOLTS 辭職率", "%", ["JTSQUR"], "level"),
    ("layoffs", "labour", "JOLTS 裁員率", "%", ["JTSLDR"], "level"),
    ("primeepop", "labour", "25–54 歲就業人口比率", "%", ["LNS12300060"], "level"),
    ("multijob", "labour", "有多份工作者佔就業人數", "%", ["LNS12026620"], "level"),
    ("ahe", "labour", "平均時薪", "按年 %", ["CES0500000003"], "yoy"),

    ("cpi", "inflation", "CPI", "按年 %", ["CPIAUCSL"], "yoy"),
    ("corecpi", "inflation", "核心 CPI", "按年 %", ["CPILFESL"], "yoy"),
    ("supercore", "inflation", "服務 CPI（不包括住屋）", "按年 %", ["CUSR0000SASL2RS"], "yoy"),
    ("pce", "inflation", "PCE 物價", "按年 %", ["PCEPI"], "yoy"),
    ("corepce", "inflation", "核心 PCE 物價", "按年 %", ["PCEPILFE"], "yoy"),
    ("sticky", "inflation", "亞特蘭大聯儲 sticky 核心 CPI", "按年 %", ["CORESTICKM159SFRBATL"], "level"),
    ("fivefive", "inflation", "5 年後 5 年通脹預期（市場）", "%", ["T5YIFR"], "level"),
    ("mich", "inflation", "密歇根一年通脹預期", "%", ["MICH"], "level"),

    ("umcsent", "consumer", "密歇根消費者信心", "指數", ["UMCSENT"], "level"),
    ("realinc", "consumer", "實質可支配收入", "按年 %", ["DSPIC96"], "yoy"),
    ("realpce", "consumer", "實質個人消費開支", "按年 %", ["PCEC96"], "yoy"),
    ("saving", "consumer", "個人儲蓄率", "%", ["PSAVERT"], "level"),
    ("credit", "consumer", "消費信貸", "按年 %", ["TOTALSL"], "yoy"),
    ("ccdelinq", "consumer", "信用卡拖欠率（商業銀行，季度）", "%", ["DRCCLACBS"], "level"),
    ("gasoline", "consumer", "汽油零售價（每週）", "美元／加侖", ["GASREGW"], "level"),

    ("starts", "housing", "新屋動工", "千間（年率）", ["HOUST"], "level"),
    ("permits", "housing", "建築許可", "千間（年率）", ["PERMIT"], "level"),
    ("newsales", "housing", "新屋銷售", "千間（年率）", ["HSN1F"], "level"),
    ("supply", "housing", "新屋供應", "月", ["MSACSR"], "level"),
    ("caseshiller", "housing", "Case-Shiller 全國樓價", "按年 %", ["CSUSHPINSA"], "yoy"),
    ("mortgage", "housing", "30 年按揭利率（每週）", "%", ["MORTGAGE30US"], "level"),

    ("interest", "fiscal", "聯邦利息支出佔 GDP", "%（季度）", ["A091RC1Q027SBEA", "GDP"], "ratio"),
    ("deficit", "fiscal", "聯邦盈餘／赤字（12 個月累計，負數為赤字）", "十億美元", ["MTSDS133FMS"], "sum12"),
    ("debt", "fiscal", "聯邦債務佔 GDP", "%（季度）", ["GFDEGDQ188S"], "level"),

    ("nfci", "conditions", "芝加哥聯儲金融條件指數（每週）", "指數（0 = 平均）", ["NFCI"], "level"),
    ("dollar", "conditions", "廣義美元指數（每日）", "指數", ["DTWEXBGS"], "level"),
    ("mktcap", "conditions", "非金融企業股票市值佔 GDP（Fed Z.1，季度）", "%", ["NCBEILQ027S", "GDP"], "ratio_mcap"),
]


def fetch(series_id, tries=3):
    for attempt in range(tries):
        try:
            # FRED stalls on browser-like user agents from scripts; a curl agent is answered at once
            req = urllib.request.Request(URL.format(series_id), headers={"User-Agent": "curl/8.7.1"})
            text = urllib.request.urlopen(req, timeout=90).read().decode()
            rows = []
            for r in list(csv.reader(io.StringIO(text)))[1:]:
                try:
                    rows.append((r[0], float(r[1])))
                except (ValueError, IndexError):
                    pass  # "." for a missing day
            if not rows:
                raise ValueError("no rows")
            return rows
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(4 * (attempt + 1))


def per_year(rows):
    """Observations per year, from the spacing of the dates (12 monthly, 4 quarterly, ~52 weekly)."""
    d = [datetime.fromisoformat(r[0]) for r in rows[-30:]]
    gap = (d[-1] - d[0]).days / max(len(d) - 1, 1)
    return 4 if gap > 80 else 12 if gap > 25 else 52 if gap > 5 else 252


def transform(kind, raw):
    a = raw[0]
    if kind == "level":
        return a
    if kind == "div1000":
        return [(d, v / 1000) for d, v in a]
    if kind == "diff":
        return [(a[i][0], a[i][1] - a[i - 1][1]) for i in range(1, len(a))]
    if kind == "yoy":
        n = per_year(a)
        return [(a[i][0], (a[i][1] / a[i - n][1] - 1) * 100) for i in range(n, len(a))]
    if kind == "sum12":
        return [(a[i][0], sum(v for _, v in a[i - 11:i + 1]) / 1000) for i in range(11, len(a))]
    if kind in ("ratio", "ratio_mcap"):
        den = dict(raw[1])
        scale = 1 / 1000 if kind == "ratio_mcap" else 1  # NCBEILQ027S is in millions, GDP in billions
        return [(d, v * scale / den[d] * 100) for d, v in a if den.get(d)]
    raise ValueError(kind)


def summarise(rows):
    last_d, last_v = rows[-1]
    prev = rows[-2] if len(rows) > 1 else None
    year_ago_d = f"{int(last_d[:4]) - 1}{last_d[4:]}"
    ago = [r for r in rows if r[0] <= year_ago_d]
    cut = f"{int(last_d[:4]) - YEARS_KEPT}{last_d[4:]}"
    window = [v for d, v in rows if d > cut]
    pct = round(sum(v <= last_v for v in window) / len(window) * 100) if len(window) >= 8 else None
    return dict(date=last_d, value=round(last_v, 3),
                prev_date=prev[0] if prev else None, prev=round(prev[1], 3) if prev else None,
                year_ago_date=ago[-1][0] if ago else None, year_ago=round(ago[-1][1], 3) if ago else None,
                pct10=pct, rows=[[d, round(v, 3)] for d, v in rows if d > cut])


def build(out=OUT):
    old = {}
    if out.exists():
        try:
            old = {s["key"]: s for s in json.loads(out.read_text())["series"]}
        except Exception:
            old = {}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ids = sorted({i for s in SERIES for i in s[4]})
    raw, errors = {}, {}
    with ThreadPoolExecutor(8) as pool:
        for sid, res in zip(ids, pool.map(lambda i: _try(fetch, i), ids)):
            (raw.__setitem__ if not isinstance(res, Exception) else errors.__setitem__)(sid, res)
    out_rows, failed = [], []
    for key, sec, name, unit, sids, kind in SERIES:
        base = dict(key=key, section=sec, name=name, unit=unit, source="FRED " + " / ".join(sids),
                    link=f"https://fred.stlouisfed.org/series/{sids[0]}")
        try:
            if any(i in errors for i in sids):
                raise errors[next(i for i in sids if i in errors)]
            s = summarise(transform(kind, [raw[i] for i in sids]))
            prior = old.get(key)
            if prior and prior.get("date") == s["date"]:
                s["seen"] = prior.get("seen")
            else:
                s["seen"] = now if prior else None  # first build: nothing counts as newly released
            out_rows.append({**base, **s, "stale": False})
        except Exception as e:
            failed.append(f"{key}: {type(e).__name__}")
            if key in old:
                out_rows.append({**old[key], **base, "stale": True})
    if not out_rows:
        raise RuntimeError("no US economy series could be built")
    data = dict(fetched_at=now, sections=[dict(key=k, name=n) for k, n in SECTIONS], series=out_rows, failed=failed)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.replace(tmp, out)
    return data


def _try(fn, *a):
    try:
        return fn(*a)
    except Exception as e:
        return e


if __name__ == "__main__":
    d = build()
    print(f"us_economy: {len(d['series'])} series, failed: {d['failed'] or 'none'}")
