import streamlit as st

from yieldcrest.domain import connect,overlaps
from yieldcrest.decision_engine import live_requests,existing_blocks,clear
from yieldcrest.ui.decisions import service_result,joint_result,money,integrated_service


def explain_assignments(result,job,window,baseline):
    """Explain calendar feasibility separately from financial selection."""
    st.session_state.latest_context={"calculation_workspace":"Operations","current_allocation":result,
        "maintenance_comparison":{"board_id":job["face_id"],"task":job["task"],"window":window,
                                  "without_maintenance":baseline["recommended"]},
        "settings":{"lit":True,"cash":False,"funding":.12}}
    with connect() as db:
        requests={r["id"]:r for r in live_requests(db)}
        boards={r["id"]:f"YC-{r['id']:03d} · {r['name']} · {r['format']}" for r in db.execute("SELECT id,name,format FROM faces")}
        before={a["request_id"]:a for a in baseline["recommended"]["assignments"]}
        for assignment in result["recommended"]["assignments"]:
            rid=assignment["request_id"];request=requests[rid]
            st.markdown(f"**{assignment['client']} · Request {rid}**")
            st.write(f"{request['start_date']} to {request['end_date']} · Proposed price {money(request['gross'])} · Needs {request['quantity']} board(s).")
            st.caption("Client-approved boards: "+"; ".join(boards[f] for f in request["faces"]))
            st.write("Without this service block: "+(", ".join(before[rid]["sites"]) or "Not selected")+". With service: "+(", ".join(assignment["sites"]) or "Not selected")+".")
            conflicts=[]
            feasible=[]
            for face in request["faces"]:
                if not clear(request["start_date"],request["end_date"],existing_blocks(db,face)):
                    conflicts.append(boards[face]+" overlaps an existing confirmed campaign")
                elif face==job["face_id"] and overlaps(request["start_date"],request["end_date"],window["Start"],window["Finish"]):
                    conflicts.append(boards[face]+f" is closed for service from {window['Start']} to {window['Finish']}")
                else:
                    feasible.append(face)
            for conflict in conflicts:st.write("• "+conflict+".")
            if not assignment["sites"]:
                if len(feasible)<request["quantity"]:
                    st.write("There are not enough client-approved boards free for the entire campaign. Other locations or formats require client approval.")
                else:
                    forced=result.get("best_including",{}).get(str(rid))
                    if forced:
                        loss=max(0,result["financial_best"]["expected"]-forced["expected"])
                        st.write(f"The request fits physically, but the best plan including it has expected contribution {money(forced['expected'])} before service expense, {money(loss)} below the financially best plan. The recommendation also applies the partner-priority policy.")
                    else:st.write("No feasible joint plan can include this request alongside the other constraints.")
            else:
                st.write("Selected as part of the recommended joint plan. Assignment remains conditional on the client closing.")
            if before[rid]["sites"]==assignment["sites"]:
                st.caption("This request's assignment did not change when maintenance was added. Its selection should not be attributed to maintenance.")
            st.button("Review this enquiry",key=f"service_enquiry_{rid}",on_click=open_enquiry,args=(rid,))


def open_enquiry(request_id):
    st.session_state.enquiry_request=request_id
    st.session_state.page="Enquiries"


def render():
    st.subheader("Strategic partner policy")
    with connect() as db:
        policy=dict(db.execute("SELECT p.*,c.name FROM partner_policies p JOIN clients c ON c.id=p.client_id").fetchone())
        jobs=[dict(r) for r in db.execute("SELECT j.*,f.name,f.format FROM maintenance_jobs j JOIN faces f ON f.id=j.face_id")]
    st.write(f"**{policy['name']}** · {policy['priority']}")
    st.caption("Editable demo terms. In the decisions view, contribution tolerance selects the best Meridian Ads plan within that amount of the financial best plan.")
    st.table([{"AdPlay revenue share":f"{policy['share']:.0%}","Priority tolerance":money(policy["tolerance_rupees"])}])
    st.subheader("Choose a service window")
    selected=st.selectbox("Service job",[j["id"] for j in jobs],format_func=lambda i:next(f"YC-{j["face_id"]:03d} · "+j["name"]+" · "+j["format"]+" · "+j["task"] for j in jobs if j["id"]==i))
    service=service_result(selected,True,False,.12)
    job=service["job"]
    selected_job=next(j for j in jobs if j["id"]==selected)
    st.info(f"Maintenance affects only YC-{job["face_id"]:03d} · {job["name"]} · {selected_job["format"]}. Other boards at other locations remain available subject to their own bookings.")
    st.write(f"Allow **{job['duration_days']} consecutive days** between **{job['earliest_start']}** and **{job['latest_finish']}**.")
    st.caption(f"Demo service interval {job['interval_days']} days; last service {job['last_service_date']}. Work deadlines are operator inputs. Failure prediction requires equipment records.")
    if not service["windows"]:
        st.warning("No window fits confirmed bookings within the service deadline. An operator must resolve the conflict.")
        return
    best=service["windows"][0]
    a,b,c=st.columns(3)
    a.metric("Lowest-loss feasible start",best["Start"], help='Feasible maintenance start date expected to displace the least future rental contribution, respecting existing bookings and the service deadline.')
    b.metric("Expected rental displaced",money(best["Expected rental displaced"]), help='Expected future rental contribution lost because maintenance blocks availability. A short block can prevent a longer consecutive campaign.')
    c.metric("Service expense",money(best["Service cost"]), help='Direct cost of the selected maintenance job, separate from rental contribution displaced.')
    st.dataframe(service["windows"],hide_index=True,use_container_width=True)
    st.caption("All dates use identical future-demand paths. A short service block can displace an entire campaign if its consecutive dates cannot fit.")
    if st.button("Find best service dates alongside current requests"):
        combined=integrated_service(selected,3,{},policy["tolerance_rupees"],policy["share"],True,False,.12)
        st.info(f"Joint planning chooses {combined['window']['Start']} to {combined['window']['Finish']}, with expected portfolio net {money(combined['net'])} after the service expense.")
        baseline=joint_result(3,{},policy["tolerance_rupees"],policy["share"],True,False,.12,{})
        explain_assignments(combined["result"],job,combined["window"],baseline)
    chosen=st.selectbox("Compare a service window",service["windows"],format_func=lambda w:w["Start"]+" to "+w["Finish"])
    if st.button("Check impact on current requests"):
        blocks={job["face_id"]:[(chosen["Start"],chosen["Finish"])]}
        comparison=joint_result(3,{},policy["tolerance_rupees"],policy["share"],True,False,.12,blocks)
        st.metric("Expected net after service expense",money(comparison["recommended"]["expected"]-job["service_cost"]), help='Expected portfolio contribution for this maintenance scenario after deducting the direct service cost.')
        baseline=joint_result(3,{},policy["tolerance_rupees"],policy["share"],True,False,.12,{})
        st.write(f"Without service, expected portfolio contribution is {money(baseline['recommended']['expected'])}. With this service window, it is {money(comparison['recommended']['expected']-job['service_cost'])} after service expense. Both use the same hold and partner policy.")
        explain_assignments(comparison,job,chosen,baseline)
        st.caption("Scenario only. Choosing a window here does not confirm work or change stored bookings.")

