import './screens.css';
import { useMemo, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { LoadingPanel, BackendDown, DiagnosticsPanel } from '../components/FetchStates';
import {
  CircleHelp,
  Compass,
  LayoutList,
  ChevronRight,
  Lock,
  Network,
  Shield,
  Settings,
} from '../components/icons';
import { LABELS } from '../lib/labels';
import { api } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import { ROUTES, SETTINGS_TAB_PARAM, isSettingsTab, type SettingsTabId } from '../lib/routes';
import {
  ABOUT_RESPONSE_FIELDS,
  REPO_DOCS,
  REPO_DOCS_CAPTION,
  SETTINGS_SOURCE_ENDPOINTS,
  settingsAboutCopy,
  settingsConcepts,
  settingsFactsFrom,
} from '../lib/settingsContent';
import { diagnosticsAppFrom, diagnosticsMemoryFrom } from '../lib/diagnostics';
import type { ApiAboutResponse, ApiGraphStatus, ApiOpenApiResponse } from '../lib/types';
import { MCP_CONNECT_COPY } from '../lib/mcpConnectContent';
import { ApiExplorerPanel, ApiQuickStartPanel } from './settings/ApiDocs';
import { ApiKeysPanel } from './settings/ApiKeys';
import { ConnectYourAgentPanel } from './settings/ConnectYourAgent';
import { AssistantCompanionSection } from './settings/AssistantCompanion';
import { HelpAndTutorialPanel } from './settings/HelpAndTutorial';
import { TUTORIAL_ANCHORS } from '../lib/tutorialSteps';

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
 *   · API Access     — everything about REACHING this build as a program: the
 *                     honest key-unavailable status, the access model, Quick
 *                     Start, and the Connect an Agent guide.
 *   · Endpoint Explorer — the master-detail browser over `GET /api/openapi`.
 *   · Connect Your Agent — ISAAC's agent (machine-callable tool) interface,
 *                     described to a human: what an agent will be able to do,
 *                     what it will never be able to do, and the honest state of
 *                     this deployment, which is that no agent can reach it.
 *                     It states a state and offers no action, and it renders no
 *                     endpoint, no activity date and no Revoke control, because
 *                     none of the three exists. See
 *                     `lib/mcpConnectContent.ts` for the reasoning per claim.
 *
 * P36V-1 slice 12 made those last two SEPARATE top-level tabs and deleted the
 * `keys | docs` sub-tab layer. The Endpoint Explorer used to sit three levels
 * deep (page tab → sub-tab → section) with no URL of its own; nothing in the app
 * linked to it. A second tab and a `?tab=` value are strictly simpler than a
 * nested tablist, and they make the browser itself linkable.
 *
 * ROUTING: the active tab is DERIVED from `?tab=` (see `lib/routes.ts`), exactly
 * as `GovernancePage` derives its own — one convention, not two. It is a query
 * VALUE, never a path literal, so the router `basename` ('' locally, '/krish'
 * deployed) is honoured automatically and no screen hard-codes a base path.
 * Selecting a tab PUSHES (Governance replaces, deliberately, because its tab
 * changes arrive from elsewhere): here the five tabs are five destinations a
 * reader links to and steps Back through, so Back/Forward walks the tabs.
 *
 * Every sentence on the first three tabs comes from `lib/settingsContent.ts`,
 * which holds each canonical definition exactly once so the wording cannot
 * drift between tabs; `settings-page.test.tsx` pins that each definition is
 * rendered exactly once across the whole page.
 *
 * There are NO user-adjustable settings in this build, and none were invented
 * to fill a page: every tab is informational, and Overview says so plainly.
 * Overview and About render `GET /api/about` verbatim; the two API tabs render
 * the app's own generated contract — never a hand-maintained duplicate, no CDN,
 * no Swagger UI/ReDoc.
 *
 * These THREE PAGE-LEVEL fetches (`/api/about`, `/api/openapi`,
 * `/api/graph/status`) are issued once at page level so switching tabs is pure
 * client state and never re-hits the backend. The third feeds Copy Diagnostics'
 * memory-provenance rows on About; it is the cheap status endpoint, never the
 * graph payload.
 *
 * THE PAGE NOW ISSUES A FOURTH READ, AND IT IS DELIBERATELY NOT ONE OF THE THREE.
 * `AssistantCompanionSection` fetches `/api/runtime/assistant-companion` at the
 * SECTION level, against the convention above and for the reason the convention
 * exists. That route re-reads its environment variable on every request,
 * precisely so an operator who sets it does not have to restart anything.
 *
 * BE PRECISE ABOUT WHAT THE CLIENT SIDE OF THAT BUYS, because an earlier
 * revision of this paragraph was not. `useFetch(…, [])` pins the answer for the
 * life of the SECTION MOUNT, which on this tab is the page load unless the
 * reader navigates away and back. So section-level placement does not make the
 * answer live; it makes the answer re-read on every remount, where page-level
 * placement would re-read it once per page load however often the reader
 * returned. That is a narrower benefit than "no staleness", and it is the true
 * one — the non-caching that matters is the ROUTE's, and it is verified there.
 * The remount behaviour is asserted rather than assumed, by
 * `assistant-companion.test.tsx`. The sentence above
 * said "all" and was true when it was written — it is narrowed here rather than
 * deleted, because "issued once at page level" remains the rule for those three
 * and a future reader must be able to see that the fourth is an argued
 * exception rather than a drift.
 */

type SettingsTab = SettingsTabId;

const SETTINGS_TABS: { id: SettingsTab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'privacy', label: 'Data & Privacy' },
  { id: 'about', label: 'About' },
  { id: 'api', label: 'API Access' },
  { id: 'explorer', label: 'Endpoint Explorer' },
  /* Connect Your Agent — the machine-interface surface, next to the other two
     tabs about reaching this build as a program. It states a deployment state
     and offers no action, so it belongs with the readout tabs rather than
     after the one thing on the page a reader acts on. */
  { id: 'mcp', label: 'Connect Your Agent' },
  /* R0 — the LAST tab (it was the sixth; Connect Your Agent above made it the
     seventh, and the reason it is last is unchanged by that). It is the ONE
     permanent home of the guided walkthrough's
     replay control: the first-run offer on My Experiments disappears for good
     once the walkthrough is finished, so without a fixed home a reader who
     completed it could never get it back. */
  { id: 'help', label: LABELS.settingsTabHelp },
];

