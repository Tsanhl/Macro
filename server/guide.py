"""讀法 (user, 2026-11-22): how to read the board. First what every indicator measures and how to read it (fixed text),
then three checklists whose 現時 column is read from the board's data on every page load: metals sold with stocks or
on their own fundamentals; rotation or a broad decline; a bounce that the other readings confirm or one they do not;
last the tested numbers (R29): the market state and the bounce check with today's three checks and the history by score.

Each 現時 reading is put in a column by definition (a sign, a direction against a week earlier, or the ±0.25 sampling
band of a 63-session correlation); nothing here is a tested signal except the market-state line and the bounce check (R29),
stated as historical rates. No advice, no position words. The page is the same on the local board and the public snapshot.
"""
from html import escape

import macro_summary as ms
from pages import page

STYLE = """<style>
.guide h2 { margin-top: 22px; } .guide h3 { margin: 14px 0 4px; }
.guide td:first-child { white-space: nowrap; font-weight: 600; }
.guide td.now { white-space: nowrap; }
.guide .lean { font-weight: 700; } .guide .muted { color: var(--ink-3); }
.guide .sum { font-weight: 600; }
</style>"""


def tr(cells, now=None):
    """One table row; cells are plain text. `now` marks the columns that hold live readings."""
    now = now or ()
    return "<tr>" + "".join(f'<td{" class=now" if i in now else ""}>{escape(str(c))}</td>' for i, c in enumerate(cells)) + "</tr>"


def grid(head, rows):
    h = "".join(f"<th>{escape(x)}</th>" for x in head)
    return f'<div class="box"><table><tr>{h}</tr>{"".join(rows)}</table></div>'


# ---------- part 1: what each indicator means (fixed text) ----------

MEANINGS = [
    ("傳導鏈（宏觀頁頂六格）", "看壓力由 AI 股傳到哪一格；愈往右轉差，問題愈由「股價」變成「借錢及資金」。", [
        ("AI 股", "SMH（半導體 ETF）一週回報", "拋售的源頭"),
        ("全部股票", "11 個板塊幾個下跌、等權標普、高於 50 日線的股份比例", "跌勢有多闊"),
        ("低評級信用", "HY 息差、CCC（最弱一級）", "借錢最貴、最脆弱的公司"),
        ("投資級", "IG 息差", "好公司借錢也開始變貴，問題就擴散了"),
        ("私募信貸", "BIZD（借錢給私人公司的上市貸款機構）", "主題拋售變全面危機的通道"),
        ("資金市場", "SOFR 對 IORB、常備回購", "銀行有沒有缺錢")]),
    ("AI 拋售卡", "", [
        ("SMH ÷ SPY", "半導體相對大市的強弱", "線向下＝半導體跑輸"),
        ("記憶體籃子", "MU、WDC、STX、SNDK 相對大市", "跑輸＝記憶體股受壓多過大市"),
        ("63 日相關", "近三個月，資產與納指同步升跌的程度", "+1 完全同步，−1 完全相反，±0.25 以內沒有可靠關係"),
        ("五年中位", "這項資產平常的相關", "與現在比較，看是否異常"),
        ("SMH 最差日", "半導體跌得最多的 25 日，這項資產平均怎樣表現", "最直接的「避不避險」測試")]),
    ("市寬", "", [
        ("升跌線", "每日上升股數減下跌股數的累計", "跟着 SPY 一起跌＝大部分股票都在跌，不只是大股"),
        ("麥克連振盪指標", "（上升 − 下跌）÷（上升 + 下跌）的 19 日減 39 日指數平均", "0 以上＝近期上升股數佔優，0 以下＝下跌佔優；看短期動能")]),
    ("信用總表", "", [
        ("HY、IG", "高收益債、投資級債比國債多付的息", "擴闊＝借錢變貴"),
        ("CCC、B、BB、BBB", "由最弱到最好的評級", "壓力通常由 CCC 開始，再向上傳到 BB、BBB"),
        ("CCC−BB", "最弱與較好一級的差距", "擴闊＝壓力集中在最弱一級"),
        ("HYG÷IEF、LQD÷IEF", "高收益債、投資級債 ETF 對國債的比率", "息差遲一日公佈，這兩個是當日的價格代理"),
        ("BIZD、BKLN", "私募信貸、槓桿貸款 ETF 的價格", "價格代理，不是息差"),
        ("SOFR−IORB", "隔夜借錢利率減聯儲付給銀行的利率", "持續高於 0＝資金偏緊；月底及結算日常有噪音"),
        ("常備回購、貼現窗口", "銀行向聯儲借錢", "有用量＝有銀行需要後備資金"),
        ("AI 借款人 CDS、債價", "CoreWeave、Oracle 等借錢的成本", "第三方參考報價，日期不一")]),
    ("美債", "", [
        ("投標倍數、間接投標", "拍賣有多少買家；間接投標代表外國及其他投資者", "低於平均＝買家偏少"),
        ("2 年期", "最貼近聯儲政策預期", "上升＝市場預期政策更緊"),
        ("10 年期", "增長、通脹加上期限溢價", "看升跌來自實質孳息還是通脹預期"),
        ("10 年減 2 年", "曲線形狀", "牛市變陡＝兩端都跌、短端跌得多；熊市變陡＝兩端都升、長端升得多"),
        ("實質孳息、通脹預期", "10 年期的兩個組成部分", "說明 10 年期升跌的來源")]),
    ("股債波動", "", [
        ("VIX、VIX9D、VIX3M", "標普 500 期權對 30 日、9 日、3 個月波幅的定價", "期權市場預期的波動大小"),
        ("期限結構", "VIX9D、VIX、VIX3M 的高低", "短期高於長期＝倒掛，恐慌集中在眼前幾週"),
        ("VXN、MOVE、GVZ", "納指、美債、黃金的期權波幅", "比較哪個市場的波動升得最多；VIX 大升而 MOVE 小升＝股市危機，未到債市")]),
    ("資金", "", [
        ("TGA", "財政部在聯儲的現金", "上升＝從銀行體系抽走資金"),
        ("淨流動性", "聯儲資產減 TGA 減逆回購", "減少＝銀行體系的流動性收縮")]),
    ("板塊輪動及市場狀態", "", [
        ("輪動圖（RRG）", "相對大市的強弱及其動量", "量度相對，不是升跌：大市下跌時，跌得少的板塊也會在「領先」"),
        ("市場狀態（R29）", "標普及等權標普距 60 日高位、HYG÷IEF 對 50 日線", "看板唯一經回測的讀數，見頁底")]),
]


