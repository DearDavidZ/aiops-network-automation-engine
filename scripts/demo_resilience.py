"""Demo reproducible sin API: latencia sintética y apertura del circuito."""

import json
import time
from pathlib import Path

from src.core.ai_resilience import AnalysisPipeline, ResilienceSettings
from src.core.analysis_result import AnalysisResult, AnalysisStatus


def synthetic_success(device: str, payload: str) -> AnalysisResult:
    time.sleep(0.1)
    return AnalysisResult(AnalysisStatus.OK, "Diagnóstico sintético", attempts=1)


def synthetic_failure(device: str, payload: str) -> AnalysisResult:
    return AnalysisResult(AnalysisStatus.PROVIDER_ERROR, "Fallo sintético", attempts=1)


def main() -> None:
    payloads = {f"synthetic-node-{i}": "interface down" for i in range(6)}
    timings: dict[str, float] = {}
    for workers in (1, 3):
        settings = ResilienceSettings(workers=workers, rpm=6000, max_retries=0)
        pipeline = AnalysisPipeline(settings, synthetic_success)
        start = time.monotonic()
        results = pipeline.run(payloads)
        if not all(item.ok for item in results.values()):
            raise RuntimeError("La demo sintética falló")
        timings[str(workers)] = round(time.monotonic() - start, 4)
    breaker = AnalysisPipeline(
        ResilienceSettings(workers=1, rpm=6000, max_retries=0, failure_threshold=2),
        synthetic_failure,
    )
    failures = breaker.run(payloads)
    report = {
        "mode": "simulation_only_no_api",
        "events": len(payloads),
        "simulated_latency_seconds": 0.1,
        "rpm_for_demo_only": 6000,
        "seconds_by_worker_count": timings,
        "speedup": round(timings["1"] / timings["3"], 2),
        "circuit_state": breaker.breaker.state.value,
        "provider_attempts_before_open": sum(item.attempts for item in failures.values()),
        "statuses_after_provider_failure": [item.status.value for item in failures.values()],
    }
    path = Path(__file__).resolve().parents[1] / "docs" / "DEMO_RESULTS.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
