from datetime import date
import json
import os

import pandas as pd
import streamlit as st

from domain import AS_OF, connect
from decision_engine import compare_calendar, joint_allocation, live_requests, maintenance_options, choose_service_allocation
from assistant_chat import respond

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


def scenario_settings():
    with st.expander("Costs and cash timing"):
        a,b,c=st.columns(3)
        lit=a.toggle("Illuminate booked campaigns",value=True,key="lit")
        cash=b.toggle("Adjust for receipt timing",value=False,key="cash")
        funding=c.number_input("Annual funding rate (%)",0.,100.,12.,step=1.,key="funding")/100
        st.caption("Illumination is an operator choice. Settled invoice timing informs the cash scenario; outstanding balances are shown separately.")
    return {"lit":lit,"cash":cash,"funding":funding}


def render():
    settings=scenario_settings()
    with connect() as db:
        requests=live_requests(db)
        names={r["id"]:r["name"] for r in db.execute("SELECT id,name FROM faces")}
    single,portfolio=st.tabs(["Accept or preserve dates","Allocate competing requests"])
    context={"settings":settings,"request_ids":[{"id":r["id"],"client":r["client"],"confirmed_faces":r["faces"]} for r in requests],
             "face_ids":names}
    with single:
        st.subheader("What would make this campaign worth accepting?")
        rid=st.selectbox("Campaign", [r["id"] for r in requests],format_func=lambda i:next(r["label"] for r in requests if r["id"]==i),key="decision_request")
        req=next(r for r in requests if r["id"]==rid)
        a,b,c=st.columns([1,1,1])
        face=a.selectbox("Confirmed location",req["faces"],format_func=lambda i:names[i],key=f"face_{rid}")
        gross=b.number_input("Gross media rent (₹)",0,1000000,int(req["gross"]),step=1000,key=f"gross_{rid}")
        shift=c.slider("Move campaign (days)",-5,10,0,key=f"shift_{rid}")
        try:
            result=calendar_result(rid,face,shift,gross,**settings)
        except ValueError as error:
            st.warning(str(error))
            return
        context["current_calendar"]=result
        st.caption(f"{result['request']['start_date']} to {result['request']['end_date']} · Firm-offer comparison · Identical future demand in both calendars")
        a,b,c=st.columns(3)
        a.metric("Break-even gross media rent",money(result["break_even_gross"]))
        b.metric("Expected advantage of accepting",money(result["difference"]))
        c.metric("Chance of no future booking if waiting",f"{result['wait']['probability_zero']:.0%}")
        view=pd.DataFrame([
            {"Choice":"Accept this firm offer","Expected net":result["accept"]["expected"],"P10":result["accept"]["p10"],"P90":result["accept"]["p90"]},
            {"Choice":"Keep the dates available","Expected net":result["wait"]["expected"],"P10":result["wait"]["p10"],"P90":result["wait"]["p90"]}])
        st.bar_chart(view.set_index("Choice")[["Expected net"]],color="#397e79",horizontal=True)
        st.dataframe(view,hide_index=True,use_container_width=True)
        shifted=calendar_result(rid,face,-5,gross,**settings)
        st.info(f"Moving this campaign five days earlier changes the break-even rent to {money(shifted['break_even_gross'])}. The current offer contributes {money(result['offer_net'])} after share, commission, absorbed costs and selected lighting.")
        if settings["cash"]:
            cash_value=result["expected_cash_by_november_end"]
            st.caption("Expected receipts from this firm offer by 30 November: "+(money(cash_value) if cash_value is not None else "insufficient settled payment history")+". Demo timing assumes invoicing at campaign end and no default.")
        with st.expander("Why these figures?"):
            st.json({"comparison":result,"model":"Poisson enquiry forecast + learned close probability + paired duration/rate samples; chronological online future bookings."})
            st.caption("P10–P90 describes simulated outcomes. It does not measure how certain we are about learned parameters. Mostly pooled evidence can dominate thin site history.")
    with portfolio:
        st.subheader("Choose commitments across the same calendar")
        st.caption("Three current requests, client-confirmed alternatives, independent close/fail outcomes. Every commitment is fixed before outcomes are revealed.")
        with connect() as db:
            from forecasting import close_probability
            learned={str(r["id"]):close_probability(db,r,r["faces"][0]) for r in requests}
        cols=st.columns(len(requests))
        probabilities={}
        for col,r in zip(cols,requests):
            probabilities[str(r["id"])]=col.slider(f"{r['client']} close chance (%)",0,100,round(learned[str(r["id"])]*100),key=f"p_{r['id']}")/100
        a,b,c=st.columns(3)
        hold=a.slider("Hold until · days from today",0,5,3)
        tolerance=b.number_input("Prakash priority tolerance (₹)",0,100000,5000,step=1000)
        share=c.number_input("AdPlay share of Prakash bill (%)",1.,100.,80.,step=1.)/100
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
        a.metric("Expected portfolio net",money(recommended["expected"]-service_cost))
        b.metric("Partner-policy trade-off",money(joint["tradeoff"]))
        c.metric("Hold resolves",joint["hold_expiry"])
        st.dataframe([{"Client":a["client"],"Allocate":" + ".join(a["sites"]) or "Decline"} for a in recommended["assignments"]],hide_index=True,use_container_width=True)
        st.caption(f"Portfolio P10–P90 {money(recommended['p10']-service_cost)} to {money(recommended['p90']-service_cost)} · All five eligible faces included.")
        with st.expander("Competing plans and probability sensitivity"):
            st.dataframe([{"Plan":" / ".join(a["client"]+": "+(",".join(a["sites"]) or "Decline") for a in p["assignments"]),
                           "Expected net":round(p["expected"]-service_cost),"Prakash included":p["partner"]} for p in joint["top_plans"]],hide_index=True,use_container_width=True)
            if st.button("Sweep Prakash close probability"):
                sweep=[]
                for probability in [0,.2,.4,.6,.8,1]:
                    ps=dict(probabilities);ps["1"]=probability
                    r=joint_result(hold,ps,tolerance,share,maintenance=maintenance,**settings)["recommended"]
                    sweep.append({"Prakash chance":probability,"Expected net":r["expected"]-service_cost,
                                  "Allocation":" / ".join(a["client"]+": "+(",".join(a["sites"]) or "Decline") for a in r["assignments"])})
                st.dataframe(sweep,hide_index=True,use_container_width=True)
                st.caption("Other close probabilities stay fixed. Changes are bracketed at 20-percentage-point resolution.")
        with st.expander("Decision assumptions"):
            st.write(joint["model_scope"])
            for item in joint["assumptions"]:
                st.write("• "+item)
        st.session_state.latest_context=context
    render_chat(context)


