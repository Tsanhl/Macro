"""server/guide.py, the 讀法 page: fixed explanations of every indicator and three checklists whose 現時 column is read
from board data and put in a column by definition only. Synthetic readings; no network."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "macro"))   # macro/ first, as in test_val_page: both folders have a serve.py
import guide  # noqa: E402


def readings(**over):
    sectors = {f"X{i}": {"ticker": f"X{i}", "group": "sector", "r1w": -3.0} for i in range(11)}
    sectors.update({"GDX": {"ticker": "GDX", "group": "sector", "r1w": -16.0}, "RSP": {"ticker": "RSP", "r1w": -6.2},
                    "IWM": {"ticker": "IWM", "r1w": -7.5}})
    D = dict(session="2026-11-20", S=sectors,
             r={"real10_1w": -14, "hy_oas_1w": 32, "ig_oas_1w": 5, "bb_oas_1w": 27, "ccc_oas_1w": 47, "hy_oas_date": "2026-11-19"},
             b={"ad_1w": -1249, "pct50": 43.0, "pct50_1w": 71.8, "pct20": 19.4, "pct20_1w": 67.0, "mcclellan": -95.1},
             R={"HYG_IEF": {"vs_50d": -2.5}}, H={"window": 63},
             week={"GLD": -9.2, "UUP": 0.4}, corr={"GLD": {"corr": 0.41, "corr_med5y": 0.16}},
             down={"GLD": {"avg_pct": -1.19, "up_share": 32}},
             V={"^GVZ": {"chg_1w_pct": 37.3, "pct1y": 89}, "^VIX9D": {"v": 40.7}, "^VIX": {"v": 35.9}, "^VIX3M": {"v": 30.9}},
             P={"BIZD": {"chg_5": -4.6}})
    D.update(over)
    return D


class GuideTests(unittest.TestCase):
    def test_metals_sold_with_stocks(self):
        rows, (a, b) = guide.metals_rows(readings())
        lean = {r[0]: r[4] for r in rows}
        self.assertEqual(lean["實質孳息"], b)          # real yields fell and gold fell anyway
        self.assertIsNone(lean["美元"])                 # size matters there, so no column by sign
        self.assertEqual(lean["與納指的相關"], b)
        self.assertEqual(lean["SMH 大跌的日子"], b)
        self.assertEqual(lean["金礦股 GDX"], b)

    def test_metals_on_fundamentals(self):
        D = readings(r={"real10_1w": 20}, corr={"GLD": {"corr": 0.05, "corr_med5y": 0.16}}, down={"GLD": {"avg_pct": 0.4, "up_share": 64}})
        lean = {r[0]: r[4] for r in guide.metals_rows(D)[0]}
        self.assertEqual(lean["實質孳息"], "基本因素")
        self.assertEqual(lean["與納指的相關"], "基本因素")
        self.assertEqual(lean["SMH 大跌的日子"], "基本因素")

    def test_broad_decline_and_unconfirmed_bounce(self):
        b_rows, (_, broad) = guide.breadth_rows(readings())
        self.assertTrue(all(r[4] in (broad, None) for r in b_rows))
        self.assertEqual(sum(r[4] == broad for r in b_rows[:-1]), 7)   # the market-state row reads the real build
        c_rows, (_, no) = guide.bounce_rows(readings())
        self.assertTrue(all(r[4] == no for r in c_rows))

    def test_confirmed_bounce(self):
        D = readings(S={"RSP": {"r1w": 2.0}, "IWM": {"r1w": 3.0}}, b={"ad_1w": 900, "pct20": 55, "pct20_1w": 30, "mcclellan": 25.0},
                     r={"hy_oas_1w": -15, "ccc_oas_1w": -30}, R={"HYG_IEF": {"vs_50d": 0.4}}, P={"BIZD": {"chg_5": 1.2}},
                     V={"^VIX9D": {"v": 17}, "^VIX": {"v": 18}, "^VIX3M": {"v": 20}})
        rows, (yes, _) = guide.bounce_rows(D)
        self.assertTrue(all(r[4] == yes for r in rows))

    def test_page_has_every_section_and_no_script(self):
        html = guide.guide_page()
        for h in ("一、每個指標的意思", "二、三張核對表", "三、唯一經測試的數字", "傳導鏈", "股債波動", "板塊輪動及市場狀態"):
            self.assertIn(h, html)
        self.assertNotIn("<script", html)
        self.assertNotIn("買入", html)


if __name__ == "__main__":
    unittest.main()