def meanings_html():
    out = ['<h2>一、每個指標的意思</h2>']
    for title, lead, rows in MEANINGS:
        out.append(f"<h3>{escape(title)}</h3>" + (f'<p class="sub">{escape(lead)}</p>' if lead else "")
                   + grid(["指標", "量度甚麼", "怎樣讀"], [tr(r) for r in rows]))
    return "".join(out)


# ---------- part 2: the three checklists, 現時 read live ----------

def data():
    """The readings the checklists use, from the local build (site_private/data)."""
    S = {x["ticker"]: x for x in ms.load("sectors")}
    C = ms.first("cross_asset") or {}
    H = C.get("havens") or {}
    return dict(
        session=ms.load("refresh_meta")[0]["session"], S=S, r=ms.first("rates_now") or {}, b=ms.first("breadth_now") or {},
        R={x["pair"]: x for x in ms.load("ratio_summary")}, H=H,
        week={x["t"]: x["r"] for x in ((H.get("week") or {}).get("rows") or [])},
        corr={x["t"]: x for x in H.get("rows") or []}, down={x["t"]: x for x in ((H.get("down") or {}).get("rows") or [])},
        V={x["t"]: x for x in ((C.get("vol") or {}).get("rows") or [])},
        P={x["t"]: x for x in ((C.get("proxies") or {}).get("rows") or [])})


def pct(v, d=1):
    return "—" if v is None else f"{ms.sg(v, d)}%"


def term_shape(V):
    a, b, c = (V.get(t, {}).get("v") for t in ("^VIX9D", "^VIX", "^VIX3M"))
    if None in (a, b, c):
        return None, "—"
    txt = f"VIX9D {a:.1f}、VIX {b:.1f}、VIX3M {c:.1f}"
    return ("倒掛" if a > b > c else "正常" if a < b < c else "不一"), txt


def checklist(title, lead, head, rows, sides):
    """rows: (check, if_a, if_b, now_text, lean) where lean is one of sides or None; then a count line."""
    count = {s: sum(1 for r in rows if r[4] == s) for s in sides}
    body = [tr([c, a, b, now, lean or "—"], now=(3,)) for c, a, b, now, lean in rows]
    summary = "；".join(f"{n} 項較像「{s}」" for s, n in count.items())
    return (f"<h3>{escape(title)}</h3>" + (f'<p class="sub">{escape(lead)}</p>' if lead else "")
            + grid(head, body) + f'<p class="sum">現時：{escape(summary)}（其餘不適用或看幅度）。</p>')


