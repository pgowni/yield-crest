import unittest
from yieldcrest.campaign_analysis import analyze_campaign

class PlanBreakdownTests(unittest.TestCase):
    def test_low_probability_alternative_reconciles_with_board_and_campaign_totals(self):
        result=analyze_campaign(2,1,0,43000,{'1':.62,'2':.05,'3':.58},{'1':3,'2':3,'3':3},5000,.8)
        for plan in [result['recommended'],result['best_including']['2'],result['best_excluding']['2']]:
            b=plan['breakdown']
            self.assertAlmostEqual(b['current_campaigns']+b['future_bookings']-b['maintenance_expense'],plan['expected'],places=6)
            self.assertAlmostEqual(sum(r['expected'] for r in b['boards']),plan['expected'],places=6)
            self.assertAlmostEqual(sum(r['expected_contribution'] for r in b['campaigns']),b['current_campaigns'],places=6)
            self.assertEqual(b['maintenance_expense'],sum(j['cost'] for j in plan['maintenance_schedule']))
        alternative=result['best_excluding']['2']['breakdown']
        lotus=next(r for r in alternative['campaigns'] if r['request_id']==2)
        self.assertEqual(lotus['board_ids'],[])
        self.assertEqual(lotus['expected_contribution'],0)
