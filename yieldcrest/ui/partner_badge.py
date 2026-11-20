"""Display-only partner badges; stored client names and model inputs stay unchanged."""
import re
import pandas as pd
import streamlit as st


def mark(value):
    if not isinstance(value,str):return value
    return re.sub(r'\bMeridian(?: Ads)?\b(?:ˢᴾ)?',lambda m:m.group(0) if m.group(0).endswith('ˢᴾ') else m.group(0)+'ˢᴾ',value)


def dataframe(data,*args,**kwargs):
    view=pd.DataFrame(data).copy()
    for column in view.columns:
        view[column]=view[column].map(mark)
    return st.dataframe(view,*args,**kwargs)


def table(data,*args,**kwargs):
    view=pd.DataFrame(data).copy()
    for column in view.columns:view[column]=view[column].map(mark)
    return st.table(view,*args,**kwargs)
