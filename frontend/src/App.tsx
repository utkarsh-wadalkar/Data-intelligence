import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { BorderBeam } from "border-beam";
import type { OrbState } from "thinking-orbs";
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
const ThinkingOrb = lazy(() =>
  import("thinking-orbs").then(({ ThinkingOrb }) => ({ default: ThinkingOrb })),
);
const MetalFx = lazy(() =>
  import("metal-fx").then(({ MetalFx }) => ({ default: MetalFx })),
);

function AuthMetal({ children }: { children: React.ReactElement }) {
  const [reducedMotion, setReducedMotion] = useState(() =>
    window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(preference.matches);
    preference.addEventListener("change", update);
    return () => preference.removeEventListener("change", update);
  }, []);

  return (
    <Suspense fallback={children}>
      <MetalFx className="auth-metal" preset="chromatic" strength={0.9} theme="light" paused={reducedMotion} disableGlow={reducedMotion} normalizeHostStyles={false}>
        {children}
      </MetalFx>
    </Suspense>
  );
}

function LoadingOrb({ state, theme = "light" }: { state: OrbState; theme?: "light" | "dark" }) {
  return (
    <span className="loading-orb" aria-hidden="true">
      <Suspense fallback={null}>
        <ThinkingOrb state={state} size={20} theme={theme} />
      </Suspense>
    </span>
  );
}

function formatDate(value: string | null) {
  return value
    ? new Date(`${value.endsWith("Z") ? value : `${value}Z`}`).toLocaleString()
    : "—";
}

