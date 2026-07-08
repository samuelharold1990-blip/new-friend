# Companion 💬

A chat app for texting back and forth with an AI companion who — over days and
weeks — gets to know you, remembers your life, and sends you photos of herself.

**Everything runs on your own machine.** The AI is a local open-source model via
[Ollama](https://ollama.com), all conversations live in a local SQLite file, and
photos come from a local folder or an optional local Stable Diffusion server.
No cloud APIs. No accounts. Nothing ever leaves your computer.

<p>
  <em>iMessage-style chat · streaming replies with a typing indicator · photo
  messages · memory of your life · relationship that deepens over time ·
  "while you were away" texts when you come back</em>
</p>

## Quick start

1. **Install [Ollama](https://ollama.com/download)** and pull a model:

   ```bash
   ollama pull llama3.1:8b
   ```

2. **Install and run the app** (Python 3.10+):

   ```bash
   pip install -r requirements.txt
   python run.py
   ```

3. Open **http://localhost:8320** — a short setup wizard checks your Ollama
   install, lets you pick a model, and lets you shape who she is. Then just text her.

No Ollama yet? Try the UI first with canned replies:

```bash
MOCK_OLLAMA=1 python run.py
```

## How it works

| Feature | How |
|---|---|
| Chat | Streams token-by-token from your local Ollama (`/api/chat`) with a typing indicator |
| Memory | Every few messages, a background LLM call extracts facts about you ("sister Emma in Denver", "started climbing in June") into a local database. She references them naturally later. View or delete any of them in Settings → Memory. |
| Relationship | A score grows with real conversation over real days (grinding one long night won't skip stages): **new → friendly → close → romantic**. Each stage warms her tone, unlocks photo moods, and makes her more proactive. |
| Her photos | She decides when a photo fits the moment. Photos come from the `photos/` pack — or are generated live if you connect Stable Diffusion. |
| Your photos | Send her photos; with a local vision model (`ollama pull llava`, enable in Settings) she actually sees them and reacts. Without one she reacts warmly and asks about them. |
| Away texts | When you come back after hours or days, she's "sent" you a few texts in the meantime — timestamped realistically while you were gone. |

## Her photo pack

The repo ships with placeholder images so everything works out of the box.
To give her real photos, drop images into the mood folders — she picks the one
that fits what she's saying:

```
photos/
  morning/   coffee/   gym/   outdoors/   selfie_generic/
  evening/   cozy/     dressed_up/
```

Cozier moods unlock as you get closer. `photos/manifest.json` can tweak
descriptions and unlock stages.

### Optional: generated photos (needs a GPU)

If you run [AUTOMATIC1111](https://github.com/AUTOMATIC1111/stable-diffusion-webui)
(launched with `--api`) or [ComfyUI](https://github.com/comfyanonymous/ComfyUI)
locally, enable it in Settings → Her photos. Selfies are then generated fresh
from her appearance description with a fixed seed for a consistent look, and
fall back to the photo pack automatically if the server is busy or offline.

## Using it from your phone

Run the server so it's reachable on your home network, then open your
computer's address from your phone and add it to your home screen:

```bash
python run.py --host 0.0.0.0
# on your phone: http://<your-computer-ip>:8320
```

## Your data

- Everything lives in `data/` next to the app: one SQLite database plus your
  uploaded and generated photos.
- **Settings → Your data** exports everything as JSON, or erases it all.
- The app makes network requests only to the local URLs you configure
  (Ollama / Stable Diffusion).

## Development

```bash
pip install -r requirements.txt
python -m pytest tests/            # full suite runs against a mock LLM
MOCK_OLLAMA=1 python run.py        # run the app without Ollama
python scripts/gen_placeholders.py # regenerate placeholder images/icons
```

Stack: FastAPI + SQLite (stdlib) + vanilla-JS PWA. No build step, no Node.
