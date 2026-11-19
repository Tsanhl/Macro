"""Funding market card: SOFR−IORB runs, own-series change windows, matching CCC/BB dates."""
import unittest
from datetime import date, timedelta
from funding_market import compute, runs


def days(n, start=date(2026, 9, 1)):
    return [(start + timedelta(days=i)).isoformat() for i in range(n)]


def raw(sofr_bp, n=30):
    d = days(n)
    flat = lambda v: {x: v for x in d}
    series = {"sofr": {x: 3.90 + bp / 100 for x, bp in zip(d, sofr_bp)}, "iorb": flat(3.90),
              "srf": {x: (31.5 if i == 3 else 0.0) for i, x in enumerate(d)}, "dw": {d[-8]: 9169.0, d[-1]: 9538.0}}
    for k, base in (("ccc", 11.0), ("b", 3.0), ("bb", 1.9), ("bbb", 1.0), ("ig", 0.8)):
        series[k] = {x: base + i / 100 for i, x in enumerate(d)}
    return series, d


class FundingTests(unittest.TestCase):
    def test_runs_split_on_any_session_below_the_bar(self):
        rows = [{"date": f"d{i}", "bp": bp} for i, bp in enumerate([0, 3, 5, 2, 4, 4, 3])]
        self.assertEqual(runs(rows), [{"start": "d1", "end": "d2", "days": 2, "max_bp": 5},
                                      {"start": "d4", "end": "d6", "days": 3, "max_bp": 4}])

    def test_current_run_counts_only_when_it_reaches_the_latest_print(self):
        series, _ = raw([-2] * 25 + [0, 2, 3, 5, 4])
        self.assertEqual(compute(series)["run_now"], 3)
        series, _ = raw([-2] * 25 + [3, 5, 4, 2, -1])
        self.assertEqual(compute(series)["run_now"], 0)

    def test_spread_change_uses_each_series_own_observation_twenty_back(self):
        series, d = raw([0] * 30)
        b = next(r for r in compute(series)["ladder"] if r["id"] == "b")
        self.assertEqual((b["date"], b["prev_date"], b["chg_bp"]), (d[-1], d[-21], 20))
        self.assertEqual(b["pct3y"], 100)

    def test_ccc_bb_gap_uses_the_latest_date_both_series_have(self):
        series, d = raw([0] * 30)
        del series["bb"][d[-1]]
        gap = compute(series)["ccc_bb"]
        self.assertEqual(gap["date"], d[-2])
        self.assertEqual(gap["pp"], 9.1)

    def test_facilities_keep_their_own_dates_and_units(self):
        series, d = raw([0] * 30)
        doc = compute(series)
        self.assertEqual((doc["dw"]["date"], doc["dw"]["bn"], doc["dw"]["prev_bn"]), (d[-1], 9.54, 9.17))
        self.assertEqual((doc["srf"]["peak_date"], doc["srf"]["peak_bn"]), (d[3], 31.5))


if __name__ == '__main__': unittest.main()
