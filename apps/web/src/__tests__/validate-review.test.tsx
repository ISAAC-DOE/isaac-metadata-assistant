import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor, within } from '@testing-library/react';
import { ValidateReview } from '../components/ValidateReview';
import { stubFetchRoutes } from '../test/apiFixtures';
import type {
  ApiEvidenceClassification,
  ApiRunCheckResponse,
  ApiValidateResult,
  ApiWarningsResponse,
} from '../lib/types';

/*
 * VALIDATE & REVIEW — the experiment-level action, grouped by run.
 *
 * WHAT THIS FILE IS GUARDING, and why each guard exists rather than reads as
 * ceremony. Every property below is one this repository has already got wrong in
 * a shipped surface, or one the component's own header claims and could
 * therefore stop honouring silently.
 *
 * THE NEGATIVE CONTROLS WERE EXECUTED. For each, the named source line was
 * broken, this file was run, the failure observed, and the source restored (the
 * restore was byte-compared against a backup taken before the first mutation).
 * THE DENOMINATOR IS 32, READ OFF THE RUNS — every count and every quoted message
 * below is transcribed from the run that produced it, not carried forward.
 *
 *  NC1 · make an advisory warning move the ROW's verdict. In `UnitGroup`, derive
 *        the state as `adviceWarnings.length > 0 ? 'fail' : runFindingState(...)`.
 *        1 of 32 failed — "an advisory-only run does NOT present as blocked" ->
 *        `Unable to find an element with the text: Passed`, over a rendered
 *        `data-state="fail"`.
 *
 *        THE SCOPE IS STATED BECAUSE IT IS NARROWER THAN IT LOOKS, and the same
 *        correction had to be made to `run-findings.test.tsx`. The tally
 *        assertions did NOT fire: `summaryLine` calls `runFindingState` itself,
 *        so a break confined to the row leaves the count line correct. They are
 *        independent of the row's ELEMENT, not of its source.
 *
 *  NC1b · the same break applied in `summaryLine` as well. 4 of 32 failed, adding
 *        "a run with advisory notes and no findings still says it passed", "the
 *        tally counts verdicts, and advisory notes are not verdicts", and "a
 *        failed read of the axis ... leaves every verdict standing". So the tally
 *        guards are live; NC1 simply does not reach them.
 *        `_fan_out_warnings_payload` hardcodes `advisory: true, gating: false`.
 *
 *  NC2 · collapse "not checked" into "clean". In `unitCounts`, replace the
 *        `detail === undefined` branch's sentence with the checked-and-empty one
 *        (`count(0, 'open question')` etc.). 1 of 32 failed:
 *        "a run whose detail has NOT been fetched says so, and does not say 0" ->
 *        `expected '0 blocking findings · 0 advisory note…' to contain
 *        'not checked yet'`.
 *
 *  NC2b · THE INVERSE, so the polarity twin is shown to be capable of failing:
 *        make the CHECKED-and-empty branch claim "not checked yet". 1 of 32
 *        failed — "a run whose detail HAS been fetched and is empty says 0, not
 *        'not checked'" -> `expected … not to contain 'not checked yet'`. Two
 *        controls in opposite directions, because a guard that only ever checks
 *        one cannot tell a working rule from a dead one.
 *
 *  NC3 · name the official schema as the source of a DRY-RUN finding. In
 *        `UnitGroup`'s heading, drop the `unit.verdict.dry_run` branch and always
 *        render the "official ISAAC schema error" wording. 2 of 32 failed:
 *        "an exactness finding on a candidate record is NOT called a schema
 *        error" -> `expected 'Blocks export · 1 official ISAAC sche…' to contain
 *        'source not named'`, and "a finding on a CANDIDATE record is never
 *        called an official ISAAC schema error" -> `… not to contain 'official
 *        ISAAC schema'`. THIS IS THE `VerdictCard` DEFECT: an anchored-pattern
 *        exactness refusal is ISAAC's gate, not upstream's, and `export.py` folds
 *        it into the same undifferentiated list, so the wire cannot tell the two
 *        apart and neither may the label.
 *
 *  NC4 · check everything on mount (`useEffect(() => runReview(), [])` plus a
 *        per-run fan-out on arrival). 32 of 32 failed — the eager mount also
 *        removes the "Validate & Review" button every other test presses, so the
 *        control is blunt. The named one is "nothing is requested until the
 *        button is pressed" -> `expected [ …(3) ] to have a length of +0 but got 3`.
 *
 *  NC4b · THE SURGICAL FORM: keep the button, but fan the per-run detail out from
 *        `runReview`'s `.then`. 4 of 32 failed, isolating the scale guard:
 *        "a 200-run record costs THREE requests, not 200" ->
 *        `expected [ …(203) ] to have a length of 3 but got 203`; and
 *        "one run's detail is ONE request…" -> `expected [ …(6) ] to have a
 *        length of 4 but got 6`.
 *
 *  NC5 · present the evidence-support axis as a blocker. Change `AttentionBlock`'s
 *        heading to `Blocks export · evidence support`. 3 of 32 failed, including
 *        "the evidence-support axis is neither blocking nor advisory, and says so"
 *        -> `expected 'Blocks export · evidence supportThis …' not to contain
 *        'Blocks export'`. `get_evidence_classification` states of itself that it
 *        "deliberately carries NO validity/completion/advisory verdict".
 *
 *  NC6 · invent a blocker kind instead of reading the server's. Replace
 *        `blockerKindLine`'s read of `blocker.kind` with a constant
 *        `'descriptor'`. 2 of 32 failed: "a descriptor blocker is counted as a
 *        descriptor, using the server's word" -> `expected 'By the kind the
 *        server recorded for e…' to contain '2 descriptor'`, and "a blocker with
 *        no kind is counted, never dropped and never assigned one" ->
 *        `… to contain '1 kind not recorded'`.
 *
 * ── REVIEW FIXES, 2026-08-16 · NC7–NC11, DENOMINATOR NOW 40 ──────────────────
 *
 * An independent review of this feature found five claims the suite above could
 * not have caught, four of them on screen and one in a comment. The guards added
 * for them were negative-controlled the same way: the named source line was
 * broken, this file was run, the failure observed, and the file restored from a
 * backup taken before the first mutation (`diff` clean after each). THE
 * DENOMINATOR IS 40, READ OFF THOSE RUNS.
 *
 *  NC7 · render the unattributable advisory count as a zero. In `unitCounts`,
 *        replace the `adviceCount === null` clause with
 *        `count(adviceCount ?? 0, 'advisory note')`. 1 of 40 failed — "does NOT
 *        claim zero advisory notes when the server reported some it cannot
 *        attribute" -> `expected '0 blocking findings · 0 advisory not…' to
 *        contain 'not attributable to this unit'`.
 *
 *        THIS IS THE ONE THAT WAS LIVE ON EVERY RECORD A SCIENTIST CAN OPEN. All
 *        five canonical seeds have NO runs, so `_warnings_payload` sends no `runs`
 *        key, so `adviceFor` returns `undefined` — while the same response carries
 *        one or two real advisory warnings (`NO_LINKS`,
 *        `NO_MEASUREMENT_SERIES`). "Cannot attribute" was being printed as "zero",
 *        which is a stronger and false claim. The refusal to attribute is CORRECT
 *        and is preserved; only its rendering changed.
 *
 *  NC8 · count the `unavailable` sentinel as a finding. In `unitCounts`, drop the
 *        `state === 'unavailable'` clause and always
 *        `count(unit.verdict.errors.length, 'blocking finding')`. 1 of 40 failed —
 *        "“no verdict” is not a failure…" -> `expected '1 blocking finding ·
 *        advisory notes n…' not to contain '1 blocking finding'`.
 *        `_validate_unit` returns exactly one synthetic `{path: "$", message:
 *        "Validation could not be completed."}` there, so the card read "1
 *        blocking finding" directly above "this is not a schema failure".
 *
 *  NC9 · freeze the detail button's accessible name at its idle wording:
 *        `aria-label={`Check This Run In Detail — ${unit.label}`}`. Chosen over
 *        the blunter break (restoring `Check ${unit.label} in detail`, which fails
 *        10 of 40 because every `pressDetail` misses) so the control isolates the
 *        RULE. 1 of 40 failed — "the detail button’s accessible name contains its
 *        visible label, in all three states" -> `expected 'Check This Run In
 *        Detail — Run 1' to contain 'Checking…'`.
 *
 * NC10 · restore the causal claim: "…do not agree, so this run changed after the
 *        summary was taken". 2 of 40 failed -> `expected 'This run’s own check and
 *        the summary …' to contain 'cannot say why'`. It cannot only mean that: a
 *        transient artifact read failure flips the unit to `unavailable` with
 *        nothing having changed, and an edit to the RECORD moves the verdict while
 *        the sentence blames the run.
 *
 * NC11 · restore "This is the whole record’s evidence-support review". 1 of 40
 *        failed — "the evidence-support axis is neither blocking nor advisory, and
 *        says so" -> `expected 'Evidence support · no verdict either …' not
 *        to contain 'whole record'`. `get_evidence_classification` classifies
 *        `exp.draft`, the EXPERIMENT-LEVEL half, which on a record with runs holds
 *        no measurement, no links and no run content and is never exported.
 *
 * POLARITY IS ASSERTED BOTH WAYS THROUGHOUT. A test in this repository has
 * already shipped INVERTED and passed (`upload-claim-parity.test.tsx`'s first
 * version), so "an advisory note does not block" is asserted alongside "a real
 * blocker does" — a guard that only ever checks one direction cannot tell a
 * working rule from a dead one.
 */

