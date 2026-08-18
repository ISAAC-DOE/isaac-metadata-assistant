import './statistics.css';
import { useCallback, useEffect, useRef, useState } from 'react';

import { ShieldCheck, Table2 } from '../../components/icons';
import { api } from '../../lib/api';
import {
  ORACLE_LABELS,
  VALIDATOR_SERIES,
  VERIFICATION_CACHE_TTL_SECONDS,
  corpusDisclosure,
  corpusSizeMismatch,
  formatAgeSeconds,
  formatDurationMs,
  histogramIsEmpty,
  histogramRowsWithSuppressed,
  histogramTotal,
  mutationGroups,
  mutationReconciliation,
  notReadyMessage,
  oracleFigures,
  oracleTotal,
  readVerificationBody,
  reconciliationMismatch,
  reportFreshness,
  safeguardCountRows,
  safeguardRows,
  shadowErrorCodeLabel,
  SUPPRESSED_ROW_KEY,
  suppressionDisclosure,
  validatorComparison,
  validatorComparisonSummary,
  type CorpusDisclosure,
  type MutationIdentity,
  type SafeguardTone,
  type ValidatorComparisonGroup,
  type VerificationFigure,
  type VerificationHistogram,
  type VerificationReport,
  type VerificationView,
} from '../../lib/verificationContract';
import {
  axisTicks,
  horizontalBars,
  niceMax,
  round,
  shareLabel,
} from './chartGeometry';
import {
  ChartEmpty,
  ChartError,
  ChartFrame,
  ChartLegend,
  ChartLoading,
  ChartSourceUnavailable,
  StatsBarChart,
  useChartWidth,
} from './StatsCharts';
import { FigureList, StatCard, StatsSection, UnavailableNote } from './StatsPrimitives';

/**
 * Statistics · Record Verification — the rendered view of
 * `GET /api/runtime/verification`.
 *
 * Every figure below is a count the API sent; `lib/verificationContract.ts`
 * decodes the body and owns every derivation, and this file formats strings,
 * picks forms, and owns the RUNTIME STATES. It computes no figure of its own and
 * reads no clock.
 *
 * ── WHAT THE SECTION IS SAYING ─────────────────────────────────────────────
 *
 * An automated program runs three things over a corpus of official ISAAC
 * records: ISAAC's own official-schema validator, a stricter format-aware second
 * validator, and a harness that injects small deterministic changes into a copy
 * of each record and checks that the validator reacts the way the change was
 * designed to make it react. The section reports the AGGREGATE outcome of all
 * three, and nothing else. No record id, title, field value or per-record
 * outcome is in the payload, so there is no slot here for one.
 *
 * ── WHICH CORPUS RAN IS THE HIGHEST-STAKES THING ON THIS SCREEN ────────────
 *
 * Two corpora can produce this report and they carry very different weight. A
 * public-corpus result displayed as if it came from the authorized sample would
 * misattribute every figure at once, and nothing else on the screen would look
 * wrong. So the corpus is stated FIRST, before any count, as a product name AND
 * as the wire token verbatim; an unrecognised token becomes its own label rather
 * than being mapped onto either shipped one. See `corpusDisclosure`.
 *
 * ── THE RUNTIME STATES ARE THE OTHER HALF OF THE JOB ───────────────────────
 *
 * This section owns its own read, deliberately. The report is a cached artifact
 * of a program run that can take ~19 seconds and states its own age — not a live
 * view of this workspace — so it is outside the page's Refresh and its round
 * tracker (`StatisticsPage.tsx`'s header records why), and it needs states the
 * page's shared 3-state hook cannot express: a run still in progress, a result
 * older than the backend's own cache lifetime, a re-read in flight, and a
 * re-read that FAILED while a good earlier result is still on screen.
 *
 * That last one is the reason the read is owned here rather than injected as a
 * fetch state. A silent reload that only records "the last refresh failed" as a
 * boolean cannot report two consecutive failures — the second sets the same
 * value, React bails out, and the control stays stuck announcing a refresh that
 * already ended. Holding the promise makes every settle observable.
 *
 * NOTHING POLLS. There is no interval, no timeout and no retry loop anywhere in
 * this file: one read on mount, and one more per press. A `running` report is
 * reported as running, with a control the reader may press again — an automatic
 * poll against a sweep that opens a database connection in one of its modes is
 * exactly the shape the backend's own rate limiter exists to survive, and this
 * client will not be the thing testing it.
 *
 * THAT INVARIANT PUTS THE WHOLE WEIGHT OF THE `running` STATE ON ITS DESIGN,
 * and for a while the design did not carry it — see `RunInProgressPanel`.
 *
 * ── THE TRI-STATE SAFEGUARDS ───────────────────────────────────────────────
 *
 * `not_applicable` is rendered as its own state, in its own words, with its own
 * reason — never as an affirmative and never as the word "Verified". A
 * read-only-transaction safeguard reading "Verified" when no database was
 * contacted would be a claim nobody measured, which is the exact defect class
 * this project has shipped and corrected repeatedly (`CLAUDE.md` §15). The
 * contract module keeps the three states apart all the way to the string; this
 * file renders whichever string it is handed and chooses no word of its own.
 *
 * ── WHY NOT A PROGRESS BAR, ANYWHERE ───────────────────────────────────────
 *
 * `StatsPrimitives.tsx` records why `StageBars` was deleted: a mark scaled
 * against a total, with no axis and no table, reads as a progress track rather
 * than as data. The two validators are drawn as a GROUPED bar chart on a shared
 * axis with a legend, a summary sentence and a data table; the issue
 * distributions are horizontal BAR CHARTS scaled to the largest category and not
 * to the total. Every value is real HTML text beside its mark, so both survive
 * with all colour removed.
 *
 * ── A ZERO IS GOOD NEWS HERE, AND IS DRAWN THAT WAY ────────────────────────
 *
 * Every self-check count and both statement counts SHOULD be 0 — they count
 * things that went wrong. A zero is therefore rendered calmly and affirmatively
 * rather than as an empty or alarming state, and the copy says what the zero
 * means so the reader is not left to infer it.
 *
 * ── THIS FILE RENDERS TWO SECTIONS, NOT ONE ────────────────────────────────
 *
 * `RecordVerification` returns a FRAGMENT: the `Record Verification` section,
 * and — only when a readable report is on screen — a sibling `h2` section
 * `Verification Safeguards`. They were one section with the safeguards as an
 * `h3` inside it.
 *
 * THE SPLIT IS A CONSEQUENCE OF PROMOTING THIS MATERIAL TO THE LEDE. Record
 * Verification is now the first thing on the page, and the reorganisation that
 * put it there moved supporting PROSE into collapsed disclosures at the foot.
 * The safeguards panel is not prose: it renders six tri-state MEASUREMENTS and
 * two counts, so it may not be collapsed — and once it is neither collapsed nor
 * buried three screens down inside another section, its own `h2` is what it
 * actually is. `A safeguard that does not apply is not a safeguard that held.`
 * is kept verbatim beside it, because that sentence is the whole reason the
 * three states are not two.
 *
 * The safeguards section renders ONLY for a readable report, exactly as the
 * panel did: a `running`, `refused`, `unavailable`, `error` or unreadable body
 * carries no safeguard block, and drawing an empty one would state six absences
 * as six measurements.
 *
 * ── THE FRESHNESS STRIP, AND WHY IT IS NOT THE PAGE'S CLOCK ────────────────
 *
 * `Report Generated` and `Report Age` used to sit at the BOTTOM of the section,
 * in `About This Run`, three screens below the figures they date. They are now
 * a strip directly under the corpus banner, beside the re-read control.
 *
 * THEY ARE STILL THE REPORT'S CLOCK AND NOT THE PAGE'S. `StatisticsPage`'s
 * `Last Read From the API` is a CLIENT-side instant captured when one of its own
 * five reads returned a body; these two are SERVER-side values the report
 * carries about the program run that produced it, and `Report Age` is measured
 * against the backend's cache rather than against this browser. Merging them
 * would produce a single timestamp that is true of neither. The two stay in
 * different places, under different labels, for that reason.
 */

