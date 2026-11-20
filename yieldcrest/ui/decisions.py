from yieldcrest.ui.partner_badge import mark, dataframe, table
from datetime import date

import pandas as pd
import streamlit as st

from yieldcrest.domain import AS_OF, HORIZON_END, connect
from yieldcrest.decision_engine import compare_calendar, joint_allocation, live_requests, maintenance_options, choose_service_allocation

money=lambda value: f"₹{value:,.0f}"


@st.cache_data(show_spinner=False)
def calendar_result(request,face,shift,gross,lit,cash,funding):
    return compare_calendar(request,face,shift,gross,lit,cash,funding)


@st.cache_data(show_spinner=False)
def joint_result(hold,probabilities,tolerance,share,lit,cash,funding,maintenance):
    return joint_allocation(hold,probabilities,tolerance,share,lit,cash,funding,maintenance)


@st.cache_data(show_spinner=False)
def service_result(job,lit,cash,funding):
    return maintenance_options(job,lit,cash,funding)


@st.cache_data(show_spinner=False)
def integrated_service(job,hold,probabilities,tolerance,share,lit,cash,funding):
    return choose_service_allocation(job,hold,probabilities,tolerance,share,lit,cash,funding)



def reset_campaign_inputs():
    """Discard scenario overrides when switching requests or explicitly resetting."""
    st.session_state["campaign_revision"]=st.session_state.get("campaign_revision",0)+1
    for key in list(st.session_state):
        if key.startswith(("gross_", "shift_", "face_")):
            del st.session_state[key]
    st.session_state.pop("latest_context", None)
    st.session_state.pop("yc_explanations", None)


