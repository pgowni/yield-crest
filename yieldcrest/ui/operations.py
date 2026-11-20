from yieldcrest.ui.partner_badge import mark, dataframe, table
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
        st.subheader("How maintenance changes the booking plan")
        st.caption(mark(f"Maintenance scenario: {boards[job['face_id']]} · {job['task']} · {window['Start']} to {window['Finish']}."))
        left,right=st.columns(2)
        with left:
            with st.container(border=True):
                st.markdown(mark("**Board stays available**"))
                st.write(mark("This maintenance job is not scheduled. The board can take bookings, subject to existing commitments."))
                st.metric("Expected contribution",money(baseline["recommended"]["expected"]),help="Contribution under the same hold and partner policy, with no block or expense for this maintenance job.")
        with right:
            with st.container(border=True):
                st.markdown(mark("**Board closed for maintenance**"))
                st.write(mark(f"Only {boards[job['face_id']]} is blocked from {window['Start']} to {window['Finish']}. Bookings are allocated around that closure."))
                st.metric("After maintenance expense",money(result["recommended"]["expected"]-job["service_cost"]),help="Contribution after blocking the selected board and deducting the direct maintenance expense.")
        rows=[]
        details=[]
        for assignment in result["recommended"]["assignments"]:
            rid=assignment["request_id"];request=requests[rid]
            old=before[rid]["sites"];new=assignment["sites"]
            same=sorted(old)==sorted(new)
            status=("Unchanged · same board" if new else "Unchanged · not selected") if same else ("No longer selected" if not new else "Now selected" if not old else "Moved to another board")
            rows.append({"Client":assignment["client"],"Request":rid,
                         "Campaign dates":request["start_date"]+" to "+request["end_date"],
                         "Board stays available":", ".join(old) or "Not selected",
                         "Board closed for maintenance":", ".join(new) or "Not selected",
                         "Effect on allocation":status})
            conflicts=[];feasible=[]
            for face in request["faces"]:
                if not clear(request["start_date"],request["end_date"],existing_blocks(db,face)):
                    conflicts.append(boards[face]+" overlaps an existing confirmed campaign.")
                elif face==job["face_id"] and overlaps(request["start_date"],request["end_date"],window["Start"],window["Finish"]):
                    conflicts.append(boards[face]+f" is closed for maintenance from {window['Start']} to {window['Finish']}.")
                else:feasible.append(face)
            if same:
                reason=(f"The request remains on {', '.join(new)}. This maintenance window does not change its board allocation." if new else "This request is not selected in either scenario. Maintenance has not changed its selection outcome.")
            else:
                reason="The recommended allocation changes when the maintenance closure is added. The model reallocates the requests together under the same partner policy."
            if not new:
                if len(feasible)<request["quantity"]:
                    reason+=" There are not enough client-approved boards free for the full campaign."
                else:
                    forced=result.get("best_including",{}).get(str(rid))
                    if forced:
                        loss=max(0,result["financial_best"]["expected"]-forced["expected"])
                        reason+=f" It fits physically, but the best plan including it is {money(loss)} below the financially best plan before maintenance expense. Partner priority also applies."
                    else:reason+=" No feasible joint plan can include it under these constraints."
            details.append((rid,assignment,request,status,reason,conflicts))
        changed=sum(row["Effect on allocation"].startswith(("Moved","Now","No longer")) for row in rows)
        if changed:
            st.warning(mark(f"{changed} of {len(rows)} request allocations change with this maintenance window."))
        else:
            st.success(mark("No request allocations change. The same clients keep the same boards; maintenance can still affect future rental opportunities and adds its direct expense."))
        dataframe(rows,hide_index=True,use_container_width=True)
        st.caption(mark("Not selected means excluded from the proposed plan, not automatically rejected. Assignments remain conditional on the client closing. No booking or maintenance job is confirmed here."))
        st.markdown(mark("**Request details**"))
        for rid,assignment,request,status,reason,conflicts in details:
            with st.expander(mark(f"{assignment['client']} · Request {rid} · {status}")):
                st.write(mark(reason))
                table([{"Campaign dates":request["start_date"]+" to "+request["end_date"],
                           "Proposed price":money(request["gross"]),"Boards required":request["quantity"]}])
                st.caption(mark("Client-approved boards: "+"; ".join(boards[f] for f in request["faces"])))
                if conflicts:
                    st.markdown(mark("**Availability constraints**"))
                    for conflict in conflicts:st.write(mark("• "+conflict))
                st.button("Review this enquiry",key=f"service_enquiry_{rid}",on_click=open_enquiry,args=(rid,))


