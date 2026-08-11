import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import { RunFindings, runFindingState } from '../components/RunFindings';
import { exportReadyRoutes, fanOutExportedRoutes, stubFetchRoutes } from '../test/apiFixtures';
import type { ApiValidateResult, ApiWarningsResponse } from '../lib/types';

/*
 * PHASE 15 · Validate & Review, grouped BY RUN.
 *
 * WHAT WAS MISSING, MEASURED. `POST /api/experiments/{id}/validate` has returned
 * per-run verdicts since the C6/F1 fan-out fix (`routes.py::post_validate` ->
 * `_fan_out_official_verdict` -> `_validate_unit`), and `lib/types.ts` has
 * declared them. Nothing in the frontend read them: on `d17a827`,
 * `rg --text -n 'validate\.runs|\.runs\?\.' apps/web/src` returned two hits, BOTH
 * inside `types.ts`. `ExportReadiness` rendered the flat `errors` list, which is
 * deliberately only the FIRST FAILING unit's errors — so on a five-run record a
 * reader saw one run's schema errors with nothing saying which run they belonged
 * to, and no route to the other four.
 *
 * THE PROPERTIES THIS FILE PINS. Each has a NEGATIVE CONTROL that was EXECUTED —
 * the source was broken, this file run, the named assertion observed failing, and
 * the source restored (byte-compared against a backup). The observed messages are
 * quoted verbatim.
 *
 * THE DENOMINATOR IS 39, MEASURED. An earlier revision of this header reported
 * "of 30" against a file that held 31, and put NC3 at 17 when it was 18 — counts
 * carried forward rather than read off a run. Every figure below was read from
 * the run that produced it: `Tests  N failed | M passed (39)`.
 *
 *  NC1 · key a run's row on `ok` alone (replace `runFindingState`'s non-pass
 *        branch with a bare `return 'fail'`, deleting BOTH the `unavailable`
 *        flag read and the `isValidationUnavailable` fallback).
 *        9 of 39 failed. The named one:
 *        "an unavailable run is NOT rendered as a schema failure" ->
 *        `Unable to find an element with the text: No verdict`; the run rendered
 *        `Failed` instead. And the tally: `expected '2 runs: 1 passed · 1 did not
 *        pass.' to be '2 runs: 1 passed · 1 could not be checked.'` — a schema
 *        failure claimed over an entry on which the server refused to give a
 *        verdict at all. This is the exact defect `unavailable: true` was added
 *        to `_validate_unit` to fix (routes.py, the `_validate_unit` comment).
 *
 *  NC2 · fold the advisory count into the state (`'fail'` when a run at that
 *        position carries warnings). 2 of 39 failed:
 *        "an advisory warning never turns a PASS into a FAIL" ->
 *        `Unable to find an element with the text: Passed`, and
 *        "the tally counts runs by verdict state" ->
 *        `expected '1 run: 1 did not pass.' to be '1 run: 1 passed.'`.
 *        Advisory is `advisory: true, gating: false`, hardcoded server-side.
 *
 *        SCOPE, corrected: the tally assertion is a "second, independent"
 *        assertion only for a break located in `states`, which is what this
 *        control breaks. An independent reviewer broke the ROW state alone,
 *        leaving `states` intact — 1 of 31 failed and the tally test did not
 *        catch it. The two assertions share `states`; they are independent of
 *        each other's ELEMENT (the word vs. the count line), not of its source.
 *
 *  NC3 · render only the flat `validate.errors` (early `return null` from
 *        `RunFindings`, which is exactly what shipped). 24 of 39 failed,
 *        including the named one:
 *        "each run's errors are addressed to THAT run, verbatim" ->
 *        `no run group rendered for "Run 2"`.
 *
 * THREE FURTHER CONTROLS, for the three defects an independent review found in
 * the first version of this component. Each was executed the same way.
 *
 *  NC-F1 · restore the subject line unguarded, keyed on `dry_run` alone (the
 *        shipped defect). 1 of 39 failed — exactly the assertion added for it:
 *        "a no-verdict run claims NO document was checked — neither branch" ->
 *        `expected <p class="run-finding-subject"></p> to be null`. The old code
 *        rendered "Checked the written official record." over the
 *        materialised-UNREADABLE branch, whose `dry_run: false` means "no dry run
 *        happened", not "the written record was checked".
 *
 *  NC-F2 · read the fixed English sentence instead of the machine-readable flag
 *        (drop `run.unavailable === true ||`). 2 of 39 failed:
 *        "the `unavailable` FLAG decides, even when the sentence differs" ->
 *        `expected 'fail' to be 'unavailable'`, and
 *        "a caption that introduces findings is not written when there are none"
 *        -> `expected 'FailedRun 3 · 600 K…' to contain 'this is not a schema
 *        failure'`. Latent against today's backend only because it emits the
 *        exact literal on both branches — which is the coupling the flag removed.
 *
 *  NC-F3 · match advice by `record_id` anywhere in the list (`warningRuns.find`)
 *        instead of by position. 1 of 39 failed:
 *        "advice is never attributed to a second run that shares a record_id" ->
 *        `expected …(2) to have a length of 1 but got 2` — the same advisory
 *        block rendered under both runs.
 *
 * The polarity assertions are explicit and two-sided. A test in this repository
 * has already shipped INVERTED and passed (`upload-claim-parity.test.tsx`'s first
 * version), so "a warning does not flip a pass" is asserted alongside "a real
 * failure still reads as a failure" — a guard that only ever checks one direction
 * cannot tell a working rule from a dead one.
 */

