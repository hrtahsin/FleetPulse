from fleetpulse.shared.config import Settings


def test_default_access_token_ttl_is_short_lived() -> None:
    assert Settings(_env_file=None).access_token_ttl_minutes == 15  # type: ignore[call-arg]
