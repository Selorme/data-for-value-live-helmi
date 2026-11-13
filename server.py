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
STEPIN_TIMEOUT = 45

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


def request(p, place):
    """What this business asks this person for, with the business's current settings."""
    F, asks = p["fields"], CONFIG[place["id"]]["asks"]
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
ALT = {"id.kids_dob": "the children's ages are enough", "photos.kids": "no photos of the children", "id.passport": "show the passport at the desk", "id.dob": "not needed for the stay", "health.diag": "the needs that matter are already shared",
       "health.all": "the needs that matter are already shared", "bank.all": "not needed", "bank.dining": "not needed",
       "loc.hist": "not needed for this", "msg.whatsapp": "private conversations with other people", "mail.inbox": "private",
       "web.history": "private", "photos.all": "other people are in them", "activity": "not needed", "card": "can show the card in person",
       "study.grades": "not needed for the event"}

STATS = {}
def reset_stats():
    STATS.clear()
    STATS.update({"n": 0, "done": 0, "stepins": 0, "stepin_yes": 0, "offers": 0, "offers_yes": 0, "blocked": 0, "ai": 0, "script": 0,
                  "cats": {}, "places": {}})
reset_stats()

CLIENTS, ACTIVE, WAIT, PENDING, TASKS, BYID = {}, {}, {}, {}, set(), {}
SEM = asyncio.Semaphore(2)
QUEUE = deque()
USE = {}
ERRORS = deque(maxlen=20)


def push(ev, vid=None):
    ev = dict(ev, at=time.time())
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


def _post(model, messages, extras=True):
    body = {"model": model, "messages": messages, "temperature": 0.6, "max_tokens": 200}
    if extras and "gpt-oss" in model:
        body.update(reasoning_effort="low", max_tokens=500)  # its thinking counts against the limit
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
                if require and not re.search(require, txt, re.I):
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
            f"Speak about {p['short']} in the third person ({P['sub']}/{P['obj']}/{P['pos']}), never as 'we' or 'I' for {P['obj']}. "
            "Write ONE chat message: 2 or 3 sentences, at most 60 words, warm but firm, plain English, no lists, no markdown, no emoji. "
            "Your instructions list exactly what to say. Say only that. Never offer, hint at or promise anything you were told not to share. "
            "Never mention any other personal detail.")


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


async def ask_person(n, place, k, offer=None):
    p, F = n["p"], n["p"]["fields"]
    fut = asyncio.get_running_loop().create_future()
    key = (n["nid"], place["id"], k)
    WAIT[key] = fut
    STATS["stepins"] += 1
    if offer:
        STATS["offers"] += 1
    push({"t": "stepin", "nid": n["nid"], "place": place["id"], "pname": place["name"], "k": k, "label": F[k]["label"], "value": F[k]["value"],
          "why": place["why"], "offer": offer, "name": p["short"]}, n["vid"])
    try:
        ok = await asyncio.wait_for(fut, STEPIN_TIMEOUT)
    except asyncio.TimeoutError:
        ok = False
        push({"t": "stepin_timeout", "nid": n["nid"], "place": place["id"], "k": k}, n["vid"])
    WAIT.pop(key, None)
    push({"t": "stepin_done", "nid": n["nid"], "place": place["id"], "k": k, "ok": ok}, n["vid"])
    if ok:
        STATS["stepin_yes"] += 1
        if offer:
            STATS["offers_yes"] += 1
    return ok


