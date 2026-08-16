import './validate-review.css';
import { useId, useState } from 'react';
import { Check, TriangleAlert, CircleHelp } from './icons';
import { FindingList } from './RunFindingList';
import { runFindingState, type RunFindingState } from './RunFindings';
import { count } from '../lib/assistantPaths';
import { api } from '../lib/api';
import type {
  ApiEvidenceClassification,
  ApiRunCheckFinding,
  ApiRunCheckResponse,
  ApiValidateResult,
  ApiWarningsResponse,
  EvidenceClass,
} from '../lib/types';

/**
 * VALIDATE & REVIEW — one experiment-level action, every finding, grouped by run.
 *
 * WHAT IT IS FOR. A record whose runs each export their own official record has
 * its findings spread across N units, and a scientist could reach them only one
 * run at a time (`RunCard`'s Check Run) or as a passive read-out on the export
 * screen (`RunFindings`). This is the ACTION: press it once, see every run's
 * standing, then open the runs that need work. NOTHING HERE SUBMITS ANYTHING,
 * EXPORTS ANYTHING, OR REPAIRS ANYTHING — every control is a read.
 *
 * ── IT IS NOT A SECOND VALIDATOR, AND THAT IS THE HARDEST CONSTRAINT ──────────
 *
 * Every pass, every failure and every finding on this surface is a field the
 * server already sent. This module contains NO validation logic, derives NO
 * verdict, and classifies NO finding. It calls four routes, all of which already
 * existed:
 *
 *   * `POST /api/experiments/{id}/validate` — the fan-out
 *     (`routes.py::_fan_out_official_verdict` -> `_validate_unit`), whose `runs[]`
 *     carries each unit's own `ok`, `errors`, `dry_run` and `unavailable`;
 *   * `GET /api/experiments/{id}/warnings` — the advisory tier
 *     (`_fan_out_warnings_payload`), which hardcodes `advisory: true,
 *     gating: false` and carries no verdict field at all, by design;
 *   * `GET /api/experiments/{id}/evidence-classification` — the evidence-SUPPORT
 *     axis (`evidence_classify.classify_fields`), whose route docstring says it
 *     "deliberately carries NO validity/completion/advisory verdict";
 *   * `POST /api/experiments/{id}/runs/{runId}/check` — ONE run at a time, only
 *     when asked, for the two things the fan-out does not carry: the run's open
 *     blocking questions and the no-guessing draft report.
 *
 * The state word for a run comes from {@link runFindingState}, IMPORTED from
 * `RunFindings` rather than re-implemented, so the two surfaces cannot disagree
 * about what `unavailable` means. The finding rows come from {@link FindingList},
 * shared with `RunCard`, for the same reason.
 *
 * ── THE SEVERITY MODEL: THREE TIERS, EACH WITH A NAMED SERVER AUTHORITY ───────
 *
 * TIER 1 · BLOCKS EXPORT. Three server channels, each under its own heading:
 *   * the unit's own official/export findings (`validate.runs[i].errors`);
 *   * the run's open blocking questions (`check.blockers`) — export is gated on
 *     there being none. Each entry's `kind` is the server's OWN blocker taxonomy
 *     (`asset` / `series` / `descriptor` / `edge`), so a DESCRIPTOR with nothing
 *     behind it is named as one using the server's word, never a word of ours;
 *   * the no-guessing draft report's errors (`check.draft.errors`) —
 *     `DraftReport.ok` is `not errors`, and `export_draft` refuses on it.
 *
 * TIER 2 · ADVISORY, NEVER BLOCKS. Two server channels, both visually and
 * semantically apart from Tier 1, both labelled non-gating:
 *   * the portal advisory warnings for that run (`warnings.runs[i].warnings`);
 *   * the no-guessing draft report's WARNINGS (`check.draft.warnings`) — the
 *     `report.warn` channel, which `DraftReport.ok` does not read.
 *
 * TIER 3 · NO VERDICT EITHER WAY. The evidence-support axis: CONFLICTS
 * (`conflicting_evidence`), EVIDENCE GAPS (`insufficient_evidence`) and entries
 * whose evidence could not be read (`unreadable`). These are the server's own
 * class names, from a route that states it decides nothing about validity — so
 * they are shown as neither blocking nor advisory, because they are neither, and
 * the heading says which. THEY ARE RECORD-LEVEL, NOT PER RUN:
 * `get_evidence_classification` classifies `exp.draft`, and there is no per-run
 * classification endpoint. Attaching this axis to a run would be a claim the API
 * does not make, so it renders once, outside the run list, saying so.
 *
 * A FOURTH STATE THAT IS NOT A TIER: `unavailable` means NO VERDICT COULD BE
 * PRODUCED for that unit. `_validate_unit` sets it on the branches whose own
 * comment reads "no verdict, not a schema violation"; `ok` stays false there to
 * fail closed, so a client keying on `ok` alone renders a refusal as a schema
 * failure. No advisory count and no Tier 3 count enters any pass/fail figure
 * anywhere in this file.
 *
 * ── `ok`, `schema_ok` AND EXACTNESS, ON A SURFACE THAT HAS ONLY ONE OF THEM ───
 *
 * `POST /api/validate/record` separates three things: the official schema's own
 * `schema_ok`, ISAAC's anchored-pattern `exactness_errors`, and `ok` as the
 * conjunction of the two. THE PER-RUN WIRE CARRIES NONE OF THAT SEPARATION.
 * `_validate_unit`'s dry-run branch returns `export_draft`'s result, and
 * `export.py` folds an exactness refusal into `draft_report` and returns
 * `official_report=None` — so on a candidate record an exactness finding and a
 * no-guessing finding arrive in one undifferentiated `{path, message}` list. Only
 * a MATERIALISED unit's errors are known to come from `validate_official`.
 *
 * So this surface does the only honest thing available to it: it names the
 * official ISAAC schema as the source ONLY where `dry_run === false`, says
 * plainly that it cannot name a source otherwise, and points at the Standalone
 * Validator, which is the surface that does report the three separately. It never
 * labels an exactness refusal a schema error, because it never labels any dry-run
 * finding a schema error at all. `CLAUDE.md` §1 makes the schema upstream-owned;
 * attributing an ISAAC gate to it is the defect `VerdictCard` already shipped once
 * ("Invalid against official ISAAC schema v1.05 — 0 errors" above
 * `schema_ok: true`), and nothing here may recreate it.
 *
 * ── SCALE: WHY NOTHING IS CHECKED ON MOUNT ───────────────────────────────────
 *
 * `docs/run-scale-measurements.md` measured the cost of a record's runs as the
 * PAYLOAD, and the run list is bounded and paged because of it. Fanning out N
 * per-run checks on mount would be the same mistake in request form: 200 POSTs a
 * scientist did not ask for, on a screen they may have opened to edit one field.
 *
 * The triggering model is therefore EXPLICIT, then BOUNDED:
 *
 *   * nothing at all until the button is pressed — the idle state says "not
 *     checked", which is deliberately not the same sentence as "no findings";
 *   * the press costs exactly THREE requests, and three is independent of run
 *     count: all three routes answer for the whole record in one response each.
 *     At 200 runs that is 3 requests, not 200 (`__tests__/validate-review.test.tsx`
 *     asserts the figure against a 200-run response, so it cannot drift silently);
 *   * per-run detail is ONE request for ONE run, only when that run's own button
 *     is pressed. A scientist who opens every one of 200 runs pays 200 — which is
 *     200 deliberate acts, not one accidental one.
 *
 * ── HONEST COUNTS ────────────────────────────────────────────────────────────
 *
 * "Not checked" and "0 findings" are different facts and read differently
 * everywhere on this surface: at section level ("no check has been run yet" vs a
 * tally), and per run ("open questions and no-guessing checks not checked yet" vs
 * "0 open questions"). No percentage, no readiness score, no completion figure.
 */

