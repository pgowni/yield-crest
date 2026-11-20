"""Calendar-aware opportunity cost, current allocations and service scheduling."""
from datetime import date, timedelta
from functools import lru_cache
import itertools
import math

import numpy as np

from yieldcrest.domain import AS_OF, HORIZON_END, connect, dates, days, overlaps, net_contribution
from yieldcrest.forecasting import sample_paths, close_probability

SCENARIOS=64


def rows(db, sql, args=()):
    return [dict(r) for r in db.execute(sql,args)]


def live_requests(db):
    result=rows(db,"SELECT r.*,c.name AS client FROM live_requests r JOIN clients c ON c.id=r.client_id ORDER BY r.id")
    for request in result:
        request["faces"]=[r[0] for r in db.execute("SELECT face_id FROM request_faces WHERE request_id=?",(request["id"],))]
    return result


def existing_blocks(db, face):
    return [(r[0],r[1]) for r in db.execute("SELECT start_date,end_date FROM bookings WHERE face_id=? AND end_date>=?",(face,AS_OF.isoformat()))]


def clear(start,end,blocks):
    return not any(overlaps(start,end,a,b) for a,b in blocks)


def payment_profile(db, client, as_of=AS_OF):
    records=rows(db,"""
        SELECT i.id,i.issued,i.due,i.amount,sum(CASE WHEN r.paid<=? THEN r.amount ELSE 0 END) AS paid,
               max(CASE WHEN r.paid<=? THEN r.paid END) AS last_paid
        FROM invoices i JOIN bookings b ON b.id=i.booking_id
        JOIN offers o ON o.id=b.offer_id JOIN enquiries e ON e.id=o.enquiry_id
        LEFT JOIN receipts r ON r.invoice_id=i.id
        WHERE e.client_id=? AND i.issued<=? GROUP BY i.id
    """,(str(as_of),str(as_of),client,str(as_of)))
    settled=[r for r in records if r["paid"]>=r["amount"] and r["last_paid"]]
    # Right-censored overdue invoices remain visible, outside settled-payment timing.
    delays=[max(0,(date.fromisoformat(r["last_paid"])-date.fromisoformat(r["issued"])).days) for r in settled]
    due=sum(max(0,r["amount"]-r["paid"]) for r in records if r["due"]<str(as_of))
    return {"settled_invoices":len(settled),"mean_days_to_pay":round(float(np.mean(delays)),1) if delays else None,
            "overdue_rupees":round(due), "sample_days":delays}


def request_net(db, request, face, cash=False, funding=.12, lit=True):
    site=dict(db.execute("SELECT * FROM faces WHERE id=?",(face,)).fetchone())
    profile=payment_profile(db,request["client_id"])
    delay=profile["mean_days_to_pay"] or 30
    # Receipt lag measured from invoicing at campaign end, discounted from today's decision.
    receipt_days=max(0,(date.fromisoformat(request["end_date"])-AS_OF).days)+delay
    return net_contribution(request["gross"],days(request["start_date"],request["end_date"]),
                            request["share"],request["commission"],request["absorbed"],lit,
                            site["electricity_daily"],cash,receipt_days,funding)


@lru_cache(maxsize=60)
def scenario_data(face, count=SCENARIOS):
    with connect() as db:
        return sample_paths(db,face,HORIZON_END,count=count)


def replay_future(events, blocks, electricity_daily, lit, release=AS_OF, cash=False, funding=.12,
                  current_payment_lag=30):
    """Online policy: accept each positive-contribution feasible arrival.
    The policy cannot see later arrivals. Whole requested intervals must fit.
    """
    occupied=list(blocks)
    result=0.0
    for e in events:
        if e["arrival"] < str(release) or not clear(e["start"],e["end"],occupied):
            continue
        receipt_lag=(date.fromisoformat(e["end"])-AS_OF).days+current_payment_lag
        net=net_contribution(e["gross"],days(e["start"],e["end"]),share=e.get("share",1.),
                             commission=e.get("commission",0.),absorbed=800,
                             illuminated=lit,electricity_daily=electricity_daily,
                             cash_adjust=cash,delay=receipt_lag,annual_rate=funding)
        if net>0:
            result+=net
            occupied.append((e["start"],e["end"]))
    return result