const ID = 'EXP-SYNTHETIC-1';
const P = (path: string) => `/api/experiments/${ID}${path}`;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** The fixed sentinel `_validate_unit` returns when NO verdict could be produced. */
const UNAVAILABLE_ERROR = { path: '$', message: 'Validation could not be completed.' };

/**
 * An anchored-pattern exactness refusal, as it arrives HERE.
 *
 * On the standalone Validator this same finding arrives in its own
 * `exactness_errors` list beside `schema_ok: true`. On the per-run wire it does
 * not: `export_draft` folds it into `draft_report` and returns
 * `official_report=None`, so `_validate_unit`'s dry-run branch emits it as an
 * ordinary `{path, message}` pair, indistinguishable from a no-guessing finding.
 * That indistinguishability is precisely why this surface may not name a source.
 */
const EXACTNESS_FINDING = {
  path: 'tags.0',
  message:
    "value is accepted by the schema pattern '^\\\\S(.*\\\\S)?$' only because Python's " +
    "'$' also matches before a trailing newline; the pattern is anchored and the value " +
    'does not match it exactly.',
};

function verdict(over: Partial<NonNullable<ApiValidateResult['runs']>[number]> = {}) {
  return {
    run_id: 'RUN-1',
    run_label: 'Run 1',
    record_id: 'REC-1',
    ok: true,
    errors: [] as { path: string; message: string }[],
    dry_run: true,
    ...over,
  };
}

function validateBody(runs: NonNullable<ApiValidateResult['runs']>): ApiValidateResult {
  return {
    ok: runs.every((r) => r.ok),
    errors: runs.find((r) => !r.ok)?.errors ?? [],
    schema: 'ISAAC v1.05',
    dry_run: runs.some((r) => r.dry_run),
    runs,
  };
}

function warningsBody(runs: NonNullable<ApiWarningsResponse['runs']> = []): ApiWarningsResponse {
  return {
    advisory: true,
    gating: false,
    warnings: runs.flatMap((r) => r.warnings),
    dry_run: true,
    runs,
  };
}

const NO_CLASSIFICATION: ApiEvidenceClassification = {
  record_rev: 3,
  field_results: [],
  counts: {
    supported: 0,
    inferred_candidate: 0,
    insufficient_evidence: 0,
    conflicting_evidence: 0,
    unknown: 0,
    unreadable: 0,
  },
};

function checkBody(over: Partial<ApiRunCheckResponse> = {}): ApiRunCheckResponse {
  return {
    ok: true,
    draft: { ok: true, errors: [], warnings: [] },
    official: { ok: true, errors: [], dry_run: true },
    blockers: [],
    checked_run_version: '1.4',
    ...over,
  };
}

/** Mounts the section with a route table, and hands back the recorded call list. */
function mount(routes: Record<string, unknown>) {
  const calls = stubFetchRoutes(routes as Parameters<typeof stubFetchRoutes>[0]);
  render(<ValidateReview experimentId={ID} />);
  return calls;
}

const press = () => fireEvent.click(screen.getByRole('button', { name: 'Validate & Review' }));

/**
 * The ACCESSIBLE NAME of one run's detail button, in each of its three states.
 *
 * It is the visible label followed by the run, in that order, because WCAG 2.5.3
 * (label in name) requires the printed words to appear in the announced name —
 * see `detailButtonLabel` and the comment on the button itself. Every query below
 * goes through here rather than through a class or a DOM position, so a change
 * that breaks the announced name breaks these tests rather than passing quietly.
 */
const detailName = {
  idle: (label = 'Run 1') => `Check This Run In Detail — ${label}`,
  again: (label = 'Run 1') => `Check This Run Again — ${label}`,
  checking: (label = 'Run 1') => `Checking… — ${label}`,
};

