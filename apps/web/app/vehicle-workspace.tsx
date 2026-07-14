"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  canManageVehicles,
  createVehicle,
  Defect,
  DefectSeverity,
  FleetApiError,
  getActiveInspectionTemplate,
  getIdentity,
  Identity,
  InspectionDetails,
  InspectionTemplate,
  listDefects,
  listNotifications,
  listVehicles,
  login,
  markNotificationRead,
  Notification,
  submitInspection,
  updateVehicle,
  Vehicle,
  VehicleCreateInput,
  vehicleStatusLabels,
  VehicleStatus,
  vehicleStatuses,
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
          <a className="nav-item" href="#safety">
            <span>✓</span> Safety loop
          </a>
          <span className="nav-item muted">
            <span>◇</span> Work orders <small>Next</small>
          </span>
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

        <div className="metric-grid" aria-label="Visible fleet summary">
          <Metric
            label="Visible vehicles"
            value={metrics.total}
            accent="blue"
          />
          <Metric
            label="Operational"
            value={metrics.available}
            accent="green"
          />
          <Metric label="Maintenance due" value={metrics.due} accent="amber" />
          <Metric
            label="Unavailable"
            value={metrics.unavailable}
            accent="red"
          />
        </div>

        <SafetyPanel session={session} />

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

function SafetyPanel({ session }: { session: Session }) {
  const [defects, setDefects] = useState<Defect[]>([]);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const [openDefects, alerts] = await Promise.all([
          listDefects(session.accessToken),
          listNotifications(session.accessToken),
        ]);
        if (active) {
          setDefects(openDefects);
          setNotifications(alerts.items);
        }
      } catch (caught) {
        if (active) setError(errorMessage(caught));
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [session.accessToken]);

  async function dismiss(notificationId: string) {
    try {
      await markNotificationRead(session.accessToken, notificationId);
      setNotifications((current) =>
        current.filter((item) => item.id !== notificationId),
      );
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  return (
    <section className="safety-panel" id="safety">
      <div className="safety-heading">
        <div>
          <p className="section-kicker">Inspection safety loop</p>
          <h2>Open safety signals</h2>
        </div>
        <span className="safety-count">{defects.length} open</span>
      </div>
      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}
      <div className="safety-grid">
        <div className="defect-list">
          {defects.slice(0, 5).map((defect) => (
            <article className="defect-card" key={defect.id}>
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
            Unread notifications <span>{notifications.length}</span>
          </h3>
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
