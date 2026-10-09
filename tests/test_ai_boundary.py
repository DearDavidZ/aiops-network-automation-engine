"""SDK real contra transporte HTTP simulado; ninguna solicitud sale del proceso."""

import json
import sys
from collections.abc import Callable
from unittest.mock import Mock

import httpx
import pytest
from google import genai
from google.genai import types

import check_models
from src.core import ai_analyzer
from src.core.ai_config import AISettings

REPORT = {
    "observations": ["Interface ether1 down"],
    "hypotheses": ["Posible falla del enlace"],
    "checks": ["Revisar contadores de la interfaz"],
}


class LocalTransport(httpx.MockTransport):
    closed: bool = False

    def close(self) -> None:
        self.closed = True
        super().close()


def install_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> LocalTransport:
    original_client = genai.Client
    transport = LocalTransport(handler)

    def factory(
        *,
        api_key: str,
        http_options: types.HttpOptions,
        vertexai: bool,
        enterprise: bool,
    ) -> genai.Client:
        http_options.client_args = {"transport": transport, "trust_env": False}
        return original_client(
            api_key=api_key,
            http_options=http_options,
            vertexai=vertexai,
            enterprise=enterprise,
        )

    monkeypatch.setattr(genai, "Client", factory)
    return transport


def response_body(text: str, reason: str = "STOP") -> dict[str, object]:
    return {
        "candidates": [
            {
                "content": {"role": "model", "parts": [{"text": text}]},
                "finishReason": reason,
            }
        ]
    }


