"""The 美國經濟 sub-page of the 宏觀 page: built from macro/data/us_economy.json (macro/us_economy.py, FRED) on every
page load. Each section opens with two sentences: every series' latest release against its previous one, grouped by
its direction in SIGN (with both values), then what the majority means and which series went the other way, then a table, newest release first (latest, period, previous, change, a year earlier, percentile among the
last ten years) and one small chart per series, with a 2-year / 10-year switch. The first card lists what came out in
the last seven days. The head card adds a one-line overview and the pairs of related
series (PAIRS) whose latest releases moved in opposite directions. No thresholds, flags, scores or rules.
"""
from datetime import datetime, timedelta, timezone
from html import escape
import json
from pathlib import Path
from zoneinfo import ZoneInfo

FILE = Path(__file__).resolve().parent.parent / "macro" / "data" / "us_economy.json"
UK = ZoneInfo("Europe/London")
NEW_DAYS = 7
DEC = {"fivefive": 2, "mortgage": 2, "nfci": 2, "gasoline": 2, "openings": 2, "sahm": 2}
ZERO_DEC = ("千人", "千間（年率）", "十億美元")
REF0 = {"gdpnow", "gdp", "indpro", "coreorders", "retail", "cfnai", "empire", "philly", "payrolls", "realinc",
        "realpce", "credit", "caseshiller", "deficit", "nfci"}


def load(path=FILE):
    return json.loads(path.read_text())


def decimals(s):
    return DEC.get(s["key"], 0 if s["unit"] in ZERO_DEC else 1)


def num(v, d, sign=False):
    return "—" if v is None else (f"{v:+,.{d}f}" if sign else f"{v:,.{d}f}")


def freq(s):
    rows = s.get("rows") or []
    if len(rows) < 3:
        return "m"
    a, b = datetime.fromisoformat(rows[-3][0]), datetime.fromisoformat(rows[-1][0])
    gap = (b - a).days / 2
    return "q" if gap > 80 else "m" if gap > 25 else "d"


def period(date, f):
    if not date:
        return "—"
    y, m = int(date[:4]), int(date[5:7])
    if f == "q":
        return f"{y} 年第 {(m - 1) // 3 + 1} 季"
    if f == "m":
        return f"{y} 年 {m} 月"
    return date


def uk_time(iso):
    try:
        return datetime.fromisoformat(iso).astimezone(UK).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso or "—"


def new_card(data, now=None):
    now = now or datetime.now(timezone.utc)
    cut = now - timedelta(days=NEW_DAYS)
    fresh = [s for s in data["series"] if s.get("seen") and datetime.fromisoformat(s["seen"]) >= cut]
    fresh.sort(key=lambda s: s["seen"], reverse=True)
    if fresh:
        items = "".join(
            f'<li>{escape(s["name"])}：{num(s["value"], decimals(s))} {escape(s["unit"])}（{period(s["date"], freq(s))}；'
            f'上期 {num(s["prev"], decimals(s))}）<span class="rb-sub">　首次抓取 {uk_time(s["seen"])}</span></li>'
            for s in fresh)
        body = f"<ul>{items}</ul>"
    else:
        body = f'<p class="rb-sub">過去 {NEW_DAYS} 日沒有新一期數據（由這頁開始記錄後計算）。</p>'
    failed = data.get("failed") or []
    stale = [s["name"] for s in data["series"] if s.get("stale")]
    warn = ""
    if failed or stale:
        warn = f'<p class="rb-sub">今次下載失敗，沿用上次的數據：{escape("、".join(stale) or "、".join(failed))}。</p>'
    return (f'<div class="rb-card rb-wide" id="ue-new"><h3 class="rb-h2">最近 {NEW_DAYS} 日新數據</h3>{body}'
            f'<p class="rb-sub">數據來源：FRED（聖路易斯聯儲），各行列明系列代碼；上次抓取 {uk_time(data.get("fetched_at"))}（英國時間）。'
            f'「首次抓取」是本頁第一次見到該期數據的時間，不是官方公佈時間。百分位是最新值在過去十年所有讀數中的位置（100 = 十年最高）。</p>'
            f'{warn}</div>')