/** The one literal this page uses wherever a figure genuinely was not returned. */
const UNAVAILABLE = 'Not Available';

/* ---- the announcements, in one place ----------------------------------- */

const ANNOUNCE_REFRESH_STARTED = 'Re-reading the verification report.';
const ANNOUNCE_REFRESH_DONE = 'The verification report was re-read.';
const ANNOUNCE_REFRESH_FAILED =
  'The verification report could not be re-read. The results shown are the ones last read ' +
  'successfully.';

/* ---- the read this section owns ---------------------------------------- */

/**
 * What the section has been able to read, which is NOT the same question as
 * what the report says.
 *
 * `read` means a body arrived and could be parsed as JSON — including a body
 * whose own `status` is `running`, `unavailable`, `refused` or `error`. Those
 * are answers, and they are decoded and rendered by the contract module.
 * `unreachable` means no body arrived at all, which is a different failure and
 * gets a different state: the API could not be reached, so the report cannot
 * even say that it has nothing to say.
 */
type ReadPhase =
  | { kind: 'loading' }
  | { kind: 'read'; body: unknown }
  | { kind: 'unreachable' };

/** Everything the section renders from, and the two controls it offers. */
export interface VerificationReportState {
  phase: ReadPhase;
  /** A re-read is in flight. The previous result stays on screen throughout. */
  refreshing: boolean;
  /** The LAST re-read failed, and an earlier good body is still being shown. */
  refreshFailed: boolean;
  /** What the live region says. Changes only in response to a press. */
  announcement: string;
  refresh: () => void;
  retry: () => void;
  /**
   * Drop a finished announcement.
   *
   * Called when the section MOUNTS, because this state outlives it: the General
   * tab panel unmounts on a switch to My Stats, and returning would otherwise
   * rebuild the live region with the previous press's sentence already inside
   * it — which is the "a live region that appears together with its message"
   * case, announcing something that did not just happen.
   */
  clearAnnouncement: () => void;
}

export interface RecordVerificationProps {
  verification: VerificationReportState;
}

function defaultRead(): Promise<unknown> {
  return api.getVerification();
}

/**
 * The section's read, its refresh, and its announcements.
 *
 * ── WHY THIS IS A HOOK CALLED BY THE PAGE, NOT STATE INSIDE THE SECTION ────
 *
 * The section is mounted inside the General ISAAC tab panel, and that panel is
 * UNMOUNTED when the reader switches to My Stats. State held here would be lost
 * on the way out and a fresh read issued on the way back — so simply moving
 * between two tabs would re-issue a request for a ~19-second program run that,
 * in one of its modes, opens a database connection. `my-stats.test.tsx`'s
 * "switching tabs is free" is the assertion that caught exactly that, and it is
 * a correctness rule rather than a preference. `StatisticsPage` outlives both
 * panels, so the hook lives there and the state is handed down.
 *
 * ── WHY NOT `useFetch` ─────────────────────────────────────────────────────
 *
 * The shared hook's silent reload records "the last refresh failed" as a
 * boolean and hands back no promise. Two consecutive failures write the same
 * value, React bails out of the re-render, and a caller waiting on that change
 * is left announcing a refresh that already ended. Holding the promise here
 * makes every settle observable, which is what the failed-refresh and
 * failed-twice states need.
 *
 * `read` is injected so a test can drive every state deterministically.
 */
export function useVerificationReport(
  read: () => Promise<unknown> = defaultRead,
): VerificationReportState {
  const [phase, setPhase] = useState<ReadPhase>({ kind: 'loading' });
  const [attempt, setAttempt] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  /** Did the LAST re-read fail while a body from an earlier read is on screen? */
  const [refreshFailed, setRefreshFailed] = useState(false);
  const [announcement, setAnnouncement] = useState('');

  const readRef = useRef(read);
  readRef.current = read;
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  /* ONE read per attempt. `attempt` is bumped only by the reader pressing Retry,
     so this effect is the whole of this section's automatic network activity. */
  useEffect(() => {
    let alive = true;
    setPhase({ kind: 'loading' });
    setRefreshFailed(false);
    readRef.current().then(
      (body) => {
        if (alive) setPhase({ kind: 'read', body });
      },
      () => {
        // The rejection's text is deliberately not captured or rendered: it can
        // carry a URL, a status line or a stack, none of which belongs on a
        // product screen and none of which a reader can act on.
        if (alive) setPhase({ kind: 'unreachable' });
      },
    );
    return () => {
      alive = false;
    };
  }, [attempt]);

  const retry = useCallback(() => setAttempt((n) => n + 1), []);

  /**
   * A re-read that keeps the current result on screen until a new one arrives.
   *
   * On rejection the previous body STAYS — a failed re-read is not a reason to
   * discard a measurement that did arrive — and the failure is stated in visible
   * copy as well as announced, so nothing on screen is silently older than it
   * looks.
   */
  const refresh = useCallback(() => {
    if (refreshing) return;
    setRefreshing(true);
    setAnnouncement(ANNOUNCE_REFRESH_STARTED);
    readRef.current().then(
      (body) => {
        if (!mountedRef.current) return;
        setPhase({ kind: 'read', body });
        setRefreshFailed(false);
        setRefreshing(false);
        setAnnouncement(ANNOUNCE_REFRESH_DONE);
      },
      () => {
        if (!mountedRef.current) return;
        setRefreshFailed(true);
        setRefreshing(false);
        setAnnouncement(ANNOUNCE_REFRESH_FAILED);
      },
    );
  }, [refreshing]);

  const clearAnnouncement = useCallback(() => setAnnouncement(''), []);

  return { phase, refreshing, refreshFailed, announcement, refresh, retry, clearAnnouncement };
}