/** Press one run's detail button in its unpressed state. */
const pressDetail = (label = 'Run 1') =>
  fireEvent.click(screen.getByRole('button', { name: detailName.idle(label) }));

/** The `<li>` for one run, addressed by the `data-run-id` the component sets. */
function unitEl(runId: string): HTMLElement {
  const el = document.querySelector(`.vr-unit[data-run-id="${runId}"]`);
  if (!el) throw new Error(`no unit rendered for run ${runId}`);
  return el as HTMLElement;
}

// --- 1. nothing happens until it is asked for --------------------------------

describe('the triggering model is explicit, and bounded when it fires', () => {
  it('nothing is requested until the button is pressed', () => {
    const calls = mount({
      [`POST ${P('/validate')}`]: { body: validateBody([verdict()]) },
      [`GET ${P('/warnings')}`]: { body: warningsBody() },
      [`GET ${P('/evidence-classification')}`]: { body: NO_CLASSIFICATION },
    });
    expect(calls).toHaveLength(0);
    // And the idle text is a statement about coverage, not about findings.
    expect(screen.getByRole('status')).toHaveTextContent(/No check has been run here yet/);
  });

  it('a 200-run record costs THREE requests, not 200', async () => {
    const runs = Array.from({ length: 200 }, (_, i) =>
      verdict({ run_id: `RUN-${i}`, run_label: `Run ${i}`, record_id: `REC-${i}` }),
    );
    const calls = mount({
      [`POST ${P('/validate')}`]: { body: validateBody(runs) },
      [`GET ${P('/warnings')}`]: { body: warningsBody() },
      [`GET ${P('/evidence-classification')}`]: { body: NO_CLASSIFICATION },
    });
    press();
    await screen.findByText(/200 runs checked/);
    expect(calls).toHaveLength(3);
    expect(calls.filter((c) => c.includes('/check'))).toHaveLength(0);
    // Re-reading is the same three, not three plus a per-run fan-out.
    fireEvent.click(screen.getByRole('button', { name: 'Check Again' }));
    await waitFor(() => expect(calls).toHaveLength(6));
  });

  it('one run’s detail is ONE request, and only for the run whose button was pressed', async () => {
    const calls = mount({
      [`POST ${P('/validate')}`]: {
        body: validateBody([
          verdict({ run_id: 'RUN-1', run_label: 'Run 1', record_id: 'REC-1' }),
          verdict({ run_id: 'RUN-2', run_label: 'Run 2', record_id: 'REC-2' }),
        ]),
      },
      [`GET ${P('/warnings')}`]: { body: warningsBody() },
      [`GET ${P('/evidence-classification')}`]: { body: NO_CLASSIFICATION },
      [`POST ${P('/runs/RUN-2/check')}`]: { body: checkBody() },
    });
    press();
    await screen.findByText(/2 runs checked/);
    pressDetail('Run 2');
    await waitFor(() => expect(calls).toHaveLength(4));
    expect(calls.filter((c) => c.includes('/check'))).toEqual([
      `POST ${P('/runs/RUN-2/check')}`,
    ]);
  });
});

// --- 2. advisory never reads as blocking, and blocking never reads as advisory --

describe('advisory and blocking stay apart', () => {
  const ADVISORY = {
    run_id: 'RUN-1',
    run_label: 'Run 1',
    record_id: 'REC-1',
    warnings: [
      {
        code: 'NO_MEASUREMENT_SERIES',
        where: 'measurement',
        message: 'This record declares no measurement series.',
      },
    ],
    dry_run: true,
  };

  async function renderAdvisoryOnly() {
    mount({
      [`POST ${P('/validate')}`]: { body: validateBody([verdict({ ok: true })]) },
      [`GET ${P('/warnings')}`]: { body: warningsBody([ADVISORY]) },
      [`GET ${P('/evidence-classification')}`]: { body: NO_CLASSIFICATION },
    });
    press();
    await screen.findByText(/1 run checked/);
  }

  it('an advisory-only run does NOT present as blocked', async () => {
    await renderAdvisoryOnly();
    const unit = unitEl('RUN-1');
    expect(within(unit).getByText('Passed')).toBeTruthy();
    expect(unit.getAttribute('data-state')).toBe('pass');
    expect(unit.textContent).not.toContain('Blocks export');
    // The advisory block is present, and says what it cannot do.
    expect(within(unit).getByText(/Advisory · non-gating/)).toBeTruthy();
    expect(unit.textContent).toContain('never block export');
  });

  it('a run with advisory notes and no findings still says it passed', async () => {
    await renderAdvisoryOnly();
    expect(screen.getByRole('status')).toHaveTextContent('1 run checked: 1 passed.');
  });

  it('the tally counts verdicts, and advisory notes are not verdicts', async () => {
    mount({
      [`POST ${P('/validate')}`]: {
        body: validateBody([
          verdict({ run_id: 'RUN-1', run_label: 'Run 1', record_id: 'REC-1', ok: true }),
          verdict({ run_id: 'RUN-2', run_label: 'Run 2', record_id: 'REC-2', ok: true }),
        ]),
      },
      [`GET ${P('/warnings')}`]: {
        body: warningsBody([
          ADVISORY,
          { ...ADVISORY, run_id: 'RUN-2', run_label: 'Run 2', record_id: 'REC-2' },
        ]),
      },
      [`GET ${P('/evidence-classification')}`]: { body: NO_CLASSIFICATION },
    });
    press();
    await screen.findByText(/2 runs checked/);
    expect(screen.getByRole('status')).toHaveTextContent('2 runs checked: 2 passed.');
  });

  it('a HARD BLOCKER does present as blocked — the polarity twin of the above', async () => {
    mount({
      [`POST ${P('/validate')}`]: {
        body: validateBody([
          verdict({
            ok: false,
            errors: [{ path: 'sample.material', message: "'name' is a required property" }],
          }),
        ]),
      },
      [`GET ${P('/warnings')}`]: { body: warningsBody() },
      [`GET ${P('/evidence-classification')}`]: { body: NO_CLASSIFICATION },
    });
    press();
    await screen.findByText(/1 run checked/);
    const unit = unitEl('RUN-1');
    expect(within(unit).getByText('Failed')).toBeTruthy();
    expect(unit.textContent).toContain('Blocks export');
    expect(unit.textContent).toContain("'name' is a required property");
    expect(screen.getByRole('status')).toHaveTextContent('1 run checked: 1 did not pass.');
  });

  it('the no-guessing WARN channel is labelled non-gating, apart from its errors', async () => {
    mount({
      [`POST ${P('/validate')}`]: { body: validateBody([verdict()]) },
      [`GET ${P('/warnings')}`]: { body: warningsBody() },
      [`GET ${P('/evidence-classification')}`]: { body: NO_CLASSIFICATION },
      [`POST ${P('/runs/RUN-1/check')}`]: {
        body: checkBody({
          draft: {
            ok: true,
            errors: [],
            warnings: [
              {
                path: 'sample.mass',
                message: 'inferred field cites a rule but no observed supporting evidence',
              },
            ],
          },
        }),
      },
    });
    press();
    await screen.findByText(/1 run checked/);
    pressDetail();
    const heading = await screen.findByText(/Advisory · non-gating · no-guessing notes/);
    // The WHOLE heading, not merely "contains a 1" — which almost any string
    // satisfies, including one that had lost the count entirely and kept a
    // version number, a path or an id.
    expect(heading.textContent).toBe('Advisory · non-gating · no-guessing notes · 1');
    // It is not filed under either export-blocking heading.
    expect(screen.queryByText(/Blocks export · no-guessing checks/)).toBeNull();
    // And the verdict is untouched by it.
    expect(within(unitEl('RUN-1')).getByText('Passed')).toBeTruthy();
  });

  it('the no-guessing ERROR channel IS filed as export-blocking — the polarity twin', async () => {
    mount({
      [`POST ${P('/validate')}`]: { body: validateBody([verdict()]) },
      [`GET ${P('/warnings')}`]: { body: warningsBody() },
      [`GET ${P('/evidence-classification')}`]: { body: NO_CLASSIFICATION },
      [`POST ${P('/runs/RUN-1/check')}`]: {
        body: checkBody({
          draft: {
            ok: false,
            errors: [{ path: 'assets.0', message: 'no evidence — every asset must cite a source' }],
            warnings: [],
          },
        }),
      },
    });
    press();
    await screen.findByText(/1 run checked/);
    pressDetail();
    expect(await screen.findByText(/Blocks export · no-guessing checks/)).toBeTruthy();
    expect(screen.queryByText(/Advisory · non-gating · no-guessing notes/)).toBeNull();
  });
});

