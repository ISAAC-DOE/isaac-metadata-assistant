import './screens.css';
import './settings/settings-widgets.css';
import {
  useEffect,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import {
  LoadingPanel,
  BackendDown,
  COPY_DIAGNOSTICS_NOTE,
  DiagnosticsPanel,
} from '../components/FetchStates';
import { Widget } from '../components/Widget';
import { LazyDisclosure } from '../components/LazyDisclosure';
import { ChevronRight, Clock, LayoutList, Network, Settings, Shield } from '../components/icons';
import { LABELS } from '../lib/labels';
import { api } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import {
  ROUTES,
  SETTINGS_TAB_PARAM,
  resolveSettingsTab,
  type SettingsTabId,
} from '../lib/routes';
import {
  ABOUT_RESPONSE_FIELDS,
  NO_GUESSING,
  REPO_DOCS,
  REPO_DOCS_CAPTION,
  SETTINGS_SOURCE_ENDPOINTS,
  SETTINGS_WIDGET_COPY as COPY,
  dataRows,
  settingsFactsFrom,
} from '../lib/settingsContent';
import { diagnosticsAppFrom, diagnosticsMemoryFrom } from '../lib/diagnostics';
import type { ApiAboutResponse, ApiGraphStatus, ApiOpenApiResponse } from '../lib/types';
import { ApiExplorerPanel } from './settings/ApiDocs';
import { ApiKeysPanel } from './settings/ApiKeys';
import { ConnectYourAgentPanel } from './settings/ConnectYourAgent';
import { HelpAndTutorialPanel } from './settings/HelpAndTutorial';
import { TUTORIAL_ANCHORS } from '../lib/tutorialSteps';

/**
 * Settings — THREE TABS since 2026-11-02: Overview · Integrations · Advanced.
 *
 * The owner retired standing disclaimers, so the Privacy & Governance tab, the
 * Overview "Data Safety" card and the "About This Build" eyebrow went. What a
 * reader needs about their data is ONE Data card on Overview (`dataRows`), plain
 * rows written from what the running app reports. `?tab=privacy` is an alias that
 * lands on that card. Integrations shows each connection as one state line plus
 * one disclosure; Advanced is a Related Tools list, Technical Details as a bare
 * `<details>`, and the Endpoint Explorer behind a closed disclosure that the
 * `explorer` alias, a `#…` hash, and every "Endpoint Explorer" jump open.
 *
 * The history below describes the four-tab page this replaced.
 *
 * Settings — FOUR TABS OF QUESTION WIDGETS (2026-10-12), `DEC-28`'s regroup
 * built: Overview · Privacy & Governance · Integrations · Advanced.
 *
 * ── WHY IT CHANGED ─────────────────────────────────────────────────────────
 *
 * The owner suspected this page was "messed up" like the old Statistics page,
 * and a measured audit confirmed it: seven tabs, 9,168 words (3,456 visible and
 * 5,706 behind 26 disclosures), the same seven build facts on Overview AND
 * About, the same twelve boundaries stated three times (Overview, Data &
 * Privacy, Governance → Policy), and "no API keys" said six times beside a
 * disabled button. The direction was widgets — one per question, with the
 * breakdown one click away INSIDE the widget.
 *
 *   · Overview — Data Safety (four state lines, each a vetted boundary
 *     summary), This Build (version, schema, and a Build | Runtime switch over
 *     the seven facts), and the Guided Walkthrough (its replay control).
 *   · Privacy & Governance — four question widgets that hold every one of the
 *     twelve boundaries, each one's state visible as a row and its full
 *     definition in Details, plus the governance policy moved here from
 *     Governance & Safety.
 *   · Integrations — Connect Your Agent and API Access, side by side, each a
 *     state with its reference material as views.
 *   · Advanced — the Endpoint Explorer at full width, then launchers for
 *     Project Memory, the Validator, the Schema Reference and the raw values.
 *
 * EVERY RETIRED `?tab=` ID STILL RESOLVES (`lib/routes.ts`'s
 * `SETTINGS_TAB_ALIASES`): `about` and `help` land on Overview, `api` and `mcp`
 * on Integrations, `explorer` on Advanced — each scrolling the widget it pointed
 * at into view. `privacy` was renamed in place. An absent or unrecognised value
 * still falls back to Overview without throwing.
 *
 * ── THE TABLIST, AND THE ONE IT IS NOT ──────────────────────────────────────
 *
 * The page tablist keeps the SAME contract as Governance & Safety, Project
 * Memory and Statistics (`.section-tabs`/`.section-tab`, roving tabindex,
 * Arrow/Home/End, automatic activation). Selecting a tab PUSHES, so
 * Back/Forward walks the tabs. The widgets' own view switches are `aria-pressed`
 * toggle groups (`Widget`'s `viewSwitcher="buttons"`), never a second tablist —
 * `settings-page.test.tsx` refuses one, the Endpoint Explorer's Code Examples
 * included. With four tabs there is no longer a
 * group to mark, so the "Advanced" group label inside the old seven-tab row went
 * with the row: Advanced is a tab now.
 *
 * ── WHAT MOVED, NOT WHAT WENT ──────────────────────────────────────────────
 *
 * Every claim the old tabs made is still rendered. Some moved behind a widget's
 * info toggle (provenance and explanation: never a state, never a figure), some
 * into a widget's Details (definitions), some into a view a reader opens. What
 * is GONE is structural: the jump-button nav, the disabled "Create API Key"
 * button and the empty key list it sat over, the seven repeated provenance
 * sublabels (one clock mark and a legend now), and the second copy of the build
 * facts. Each removal is recorded where it happened.
 *
 * ── FETCHES ────────────────────────────────────────────────────────────────
 *
 * The THREE page-level reads (`/api/about`, `/api/openapi`, `/api/graph/status`)
 * are issued once here, so switching tabs is pure client state and never re-hits
 * the backend. `AssistantCompanionSection` reads `/api/runtime/assistant-companion`
 * at the section level, deliberately — that route re-reads its environment on
 * every request, so it is re-read on every remount of the section; see that file.
 * The Connect Your Agent widget reads `/api/health` through the shared,
 * module-cached `useHealthState`, which the top bar has already primed.
 *
 * There are NO user-adjustable settings in this build, and none were invented
 * to fill a page; This Build says so in its description.
 */

/**
 * `short` is the label a NARROW tab row shows (2026-10-18): at 390px the four full
 * labels wrapped onto two rows. Only the visible text changes — the full label is
 * the tab's `sr-only` name at every width, so the accessible name never changes
 * with the viewport (`.section-tab-label-full` / `-short` in `settings-widgets.css`).
 */
const SETTINGS_TABS: { id: SettingsTabId; label: string; short?: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'integrations', label: 'Integrations' },
  { id: 'advanced', label: 'Advanced' },
];

