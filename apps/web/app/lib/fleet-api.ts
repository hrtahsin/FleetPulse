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

export type DefectSeverity = "minor" | "major" | "critical";
export type DefectStatus =
  "open" | "triaged" | "in_repair" | "resolved" | "dismissed";

export interface InspectionTemplateItem {
  id: string;
  code: string;
  label: string;
  category: string;
  response_type: "pass_fail" | "boolean" | "text" | "number";
  required: boolean;
  sort_order: number;
}

export interface InspectionTemplate {
  id: string;
  name: string;
  version: number;
  items: InspectionTemplateItem[];
}

export interface InspectionResponseInput {
  template_item_id: string;
  result: string;
  comment?: string;
  defect?: {
    category: string;
    description: string;
    severity: DefectSeverity;
  };
}

export interface InspectionSubmitInput {
  vehicle_id: string;
  template_id: string;
  odometer_km: string;
  notes?: string;
  responses: InspectionResponseInput[];
}

export interface InspectionDetails {
  id: string;
  vehicle_id: string;
  odometer_km: string;
  status: "submitted" | "reviewed";
  submitted_at: string;
  replayed: boolean;
  defects: Defect[];
}

export interface Defect {
  id: string;
  inspection_id: string;
  vehicle_id: string;
  category: string;
  description: string;
  severity: DefectSeverity;
  status: DefectStatus;
  reported_by_user_id: string;
  resolved_at: string | null;
  resolution_note: string | null;
  created_at: string;
  updated_at: string;
}

export interface Notification {
  id: string;
  type: string;
  title: string;
  body: string;
  entity_type: string | null;
  entity_id: string | null;
  read_at: string | null;
  created_at: string;
}

export type MaintenanceScheduleStatus =
  "upcoming" | "due" | "overdue" | "completed" | "dismissed";

