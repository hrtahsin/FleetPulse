# Maintenance rules and schedules

Maintenance routes derive the organization from the authenticated membership and never accept a
tenant identifier from the client. Owners and managers can manage rules and run an evaluation.
Owners, managers, and mechanics can read schedules. Drivers cannot access these routes.

## Rules

- `GET /api/v1/maintenance-rules`
- `POST /api/v1/maintenance-rules`
- `PATCH /api/v1/maintenance-rules/{rule_id}`

A rule may apply to every non-retired vehicle or one vehicle. It must define a positive
`interval_km`, `interval_days`, or both. Vehicle references are tenant-bound; unknown and
cross-tenant identifiers return the same `404 VEHICLE_NOT_FOUND` response.

## Evaluation

- `GET /api/v1/maintenance-schedules?status=due`
- `POST /api/v1/maintenance-schedules/evaluate`

The evaluator upserts one schedule for each vehicle/rule pair. A schedule becomes `due` when it is
within 30 days or 1,000 km of either threshold and `overdue` only after a threshold has passed.
Repeated evaluation updates the same schedules and does not duplicate audit, outbox, or manager
notification records. Active rule rows are locked for the transaction so manual and worker runs do
not race each other.

The background worker runs the same evaluator every day at 05:00 UTC for every organization with
an active rule. Managers can also trigger it from the maintenance workspace. A transition to `due`
or `overdue` creates an audit event, an outbox event, and notifications for active owners and
managers in the same transaction.

## Demo data

The idempotent demo seed creates fleet-wide engine-oil and annual-safety rules. Run the seed after
the database migration, then select **Evaluate now** in the manager workspace to populate the
schedules immediately.