const tabId = (id: SettingsTabId) => `settings-tab-${id}`;
const panelId = (id: SettingsTabId) => `settings-tabpanel-${id}`;

type AboutState = ReturnType<typeof useFetch<ApiAboutResponse>>;
type OpenApiState = ReturnType<typeof useFetch<ApiOpenApiResponse>>;
type GraphStatusState = ReturnType<typeof useFetch<ApiGraphStatus>>;

export function SettingsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();
  const { tab: activeTab, widget: aliasWidget } = resolveSettingsTab(
    searchParams.get(SETTINGS_TAB_PARAM),
  );

  const about = useFetch(() => api.getAbout(), []);
  const openapi = useFetch(() => api.getOpenApi(), []);
  /* Copy Diagnostics' memory-provenance rows (This Build). Issued HERE with the
     other two rather than inside the widget, because a widget-scoped fetch would
     re-hit the backend on every switch back to Overview — the one thing this
     page's fetch layout deliberately avoids. `GET /api/graph/status` is the cheap
     provider-agnostic status endpoint, not the graph payload. */
  const graphStatus = useFetch(() => api.getGraphStatus(), []);

  /** Client-side only: `setSearchParams` never reloads the document, and the
   *  value is a query param, so the router's basename is preserved untouched.
   *  A tab chosen here always writes its CANONICAL id. */
  function setActiveTab(tab: SettingsTabId) {
    const next = new URLSearchParams(searchParams);
    next.set(SETTINGS_TAB_PARAM, tab);
    setSearchParams(next);
  }

  /** Every "Endpoint Explorer" jump: Advanced, with the explorer's disclosure open. */
  function openExplorer() {
    const next = new URLSearchParams(searchParams);
    next.set(SETTINGS_TAB_PARAM, 'explorer');
    setSearchParams(next);
  }
  const explorerOpen = aliasWidget === EXPLORER_HEADING_ID || location.hash !== '';

  /*
   * A RETIRED TAB ID LANDS ON ITS WIDGET. `/settings?tab=mcp` used to open a tab
   * that was nothing but that one surface; it now opens Integrations, where the
   * Connect Your Agent widget may sit second in a stacked phone layout. So the
   * region the old link named is scrolled into view. Focus is deliberately NOT
   * moved: the walkthrough's own step navigates here and manages focus itself,
   * and stealing it would strand a keyboard reader outside the tour.
   * `location.key` re-runs it for a repeat navigation to the same URL, and the
   * two page-level reads re-run it as they settle: the widgets above the target
   * grow when their data arrives, and a scroll taken before that would land
   * short of it (measured at 390px: `?tab=help` stopped on Data Safety).
   */
  useEffect(() => {
    if (!aliasWidget) return;
    const heading = document.getElementById(aliasWidget);
    const region = heading?.closest('section') ?? heading;
    // jsdom does not implement scrollIntoView — call it only where it exists.
    region?.scrollIntoView?.({ block: 'start' });
  }, [location.key, aliasWidget, about.status, openapi.status]);

  return (
    <AppShell
      variant="full"
      topBar={<TopBar variant="home" />}
      sidebar={<LeftNav active="settings" />}
      mainPad="pad"
      width="wide"
    >
      <div className="placeholder">
        {/* ~~"About This Build" eyebrow~~ — cut 2026-11-02: it named one widget, not
            the page. */}
        <h1>{LABELS.navSettings}</h1>
        {/* ~~"View this build's runtime status, data boundaries, provenance, and
            API access."~~ — dropped 2026-10-18 (re-review): the four tab labels
            directly beneath it say the same thing, and the eyebrow names the page. */}

        <SettingsSectionTabs active={activeTab} onSelect={setActiveTab} />
      </div>

      <div
        className="settings-panel"
        id={panelId(activeTab)}
        role="tabpanel"
        aria-labelledby={tabId(activeTab)}
        tabIndex={0}
      >
        {activeTab === 'overview' && <OverviewTab state={about} graphStatus={graphStatus} />}
        {activeTab === 'integrations' && (
          <IntegrationsTab state={openapi} onOpenExplorer={openExplorer} />
        )}
        {activeTab === 'advanced' && (
          <AdvancedTab state={openapi} about={about} explorerOpen={explorerOpen} />
        )}
      </div>
    </AppShell>
  );
}

