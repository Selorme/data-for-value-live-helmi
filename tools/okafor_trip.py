"""The Okafor family in trip mode's own format, so they can be played on the fair's phone page like the other eight.

Trip mode keeps one invented person per trip. For the family, the visitor plays Ada Okafor, travelling with her husband
Chidi and their children Amara (9) and Tobi (6). The details come from static/trip.json (the family's fields, places and
moments), turned into trip mode's shapes: DATA (profile, fields, data sources), BIZ (the five core places), POOL entries
for the extras, and the small per-person texts trip mode uses for its events (the accident, the message from home, and so on).
"""
import json
import random
import re

trip = json.load(open("static/trip.json", encoding="utf-8"))
OK = next(p for p in trip["people"] if p["id"] == "okafor")
F0, PL = OK["fields"], {pl["id"]: pl for pl in OK["places"]}


def you(s):
    """The family's texts are written about them; the visitor plays Ada, so they become 'you'."""
    s = str(s or "")
    for a, b in [("The family is", "You are"), ("the family is", "you are"), ("The family has", "You have"), ("the family has", "you have"),
                 ("The family", "You"), ("the family", "you"), ("The Okafors", "You"), ("the Okafors", "you"),
                 ("They are", "You are"), ("they are", "you are"), ("They have", "You have"), ("they have", "you have"),
                 ("They were", "You were"), ("they were", "you were"), ("Their ", "Your "), (" their ", " your "), ("They ", "You "), (" they ", " you "),
                 (" them.", " you."), (" them,", " you,"), (" them ", " you "), ("Ada and Chidi", "You and Chidi"), ("Chidi or Ada", "Chidi or you"),
                 ("Ada works", "You work"), ("Ada asks", "You ask"), ("Ada ", "You "), (" Ada", " you")]:
        s = s.replace(a, b)
    return s


# where each detail is kept, as trip mode shows it under My data
SRC = {"trip": "google", "id.kids_dob": "dvv", "id.passport": "dvv", "id.dob": "dvv", "allergy": "kanta", "health.diag": "kanta", "health.all": "kanta",
       "bank.dining": "bank", "bank.all": "bank", "loc.hist": "google", "activity": "health", "msg.whatsapp": "whatsapp", "mail.inbox": "email",
       "web.history": "browser", "photos.all": "photos", "photos.kids": "photos", "diet": "vault"}
ROWS = {"bank.dining": 48, "bank.all": 1022, "loc.hist": 9410, "activity": 365, "msg.whatsapp": 24310, "mail.inbox": 14880, "photos.all": 31200,
        "health.all": 150, "web.history": 2140, "photos.kids": 12}
VERIFIED = {"need.kids": "Population register (children's dates of birth)", "need.ages": "Population register", "need.pickup": "Self-declared",
            "diet": "Self-declared"}
ADV = {"photos.kids": "Photos of your children are about them, not about you. The circus can seat you without them.",
       "id.kids_dob": "The conductor only needs to know the children's ages are right for child tickets. A yes-or-no check would do."}

fields = {}
for k, f in F0.items():
    fields[k] = {"label": you(f["label"]), "value": you(f["value"]), "src": "vault" if f["kind"] == "need" else SRC.get(k, "vault"),
                 "rows": ROWS.get(k, 1), "kind": f["kind"], "verified": VERIFIED.get(k, "Self-declared" if f["kind"] == "need" else "")}
    if k in ADV:
        fields[k]["adv"] = ADV[k]
    if k == "allergy":
        fields[k]["verified"] = "Health centre (allergy clinic, 2021)"
fields["trip"]["value"] = "Train Tampere to Helsinki 12 Nov, 09:05 to 10:52. Hotel 12 to 14 Nov. Return train 14 Nov, 16:30."

R = random.Random(7)
def day(i, base=(2026, 10, 31)):
    import datetime
    d = datetime.date(*base) - datetime.timedelta(days=i)
    return d.isoformat()

