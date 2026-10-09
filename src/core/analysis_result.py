"""Estados independientes del texto presentado y de los resultados de red."""

from dataclasses import dataclass
from enum import StrEnum


class AnalysisStatus(StrEnum):
    OK = "ok"
    CONFIGURATION = "configuration_error"
    INPUT_REJECTED = "input_rejected"
    INVALID_RESPONSE = "invalid_response"
    BLOCKED = "blocked_response"
    TIMEOUT = "timeout"
    TRANSPORT_ERROR = "transport_error"
    ACCESS_DENIED = "access_denied"
    MODEL_UNAVAILABLE = "model_unavailable"
    REQUEST_REJECTED = "request_rejected"
    RATE_LIMIT = "rate_limit"
    PROVIDER_ERROR = "provider_error"
    INTERNAL_ERROR = "internal_error"
    CIRCUIT_OPEN = "circuit_open"
    ADMISSION_TIMEOUT = "admission_timeout"


@dataclass(frozen=True)
class AnalysisResult:
    status: AnalysisStatus
    message: str
    attempts: int = 0
    retry_after_seconds: float | None = None

    @property
    def ok(self) -> bool:
        return self.status is AnalysisStatus.OK

    @property
    def retryable(self) -> bool:
        return self.status in {
            AnalysisStatus.TIMEOUT,
            AnalysisStatus.TRANSPORT_ERROR,
            AnalysisStatus.RATE_LIMIT,
            AnalysisStatus.PROVIDER_ERROR,
        }
