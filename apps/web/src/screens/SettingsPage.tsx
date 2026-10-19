import './screens.css';
import './settings/settings-widgets.css';
import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
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
import {
  ChevronRight,
  CircleHelp,
  Clock,
  Download,
  FileJson,
  History,
  LayoutList,
  Network,
  Settings,
  Shield,
  ShieldCheck,
  Table2,
  Upload,
} from '../components/icons';
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
  GOVERNANCE_POLICY,
  OVERVIEW_SAFETY_ROWS,
  PRIVACY_QUESTIONS,
  REPO_DOCS,
  REPO_DOCS_CAPTION,
  SETTINGS_SOURCE_ENDPOINTS,
  SETTINGS_WIDGET_COPY as COPY,
  settingsAboutCopy,
  settingsConcepts,
  settingsFactsFrom,
  syntheticWorkspaceRow,
  type SettingsConcept,
} from '../lib/settingsContent';
import { diagnosticsAppFrom, diagnosticsMemoryFrom } from '../lib/diagnostics';
import type { ApiAboutResponse, ApiGraphStatus, ApiOpenApiResponse } from '../lib/types';
import { ApiExplorerPanel } from './settings/ApiDocs';
import { ApiKeysPanel } from './settings/ApiKeys';
import { ConnectYourAgentPanel } from './settings/ConnectYourAgent';
import { HelpAndTutorialPanel } from './settings/HelpAndTutorial';
import { TUTORIAL_ANCHORS } from '../lib/tutorialSteps';

