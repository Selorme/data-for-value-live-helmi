"""Helmi live negotiation server for the Demola demo fair.

Visitors' phones (Helmi's side) and the stand screen (Hotel Merikaari's side) connect here.
Two language models write the messages. The code decides what data moves:
an item leaves Helmi only if the visitor's rule allows it, or the visitor says yes when pinged.

Run locally:   uvicorn server:app --port 8000
Environment:   GROQ_API_KEY   (no key = scripted messages, everything else still works)
               HELMI_MODEL, BOT_MODEL, BACKUP_MODEL, LLM_BASE_URL, TOKENS_PER_MINUTE, STAND_KEY
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
DATA = json.loads((STATIC / "data.json").read_text(encoding="utf-8"))
Q = {q["id"]: q for q in DATA["questions"]}
G = {g["id"]: g for g in DATA["guests"]}

LLM_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
LLM_KEY = os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY", "")
HELMI_MODEL = os.getenv("HELMI_MODEL", "openai/gpt-oss-120b")
BOT_MODEL = os.getenv("BOT_MODEL", "qwen/qwen3.8-27b")
BACKUP_MODEL = os.getenv("BACKUP_MODEL", "openai/gpt-oss-20b")
TPM = int(os.getenv("TOKENS_PER_MINUTE", "7000"))  # free plan allows 8K per model, keep a margin
STAND_KEY = os.getenv("STAND_KEY", "")
LOCAL_LLM = any(h in LLM_URL for h in ("localhost", "127.0.0.1", "0.0.0.0"))
AI_ON = bool(LLM_KEY) or LOCAL_LLM
PACE = float(os.getenv("PACE_SECONDS", "1.4"))  # pause between messages so people can read
STEPIN_TIMEOUT = 45

OFFERS = {
    "stepfree": "step-free rooms near a working lift, listed on our website",
    "form": "a check-in form that works with screen readers",
    "keypad": "card terminals with physical keys",
    "animal": "staff briefed on assistance animals",
}
TRUST = {
    "delete": "we delete guest details at checkout",
    "nopartners": "we never pass details on, not even to our own bistro",
    "contact": "a named person answers data questions",
    "audit": "our booking system is audited every year by an outside firm",
}
KEEP = {"stay": "until checkout", "d30": "for 30 days", "y1": "for one year"}
ALT = {  # what Helmi offers instead when an item stays with the guest
    "passport": "she can show her passport at the desk",
    "dob": "it isn't needed for the stay",
    "spend": "it isn't needed for the stay",
    "health": "the needs that matter for the stay are already covered",
    "loyalty": "she can give her member number at check-in",
}

HOTEL = {  # the stand screen changes this; a deliberately slightly greedy default
    "asks": ["arrival", "access", "health", "allergy", "animal", "family", "prefs", "passport", "dob"],
    "sum": True, "keep": "stay", "offers": ["stepfree"], "trust": ["delete"], "review": True,
}
STATS = {"n": 0, "done": 0, "stepins": 0, "stepin_yes": 0, "items": {}, "access_shared": 0, "records": 0, "ai": 0, "script": 0}
CLIENTS = {}        # client id -> {"role", "vid", "q"}
ACTIVE = {}         # nid -> negotiation
WAIT = {}           # (nid, qid) -> Future
PENDING = {}        # vid -> nid, queued or running
TASKS = set()
SEM = asyncio.Semaphore(2)
QUEUE = deque()
USE = {}            # model -> deque[(time, tokens)]


# ---------------------------------------------------------------- events
def push(ev, vid=None):
    """Send an event to the stand screens and, if vid is given, to that visitor only."""
    ev = dict(ev, at=time.time())
    for c in list(CLIENTS.values()):
        if c["role"] == "stand" or (vid and c["vid"] == vid):
            try:
                c["q"].put_nowait(ev)
            except asyncio.QueueFull:
                pass


def public_state():
    return {"hotel": HOTEL, "stats": STATS, "ai": AI_ON, "models": {"helmi": HELMI_MODEL, "bot": BOT_MODEL, "backup": BACKUP_MODEL},
            "active": [{"nid": n["nid"], "guest": n["guest"]} for n in ACTIVE.values()], "queue": len(QUEUE)}


# ---------------------------------------------------------------- language models
def used(m):
    now, d = time.time(), USE.setdefault(m, deque())
    while d and now - d[0][0] > 60:
        d.popleft()
    return sum(t for _, t in d)


def note(m, n):
    USE.setdefault(m, deque()).append((time.time(), n))


def _post(model, messages, extras=True):
    body = {"model": model, "messages": messages, "temperature": 0.5, "max_tokens": 160}
    if extras and "gpt-oss" in model:
        body.update(reasoning_effort="low", max_tokens=450)  # its thinking counts against the limit
    if extras and "qwen3" in model:
        body.update(reasoning_effort="none")
    req = urllib.request.Request(LLM_URL + "/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "helmi-live/1.0",
                                          "Authorization": "Bearer " + (LLM_KEY or "local")})
    with urllib.request.urlopen(req, timeout=25) as r:
        j = json.loads(r.read())
    txt = (j["choices"][0]["message"].get("content") or "")
    return txt, int(j.get("usage", {}).get("total_tokens") or 900)


ERRORS = deque(maxlen=20)


def log_err(model, msg):
    ERRORS.append({"at": time.strftime("%H:%M:%S"), "model": model, "error": msg})
    print("LLM error", model, msg, flush=True)


def clean(t):
    t = re.sub(r"<think>.*?</think>", "", t, flags=re.S)
    t = re.sub(r"[*_#`>]+", "", t).strip().strip('"').strip()
    t = re.sub(r"\s+", " ", t)
    words = t.split(" ")
    if len(words) > 70:
        t = " ".join(words[:70]).rstrip(",;") + "…"
    return t


async def write(role, system, user, fallback, forbidden=()):
    """Ask a model for one chat message. Falls back to the scripted line on any problem."""
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
                if any(f and f.lower() in low for f in forbidden):
                    blocked = True  # it mentioned something the guest did not share
                    STATS["blocked"] = STATS.get("blocked", 0) + 1
                    break
                if len(txt) < 8:
                    log_err(m, "empty reply (the model may have spent its tokens thinking)")
                    break
                STATS["ai"] += 1
                return txt, m, False
            except urllib.error.HTTPError as e:
                body = ""
                try:
                    body = e.read().decode("utf-8", "replace")[:300]
                except Exception:
                    pass
                log_err(m, f"HTTP {e.code}: {body}")
                if e.code == 400 and extras:
                    continue  # model may not support the extra setting, try plain
                if e.code == 429:
                    note(m, TPM)  # treat as full for a minute
                break
            except Exception as e:
                log_err(m, repr(e)[:300])
                break
    STATS["script"] += 1
    return fallback, "script", blocked


BOT_SYS = ("You are Merikaari Assistant, the booking bot of Hotel Merikaari, a 48-room hotel in Helsinki with a bistro owned by the same company. "
           "You are chatting with a guest's personal AI assistant, called Helmi, before the guest arrives. "
           "Write ONE short chat message: at most 2 sentences and 45 words, friendly and professional, plain English, no lists, no markdown, no emoji. "
           "Only use the facts given to you. Never invent prices, room numbers you were not given, or policies.")
HELMI_SYS = ("You are Helmi, a personal AI assistant. You negotiate with a hotel's booking bot on behalf of your owner. "
             "Your owner set rules about what you may share; those decisions are already made and are listed for you. "
             "Write ONE short chat message to the hotel's bot: at most 2 sentences and 45 words, warm but brief, plain English, no lists, no markdown, no emoji. "
             "Mention ONLY the details given to you as shared. Never guess or add any other personal detail.")


def ql(q):
    return Q[q]["l"].lower()


def join(xs):
    xs = list(xs)
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1] if xs else ""


# ---------------------------------------------------------------- negotiation
async def say(n, who, out, **extra):
    text, src, blocked = out
    push({"t": "msg", "nid": n["nid"], "who": who, "text": text, "src": src, "blocked": blocked, **extra}, n["vid"])
    n["log"].append({"who": who, "text": text, "src": src})
    await asyncio.sleep(PACE)


async def negotiate(n):
    g, H = G[n["guest"]], n["hotel"]
    name = g["short"]
    asks = [q for q in H["asks"] if q in Q]
    offers = [OFFERS[o] for o in H.get("offers", []) if o in OFFERS]
    trust = [TRUST[t] for t in H.get("trust", []) if t in TRUST]
    keep = KEEP.get(H.get("keep"), "until checkout")
    push({"t": "start", "nid": n["nid"], "guest": g["id"], "name": g["name"], "who": g["who"], "asks": asks,
          "models": {"helmi": HELMI_MODEL, "bot": BOT_MODEL} if AI_ON else None}, n["vid"])

    # 1. the hotel's bot opens
    reasons = "; ".join(f"{Q[q]['l']} ({Q[q]['why']})" for q in asks)
    fb = (f"Hello, this is Merikaari Assistant. To prepare {name}'s stay, could you share: {join(ql(q) for q in asks)}? "
          f"We keep guest details {keep}.")
    ctx = (f"The guest is {name}. Ask Helmi for these items and say briefly why: {reasons}. "
           f"Say the hotel keeps guest details {keep}. "
           + (f"Also mention that the hotel offers {join(offers)}. " if offers else "")
           + (f"Also mention that {join(trust)}. " if trust else ""))
    out = await write("bot", BOT_SYS, ctx, fb)
    await say(n, "bot", out, asks=asks)

    # 2. the code decides, item by item
    give, check, keepback, na = [], [], [], []
    for q in asks:
        if q not in g["items"]:
            na.append(q)
            continue
        p = n["policy"].get(q, "ask")
        (give if p == "share" else check if p == "ask" else keepback).append(q)
    form = "need" if (n.get("form", "need") == "need" or H.get("sum")) else "record"
    val = lambda q: g["items"][q][form]
    def withheld_text():
        """Fragments of details that have not been shared. If a model's message contains one, it is not used."""
        shared = " ".join(val(q) for q in give).lower()
        frags = []
        for q, v in g["items"].items():
            if q in give:
                continue
            for s in (v["record"], v["need"]):
                f = s[:14]
                if len(f) >= 8 and f.lower() not in shared and not f.lower().startswith(("no ", "not ", "any ")):
                    frags.append(f)
        return frags

    async def helmi_turn(new_give, refuse, checking, intro):
        parts = []
        if new_give:
            parts.append("Shared: " + "; ".join(f"{Q[q]['l']}: {val(q)}" for q in new_give) + ".")
        if checking:
            parts.append(f"You still need to ask {name} about: {join(ql(q) for q in checking)}. Say you are checking with her or them.")
        if refuse:
            parts.append("Not shared, say so politely and offer the alternative: " +
                         "; ".join(f"{ql(q)} ({ALT.get(q, 'it stays with ' + name)})" for q in refuse) + ".")
        nas = [q for q in na if q in asks and intro]
        if nas:
            parts.append(f"Does not apply to {name}: {join(ql(q) for q in nas)}.")
        fbp = []
        if new_give:
            fbp.append("Here is what " + name + " shares: " + "; ".join(f"{ql(q)}: {val(q)}" for q in new_give) + ".")
        if checking:
            fbp.append(f"I'm checking with {name} about {join(ql(q) for q in checking)}.")
        if refuse:
            fbp.append(f"{join(ql(q) for q in refuse).capitalize()} stays with {name}: " + "; ".join(ALT.get(q, "it isn't needed") for q in refuse) + ".")
        if nas:
            fbp.append(f"{join(ql(q) for q in nas).capitalize()}: doesn't apply.")
        fb = " ".join(fbp) or f"Nothing more to add for {name}."
        out = await write("helmi", HELMI_SYS, f"Your owner is {name}. " + " ".join(parts) or fb, fb, forbidden=withheld_text())
        await say(n, "helmi", out, shared=new_give, kept=refuse)

    await helmi_turn(give, keepback, check, True)

    # 3. step in: the visitor decides on each "ask me" item
    later_yes, later_no = [], []
    for q in check:
        fut = asyncio.get_running_loop().create_future()
        WAIT[(n["nid"], q)] = fut
        STATS["stepins"] += 1
        push({"t": "stepin", "nid": n["nid"], "q": q, "label": Q[q]["l"], "why": Q[q]["why"], "value": val(q), "name": name}, n["vid"])
        try:
            ok = await asyncio.wait_for(fut, STEPIN_TIMEOUT)
        except asyncio.TimeoutError:
            ok = False
            push({"t": "stepin_timeout", "nid": n["nid"], "q": q}, n["vid"])
        WAIT.pop((n["nid"], q), None)
        push({"t": "stepin_done", "nid": n["nid"], "q": q, "ok": ok}, n["vid"])
        if ok:
            STATS["stepin_yes"] += 1
            later_yes.append(q)
        else:
            later_no.append(q)
    give += later_yes
    keepback += later_no
    if check:
        await helmi_turn(later_yes, later_no, [], False)

    # 4. the bot may push back once, on the first item it did not get
    push_q = next((q for q in ("passport", "health", "allergy", "dob", "spend") if q in keepback), None)
    if push_q:
        fb = {
            "passport": f"Understood. Reception will check {name}'s passport at the desk instead.",
            "health": f"That's fine. We'll prepare the room from the needs you've shared.",
        }.get(push_q, f"No problem, we don't need the {ql(push_q)} for the stay.")
        out = await write("bot", BOT_SYS,
                                f"Helmi will not share {ql(push_q)} for {name}. Accept this politely and say what the hotel will do instead "
                                f"({ALT.get(push_q, 'manage without it')}). Do not ask again.", fb)
        await say(n, "bot", out)

    # 5. the bot confirms what is prepared
    prepared = [val(q) for q in give if q not in ("arrival", "dob", "spend", "passport", "loyalty")]
    fb = (f"Thank you. Everything is ready for {name}" + (": " + "; ".join(prepared[:4]).rstrip(".") + "." if prepared else ".")
          + (" A colleague at reception will double-check the room plan." if H.get("review") and set(give) & {"access", "allergy", "health"} else ""))
    out = await write("bot", BOT_SYS,
                            f"Confirm the booking for {name} and say what the hotel has prepared, using only these details: {'; '.join(prepared) or 'none beyond the booking'}."
                            + (" Say a person at reception will double-check the room plan." if H.get("review") and set(give) & {"access", "allergy", "health"} else ""), fb)
    await say(n, "bot", out)

    # stats
    for q in asks:
        s = STATS["items"].setdefault(q, {"asked": 0, "shared": 0, "kept": 0, "na": 0})
        s["asked"] += 1
        s["shared" if q in give else "na" if q in na else "kept"] += 1
    if g["id"] in ("aino", "elina", "laura"):
        STATS["access_shared"] += len(set(give) & {"access", "health", "animal"})
    if form == "record" and "health" in give:
        STATS["records"] += 1
    STATS["done"] += 1
    push({"t": "done", "nid": n["nid"], "guest": g["id"], "shared": give, "kept": keepback, "na": na,
          "values": {q: val(q) for q in give}, "stats": STATS}, n["vid"])


