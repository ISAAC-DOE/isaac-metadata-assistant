import './run-findings.css';
import { useId } from 'react';
import { Check, TriangleAlert, CircleHelp } from './icons';
import { count, isValidationUnavailable } from '../lib/assistantPaths';
import {
  officialCheckedDocument,
  officialDocumentSentence,
  officialFindingSource,
  officialFindingsCaption,
} from '../lib/officialAttribution';
import type { ApiValidateResult, ApiWarningsResponse } from '../lib/types';

/**
 * Validate & Review, addressed BY RUN — the per-run half of what
 * `POST /api/experiments/{id}/validate` has always returned for a record whose
 * runs each export their own official record.
 *
 * WHY THIS EXISTS. The route fans out (`routes.py::_fan_out_official_verdict`)
 * and `runs[]` carries each unit's own verdict, its own errors and its own
 * `dry_run`. The frontend read NONE of it: measured on `d17a827`,
 * `rg --text -n 'validate\.runs' apps/web/src` returned only the declaration in
 * `lib/types.ts`. The screen rendered the flat `errors` list, which is
 * deliberately only the FIRST FAILING unit's errors — so a reader of a five-run
 * record saw one run's schema errors with nothing saying which run they belonged
 * to, and no way to reach the other four.
 *
 * THREE THINGS THIS COMPONENT MUST NOT DO, each because the same mistake has
 * already shipped in this repository:
 *
 *  1. IT COMPUTES NO VERDICT. Every pass/fail here is the server's own `ok` for
 *     that unit, from the one `validate_official` over the one vendored schema.
 *     `_assistant_validate_dryrun` once carried an independent copy of the
 *     fan-out logic and DISAGREED with `/validate` on the same experiment
 *     (measured on `c467dc7`: `/validate -> ok: true` while the assistant thunk
 *     returned `ok: false, "'descriptors' is a required property"`). A second
 *     validator in the client would be the same defect in a third place. The
 *     reserved PASS/FAIL verdict presentation stays where it is — `VerdictCard`
 *     — and this section never borrows its classes or its words.
 *
 *  2. `unavailable` IS NOT `ok: false`. `_validate_unit` returns
 *     `unavailable: true` to say NO VERDICT COULD BE PRODUCED — the written
 *     record could not be read, or the dry run raised — as distinct from the
 *     schema rejecting it. `ok` stays false either way, so a client keying on
 *     `ok` alone renders a non-verdict as a schema failure, which is exactly the
 *     defect the flag was added to fix. The MACHINE-READABLE FLAG is what is
 *     read, as `RunCard` already reads it (`data.official?.unavailable === true`);
 *     the shared helper `isValidationUnavailable` — the TypeScript twin of
 *     `assistant_paths.is_validation_unavailable`, never a local
 *     re-implementation — is retained only as a fallback for a response that
 *     predates the flag.
 *
 *  3. AN ADVISORY WARNING NEVER TOUCHES A VERDICT. `_fan_out_warnings_payload`
 *     hardcodes `advisory: true, gating: false`. Warnings render in their own
 *     block, labelled non-gating, and no count of them enters any pass/fail
 *     figure here. Note the deliberate asymmetry we honour: `/validate` returns
 *     the first failing unit's errors (a verdict must not be aggregated) while
 *     `/warnings` returns the deduplicated UNION (advice is safe to aggregate).
 *     Only each run's OWN warnings are shown here, so the union is never
 *     presented as if it were a verdict.
 *
 * There are also no invented figures: the summary is a count of runs in each
 * state and nothing else. No percentage, no readiness score, no "N% complete".
 */

type RunVerdict = NonNullable<ApiValidateResult['runs']>[number];
type RunWarnings = NonNullable<ApiWarningsResponse['runs']>[number];

/** The three states a run's entry can be in. `unavailable` is not a failure. */
export type RunFindingState = 'pass' | 'fail' | 'unavailable';

/**
 * The state of one run's entry, from the server's own fields only.
 *
 * Order matters. `ok` decides a pass, so nothing here can turn a server PASS
 * into anything else. A non-`ok` entry is a NO-VERDICT when the server SAYS so,
 * and only otherwise a schema failure.
 *
 * THE FLAG IS READ FIRST, AND THE STRING MATCH IS ONLY A FALLBACK. `unavailable`
 * is the field `_validate_unit` added precisely because the fixed English
 * sentence in `errors[0].message` was the only signal a client had; keying on
 * that sentence again would re-create the coupling the flag exists to remove —
 * one comma in that message and a refusal renders as a schema failure. The
 * helper stays for a response that carries the sentence but not the flag, so
 * neither signal alone is load-bearing.
 */