const tabId = (id: SettingsTab) => `settings-tab-${id}`;
const panelId = (id: SettingsTab) => `settings-tabpanel-${id}`;

export function SettingsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get(SETTINGS_TAB_PARAM);
  const activeTab: SettingsTab = isSettingsTab(requested) ? requested : 'overview';

  const about = useFetch(() => api.getAbout(), []);
  const openapi = useFetch(() => api.getOpenApi(), []);
  /* Copy Diagnostics' memory-provenance rows (About tab). Issued HERE with the
     other two rather than inside the About panel, because a panel-scoped fetch
     would re-hit the backend on every switch back to About — the one thing this
     page's fetch layout deliberately avoids. `GET /api/graph/status` is the cheap
     provider-agnostic status endpoint, not the graph payload. */
  const graphStatus = useFetch(() => api.getGraphStatus(), []);

  /** Client-side only: `setSearchParams` never reloads the document, and the
   *  value is a query param, so the router's basename is preserved untouched. */
  function setActiveTab(tab: SettingsTab) {
    const next = new URLSearchParams(searchParams);
    next.set(SETTINGS_TAB_PARAM, tab);
    setSearchParams(next);
  }

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
          <AboutTab state={about} graphStatus={graphStatus} />
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
          <ApiAccessTab state={openapi} onOpenExplorer={() => setActiveTab('explorer')} />
        </div>
      )}

      {activeTab === 'explorer' && (
        <div
          className="settings-panel"
          id={panelId('explorer')}
          role="tabpanel"
          aria-labelledby={tabId('explorer')}
          tabIndex={0}
        >
          <EndpointExplorerTab state={openapi} />
        </div>
      )}

      {activeTab === 'mcp' && (
        <div
          className="settings-panel"
          id={panelId('mcp')}
          role="tabpanel"
          aria-labelledby={tabId('mcp')}
          tabIndex={0}
        >
          <ConnectYourAgentTab onOpenExplorer={() => setActiveTab('explorer')} />
        </div>
      )}

      {activeTab === 'help' && (
        <div
          className="settings-panel"
          id={panelId('help')}
          role="tabpanel"
          aria-labelledby={tabId('help')}
          tabIndex={0}
        >
          <HelpAndTutorialTab />
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
    <div
      className="section-tabs"
      role="tablist"
      aria-label="Settings & API sections"
      /* The walkthrough's "where Settings and API access live" anchor: the
         tablist, because that is what the step is actually describing. */
      data-tutorial-anchor={TUTORIAL_ANCHORS.settingsSections}
    >
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
type GraphStatusState = ReturnType<typeof useFetch<ApiGraphStatus>>;

// --- Overview ---------------------------------------------------------------

/**
 * A summary, not a second copy. Overview renders the live runtime snapshot and
 * the ONE-LINE `summary` of each boundary, then links into the tab that owns
 * the definition. It renders no `detail` string at all — that is what stops the
 * old two-and-three-times duplication from creeping back.
 *
 * THE FRAMING SENTENCE USED TO OVER-CLAIM, and the fix is to scope it rather
 * than to make every row live. It read "the runtime values below are read from
 * the app itself", over SEVEN rows of which THREE were hardcoded literals — not
 * one. (~~TWO~~ — corrected in review: `about()` returns seven fields and
 * `persistence`, `data_regime` and `core` were all fixed literals. Miscounting
 * the set a scoping sentence is scoping is the same class of defect as the
 * sentence itself.) `persistence` was `"ephemeral"` unconditionally, which was
 * false on the hosted deployment (`docs/evidence/hosted-qa-2026-08-27.md` §3)
 * and is now DERIVED from `experiment_storage.state`, so that row has become
 * what the sentence always claimed it was.
 *
 * `data_regime` HAS NOT AND DELIBERATELY MUST NOT. It stays the literal
 * `"synthetic-only"`, which is defensible as a SCOPED claim: `runtime_mode`
 * independently refuses to boot in `real` mode, and the mode has never meant "no
 * real data exists anywhere in the process" — production-derived records transit
 * pod memory during the read-only diagnostic. Changing that value is a different
 * decision with its own guard tests, and making it live "for consistency" would
 * be a claim nobody has established.
 *
 * So the sentence now says which rows are live and which are fixed, instead of
 * asserting liveness over a block that contains both. `App Version`, `Record
 * Schema`, `Data Regime` and `Core` are all fixed for a given build; `Runtime
 * Mode`, `Persistence` and `Build Commit` are resolved per request.
 *
 * ~~"`Build Commit` ... fixed for a given build"~~ — corrected in review, in the
 * same change that wrote it. `routes._build_commit()` is read from the
 * environment on EVERY request (`ISAAC_BUILD_COMMIT`, else
 * `RAILWAY_GIT_COMMIT_SHA`, else `null`), and its own docstring says "read live
 * (not cached) so it reflects the running env" — it is a property of the
 * DEPLOYMENT, not of the build, and the same image redeployed with a different
 * value reports the different value. The `/api/about` description written in this
 * same change already grouped it with the live reads, so two surfaces authored
 * together partitioned the same field differently; the frontend half was the
 * wrong one.
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
      sub="What this running build is right now. Runtime Mode, Persistence and Build Commit are read live from this deployment; the other rows are fixed properties of this build. This build has no user-adjustable settings."
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
          API Access
          <ChevronRight size={13} strokeWidth={2.2} aria-hidden="true" />
        </button>
        <button type="button" className="settings-jump-btn" onClick={() => onSelectTab('explorer')}>
          Endpoint Explorer
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
    <>
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
      {/* P2 — the reciprocal of Governance & Safety → Policy's canonical-home
          pointer. This tab owns the data-handling DEFINITIONS; the policy those
          definitions serve, the standalone Validator and the schema reference
          live on one screen, and a reader who arrives here from Governance
          needs a way back that is not the browser's. It states no claim — it is
          navigation only, so nothing on it can drift from the definitions
          above. */}
      <nav className="settings-jump" aria-label="Related governance surfaces">
        <Link className="settings-jump-btn" to={ROUTES.governance}>
          Governance &amp; Safety
          <ChevronRight size={13} strokeWidth={2.2} aria-hidden="true" />
        </Link>
      </nav>
    </>
  );
}

