"""Headlines for the 新聞與連接 page (news_feed.py) and the page's hand-kept file; saved sample XML, no network."""
from datetime import datetime, timezone
import json
import re
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import build_site
import news_feed
from news_feed import build, merge, parse, title_key
from refresh import fetch_news

FIX = Path(__file__).resolve().parent / "fixtures"
NOW = datetime(2026, 11, 15, 15, 0, tzinfo=timezone.utc)
GOOGLE = dict(id="google_ai_memory", name="Google News", topic="ai_memory", kind="google")
FED = dict(id="fed_speeches", name="Federal Reserve（講話）", topic="fed_liquidity", kind="official", skip=("enforcement action",))


def item(link, title, published, topic="ai_memory", official=False, publisher="Reuters"):
    return dict(topic=topic, title=title, publisher=publisher, published=published, link=link, official=official)


class Parse(unittest.TestCase):
    def test_google_items_take_publisher_and_drop_its_suffix(self):
        rows = {r["link"]: r for r in parse((FIX / "news_google.xml").read_bytes(), GOOGLE)}
        r = rows["https://news.google.com/rss/articles/CBMiAAA2?oc=5"]
        self.assertEqual((r["title"], r["publisher"], r["published"], r["topic"], r["official"]),
                         ("UPDATE 1-Judge lets DRAM antitrust case proceed", "Reuters", "2026-11-15T14:02:00Z", "ai_memory", False))
        # the allow-list name replaces Google's publisher text
        self.assertEqual(rows["https://news.google.com/rss/articles/CBMiAAA3?oc=5"]["publisher"], "Nikkei")
        self.assertNotIn("https://news.google.com/rss/articles/CBMiAAA6?oc=5", rows)  # no date: left out
        self.assertNotIn("https://news.google.com/rss/articles/CBMiAAA4?oc=5", rows)  # stock-picking headline
        self.assertTrue(rows["https://news.google.com/rss/articles/CBMiAAA7?oc=5"]["official"])  # published by federalreserve.gov
        for r in rows.values():  # only these fields are stored, never article text
            self.assertEqual(set(r), {"topic", "title", "publisher", "published", "link", "official"})

    def test_only_official_sites_and_named_publishers_pass(self):
        rows = {r["link"]: r for r in parse((FIX / "news_google.xml").read_bytes(), GOOGLE)}
        for dropped in ("AAA1", "AAA8", "AAA5"):  # TokenPost, Wccftech, an unknown site
            self.assertNotIn(f"https://news.google.com/rss/articles/CBMi{dropped}?oc=5", rows)
        self.assertEqual(set(rows), {f"https://news.google.com/rss/articles/CBMi{k}?oc=5" for k in ("AAA2", "AAA3", "AAA7")})
        for host in ("tokenpost.com", "wccftech.com", "x.com", "twitter.com", "fourweekmba.com", "mlq.ai", "litnews.ai",
                     "finance.yahoo.com", "investing.com", "tradingview.com", "fool.com", "kucoin.com", "substack.com",
                     "biggo.com", "news.lavx.hu"):
            self.assertIsNone(news_feed.on_host(host, news_feed.PUBLISHERS), host)
        self.assertEqual(news_feed.on_host("www.reuters.com", news_feed.PUBLISHERS), "reuters.com")
        self.assertEqual(news_feed.on_host("asia.nikkei.com", news_feed.PUBLISHERS), "nikkei.com")
        self.assertIsNone(news_feed.on_host("notreuters.com", news_feed.PUBLISHERS))

    def test_no_social_media_source(self):
        for name in ("X_HANDLES", "X_URL", "parse_x", "fetch_x", "social"):
            self.assertFalse(hasattr(news_feed, name), name)
        self.assertFalse(any("twitter" in f["url"] or "x.com" in f["url"] for f in news_feed.feeds()))

    def test_official_rss_skips_listed_words_and_reads_us_zone_dates(self):
        fed = parse((FIX / "news_fed.xml").read_bytes(), FED)
        self.assertEqual([r["title"][:6] for r in fed], ["Waller"])
        self.assertTrue(fed[0]["official"]); self.assertEqual(fed[0]["publisher"], "Federal Reserve（講話）")
        eia = parse((FIX / "news_eia.xml").read_bytes(), dict(id="eia", name="EIA", topic="oil_iran", kind="official",
                                                              only=news_feed.OIL_WORDS))
        self.assertEqual([(r["title"][:10], r["published"]) for r in eia], [("EIA foreca", "2026-11-12T14:00:00Z")])

    def test_atom_entries(self):
        rows = parse((FIX / "news_atom.xml").read_bytes(), dict(id="bis", name="Federal Register（BIS）", topic="export_tariffs",
                                                               kind="official", skip=("information collection",)))
        self.assertEqual([(r["link"][-7:], r["published"]) for r in rows], [("example", "2026-11-09T05:00:00Z")])

    def test_host_limited_google_feed_keeps_only_that_site(self):
        feed = dict(id="treasury", name="US Treasury", topic="fed_liquidity", kind="official", host="federalreserve.gov")
        rows = parse((FIX / "news_google.xml").read_bytes(), feed)
        self.assertEqual([(r["title"], r["publisher"]) for r in rows], [("Fed statement mirrored by Google", "US Treasury")])


