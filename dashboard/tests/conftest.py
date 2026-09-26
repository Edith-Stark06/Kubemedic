"""The dashboard's own tests exercise the mock adapter on purpose."""
import pytest


@pytest.fixture(autouse=True)
def _allow_mock_adapter(monkeypatch):
    monkeypatch.setenv("KUBEMEDIC_DASHBOARD_MOCK", "true")
