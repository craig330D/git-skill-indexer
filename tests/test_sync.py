"""Tests for sync module — unit tests with mocked dependencies."""

import json
from unittest.mock import MagicMock, patch

from src.sync import _load_state, _save_state


def test_state_roundtrip(tmp_path):
    """Test state file save and load."""
    state_path = tmp_path / "state.json"

    with patch("src.sync.get_state_path", return_value=state_path):
        original = {"test/repo": {"last_indexed_at": "2026-01-01T00:00:00", "pushed_at": "2026-01-01T00:00:00"}}
        _save_state(original)
        loaded = _load_state()
        assert loaded == original


def test_empty_state(tmp_path):
    """Test loading state when no file exists."""
    state_path = tmp_path / "nonexistent.json"

    with patch("src.sync.get_state_path", return_value=state_path):
        state = _load_state()
        assert state == {}
