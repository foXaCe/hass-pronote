"""Config flow for Pronote integration."""

from __future__ import annotations

import importlib
import json
import logging
import uuid
from pathlib import Path
from typing import Any

# isort: off
import custom_components.pronote._compat  # noqa: F401  # Patch autoslot before pronotepy

# isort: on
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    FileSelector,
    FileSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
)

from .const import (
    DEFAULT_ALARM_OFFSET,
    DEFAULT_DEVICE_NAME,
    DEFAULT_GRADES_TO_DISPLAY,
    DEFAULT_LUNCH_BREAK_TIME,
    DEFAULT_REFRESH_INTERVAL,
    DEFAULT_SHOW_ALL_PERIODS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _get_api_client():
    """Import PronoteAPIClient lazily to avoid loading pronotepy at config_flow import."""
    from .api import PronoteAPIClient  # noqa: PLC0415

    return PronoteAPIClient()


def _get_auth_error():
    """Import AuthenticationError lazily."""
    from .api import AuthenticationError  # noqa: PLC0415

    return AuthenticationError


def _get_qr_rejected_error():
    """Import QRCodeRejectedError lazily."""
    from .api import QRCodeRejectedError  # noqa: PLC0415

    return QRCodeRejectedError


def _get_ip_suspended_error():
    """Import IPSuspendedError lazily."""
    from .api import IPSuspendedError  # noqa: PLC0415

    return IPSuspendedError


def get_ent_list() -> list[str]:
    import pronotepy.ent  # noqa: PLC0415  # lazy: avoids loading pronotepy at config_flow import

    ent_functions = dir(pronotepy.ent)
    ent = []
    for func in ent_functions:
        if func.startswith("__") or func in ["ent", "complex_ent", "generic_func"]:
            continue
        ent.append(func)
    return ent


ACCOUNT_TYPE_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=["eleve", "parent"],
        translation_key="account_type",
    )
)


def _step_user_schema_up() -> vol.Schema:
    """Build the username/password schema lazily (pronotepy.ent is heavy)."""
    return vol.Schema(
        {
            vol.Required("account_type"): ACCOUNT_TYPE_SELECTOR,
            vol.Required("url"): str,
            vol.Required("username"): str,
            vol.Required("password"): str,
            vol.Optional("ent"): vol.In(get_ent_list()),
        }
    )


# Static page that decodes the QR Code in the browser. Python decoders are a
# dead end on Home Assistant OS: zxing-cpp ships no musl wheel and pyzbar needs
# the system libzbar, so the reading happens client-side and only the resulting
# JSON is pasted back into the form.
QR_READER_URL = "/pronote-qr-reader"
QR_READER_PAGE = f"{QR_READER_URL}/index.html"
_QR_READER_REGISTERED = f"{DOMAIN}_qr_reader_registered"


async def _async_qr_reader_url(hass: HomeAssistant) -> str:
    """Serve the QR reader page once per Home Assistant run, and return its path."""
    if not hass.data.get(_QR_READER_REGISTERED):
        try:
            from homeassistant.components.http import StaticPathConfig  # noqa: PLC0415

            await hass.http.async_register_static_paths(
                [StaticPathConfig(QR_READER_URL, str(Path(__file__).parent / "qr_reader"), False)]
            )
        except Exception as err:  # noqa: BLE001  # a missing page must never block the form
            _LOGGER.warning("Could not serve the Pronote QR reader page: %s", err)
        hass.data[_QR_READER_REGISTERED] = True
    return QR_READER_PAGE


# Upper bounds for an uploaded picture, to keep the decoder cheap.
MAX_QR_IMAGE_BYTES = 12 * 1024 * 1024
MAX_QR_IMAGE_PIXELS = 24_000_000

_UNSET = object()
_qr_decoder: Any = _UNSET