/** The state word for each of the three states. Never colour alone. */
const STATE_WORD: Record<RunFindingState, string> = {
  pass: 'Passed',
  fail: 'Failed',
  unavailable: 'No verdict',
};

const STATE_ICON = {
  pass: Check,
  fail: TriangleAlert,
  unavailable: CircleHelp,
} as const;

/**
 * The clause each state contributes to the section tally.
 *
 * `fail` reads "did not pass" and NOT "failed the official ISAAC schema", for the
 * reason set out in the header: on a dry-run unit the wire carries no
 * discriminator between an official-schema error, a no-guessing error and an
 * exactness refusal, so naming the schema would be a claim the response does not
 * support.
 */
const STATE_CLAUSE: Record<RunFindingState, string> = {
  pass: 'passed',
  fail: 'did not pass',
  unavailable: 'could not be checked',
};

/**
 * The evidence-support classes this surface reports, and what each is CALLED.
 *
 * The keys are the server's own class strings from `evidence_classify`; the
 * values are the plain-English heading for each, and nothing more. No class is
 * merged into another, no severity is attached, and the three classes NOT listed
 * (`supported`, `inferred_candidate`, `unknown`) are deliberately absent: this
 * block reports what needs a person's attention, and a supported field does not.
 *
 * `unreadable` is listed separately from `unknown` for the reason
 * `evidence_classify._classify_entry` rule 0 gives — `unknown` asserts that
 * nothing defensible is recorded, while `unreadable` asserts only that the server
 * could not read what is. Folding them would turn a read failure into a claim
 * about the science.
 */
const ATTENTION_CLASSES: { cls: EvidenceClass; heading: string }[] = [
  { cls: 'conflicting_evidence', heading: 'Conflicting evidence' },
  { cls: 'insufficient_evidence', heading: 'Insufficient evidence' },
  { cls: 'unreadable', heading: 'Evidence that could not be read' },
];

/**
 * Is this classification row about a DESCRIPTOR?
 *
 * It reads the server's OWN address namespace and nothing else. `field` on a
 * classification row is either a dotted official path or one of the namespaced
 * forms the backend documents (`assets:`, `descriptors:`, `implicit:`), so the
 * prefix is a fact the response states rather than a guess about the content.
 * Nothing about the message text, the value or the science is examined.
 */
