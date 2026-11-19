"""Local daily macro summary, from the board's same completed-session snapshot.

Presentation only. Confirmed weekly models and trading thresholds are unchanged.
The canonical selection/update policy is board_maintenance.md. The backdrop sentence (大環境) is not part of this
summary: it is shown in the top summary of the one-board macro view (server/macro_summary.py, line_backdrop).
"""
import json
import math
from datetime import date
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
JOINT = "共同改善：市寬及領跌板塊持續修復，AI借款人的CDS／債券息差亦同步收窄，便重新評估AI的防守取態；缺報價維持未確認。大市取態另看廣泛信用、市寬及利率。"


def load(name):
    return json.loads((DATA / f"{name}.json").read_text())


def sg(x, digits=1):
    if x is None:
        return "未確認"
    return ("+" if x > 0 else "−" if x < 0 else "") + f"{abs(x):.{digits}f}"


def md(x):
    return f"{int(x[5:7])}月{int(x[8:10])}日" if x else "日期未確認"


def reference_reading(issuer, asof):
    """Dated vendor price/YTW comparisons only; never a CDS/OAS confirmation.

    An explicit superseded flag preserves revisions without comparing two versions
    of the same day. Unresolved duplicate dates or differing quote bases fail closed.
    """
    def valid(q):
        try:
            d = q.get("price_date", "")
            return (not q.get("superseded") and date.fromisoformat(d).isoformat() == d and d <= asof
                    and all(q.get(k) for k in ("isin", "currency", "yield_type", "provider", "price_basis"))
                    and q.get("source", "").startswith("https://")
                    and all(isinstance(q.get(k), (int, float)) and not isinstance(q[k], bool)
                            and math.isfinite(q[k]) for k in ("clean_price_per_100", "yield_pct"))
                    and q["clean_price_per_100"] > 0)
        except (ValueError, TypeError):
            return False
    rows = sorted([q for q in issuer.get("reference_quotes", []) if valid(q)], key=lambda q: q["price_date"])
    if not rows:
        return None
    last = rows[-1]
    out = {"latest": last, "prior": None, "price_change": None, "price_return_pct": None,
           "yield_change_bp": None, "status": "延遲第三方參考；信用改善未確認"}
    if sum(q["price_date"] == last["price_date"] for q in rows) != 1:
        return {**out, "latest": None, "status": "同日報價有衝突，暫不比較"}
    earlier = [q for q in rows if q["price_date"] < last["price_date"]]
    if not earlier:
        return out
    prior = earlier[-1]
    keys = ("isin", "currency", "yield_type", "provider", "price_basis")
    if sum(q["price_date"] == prior["price_date"] for q in earlier) != 1 or any(prior[k] != last[k] for k in keys):
        out["status"] = "前次報價口徑不一或有衝突，暫不比較"
        return out
    if prior.get("settlement_basis") != last.get("settlement_basis"):
        out["status"] = "結算假設不一致或前值未記錄，變化未確認"
        return out
    change = last["clean_price_per_100"] - prior["clean_price_per_100"]
    out.update(prior=prior, price_change=round(change, 6),
               price_return_pct=round(change / prior["clean_price_per_100"] * 100, 6),
               yield_change_bp=round((last["yield_pct"] - prior["yield_pct"]) * 100, 6))
    return out


def credit_change(rt, cols):
    dates = [rt.get(c + "_date") for c in cols]
    prev = [rt.get(c + "_prev_date") for c in cols]
    values = [rt.get(c + "_1d") for c in cols]
    if (not all(dates + prev) or len(set(dates)) != 1 or len(set(prev)) != 1
            or any(not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) for v in values)):
        return None, None, None
    try:
        if any(date.fromisoformat(d).isoformat() != d for d in dates + prev) or prev[0] >= dates[0]:
            return None, None, None
    except (ValueError, TypeError):
        return None, None, None
    return values[0] - sum(values[1:]), dates[0], prev[0]