# Direction of each series, by definition: +1 = a higher value reads as the section's first word (偏強, 上升, 壓力增加,
# 寬鬆), -1 = a lower value does. None = no single reading (left out of the counts, still shown in the table).
SIGN = {
    "gdpnow": 1, "gdp": 1, "indpro": 1, "coreorders": 1, "retail": 1, "cfnai": 1, "empire": 1, "philly": 1,
    "payrolls": 1, "unrate": -1, "u6": -1, "sahm": -1, "claims": -1, "contclaims": -1, "openings": 1, "quits": 1,
    "layoffs": -1, "primeepop": 1, "multijob": None, "ahe": 1,
    "cpi": 1, "corecpi": 1, "supercore": 1, "pce": 1, "corepce": 1, "sticky": 1, "fivefive": 1, "mich": 1,
    "umcsent": 1, "realinc": 1, "realpce": 1, "saving": None, "credit": None, "ccdelinq": -1, "gasoline": -1,
    "starts": 1, "permits": 1, "newsales": 1, "supply": -1, "caseshiller": 1, "mortgage": -1,
    "interest": 1, "deficit": -1, "debt": 1,
    "nfci": -1, "dollar": -1, "mktcap": 1,
}
# words for the latest release against the previous one: (first word, second word)
WORDS = {"growth": ("加快", "放緩"), "labour": ("轉強", "轉弱"), "inflation": ("升溫", "降溫"), "consumer": ("改善", "轉差"),
         "housing": ("轉強", "轉弱"), "fiscal": ("增加", "減輕"), "conditions": ("放鬆", "收緊")}
WHAT = {"growth": "經濟活動", "labour": "勞動市場", "inflation": "物價壓力", "consumer": "家庭狀況", "housing": "樓市活動",
        "fiscal": "財政壓力", "conditions": "金融條件"}
# related series whose directions are compared; a pair whose two directions differ is listed as a divergence
PAIRS = [("gdpnow", "umcsent", "增長數據對消費者感受"), ("retail", "umcsent", "零售銷售對消費者信心"),
         ("payrolls", "claims", "非農對首次申領"), ("openings", "quits", "職位空缺對辭職率"),
         ("indpro", "empire", "工業生產對紐約聯儲調查"), ("indpro", "philly", "工業生產對費城聯儲調查"),
         ("realpce", "realinc", "實質消費對實質收入"), ("starts", "permits", "動工對許可證"),
         ("newsales", "mortgage", "新屋銷售對按揭利率"), ("corecpi", "fivefive", "核心 CPI 對市場長期通脹預期"),
         ("corecpi", "mich", "核心 CPI 對家庭通脹預期"), ("mktcap", "umcsent", "股票估值對消費者信心"),
         ("nfci", "ccdelinq", "金融條件對信用卡拖欠")]


def newest_first(rows):
    return sorted(rows, key=lambda s: s.get("date") or "", reverse=True)


def way(s, base):
    """+1 / -1 / 0 in the section's own words (first word / second word / unchanged), None when it has no reading."""
    sign, b = SIGN.get(s["key"]), s.get(base)
    if sign is None or b is None or s.get("value") is None:
        return None
    d = (s["value"] - b) * sign
    return 1 if d > 0 else -1 if d < 0 else 0


def counts(rows, base):
    w = [way(s, base) for s in rows]
    return sum(x == 1 for x in w), sum(x == -1 for x in w), sum(x == 0 for x in w), sum(x is not None for x in w)


def names(xs):
    return "、".join(escape(s["name"]) for s in xs)


def pair(s):
    """Previous and latest value, with extra decimals when the usual ones would show the same number."""
    d = decimals(s)
    while d < 4 and num(s["prev"], d) == num(s["value"], d) and s["prev"] != s["value"]:
        d += 1
    return num(s["prev"], d), num(s["value"], d)


def move(s):
    a, b = pair(s)
    return f"{escape(s['name'])}（{a} → {b}，{period(s['date'], freq(s))}）"


