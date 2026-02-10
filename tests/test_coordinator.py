"""Tests for the Pronote coordinator _fetch_all_sync_data and _async_update_data."""

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.pronote.coordinator import (
    PronoteDataUpdateCoordinator,
    _fetch_all_sync_data,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TODAY = date(2025, 3, 10)  # A Monday


def _make_lesson(start_dt):
    """Create a minimal lesson SimpleNamespace."""
    return SimpleNamespace(
        start=start_dt,
        end=start_dt + timedelta(hours=1),
        canceled=False,
        subject=SimpleNamespace(name="Maths"),
        teacher_name="M. Dupont",
        classroom="A101",
        status="",
        background_color="#FFFFFF",
        teacher_names=["M. Dupont"],
        classrooms=["A101"],
        outing=False,
        memo=None,
        group_name=None,
        group_names=[],
        exempted=False,
        virtual_classrooms=[],
        num=1,
        detention=False,
        test=False,
    )


def _make_period(name, start, end=None, **kwargs):
    """Create a minimal period SimpleNamespace."""
    return SimpleNamespace(
        name=name,
        start=start,
        end=end or start + timedelta(days=90),
        grades=kwargs.get("grades", []),
        absences=kwargs.get("absences", []),
        delays=kwargs.get("delays", []),
        averages=kwargs.get("averages", []),
        punishments=kwargs.get("punishments", []),
        evaluations=kwargs.get("evaluations", []),
        overall_average=kwargs.get("overall_average", "14.5"),
    )


def _make_homework(hw_date):
    return SimpleNamespace(
        date=hw_date,
        subject=SimpleNamespace(name="Francais"),
        description="Exercice 5",
        done=False,
        background_color="#FFFFFF",
        files=[],
    )


def _make_info_survey(creation_date):
    return SimpleNamespace(
        author="M. Le Principal",
        title="Sortie",
        read=False,
        creation_date=creation_date,
        start_date=creation_date,
        end_date=creation_date + timedelta(days=5),
        category="Information",
        survey=False,
        anonymous_response=False,
        attachments=[],
        template=None,
        shared_template=None,
        content="Contenu",
    )


def _make_menu(menu_date):
    return SimpleNamespace(
        name="Dejeuner",
        date=menu_date,
        is_lunch=True,
        is_dinner=False,
        first_meal=None,
        main_meal=None,
        side_meal=None,
        other_meal=None,
        cheese=None,
        dessert=None,
    )


def _make_client(
    *,
    account_type="student",
    lessons_today=None,
    lessons_tomorrow=None,
    lessons_period=None,
    lessons_side_effects=None,
    homework=None,
    homework_period=None,
    homework_side_effect=None,
    info_surveys=None,
    info_surveys_side_effect=None,
    ical_url="https://pronote.example/ical",
    ical_side_effect=None,
    menus=None,
    menus_side_effect=None,
    periods=None,
    periods_side_effect=None,
    current_period=None,
    child_info=None,
    export_credentials=None,
    password="secret",
):
    """Build a mock Pronote client with configurable return values and side effects."""
    client = MagicMock()
    client.password = password
    client.info = child_info or SimpleNamespace(name="Jean Dupont", class_name="3emeA", establishment="College")
    client.export_credentials.return_value = export_credentials or {
        "pronote_url": "https://pronote.example/eleve.html",
        "username": "jean.dupont",
        "password": "secret",
        "uuid": "uid-123",
        "client_identifier": "cid-456",
    }

    if current_period is None:
        current_period = _make_period("Trimestre 2", date(2025, 1, 1))
    client.current_period = current_period

    if periods is None:
        periods = [current_period]
    if periods_side_effect:
        type(client).periods = property(lambda self: (_ for _ in ()).throw(periods_side_effect))
    else:
        type(client).periods = property(lambda self: periods)

    # Lessons helper: allows per-call side effects
    if lessons_side_effects is not None:
        client.lessons.side_effect = lessons_side_effects
    else:

        def lessons_fn(d, end=None):
            if end is not None:
                return lessons_period if lessons_period is not None else []
            if d == TODAY:
                return lessons_today if lessons_today is not None else []
            if d == TODAY + timedelta(days=1):
                return lessons_tomorrow if lessons_tomorrow is not None else []
            return []

        client.lessons.side_effect = lessons_fn

    # Homework
    if homework_side_effect:
        client.homework.side_effect = homework_side_effect
    else:

        def homework_fn(d, end=None):
            if end is not None:
                return homework_period if homework_period is not None else []
            return homework if homework is not None else []

        client.homework.side_effect = homework_fn

    # Information and surveys
    if info_surveys_side_effect:
        client.information_and_surveys.side_effect = info_surveys_side_effect
    else:
        client.information_and_surveys.return_value = info_surveys or []

    # iCal
    if ical_side_effect:
        client.export_ical.side_effect = ical_side_effect
    else:
        client.export_ical.return_value = ical_url

    # Menus
    if menus_side_effect:
        client.menus.side_effect = menus_side_effect
    else:
        client.menus.return_value = menus or []

    return client


def _default_config_data(account_type="student", connection_type="qrcode"):
    data = {
        "account_type": account_type,
        "connection_type": connection_type,
        "url": "https://pronote.example",
    }
    if connection_type == "qrcode":
        data["qr_code_json"] = '{"url":"https://old"}'
        data["qr_code_pin"] = "1234"
    return data


def _make_coordinator(*, data=None, options=None, config_data=None):
    """Create a minimal coordinator for _async_update_data testing."""
    hass = MagicMock()
    hass.config.time_zone = "Europe/Paris"

    entry = MagicMock()
    entry.title = "Test"
    entry.options = options or {"refresh_interval": 15, "alarm_offset": 60}
    entry.data = config_data or _default_config_data()

    with patch.object(PronoteDataUpdateCoordinator, "__init__", lambda self, *a, **kw: None):
        coord = PronoteDataUpdateCoordinator.__new__(PronoteDataUpdateCoordinator)
        coord.hass = hass
        coord.config_entry = entry
        coord.data = data
        coord.logger = MagicMock()
    return coord


def _full_fetched_data(*, child_info=None, lessons_today=None, lessons_next_day=None):
    """Return a complete data dict as would be returned by _fetch_all_sync_data."""
    info = child_info or SimpleNamespace(name="Jean Dupont", class_name="3emeA", establishment="College")
    return {
        "credentials": {
            "pronote_url": "https://pronote.example/eleve.html",
            "username": "jean.dupont",
            "password": "secret",
            "uuid": "uid-123",
            "client_identifier": "cid-456",
        },
        "password": "secret",
        "child_info": info,
        "lessons_today": lessons_today or [],
        "lessons_tomorrow": [],
        "lessons_period": [],
        "lessons_next_day": lessons_next_day,
        "grades": [],
        "averages": [],
        "absences": [],
        "delays": [],
        "evaluations": [],
        "punishments": [],
        "overall_average": "14.5",
        "homework": [],
        "homework_period": [],
        "information_and_surveys": [],
        "ical_url": "https://pronote.example/ical",
        "menus": [],
        "periods": [],
        "current_period": _make_period("Trimestre 2", date(2025, 1, 1)),
        "current_period_key": "trimestre_2",
        "previous_periods": [],
        "active_periods": [_make_period("Trimestre 2", date(2025, 1, 1))],
    }


# ===========================================================================
# Tests for _fetch_all_sync_data
# ===========================================================================


class TestFetchAllSyncDataSuccess:
    """Happy-path test for _fetch_all_sync_data."""

    def test_fetch_all_sync_data_success(self):
        lesson_today = _make_lesson(datetime(2025, 3, 10, 8, 0))
        lesson_tomorrow = _make_lesson(datetime(2025, 3, 11, 9, 0))
        hw = _make_homework(date(2025, 3, 12))
        hw_period = _make_homework(date(2025, 3, 20))
        info = _make_info_survey(datetime(2025, 3, 8, 10, 0))
        menu = _make_menu(date(2025, 3, 10))
        period = _make_period("Trimestre 2", date(2025, 1, 1))
        client = _make_client(
            lessons_today=[lesson_today],
            lessons_tomorrow=[lesson_tomorrow],
            lessons_period=[lesson_today, lesson_tomorrow],
            homework=[hw],
            homework_period=[hw, hw_period],
            info_surveys=[info],
            ical_url="https://example.com/ical",
            menus=[menu],
            periods=[period],
            current_period=period,
        )
        config_data = _default_config_data()

        result = _fetch_all_sync_data(client, config_data, TODAY)

        assert result["credentials"]["pronote_url"] == "https://pronote.example/eleve.html"
        assert result["credentials"]["uuid"] == "uid-123"
        assert result["password"] == "secret"
        assert result["child_info"] is not None
        assert result["lessons_today"] is not None and len(result["lessons_today"]) == 1
        assert result["lessons_tomorrow"] is not None and len(result["lessons_tomorrow"]) == 1
        assert result["lessons_period"] is not None
        assert result["lessons_next_day"] == result["lessons_tomorrow"]
        assert result["grades"] is not None
        assert result["averages"] is not None
        assert result["absences"] is not None
        assert result["delays"] is not None
        assert result["evaluations"] is not None
        assert result["punishments"] is not None
        assert result["overall_average"] is not None
        assert result["homework"] is not None
        assert result["homework_period"] is not None
        assert result["information_and_surveys"] is not None
        assert result["ical_url"] == "https://example.com/ical"
        assert result["menus"] is not None
        assert result["periods"] is not None
        assert result["current_period"] is period
        assert result["current_period_key"] == "trimestre_2"


class TestFetchParentAccount:
    """Parent account should call client.set_child."""

    def test_fetch_parent_account(self):
        client = _make_client()
        client._selected_child = SimpleNamespace(name="Enfant", class_name="5B", establishment="College")
        config_data = _default_config_data(account_type="parent")
        config_data["child"] = "Enfant"

        result = _fetch_all_sync_data(client, config_data, TODAY)

        client.set_child.assert_called_once_with("Enfant")
        assert result["child_info"].name == "Enfant"


class TestFetchLessonsErrors:
    """Error handling for lesson fetching."""

    def test_fetch_lessons_today_error(self):
        def lessons_fn(d, end=None):
            if end is not None:
                return []
            if d == TODAY:
                raise RuntimeError("Network error")
            return []

        client = _make_client(lessons_side_effects=lessons_fn)
        result = _fetch_all_sync_data(client, _default_config_data(), TODAY)

        assert result["lessons_today"] is None

    def test_fetch_lessons_tomorrow_error(self):
        def lessons_fn(d, end=None):
            if end is not None:
                return []
            if d == TODAY:
                return []
            if d == TODAY + timedelta(days=1):
                raise RuntimeError("Network error")
            return []

        client = _make_client(lessons_side_effects=lessons_fn)
        result = _fetch_all_sync_data(client, _default_config_data(), TODAY)

        assert result["lessons_tomorrow"] is None

    def test_fetch_lessons_period_retry(self):
        """First call with delta=LESSON_MAX_DAYS fails, second with delta-1 succeeds."""
        expected_lesson = _make_lesson(datetime(2025, 3, 10, 8, 0))
        call_count = 0

        def lessons_fn(d, end=None):
            nonlocal call_count
            if end is not None:
                call_count += 1
                if call_count == 1:
                    raise RuntimeError("Too far")
                return [expected_lesson]
            return []

        client = _make_client(lessons_side_effects=lessons_fn)
        result = _fetch_all_sync_data(client, _default_config_data(), TODAY)

        assert result["lessons_period"] is not None
        assert len(result["lessons_period"]) == 1
        assert result["lessons_period"][0] is expected_lesson

    def test_fetch_lessons_period_all_fail(self):
        """All retry attempts fail."""

        def lessons_fn(d, end=None):
            if end is not None:
                raise RuntimeError("Always fail")
            return []

        client = _make_client(lessons_side_effects=lessons_fn)
        result = _fetch_all_sync_data(client, _default_config_data(), TODAY)

        assert result["lessons_period"] is None


class TestFetchLessonsNextDay:
    """Next day lesson search logic."""

    def test_fetch_lessons_next_day_from_tomorrow(self):
        """When tomorrow has lessons, lessons_next_day = lessons_tomorrow."""
        lesson = _make_lesson(datetime(2025, 3, 11, 8, 0))
        client = _make_client(lessons_tomorrow=[lesson])
        result = _fetch_all_sync_data(client, _default_config_data(), TODAY)

        assert result["lessons_next_day"] == result["lessons_tomorrow"]

    def test_fetch_lessons_next_day_search(self):
        """Tomorrow empty, today+2 empty, today+3 has lessons."""
        lesson_day3 = _make_lesson(datetime(2025, 3, 13, 8, 0))

        def lessons_fn(d, end=None):
            if end is not None:
                return []
            if d == TODAY + timedelta(days=3):
                return [lesson_day3]
            return []

        client = _make_client(lessons_side_effects=lessons_fn)
        result = _fetch_all_sync_data(client, _default_config_data(), TODAY)

        assert result["lessons_next_day"] is not None
        assert len(result["lessons_next_day"]) == 1
        assert result["lessons_next_day"][0] is lesson_day3

    def test_fetch_lessons_next_day_not_found(self):
        """All search days return empty."""

        def lessons_fn(d, end=None):
            return []

        client = _make_client(lessons_side_effects=lessons_fn)
        result = _fetch_all_sync_data(client, _default_config_data(), TODAY)

        assert result["lessons_next_day"] is None


class TestFetchHomeworkErrors:
    """Error handling for homework fetching."""

    def test_fetch_homework_error(self):
        client = _make_client(homework_side_effect=RuntimeError("homework fail"))
        result = _fetch_all_sync_data(client, _default_config_data(), TODAY)

        assert result["homework"] is None
        assert result["homework_period"] is None


class TestFetchInformationAndSurveysError:
    """Error handling for information_and_surveys."""

    def test_fetch_information_and_surveys_error(self):
        client = _make_client(info_surveys_side_effect=RuntimeError("info fail"))
        result = _fetch_all_sync_data(client, _default_config_data(), TODAY)

        assert result["information_and_surveys"] is None


class TestFetchIcalError:
    """Error handling for iCal export."""

    def test_fetch_ical_error(self):
        client = _make_client(ical_side_effect=RuntimeError("ical fail"))
        result = _fetch_all_sync_data(client, _default_config_data(), TODAY)

        assert result["ical_url"] is None


class TestFetchMenusError:
    """Error handling for menus."""

    def test_fetch_menus_error(self):
        client = _make_client(menus_side_effect=RuntimeError("menus fail"))
        result = _fetch_all_sync_data(client, _default_config_data(), TODAY)

        assert result["menus"] is None


class TestFetchPeriodsError:
    """Error handling for periods."""

    def test_fetch_periods_error(self):
        client = _make_client(periods_side_effect=RuntimeError("periods fail"))
        result = _fetch_all_sync_data(client, _default_config_data(), TODAY)

        assert result["periods"] is None


class TestFetchPreviousPeriods:
    """Previous period data fetching."""

    def test_fetch_previous_periods(self):
        """Trimestre 2 is current => Trimestre 1 data should be fetched."""
        t1 = _make_period("Trimestre 1", date(2024, 9, 1), date(2024, 12, 20))
        t2 = _make_period("Trimestre 2", date(2025, 1, 1), date(2025, 3, 31))
        t3 = _make_period("Trimestre 3", date(2025, 4, 1), date(2025, 6, 30))

        client = _make_client(
            current_period=t2,
            periods=[t1, t2, t3],
        )
        result = _fetch_all_sync_data(client, _default_config_data(), TODAY)

        assert len(result["previous_periods"]) == 1
        assert result["previous_periods"][0] is t1
        assert "grades_trimestre_1" in result
        assert "averages_trimestre_1" in result
        assert "absences_trimestre_1" in result
        assert "delays_trimestre_1" in result
        assert "evaluations_trimestre_1" in result
        assert "punishments_trimestre_1" in result
        assert "overall_average_trimestre_1" in result

        # active_periods should include both T1 and T2
        assert len(result["active_periods"]) == 2

    def test_fetch_no_previous_periods_for_unsupported_type(self):
        """Period name starting with unsupported type => no previous period data."""
        p = _make_period("Annee 1", date(2025, 1, 1))
        client = _make_client(current_period=p, periods=[p])
        result = _fetch_all_sync_data(client, _default_config_data(), TODAY)

        assert result["previous_periods"] == []


# ===========================================================================
# Tests for _async_update_data
# ===========================================================================


class TestAsyncUpdateDataSuccess:
    """Happy-path test for _async_update_data."""

    @pytest.mark.asyncio
    async def test_async_update_data_success(self):
        coord = _make_coordinator()
        mock_client = MagicMock()
        fetched = _full_fetched_data()

        async def fake_executor(fn, *args):
            return fn(*args)

        coord.hass.async_add_executor_job = MagicMock(side_effect=fake_executor)

        with (
            patch(
                "custom_components.pronote.coordinator.get_pronote_client",
                return_value=mock_client,
            ),
            patch(
                "custom_components.pronote.coordinator._fetch_all_sync_data",
                return_value=fetched,
            ),
        ):
            result = await coord._async_update_data()

        assert result["account_type"] == "student"
        assert result["sensor_prefix"] == "jean_dupont"
        assert result["child_info"].name == "Jean Dupont"
        # Verify credentials were saved for QR code connection
        coord.hass.config_entries.async_update_entry.assert_called_once()
        updated_data = coord.hass.config_entries.async_update_entry.call_args[1]["data"]
        assert updated_data["qr_code_url"] == "https://pronote.example/eleve.html"
        assert updated_data["qr_code_username"] == "jean.dupont"
        assert updated_data["qr_code_password"] == "secret"
        assert updated_data["qr_code_uuid"] == "uid-123"
        assert updated_data["client_identifier"] == "cid-456"
        # One-time QR code data should be removed
        assert "qr_code_json" not in updated_data
        assert "qr_code_pin" not in updated_data


class TestAsyncUpdateDataUsernamePassword:
    """Credentials are NOT saved for username_password connections."""

    @pytest.mark.asyncio
    async def test_no_qr_code_credential_saving(self):
        coord = _make_coordinator(config_data=_default_config_data(connection_type="username_password"))
        mock_client = MagicMock()
        fetched = _full_fetched_data()

        async def fake_executor(fn, *args):
            return fn(*args)

        coord.hass.async_add_executor_job = MagicMock(side_effect=fake_executor)

        with (
            patch(
                "custom_components.pronote.coordinator.get_pronote_client",
                return_value=mock_client,
            ),
            patch(
                "custom_components.pronote.coordinator._fetch_all_sync_data",
                return_value=fetched,
            ),
        ):
            result = await coord._async_update_data()

        assert result["account_type"] == "student"
        # No QR code credentials should be saved
        coord.hass.config_entries.async_update_entry.assert_called_once()
        updated_data = coord.hass.config_entries.async_update_entry.call_args[1]["data"]
        assert "qr_code_url" not in updated_data
        assert "qr_code_password" not in updated_data


class TestAsyncUpdateDataClientNone:
    """get_pronote_client returns None."""

    @pytest.mark.asyncio
    async def test_async_update_data_client_none(self):
        coord = _make_coordinator()

        async def fake_executor(fn, *args):
            return fn(*args)

        coord.hass.async_add_executor_job = MagicMock(side_effect=fake_executor)

        with patch(
            "custom_components.pronote.coordinator.get_pronote_client",
            return_value=None,
        ):
            with pytest.raises(ConfigEntryAuthFailed):
                await coord._async_update_data()


class TestAsyncUpdateDataClientException:
    """get_pronote_client raises an exception."""

    @pytest.mark.asyncio
    async def test_async_update_data_client_exception(self):
        coord = _make_coordinator()

        async def fake_executor(fn, *args):
            return fn(*args)

        coord.hass.async_add_executor_job = MagicMock(side_effect=fake_executor)

        with patch(
            "custom_components.pronote.coordinator.get_pronote_client",
            side_effect=RuntimeError("Auth failed"),
        ):
            with pytest.raises(UpdateFailed, match="Error communicating with Pronote"):
                await coord._async_update_data()


class TestAsyncUpdateDataAuthException:
    """get_pronote_client raises a pronotepy auth exception -> ConfigEntryAuthFailed."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "exc_class",
        [
            pytest.param("CryptoError", id="CryptoError"),
            pytest.param("QRCodeDecryptError", id="QRCodeDecryptError"),
            pytest.param("ENTLoginError", id="ENTLoginError"),
        ],
    )
    async def test_auth_exceptions_raise_config_entry_auth_failed(self, exc_class):
        import pronotepy

        coord = _make_coordinator()

        async def fake_executor(fn, *args):
            return fn(*args)

        coord.hass.async_add_executor_job = MagicMock(side_effect=fake_executor)

        exc = getattr(pronotepy, exc_class)("Token expired")

        with patch(
            "custom_components.pronote.coordinator.get_pronote_client",
            side_effect=exc,
        ):
            with pytest.raises(ConfigEntryAuthFailed, match="Authentication failed"):
                await coord._async_update_data()


class TestAsyncUpdateDataFetchException:
    """_fetch_all_sync_data raises an exception."""

    @pytest.mark.asyncio
    async def test_async_update_data_fetch_exception(self):
        coord = _make_coordinator()
        mock_client = MagicMock()

        call_count = 0

        async def fake_executor(fn, *args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call: get_pronote_client
                return mock_client
            # Second call: _fetch_all_sync_data
            raise RuntimeError("Fetch error")

        coord.hass.async_add_executor_job = MagicMock(side_effect=fake_executor)

        with patch(
            "custom_components.pronote.coordinator.get_pronote_client",
            return_value=mock_client,
        ):
            with pytest.raises(UpdateFailed, match="Error fetching data from Pronote"):
                await coord._async_update_data()


class TestAsyncUpdateDataChildInfoNone:
    """Fetched data has child_info=None."""

    @pytest.mark.asyncio
    async def test_async_update_data_child_info_none(self):
        coord = _make_coordinator()
        mock_client = MagicMock()
        fetched = _full_fetched_data()
        fetched["child_info"] = None

        async def fake_executor(fn, *args):
            return fn(*args)

        coord.hass.async_add_executor_job = MagicMock(side_effect=fake_executor)

        with (
            patch(
                "custom_components.pronote.coordinator.get_pronote_client",
                return_value=mock_client,
            ),
            patch(
                "custom_components.pronote.coordinator._fetch_all_sync_data",
                return_value=fetched,
            ),
        ):
            with pytest.raises(UpdateFailed, match="No child info"):
                await coord._async_update_data()


class TestAsyncUpdateDataAlarm:
    """Next alarm computation."""

    @pytest.mark.asyncio
    async def test_async_update_data_computes_next_alarm(self):
        coord = _make_coordinator(options={"refresh_interval": 15, "alarm_offset": 60})
        mock_client = MagicMock()

        # Lesson starting at 09:00 today - set a future time so the alarm is relevant
        lesson_start = datetime(2025, 3, 10, 9, 0)
        lesson = _make_lesson(lesson_start)
        fetched = _full_fetched_data(lessons_today=[lesson])

        async def fake_executor(fn, *args):
            return fn(*args)

        coord.hass.async_add_executor_job = MagicMock(side_effect=fake_executor)

        with (
            patch(
                "custom_components.pronote.coordinator.get_pronote_client",
                return_value=mock_client,
            ),
            patch(
                "custom_components.pronote.coordinator._fetch_all_sync_data",
                return_value=fetched,
            ),
            patch(
                "custom_components.pronote.coordinator.datetime",
            ) as mock_dt,
            patch(
                "custom_components.pronote.coordinator.get_day_start_at",
            ) as mock_get_start,
        ):
            # First call for lessons_today, second for lessons_next_day
            mock_get_start.side_effect = [lesson_start, None]
            # Make "now" earlier than the alarm so today's alarm is valid
            mock_dt.now.return_value = datetime(2025, 3, 10, 7, 0)
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            result = await coord._async_update_data()

        expected_alarm = lesson_start - timedelta(minutes=60)
        assert result["next_alarm"] is not None
        assert result["next_alarm"].replace(tzinfo=None) == expected_alarm

    @pytest.mark.asyncio
    async def test_async_update_data_no_alarm(self):
        coord = _make_coordinator()
        mock_client = MagicMock()
        fetched = _full_fetched_data(lessons_today=[], lessons_next_day=None)

        async def fake_executor(fn, *args):
            return fn(*args)

        coord.hass.async_add_executor_job = MagicMock(side_effect=fake_executor)

        with (
            patch(
                "custom_components.pronote.coordinator.get_pronote_client",
                return_value=mock_client,
            ),
            patch(
                "custom_components.pronote.coordinator._fetch_all_sync_data",
                return_value=fetched,
            ),
        ):
            result = await coord._async_update_data()

        assert result["next_alarm"] is None


class TestAsyncUpdateDataFiresEvents:
    """Event firing via compare_data."""

    @pytest.mark.asyncio
    async def test_async_update_data_fires_events(self):
        """With previous data and new grades, compare_data is called."""
        previous = {
            "grades": [],
            "absences": [],
            "delays": [],
            "evaluations": [],
        }
        coord = _make_coordinator(data=previous)
        mock_client = MagicMock()
        fetched = _full_fetched_data()

        async def fake_executor(fn, *args):
            return fn(*args)

        coord.hass.async_add_executor_job = MagicMock(side_effect=fake_executor)

        with (
            patch(
                "custom_components.pronote.coordinator.get_pronote_client",
                return_value=mock_client,
            ),
            patch(
                "custom_components.pronote.coordinator._fetch_all_sync_data",
                return_value=fetched,
            ),
            patch.object(coord, "compare_data") as mock_compare,
        ):
            await coord._async_update_data()

        # compare_data is called 4 times: grades, absences, delays, evaluations
        assert mock_compare.call_count == 4
        call_event_types = [call.args[3] for call in mock_compare.call_args_list]
        assert "new_grade" in call_event_types
        assert "new_absence" in call_event_types
        assert "new_delay" in call_event_types
        assert "new_evaluation" in call_event_types


class TestFetchLessonsNextDayException:
    def test_fetch_lessons_next_day_exception(self):
        """Exception during next_day search sets lessons_next_day to None (line 165-167)."""
        call_count = 0

        def lessons_fn(d, end=None):
            nonlocal call_count
            call_count += 1
            if end is not None:
                return [_make_lesson(d)]
            if d == TODAY:
                return [_make_lesson(d)]
            if d == TODAY + timedelta(days=1):
                return []  # no lessons tomorrow
            # next_day search: raise on first call
            raise RuntimeError("connection error")

        client = _make_client(lessons_side_effects=lessons_fn)
        data = _fetch_all_sync_data(client, _default_config_data(), TODAY)
        assert data["lessons_next_day"] is None


class TestFetchCurrentPeriodKeyError:
    def test_fetch_current_period_slugify_error(self):
        """When current_period.name raises, both current_period and key are None (line 231-234)."""
        bad_period = MagicMock()
        type(bad_period).name = property(lambda self: (_ for _ in ()).throw(RuntimeError("no name")))
        bad_period.grades = []
        bad_period.absences = []
        bad_period.delays = []
        bad_period.averages = []
        bad_period.punishments = []
        bad_period.evaluations = []
        bad_period.overall_average = None

        client = _make_client(current_period=bad_period)
        data = _fetch_all_sync_data(client, _default_config_data(), TODAY)
        assert data["current_period"] is None
        assert data["current_period_key"] is None


class TestAsyncUpdateDataNextDayAlarm:
    async def test_async_update_data_next_day_alarm(self):
        """When today's alarm is past, use next_day alarm (line 331)."""
        coord = _make_coordinator()

        fetched = _full_fetched_data()
        # today's lesson is in the past
        fetched["lessons_today"] = [_make_lesson(datetime(2025, 3, 10, 5, 0))]
        # next_day lesson is tomorrow at 09:00
        fetched["lessons_next_day"] = [_make_lesson(datetime(2025, 3, 11, 9, 0))]

        mock_client = MagicMock()

        async def fake_executor(fn, *args):
            return fn(*args)

        coord.hass.async_add_executor_job = MagicMock(side_effect=fake_executor)

        with (
            patch(
                "custom_components.pronote.coordinator.get_pronote_client",
                return_value=mock_client,
            ),
            patch(
                "custom_components.pronote.coordinator._fetch_all_sync_data",
                return_value=fetched,
            ),
        ):
            result = await coord._async_update_data()

        # next_alarm should be from next_day (09:00 - 60min = 08:00 on March 11)
        assert result["next_alarm"] is not None
        assert result["next_alarm"].hour == 8
        assert result["next_alarm"].day == 11
