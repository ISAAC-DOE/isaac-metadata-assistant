import './screens.css';
import {
  useCallback,
  useMemo,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from 'react';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { LoadingPanel, BackendDown } from '../components/FetchStates';
import { CircleHelp, LayoutList, Search, ChevronRight, Shield, Settings } from '../components/icons';
import { LABELS } from '../lib/labels';
import { api } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import type {
  ApiAboutResponse,
  ApiOpenApiResponse,
  OpenApiMediaType,
  OpenApiMethod,
  OpenApiParameter,
  OpenApiRequestBody,
} from '../lib/types';

/**
 * Settings — P36R Slice 9 reorganises this surface into four local page tabs
 * (Overview · Data & Privacy · About · API) using the SAME tablist contract as
 * Governance & Safety and Project Memory (`.section-tabs`/`.section-tab`,
 * roving tabindex, Arrow/Home/End), not a fourth variant.
 *
 * There are NO user-adjustable settings in this build, and none were invented
 * to fill a page: every tab is informational, and the page says so plainly.
 * Overview and About render `GET /api/about` verbatim; the API tab is a
 * master-detail browser over `GET /api/openapi`, the app's own generated
 * contract — never a hand-maintained duplicate, no CDN, no Swagger UI/ReDoc.
 *
 * Both fetches are issued once at page level so switching tabs is pure client
 * state and never re-hits the backend.
 */

type SettingsTab = 'overview' | 'privacy' | 'about' | 'api';

const SETTINGS_TABS: { id: SettingsTab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'privacy', label: 'Data & Privacy' },
  { id: 'about', label: 'About' },
  { id: 'api', label: 'API' },
];

const tabId = (id: SettingsTab) => `settings-tab-${id}`;
const panelId = (id: SettingsTab) => `settings-tabpanel-${id}`;

export function SettingsPage() {
  const [activeTab, setActiveTab] = useState<SettingsTab>('overview');
  const about = useFetch(() => api.getAbout(), []);
  const openapi = useFetch(() => api.getOpenApi(), []);

  return (
    <AppShell
      variant="full"
      topBar={<TopBar variant="home" />}
      sidebar={<LeftNav active="settings" />}
      mainPad="pad"
      width="wide"
    >
      <div className="placeholder">
        <span className="eyebrow">Local Configuration</span>
        <h1>{LABELS.navSettings}</h1>
        <p>
          This build has no user-adjustable settings — nothing on this screen changes how the app
          behaves. It reports what the running app is: its data regime, what it stores and discards,
          its identity and provenance, and the API it exposes.
        </p>

        <SettingsSectionTabs active={activeTab} onSelect={setActiveTab} />
      </div>

      {activeTab === 'overview' && (
        <div
          className="settings-panel"
          id={panelId('overview')}
          role="tabpanel"
          aria-labelledby={tabId('overview')}
          tabIndex={0}
        >
          <OverviewTab state={about} onSelectTab={setActiveTab} />
        </div>
      )}

      {activeTab === 'privacy' && (
        <div
          className="settings-panel"
          id={panelId('privacy')}
          role="tabpanel"
          aria-labelledby={tabId('privacy')}
          tabIndex={0}
        >
          <PrivacyTab state={about} />
        </div>
      )}

      {activeTab === 'about' && (
        <div
          className="settings-panel"
          id={panelId('about')}
          role="tabpanel"
          aria-labelledby={tabId('about')}
          tabIndex={0}
        >
          <AboutTab state={about} />
        </div>
      )}

      {activeTab === 'api' && (
        <div
          className="settings-panel"
          id={panelId('api')}
          role="tabpanel"
          aria-labelledby={tabId('api')}
          tabIndex={0}
        >
          <ApiTab state={openapi} />
        </div>
      )}
    </AppShell>
  );
}

// --- local page tabs (same contract as GovernancePage / ProjectMemory) ------

