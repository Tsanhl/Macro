"""The local board's 美債 section (server/macro_summary.py): curve-shape names by definition, and which auctions are listed."""
import importlib.util
import unittest
from pathlib import Path

from auctions import parse, with_history
from test_auctions import rec

if not (Path(__file__).resolve().parents[2] / "server" / "macro_summary.py").exists():
    raise unittest.SkipTest("server/ not found next to macro/")
# loaded by path, so server/serve.py does not shadow macro/serve.py for the other tests
_spec = importlib.util.spec_from_file_location("macro_summary", Path(__file__).resolve().parents[2] / "server" / "macro_summary.py")
ms = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ms)
curve_sentence, curve_shape, latest_auctions = ms.curve_sentence, ms.curve_shape, ms.latest_auctions


class CurveShapeTests(unittest.TestCase):
    def test_four_names_follow_direction_and_which_end_moved_more(self):
        self.assertEqual(curve_shape(10, 20), "熊市變陡")
        self.assertEqual(curve_shape(-20, -10), "牛市變陡")
        self.assertEqual(curve_shape(37, 29), "熊市變平")
        self.assertEqual(curve_shape(-5, -12), "牛市變平")

    def test_no_size_cut_off(self):
        self.assertEqual(curve_shape(1, 2), "熊市變陡")

    def test_opposite_directions_and_ties(self):
        self.assertEqual(curve_shape(6, -4), "兩端方向相反，息差收窄")
        self.assertEqual(curve_shape(-3, 5), "兩端方向相反，息差擴闊")
        self.assertEqual(curve_shape(0, 5), "只有一端變動，息差擴闊")
        self.assertEqual(curve_shape(8, 8), "兩端同幅上升，息差不變")
        self.assertEqual(curve_shape(0, 0), "兩端持平")

    def test_sentence_states_moves_end_and_spread(self):
        s = curve_sentence("一週內，", 37, 29)
        self.assertIn("2 年期上升 37 基點、10 年期上升 29 基點", s)
        self.assertIn("短端變動較大，按定義屬熊市變平（息差收窄 8 基點）", s)
        self.assertIn("兩端方向相反，息差收窄 10 基點", curve_sentence("一個月內，", 6, -4))


class AuctionListTests(unittest.TestCase):
    def test_latest_of_each_core_term_and_other_terms_only_within_a_month(self):
        rows = with_history([parse(x) for x in (
            rec(term='10-Year', date='2026-10-07'), rec(term='10-Year', date='2026-11-10', hy='5.020'),
            rec(term='2-Year', date='2026-09-20'),  # older than a month, still listed (core term)
            rec(term='7-Year', date='2026-09-24'),  # older than a month, left out
            rec(term='3-Year', date='2026-11-09'), rec(term='30-Year', date='2026-11-12'))])
        out = latest_auctions(rows, '2026-11-13')
        self.assertEqual([(x['term'], x['date']) for x in out],
                         [('2Y', '2026-09-20'), ('3Y', '2026-11-09'), ('10Y', '2026-11-10'), ('30Y', '2026-11-12')])
        self.assertEqual(out[2]['chg_bp'], -28.0)


if __name__ == '__main__': unittest.main()
