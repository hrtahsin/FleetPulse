"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  addWorkOrderCostItem,
  addWorkOrderNote,
  AuditEvent,
  canManageVehicles,
  createMember,
  createMaintenanceRule,
  createVehicle,
  createWorkOrder,
  DashboardSummary,
  Defect,
  DefectSeverity,
  evaluateMaintenanceSchedules,
  FleetApiError,
  getActiveInspectionTemplate,
  getDashboardSummary,
  getIdentity,
  getWorkOrder,
  Identity,
  InspectionDetails,
  InspectionTemplate,
  listAuditEvents,
  listDefects,
  listMaintenanceRules,
  listMaintenanceSchedules,
  listMembers,
  listNotifications,
  listVehicles,
  listWorkOrders,
  login,
  MaintenanceRule,
  MaintenanceSchedule,
  Member,
  markAllNotificationsRead,
  markNotificationRead,
  Notification,
  submitInspection,
  transitionWorkOrder,
  updateDefect,
  updateMember,
  updateVehicle,
  Vehicle,
  VehicleCreateInput,
  vehicleStatusLabels,
  VehicleStatus,
  vehicleStatuses,
  WorkOrder,
  WorkOrderCostKind,
  WorkOrderDetails,
  WorkOrderPriority,
  WorkOrderStatus,
} from "./lib/fleet-api";

interface Session {
  accessToken: string;
  identity: Identity;
}