async def run(n):
    QUEUE.append(n["nid"])
    try:
        while QUEUE.index(n["nid"]) >= 2 and SEM.locked():
            push({"t": "queue", "nid": n["nid"], "pos": QUEUE.index(n["nid"])}, n["vid"])
            await asyncio.sleep(2)
        async with SEM:
            QUEUE.remove(n["nid"])
            ACTIVE[n["nid"]] = n
            try:
                await negotiate(n)
            except Exception as e:  # never leave a phone hanging
                push({"t": "error", "nid": n["nid"], "text": "Something went wrong. Please try again."}, n["vid"])
                print("negotiation error", repr(e))
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
    q = asyncio.Queue(maxsize=300)
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


async def api_config(req: Request):
    b = await req.json()
    if STAND_KEY and b.get("key") != STAND_KEY:
        return JSONResponse({"ok": False, "error": "Wrong stand key"}, status_code=403)
    h = b.get("hotel") or {}
    HOTEL["asks"] = [q for q in h.get("asks", HOTEL["asks"]) if q in Q][:11]
    HOTEL["sum"] = bool(h.get("sum", HOTEL["sum"]))
    HOTEL["keep"] = h.get("keep") if h.get("keep") in KEEP else HOTEL["keep"]
    HOTEL["offers"] = [o for o in h.get("offers", HOTEL["offers"]) if o in OFFERS]
    HOTEL["trust"] = [t for t in h.get("trust", HOTEL["trust"]) if t in TRUST]
    HOTEL["review"] = bool(h.get("review", HOTEL["review"]))
    push({"t": "config", "hotel": HOTEL})
    for c in CLIENTS.values():  # visitors' phones update the request they see
        if c["role"] == "visitor":
            try:
                c["q"].put_nowait({"t": "config", "hotel": HOTEL, "at": time.time()})
            except asyncio.QueueFull:
                pass
    return JSONResponse({"ok": True, "hotel": HOTEL})


