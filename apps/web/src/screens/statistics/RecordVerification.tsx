import './statistics.css';

import { Table2 } from '../../components/icons';
import type { FetchState } from '../../lib/useFetch';
import {
  ORACLE_LABELS,
  formatAgeSeconds,
  formatDurationMs,
  histogramRows,
  histogramTotal,
  mutationGroups,
  notReadyMessage,
  oracleFigures,
  oracleTotal,
  readVerificationBody,
  safeguardCountRows,
  safeguardRows,
  suppressionDisclosure,
  validatorSplit,
  type SafeguardTone,
  type VerificationFigure,
  type VerificationHistogram,
  type VerificationReport,
} from '../../lib/verificationContract';
import {
  ChartEmpty,
  ChartError,
  ChartLoading,
  ChartSourceUnavailable,
  StatsBarChart,
  StatsStackedBar,
} from './StatsCharts';
import { FigureList, StatCard, StatsSection } from './StatsPrimitives';

/**
 * Statistics · Record Verification — the rendered view of
 * `GET /api/runtime/verification`.
 *
 * COMPOSITION ONLY, exactly like the rest of this page. Every figure below is a
 * count the API sent; `lib/verificationContract.ts` decodes the body and owns
 * every derivation, and this file formats strings and picks forms. It computes
 * no figure of its own, holds no state, and reads no clock.
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
 * ── THE TRI-STATE SAFEGUARDS ARE THE POINT OF THIS SECTION ─────────────────
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
 * than as data. The two validator results are drawn as STACKED BARS, because
 * passing and not-passing are mutually exclusive over one known whole; the issue
 * distributions are drawn as horizontal BAR CHARTS on a shared axis, scaled to
 * the largest category and not to the total. Both forms already exist on this
 * surface and neither is re-implemented here.
 *
 * ── A ZERO IS GOOD NEWS HERE, AND IS DRAWN THAT WAY ────────────────────────
 *
 * Every self-check count and both statement counts SHOULD be 0 — they count
 * things that went wrong. A zero is therefore rendered calmly and affirmatively
 * rather than as an empty or alarming state, and the copy says what the zero
 * means so the reader is not left to infer it.
 */

/** What `useFetch` hands back, matching `StatisticsPage`'s own `Fetched<T>`. */
type VerificationFetch = FetchState<unknown> & { reload: () => void; reloadSilent: () => void };

/** The one literal this page uses wherever a figure genuinely was not returned. */
const UNAVAILABLE = 'Not Available';

export function RecordVerification({ verification }: { verification: VerificationFetch }) {
  return (
    <StatsSection
      id="stats-verification"
      title="Record Verification"
      sub="Aggregate results of an automated program that checks official ISAAC records against ISAAC's own validator, against a stricter format-aware second validator, and against a harness that injects small deterministic changes and checks the validator reacts as the change was designed to make it react. Every figure is a count across the whole corpus; no individual record is named."
      icon={<Table2 size={18} strokeWidth={2} aria-hidden="true" />}
    >
      {verification.status === 'loading' && (
        <ChartLoading label="Loading the verification report…" />
      )}
      {verification.status === 'error' && (
        <ChartError
          message="The verification report could not be read from the API, so no result from it is stated here."
          onRetry={verification.reload}
        />
      )}
      {verification.status === 'data' && <VerificationBody body={verification.data} />}
    </StatsSection>
  );
}

/**
 * The three things the body can be, decided by the contract module rather than
 * by branching on fields here. A report that is not fully readable never reaches
 * the figure-rendering path at all.
 */
