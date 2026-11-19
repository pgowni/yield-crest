"""Point-in-time feature construction and offline-trained model loading."""
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
import math

import joblib
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction import DictVectorizer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression, PoissonRegressor, Ridge
from sklearn.ensemble import RandomForestClassifier

from domain import AS_OF, dates, days, overlaps

ARTIFACT = Path(__file__).with_name("models") / "forecast.joblib"


def season(db, start, end):
    return bool(db.execute(
        "SELECT 1 FROM seasonal_periods WHERE start_date<=? AND end_date>=?",
        (str(end), str(start))).fetchone())


def arrival_features(db, face, current):
    """Daily information available without inspecting subsequent enquiries."""
    current = date.fromisoformat(str(current))
    upcoming = db.execute("SELECT start_date,end_date FROM seasonal_periods WHERE end_date>=? ORDER BY start_date LIMIT 1",
                          (current.isoformat(),)).fetchone()
    lead_period = bool(upcoming and date.fromisoformat(upcoming[0])-timedelta(days=30) <= current <= date.fromisoformat(upcoming[1]))
    return {"face": str(face), "festive_sales_period": float(lead_period),
            "month_sin": math.sin(2*math.pi*current.month/12),
            "month_cos": math.cos(2*math.pi*current.month/12)}


def close_features(db, face, client, quote, start, end, gross):
    repeat = db.execute("""
        SELECT count(*) FROM bookings b JOIN offers o ON o.id=b.offer_id
        JOIN enquiries e ON e.id=o.enquiry_id
        WHERE e.client_id=? AND b.end_date<? AND b.confirmed<?
    """, (client,str(quote),str(quote))).fetchone()[0]
    duration=days(start,end)
    base=db.execute("SELECT base_daily FROM faces WHERE id=?",(face,)).fetchone()[0]
    return {"face":str(face), "daily_rate_relative_to_site":gross/duration/base,
            "duration_days":float(duration), "lead_days":float((date.fromisoformat(str(start))-date.fromisoformat(str(quote))).days),
            "festive_campaign":float(season(db,start,end)), "prior_completed_bookings":float(min(repeat,10))}


def close_records(db, before=AS_OF):
    result=[]
    for row in db.execute("""
        SELECT o.*,e.client_id,e.face_id,e.requested_start,e.requested_end
        FROM offers o JOIN enquiries e ON e.id=o.enquiry_id
        WHERE o.feasible_when_quoted=1 AND o.outcome IN ('Won','Lost') AND o.decided<?
        ORDER BY o.quoted,o.id
    """,(str(before),)):
        row=dict(row)
        row["features"]=close_features(db,row["face_id"],row["client_id"],row["quoted"],row["requested_start"],row["requested_end"],row["gross"])
        result.append(row)
    return result


def pipeline(estimator):
    return make_pipeline(DictVectorizer(sparse=False),StandardScaler(),estimator)


def close_candidates():
    return {"Logistic regression":pipeline(LogisticRegression(C=.4,max_iter=1000)),
            "Shallow random forest":pipeline(RandomForestClassifier(n_estimators=160,max_depth=3,min_samples_leaf=15,random_state=42))}


def daily_records(db, end):
    counts = {(r[0],r[1]):r[2] for r in db.execute(
        "SELECT face_id,received,count(*) FROM enquiries WHERE received<? GROUP BY face_id,received",(str(end),))}
    for current in dates("2024-01-01",date.fromisoformat(str(end))-timedelta(days=1)):
        for face, in db.execute("SELECT id FROM faces"):
            yield current.isoformat(),face,arrival_features(db,face,current),counts.get((face,current.isoformat()),0)


@lru_cache(maxsize=1)
def models():
    return joblib.load(ARTIFACT)


def close_probability(db, request, face, start=None, end=None):
    start=start or request["start_date"]
    end=end or request["end_date"]
    features=close_features(db,face,request["client_id"],AS_OF,start,end,request["gross"])
    return float(models()["close"].predict_proba([features])[0,1])


def timing_templates(db, face, future_date):
    """Pool joint lead-duration-rate observations, preserving their pairing.
    Only bookings confirmed before the snapshot are used for achieved-price samples.
    """
    templates=[]
    for r in db.execute("""
        SELECT e.face_id,e.received,e.requested_start,e.requested_end,o.gross
        FROM enquiries e JOIN offers o ON o.enquiry_id=e.id
        WHERE o.outcome='Won' AND o.decided<? AND e.received<?
    """,(AS_OF.isoformat(),AS_OF.isoformat())):
        duration=days(r[2],r[3])
        lead=(date.fromisoformat(r[2])-date.fromisoformat(r[1])).days
        templates.append((r[0],lead,duration,r[4]/duration,season(db,r[2],r[3])))
    return templates


def sample_paths(db, face, end_date, count=96, seed=7319):
    """Common random numbers: every competing calendar receives identical future paths."""
    model=models()
    features=[arrival_features(db,face,d) for d in dates(AS_OF+timedelta(days=1),end_date)]
    rates=model["arrival"].predict(features)
    templates=timing_templates(db,face,end_date)
    if not templates:
        raise ValueError("No achieved-rate history in the portfolio")
    local=[t for t in templates if t[0]==face]
    local_weight=len(local)/(len(local)+25)
    rng=np.random.default_rng(seed+face)
    paths=[]
    candidate_features=[]
    candidate_events=[]
    draws=[]
    days_list=list(dates(AS_OF+timedelta(days=1),end_date))
    for index in range(count):
        events=[]
        # Portfolio scenarios share a demand shock; individual arrivals retain their site noise.
        shock=np.random.default_rng(seed+index).lognormal(-.5*.2**2,.2)
        for current,lam in zip(days_list,rates):
            for _ in range(int(rng.poisson(lam*shock))):
                pool=local if local and rng.random()<local_weight else templates
                weights=np.array([3 if t[4]==season(db,current+timedelta(days=14),current+timedelta(days=28)) else 1 for t in pool],dtype=float)
                t=pool[int(rng.choice(len(pool),p=weights/weights.sum()))]
                _,lead,duration,daily,was_festive=t
                start=current+timedelta(days=lead)
                finish=start+timedelta(days=duration-1)
                if finish>end_date:
                    continue
                festive=season(db,start,finish)
                # Learned achieved-rate ratio adjusts a paired historical template to its new dates.
                f={"face":str(face),"duration_days":float(duration),"festive_campaign":float(festive)}
                original={"face":str(t[0]),"duration_days":float(duration),"festive_campaign":float(was_festive)}
                multiplier=math.exp(float(model["price"].predict([f])[0]-model["price"].predict([original])[0]))
                gross=daily*multiplier*duration
                client=int(rng.integers(1,37))
                feat=close_features(db,face,client,AS_OF,start,finish,gross)
                candidate_features.append(feat)
                candidate_events.append((index, {"arrival":current.isoformat(),"start":start.isoformat(),
                                                "end":finish.isoformat(),"gross":float(gross),
                                                "share":.8 if client==1 else 1., "commission":.05 if client%7==0 else 0.}))
                draws.append(rng.random())
        paths.append(events)
    if candidate_features:
        probabilities=model["close"].predict_proba(candidate_features)[:,1]
        for (index,event),draw,probability in zip(candidate_events,draws,probabilities):
            if draw<probability:
                paths[index].append(event)
    return paths, {"local_bookings":len(local),"pooled_bookings":len(templates),
                   "local_weight":round(local_weight,3),"seasonal_periods":len({str(r[0])[:4] for r in db.execute("SELECT start_date FROM seasonal_periods WHERE end_date<?",(AS_OF.isoformat(),))})}