def future_values(db, face, extra=(), release=AS_OF, lit=True, cash=False, funding=.12):
    paths,evidence=scenario_data(face)
    blocks=existing_blocks(db,face)+list(extra)
    cost=db.execute("SELECT electricity_daily FROM faces WHERE id=?",(face,)).fetchone()[0]
    values=np.array([replay_future(path,blocks,cost,lit,release,cash,funding) for path in paths])
    return values,evidence


def stats(values):
    return {"expected":round(float(np.mean(values)),2),"p10":round(float(np.quantile(values,.1)),2),
            "p90":round(float(np.quantile(values,.9)),2),
            "probability_zero":round(float(np.mean(values<=0)),4)}


def compare_calendar(request_id, face, shift=0, gross=None, lit=True, cash=False, funding=.12):
    with connect() as db:
        request=next(r for r in live_requests(db) if r["id"]==request_id)
        if face not in request["faces"]:
            raise ValueError("This face has not been confirmed for this request.")
        for field in ["start_date","end_date"]:
            request[field]=(date.fromisoformat(request[field])+timedelta(days=shift)).isoformat()
        if gross is not None:
            if not 0<=gross<=1000000:
                raise ValueError("Gross rent must be between zero and ₹1,000,000.")
            request["gross"]=gross
        if request["start_date"]<str(AS_OF) or request["end_date"]>str(HORIZON_END):
            raise ValueError("Campaign must fit the demo planning period.")
        if not clear(request["start_date"],request["end_date"],existing_blocks(db,face)):
            raise ValueError("Campaign conflicts with an existing booking.")
        wait,evidence=future_values(db,face,lit=lit,cash=cash,funding=funding)
        remaining,_=future_values(db,face,[(request["start_date"],request["end_date"])],lit=lit,cash=cash,funding=funding)
        offer_net=request_net(db,request,face,cash,funding,lit)
        displaced=float(np.mean(wait-remaining))
        site=dict(db.execute("SELECT * FROM faces WHERE id=?",(face,)).fetchone())
        profile=payment_profile(db,request["client_id"])
        factor=request["share"]*(1-request["commission"])
        if cash:
            lag=max(0,(date.fromisoformat(request["end_date"])-AS_OF).days)+(profile["mean_days_to_pay"] or 30)
            factor/=(1+funding)**(lag/365)
        fixed=request["absorbed"]+days(request["start_date"],request["end_date"])*site["electricity_daily"]*lit
        threshold=max(0,(displaced+fixed)/factor) if factor>0 else None
        receipt_lags=profile["sample_days"]
        month_end=date(2026,11,30)
        collection_chance=(sum(date.fromisoformat(request["end_date"])+timedelta(days=int(lag))<=month_end for lag in receipt_lags)/len(receipt_lags)) if receipt_lags else None
        expected_cash=(request["gross"]*request["share"]*(1-request["commission"])*collection_chance) if collection_chance is not None else None
        return {"expected_cash_by_november_end":round(expected_cash,2) if expected_cash is not None else None,
                "cash_timing_assumption":"Firm offer; invoice issued at campaign end; settled-payment lags; no-default assumption.",
                "request":request,"face":site["name"],"offer_net":round(offer_net,2),
                "wait":stats(wait),"accept":stats(remaining+offer_net),
                "displaced_contribution":round(displaced,2),
                "break_even_gross":round(threshold,2) if threshold is not None else None,
                "evidence":evidence,"payment":profile,
                "close_probability":close_probability(db,request,face),
                "difference":round(float(np.mean(remaining+offer_net-wait)),2),
                "assumption":"Current offer is firm. Future paths are identical in both calendar alternatives.",
                "scenario_count":SCENARIOS}


