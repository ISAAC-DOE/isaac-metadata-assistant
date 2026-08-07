import '../screens.css';
import './statistics.css';
import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { AppShell } from '../../components/AppShell';
import { TopBar } from '../../components/TopBar';
import { LeftNav } from '../../components/LeftNav';
import { BackendDown, LoadingPanel } from '../../components/FetchStates';
import { StatusChip } from '../../components/StatusChip';
import {
  BarChart3,
  CircleDashed,
  CircleHelp,
  FileJson,
  LayoutList,
  Network,
  Settings,
  Shield,
  ShieldCheck,
  Table2,
} from '../../components/icons';
import { api } from '../../lib/api';
import { useFetch, type FetchState } from '../../lib/useFetch';
import { useWorkspaceScope } from '../../lib/workspaceScope';
import { subscribeWorkspaceRebuilt } from '../../lib/workspaceInvalidation';
import type { RuntimeRecord } from '../../lib/crossRecordTriage';
import type {
  ApiAboutResponse,
  ApiGraphStatus,
  ApiOpenApiResponse,
  ApiSchemaResponse,
} from '../../lib/types';
import {
  PORTAL_METRICS_UNAVAILABLE_COPY,
  PORTAL_METRICS_UNAVAILABLE_TITLE,
  PORTAL_METRIC_VIEWS,
  type PortalMetricsSource,
  unconfiguredPortalMetricsSource,
} from '../../lib/portalMetricsContract';
import {
  ROUTES,
  STATISTICS_TAB_PARAM,
  isStatisticsTab,
  type StatisticsTabId,
} from '../../lib/routes';
import { EVIDENCE_CLASS_CHIP } from '../../lib/status';
import {
  EVIDENCE_CLASSES,
  deriveApiSurface,
  deriveEvidenceTotals,
  deriveExportGate,
  deriveMemoryFacts,
  deriveOpenQuestions,
  deriveSchemaFacts,
  deriveWorkflowStages,
  deriveWorkspaceTotals,
} from '../../lib/statisticsModel';
import { RovingTabs } from '../settings/apiShared';
import {
  ChartEmpty,
  ChartError,
  ChartLoading,
  ChartSourceUnavailable,
  StatsBarChart,
  StatsColumnChart,
  StatsComparisonRows,
  StatsStackedBar,
  TechnicalDetails,
} from './StatsCharts';
import {
  FigureList,
  MiniBreakdown,
  StatCard,
  StatsSection,
  UnavailableNote,
} from './StatsPrimitives';
import { MyStats } from './MyStats';

/**
 * Statistics — the read-only insights surface, in two tabs.
 *
 * COMPOSITION ONLY. Every number on the General ISAAC tab is produced by
 * `lib/statisticsModel.ts` from one of five read-only GETs
 * (`/api/runtime/records`, `/api/graph/status`, `/api/about`, `/api/openapi`,
 * `/api/schema`); this file fetches them, formats the strings the primitives
 * display, and owns the states. It computes no figure of its own. The My Stats
 * tab reads NOTHING — see `MyStats.tsx`.
 *
 * The five fetches are deliberately INDEPENDENT — that independence is the
 * partial-failure design. One dead endpoint degrades the sections that read it
 * and nothing else; the page never blanks and never substitutes a plausible
 * value for one it did not receive. When (and only when) all five have failed,
 * one page-level failure state replaces the body rather than five identical
 * stacked copies of the same message.
 *
 * ONE SECTION READS NO ENDPOINT AT ALL. `Platform Metrics` renders the state of
 * an adapter boundary that is not connected in this build — see
 * `lib/portalMetricsContract.ts`. It issues no request, so it neither joins a
 * round nor can fail one, and it is present so a reader who wonders why there is
 * no platform-wide figure is told rather than left to infer.
 *
 * Nothing on this surface is telemetry: there is no request, visit, user, IP,
 * latency, uptime or database figure, because no such signal exists in this app
 * to read. Nothing here mutates, validates, exports, or gates anything —
 * `Refresh` issues exactly the same five GETs and nothing else.
 *
 * The "last read" timestamp is captured HERE, on the settle of each read,
 * because the derivations are pure and hold no clock. It is labelled as when
 * this page last read the API, which is the only thing a client-side clock can
 * honestly claim — it is not a server "data last changed" time.
 *
 * TWO clocks, deliberately. `lastSuccess` advances only when a read is
 * FULFILLED; `lastAttempt` advances on every settle, rejection included. The
 * displayed "Last Read From the API" time is `lastSuccess` and nothing else.
 * That separation is load-bearing rather than pedantic, because `Refresh` uses
 * `reloadSilent()`, which on rejection deliberately KEEPS the previous data and
 * stays in the `data` state so the page does not blank: if a rejected read
 * advanced the read clock, an unreachable backend would leave every figure on
 * screen at its old value while the meta row stamped it with the current time —
 * a reading that never happened. When any read in the latest round failed, the
 * page states that, names how many, and leaves the figures' timestamp at the
 * last read that actually returned a body.
 *
 * ── THE TWO TABS, and what belongs in each ─────────────────────────────────
 *
 * `general` holds material that is genuinely workspace- or build-derived:
 * Workspace at a Glance, Workflow Distribution, Evidence and Validation, and the
 * no-analytics disclosure. `mine` holds personal statistics, which this build
 * cannot produce — the honest gate lives in `MyStats.tsx` and is the whole of
 * that tab.
 *
 * BUILD INTERNALS MOVED INTO ONE COLLAPSED REGION. Project Memory's snapshot
 * counts and provenance commits, the API surface breakdown, and the two runtime
 * facts `/api/about` reports (runtime mode and persistence) are properties of the
 * DEPLOYMENT rather than answers to "how is this workspace doing", and they used
 * to sit in the main flow with equal weight to the record figures. They are now
 * inside `Technical Details`, collapsed by default. Nothing was deleted, nothing
 * became unreachable, and no figure changed its label or its scope on the way.
 *
 * The no-analytics section stays in the MAIN flow, uncollapsed. It is a
 * governance claim about what this application does and does not measure, not
 * clutter, and hiding a privacy statement behind a disclosure would weaken it.
 */

/** The one literal used wherever a figure genuinely was not returned. */
const UNAVAILABLE = 'Not Available';

/** Display formatting for a count. The model already guarantees finiteness. */
function count(value: number): string {
  return String(value);
}

/** A count, or the unavailable literal — never `0` standing in for absence. */
function countOrUnavailable(value: number | null): string {
  return value === null ? UNAVAILABLE : String(value);
}

function stringOrUnavailable(value: string | null): string {
  return value === null ? UNAVAILABLE : value;
}

/** A schema version as `v<n>`, or the unavailable literal. Matches how Project
 *  Memory renders the same field, so one number reads one way on both screens. */
function versionOrUnavailable(value: number | null): string {
  return value === null ? UNAVAILABLE : `v${value}`;
}

/**
 * Title Case for an API-reported token, so `synthetic-only` renders as
 * `Synthetic-Only` and `ephemeral` as `Ephemeral`. Only capitalisation changes:
 * the separators, and every character the API sent, are preserved, so this can
 * never turn an unexpected value into a different word.
 *
 * Takes `unknown` and returns `null` for anything that is not a non-empty
 * string. The types say `runtime_mode` and `persistence` are strings; the wire
 * does not. This function used to call `.replace()` on the value directly, and
 * there is NO ErrorBoundary anywhere in this app (`main.tsx` renders `<App/>`
 * bare), so a body carrying `runtime_mode: null` — or a number — threw during
 * render and blanked the WHOLE SPA, not just this card. A malformed field is now
 * an unavailable figure, which is what the rest of this page already does with
 * anything it did not receive; the pre-existing `SettingsPage.tsx` rows degrade
 * the same way by rendering the value verbatim rather than transforming it.
 */
function titleCaseTokenOrNull(value: unknown): string | null {
  if (typeof value !== 'string' || value.length === 0) return null;
  return value.replace(/[A-Za-z0-9]+/g, (word) => word.charAt(0).toUpperCase() + word.slice(1));
}

/** The reader's locale rendering of a captured client-side instant. */
function formatInstant(when: Date): string {
  return when.toLocaleString();
}

/**
 * One round of reads: how many were STARTED while the page was busy, and how
 * many of those rejected. A page-level Refresh is a round of five; a single
 * section's Retry is a round of one — which is why the denominator is counted
 * rather than hard-coded.
 */
