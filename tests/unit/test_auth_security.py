import uuid
from datetime import UTC, datetime

import pytest

from fleetpulse.auth.exceptions import AuthenticationError
from fleetpulse.auth.roles import MembershipRole
from fleetpulse.auth.security import PasswordSecurity, generate_refresh_token, hash_refresh_token
from fleetpulse.auth.tokens import AccessTokenCodec
from fleetpulse.shared.config import Settings


def test_argon2_password_hash_verification() -> None:
    security = PasswordSecurity()
    password_hash = security.hash("correct horse battery staple")

    assert password_hash.startswith("$argon2id$")
    assert security.verify("correct horse battery staple", password_hash)
    assert not security.verify("wrong password", password_hash)


def test_refresh_tokens_are_opaque_and_only_hashes_are_stable() -> None:
    first = generate_refresh_token()
    second = generate_refresh_token()

    assert first != second
    assert len(first) >= 60
    assert hash_refresh_token(first) == hash_refresh_token(first)
    assert hash_refresh_token(first) != first


def test_access_token_round_trip_contains_tenant_and_role() -> None:
    settings = Settings(
        _env_file=None,
        jwt_secret="unit-test-secret-with-at-least-32-characters",
    )
    codec = AccessTokenCodec(settings)
    user_id = uuid.uuid4()
    membership_id = uuid.uuid4()
    organization_id = uuid.uuid4()
    now = datetime.now(UTC)

    token, expires_at = codec.encode(
        user_id=user_id,
        membership_id=membership_id,
        organization_id=organization_id,
        role=MembershipRole.MANAGER,
        now=now,
    )
    claims = codec.decode(token)

    assert claims.user_id == user_id
    assert claims.membership_id == membership_id
    assert claims.organization_id == organization_id
    assert claims.role is MembershipRole.MANAGER
    assert claims.expires_at == expires_at


def test_access_token_rejects_wrong_secret() -> None:
    source = AccessTokenCodec(
        Settings(_env_file=None, jwt_secret="source-secret-with-at-least-32-characters")
    )
    verifier = AccessTokenCodec(
        Settings(_env_file=None, jwt_secret="different-secret-with-at-least-32-chars")
    )
    token, _ = source.encode(
        user_id=uuid.uuid4(),
        membership_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        role=MembershipRole.DRIVER,
    )

    with pytest.raises(AuthenticationError):
        verifier.decode(token)