class Merge(unittest.TestCase):
    def test_duplicates_by_link_and_near_identical_title_keep_the_stored_item(self):
        stored = [item("https://a/1", "Judge Lets DRAM Antitrust Case Proceed", "2026-11-15T13:19:18Z")]
        fresh = [item("https://a/1", "Judge Lets DRAM Antitrust Case Proceed (updated)", "2026-11-15T14:00:00Z"),
                 item("https://a/2", "UPDATE 1-Judge lets DRAM antitrust case proceed!", "2026-11-15T14:02:00Z"),
                 item("https://a/3", "SK Hynix plans more HBM4 wafers", "2026-11-15T10:14:37Z")]
        out = merge(stored, fresh, now=NOW)
        self.assertEqual([x["link"] for x in out], ["https://a/1", "https://a/3"])
        self.assertEqual(title_key("UPDATE 1-Judge lets DRAM antitrust case proceed!"), title_key("Judge Lets DRAM Antitrust Case Proceed"))

    def test_seven_day_window_and_cap_per_topic_keep_noted_links(self):
        fresh = [item(f"https://a/{i}", f"story {i}", f"2026-11-15T{i:02d}:00:00Z") for i in range(14)]
        fresh += [item("https://a/old", "old story", "2026-11-07T14:59:00Z"),
                  item("https://a/fed", "fed release", "2026-11-10T09:00:00Z", "fed_liquidity", True),
                  item("https://a/gone", "topic no longer configured", "2026-11-15T09:00:00Z", "retired")]
        out = merge([], fresh, keep_links={"https://a/0"}, now=NOW)
        links = [x["link"] for x in out]
        mem = [x for x in out if x["topic"] == "ai_memory"]
        self.assertEqual(len(mem), news_feed.CAP + 1)  # newest twelve plus the noted one
        self.assertIn("https://a/0", links); self.assertNotIn("https://a/1", links)
        self.assertNotIn("https://a/old", links); self.assertNotIn("https://a/gone", links)
        self.assertIn("https://a/fed", links)
        self.assertEqual(links, sorted(links, key=lambda l: next(x["published"] for x in out if x["link"] == l), reverse=True))

    def test_stored_items_from_publishers_off_the_list_are_dropped(self):
        stored = [item("https://a/1", "Judge lets DRAM case proceed", "2026-11-15T13:00:00Z", publisher="TOKENPOST"),
                  item("https://a/2", "Fed holds", "2026-11-15T12:00:00Z", "fed_liquidity", True, publisher="Federal Reserve"),
                  item("https://a/3", "Memory prices rise", "2026-11-15T11:00:00Z")]
        self.assertEqual([x["link"] for x in merge(stored, [], keep_links={"https://a/1"}, now=NOW)], ["https://a/2", "https://a/3"])

    def test_official_items_have_their_own_cap(self):
        fresh = [item(f"https://g/{i}", f"report {i}", f"2026-11-15T{i:02d}:00:00Z", "fed_liquidity") for i in range(14)]
        fresh += [item("https://fed/1", "speech", "2026-11-10T09:00:00Z", "fed_liquidity", True)]
        self.assertIn("https://fed/1", [x["link"] for x in merge([], fresh, now=NOW)])