export function RecordVerification({ verification }: RecordVerificationProps) {
  const { phase, refreshing, refreshFailed, announcement, refresh, retry, clearAnnouncement } =
    verification;

  /* The state outlives this component (see `clearAnnouncement`), so a sentence
     from a press made before the reader left the tab is dropped on the way back
     in rather than re-announced as if it had just happened. */
  useEffect(() => clearAnnouncement(), [clearAnnouncement]);

  /* Decoded HERE rather than deeper down, because the outcome now decides
     whether a SECOND section renders. `readVerificationBody` is pure and holds
     no state, so calling it at this level costs nothing and keeps the contract
     module the only thing that decides what a body is. */
  const view = phase.kind === 'read' ? readVerificationBody(phase.body) : null;
  const report = view !== null && view.kind === 'report' ? view.report : null;

  return (
    <>
      <StatsSection
        id="stats-verification"
        title="Record Verification"
        sub="Aggregate results of an automated program run over a corpus of official ISAAC records. Every figure is a count across the whole corpus; no individual record is named. How the program works is set out under How Verification Works, at the foot of this page."
        icon={<Table2 size={18} strokeWidth={2} aria-hidden="true" />}
      >
        {/* Present from the FIRST render, so a change to its text is what gets
            announced — a live region that appears together with its message is
            unreliable. It only ever speaks in response to a press. */}
        <p className="stats-verify-live sr-only" role="status">
          {announcement}
        </p>

        {phase.kind === 'loading' && <ChartLoading label="Loading the verification report…" />}

        {phase.kind === 'unreachable' && (
          <ChartError
            message="The verification report could not be read from the API, so no result from it is stated here. Nothing is shown in its place and no count is assumed to be zero."
            onRetry={retry}
          />
        )}

        {view !== null &&
          (view.kind === 'report' ? (
            <VerificationReportBody
              report={view.report}
              refreshing={refreshing}
              refreshFailed={refreshFailed}
              onRefresh={refresh}
            />
          ) : view.kind === 'notReady' && view.status === 'running' ? (
            /* The one not-ready status a reader is meant to WAIT OUT, so it gets
               a designed state of its own rather than the shared not-available
               panel. See `RunInProgressPanel`. */
            <RunInProgressPanel
              refreshing={refreshing}
              refreshFailed={refreshFailed}
              onRefresh={refresh}
            />
          ) : (
            /* No report, so no corpus banner and nothing to date: the control
               leads, because there is nothing above it for it to follow. */
            <>
              <ReadControls refreshing={refreshing} onRefresh={refresh} />
              {refreshFailed && <RefreshFailedNote />}
              <NotReadyBody view={view} />
            </>
          ))}
      </StatsSection>

      {report !== null && <SafeguardsSection report={report} />}
    </>
  );
}

/**
 * The re-read control.
 *
 * ITS ACCESSIBLE NAME NEVER CHANGES. The busy state is carried by `aria-busy`,
 * by the disabled state, by a visible sentence and by the live region — not by
 * relabelling the button, which would move the control out from under a reader
 * who was about to press it again and would break any reference to it by name.
 *
 * THE PARAGRAPH THAT USED TO SIT ABOVE IT MOVED, and it was not deleted: "This
 * report is produced by a program run that is kept off the request path… Nothing
 * on this screen polls" is now the second paragraph of `How Verification Works`
 * on the page. It explains the control rather than reporting anything, and it
 * was three lines of prose standing between the reader and the first figure.
 * `Report Age`, which is the part of it a reader acts on, is rendered beside
 * this button instead.
 *
 * TWO THINGS ARE VARIABLE AND THE NAME IS NOT. `emphasis` picks the button
 * treatment and `busyNote` the sentence beside it, because the run-in-progress
 * state needs a prominent control and cannot say "the results below are still
 * the ones last read" — there are no results below it. The accessible name,
 * which is what every test and every reader addresses this control by, is the
 * same string in every state.
 */
function ReadControls({
  refreshing,
  onRefresh,
  emphasis = 'secondary',
  busyNote = 'Re-reading… the results below are still the ones last read.',
}: {
  refreshing: boolean;
  onRefresh: () => void;
  emphasis?: 'primary' | 'secondary';
  busyNote?: string;
}) {
  return (
    <div className="stats-verify-controls">
      <div className="stats-verify-controls-row">
        <button
          type="button"
          className={emphasis === 'primary' ? 'btn btn-primary' : 'btn btn-secondary'}
          onClick={onRefresh}
          aria-busy={refreshing}
          disabled={refreshing}
        >
          Refresh the verification report
        </button>
        {refreshing && <span className="stats-verify-refreshing">{busyNote}</span>}
      </div>
    </div>
  );
}

/**
 * How long a run takes, as an ORDER OF MAGNITUDE — never as a measurement of the
 * run the reader is waiting on, and never as a countdown.
 *
 * WHERE THE PHRASE COMES FROM, because this repository does not print figures it
 * did not measure. There is no backend constant to mirror: the duration is a
 * property of the corpus and the machine, not of the code, and the `running`
 * envelope carries no metadata at all (`verification.build_pending_report`), so
 * nothing on the wire could tell this build a number. What IS known is the
 * magnitude, from two independent measurements of this build: `e2e/global-setup.ts`
 * records the sweep at "~15s locally", and a cold run measured while this panel
 * was being written reported `metadata.duration_ms` of 19,325. Both are tens of
 * seconds, so tens of seconds is what the copy claims — and it is hedged as
 * typical, because the next corpus may not be this one.
 *
 * A precise "about 20 seconds" was deliberately NOT written. It would read as a
 * property of the run in progress, which this screen cannot see, and it would rot
 * silently the first time the corpus grew.
 */
const RUN_MAGNITUDE = 'tens of seconds';

/**
 * `running`, as a FIRST-CLASS STATE.
 *
 * ── THE DEFECT THIS REPLACES, WHICH WAS MEASURED AND NOT THEORISED ─────────
 *
 * Record Verification is the LEDE of this page, so `running` is what a
 * first-time visitor meets on a cold backend — and `running` is the one state
 * that ends on its own without telling anybody. An independent review loaded
 * `/statistics` against a cold backend and read "Verification Run in Progress"
 * at 5s, 20s, 40s and 65s; the sweep itself had finished at 19.6s. The state was
 * never wrong. It was USELESS: it said what was true, said nothing about what
 * the reader should do, and left the one control that ends the wait sitting
 * above the message as a quiet secondary button that reads as page furniture.
 *
 * ── WHY THE OBVIOUS FIX IS NOT THE FIX ─────────────────────────────────────
 *
 * Polling would repaint the page and would also be the one thing this section is
 * built not to do. The reasons are in this file's header and are real — a sweep
 * that takes tens of seconds, a server-side minimum interval between runs, and
 * as many pollers as there are open tabs — and `record-verification.test.tsx`
 * pins them twice, once by advancing an hour of clock and once by proving
 * nothing is SCHEDULED at all. A presentation defect does not justify weakening
 * a deliberate invariant, so nothing here schedules anything: this is the same
 * one-read-per-press section, wearing a state that admits what it is.
 *
 * ── WHAT IT SAYS, AND WHAT IT MUST KEEP SAYING ─────────────────────────────
 *
 * The first paragraph is `notReadyMessage('running')` VERBATIM — the same title
 * and the same body the shared not-ready panel rendered. It is the load-bearing
 * honesty in this state ("no earlier result is shown in its place"), it is
 * asserted in `record-verification.test.tsx` and in `e2e/specs/statistics-states.spec.ts`,
 * and it is deliberately not re-authored here. What is ADDED is the part the
 * reader was missing: that nothing on this screen will change on its own, what
 * order of time a run takes, and the control — promoted to the primary
 * treatment and placed after the sentence that tells you to press it, rather
 * than before the sentence that explains it.
 *
 * The closing sentence exists so the control does not feel dangerous to press.
 * Both halves are properties of the backend rather than hopes: a request made
 * while a sweep is in flight is answered `running` from the run already under
 * way instead of starting a second one (`verification.VerificationState.report`),
 * and a finished report is held for `CACHE_TTL_SECONDS`, which is the same
 * constant `StalenessNote` already states to the reader.
 */
