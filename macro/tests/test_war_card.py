import importlib.util
import fcntl
import json
import sys
import inspect
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if not (Path(__file__).resolve().parents[2] / "server" / "macro_summary.py").exists():
    raise unittest.SkipTest("server/ not found next to macro/")
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "macro"))
import macro_summary as ms  # noqa: E402
import news_feed  # noqa: E402
import pages  # noqa: E402

# server/serve.py under its own name (macro/serve.py is imported as "serve" by test_refresh)
_spec = importlib.util.spec_from_file_location("server_serve", ROOT / "server" / "serve.py")
board = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(board)

LADDER = [{"n": n, "name": f"名{n}", "means": "x"} for n in range(1, 7)]


def ev(d, r):
    return {"date": d, "text": "t", "rung": r, "source": "https://e.com", "provider": "P"}


def head(i, published, topic="war"):
    return {"topic": topic, "title": f"headline {i}", "publisher": f"pub {i}", "published": published,
            "link": f"https://news.example/{i}", "official": False}


FEED = {"fetched_at": "2026-11-15T15:38:16Z", "attempted_at": "2026-11-15T15:38:16Z",
        "items": [head(i, f"2026-11-15T{i:02d}:05:00Z") for i in range(12)] + [head(99, "2026-11-15T23:00:00Z", "oil_iran")]}


class WarCardTest(unittest.TestCase):
    def render(self, events, feed=None, **extra):
        war = {"ladder": LADDER, "events": events, **extra}
        with mock.patch.object(ms, "oil_row", return_value={"manual": {"war": war}}):
            return ms.war_card(today="2026-11-16", feed=feed or {})

    def test_two_lines(self):
        h = self.render([ev("2026-11-10", 2), ev("2026-11-12", 5), ev("2026-11-14", 5), ev("2026-11-15", 3)])
        self.assertIn("最近一宗事件：第 3 級「名3」（11月15日）", h)
        self.assertIn("清單期內到過的最高級別：第 5 級「名5」，最近一次在 11月14日（清單由 11月10日 起）", h)
        self.assertNotIn("現處級別：", h)

    def test_note_optional(self):
        self.assertNotIn("未經獨立證實", self.render([ev("2026-11-10", 2)]))
        self.assertIn("未經獨立證實", self.render([ev("2026-11-10", 2)], note="未經獨立證實"))


class WarHeadlinesTest(unittest.TestCase):
    def render(self, feed, last="2026-11-15"):
        war = {"ladder": LADDER, "events": [ev("2026-11-10", 2), ev(last, 5)], "updated": "2026-11-15"}
        with mock.patch.object(ms, "oil_row", return_value={"manual": {"war": war}}):
            return ms.war_card(today="2026-11-16", feed=feed)

    def test_newest_ten_war_headlines_first_then_the_hand_kept_part(self):
        h = self.render(FEED)
        auto, hand = h.index("最新報道（自動抓取）"), h.index("已整理的事件及升級階梯（人手整理至 11月15日）")
        self.assertNotIn("未核實", h)
        self.assertLess(auto, hand)
        self.assertIn("上次成功抓取：11月15日 15:38（英國時間）", h)
        shown = [i for i in range(12) if f">headline {i}<" in h]
        self.assertEqual(shown, list(range(2, 12)))  # the newest ten; other topics are not shown
        self.assertNotIn("headline 99", h)
        self.assertLess(h.index("headline 11"), h.index("headline 10"))
        self.assertIn("<td class=rb-left>11月15日 11:05</td>", h); self.assertIn("pub 11", h)
        self.assertIn('href="https://news.example/11"', h)
        self.assertLess(hand, h.index("最近一宗事件："))
        self.assertNotIn("自動抓取的報道比已整理的清單新", h)  # same UK date as the newest event

    def test_a_later_headline_adds_one_line_and_no_rung(self):
        h = self.render(FEED, last="2026-11-14")
        self.assertIn("自動抓取的報道比已整理的清單新，級別未包括這些報道。", h)
        self.assertIn("最近一宗事件：第 5 級「名5」（11月14日）", h)

    def test_no_social_posts_even_if_an_old_feed_still_holds_them(self):
        post = {"handle": "SomeAccount", "text": "post text", "published": "2026-11-15T10:00:00Z",
                "link": "https://x.com/SomeAccount/status/1"}
        h = self.render({**FEED, "social": [{"handle": "SomeAccount", "ok": True, "posts": [post]}]})
        self.assertNotIn("post text", h); self.assertNotIn("社交媒體", h); self.assertNotIn("x.com", h)

    def test_no_feed(self):
        h = self.render({})
        self.assertIn("未有自動抓取紀錄", h); self.assertIn("最近一宗事件：", h)


