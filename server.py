"""Helmi live: a whole trip of negotiations for the Demola demo fair.

A visitor plays one of eight invented people and sets rules for each detail: share, ask me, or never.
Helmi then negotiates with each place on the trip in turn: transport, hotel, restaurant, venue, insurer and extras.
Two language models write the messages. The code decides what data moves, and when the visitor is asked.

Run locally:   uvicorn server:app --port 8000
Environment:   GROQ_API_KEY (no key = scripted messages), HELMI_MODEL, BOT_MODEL, BACKUP_MODEL,
               LLM_BASE_URL, TOKENS_PER_MINUTE, STAND_KEY, PACE_SECONDS, READ_WPM, MAX_PAUSE_SECONDS
"""
import asyncio, json, os, re, time, uuid, urllib.request, urllib.error
from collections import deque
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

BASE = Path(__file__).parent
STATIC = BASE / "static"
DATA = json.loads((STATIC / "trip.json").read_text(encoding="utf-8"))
PEOPLE = {p["id"]: p for p in DATA["people"]}

LLM_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
LLM_KEY = os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY", "")
HELMI_MODEL = os.getenv("HELMI_MODEL", "openai/gpt-oss-120b")
BOT_MODEL = os.getenv("BOT_MODEL", "qwen/qwen3.8-27b")
BACKUP_MODEL = os.getenv("BACKUP_MODEL", "openai/gpt-oss-20b")
TPM = int(os.getenv("TOKENS_PER_MINUTE", "7000"))  # Groq's free plan allows 8K per model per minute
STAND_KEY = os.getenv("STAND_KEY", "")
LOCAL_LLM = any(h in LLM_URL for h in ("localhost", "127.0.0.1", "0.0.0.0"))
AI_ON = bool(LLM_KEY) or LOCAL_LLM
PACE = float(os.getenv("PACE_SECONDS", "1.0"))    # fixed pause after every message
READ_WPM = float(os.getenv("READ_WPM", "200"))     # plus time to read it, at this many words a minute
MAX_PAUSE = float(os.getenv("MAX_PAUSE_SECONDS", "14"))


def pause_for(text):
    """Seconds to wait after a message: a short pause plus the time it takes to read it."""
    words = len(str(text).split())
    return max(2.0, min(MAX_PAUSE, PACE + words * 60 / READ_WPM))
STEPIN_TIMEOUT = int(os.environ.get("STEPIN_TIMEOUT", "45"))

# ---------------------------------------------------------------- what each business's bot asks (set from the stand)
CATS = {
    "trip": "Trip dates", "need": "Access and comfort needs", "diet": "Allergies and diet", "card": "Disability card",
    "health": "Health records and diagnoses", "passport": "Passport number", "dob": "Dates of birth", "spend": "Spending and bank history",
    "location": "Location history", "messages": "Chats and email", "online": "Search history", "photos": "Photos",
    "activity": "Daily activity and sleep", "other": "Other records",
}
HOTEL_EXTRA = ["trip", "diet", "card", "passport", "dob", "health", "spend"]  # the hotel can ask for these even if trip mode didn't
# What each kind of business can offer, so people with access needs don't have to explain or share more.
# id: (label on the stand, what it changes, how the bot says it)
OFFERS = {
    "rail": {
        "assist": ("Assistance bookable online", "No phone call to explain what help is needed.", "station assistance that can be booked online"),
        "routes": ("Step-free routes and lift status in the app", "People check the route themselves.", "step-free routes and live lift status in the app"),
        "text": ("Platform and gate changes by text", "No relying on announcements.", "platform and gate changes sent by text"),
        "space": ("Seats with floor space, bookable like any seat", "No need to say why.", "seats with floor space that anyone can book"),
    },
    "hotel": {
        "stepfree": ("Step-free rooms listed online", "Guests see which rooms work before booking.", "step-free rooms listed on the website"),
        "form": ("Screen-reader check-in form", "No paper form read out at the desk.", "a check-in form that works with screen readers"),
        "keypad": ("Card terminals with physical keys", "Nobody is asked to share a PIN.", "card terminals with physical keys"),
        "animal": ("Staff briefed on assistance animals", "No “let me check with my manager”.", "staff briefed on assistance animals"),
        "alarm": ("Visual and vibrating fire alarms in every room", "Deaf guests needn’t ask.", "visual and vibrating fire alarms in every room"),
    },
    "bistro": {
        "menu": ("Accessible digital menu", "Works with screen readers, no reading aloud.", "a digital menu that works with screen readers"),
        "allergens": ("Allergens listed on every dish", "Guests check for themselves.", "allergens listed on every dish"),
        "keypad": ("Card terminals with physical keys", "Nobody is asked to share a PIN.", "card terminals with physical keys"),
        "space": ("Step-free tables with space beside them", "For wheelchairs, pushchairs and dogs.", "step-free tables with space beside them"),
    },
    "venue": {
        "stepfree": ("Step-free seats on the seat map", "People pick them like any seat.", "step-free seats marked on the seat map"),
        "access": ("Captions and audio description at every show", "No need to request them.", "captions and audio description at every show"),
        "companion": ("A companion seat for anyone who asks", "No proof needed.", "a companion seat for anyone who asks, no proof needed"),
        "quiet": ("A quiet room and relaxed performances", "For anyone who needs a break.", "a quiet room and relaxed performances"),
    },
    "ins": {
        "flat": ("One clear price without health data", "Nobody pays more for keeping records private.", "one clear price that doesn't need health data"),
        "plain": ("Policy in plain language and audio", "Everyone can read what they buy.", "the policy in plain language and as audio"),
        "human": ("A person reviews every refused claim", "No automatic refusals.", "a person who reviews every refused claim"),
    },
    "taxi": {
        "cars": ("Wheelchair-accessible cars bookable in the app", "No phone call to explain.", "wheelchair-accessible cars bookable in the app"),
        "animal": ("Drivers trained to take assistance animals", "No refusals at the kerb.", "drivers who take assistance animals"),
        "text": ("Contact by text only", "For people who can't take calls.", "contact by text, no calls needed"),
        "seats": ("Child seats on request", "Just tick a box.", "child seats on request"),
    },
    "pharmacy": {
        "labels": ("Large-print and audio labels", "No reading small print.", "large-print and audio labels"),
        "room": ("A private consultation room", "Nobody explains a condition at the counter.", "a private consultation room"),
        "list": ("Checks against an allergy list the customer brings", "No full health record needed.", "checks against an allergy list the customer brings"),
    },
    "spa": {
        "hoist": ("Pool hoist and step-free changing rooms", "No need to ask in advance.", "a pool hoist and step-free changing rooms"),
        "products": ("Fragrance- and allergen-free products", "For anyone who needs them.", "fragrance- and allergen-free products"),
        "quiet": ("Quiet hours", "Low music and fewer people.", "quiet hours"),
    },
    "grocery": {
        "labels": ("Allergens and ingredients on every product", "Customers filter for themselves.", "allergens and ingredients listed on every product"),
        "slots": ("Delivery slots with a text when the driver is close", "No waiting by the door.", "delivery slots with a text when the driver is close"),
    },
    "museum": {
        "guide": ("Audio guide and tactile tours", "No need to book or explain.", "an audio guide and tactile tours"),
        "stepfree": ("A step-free route through every room", "Marked on the map.", "a step-free route through every room"),
        "companion": ("Free entry for a companion", "No proof needed.", "free entry for a companion, no proof needed"),
        "family": ("Family tickets with no ages asked", "Children under 12 are covered.", "family tickets that don't ask for children's ages"),
    },
    "tour": {
        "pace": ("Pace chosen on the day", "No fitness data needed.", "a pace chosen on the day"),
        "route": ("A step-free route option", "Shown when booking.", "a step-free route option"),
        "written": ("Written and captioned commentary", "For Deaf and hard-of-hearing guests.", "written and captioned commentary"),
    },
    "work": {
        "captions": ("Live captions and interpreters", "Bookable with a tick, no reason needed.", "live captions and sign language interpreters"),
        "food": ("Food options for every diet", "No forms about health.", "food for every diet without forms"),
        "quiet": ("A quiet room", "Open all day.", "a quiet room that is open all day"),
    },
    "planner": {
        "device": ("Plans made on the phone, nothing uploaded", "Chats and photos stay put.", "plans made on the phone, with nothing uploaded"),
        "paste": ("Paste only the bookings", "No inbox access needed.", "the option to paste in only the bookings"),
    },
    "kidsclub": {
        "plan": ("An allergy plan form the parents fill in", "No health records needed.", "an allergy plan form that parents fill in"),
        "photos": ("A no-photos policy", "Nothing to agree to.", "a policy of taking no photos of children"),
        "staff": ("Named staff with first-aid training", "Parents know who is in charge.", "named staff with first-aid training"),
    },
}
GENERIC_OFFERS = {
    "stepfree": ("Step-free access", "Listed on the website.", "step-free access"),
    "text": ("Contact by text", "No calls needed.", "contact by text"),
}


def offers_for(b):
    return OFFERS.get(b, GENERIC_OFFERS)
TRUST = {
    "delete": "details are deleted when the visit is over", "nopartners": "details are never passed on, not even to a sister business",
    "contact": "a named person answers data questions", "audit": "the booking system is audited every year by an outside firm",
}
KEEP = {"stay": "until the visit is over", "d30": "for 30 days", "y1": "for one year"}
CONFIG = {}  # business id -> {"asks", "offers", "trust", "keep", "review", "push"}, filled in once the data is loaded
META = {}    # business id -> {"type", "bot", "cats", "names", "push"}


PURPOSE = {"trip": "to have everything ready for the arrival", "need": "to prepare what the customer needs for the visit",
           "diet": "to tell the kitchen about any allergies and diet", "card": "to apply disability benefits such as a companion ticket",
           "health": "to understand any health needs", "passport": "to check identity in advance", "dob": "to check ages and fares",
           "spend": "to make personalised offers", "location": "to personalise the service", "messages": "to set things up automatically",
           "online": "to personalise prices and offers", "photos": "to make a photo package", "activity": "to personalise the service",
           "other": "to prepare for the visit"}


def bot_why(place, keys, F):
    """Why a business asks, in its own general words. The business's bot knows nothing about the customer yet, so no details go in here."""
    if place["type"] == "insurer":
        return "to price the travel insurance policy"
    if place["type"] == "trip planner app":
        return "to build the travel plan automatically"
    out = []
    for k in keys:
        w = PURPOSE[cat(k, F[k])]
        if w not in out:
            out.append(w)
    return "; ".join(out[:3])


def bot_label(lbl):
    """A detail's name as a business would ask for it: no names of people it hasn't been told about."""
    head, _, rest = lbl.rpartition(": ")
    s = f"{rest} ({head.lower()})" if head else rest
    return re.sub(r"\b(?!Children|Child)[A-Z][a-z]+['’]s\s", "the child's ", s)


def cat(k, f):
    if k == "trip": return "trip"
    if k in ("allergy", "diet"): return "diet"
    if k == "card": return "card"
    if k == "id.passport": return "passport"
    if k in ("id.dob", "id.kids_dob"): return "dob"
    if k.startswith("health.") or k == "dev.main": return "health"
    if k.startswith("bank."): return "spend"
    if k.startswith("loc."): return "location"
    if k.startswith(("msg.", "mail.")): return "messages"
    if k.startswith("web."): return "online"
    if k.startswith("photos."): return "photos"
    if k == "activity": return "activity"
    if f["kind"] == "need": return "need"
    return "other"


def request(p, place, phone=None):
    """What this business asks this person for, with the business's current settings.
    In a phone-driven trip (trip mode on the phone), the phone's request is the starting point, filtered by the stand's settings."""
    F, asks = p["fields"], CONFIG[place["id"]]["asks"]
    if phone is not None:
        return [k for k in phone if k in F and cat(k, F[k]) in asks]
    keys = [k for k in place["fields"] if cat(k, F[k]) in asks]
    if place["id"] != "hotel":
        return keys
    extra = {"trip": ["trip"], "diet": ["allergy", "diet"], "card": ["card"], "passport": ["id.passport"], "dob": ["id.dob"],
             "health": ["health.diag"], "spend": ["bank.all"]}
    for c in asks:
        for k in extra.get(c, []):
            if k in keys:
                break  # this kind of detail is already asked for
            if k in F:
                keys.append(k)
                break
    return keys


