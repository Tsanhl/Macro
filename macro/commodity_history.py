"""Dated Brent front-month vendor closes for the local overview."""
import math
import pandas as pd


def brent_history(series, asof):
    """Exclude unfinished/future bars; retain internal missing quotes as chart gaps."""
    data = series.copy()
    data.index = pd.to_datetime(data.index).tz_localize(None).normalize()
    data = data.sort_index().loc[:asof]
    if data.index.has_duplicates:
        raise ValueError('Duplicate Brent observation dates')
    valid = data.dropna()
    if len(valid) < 2:
        raise ValueError('Insufficient completed Brent observations')
    if any(not math.isfinite(float(v)) or v <= 0 for v in valid):
        raise ValueError('Invalid Brent price')
    data = data.loc[max(valid.index[0], valid.index[-1] - pd.DateOffset(years=1)):valid.index[-1]]
    return [{'date': d.strftime('%Y-%m-%d'), 'close': None if pd.isna(v) else round(float(v), 4),
             'ticker': 'BZ=F', 'unit': 'USD/bbl', 'basis': 'vendor_daily_close_front_month',
             'source': 'https://finance.yahoo.com/quote/BZ=F/history/'} for d, v in data.items()]


def validate_brent(rows, asof):
    if not isinstance(rows, list) or len(rows) < 2:
        raise ValueError('Missing Brent history')
    dates = [pd.Timestamp(r['date']).strftime('%Y-%m-%d') for r in rows]
    if dates != sorted(set(dates)) or dates[-1] > asof:
        raise ValueError('Duplicate, unordered or future Brent dates')
    if any(r.get('ticker') != 'BZ=F' or r.get('unit') != 'USD/bbl' or
           r.get('basis') != 'vendor_daily_close_front_month' for r in rows):
        raise ValueError('Mixed Brent instrument/basis')
    values = [r['close'] for r in rows if r.get('close') is not None]
    if len(values) < 2 or any(not isinstance(v, (int,float)) or not math.isfinite(v) or v <= 0 for v in values):
        raise ValueError('Invalid Brent history values')
    return rows
