import streamlit as st

st.set_page_config(page_title="YieldCrest · Portfolio", layout="wide")
from ui import dashboard

dashboard.render()
