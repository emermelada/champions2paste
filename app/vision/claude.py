"""Motor via la API de Claude. Funciona en cualquier hardware, incluido un NAS ARM."""

from __future__ import annotations

import os

import anthropic

from ..schema import RawTeam
from .base import PROMPT


class ClaudeBackend:
    name = "claude"

    def __init__(self) -> None:
        # El cliente sin argumentos resuelve la credencial por su cuenta:
        # ANTHROPIC_API_KEY, o el perfil OAuth de `ant auth login`.
        self.client = anthropic.Anthropic()
        self.model = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5")

    def extract(self, images: list[tuple[str, bytes]]) -> RawTeam:
        import base64

        content: list[dict] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": base64.b64encode(data).decode(),
                },
            }
            for media_type, data in images
        ]
        content.append({"type": "text", "text": PROMPT})

        response = self.client.messages.parse(
            model=self.model,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": content}],
            output_format=RawTeam,
        )

        if response.stop_reason == "refusal":
            raise RuntimeError("La API rechazo la peticion (stop_reason=refusal)")

        if response.parsed_output is None:
            raise RuntimeError("La API no devolvio un equipo utilizable")

        return response.parsed_output