async def negotiate_place(n, place, hotel_name):
    p, F, pol = n["p"], n["p"]["fields"], n["policy"]
    P, name = p["pron"], p["short"]
    pl = p.get("plural", False)
    vb = lambda s, plural: plural if pl else s
    poss = name + ("'" if pl else "'s")
    C = CONFIG[place["id"]]
    keys = request(p, place)
    if not keys:
        return {"shared": [], "kept": []}
    def lab(k):
        s = F[k]["label"].split(": ")[-1]
        w = s.split(" ")[0]
        return s if (s[:2].isupper() or any(c.isupper() for c in w[1:]) or "'" in w or "’" in w) else s[0].lower() + s[1:]
    push({"t": "place", "nid": n["nid"], "place": place["id"], "pname": place["name"], "ptype": place["type"], "bot": bot_name(place), "keys": keys,
          "labels": {k: F[k]["label"] for k in keys}}, n["vid"])

    # 1. the business's bot opens
    ctx = f"Ask Helmi for these details about {name} and say briefly why: {jn(lab(k) for k in keys)}. Your reason: {place['why']}"
    fb = f"Hello Helmi, {bot_name(place)} here from {place['name']}. To prepare for {name}, could you share {P['pos']} {jn(lab(k) for k in keys)}? {place['why']}"
    ctx += f" Say you keep customers' details {KEEP[C['keep']]}."
    fb += f" We keep customers' details {KEEP[C['keep']]}."
    if C["offers"]:
        O = offers_for(place["id"])
        ctx += f" Also mention that {place['name']} offers " + jn(O[o][2] for o in C["offers"] if o in O) + "."
        fb += " We offer " + jn(O[o][2] for o in C["offers"] if o in O) + "."
    if C["trust"]:
        ctx += " Also promise that " + jn(TRUST[t] for t in C["trust"]) + "."
        fb += " " + cap(jn(TRUST[t] for t in C["trust"])) + "."
    if place["id"] == "bistro" and hotel_name:
        ctx += f" First ask whether you may simply reuse what {name} already shared with {hotel_name}, which has the same owner as you."
        fb = f"Hello Helmi, {bot_name(place)} here from {place['name']}. We share an owner with {hotel_name}: could we reuse what {name} shared there? Otherwise, could you share {P['pos']} {jn(lab(k) for k in keys)}?"
    await say(n, "bot", await write("bot", bot_sys(place, p, True), ctx, fb), place=place["id"], asks=keys)

    # 2. the code decides each detail from the visitor's rules
    give = [k for k in keys if pol.get(k) == "share"]
    check = [k for k in keys if pol.get(k, "ask") == "ask"]
    keep = [k for k in keys if pol.get(k) == "never"]

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

    async def helmi(new_give, refuse, checking, first=False):
        lines, fbp = [], []
        if new_give:
            lines.append("Share these details, in your own words but keeping the facts: " + "; ".join(f"{F[k]['label']}: {F[k]['value']}" for k in new_give) + ".")
            fbp.append("Here is what " + name + vb(" shares: ", " share: ") + "; ".join(f"{lab(k)}: {F[k]['value'].rstrip('.')}" for k in new_give) + ".")
        if checking:
            lines.append(f"Say you are checking with {name} about: {jn(lab(k) for k in checking)}.")
            fbp.append(f"I'm checking with {name} about {P['pos']} {jn(lab(k) for k in checking)}.")
        if refuse:
            lines.append("Say clearly that these will NOT be shared, and do not offer them in any form: " +
                         "; ".join(f"{lab(k)} (reason or alternative: {ALT.get(k, 'not needed')})" for k in refuse) + ".")
            fbp.append(f"{cap(jn(lab(k) for k in refuse))} stays with {name}: " + "; ".join(ALT.get(k, "not needed") for k in refuse) + ".")
        if not lines:
            return
        out = await write("helmi", helmi_sys(p, first), f"Your message to {place['name']}'s bot. " + " ".join(lines), " ".join(fbp), forbidden())
        await say(n, "helmi", out, place=place["id"], shared=new_give, kept=refuse)

    reuse = place["id"] == "bistro" and bool(hotel_name)
    if reuse:  # a sister business asks to reuse what the hotel got: Helmi always says no, in its own message
        out = await write("helmi", helmi_sys(p, True),
                          f"The bot of {place['name']} asked to reuse what {name} shared with {hotel_name}, because they have the same owner. "
                          f"Refuse clearly: begin your message with the word 'No'. Explain that what {name} shared with {hotel_name} was for the hotel stay only, "
                          f"that you never pass details from one business to another, even with the same owner, and that you will answer {place['name']}'s own request "
                          "separately. Do not share any details in this message.",
                          f"No, I'm sorry. What {name} shared with {hotel_name} was for the hotel stay only, and I never pass details from one business to another, "
                          f"even with the same owner. I'll answer your own request separately.", forbidden(), require=r"^\W*no\b")
        await say(n, "helmi", out, place=place["id"], reuse=True)
    await helmi(give, keep, check, not reuse)

    # 3. "ask me" details: the visitor's phone buzzes
    yes, no = [], []
    for k in check:
        (yes if await ask_person(n, place, k) else no).append(k)
    give += yes
    keep += no
    if check:
        await helmi(yes, no, [])

    # 4. the business pushes back once on something it didn't get
    base = PUSH.get(place["id"], {})
    target = next((k for k in base.get("keys", []) if k in keep), None)
    if not C["push"]:
        target = None
    rule = {**base, **base.get("by", {}).get(target, {})}
    if "alt" in base.get("by", {}).get(target, {}):
        rule.pop("offer", None)
    lost = None
    if target:
        if "offer" in rule:
            out = await write("bot", bot_sys(place, p),
                              f"Helmi did not share {poss} {lab(target)}. Make one friendly offer: if {name} {vb('shares','share')} it, {P['sub']} {vb('gets','get')} {rule['offer']}. "
                              f"Without it, {P['sub']} {vb('gets','get')} {rule['lose']}. Ask once.",
                              f"Understood. If {name} {vb('shares','share')} {P['pos']} {lab(target)}, {P['sub']} {vb('gets','get')} {rule['offer']}. Without it, {rule['lose']}. Would {P['sub']} like to reconsider?")
            await say(n, "bot", out, place=place["id"])
            if pol.get(target) == "never":
                o = await write("helmi", helmi_sys(p), f"Your message to {place['name']}'s bot. Thank them, but say {poss} rule is never to share {lab(target)}, "
                                f"so the answer stays no, whatever the offer. Do not offer it in any form.",
                                f"Thank you, but {name}'{'' if pl else 's'} rule is never to share {P['pos']} {lab(target)}, whatever the offer.", forbidden())
                await say(n, "helmi", o, place=place["id"], kept=[target], rule=True)
                lost = rule["lose"]
            elif await ask_person(n, place, target, offer=rule["offer"]):
                keep.remove(target)
                give.append(target)
                o = await write("helmi", helmi_sys(p), f"Your message to {place['name']}'s bot. Say {name} {vb('accepts','accept')} the offer of {rule['offer']}, and share: "
                                f"{F[target]['label']}: {F[target]['value']}.", f"{name} {vb('accepts', 'accept')}. Here it is: {lab(target)}: {F[target]['value'].rstrip('.')}.", [])
                await say(n, "helmi", o, place=place["id"], shared=[target])
            else:
                o = await write("helmi", helmi_sys(p), f"Your message to {place['name']}'s bot. Say {name} considered the offer and still {vb('says','say')} no to sharing "
                                f"{lab(target)}. Do not offer it in any form.", f"{name} thought about it and still {vb('says', 'say')} no.", forbidden())
                await say(n, "helmi", o, place=place["id"], kept=[target])
                lost = rule["lose"]
        else:
            out = await write("bot", bot_sys(place, p), f"Helmi did not share {poss} {lab(target)}. Accept this politely and say what you will do instead: {rule['alt']}. Do not ask again.",
                              f"That's fine. Instead, {rule['alt']}.")
            await say(n, "bot", out, place=place["id"])

    # 5. the business confirms
    prepared = [F[k]["value"] for k in give if F[k]["kind"] == "need"][:4]
    extra = (" A member of staff double-checks the arrangements." if C["review"] and prepared else "")
    out = await write("bot", bot_sys(place, p),
                      f"Confirm what you will do for {name}, using only these details: {'; '.join(prepared) or 'only the basic booking'}."
                      + (f" Also say that {name} {vb('gets','get')} {lost}." if lost else "") + extra,
                      f"Thank you. Everything is set for {name}" + (": " + "; ".join(prepared).rstrip(".") + "." if prepared else ".") + (f" Note: {lost}." if lost else "") + extra)
    await say(n, "bot", out, place=place["id"])

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
    res = {"shared": give, "kept": keep, "lost": lost}
    push({"t": "place_done", "nid": n["nid"], "place": place["id"], "pname": place["name"], **res}, n["vid"])
    return res


