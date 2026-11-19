"""Run offline after intentionally changing the committed synthetic dataset."""
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import PoissonRegressor, Ridge
from sklearn.metrics import brier_score_loss, mean_poisson_deviance

from yieldcrest.domain import AS_OF, ROOT, connect
from yieldcrest.datasets import read_dataset
from yieldcrest.forecasting import ARTIFACT, close_candidates, pipeline


def train():
    with connect() as db:
        scores=[]
        for stage, folder, name in [("Validation","offer_close/validation","validation.csv"),
                                     ("Test","offer_close","test.csv")]:
            x_train,y_train,_=read_dataset(folder+"/train.csv")
            x_test,y_test,_=read_dataset(folder+"/"+name)
            prior=float(np.mean(y_train))
            scores.append({"Stage":stage,"Model":"Historical win rate","Train":len(x_train),"Test":len(x_test),
                           "Brier":float(brier_score_loss(y_test,[prior]*len(y_test)))})
            for label,model in close_candidates().items():
                model.fit(x_train,y_train)
                prediction=model.predict_proba(x_test)[:,1]
                scores.append({"Stage":stage,"Model":label,"Train":len(x_train),"Test":len(x_test),
                               "Brier":float(brier_score_loss(y_test,prediction))})
        candidates=[s for s in scores if s["Stage"]=="Validation" and s["Model"]!="Historical win rate"]
        selected=min(candidates,key=lambda s:s["Brier"])["Model"]
        close=close_candidates()[selected]
        final_x,final_y,_=read_dataset("offer_close/final_fit.csv")
        close.fit(final_x,final_y)
        older_x,older_y,_=read_dataset("demand/train.csv")
        later_x,later_y,_=read_dataset("demand/test.csv")
        arrival=pipeline(PoissonRegressor(alpha=.08,max_iter=1000))
        arrival.fit(older_x,older_y)
        predicted=arrival.predict(later_x)
        prior=float(np.mean(older_y))
        arrival_report={"train_face_days":len(older_x),"test_face_days":len(later_x),
            "poisson_deviance":float(mean_poisson_deviance(later_y,predicted)),
            "baseline_deviance":float(mean_poisson_deviance(later_y,[prior]*len(later_y))),
            "brier":float(brier_score_loss(np.array(later_y)>0,1-np.exp(-predicted)))}
        all_x,all_y,_=read_dataset("demand/final_fit.csv")
        arrival.fit(all_x,all_y)
        price_x,price_y,_=read_dataset("achieved_rate/train.csv")
        price=pipeline(Ridge(alpha=10))
        price.fit(price_x,price_y)
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
        (ROOT / "reports").mkdir(exist_ok=True)
        (ROOT / "reports" / "evaluation.json").write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))


if __name__=="__main__":
    train()

