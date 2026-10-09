"""Reloj simulado para resiliencia y sincronización real para concurrencia."""

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import TypeVar
from unittest.mock import Mock

import pytest
from netmiko.exceptions import NetmikoTimeoutException
from nornir.core import Nornir
from nornir.core.inventory import Host
from nornir.core.task import Result, Task

from src import run_engine
from src.core import ai_resilience, network_tasks
from src.core.ai_config import AIConfigurationError
from src.core.ai_resilience import (
    AnalysisPipeline,
    CircuitBreaker,
    CircuitState,
    RequestPacer,
    ResilienceSettings,
)
from src.core.analysis_result import AnalysisResult, AnalysisStatus

ReturnType = TypeVar("ReturnType")

OK = AnalysisResult(AnalysisStatus.OK, "synthetic diagnosis", attempts=1)
FAILURE = AnalysisResult(AnalysisStatus.PROVIDER_ERROR, "synthetic failure", attempts=1)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_breaker_recovery_and_stale_response() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(1, 10, clock)
    first, stale = breaker.acquire(), breaker.acquire()
    assert first is not None and stale is not None
    breaker.finish(first, FAILURE)
    assert breaker.state is CircuitState.OPEN
    breaker.finish(stale, OK)
    assert breaker.state is CircuitState.OPEN
    assert breaker.acquire() is None
    clock.sleep(10)
    probe = breaker.acquire()
    assert probe is not None and probe.probe
    assert breaker.state is CircuitState.HALF_OPEN
    assert breaker.acquire() is None
    breaker.finish(probe, OK)
    assert breaker.state is CircuitState.CLOSED
    assert breaker.acquire() is not None


def test_failed_probe_reopens_and_abandoned_probe_releases() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(1, 10, clock)
    permit = breaker.acquire()
    assert permit is not None
    breaker.finish(permit, FAILURE)
    for outcome in (FAILURE, None):
        clock.sleep(10)
        probe = breaker.acquire()
        assert probe is not None
        breaker.finish(probe, outcome)
        assert breaker.state is CircuitState.OPEN
        assert breaker.acquire() is None


def test_only_one_half_open_probe_under_contention() -> None:
    clock = FakeClock()
    breaker = CircuitBreaker(1, 1, clock)
    permit = breaker.acquire()
    assert permit is not None
    breaker.finish(permit, FAILURE)
    clock.sleep(1)
    with ThreadPoolExecutor(max_workers=8) as executor:
        permits = list(executor.map(lambda _: breaker.acquire(), range(32)))
    assert sum(item is not None for item in permits) == 1


def test_success_resets_failure_counter_and_local_errors_do_not_trip() -> None:
    breaker = CircuitBreaker(2, 10)
    for result in (FAILURE, OK, FAILURE, AnalysisResult(AnalysisStatus.CONFIGURATION, "invalid")):
        permit = breaker.acquire()
        assert permit is not None
        breaker.finish(permit, result)
        assert breaker.state is CircuitState.CLOSED
    permit = breaker.acquire()
    assert permit is not None
    breaker.finish(permit, FAILURE)
    assert breaker.state is CircuitState.OPEN


def test_pacing_and_shared_retry_after() -> None:
    clock = FakeClock()
    pacer = RequestPacer(30, clock, clock.sleep)
    times = []
    for _ in range(3):
        assert pacer.acquire(20)
        times.append(clock())
    assert times == [0, 2, 4]
    pacer.defer(10)
    assert not pacer.acquire(10)
    assert clock() == 4
    assert pacer.acquire(20)
    assert clock() == 14


def test_retry_transient_success_and_attempt_count() -> None:
    clock = FakeClock()
    call_times: list[float] = []

    def analyze(device: str, payload: str) -> AnalysisResult:
        call_times.append(clock())
        return FAILURE if len(call_times) == 1 else OK

    pipeline = AnalysisPipeline(ResilienceSettings(rpm=60), analyze, clock, clock.sleep)
    result = pipeline.analyze_one("node", "event")
    assert result.ok and result.attempts == 2
    assert call_times == [0, 1]


@pytest.mark.parametrize(
    "status",
    [
        AnalysisStatus.ACCESS_DENIED,
        AnalysisStatus.REQUEST_REJECTED,
        AnalysisStatus.CONFIGURATION,
        AnalysisStatus.INVALID_RESPONSE,
        AnalysisStatus.INPUT_REJECTED,
        AnalysisStatus.MODEL_UNAVAILABLE,
    ],
)
def test_permanent_failures_not_retried(status: AnalysisStatus) -> None:
    analyzer = Mock(return_value=AnalysisResult(status, "synthetic failure", attempts=1))
    pipeline = AnalysisPipeline(ResilienceSettings(max_retries=2), analyzer)
    assert pipeline.analyze_one("node", "event").status is status
    analyzer.assert_called_once()
    assert pipeline.breaker.state is CircuitState.CLOSED


def test_retry_after_exceeds_admission_budget_preserves_original_error() -> None:
    clock = FakeClock()
    rate_limit = AnalysisResult(AnalysisStatus.RATE_LIMIT, "synthetic quota", 1, 90)
    analyzer = Mock(return_value=rate_limit)
    pipeline = AnalysisPipeline(ResilienceSettings(), analyzer, clock, clock.sleep)
    result = pipeline.analyze_one("node", "event")
    assert result.status is AnalysisStatus.RATE_LIMIT
    assert result.attempts == 1
    analyzer.assert_called_once()
    other = pipeline.analyze_one("next", "event")
    assert other.status is AnalysisStatus.ADMISSION_TIMEOUT
    assert other.attempts == 0


