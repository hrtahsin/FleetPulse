# Inspection safety-loop API

Inspection routes use the authenticated organization and never accept tenant identifiers from the
client. A driver may submit and read their own inspections. Owners and managers can read all
organization inspections, while owners, managers, and mechanics can read defects.

## Active template

`GET /api/v1/inspection-templates/active` returns the current ordered checklist and response types.

## Submit an inspection

`POST /api/v1/inspections` requires a unique `Idempotency-Key` header. Repeating the same key and
logical payload returns the original inspection with `200`. Reusing the key with a different payload
returns `409 IDEMPOTENCY_PAYLOAD_MISMATCH`.

Every required template item must be answered. Failed `pass_fail` items require defect details;
passed items cannot include defects. The submitted odometer may stay the same or increase.

Critical defects synchronously move the vehicle to `out_of_service`. The inspection, responses,
defects, vehicle status/history, audit records, manager notifications, and outbox events commit in
one database transaction.

## Query operational records

- `GET /api/v1/inspections`
- `GET /api/v1/inspections/{inspection_id}`
- `GET /api/v1/defects`
- `GET /api/v1/defects/{defect_id}`
- `GET /api/v1/notifications`
- `POST /api/v1/notifications/{notification_id}/read`

Unknown and cross-tenant IDs return the same resource-specific `404` response.
