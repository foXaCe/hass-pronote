"""Tests for the Pronote config flow with new API client."""

import contextlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pronote import config_flow as config_flow_module
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


QR_PAYLOAD = json.dumps({"url": "https://pronote.example.com", "login": "abc", "jeton": "def"})
# The file selector validates its value as a UUID (a file_upload id).
UPLOAD_ID = "6f1d7b2e-3a4c-4f5d-8e9a-0b1c2d3e4f5a"


@pytest.fixture(autouse=True)
def reset_qr_decoder_cache():
    """The decoder probe is cached module-wide; keep tests independent."""
    config_flow_module._qr_decoder = config_flow_module._UNSET
    yield
    config_flow_module._qr_decoder = config_flow_module._UNSET


@pytest.fixture
def no_qr_decoder():
    """Simulate a Home Assistant without pyzbar/Pillow."""
    with patch.object(config_flow_module, "_load_qr_decoder", return_value=None):
        yield


def _fake_decoder(codes):
    """Build a (pyzbar, Image) pair returning the given decoded codes."""
    pyzbar = SimpleNamespace(decode=lambda image: codes)

    class _FakeImage:
        width = 100
        height = 100

        def convert(self, mode):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    image_module = SimpleNamespace(open=lambda path: _FakeImage())
    return pyzbar, image_module


@pytest.fixture
def qr_decoder():
    """Simulate a Home Assistant where the optional decoder is importable."""
    codes = [SimpleNamespace(type="QRCODE", data=QR_PAYLOAD.encode())]
    with patch.object(config_flow_module, "_load_qr_decoder", return_value=_fake_decoder(codes)):
        yield


async def test_decoder_is_never_a_hard_requirement(hass: HomeAssistant) -> None:
    """No decoder in the manifest: a missing wheel must never break the flow."""
    from homeassistant.loader import async_get_integration

    integration = await async_get_integration(hass, DOMAIN)
    assert not any(
        requirement.lower().startswith(("zxing", "pyzbar", "pillow")) for requirement in integration.requirements
    )


async def test_slugify_is_never_pinned_by_this_integration(hass: HomeAssistant) -> None:
    """Home Assistant pins python-slugify itself, so pinning it here can only conflict.

    Renovate raised it to v9, which pip refused outright: homeassistant
    depends on python-slugify==8.0.4, and the resolution became impossible.
    The package ships with Home Assistant, so importing it needs no
    requirement of our own.
    """
    from homeassistant.loader import async_get_integration

    integration = await async_get_integration(hass, DOMAIN)
    assert not any(requirement.lower().startswith("python-slugify") for requirement in integration.requirements)

    from slugify import slugify

    assert slugify("Trimestre 1", separator="_") == "trimestre_1"


async def test_qr_form_without_image_decoder(hass: HomeAssistant, no_qr_decoder) -> None:
    """Without a decoder, the form falls back to the JSON field only."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "qr_code_login"})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "qr_code_login"
    assert {str(key) for key in result["data_schema"].schema} == {
        "account_type",
        "qr_code_json",
        "qr_code_pin",
    }
    assert result["data_schema"]({**QR_ELEVE_INPUT, "qr_code_pin": "0001"})["qr_code_pin"] == "0001"


async def test_qr_form_with_image_decoder(hass: HomeAssistant, qr_decoder) -> None:
    """With a decoder, the photo field shows up and the JSON becomes optional."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "qr_code_login"})

    assert result["type"] is FlowResultType.FORM
    # The JSON field is the fallback, not part of the first ask.
    assert {str(key) for key in result["data_schema"].schema} == {
        "account_type",
        "qr_code_image",
        "qr_code_pin",
    }
    validated = result["data_schema"]({"account_type": "eleve", "qr_code_pin": "1234"})
    assert "qr_code_json" not in validated


async def test_qr_photo_feeds_the_json(hass: HomeAssistant, qr_decoder) -> None:
    """A decoded photo is used as the QR JSON for authentication."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "qr_code_login"})

    mock_client = _make_qr_client("Jean Dupont")
    mock_creds = _make_credentials()

    with (
        patch.object(config_flow_module, "_decode_qr_image", return_value=QR_PAYLOAD),
        patch(
            "custom_components.pronote.api.auth.PronoteAuth.authenticate",
            return_value=(mock_client, mock_creds),
        ) as authenticate,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"account_type": "eleve", "qr_code_image": UPLOAD_ID, "qr_code_pin": "1234"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "nickname"
    credentials = authenticate.call_args.args[-1]
    assert credentials["qr_code_json"] == QR_PAYLOAD
    assert "qr_code_image" not in credentials


async def test_qr_photo_undecodable(hass: HomeAssistant, qr_decoder) -> None:
    """An unreadable photo shows a field error and never authenticates."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "qr_code_login"})

    with (
        patch.object(config_flow_module, "_decode_qr_image", side_effect=ValueError("nope")),
        patch("custom_components.pronote.api.auth.PronoteAuth.authenticate") as authenticate,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"account_type": "eleve", "qr_code_image": UPLOAD_ID, "qr_code_pin": "1234"},
        )

    assert result["errors"] == {"qr_code_image": "invalid_qr_image"}
    authenticate.assert_not_called()


