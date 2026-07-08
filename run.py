#!/usr/bin/env python3
"""Launcher for the companion app.

Usage:
    python run.py [--host 127.0.0.1] [--port 8320] [--data-dir ./data]

Set MOCK_OLLAMA=1 to run without a real Ollama install (canned replies,
useful for trying the UI or developing).
"""
import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local companion chat app")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Bind address. Use 0.0.0.0 to reach the app from your phone on the same wifi.")
    parser.add_argument("--port", type=int, default=8320)
    parser.add_argument("--data-dir", default=None,
                        help="Where the database, uploads and generated photos live (default: ./data)")
    args = parser.parse_args()

    if args.data_dir:
        os.environ["COMPANION_DATA_DIR"] = args.data_dir

    import uvicorn
    uvicorn.run("companion.main:app", host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
