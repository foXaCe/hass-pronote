"""Tests for the Pronote config flow."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pronotepy.exceptions
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pronote.config_flow import (
    CannotConnect,
    InvalidAuth,
    get_ent_list,
)
from custom_components.pronote.const import (
    DEFAULT_ALARM_OFFSET,
    DEFAULT_LUNCH_BREAK_TIME,
    DEFAULT_REFRESH_INTERVAL,
    DOMAIN,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_eleve_client(name="Jean Dupont"):
    """Return a mock pronote client for an 'eleve' account."""
    client = MagicMock()
    client.info = SimpleNamespace(name=name)
    client.children = []
    return client


def _make_parent_client(name="Parent Dupont", children_names=None):
    """Return a mock pronote client for a 'parent' account."""
    if children_names is None:
        children_names = ["Jean Dupont", "Marie Dupont"]
    client = MagicMock()
    client.info = SimpleNamespace(name=name)
    client.children = [SimpleNamespace(name=n) for n in children_names]
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


UP_ELEVE_INPUT = {
    "account_type": "eleve",
    "url": "https://pronote.example.com/pronote/",
    "username": "jean.dupont",
    "password": "secret123",
}

UP_PARENT_INPUT = {
    "account_type": "parent",
    "url": "https://pronote.example.com/pronote/",
    "username": "parent.dupont",
    "password": "secret456",
}

QR_ELEVE_INPUT = {
    "account_type": "eleve",
    "qr_code_json": '{"url":"https://pronote.example.com"}',
    "qr_code_pin": "1234",
}

QR_PARENT_INPUT = {
    "account_type": "parent",
    "qr_code_json": '{"url":"https://pronote.example.com"}',
    "qr_code_pin": "5678",
}


# ===========================================================================
# Original unit tests (kept)
# ===========================================================================


class TestGetEntList:
    @patch("custom_components.pronote.config_flow.pronotepy")
    def test_returns_ent_list(self, mock_pronotepy):
        mock_pronotepy.ent = MagicMock()
        mock_pronotepy.ent.__dir__ = lambda self: [
            "__builtins__",
            "ent",
            "complex_ent",
            "generic_func",
            "ac_paris",
            "ac_lyon",
        ]

        result = get_ent_list()

        assert "ac_paris" in result
        assert "ac_lyon" in result
        assert "__builtins__" not in result
        assert "ent" not in result
        assert "complex_ent" not in result
        assert "generic_func" not in result

    @patch("custom_components.pronote.config_flow.pronotepy")
    def test_excludes_dunder(self, mock_pronotepy):
        mock_pronotepy.ent = MagicMock()
        mock_pronotepy.ent.__dir__ = lambda self: ["__init__", "__name__", "ac_paris"]

        result = get_ent_list()
        assert len(result) == 1
        assert result[0] == "ac_paris"


class TestExceptions:
    def test_cannot_connect(self):
        exc = CannotConnect()
        assert isinstance(exc, Exception)

    def test_invalid_auth(self):
        exc = InvalidAuth()
        assert isinstance(exc, Exception)


# ===========================================================================
# async_step_user  (menu)
# ===========================================================================


async def test_step_user_shows_menu(hass: HomeAssistant) -> None:
    """The initial user step should present a menu with two login options."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.MENU
    assert "username_password_login" in result["menu_options"]
    assert "qr_code_login" in result["menu_options"]


# ===========================================================================
# async_step_username_password_login
# ===========================================================================


