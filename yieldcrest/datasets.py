"""Reproducible feature snapshots and the chronological splits used in training."""
import csv
import hashlib
import json
import math

from yieldcrest.domain import AS_OF, ROOT, connect, days
from yieldcrest.forecasting import close_records, daily_records, season

SPLITS = ROOT / "data" / "splits"
CLOSE_FEATURES = ["face", "daily_rate_relative_to_site", "duration_days",
                  "lead_days", "festive_campaign", "prior_completed_bookings"]
ARRIVAL_FEATURES = ["face", "festive_sales_period", "month_sin", "month_cos"]
PRICE_FEATURES = ["face", "duration_days", "festive_campaign"]


def write_dataset(relative, rows, features, target, purpose, metadata):
    path = SPLITS / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"Empty dataset: {relative}")
    fields = list(rows[0])
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    metadata[relative] = {
        "rows": len(rows), "features": features, "target": target, "purpose": purpose,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def export_datasets():
    manifest = {}
    with connect() as db:
        offers = close_records(db)
        offer_rows = [{
            "offer_id": r["id"], "enquiry_id": r["enquiry_id"], "client_id": r["client_id"],
            "quoted": r["quoted"], "decided": r["decided"],
            "requested_start": r["requested_start"], "requested_end": r["requested_end"],
            **r["features"], "won": int(r["outcome"] == "Won"),
        } for r in offers]
        for folder, cutoff, end, test_name in [
            ("offer_close/validation", "2025-07-01", "2025-11-01", "validation.csv"),
            ("offer_close", "2026-03-01", "2026-08-01", "test.csv"),
        ]:
            train = [r for r in offer_rows if r["quoted"] < cutoff and r["decided"] < cutoff]
            test = [r for r in offer_rows if cutoff <= r["quoted"] < end]
            write_dataset(folder+"/train.csv", train, CLOSE_FEATURES, "won",
                          f"Quotes and known outcomes before {cutoff}", manifest)
            write_dataset(folder+"/"+test_name, test, CLOSE_FEATURES, "won",
                          f"Quotes from {cutoff} inclusive to {end} exclusive", manifest)
        write_dataset("offer_close/final_fit.csv", offer_rows, CLOSE_FEATURES, "won",
                      "Final deployed fit after evaluation; includes all eligible known outcomes before the snapshot", manifest)

        daily = [{"date": day, **features, "enquiry_count": count}
                 for day, face, features, count in daily_records(db, AS_OF)]
        write_dataset("demand/train.csv", [r for r in daily if r["date"] < "2026-03-01"],
                      ARRIVAL_FEATURES, "enquiry_count", "Dates before 2026-03-01, including zero-count face-days", manifest)
        write_dataset("demand/test.csv", [r for r in daily if r["date"] >= "2026-03-01"],
                      ARRIVAL_FEATURES, "enquiry_count", "Dates from 2026-03-01 through 2026-11-18", manifest)
        write_dataset("demand/final_fit.csv", daily, ARRIVAL_FEATURES, "enquiry_count",
                      "Final deployed fit on all face-days before the snapshot", manifest)
        for cutoff in ["2025-07-01", "2026-03-01", "2026-08-01"]:
            write_dataset(f"demand/replay/{cutoff}/train.csv", [r for r in daily if r["date"] < cutoff],
                          ARRIVAL_FEATURES, "enquiry_count", "Training input for T−30/T−14/T−7 replay", manifest)
            # One 30-day test file supports all three horizons by date filtering.
            from datetime import date, timedelta
            end = (date.fromisoformat(cutoff) + timedelta(days=30)).isoformat()
            write_dataset(f"demand/replay/{cutoff}/test.csv",
                          [r for r in daily if cutoff <= r["date"] < end],
                          ARRIVAL_FEATURES, "enquiry_count", "First 7, 14 or 30 days selected for the corresponding replay horizon", manifest)
        prices = [{
            "offer_id": r["id"], "quoted": r["quoted"], "decided": r["decided"],
            "face": str(r["face_id"]),
            "duration_days": float(days(r["requested_start"], r["requested_end"])),
            "festive_campaign": float(season(db, r["requested_start"], r["requested_end"])),
            "log_daily_rate": math.log(r["gross"]/days(r["requested_start"], r["requested_end"])),
        } for r in offers if r["outcome"] == "Won"]
        write_dataset("achieved_rate/train.csv", prices, PRICE_FEATURES, "log_daily_rate",
                      "All eligible accepted rates. This adjustment model previously had no held-out test; none is fabricated here.", manifest)

    payload = {
        "snapshot": AS_OF.isoformat(),
        "source_database_sha256": hashlib.sha256((ROOT/"data/yieldcrest.sqlite").read_bytes()).hexdigest(),
        "synthetic": True,
        "notes": [
            "IDs, dates and outcome metadata are exported for audit; only the listed feature columns enter the estimators.",
            "Training labels must be known before a chronological cutoff.",
            "Validation and final-test training windows intentionally overlap because training expands over time.",
            "Final-fit snapshots include evaluated rows after scoring and are never used to report held-out performance.",
            "Achieved-rate adjustment has training data only; no test score was previously calculated.",
        ],
        "datasets": manifest,
    }
    (SPLITS/"manifest.json").write_text(json.dumps(payload, indent=2)+"\n")
    return payload


def read_dataset(relative):
    manifest = json.loads((SPLITS/"manifest.json").read_text())["datasets"][relative]
    path = SPLITS / relative
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["sha256"]:
        raise ValueError(f"Dataset checksum mismatch: {relative}. Run the exporter intentionally before retraining.")
    with path.open(newline="") as handle:
        records = list(csv.DictReader(handle))
    features = [{f: r[f] if f == "face" else float(r[f]) for f in manifest["features"]} for r in records]
    targets = [float(r[manifest["target"]]) for r in records]
    return features, targets, records