def candidate_assignments(db, requests):
    choices=[]
    for r in requests:
        eligible=[f for f in r["faces"] if clear(r["start_date"],r["end_date"],existing_blocks(db,f))]
        options=list(itertools.combinations(eligible,r["quantity"]))
        choices.append([()]+options)
    for plan in itertools.product(*choices):
        feasible=True
        for i,j in itertools.combinations(range(len(requests)),2):
            if set(plan[i])&set(plan[j]) and overlaps(requests[i]["start_date"],requests[i]["end_date"],
                                                    requests[j]["start_date"],requests[j]["end_date"]):
                feasible=False
                break
        if feasible:
            yield plan


def connected_requests(requests,target_id):
    """Connected conflicts require both date overlap and a shared approved face."""
    selected={target_id}
    while True:
        expanded=selected | {r["id"] for r in requests if any(
            other["id"] in selected and set(r["faces"]) & set(other["faces"]) and
            overlaps(r["start_date"],r["end_date"],other["start_date"],other["end_date"])
            for other in requests)}
        if expanded==selected:return [r for r in requests if r["id"] in selected]
        selected=expanded


def joint_allocation(hold_days=3, probabilities=None, partner_tolerance=0, partner_share=.8,
                     lit=True, cash=False, funding=.12, maintenance=None,
                     target_request=None,target_face=None,target_shift=0,target_gross=None,hold_days_by_request=None):
    """Two-stage scenario evaluation with nonanticipative commitments.
    A skipped request is declined. Active waitlist requests, when present, are
    allocated jointly after hold outcomes become known, respecting their expiry.
    """
    if not 0<=hold_days<=5:
        raise ValueError("Hold must be between zero and five days.")
    if not 0<partner_share<=1 or not 0<=partner_tolerance<=100000:
        raise ValueError("Check partner share and priority tolerance.")
    if not 0<=funding<=1:
        raise ValueError("Funding rate must be between zero and one.")
    probabilities=probabilities or {}
    with connect() as db:
        requests=live_requests(db)
        if len(requests)>3:
            raise ValueError("The review workspace supports up to three uncertain requests.")
        for r in requests:
            if r["client_id"]==1:
                r["share"]=partner_share
        if target_request is not None:
            target=next((r for r in requests if r["id"]==target_request),None)
            if target is None:raise ValueError("Unknown campaign.")
            if target_face not in target["faces"]:raise ValueError("Board is not client-approved.")
            target["faces"]=[target_face]
            for field in ["start_date","end_date"]:
                target[field]=(date.fromisoformat(target[field])+timedelta(days=target_shift)).isoformat()
            if target_gross is not None:
                if not 0<=target_gross<=1000000:raise ValueError("Check proposed price.")
                target["gross"]=target_gross
            if target["start_date"]<str(AS_OF) or target["end_date"]>str(HORIZON_END):raise ValueError("Campaign must fit the planning period.")
            requests=connected_requests(requests,target_request)
        faces=sorted({f for r in requests for f in r["faces"]})
        releases={}
        for r in requests:
            days_held=(hold_days_by_request or {}).get(str(r["id"]),hold_days)
            if not isinstance(days_held,int) or not 0<=days_held<=5:raise ValueError("Each reservation must be between zero and five days.")
            release=(AS_OF+timedelta(days=days_held)).isoformat()
            if release>min(r["expires"],r["start_date"]):raise ValueError("Reservation cannot extend beyond offer expiry or campaign start.")
            releases[str(r["id"])]=release
        release=max(releases.values())
        probability=[float(probabilities.get(str(r["id"]),close_probability(db,r,r["faces"][0]))) for r in requests]
        if any(not 0<=p<=1 for p in probability):
            raise ValueError("Close probabilities must be between zero and one.")
        maintenance=maintenance or {}
        costs={f:db.execute("SELECT electricity_daily FROM faces WHERE id=?",(f,)).fetchone()[0] for f in faces}
        base={f:existing_blocks(db,f)+maintenance.get(f,[]) for f in faces}
        paths={f:scenario_data(f)[0] for f in faces}
        # For a given plan and close outcome, the forecast is recomputed against
        # those exact occupied intervals and the hold release date.
        value_cache={}
        gains={(r["id"],f):request_net(db,r,f,cash,funding,lit)/r["quantity"] for r in requests for f in r["faces"]}
        def face_revenue(face, locked, outcome):
            key=(face,tuple((r["id"],ok) for r,ok in zip(locked,outcome)))
            if key in value_cache:
                return value_cache[key]
            result=[]
            for events in paths[face]:
                occupied=list(base[face])
                value=0.
                for r,ok in zip(locked,outcome):
                    # Enquiry arrivals before expiry are lost if their campaign
                    # intersects a held interval, even when that offer later fails.
                    if ok:
                        occupied.append((r["start_date"],r["end_date"]))
                        value+=gains[(r["id"],face)]
                filtered=[e for e in events if not any(
                    e["arrival"]<releases[str(r["id"])] and overlaps(e["start"],e["end"],r["start_date"],r["end_date"])
                    for r in locked)]
                value+=replay_future(filtered,occupied,costs[face],lit,AS_OF,cash,funding)
                result.append(value)
            value_cache[key]=np.array(result)
            return value_cache[key]
        plans=[]
        for plan in candidate_assignments(db,requests):
            if any(any(not clear(r["start_date"],r["end_date"],maintenance.get(f,[])) for f in assigned)
                   for r,assigned in zip(requests,plan)):
                continue
            samples=[]
            weights=[]
            expectation=0.
            face_expectations={f:0. for f in faces}
            p_success_partner=0.
            conditional={False:0.,True:0.}
            for outcome in itertools.product([False,True],repeat=len(requests)):
                weight=math.prod(p if ok else 1-p for p,ok in zip(probability,outcome))
                if weight==0 and target_request is None:
                    continue
                totals=np.zeros(SCENARIOS)
                for face in faces:
                    indices=[i for i,assigned in enumerate(plan) if face in assigned]
                    locked=[requests[i] for i in indices]
                    successes=[outcome[i] for i in indices]
                    face_values=face_revenue(face,locked,successes)
                    totals+=face_values
                    face_expectations[face]+=weight*float(np.mean(face_values))
                mean_total=float(np.mean(totals))
                expectation+=weight*mean_total
                if target_request is not None:
                    ti=next(i for i,r in enumerate(requests) if r["id"]==target_request)
                    other_weight=math.prod(p if ok else 1-p for i,(p,ok) in enumerate(zip(probability,outcome)) if i!=ti)
                    conditional[outcome[ti]]+=other_weight*mean_total
                samples.extend(totals.tolist())
                weights.extend([weight/SCENARIOS]*SCENARIOS)
                if plan[0] and outcome[0]:
                    p_success_partner+=weight
            order=np.argsort(samples)
            ordered=np.array(samples)[order]
            cumulative=np.cumsum(np.array(weights)[order])
            quantile=lambda q:float(ordered[min(np.searchsorted(cumulative,q),len(ordered)-1)])
            labels=[{"request_id":r["id"],"client":r["client"],"sites":[db.execute("SELECT name FROM faces WHERE id=?",(f,)).fetchone()[0] for f in assigned]}
                    for r,assigned in zip(requests,plan)]
            campaign_breakdown=[]
            for r,assigned,p_close in zip(requests,plan,probability):
                net=sum(gains[(r["id"],f)] for f in assigned)
                campaign_breakdown.append({"request_id":r["id"],"client":r["client"],"board_ids":list(assigned),
                    "start":r["start_date"],"end":r["end_date"],"proposed_price":r["gross"],
                    "confirmation_probability":p_close,"net_if_confirmed":net,"expected_contribution":net*p_close,
                    "reserve_until":releases[str(r["id"])] if assigned else None})
            boards_breakdown=[]
            for f in faces:
                current=sum(gains[(r["id"],f)]*p_close for r,assigned,p_close in zip(requests,plan,probability) if f in assigned)
                boards_breakdown.append({"board_id":f,"current_campaigns":current,
                    "future_bookings":face_expectations[f]-current,"expected":face_expectations[f]})
            breakdown={"campaigns":campaign_breakdown,"boards":boards_breakdown,
                "current_campaigns":sum(r["expected_contribution"] for r in campaign_breakdown),
                "future_bookings":sum(r["future_bookings"] for r in boards_breakdown),"maintenance_expense":0.,"total":expectation}
            plans.append({"expected":expectation,"p10":quantile(.1),"p90":quantile(.9),
                          "probability_zero":sum(w for v,w in zip(samples,weights) if v<=0),
                          "target_success":conditional[True],"target_failure":conditional[False],
                          "breakdown":breakdown,"assignments":labels,"partner":any(assigned and r["client_id"]==1 for r,assigned in zip(requests,plan)),"plan":plan})
        if not plans:
            raise ValueError("No feasible plan including the service constraint.")
        plans.sort(key=lambda p:p["expected"],reverse=True)
        financial=plans[0]
        preferred=next((p for p in plans if p["partner"] and financial["expected"]-p["expected"]<=partner_tolerance),financial)
        return {"recommended":preferred,"financial_best":financial,"tradeoff":round(financial["expected"]-preferred["expected"],2),
                "all_plans":plans if target_request is not None else [],
                "best_including":{str(r["id"]):next((p for p in plans if p["plan"][i]),None) for i,r in enumerate(requests)},
                "top_plans":plans[:8],"probabilities":dict(zip([str(r["id"]) for r in requests],probability)),
                "hold_expiry":release,"hold_expiries":releases,
                "included_request_ids":[r["id"] for r in requests],
                "best_excluding":{str(r["id"]):next((p for p in plans if not p["plan"][i]),None) for i,r in enumerate(requests)},
                "policy":"Prefer a Meridian Ads allocation within the operator's contribution tolerance.",
                "model_scope":"Skipped requests are declined. Failed holds release their exact faces to subsequent simulated enquiries. No client is assumed to wait past expiry.",
                "assumptions":["Close outcomes assumed independent; the same close probability is held when changing hold length unless overridden.",
                               "Future arrivals follow an online first-feasible booking policy; this is a policy comparison, not perfect-foresight revenue.",
                               "Current allocations are exhaustive; future buyer requests are for one fixed face.",
                               "All values are illustrative synthetic forecasts."]}