def metals_rows(D):
    r, wk, corr, down, V, S = D["r"], D["week"], D["corr"], D["down"], D["V"], D["S"]
    gld, real, uup = wk.get("GLD"), r.get("real10_1w"), wk.get("UUP")
    A, B = "基本因素", "跟股市被賣"
    rows = []
    lean = None if None in (gld, real) or gld >= 0 else (B if real < 0 else A)
    rows.append(("實質孳息", "黃金跌時，實質孳息在升", "實質孳息跌，黃金照跌",
                 f"實質孳息一週 {ms.sg(real)} 基點；黃金 {pct(gld)}" if None not in (gld, real) else "—", lean))
    rows.append(("美元", "美元大升，可解釋金價跌幅", "美元沒有大動", f"美元（UUP）{pct(uup)}；黃金 {pct(gld)}" if None not in (gld, uup) else "—", None))
    g = corr.get("GLD") or {}
    b = ms.corr_band(D["H"].get("window") or 63)
    word = ms.corr_word(g.get("corr"), b)
    rows.append(("與納指的相關", "接近 0 或負數", "明顯正數，高過平常",
                 f"{ms.fmt_chg(g.get('corr'), 2)}（五年中位 {ms.fmt_chg(g.get('corr_med5y'), 2)}）" if g else "—",
                 B if word == "同向" else A if g else None))
    d = down.get("GLD")
    rows.append(("SMH 大跌的日子", "黃金升或不動", "黃金一起跌",
                 f"平均 {pct(d['avg_pct'], 2)}，{d['up_share']}% 的日子上升" if d else "—",
                 None if not d else B if d["avg_pct"] < 0 and d["up_share"] < 50 else A if d["avg_pct"] > 0 and d["up_share"] > 50 else None))
    gv = V.get("^GVZ") or {}
    rows.append(("黃金波幅 GVZ", "平穩", "金價跌而波幅升（被當成風險資產）",
                 f"GVZ 一週 {pct(gv.get('chg_1w_pct'))}，一年第 {gv.get('pct1y', '—')} 百分位" if gv else "—",
                 None if not gv or gld is None else B if gld < 0 and (gv.get("chg_1w_pct") or 0) > 0 else A if gld < 0 else None))
    gdx = (S.get("GDX") or {}).get("r1w")
    rows.append(("金礦股 GDX", "跌幅與金價相若", "跌得比金價多（有股票的成分）", f"GDX {pct(gdx)}；黃金 {pct(gld)}" if None not in (gdx, gld) else "—",
                 None if None in (gdx, gld) or gld >= 0 else B if gdx < gld else A))
    return rows, (A, B)


def breadth_rows(D):
    S, b, r, V = D["S"], D["b"], D["r"], D["V"]
    A, B = "輪動", "全面轉差"
    sec = [x for x in S.values() if x.get("group") == "sector" and x["ticker"] != "GDX" and x.get("r1w") is not None]
    down = [x for x in sec if x["r1w"] < 0]
    rows = [("板塊絕對升跌", "有板塊上升", "幾乎全部下跌", f"{len(down)}／{len(sec)} 個板塊一週下跌",
             B if sec and len(down) == len(sec) else A if len(down) < len(sec) / 2 else None)]
    rsp = (S.get("RSP") or {}).get("r1w")
    rows.append(("等權標普", "持平或上升", "一樣下跌", f"一週 {pct(rsp)}", None if rsp is None else B if rsp < 0 else A))
    ad = b.get("ad_1w")
    rows.append(("升跌線", "持平或上升", "與 SPY 一起跌", f"一週 {ms.sg(ad)}" if ad is not None else "—", None if ad is None else B if ad < 0 else A))
    p50, p50w = b.get("pct50"), b.get("pct50_1w")
    rows.append(("高於 50 日線比例", "大致不變或上升", "下跌", f"{p50:.0f}%（一週前 {p50w:.0f}%）" if None not in (p50, p50w) else "—",
                 None if None in (p50, p50w) else B if p50 < p50w else A))
    mc = b.get("mcclellan")
    rows.append(("麥克連", "0 或以上", "負數", ms.sg(mc, 1) if mc is not None else "—", None if mc is None else B if mc < 0 else A))
    tiers = [r.get(f"{k}_oas_1w") for k in ("hy", "ig", "bb", "ccc")]
    wide = sum(1 for v in tiers if v is not None and v > 0)
    rows.append(("信用息差（HY、IG、BB、CCC）", "平靜或收窄", "擴闊，並傳到 BB、IG", f"一週 {wide}／4 個擴闊（至 {ms.md(r.get('hy_oas_date'))}）",
                 B if wide == 4 else A if wide == 0 else None))
    shape, txt = term_shape(V)
    rows.append(("VIX 期限結構", "正常（短低長高）", "倒掛", f"{txt}：{shape}" if shape else "—",
                 B if shape == "倒掛" else A if shape == "正常" else None))
    try:
        st = ms.state_of(ms.market())
        name = ms.STATE_NAME.get(st, "不屬任何狀態")
        lean = A if st in ("rotation", "narrow_weak") else B if st in ("broad", "worse") else None
    except Exception:
        name, lean = "—", None
    rows.append(("市場狀態（R29）", "「輪動」或「指數弱」", "「大市下跌」或「大市惡化」", name, lean))
    return rows, (A, B)


