"""Run offline after intentionally changing the committed synthetic dataset."""
import json
import math
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import PoissonRegressor, Ridge
from sklearn.metrics import brier_score_loss, mean_poisson_deviance, mean_absolute_error

from domain import AS_OF, connect, days
from forecasting import ARTIFACT, close_candidates, close_records, daily_records, pipeline, season


def train():
    with connect() as db:
        records=close_records(db)
        # Validation chooses the algorithm. The final period stays untouched during selection.
        splits=[("Validation","2025-07-01","2025-11-01"),("Test","2026-03-01","2026-08-01")]
        scores=[]
        for stage,cutoff,end in splits:
            train=[r for r in records if r["quoted"]<cutoff and r["decided"]<cutoff]
            test=[r for r in records if cutoff<=r["quoted"]<end]
            prior=np.mean([r["outcome"]=="Won" for r in train])
            y=[r["outcome"]=="Won" for r in test]
            scores.append({"Stage":stage,"Model":"Historical win rate","Train":len(train),"Test":len(test),
                           "Brier":float(brier_score_loss(y,[prior]*len(y)))})
            for label,model in close_candidates().items():
                model.fit([r["features"] for r in train],[r["outcome"]=="Won" for r in train])
                prediction=model.predict_proba([r["features"] for r in test])[:,1]
                scores.append({"Stage":stage,"Model":label,"Train":len(train),"Test":len(test),
                               "Brier":float(brier_score_loss(y,prediction))})
        candidates=[s for s in scores if s["Stage"]=="Validation" and s["Model"]!="Historical win rate"]
        selected=min(candidates,key=lambda s:s["Brier"])["Model"]
        close=close_candidates()[selected]
        close.fit([r["features"] for r in records],[r["outcome"]=="Won" for r in records])
        daily=list(daily_records(db,AS_OF))
        cutoff="2026-03-01"
        older=[r for r in daily if r[0]<cutoff]
        later=[r for r in daily if r[0]>=cutoff]
        arrival=pipeline(PoissonRegressor(alpha=.08,max_iter=1000))
        arrival.fit([r[2] for r in older],[r[3] for r in older])
        predicted=arrival.predict([r[2] for r in later])
        prior=np.mean([r[3] for r in older])
        arrival_report={"train_face_days":len(older),"test_face_days":len(later),
            "poisson_deviance":float(mean_poisson_deviance([r[3] for r in later],predicted)),
            "baseline_deviance":float(mean_poisson_deviance([r[3] for r in later],[prior]*len(later))),
            "brier":float(brier_score_loss([r[3]>0 for r in later],1-np.exp(-predicted)))}
        arrival.fit([r[2] for r in daily],[r[3] for r in daily])
        prices=[]
        for r in records:
            if r["outcome"]=="Won":
                prices.append(({"face":str(r["face_id"]),"duration_days":float(days(r["requested_start"],r["requested_end"])),
                                "festive_campaign":float(season(db,r["requested_start"],r["requested_end"]))},
                               math.log(r["gross"]/days(r["requested_start"],r["requested_end"]))))
        price=pipeline(Ridge(alpha=10))
        price.fit([x for x,y in prices],[y for x,y in prices])
        ARTIFACT.parent.mkdir(exist_ok=True)
        joblib.dump({"close":close,"arrival":arrival,"price":price},ARTIFACT)
        report={"as_of":AS_OF.isoformat(),"close_selected_on_validation":selected,
                "offer_metrics":scores,"arrival_metrics":arrival_report,
                "features":["site","festive sales period","month sine/cosine","relative daily quote",
                            "duration","lead time","prior completed bookings"],
                "limitations":["Synthetic replay demonstrates plumbing and point-in-time controls only.",
                               "Achieved prices are conditional on historical accepted bookings.",
                               "Only two completed illustrative festive periods exist.",
                               "Future buyer location is fixed to a single face.",
                               "Daily arrival and conversion assumptions originate in the published generator."]}
        Path(__file__).with_name("models").joinpath("evaluation.json").write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))


if __name__=="__main__":
    train()