needs = [k for k, f in fields.items() if f["src"] == "vault"]
tables = {
    "vault": [{"name": "Your needs", "cols": ["need_id", "category", "need", "verified_by"],
               "rows": [[k.split(".")[-1], fields[k]["label"].split(":")[0], fields[k]["value"], fields[k]["verified"] or "Self-declared"] for k in needs]}],
    "kanta": [{"name": "Health records", "cols": ["date", "who", "type", "text"], "rows":
               [["2021-05-12", "Amara", "diagnosis", "T78.1 Anaphylaxis to tree nuts, after cashew at a birthday party"],
                ["2021-05-12", "Amara", "plan", "Allergy action plan: avoid all tree nuts; adrenaline auto-injector 0.3 mg"],
                ["2023-09-04", "Chidi", "diagnosis", "I10 Essential hypertension"],
                ["2024-02-20", "Tobi", "visit", "Ear infection, antibiotics for 7 days"],
                ["2025-03-11", "Ada", "visit", "Annual check, no findings"]] + [[day(i * 9), R.choice(["Ada", "Chidi", "Amara", "Tobi"]), R.choice(["visit", "lab", "vaccination"]),
                R.choice(["Routine check", "Blood pressure 148/94", "Influenza vaccine", "School health check", "Blood count normal"])] for i in range(20)]},
              {"name": "Prescriptions", "cols": ["date", "who", "medicine", "status"], "rows":
               [[day(i * 30), w, m, "dispensed"] for i, (w, m) in enumerate([("Amara", "Adrenaline auto-injector 0.3 mg, 2 pens"), ("Chidi", "Amlodipine 5 mg"), ("Chidi", "Amlodipine 5 mg"),
                                                                             ("Amara", "Cetirizine 5 mg"), ("Tobi", "Amoxicillin 250 mg"), ("Chidi", "Amlodipine 10 mg")])]}],
    "google": [{"name": "Calendar", "cols": ["date", "event"], "rows": [["2026-11-12", "Train to Helsinki 09:05, Rata Rail"], ["2026-11-12", "Hotel Merikaari, 2 nights"],
                                                                         ["2026-11-13", "Circus 13:00 with the kids"], ["2026-11-14", "Train home 16:30"],
                                                                         ["2026-11-20", "Parents' evening, Hervanta school"]]},
               {"name": "Location points", "cols": ["time", "phone", "place"], "rows": [[f"{day(i // 6)} {7 + (i % 6) * 2:02d}:{(i * 17) % 60:02d}", R.choice(["Ada", "Chidi"]),
                                                                                          R.choice(["Home, Hervanta", "Hervanta school", "Work, Hermia", "Tampere University Hospital", "Prisma Kaleva", "Football practice, Kauppi"])] for i in range(60)]}],
    "bank": [{"name": "Transactions", "cols": ["date", "who", "amount", "description"], "rows": [[day(i * 3), R.choice(["Ada", "Chidi"]), f"-{R.randint(4, 140)}.{R.randint(0, 99):02d}",
                                                                                                R.choice(["K-Market Hervanta", "Pizzeria Napoli", "Hesburger", "School trip payment", "Pharmacy", "Football club fee", "Café Pispala", "Western Union to Lagos"])] for i in range(60)]}],
    "health": [{"name": "Daily activity", "cols": ["date", "who", "steps", "sleep_h"], "rows": [[day(i), R.choice(["Ada", "Chidi"]), R.randint(3000, 14000), round(R.uniform(5, 8.5), 1)] for i in range(60)]}],
    "whatsapp": [{"name": "Chats", "cols": ["time", "chat", "from", "message"], "rows": [
        ["2026-10-02 22:10", "Chidi", "Chidi", "Blood pressure was high again at the check-up. Doctor wants to change my pills."],
        ["2026-10-05 08:12", "School parents 3B", "Teacher", "Reminder: the class trip on Friday is nut-free. Thank you!"],
        ["2026-10-09 19:40", "Family Lagos", "Mama", "When are you bringing the children home for Christmas?"],
        ["2026-10-14 07:55", "Chidi", "Ada", "Can you collect Tobi today? I'm on a late shift"],
        ["2026-10-20 21:03", "Sister", "Ada", "Money is tight after the dentist, but we're managing"],
        ["2026-10-28 18:30", "Chidi", "Chidi", "Booked the hotel for Helsinki 🎉 family room"]]}],
    "email": [{"name": "Inbox", "cols": ["date", "from", "subject"], "rows": [["2026-10-30", "Rata Rail", "Your tickets: Tampere to Helsinki"], ["2026-10-28", "Hotel Merikaari", "Booking confirmation"],
                                                                         ["2026-10-22", "Hervanta school", "Amara's allergy plan for the school year"], ["2026-10-15", "Employer", "Payslip October"],
                                                                         ["2026-10-02", "Kanta", "New prescription for Chidi"]]}],
    "browser": [{"name": "Searches", "cols": ["date", "search"], "rows": [["2026-10-29", "nut-free restaurants Helsinki"], ["2026-10-21", "child booster seat law Finland"],
                                                                          ["2026-10-12", "allergy plan for school"], ["2026-10-03", "high blood pressure diet"], ["2026-09-18", "cheap flights Lagos Christmas"]]}],
    "photos": [{"name": "Photos", "cols": ["date", "place", "who"], "rows": [[day(i * 2), R.choice(["Home", "School", "Football", "Särkänniemi", "Grandma's video call"]), R.choice(["Amara", "Tobi", "Amara and Tobi", "Chidi"])] for i in range(40)]}],
    "dvv": [{"name": "Population register", "cols": ["detail", "value"], "rows": [[fields[k]["label"], fields[k]["value"]] for k in ("id.passport", "id.dob", "id.kids_dob") if k in fields]}],
}
META = {"vault": ("About me (told once)", "Ada, in her vault app", "Your family's needs, written once, in plain words"),
        "kanta": ("Health records and prescriptions", "Kanta", "Diagnoses, visits and prescriptions for the whole family"),
        "google": ("Location history and calendar", "Google", "Where both phones have been, and your calendar"),
        "bank": ("Bank account", "Kaleva Bank", "Every payment from the family account"),
        "health": ("Activity and sleep", "Phone health app", "Steps and sleep for both parents"),
        "whatsapp": ("WhatsApp chats", "WhatsApp", "A year of your chats: family, school parents, friends"),
        "email": ("Email inbox", "Gmail", "School letters, payslips, bank and bookings"),
        "browser": ("Search history", "Your browser", "Three years of searches"),
        "photos": ("Photo library", "Phone photos (cloud)", "Your photos, most of them of Amara and Tobi"),
        "dvv": ("Passports and dates of birth", "Population register", "Identity details for the family")}