function VerificationBody({ body }: { body: unknown }) {
  const view = readVerificationBody(body);

  if (view.kind === 'notReady') {
    const message = notReadyMessage(view.status);
    return (
      <ChartSourceUnavailable title={message.title}>{message.body}</ChartSourceUnavailable>
    );
  }

  if (view.kind === 'unreadable') {
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

  return <VerificationReportBody report={view.report} />;
}

function VerificationReportBody({ report }: { report: VerificationReport }) {
  const official = validatorSplit(
    report.official_validation.passing,
    report.official_validation.failing,
  );
  const shadow = validatorSplit(
    report.format_shadow.records_passing,
    report.format_shadow.records_failing,
  );
  const mutations = report.mutations;

  return (
    <>
      {/* Four headline figures with no shared scale and no ordering between
          them — the KPI form, deliberately not a chart, for the same reason
          `WorkspaceGlance` gives. */}
      <div className="stats-cards">
        <StatCard
          label="Records Evaluated"
          value={String(report.corpus.records_scanned)}
          note="records in the corpus this run examined."
        />
        <StatCard
          label="Official Validation"
          value={`${report.official_validation.passing} of ${official.total}`}
          note={`records satisfying the official ISAAC schema; ${report.official_validation.failing} do not.`}
          tone={report.official_validation.failing === 0 ? 'good' : 'neutral'}
        />
        <StatCard
          label="Stricter Format Checks"
          value={`${report.format_shadow.records_passing} of ${shadow.total}`}
          note={`records with no format issue; ${report.format_shadow.records_failing} have at least one.`}
          tone={report.format_shadow.records_failing === 0 ? 'good' : 'neutral'}
        />
        <StatCard
          label="Mutation Verification"
          value={String(mutations.trials_attempted)}
          note={`trials run; ${mutations.unexpected_outcomes} behaved unexpectedly.`}
          tone={mutations.unexpected_outcomes === 0 ? 'good' : 'attention'}
        />
      </div>

      {/* The comparison. TWO stacked bars rather than one grouped chart: each
          validator's own passing/not-passing counts are mutually exclusive over
          a whole that validator itself defines, and those two wholes are not
          guaranteed to be the same number. Drawing them on one shared axis would
          invite adding four bars that partition two different totals. */}
      <div className="stats-block stats-columns">
        <div className="stats-group">
          <StatsStackedBar
            caption={`Official ISAAC schema check, over ${official.total} records`}
            rows={official.rows}
            total={official.total}
            unit="records"
            categoryHeader="Outcome"
            note="ISAAC's own official validator — the authority on whether a record is valid. This section reports its result and does not change it."
          />
        </div>
        <div className="stats-group">
          <StatsStackedBar
            caption={`Stricter format-aware check, over ${shadow.total} records`}
            rows={shadow.rows}
            total={shadow.total}
            unit="records"
            categoryHeader="Outcome"
            note="A second, stricter validator run alongside the official one. It reports format issues the official schema tolerates, and it decides nothing: it can never make a record invalid."
          />
        </div>
      </div>

      <div className="stats-block stats-group">
        <h3>Where the Stricter Checks Disagreed</h3>
        <IssueDistribution
          caption="Format issues by check name"
          categoryHeader="Check"
          histogram={report.format_shadow.failures_by_error_code}
          emptyTitle="No Format Issues by Check Name"
        />
        <IssueDistribution
          caption="Format issues by position in the ISAAC schema"
          categoryHeader="Schema Position"
          histogram={report.format_shadow.failures_by_schema_path}
          emptyTitle="No Format Issues by Schema Position"
          note="These positions are places in the ISAAC schema, not places inside any record."
        />
      </div>

      <MutationPanel report={report} />
      <SafeguardsPanel report={report} />
      <RunDetails report={report} />
    </>
  );
}

/* ---- issue distributions ----------------------------------------------- */

/**
 * One suppressed histogram as a horizontal bar chart.
 *
 * THE SUPPRESSION NOTE IS NOT OPTIONAL. When the backend withheld categories,
 * the count of withheld categories and the occurrences they account for are
 * stated in VISIBLE copy under the caption — because without it the visible
 * bars read as the whole distribution. The withheld KEYS are not in the payload
 * and there is nowhere here that could render one.
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
}: {
  caption: string;
  categoryHeader: string;
  histogram: VerificationHistogram;
  emptyTitle: string;
  note?: string;
}) {
  const suppression = suppressionDisclosure(histogram);

  if (histogram.cells.length === 0) {
    return (
      <ChartEmpty title={emptyTitle}>
        {suppression === null
          ? 'No occurrence was recorded in this breakdown, so no bar is drawn rather than a row of zeros.'
          : `Every category in this breakdown is below the disclosure floor. ${suppression}`}
      </ChartEmpty>
    );
  }

  const scaleNote =
    'Bars share one scale, marked beneath them. The scale runs to the largest category, not to the total.';
  return (
    <div className="stats-block">
      <StatsBarChart
        caption={caption}
        rows={histogramRows(histogram)}
        unit="occurrences"
        total={histogramTotal(histogram)}
        categoryHeader={categoryHeader}
        note={[note, scaleNote, suppression].filter((part) => part != null).join(' ')}
      />
    </div>
  );
}

/* ---- mutation harness --------------------------------------------------- */

/**
 * The harness, in four labelled groups with three different tones.
 *
 * The split carries the meaning. "391 trials behaved as designed" and "0 trials
 * behaved unexpectedly" are opposite kinds of news and a single list of seven
 * counts makes them look alike — so the expected group, the unexpected group and
 * the checks on the run itself are visually distinct AND separately labelled in
 * plain words. Tone is decoration: each group states in text what it counts.
 */
function MutationPanel({ report }: { report: VerificationReport }) {
  const groups = mutationGroups(report.mutations);
  const unexpected = report.mutations.unexpected_outcomes;
  const selfChecks = oracleTotal(report.oracles);

  return (
    <div className="stats-block stats-group">
      <h3>Mutation Verification</h3>
      <p className="stats-note">
        Each trial takes a copy of one record, makes one small deliberate change to it, and
        checks that the validator reacts the way that change was designed to make it react. The
        records themselves are never altered.
      </p>

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
      <FigureList rows={figures.map((f) => ({ label: f.label, value: String(f.value), mono: true }))} />
    </div>
  );
}

/* ---- safeguards --------------------------------------------------------- */

/**
 * The tri-state panel.
 *
 * EVERY ROW RENDERS ITS STATE AS A WORD, from `SAFEGUARD_STATE_LABELS` — three
 * distinct words for three distinct states. Nothing here maps two states onto
 * one presentation, and there is no tick glyph anywhere in this panel: a tick
 * beside "Not applicable" is precisely how the affirmative reading gets back in
 * after the word was kept out.
 *
 * The two counts are separate, and a 0 is stated calmly and affirmatively —
 * these count statements that would have changed something, so none is the good
 * reading and the sentence says so.
 */
function SafeguardsPanel({ report }: { report: VerificationReport }) {
  const rows = safeguardRows(report.safeguards);
  const counts = safeguardCountRows(report.safeguards);

  return (
    <div className="stats-block stats-group">
      <h3>Verification Safeguards</h3>
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
          rows={counts.map((c) => ({ label: c.label, value: String(c.value), mono: true }))}
        />
      </div>
    </div>
  );
}

/* ---- run details -------------------------------------------------------- */

/**
 * When the run happened, what it ran against, and what it cannot establish.
 *
 * `verification_mode` is rendered VERBATIM, in the mono face, as a disclosure of
 * which corpus was evaluated. It is not mapped onto a friendlier phrase: the
 * value is a closed enum on the wire and a build that received an unfamiliar
 * member must show what it received rather than a word chosen here.
 *
 * `limitations` is the report's own statement of what its numbers do not
 * establish, rendered as it arrived. Rewriting it in this file would put the UI
 * in the position of deciding how strong the report's own caveats are.
 */
function RunDetails({ report }: { report: VerificationReport }) {
  return (
    <div className="stats-block stats-group">
      <h3>About This Run</h3>
      <FigureList
        rows={[
          { label: 'Report Generated', value: report.metadata.generated_at, mono: true },
          { label: 'Report Age', value: formatAgeSeconds(report.metadata.cache_age_seconds) },
          { label: 'Run Duration', value: formatDurationMs(report.metadata.duration_ms) },
          { label: 'Corpus Size', value: String(report.metadata.corpus_size), mono: true },
          { label: 'Verification Mode', value: report.metadata.verification_mode, mono: true },
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