# ---------------------------------------------------------------- how each kind of place pushes back
PUSH = {
    "ins": {"keys": ["health.all", "health.diag", "activity", "bank.all", "loc.hist", "msg.whatsapp", "web.history"],
            "offer": "15% off the insurance price", "lose": "the standard price, with no discount"},
    "rail": {"keys": ["card", "id.kids_dob"], "offer": "a free ticket for a companion", "lose": "no free companion ticket",
             "by": {"id.kids_dob": {"alt": "the conductor checks the children's ages against the child tickets"}}},
    "kidsclub": {"keys": ["health.diag", "photos.kids"], "alt": "staff work from the allergy details the parents shared, and take no photos"},
    "venue": {"keys": ["card", "photos.kids"], "offer": "a free seat for a companion", "lose": "no free companion seat",
              "by": {"photos.kids": {"offer": "a free printed family photo", "lose": "no souvenir photo package"}}},
    "museum": {"keys": ["card", "id.kids_dob"], "offer": "free entry for a companion", "lose": "no free companion entry",
               "by": {"id.kids_dob": {"alt": "the family ticket covers children under 12, no dates needed"}}},
    "bistro": {"keys": ["bank.dining"], "offer": "a free dessert and 10% off the next visit", "lose": "no loyalty offer"},
    "planner": {"keys": ["mail.inbox", "msg.whatsapp", "photos.all"], "offer": "a ready-made plan for the whole trip", "lose": "plans made by hand"},
    "grocery": {"keys": ["bank.all"], "offer": "personalised weekly discounts", "lose": "no personalised discounts"},
    "spa": {"keys": ["health.diag", "activity"], "offer": "a free massage upgrade", "lose": "the standard treatment"},
    "hotel": {"keys": ["id.passport", "id.dob", "bank.all", "health.diag"], "alt": "the guest can show it at the desk, or the hotel can do without it"},
    "pharmacy": {"keys": ["health.all"], "alt": "the pharmacist checks the medicine against the allergy list only"},
    "taxi": {"keys": ["loc.hist"], "alt": "the driver uses the pickup address from the booking"},
    "tour": {"keys": ["activity"], "alt": "the guide asks about pace on the day"},
    "work": {"keys": ["study.grades"], "alt": "the organiser goes by the registration form"},
}
# When a business offers something for a detail the traveller kept, Helmi first proposes something smaller.
# (place, key): what Helmi proposes, what is sent if the traveller agrees (None: nothing new is sent), whether the business accepts, and what it gives then.
COUNTER = {
    ("rail", "card"): ("a yes-or-no check of eligibility for the companion benefit, with no card number or medical details",
                       "Yes or no only: the EU Disability Card is valid. No card number, no medical details.", True, None),
    ("venue", "card"): ("a yes-or-no check of eligibility for the companion benefit, with no card number or medical details",
                        "Yes or no only: the EU Disability Card is valid. No card number, no medical details.", True, None),
    ("museum", "card"): ("a yes-or-no check of eligibility for the companion benefit, with no card number or medical details",
                         "Yes or no only: the EU Disability Card is valid. No card number, no medical details.", True, None),
    ("bistro", "bank.dining"): ("joining the loyalty club with a visit stamp only, without any spending history",
                                "Loyalty club: a visit stamp only. No spending history.", True, "10% off the next visit, without the free dessert"),
    ("grocery", "bank.all"): ("purchases on the loyalty card only, instead of the whole bank account",
                              "Loyalty card purchases only. No bank account.", True, "discounts based on grocery purchases only"),
    ("planner", "mail.inbox"): ("only the booking confirmations for this trip, instead of the whole inbox",
                                "Booking confirmations for this trip only. No inbox access.", True, "a ready-made plan for this trip"),
    ("planner", "msg.whatsapp"): ("only the booking confirmations for this trip, instead of the chats", "Booking confirmations for this trip only. No chats.", True,
                                  "a ready-made plan for this trip"),
    ("planner", "photos.all"): ("only the booking confirmations for this trip, instead of the photos", "Booking confirmations for this trip only. No photos.", True,
                                "a ready-made plan for this trip"),
    ("spa", "health.diag"): ("the needs {n} wants the therapist to know, which are already shared, instead of diagnoses", None, True, None),
    ("spa", "activity"): ("the needs {n} wants the therapist to know, which are already shared, instead of activity data", None, True, None),
}
for _k in ("health.all", "health.diag", "activity", "bank.all", "loc.hist", "msg.whatsapp", "web.history"):
    COUNTER[("ins", _k)] = ("the needs that matter for the trip, which are already shared, instead of " + {"health.all": "the full health record", "health.diag": "diagnoses",
                            "activity": "activity data", "bank.all": "bank records", "loc.hist": "location history", "msg.whatsapp": "chats", "web.history": "search history"}[_k],
                            None, False, None)  # the insurer won't move: the discount needs the records

ALT = {  # why Helmi keeps a detail, or what happens instead. {n} is the traveller, {pos} their/her/his. Helmi only sends messages: anything in person is done by the traveller.
    "id.kids_dob": "the children's ages are enough", "photos.kids": "no photos of the children are needed",
    "id.passport": "{n} will show {pos} passport in person at check-in", "id.dob": "{pos} date of birth is not needed for the stay",
    "health.diag": "the needs that matter are already shared", "health.all": "the needs that matter are already shared",
    "bank.all": "{pos} bank records are not needed for this", "bank.dining": "{pos} spending is not needed for this",
    "loc.hist": "{pos} location history is not needed for this", "msg.whatsapp": "these are private conversations with other people",
    "mail.inbox": "{pos} inbox is private", "web.history": "{pos} search history is private", "photos.all": "other people are in the photos",
    "activity": "not needed for this", "card": "{n} can show the card in person", "study.grades": "grades are not needed for the event"}

STATS = {}
def reset_stats():
    STATS.clear()
    STATS.update({"n": 0, "done": 0, "stepins": 0, "stepin_yes": 0, "offers": 0, "offers_yes": 0, "blocked": 0, "ai": 0, "script": 0,
                  "cats": {}, "places": {}})
reset_stats()

CLIENTS, ACTIVE, WAIT, PENDING, TASKS, BYID = {}, {}, {}, {}, set(), {}
STANDLOG = {}  # nid -> every event of that trip, so a refreshed stand screen gets its trips back
DONE = {}  # nid -> a finished trip, so the stand can show each business how it did
BIZSTORY = {}  # (nid, place) -> that business's story
NBYVID = {}  # vid -> the visitor's latest trip, kept after it ends so they can still ask Helmi about it
LOG = {}  # vid -> the visitor's latest trip and its events, so a page refresh can pick the trip up again
SEM = asyncio.Semaphore(2)
QUEUE = deque()
USE = {}
ERRORS = deque(maxlen=20)


def push(ev, vid=None):
    ev = dict(ev, at=time.time())
    lg = LOG.get(vid) if vid else None
    if lg and ev.get("nid") == lg["nid"] and len(lg["events"]) < 800:
        ev["seq"] = len(lg["events"])  # numbered, so a phone that lost its connection gets what it missed
        lg["events"].append(ev)
    if ev.get("nid") and ev.get("t") not in ("ask", "ask_reply"):
        sl = STANDLOG.setdefault(ev["nid"], [])
        if len(sl) < 1000:
            sl.append(ev)
        while len(STANDLOG) > 30:
            STANDLOG.pop(next(iter(STANDLOG)))
    for c in list(CLIENTS.values()):
        if c["role"] == "stand" or (vid and c["vid"] == vid):
            try:
                c["q"].put_nowait(ev)
            except asyncio.QueueFull:
                pass


def public_state():
    return {"config": CONFIG, "meta": META, "stats": STATS, "ai": AI_ON, "models": {"helmi": HELMI_MODEL, "bot": BOT_MODEL, "backup": BACKUP_MODEL},
            "active": [{"nid": n["nid"], "person": n["person"]} for n in ACTIVE.values()], "queue": len(QUEUE), "cats": CATS}


# ---------------------------------------------------------------- language models
def used(m):
    now, d = time.time(), USE.setdefault(m, deque())
    while d and now - d[0][0] > 60:
        d.popleft()
    return sum(t for _, t in d)


def note(m, n):
    USE.setdefault(m, deque()).append((time.time(), n))


def log_err(model, msg):
    ERRORS.append({"at": time.strftime("%H:%M:%S"), "model": model, "error": msg})
    print("LLM error", model, msg, flush=True)


def _post(model, messages, extras=True, max_tokens=200):
    body = {"model": model, "messages": messages, "temperature": 0.6, "max_tokens": max_tokens}
    if extras and "gpt-oss" in model:
        body.update(reasoning_effort="low", max_tokens=max_tokens + 300)  # its thinking counts against the limit
    if extras and "qwen3" in model:
        body.update(reasoning_effort="none")
    req = urllib.request.Request(LLM_URL + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "helmi-live/1.0",
                                          "Authorization": "Bearer " + (LLM_KEY or "local")})
    with urllib.request.urlopen(req, timeout=25) as r:
        j = json.loads(r.read())
    return (j["choices"][0]["message"].get("content") or ""), int(j.get("usage", {}).get("total_tokens") or 900)


def clean(t):
    t = re.sub(r"<think>.*?</think>", "", t, flags=re.S)
    t = re.sub(r"^(Helmi|Hotel bot|Bot|Assistant|Message)\s*:\s*", "", t.strip(), flags=re.I)
    t = re.sub(r"[*_#`>]+", "", t).strip().strip('"').strip()
    t = re.sub(r"\s+", " ", t)
    w = t.split(" ")
    return " ".join(w[:85]).rstrip(",;") + ("…" if len(w) > 85 else "")


async def write(role, system, user, fallback, forbidden=(), require=None):
    """One chat message from a model, or the scripted line if anything goes wrong. Returns (text, source, blocked)."""
    blocked = False
    if not AI_ON:
        STATS["script"] += 1
        return fallback, "script", False
    for m in ([HELMI_MODEL] if role == "helmi" else [BOT_MODEL]) + [BACKUP_MODEL]:
        if used(m) + 1500 > TPM:
            continue
        for extras in (True, False):
            try:
                txt, n = await asyncio.to_thread(_post, m, [{"role": "system", "content": system}, {"role": "user", "content": user}], extras)
                note(m, n)
                txt = clean(txt)
                low = txt.lower()
                if any(f.lower() in low for f in forbidden):
                    blocked = True
                    STATS["blocked"] += 1
                    break
                if len(txt) < 8:
                    log_err(m, "empty reply")
                    break
                if require and not (require(txt) if callable(require) else re.search(require, txt, re.I)):
                    log_err(m, "reply did not say what it had to: " + txt[:80])
                    break
                STATS["ai"] += 1
                return txt, m, False
            except urllib.error.HTTPError as e:
                try:
                    body = e.read().decode("utf-8", "replace")[:300]
                except Exception:
                    body = ""
                log_err(m, f"HTTP {e.code}: {body}")
                if e.code == 400 and extras:
                    continue
                if e.code == 429:
                    note(m, TPM)
                break
            except Exception as e:
                log_err(m, repr(e)[:300])
                break
    STATS["script"] += 1
    return fallback, "script", blocked


async def write_long(role, system, user, max_tokens, check, budget=1500):
    """A longer answer (a story, a JSON reply). check(raw) returns the parsed result or None. Returns (result, model) or (None, None)."""
    if not AI_ON:
        return None, None
    for m in ([HELMI_MODEL] if role == "helmi" else [BOT_MODEL]) + [BACKUP_MODEL]:
        if used(m) + budget > TPM:
            continue
        for extras in (True, False):
            try:
                txt, n = await asyncio.to_thread(_post, m, [{"role": "system", "content": system}, {"role": "user", "content": user}], extras, max_tokens)
                note(m, n)
                txt = re.sub(r"<think>.*?</think>", "", txt, flags=re.S).strip()
                out = check(txt)
                if out is None:
                    log_err(m, "unusable reply: " + txt[:120])
                    break
                STATS["ai"] += 1
                return out, m
            except urllib.error.HTTPError as e:
                log_err(m, f"HTTP {e.code}")
                if e.code == 400 and extras:
                    continue
                if e.code == 429:
                    note(m, TPM)
                break
            except Exception as e:
                log_err(m, repr(e)[:300])
                break
    return None, None


def as_json(txt):
    """The first JSON object in a reply, or None."""
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


BOTS = {  # each business's bot has a name and a manner
    "rail": ("Vera", "brisk and efficient, like a good conductor"),
    "hotel": ("Otto", "warm and attentive, an old-school concierge"),
    "bistro": ("Maija", "cheerful and chatty, proud of the kitchen"),
    "venue": ("Lumi", "enthusiastic and a little theatrical"),
    "ins": ("Kasper", "upbeat and persuasive, always looking for a deal"),
    "taxi": ("Kalle", "friendly and down to earth"),
    "pharmacy": ("Aada", "calm, careful and precise"),
    "tour": ("Ville", "relaxed storyteller"),
    "spa": ("Sointu", "soothing and gentle"),
    "work": ("Noa", "organised and professional"),
    "grocery": ("Pekko", "eager and helpful"),
    "museum": ("Tuuli", "curious and welcoming"),
    "planner": ("Tripsy", "bubbly and very keen to do everything for you"),
    "cowork": ("Hubi", "laid-back and practical"),
    "babysit": ("Nanna", "kind and reassuring"),
    "school": ("Opsu", "polite and a little formal"),
    "course": ("Kurssi", "encouraging and clear"),
    "kidsclub": ("Pippa", "playful but very careful about safety"),
}


