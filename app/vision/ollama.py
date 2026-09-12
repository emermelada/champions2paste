"""Local engine via Ollama. Needs a machine with some muscle (GPU or fast x86 CPU)."""

from __future__ import annotations

import base64
import json
import os

import httpx

from ..schema import RawTeam
from .base import PROMPT


class OllamaBackend:
    name = "ollama"

    def __init__(self) -> None:
        self.host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        self.model = os.environ.get("OLLAMA_MODEL", "qwen3-vl:8b")
        # A VLM reading two dense screenshots takes a while; httpx's default
        # timeout (5s) would cut every request short.
        self.timeout = float(os.environ.get("OLLAMA_TIMEOUT", "600"))

    def extract(self, images: list[tuple[str, bytes]]) -> RawTeam:
        payload = {
            "model": self.model,
            "stream": False,
            # Ollama accepts a JSON Schema in `format` and constrains decoding to
            # it, so we get the same structural guarantee as with Claude.
            "format": RawTeam.model_json_schema(),
            "options": {"temperature": 0},
            "messages": [{
                "role": "user",
                "content": PROMPT,
                "images": [base64.b64encode(data).decode() for _, data in images],
            }],
        }

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(f"{self.host}/api/chat", json=payload)
            response.raise_for_status()
            body = response.json()

        content = body.get("message", {}).get("content", "")
        if not content.strip():
            raise RuntimeError(f"Model {self.model} returned an empty response")

        try:
            return RawTeam.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValueError) as exc:
            raise RuntimeError(f"Invalid response from {self.model}: {exc}") from exc