def open_enquiry(request_id):
    st.session_state.enquiry_request=request_id
    st.session_state.page="Enquiries"


def render():
    st.subheader("Strategic partner policy")
    with connect() as db:
        policy=dict(db.execute("SELECT p.*,c.name FROM partner_policies p JOIN clients c ON c.id=p.client_id").fetchone())
        jobs=[dict(r) for r in db.execute("SELECT j.*,f.name,f.format FROM maintenance_jobs j JOIN faces f ON f.id=j.face_id")]
    st.write(mark(f"**{policy['name']}** · {policy['priority']}"))
    st.caption(mark("Editable demo terms. In the decisions view, contribution tolerance selects the best Meridian Ads plan within that amount of the financial best plan."))
    table([{"AdPlay revenue share":f"{policy['share']:.0%}","Priority tolerance":money(policy["tolerance_rupees"])}])
    st.subheader("Choose a service window")
    selected=st.selectbox("Service job",[j["id"] for j in jobs],format_func=lambda i:mark(next(f"YC-{j["face_id"]:03d} · "+j["name"]+" · "+j["format"]+" · "+j["task"] for j in jobs if j["id"]==i)))
    service=service_result(selected,True,False,.12)
    job=service["job"]
    selected_job=next(j for j in jobs if j["id"]==selected)
    st.info(mark(f"Maintenance affects only YC-{job["face_id"]:03d} · {job["name"]} · {selected_job["format"]}. Other boards at other locations remain available subject to their own bookings."))
    st.write(mark(f"Allow **{job['duration_days']} consecutive days** between **{job['earliest_start']}** and **{job['latest_finish']}**."))
    st.caption(mark(f"Demo service interval {job['interval_days']} days; last service {job['last_service_date']}. Work deadlines are operator inputs. Failure prediction requires equipment records."))
    if not service["windows"]:
        st.warning(mark("No window fits confirmed bookings within the service deadline. An operator must resolve the conflict."))
        return
    best=service["windows"][0]
    a,b,c=st.columns(3)
    a.metric("Lowest-loss feasible start",best["Start"], help='Feasible maintenance start date expected to displace the least future rental contribution, respecting existing bookings and the service deadline.')
    b.metric("Expected rental displaced",money(best["Expected rental displaced"]), help='Expected future rental contribution lost because maintenance blocks availability. A short block can prevent a longer consecutive campaign.')
    c.metric("Service expense",money(best["Service cost"]), help='Direct cost of the selected maintenance job, separate from rental contribution displaced.')
    dataframe(service["windows"],hide_index=True,use_container_width=True)
    st.caption(mark("All dates use identical future-demand paths. A short service block can displace an entire campaign if its consecutive dates cannot fit."))
    if st.button("Find best service dates alongside current requests"):
        combined=integrated_service(selected,3,{},policy["tolerance_rupees"],policy["share"],True,False,.12)
        st.info(mark(f"Joint planning chooses {combined['window']['Start']} to {combined['window']['Finish']}, with expected portfolio net {money(combined['net'])} after the service expense."))
        baseline=joint_result(3,{},policy["tolerance_rupees"],policy["share"],True,False,.12,{})
        explain_assignments(combined["result"],job,combined["window"],baseline)
    chosen=st.selectbox("Compare a service window",service["windows"],format_func=lambda w:mark(w["Start"]+" to "+w["Finish"]))
    if st.button("Check impact on current requests"):
        blocks={job["face_id"]:[(chosen["Start"],chosen["Finish"])]}
        comparison=joint_result(3,{},policy["tolerance_rupees"],policy["share"],True,False,.12,blocks)
        st.metric("Expected net after service expense",money(comparison["recommended"]["expected"]-job["service_cost"]), help='Expected portfolio contribution for this maintenance scenario after deducting the direct service cost.')
        baseline=joint_result(3,{},policy["tolerance_rupees"],policy["share"],True,False,.12,{})
        explain_assignments(comparison,job,chosen,baseline)
        st.caption(mark("Scenario only. Choosing a window here does not confirm work or change stored bookings."))

