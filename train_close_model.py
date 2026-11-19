"""Offline comparison on synthetic offers. Requires scikit-learn (tested with 1.8.0)."""
import sqlite3
from pathlib import Path

from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def compare(db):
    rows = db.execute("""
        SELECT o.quoted, o.decided, o.outcome='Won',
               o.rupees/(1+julianday(e.requested_end)-julianday(e.requested_start)),
               1+julianday(e.requested_end)-julianday(e.requested_start),
               julianday(e.requested_start)-julianday(o.quoted),
               EXISTS(SELECT 1 FROM seasonal_periods s WHERE
                   s.start_date<=e.requested_end AND s.end_date>=e.requested_start),
               (SELECT count(*) FROM bookings b JOIN offers past ON past.id=b.offer_id
                JOIN enquiries pe ON pe.id=past.enquiry_id WHERE pe.client_id=e.client_id
                AND b.end_date<o.quoted AND past.decided<o.quoted)
        FROM offers o JOIN enquiries e ON e.id=o.enquiry_id
        WHERE o.outcome IN ('Won','Lost') ORDER BY o.quoted,o.id
    """).fetchall()
    cutoff = rows[int(len(rows)*0.8)][0]
    train = [r for r in rows if r[1] < cutoff and r[0] < cutoff]
    test = [r for r in rows if r[0] >= cutoff]
    print(f"Test starts {cutoff}: {len(train)} train, {len(test)} test, "
          f"{len(rows)-len(train)-len(test)} pending at cutoff")
    for label, model in [
        ("Historical win rate", DummyClassifier(strategy="prior")),
        ("Logistic regression", make_pipeline(StandardScaler(), LogisticRegression())),
        ("Shallow random forest", RandomForestClassifier(n_estimators=200, max_depth=3,
                                                       min_samples_leaf=12, random_state=42)),
    ]:
        model.fit([r[3:] for r in train], [r[2] for r in train])
        predictions = model.predict_proba([r[3:] for r in test])[:, 1]
        print(label, round(brier_score_loss([r[2] for r in test], predictions), 4))


if __name__ == "__main__":
    with sqlite3.connect(Path(__file__).with_name("yieldcrest_step2.sqlite").as_uri() + "?mode=ro", uri=True) as db:
        compare(db)
