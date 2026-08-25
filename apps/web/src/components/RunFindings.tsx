import './run-findings.css';
import { useId } from 'react';
import { Check, TriangleAlert, CircleHelp } from './icons';
import { count, isValidationUnavailable } from '../lib/assistantPaths';
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
 * What each state's clause says in the count line. Never a percentage.
 *
 * `fail` deliberately reads "did not pass" and NOT "failed the official ISAAC
 * schema", which is what this file said first and which would have been FALSE for
 * a whole class of entry. `_validate_unit`'s dry-run branch returns
 * `export_draft(...)`'s `ok`, and when the export never reached the official
 * validator (`official_report is None`) it returns the NO-GUESSING DRAFT report's
 * errors instead. Both arrive as the same `{path, message}` shape, so the wire
 * carries no discriminator: naming the official schema as the source would be a
 * claim the response does not support. Only a MATERIALISED unit's errors are
 * known to come from `validate_official`, and only there is that source named.
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
        {runs.map((run, i) => {
          const state = states[i];
          const Icon = STATE_ICON[state];
          const label = labelFor(run);
          const advice = adviceFor(run, i);
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
                  route makes. `dry_run: false` is the strong claim that a WRITTEN
                  record was checked, so it is only made when the server makes it.

                  AND IT IS NOT MADE AT ALL FOR A NO-VERDICT RUN. `dry_run` does not
                  mean the same thing on an `unavailable` entry: `_validate_unit`'s
                  materialised-unreadable branch returns `dry_run: false` to say NO
                  DRY RUN HAPPENED (its own comment), not that the written record was
                  checked — it is returned exactly because that record could NOT be
                  read. Rendering this line there turned the server's refusal into an
                  affirmative claim that the very document it failed to open had been
                  checked, contradicted one line later by the caption. Nothing was
                  checked on either unavailable branch, so nothing is claimed: the
                  caption below is the whole statement. */}
              {state !== 'unavailable' && (
                <p className="run-finding-subject">
                  {run.dry_run
                    ? 'Checked an in-memory candidate record — nothing was written.'
                    : 'Checked the written official record.'}
                </p>
              )}

              {state === 'unavailable' && (
                <p className="run-finding-caption">
                  No verdict could be produced for this run — this is not a schema failure.
                  {/* The lead-in is only written when there is something to lead into. */}
                  {run.errors.length > 0 ? ' What the check reported:' : ''}
                </p>
              )}
              {/* WHOSE FINDINGS THESE ARE, and the two cases are not the same
                  claim. A materialised unit is validated by `validate_official`,
                  so naming the official schema there is exact. A dry-run unit's
                  errors come from `export_draft`, which returns the NO-GUESSING
                  DRAFT report's errors when the export never reached the official
                  validator — same `{path, message}` shape, no discriminator on the
                  wire. So the dry-run caption names neither validator rather than
                  claiming the wrong one.

                  M1 — IT NAMED TWO CANDIDATE SOURCES AND THERE ARE THREE, which
                  made a list that reads as exhaustive silently exclude the one
                  ISAAC owns. `export.py` runs `check_exactness` on the assembled
                  record between the no-guessing report and `validate_official`
                  (`:339`) and FOLDS a refusal into `draft_report` (`:339-343`), so
                  an anchored-pattern exactness finding arrives in this same
                  undifferentiated list. A reader told the source was "the
                  no-guessing checks or the official ISAAC schema" would conclude
                  by elimination that an unfamiliar finding came from the schema —
                  the exact attribution `CLAUDE.md` §12 forbids, reached by
                  omission instead of by assertion.

                  `ValidateReview` already had both halves and this file had only
                  one: its heading applies the same `dry_run` rule (`:648-651`),
                  and a standing note above the list enumerates all THREE sources
                  (`:412-420`, "Beyond the official schema, ISAAC applies one gate
                  of its own (anchored-pattern exactness)"). This component renders
                  without that note, so the third source has to be named in the
                  caption itself or it is named nowhere on the surface.

                  Both captions end in a colon, so both are guarded on there being
                  something after it. `{ok: false, errors: []}` is not reachable
                  today — `export_draft` returns `official_report=None` only when
                  `not draft_report.ok`, and `OfficialReport.ok` is `not
                  self.errors` — so this is defensive, not a live fix. */}
              {state === 'fail' && run.errors.length > 0 && (
                <p className="run-finding-caption">
                  {run.dry_run
                    ? 'Findings reported for this run’s candidate record. This check does not record which findings came from the no-guessing checks, which from ISAAC’s own anchored-pattern exactness gate, and which from the official ISAAC schema, so none is claimed:'
                    : 'Official ISAAC schema errors reported for this run’s written record:'}
                </p>
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
    </section>
  );
}