def test_decode_qr_image_rejects_a_foreign_qr_code(hass: HomeAssistant) -> None:
    """A QR code that is not a Pronote payload is refused."""
    codes = [SimpleNamespace(type="QRCODE", data=b'{"url":"https://example.com"}')]
    decoder = _fake_decoder(codes)

    @contextlib.contextmanager
    def fake_upload(hass, file_id):
        yield SimpleNamespace(stat=lambda: SimpleNamespace(st_size=1024))

    with patch("homeassistant.components.file_upload.process_uploaded_file", fake_upload):
        with pytest.raises(ValueError):
            config_flow_module._decode_qr_image(hass, "upload-id", decoder)


def test_decode_qr_image_accepts_a_pronote_qr_code(hass: HomeAssistant) -> None:
    """A valid Pronote QR code is returned as raw JSON text."""
    codes = [SimpleNamespace(type="QRCODE", data=QR_PAYLOAD.encode())]
    decoder = _fake_decoder(codes)

    @contextlib.contextmanager
    def fake_upload(hass, file_id):
        yield SimpleNamespace(stat=lambda: SimpleNamespace(st_size=1024))

    with patch("homeassistant.components.file_upload.process_uploaded_file", fake_upload):
        assert config_flow_module._decode_qr_image(hass, "upload-id", decoder) == QR_PAYLOAD


async def test_qr_blank_input_does_not_authenticate(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "qr_code_login"})
    with patch.object(PronoteAPIClient, "authenticate") as authenticate:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**QR_ELEVE_INPUT, "qr_code_json": "   "}
        )
    assert result["errors"] == {"base": "qr_code_required"}
    authenticate.assert_not_called()


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

    await hass.async_block_till_done()


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

    await hass.async_block_till_done()


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


class TestQRReaderPage:
    """The QR Code is decoded in the browser, so the page must be served and linked.

    Python decoders are a dead end on Home Assistant OS (no musl wheel for
    zxing-cpp, libzbar missing for pyzbar), which is why this page exists.
    """

    def test_the_page_and_its_decoder_ship_with_the_integration(self):
        folder = Path(config_flow_module.__file__).parent / "qr_reader"
        page = folder / "index.html"

        assert page.is_file()
        assert (folder / "jsQR.js").is_file()
        assert (folder / "LICENSE.jsQR").is_file(), "vendored jsQR keeps its Apache-2.0 licence"

        html = page.read_text(encoding="utf-8")
        # jsQR is the fallback for browsers without BarcodeDetector (Firefox, iOS).
        assert 'script.src = "jsQR.js"' in html
        assert "BarcodeDetector" in html
        # Nothing may leave the browser: no upload, no third-party origin.
        assert "cdn." not in html
        assert "https://" not in html.split("<script>")[1]

    async def test_the_form_links_to_the_reader(self, hass: HomeAssistant) -> None:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "qr_code_login"})

        assert result["description_placeholders"]["qr_reader_url"] == config_flow_module.QR_READER_PAGE

    async def test_the_page_is_registered_once(self, hass: HomeAssistant) -> None:
        assert await async_setup_component(hass, "http", {})

        with patch.object(hass.http, "async_register_static_paths") as register:
            await config_flow_module._async_qr_reader_url(hass)
            await config_flow_module._async_qr_reader_url(hass)

        register.assert_called_once()
        config = register.call_args[0][0][0]
        assert config.url_path == config_flow_module.QR_READER_URL
        assert Path(config.path).name == "qr_reader"

    async def test_a_failing_registration_never_blocks_the_form(self, hass: HomeAssistant) -> None:
        """A 404 link is annoying; a config flow that cannot open is not acceptable."""
        assert await async_setup_component(hass, "http", {})

        with patch.object(hass.http, "async_register_static_paths", side_effect=RuntimeError("boom")):
            url = await config_flow_module._async_qr_reader_url(hass)

        assert url == config_flow_module.QR_READER_PAGE

    async def test_the_reauth_form_links_to_the_reader(self, hass: HomeAssistant) -> None:
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={"connection_type": "qrcode", "account_type": "eleve", "qr_code_url": "https://pronote.example.com"},
            version=3,
        )
        entry.add_to_hass(hass)

        result = await entry.start_reauth_flow(hass)

        assert result["step_id"] == "reauth_confirm"
        assert result["description_placeholders"]["qr_reader_url"] == config_flow_module.QR_READER_PAGE


