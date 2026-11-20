"""Display-only partner badges; stored client names and model inputs stay unchanged."""
import re
import pandas as pd
import streamlit as st


def mark(value):
    if not isinstance(value,str):return value
    if re.search(r'\bMeridian(?: Ads)?',value):
        st.session_state["partner_badge_visible"]=True
    return re.sub(r'\bMeridian(?: Ads)?(?:ˢᴾ| \[SP\])?',lambda m:re.sub(r'(?:ˢᴾ| \[SP\])$','',m.group(0))+' [SP]',value)


def dataframe(data,*args,**kwargs):
    view=pd.DataFrame(data).copy()
    for column in view.columns:
        view[column]=view[column].map(mark)
    return st.dataframe(view,*args,**kwargs)


def table(data,*args,**kwargs):
    view=pd.DataFrame(data).copy()
    for column in view.columns:view[column]=view[column].map(mark)
    return st.table(view,*args,**kwargs)