// --- 3. "not checked" is not "clean" -----------------------------------------

describe('“not checked” and “0 findings” are different sentences', () => {
  const ROUTES_ONE_RUN = {
    [`POST ${P('/validate')}`]: { body: validateBody([verdict()]) },
    [`GET ${P('/warnings')}`]: { body: warningsBody() },
    [`GET ${P('/evidence-classification')}`]: { body: NO_CLASSIFICATION },
    [`POST ${P('/runs/RUN-1/check')}`]: { body: checkBody() },
  };

  it('a run whose detail has NOT been fetched says so, and does not say 0', async () => {
    mount(ROUTES_ONE_RUN);
    press();
    await screen.findByText(/1 run checked/);
    const counts = unitEl('RUN-1').querySelector('.vr-unit-counts')!;
    expect(counts.textContent).toContain('not checked yet');
    expect(counts.textContent).not.toContain('0 open questions');
    // Section level says the same fact in its own words.
    expect(screen.getByRole('status')).toHaveTextContent('0 of 1 run also checked in detail.');
  });

  it('a run whose detail HAS been fetched and is empty says 0, not “not checked”', async () => {
    mount(ROUTES_ONE_RUN);
    press();
    await screen.findByText(/1 run checked/);
    pressDetail();
    await screen.findByText(/This run has no open questions/);
    const counts = unitEl('RUN-1').querySelector('.vr-unit-counts')!;
    expect(counts.textContent).toContain('0 open questions');
    expect(counts.textContent).not.toContain('not checked yet');
    expect(screen.getByRole('status')).toHaveTextContent('1 of 1 run also checked in detail.');
  });

  it('a detail request that FAILS reads as neither checked nor clean', async () => {
    mount({
      ...ROUTES_ONE_RUN,
      [`POST ${P('/runs/RUN-1/check')}`]: { status: 500, body: { detail: 'boom' } },
    });
    press();
    await screen.findByText(/1 run checked/);
    pressDetail();
    await screen.findByRole('alert');
    const counts = unitEl('RUN-1').querySelector('.vr-unit-counts')!;
    expect(counts.textContent).toContain('could not be run');
    expect(counts.textContent).not.toContain('0 open questions');
    expect(screen.getByRole('status')).toHaveTextContent('0 of 1 run also checked in detail.');
  });
});

// --- 4. ok / schema_ok / exactness are never conflated -----------------------