function RunInProgressPanel({
  refreshing,
  refreshFailed,
  onRefresh,
}: {
  refreshing: boolean;
  refreshFailed: boolean;
  onRefresh: () => void;
}) {
  const message = notReadyMessage('running');
  return (
    <div className="stats-block stats-verify-running">
      <p className="stats-verify-running-title">{message.title}</p>
      <p className="stats-note">{message.body}</p>
      <p className="stats-note">
        The run happens away from this request, so this page is not waiting on it and nothing on
        this screen changes on its own. A run of this program usually takes {RUN_MAGNITUDE}; this
        screen cannot see how far along this one is, and it will not tell you when the result
        lands.
      </p>
      <ReadControls
        refreshing={refreshing}
        onRefresh={onRefresh}
        emphasis="primary"
        busyNote="Re-reading… nothing has been discarded, and no result is being replaced."
      />
      <p className="stats-note">
        Pressing it costs nothing while a run is under way: the API answers from the run already in
        flight rather than starting a second one, and once a report exists it is held for{' '}
        {formatAgeSeconds(VERIFICATION_CACHE_TTL_SECONDS)}.
      </p>
      {/* NOT `RefreshFailedNote`, which qualifies a `Report Age` and a set of
          figures — neither of which exists in this state. Its sentences would
          describe a screen the reader is not looking at. */}
      {refreshFailed && (
        <UnavailableNote>
          <p>
            The most recent attempt to re-read this report did not return anything, so nothing on
            screen has changed: a run in progress is still the last thing this build heard, and no
            result has been assumed in its place.
          </p>
        </UnavailableNote>
      )}
    </div>
  );
}

function RefreshFailedNote() {
  return (
    <div className="stats-block">
      <UnavailableNote>
        <p>
          The most recent attempt to re-read this report did not return anything, so what is shown
          below is the result of the last read that did. It has not been replaced by a guess, and
          the report age shown above was measured at that earlier read — it is older than it says.
        </p>
      </UnavailableNote>
    </div>
  );
}

/**
 * The two things a READ body can be that are not a report, decided by the
 * contract module rather than by branching on fields here. A report that is not
 * fully readable never reaches the figure-rendering path at all.
 *
 * `VerificationView`'s third member (`report`) is handled by the caller, which
 * decodes the body once and needs the outcome to decide whether the sibling
 * safeguards section renders at all.
 *
 * `notReady` WITH STATUS `running` is also handled by the caller, by
 * `RunInProgressPanel`. It is the one status a reader is meant to wait out
 * rather than read and leave, and it needs a control and an expectation this
 * panel has nowhere to put. The branch here is kept rather than narrowed by
 * type: it renders the same message the panel opens with, so a future caller
 * that forgets the split degrades to correct-but-plain instead of to nothing.
 */
function NotReadyBody({ view }: { view: Exclude<VerificationView, { kind: 'report' }> }) {
  if (view.kind === 'notReady') {
    const message = notReadyMessage(view.status);
    return (
      <ChartSourceUnavailable title={message.title}>{message.body}</ChartSourceUnavailable>
    );
  }

  return (
    <ChartSourceUnavailable title="Verification Results Not Shown">
      {view.reason === 'format_version'
        ? `This build reads verification reports in format 2. The API answered in format ${
            view.formatVersion === null ? 'none it stated' : String(view.formatVersion)
          }, so its figures are not displayed rather than displayed under labels that may not match them.`
        : 'The API answered with a body this build cannot read as a verification report, so no figure from it is shown. Nothing is substituted for what could not be read.'}
    </ChartSourceUnavailable>
  );
}

/**
 * The report, in the order a reader needs it.
 *
 * WHAT QUALIFIES A FIGURE COMES BEFORE THE FIGURE. The corpus banner is first —
 * a public-corpus result read as the authorized sample misattributes every count
 * at once — then the freshness strip, which dates the whole report and carries
 * the control that re-reads it, and only then the four headline counts. That
 * order is asserted (`record-verification.test.tsx`, "states the corpus BEFORE
 * the first figure").
 *
 * THE THREE FIGURE GROUPS FOLLOW IN DESCENDING WEIGHT: the two validators side
 * by side, the mutation harness, and the format-issue breakdowns. `About This
 * Run` is last, because it is provenance for everything above it rather than a
 * finding of its own.
 *
 * `About This Run` was NOT moved into a disclosure with the page's supporting
 * prose. Every row in it is a measurement the report carried — run duration,
 * corpus size, the schema fingerprint, the two baseline counts — and the
 * report's own `limitations` list is its statement of what its numbers do not
 * establish. Collapsing measurements is the thing this reorganisation
 * deliberately does not do.
 */
