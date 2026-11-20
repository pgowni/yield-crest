"""Explain the actual components of a calculated allocation plan."""
import streamlit as st
from yieldcrest.domain import overlaps,HORIZON_END
from yieldcrest.ui.partner_badge import mark,dataframe

money=lambda x:f"₹{x:,.0f}"


def render_plan(plan,names,target_face,target_start,target_end):
    b=plan['breakdown']
    st.markdown('**How the expected contribution adds up**')
    dataframe([{'Component':'Current requests · probability-weighted net','Amount':money(b['current_campaigns'])},
               {'Component':'Future bookings on remaining available dates','Amount':money(b['future_bookings'])},
               {'Component':'Direct maintenance expense','Amount':money(-b['maintenance_expense'])},
               {'Component':'Total expected contribution','Amount':money(b['total'])}],hide_index=True,use_container_width=True)
    st.caption('Current and future booking contributions already deduct revenue shares, commissions, absorbed campaign costs and electricity. Maintenance expense is deducted once, separately. Totals use unrounded figures.')
    st.markdown('**What happens to the selected board and dates?**')
    occupants=[r for r in b['campaigns'] if target_face in r['board_ids'] and overlaps(r['start'],r['end'],target_start,target_end)]
    work=[j for j in plan.get('maintenance_schedule',[]) if j['board_id']==target_face and overlaps(j['start'],j['end'],target_start,target_end)]
    if occupants:
        for r in occupants:
            st.write(mark(f"{names[target_face]} is proposed for {r['client']} from {r['start']} to {r['end']}, conditional on confirmation ({r['confirmation_probability']:.0%}). Reserved until {r['reserve_until']}."))
    elif work:
        st.write('No current client is assigned to the selected dates. Part of the window is blocked for maintenance; the remaining dates are open to future enquiries.')
    else:
        st.write('No current client is assigned to this board during the selected campaign dates. Those dates remain available for future enquiries, subject to existing confirmed bookings. This is not an instruction to leave the board deliberately empty.')
    st.markdown('**Current requests and their contribution**')
    dataframe([{'Client':r['client'],'Assigned boards':'; '.join(names[f] for f in r['board_ids']) or 'Not selected',
                'Booking dates':r['start']+' to '+r['end'],'Proposed price':money(r['proposed_price']),
                'Confirmation chance':f"{r['confirmation_probability']:.0%}",
                'Net if confirmed':money(r['net_if_confirmed']) if r['board_ids'] else '—',
                'Expected net':money(r['expected_contribution'])} for r in b['campaigns']],hide_index=True,use_container_width=True)
    st.markdown('**Future opportunity by board**')
    dataframe([{'Board':names[r['board_id']],'Current requests':money(r['current_campaigns']),
                'Forecast future bookings':money(r['future_bookings']),'Maintenance expense':money(-r.get('maintenance_expense',0)),
                'Total expected net':money(r['expected'])} for r in b['boards']],hide_index=True,use_container_width=True)
    st.caption(f'Future value runs through {HORIZON_END:%d %b %Y}. It uses the same simulated enquiry paths, seasonal demand and paired rental-rate/campaign-duration samples, re-evaluated against each plan’s occupied dates and reservation deadlines. It is an uncertain forecast, not a signed offer; empty simulated periods contribute zero. Maintenance opportunity cost is reflected in the reduced available dates, not deducted a second time.')
    schedule=plan.get('maintenance_schedule',[])
    if schedule:
        st.markdown('**Maintenance calendar for this plan**')
        dataframe([{'Board':names[j['board_id']],'Work':j['task'],'From':j['start'],'Through':j['end'],'Expense':money(j['cost'])} for j in schedule],hide_index=True,use_container_width=True)
