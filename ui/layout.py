from pathlib import Path
import streamlit as st

def header():
    st.html(Path(__file__).with_name("theme.css"))
    st.html('<header class="yc-mast"><div class="yc-name"><span class="yc-mark">◩</span>YieldCrest</div><div class="yc-context">AdPlay &nbsp; / &nbsp; Hyderabad</div></header>')

def navigation(pages):
    for col, page in zip(st.columns(len(pages)), pages):
        col.button(page, key=f"nav_{page}", type="primary" if st.session_state.page == page else "secondary",
                   use_container_width=True, on_click=navigate, args=(page,))
    return st.session_state.page

def navigate(page):
    st.session_state.page = page

def occupancy(total, available):
    occupied = total - available
    percent = round(100 * occupied / total) if total else 0
    st.html(f'<section class="yc-summary"><b>Portfolio occupancy</b><div class="yc-track"><div class="yc-fill" style="width:{percent}%"></div></div><span class="yc-sub">{occupied} of {total} sites occupied · {percent}%</span></section>')
