"""Headlines for the 新聞與連接 page and the 戰事最新進展 card of the local board. No AI calls.

refresh.py runs this on every data refresh (not --render-only), and server/serve.py runs build()
in the background every 30 minutes while the local board is up. It reads public RSS and Atom feeds: one or more Google
News search feeds per topic and the official feeds in OFFICIAL. For each item it stores only the headline, publisher,
published time (UTC), link, topic and whether it came from an official source, never article text, in
data/news_feed.json. It keeps the last WINDOW_DAYS days, de-duplicates by link and by near-identical title (the same
words once case, punctuation and wire prefixes such as "UPDATE 2-" are ignored), and keeps the newest CAP items per
topic plus every item whose link has a hand-written note in evidence/news_connect.json. A headline found by a
search of a PRIORITY topic (the war) is filed under that topic even when another topic found it first.

Sources: official feeds and named established publishers only. A Google News item is kept only when its publisher's
site is an official site (OFFICIAL_HOSTS) or is on the publisher allow-list (PUBLISHERS); social media, aggregators,
blogs, crypto or token sites and unknown sites are dropped, and so are stored items whose publisher is not on the list.
No social-media source is read.

Failures never reach the board refresh: a feed that fails keeps its earlier items and its time of last success, and
its error is listed; when every feed fails, the previous items stay as they were and only the attempt time and errors
change. refresh.py also catches any error or timeout of this whole script.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import json
import os
from pathlib import Path
import re
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

# ---------------- What to fetch (edit here) ----------------
WINDOW_DAYS = 7  # items published in the last seven days are kept
CAP = 10         # per topic: the newest CAP reports and the newest CAP official items (the page shows the newest ten of
                 # each topic group); items with a hand-written note in evidence/news_connect.json are kept as well
GOOGLE = "https://news.google.com/rss/search?q={q}+when:{d}d&hl=en-US&gl=US&ceid=US:en"
# id, name on the page (in display order), Google News search query (one, or a tuple of several, per topic)
TOPICS = [
    ("ai_memory", "AI 晶片及記憶體供應（HBM、DRAM、反壟斷）",
     '"HBM4" OR "HBM3E" OR "high-bandwidth memory" OR "HBM chips" OR DRAM OR "memory chip" OR "memory chips" '
     'OR "memory prices" OR "memory antitrust"'),
    ("ai_capex", "AI 資本開支及融資（超大型雲端、CoreWeave、Oracle、發債）",
     '"AI capex" OR "AI spending" OR hyperscalers OR CoreWeave OR "Oracle debt" OR "Oracle bonds" '
     'OR "data center financing" OR "data center debt"'),
    ("fed_liquidity", "聯儲、財政部及流動性（TGA、回購、拍賣）",
     '"Fed officials" OR "Federal Reserve officials" OR FOMC OR "Fed rate" OR "Treasury General Account" '
     'OR "repo market" OR "bank reserves" OR "Treasury auction" OR "Treasury yields"'),
    ("credit", "信用市場",
     '("credit spreads" OR "junk bonds" OR "high-yield bonds" OR "leveraged loans" OR "private credit" '
     'OR "investment-grade bonds") -tokenized -crypto'),
    ("oil_iran", "油市及伊朗戰事（Hormuz）",
     '"oil prices" OR "crude oil" OR Hormuz OR "Iran war" OR OPEC'),
    ("china_macro", "中國宏觀",
     '"China economy" OR "China\'s economy" OR PBOC OR "People\'s Bank of China" OR "China exports" '
     'OR "China property" OR "Chinese yuan" OR "China deflation"'),
    ("export_tariffs", "出口管制及關稅",
     '"export controls" OR "chip exports" OR "Entity List" OR "Bureau of Industry and Security" OR "Section 232" '
     'OR "reciprocal tariffs" OR "tariff rates"'),
    ("war", "戰事最新報道（伊朗、海灣及荷姆茲）",
     ('Iran (strike OR attack OR missile OR drone) (Bahrain OR Gulf OR Hormuz OR Saudi OR UAE OR Qatar OR Kuwait)',
      '(tanker OR port OR refinery OR terminal OR pipeline) (attack OR strike OR explosion OR drone) '
      '(Gulf OR Hormuz OR Bahrain OR "Red Sea")',
      'Iran (ceasefire OR talks OR negotiations OR truce)')),
]
SEARCH_DAYS = {"war": 2}  # Google News search window in days for these topics (others: WINDOW_DAYS)
PRIORITY = ("war",)       # a headline found by these topics' searches is filed under them, not under the other topic
# Headlines with these words are dropped from every feed (stock-picking and promotional pieces, not news)
SKIP_WORDS = ("stock a buy", "a buy after", "too late to buy", "prediction:", "should you buy", "stock to buy",
              "stocks to buy", "where will", "still undervalued", "time to buy", "buy the dip")
# Official feeds. "only": keep titles containing one of these words (empty = keep all); "skip": drop titles containing
# one of these words; "host": for a Google News feed, keep only items whose publisher site ends with this host.
# The US Treasury publishes no press-release RSS feed, so its press releases come from a Google News search limited to
# home.treasury.gov, and only items published by that site are kept.
OIL_WORDS = ("oil", "crude", "petroleum", "gasoline", "diesel", "distillate", "fuel", "brent", "wti", "opec", "hormuz",
             "iran", "refiner", "inventor", "strategic petroleum reserve")
OFFICIAL = [
    dict(id="fed_press", name="Federal Reserve", topic="fed_liquidity",
         url="https://www.federalreserve.gov/feeds/press_all.xml", skip=("enforcement action",)),
    dict(id="fed_speeches", name="Federal Reserve（講話）", topic="fed_liquidity",
         url="https://www.federalreserve.gov/feeds/speeches.xml"),
    dict(id="treasury", name="US Treasury", topic="fed_liquidity", url=GOOGLE.format(q="site:home.treasury.gov", d=WINDOW_DAYS),
         host="treasury.gov", skip=("sanction",)),
    dict(id="treasury_iran", name="US Treasury", topic="oil_iran", url=GOOGLE.format(q="site:home.treasury.gov", d=WINDOW_DAYS),
         host="treasury.gov", only=("iran", "oil", "petroleum", "hormuz", "tanker", "shipping")),
    dict(id="eia_press", name="EIA", topic="oil_iran", url="https://www.eia.gov/rss/press_rss.xml", only=OIL_WORDS),
    dict(id="eia_today", name="EIA", topic="oil_iran", url="https://www.eia.gov/rss/todayinenergy.xml", only=OIL_WORDS),
    dict(id="bis", name="Federal Register（BIS）", topic="export_tariffs",
         url="https://www.federalregister.gov/api/v1/documents.rss?conditions%5Bagencies%5D%5B%5D=industry-and-security-bureau&order=newest",
         skip=("information collection",)),
    dict(id="sec", name="SEC", topic="credit", url="https://www.sec.gov/news/pressreleases.rss",
         only=("credit", "debt", "bond", "treasury", "money market", "private fund", "clearing", "fixed income")),
]
# A Google News item published by one of these sites is also labelled 官方公告
OFFICIAL_HOSTS = ("federalreserve.gov", "treasury.gov", "eia.gov", "bis.gov", "commerce.gov", "sec.gov",
                  "federalregister.gov", "bls.gov", "ustr.gov")
# Publisher allow-list: a Google News item is kept only when its publisher's site (the <source url> host, or a subdomain
# of it) is listed here or in OFFICIAL_HOSTS. The name is what the page shows. Named established news organisations,
# wire services, legal and trade newspapers, and one exchange; no social media, aggregators, blogs or crypto sites.
PUBLISHERS = {
    # wires and international
    "reuters.com": "Reuters", "apnews.com": "AP", "afp.com": "AFP", "bloomberg.com": "Bloomberg",
    "bloomberglaw.com": "Bloomberg Law", "wsj.com": "WSJ", "ft.com": "Financial Times", "economist.com": "The Economist",
    "nytimes.com": "The New York Times", "washingtonpost.com": "The Washington Post", "cnbc.com": "CNBC",
    "marketwatch.com": "MarketWatch", "barrons.com": "Barron's", "axios.com": "Axios", "politico.com": "Politico",
    "theinformation.com": "The Information", "fortune.com": "Fortune", "businessinsider.com": "Business Insider",
    "latimes.com": "Los Angeles Times", "theguardian.com": "The Guardian", "bbc.com": "BBC", "bbc.co.uk": "BBC",
    "cnn.com": "CNN", "nbcnews.com": "NBC News", "cbsnews.com": "CBS News", "abcnews.go.com": "ABC News",
    "abcnews.com": "ABC News", "npr.org": "NPR", "foxbusiness.com": "Fox Business",
    # legal
    "law360.com": "Law360", "mlex.com": "MLex", "law.com": "Law.com", "courthousenews.com": "Courthouse News",
    # Asia and Pacific
    "nikkei.com": "Nikkei", "japantimes.co.jp": "The Japan Times", "kyodonews.net": "Kyodo News",
    "scmp.com": "South China Morning Post", "caixinglobal.com": "Caixin", "yna.co.kr": "Yonhap",
    "koreaherald.com": "The Korea Herald", "koreajoongangdaily.joins.com": "Korea JoongAng Daily",
    "koreajoongangdaily.com": "Korea JoongAng Daily", "koreatimes.co.kr": "The Korea Times", "chosun.com": "Chosun Ilbo",
    "kedglobal.com": "The Korea Economic Daily", "hankyung.com": "The Korea Economic Daily", "mk.co.kr": "Maeil Business",
    "sedaily.com": "Seoul Economic Daily", "etnews.com": "ETNews", "focustaiwan.tw": "Focus Taiwan (CNA)",
    "taipeitimes.com": "Taipei Times", "digitimes.com": "DigiTimes", "straitstimes.com": "The Straits Times",
    "channelnewsasia.com": "CNA", "afr.com": "Australian Financial Review", "abc.net.au": "ABC (Australia)",
    "indiatimes.com": "The Times of India / The Economic Times", "livemint.com": "Mint",
    "hindustantimes.com": "Hindustan Times", "thehindu.com": "The Hindu", "business-standard.com": "Business Standard",
    "indianexpress.com": "The Indian Express",
    # Middle East and Europe
    "aljazeera.com": "Al Jazeera", "thenationalnews.com": "The National", "arabnews.com": "Arab News",
    "gulfnews.com": "Gulf News", "gulf-times.com": "Gulf Times", "al-monitor.com": "Al-Monitor",
    "timesofisrael.com": "The Times of Israel", "aa.com.tr": "Anadolu Agency", "dw.com": "DW", "france24.com": "France 24",
    "lemonde.fr": "Le Monde", "handelsblatt.com": "Handelsblatt", "spiegel.de": "Der Spiegel",
    # energy, shipping, exchange
    "spglobal.com": "S&P Global", "argusmedia.com": "Argus", "lloydslist.com": "Lloyd's List",
    "tradewindsnews.com": "TradeWinds", "gcaptain.com": "gCaptain", "cmegroup.com": "CME Group",
}
# ------------------------------------------------------------

HERE = Path(__file__).resolve().parent
HAND = HERE.parent / "evidence" / "news_connect.json"
UA = "Mozilla/5.0 (compatible; local-board-news/1.0)"
MAX_BYTES = 5_000_000
ATOM = "{http://www.w3.org/2005/Atom}"
RSS1 = "{http://purl.org/rss/1.0/}"
DC = "{http://purl.org/dc/elements/1.1/}"


def feeds():
    """Every feed to read: the official ones first (so an official copy of a headline wins), then the Google News
    searches of each topic (id google_<topic>, or google_<topic>_<n> when a topic has several)."""
    out = [dict(f, kind="official") for f in OFFICIAL]
    for tid, name, query in TOPICS:
        queries = (query,) if isinstance(query, str) else tuple(query)
        for n, q in enumerate(queries, 1):
            out.append(dict(id="google_" + tid + (f"_{n}" if len(queries) > 1 else ""), name=f"Google News：{name}",
                            topic=tid, kind="google",
                            url=GOOGLE.format(q=urllib.parse.quote(q), d=SEARCH_DAYS.get(tid, WINDOW_DAYS))))
    return out


def fetch(url, timeout=20, accept="application/rss+xml, application/atom+xml, application/xml, text/xml"):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        body = res.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError("feed larger than expected")
    return body


def when(text):
    """A feed date (RFC 822 as in RSS, or ISO 8601 as in Atom) as a UTC ISO string, or None."""
    text = " ".join((text or "").split())
    if not text:
        return None
    try:
        d = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        try:
            d = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _text(node, *tags):
    for t in tags:
        x = node.find(t)
        if x is not None and (x.text or "").strip():
            return " ".join(x.text.split())
    return ""


def parse(body, feed):
    """The items of one RSS 2.0, RSS 1.0 or Atom feed as dicts with title, publisher, published, link, topic and
    official. Items without a title, an http(s) link or a date are left out, and so is a Google News item whose
    publisher's site is neither official nor on the allow-list (its publisher then takes the allow-list name)."""
    root = ET.fromstring(body)
    nodes = root.findall(".//item") or root.findall(f".//{RSS1}item") or root.findall(f".//{ATOM}entry")
    out = []
    for n in nodes:
        title = _text(n, "title", f"{RSS1}title", f"{ATOM}title")
        link = _text(n, "link", f"{RSS1}link")
        if not link:
            a = next((x for x in n.findall(f"{ATOM}link") if x.get("rel", "alternate") == "alternate"), None)
            link = (a.get("href") or "").strip() if a is not None else ""
        published = when(_text(n, "pubDate", f"{DC}date", f"{ATOM}published", f"{ATOM}updated"))
        publisher, site = feed["name"], ""
        src = n.find("source")  # Google News: <source url="publisher's site">publisher</source>; title ends " - publisher"
        if src is not None and (src.text or "").strip():
            name, site = " ".join(src.text.split()), urllib.parse.urlsplit(src.get("url") or "").hostname or ""
            if title.endswith(" - " + name):
                title = title[: -len(" - " + name)].rstrip()
            if feed["kind"] == "google":
                publisher = name
        elif feed["kind"] == "google" or feed.get("host"):
            continue
        if not title or not published or not link.startswith(("https://", "http://")):
            continue
        low = title.lower()
        if feed.get("host") and not (site == feed["host"] or site.endswith("." + feed["host"])):
            continue
        if feed.get("only") and not any(w in low for w in feed["only"]):
            continue
        if any(w in low for w in feed.get("skip", ()) + SKIP_WORDS):
            continue
        official = feed["kind"] == "official" or on_host(site, OFFICIAL_HOSTS) is not None
        if not official:
            known = on_host(site, PUBLISHERS)
            if known is None:
                continue  # not an official site and not a named established publisher
            publisher = PUBLISHERS[known]
        out.append(dict(topic=feed["topic"], title=title, publisher=publisher, published=published, link=link,
                        official=official))
    return out


