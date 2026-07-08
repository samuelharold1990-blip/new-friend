"""Async client for a local Ollama server, plus a mock with the same
interface so the whole app can run and be tested without Ollama installed
(MOCK_OLLAMA=1, or set the Ollama URL to mock://).
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import AsyncIterator

import httpx

VISION_NAME_HINTS = ("llava", "vision", "moondream", "bakllava", "qwen-vl", "qwen2-vl", "minicpm-v")


def is_vision_model(name: str) -> bool:
    n = name.lower()
    return any(h in n for h in VISION_NAME_HINTS)


class OllamaClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def ping(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                r = await client.get(f"{self.base_url}/api/version")
                return r.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{self.base_url}/api/tags")
            r.raise_for_status()
            models = r.json().get("models", [])
        return [{"name": m["name"], "is_vision": is_vision_model(m["name"])} for m in models]

    async def chat_stream(self, model: str, messages: list[dict],
                          options: dict | None = None) -> AsyncIterator[str]:
        payload = {"model": model, "messages": messages, "stream": True}
        if options:
            payload["options"] = options
        async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=5)) as client:
            async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        yield chunk
                    if data.get("done"):
                        break

    async def chat_json(self, model: str, messages: list[dict]) -> dict:
        """Non-streaming call with format=json; returns the parsed object."""
        payload = {
            "model": model, "messages": messages, "stream": False,
            "format": "json", "options": {"temperature": 0},
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=5)) as client:
            r = await client.post(f"{self.base_url}/api/chat", json=payload)
            r.raise_for_status()
            content = r.json().get("message", {}).get("content", "")
        return json.loads(content)

    async def chat_vision(self, model: str, prompt: str, image_b64: str) -> str:
        payload = {
            "model": model, "stream": False,
            "messages": [{"role": "user", "content": prompt, "images": [image_b64]}],
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(300, connect=5)) as client:
            r = await client.post(f"{self.base_url}/api/chat", json=payload)
            r.raise_for_status()
            return r.json().get("message", {}).get("content", "")


class MockOllamaClient:
    """Deterministic stand-in that exercises every feature path:

    - mentions of selfie/pic/photo in the user's message trigger a
      [SELFIE: coffee] tag so the photo pipeline runs
    - extraction prompts get valid facts/summary JSON
    - catch-up prompts get valid texts JSON
    """

    REPLIES = [
        "aww I was just thinking about you! how's your day going?",
        "haha okay that's actually really cute. tell me more?",
        "mm I've been curled up with a playlist and my camera roll, very on brand for me",
        "you always know how to make me smile. what are you up to right now?",
        "okay noted!! I'm remembering that about you forever, just so you know",
    ]

    def __init__(self, base_url: str = "mock://"):
        self.base_url = base_url
        self._i = 0

    async def ping(self) -> bool:
        return True

    async def list_models(self) -> list[dict]:
        return [
            {"name": "mock-chat:latest", "is_vision": False},
            {"name": "mock-llava:latest", "is_vision": True},
        ]

    def _pick_reply(self, messages: list[dict]) -> str:
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        if re.search(r"\b(selfie|pic|photo|picture)\b", last_user, re.I):
            return "okay okay, just for you… took this a minute ago ☕\n[SELFIE: coffee]"
        reply = self.REPLIES[self._i % len(self.REPLIES)]
        self._i += 1
        return reply

    async def chat_stream(self, model: str, messages: list[dict],
                          options: dict | None = None):
        text = self._pick_reply(messages)
        # stream in small chunks so the tag-across-chunks path is exercised
        for i in range(0, len(text), 7):
            await asyncio.sleep(0.01)
            yield text[i:i + 7]

    async def chat_json(self, model: str, messages: list[dict]) -> dict:
        blob = " ".join(m["content"] for m in messages)
        if "new_facts" in blob:
            return {
                "new_facts": [{"category": "hobbies", "content": "User is trying out this app"}],
                "updated_facts": [],
                "summary": "You and the user have been chatting casually and getting to know each other.",
            }
        if '"texts"' in blob or "short texts" in blob:
            return {"texts": ["good morning!! hope today is kind to you ☀️",
                              "was just thinking about our last chat and smiling"]}
        return {}

    async def chat_vision(self, model: str, prompt: str, image_b64: str) -> str:
        return "A photo the user shared; it looks like a casual snapshot from their day."


def make_client(config, settings) -> OllamaClient | MockOllamaClient:
    if config.mock_ollama or settings.ollama_url.startswith("mock"):
        return MockOllamaClient(settings.ollama_url)
    return OllamaClient(settings.ollama_url)