const isDescriptor = (field: string): boolean => field.startsWith('descriptors:');

/**
 * ONE unit of the review, exactly as the server described it.
 *
 * A "unit" is an `exp.export_units()` entry: one run for a record with runs, and
 * the record itself for a record with none. Nothing in this shape is computed —
 * it is a rename of the fields `_validate_unit` returned.
 */
interface ReviewUnit {
  /** The server's `run_id`, or `null` for a record with no runs. */
  runId: string | null;
  /** The server's `record_id`, or `null` when there is no per-unit record id. */
  recordId: string | null;
  /** What to call this unit on screen. Never an interpolated `null`. */
  label: string;
  /** The server's own verdict fields, passed to `runFindingState` untouched. */
  verdict: NonNullable<ApiValidateResult['runs']>[number];
}

/**
 * The units to review, from the response and nothing else.
 *
 * A record WITH runs has `validate.runs`, one entry per unit. A record WITHOUT
 * runs has no `runs` key at all, and the top-level `ok`/`errors`/`dry_run` ARE
 * that single unit's verdict — `post_validate`'s non-fan-out branch computes
 * exactly one. So the single unit is built from those fields rather than a run
 * being invented for it: `runId` is null (there is no run, and no per-run detail
 * to offer), `recordId` is null (the singular `record_id` is not on this
 * response), and the label says what it is.
 *
 * The synthesized entry deliberately carries no `unavailable` flag, because the
 * non-fan-out branch does not send one. It emits the same fixed sentence, which
 * `runFindingState`'s `isValidationUnavailable` fallback recognises — the exact
 * case that fallback exists for.
 */
function reviewUnits(validate: ApiValidateResult): ReviewUnit[] {
  if (validate.runs && validate.runs.length > 0) {
    return validate.runs.map((verdict) => ({
      runId: verdict.run_id,
      recordId: verdict.record_id,
      label: verdict.run_label?.trim() || 'Run',
      verdict,
    }));
  }
  return [
    {
      runId: null,
      recordId: null,
      label: 'This record',
      verdict: {
        run_id: null,
        run_label: null,
        record_id: '',
        ok: validate.ok,
        errors: validate.errors,
        dry_run: validate.dry_run,
      },
    },
  ];
}

/** What has been asked of the two verdict-bearing experiment-level endpoints. */
type Review =
  | { status: 'idle' }
  | { status: 'checking' }
  | { status: 'error'; message: string }
  | { status: 'data'; validate: ApiValidateResult; warnings: ApiWarningsResponse };

/**
 * What has been asked of the evidence-support axis. It has its OWN state rather
 * than riding on {@link Review} deliberately: it decides nothing about validity,
 * so a failure to read it must not blank the verdicts, and a success must not be
 * needed before they render. Its failure is disclosed in place instead.
 */
type Attention =
  | { status: 'idle' }
  | { status: 'checking' }
  | { status: 'error' }
  | { status: 'data'; data: ApiEvidenceClassification };

/**
 * What has been asked of ONE run's own check. An ABSENT key is "not checked",
 * which is why this is a sparse map and not a per-unit field with a default.
 */
type Detail =
  | { status: 'checking' }
  | { status: 'error'; message: string }
  | { status: 'data'; data: ApiRunCheckResponse };

const IDLE_TEXT =
  'No check has been run here yet, so nothing on this record has been checked on this screen. ' +
  'That is not the same as “no findings”.';

