"""Brent history keeps completed source dates and missing-data gaps."""
import unittest
import pandas as pd
from commodity_history import brent_history, validate_brent


class CommodityHistoryTests(unittest.TestCase):
    def test_future_bar_excluded_and_missing_quote_is_not_filled(self):
        data = pd.Series([100, float('nan'), 110, 999], index=pd.to_datetime(['2026-10-13','2026-10-14','2026-10-16','2026-10-19']))
        rows = brent_history(data, '2026-10-16')
        self.assertEqual([r['date'] for r in rows], ['2026-10-13','2026-10-14','2026-10-16'])
        self.assertIsNone(rows[1]['close'])
        self.assertEqual(rows[-1]['close'], 110)
        validate_brent(rows, '2026-10-16')

    def test_duplicates_and_invalid_prices_fail_closed(self):
        for values, dates in [([100,110], ['2026-10-16','2026-10-16']),
                              ([100,-1], ['2026-10-15','2026-10-16'])]:
            with self.assertRaises(ValueError):
                brent_history(pd.Series(values,index=pd.to_datetime(dates)), '2026-10-16')

    def test_future_or_mixed_instrument_file_is_rejected(self):
        rows = brent_history(pd.Series([100,110],index=pd.to_datetime(['2026-10-15','2026-10-16'])), '2026-10-16')
        with self.assertRaises(ValueError): validate_brent(rows, '2026-10-15')
        rows[-1]['ticker'] = 'CL=F'
        with self.assertRaises(ValueError): validate_brent(rows, '2026-10-16')

if __name__ == '__main__': unittest.main()
