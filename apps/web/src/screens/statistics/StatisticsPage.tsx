import '../screens.css';
import './statistics.css';
import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import { AppShell } from '../../components/AppShell';
import { TopBar } from '../../components/TopBar';
import { LeftNav } from '../../components/LeftNav';
import { BackendDown, LoadingPanel } from '../../components/FetchStates';
import { StatusChip } from '../../components/StatusChip';
import {
  BarChart3,
  FileJson,
  LayoutList,
  Network,
  Shield,
  ShieldCheck,
} from '../../components/icons';
import { api } from '../../lib/api';
import { useFetch, type FetchState } from '../../lib/useFetch';
import { useWorkspaceScope } from '../../lib/workspaceScope';
import type { RuntimeRecord } from '../../lib/crossRecordTriage';
import type { ApiAboutResponse, ApiGraphStatus, ApiOpenApiResponse } from '../../lib/types';
import { ROUTES } from '../../lib/routes';
import { EVIDENCE_CLASS_CHIP } from '../../lib/status';
import {
  ALL_COMPLETE_STAGE_ID,
  EVIDENCE_CLASSES,
  deriveApiSurface,
  deriveEvidenceTotals,
  deriveExportGate,
  deriveMemoryFacts,
  deriveWorkflowStages,
  deriveWorkspaceTotals,
} from '../../lib/statisticsModel';
import { CANONICAL_STEPS } from '../../lib/workflowSteps';
import {
  FigureList,
  MiniBreakdown,
  StageBars,
  StatCard,
  StatsSection,
  UnavailableNote,
} from './StatsPrimitives';

/**
 * Statistics — the read-only workspace insights surface.
 *
 * COMPOSITION ONLY. Every number below is produced by `lib/statisticsModel.ts`
 * from one of four read-only GETs (`/api/runtime/records`, `/api/graph/status`,
 * `/api/about`, `/api/openapi`); this file fetches them, formats the strings the
 * primitives display, and owns the states. It computes no figure of its own.
 *
 * The four fetches are deliberately INDEPENDENT — that independence is the
 * partial-failure design. One dead endpoint degrades the sections that read it
 * and nothing else; the page never blanks and never substitutes a plausible
 * value for one it did not receive. When (and only when) all four have failed,
 * one page-level failure state replaces the body rather than four identical
 * stacked copies of the same message.
 *
 * Nothing on this surface is telemetry: there is no request, visit, user, IP,
 * latency, uptime or database figure, because no such signal exists in this app
 * to read. Nothing here mutates, validates, exports, or gates anything —
 * `Refresh` issues exactly the same four GETs and nothing else.
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
 * Stable categorical colour slot per workflow bucket, keyed by CANONICAL
 * POSITION rather than by array index, so a stage keeps its colour even if a
 * seventh (unrecognized) bucket appears. `Unrecognized Step` is deliberately
 * absent from this map: it is not a canonical stage, so it renders on the
 * neutral default instead of borrowing another stage's colour.
 */
const STAGE_TONE: Readonly<Record<string, number>> = Object.freeze(
  Object.fromEntries([
    ...CANONICAL_STEPS.map((step, index) => [step.id, index] as const),
    [ALL_COMPLETE_STAGE_ID, CANONICAL_STEPS.length] as const,
  ]),
);

/**
 * One round of reads: how many were STARTED while the page was busy, and how
 * many of those rejected. A page-level Refresh is a round of four; a single
 * section's Retry is a round of one — which is why the denominator is counted
 * rather than hard-coded to four.
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
 * workspace". The five built-in example records exist ONLY inside a
 * worked-example session — `apps/api/isaac_api/workspace.py:22-32` states it as a
 * structural property ("the NORMAL scope … is **never** auto-seeded: on a fresh
 * deployment it is empty and it stays empty until something explicitly creates a
 * record in it", against "a TUTORIAL scope … The five canonical worked-example
 * records live ONLY here") — so on every ordinary screen that sentence asserted
 * contents that are not there. Same defect class, and same correction, as the mode
 * chip: see `components/TopBar.tsx`, "THE SCOPE DECIDES THE LABEL".
 *
 * ONE SENTENCE CANNOT BE TRUE OF BOTH SCOPES, which is why this is a branch rather
 * than a rewording. The record read is keyed on the same `scope` value (see D1
 * below), so this page really does describe either workspace: only the session
 * scope holds examples, and only the ordinary scope can be named without them.
 *
 * The four other things listed are unchanged and are not scope claims: workflow
 * readiness and evidence are derived from whichever records were read, while
 * Project Memory and the API surface are properties of the build.
 */