def bounce_rows(D):
    S, b, r, R, P, V = D["S"], D["b"], D["r"], D["R"], D["P"], D["V"]
    A, B = "得到確認", "未得到確認"
    rows = []
    rsp, iwm = (S.get("RSP") or {}).get("r1w"), (S.get("IWM") or {}).get("r1w")
    rows.append(("參與程度", "等權標普、小型股一起上升", "只有大型股或 AI 反彈", f"等權標普 {pct(rsp)}、小型股 {pct(iwm)}（一週）",
                 None if None in (rsp, iwm) else A if rsp > 0 and iwm > 0 else B))
    p20, p20w = b.get("pct20"), b.get("pct20_1w")
    rows.append(("高於 20 日線比例", "比一週前高", "比一週前低", f"{p20:.0f}%（一週前 {p20w:.0f}%）" if None not in (p20, p20w) else "—",
                 None if None in (p20, p20w) else A if p20 > p20w else B))
    ad, mc = b.get("ad_1w"), b.get("mcclellan")
    rows.append(("升跌線", "一週回升", "一週下跌", f"一週 {ms.sg(ad)}" if ad is not None else "—", None if ad is None else A if ad > 0 else B))
    rows.append(("麥克連", "0 以上", "仍是負數", ms.sg(mc, 1) if mc is not None else "—", None if mc is None else A if mc > 0 else B))
    hy, ccc = r.get("hy_oas_1w"), r.get("ccc_oas_1w")
    rows.append(("HY、CCC 息差", "一週收窄", "一週擴闊", f"HY {ms.sg(hy)}、CCC {ms.sg(ccc)} 基點（至 {ms.md(r.get('hy_oas_date'))}）" if None not in (hy, ccc) else "—",
                 None if None in (hy, ccc) else A if hy < 0 and ccc < 0 else B if hy > 0 and ccc > 0 else None))
    bz = P.get("BIZD")
    rows.append(("私募信貸代理 BIZD", "一週回穩或上升", "一週下跌", f"一週 {pct(bz['chg_5'])}" if bz else "—",
                 None if not bz else A if bz["chg_5"] >= 0 else B))
    h = R.get("HYG_IEF") or {}
    rows.append(("HYG÷IEF", "回到 50 日線以上", "仍低於 50 日線", f"對 50 日線 {pct(h.get('vs_50d'))}" if h.get("vs_50d") is not None else "—",
                 None if h.get("vs_50d") is None else A if h["vs_50d"] > 0 else B))
    shape, txt = term_shape(V)
    rows.append(("VIX 期限結構", "回到正常斜率", "仍然倒掛", f"{txt}：{shape}" if shape else "—",
                 A if shape == "正常" else B if shape == "倒掛" else None))
    return rows, (A, B)