export function runFindingState(run: RunVerdict): RunFindingState {
  if (run.ok) return 'pass';
  return run.unavailable === true || isValidationUnavailable(run.errors)
    ? 'unavailable'
    : 'fail';
}

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
 * How many run findings are DRAWN. See the long note in the component for why the
 * bound is ordered by state rather than by position, and for the measurement that
 * made it necessary (22,267 DOM nodes at 1,000 runs, essentially all of it this list).
 *
 * 50 matches `serialize.PENDING_WINDOW` and `runPaging.RUNS_PAGE_SIZE` — the number
 * this product already means by "a page of runs" — rather than inventing a third.
 */
export const RUN_FINDINGS_WINDOW = 50;

/**
 * What each state's clause says in the count line. Never a percentage.
 *
 * `fail` deliberately reads "did not pass" and NOT "failed the official ISAAC
 * schema", which is what this file said first and which would have been FALSE for
 * a whole class of entry. `_validate_unit`'s dry-run branch returns
 * `export_draft(...)`'s `ok`, and when the export never reached the official
 * validator (`official_report is None`) it returns the NO-GUESSING DRAFT report's
 * errors instead. Both arrive as the same `{path, message}` shape.
 *
 * ~~"so the wire carries no discriminator"~~ — IT DOES NOW
 * (`official_validator_ran`), and this clause STILL reads "did not pass". That is
 * deliberate, not an oversight: a COUNT LINE aggregates several runs, whose sources
 * may differ from one another, so no single source may be named in it. The source is
 * named per run, beside that run's own findings, by `officialFindingsCaption`.
 */
const STATE_CLAUSE: Record<RunFindingState, string> = {
  pass: 'passed',
  fail: 'did not pass',
  unavailable: 'could not be checked',
};

/**
 * A run's display name. `run_label` is `string | null` in the contract, so the
 * fallback is the neutral noun the fan-out export report already uses — never an
 * interpolated `null` (the defect `__tests__/fan-out-null-render.test.tsx`
 * exists for) and never an invented label.
 */
function labelFor(run: RunVerdict): string {
  return run.run_label?.trim() || 'Run';
}

