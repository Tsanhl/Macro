"""The 油價 page: managed money summed over five oil contracts (oil_tracking.py), and the curve and spread sentences of
server/macro_summary.py, which say what a reading means by definition and use no size cut-off. No network required."""
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

import oil_tracking
from oil_tracking import GASOIL_BBL_PER_TONNE, aggregate_positions, build_positions, ice_rows, positions_summary

if not (Path(__file__).resolve().parents[2] / "server" / "macro_summary.py").exists():
    raise unittest.SkipTest("server/ not found next to macro/")
# loaded by path, so server/serve.py does not shadow macro/serve.py for the other tests
_spec = importlib.util.spec_from_file_location("macro_summary", Path(__file__).resolve().parents[2] / "server" / "macro_summary.py")
ms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ms)


class PositionsTests(unittest.TestCase):
    def test_sum_in_million_barrels_with_contract_sizes(self):
        series = {"brent": {"2026-10-27": (300000, 100000)}, "rbob": {"2026-10-27": (90000, 10000)},
                  "gasoil": {"2026-10-27": (80000, 20000)}}
        row = aggregate_positions(series)[0]
        gasoil = 100 * GASOIL_BBL_PER_TONNE  # 100 tonnes a lot
        self.assertEqual(gasoil, 745)
        self.assertEqual(row["long"], round((300000 * 1000 + 90000 * 1000 + 80000 * gasoil) / 1e6, 1))
        self.assertEqual(row["short"], round((100000 * 1000 + 10000 * 1000 + 20000 * gasoil) / 1e6, 1))
        self.assertEqual(row["net"], round(row["long"] - row["short"], 1))

    def test_only_weeks_every_contract_reports(self):
        series = {"brent": {"2026-10-20": (1000, 0), "2026-10-27": (2000, 0)}, "ulsd": {"2026-10-27": (500, 0), "2026-11-03": (600, 0)}}
        self.assertEqual([r["date"] for r in aggregate_positions(series)], ["2026-10-27"])

    def test_summary_change_and_percentile_at_or_below(self):
        rows = [{"date": f"2026-10-{d:02d}", "long": 0, "short": 0, "net": n} for d, n in ((6, 5.0), (13, 9.0), (20, 1.0), (27, 7.0))]
        s = positions_summary(rows)
        self.assertEqual((s["net"], s["chg_1w"], s["chg_1w_base"], s["pct"], s["n"]), (7.0, 6.0, "2026-10-20", 75, 4))

    def test_ice_file_keeps_futures_only_rows(self):
        text = ("Market_and_Exchange_Names,As_of_Date_Form_MM/DD/YYYY,M_Money_Positions_Long_All,M_Money_Positions_Short_All,FutOnly_or_Combined\n"
                "ICE Brent Crude Futures - ICE Futures Europe,9/15/2026,100,40,FutOnly\n"
                "ICE Brent Crude Futures - ICE Futures Europe,9/15/2026,999,999,Combined\n"
                "ICE Gasoil Futures - ICE Futures Europe,11/03/2026,79,23,FutOnly\n")
        got = ice_rows(text, ["ICE Brent Crude Futures - ICE Futures Europe", "ICE Gasoil Futures - ICE Futures Europe"])
        self.assertEqual(got["ICE Brent Crude Futures - ICE Futures Europe"], {"2026-09-15": (100, 40)})
        self.assertEqual(got["ICE Gasoil Futures - ICE Futures Europe"], {"2026-11-03": (79, 23)})

    def test_failed_source_keeps_stored_series_and_names_the_missing(self):
        prev = {"series": {"brent": [["2026-10-27", 200, 50], ["2026-11-03", 210, 60]]}}
        cftc = {"2026-10-27": (10, 5), "2026-11-03": (12, 5)}
        with patch.object(oil_tracking, "get", side_effect=OSError("down")), patch.object(oil_tracking, "cftc_rows", return_value=cftc):
            b = build_positions("2026-11-13", prev)
        self.assertIn("歐洲柴油 ICE Gasoil", b["missing"])
        self.assertNotIn("ICE Brent", b["missing"])
        self.assertEqual(b["summary"]["date"], "2026-11-03")
        self.assertEqual(b["rows"][-1]["long"], round((210 + 4 * 12) * 1000 / 1e6, 1))
        self.assertTrue(any(e.startswith("ICE") for e in b["errors"]))


