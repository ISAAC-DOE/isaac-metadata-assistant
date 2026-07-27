import './screens.css';
import {
  useMemo,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from 'react';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { LoadingPanel, BackendDown } from '../components/FetchStates';
import { CircleHelp, LayoutList, ChevronRight, Shield, Settings } from '../components/icons';
import { LABELS } from '../lib/labels';
import { api } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import {
  ABOUT_RESPONSE_FIELDS,
  REPO_DOCS,
  REPO_DOCS_CAPTION,
  SETTINGS_SOURCE_ENDPOINTS,
  settingsAboutCopy,
  settingsConcepts,
  settingsFactsFrom,
} from '../lib/settingsContent';
import type { ApiAboutResponse, ApiOpenApiResponse } from '../lib/types';
import { ApiDocsPanel } from './settings/ApiDocs';
import { ApiKeysPanel } from './settings/ApiKeys';
import { RovingTabs } from './settings/apiShared';

/**
 * Settings — P36R Slice 9 reorganised this surface into four local page tabs
 * (Overview · Data & Privacy · About · API) using the SAME tablist contract as
 * Governance & Safety and Project Memory (`.section-tabs`/`.section-tab`,
 * roving tabindex, Arrow/Home/End), not a fourth variant.
 *
 * P36V PR3 slice B gave the four tabs one job each, because six claims were
 * being authored two or three times over:
 *
 *   · Overview      — the live runtime snapshot, plus a ONE-LINE summary of
 *                     each boundary and links into the tab that defines it.
 *   · Data & Privacy — the ONE canonical home of the detailed definitions.
 *   · About          — identity and provenance only, with the raw values
 *                     (full commit SHA, response field names, source
 *                     endpoints, repository doc paths) behind Technical Details.
 *   · API            — two sub-surfaces (slice C): API Keys, an honest
 *                     unavailable state, and Documentation, a Quick Start plus
 *                     the master-detail browser over `GET /api/openapi` plus a
 *                     Connect an Agent guide.
 *
 * Every sentence on the first three tabs comes from `lib/settingsContent.ts`,
 * which holds each canonical definition exactly once so the wording cannot
 * drift between tabs; `settings-page.test.tsx` pins that each definition is
 * rendered exactly once across the whole page.
 *
 * There are NO user-adjustable settings in this build, and none were invented
 * to fill a page: every tab is informational, and Overview says so plainly.
 * Overview and About render `GET /api/about` verbatim; the API tab renders the
 * app's own generated contract — never a hand-maintained duplicate, no CDN, no
 * Swagger UI/ReDoc.
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
        {/* Slice C: was "Local Configuration", which promised settings to adjust
            beside copy that says there are none. This names what the page is. */}
        <span className="eyebrow">About This Build</span>
        <h1>{LABELS.navSettings}</h1>
        <p>View this build's runtime status, data boundaries, provenance, and API access.</p>

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
 * A summary, not a second copy. Overview renders the live runtime snapshot and
 * the ONE-LINE `summary` of each boundary, then links into the tab that owns
 * the definition. It renders no `detail` string at all — that is what stops the
 * old two-and-three-times duplication from creeping back.
 *
 * Authentication deliberately has no status row: `ApiKeyAuthMiddleware` is only
 * active when the backend was started with a shared key configured, and the
 * browser cannot read that. So the boundary appears as a summary that states
 * the uncertainty, never as an "active"/"inactive" claim the app cannot verify.
 */
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
      sub="What this running build is right now — the runtime values below are read from the app itself. This build has no user-adjustable settings."
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
  const concepts = useMemo(() => settingsConcepts(settingsFactsFrom(data)), [data]);
  return (
    <>
      <h3 className="settings-subheading">Runtime Status</h3>
      <dl className="settings-figures">
        <Figure label="App Version" value={<span className="mono">{data.app_version}</span>} />
        <Figure label="Build Commit" value={<CommitShort commit={data.build_commit} />} />
        <Figure
          label="Record Schema"
          value={<span className="mono">v{data.record_schema_version}</span>}
        />
        <Figure label="Runtime Mode" value={<span className="mono">{data.runtime_mode}</span>} />
        <Figure label="Data Regime" value={<span className="mono">{data.data_regime}</span>} />
        <Figure label="Persistence" value={<span className="mono">{data.persistence}</span>} />
        <Figure label="Core" value={<span className="mono">{data.core}</span>} />
      </dl>

      <h3 className="settings-subheading">Boundaries at a Glance</h3>
      <dl className="settings-summary-list">
        {concepts.map((concept) => (
          <div className="settings-summary-row" key={concept.id}>
            <dt className="settings-summary-label">{concept.heading}</dt>
            <dd className="settings-summary-text">{concept.summary}</dd>
          </div>
        ))}
      </dl>

      <nav className="settings-jump" aria-label="More settings detail">
        <button type="button" className="settings-jump-btn" onClick={() => onSelectTab('privacy')}>
          Data &amp; Privacy Detail
          <ChevronRight size={13} strokeWidth={2.2} aria-hidden="true" />
        </button>
        <button type="button" className="settings-jump-btn" onClick={() => onSelectTab('about')}>
          Version &amp; Provenance
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

/** The conventional 12-character short SHA — never truncates a shorter string. */
function shortCommit(commit: string): string {
  return commit.length > 12 ? commit.slice(0, 12) : commit;
}

/**
 * The build commit as every tab shows it: the SHORT SHA only. The full SHA is
 * rendered in exactly one place on the page — About's Technical Details
 * disclosure — so the identity rows stay scannable and the raw value is still
 * one keystroke away. A build with no identity injected says so rather than
 * showing a plausible-looking commit.
 */
function CommitShort({ commit }: { commit: string | null }) {
  if (!commit) {
    return <span className="settings-commit-note">not set (no build identity injected)</span>;
  }
  return <span className="mono settings-commit-short">{shortCommit(commit)}</span>;
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

/**
 * The ONE canonical home of the detailed definitions. Every string comes from
 * `settingsConcepts()`; nothing here is authored inline, and no `detail` is
 * rendered by any other tab. Secondary edge cases sit behind a native
 * `<details>` — never an honesty caveat, which would let the visible copy
 * overstate what the code checks.
 */
function PrivacyBody({ data }: { data: ApiAboutResponse }) {
  const concepts = useMemo(() => settingsConcepts(settingsFactsFrom(data)), [data]);
  return (
    <ul className="settings-points">
      {concepts.map((concept) => (
        <li key={concept.id}>
          <h3>{concept.heading}</h3>
          <p>{concept.detail}</p>
          {concept.more && (
            <details className="settings-more">
              <summary>{concept.more.label}</summary>
              <p>{concept.more.text}</p>
            </details>
          )}
        </li>
      ))}
    </ul>
  );
}

// --- About ------------------------------------------------------------------

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

/**
 * Identity and provenance only. Runtime Mode / Data Regime / Persistence are
 * NOT repeated here — they are runtime status, which Overview owns — and the
 * data/privacy definitions are not repeated either. Everything raw (the FULL
 * commit SHA, the response field names, the source endpoints, the repository
 * documentation paths) sits behind Technical Details, the same collapsed
 * `<details>` pattern the Concepts detail pane uses.
 */
function AboutDetail({ data }: { data: ApiAboutResponse }) {
  const copy = useMemo(() => settingsAboutCopy(settingsFactsFrom(data)), [data]);
  return (
    <>
      <h3 className="settings-subheading">Identity</h3>
      <dl className="settings-figures">
        <Figure label="App Version" value={<span className="mono">{data.app_version}</span>} />
        <Figure label="Build Commit" value={<CommitShort commit={data.build_commit} />} />
        <Figure
          label="ISAAC Record Schema"
          value={<span className="mono">v{data.record_schema_version}</span>}
        />
        <Figure label="Core" value={<span className="mono">{data.core}</span>} />
      </dl>
      <p className="settings-figures-caption">{copy.identityCaption}</p>

      <h3 className="settings-subheading">Authority</h3>
      <div className="settings-provenance-note">
        <p>
          <strong>{copy.truthVsMemoryLabel}.</strong> {copy.truthVsMemory}
        </p>
        <p>
          <strong>{copy.noGuessingLabel}.</strong> {copy.noGuessing}
        </p>
      </div>

      <details className="settings-technical">
        <summary>Technical Details</summary>
        <dl className="settings-technical-figures">
          <div className="settings-technical-figure">
            <dt>Build Commit (Full)</dt>
            <dd className="mono settings-commit-full">{data.build_commit ?? 'not set'}</dd>
          </div>
          <div className="settings-technical-figure">
            <dt>Response Fields</dt>
            <dd>
              <ul className="settings-docs-list">
                {ABOUT_RESPONSE_FIELDS.map((field) => (
                  <li key={field}>
                    <code className="mono">{field}</code>
                  </li>
                ))}
              </ul>
            </dd>
          </div>
          <div className="settings-technical-figure">
            <dt>Source Endpoints</dt>
            <dd>
              <ul className="settings-docs-list">
                {SETTINGS_SOURCE_ENDPOINTS.map((endpoint) => (
                  <li key={endpoint}>
                    <code className="mono">{endpoint}</code>
                  </li>
                ))}
              </ul>
            </dd>
          </div>
          <div className="settings-technical-figure">
            <dt>Repository Documentation</dt>
            <dd>
              <ul className="settings-docs-list">
                {REPO_DOCS.map((doc) => (
                  <li key={doc}>
                    <code className="mono">{doc}</code>
                  </li>
                ))}
              </ul>
              <p className="settings-docs-caption">{REPO_DOCS_CAPTION}</p>
            </dd>
          </div>
        </dl>
      </details>
    </>
  );
}

// --- API tab: sub-navigation over two sub-surfaces --------------------------

/**
 * The API tab is two jobs, so it is two sub-surfaces rather than one long page:
 *
 *   · API Keys      — an honest UNAVAILABLE state. The backend has one shared
 *                     credential read from the environment and no operation that
 *                     creates, lists, revokes or rotates one, so nothing here
 *                     generates a key, writes to browser storage, or pretends a
 *                     control works (see `settings/ApiKeys.tsx`).
 *   · Documentation — Quick Start, the Endpoint Explorer, and Connect an Agent,
 *                     every fact derived from `GET /api/openapi`.
 *
 * The sub-tabs use the SAME accessible contract as the page tabs above and as
 * Governance & Safety — `RovingTabs`, which is that contract extracted rather
 * than a third reimplementation of it.
 *
 * API Keys is first and selected by default: it answers the question that brings
 * someone to a Settings "API" tab (can I get a key?) truthfully and immediately,
 * and links straight into Documentation. Only Documentation needs the fetch, so
 * the loading and unreachable states live in that panel alone.
 */
type ApiSubTab = 'keys' | 'docs';

const API_SUB_TABS: { id: ApiSubTab; label: string }[] = [
  { id: 'keys', label: 'API Keys' },
  { id: 'docs', label: 'Documentation' },
];

const apiSubTabId = (id: ApiSubTab) => `settings-api-subtab-${id}`;
const apiSubPanelId = (id: ApiSubTab) => `settings-api-subpanel-${id}`;

function ApiTab({ state }: { state: OpenApiState }) {
  const [sub, setSub] = useState<ApiSubTab>('keys');
  return (
    <SettingsCard
      icon={
        <LayoutList size={18} strokeWidth={2} aria-hidden="true" className="settings-card-icon" />
      }
      headingId="settings-apidocs-heading"
      title="API"
      sub="How a program reaches this build, and what this build can and cannot issue. The reference is generated from the app's own OpenAPI contract, never a hand-maintained duplicate."
    >
      <RovingTabs
        className="api-subtabs"
        label="API sections"
        tabs={API_SUB_TABS}
        active={sub}
        onSelect={setSub}
        tabId={apiSubTabId}
        panelId={apiSubPanelId}
      />

      {sub === 'keys' && (
        <div
          className="api-subpanel"
          id={apiSubPanelId('keys')}
          role="tabpanel"
          aria-labelledby={apiSubTabId('keys')}
        >
          <ApiKeysPanel onOpenDocumentation={() => setSub('docs')} />
        </div>
      )}

      {sub === 'docs' && (
        <div
          className="api-subpanel"
          id={apiSubPanelId('docs')}
          role="tabpanel"
          aria-labelledby={apiSubTabId('docs')}
        >
          {state.status === 'loading' && <LoadingPanel label="Loading API documentation…" />}
          {state.status === 'error' && <BackendDown error={state.error} onRetry={state.reload} />}
          {state.status === 'data' && (
            <ApiDocsPanel schema={state.data} onOpenKeys={() => setSub('keys')} />
          )}
        </div>
      )}
    </SettingsCard>
  );
}
