# Authentication API

Base path: `/api/v1`.

## Demo identities

The idempotent seed command creates these users in the `demo-fleet` organization:

| Role | Email |
|---|---|
| Owner | `owner@demo.fleetpulse.example.com` |
| Manager | `manager@demo.fleetpulse.example.com` |
| Driver | `driver@demo.fleetpulse.example.com` |
| Mechanic | `mechanic@demo.fleetpulse.example.com` |

Their password comes exclusively from the local `DEMO_USER_PASSWORD` environment variable and is never stored in the repository.

## Endpoints

- `POST /auth/login` accepts email and password and returns a short-lived access token plus an opaque refresh token.
- `POST /auth/refresh` rotates the refresh token. Reusing an already rotated token revokes its entire token family.
- `POST /auth/logout` revokes the supplied refresh token and is idempotent.
- `GET /me` requires `Authorization: Bearer <access-token>` and returns the active server-side membership and organization context.

Access tokens expire after 15 minutes by default. Refresh tokens expire after 30 days by default and are stored only as SHA-256 hashes. Passwords use Argon2id. Organization context is derived from the authenticated membership; client-supplied tenant headers are ignored.

Authentication and validation failures use the standard error envelope and include the response `X-Request-ID` value.
