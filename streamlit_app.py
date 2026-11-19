from contextlib import closing
import sqlite3

import streamlit as st

from yieldcrest_model import DATABASE, allocations

st.set_page_config(page_title="YieldCrest · Booking decisions")
st.title("YieldCrest")
st.caption("Hyderabad · Synthetic booking data")
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
