# dashboard--macro-

宏觀數據來源 · Macro data source for the local board

This folder downloads and computes the macro data behind the owner's local board at http://localhost:8770
(`server/serve.py`, outside this folder), which has four pages: 機構持倉, 宏觀 (with 油價), 新聞與連接 and AI 追蹤.
It builds one local page, `site_private/`, served on port 8766 by `serve.py`; the board's 宏觀 view
(`server/macro_view.py`) regroups that page as it is served, and the 新聞與連接 and AI 追蹤 pages read its data.
8766 is an internal source and is not opened directly. A static copy is published by `../export_site.py` (see `../README.md`).

The macro pages show data and short summaries only: no trading, rotation or position rules. Prices and relative
performance are not observed fund flows; CTA and volatility control are estimates, not a census of institutional
positions. The board has no alerts, alert lamps or notifications, and it sends nothing to any webhook or chat service.

## Run locally

Python 3.12 or later on macOS/Linux:

```bash
pip install -r requirements.txt
python3 refresh.py                  # download, validate and build site_private/
python3 refresh.py --render-only    # rebuild the page from the saved data and hand-kept files; no downloads
python3 ../server/serve.py       # http://localhost:8770; starts serve.py (8766) when it is not running
```

The **更新數據 / Update data** button in the 宏觀 view (and 更新全部數據 on the board) posts to `serve.py`'s
`/api/update`, which runs the same `refresh.run()`. The endpoint accepts same-origin requests on loopback only.

The updater uses a process lock (`.refresh/lock`, which `server/serve.py`'s news thread also checks), a staged
build, source-date validation and rollback backups. Concurrent clicks share one update; an independently running
command holds the same lock. A failed batch keeps the previous served board. Logs and prior snapshots stay in the
parent `logs/<session>/` folder; after a successful run only the latest run folder of that session is kept,
and its `previous/` holds the replaced data and page for recovery.

Hand-kept inputs (`../evidence/`: AI tracker, news issues, oil and war notes, borrower evidence) and the AI-cycle
tracker (`../ai_cycle_watch/`) live outside this folder; a run copies them into its staging folder.

## Datasets

`build_site.DATASETS` lists the datasets the page, `server/` and `daily_summary.py` read; `refresh.validate`
requires each of them, plus `positioning` (read by `oil_tracking.py` for CFTC WTI), `positioning_now` (its CFTC dates
are checked) and `stocks` (read by `server/pages.py` for the price-reaction column), which stay in `data/` and are not loaded by the
page. `refresh_meta` adds the observation dates shown under 資料更新狀態.

| Module | Content | Source |
|---|---|---|
| `build_data.py` | Sectors, themes, styles and AI baskets with weekly and daily rotation; breadth (% above 50-day, A/D line); ratio lines; rates, credit and net liquidity; CFTC positions; Brent closes; split checks | Yahoo, S&P member list, CFTC, FRED, US Treasury |
| `flows.py` | CTA, volatility-control and VIX term-structure model estimates (`flowmodel`, `flowmodel_now`) | Yahoo, FRED, Treasury |
| `summary_checks.py` | `check_prices`: SMH and the neocloud basket against SPY, for `daily_summary.py` | Yahoo (same snapshot) |
| `macro_watch.py` | Treasury cash balance (TGA), MOVE index | US Treasury fiscaldata (Daily Treasury Statement); Yahoo ^MOVE |
| `auctions.py` | Treasury coupon auction results: clearing yield, bid-to-cover, bidder shares | TreasuryDirect |
| `funding_market.py` | SOFR − IORB, Standing Repo Facility, discount window, ICE BofA spreads by rating with three-year percentiles | FRED |
| `oil_tracking.py` | Brent/WTI futures curve and spreads, Dated Brent, EIA stocks, managed-money positions in five contracts, OVX | Yahoo, EIA, CFTC, ICE, FRED |
| `us_economy.py` | 47 US economy series for the 美國經濟 sub-page: latest, previous, a year earlier, ten-year percentile and ten years of history; failed series keep their previous values, marked stale. Run by `refresh.py` (never fails the refresh) or on its own | FRED public CSV |
| `news_feed.py` | Headlines for 新聞與連接, grouped by topic, newest ten per topic, de-duplicated over seven days | Official feeds (Fed, Treasury, EIA and others) and an allow-list of named news organisations via Google News RSS |

The news feed keeps only official sources (labelled 官方公告) and named, established publishers (labelled 報道).
Social media, post aggregators and sites not on the allow-list are dropped, including headlines already stored.

## What the button updates

| Cadence | Content | Rule |
|---|---|---|
| Each completed US session | Prices, sector/AI returns, breadth, A/D, relative strength, daily rotation, CTA/volatility models | Calendar-aware close plus a settling buffer; never label an unfinished bar as the close |
| Check daily for releases | Nominal/real Treasury yields, breakevens, curve, HY/IG/CCC/BB spreads | Keep each source's observation date; a carried value is not a new observation |
| Check daily for reference quotes | Specified CoreWeave/Oracle BondTerminal bonds | Same ISIN, dated price/YTW and convention; gaps/conflicts remain unconfirmed. These are not CDS or OAS |
| New weekly report | CFTC positions | Usually Friday release of Tuesday positions; unchanged between reports |
| Completed trading week | Confirmed weekly rotation | Preserve the prior confirmation during the week; daily previews stay separate |
| New weekly release | Fed balance sheet / aligned net liquidity | Match the existing weekly observation basis |

The button does not write AI analysis or the event calendar. `commodity_history.py` validates dated BZ=F closes for
`brent.json`.

## The page

`index.html` has three tabs on 8766: 板塊輪動 (relative rotation graph), 市寬 (share of S&P 500 members above the
50-day average, A/D line with SPY) and 油價 (oil cards). The 宏觀 view adds its own cards from
`server/macro_summary.py` and patches this page by exact text (`macro_view.PATCHES`); when a change here breaks a
patch, the view shows the original page with a red notice, and `tests/test_war_card.py` fails.

## Code map

| File | Responsibility |
|---|---|
| `refresh.py`, `market_clock.py` | Shared transaction, backups, validation and exchange calendar |
| `serve.py`, `refresh.js` | Local update API and the 更新數據 button with its source dates |
| `build_data.py`, `flows.py`, `summary_checks.py` | Fetch and calculate the datasets; invoked by the updater |
| `macro_watch.py`, `auctions.py`, `funding_market.py`, `oil_tracking.py`, `news_feed.py`, `us_economy.py` | Further datasets (see above) |
| `bond_reference.py` | Fail-closed parsing of dated specified-bond price/YTW references |
| `daily_summary.py`, `daily_facts.py` | Reviewable facts from the same snapshot for the evening summary, not an independent market download |
| `build_site.py`, `index.html` | The local build (`site_private/`) and its interactive charts |
| `tests/` | Date/comparison, rollback, concurrency, endpoint and board checks |

Sources: Yahoo Finance (`yfinance`, adjusted prices), CFTC, ICE, EIA, US Treasury (fiscaldata, TreasuryDirect),
FRED, public S&P constituent lists, delayed BondTerminal reference quotations, and official feeds and allow-listed
news organisations for headlines.

Run checks with `python3 -m unittest discover -s tests` (tests that need the local `server/` folder skip when it is
absent). Not investment advice.
