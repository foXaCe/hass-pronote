"""Tests for the Pronote helper functions."""

from datetime import datetime
from unittest.mock import MagicMock, patch

from custom_components.pronote.pronote_helper import (
    get_client_from_qr_code,
    get_client_from_username_password,
    get_day_start_at,
    get_pronote_client,
)


class TestGetDayStartAt:
    def test_none_lessons(self):
        assert get_day_start_at(None) is None

    def test_empty_lessons(self):
        assert get_day_start_at([]) is None

    def test_first_non_canceled(self, mock_lesson):
        lessons = [
            mock_lesson(start=datetime(2025, 1, 15, 8, 0), canceled=False),
            mock_lesson(start=datetime(2025, 1, 15, 9, 0), canceled=False),
        ]
        result = get_day_start_at(lessons)
        assert result == datetime(2025, 1, 15, 8, 0)

    def test_first_canceled_skipped(self, mock_lesson):
        lessons = [
            mock_lesson(start=datetime(2025, 1, 15, 8, 0), canceled=True),
            mock_lesson(start=datetime(2025, 1, 15, 9, 0), canceled=False),
        ]
        result = get_day_start_at(lessons)
        assert result == datetime(2025, 1, 15, 9, 0)

    def test_all_canceled(self, mock_lesson):
        lessons = [
            mock_lesson(start=datetime(2025, 1, 15, 8, 0), canceled=True),
            mock_lesson(start=datetime(2025, 1, 15, 9, 0), canceled=True),
        ]
        assert get_day_start_at(lessons) is None


