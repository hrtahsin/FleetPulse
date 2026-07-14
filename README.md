# FleetPulse Intelligence

FleetPulse is a multi-tenant fleet maintenance and operations platform. It provides a foundation for auditable vehicle inspections, defect handling, maintenance scheduling, and repair workflows.

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

## Development checks

```bash
make install
make check
```

Architecture decisions live in `docs/adr`.