// --- the page tabs (same contract as GovernancePage / ProjectMemory) --------

function SettingsSectionTabs({
  active,
  onSelect,
}: {
  active: SettingsTabId;
  onSelect: (tab: SettingsTabId) => void;
}) {
  /* ~~A measured `data-overflowing` fade and a `scrollIntoView` of the selected
     tab~~ — both RETIRED 2026-10-18 with the sideways-scrolling row they served:
     the row now always FITS (one row to 441px, two rows of two below — see
     `settings-widgets.css`), so no tab, selected or not, can be off-screen. */

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
      className="section-tabs settings-section-tabs"
      role="tablist"
      aria-label="Settings sections"
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
            {tab.short ? (
              /* The NAME is the `sr-only` full label — the shared visually-hidden
                 class the layout probes already allowlist — and the two visible
                 forms are `aria-hidden`, one shown per width. So the accessible
                 name never changes with the viewport, and no bespoke clip rule
                 hides text a readability probe would rightly flag. */
              <>
                <span className="sr-only">{tab.label}</span>
                <span className="section-tab-label-full" aria-hidden="true">
                  {tab.label}
                </span>
                <span className="section-tab-label-short" aria-hidden="true">
                  {tab.short}
                </span>
              </>
            ) : (
              tab.label
            )}
          </button>
        );
      })}
    </div>
  );
}