def test_real_sdk_wire_contract_and_redaction(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=response_body(json.dumps(REPORT)))

    transport = install_transport(monkeypatch, handler)
    result = ai_analyzer.analyze_telemetry_with_ai(
        "private-node",
        "private-node 192.0.2.15 ether1 link down\npassword=private-secret",
    )
    assert "Hipótesis no confirmadas" in result
    assert len(requests) == 1
    request = requests[0]
    body = request.content.decode()
    for forbidden in (
        "private-node",
        "192.0.2.15",
        "private-secret",
        "test-password",
        "test-key-not-a-secret",
    ):
        assert forbidden not in body
    assert "link down" in body
    assert request.url.host == "generativelanguage.googleapis.com"
    assert request.url.path.endswith("/models/gemini-test-model:generateContent")
    assert request.extensions["timeout"]["read"] == 20.0
    assert request.headers["x-goog-api-key"] == "test-key-not-a-secret"
    config = json.loads(body)["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["maxOutputTokens"] == 1024
    assert "additionalProperties" not in config["responseSchema"]
    assert "additional_properties" not in config["responseSchema"]
    assert transport.closed


@pytest.mark.parametrize(
    "header,minimum,maximum",
    [
        ("90", 90.0, 90.0),
        ("invalid", None, None),
    ],
)
def test_retry_after_from_real_sdk_error(
    header: str,
    minimum: float | None,
    maximum: float | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transport(
        monkeypatch,
        lambda request: httpx.Response(
            429,
            headers={"Retry-After": header},
            json={"error": {"code": 429, "message": "synthetic quota"}},
        ),
    )
    result = ai_analyzer.analyze_telemetry("node", "link down")
    assert result.retryable
    if minimum is None:
        assert result.retry_after_seconds is None
    else:
        assert result.retry_after_seconds == minimum


def test_response_extra_fields_still_rejected_locally(monkeypatch: pytest.MonkeyPatch) -> None:
    install_transport(
        monkeypatch,
        lambda request: httpx.Response(
            200,
            json=response_body(json.dumps({**REPORT, "unexpected": "value"})),
        ),
    )
    result = ai_analyzer.analyze_telemetry("node", "link down")
    assert not result.ok
    assert "esquema" in result.message


@pytest.mark.parametrize(
    "code,expected",
    [
        (401, "autenticación"),
        (403, "denegado"),
        (404, "modelo o recurso"),
        (429, "cuota"),
        (500, "error del proveedor"),
        (503, "error del proveedor"),
    ],
)
def test_api_errors_no_retry_or_secret_leak(
    code: int, expected: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(code, json={"error": {"code": code, "message": "private-secret"}})

    transport = install_transport(monkeypatch, handler)
    result = ai_analyzer.analyze_telemetry_with_ai("private-node", "link down")
    assert expected in result
    assert "private-secret" not in result + caplog.text
    assert "private-node" not in caplog.text
    assert len(requests) == 1
    assert transport.closed


def test_transport_timeout_closes_client(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("private-secret", request=request)

    transport = install_transport(monkeypatch, handler)
    result = ai_analyzer.analyze_telemetry_with_ai("private-node", "link down")
    assert "tiempo de espera" in result
    assert "private-secret" not in result
    assert transport.closed


@pytest.mark.parametrize(
    "text,reason,expected",
    [
        ("", "STOP", "sin texto"),
        ("{", "STOP", "esquema"),
        (json.dumps({"observations": ["up"]}), "STOP", "esquema"),
        (json.dumps(REPORT), "MAX_TOKENS", "incompleta"),
        (json.dumps(REPORT), "SAFETY", "bloqueada"),
        ("x" * 16001, "STOP", "límite local"),
    ],
    ids=["empty", "json", "schema", "truncated", "blocked", "oversize"],
)
def test_rejects_invalid_model_response(
    text: str, reason: str, expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = install_transport(
        monkeypatch, lambda request: httpx.Response(200, json=response_body(text, reason))
    )
    assert expected in ai_analyzer.analyze_telemetry_with_ai("private-node", "link down")
    assert transport.closed


def test_prompt_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = install_transport(
        monkeypatch,
        lambda request: httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}}),
    )
    assert "bloqueada" in ai_analyzer.analyze_telemetry_with_ai("private-node", "link down")
    assert transport.closed


@pytest.mark.parametrize(
    "name,value",
    [
        ("AI_TIMEOUT_MS", "private-secret"),
        ("AI_TIMEOUT_MS", "0"),
        ("AI_TIMEOUT_MS", "120001"),
        ("AI_MAX_PAYLOAD_CHARS", "255"),
        ("AI_MAX_PAYLOAD_CHARS", "32001"),
        ("AI_MODEL", "https://invalid.example"),
    ],
)
def test_invalid_config_never_opens_client(
    name: str, value: str, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv(name, value)
    client = Mock()
    monkeypatch.setattr(genai, "Client", client)
    result = ai_analyzer.analyze_telemetry_with_ai("private-node", "link down")
    assert "NO DISPONIBLE" in result
    assert "private-secret" not in result + caplog.text
    client.assert_not_called()


@pytest.mark.parametrize(
    "payload", ["", "x" * 65537, "-----BEGIN PRIVATE KEY-----"], ids=["empty", "oversize", "pem"]
)
def test_rejected_input_never_opens_client(payload: str, monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock()
    monkeypatch.setattr(genai, "Client", client)
    assert "NO DISPONIBLE" in ai_analyzer.analyze_telemetry_with_ai("private-node", payload)
    client.assert_not_called()


def test_response_redaction(monkeypatch: pytest.MonkeyPatch) -> None:
    report = {**REPORT, "observations": ["private-node 192.0.2.15 test-password"]}
    install_transport(
        monkeypatch, lambda request: httpx.Response(200, json=response_body(json.dumps(report)))
    )
    result = ai_analyzer.analyze_telemetry_with_ai("private-node", "link down")
    for forbidden in ("private-node", "192.0.2.15", "test-password"):
        assert forbidden not in result


def test_settings_repr_hides_key() -> None:
    assert "test-key-not-a-secret" not in repr(AISettings.from_environment())


def test_catalog_closes_sdk_client(monkeypatch: pytest.MonkeyPatch) -> None:
    install = install_transport(
        monkeypatch,
        lambda request: httpx.Response(
            200,
            json={
                "models": [
                    {
                        "name": "models/gemini-test-model",
                        "supportedGenerationMethods": ["generateContent"],
                    }
                ]
            },
        ),
    )
    monkeypatch.setattr(check_models, "load_dotenv", Mock())
    assert check_models.audit_authorized_models() == 0
    assert install.closed


@pytest.mark.parametrize("code", [200, 403])
def test_explicit_probe_sends_only_synthetic_input(
    code: int, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = (
            response_body(json.dumps(REPORT))
            if code == 200
            else {"error": {"code": code, "message": "synthetic rejection"}}
        )
        return httpx.Response(code, json=body)

    transport = install_transport(monkeypatch, handler)
    monkeypatch.setattr(check_models, "load_dotenv", Mock())
    monkeypatch.setattr(sys, "argv", ["check_models.py", "--probe"])
    assert check_models.main() == (0 if code == 200 else 1)
    assert "Synthetic laboratory event" in requests[0].content.decode()
    assert "test-key" not in capsys.readouterr().out
    assert transport.closed


def test_catalog_failure_closes_client(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = install_transport(
        monkeypatch,
        lambda request: httpx.Response(
            403, json={"error": {"code": 403, "message": "synthetic rejection"}}
        ),
    )
    monkeypatch.setattr(check_models, "load_dotenv", Mock())
    assert check_models.audit_authorized_models() == 1
    assert transport.closed
