import streamlit as st
from yieldcrest.demand_drivers import demand_drivers
from yieldcrest.domain import HORIZON_END
from yieldcrest.ui.partner_badge import dataframe


@st.cache_data(show_spinner=False)
def signals(face,start,end):return demand_drivers(face,start,end)


def render(face,start,end,mode="accept"):
    d=signals(face,start,end)
    st.markdown("#### Demand outlook")
    actual=d['expected_enquiries'];off=d['enquiries_without_festive_indicator']
    ratio=d['price_festive_ratio']
    periods='; '.join(f"{p['start_date']} to {p['end_date']}" for p in d['periods'])
    rows=[{"Factor":"Festive overlap","What the model sees":periods or "No festive overlap",
           "What it means":"These dates may also be needed by festive campaigns." if periods else "A festive overlap is not a reason for this decision."},
          {"Factor":"New enquiries","What the model sees":f"About {actual:.1f} through {HORIZON_END:%d %B}",
           "What it means":"Covers the whole forecast period, including requests for other dates. Enquiries are not guaranteed bookings."},
          {"Factor":"Seasonal demand pattern","What the model sees":f"{actual:.1f} enquiries with the festive pattern; {off:.1f} without it",
           "What it means":"Same board and calendar months; only the festive-sales input is changed."}]
    if periods:
        direction='higher' if ratio>=1 else 'lower'
        rows.append({"Factor":"Festive daily rates","What the model sees":f"About {abs(ratio-1):.0%} {direction} for a booking of this length",
                     "What it means":"Based on accepted demo deals. A better-paying booking may not arrive."})
    dataframe(rows,hide_index=True,use_container_width=True)
    st.markdown("**Evidence supporting this outlook**")
    evidence=[]
    for label,group,count,weight in [
        ("This board","This board",d['evidence']['local_bookings'],d['local_weight']),
        ("Entire portfolio · includes this board","Portfolio",d['evidence']['pooled_bookings'],1-d['local_weight'])]:
        festive=next((r['Accepted bookings'] for r in d['history'] if r['Group']==group and r['Campaign period']=='Festive overlap'),0)
        evidence.append({"History source":label,"Accepted bookings":count,"Festive bookings":festive,
                         "Other bookings":count-festive,"Sampling weight":f"{weight:.0%}"})
    dataframe(evidence,hide_index=True,use_container_width=True)
    st.caption("Sampling weight shows how often the model draws from the board-specific history versus the portfolio pool. The portfolio includes this board, so the counts are not added together. Bookings can share seasonal conditions; more records alone do not establish forecast confidence. All records are synthetic, and pricing evidence covers accepted offers only.")
    st.markdown("**What this means for the decision**")
    if mode in ['future','maintenance']:
        st.markdown("- **Future business:** The chosen plan depends partly on new enquiries arriving and fitting the open dates.\n- **Risk:** The board could remain unsold. Keep marketing it while respecting maintenance dates.")
    elif mode=='competitor':
        st.markdown("- **Current alternative:** Another client gets the overlapping dates, subject to confirmation.\n- **Future business:** Forecast demand applies to dates still available.")
    else:
        st.markdown("- **Current opportunity:** The recommended plan takes this request while considering future demand.\n- **Remaining dates:** New enquiries can still fill the dates left open.")
