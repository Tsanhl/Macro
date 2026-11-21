"""One locked, staged data-refresh path for the 8770 board's update buttons and the command line.

Never generates an AI summary. Failed batches never replace the served snapshot.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

from market_clock import completed_session, week_complete

ROOT = Path(__file__).resolve().parent


class Busy(RuntimeError):
    pass


@contextmanager
def refresh_lock(root=ROOT):
    folder = root / '.refresh'; folder.mkdir(exist_ok=True)
    with (folder/'lock').open('a') as handle:
        try: fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: raise Busy('已有更新進行中，請稍候。')
        try: yield
        finally: fcntl.flock(handle, fcntl.LOCK_UN)


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name+'.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    os.replace(temp, path)


# read straight from data/ rather than through the page: positioning (oil_tracking.py's CFTC WTI), positioning_now
# (the CFTC dates checked below) and stocks (server/pages.py's price-reaction column)
DATA_ONLY = ['positioning', 'positioning_now', 'stocks']


def validate(data, session, previous=None):
    from build_site import DATASETS
    rows = {}
    for key in DATASETS + DATA_ONLY:
        rows[key] = read(data/f'{key}.json')
        # data_checks lists suspected unadjusted splits: empty on a normal day
        if not isinstance(rows[key], list) or (not rows[key] and key != 'data_checks'):
            raise ValueError(f'Missing required dataset: {key}')
    for key, field in [('breadth_now','asof'), ('flowmodel_now','date')]:
        if rows[key][0].get(field) != session:
            raise ValueError(f'{key} does not match completed session {session}')
    for key in ['breadth','check_prices','flowmodel','ratios','rrg_daily']:
        if max(r.get('date','') for r in rows[key]) != session:
            raise ValueError(f'{key} latest observation is incomplete')
    from commodity_history import validate_brent
    validate_brent(rows["brent"], session)
    for row in rows['sectors']:
        if row.get('week_done') != week_complete(session):
            raise ValueError('Sector dates / completed-week flag mismatch')
        if not row.get('week_fw') or row['week_fw'] > session or not week_complete(row['week_fw']):
            raise ValueError('Invalid confirmed-week observation')
    for key, fields in [('breadth_now', ('pct50','pct200','mcclellan','adv','dec')),
                        ('flowmodel_now', ('cta','vc','rv1','rv3','vix_ratio'))]:
        if any(not isinstance(rows[key][0].get(f), (int,float)) or not math.isfinite(rows[key][0][f]) for f in fields):
            raise ValueError(f'Incomplete core calculations: {key}')
    for row in rows['positioning_now']:
        if row['date'] > session: raise ValueError('Future CFTC observation')
    old = read(previous/'breadth_now.json', []) if previous else []
    if old and old[0]['asof'] > session: raise ValueError('Refusing to move stock dates backwards')
    rt = rows['rates_now'][0]
    for col in ('nominal2','nominal10','real10','hy_oas','ig_oas','ccc_oas','bb_oas'):
        d = rt.get(col+'_date')
        if not d or rt.get(col) is None or d > datetime.now(timezone.utc).date().isoformat():
            raise ValueError(f'Unconfirmed source date/value: {col}')
    if previous:
        prior = read(previous/'rates_now.json', [{}])[0]
        for key, value in rt.items():
            if key.endswith('_date') and prior.get(key) and value and value < prior[key]:
                raise ValueError(f'Source date regressed: {key}')
        prior_pos = {r['market']: r['date'] for r in read(previous/'positioning_now.json', [])}
        if set(prior_pos) - {r['market'] for r in rows['positioning_now']}:
            raise ValueError('CFTC markets disappeared from the new batch')
        if any(r['date'] < prior_pos.get(r['market'],'') for r in rows['positioning_now']):
            raise ValueError('CFTC report regressed')
    return rows


def promote(pairs, backup):
    """Same-volume renames; restore every previous destination if a later rename fails."""
    backup.mkdir(parents=True, exist_ok=True)
    moved = []
    try:
        for n, (source, dest) in enumerate(pairs):
            dest.parent.mkdir(parents=True, exist_ok=True)
            old = backup/f'{n}-{dest.name}'
            had_old = dest.exists()
            if had_old: os.replace(dest, old)
            moved.append((source, dest, old, had_old))
            os.replace(source, dest)
    except Exception:
        for source, dest, old, had_old in reversed(moved):
            if dest.exists(): os.replace(dest, source)
            if had_old: os.replace(old, dest)
        raise


def metadata(rows, previous, bonds, session):
    rt = rows['rates_now'][0]
    prior_rt = read(previous/'rates_now.json', [{}])[0]
    old_pos = read(previous/'positioning_now.json', [])
    groups = []
    def add(name, cadence, dates, old_dates):
        dates = sorted(set(d for d in dates if d))
        groups.append(dict(name=name, cadence=cadence, dates=dates,
                           state='new_observation' if dates != sorted(set(d for d in old_dates if d)) else 'same_observation_dates'))
    old_br = read(previous/'breadth_now.json', [{}])[0]
    add('股價／市寬／每日輪動／模型', 'daily', [session], [old_br.get('asof')])
    add('利率', 'daily_release', [rt.get(k+'_date') for k in ('nominal2','nominal10','real10')],
        [prior_rt.get(k+'_date') for k in ('nominal2','nominal10','real10')])
    add('Brent原油', 'daily', [r['date'] for r in rows.get('brent', []) if r.get('close') is not None][-1:],
        [r['date'] for r in read(previous/'brent.json', []) if r.get('close') is not None][-1:])
    add('信用', 'daily_release', [rt.get(k+'_date') for k in ('hy_oas','ig_oas','ccc_oas','bb_oas')],
        [prior_rt.get(k+'_date') for k in ('hy_oas','ig_oas','ccc_oas','bb_oas')])
    add('CFTC持倉', 'weekly', [r['date'] for r in rows['positioning_now']], [r['date'] for r in old_pos])
    add('聯儲／淨流動性', 'weekly', [rt.get('liq_date')], [prior_rt.get('liq_date')])
    add('已確認週線', 'completed_week', [rows['sectors'][0].get('week_fw')],
        [r.get('week_fw') for r in read(previous/'sectors.json', [])])
    return dict(checked_at=datetime.now(timezone.utc).isoformat(), session=session, groups=groups,
                borrower_references=bonds, ai_summary_updated=False)


def fetch_news(work, env, log_path, timeout=300):
    """Headlines for the 新聞與連接 page (local runs only; news_feed.py). Never fails the refresh: on any error or
    timeout the copy of data/news_feed.json taken into the staging folder stays as it was, so the page keeps the
    previous headlines and shows the time of their last successful fetch."""
    try:
        with log_path.open('a') as log:
            subprocess.run([sys.executable, 'news_feed.py'], cwd=work, env=env, stdout=log, stderr=log,
                           check=True, timeout=timeout)
        return True
    except Exception as exc:
        try:
            with log_path.open('a') as log: log.write(f'news feed not updated ({type(exc).__name__}); previous feed kept\n')
        except OSError: pass
        return False


def fetch_us_economy(work, env, log_path, timeout=300):
    """FRED series for the 美國經濟 sub-page (us_economy.py). Never fails the refresh: series that fail keep their
    previous values (marked stale in data/us_economy.json), and on any other error the previous file stays."""
    try:
        with log_path.open('a') as log:
            subprocess.run([sys.executable, 'us_economy.py'], cwd=work, env=env, stdout=log, stderr=log,
                           check=True, timeout=timeout)
        return True
    except Exception as exc:
        try:
            with log_path.open('a') as log: log.write(f'us economy not updated ({type(exc).__name__}); previous file kept\n')
        except OSError: pass
        return False


def prune_older_runs(run_dir):
    """After a successful local run, keep only this run folder for its session; nothing reads older runs."""
    for other in run_dir.parent.glob('*_data_refresh'):
        if other.is_dir() and other != run_dir:
            shutil.rmtree(other, ignore_errors=True)


def run(render_only=False, root=ROOT):
    # root is dashboard/macro; its parent is the board folder (dashboard/) and the staging folder mirrors the project
    # layout (dashboard/macro, dashboard/evidence, dashboard/ai_cycle_watch) so every
    # script finds its inputs at the same relative places as in the real folders.
    board = root.parent
    with refresh_lock(root):
        session = completed_session()
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:6]
        run_dir = board/'logs'/session/(stamp+'_data_refresh')
        stage = run_dir/'staged'; sboard = stage/'dashboard'; work = sboard/'macro'
        work.mkdir(parents=True)
        for p in root.iterdir():
            if p.is_file() and p.suffix in ('.py','.js','.html','.md','.txt'):
                shutil.copy2(p, work/p.name)
        if (root/'data').exists(): shutil.copytree(root/'data', work/'data')
        # Copy only explicitly needed inputs, never the whole parent workspace.
        for name in ('evidence','ai_cycle_watch'):
            if (board/name).is_dir():
                shutil.copytree(board/name, sboard/name, ignore=shutil.ignore_patterns('__pycache__'))
        env = dict(os.environ, BOARD_ASOF=session, BOARD_STRICT_REFRESH='1', PYTHONUNBUFFERED='1')
        def command(args):
            with (run_dir/'execution.log').open('a') as log:
                subprocess.run([sys.executable, *args], cwd=work, env=env, stdout=log, stderr=log,
                               check=True, timeout=1800)
        try:
            if not render_only:
                for attempt in range(2):
                    try: command(['build_data.py']); break
                    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                        if attempt: raise
            else:
                session = read(work/'data/breadth_now.json')[0]['asof']
            rows = validate(work/'data', session, root/'data')
            bond_results, news_ok = [], None
            if not render_only:
                news_ok = fetch_news(work, env, run_dir/'execution.log')
                useco_ok = fetch_us_economy(work, env, run_dir/'execution.log')
                from bond_reference import collect
                bond_results = collect(sboard/'evidence/borrower_credit.json', session, run_dir)
                tracker = sboard/'ai_cycle_watch/track.py'
                if tracker.exists():
                    command([str(tracker)])
                    if read(sboard/'ai_cycle_watch/data/latest.json').get('asof') != session:
                        raise ValueError('AI cycle tracker date does not match')
            meta = metadata(rows, root/'data', bond_results, session)
            if render_only:
                meta = read(root/'data/refresh_meta.json', [meta])[0]
                meta.pop('summary_needs_review', None)  # left by builds that still carried a summary
            atomic_json(work/'data/refresh_meta.json', [meta])
            command(['build_site.py'])
            pairs = [(work/'data', root/'data'), (work/'site_private', root/'site_private')]
            if not render_only:
                pairs.append((sboard/'evidence/borrower_credit.json', board/'evidence/borrower_credit.json'))
                if (sboard/'ai_cycle_watch/data').exists():
                    pairs.append((sboard/'ai_cycle_watch/data', board/'ai_cycle_watch/data'))
            promote(pairs, run_dir/'previous')
            result = dict(state='success', session=session, checked_at=meta['checked_at'], groups=meta['groups'],
                          borrower_references=bond_results, ai_summary_updated=False)
            view = board.parent/'valuation and research'/'Backtests'/'scripts'/'59_board_view.py'
            if view.exists():   # local-only 估值 page: a private script outside this repository; a failure keeps its previous file
                try:
                    with (run_dir/'execution.log').open('a') as log:
                        subprocess.run([sys.executable, str(view)], cwd=view.parent, stdout=log, stderr=log, check=True, timeout=300)
                    result['local_view'] = 'written'
                except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
                    result['local_view'] = 'previous kept'
            if news_ok is not None: result['news_feed'] = 'fetched' if news_ok else 'previous kept'
            if not render_only: result['us_economy'] = 'fetched' if useco_ok else 'previous kept'
            atomic_json(run_dir/'result.json', result)
            prune_older_runs(run_dir)
            return result
        except Exception as exc:
            atomic_json(run_dir/'result.json', {'state':'failed','error':str(exc),'previous_snapshot_preserved':True})
            raise


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--render-only', action='store_true', help='Rebuild the page from the saved data and hand-kept files; no downloads')
    args = ap.parse_args()
    try: print(json.dumps(run(args.render_only), ensure_ascii=False))
    except Exception as exc:
        print(str(exc), file=sys.stderr); sys.exit(1)
