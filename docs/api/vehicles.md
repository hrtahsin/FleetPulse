# Vehicle API

Vehicle routes are available below `/api/v1/vehicles` and require a valid bearer access token.
The organization is always derived from the authenticated membership; tenant headers are ignored.

## Permissions

- Owners and managers may create and update vehicles.
- Drivers and mechanics may list vehicles, view a vehicle, and read status history.
- IDs belonging to another organization return the same `404 VEHICLE_NOT_FOUND` response as an
  unknown ID.

## Listing

`GET /vehicles` accepts `limit`, opaque `cursor`, `status`, and `q` parameters. Responses contain
`items` and `next_cursor`. Clients must treat the cursor as opaque.

## Creating and updating

`POST /vehicles` creates a vehicle and its initial `vehicle_created` status-history entry.

`PATCH /vehicles/{vehicle_id}` requires the latest integer `version`. Successful updates increment
the version; stale writes return `409 STALE_VEHICLE_VERSION`. A status change also requires a
short `status_reason`. Illegal status transitions return `409 INVALID_STATUS_TRANSITION`.

Odometer readings use kilometres with one decimal place and may stay the same or increase. Lower
readings return `422 ODOMETER_ROLLBACK`.

## Status history

`GET /vehicles/{vehicle_id}/history` returns newest-first immutable status changes, including the
actor and reason code.