function statusLabel(status: string) {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function BeamCard({
  children,
  className = "",
  theme = "light",
  subtle = false,
}: {
  children: React.ReactElement;
  className?: string;
  theme?: "light" | "dark";
  subtle?: boolean;
}) {
  const [reducedMotion, setReducedMotion] = useState(false);
  const [engaged, setEngaged] = useState(false);
  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReducedMotion(preference.matches);
    const update = () => setReducedMotion(preference.matches);
    preference.addEventListener("change", update);
    return () => preference.removeEventListener("change", update);
  }, []);

  return (
    <BorderBeam
      className={`beam-card ${className}`.trim()}
      size="pulse-inner"
      glowSize={2.2}
      brightness={1.6}
      strength={subtle ? 0.8 : 1}
      theme={theme}
      active={!reducedMotion && engaged}
      onMouseEnter={() => setEngaged(true)}
      onMouseLeave={() => setEngaged(false)}
      onFocusCapture={() => setEngaged(true)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setEngaged(false);
      }}
    >
      {children}
    </BorderBeam>
  );
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
    <main className="welcome" id="top">
      <header className="welcome-nav">
        <a className="welcome-home" href="#top" aria-label="SourcePilot, back to top">
          <Brand />
        </a>
        <nav className="welcome-links" aria-label="Landing page">
          <a href="#how-it-works">How it works</a>
          <a href="#why-sourcepilot">Why SourcePilot</a>
          <a href="#access">Access</a>
        </nav>
        <AuthMetal>
          <SignInButton mode="redirect">
            <button className="welcome-signin">Sign in</button>
          </SignInButton>
        </AuthMetal>
      </header>

      <section className="welcome-content" aria-labelledby="welcome-title">
        <div className="welcome-copy">
          <h1 id="welcome-title">
            Collect web data.<br />
            <span>Keep the evidence.</span>
          </h1>
          <p>
            Turn a plain-English research question into a structured dataset
            with sources you can inspect and results you can revisit.
          </p>
          <div className="welcome-actions">
            <AuthMetal>
              <SignUpButton mode="redirect">
                <button className="welcome-primary">Create account</button>
              </SignUpButton>
            </AuthMetal>
            <a className="welcome-secondary" href="#how-it-works">See how it works</a>
          </div>
        </div>
        <BeamCard className="beam-preview" theme="dark">
        <div className="landing-preview" aria-label="Illustrative event with sample records">
          <div className="preview-heading">
            <span>EVENT / 01</span>
            <span className="preview-status">LIVE</span>
          </div>
          <div className="preview-request">
            <strong>Find independent climate tech companies hiring product designers in Europe.</strong>
          </div>
          <div className="preview-arrow" aria-hidden="true" />
          <BeamCard className="beam-preview-output" subtle>
          <div className="preview-output">
            <table className="preview-table" aria-label="Illustrative results">
              <thead>
                <tr><th>Company</th><th>Role</th><th>Location</th></tr>
              </thead>
              <tbody>
                <tr><td>Northstar</td><td>Product Designer</td><td>Berlin</td></tr>
                <tr><td>Canopy</td><td>Senior Designer</td><td>Remote EU</td></tr>
                <tr><td>Forma</td><td>Design Lead</td><td>Amsterdam</td></tr>
              </tbody>
            </table>
          </div>
          </BeamCard>
          <div className="preview-bottom">
            <span>12 sources inspected</span>
            <span>Evidence attached to every record ↗</span>
          </div>
        </div>
        </BeamCard>
      </section>

      <section className="landing-promises" aria-label="SourcePilot at a glance">
        <div><strong>Approve the plan</strong><span>Set the fields before a run starts.</span></div>
        <div><strong>Trace every record</strong><span>Inspect the source behind each result.</span></div>
        <div><strong>Keep it current</strong><span>Schedule reruns into one dataset.</span></div>
      </section>

      <section className="landing-section landing-how" id="how-it-works" aria-labelledby="how-title">
        <div className="landing-section-heading">
          <h2 id="how-title">A clear path from question to dataset.</h2>
          <p>SourcePilot gathers public data for your event while you stay in control of what the records mean.</p>
        </div>
        <div className="landing-steps">
          <article>
            <span className="step-number">01</span>
            <h3>Describe the need</h3>
            <p>Write the data you want in plain English. SourcePilot proposes searches, fields, and record identity rules.</p>
          </article>
          <article>
            <span className="step-number">02</span>
            <h3>Approve the shape</h3>
            <p>Edit the proposed queries and fields before the first run. The approved schema keeps later runs consistent.</p>
          </article>
          <article>
            <span className="step-number">03</span>
            <h3>Collect and revisit</h3>
            <p>Review run progress, inspect evidence, search the accumulated records, and export CSV or JSON.</p>
          </article>
        </div>
      </section>

      <section className="landing-section landing-difference" id="why-sourcepilot" aria-labelledby="difference-title">
        <div className="landing-section-heading">
          <h2 id="difference-title">More useful than a one-off scrape.</h2>
          <p>The value is in what happens after a run: a stable structure, a source trail, and records you can return to.</p>
        </div>
        <div className="landing-feature-grid">
          <BeamCard className="beam-feature beam-feature-evidence" theme="dark">
          <article className="landing-feature landing-feature-evidence">
            <div>
              <h3>Answers with a trail.</h3>
              <p>Every result carries a URL, a short evidence excerpt, and the time the page was fetched. Inspect the source before you act.</p>
            </div>
            <BeamCard className="beam-evidence-slip" subtle>
            <div className="evidence-slip" aria-label="What each evidence field lets you verify">
              <div><strong>Source URL</strong><span>Open the original page</span></div>
              <div><strong>Evidence excerpt</strong><span>Match the claim to page text</span></div>
              <div><strong>Fetched at</strong><span>Know when it was checked</span></div>
            </div>
            </BeamCard>
          </article>
          </BeamCard>
          <BeamCard className="beam-feature beam-feature-schema">
          <article className="landing-feature landing-feature-schema">
            <h3>Your fields, your call.</h3>
            <p>The generated plan is a draft. You approve the typed fields and identity rules before the first run.</p>
            <div className="schema-tags" aria-label="Example field types">
              <span>title · text</span><span>deadline · date</span><span>region · text</span>
            </div>
          </article>
          </BeamCard>
          <BeamCard className="beam-feature beam-feature-history">
          <article className="landing-feature landing-feature-history">
            <h3>Set it once. Let it rerun.</h3>
            <p>Choose a daily or weekly schedule. Each due run updates the records, with run history intact.</p>
            <BeamCard className="beam-rerun-flow" subtle>
            <div className="rerun-flow" aria-label="Daily or weekly schedule starts the next run and updates the dataset">
              <div><span>Schedule</span><strong>Daily / weekly</strong></div>
              <span className="rerun-trigger" aria-hidden="true">
                <Suspense fallback={null}>
                  <ThinkingOrb state="composing" size={64} theme="light" />
                </Suspense>
              </span>
              <div><span>Auto rerun</span><strong>Dataset updated</strong></div>
            </div>
            </BeamCard>
          </article>
          </BeamCard>
        </div>
      </section>

      <section className="landing-section landing-compare" aria-labelledby="compare-title">
        <h2 id="compare-title">From scattered research to a repeatable workflow.</h2>
        <div className="compare-list">
          <div><span>Setup</span><p>Describe the request and approve a plan instead of building a separate scraper for every question.</p></div>
          <div><span>Confidence</span><p>Review source-backed records instead of losing the evidence in a spreadsheet export.</p></div>
          <div><span>Follow-up</span><p>Run an approved event again to refresh its records next week.</p></div>
        </div>
      </section>

      <BeamCard className="beam-access" theme="dark">
      <section className="landing-access" id="access" aria-labelledby="access-title">
        <div>
          <h2 id="access-title">Start with a question. Leave with something you can verify.</h2>
          <p>SourcePilot is available to invited members of the shared workspace. Public pages only, with free-provider limits and no paid model fallback.</p>
        </div>
        <AuthMetal>
          <SignUpButton mode="redirect">
            <button className="welcome-primary welcome-primary-light">Create account</button>
          </SignUpButton>
        </AuthMetal>
      </section>
      </BeamCard>
      <footer className="welcome-footer">
        <span>SourcePilot</span>
        <span>Data you can trace back to its source.</span>
        <a href="https://github.com/utkarsh-wadalkar/Data-intelligence" target="_blank" rel="noreferrer">GitHub</a>
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
  const [recoveryNotice, setRecoveryNotice] = useState<string | null>(null);
  const [notificationPermission, setNotificationPermission] = useState(
    typeof Notification === "undefined" ? "unsupported" : Notification.permission,
  );
  const [query, setQuery] = useState("");
  const [filterField, setFilterField] = useState("");
  const [filterValue, setFilterValue] = useState("");
  const [approval, setApproval] = useState<Workflow | null>(null);
  const [runPromptId, setRunPromptId] = useState<string | null>(null);
  const [usage, setUsage] = useState<{
    model: { used: number; limit: number };
    web: { used: number; limit: number };
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
    if (!source && !runDetails && !runPromptId) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSource(null);
        setRunDetails(null);
        setRunPromptId(null);
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [source, runDetails, runPromptId]);
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
          for (const run of nextRuns) {
            if (!run.recovery_count) continue;
            const key = `sourcepilot:recovery:${run.id}`;
            const notified = Number(window.localStorage.getItem(key) || 0);
            if (run.recovery_count <= notified) continue;
            window.localStorage.setItem(key, String(run.recovery_count));
            const message = `Run resumed after a rate limit (${run.observations} records found so far).`;
            setRecoveryNotice(message);
            if (typeof Notification !== "undefined" && Notification.permission === "granted") {
              new Notification("SourcePilot run resumed", { body: message });
            }
          }
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
  useEffect(() => {
    if (!recoveryNotice) return;
    const timeout = window.setTimeout(() => setRecoveryNotice(null), 10000);
    return () => window.clearTimeout(timeout);
  }, [recoveryNotice]);

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
      setRunPromptId(approval.id);
      setApproval(null);
    });
  }

  async function startRun(workflowId: string) {
    await act(async () => {
      const run = await request<Run>(`/api/workflows/${workflowId}/runs`, {
        method: "POST",
      });
      setRuns((previous) => [run, ...previous]);
      setRunPromptId(null);
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
      {recoveryNotice && (
        <div className="recovery-toast" role="alert">
          <div><strong>Run resumed</strong><span>{recoveryNotice}</span></div>
          <button onClick={() => setRecoveryNotice(null)} aria-label="Dismiss notification">×</button>
        </div>
      )}
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
          <div className="sidebar-caption sidebar-group">EVENTS</div>
          <button
            className={`nav-item ${!selectedId ? "active" : ""}`}
            onClick={() => {
              setSelectedId(null);
              setApproval(null);
              setRunPromptId(null);
            }}
          >
            ＋ &nbsp; New event
          </button>
          <div className="workflow-nav">
            {workflows.map((item) => (
              <button
                key={item.id}
                className={`nav-item ${selectedId === item.id ? "active" : ""}`}
                onClick={() => {
                  setSelectedId(item.id);
                  setApproval(item.status === "draft" ? item : null);
                  setRunPromptId(null);
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
                ? `${usage.model.used}/${usage.model.limit} AI calls today · ${usage.web.used}/${usage.web.limit} web requests this month`
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
              <span>/</span> {selected?.title ?? "New event"}
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
              <h1>Choose your record fields.</h1>
              <p className="intro">
                Review the proposed searches and fields. The schema locks when
                the first run begins. You can duplicate the event later to
                change it.
              </p>
              <BeamCard className="beam-form">
              <div className="panel form-panel">
                <label>
                  Event name
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
                  Record fields <span>Select at least one identity field</span>
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
                    {busy && <LoadingOrb state="connecting" theme="dark" />}
                    {busy ? "Saving…" : "Save event"}{" "}
                    {!busy && <span aria-hidden>→</span>}
                  </button>
                </div>
              </div>
              </BeamCard>
            </div>
          ) : !selected ? (
            <div className="content new-content">
              <div className="eyebrow">NEW EVENT</div>
              <h1>What do you need to know?</h1>
              <p className="intro">
                Describe the information you need from public web pages. We’ll
                suggest searches and fields for you to approve before collecting
                anything.
              </p>
              <BeamCard className="beam-prompt">
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
                    {drafting && <LoadingOrb state="shaping" theme="dark" />}
                    {drafting ? "Designing fields…" : "Create event"}{" "}
                    {!drafting && <span aria-hidden>→</span>}
                  </button>
                </div>
              </form>
              </BeamCard>
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
                    EVENT / {selected.status.toUpperCase()}
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
                  <b>Run paused</b>
                  <span>
                    {selected.pause_reason}.
                    {runs.find((run) => run.status === "paused" && run.next_retry_at)
                      ? ` Next retry ${formatDate(runs.find((run) => run.status === "paused" && run.next_retry_at)!.next_retry_at)}.`
                      : " Automatic retries will resume when the service or quota becomes available."}
                  </span>
                </div>
              )}
              {selected.status === "active" && runs.length === 0 && canManage && (
                <div className="ready-notice" role="status">
                  <div>
                    <b>Your event is ready</b>
                    <span>Start the first run whenever you’re ready.</span>
                  </div>
                  <button className="primary" disabled={busy} onClick={() => void startRun(selected.id)}>
                    {busy ? "Starting…" : "Run now"}
                  </button>
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
                    <BeamCard className="beam-stat">
                    <div className="stat-card">
                      <span>RECORDS IN VIEW</span>
                      <strong>{records.length}</strong>
                      <small>Across all runs</small>
                    </div>
                    </BeamCard>
                    <BeamCard className="beam-stat">
                    <div className="stat-card">
                      <span>RUNS</span>
                      <strong>{runs.length}</strong>
                      <small>History retained</small>
                    </div>
                    </BeamCard>
                    <BeamCard className="beam-stat">
                    <div className="stat-card">
                      <span>NEXT RUN</span>
                      <strong className="date-stat">
                        {selected.next_run_at
                          ? formatDate(selected.next_run_at)
                          : "Not scheduled"}
                      </strong>
                      <small>
                        {selected.cadence === "none"
                          ? "Manual runs"
                          : `${selected.cadence} · ${selected.timezone}`}
                      </small>
                    </div>
                    </BeamCard>
                  </div>
                  <div className="section-heading">
                    <div>
                      <h2>Run activity</h2>
                      <p>Monitor progress and inspect failures.</p>
                    </div>
                    {notificationPermission === "default" && (
                      <button
                        className="secondary"
                        onClick={() => {
                          void Notification.requestPermission().then(setNotificationPermission);
                        }}
                      >
                        Enable desktop alerts
                      </button>
                    )}
                    {canManage && selected.status === "active" && runs.length > 0 && (
                      <button
                        className="secondary"
                        disabled={busy || runs.some((run) => ["queued", "running", "paused"].includes(run.status))}
                        onClick={() => void startRun(selected.id)}
                      >
                        ↻ &nbsp; {runs.some((run) => ["queued", "running", "paused"].includes(run.status)) ? "Run pending" : "Run now"}
                      </button>
                    )}
                  </div>
                  <BeamCard className="beam-panel">
                  <div className="panel activity-panel" aria-live="polite">
                    {runs.length ? (
                      runs.map((run) => (
                        <div className="run-row" key={run.id}>
                          {run.status === "running" ? (
                            <LoadingOrb
                              state={run.stage === "extracting" ? "composing" : run.stage === "searching" ? "searching" : "working"}
                            />
                          ) : (
                            <span className={`run-indicator ${run.status}`} />
                          )}
                          <div>
                            <b>
                              {statusLabel(run.status)}{" "}
                              <span>· {run.trigger}</span>
                            </b>
                            <small>
                              {run.pause_reason
                                ? `${run.pause_reason}${run.next_retry_at ? ` · Next retry ${formatDate(run.next_retry_at)}` : ""}`
                                :
                                run.error ||
                                `${run.stage} · ${run.searched} searches · ${run.scraped} pages · ${run.observations} records found`}
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
                                      "Cancel this run?",
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
                        No runs yet. Start one when you're ready.
                      </div>
                    )}
                  </div>
                  </BeamCard>
                  <div className="section-heading">
                    <div>
                      <h2>Schedule</h2>
                      <p>Repeat this event automatically.</p>
                    </div>
                  </div>
                  <BeamCard className="beam-panel">
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
                  </BeamCard>
                </>
              ) : (
                <>
                  <div className="section-heading">
                    <div>
                      <h2>Records</h2>
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
                  <BeamCard className="beam-table">
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
                  </BeamCard>
                </>
              )}
            </div>
          )}
        </main>
        {runPromptId && (
          <div className="run-prompt-backdrop">
            <section className="run-prompt" role="dialog" aria-modal="true" aria-labelledby="run-prompt-title">
              <div className="eyebrow">EVENT SAVED</div>
              <h2 id="run-prompt-title">Ready to run your event?</h2>
              <p>Start a run to search public pages and add matching results to Records.</p>
              {error && <p role="alert">{error}</p>}
              <div className="run-prompt-actions">
                <button className="secondary" onClick={() => setRunPromptId(null)}>I'll run it later</button>
                <button className="primary" autoFocus disabled={busy} onClick={() => void startRun(runPromptId)}>
                  {busy ? "Starting…" : "Run now"}
                </button>
              </div>
            </section>
          </div>
        )}
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
              <div className="eyebrow">RUN DETAILS</div>
              <h2>{statusLabel(runDetails.status)}</h2>
              <p>
                {runDetails.pause_reason ||
                  runDetails.error ||
                  "Run progress and source counts."}
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
                <dt>RECORDS FOUND</dt>
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