def checklists_html():
    try:
        D = data()
    except Exception as e:  # a data file changed shape: keep the fixed text, say so
        print("guide data failed:", repr(e), flush=True)
        return '<h2>二、三張核對表</h2><p class="sub">現時讀數暫時未能載入。</p>'
    r = D["r"]
    out = ['<h2>二、三張核對表（現時一欄每次載入頁面時由看板數據填入）</h2>',
           f'<p class="sub">數據日期：股價 {ms.md(D["session"])}；信用息差 {ms.md(r.get("hy_oas_date"))}；孳息 {ms.md(r.get("nominal10_date"))}。'
           "「較像」一欄只按定義歸類：正負號、與一週前比較，或 63 日相關的 ±0.25 抽樣範圍；不是經測試的訊號。</p>"]
    for fn, title, lead, head in (
            (metals_rows, "A. 金屬是跟股市被賣，還是基本因素出事", "黃金的基本因素主要是實質孳息和美元；逐項核對。",
             ["核對", "如果是基本因素", "如果是跟股市被賣", "現時", "較像"]),
            (breadth_rows, "B. 輪動，還是全面轉差", "輪動＝資金由一組轉到另一組；全面轉差＝大部分股票及信用一起轉差。",
             ["讀數", "輪動", "全面轉差", "現時", "較像"]),
            (bounce_rows, "C. 反彈有沒有得到其他讀數確認", "反彈出現時逐項看；經回測的三項見頁底「反彈確認」。股價反彈而信用不改善，是常見的假反彈特徵（一般原則，這一句未經測試）。",
             ["讀數", "得到確認（較健康）", "未得到確認（較易再跌）", "現時", "較像"])):
        try:
            rows, sides = fn(D)
            out.append(checklist(title, lead, head, rows, sides))
        except Exception as e:
            print(f"guide checklist failed: {title}", repr(e), flush=True)
            out.append(f"<h3>{escape(title)}</h3><p class='sub'>現時讀數暫時未能生成。</p>")
    return "".join(out)


def bounce_html():
    """The tested bounce check (R29): today's three checks, then what bounces did by the number of checks met."""
    try:
        items, score, dd60 = ms.bounce_check()
    except Exception as e:
        print("guide bounce failed:", repr(e), flush=True)
        return '<p class="sub">反彈確認暫時未能生成。</p>'
    now = grid(["項目", "現時", "達到"], [tr([name, reading, "是" if met else "否" if met is not None else "—"], now=(1,)) for name, met, reading in items])
    hist = grid(["達到項數", "20 日內跌穿之前 20 日低位", "每段跌勢只計一次", "60 日後中位數", "60 日後上升"],
                [tr([f"{k} 項" + ("（現時）" if k == score else ""), f"{ms.BOUNCE_FAIL[k][0]}%", f"{ms.BOUNCE_FAIL[k][1]}%",
                     ms.BOUNCE_F60[k][0], f"{ms.BOUNCE_F60[k][1]}%"]) for k in range(4)])
    where = (f"標普現距 60 日高位 {ms.sg(dd60, 1)}%，" + ("屬測試的範圍。" if dd60 is not None and dd60 <= -5 else "未到測試的範圍（5% 或以上），以下歷史只作參考。")
             if dd60 is not None else "")
    return ("<h3>反彈確認（R29，2007 年以來的回測）</h3>"
            '<p class="sub">測試的反彈日：標普距 60 日高位跌 5% 或以上時，單日升 0.5% 或以上（共 388 日，整體 42% 失敗）。'
            "失敗＝之後 20 個交易日內收市跌穿之前 20 日的低位，即牛市陷阱。三項中最有分辨力的是標普回到 20 日平均以上"
            "（做到的失敗率 24%，做不到的 56%）。</p>"
            + f'<p class="sum">現時 {score}／3 項達到。{escape(where)}</p>' + now + hist
            + '<p class="sub">失敗不等於之後幾個月都跌：0 項達到的反彈，60 日後中位數仍是正數；但途中常先再創新低。這是歷史比率，不是預測。</p>')


def tested_html():
    try:
        line = ms.line_state()
    except Exception:
        line = "市場狀態暫時未能生成。"
    return ('<h2>三、經測試的數字</h2><h3>市場狀態（R29）</h3>' + f"<p>{escape(line)}</p>" + bounce_html()
            + '<p class="sub">其他讀數都是按定義的描述，不是經測試的訊號，不要單憑一項下判斷。</p>')


def guide_page():
    body = ('<div class="guide"><h1>讀法</h1>'
            '<p class="sub">這頁說明看板上每個指標量度甚麼、怎樣讀，以及三張核對表。只描述數據，不是買賣建議。</p>'
            + meanings_html() + checklists_html() + tested_html() + "</div>")
    return page("讀法", STYLE + body)