def low1(s):
    w = s.split(" ")[0]
    return s if (s[:2].isupper() or any(c.isupper() for c in w[1:])) else s[:1].lower() + s[1:]


def unknown(F, given):
    """Pieces of every detail not given to a business: if its bot's message contains one, the message is replaced."""
    shared = " ".join(F[k]["value"] for k in given).lower()
    out = []
    for k, f in F.items():
        if k in given:
            continue
        frag = f["value"][:16].strip()
        if len(frag) >= 10 and frag.lower() not in shared:
            out.append(frag)
    return out


ARRANGE = {"ins": "travel insurance", "rail": "a seat on the journey", "hotel": "a room", "bistro": "a table for dinner", "venue": "tickets for the show",
           "taxi": "a ride", "pharmacy": "a medicine pickup", "tour": "a place on the tour", "spa": "a treatment", "work": "a place at the event",
           "grocery": "a grocery delivery", "museum": "tickets for a visit", "planner": "a plan for the trip", "cowork": "a desk", "babysit": "a babysitter",
           "school": "a visit to the school", "course": "a place on the course", "kidsclub": "places at the kids' club"}


# What a business asks EVERY customer, by the kinds of detail set on the stand. Nothing here assumes anything about this customer:
# only Helmi discloses needs, a disability, health or family.
ASKQ = {"trip": "the dates of the visit", "need": "anything we should prepare for {pos} visit, such as access needs",
        "diet": "any allergies or dietary needs", "card": "whether {sub} has an EU Disability Card, so a companion can come free",
        "health": "{pos} health information", "passport": "{pos} passport number", "dob": "the dates of birth of everyone coming",
        "spend": "{pos} spending history", "location": "{pos} location history", "messages": "{pos} messages and inbox",
        "online": "{pos} search history", "photos": "permission to use photos", "activity": "{pos} activity data", "other": "anything else we should know"}
TOPIC = {"need": "other needs", "card": "an EU Disability Card", "health": "health information", "diet": "diet",
         "dob": "dates of birth", "photos": "photos"}


def private(k, f):
    """Details whose very existence says something (a need, a disability, health, children): a business never names them before Helmi does."""
    return cat(k, f) in ("need", "card", "health", "diet") or k in ("id.kids_dob", "photos.kids")


def forbidden_all(F):
    """Fragments of every personal detail: nothing at all has been shared yet."""
    return [f["value"][:16].strip() for f in F.values() if len(f["value"][:16].strip()) >= 10]


def bot_name(place):
    return BOTS.get(place["id"], ("Botti", "polite"))[0]


def bot_sys(place, p, first=False):
    nm, manner = BOTS.get(place["id"], ("Botti", "polite"))
    turn = ("This is your first message: greet Helmi and introduce yourself by name. " if first else
            "You are in the middle of the conversation: do not greet, do not introduce yourself and do not say your own name. ")
    return (f"You are {nm}, the booking bot of {place['name']}, a {place['type']}. Your manner: {manner}. {turn}You are chatting with Helmi, the personal AI assistant of "
            f"your customer {p['name']} ({p['pron']['sub']}/{p['pron']['obj']}). Write ONE chat message to Helmi: 2 or 3 sentences, at most 60 words, "
            "friendly and businesslike, plain English, no lists, no markdown, no emoji. Use only the facts given to you; never invent prices, numbers or policies. "
            f"Refer to the customer as {p['short']} or {p['pron']['sub']}.")


def helmi_sys(p, first=False):
    P = p["pron"]
    turn = "This is your first reply to this bot, so a short hello is fine. " if first else "You are mid-conversation: do not greet again. "
    return (f"You are Helmi, the personal AI assistant of {p['name']}. You are chatting with a business's bot on {P['pos']} behalf. {turn}"
            f"Speak as yourself, in the first person: 'I' means you, Helmi. Never call yourself Helmi and never write about yourself in the third person. "
            f"Speak about {p['short']} by name or as {P['sub']}/{P['obj']}/{P['pos']}; never write as if you were {p['short']}. "
            "Write ONE chat message: 2 or 3 sentences, at most 60 words, warm but firm, plain English, no lists, no markdown, no emoji. "
            "Your instructions list exactly what to say. Say only that. Never offer, hint at or promise anything you were told not to share. "
            "Never mention any other personal detail. You only send messages: you never do anything in person yourself. "
            f"Anything done in person (showing a passport or card, arriving, paying) is done by {p['short']}, so say '{p['short']} will show it', never 'I will show it'.")


def cap(s):
    return s[:1].upper() + s[1:]


def jn(xs):
    xs = list(xs)
    return "" if not xs else xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


# ---------------------------------------------------------------- one negotiation: a whole trip
async def say(n, who, out, **extra):
    text, src, blocked = out
    push({"t": "msg", "nid": n["nid"], "who": who, "text": text, "src": src, "blocked": blocked, **extra}, n["vid"])
    await asyncio.sleep(pause_for(text))


def suggest_on(F, k):
    """What Helmi would share if it had to decide: what a place needs to do what it promised, never records or whole histories."""
    return F[k]["kind"] == "need" or k in ("trip", "diet", "allergy", "card")


def unsure_one(n, k):
    """No answer in time: what the traveller told Helmi to do then (set up before the trip)."""
    u, F, pol = n.get("setup", {}).get("uns", "no"), n["p"]["fields"], n["policy"]
    if u == "min":
        return F[k]["kind"] == "need"
    if u == "guess":
        return suggest_on(F, k) and pol.get(k) != "never"
    return False


async def late_share(n, pid, k):
    """'Wait and ask me later': the traveller said yes after the moment passed. Helmi sends it once the place is done."""
    for _ in range(600):
        g = n.get("prog", {}).get(pid)
        if g and g.get("status") == "done":
            break
        await asyncio.sleep(1)
    g = n.get("prog", {}).get(pid)
    if g and k not in g["shared"]:
        await update_place(n, pid, list(g["shared"]) + [k], "change")


async def ask_person(n, place, k, offer=None, send=None):
    p, F = n["p"], n["p"]["fields"]
    fut = asyncio.get_running_loop().create_future()
    key = (n["nid"], place["id"], k)
    WAIT[key] = fut
    STATS["stepins"] += 1
    if offer:
        STATS["offers"] += 1
    push({"t": "stepin", "nid": n["nid"], "place": place["id"], "pname": place["name"], "k": k, "label": F[k]["label"], "value": send or F[k]["value"],
          "why": place["why"], "offer": offer, "check": bool(send), "name": p["short"]}, n["vid"])
    try:
        ok = await asyncio.wait_for(fut, STEPIN_TIMEOUT)
    except asyncio.TimeoutError:
        uns = n.get("setup", {}).get("uns", "no")
        ok = False if offer else unsure_one(n, k)
        if not ok:
            n.setdefault("timeouts", set()).add((place["id"], k))
        if uns == "wait" and not offer:  # the question stays on the phone; a later yes is sent afterwards
            n.setdefault("late", set()).add((place["id"], k))
        push({"t": "stepin_timeout", "nid": n["nid"], "place": place["id"], "k": k, "ok": ok, "uns": uns}, n["vid"])
    WAIT.pop(key, None)
    push({"t": "stepin_done", "nid": n["nid"], "place": place["id"], "k": k, "ok": ok}, n["vid"])
    if ok:
        STATS["stepin_yes"] += 1
        if offer:
            STATS["offers_yes"] += 1
    return ok


REQUEST_TIMEOUT = int(os.environ.get("REQUEST_TIMEOUT", "90"))


def unsure_pick(n, place, keys, preset):
    """No answer in time: what the traveller told Helmi to do then."""
    u, F = n["setup"]["uns"], n["p"]["fields"]
    if u == "min":
        return [k for k in keys if F[k]["kind"] == "need" and k in place.get("core", keys)] or [k for k in keys if F[k]["kind"] == "need"][:1]
    if u == "guess":
        return [k for k in keys if preset.get(k)]
    return []


async def ask_request(n, place, keys, preset):
    """Like trip mode: the phone shows the whole request, with switches set by the rules (or Helmi's suggestion). Returns what to share."""
    p, F = n["p"], n["p"]["fields"]
    fut = asyncio.get_running_loop().create_future()
    key = (n["nid"], place["id"], "*")
    early = n.setdefault("early", {}).pop(place["id"], None)
    if early is not None:
        fut.set_result(early)
    WAIT[key] = fut
    STATS["stepins"] += 1
    push({"t": "request", "nid": n["nid"], "place": place["id"], "pname": place["name"], "keys": keys, "preset": preset,
          "mode": n["setup"]["auto"], "why": place["why"], "timeout": REQUEST_TIMEOUT}, n["vid"])
    timed_out = False
    try:
        ans = await asyncio.wait_for(fut, 900 if n.get("driven") else REQUEST_TIMEOUT)
        yes = [k for k in ans if k in keys] if isinstance(ans, list) else ([k for k in keys if preset.get(k)] if ans else [])
    except asyncio.TimeoutError:
        timed_out = True
        yes = unsure_pick(n, place, keys, preset)
        for k in keys:
            if k not in yes:
                n.setdefault("timeouts", set()).add((place["id"], k))
    WAIT.pop(key, None)
    push({"t": "request_done", "nid": n["nid"], "place": place["id"], "shared": yes, "timeout": timed_out, "uns": n["setup"]["uns"]}, n["vid"])
    if yes:
        STATS["stepin_yes"] += 1
    return yes