/** A widget body that waits on `GET /api/about`, honestly. */
function AboutGate({
  state,
  children,
}: {
  state: AboutState;
  children: (data: ApiAboutResponse) => ReactNode;
}) {
  if (state.status === 'loading') return <LoadingPanel label="Loading app info…" />;
  if (state.status === 'error') return <BackendDown error={state.error} onRetry={state.reload} />;
  return <>{children(state.data)}</>;
}

/** A launcher link. A real `<a href>`, because each opens another ROUTE — a
 *  button would be unopenable in a new tab and unlinkable. */
function OpenLink({ to, children }: { to: string | { search: string }; children: ReactNode }) {
  return (
    <Link to={to} className="settings-open-link">
      {children}
      <ChevronRight size={13} strokeWidth={2.2} aria-hidden="true" />
    </Link>
  );
}

// --- Overview -----------------------------------------------------------------

/**
 * Three widgets: Data (where your records and exports live — four plain rows from
 * `dataRows`), This Build, and the Guided Walkthrough.
 */
function OverviewTab({ state, graphStatus }: { state: AboutState; graphStatus: GraphStatusState }) {
  return (
    <div className="settings-grid settings-grid-overview">
      <Widget
        id="settings-data-heading"
        className="settings-widget-data"
        title={COPY.dataTitle}
        icon={<Shield size={18} strokeWidth={2} />}
      >
        <AboutGate state={state}>
          {(data) => (
            <dl className="settings-rows">
              {dataRows(settingsFactsFrom(data)).map((row) => (
                <div className="settings-row" key={row.label}>
                  <dt className="settings-row-label">{row.label}</dt>
                  <dd className="settings-row-text">{row.text}</dd>
                </div>
              ))}
            </dl>
          )}
        </AboutGate>
      </Widget>

      <BuildWidget state={state} graphStatus={graphStatus} />

      <HelpAndTutorialPanel />
    </div>
  );
}

/**
 * THIS BUILD — version and schema as the headline, and the seven facts
 * `GET /api/about` reports behind a Build | Runtime switch.
 *
 * ── PROVENANCE, ONE MARK INSTEAD OF SEVEN SUBLABELS ─────────────────────────
 *
 * Each row used to carry a visible word, "read per request" or "fixed for this
 * build", because the card's supporting sentence had been WRONG TWICE about
 * which rows were which (once claiming every row was live over three literals,
 * once grouping `Build Commit` with the fixed rows when it is read from the
 * environment per request). That per-row decision is kept — it is checkable —
 * and only its PRESENTATION changes: a row read per request carries a clock
 * mark, the legend is in the widget's info, and every row still states its
 * provenance in words to assistive technology. `Build Commit`, `Runtime Mode`
 * and `Persistence` are the three live ones; the switch partitions the facts
 * by what a reader asks (which build / how is it running), not by provenance,
 * which is why the mark is still needed in both views.
 *
 * `data_regime` stays the literal `"synthetic-only"` deliberately: a SCOPED
 * claim that `runtime_mode` independently enforces. Making it live "for
 * consistency" would be a claim nobody has established.
 */
