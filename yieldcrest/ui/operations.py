import streamlit as st

from yieldcrest.domain import connect
from yieldcrest.ui.decisions import service_result,joint_result,money,integrated_service


def render():
    st.subheader("Strategic partner policy")
    with connect() as db:
        policy=dict(db.execute("SELECT p.*,c.name FROM partner_policies p JOIN clients c ON c.id=p.client_id").fetchone())
        jobs=[dict(r) for r in db.execute("SELECT j.*,f.name FROM maintenance_jobs j JOIN faces f ON f.id=j.face_id")]
    st.write(f"**{policy['name']}** · {policy['priority']}")
    st.caption("Editable demo terms. In the decisions view, contribution tolerance selects the best Prakash plan within that amount of the financial best plan.")
    st.table([{"AdPlay revenue share":f"{policy['share']:.0%}","Priority tolerance":money(policy["tolerance_rupees"])}])
    st.subheader("Choose a service window")
    selected=st.selectbox("Service job",[j["id"] for j in jobs],format_func=lambda i:next(j["name"]+" · "+j["task"] for j in jobs if j["id"]==i))
    service=service_result(selected,True,False,.12)
    job=service["job"]
    st.write(f"Allow **{job['duration_days']} consecutive days** between **{job['earliest_start']}** and **{job['latest_finish']}**.")
    st.caption(f"Demo service interval {job['interval_days']} days; last service {job['last_service_date']}. Work deadlines are operator inputs. Failure prediction requires equipment records.")
    if not service["windows"]:
        st.warning("No window fits confirmed bookings within the service deadline. An operator must resolve the conflict.")
        return
    best=service["windows"][0]
    a,b,c=st.columns(3)
    a.metric("Lowest-loss feasible start",best["Start"])
    b.metric("Expected rental displaced",money(best["Expected rental displaced"]))
    c.metric("Service expense",money(best["Service cost"]))
    st.dataframe(service["windows"],hide_index=True,use_container_width=True)
    st.caption("All dates use identical future-demand paths. A short service block can displace an entire campaign if its consecutive dates cannot fit.")
    if st.button("Find best service dates alongside current requests"):
        combined=integrated_service(selected,3,{},policy["tolerance_rupees"],policy["share"],True,False,.12)
        st.info(f"Joint planning chooses {combined['window']['Start']} to {combined['window']['Finish']}, with expected portfolio net {money(combined['net'])} after the service expense.")
        st.dataframe([{"Client":r["client"],"Allocate":", ".join(r["sites"]) or "Decline"} for r in combined["result"]["recommended"]["assignments"]],hide_index=True,use_container_width=True)
    chosen=st.selectbox("Compare a service window",service["windows"],format_func=lambda w:w["Start"]+" to "+w["Finish"])
    if st.button("Check impact on current requests"):
        blocks={job["face_id"]:[(chosen["Start"],chosen["Finish"])]}
        comparison=joint_result(3,{},policy["tolerance_rupees"],policy["share"],True,False,.12,blocks)
        st.metric("Expected net after service expense",money(comparison["recommended"]["expected"]-job["service_cost"]))
        st.dataframe([{"Client":r["client"],"Allocate":", ".join(r["sites"]) or "Decline"} for r in comparison["recommended"]["assignments"]],hide_index=True,use_container_width=True)
        st.caption("Scenario only. Choosing a window here does not confirm work or change stored bookings.")