async def test_up_login_shows_form(hass: HomeAssistant) -> None:
    """Selecting username_password_login shows the UP form."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "username_password_login"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "username_password_login"


async def test_up_login_eleve_success(hass: HomeAssistant) -> None:
    """Successful eleve login via UP goes to nickname step."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "username_password_login"},
    )

    mock_client = _make_eleve_client("Jean Dupont")
    with patch(
        "custom_components.pronote.config_flow.get_client_from_username_password",
        return_value=mock_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            UP_ELEVE_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "nickname"


async def test_up_login_eleve_full_flow(hass: HomeAssistant) -> None:
    """Full UP eleve flow: menu -> UP form -> nickname -> create entry."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "username_password_login"},
    )

    mock_client = _make_eleve_client("Jean Dupont")
    with patch(
        "custom_components.pronote.config_flow.get_client_from_username_password",
        return_value=mock_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            UP_ELEVE_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "nickname"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"nickname": "Jean"},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Jean Dupont"
    assert result["data"]["connection_type"] == "username_password"
    assert result["data"]["username"] == "jean.dupont"
    assert result["options"]["nickname"] == "Jean"


async def test_up_login_parent_success(hass: HomeAssistant) -> None:
    """Successful parent login via UP goes to parent step, then nickname."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "username_password_login"},
    )

    mock_client = _make_parent_client("Parent Dupont", ["Jean Dupont", "Marie Dupont"])
    with patch(
        "custom_components.pronote.config_flow.get_client_from_username_password",
        return_value=mock_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            UP_PARENT_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "parent"


async def test_up_login_parent_full_flow(hass: HomeAssistant) -> None:
    """Full UP parent flow: menu -> UP form -> parent -> nickname -> create entry."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "username_password_login"},
    )

    mock_client = _make_parent_client("Parent Dupont", ["Jean Dupont", "Marie Dupont"])
    with patch(
        "custom_components.pronote.config_flow.get_client_from_username_password",
        return_value=mock_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            UP_PARENT_INPUT,
        )

    assert result["step_id"] == "parent"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"child": "Jean Dupont"},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "nickname"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"nickname": "Jean"},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Jean Dupont (via compte parent)"
    assert result["data"]["child"] == "Jean Dupont"
    assert result["data"]["account_type"] == "parent"
    assert result["options"]["nickname"] == "Jean"


async def test_up_login_invalid_auth_none_client(hass: HomeAssistant) -> None:
    """When get_client_from_username_password returns None, show invalid_auth."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "username_password_login"},
    )

    with patch(
        "custom_components.pronote.config_flow.get_client_from_username_password",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            UP_ELEVE_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "username_password_login"
    assert result["errors"]["base"] == "invalid_auth"


async def test_up_login_invalid_auth_raised(hass: HomeAssistant) -> None:
    """When InvalidAuth is raised directly, show invalid_auth."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "username_password_login"},
    )

    with patch(
        "custom_components.pronote.config_flow.get_client_from_username_password",
        side_effect=InvalidAuth,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            UP_ELEVE_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_auth"


async def test_up_login_crypto_error(hass: HomeAssistant) -> None:
    """When CryptoError is raised by pronotepy, show invalid_auth."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "username_password_login"},
    )

    with patch(
        "custom_components.pronote.config_flow.get_client_from_username_password",
        side_effect=pronotepy.exceptions.CryptoError("bad key"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            UP_ELEVE_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_auth"


async def test_up_login_with_ent(hass: HomeAssistant) -> None:
    """UP login with an ENT function stores it in user inputs."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "username_password_login"},
    )

    mock_client = _make_eleve_client("Jean Dupont")
    input_with_ent = {**UP_ELEVE_INPUT, "ent": "ac_rennes"}
    with patch(
        "custom_components.pronote.config_flow.get_client_from_username_password",
        return_value=mock_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            input_with_ent,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "nickname"


# ===========================================================================
# async_step_qr_code_login
# ===========================================================================


async def test_qr_login_shows_form(hass: HomeAssistant) -> None:
    """Selecting qr_code_login shows the QR form."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "qr_code_login"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "qr_code_login"


async def test_qr_login_eleve_success(hass: HomeAssistant) -> None:
    """Successful eleve QR login goes to nickname step."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "qr_code_login"},
    )

    mock_client = _make_qr_client("Jean Dupont")
    with patch(
        "custom_components.pronote.config_flow.get_client_from_qr_code",
        return_value=mock_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            QR_ELEVE_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "nickname"


async def test_qr_login_eleve_full_flow(hass: HomeAssistant) -> None:
    """Full QR eleve flow: menu -> QR form -> nickname -> create entry."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "qr_code_login"},
    )

    mock_client = _make_qr_client("Jean Dupont")
    with patch(
        "custom_components.pronote.config_flow.get_client_from_qr_code",
        return_value=mock_client,
    ):
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
    assert result["data"]["qr_code_url"] == "https://pronote.example.com/pronote/eleve.html"
    assert result["data"]["qr_code_username"] == "qr_user"
    assert result["data"]["qr_code_password"] == "qr_pass"
    assert result["data"]["qr_code_uuid"] == "qr_uuid_1234"
    assert result["options"]["nickname"] == "Jean"


async def test_qr_login_parent_success(hass: HomeAssistant) -> None:
    """Successful parent QR login goes to parent step."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "qr_code_login"},
    )

    mock_client = _make_qr_client("Parent Dupont", is_parent=True)
    with patch(
        "custom_components.pronote.config_flow.get_client_from_qr_code",
        return_value=mock_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            QR_PARENT_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "parent"


async def test_qr_login_parent_full_flow(hass: HomeAssistant) -> None:
    """Full QR parent flow: menu -> QR form -> parent -> nickname -> create entry."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "qr_code_login"},
    )

    mock_client = _make_qr_client("Parent Dupont", is_parent=True, children_names=["Jean Dupont", "Marie Dupont"])
    with patch(
        "custom_components.pronote.config_flow.get_client_from_qr_code",
        return_value=mock_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            QR_PARENT_INPUT,
        )

    assert result["step_id"] == "parent"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"child": "Marie Dupont"},
    )

    assert result["step_id"] == "nickname"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"nickname": "Marie"},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Marie Dupont (via compte parent)"
    assert result["data"]["child"] == "Marie Dupont"
    assert result["options"]["nickname"] == "Marie"