function VerificationReportBody({
  report,
  refreshing,
  refreshFailed,
  onRefresh,
}: {
  report: VerificationReport;
  refreshing: boolean;
  refreshFailed: boolean;
  onRefresh: () => void;
}) {
  const disclosure = corpusDisclosure(report.metadata.verification_mode);
  const [official, shadow] = validatorComparison(
    report.official_validation,
    report.format_shadow,
  );
  const groups = [official, shadow] as const;
  const mutations = report.mutations;

  return (
    <>
      <CorpusBanner report={report} disclosure={disclosure} />
      <FreshnessStrip
        report={report}
        refreshing={refreshing}
        refreshFailed={refreshFailed}
        onRefresh={onRefresh}
      />

      {/* Four headline figures with no shared scale and no ordering between
          them — the KPI form, deliberately not a chart, for the same reason
          `WorkspaceGlance` gives. FOUR, and no more: a fifth card is how a row
          of headlines becomes a second, worse copy of the sections below it.
          `stats-cards-headline` is a NARROW-WIDTH treatment only (two-up rather
          than one-up under 560px); it changes no count and no wording. */}
      {/*
        NOTHING EXAMINED MEANS NOTHING PASSED, AND THESE CARDS USED TO SAY OTHERWISE.

        Each tone was `x === 0 ? 'good' : …` with no zero-DENOMINATOR guard, and
        `data-tone='good'` is the reserved pass palette (`statistics.css` paints it
        with `--pass-bg`/`--pass-border`/`--pass-text`). A corpus of zero therefore
        produced three green cards reading "0 of 0" and "0 behaved unexpectedly",
        with the only honest signal being the neutral fourth card, `Records
        Evaluated: 0`.

        This is REACHABLE, not theoretical, and the backend produces it silently
        rather than refusing: `verification.py` returns `()` for a missing corpus
        directory and `continue`s a file that will not parse, so a single malformed
        fixture — or a fixtures directory absent from the image — shrinks the corpus
        without any error surfacing. `failing = total - passing` is then `0`. And
        this is a FULL report, not the pending envelope, so the client's existing
        refused/partial branches never see it.

        `evaluated` gates all three. A green tone must assert something was checked;
        `neutral` says only that no failure was counted, which is the truth when
        nothing was examined. The same codebase already does this correctly two files
        away — `StatisticsPage` writes "No records were returned, so no fields were
        classified and no count is stated." rather than drawing an empty verdict.
      */}
      {(() => {
        /* Each card gates on ITS OWN denominator rather than on a single
           `records_scanned > 0` flag. They can differ: a record can be scanned and
           still be absent from the shadow tier, so one shared gate would either
           over- or under-claim for one of the three. */
        const nothingExamined =
          ' No records were examined, so this is not a pass — nothing was checked.';
        return (
          <div className="stats-cards stats-cards-headline">
            <StatCard
              label="Records Evaluated"
              value={String(report.corpus.records_scanned)}
              note="records in the corpus this run examined."
            />
            <StatCard
              label="Official Validation"
              value={`${report.official_validation.passing} of ${official.total}`}
              note={
                official.total > 0
                  ? `records satisfying the official ISAAC schema; ${report.official_validation.failing} do not.`
                  : `records satisfying the official ISAAC schema.${nothingExamined}`
              }
              tone={
                official.total > 0 && report.official_validation.failing === 0
                  ? 'good'
                  : 'neutral'
              }
            />
            <StatCard
              label="Format Shadow"
              value={`${report.format_shadow.records_passing} of ${shadow.total}`}
              note={
                shadow.total > 0
                  ? `records with no format issue found by the stricter second validator; ${report.format_shadow.records_failing} have at least one.`
                  : `records with no format issue found by the stricter second validator.${nothingExamined}`
              }
              tone={
                shadow.total > 0 && report.format_shadow.records_failing === 0
                  ? 'good'
                  : 'neutral'
              }
            />
            <StatCard
              label="Mutation Verification"
              value={String(mutations.trials_attempted)}
              note={
                mutations.trials_attempted > 0
                  ? `trials run; ${mutations.unexpected_outcomes} behaved unexpectedly.`
                  : `trials run.${nothingExamined}`
              }
              /* `attention` is withheld too when nothing ran: zero unexpected
                 outcomes out of zero trials is not a finding either way. */
              tone={
                mutations.trials_attempted === 0
                  ? 'neutral'
                  : mutations.unexpected_outcomes === 0
                    ? 'good'
                    : 'attention'
              }
            />
          </div>
        );
      })()}
      {report.corpus.records_scanned === 0 && (
        /*
          AND IT IS STATED ONCE, PLAINLY, ABOVE THE SECTIONS. A reader who takes in
          only the headline row should not have to notice that three tones went
          neutral to learn that the run examined nothing. `role="status"` rather
          than `alert`: it is a fact about the run, not an error in the page.
        */
        <p className="stats-empty-note" role="status">
          This run examined <strong>no records</strong>. Every figure below is
          therefore a count over an empty corpus, and none of them is evidence that
          anything passed. A corpus can be empty because its directory is absent or
          because every file in it failed to parse — neither is reported as an error
          by the run itself.
        </p>
      )}

      <ValidatorComparison groups={groups} />

      <MutationPanel report={report} />

      <div className="stats-block stats-group">
        <h3>Where the Stricter Checks Disagreed</h3>
        {/* `shadowErrorCodeLabel` — the codes were reaching the bar label, the
            table row header and the `sr-only` summary raw
            (`ADDITIONAL_PROPERTIES`, `REQUIRED_MISSING`, …) under a caption that
            called them a "check name". The wire vocabulary is untouched; only
            the presentation is mapped, and an unmapped code still renders as
            itself. */}
        <IssueDistribution
          caption="Format issues by check name"
          categoryHeader="Check"
          histogram={report.format_shadow.failures_by_error_code}
          emptyTitle="No Format Issues by Check Name"
          labelFor={shadowErrorCodeLabel}
        />
        <IssueDistribution
          caption="Format issues by position in the ISAAC schema"
          categoryHeader="Schema Position"
          histogram={report.format_shadow.failures_by_schema_path}
          emptyTitle="No Format Issues by Schema Position"
          note="These positions are places in the ISAAC schema, not places inside any record."
        />
      </div>

      <RunDetails report={report} disclosure={disclosure} />
    </>
  );
}

/**
 * When this report was produced, how old it is, and the control that re-reads it
 * — one strip, directly under the corpus banner.
 *
 * THESE TWO ROWS MOVED UP FROM `About This Run`, where they sat below every
 * figure they date. A report that states its own age is only useful if the age
 * is read before the counts are, and the staleness note — which is the case the
 * age exists to catch — belongs beside the age rather than three screens above
 * it.
 *
 * IT IS THE REPORT'S CLOCK, NOT THE PAGE'S. See this file's header: the page's
 * own `Last Read From the API` is a client-side instant for a different set of
 * reads, and the two are never merged.
 *
 * `RefreshFailedNote` renders here too, because what it qualifies is exactly the
 * `Report Age` beside it: the age was measured at the last read that returned a
 * body, so a failed re-read leaves the report older than the strip says.
 */
function FreshnessStrip({
  report,
  refreshing,
  refreshFailed,
  onRefresh,
}: {
  report: VerificationReport;
  refreshing: boolean;
  refreshFailed: boolean;
  onRefresh: () => void;
}) {
  return (
    <div className="stats-block stats-verify-freshness">
      <div className="stats-verify-freshness-row">
        <FigureList
          rows={[
            { label: 'Report Generated', value: report.metadata.generated_at, mono: true },
            { label: 'Report Age', value: formatAgeSeconds(report.metadata.cache_age_seconds) },
          ]}
        />
        <ReadControls refreshing={refreshing} onRefresh={onRefresh} />
      </div>
      <StalenessNote report={report} />
      {refreshFailed && <RefreshFailedNote />}
    </div>
  );
}

/* ---- which corpus ran --------------------------------------------------- */

/**
 * The corpus disclosure, FIRST and before any count.
 *
 * Three things, in one block, and none of them is optional: the product name for
 * the corpus, the wire token exactly as it arrived, and what that corpus is. The
 * measured `corpus_size` sits beside them so a label carrying a number can be
 * compared against the report's own reading rather than trusted over it.
 */
function CorpusBanner({
  report,
  disclosure,
}: {
  report: VerificationReport;
  disclosure: CorpusDisclosure;
}) {
  const mismatch = corpusSizeMismatch(disclosure.mode, report.metadata.corpus_size);
  return (
    <div className="stats-block stats-verify-corpus" data-known={String(disclosure.known)}>
      <p className="stats-mini-label">Corpus Evaluated</p>
      <p className="stats-verify-corpus-label">{disclosure.label}</p>
      <p className="stats-verify-corpus-mode">
        <span className="stats-verify-corpus-mode-label">Reported as</span>{' '}
        <span className="mono">{disclosure.mode}</span>
      </p>
      <p className="stats-note">{disclosure.description}</p>
      {!disclosure.known && (
        <p className="stats-note">
          The figures below are shown as they arrived, under the labels this report gave them.
        </p>
      )}
      {mismatch !== null && (
        <UnavailableNote>
          <p>{mismatch}</p>
        </UnavailableNote>
      )}
    </div>
  );
}

