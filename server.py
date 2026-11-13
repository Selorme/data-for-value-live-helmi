"""Helmi live: a whole trip of negotiations for the Demola demo fair.

A visitor plays one of eight invented people and sets rules for each detail: share, ask me, or never.
Helmi then negotiates with each place on the trip in turn: transport, hotel, restaurant, venue, insurer and extras.
Two language models write the messages. The code decides what data moves, and when the visitor is asked.

Run locally:   uvicorn server:app --port 8000
Environment:   GROQ_API_KEY (no key = scripted messages), HELMI_MODEL, BOT_MODEL, BACKUP_MODEL,
               LLM_BASE_URL, TOKENS_PER_MINUTE, STAND_KEY, PACE_SECONDS
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
PACE = float(os.getenv("PACE_SECONDS", "1.8"))
STEPIN_TIMEOUT = 45

# ---------------------------------------------------------------- what the hotel's bot asks (set from the stand)
CATS = {
    "trip": "Trip dates", "need": "Access and comfort needs", "diet": "Allergies and diet", "card": "Disability card",
    "health": "Diagnoses (health record)", "passport": "Passport number", "dob": "Date of birth", "spend": "Spending history",
}
OFFERS = {
    "stepfree": "step-free rooms listed on the website", "form": "a check-in form that works with screen readers",
    "keypad": "card terminals with physical keys", "animal": "staff briefed on assistance animals",
}
TRUST = {
    "delete": "the hotel deletes guest details at checkout", "nopartners": "the hotel never passes details on, not even to its restaurant",
    "contact": "a named person answers data questions", "audit": "the booking system is audited every year by an outside firm",
}
KEEP = {"stay": "until checkout", "d30": "for 30 days", "y1": "for one year"}
HOTEL = {"asks": ["trip", "need", "diet", "card", "passport", "dob"], "offers": ["stepfree"], "trust": ["delete"], "keep": "stay", "review": True}


def cat(k, f):
    if k == "trip": return "trip"
    if k in ("allergy", "diet"): return "diet"
    if k == "card": return "card"
    if k == "id.passport": return "passport"
    if k == "id.dob": return "dob"
    if k.startswith("health.") or k == "dev.main": return "health"
    if k.startswith("bank."): return "spend"
    if f["kind"] == "need": return "need"
    return "other"


def hotel_request(p, place):
    F, asks = p["fields"], HOTEL["asks"]
    keys = [k for k in place["fields"] if cat(k, F[k]) in asks]
    extra = {"trip": ["trip"], "diet": ["allergy", "diet"], "card": ["card"], "passport": ["id.passport"], "dob": ["id.dob"],
             "health": ["health.diag"], "spend": ["bank.all"]}
    for c in asks:
        for k in extra.get(c, []):
            if k in F and k not in keys:
                keys.append(k)
                if c == "diet":
                    break
    return keys


# ---------------------------------------------------------------- how each kind of place pushes back
PUSH = {
    "ins": {"keys": ["health.all", "health.diag", "activity", "bank.all", "loc.hist", "msg.whatsapp", "web.history"],
            "offer": "15% off the insurance price", "lose": "the standard price, with no discount"},
    "rail": {"keys": ["card"], "offer": "a free ticket for a companion", "lose": "no free companion ticket"},
    "venue": {"keys": ["card"], "offer": "a free seat for a companion", "lose": "no free companion seat"},
    "museum": {"keys": ["card"], "offer": "free entry for a companion", "lose": "no free companion entry"},
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
ALT = {"id.passport": "show the passport at the desk", "id.dob": "not needed for the stay", "health.diag": "the needs that matter are already shared",
       "health.all": "the needs that matter are already shared", "bank.all": "not needed", "bank.dining": "not needed",
       "loc.hist": "a pickup address is enough", "msg.whatsapp": "private conversations with other people", "mail.inbox": "private",
       "web.history": "private", "photos.all": "other people are in them", "activity": "not needed", "card": "can show the card in person",
       "study.grades": "not needed for the event"}

STATS = {}
def reset_stats():
    STATS.clear()
    STATS.update({"n": 0, "done": 0, "stepins": 0, "stepin_yes": 0, "offers": 0, "offers_yes": 0, "blocked": 0, "ai": 0, "script": 0,
                  "cats": {}, "places": {}})
reset_stats()

CLIENTS, ACTIVE, WAIT, PENDING, TASKS = {}, {}, {}, {}, set()
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
    return {"hotel": HOTEL, "stats": STATS, "ai": AI_ON, "models": {"helmi": HELMI_MODEL, "bot": BOT_MODEL, "backup": BACKUP_MODEL},
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


async def write(role, system, user, fallback, forbidden=()):
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


def bot_sys(place, p):
    return (f"You are the booking assistant bot of {place['name']}, a {place['type']}. You are chatting with Helmi, the personal AI assistant of "
            f"your customer {p['name']} ({p['pron']['sub']}/{p['pron']['obj']}). Write ONE chat message to Helmi: 2 or 3 sentences, at most 60 words, "
            "friendly and businesslike, plain English, no lists, no markdown, no emoji. Use only the facts given to you; never invent prices, numbers or policies. "
            f"Refer to the customer as {p['short']} or {p['pron']['sub']}.")


def helmi_sys(p):
    P = p["pron"]
    return (f"You are Helmi, the personal AI assistant of {p['name']}. You are chatting with a business's bot on {P['pos']} behalf. "
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
    await asyncio.sleep(PACE)


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
    keys = hotel_request(p, place) if place["id"] == "hotel" else list(place["fields"])
    if not keys:
        return {"shared": [], "kept": []}
    def lab(k):
        s = F[k]["label"].split(": ")[-1]
        return s if s[:2].isupper() else s[0].lower() + s[1:]
    push({"t": "place", "nid": n["nid"], "place": place["id"], "pname": place["name"], "ptype": place["type"], "keys": keys,
          "labels": {k: F[k]["label"] for k in keys}}, n["vid"])

    # 1. the business's bot opens
    ctx = f"Ask Helmi for these details about {name} and say briefly why: {jn(lab(k) for k in keys)}. Your reason: {place['why']}"
    fb = f"Hello Helmi, this is {place['name']}. To prepare for {name}, could you share {P['pos']} {jn(lab(k) for k in keys)}? {place['why']}"
    if place["id"] == "hotel":
        ctx += f" Say you keep guest details {KEEP[HOTEL['keep']]}."
        fb += f" We keep guest details {KEEP[HOTEL['keep']]}."
        if HOTEL["offers"]:
            ctx += " Also mention that the hotel offers " + jn(OFFERS[o] for o in HOTEL["offers"]) + "."
        if HOTEL["trust"]:
            ctx += " Also say that " + jn(TRUST[t] for t in HOTEL["trust"]) + "."
    if place["id"] == "bistro" and hotel_name:
        ctx += f" First ask whether you may simply reuse what {name} already shared with {hotel_name}, which has the same owner as you."
        fb = f"Hello Helmi, {place['name']} here. We share an owner with {hotel_name}: could we reuse what {name} shared there? Otherwise, could you share {P['pos']} {jn(lab(k) for k in keys)}?"
    await say(n, "bot", await write("bot", bot_sys(place, p), ctx, fb), place=place["id"], asks=keys)

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

    async def helmi(new_give, refuse, checking, first=False, why_no_reuse=False):
        lines, fbp = [], []
        if why_no_reuse:
            lines.append(f"Say no to reusing the hotel's details: what {name} shared with {hotel_name} was for the hotel only, so you answer this request separately.")
            fbp.append(f"No: what {name} shared with {hotel_name} was for the hotel only, so I'll answer you separately.")
        if new_give:
            lines.append("Share these details, in your own words but keeping the facts: " + "; ".join(f"{F[k]['label']}: {F[k]['value']}" for k in new_give) + ".")
            fbp.append("Here is what " + name + " shares: " + "; ".join(f"{lab(k)}: {F[k]['value'].rstrip('.')}" for k in new_give) + ".")
        if checking:
            lines.append(f"Say you are checking with {name} about: {jn(lab(k) for k in checking)}.")
            fbp.append(f"I'm checking with {name} about {P['pos']} {jn(lab(k) for k in checking)}.")
        if refuse:
            lines.append("Say clearly that these will NOT be shared, and do not offer them in any form: " +
                         "; ".join(f"{lab(k)} (reason or alternative: {ALT.get(k, 'not needed')})" for k in refuse) + ".")
            fbp.append(f"{cap(jn(lab(k) for k in refuse))} stays with {name}: " + "; ".join(ALT.get(k, "not needed") for k in refuse) + ".")
        if not lines:
            return
        out = await write("helmi", helmi_sys(p), f"Your message to {place['name']}'s bot. " + " ".join(lines), " ".join(fbp), forbidden())
        await say(n, "helmi", out, place=place["id"], shared=new_give, kept=refuse)

    await helmi(give, keep, check, True, why_no_reuse=place["id"] == "bistro" and bool(hotel_name))

    # 3. "ask me" details: the visitor's phone buzzes
    yes, no = [], []
    for k in check:
        (yes if await ask_person(n, place, k) else no).append(k)
    give += yes
    keep += no
    if check:
        await helmi(yes, no, [])

    # 4. the business pushes back once on something it didn't get
    rule = PUSH.get(place["id"], {})
    target = next((k for k in rule.get("keys", []) if k in keep), None)
    lost = None
    if target:
        if "offer" in rule:
            out = await write("bot", bot_sys(place, p),
                              f"Helmi did not share {name}'s {lab(target)}. Make one friendly offer: if {name} shares it, {P['sub']} gets {rule['offer']}. "
                              f"Without it, {P['sub']} gets {rule['lose']}. Ask once.",
                              f"Understood. If {name} shares {P['pos']} {lab(target)}, {P['sub']} gets {rule['offer']}. Without it, {rule['lose']}. Would {P['sub']} reconsider?")
            await say(n, "bot", out, place=place["id"])
            if pol.get(target) == "never":
                o = await write("helmi", helmi_sys(p), f"Your message to {place['name']}'s bot. Thank them, but say {name}'s rule is never to share {lab(target)}, "
                                f"so the answer stays no, whatever the offer. Do not offer it in any form.",
                                f"Thank you, but {name}'s rule is never to share {P['pos']} {lab(target)}, whatever the offer.", forbidden())
                await say(n, "helmi", o, place=place["id"], kept=[target], rule=True)
                lost = rule["lose"]
            elif await ask_person(n, place, target, offer=rule["offer"]):
                keep.remove(target)
                give.append(target)
                o = await write("helmi", helmi_sys(p), f"Your message to {place['name']}'s bot. Say {name} accepts the offer of {rule['offer']}, and share: "
                                f"{F[target]['label']}: {F[target]['value']}.", f"{name} accepts. Here it is: {lab(target)}: {F[target]['value'].rstrip('.')}.", [])
                await say(n, "helmi", o, place=place["id"], shared=[target])
            else:
                o = await write("helmi", helmi_sys(p), f"Your message to {place['name']}'s bot. Say {name} considered the offer and still says no to sharing "
                                f"{lab(target)}. Do not offer it in any form.", f"{name} thought about it and still says no.", forbidden())
                await say(n, "helmi", o, place=place["id"], kept=[target])
                lost = rule["lose"]
        else:
            out = await write("bot", bot_sys(place, p), f"Helmi did not share {name}'s {lab(target)}. Accept this politely and say what you will do instead: {rule['alt']}. Do not ask again.",
                              f"That's fine. Instead, {rule['alt']}.")
            await say(n, "bot", out, place=place["id"])

    # 5. the business confirms
    prepared = [F[k]["value"] for k in give if F[k]["kind"] == "need"][:4]
    extra = (" A person at reception double-checks the room plan." if place["id"] == "hotel" and HOTEL["review"] and prepared else "")
    out = await write("bot", bot_sys(place, p),
                      f"Confirm what you will do for {name}, using only these details: {'; '.join(prepared) or 'only the basic booking'}."
                      + (f" Also say that {name} gets {lost}." if lost else "") + extra,
                      f"Thank you. Everything is set for {name}" + (": " + "; ".join(prepared).rstrip(".") + "." if prepared else ".") + (f" Note: {lost}." if lost else "") + extra)
    await say(n, "bot", out, place=place["id"])

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
    push({"t": "start", "nid": n["nid"], "person": p["id"], "name": p["name"], "who": p["who"], "places": [[pl["id"], pl["name"], pl["type"]] for pl in places],
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
    h = b.get("hotel") or {}
    HOTEL["asks"] = [c for c in h.get("asks", HOTEL["asks"]) if c in CATS]
    HOTEL["offers"] = [o for o in h.get("offers", HOTEL["offers"]) if o in OFFERS]
    HOTEL["trust"] = [t for t in h.get("trust", HOTEL["trust"]) if t in TRUST]
    HOTEL["keep"] = h.get("keep") if h.get("keep") in KEEP else HOTEL["keep"]
    HOTEL["review"] = bool(h.get("review", HOTEL["review"]))
    for c in list(CLIENTS.values()):
        try:
            c["q"].put_nowait({"t": "config", "hotel": HOTEL, "at": time.time()})
        except asyncio.QueueFull:
            pass
    return JSONResponse({"ok": True, "hotel": HOTEL})


async def api_requests(req: Request):
    """What each place on this person's trip will ask for, with the hotel's current settings."""
    p = PEOPLE.get(req.query_params.get("person"))
    if not p:
        return JSONResponse({"ok": False}, status_code=404)
    return JSONResponse({"ok": True, "places": [{"id": pl["id"], "name": pl["name"], "type": pl["type"], "why": pl["why"], "core": pl["core"],
                                                 "keys": hotel_request(p, pl) if pl["id"] == "hotel" else pl["fields"]} for pl in p["places"]]})


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
    t = asyncio.create_task(run(n))
    TASKS.add(t)
    t.add_done_callback(TASKS.discard)
    return JSONResponse({"ok": True, "nid": n["nid"]})


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


page = lambda f: (lambda req: FileResponse(STATIC / f))
app = Starlette(routes=[
    Route("/", page("live.html")),
    Route("/stand", page("stand.html")),
    Route("/events", events),
    Route("/api/state", api_state),
    Route("/api/ping", api_state),
    Route("/api/requests", api_requests),
    Route("/api/config", api_config, methods=["POST"]),
    Route("/api/start", api_start, methods=["POST"]),
    Route("/api/answer", api_answer, methods=["POST"]),
    Route("/api/reset", api_reset, methods=["POST"]),
    Route("/api/diag", api_diag),
    Mount("/static", StaticFiles(directory=STATIC)),
])