async def api_start(req: Request):
    b = await req.json()
    vid, guest = str(b.get("vid", ""))[:40], b.get("guest")
    if not vid or guest not in G:
        return JSONResponse({"ok": False, "error": "Choose a guest first"}, status_code=400)
    if vid in PENDING:
        return JSONResponse({"ok": False, "error": "Your Helmi is already negotiating"}, status_code=409)
    if len(QUEUE) >= 6:
        return JSONResponse({"ok": False, "error": "The stand is busy. Try again in a minute."}, status_code=429)
    pol = {k: v for k, v in (b.get("policy") or {}).items() if k in Q and v in ("share", "ask", "never")}
    n = {"nid": uuid.uuid4().hex[:10], "vid": vid, "guest": guest, "policy": pol, "form": "record" if b.get("form") == "record" else "need",
         "hotel": json.loads(json.dumps(HOTEL)), "log": []}
    STATS["n"] += 1
    PENDING[vid] = n["nid"]
    t = asyncio.create_task(run(n))
    TASKS.add(t)
    t.add_done_callback(TASKS.discard)
    return JSONResponse({"ok": True, "nid": n["nid"]})


async def api_answer(req: Request):
    b = await req.json()
    fut = WAIT.get((b.get("nid"), b.get("q")))
    if fut and not fut.done():
        fut.set_result(bool(b.get("ok")))
        return JSONResponse({"ok": True})
    return JSONResponse({"ok": False}, status_code=404)


