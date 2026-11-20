"""Campaign-centric allocation, pending maintenance and probability sensitivity."""
from itertools import product
from yieldcrest.domain import connect,overlaps
from yieldcrest.decision_engine import live_requests,connected_requests,joint_allocation,maintenance_options


def analyze_campaign(rid,face,shift,gross,probabilities,holds,tolerance,share):
    from datetime import date,timedelta
    with connect() as db:
        requests=live_requests(db)
        target=next(r for r in requests if r['id']==rid)
        target['faces']=[face]
        for field in ['start_date','end_date']:
            target[field]=(date.fromisoformat(target[field])+timedelta(days=shift)).isoformat()
        relevant=connected_requests(requests,rid)
        faces={f for r in relevant for f in r['faces']}
        jobs=[dict(j) for j in db.execute("SELECT * FROM maintenance_jobs WHERE status='Proposed'")
              if j['face_id'] in faces and any(j['face_id'] in r['faces'] and overlaps(j['earliest_start'],j['latest_finish'],r['start_date'],r['end_date']) for r in relevant)]
    choices=[]
    for job in jobs:
        windows=maintenance_options(job['id'])['windows']
        if not windows:raise ValueError('No feasible maintenance window for '+job['task'])
        # Keep the three lowest forecast-loss windows and the least-loss window
        # that avoids all current requests. This bounds interactive demo latency.
        candidates=windows[:3]
        avoiding=[w for w in windows if all(not overlaps(w['Start'],w['Finish'],r['start_date'],r['end_date']) for r in relevant if job['face_id'] in r['faces'])]
        if avoiding and avoiding[0] not in candidates:candidates.append(avoiding[0])
        choices.append(candidates)
    candidates=[];last=None
    for windows in product(*choices):
        blocks={}
        for job,w in zip(jobs,windows):blocks.setdefault(job['face_id'],[]).append((w['Start'],w['Finish']))
        result=joint_allocation(probabilities=probabilities,partner_tolerance=0,partner_share=share,
            target_request=rid,target_face=face,target_shift=shift,target_gross=gross,
            hold_days_by_request=holds,maintenance=blocks)
        last=result
        expense=sum(j['service_cost'] for j in jobs)
        schedule=[dict(job_id=j['id'],board_id=j['face_id'],task=j['task'],start=w['Start'],end=w['Finish'],cost=j['service_cost']) for j,w in zip(jobs,windows)]
        for plan in result['all_plans']:
            p=dict(plan)
            for key in ['expected','p10','p90','target_success','target_failure']:p[key]-=expense
            p['maintenance_schedule']=schedule
            p['breakdown']={**plan['breakdown'],'maintenance_expense':expense,'total':p['expected'],
                'boards':[{**b,'maintenance_expense':sum(j['cost'] for j in schedule if j['board_id']==b['board_id']),
                    'expected':b['expected']-sum(j['cost'] for j in schedule if j['board_id']==b['board_id'])} for b in plan['breakdown']['boards']]}
            candidates.append(p)
    def includes(p):return bool(next(a for a in p['assignments'] if a['request_id']==rid)['sites'])
    def best(pool):return max(pool,key=lambda p:p['expected']) if pool else None
    financial=best(candidates)
    preferred=best([p for p in candidates if p['partner'] and financial['expected']-p['expected']<=tolerance]) or financial
    included=best([p for p in candidates if includes(p)])
    excluded=best([p for p in candidates if not includes(p)])
    sweep=[]
    for percent in range(101):
        probability=percent/100
        inc=max((p['target_failure']*(1-probability)+p['target_success']*probability for p in candidates if includes(p)),default=None)
        exc=max(p['target_failure']*(1-probability)+p['target_success']*probability for p in candidates if not includes(p))
        sweep.append({'chance':percent,'advantage':None if inc is None else inc-exc})
    switches=[{'from':sweep[i-1]['chance'],'to':row['chance']} for i,row in enumerate(sweep) if i and row['advantage'] is not None and (row['advantage']>=0)!=(sweep[i-1]['advantage']>=0)]
    return {**last,'all_plans':[], 'recommended':preferred,'financial_best':financial,
        'best_including':{str(rid):included},'best_excluding':{str(rid):excluded},
        'tradeoff':financial['expected']-preferred['expected'],'chance_sweep':sweep,'chance_switches':switches,
        'maintenance_jobs':jobs,'maintenance_candidates_per_job':[len(c) for c in choices],
        'maintenance_scope':'Proposed jobs treated as required within their recorded windows. Search uses up to four candidate windows per job, not every possible service calendar. All displayed contribution figures include direct maintenance expense.'}
