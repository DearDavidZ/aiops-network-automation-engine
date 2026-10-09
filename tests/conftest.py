"""Pruebas aisladas: nunca usan credenciales ni conexiones reales."""

import socket
from pathlib import Path

import pytest
from nornir import InitNornir
from nornir.core import Nornir


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(Path(__file__).resolve().parents[1])
    monkeypatch.setenv("AI_API_KEY", "test-key-not-a-secret")
    monkeypatch.setenv("AI_MODEL", "gemini-test-model")
    monkeypatch.setenv("AI_TIMEOUT_MS", "20000")
    monkeypatch.setenv("AI_MAX_PAYLOAD_CHARS", "8000")
    monkeypatch.setenv("AI_REQUESTS_PER_MINUTE", "6000")
    monkeypatch.setenv("AI_MAX_RETRIES", "0")
    monkeypatch.setenv("NET_USER", "test-user")
    monkeypatch.setenv("NET_PASSWORD", "test-password")

    def deny_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("Una prueba intentó usar la red")

    monkeypatch.setattr(socket.socket, "connect", deny_network)


@pytest.fixture
def engine() -> Nornir:
    return InitNornir(config_file="config/config.yaml")