// --- About ------------------------------------------------------------------

function AboutTab({ state, graphStatus }: { state: AboutState; graphStatus: GraphStatusState }) {
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
      {state.status === 'data' && <AboutDetail data={state.data} graphStatus={graphStatus} />}
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
function AboutDetail({
  data,
  graphStatus,
}: {
  data: ApiAboutResponse;
  graphStatus: GraphStatusState;
}) {
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

      {/*
        THE NORMAL-STATE HOME OF COPY DIAGNOSTICS.

        WHY ABOUT, and not Overview or the Help panel. About is already the tab
        whose single job is identity and provenance, and already the ONE place
        that renders raw values (the full commit SHA, the response field names,
        the source endpoints) — a pasteable dump of exactly those values belongs
        beside them. Overview is a summary surface that states no raw value; Help
        is a floating panel where a multi-line monospace fallback block has
        nowhere to go. It sits just BELOW Technical Details rather than inside it,
        so reaching it is one activation and not two.

        It is the SAME control over the SAME generator the failure state uses
        (`components/FetchStates.tsx`), so the two surfaces cannot drift.

        A failing or unavailable `GET /api/graph/status` is NOT an error state
        here: the memory rows report "not available", which is the honest outcome
        and still leaves every build fact in the report.
      */}
      <DiagnosticsPanel
        app={diagnosticsAppFrom(data)}
        memory={graphStatus.status === 'data' ? diagnosticsMemoryFrom(graphStatus.data) : null}
        tab="about"
      />
    </>
  );
}

