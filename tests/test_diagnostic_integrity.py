"""Regresiones de comandos, clasificación de fallos y contingencia IA."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from google.genai import types
from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException
from nornir.core import Nornir
from nornir.core.inventory import Host
from nornir.core.task import Result, Task

import check_models
from src import run_engine
from src.core import ai_analyzer, network_tasks
from src.core.analysis_result import AnalysisResult, AnalysisStatus


def ai_response(text: str | None) -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                finish_reason=types.FinishReason.STOP,
                content=types.Content(parts=[types.Part(text=text)]),
            )
        ]
    )


def test_multivendor_commands(engine: Nornir, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, str] = {}

    def collect(task: Task, command_string: str, enable: bool) -> Result:
        assert task.host.platform is not None
        calls[task.host.platform] = command_string
        return Result(host=task.host, result="synthetic log")

    monkeypatch.setattr(network_tasks, "netmiko_send_command", collect)
    results = engine.run(task=network_tasks.fetch_telemetry_logs)
    assert not results.failed
    assert calls == {"cisco_ios": "show logging", "mikrotik_routeros": "/log print"}
    assert all(items[0].result == "synthetic log" for items in results.values())


@pytest.mark.parametrize("platform", [None, "unsupported"])
def test_unknown_platform_never_connects(
    platform: str | None, engine: Nornir, monkeypatch: pytest.MonkeyPatch
) -> None:
    for host in engine.inventory.hosts.values():
        host.groups.clear()
        host.platform = platform
    collect = Mock()
    monkeypatch.setattr(network_tasks, "netmiko_send_command", collect)
    results = engine.run(task=network_tasks.fetch_telemetry_logs)
    assert results.failed
    assert all("UNSUPPORTED_PLATFORM" in items[0].result for items in results.values())
    collect.assert_not_called()


@pytest.mark.parametrize(
    "error,category",
    [
        (NetmikoAuthenticationException("synthetic rejection"), "AUTHENTICATION_ERROR"),
        (NetmikoTimeoutException("synthetic timeout"), "CONNECTION_TIMEOUT"),
        (ValueError("synthetic internal failure"), "COLLECTION_ERROR"),
    ],
)
def test_real_nornir_subtask_preserves_cause(
    error: Exception, category: str, engine: Nornir, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(task: Task, command_string: str, enable: bool) -> Result:
        raise error

    monkeypatch.setattr(network_tasks, "netmiko_send_command", fail)
    results = engine.run(task=network_tasks.fetch_telemetry_logs)
    assert results.failed
    for items in results.values():
        assert items[0].result == category
        assert items[0].exception is error


@pytest.mark.parametrize("text", [None, "", "  "])
def test_empty_ai_response(text: str | None, monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock()
    client.models.generate_content.return_value = ai_response(text)
    monkeypatch.setattr(ai_analyzer.genai, "Client", Mock(return_value=client))
    assert "respuesta sin texto" in ai_analyzer.analyze_telemetry_with_ai("node", "log")


def test_ai_failure_does_not_diagnose_network(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    client = Mock()
    client.models.generate_content.side_effect = RuntimeError("secret-value")
    monkeypatch.setattr(ai_analyzer.genai, "Client", Mock(return_value=client))
    diagnosis = ai_analyzer.analyze_telemetry_with_ai("node", "healthy log")
    assert "ANÁLISIS IA NO DISPONIBLE" in diagnosis
    assert "Timeout TCP" not in diagnosis
    assert "secret-value" not in caplog.text


def test_ai_uses_configured_model(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Mock()
    client.models.generate_content.return_value = ai_response(
        json.dumps(
            {
                "observations": ["Interface down"],
                "hypotheses": ["Link issue"],
                "checks": ["Inspect interface counters"],
            }
        )
    )
    monkeypatch.setattr(ai_analyzer.genai, "Client", Mock(return_value=client))
    assert "Hipótesis no confirmadas: Link issue" in ai_analyzer.analyze_telemetry_with_ai(
        "node", "log"
    )
    assert client.models.generate_content.call_args.kwargs["model"] == "gemini-test-model"


@pytest.mark.parametrize("variable", ["AI_API_KEY", "AI_MODEL"])
def test_missing_ai_config_never_calls_provider(
    variable: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(variable)
    client = Mock()
    monkeypatch.setattr(ai_analyzer.genai, "Client", client)
    assert variable in ai_analyzer.analyze_telemetry_with_ai("node", "log")
    client.assert_not_called()


@pytest.mark.parametrize("fail_network", [False, True])
def test_exit_code_and_cleanup(
    fail_network: bool, engine: Nornir, monkeypatch: pytest.MonkeyPatch
) -> None:
    def collect(task: Task, command_string: str, enable: bool) -> Result:
        if fail_network:
            raise NetmikoAuthenticationException("synthetic rejection")
        return Result(host=task.host, result="synthetic log")

    monkeypatch.setattr(network_tasks, "netmiko_send_command", collect)
    monkeypatch.setattr(run_engine, "InitNornir", Mock(return_value=engine))
    close = Mock()
    monkeypatch.setattr(Host, "close_connections", close)
    analysis = Mock(return_value=AnalysisResult(AnalysisStatus.OK, "hypothesis", 1))
    monkeypatch.setattr(run_engine, "analyze_telemetry", analysis)
    assert run_engine.main() == (2 if fail_network else 0)
    assert close.call_count == 2
    assert analysis.call_count == (0 if fail_network else 2)


def test_mixed_results_from_another_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def collect(task: Task, command_string: str, enable: bool) -> Result:
        if task.host.platform == "cisco_ios":
            raise NetmikoAuthenticationException("synthetic rejection")
        return Result(host=task.host, result="synthetic log")

    monkeypatch.setattr(network_tasks, "netmiko_send_command", collect)
    analysis = Mock(return_value=AnalysisResult(AnalysisStatus.OK, "hypothesis", 1))
    monkeypatch.setattr(run_engine, "analyze_telemetry", analysis)
    monkeypatch.chdir(tmp_path)
    assert run_engine.main() == 2
    analysis.assert_called_once_with("edge-rtr-01.branch", "synthetic log")


def test_cleanup_after_unexpected_failure(engine: Nornir, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_engine, "InitNornir", Mock(return_value=engine))
    monkeypatch.setattr(engine, "run", Mock(side_effect=RuntimeError("synthetic failure")))
    close = Mock()
    monkeypatch.setattr(Host, "close_connections", close)
    assert run_engine.main() == 1
    assert close.call_count == 2


def test_cleanup_continues_after_close_failure(
    engine: Nornir, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(run_engine, "InitNornir", Mock(return_value=engine))
    monkeypatch.setattr(engine, "run", Mock(side_effect=RuntimeError("synthetic failure")))
    close = Mock(side_effect=[RuntimeError("close failed"), None])
    monkeypatch.setattr(Host, "close_connections", close)
    assert run_engine.main() == 1
    assert close.call_count == 2


def test_missing_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_engine, "load_dotenv", Mock())
    monkeypatch.delenv("NET_PASSWORD")
    initialize = Mock()
    monkeypatch.setattr(run_engine, "InitNornir", initialize)
    assert run_engine.main() == 1
    initialize.assert_not_called()


def test_model_catalog_never_prints_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client = Mock()
    client.models.list.return_value = [
        types.Model(name="models/test-model", supported_actions=["generateContent"]),
        types.Model(name="models/no-actions"),
    ]
    monkeypatch.setattr(check_models, "load_dotenv", Mock())
    monkeypatch.setattr(check_models.genai, "Client", Mock(return_value=client))
    check_models.audit_authorized_models()
    output = capsys.readouterr().out
    assert "test-key" not in output
    assert "Token detectado" not in output
    assert "models/test-model" in output
    assert "models/no-actions" not in output