class TestGetPronoteClient:
    @patch("custom_components.pronote.pronote_helper.get_client_from_username_password")
    def test_username_password_connection(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        data = {"connection_type": "username_password"}
        result = get_pronote_client(data)

        mock_get_client.assert_called_once_with(data)
        mock_client.session_check.assert_called_once()
        assert result == mock_client

    @patch("custom_components.pronote.pronote_helper.get_client_from_qr_code")
    def test_qrcode_connection(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        data = {"connection_type": "qrcode"}
        result = get_pronote_client(data)

        mock_get_client.assert_called_once_with(data)
        assert result == mock_client

    @patch("custom_components.pronote.pronote_helper.get_client_from_username_password")
    def test_returns_none_on_failed_client(self, mock_get_client):
        mock_get_client.return_value = None

        data = {"connection_type": "username_password"}
        result = get_pronote_client(data)

        assert result is None

    @patch("custom_components.pronote.pronote_helper.get_client_from_username_password")
    def test_session_check_failure_still_returns_client(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.session_check.side_effect = Exception("Session expired")
        mock_get_client.return_value = mock_client

        data = {"connection_type": "username_password"}
        result = get_pronote_client(data)

        assert result == mock_client


class TestGetClientFromUsernamePassword:
    @patch("custom_components.pronote.pronote_helper.pronotepy")
    def test_student_url_construction(self, mock_pronotepy):
        mock_client = MagicMock()
        mock_client.info.name = "Jean Dupont"
        mock_pronotepy.Client.return_value = mock_client
        mock_pronotepy.ent = MagicMock(spec=[])

        data = {
            "url": "https://pronote.example.com/",
            "account_type": "eleve",
            "username": "jean",
            "password": "pass",
        }
        get_client_from_username_password(data)

        call_kwargs = mock_pronotepy.Client.call_args
        assert "eleve.html" in call_kwargs.kwargs["pronote_url"]

    @patch("custom_components.pronote.pronote_helper.pronotepy")
    def test_parent_url_construction(self, mock_pronotepy):
        mock_client = MagicMock()
        mock_client.info.name = "Parent Dupont"
        mock_pronotepy.ParentClient.return_value = mock_client
        mock_pronotepy.ent = MagicMock(spec=[])

        data = {
            "url": "https://pronote.example.com/",
            "account_type": "parent",
            "username": "parent",
            "password": "pass",
        }
        get_client_from_username_password(data)

        call_kwargs = mock_pronotepy.ParentClient.call_args
        assert "parent.html" in call_kwargs.kwargs["pronote_url"]

    @patch("custom_components.pronote.pronote_helper.pronotepy")
    def test_url_without_trailing_slash(self, mock_pronotepy):
        mock_client = MagicMock()
        mock_client.info.name = "Jean"
        mock_pronotepy.Client.return_value = mock_client
        mock_pronotepy.ent = MagicMock(spec=[])

        data = {
            "url": "https://pronote.example.com",
            "account_type": "eleve",
            "username": "jean",
            "password": "pass",
        }
        get_client_from_username_password(data)

        call_kwargs = mock_pronotepy.Client.call_args
        assert call_kwargs.kwargs["pronote_url"].startswith("https://pronote.example.com/")

    @patch("custom_components.pronote.pronote_helper.pronotepy")
    def test_url_with_html_suffix(self, mock_pronotepy):
        mock_client = MagicMock()
        mock_client.info.name = "Jean"
        mock_pronotepy.Client.return_value = mock_client
        mock_pronotepy.ent = MagicMock(spec=[])

        data = {
            "url": "https://pronote.example.com/old.html",
            "account_type": "eleve",
            "username": "jean",
            "password": "pass",
        }
        get_client_from_username_password(data)

        call_kwargs = mock_pronotepy.Client.call_args
        assert "old.html" not in call_kwargs.kwargs["pronote_url"]
        assert "eleve.html" in call_kwargs.kwargs["pronote_url"]

    @patch("custom_components.pronote.pronote_helper.pronotepy")
    def test_no_ent_adds_login_param(self, mock_pronotepy):
        mock_client = MagicMock()
        mock_client.info.name = "Jean"
        mock_pronotepy.Client.return_value = mock_client
        mock_pronotepy.ent = MagicMock(spec=[])

        data = {
            "url": "https://pronote.example.com/",
            "account_type": "eleve",
            "username": "jean",
            "password": "pass",
        }
        get_client_from_username_password(data)

        call_kwargs = mock_pronotepy.Client.call_args
        assert "?login=true" in call_kwargs.kwargs["pronote_url"]

    @patch("custom_components.pronote.pronote_helper.pronotepy")
    def test_exception_returns_none(self, mock_pronotepy):
        mock_pronotepy.Client.side_effect = Exception("Connection failed")
        mock_pronotepy.ent = MagicMock(spec=[])

        data = {
            "url": "https://pronote.example.com/",
            "account_type": "eleve",
            "username": "jean",
            "password": "pass",
        }
        result = get_client_from_username_password(data)
        assert result is None


class TestGetClientFromQrCode:
    @patch("custom_components.pronote.pronote_helper.pronotepy")
    def test_token_login_with_existing_credentials(self, mock_pronotepy):
        mock_client = MagicMock()
        mock_pronotepy.Client.token_login.return_value = mock_client

        data = {
            "connection_type": "qrcode",
            "account_type": "eleve",
            "qr_code_url": "https://pronote.example.com/eleve.html",
            "qr_code_username": "jean",
            "qr_code_password": "token123",
            "qr_code_uuid": "uuid-123",
        }
        result = get_client_from_qr_code(data)

        mock_pronotepy.Client.token_login.assert_called_once()
        assert result == mock_client

    @patch("custom_components.pronote.pronote_helper.pronotepy")
    def test_qrcode_first_login(self, mock_pronotepy):
        mock_client = MagicMock()
        mock_client.pronote_url = "https://pronote.example.com"
        mock_client.username = "jean"
        mock_client.password = "token"
        mock_client.uuid = "uuid"
        mock_client.account_pin = None
        mock_client.device_name = None
        mock_client.client_identifier = None
        mock_pronotepy.Client.qrcode_login.return_value = mock_client
        mock_pronotepy.Client.token_login.return_value = mock_client

        data = {
            "account_type": "eleve",
            "qr_code_json": '{"url": "test"}',
            "qr_code_pin": "1234",
            "qr_code_uuid": "uuid-123",
        }
        get_client_from_qr_code(data)

        mock_pronotepy.Client.qrcode_login.assert_called_once()

    @patch("custom_components.pronote.pronote_helper.pronotepy")
    def test_parent_token_login(self, mock_pronotepy):
        mock_client = MagicMock()
        mock_pronotepy.ParentClient.token_login.return_value = mock_client

        data = {
            "connection_type": "qrcode",
            "account_type": "parent",
            "qr_code_url": "https://pronote.example.com/parent.html",
            "qr_code_username": "parent",
            "qr_code_password": "token123",
            "qr_code_uuid": "uuid-123",
        }
        get_client_from_qr_code(data)

        mock_pronotepy.ParentClient.token_login.assert_called_once()