def section_lines(sec, rows):
    """Two sentences from the latest release of each series against its previous release."""
    w0, w1 = WORDS[sec]
    up = [s for s in rows if way(s, "prev") == 1]
    dn = [s for s in rows if way(s, "prev") == -1]
    flat = [s for s in rows if way(s, "prev") == 0]
    other = [s for s in rows if way(s, "prev") is None and s.get("prev") is not None]
    bits = []
    if up: bits.append(f"{w0} {len(up)} 項：" + "、".join(move(s) for s in up))
    if dn: bits.append(f"{w1} {len(dn)} 項：" + "、".join(move(s) for s in dn))
    if flat: bits.append(f"持平：" + "、".join(move(s) for s in flat))
    if other: bits.append(f"沒有單一讀法：" + "、".join(move(s) for s in other))
    line = "<br>".join(bits)
    what = WHAT[sec]
    if not up and not dn:
        imp = f"含義：最新一期沒有變動，{what}方向不變。"
    elif len(up) == len(dn):
        imp = f"含義：{w0}和{w1}的一樣多，{what}最新一期沒有一致方向。"
    else:
        major, minor = (w0, dn) if len(up) > len(dn) else (w1, up)
        mw = w1 if len(up) > len(dn) else w0
        imp = f"含義：按最新一期，{what}整體{major}（{max(len(up), len(dn))}/{len(up) + len(dn)} 項）"
        imp += (f"；但{names(minor)}{mw}，與多數相反。" if minor else "，各項方向一致。")
    return line, imp


def divergences(series):
    """Pairs of related series whose latest releases moved in opposite directions."""
    by = {s["key"]: s for s in series}
    out = []
    for a, b, label in PAIRS:
        sa, sb = by.get(a), by.get(b)
        if not sa or not sb:
            continue
        wa, wb = way(sa, "prev"), way(sb, "prev")
        if wa is None or wb is None or wa == 0 or wb == 0 or wa == wb:
            continue
        def say(s, w):
            x, y = pair(s)
            return (f"{escape(s['name'])}{WORDS[s['section']][0 if w == 1 else 1]}"
                    f"（{x} → {y} {escape(s['unit'])}，{period(s['date'], freq(s))}）")
        out.append(f"<li><b>{label}</b>：{say(sa, wa)}；{say(sb, wb)}。</li>")
    return out


SOFT = {"umcsent", "empire", "philly"}  # surveys and sentiment; the rest of growth and labour is measured activity
QUADRANT = {(1, 1): "增長加快、通脹升溫（按定義是過熱方向）", (1, -1): "增長加快、通脹降溫",
            (-1, 1): "增長放緩、通脹升溫（按定義是滯脹方向）", (-1, -1): "增長放緩、通脹降溫（按定義是放緩方向）"}


def majority(rows):
    up = sum(way(s, "prev") == 1 for s in rows)
    dn = sum(way(s, "prev") == -1 for s in rows)
    return (1 if up > dn else -1 if dn > up else 0), up, dn


def conclusion(data):
    """One paragraph from the latest releases: the growth/inflation pair, then where labour, households, housing,
    financial conditions and the fiscal side stand against it, then measured activity against surveys."""
    by_sec = {sec["key"]: [s for s in data["series"] if s["section"] == sec["key"]] for sec in data["sections"]}
    m = {k: majority(v) for k, v in by_sec.items()}
    g, i = m["growth"][0], m["inflation"][0]
    if g and i:
        head = QUADRANT[(g, i)]
    else:
        head = ("增長" + ("加快" if g == 1 else "放緩" if g == -1 else "方向不一") + "、通脹"
                + ("升溫" if i == 1 else "降溫" if i == -1 else "方向不一"))
    parts = [f"美國經濟最新一期是{head}"]
    same, against = [], []
    for k in ("labour", "consumer", "housing"):
        d = m[k][0]
        if not d:
            continue
        txt = f"{WHAT[k]}{WORDS[k][0 if d == 1 else 1]}"
        (same if d == g else against).append(txt)
    if same:
        parts.append("與增長同方向的有" + "、".join(same))
    if against:
        parts.append("方向相反的有" + "、".join(against))
    for k in ("conditions", "fiscal"):
        d = m[k][0]
        if d:
            parts.append(f"{WHAT[k]}{WORDS[k][0 if d == 1 else 1]}")
    text = "；".join(parts) + "。"
    act = [s for k in ("growth", "labour") for s in by_sec[k] if s["key"] not in SOFT]
    soft = [s for k in ("growth", "consumer") for s in by_sec[k] if s["key"] in SOFT]
    ha, sa = majority(act)[0], majority(soft)[0]
    if ha and sa and ha != sa:
        text += (f"實際活動數據{'較強' if ha == 1 else '較弱'}，調查及信心數據（{names(soft)}）{'較弱' if ha == 1 else '較強'}，"
                 "兩者方向相反。")
    return text


# ---- 總結: who is better off and who is worse off, why, and what would change the reading ----
def _f(v, d=1):
    return "—" if v is None else f"{v:,.{d}f}"