function BuildWidget({ state, graphStatus }: { state: AboutState; graphStatus: GraphStatusState }) {
  return (
    <Widget
      id="settings-build-heading"
      className="settings-widget-build"
      title={COPY.buildTitle}
      icon={<Settings size={18} strokeWidth={2} />}
      info={
        <>
          <p>{COPY.provenanceLegend}</p>
          <p>
            <strong>{NO_GUESSING.label}.</strong> {NO_GUESSING.text}
          </p>
          <p>{COPY_DIAGNOSTICS_NOTE}</p>
        </>
      }
      headline={
        state.status === 'data' ? (
          <>
            <span className="widget-figure">ISAAC {state.data.app_version}</span>
            <span className="widget-figure-unit">Schema v{state.data.record_schema_version}</span>
          </>
        ) : undefined
      }
      footer={
        state.status === 'data' ? (
          /* THE NORMAL-STATE HOME OF COPY DIAGNOSTICS, beside the identity it
             reports — the same control over the same generator the failure state
             uses (`components/FetchStates.tsx`). */
          <DiagnosticsPanel
            app={diagnosticsAppFrom(state.data)}
            memory={graphStatus.status === 'data' ? diagnosticsMemoryFrom(graphStatus.data) : null}
            tab="overview"
            showNote={false}
          />
        ) : undefined
      }
    >
      {state.status !== 'data' ? (
        <AboutGate state={state}>{() => null}</AboutGate>
      ) : (
        <>
          {/* The Build rows, then Runtime one press away (2026-11-02): the widget
              used to switch between two views inside a tabbed page. */}
          <dl className="settings-figures settings-facts">
            <Figure
              label="App Version"
              value={<span className="mono">{state.data.app_version}</span>}
              source="build"
            />
            <Figure
              label="Build Commit"
              value={<CommitShort commit={state.data.build_commit} />}
              source="live"
            />
            <Figure
              label="Record Schema"
              value={<span className="mono">v{state.data.record_schema_version}</span>}
              source="build"
            />
            <Figure label="Core" value={<span className="mono">{state.data.core}</span>} source="build" />
          </dl>
          <details className="settings-runtime">
            <summary>{COPY.buildRuntime}</summary>
            <dl className="settings-figures settings-facts">
              <Figure
                label="Runtime Mode"
                value={<span className="mono">{state.data.runtime_mode}</span>}
                source="live"
              />
              <Figure
                label="Data Regime"
                value={<span className="mono">{state.data.data_regime}</span>}
                source="build"
              />
              <Figure
                label="Persistence"
                value={<span className="mono">{state.data.persistence}</span>}
                source="live"
              />
            </dl>
          </details>
        </>
      )}
    </Widget>
  );
}

/**
 * One labelled figure, with its provenance.
 *
 * `source` is `'live'` for a value this deployment resolves per request and
 * `'build'` for one fixed for a given image. The words are always present for
 * assistive technology (`.settings-figure-source`, visually hidden); a live row
 * also carries a visible clock mark, and the widget's info says what it means.
 * Omitted entirely where the caller does not know — guessing a provenance is
 * how two wrong sentences about these rows were written.
 */
function Figure({
  label,
  value,
  source,
}: {
  label: string;
  value: ReactNode;
  source?: 'live' | 'build';
}) {
  return (
    <div className="settings-figure">
      <dt>
        {/* The label is ALWAYS its own element, provenance or not, so a query
            for the label text matches the label rather than the label with the
            provenance word concatenated onto it. */}
        <span className="settings-figure-label">{label}</span>
        {source === 'live' ? (
          <Clock
            size={12}
            strokeWidth={2.2}
            aria-hidden="true"
            className="settings-provenance-mark"
          />
        ) : null}
        {source ? (
          <span className="settings-figure-source sr-only">
            {source === 'live' ? COPY.provenanceLive : COPY.provenanceFixed}
          </span>
        ) : null}
      </dt>
      <dd>{value}</dd>
    </div>
  );
}

/** The conventional 12-character short SHA — never truncates a shorter string. */
function shortCommit(commit: string): string {
  return commit.length > 12 ? commit.slice(0, 12) : commit;
}

/**
 * The build commit as Overview shows it: the SHORT SHA only. The full SHA is
 * rendered in exactly one place on the page — Advanced → Technical Details. A
 * build with no identity injected says so rather than showing a plausible-looking
 * commit.
 */
function CommitShort({ commit }: { commit: string | null }) {
  if (!commit) {
    return <span className="settings-commit-note">not set</span>;
  }
  return <span className="mono settings-commit-short">{shortCommit(commit)}</span>;
}

