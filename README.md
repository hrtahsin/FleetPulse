# FleetPulse Intelligence

FleetPulse is a multi-tenant fleet maintenance and operations platform. It provides a foundation for auditable vehicle inspections, defect handling, maintenance scheduling, and repair workflows. The API includes organization-scoped authentication with rotating refresh tokens and fixed role-based permissions.

## Prerequisites

- Docker with Compose, or Python 3.12+, `uv`, Node.js 22+, and `pnpm`

## Start locally

```bash
cp .env.example .env
docker compose up --build
```

- Web: http://localhost:3000
- API: http://localhost:8000
- API docs: http://localhost:8000/docs
- Liveness: http://localhost:8000/api/v1/health/live
- Readiness: http://localhost:8000/api/v1/health/ready

## Migrate and seed demo identities

Set a local-only demo password in `.env`, then run the migration and seed commands:

```bash
DEMO_USER_PASSWORD='choose-a-local-password' make migrate seed
```

The seed is idempotent and creates owner, manager, driver, and mechanic accounts under the `demo-fleet` organization. Account addresses and authentication behavior are documented in `docs/api/authentication.md`.

## Development checks

```bash
make install
make check
```

Architecture decisions live in `docs/adr`.