def _pc(s):
    p = s.get("pct10")
    if p is None:
        return ""
    return "，是十年最高" if p == 100 else "，是十年最低" if p == 0 else f"，在十年第 {p} 百分位"


def split_summary(data):
    """The 總結 card. Every comparison is a sign (higher or lower than the previous release or a year earlier) or a
    difference of two published numbers; no cut-offs. Groups of people are inferred from national totals."""
    S = {s["key"]: s for s in data["series"]}
    need = ["gdp", "payrolls", "unrate", "ahe", "cpi", "realinc", "realpce", "saving", "umcsent", "mortgage"]
    if any(k not in S for k in need):
        return '<p class="rb-sub">總結需要的系列未齊，暫時未能生成。</p>'
    v = lambda k: S[k]["value"]
    ya = lambda k: S[k].get("year_ago")
    by_sec = {sec["key"]: [s for s in data["series"] if s["section"] == sec["key"]] for sec in data["sections"]}
    g, lab = majority(by_sec["growth"])[0], majority(by_sec["labour"])[0]
    infl = majority(by_sec["inflation"])
    rw = v("ahe") - v("cpi")
    rw_ya = (ya("ahe") - ya("cpi")) if ya("ahe") is not None and ya("cpi") is not None else None
    gap = v("realpce") - v("realinc")
    saving_down = ya("saving") is not None and v("saving") < ya("saving")
    mood_down = ya("umcsent") is not None and v("umcsent") < ya("umcsent")
    agg_up = g == 1 or lab == 1
    house_down = rw < 0 or (gap > 0 and saving_down) or mood_down
    assets_up = "mktcap" in S and ya("mktcap") is not None and v("mktcap") > ya("mktcap")

    if agg_up and house_down:
        head = ("分化：總體數字變好，但一般家庭的實際處境變差。"
                + ("按數據，大致是「有資產的人較好，靠工資的人較差」。" if assets_up and rw < 0 else ""))
    elif agg_up:
        head = "整體變好：總體數字改善，家庭的實質收入及消費也沒有轉差。"
    elif house_down:
        head = "整體變差：總體數字轉弱，家庭的實際處境也在轉差。"
    else:
        head = "分化：總體數字轉弱，但家庭的實質收入仍在改善。"

    good, bad = [], []
    pay = v("payrolls")
    (good if agg_up else bad).append(
        f"<b>產出和就業</b>：實質 GDP {_f(S['gdp']['prev'])}% → {_f(v('gdp'))}%（{period(S['gdp']['date'], 'q')}，年率）；"
        f"非農 {pay:+,.0f} 千人；失業率 {_f(v('unrate'))}%{_pc(S['unrate'])}。")
    if "mktcap" in S:
        n = S.get("nfci")
        (good if assets_up else bad).append(
            f"<b>股票持有人</b>：非金融企業股票市值對 GDP {_f(v('mktcap'), 0)}%{_pc(S['mktcap'])}（一年前 {_f(ya('mktcap'), 0)}%）"
            + (f"；芝加哥聯儲金融條件指數 {_f(n['value'], 2)}，{'低於' if n['value'] < 0 else '高於'}平均（0），即金融條件{'比平均寬鬆' if n['value'] < 0 else '比平均緊'}" if n else "")
            + "。")
    if "coreorders" in S:
        co = S["coreorders"]
        (good if co["value"] > 0 else bad).append(f"<b>企業投資</b>：核心資本財訂單按年 {co['value']:+.1f}%{_pc(co)}。")
    rw_txt = (f"<b>實質工資{'下跌' if rw < 0 else '上升'}</b>：時薪按年升 {_f(v('ahe'))}%，CPI 升 {_f(v('cpi'))}%，"
              f"扣除通脹後時薪約{'跌' if rw < 0 else '升'} {abs(rw):.1f}%。")
    if rw_ya is not None:
        rw_txt += (f"一年前時薪 {_f(ya('ahe'))}%、CPI {_f(ya('cpi'))}%，那時實質工資{'是正增長' if rw_ya > 0 else '已是負增長'}"
                   + ("；這是最清楚的分化證據。" if rw < 0 < rw_ya and agg_up else "。"))
    (bad if rw < 0 else good).append(rw_txt)
    (bad if gap > 0 else good).append(
        f"<b>收入{'追不上' if gap > 0 else '跟得上'}消費</b>：實質可支配收入按年 {_f(v('realinc'))}%，實質消費 {_f(v('realpce'))}%；"
        f"儲蓄率 {_f(v('saving'))}%{_pc(S['saving'])}（一年前 {_f(ya('saving'))}%）。"
        + ("即是說，家庭在減少儲蓄去維持消費。" if gap > 0 and saving_down else ""))
    (bad if mood_down else good).append(f"<b>信心</b>：密歇根消費者信心 {_f(v('umcsent'))}{_pc(S['umcsent'])}（一年前 {_f(ya('umcsent'))}）。")
    m = S["mortgage"]
    weak_house = [S[k]["name"] for k in ("newsales", "permits") if k in S and way(S[k], "prev") == -1]
    (bad if ya("mortgage") is not None and v("mortgage") > ya("mortgage") else good).append(
        f"<b>借貸成本</b>：30 年按揭利率 {_f(m['value'], 2)}%{_pc(m)}（一年前 {_f(m.get('year_ago'), 2)}%）"
        + (f"；{'和'.join(weak_house)}都轉弱。" if weak_house else "。"))

    gov = []
    if "interest" in S:
        gov.append(f"利息支出佔 GDP {_f(v('interest'))}%{_pc(S['interest'])}")
    if "deficit" in S:
        gov.append(f"12 個月赤字約 {abs(v('deficit')) / 1000:.1f} 萬億美元（一年前 {abs(ya('deficit') or 0) / 1000:.1f} 萬億）")

    calm = []
    if ya("unrate") is not None and v("unrate") <= ya("unrate"):
        calm.append(f"失業率 {_f(v('unrate'))}%，不高於一年前（{_f(ya('unrate'))}%）")
    if "ccdelinq" in S and S["ccdelinq"].get("prev") is not None and S["ccdelinq"]["value"] <= S["ccdelinq"]["prev"]:
        c = S["ccdelinq"]
        calm.append(f"信用卡拖欠率 {_f(c['value'])}%（{period(c['date'], 'q')}）沒有上升")
    if "claims" in S:
        cl = S["claims"]
        calm.append(f"首次申領失業金 {cl['value']:,.0f} 千人{_pc(cl)}")

    why = []
    if gap > 0 and saving_down:
        why.append(f"消費靠減少儲蓄支撐：實質消費增長比收入高 {gap:.1f} 個百分點，差距由儲蓄填補。儲蓄率{_pc(S['saving'])[1:]}，"
                   "收入如果不追上，消費遲早要放慢；這是現時增長最弱的一環。")
    if infl[0] == 1:
        why.append(f"物價是家庭受壓的主因，不是就業：通脹指標最新一期 {infl[1]}/{infl[1] + infl[2]} 項升溫，而就業仍{'轉強' if lab == 1 else '未見明顯轉弱'}。"
                   f"通脹升溫也令利率難以回落，按揭利率{_pc(m)[1:]}，借款家庭和樓市繼續受壓。")
    if assets_up and mood_down:
        why.append("股市財富集中在持股的家庭，所以 GDP、股市等總體數字與一般家庭的感受脫節。消費者信心低而消費仍在增長，"
                   "較可能是收入較高或持有資產的家庭在支撐支出（這是推論：現有數據是全國總數，沒有按收入分組）。")
    soft = [S[k] for k in ("empire", "philly", "umcsent") if k in S and way(S[k], "prev") == -1]
    if agg_up and soft:
        why.append(f"調查和信心先轉弱（{names(soft)}），實際活動仍強。調查反映受訪者對當前及前景的看法；"
                   "如果之後實際數據跟隨調查回落，分化就會變成全面轉差。")
    if "deficit" in S and ya("deficit") is not None and v("deficit") < ya("deficit"):
        why.append("赤字擴大本身在支撐需求；但利息支出創高，這部分開支流向國債持有人，不是一般家庭，同時增加國債供應。")

    flip = "實質工資轉正（時薪增長高於 CPI），儲蓄率回升而消費沒有下跌：代表家庭處境追上總體數字，分化收窄。"
    flip += "反方向：首次申領失業金和失業率上升，代表壓力由物價擴散到就業，分化變成全面轉差。"
    watch = "下一期 CPI 和時薪（實質工資）、每週首次申領失業金、儲蓄率、紐約及費城聯儲調查及消費者信心是否回升。"

    li = lambda xs: "<ul class='ue-div'>" + "".join(f"<li>{x}</li>" for x in xs) + "</ul>"
    html = f"<p><b>{head}</b></p>"
    if good: html += "<p><b>變好的</b></p>" + li(good)
    if bad: html += "<p><b>變差的</b></p>" + li(bad)
    if gov: html += f"<p><b>政府：財政{'變差' if 'deficit' in S and ya('deficit') is not None and v('deficit') < ya('deficit') else '狀況'}</b></p>" + li(["；".join(gov) + "。"])
    if calm: html += "<p><b>還未見到的壓力</b></p>" + li(["；".join(calm) + "。" + ("家庭感覺變差，但還沒有出現失業或還不起債的情況。" if house_down else "")])
    if why: html += "<p><b>推論：為甚麼會這樣，會怎樣延續</b></p>" + li(why)
    html += f"<p><b>推翻條件：</b>{flip}</p><p><b>要看：</b>{watch}</p>"
    html += ('<p class="rb-sub">由本頁數據自動寫成，每次更新按最新數字重寫。比較只用升跌方向及兩個公佈數字之差，不設門檻；'
             '「推論」一節是我們的解讀。各系列期間不同（每週至每季）。</p>')
    return html