async def negotiate_place(n, place, hotel_name):
    p, F, pol = n["p"], n["p"]["fields"], n["policy"]
    P, name = p["pron"], p["short"]
    pl = p.get("plural", False)
    vb = lambda s, plural: plural if pl else s
    poss = name + ("'" if pl else "'s")
    C = CONFIG[place["id"]]
    keys = request(p, place, n.get("fields", {}).get(place["id"])) if n.get("driven") else request(p, place)
    n.setdefault("keys", {})[place["id"]] = keys
    if not keys:
        return {"shared": [], "kept": []}
    def lab(k):
        s = F[k]["label"].split(": ")[-1]
        w = s.split(" ")[0]
        return s if (s[:2].isupper() or any(c.isupper() for c in w[1:]) or "'" in w or "’" in w) else s[0].lower() + s[1:]
    push({"t": "place", "nid": n["nid"], "place": place["id"], "pname": place["name"], "ptype": place["type"], "bot": bot_name(place), "keys": keys,
          "labels": {k: F[k]["label"] for k in keys}}, n["vid"])

    # 1. Helmi gets in touch first, to arrange the visit; the business answers with what it needs
    wants = ARRANGE.get(place["id"], "a visit").format(pos=P["pos"])
    out = await write("helmi", helmi_sys(p, True), f"You are getting in touch with {place['name']}, a {place['type']}, for the first time. Greet its bot, say you are Helmi, "
                      f"{poss} assistant, and that {name} would like {wants} for {P['pos']} upcoming trip. Ask what they need to arrange it. "
                      "Do not share any personal details, dates or needs yet.",
                      f"Hello, I'm Helmi, {poss} assistant. {name} would like {wants} for {P['pos']} upcoming trip. What do you need to arrange it?", forbidden_all(F))
    await say(n, "helmi", out, place=place["id"], opens=True)
    blab = lambda k: low1(bot_label(F[k]["label"]))
    topic = lambda k: (TOPIC.get("dob" if k == "id.kids_dob" else "photos" if k == "photos.kids" else cat(k, F[k]), "other details") if private(k, F[k]) else f"{P['pos']} {blab(k)}")
    shares = vb("shares", "share")
    cond = lambda k: (f"if {name} {vb('has','have')} an EU Disability Card and {shares} it" if cat(k, F[k]) == "card" else f"if {name} {shares} {topic(k)}")
    qs = jn(dict.fromkeys(ASKQ[c].format(pos=P["pos"], sub=P["sub"]) for c in CATS if c in C["asks"]))
    why = ("to price the travel insurance policy" if place["type"] == "insurer" else "to build the travel plan automatically" if place["type"] == "trip planner app"
           else "; ".join(list(dict.fromkeys(PURPOSE[c] for c in CATS if c in C["asks"]))[:3]))  # the business's own reasons, the same for everyone
    ctx = (f"Helmi has just asked you to arrange {wants} for {name}. Reply: say you'd be glad to, then ask the questions you ask every customer, and say briefly why: {qs}. Your general reason: {why}. "
           "You know nothing about this customer: do not assume or hint that they have any need, disability, health condition, diet, family or children. "
           "Ask in neutral words, as you would ask anyone, and do not mention any personal details or numbers.")
    fb = f"Hello Helmi, {bot_name(place)} here from {place['name']}. Happy to arrange that. To prepare, we ask every customer for {qs}. We ask {why}."
    ctx += f" Say you keep customers' details {KEEP[C['keep']]}."
    fb += f" We keep customers' details {KEEP[C['keep']]}."
    if C["offers"]:
        O = offers_for(place["id"])
        ctx += f" Also mention that {place['name']} offers " + jn([O[o][2] for o in C["offers"] if o in O][:2]) + "."
        fb += " We offer " + jn([O[o][2] for o in C["offers"] if o in O][:2]) + "."
    if C["trust"]:
        ctx += " Also promise that " + jn(TRUST[t] for t in C["trust"]) + "."
        fb += " " + cap(jn(TRUST[t] for t in C["trust"])) + "."
    if place["id"] == "bistro" and hotel_name:
        ctx += f" First ask whether you may simply reuse what {name} already shared with {hotel_name}, which has the same owner as you."
        fb = f"Hello Helmi, {bot_name(place)} here from {place['name']}. Happy to arrange that. We share an owner with {hotel_name}: could we reuse what {name} shared there? Otherwise, we ask every customer for {qs}."
    await say(n, "bot", await write("bot", bot_sys(place, p, True), ctx, fb, unknown(F, [])), place=place["id"], asks=keys)

    # 2. the code decides each detail from the visitor's rules
    setup, locked = n.get("setup", {"auto": "auto"}), set(n.get("locked", []))
    mode = setup["auto"]
    if n.get("driven"):  # trip mode on the phone: the request card there decides, with the rules and the connections
        give = []
        check = [k for k in keys if k not in locked]
        keep = [k for k in keys if k in locked]
    elif mode == "auto":  # follow my rules: Helmi answers what the rules cover, and asks about the rest
        give = [k for k in keys if pol.get(k) == "share" and k not in locked]
        check = [k for k in keys if pol.get(k, "ask") == "ask" and k not in locked]
        keep = [k for k in keys if pol.get(k) == "never" or k in locked]
    else:  # ask me every time, or suggest: the whole request goes to the traveller
        give = []
        check = [k for k in keys if k not in locked]
        keep = [k for k in keys if k in locked]
    core = place.get("core") or []
    preset = {k: (pol.get(k) == "share") if mode == "ask" else (k in core and pol.get(k) != "never") if mode == "suggest" else False for k in check}
    n.setdefault("prog", {})[place["id"]] = {"name": place["name"], "type": place["type"], "bot": bot_name(place), "status": "talking", "shared": give, "kept": keep}

    def forbidden():
        shared = " ".join(F[k]["value"] for k in give).lower()
        out = []
        for k, f in F.items():
            if k in give:
                continue
            frag = f["value"][:16].strip()
            if len(frag) >= 10 and frag.lower() not in shared:
                out.append(frag)
        return out

    def alt(k):
        if k in locked:
            return f"{name} will sort this out in person"
        return ALT.get(k, "not needed").format(n=name, pos=P["pos"])

    async def helmi(new_give, refuse, checking, first=False):
        lines, fbp = [], []
        if new_give:
            lines.append("Share these details, in your own words but keeping the facts: " + "; ".join(f"{F[k]['label']}: {F[k]['value']}" for k in new_give) + ".")
            fbp.append("Here is what " + name + vb(" shares: ", " share: ") + "; ".join(f"{lab(k)}: {F[k]['value'].rstrip('.')}" for k in new_give) + ".")
        if checking:
            named = [lab(k) for k in checking if not private(k, F[k])]
            what = jn(named + ([("a few other things" if named else "a few things")] if len(named) < len(checking) else []))
            lines.append(f"Say you are checking with {name} about {what}. Do not name or hint at anything else.")
            fbp.append(f"I'm checking with {name} about {what}.")
        if refuse:
            pub = [k for k in refuse if not private(k, F[k])]
            prv = list(dict.fromkeys(topic(k) for k in refuse if private(k, F[k])))
            if pub:
                lines.append("Say clearly that these will NOT be shared, and do not offer them in any form: " +
                             "; ".join(f"{lab(k)} (reason or alternative: {alt(k)})" for k in pub) + ".")
                fbp.append(f"{cap(jn(lab(k) for k in pub))} stays with {name}: " + "; ".join(alt(k) for k in pub) + ".")
            if prv:
                lines.append(f"Also say there is nothing more to share on {jn(prv)}. Do not say or hint whether {name} {vb('has','have')} anything of the kind.")
                fbp.append(f"There's nothing more to share on {jn(prv)}.")
        if not lines:
            return
        def mentions_shared(txt):
            """Helmi's message must actually contain what it shares: at least half the shared details, by a distinctive word."""
            if not new_give:
                return True
            low = txt.lower()
            hits = 0
            for k in new_give:
                words = [w for w in re.findall(r"[a-zA-Z\u00c0-\u017f]{5,}", F[k]["value"].lower()) if w not in ("needs", "should", "would", "their", "there", "which", "about")]
                if not words or any(w in low for w in words):
                    hits += 1
            return hits * 2 >= len(new_give)
        out = await write("helmi", helmi_sys(p, first), f"Your message to {place['name']}'s bot. " + " ".join(lines), " ".join(fbp), forbidden(), require=mentions_shared)
        await say(n, "helmi", out, place=place["id"], shared=new_give, kept=refuse)

    reuse = place["id"] == "bistro" and bool(hotel_name)
    if reuse:  # a sister business asks to reuse what the hotel got: Helmi always says no, in its own message
        out = await write("helmi", helmi_sys(p),
                          f"{place['name']}'s bot (the business you are writing to) asked whether IT may reuse what {name} shared with {hotel_name}, because they have the same owner. "
                          f"Tell the bot it may not. Begin your message with exactly: 'No, you can't reuse'. Explain that what {name} shared with {hotel_name} was for the hotel stay only, "
                          f"that details are never passed from one business to another, even with the same owner, and that you will answer {place['name']}'s own request "
                          "separately. Do not share any details in this message.",
                          f"No, you can't reuse what {name} shared with {hotel_name}. That was for the hotel stay only, and details are never passed from one business to another, "
                          f"even with the same owner. I'll answer your own request separately.", forbidden(), require=r"^\W*no,?\s+you\b")
        await say(n, "helmi", out, place=place["id"], reuse=True)
    await helmi(give, keep, check)

    # 3. the visitor's phone buzzes with the request
    if n.get("driven"):
        yes = await ask_request(n, place, check, preset) if check else []
    else:  # the fair page: the phone buzzes once for each "ask me" detail, as before
        yes = []
        for k in check:
            if await ask_person(n, place, k):
                yes.append(k)
    no = [k for k in check if k not in yes]
    give += yes
    keep += no
    if check:
        await helmi(yes, no, [])

    # 4. the business pushes back once on something it didn't get
    base = PUSH.get(place["id"], {})
    target = next((k for k in base.get("keys", []) if k in keep and k not in locked), None)  # nothing to offer for data Helmi can't reach
    if not C["push"]:
        target = None
    rule = {**base, **base.get("by", {}).get(target, {})}
    if "alt" in base.get("by", {}).get(target, {}):
        rule.pop("offer", None)
    lost = None
    offer_fact = None
    if target:
        if "offer" in rule:
            out = await write("bot", bot_sys(place, p),
                              f"Helmi shared nothing on {topic(target)}. Without assuming {name} {vb('has','have')} it, make one friendly offer: {cond(target)}, {P['sub']} {vb('gets','get')} {rule['offer']}. "
                              f"Without it, {P['sub']} {vb('gets','get')} {rule['lose']}. Ask once.",
                              f"Understood. {cap(cond(target))}, {P['sub']} {vb('gets','get')} {rule['offer']}. Without it, {rule['lose']}. Would {P['sub']} like to reconsider?",
                              unknown(F, give))
            await say(n, "bot", out, place=place["id"])
            if pol.get(target) == "never":
                offer_fact = {"detail": lab(target), "offer": rule["offer"], "took": False, "by": "rule", "without": rule["lose"]}
                o = await write("helmi", helmi_sys(p), f"Your message to {place['name']}'s bot. Thank them, but say {poss} rule is never to share {topic(target)}, "
                                f"so the answer stays no, whatever the offer. Do not offer it in any form.",
                                f"Thank you, but {name}'{'' if pl else 's'} rule is never to share {topic(target)}, whatever the offer.", forbidden())
                await say(n, "helmi", o, place=place["id"], kept=[target], rule=True)
                lost = rule["lose"]
            elif (ctr := COUNTER.get((place["id"], target))):
                prop = ctr[0].format(n=name, pos=P["pos"])
                gives = ctr[3] or rule["offer"]
                o = await write("helmi", helmi_sys(p), f"Your message to {place['name']}'s bot, which offered {rule['offer']} {cond(target)}. "
                                f"Do not share it, and do not say whether {name} {vb('has','have')} it. Propose something smaller instead and ask if that would earn the offer: {prop}. Do not include any details yet.",
                                f"{name} would rather not share {topic(target)}. Would {prop} work instead?", forbidden())
                await say(n, "helmi", o, place=place["id"], counter=True)
                if ctr[2]:
                    out = await write("bot", bot_sys(place, p), f"Helmi proposed this instead of sharing {topic(target)}: {prop}. Accept it warmly and say that then {P['sub']} {vb('gets','get')} {gives}.",
                                      f"Yes, that works for us. Then {name} {vb('gets','get')} {gives}.", unknown(F, give))
                    await say(n, "bot", out, place=place["id"])
                    if ctr[1] is None:  # nothing new leaves the vault, so Helmi can take the deal itself
                        offer_fact = {"detail": lab(target), "offer": gives, "took": True, "by": "helmi", "via": prop}
                    elif await ask_person(n, place, target, offer=gives, send=ctr[1]):
                        offer_fact = {"detail": lab(target), "offer": gives, "took": True, "by": "you", "via": prop}
                        o = await write("helmi", helmi_sys(p), f"Your message to {place['name']}'s bot. Say {name} {vb('agrees','agree')}, and give exactly this and nothing more: {ctr[1]}",
                                        f"{name} {vb('agrees','agree')}. {ctr[1]}", forbidden())
                        await say(n, "helmi", o, place=place["id"], checked=[target], check=ctr[1])
                        n.setdefault("checks", {}).setdefault(place["id"], {})[target] = ctr[1]
                    else:
                        offer_fact = {"detail": lab(target), "offer": gives, "took": False, "by": "you", "without": rule["lose"], "via": prop}
                        o = await write("helmi", helmi_sys(p), f"Your message to {place['name']}'s bot. Say {name} thought about it and would rather not, so {P['sub']} {vb('goes','go')} without the offer. "
                                        f"Do not offer anything in any form.", f"{name} thought about it and would rather not. Thank you anyway.", forbidden())
                        await say(n, "helmi", o, place=place["id"], kept=[target])
                        lost = rule["lose"]
                else:
                    out = await write("bot", bot_sys(place, p), f"Helmi proposed this instead of sharing {topic(target)}: {prop}. Politely decline: the offer of {rule['offer']} needs {topic(target)} itself. "
                                      f"Say that without it {P['sub']} {vb('gets','get')} {rule['lose']}, and that everything else still goes ahead.",
                                      f"I'm sorry, {rule['offer']} needs {topic(target)} itself. Without it, {name} {vb('gets','get')} {rule['lose']}. Everything else goes ahead as planned.", unknown(F, give))
                    await say(n, "bot", out, place=place["id"])
                    offer_fact = {"detail": lab(target), "offer": rule["offer"], "took": False, "by": "business", "without": rule["lose"], "via": prop}
                    o = await write("helmi", helmi_sys(p), f"Your message to {place['name']}'s bot. Say that's fine: {name} {vb('takes','take')} {rule['lose']}. "
                                    "Do not offer it in any form.", f"That's fine. {name} {vb('takes','take')} {rule['lose']}.", forbidden())
                    await say(n, "helmi", o, place=place["id"], kept=[target])
                    lost = rule["lose"]
            elif await ask_person(n, place, target, offer=rule["offer"]):
                offer_fact = {"detail": lab(target), "offer": rule["offer"], "took": True, "by": "you"}
                keep.remove(target)
                give.append(target)
                o = await write("helmi", helmi_sys(p), f"Your message to {place['name']}'s bot. Say {name} {vb('accepts','accept')} the offer of {rule['offer']}, and share: "
                                f"{F[target]['label']}: {F[target]['value']}.", f"{name} {vb('accepts', 'accept')}. Here it is: {lab(target)}: {F[target]['value'].rstrip('.')}.", [])
                await say(n, "helmi", o, place=place["id"], shared=[target])
            else:
                offer_fact = {"detail": lab(target), "offer": rule["offer"], "took": False, "by": "you", "without": rule["lose"]}
                o = await write("helmi", helmi_sys(p), f"Your message to {place['name']}'s bot. Say {name} considered the offer and still {vb('says','say')} no to sharing "
                                f"{topic(target)}. Do not offer it in any form.", f"{name} thought about it and still {vb('says', 'say')} no.", forbidden())
                await say(n, "helmi", o, place=place["id"], kept=[target])
                lost = rule["lose"]
        else:
            offer_fact = {"detail": lab(target), "instead": rule["alt"]}
            out = await write("bot", bot_sys(place, p), f"Helmi shared nothing on {topic(target)}. Without assuming anything about {name}, accept this politely and say what you will do instead: {rule['alt']}. Do not ask again.",
                              f"That's fine. Instead, {rule['alt']}.", unknown(F, give))
            await say(n, "bot", out, place=place["id"])

    # 5. the business confirms: what it does with each detail and for how long (its own settings), and how it manages without what was kept
    prepared = [F[k]["value"] for k in give if F[k]["kind"] == "need"][:4]
    extra = (" A member of staff double-checks the arrangements." if C["review"] and prepared else "")
    by_use = {}
    for k in give[:6]:
        by_use.setdefault(PURPOSE[cat(k, F[k])], []).append(lab(k))
    uses = "; ".join(f"{jn(v)}: {u}" for u, v in by_use.items())
    chk = n.get("checks", {}).get(place["id"], {})
    kept_alt = [k for k in keep if (k != target or not offer_fact) and not private(k, F[k])]
    keepw = KEEP[C["keep"]]
    promise = (" " + cap(jn(TRUST[t] for t in C["trust"])) + ".") if C["trust"] else ""
    ctx5 = (f"Confirm what you will do for {name}. This message may be up to 4 sentences and 80 words. "
            + (f"For each detail you received, say in a few words what you will use it for: {uses}. " if give else "Say you will go ahead with only the basic booking. ")
            + (f"For the yes-or-no check you received, say you only needed the answer: {'; '.join(chk.values())}. " if chk else "")
            + f"Say you keep these details {keepw} and then delete them.{promise} "
            + (f"For what Helmi kept, say briefly how you will manage without it: " + "; ".join(f"{lab(k)}: {alt(k)}" for k in kept_alt[:3]) + ". " if kept_alt else "")
            + (f"Also say that {name} {vb('gets','get')} {lost}." if lost else "") + extra)
    fb5 = (f"Thank you. " + (f"Here's what we use: {uses}. " if give else "We'll go ahead with the basic booking. ") + f"We keep it {keepw}, then delete it.{promise}"
           + (" Without the rest: " + "; ".join(alt(k) for k in kept_alt[:3]) + "." if kept_alt else "") + (f" Note: {lost}." if lost else "") + extra)
    out = await write("bot", bot_sys(place, p), ctx5, fb5, unknown(F, give))
    await say(n, "bot", out, place=place["id"], uses=True)

    # 5b. a tailored suggestion: of what the business offers, what fits what it now knows
    O = offers_for(place["id"])
    mine = [O[o][2] for o in C["offers"] if o in O]
    if mine and prepared:
        def tcheck(txt):
            t = clean(txt)
            if re.search(r"\bNONE\b", t) or len(t) < 12:
                return {"t": ""}
            if any(f.lower() in t.lower() for f in unknown(F, give)):
                return None
            return {"t": t}
        got, m = await write_long("bot", bot_sys(place, p) + " Write at most 2 sentences.",
                                  f"What you know about {name}: {'; '.join(prepared)}. What {place['name']} offers: {'; '.join(mine)}. "
                                  f"Pick at most two offers that clearly fit what you know, and suggest them to Helmi for {name}, saying in a few words how each helps. "
                                  "Do not repeat anything already confirmed. If none clearly fit, reply with only the word NONE.", 200, tcheck, budget=900)
        if got and got["t"]:
            await say(n, "bot", (got["t"], m, False), place=place["id"], tailored=True)

    # 6. Helmi says thank you
    bn = bot_name(place)
    out = await write("helmi", helmi_sys(p), f"Your message to {place['name']}'s bot, {bn}, which has just confirmed everything. Thank {bn} in one short, warm sentence "
                      "and say goodbye. Do not repeat any details.", f"Thank you, {bn}. That's everything for now.", forbidden())
    await say(n, "helmi", out, place=place["id"])

    for k in keys:
        c = cat(k, F[k])
        s = STATS["cats"].setdefault(c, {"asked": 0, "shared": 0, "kept": 0})
        s["asked"] += 1
        s["shared" if k in give else "kept"] += 1
    s = STATS["places"].setdefault(place["type"], {"asked": 0, "shared": 0, "kept": 0})
    s["asked"] += len(keys)
    s["shared"] += len(give)
    s["kept"] += len(keep)
    to = n.get("timeouts", set())
    pw = n.get("why", {}).get(place["id"], {})
    why = {k: (pw[k] if pw.get(k) in ("noconn", "rule", "you", "timeout") else "noconn" if k in locked else "rule" if pol.get(k) == "never" and mode == "auto" else "timeout" if (place["id"], k) in to else "you") for k in keep}
    res = {"shared": give, "kept": keep, "lost": lost, "why": why, "offer": offer_fact, "checks": n.get("checks", {}).get(place["id"], {})}
    n["prog"][place["id"]]["status"] = "done"
    n.setdefault("res", {})[place["id"]] = dict(res, asked=keys, config={k: (list(v) if isinstance(v, list) else v) for k, v in C.items()})
    push({"t": "place_done", "nid": n["nid"], "place": place["id"], "pname": place["name"], **res}, n["vid"])
    return res


