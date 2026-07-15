# Operations dashboard and administration

All operations routes derive organization scope from the authenticated membership. They never
accept a client-selected organization identifier. Owners and managers can use these endpoints;
drivers and mechanics receive `403 FORBIDDEN` except where notification access is described below.

## Dashboard summary

- `GET /api/v1/dashboard/summary`

The dashboard response is generated from committed tenant records and includes vehicle status,
active and critical defects, due or overdue maintenance, active and unassigned work orders, and
work-order costs recorded during the preceding 30 days. The web workspace refreshes this summary
every 30 seconds and exposes a manual refresh action.

## Audit timeline

- `GET /api/v1/audit-events`

The timeline is ordered newest first and supports exact filters for `entity_type`, `entity_id`,
`action`, and `actor_user_id`, plus a bounded result limit. Actor display details are expanded when
the user still exists. Request IDs remain available for tracing an operational change back to API
logs without exposing data from another organization.

## Member administration

- `GET /api/v1/members`
- `POST /api/v1/members`
- `PATCH /api/v1/members/{membership_id}`

Owners can create and manage every role. Managers can create or manage drivers and mechanics only.
An actor cannot change their own role or activation state, and the last active owner cannot be
deactivated or moved to another role. Deactivation revokes the user's outstanding refresh tokens.
Creation requires a temporary password of at least 12 characters; communicate it through a private
channel and never place it in source control, logs, or audit metadata.

## Defect triage and dismissal

- `GET /api/v1/defects`
- `PATCH /api/v1/defects/{defect_id}`

Owners and managers can move an open defect to `triaged` or dismiss an open/triaged defect with a
required resolution note. A defect linked to an active work order cannot be dismissed. A valid
dismissal records audit and outbox events, notifies the original reporter, and atomically restores
the vehicle to the safest state allowed by remaining defects, maintenance schedules, and work
orders.

## Notifications

- `GET /api/v1/notifications`
- `POST /api/v1/notifications/{notification_id}/read`
- `POST /api/v1/notifications/read-all`

Every authenticated user can read or acknowledge only notifications addressed to their own user ID
inside the active organization. The list response reports the total unread count independently of
the requested page size. Mark-all updates only the caller's unread records and returns the number of
records changed.