def overview(data):
    parts = []
    for sec in data["sections"]:
        rows = [s for s in data["series"] if s["section"] == sec["key"]]
        w0, w1 = WORDS[sec["key"]]
        up = sum(way(s, "prev") == 1 for s in rows)
        dn = sum(way(s, "prev") == -1 for s in rows)
        if not up and not dn:
            continue
        what = WHAT[sec["key"]]
        if up == dn:
            parts.append(f"{what}方向不一（{w0} {up}、{w1} {dn}）")
        else:
            parts.append(f"{what}{w0 if up > dn else w1}（{max(up, dn)}/{up + dn}）")
    div = divergences(data["series"])
    html = f'<p><b>各節最新一期：</b>{conclusion(data)}</p><p>{"；".join(parts)}。</p>'
    html += (f'<p><b>互相矛盾的數據（{len(div)} 組相關指標最新一期方向相反）</b></p><ul class="ue-div">{"".join(div)}</ul>' if div
             else '<p>相關指標的最新一期沒有方向相反。</p>')
    html += ('<p class="rb-sub">每項都是最新一期對上一期（每週、每月或每季，按該指標的公佈頻率，所以各項的期間不同）。'
             '方向按每個指標的定義（例如失業率上升算轉弱、按揭利率上升算轉弱、美元走強算收緊）；不設幅度門檻，很小的變動也算一個方向。'
             '有多份工作者比例、儲蓄率及消費信貸沒有單一讀法，不計入。</p>')
    return html