class LiveNewsPageTest(unittest.TestCase):
    def test_news_page_reads_the_stored_feed_and_keeps_hand_notes(self):
        built = {"issues": [], "feed": {"attempted_at": "2026-11-15T10:00:00Z", "items": [
            {**head(1, "2026-11-15T09:00:00Z", "oil_iran"), "note": "含義", "issue": None}]}}
        stored = {"attempted_at": "2026-11-15T15:00:00Z", "fetched_at": "2026-11-15T15:00:00Z",
                  "items": [head(2, "2026-11-15T14:00:00Z"), head(1, "2026-11-15T09:00:00Z", "oil_iran")], "social": []}
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "news_feed.json"; path.write_text(json.dumps([stored]))
            with mock.patch.object(pages, "NEWS_FEED", path):
                doc = pages.live_feed(built)
            with mock.patch.object(pages, "NEWS_FEED", Path(t) / "missing.json"):
                self.assertIs(pages.live_feed(built), built)
        self.assertEqual(doc["feed"]["fetched_at"], "2026-11-15T15:00:00Z")
        self.assertEqual([(x["link"], x["note"]) for x in doc["feed"]["items"]],
                         [("https://news.example/2", ""), ("https://news.example/1", "含義")])
        self.assertIn("每 30 分鐘擷取", pages.news_body(doc))


DOC = {"updated": "2026-11-15", "rule": "規則", "driver": "一句", "issues": [
    {"id": "a", "title": "議題甲", "status": "進行中", "reviewed": "2026-11-15", "topics": ["oil_iran"], "now": "正在發生的事",
     "facts": [{"text": "命令拒絕駁回", "src": [{"tag": "已核實（一手文件）", "name": "法院命令", "date": "2026-11-14", "url": "https://court.example/68.pdf"},
                                              {"tag": "看板數據", "name": "看板", "date": "2026-11-13"}]}],
     "meaning": ["合起來看：甲", "機構：乙"],
     "stocks": [{"who": "Micron（MU）", "effect": "法律風險上升", "why": "須答辯"}],
     "watch": [{"when": "未公佈", "if": "監管調查", "then": "風險上升（記憶體廠）"}, {"date": "2026-11-17", "if": "承擔上升", "then": "長約延續"}]},
    {"id": "b", "title": "議題乙", "status": "已有結論", "reviewed": "2026-11-14", "topics": ["war"], "now": "乙"}]}


def feed(n_war=12):
    items = [head(i, f"2026-11-15T{i:02d}:05:00Z") for i in range(n_war)] + [head(90 + i, f"2026-11-14T0{i}:00:00Z", "credit") for i in range(3)]
    return {"fetched_at": "2026-11-15T15:00:00Z", "attempted_at": "2026-11-15T15:00:00Z", "items": items,
            "topics": [{"id": "credit", "name": "信用市場"}, {"id": "oil_iran", "name": "油市"}, {"id": "war", "name": "戰事"}]}


