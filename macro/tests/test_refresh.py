"""Failure preservation, source dates and local request security."""
import copy
import json
from pathlib import Path
import tempfile
import subprocess
import threading
import unittest
import urllib.request
from urllib.error import HTTPError
from unittest.mock import patch

from bond_reference import BONDS, parse_quote, merge_quote
from market_clock import completed_session, week_complete
from refresh import Busy, promote, prune_older_runs, refresh_lock, run
from serve import make_server, Updates


class RefreshTests(unittest.TestCase):
    def test_completed_calendar_handles_intraday_holiday_and_early_close(self):
        self.assertEqual(completed_session('2026-10-16T19:55:00Z'), '2026-10-15')
        self.assertEqual(completed_session('2026-10-16T20:16:00Z'), '2026-10-16')
        self.assertEqual(completed_session('2026-11-26T22:00:00Z'), '2026-11-25')
        self.assertEqual(completed_session('2026-11-27T18:16:00Z'), '2026-11-27')
        self.assertTrue(week_complete('2026-04-02'))  # Good Friday holiday
        self.assertFalse(week_complete('2026-10-15'))  # missing Friday cannot become confirmed on Saturday

    def test_independent_writers_share_a_lock(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            with refresh_lock(root):
                with self.assertRaises(Busy):
                    with refresh_lock(root): pass
            with refresh_lock(root): pass

    def test_failed_promotion_restores_all_old_outputs(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            for name,value in [('old1','a'),('old2','b'),('new1','x')]: (root/name).write_text(value)
            with self.assertRaises(FileNotFoundError):
                promote([(root/'new1',root/'old1'),(root/'missing',root/'old2')],root/'backup')
            self.assertEqual((root/'old1').read_text(),'a')
            self.assertEqual((root/'old2').read_text(),'b')
            self.assertEqual((root/'new1').read_text(),'x')

    def test_download_failure_retries_once_and_keeps_live_snapshot(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/'macro';root.mkdir()
            (root/'data').mkdir();(root/'data/marker.json').write_text('["old"]')
            (root/'site_private').mkdir();(root/'site_private/index.html').write_text('old board')
            failure=subprocess.CalledProcessError(1,['build_data.py'])
            with patch('refresh.subprocess.run',side_effect=failure) as call:
                with self.assertRaises(subprocess.CalledProcessError): run(root=root)
                self.assertEqual(call.call_count,2)
            self.assertEqual((root/'data/marker.json').read_text(),'["old"]')
            self.assertEqual((root/'site_private/index.html').read_text(),'old board')
            results=list(Path(t).glob('logs/*/*/result.json'))
            self.assertEqual(len(results),1)
            self.assertTrue(json.loads(results[0].read_text())['previous_snapshot_preserved'])

    def test_success_keeps_only_latest_run_folder_of_its_session(self):
        with tempfile.TemporaryDirectory() as t:
            base=Path(t)/'board updates'
            for name in ['2026-11-13/a_data_refresh','2026-11-13/b_data_refresh','2026-11-13/c_data_refresh','2026-11-12/z_data_refresh']:
                (base/name/'previous').mkdir(parents=True)
            (base/'2026-11-13/notes.txt').write_text('kept')
            prune_older_runs(base/'2026-11-13/c_data_refresh')
            self.assertEqual(sorted(p.name for p in (base/'2026-11-13').iterdir()),['c_data_refresh','notes.txt'])
            self.assertTrue((base/'2026-11-12/z_data_refresh').is_dir())

    def test_bond_parser_requires_dated_matching_instrument_and_keeps_revisions(self):
        html='<h1>CoreWeave US21873SAK42</h1><p>USD semiannual Settlement: T+2. Last close (15 Oct 2026): price 81.50, yield to worst 14.45%.</p>'
        q=parse_quote(html,BONDS[0],'2026-10-16','2026-10-17T00:00:00Z')
        self.assertFalse(q['eligible_for_signal'])
        self.assertEqual(q['price_date'],'2026-10-15')
        for bad in [html.replace('US21873SAK42','OTHER'),html.replace('15 Oct','19 Oct'),html.replace('Last close','Current')]:
            with self.assertRaises(ValueError): parse_quote(bad,BONDS[0],'2026-10-16','now')
        issuer={'reference_quotes':[]}
        self.assertEqual(merge_quote(issuer,copy.deepcopy(q)),'new_observation')
        self.assertEqual(merge_quote(issuer,copy.deepcopy(q)),'unchanged')
        self.assertEqual(merge_quote(issuer,q|{'clean_price_per_100':81.6}),'revision')
        self.assertTrue(issuer['reference_quotes'][0]['superseded'])
        self.assertEqual(len(issuer['reference_quotes']),2)

    def test_settlement_revision_is_preserved_without_a_new_observation(self):
        html = 'CoreWeave US21873SAK42 USD semiannual Settlement T+2 Last close (15 Oct 2026): price 81.5, yield to worst 14.45%'
        old = parse_quote(html, BONDS[0], '2026-10-19', 'earlier')
        new = parse_quote(html.replace('T+2', 'T+1'), BONDS[0], '2026-10-19', 'later')
        self.assertEqual(new['settlement_basis'], 'T+1')
        self.assertFalse(new['settlement_verified'])
        issuer = {'reference_quotes': [copy.deepcopy(old)]}
        self.assertEqual(merge_quote(issuer, new), 'revision')
        self.assertTrue(issuer['reference_quotes'][0]['superseded'])
        self.assertEqual({r['price_date'] for r in issuer['reference_quotes']}, {'2026-10-15'})
        self.assertEqual(merge_quote(issuer, copy.deepcopy(new)), 'unchanged')
        for invalid in [html.replace('T+2', 'T+20'), html.replace('Settlement T+2', ''), html + ' Settlement T+1']:
            with self.assertRaises(ValueError):
                parse_quote(invalid, BONDS[0], '2026-10-19', 'later')

    def test_simultaneous_clicks_run_only_one_worker(self):
        with tempfile.TemporaryDirectory() as t:
            updater=Updates(Path(t)); entered=threading.Event(); release=threading.Event()
            def worker(**kwargs):
                entered.set(); release.wait(3); return {'state':'success'}
            with patch('serve.run',side_effect=worker) as fn:
                self.assertEqual(updater.start()['state'],'running')
                self.assertTrue(entered.wait(1))
                self.assertEqual(updater.start()['state'],'running')
                self.assertEqual(fn.call_count,1)
                release.set()

    def test_server_blocks_cross_origin_invalid_host_and_wrong_token(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'site_private').mkdir();(root/'site_private/index.html').write_text('safe')
            server=make_server(0,root)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{server.server_port}'
            try:
                with urllib.request.urlopen(base+'/api/update') as r: token=json.load(r)['token']
                for headers in [{'Origin':'https://evil.example','X-Refresh-Token':token},
                                {'Origin':base,'X-Refresh-Token':'wrong'},
                                {'Host':'evil.example','Origin':base,'X-Refresh-Token':token}]:
                    req=urllib.request.Request(base+'/api/update',method='POST',headers=headers)
                    with self.assertRaises(HTTPError) as e: urllib.request.urlopen(req)
                    self.assertEqual(e.exception.code,403)
                    e.exception.close()
                with patch.object(server.updates,'start',return_value={'state':'running'}) as start:
                    req=urllib.request.Request(base+'/api/update',method='POST',headers={'Origin':base,'X-Refresh-Token':token})
                    with urllib.request.urlopen(req) as r: self.assertEqual(r.status,202)
                    self.assertEqual(start.call_count,1)
                with self.assertRaises(HTTPError) as e: urllib.request.urlopen(base+'/../holdings.json')
                e.exception.close()
            finally:
                server.shutdown();server.server_close();thread.join()


if __name__ == '__main__': unittest.main()
