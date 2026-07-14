# ADR 0001: Modular monolith

- Status: Accepted
- Date: 2026-07-14

## Context

The MVP must deliver an auditable inspection-to-repair workflow in two sprints. Separate services would add deployment and transaction complexity before the domain boundaries are proven.

## Decision

Use one FastAPI application and one PostgreSQL database, with domain modules under `src/fleetpulse`. Celery runs background work from the same package. Business operations that span records use one database transaction and a transactional outbox.

## Consequences

Modules must retain clear service/repository boundaries. Safety-critical state changes remain synchronous. A module can be extracted later if measured operational needs justify it.
