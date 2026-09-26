"""Tests for the Pronote coordinator."""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.pronote.const import EVENT_TYPE
from custom_components.pronote.coordinator import (
    PronoteDataUpdateCoordinator,
    get_day_start_at,
)


class TestGetDayStartAt:
    """Tests for get_day_start_at function."""

    def test_returns_first_non_canceled_lesson(self):
        """Test returns start time of first non-canceled lesson."""
        lessons = [
            SimpleNamespace(canceled=True, start=datetime(2025, 1, 15, 8, 0)),
            SimpleNamespace(canceled=False, start=datetime(2025, 1, 15, 9, 0)),
            SimpleNamespace(canceled=False, start=datetime(2025, 1, 15, 10, 0)),
        ]
        result = get_day_start_at(lessons)
        assert result == datetime(2025, 1, 15, 9, 0)

    def test_returns_none_when_all_canceled(self):
        """Test returns None when all lessons are canceled."""
        lessons = [
            SimpleNamespace(canceled=True, start=datetime(2025, 1, 15, 8, 0)),
            SimpleNamespace(canceled=True, start=datetime(2025, 1, 15, 9, 0)),
        ]
        result = get_day_start_at(lessons)
        assert result is None

    def test_returns_none_when_empty_list(self):
        """Test returns None when list is empty."""
        result = get_day_start_at([])
        assert result is None

    def test_returns_none_when_none_input(self):
        """Test returns None when input is None."""
        result = get_day_start_at(None)
        assert result is None


