import { afterEach, describe, expect, it, vi } from "vitest";

import {
  canManageVehicles,
  createVehicle,
  FleetApiError,
  listDefects,
  listVehicles,
  submitInspection,
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
    expect(url).toContain("/defects?status=open&limit=50");
    expect(url).not.toContain("organization");
    expect(new Headers(init.headers).get("Authorization")).toBe(
      "Bearer manager-token",
    );
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
