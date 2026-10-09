"""Reducción local de datos. No sustituye una política DLP corporativa."""

import re
from collections.abc import Iterable

RAW_INPUT_LIMIT = 65536
SENSITIVE_LINE = re.compile(
    r"(?i)\b(?:[\w-]*(?:password|passwd|secret|token|api[-_ ]?key|authorization|"
    r"cookie|community|private[-_ ]?key)[\w-]*|pwd)\b"
)
PRIVATE_KEY = re.compile(r"-----BEGIN [^-\r\n]*PRIVATE KEY-----", re.IGNORECASE)
URL = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s<>]+")
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}")
MAC = re.compile(r"(?i)\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b|\b(?:[0-9a-f]{4}\.){2}[0-9a-f]{4}\b")
IPV4 = re.compile(r"(?<!\w)(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?(?!\w)")
# Deliberadamente conservador: también puede ocultar horas y otros valores con ':'.
IPV6 = re.compile(r"(?i)(?<![\w:])(?:[0-9a-f]*:){2,}[0-9a-f:.]*(?:%[\w.-]+)?(?:/\d{1,3})?")
HOSTNAME = re.compile(r"(?i)\b(?:[a-z0-9_-]+\.)+[a-z][a-z0-9_-]*\b")
ACCOUNT = re.compile(
    r"(?i)\b(?:user(?:name)?|login|hostname)\s*(?:[=:]\s*|\s+)(?:\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]")


class TelemetryRejected(ValueError):
    """Entrada no apta para envío; el mensaje no contiene el payload."""


def redact_telemetry(text: str, known_values: Iterable[str] = ()) -> str:
    """Depura antes de limitar tamaño, sin conservar mapas con datos originales."""
    if len(text) > RAW_INPUT_LIMIT:
        raise TelemetryRejected("entrada superior al límite local")
    text = CONTROL.sub("", text)
    # Rechazar claves PEM evita enviar cuerpos de claves partidas o incompletas.
    if PRIVATE_KEY.search(text):
        raise TelemetryRejected("entrada contiene una clave privada")
    lines = [
        "[SENSITIVE_LINE_REMOVED]" if SENSITIVE_LINE.search(line) else line
        for line in text.splitlines()
    ]
    text = "\n".join(lines)
    for value in sorted({value for value in known_values if value}, key=len, reverse=True):
        text = re.sub(re.escape(value), "[REDACTED]", text, flags=re.IGNORECASE)
    for pattern, label in (
        (URL, "[URL]"),
        (EMAIL, "[EMAIL]"),
        (MAC, "[MAC]"),
        (IPV6, "[IP]"),
        (IPV4, "[IP]"),
        (HOSTNAME, "[HOST]"),
        (ACCOUNT, "[ACCOUNT]"),
    ):
        text = pattern.sub(label, text)
    return text


def prepare_telemetry(payload: str, known_values: Iterable[str], max_chars: int) -> str:
    sanitized = redact_telemetry(payload, known_values)
    if not sanitized.strip():
        raise TelemetryRejected("entrada vacía")
    if len(sanitized) > max_chars:
        raise TelemetryRejected("telemetría depurada supera AI_MAX_PAYLOAD_CHARS")
    return sanitized
