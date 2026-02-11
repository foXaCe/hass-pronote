"""Tests for the Pronote repairs module."""

from unittest.mock import MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pronote.const import DOMAIN
from custom_components.pronote.repairs import (
    ISSUE_TYPE_CONNECTION_ERROR,
    ISSUE_TYPE_RATE_LIMITED,
    ISSUE_TYPE_SESSION_EXPIRED,
    async_create_connection_error_issue,
    async_create_rate_limited_issue,
    async_create_session_expired_issue,
    async_delete_all_issues,
    async_delete_issue_for_entry,
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
