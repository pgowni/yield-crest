"""Operational inputs for partner policies and maintenance planning."""
from datetime import date, timedelta


def service_windows(db, job_id):
    job = db.execute(
        "SELECT face_id, earliest_start, latest_finish, duration_days "
        "FROM maintenance_jobs WHERE id=?", (job_id,)
    ).fetchone()
    face, earliest, latest, duration = job
    first, last = date.fromisoformat(earliest), date.fromisoformat(latest)
    windows = []
    start = first
    while start + timedelta(days=duration-1) <= last:
        end = start + timedelta(days=duration-1)
        conflicts = db.execute(
            "SELECT client FROM bookings WHERE face_id=? "
            "AND start_date<=? AND end_date>=?",
            (face, end.isoformat(), start.isoformat()),
        ).fetchall()
        windows.append({"Start": start.isoformat(), "Finish": end.isoformat(),
                        "Booking conflicts": ", ".join(c for c, in conflicts) or "None"})
        start += timedelta(days=1)
    return windows
