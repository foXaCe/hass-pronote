"""Tests for the Pronote config flow with new API client."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pronote.api import AuthenticationError, PronoteAPIClient
from custom_components.pronote.config_flow import (
    DOMAIN,
)

UP_ELEVE_INPUT = {
    "account_type": "eleve",
    "url": "https://pronote.example.com/pronote/",
    "username": "jean.dupont",
    "password": "secret123",
}

QR_ELEVE_INPUT = {
    "account_type": "eleve",
    "qr_code_json": '{"url":"https://pronote.example.com"}',
    "qr_code_pin": "1234",
}


def _make_eleve_client(name="Jean Dupont"):
    """Return a mock pronote client for an 'eleve' account."""
    client = MagicMock()
    client.info = SimpleNamespace(name=name)
    client.children = []
    return client


def _make_qr_client(name="Jean Dupont", is_parent=False, children_names=None):
    """Return a mock pronote client for a QR-code login."""
    client = MagicMock()
    client.info = SimpleNamespace(name=name)
    client.pronote_url = "https://pronote.example.com/pronote/eleve.html"
    client.username = "qr_user"
    client.password = "qr_pass"
    client.uuid = "qr_uuid_1234"
    if is_parent:
        if children_names is None:
            children_names = ["Jean Dupont", "Marie Dupont"]
        client.children = [SimpleNamespace(name=n) for n in children_names]
    else:
        client.children = []
    return client


def _make_credentials():
    """Return mock credentials for QR login."""
    from custom_components.pronote.api.models import Credentials

    return Credentials(
        pronote_url="https://pronote.example.com/pronote/eleve.html",
        username="qr_user",
        password="qr_pass",
        uuid="qr_uuid_1234",
        client_identifier=None,
    )


async def test_step_user_shows_menu(hass: HomeAssistant) -> None:
    """The initial user step should present a menu."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.MENU
    assert "username_password_login" in result["menu_options"]
    assert "qr_code_login" in result["menu_options"]


async def test_up_login_eleve_success(hass: HomeAssistant) -> None:
    """Successful eleve login via UP goes to nickname step."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "username_password_login"},
    )

    mock_client = _make_eleve_client("Jean Dupont")
    mock_creds = _make_credentials()

    with patch("custom_components.pronote.api.auth.PronoteAuth.authenticate", return_value=(mock_client, mock_creds)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            UP_ELEVE_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "nickname"


async def test_up_login_full_flow(hass: HomeAssistant) -> None:
    """Full UP eleve flow."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "username_password_login"},
    )

    mock_client = _make_eleve_client("Jean Dupont")
    mock_creds = _make_credentials()

    with patch("custom_components.pronote.api.auth.PronoteAuth.authenticate", return_value=(mock_client, mock_creds)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            UP_ELEVE_INPUT,
        )

    assert result["step_id"] == "nickname"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"nickname": "Jean"},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Jean Dupont"
    assert result["data"]["connection_type"] == "username_password"


async def test_up_login_invalid_auth(hass: HomeAssistant) -> None:
    """Invalid auth shows error."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "username_password_login"},
    )

    with patch.object(PronoteAPIClient, "authenticate", side_effect=AuthenticationError("Invalid credentials")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            UP_ELEVE_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_auth"


async def test_qr_login_eleve_success(hass: HomeAssistant) -> None:
    """Successful eleve QR login goes to nickname step."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "qr_code_login"},
    )

    mock_client = _make_qr_client("Jean Dupont")
    mock_creds = _make_credentials()

    with patch("custom_components.pronote.api.auth.PronoteAuth.authenticate", return_value=(mock_client, mock_creds)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            QR_ELEVE_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "nickname"


async def test_qr_login_full_flow(hass: HomeAssistant) -> None:
    """Full QR eleve flow."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "qr_code_login"},
    )

    mock_client = _make_qr_client("Jean Dupont")
    mock_creds = _make_credentials()

    with patch("custom_components.pronote.api.auth.PronoteAuth.authenticate", return_value=(mock_client, mock_creds)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            QR_ELEVE_INPUT,
        )

    assert result["step_id"] == "nickname"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"nickname": "Jean"},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Jean Dupont"
    assert result["data"]["connection_type"] == "qrcode"
    # Verify QR credentials were saved
    assert result["data"]["qr_code_url"] == "https://pronote.example.com/pronote/eleve.html"
    assert result["data"]["qr_code_username"] == "qr_user"
    assert result["data"]["qr_code_password"] == "qr_pass"
    assert result["data"]["qr_code_uuid"] == "qr_uuid_1234"


async def test_qr_login_invalid_auth(hass: HomeAssistant) -> None:
    """QR login with invalid auth shows error."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "qr_code_login"},
    )

    with patch.object(PronoteAPIClient, "authenticate", side_effect=AuthenticationError("Invalid QR code")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            QR_ELEVE_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_auth"


async def test_reauth_up_success(hass: HomeAssistant) -> None:
    """Successful UP reauth updates the entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "connection_type": "username_password",
            "account_type": "eleve",
            "url": "https://pronote.example.com/pronote/",
            "username": "jean.dupont",
            "password": "old_password",
        },
        unique_id="Jean Dupont",
        version=2,
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)

    mock_client = _make_eleve_client("Jean Dupont")
    mock_creds = _make_credentials()

    with patch("custom_components.pronote.api.auth.PronoteAuth.authenticate", return_value=(mock_client, mock_creds)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"password": "new_password"},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == "new_password"


async def test_reauth_up_invalid_auth(hass: HomeAssistant) -> None:
    """Failed UP reauth shows error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "connection_type": "username_password",
            "account_type": "eleve",
            "url": "https://pronote.example.com/pronote/",
            "username": "jean.dupont",
            "password": "old_password",
        },
        unique_id="Jean Dupont",
        version=2,
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)

    with patch.object(PronoteAPIClient, "authenticate", side_effect=AuthenticationError("Invalid credentials")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"password": "wrong_password"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"]["base"] == "invalid_auth"


async def test_reauth_qr_success(hass: HomeAssistant) -> None:
    """Successful QR reauth updates credentials."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "connection_type": "qrcode",
            "account_type": "eleve",
            "qr_code_json": '{"old":"data"}',
            "qr_code_pin": "0000",
            "qr_code_url": "https://pronote.example.com/pronote/eleve.html",
            "qr_code_username": "old_user",
            "qr_code_password": "old_pass",
            "qr_code_uuid": "old_uuid",
        },
        unique_id="Jean Dupont",
        version=2,
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)

    mock_client = _make_qr_client("Jean Dupont")
    mock_creds = _make_credentials()

    with patch("custom_components.pronote.api.auth.PronoteAuth.authenticate", return_value=(mock_client, mock_creds)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "qr_code_json": '{"new":"data"}',
                "qr_code_pin": "9999",
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["qr_code_password"] == "qr_pass"


# Additional tests for coverage

UP_PARENT_INPUT = {
    "account_type": "parent",
    "url": "https://pronote.example.com/pronote/",
    "username": "parent.dupont",
    "password": "secret123",
}

QR_PARENT_INPUT = {
    "account_type": "parent",
    "qr_code_json": '{"url":"https://pronote.example.com"}',
    "qr_code_pin": "1234",
}


async def test_up_login_parent_success(hass: HomeAssistant) -> None:
    """Successful parent login via UP goes to parent step then nickname."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "username_password_login"},
    )

    mock_client = _make_eleve_client("Parent Account")
    mock_client.children = [SimpleNamespace(name="Jean Dupont"), SimpleNamespace(name="Marie Dupont")]
    mock_creds = _make_credentials()

    with patch("custom_components.pronote.api.auth.PronoteAuth.authenticate", return_value=(mock_client, mock_creds)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            UP_PARENT_INPUT,
        )

    # Should go to parent step to select child
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "parent"

    # Select child
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"child": "Jean Dupont"},
    )

    # Should go to nickname step
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "nickname"

    # Set nickname and complete
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"nickname": "Jean"},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert "Jean Dupont (via compte parent)" in result["title"]