export function ValidateReview({ experimentId }: { experimentId: string }) {
  const headingId = useId();
  const [review, setReview] = useState<Review>({ status: 'idle' });
  const [attention, setAttention] = useState<Attention>({ status: 'idle' });
  const [details, setDetails] = useState<Record<string, Detail>>({});

  const runReview = () => {
    setReview({ status: 'checking' });
    setAttention({ status: 'checking' });
    // The per-run details belong to the review that produced them. A fresh review
    // is a fresh read of the record, so keeping the old details would leave
    // findings from a previous revision under a run whose summary has moved.
    setDetails({});
    Promise.all([api.validate(experimentId), api.getWarnings(experimentId)])
      .then(([validate, warnings]) => setReview({ status: 'data', validate, warnings }))
      .catch((err: unknown) =>
        setReview({
          status: 'error',
          message:
            err instanceof Error
              ? err.message
              : 'This record could not be checked. Nothing was changed.',
        }),
      );
    api
      .getEvidenceClassification(experimentId)
      .then((data) => setAttention({ status: 'data', data }))
      // The message is fixed rather than the server's, because this block asserts
      // nothing about validity and an error string here would read as a finding.
      .catch(() => setAttention({ status: 'error' }));
  };

  const runDetail = (runId: string) => {
    setDetails((prev) => ({ ...prev, [runId]: { status: 'checking' } }));
    api
      .checkRun(experimentId, runId)
      .then((data) => setDetails((prev) => ({ ...prev, [runId]: { status: 'data', data } })))
      .catch((err: unknown) =>
        setDetails((prev) => ({
          ...prev,
          [runId]: {
            status: 'error',
            message:
              err instanceof Error ? err.message : 'This run could not be checked in detail.',
          },
        })),
      );
  };

  const units = review.status === 'data' ? reviewUnits(review.validate) : [];
  const hasRuns = review.status === 'data' && (review.validate.runs?.length ?? 0) > 0;

  return (
    <section className="validate-review card" aria-labelledby={headingId}>
      <h2 id={headingId} className="vr-title">
        Validate &amp; Review
      </h2>
      {/*
        THE SUB-LINE SAYS "EVERY RUN" ONLY WHERE THERE ARE RUNS. A record with no
        runs exports one official record and has no run list at all — every one of
        the five canonical seeds is such a record — so the unconditional wording
        described a fan-out that does not exist there. Before the check has run,
        nothing on this screen knows which shape the record is, and the honest
        third form says so rather than picking one.
      */}
      <p className="vr-sub">
        {review.status !== 'data'
          ? 'Checks this record against the same deterministic validators the export gate uses — each run separately if it has runs — and lists what was found, so you can decide what to fix. '
          : hasRuns
            ? 'Checks every run against the same deterministic validators the export gate uses, and lists what each one found, so you can decide what to fix. '
            : 'Checks this record against the same deterministic validators the export gate uses, and lists what they found, so you can decide what to fix. '}
        Read-only: nothing here is written, exported, submitted, or repaired for you.
      </p>

      <div className="vr-actions">
        <button
          type="button"
          className="btn btn-primary"
          onClick={runReview}
          disabled={review.status === 'checking'}
        >
          {review.status === 'checking'
            ? 'Checking…'
            : review.status === 'data'
              ? 'Check Again'
              : 'Validate & Review'}
        </button>
      </div>

      {/*
        THE ONE PROGRESS / SUMMARY REGION. It is rendered in every state and at the
        same position, so the node survives a re-check rather than being unmounted
        and remounted with its new text — a live region that arrives carrying its
        content is generally not announced, which would make the announcement
        present in the markup and absent in practice.
      */}
      <p className="vr-status" role="status">
        {review.status === 'idle' && IDLE_TEXT}
        {review.status === 'checking' && 'Checking every run…'}
        {review.status === 'data' && summaryLine(units, review.validate, details)}
      </p>

      {review.status === 'error' && (
        <p className="vr-error" role="alert">
          {review.message} Nothing on this record was changed.
        </p>
      )}

      {review.status === 'data' && (
        <>
          <p className="vr-note">
            {hasRuns
              ? 'Each run exports its own official ISAAC record, so each one is checked on its own. ' +
                'The record-level verdict passes only when every run passes.'
              : 'This record has no runs, so it exports one official record and is checked as one unit.'}
          </p>
          {/*
            WHAT THIS SCREEN CANNOT TELL YOU, said once, here.

            `export_draft` folds an anchored-pattern exactness refusal into the
            no-guessing draft report and returns no official report, so on a
            candidate record those findings arrive in the same undifferentiated
            list as everything else. The Standalone Validator reports the schema
            verdict, ISAAC's exactness findings and the combined verdict as three
            separate things; this per-run channel has only one of them. Saying so
            is what stops a reader taking a dry-run finding for a schema error.
          */}
          <p className="vr-note">
            Beyond the official schema, ISAAC applies one gate of its own (anchored-pattern
            exactness). On a candidate record its findings arrive in the same list as the
            rest and are not labelled apart, so nothing below names the official ISAAC schema
            as the source unless a written record was checked. To see the schema verdict,
            ISAAC&rsquo;s own findings and the combined verdict reported separately, use the
            Standalone Validator on Governance &amp; Safety.
          </p>

          <ul className="vr-list">
            {units.map((unit, i) => (
              <UnitGroup
                key={`${i}:${unit.runId ?? unit.recordId ?? 'unit'}`}
                unit={unit}
                advice={adviceFor(review.warnings, unit, i)}
                detail={unit.runId === null ? undefined : details[unit.runId]}
                onCheckDetail={unit.runId === null ? undefined : () => runDetail(unit.runId!)}
              />
            ))}
          </ul>

          <AttentionBlock attention={attention} />
        </>
      )}
    </section>
  );
}

/**
 * The advice for the unit at THIS POSITION, and only if it names the same record.
 *
 * `_fan_out_warnings_payload` builds `runs` as one entry per `exp.export_units()`
 * entry, in the same order as `/validate`'s, so position is the primary key;
 * `record_id` is then confirmed, so a re-ordered or short list shows NO advice
 * rather than another run's. Matching on `record_id` alone attaches one run's
 * advice to every entry sharing it — the guard `RunFindings` already carries, and
 * the same reasoning applies unchanged here.
 *
 * A record with no runs has no `warnings.runs` at all. The deduplicated top-level
 * union is deliberately NOT substituted for it: that union is an aggregate over
 * units, and presenting an aggregate as one unit's own advice would be a claim
 * the response does not make. A single-unit record's union happens to equal its
 * one entry, but this file must not depend on a coincidence to stay truthful.
 *
 * `undefined` THEREFORE MEANS "NOT ATTRIBUTABLE", WHICH IS NOT "NONE". Every
 * caller must keep those apart. It was got wrong once and it mattered: the counts
 * line rendered `${count(0, 'advisory note')}` on the undefined branch, so a
 * record with no runs — which is every canonical seed, each carrying one or two
 * REAL advisory warnings from `_warnings_payload` — read "0 advisory notes" while
 * the server had reported some. Refusing to attribute an aggregate is correct;
 * printing that refusal as a zero is a stronger and false claim.
 */