def _load_qr_decoder() -> tuple[Any, Any] | None:
    """Return (pyzbar, PIL.Image) when a local QR decoder is usable, else None.

    Neither pyzbar nor Pillow is declared in the manifest: shipping a decoder as
    a hard requirement broke the whole config flow once (zxing-cpp has no wheel
    on Home Assistant OS/Container). The photo field is therefore a bonus that
    only shows up when both libraries happen to be importable, and pyzbar also
    needs the system libzbar, which it reports as ImportError/OSError.
    """
    try:
        from PIL import Image  # noqa: PLC0415
        from pyzbar import pyzbar  # noqa: PLC0415
    except (ImportError, OSError) as err:
        _LOGGER.debug("QR image decoder unavailable, falling back to JSON only: %s", err)
        return None
    return pyzbar, Image


async def _async_qr_decoder(hass: HomeAssistant) -> tuple[Any, Any] | None:
    """Return the cached QR decoder, importing it off the event loop."""
    global _qr_decoder  # noqa: PLW0603
    if _qr_decoder is _UNSET:
        _qr_decoder = await hass.async_add_import_executor_job(_load_qr_decoder)
    return _qr_decoder


def _decode_qr_image(hass: HomeAssistant, file_id: str, decoder: tuple[Any, Any]) -> str:
    """Decode an uploaded picture and return its Pronote QR payload as JSON text."""
    pyzbar, image_module = decoder

    from homeassistant.components.file_upload import process_uploaded_file  # noqa: PLC0415

    with process_uploaded_file(hass, file_id) as path:
        if path.stat().st_size > MAX_QR_IMAGE_BYTES:
            raise ValueError("QR image too large")
        with image_module.open(path) as image:
            if image.width * image.height > MAX_QR_IMAGE_PIXELS:
                raise ValueError("QR image too large")
            codes = [code for code in pyzbar.decode(image.convert("RGB")) if code.type == "QRCODE"]

    if len(codes) != 1:
        raise ValueError("Expected exactly one QR code")

    text = codes[0].data.decode("utf-8")
    payload = json.loads(text)
    if not isinstance(payload, dict) or not all(
        isinstance(payload.get(key), str) and payload[key] for key in ("url", "login", "jeton")
    ):
        raise ValueError("Not a Pronote QR code")
    return text


