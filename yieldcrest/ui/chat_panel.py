"""Persistent assistant drawer shared by every workspace."""
from pathlib import Path

import streamlit as st

from yieldcrest.llm import respond_with_fallback
from yieldcrest.ui.connection import connection, connection_label, render_settings, save_settings
from yieldcrest.domain import AS_OF, connect
from yieldcrest.decision_engine import live_requests


def set_open(value):
    st.session_state.yc_chat_open = value


def save_connection():
    save_settings()


def clear_conversation():
    st.session_state.conversation = []


def workspace_context(section):
    """Retain the last calculated scenario and identify the currently visible page."""
    context = dict(st.session_state.get("latest_context", {}))
    has_previous_calculation = bool(context)
    context["active_workspace"] = section
    context["as_of"] = AS_OF.isoformat()
    context["last_calculation_workspace"] = "Decisions" if has_previous_calculation else None
    with connect() as db:
        requests = live_requests(db)
        context["request_ids"] = [
            {"id":r["id"], "client":r["client"], "confirmed_faces":r["faces"],
             "start":r["start_date"], "end":r["end_date"], "gross":r["gross"]}
            for r in requests
        ]
        context["face_ids"] = {r["id"]:r["name"] for r in db.execute("SELECT id,name FROM faces")}
        context["service_jobs"] = [dict(r) for r in db.execute(
            "SELECT id,face_id,task,earliest_start,latest_finish,duration_days FROM maintenance_jobs")]
    context.setdefault("settings", {"lit": True, "cash": False, "funding": .12})
    return context


def render(section):
    st.session_state.setdefault("yc_chat_open", True)
    st.session_state.setdefault("conversation", [])
    st.session_state.setdefault("yc_saved_key", st.session_state.get("personal_api_key", ""))
    st.html(Path(__file__).with_name("chat_panel.css"))
    if not st.session_state.yc_chat_open:
        with st.container(key="yc_chat_launcher"):
            st.button("Ask YieldCrest", key="yc_open_chat", type="primary",
                      on_click=set_open, args=(True,), use_container_width=True)
        return

    st.html("<style>@media(min-width:1100px){.block-container{max-width:1650px;padding-right:430px;padding-left:2.4rem}}</style>")
    with st.container(key="yc_chat"):
        title, minimize = st.columns([3, 1])
        title.markdown("### Ask YieldCrest")
        minimize.button("Hide", key="yc_hide_chat", on_click=set_open, args=(False,),
                        help="Minimize the assistant. Your conversation stays available.")
        st.caption(f"Viewing {section} · Conversation follows you across workspaces")

        config = connection()
        connected = bool(config["gemini_key"] or config["openai_key"])

        with st.container(height=280, border=False, key="yc_chat_messages"):
            if not st.session_state.conversation:
                st.markdown("**Understand the decision. Explore another option.**")
                st.write("Ask how festival demand changes an offer, why Meridian Ads gets priority, or which maintenance dates protect revenue.")
            for message in st.session_state.conversation:
                with st.chat_message(message["role"]):
                    if message.get("error"):
                        st.warning(message["content"])
                    else:
                        st.markdown(message["content"])
                    if message.get("provider"):
                        st.caption("Answered by "+message["provider"]+(" after Gemini failed" if message.get("fallback_reason") else ""))
                    if message.get("traces"):
                        with st.expander("Calculations used"):
                            for trace in message["traces"]:
                                label = {"compare_calendar":"Campaign calendar and break-even recalculated",
                                         "joint_allocation":"Competing bookings and partner policy compared",
                                         "maintenance_options":"Feasible service windows compared"}.get(trace["tool"],"Decision calculation")
                                st.write(label)

        question = st.chat_input("Ask about this portfolio or change a scenario…",
                                 key="yc_chat_prompt", disabled=not connected)
        st.caption(connection_label(config))
        render_settings(config)
        st.button("Clear conversation", key="yc_clear_chat", on_click=clear_conversation)

        if question:
            history = [m for m in st.session_state.conversation if not m.get("error")]
            st.session_state.conversation.append({"role":"user","content":question})
            try:
                with st.spinner("Checking the figures · OpenAI backup enabled when configured…"):
                    result = respond_with_fallback(question, history, workspace_context(section), **config)
                st.session_state.conversation.append({
                    "role":"assistant", "content":result["text"], "traces":result["traces"],
                    "provider":result["provider"], "model":result["model"],
                    "fallback_reason":result["fallback_reason"],
                })
            except (RuntimeError, ValueError) as error:
                st.session_state.conversation.append({"role":"assistant","content":str(error),"error":True})
            st.rerun()