function adviceFor(
  warnings: ApiWarningsResponse,
  unit: ReviewUnit,
  index: number,
): NonNullable<ApiWarningsResponse['runs']>[number] | undefined {
  const entry = warnings.runs?.[index];
  if (entry === undefined || unit.recordId === null) return undefined;
  return entry.record_id === unit.recordId ? entry : undefined;
}

/**
 * The section tally. COUNTS ONLY — never a percentage, a score or a readiness
 * figure, and the detail clause states coverage rather than implying it.
 *
 * The second sentence is the one that keeps "not checked" and "clean" apart at
 * section level: `0 of 3 runs also checked in detail` says the open questions and
 * the no-guessing report have not been read for any of them, which a tally of
 * verdicts alone would leave a reader to assume either way.
 */
function summaryLine(
  units: ReviewUnit[],
  validate: ApiValidateResult,
  details: Record<string, Detail>,
): string {
  const states = units.map((unit) => runFindingState(unit.verdict));
  const tally = (state: RunFindingState) => states.filter((s) => s === state).length;
  const clauses = (['pass', 'fail', 'unavailable'] as const)
    .filter((state) => tally(state) > 0)
    .map((state) => `${tally(state)} ${STATE_CLAUSE[state]}`);

  const hasRuns = (validate.runs?.length ?? 0) > 0;
  const subject = hasRuns ? count(units.length, 'run') : '1 record';
  const head = `${subject} checked: ${clauses.join(' · ')}.`;
  if (!hasRuns) return head;

  const checkable = units.filter((unit) => unit.runId !== null);
  const checked = checkable.filter((unit) => details[unit.runId!]?.status === 'data').length;
  return `${head} ${checked} of ${checkable.length} ${
    checkable.length === 1 ? 'run' : 'runs'
  } also checked in detail.`;
}

/**
 * WHAT THIS UNIT'S NUMBERS COUNT, and what has not been counted at all.
 *
 * The undone half is stated rather than omitted. An earlier shape of this line
 * read `2 blocking findings · 1 advisory note` before any detail had been
 * fetched, which a reader takes as the whole story about a run whose open
 * questions nobody has looked at.
 *
 * EVERY CLAUSE HERE IS EITHER A COUNT OR A COVERAGE STATEMENT, NEVER A ZERO
 * STANDING IN FOR AN UNKNOWN. Two of the three ways this line can fail to know a
 * number are the reason:
 *
 *   * `adviceCount === null` — {@link adviceFor} could not attribute any advisory
 *     entry to this unit (a record with no runs has no `warnings.runs` at all; a
 *     short or re-ordered fan-out list has no entry at this position). The server
 *     may well have reported advisory warnings for the record; this line simply
 *     may not say which are this unit's. Printing `0 advisory notes` there told a
 *     scientist there were none, on every record they can currently open;
 *   * `state === 'unavailable'` — no verdict was produced at all. `_validate_unit`
 *     still returns exactly one synthetic sentinel error there ("Validation could
 *     not be completed."), which is a REFUSAL, not a finding. Counting it made the
 *     card read "1 blocking finding" immediately above "No verdict could be
 *     produced for this run — this is not a schema failure". The header's tier
 *     model already declares `unavailable` a fourth state that is not a tier;
 *     this honours that in the numbers as well as in the words.
 */
function unitCounts(
  unit: ReviewUnit,
  state: RunFindingState,
  adviceCount: number | null,
  detail: Detail | undefined,
  detailAvailable: boolean,
): string {
  const parts = [
    state === 'unavailable'
      ? 'no verdict, so nothing here is counted as a blocking finding'
      : count(unit.verdict.errors.length, 'blocking finding'),
    adviceCount === null
      ? 'advisory notes not attributable to this unit — which is not the same as none'
      : count(adviceCount, 'advisory note'),
  ];
  if (!detailAvailable) {
    parts.push('this record has no runs, so there is no per-run detail to check');
  } else if (detail === undefined) {
    parts.push('open questions and no-guessing checks not checked yet');
  } else if (detail.status === 'checking') {
    parts.push('checking this run…');
  } else if (detail.status === 'error') {
    parts.push('this run’s detailed check could not be run');
  } else {
    parts.push(count(detail.data.blockers?.length ?? 0, 'open question'));
    parts.push(count(detail.data.draft?.errors?.length ?? 0, 'no-guessing finding'));
    parts.push(count(detail.data.draft?.warnings?.length ?? 0, 'no-guessing advisory note'));
  }
  return parts.join(' · ');
}