def maintenance_options(job_id, lit=True, cash=False, funding=.12):
    with connect() as db:
        job=dict(db.execute("SELECT j.*,f.name FROM maintenance_jobs j JOIN faces f ON f.id=j.face_id WHERE j.id=?",(job_id,)).fetchone())
        baseline,evidence=future_values(db,job["face_id"],lit=lit,cash=cash,funding=funding)
        result=[]
        for start in dates(job["earliest_start"],job["latest_finish"]):
            finish=start+timedelta(days=job["duration_days"]-1)
            if str(finish)>job["latest_finish"]:
                break
            if not clear(start,finish,existing_blocks(db,job["face_id"])):
                continue
            remaining,_=future_values(db,job["face_id"],[(str(start),str(finish))],lit=lit,cash=cash,funding=funding)
            result.append({"Start":str(start),"Finish":str(finish),
                           "Expected rental displaced":round(float(np.mean(baseline-remaining)),2),
                           "Service cost":job["service_cost"]})
        result.sort(key=lambda r:r["Expected rental displaced"])
        return {"job":job,"windows":result,"evidence":evidence}


def choose_service_allocation(job_id,hold_days=3,probabilities=None,partner_tolerance=0,
                              partner_share=.8,lit=True,cash=False,funding=.12):
    """Choose work dates and booking commitments together across all feasible windows."""
    options=maintenance_options(job_id,lit,cash,funding)
    if not options["windows"]:
        raise ValueError("No service window meets the technician deadline.")
    best=None
    for window in options["windows"]:
        blocks={options["job"]["face_id"]:[(window["Start"],window["Finish"])]}
        result=joint_allocation(hold_days,probabilities,partner_tolerance,partner_share,lit,cash,funding,blocks)
        net=result["recommended"]["expected"]-options["job"]["service_cost"]
        if best is None or net>best["net"]:
            best={"window":window,"result":result,"net":net,"blocks":blocks,"service_cost":options["job"]["service_cost"]}
    return best