def on_host(site, hosts):
    """The entry of hosts that site is, or is a subdomain of, or None."""
    site = (site or "").lower()
    return next((h for h in hosts if site == h or site.endswith("." + h)), None)


def allowed(item):
    """True for an official item or one whose publisher is a name on the allow-list."""
    return bool(item.get("official")) or item.get("publisher") in ALLOWED_NAMES


ALLOWED_NAMES = frozenset(PUBLISHERS.values())


def title_key(title):
    """Near-identical titles share this key: case, punctuation, spacing and wire prefixes are ignored."""
    t = unicodedata.normalize("NFKC", title).lower()
    t = re.sub(r"^(update \d+|exclusive|analysis|factbox|explainer|breakingviews|instant view|corrected)\s*[-:–—]\s*", "", t)
    return re.sub(r"[\W_]+", " ", t).strip()


def merge(previous, fresh, keep_links=(), now=None):
    """Stored items first, so a stored item keeps its link (hand notes are keyed by link); then de-duplicate by link and
    near-identical title, drop items older than WINDOW_DAYS, and keep per topic the newest CAP reports and the newest CAP
    official items, plus every item whose link is in keep_links. Items that are neither official nor from a publisher on
    the allow-list are dropped, stored ones included. When a PRIORITY topic's search finds a headline already kept under
    another topic, the kept item moves to the PRIORITY topic."""
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    known = {t[0] for t in TOPICS}
    by_link, by_title, items = {}, {}, []
    for it in list(previous) + list(fresh):
        if it.get("topic") not in known or not it.get("published") or it["published"] < cutoff or not allowed(it):
            continue
        key = title_key(it.get("title") or "")
        if not key:
            continue
        kept = by_link.get(it.get("link"), by_title.get(key))
        if kept is not None:
            if it["topic"] in PRIORITY and kept["topic"] not in PRIORITY:
                kept["topic"] = it["topic"]
            continue
        row = {k: it.get(k) for k in ("topic", "title", "publisher", "published", "link", "official")}
        by_link[it["link"]] = by_title[key] = row
        items.append(row)
    keep, out = set(keep_links), []
    for tid, _, _ in TOPICS:
        for official in (True, False):
            group = sorted((x for x in items if x["topic"] == tid and bool(x["official"]) == official),
                           key=lambda x: x["published"], reverse=True)
            out += [x for i, x in enumerate(group) if i < CAP or x["link"] in keep]
    return sorted(out, key=lambda x: x["published"], reverse=True)


