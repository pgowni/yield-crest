import streamlit as st
from yieldcrest.demand_drivers import demand_drivers
from yieldcrest.domain import HORIZON_END
from yieldcrest.ui.partner_badge import dataframe


@st.cache_data(show_spinner=False)
def signals(face,start,end):return demand_drivers(face,start,end)


def render(face,start,end,mode="accept"):
    d=signals(face,start,end)
    if d['periods']:
        periods='; '.join(f"{p['start_date']} to {p['end_date']}" for p in d['periods'])
        st.write(f"These dates overlap the demo’s festive selling period ({periods}). Accepting this campaign uses dates that another festive campaign might need.")
    else:
        st.write("These dates do not overlap a festive period in the demo calendar.")
    actual=d['expected_enquiries'];off=d['enquiries_without_festive_indicator']
    if off and abs(actual/off-1)>.01:
        verb='raises' if actual>off else 'lowers'
        st.write(f"The forecast suggests about {actual:.1f} new enquiries for this board by {HORIZON_END:%d %B}, including enquiries for other dates. The seasonal pattern in the demo history {verb} this estimate from {off:.1f}.")
    else:
        st.write(f"The forecast suggests about {actual:.1f} new enquiries for this board by {HORIZON_END:%d %B}. The festive pattern makes little difference to this estimate.")
    ratio=d['price_festive_ratio']
    if d['periods'] and abs(ratio-1)>.01:
        direction='higher' if ratio>1 else 'lower'
        st.write(f"For a booking of this length, the pricing model estimates festive daily rates about {abs(ratio-1):.0%} {direction} than other dates. That affects the value of keeping dates available, but does not mean a better-paying client will definitely arrive.")
    if mode in ['future','maintenance']:
        st.write("Here, future business is part of the plan being recommended, rather than just an alternative to an accepted offer. Leaving dates open gives those enquiries a chance to fit; it also means you carry the risk of unsold days.")
    elif mode=='competitor':
        st.write("Here, another current client gets the overlapping dates. Future demand is considered on the dates still free, rather than replacing that client’s booking.")
    else:
        st.write("Here, the model chooses the current request despite the possible future business. Its expected value and the wider board assignments support taking it now; new enquiries can still use the dates left free.")
    with st.expander('History behind the forecast'):
        st.write(f"There are {d['evidence']['local_bookings']} accepted bookings for this board and {d['evidence']['pooled_bookings']} across all boards. About {d['local_weight']:.0%} of the booking examples used come from this board; the rest come from the wider business.")
        rows=[]
        for r in d['history']:
            rows.append({'History':r['Group'],'Dates':r['Campaign period'],'Bookings':r['Accepted bookings'],
                         'Average daily rent':f"₹{r['Average achieved daily rent']:,.0f}" if r['Average achieved daily rent'] is not None else 'No records',
                         'Average booking length (days)':round(r['Average campaign days'],1) if r['Average campaign days'] is not None else 'No records'})
        dataframe(rows,hide_index=True,use_container_width=True)
        st.caption('These are made-up demo records. Prices come from accepted offers only. Several bookings can share the same seasonal conditions, so they are not separate proof that the forecast is accurate.')
