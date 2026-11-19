from datetime import date, timedelta
from pathlib import Path
import json

import pandas as pd
import streamlit as st

from domain import AS_OF,HORIZON_END,connect,days,overlaps
from decision_engine import live_requests,existing_blocks,clear,payment_profile,future_values
from ui.layout import header,navigate,navigation,occupancy

PAGES=["Overview","Inventory","Enquiries","Decisions","Operations","Evidence"]
money=lambda x:f"₹{x:,.0f}"


@st.cache_data(show_spinner=False)
def portfolio_forecast():
    with connect() as db:
        return sum(float(future_values(db,r[0])[0].mean()) for r in db.execute("SELECT id FROM faces"))


def site_calendar(db):
    result=[]
    for face in db.execute("SELECT * FROM faces ORDER BY name"):
        blocks=existing_blocks(db,face["id"])
        opening=AS_OF
        for start,end in sorted(blocks):
            if start>str(opening):
                break
            opening=max(opening,date.fromisoformat(end)+timedelta(days=1))
        next_start=next((a for a,b in sorted(blocks) if a>str(opening)),None)
        result.append({"ID":face["id"],"Location":face["name"],"Zone":face["zone"],"Format":face["format"],
                       "Available from":str(opening),"Next campaign":next_start or "—",
                       "Base daily rent":face["base_daily"],"Electricity / day":face["electricity_daily"]})
    return result


