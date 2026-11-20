import importlib
import streamlit as st

st.set_page_config(page_title="YieldCrest · Portfolio", layout="wide")
from yieldcrest.ui import dashboard

# Refresh imported modules once per deployed release, including existing sessions.
_RELEASE = "campaign-workspace-2026-11-20-v4"
if getattr(dashboard, "_loaded_release", None) != _RELEASE:
    from yieldcrest import decision_engine, assistant_chat, llm
    from yieldcrest.ui import decisions, operations, chat_panel
    importlib.invalidate_caches()
    importlib.reload(decision_engine)
    importlib.reload(assistant_chat)
    importlib.reload(llm)
    importlib.reload(decisions)
    decisions.joint_result.clear()
    decisions.integrated_service.clear()
    importlib.reload(operations)
    importlib.reload(chat_panel)
    importlib.reload(dashboard)
    dashboard._loaded_release = _RELEASE

dashboard.render()
