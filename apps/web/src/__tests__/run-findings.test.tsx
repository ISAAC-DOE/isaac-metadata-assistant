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
 * THE THREE PROPERTIES THIS FILE PINS. Each has a NEGATIVE CONTROL that was
 * EXECUTED — the source was broken, the suite run, the named assertion observed
 * failing, and the source restored. The observed messages are quoted verbatim.
 *
 *  NC1 · key a run's row on `ok` alone (replace `runFindingState`'s body with
 *        `run.ok ? 'pass' : 'fail'`, deleting the `isValidationUnavailable`
 *        branch). 5 of 30 tests failed. The named one:
 *        "an unavailable run is NOT rendered as a schema failure" ->
 *        `Unable to find an element with the text: No verdict`; the run rendered
 *        `Failed` instead. And the tally: `expected '2 runs: 1 passed · 1 did not
 *        pass.' to be '2 runs: 1 passed · 1 could not be checked.'` — a schema
 *        failure claimed over an entry on which the server refused to give a
 *        verdict at all. This is the exact defect `unavailable: true` was added
 *        to `_validate_unit` to fix (routes.py, the `_validate_unit` comment).
 *
 *  NC2 · fold the advisory count into the state (`'fail'` when a passing run
 *        carries warnings). 2 of 30 failed:
 *        "an advisory warning never turns a PASS into a FAIL" ->
 *        `Unable to find an element with the text: Passed`, and
 *        "the tally counts runs by verdict state" ->
 *        `expected '1 run: 1 did not pass.' to be '1 run: 1 passed.'`.
 *        Advisory is `advisory: true, gating: false`, hardcoded server-side.
 *
 *  NC3 · render only the flat `validate.errors` (early `return null` from
 *        `RunFindings`, which is exactly what shipped). 17 of 30 failed,
 *        including the named one:
 *        "each run's errors are addressed to THAT run, verbatim" ->
 *        `no run group rendered for "Run 2"`.
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

const UNAVAILABLE: RunVerdict = {
  run_id: '01JQZ0FIXTURERUNTHREE00001',
  run_label: 'Run 3 · 600 K',
  record_id: '01JQZ0FIXTURERUNTHREE00001',
  ok: false,
  errors: [UNAVAILABLE_ERROR],
  dry_run: false,
};

const ADVICE_FOR = (recordId: string): RunWarnings => ({
  run_id: recordId,
  run_label: 'ignored — matching is on record_id',
  record_id: recordId,
  warnings: [{ code: 'NO_LINKS', where: 'record.links', message: 'no relationships declared' }],
  dry_run: false,
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
    expect(dryCaption).toMatch(/does not say whether a finding came from/);
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
    // The server's own sentence is still shown — the refusal is not hidden.
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
    const { container } = renderFindings(
      [PASSING, FAILING],
      [ADVICE_FOR(FAILING.record_id)],
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
          runs: [ADVICE_FOR(FAILING.record_id)],
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
   * THE REGRESSION GUARD. A zero-run record — every record this API can currently
   * create — must render exactly what it rendered before this slice. `validate`
   * carries no `runs` key at all there, so the gate is the absence of the prop.
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