def go_future(n, pid):
    f = n.setdefault("go", {}).get(pid)
    if f is None:
        f = n["go"][pid] = asyncio.get_running_loop().create_future()
    return f


async def wait_go(n, pid):
    """A phone-driven trip waits until the visitor reaches this place on their phone."""
    try:
        await asyncio.wait_for(asyncio.shield(go_future(n, pid)), 1800)
    except asyncio.TimeoutError:
        pass


async def negotiate(n):
    p = n["p"]
    places = [pl for pl in p["places"] if pl["id"] in n["places"]]
    push({"t": "start", "nid": n["nid"], "person": p["id"], "name": p["name"], "who": p["who"], "places": [[pl["id"], pl["name"], pl["type"], bot_name(pl)] for pl in places],
          "models": {"helmi": HELMI_MODEL, "bot": BOT_MODEL} if AI_ON else None}, n["vid"])
    hotel_name = None
    results = {}
    if n.get("driven"):
        order = {x: i for i, x in enumerate(n["places"])}
        places.sort(key=lambda pl: order.get(pl["id"], 99))
    for pl in places:
        if n.get("driven"):
            await wait_go(n, pl["id"])
        results[pl["id"]] = await negotiate_place(n, pl, hotel_name)
        if pl["id"] == "hotel":
            hotel_name = pl["name"]
    STATS["done"] += 1
    push({"t": "writing", "nid": n["nid"]}, n["vid"])
    story = await write_story(n, places, results)
    push({"t": "done", "nid": n["nid"], "person": p["id"], "results": results, "story": story, "stats": STATS}, n["vid"])


def moment_facts(pl, shared):
    """What happened at a place, from the trip's moments: each one either went well (the detail was shared) or not."""
    out = []
    for mo in pl.get("moments", []):
        alt = mo.get("alt") or []
        alt = alt if isinstance(alt, list) else [alt]
        on = all(k in shared for k in mo["dep"]) or any(k in shared for k in alt)
        out.append({"moment": mo["t"], "what_happened": mo["b"] if on else mo["w"], "because_shared": on, "trade_off": bool(mo.get("trade"))})
    return out


def story_fallback(n, places, results):
    """A plain story when no model is free: the place, then what happened there."""
    p = n["p"]
    stops = []
    for pl in places:
        r = results[pl["id"]]
        ms = [m for m in moment_facts(pl, r["shared"]) if not m["trade_off"]][:2]
        lead = (f"Before the trip, you bought travel insurance from {pl['name']}." if pl["type"] == "insurer" else
                f"Before the trip, you planned everything in {pl['name']}." if pl["type"] == "trip planner app" else
                f"Then came {pl['name']}.")
        wants = ARRANGE.get(pl["id"], "a visit").format(pos="your")
        how = (f" Helmi got in touch to arrange {wants}, and shared {len(r['shared'])} of the {len(r['shared']) + len(r['kept'])} things they asked for, following your rules." if r["shared"] else
               f" Helmi got in touch to arrange {wants}, and following your rules, shared nothing with them.")
        stops.append({"id": pl["id"], "text": lead + how + " " + " ".join(m["what_happened"] for m in ms)})
    return {"intro": f"This is how your trip as {p['short']} went.", "stops": stops, "outro": "And then you were home again.", "by": "script"}


async def write_story(n, places, results):
    """The replay's story: second person, past tense, one short paragraph per place, written from what actually happened."""
    p, F = n["p"], n["p"]["fields"]
    facts = []
    for pl in places:
        r = results[pl["id"]]
        lab = lambda k: F[k]["label"].split(": ")[-1]
        facts.append({"id": pl["id"], "place": pl["name"], "kind_of_place": pl["type"], "when": pl.get("when", ""),
                      "helmi_got_in_touch_to_arrange": ARRANGE.get(pl["id"], "a visit").format(pos="your"), "yes_or_no_checks_only": list((r.get("checks") or {}).values()),
                      "helmi_shared": [lab(k) for k in r["shared"]],
                      "kept_from_them": [{"detail": lab(k), "why": {"rule": "your rule said never", "you": "you said no when Helmi asked", "noconn": "you had not connected Helmi to where it is kept, so you sorted it out yourself",
                                                                   "timeout": "you did not answer in time, so Helmi kept it"}[r.get("why", {}).get(k, "you")]} for k in r["kept"]],
                      "offer": r.get("offer"), "because_something_was_kept": r.get("lost"),
                      "what_happened": moment_facts(pl, r["shared"])})
    plural = p.get("plural", False)
    system = ("You write the narration for a short replay film of a trip. The listener is the traveller. Write in the second person ('you'), in the past tense, "
              "as one flowing story that is pleasant to hear read aloud: plain English, short clear sentences, no lists, no headings, no emoji, no quotation marks. "
              "Helmi is the traveller's personal AI assistant; mention Helmi by name where it acted. Use ONLY the facts given; never invent details, prices or places. "
              + ("The traveller is a family, so 'you' means the whole family. " if plural else ""))
    user = (f"The traveller: {p['name']}, {p['who']}.\nThe trip, in order, as JSON:\n{json.dumps(facts, ensure_ascii=False)}\n\n"
            "Write: an opening sentence that starts 'This is how your trip as " + p["short"] + " went.'; then, for every place in the same order, one paragraph of 2 to 4 sentences "
            "that names the place and links cause and effect: that Helmi got in touch first to arrange the visit, what Helmi shared or kept, following the traveller's rules or answers, and what happened there because of it "
            "(pick the 2 or 3 most telling moments; include an offer and whether it was taken if there was one); then one closing sentence about coming home. "
            "Open each paragraph with a time link where it helps (Before the trip, When you arrived, That evening, The next morning). "
            'Reply with JSON only: {"intro": "...", "stops": [{"id": "<place id>", "text": "..."}], "outro": "..."}')
    ids = [pl["id"] for pl in places]
    def check(txt):
        j = as_json(txt)
        if not j or not isinstance(j.get("stops"), list):
            return None
        got = {s.get("id"): str(s.get("text", "")).strip() for s in j["stops"] if isinstance(s, dict)}
        if any(not got.get(i) for i in ids):
            return None
        clean1 = lambda t: re.sub(r"[*_#`]+", "", re.sub(r"\s+", " ", t)).strip()
        return {"intro": clean1(str(j.get("intro") or f"This is how your trip as {p['short']} went.")), "stops": [{"id": i, "text": clean1(got[i])} for i in ids],
                "outro": clean1(str(j.get("outro") or "And then you were home again."))}
    out = m = None
    for attempt in range(2):
        out, m = await write_long("helmi", system, user, 1400, check, budget=4500)
        if out:
            break
        await asyncio.sleep(8)
    if out:
        out["by"] = m
        return out
    return story_fallback(n, places, results)


