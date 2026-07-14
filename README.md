# FleetPulse Intelligence

FleetPulse is a multi-tenant fleet maintenance and operations platform. It provides a foundation for auditable vehicle inspections, defect handling, maintenance scheduling, and repair workflows. The current application includes organization-scoped authentication, rotating refresh tokens, fixed role-based permissions, and tenant-isolated vehicle management with immutable status history.

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

## Migrate and seed the demo fleet

Set a local-only demo password in `.env`, then run the migration and seed commands:

```bash
DEMO_USER_PASSWORD='choose-a-local-password' make migrate seed
```

The seed is idempotent and creates owner, manager, driver, and mechanic accounts plus four operational vehicle records under the `demo-fleet` organization. Sign in through the web application with the manager account to create vehicles, search the fleet, record odometer changes, and manage status transitions.

Authentication behavior is documented in `docs/api/authentication.md`; vehicle permissions, version handling, and lifecycle errors are documented in `docs/api/vehicles.md`.

## Development checks

```bash
make install
make check
```

Architecture decisions live in `docs/adr`.
