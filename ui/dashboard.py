from contextlib import closing
import sqlite3
from portfolio import AS_OF, inventory

import streamlit as st

from yieldcrest_model import DATABASE, allocations


from ui.layout import header, navigate, navigation, occupancy

def render():
    header()
    st.session_state.setdefault("page", "Overview")
    section = navigation(["Overview", "Inventory", "Enquiries", "Booking decisions"])
    with closing(sqlite3.connect(DATABASE.as_uri() + "?mode=ro", uri=True)) as db:
        sites = inventory(db)
        enquiries = [dict(zip(("Client", "Location", "Received", "From", "Through"), row)) for row in db.execute(
            "SELECT client, name, received, requested_start, requested_end FROM enquiries "
            "JOIN faces ON faces.id=enquiries.face_id WHERE status='Open' ORDER BY received DESC"
        )]
    free = [row for row in sites if row["Available from"] == AS_OF]
    upcoming = sorted((row for row in sites if row["Available from"] > AS_OF), key=lambda row: row["Available from"])

    with closing(sqlite3.connect(DATABASE.as_uri() + "?mode=ro", uri=True)) as db:
        conflicts = db.execute("""
            SELECT count(*) FROM enquiries e WHERE status='Open' AND EXISTS (
                SELECT 1 FROM bookings b WHERE b.face_id=e.face_id
                AND b.start_date<=e.requested_end AND b.end_date>=e.requested_start)
        """).fetchone()[0]
        baseline = allocations(db)[0][0]
    st.title("Portfolio overview" if section == "Overview" else section)
    st.caption(f"{AS_OF:%d %B %Y}  ·  Synthetic portfolio")
    if section == "Overview":
        metrics = [("Portfolio sites", len(sites)), ("Available today", len(free)),
                   ("Opening in 7 days", sum((r["Available from"]-AS_OF).days <= 7 for r in upcoming)),
                   ("Open enquiries", len(enquiries))]
        for col, (label, value) in zip(st.columns(4), metrics):
            col.metric(label, value)
        occupancy(len(sites), len(free))
        left, right = st.columns([1.25, 1])
        with left:
            st.subheader("Next vacancies")
            st.dataframe(upcoming[:4], hide_index=True, use_container_width=True)
            st.button("Explore inventory →", on_click=navigate, args=("Inventory",))
        with right:
            st.subheader("Enquiries needing attention")
            st.write(f"**{conflicts} of {len(enquiries)} requests** overlap a confirmed booking at the requested location.")
            st.button("Review enquiries →", on_click=navigate, args=("Enquiries",))
        st.html(f'<div class="yc-panel">Booking decision · Five Hyderabad locations<strong>₹{baseline:,.0f}</strong><small>Highest expected net contribution at the default agency hold and close probability</small></div>')
        st.button("Compare booking options →", on_click=navigate, args=("Booking decisions",))
    elif section == "Inventory":
        available, opening = st.tabs(["Available now", "Upcoming vacancies"])
        available.dataframe(free, hide_index=True, use_container_width=True)
        opening.dataframe(upcoming, hide_index=True, use_container_width=True)
    elif section == "Enquiries":
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
                    st.info(f"{site} overlaps with {client}'s booking from {start_date} through {end_date}.")
            else:
                st.info(f"{selected['Location']} is available for the entire campaign.")
            alternatives = [name for name, client, _, _ in matches if client is None and name != selected["Location"]]
            st.write("Other sites available for all requested dates")
            st.write(", ".join(alternatives) or "None")
            st.caption("Confirm location flexibility with the client before offering an alternative.")
        st.dataframe(enquiries, hide_index=True, use_container_width=True)
    else:
        with closing(sqlite3.connect(DATABASE.as_uri() + "?mode=ro", uri=True)) as db:
            start, duration, hold, probability, rent = db.execute(
                "SELECT start_day, duration_days, hold_days, close_probability, net_rupees "
                "FROM requests WHERE client='Agency'"
            ).fetchone()
            with st.expander("Locations confirmed for each request"):
                st.table([{"Client": c, "Location": f, "Basis": b} for c, f, b in db.execute("SELECT r.client, f.name, e.basis FROM eligible_faces e JOIN requests r ON r.id=e.request_id JOIN faces f ON f.id=e.face_id ORDER BY r.id, f.name")])
            st.write(f"The agency offers ₹{rent:,} for a {duration}-day campaign starting in {start} days.")
            days = st.slider("Agency hold (days)", 0, start, hold)
            chance = st.slider("Agency close probability (%)", 0, 100, round(probability * 100))
            ranked = allocations(db, days, chance / 100)

        best, assignments = ranked[0]
        st.metric("Highest expected net contribution", f"₹{best:,.0f}")
        st.write(" · ".join(f"{client}: {face}" for client, face in assignments))
        st.subheader("Feasible allocations")
        st.table([{**dict(labels), "Expected net": f"₹{value:,.0f}"} for value, labels in ranked])
