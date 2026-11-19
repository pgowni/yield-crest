"""Run python yieldcrest_model.py beside yieldcrest_step2.sqlite."""
import argparse
import itertools
import sqlite3
from pathlib import Path

DATABASE = Path(__file__).with_name("yieldcrest_step2.sqlite")


def allocations(db, hold_days=None, close_probability=None):
    """Rank the single-face requests in the shared campaign window."""
    requests = db.execute(
        "SELECT id, client, hold_days, close_probability, net_rupees, start_day, duration_days "
        "FROM requests ORDER BY id"
    ).fetchall()
    if len({row[5:] for row in requests}) != 1:
        raise ValueError("This milestone supports one shared campaign window.")
    faces = dict(db.execute("SELECT id, name FROM faces JOIN case_faces ON face_id=id"))
    choices = []
    gains = []
    for request_id, client, hold, probability, rent, start, duration in requests:
        if client == "Agency":
            hold = hold if hold_days is None else hold_days
            probability = probability if close_probability is None else close_probability
        if not (0 <= hold <= start and 0 <= probability <= 1):
            raise ValueError("Check hold length and close probability.")
        eligible = db.execute("SELECT face_id FROM eligible_faces WHERE request_id=?", (request_id,))
        choices.append([None] + [face for face, in eligible])
        gains.append((hold, probability, rent))

    def fallback(face, release):
        result, = db.execute(
            "SELECT AVG(CASE WHEN arrival_day >= ? THEN booked_days * net_daily_rupees "
            "ELSE 0 END) FROM vacancy_episodes WHERE face_id=?", (release, face)
        ).fetchone()
        if result is None:
            raise ValueError(f"No comparable history for {faces[face]}")
        return result

    results = []
    for assignment in itertools.product(*choices):
        used = [face for face in assignment if face is not None]
        if len(used) != len(set(used)):
            continue
        value = sum(fallback(face, 0) for face in faces if face not in used)
        for face, (hold, probability, rent) in zip(assignment, gains):
            if face is not None:
                value += probability * rent + (1 - probability) * fallback(face, hold)
        labels = tuple((row[1], faces.get(face, "Decline")) for row, face in zip(requests, assignment))
        results.append((value, labels))
    return sorted(results, key=lambda row: row[0], reverse=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hold-days", type=int)
    parser.add_argument("--close-prob", type=float)
    args = parser.parse_args()
    with sqlite3.connect(DATABASE.as_uri() + "?mode=ro", uri=True) as db:
        for value, labels in allocations(db, args.hold_days, args.close_prob):
            print(f"₹{value:,.0f}", dict(labels))
