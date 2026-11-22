"""macro/cross_asset.py (havens against the AI trade, equity and bond volatility, private-credit proxies) and the 宏觀
view's sentences built from it in server/macro_summary.py. Synthetic prices only; no network."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

import cross_asset as ca

_spec = importlib.util.spec_from_file_location("macro_summary", Path(__file__).resolve().parents[2] / "server" / "macro_summary.py")
ms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ms)


def prices(n=1400, seed=1):
    """Daily closes for every ticker the step reads: GLD moves with QQQ, TLT against it, the rest independent."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2021-01-04", periods=n)
    q = rng.normal(0, 0.01, n)
    ret = {t: rng.normal(0, 0.005, n) for t in ca.TICKERS}
    ret["QQQ"], ret["SMH"], ret["SPY"] = q, 1.5 * q + rng.normal(0, 0.005, n), 0.8 * q
    ret["GLD"], ret["TLT"] = 0.8 * q + rng.normal(0, 0.003, n), -0.8 * q + rng.normal(0, 0.003, n)
    close = pd.DataFrame({t: 100 * np.cumprod(1 + r) for t, r in ret.items()}, index=idx)
    for t, _ in ca.VOL:  # volatility indices: a level that ends at its high
        close[t] = np.linspace(10, 40, n)
    return close


class HavenTests(unittest.TestCase):
    def test_correlation_signs_and_median(self):
        H = ca.haven_block(prices())
        rows = {r["t"]: r for r in H["rows"]}
        self.assertGreater(rows["GLD"]["corr"], 0.5)
        self.assertLess(rows["TLT"]["corr"], -0.5)
        self.assertEqual(H["window"], 63)
        self.assertIsNotNone(rows["GLD"]["corr_med5y"])
        self.assertTrue(H["week"]["base_date"] < H["date"])
        roll = H["roll"]  # the card's charts: one year of the rolling readings, the last one equal to the table's
        self.assertEqual(len(roll["dates"]), ca.CHART_SESSIONS)
        self.assertEqual(roll["dates"][-1], H["date"])
        self.assertAlmostEqual(roll["GLD"][-1], rows["GLD"]["corr"], places=2)

    def test_worst_tenth_of_smh_days(self):
        close = prices()
        D = ca.haven_block(close)["down"]
        ret = close["SMH"].pct_change().dropna().iloc[-252:]
        self.assertEqual((D["sessions"], D["n"]), (252, 25))
        self.assertAlmostEqual(D["cut_pct"], round(ret.nsmallest(25).max() * 100, 2))
        self.assertEqual([r["t"] for r in D["rows"]][0], "SPY")
        self.assertTrue(all(0 <= r["up_share"] <= 100 for r in D["rows"]))

    def test_reading_uses_the_sampling_band(self):
        self.assertEqual(ms.corr_band(63), 0.25)   # about two standard errors over 63 sessions
        self.assertEqual([ms.corr_word(v, 0.25) for v in (0.41, -0.30, 0.01, -0.24, None)], ["同向", "反向", "沒有可靠關係", "沒有可靠關係", "—"])
        H = {"date": "2026-11-20", "window": 63,
             "rows": [{"name": "黃金", "corr": 0.41}, {"name": "短債", "corr": -0.30}, {"name": "美元", "corr": 0.01}],
             "down": {"n": 25, "cut_pct": -3.7, "rows": [{"t": "SPY", "name": "SPY", "avg_pct": -1.29, "up_share": 0},
                      {"t": "XLP", "name": "必需消費", "avg_pct": 0.89, "up_share": 84}, {"t": "GLD", "name": "黃金", "avg_pct": -1.19, "up_share": 32},
                      {"t": "IEF", "name": "中債", "avg_pct": 0.0, "up_share": 48}]}}
        (line,) = ms.haven_lines(H)
        self.assertIn("明顯跟科技股同向的有 黃金，明顯反向的有 短債，其餘沒有可靠關係", line)
        self.assertIn("平均上升而且多數日子上升的有 必需消費，平均下跌而且多數日子下跌的有 黃金", line)
        self.assertNotIn("中債", line)   # flat on average: in neither list
        self.assertNotIn("SPY", line)


class VolAndProxyTests(unittest.TestCase):
    def test_vol_change_and_percentile(self):
        V = ca.vol_block(prices())["rows"]
        vix = next(r for r in V if r["t"] == "^VIX")
        self.assertEqual(vix["pct1y"], 100)          # the series ends at its high
        self.assertGreater(vix["chg_1w"], 0)
        self.assertTrue(vix["base_date"] < vix["date"])

    def test_term_structure_by_definition(self):
        row = lambda t, v: {"t": t, "v": v, "date": "2026-11-20"}
        inv = ms.term_structure_line([row("^VIX9D", 40.7), row("^VIX", 35.9), row("^VIX3M", 30.9)])
        self.assertIn("期限結構倒掛", inv)
        self.assertIn("正常的向上斜率", ms.term_structure_line([row("^VIX9D", 14), row("^VIX", 16), row("^VIX3M", 18)]))
        self.assertIsNone(ms.term_structure_line([row("^VIX", 16), dict(row("^VIX9D", 14), date="2026-11-19"), row("^VIX3M", 18)]))

    def test_proxy_distance_from_high(self):
        close = prices()
        P = {r["t"]: r for r in ca.proxy_block(close)["rows"]}
        s = close["BIZD"]
        self.assertAlmostEqual(P["BIZD"]["off_high"], round((s.iloc[-1] / s.iloc[-252:].max() - 1) * 100, 2))
        self.assertAlmostEqual(P["BIZD"]["chg_5"], round((s.iloc[-1] / s.iloc[-6] - 1) * 100, 2))