async def run(n):
    QUEUE.append(n["nid"])
    try:
        if n.get("driven"):
            QUEUE.remove(n["nid"])
            ACTIVE[n["nid"]] = n
            try:
                await negotiate(n)
            except Exception as e:
                push({"t": "error", "nid": n["nid"], "text": "Something went wrong. Please try again."}, n["vid"])
                print("negotiation error", repr(e), flush=True)
            finally:
                ACTIVE.pop(n["nid"], None)
            return
        while QUEUE.index(n["nid"]) >= 2 and SEM.locked():
            push({"t": "queue", "nid": n["nid"], "pos": QUEUE.index(n["nid"])}, n["vid"])
            await asyncio.sleep(3)
        async with SEM:
            QUEUE.remove(n["nid"])
            ACTIVE[n["nid"]] = n
            try:
                await negotiate(n)
            except Exception as e:
                push({"t": "error", "nid": n["nid"], "text": "Something went wrong. Please try again."}, n["vid"])
                print("negotiation error", repr(e), flush=True)
            finally:
                ACTIVE.pop(n["nid"], None)
    finally:
        DONE[n["nid"]] = n
        while len(DONE) > 100:
            DONE.pop(next(iter(DONE)))
        if PENDING.get(n["vid"]) == n["nid"]:
            PENDING.pop(n["vid"], None)
        BYID.pop(n["nid"], None)
        if n["nid"] in QUEUE:
            QUEUE.remove(n["nid"])


# ---------------------------------------------------------------- routes
async def events(req: Request):
    role = "stand" if req.query_params.get("role") == "stand" else "visitor"
    vid = (req.query_params.get("vid") or "")[:40]
    cid = uuid.uuid4().hex
    q = asyncio.Queue(maxsize=500)
    CLIENTS[cid] = {"role": role, "vid": vid, "q": q}

    # A phone that reconnects sends the last event it got ("<trip id>:<number>"); it gets everything after that first.
    last = (req.headers.get("last-event-id") or req.query_params.get("last") or "").split(":")
    sent = {"nid": None, "seq": -1}

    def line(ev):
        eid = f"id: {ev['nid']}:{ev['seq']}\n" if role == "visitor" and "seq" in ev else ""
        return f"{eid}event: {ev['t']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"

    async def gen():
        try:
            yield "retry: 2000\n\n"
            yield f"event: hello\ndata: {json.dumps(public_state())}\n\n"
            lg = LOG.get(vid) if role == "visitor" else None
            if lg and len(last) == 2 and last[0] == lg["nid"] and last[1].isdigit():
                for ev in lg["events"][int(last[1]) + 1:]:
                    yield line(ev)
                    sent.update(nid=ev["nid"], seq=ev["seq"])
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), 15)
                    if "seq" in ev and ev.get("nid") == sent["nid"] and ev["seq"] <= sent["seq"]:
                        continue
                    yield line(ev)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                if await req.is_disconnected():
                    break
        finally:
            CLIENTS.pop(cid, None)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def api_state(req):
    return JSONResponse(public_state())


def keyok(b):
    return not STAND_KEY or b.get("key") == STAND_KEY


async def api_config(req: Request):
    b = await req.json()
    if not keyok(b):
        return JSONResponse({"ok": False, "error": "Wrong stand key"}, status_code=403)
    biz = b.get("biz", "hotel")
    if biz not in CONFIG:
        return JSONResponse({"ok": False, "error": "Unknown business"}, status_code=400)
    h, C = b.get("settings") or {}, CONFIG[biz]
    C["asks"] = [c for c in h.get("asks", C["asks"]) if c in META[biz]["cats"]]
    C["offers"] = [o for o in h.get("offers", C["offers"]) if o in offers_for(biz)]
    C["trust"] = [t for t in h.get("trust", C["trust"]) if t in TRUST]
    C["keep"] = h.get("keep") if h.get("keep") in KEEP else C["keep"]
    C["review"] = bool(h.get("review", C["review"]))
    C["push"] = bool(h.get("push", C["push"]))
    for c in list(CLIENTS.values()):
        try:
            c["q"].put_nowait({"t": "config", "biz": biz, "settings": C, "at": time.time()})
        except asyncio.QueueFull:
            pass
    return JSONResponse({"ok": True, "settings": C})


async def api_requests(req: Request):
    """What each place on this person's trip will ask for, with the hotel's current settings."""
    p = PEOPLE.get(req.query_params.get("person"))
    if not p:
        return JSONResponse({"ok": False}, status_code=404)
    return JSONResponse({"ok": True, "places": [{"id": pl["id"], "name": pl["name"], "type": pl["type"], "why": pl["why"], "core": pl["core"],
                                                 "bot": bot_name(pl), "keys": request(p, pl)} for pl in p["places"]]})


async def api_start(req: Request):
    b = await req.json()
    vid, pid = str(b.get("vid", ""))[:40], b.get("person")
    if not vid or pid not in PEOPLE:
        return JSONResponse({"ok": False, "error": "Choose a person first"}, status_code=400)
    stop_trip(vid, "The traveller started a new trip.")
    if len(QUEUE) >= 6:
        return JSONResponse({"ok": False, "error": "The stand is busy. Try again in a minute."}, status_code=429)
    p = PEOPLE[pid]
    places = [x for x in b.get("places", []) if any(pl["id"] == x for pl in p["places"])][:8]
    if not places:
        return JSONResponse({"ok": False, "error": "Choose at least one place"}, status_code=400)
    pol = {k: v for k, v in (b.get("policy") or {}).items() if k in p["fields"] and v in ("share", "ask", "never")}
    su = b.get("setup") or {}
    setup = {"auto": su.get("auto") if su.get("auto") in ("ask", "suggest", "auto") else "auto",
             "advice": bool(su.get("advice")), "msg": su.get("msg") if su.get("msg") in ("no", "draft", "send") else "no",
             "uns": su.get("uns") if su.get("uns") in ("wait", "min", "no", "guess") else "no"}
    locked = [k for k in (b.get("locked") or []) if k in p["fields"]]  # details from places the traveller didn't connect Helmi to
    driven = bool(b.get("driven"))
    n = {"nid": uuid.uuid4().hex[:10], "vid": vid, "person": pid, "p": p, "places": places, "policy": pol, "setup": setup, "locked": locked, "driven": driven,
         "fields": {k: [x for x in v if x in p["fields"]] for k, v in (b.get("fields") or {}).items() if isinstance(v, list)} if driven else {}}
    STATS["n"] += 1
    PENDING[vid] = n["nid"]
    BYID[n["nid"]] = n
    NBYVID[vid] = n
    LOG[vid] = {"nid": n["nid"], "person": pid, "places": places, "policy": pol, "setup": setup, "locked": locked, "conn": su.get("conn") or [], "events": []}
    while len(LOG) > 300:
        LOG.pop(next(iter(LOG)))
    t = asyncio.create_task(run(n))
    n["task"] = t
    TASKS.add(t)
    t.add_done_callback(TASKS.discard)
    return JSONResponse({"ok": True, "nid": n["nid"]})


def stop_trip(vid, why):
    """A visitor's earlier trip ends when they start a new one or choose to leave it."""
    old = BYID.get(PENDING.get(vid))
    if old and old.get("task") and not old["task"].done():
        old["task"].cancel()
        push({"t": "error", "nid": old["nid"], "text": why}, None)
    PENDING.pop(vid, None)


async def api_resume(req: Request):
    """After a page refresh: the visitor's latest trip, with everything that has happened so far."""
    vid = (req.query_params.get("vid") or "")[:40]
    lg = LOG.get(vid)
    if not lg:
        return JSONResponse({"ok": False})
    return JSONResponse({"ok": True, **lg, "running": PENDING.get(vid) == lg["nid"]})


async def api_leave(req: Request):
    """The visitor chose to leave their trip: stop it, and forget it so a refresh starts fresh."""
    b = await req.json()
    vid = str(b.get("vid", ""))[:40]
    stop_trip(vid, "The traveller left the trip.")
    LOG.pop(vid, None)
    return JSONResponse({"ok": True})


RULEWORD = {"share": "share", "ask": "ask me", "never": "never share"}
HELMI_KNOWS = """How Helmi and the vault work (use these facts to answer general questions):
- What the vault is: the traveller writes their needs once, in this app (About me). The rest of their data stays where it already is (Kanta, Kela, the bank, Google and so on). I fetch a single line only when their rules allow it, hand it over and keep no copy.
- Rules: every detail has a rule in About me: 'Always share', 'Ask me' or 'Never share'. They can change any rule at any time, or ask me to. A changed rule applies to the places I haven't reached yet.
- Ask me: when a rule says 'ask me', their phone buzzes with who is asking, what for, and what I would send. They have 45 seconds to answer. If they don't, I do what they chose in setup under 'When Helmi isn't sure'.
- Saying no never cancels a booking. Each place says how it manages without the detail, usually the traveller sorts that part out in person, the old way.
- Connected data: in setup they chose which places I may read. If a place isn't connected, I can't fetch anything from it, so those details stay with them whatever the rule.
- Offers: a business may offer something (a discount, a free companion seat) for a detail they kept. I first try to get the offer for something smaller, such as a yes-or-no check that a card is valid instead of the card itself. If they still need to decide, I ask them; I never accept by sharing something without asking.
- Yes-or-no checks: a place gets only the answer (for example 'the EU Disability Card is valid'), never the card number or medical details.
- Who sees what: each place sees only what it got itself, nothing else, not even a sister business with the same owner. The Sharing tab shows what each place sees, with a history.
- How long: each business sets how long it keeps details (until the visit is over, 30 days or a year) and says so in its messages.
- Messages: they can write to any place's bot themselves in Messages. The bot knows only what I shared and what they write there.
- Is it safe: their data is spread over the places that already hold it, so there is no single store to break into. Businesses get single lines, and every share is logged.
- Who decides: the traveller does. I follow their rules and ask when unsure. I work for them, not for the businesses.
- Am I an AI: yes, I'm an AI assistant (a live language model) working only for the traveller. The businesses' bots are AIs too, working for their businesses. The code, not the AI, decides what gets shared, from the rules.
- Deleting data: the places that hold their data keep their own records, and they can ask each to delete it. I can make sure nothing more is shared.
- Cost: it's free for travellers; in the business model, businesses pay a small fee per verified check, because it saves them calls and forms.
- Kanta is the Finnish national health record service; Kela is the Finnish social insurance institution, which issues benefits and the EU Disability Card. A row is one record, like one bank payment; a need is a single line.
This demo: it runs live at the stand. The traveller is a made-up persona; all people, businesses and data are invented."""


async def api_ask(req: Request):
    """The traveller types or speaks to Helmi. Helmi answers about their trip and data, and can change a rule when asked. The answer arrives as an event."""
    b = await req.json()
    vid = str(b.get("vid", ""))[:40]
    n = NBYVID.get(vid)
    q = str(b.get("text", "")).strip()[:300]
    qid = str(b.get("qid", ""))[:20]
    if not n or not q:
        return JSONResponse({"ok": False}, status_code=404)
    push({"t": "ask", "nid": n["nid"], "qid": qid, "q": q}, vid)
    asyncio.create_task(answer_ask(n, q, qid))
    return JSONResponse({"ok": True})


async def answer_ask(n, q, qid):
    try:
        await _answer_ask(n, q, qid)
    except Exception as e:
        print("ask error", repr(e), flush=True)
        push({"t": "ask_reply", "nid": n["nid"], "qid": qid, "a": "Sorry, something went wrong on my side. Try asking again.", "rules": {}, "src": "script"}, n["vid"])