/**
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
  { id: 'privacy', label: 'Privacy & Governance', short: 'Privacy' },
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

  /** The same move as a real link: a query that keeps every other parameter. */
  function tabSearch(tab: SettingsTabId): string {
    const next = new URLSearchParams(searchParams);
    next.set(SETTINGS_TAB_PARAM, tab);
    return `?${next.toString()}`;
  }

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
        {/* Slice C: was "Local Configuration", which promised settings to adjust
            beside copy that says there are none. This names what the page is. */}
        <span className="eyebrow">About This Build</span>
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
        {activeTab === 'overview' && (
          <OverviewTab
            state={about}
            graphStatus={graphStatus}
            privacySearch={tabSearch('privacy')}
          />
        )}
        {activeTab === 'privacy' && <PrivacyTab state={about} />}
        {activeTab === 'integrations' && (
          <IntegrationsTab state={openapi} onOpenExplorer={() => setActiveTab('advanced')} />
        )}
        {activeTab === 'advanced' && <AdvancedTab state={openapi} about={about} />}
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
  /* Whether the row is WIDER than its box — the one fact CSS cannot read, and the
     only thing the trailing fade may claim. At 390px the short labels fit and no
     fade is drawn; at 320px the row scrolls and the fade says there is more. */
  const listRef = useRef<HTMLDivElement>(null);
  const [overflowing, setOverflowing] = useState(false);
  useLayoutEffect(() => {
    const el = listRef.current;
    if (!el) return;
    const measure = () => setOverflowing(el.scrollWidth > el.clientWidth + 1);
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  /* THE SELECTED TAB IS ALWAYS ON SCREEN (WCAG 2.4.11, re-review 2026-10-18). At
     320px the row scrolls sideways, and `?tab=advanced` — or End / ArrowLeft from
     Overview — left it at scrollLeft 0 with the selected, focused tab out of view.
     `nearest` moves the row only as far as it must and, the tab row being on
     screen, does not move the page; a no-op whenever the tab is already visible. */
  useEffect(() => {
    document
      .getElementById(tabId(active))
      ?.scrollIntoView?.({ inline: 'nearest', block: 'nearest' });
  }, [active]);

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
      ref={listRef}
      className="section-tabs settings-section-tabs"
      data-overflowing={overflowing ? 'true' : undefined}
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

function conceptsById(data: ApiAboutResponse): Map<string, SettingsConcept> {
  return new Map(settingsConcepts(settingsFactsFrom(data)).map((c) => [c.id, c]));
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
 * Three widgets, and no definition. The Data Safety widget renders ONE-LINE
 * concept summaries — the vetted lines, not new sentences — grouped into the four
 * questions a scientist brings to a settings page, and links to the tab that
 * defines each in full. It renders no `detail` at all: that is what stops the old
 * two-and-three-times duplication from creeping back.
 *
 * Authentication deliberately has no status row: `ApiKeyAuthMiddleware` is only
 * active when the backend was started with a shared key configured, and the
 * browser cannot read that. So the boundary appears (on Privacy & Governance) as
 * a summary that states the uncertainty, never as an "active"/"inactive" claim.
 */
function OverviewTab({
  state,
  graphStatus,
  privacySearch,
}: {
  state: AboutState;
  graphStatus: GraphStatusState;
  privacySearch: string;
}) {
  return (
    <div className="settings-grid settings-grid-overview">
      <Widget
        id="settings-safety-heading"
        className="settings-widget-safety"
        title={COPY.safetyTitle}
        icon={<Shield size={18} strokeWidth={2} />}
        sub={COPY.safetySub}
        info={<p>{COPY.safetyInfo}</p>}
        headline={
          state.status === 'data' ? (
            <span className="widget-state">
              {state.data.data_regime === 'synthetic-only'
                ? COPY.safetyHeadline
                : COPY.safetyHeadlineOther}
            </span>
          ) : undefined
        }
        footer={<OpenLink to={{ search: privacySearch }}>{COPY.safetyAll}</OpenLink>}
      >
        <AboutGate state={state}>
          {(data) => {
            const concepts = conceptsById(data);
            return (
              <dl className="settings-rows">
                {OVERVIEW_SAFETY_ROWS.map((row) => (
                  <div className="settings-row" key={row.label}>
                    <dt className="settings-row-label">{row.label}</dt>
                    <dd className="settings-row-text">
                      {row.items
                        .map((item) =>
                          'concept' in item
                            ? (concepts.get(item.concept)?.summary ?? '')
                            : GOVERNANCE_POLICY[item.policy].summary,
                        )
                        .join(' ')}
                    </dd>
                  </div>
                ))}
              </dl>
            );
          }}
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
  const copy = useMemo(
    () => (state.status === 'data' ? settingsAboutCopy(settingsFactsFrom(state.data)) : null),
    [state],
  );
  return (
    <Widget
      id="settings-build-heading"
      className="settings-widget-build"
      title={COPY.buildTitle}
      icon={<Settings size={18} strokeWidth={2} />}
      /* ~~sub={COPY.buildSub}~~ — moved into the info panel 2026-10-18 (re-review:
         Overview trims). The claim is kept, first, where the widget explains itself. */
      info={
        copy ? (
          <>
            <p>{COPY.buildNoSettings}</p>
            <p>{COPY.provenanceLegend}</p>
            <p>{copy.identityCaption}</p>
            <p>
              <strong>{copy.truthVsMemoryLabel}.</strong> {copy.truthVsMemory}
            </p>
            <p>
              <strong>{copy.noGuessingLabel}.</strong> {copy.noGuessing}
            </p>
            <p>{COPY_DIAGNOSTICS_NOTE}</p>
          </>
        ) : (
          <>
            <p>{COPY.buildNoSettings}</p>
            <p>{COPY.provenanceLegend}</p>
          </>
        )
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
             reports. It is the SAME control over the SAME generator the failure
             state uses (`components/FetchStates.tsx`), so the two cannot drift. A
             failing `GET /api/graph/status` is not an error here: the memory rows
             report "not available", which is the honest outcome. */
          <DiagnosticsPanel
            app={diagnosticsAppFrom(state.data)}
            memory={graphStatus.status === 'data' ? diagnosticsMemoryFrom(graphStatus.data) : null}
            tab="overview"
            /* Its caption is this widget's info (below), not a second line here. */
            showNote={false}
          />
        ) : undefined
      }
      viewSwitcher="buttons"
      views={state.status === 'data' ? buildViews(state.data) : undefined}
    >
      {state.status !== 'data' && <AboutGate state={state}>{() => null}</AboutGate>}
    </Widget>
  );
}

/** The two views of This Build, over the seven facts `GET /api/about` reports. */
function buildViews(data: ApiAboutResponse) {
  return [
    {
      id: 'build',
      label: COPY.buildViewBuild,
      icon: <FileJson size={14} strokeWidth={2} />,
      content: (
        <dl className="settings-figures settings-facts">
          <Figure
            label="App Version"
            value={<span className="mono">{data.app_version}</span>}
            source="build"
          />
          <Figure label="Build Commit" value={<CommitShort commit={data.build_commit} />} source="live" />
          <Figure
            label="Record Schema"
            value={<span className="mono">v{data.record_schema_version}</span>}
            source="build"
          />
          <Figure label="Core" value={<span className="mono">{data.core}</span>} source="build" />
        </dl>
      ),
    },
    {
      id: 'runtime',
      label: COPY.buildViewRuntime,
      icon: <Clock size={14} strokeWidth={2} />,
      content: (
        <dl className="settings-figures settings-facts">
          <Figure
            label="Runtime Mode"
            value={<span className="mono">{data.runtime_mode}</span>}
            source="live"
          />
          <Figure
            label="Data Regime"
            value={<span className="mono">{data.data_regime}</span>}
            source="build"
          />
          <Figure
            label="Persistence"
            value={<span className="mono">{data.persistence}</span>}
            source="live"
          />
        </dl>
      ),
    },
  ];
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
    return <span className="settings-commit-note">not set (no build identity injected)</span>;
  }
  return <span className="mono settings-commit-short">{shortCommit(commit)}</span>;
}

// --- Privacy & Governance -------------------------------------------------------

/**
 * THE ONE CANONICAL HOME of the data-handling definitions, and since 2026-10-12
 * of the governance policy as well — four question widgets.
 *
 * ── TWO LAYERS, AND THE RULE THAT SEPARATES THEM ────────────────────────────
 *
 * Each concept is a VISIBLE ROW: its heading and its `summary`, the vetted
 * one-liner. A privacy or data-handling state is never something a reader has
 * to open something to find (`DEC-35`), and each summary carries its own
 * load-bearing caveat ("cannot tell real data from synthetic", "the upload block
 * never checks whether what it blocked was real", "this screen cannot report
 * whether access is restricted"), so no visible row overstates what the code does.
 *
 * Each concept's `detail` — the full definition, verbatim — sits in the widget's
 * Details, under its own heading, with the inner `concept.more` drawers inside
 * it. The Details trigger reads "Full Definitions": a TOPIC, never a claim, so no
 * summary is ever promoted into a disclosure label.
 *
 * The three governance-policy paragraphs (`GOVERNANCE_POLICY`) are the old
 * Governance & Safety → Policy tab, moved here. "What a Review Tool Reads" and
 * the diagnostic are visible rows in their ONE-LINE form (2026-10-18, review:
 * each paragraph ran 50–70 words in the first screenful) — the diagnostic's line
 * keeps every bound visible: read-only, aggregates only, no record displayed,
 * nothing sent to a model — with each full paragraph, verbatim, in Details beside
 * "Workspace Scope". The Synthetic-Only Mode and No Real Experiment Data rows,
 * which stated one boundary twice, are one visible row (`syntheticWorkspaceRow`);
 * both definitions stay, each under its own heading.
 */
const PRIVACY_ICONS: Record<(typeof PRIVACY_QUESTIONS)[number]['id'], ReactNode> = {
  enter: <Upload size={18} strokeWidth={2} />,
  kept: <History size={18} strokeWidth={2} />,
  leaves: <Download size={18} strokeWidth={2} />,
  truth: <ShieldCheck size={18} strokeWidth={2} />,
};

function PrivacyTab({ state }: { state: AboutState }) {
  /* The governance policy is static, so its rows render at once; only the
     concept rows wait on `/api/about`, because the persistence-dependent ones
     are written from what the running app reports. */
  const facts = state.status === 'data' ? settingsFactsFrom(state.data) : null;
  const concepts = state.status === 'data' ? conceptsById(state.data) : null;
  return (
    <div className="settings-grid settings-grid-privacy">
      {PRIVACY_QUESTIONS.map((question, index) => {
        const all = concepts
          ? question.concepts
              .map((id) => concepts.get(id))
              .filter((c): c is SettingsConcept => c !== undefined)
          : [];
        const merged = question.merged ?? [];
        const rows = all.filter((c) => !merged.includes(c.id));
        const mergedRow = facts && merged.length > 0 ? syntheticWorkspaceRow(facts) : null;
        const definitionCount =
          question.concepts.length + question.policyRows.length + question.policyDetails.length;
        return (
          <Widget
            key={question.id}
            id={`settings-privacy-${question.id}-heading`}
            title={question.title}
            icon={PRIVACY_ICONS[question.id]}
            details={{
              summary: COPY.fullDefinitions,
              meta: String(definitionCount),
              content: (
                <div className="settings-definitions">
                  {all.map((concept) => (
                    <section className="settings-definition" key={concept.id}>
                      <h4 className="settings-definition-heading">{concept.heading}</h4>
                      <p className="settings-definition-text">{concept.detail}</p>
                      {concept.more && (
                        <details className="settings-more">
                          <summary>{concept.more.label}</summary>
                          <p>{concept.more.text}</p>
                        </details>
                      )}
                    </section>
                  ))}
                  {/* A policy ROW's full paragraph, then the Details-only ones.
                      The visible row above states the paragraph's one-line form
                      with every bound a reader needs at a glance. */}
                  {[...question.policyRows, ...question.policyDetails].map((id) => (
                    <section
                      className="settings-definition gov-policy-section"
                      data-policy={id}
                      key={id}
                    >
                      <h4 className="settings-definition-heading">
                        {GOVERNANCE_POLICY[id].heading}
                      </h4>
                      <p className="settings-definition-text">{GOVERNANCE_POLICY[id].text}</p>
                    </section>
                  ))}
                </div>
              ),
            }}
            footer={
              question.id === 'enter' ? (
                <OpenLink to={`${ROUTES.governance}?tab=validator`}>{COPY.validatorOpen}</OpenLink>
              ) : undefined
            }
          >
            <div className="settings-points">
              {/* The read, stated in the FIRST widget only: one loading line or
                  one failure for the tab, not four of each. */}
              {!concepts && index === 0 && state.status === 'loading' && (
                <LoadingPanel label="Loading app info…" />
              )}
              {!concepts && index === 0 && state.status === 'error' && (
                <BackendDown error={state.error} onRetry={state.reload} />
              )}
              {mergedRow && (
                <section
                  className="settings-point"
                  data-concepts={merged.join(' ')}
                  key="merged"
                >
                  <h3 className="settings-point-heading">{mergedRow.heading}</h3>
                  <p className="settings-point-text">{mergedRow.text}</p>
                </section>
              )}
              {rows.map((concept) => (
                <section className="settings-point" key={concept.id}>
                  <h3 className="settings-point-heading">{concept.heading}</h3>
                  <p className="settings-point-text">{concept.summary}</p>
                </section>
              ))}
              {question.policyRows.map((id) => (
                <section className="settings-point gov-policy-section" data-policy={id} key={id}>
                  <h3 className="settings-point-heading">{GOVERNANCE_POLICY[id].heading}</h3>
                  <p className="settings-point-text">{GOVERNANCE_POLICY[id].summary}</p>
                </section>
              ))}
            </div>
          </Widget>
        );
      })}
    </div>
  );
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
      <ConnectYourAgentPanel onOpenExplorer={onOpenExplorer} />
      <ApiKeysPanel state={state} onOpenExplorer={onOpenExplorer} />
    </div>
  );
}

// --- Advanced -------------------------------------------------------------------

/**
 * The developer surfaces, and nothing a scientist recording an experiment has to
 * visit. Four launchers first — Project Memory (`DEC-19`/`DEC-26`: demoted from
 * primary navigation, provided here), the Validator, the Schema Reference, and
 * the raw values that used to sit in About's Technical Details — then the
 * Endpoint Explorer at full width, its list and detail panes scrolling
 * independently, each no taller than the viewport.
 *
 * ~~Explorer first, launchers below it~~ — reordered 2026-10-18 (review): the
 * Explorer is a viewport tall, so the four launchers sat below a whole screen of
 * it and read as an afterthought nobody would scroll to.
 */
function AdvancedTab({ state, about }: { state: OpenApiState; about: AboutState }) {
  return (
    <>
      <p className="settings-tab-note">{COPY.advancedNote}</p>
      <div className="settings-grid settings-grid-advanced">
        <Widget
          id="settings-memory-heading"
          title={COPY.memoryTitle}
          icon={<Network size={18} strokeWidth={2} />}
          sub={COPY.memorySub}
          /* What Project Memory is NOT — it never rules on a record — is the
             Project Memory Boundary row on Privacy & Governance; here it is the
             launcher's explanation. */
          info={<p>{COPY.memoryBody}</p>}
          footer={<OpenLink to={ROUTES.memory}>{COPY.memoryOpen}</OpenLink>}
        />

        <Widget
          id="settings-validator-heading"
          title={COPY.validatorTitle}
          icon={<FileJson size={18} strokeWidth={2} />}
          sub={COPY.validatorSub}
          footer={
            <OpenLink to={`${ROUTES.governance}?tab=validator`}>{COPY.validatorOpen}</OpenLink>
          }
        />

        <Widget
          id="settings-schema-heading"
          title={COPY.schemaTitle}
          icon={<Table2 size={18} strokeWidth={2} />}
          sub={COPY.schemaSub}
          footer={<OpenLink to={`${ROUTES.governance}?tab=schema`}>{COPY.schemaOpen}</OpenLink>}
        />

        <TechnicalDetailsWidget state={about} />

        <Widget
          id="settings-apidocs-heading"
          className="settings-explorer"
          span="full"
          title={COPY.explorerTitle}
          icon={<LayoutList size={18} strokeWidth={2} />}
          sub={COPY.explorerSub}
        >
          {state.status === 'loading' && <LoadingPanel label="Loading the API contract…" />}
          {state.status === 'error' && <BackendDown error={state.error} onRetry={state.reload} />}
          {state.status === 'data' && <ApiExplorerPanel schema={state.data} />}
        </Widget>
      </div>
    </>
  );
}

/**
 * The raw values — the FULL commit SHA, the response field names, the source
 * endpoints, the repository documentation paths — moved here from About's
 * Technical Details, because a raw value is a developer's (`DEC-56`). The full
 * SHA is still rendered in exactly one place on the page, and it is this one.
 */
function TechnicalDetailsWidget({ state }: { state: AboutState }) {
  return (
    <Widget
      id="settings-technical-heading"
      title={COPY.technicalTitle}
      icon={<CircleHelp size={18} strokeWidth={2} />}
      sub={COPY.technicalSub}
      details={{
        summary: COPY.technicalShow,
        content: (
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
        ),
      }}
    />
  );
}
