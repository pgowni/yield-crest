from contextlib import closing
import sqlite3

import streamlit as st

from operations import service_windows
from yieldcrest_model import DATABASE


def render():
    st.subheader("Partner agreements")
    st.caption("Operator policies and commercial inputs. Blank terms require confirmation.")
    with closing(sqlite3.connect(DATABASE.as_uri() + "?mode=ro", uri=True)) as db:
        cursor = db.execute("""
            SELECT c.name AS Partner, p.priority AS Priority,
                   p.adplay_share_percent AS AdPlay_share_percent,
                   p.contribution_tolerance_rupees AS Priority_tolerance_rupees
            FROM partner_policies p JOIN clients c ON c.id=p.client_id
        """)
        st.table([dict(zip([c[0] for c in cursor.description], row)) for row in cursor])
        st.write("Prakash Ads is recorded as a strategic partner. Confirm the share and the maximum contribution trade-off before applying the policy to allocations.")
        st.subheader("Maintenance planner")
        jobs = db.execute("""
            SELECT j.id,f.name,j.task FROM maintenance_jobs j JOIN faces f ON f.id=j.face_id ORDER BY j.id
        """).fetchall()
        selected = st.selectbox("Service job", jobs, format_func=lambda row: f"{row[1]} · {row[2]}")
        row = db.execute("""
            SELECT earliest_start,latest_finish,duration_days,last_service_date,status
            FROM maintenance_jobs WHERE id=?
        """, (selected[0],)).fetchone()
        start, finish, duration, last, status = row
        st.write(f"Allow {duration} days between {start} and {finish}. Status: {status}.")
        st.caption("Illustrative technician-supplied service windows. These deadlines are scenario inputs. Historical equipment-failure estimates are pending.")
        options = service_windows(db, selected[0])
        available = [w for w in options if w["Booking conflicts"] == "None"]
        st.metric("Windows clear of confirmed bookings", len(available))
        st.dataframe(options, hide_index=True, use_container_width=True)
        st.caption("These are candidate service windows. Expected lost rental contribution still needs the future-demand forecast before a window can be recommended.")