export function RunFindings({
  runs,
  warningRuns,
}: {
  runs: RunVerdict[];
  /** `warnings.runs` from the same bundle. Absent is a valid state: no advice shown. */
  warningRuns?: RunWarnings[];
}) {
  // Named so the section is exposed as a region a screen reader can navigate to;
  // an unnamed <section> is not. Hooks run before the early return below.
  const headingId = useId();
  if (runs.length === 0) return null;

  const states = runs.map(runFindingState);
  const tally = (state: RunFindingState) => states.filter((s) => s === state).length;
  const clauses = (['pass', 'fail', 'unavailable'] as const)
    .filter((state) => tally(state) > 0)
    .map((state) => `${tally(state)} ${STATE_CLAUSE[state]}`);

  /*
   * ── THE LIST IS BOUNDED, AND THE BOUND IS ORDERED BY STATE. ─────────────────
   *
   * MEASURED, not anticipated: at 1,000 runs this screen settled at **22,267 DOM
   * nodes**, of which `run-finding` and its twelve sibling classes were 1,000 each
   * and `mono` was 4,002 — i.e. essentially all of it. The record screen beside it
   * was 1,186. That is the SAME defect `docs/run-scale-measurements.md` §1 records
   * and fixed on the record screen's "Fields Need Your Confirmation" banner; the fix
   * never reached this screen, and here it is LARGER than the 16,134 §1 calls "THE
   * DEFECT". `docs/evidence/scale-envelope-2026-08-27.md` has the attribution.
   *
   * WHY NOT "THE FIRST 50", WHICH IS WHAT THE BANNER DOES. The banner's list is
   * homogeneous — every entry is an open question, so the first ten are a fair
   * sample. THESE ENTRIES ARE NOT INTERCHANGEABLE: this list's whole purpose is to
   * say WHICH runs did not pass, and a record with 40 passing runs before its first
   * failure would have shown a scientist fifty green rows and hidden every failure
   * behind a bound. Truncating by position would have been a silent truncation of
   * blockers wearing a disclosure.
   *
   * So when the bound engages, the entries a scientist needs come first: `fail`,
   * then `unavailable`, then `pass`. The sort is STABLE, so within a state the
   * server's order is untouched.
   *
   * IT ENGAGES ONLY ABOVE THE BOUND. At or below `RUN_FINDINGS_WINDOW` the rendered
   * order is exactly the server's, unchanged — so no existing record's screen is
   * reordered by this, and the change is invisible until it is needed.
   *
   * THE ORIGINAL INDEX TRAVELS WITH EACH ENTRY. `adviceFor(run, i)` is POSITIONAL
   * into `warningRuns` and its comment explains at length why (both lists come from
   * `exp.export_units()` in the same order). Sorting the runs while passing the loop
   * index would have handed run 900's advisory to run 3 — a wrong attribution of the
   * exact kind that comment exists to prevent — so `i` below is the ORIGINAL index,
   * never the position in the drawn list. The React key uses it too, so keys stay
   * stable and unique across a reorder.
   *
   * NOTHING IS HIDDEN SILENTLY: `clauses` above is computed over the FULL array and
   * is unchanged, and the withheld entries are named by state under the list.
   */
  const bounded = runs.length > RUN_FINDINGS_WINDOW;
  const order: Record<RunFindingState, number> = { fail: 0, unavailable: 1, pass: 2 };
  const entries = runs.map((run, i) => ({ run, i, state: states[i] }));
  const ordered = bounded
    ? [...entries].sort((a, b) => order[a.state] - order[b.state])
    : entries;
  const drawn = bounded ? ordered.slice(0, RUN_FINDINGS_WINDOW) : ordered;
  const withheld = bounded ? ordered.slice(RUN_FINDINGS_WINDOW) : [];
  const withheldClauses = (['fail', 'unavailable', 'pass'] as const)
    .map((state) => [state, withheld.filter((e) => e.state === state).length] as const)
    .filter(([, n]) => n > 0)
    .map(([state, n]) => `${n} ${STATE_CLAUSE[state]}`);

  /*
   * Advice for the run at THIS POSITION, and only if it names the same record.
   *
   * Both lists come from `exp.export_units()` in the same order, so position is
   * the primary key; `record_id` is then checked as well, so a re-ordered or
   * short `warnings.runs` shows NO advice rather than another run's. A `find` on
   * `record_id` alone attached the same advisory block to every entry sharing a
   * `record_id` — including two runs that both carry `''`. The API does not
   * currently produce that shape (`workspace.py` drops empty/duplicate run ids on
   * load and `add_run` refuses duplicates), so this is a guard against a wrong
   * attribution, not a fix for a live one.
   */
  const adviceFor = (run: RunVerdict, i: number): RunWarnings | undefined => {
    const entry = warningRuns?.[i];
    return entry && entry.record_id === run.record_id ? entry : undefined;
  };

  return (
    <section className="run-findings card" aria-labelledby={headingId}>
      <h2 id={headingId} className="run-findings-title">
        Findings by Run
      </h2>
      {/* The counts, and only the counts. `role="status"` because this section is
          re-rendered by Re-Validate and by the live-sync refetch, and the figures
          are what changed. */}
      <p className="run-findings-summary" role="status">
        {count(runs.length, 'run')}: {clauses.join(' · ')}.
      </p>
      <p className="run-findings-note">
        Each run exports its own official ISAAC record, so each one is checked on its own. The
        record-level verdict passes only when every run passes.
      </p>

      <ul className="run-findings-list">
        {drawn.map(({ run, i, state }) => {
          const Icon = STATE_ICON[state];
          const label = labelFor(run);
          const advice = adviceFor(run, i);
          /* The two questions, per run, asked once each. WHO produced the findings
             (`official_validator_ran`, read only inside the shared module) and WHICH
             document was read (`dry_run`). This file previously derived both from
             `dry_run` and so could not name the real source in either direction. */
          const source = officialFindingSource(run);
          const documentSentence = officialDocumentSentence(officialCheckedDocument(run));
          return (
            <li className="run-finding" key={`${i}:${run.record_id}`} data-state={state}>
              <div className="run-finding-head">
                {/* Icon + word: the state is never carried by colour alone. */}
                <span className={`run-finding-state run-finding-state-${state}`}>
                  <Icon size={14} strokeWidth={2.2} aria-hidden="true" />
                  {STATE_WORD[state]}
                </span>
                <span className="run-finding-label">{label}</span>
              </div>

              {/* The identifiers, so a finding is addressable. `run_id` is
                  nullable in the contract and is simply omitted when absent;
                  `record_id` is not. */}
              <p className="run-finding-ids mono">
                {run.run_id ? <>run {run.run_id} · </> : null}record {run.record_id}
              </p>

              {/* WHICH DOCUMENT was checked, per unit — the same distinction the
                  route makes, and a DIFFERENT question from who produced the
                  findings. `dry_run: false` is the strong claim that a WRITTEN record
                  was checked, so it is only made when the server makes it.

                  AND IT IS NOT MADE AT ALL FOR A NO-VERDICT RUN. `_validate_unit`'s
                  materialised-unreadable branch returns `dry_run: false` to say NO
                  DRY RUN HAPPENED (its own comment), not that the written record was
                  checked — it is returned exactly because that record could NOT be
                  read. Rendering this line there turned the server's refusal into an
                  affirmative claim that the very document it failed to open had been
                  checked, contradicted one line later by the caption.

                  The guard now lives in `officialCheckedDocument`, which returns
                  `null` on that branch, rather than in this component's `state`
                  check — because the same branch was got wrong independently in
                  `RunCard` and in `evidenceGraph`, which is what a per-component
                  guard buys you. */}
              {documentSentence !== null && (
                <p className="run-finding-subject">{documentSentence}</p>
              )}

              {state === 'unavailable' && (
                <p className="run-finding-caption">
                  No verdict could be produced for this run — this is not a schema failure.
                  {/* The lead-in is only written when there is something to lead into. */}
                  {run.errors.length > 0 ? ' What the check reported:' : ''}
                </p>
              )}
              {/* WHOSE FINDINGS THESE ARE — now answered by the server rather than
                  guessed from `dry_run`.

                  M1, KEPT BECAUSE THE FIX IT ASKED FOR IS THE ONE THAT SHIPPED: the
                  old caption "named two candidate sources and there are three", so a
                  reader told the source was "the no-guessing checks or the official
                  ISAAC schema" would conclude by elimination that an unfamiliar
                  finding came from the schema — the attribution `CLAUDE.md` §12
                  forbids, reached by omission instead of by assertion. `export.py`
                  runs `check_exactness` between the no-guessing report and
                  `validate_official` and FOLDS a refusal into `draft_report`.

                  `officialFindingsCaption` now answers it from
                  `official_validator_ran`: where the official schema DID produce the
                  findings it says so, and where it did not it names ISAAC's export
                  gate and declines to say which of ISAAC's two gates refused —
                  because the wire still cannot separate those two from each other,
                  and claiming one would be the same defect one level finer.

                  Both captions end in a colon, so both are guarded on there being
                  something after it. `{ok: false, errors: []}` is not reachable today
                  — `export_draft` returns `official_report=None` only when `not
                  draft_report.ok`, and `OfficialReport.ok` is `not self.errors` — so
                  this is defensive, not a live fix. */}
              {state === 'fail' && run.errors.length > 0 && (
                <p className="run-finding-caption">{officialFindingsCaption(source)}</p>
              )}
              {state !== 'pass' && run.errors.length > 0 && (
                <ul className="run-finding-errors mono">
                  {/* `err.path` is NOT unique — several missing required
                      properties all report at `$` — so the index is part of the
                      key, as in VerdictCard. The message is rendered verbatim:
                      paraphrasing a schema error would change what the validator
                      said. */}
                  {run.errors.map((err, j) => (
                    <li key={`${j}:${err.path}`}>
                      <span className="run-finding-error-path">{err.path}</span> — {err.message}
                    </li>
                  ))}
                </ul>
              )}

              {advice && advice.warnings.length > 0 && (
                <div className="run-finding-advisory">
                  <p className="run-finding-advisory-caption">
                    Advisory · non-gating — this never changes this run&rsquo;s verdict and never
                    blocks export.
                  </p>
                  <ul className="run-finding-advisory-list">
                    {advice.warnings.map((warning, j) => (
                      <li key={`${j}:${warning.code}`}>
                        <span className="mono">[{warning.code}]</span> {warning.where} —{' '}
                        {warning.message}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {/*
        WHAT WAS NOT DRAWN, NAMED BY STATE — never a bare "and N more".
        `docs/run-scale-measurements.md` §2 is explicit that "a truncated list that read
        as complete would be worse than a slow one", and a count alone would leave a
        scientist unable to tell whether the 950 rows they cannot see contain a failure.
        The clauses reuse `STATE_CLAUSE`, so this sentence and the count line above
        cannot drift apart into two vocabularies for the same three states.

        `role="status"`, matching the count line it qualifies: both are re-rendered by
        Re-Validate and by the live-sync refetch, and both are figures that changed.
      */}
      {withheld.length > 0 && (
        <p className="run-findings-withheld" role="status">
          Showing {drawn.length} of {runs.length} runs, the ones needing attention first.{' '}
          {withheldClauses.join(' · ')} {withheld.length === 1 ? 'is' : 'are'} not listed.
        </p>
      )}
    </section>
  );
}