describe('an ISAAC gate is never reported as an official-schema error', () => {
  async function renderDryRunFinding(errors: { path: string; message: string }[]) {
    mount({
      [`POST ${P('/validate')}`]: {
        body: validateBody([verdict({ ok: false, dry_run: true, errors })]),
      },
      [`GET ${P('/warnings')}`]: { body: warningsBody() },
      [`GET ${P('/evidence-classification')}`]: { body: NO_CLASSIFICATION },
    });
    press();
    await screen.findByText(/1 run checked/);
    return unitEl('RUN-1');
  }

  it('an exactness finding on a candidate record is NOT called a schema error', async () => {
    const unit = await renderDryRunFinding([EXACTNESS_FINDING]);
    const heading = unit.querySelector('.vr-group-title')!;
    expect(heading.textContent).toContain('Blocks export');
    expect(heading.textContent).toContain('source not named');
    expect(heading.textContent).not.toContain('official ISAAC schema');
    // The finding itself is still shown, verbatim.
    expect(unit.textContent).toContain('the pattern is anchored');
  });

  it('a finding on a CANDIDATE record is never called an official ISAAC schema error', async () => {
    const unit = await renderDryRunFinding([
      { path: 'sample', message: "'material' is a required property" },
    ]);
    expect(unit.querySelector('.vr-group-title')!.textContent).not.toContain(
      'official ISAAC schema',
    );
  });

  it('a finding on a WRITTEN record IS named as the schema’s — the polarity twin', async () => {
    mount({
      [`POST ${P('/validate')}`]: {
        body: validateBody([
          verdict({
            ok: false,
            dry_run: false,
            errors: [{ path: 'sample', message: "'material' is a required property" }],
          }),
        ]),
      },
      [`GET ${P('/warnings')}`]: { body: warningsBody() },
      [`GET ${P('/evidence-classification')}`]: { body: NO_CLASSIFICATION },
    });
    press();
    await screen.findByText(/1 run checked/);
    const heading = unitEl('RUN-1').querySelector('.vr-group-title')!;
    expect(heading.textContent).toContain('official ISAAC schema error');
    expect(heading.textContent).not.toContain('source not named');
  });

  it('the screen states, once, that it cannot separate the schema from ISAAC’s gate', async () => {
    await renderDryRunFinding([EXACTNESS_FINDING]);
    const notes = [...document.querySelectorAll('.vr-note')].map((n) => n.textContent ?? '');
    expect(notes.some((t) => t.includes('anchored-pattern exactness'))).toBe(true);
    expect(notes.some((t) => t.includes('Standalone Validator'))).toBe(true);
  });

  it('“no verdict” is not a failure, and claims no document was checked', async () => {
    mount({
      [`POST ${P('/validate')}`]: {
        body: validateBody([
          verdict({ ok: false, dry_run: false, unavailable: true, errors: [UNAVAILABLE_ERROR] }),
        ]),
      },
      [`GET ${P('/warnings')}`]: { body: warningsBody() },
      [`GET ${P('/evidence-classification')}`]: { body: NO_CLASSIFICATION },
    });
    press();
    await screen.findByText(/1 run checked/);
    const unit = unitEl('RUN-1');
    expect(within(unit).getByText('No verdict')).toBeTruthy();
    expect(unit.textContent).toContain('this is not a schema failure');
    expect(unit.querySelector('.vr-unit-subject')).toBeNull();
    expect(unit.textContent).not.toContain('Blocks export');
    expect(screen.getByRole('status')).toHaveTextContent(
      '1 run checked: 1 could not be checked.',
    );
    /*
     * AND THE COUNTS LINE DOES NOT COUNT THE REFUSAL AS A FINDING. `_validate_unit`
     * returns exactly one synthetic sentinel error on this branch — the fixed
     * "Validation could not be completed." above — which is a refusal, not
     * something wrong with the record. Counting it put "1 blocking finding"
     * directly above "this is not a schema failure", which is the same sentence
     * pair contradicting itself. `unavailable` is a fourth state that is not a
     * tier; the numbers have to honour that too.
     */
    const counts = unit.querySelector('.vr-unit-counts')!.textContent ?? '';
    expect(counts).not.toContain('1 blocking finding');
    expect(counts).not.toContain('blocking findings');
    expect(counts).toContain('no verdict, so nothing here is counted as a blocking finding');
  });

  /*
   * THE POLARITY TWIN. A unit that DID produce a verdict and DID fail counts its
   * findings as findings — so the branch above is a real distinction and not a
   * blanket suppression of the number.
   */
  it('a unit that DID produce a verdict still counts its blocking findings', async () => {
    mount({
      [`POST ${P('/validate')}`]: {
        body: validateBody([
          verdict({
            ok: false,
            errors: [
              { path: 'sample', message: "'material' is a required property" },
              { path: '$', message: "'title' is a required property" },
            ],
          }),
        ]),
      },
      [`GET ${P('/warnings')}`]: { body: warningsBody() },
      [`GET ${P('/evidence-classification')}`]: { body: NO_CLASSIFICATION },
    });
    press();
    await screen.findByText(/1 run checked/);
    const counts = unitEl('RUN-1').querySelector('.vr-unit-counts')!.textContent ?? '';
    expect(counts).toContain('2 blocking findings');
    expect(counts).not.toContain('no verdict');
  });
});

// --- 5. the evidence-support axis: conflicts, gaps, unsupported descriptors ---

describe('the evidence-support axis is a third thing, and says which', () => {
  const CLASSIFIED: ApiEvidenceClassification = {
    record_rev: 4,
    field_results: [
      {
        field: 'sample.material.name',
        classification: 'conflicting_evidence',
        value_state: 'candidate',
        explanation: 'Two cited sources give different values for this field.',
        sources: [],
      },
      {
        field: 'descriptors:absorbing_element',
        classification: 'insufficient_evidence',
        value_state: 'none',
        explanation: 'No cited source supports this descriptor.',
        sources: [],
      },
      {
        field: 'sample.mass',
        classification: 'supported',
        value_state: 'confirmed',
        explanation: 'Supported by one observed source.',
        sources: [],
      },
    ],
    counts: {
      supported: 1,
      inferred_candidate: 0,
      insufficient_evidence: 1,
      conflicting_evidence: 1,
      unknown: 0,
      unreadable: 0,
    },
  };

  async function renderClassified(body: ApiEvidenceClassification | { status: number }) {
    mount({
      [`POST ${P('/validate')}`]: { body: validateBody([verdict()]) },
      [`GET ${P('/warnings')}`]: { body: warningsBody() },
      [`GET ${P('/evidence-classification')}`]:
        'status' in body ? { status: body.status, body: {} } : { body },
    });
    press();
    await screen.findByText(/1 run checked/);
  }

  it('conflicts and gaps are reported under the server’s own class names', async () => {
    await renderClassified(CLASSIFIED);
    const block = await screen.findByText(/Evidence support · no verdict either way/);
    const panel = block.closest('.vr-attention')!;
    expect(within(panel as HTMLElement).getByText(/Conflicting evidence · 1/)).toBeTruthy();
    expect(within(panel as HTMLElement).getByText(/Insufficient evidence · 1/)).toBeTruthy();
    expect(panel.textContent).toContain('sample.material.name');
    expect(panel.textContent).toContain('descriptors:absorbing_element');
    // A supported field is not listed: this block is what needs attention.
    expect(panel.textContent).not.toContain('sample.mass');
  });

  it('a descriptor is named a descriptor, from the server’s own address namespace', async () => {
    await renderClassified(CLASSIFIED);
    const panel = document.querySelector('.vr-attention')!;
    expect(within(panel as HTMLElement).getByText('descriptor')).toBeTruthy();
    expect(panel.textContent).toContain('1 of them a descriptor');
  });

  it('the evidence-support axis is neither blocking nor advisory, and says so', async () => {
    await renderClassified(CLASSIFIED);
    const panel = document.querySelector('.vr-attention')!;
    expect(panel.textContent).toContain('It decides nothing about validity');
    expect(panel.textContent).toContain('neither blocks export');
    expect(panel.textContent).not.toContain('Blocks export');
    expect(panel.querySelector('.vr-advisory')).toBeNull();
    // And it does not claim to be per-run.
    expect(panel.textContent).toContain('not one run’s');
    /*
     * NOR DOES IT CLAIM TO COVER THE WHOLE RECORD, which is the opposite
     * over-claim and the one that actually shipped. `get_evidence_classification`
     * classifies `exp.draft` — the EXPERIMENT-LEVEL half, which on a record with
     * runs carries no measurement, no links and no run content, and is never
     * exported on its own. "The whole record's evidence-support review" was
     * therefore false wherever it mattered most.
     */
    expect(panel.textContent).not.toContain('whole record');
    expect(panel.textContent).toContain('record-level draft');
  });

  it('“Blocks export” appears only where the server gates export', async () => {
    await renderClassified(CLASSIFIED);
    // The one run passed, and the attention block carries conflicts + gaps. If
    // either were presented as gating, this phrase would be on the screen.
    expect(screen.queryByText(/Blocks export/)).toBeNull();
  });

  it('an empty axis says 0 conflicts — which is not what a failed read says', async () => {
    await renderClassified(NO_CLASSIFICATION);
    const panel = document.querySelector('.vr-attention')!;
    expect(panel.textContent).toContain('0 conflicts, 0 gaps');
    expect(panel.textContent).not.toContain('not checked');
  });

  it('a failed read of the axis says “not checked” and leaves every verdict standing', async () => {
    await renderClassified({ status: 500 });
    const panel = await waitFor(() => {
      const el = document.querySelector('.vr-attention');
      if (!el || !el.textContent?.includes('not checked')) throw new Error('not yet');
      return el;
    });
    expect(panel.textContent).toContain('not checked');
    expect(panel.textContent).not.toContain('0 conflicts');
    // The run verdicts came from different endpoints and are unaffected.
    expect(within(unitEl('RUN-1')).getByText('Passed')).toBeTruthy();
    expect(screen.getByRole('status')).toHaveTextContent('1 run checked: 1 passed.');
  });
});

