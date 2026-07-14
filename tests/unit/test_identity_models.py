import fleetpulse.auth.models  # noqa: F401
import fleetpulse.organizations.models  # noqa: F401
from fleetpulse.shared.models import Base


def test_identity_tables_are_registered_with_tenant_constraints() -> None:
    tables = Base.metadata.tables

    assert {"organizations", "users", "organization_memberships", "refresh_tokens"} <= tables.keys()
    membership_columns = set(tables["organization_memberships"].columns.keys())
    refresh_token_columns = set(tables["refresh_tokens"].columns.keys())

    assert {"organization_id", "user_id", "role"} <= membership_columns
    assert {"family_id", "token_hash", "revoked_at", "replaced_by_token_id"} <= (
        refresh_token_columns
    )