class FailureTolerance(unittest.TestCase):
    def fetcher(self, failing=()):
        google, fed = (FIX / "news_google.xml").read_bytes(), (FIX / "news_fed.xml").read_bytes()

        def get(url):
            if url in failing or "*" in failing:
                raise TimeoutError("timed out")
            if "federalreserve.gov/feeds/speeches" in url:
                return fed
            if "news.google.com" in url and "DRAM" in url:
                return google
            return b"<rss><channel></channel></rss>"
        return get

    def test_one_failing_feed_keeps_its_items_and_last_success(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t)
            first = build(out, hand=out / "none.json", now=NOW, fetcher=self.fetcher())
            speech = "https://www.federalreserve.gov/newsevents/speech/waller20261110a.htm"
            self.assertIn(speech, [x["link"] for x in first["items"]])
            later = datetime(2026, 11, 15, 18, 0, tzinfo=timezone.utc)
            fed_url = next(f["url"] for f in news_feed.feeds() if f["id"] == "fed_speeches")
            second = build(out, hand=out / "none.json", now=later, fetcher=self.fetcher({fed_url}))
            st = {f["id"]: f for f in second["feeds"]}
            self.assertFalse(st["fed_speeches"]["ok"]); self.assertEqual(st["fed_speeches"]["last_ok"], "2026-11-15T15:00:00Z")
            self.assertIn("TimeoutError", st["fed_speeches"]["error"])
            self.assertIn(speech, [x["link"] for x in second["items"]])  # the failed feed's items stay
            self.assertEqual(second["fetched_at"], "2026-11-15T18:00:00Z")

    def test_every_feed_failing_leaves_the_previous_items_and_fetch_time(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t)
            first = build(out, hand=out / "none.json", now=NOW, fetcher=self.fetcher())
            later = datetime(2026, 11, 25, 9, 0, tzinfo=timezone.utc)  # even past the window: nothing is pruned
            second = build(out, hand=out / "none.json", now=later, fetcher=self.fetcher({"*"}))
            self.assertEqual(second["items"], first["items"])
            self.assertEqual((second["fetched_at"], second["attempted_at"]), ("2026-11-15T15:00:00Z", "2026-11-25T09:00:00Z"))
            self.assertTrue(all(not f["ok"] for f in second["feeds"]))
            self.assertEqual(json.loads((out / "news_feed.json").read_text())[0]["items"], first["items"])

    def test_malformed_xml_is_one_feed_error_not_a_crash(self):
        with tempfile.TemporaryDirectory() as t:
            row = build(Path(t), hand=Path(t) / "none.json", now=NOW, fetcher=lambda url: b"<rss><channel><item>")
            self.assertTrue(all("ParseError" in f["error"] for f in row["feeds"]))
            self.assertEqual((row["items"], row["fetched_at"]), ([], None))

    def test_noted_links_survive_the_cap(self):
        with tempfile.TemporaryDirectory() as t:
            hand = Path(t) / "news_connect.json"
            hand.write_text(json.dumps({"news": {"https://news.google.com/rss/articles/CBMiAAA3?oc=5": {"note": "x"}}}))
            with patch.object(news_feed, "CAP", 1):
                row = build(Path(t), hand=hand, now=NOW, fetcher=self.fetcher())
            mem = [x["link"] for x in row["items"] if x["topic"] == "ai_memory"]
            # newest report (AAA1 and AAA8 are off the publisher list), the noted report, and the newest official item
            self.assertEqual(mem, ["https://news.google.com/rss/articles/CBMiAAA2?oc=5",
                                   "https://news.google.com/rss/articles/CBMiAAA3?oc=5",
                                   "https://news.google.com/rss/articles/CBMiAAA7?oc=5"])

    def test_refresh_never_fails_on_the_news_step(self):
        with tempfile.TemporaryDirectory() as t:
            log = Path(t) / "execution.log"
            for exc in (subprocess.TimeoutExpired(["news_feed.py"], 300), subprocess.CalledProcessError(1, ["news_feed.py"]), OSError("x")):
                with patch("refresh.subprocess.run", side_effect=exc):
                    self.assertFalse(fetch_news(Path(t), {}, log))
            self.assertIn("previous feed kept", log.read_text())