// --- API Access ---------------------------------------------------------------

/**
 * Everything about REACHING this build as a program, on one tab and each thing
 * said exactly once (P36V-1 slice 13):
 *
 *   · the STATUS — key management is unavailable, stated once, at the top;
 *   · the ACCESS MODEL, external-agent access and the hosted-authentication
 *     boundary — one compact row each (`settings/ApiKeys.tsx`);
 *   · CREATE API KEY — a genuinely `disabled` control with a programmatically
 *     associated reason, and the backend contract that would be required first
 *     behind a collapsed Technical Requirements disclosure;
 *   · QUICK START — only facts the generated contract itself carries;
 *   · CONNECT AN AGENT — the collapsed integration guide, which is also the one
 *     canonical home of the credential-safety rules.
 *
 * The endpoint browser is NOT here: it is its own tab, so this surface stays
 * short enough to read.
 *
 * The key sections need no data, so they render immediately; only the
 * contract-derived Quick Start and Connect an Agent wait on the fetch.
 */
function ApiAccessTab({
  state,
  onOpenExplorer,
}: {
  state: OpenApiState;
  onOpenExplorer: () => void;
}) {
  return (
    <SettingsCard
      icon={<Lock size={18} strokeWidth={2} aria-hidden="true" className="settings-card-icon" />}
      headingId="settings-apiaccess-heading"
      title="API Access"
      sub="What a program can and cannot do with this build, and what it needs to send."
    >
      <ApiKeysPanel onOpenExplorer={onOpenExplorer} />

      {state.status === 'loading' && <LoadingPanel label="Loading the API contract…" />}
      {state.status === 'error' && <BackendDown error={state.error} onRetry={state.reload} />}
      {state.status === 'data' && (
        <ApiQuickStartPanel schema={state.data} onOpenExplorer={onOpenExplorer} />
      )}
    </SettingsCard>
  );
}