def render_chat(context):
    st.divider()
    st.subheader("Ask YieldCrest")
    st.caption("Ask why, move dates, change a probability, or explore a service window. Calculations run through the Python engine.")
    try:
        secret_key=st.secrets.get("GEMINI_API_KEY","")
        configured=st.secrets.get("GEMINI_MODEL","")
    except (FileNotFoundError,st.errors.StreamlitSecretNotFoundError):
        secret_key="";configured=""
    key=secret_key or os.environ.get("GEMINI_API_KEY","")
    with st.expander("Assistant connection"):
        st.caption("For shared access, add GEMINI_API_KEY to Streamlit app secrets. A personal key below lasts only for this browser session.")
        personal=st.text_input("Gemini API key",type="password",key="personal_api_key") if not key else ""
        model=st.text_input("Model ID (optional)",value=configured)
        key=key or personal
    st.session_state.setdefault("conversation",[])
    if st.button("Clear conversation"):
        st.session_state.conversation=[]
    for message in st.session_state.conversation:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    question=st.chat_input("Why does moving the campaign change the break-even rent?",disabled=not bool(key))
    if not key:
        st.info("Connect Gemini to enable the conversation. All forecasts and what-if controls are usable above.")
    if question:
        with st.chat_message("user"):
            st.write(question)
        try:
            with st.spinner("Checking the decision and recalculating when needed…"):
                answer,traces,used=respond(key,question,st.session_state.conversation,context,model)
            st.session_state.conversation.extend([{"role":"user","content":question},{"role":"assistant","content":answer}])
            with st.chat_message("assistant"):
                st.markdown(answer)
                with st.expander("Calculation trace"):
                    st.caption(used)
                    st.json(traces)
        except (RuntimeError,ValueError) as error:
            st.error(str(error))