async def test_qr_login_invalid_auth_none_client(hass: HomeAssistant) -> None:
    """When get_client_from_qr_code returns None, show invalid_auth."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "qr_code_login"},
    )

    with patch(
        "custom_components.pronote.config_flow.get_client_from_qr_code",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            QR_ELEVE_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "qr_code_login"
    assert result["errors"]["base"] == "invalid_auth"


async def test_qr_login_invalid_auth_raised(hass: HomeAssistant) -> None:
    """When InvalidAuth is raised for QR login, show invalid_auth."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "qr_code_login"},
    )

    with patch(
        "custom_components.pronote.config_flow.get_client_from_qr_code",
        side_effect=InvalidAuth,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            QR_ELEVE_INPUT,
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "qr_code_login"
    assert result["errors"]["base"] == "invalid_auth"


# ===========================================================================
# async_step_nickname  (unique_id abort, default nickname logic)
# ===========================================================================


async def test_nickname_default_uses_last_name(hass: HomeAssistant) -> None:
    """The default nickname for 'Jean Dupont' should be 'Dupont'."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "username_password_login"},
    )

    mock_client = _make_eleve_client("Jean Dupont")
    with patch(
        "custom_components.pronote.config_flow.get_client_from_username_password",
        return_value=mock_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            UP_ELEVE_INPUT,
        )

    assert result["step_id"] == "nickname"
    # The schema default should contain 'Dupont' (last name)
    schema = result["data_schema"].schema
    for key in schema:
        if key == "nickname":
            assert key.default() == "Dupont"


async def test_nickname_single_name_default(hass: HomeAssistant) -> None:
    """When client name is a single word, nickname default is that word."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "username_password_login"},
    )

    mock_client = _make_eleve_client("Jean")
    with patch(
        "custom_components.pronote.config_flow.get_client_from_username_password",
        return_value=mock_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            UP_ELEVE_INPUT,
        )

    assert result["step_id"] == "nickname"
    schema = result["data_schema"].schema
    for key in schema:
        if key == "nickname":
            assert key.default() == "Jean"