// --- Integrations -------------------------------------------------------------

/**
 * Two ways in, side by side: ISAAC's agent (machine-callable tool) interface,
 * and its HTTP API. They are different mechanisms with different answers about
 * authentication, and each widget's copy points at the other — which is why
 * they share a tab now rather than sitting three tabs apart.
 */
function IntegrationsTab({
  state,
  onOpenExplorer,
}: {
  state: OpenApiState;
  onOpenExplorer: () => void;
}) {
  return (
    <div className="settings-grid settings-grid-integrations">
      <ConnectYourAgentPanel />
      <ApiKeysPanel state={state} onOpenExplorer={onOpenExplorer} />
    </div>
  );
}

// --- Advanced -------------------------------------------------------------------

/** The Endpoint Explorer widget's heading id — the `explorer` alias's target. */
const EXPLORER_HEADING_ID = 'settings-apidocs-heading';

/**
 * The developer surfaces. ~~A lead note, three launcher cards and a Technical
 * Details card, then the explorer open at full width~~ — 2026-11-02: one Related
 * Tools link list, Technical Details as a bare `<details>`, and the Endpoint
 * Explorer behind a closed disclosure. `explorerOpen` (the `explorer` alias, a
 * `#…` hash, or an "Endpoint Explorer" jump from Integrations) opens it on arrival.
 */
function AdvancedTab({
  state,
  about,
  explorerOpen,
}: {
  state: OpenApiState;
  about: AboutState;
  explorerOpen: boolean;
}) {
  const tools: { to: string; title: string; sub: string }[] = [
    { to: ROUTES.memory, title: COPY.memoryTitle, sub: COPY.memorySub },
    { to: `${ROUTES.governance}?tab=validator`, title: COPY.validatorTitle, sub: COPY.validatorSub },
    { to: `${ROUTES.governance}?tab=schema`, title: COPY.schemaTitle, sub: COPY.schemaSub },
  ];
  return (
    <div className="settings-grid settings-grid-advanced">
      <Widget
        id="settings-related-heading"
        title={COPY.relatedTitle}
        icon={<Network size={18} strokeWidth={2} />}
      >
        <ul className="settings-related">
          {tools.map((tool) => (
            <li key={tool.title} className="settings-related-item">
              <OpenLink to={tool.to}>{tool.title}</OpenLink>
              <span className="settings-related-sub">{tool.sub}</span>
            </li>
          ))}
        </ul>
        <TechnicalDetails state={about} />
      </Widget>

      <Widget
        id={EXPLORER_HEADING_ID}
        className="settings-explorer"
        span="full"
        title={COPY.explorerTitle}
        icon={<LayoutList size={18} strokeWidth={2} />}
        sub={COPY.explorerSub}
      >
        <LazyDisclosure summary="Browse Every Operation" defaultOpen={explorerOpen}>
          {() => (
            <>
              {state.status === 'loading' && <LoadingPanel label="Loading the API contract…" />}
              {state.status === 'error' && <BackendDown error={state.error} onRetry={state.reload} />}
              {state.status === 'data' && <ApiExplorerPanel schema={state.data} />}
            </>
          )}
        </LazyDisclosure>
      </Widget>
    </div>
  );
}

/**
 * The raw values — the FULL commit SHA, the response field names, the source
 * endpoints, the repository documentation paths — moved here from About's
 * Technical Details, because a raw value is a developer's (`DEC-56`). The full
 * SHA is still rendered in exactly one place on the page, and it is this one.
 */
function TechnicalDetails({ state }: { state: AboutState }) {
  return (
    <details className="settings-technical" id="settings-technical-heading">
      <summary>{COPY.technicalTitle}</summary>
      <dl className="settings-technical-figures">
        <div className="settings-technical-figure">
          <dt>Build Commit (Full)</dt>
          <dd className="mono settings-commit-full">
            {state.status === 'data' ? (state.data.build_commit ?? 'not set') : '—'}
          </dd>
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
  );
}