def daily_context(asof, sectors):
    pts = load("check_prices")
    if not pts or pts[-1]["date"] != asof:
        raise ValueError("每日相對走勢資料未與摘要收市日期對齊")
    spy = pts[-1]["spy_1d"]
    return {r["ticker"]: {**r, "rel_day": None if r.get("r1d") is None else r["r1d"] - spy} for r in sectors}


def borrower_reading(asof):
    path = DATA.parent.parent / "evidence" / "borrower_credit.json"
    doc = json.loads(path.read_text()) if path.is_file() else {}
    lines, available = [], set()
    for issuer in doc.get("issuers", []):
        for s in issuer.get("series", []):
            if not (s.get("comparable") is True and s.get("metric") in ("cds_bp", "bond_oas_bp")
                    and s.get("quote_type") in ("close_mid", "close_trade")
                    and all(s.get(k) for k in ("instrument", "currency", "series_id"))):
                continue
            def valid_date(value):
                try:
                    return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
                except ValueError:
                    return False
            obs = [o for o in s.get("observations", []) if o.get("verified") is True
                   and isinstance(o.get("value"), (int, float)) and not isinstance(o["value"], bool) and math.isfinite(o["value"])
                   and o.get("source", "").startswith("https://") and o.get("observed_at", "")[:10] == o.get("date")
                   and valid_date(o.get("date")) and o["date"] <= asof]
            counts = {o["date"]: sum(x["date"] == o["date"] for x in obs) for o in obs}
            obs = sorted([o for o in obs if counts[o["date"]] == 1], key=lambda o: o["date"])
            if len(obs) < 2:
                continue
            last, prior = obs[-1], obs[-2]
            change = last["value"] - prior["value"]
            lines.append(f"{issuer['name']} {s['instrument']} {sg(change, 1)} 基點（{md(prior['date'])}至{md(last['date'])}）")
            if last["date"] == asof:
                available.add(issuer["id"])
    if available >= {"CRWV", "ORCL"}:
        return "已有同日可比較報價，持續改善仍待確認", "；".join(lines) + "。要看之後能否持續收窄。"
    evidence = "；".join(lines) + "。" if lines else ""
    has_reference = any(reference_reading(i, asof) for i in doc.get("issuers", []))
    reference = "已有延遲第三方債價／YTW及可比較日期的變化，見下方展開資料；它們不等於已確認信用息差。" if has_reference else ""
    return "信用改善未確認", evidence + reference + "CoreWeave、Oracle尚未同時具備最新可比較收市CDS／指定債券息差。"


def overview(asof, br, rt, sectors):
    # Keep the existing entry point; weekly position date and layer names are not daily-summary inputs.
    if br[-1]["date"] != asof:
        raise ValueError("摘要資料不是同一個已完成交易日")
    sector = daily_context(asof, sectors)
    latest, prior = br[-1], br[-2]
    change = latest["pct50"] - prior["pct50"]
    adv, dec = latest["adv"], latest["dec"]
    cb, cd, cp = credit_change(rt, ["ccc_oas", "bb_oas"])
    rsp, smh = [sector[t] for t in ("RSP", "SMH")]
    repair = change > 0 and adv > dec and rsp["rel_day"] > 0
    headline = ("市寬回升、等權股跑贏，大市出現修復" if repair else
                "市寬轉弱、下跌股票較多，大市修復受阻" if change < 0 and dec > adv else "市寬與等權表現分歧，大市方向仍待確認")
    semi = "半導體當日仍跑輸" if smh["rel_day"] < 0 else "半導體當日跑贏"
    cred = "低質信用最新變化未確認" if cb is None else "低質信用息差仍擴闊" if cb > 0 else "低質信用息差最新一天收窄" if cb < 0 else "低質信用息差最新持平"
    # Reviewed one-sentence reading only. Completed-week/CFTC additions and the UK calendar
    # are independently reviewed by the existing task under the latest format in board_maintenance.md.
    out = [f"市場摘要（{md(asof)}收市）：", "",
           f"一句摘要：{headline}；{semi}，{cred}（{md(cd)}）。", ""]
    return out


