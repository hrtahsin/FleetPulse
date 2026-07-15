# FleetPulse Intelligence

FleetPulse is a multi-tenant fleet maintenance and operations platform. It provides auditable
vehicle inspections, defect handling, preventive-maintenance scheduling, and repair execution. The current
application includes organization-scoped authentication, rotating refresh tokens, fixed role-based
permissions, tenant-isolated vehicle management with immutable status history, an atomic critical
defect safety loop, date/odometer maintenance evaluation, and a versioned work-order lifecycle
with mechanic assignment, notes, cost totals, and manager verification.

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

The seed is idempotent and creates owner, manager, driver, and mechanic accounts, four operational
vehicles, a pre-shift inspection template, and two maintenance rules under the `demo-fleet`
organization. Sign in through the web application with the manager account to manage vehicles,
review safety defects, define maintenance rules, evaluate schedules, and create assigned work
orders. Mechanics receive an assigned repair queue for recording diagnosis, labour, parts, and
completion. Drivers receive the responsive pre-shift inspection workflow.

API behavior is documented in:

- `docs/api/authentication.md`
- `docs/api/vehicles.md`
- `docs/api/inspections.md`
- `docs/api/maintenance.md`
- `docs/api/work-orders.md`

## Development checks

```bash
make install
make check
```

Architecture decisions live in `docs/adr`.
