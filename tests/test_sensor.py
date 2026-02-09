"""Tests for the Pronote sensor module."""

from custom_components.pronote.sensor import len_or_none


class TestLenOrNone:
    def test_none_returns_none(self):
        assert len_or_none(None) is None

    def test_empty_list(self):
        assert len_or_none([]) == 0

    def test_list_with_items(self):
        assert len_or_none([1, 2, 3]) == 3

    def test_string(self):
        assert len_or_none("hello") == 5
