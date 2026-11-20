from datetime import date, timedelta
from pathlib import Path
import json

import pandas as pd
import streamlit as st

from yieldcrest.domain import AS_OF,HORIZON_END,ROOT,connect,days,overlaps
from yieldcrest.decision_engine import live_requests,existing_blocks,clear,payment_profile,future_values
from yieldcrest.ui.layout import header,navigate,navigation,occupancy

PAGES=["Overview","Inventory","Enquiries","Decisions","Operations"]
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
        result.append({"ID":face["id"],"Board":f"YC-{face["id"]:03d}","Location":face["name"],"Zone":face["zone"],"Format":face["format"],
                       "Available from":str(opening),"Next campaign":next_start or "—",
                       "Base daily rent":face["base_daily"],"Electricity / day":face["electricity_daily"]})
    return result


def render():
    header()
    st.session_state.setdefault("page","Overview")
    if st.session_state.page not in PAGES:
        st.session_state.page="Overview"
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
            metric_help={'Sites available': 'Boards free on the demo planning date, out of all boards in the portfolio.', 'Opening within 7 days': 'Currently occupied boards whose next availability begins within seven days of the planning date.', 'Requests for review': 'Current client enquiries available for evaluation. These are not confirmed bookings.', 'Proposed service jobs': 'Maintenance tasks marked as proposed in the database.', 'November booked gross rent': 'Confirmed campaign rent allocated to November display days, before commission and operating costs. This is not cash collected.', 'Forecast additional net · through Dec 31': 'Estimated additional contribution from future bookings on open dates through December 31, after modeled costs. Excludes rent from existing confirmed bookings; synthetic forecast.', 'Overdue invoice balance': 'Unpaid invoice balance past its due date on the planning date. This is a collections measure.', 'Break-even proposed price': 'Proposed gross price at which accepting and preserving the dates have equal expected contribution, under the selected cost settings.', 'Expected advantage of accepting': 'Expected net contribution with this firm offer minus expected contribution from keeping the dates available. Positive favors accepting; negative favors waiting.', 'Chance of no future booking if waiting': 'Share of simulated futures with no additional booking through the planning horizon if these dates remain open. This is not the current client’s close probability.', 'Expected portfolio net': 'Expected contribution from the evaluated boards and requests, including possible future bookings, modeled costs and any selected service expense. Not total company revenue.', 'Partner-policy trade-off': 'Expected contribution given up versus the financially best plan to honor the partner priority tolerance. Zero means the policy adds no expected loss.', 'Hold resolves': 'Date when uncertain offers resolve. Failed offers release their reserved dates afterward. Close chances stay fixed when hold length changes.', 'Lowest-loss feasible start': 'Feasible maintenance start date expected to displace the least future rental contribution, respecting existing bookings and the service deadline.', 'Expected rental displaced': 'Expected future rental contribution lost because maintenance blocks availability. A short block can prevent a longer consecutive campaign.', 'Service expense': 'Direct cost of the selected maintenance job, separate from rental contribution displaced.', 'Expected net after service expense': 'Expected portfolio contribution for this maintenance scenario after deducting the direct service cost.'}
            metric_help.update({"Sites available":"Boards available on the demonstration date, out of all boards in the portfolio.","Opening within 7 days":"Currently occupied boards that become available within the next seven days. Excludes boards already free.","Requests for review":"Current enquiries awaiting evaluation. These are not confirmed bookings.","Proposed service jobs":"Maintenance jobs marked as proposed in the database. These are not scheduled commitments."})
            for col,(label,value) in zip(cols,values):
                col.metric(label,value, help=metric_help[label])
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
            a.metric("November booked gross rent",money(booked), help='Confirmed campaign rent allocated to November display days, before commission and operating costs. This is not cash collected.')
            b.metric("Forecast additional net · through Dec 31",money(portfolio_forecast()), help='Estimated additional contribution from future bookings on open dates through December 31, after modeled costs. Excludes rent from existing confirmed bookings; synthetic forecast.')
            c.metric("Overdue invoice balance",money(due), help='Unpaid invoice balance past its due date on the planning date. This is a collections measure.')
            st.caption("Booked rent is prorated to November display dates. Forecast is additional net contribution from currently open dates; invoice balances measure collections.")
            occupancy(len(sites),available)
            st.subheader("Upcoming availability")
            st.dataframe(pd.DataFrame(sorted(sites,key=lambda r:r["Available from"]))[["Location","Available from","Next campaign"]].head(6),hide_index=True,use_container_width=True)
            st.button("Explore inventory →",on_click=navigate,args=("Inventory",))
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
                matches.append({"Board":site["Board"],"Location":site["Location"],"Format":site["Format"],"Free for entire campaign":match,
                                "Client-confirmed":f in req["faces"]})
            st.dataframe(matches,hide_index=True,use_container_width=True)
            st.caption("A free site can be suggested, but allocation uses only locations the client confirmed for this request.")
            if any(not row["Free for entire campaign"] and row["Client-confirmed"] for row in matches):
                if st.button("Show available alternative boards",key=f"alternatives_{selected}"):
                    alternatives=[{"Board":row["Board"],"Location":row["Location"],"Format":row["Format"],
                                   "Client approval":"Already confirmed" if row["Client-confirmed"] else "Needs client approval"}
                                  for row in matches if row["Free for entire campaign"]]
                    if alternatives:
                        st.dataframe(alternatives,hide_index=True,use_container_width=True)
                        st.info("These boards are free for the full requested dates. Confirm the format, location and price with the client before substituting. No booking has been moved.")
                    else:
                        st.info("No board is free for the entire requested campaign. Dates or campaign requirements need to change.")
            def open_decision():
                st.session_state.decision_request=selected
                navigate("Decisions")
            st.button("Evaluate this request →",on_click=open_decision)
            profile=payment_profile(db,req["client_id"])
            st.write(f"Past settled invoices {profile['settled_invoices']} · Average invoice-to-payment {profile['mean_days_to_pay'] or 'unknown'} days · Overdue {money(profile['overdue_rupees'])}")
            with st.expander("Connected sales history"):
                st.dataframe([dict(r) for r in db.execute("""
                    SELECT e.id AS "Enquiry ID",c.name AS Client,f.name AS Location,e.received AS "Enquiry received",
                           e.requested_start AS "Requested start",e.requested_end AS "Requested end",
                           o.gross AS "Proposed price (₹)",o.outcome AS "Offer outcome",b.confirmed AS "Booking confirmed",
                           i.issued AS "Invoice issued",i.due AS "Payment due",r.paid AS "Payment received"
                    FROM enquiries e JOIN clients c ON c.id=e.client_id JOIN faces f ON f.id=e.face_id
                    JOIN offers o ON o.enquiry_id=e.id LEFT JOIN bookings b ON b.offer_id=o.id
                    LEFT JOIN invoices i ON i.booking_id=b.id LEFT JOIN receipts r ON r.invoice_id=i.id
                    ORDER BY e.received DESC LIMIT 300
                """)],hide_index=True,use_container_width=True)
        elif section=="Decisions":
            from yieldcrest.ui.decisions import render as decisions
            decisions()
        elif section=="Operations":
            from yieldcrest.ui.operations import render as operations
            operations()


