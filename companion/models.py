"""Pydantic schemas: persisted settings and API request bodies."""
from __future__ import annotations

from pydantic import BaseModel, Field


class CharacterCard(BaseModel):
    name: str = "Mira"
    personality: str = (
        "warm, playful and a little witty; genuinely curious about your day; "
        "loves cozy mornings, indie music, photography and long walks"
    )
    appearance: str = (
        "a woman in her mid twenties with long wavy chestnut hair, hazel eyes, "
        "a soft smile and a casual relaxed style"
    )


class AppSettings(BaseModel):
    ollama_url: str = "http://localhost:11434"
    model: str = "llama3.1:8b"
    vision_enabled: bool = False
    vision_model: str = "llava"
    sd_enabled: bool = False
    sd_backend: str = "a1111"  # 'a1111' | 'comfyui'
    sd_url: str = "http://localhost:7860"
    sd_checkpoint: str = ""  # e.g. "cyberrealisticPony_v90.safetensors"; empty = server default
    sd_prompt_prefix: str = ""  # e.g. "score_9, score_8_up, score_7_up" for Pony-family models
    character_seed: int = 20260708
    embedding_model: str = "nomic-embed-text"  # empty string disables semantic memory
    user_name: str = ""
    realistic_typing: bool = True
    character: CharacterCard = Field(default_factory=CharacterCard)


class ChatRequest(BaseModel):
    text: str = ""
    upload_id: str | None = None


class OnboardingRequest(BaseModel):
    model: str
    user_name: str
    character: CharacterCard = Field(default_factory=CharacterCard)


class TestConnectionRequest(BaseModel):
    kind: str  # 'ollama' | 'a1111' | 'comfyui'
    url: str


class FactUpdate(BaseModel):
    content: str


class WipeRequest(BaseModel):
    confirm: str


class GeneratePhotoRequest(BaseModel):
    mood: str = "selfie_generic"