/**
 * The VISIBLE words on one run's detail button, in one place.
 *
 * It exists so the button's `aria-label` can be composed FROM this string rather
 * than restating it. WCAG 2.5.3 requires the visible label to appear in the
 * accessible name; deriving one from the other makes that structural instead of
 * something a future edit has to remember.
 */
function detailButtonLabel(detail: Detail | undefined): string {
  if (detail?.status === 'checking') return 'Checking…';
  return detail?.status === 'data' ? 'Check This Run Again' : 'Check This Run In Detail';
}

function UnitGroup({
  unit,
  advice,
  detail,
  onCheckDetail,
}: {
  unit: ReviewUnit;
  advice: NonNullable<ApiWarningsResponse['runs']>[number] | undefined;
  detail: Detail | undefined;
  /** Absent when the unit has no run id, so there is no per-run route to call. */
  onCheckDetail?: () => void;
}) {
  const state = runFindingState(unit.verdict);
  const Icon = STATE_ICON[state];
  const errors = unit.verdict.errors;
  // `undefined` advice is NOT an empty advice list — see {@link adviceFor}. The
  // rendered list is empty either way (there is nothing attributable to render),
  // but the COUNT must stay `null` so the counts line states coverage instead of
  // asserting a zero the response does not support.
  const adviceWarnings = advice?.warnings ?? [];
  const adviceCount = advice === undefined ? null : advice.warnings.length;

  return (
    <li className="vr-unit" data-state={state} data-run-id={unit.runId ?? undefined}>
      {/* A real heading, so a screen reader can jump run to run. `h3` because the
          section's own heading is `h2` and the findings blocks below are `h4` —
          no level is skipped anywhere in this subtree. */}
      <h3 className="vr-unit-head">
        {/* Icon + word: the state is never carried by colour alone. */}
        <span className={`vr-state vr-state-${state}`}>
          <Icon size={14} strokeWidth={2.2} aria-hidden="true" />
          {STATE_WORD[state]}
        </span>
        <span className="vr-unit-label">{unit.label}</span>
      </h3>

      {(unit.runId !== null || unit.recordId) && (
        <p className="vr-unit-ids mono">
          {unit.runId ? <>run {unit.runId}</> : null}
          {unit.runId && unit.recordId ? ' · ' : null}
          {unit.recordId ? <>record {unit.recordId}</> : null}
        </p>
      )}

      {/* WHICH DOCUMENT WAS CHECKED, and NOT CLAIMED AT ALL for a no-verdict unit.
          `_validate_unit`'s materialised-unreadable branch returns `dry_run: false`
          to say NO DRY RUN HAPPENED — it is returned precisely because the written
          record could not be read — so rendering this line there would turn a
          refusal into a claim that the unopened document was checked. */}
      {state !== 'unavailable' && (
        <p className="vr-unit-subject">
          {unit.verdict.dry_run
            ? 'Checked an in-memory candidate record — nothing was written.'
            : 'Checked the written official record.'}
        </p>
      )}

      <p className="vr-unit-counts">
        {unitCounts(unit, state, adviceCount, detail, onCheckDetail !== undefined)}
      </p>

      {state === 'unavailable' && (
        <p className="vr-caption">
          No verdict could be produced for this run — this is not a schema failure.
          {errors.length > 0 ? ' What the check reported:' : ''}
        </p>
      )}

      {state !== 'pass' && errors.length > 0 && (
        <>
          {/* WHOSE FINDINGS THESE ARE. Two different claims, and only one of them
              is supported on a dry run: `_validate_unit` returns `export_draft`'s
              errors there, which may be the no-guessing report's — including an
              anchored-pattern exactness refusal, which `export.py` folds into it —
              with no discriminator on the wire. Naming the official schema there
              would attribute an ISAAC gate to an upstream document. */}
          {state === 'fail' && (
            <h4 className="vr-group-title">
              {unit.verdict.dry_run
                ? `Blocks export · ${errors.length} finding${errors.length === 1 ? '' : 's'} on this candidate record — source not named`
                : `Blocks export · ${errors.length} official ISAAC schema error${errors.length === 1 ? '' : 's'} on the written record`}
            </h4>
          )}
          <ul className="vr-errors mono">
            {/* `err.path` is NOT unique — several missing required properties all
                report at `$` — so the index is part of the key. The message is
                verbatim: paraphrasing would change what the validator said. */}
            {errors.map((err, j) => (
              <li key={`${j}:${err.path}`}>
                <span className="vr-error-path">{err.path}</span> — {err.message}
              </li>
            ))}
          </ul>
        </>
      )}

      {adviceWarnings.length > 0 && (
        <div className="vr-advisory">
          <h4 className="vr-advisory-title">
            Advisory · non-gating — {adviceWarnings.length}{' '}
            {adviceWarnings.length === 1 ? 'note' : 'notes'}. These never change this
            run&rsquo;s verdict and never block export.
          </h4>
          <ul className="vr-advisory-list">
            {adviceWarnings.map((warning, j) => (
              <li key={`${j}:${warning.code}`}>
                <span className="mono">[{warning.code}]</span> {warning.where} —{' '}
                {warning.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {onCheckDetail !== undefined && (
        <div className="vr-actions">
          {/*
            THE ACCESSIBLE NAME NAMES THE RUN AND CONTAINS THE VISIBLE WORDS, and
            it is BUILT FROM the visible label rather than written twice, so the
            two cannot drift apart on a later edit. Fifty runs each offering a
            button called "Check This Run In Detail" is fifty identically named
            controls in a screen reader's list, which is why the run is appended;
            WCAG 2.5.3 (label in name) is why the visible string is the prefix and
            not a paraphrase of it, so speech input still reaches the control by
            saying what is printed on it.

            IT ALSO HAS TO STAY TRUE IN ALL THREE STATES. A fixed
            `Check {label} in detail` went stale the moment the button re-labelled
            itself "Check This Run Again", leaving the announced name describing a
            press that had already happened.
          */}
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onCheckDetail}
            disabled={detail?.status === 'checking'}
            aria-label={`${detailButtonLabel(detail)} — ${unit.label}`}
          >
            {detailButtonLabel(detail)}
          </button>
        </div>
      )}

      {detail?.status === 'error' && (
        <p className="vr-error" role="alert">
          {detail.message} Nothing on this run was changed.
        </p>
      )}

      {detail?.status === 'data' && <UnitDetail unit={unit} data={detail.data} />}
    </li>
  );
}

/**
 * The blocker kinds present, in the SERVER'S OWN WORDS, as a count per kind.
 *
 * This is the "unsupported descriptor" distinction, and it is a group-by on a
 * field the response already carries (`kind`), not a classification of anything.
 * An entry with no `kind` is counted under "kind not recorded" rather than being
 * dropped or assigned one — `_blocker_message`'s last branch exists for exactly
 * that entry, so it is a shape the backend acknowledges.
 *
 * Returns `null` when there is nothing to say, so the caller renders no line at
 * all rather than an empty one.
 */
function blockerKindLine(blockers: ApiRunCheckFinding[]): string | null {
  if (blockers.length === 0) return null;
  const tally = new Map<string, number>();
  for (const blocker of blockers) {
    const raw = typeof blocker === 'object' && blocker !== null ? blocker.kind : undefined;
    const key = typeof raw === 'string' && raw.trim() !== '' ? raw.trim() : 'kind not recorded';
    tally.set(key, (tally.get(key) ?? 0) + 1);
  }
  return [...tally.entries()]
    .sort((a, b) => (b[1] - a[1] !== 0 ? b[1] - a[1] : a[0].localeCompare(b[0])))
    .map(([kind, n]) => `${n} ${kind}`)
    .join(' · ');
}

/**
 * The two things the fan-out does not carry, for ONE run.
 *
 * IT DELIBERATELY DOES NOT RESTATE THE OFFICIAL VERDICT. `POST …/runs/{id}/check`
 * computes `official` from the same `_validate_unit` the fan-out above used, so
 * rendering it again would put two verdicts in one group with nothing saying
 * which is current. What it does instead is compare them and SAY when they
 * differ — which is not a derived verdict but the observation that two answers
 * from one function, taken at two moments, disagree.
 *
 * IT REPORTS THE DISAGREEMENT AND NAMES NO CAUSE, because it cannot know one.
 * The copy used to read "so this run changed after the summary was taken", which
 * is only one of several ways the two reads can differ: an edit to the RECORD
 * rather than to the run moves the verdict while the sentence blames the run, and
 * a transient artifact read failure flips a unit to `unavailable` with nothing
 * having changed at all. Stating the observation is supported; stating the cause
 * is not, and the reader is the one who can find out which it was.
 */
function UnitDetail({ unit, data }: { unit: ReviewUnit; data: ApiRunCheckResponse }) {
  const blockers = data.blockers ?? [];
  const draftErrors = data.draft?.errors ?? [];
  const draftWarnings = data.draft?.warnings ?? [];
  const kindLine = blockerKindLine(blockers);
  const disagrees =
    (data.official?.ok ?? unit.verdict.ok) !== unit.verdict.ok ||
    (data.official?.unavailable === true) !== (unit.verdict.unavailable === true);

  return (
    <div className="vr-detail">
      <p className="vr-detail-scope">
        Read-only detail for run version {data.checked_run_version}. Nothing was written,
        submitted or exported.
      </p>

      {disagrees && (
        <p className="vr-detail-disagree">
          This run&rsquo;s own check and the summary above do not agree. This screen cannot
          say why: the run or the record may have changed between the two reads, or one of
          the two checks may not have been able to produce a verdict. Run Validate &amp;
          Review again for a current summary.
        </p>
      )}

      <FindingList titleAs="h4" title="Blocks export · open questions" findings={blockers} />
      {kindLine && (
        <p className="vr-kinds">
          By the kind the server recorded for each: {kindLine}.
          {/* The gloss is written only when there IS one, so the sentence never
              explains a category this run does not have. */}
          {kindLine.includes('descriptor') && (
            <>
              {' '}
              A <span className="mono">descriptor</span> here is a descriptor this record
              carries with nothing behind it yet.
            </>
          )}
        </p>
      )}
      <FindingList
        titleAs="h4"
        title="Blocks export · no-guessing checks"
        findings={draftErrors}
      />
      {/* The no-guessing validator's OWN advisory channel (`report.warn`), which
          `DraftReport.ok` does not read — so it cannot gate anything, and the
          heading says so rather than leaving it beside the two above. */}
      <FindingList
        titleAs="h4"
        title="Advisory · non-gating · no-guessing notes"
        findings={draftWarnings}
      />

      {blockers.length === 0 && draftErrors.length === 0 && draftWarnings.length === 0 && (
        <p className="vr-detail-clean">
          This run has no open questions and the no-guessing checks reported nothing.
        </p>
      )}
    </div>
  );
}

/**
 * TIER 3 — the evidence-support axis: conflicts, gaps, and evidence that could
 * not be read. RECORD-LEVEL, and NEITHER BLOCKING NOR ADVISORY.
 *
 * `get_evidence_classification` says of itself that it "deliberately carries NO
 * validity/completion/advisory verdict", so this block must not be read as
 * either. It therefore borrows nothing from the two tiers above: not the words
 * "blocks export", not the advisory treatment, and no count from here reaches any
 * pass/fail figure. What it says instead is what the route says — these are
 * facts about evidence support, and a person decides what they mean.
 *
 * IT IS OUTSIDE THE RUN LIST ON PURPOSE. The route classifies `exp.draft`, which
 * is the record-level draft; there is no per-run classification endpoint, so
 * attaching a conflict to a run would be an attribution the API never made.
 *
 * A FAILED READ IS SHOWN AS A FAILED READ. Nothing above it depends on this
 * request, so a failure here leaves every verdict on screen intact and says only
 * that this one axis is unknown — which is what "not checked" means everywhere
 * else on this surface too.
 */
function AttentionBlock({ attention }: { attention: Attention }) {
  if (attention.status === 'idle') return null;

  if (attention.status === 'checking') {
    return (
      <div className="vr-attention">
        <h3 className="vr-attention-title">Evidence support · no verdict either way</h3>
        <p className="vr-attention-note">Reading the evidence-support review…</p>
      </div>
    );
  }

  if (attention.status === 'error') {
    return (
      <div className="vr-attention">
        <h3 className="vr-attention-title">Evidence support · no verdict either way</h3>
        <p className="vr-attention-note">
          The evidence-support review could not be read, so conflicts and gaps are not
          checked here — which is not the same as there being none. The run results above
          are unaffected: they come from different endpoints and did not depend on this one.
        </p>
      </div>
    );
  }

  const rows = attention.data.field_results;
  const groups = ATTENTION_CLASSES.map(({ cls, heading }) => ({
    cls,
    heading,
    entries: rows.filter((row) => row.classification === cls),
  }));
  const total = groups.reduce((n, group) => n + group.entries.length, 0);
  const descriptors = groups.reduce(
    (n, group) => n + group.entries.filter((row) => isDescriptor(row.field)).length,
    0,
  );

  return (
    <div className="vr-attention">
      <h3 className="vr-attention-title">Evidence support · no verdict either way</h3>
      {/*
        THE SCOPE SENTENCE SAYS WHAT IS ACTUALLY CLASSIFIED, and "the whole record"
        was not it. `get_evidence_classification` classifies `exp.draft`, which on
        a record with runs is the EXPERIMENT-LEVEL half only: it carries no
        measurement, no links and no run content, and it is never exported on its
        own — each run's own document is. Calling that "the whole record's review"
        claimed coverage of material this axis never read.
      */}
      <p className="vr-attention-note">
        This reviews a different document, not one run&rsquo;s: the server classifies the
        record-level draft, which on a record with runs holds the experiment-level fields
        only — no measurement, no links, no run content — and is never exported on its own.
        There is no per-run breakdown, so none is shown. It decides nothing about validity:
        it neither blocks export nor is it one of the advisory notes above. These are yours
        to judge.
      </p>
      <p className="vr-attention-counts">
        {total === 0
          ? 'Nothing on this axis needs attention: 0 conflicts, 0 gaps, 0 unreadable entries.'
          : `${count(total, 'field')} to look at${
              descriptors > 0
                ? `, ${descriptors} of them ${descriptors === 1 ? 'a descriptor' : 'descriptors'}`
                : ''
            }.`}
      </p>

      {groups
        .filter((group) => group.entries.length > 0)
        .map((group) => (
          <div className="vr-attention-group" key={group.cls}>
            <h4 className="vr-attention-group-title">
              {group.heading} · {group.entries.length}
            </h4>
            <ul className="vr-attention-list">
              {group.entries.map((row, j) => (
                <li key={`${j}:${row.field}`}>
                  <span className="mono vr-attention-field">{row.field}</span>
                  {isDescriptor(row.field) && (
                    <span className="vr-attention-tag">descriptor</span>
                  )}{' '}
                  — {row.explanation}
                </li>
              ))}
            </ul>
          </div>
        ))}
    </div>
  );
}
