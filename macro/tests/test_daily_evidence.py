"""Protect dated comparisons and the AI tracker's dated readings; no network required."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_site
from daily_summary import credit_change, reference_reading, borrower_reading


def quote(day, price, yield_pct, **extra):
    return dict(price_date=day, clean_price_per_100=price, yield_pct=yield_pct,
                isin='TEST123', currency='USD', yield_type='YTW semiannual',
                provider='Example', price_basis='vendor_close_per_100',
                source='https://example.com/quote', **extra)


class EvidenceTests(unittest.TestCase):
    def read(self, rows, asof='2026-10-15'):
        return reference_reading({'reference_quotes': rows}, asof)

    def test_price_percent_and_yield_basis_points_are_distinct(self):
        r = self.read([quote('2026-10-14', 80, 15), quote('2026-10-15', 84, 14.5)])
        self.assertEqual((r['price_change'], r['price_return_pct'], r['yield_change_bp']), (4, 5, -50))
        self.assertIn('未確認', r['status'])

    def test_revision_is_not_another_day(self):
        r = self.read([quote('2026-10-14',80,15), quote('2026-10-15',83,14.6,superseded=True), quote('2026-10-15',84,14.5)])
        self.assertEqual(r['price_change'],4)
        self.assertEqual(r['prior']['price_date'],'2026-10-14')

    def test_unresolved_duplicate_is_not_cherry_picked(self):
        r = self.read([quote('2026-10-14',80,15),quote('2026-10-15',83,14.6),quote('2026-10-15',84,14.5)])
        self.assertIsNone(r['latest'])
        self.assertIsNone(r['price_change'])

    def test_future_quote_and_invalid_values_are_excluded(self):
        r = self.read([quote('2026-10-14',80,15),quote('2026-10-16',84,14.5),quote('2026-10-15',float('nan'),14)])
        self.assertEqual(r['latest']['price_date'],'2026-10-14')
        self.assertIsNone(r['price_change'])

    def test_different_bond_or_basis_is_not_compared(self):
        for key,value in [('isin','OTHER123'),('yield_type','YTM'),('price_basis','dirty'),('settlement_basis','T+2')]:
            last=quote('2026-10-15',84,14.5);last[key]=value
            self.assertIsNone(self.read([quote('2026-10-14',80,15),last])['price_change'])

    def test_missing_prior_is_not_zero(self):
        self.assertIsNone(self.read([quote('2026-10-15',84,14.5)])['price_change'])

    def test_credit_needs_two_shared_real_observation_dates(self):
        rt={'ccc_date':'2026-10-14','bb_date':'2026-10-14','ccc_prev_date':'2026-10-13','bb_prev_date':'2026-10-13','ccc_1d':15,'bb_1d':8}
        self.assertEqual(credit_change(rt,['ccc','bb']),(7,'2026-10-14','2026-10-13'))
        for key,value in [('bb_date','2026-10-13'),('ccc_1d',float('nan')),('ccc_prev_date','2026-10-14')]:
            other=rt|{key:value};self.assertIsNone(credit_change(other,['ccc','bb'])[0])

    def test_bond_reference_does_not_confirm_borrower_spread(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'macro/data').mkdir(parents=True);(root/'evidence').mkdir()
            (root/'evidence/borrower_credit.json').write_text(json.dumps({'issuers':[{'id':i,'name':i,'reference_quotes':[quote('2026-10-14',80,15),quote('2026-10-15',84,14.5)]} for i in ['CRWV','ORCL']]}))
            with patch('daily_summary.DATA',root/'macro/data'):
                self.assertEqual(borrower_reading('2026-10-15')[0],'信用改善未確認')
                self.assertEqual(borrower_reading('2026-10-19')[0],'信用改善未確認')

    def test_ai_tracker_shows_only_dated_readings(self):
        doc={'updated':'2026-11-20','indicators':[
            {'item':'hand','reading':'x','date':'2026-08-31','source':'10-Q','url':'https://example.com/q'},
            {'item':'empty','reading':None,'date':None},
            {'item':'undated','reading':'z','date':'早段'},
            {'item':'hy','live':'hy_oas'},
            {'item':'bond without board data','live':'bond:CRWV'},
            {'item':'cds','live':'cds:CRWV'}],'tracking':[]}
        data={'rates_now':[{'hy_oas':3.4,'hy_oas_date':'2026-11-18','hy_oas_1w':5.0,'hy_oas_base_1w':'2026-11-11'}],
              'borrower_credit':[{'issuers':[],'cds_reference':[{'id':'CRWV','readings':[
                  {'date':'2026-10-26','value_bp':1148,'source':'https://example.com/cds','second_hand':True}]}]}]}
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'ai_tracker.json';path.write_text(json.dumps(doc))
            with patch.object(build_site,'AI_TRACKER',path):
                out=build_site.ai_tracker(data)[0];rows={r['item']:r for r in out['indicators']}
                # rows without a dated reading, live rows the board cannot fill, and CDS are left out, never carried forward
                self.assertEqual(list(rows),['hand','hy'])
                self.assertEqual(rows['hand']['date'],'2026-08-31');self.assertNotIn('from_board',rows['hand'])
                self.assertEqual((rows['hy']['date'],rows['hy']['from_board']),('2026-11-18',True));self.assertIn('340',rows['hy']['reading'])
                for r in out['indicators']:
                    for gone in ('status','old','second_hand','conflict','date_shown'):
                        self.assertNotIn(gone,r)
                self.assertNotIn('quarter_end',out)
            with patch.object(build_site,'AI_TRACKER',Path(temp)/'missing.json'):
                self.assertTrue(build_site.ai_tracker({})[0]['missing'])

    def test_ai_tracker_file_shape(self):
        # the hand-kept file: six stages in order, a dated judgement, watch rows with if-then lines, and evidence rows
        # that are either board data ("live") or a dated reading with a source; no flags that marked doubt
        doc=json.loads(build_site.AI_TRACKER.read_text()) if build_site.AI_TRACKER.is_file() else None
        if doc is None:
            self.skipTest('no ai_tracker.json in this checkout')
        self.assertEqual([s['n'] for s in doc['stages']],[1,2,3,4,5,6])
        self.assertTrue(build_site._iso(doc['current']['judged_on']))
        self.assertIn(doc['current']['frontier']['stage'],range(1,7));self.assertIn(doc['current']['majority']['stage'],range(1,7))
        self.assertNotIn('tracking',doc)
        for w in doc['watch']:
            self.assertTrue(w['event'] and w['if'])
            self.assertTrue(build_site._iso(w['date']) if w.get('date') else w.get('when') in ('未公佈','每次看板刷新'))
            for x in w['if']:self.assertTrue(x['if'] and x['then'])
        for r in doc['indicators']:
            self.assertTrue(r.get('means'))
            if r.get('live'):
                self.assertIn(r['live'],('bond:CRWV','bond:ORCL','hy_oas','b_oas','sofr_iorb'))
            else:
                self.assertTrue(r['reading'] and build_site._iso(r['date']) and r['source'])
                self.assertTrue(r.get('url','https://').startswith('https://'))
        text=json.dumps(doc,ensure_ascii=False)
        for gone in ('S1.5','上次判斷','"events"','points_to','second_hand','conflict','date_shown','"old"','caveats',
                     'previous_update','"cds:'):
            self.assertNotIn(gone,text)


if __name__=='__main__':unittest.main()
