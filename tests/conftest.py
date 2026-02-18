import sys
from unittest.mock import MagicMock
import pytest


class _FakeSessionState(dict):
    """Dict that supports both dict-style and attribute-style access, like st.session_state."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        self[name] = value

    def get(self, key, default=None):
        return dict.get(self, key, default)

    def setdefault(self, key, default=None):
        return dict.setdefault(self, key, default)

    def __contains__(self, key):
        return dict.__contains__(self, key)


_fake_st = MagicMock()
_fake_st.session_state = _FakeSessionState()
_fake_st.secrets = {}
sys.modules['streamlit'] = _fake_st


@pytest.fixture(autouse=True)
def reset_streamlit_state():
    """Clear session state and secrets before each test."""
    _fake_st.session_state.clear()
    _fake_st.secrets = {}
    yield
    _fake_st.session_state.clear()
