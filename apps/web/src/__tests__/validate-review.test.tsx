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
    fireEvent.click(screen.getByRole('button', { name: 'Check Run 2 in detail' }));
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
    fireEvent.click(screen.getByRole('button', { name: 'Check Run 1 in detail' }));
    const heading = await screen.findByText(/Advisory · non-gating · no-guessing notes/);
    expect(heading.textContent).toContain('1');
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
    fireEvent.click(screen.getByRole('button', { name: 'Check Run 1 in detail' }));
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
    fireEvent.click(screen.getByRole('button', { name: 'Check Run 1 in detail' }));
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
    fireEvent.click(screen.getByRole('button', { name: 'Check Run 1 in detail' }));
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
    fireEvent.click(screen.getByRole('button', { name: 'Check Run 1 in detail' }));
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
    fireEvent.click(screen.getByRole('button', { name: 'Check Run 1 in detail' }));
    await screen.findByText(/This run has no open questions/);
    expect(document.querySelector('.vr-kinds')).toBeNull();
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
    expect(screen.getByRole('button', { name: 'Check Run 1 in detail' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Check Run 2 in detail' })).toBeTruthy();
  });
});

// --- 8. a record with no runs is one unit, and is not given an invented run ---

describe('a record with no runs', () => {
  it('is checked as one unit, with no per-run detail offered', async () => {
    mount({
      [`POST ${P('/validate')}`]: {
        body: {
          ok: true,
          errors: [],
          schema: 'ISAAC v1.05',
          dry_run: true,
        } satisfies ApiValidateResult,
      },
      [`GET ${P('/warnings')}`]: { body: { advisory: true, gating: false, warnings: [] } },
      [`GET ${P('/evidence-classification')}`]: { body: NO_CLASSIFICATION },
    });
    press();
    await screen.findByText(/1 record checked/);
    expect(screen.getByText('This record')).toBeTruthy();
    expect(screen.queryByRole('button', { name: /in detail/ })).toBeNull();
    expect(document.querySelector('.vr-unit-counts')!.textContent).toContain(
      'no per-run detail to check',
    );
    // No `null` was interpolated into a label or an id line.
    expect(document.body.textContent).not.toContain('null');
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
    fireEvent.click(screen.getByRole('button', { name: 'Check Run 1 in detail' }));
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
