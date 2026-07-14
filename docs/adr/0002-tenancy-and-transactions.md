# ADR 0002: Tenant context and transactional invariants

- Status: Accepted
- Date: 2026-07-14

## Decision

Authenticated membership determines organization context. Every tenant-owned repository operation requires that context, and cross-tenant identifiers return 404. Inspection creation, critical-defect handling, vehicle history, audit records, notifications, and outbox events commit in one transaction.
