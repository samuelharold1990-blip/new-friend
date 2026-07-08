#!/usr/bin/env bash
# Companion — one-command install for macOS (works on Linux too).
#
#   curl -fsSL https://raw.githubusercontent.com/samuelharold1990-blip/new-friend/claude/chat-friend-app-36po3l/get.sh | bash
#
# What it does: downloads the app to ~/Companion, sets up Python deps,
# installs/starts Ollama, pulls the models, puts a launcher on your Desktop,
# then starts the app and opens it in your browser. Safe to re-run: your
# conversations (data/) and any photos you added are preserved.
set -euo pipefail

REPO_TARBALL="https://github.com/samuelharold1990-blip/new-friend/archive/refs/heads/claude/chat-friend-app-36po3l.tar.gz"
APP_DIR="$HOME/Companion"
CHAT_MODEL="llama3.1:8b"
EMBED_MODEL="nomic-embed-text"

say()  { printf '\033[1;35m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*"; }

# --- 1. Python -----------------------------------------------------------
say "Checking Python…"
if ! python3 --version >/dev/null 2>&1; then
  warn "Python 3 isn't ready. On a Mac, a dialog may have just appeared —"
  warn "click 'Install' (Command Line Tools), wait for it to finish, then run this command again."
  exit 1
fi

# --- 2. Download the app --------------------------------------------------
say "Downloading Companion to $APP_DIR…"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
curl -fsSL "$REPO_TARBALL" | tar -xz -C "$TMP"
SRC="$(find "$TMP" -maxdepth 1 -type d -name 'new-friend-*' | head -1)"
mkdir -p "$APP_DIR"
# copy over the top (never deletes): data/ and your own photos are untouched
cp -R "$SRC"/. "$APP_DIR"/

# --- 3. Python dependencies ----------------------------------------------
say "Setting up Python environment…"
cd "$APP_DIR"
python3 -m venv .venv
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -r requirements.txt

# --- 4. Ollama -------------------------------------------------------------
if ! command -v ollama >/dev/null 2>&1 && [ ! -x "/Applications/Ollama.app/Contents/Resources/ollama" ]; then
  say "Installing Ollama (the local AI she thinks with)…"
  if command -v brew >/dev/null 2>&1; then
    brew install --quiet ollama || warn "brew install failed"
  elif [ "$(uname)" = "Darwin" ]; then
    curl -fsSL -o "$TMP/Ollama.zip" https://ollama.com/download/Ollama-darwin.zip
    ditto -xk "$TMP/Ollama.zip" /Applications/
  else
    curl -fsSL https://ollama.com/install.sh | sh || warn "Ollama install failed"
  fi
fi

# make the CLI reachable even when Ollama is app-only
OLLAMA_BIN="$(command -v ollama || true)"
[ -z "$OLLAMA_BIN" ] && [ -x "/Applications/Ollama.app/Contents/Resources/ollama" ] \
  && OLLAMA_BIN="/Applications/Ollama.app/Contents/Resources/ollama"

if [ -n "$OLLAMA_BIN" ]; then
  # start the Ollama server if it isn't running
  if ! curl -fsS http://localhost:11434/api/version >/dev/null 2>&1; then
    say "Starting Ollama…"
    if [ -d "/Applications/Ollama.app" ]; then
      open -a Ollama || true
    else
      nohup "$OLLAMA_BIN" serve >/dev/null 2>&1 &
    fi
    for _ in $(seq 1 30); do
      curl -fsS http://localhost:11434/api/version >/dev/null 2>&1 && break
      sleep 1
    done
  fi
  say "Downloading her brain ($CHAT_MODEL, ~5GB — one time, grab a coffee)…"
  "$OLLAMA_BIN" pull "$CHAT_MODEL" || warn "model pull failed — run '$OLLAMA_BIN pull $CHAT_MODEL' later"
  say "Downloading the memory model ($EMBED_MODEL, small)…"
  "$OLLAMA_BIN" pull "$EMBED_MODEL" || true
else
  warn "Ollama couldn't be installed automatically."
  warn "Get it from https://ollama.com/download, then run: ollama pull $CHAT_MODEL"
fi

# --- 5. Desktop launcher ----------------------------------------------------
if [ "$(uname)" = "Darwin" ] && [ -d "$HOME/Desktop" ]; then
  cat > "$HOME/Desktop/Companion.command" <<EOF
#!/usr/bin/env bash
cd "$APP_DIR"
[ -d /Applications/Ollama.app ] && open -a Ollama
( sleep 2 && open http://localhost:8320 ) &
exec ./.venv/bin/python run.py
EOF
  chmod +x "$HOME/Desktop/Companion.command"
  say "Put a launcher on your Desktop: Companion.command (double-click it any time)"
fi

# --- 6. Launch --------------------------------------------------------------
say "Starting Companion…"
( sleep 2 && { command -v open >/dev/null && open http://localhost:8320 || true; } ) &
echo ""
echo "  She's at:  http://localhost:8320"
echo "  (leave this window open while you chat; press Ctrl+C to stop her)"
echo ""
exec ./.venv/bin/python run.py