async def negotiate(n):
    p = n["p"]
    places = [pl for pl in p["places"] if pl["id"] in n["places"]]
    push({"t": "start", "nid": n["nid"], "person": p["id"], "name": p["name"], "who": p["who"], "places": [[pl["id"], pl["name"], pl["type"], bot_name(pl)] for pl in places],
          "models": {"helmi": HELMI_MODEL, "bot": BOT_MODEL} if AI_ON else None}, n["vid"])
    hotel_name = None
    results = {}
    for pl in places:
        results[pl["id"]] = await negotiate_place(n, pl, hotel_name)
        if pl["id"] == "hotel":
            hotel_name = pl["name"]
    STATS["done"] += 1
    push({"t": "done", "nid": n["nid"], "person": p["id"], "results": results, "stats": STATS}, n["vid"])


async def run(n):
    QUEUE.append(n["nid"])
    try:
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

    async def gen():
        try:
            yield "retry: 3000\n\n"
            yield f"event: hello\ndata: {json.dumps(public_state())}\n\n"
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), 15)
                    yield f"event: {ev['t']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
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
    if vid in PENDING:
        return JSONResponse({"ok": False, "error": "Your Helmi is already on a trip"}, status_code=409)
    if len(QUEUE) >= 6:
        return JSONResponse({"ok": False, "error": "The stand is busy. Try again in a minute."}, status_code=429)
    p = PEOPLE[pid]
    places = [x for x in b.get("places", []) if any(pl["id"] == x for pl in p["places"])][:8]
    if not places:
        return JSONResponse({"ok": False, "error": "Choose at least one place"}, status_code=400)
    pol = {k: v for k, v in (b.get("policy") or {}).items() if k in p["fields"] and v in ("share", "ask", "never")}
    n = {"nid": uuid.uuid4().hex[:10], "vid": vid, "person": pid, "p": p, "places": places, "policy": pol}
    STATS["n"] += 1
    PENDING[vid] = n["nid"]
    BYID[n["nid"]] = n
    t = asyncio.create_task(run(n))
    TASKS.add(t)
    t.add_done_callback(TASKS.discard)
    return JSONResponse({"ok": True, "nid": n["nid"]})


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
        fut.set_result(bool(b.get("ok")))
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


def setup():
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
        CONFIG[b] = {"asks": list(m["cats"]), "offers": [], "trust": [], "keep": "stay", "review": False, "push": bool(r)}
    CONFIG["hotel"].update(asks=["trip", "need", "diet", "card", "passport", "dob"], offers=["stepfree"], trust=["delete"], review=True)
    CONFIG["ins"].update(keep="y1")


setup()


page = lambda f: (lambda req: FileResponse(STATIC / f))
app = Starlette(routes=[
    Route("/", page("live.html")),
    Route("/stand", page("stand.html")),
    Route("/intro", page("intro.html")),
    Route("/events", events),
    Route("/api/state", api_state),
    Route("/api/ping", api_state),
    Route("/api/requests", api_requests),
    Route("/api/config", api_config, methods=["POST"]),
    Route("/api/start", api_start, methods=["POST"]),
    Route("/api/answer", api_answer, methods=["POST"]),
    Route("/api/policy", api_policy, methods=["POST"]),
    Route("/api/reset", api_reset, methods=["POST"]),
    Route("/api/diag", api_diag),
    Mount("/static", StaticFiles(directory=STATIC)),
])
