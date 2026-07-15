class AuthenticationError(Exception):
    """Credentials or tokens could not be authenticated."""


class TokenReuseError(AuthenticationError):
    """A rotated refresh token was presented again."""


class MemberAlreadyExistsError(Exception):
    """The email address is already associated with an account."""


class MemberNotFoundError(Exception):
    """The membership does not exist in the authenticated organization."""


class MemberPermissionError(Exception):
    """The actor cannot manage the requested membership or role."""


class LastOwnerError(Exception):
    """The final active owner cannot be removed or deactivated."""