def noted_links(path=HAND):
    try:
        return set((json.loads(Path(path).read_text()).get("news") or {}))
    except (OSError, ValueError, AttributeError):
        return set()


def build(out_dir, hand=HAND, now=None, fetcher=fetch, workers=8):
    """Fetch every feed, merge with data/news_feed.json and write it back. Returns the row written."""
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    path = Path(out_dir) / "news_feed.json"
    try:
        prev = json.loads(path.read_text())[0]
    except (OSError, ValueError, IndexError, KeyError):
        prev = {}
    prev_status = {f.get("id"): f for f in prev.get("feeds", [])}
    todo = feeds()

    def one(feed):
        try:
            return feed, parse(fetcher(feed["url"]), feed), None
        except Exception as exc:  # any failure of one feed: keep its earlier items
            return feed, [], f"{type(exc).__name__}: {str(exc)[:120]}"
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, todo))
    fresh, status, errors = [], [], []
    for feed, items, err in results:
        old = prev_status.get(feed["id"]) or {}
        status.append(dict(id=feed["id"], name=feed["name"], topic=feed["topic"], kind=feed["kind"], ok=err is None,
                           n=len(items), last_ok=stamp if err is None else old.get("last_ok"), error=err))
        if err:
            errors.append(f"{feed['name']}: {err}")
        fresh += items
    any_ok = any(s["ok"] for s in status)
    row = dict(attempted_at=stamp, fetched_at=stamp if any_ok else prev.get("fetched_at"), window_days=WINDOW_DAYS,
               cap=CAP, topics=[dict(id=t, name=n) for t, n, _ in TOPICS], feeds=status, errors=errors,
               items=merge(prev.get("items", []), fresh, noted_links(hand), now) if any_ok else prev.get("items", []))
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps([row], ensure_ascii=False, separators=(",", ":")))
    os.replace(tmp, path)
    counts = {t: sum(x["topic"] == t for x in row["items"]) for t, _, _ in TOPICS}
    print(f"  news_feed.json  items={len(row['items'])} {counts}"
          + (f"  errors={row['errors']}" if row["errors"] else ""), flush=True)
    return row


if __name__ == "__main__":
    build(HERE / "data")