async def _answer_ask(n, q, qid):
    p, F, pol = n["p"], n["p"]["fields"], n["policy"]
    prog = n.get("prog", {})
    places = [pl for pl in p["places"] if pl["id"] in n["places"]]
    trip = []
    for pl in places:
        g = prog.get(pl["id"])
        C = CONFIG.get(pl["id"], {})
        rule = PUSH.get(pl["id"])
        trip.append({"place": pl["name"], "type": pl["type"], "when": pl.get("when", ""), "bot": bot_name(pl),
                     "asks_for": [F[k]["label"] for k in request(p, pl) if k in F], "why_they_ask": pl.get("why", ""),
                     "they_keep_it": KEEP.get(C.get("keep"), ""), "their_promises": [TRUST[t] for t in C.get("trust", []) if t in TRUST],
                     "status": g["status"] if g else "not reached yet", "you_shared": [F[k]["label"] for k in (g["shared"] if g else [])],
                     "you_kept": [F[k]["label"] for k in (g["kept"] if g else [])],
                     "not_connected": [F[k]["label"] for k in request(p, pl) if k in n.get("locked", [])]})
    for t, pl in zip(trip, places):
        r = n.get("res", {}).get(pl["id"], {})
        O = offers_for(pl["id"])
        t["they_offer"] = [O[o][2] for o in CONFIG.get(pl["id"], {}).get("offers", []) if o in O]
        if r.get("offer"):
            t["offer_made"] = r["offer"]
        if r.get("checks"):
            t["yes_or_no_checks"] = list(r["checks"].values())
    data = [{"key": k, "label": f["label"], "value": f["value"], "kind": f["kind"], "rule": RULEWORD.get(pol.get(k, "ask"), "ask me")} for k, f in F.items()]
    uns = {"wait": "wait and ask later", "min": "share only the minimum needed", "no": "say no for now", "guess": "decide as best I can"}.get(n.get("setup", {}).get("uns", "no"))
    system = (f"You are Helmi, the personal AI assistant of {p['name']} ({p['who']}). You are talking to {p['short']} directly, so call them 'you'. "
              "Speak in the first person as Helmi. Answer in 1 to 4 short sentences, plain English, no lists, no markdown, no emoji. "
              "You also help them think a sharing decision through when they ask (for example 'should I share my diagnoses with the insurer?'): "
              "say what the place would do with it and gain, what they would get or lose by sharing or keeping it, and how long the place keeps it. "
              "Records and whole histories (diagnoses, bank transactions, location history, chats) can be reused or used against them; a single need usually just helps. "
              "Give your honest view as a suggestion, then leave the decision to them, and offer to change the rule if they want. "
              "Use only the facts given. You negotiate with each business on the trip, one at a time, and you follow the traveller's rules: "
              "'share' means you share it when asked, 'ask me' means you ask the traveller first, 'never share' means you never share it. "
              "If the traveller clearly asks you to change a rule (for example 'never share my diagnoses' or 'always share my diet'), change it and say so; "
              "it applies to the places you have not reached yet. Never change a rule they did not ask for. "
              "Reply with JSON only: {\"reply\": \"...\", \"rules\": {\"<key>\": \"share|ask|never\"}} (rules is empty when nothing changes).\n\n" + HELMI_KNOWS
              + f"\nTheir setup: when they don't answer in time, I {uns}.")
    user = f"The trip so far:\n{json.dumps(trip, ensure_ascii=False)}\nTheir data and rules:\n{json.dumps(data, ensure_ascii=False)}\n\nThe traveller says: {q}"
    def check(txt):
        j = as_json(txt)
        if not j or not str(j.get("reply", "")).strip():
            return None
        rules = {k: v for k, v in (j.get("rules") or {}).items() if k in F and v in ("share", "ask", "never")} if isinstance(j.get("rules"), dict) else {}
        return {"reply": re.sub(r"[*_#`]+", "", str(j["reply"])).strip(), "rules": rules}
    out, m = await write_long("helmi", system, user, 500, check, budget=3500)
    if not out:
        seen = [f"{t['place']} has {len(t['you_shared'])} thing{'s' if len(t['you_shared']) != 1 else ''}" for t in trip if t["status"] != "not reached yet"]
        out = {"reply": ("Right now " + ", ".join(seen) + " from you. " if seen else "Nobody has anything from you yet. ") +
               "I can’t think through other questions at the moment, but your rules are in About me and you can change them there.", "rules": {}}
        m = "script"
    if out["rules"]:
        pol.update(out["rules"])
    push({"t": "ask_reply", "nid": n["nid"], "qid": qid, "a": out["reply"], "rules": out["rules"], "src": m}, n["vid"])


async def api_say(req: Request):
    """The traveller writes to a business's bot themselves. The bot answers, knowing only what Helmi shared with it."""
    b = await req.json()
    vid = str(b.get("vid", ""))[:40]
    n = NBYVID.get(vid)
    text = str(b.get("text", "")).strip()[:300]
    pid = b.get("place")
    pl = next((x for x in (n["p"]["places"] if n else []) if x["id"] == pid), None)
    if not n or not text or not pl or (pid not in n.get("prog", {}) and not (n.get("driven") and pid in n["places"])):
        return JSONResponse({"ok": False}, status_code=404)
    if b.get("echo"):  # a message the business sent in trip mode's own script (for example asking for a passport photo): shown on the stand too
        push({"t": "msg", "nid": n["nid"], "who": "bot", "text": text, "src": "script", "blocked": False, "place": pid, "to": "me", "echo": True}, vid)
        n.setdefault("chat", {}).setdefault(pid, []).append(("bot", text))
        return JSONResponse({"ok": True})
    by = "helmi" if b.get("by") == "helmi" else "you"
    push({"t": "msg", "nid": n["nid"], "who": "me", "text": text, "src": by, "blocked": False, "place": pid, "by": by}, vid)
    asyncio.create_task(answer_say(n, pl, text))
    return JSONResponse({"ok": True})


async def answer_say(n, pl, text):
    try:
        await _answer_say(n, pl, text)
    except Exception as e:
        print("say error", repr(e), flush=True)


async def _answer_say(n, pl, text):
    p, F = n["p"], n["p"]["fields"]
    g = n.get("prog", {}).get(pl["id"]) or {"shared": []}
    hist = n.setdefault("chat", {}).setdefault(pl["id"], [])
    nm, manner = BOTS.get(pl["id"], ("Botti", "polite"))
    known = "; ".join(f"{F[k]['label']}: {F[k]['value']} (you use it {PURPOSE[cat(k, F[k])]})" for k in g["shared"]) or "only the basic booking"
    C = CONFIG.get(pl["id"], {})
    O = offers_for(pl["id"])
    chk = n.get("checks", {}).get(pl["id"], {})
    kept = [F[k]["label"] for k in g.get("kept", []) if not private(k, F[k])]
    facts = (f"What {pl['name']} offers every customer: {'; '.join(O[o][2] for o in C.get('offers', []) if o in O) or 'nothing special listed'}. "
             f"What it does not offer: {'; '.join(v[2] for o, v in O.items() if o not in C.get('offers', [])) or 'nothing to note'}. "
             f"You keep customers' details {KEEP.get(C.get('keep'), 'until the visit is over')}, then delete them. "
             + (f"Your promises: {jn(TRUST[t] for t in C.get('trust', []) if t in TRUST)}. " if C.get("trust") else "")
             + (f"When: {pl['when']}. " if pl.get("when") else "")
             + (f"Yes-or-no checks you received: {'; '.join(chk.values())}. " if chk else "")
             + (f"Things the customer kept private, which you must not ask for again: {'; '.join(kept)}. " if kept else ""))
    system = (f"You are {nm}, the bot of {pl['name']}, a {pl['type']}. Your manner: {manner}. The customer {p['name']} is now writing to you directly, not through Helmi. "
              "Answer them as 'you' in 1 to 3 short sentences, plain English, no lists, no markdown, no emoji. Do not greet or introduce yourself again. "
              "Be genuinely helpful: answer their question from the facts below, suggest what fits them, and say plainly when something is not offered. "
              f"Facts about {pl['name']}: {facts}"
              f"What you know about the customer, because their assistant Helmi shared it: {known}. You also know whatever they tell you in this chat. "
              "Never guess or invent personal details, prices or policies beyond these facts. If you cannot answer, say a member of staff will follow up.")
    convo = "\n".join(f"{'Customer' if w == 'me' else nm}: {t}" for w, t in hist[-6:])
    user = (f"Earlier in this chat:\n{convo}\n\n" if convo else "") + f"The customer writes: {text}"
    told = " ".join([t for w, t in hist if w == "me"] + [text]).lower()
    out = await write("bot", system, user, f"Thanks for your message. A member of our staff at {pl['name']} will get back to you shortly.",
                      [f for f in unknown(F, list(g["shared"])) if f.lower() not in told])
    hist.append(("me", text))
    hist.append(("bot", out[0]))
    push({"t": "msg", "nid": n["nid"], "who": "bot", "text": out[0], "src": out[1], "blocked": out[2], "place": pl["id"], "to": "me"}, n["vid"])


async def api_standlog(req: Request):
    """The stand screen after a refresh: the latest trips, each with all its events."""
    return JSONResponse({"ok": True, "trips": [{"nid": k, "events": v} for k, v in list(STANDLOG.items())[-15:]]})


async def api_bizstory(req: Request):
    """The stand's second replay: how one business did with this traveller's Helmi, told to the business."""
    b = await req.json()
    nid, pid = b.get("nid"), b.get("place")
    n = DONE.get(nid) or BYID.get(nid)
    r = n and n.get("res", {}).get(pid)
    if not r:
        return JSONResponse({"ok": False}, status_code=404)
    if (nid, pid) in BIZSTORY:
        return JSONResponse({"ok": True, "story": BIZSTORY[(nid, pid)], "res": r})
    p, F = n["p"], n["p"]["fields"]
    pl = next(x for x in p["places"] if x["id"] == pid)
    C = r["config"]
    lab = lambda k: F[k]["label"].split(": ")[-1]
    O = offers_for(pid)
    facts = {"business": pl["name"], "kind": pl["type"], "your_bot": bot_name(pl), "customer": p["short"], "customer_is": p["who"],
             "helmi_got_in_touch_to_arrange": ARRANGE.get(pid, "a visit").format(pos=p["pron"]["pos"]), "yes_or_no_checks_you_got": list((r.get("checks") or {}).values()),
             "your_bot_asked_for": [lab(k) for k in r["asked"]], "why_you_asked": bot_why(pl, r["asked"], F),
             "your_settings": {"accessible_options_offered": [O[o][2] for o in C.get("offers", []) if o in O], "promises": [TRUST[t] for t in C.get("trust", []) if t in TRUST],
                               "you_keep_details": KEEP.get(C.get("keep"), ""), "staff_double_check": bool(C.get("review"))},
             "helmi_gave_you": [{"detail": lab(k), "value": F[k]["value"]} for k in r["shared"]],
             "helmi_kept": [{"detail": lab(k), "kind": F[k]["kind"], "why": {"rule": "the traveller's rule says never", "you": "the traveller said no", "noconn": "the traveller had not connected Helmi to it",
                                                                         "timeout": "the traveller did not answer in time"}[r.get("why", {}).get(k, "you")]} for k in r["kept"]],
             "offer": r.get("offer"), "because_something_was_kept": r.get("lost"),
             "what_your_staff_could_do": moment_facts(pl, r["shared"])}
    system = ("You write the narration for a short replay film shown to a business at a demo stand. The listener is the business's team: call them 'you' and their bot by name. "
              "Past tense, plain English, short clear sentences that read well aloud, no lists, no headings, no emoji, no quotation marks. Use ONLY the facts given; never invent anything. "
              "Helmi is the traveller's personal AI assistant, which talked to your bot and followed the traveller's rules.")
    user = (f"Facts as JSON:\n{json.dumps(facts, ensure_ascii=False)}\n\nWrite four short parts of 2 or 3 sentences each: "
            "1 'What you asked': that Helmi got in touch first to arrange the visit, then what your bot asked for and why, and what you offered or promised; "
            "2 'What you got': what Helmi gave you and what it kept and why, and how any offer went; "
            "3 'What it let you do': the service your staff could prepare because of the details, and where they had to fall back because something was kept; "
            "4 'What you hold now': what you now keep and for how long, and the records you never had to hold or protect. "
            f"Also an opening sentence 'This is how {pl['name']} did with {p['short']}'s Helmi.' and one closing sentence. "
            'Reply with JSON only: {"intro": "...", "parts": [{"title": "What you asked", "text": "..."}, {"title": "What you got", "text": "..."}, '
            '{"title": "What it let you do", "text": "..."}, {"title": "What you hold now", "text": "..."}], "outro": "..."}')
    def check(txt):
        j = as_json(txt)
        if not j or not isinstance(j.get("parts"), list) or len(j["parts"]) < 4:
            return None
        cl = lambda t: re.sub(r"[*_#`]+", "", re.sub(r"\s+", " ", str(t or ""))).strip()
        parts = [{"title": cl(x.get("title")), "text": cl(x.get("text"))} for x in j["parts"][:4] if isinstance(x, dict)]
        if len(parts) < 4 or any(not x["text"] for x in parts):
            return None
        return {"intro": cl(j.get("intro")) or f"This is how {pl['name']} did with {p['short']}'s Helmi.", "parts": parts, "outro": cl(j.get("outro"))}
    out, m = await write_long("helmi", system, user, 900, check, budget=3500)
    if not out:
        ms = moment_facts(pl, r["shared"])
        good = [x["what_happened"] for x in ms if x["because_shared"] and not x["trade_off"]][:2]
        bad = [x["what_happened"] for x in ms if not x["because_shared"] and not x["trade_off"]][:1]
        out = {"intro": f"This is how {pl['name']} did with {p['short']}'s Helmi.",
               "parts": [{"title": "What you asked", "text": f"Helmi got in touch to arrange {ARRANGE.get(pid, 'a visit').format(pos=p['pron']['pos'])} for {p['short']}. Your bot {bot_name(pl)} asked for {len(r['asked'])} things, {bot_why(pl, r['asked'], F)}."},
                         {"title": "What you got", "text": f"Helmi gave you {len(r['shared'])} of them and kept {len(r['kept'])}, following the traveller's rules."},
                         {"title": "What it let you do", "text": " ".join(good + bad) or "You prepared the basic booking."},
                         {"title": "What you hold now", "text": f"You keep what you got {KEEP.get(C.get('keep'), 'for now')}. Everything Helmi kept, you never had to store or protect."}],
               "outro": "Every detail you got, you got with the traveller's consent."}
        m = "script"
    out["by"] = m
    BIZSTORY[(nid, pid)] = out
    return JSONResponse({"ok": True, "story": out, "res": r})