// --- CSS source access (same pattern as no-vertical-rail / evidence-hierarchy) --
const cssFiles = import.meta.glob('../**/*.css', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;
const cssByName = (name: string): string =>
  Object.entries(cssFiles).find(([path]) => path.endsWith(`/${name}`))?.[1] ?? '';
const stripComments = (source: string): string => source.replace(/\/\*[\s\S]*?\*\//g, '');
function cssRules(source: string): { selector: string; body: string }[] {
  return [...stripComments(source).matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({
    selector: m[1].trim(),
    body: m[2],
  }));
}
const ruleFor = (file: string, selector: string) =>
  cssRules(cssByName(file)).find((r) => r.selector === selector);

type RunVerdict = NonNullable<ApiValidateResult['runs']>[number];
type RunWarnings = NonNullable<ApiWarningsResponse['runs']>[number];

/** The fixed sentinel `_validate_unit` returns when NO verdict could be produced. */
const UNAVAILABLE_ERROR = { path: '$', message: 'Validation could not be completed.' };

const PASSING: RunVerdict = {
  run_id: '01JQZ0FIXTURERUNONE000001',
  run_label: 'Run 1 · 300 K',
  record_id: '01JQZ0FIXTURERUNONE000001',
  ok: true,
  errors: [],
  dry_run: false,
};

const FAILING: RunVerdict = {
  run_id: '01JQZ0FIXTURERUNTWO000001',
  run_label: 'Run 2 · 450 K',
  record_id: '01JQZ0FIXTURERUNTWO000001',
  ok: false,
  errors: [{ path: 'measurement.series', message: "'series' is a required property" }],
  dry_run: true,
};

/**
 * `_validate_unit`'s MATERIALISED-UNREADABLE branch, verbatim. Note `dry_run:
 * false` — the route's own comment reads "no dry run happened", NOT "the written
 * record was checked"; it is returned exactly because that record could not be
 * read. And `unavailable: true`, which is the field a client is supposed to key
 * on.
 */
const UNAVAILABLE: RunVerdict = {
  run_id: '01JQZ0FIXTURERUNTHREE00001',
  run_label: 'Run 3 · 600 K',
  record_id: '01JQZ0FIXTURERUNTHREE00001',
  ok: false,
  errors: [UNAVAILABLE_ERROR],
  dry_run: false,
  unavailable: true,
};

/**
 * One `warnings.runs` entry. `_fan_out_warnings_payload` builds `runs` as
 * `[_unit_warnings_entry(unit) for unit in exp.export_units()]` — ONE ENTRY PER
 * UNIT, in the same order as `/validate`'s `runs`, so the two lists are 1:1 and
 * a run with nothing to advise carries an entry with an EMPTY `warnings` list
 * rather than no entry. Fixtures here follow that shape.
 */
const ADVICE_FOR = (recordId: string): RunWarnings => ({
  run_id: recordId,
  run_label: 'ignored — matching is positional, confirmed by record_id',
  record_id: recordId,
  warnings: [{ code: 'NO_LINKS', where: 'record.links', message: 'no relationships declared' }],
  dry_run: false,
});

/** The same entry with nothing to advise — what the route emits for a clean run. */
const NO_ADVICE_FOR = (recordId: string): RunWarnings => ({
  ...ADVICE_FOR(recordId),
  warnings: [],
});

function renderFindings(runs: RunVerdict[], warningRuns?: RunWarnings[]) {
  return render(<RunFindings runs={runs} warningRuns={warningRuns} />);
}

/** Every rendered `.run-finding` group, keyed by its visible run label. */
function groupsIn(container: HTMLElement): HTMLElement[] {
  return [...container.querySelectorAll<HTMLElement>('.run-finding')];
}
function groupFor(container: HTMLElement, label: string): HTMLElement {
  const hit = groupsIn(container).find((el) => el.textContent?.includes(label));
  if (!hit) throw new Error(`no run group rendered for "${label}"`);
  return hit;
}

function renderAt(path: string) {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

afterEach(() => vi.unstubAllGlobals());

// --- 1. N runs -> N groups -----------------------------------------------------

describe('Validate & Review · one group per run', () => {
  it('renders exactly one group per run, each naming its run and its record id', () => {
    const runs = [PASSING, FAILING, UNAVAILABLE];
    const { container } = renderFindings(runs);

    expect(groupsIn(container as HTMLElement)).toHaveLength(3);
    for (const run of runs) {
      const group = groupFor(container as HTMLElement, run.run_label!);
      // The identifiers are what make a finding addressable — the whole point of
      // the grouping. Both are asserted, not just the label.
      expect(group.textContent).toContain(run.run_id!);
      expect(group.textContent).toContain(run.record_id);
    }
  });

  it('the count line is a grounded tally — never a percentage or a readiness score', () => {
    const { getByRole } = renderFindings([PASSING, FAILING, UNAVAILABLE]);
    const summary = getByRole('status');

    expect(summary.textContent).toBe(
      '3 runs: 1 passed · 1 did not pass · 1 could not be checked.',
    );
    // No invented figure of any kind.
    expect(summary.textContent).not.toMatch(/%|complete|score|readiness/i);
  });

  it('states per run WHICH document was checked, following the server’s dry_run', () => {
    const { container } = renderFindings([PASSING, FAILING]);
    // `dry_run: false` is the strong claim that a WRITTEN record was checked, so
    // it is only made where the server made it.
    expect(groupFor(container as HTMLElement, 'Run 1').textContent).toContain(
      'Checked the written official record.',
    );
    expect(groupFor(container as HTMLElement, 'Run 2').textContent).toContain(
      'in-memory candidate record',
    );
  });

  /**
   * A LIVE FALSE CLAIM THIS FILE DID NOT COVER, and the reason the assertion is
   * on the RENDERED SENTENCE rather than on a flag.
   *
   * `dry_run` does not mean the same thing on an `unavailable` entry.
   * `_validate_unit`'s materialised-unreadable branch returns `dry_run: false`
   * with the comment "no dry run happened" — it is returned BECAUSE the written
   * record could not be read. Keying the subject line on `dry_run` alone
   * therefore rendered "Checked the written official record." over a run whose
   * record was never opened, and then contradicted it one line later with "No
   * verdict could be produced for this run". Neither unavailable branch checked
   * any document, so NO document is claimed for either.
   */
  it('a no-verdict run claims NO document was checked — neither branch', () => {
    const dryCrash: RunVerdict = { ...UNAVAILABLE, dry_run: true }; // the export-raised branch
    for (const run of [UNAVAILABLE, dryCrash]) {
      const { container } = renderFindings([run]);
      const group = groupFor(container as HTMLElement, 'Run 3');
      expect(group.querySelector('.run-finding-subject')).toBeNull();
      expect(group.textContent).not.toContain('Checked the written official record');
      expect(group.textContent).not.toContain('Checked an in-memory candidate record');
      // …and the refusal is still stated, so suppressing the line hides nothing.
      expect(group.textContent).toContain('No verdict could be produced for this run');
    }
    // POLARITY — the line is suppressed for the no-verdict state ONLY, not
    // removed. A run that really was checked still says which document.
    const checked = groupFor(
      renderFindings([PASSING]).container as HTMLElement,
      'Run 1',
    );
    expect(checked.querySelector('.run-finding-subject')!.textContent).toBe(
      'Checked the written official record.',
    );
  });

  it('a null run_label / null run_id never renders the literal "null"', () => {
    // `run_label` and `run_id` are `string | null` in the contract. Two screens
    // already shipped rendering the string `null` from this record shape
    // (`__tests__/fan-out-null-render.test.tsx`), so the absent case is pinned on
    // the RENDERED TEXT, which is the only thing that shows a template defect.
    const { container } = renderFindings([
      { ...PASSING, run_id: null, run_label: null },
    ]);
    const text = (container as HTMLElement).textContent!.toLowerCase();
    for (const marker of ['null', 'undefined', 'nan', '[object object]']) {
      expect(text, `rendered the literal "${marker}"`).not.toContain(marker);
    }
    // …and it still identifies the run by the id it DOES have.
    expect((container as HTMLElement).textContent).toContain(PASSING.record_id);
  });
});

// --- 2. a failing run is visibly distinguished --------------------------------

describe('Validate & Review · a failing run is distinguished, and owns its errors', () => {
  it('the failing run reads "Failed" while its passing sibling reads "Passed"', () => {
    const { container } = renderFindings([PASSING, FAILING]);
    const pass = groupFor(container as HTMLElement, 'Run 1');
    const fail = groupFor(container as HTMLElement, 'Run 2');

    expect(pass.getAttribute('data-state')).toBe('pass');
    expect(fail.getAttribute('data-state')).toBe('fail');
    // The state is carried by a WORD, not by colour alone (the icon is decorative).
    expect(within(pass).getByText('Passed')).toBeInTheDocument();
    expect(within(fail).getByText('Failed')).toBeInTheDocument();
    expect(pass.querySelector('.run-finding-state-fail')).toBeNull();
  });

  /**
   * NC3 — the negative control for the whole slice. Rendering only the flat
   * `validate.errors` list (which is the FIRST FAILING unit's errors) is what
   * shipped, and it cannot say which run an error belongs to. So the assertion is
   * not "the message appears somewhere" but "the message appears INSIDE that
   * run's group, and not inside the other's".
   */
  it('each run’s errors are addressed to THAT run, verbatim', () => {
    const secondFailure: RunVerdict = {
      ...UNAVAILABLE,
      ok: false,
      errors: [{ path: 'system.technique', message: "'HERFD' is not one of ['XANES', 'EXAFS']" }],
    };
    const { container } = renderFindings([PASSING, FAILING, secondFailure]);
    const two = groupFor(container as HTMLElement, 'Run 2');
    const three = groupFor(container as HTMLElement, 'Run 3');

    // Verbatim, not paraphrased: a friendlier restatement would change what the
    // validator said.
    expect(two.textContent).toContain("'series' is a required property");
    expect(two.textContent).toContain('measurement.series');
    expect(three.textContent).toContain("'HERFD' is not one of ['XANES', 'EXAFS']");
    expect(three.textContent).toContain('system.technique');

    // …and NOT each other's. This is the half a flat list cannot satisfy.
    expect(two.textContent).not.toContain('system.technique');
    expect(three.textContent).not.toContain('measurement.series');
    // A passing run shows no error list at all.
    expect(groupFor(container as HTMLElement, 'Run 1').querySelector('.run-finding-errors')).toBeNull();
  });

  /**
   * AN HONESTY DEFECT THIS FILE CAUGHT IN ITS OWN FIRST DRAFT. The caption read
   * "Official ISAAC schema errors reported for this run" for EVERY failing run.
   * That is false for a dry-run unit: `_validate_unit` returns
   * `export_draft(...)`'s result, and when the export never reached the official
   * validator (`official_report is None`) the errors it returns are the
   * NO-GUESSING DRAFT report's. Both arrive as `{path, message}`, so the wire
   * carries no discriminator — which means the source can only be named for a
   * MATERIALISED unit, where `validate_official` is what ran.
   */
  it('names the official schema as the source ONLY where the server’s own field allows it', () => {
    const written: RunVerdict = { ...FAILING, dry_run: false };
    const dry: RunVerdict = { ...FAILING, dry_run: true };

    const writtenCaption = groupFor(
      renderFindings([written]).container as HTMLElement,
      'Run 2',
    ).querySelector('.run-finding-caption')!.textContent!;
    const dryCaption = groupFor(
      renderFindings([dry]).container as HTMLElement,
      'Run 2',
    ).querySelector('.run-finding-caption')!.textContent!;

    // dry_run: false — `validate_official` ran, so the source is named.
    expect(writtenCaption).toMatch(/Official ISAAC schema errors/);
    // dry_run: true — the source is UNKNOWN from the response, and the copy says
    // so instead of asserting one. This is the polarity that matters: the guard
    // must fail if the caption ever hard-codes the official schema again.
    expect(dryCaption).not.toMatch(/^Official ISAAC schema errors/);
    expect(dryCaption).toMatch(/does not record which findings came from/);
    // …in the screen's own vocabulary. "The response" is API vocabulary on a
    // product screen (CLAUDE.md §11) and the earlier draft used it here.
    expect(dryCaption).not.toMatch(/\bthe response\b/i);
    // …and the findings themselves are still shown verbatim in both cases.
    expect(groupFor(renderFindings([dry]).container as HTMLElement, 'Run 2').textContent).toContain(
      "'series' is a required property",
    );
  });
});

// --- 3. `unavailable` is NOT `ok: false` -------------------------------------

describe('Validate & Review · "no verdict" is not a schema failure (NC1)', () => {
  it('an unavailable run is NOT rendered as a schema failure', () => {
    const { container } = renderFindings([UNAVAILABLE]);
    const group = groupFor(container as HTMLElement, 'Run 3');

    // The state word — this is the assertion NC1 breaks.
    expect(within(group).getByText('No verdict')).toBeInTheDocument();
    expect(group.getAttribute('data-state')).toBe('unavailable');
    expect(within(group).queryByText('Failed')).toBeNull();
    expect(group.querySelector('.run-finding-state-fail')).toBeNull();
    // …and it SAYS so, rather than leaving a reader to infer it.
    expect(group.textContent).toContain('this is not a schema failure');
    // The server's own sentence is still shown — the refusal is not hidden —
    // and it is introduced, so the reader knows whose words follow.
    expect(group.textContent).toContain('this is not a schema failure. What the check reported:');
    expect(group.textContent).toContain(UNAVAILABLE_ERROR.message);
  });

  it('the count line calls it "could not be checked", never "failed"', () => {
    const { getByRole } = renderFindings([PASSING, UNAVAILABLE]);
    expect(getByRole('status').textContent).toBe('2 runs: 1 passed · 1 could not be checked.');
  });

  it('POLARITY — a genuine schema failure still reads as a failure', () => {
    // The guard above must not have been bought by never saying "Failed" at all.
    const { container, getByRole } = renderFindings([FAILING]);
    expect(within(groupFor(container as HTMLElement, 'Run 2')).getByText('Failed')).toBeInTheDocument();
    expect(getByRole('status').textContent).toBe('1 run: 1 did not pass.');
  });

  it('runFindingState reads the server’s fields and nothing else', () => {
    expect(runFindingState(PASSING)).toBe('pass');
    expect(runFindingState(FAILING)).toBe('fail');
    expect(runFindingState(UNAVAILABLE)).toBe('unavailable');
    // A server PASS is a pass regardless of anything else on the entry.
    expect(runFindingState({ ...UNAVAILABLE, ok: true })).toBe('pass');
    expect(runFindingState({ ...UNAVAILABLE, ok: true, unavailable: true })).toBe('pass');
  });

  /**
   * THE MACHINE-READABLE FLAG IS THE SIGNAL, and this is the assertion that says
   * so. `unavailable` was added to `_validate_unit` precisely because the fixed
   * English sentence in `errors[0].message` was the only thing a client could
   * key on — so keying on that sentence is keying on the very coupling the flag
   * removed. One comma in the message and the server's explicit refusal renders
   * as `Failed`: a schema verdict over an entry on which no verdict was given.
   * `RunCard` already reads the flag (`data.official?.unavailable === true`).
   */
  it('the `unavailable` FLAG decides, even when the sentence differs', () => {
    const reworded: RunVerdict = {
      ...UNAVAILABLE,
      unavailable: true,
      errors: [{ path: '$', message: 'Validation could not be completed (record unreadable).' }],
    };
    expect(runFindingState(reworded)).toBe('unavailable');

    const group = groupFor(renderFindings([reworded]).container as HTMLElement, 'Run 3');
    expect(group.getAttribute('data-state')).toBe('unavailable');
    expect(within(group).getByText('No verdict')).toBeInTheDocument();
    expect(within(group).queryByText('Failed')).toBeNull();
    // The server's own sentence is shown verbatim whatever it says.
    expect(group.textContent).toContain('Validation could not be completed (record unreadable).');
  });

  it('the sentence remains a live FALLBACK when the flag is absent', () => {
    // A response that predates `unavailable` — or any path that omits it —
    // still must not read as a schema failure. Keeping this asserted is what
    // stops the helper becoming dead code that no longer works.
    const flagless: RunVerdict = { ...UNAVAILABLE };
    delete (flagless as { unavailable?: boolean }).unavailable;
    expect('unavailable' in flagless).toBe(false);
    expect(runFindingState(flagless)).toBe('unavailable');

    const group = groupFor(renderFindings([flagless]).container as HTMLElement, 'Run 3');
    expect(within(group).getByText('No verdict')).toBeInTheDocument();
  });

  it('POLARITY — neither signal makes a real schema failure a no-verdict', () => {
    // The two guards above must not have been bought by never saying "Failed".
    expect(runFindingState({ ...FAILING, unavailable: false })).toBe('fail');
    expect(runFindingState(FAILING)).toBe('fail');
    // …including a failure whose message merely MENTIONS the sentinel wording.
    expect(
      runFindingState({
        ...FAILING,
        errors: [{ path: '$', message: 'Validation could not be completed for two of five units.' }],
      }),
    ).toBe('fail');
  });

  /**
   * DEFENSIVE, and stated as such: `{ok: false, errors: []}` is NOT reachable
   * through this API — `export_draft` returns `official_report=None` only when
   * `not draft_report.ok`, and `OfficialReport.ok` is `not self.errors`. The
   * captions both end in a colon, so a caption with nothing after it would be a
   * dangling promise on a validation screen.
   */
  it('a caption that introduces findings is not written when there are none', () => {
    const noErrors = groupFor(
      renderFindings([{ ...FAILING, errors: [] }]).container as HTMLElement,
      'Run 2',
    );
    expect(noErrors.querySelector('.run-finding-caption')).toBeNull();
    expect(noErrors.textContent).not.toContain('Findings reported for this run');
    expect(noErrors.textContent).not.toMatch(/:\s*$/);

    const noVerdict = groupFor(
      renderFindings([{ ...UNAVAILABLE, errors: [] }]).container as HTMLElement,
      'Run 3',
    );
    // The refusal is still stated — only the lead-in to an empty list is dropped.
    expect(noVerdict.textContent).toContain('this is not a schema failure');
    expect(noVerdict.textContent).not.toContain('What the check reported');
  });
});

// --- 4. advisory never flips a verdict ---------------------------------------

describe('Validate & Review · advisory is separate and non-gating (NC2)', () => {
  it('an advisory warning never turns a PASS into a FAIL', () => {
    const { container, getByRole } = renderFindings(
      [PASSING],
      [ADVICE_FOR(PASSING.record_id)],
    );
    const group = groupFor(container as HTMLElement, 'Run 1');

    // The verdict half — unchanged by the presence of advice.
    expect(within(group).getByText('Passed')).toBeInTheDocument();
    expect(group.getAttribute('data-state')).toBe('pass');
    expect(within(group).queryByText('Failed')).toBeNull();
    expect(getByRole('status').textContent).not.toMatch(/failed/i);
  });

  it('the tally counts runs by verdict state, and never counts a warning', () => {
    // A SECOND, independent assertion on NC2 — the one above stops at the state
    // word, so without this the count line would be unguarded if that word ever
    // stopped being the thing that broke.
    const { getByRole } = renderFindings([PASSING], [ADVICE_FOR(PASSING.record_id)]);
    expect(getByRole('status').textContent).toBe('1 run: 1 passed.');
    expect(getByRole('status').textContent).not.toMatch(/warning|advisor/i);
  });

  it('the advisory block is visually and semantically separate, and says it is non-gating', () => {
    const { container } = renderFindings([PASSING], [ADVICE_FOR(PASSING.record_id)]);
    const group = groupFor(container as HTMLElement, 'Run 1');
    const advisory = group.querySelector('.run-finding-advisory')!;

    expect(advisory).not.toBeNull();
    expect(advisory.textContent).toMatch(/non-gating/);
    expect(advisory.textContent).toContain('[NO_LINKS]');
    expect(advisory.textContent).toContain('no relationships declared');
    // It is NOT inside the state chip or the schema-error list.
    expect(advisory.querySelector('.run-finding-state')).toBeNull();
    expect(group.querySelector('.run-finding-errors')).toBeNull();
    // …and it never borrows the reserved verdict presentation.
    expect(group.querySelector('.verdict-fail')).toBeNull();
    expect(group.querySelector('.verdict-pass')).toBeNull();
  });

  it('advice is matched to its OWN run, and a run with none shows none', () => {
    // The wire shape: one entry per unit, in order, the clean run's empty.
    const { container } = renderFindings(
      [PASSING, FAILING],
      [NO_ADVICE_FOR(PASSING.record_id), ADVICE_FOR(FAILING.record_id)],
    );
    expect(
      groupFor(container as HTMLElement, 'Run 1').querySelector('.run-finding-advisory'),
    ).toBeNull();
    expect(
      groupFor(container as HTMLElement, 'Run 2').querySelector('.run-finding-advisory'),
    ).not.toBeNull();
  });

  it('POLARITY — a failing run with NO advice still reads as a failure', () => {
    // Symmetry with the assertion above: if the advisory branch were what produced
    // "Failed", this would break.
    const { container } = renderFindings([FAILING], []);
    const group = groupFor(container as HTMLElement, 'Run 2');
    expect(within(group).getByText('Failed')).toBeInTheDocument();
    expect(group.querySelector('.run-finding-advisory')).toBeNull();
  });

  it('absent warnings.runs is a valid state — no advice, no claim', () => {
    const { container } = renderFindings([PASSING, FAILING], undefined);
    expect((container as HTMLElement).querySelectorAll('.run-finding-advisory')).toHaveLength(0);
  });

  /**
   * ADVICE IS MATCHED BY POSITION, THEN CONFIRMED BY `record_id`.
   *
   * Both lists come from `exp.export_units()` in the same order, so position is
   * the primary key. A `find` on `record_id` alone attached the SAME advisory
   * block to every entry sharing a `record_id` — and to both entries when two
   * runs carry `''`. That shape is not reachable through the API today
   * (`workspace.py` drops empty/duplicate run ids on load, `add_run` refuses
   * duplicates, and `record_id == unit.target_id == run.id`), so this pins a
   * guard against a WRONG ATTRIBUTION on a validation screen, not a live bug.
   */
  it('advice is never attributed to a second run that shares a record_id', () => {
    const a: RunVerdict = { ...PASSING, run_id: 'R1', run_label: 'Run A', record_id: 'SAME' };
    const b: RunVerdict = { ...PASSING, run_id: 'R2', run_label: 'Run B', record_id: 'SAME' };
    const { container } = renderFindings([a, b], [ADVICE_FOR('SAME')]);

    // Exactly ONE advisory block, and it belongs to the run at that position.
    expect((container as HTMLElement).querySelectorAll('.run-finding-advisory')).toHaveLength(1);
    expect(groupFor(container as HTMLElement, 'Run A').querySelector('.run-finding-advisory')).not.toBeNull();
    expect(groupFor(container as HTMLElement, 'Run B').querySelector('.run-finding-advisory')).toBeNull();
  });

  it('a positional entry naming a DIFFERENT record shows no advice at all', () => {
    // Position agrees, `record_id` does not — so nothing is shown, rather than
    // another run's advice being attached to this one.
    const { container } = renderFindings([PASSING], [ADVICE_FOR('01JQZSOMEOTHERRECORD0001')]);
    expect((container as HTMLElement).querySelectorAll('.run-finding-advisory')).toHaveLength(0);
  });

  it('a shorter warnings.runs leaves the trailing runs with no advice', () => {
    const { container } = renderFindings([PASSING, FAILING], [ADVICE_FOR(PASSING.record_id)]);
    expect(groupFor(container as HTMLElement, 'Run 1').querySelector('.run-finding-advisory')).not.toBeNull();
    expect(groupFor(container as HTMLElement, 'Run 2').querySelector('.run-finding-advisory')).toBeNull();
  });
});

// --- 5. the real screen, and the zero-run regression guard -------------------

describe('Export Readiness · the section renders on the real screen', () => {
  /** `exportReadyRoutes` with a fan-out validate body (and its warnings twin). */
  function withRunsRoutes(id: string) {
    const base = `/api/experiments/${id}`;
    return {
      ...exportReadyRoutes(id),
      [`POST ${base}/validate`]: {
        body: {
          // Verbatim `_fan_out_official_verdict` shape: `errors` is the FIRST
          // FAILING unit's, which is precisely why `runs[]` is needed.
          ok: false,
          errors: FAILING.errors,
          schema: 'ISAAC v1.05',
          dry_run: true,
          runs: [PASSING, FAILING, UNAVAILABLE],
        },
      },
      [`GET ${base}/warnings`]: {
        body: {
          advisory: true,
          gating: false,
          warnings: ADVICE_FOR(FAILING.record_id).warnings,
          dry_run: true,
          // 1:1 with `runs` above, in `export_units()` order — the shape
          // `_fan_out_warnings_payload` actually returns.
          runs: [
            NO_ADVICE_FOR(PASSING.record_id),
            ADVICE_FOR(FAILING.record_id),
            NO_ADVICE_FOR(UNAVAILABLE.record_id),
          ],
        },
      },
    };
  }

  it('a pre-export record with runs shows the per-run groups under the gate', async () => {
    stubFetchRoutes(withRunsRoutes('demo'));
    const view = renderAt('/record/demo/export');

    expect(await view.findByText('Findings by Run')).toBeInTheDocument();
    const container = view.container as HTMLElement;
    expect(groupsIn(container)).toHaveLength(3);
    // The existing flat gate section is untouched and still renders…
    expect(view.getByText('Would Not Validate Yet')).toBeInTheDocument();
    // …and the per-run detail follows it in document order (summary before detail).
    const gate = container.querySelector('.preexport-blocked')!;
    const findings = container.querySelector('.run-findings')!;
    expect(gate.compareDocumentPosition(findings) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // The unavailable run is not presented as a schema failure on the real screen.
    expect(groupFor(container, 'Run 3').getAttribute('data-state')).toBe('unavailable');
  });

  it('a post-export fan-out shows the groups after the reserved verdict', async () => {
    const base = '/api/experiments/demo';
    stubFetchRoutes({
      ...fanOutExportedRoutes('demo'),
      [`POST ${base}/validate`]: {
        body: {
          ok: true,
          errors: [],
          schema: 'ISAAC v1.05',
          dry_run: false,
          runs: [PASSING, { ...FAILING, ok: true, errors: [], dry_run: false }],
        },
      },
    });
    const view = renderAt('/record/demo/export');

    expect(await view.findByText('Findings by Run')).toBeInTheDocument();
    const container = view.container as HTMLElement;
    expect(groupsIn(container)).toHaveLength(2);
    // The reserved verdict still owns the gate presentation, and comes first.
    const verdict = container.querySelector('.verdict')!;
    const findings = container.querySelector('.run-findings')!;
    expect(verdict.compareDocumentPosition(findings) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // The section does not add a second verdict presentation.
    expect(findings.querySelector('.verdict')).toBeNull();
  });

  /**
   * THE REGRESSION GUARD. A zero-run record — how every record starts, and how it
   * stays until a run is added through `POST /api/experiments/{experiment_id}/runs`
   * — must render exactly what it rendered before this slice. `validate` carries no
   * `runs` key at all there, so the gate is the absence of the prop.
   *
   * (This read "every record this API can currently create". True when written,
   * false since #109 added the run-creation route.)
   */
  it('REGRESSION — a zero-run experiment renders exactly as before', async () => {
    stubFetchRoutes(exportReadyRoutes('demo'));
    const view = renderAt('/record/demo/export');

    await view.findByText('Export Official Record + Sidecar');
    const container = view.container as HTMLElement;
    expect(container.querySelector('.run-findings')).toBeNull();
    expect(groupsIn(container)).toHaveLength(0);
    expect(view.queryByText('Findings by Run')).toBeNull();
    // The pre-export surface it has always shown is intact.
    expect(view.getByText('dry-run · would validate')).toBeInTheDocument();
    expect(container.querySelector('.preexport-ready')).not.toBeNull();
  });

  it('A11Y — the section is a NAMED region, has a real h2, and skips no heading level', async () => {
    stubFetchRoutes(withRunsRoutes('demo'));
    const view = renderAt('/record/demo/export');
    await view.findByText('Findings by Run');
    const container = view.container as HTMLElement;

    // A named region: an unnamed <section> is not exposed as one at all.
    const region = view.getByRole('region', { name: 'Findings by Run' });
    expect(region.tagName).toBe('SECTION');
    expect(region.querySelector('h2')!.textContent).toBe('Findings by Run');

    // Document order never steps DOWN by more than one level (the one shape a
    // screen reader's heading navigation cannot recover from) — the same rule
    // `heading-outline.test.tsx` enforces on the screens it covers.
    const levels = [...container.querySelectorAll('h1, h2, h3, h4, h5, h6')].map((h) =>
      Number(h.tagName[1]),
    );
    expect(levels.length).toBeGreaterThan(0);
    for (let i = 1; i < levels.length; i += 1) {
      expect(levels[i] - levels[i - 1], `h${levels[i - 1]} → h${levels[i]} (${levels.join(',')})`).toBeLessThanOrEqual(1);
    }
    // Exactly one screen-level h1 still, as A11Y-1 requires.
    expect(container.querySelectorAll('h1')).toHaveLength(1);
    // The decorative state glyphs are hidden from the accessible tree; the WORD
    // carries the state, so it is never colour- or icon-only.
    for (const chip of container.querySelectorAll('.run-finding-state')) {
      expect(chip.querySelector('svg')!.getAttribute('aria-hidden')).toBe('true');
      expect(chip.textContent!.trim().length).toBeGreaterThan(0);
    }
  });

  it('REGRESSION — an empty runs[] renders nothing either', () => {
    // A defensive edge the screen guard and the component guard BOTH cover, so
    // neither can be removed on the assumption that the other holds.
    const { container } = renderFindings([]);
    expect(container.querySelector('.run-findings')).toBeNull();
  });
});

// --- 6. responsive: long strings wrap, the page never scrolls sideways -------

describe('Validate & Review · CSS source: unbounded strings wrap (320px)', () => {
  // jsdom applies no layout, so the responsive contract is asserted at its
  // source, the same way `evidence-hierarchy` and `graph-declutter` do. Every
  // selector here holds content of unbounded length with no spaces to break at:
  // a ULID, a run label, a jsonschema message, an advisory message.
  it.each([
    '.run-findings-summary',
    '.run-finding-label',
    '.run-finding-ids',
    '.run-finding-errors li',
    '.run-finding-advisory-caption',
    '.run-finding-advisory-list li',
  ])('%s wraps instead of widening the page', (selector) => {
    const rule = ruleFor('run-findings.css', selector);
    expect(rule, `${selector} must be declared`).toBeDefined();
    expect(rule!.body, `${selector} must wrap`).toContain('overflow-wrap: anywhere');
    // break-all splits mid-token even where unnecessary; the repo uses `anywhere`.
    expect(rule!.body).not.toMatch(/word-break\s*:\s*break-all/);
  });

  it('the header row wraps and its label can shrink inside the flex row', () => {
    expect(ruleFor('run-findings.css', '.run-finding-head')!.body).toContain('flex-wrap: wrap');
    expect(ruleFor('run-findings.css', '.run-finding-head')!.body).toContain('min-width: 0');
    expect(ruleFor('run-findings.css', '.run-finding-label')!.body).toContain('min-width: 0');
  });

  it('nothing in the file forces a horizontal overflow or a fixed width', () => {
    const css = stripComments(cssByName('run-findings.css'));
    expect(css).not.toMatch(/white-space\s*:\s*nowrap/);
    expect(css).not.toMatch(/overflow-x\s*:\s*scroll/);
    expect(css).not.toMatch(/(?:^|[\s;{])width\s*:\s*\d/);
  });

  it('the reserved verdict treatment is not borrowed, and no vertical rail is added', () => {
    const css = stripComments(cssByName('run-findings.css'));
    // The filled green/red verdict tokens belong to VerdictCard alone. `--fail-text`
    // on the FAIL word is text colour beside a word and an icon, never a fill.
    expect(css).not.toMatch(/--pass-/);
    expect(css).not.toMatch(/background:\s*var\(--fail-/);
    // No colored border-left/right (the system-wide no-vertical-rail rule).
    for (const line of css.split('\n')) {
      if (/border-(?:left|right)(?:-color)?\s*:/.test(line)) {
        expect(line, `colored vertical rail: ${line.trim()}`).toMatch(/--border|transparent|currentColor/);
      }
    }
  });
});