def fixture_fetcher(url):
    """Every Google News search answers with the saved Google sample, the Fed speeches feed with its sample, every
    other feed with an empty channel."""
    if "news.google.com" in url:
        return (FIX / "news_google.xml").read_bytes()
    if "federalreserve.gov/feeds/speeches" in url:
        return (FIX / "news_fed.xml").read_bytes()
    return b"<rss><channel></channel></rss>"


class RepeatAndAge(unittest.TestCase):
    def test_fetching_the_same_items_twice_adds_no_duplicates(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t)
            first = build(out, hand=out / "none.json", now=NOW, fetcher=fixture_fetcher)
            later = datetime(2026, 11, 15, 15, 30, tzinfo=timezone.utc)
            second = build(out, hand=out / "none.json", now=later, fetcher=fixture_fetcher)
            links = [x["link"] for x in second["items"]]
            self.assertTrue(first["items"])
            self.assertEqual(len(links), len(set(links)))
            self.assertEqual(len({title_key(x["title"]) for x in second["items"]}), len(links))
            self.assertEqual(second["items"], first["items"])
            self.assertEqual(json.loads((out / "news_feed.json").read_text())[0]["items"], first["items"])

    def test_items_older_than_seven_days_are_dropped(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t)
            first = build(out, hand=out / "none.json", now=NOW, fetcher=fixture_fetcher)
            later = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)  # cut-off 13 Nov 12:00
            second = build(out, hand=out / "none.json", now=later, fetcher=lambda url: b"<rss><channel></channel></rss>")
            self.assertTrue(any(x["published"] < "2026-11-13T12:00:00Z" for x in first["items"]))
            self.assertTrue(second["items"])
            self.assertTrue(all(x["published"] >= "2026-11-13T12:00:00Z" for x in second["items"]))
            self.assertEqual([x["link"] for x in second["items"]],
                             [x["link"] for x in first["items"] if x["published"] >= "2026-11-13T12:00:00Z"])


