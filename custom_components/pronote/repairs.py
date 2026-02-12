"""Repairs support for the Pronote integration.

Provides user-facing repairs for recoverable errors:
- Session expiration (re-authentication required)
- Rate limiting (temporary backoff)
- Connection issues (network instability)
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant import data_entry_flow
from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.issue_registry import (
    async_create_issue,
    async_delete_issue,
)

from .const import DOMAIN, PronoteConfigEntry

_LOGGER = logging.getLogger(__name__)

ISSUE_TYPE_SESSION_EXPIRED = "session_expired"
ISSUE_TYPE_RATE_LIMITED = "rate_limited"
ISSUE_TYPE_CONNECTION_ERROR = "connection_error"


@callback
def async_create_session_expired_issue(
    hass: HomeAssistant,
    entry: PronoteConfigEntry,
) -> None:
    """Create a repair issue for expired session requiring re-authentication."""
    async_create_issue(
        hass,
        DOMAIN,
        f"{ISSUE_TYPE_SESSION_EXPIRED}_{entry.entry_id}",
        is_fixable=True,
        is_persistent=True,
        learn_more_url="https://github.com/delphiki/hass-pronote#re-authentication",
        severity="error",
        translation_key=ISSUE_TYPE_SESSION_EXPIRED,
        translation_placeholders={
            "child_name": entry.title,
        },
        data={"entry_id": entry.entry_id},
    )


@callback
def async_create_rate_limited_issue(
    hass: HomeAssistant,
    entry: PronoteConfigEntry,
    retry_after: int | None = None,
) -> None:
    """Create a repair issue for rate limiting (HTTP 429).

    This is a transient issue that will be automatically resolved
    when the rate limit period expires.
    """
    placeholders: dict[str, Any] = {"child_name": entry.title}
    if retry_after:
        placeholders["retry_after"] = str(retry_after)

    async_create_issue(
        hass,
        DOMAIN,
        f"{ISSUE_TYPE_RATE_LIMITED}_{entry.entry_id}",
        is_fixable=False,
        is_persistent=False,
        severity="warning",
        translation_key=ISSUE_TYPE_RATE_LIMITED,
        translation_placeholders=placeholders,
        data={
            "entry_id": entry.entry_id,
            "retry_after": retry_after,
        },
    )


@callback
def async_create_connection_error_issue(
    hass: HomeAssistant,
    entry: PronoteConfigEntry,
    error_message: str | None = None,
) -> None:
    """Create a repair issue for connection errors.

    This is a transient issue for network instability.
    """
    placeholders: dict[str, Any] = {"child_name": entry.title}
    if error_message:
        placeholders["error"] = error_message

    async_create_issue(
        hass,
        DOMAIN,
        f"{ISSUE_TYPE_CONNECTION_ERROR}_{entry.entry_id}",
        is_fixable=False,
        is_persistent=False,
        severity="warning",
        translation_key=ISSUE_TYPE_CONNECTION_ERROR,
        translation_placeholders=placeholders,
        data={"entry_id": entry.entry_id},
    )


@callback
def async_delete_issue_for_entry(
    hass: HomeAssistant,
    entry: PronoteConfigEntry,
    issue_type: str,
) -> None:
    """Delete a repair issue for a config entry."""
    async_delete_issue(hass, DOMAIN, issue_id=f"{issue_type}_{entry.entry_id}")


@callback
def async_delete_all_issues(
    hass: HomeAssistant,
    entry: PronoteConfigEntry,
) -> None:
    """Delete all repair issues for a config entry."""
    for issue_type in (
        ISSUE_TYPE_SESSION_EXPIRED,
        ISSUE_TYPE_RATE_LIMITED,
        ISSUE_TYPE_CONNECTION_ERROR,
    ):
        async_delete_issue(hass, DOMAIN, issue_id=f"{issue_type}_{entry.entry_id}")


class PronoteSessionExpiredRepairFlow(RepairsFlow):
    """Handler for session expired repair flow."""

    def __init__(self, issue_id: str, data: dict[str, Any] | None) -> None:
        """Initialize the repair flow."""
        super().__init__(issue_id, data)
        self._entry_id = data.get("entry_id") if data else None

    async def async_step_init(self, user_input: dict[str, str] | None = None) -> data_entry_flow.FlowResult:
        """Handle the initial step - redirect to reauth."""
        if self._entry_id is None:
            return self.async_abort(reason="no_entry")

        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None:
            return self.async_abort(reason="entry_not_found")

        # Redirect to the re-authentication flow
        return await self.async_step_reauth()

    async def async_step_reauth(self, user_input: dict[str, str] | None = None) -> data_entry_flow.FlowResult:
        """Handle re-authentication."""
        if user_input is None:
            # Show confirmation form
            return self.async_show_form(
                step_id="reauth",
                description_placeholders={
                    "child_name": self.issue_id.split("_")[-1],
                },
            )

        # Start the actual reauth flow
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None:
            return self.async_abort(reason="entry_not_found")

        try:
            result = await entry.start_reauth_flow(self.hass)
            if result.get("type") == data_entry_flow.FlowResultType.ABORT:
                if result.get("reason") == "reauth_successful":
                    # Delete the issue since it's fixed
                    return self.async_create_fix_result()
            return result
        except HomeAssistantError as err:
            _LOGGER.error("Re-authentication failed: %s", err)
            return self.async_abort(reason="reauth_failed")

    async def async_step_confirm(self, user_input: dict[str, str] | None = None) -> data_entry_flow.FlowResult:
        """Confirm the repair."""
        return self.async_create_fix_result()


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, Any] | None,
) -> RepairsFlow:
    """Create a repair flow for the given issue."""
    if issue_id.startswith(f"{ISSUE_TYPE_SESSION_EXPIRED}_"):
        return PronoteSessionExpiredRepairFlow(issue_id, data)

    # Other issue types are not fixable by the user (transient)
    raise HomeAssistantError(f"Issue {issue_id} is not fixable")


@callback
def async_register_repairs(hass: HomeAssistant) -> None:
    """Register the repairs platform."""
    # This function is called by async_setup_entry
    # Repairs are created dynamically when errors occur
    pass