// --- 6. blocker kinds, verbatim from the server ------------------------------

describe('blocker kinds come from the server’s own field', () => {
  async function renderBlockers(blockers: unknown[]) {
    mount({
      [`POST ${P('/validate')}`]: { body: validateBody([verdict()]) },
      [`GET ${P('/warnings')}`]: { body: warningsBody() },
      [`GET ${P('/evidence-classification')}`]: { body: NO_CLASSIFICATION },
      [`POST ${P('/runs/RUN-1/check')}`]: {
        body: checkBody({ blockers: blockers as ApiRunCheckResponse['blockers'] }),
      },
    });
    press();
    await screen.findByText(/1 run checked/);
    pressDetail();
    return await screen.findByText(/Blocks export · open questions/);
  }

  it('a descriptor blocker is counted as a descriptor, using the server’s word', async () => {
    await renderBlockers([
      { kind: 'descriptor', question: 'Which absorbing element?', message: 'Which absorbing element?' },
      { kind: 'descriptor', question: 'Which edge?', message: 'Which edge?' },
      { kind: 'asset', question: 'Paste the sha256.', message: 'Paste the sha256.' },
    ]);
    const line = document.querySelector('.vr-kinds')!;
    expect(line.textContent).toContain('2 descriptor');
    expect(line.textContent).toContain('1 asset');
  });

  it('a blocker with no kind is counted, never dropped and never assigned one', async () => {
    await renderBlockers([{ message: 'A blocking question is open on this run.' }]);
    const line = document.querySelector('.vr-kinds')!;
    expect(line.textContent).toContain('1 kind not recorded');
    expect(line.textContent).not.toContain('descriptor ·');
    // The finding row itself is still rendered.
    expect(screen.getByText('A blocking question is open on this run.')).toBeTruthy();
  });

  it('no kind line is rendered when there are no blockers', async () => {
    mount({
      [`POST ${P('/validate')}`]: { body: validateBody([verdict()]) },
      [`GET ${P('/warnings')}`]: { body: warningsBody() },
      [`GET ${P('/evidence-classification')}`]: { body: NO_CLASSIFICATION },
      [`POST ${P('/runs/RUN-1/check')}`]: { body: checkBody() },
    });
    press();
    await screen.findByText(/1 run checked/);
    pressDetail();
    await screen.findByText(/This run has no open questions/);
    expect(document.querySelector('.vr-kinds')).toBeNull();
  });
});

// --- 6b. a disagreement is reported as an observation, with no cause named ----

/*
 * `UnitDetail` compares its own `official` verdict with the summary's and says
 * when they differ. THAT COMPARISON IS SUPPORTED; A CAUSE FOR IT IS NOT. The copy
 * used to read "so this run changed after the summary was taken", which is one
 * explanation among several — an edit to the RECORD moves the verdict while that
 * sentence blames the run, and a transient artifact read failure flips a unit to
 * `unavailable` with nothing having changed at all. There was NO test here; the
 * over-claim shipped unguarded.
 */
describe('a check that disagrees with the summary reports the disagreement, not a cause', () => {
  async function renderDisagreement(official: ApiRunCheckResponse['official']) {
    mount({
      // The summary says this run passed.
      [`POST ${P('/validate')}`]: { body: validateBody([verdict({ ok: true })]) },
      [`GET ${P('/warnings')}`]: { body: warningsBody() },
      [`GET ${P('/evidence-classification')}`]: { body: NO_CLASSIFICATION },
      // Its own check says otherwise.
      [`POST ${P('/runs/RUN-1/check')}`]: { body: checkBody({ official }) },
    });
    press();
    await screen.findByText(/1 run checked/);
    pressDetail();
    return await screen.findByText(/do not agree/);
  }

  it('states that the two checks do not agree, and names no cause', async () => {
    const line = await renderDisagreement({
      ok: false,
      errors: [{ path: 'sample', message: "'material' is a required property" }],
      dry_run: true,
    });
    const text = line.textContent ?? '';
    expect(text).toContain('do not agree');
    expect(text).toContain('cannot say why');
    // The three over-claims, each asserted absent by its own words.
    expect(text).not.toContain('this run changed after the summary');
    expect(text).not.toMatch(/can only mean/);
    expect(text).not.toMatch(/so this run changed/);
    // It still tells the reader the one thing they can do about it.
    expect(text).toContain('again for a current summary');
  });

  it('says the same thing when the flip is to “no verdict”, where nothing need have changed', async () => {
    // A transient artifact read failure produces exactly this: the per-run check
    // comes back `unavailable` against a summary that had a verdict. Nothing about
    // the run moved, so a sentence claiming it did would be false here.
    const line = await renderDisagreement({ ok: false, unavailable: true, errors: [], dry_run: false });
    expect(line.textContent).toContain('cannot say why');
    expect(line.textContent).not.toContain('this run changed after the summary');
  });

  it('THE POLARITY TWIN — two checks that agree render no disagreement line at all', async () => {
    mount({
      [`POST ${P('/validate')}`]: { body: validateBody([verdict({ ok: true })]) },
      [`GET ${P('/warnings')}`]: { body: warningsBody() },
      [`GET ${P('/evidence-classification')}`]: { body: NO_CLASSIFICATION },
      [`POST ${P('/runs/RUN-1/check')}`]: { body: checkBody() },
    });
    press();
    await screen.findByText(/1 run checked/);
    pressDetail();
    await screen.findByText(/This run has no open questions/);
    expect(document.querySelector('.vr-detail-disagree')).toBeNull();
    expect(screen.queryByText(/do not agree/)).toBeNull();
  });
});