def test_breaker_stops_retry_and_following_nodes() -> None:
    clock = FakeClock()
    analyzer = Mock(return_value=FAILURE)
    pipeline = AnalysisPipeline(
        ResilienceSettings(failure_threshold=1), analyzer, clock, clock.sleep
    )
    assert pipeline.analyze_one("first", "event").attempts == 1
    assert pipeline.analyze_one("next", "event").status is AnalysisStatus.CIRCUIT_OPEN
    analyzer.assert_called_once()


def test_unexpected_analyzer_error_does_not_poison_circuit() -> None:
    analyzer = Mock(side_effect=RuntimeError("synthetic secret"))
    pipeline = AnalysisPipeline(ResilienceSettings(), analyzer)
    result = pipeline.analyze_one("node", "event")
    assert result.status is AnalysisStatus.INTERNAL_ERROR
    assert "synthetic secret" not in result.message
    assert pipeline.breaker.state is CircuitState.CLOSED


def test_workers_and_pending_submissions_are_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    release = threading.Event()
    entered = threading.Event()
    lock = threading.Lock()
    active = peak = submitted = 0

    class TrackingExecutor(ThreadPoolExecutor):
        def submit(
            self, fn: Callable[..., ReturnType], /, *args: object, **kwargs: object
        ) -> Future[ReturnType]:
            nonlocal submitted
            with lock:
                submitted += 1
            return super().submit(fn, *args, **kwargs)

    def analyze(device: str, payload: str) -> AnalysisResult:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            if active == 3:
                entered.set()
        try:
            assert release.wait(5)
            return OK
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(ai_resilience, "ThreadPoolExecutor", TrackingExecutor)
    pipeline = AnalysisPipeline(ResilienceSettings(workers=3, rpm=6000), analyze)
    outputs: dict[str, AnalysisResult] = {}
    payloads = {f"node-{i}": "synthetic" for i in range(20)}
    thread = threading.Thread(target=lambda: outputs.update(pipeline.run(payloads)))
    thread.start()
    try:
        assert entered.wait(5)
        with lock:
            assert submitted == 3
        assert peak == 3
    finally:
        release.set()
        thread.join(10)
    assert not thread.is_alive()
    assert list(outputs) == list(payloads)
    assert all(result.ok for result in outputs.values())
    assert peak <= 3


@pytest.mark.parametrize(
    "network_failed,ai_failed,expected",
    [
        (False, False, 0),
        (True, False, 2),
        (False, True, 3),
        (True, True, 4),
    ],
)
def test_exit_code_truth_table(network_failed: bool, ai_failed: bool, expected: int) -> None:
    assert run_engine.execution_exit_code(network_failed, ai_failed) == expected


@pytest.mark.parametrize("network_failure,expected", [(False, 3), (True, 4)])
def test_orchestrator_degradation_and_early_ssh_close(
    network_failure: bool, expected: int, engine: Nornir, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed: set[str] = set()

    def close(host: Host) -> None:
        closed.add(host.name)

    def collect(task: Task, command_string: str, enable: bool) -> Result:
        if network_failure and task.host.platform == "cisco_ios":
            raise NetmikoTimeoutException("synthetic")
        return Result(host=task.host, result="event")

    def analyze(device: str, payload: str) -> AnalysisResult:
        assert closed == set(engine.inventory.hosts)
        return FAILURE

    monkeypatch.setattr(Host, "close_connections", close)
    monkeypatch.setattr(run_engine, "InitNornir", Mock(return_value=engine))
    monkeypatch.setattr(network_tasks, "netmiko_send_command", collect)
    monkeypatch.setattr(run_engine, "analyze_telemetry", analyze)
    assert run_engine.main() == expected


@pytest.mark.parametrize(
    "name,value",
    [
        ("AI_WORKERS", "0"),
        ("AI_WORKERS", "17"),
        ("AI_MAX_RETRIES", "3"),
        ("AI_REQUESTS_PER_MINUTE", "0"),
        ("AI_RECOVERY_SECONDS", "invalid"),
        ("AI_ADMISSION_TIMEOUT_SECONDS", "0"),
    ],
)
def test_invalid_resilience_configuration(
    name: str, value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(AIConfigurationError):
        ResilienceSettings.from_environment()


def test_missing_ai_config_collects_without_pacing_or_api(
    engine: Nornir, monkeypatch: pytest.MonkeyPatch
) -> None:
    def collect(task: Task, command_string: str, enable: bool) -> Result:
        return Result(host=task.host, result="synthetic log")

    monkeypatch.setattr(run_engine, "load_dotenv", Mock())
    monkeypatch.delenv("AI_API_KEY")
    monkeypatch.setattr(run_engine, "InitNornir", Mock(return_value=engine))
    monkeypatch.setattr(network_tasks, "netmiko_send_command", collect)
    analyze = Mock()
    monkeypatch.setattr(run_engine, "analyze_telemetry", analyze)
    pipeline_run = Mock()
    monkeypatch.setattr(AnalysisPipeline, "run", pipeline_run)
    assert run_engine.main() == 3
    analyze.assert_not_called()
    pipeline_run.assert_not_called()
