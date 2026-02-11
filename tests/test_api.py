"""Tests for the Pronote API client."""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from custom_components.pronote.api import (
    AuthenticationError,
    CircuitBreakerOpenError,
    Lesson,
    PronoteAPIClient,
    RateLimitError,
)
from custom_components.pronote.api.auth import PronoteAuth
from custom_components.pronote.api.circuit_breaker import CircuitBreaker


class TestCircuitBreaker:
    """Tests for the CircuitBreaker class."""

    def test_initially_closed(self):
        cb = CircuitBreaker()
        assert not cb.is_open

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert not cb.is_open  # Still closed at 2 failures
        cb.record_failure()
        assert cb.is_open  # Open at 3 failures

    def test_closes_after_recovery_timeout(self):
        import time

        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=0.01)  # 10ms
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open
        # Wait for recovery timeout
        time.sleep(0.02)  # 20ms
        # Circuit should now be closed (or at least checkable)
        assert not cb.is_open

    def test_success_resets_counter(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        # Should still be closed (only 1 failure after reset)
        assert not cb.is_open


class TestPronoteAuth:
    """Tests for the PronoteAuth class."""

    def test_normalize_url_student(self):
        auth = PronoteAuth()
        result = auth._normalize_url("https://pronote.example.com/", "student")
        assert "eleve.html" in result

    def test_normalize_url_parent(self):
        auth = PronoteAuth()
        result = auth._normalize_url("https://pronote.example.com/", "parent")
        assert "parent.html" in result

    def test_normalize_url_no_trailing_slash(self):
        auth = PronoteAuth()
        result = auth._normalize_url("https://pronote.example.com", "student")
        assert result.startswith("https://pronote.example.com/")

    def test_normalize_url_removes_old_html(self):
        auth = PronoteAuth()
        result = auth._normalize_url("https://pronote.example.com/old.html", "student")
        assert "old.html" not in result
        assert "eleve.html" in result


class TestPronoteAPIClient:
    """Tests for the PronoteAPIClient class."""

    @pytest.mark.asyncio
    async def test_authenticate_success(self):
        """Test successful authentication."""
        client = PronoteAPIClient()
        mock_pronotepy_client = MagicMock()

        with patch.object(PronoteAuth, "authenticate", return_value=(mock_pronotepy_client, MagicMock())):
            await client.authenticate("username_password", {})

        assert client.is_authenticated()

    @pytest.mark.asyncio
    async def test_authenticate_raises_authentication_error(self):
        """Test that AuthenticationError is propagated."""
        client = PronoteAPIClient()

        with patch.object(PronoteAuth, "authenticate", side_effect=AuthenticationError("Invalid credentials")):
            with pytest.raises(AuthenticationError):
                await client.authenticate("username_password", {})

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_failures(self):
        """Test that circuit breaker opens after repeated failures."""

        client = PronoteAPIClient()
        client._circuit_breaker.failure_threshold = 3  # Lower threshold for test

        # Simulate 3 failures directly on circuit breaker
        client._circuit_breaker.record_failure()
        client._circuit_breaker.record_failure()
        client._circuit_breaker.record_failure()

        # Circuit should be open now
        assert client._circuit_breaker.is_open

        # Next call should raise CircuitBreakerOpenError immediately
        with pytest.raises(CircuitBreakerOpenError):
            # Use a mock that would succeed, but circuit breaker prevents it
            with patch.object(PronoteAuth, "authenticate", return_value=(MagicMock(), MagicMock())):
                await client.authenticate("username_password", {})

    def test_is_authenticated_initially_false(self):
        """Test that client is not authenticated initially."""
        client = PronoteAPIClient()
        assert not client.is_authenticated()


class TestExceptions:
    """Tests for API exceptions."""

    def test_rate_limit_error_with_retry_after(self):
        err = RateLimitError("Too many requests", retry_after=120)
        assert err.retry_after == 120

    def test_authentication_error_inherits_base(self):
        err = AuthenticationError("Auth failed")
        assert err.message == "Auth failed"

    def test_circuit_breaker_error(self):
        err = CircuitBreakerOpenError("Circuit open")
        assert err.message == "Circuit open"


class TestModels:
    """Tests for API models."""

    def test_lesson_creation(self):
        start = datetime(2025, 1, 15, 8, 0)
        end = datetime(2025, 1, 15, 9, 0)
        lesson = Lesson(
            id="123",
            subject="Math",
            start=start,
            end=end,
            room="A101",
            teacher="M. Dupont",
            canceled=False,
            is_detention=False,
        )
        assert lesson.id == "123"
        assert lesson.subject == "Math"
        assert lesson.start == start
        assert lesson.canceled is False

    def test_lesson_defaults(self):
        start = datetime(2025, 1, 15, 8, 0)
        end = datetime(2025, 1, 15, 9, 0)
        lesson = Lesson(
            id="123",
            subject="Math",
            start=start,
            end=end,
        )
        assert lesson.room is None
        assert lesson.canceled is False
        assert lesson.is_detention is False


class TestClientConverters:
    """Tests for data converters in the client."""

    def test_convert_lesson(self):
        client = PronoteAPIClient()
        mock_lesson = SimpleNamespace(
            id="lesson1",
            subject="Math",  # Simple string subject
            start=datetime(2025, 1, 15, 8, 0),
            end=datetime(2025, 1, 15, 9, 0),
            classroom="A101",
            teacher="M. Dupont",
            canceled=False,
            status="",
            background_color="#FFFFFF",
            is_outside=False,
            detention=False,
        )

        result = client._convert_lesson(mock_lesson)
        assert result.id == "lesson1"
        assert result.subject == "Math"
        assert result.room == "A101"
        assert result.canceled is False

    def test_convert_grade(self):
        client = PronoteAPIClient()
        mock_grade = SimpleNamespace(
            id="grade1",
            date=date(2025, 1, 15),
            subject=SimpleNamespace(name="Math"),
            grade="15",
            grade_out_of="20",
            coefficient="1",
            average="14",
            comment="Good work",
            is_bonus=False,
            is_optionnal=False,
        )

        result = client._convert_grade(mock_grade)
        assert result.id == "grade1"
        assert result.grade == "15"
        assert result.grade_out_of == "20"

    def test_convert_absence(self):
        client = PronoteAPIClient()
        mock_absence = SimpleNamespace(
            id="abs1",
            from_date=datetime(2025, 1, 15, 8, 0),
            to_date=datetime(2025, 1, 15, 12, 0),
            justified=True,
            hours="4",
            reasons="Sickness",
        )

        result = client._convert_absence(mock_absence)
        assert result.id == "abs1"
        assert result.justified is True
        assert result.hours == "4"

    def test_convert_homework(self):
        client = PronoteAPIClient()
        mock_hw = SimpleNamespace(
            id="hw1",
            date=date(2025, 1, 20),
            subject=SimpleNamespace(name="Francais"),
            description="Exercice 5",
            done=False,
            background_color="#FFFFFF",
            files=[],
        )

        result = client._convert_homework(mock_hw)
        assert result.id == "hw1"
        assert result.description == "Exercice 5"
        assert result.done is False
