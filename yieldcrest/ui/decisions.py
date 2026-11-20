from datetime import date
import json
import hashlib

import pandas as pd
import streamlit as st

from yieldcrest.domain import AS_OF, connect
from yieldcrest.explanations import explain_calendar
from yieldcrest.llm import respond_with_fallback
from yieldcrest.ui.connection import connection
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
    settings={"lit":True,"cash":False,"funding":.12}
    with connect() as db:
        requests=live_requests(db)
        names={r["id"]:f"YC-{r["id"]:03d} · {r["name"]} · {r["format"]}" for r in db.execute("SELECT id,name,format FROM faces")}
    single,portfolio=st.tabs(["Accept or preserve dates","Allocate competing requests"])
    context={"settings":settings,"request_ids":[{"id":r["id"],"client":r["client"],"confirmed_faces":r["faces"]} for r in requests],
             "face_ids":names}
    with single:
        st.subheader("What would make this campaign worth accepting?")
        rid=st.selectbox("Campaign", [r["id"] for r in requests],format_func=lambda i:next(r["label"] for r in requests if r["id"]==i),key="decision_request",on_change=reset_campaign_inputs)
        req=next(r for r in requests if r["id"]==rid)
        st.button("Reset campaign scenario",on_click=reset_campaign_inputs)
        revision=st.session_state.get("campaign_revision",0)
        price_key=f"campaign_price_v2_{rid}_{revision}"
        if price_key not in st.session_state:
            st.session_state[price_key]=int(req["gross"])
        a,b,c=st.columns([1,1,1])
        face=a.selectbox("Client-approved board",req["faces"],format_func=lambda i:names[i],key=f"face_{rid}")
        st.caption("Each option identifies an individual board and its physical format. A different board or format requires client approval; the current demo has one board per location.")
        gross=b.number_input("Proposed price (₹)",min_value=0,max_value=1000000,step=1000,key=price_key)
        b.caption(f"Recorded campaign price: {money(req["gross"])}. Edits here apply only to this scenario.")
        shift=c.slider("Move campaign (days)",-5,10,0,key=f"shift_{rid}")
        try:
            result=calendar_result(rid,face,shift,gross,**settings)
        except ValueError as error:
            st.warning(str(error))
            return
        context["current_calendar"]=result
        st.caption(f"{result['request']['start_date']} to {result['request']['end_date']} · Firm-offer comparison · Identical future demand in both calendars")
        a,b,c=st.columns(3)
        a.metric("Break-even proposed price",money(result["break_even_gross"]), help='Proposed gross price at which accepting and preserving the dates have equal expected contribution, under the selected cost settings.')
        b.metric("Expected advantage of accepting",money(result["difference"]), help='Expected net contribution with this firm offer minus expected contribution from keeping the dates available. Positive favors accepting; negative favors waiting.')
        c.metric("Chance of no future booking if waiting",f"{result['wait']['probability_zero']:.0%}", help='Share of simulated futures with no additional booking through the planning horizon if these dates remain open. This is not the current client’s close probability.')
        view=pd.DataFrame([
            {"Choice":"Accept this firm offer","Expected net":result["accept"]["expected"],"Lower outcome (10th percentile)":result["accept"]["p10"],"Upper outcome (90th percentile)":result["accept"]["p90"]},
            {"Choice":"Keep the dates available","Expected net":result["wait"]["expected"],"Lower outcome (10th percentile)":result["wait"]["p10"],"Upper outcome (90th percentile)":result["wait"]["p90"]}])
        display_view=view.copy()
        for column in display_view.columns:
            if column != "Choice":
                display_view[column]=display_view[column].map(money)
        st.dataframe(display_view,hide_index=True,use_container_width=True)
        st.caption("The lower outcome has 10% of simulations below it; the upper outcome has 10% above it. Together they show the middle 80% of simulated outcomes, not a guaranteed range.")
        st.caption(f"Showing {req['label']} · {names[face]} · Proposed price {money(gross)} · Date shift {shift:+d} days. Refreshing with identical inputs produces identical forecasts.")
        with st.expander("Compare with dates five days earlier"):
            try:
                shifted=calendar_result(rid,face,shift-5,gross,**settings)
                st.info(f"For {req['label']} at {names[face]}, moving the currently selected dates five days earlier gives {shifted['request']['start_date']} to {shifted['request']['end_date']}. The break-even proposed price becomes {money(shifted['break_even_gross'])}, compared with {money(result['break_even_gross'])} for the selected dates.")
            except ValueError as error:
                st.info("A five-days-earlier campaign is not feasible: "+str(error))
        if settings["cash"]:
            cash_value=result["expected_cash_by_november_end"]
            st.caption("Expected receipts from this firm offer by 30 November: "+(money(cash_value) if cash_value is not None else "insufficient settled payment history")+". Demo timing assumes invoicing at campaign end and no default.")
        with st.expander("Why these figures?"):
            for paragraph in explain_calendar(result):
                st.markdown(paragraph)
            config=connection()
            signature=hashlib.sha256(json.dumps({"result":result,"settings":settings},sort_keys=True,default=str).encode()).hexdigest()
            st.session_state.setdefault("yc_explanations",{})
            if st.button("Explain this decision with AI",disabled=not bool(config["gemini_key"] or config["openai_key"])):
                try:
                    with st.spinner("Writing an explanation from the calculated figures…"):
                        explanation=respond_with_fallback(
                            "Explain this computed calendar comparison for an advertising operator in 150 words. "
                            "Use only the supplied figures. Cover net money, opportunity cost, threshold and risk. "
                            "Do not calculate new amounts or return JSON.",[],{"current_calendar":result,"settings":settings},**config)
                    st.session_state.yc_explanations={signature:explanation}
                except (RuntimeError,ValueError) as error:
                    st.warning("AI explanation unavailable. "+str(error))
            saved=st.session_state.yc_explanations.get(signature)
            if saved:
                st.divider()
                st.markdown(saved["text"])
                st.caption("Explained by "+saved["provider"]+(" after Gemini failed" if saved["fallback_reason"] else ""))
            st.caption("The explanation updates when the scenario changes. AI wording uses the Python model's results.")
    with portfolio:
        st.subheader("Choose commitments across the same calendar")
        st.caption("Three current requests, client-confirmed alternatives, independent close/fail outcomes. Every commitment is fixed before outcomes are revealed.")
        with connect() as db:
            from yieldcrest.forecasting import close_probability
            learned={str(r["id"]):close_probability(db,r,r["faces"][0]) for r in requests}
        cols=st.columns(len(requests))
        probabilities={}
        for col,r in zip(cols,requests):
            probabilities[str(r["id"])]=col.slider(f"{r['client']} close chance (%)",0,100,round(learned[str(r["id"])]*100),key=f"p_{r['id']}")/100
        a,b,c=st.columns(3)
        hold=a.slider("Hold until · days from today",0,5,3)
        tolerance=b.number_input("Meridian Ads priority tolerance (₹)",0,100000,5000,step=1000)
        share=c.number_input("AdPlay share of Meridian Ads bill (%)",1.,100.,80.,step=1.)/100
        st.caption("The 80% share and ₹5,000 priority tolerance are editable demo assumptions. Longer holds keep the displayed close chances fixed.")
        include=st.toggle("Schedule Ameerpet maintenance alongside these requests",value=False)
        maintenance={}
        service_cost=0
        if include:
            with st.spinner("Comparing service windows and booking assignments together…"):
                integrated=integrated_service(1,hold,probabilities,tolerance,share,**settings)
            maintenance=integrated["blocks"]
            service_cost=integrated["service_cost"]
            window=integrated["window"]
            joint=integrated["result"]
            st.caption(f"Best joint service window {window['Start']} to {window['Finish']}. Rental availability is blocked; {money(service_cost)} service expense applies.")
        else:
            joint=joint_result(hold,probabilities,tolerance,share,maintenance=maintenance,**settings)
        context["allocation_settings"]={"hold_days":hold,"probabilities":probabilities,"partner_tolerance":tolerance,
                                        "partner_share":share,"maintenance":maintenance,**settings}
        context["current_allocation"]=joint
        recommended=joint["recommended"]
        a,b,c=st.columns(3)
        a.metric("Expected portfolio net",money(recommended["expected"]-service_cost), help='Expected contribution from the evaluated boards and requests, including possible future bookings, modeled costs and any selected service expense. Not total company revenue.')
        b.metric("Partner-policy trade-off",money(joint["tradeoff"]), help='Expected contribution given up versus the financially best plan to honor the partner priority tolerance. Zero means the policy adds no expected loss.')
        c.metric("Hold resolves",joint["hold_expiry"], help='Date when uncertain offers resolve. Failed offers release their reserved dates afterward. Close chances stay fixed when hold length changes.')
        st.dataframe([{"Client":a["client"],"Allocate":" + ".join(a["sites"]) or "Decline"} for a in recommended["assignments"]],hide_index=True,use_container_width=True)
        st.caption(f"Middle 80% of simulated portfolio outcomes {money(recommended['p10']-service_cost)} to {money(recommended['p90']-service_cost)} · All five eligible faces included.")
        with st.expander("Competing plans and probability sensitivity"):
            st.dataframe([{"Plan":" / ".join(a["client"]+": "+(",".join(a["sites"]) or "Decline") for a in p["assignments"]),
                           "Expected net":round(p["expected"]-service_cost),"Meridian Ads included":p["partner"]} for p in joint["top_plans"]],hide_index=True,use_container_width=True)
            if st.button("Sweep Meridian Ads close probability"):
                sweep=[]
                for probability in [0,.2,.4,.6,.8,1]:
                    ps=dict(probabilities);ps["1"]=probability
                    r=joint_result(hold,ps,tolerance,share,maintenance=maintenance,**settings)["recommended"]
                    sweep.append({"Meridian Ads chance":probability,"Expected net":r["expected"]-service_cost,
                                  "Allocation":" / ".join(a["client"]+": "+(",".join(a["sites"]) or "Decline") for a in r["assignments"])})
                st.dataframe(sweep,hide_index=True,use_container_width=True)
                st.caption("Other close probabilities stay fixed. Changes are bracketed at 20-percentage-point resolution.")
        with st.expander("Decision assumptions"):
            st.write(joint["model_scope"])
            for item in joint["assumptions"]:
                st.write("• "+item)
        st.session_state.latest_context=context

