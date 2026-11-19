"""Offline-only synthetic dataset creation. Never called by the running app."""
from datetime import date, timedelta
from pathlib import Path
import json
import random
import sqlite3

from yieldcrest.domain import AS_OF, DATABASE, ROOT, dates, overlaps

PARAMETERS = {
    "seed": 7319, "history_start": "2024-01-01",
    "as_of": AS_OF.isoformat(), "normal_daily_enquiries_per_face": 0.045,
    "festive_sales_enquiry_multiplier": 3.2,
    "festive_daily_rate_multiplier": 1.8, "weekly_shared_demand_range": [0.75, 1.25],
    "demo_reserve": "Faces 1–5 kept free from 19 November for review; operator-declined offers excluded from classifier",
    "client_repeat_close_log_odds": 0.06, "price_ratio_close_log_odds": -1.4,
    "festive_period": "5–20 December, illustrative retail period; not official festival dates",
    "assumptions": "All enquiries are logged, even when unavailable. Hypothetical operator behaviour generates bookings. Synthetic evidence only.",
}


def generate():
    if DATABASE.exists():
        raise SystemExit("Database already exists. Restore from git or choose a new output before regenerating.")
    rng = random.Random(PARAMETERS["seed"])
    db = sqlite3.connect(DATABASE)
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript("""
    CREATE TABLE faces(id INTEGER PRIMARY KEY,name TEXT UNIQUE,zone TEXT,format TEXT,area_sqft INTEGER,
      base_daily INTEGER,electricity_daily INTEGER);
    CREATE TABLE clients(id INTEGER PRIMARY KEY,name TEXT UNIQUE,channel TEXT,sector TEXT);
    CREATE TABLE partner_policies(client_id INTEGER PRIMARY KEY REFERENCES clients,
      share REAL CHECK(share BETWEEN 0 AND 1),tolerance_rupees REAL CHECK(tolerance_rupees>=0),priority TEXT);
    CREATE TABLE seasonal_periods(id INTEGER PRIMARY KEY,label TEXT,start_date TEXT,end_date TEXT,illustrative INTEGER);
    CREATE TABLE enquiries(id INTEGER PRIMARY KEY,client_id INTEGER REFERENCES clients,face_id INTEGER REFERENCES faces,
      received TEXT,requested_start TEXT,requested_end TEXT,status TEXT,record_source TEXT,
      CHECK(received<=requested_start),CHECK(requested_start<=requested_end));
    CREATE TABLE offers(id INTEGER PRIMARY KEY,enquiry_id INTEGER UNIQUE REFERENCES enquiries,quoted TEXT,
      decided TEXT,gross REAL,share REAL,commission REAL,absorbed REAL,illuminated INTEGER,
      feasible_when_quoted INTEGER,outcome TEXT,CHECK(quoted<=decided));
    CREATE TABLE bookings(id INTEGER PRIMARY KEY,offer_id INTEGER UNIQUE REFERENCES offers,face_id INTEGER REFERENCES faces,
      start_date TEXT,end_date TEXT,confirmed TEXT);
    CREATE TABLE invoices(id INTEGER PRIMARY KEY,booking_id INTEGER UNIQUE REFERENCES bookings,issued TEXT,due TEXT,amount REAL);
    CREATE TABLE receipts(id INTEGER PRIMARY KEY,invoice_id INTEGER REFERENCES invoices,paid TEXT,amount REAL);
    CREATE TABLE live_requests(id INTEGER PRIMARY KEY,client_id INTEGER REFERENCES clients,label TEXT,start_date TEXT,
      end_date TEXT,gross REAL,share REAL,commission REAL,absorbed REAL,illuminated INTEGER,
      quantity INTEGER,min_duration INTEGER,expires TEXT,kind TEXT,enquiry_id INTEGER UNIQUE REFERENCES enquiries);
    CREATE TABLE request_faces(request_id INTEGER REFERENCES live_requests,face_id INTEGER REFERENCES faces,
      basis TEXT,PRIMARY KEY(request_id,face_id));
    CREATE TABLE maintenance_jobs(id INTEGER PRIMARY KEY,face_id INTEGER REFERENCES faces,task TEXT,
      earliest_start TEXT,latest_finish TEXT,duration_days INTEGER,service_cost REAL,status TEXT,
      last_service_date TEXT,interval_days INTEGER);
    CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
    """)
    names = ["Ameerpet","Dilsukhnagar","Madhapur","Kondapur","Banjara Hills","Jubilee Hills",
             "Kukatpally","Gachibowli","Begumpet","Secunderabad","Uppal","Hitech City"]
    for i, name in enumerate(names,1):
        zone = "West" if name in ["Madhapur","Kondapur","Gachibowli","Hitech City","Kukatpally"] else "Central" if name in ["Ameerpet","Begumpet","Banjara Hills","Jubilee Hills"] else "East"
        db.execute("INSERT INTO faces VALUES(?,?,?,?,?,?,?)",
                   (i,name,zone,"Hoarding" if i%3 else "Bus shelter",200 if i%3 else 100,
                    1400+150*(i%5),100+15*(i%3)))
    client_names = ["Partner Agency","Lotus Retail","Vista Cinemas","Metro Furnishings","Summit College",
                    "Garden Foods","City Mobility"] + [f"Advertiser {i:02}" for i in range(8,37)]
    for i,name in enumerate(client_names,1):
        db.execute("INSERT INTO clients VALUES(?,?,?,?)",
                   (i,name,"Agency" if i==1 or i%7==0 else "Direct",["Retail","Cinema","Education","Mobility"][i%4]))
    db.execute("INSERT INTO partner_policies VALUES(1,0.8,5000,'Strategic partner')")
    for year in [2024,2025,2026]:
        db.execute("INSERT INTO seasonal_periods(label,start_date,end_date,illustrative) VALUES(?,?,?,1)",
                   ("Illustrative festive retail period",f"{year}-12-05",f"{year}-12-20"))
    # Ordered event generation preserves the operator's information timeline.
    prior_completed = {c: [] for c in range(1,37)}
    occupied = {f: [] for f in range(1,13)}
    week_shocks = {}
    for current in dates(PARAMETERS["history_start"], AS_OF-timedelta(days=1)):
        week = current.isocalendar()[:2]
        week_shocks.setdefault(week,rng.uniform(.75,1.25))
        sales_period = date(current.year,11,5) <= current <= date(current.year,12,20)
        for face in range(1,13):
            arrival = .045 * (3.2 if sales_period else 1) * week_shocks[week]
            if rng.random() >= arrival:
                continue
            client = rng.choices(range(1,37), weights=[5]+[1]*35)[0]
            lead = rng.choice([5,7,10,14,21,28])
            duration = rng.choice([7,10,15,21,30])
            start = current+timedelta(days=lead)
            end = start+timedelta(days=duration-1)
            seasonal = overlaps(start,end,f"{start.year}-12-05",f"{start.year}-12-20")
            base = db.execute("SELECT base_daily FROM faces WHERE id=?",(face,)).fetchone()[0]
            premium = 1.8 if seasonal else 1
            ratio = rng.uniform(.85,1.2)
            gross = round(base*premium*ratio*(.90 if duration>=21 else 1)*duration)
            decided = current+timedelta(days=2)
            feasible = not any(overlaps(start,end,a,b) for a,b in occupied[face])
            repeats = sum(end_date<current for end_date in prior_completed[client])
            import math
            probability = 1/(1+math.exp(-(.35 + .06*min(repeats,10) - 1.4*(ratio-1))))
            won = feasible and rng.random()<probability and decided<AS_OF
            if face <= 5 and end >= AS_OF:
                won = False
                status = "Declined by operator"
            else:
                status = "Won" if won else "Lost" if decided<AS_OF else "Open"
            eid=db.execute("INSERT INTO enquiries(client_id,face_id,received,requested_start,requested_end,status,record_source) VALUES(?,?,?,?,?,?,?)",
                           (client,face,current.isoformat(),start.isoformat(),end.isoformat(),status,"generated")).lastrowid
            share=.8 if client==1 else 1
            commission=.05 if client%7==0 else 0
            db.execute("INSERT INTO offers VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       (eid,eid,current.isoformat(),decided.isoformat(),gross,share,commission,800,1,int(feasible),status))
            if won:
                occupied[face].append((start,end))
                prior_completed[client].append(end)
                bid=db.execute("INSERT INTO bookings(offer_id,face_id,start_date,end_date,confirmed) VALUES(?,?,?,?,?)",
                               (eid,face,start.isoformat(),end.isoformat(),decided.isoformat())).lastrowid
                if end<AS_OF:
                    due=end+timedelta(days=30)
                    amount=round(gross*share*(1-commission))
                    inv=db.execute("INSERT INTO invoices(booking_id,issued,due,amount) VALUES(?,?,?,?)",
                                   (bid,end.isoformat(),due.isoformat(),amount)).lastrowid
                    paid=due+timedelta(days=rng.choice([0,7,14,30,45]))
                    if paid<AS_OF:
                        db.execute("INSERT INTO receipts(invoice_id,paid,amount) VALUES(?,?,?)",(inv,paid.isoformat(),amount))
    # Keep dedicated cases feasible without rewriting the historical training events.
    # Use currently vacant faces; choose five with no confirmed bookings over the planning window.
    available=[]
    for face in range(1,13):
        if not db.execute("SELECT 1 FROM bookings WHERE face_id=? AND end_date>=?",(face,AS_OF.isoformat())).fetchone():
            available.append(face)
    if len(available)<5:
        # Exact case feasibility is checked by the app for all requests, regardless of seeds.
        available=list(range(1,6))
    selected=available[:5]
    for i,(client,label,start,end,gross,kind) in enumerate([
        (1,"Partner Agency · flexible retail campaign","2026-11-25","2026-12-09",65000,"Agency"),
        (2,"Lotus · local storefront","2026-11-25","2026-12-09",43000,"Direct"),
        (3,"Vista · renewal request","2026-11-25","2026-12-09",46000,"Renewal")],1):
        eid=db.execute("INSERT INTO enquiries(client_id,face_id,received,requested_start,requested_end,status,record_source) VALUES(?,?,?,?,?,?,?)",
                       (client,selected[0] if i==1 else selected[i-2],AS_OF.isoformat(),start,end,"Open","live_demo")).lastrowid
        db.execute("INSERT INTO offers VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (eid,eid,AS_OF.isoformat(),"2026-11-24",gross,.8 if client==1 else 1,0,900,1,1,"Open"))
        db.execute("INSERT INTO live_requests VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (i,client,label,start,end,gross,.8 if client==1 else 1,0,900,1,1,7,"2026-11-24",kind,eid))
        eligible=selected if i==1 else [selected[i-2]]
        for face in eligible:
            db.execute("INSERT INTO request_faces VALUES(?,?,?)",(i,face,"Client-confirmed for this synthetic request"))
    for i,face in enumerate(selected[:2],1):
        db.execute("INSERT INTO maintenance_jobs VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (i,face,"Bulb replacement" if i==1 else "Electrical inspection","2026-11-25","2026-12-20",
                    2,1800,"Proposed","2026-05-25",180))
    for key,value in PARAMETERS.items():
        db.execute("INSERT INTO metadata VALUES(?,?)",(key,json.dumps(value)))
    db.commit()
    assert not db.execute("PRAGMA foreign_key_check").fetchall()
    assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data").joinpath("generator_parameters.json").write_text(json.dumps(PARAMETERS,indent=2))
    for table in ["faces","clients","enquiries","offers","bookings","invoices","receipts"]:
        print(table,db.execute("SELECT count(*) FROM "+table).fetchone()[0])
    print("Planning faces", selected)
    db.close()


if __name__=="__main__":
    generate()

