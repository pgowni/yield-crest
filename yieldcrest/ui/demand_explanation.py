import streamlit as st
from yieldcrest.demand_drivers import demand_drivers
from yieldcrest.domain import HORIZON_END
from yieldcrest.ui.partner_badge import dataframe


@st.cache_data(show_spinner=False)
def signals(face,start,end):return demand_drivers(face,start,end)


def render(face,start,end):
    d=signals(face,start,end)
    st.markdown('**What demand assumptions are behind the future-booking value?**')
    if d['periods']:
        labels='; '.join(f"{p['label']} ({p['start_date']} to {p['end_date']})" for p in d['periods'])
        st.write('The selected campaign overlaps '+labels+'. Reserving these dates can prevent a future campaign that needs the same consecutive dates.')
    else:
        st.write('The selected campaign does not overlap a recorded festive period. A festival should not be presented as the reason for this decision.')
    actual=d['expected_enquiries'];off=d['enquiries_without_festive_indicator']
    change=(actual/off-1)*100 if off else 0
    direction='higher' if change>0 else 'lower' if change<0 else 'unchanged'
    st.write(f"For this board, the enquiry model expects {actual:.2f} new enquiries through {HORIZON_END:%d %b %Y}. Keeping the board and calendar-month inputs fixed but switching off the festive-sales indicator gives {off:.2f}. The fitted festive signal makes the enquiry estimate {abs(change):.1f}% {direction}. This is a model-feature comparison, not a measured revenue uplift.")
    ratio=d['price_festive_ratio']
    st.write(f"For the same board and campaign duration, the achieved-rate model estimates a festive-to-other-date rental-rate ratio of {ratio:.2f}×. The simulation adjusts historical rate-and-duration pairs using this model; it does not assume every festive booking pays more.")
    st.write(f"Across the shared simulations, an average of {d['overlapping_candidates_per_path']:.2f} future booking candidates per scenario overlap these campaign dates; {d['festive_candidates_per_path']:.2f} overlap a festive period. Candidates have passed the simulated confirmation draw, but may still fail to fit existing bookings, maintenance or other accepted campaigns. Their value is not guaranteed income.")
    st.caption(f"Rate/duration evidence: {d['evidence']['local_bookings']} accepted bookings on this board and {d['evidence']['pooled_bookings']} portfolio bookings. Local history supplies {d['local_weight']:.0%} of template draws; the rest is pooled. History spans {len(d['historical_periods'])} recorded seasonal episodes. These observations share seasonal conditions and are not independent.")
    with st.expander('Inspect the historical demand and pricing evidence'):
        rows=[]
        for r in d['history']:
            rows.append({**r,'Average achieved daily rent':f"₹{r['Average achieved daily rent']:,.0f}" if r['Average achieved daily rent'] is not None else 'No samples',
                         'Average campaign days':round(r['Average campaign days'],1) if r['Average campaign days'] is not None else 'No samples'})
        dataframe(rows,hide_index=True,use_container_width=True)
        st.caption('Descriptive achieved rates from accepted offers only. These do not measure prices of rejected or unlogged opportunities. The model also uses board identity and calendar-month features; future campaigns preserve sampled lead-time, duration and rate pairings.')
    st.caption('All records and seasonal periods are synthetic, including the illustrative December festive window. These signals explain the forecast inputs; the include-versus-exclude calculation determines the actual decision. This panel does not claim that seasonality alone caused the recommendation.')
