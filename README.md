# Helmi Live

Live negotiations between AI agents: **Helmi**, a personal assistant acting for a traveller, and the bots of every place on the trip: the airline or train, the hotel, the restaurant, the venue, the insurer and optional extras such as a taxi or pharmacy. Built for the Demola *Data for Value* project (Tampere University) and shown at a demo fair.

Visitors play one of nine invented travellers (eight people and one family) on their phone, choose the places on their trip and set a rule for each detail. Helmi then negotiates with each place in turn. The visitor's phone buzzes when Helmi needs a decision, and some businesses come back with an offer (a discount, a free companion ticket) to see whether a benefit changes the answer. At the end, they can watch a replay film of their trip, narrated by the phone's voice. A stand screen shows the negotiations live, lets you pick any business and set up its bot, and charts what travellers shared by place and by kind of detail.

All people, businesses and data in this project are invented.

## The idea in one line

**The AI writes the words. The person's rules decide what data moves.**

Language models only phrase the messages. Every decision about data is made in code:

- A detail leaves Helmi only if the guest's rule is **Share**, or the guest taps **Share it** when asked.
- Details marked **Ask me** wait for the guest. With no answer within 45 seconds, Helmi keeps them.
- Details marked **Never** are never sent, whatever a business offers.
- Every business asks separately, even a restaurant owned by the hotel. Helmi never reuses what was shared with another place.
- If a business makes an offer for something the visitor declined, the visitor is asked again. Their answer is final.
- Each model only sees the details it is allowed to mention. If a message still mentions something that wasn't shared, it is discarded and replaced with a safe scripted line, and both screens say so.
- Requests mix **needs** ("seat with floor space for the guide dog") with **records** (diagnoses, the disability card) and **lots of data** (bank transactions, chats). The visitor sees which is which.

## What's in the repo

| Path | What it is |
|---|---|
| `server.py` | The negotiation server (Starlette). Runs the agents, enforces the rules, streams events |
| `static/live.html` | Phone page for visitors: pick a traveller and places, set Helmi's rules, follow the trip |
| `static/stand.html` | Stand screen: pick a business and set up its bot, watch negotiations live, see share rates by place and by detail |
| `static/film.js`, `static/film.css` | The replay film at the end of a trip (the same animation engine as the trip-mode demo) |
| `static/trip.json` | The nine invented travellers, the places on each trip, what each place asks for, and every detail's value |
| `requirements.txt`, `render.yaml`, `.python-version` | Deployment on Render |

## How it works

```
 phone (Helmi's side)            server                       stand screen (hotel's side)
 ─────────────────────           ──────                       ───────────────────────────
 choose person, places, rules ─POST─▶ /api/start              hotel settings ──POST──▶ /api/config
                                   │
                                   │  for each place on the trip:
                                   ├─ business bot asks      (BOT_MODEL)
                                   ├─ code decides each detail: share / ask / never
                                   ├─ Helmi replies          (HELMI_MODEL)
 "Helmi needs you"  ◀──event───────┤  step-in for "ask me" details
 tap Share / Don't  ──POST──▶ /api/answer
                                   ├─ bot pushes back once: an offer, or an alternative
 "An offer"         ◀──event───────┤  if offered, the visitor decides again
                                   └─ bot confirms what is prepared
 live messages      ◀──────── /events (Server-Sent Events) ────────▶ live messages + stats
```

- **Bots with names:** each business's bot has its own name and manner, for example Vera (train, brisk), Otto (hotel concierge), Maija (restaurant), Lumi (venue), Kasper (insurer, persuasive) and Pippa (kids club). Each one can be set up from the stand.
- **Models:** Helmi uses `openai/gpt-oss-120b`, the hotel uses `qwen/qwen3.8-27b`, and `openai/gpt-oss-20b` is the backup. All run on Groq's free tier through its OpenAI-compatible API. Any OpenAI-compatible endpoint works, including a local model through Ollama.
- **Limits:** the server tracks tokens per model per minute, runs two negotiations at a time and queues the rest. It falls back to the backup model, then to scripted lines.
- **No storage:** nothing is written to disk. Settings and stats live in memory and reset when the server restarts.
- **Stand settings (any business's bot):** pick a business, then choose which kinds of detail its bot asks for, accessible options it offers (step-free rooms, screen-reader check-in form, keypad card terminals, staff briefed on assistance animals), promises shown to guests' assistants, retention, human review, and whether the bot comes back with an offer or alternative when something is kept.

## Run locally

Python 3.11 or newer.

```
pip install -r requirements.txt
uvicorn server:app --port 8000
```

- Phone page: http://localhost:8000/
- Stand screen: http://localhost:8000/stand

Without an API key, messages are scripted and everything else works. To use the models, set `GROQ_API_KEY` before starting.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `GROQ_API_KEY` | none | Groq API key. Without it, messages are scripted |
| `STAND_KEY` | none | Password needed to change the hotel's settings. Open the stand as `/stand?key=…` |
| `HELMI_MODEL` | `openai/gpt-oss-120b` | Writes Helmi's messages |
| `BOT_MODEL` | `qwen/qwen3.8-27b` | Writes the hotel bot's messages |
| `BACKUP_MODEL` | `openai/gpt-oss-20b` | Used when a model is at its limit |
| `LLM_BASE_URL` | `https://api.groq.com/openai/v1` | Any OpenAI-compatible API, e.g. `http://localhost:11434/v1` for Ollama |
| `TOKENS_PER_MINUTE` | `7000` | Per-model budget, under Groq's free 8K |
| `PACE_SECONDS` | `1.0` | Fixed pause after every message |
| `READ_WPM` | `200` | Each message also stays up for the time it takes to read at this many words a minute. Lower is slower |
| `MAX_PAUSE_SECONDS` | `14` | Longest pause after any one message |

## Deploy

`render.yaml` describes a free Render web service:

- build `pip install -r requirements.txt`
- start `uvicorn server:app --host 0.0.0.0 --port $PORT`

Add `GROQ_API_KEY` and `STAND_KEY` as environment variables in the Render dashboard. Never put them in the repo.

## API

| Method | Path | Body | |
|---|---|---|---|
| GET | `/events?role=stand` or `?vid=<visitor id>` | | Event stream: `hello`, `config`, `start`, `place`, `msg`, `stepin`, `stepin_done`, `stepin_timeout`, `place_done`, `queue`, `done`, `error`, `stats` |
| GET | `/api/diag?key=…` | | Tries each model once and shows recent model errors |
| GET | `/api/state` | | Hotel settings, stats, models, active trips |
| GET | `/api/requests?person=<id>` | | What each place on that person's trip asks for, with the current hotel settings |
| POST | `/api/start` | `{vid, person, places:[ids], policy:{detail:"share"\|"ask"\|"never"}}` | Start a trip |
| POST | `/api/answer` | `{nid, place, k, ok}` | Answer a step-in or an offer |
| POST | `/api/config` | `{key, biz, settings}` | Change one business's bot settings (`biz` is e.g. `hotel`, `ins`, `rail`) |
| POST | `/api/reset` | `{key}` | Reset the stand's numbers |

## Related

- Main demo (trip mode, business mode, researcher page): https://selorme.github.io/data-for-value-demo/
- Project journey: https://selorme.github.io/data-for-value-demo/journey/

Made by Ruth, Dora, Towhidul and Rui for the Demola Data for Value challenge, 2026.