async def test_qr_login_parent_success(hass: HomeAssistant) -> None:
    """Successful parent login via QR goes to parent step then nickname."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "qr_code_login"},
    )

    mock_client = _make_qr_client("Parent Account", is_parent=True)
    mock_creds = _make_credentials()

    with patch("custom_components.pronote.api.auth.PronoteAuth.authenticate", return_value=(mock_client, mock_creds)):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            QR_PARENT_INPUT,
        )

    # Should go to parent step to select child
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "parent"

    # Select child
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"child": "Jean Dupont"},
    )

    # Should go to nickname step
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "nickname"


async def test_up_login_invalid_auth_exception(hass: HomeAssistant) -> None:
    """InvalidAuth exception shows error."""
    from custom_components.pronote.config_flow import InvalidAuth

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "username_password_login"},
    )

    with patch.object(PronoteAPIClient, "authenticate", side_effect=InvalidAuth()):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            UP_ELEVE_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_auth"


async def test_up_login_generic_exception(hass: HomeAssistant) -> None:
    """Generic exception shows error."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "username_password_login"},
    )

    with patch.object(PronoteAPIClient, "authenticate", side_effect=RuntimeError("Unexpected")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            UP_ELEVE_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_auth"


async def test_qr_login_invalid_auth_exception(hass: HomeAssistant) -> None:
    """QR login with InvalidAuth exception shows error."""
    from custom_components.pronote.config_flow import InvalidAuth

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "qr_code_login"},
    )

    with patch.object(PronoteAPIClient, "authenticate", side_effect=InvalidAuth()):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            QR_ELEVE_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_auth"


async def test_qr_login_generic_exception(hass: HomeAssistant) -> None:
    """QR login with generic exception shows error."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "qr_code_login"},
    )

    with patch.object(PronoteAPIClient, "authenticate", side_effect=RuntimeError("Unexpected")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            QR_ELEVE_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_auth"


async def test_reauth_qr_invalid_auth(hass: HomeAssistant) -> None:
    """Failed QR reauth shows error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "connection_type": "qrcode",
            "account_type": "eleve",
            "qr_code_json": '{"old":"data"}',
            "qr_code_pin": "0000",
        },
        unique_id="Jean Dupont",
        version=2,
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)

    with patch.object(PronoteAPIClient, "authenticate", side_effect=AuthenticationError("Invalid QR")):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "qr_code_json": '{"new":"data"}',
                "qr_code_pin": "9999",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"]["base"] == "invalid_auth"


async def test_options_flow(hass: HomeAssistant) -> None:
    """Test options flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "connection_type": "username_password",
            "account_type": "eleve",
            "url": "https://pronote.example.com/pronote/",
            "username": "jean.dupont",
            "password": "secret123",
        },
        options={"nickname": "Jean", "refresh_interval": 15},
        unique_id="Jean Dupont",
        version=2,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "nickname": "Jean Updated",
            "refresh_interval": 30,
            "lunch_break_time": "12:00",
            "alarm_offset": 45,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["nickname"] == "Jean Updated"
    assert result["data"]["refresh_interval"] == 30
    assert result["data"]["lunch_break_time"] == "12:00"
    assert result["data"]["alarm_offset"] == 45