def render():
    from datetime import timedelta
    from yieldcrest.decision_engine import connected_requests
    from yieldcrest.forecasting import close_probability
    settings={"lit":True,"cash":False,"funding":.12}
    with connect() as db:
        requests=live_requests(db)
        names={r["id"]:f"YC-{r['id']:03d} · {r['name']} · {r['format']}" for r in db.execute("SELECT id,name,format FROM faces")}
    st.subheader("Review a campaign and its competing opportunities")
    rid=st.selectbox("Campaign",[r["id"] for r in requests],format_func=lambda i:mark(next(r["label"] for r in requests if r["id"]==i)),key="decision_request",on_change=reset_campaign_inputs)
    req=next(r for r in requests if r["id"]==rid)
    st.button("Reset campaign scenario",on_click=reset_campaign_inputs)
    revision=st.session_state.get("campaign_revision",0)
    price_key=f"campaign_price_v3_{rid}_{revision}"
    st.session_state.setdefault(price_key,int(req["gross"]))
    a,b,c=st.columns(3)
    face=a.selectbox("Client-approved board",req["faces"],format_func=lambda f:mark(names[f]),key=f"face_{rid}")
    gross=b.number_input("Proposed price (₹)",min_value=0,max_value=1000000,step=1000,key=price_key)
    original_start=date.fromisoformat(req["start_date"])
    duration=(date.fromisoformat(req["end_date"])-original_start).days+1
    latest_start=HORIZON_END-timedelta(days=duration-1)
    start=c.date_input("Campaign start date",value=original_start,min_value=AS_OF,max_value=latest_start,
                       key=f"campaign_start_{rid}_{revision}",
                       help="Choose the proposed start date. The campaign keeps its original duration; availability, competing requests and maintenance are recalculated.")
    shift=(start-original_start).days
    c.caption(f"Ends {(start+timedelta(days=duration-1)):%d %b %Y} · {duration} days")
    try:
        firm=calendar_result(rid,face,shift,gross,**settings)
    except ValueError as error:
        st.warning(mark(str(error)));return
    scoped=[dict(r) for r in requests]
    target=next(r for r in scoped if r["id"]==rid)
    target.update({k:firm["request"][k] for k in ["start_date","end_date","gross"]});target["faces"]=[face]
    relevant=connected_requests(scoped,rid)
    ids={r["id"] for r in relevant}
    st.markdown(mark("### Requests affecting this decision"))
    st.caption(mark(f"Selected campaign: {firm['request']['start_date']} to {firm['request']['end_date']} on {names[face]}. Only requests connected through overlapping dates and approved boards enter this comparison."))
    probabilities={};holds={};rows=[]
    with connect() as db:
        for r in relevant:
            direct=r["id"]!=rid and face in r["faces"] and not (r["end_date"]<target["start_date"] or r["start_date"]>target["end_date"])
            reason="Selected campaign" if r["id"]==rid else "Direct competitor · same board and overlapping dates" if direct else "Connected competitor · shares an alternative board with another competing request"
            rows.append({"Client":r["client"],"Campaign dates":r["start_date"]+" to "+r["end_date"],"Why included":reason})
        dataframe(rows,hide_index=True,use_container_width=True)
        for r in relevant:
            with st.container(border=True):
                st.markdown(mark(f"**{r['client']}** · "+("Selected campaign" if r["id"]==rid else "Competing request")))
                booking_start=date.fromisoformat(r["start_date"])
                booking_end=date.fromisoformat(r["end_date"])
                start_col,end_col,price_col,count_col=st.columns(4)
                start_col.markdown(f"**Booking starts**\n\n{booking_start:%d %b %Y}")
                end_col.markdown(f"**Booking ends**\n\n{booking_end:%d %b %Y}")
                price_col.markdown(f"**Proposed price**\n\n{money(r['gross'])}")
                count_col.markdown(f"**Boards required**\n\n{r['quantity']}")
                st.caption(f"Request {r['id']} · {r['kind']} · {(booking_end-booking_start).days+1} display days")
                left,right=st.columns(2)
                learned=close_probability(db,r,r["faces"][0])
                probabilities[str(r["id"])]=left.slider("Chance of confirmation (%)",0,100,round(learned*100),key=f"close_{rid}_{r['id']}_{revision}",help="Experimental model estimate; adjust using your knowledge of this client. Changing the deadline does not automatically change this probability.")/100
                last=min(AS_OF+timedelta(days=5),date.fromisoformat(r["expires"]),date.fromisoformat(r["start_date"]))
                deadline=right.date_input("Reserve until",value=min(AS_OF+timedelta(days=3),last),min_value=AS_OF,max_value=last,key=f"reserve_{rid}_{r['id']}_{revision}",help="If this request is selected, reserve its assigned board until this date. If it fails to confirm, the board is released for subsequent enquiries.")
                holds[str(r["id"])]=(deadline-AS_OF).days
                with st.expander(f"Approved boards ({len(r['faces'])})"):
                    for approved_face in r["faces"]:
                        st.write(names[approved_face])
    excluded=[r["client"] for r in requests if r["id"] not in ids]
    if excluded:st.caption(mark("Outside this comparison: "+", ".join(excluded)+" — no connected date-and-board conflict."))
    with st.expander(mark("Strategic partner policy")):
        a,b=st.columns(2)
        tolerance=a.number_input("Meridian Ads [SP] priority tolerance (₹)",0,100000,5000,step=1000)
        share=b.number_input("AdPlay share of Meridian Ads [SP] bill (%)",1.,100.,80.,step=1.)/100
    with st.spinner("Comparing this campaign with connected requests and future demand…"):
        result=campaign_result(rid,face,shift,gross,probabilities,holds,tolerance,share)
    including=result["best_including"][str(rid)]
    excluding=result["best_excluding"][str(rid)]
    recommended=result["recommended"]
    chosen=next(a for a in recommended["assignments"] if a["request_id"]==rid)
    st.subheader("Campaign decision")
    if chosen["sites"]:st.success(mark(f"Proposed plan includes {req['client']} on "+", ".join(chosen["sites"])+"."))
    else:st.info(mark(f"Proposed plan leaves out {req['client']} and preserves its dates for competing requests or future business."))
    st.markdown(mark("**Maintenance included in this decision**"))
    schedule=recommended.get("maintenance_schedule",[])
    if schedule:
        dataframe([{"Board":names[j["board_id"]],"Work":j["task"],"Closed from":j["start"],"Closed through":j["end"],"Expense":money(j["cost"])} for j in schedule],hide_index=True,use_container_width=True)
        st.caption(mark(result["maintenance_scope"]))
    else:st.caption(mark("No pending maintenance job overlaps the boards and campaign windows in this comparison."))
    a,b,c=st.columns(3)
    a.metric("Proposed price",money(gross))
    b.metric("Expected advantage of including campaign",money(including["expected"]-excluding["expected"]) if including else "Cannot fit",help="Best expected contribution including this campaign minus the best excluding it. Includes connected competitors, confirmation chances, future demand and maintenance expense.")
    switches=result.get("chance_switches",[])
    threshold="; ".join(f"{x['from']}–{x['to']}%" for x in switches) if switches else ("Cannot fit" if not including else "Always favors inclusion" if all(x["advantage"]>=0 for x in result["chance_sweep"]) else "Never favors inclusion")
    c.metric("Confirmation chance · break-even",threshold,help="Where the financially preferred plan switches in a 1-percentage-point sensitivity sweep. Other probabilities stay fixed. Partner priority can change the recommendation.")
    st.metric("Expected contribution · recommended plan",money(recommended["expected"]),help="Contribution across the same connected boards, including uncertain offers, future business and maintenance expense.")
    comparisons=[]
    for label,plan in [("Include this campaign",including),("Leave this campaign out",excluding)]:
        if plan:
            comparisons.append({"Plan":label,"Expected contribution":money(plan["expected"]),"Lower simulated outcome":money(plan["p10"]),"Upper simulated outcome":money(plan["p90"])})
    dataframe(comparisons,hide_index=True,use_container_width=True)
    if including and excluding:
        st.caption(mark(f"Including this campaign changes expected contribution by {money(including['expected']-excluding['expected'])}. Each row uses its financially best feasible allocation across the same boards; partner priority is applied to the recommended plan above."))
    st.markdown(mark("**Recommended board assignments**"))
    dataframe([{"Client":a["client"],"Board assignment":", ".join(a["sites"]) or "Not selected","Reserve until":result["hold_expiries"][str(a["request_id"]) ] if a["sites"] else "—"} for a in recommended["assignments"]],hide_index=True,use_container_width=True)
    st.caption(mark("These are proposed commitments, not confirmed bookings. Unselected requests are declined in this scenario; they are not assumed to wait for another request to fail."))
    st.markdown(mark("**Expected value of each request in the recommended allocation**"))
    from yieldcrest.decision_engine import request_net
    with connect() as db:
        contribution_rows=[]
        for item in recommended["assignments"]:
            request=dict(next(r for r in relevant if r["id"]==item["request_id"]))
            if request["client_id"]==1:request["share"]=share
            assigned=[f for f in request["faces"] if names[f].split(" · ")[1] in item["sites"]]
            net=sum(request_net(db,request,f)/request["quantity"] for f in assigned)
            contribution_rows.append({"Client":request["client"],"Proposed price":money(request["gross"]),"Chance of confirmation":f"{probabilities[str(request['id'])]:.0%}","Net if confirmed":money(net) if assigned else "Not selected","Expected campaign contribution":money(net*probabilities[str(request['id'])])})
    dataframe(contribution_rows,hide_index=True,use_container_width=True)
    st.caption(mark("Campaign contribution excludes future bookings and maintenance expense, which are included in the plan totals above. Unselected requests contribute zero to this plan."))
    with st.expander(mark("What if this client confirms now?")):
        confirmed_probabilities={**probabilities,str(rid):1.0}
        confirmed_holds={**holds,str(rid):0}
        confirmed=campaign_result(rid,face,shift,gross,confirmed_probabilities,confirmed_holds,tolerance,share)
        accept=confirmed["best_including"][str(rid)]
        wait=confirmed["best_excluding"][str(rid)]
        st.caption(mark("Only this client is set to 100% confirmation with no reservation delay. Competitors retain the probabilities and deadlines above. Maintenance and future demand are recalculated in both plans."))
        if accept:
            st.metric("Expected advantage of accepting now",money(accept["expected"]-wait["expected"]),help="Expected contribution with this campaign confirmed now minus the best plan without it, across the same boards and including maintenance expense.")
            dataframe([{"Plan":label,"Expected contribution":money(plan["expected"]),"Lower simulated outcome":money(plan["p10"]),"Upper simulated outcome":money(plan["p90"])} for label,plan in [("Accept confirmed campaign now",accept),("Leave this campaign out",wait)]],hide_index=True,use_container_width=True)
            st.markdown("**Assignments if accepted now**")
            dataframe([{"Client":item["client"],"Board assignment":", ".join(item["sites"]) or "Not selected"} for item in accept["assignments"]],hide_index=True,use_container_width=True)
        else:
            st.warning("This campaign cannot fit the current board and maintenance constraints, even with confirmation guaranteed.")
    context={"calculation_workspace":"Decisions","settings":settings,"current_allocation":result,
             "selected_campaign":rid,"allocation_settings":{"target_request":rid,"target_face":face,"target_shift":shift,"target_gross":gross,"probabilities":probabilities,"hold_days_by_request":holds,"partner_tolerance":tolerance,"partner_share":share}}
    st.session_state.latest_context=context


@st.cache_data(show_spinner=False)
def campaign_result(rid,face,shift,gross,probabilities,holds,tolerance,share):
    from yieldcrest.campaign_analysis import analyze_campaign
    return analyze_campaign(rid,face,shift,gross,probabilities,holds,tolerance,share)
