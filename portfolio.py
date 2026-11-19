from datetime import date, timedelta

AS_OF = date(2026, 11, 19)


def inventory(db):
    rows = []
    for face, name in db.execute("SELECT id, name FROM faces ORDER BY name"):
        available = AS_OF
        next_start = None
        for start, end in db.execute(
            "SELECT start_date, end_date FROM bookings WHERE face_id=? AND end_date>=? ORDER BY start_date",
            (face, AS_OF.isoformat()),
        ):
            if date.fromisoformat(start) > available:
                next_start = start
                break
            available = max(available, date.fromisoformat(end) + timedelta(days=1))
        rows.append({"Location": name, "Available from": available, "Next booking": next_start or "—"})
    return rows
