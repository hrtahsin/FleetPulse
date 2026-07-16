import { afterEach, describe, expect, it, vi } from "vitest";

import {
  addWorkOrderCostItem,
  canManageVehicles,
  createMember,
  createVehicle,
  FleetApiError,
  evaluateMaintenanceSchedules,
  getDashboardSummary,
  listAuditEvents,
  listDefects,
  listMaintenanceRules,
  listVehicles,
  listWorkOrders,
  markAllNotificationsRead,
  submitInspection,
  transitionWorkOrder,
  updateDefect,
  updateMember,
  vehicleStatusLabels,
} from "./fleet-api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fleet API client", () => {
  it("derives management capability from the fixed role matrix", () => {
    expect(canManageVehicles("owner")).toBe(true);
    expect(canManageVehicles("manager")).toBe(true);
    expect(canManageVehicles("driver")).toBe(false);
    expect(canManageVehicles("mechanic")).toBe(false);
  });

  it("sends tenant-neutral filters and bearer authentication", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      response({
        items: [],
        next_cursor: null,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await listVehicles("access-token", {
      status: "maintenance_due",
      query: "service van",
      cursor: "opaque-cursor",
    });

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain(
      "/vehicles?limit=25&status=maintenance_due&q=service+van&cursor=opaque-cursor",
    );
    expect(new Headers(init.headers).get("Authorization")).toBe(
      "Bearer access-token",
    );
    expect(url).not.toContain("organization");
  });

  it("preserves the API error code and request reference", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        response(
          {
            error: {
              code: "VEHICLE_ALREADY_EXISTS",
              message: "A vehicle with that unit number or VIN already exists.",
              request_id: "request-123",
            },
          },
          409,
        ),
      ),
    );

    const request = createVehicle("access-token", {
      unit_number: "FP-101",
      make: "Ford",
      model: "Transit",
      model_year: 2024,
      odometer_km: "100.0",
    });

    await expect(request).rejects.toMatchObject({
      status: 409,
      code: "VEHICLE_ALREADY_EXISTS",
      requestId: "request-123",
    } satisfies Partial<FleetApiError>);
  });

  it("submits inspections with authentication and an idempotency key", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      response({
        id: "inspection-1",
        vehicle_id: "vehicle-1",
        odometer_km: "41200.0",
        status: "submitted",
        submitted_at: "2026-07-14T12:00:00Z",
        replayed: false,
        defects: [],
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await submitInspection("driver-token", "inspection-request-1", {
      vehicle_id: "vehicle-1",
      template_id: "template-1",
      odometer_km: "41200.0",
      responses: [
        {
          template_item_id: "item-1",
          result: "pass",
        },
      ],
    });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = new Headers(init.headers);
    expect(url).toContain("/inspections");
    expect(init.method).toBe("POST");
    expect(headers.get("Authorization")).toBe("Bearer driver-token");
    expect(headers.get("Idempotency-Key")).toBe("inspection-request-1");
  });

  it("loads open defects without exposing tenant identifiers", async () => {
    const fetchMock = vi.fn().mockResolvedValue(response({ items: [] }));
    vi.stubGlobal("fetch", fetchMock);

    await listDefects("manager-token");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/defects?limit=50&status=open");
    expect(url).not.toContain("organization");
    expect(new Headers(init.headers).get("Authorization")).toBe(
      "Bearer manager-token",
    );
  });

  it("uses tenant-derived dashboard, audit, safety, and member administration routes", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response({ generated_at: "2026-07-14T12:00:00Z" }))
      .mockResolvedValueOnce(response({ items: [] }))
      .mockResolvedValueOnce(response({ id: "defect-1", status: "triaged" }))
      .mockResolvedValueOnce(response({ updated: 4 }))
      .mockResolvedValueOnce(response({ membership_id: "member-1" }))
      .mockResolvedValueOnce(response({ membership_id: "member-1", is_active: false }));
    vi.stubGlobal("fetch", fetchMock);

    await getDashboardSummary("manager-token");
    await listAuditEvents("manager-token", { entityType: "defect", limit: 30 });
    await updateDefect("manager-token", "defect-1", {
      status: "triaged",
      resolution_note: "Reviewed",
    });
    await markAllNotificationsRead("manager-token");
    await createMember("manager-token", {
      email: "driver@example.com",
      display_name: "Demo Driver",
      role: "driver",
      temporary_password: "temporary-passphrase",
    });
    await updateMember("manager-token", "member-1", { is_active: false });

    const calls = fetchMock.mock.calls as [string, RequestInit][];
    expect(calls[0][0]).toContain("/dashboard/summary");
    expect(calls[1][0]).toContain("/audit-events?limit=30&entity_type=defect");
    expect(calls[2][0]).toContain("/defects/defect-1");
    expect(calls[2][1].method).toBe("PATCH");
    expect(calls[3][0]).toContain("/notifications/read-all");
    expect(calls[4][0]).toContain("/members");
    expect(calls[4][1].method).toBe("POST");
    expect(calls[5][0]).toContain("/members/member-1");
    expect(calls.every(([url]) => !url.includes("organization"))).toBe(true);
  });

  it("loads maintenance rules and triggers tenant-neutral evaluation", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response({ items: [] }))
      .mockResolvedValueOnce(
        response({ created: 1, updated: 0, due: 1, overdue: 0, schedules: [] }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await listMaintenanceRules("manager-token");
    await evaluateMaintenanceSchedules("manager-token");

    const [listUrl] = fetchMock.mock.calls[0] as [string, RequestInit];
    const [evaluateUrl, evaluateInit] = fetchMock.mock.calls[1] as [
      string,
      RequestInit,
    ];
    expect(listUrl).toContain("/maintenance-rules");
    expect(evaluateUrl).toContain("/maintenance-schedules/evaluate");
    expect(evaluateInit.method).toBe("POST");
    expect(listUrl).not.toContain("organization");
  });

  it("uses versioned tenant-neutral work-order mutations", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response({ items: [] }))
      .mockResolvedValueOnce(response({ id: "order-1", version: 4 }))
      .mockResolvedValueOnce(
        response({
          item: { id: "cost-1" },
          work_order: { id: "order-1", version: 5 },
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await listWorkOrders("mechanic-token");
    await transitionWorkOrder("mechanic-token", "order-1", {
      version: 3,
      status: "in_progress",
      note: "Diagnosis started",
    });
    await addWorkOrderCostItem("mechanic-token", "order-1", {
      version: 4,
      kind: "labour",
      description: "Diagnosis",
      quantity: "1.50",
      unit_cost: "95.00",
    });

    const [listUrl] = fetchMock.mock.calls[0] as [string, RequestInit];
    const [transitionUrl, transitionInit] = fetchMock.mock.calls[1] as [
      string,
      RequestInit,
    ];
    const [costUrl, costInit] = fetchMock.mock.calls[2] as [
      string,
      RequestInit,
    ];
    expect(listUrl).toContain("/work-orders?limit=50");
    expect(transitionUrl).toContain("/work-orders/order-1/transitions");
    expect(transitionInit.method).toBe("POST");
    expect(JSON.parse(String(transitionInit.body))).toMatchObject({
      version: 3,
    });
    expect(costUrl).toContain("/work-orders/order-1/cost-items");
    expect(JSON.parse(String(costInit.body))).toMatchObject({ version: 4 });
    expect(listUrl).not.toContain("organization");
  });

  it("provides readable labels for every API status", () => {
    expect(Object.keys(vehicleStatusLabels)).toHaveLength(6);
    expect(vehicleStatusLabels.out_of_service).toBe("Out of service");
    expect(vehicleStatusLabels.maintenance_due).toBe("Maintenance due");
  });
});

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