/**
 * Whether the reader is looking at a current result or a superseded one.
 *
 * Past the backend's own cache lifetime the next request triggers a
 * recomputation and is still answered with the OLD result. That is a deliberate
 * choice there and an unstated one here unless this note exists — the figures
 * look identical either way.
 */
function StalenessNote({ report }: { report: VerificationReport }) {
  if (reportFreshness(report.metadata.cache_age_seconds) === 'fresh') return null;
  return (
    <div className="stats-block">
      <UnavailableNote>
        <p>
          These results were produced {formatAgeSeconds(report.metadata.cache_age_seconds)} ago,
          which is past the {formatAgeSeconds(VERIFICATION_CACHE_TTL_SECONDS)} the API holds one
          for. They are shown rather than withheld, because a measurement with its age stated is
          worth more than a blank panel — but a newer run may already have replaced them.
        </p>
      </UnavailableNote>
    </div>
  );
}

/* ---- official vs shadow ------------------------------------------------- */

/** Height of one bar within a group, in px. */
const GROUP_BAR_HEIGHT = 18;

/**
 * The two validators as a GROUPED horizontal bar chart on one shared axis.
 *
 * FORM. Two groups of two comparable counts is the grouped bar's exact case: the
 * eye compares passing against not-passing WITHIN a validator, and either of
 * them ACROSS the two validators, from one scale. A single stacked bar per
 * validator answers only the first question; two separate charts answer only the
 * second.
 *
 * WHAT IT DELIBERATELY DOES NOT DO IS SUM THE GROUPS. Each group's own total is
 * printed on the group, the shared axis is a nice maximum over the largest
 * single value, and no denominator spanning both validators exists anywhere in
 * this component — the shadow reports its own count of records and this file
 * must not assume it equals the official one.
 *
 * NON-COLOUR IDENTITY IS COMPLETE. Every bar carries its series name and its
 * value as real text on its own row, each group carries its name and its role as
 * a sentence, and the legend pairs each swatch with its series name. Remove
 * every fill and nothing is lost.
 */
function ValidatorComparison({ groups }: { groups: readonly ValidatorComparisonGroup[] }) {
  const [attach, width] = useChartWidth();
  const largest = Math.max(0, ...groups.flatMap((group) => [group.passing, group.failing]));
  const domainMax = niceMax(largest);
  const ticks = axisTicks(domainMax);
  const summary = validatorComparisonSummary(groups);

  return (
    <div className="stats-block stats-group">
      <h3>Official Validation and the Format Shadow, Side by Side</h3>
      <ChartFrame
        caption="Records passing and not passing, by validator"
        summary={summary}
        note="Bars share one scale, marked beneath them. The scale runs to the largest single count, not to any total, and the two validators are never added together: each states its own number of records."
        legend={
          <ChartLegend
            items={VALIDATOR_SERIES.map((series, i) => ({
              key: series.key,
              label: series.label,
              slot: i + 1,
            }))}
          />
        }
        tableRowHeader="Validator"
        tableColumns={['Passing', 'Not Passing', 'Records Counted']}
        tableRows={groups.map((group) => ({
          key: group.key,
          label: group.label,
          cells: [String(group.passing), String(group.failing), String(group.total)],
        }))}
      >
        <div className="stats-chart-plot" ref={attach}>
          {groups.map((group) => (
            <div className="stats-verify-chartgroup" key={group.key}>
              <p className="stats-verify-chartgroup-label">
                {group.label}
                <span className="stats-verify-chartgroup-total mono">
                  {group.total} records
                </span>
              </p>
              <p className="stats-verify-chartgroup-role">{group.role}</p>
              {VALIDATOR_SERIES.map((series, i) => {
                const value = series.key === 'passing' ? group.passing : group.failing;
                const marks = horizontalBars(
                  [{ key: series.key, value }],
                  domainMax,
                  { width, height: GROUP_BAR_HEIGHT },
                );
                const mark = marks[0];
                const share = shareLabel(value, group.total);
                return (
                  <div className="stats-chart-row" key={series.key}>
                    <span className="stats-chart-row-label">
                      {series.label}
                      {share === null ? '' : ` · ${share}`}
                    </span>
                    <span className="stats-chart-row-value mono">{value}</span>
                    <svg
                      className="stats-chart-track"
                      width={width}
                      height={GROUP_BAR_HEIGHT}
                      viewBox={`0 0 ${width} ${GROUP_BAR_HEIGHT}`}
                      aria-hidden="true"
                      focusable="false"
                    >
                      {ticks.map((tick) => (
                        <line
                          key={tick}
                          className="stats-chart-grid"
                          x1={round((tick / domainMax) * width)}
                          x2={round((tick / domainMax) * width)}
                          y1={0}
                          y2={GROUP_BAR_HEIGHT}
                        />
                      ))}
                      {mark !== undefined && (
                        <rect
                          className="stats-chart-bar"
                          data-slot={String(i + 1)}
                          x={0}
                          y={round(mark.y)}
                          width={round(Math.max(0, mark.width))}
                          height={round(mark.height)}
                          rx={2}
                        />
                      )}
                    </svg>
                  </div>
                );
              })}
            </div>
          ))}
          <div className="stats-chart-axis" aria-hidden="true">
            {ticks.map((tick) => (
              <span
                className="stats-chart-tick"
                key={tick}
                data-anchor={tick === 0 ? 'start' : tick === domainMax ? 'end' : 'middle'}
                style={{ left: `${round((tick / domainMax) * 100)}%` }}
              >
                {tick}
              </span>
            ))}
          </div>
        </div>
      </ChartFrame>
      <p className="stats-note">{summary}</p>
      <p className="stats-note">
        The official validator is the authority: this section reports its result and never changes
        it. The format shadow is advisory — it reports issues the official schema tolerates, it can
        never make a record invalid, and it gates nothing.
      </p>
    </div>
  );
}

/* ---- issue distributions ----------------------------------------------- */

/**
 * One suppressed histogram as a horizontal bar chart.
 *
 * THE WITHHELD OCCURRENCES GET THEIR OWN BAR, and the disclosure sentence is not
 * optional. Without both, the visible bars read as the whole distribution. The
 * bar names no category — it cannot, because the withheld KEYS are not in the
 * payload and there is nowhere here that could render one — and the sentence
 * says how many categories were withheld and why.
 *
 * The denominator is the shown occurrences PLUS the withheld ones, so the
 * visible shares deliberately do not add to 100% and the note explains why.
 */