class IssuePageTest(unittest.TestCase):
    def test_numbered_cards_with_three_blocks_in_order(self):
        h = pages.news_body(DOC, today="2026-11-15")
        self.assertIn("<h2>1. 議題甲 ", h); self.assertIn("<h2>2. 議題乙 ", h)
        card = h[h.index('id="issue-a"'):h.index('id="issue-b"')]
        heads = ["正在發生甚麼", "事實與連接", "含義", "受影響股票及影響"]   # `now` of an old card still shows; nothing else is added
        pos = [card.index(f"<h3>{x}") for x in heads]
        self.assertEqual(pos, sorted(pos))
        self.assertEqual(card.count("推論（依據上面的事實）"), 1)  # once, at the heading
        self.assertNotIn("<span class=\"tag\">推論</span>", card)
        for col in ("公司／組別", "影響（方向）", "原因"):
            self.assertIn(f"<th>{col}</th>", card)
        for gone in ("取決於", "依據：", "<h3>連接</h3>", "<h3>事實</h3>", "各方想做甚麼"):
            self.assertNotIn(gone, card)
        self.assertIn('〔已核實（一手文件）：<a href="https://court.example/68.pdf"', card)
        self.assertIn("〔看板數據：看板 11月13日〕", card)
        self.assertIn("要看：11月17日如果承擔上升 → 長約延續", card)   # an old card's watch rows are folded into 含義 as one line
        self.assertNotIn("<h3>要留意", card)
        self.assertLess(card.index("11月17日"), card.index("未公佈"))
        self.assertNotIn("未核實", h)

    def test_headline_label_is_report_or_official(self):
        self.assertIn(">報道<", pages.feed_label({"official": False}))
        self.assertIn(">官方公告<", pages.feed_label({"official": True}))


class HeadlineGroupTest(unittest.TestCase):
    def test_groups_are_the_issue_topics_only_with_ten_newest_each(self):
        gs = pages.groups(feed(), DOC["issues"])
        self.assertEqual([(g["id"], g["issue"]) for g in gs], [("oil_iran", 1), ("war", 2)])  # a topic with no issue has no group of its own
        war = gs[1]["items"]
        self.assertEqual(len(war), pages.SHOW)
        self.assertEqual([x["link"] for x in war], [f"https://news.example/{i}" for i in range(11, 1, -1)])  # newest ten
        self.assertEqual(gs[0]["items"], [])

    def test_page_shows_groups_without_the_attached_block(self):
        h = pages.news_body({**DOC, "feed": feed()}, today="2026-11-15")
        self.assertNotIn("已連到議題的新聞", h)
        self.assertIn('<h2>戰事<span class="tag">議題 2</span></h2>', h)
        self.assertLess(h.index("<h2>油市"), h.index("<h2>戰事"))
        # a topic with no issue is no longer dropped silently: it is listed in the 未有議題的主題 strip (count and newest headline)
        strip = h[h.index("未有議題的主題"):h.index("二、議題")]
        self.assertIn("信用市場", strip); self.assertIn("<td class=\"nowrap\">3</td>", strip); self.assertIn("headline 92", strip)
        self.assertNotIn("信用市場", h[:h.index("未有議題的主題")])
        self.assertEqual(h.count('href="https://news.example/'), pages.SHOW + 1)  # ten in the groups, one newest headline in the strip


PX = {"AAA": {"ticker": "AAA", "r1d": 1.0, "r1w": 5.0, "rel1w": 3.0, "r1m": -4.0, "rel1m": -6.0},
      "BBB": {"ticker": "BBB", "r1d": -1.0, "r1w": -2.0, "rel1w": -4.0, "r1m": 3.0, "rel1m": 1.0},
      "CCC": {"ticker": "CCC", "r1d": 0.0, "r1w": 1.0, "rel1w": 0.5, "r1m": 1.0, "rel1m": 0.5}}


