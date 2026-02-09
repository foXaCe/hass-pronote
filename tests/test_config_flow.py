"""Tests for the Pronote config flow."""

from unittest.mock import MagicMock, patch

from custom_components.pronote.config_flow import (
    CannotConnect,
    InvalidAuth,
    get_ent_list,
)


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