interface Round {
  attempted: number;
  failed: number;
}

const IDLE_ROUND: Round = Object.freeze({ attempted: 0, failed: 0 });

/**
 * What the live region says once a Refresh round drains.
 *
 * Every branch describes THIS round. None of them claims a reading at a time
 * when nothing was read: with a failure in the round, the sentence names how
 * many reads failed and dates the figures to `lastSuccess` — the last read that
 * actually returned a body — instead of to the moment the round ended.
 */
function announceRound(round: Round, lastSuccess: Date | null): string {
  if (round.failed === 0) {
    return lastSuccess === null
      ? 'Refresh finished.'
      : `Refresh finished. The page last read the API at ${formatInstant(lastSuccess)}.`;
  }
  const reads = `${round.failed} of ${round.attempted} reads failed`;
  return lastSuccess === null
    ? `Refresh finished, but ${reads} and no read has succeeded yet, so nothing on this page has been read from the API.`
    : `Refresh finished, but ${reads} — the figures shown were last read at ${formatInstant(lastSuccess)}.`;
}

/**
 * The lead sentence, which names WHICH workspace the figures below describe.
 *
 * IT USED TO NAME THE WRONG ONE, unconditionally: "the current example
 * workspace". The five built-in example records are created ONLY inside a
 * worked-example session — `apps/api/isaac_api/workspace.py:22-32` states it as a
 * structural property ("the NORMAL scope … is **never** auto-seeded: on a fresh
 * deployment it is empty and it stays empty until something explicitly creates a
 * record in it", against "a TUTORIAL scope … The five canonical worked-example
 * records live ONLY here") — so on every ordinary screen that sentence named this
 * scope after content this build never puts there. Same defect class, and same
 * correction, as the mode chip: see `components/TopBar.tsx`, "THE SCOPE DECIDES
 * THE LABEL".
 *
 * KEEP THE QUALIFIER THE QUOTE CARRIES. This conclusion used to read "so on every
 * ordinary screen that sentence asserted contents that are not there" — dropping
 * "on a fresh deployment" and turning a statement about what the build DOES into
 * one about what a directory HOLDS. Nothing here measures contents: there is no
 * startup migration, so a workspace that already held the five still lists them.
 *
 * ONE SENTENCE CANNOT BE TRUE OF BOTH SCOPES, which is why this is a branch rather
 * than a rewording. The record read is keyed on the same `scope` value (see D1
 * below), so this page really does describe either workspace: only the session
 * scope holds examples, and only the ordinary scope can be named without them.
 *
 * THE TAB SPLIT DID CHANGE WHAT THIS SENTENCE PROMISES, and the previous version
 * of this comment denied it. It said "the tab split did not change this
 * sentence's subject … everything it lists is on the General ISAAC tab", and then
 * rendered that sentence ABOVE THE TABLIST on both tabs. So at `?tab=mine` the
 * page lead named workflow readiness, evidence, Project Memory and the API
 * surface — four things, none of which is on the panel the reader is looking at —
 * while the comment recorded the choice as deliberate. Both halves were true and
 * their conjunction was the defect: a lead that is correct about the page reads as
 * a promise about the panel, because it sits directly above it.
 *
 * So the lead is now TAB-SCOPED. The reasoning the old comment gave still stands
 * and is preserved: the General lead must not mention personal statistics,
 * because promising personal figures where nothing can qualify them is exactly
 * the claim this build cannot support. What changes is that the My Stats tab gets
 * its own lead instead of inheriting one about a panel it is not showing — and
 * that lead states the tab's condition rather than a figure, in the same terms
 * `MyStats.tsx` and `lib/myStatsContract.ts` use.
 *
 * The WORKSPACE clause stays on the General lead only. On My Stats it would be
 * actively misleading: that tab reads nothing at all, in either scope, so naming
 * a workspace there would imply the gate is a property of which workspace is open.
 *
 * AND IT MUST NOT REPEAT THE PANEL'S OWN SUBTITLE. The first version of the My
 * Stats lead opened with "What this tab will show once records are associated with
 * a signed-in account." — BYTE-IDENTICAL to `MyStats.tsx`'s `stats-mine-gate`
 * section `sub`, which renders a few lines below it in the same viewport. The
 * duplicate is dropped HERE rather than there, because the section subtitle is the
 * component's own self-description and is the only place that sentence appears
 * when `MyStats` is mounted on its own (which two tests do). `the page lead does
 * not repeat a section subtitle` in `my-stats.test.tsx` is the assertion that
 * keeps them distinct.
 *
 * `workspace` is computed AFTER the `mine` branch returns, not before it. It was
 * dead on that path — the My Stats lead names no workspace, by the paragraph above.
 */
function leadSentence(scope: string | null, tab: StatisticsTabId): string {
  if (tab === 'mine') {
    return (
      'This preview cannot tell whose records these are, so this tab states that ' +
      'rather than a figure.'
    );
  }
  const workspace = scope === null ? 'this workspace' : 'the open worked-example workspace';
  /*
   * IT NAMES THE TOPICS THAT STATE FIGURES — NOT EVERY HEADING BELOW IT, and the
   * narrower claim is the true one. Open Questions, Record Schema and Platform
   * Metrics are added by this same change, so the previous four-topic sentence was
   * not stale: it was complete for the page it described, and it is adding a
   * section that makes a lead go wrong. Two headings stay unnamed on purpose — the
   * runtime facts inside Technical Details, and the no-analytics disclosure, which
   * is an absence rather than a topic — so this is not a table of contents.
   *
   * Platform Metrics is named DIFFERENTLY from the rest, in its own clause, because
   * it is the one section that states no figure — listing "platform metrics"
   * alongside the others would promise a platform-wide number this build cannot
   * produce, which is the same defect class as the workspace clause this function
   * already branches on.
   */
  return (
    `A read-only view of ${workspace}, workflow readiness, open questions, ` +
    'evidence, the official record schema, Project Memory, and the API surface — ' +
    'and, for platform-wide figures, why none is stated.'
  );
}

/**
 * A compact, localized failure note. Neutral rather than alarm-coloured, with
 * the recourse (a real button, keyboard reachable) still offered.
 *
 * THE RULE THIS PAGE FOLLOWS IS ONE ALARM PER FAILED SOURCE, NOT ONE PER PAGE.
 * The five reads are independent, so each dead source states itself ONCE, as a
 * full `BackendDown`, at the first section that reads it; every FURTHER section
 * reading that same source gets this compact note instead, because repeating the
 * identical alarm three times would be noise. Three simultaneously dead sources
 * therefore do produce three alarms — and that is the intent: they are three
 * different failures, and collapsing them into one panel would hide which
 * sources are actually down while the degraded banner above says "3 of 5 reads
 * failed". Only the ALL-FIVE-failed case collapses, into the single page-level
 * `BackendDown`, because there is then nothing left to localize.
 *
 * `/api/about` is the ONE deliberate exception, and it is quieter rather than
 * louder: its failure costs two supporting cards in the collapsed Technical
 * Details region, so it states itself with this note at its only reader. An alarm
 * panel there would out-shout the figures beside it that were read successfully.
 *
 * `/api/schema` WAS A SECOND, UNDOCUMENTED EXCEPTION and is no longer one. It has
 * a single reader, so this rule always prescribed a full `BackendDown` for it, and
 * rendering this note instead meant a dead schema announced nothing at all: this
 * component has no `role`, while `BackendDown` is `role="alert"`. It was not
 * recorded as an exception because it was not a decision. `RecordSchemaFacts` now
 * renders `BackendDown` like the other two sections in its region, and
 * `a dead /api/schema alarms ONCE, like its two siblings in this region` pins the
 * alarm count rather than only the message.
 *
 * (The earlier wording of this comment said the alarm is "stated once" full
 * stop, which read as a page-level promise the code never made — the code and
 * the comment are reconciled here in favour of the code, which is right.)
 */
function SectionUnavailable({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <UnavailableNote>
      <p>{message}</p>
      <div className="stats-retry">
        <button type="button" className="btn btn-secondary" onClick={onRetry}>
          Retry
        </button>
      </div>
    </UnavailableNote>
  );
}

/* ---- the two tabs ------------------------------------------------------ */