def _qr_fields(*, with_image: bool, with_json: bool) -> dict:
    """Build the QR fields: a photo and a PIN, and that is all it takes.

    The JSON field is the fallback, not the default. It only shows up when no
    decoder is installed, or once a picture has failed to decode — asking for
    both at once made the form look like it needed both.

    account_pin and device_name are not asked either: the QR PIN doubles as the
    account PIN and the device name has a sane default. Both stay editable in
    the options for the rare account where they differ.
    """
    fields: dict = {}
    if with_image:
        fields[vol.Optional("qr_code_image")] = FileSelector(FileSelectorConfig(accept="image/*"))
        if with_json:
            fields[vol.Optional("qr_code_json")] = str
    else:
        fields[vol.Required("qr_code_json")] = str
    fields[vol.Required("qr_code_pin")] = str
    return fields


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Pronote."""

    VERSION = 3
    pronote_client = None

    def __init__(self) -> None:
        self._user_inputs: dict = {}
        # Raised once a picture could not be turned into a QR payload, so the
        # user gets the JSON fallback instead of a dead end.
        self._show_json_field = False
        # Built lazily off the event loop: creating it imports pronotepy, whose
        # first import does blocking file I/O (ctypes looking up libgmp).
        self._api_client = None

    async def _async_ensure_api_client(self):
        """Return the API client, importing pronotepy off the event loop.

        pronotepy does blocking file I/O the first time it is imported, so the
        import must run in the executor rather than in the event loop.
        """
        if self._api_client is None:
            await self.hass.async_add_import_executor_job(importlib.import_module, "pronotepy")
            self._api_client = _get_api_client()
        return self._api_client

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Handle a flow initialized by the user."""
        _LOGGER.debug("Setup process initiated by user.")

        return self.async_show_menu(
            step_id="user",
            menu_options=["username_password_login", "qr_code_login"],
        )

    async def async_step_username_password_login(self, user_input: dict | None = None) -> FlowResult:
        """Handle username/password login step."""
        _LOGGER.debug("Connexion par identifiant et mot de passe")
        errors: dict[str, str] = {}
        await self._async_ensure_api_client()
        if user_input is not None:
            try:
                _LOGGER.debug("User Input received (keys: %s)", list(user_input.keys()))
                self._user_inputs.update(user_input)
                self._user_inputs["connection_type"] = "username_password"

                # Use the new API client
                await self._api_client.authenticate("username_password", self._user_inputs)
                client = self._api_client._client  # Access internal client for compatibility

                if client is None:
                    raise InvalidAuth
            except _get_ip_suspended_error() as err:
                _LOGGER.error("Pronote suspended this IP address: %s", err)
                errors["base"] = "ip_suspended"
            except _get_auth_error():
                errors["base"] = "invalid_auth"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception as err:
                _LOGGER.error("Unexpected error during auth: %s", err)
                errors["base"] = "invalid_auth"
            else:
                self.pronote_client = client

                if self._user_inputs["account_type"] == "parent":
                    return await self.async_step_parent()

                return await self.async_step_nickname()

        return self.async_show_form(
            step_id="username_password_login",
            # Building the schema imports pronotepy.ent; keep it off the loop.
            data_schema=await self.hass.async_add_executor_job(_step_user_schema_up),
            errors=errors,
        )

    async def _async_qr_schema(self, *, with_account_type: bool) -> vol.Schema:
        """Build the QR schema, probing the optional decoder off the event loop."""
        fields = _qr_fields(
            with_image=(await _async_qr_decoder(self.hass)) is not None,
            with_json=self._show_json_field,
        )
        if with_account_type:
            return vol.Schema({vol.Required("account_type"): ACCOUNT_TYPE_SELECTOR, **fields})
        return vol.Schema(fields)

    async def _async_prepare_qr_input(self, user_input: dict) -> dict[str, str]:
        """Turn an uploaded photo into JSON, and refuse an empty QR payload.

        Every failure here reveals the JSON field, so a picture Home Assistant
        cannot read never leaves the user stuck on a form they cannot fill.
        """
        image_id = user_input.pop("qr_code_image", None)
        if image_id:
            decoder = await _async_qr_decoder(self.hass)
            if decoder is None:
                self._show_json_field = True
                return {"qr_code_image": "qr_decoder_missing"}
            try:
                user_input["qr_code_json"] = await self.hass.async_add_executor_job(
                    _decode_qr_image, self.hass, image_id, decoder
                )
            except Exception as err:
                _LOGGER.debug("Could not decode the QR picture: %s - %s", type(err).__name__, err)
                self._show_json_field = True
                return {"qr_code_image": "invalid_qr_image"}
        if not user_input.get("qr_code_json", "").strip():
            self._show_json_field = True
            return {"base": "qr_code_required"}
        return {}

    async def async_step_qr_code_login(self, user_input: dict | None = None) -> FlowResult:
        """Handle QR code login step."""
        _LOGGER.debug("Connexion par QR code")
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input = dict(user_input)
            errors = await self._async_prepare_qr_input(user_input)
        if user_input is not None and not errors:
            await self._async_ensure_api_client()
            try:
                _LOGGER.debug("User Input received (keys: %s)", list(user_input.keys()))
                self._user_inputs.update(user_input)
                self._user_inputs["connection_type"] = "qrcode"
                self._user_inputs["qr_code_uuid"] = str(uuid.uuid4())

                # Use the new API client
                await self._api_client.authenticate("qrcode", self._user_inputs)
                client = self._api_client._client  # Access internal client for compatibility
                creds = self._api_client._credentials

                if client is None:
                    raise InvalidAuth
            except _get_ip_suspended_error() as err:
                # Retrying here is what makes the ban last; say so and stop.
                _LOGGER.error("Pronote suspended this IP address: %s", err)
                errors["base"] = "ip_suspended"
            except _get_qr_rejected_error() as err:
                # A wrong PIN or a spent QR code: say so, instead of a blanket
                # "authentication error" that sends people hunting elsewhere.
                _LOGGER.error("QR code rejected by Pronote: %s", err)
                errors["base"] = "qr_code_rejected"
            except _get_auth_error() as err:
                _LOGGER.error("AuthenticationError during QR auth: %s", err)
                errors["base"] = "invalid_auth"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception as err:
                _LOGGER.error("Unexpected error during QR auth: %s - %s", type(err).__name__, err)
                errors["base"] = "invalid_auth"
            else:
                # Save credentials from auth response
                if creds:
                    self._user_inputs["qr_code_url"] = creds.pronote_url
                    self._user_inputs["qr_code_username"] = creds.username
                    self._user_inputs["qr_code_password"] = creds.password
                    self._user_inputs["qr_code_uuid"] = creds.uuid

                self.pronote_client = client

                if self._user_inputs["account_type"] == "parent":
                    return await self.async_step_parent()

                return await self.async_step_nickname()

        return self.async_show_form(
            step_id="qr_code_login",
            data_schema=await self._async_qr_schema(with_account_type=True),
            errors=errors,
            description_placeholders={"qr_reader_url": await _async_qr_reader_url(self.hass)},
        )

    async def async_step_parent(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}

        children: dict[str, str] = {}
        for child in self.pronote_client.children:
            children[child.name] = child.name

        STEP_PARENT_DATA_SCHEMA = vol.Schema(
            {
                vol.Required("child"): vol.In(children),
            }
        )

        if user_input is None:
            return self.async_show_form(
                step_id="parent",
                data_schema=STEP_PARENT_DATA_SCHEMA,
                errors=errors,
            )

        self._user_inputs["child"] = user_input["child"]
        return await self.async_step_nickname()

    async def async_step_nickname(self, user_input: dict | None = None) -> FlowResult:
        """Handle nickname step."""

        child_name = self.pronote_client.info.name
        title = child_name
        if self._user_inputs.get("account_type") == "parent":
            child_name = self._user_inputs["child"]
            title = f"{child_name} (via compte parent)"

        await self.async_set_unique_id(child_name)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            self._user_inputs.update(user_input)

            return self.async_create_entry(
                title=title,
                data=self._user_inputs,
                options={
                    "nickname": self._user_inputs["nickname"],
                    "grades_to_display": DEFAULT_GRADES_TO_DISPLAY,
                    "show_all_periods": DEFAULT_SHOW_ALL_PERIODS,
                },
            )

        STEP_NICKNAME_SCHEMA = vol.Schema(
            {
                vol.Optional(
                    "nickname",
                    default=f"{child_name.split(' ')[-1] if ' ' in child_name else child_name}",
                ): str,
            }
        )

        return self.async_show_form(
            step_id="nickname",
            data_schema=STEP_NICKNAME_SCHEMA,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Handle reauth when credentials expire."""
        self._user_inputs = dict(entry_data)
        # Reset API client for fresh auth (imports pronotepy off the loop)
        self._api_client = None
        await self._async_ensure_api_client()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict | None = None) -> FlowResult:
        """Handle reauth confirmation."""
        errors: dict[str, str] = {}
        connection_type = self._user_inputs.get("connection_type", "username_password")
        if user_input is not None and connection_type == "qrcode":
            user_input = dict(user_input)
            errors = await self._async_prepare_qr_input(user_input)

        if user_input is not None and not errors:
            if connection_type == "qrcode":
                self._user_inputs["qr_code_json"] = user_input.get("qr_code_json", "")
                self._user_inputs["qr_code_pin"] = user_input.get("qr_code_pin", "")
                self._user_inputs["qr_code_uuid"] = str(uuid.uuid4())
                try:
                    await self._api_client.authenticate("qrcode", self._user_inputs)
                    client = self._api_client._client
                    creds = self._api_client._credentials
                    if client is None:
                        raise InvalidAuth
                except _get_ip_suspended_error() as err:
                    _LOGGER.error("Pronote suspended this IP address: %s", err)
                    errors["base"] = "ip_suspended"
                except _get_qr_rejected_error() as err:
                    _LOGGER.error("QR code rejected by Pronote: %s", err)
                    errors["base"] = "qr_code_rejected"
                except (_get_auth_error(), InvalidAuth):
                    errors["base"] = "invalid_auth"
                except Exception:
                    _LOGGER.exception("Unexpected error during QR reauth")
                    errors["base"] = "unknown"
                else:
                    if creds:
                        self._user_inputs["qr_code_url"] = creds.pronote_url
                        self._user_inputs["qr_code_username"] = creds.username
                        self._user_inputs["qr_code_password"] = creds.password
                        self._user_inputs["qr_code_uuid"] = creds.uuid
                    return self.async_update_reload_and_abort(
                        self._get_reauth_entry(),
                        data=self._user_inputs,
                    )
            else:
                self._user_inputs["password"] = user_input["password"]
                try:
                    await self._api_client.authenticate("username_password", self._user_inputs)
                    client = self._api_client._client
                    if client is None:
                        raise InvalidAuth
                except (_get_auth_error(), InvalidAuth):
                    errors["base"] = "invalid_auth"
                except Exception:
                    _LOGGER.exception("Unexpected error during password reauth")
                    errors["base"] = "unknown"
                else:
                    return self.async_update_reload_and_abort(
                        self._get_reauth_entry(),
                        data=self._user_inputs,
                    )

        connection_type = self._user_inputs.get("connection_type", "username_password")
        if connection_type == "qrcode":
            schema = await self._async_qr_schema(with_account_type=False)
        else:
            schema = vol.Schema(
                {
                    vol.Required("password"): str,
                }
            )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
            description_placeholders={"qr_reader_url": await _async_qr_reader_url(self.hass)},
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler(config_entry.entry_id)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry_id: str) -> None:
        """Initialize options flow."""
        self.config_entry_id = config_entry_id

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        config_entry = self.hass.config_entries.async_get_entry(self.config_entry_id)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional("nickname", default=config_entry.options.get("nickname")): vol.All(
                        vol.Coerce(str), vol.Length(min=0)
                    ),
                    vol.Optional(
                        "refresh_interval",
                        default=config_entry.options.get("refresh_interval", DEFAULT_REFRESH_INTERVAL),
                    ): int,
                    vol.Optional(
                        "lunch_break_time",
                        default=config_entry.options.get("lunch_break_time", DEFAULT_LUNCH_BREAK_TIME),
                    ): str,
                    vol.Optional(
                        "alarm_offset",
                        default=config_entry.options.get("alarm_offset", DEFAULT_ALARM_OFFSET),
                    ): int,
                    vol.Required(
                        "grades_to_display",
                        default=config_entry.options.get("grades_to_display", DEFAULT_GRADES_TO_DISPLAY),
                    ): vol.All(
                        NumberSelector(
                            NumberSelectorConfig(min=1, max=50, mode=NumberSelectorMode.BOX),
                        ),
                        vol.Coerce(int),
                    ),
                    vol.Optional(
                        "show_all_periods",
                        default=config_entry.options.get("show_all_periods", DEFAULT_SHOW_ALL_PERIODS),
                    ): bool,
                    # Kept out of the setup form: Pronote asks for these only
                    # when it re-runs its two-factor check, and the defaults
                    # are right for nearly every account.
                    vol.Optional(
                        "device_name",
                        default=config_entry.options.get(
                            "device_name", config_entry.data.get("device_name", DEFAULT_DEVICE_NAME)
                        ),
                    ): str,
                    vol.Optional(
                        "account_pin",
                        default=config_entry.options.get("account_pin", ""),
                    ): str,
                }
            ),
        )