sources = []
for sid, (name, holder, what) in META.items():
    rows = sum(f["rows"] for f in fields.values() if f["src"] == sid) if sid not in ("vault", "dvv", "google") else 0
    rows = max(rows, sum(len(t["rows"]) for t in tables[sid]))
    if sid == "google":
        rows = 9410 + 5
    sources.append({"id": sid, "name": name, "holder": holder, "what": what, "rows": rows, "tables": tables[sid]})
total = sum(s["rows"] for s in sources)

profile = {"id": "okafor", "name": "Ada Okafor", "age": 40, "city": "Tampere", "home_area": "Hervanta, Tampere", "job": "Software developer",
           "employer": "", "pronouns": "she/her", "languages": "English, Igbo, Finnish",
           "disability": "No disability. Travelling with her husband Chidi and her children Amara (9) and Tobi (6). Amara has a severe tree-nut allergy and carries an adrenaline pen.",
           "household": "Husband Chidi (42), daughter Amara (9), son Tobi (6)", "trip": "Helsinki, 12-14 Nov 2026 (family weekend), by train"}

WHEN = {"rail": "Thu 12 Nov · 09:05", "hotel": "Thu 12 Nov · arrival", "bistro": "Thu 12 Nov · 18:00", "venue": "Fri 13 Nov · 13:00", "ins": "Before the trip",
        "kidsclub": "Thu 12 Nov, 20:00", "taxi": "Sat 14 Nov, 15:30", "museum": "Fri 13 Nov, 10:00", "pharmacy": "Thu 12 Nov, 16:30", "grocery": "Thu 12 Nov, 12:00", "planner": "Mon 9 Nov, 20:00"}
CORE = {"rail": ("Rata Rail", "Train operator", "You can still travel. You buy the children's tickets at the machine and look for four seats together yourselves."),
        "hotel": ("Hotel Merikaari", "Hotel, Helsinki", "You can still stay. You ask for extra beds at the desk and check every dish at breakfast."),
        "bistro": ("Merikaari Bistro", "Restaurant, same owner as the hotel", "You can still eat there. You ask about nuts in every dish and wait for a table."),
        "venue": ("Satama Family Circus", "Family circus", "You can still go. You look for four seats together when you arrive."),
        "ins": ("Vakaa Insurance", "Insurance company", "You can still buy the standard family policy.")}


