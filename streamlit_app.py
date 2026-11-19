from contextlib import closing
import sqlite3
from portfolio import AS_OF, inventory

import streamlit as st

from yieldcrest_model import DATABASE, allocations

st.set_page_config(page_title="YieldCrest · Booking decisions")
st.title("YieldCrest")
st.caption("Hyderabad · Synthetic booking data")
st.header("Inventory overview")
st.caption("Portfolio as of 19 November 2026")
with closing(sqlite3.connect(DATABASE.as_uri() + "?mode=ro", uri=True)) as db:
    sites = inventory(db)
    enquiries = [dict(zip(("Client", "Location", "Received", "From", "Through"), row)) for row in db.execute(
        "SELECT client, name, received, requested_start, requested_end FROM enquiries "
        "JOIN faces ON faces.id=enquiries.face_id WHERE status='Open' ORDER BY received DESC"
    )]
free = [row for row in sites if row["Available from"] == AS_OF]
upcoming = sorted((row for row in sites if row["Available from"] > AS_OF), key=lambda row: row["Available from"])
a, b, c = st.columns(3)
a.metric("Available today", len(free))
b.metric("Opening in 7 days", sum((row["Available from"] - AS_OF).days <= 7 for row in upcoming))
c.metric("Open enquiries", len(enquiries))
now, soon, leads = st.tabs(["Available sites", "Upcoming vacancies", "Open enquiries"])
now.table(free)
soon.table(upcoming)
with leads:
    if enquiries:
        selected = st.selectbox("Check campaign availability", enquiries, format_func=lambda e: f"{e['Client']} · {e['Location']} · {e['From']} to {e['Through']}")
        with closing(sqlite3.connect(DATABASE.as_uri() + "?mode=ro", uri=True)) as db:
            matches = db.execute("""
                SELECT f.name, b.client, b.start_date, b.end_date
                FROM faces f LEFT JOIN bookings b
                  ON b.face_id=f.id AND b.start_date<=? AND b.end_date>=?
                ORDER BY f.name
            """, (selected["Through"], selected["From"])).fetchall()
        clashes = [row for row in matches if row[0] == selected["Location"] and row[1] is not None]
        if clashes:
            for site, client, start_date, end_date in clashes:
                st.warning(f"{site} overlaps with {client}'s booking from {start_date} through {end_date}.")
        else:
            st.success(f"{selected['Location']} is available for the entire campaign.")
        alternatives = [name for name, client, _, _ in matches if client is None and name != selected["Location"]]
        st.write("Other sites available for all requested dates")
        st.write(", ".join(alternatives) or "None")
        st.caption("Confirm location flexibility with the client before offering an alternative.")
    leads.table(enquiries)
st.divider()
st.header("Compare booking decisions")
with closing(sqlite3.connect(DATABASE.as_uri() + "?mode=ro", uri=True)) as db:
    start, duration, hold, probability, rent = db.execute(
        "SELECT start_day, duration_days, hold_days, close_probability, net_rupees "
        "FROM requests WHERE client='Agency'"
    ).fetchone()
    st.write(f"The agency offers ₹{rent:,} for a {duration}-day campaign starting in {start} days.")
    days = st.slider("Agency hold (days)", 0, start, hold)
    chance = st.slider("Agency close probability (%)", 0, 100, round(probability * 100))
    ranked = allocations(db, days, chance / 100)

best, assignments = ranked[0]
st.metric("Highest expected net contribution", f"₹{best:,.0f}")
st.write(" · ".join(f"{client}: {face}" for client, face in assignments))
st.subheader("Feasible allocations")
st.table([{**dict(labels), "Expected net": f"₹{value:,.0f}"} for value, labels in ranked])
