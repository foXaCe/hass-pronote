"""API Client Pronote - Exports publics."""

from __future__ import annotations

from .circuit_breaker import CircuitBreaker
from .client import PronoteAPIClient
from .exceptions import (
    AuthenticationError,
    CircuitBreakerOpenError,
    ConnectionError,
    InvalidResponseError,
    IPSuspendedError,
    PronoteAPIError,
    QRCodeRejectedError,
    RateLimitError,
    SessionExpiredError,
)
from .models import (
    Absence,
    Average,
    ChildInfo,
    Credentials,
    Delay,
    Evaluation,
    Grade,
    Homework,
    InformationSurvey,
    Lesson,
    Menu,
    PeriodInfo,
    PronoteData,
    Punishment,
)

__all__ = [
    # Client
    "PronoteAPIClient",
    # Circuit Breaker
    "CircuitBreaker",
    # Exceptions
    "AuthenticationError",
    "QRCodeRejectedError",
    "CircuitBreakerOpenError",
    "ConnectionError",
    "InvalidResponseError",
    "IPSuspendedError",
    "PronoteAPIError",
    "RateLimitError",
    "SessionExpiredError",
    # Models
    "Absence",
    "Average",
    "ChildInfo",
    "Credentials",
    "Delay",
    "Evaluation",
    "Grade",
    "Homework",
    "InformationSurvey",
    "Lesson",
    "Menu",
    "PeriodInfo",
    "PronoteData",
    "Punishment",
]
