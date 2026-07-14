import pytest
from pydantic import ValidationError

from fleetpulse.shared.config import Settings


def test_default_access_token_ttl_is_short_lived() -> None:
    assert Settings(_env_file=None).access_token_ttl_minutes == 15  # type: ignore[call-arg]


def test_production_rejects_development_jwt_secret() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production")  # type: ignore[call-arg]