async def test_nickname_abort_if_unique_id_configured(hass: HomeAssistant) -> None:
    """If a config entry for the same child already exists, abort."""
    # Pre-add an entry with unique_id "Jean Dupont"
    existing = MockConfigEntry(
        domain=DOMAIN,
        data={**UP_ELEVE_INPUT, "connection_type": "username_password"},
        unique_id="Jean Dupont",
        version=2,
    )
    existing.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "username_password_login"},
    )

    mock_client = _make_eleve_client("Jean Dupont")
    with patch(
        "custom_components.pronote.config_flow.get_client_from_username_password",
        return_value=mock_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            UP_ELEVE_INPUT,
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_nickname_parent_uses_child_name_for_unique_id(hass: HomeAssistant) -> None:
    """For parent accounts the unique_id is the child's name, not the parent's."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "username_password_login"},
    )

    mock_client = _make_parent_client("Parent Dupont", ["Jean Dupont", "Marie Dupont"])
    with patch(
        "custom_components.pronote.config_flow.get_client_from_username_password",
        return_value=mock_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            UP_PARENT_INPUT,
        )

    # Select child "Marie Dupont"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"child": "Marie Dupont"},
    )

    assert result["step_id"] == "nickname"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"nickname": "Marie"},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    # unique_id should be child name, not parent name
    assert result["result"].unique_id == "Marie Dupont"


# ===========================================================================
# async_step_reauth  (username_password path)
# ===========================================================================


async def test_reauth_up_shows_password_form(hass: HomeAssistant) -> None:
    """Reauth for UP connection shows a password-only form."""
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

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    # The schema should have a "password" field
    schema_keys = [str(k) for k in result["data_schema"].schema]
    assert "password" in schema_keys


async def test_reauth_up_success(hass: HomeAssistant) -> None:
    """Successful reauth for UP updates the entry and aborts."""
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
    with patch(
        "custom_components.pronote.config_flow.get_client_from_username_password",
        return_value=mock_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"password": "new_password"},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == "new_password"


async def test_reauth_up_invalid_auth(hass: HomeAssistant) -> None:
    """Failed reauth for UP shows error and stays on form."""
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

    with patch(
        "custom_components.pronote.config_flow.get_client_from_username_password",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"password": "wrong_password"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"]["base"] == "invalid_auth"


async def test_reauth_up_crypto_error(hass: HomeAssistant) -> None:
    """CryptoError during UP reauth shows invalid_auth error."""
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

    with patch(
        "custom_components.pronote.config_flow.get_client_from_username_password",
        side_effect=pronotepy.exceptions.CryptoError("bad key"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"password": "bad_password"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_auth"


async def test_reauth_up_generic_exception(hass: HomeAssistant) -> None:
    """A generic Exception during UP reauth shows invalid_auth error."""
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

    with patch(
        "custom_components.pronote.config_flow.get_client_from_username_password",
        side_effect=Exception("network error"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"password": "bad_password"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_auth"


# ===========================================================================
# async_step_reauth  (qrcode path)
# ===========================================================================


async def test_reauth_qr_shows_qr_form(hass: HomeAssistant) -> None:
    """Reauth for QR code connection shows qr_code fields."""
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

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    schema_keys = [str(k) for k in result["data_schema"].schema]
    assert "qr_code_json" in schema_keys
    assert "qr_code_pin" in schema_keys


async def test_reauth_qr_success(hass: HomeAssistant) -> None:
    """Successful QR reauth updates the entry credentials and aborts."""
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
    with patch(
        "custom_components.pronote.config_flow.get_client_from_qr_code",
        return_value=mock_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "qr_code_json": '{"new":"data"}',
                "qr_code_pin": "9999",
            },
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["qr_code_url"] == "https://pronote.example.com/pronote/eleve.html"
    assert entry.data["qr_code_username"] == "qr_user"
    assert entry.data["qr_code_password"] == "qr_pass"
    assert entry.data["qr_code_uuid"] == "qr_uuid_1234"


async def test_reauth_qr_invalid_auth(hass: HomeAssistant) -> None:
    """Failed QR reauth shows error and stays on form."""
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

    with patch(
        "custom_components.pronote.config_flow.get_client_from_qr_code",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "qr_code_json": '{"bad":"data"}',
                "qr_code_pin": "0000",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"]["base"] == "invalid_auth"


async def test_reauth_qr_generic_exception(hass: HomeAssistant) -> None:
    """A generic Exception during QR reauth shows invalid_auth error."""
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

    with patch(
        "custom_components.pronote.config_flow.get_client_from_qr_code",
        side_effect=Exception("network failure"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "qr_code_json": '{"bad":"data"}',
                "qr_code_pin": "0000",
            },
        )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["errors"]["base"] == "invalid_auth"


async def test_reauth_default_connection_type_is_up(hass: HomeAssistant) -> None:
    """When connection_type is missing from entry data, default to username_password."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
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

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    # Should show a password field (UP path), not QR fields
    schema_keys = [str(k) for k in result["data_schema"].schema]
    assert "password" in schema_keys
    assert "qr_code_json" not in schema_keys


# ===========================================================================
# OptionsFlowHandler
# ===========================================================================


async def test_options_flow_shows_form(hass: HomeAssistant) -> None:
    """Options flow init shows the options form with defaults."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "connection_type": "username_password",
            "account_type": "eleve",
            "url": "https://pronote.example.com/pronote/",
            "username": "jean.dupont",
            "password": "secret",
        },
        options={"nickname": "Jean"},
        unique_id="Jean Dupont",
        version=2,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"


async def test_options_flow_submit(hass: HomeAssistant) -> None:
    """Submitting the options flow creates an entry with user input."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "connection_type": "username_password",
            "account_type": "eleve",
            "url": "https://pronote.example.com/pronote/",
            "username": "jean.dupont",
            "password": "secret",
        },
        options={"nickname": "Jean"},
        unique_id="Jean Dupont",
        version=2,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "nickname": "Jeannot",
            "refresh_interval": 30,
            "lunch_break_time": "12:30",
            "alarm_offset": 45,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["nickname"] == "Jeannot"
    assert result["data"]["refresh_interval"] == 30
    assert result["data"]["lunch_break_time"] == "12:30"
    assert result["data"]["alarm_offset"] == 45