class TestRejectedQRCodeMessage:
    """A refused PIN or a spent QR code must say so, not "authentication error"."""

    async def test_the_setup_form_names_the_real_cause(self, hass: HomeAssistant) -> None:
        from custom_components.pronote.api import QRCodeRejectedError

        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "qr_code_login"})

        with patch.object(
            PronoteAPIClient, "authenticate", side_effect=QRCodeRejectedError("QR code expiré ou déjà utilisé")
        ):
            result = await hass.config_entries.flow.async_configure(result["flow_id"], QR_ELEVE_INPUT)

        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "qr_code_rejected"}

    async def test_the_reauth_form_names_the_real_cause(self, hass: HomeAssistant) -> None:
        from custom_components.pronote.api import QRCodeRejectedError

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={"connection_type": "qrcode", "account_type": "eleve", "qr_code_url": "https://pronote.example.com"},
            version=3,
        )
        entry.add_to_hass(hass)
        result = await entry.start_reauth_flow(hass)

        with patch.object(PronoteAPIClient, "authenticate", side_effect=QRCodeRejectedError("PIN incorrect")):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {"qr_code_json": '{"url":"x"}', "qr_code_pin": "0000"}
            )

        assert result["errors"] == {"base": "qr_code_rejected"}


class TestSuspendedIPMessage:
    """A banned IP must be named, so the user waits instead of retrying."""

    async def test_the_qr_form_tells_the_user_to_wait(self, hass: HomeAssistant) -> None:
        from custom_components.pronote.api import IPSuspendedError

        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "qr_code_login"})

        with patch.object(PronoteAPIClient, "authenticate", side_effect=IPSuspendedError("IP suspendue")):
            result = await hass.config_entries.flow.async_configure(result["flow_id"], QR_ELEVE_INPUT)

        assert result["errors"] == {"base": "ip_suspended"}

    async def test_the_password_form_tells_the_user_to_wait(self, hass: HomeAssistant) -> None:
        from custom_components.pronote.api import IPSuspendedError

        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"next_step_id": "username_password_login"}
        )

        with patch.object(PronoteAPIClient, "authenticate", side_effect=IPSuspendedError("IP suspendue")):
            result = await hass.config_entries.flow.async_configure(result["flow_id"], UP_ELEVE_INPUT)

        assert result["errors"] == {"base": "ip_suspended"}


class TestJSONFieldIsAFallback:
    """Asking for a photo and a JSON at once made the form look like it needed both."""

    async def test_an_unreadable_picture_reveals_the_json_field(self, hass: HomeAssistant, qr_decoder) -> None:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "qr_code_login"})

        assert "qr_code_json" not in {str(key) for key in result["data_schema"].schema}

        with patch.object(config_flow_module, "_decode_qr_image", side_effect=ValueError("no QR here")):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {"account_type": "eleve", "qr_code_image": UPLOAD_ID, "qr_code_pin": "1234"},
            )

        assert result["errors"] == {"qr_code_image": "invalid_qr_image"}
        assert "qr_code_json" in {str(key) for key in result["data_schema"].schema}

    async def test_an_empty_submission_reveals_the_json_field(self, hass: HomeAssistant, qr_decoder) -> None:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "qr_code_login"})

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"account_type": "eleve", "qr_code_pin": "1234"}
        )

        assert result["errors"] == {"base": "qr_code_required"}
        assert "qr_code_json" in {str(key) for key in result["data_schema"].schema}


class TestTwoFactorSettingsLiveInOptions:
    """Off the setup form, but still reachable for the accounts that need them."""

    async def test_the_options_expose_them(self, hass: HomeAssistant) -> None:
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={"connection_type": "qrcode", "account_type": "eleve", "device_name": "Salon"},
            options={"nickname": "Jean"},
            version=3,
        )
        entry.add_to_hass(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)
        keys = {str(key): key for key in result["data_schema"].schema}

        assert "device_name" in keys
        assert "account_pin" in keys
        # The value already stored at setup is what the form starts from.
        assert keys["device_name"].default() == "Salon"
