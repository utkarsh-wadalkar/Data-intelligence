import { useCallback, useEffect, useState } from "react";
import {
  OrganizationSwitcher,
  SignInButton,
  SignUpButton,
  UserButton,
  useAuth,
  useOrganization,
} from "@clerk/react";
import type { Field, RecordRow, Run, Source, Workflow } from "./types";

const apiBase = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function formatDate(value: string | null) {
  return value
    ? new Date(`${value.endsWith("Z") ? value : `${value}Z`}`).toLocaleString()
    : "—";
}

function statusLabel(status: string) {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function Brand() {
  return (
    <div className="brand">
      <img className="brand-logo" src="/sourcepilot-logo.png" alt="SourcePilot" />
    </div>
  );
}

export function Welcome() {
  return (
    <main className="welcome">
      <header className="welcome-nav">
        <Brand />
        <span>Data intelligence, on your terms</span>
      </header>
      <div className="welcome-content">
        <div className="welcome-copy">
          <div className="eyebrow">A clearer view of the web</div>
          <h1>
            From a question to a <em>living dataset.</em>
          </h1>
          <p>
            Describe the information you need. Approve the fields and sources.
            SourcePilot gathers traceable records and keeps them fresh on your
            schedule.
          </p>
          <div className="welcome-actions">
            <SignInButton mode="redirect">
              <button className="primary large">
                Sign in <span aria-hidden>↗</span>
              </button>
            </SignInButton>
            <SignUpButton mode="redirect">
              <button className="secondary large">Create account</button>
            </SignUpButton>
          </div>
          <small>Open your invitation email to join the shared workspace.</small>
        </div>
        <div className="welcome-art" aria-hidden="true">
          <div className="art-top">
            <span>COLLECTION / 01</span>
            <span>● LIVE</span>
          </div>
          <div className="art-question">
            Find independent climate tech companies hiring product designers in
            Europe.
          </div>
          <div className="art-arrow">↓</div>
          <div className="art-table">
            <div>
              <b>Company</b>
              <b>Role</b>
              <b>Location</b>
            </div>
            <div>
              <span>Northstar</span>
              <span>Product Designer</span>
              <span>Berlin</span>
            </div>
            <div>
              <span>Canopy</span>
              <span>Senior Designer</span>
              <span>Remote EU</span>
            </div>
            <div>
              <span>Forma</span>
              <span>Design Lead</span>
              <span>Amsterdam</span>
            </div>
          </div>
          <div className="art-bottom">
            <span>12 sources inspected</span>
            <span>Evidence attached to every record ↗</span>
          </div>
        </div>
      </div>
      <footer className="welcome-footer">
        <span>QUESTION → SOURCES → EVIDENCE → DATASET</span>
        <span>Built for decisions you can trace.</span>
      </footer>
    </main>
  );
}

export default function App() {
  const { getToken, userId, orgRole } = useAuth();
  const { organization, isLoaded } = useOrganization();
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [records, setRecords] = useState<RecordRow[]>([]);
  const [source, setSource] = useState<Source | null>(null);
  const [runDetails, setRunDetails] = useState<Run | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState("");
  const [view, setView] = useState<"overview" | "records">("overview");
  const [prompt, setPrompt] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filterField, setFilterField] = useState("");
  const [filterValue, setFilterValue] = useState("");
  const [approval, setApproval] = useState<Workflow | null>(null);
  const [usage, setUsage] = useState<{
    model: { used: number; limit: number };
    firecrawl: { used: number; limit: number };
  } | null>(null);

  const request = useCallback(
    async <T,>(path: string, init?: RequestInit): Promise<T> => {
      const token = await getToken();
      const response = await fetch(`${apiBase}${path}`, {
        ...init,
        headers: {
          Authorization: `Bearer ${token}`,
          ...(init?.body ? { "Content-Type": "application/json" } : {}),
          ...init?.headers,
        },
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(
          typeof detail.detail === "string"
            ? detail.detail
            : Array.isArray(detail.detail)
              ? detail.detail
                  .map(
                    (issue: { msg?: string }) => issue.msg || "Invalid input",
                  )
                  .join("; ")
              : `Request failed (${response.status}). Try again or check the run details.`,
        );
      }
      return response.json() as Promise<T>;
    },
    [getToken],
  );

  const refresh = useCallback(async () => {
    try {
      const [items, limits] = await Promise.all([
        request<Workflow[]>("/api/workflows"),
        request<typeof usage>("/api/usage"),
      ]);
      setWorkflows(items);
      setUsage(limits);
      setSelectedId((previous) =>
        previous && items.some((item) => item.id === previous)
          ? previous
          : (items[0]?.id ?? null),
      );
      setError(null);
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setLoading(false);
    }
  }, [request]);

  useEffect(() => {
    if (organization) void refresh();
  }, [organization, refresh]);
  useEffect(() => {
    if (!source && !runDetails) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSource(null);
        setRunDetails(null);
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [source, runDetails]);
  useEffect(() => {
    if (!selectedId) {
      setRuns([]);
      setRecords([]);
      return;
    }
    let active = true;
    const load = async () => {
      try {
        const [nextRuns, nextRecords] = await Promise.all([
          request<Run[]>(`/api/workflows/${selectedId}/runs`),
          request<RecordRow[]>(
            `/api/workflows/${selectedId}/records?q=${encodeURIComponent(query)}&field=${encodeURIComponent(filterField)}&value=${encodeURIComponent(filterValue)}`,
          ),
        ]);
        if (active) {
          setRuns(nextRuns);
          setRecords(nextRecords);
        }
      } catch (cause) {
        if (active) setError((cause as Error).message);
      }
    };
    void load();
    const interval = window.setInterval(() => {
      void load();
    }, 10000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [selectedId, query, filterField, filterValue, request]);

  const selected = workflows.find((item) => item.id === selectedId);
  const canManage =
    selected && (selected.creator_id === userId || orgRole === "org:admin");

  async function act(operation: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await operation();
      await refresh();
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function makeDraft(event: React.FormEvent) {
    event.preventDefault();
    if (!prompt.trim()) return;
    setDrafting(true);
    await act(async () => {
      const draft = await request<Workflow>("/api/drafts", {
        method: "POST",
        body: JSON.stringify({ prompt }),
      });
      setApproval(draft);
      setSelectedId(draft.id);
      setPrompt("");
    });
    setDrafting(false);
  }

  async function approve() {
    if (!approval) return;
    await act(async () => {
      await request(`/api/workflows/${approval.id}/approve`, {
        method: "POST",
        body: JSON.stringify({
          title: approval.title,
          queries: approval.queries,
          fields: approval.fields,
          identity_fields: approval.identity_fields,
        }),
      });
      setApproval(null);
    });
  }

  async function download(format: "csv" | "json") {
    if (!selected) return;
    try {
      const token = await getToken();
      const response = await fetch(
        `${apiBase}/api/workflows/${selected.id}/export?format=${format}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!response.ok) throw new Error("Export failed");
      const href = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = href;
      anchor.download = `${selected.title.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}.${format}`;
      anchor.click();
      URL.revokeObjectURL(href);
    } catch (cause) {
      setError((cause as Error).message);
    }
  }

  if (!isLoaded)
    return <div className="center-state">Loading your workspace…</div>;
  if (!organization)
    return (
      <main className="center-state">
        <img className="state-icon" src="/sourcepilot-icon.png" alt="" />
        <h1>Select your organization</h1>
        <p>
          Accept your invitation, then choose the organization to access shared data.
        </p>
        <OrganizationSwitcher hidePersonal />
        <UserButton />
      </main>
    );

  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <div className="shell">
        <aside className="sidebar">
          <div className="sidebar-wordmark">SourcePilot</div>
          <div className="sidebar-caption">WORKSPACE</div>
          <div className="org-line">
            <span className="org-dot" />
            {organization.name}
          </div>
          <div className="sidebar-caption sidebar-group">COLLECTIONS</div>
          <button
            className={`nav-item ${!selectedId ? "active" : ""}`}
            onClick={() => {
              setSelectedId(null);
              setApproval(null);
            }}
          >
            ＋ &nbsp; New collection
          </button>
          <div className="workflow-nav">
            {workflows.map((item) => (
              <button
                key={item.id}
                className={`nav-item ${selectedId === item.id ? "active" : ""}`}
                onClick={() => {
                  setSelectedId(item.id);
                  setApproval(item.status === "draft" ? item : null);
                  setView("overview");
                }}
              >
                <span className="nav-symbol">◈</span>
                <span>{item.title}</span>
              </button>
            ))}
          </div>
          <div className="sidebar-bottom">
            <span>Included usage</span>
            <small>
              {usage
                ? `${usage.model.used}/${usage.model.limit} AI calls today · ${usage.firecrawl.used}/${usage.firecrawl.limit} source credits this month`
                : "Loading usage…"}
            </small>
            <div className="account">
              <OrganizationSwitcher hidePersonal />
              <UserButton />
            </div>
          </div>
        </aside>
        <main className="main" id="main-content">
          <div className="topbar">
            <div className="breadcrumb">
              <img className="title-icon" src="/sourcepilot-icon.png" alt="" />
              <span className="title-name">SourcePilot</span>
              <span>/</span> {selected?.title ?? "New collection"}
            </div>
            <div className="topbar-right">
              <span className="topbar-dot" /> Shared organization data
            </div>
          </div>
          {error && (
            <div className="alert" role="alert">
              <span>{error}</span>
              <button onClick={() => setError(null)} aria-label="Dismiss error">
                ×
              </button>
            </div>
          )}
          {loading ? (
            <div className="content">
              <div className="skeleton title-skeleton" />
              <div className="skeleton block-skeleton" />
            </div>
          ) : approval ? (
            <div className="content narrow">
              <div className="eyebrow">STEP 02 / REVIEW THE PLAN</div>
              <h1>Shape your dataset.</h1>
              <p className="intro">
                Review the proposed searches and fields. The schema locks when
                the first run begins. You can clone the collection later to
                change it.
              </p>
              <div className="panel form-panel">
                <label>
                  Collection name
                  <input
                    value={approval.title}
                    maxLength={160}
                    onChange={(event) =>
                      setApproval({ ...approval, title: event.target.value })
                    }
                  />
                </label>
                <h2>
                  Searches <span>Up to three</span>
                </h2>
                {approval.queries.map((item, index) => (
                  <label key={index} className="query-row">
                    <span>0{index + 1}</span>
                    <input
                      value={item}
                      maxLength={200}
                      onChange={(event) =>
                        setApproval({
                          ...approval,
                          queries: approval.queries.map((query, i) =>
                            i === index ? event.target.value : query,
                          ),
                        })
                      }
                    />
                  </label>
                ))}
                <h2>
                  Dataset fields <span>Select at least one identity field</span>
                </h2>
                <div className="field-head">
                  <span>FIELD</span>
                  <span>TYPE</span>
                  <span>IDENTITY</span>
                  <span></span>
                </div>
                {approval.fields.map((field, index) => (
                  <div className="field-row" key={index}>
                    <div>
                      <input
                        aria-label={`Field ${index + 1} name`}
                        value={field.name}
                        autoComplete="off"
                        spellCheck={false}
                        onChange={(event) =>
                          setApproval({
                            ...approval,
                            fields: approval.fields.map((entry, i) =>
                              i === index
                                ? { ...entry, name: event.target.value }
                                : entry,
                            ),
                            identity_fields: approval.identity_fields.map(
                              (name) =>
                                name === field.name ? event.target.value : name,
                            ),
                          })
                        }
                      />
                      <input
                        aria-label={`Field ${index + 1} label`}
                        value={field.label}
                        onChange={(event) =>
                          setApproval({
                            ...approval,
                            fields: approval.fields.map((entry, i) =>
                              i === index
                                ? { ...entry, label: event.target.value }
                                : entry,
                            ),
                          })
                        }
                      />
                    </div>
                    <select
                      aria-label={`Field ${index + 1} type`}
                      value={field.type}
                      onChange={(event) =>
                        setApproval({
                          ...approval,
                          fields: approval.fields.map((entry, i) =>
                            i === index
                              ? {
                                  ...entry,
                                  type: event.target.value as Field["type"],
                                }
                              : entry,
                          ),
                        })
                      }
                    >
                      {["text", "number", "date", "url", "boolean"].map(
                        (type) => (
                          <option key={type}>{type}</option>
                        ),
                      )}
                    </select>
                    <label className="identity-check">
                      <input
                        aria-label={`Use ${field.name} for identity`}
                        type="checkbox"
                        checked={approval.identity_fields.includes(field.name)}
                        onChange={(event) =>
                          setApproval({
                            ...approval,
                            identity_fields: event.target.checked
                              ? [...approval.identity_fields, field.name]
                              : approval.identity_fields.filter(
                                  (name) => name !== field.name,
                                ),
                          })
                        }
                      />
                    </label>
                    <button
                      className="text-button"
                      aria-label={`Remove ${field.label || field.name}`}
                      disabled={approval.fields.length <= 1}
                      onClick={() =>
                        setApproval({
                          ...approval,
                          fields: approval.fields.filter((_, i) => i !== index),
                          identity_fields: approval.identity_fields.filter(
                            (name) => name !== field.name,
                          ),
                        })
                      }
                    >
                      Remove
                    </button>
                  </div>
                ))}
                <button
                  className="text-button"
                  disabled={approval.fields.length >= 20}
                  onClick={() =>
                    setApproval({
                      ...approval,
                      fields: [
                        ...approval.fields,
                        { name: "", label: "", type: "text", description: "" },
                      ],
                    })
                  }
                >
                  + Add field
                </button>
                <div className="form-actions">
                  <button
                    className="secondary"
                    onClick={() => setApproval(null)}
                  >
                    Review later
                  </button>
                  <button
                    className="primary"
                    disabled={busy}
                    onClick={() => void approve()}
                  >
                    {busy ? "Starting…" : "Approve & start collection"}{" "}
                    <span aria-hidden>→</span>
                  </button>
                </div>
              </div>
            </div>
          ) : !selected ? (
            <div className="content new-content">
              <div className="eyebrow">NEW COLLECTION</div>
              <h1>What do you need to know?</h1>
              <p className="intro">
                Describe the information you need from public web pages. We’ll
                suggest searches and fields for you to approve before collecting
                anything.
              </p>
              <form
                className="prompt-form"
                onSubmit={(event) => void makeDraft(event)}
              >
                <label htmlFor="prompt">YOUR DATA REQUEST</label>
                <textarea
                  id="prompt"
                  name="prompt"
                  autoComplete="off"
                  required
                  minLength={15}
                  maxLength={3000}
                  placeholder="Find publicly listed companies in Berlin hiring senior product designers. Include company, role, location, posting date, and application link…"
                  value={prompt}
                  onChange={(event) => setPrompt(event.target.value)}
                />
                <div className="prompt-footer">
                  <span>Public sources only · Up to 12 pages per run</span>
                  <button className="primary" disabled={drafting}>
                    {drafting ? "Designing fields…" : "Design collection"}{" "}
                    <span aria-hidden>→</span>
                  </button>
                </div>
              </form>
              <div className="how-it-works">
                <div>
                  <b>01</b>
                  <h3>Describe</h3>
                  <p>Start with a question in plain language.</p>
                </div>
                <div>
                  <b>02</b>
                  <h3>Approve</h3>
                  <p>Choose the fields and stable record identity.</p>
                </div>
                <div>
                  <b>03</b>
                  <h3>Explore</h3>
                  <p>Trace every result back to its source.</p>
                </div>
              </div>
            </div>
          ) : (
            <div className="content">
              <div className="page-heading">
                <div>
                  <div className="eyebrow">
                    COLLECTION / {selected.status.toUpperCase()}
                  </div>
                  <h1>{selected.title}</h1>
                  <p>{selected.prompt}</p>
                </div>
                <span
                  className={`status-pill ${selected.pause_reason ? "paused" : ""}`}
                >
                  {selected.pause_reason
                    ? "Paused"
                    : selected.status === "draft"
                      ? "Awaiting approval"
                      : "Active"}
                </span>
              </div>
              {selected.pause_reason && (
                <div className="notice" role="status">
                  <b>Collection paused</b>
                  <span>
                    {selected.pause_reason}. Scheduled work will retry when the
                    service or quota becomes available.
                  </span>
                </div>
              )}
              <div className="tabs">
                <button
                  className={view === "overview" ? "selected" : ""}
                  onClick={() => setView("overview")}
                >
                  Overview
                </button>
                <button
                  className={view === "records" ? "selected" : ""}
                  onClick={() => setView("records")}
                >
                  Records <span>{records.length}</span>
                </button>
              </div>
              {view === "overview" ? (
                <>
                  <div className="stats">
                    <div>
                      <span>RECORDS IN VIEW</span>
                      <strong>{records.length}</strong>
                      <small>Cumulative dataset</small>
                    </div>
                    <div>
                      <span>COLLECTION RUNS</span>
                      <strong>{runs.length}</strong>
                      <small>History retained</small>
                    </div>
                    <div>
                      <span>NEXT RUN</span>
                      <strong className="date-stat">
                        {selected.next_run_at
                          ? formatDate(selected.next_run_at)
                          : "Not scheduled"}
                      </strong>
                      <small>
                        {selected.cadence === "none"
                          ? "Manual collection"
                          : `${selected.cadence} · ${selected.timezone}`}
                      </small>
                    </div>
                  </div>
                  <div className="section-heading">
                    <div>
                      <h2>Collection activity</h2>
                      <p>Monitor progress and inspect failures.</p>
                    </div>
                    {canManage && selected.status === "active" && (
                      <button
                        className="secondary"
                        disabled={busy}
                        onClick={() =>
                          void act(() =>
                            request(`/api/workflows/${selected.id}/runs`, {
                              method: "POST",
                            }),
                          )
                        }
                      >
                        ↻ &nbsp; Run now
                      </button>
                    )}
                  </div>
                  <div className="panel activity-panel" aria-live="polite">
                    {runs.length ? (
                      runs.map((run) => (
                        <div className="run-row" key={run.id}>
                          <span className={`run-indicator ${run.status}`} />
                          <div>
                            <b>
                              {statusLabel(run.status)}{" "}
                              <span>· {run.trigger}</span>
                            </b>
                            <small>
                              {run.pause_reason ||
                                run.error ||
                                `${run.stage} · ${run.searched} searches · ${run.scraped} pages · ${run.observations} observations`}
                            </small>
                          </div>
                          <time>{formatDate(run.created_at)}</time>
                          <button
                            className="text-button"
                            onClick={() => setRunDetails(run)}
                          >
                            Details
                          </button>
                          {canManage &&
                            ["queued", "running", "paused"].includes(
                              run.status,
                            ) && (
                              <button
                                className="text-button"
                                onClick={() => {
                                  if (
                                    window.confirm(
                                      "Cancel this collection run?",
                                    )
                                  )
                                    void act(() =>
                                      request(`/api/runs/${run.id}/cancel`, {
                                        method: "POST",
                                      }),
                                    );
                                }}
                              >
                                Cancel
                              </button>
                            )}
                          {canManage &&
                            ["failed", "cancelled", "paused"].includes(
                              run.status,
                            ) && (
                              <button
                                className="text-button"
                                onClick={() =>
                                  void act(() =>
                                    request(`/api/runs/${run.id}/retry`, {
                                      method: "POST",
                                    }),
                                  )
                                }
                              >
                                Retry
                              </button>
                            )}
                        </div>
                      ))
                    ) : (
                      <div className="empty-state">
                        No runs yet. Approve this collection to begin.
                      </div>
                    )}
                  </div>
                  <div className="section-heading">
                    <div>
                      <h2>Schedule</h2>
                      <p>Repeat the approved collection automatically.</p>
                    </div>
                  </div>
                  <div className="panel schedule-panel">
                    <ScheduleEditor
                      workflow={selected}
                      disabled={
                        !canManage || busy || selected.status !== "active"
                      }
                      onSave={(value) =>
                        void act(() =>
                          request(`/api/workflows/${selected.id}/schedule`, {
                            method: "PATCH",
                            body: JSON.stringify(value),
                          }),
                        )
                      }
                    />
                    {canManage && selected.status === "active" && (
                      <button
                        className="text-button"
                        onClick={() =>
                          void act(async () => {
                            const copy = await request<Workflow>(
                              `/api/workflows/${selected.id}/clone`,
                              { method: "POST" },
                            );
                            setSelectedId(copy.id);
                            setApproval(copy);
                          })
                        }
                      >
                        Clone to change fields ↗
                      </button>
                    )}
                  </div>
                </>
              ) : (
                <>
                  <div className="section-heading">
                    <div>
                      <h2>Dataset</h2>
                      <p>
                        Search, filter, inspect evidence, or export all records.
                      </p>
                    </div>
                    <div className="export-actions">
                      <button
                        className="secondary"
                        onClick={() => void download("csv")}
                      >
                        Export CSV
                      </button>
                      <button
                        className="secondary"
                        onClick={() => void download("json")}
                      >
                        Export JSON
                      </button>
                    </div>
                  </div>
                  <div className="filters">
                    <input
                      aria-label="Search all records"
                      placeholder="Search records…"
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                    />
                    <select
                      aria-label="Filter field"
                      value={filterField}
                      onChange={(event) => setFilterField(event.target.value)}
                    >
                      <option value="">All fields</option>
                      {selected.fields.map((field) => (
                        <option value={field.name} key={field.name}>
                          {field.label}
                        </option>
                      ))}
                    </select>
                    <input
                      aria-label="Filter value"
                      placeholder="Filter value…"
                      value={filterValue}
                      onChange={(event) => setFilterValue(event.target.value)}
                      disabled={!filterField}
                    />
                  </div>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          {selected.fields.map((field) => (
                            <th key={field.name}>{field.label}</th>
                          ))}
                          <th>LAST SEEN</th>
                          <th>SOURCE</th>
                        </tr>
                      </thead>
                      <tbody>
                        {records.map((row) => (
                          <tr key={row.id}>
                            {selected.fields.map((field) => (
                              <td key={field.name}>
                                {String(row.data[field.name] ?? "—")}
                              </td>
                            ))}
                            <td>{formatDate(row.last_seen_at)}</td>
                            <td>
                              <button
                                className="link-button"
                                onClick={() => {
                                  setSelectedEvidence(row.evidence);
                                  void request<Source>(
                                    `/api/sources/${row.source_id}`,
                                  )
                                    .then(setSource)
                                    .catch((cause) =>
                                      setError((cause as Error).message),
                                    );
                                }}
                              >
                                Inspect ↗
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {!records.length && (
                      <div className="empty-state">
                        No matching records yet. Try a different filter or check
                        the run status.
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          )}
        </main>
        {source && (
          <div className="drawer-backdrop">
            <aside
              className="source-drawer"
              role="dialog"
              aria-modal="true"
              aria-label="Source details"
            >
              <button
                className="close-button"
                onClick={() => setSource(null)}
                aria-label="Close source details"
              >
                ×
              </button>
              <div className="eyebrow">SOURCE EVIDENCE</div>
              <h2>{source.title || "Web page"}</h2>
              <a href={source.url} target="_blank" rel="noreferrer">
                {source.url} ↗
              </a>
              <dl>
                <dt>FETCHED</dt>
                <dd>{formatDate(source.fetched_at)}</dd>
                <dt>RUN</dt>
                <dd>{source.run_id}</dd>
              </dl>
              <h3>Record evidence</h3>
              <blockquote>{selectedEvidence}</blockquote>
              <h3>Page excerpt</h3>
              <blockquote>{source.excerpt}</blockquote>
            </aside>
          </div>
        )}
        {runDetails && (
          <div className="drawer-backdrop">
            <aside
              className="source-drawer"
              role="dialog"
              aria-modal="true"
              aria-label="Run details"
            >
              <button
                className="close-button"
                onClick={() => setRunDetails(null)}
                aria-label="Close run details"
              >
                ×
              </button>
              <div className="eyebrow">COLLECTION RUN</div>
              <h2>{statusLabel(runDetails.status)}</h2>
              <p>
                {runDetails.pause_reason ||
                  runDetails.error ||
                  "Collection progress and source counts."}
              </p>
              <dl>
                <dt>STAGE</dt>
                <dd>{runDetails.stage}</dd>
                <dt>TRIGGER</dt>
                <dd>{runDetails.trigger}</dd>
                <dt>STARTED</dt>
                <dd>{formatDate(runDetails.created_at)}</dd>
                <dt>FINISHED</dt>
                <dd>{formatDate(runDetails.finished_at)}</dd>
                <dt>SEARCHES</dt>
                <dd>{runDetails.searched}</dd>
                <dt>PAGES</dt>
                <dd>{runDetails.scraped}</dd>
                <dt>OBSERVATIONS</dt>
                <dd>{runDetails.observations}</dd>
              </dl>
            </aside>
          </div>
        )}
      </div>
    </>
  );
}

function ScheduleEditor({
  workflow,
  disabled,
  onSave,
}: {
  workflow: Workflow;
  disabled: boolean;
  onSave: (value: {
    cadence: string;
    timezone: string;
    local_hour: number;
    week_day: number;
  }) => void;
}) {
  const [cadence, setCadence] = useState(workflow.cadence);
  const [timezone, setTimezone] = useState(workflow.timezone);
  const [hour, setHour] = useState(workflow.local_hour);
  const [day, setDay] = useState(workflow.week_day);
  useEffect(() => {
    setCadence(workflow.cadence);
    setTimezone(workflow.timezone);
    setHour(workflow.local_hour);
    setDay(workflow.week_day);
  }, [workflow]);
  return (
    <div className="schedule-form">
      <label>
        Frequency
        <select
          disabled={disabled}
          value={cadence}
          onChange={(event) =>
            setCadence(event.target.value as Workflow["cadence"])
          }
        >
          <option value="none">Manual only</option>
          <option value="daily">Every day</option>
          <option value="weekly">Every week</option>
        </select>
      </label>
      <label>
        Hour
        <select
          disabled={disabled || cadence === "none"}
          value={hour}
          onChange={(event) => setHour(Number(event.target.value))}
        >
          {Array.from({ length: 24 }, (_, index) => (
            <option value={index} key={index}>
              {String(index).padStart(2, "0")}:00
            </option>
          ))}
        </select>
      </label>
      {cadence === "weekly" && (
        <label>
          Day
          <select
            disabled={disabled}
            value={day}
            onChange={(event) => setDay(Number(event.target.value))}
          >
            {[
              "Monday",
              "Tuesday",
              "Wednesday",
              "Thursday",
              "Friday",
              "Saturday",
              "Sunday",
            ].map((name, index) => (
              <option value={index} key={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
      )}
      <label>
        Timezone
        <input
          disabled={disabled || cadence === "none"}
          value={timezone}
          onChange={(event) => setTimezone(event.target.value)}
          placeholder="Asia/Kolkata"
        />
      </label>
      <button
        className="primary"
        disabled={disabled}
        onClick={() =>
          onSave({ cadence, timezone, local_hour: hour, week_day: day })
        }
      >
        Save schedule
      </button>
    </div>
  );
}
