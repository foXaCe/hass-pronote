"""Config flow for Pronote integration."""

from __future__ import annotations

import logging
import uuid
from typing import Any

import pronotepy
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig
from pronotepy.ent import *  # noqa: F403

from .api import (
    AuthenticationError,
    PronoteAPIClient,
)
from .const import (
    DEFAULT_ALARM_OFFSET,
    DEFAULT_LUNCH_BREAK_TIME,
    DEFAULT_REFRESH_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def get_ent_list() -> list[str]:
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

STEP_USER_DATA_SCHEMA_UP = vol.Schema(
    {
        vol.Required("account_type"): ACCOUNT_TYPE_SELECTOR,
        vol.Required("url"): str,
        vol.Required("username"): str,
        vol.Required("password"): str,
        vol.Optional("ent"): vol.In(get_ent_list()),
    }
)

STEP_USER_DATA_SCHEMA_QR = vol.Schema(
    {
        vol.Required("account_type"): ACCOUNT_TYPE_SELECTOR,
        vol.Required("qr_code_json"): str,
        vol.Required("qr_code_pin"): str,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Pronote."""

    VERSION = 2
    pronote_client = None

    def __init__(self) -> None:
        self._user_inputs: dict = {}
        self._api_client = PronoteAPIClient()

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Handle a flow initialized by the user."""
        _LOGGER.debug("Setup process initiated by user.")

        return self.async_show_menu(
            step_id="user",
            menu_options=["username_password_login", "qr_code_login"],
        )

    async def async_step_username_password_login(self, user_input: dict | None = None) -> FlowResult:
        """Handle username/password login step."""
        _LOGGER.info("async_step_up: Connecting via user/password")
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                _LOGGER.debug("User Input: %s", user_input)
                self._user_inputs.update(user_input)
                self._user_inputs["connection_type"] = "username_password"

                # Use the new API client
                await self._api_client.authenticate("username_password", self._user_inputs)
                client = self._api_client._client  # Access internal client for compatibility

                if client is None:
                    raise InvalidAuth
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception as err:
                _LOGGER.error("Unexpected error during auth: %s", err)
                errors["base"] = "invalid_auth"
            else:
                self.pronote_client = client

                if self._user_inputs["account_type"] == "parent":
                    _LOGGER.debug("_User Inputs UP Parent: %s", self._user_inputs)
                    return await self.async_step_parent()

                return await self.async_step_nickname()

        return self.async_show_form(
            step_id="username_password_login",
            data_schema=STEP_USER_DATA_SCHEMA_UP,
            errors=errors,
        )

    async def async_step_qr_code_login(self, user_input: dict | None = None) -> FlowResult:
        """Handle QR code login step."""
        _LOGGER.info("async_step_up: Connecting via qrcode")
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                _LOGGER.debug("User Input: %s", user_input)
                self._user_inputs.update(user_input)
                self._user_inputs["connection_type"] = "qrcode"
                self._user_inputs["qr_code_uuid"] = str(uuid.uuid4())

                # Use the new API client
                await self._api_client.authenticate("qrcode", self._user_inputs)
                client = self._api_client._client  # Access internal client for compatibility
                creds = self._api_client._credentials

                if client is None:
                    raise InvalidAuth
            except AuthenticationError:
                errors["base"] = "invalid_auth"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception as err:
                _LOGGER.error("Unexpected error during QR auth: %s", err)
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
            data_schema=STEP_USER_DATA_SCHEMA_QR,
            errors=errors,
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
        _LOGGER.debug("Parent Input UP: %s", self._user_inputs)
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
                options={"nickname": self._user_inputs["nickname"]},
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
        # Reset API client for fresh auth
        self._api_client = PronoteAPIClient()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict | None = None) -> FlowResult:
        """Handle reauth confirmation."""
        errors: dict[str, str] = {}

        if user_input is not None:
            connection_type = self._user_inputs.get("connection_type", "username_password")

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
                except (AuthenticationError, InvalidAuth, Exception):
                    errors["base"] = "invalid_auth"
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
                except (AuthenticationError, InvalidAuth, Exception):
                    errors["base"] = "invalid_auth"
                else:
                    return self.async_update_reload_and_abort(
                        self._get_reauth_entry(),
                        data=self._user_inputs,
                    )

        connection_type = self._user_inputs.get("connection_type", "username_password")
        if connection_type == "qrcode":
            schema = vol.Schema(
                {
                    vol.Required("qr_code_json"): str,
                    vol.Required("qr_code_pin"): str,
                }
            )
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
                }
            ),
        )