class SpreadSentenceTests(unittest.TestCase):
    def test_backwardation_and_the_premium_widening(self):
        s = ms.spread_meaning("m1_m2", 2.81, 2.67)
        self.assertIn("近月比次月貴，即逆價差：買家為即時供應付溢價", s)
        self.assertIn("溢價擴闊", s)
        self.assertIn("市場為近期供應緊張定價更多", s)

    def test_premium_narrowing_and_no_size_cut_off(self):
        s = ms.spread_meaning("m1_dec_next", 15.86, 15.87)
        self.assertIn("溢價收窄", s)
        self.assertIn("為近期緊張所付的溢價減少", s)

    def test_contango_and_a_change_of_sign(self):
        self.assertIn("即正價差", ms.spread_meaning("m1_m6", -1.0, -0.5))
        self.assertIn("正價差擴闊", ms.spread_meaning("m1_m6", -1.0, -0.5))
        self.assertIn("由正價差轉為逆價差", ms.spread_meaning("m1_m2", 0.4, -0.2))
        self.assertIn("由逆價差轉為正價差", ms.spread_meaning("m1_m2", -0.4, 0.2))
        self.assertIn("一週不變", ms.spread_meaning("m1_m2", 1.0, 1.0))

    def test_brent_over_wti(self):
        self.assertIn("海運原油的定價比美國內陸原油更緊", ms.spread_meaning("brent_wti", 7.5, 7.28))
        self.assertIn("海運原油的定價相對美國內陸原油轉鬆", ms.spread_meaning("brent_wti", 7.28, 7.49))

    def test_spread_line_states_value_week_change_and_pair(self):
        line = ms.spread_line({"key": "m1_m2", "a": "2027-01", "b": "2027-02", "now": 2.81, "date": "2026-11-13", "week": 2.67,
                               "week_date": "2026-11-06"})
        self.assertIn("近月對次月（2027-01 減 2027-02）：+2.81 美元（11月13日）；一週 +0.14 美元（11月6日為 +2.67）", line)

    def test_whole_curve_sentence(self):
        rows = lambda *c: [{"month": f"2027-{i + 1:02d}", "chg_1w": v, "week_date": "2026-11-06"} for i, v in enumerate(c)]
        self.assertIn("整條曲線上升", ms.curve_move_sentence(rows(1.0, 0.5, 0.2)))
        self.assertIn("較持久的供應減少定價", ms.curve_move_sentence(rows(1.0, 0.5, 0.2)))
        self.assertIn("整條曲線下跌", ms.curve_move_sentence(rows(-1.0, -0.5, -0.2)))
        self.assertIn("定價的是近期緊張", ms.curve_move_sentence(rows(1.0, 0.1, -0.2)))
        self.assertIn("近期緊張的溢價減少", ms.curve_move_sentence(rows(-2.5, -0.6, 0.05)))

    def test_brent_week_change_uses_one_contract_through_a_roll(self):
        # the week Yahoo's continuous BZ=F moved from January to February: 95.84 (Jan, 13 Nov) -> 89.95 (Feb, 20 Nov)
        rows = [{"month": "2027-01", "close": 92.57, "date": "2026-11-20", "week_date": "2026-11-13", "chg_1w": -3.27},
                {"month": "2027-02", "close": 89.95, "date": "2026-11-20", "week_date": "2026-11-13", "chg_1w": -3.08}]
        bz = [{"date": "2026-11-13", "close": 95.84}, {"date": "2026-11-20", "close": 89.95}]
        line = ms.brent_price_line(rows, bz)
        self.assertIn("Brent 近月（2027-01 合約）92.57 美元（11月20日），對 11月13日同一合約下降 3.27 美元", line)
        self.assertIn("已轉到 2027-02 合約", line)
        self.assertNotIn("5.89", line)  # the cross-contract change is never stated

    def test_brent_line_without_a_roll_and_without_a_curve(self):
        rows = [{"month": "2027-01", "close": 95.84, "date": "2026-11-13", "week_date": "2026-11-06", "chg_1w": 1.2},
                {"month": "2027-02", "close": 93.10, "date": "2026-11-13", "week_date": "2026-11-06", "chg_1w": 1.0}]
        line = ms.brent_price_line(rows, [{"date": "2026-11-13", "close": 95.84}])
        self.assertIn("對 11月6日同一合約上升 1.20 美元", line)
        self.assertNotIn("BZ=F", line)
        bz = [{"date": "2026-11-06", "close": 94.0}, {"date": "2026-11-13", "close": 95.84}]
        self.assertIn("連續近月（Yahoo BZ=F）95.84 美元", ms.brent_price_line([], bz))
        self.assertIn("轉倉週的變化會包括換合約", ms.brent_price_line([], bz))
        self.assertIsNone(ms.brent_price_line([], []))

    def test_put_and_call_say_which_side_was_larger_not_who_is_right(self):
        base = {"group": "options", "date": "2026-10-20", "unit": "張", "provider": "X"}
        both = [dict(base, key="brent_put_volume", item="Brent 認沽期權單日成交", value=787000),
                dict(base, key="brent_call_volume", item="Brent 認購期權單日成交", value=500000)]
        s = ms.options_sides(both)
        self.assertIn("認沽（put）較多", s)
        self.assertIn("不顯示哪一方對", s)
        self.assertIn("不能說哪一方較大", ms.options_sides(both[:1]))
        self.assertIsNone(ms.options_sides([]))


if __name__ == "__main__":
    unittest.main()
