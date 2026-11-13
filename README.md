# Helmi live: the demo fair stand

Visitors scan a QR code and play an invented guest on their phone. They set what their Helmi may share, then Helmi negotiates with Hotel Merikaari's booking bot. The stand screen shows the hotel's side live, plus what guests shared.

- **Phone page:** `https://<your-service>.onrender.com/`
- **Stand screen:** `https://<your-service>.onrender.com/stand?key=<your stand key>`

Two AI models write the messages: Helmi uses `openai/gpt-oss-120b` and the hotel's bot uses `qwen/qwen3.8-27b`, with `openai/gpt-oss-20b` as a backup. **The code decides what data moves.** A detail leaves Helmi only if the visitor's rule says "Share", or the visitor taps "Share it" when pinged. If a model's message mentions anything that wasn't shared, the server throws the message away and uses a safe scripted line, and the screen says so. With no API key, every message is scripted and everything else still works.

Everything is synthetic. Nothing is stored on disk: the numbers on the stand reset when the service restarts.

## Put it on Render (about 15 minutes)

1. **Put this folder on GitHub.** Make a new repository (for example `helmi-live`) and upload everything in this folder: `server.py`, `requirements.txt`, `render.yaml`, `.python-version`, `README.md` and the `static` folder. Don't upload the `test` folder. On Windows, `.python-version` may be hidden; if it doesn't upload, it doesn't matter.
2. **Create the service.** On render.com choose **New > Web Service**, connect your GitHub and pick the `helmi-live` repository.
   - Runtime: **Python**
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn server:app --host 0.0.0.0 --port $PORT`
   - Instance type: **Free**
3. **Add the settings.** Under **Environment**, add:
   - `GROQ_API_KEY`: your Groq key
   - `STAND_KEY`: any password you choose, for example `merikaari18`. Only someone with it can change the hotel's settings from the stand screen.
4. **Deploy.** Render gives you an address like `https://helmi-live-xxxx.onrender.com`. Open it: you should see "Send your Helmi to book a hotel".
5. **Open the stand screen** at `/stand?key=<your STAND_KEY>`. The QR code on the right points to the phone page.

Keep this as a separate Render service from your personal site, so a busy stand can't affect it.

## On the day

- **Open the stand screen at least 5 minutes before 11:30.** A free Render service sleeps after 15 minutes without visitors and takes about a minute to wake. The stand screen pings the server every 4 minutes, so it stays awake while it's open.
- **Use "Reset today's numbers"** after you've tested, so the stand starts at zero.
- **Change the hotel's settings live** in the left column. Business people can try asking for less, adding the keypad terminal or promising deletion at checkout, then watch the next guest's negotiation and the share rates.
- **If the Wi-Fi fails,** the offline business mode still works on the laptop: `trip.html#business` from the demo folder.

## Free limits

Each model allows about 8,000 tokens a minute on Groq's free plan. One negotiation uses roughly 3,000–5,000 tokens across both models. The server runs two negotiations at a time, queues the rest (visitors see "you are number 2 in the queue"), and switches to the backup model or to scripted lines when a model is at its limit. Expect 60–80 AI negotiations over the day.

## Settings you can change on Render

| Setting | Default | What it does |
|---|---|---|
| `HELMI_MODEL` | `openai/gpt-oss-120b` | Model that writes Helmi's messages |
| `BOT_MODEL` | `qwen/qwen3.8-27b` | Model that writes the hotel bot's messages |
| `BACKUP_MODEL` | `openai/gpt-oss-20b` | Used when either is at its limit |
| `TOKENS_PER_MINUTE` | `7000` | Stays under Groq's 8K per minute |
| `PACE_SECONDS` | `1.4` | Pause between messages, so people can read |
| `LLM_BASE_URL` | Groq | Any OpenAI-compatible server, for example a local model |

## Running it on the laptop instead (optional)

You need Python 3.11 or newer.

```
pip install -r requirements.txt
set GROQ_API_KEY=your-key-here
uvicorn server:app --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000/stand`. Phones on the same network open `http://<laptop's IP>:8000/`. Many guest Wi-Fi networks stop phones reaching a laptop, so Render is the safer choice at the fair.

For a fully offline version with a local model, install Ollama, run `ollama pull llama3.2:3b`, and start the server with:

```
set LLM_BASE_URL=http://localhost:11434/v1
set HELMI_MODEL=llama3.2:3b
set BOT_MODEL=llama3.2:3b
set BACKUP_MODEL=llama3.2:3b
uvicorn server:app --host 0.0.0.0 --port 8000
```

Expect several seconds per message on a laptop without a graphics card.