// --- 7. structure a keyboard and a screen reader can use ---------------------

describe('headings, live region and severity without colour', () => {
  it('every run is a real heading under the section heading, with no level skipped', async () => {
    mount({
      [`POST ${P('/validate')}`]: {
        body: validateBody([
          verdict({ run_id: 'RUN-1', run_label: 'Run 1', record_id: 'REC-1' }),
          verdict({ run_id: 'RUN-2', run_label: 'Run 2', record_id: 'REC-2' }),
        ]),
      },
      [`GET ${P('/warnings')}`]: { body: warningsBody() },
      [`GET ${P('/evidence-classification')}`]: { body: NO_CLASSIFICATION },
    });
    press();
    await screen.findByText(/2 runs checked/);
    expect(screen.getByRole('heading', { level: 2, name: 'Validate & Review' })).toBeTruthy();
    const runHeadings = screen.getAllByRole('heading', { level: 3 });
    expect(runHeadings.map((h) => h.textContent)).toEqual(
      expect.arrayContaining([expect.stringContaining('Run 1'), expect.stringContaining('Run 2')]),
    );
    // No h4 exists without an h3 above it: the only h4s are inside a run group or
    // inside the attention block, both of which are h3-headed.
    for (const h4 of screen.queryAllByRole('heading', { level: 4 })) {
      expect(h4.closest('.vr-unit, .vr-attention')).not.toBeNull();
    }
  });

  it('the live region is one node that survives a re-check', async () => {
    mount({
      [`POST ${P('/validate')}`]: { body: validateBody([verdict()]) },
      [`GET ${P('/warnings')}`]: { body: warningsBody() },
      [`GET ${P('/evidence-classification')}`]: { body: NO_CLASSIFICATION },
    });
    const before = screen.getByRole('status');
    press();
    await screen.findByText(/1 run checked/);
    // The SAME element, re-texted — not a new one mounted with its content, which
    // is generally not announced at all.
    expect(screen.getByRole('status')).toBe(before);
  });

  it('every state is carried by a word, not only by a colour', async () => {
    mount({
      [`POST ${P('/validate')}`]: {
        body: validateBody([
          verdict({ run_id: 'RUN-1', run_label: 'Run 1', record_id: 'REC-1', ok: true }),
          verdict({
            run_id: 'RUN-2',
            run_label: 'Run 2',
            record_id: 'REC-2',
            ok: false,
            errors: [{ path: '$', message: 'nope' }],
          }),
          verdict({
            run_id: 'RUN-3',
            run_label: 'Run 3',
            record_id: 'REC-3',
            ok: false,
            unavailable: true,
            errors: [UNAVAILABLE_ERROR],
          }),
        ]),
      },
      [`GET ${P('/warnings')}`]: { body: warningsBody() },
      [`GET ${P('/evidence-classification')}`]: { body: NO_CLASSIFICATION },
    });
    press();
    await screen.findByText(/3 runs checked/);
    expect(within(unitEl('RUN-1')).getByText('Passed')).toBeTruthy();
    expect(within(unitEl('RUN-2')).getByText('Failed')).toBeTruthy();
    expect(within(unitEl('RUN-3')).getByText('No verdict')).toBeTruthy();
  });

  it('each run’s detail button names its run, so it is unambiguous out of context', async () => {
    mount({
      [`POST ${P('/validate')}`]: {
        body: validateBody([
          verdict({ run_id: 'RUN-1', run_label: 'Run 1', record_id: 'REC-1' }),
          verdict({ run_id: 'RUN-2', run_label: 'Run 2', record_id: 'REC-2' }),
        ]),
      },
      [`GET ${P('/warnings')}`]: { body: warningsBody() },
      [`GET ${P('/evidence-classification')}`]: { body: NO_CLASSIFICATION },
    });
    press();
    await screen.findByText(/2 runs checked/);
    expect(screen.getByRole('button', { name: detailName.idle('Run 1') })).toBeTruthy();
    expect(screen.getByRole('button', { name: detailName.idle('Run 2') })).toBeTruthy();
  });

  /*
   * WCAG 2.5.3, LABEL IN NAME — asserted in every state the button has, because
   * the defect this replaces was not a missing name but a STALE one: a fixed
   * `Check {label} in detail` stayed on the button after it re-labelled itself
   * "Check This Run Again", so speech input saying the printed words missed, and
   * a screen reader announced a press that had already happened.
   *
   * The assertion is deliberately written as "the accessible name CONTAINS the
   * visible text" rather than as a literal string comparison, so it keeps testing
   * the rule and not this particular wording.
   */
  it('the detail button’s accessible name contains its visible label, in all three states', async () => {
    let release!: () => void;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    mount({
      [`POST ${P('/validate')}`]: { body: validateBody([verdict()]) },
      [`GET ${P('/warnings')}`]: { body: warningsBody() },
      [`GET ${P('/evidence-classification')}`]: { body: NO_CLASSIFICATION },
      // A whole-route thunk, held open so the third state — "Checking…" — is
      // observable at all. It is the state a reader is most likely to be sitting
      // in when they ask their screen reader what the focused control is.
      [`POST ${P('/runs/RUN-1/check')}`]: async () => {
        await held;
        return { body: checkBody() };
      },
    });
    press();
    await screen.findByText(/1 run checked/);

    const nameContainsLabel = () => {
      const button = unitEl('RUN-1').querySelector('button')!;
      const visible = (button.textContent ?? '').trim();
      const accessible = button.getAttribute('aria-label') ?? '';
      expect(visible).not.toBe('');
      expect(accessible).toContain(visible);
      // And it still says WHICH run, which is why an `aria-label` is here at all.
      expect(accessible).toContain('Run 1');
      return visible;
    };

    expect(nameContainsLabel()).toBe('Check This Run In Detail');
    pressDetail();
    await waitFor(() => expect(nameContainsLabel()).toBe('Checking…'));
    release();
    await waitFor(() => expect(nameContainsLabel()).toBe('Check This Run Again'));
  });
});

// --- 8. a record with no runs is one unit, and is not given an invented run ---

