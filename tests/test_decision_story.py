import unittest
from copy import deepcopy
from yieldcrest.decision_story import decision_story

class StoryTests(unittest.TestCase):
    def fixture(self):
        return {'recommended':{'assignments':[{'request_id':2,'sites':[]}],
                'breakdown':{'campaigns':[],'boards':[{'board_id':1,'future_bookings':12000}]}},
                'best_including':{'2':{'expected':20000}},'best_excluding':{'2':{'expected':24000}},
                'hold_expiries':{'2':'2026-11-22'},'tradeoff':0}
    def story(self,r):return decision_story(r,2,1,'2026-11-25','2026-12-09','Lotus','Ameerpet',.05)
    def test_open_for_future_business(self):
        s=self.story(self.fixture());self.assertEqual(s['mode'],'future')
        self.assertIn('No other current client',s['paragraphs'][0]);self.assertIn('₹12,000',' '.join(s['paragraphs']))
    def test_current_competitor_not_called_empty(self):
        r=self.fixture();r['recommended']['breakdown']['campaigns']=[dict(request_id=1,client='Meridian Ads',board_ids=[1],start='2026-11-25',end='2026-12-09')]
        s=self.story(r);self.assertEqual(s['mode'],'competitor');self.assertIn('Meridian Ads',s['headline'])
    def test_accepted_campaign_has_distinct_wording(self):
        r=self.fixture();r['recommended']['assignments'][0]['sites']=['Ameerpet']
        self.assertEqual(self.story(r)['mode'],'accept')
    def test_maintenance_has_distinct_wording(self):
        r=self.fixture();r['recommended']['maintenance_schedule']=[dict(board_id=1,start='2026-11-25',end='2026-11-26')]
        self.assertEqual(self.story(r)['mode'],'maintenance')
