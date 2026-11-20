"""Outcome-specific wording grounded in the recommended allocation."""
from yieldcrest.domain import overlaps,HORIZON_END

money=lambda x:f"₹{x:,.0f}"


def decision_story(result,rid,face,start,end,client,board,chance):
    plan=result['recommended']
    selected=next(r for r in plan['assignments'] if r['request_id']==rid)
    other=[r for r in plan['breakdown']['campaigns'] if r['request_id']!=rid and face in r['board_ids'] and overlaps(r['start'],r['end'],start,end)]
    work=[j for j in plan.get('maintenance_schedule',[]) if j['board_id']==face and overlaps(j['start'],j['end'],start,end)]
    deadline=result['hold_expiries'][str(rid)]
    if selected['sites']:
        mode='accept';headline=f"Offer {board} to {client}"
        message=f"The recommended plan reserves this board for {client} from {start} to {end}, with confirmation due by {deadline}. At the current {chance:.0%} confirmation chance, this is the selected booking plan."
    elif other:
        mode='competitor';names=', '.join(r['client'] for r in other)
        headline=f"Offer {board} to {names} instead"
        message=f"Do not reserve these dates for {client}. The recommended plan assigns the overlapping dates to {names}, subject to their confirmation. This board is not being kept empty for an unknown future buyer."
    elif work:
        mode='maintenance';headline=f"Keep {board} available around maintenance"
        message=f"Do not reserve {start} to {end} for {client}. No current request gets this board for the overlapping dates. Maintenance blocks part of the window; the remaining dates stay open for new enquiries."
    else:
        mode='future';headline=f"Keep {board} open for future business"
        message=f"Do not reserve {start} to {end} for {client} at the current {chance:.0%} confirmation chance. No other current client is assigned to these dates. Keep selling this availability to new enquiries rather than holding it until {deadline}. A future booking is not guaranteed."
    paragraphs=[message]
    inc=result['best_including'][str(rid)];exc=result['best_excluding'][str(rid)]
    if inc:
        gap=exc['expected']-inc['expected']
        if gap>0.01:
            paragraphs.append(f"Keeping this request out earns about {money(gap)} more on average: {money(exc['expected'])} without it versus {money(inc['expected'])} with it. These totals cover the same connected boards, after costs and maintenance; they are not offers for this board alone.")
        elif gap<-.01:
            paragraphs.append(f"Including this request earns about {money(-gap)} more on average across the connected boards: {money(inc['expected'])} with it versus {money(exc['expected'])} without it, after costs and maintenance.")
        else:paragraphs.append('The two choices have almost the same expected earnings. Small changes in the assumptions can change the preferred plan.')
    else:paragraphs.append('The request cannot fit the current board, dates and maintenance constraints, even if the client confirms.')
    if mode in ['future','maintenance']:
        b=next(r for r in plan['breakdown']['boards'] if r['board_id']==face)
        paragraphs.append(f"For this board, the chosen plan forecasts {money(b['future_bookings'])} from future bookings through {HORIZON_END:%d %B}. This covers all remaining available dates, not only {start} to {end}, and is already included in the plan total.")
    if result['tradeoff']>0.01:
        paragraphs.append(f"Strategic-partner priority changes the financial choice, giving up {money(result['tradeoff'])} of expected earnings to favor the partner. This policy, rather than the financial comparison alone, determines the recommendation.")
    return {'mode':mode,'headline':headline,'paragraphs':paragraphs}
