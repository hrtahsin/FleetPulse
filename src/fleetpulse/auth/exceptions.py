class AuthenticationError(Exception):
    """Credentials or tokens could not be authenticated."""


class TokenReuseError(AuthenticationError):
    """A rotated refresh token was presented again."""