async def test_options_flow_defaults(hass: HomeAssistant) -> None:
    """Options form defaults come from the existing options or global defaults."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "connection_type": "username_password",
            "account_type": "eleve",
            "url": "https://pronote.example.com/pronote/",
            "username": "jean.dupont",
            "password": "secret",
        },
        options={},
        unique_id="Jean Dupont",
        version=2,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    # Verify the schema defaults
    schema = result["data_schema"].schema
    defaults = {}
    for key in schema:
        if hasattr(key, "default") and callable(key.default):
            defaults[str(key)] = key.default()
    assert defaults.get("refresh_interval") == DEFAULT_REFRESH_INTERVAL
    assert defaults.get("lunch_break_time") == DEFAULT_LUNCH_BREAK_TIME
    assert defaults.get("alarm_offset") == DEFAULT_ALARM_OFFSET


async def test_options_flow_preserves_existing_options(hass: HomeAssistant) -> None:
    """When existing options are set, they appear as defaults."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "connection_type": "username_password",
            "account_type": "eleve",
            "url": "https://pronote.example.com/pronote/",
            "username": "jean.dupont",
            "password": "secret",
        },
        options={
            "nickname": "JD",
            "refresh_interval": 60,
            "lunch_break_time": "11:45",
            "alarm_offset": 90,
        },
        unique_id="Jean Dupont",
        version=2,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    schema = result["data_schema"].schema
    defaults = {}
    for key in schema:
        if hasattr(key, "default") and callable(key.default):
            defaults[str(key)] = key.default()
    assert defaults.get("nickname") == "JD"
    assert defaults.get("refresh_interval") == 60
    assert defaults.get("lunch_break_time") == "11:45"
    assert defaults.get("alarm_offset") == 90