class TestPronoteDataUpdateCoordinator:
    """Tests for PronoteDataUpdateCoordinator."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator with fully mocked hass."""
        entry = MagicMock()
        entry.title = "Test Student"
        entry.options = {"refresh_interval": 15, "nickname": "Jean", "alarm_offset": 30}
        entry.data = {
            "connection_type": "username_password",
            "account_type": "student",
            "url": "https://example.com",
            "username": "test",
            "password": "pass",
        }

        with patch.object(PronoteDataUpdateCoordinator, "__init__", lambda self, *a, **kw: None):
            coord = PronoteDataUpdateCoordinator.__new__(PronoteDataUpdateCoordinator)
            coord.hass = MagicMock()
            coord.hass.config.time_zone = "Europe/Paris"
            coord.config_entry = entry
            coord.data = None
            coord._api_client = MagicMock()
            # Make async methods use AsyncMock
            coord._api_client.authenticate = AsyncMock()
            coord._api_client.fetch_all_data = AsyncMock()
            coord._api_client.is_authenticated = MagicMock(return_value=True)
            coord._api_client.check_session = AsyncMock(return_value=True)
            coord.logger = MagicMock()
            coord._previous_period_cache = None
            coord._previous_period_cache_date = None
        return coord

    @pytest.mark.asyncio
    async def test_async_update_data_success(self, mock_coordinator):
        """Test successful data update."""
        mock_pronote_data = MagicMock()
        mock_pronote_data.child_info = SimpleNamespace(name="Test Student")
        mock_pronote_data.lessons_today = []
        mock_pronote_data.lessons_tomorrow = []
        mock_pronote_data.lessons_next_day = []
        mock_pronote_data.lessons_period = []
        mock_pronote_data.grades = []
        mock_pronote_data.averages = []
        mock_pronote_data.overall_average = None
        mock_pronote_data.absences = []
        mock_pronote_data.delays = []
        mock_pronote_data.punishments = []
        mock_pronote_data.evaluations = []
        mock_pronote_data.homework = []
        mock_pronote_data.homework_period = []
        mock_pronote_data.information_and_surveys = []
        mock_pronote_data.menus = []
        mock_pronote_data.periods = []
        mock_pronote_data.current_period = None
        mock_pronote_data.current_period_key = None
        mock_pronote_data.previous_periods = []
        mock_pronote_data.active_periods = []
        mock_pronote_data.ical_url = None
        mock_pronote_data.previous_period_data = {}
        mock_pronote_data.credentials = None
        mock_pronote_data.password = None

        mock_coordinator._api_client.is_authenticated.return_value = True
        mock_coordinator._api_client.fetch_all_data.return_value = mock_pronote_data

        with patch("custom_components.pronote.repairs.async_delete_issue_for_entry"):
            with patch.object(mock_coordinator, "_compare_and_fire_events"):
                result = await mock_coordinator._async_update_data()

        assert result is not None
        assert result["child_info"].name == "Test Student"
        assert result["sensor_prefix"] == "test_student"
        # is_authenticated returns True, so authenticate is NOT called
        mock_coordinator._api_client.authenticate.assert_not_called()
        mock_coordinator._api_client.fetch_all_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_update_data_auth_error(self, mock_coordinator):
        """Test authentication error handling."""
        from custom_components.pronote.api import AuthenticationError

        mock_coordinator._api_client.is_authenticated.return_value = False
        mock_coordinator._api_client.authenticate.side_effect = AuthenticationError("Invalid credentials")

        with patch("custom_components.pronote.repairs.async_create_session_expired_issue") as mock_create:
            with pytest.raises(ConfigEntryAuthFailed, match="Authentication failed"):
                await mock_coordinator._async_update_data()

        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_update_data_rate_limit(self, mock_coordinator):
        """Test rate limit error handling."""
        from custom_components.pronote.api import RateLimitError

        mock_coordinator._api_client.is_authenticated.return_value = False
        mock_coordinator._api_client.authenticate.side_effect = RateLimitError("Rate limited", retry_after=60)

        with patch("custom_components.pronote.repairs.async_create_rate_limited_issue") as mock_create:
            with pytest.raises(UpdateFailed, match="Rate limited"):
                await mock_coordinator._async_update_data()

        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_a_malformed_answer_is_retried_not_reauthenticated(self, mock_coordinator):
        """A broken payload is not a credentials problem.

        A bare KeyError('dataSec') was reported as "Token expiré, veuillez
        reconfigurer l'intégration avec un nouveau QR code" and opened a reauth
        flow, over a server answer.
        """
        from custom_components.pronote.api import InvalidResponseError

        mock_coordinator._api_client.is_authenticated.return_value = False
        mock_coordinator._api_client.authenticate.side_effect = InvalidResponseError(
            "Réponse inattendue de Pronote (champ 'dataSec' manquant)"
        )

        with pytest.raises(UpdateFailed, match="unexpected"):
            await mock_coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_a_suspended_ip_is_retried_not_reauthenticated(self, mock_coordinator):
        """A banned IP must never open a reauth flow.

        Asking for a new QR code makes the user retry, and retrying is exactly
        what keeps Pronote's ban alive.
        """
        from custom_components.pronote.api import IPSuspendedError

        mock_coordinator._api_client.is_authenticated.return_value = False
        mock_coordinator._api_client.authenticate.side_effect = IPSuspendedError("IP suspendue")

        with patch("custom_components.pronote.repairs.async_create_rate_limited_issue") as mock_create:
            with pytest.raises(UpdateFailed):
                await mock_coordinator._async_update_data()

        mock_create.assert_called_once()
        assert mock_create.call_args[0][2] == 900

    @pytest.mark.asyncio
    async def test_async_update_data_circuit_breaker_open(self, mock_coordinator):
        """Test circuit breaker open error handling."""
        from custom_components.pronote.api import CircuitBreakerOpenError

        mock_coordinator._api_client.is_authenticated.return_value = False
        mock_coordinator._api_client.authenticate.side_effect = CircuitBreakerOpenError("Circuit open")

        with pytest.raises(UpdateFailed, match="temporarily unavailable"):
            await mock_coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_async_update_data_connection_error(self, mock_coordinator):
        """Test connection error handling during auth."""
        from custom_components.pronote.api import ConnectionError

        mock_coordinator._api_client.is_authenticated.return_value = False
        mock_coordinator._api_client.authenticate.side_effect = ConnectionError("Network error")

        with patch("custom_components.pronote.repairs.async_create_connection_error_issue") as mock_create:
            with pytest.raises(UpdateFailed, match="Connection error"):
                await mock_coordinator._async_update_data()

        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_update_data_not_authenticated(self, mock_coordinator):
        """Test when client is not authenticated after auth attempt."""
        mock_coordinator._api_client.is_authenticated.return_value = False

        with patch("custom_components.pronote.repairs.async_create_session_expired_issue") as mock_create:
            with patch("custom_components.pronote.repairs.async_delete_issue_for_entry"):
                with pytest.raises(ConfigEntryAuthFailed, match="Unable to authenticate"):
                    await mock_coordinator._async_update_data()

        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_update_data_fetch_rate_limit(self, mock_coordinator):
        """Test rate limit during fetch."""
        from custom_components.pronote.api import RateLimitError

        mock_coordinator._api_client.is_authenticated.return_value = True
        mock_coordinator._api_client.fetch_all_data.side_effect = RateLimitError("Rate limited", retry_after=120)

        with patch("custom_components.pronote.repairs.async_create_rate_limited_issue") as mock_create:
            with patch("custom_components.pronote.repairs.async_delete_issue_for_entry"):
                with pytest.raises(UpdateFailed, match="Rate limited"):
                    await mock_coordinator._async_update_data()

        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_update_data_no_child_info(self, mock_coordinator):
        """Test when no child info is returned."""
        mock_pronote_data = MagicMock()
        mock_pronote_data.child_info = None

        mock_coordinator._api_client.is_authenticated.return_value = True
        mock_coordinator._api_client.fetch_all_data.return_value = mock_pronote_data

        with patch("custom_components.pronote.repairs.async_delete_issue_for_entry"):
            with pytest.raises(UpdateFailed, match="No child info available"):
                await mock_coordinator._async_update_data()

    def test_compute_next_alarm_with_today_lessons(self, mock_coordinator):
        """Test computing next alarm with today's lessons."""
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("Europe/Paris")
        mock_coordinator.hass.config.time_zone = "Europe/Paris"

        lessons_today = [
            SimpleNamespace(canceled=False, start=datetime(2025, 1, 15, 8, 0, tzinfo=tz)),
        ]

        future_time = datetime(2025, 1, 15, 7, 0, tzinfo=tz)
        with patch("custom_components.pronote.coordinator.datetime") as mock_dt:
            mock_dt.now.return_value = future_time
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            result = mock_coordinator._compute_next_alarm(lessons_today, None, None)

        assert result is not None
        # Alarm should be 30 minutes before 8:00 = 7:30
        assert result.hour == 7
        assert result.minute == 30

    def test_compute_next_alarm_with_next_day_lessons(self, mock_coordinator):
        """Test computing next alarm with next day lessons."""
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("Europe/Paris")
        mock_coordinator.hass.config.time_zone = "Europe/Paris"

        lessons_today = []
        lessons_next_day = [
            SimpleNamespace(canceled=False, start=datetime(2025, 1, 16, 9, 0, tzinfo=tz)),
        ]

        with patch("custom_components.pronote.coordinator.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 1, 15, 10, 0, tzinfo=tz)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            result = mock_coordinator._compute_next_alarm(lessons_today, lessons_next_day, None)

        assert result is not None
        # Alarm should be 30 minutes before 9:00 = 8:30
        assert result.hour == 8
        assert result.minute == 30

    def test_compute_next_alarm_no_lessons(self, mock_coordinator):
        """Test computing next alarm with no lessons."""
        result = mock_coordinator._compute_next_alarm(None, None, None)
        assert result is None

    def test_compute_next_alarm_all_canceled_today(self, mock_coordinator):
        """Test computing next alarm when all today lessons are canceled."""
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("Europe/Paris")
        mock_coordinator.hass.config.time_zone = "Europe/Paris"

        lessons_today = [
            SimpleNamespace(canceled=True, start=datetime(2025, 1, 15, 8, 0, tzinfo=tz)),
        ]
        lessons_next_day = [
            SimpleNamespace(canceled=False, start=datetime(2025, 1, 16, 9, 0, tzinfo=tz)),
        ]

        with patch("custom_components.pronote.coordinator.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 1, 15, 7, 0, tzinfo=tz)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            result = mock_coordinator._compute_next_alarm(lessons_today, lessons_next_day, None)

        # Should use next day's alarm
        assert result is not None
        assert result.day == 16

    def test_compute_next_alarm_skips_today_in_period(self, mock_coordinator):
        """Test that lessons_period skips today and finds next school day.

        The alarm is a morning wake-up alarm. Once today's alarm has passed,
        it should find the first lesson of the next school day, not the next
        lesson later today.
        """
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("Europe/Paris")
        mock_coordinator.hass.config.time_zone = "Europe/Paris"
        mock_coordinator.config_entry.options = {"alarm_offset": 60}

        # Today's alarm already passed, tomorrow all canceled
        lessons_today = [
            SimpleNamespace(canceled=False, start=datetime(2025, 1, 15, 8, 0, tzinfo=tz)),
        ]
        lessons_next_day = [
            SimpleNamespace(canceled=True, start=datetime(2025, 1, 16, 8, 0, tzinfo=tz)),
        ]
        # Period includes today's lessons (should be skipped),
        # tomorrow all canceled (should be skipped),
        # and Jan 17 with a lesson at 9:00 (next school day)
        lessons_period = [
            SimpleNamespace(canceled=False, start=datetime(2025, 1, 15, 14, 0, tzinfo=tz)),
            SimpleNamespace(canceled=False, start=datetime(2025, 1, 15, 16, 0, tzinfo=tz)),
            SimpleNamespace(canceled=True, start=datetime(2025, 1, 16, 8, 0, tzinfo=tz)),
            SimpleNamespace(canceled=False, start=datetime(2025, 1, 17, 9, 0, tzinfo=tz)),
            SimpleNamespace(canceled=False, start=datetime(2025, 1, 17, 10, 0, tzinfo=tz)),
        ]

        # now = 13:10 on Jan 15
        with patch("custom_components.pronote.coordinator.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 1, 15, 13, 10, tzinfo=tz)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            result = mock_coordinator._compute_next_alarm(lessons_today, lessons_next_day, lessons_period)

        # Should skip today (already handled) and tomorrow (all canceled)
        # and find Jan 17 first lesson at 9:00 → alarm at 8:00
        assert result is not None
        assert result.day == 17
        assert result.hour == 8
        assert result.minute == 0


class TestCompareAndFireEvents:
    """Tests for _compare_and_fire_events and related methods."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator with data."""
        entry = MagicMock()
        entry.title = "Test"
        entry.options = {"refresh_interval": 15, "nickname": "Jean"}

        with patch.object(PronoteDataUpdateCoordinator, "__init__", lambda self, *a, **kw: None):
            coord = PronoteDataUpdateCoordinator.__new__(PronoteDataUpdateCoordinator)
            coord.hass = MagicMock()
            coord.config_entry = entry
            coord.data = {
                "child_info": SimpleNamespace(name="Test Student"),
                "sensor_prefix": "test_student",
            }
            coord._previous_period_cache = None
            coord._previous_period_cache_date = None
        return coord

    def test_compare_data_no_previous(self, mock_coordinator):
        """Test _compare_data with no previous data."""
        mock_coordinator._trigger_event = MagicMock()

        mock_coordinator._compare_data(None, "grades", ["date"], "new_grade", lambda x: {"date": "2025-01-15"})

        mock_coordinator._trigger_event.assert_not_called()

    def test_compare_data_no_current(self, mock_coordinator):
        """Test _compare_data with no current data."""
        mock_coordinator._trigger_event = MagicMock()
        mock_coordinator.data = None

        mock_coordinator._compare_data(
            {"grades": []}, "grades", ["date"], "new_grade", lambda x: {"date": "2025-01-15"}
        )

        mock_coordinator._trigger_event.assert_not_called()

    def test_compare_data_fires_event_for_new_items(self, mock_coordinator):
        """Test _compare_data fires events for new items."""
        with patch.object(mock_coordinator, "_trigger_event") as mock_trigger:
            # Use SimpleNamespace to mock Grade model objects
            grade1 = SimpleNamespace(
                id="g1",
                date=date(2025, 1, 15),
                subject="Math",
                grade="15",
                grade_out_of="20",
                coefficient="1",
                class_average="12",
                comment="",
                is_bonus=False,
                is_optional=False,
            )
            grade2 = SimpleNamespace(
                id="g2",
                date=date(2025, 1, 16),
                subject="French",
                grade="12",
                grade_out_of="20",
                coefficient="1",
                class_average="14",
                comment="",
                is_bonus=False,
                is_optional=False,
            )

            mock_coordinator.data["grades"] = [grade1, grade2]

            previous = {"grades": [grade1]}

            from custom_components.pronote.pronote_formatter import format_grade

            mock_coordinator._compare_data(
                previous, "grades", ["date", "subject", "grade_out_of"], "new_grade", format_grade
            )

            mock_trigger.assert_called_once()
            call_args = mock_trigger.call_args
            assert call_args[0][0] == "new_grade"

    def test_trigger_event_fires_on_bus(self, mock_coordinator):
        """Test _trigger_event fires event on HA bus."""
        mock_coordinator.hass.bus.async_fire = MagicMock()

        event_data = {"date": "2025-01-15", "subject": "Math"}
        mock_coordinator._trigger_event("new_grade", event_data)

        mock_coordinator.hass.bus.async_fire.assert_called_once()
        call_args = mock_coordinator.hass.bus.async_fire.call_args
        assert call_args[0][0] == EVENT_TYPE
        payload = call_args[0][1]
        assert payload["child_name"] == "Test Student"
        assert payload["child_nickname"] == "Jean"
        assert payload["type"] == "new_grade"
        assert payload["data"] == event_data

    def test_trigger_event_no_data(self, mock_coordinator):
        """Test _trigger_event returns early when no data."""
        mock_coordinator.hass.bus.async_fire = MagicMock()
        mock_coordinator.data = None

        mock_coordinator._trigger_event("new_grade", {})

        mock_coordinator.hass.bus.async_fire.assert_not_called()

    def test_compare_and_fire_events_calls_all_comparisons(self, mock_coordinator):
        """Test _compare_and_fire_events calls all comparison types."""
        mock_coordinator._compare_data = MagicMock()

        mock_coordinator._compare_and_fire_events({})

        assert mock_coordinator._compare_data.call_count == 4  # grades, absences, delays, evaluations


class TestCoordinatorAdditionalCoverage:
    """Additional tests for coordinator to reach 95% coverage."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator with fully mocked hass."""
        entry = MagicMock()
        entry.title = "Test Student"
        entry.options = {"refresh_interval": 15, "nickname": "Jean", "alarm_offset": 30}
        entry.data = {
            "connection_type": "username_password",
            "account_type": "student",
            "url": "https://example.com",
            "username": "test",
            "password": "pass",
        }

        with patch.object(PronoteDataUpdateCoordinator, "__init__", lambda self, *a, **kw: None):
            coord = PronoteDataUpdateCoordinator.__new__(PronoteDataUpdateCoordinator)
            coord.hass = MagicMock()
            coord.hass.config.time_zone = "Europe/Paris"
            coord.config_entry = entry
            coord.data = None
            coord._api_client = MagicMock()
            coord._api_client.authenticate = AsyncMock()
            coord._api_client.fetch_all_data = AsyncMock()
            coord._api_client.is_authenticated = MagicMock(return_value=True)
            coord._api_client.check_session = AsyncMock(return_value=True)
            coord.logger = MagicMock()
            coord._previous_period_cache = None
            coord._previous_period_cache_date = None
        return coord

    @pytest.mark.asyncio
    async def test_async_update_data_invalid_response_error(self, mock_coordinator):
        """Test InvalidResponseError handling during fetch."""
        from custom_components.pronote.api import InvalidResponseError

        mock_coordinator._api_client.is_authenticated.return_value = True
        mock_coordinator._api_client.fetch_all_data.side_effect = InvalidResponseError("Invalid response")

        with patch("custom_components.pronote.repairs.async_delete_issue_for_entry"):
            with pytest.raises(UpdateFailed, match="Invalid response"):
                await mock_coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_async_update_data_connection_error_during_fetch(self, mock_coordinator):
        """Test ConnectionError handling during fetch."""
        from custom_components.pronote.api import ConnectionError

        mock_coordinator._api_client.is_authenticated.return_value = True
        mock_coordinator._api_client.fetch_all_data.side_effect = ConnectionError("Network error")

        with patch("custom_components.pronote.repairs.async_create_connection_error_issue") as mock_create:
            with patch("custom_components.pronote.repairs.async_delete_issue_for_entry"):
                with pytest.raises(UpdateFailed, match="Connection error"):
                    await mock_coordinator._async_update_data()

        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_update_data_generic_exception_during_fetch(self, mock_coordinator):
        """Test generic Exception handling during fetch."""
        mock_coordinator._api_client.is_authenticated.return_value = True
        mock_coordinator._api_client.fetch_all_data.side_effect = RuntimeError("Unknown error")

        with patch("custom_components.pronote.repairs.async_delete_issue_for_entry"):
            with pytest.raises(UpdateFailed, match="Error fetching data"):
                await mock_coordinator._async_update_data()

    @pytest.mark.asyncio
    async def test_async_update_data_auth_error_during_fetch(self, mock_coordinator):
        """Test AuthenticationError during fetch triggers reset and UpdateFailed (not ConfigEntryAuthFailed)."""
        from custom_components.pronote.api import AuthenticationError

        mock_coordinator._api_client.is_authenticated.return_value = True
        mock_coordinator._api_client.fetch_all_data.side_effect = AuthenticationError("Session expired")

        with patch("custom_components.pronote.repairs.async_delete_issue_for_entry"):
            with pytest.raises(UpdateFailed, match="Session expired"):
                await mock_coordinator._async_update_data()

        mock_coordinator._api_client.reset.assert_called_once()

    @pytest.mark.asyncio
    async def test_token_kept_from_dropped_client_is_used_for_the_next_login(self, mock_coordinator):
        """A failed session check spent the stored token: log in with the one it received."""
        from custom_components.pronote.api import AuthenticationError
        from custom_components.pronote.api.models import Credentials

        mock_coordinator.config_entry.data = {
            "connection_type": "qrcode",
            "account_type": "parent",
            "qr_code_url": "https://example.com",
            "qr_code_username": "user",
            "qr_code_password": "spent_token",
            "qr_code_uuid": "uuid",
        }
        mock_coordinator._api_client.is_authenticated.return_value = True
        mock_coordinator._api_client.check_session = AsyncMock(return_value=False)
        mock_coordinator._api_client.get_credentials.return_value = Credentials(
            pronote_url="https://example.com", username="user", password="fresh_token", uuid="uuid"
        )
        mock_coordinator._api_client.authenticate = AsyncMock(side_effect=AuthenticationError("stop here"))

        def update_entry_side_effect(entry, **kwargs):
            entry.data = kwargs["data"]

        with (
            patch("custom_components.pronote.repairs.async_delete_issue_for_entry"),
            patch("custom_components.pronote.repairs.async_create_session_expired_issue"),
            patch.object(
                mock_coordinator.hass.config_entries, "async_update_entry", side_effect=update_entry_side_effect
            ),
            pytest.raises(ConfigEntryAuthFailed),
        ):
            await mock_coordinator._async_update_data()

        assert mock_coordinator.config_entry.data["qr_code_password"] == "fresh_token"
        used_config = mock_coordinator._api_client.authenticate.call_args[0][1]
        assert used_config["qr_code_password"] == "fresh_token"

    @pytest.mark.asyncio
    async def test_failed_fetch_persists_the_token_kept_from_the_dropped_client(self, mock_coordinator):
        """pronotepy rotated the token mid-fetch, then the fetch failed: the token is saved."""
        from custom_components.pronote.api.models import Credentials

        mock_coordinator.config_entry.data = {
            "connection_type": "qrcode",
            "account_type": "parent",
            "qr_code_url": "https://example.com",
            "qr_code_username": "user",
            "qr_code_password": "spent_token",
            "qr_code_uuid": "uuid",
        }
        mock_coordinator._api_client.is_authenticated.return_value = True
        mock_coordinator._api_client.check_session = AsyncMock(return_value=True)
        mock_coordinator._api_client._client = MagicMock(password="spent_token")
        mock_coordinator._api_client.fetch_all_data.side_effect = RuntimeError("boom")
        mock_coordinator._api_client.get_credentials.return_value = None

        def reset():
            mock_coordinator._api_client.get_credentials.return_value = Credentials(
                pronote_url="https://example.com", username="user", password="fresh_token", uuid="uuid"
            )

        mock_coordinator._api_client.reset.side_effect = reset

        with (
            patch("custom_components.pronote.repairs.async_delete_issue_for_entry"),
            patch.object(mock_coordinator.hass.config_entries, "async_update_entry") as mock_update,
            pytest.raises(UpdateFailed),
        ):
            await mock_coordinator._async_update_data()

        mock_update.assert_called_once()
        assert mock_update.call_args[1]["data"]["qr_code_password"] == "fresh_token"

    def test_late_login_token_is_persisted_at_once(self, mock_coordinator):
        """A login adopted after its refresh gave up has its token saved right away."""
        mock_coordinator.config_entry.data = {
            "connection_type": "qrcode",
            "account_type": "parent",
            "qr_code_url": "https://example.com",
            "qr_code_username": "user",
            "qr_code_password": "spent_token",
            "qr_code_uuid": "uuid",
        }
        mock_coordinator.config_entry.options = {}
        mock_coordinator._api_client._client = MagicMock(password="fresh_token")
        mock_coordinator._api_client._client.export_credentials.return_value = {
            "pronote_url": "https://example.com",
            "username": "user",
            "password": "fresh_token",
            "uuid": "uuid",
        }
        mock_coordinator._api_client.get_credentials = lambda: mock_coordinator._api_client._credentials

        with patch.object(mock_coordinator.hass.config_entries, "async_update_entry") as mock_update:
            mock_coordinator._persist_late_login()

        mock_update.assert_called_once()
        assert mock_update.call_args[1]["data"]["qr_code_password"] == "fresh_token"

    @pytest.mark.asyncio
    async def test_async_update_data_saves_qr_credentials_after_auth(self, mock_coordinator):
        """Test QR code credentials are saved immediately after successful auth."""
        from custom_components.pronote.api.models import Credentials

        mock_pronote_data = MagicMock()
        mock_pronote_data.child_info = SimpleNamespace(name="Test Student")
        mock_pronote_data.lessons_today = []
        mock_pronote_data.lessons_tomorrow = []
        mock_pronote_data.lessons_next_day = []
        mock_pronote_data.lessons_period = []
        mock_pronote_data.grades = []
        mock_pronote_data.averages = []
        mock_pronote_data.overall_average = None
        mock_pronote_data.absences = []
        mock_pronote_data.delays = []
        mock_pronote_data.punishments = []
        mock_pronote_data.evaluations = []
        mock_pronote_data.homework = []
        mock_pronote_data.homework_period = []
        mock_pronote_data.information_and_surveys = []
        mock_pronote_data.menus = []
        mock_pronote_data.periods = []
        mock_pronote_data.current_period = None
        mock_pronote_data.current_period_key = None
        mock_pronote_data.previous_periods = []
        mock_pronote_data.active_periods = []
        mock_pronote_data.ical_url = None
        mock_pronote_data.previous_period_data = {}
        mock_pronote_data.credentials = None
        mock_pronote_data.password = None

        # Session invalid → force re-auth
        mock_coordinator._api_client.check_session = AsyncMock(return_value=False)
        mock_coordinator._api_client.is_authenticated.return_value = True
        mock_coordinator._api_client.fetch_all_data.return_value = mock_pronote_data
        new_credentials = Credentials(
            pronote_url="https://example.com",
            username="new_user",
            password="new_token",
            uuid="new_uuid",
            client_identifier="new_client_id",
        )
        # The dropped client carried no token: credentials only appear with the login
        mock_coordinator._api_client.get_credentials.return_value = None

        async def authenticate(*_args):
            mock_coordinator._api_client.get_credentials.return_value = new_credentials

        mock_coordinator._api_client.authenticate = AsyncMock(side_effect=authenticate)
        # Set live client password to match saved credentials (no drift)
        mock_coordinator._api_client._client = MagicMock()
        mock_coordinator._api_client._client.password = "new_token"
        mock_coordinator.config_entry.data = {
            "connection_type": "qrcode",
            "account_type": "student",
            "qr_code_json": '{"old":"data"}',
            "qr_code_pin": "1234",
        }

        def update_entry_side_effect(entry, **kwargs):
            if "data" in kwargs:
                entry.data = kwargs["data"]

        with (
            patch("custom_components.pronote.repairs.async_delete_issue_for_entry"),
            patch.object(
                mock_coordinator.hass.config_entries,
                "async_update_entry",
                side_effect=update_entry_side_effect,
            ) as mock_update,
            patch.object(mock_coordinator, "_compare_and_fire_events"),
        ):
            result = await mock_coordinator._async_update_data()

        assert result is not None
        # Called once by _save_credentials_if_needed (no drift since live password matches)
        mock_update.assert_called_once()
        call_kwargs = mock_update.call_args[1]
        assert "data" in call_kwargs
        assert call_kwargs["data"]["qr_code_url"] == "https://example.com"
        assert call_kwargs["data"]["qr_code_username"] == "new_user"
        assert call_kwargs["data"]["qr_code_password"] == "new_token"
        assert call_kwargs["data"]["qr_code_uuid"] == "new_uuid"
        assert call_kwargs["data"]["client_identifier"] == "new_client_id"
        # Single-use QR payload must be removed after successful auth
        assert "qr_code_json" not in call_kwargs["data"]
        # ...but the PIN stays: Pronote re-runs its two-factor check later on
        assert call_kwargs["data"]["qr_code_pin"] == "1234"

    @pytest.mark.asyncio
    async def test_check_token_drift_detects_silent_rotation(self, mock_coordinator):
        """Test _check_token_drift detects when pronotepy silently rotates the token."""
        mock_pronote_data = MagicMock()
        mock_pronote_data.child_info = SimpleNamespace(name="Test Student")
        mock_pronote_data.lessons_today = []
        mock_pronote_data.lessons_tomorrow = []
        mock_pronote_data.lessons_next_day = []
        mock_pronote_data.lessons_period = []
        mock_pronote_data.grades = []
        mock_pronote_data.averages = []
        mock_pronote_data.overall_average = None
        mock_pronote_data.absences = []
        mock_pronote_data.delays = []
        mock_pronote_data.punishments = []
        mock_pronote_data.evaluations = []
        mock_pronote_data.homework = []
        mock_pronote_data.homework_period = []
        mock_pronote_data.information_and_surveys = []
        mock_pronote_data.menus = []
        mock_pronote_data.periods = []
        mock_pronote_data.current_period = None
        mock_pronote_data.current_period_key = None
        mock_pronote_data.previous_periods = []
        mock_pronote_data.active_periods = []
        mock_pronote_data.ical_url = None
        mock_pronote_data.previous_period_data = {}

        # Session is valid → reuse path (no authenticate call)
        mock_coordinator._api_client.is_authenticated.return_value = True
        mock_coordinator._api_client.check_session = AsyncMock(return_value=True)
        mock_coordinator._api_client.fetch_all_data.return_value = mock_pronote_data

        # Simulate pronotepy silently rotating the password during fetch
        mock_client = MagicMock()
        mock_client.password = "silently_rotated_token"
        mock_client.export_credentials.return_value = {
            "pronote_url": "https://example.com",
            "username": "user",
            "password": "silently_rotated_token",
            "uuid": "uuid123",
            "client_identifier": "client_id",
        }
        mock_coordinator._api_client._client = mock_client
        # Make get_credentials() read _credentials dynamically (not a fixed mock)
        mock_coordinator._api_client.get_credentials = lambda: mock_coordinator._api_client._credentials

        # Config entry has old password
        mock_coordinator.config_entry.data = {
            "connection_type": "qrcode",
            "account_type": "student",
            "qr_code_url": "https://example.com",
            "qr_code_username": "user",
            "qr_code_password": "old_token",
            "qr_code_uuid": "uuid123",
            "client_identifier": "client_id",
        }

        def update_entry_side_effect(entry, **kwargs):
            if "data" in kwargs:
                entry.data = kwargs["data"]

        with (
            patch("custom_components.pronote.repairs.async_delete_issue_for_entry"),
            patch.object(
                mock_coordinator.hass.config_entries,
                "async_update_entry",
                side_effect=update_entry_side_effect,
            ) as mock_update,
            patch.object(mock_coordinator, "_compare_and_fire_events"),
        ):
            await mock_coordinator._async_update_data()

        # Drift detected → credentials persisted
        mock_update.assert_called()
        last_call_kwargs = mock_update.call_args[1]
        assert last_call_kwargs["data"]["qr_code_password"] == "silently_rotated_token"

    @pytest.mark.asyncio
    async def test_check_token_drift_no_drift_no_update(self, mock_coordinator):
        """Test _check_token_drift does nothing when password hasn't changed."""
        mock_pronote_data = MagicMock()
        mock_pronote_data.child_info = SimpleNamespace(name="Test Student")
        mock_pronote_data.lessons_today = []
        mock_pronote_data.lessons_tomorrow = []
        mock_pronote_data.lessons_next_day = []
        mock_pronote_data.lessons_period = []
        mock_pronote_data.grades = []
        mock_pronote_data.averages = []
        mock_pronote_data.overall_average = None
        mock_pronote_data.absences = []
        mock_pronote_data.delays = []
        mock_pronote_data.punishments = []
        mock_pronote_data.evaluations = []
        mock_pronote_data.homework = []
        mock_pronote_data.homework_period = []
        mock_pronote_data.information_and_surveys = []
        mock_pronote_data.menus = []
        mock_pronote_data.periods = []
        mock_pronote_data.current_period = None
        mock_pronote_data.current_period_key = None
        mock_pronote_data.previous_periods = []
        mock_pronote_data.active_periods = []
        mock_pronote_data.ical_url = None
        mock_pronote_data.previous_period_data = {}

        # Session is valid → reuse path
        mock_coordinator._api_client.is_authenticated.return_value = True
        mock_coordinator._api_client.check_session = AsyncMock(return_value=True)
        mock_coordinator._api_client.fetch_all_data.return_value = mock_pronote_data

        # Live password matches stored password — no drift
        mock_client = MagicMock()
        mock_client.password = "same_token"
        mock_coordinator._api_client._client = mock_client

        mock_coordinator.config_entry.data = {
            "connection_type": "qrcode",
            "account_type": "student",
            "qr_code_url": "https://example.com",
            "qr_code_username": "user",
            "qr_code_password": "same_token",
            "qr_code_uuid": "uuid123",
        }

        with patch("custom_components.pronote.repairs.async_delete_issue_for_entry"):
            with patch.object(mock_coordinator.hass.config_entries, "async_update_entry") as mock_update:
                with patch.object(mock_coordinator, "_compare_and_fire_events"):
                    await mock_coordinator._async_update_data()

        # No drift → no update call
        mock_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_update_data_with_previous_period_data(self, mock_coordinator):
        """Test previous period data is added to the result."""
        mock_pronote_data = MagicMock()
        mock_pronote_data.child_info = SimpleNamespace(name="Test Student")
        mock_pronote_data.lessons_today = []
        mock_pronote_data.lessons_tomorrow = []
        mock_pronote_data.lessons_next_day = []
        mock_pronote_data.lessons_period = []
        mock_pronote_data.grades = []
        mock_pronote_data.averages = []
        mock_pronote_data.overall_average = None
        mock_pronote_data.absences = []
        mock_pronote_data.delays = []
        mock_pronote_data.punishments = []
        mock_pronote_data.evaluations = []
        mock_pronote_data.homework = []
        mock_pronote_data.homework_period = []
        mock_pronote_data.information_and_surveys = []
        mock_pronote_data.menus = []
        mock_pronote_data.periods = []
        mock_pronote_data.current_period = None
        mock_pronote_data.current_period_key = None
        mock_pronote_data.previous_periods = []
        mock_pronote_data.active_periods = []
        mock_pronote_data.ical_url = None
        mock_pronote_data.previous_period_data = {
            "grades_trimestre_1": [{"grade": "15"}],
            "averages_trimestre_1": [{"average": "14"}],
        }
        mock_pronote_data.credentials = None
        mock_pronote_data.password = None

        mock_coordinator._api_client.is_authenticated.return_value = True
        mock_coordinator._api_client.fetch_all_data.return_value = mock_pronote_data

        with patch("custom_components.pronote.repairs.async_delete_issue_for_entry"):
            with patch.object(mock_coordinator, "_compare_and_fire_events"):
                result = await mock_coordinator._async_update_data()

        assert result is not None
        assert "grades_trimestre_1" in result
        assert result["grades_trimestre_1"] == [{"grade": "15"}]
        assert "averages_trimestre_1" in result

    def test_compare_data_keyerror_in_format(self, mock_coordinator):
        """Test _compare_data handles KeyError when formatting items."""
        mock_coordinator._trigger_event = MagicMock()

        # Create items that will cause KeyError when formatted
        class BadItem:
            pass

        previous = {"grades": [BadItem()]}
        mock_coordinator.data = {"grades": [BadItem()]}

        def bad_format(item):
            return {"missing_key": "value"}  # Will cause KeyError for compare_keys

        mock_coordinator._compare_data(previous, "grades", ["date", "subject"], "new_grade", bad_format)

        # Should not raise and not call trigger
        mock_coordinator._trigger_event.assert_not_called()


class TestAuthConfigFromOptions:
    """device_name and account_pin are set in the options, not at setup."""

    @staticmethod
    def _coordinator(data, options):
        coordinator = PronoteDataUpdateCoordinator.__new__(PronoteDataUpdateCoordinator)
        coordinator.config_entry = MagicMock()
        coordinator.config_entry.data = data
        coordinator.config_entry.options = options
        return coordinator

    def test_the_options_win_over_the_entry(self):
        coordinator = self._coordinator(
            {"connection_type": "qrcode", "device_name": "Home Assistant"},
            {"device_name": "Salon", "account_pin": "9876"},
        )

        config = coordinator._auth_config()

        assert config["device_name"] == "Salon"
        assert config["account_pin"] == "9876"
        assert config["connection_type"] == "qrcode"

    def test_an_empty_option_never_erases_the_stored_value(self):
        """The options form submits "" for an untouched field."""
        coordinator = self._coordinator(
            {"device_name": "Home Assistant"},
            {"device_name": "", "account_pin": ""},
        )

        config = coordinator._auth_config()

        assert config["device_name"] == "Home Assistant"
        assert "account_pin" not in config