def render():
    header()
    st.session_state.setdefault("page","Overview")
    section=navigation(PAGES)
    st.title("Portfolio overview" if section=="Overview" else section)
    st.caption("19 November 2026 · Synthetic demonstration · Planning through 31 December")
    with connect() as db:
        sites=site_calendar(db)
        requests=live_requests(db)
        available=sum(r["Available from"]==str(AS_OF) for r in sites)
        if section=="Overview":
            cols=st.columns(4)
            values=[("Sites available",f"{available} / {len(sites)}"),
                    ("Opening within 7 days",sum(str(AS_OF)<r["Available from"]<=str(AS_OF+timedelta(days=7)) for r in sites)),
                    ("Requests for review",len(requests)),
                    ("Proposed service jobs",db.execute("SELECT count(*) FROM maintenance_jobs WHERE status='Proposed'").fetchone()[0])]
            for col,(label,value) in zip(cols,values):
                col.metric(label,value)
            month_start="2026-11-01";month_end="2026-11-30"
            booked=0.
            for row in db.execute("""
                SELECT b.start_date,b.end_date,o.gross FROM bookings b JOIN offers o ON o.id=b.offer_id
                WHERE b.confirmed<=? AND b.start_date<=? AND b.end_date>=?
            """,(str(AS_OF),month_end,month_start)):
                overlap=days(max(row[0],month_start),min(row[1],month_end))
                booked+=row[2]*overlap/days(row[0],row[1])
            due=sum(payment_profile(db,c[0])["overdue_rupees"] for c in db.execute("SELECT id FROM clients"))
            a,b,c=st.columns(3)
            a.metric("November booked gross rent",money(booked))
            b.metric("Forecast additional net · through Dec 31",money(portfolio_forecast()))
            c.metric("Overdue invoice balance",money(due))
            st.caption("Booked rent is prorated to November display dates. Forecast is additional net contribution from currently open dates; invoice balances measure collections.")
            occupancy(len(sites),available)
            left,right=st.columns([1.2,1])
            with left:
                st.subheader("Upcoming availability")
                st.dataframe(pd.DataFrame(sorted(sites,key=lambda r:r["Available from"]))[["Location","Available from","Next campaign"]].head(6),hide_index=True,use_container_width=True)
                st.button("Explore inventory →",on_click=navigate,args=("Inventory",))
            with right:
                st.subheader("Protect the festive window")
                st.write("Compare a campaign that crosses 5 December with the same campaign moved five days earlier. Inspect the break-even price and the risk of earning nothing.")
                st.button("Compare campaign dates →",on_click=navigate,args=("Decisions",))
                st.subheader("Prakash and maintenance")
                st.write("See the expected contribution traded for partner priority and which service window displaces the least rental value.")
                st.button("Review operations →",on_click=navigate,args=("Operations",))
        elif section=="Inventory":
            zone=st.selectbox("Zone",["All"]+sorted({r["Zone"] for r in sites}))
            view=[r for r in sites if zone=="All" or r["Zone"]==zone]
            st.dataframe(view,hide_index=True,use_container_width=True)
            selected=st.selectbox("Inspect a board",[r["ID"] for r in sites],format_func=lambda f:next(r["Location"] for r in sites if r["ID"]==f))
            bookings=[dict(r) for r in db.execute("""
                SELECT c.name AS Client,b.start_date AS Starts,b.end_date AS Ends,o.gross AS Gross_rent
                FROM bookings b JOIN offers o ON o.id=b.offer_id JOIN enquiries e ON e.id=o.enquiry_id
                JOIN clients c ON c.id=e.client_id WHERE b.face_id=? AND b.end_date>=? ORDER BY b.start_date
            """,(selected,str(AS_OF)))]
            st.subheader("Confirmed campaigns")
            st.dataframe(bookings,hide_index=True,use_container_width=True)
        elif section=="Enquiries":
            selected=st.selectbox("Request",[r["id"] for r in requests],
                                  format_func=lambda i:next(r["label"] for r in requests if r["id"]==i),key="enquiry_request")
            req=next(r for r in requests if r["id"]==selected)
            st.write(f"**{req['start_date']} to {req['end_date']}** · Gross rent {money(req['gross'])} · {req['kind']}")
            matches=[]
            for site in sites:
                f=site["ID"]
                match=clear(req["start_date"],req["end_date"],existing_blocks(db,f))
                matches.append({"Location":site["Location"],"Free for entire campaign":match,
                                "Client-confirmed":f in req["faces"]})
            st.dataframe(matches,hide_index=True,use_container_width=True)
            st.caption("A free site can be suggested, but allocation uses only locations the client confirmed for this request.")
            def open_decision():
                st.session_state.decision_request=selected
                navigate("Decisions")
            st.button("Evaluate this request →",on_click=open_decision)
            profile=payment_profile(db,req["client_id"])
            st.write(f"Past settled invoices {profile['settled_invoices']} · Average invoice-to-payment {profile['mean_days_to_pay'] or 'unknown'} days · Overdue {money(profile['overdue_rupees'])}")
            with st.expander("Connected sales history"):
                st.dataframe([dict(r) for r in db.execute("""
                    SELECT e.id,c.name AS Client,f.name AS Site,e.received,e.requested_start,e.requested_end,
                           o.gross,o.outcome,b.confirmed,i.issued,i.due,r.paid
                    FROM enquiries e JOIN clients c ON c.id=e.client_id JOIN faces f ON f.id=e.face_id
                    JOIN offers o ON o.enquiry_id=e.id LEFT JOIN bookings b ON b.offer_id=o.id
                    LEFT JOIN invoices i ON i.booking_id=b.id LEFT JOIN receipts r ON r.invoice_id=i.id
                    ORDER BY e.received DESC LIMIT 300
                """)],hide_index=True,use_container_width=True)
        elif section=="Decisions":
            from ui.decisions import render as decisions
            decisions()
        elif section=="Operations":
            from ui.operations import render as operations
            operations()
        else:
            st.subheader("What the models learned")
            report=json.loads(Path(__file__).parents[1].joinpath("models/evaluation.json").read_text())
            st.caption("Synthetic replay checks implementation and chronology. These scores establish no real-world forecast accuracy or revenue uplift.")
            st.write(f"Offer classifier selected on validation: **{report['close_selected_on_validation']}**")
            st.dataframe(report["offer_metrics"],hide_index=True,use_container_width=True)
            st.info("The selected classifier underperformed the historical win-rate baseline on the later test period. Its live probabilities are experimental and editable.")
            st.write("Lower Brier score is better. Training outcomes must be known before the split date; prior-client counts use only bookings completed before the quote.")
            st.subheader("Future enquiry arrivals")
            st.json(report["arrival_metrics"])
            replay=Path(__file__).parents[1].joinpath("models/replay.json")
            if replay.exists():
                st.subheader("T−30, T−14 and T−7 replay")
                st.dataframe(json.loads(replay.read_text())["replays"],hide_index=True,use_container_width=True)
                st.caption("Counts are correlated across sites and seasons. The replay uses dated enquiry arrivals and discrete Poisson count intervals, not unobservable revenue from rejected alternatives.")
            with st.expander("Dataset and generator assumptions"):
                st.json(json.loads(Path(__file__).parents[1].joinpath("data/generator_parameters.json").read_text()))
                st.table([{"Table":r[0],"Rows":db.execute("SELECT count(*) FROM "+r[0]).fetchone()[0]}
                          for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")])
            for limitation in report["limitations"]:
                st.write("• "+limitation)

    from ui.chat_panel import render as render_chat_panel
    render_chat_panel(section)
