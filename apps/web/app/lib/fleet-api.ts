export type MembershipRole = "owner" | "manager" | "driver" | "mechanic";

export type VehicleStatus =
  | "available"
  | "in_service"
  | "maintenance_due"
  | "under_repair"
  | "out_of_service"
  | "retired";

export interface Identity {
  id: string;
  email: string;
  display_name: string;
  membership_id: string;
  role: MembershipRole;
  organization: {
    id: string;
    name: string;
    slug: string;
    timezone: string;
    default_currency: string;
  };
}

export interface Vehicle {
  id: string;
  unit_number: string;
  vin: string | null;
  registration: string | null;
  make: string;
  model: string;
  model_year: number;
  fuel_type: string | null;
  odometer_km: string;
  status: VehicleStatus;
  version: number;
  created_at: string;
  updated_at: string;
  retired_at: string | null;
}

export interface VehiclePage {
  items: Vehicle[];
  next_cursor: string | null;
}

export interface VehicleCreateInput {
  unit_number: string;
  vin?: string;
  registration?: string;
  make: string;
  model: string;
  model_year: number;
  fuel_type?: string;
  odometer_km: string;
}

export interface VehicleUpdateInput {
  version: number;
  odometer_km: string;
  status: VehicleStatus;
  status_reason?: string;
}

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_at: string;
}

interface ErrorEnvelope {
  error?: {
    code?: string;
    message?: string;
    request_id?: string;
  };
}

export class FleetApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly requestId?: string,
  ) {
    super(message);
    this.name = "FleetApiError";
  }
}

const apiUrl =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export async function login(
  email: string,
  password: string,
): Promise<TokenResponse> {
  return request<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function getIdentity(accessToken: string): Promise<Identity> {
  return request<Identity>("/me", {}, accessToken);
}

export async function listVehicles(
  accessToken: string,
  filters: { status?: VehicleStatus; query?: string; cursor?: string } = {},
): Promise<VehiclePage> {
  const params = new URLSearchParams({ limit: "25" });
  if (filters.status) params.set("status", filters.status);
  if (filters.query) params.set("q", filters.query);
  if (filters.cursor) params.set("cursor", filters.cursor);
  return request<VehiclePage>(
    `/vehicles?${params.toString()}`,
    {},
    accessToken,
  );
}

export async function createVehicle(
  accessToken: string,
  input: VehicleCreateInput,
): Promise<Vehicle> {
  return request<Vehicle>(
    "/vehicles",
    { method: "POST", body: JSON.stringify(input) },
    accessToken,
  );
}

export async function updateVehicle(
  accessToken: string,
  vehicleId: string,
  input: VehicleUpdateInput,
): Promise<Vehicle> {
  return request<Vehicle>(
    `/vehicles/${vehicleId}`,
    { method: "PATCH", body: JSON.stringify(input) },
    accessToken,
  );
}

async function request<T>(
  path: string,
  init: RequestInit,
  accessToken?: string,
): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body) headers.set("Content-Type", "application/json");
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);

  let response: Response;
  try {
    response = await fetch(`${apiUrl}${path}`, { ...init, headers });
  } catch {
    throw new FleetApiError(
      "FleetPulse could not reach the API.",
      0,
      "NETWORK_ERROR",
    );
  }

  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ErrorEnvelope;
    throw new FleetApiError(
      body.error?.message ?? "The request could not be completed.",
      response.status,
      body.error?.code ?? "REQUEST_FAILED",
      body.error?.request_id,
    );
  }
  return (await response.json()) as T;
}

export function canManageVehicles(role: MembershipRole): boolean {
  return role === "owner" || role === "manager";
}

export const vehicleStatusLabels: Record<VehicleStatus, string> = {
  available: "Available",
  in_service: "In service",
  maintenance_due: "Maintenance due",
  under_repair: "Under repair",
  out_of_service: "Out of service",
  retired: "Retired",
};

export const vehicleStatuses = Object.keys(
  vehicleStatusLabels,
) as VehicleStatus[];
