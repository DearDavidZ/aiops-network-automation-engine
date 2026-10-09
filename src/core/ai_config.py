"""Configuración validada antes de abrir el cliente del proveedor."""

import os
import re
from dataclasses import dataclass, field

from google.genai import types


class AIConfigurationError(ValueError):
    """Errores locales cuyo texto no incluye secretos ni valores del usuario."""


def bounded_integer(name: str, default: int, minimum: int, maximum: int) -> int:
    """Nunca incluye el valor recibido en el mensaje de error."""
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        raise AIConfigurationError(f"{name}: debe ser un entero") from None
    if not minimum <= value <= maximum:
        raise AIConfigurationError(f"{name}: fuera de rango")
    return value


@dataclass(frozen=True)
class AISettings:
    api_key: str = field(repr=False)
    model: str
    timeout_ms: int
    max_payload_chars: int

    @classmethod
    def from_environment(cls) -> "AISettings":
        api_key = os.environ.get("AI_API_KEY", "").strip()
        if not api_key:
            raise AIConfigurationError("falta AI_API_KEY")
        model = os.environ.get("AI_MODEL", "").strip()
        if not model:
            raise AIConfigurationError("falta AI_MODEL")
        if not re.fullmatch(r"(?:models/)?gemini-[a-zA-Z0-9._-]{1,100}", model):
            raise AIConfigurationError("AI_MODEL: identificador inválido")
        return cls(
            api_key=api_key,
            model=model,
            timeout_ms=bounded_integer("AI_TIMEOUT_MS", 20000, 1000, 120000),
            max_payload_chars=bounded_integer("AI_MAX_PAYLOAD_CHARS", 8000, 256, 32000),
        )

    def http_options(self) -> types.HttpOptions:
        return types.HttpOptions(
            timeout=self.timeout_ms,
            retry_options=types.HttpRetryOptions(attempts=1),
        )