def moments(pl):
    out = []
    for m in pl.get("moments", []):
        mm = {"t": you(m["t"]), "dep": m["dep"], "w": you(m["w"]), "b": you(m["b"])}
        if m.get("alt"):
            mm["alt"] = m["alt"] if isinstance(m["alt"], list) else [m["alt"]]
        if m.get("trade"):
            mm["trade"] = 1
            mm["c"] = {}
        else:
            mm["c"] = {"e": 1, "m": 15 + 5 * (len(out) % 3), "r": 1 if len(out) == 0 else 0}
        if m.get("neg"):
            mm["neg"] = 1
        out.append(mm)
    return out


biz = []
for bid in ("rail", "hotel", "bistro", "venue", "ins"):
    pl = PL[bid]
    name, typ, refuse = CORE[bid]
    b = {"id": bid, "name": name, "type": typ, "when": WHEN[bid], "why": you(pl["why"]), "refuse": refuse, "fields": pl["fields"], "moments": moments(pl)}
    if bid == "bistro":
        b["owner"] = "hotel"
    if bid == "ins":
        b["over"] = 1
    biz.append(b)

EXTRA = {}
for bid in ("kidsclub", "taxi", "museum", "pharmacy", "grocery", "planner"):
    pl = PL.get(bid)
    if not pl:
        continue
    ms = moments(pl)
    EXTRA[bid] = {"f": pl["fields"], "m": ms[0] if ms else None, "ms": ms[1:], "when": WHEN[bid], "why": you(pl["why"]).replace("Saturday evening", "Thursday evening")}

OWN = {"rail": {"app": "Passenger bookings", "ref": "RR-5521K", "item": "Tampere to Helsinki, Thu 12 Nov, 09:05, 2 adults + 2 children. Return 14 Nov, 16:30."},
       "hotel": {"app": "Front desk", "ref": "HM-48120", "item": "Family room, 12 to 14 Nov, 2 nights, 2 adults + 2 children"},
       "bistro": {"app": "Table bookings", "ref": "MB-2207", "item": "Table for four, Thu 12 Nov, 18:00"},
       "venue": {"app": "Box office", "ref": "SC-7713", "item": "Family circus, Fri 13 Nov, 13:00, 4 tickets"},
       "ins": {"app": "Underwriting", "ref": "VK-Q-91204", "item": "Family travel insurance quote, 12 to 14 Nov"},
       "kidsclub": {"app": "Kids club bookings", "ref": "KC-118", "item": "Kids club, Thu 12 Nov, 20:00, 2 children"}}

OKAFOR = {
    "data": {"profile": profile, "first": "Ada", "sources": sources, "fields": fields, "samples": {}, "stats": {"trips": 3, "failed": 0, "total": total}},
    "biz": biz, "extra": EXTRA, "own": OWN, "city": "Helsinki",
    "acc": {"what": "On the way back from the circus, Chidi feels dizzy and faint on the tram. You take him to a clinic.", "bill": 310,
            "link": "Chidi's high blood pressure in your health record"},
    "pain": "Blood pressure was high again at the check-up. Doctor wants to change my pills.",
    "home": ["Mama here! Did the children like the train? Send me photos 😊", "They loved it! Tobi counted every station. Photos coming tonight ❤️"],
    "who": "your mum",
    "sty": {"hi": "Hello,", "bye": "Thank you! Ada Okafor"},
    "kidsclub": {"id": "kidsclub", "name": "Merikaari Kids Club", "type": "Childcare at the hotel", "ord": 33, "when": WHEN["kidsclub"],
                 "scene": "You book the hotel's kids club for Thursday evening, so you and Chidi can have dinner alone.",
                 "why": "To look after Amara and Tobi on Thursday evening, keep Amara safe and hand the children only to you or Chidi.",
                 "refuse": "You can still use the kids club. You tell the staff about Amara's allergy at the door."},
}


def js():
    return "const LIVE_OKAFOR=" + json.dumps(OKAFOR, ensure_ascii=False) + ";"


if __name__ == "__main__":
    print(len(js()))
