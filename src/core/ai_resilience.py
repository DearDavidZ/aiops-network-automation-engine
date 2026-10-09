"""Coordinación por proceso: concurrencia, ritmo y circuit breaker sincronizado."""

import logging
import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, replace
from enum import StrEnum

from src.core.ai_analyzer import analyze_telemetry
from src.core.ai_config import bounded_integer
from src.core.analysis_result import AnalysisResult, AnalysisStatus

logger = logging.getLogger("AIResilience")
Clock = Callable[[], float]
Sleeper = Callable[[float], None]
Analyzer = Callable[[str, str], AnalysisResult]


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class Permit:
    generation: int
    probe: bool = False


class CircuitBreaker:
    def __init__(
        self, threshold: int, recovery_seconds: float, clock: Clock = time.monotonic
    ) -> None:
        if threshold < 1 or recovery_seconds <= 0:
            raise ValueError("Parámetros de circuit breaker inválidos")
        self._threshold = threshold
        self._recovery = recovery_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._generation = 0
        self._failures = 0
        self._opened_at = 0.0

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state

    def acquire(self) -> Permit | None:
        with self._lock:
            if self._state is CircuitState.OPEN:
                if self._clock() - self._opened_at < self._recovery:
                    return None
                self._state = CircuitState.HALF_OPEN
                self._generation += 1
                logger.info("Circuit breaker: half_open, una única prueba permitida")
                return Permit(self._generation, probe=True)
            if self._state is CircuitState.HALF_OPEN:
                return None
            return Permit(self._generation)

    def valid(self, permit: Permit) -> bool:
        with self._lock:
            return permit.generation == self._generation and self._state is not CircuitState.OPEN

    def finish(self, permit: Permit, result: AnalysisResult | None) -> None:
        with self._lock:
            if permit.generation != self._generation:
                return  # Una respuesta antigua no puede cerrar un circuito recién abierto.
            if result is not None and result.ok:
                self._failures = 0
                if permit.probe:
                    self._state = CircuitState.CLOSED
                    self._generation += 1
                    logger.info("Circuit breaker: closed tras prueba satisfactoria")
            elif result is not None and result.retryable:
                self._failures += 1
                if permit.probe or self._failures >= self._threshold:
                    self._open()
            elif permit.probe:
                # Si la prueba no confirma recuperación, libera la reserva y mantiene pausa.
                self._open()

    def _open(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = self._clock()
        self._generation += 1
        logger.warning("Circuit breaker: open; nuevas solicitudes suspendidas")


class RequestPacer:
    """Espaciado sin ráfagas; Retry-After aplaza admisiones del mismo proceso."""

    def __init__(
        self, rpm: int, clock: Clock = time.monotonic, sleep: Sleeper = time.sleep
    ) -> None:
        if rpm < 1:
            raise ValueError("RPM debe ser positivo")
        self._interval = 60.0 / rpm
        self._clock = clock
        self._sleep = sleep
        self._next = 0.0
        self._lock = threading.Lock()

    def defer(self, seconds: float) -> None:
        with self._lock:
            self._next = max(self._next, self._clock() + max(0.0, seconds))

    def acquire(self, deadline: float) -> bool:
        while True:
            with self._lock:
                now = self._clock()
                if now >= deadline or self._next >= deadline:
                    return False
                delay = self._next - now
                if delay <= 0:
                    self._next = now + self._interval
                    return True
            self._sleep(delay)


@dataclass(frozen=True)
class ResilienceSettings:
    workers: int = 3
    rpm: int = 30
    failure_threshold: int = 3
    recovery_seconds: int = 30
    max_retries: int = 1
    retry_delay_ms: int = 1000
    admission_timeout_seconds: int = 60

    @classmethod
    def from_environment(cls) -> "ResilienceSettings":
        return cls(
            workers=bounded_integer("AI_WORKERS", 3, 1, 16),
            rpm=bounded_integer("AI_REQUESTS_PER_MINUTE", 30, 1, 6000),
            failure_threshold=bounded_integer("AI_FAILURE_THRESHOLD", 3, 1, 20),
            recovery_seconds=bounded_integer("AI_RECOVERY_SECONDS", 30, 1, 3600),
            max_retries=bounded_integer("AI_MAX_RETRIES", 1, 0, 2),
            retry_delay_ms=bounded_integer("AI_RETRY_DELAY_MS", 1000, 1, 30000),
            admission_timeout_seconds=bounded_integer("AI_ADMISSION_TIMEOUT_SECONDS", 60, 1, 600),
        )


class AnalysisPipeline:
    def __init__(
        self,
        settings: ResilienceSettings,
        analyzer: Analyzer = analyze_telemetry,
        clock: Clock = time.monotonic,
        sleep: Sleeper = time.sleep,
    ) -> None:
        self.settings = settings
        self._analyzer = analyzer
        self._clock = clock
        self._sleep = sleep
        self.breaker = CircuitBreaker(settings.failure_threshold, settings.recovery_seconds, clock)
        self.pacer = RequestPacer(settings.rpm, clock, sleep)

    def analyze_one(self, device: str, payload: str) -> AnalysisResult:
        deadline = self._clock() + self.settings.admission_timeout_seconds
        attempts = 0
        last: AnalysisResult | None = None
        for retry_index in range(self.settings.max_retries + 1):
            permit = self.breaker.acquire()
            if permit is None:
                return last or AnalysisResult(
                    AnalysisStatus.CIRCUIT_OPEN, "IA omitida: circuito abierto o prueba en curso."
                )
            if not self.pacer.acquire(deadline):
                self.breaker.finish(permit, None)
                return last or AnalysisResult(
                    AnalysisStatus.ADMISSION_TIMEOUT, "IA omitida: plazo de admisión agotado."
                )
            if not self.breaker.valid(permit):
                return last or AnalysisResult(
                    AnalysisStatus.CIRCUIT_OPEN, "IA omitida: circuito abierto durante la espera."
                )
            try:
                result = self._analyzer(device, payload)
            except Exception as exc:
                logger.error("Fallo interno del analizador: %s", type(exc).__name__)
                result = AnalysisResult(
                    AnalysisStatus.INTERNAL_ERROR, "Fallo interno del analizador."
                )
            attempts += result.attempts
            last = replace(result, attempts=attempts)
            self.breaker.finish(permit, result)
            if result.retryable and result.retry_after_seconds is not None:
                self.pacer.defer(result.retry_after_seconds)
            elif result.status is AnalysisStatus.RATE_LIMIT:
                self.pacer.defer(self.settings.recovery_seconds)
            if not result.retryable or retry_index == self.settings.max_retries or permit.probe:
                return last
            delay = self.settings.retry_delay_ms / 1000.0 * (2**retry_index)
            if self._clock() + delay >= deadline:
                return last
            self._sleep(delay)
        raise RuntimeError("Bucle de reintentos sin resultado")

    def run(self, payloads: Mapping[str, str]) -> dict[str, AnalysisResult]:
        """Como máximo workers futures pendientes; resultados en orden de inventario."""
        results: dict[str, AnalysisResult] = {}
        source = iter(payloads.items())
        with ThreadPoolExecutor(
            max_workers=self.settings.workers, thread_name_prefix="ai"
        ) as executor:
            pending: dict[Future[AnalysisResult], str] = {}

            def submit_next() -> None:
                item = next(source, None)
                if item is not None:
                    device, payload = item
                    pending[executor.submit(self.analyze_one, device, payload)] = device

            for _ in range(self.settings.workers):
                submit_next()
            while pending:
                completed, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in completed:
                    device = pending.pop(future)
                    try:
                        results[device] = future.result()
                    except Exception as exc:
                        logger.error("Fallo del coordinador: %s", type(exc).__name__)
                        results[device] = AnalysisResult(
                            AnalysisStatus.INTERNAL_ERROR, "Fallo del coordinador IA."
                        )
                    submit_next()
        return {device: results[device] for device in payloads}