// --- Endpoint Explorer ---------------------------------------------------------

/**
 * The master-detail browser over `GET /api/openapi`, promoted out of the old
 * Documentation sub-tab into a top-level, deep-linkable tab. Nothing else lives
 * here, so the full page measure belongs to the list and the detail pane.
 */
function EndpointExplorerTab({ state }: { state: OpenApiState }) {
  return (
    <SettingsCard
      icon={
        <LayoutList size={18} strokeWidth={2} aria-hidden="true" className="settings-card-icon" />
      }
      headingId="settings-apidocs-heading"
      title="Endpoint Explorer"
      sub="Every operation this build exposes, read from the OpenAPI document the app generates for itself."
    >
      {state.status === 'loading' && <LoadingPanel label="Loading the API contract…" />}
      {state.status === 'error' && <BackendDown error={state.error} onRetry={state.reload} />}
      {state.status === 'data' && <ApiExplorerPanel schema={state.data} />}
    </SettingsCard>
  );
}

// --- Connect Your Agent --------------------------------------------------------

/**
 * ISAAC's agent (machine-callable tool) interface, described to a human.
 *
 * Needs no fetch, and that is a property of what it reports rather than a
 * convenience: there is no agent interface in this build to ask about, so there
 * is no endpoint to probe, no session to list and no activity to read. A
 * loading state here would imply a source, and a failure state would imply
 * something had failed. Neither is true, so the panel renders immediately from
 * authored copy whose provenance it states on the page.
 */
function ConnectYourAgentTab({ onOpenExplorer }: { onOpenExplorer: () => void }) {
  return (
    <SettingsCard
      icon={<Network size={18} strokeWidth={2} aria-hidden="true" className="settings-card-icon" />}
      headingId="settings-mcp-heading"
      title="Connect Your Agent"
      sub={MCP_CONNECT_COPY.cardSub}
    >
      <ConnectYourAgentPanel onOpenExplorer={onOpenExplorer} />
      {/* THE COMPANION ARTIFACT, a SIBLING of the panel above rather than a
          section inside it, and the separation is deliberate twice over.

          It is a DIFFERENT DIRECTION: everything in the panel above is ISAAC's
          own agent interface — the tool surface a scientist's Claude would call,
          which this deployment publishes no address for. The companion is the
          other way round, an optional page a scientist opens in Claude, which
          this website neither hosts nor depends on. It is on this tab because
          its stated prerequisite is the same connector the panel's setup steps
          describe, so a reader meets both claims or neither.

          And `ConnectYourAgentPanel`'s docstring enumerates, claim by claim,
          what that panel does not render — no endpoint URL, no activity date,
          no control but one. Nesting a section that DOES render a link (when a
          deployment has one) inside that component would make its own stated
          contract false about its own subtree. As siblings under the card's
          `h2`, each keeps its own contract and its own tests.

          It reads its own live configuration; see `AssistantCompanion.tsx` for
          why that read is not hoisted to the page with the other three. */}
      <AssistantCompanionSection onOpenExplorer={onOpenExplorer} />
    </SettingsCard>
  );
}

// --- Help & Tutorial ---------------------------------------------------------

/**
 * Needs no fetch: everything on it is either authored copy or the walkthrough's
 * own browser-local completion flag. It therefore renders immediately, with no
 * loading state to flash and no failure state to invent.
 */
function HelpAndTutorialTab() {
  return (
    <SettingsCard
      icon={<Compass size={18} strokeWidth={2} aria-hidden="true" className="settings-card-icon" />}
      headingId="settings-help-heading"
      title={LABELS.settingsTabHelp}
      sub="A guided tour of the real screens, and where finishing it is remembered."
    >
      <HelpAndTutorialPanel />
    </SettingsCard>
  );
}
