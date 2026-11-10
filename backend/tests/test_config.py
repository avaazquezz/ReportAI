"""The settings never print a secret: not in a traceback, a failed test or a log line that shows
the whole object, nor in a validation error's echo of what it was given."""

import re

import pytest
from pydantic import ValidationError

from app.core.config import Settings

_KEY = "sk-ant-not-a-real-key-0123456789"
_GIVEN = {"POSTGRES_USER": "reportai", "POSTGRES_PASSWORD": "pg-not-a-real-password", "POSTGRES_DB": "d", "SECRET_KEY": "jwt-not-a-real-secret"}


@pytest.fixture(autouse=True)
def _no_real_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    # The test run's environment may hold real keys: none of them may reach a failure message.
    for name in Settings.model_fields:
        if re.search("KEY|SECRET|PASSWORD|TOKEN|DSN", name):
            monkeypatch.delenv(name, raising=False)


def test_printing_the_settings_never_shows_a_secret() -> None:
    settings = Settings(_env_file=None, **_GIVEN, ANTHROPIC_API_KEY=_KEY, SENTRY_DSN="https://abc@o1.ingest.sentry.io/2")  # type: ignore[call-arg]

    shown = repr(settings) + str(settings)

    for secret in (_KEY, "pg-not-a-real-password", "jwt-not-a-real-secret", "abc@o1"):
        assert secret not in shown
    assert "ANTHROPIC_API_KEY='**********'" in shown
    assert "POSTGRES_USER='reportai'" in shown and "ACCESS_TOKEN_EXPIRE_MINUTES=60" in shown  # the rest stays readable
    assert settings.ANTHROPIC_API_KEY == _KEY and "pg-not-a-real-password" in settings.DATABASE_URL  # read as always


def test_a_refused_configuration_does_not_echo_what_it_was_given() -> None:
    with pytest.raises(ValidationError) as refused:
        Settings(_env_file=None, **_GIVEN, ANTHROPIC_API_KEY=_KEY, SIGNUP_ENABLED=True, SINGLE_TENANT=True)  # type: ignore[call-arg]

    assert "SIGNUP_ENABLED=true needs SINGLE_TENANT=false" in str(refused.value)
    # Pydantic shortens a long input from its middle: whatever sits at either end would show.
    assert "input_value" not in str(refused.value)