export function VehicleWorkspace() {
  const [session, setSession] = useState<Session | null>(null);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<VehicleStatus | "">("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [selectedVehicle, setSelectedVehicle] = useState<Vehicle | null>(null);

  const loadFleet = useCallback(
    async (cursor?: string) => {
      if (!session) return;
      setIsLoading(true);
      setError(null);
      try {
        const page = await listVehicles(session.accessToken, {
          status: statusFilter || undefined,
          query: query || undefined,
          cursor,
        });
        setVehicles((current) =>
          cursor ? [...current, ...page.items] : page.items,
        );
        setNextCursor(page.next_cursor);
      } catch (caught) {
        setError(errorMessage(caught));
      } finally {
        setIsLoading(false);
      }
    },
    [query, session, statusFilter],
  );

  useEffect(() => {
    void loadFleet();
  }, [loadFleet]);

  const metrics = useMemo(() => {
    const unavailable = vehicles.filter((vehicle) =>
      ["under_repair", "out_of_service", "retired"].includes(vehicle.status),
    ).length;
    const due = vehicles.filter(
      (vehicle) => vehicle.status === "maintenance_due",
    ).length;
    return {
      total: vehicles.length,
      available: vehicles.length - unavailable,
      unavailable,
      due,
    };
  }, [vehicles]);

  if (!session) {
    return <LoginView onAuthenticated={setSession} />;
  }

  if (session.identity.role === "driver") {
    return (
      <DriverInspectionWorkspace
        session={session}
        onSignOut={() => setSession(null)}
      />
    );
  }

  const canManage = canManageVehicles(session.identity.role);
  return (
    <main className="workspace-shell">
      <aside className="sidebar">
        <Brand />
        <nav aria-label="Primary navigation">
          <a className="nav-item active" href="#fleet">
            <span>▦</span> Fleet overview
          </a>
          {canManage && (
            <a className="nav-item" href="#dashboard">
              <span>⌁</span> Command dashboard
            </a>
          )}
          <a className="nav-item" href="#safety">
            <span>✓</span> Safety loop
          </a>
          <a className="nav-item" href="#maintenance">
            <span>◇</span> Maintenance
          </a>
          <a className="nav-item" href="#work-orders">
            <span>⚒</span> Work orders
          </a>
          {canManage && (
            <a className="nav-item" href="#operations">
              <span>◎</span> Audit &amp; team
            </a>
          )}
        </nav>
        <div className="tenant-card">
          <span className="tenant-mark">
            {session.identity.organization.name.slice(0, 2)}
          </span>
          <div>
            <strong>{session.identity.organization.name}</strong>
            <small>{session.identity.role}</small>
          </div>
        </div>
      </aside>

      <section className="workspace" id="fleet">
        <header className="topbar">
          <div>
            <p className="section-kicker">Operations / Fleet</p>
            <h1>Vehicle control</h1>
          </div>
          <div className="topbar-actions">
            <span className="user-chip">
              {initials(session.identity.display_name)}
            </span>
            <div className="user-copy">
              <strong>{session.identity.display_name}</strong>
              <small>{session.identity.email}</small>
            </div>
            <button className="text-button" onClick={() => setSession(null)}>
              Sign out
            </button>
          </div>
        </header>

        {canManage ? (
          <ManagementDashboard session={session} />
        ) : (
          <div className="metric-grid" aria-label="Visible fleet summary">
            <Metric label="Visible vehicles" value={metrics.total} accent="blue" />
            <Metric label="Operational" value={metrics.available} accent="green" />
            <Metric label="Maintenance due" value={metrics.due} accent="amber" />
            <Metric label="Unavailable" value={metrics.unavailable} accent="red" />
          </div>
        )}

        <SafetyPanel
          session={session}
          canManage={canManage}
          onFleetChanged={() => loadFleet()}
        />

        {canManage && (
          <MaintenancePanel session={session} vehicles={vehicles} />
        )}

        <WorkOrderPanel
          session={session}
          vehicles={vehicles}
          onFleetChanged={() => loadFleet()}
        />

        {canManage && <OperationsAdminPanel session={session} />}

        <section className="fleet-panel">
          <div className="panel-heading">
            <div>
              <h2>Fleet inventory</h2>
              <p>Current operational state and recorded distance.</p>
            </div>
            {canManage && (
              <button
                className="primary-button"
                onClick={() => setShowCreate(true)}
              >
                + Add vehicle
              </button>
            )}
          </div>

          <form
            className="filters"
            onSubmit={(event) => {
              event.preventDefault();
              setQuery(queryInput.trim());
            }}
          >
            <label className="search-field">
              <span>⌕</span>
              <input
                aria-label="Search vehicles"
                placeholder="Search unit, VIN, make or model"
                value={queryInput}
                onChange={(event) => setQueryInput(event.target.value)}
              />
            </label>
            <select
              aria-label="Filter by status"
              value={statusFilter}
              onChange={(event) =>
                setStatusFilter(event.target.value as VehicleStatus | "")
              }
            >
              <option value="">All statuses</option>
              {vehicleStatuses.map((status) => (
                <option key={status} value={status}>
                  {vehicleStatusLabels[status]}
                </option>
              ))}
            </select>
            <button className="secondary-button" type="submit">
              Apply
            </button>
          </form>

          {error && (
            <div className="error-banner" role="alert">
              <strong>Unable to load fleet.</strong> {error}
            </div>
          )}
          <div className="vehicle-table-wrap">
            <table className="vehicle-table">
              <thead>
                <tr>
                  <th>Vehicle</th>
                  <th>Status</th>
                  <th>Registration</th>
                  <th>Odometer</th>
                  <th>Fuel</th>
                  <th>
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {vehicles.map((vehicle) => (
                  <tr key={vehicle.id}>
                    <td>
                      <div className="vehicle-identity">
                        <span className="vehicle-icon">
                          {vehicle.unit_number.slice(-2)}
                        </span>
                        <div>
                          <strong>{vehicle.unit_number}</strong>
                          <small>
                            {vehicle.model_year} {vehicle.make} {vehicle.model}
                          </small>
                        </div>
                      </div>
                    </td>
                    <td>
                      <span className={`status-pill status-${vehicle.status}`}>
                        {vehicleStatusLabels[vehicle.status]}
                      </span>
                    </td>
                    <td>
                      <strong className="table-primary">
                        {vehicle.registration ?? "—"}
                      </strong>
                      <small className="table-secondary">
                        {vehicle.vin ?? "VIN not recorded"}
                      </small>
                    </td>
                    <td>
                      <strong className="table-primary">
                        {formatOdometer(vehicle.odometer_km)} km
                      </strong>
                      <small className="table-secondary">
                        Version {vehicle.version}
                      </small>
                    </td>
                    <td>{titleCase(vehicle.fuel_type ?? "Not set")}</td>
                    <td>
                      {canManage && (
                        <button
                          className="row-action"
                          aria-label={`Manage ${vehicle.unit_number}`}
                          onClick={() => setSelectedVehicle(vehicle)}
                        >
                          Manage
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!isLoading && vehicles.length === 0 && (
              <div className="empty-state">
                <span>▦</span>
                <h3>No vehicles found</h3>
                <p>
                  Try another filter or add the first vehicle to this fleet.
                </p>
              </div>
            )}
            {isLoading && vehicles.length === 0 && (
              <div className="loading-state">
                <span />
                <span />
                <span />
                <p>Loading fleet records…</p>
              </div>
            )}
          </div>
          {nextCursor && (
            <button
              className="load-more"
              disabled={isLoading}
              onClick={() => void loadFleet(nextCursor)}
            >
              {isLoading ? "Loading…" : "Load more vehicles"}
            </button>
          )}
        </section>
      </section>

      {showCreate && (
        <CreateVehicleDialog
          accessToken={session.accessToken}
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false);
            void loadFleet();
          }}
        />
      )}
      {selectedVehicle && (
        <ManageVehicleDialog
          accessToken={session.accessToken}
          vehicle={selectedVehicle}
          onClose={() => setSelectedVehicle(null)}
          onUpdated={() => {
            setSelectedVehicle(null);
            void loadFleet();
          }}
        />
      )}
    </main>
  );
}

interface ChecklistAnswer {
  result: "" | "pass" | "fail";
  comment: string;
  description: string;
  severity: DefectSeverity;
}

function DriverInspectionWorkspace({
  session,
  onSignOut,
}: {
  session: Session;
  onSignOut: () => void;
}) {
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [template, setTemplate] = useState<InspectionTemplate | null>(null);
  const [vehicleId, setVehicleId] = useState("");
  const [odometer, setOdometer] = useState("");
  const [notes, setNotes] = useState("");
  const [answers, setAnswers] = useState<
    Partial<Record<string, ChecklistAnswer>>
  >({});
  const [idempotencyKey, setIdempotencyKey] = useState(() =>
    crypto.randomUUID(),
  );
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<InspectionDetails | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const [fleet, activeTemplate] = await Promise.all([
          listVehicles(session.accessToken),
          getActiveInspectionTemplate(session.accessToken),
        ]);
        if (!active) return;
        const inspectable = fleet.items.filter((vehicle) =>
          ["available", "in_service", "maintenance_due"].includes(
            vehicle.status,
          ),
        );
        setVehicles(inspectable);
        setTemplate(activeTemplate);
        if (inspectable[0]) {
          setVehicleId(inspectable[0].id);
          setOdometer(inspectable[0].odometer_km);
        }
      } catch (caught) {
        if (active) setError(errorMessage(caught));
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [session.accessToken]);

  const answeredCount = template
    ? template.items.filter((item) => answers[item.id]?.result).length
    : 0;
  const requiredCount =
    template?.items.filter((item) => item.required).length ?? 0;
  const selectedVehicle = vehicles.find((vehicle) => vehicle.id === vehicleId);

  function chooseVehicle(id: string) {
    const selected = vehicles.find((vehicle) => vehicle.id === id);
    setVehicleId(id);
    if (selected) setOdometer(selected.odometer_km);
  }

  function updateAnswer(itemId: string, patch: Partial<ChecklistAnswer>) {
    setAnswers((current) => {
      const existing = current[itemId];
      return {
        ...current,
        [itemId]: {
          ...(existing ?? {
            result: "",
            comment: "",
            description: "",
            severity: "major",
          }),
          ...patch,
        },
      };
    });
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!template || !selectedVehicle) return;
    setSubmitting(true);
    setError(null);
    try {
      const inspection = await submitInspection(
        session.accessToken,
        idempotencyKey,
        {
          vehicle_id: selectedVehicle.id,
          template_id: template.id,
          odometer_km: odometer,
          notes: notes.trim() || undefined,
          responses: template.items.map((item) => {
            const answer = answers[item.id];
            if (!answer)
              throw new Error("Required inspection response is missing.");
            return {
              template_item_id: item.id,
              result: answer.result,
              comment: answer.comment.trim() || undefined,
              ...(answer.result === "fail"
                ? {
                    defect: {
                      category: item.category,
                      description: answer.description.trim(),
                      severity: answer.severity,
                    },
                  }
                : {}),
            };
          }),
        },
      );
      setResult(inspection);
      setIdempotencyKey(crypto.randomUUID());
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <main className="driver-shell driver-loading">
        <Brand />
        <div className="loading-state">
          <span /> <span /> <span /> <p>Preparing your safety checklist…</p>
        </div>
      </main>
    );
  }

  if (result) {
    const critical = result.defects.some(
      (defect) => defect.severity === "critical",
    );
    return (
      <main className="driver-shell result-shell">
        <Brand />
        <section
          className={`inspection-result ${critical ? "critical" : "safe"}`}
        >
          <span className="result-symbol">{critical ? "!" : "✓"}</span>
          <p className="section-kicker">Inspection recorded</p>
          <h1>
            {critical
              ? "Vehicle placed out of service"
              : "Pre-shift check complete"}
          </h1>
          <p>
            {critical
              ? "A critical defect was reported. Fleet management has been notified and this vehicle must not be operated."
              : "Your inspection is safely recorded and the vehicle remains in its current operational state."}
          </p>
          <div className="result-meta">
            <span>
              Inspection <strong>{result.id.slice(0, 8)}</strong>
            </span>
            <span>
              Defects <strong>{result.defects.length}</strong>
            </span>
          </div>
          <button className="primary-button" onClick={() => setResult(null)}>
            Start another inspection
          </button>
        </section>
      </main>
    );
  }

  return (
    <main className="driver-shell">
      <header className="driver-header">
        <Brand />
        <div>
          <span className="user-chip">
            {initials(session.identity.display_name)}
          </span>
          <button className="text-button" onClick={onSignOut}>
            Sign out
          </button>
        </div>
      </header>
      <section className="driver-intro">
        <p className="section-kicker">Driver / Pre-shift</p>
        <h1>Safety starts before the wheels move.</h1>
        <p>Complete every required check. Report exactly what you observe.</p>
      </section>
      {error && (
        <div className="error-banner driver-error" role="alert">
          {error}
        </div>
      )}
      {!template || vehicles.length === 0 ? (
        <section className="empty-state driver-empty">
          <span>!</span>
          <h3>No inspectable vehicle or active checklist</h3>
          <p>Contact a fleet manager before beginning a shift.</p>
        </section>
      ) : (
        <form className="inspection-form" onSubmit={submit}>
          <section className="inspection-setup">
            <label>
              Vehicle
              <select
                value={vehicleId}
                onChange={(event) => chooseVehicle(event.target.value)}
              >
                {vehicles.map((vehicle) => (
                  <option key={vehicle.id} value={vehicle.id}>
                    {vehicle.unit_number} · {vehicle.make} {vehicle.model}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Odometer (km)
              <input
                type="number"
                min={selectedVehicle?.odometer_km}
                step="0.1"
                value={odometer}
                onChange={(event) => setOdometer(event.target.value)}
                required
              />
            </label>
          </section>
          <div className="checklist-heading">
            <div>
              <p className="section-kicker">
                {template.name} · v{template.version}
              </p>
              <h2>Required checks</h2>
            </div>
            <span>
              {answeredCount} / {requiredCount} answered
            </span>
          </div>
          <div className="checklist">
            {template.items.map((item, index) => {
              const answer = answers[item.id];
              return (
                <article
                  className={`check-item ${answer?.result === "fail" ? "failed" : ""}`}
                  key={item.id}
                >
                  <div className="check-copy">
                    <span className="check-number">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <div>
                      <small>{titleCase(item.category)}</small>
                      <h3>{item.label}</h3>
                    </div>
                  </div>
                  <div className="check-actions">
                    <button
                      type="button"
                      className={
                        answer?.result === "pass" ? "selected pass" : "pass"
                      }
                      onClick={() =>
                        updateAnswer(item.id, {
                          result: "pass",
                          description: "",
                        })
                      }
                    >
                      ✓ Pass
                    </button>
                    <button
                      type="button"
                      className={
                        answer?.result === "fail" ? "selected fail" : "fail"
                      }
                      onClick={() => updateAnswer(item.id, { result: "fail" })}
                    >
                      ! Defect
                    </button>
                  </div>
                  {answer?.result === "fail" && (
                    <div className="defect-fields">
                      <label>
                        What did you observe?
                        <textarea
                          value={answer.description}
                          onChange={(event) =>
                            updateAnswer(item.id, {
                              description: event.target.value,
                            })
                          }
                          minLength={3}
                          maxLength={2000}
                          required
                          placeholder="Describe the condition clearly"
                        />
                      </label>
                      <label>
                        Severity
                        <select
                          value={answer.severity}
                          onChange={(event) =>
                            updateAnswer(item.id, {
                              severity: event.target.value as DefectSeverity,
                            })
                          }
                        >
                          <option value="minor">Minor</option>
                          <option value="major">Major</option>
                          <option value="critical">
                            Critical — unsafe to operate
                          </option>
                        </select>
                      </label>
                      <label>
                        Additional note
                        <input
                          value={answer.comment}
                          onChange={(event) =>
                            updateAnswer(item.id, {
                              comment: event.target.value,
                            })
                          }
                          maxLength={2000}
                          placeholder="Optional context"
                        />
                      </label>
                    </div>
                  )}
                </article>
              );
            })}
          </div>
          <label className="inspection-notes">
            Inspection notes
            <textarea
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              maxLength={4000}
              placeholder="Optional overall notes"
            />
          </label>
          <footer className="inspection-submit">
            <div>
              <strong>
                {answeredCount === requiredCount
                  ? "Ready to submit"
                  : `${requiredCount - answeredCount} checks remaining`}
              </strong>
              <small>Submission is time-stamped and auditable.</small>
            </div>
            <button
              className="primary-button"
              disabled={submitting || answeredCount !== requiredCount}
            >
              {submitting ? "Submitting safely…" : "Submit inspection"}
            </button>
          </footer>
        </form>
      )}
    </main>
  );
}

function MaintenancePanel({
  session,
  vehicles,
}: {
  session: Session;
  vehicles: Vehicle[];
}) {
  const [rules, setRules] = useState<MaintenanceRule[]>([]);
  const [schedules, setSchedules] = useState<MaintenanceSchedule[]>([]);
  const [name, setName] = useState("");
  const [vehicleId, setVehicleId] = useState("");
  const [intervalKm, setIntervalKm] = useState("");
  const [intervalDays, setIntervalDays] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [nextRules, nextSchedules] = await Promise.all([
        listMaintenanceRules(session.accessToken),
        listMaintenanceSchedules(session.accessToken),
      ]);
      setRules(nextRules);
      setSchedules(nextSchedules);
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }, [session.accessToken]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function addRule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await createMaintenanceRule(session.accessToken, {
        name: name.trim(),
        vehicle_id: vehicleId || undefined,
        interval_km: intervalKm || undefined,
        interval_days: intervalDays ? Number(intervalDays) : undefined,
      });
      setName("");
      setVehicleId("");
      setIntervalKm("");
      setIntervalDays("");
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function evaluate() {
    setBusy(true);
    setError(null);
    try {
      await evaluateMaintenanceSchedules(session.accessToken);
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  const vehicleLabels = new Map(
    vehicles.map((vehicle) => [vehicle.id, vehicle.unit_number]),
  );
  const ruleLabels = new Map(rules.map((rule) => [rule.id, rule.name]));
  const attention = schedules.filter((schedule) =>
    ["due", "overdue"].includes(schedule.status),
  );

  return (
    <section className="maintenance-panel" id="maintenance">
      <div className="maintenance-heading">
        <div>
          <p className="section-kicker">Preventive maintenance</p>
          <h2>Service schedules</h2>
          <p>Due within 30 days or 1,000 km; overdue after the threshold.</p>
        </div>
        <button
          className="secondary-button"
          disabled={busy || rules.length === 0}
          onClick={() => void evaluate()}
        >
          {busy ? "Working…" : "Evaluate now"}
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="maintenance-grid">
        <form className="maintenance-form" onSubmit={addRule}>
          <h3>Create a rule</h3>
          <label>
            Rule name
            <input
              required
              maxLength={120}
              placeholder="Engine oil service"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <label>
            Applies to
            <select
              value={vehicleId}
              onChange={(event) => setVehicleId(event.target.value)}
            >
              <option value="">All active vehicles</option>
              {vehicles.map((vehicle) => (
                <option key={vehicle.id} value={vehicle.id}>
                  {vehicle.unit_number} · {vehicle.make} {vehicle.model}
                </option>
              ))}
            </select>
          </label>
          <div className="maintenance-intervals">
            <label>
              Every kilometres
              <input
                min="0.1"
                step="0.1"
                type="number"
                value={intervalKm}
                onChange={(event) => setIntervalKm(event.target.value)}
              />
            </label>
            <label>
              Every days
              <input
                max="3650"
                min="1"
                type="number"
                value={intervalDays}
                onChange={(event) => setIntervalDays(event.target.value)}
              />
            </label>
          </div>
          <button
            className="primary-button"
            disabled={busy || (!intervalKm && !intervalDays)}
            type="submit"
          >
            Add maintenance rule
          </button>
        </form>

        <div className="schedule-list">
          <div className="schedule-summary">
            <strong>{attention.length}</strong>
            <span>items need attention</span>
            <small>{rules.length} active and inactive rules</small>
          </div>
          {schedules.map((schedule) => (
            <article key={schedule.id} className="schedule-card">
              <span className={`schedule-state state-${schedule.status}`}>
                {schedule.status}
              </span>
              <div>
                <strong>
                  {ruleLabels.get(schedule.maintenance_rule_id) ??
                    "Maintenance"}
                </strong>
                <small>
                  {vehicleLabels.get(schedule.vehicle_id) ?? "Vehicle"}
                  {schedule.due_odometer_km
                    ? ` · ${formatOdometer(schedule.due_odometer_km)} km`
                    : ""}
                  {schedule.due_at
                    ? ` · ${new Date(schedule.due_at).toLocaleDateString()}`
                    : ""}
                </small>
              </div>
            </article>
          ))}
          {schedules.length === 0 && (
            <div className="maintenance-empty">
              Create a rule, then evaluate schedules to see upcoming service.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

const managerWorkOrderTransitions: Record<WorkOrderStatus, WorkOrderStatus[]> =
  {
    reported: ["triaged", "cancelled"],
    triaged: ["approved", "cancelled"],
    approved: ["in_progress", "cancelled"],
    in_progress: ["waiting_parts", "completed", "cancelled"],
    waiting_parts: ["in_progress", "completed", "cancelled"],
    completed: ["in_progress", "verified"],
    verified: ["closed"],
    closed: [],
    cancelled: [],
  };

const mechanicWorkOrderTransitions: Record<WorkOrderStatus, WorkOrderStatus[]> =
  {
    reported: [],
    triaged: [],
    approved: ["in_progress"],
    in_progress: ["waiting_parts", "completed"],
    waiting_parts: ["in_progress", "completed"],
    completed: [],
    verified: [],
    closed: [],
    cancelled: [],
  };

function WorkOrderPanel({
  session,
  vehicles,
  onFleetChanged,
}: {
  session: Session;
  vehicles: Vehicle[];
  onFleetChanged: () => Promise<void>;
}) {
  const canManage = canManageVehicles(session.identity.role);
  const [orders, setOrders] = useState<WorkOrder[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [details, setDetails] = useState<WorkOrderDetails | null>(null);
  const [defects, setDefects] = useState<Defect[]>([]);
  const [schedules, setSchedules] = useState<MaintenanceSchedule[]>([]);
  const [mechanics, setMechanics] = useState<Member[]>([]);
  const [source, setSource] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState<WorkOrderPriority>("normal");
  const [mechanicId, setMechanicId] = useState("");
  const [transitionNote, setTransitionNote] = useState("");
  const [repairNote, setRepairNote] = useState("");
  const [costKind, setCostKind] = useState<WorkOrderCostKind>("labour");
  const [costDescription, setCostDescription] = useState("");
  const [costQuantity, setCostQuantity] = useState("1.00");
  const [costUnit, setCostUnit] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(
    async (preferredId?: string) => {
      setError(null);
      try {
        const nextOrders = await listWorkOrders(session.accessToken);
        setOrders(nextOrders);
        if (canManage) {
          const [nextDefects, nextSchedules, nextMechanics] = await Promise.all(
            [
              listDefects(session.accessToken),
              listMaintenanceSchedules(session.accessToken),
              listMembers(session.accessToken, "mechanic"),
            ],
          );
          setDefects(nextDefects);
          setSchedules(nextSchedules);
          setMechanics(nextMechanics.filter((member) => member.is_active));
        }
        const targetId =
          preferredId ??
          (selectedId && nextOrders.some((order) => order.id === selectedId)
            ? selectedId
            : nextOrders[0]?.id);
        setSelectedId(targetId ?? null);
        setDetails(
          targetId ? await getWorkOrder(session.accessToken, targetId) : null,
        );
      } catch (caught) {
        setError(errorMessage(caught));
      }
    },
    [canManage, selectedId, session.accessToken],
  );

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function selectOrder(orderId: string) {
    setSelectedId(orderId);
    setError(null);
    try {
      setDetails(await getWorkOrder(session.accessToken, orderId));
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const [sourceType, sourceId] = source.split(":", 2);
    setBusy(true);
    setError(null);
    try {
      const order = await createWorkOrder(session.accessToken, {
        ...(sourceType === "defect"
          ? { source_defect_id: sourceId }
          : { maintenance_schedule_id: sourceId }),
        title: title.trim(),
        description: description.trim(),
        priority,
        assigned_mechanic_membership_id: mechanicId || undefined,
      });
      setSource("");
      setTitle("");
      setDescription("");
      setPriority("normal");
      setMechanicId("");
      await refresh(order.id);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function transition(status: WorkOrderStatus) {
    if (!details) return;
    setBusy(true);
    setError(null);
    try {
      const order = await transitionWorkOrder(session.accessToken, details.id, {
        version: details.version,
        status,
        note: transitionNote.trim() || undefined,
      });
      setTransitionNote("");
      await refresh(order.id);
      await onFleetChanged();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function addNote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!details) return;
    setBusy(true);
    setError(null);
    try {
      await addWorkOrderNote(
        session.accessToken,
        details.id,
        repairNote.trim(),
      );
      setRepairNote("");
      await refresh(details.id);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function addCost(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!details) return;
    setBusy(true);
    setError(null);
    try {
      await addWorkOrderCostItem(session.accessToken, details.id, {
        version: details.version,
        kind: costKind,
        description: costDescription.trim(),
        quantity: costQuantity,
        unit_cost: costUnit,
      });
      setCostDescription("");
      setCostQuantity("1.00");
      setCostUnit("");
      await refresh(details.id);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  const vehicleLabels = new Map(
    vehicles.map((vehicle) => [vehicle.id, vehicle.unit_number]),
  );
  const usedDefects = new Set(
    orders.flatMap((order) =>
      order.source_defect_id ? [order.source_defect_id] : [],
    ),
  );
  const usedSchedules = new Set(
    orders.flatMap((order) =>
      order.maintenance_schedule_id ? [order.maintenance_schedule_id] : [],
    ),
  );
  const sourceOptions = [
    ...defects
      .filter((defect) => !usedDefects.has(defect.id))
      .map((defect) => ({
        value: `defect:${defect.id}`,
        label: `${defect.severity.toUpperCase()} defect · ${defect.description}`,
      })),
    ...schedules
      .filter(
        (schedule) =>
          ["due", "overdue"].includes(schedule.status) &&
          !usedSchedules.has(schedule.id),
      )
      .map((schedule) => ({
        value: `schedule:${schedule.id}`,
        label: `${schedule.status.toUpperCase()} service · ${vehicleLabels.get(schedule.vehicle_id) ?? "Vehicle"}`,
      })),
  ];
  const transitions = details
    ? canManage
      ? managerWorkOrderTransitions[details.status]
      : mechanicWorkOrderTransitions[details.status]
    : [];
  const acceptsRepairEntries =
    details &&
    !["completed", "verified", "closed", "cancelled"].includes(details.status);
  const openCount = orders.filter(
    (order) => !["closed", "cancelled"].includes(order.status),
  ).length;

  return (
    <section className="work-order-panel" id="work-orders">
      <div className="work-order-heading">
        <div>
          <p className="section-kicker">Repair execution</p>
          <h2>{canManage ? "Work-order control" : "My assigned work"}</h2>
          <p>Versioned repair records from source issue to verified closure.</p>
        </div>
        <span className="work-order-count">{openCount} open</span>
      </div>
      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}

      {canManage && (
        <form className="work-order-create" onSubmit={create}>
          <label>
            Source record
            <select
              required
              value={source}
              onChange={(event) => setSource(event.target.value)}
            >
              <option value="">Select an open defect or due service</option>
              {sourceOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Title
            <input
              required
              maxLength={180}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Repair brake warning"
            />
          </label>
          <label>
            Priority
            <select
              value={priority}
              onChange={(event) =>
                setPriority(event.target.value as WorkOrderPriority)
              }
            >
              {(["low", "normal", "high", "critical"] as const).map((value) => (
                <option key={value} value={value}>
                  {titleCase(value)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Assign mechanic
            <select
              required
              value={mechanicId}
              onChange={(event) => setMechanicId(event.target.value)}
            >
              <option value="">Choose a mechanic</option>
              {mechanics.map((mechanic) => (
                <option
                  key={mechanic.membership_id}
                  value={mechanic.membership_id}
                >
                  {mechanic.display_name}
                </option>
              ))}
            </select>
          </label>
          <label className="work-order-description">
            Work description
            <textarea
              required
              maxLength={5000}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Describe the diagnosis and expected repair."
            />
          </label>
          <button className="primary-button" disabled={busy || !source}>
            {busy ? "Creating…" : "Create work order"}
          </button>
        </form>
      )}

      <div className="work-order-grid">
        <div className="work-order-list">
          {orders.map((order) => (
            <button
              type="button"
              key={order.id}
              className={`work-order-card ${selectedId === order.id ? "selected" : ""}`}
              onClick={() => void selectOrder(order.id)}
            >
              <span className={`priority-dot priority-${order.priority}`} />
              <div>
                <strong>
                  #{order.number} · {order.title}
                </strong>
                <small>
                  {vehicleLabels.get(order.vehicle_id) ?? "Vehicle"} · Version{" "}
                  {order.version}
                </small>
              </div>
              <span className={`work-state state-${order.status}`}>
                {titleCase(order.status)}
              </span>
            </button>
          ))}
          {orders.length === 0 && (
            <div className="compact-empty">
              {canManage
                ? "No work orders yet. Select a source record above."
                : "No work orders are assigned to you."}
            </div>
          )}
        </div>

        <div className="work-order-detail">
          {details ? (
            <>
              <div className="work-order-detail-heading">
                <div>
                  <small>Work order #{details.number}</small>
                  <h3>{details.title}</h3>
                  <p>{details.description}</p>
                </div>
                <span className={`work-state state-${details.status}`}>
                  {titleCase(details.status)}
                </span>
              </div>
              <div className="repair-totals">
                <span>
                  <strong>{details.labour_hours}</strong> labour hours
                </span>
                <span>
                  <strong>
                    {formatMoney(details.labour_cost, details.currency)}
                  </strong>{" "}
                  labour
                </span>
                <span>
                  <strong>
                    {formatMoney(details.parts_cost, details.currency)}
                  </strong>{" "}
                  parts
                </span>
                <span>
                  <strong>
                    {formatMoney(details.total_cost, details.currency)}
                  </strong>{" "}
                  total
                </span>
              </div>

              {transitions.length > 0 && (
                <div className="transition-box">
                  <label>
                    Transition note
                    <input
                      value={transitionNote}
                      onChange={(event) =>
                        setTransitionNote(event.target.value)
                      }
                      placeholder="Required when verifying a repair"
                    />
                  </label>
                  <div>
                    {transitions.map((status) => (
                      <button
                        type="button"
                        className={
                          status === "verified"
                            ? "primary-button"
                            : "secondary-button"
                        }
                        disabled={
                          busy ||
                          (status === "verified" && !transitionNote.trim())
                        }
                        key={status}
                        onClick={() => void transition(status)}
                      >
                        {titleCase(status)}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {acceptsRepairEntries && (
                <div className="repair-entry-grid">
                  <form onSubmit={addNote}>
                    <h4>Repair note</h4>
                    <textarea
                      required
                      value={repairNote}
                      onChange={(event) => setRepairNote(event.target.value)}
                      placeholder="Diagnosis, repair, or test result"
                    />
                    <button className="secondary-button" disabled={busy}>
                      Add note
                    </button>
                  </form>
                  <form onSubmit={addCost}>
                    <h4>Labour or part</h4>
                    <select
                      value={costKind}
                      onChange={(event) =>
                        setCostKind(event.target.value as WorkOrderCostKind)
                      }
                    >
                      <option value="labour">Labour</option>
                      <option value="part">Part</option>
                      <option value="other">Other</option>
                    </select>
                    <input
                      required
                      value={costDescription}
                      onChange={(event) =>
                        setCostDescription(event.target.value)
                      }
                      placeholder="Description"
                    />
                    <div>
                      <input
                        required
                        min="0.01"
                        step="0.01"
                        type="number"
                        value={costQuantity}
                        onChange={(event) =>
                          setCostQuantity(event.target.value)
                        }
                        aria-label="Cost quantity"
                      />
                      <input
                        required
                        min="0"
                        step="0.01"
                        type="number"
                        value={costUnit}
                        onChange={(event) => setCostUnit(event.target.value)}
                        placeholder="Unit cost"
                        aria-label="Unit cost"
                      />
                    </div>
                    <button className="secondary-button" disabled={busy}>
                      Add cost item
                    </button>
                  </form>
                </div>
              )}

              <div className="repair-history">
                <h4>Repair record</h4>
                {[...details.notes].reverse().map((note) => (
                  <article key={note.id}>
                    <p>{note.body}</p>
                    <small>{new Date(note.created_at).toLocaleString()}</small>
                  </article>
                ))}
                {details.notes.length === 0 && (
                  <div className="compact-empty">No repair notes recorded.</div>
                )}
              </div>
            </>
          ) : (
            <div className="compact-empty">
              Select a work order to review it.
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function ManagementDashboard({ session }: { session: Session }) {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setSummary(await getDashboardSummary(session.accessToken));
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }, [session.accessToken]);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 30_000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  return (
    <section className="command-dashboard" id="dashboard">
      <div className="command-heading">
        <div>
          <p className="section-kicker">Live operational picture</p>
          <h2>Command dashboard</h2>
        </div>
        <button className="text-button" onClick={() => void refresh()}>
          Refresh
        </button>
      </div>
      {error && <div className="error-banner">{error}</div>}
      <div className="metric-grid" aria-label="Tenant operations summary">
        <Metric
          label="Operational vehicles"
          value={summary?.vehicles.operational ?? 0}
          accent="green"
        />
        <Metric
          label="Critical defects"
          value={summary?.defects.critical ?? 0}
          accent="red"
        />
        <Metric
          label="Due / overdue service"
          value={(summary?.maintenance.due ?? 0) + (summary?.maintenance.overdue ?? 0)}
          accent="amber"
        />
        <Metric
          label="Active work orders"
          value={summary?.work_orders.active ?? 0}
          accent="blue"
        />
      </div>
      <div className="command-signals">
        <span>
          <small>Fleet unavailable</small>
          <strong>{summary?.vehicles.unavailable ?? 0}</strong>
        </span>
        <span>
          <small>Unassigned repairs</small>
          <strong>{summary?.work_orders.unassigned ?? 0}</strong>
        </span>
        <span>
          <small>Awaiting verification</small>
          <strong>{summary?.work_orders.awaiting_verification ?? 0}</strong>
        </span>
        <span>
          <small>Repair cost · 30 days</small>
          <strong>
            {formatMoney(
              summary?.work_orders.repair_cost_30_days ?? "0",
              summary?.currency ?? session.identity.organization.default_currency,
            )}
          </strong>
        </span>
        {summary && (
          <time dateTime={summary.generated_at}>
            Updated {relativeTime(summary.generated_at)}
          </time>
        )}
      </div>
    </section>
  );
}

function OperationsAdminPanel({ session }: { session: Session }) {
  const [members, setMembers] = useState<Member[]>([]);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [entityType, setEntityType] = useState("");
  const [action, setAction] = useState("");
  const [auditFilters, setAuditFilters] = useState({ entityType: "", action: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [nextMembers, nextEvents] = await Promise.all([
        listMembers(session.accessToken),
        listAuditEvents(session.accessToken, {
          entityType: auditFilters.entityType || undefined,
          action: auditFilters.action || undefined,
          limit: 30,
        }),
      ]);
      setMembers(nextMembers);
      setEvents(nextEvents);
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }, [auditFilters, session.accessToken]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const assignableRoles =
    session.identity.role === "owner"
      ? (["owner", "manager", "driver", "mechanic"] as const)
      : (["driver", "mechanic"] as const);

  async function addMember(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    try {
      await createMember(session.accessToken, {
        email: String(form.get("email")),
        display_name: String(form.get("display_name")),
        role: String(form.get("role")) as Member["role"],
        temporary_password: String(form.get("temporary_password")),
      });
      event.currentTarget.reset();
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function changeMember(
    member: Member,
    patch: { role?: Member["role"]; is_active?: boolean },
  ) {
    setBusy(true);
    setError(null);
    try {
      await updateMember(session.accessToken, member.membership_id, patch);
      await refresh();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="operations-panel" id="operations">
      <div className="operations-heading">
        <div>
          <p className="section-kicker">Accountability &amp; access</p>
          <h2>Audit and team administration</h2>
        </div>
        <button className="secondary-button" disabled={busy} onClick={() => void refresh()}>
          Refresh workspace
        </button>
      </div>
      {error && <div className="error-banner">{error}</div>}
      <div className="operations-grid">
        <div className="team-admin">
          <form className="member-create" onSubmit={addMember}>
            <h3>Add a team member</h3>
            <div>
              <input name="display_name" placeholder="Full name" minLength={2} required />
              <input name="email" placeholder="Email address" type="email" required />
              <select name="role" aria-label="New member role">
                {assignableRoles.map((role) => (
                  <option key={role} value={role}>
                    {titleCase(role)}
                  </option>
                ))}
              </select>
              <input
                name="temporary_password"
                placeholder="Temporary password"
                type="password"
                minLength={12}
                required
              />
              <button className="primary-button" disabled={busy}>Add member</button>
            </div>
            <p>Share the temporary password privately and require it to be replaced.</p>
          </form>
          <div className="member-list">
            {members.map((member) => {
              const isSelf = member.user_id === session.identity.id;
              const canEdit =
                !isSelf &&
                (session.identity.role === "owner" ||
                  member.role === "driver" ||
                  member.role === "mechanic");
              return (
                <article key={member.membership_id}>
                  <span className="user-chip">{initials(member.display_name)}</span>
                  <div>
                    <strong>{member.display_name}</strong>
                    <small>{member.email}</small>
                  </div>
                  <select
                    aria-label={`Role for ${member.display_name}`}
                    disabled={!canEdit || busy}
                    value={member.role}
                    onChange={(event) =>
                      void changeMember(member, {
                        role: event.target.value as Member["role"],
                      })
                    }
                  >
                    {["owner", "manager", "driver", "mechanic"].map((role) => (
                      <option
                        key={role}
                        value={role}
                        disabled={
                          session.identity.role !== "owner" &&
                          (role === "owner" || role === "manager")
                        }
                      >
                        {titleCase(role)}
                      </option>
                    ))}
                  </select>
                  <button
                    className={member.is_active ? "member-active" : "member-inactive"}
                    disabled={!canEdit || busy}
                    onClick={() => void changeMember(member, { is_active: !member.is_active })}
                  >
                    {member.is_active ? "Active" : "Inactive"}
                  </button>
                </article>
              );
            })}
          </div>
        </div>
        <div className="audit-timeline">
          <form
            className="audit-filters"
            onSubmit={(event) => {
              event.preventDefault();
              const nextFilters = {
                entityType: entityType.trim(),
                action: action.trim(),
              };
              if (
                nextFilters.entityType === auditFilters.entityType &&
                nextFilters.action === auditFilters.action
              ) {
                void refresh();
              } else {
                setAuditFilters(nextFilters);
              }
            }}
          >
            <h3>Operational timeline</h3>
            <input
              aria-label="Filter audit entity type"
              placeholder="Entity type"
              value={entityType}
              onChange={(event) => setEntityType(event.target.value)}
            />
            <input
              aria-label="Filter audit action"
              placeholder="Exact action"
              value={action}
              onChange={(event) => setAction(event.target.value)}
            />
            <button className="secondary-button">Filter</button>
          </form>
          <div className="timeline-list">
            {events.map((event) => (
              <article key={event.id}>
                <span />
                <div>
                  <strong>{titleCase(event.action.replaceAll(".", " "))}</strong>
                  <p>
                    {event.actor?.display_name ?? "System"} · {titleCase(event.entity_type)}
                    {event.entity_id ? ` ${event.entity_id.slice(0, 8)}` : ""}
                  </p>
                  <small title={event.request_id ?? undefined}>
                    {new Date(event.created_at).toLocaleString()}
                  </small>
                </div>
              </article>
            ))}
            {events.length === 0 && <div className="compact-empty">No matching audit events.</div>}
          </div>
        </div>
      </div>
    </section>
  );
}

function SafetyPanel({
  session,
  canManage,
  onFleetChanged,
}: {
  session: Session;
  canManage: boolean;
  onFleetChanged: () => void;
}) {
  const [defects, setDefects] = useState<Defect[]>([]);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [dismissDefectId, setDismissDefectId] = useState<string | null>(null);
  const [dismissalNote, setDismissalNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [allDefects, alerts] = await Promise.all([
        listDefects(session.accessToken, {}),
        listNotifications(session.accessToken),
      ]);
      setDefects(
        allDefects.filter((defect) =>
          ["open", "triaged", "in_repair"].includes(defect.status),
        ),
      );
      setNotifications(alerts.items);
      setUnreadCount(alerts.unread_count);
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }, [session.accessToken]);

  useEffect(() => {
    void load();
  }, [load]);

  async function dismiss(notificationId: string) {
    try {
      await markNotificationRead(session.accessToken, notificationId);
      setNotifications((current) =>
        current.filter((item) => item.id !== notificationId),
      );
      setUnreadCount((current) => Math.max(0, current - 1));
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function dismissAll() {
    setBusy(true);
    try {
      await markAllNotificationsRead(session.accessToken);
      setNotifications([]);
      setUnreadCount(0);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  async function setDefectStatus(defect: Defect, status: "triaged" | "dismissed") {
    setBusy(true);
    setError(null);
    try {
      await updateDefect(session.accessToken, defect.id, {
        status,
        resolution_note:
          status === "dismissed" ? dismissalNote.trim() : "Reviewed by fleet management",
      });
      setDismissDefectId(null);
      setDismissalNote("");
      await load();
      onFleetChanged();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="safety-panel" id="safety">
      <div className="safety-heading">
        <div>
          <p className="section-kicker">Inspection safety loop</p>
          <h2>Open safety signals</h2>
        </div>
        <span className="safety-count">{defects.length} active</span>
      </div>
      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}
      <div className="safety-grid">
        <div className="defect-list">
          {defects.slice(0, 8).map((defect) => (
            <article
              className={`defect-card ${dismissDefectId === defect.id ? "expanded" : ""}`}
              key={defect.id}
            >
              <span className={`severity-mark severity-${defect.severity}`}>
                {defect.severity.slice(0, 1).toUpperCase()}
              </span>
              <div>
                <small>
                  {titleCase(defect.category)} ·{" "}
                  {relativeTime(defect.created_at)}
                </small>
                <strong>{defect.description}</strong>
                <span>{titleCase(defect.status)}</span>
              </div>
              {canManage && defect.status !== "in_repair" && (
                <div className="defect-actions">
                  {defect.status === "open" && (
                    <button
                      className="secondary-button"
                      disabled={busy}
                      onClick={() => void setDefectStatus(defect, "triaged")}
                    >
                      Triage
                    </button>
                  )}
                  <button
                    className="text-button danger"
                    disabled={busy}
                    onClick={() => setDismissDefectId(defect.id)}
                  >
                    Dismiss
                  </button>
                </div>
              )}
              {dismissDefectId === defect.id && (
                <form
                  className="defect-dismiss-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void setDefectStatus(defect, "dismissed");
                  }}
                >
                  <textarea
                    aria-label="Defect dismissal reason"
                    minLength={3}
                    maxLength={2000}
                    required
                    value={dismissalNote}
                    onChange={(event) => setDismissalNote(event.target.value)}
                    placeholder="Record why this signal is safe to dismiss"
                  />
                  <button className="primary-button" disabled={busy}>Confirm dismissal</button>
                  <button
                    className="text-button"
                    type="button"
                    onClick={() => setDismissDefectId(null)}
                  >
                    Cancel
                  </button>
                </form>
              )}
            </article>
          ))}
          {defects.length === 0 && (
            <div className="compact-empty">
              No open defects in the visible fleet.
            </div>
          )}
        </div>
        <div className="notification-list">
          <h3>
            Unread notifications <span>{unreadCount}</span>
          </h3>
          {unreadCount > 0 && (
            <button
              className="notification-read-all"
              disabled={busy}
              onClick={() => void dismissAll()}
            >
              Mark all read
            </button>
          )}
          {notifications.slice(0, 4).map((notification) => (
            <article key={notification.id}>
              <div>
                <strong>{notification.title}</strong>
                <p>{notification.body}</p>
              </div>
              <button
                aria-label={`Mark ${notification.title} read`}
                onClick={() => void dismiss(notification.id)}
              >
                ×
              </button>
            </article>
          ))}
          {notifications.length === 0 && (
            <div className="compact-empty">You’re caught up.</div>
          )}
        </div>
      </div>
    </section>
  );
}

function LoginView({
  onAuthenticated,
}: {
  onAuthenticated: (session: Session) => void;
}) {
  const [email, setEmail] = useState("manager@demo.fleetpulse.example.com");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const tokens = await login(email, password);
      const identity = await getIdentity(tokens.access_token);
      onAuthenticated({ accessToken: tokens.access_token, identity });
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-shell">
      <section className="login-story">
        <Brand />
        <div>
          <p className="eyebrow">Fleet operations, clarified</p>
          <h1>
            Know what can roll.
            <br />
            Act on what can’t.
          </h1>
          <p>
            A single, accountable view of fleet availability, safety holds, and
            maintenance readiness.
          </p>
        </div>
        <div className="signal-card">
          <span className="signal-pulse" />
          <div>
            <strong>Operational records stay tenant-isolated</strong>
            <small>
              Identity, role, and fleet context are verified by the API.
            </small>
          </div>
        </div>
      </section>
      <section className="login-panel">
        <form onSubmit={submit}>
          <p className="section-kicker">Secure workspace</p>
          <h2>Welcome back</h2>
          <p>Sign in with a seeded fleet account.</p>
          {error && (
            <div className="error-banner" role="alert">
              {error}
            </div>
          )}
          <label>
            Email address
            <input
              type="email"
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>
          <label>
            Password
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              minLength={12}
              required
            />
          </label>
          <button className="primary-button login-button" disabled={submitting}>
            {submitting ? "Verifying…" : "Sign in to FleetPulse"}
          </button>
          <small className="privacy-note">
            Access tokens remain only in this browser tab and are cleared on
            sign out or refresh.
          </small>
        </form>
      </section>
    </main>
  );
}

function CreateVehicleDialog({
  accessToken,
  onClose,
  onCreated,
}: {
  accessToken: string;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const input: VehicleCreateInput = {
      unit_number: String(form.get("unit_number")),
      vin: optional(form, "vin"),
      registration: optional(form, "registration"),
      make: String(form.get("make")),
      model: String(form.get("model")),
      model_year: Number(form.get("model_year")),
      fuel_type: optional(form, "fuel_type"),
      odometer_km: String(form.get("odometer_km")),
    };
    try {
      await createVehicle(accessToken, input);
      onCreated();
    } catch (caught) {
      setError(errorMessage(caught));
      setSaving(false);
    }
  }
  return (
    <Dialog
      title="Add a fleet vehicle"
      description="Create an auditable inventory record."
      onClose={onClose}
    >
      <form className="dialog-form" onSubmit={submit}>
        {error && (
          <div className="error-banner" role="alert">
            {error}
          </div>
        )}
        <div className="form-grid">
          <Field
            name="unit_number"
            label="Unit number"
            required
            placeholder="FP-505"
          />
          <Field
            name="registration"
            label="Registration"
            placeholder="NL-FP505"
          />
          <Field
            name="vin"
            label="VIN"
            placeholder="17 characters"
            minLength={17}
            maxLength={17}
          />
          <Field
            name="model_year"
            label="Model year"
            type="number"
            required
            defaultValue={new Date().getFullYear()}
            min={1886}
            max={2100}
          />
          <Field name="make" label="Make" required placeholder="Ford" />
          <Field name="model" label="Model" required placeholder="Transit" />
          <Field name="fuel_type" label="Fuel type" placeholder="diesel" />
          <Field
            name="odometer_km"
            label="Odometer (km)"
            type="number"
            required
            defaultValue="0.0"
            min={0}
            step="0.1"
          />
        </div>
        <div className="dialog-actions">
          <button type="button" className="secondary-button" onClick={onClose}>
            Cancel
          </button>
          <button className="primary-button" disabled={saving}>
            {saving ? "Adding…" : "Add vehicle"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

function ManageVehicleDialog({
  accessToken,
  vehicle,
  onClose,
  onUpdated,
}: {
  accessToken: string;
  vehicle: Vehicle;
  onClose: () => void;
  onUpdated: () => void;
}) {
  const [status, setStatus] = useState<VehicleStatus>(vehicle.status);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    const changed = status !== vehicle.status;
    try {
      await updateVehicle(accessToken, vehicle.id, {
        version: vehicle.version,
        odometer_km: String(form.get("odometer_km")),
        status,
        ...(changed
          ? { status_reason: String(form.get("status_reason")) }
          : {}),
      });
      onUpdated();
    } catch (caught) {
      setError(errorMessage(caught));
      setSaving(false);
    }
  }
  return (
    <Dialog
      title={`Manage ${vehicle.unit_number}`}
      description={`${vehicle.model_year} ${vehicle.make} ${vehicle.model}`}
      onClose={onClose}
    >
      <form className="dialog-form" onSubmit={submit}>
        {error && (
          <div className="error-banner" role="alert">
            {error}
          </div>
        )}
        <label>
          Status
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value as VehicleStatus)}
          >
            {vehicleStatuses.map((value) => (
              <option key={value} value={value}>
                {vehicleStatusLabels[value]}
              </option>
            ))}
          </select>
        </label>
        {status !== vehicle.status && (
          <label>
            Reason code
            <input
              name="status_reason"
              required
              maxLength={80}
              placeholder="manager_safety_hold"
            />
          </label>
        )}
        <label>
          Odometer (km)
          <input
            name="odometer_km"
            type="number"
            min={vehicle.odometer_km}
            step="0.1"
            defaultValue={vehicle.odometer_km}
            required
          />
        </label>
        <p className="form-note">
          The API will reject lower readings, illegal transitions, or a stale
          version.
        </p>
        <div className="dialog-actions">
          <button type="button" className="secondary-button" onClick={onClose}>
            Cancel
          </button>
          <button className="primary-button" disabled={saving}>
            {saving ? "Saving…" : "Save changes"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

function Dialog({
  title,
  description,
  onClose,
  children,
}: {
  title: string;
  description: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      className="dialog-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <section
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
      >
        <header>
          <div>
            <h2 id="dialog-title">{title}</h2>
            <p>{description}</p>
          </div>
          <button
            className="close-button"
            aria-label="Close dialog"
            onClick={onClose}
          >
            ×
          </button>
        </header>
        {children}
      </section>
    </div>
  );
}
function Field({
  label,
  ...props
}: {
  label: string;
  name: string;
  type?: string;
  required?: boolean;
  placeholder?: string;
  defaultValue?: string | number;
  min?: number;
  max?: number;
  minLength?: number;
  maxLength?: number;
  step?: string;
}) {
  return (
    <label>
      {label}
      <input {...props} />
    </label>
  );
}
function Metric({
  label,
  value,
  accent,
}: {
  label: string;
  value: number;
  accent: string;
}) {
  return (
    <article className={`metric-card metric-${accent}`}>
      <span className="metric-dot" />
      <div>
        <strong>{value}</strong>
        <small>{label}</small>
      </div>
    </article>
  );
}
function Brand() {
  return (
    <div className="brand">
      <span className="brand-mark">
        <i />
        <i />
        <i />
      </span>
      <span>
        FleetPulse<small>Intelligence</small>
      </span>
    </div>
  );
}
function optional(form: FormData, name: string): string | undefined {
  const value = String(form.get(name) ?? "").trim();
  return value || undefined;
}
function initials(name: string): string {
  return name
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}
function titleCase(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
function formatOdometer(value: string): string {
  return new Intl.NumberFormat("en-CA", { maximumFractionDigits: 1 }).format(
    Number(value),
  );
}
function formatMoney(value: string, currency: string): string {
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency,
  }).format(Number(value));
}
function relativeTime(value: string): string {
  const minutes = Math.max(
    0,
    Math.round((Date.now() - new Date(value).getTime()) / 60000),
  );
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}
function errorMessage(error: unknown): string {
  if (error instanceof FleetApiError)
    return `${error.message}${error.requestId ? ` Reference ${error.requestId}.` : ""}`;
  return "An unexpected error occurred.";
}