def section_card(sec, rows):
    rows = newest_first(rows)
    line, imp = section_lines(sec["key"], rows)
    trs = []
    for s in rows:
        d = decimals(s)
        f = freq(s)
        chg = None if s.get("prev") is None else s["value"] - s["prev"]
        stale = ' <span class="rb-sub">（沿用上次）</span>' if s.get("stale") else ""
        trs.append(
            f'<tr><td class="rb-left"><a href="{escape(s["link"])}" target="_blank" rel="noopener">{escape(s["name"])}</a>{stale}'
            f'<div class="rb-sub">{escape(s["unit"])} · {escape(s["source"])}</div></td>'
            f'<td><b>{num(s["value"], d)}</b></td><td>{period(s["date"], f)}</td><td>{num(s.get("prev"), d)}</td>'
            f'<td>{num(chg, d, True)}</td><td>{num(s.get("year_ago"), d)}</td>'
            f'<td>{"—" if s.get("pct10") is None else s["pct10"]}</td></tr>')
    charts = "".join(
        f'<div class="ue-chart"><div class="rb-sub">{escape(s["name"])}（{escape(s["unit"])}）</div>'
        f'<div class="rb-chart" id="ch-ue-{s["key"]}" style="min-height: 8.5rem"></div></div>' for s in rows)
    return (f'<div class="rb-card rb-wide" id="ue-{sec["key"]}"><h3 class="rb-h2">{escape(sec["name"])}</h3>'
            f'<p class="ue-sum">{line}</p><p class="ue-sum">{imp}</p>'
            f'<div class="rb-tablebox"><table class="rb-table ue-table"><thead><tr><th class="rb-left">指標</th><th>最新</th>'
            f'<th>期間</th><th>上期</th><th>變動</th><th>一年前</th><th>十年百分位</th></tr></thead><tbody>{"".join(trs)}</tbody></table></div>'
            f'<div class="ue-grid">{charts}</div></div>')


