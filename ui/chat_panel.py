"""Persistent assistant drawer shared by every workspace."""
import os
from pathlib import Path

import streamlit as st

from assistant_chat import respond
from domain import AS_OF, connect
from decision_engine import live_requests


def set_open(value):
    st.session_state.yc_chat_open = value


def save_connection():
    st.session_state.yc_saved_key = st.session_state.get("yc_key_input", "")
    st.session_state.yc_saved_model = st.session_state.get("yc_model_input", "")


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

        try:
            server_key = st.secrets.get("GEMINI_API_KEY", "")
            server_model = st.secrets.get("GEMINI_MODEL", "")
        except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
            server_key = ""
            server_model = ""
        key = server_key or os.environ.get("GEMINI_API_KEY", "") or st.session_state.get("yc_saved_key", "")
        model = st.session_state.get("yc_saved_model", server_model)

        with st.container(height=280, border=False, key="yc_chat_messages"):
            if not st.session_state.conversation:
                st.markdown("**Understand the decision. Explore another option.**")
                st.write("Ask how festival demand changes an offer, why Prakash gets priority, or which maintenance dates protect revenue.")
            for message in st.session_state.conversation:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
                    if message.get("traces"):
                        with st.expander("Calculation trace"):
                            st.json(message["traces"])

        question = st.chat_input("Ask about this portfolio or change a scenario…",
                                 key="yc_chat_prompt", disabled=not bool(key))
        if not key:
            st.caption("Connect Gemini in Assistant connection to start chatting.")
        else:
            st.caption("Connected to Gemini · Synthetic portfolio")

        with st.expander("Assistant connection"):
            st.caption("Shared access uses GEMINI_API_KEY in Streamlit secrets. A personal key is kept only in this browser session.")
            if not server_key and not os.environ.get("GEMINI_API_KEY", ""):
                st.text_input("Gemini API key", type="password",
                              value=st.session_state.get("yc_saved_key", ""), key="yc_key_input",
                              on_change=save_connection)
            st.text_input("Model ID (optional)", value=model, key="yc_model_input",
                          on_change=save_connection)
        st.button("Clear conversation", key="yc_clear_chat", on_click=clear_conversation)

        if question:
            try:
                with st.spinner("Checking the model…"):
                    answer, traces, used = respond(key, question, st.session_state.conversation,
                                                   workspace_context(section), model)
                st.session_state.conversation.extend([
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": answer, "traces": traces, "model": used},
                ])
                st.rerun()
            except (RuntimeError, ValueError) as error:
                st.error(str(error))