function leadSentence(scope: string | null): string {
  const workspace = scope === null ? 'this workspace' : 'the open worked-example workspace';
  return (
    `A read-only view of ${workspace}, workflow readiness, evidence, Project ` +
    'Memory, and the API surface.'
  );
}

/**
 * A compact, localized failure note. Neutral rather than alarm-coloured, with
 * the recourse (a real button, keyboard reachable) still offered.
 *
 * THE RULE THIS PAGE FOLLOWS IS ONE ALARM PER FAILED SOURCE, NOT ONE PER PAGE.
 * The four reads are independent, so each dead source states itself ONCE, as a
 * full `BackendDown`, at the first section that reads it; every FURTHER section
 * reading that same source gets this compact note instead, because repeating the
 * identical alarm three times would be noise. Three simultaneously dead sources
 * therefore do produce three alarms — and that is the intent: they are three
 * different failures, and collapsing them into one panel would hide which
 * sources are actually down while the degraded banner above says "3 of 4 reads
 * failed". Only the ALL-FOUR-failed case collapses, into the single page-level
 * `BackendDown`, because there is then nothing left to localize.
 *
 * `/api/about` is the one deliberate exception, and it is quieter rather than
 * louder: its failure costs two supporting cards inside a section whose four
 * record cards are still fine, so it states itself with this note at its only
 * reader. An alarm panel there would out-shout the figures beside it that were
 * read successfully.
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

export function StatisticsPage() {
  /*
   * Round tracking. `useFetch` exposes no completion callback, so the four
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
   * of the four reads can settle in the same tick, so a functional
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
   * The graph status, the About payload and the OpenAPI schema are properties of
   * the build rather than of a workspace, so they are deliberately left unkeyed.
   */
  const scope = useWorkspaceScope();
  const records = useFetch(() => track(api.getRuntimeRecords()), [scope]);
  const graph = useFetch(() => track(api.getGraphStatus()), []);
  const about = useFetch(() => track(api.getAbout()), []);
  const openapi = useFetch(() => track(api.getOpenApi()), []);

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
    // and scroll position is kept. Four GETs, no write, no third endpoint.
    records.reloadSilent();
    graph.reloadSilent();
    about.reloadSilent();
    openapi.reloadSilent();
    setRefreshing(true);
    setRefreshMessage('Refreshing — re-reading the API.');
  }

  const allFailed =
    records.status === 'error' &&
    graph.status === 'error' &&
    about.status === 'error' &&
    openapi.status === 'error';

  function retryAll() {
    records.reload();
    graph.reload();
    about.reload();
    openapi.reload();
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
        <p>{leadSentence(scope)}</p>
      </div>

      <div className="statistics">
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
            <WorkspaceGlance records={records} about={about} />
            <WorkflowDistribution records={records} />
            <EvidenceAndValidation records={records} />
            <ProjectMemoryFacts graph={graph} />
            <ApiSurface openapi={openapi} />
            <NoAnalytics />
          </>
        )}
      </div>
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

/**
 * The at-a-glance row. The four record cards and the two runtime cards read
 * DIFFERENT endpoints, so they fail independently: a dead `/api/about` leaves
 * the record cards in place and states the two runtime facts as unavailable.
 *
 * There is no "Database Online" card and no health score here. `Persistence` is
 * reported verbatim from the API and never dressed up as a durable database.
 */
function WorkspaceGlance({ records, about }: { records: RecordsFetch; about: AboutFetch }) {
  return (
    <StatsSection
      id="stats-glance"
      title="Workspace at a Glance"
      sub="Counts for the records this workspace holds right now, plus what this build reports about itself."
      icon={<LayoutList size={18} strokeWidth={2} aria-hidden="true" />}
    >
      {records.status === 'loading' && <LoadingPanel label="Loading the workspace summary…" />}
      {records.status === 'error' && <BackendDown error={records.error} onRetry={records.reload} />}
      {records.status === 'data' && <GlanceRecordCards body={records.data} />}

      {about.status === 'loading' && (
        <LoadingPanel label="Loading the runtime mode and persistence…" />
      )}
      {about.status === 'error' && (
        <div className="stats-block">
          <SectionUnavailable
            message="This build's runtime mode and persistence could not be read from the API, so neither is stated here."
            onRetry={about.reload}
          />
        </div>
      )}
      {about.status === 'data' && <GlanceRuntimeCards body={about.data} />}
    </StatsSection>
  );
}