def page(path=FILE):
    """HTML of the sub-page's cards plus the chart data as inline JSON."""
    try:
        data = load(path)
    except Exception:
        return ('<div class="rb-card rb-wide"><p class="rb-sub">未有美國經濟數據：請執行 '
                '<code>python3 macro/us_economy.py</code> 或按「更新全部數據」。</p></div>')
    head = ('<div class="rb-card rb-wide" id="ue-head"><h3 class="rb-h2">美國經濟</h3>'
            '<p class="rb-sub">增長、就業、通脹、消費者、樓市、財政及金融條件的公開數據。</p>'
            + overview(data) +
            '<div class="rb-seg" role="group" aria-label="圖表範圍"><button type="button" class="ue-range" data-range="2" aria-pressed="true">2 年</button>'
            '<button type="button" class="ue-range" data-range="10" aria-pressed="false">10 年</button></div></div>')
    summary = f'<div class="rb-card rb-wide" id="ue-summary"><h3 class="rb-h2">總結</h3>{split_summary(data)}</div>'
    cards = [summary, head, new_card(data)]
    for sec in data["sections"]:
        rows = [s for s in data["series"] if s["section"] == sec["key"]]
        if rows:
            cards.append(section_card(sec, rows))
    chart = {s["key"]: {"rows": s["rows"], "dec": decimals(s), "ref": s["key"] in REF0, "name": s["name"]} for s in data["series"]}
    blob = json.dumps(chart, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return "\n".join(cards) + f'\n<script type="application/json" id="useco-json">{blob}</script>'


# Drawn inside the dashboard's script (macro_view.RB_JS), with its lineChart, so the tooltips and colours match.
JS = """  let ueYears = 2;
  function drawRbUsEco() {
    const src = document.getElementById('useco-json'); if (!src) return;
    const data = JSON.parse(src.textContent), c = colors();
    document.querySelectorAll('.ue-range').forEach((b) => {
      b.setAttribute('aria-pressed', String(+b.dataset.range === ueYears));
      if (!b.dataset.bound) { b.dataset.bound = '1'; b.addEventListener('click', () => { ueYears = +b.dataset.range; drawRbUsEco(); }); }
    });
    for (const [key, s] of Object.entries(data)) {
      const el = document.getElementById('ch-ue-' + key); if (!el || !s.rows.length) continue;
      const last = day(s.rows.at(-1)[0]), cut = new Date(Date.UTC(last.getUTCFullYear() - ueYears, last.getUTCMonth(), last.getUTCDate()));
      const values = s.rows.map((r) => ({ d: day(r[0]), v: r[1] })).filter((p) => p.d > cut);
      const f = d3.format(',.' + s.dec + 'f');
      try { lineChart(el, { series: [{ name: s.name, color: c[0], values }], height: 140, yFmt: d3.format(',~f'), tipFmt: f, ref: s.ref ? 0 : null }); }
      catch (e) { console.error('us economy chart', key, e); }
    }
  }
"""

STYLE = """
#rb-wrap .ue-grid { display: grid; gap: 10px 16px; grid-template-columns: repeat(auto-fill, minmax(min(100%, 16rem), 1fr)); margin-top: 10px; }
#rb-wrap .ue-chart .rb-sub { font-size: 12px; }
#rb-wrap .ue-table td, #rb-wrap .ue-table th { text-align: right; } #rb-wrap .ue-table .rb-left { text-align: left; }
#rb-wrap .ue-table td.rb-left { white-space: normal; min-width: 12rem; } #rb-wrap .ue-table td.rb-left .rb-sub { font-size: 11px; }
#rb-wrap .ue-table a { color: inherit; }
#rb-wrap #ue-head .rb-seg { display: flex; margin-top: 6px; }
#rb-wrap #ue-new ul, #rb-wrap .ue-div { margin: 0 0 8px; padding-left: 20px; }\n#rb-wrap #ue-summary { background: var(--surface-2); }\n#rb-wrap .ue-sum, #rb-wrap #ue-head p, #rb-wrap #ue-summary p { margin: 0 0 6px; max-width: 120ch; }
"""
