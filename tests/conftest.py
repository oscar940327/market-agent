import pytest


@pytest.fixture(autouse=True)
def disable_real_alert_email(monkeypatch):
    monkeypatch.setenv("ALERT_EMAIL_ENABLED", "false")
