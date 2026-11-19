"""Treasury auction rows: competitive shares, nominal coupons only, same-term history."""
import unittest
from auctions import parse, with_history


def rec(term='10-Year', date='2026-10-07', hy='5.300', dealer=984000000, direct=6618200000, indirect=31063238000, **kw):
    r = {'originalSecurityTerm': term, 'competitiveAuctionCloseDate': date + 'T00:00:00', 'highYield': hy,
         'bidToCoverRatio': '2.77', 'highPrice': '94.864261', 'offeringAmount': '39000000000', 'reopening': 'Yes',
         'cusip': 'X' + date, 'inflationProtected': 'No', 'floatingRate': 'No',
         'primaryDealersCompetitiveParAwarded': str(dealer), 'directBiddersCompetitiveParAwarded': str(direct),
         'indirectBiddersCompetitiveParAwarded': str(indirect), 'somaNoncompetitiveParAwarded': '926290200'}
    r.update(kw)
    return r


class AuctionTests(unittest.TestCase):
    def test_shares_match_the_published_competitive_split(self):
        r = parse(rec())
        self.assertEqual((r['indirect_pct'], r['direct_pct'], r['dealer_pct']), (80.3, 17.1, 2.5))
        self.assertEqual(r['soma_bn'], 0.93)
        self.assertEqual(r['term'], '10Y')

    def test_tips_frn_other_terms_and_pending_results_are_left_out(self):
        self.assertIsNone(parse(rec(inflationProtected='Yes')))
        self.assertIsNone(parse(rec(floatingRate='Yes')))
        self.assertIsNone(parse(rec(term='4-Week')))
        self.assertIsNone(parse(rec(hy=None)))

    def test_change_and_six_auction_average_use_the_same_term_only(self):
        rows = [parse(rec(date=f'2026-0{m}-10', hy=str(4 + m / 10))) for m in range(1, 8)]
        rows.append(parse(rec(term='30-Year', date='2026-07-11', hy='5.5')))
        out = {(r['term'], r['date']): r for r in with_history(rows)}
        last = out[('10Y', '2026-07-10')]
        self.assertEqual(last['chg_bp'], 10.0)
        self.assertEqual(last['prev_date'], '2026-06-10')
        self.assertEqual(last['btc_avg6'], 2.77)
        self.assertIsNone(out[('30Y', '2026-07-11')]['chg_bp'])
        self.assertIsNone(out[('10Y', '2026-06-10')]['btc_avg6'])


if __name__ == '__main__': unittest.main()