function SettingsSectionTabs({
  active,
  onSelect,
}: {
  active: SettingsTab;
  onSelect: (tab: SettingsTab) => void;
}) {
  function onKeyDown(e: ReactKeyboardEvent<HTMLButtonElement>, index: number) {
    let nextIndex: number | null = null;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      nextIndex = (index + 1) % SETTINGS_TABS.length;
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      nextIndex = (index - 1 + SETTINGS_TABS.length) % SETTINGS_TABS.length;
    } else if (e.key === 'Home') {
      nextIndex = 0;
    } else if (e.key === 'End') {
      nextIndex = SETTINGS_TABS.length - 1;
    }
    if (nextIndex === null) return;
    e.preventDefault();
    const next = SETTINGS_TABS[nextIndex];
    onSelect(next.id);
    (document.getElementById(tabId(next.id)) as HTMLButtonElement | null)?.focus();
  }

  return (
    <div className="section-tabs" role="tablist" aria-label="Settings sections">
      {SETTINGS_TABS.map((tab, i) => {
        const selected = active === tab.id;
        return (
          <button
            key={tab.id}
            id={tabId(tab.id)}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-controls={selected ? panelId(tab.id) : undefined}
            tabIndex={selected ? 0 : -1}
            className={`section-tab${selected ? ' active' : ''}`}
            onClick={() => onSelect(tab.id)}
            onKeyDown={(e) => onKeyDown(e, i)}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

// --- shared card chrome -----------------------------------------------------

function SettingsCard({
  icon,
  headingId,
  title,
  sub,
  children,
}: {
  icon: ReactNode;
  headingId: string;
  title: string;
  sub: string;
  children: ReactNode;
}) {
  return (
    <section className="card placeholder-card settings-card" aria-labelledby={headingId}>
      <header className="settings-card-head">
        {icon}
        <div>
          <h2 id={headingId}>{title}</h2>
          <p className="settings-card-sub">{sub}</p>
        </div>
      </header>
      {children}
    </section>
  );
}

type AboutState = ReturnType<typeof useFetch<ApiAboutResponse>>;
type OpenApiState = ReturnType<typeof useFetch<ApiOpenApiResponse>>;

// --- Overview ---------------------------------------------------------------

/**
 * Every sentence below is gated on the value the backend actually reported. If
 * `/api/about` ever reports something else, the honest fallback names the real
 * value rather than repeating a claim the API contradicts.
 *
 * These sentences describe what the CODE does, not what the governance policy
 * asks for. Two things the copy must never overstate:
 *
 *  - the app gates on runtime MODE, never on the CONTENTS of what it is handed.
 *    There is no real-vs-synthetic detector anywhere in the backend, so nothing
 *    here may imply that real data is recognised and turned away.
 *  - `persistence: "ephemeral"` is a fixed literal about deployment intent, not
 *    a process-lifetime guarantee. Workspace state is written to files under a
 *    server-side working directory (`ISAAC_UI_WORKSPACE`), so it outlives the
 *    process; only the deployment's temporary storage bounds it.
 */
function regimeClaim(value: string): string {
  return value === 'synthetic-only'
    ? 'Only unmistakably synthetic data is in scope, and this build runs in synthetic-only mode: file upload is refused outright. What the app enforces is that mode, not the contents of what it is handed — it cannot tell real data from synthetic, so keeping real artifacts out is a responsibility of whoever operates it, not a check the software performs.'
    : `The backend reports the data regime as "${value}". This screen states only what the backend reports.`;
}

function persistenceClaim(value: string): string {
  return value === 'ephemeral'
    ? 'There is no database. Workspace state is written as files in a working directory on the server, so restarting the backend process does not by itself clear it. The backend reports that storage as ephemeral: it is not durable, is not shared between deployments, and is discarded whenever the temporary storage it sits on goes away — this screen cannot say when that will be.'
    : `The backend reports persistence as "${value}". This screen states only what the backend reports.`;
}

function OverviewTab({
  state,
  onSelectTab,
}: {
  state: AboutState;
  onSelectTab: (tab: SettingsTab) => void;
}) {
  return (
    <SettingsCard
      icon={<Settings size={18} strokeWidth={2} aria-hidden="true" className="settings-card-icon" />}
      headingId="settings-overview-heading"
      title="Overview"
      sub="What this running build is right now — read from the app itself, not configured here."
    >
      {state.status === 'loading' && <LoadingPanel label="Loading app info…" />}
      {state.status === 'error' && <BackendDown error={state.error} onRetry={state.reload} />}
      {state.status === 'data' && <OverviewBody data={state.data} onSelectTab={onSelectTab} />}
    </SettingsCard>
  );
}

function OverviewBody({
  data,
  onSelectTab,
}: {
  data: ApiAboutResponse;
  onSelectTab: (tab: SettingsTab) => void;
}) {
  return (
    <>
      <dl className="settings-figures">
        <Figure label="App version" value={<span className="mono">{data.app_version}</span>} />
        <Figure
          label="Record schema"
          value={<span className="mono">v{data.record_schema_version}</span>}
        />
        <Figure label="Runtime mode" value={<span className="mono">{data.runtime_mode}</span>} />
        <Figure label="Data regime" value={<span className="mono">{data.data_regime}</span>} />
        <Figure label="Persistence" value={<span className="mono">{data.persistence}</span>} />
        <Figure label="Core" value={<span className="mono">{data.core}</span>} />
      </dl>

      <ul className="settings-points">
        <li>
          <h3>Data regime</h3>
          <p>{regimeClaim(data.data_regime)}</p>
        </li>
        <li>
          <h3>Persistence</h3>
          <p>{persistenceClaim(data.persistence)}</p>
        </li>
        <li>
          <h3>Telemetry</h3>
          <p>
            None. No analytics, no usage tracking, and no cloud sync — this app makes no
            third-party network requests at all.
          </p>
        </li>
        <li>
          <h3>Authentication</h3>
          <p>
            This app has no sign-in flow, no accounts, and no user profiles — there is nothing to
            log in as. Access can still be restricted, either by the environment this build is
            deployed into or by an optional shared key the backend requires when an operator
            configures one. This screen cannot report whether either is in force.
          </p>
        </li>
        <li>
          <h3>Record truth</h3>
          <p>
            Validity, evidence, and export are decided by the deterministic core against the
            official ISAAC v{data.record_schema_version} schema. Project Memory and the assistant
            are advisory and can never authorize an export.
          </p>
        </li>
      </ul>

      <nav className="settings-jump" aria-label="More settings detail">
        <button type="button" className="settings-jump-btn" onClick={() => onSelectTab('privacy')}>
          Data &amp; Privacy detail
          <ChevronRight size={13} strokeWidth={2.2} aria-hidden="true" />
        </button>
        <button type="button" className="settings-jump-btn" onClick={() => onSelectTab('about')}>
          Version &amp; provenance
          <ChevronRight size={13} strokeWidth={2.2} aria-hidden="true" />
        </button>
        <button type="button" className="settings-jump-btn" onClick={() => onSelectTab('api')}>
          Browse the API
          <ChevronRight size={13} strokeWidth={2.2} aria-hidden="true" />
        </button>
      </nav>
    </>
  );
}

function Figure({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="settings-figure">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

// --- Data & Privacy ---------------------------------------------------------

function PrivacyTab({ state }: { state: AboutState }) {
  return (
    <SettingsCard
      icon={<Shield size={18} strokeWidth={2} aria-hidden="true" className="settings-card-icon" />}
      headingId="settings-privacy-heading"
      title="Data & Privacy"
      sub="What this build accepts, what it keeps, what it discards, and what it never sends anywhere."
    >
      {state.status === 'loading' && <LoadingPanel label="Loading app info…" />}
      {state.status === 'error' && <BackendDown error={state.error} onRetry={state.reload} />}
      {state.status === 'data' && <PrivacyBody data={state.data} />}
    </SettingsCard>
  );
}

function PrivacyBody({ data }: { data: ApiAboutResponse }) {
  return (
    <ul className="settings-points">
      <li>
        <h3>Synthetic data only</h3>
        <p>{regimeClaim(data.data_regime)}</p>
      </li>
      <li>
        <h3>No real experiment data</h3>
        <p>
          Real or private facility artifacts are out of scope for this prototype and require written
          data-governance approval before they could be read, indexed, or sent anywhere. What the
          code enforces is narrower than that policy: file upload is refused outright, with no file
          parsed at all, while the CSV preview and the record validator do read what you paste or
          pick — in memory, never stored, and logged only as an outcome, never as content. Nothing
          in the app inspects that text to judge whether it is real.
        </p>
      </li>
      <li>
        <h3>What is stored</h3>
        <p>
          Only the synthetic workspace: experiments, their drafts, the answers you confirm,
          exported records, and evidence sidecars. They are held on the server for this deployment
          and are not shared between deployments.
        </p>
      </li>
      <li>
        <h3>What resets</h3>
        <p>
          {persistenceClaim(data.persistence)} Assistant conversations are more ephemeral still:
          they exist only in the open browser tab and are never written down or logged.
        </p>
      </li>
      <li>
        <h3>No telemetry or analytics</h3>
        <p>
          Nothing about your session is measured, collected, or transmitted. The app makes no
          third-party network requests, loads nothing from a CDN, and has no cloud sync.
        </p>
      </li>
      <li>
        <h3>No external model calls</h3>
        <p>
          There is no language model in this build. The assistant answers from a bounded,
          deterministic catalog over local data, and refuses anything outside it rather than
          guessing. Nothing you type is sent to a model provider.
        </p>
      </li>
      <li>
        <h3>Project Memory boundary</h3>
        <p>
          Project Memory reads a committed, sanitized snapshot of served repository content. It
          returns navigational leads and provenance to verify — never a correctness ruling — and it
          cannot mark a record valid, change one, or authorize an export.
        </p>
      </li>
      <li>
        <h3>Record truth boundary</h3>
        <p>
          Validity and export are decided only by the official ISAAC v{data.record_schema_version}{' '}
          schema and the deterministic validators, working from evidence you confirmed. Advisory
          surfaces never override that.
        </p>
      </li>
      <li>
        <h3>Authentication boundary</h3>
        <p>
          The app has no accounts, no sign-in, and no user profiles, and none of this is
          configurable here. Access can be restricted in two places: by the environment this build
          is deployed into, and by an optional shared key the backend requires when an operator sets
          one. That key belongs to the deployment rather than to any user, and the app never
          displays it. This screen has no way to report whether either restriction is active.
        </p>
      </li>
    </ul>
  );
}

// --- About ------------------------------------------------------------------

const IN_REPO_DOCS = [
  'CLAUDE.md',
  'AGENTS.md',
  'README.md',
  'docs/mentor-brief.md',
  'schema/PROVENANCE.md',
];

function shortCommit(commit: string | null): string {
  if (!commit) return 'not set';
  return commit.length > 12 ? commit.slice(0, 12) : commit;
}

function AboutTab({ state }: { state: AboutState }) {
  return (
    <SettingsCard
      icon={
        <CircleHelp size={18} strokeWidth={2} aria-hidden="true" className="settings-card-icon" />
      }
      headingId="settings-about-heading"
      title="About"
      sub="App identity and provenance — and where truth ends and memory/advisory help begins."
    >
      {state.status === 'loading' && <LoadingPanel label="Loading app info…" />}
      {state.status === 'error' && <BackendDown error={state.error} onRetry={state.reload} />}
      {state.status === 'data' && <AboutDetail data={state.data} />}
    </SettingsCard>
  );
}

function AboutDetail({ data }: { data: ApiAboutResponse }) {
  const rows: { label: string; value: ReactNode }[] = [
    { label: 'App version', value: <span className="mono">{data.app_version}</span> },
    {
      label: 'Build commit',
      value: data.build_commit ? (
        <span className="settings-commit">
          <span className="mono settings-commit-short">{shortCommit(data.build_commit)}</span>
          {data.build_commit.length > 12 && (
            <span className="mono settings-commit-full">{data.build_commit}</span>
          )}
        </span>
      ) : (
        <span className="settings-commit-note">not set (no build identity injected)</span>
      ),
    },
    {
      label: 'ISAAC record schema',
      value: <span className="mono">v{data.record_schema_version}</span>,
    },
    { label: 'Runtime mode', value: <span className="mono">{data.runtime_mode}</span> },
    { label: 'Data regime', value: <span className="mono">{data.data_regime}</span> },
    { label: 'Persistence', value: <span className="mono">{data.persistence}</span> },
    { label: 'Core', value: <span className="mono">{data.core}</span> },
  ];
  return (
    <>
      <h3 className="settings-subheading">Identity</h3>
      <dl className="settings-figures">
        {rows.map((row) => (
          <Figure key={row.label} label={row.label} value={row.value} />
        ))}
      </dl>
      <p className="settings-figures-caption">
        Every value above is served by <code className="mono">GET /api/about</code> and rendered
        verbatim; this screen computes none of them. A build with no deploy identity injected says
        so rather than showing a plausible-looking commit.
      </p>

      <h3 className="settings-subheading">Authority</h3>
      <div className="settings-provenance-note">
        <p>
          <strong>Truth vs. memory.</strong> Record validity, export, and audit are decided ENTIRELY
          by the deterministic core (the official ISAAC v{data.record_schema_version} schema, the
          draft validator, and the export/audit pipeline) — never by the assistant or by Project
          Memory. Graphify and the assistant are the memory/query plane: they surface leads,
          context, and provenance to verify, but they cannot mark a record valid, mutate it, or
          authorize export.
        </p>
        <p>
          <strong>No-guessing.</strong> Every finalized field carries either cited evidence or an
          explicit user confirmation — nothing scientific is invented. This build's data regime is
          synthetic-only; real experiment data requires separate, explicit governance approval.
        </p>
      </div>

      <h3 className="settings-subheading">In-repository documentation</h3>
      <div className="settings-docs-note">
        <ul className="settings-docs-list">
          {IN_REPO_DOCS.map((doc) => (
            <li key={doc}>
              <code className="mono">{doc}</code>
            </li>
          ))}
        </ul>
        <p className="settings-docs-caption">
          Tracked in the repository, not served as pages by this app.
        </p>
      </div>
    </>
  );
}

// --- API browser ------------------------------------------------------------

interface ApiEndpoint {
  /** Stable identity for selection: "get /api/health". */
  key: string;
  method: OpenApiMethod;
  path: string;
  group: string;
  summary?: string;
  description?: string;
  parameters: OpenApiParameter[];
  requestBody?: OpenApiRequestBody;
  responses: { code: string; description?: string; content?: Record<string, OpenApiMediaType> }[];
}

const METHOD_ORDER: OpenApiMethod[] = ['get', 'post', 'put', 'delete'];

/** The path segment right after `/api/` (or the first non-parameter segment
 * when that marker is absent) — a deterministic, no-guessing grouping key
 * derived straight from the real schema, never a hand-maintained tag map
 * (this backend does not assign OpenAPI `tags`). */
function deriveGroup(path: string): string {
  const marker = '/api/';
  const idx = path.indexOf(marker);
  const rest = idx >= 0 ? path.slice(idx + marker.length) : path.replace(/^\/+/, '');
  const segment = rest.split('/').find((s) => s.length > 0 && !s.startsWith('{'));
  return segment ?? 'root';
}

function flattenOpenApi(schema: ApiOpenApiResponse): ApiEndpoint[] {
  const rows: ApiEndpoint[] = [];
  for (const [path, item] of Object.entries(schema.paths ?? {})) {
    for (const method of METHOD_ORDER) {
      const op = item?.[method];
      if (!op) continue;
      rows.push({
        key: `${method} ${path}`,
        method,
        path,
        group: deriveGroup(path),
        summary: op.summary,
        description: op.description,
        parameters: op.parameters ?? [],
        requestBody: op.requestBody,
        responses: Object.entries(op.responses ?? {})
          .map(([code, res]) => ({
            code,
            description: res?.description,
            content: res?.content,
          }))
          .sort((a, b) => a.code.localeCompare(b.code)),
      });
    }
  }
  rows.sort(
    (a, b) =>
      a.group.localeCompare(b.group) ||
      a.path.localeCompare(b.path) ||
      a.method.localeCompare(b.method),
  );
  return rows;
}

/** Consecutive runs of one group, carrying each row's index in the FLAT
 *  filtered list so the roving cursor spans the whole list, not each group. */
function groupRows(
  rows: ApiEndpoint[],
): { key: string; rows: { row: ApiEndpoint; index: number }[] }[] {
  const groups: { key: string; rows: { row: ApiEndpoint; index: number }[] }[] = [];
  rows.forEach((row, index) => {
    const last = groups[groups.length - 1];
    if (last && last.key === row.group) last.rows.push({ row, index });
    else groups.push({ key: row.group, rows: [{ row, index }] });
  });
  return groups;
}

function ApiTab({ state }: { state: OpenApiState }) {
  return (
    <SettingsCard
      icon={
        <LayoutList size={18} strokeWidth={2} aria-hidden="true" className="settings-card-icon" />
      }
      headingId="settings-apidocs-heading"
      title="API"
      sub="Generated live from this app's own OpenAPI contract — the exact routes an authenticated caller can reach, never a hand-maintained duplicate."
    >
      {state.status === 'loading' && <LoadingPanel label="Loading API documentation…" />}
      {state.status === 'error' && <BackendDown error={state.error} onRetry={state.reload} />}
      {state.status === 'data' && <ApiBrowser schema={state.data} />}
    </SettingsCard>
  );
}

const API_DETAIL_ID = 'settings-api-detail';
const API_DETAIL_NAME_ID = 'settings-api-detail-name';
const API_LIST_HEADING_ID = 'settings-api-list-heading';

const endpointRowId = (key: string) => `settings-api-row-${key.replace(/[^a-zA-Z0-9]+/g, '-')}`;
const groupHeadingId = (key: string) => `settings-api-group-${key.replace(/[^a-zA-Z0-9]+/g, '-')}`;

function ApiBrowser({ schema }: { schema: ApiOpenApiResponse }) {
  const [query, setQuery] = useState('');
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [focusIndex, setFocusIndex] = useState(0);

  const rows = useMemo(() => flattenOpenApi(schema), [schema]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (r) => r.path.toLowerCase().includes(q) || (r.summary ?? '').toLowerCase().includes(q),
    );
  }, [rows, query]);

  const groups = useMemo(() => groupRows(filtered), [filtered]);

  // Selection follows the filter without an effect: the explicitly selected
  // endpoint when it is still visible, otherwise the first visible one,
  // otherwise nothing. Never an endpoint the user cannot see in the list.
  const selected =
    filtered.find((r) => r.key === selectedKey) ?? (filtered.length > 0 ? filtered[0] : null);

  const cursor = filtered.length === 0 ? 0 : Math.min(focusIndex, filtered.length - 1);

  /** Roving tabindex: exactly ONE row is in the tab order; Arrow/Home/End move
   *  that cursor without selecting. Same contract as the Schema Reference
   *  Fields list and the Concepts master list — one interaction model. */
  const onListKeyDown = useCallback(
    (e: ReactKeyboardEvent<HTMLButtonElement>, index: number) => {
      let next: number | null = null;
      if (e.key === 'ArrowDown') next = Math.min(index + 1, filtered.length - 1);
      else if (e.key === 'ArrowUp') next = Math.max(index - 1, 0);
      else if (e.key === 'Home') next = 0;
      else if (e.key === 'End') next = filtered.length - 1;
      if (next === null || filtered.length === 0) return;
      e.preventDefault();
      setFocusIndex(next);
      (document.getElementById(endpointRowId(filtered[next].key)) as HTMLButtonElement | null)
        ?.focus();
    },
    [filtered],
  );

  const contractLine = [
    `OpenAPI ${schema.openapi}`,
    schema.info?.title,
    schema.info?.version ? `v${schema.info.version}` : null,
  ]
    .filter(Boolean)
    .join(' · ');

  return (
    <>
      <p className="settings-source-line mono">{contractLine}</p>

      <div className="settings-search" role="search">
        <label className="settings-search-label" htmlFor="api-docs-search">
          Search endpoints
        </label>
        <div className="settings-search-input-wrap">
          <Search size={14} strokeWidth={2.2} aria-hidden="true" className="settings-search-icon" />
          <input
            id="api-docs-search"
            type="search"
            className="settings-search-input"
            placeholder="Filter by path or summary…"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedKey(null);
              setFocusIndex(0);
            }}
          />
        </div>
      </div>

      {/* The ONLY live region on this surface — the loading panel it replaces
          is gone by the time this renders. */}
      <p className="settings-doc-count" aria-live="polite">
        {filtered.length} of {rows.length} endpoint{rows.length === 1 ? '' : 's'}
      </p>

      {filtered.length === 0 && (
        <p className="settings-doc-empty">No endpoints match &ldquo;{query}&rdquo;.</p>
      )}

      {filtered.length > 0 && (
        <div className="api-browser-split">
          {/* Named the same way the detail pane is, so both halves of the
              master-detail pair announce what they are. */}
          <section className="api-browser-master" aria-labelledby={API_LIST_HEADING_ID}>
            <h3 id={API_LIST_HEADING_ID} className="api-browser-pane-heading">
              Endpoints
              <span className="api-browser-pane-count mono">{groups.length} groups</span>
            </h3>
            <div className="api-browser-list">
              {groups.map((group) => (
                <section
                  className="api-browser-group"
                  key={group.key}
                  aria-labelledby={groupHeadingId(group.key)}
                >
                  <h4 id={groupHeadingId(group.key)} className="api-browser-group-heading">
                    {group.key}
                    <span className="api-browser-group-count">{group.rows.length}</span>
                  </h4>
                  <ul className="api-browser-rows">
                    {group.rows.map(({ row, index }) => (
                      <ApiEndpointRow
                        key={row.key}
                        row={row}
                        selected={selected?.key === row.key}
                        tabIndex={index === cursor ? 0 : -1}
                        onSelect={() => {
                          setSelectedKey(row.key);
                          setFocusIndex(index);
                        }}
                        onKeyDown={(e) => onListKeyDown(e, index)}
                      />
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          </section>

          {/* `tabIndex={-1}`: a programmatic focus target that adds no tab stop;
              its accessible name is the selected endpoint's own heading. */}
          <div
            className="api-browser-detail"
            id={API_DETAIL_ID}
            role="region"
            tabIndex={-1}
            aria-labelledby={API_DETAIL_NAME_ID}
          >
            {selected && <ApiEndpointDetail row={selected} schema={schema} />}
          </div>
        </div>
      )}
    </>
  );
}

function MethodBadge({ method }: { method: OpenApiMethod }) {
  // The method is carried by the TEXT itself; the tint is secondary only.
  return (
    <span className={`api-docs-method api-docs-method-${method}`}>{method.toUpperCase()}</span>
  );
}

function ApiEndpointRow({
  row,
  selected,
  tabIndex,
  onSelect,
  onKeyDown,
}: {
  row: ApiEndpoint;
  selected: boolean;
  tabIndex: number;
  onSelect: () => void;
  onKeyDown: (e: ReactKeyboardEvent<HTMLButtonElement>) => void;
}) {
  // Selection comes from the native <button> (browsers synthesize a click from
  // Enter and Space); `onKeyDown` only moves the roving cursor.
  return (
    <li className="api-browser-row">
      <button
        id={endpointRowId(row.key)}
        type="button"
        className={`api-browser-rowbtn${selected ? ' selected' : ''}`}
        aria-current={selected ? 'true' : undefined}
        aria-controls={API_DETAIL_ID}
        tabIndex={tabIndex}
        onClick={onSelect}
        onKeyDown={onKeyDown}
      >
        <MethodBadge method={row.method} />
        <span className="api-browser-rowtext">
          <code className="mono api-docs-path">{row.path}</code>
          {row.summary && <span className="api-docs-summary-text">{row.summary}</span>}
        </span>
      </button>
    </li>
  );
}

/** Resolve a local `#/components/schemas/<Name>` reference ONE level, and only
 *  when the named schema is really present. Anything else is shown verbatim —
 *  a missing target is never replaced with an invented shape. */
function resolveSchema(
  value: unknown,
  schema: ApiOpenApiResponse,
): { value: unknown; resolvedFrom: string | null } {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const ref = (value as { $ref?: unknown }).$ref;
    if (typeof ref === 'string') {
      const match = /^#\/components\/schemas\/(.+)$/.exec(ref);
      const target = match ? schema.components?.schemas?.[match[1]] : undefined;
      if (match && target !== undefined) return { value: target, resolvedFrom: match[1] };
    }
  }
  return { value, resolvedFrom: null };
}

function ApiEndpointDetail({ row, schema }: { row: ApiEndpoint; schema: ApiOpenApiResponse }) {
  return (
    <>
      <h3 id={API_DETAIL_NAME_ID} className="api-browser-detail-name">
        <MethodBadge method={row.method} />
        <code className="mono api-browser-detail-path">{row.path}</code>
      </h3>
      {row.summary && <p className="api-browser-detail-summary">{row.summary}</p>}
      {row.description && <p className="api-docs-description">{row.description}</p>}

      <section className="api-browser-section">
        <h4 className="api-browser-section-heading">Parameters</h4>
        {row.parameters.length > 0 ? (
          <div className="api-docs-params-wrap">
            <table className="api-docs-params">
              <caption className="sr-only">Parameters for {row.path}</caption>
              <thead>
                <tr>
                  <th scope="col">Name</th>
                  <th scope="col">In</th>
                  <th scope="col">Required</th>
                </tr>
              </thead>
              <tbody>
                {row.parameters.map((p) => (
                  <tr key={`${p.in}:${p.name}`}>
                    <td className="mono">{p.name}</td>
                    <td>{p.in}</td>
                    <td>{p.required ? 'Yes' : 'No'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="api-docs-no-params">No parameters.</p>
        )}
      </section>

      {row.requestBody && (
        <section className="api-browser-section">
          <h4 className="api-browser-section-heading">Request body</h4>
          {row.requestBody.description && (
            <p className="api-browser-section-note">{row.requestBody.description}</p>
          )}
          <p className="api-browser-section-note">
            {row.requestBody.required ? 'Required.' : 'Optional.'}
          </p>
          <ContentBlocks content={row.requestBody.content} schema={schema} idBase="reqbody" />
        </section>
      )}

      {row.responses.length > 0 && (
        <section className="api-browser-section">
          <h4 className="api-browser-section-heading">Responses</h4>
          <ul className="api-browser-responses">
            {row.responses.map((res) => (
              <li key={res.code} className="api-browser-response">
                <span className="api-browser-status mono">{res.code}</span>
                <div className="api-browser-response-body">
                  {res.description && (
                    <p className="api-browser-section-note">{res.description}</p>
                  )}
                  <ContentBlocks
                    content={res.content}
                    schema={schema}
                    idBase={`res-${res.code}`}
                  />
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      <p className="api-browser-detail-source">
        Rendered verbatim from <code className="mono">GET /api/openapi</code> — this app's own
        generated contract.
      </p>
    </>
  );
}

/** Per-media-type schema + example disclosures. Collapsed by default so the
 *  detail pane never becomes a wall of JSON. */
function ContentBlocks({
  content,
  schema,
  idBase,
}: {
  content?: Record<string, OpenApiMediaType>;
  schema: ApiOpenApiResponse;
  idBase: string;
}) {
  const entries = Object.entries(content ?? {});
  if (entries.length === 0) return null;
  return (
    <>
      {entries.map(([mediaType, media]) => {
        const resolved = resolveSchema(media?.schema, schema);
        const examples = collectExamples(media);
        return (
          <div className="api-browser-media" key={`${idBase}:${mediaType}`}>
            <p className="api-browser-mediatype mono">{mediaType}</p>
            {resolved.value !== undefined && (
              <details className="api-browser-disclosure">
                <summary>
                  Schema
                  {resolved.resolvedFrom && (
                    <span className="api-browser-reftag mono">{resolved.resolvedFrom}</span>
                  )}
                </summary>
                <pre className="mono api-browser-json">{stringify(resolved.value)}</pre>
              </details>
            )}
            {examples.map((ex) => (
              <details className="api-browser-disclosure" key={ex.name}>
                <summary>
                  Example
                  <span className="api-browser-reftag mono">{ex.name}</span>
                </summary>
                <pre className="mono api-browser-json">{stringify(ex.value)}</pre>
              </details>
            ))}
          </div>
        );
      })}
    </>
  );
}

function collectExamples(media?: OpenApiMediaType): { name: string; value: unknown }[] {
  if (!media) return [];
  const out: { name: string; value: unknown }[] = [];
  if (media.example !== undefined) out.push({ name: 'example', value: media.example });
  for (const [name, entry] of Object.entries(media.examples ?? {})) {
    out.push({ name, value: entry?.value });
  }
  return out;
}

function stringify(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2) ?? String(value);
  } catch {
    // A cyclic or non-serializable fragment is reported honestly, never faked.
    return 'This fragment could not be displayed as JSON.';
  }
}
