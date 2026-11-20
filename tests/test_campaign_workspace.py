import unittest
from yieldcrest.decision_engine import connected_requests,joint_allocation

class CampaignTests(unittest.TestCase):
    def test_connections_require_dates_and_board_and_follow_indirect_conflicts(self):
        def r(i,faces,start='2026-11-25',end='2026-12-09'):
            return dict(id=i,faces=faces,start_date=start,end_date=end)
        records=[r(1,[1]),r(2,[1,2]),r(3,[2]),r(4,[3]),r(5,[1],'2026-12-10','2026-12-15')]
        self.assertEqual([x['id'] for x in connected_requests(records,1)],[1,2,3])
    def test_individual_deadlines_and_selected_price(self):
        result=joint_allocation(target_request=2,target_face=1,target_gross=50000,
            probabilities={'1':1,'2':1,'3':1},hold_days_by_request={'1':1,'2':2,'3':3})
        self.assertEqual(result['hold_expiries'],{'1':'2026-11-20','2':'2026-11-21','3':'2026-11-22'})
        self.assertTrue(next(x for x in result['best_including']['2']['assignments'] if x['request_id']==2)['sites'])
        self.assertFalse(next(x for x in result['best_excluding']['2']['assignments'] if x['request_id']==2)['sites'])
        lower=joint_allocation(target_request=2,target_face=1,target_gross=40000,
            probabilities={'1':1,'2':1,'3':1},hold_days_by_request={'1':1,'2':2,'3':3})
        self.assertGreater(result['best_including']['2']['expected'],lower['best_including']['2']['expected'])
    def test_disconnected_target_does_not_pull_in_other_requests(self):
        result=joint_allocation(target_request=2,target_face=1,target_shift=20)
        self.assertEqual(result['included_request_ids'],[2])
    def test_invalid_individual_deadline(self):
        with self.assertRaises(ValueError):joint_allocation(hold_days_by_request={'2':6})

if __name__=='__main__':unittest.main()
