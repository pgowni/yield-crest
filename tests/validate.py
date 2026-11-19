"""Regression checks and synthetic rolling demand replay. Run offline."""
from datetime import date,timedelta
from pathlib import Path
from unittest.mock import patch
import json
import sqlite3

import numpy as np
from scipy.stats import poisson
from sklearn.linear_model import PoissonRegressor

from yieldcrest.datasets import read_dataset
from yieldcrest.domain import AS_OF,ROOT,connect,net_contribution,overlaps
from yieldcrest.forecasting import arrival_features,daily_records,pipeline,close_features
from yieldcrest.decision_engine import compare_calendar,joint_allocation,maintenance_options,replay_future,choose_service_allocation
from yieldcrest.assistant_chat import respond,execute_tool


def validate():
    with connect() as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        assert db.execute("""
            SELECT count(*) FROM bookings a JOIN bookings b ON a.face_id=b.face_id AND a.id<b.id
            WHERE a.start_date<=b.end_date AND a.end_date>=b.start_date
        """).fetchone()[0]==0
        assert db.execute("""
            SELECT count(*) FROM offers o JOIN enquiries e ON e.id=o.enquiry_id
            WHERE e.received>o.quoted OR o.quoted>o.decided
        """).fetchone()[0]==0
        # Adding an eventual booking must not leak a repeat-customer flag into an earlier quote.
        mem=sqlite3.connect(":memory:")
        mem.row_factory=sqlite3.Row
        db.backup(mem)
        before=close_features(mem,1,1,"2025-01-01","2025-01-10","2025-01-20",20000)
        mem.execute("UPDATE bookings SET confirmed='2026-01-01' WHERE start_date>='2025-01-01'")
        after=close_features(mem,1,1,"2025-01-01","2025-01-10","2025-01-20",20000)
        assert before==after
        # Simple leakage check uses a future observation unavailable at the quote.
        mem.execute("UPDATE offers SET gross=gross*2 WHERE quoted>'2025-01-01'")
        assert close_features(mem,1,1,"2025-01-01","2025-01-10","2025-01-20",20000)==before
        mem.close()
    assert net_contribution(10000,10,.8,.1,500,True,100)==5700
    assert net_contribution(10000,10,cash_adjust=True,delay=60)<10000
    event={"arrival":"2026-11-21","start":"2026-12-05","end":"2026-12-14","gross":70000}
    assert replay_future([event],[("2026-12-05","2026-12-05")],0,False)==0
    assert replay_future([event],[],0,False)==69200
    assert replay_future([event],[],0,False,release=date(2026,11,22))==0
    original=compare_calendar(1,1)
    moved=compare_calendar(1,1,shift=-5)
    assert original["wait"]==moved["wait"]  # same future paths
    assert original["break_even_gross"]!=moved["break_even_gross"]
    near=(original["break_even_gross"]+moved["break_even_gross"])/2
    assert compare_calendar(1,1,gross=near)["difference"]*compare_calendar(1,1,shift=-5,gross=near)["difference"]<0
    assert compare_calendar(1,1,gross=65000)["difference"]>0
    assert compare_calendar(1,1,shift=-5,gross=65000)["difference"]>0
    zero=joint_allocation(hold_days=0,probabilities={"1":0,"2":0,"3":0})
    certain=joint_allocation(hold_days=0,probabilities={"1":1,"2":1,"3":1})
    assert certain["financial_best"]["expected"]>=zero["financial_best"]["expected"]
    priority=joint_allocation(partner_tolerance=100000)
    assert priority["recommended"]["partner"]
    service=maintenance_options(1)
    assert all(w["Start"]<=w["Finish"]<=service["job"]["latest_finish"] for w in service["windows"])
    w=service["windows"][0]
    constrained=joint_allocation(maintenance={service["job"]["face_id"]:[(w["Start"],w["Finish"])]})
    assert constrained["recommended"]["expected"]>=0
    integrated=choose_service_allocation(1)
    assert integrated["net"]>=constrained["recommended"]["expected"]-service["job"]["service_cost"]-1e-6
    # Tool protocol test. All numbers in the response come from the executed Python function.
    calls=[
        {"candidates":[{"content":{"role":"model","parts":[{"functionCall":{"name":"compare_calendar","args":{"request_id":1,"face":1,"shift":-5}},"thoughtSignature":"preserved"}]}}]},
        {"candidates":[{"content":{"role":"model","parts":[{"text":"The earlier dates reduce the calculated threshold."}]}}]}]
    with patch("yieldcrest.assistant_chat.choose_model",return_value="test"),patch("yieldcrest.assistant_chat.api_call",side_effect=calls):
        answer,traces,_=respond("test","move earlier",[],{"settings":{}})
        assert traces[0]["result"]["break_even_gross"]==moved["break_even_gross"]
    for invalid in [{"partner_share":2},{"funding":-1}]:
        try:
            execute_tool("joint_allocation",invalid,{})
            raise AssertionError("Invalid tool input accepted")
        except ValueError:
            pass
    print("Passed integrity, chronology, leakage, costs, whole-campaign overlap, hold release, shared-path, switch/no-switch, joint, maintenance and chat-protocol checks.")


def replay():
    result=[]
    with connect() as db:
        for cutoff in ["2025-07-01","2026-03-01","2026-08-01"]:
            train_x,train_y,_=read_dataset(f"demand/replay/{cutoff}/train.csv")
            _,_,test_rows=read_dataset(f"demand/replay/{cutoff}/test.csv")
            model=pipeline(PoissonRegressor(alpha=.08,max_iter=1000))
            model.fit(train_x,train_y)
            for horizon in [30,14,7]:
                start=date.fromisoformat(cutoff)
                end=start+timedelta(days=horizon-1)
                observed=[];expected=[];covered=[]
                for face in range(1,13):
                    selected=[r for r in test_rows if int(r["face"])==face and str(start)<=r["date"]<=str(end)]
                    count=sum(float(r["enquiry_count"]) for r in selected)
                    features=[{key:r[key] if key=="face" else float(r[key]) for key in
                               ["face","festive_sales_period","month_sin","month_cos"]} for r in selected]
                    mean=float(model.predict(features).sum())
                    low,high=poisson.ppf([.1,.9],mean)
                    observed.append(count>0)
                    expected.append(1-np.exp(-mean))
                    covered.append(low<=count<=high)
                result.append({"Decision date":cutoff,"Lead horizon":horizon,"Faces":12,
                               "Mean predicted any-enquiry chance":round(float(np.mean(expected)),3),
                               "Observed share with enquiries":round(float(np.mean(observed)),3),
                               "Count interval coverage":round(float(np.mean(covered)),3),
                               "Brier":round(float(np.mean((np.array(expected)-observed)**2)),4)})
    (ROOT / "reports" / "replay.json").write_text(json.dumps({"replays":result,
        "interpretation":"Synthetic enquiry-count replay only. Three decision dates; site observations share seasonal demand conditions. No counterfactual revenue claim."},indent=2))
    print("Wrote synthetic T−30 / T−14 / T−7 rolling replay.")


if __name__=="__main__":
    validate()
    replay()