function IssueDistribution({
  caption,
  categoryHeader,
  histogram,
  emptyTitle,
  note,
  labelFor,
}: {
  caption: string;
  categoryHeader: string;
  histogram: VerificationHistogram;
  emptyTitle: string;
  note?: string;
  /**
   * Presentation mapping for the category keys, when a closed vocabulary makes
   * one possible. Omitted for the schema-path breakdown, whose keys are RFC 6901
   * pointers into the public schema and are genuinely the data.
   */
  labelFor?: (key: string) => string;
}) {
  const suppression = suppressionDisclosure(histogram);

  if (histogramIsEmpty(histogram)) {
    return (
      <ChartEmpty title={emptyTitle}>
        No occurrence was recorded in this breakdown, so no bar is drawn rather than a row of
        zeros.
      </ChartEmpty>
    );
  }

  const rows = histogramRowsWithSuppressed(histogram, labelFor);

  /*
   * A THIRD STATE, distinct from both of the others: something WAS withheld, and
   * there is no quantity to plot — every category fell below the floor and the
   * withheld occurrence count was itself withheld, because with one category
   * withheld that count is that category's exact value.
   *
   * It must not fall through to the chart. A `StatsBarChart` with no rows draws
   * an axis over nothing and would read as a measured emptiness. It must not
   * fall through to `emptyTitle` either — "No Format Issues by Check Name"
   * asserts an absence, and this is the opposite: issues were found and cannot
   * be broken down without naming a category. So the disclosure sentence is the
   * whole content, and it is never null on this path (`histogramIsEmpty` is
   * false only because something was withheld).
   */
  if (rows.length === 0) {
    return (
      <ChartEmpty title="Breakdown Withheld">
        {suppression ??
          'This breakdown was withheld in full, and no figure is stated in its place.'}
      </ChartEmpty>
    );
  }

  const scaleNote =
    'Bars share one scale, marked beneath them. The scale runs to the largest category, not to the total.';
  /*
   * Gated on the bar EXISTING, not on there being a disclosure. The withheld
   * bucket is now omitted whenever its count was withheld, so a note asserting
   * "the final bar stands for every withheld category" would describe a bar that
   * is not on screen.
   */
  const withheldNote = rows.some((row) => row.key === SUPPRESSED_ROW_KEY)
    ? 'The final bar stands for every withheld category together; none of them is named here, because their names are not in the report.'
    : null;
  return (
    <div className="stats-block">
      <StatsBarChart
        caption={caption}
        rows={rows}
        unit="occurrences"
        total={histogramTotal(histogram)}
        categoryHeader={categoryHeader}
        note={[note, scaleNote, suppression, withheldNote]
          .filter((part) => part != null)
          .join(' ')}
      />
    </div>
  );
}

/* ---- mutation harness --------------------------------------------------- */

/**
 * The harness, in labelled groups with three tones — plus the accounting shown
 * to reconcile ON SCREEN.
 *
 * The split carries the meaning. "391 trials behaved as designed" and "0 trials
 * behaved unexpectedly" are opposite kinds of news and a single list of seven
 * counts makes them look alike — so the expected group, the unexpected group and
 * the checks on the run itself are visually distinct AND separately labelled in
 * plain words. Tone is decoration: each group states in text what it counts.
 *
 * AND THE TOTALS ARE SHOWN ADDING UP. Seven counts that are supposed to satisfy
 * two identities, printed as seven independent figures, ask the reader to trust
 * that they do. `mutationReconciliation` computes both identities from the
 * values that actually arrived, prints them as arithmetic, and says so plainly
 * when they do not hold — which a tidy total would have hidden.
 */
function MutationPanel({ report }: { report: VerificationReport }) {
  const groups = mutationGroups(report.mutations);
  const identities = mutationReconciliation(report.mutations);
  const unexpected = report.mutations.unexpected_outcomes;
  const selfChecks = oracleTotal(report.oracles);

  return (
    <div className="stats-block stats-group">
      <h3>Mutation Verification</h3>
      {/*
          THE SECOND SENTENCE USED TO READ "The records themselves are never
          altered." — a flat assertion this very panel can contradict.

          A report carrying `source_mutation_failures: 5` and
          `source_records_modified: 'unverified'` rendered all four of these at
          once: that sentence; "Source Records Altered by the Run → 5"; "Source
          Records Left Unchanged → Unverified"; and "This check did not run, so
          nothing here states that it holds." The copy was stating as fact the
          exact thing the safeguards panel was declining to state.

          So the design intent stays (each trial works on a copy — that is what
          the harness is built to do) and the OUTCOME is handed to the data,
          which is measured and already on screen. `not_applicable` and
          `unverified` reach the reader intact instead of being overruled by a
          sentence written in advance.

          THE LAST SENTENCE ALSO NAMES THE SCOPE, since the safeguard it points
          at was renamed to "Source Records Unchanged in Memory": the check is a
          before-and-after comparison of the record objects this process held,
          not a re-read of anything stored. Pointing at a measurement while
          leaving its scope to be assumed is how the stronger reading got back
          in the first time. */}
      <p className="stats-note">
        Each trial works on a copy of one record, makes one small deliberate change to it, and
        checks that the validator reacts the way that change was designed to make it react.
        Whether the source records in this process were in fact left unmodified is one of the
        checks the run makes on itself, and it is reported below rather than promised here — as a
        comparison of the records as this process held them, not as a re-read of anything stored.
      </p>

      <MutationAccounting identities={identities} />

      <FigureGroup label="How Much Was Attempted" tone="neutral" figures={groups.coverage} />

      <FigureGroup
        label="Changes That Behaved as Designed"
        tone="good"
        figures={groups.expected}
        summary="These are the trials where the validator reacted exactly as the injected change intended. A high count here is the expected outcome."
      />

      <FigureGroup
        label="Changes That Behaved Unexpectedly"
        tone={unexpected === 0 ? 'good' : 'attention'}
        figures={groups.unexpected}
        summary={
          unexpected === 0
            ? 'No trial produced an outcome other than the one its change was designed to produce.'
            : 'Each of these trials produced an outcome other than the one its change was designed to produce.'
        }
      />

      <FigureGroup
        label="Checks on the Verification Run Itself"
        tone={selfChecks === 0 ? 'good' : 'attention'}
        figures={oracleFigures(report.oracles)}
        summary={
          selfChecks === 0
            ? `None of the ${Object.keys(ORACLE_LABELS).length} checks on the run itself counted anything. Each row is a number of trials, and 0 is the expected reading.`
            : `${selfChecks} trials tripped a check on the run itself. Each row is a number of trials, and 0 is the expected reading.`
        }
      />
    </div>
  );
}

/**
 * The two accounting identities, printed as arithmetic.
 *
 * Each line names the backend's own field for every term it uses, in the mono
 * face, beside the plain words. Both are rendered on purpose: the words are what
 * a reader who has never seen the wire can act on, and the key is what makes a
 * figure on this screen traceable to the field it came from — a UI that renamed
 * these categories into words of its own would leave the two descriptions of the
 * same number unable to be checked against each other.
 */