def rotation_daily(asof, sectors):
    rows = daily_context(asof, sectors)
    groups = [r for r in rows.values() if r["group"] == "sector" and r["rel_day"] is not None]
    ordered = sorted(groups, key=lambda r: r["rel_day"], reverse=True)
    winners = [r for r in ordered if r["rel_day"] > 0][:3]
    losers = [r for r in reversed(ordered) if r["rel_day"] < 0][:3]
    describe = lambda xs: "、".join(f"{r['name']} {sg(r['rel_day'])}" for r in xs) or "沒有"
    out = ["", f"板塊輪動（{md(asof)}當日，相對標普百分點）：", "",
           f"* 跑贏較多：{describe(winners)}。", f"* 跑輸較多：{describe(losers)}。",
           "* 相對強弱表示價格表現，並非已確認資金流入／流出；一日排名不代表趨勢已轉向。"]
    return out


def model_daily(asof, f):
    if f.get("date") != asof:
        return ["", "持倉與流向：模型未有同日數據，暫不判讀。"]
    out = ["", "持倉與流向（每日模型估算）：", "",
           f"* CTA {sg(f['cta'], 0)}，今日 {sg(f.get('cta_1d'))}：模型{'多倉減少' if f.get('cta_1d',0) < 0 else '倉位增加'}，不是實際基金買賣統計。",
           f"* 波幅控制模型倉位為上限的 {f['vc']:.0f}%，今日 {sg(f.get('vc_1d'))} 點；"
           + ("此模型今日沒有同步減倉。" if f.get('vc_1d') is not None and f['vc_1d'] >= 0 else "此模型今日亦減少風險。")]
    return out


def detail_daily(asof, sectors, f):
    rows = daily_context(asof, sectors)
    out = ["", "[[details:每日板塊及模型數據]]", "", f"板塊相對標普（{md(asof)}當日，百分點）：", ""]
    for group, label in [("sector", "標普板塊及貴金屬"), ("theme", "主題"), ("style", "風格"), ("ai", "AI籃子")]:
        xs = sorted([r for r in rows.values() if r["group"] == group and r["rel_day"] is not None], key=lambda r: -r["rel_day"])
        out.append(f"* {label}：" + "、".join(f"{r['name']} {sg(r['rel_day'])}" for r in xs) + "。")
    if f.get("date") == asof:
        out += ["", "每日模型詳情：", "",
                f"* CTA 今日 {sg(f.get('cta_1d'))}、近5日 {sg(f.get('cta_5d'))}。",
                f"* 波幅控制：近5日 {sg(f.get('vc_5d'))}、近21日 {sg(f.get('vc_21d'))} 點；實現波幅1個月 {f['rv1']:.1f}%、3個月 {f['rv3']:.1f}%。",
                f"* VIX／VIX3M {f['vix_ratio']:.3f}（{md(f.get('vix_date'))}）。"]
        fresh = [b for b in f.get("bonds", []) if b.get("date") == asof and b.get("name") == "美國"]
        if fresh:
            out.append("* 國債CTA模型（同日觀察）：" + "、".join(f"{b['name']} {sg(b['signal'],2)}" for b in fresh) + "。")
    out += ["", "[[/details]]"]
    return out


def build():
    br, rt, sectors, f = [load(k) for k in ("breadth", "rates_now", "sectors", "flowmodel_now")]
    asof, rt, f = br[-1]["date"], rt[0], f[0]
    out = overview(asof, br, rt, sectors)
    out += ["", "---", ""] + model_daily(asof, f) + detail_daily(asof, sectors, f)
    return "\n".join(out) + "\n"