# ===========================================================================
# Edge cases / additional coverage
# ===========================================================================


async def test_qr_stores_uuid(hass: HomeAssistant) -> None:
    """QR code login generates and stores a UUID in user inputs."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "qr_code_login"},
    )

    generated_uuids = []

    def capture_qr_call(user_inputs):
        """Capture the UUID that was generated before client overwrites it."""
        generated_uuids.append(user_inputs.get("qr_code_uuid"))
        return _make_qr_client("Jean Dupont")

    with patch(
        "custom_components.pronote.config_flow.get_client_from_qr_code",
        side_effect=capture_qr_call,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            QR_ELEVE_INPUT,
        )

    assert len(generated_uuids) == 1
    # The UUID generated before the call should be a valid uuid4 string (36 chars)
    assert generated_uuids[0] is not None
    assert len(generated_uuids[0]) == 36


async def test_up_login_connection_type_set(hass: HomeAssistant) -> None:
    """UP login sets connection_type to 'username_password' in user_inputs."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "username_password_login"},
    )

    mock_client = _make_eleve_client("Jean Dupont")
    with patch(
        "custom_components.pronote.config_flow.get_client_from_username_password",
        return_value=mock_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            UP_ELEVE_INPUT,
        )

    # Complete the nickname step
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"nickname": "Jean"},
    )

    assert result["data"]["connection_type"] == "username_password"


async def test_qr_login_connection_type_set(hass: HomeAssistant) -> None:
    """QR login sets connection_type to 'qrcode' in user_inputs."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "qr_code_login"},
    )

    mock_client = _make_qr_client("Jean Dupont")
    with patch(
        "custom_components.pronote.config_flow.get_client_from_qr_code",
        return_value=mock_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            QR_ELEVE_INPUT,
        )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"nickname": "Jean"},
    )

    assert result["data"]["connection_type"] == "qrcode"


async def test_parent_step_shows_children(hass: HomeAssistant) -> None:
    """Parent step shows a form with child selection matching client children."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "username_password_login"},
    )

    mock_client = _make_parent_client("Parent Dupont", ["Alice", "Bob", "Charlie"])
    with patch(
        "custom_components.pronote.config_flow.get_client_from_username_password",
        return_value=mock_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            UP_PARENT_INPUT,
        )

    assert result["step_id"] == "parent"
    # The schema should contain a 'child' key with In validator
    schema = result["data_schema"].schema
    for key in schema:
        if str(key) == "child":
            container = key.validators[0] if hasattr(key, "validators") else schema[key]
            assert "Alice" in container.container
            assert "Bob" in container.container
            assert "Charlie" in container.container


async def test_reauth_up_then_retry_after_error(hass: HomeAssistant) -> None:
    """After a failed reauth attempt, user can retry and succeed."""
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

    # First attempt fails
    with patch(
        "custom_components.pronote.config_flow.get_client_from_username_password",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"password": "wrong"},
        )

    assert result["errors"]["base"] == "invalid_auth"

    # Second attempt succeeds
    mock_client = _make_eleve_client("Jean Dupont")
    with patch(
        "custom_components.pronote.config_flow.get_client_from_username_password",
        return_value=mock_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"password": "correct_password"},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == "correct_password"


async def test_reauth_qr_then_retry_after_error(hass: HomeAssistant) -> None:
    """After a failed QR reauth attempt, user can retry and succeed."""
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

    # First attempt fails
    with patch(
        "custom_components.pronote.config_flow.get_client_from_qr_code",
        return_value=None,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"qr_code_json": '{"bad":"data"}', "qr_code_pin": "0000"},
        )

    assert result["errors"]["base"] == "invalid_auth"

    # Second attempt succeeds
    mock_client = _make_qr_client("Jean Dupont")
    with patch(
        "custom_components.pronote.config_flow.get_client_from_qr_code",
        return_value=mock_client,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"qr_code_json": '{"new":"data"}', "qr_code_pin": "9999"},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
