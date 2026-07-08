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

### Mac — one command

Paste this into Terminal (⌘-space, type "Terminal", Enter):

```bash
curl -fsSL https://raw.githubusercontent.com/samuelharold1990-blip/new-friend/claude/chat-friend-app-36po3l/get.sh | bash
```

It installs everything — the app (to `~/Companion`), Python deps, Ollama and
her models — puts a **Companion** launcher on your Desktop, and opens the app
in your browser. From then on, just double-click `Companion.command` on the
Desktop. Safe to re-run any time to update; your conversations are preserved.

### Windows / manual

1. **Install [Ollama](https://ollama.com/download)** (the local AI she thinks with).
2. Clone or download this repo, then run `install.bat` (Windows) or
   `bash install.sh` (Mac/Linux). Start with `start.bat` or
   `./.venv/bin/python run.py`.
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
| Memory | Every few messages, a background LLM call extracts facts about you ("sister Emma in Denver", "started climbing in June") into a local database. **Semantic recall**: each message is matched against her memories with a local embedding model (`ollama pull nomic-embed-text`) so the *relevant* memory surfaces — mention your sister and she remembers Denver, even months later. View or delete anything in Settings → Memory. |
| Her own life | She wakes up to a small, plausible day of her own (a run, a cafe afternoon, a movie night) — invented fresh each day and kept consistent: ask "what are you up to?" at 2pm and 4pm and her story holds, her selfies match what she said she was doing, and her away-texts reference her actual day. |
| Relationship | A score grows with real conversation over real days (grinding one long night won't skip stages): **new → friendly → close → romantic**. Each stage warms her tone, unlocks photo moods, and makes her more proactive. |
| Her photos | She decides when a photo fits the moment. Photos come from the `photos/` pack — or are generated live: the app **finds your local Stable Diffusion by itself** (see below). |
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

### Optional: generated photos (needs a GPU, ~8GB+ VRAM)

Run [AUTOMATIC1111](https://github.com/AUTOMATIC1111/stable-diffusion-webui)
(launched with `--api`) or [ComfyUI](https://github.com/comfyanonymous/ComfyUI)
locally — **that's it**. The app probes the standard ports (7860 / 8188) on
startup, connects itself, and picks the most photoreal checkpoint you have
installed. Everything falls back to the photo pack automatically if the server
is busy or offline. Flip it off in Settings if you ever want pack-only.

**Which model?** Good local checkpoints for realistic phone-style selfies:

- **CyberRealistic Pony** — the Pony Diffusion XL lineage with photoreal
  rendering; great character variety. The app detects Pony-family checkpoints
  by name and automatically adds the `score_9, score_8_up…` quality tags and
  anime/cartoon negatives they need.
- **Juggernaut XL** or **RealVisXL** — the community's go-to pure-photoreal
  SDXL models; the most "actual phone photo" look.
- Base Pony Diffusion V6 XL is stylized (anime-leaning) — for realistic selfies
  prefer one of the realism merges above.

Download one from Civitai/Hugging Face into your SD models folder; the app
will find it (or set it explicitly in Settings → Her photos).

**The same face every time (reference photos).** Generate portraits until you
find *her*, save 1–3 face shots into `photos/reference/`, and install the
[ComfyUI IPAdapter Plus](https://github.com/cubiq/ComfyUI_IPAdapter_plus)
custom nodes (FaceID Plus V2 preset). Every selfie is then conditioned on her
reference face (weight 0.85), so she looks like the same person across every
mood, outfit and setting. No reference photos or no FaceID nodes? The app
automatically uses the plain workflow with a fixed seed instead. Power users
can swap `companion/services/comfy_workflow_faceid.json` for their own
API-format workflow export — keep the `{{PROMPT}}`-style placeholders.

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
