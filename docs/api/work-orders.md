# Work-order lifecycle

Work-order routes derive the organization and currency from the authenticated membership. Owners
and managers can create, assign, edit, and transition every organization work order. Mechanics see
only orders assigned to their membership and can perform operational transitions, add repair notes,
and record labour, part, or other cost items. Drivers cannot access work orders.

## Creation and assignment

- `GET /api/v1/members?role=mechanic`
- `POST /api/v1/work-orders`
- `POST /api/v1/defects/{defect_id}/work-order`

An order must reference exactly one open defect or due/overdue maintenance schedule. Each source
can create only one order. Assigned mechanics must be active mechanic members of the same
organization. Work-order numbers are allocated sequentially while the organization row is locked.

## Reading and editing

- `GET /api/v1/work-orders`
- `GET /api/v1/work-orders/{work_order_id}`
- `PATCH /api/v1/work-orders/{work_order_id}`

Mutable order requests carry the current integer `version`. A stale value returns `409
STALE_VERSION` without overwriting the committed record. Unknown, unassigned, and cross-tenant
records use the same `404 WORK_ORDER_NOT_FOUND` response where applicable.

## Repair records and transitions

- `POST /api/v1/work-orders/{work_order_id}/transitions`
- `POST /api/v1/work-orders/{work_order_id}/notes`
- `POST /api/v1/work-orders/{work_order_id}/cost-items`

The state path is explicit:

```text
reported -> triaged -> approved -> in_progress -> completed -> verified -> closed
                                      |     ^
                                      v     |
                                  waiting_parts
```

Managers may cancel a pre-verification order. Assigned mechanics may move approved work into
progress, waiting-for-parts, or completed states; they cannot verify or close their own repair.
Verification requires a manager note.

Labour items add their quantity to labour hours and quantity multiplied by unit cost to labour cost.
Part items update the parts total. Detailed cost items remain immutable and the detail response
returns the sum of all labour, part, and other items.

## Atomic reconciliation

Starting repair moves the vehicle to `under_repair` and marks a source defect `in_repair`.
Manager verification resolves the source defect or completes the maintenance schedule with the
current odometer baseline. The same transaction then returns the vehicle to the safest valid state:

1. `out_of_service` for another unresolved critical defect;
2. `under_repair` for another active work order;
3. `maintenance_due` for remaining defects or due maintenance;
4. otherwise `available`.

Every creation, status change, repair note, and cost item writes an audit event. Creation and status
changes also write outbox events; assignments and status changes notify relevant active users.
