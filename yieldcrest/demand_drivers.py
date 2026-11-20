"""Measured forecast signals, not post-hoc claims about why an allocation won."""
from datetime import timedelta,date
import math
import numpy as np
from yieldcrest.domain import connect,AS_OF,HORIZON_END,dates,overlaps,days
from yieldcrest.forecasting import models,arrival_features,season,timing_templates
from yieldcrest.decision_engine import scenario_data


def demand_drivers(face,start,end):
    with connect() as db:
        periods=[dict(r) for r in db.execute('SELECT * FROM seasonal_periods WHERE start_date<=? AND end_date>=?',(str(end),str(start)))]
        features=[arrival_features(db,face,d) for d in dates(AS_OF+timedelta(days=1),HORIZON_END)]
        trained=models()
        actual=trained['arrival'].predict(features)
        off=trained['arrival'].predict([{**f,'festive_sales_period':0.} for f in features])
        flagged=sum(f['festive_sales_period']>0 for f in features)
        duration=days(start,end)
        price_features={'face':str(face),'duration_days':float(duration),'festive_campaign':1.}
        regular={**price_features,'festive_campaign':0.}
        price_ratio=math.exp(float(trained['price'].predict([price_features])[0]-trained['price'].predict([regular])[0]))
        templates=timing_templates(db,face,HORIZON_END)
        local=[t for t in templates if t[0]==face]
        samples=[]
        for label,group in [('This board',local),('Portfolio',templates)]:
            for festive in [False,True]:
                subset=[t for t in group if bool(t[4])==festive]
                samples.append({'Group':label,'Campaign period':'Festive overlap' if festive else 'Other dates','Accepted bookings':len(subset),
                                'Average achieved daily rent':float(np.mean([t[3] for t in subset])) if subset else None,
                                'Average campaign days':float(np.mean([t[2] for t in subset])) if subset else None})
        paths,evidence=scenario_data(face)
        candidates=[e for path in paths for e in path if overlaps(e['start'],e['end'],start,end)]
        festive_candidates=[e for e in candidates if season(db,e['start'],e['end'])]
        historical_periods=[dict(r) for r in db.execute('SELECT label,start_date,end_date FROM seasonal_periods WHERE end_date<?',(str(AS_OF),))]
        return {'periods':periods,'expected_enquiries':float(sum(actual)),'enquiries_without_festive_indicator':float(sum(off)),
            'flagged_days':int(flagged),'price_festive_ratio':price_ratio,'history':samples,'evidence':evidence,
            'overlapping_candidates_per_path':len(candidates)/len(paths),'festive_candidates_per_path':len(festive_candidates)/len(paths),
            'historical_periods':historical_periods,'local_weight':len(local)/(len(local)+25)}
