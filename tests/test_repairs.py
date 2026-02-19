"""Tests for the Pronote repairs module."""

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pronote.const import DOMAIN
from custom_components.pronote.repairs import (
    ISSUE_TYPE_CONNECTION_ERROR,
    ISSUE_TYPE_RATE_LIMITED,
    ISSUE_TYPE_SESSION_EXPIRED,
    PronoteSessionExpiredRepairFlow,
    async_create_connection_error_issue,
    async_create_fix_flow,
    async_create_rate_limited_issue,
    async_create_session_expired_issue,
    async_delete_all_issues,
    async_delete_issue_for_entry,
    async_register_repairs,
)


@pytest.fixture
def mock_entry():
    """Return a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Jean Dupont",
        data={"account_type": "eleve"},
        entry_id="test_entry_id",
    )


async def test_create_session_expired_issue(hass, mock_entry):
    """Test creating a session expired issue."""
    with patch("custom_components.pronote.repairs.async_create_issue") as mock_create:
        async_create_session_expired_issue(hass, mock_entry)

        mock_create.assert_called_once()
        call_args = mock_create.call_args
        assert call_args[0][0] == hass
        assert call_args[0][1] == DOMAIN
        assert ISSUE_TYPE_SESSION_EXPIRED in call_args[0][2]
        assert call_args[1]["is_fixable"] is True
        assert call_args[1]["is_persistent"] is True
        assert call_args[1]["severity"] == "error"


async def test_create_rate_limited_issue(hass, mock_entry):
    """Test creating a rate limited issue."""
    with patch("custom_components.pronote.repairs.async_create_issue") as mock_create:
        async_create_rate_limited_issue(hass, mock_entry, retry_after=60)

        mock_create.assert_called_once()
        call_args = mock_create.call_args
        assert call_args[0][0] == hass
        assert call_args[0][1] == DOMAIN
        assert ISSUE_TYPE_RATE_LIMITED in call_args[0][2]
        assert call_args[1]["is_fixable"] is False
        assert call_args[1]["is_persistent"] is False
        assert call_args[1]["severity"] == "warning"
        assert call_args[1]["translation_placeholders"]["retry_after"] == "60"


async def test_create_connection_error_issue(hass, mock_entry):
    """Test creating a connection error issue."""
    with patch("custom_components.pronote.repairs.async_create_issue") as mock_create:
        async_create_connection_error_issue(hass, mock_entry, "Network timeout")

        mock_create.assert_called_once()
        call_args = mock_create.call_args
        assert call_args[0][0] == hass
        assert call_args[0][1] == DOMAIN
        assert ISSUE_TYPE_CONNECTION_ERROR in call_args[0][2]
        assert call_args[1]["is_fixable"] is False
        assert call_args[1]["is_persistent"] is False
        assert call_args[1]["severity"] == "warning"


async def test_delete_issue_for_entry(hass, mock_entry):
    """Test deleting an issue for an entry."""
    with patch("custom_components.pronote.repairs.async_delete_issue") as mock_delete:
        async_delete_issue_for_entry(hass, mock_entry, "rate_limited")

        mock_delete.assert_called_once()
        call_kwargs = mock_delete.call_args[1]
        assert "rate_limited_test_entry_id" in call_kwargs["issue_id"]


async def test_delete_all_issues(hass, mock_entry):
    """Test deleting all issues for an entry."""
    with patch("custom_components.pronote.repairs.async_delete_issue") as mock_delete:
        async_delete_all_issues(hass, mock_entry)

        # Should be called for each issue type
        assert mock_delete.call_count == 3
        # Extract issue_ids from kwargs or args
        issue_ids = []
        for call in mock_delete.call_args_list:
            if call.kwargs.get("issue_id"):
                issue_ids.append(call.kwargs["issue_id"])
            elif len(call.args) >= 2:
                issue_ids.append(call.args[1])  # second arg is issue_id
        # Just verify we got 3 calls
        assert len(issue_ids) == 3


class TestPronoteSessionExpiredRepairFlow:
    """Tests for PronoteSessionExpiredRepairFlow."""

    def _create_flow(self, hass, issue_id="session_expired_test_123", data=None):
        """Helper to create a flow with mocked properties."""
        flow = PronoteSessionExpiredRepairFlow()
        flow.hass = hass
        flow.issue_id = issue_id
        flow.data = data
        # Add mocked parent methods
        flow.async_abort = lambda reason: {"type": "abort", "reason": reason}
        flow.async_show_form = lambda **kwargs: {"type": "form", **kwargs}
        flow.async_create_fix_result = lambda: {"type": "create_entry"}
        return flow

    async def test_async_step_init_no_entry_id(self, hass):
        """Test async_step_init aborts when no entry_id."""
        flow = self._create_flow(hass, "session_expired_test", None)

        result = await flow.async_step_init(None)

        assert result["type"] == "abort"
        assert result["reason"] == "no_entry"

    async def test_async_step_init_entry_not_found(self, hass):
        """Test async_step_init aborts when entry not found."""
        flow = self._create_flow(hass, "session_expired_test_123", {"entry_id": "test_123"})

        with patch.object(hass.config_entries, "async_get_entry", return_value=None):
            result = await flow.async_step_init(None)

        assert result["type"] == "abort"
        assert result["reason"] == "entry_not_found"

    async def test_async_step_init_redirects_to_reauth(self, hass):
        """Test async_step_init redirects to reauth step."""
        mock_entry = MagicMock()
        flow = self._create_flow(hass, "session_expired_test_123", {"entry_id": "test_123"})

        # Mock async_step_reauth to avoid actual execution
        with patch.object(flow, "async_step_reauth") as mock_reauth:
            mock_reauth.return_value = {"type": "form", "step_id": "reauth"}
            with patch.object(hass.config_entries, "async_get_entry", return_value=mock_entry):
                result = await flow.async_step_init(None)

        # Should show the form for reauth
        assert result["type"] == "form"
        assert result["step_id"] == "reauth"

    async def test_async_step_reauth_shows_form(self, hass):
        """Test async_step_reauth shows form when no user_input."""
        from unittest.mock import AsyncMock

        flow = self._create_flow(hass, "session_expired_test_123", {"entry_id": "test_123"})

        mock_entry = MagicMock()
        mock_entry.start_reauth_flow = AsyncMock(return_value={"type": "form", "step_id": "reauth"})

        with patch.object(hass.config_entries, "async_get_entry", return_value=mock_entry):
            result = await flow.async_step_reauth(None)

        assert result["type"] == "form"
        assert result["step_id"] == "reauth"

    async def test_async_step_reauth_entry_not_found(self, hass):
        """Test async_step_reauth aborts when entry not found."""
        flow = self._create_flow(hass, "session_expired_test_123", {"entry_id": "test_123"})

        with patch.object(hass.config_entries, "async_get_entry", return_value=None):
            result = await flow.async_step_reauth({})

        assert result["type"] == "abort"
        assert result["reason"] == "entry_not_found"

    async def test_async_step_reauth_successful(self, hass):
        """Test async_step_reauth creates fix result on success."""
        from unittest.mock import AsyncMock

        mock_entry = MagicMock()
        mock_entry.start_reauth_flow = AsyncMock(return_value={"type": "abort", "reason": "reauth_successful"})

        flow = self._create_flow(hass, "session_expired_test_123", {"entry_id": "test_123"})

        # Mock the start_reauth_flow to return a successful abort
        with patch.object(hass.config_entries, "async_get_entry", return_value=mock_entry):
            result = await flow.async_step_reauth({})

        assert result["type"] == "create_entry"

    async def test_async_step_reauth_failed(self, hass):
        """Test async_step_reauth aborts on failure."""
        mock_entry = MagicMock()
        flow = self._create_flow(hass, "session_expired_test_123", {"entry_id": "test_123"})

        with patch.object(hass.config_entries, "async_get_entry", return_value=mock_entry):
            with patch.object(mock_entry, "start_reauth_flow", side_effect=HomeAssistantError("Auth failed")):
                result = await flow.async_step_reauth({})

        assert result["type"] == "abort"
        assert result["reason"] == "reauth_failed"

    async def test_async_step_confirm_creates_fix_result(self, hass):
        """Test async_step_confirm creates fix result."""
        flow = self._create_flow(hass, "session_expired_test_123", {"entry_id": "test_123"})

        result = await flow.async_step_confirm(None)

        assert result["type"] == "create_entry"


async def test_async_create_fix_flow_session_expired(hass):
    """Test async_create_fix_flow creates repair flow for session expired."""
    flow = await async_create_fix_flow(
        hass,
        "session_expired_test_123",
        {"entry_id": "test_123"},
    )
    assert isinstance(flow, PronoteSessionExpiredRepairFlow)


async def test_async_create_fix_flow_not_fixable(hass):
    """Test async_create_fix_flow raises error for non-fixable issues."""
    with pytest.raises(HomeAssistantError, match="is not fixable"):
        await async_create_fix_flow(
            hass,
            "rate_limited_test_123",
            {"entry_id": "test_123"},
        )


async def test_async_register_repairs(hass):
    """Test async_register_repairs does not raise."""
    # This function is a no-op, just verify it doesn't raise
    async_register_repairs(hass)
    # No assertion needed - if it doesn't raise, it passes