class War(unittest.TestCase):
    def test_war_topic_has_several_two_day_searches(self):
        war = [f for f in news_feed.feeds() if f["topic"] == "war"]
        self.assertGreaterEqual(len(war), 2)
        self.assertEqual([f["id"] for f in war], [f"google_war_{n}" for n in range(1, len(war) + 1)])
        self.assertTrue(all("when:2d" in f["url"] for f in war))
        self.assertTrue(all("when:7d" in f["url"] for f in news_feed.feeds() if "news.google.com" in f["url"] and f["topic"] != "war"))
        ids = [f["id"] for f in news_feed.feeds()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_a_headline_the_war_search_also_finds_is_filed_under_war_once(self):
        stored = [item("https://a/1", "Iran strikes Bahrain oil port", "2026-11-15T08:38:26Z", "oil_iran")]
        fresh = [item("https://a/2", "UPDATE 1-Iran strikes Bahrain oil port", "2026-11-15T09:00:00Z", "war"),
                 item("https://a/3", "Oil prices rise", "2026-11-15T09:00:00Z", "oil_iran"),
                 item("https://a/3", "Oil prices rise", "2026-11-15T09:00:00Z", "war")]
        out = merge(stored, fresh, now=NOW)
        self.assertEqual([(x["link"], x["topic"]) for x in out], [("https://a/3", "war"), ("https://a/1", "war")])
        # a war item found again by another topic stays under war
        again = merge(out, [item("https://a/1", "Iran strikes Bahrain oil port", "2026-11-15T08:38:26Z", "oil_iran")], now=NOW)
        self.assertEqual({x["topic"] for x in again}, {"war"})


class Page(unittest.TestCase):
    def test_build_attaches_hand_notes_by_link_and_keeps_feed_local(self):
        doc = {"issues": [{"id": "a", "title": "A"}], "news": {
            "https://n/1": {"issue": "a", "note": "含義一"}, "https://n/2": {"issue": "missing", "note": "含義二"}}}
        feed = [{"fetched_at": "2026-11-15T15:00:00Z", "items": [item("https://n/1", "one", "2026-11-15T10:00:00Z"),
                                                                item("https://n/2", "two", "2026-11-15T09:00:00Z"),
                                                                item("https://n/3", "three", "2026-11-15T08:00:00Z")]}]
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "news_connect.json"; path.write_text(json.dumps(doc))
            with patch.object(build_site, "NEWS_CONNECT", path):
                out = build_site.news_connect({"news_feed": feed})[0]
                bad = build_site.news_connect({"news_feed": [{"items": [None]}]})[0]
            with patch.object(build_site, "NEWS_CONNECT", Path(t) / "missing.json"):
                self.assertTrue(build_site.news_connect({})[0]["missing"])
        got = {x["link"]: (x["issue"], x["note"]) for x in out["feed"]["items"]}
        self.assertEqual(got, {"https://n/1": ("a", "含義一"), "https://n/2": (None, "含義二"), "https://n/3": (None, "")})
        self.assertNotIn("news", out); self.assertEqual(out["feed"]["fetched_at"], "2026-11-15T15:00:00Z")
        self.assertEqual(bad["feed"]["items"], [])  # an unreadable feed never fails the build

    def test_hand_file_shape(self):
        path = build_site.NEWS_CONNECT
        if not path.is_file():
            self.skipTest("no news_connect.json in this checkout")
        doc = json.loads(path.read_text())
        self.assertTrue(doc["driver"] and build_site._iso(doc["updated"]))
        for gone in ("domains", "links", "force", "week"):
            self.assertNotIn(gone, doc)
        text = json.dumps(doc, ensure_ascii=False)
        for word in ("未核實", "說法來源", "網上流傳", "社交媒體", "x.com/", "twitter.com"):
            self.assertNotIn(word, text)  # nothing unverified and nothing sourced from social posts
        ids = [i["id"] for i in doc["issues"]]
        self.assertEqual(len(ids), len(set(ids)))
        tags = ("已核實（一手文件）", "報道（具名媒體）", "第三方估算", "看板數據")
        topics = {t[0] for t in news_feed.TOPICS}
        board = {x["ticker"] for f in ("stocks", "sectors") for x in json.loads((build_site.ROOT / "data" / f"{f}.json").read_text())}
        board |= {t.replace("-", ".") for t in board}
        stock_old = {"who", "effect", "why"}
        stock_new = {"tickers", "channel", "expected", "reaction_note"}
        channels = {"收入", "利潤率", "成本", "折現率", "融資", "法律"}
        for iss in doc["issues"]:
            self.assertIn(iss["status"], ("進行中", "已有結論"))
            self.assertTrue(iss["title"] and build_site._iso(iss["reviewed"]))   # `now` is an old field: new cards fold it into 事實與連接
            self.assertTrue(set(iss["topics"]) <= topics)
            for gone in ("chain", "actors", "next", "what"):
                self.assertNotIn(gone, iss)
            self.assertTrue(1 <= len(iss["facts"]) <= 8)
            for f in iss["facts"]:
                self.assertTrue(f["text"] and f["src"])
                for x in f["src"]:
                    self.assertIn(x["tag"], tags)
                    self.assertTrue(x["name"] and build_site._iso(x["date"]))
                    if x["tag"] in ("已核實（一手文件）", "報道（具名媒體）"):
                        self.assertTrue(x["url"].startswith("https://"))
            self.assertTrue(3 <= len(iss["meaning"]) <= 8 and all(isinstance(m, str) and m for m in iss["meaning"]))
            # stock rows: {who, effect, why} are required; the depth fields are optional but checked when present
            for r in iss["stocks"]:
                self.assertTrue({"who", "why"} <= set(r) <= stock_old | stock_new, r)
                self.assertTrue(r["who"] and r["why"])
                self.assertTrue(r.get("effect") or "tickers" in r, "an old three-column row needs `effect`")
                if "expected" in r:
                    self.assertIn(r["expected"], ("跑贏", "跑輸", "無關"))
                    self.assertTrue(r.get("tickers"), "an expectation needs tickers to be checked against the tape")
                if "channel" in r:
                    self.assertTrue(r["channel"] and set(r["channel"].split("、")) <= channels, r["channel"])
                for t in r.get("tickers") or []:
                    self.assertIn(t, board, f"{t} is not in the board's stocks.json or sectors.json")
                if "reaction_note" in r:
                    self.assertTrue(r["reaction_note"].strip())
            for w in iss.get("watch") or []:   # old field: still read, folded into 含義 by the page
                self.assertTrue(w["if"] and w["then"])
                self.assertTrue(build_site._iso(w["date"]) if w.get("date") else w.get("when"))
                if "breaks" in w:
                    self.assertIn(w["breaks"], ("確認", "推翻"))
                for t in w.get("tickers") or []:
                    self.assertIn(t, board)
            # three sections only: the old blocks are gone from the file and 含義 ends with 推翻條件 then 要看
            for gone in ("now", "watch", "breaks_if", "links", "confidence", "log"):
                self.assertNotIn(gone, iss, f"{iss['id']}: {gone} is folded into the three sections")
            self.assertTrue(iss["meaning"][-2].startswith("推翻條件：") and iss["meaning"][-1].startswith("要看："))
            self.assertEqual(sum(m.startswith("推翻條件") for m in iss["meaning"]), 1)
            # issue-level depth fields (optional): since, confidence, links, breaks_if, log
            self.assertTrue(build_site._iso(iss["since"]), "every issue needs `since`: the page numbers issues by it")
            self.assertTrue(build_site._iso(iss["since"]) <= build_site._iso(iss["reviewed"]))
            self.assertNotRegex(json.dumps(iss, ensure_ascii=False), r"議題 ?[0-9]", "refer to an issue as {#id}; the page computes its number")
            if "confidence" in iss:
                self.assertIn(iss["confidence"]["level"], ("高", "中", "低"))
                self.assertTrue(iss["confidence"]["why"])
            if "breaks_if" in iss:
                self.assertTrue(isinstance(iss["breaks_if"], str) and iss["breaks_if"].strip())
            for l in iss.get("links") or []:
                self.assertIn(l["to"], ids)
                self.assertNotEqual(l["to"], iss["id"])
                self.assertTrue(l["channel"] and l["text"])
            for g in iss.get("log") or []:
                self.assertTrue(build_site._iso(g["date"]) and g["change"])
                self.assertIn(g["outcome"], ("確認", "削弱", "不變"))
        # no repetition across cards: no 30-character stretch of a fact or 含義 line is written in two different cards
        def grams(i):
            text = re.sub(r"\{#[A-Za-z0-9_]+\}", "", "".join(f["text"] for f in i["facts"]) + "".join(i["meaning"]))
            return {text[k:k + 30] for k in range(len(text) - 29)}
        for n, a in enumerate(doc["issues"]):
            for b in doc["issues"][n + 1:]:
                self.assertFalse(grams(a) & grams(b), f"{a['id']} repeats {b['id']}")
        rates = next(i for i in doc["issues"] if i["id"] == "tga_rates_credit")
        for i in doc["issues"]:
            if i is not rates:
                self.assertNotIn("31.7 基點", json.dumps(i, ensure_ascii=False), "the rates move is stated once, in the rates card")
        # the top line names every open issue (a plain sentence is the old shape and is not checked)
        if isinstance(doc["driver"], (list, dict)):
            lines = doc["driver"] if isinstance(doc["driver"], list) else [doc["driver"]]
            named = set()
            for x in lines:
                self.assertTrue(x["line"] and x["issues"])
                self.assertTrue(set(x["issues"]) <= set(ids))
                named |= set(x["issues"])
            self.assertEqual(named, {i["id"] for i in doc["issues"] if i["status"] == "進行中"})
        for url, n in doc["news"].items():
            self.assertTrue(url.startswith("https://"))
            self.assertTrue(n.get("note"))
            self.assertNotRegex(n["note"], r"議題 ?[0-9]")


if __name__ == "__main__":
    unittest.main()