describe('a record with no runs', () => {
  /** `post_validate`'s non-fan-out branch: one verdict, and no `runs` key at all. */
  const NO_RUNS_VALIDATE = {
    ok: true,
    errors: [],
    schema: 'ISAAC v1.05',
    dry_run: true,
  } satisfies ApiValidateResult;

  /**
   * `_warnings_payload`'s non-fan-out shape, WITH ADVICE IN IT.
   *
   * The two codes are the ones the five canonical seed records actually produce
   * — `NO_LINKS` and `NO_MEASUREMENT_SERIES` — and the missing `runs` key is the
   * whole point of the fixture: on this shape there is no per-unit entry, so
   * `adviceFor` can attribute nothing, while the server plainly did report
   * advisory warnings. An `warnings: []` fixture cannot show the difference,
   * which is why the original test could not catch what this one does.
   */
  const NO_RUNS_WARNINGS: ApiWarningsResponse = {
    advisory: true,
    gating: false,
    warnings: [
      { code: 'NO_LINKS', where: 'links', message: 'This record declares no links.' },
      {
        code: 'NO_MEASUREMENT_SERIES',
        where: 'measurement',
        message: 'This record declares no measurement series.',
      },
    ],
    dry_run: true,
  };

  async function renderNoRuns(warnings: ApiWarningsResponse) {
    mount({
      [`POST ${P('/validate')}`]: { body: NO_RUNS_VALIDATE },
      [`GET ${P('/warnings')}`]: { body: warnings },
      [`GET ${P('/evidence-classification')}`]: { body: NO_CLASSIFICATION },
    });
    press();
    await screen.findByText(/1 record checked/);
    return document.querySelector('.vr-unit') as HTMLElement;
  }

  it('is checked as one unit, with no per-run detail offered', async () => {
    const unit = await renderNoRuns({ advisory: true, gating: false, warnings: [] });
    expect(screen.getByText('This record')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /detail/i })).toBeNull();
    expect(unit.querySelector('.vr-unit-counts')!.textContent).toContain(
      'no per-run detail to check',
    );
    /*
     * NO `null` WAS INTERPOLATED INTO A LABEL OR AN ID LINE — asserted
     * structurally, because the old form (`document.body.textContent` does not
     * contain the substring "null") passes on almost any DOM and so could not
     * fail for the reason it was written. With no run id and no per-unit record
     * id there is no id line to render AT ALL, and the label is a real phrase.
     */
    expect(unit.querySelector('.vr-unit-ids')).toBeNull();
    expect(unit.querySelector('.vr-unit-label')!.textContent).toBe('This record');
    expect(unit.textContent).not.toMatch(/\bnull\b/);
  });

  /*
   * THE FALSE AFFIRMATIVE ZERO. `_warnings_payload` sends no `runs` key here, and
   * `reviewUnits` gives the synthesized unit a null `record_id`, so `adviceFor`
   * returns `undefined` — correctly, because the top-level list is an aggregate
   * over units and attributing it to one unit is a claim the response does not
   * make. What was WRONG was rendering that refusal as `0 advisory notes`: on
   * every record a scientist can currently open (all five seeds have no runs and
   * one or two real advisory warnings each) the screen asserted zero while the
   * server had reported some.
   *
   * The last two expectations are the NEGATIVE CONTROL: restore
   * `count(adviceCount ?? 0, 'advisory note')` in `unitCounts` and they fail.
   */
  it('does NOT claim zero advisory notes when the server reported some it cannot attribute', async () => {
    const unit = await renderNoRuns(NO_RUNS_WARNINGS);
    const counts = unit.querySelector('.vr-unit-counts')!.textContent ?? '';
    expect(counts).toContain('not attributable to this unit');
    expect(counts).toContain('not the same as none');
    expect(counts).not.toContain('0 advisory note');
    expect(document.body.textContent).not.toContain('0 advisory notes');
  });

  /*
   * ...AND IT DOES NOT INVENT A NUMBER EITHER. Refusing to attribute is not the
   * same as adopting the aggregate: the two top-level warnings above must not
   * reappear as "2 advisory notes" on the one unit, and neither warning's text
   * may be rendered under it as though the server had placed it there.
   */
  it('does not adopt the record-level aggregate as this unit’s own advice', async () => {
    const unit = await renderNoRuns(NO_RUNS_WARNINGS);
    expect(unit.querySelector('.vr-unit-counts')!.textContent).not.toContain('2 advisory notes');
    expect(unit.querySelector('.vr-advisory')).toBeNull();
    expect(unit.textContent).not.toContain('NO_LINKS');
  });

  /*
   * THE POLARITY TWIN, and the reason the coverage clause is not simply always
   * printed: where the server DOES attribute advice to a unit, a real count is
   * rendered and the coverage clause is absent.
   */
  it('a unit the server DID attribute advice to gets a number, not the coverage clause', async () => {
    mount({
      [`POST ${P('/validate')}`]: { body: validateBody([verdict()]) },
      [`GET ${P('/warnings')}`]: {
        body: warningsBody([
          {
            run_id: 'RUN-1',
            run_label: 'Run 1',
            record_id: 'REC-1',
            warnings: [
              { code: 'NO_LINKS', where: 'links', message: 'This record declares no links.' },
            ],
            dry_run: true,
          },
        ]),
      },
      [`GET ${P('/evidence-classification')}`]: { body: NO_CLASSIFICATION },
    });
    press();
    await screen.findByText(/1 run checked/);
    const counts = unitEl('RUN-1').querySelector('.vr-unit-counts')!.textContent ?? '';
    expect(counts).toContain('1 advisory note');
    expect(counts).not.toContain('not attributable');
  });
});

// --- 9. nothing on this surface mutates --------------------------------------

describe('read-only', () => {
  it('every request is a validation read; nothing is written, exported or answered', async () => {
    const calls = mount({
      [`POST ${P('/validate')}`]: { body: validateBody([verdict()]) },
      [`GET ${P('/warnings')}`]: { body: warningsBody() },
      [`GET ${P('/evidence-classification')}`]: { body: NO_CLASSIFICATION },
      [`POST ${P('/runs/RUN-1/check')}`]: { body: checkBody() },
    });
    press();
    await screen.findByText(/1 run checked/);
    pressDetail();
    await screen.findByText(/This run has no open questions/);
    expect(calls).toEqual([
      `POST ${P('/validate')}`,
      `GET ${P('/warnings')}`,
      `GET ${P('/evidence-classification')}`,
      `POST ${P('/runs/RUN-1/check')}`,
    ]);
    for (const forbidden of ['/export', '/answers', '/edit', '/runs/RUN-1/edit', '/demo/reset']) {
      expect(calls.some((c) => c.includes(forbidden))).toBe(false);
    }
    // Said at section level AND again on the per-run detail, deliberately: a
    // reader who scrolled straight to one run's findings never saw the first.
    expect(screen.getAllByText(/Read-only/)).toHaveLength(2);
  });
});
