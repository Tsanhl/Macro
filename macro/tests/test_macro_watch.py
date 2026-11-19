"""TGA and MOVE parsers for the local 宏觀 view (macro_watch.py); no network required."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import macro_watch
from macro_watch import TGA_ROW, move_block, tga_block, tga_rows


def dts(date, v, account=TGA_ROW):
    return {"record_date": date, "account_type": account, "close_today_bal": "null", "open_today_bal": str(v)}


class MacroWatch(unittest.TestCase):
    def test_tga_rows_take_the_closing_row_only(self):
        payload = {"data": [dts("2026-11-12", 933127), dts("2026-11-12", 912134, "Treasury General Account (TGA) Opening Balance"),
                            dts("2026-11-10", 922633), dts("2026-11-11", "null"), {"record_date": "2026-11-09", "account_type": TGA_ROW,
                            "close_today_bal": "900000", "open_today_bal": "null"}]}
        self.assertEqual(tga_rows(payload), [{"date": "2026-11-09", "bn": 900.0}, {"date": "2026-11-10", "bn": 922.6},
                                             {"date": "2026-11-12", "bn": 933.1}])

    def test_tga_changes_use_the_last_reading_on_or_before_each_window(self):
        rows = [{"date": d, "bn": v} for d, v in [("2026-10-10", 800.0), ("2026-10-13", 820.0), ("2026-11-05", 922.8),
                                                   ("2026-11-06", 925.0), ("2026-11-12", 933.1)]]
        b = tga_block(rows)
        self.assertEqual(b["latest"], {"date": "2026-11-12", "bn": 933.1})
        self.assertEqual(b["chg_1w"], {"bn": 10.3, "base_date": "2026-11-05"})
        self.assertEqual(b["chg_1m"], {"bn": 113.1, "base_date": "2026-10-13"})
        self.assertIsNone(tga_block([]))

    def test_move_percentile_week_change_and_gaps(self):
        pts = [("2025-11-10", 70.0), ("2026-06-01", 80.0), ("2026-11-06", 92.77), ("2026-11-12", float("nan")), ("2026-11-13", 98.79)]
        m = move_block(pts)
        self.assertEqual(m["latest"], {"date": "2026-11-13", "v": 98.79})
        self.assertEqual(m["chg_1w"], {"v": 6.02, "base_date": "2026-11-06"})
        self.assertEqual((m["n1y"], m["pct1y"], m["first1y"]), (3, 100, "2026-06-01"))  # the 2025-11-10 close is over a year old
        self.assertIsNone(move_block([]))

    def test_failed_fetch_keeps_previous_block_and_says_so(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            old = {"tga": {"latest": {"date": "2026-11-05", "bn": 922.8}}, "move": None}
            (out / "macro_watch.json").write_text(json.dumps([old]))
            with patch.object(macro_watch, "fetch_tga", side_effect=OSError("down")):
                row = macro_watch.build_macro_watch(out, [("2026-11-13", 98.79)])
            self.assertEqual(row["tga"], old["tga"])
            self.assertEqual(row["move"]["latest"]["v"], 98.79)
            self.assertEqual(row["errors"], ["TGA: OSError"])
            self.assertEqual(json.loads((out / "macro_watch.json").read_text())[0]["tga"], old["tga"])


if __name__ == "__main__":
    unittest.main()