const STATISTICS_TABS: { id: StatisticsTabId; label: string }[] = [
  { id: 'general', label: 'General ISAAC' },
  { id: 'mine', label: 'My Stats' },
];

const tabId = (id: StatisticsTabId) => `statistics-tab-${id}`;
const panelId = (id: StatisticsTabId) => `statistics-tabpanel-${id}`;

export function StatisticsPage() {
  /*
   * THE ACTIVE TAB IS DERIVED FROM THE URL, not held in `useState`.
   *
   * A tab in component state cannot be linked to, bookmarked, reloaded back into,
   * or reached from another surface — and that is not hypothetical here: the
   * Governance & Safety Validator shipped exactly that way and had to be fixed
   * (`GovernancePage.tsx`, "the Validator was unreachable by link"). This uses the
   * same `?tab=` parameter and the same fallback discipline: anything
   * unrecognised — a typo, an empty value, an absent param — resolves to
   * `general` without throwing.
   */
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get(STATISTICS_TAB_PARAM);
  const activeTab: StatisticsTabId = isStatisticsTab(requestedTab) ? requestedTab : 'general';

  function selectTab(tab: StatisticsTabId) {
    const next = new URLSearchParams(searchParams);
    next.set(STATISTICS_TAB_PARAM, tab);
    /* `replace` for a within-page tab click, matching Governance: switching tabs
       is not a destination, and pushing each one would bury the screen the reader
       arrived from behind a stack of Back presses. Copying the existing params
       (rather than building a fresh URL from `ROUTES.statisticsTab`) is what keeps
       any other query parameter on the URL alive. */
    setSearchParams(next, { replace: true });
  }

  /*
   * Round tracking. `useFetch` exposes no completion callback, so the five
   * fetchers are wrapped here: `track` is what `useFetch` actually calls, on the
   * initial load, on `reload()` and on `reloadSilent()` alike, which makes every
   * request's start and settle — and crucially whether it was FULFILLED or
   * REJECTED — observable without issuing a second request. This is the only
   * reason the page holds state at all.
   */
  const [pending, setPending] = useState(0);
  /** When a read last actually RETURNED A BODY. A rejection never advances it. */
  const [lastSuccess, setLastSuccess] = useState<Date | null>(null);
  /** When a read last settled, fulfilled or rejected. */
  const [lastAttempt, setLastAttempt] = useState<Date | null>(null);
  /** How the latest round went: reads started, and how many did not answer. */
  const [round, setRound] = useState<Round>(IDLE_ROUND);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState('');

  /*
   * The arithmetic lives in refs; the state only MIRRORS them for rendering. Two
   * of the five reads can settle in the same tick, so a functional
   * `setState(n => n + 1)` chain would be correct while anything that had to
   * READ the resulting value in that same tick (which of the round's reads have
   * failed so far) would not.
   */
  const pendingRef = useRef(0);
  const roundRef = useRef<Round>(IDLE_ROUND);

  function settle(fulfilled: boolean): void {
    pendingRef.current -= 1;
    if (!fulfilled) {
      roundRef.current = { ...roundRef.current, failed: roundRef.current.failed + 1 };
    }
    const now = new Date();
    setPending(pendingRef.current);
    setRound(roundRef.current);
    setLastAttempt(now);
    /* ONLY a fulfilled read advances the read clock. A rejection is an attempt,
       and an attempt is not a reading: advancing it here is precisely what let a
       failed Refresh stamp the current time onto figures nobody had just read. */
    if (fulfilled) setLastSuccess(now);
  }

  function track<T>(request: Promise<T>): Promise<T> {
    /* A read that joins an IDLE page opens a new round, so the previous round's
       tally — which described reads this one supersedes — is cleared. */
    if (pendingRef.current === 0) roundRef.current = IDLE_ROUND;
    pendingRef.current += 1;
    roundRef.current = { ...roundRef.current, attempted: roundRef.current.attempted + 1 };
    setPending(pendingRef.current);
    setRound(roundRef.current);
    return request.then(
      (value) => {
        settle(true);
        return value;
      },
      (error: unknown) => {
        settle(false);
        // Rethrown: this wrapper OBSERVES a read, it never swallows one, so
        // `useFetch` still renders its own error state for a hard reload and
        // still keeps the previous data for a silent one.
        throw error;
      },
    );
  }

  /*
   * D1 — the RECORD read is keyed on the workspace scope, the other three are not.
   *
   * `GET /api/runtime/records` is scope-sensitive exactly as the experiment list
   * is: nothing in the ordinary workspace, the five built-in examples inside a
   * worked-example session. With an empty dependency list this page read once, so
   * opening or leaving a session left every record-derived figure on it describing
   * a workspace that was no longer being addressed. This is a LIST-shaped surface,
   * so the right answer is to re-read (unlike the record surfaces, which leave —
   * see `lib/workspaceScope.ts`).
   *
   * The graph status, the About payload, the OpenAPI document and the official
   * record schema are properties of the build rather than of a workspace, so
   * they are deliberately left unkeyed.
   *
   * THE READS ARE NOT KEYED ON THE TAB, and that is deliberate rather than an
   * oversight: they are issued on mount regardless of which tab is showing, so
   * switching tabs never costs a round trip and never resets the read clock. The
   * My Stats tab adds no read of its own — it has nothing to read.
   */
  const scope = useWorkspaceScope();
  const records = useFetch(() => track(api.getRuntimeRecords()), [scope]);
  const graph = useFetch(() => track(api.getGraphStatus()), []);
  const about = useFetch(() => track(api.getAbout()), []);
  const openapi = useFetch(() => track(api.getOpenApi()), []);
  const schema = useFetch(() => track(api.getSchema()), []);

  /*
   * ...AND the record read also listens for a workspace REBUILD, which the scope
   * key cannot cover.
   *
   * The guarded reset (`components/ResetDemoDialog.tsx`, in the worked-example bar
   * that `AppShell` mounts on EVERY surface including this one) rewrites the record
   * set without changing the scope — same session, different records. So `[scope]`
   * is unchanged by it and every record-derived figure on this page — the four
   * record cards, the workflow spine, the evidence totals, the export gate — went
   * on describing the records the reset had just discarded. My Experiments already
   * subscribed; this page renders the same workspace-derived data one click away
   * from the control and did not.
   *
   * SILENT on purpose, exactly as the queue's is: the figures stay on screen while
   * the fresh ones arrive, so the page does not blank and the reader does not lose
   * their scroll position. Only the RECORD read is re-issued — the graph status, the
   * About payload, the OpenAPI document and the official record schema are
   * properties of the build and a reset cannot change them.
   */
  const { reloadSilent: reloadRecordsSilent } = records;
  useEffect(() => subscribeWorkspaceRebuilt(reloadRecordsSilent), [reloadRecordsSilent]);

  /*
   * Did the latest round come back complete? This reads the round's own TALLY,
   * not a comparison of the two clocks: a round whose failing read settles
   * BEFORE its succeeding ones leaves `lastAttempt` equal to `lastSuccess`, so a
   * clock comparison would silently under-report a partial failure.
   */
  const degraded = round.failed > 0;

  // Refresh completes when the round drains. No polling anywhere on this page.
  useEffect(() => {
    if (!refreshing || pending !== 0) return;
    setRefreshing(false);
    setRefreshMessage(announceRound(round, lastSuccess));
  }, [refreshing, pending, round, lastSuccess]);

  function refreshAll() {
    if (refreshing) return;
    // Silent reloads: current data stays on screen, so the page does not blank
    // and scroll position is kept. Five GETs, no write, nothing else.
    records.reloadSilent();
    graph.reloadSilent();
    about.reloadSilent();
    openapi.reloadSilent();
    schema.reloadSilent();
    setRefreshing(true);
    setRefreshMessage('Refreshing — re-reading the API.');
  }

  const allFailed =
    records.status === 'error' &&
    graph.status === 'error' &&
    about.status === 'error' &&
    openapi.status === 'error' &&
    schema.status === 'error';

  function retryAll() {
    records.reload();
    graph.reload();
    about.reload();
    openapi.reload();
    schema.reload();
  }

  return (
    <AppShell
      variant="full"
      topBar={<TopBar variant="home" />}
      sidebar={<LeftNav active="statistics" />}
      mainPad="pad"
      width="wide"
    >
      <div className="placeholder">
        <span className="eyebrow">Workspace Insights</span>
        <h1>Statistics</h1>
        <p>{leadSentence(scope, activeTab)}</p>

        {/* The app's shared page-tab pattern, reused rather than reimplemented:
            `RovingTabs` is the same component the Settings code-sample tabs use
            and the same contract Project Memory's and Governance's local tablists
            implement (automatic activation, Arrow/Home/End, exactly one tab in the
            tab order, `aria-controls` on the selected tab only) — and it wears the
            same `.section-tabs` / `.section-tab` styling those three pages do.
            NOT a fourth paradigm. */}
        <RovingTabs
          className="section-tabs"
          tabClassName="section-tab"
          label="Statistics sections"
          tabs={STATISTICS_TABS}
          active={activeTab}
          onSelect={selectTab}
          tabId={tabId}
          panelId={panelId}
        />
      </div>

      {activeTab === 'general' && (
        <div
          className="statistics"
          id={panelId('general')}
          role="tabpanel"
          aria-labelledby={tabId('general')}
          tabIndex={0}
        >
          <div className="stats-meta">
            {/* Three mutually exclusive states, and the labels are not
                interchangeable. `Last Read From the API` is rendered from
                `lastSuccess` ONLY, so it can never date the figures to an attempt
                that returned nothing. With no successful read at all there is a
                time but no reading, so the row says `Last Read Attempt`; before
                the first settle there is neither, and a placeholder there would be
                a fabricated reading time. */}
            {lastSuccess !== null ? (
              <p className="stats-meta-read">
                <span className="stats-meta-label">Last Read From the API</span>
                <time className="mono" dateTime={lastSuccess.toISOString()}>
                  {formatInstant(lastSuccess)}
                </time>
              </p>
            ) : lastAttempt !== null ? (
              <p className="stats-meta-read">
                <span className="stats-meta-label">Last Read Attempt</span>
                <time className="mono" dateTime={lastAttempt.toISOString()}>
                  {formatInstant(lastAttempt)}
                </time>
              </p>
            ) : (
              <p className="stats-meta-read">
                <span className="stats-meta-label">Reading From the API</span>
              </p>
            )}
            <button
              type="button"
              className="btn btn-secondary"
              onClick={refreshAll}
              aria-busy={refreshing}
            >
              {refreshing ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>
          {/* The failure of a round is stated in the page's own words, next to the
              timestamp it qualifies. Suppressed when EVERY read failed, because
              the page-level `BackendDown` below already says so and there are then
              no figures left to caveat. Neutral (`UnavailableNote`), not an alert:
              each affected section carries its own alert and its own Retry. */}
          {degraded && !allFailed && lastAttempt !== null && (
            <div className="stats-block">
              <UnavailableNote>
                <p>
                  {round.failed} of {round.attempted} reads failed on the most recent attempt, at{' '}
                  {formatInstant(lastAttempt)}.{' '}
                  {lastSuccess !== null
                    ? 'Nothing was substituted for what did not arrive, so any figure a failed read feeds is either absent or older than the last-read time above.'
                    : 'No read has succeeded yet, so nothing on this page has been read from the API.'}
                </p>
              </UnavailableNote>
            </div>
          )}
          {/* Present from FIRST render so a change to its text is what gets
              announced — a live region that appears with its message is
              unreliable. This page never auto-polls, so it only ever speaks in
              response to the reader pressing Refresh. */}
          <p className="sr-only" role="status">
            {refreshMessage}
          </p>

          {allFailed ? (
            <BackendDown
              error={records.status === 'error' ? records.error : undefined}
              onRetry={retryAll}
            />
          ) : (
            <>
              <WorkspaceGlance records={records} />
              <WorkflowDistribution records={records} />
              <OpenQuestions records={records} />
              <EvidenceAndValidation records={records} />
              <PlatformMetrics />
              <NoAnalytics />
              <TechnicalDetails
                id="stats-technical"
                title="Technical Details"
                sub="What this build reports about itself: the runtime mode, the served memory snapshot, the official record schema, and the shape of the API. Properties of the deployment, not of your records."
              >
                <RuntimeFacts about={about} />
                <RecordSchemaFacts schema={schema} />
                <ProjectMemoryFacts graph={graph} />
                <ApiSurface openapi={openapi} />
              </TechnicalDetails>
            </>
          )}
        </div>
      )}

      {activeTab === 'mine' && (
        <div
          className="statistics"
          id={panelId('mine')}
          role="tabpanel"
          aria-labelledby={tabId('mine')}
          tabIndex={0}
        >
          <MyStats />
        </div>
      )}
    </AppShell>
  );
}

/* ---- 1 · Workspace at a Glance ---------------------------------------- */

/** What `useFetch` hands back: the 3-state union plus its two reload controls. */
type Fetched<T> = FetchState<T> & { reload: () => void; reloadSilent: () => void };

type RecordsBody = { records: RuntimeRecord[]; total: number };
type RecordsFetch = Fetched<RecordsBody>;
type AboutFetch = Fetched<ApiAboutResponse>;
type GraphFetch = Fetched<ApiGraphStatus>;
type OpenApiFetch = Fetched<ApiOpenApiResponse>;
type SchemaFetch = Fetched<ApiSchemaResponse>;

/**
 * The at-a-glance row — the KPI form, deliberately not a chart.
 *
 * Four headline numbers with no shared scale and no ordering between them are a
 * row of stat tiles; a four-bar chart of "Total / Need Attention / Ready /
 * Exported" would put a total and its own subsets on one axis, which invites
 * reading the parts as a partition of the whole when `Total Records` is the API's
 * workspace denominator and the other three describe only the records received.
 *
 * The two runtime cards this section used to carry (`Runtime Mode`,
 * `Persistence`) moved into `Technical Details`: they are facts about the build,
 * not about the workspace, and they sat here only because they arrived in the
 * same round of reads. This section therefore reads exactly one endpoint now, so
 * its sub-line no longer promises anything about the build.
 */
function WorkspaceGlance({ records }: { records: RecordsFetch }) {
  return (
    <StatsSection
      id="stats-glance"
      title="Workspace at a Glance"
      sub="Counts for the records this workspace holds right now."
      icon={<LayoutList size={18} strokeWidth={2} aria-hidden="true" />}
    >
      {records.status === 'loading' && <LoadingPanel label="Loading the workspace summary…" />}
      {records.status === 'error' && <BackendDown error={records.error} onRetry={records.reload} />}
      {records.status === 'data' && <GlanceRecordCards body={records.data} />}
    </StatsSection>
  );
}

/**
 * The two runtime facts `/api/about` reports about this build, inside Technical
 * Details.
 *
 * Each is stated only if the response actually carried a usable string. A
 * malformed field becomes the same unavailable literal every other absent figure
 * on this page uses, in the neutral `quiet` tone — not an error, and not a
 * guessed default such as "Synthetic-Only", which would be the one substitution
 * this project forbids outright. Rendering never throws on this body.
 */
function RuntimeFacts({ about }: { about: AboutFetch }) {
  return (
    <StatsSection
      id="stats-runtime"
      title="Runtime"
      sub="What this build reports about its own data regime and storage."
      icon={<Settings size={18} strokeWidth={2} aria-hidden="true" />}
      headingLevel={3}
    >
      {about.status === 'loading' && (
        <LoadingPanel label="Loading the runtime mode and persistence…" />
      )}
      {about.status === 'error' && (
        <SectionUnavailable
          message="This build's runtime mode and persistence could not be read from the API, so neither is stated here."
          onRetry={about.reload}
        />
      )}
      {about.status === 'data' && <GlanceRuntimeCards body={about.data} />}
    </StatsSection>
  );
}

function GlanceRuntimeCards({ body }: { body: ApiAboutResponse }) {
  const runtimeMode = titleCaseTokenOrNull(body.runtime_mode);
  const persistence = titleCaseTokenOrNull(body.persistence);
  return (
    <div className="stats-cards stats-cards-pair">
      <StatCard
        label="Runtime Mode"
        value={runtimeMode ?? UNAVAILABLE}
        note={
          runtimeMode === null
            ? 'the API answered without a usable runtime mode, so none is stated.'
            : 'the data regime this build reports.'
        }
        tone={runtimeMode === null ? 'quiet' : 'neutral'}
      />
      <StatCard
        label="Persistence"
        value={persistence ?? UNAVAILABLE}
        note={
          persistence === null
            ? 'the API answered without a usable storage class, so none is stated.'
            : 'the storage class this build reports.'
        }
        tone={persistence === null ? 'quiet' : 'neutral'}
      />
    </div>
  );
}

function GlanceRecordCards({ body }: { body: { records: RuntimeRecord[]; total: number } }) {
  const totals = deriveWorkspaceTotals(body);

  /* NOT defensive any more, and the comment here said it was. It read "the workspace
     always holds its canonical synthetic records ... so this branch is not reachable
     through the shipped product", which stopped being true when the five examples moved
     into a worked-example session: the ORDINARY scope starts with no records, so opening
     Statistics without a walkthrough open reaches this branch as the normal case. The
     rendered sentence is measured (`totals.total === 0`, derived from the same body the
     cards are built from), so it stays as it is — only the claim about reachability was
     wrong. */
  if (totals.total === 0) {
    return (
      <div className="stats-empty">
        <p className="stats-empty-title">No Records Yet</p>
        <p className="stats-note">
          The workspace holds no records, so there is nothing to summarise here.
        </p>
        <p className="stats-actions">
          <Link to={ROUTES.experiments}>Go to My Experiments</Link>
        </p>
      </div>
    );
  }

  return (
    <>
      {/* ABOVE the grid, and it names the exception explicitly.
          Two things were wrong with this note when it sat BELOW the cards and
          said "every breakdown below describes only the records received":
          `Need Attention`, `Ready to Export` and `Exported` are in the grid the
          note followed, so the very counts most at risk of being read as
          workspace-wide were the ones its own wording excluded — while sitting
          beside a `Total Records` that IS workspace-wide. It now precedes what it
          qualifies and states the one figure it does not apply to. */}
      {body.records.length !== totals.total && (
        <div className="stats-block stats-block-lead">
          <UnavailableNote>
            This page received {count(body.records.length)} of the {count(totals.total)} records the
            API reports. Total Records below is the API&rsquo;s own workspace total; every other
            count on this page — the cards beside it and every breakdown further down — describes
            only the {count(body.records.length)} records received.
          </UnavailableNote>
        </div>
      )}
      <div className="stats-cards">
        <StatCard
          label="Total Records"
          value={count(totals.total)}
          note="the workspace total the API reports."
        />
        <StatCard
          label="Need Attention"
          value={count(totals.needsAttention)}
          note="open questions remain."
          tone={totals.needsAttention > 0 ? 'attention' : 'neutral'}
        />
        <StatCard
          label="Ready to Export"
          value={count(totals.readyToExport)}
          note="no open questions and the export dry-run passes."
          tone={totals.readyToExport > 0 ? 'good' : 'neutral'}
        />
        <StatCard
          label="Exported"
          value={count(totals.exported)}
          note="an official record has been written."
        />
        {totals.unknownStatus > 0 && (
          <StatCard
            label="Unrecognized Status"
            value={count(totals.unknownStatus)}
            note="a status this page cannot place; counted, not folded into a known bucket."
            tone="attention"
          />
        )}
      </div>
    </>
  );
}

/* ---- 2 · Workflow Distribution ---------------------------------------- */

function WorkflowDistribution({ records }: { records: RecordsFetch }) {
  return (
    <StatsSection
      id="stats-workflow"
      title="Workflow Distribution"
      sub="Where the records stand in the five-step workflow. Each record is counted once, at its first unsatisfied step."
      icon={<BarChart3 size={18} strokeWidth={2} aria-hidden="true" />}
    >
      {records.status === 'loading' && (
        <ChartLoading label="Loading the workflow distribution…" />
      )}
      {records.status === 'error' && (
        <ChartError
          message="The workspace records could not be read, so there is no workflow distribution to show."
          onRetry={records.reload}
        />
      )}
      {records.status === 'data' && <WorkflowBars records={records.data.records} />}
    </StatsSection>
  );
}

/**
 * FORM CHOICE — a horizontal bar chart over a shared value axis.
 *
 * The job is comparing counts across up to seven named buckets whose labels are
 * long ("Review Export Readiness"), which is the horizontal bar's exact case: the
 * label gets a line of real text that wraps, and one axis lets the eye compare
 * lengths. A column chart would clip or rotate those names; a single stacked bar
 * would turn five records into five indistinguishable 20% slices and hide the
 * zeros the canonical axis is deliberately keeping.
 *
 * AND IT IS NOT THE ROW OF PROGRESS BARS THIS SECTION USED TO DRAW. The old
 * `StageBars` scaled every bar against the TOTAL, drew no axis and offered no
 * table, so six buckets over five records were six near-empty tracks that could
 * not be read as numbers. The scale is now a nice maximum over the LARGEST
 * bucket, gridlines and tick labels are shared across the rows, and the figure
 * carries both a summary sentence and a data table.
 */
function WorkflowBars({ records }: { records: RuntimeRecord[] }) {
  if (records.length === 0) {
    return (
      <ChartEmpty title="No Records to Distribute">
        No records were returned, so there is no distribution to show. No bar is drawn rather than a
        row of zeros.
      </ChartEmpty>
    );
  }
  const stages = deriveWorkflowStages(records);
  return (
    <StatsBarChart
      caption={`Records by current workflow step, out of ${count(records.length)} counted`}
      rows={stages.map((stage) => ({ key: stage.id, label: stage.label, value: stage.count }))}
      unit="records"
      total={records.length}
      categoryHeader="Workflow Step"
      note="Bars share one scale, marked beneath them. The scale runs to the largest bucket, not to the total, so small differences stay visible."
    />
  );
}

/* ---- 3 · Open Questions ------------------------------------------------ */

/**
 * The one figure the safe record projection carries that this page used to
 * discard: `pending_count`.
 *
 * It is the quantity that DRIVES the status distribution above — `needs_attention`
 * is exactly "open questions remain" — so the page stated the consequence four
 * times and never the cause. Nothing new is fetched for it.
 */
function OpenQuestions({ records }: { records: RecordsFetch }) {
  return (
    <StatsSection
      id="stats-questions"
      title="Open Questions"
      sub="How many answers the records are still waiting for, counted in questions rather than in records."
      icon={<CircleHelp size={18} strokeWidth={2} aria-hidden="true" />}
    >
      {records.status === 'loading' && <LoadingPanel label="Loading the open-question counts…" />}
      {records.status === 'error' && (
        <SectionUnavailable
          message="The workspace records could not be read, so no open-question count is stated."
          onRetry={records.reload}
        />
      )}
      {records.status === 'data' && <OpenQuestionFigures records={records.data.records} />}
    </StatsSection>
  );
}

/**
 * FORM CHOICE — a figure list, for the same reason the export gate is one.
 *
 * These five numbers sit on THREE different axes. `Total Open Questions` counts
 * questions; the next three count records; `Most on One Record` is a maximum,
 * not a tally of anything. Putting them on one shared scale would invite adding
 * a question total to a record count, and a stacked bar would assert a
 * partition that does not exist — a record with a blocked step may also have
 * open questions, and usually does.
 */
function OpenQuestionFigures({ records }: { records: RuntimeRecord[] }) {
  const questions = deriveOpenQuestions(records);

  if (questions.recordsCounted === 0) {
    return (
      <p className="stats-note">
        No records were returned, so there is no open-question count to state.
      </p>
    );
  }

  return (
    <>
      <FigureList
        rows={[
          {
            label: 'Total Open Questions',
            value: count(questions.totalOpenQuestions),
            mono: true,
          },
          {
            label: 'Records With Open Questions',
            value: count(questions.recordsWithOpenQuestions),
            mono: true,
          },
          { label: 'Most on One Record', value: count(questions.mostOnOneRecord), mono: true },
          {
            label: 'Records With a Blocked Step',
            value: count(questions.recordsWithBlockedStep),
            mono: true,
          },
          {
            label: 'Records With a Reopened Step',
            value: count(questions.recordsWithReopenedStep),
            mono: true,
          },
        ]}
      />
      {questions.recordsWithUnreadableCount > 0 && (
        <div className="stats-block">
          <UnavailableNote>
            <p>
              {count(questions.recordsWithUnreadableCount)} of the{' '}
              {count(questions.recordsCounted)} records received carried no usable question count,
              so they contribute nothing to the total above. Nothing was assumed for them, and they
              were not counted as zero.
            </p>
          </UnavailableNote>
        </div>
      )}
      <p className="stats-note">
        Total Open Questions counts QUESTIONS across the {count(questions.recordsCounted)} records
        received. Records With Open Questions, Records With a Blocked Step and Records With a
        Reopened Step count RECORDS. Most on One Record is the largest single record&rsquo;s
        question count, and is neither a total nor a share of one.
      </p>
      <p className="stats-note">
        A blocked step and a reopened step are separate axes and overlap each other and the question
        counts, so none of these five may be added together. Each reports only whether a record has
        at least one such step — the workspace projection reduces all five steps to one flag apiece,
        so it does not name the step. No question text, field name or answer is read here.
      </p>
    </>
  );
}

/* ---- 4 · Evidence and Validation -------------------------------------- */

function EvidenceAndValidation({ records }: { records: RecordsFetch }) {
  return (
    <StatsSection
      id="stats-evidence"
      title="Evidence and Validation"
      sub="Two separate readings of the same records: how well their fields are supported by evidence, and where each record stands against the export gate."
      icon={<ShieldCheck size={18} strokeWidth={2} aria-hidden="true" />}
    >
      {records.status === 'loading' && (
        <ChartLoading label="Loading evidence and export-gate counts…" />
      )}
      {records.status === 'error' && (
        <ChartError
          message="The workspace records could not be read, so neither the evidence counts nor the export-gate counts can be stated."
          onRetry={records.reload}
        />
      )}
      {records.status === 'data' && (
        <div className="stats-columns">
          <EvidenceGroup records={records.data.records} />
          <ExportGateGroup records={records.data.records} />
        </div>
      )}
    </StatsSection>
  );
}

/**
 * FORM CHOICE — chips for the counts, and ONE stacked bar for the composition.
 *
 * These are two different questions and they are answered separately rather than
 * twice. The chip row states each class's COUNT with the app's own status glyph
 * and colour, which is where those hues belong (a `StatusChip` carries an icon
 * and a label, so colour is never alone). The stacked bar states each class's
 * SHARE of one whole, which is the part-to-whole job and the one thing a row of
 * counts cannot show at a glance: the five classes are mutually exclusive and
 * exhaustive over classified fields, so they genuinely sum to the total.
 */
function EvidenceGroup({ records }: { records: RuntimeRecord[] }) {
  const evidence = deriveEvidenceTotals(records);
  return (
    <div className="stats-group">
      <h3>Evidence Support</h3>
      {evidence.recordsCounted === 0 ? (
        <p className="stats-note">
          No records were returned, so no fields were classified and no count is stated.
        </p>
      ) : (
        <>
          {/* EVIDENCE_CLASSES order is severity precedence, not count order —
              iterated as given, never re-sorted. */}
          <MiniBreakdown
            label="Fields by Evidence-Support Class"
            items={EVIDENCE_CLASSES.map((cls) => {
              const n = evidence[cls.field];
              return {
                key: cls.key,
                chip: <StatusChip kind={EVIDENCE_CLASS_CHIP[cls.key]} />,
                count: n,
                noun: n === 1 ? 'field' : 'fields',
              };
            })}
          />
          {/* A composition needs a whole. With no classified field there is no
              denominator, so the stack is omitted rather than drawn empty — the
              chip row above still states the five zeros as measurements. */}
          {evidence.totalFields > 0 && (
            <div className="stats-block">
              <StatsStackedBar
                caption="Share of classified fields by evidence-support class"
                rows={EVIDENCE_CLASSES.map((cls) => ({
                  key: cls.key,
                  label: evidenceClassLabel(cls.key),
                  value: evidence[cls.field],
                }))}
                total={evidence.totalFields}
                unit="fields"
                categoryHeader="Evidence-Support Class"
                note="Segment shade marks position in the order above — it is not a magnitude and it does not rank severity. The class name carries the meaning."
              />
            </div>
          )}
          <FigureList
            rows={[
              { label: 'Total Fields Counted', value: count(evidence.totalFields), mono: true },
              { label: 'Records Counted', value: count(evidence.recordsCounted), mono: true },
            ]}
          />
          <p className="stats-note">
            Every number in this group counts FIELDS across the records counted, not records. One
            record contributes many fields.
          </p>
        </>
      )}
    </div>
  );
}

/**
 * The evidence-class name as words, for the legend and the data table.
 *
 * The chip row above renders `StatusChip`, which supplies its own label from
 * `LABELS`; a chart legend cannot embed a chip (a swatch keys the ramp step), so
 * it needs the class name as a plain string. Derived from the backend's own
 * histogram key rather than authored per class, so a class added to
 * `EVIDENCE_CLASSES` cannot arrive here with no name at all.
 */
function evidenceClassLabel(key: string): string {
  return key
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

/**
 * FORM CHOICE — a figure list, and DELIBERATELY NOT A CHART.
 *
 * Every chart form for these five numbers would state something false.
 * `Stale Artifacts` is a SUBSET OF `Exported`, not a fifth bucket, so a stacked
 * bar would imply a partition that does not exist and a bar chart on one shared
 * axis would invite adding the rows up. The four status counts alone would chart
 * honestly, but splitting the five across a chart and a list would separate the
 * very rows whose relationship the copy below has to explain. So they stay a
 * labelled list with the overlap stated in words.
 *
 * "OVERLAPS the four status rows" is what this used to say, and it is looser than
 * the truth in a way that matters: it implies a record could be stale while
 * sitting in `Ready Now` or one of the two blocked rows, which cannot happen.
 * `artifact_state` returns `none` unless `exp.exported()`
 * (`apps/api/isaac_api/dependencies.py:56-57`), and `status()` returns `DONE` if
 * and only if `exported()` is true (`workspace.py:549-566`, checked) — which is
 * also the field `deriveExportGate` buckets on. So stale ⊆ Exported, and the
 * overlap is with exactly ONE row. The decision not to chart is unchanged; only
 * the reason is stated at its real strength.
 */
function ExportGateGroup({ records }: { records: RuntimeRecord[] }) {
  const gate = deriveExportGate(records);
  return (
    <div className="stats-group">
      <h3>Export Gate</h3>
      {records.length === 0 ? (
        <p className="stats-note">
          No records were returned, so there is no export-gate position to state.
        </p>
      ) : (
        <>
          <FigureList
            rows={[
              { label: 'Exported', value: count(gate.exported), mono: true },
              { label: 'Ready Now', value: count(gate.readyNow), mono: true },
              {
                label: 'Blocked by the Export Gate',
                value: count(gate.blockedByGate),
                mono: true,
              },
              {
                label: 'Blocked by Open Questions',
                value: count(gate.blockedByQuestions),
                mono: true,
              },
              { label: 'Stale Artifacts', value: count(gate.staleArtifacts), mono: true },
            ]}
          />
          <p className="stats-note">
            Ready Now means no open questions remain and the official export dry-run passes. Blocked
            by the Export Gate means no open questions remain but the dry-run does not pass. Blocked
            by Open Questions means the gate has not been reached yet. Stale Artifacts is a subset of
            Exported, not a fifth bucket — a record whose exported file no longer matches its draft
            is counted in both — so it must not be added to the four, and for that reason these five
            are not charted on a shared scale.
          </p>
          <p className="stats-note">
            These positions are recomputed from the current drafts on every read and are never
            stored, so there is no saved verdict and no not-yet-run state to report.
          </p>
          <p className="stats-note">Evidence support and schema validation are separate signals.</p>
        </>
      )}
    </div>
  );
}

/* ---- Technical Details · Record Schema --------------------------------- */

/**
 * The shape of the official ISAAC record schema this build validates against.
 *
 * A BUILD PROPERTY, not a workspace one, which is why it sits inside Technical
 * Details beside the runtime facts and the API surface: the numbers do not
 * change when a record does. Every figure is a count of the schema's own
 * structure — no record is read to produce any of them.
 */
function RecordSchemaFacts({ schema }: { schema: SchemaFetch }) {
  return (
    <StatsSection
      id="stats-schema"
      title="Record Schema"
      sub="The shape of the official record schema this build validates against, and the controlled vocabularies served beside it."
      icon={<Table2 size={18} strokeWidth={2} aria-hidden="true" />}
      headingLevel={3}
    >
      {schema.status === 'loading' && <LoadingPanel label="Loading the official record schema…" />}
      {/*
        `BackendDown`, MATCHING ITS TWO SIBLINGS IN THIS REGION, not the compact
        note it used to render.

        `/api/schema` has exactly ONE reader, so the rule stated on
        `SectionUnavailable` — a full alarm at the first section that reads a dead
        source, the compact note only at FURTHER readers — already prescribed this.
        The compact note here was a violation of that rule rather than an exception
        to it, and it had a consequence beyond tidiness: `SectionUnavailable` renders
        no `role`, so a dead `/api/schema` announced nothing to a screen reader while
        the banner above stated "1 of 5 reads failed". `/api/about`'s exception does
        not transfer — its rationale is that its two cards sit BESIDE record cards
        that were read successfully, whereas a dead schema empties this whole section
        including its chart, exactly as a dead `/api/graph/status` empties Project
        Memory and a dead `/api/openapi` empties API Surface.
      */}
      {schema.status === 'error' && <BackendDown error={schema.error} onRetry={schema.reload} />}
      {schema.status === 'data' && <SchemaBody body={schema.data} />}
    </StatsSection>
  );
}

/**
 * FORM CHOICE — figures for the totals, comparison rows for the sections.
 *
 * The totals sit on different axes (sections, fields, rules, files, terms) and
 * are a labelled list for the same reason the export gate is. The section
 * breakdown IS one whole divided into named parts whose labels come from the
 * document and can be any length, which is the compact comparison row's case —
 * the same form the API surface uses for its groups, and for the same reason.
 */
function SchemaBody({ body }: { body: ApiSchemaResponse }) {
  const facts = deriveSchemaFacts(body);

  if (facts.totalFields === 0) {
    return (
      <>
        <p className="stats-note">
          The schema this build served declares no fields, so there is no breakdown to show.
        </p>
        <p className="stats-actions">
          <Link to={`${ROUTES.governance}?tab=schema`}>Open Schema Reference</Link>
        </p>
      </>
    );
  }

  return (
    <>
      <FigureList
        rows={[
          { label: 'Schema Title', value: stringOrUnavailable(facts.schemaTitle) },
          { label: 'Schema Version', value: stringOrUnavailable(facts.schemaVersion), mono: true },
          /* "FIELDS", NOT "SECTIONS". These two labelled the schema's top-level
             properties as sections, and on the real document 5 of the 6 the root
             requires are scalar strings — `isaac_record_version`, `record_id`,
             `record_type` and so on — which are fields by any reading and are not
             sections of anything. The model's own field names (`topLevelFields`,
             `requiredTopLevelFields`) already said so. The chart below still says
             "section", correctly: it groups each top-level field WITH ITS
             DESCENDANTS, which is what makes a scalar field a one-field group. */
          { label: 'Top-Level Fields', value: count(facts.topLevelFields), mono: true },
          { label: 'Fields at Every Depth', value: count(facts.totalFields), mono: true },
          {
            label: 'Required Top-Level Fields',
            value: count(facts.requiredTopLevelFields),
            mono: true,
          },
          {
            label: 'Fields With Enumerated Values',
            value: count(facts.fieldsWithEnumeratedValues),
            mono: true,
          },
          { label: 'Conditional Rules', value: count(facts.conditionalRules), mono: true },
          { label: 'Vocabulary Files', value: count(facts.vocabularyFiles), mono: true },
          { label: 'Vocabulary Terms', value: count(facts.vocabularyTerms), mono: true },
        ]}
      />
      <div className="stats-block">
        <StatsComparisonRows
          caption="Fields by top-level section, in the schema's own declaration order"
          rows={facts.bySection.map((row) => ({
            key: row.section,
            label: row.section,
            value: row.count,
          }))}
          unit="fields"
          total={facts.totalFields}
          categoryHeader="Section"
        />
      </div>
      <p className="stats-note">
        Required Top-Level Fields counts what the schema&rsquo;s own root requires. Requiredness
        deeper in the document is not added to it: a field marked required inside an optional
        section is required only once that section is present, so a single total across depths would
        state an obligation the schema does not impose. Fields at Every Depth is counted through the
        schema&rsquo;s <span className="mono">properties</span> and array items; fields declared only
        inside a <span className="mono">oneOf</span> alternative are not listed, so this is a count of
        the fields this view can enumerate rather than of every field the document can express. The
        Schema Reference browser walks the document the same way, so the two screens state the same
        number.
      </p>
      <p className="stats-note">
        Vocabulary Terms counts the entries in the vocabulary files this build serves alongside the
        schema. It is a property of those files, not a measurement of any stored data.
      </p>
      <p className="stats-actions">
        <Link to={`${ROUTES.governance}?tab=schema`}>Open Schema Reference</Link>
      </p>
    </>
  );
}

/* ---- Technical Details · Project Memory -------------------------------- */

function ProjectMemoryFacts({ graph }: { graph: GraphFetch }) {
  return (
    <StatsSection
      id="stats-memory"
      title="Project Memory"
      sub="What the served memory snapshot reports about itself. This is the memory and query plane — it is never the authority on record validity."
      icon={<Network size={18} strokeWidth={2} aria-hidden="true" />}
      headingLevel={3}
    >
      {graph.status === 'loading' && <LoadingPanel label="Loading Project Memory provenance…" />}
      {graph.status === 'error' && (
        <BackendDown error={graph.error} onRetry={graph.reload} />
      )}
      {graph.status === 'data' && <MemoryBody graph={graph.data} />}
    </StatsSection>
  );
}

function MemoryBody({ graph }: { graph: Parameters<typeof deriveMemoryFacts>[0] }) {
  const facts = deriveMemoryFacts(graph);
  const noCounts =
    facts.servedFiles === null &&
    facts.concepts === null &&
    facts.communities === null &&
    facts.nodes === null &&
    facts.edges === null;

  return (
    <>
      <FigureList
        rows={[
          {
            // The served PATH SET (`file_count`), NOT the content manifest —
            // the two are different sets and the label must name which one.
            // Project Memory states the SAME field under this SAME label
            // (`ProjectMemory.tsx` `MemoryFigures`); one number, one name.
            label: 'Served Files (Path Set)',
            value: countOrUnavailable(facts.servedFiles),
            mono: true,
          },
          { label: 'Concepts', value: countOrUnavailable(facts.concepts), mono: true },
          { label: 'Communities', value: countOrUnavailable(facts.communities), mono: true },
          { label: 'Nodes', value: countOrUnavailable(facts.nodes), mono: true },
          { label: 'Edges', value: countOrUnavailable(facts.edges), mono: true },
          {
            // Same label AND same rendering as Project Memory's own row for this
            // field (`ProjectMemory.tsx` `MemoryFigures`): a `v` prefix, so a
            // schema version in a column of counts cannot be read as a count.
            label: 'Snapshot Schema Version',
            value: versionOrUnavailable(facts.snapshotSchemaVersion),
            mono: true,
          },
        ]}
      />
      {noCounts && (
        <div className="stats-block">
          <UnavailableNote>
            This build served no snapshot overview, so none of the graph counts above is available.
            No count is inferred and none is shown as zero.
          </UnavailableNote>
        </div>
      )}

      {facts.freshness === 'point_in_time' && (
        <>
          <p className="stats-note">
            <span className="stats-freshness-label">Point-in-Time Snapshot</span> — the snapshot was
            built from a different commit than the one this build reports, so it describes the
            repository at that earlier point and not necessarily the running app.
          </p>
          <FigureList
            rows={[
              {
                label: 'Source Graph Commit',
                value: stringOrUnavailable(facts.sourceGraphCommit),
                mono: true,
              },
              {
                label: 'Deployed App Commit',
                value: stringOrUnavailable(facts.deployedAppCommit),
                mono: true,
              },
            ]}
          />
        </>
      )}
      {facts.freshness === 'current' && (
        <p className="stats-note">
          <span className="stats-freshness-label">Built From This Commit</span> — the snapshot's
          source commit matches the commit this build reports.
        </p>
      )}
      {facts.freshness === 'undetermined' && (
        <div className="stats-block">
          <UnavailableNote>
            Whether this snapshot describes the running build cannot be determined in this
            environment: the two commits needed for the comparison were not both reported. This is
            not a claim that the snapshot is current.
          </UnavailableNote>
        </div>
      )}

      <p className="stats-actions">
        <Link to={ROUTES.memory}>Open Project Memory</Link>
      </p>
    </>
  );
}

/* ---- Technical Details · API Surface ----------------------------------- */

function ApiSurface({ openapi }: { openapi: OpenApiFetch }) {
  return (
    <StatsSection
      id="stats-api"
      title="API Surface"
      sub="The shape of the API this build documents, read from its own generated contract. These are the operations that exist — not traffic, which is not recorded anywhere."
      icon={<FileJson size={18} strokeWidth={2} aria-hidden="true" />}
      headingLevel={3}
    >
      {openapi.status === 'loading' && <LoadingPanel label="Loading the API contract…" />}
      {openapi.status === 'error' && (
        <BackendDown error={openapi.error} onRetry={openapi.reload} />
      )}
      {openapi.status === 'data' && <ApiSurfaceBody doc={openapi.data} />}
    </StatsSection>
  );
}

/**
 * FORM CHOICE — two different forms for two differently-shaped breakdowns of the
 * same contract, because the shape of the LABELS decides the form.
 *
 * By METHOD: at most five categories whose names are three to six characters
 * (`GET`, `DELETE`). Columns are right — the names sit under the marks with no
 * wrapping, rotation or truncation, and heights compare against one baseline.
 * Only the sole maximum is labelled on its cap; the y-axis carries the rest
 * approximately and the table exactly.
 *
 * By GROUP: as many categories as the document has tags, with names that come
 * from the contract itself and can be anything. Compact comparison rows are
 * right — the name gets a wrapping line of real text, and the tracks stay short
 * enough that ten groups still fit without a per-row axis strip.
 */
function ApiSurfaceBody({ doc }: { doc: Parameters<typeof deriveApiSurface>[0] }) {
  const surface = deriveApiSurface(doc);

  if (surface.operationCount === 0) {
    return (
      <>
        <p className="stats-note">
          The contract this build served documents no operations, so there is no breakdown to show.
        </p>
        <p className="stats-actions">
          <Link to={ROUTES.settingsTab('explorer')}>Open Endpoint Explorer</Link>
        </p>
      </>
    );
  }

  return (
    <>
      <FigureList
        rows={[
          {
            label: 'Documented Operations',
            value: count(surface.operationCount),
            mono: true,
          },
          { label: 'Groups', value: count(surface.groupCount), mono: true },
        ]}
      />
      <div className="stats-block">
        <StatsColumnChart
          caption="Documented operations by HTTP method"
          rows={surface.byMethod.map((row) => ({
            key: row.method,
            label: row.method.toUpperCase(),
            value: row.count,
          }))}
          unit="operations"
          total={surface.operationCount}
          categoryHeader="HTTP Method"
        />
      </div>
      <div className="stats-block">
        <StatsComparisonRows
          caption="Documented operations by group, in the contract's own tag order"
          rows={surface.byGroup.map((row) => ({
            key: row.group,
            label: row.group,
            value: row.count,
          }))}
          unit="operations"
          total={surface.operationCount}
          categoryHeader="Group"
        />
      </div>
      <p className="stats-actions">
        <Link to={ROUTES.settingsTab('explorer')}>Open Endpoint Explorer</Link>
      </p>
    </>
  );
}

/* ---- 5 · Platform Metrics (an inactive adapter boundary) --------------- */

/**
 * The wider-platform figures this deployment has no source for.
 *
 * THE SECTION EXISTS BECAUSE THE ABSENCE NEEDS STATING. Every figure above is
 * scoped to this workspace or this build, and a reader who wants to know how
 * ISAAC is doing across the platform would otherwise conclude either that the
 * question is unasked or that the answer is on some other screen. It is neither.
 *
 * NOTHING HERE ISSUES A REQUEST. The state is read from
 * `lib/portalMetricsContract.ts`, whose only implementation holds no URL, no
 * host and no token, and this component does not join the page's fetch rounds —
 * so it can neither slow a Refresh nor be counted among reads that failed.
 *
 * The state is PROBED THROUGH THE REAL BOUNDARY (`platformRecordTotal()`) rather
 * than hard-coded, so wiring a source later changes this section's behaviour
 * instead of requiring it to be rewritten. Only `unavailable` has a rendering:
 * this build's source cannot return `ready` or `loading`, and writing branches
 * for payloads no adapter produces is how a placeholder chart gets shipped.
 */
function PlatformMetrics({
  source = unconfiguredPortalMetricsSource,
}: {
  source?: PortalMetricsSource;
}) {
  const probe = source.platformRecordTotal();

  return (
    <StatsSection
      id="stats-platform"
      title="Platform Metrics"
      sub="Figures about the wider ISAAC platform, as distinct from this workspace and this build."
      icon={<CircleDashed size={18} strokeWidth={2} aria-hidden="true" />}
    >
      <ChartSourceUnavailable title={PORTAL_METRICS_UNAVAILABLE_TITLE}>
        {probe.status === 'unavailable'
          ? PORTAL_METRICS_UNAVAILABLE_COPY[probe.reason]
          : /* Reachable only if a source is wired that this build does not ship.
               It states the state it received and draws nothing, which is the
               only honest thing to do with a payload no view here can read. */
            `The platform metrics source reported "${probe.status}", and this page has no view built for it, so nothing is shown.`}
      </ChartSourceUnavailable>
      <ul className="stats-plan-grid">
        {PORTAL_METRIC_VIEWS.map((view) => (
          <li className="stats-plan-card" key={view.id}>
            <h3 className="stats-plan-title">{view.title}</h3>
            <p className="stats-plan-desc">{view.description}</p>
          </li>
        ))}
      </ul>
      <p className="stats-note">
        Each description names the unit it would count. None of these figures is being withheld from
        you and none of them is zero — this application has no source to read one from, so it states
        that instead of a number.
      </p>
    </StatsSection>
  );
}

/* ---- No analytics ------------------------------------------------------ */

/**
 * Absence of telemetry is a PRIVACY FEATURE, so this section is informational,
 * not a failure: neutral colours, no alert role, no warning glyph, no empty
 * chart, no zero-filled placeholder. The shield is the privacy mark this app
 * already uses, and it is decorative.
 *
 * IT STAYS IN THE MAIN FLOW. Project Memory and the API surface moved into a
 * collapsed Technical Details region; this did not, because it is a claim about
 * what the application measures and stores, and a governance claim behind a
 * disclosure is a weaker claim. It sits directly after the record figures, where
 * a reader wondering why there is no traffic figure will look.
 *
 * SCOPE IS THE WHOLE POINT of the copy below. An earlier version of this section
 * claimed the preview "does not track visits, users, source IPs, request
 * history, or behavioral analytics" — and the last three clauses were not the
 * app's to make. `Dockerfile` starts `uvicorn` with default settings, so the web
 * server writes an access line (client address, method, path, status) for every
 * request; `apps/api/isaac_api/routes.py` writes metadata-only per-operation
 * outcome lines, which is request history by any reasonable reading; and a
 * hosted deployment sits behind an identity gateway whose logs the browser
 * cannot see at all. So every claim here is scoped to THIS APPLICATION — what it
 * ships, measures and stores — and server-side logging is named rather than
 * denied. The narrower privacy wording this app had already vetted lives in
 * `lib/settingsContent.ts` (`no-telemetry`, `no-real-experiment-data`); this
 * section states the same boundary for the page's own subject and links there
 * instead of authoring a third variant.
 */
function NoAnalytics() {
  return (
    <StatsSection
      id="stats-no-analytics"
      title="This Application Collects No Analytics"
      icon={<Shield size={18} strokeWidth={2} aria-hidden="true" />}
    >
      <p className="stats-note">
        This application ships no analytics SDK, no tracking pixel, and makes no third-party
        network request. It measures nothing about how it is used and stores no per-user or
        per-operation metric, which is why this page shows no figure for visits, traffic or request
        volume: no such figure exists in this app to read.
      </p>
      <p className="stats-note">
        Server-side logs are a different matter, and this page does not speak for them. The backend
        writes a metadata-only outcome line per operation, the web server it runs under writes an
        access line per request, and a hosted deployment sits behind an identity gateway that keeps
        records of its own. Those belong to whoever operates the deployment, the browser cannot see
        them, and nothing here is a claim about what they contain or how long they are kept.
      </p>
      <p className="stats-actions">
        <Link to={ROUTES.settingsTab('privacy')}>Open Data &amp; Privacy Settings</Link>
      </p>
    </StatsSection>
  );
}