class BuildTests(unittest.TestCase):
    def test_failed_download_keeps_the_previous_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            first = ca.build_cross_asset(out, "2026-05-12", fetch=lambda t: prices())
            self.assertEqual(first["errors"], [])
            def boom(t):
                raise TimeoutError("no answer")
            second = ca.build_cross_asset(out, "2026-05-13", fetch=boom)
            self.assertEqual(second["havens"], first["havens"])   # same block, same dates
            self.assertEqual(second["errors"], ["download: TimeoutError"])
            self.assertEqual(json.loads((out / "cross_asset.json").read_text())[0]["vol"], first["vol"])

    def test_cutoff_drops_later_sessions(self):
        with tempfile.TemporaryDirectory() as d:
            row = ca.build_cross_asset(Path(d), "2025-06-30", fetch=lambda t: prices())
            self.assertLessEqual(row["havens"]["date"], "2025-06-30")


if __name__ == "__main__":
    unittest.main()


class VerdictTests(unittest.TestCase):
    """The 現在要看 section of the 宏觀 page: conclusions and chain states, signs only, by definition."""

    def sectors(self, r1w, smh=-17.8, rsp=-6.2):
        rows = [{"ticker": f"X{i}", "name": f"板塊{i}", "group": "sector", "r1w": v} for i, v in enumerate(r1w)]
        return rows + [{"ticker": "GDX", "name": "貴金屬", "group": "sector", "r1w": -16.0},   # not one of the 11
                       {"ticker": "SMH", "name": "半導體", "group": "theme", "r1w": smh}, {"ticker": "RSP", "name": "等權", "group": "style", "r1w": rsp}]

    def test_broad_ai_led_and_money_into_treasuries(self):
        v = ms.sell_verdict(self.sectors([-12.5, -8, -6.3, -7, -7.4, -6.9, -7.5, -3.1, -2.1, -6.2, -4.3]),
                            {"TLT": 2.6, "IEF": 1.8, "SPY": -8.6}, "11月13日至11月20日")
        self.assertIn("（11月13日至11月20日）在股票之內，全面下跌（11 個板塊中 11 個一週下跌，等權標普 −6.2%）", v)
        self.assertIn("重心在 AI（SMH −17.8%，跌幅大過所有板塊）", v)
        self.assertIn("不是甚麼都賣，資金轉向國債", v)

    def test_narrow_fall_and_stocks_and_bonds_sold_together(self):
        v = ms.sell_verdict(self.sectors([-3, 1, 2, 1, -1, 2, 1, 1, 2, 1, 1], smh=-1.0), {"TLT": -1.0, "IEF": -0.5, "SPY": -0.4})
        self.assertIn("下跌集中在部分板塊（11 個板塊中 2 個一週下跌", v)
        self.assertIn("跌得最多的是板塊0（−3.0%）", v)
        self.assertIn("股債同時被賣", v)

    def test_credit_verdict(self):
        m = {"hy_oas_1w": 32, "ig_oas_1w": 5, "bb_oas_1w": 27, "ccc_oas_1w": 47, "hy_oas_date": "2026-11-19"}
        v = ms.credit_verdict(m, ["CCC", "CCC−BB"])
        self.assertTrue(v.startswith("信用轉差，四個息差一週全部擴闊（HY +32、IG +5、BB +27、CCC +47 基點，至 11月19日）"))
        self.assertIn("CCC、CCC−BB 在三年最高", v)
        self.assertIn("HY 擴闊多過 IG", v)
        self.assertIn("信用好壞參半，一週擴闊的有 HY、BB、CCC，收窄的有 IG", ms.credit_verdict(dict(m, ig_oas_1w=-1), []))

    def test_chain_states_and_heading(self):
        self.assertEqual([ms.spread_state(x) for x in (5, -2, 0, None)], ["擴闊", "收窄", "持平", "—"])
        self.assertEqual([ms.price_state(x) for x in (-4.6, 0.3, 0, None)], ["下跌", "上升", "持平", "—"])
        nodes = [dict(t="AI 股", v="", s="", st="下跌"), dict(t="投資級", v="", s="", st="擴闊", hot=True),
                 dict(t="資金市場", v="", s="", st="常備回購沒有使用")]
        h = ms.chain_html(nodes)
        self.assertIn("本週轉差的有 AI 股、投資級；未轉差的有 資金市場。", h)
        self.assertIn('class="rb-node hot"', h)