class DepthPageTest(unittest.TestCase):
    """Schema additions of the 新聞與連接 page: price-reaction column, links, breaks, driver naming every issue, strip, coverage."""

    def label(self, **row):
        return pages.reaction(row, PX)[1]

    def test_reaction_label_compares_the_one_week_relative_return_with_the_expectation(self):
        self.assertEqual(self.label(tickers=["AAA"], expected="跑贏"), "符合論點")
        self.assertEqual(self.label(tickers=["AAA"], expected="跑輸"), "與論點相反")
        self.assertEqual(self.label(tickers=["BBB"], expected="跑輸"), "符合論點")
        self.assertEqual(self.label(tickers=["AAA", "BBB"], expected="跑贏"), "不明")      # the tickers disagree
        self.assertEqual(self.label(tickers=["ZZZ"], expected="跑贏"), "不明")             # no board data
        self.assertEqual(self.label(tickers=["AAA"], expected="無關"), "不明")             # nothing to compare
        self.assertEqual(self.label(tickers=["AAA"]), "")                                  # no expectation, no label
        self.assertEqual(pages.reaction({"tickers": ["BRK.B"], "expected": "跑贏"}, {"BRK-B": PX["AAA"]})[1], "符合論點")  # BRK.B finds BRK-B
        self.assertIn("一週與一個月的相對方向不同", pages.reaction({"tickers": ["AAA"], "expected": "跑贏"}, PX)[2])

    def test_stock_table_has_text_labels_not_symbols_and_old_rows_keep_three_columns(self):
        h = pages.stock_rows([{"who": "甲", "tickers": ["AAA", "ZZZ"], "channel": "收入", "effect": "受惠", "expected": "跑贏",
                               "why": "因", "reaction_note": "手寫說明"}], PX, "2026-11-13")
        for x in ("符合論點", "AAA", "一週+5.0%（相對大市+3.0%）", "ZZZ：看板沒有數據", "手寫說明", "11月13日", "按論點應", "影響項目", "受惠：因"):
            self.assertIn(x, h)
        for sym in ("✓", "✗", "✔", "✘"):
            self.assertNotIn(sym, h)
        old = pages.stock_rows([{"who": "甲", "effect": "乙", "why": "丙"}], PX, "2026-11-13")
        self.assertEqual(old.count("<th>"), 3)
        self.assertEqual(pages.stock_rows([{"who": "甲", "effect": "乙", "why": "丙", "tickers": ["AAA"]}], {}, "").count("<th>"), 5)

    def test_missing_price_data_never_breaks_the_page(self):
        self.assertEqual(pages.price_data("/nonexistent/dir"), {})
        h = pages.news_body({**DOC, "issues": [{**DOC["issues"][0], "stocks": [{"who": "甲", "effect": "乙", "why": "丙", "tickers": ["AAA"], "expected": "跑贏"}]}]},
                            today="2026-11-15", px={}, session="", watch=[])
        self.assertIn("看板沒有數據", h)

    def test_card_has_exactly_three_blocks_and_no_metadata_blocks(self):
        iss = {**DOC["issues"][0], "since": "2026-11-10", "confidence": {"level": "中", "why": "因為"}, "breaks_if": "唯一推翻條件",
               "log": [{"date": "2026-11-15", "change": "改了", "outcome": "不變"}], "links": [{"to": "b", "channel": "通道", "text": "理由"}],
               "watch": [{"date": "2026-11-17", "if": "甲", "then": "乙", "breaks": "推翻", "tickers": ["AAA"]}]}
        h = pages.news_body({**DOC, "issues": [iss, DOC["issues"][1]]}, today="2026-11-15", px=PX, session="", watch=[])
        card = h[h.index('id="issue-a"'):h.index('id="issue-b"')]
        # old fields are still read; breaks_if and watch fold into 含義, the rest is not shown
        for x in ("推翻條件：唯一推翻條件", "要看：11月17日如果甲 → 乙"):
            self.assertIn(x, card)
        for gone in ("看法開始", "把握：", "檢討紀錄", "連到其他議題", "推翻這個看法的條件", "<h3>要留意", "成立則推翻看法", "因為", "改了", "理由"):
            self.assertNotIn(gone, card)
        self.assertEqual(card.count("<h3>"), 4)   # DOC's old card still has its `now` block; new cards have three
        newcard = pages.issue_card(1, {"id": "z", "title": "新", "reviewed": "2026-11-15", "facts": [{"text": "事實", "src": []}],
                                       "meaning": ["含義一"], "stocks": [{"who": "甲", "tickers": ["AAA"], "expected": "跑贏", "why": "因"}]},
                                   "2026-11-15", px=PX, session="")
        heads = [x.split("<")[0] for x in newcard.split("<h3>")[1:]]
        self.assertEqual(heads, ["事實與連接", "含義", "受影響股票及影響"])

    def test_edges_come_from_inline_references_and_old_links(self):
        a = {**DOC["issues"][0], "meaning": ["見 {#b} 及 {#b}、{#nope}、{#a}"]}
        b = {**DOC["issues"][1], "links": [{"to": "a", "channel": "x", "text": "y"}]}
        self.assertEqual(pages.issue_edges([a, b]), {"a": ["b"], "b": ["a"]})   # once each; unknown and self ignored
        h = pages.news_body({**DOC, "issues": [a, b]}, today="2026-11-15", px={}, session="", watch=[])
        self.assertIn('議題 1</a> → <a href="#issue-b">2</a>', h)
        self.assertIn('議題 2</a> → <a href="#issue-a">1</a>', h)
        self.assertIn("見 議題 2 及 議題 2", h)

    def test_driver_may_be_a_list_and_must_name_every_open_issue(self):
        doc = {**DOC, "driver": [{"line": "第一行", "issues": ["a"]}]}
        h = pages.driver_block(doc)
        self.assertIn("第一行", h); self.assertIn('href="#issue-a"', h)
        self.assertNotIn("未被上面任何一行提及", h)           # b is 已有結論, so only a is open
        doc2 = {**DOC, "issues": [DOC["issues"][0], {**DOC["issues"][1], "status": "進行中"}], "driver": [{"line": "只講甲", "issues": ["a", "ghost"]}]}
        h2 = pages.driver_block(doc2)
        self.assertIn("未被上面任何一行提及", h2); self.assertIn('href="#issue-b"', h2); self.assertIn("ghost（不存在）", h2)
        self.assertIn("一句", pages.driver_block(DOC))       # the old one-sentence shape still works

    def test_cross_section_lever_edges_and_coverage(self):
        a = {**DOC["issues"][0], "meaning": ["見 {#b}"], "stocks": [{"who": "甲", "effect": "乙", "why": "丙", "tickers": ["AAA"]}]}
        b = {**DOC["issues"][1]}
        doc = {**DOC, "issues": [a, b], "lever": {"name": "利率", "issue": "b", "text": "共同變量"}}
        h = pages.cross_section(doc, watch=[("AAA", {"AAA"}), ("BBB", {"BBB"}), ("組別甲", {"CCC", "DDD"})])
        for x in ("議題之間的連接", "共同槓桿：利率", "共同變量", "卡內互相引用", "議題 1</a> → <a href=\"#issue-b\">2</a>", "3 項中 1 項", "沒有任何議題涉及：BBB、組別甲"):
            self.assertIn(x, h)
        self.assertEqual(pages.cross_section({"issues": []}, watch=[]), "")

    def test_watchlist_names_come_from_watchlist_md_and_holdings(self):
        # sample names only: the real list, its groups and the holdings are private files outside this repository
        with tempfile.TemporaryDirectory() as t:
            w, hld, grp = Path(t) / "watchlist.md", Path(t) / "holdings.json", Path(t) / "watch_groups.json"
            w.write_text("# x\n\n更新：x。**長期追蹤 3 項**（AAA、組別甲、組別乙；提醒價見下表）。\n", encoding="utf-8")
            hld.write_text(json.dumps({"held": ["XYZ"], "picks": ["CCC", "EEE"]}), encoding="utf-8")
            grp.write_text(json.dumps({"groups": {"組別甲": ["CCC", "DDD"], "組別乙": ["FFF"]}, "aliases": {"group a": "組別甲", "group b": "組別乙"}}), encoding="utf-8")
            items = pages.watch_items_list(w, hld, grp)
            self.assertEqual([n for n, _ in items], ["AAA", "組別甲", "組別乙", "XYZ", "EEE"])   # CCC is inside 組別甲, so not added again
            self.assertIn("FFF", items[2][1]); self.assertEqual(pages.watch_items_list(Path("/nonexistent.md"), hld, grp), [])
            w.write_text("Updated: x. **Long-term list of 3 items** (AAA, Group A, group b; alert levels below).\n", encoding="utf-8")   # English wording
            self.assertEqual([n for n, _ in pages.watch_items_list(w, Path(t) / "none.json", grp)], ["AAA", "組別甲", "組別乙"])
            self.assertEqual([n for n, _ in pages.watch_items_list(w, Path(t) / "none.json", Path(t) / "none2.json")], ["AAA", "Group A", "group b"])   # no groups file: each name is its own ticker
        self.assertEqual(pages.watch_groups(Path("/nonexistent.json")), ({}, {}))

    def test_public_render_never_reads_the_private_watchlist_or_holdings(self):
        # export_site.py renders pages.news_page() into the public static site, so the default must not read watchlist.md or
        # holdings.json; only the local server (news_page(local=True)) adds the coverage line.
        doc = json.loads((ROOT / "evidence" / "news_connect.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as t:
            w, hld = Path(t) / "watchlist.md", Path(t) / "holdings.json"
            w.write_text("# x\n\n**長期追蹤 2 項**（ZZPRIVATE、MSFT；提醒價見下表）。\n", encoding="utf-8")
            hld.write_text(json.dumps({"held": ["QQPRIVATE"], "picks": []}), encoding="utf-8")
            with mock.patch.object(pages, "WATCHLIST", w), mock.patch.object(pages, "HOLDINGS", hld), \
                    mock.patch.object(pages, "load", return_value=doc), mock.patch.object(pages, "live_feed", side_effect=lambda d: d):
                public, local = pages.news_page(), pages.news_page(local=True)
        self.assertFalse(inspect.signature(pages.news_page).parameters["local"].default)
        for x in ("ZZPRIVATE", "QQPRIVATE", "觀察名單覆蓋"):
            self.assertNotIn(x, public)
        for x in ("ZZPRIVATE", "QQPRIVATE", "觀察名單覆蓋"):
            self.assertIn(x, local)
        self.assertEqual(pages.coverage_line([]), "")   # no items given, no file read

    def test_real_page_renders_with_every_open_issue_in_the_driver_and_no_uncovered_topic(self):
        doc = json.loads((ROOT / "evidence" / "news_connect.json").read_text(encoding="utf-8"))
        feed_doc = {**doc, "feed": {"fetched_at": "2026-11-15T15:00:00Z", "items": [],
                                    "topics": [{"id": t[0], "name": t[1]} for t in news_feed.TOPICS]}}
        h = pages.news_body(feed_doc, today="2026-11-15")
        self.assertNotIn("未被上面任何一行提及", h)
        self.assertNotIn("不存在）", h)
        self.assertNotIn("未有議題的主題", h)   # every feed topic has an issue
        for c in h.split('<section class="card issue"')[1:]:
            self.assertEqual([x.split("<")[0] for x in c.split("<h3>")[1:]], ["事實與連接", "含義", "受影響股票及影響"])
        for sym in ("✓", "✗"):
            self.assertNotIn(sym, h)


def iss(i, since=None, fact_date=None, **kw):
    x = {"id": i, "title": f"題{i}", "status": "進行中", "reviewed": "2026-11-15", "topics": [], "now": "x"}
    if since:
        x["since"] = since
    if fact_date:
        x["facts"] = [{"text": "t", "src": [{"tag": "看板數據", "name": "n", "date": fact_date}]}]
    return {**x, **kw}


class IssueOrderTest(unittest.TestCase):
    """Cards are numbered oldest story first (by `since`, else the earliest dated fact); every number on the page follows."""

    def test_sort_key_since_then_earliest_fact_then_file_order(self):
        issues = [iss("late", "2026-11-12"), iss("tie_b", "2026-11-05", "2026-11-03"), iss("tie_a", "2026-11-05", "2026-11-01"),
                  iss("fallback", None, "2026-11-04"), iss("undated"), iss("early", "2026-07-24", "2026-09-01")]
        self.assertEqual([i["id"] for i in pages.ordered_issues(issues)],
                         ["early", "fallback", "tie_a", "tie_b", "late", "undated"])  # fallback (11-04) sorts before the 11-05 tie; undated last
        same = [iss("x", "2026-11-05"), iss("y", "2026-11-05")]
        self.assertEqual([i["id"] for i in pages.ordered_issues(same)], ["x", "y"])      # full tie keeps the file order
        self.assertEqual(pages.ordered_issues(None), [])

    def test_every_number_on_the_page_follows_the_sorted_order(self):
        # file order is newest first; the page must show oldest first as 1, 2, 3
        c = iss("c", "2026-11-12", topics=["credit"], meaning=["回到最舊：{#a}"], now="見 {#a}，另見 {#b}")
        b = iss("b", "2026-11-05", topics=["war"])
        a = iss("a", "2026-07-24", topics=["oil_iran"])
        doc = {"updated": "2026-11-15", "rule": "r", "issues": [c, b, a],
               "driver": [{"line": "三個議題", "issues": ["c", "b", "a"]}], "lever": {"name": "槓桿", "issue": "a", "text": "t"},
               "feed": feed(2)}
        h = pages.news_body(doc, today="2026-11-15", px={}, session="", watch=[])
        pos = [h.index(f'id="issue-{x}"') for x in "abc"]
        self.assertEqual(pos, sorted(pos))                                               # cards appear a, b, c
        for n, x in ((1, "a"), (2, "b"), (3, "c")):
            self.assertIn(f"<h2>{n}. 題{x} ", h)
            self.assertIn(f'<a class="chip out n" href="#issue-{x}">議題 {n}</a>', h)  # driver chips
        self.assertIn('<span class="tag">議題 1</span>', h)                              # headline group of oil_iran (issue a)
        self.assertIn('<h2>戰事<span class="tag">議題 2</span></h2>', h)                # war belongs to b
        self.assertIn("見 議題 1，另見 議題 2", h)                                        # {#id} resolved at render
        self.assertIn('議題 3</a> → <a href="#issue-a">1</a>', h)                        # inline references: c → a
        self.assertIn("共同槓桿：槓桿</b>（<a href=\"#issue-a\">議題 1</a>）", h)         # lever hub
        self.assertEqual(pages.resolve_refs("{#nope}", []), "議題（不存在）")

    def test_real_file_is_chronological_and_numbered_from_one(self):
        doc = json.loads((ROOT / "evidence" / "news_connect.json").read_text(encoding="utf-8"))
        order = pages.ordered_issues(doc["issues"])
        sinces = [i["since"] for i in order]
        self.assertEqual(sinces, sorted(sinces))
        h = pages.news_body({**doc, "feed": {"items": [], "topics": []}}, today="2026-11-15", px={}, session="", watch=[])
        for n, i in enumerate(order, 1):
            self.assertIn(f"<h2>{n}. {i['title']} ", h)
        self.assertNotIn("{#", h)
        self.assertNotIn("議題（不存在）", h)


class BackgroundNewsTest(unittest.TestCase):
    def run_once(self, stored_age, running=False, fetch=None):
        calls, stop = [], threading.Event()
        stop.set()  # one round only
        with mock.patch.object(board, "news_time", return_value=time.time() - stored_age), \
                mock.patch.object(board, "refresh_running", return_value=running):
            board.news_loop(stop, every=1800, check=0, fetch=fetch or (lambda: calls.append(1)))
        return calls

    def test_fetches_only_when_the_stored_feed_is_old_and_no_refresh_runs(self):
        self.assertEqual(self.run_once(31 * 60), [1])
        self.assertEqual(self.run_once(5 * 60), [])
        self.assertEqual(self.run_once(31 * 60, running=True), [])

    def test_never_raises_into_the_server(self):
        def boom():
            raise RuntimeError("x")
        self.run_once(31 * 60, fetch=boom)
        with mock.patch.object(news_feed, "build", side_effect=OSError("disk")):
            self.assertFalse(board.fetch_news())

    def test_stored_time_and_refresh_lock(self):
        with tempfile.TemporaryDirectory() as t:
            feed = Path(t) / "news_feed.json"
            feed.write_text(json.dumps([{"attempted_at": "2026-11-15T15:00:00Z", "fetched_at": "2026-11-15T14:00:00Z"}]))
            self.assertEqual(board.news_time(feed), 1794754800.0)
            self.assertEqual(board.news_time(Path(t) / "none.json"), 0.0)
            lock = Path(t) / "lock"
            self.assertFalse(board.refresh_running(lock))
            with lock.open("a") as h:
                fcntl.flock(h, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assertTrue(board.refresh_running(lock))
                fcntl.flock(h, fcntl.LOCK_UN)
            self.assertFalse(board.refresh_running(lock))



class MacroViewTest(unittest.TestCase):
    def test_every_patch_matches_the_built_page(self):
        # server/macro_view.py edits the served page by exact text; a page change that breaks one shows the red notice
        import build_site
        import macro_view
        page = (build_site.PAGE.replace("__TOKENS__", build_site.TOKENS).replace("__SHIM__", build_site.SHIM)
                .replace("__BODY__", (ROOT / "macro" / "index.html").read_text()))
        self.assertEqual(macro_view.missing_patches(page), [])
        out = macro_view.regroup(page, {"macro": "", "oil": ""})
        self.assertNotIn("未能重組", out)
        for sel in macro_view.HIDE:
            self.assertIn(f'id="{sel[1:]}"', page)

if __name__ == "__main__":
    unittest.main()