/**
 * The two runtime facts `/api/about` reports about this build.
 *
 * Each is stated only if the response actually carried a usable string. A
 * malformed field becomes the same unavailable literal every other absent figure
 * on this page uses, in the neutral `quiet` tone — not an error, and not a
 * guessed default such as "Synthetic-Only", which would be the one substitution
 * this project forbids outright. Rendering never throws on this body.
 */
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

  /* Defensive only. The workspace always holds its canonical synthetic records
     and this app exposes no delete, so this branch is not reachable through the
     shipped product; it exists so an empty body renders an honest sentence
     instead of a grid of zeros. */
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
        <LoadingPanel label="Loading the workflow distribution…" />
      )}
      {records.status === 'error' && (
        <SectionUnavailable
          message="The workspace records could not be read, so there is no workflow distribution to show."
          onRetry={records.reload}
        />
      )}
      {records.status === 'data' && <WorkflowBars records={records.data.records} />}
    </StatsSection>
  );
}

function WorkflowBars({ records }: { records: RuntimeRecord[] }) {
  if (records.length === 0) {
    return (
      <p className="stats-note">
        No records were returned, so there is no distribution to show. No bar is drawn rather than a
        row of zeros.
      </p>
    );
  }
  const stages = deriveWorkflowStages(records);
  return (
    <StageBars
      caption={`Records by current workflow step, out of ${count(records.length)} counted`}
      rows={stages.map((stage) => ({
        id: stage.id,
        label: stage.label,
        count: stage.count,
        toneIndex: STAGE_TONE[stage.id],
      }))}
      total={records.length}
    />
  );
}

/* ---- 3 · Evidence and Validation -------------------------------------- */

function EvidenceAndValidation({ records }: { records: RecordsFetch }) {
  return (
    <StatsSection
      id="stats-evidence"
      title="Evidence and Validation"
      sub="Two separate readings of the same records: how well their fields are supported by evidence, and where each record stands against the export gate."
      icon={<ShieldCheck size={18} strokeWidth={2} aria-hidden="true" />}
    >
      {records.status === 'loading' && (
        <LoadingPanel label="Loading evidence and export-gate counts…" />
      )}
      {records.status === 'error' && (
        <SectionUnavailable
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
            by Open Questions means the gate has not been reached yet. Stale Artifacts overlaps the
            rows above — an exported record whose draft has since changed is both — so it must not be
            added to them.
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

/* ---- 4 · Project Memory ----------------------------------------------- */

function ProjectMemoryFacts({ graph }: { graph: GraphFetch }) {
  return (
    <StatsSection
      id="stats-memory"
      title="Project Memory"
      sub="What the served memory snapshot reports about itself. This is the memory and query plane — it is never the authority on record validity."
      icon={<Network size={18} strokeWidth={2} aria-hidden="true" />}
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

/* ---- 5 · API Surface --------------------------------------------------- */

function ApiSurface({ openapi }: { openapi: OpenApiFetch }) {
  return (
    <StatsSection
      id="stats-api"
      title="API Surface"
      sub="The shape of the API this build documents, read from its own generated contract. These are the operations that exist — not traffic, which is not recorded anywhere."
      icon={<FileJson size={18} strokeWidth={2} aria-hidden="true" />}
    >
      {openapi.status === 'loading' && <LoadingPanel label="Loading the API contract…" />}
      {openapi.status === 'error' && (
        <BackendDown error={openapi.error} onRetry={openapi.reload} />
      )}
      {openapi.status === 'data' && <ApiSurfaceBody doc={openapi.data} />}
    </StatsSection>
  );
}

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
        <StageBars
          caption="Documented operations by HTTP method"
          rows={surface.byMethod.map((row, index) => ({
            id: row.method,
            label: row.method.toUpperCase(),
            count: row.count,
            toneIndex: index,
          }))}
          total={surface.operationCount}
        />
      </div>
      {/* The one wide block on this page: group names come from the contract's
          own tags and can be long, so this scrolls inside itself rather than
          widening the page. */}
      <div className="stats-block stats-scroll">
        <StageBars
          caption="Documented operations by group, in the contract's own tag order"
          rows={surface.byGroup.map((row, index) => ({
            id: row.group,
            label: row.group,
            count: row.count,
            toneIndex: index,
          }))}
          total={surface.operationCount}
        />
      </div>
      <p className="stats-actions">
        <Link to={ROUTES.settingsTab('explorer')}>Open Endpoint Explorer</Link>
      </p>
    </>
  );
}

/* ---- 6 · No analytics -------------------------------------------------- */

/**
 * Absence of telemetry is a PRIVACY FEATURE, so this section is informational,
 * not a failure: neutral colours, no alert role, no warning glyph, no empty
 * chart, no zero-filled placeholder. The shield is the privacy mark this app
 * already uses, and it is decorative.
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