function MutationAccounting({ identities }: { identities: readonly MutationIdentity[] }) {
  const balanced = identities.every((identity) => identity.balances);
  return (
    <div className="stats-verify-group" data-tone={balanced ? 'good' : 'attention'}>
      <p className="stats-mini-label">How the Trial Counts Add Up</p>
      <p className="stats-verify-group-note">
        {balanced
          ? 'Every trial is accounted for exactly once in each of these two readings.'
          : 'These counts do not account for every trial exactly once. Both sides of each reading are shown as they arrived.'}
      </p>
      <ul className="stats-verify-identities">
        {identities.map((identity) => (
          <li className="stats-verify-identity" key={identity.key} data-balances={String(identity.balances)}>
            <p className="stats-verify-identity-statement">{identity.statement}</p>
            <p className="stats-verify-identity-keys mono">
              {[identity.total.key, '=', identity.parts.map((part) => part.key).join(' + ')].join(
                ' ',
              )}
            </p>
            {!identity.balances && (
              <p className="stats-verify-identity-mismatch">{reconciliationMismatch(identity)}</p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * One tinted, labelled group of counts.
 *
 * The label and the summary sentence carry the meaning; `data-tone` only tints
 * the box, so every group is fully readable with all colour removed. `FigureList`
 * renders the counts as a real `<dl>`, which is the repo rule for figures.
 */
function FigureGroup({
  label,
  tone,
  figures,
  summary,
}: {
  label: string;
  tone: SafeguardTone;
  figures: readonly VerificationFigure[];
  summary?: string;
}) {
  return (
    <div className="stats-verify-group" data-tone={tone}>
      <p className="stats-mini-label">{label}</p>
      {summary ? <p className="stats-verify-group-note">{summary}</p> : null}
      {/* `hint: f.key` — the backend's own field name beside each plain-word
          label, matching what the accounting identities above already print.
          Without it `operators_defined` appeared on screen only as "Change
          Types Defined", since it is the one mutation count neither identity
          uses. */}
      <FigureList
        rows={figures.map((f) => ({
          label: f.label,
          value: String(f.value),
          mono: true,
          hint: f.key,
        }))}
      />
    </div>
  );
}

/* ---- safeguards --------------------------------------------------------- */

/**
 * The tri-state panel, as its own `h2` SECTION rather than an `h3` inside
 * Record Verification.
 *
 * IT IS NOT PROSE AND IT IS NOT COLLAPSED. Six measured states and two counts;
 * the reorganisation that moved this page's supporting copy into disclosures at
 * the foot deliberately left every measurement in the visible flow, and this is
 * the block that rule was written for. A `<details>` summary reading
 * "Verification Safeguards" is an invitation to skip six findings.
 *
 * EVERY ROW RENDERS ITS STATE AS A WORD, from `SAFEGUARD_STATE_LABELS` — three
 * distinct words for three distinct states. Nothing here maps two states onto
 * one presentation, and there is no tick glyph anywhere in this panel: a tick
 * beside "Not applicable" is precisely how the affirmative reading gets back in
 * after the word was kept out.
 *
 * THE INTRO SENTENCE IS UNCHANGED, to the byte. "A safeguard that does not apply
 * is not a safeguard that held." is the sentence that keeps `not_applicable`
 * from being read as an affirmative, and it is rendered as visible copy inside
 * the section — not as the section's supporting line, where a future tidy-up of
 * subtitles could shorten it away.
 *
 * The two counts are separate, and a 0 is stated calmly and affirmatively —
 * these count statements that would have changed something, so none is the good
 * reading and the sentence says so.
 */
function SafeguardsSection({ report }: { report: VerificationReport }) {
  const rows = safeguardRows(report.safeguards);
  const counts = safeguardCountRows(report.safeguards);

  return (
    <StatsSection
      id="stats-safeguards"
      title="Verification Safeguards"
      icon={<ShieldCheck size={18} strokeWidth={2} aria-hidden="true" />}
    >
      <p className="stats-note">
        What the run did and did not check about itself. Each safeguard states one of three
        things: it was checked, it does not apply to this run, or it was not checked. A
        safeguard that does not apply is not a safeguard that held.
      </p>
      <dl className="stats-verify-safeguards">
        {rows.map((row) => (
          <div className="stats-verify-safeguard" data-tone={row.tone} key={row.key}>
            <dt className="stats-verify-safeguard-label">{row.label}</dt>
            <dd className="stats-verify-state" data-state={row.state}>
              {row.stateLabel}
            </dd>
            <dd className="stats-verify-safeguard-detail">{row.detail}</dd>
          </div>
        ))}
      </dl>
      <div className="stats-verify-group" data-tone={counts.every((c) => c.value === 0) ? 'good' : 'attention'}>
        <p className="stats-mini-label">Statements Counted During the Run</p>
        <p className="stats-verify-group-note">
          {counts.every((c) => c.value === 0)
            ? 'The run counted no statement that would have changed data or structure.'
            : 'The run counted at least one statement that would have changed data or structure.'}
        </p>
        <FigureList
          rows={counts.map((c) => ({
            label: c.label,
            value: String(c.value),
            mono: true,
            hint: c.key,
          }))}
        />
      </div>
    </StatsSection>
  );
}

/* ---- run details -------------------------------------------------------- */

/**
 * When the run happened, what it ran against, and what it cannot establish.
 *
 * `verification_mode` is rendered VERBATIM, in the mono face. The product name
 * for it is stated at the top of the section and repeated here beside the token,
 * never in place of it: the value is a closed enum on the wire and a build that
 * received an unfamiliar member must show what it received rather than a word
 * chosen here.
 *
 * `limitations` is the report's own statement of what its numbers do not
 * establish, rendered as it arrived. Rewriting it in this file would put the UI
 * in the position of deciding how strong the report's own caveats are. It is
 * NOT folded into the page's `Known Limitations` disclosure for that reason:
 * this list is data the report sent, and that disclosure is authored copy about
 * the application.
 *
 * `Report Generated` and `Report Age` USED TO BE THE FIRST TWO ROWS HERE and are
 * now in the freshness strip at the top of the section, beside the control that
 * re-reads the report. They are not duplicated: a figure stated twice on one
 * screen is a figure that can disagree with itself.
 */
function RunDetails({
  report,
  disclosure,
}: {
  report: VerificationReport;
  disclosure: CorpusDisclosure;
}) {
  return (
    <div className="stats-block stats-group">
      <h3>About This Run</h3>
      <FigureList
        rows={[
          { label: 'Run Duration', value: formatDurationMs(report.metadata.duration_ms) },
          { label: 'Corpus Size', value: String(report.metadata.corpus_size), mono: true },
          { label: 'Verification Mode', value: report.metadata.verification_mode, mono: true },
          { label: 'Corpus', value: disclosure.label },
          {
            label: 'Records Meeting the Baseline',
            value: String(report.corpus.records_passing_baseline),
            mono: true,
          },
          {
            label: 'Records Not Meeting the Baseline',
            value: String(report.corpus.records_failing_baseline),
            mono: true,
          },
          { label: 'Schema Version', value: report.schema_version ?? UNAVAILABLE, mono: true },
          {
            label: 'Schema Fingerprint',
            value: report.schema_fingerprint ?? UNAVAILABLE,
            mono: true,
          },
          {
            label: 'Report Format Version',
            value: String(report.report_format_version),
            mono: true,
          },
        ]}
      />
      {report.limitations.length > 0 && (
        <>
          <p className="stats-mini-label">What These Figures Do Not Establish</p>
          <ul className="stats-verify-limits">
            {report.limitations.map((limitation) => (
              <li key={limitation}>{limitation}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
