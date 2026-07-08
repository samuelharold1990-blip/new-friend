#!/usr/bin/env bash
# One-command install for Mac/Linux:  bash install.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "== Companion installer =="

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required. Install it from https://www.python.org/downloads/ and re-run."
  exit 1
fi

echo "-> creating virtual environment"
python3 -m venv .venv
./.venv/bin/pip install --quiet --upgrade pip
echo "-> installing dependencies"
./.venv/bin/pip install --quiet -r requirements.txt

if command -v ollama >/dev/null 2>&1; then
  echo "-> Ollama found"
  if ! ollama list 2>/dev/null | grep -q llama3.1; then
    echo "-> pulling the default chat model (llama3.1:8b, ~5GB — one time)"
    ollama pull llama3.1:8b || echo "   (pull failed — you can run 'ollama pull llama3.1:8b' later)"
  fi
else
  echo ""
  echo "!! Ollama is not installed — the app needs it to think."
  echo "   Install it from https://ollama.com/download then run: ollama pull llama3.1:8b"
fi

echo ""
echo "Done. Start her with:"
echo "  ./.venv/bin/python run.py"
echo "then open http://localhost:8320"