export interface MaintenanceRule {
  id: string;
  name: string;
  vehicle_id: string | null;
  interval_km: string | null;
  interval_days: number | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface MaintenanceSchedule {
  id: string;
  vehicle_id: string;
  maintenance_rule_id: string;
  last_completed_at: string | null;
  last_completed_odometer_km: string | null;
  due_at: string | null;
  due_odometer_km: string | null;
  status: MaintenanceScheduleStatus;
  evaluated_at: string;
  created_at: string;
  updated_at: string;
}

export interface MaintenanceRuleCreateInput {
  name: string;
  vehicle_id?: string;
  interval_km?: string;
  interval_days?: number;
}

export interface Member {
  membership_id: string;
  user_id: string;
  email: string;
  display_name: string;
  role: MembershipRole;
  is_active: boolean;
}

export interface MemberCreateInput {
  email: string;
  display_name: string;
  role: MembershipRole;
  temporary_password: string;
}

export interface MemberUpdateInput {
  display_name?: string;
  role?: MembershipRole;
  is_active?: boolean;
}

export interface DashboardSummary {
  generated_at: string;
  currency: string;
  vehicles: {
    total: number;
    operational: number;
    unavailable: number;
    available: number;
    in_service: number;
    maintenance_due: number;
    under_repair: number;
    out_of_service: number;
    retired: number;
  };
  defects: {
    active: number;
    critical: number;
    triaged: number;
    in_repair: number;
  };
  maintenance: {
    upcoming: number;
    due: number;
    overdue: number;
  };
  work_orders: {
    active: number;
    unassigned: number;
    waiting_parts: number;
    awaiting_verification: number;
    repair_cost_30_days: string;
  };
}

export interface AuditEvent {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  actor: {
    id: string;
    display_name: string;
    email: string;
  } | null;
  before_data: Record<string, unknown> | null;
  after_data: Record<string, unknown> | null;
  request_id: string | null;
  created_at: string;
}

export type WorkOrderPriority = "low" | "normal" | "high" | "critical";
export type WorkOrderStatus =
  | "reported"
  | "triaged"
  | "approved"
  | "in_progress"
  | "waiting_parts"
  | "completed"
  | "verified"
  | "closed"
  | "cancelled";
export type WorkOrderCostKind = "part" | "labour" | "other";

export interface WorkOrder {
  id: string;
  number: number;
  vehicle_id: string;
  source_defect_id: string | null;
  maintenance_schedule_id: string | null;
  title: string;
  description: string;
  priority: WorkOrderPriority;
  status: WorkOrderStatus;
  assigned_mechanic_membership_id: string | null;
  labour_hours: string;
  labour_cost: string;
  parts_cost: string;
  currency: string;
  opened_at: string;
  started_at: string | null;
  completed_at: string | null;
  closed_at: string | null;
  version: number;
  created_by_user_id: string;
  created_at: string;
  updated_at: string;
}

export interface WorkOrderNote {
  id: string;
  author_user_id: string;
  body: string;
  created_at: string;
}

export interface WorkOrderCostItem {
  id: string;
  kind: WorkOrderCostKind;
  description: string;
  quantity: string;
  unit_cost: string;
  created_at: string;
}

export interface WorkOrderDetails extends WorkOrder {
  notes: WorkOrderNote[];
  cost_items: WorkOrderCostItem[];
  total_cost: string;
}

export interface WorkOrderCreateInput {
  source_defect_id?: string;
  maintenance_schedule_id?: string;
  title: string;
  description: string;
  priority: WorkOrderPriority;
  assigned_mechanic_membership_id?: string;
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

export async function getActiveInspectionTemplate(
  accessToken: string,
): Promise<InspectionTemplate> {
  return request<InspectionTemplate>(
    "/inspection-templates/active",
    {},
    accessToken,
  );
}

export async function submitInspection(
  accessToken: string,
  idempotencyKey: string,
  input: InspectionSubmitInput,
): Promise<InspectionDetails> {
  return request<InspectionDetails>(
    "/inspections",
    {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(input),
    },
    accessToken,
  );
}

export async function listDefects(
  accessToken: string,
  filters: { status?: DefectStatus; limit?: number } = { status: "open" },
): Promise<Defect[]> {
  const params = new URLSearchParams({ limit: String(filters.limit ?? 50) });
  if (filters.status) params.set("status", filters.status);
  const result = await request<{ items: Defect[] }>(
    `/defects?${params.toString()}`,
    {},
    accessToken,
  );
  return result.items;
}

export async function updateDefect(
  accessToken: string,
  defectId: string,
  input: { status: DefectStatus; resolution_note?: string },
): Promise<Defect> {
  return request<Defect>(
    `/defects/${defectId}`,
    { method: "PATCH", body: JSON.stringify(input) },
    accessToken,
  );
}

export async function listNotifications(
  accessToken: string,
): Promise<{ items: Notification[]; unread_count: number }> {
  return request<{ items: Notification[]; unread_count: number }>(
    "/notifications?unread_only=true&limit=20",
    {},
    accessToken,
  );
}

export async function markNotificationRead(
  accessToken: string,
  notificationId: string,
): Promise<Notification> {
  return request<Notification>(
    `/notifications/${notificationId}/read`,
    { method: "POST" },
    accessToken,
  );
}

export async function markAllNotificationsRead(
  accessToken: string,
): Promise<{ updated: number }> {
  return request<{ updated: number }>(
    "/notifications/read-all",
    { method: "POST" },
    accessToken,
  );
}

export async function listMaintenanceRules(
  accessToken: string,
): Promise<MaintenanceRule[]> {
  const result = await request<{ items: MaintenanceRule[] }>(
    "/maintenance-rules",
    {},
    accessToken,
  );
  return result.items;
}

export async function createMaintenanceRule(
  accessToken: string,
  input: MaintenanceRuleCreateInput,
): Promise<MaintenanceRule> {
  return request<MaintenanceRule>(
    "/maintenance-rules",
    { method: "POST", body: JSON.stringify(input) },
    accessToken,
  );
}

export async function listMaintenanceSchedules(
  accessToken: string,
): Promise<MaintenanceSchedule[]> {
  const result = await request<{ items: MaintenanceSchedule[] }>(
    "/maintenance-schedules",
    {},
    accessToken,
  );
  return result.items;
}

export async function evaluateMaintenanceSchedules(
  accessToken: string,
): Promise<{ created: number; updated: number; due: number; overdue: number }> {
  return request(
    "/maintenance-schedules/evaluate",
    { method: "POST" },
    accessToken,
  );
}

export async function listMembers(
  accessToken: string,
  role?: MembershipRole,
): Promise<Member[]> {
  const path = role ? `/members?role=${role}` : "/members";
  const result = await request<{ items: Member[] }>(
    path,
    {},
    accessToken,
  );
  return result.items;
}

export async function createMember(
  accessToken: string,
  input: MemberCreateInput,
): Promise<Member> {
  return request<Member>(
    "/members",
    { method: "POST", body: JSON.stringify(input) },
    accessToken,
  );
}

export async function updateMember(
  accessToken: string,
  membershipId: string,
  input: MemberUpdateInput,
): Promise<Member> {
  return request<Member>(
    `/members/${membershipId}`,
    { method: "PATCH", body: JSON.stringify(input) },
    accessToken,
  );
}

export async function getDashboardSummary(
  accessToken: string,
): Promise<DashboardSummary> {
  return request<DashboardSummary>("/dashboard/summary", {}, accessToken);
}

export async function listAuditEvents(
  accessToken: string,
  filters: { entityType?: string; action?: string; limit?: number } = {},
): Promise<AuditEvent[]> {
  const params = new URLSearchParams({ limit: String(filters.limit ?? 50) });
  if (filters.entityType) params.set("entity_type", filters.entityType);
  if (filters.action) params.set("action", filters.action);
  const result = await request<{ items: AuditEvent[] }>(
    `/audit-events?${params.toString()}`,
    {},
    accessToken,
  );
  return result.items;
}

export async function listWorkOrders(
  accessToken: string,
): Promise<WorkOrder[]> {
  const result = await request<{ items: WorkOrder[] }>(
    "/work-orders?limit=50",
    {},
    accessToken,
  );
  return result.items;
}

export async function getWorkOrder(
  accessToken: string,
  workOrderId: string,
): Promise<WorkOrderDetails> {
  return request<WorkOrderDetails>(
    `/work-orders/${workOrderId}`,
    {},
    accessToken,
  );
}

export async function createWorkOrder(
  accessToken: string,
  input: WorkOrderCreateInput,
): Promise<WorkOrder> {
  return request<WorkOrder>(
    "/work-orders",
    { method: "POST", body: JSON.stringify(input) },
    accessToken,
  );
}

export async function transitionWorkOrder(
  accessToken: string,
  workOrderId: string,
  input: { version: number; status: WorkOrderStatus; note?: string },
): Promise<WorkOrder> {
  return request<WorkOrder>(
    `/work-orders/${workOrderId}/transitions`,
    { method: "POST", body: JSON.stringify(input) },
    accessToken,
  );
}

export async function addWorkOrderNote(
  accessToken: string,
  workOrderId: string,
  body: string,
): Promise<WorkOrderNote> {
  return request<WorkOrderNote>(
    `/work-orders/${workOrderId}/notes`,
    { method: "POST", body: JSON.stringify({ body }) },
    accessToken,
  );
}

export async function addWorkOrderCostItem(
  accessToken: string,
  workOrderId: string,
  input: {
    version: number;
    kind: WorkOrderCostKind;
    description: string;
    quantity: string;
    unit_cost: string;
  },
): Promise<{ item: WorkOrderCostItem; work_order: WorkOrder }> {
  return request(
    `/work-orders/${workOrderId}/cost-items`,
    { method: "POST", body: JSON.stringify(input) },
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