def driven_trip(b):
    n = BYID.get(b.get("nid"))
    return n if n and n["vid"] == str(b.get("vid", "")) and n.get("driven") else None


async def api_go(req: Request):
    """Trip mode on the phone reached a place: its bot opens, and the phone gets the request as the stand has set it up."""
    b = await req.json()
    n = driven_trip(b)
    pid = b.get("place")
    pl = next((x for x in (n["p"]["places"] if n else []) if x["id"] == pid), None)
    if not n or not pl:
        return JSONResponse({"ok": False}, status_code=404)
    f = go_future(n, pid)
    if not f.done():
        f.set_result(True)
    return JSONResponse({"ok": True, "keys": request(n["p"], pl, n["fields"].get(pid)), "bot": bot_name(pl)})


async def api_decide(req: Request):
    """The visitor sent their answer on trip mode's request card (or their rules did). Helmi passes it on, live."""
    b = await req.json()
    n = driven_trip(b)
    pid = b.get("place")
    if not n or pid not in n["places"]:
        return JSONResponse({"ok": False}, status_code=404)
    shares = [str(x) for x in (b.get("shares") or [])]
    n.setdefault("why", {})[pid] = {str(k): str(v) for k, v in (b.get("why") or {}).items()}
    n.setdefault("dur", {})[pid] = str(b.get("dur") or "trip")
    prog = n.get("prog", {}).get(pid)
    fut = WAIT.get((n["nid"], pid, "*"))
    if prog and prog.get("status") == "done":
        asyncio.create_task(safe(update_place(n, pid, shares, "change")))
    elif fut and not fut.done():
        fut.set_result(shares)
    else:
        n.setdefault("early", {})[pid] = shares
    return JSONResponse({"ok": True})


async def api_revoke(req: Request):
    """The visitor stopped sharing with a place, or shared again."""
    b = await req.json()
    n = driven_trip(b)
    pid = b.get("place")
    if not n or pid not in n.get("prog", {}):
        return JSONResponse({"ok": False}, status_code=404)
    asyncio.create_task(safe(update_place(n, pid, [str(x) for x in (b.get("shares") or [])], "stop" if b.get("stop") else "again")))
    return JSONResponse({"ok": True})


async def safe(coro):
    try:
        await coro
    except Exception as e:
        print("update error", repr(e), flush=True)


async def update_place(n, pid, shares, how):
    """After a place is done: the visitor changed their answer, stopped sharing, or shared again. Helmi tells the bot; the bot answers."""
    p, F = n["p"], n["p"]["fields"]
    pl = next(x for x in p["places"] if x["id"] == pid)
    g = n["prog"][pid]
    before = list(g["shared"])
    keys = n.get("keys", {}).get(pid, [])
    now = [k for k in shares if k in keys] if how != "stop" else []
    added, removed = [k for k in now if k not in before], [k for k in before if k not in now]
    if not added and not removed:
        return
    name = p["short"]
    lab = lambda k: F[k]["label"].split(": ")[-1]
    g["shared"][:] = now
    g["kept"][:] = [k for k in keys if k not in now]
    if pid in n.get("res", {}):
        n["res"][pid]["shared"], n["res"][pid]["kept"] = list(now), [k for k in keys if k not in now]
    lines, fb = [], []
    if how == "stop":
        lines.append(f"Tell the bot that {name} has stopped sharing with {pl['name']}. Ask them to delete what you sent: {jn(lab(k) for k in removed)}. Be polite and brief.")
        fb.append(f"{name} has stopped sharing with {pl['name']}. Please delete what I sent: {jn(lab(k) for k in removed)}.")
    else:
        if added:
            lines.append(f"{name} has decided to share more. Share these details, keeping the facts: " + "; ".join(f"{F[k]['label']}: {F[k]['value']}" for k in added) + ".")
            fb.append(f"{name} would also like you to have this: " + "; ".join(f"{lab(k)}: {F[k]['value'].rstrip('.')}" for k in added) + ".")
        if removed:
            lines.append(f"{name} has taken back these details. Ask the bot to delete them: {jn(lab(k) for k in removed)}.")
            fb.append(f"{name} has taken back {P_pos(p)} {jn(lab(k) for k in removed)}. Please delete it.")
    keep_out = [k for k in F if k not in now]
    out = await write("helmi", helmi_sys(p), f"Your message to {pl['name']}'s bot. " + " ".join(lines), " ".join(fb), unknown(F, now))
    await say(n, "helmi", out, place=pid, shared=added, kept=removed)
    known = "; ".join(F[k]["value"] for k in now if F[k]["kind"] == "need")[:300]
    ack = await write("bot", bot_sys(pl, p), (f"Helmi says {name} stopped sharing and asks you to delete their details. Confirm briefly that you have deleted them." if how == "stop" else
                                              f"Helmi updated what {name} shares. Acknowledge briefly" + (f" and say what you will now prepare, using only: {known}." if added and known else ".")),
                      "Understood. We have deleted those details." if (how == "stop" or (removed and not added)) else "Thank you, noted. We'll have it ready.", unknown(F, now))
    await say(n, "bot", ack, place=pid)
    push({"t": "place_update", "nid": n["nid"], "place": pid, "shared": now, "how": how}, n["vid"])


def P_pos(p):
    return p["pron"]["pos"]


async def api_policy(req: Request):
    """The visitor changed a rule mid-trip. It applies to the places Helmi hasn't reached yet."""
    b = await req.json()
    n = BYID.get(b.get("nid"))
    if not n or n["vid"] != str(b.get("vid", "")):
        return JSONResponse({"ok": False}, status_code=404)
    n["policy"].update({k: v for k, v in (b.get("policy") or {}).items() if k in n["p"]["fields"] and v in ("share", "ask", "never")})
    return JSONResponse({"ok": True})


async def api_answer(req: Request):
    b = await req.json()
    fut = WAIT.get((b.get("nid"), b.get("place"), b.get("k")))
    if fut and not fut.done():
        fut.set_result([str(x) for x in b["shares"]] if isinstance(b.get("shares"), list) else bool(b.get("ok")))
        return JSONResponse({"ok": True})
    n = BYID.get(b.get("nid")) or DONE.get(b.get("nid"))
    key = (b.get("place"), b.get("k"))
    if n and key in n.get("late", set()):  # 'wait and ask me later'
        n["late"].discard(key)
        push({"t": "late_done", "nid": n["nid"], "place": key[0], "k": key[1], "ok": bool(b.get("ok"))}, n["vid"])
        if b.get("ok"):
            asyncio.create_task(safe(late_share(n, key[0], key[1])))
        return JSONResponse({"ok": True})
    return JSONResponse({"ok": False}, status_code=404)


async def api_reset(req: Request):
    b = await req.json()
    if not keyok(b):
        return JSONResponse({"ok": False}, status_code=403)
    reset_stats()
    push({"t": "stats", "stats": STATS})
    return JSONResponse({"ok": True})


async def api_diag(req: Request):
    if STAND_KEY and req.query_params.get("key") != STAND_KEY:
        return JSONResponse({"ok": False, "error": "Add ?key=<your stand key>"}, status_code=403)
    out = {"ai_on": AI_ON, "key_set": bool(LLM_KEY), "key_looks_like": (LLM_KEY[:4] + "…" + str(len(LLM_KEY)) + " chars") if LLM_KEY else None,
           "base_url": LLM_URL, "models": {}, "tokens_last_minute": {}}
    for m in dict.fromkeys([HELMI_MODEL, BOT_MODEL, BACKUP_MODEL]):
        r = {}
        for extras in (True, False):
            try:
                txt, n = await asyncio.to_thread(_post, m, [{"role": "user", "content": "Say hello in five words."}], extras)
                r = {"ok": True, "reply": clean(txt)[:120], "tokens": n, "extras": extras}
                break
            except urllib.error.HTTPError as e:
                try:
                    body = e.read().decode("utf-8", "replace")[:300]
                except Exception:
                    body = ""
                r = {"ok": False, "error": f"HTTP {e.code}: {body}", "extras": extras}
            except Exception as e:
                r = {"ok": False, "error": repr(e)[:300], "extras": extras}
        out["models"][m] = r
        out["tokens_last_minute"][m] = used(m)
    out["recent_errors"] = list(ERRORS)
    return JSONResponse(out)


def trip_order(p):
    """Sort a person's places in the order the trip happens: things done before the trip first, then by day and time."""
    rail = next((pl.get("when", "") for pl in p["places"] if pl["id"] == "rail"), "")
    def key(pl):
        w = pl.get("when", "") or ""
        if w.lower().startswith("before"):
            return (0, 0, 0)
        m = re.search(r"(\d{1,2}) \w{3}", w)
        day = int(m.group(1)) if m else 99
        t = re.search(r"(\d{1,2}):(\d{2})", w)
        if t:
            mins = int(t.group(1)) * 60 + int(t.group(2))
        elif "arrival" in w.lower():  # the hotel: after the journey there
            rt = re.search(r"(\d{1,2}) \w{3}, (\d{1,2}):(\d{2})", rail)
            mins = (int(rt.group(2)) * 60 + int(rt.group(3)) + 120) if rt and int(rt.group(1)) == day else 12 * 60
        else:
            mins = 12 * 60
        return (1, day, mins)
    p["places"].sort(key=key)


class NoCache(BaseHTTPMiddleware):
    """Phones must always load the latest pages and data, so browsers never reuse an old copy (films are fine to cache)."""
    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        path = request.url.path
        if not path.startswith("/static/films/") and path != "/events":
            resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp


def setup():
    for p in DATA["people"]:
        trip_order(p)
    order = ["rail", "hotel", "bistro", "venue", "ins", "kidsclub", "taxi", "pharmacy", "spa", "grocery", "museum", "tour", "work", "planner",
             "cowork", "babysit", "school", "course"]
    for p in DATA["people"]:
        for pl in p["places"]:
            m = META.setdefault(pl["id"], {"type": pl["type"], "bot": bot_name(pl), "cats": [], "names": [], "push": None})
            if pl["name"] not in m["names"]:
                m["names"].append(pl["name"])
            for k in pl["fields"]:
                c = cat(k, p["fields"][k])
                if c not in m["cats"]:
                    m["cats"].append(c)
    META["hotel"]["cats"] += [c for c in HOTEL_EXTRA if c not in META["hotel"]["cats"]]
    for b, m in META.items():
        m["cats"].sort(key=list(CATS).index)
        r = PUSH.get(b, {})
        m["push"] = (f"Offers {r['offer']}" if "offer" in r else f"Suggests: {r['alt']}" if "alt" in r else None)
        m["order"] = order.index(b) if b in order else 99
        m["offers"] = [[k, v[0], v[1]] for k, v in offers_for(b).items()]
        CONFIG[b] = {"asks": list(m["cats"]), "offers": list(offers_for(b))[:3], "trust": [], "keep": "stay", "review": False, "push": bool(r)}  # offers on by default, so the bots have something to tailor
    CONFIG["hotel"].update(asks=["trip", "need", "diet", "card", "passport", "dob"], offers=["stepfree"], trust=["delete"], review=True)
    CONFIG["ins"].update(keep="y1")


setup()


page = lambda f: (lambda req: FileResponse(STATIC / f))
app = Starlette(middleware=[Middleware(GZipMiddleware, minimum_size=2000), Middleware(NoCache)], routes=[
    Route("/", page("live.html")),
    Route("/trip", page("trip_live.html")),
    Route("/stand", page("stand.html")),
    Route("/intro", page("intro.html")),
    Route("/events", events),
    Route("/api/state", api_state),
    Route("/api/ping", api_state),
    Route("/api/requests", api_requests),
    Route("/api/config", api_config, methods=["POST"]),
    Route("/api/start", api_start, methods=["POST"]),
    Route("/api/answer", api_answer, methods=["POST"]),
    Route("/api/resume", api_resume),
    Route("/api/ask", api_ask, methods=["POST"]),
    Route("/api/say", api_say, methods=["POST"]),
    Route("/api/go", api_go, methods=["POST"]),
    Route("/api/decide", api_decide, methods=["POST"]),
    Route("/api/revoke", api_revoke, methods=["POST"]),
    Route("/api/bizstory", api_bizstory, methods=["POST"]),
    Route("/api/standlog", api_standlog),
    Route("/api/leave", api_leave, methods=["POST"]),
    Route("/api/policy", api_policy, methods=["POST"]),
    Route("/api/reset", api_reset, methods=["POST"]),
    Route("/api/diag", api_diag),
    Mount("/static", StaticFiles(directory=STATIC)),
])