async def api_diag(req: Request):
    """Try each model once with a tiny prompt and report what happened. Needs the stand key if one is set."""
    if STAND_KEY and req.query_params.get("key") != STAND_KEY:
        return JSONResponse({"ok": False, "error": "Add ?key=<your stand key>"}, status_code=403)
    out = {"ai_on": AI_ON, "key_set": bool(LLM_KEY), "key_looks_like": (LLM_KEY[:4] + "…" + str(len(LLM_KEY)) + " chars") if LLM_KEY else None,
           "base_url": LLM_URL, "models": {}}
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
    out["recent_errors"] = list(ERRORS)
    return JSONResponse(out)


async def api_reset(req: Request):
    b = await req.json()
    if STAND_KEY and b.get("key") != STAND_KEY:
        return JSONResponse({"ok": False}, status_code=403)
    STATS.update({"n": 0, "done": 0, "stepins": 0, "stepin_yes": 0, "items": {}, "access_shared": 0, "records": 0, "ai": 0, "script": 0})
    push({"t": "stats", "stats": STATS})
    return JSONResponse({"ok": True})


page = lambda f: (lambda req: FileResponse(STATIC / f))
app = Starlette(routes=[
    Route("/", page("live.html")),
    Route("/stand", page("stand.html")),
    Route("/events", events),
    Route("/api/state", api_state),
    Route("/api/ping", api_state),
    Route("/api/config", api_config, methods=["POST"]),
    Route("/api/start", api_start, methods=["POST"]),
    Route("/api/answer", api_answer, methods=["POST"]),
    Route("/api/reset", api_reset, methods=["POST"]),
    Route("/api/diag", api_diag),
    Mount("/static", StaticFiles(directory=STATIC)),
])
