import importlib
import streamlit as st

st.set_page_config(page_title="YieldCrest · Portfolio", layout="wide")
from yieldcrest.ui import dashboard

# Refresh imported modules once per deployed release, including existing sessions.
_RELEASE = "campaign-workspace-2026-11-20-v15-demand-explanation"
if getattr(dashboard, "_loaded_release", None) != _RELEASE:
    from yieldcrest import decision_engine, campaign_analysis, demand_drivers
    from yieldcrest.ui import decisions, layout, partner_badge, plan_details, demand_explanation
    importlib.invalidate_caches()
    importlib.reload(decision_engine)
    importlib.reload(campaign_analysis)
    importlib.reload(partner_badge)
    importlib.reload(layout)
    importlib.reload(demand_drivers)
    importlib.reload(demand_explanation)
    importlib.reload(plan_details)
    importlib.reload(decisions)
    decisions.calendar_result.clear()
    decisions.campaign_result.clear()
    decisions.joint_result.clear()
    decisions.integrated_service.clear()
    importlib.reload(dashboard)
    dashboard._loaded_release = _RELEASE

dashboard.render()
