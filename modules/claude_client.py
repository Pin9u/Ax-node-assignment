"""Thin wrapper around the Anthropic SDK with prompt caching enabled.

We expose two helpers:
- ``call_text``  : text-only system+user call returning a string.
- ``call_vision``: image+text call returning a string.

System prompts are sent with ``cache_control={"type": "ephemeral"}`` so that
the long, static auditor-persona instructions in ``modules.prompts`` are
served from cache on every subsequent request within a session.
"""

from __future__ import annotations

import base64
import os
from typing import Optional

import anthropic


DEFAULT_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
DEFAULT_VISION_MODEL = os.getenv("CLAUDE_VISION_MODEL", DEFAULT_MODEL)


def _client(api_key: Optional[str]) -> anthropic.Anthropic:
    key = api_key or os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is missing. Paste it in the sidebar or set it in .env."
        )
    return anthropic.Anthropic(api_key=key)


def call_text(
    system_prompt: str,
    user_prompt: str,
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = 4096,
    temperature: float = 0.1,
) -> str:
    client = _client(api_key)
    resp = client.messages.create(
        model=model or DEFAULT_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_prompt}],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def call_vision(
    system_prompt: str,
    user_prompt: str,
    image_bytes: bytes,
    mime_type: str = "image/png",
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = 3000,
    temperature: float = 0.0,
) -> str:
    client = _client(api_key)
    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    resp = client.messages.create(
        model=model or DEFAULT_VISION_MODEL,
        max_tokens=max_tokens,
        temperature=temperature,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime_type,
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": user_prompt},
                ],
            }
        ],
    )
    return "".join(b.text for b in resp.content if b.type == "text").strip()
