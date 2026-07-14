from enum import StrEnum


class MembershipRole(StrEnum):
    OWNER = "owner"
    MANAGER = "manager"
    DRIVER = "driver"
    MECHANIC = "mechanic"


MANAGEMENT_ROLES = frozenset({MembershipRole.OWNER, MembershipRole.MANAGER})
