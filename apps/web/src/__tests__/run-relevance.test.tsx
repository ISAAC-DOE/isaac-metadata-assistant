/*
 * WHAT A RUN SHOWS, AND WHAT IT REFUSES TO SHOW.
 *
 * THE ONE ASSERTION THIS FILE EXISTS FOR: a field the contract classifies as
 * UNCLASSIFIED never becomes a control on a run. `workspace.field_level` puts the
 * six `system.configuration.*` paths and `timestamps.created_utc` in neither level
 * and its docstring says in capitals that this is a real answer rather than an
 * oversight; `RUN_WRITABLE_FIELD_PATHS` therefore excludes them and the PATCH route
 * refuses them with a typed 422. A control at one of those paths would have exactly
 * one possible outcome — a refusal — and handing a scientist one is the defect.
 *
 * IT IS TESTED THROUGH `run.fields`, WHICH IS WHERE IT COULD ACTUALLY GO WRONG. The
 * card renders `RUN_FIELDS`, a closed list; the failure mode is somebody deriving the
 * grid from the run's own draft field map instead, which is where an unclassified
 * value genuinely arrives from the extractor. So every fixture below puts the
 * unclassified paths in `run.fields` and the test asserts they still do not surface.
 *
 * ITS SECOND SUBJECT, ADDED AFTER REVIEW (§6): WHAT AN EMPTY SECTION SAYS ABOUT THE
 * RECORD. That is a no-guessing assertion rather than a layout one. Three sentences on
 * this card used to claim the record carried nothing at the addresses a run inherits,
 * for a run whose `inherited` map the server had filled — so the fixtures in §6 are
 * measured off the running app rather than composed, and a detector plus a canary keep
 * the four retired sentences from coming back.
 *
 * MUTATION-TESTED. Each load-bearing assertion here was verified by breaking the
 * component in the exact way it claims to catch and confirming the failure; the
 * mutations and their output are in the slice report. TWO standing canaries: `the
 * assertion helper itself bites` runs the path detector over a DOM that DOES contain a
 * forbidden path, and `the claim detector itself bites` runs the claim detector over
 * the four sentences this branch retired. Either detector going quiet fails its own
 * canary instead of passing the file vacuously.
 *
 * WHAT THIS FILE DOES NOT DO: it never re-derives a classification. The levels are
 * the backend's, `RUN_FIELDS` is pinned against `RUN_WRITABLE_FIELD_PATHS` by
 * `apps/api/tests/test_run_api.py`, and nothing below asserts what SHOULD be
 * run-level — only that what the app offers matches what it already decided.
 */

import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { act, configure, render, fireEvent, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { RUN_FIELDS } from '../lib/runFields';
import { __resetRunAutosaveStore } from '../lib/runAutosaveStore';
import {
  bundleRoutes,
  runFixture,
  runsPage,
  stubFetchRoutes,
  type RouteEntry,
} from '../test/apiFixtures';

configure({ asyncUtilTimeout: 5_000 });

/*
 * THE HARNESS DEADLINE, RAISED SO THE BUDGET ABOVE CAN ACTUALLY BE SPENT.
 *
 * `vite.config.ts` declares no `testTimeout`, so vitest's own per-test deadline is
 * ALSO 5,000 ms. Two equal budgets make the raised one unreachable: a `findBy*` here
 * can never spend its five seconds, because the harness kills the test at the same
 * instant — and the failure then reads `Test timed out in 5000ms`, which names neither
 * the query nor the DOM. The full argument, the CI measurements and the scaled proof
 * are written out once at `run-workspace.test.tsx:67-112` rather than five times.
 *
 * 30,000 ms is a HARNESS limit, NOT a performance claim. It is the number this
 * repository already uses for its mount-heavy suites (`run-workspace`,
 * `experiment-graph`, `evidence-graph`, `graph-real-artifact`, `memory-status`). Every
 * `find*`/`waitFor` still resolves as soon as the DOM is ready, and the strict 5,000 ms
 * default still stands in every other file of the suite.
 *
 * IT CANNOT TURN A RED ASSERTION GREEN, and that was checked rather than assumed. The
 * two budgets bound different things: `testTimeout` bounds the TEST, `asyncUtilTimeout`
 * bounds each individual `waitFor`/`findBy*`. Raising only the former gives no single
 * query one millisecond more than it already had, so a value that never arrives still
 * never arrives. This file is the easiest of the five to check: it calls `waitFor`
 * ZERO times, and its single negative assertion (`:312`, no Environment combobox on a
 * collapsed card) is a synchronous `queryByRole` no deadline can move.
 */
vi.setConfig({ testTimeout: 30_000 });

const ID = 'demo';
const BASE = `/api/experiments/${ID}`;

/**
 * PATHS THAT MUST NEVER BECOME A CONTROL, and where each one's verdict comes from.
 *
 * The first seven are `field_level`'s own unclassified set — the six
 * `system.configuration.*` fields (a scientific question this repository has no
 * answer to) and `timestamps.created_utc` (a record-creation stamp, not an inherited
 * scientific value; `docs/run-scope-decision-packet.md` §3).
 *
 * The last is different and is included deliberately: `context.electrochemistry.*`
 * sits under a run-level PREFIX, so `field_level` answers `run` for it — and it is
 * NOT in `RUN_WRITABLE_FIELD_PATHS`, because that set is the extractor's field map
 * intersected with the classification, and the extractor emits no such path. It is
 * the case that proves the filter is membership in the writable set rather than a
 * prefix test, which is the exact bug finding I2 of `90b432d` removed from the
 * backend.
 */
const NEVER_A_CONTROL = [
  'system.configuration.detector_model',
  'system.configuration.monochromator_crystal',
  'system.configuration.spectrometer_geometry',
  'system.configuration.n_scans',
  'system.configuration.proposal_id',
  'system.configuration.session_id',
  'timestamps.created_utc',
  'context.electrochemistry.voltage_V',
] as const;

const envelope = (value: unknown) => ({ value, status: 'verified', evidence: [] });

/** A run carrying every unclassified path in its OWN field map. */
const RUN_WITH_UNCLASSIFIED = runFixture({
  id: 'RUNAAA',
  label: 'Run 1',
  version: 'ra.0',
  fields: {
    'context.environment': envelope('in_situ'),
    'context.temperature_K': envelope(300),
    ...Object.fromEntries(
      NEVER_A_CONTROL.map((path) => [path, envelope(`SYNTHETIC-${path}`)]),
    ),
  },
});

/** The listing shape, with the four counts the real route always sends — see
 *  `runsPage` in `test/apiFixtures.ts` for why omitting them is not neutral. */
function runsBody(runs: unknown[]) {
  return runsPage(runs);
}

function renderRecord(extra: Record<string, RouteEntry>) {
  stubFetchRoutes({ ...bundleRoutes(ID), ...extra });
  render(
    <MemoryRouter
      initialEntries={[`/record/${ID}`]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

function cardFor(runId: string): HTMLElement {
  const el = document.querySelector(`[data-run-id="${runId}"]`);
  if (!el) throw new Error(`no run card rendered for ${runId}`);
  return el as HTMLElement;
}

async function expand(runId: string) {
  await act(async () => {
    /*
     * ANCHORED ON THE VERB, NOT THE LABEL (fix round, review finding m-8).
     * The compact row's own open control carries an `.sr-only` "Open "
     * prefix ahead of the run's label (I-3), so its accessible name begins
     * `Open Run 1 …` rather than `Run 1 …`. Role + name, not a raw
     * `.run-card-header` class query: that class matches BOTH the compact
     * row's `<button>` and the focused editor's own plain `<h3>` heading
     * (`RunCard.tsx`'s m-2 note) — this helper is only ever called while
     * COMPACT, so pinning the query to `role="button"` is a real assertion
     * rather than a coincidence, and would fail loudly if it were ever
     * called on an already-focused run instead of silently clicking a
     * heading nothing happens to.
     */
    fireEvent.click(within(cardFor(runId)).getByRole('button', { name: /^Open Run \d/ }));
  });
}

/** Mount one run, expanded. Returns its card. */
async function showRun(run: unknown, runId = 'RUNAAA'): Promise<HTMLElement> {
  renderRecord({ [`GET ${BASE}/runs`]: { body: runsBody([run]) } });
  await screen.findByRole('button', { name: /Add Run/ });
  await expand(runId);
  return cardFor(runId);
}

/**
 * THE DETECTOR. Every forbidden path, checked three ways, because a path can leak
 * into a card as visible text, as a control's accessible name, or as a form
 * element's id/name without ever being rendered as prose.
 *
 * Returns the paths it FOUND rather than asserting, so the canary below can assert
 * that it finds them when they are there.
 */
function forbiddenPathsIn(card: HTMLElement): string[] {
  const text = card.textContent ?? '';
  const controls = Array.from(card.querySelectorAll('input, select, textarea, button'));
  const controlText = controls
    .map((el) => [el.id, el.getAttribute('name'), el.getAttribute('aria-label'), el.textContent].join(' '))
    .join(' ');
  const labels = Array.from(card.querySelectorAll('label'))
    .map((el) => `${el.getAttribute('for') ?? ''} ${el.textContent ?? ''}`)
    .join(' ');
  return NEVER_A_CONTROL.filter(
    (path) => text.includes(path) || controlText.includes(path) || labels.includes(path),
  );
}

/** The section disclosure button whose visible title starts with `title`. */
function sectionButton(card: HTMLElement, title: string): HTMLButtonElement {
  const found = Array.from(card.querySelectorAll('button.run-section-header')).find((el) =>
    (el.querySelector('.run-section-title')?.textContent ?? '') === title,
  );
  if (!found) throw new Error(`no section disclosure titled ${title}`);
  return found as HTMLButtonElement;
}

beforeEach(() => {
  vi.useRealTimers();
  __resetRunAutosaveStore();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

// ---------------------------------------------------------------------------
// 1 — the relevance filter
// ---------------------------------------------------------------------------

describe('an unclassified field is never a Run control', () => {
  it('renders none of them, even when the run itself carries every one', async () => {
    const card = await showRun(RUN_WITH_UNCLASSIFIED);
    expect(forbiddenPathsIn(card)).toEqual([]);
  });

  it('renders none of their VALUES either — not in a box, not in the header line', async () => {
    const card = await showRun(RUN_WITH_UNCLASSIFIED);
    // Every fixture value is `SYNTHETIC-<path>`, so one substring covers all eight.
    expect(card.textContent ?? '').not.toContain('SYNTHETIC-');
    const boxes = Array.from(
      card.querySelectorAll<HTMLInputElement | HTMLSelectElement>('.run-fields input, .run-fields select'),
    );
    for (const box of boxes) expect(box.value).not.toContain('SYNTHETIC-');
  });

  it('offers exactly the writable set — no more controls than there are run-level paths', async () => {
    const card = await showRun(RUN_WITH_UNCLASSIFIED);
    const boxes = card.querySelectorAll('.run-fields input, .run-fields select');
    // The run carries eight extra field-map keys; the grid still holds five controls.
    expect(boxes).toHaveLength(RUN_FIELDS.length);
    for (const spec of RUN_FIELDS) {
      expect(within(card).getByText(spec.path)).toBeInTheDocument();
    }
  });

  /*
   * THE CANARY. It asserts nothing about the product: it builds a DOM that DOES
   * contain a forbidden path and checks that `forbiddenPathsIn` reports it. A
   * detector that stopped detecting — a renamed class, a `textContent` that no
   * longer reaches, a typo in the list — would make the three tests above pass
   * vacuously, and this is what fails instead.
   */
  it('the assertion helper itself bites', () => {
    const fake = document.createElement('div');
    fake.innerHTML = `
      <label for="x">Detector model</label>
      <input id="run-system.configuration.detector_model" />
      <span>timestamps.created_utc</span>`;
    expect(forbiddenPathsIn(fake).sort()).toEqual(
      ['system.configuration.detector_model', 'timestamps.created_utc'].sort(),
    );
    // …and reports nothing on a card-shaped DOM that is clean.
    const clean = document.createElement('div');
    clean.innerHTML = '<label for="y">Environment</label><input id="y" />';
    expect(forbiddenPathsIn(clean)).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// 2 — run-level fields, and the two that were held back
// ---------------------------------------------------------------------------

describe('every run-level writable field is offered', () => {
  it('renders a labelled control for each of the five, including the two added later', async () => {
    const card = await showRun(RUN_WITH_UNCLASSIFIED);
    for (const spec of RUN_FIELDS) {
      const label = spec.unit ? `${spec.label} (${spec.unit})` : spec.label;
      expect(within(card).getByLabelText(label)).toBeInTheDocument();
    }
    // The two `runFields.ts` once withheld, named so a silent removal is loud.
    expect(within(card).getByLabelText('Atmosphere')).toBeInTheDocument();
    expect(within(card).getByLabelText('Acquisition end')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 3 — progressive disclosure
// ---------------------------------------------------------------------------

describe('the run body is sections, not one dump', () => {
  it('is a real disclosure: a button with aria-expanded over the element it controls', async () => {
    const card = await showRun(RUN_WITH_UNCLASSIFIED);
    for (const title of ['Conditions for this run', 'Values this run inherits']) {
      const button = sectionButton(card, title);
      expect(button.tagName).toBe('BUTTON');
      expect(button).toHaveAttribute('aria-expanded', 'true');
      const bodyId = button.getAttribute('aria-controls');
      expect(bodyId).toBeTruthy();
      expect(document.getElementById(bodyId!)).not.toBeNull();
    }
  });

  /*
   * THE QUERY IS `byRole`, NOT `byLabelText`, and the difference is the whole point
   * of the assertion. `getByLabelText` walks the DOM and finds a control inside a
   * `hidden` subtree perfectly happily; `getByRole` computes accessibility and does
   * not. So only the role query can distinguish "collapsed" from "still exposed to a
   * screen reader while invisible on screen", which is what a collapse must never be.
   */
  it('collapsing a section takes its controls out of the accessibility tree', async () => {
    const card = await showRun(RUN_WITH_UNCLASSIFIED);
    expect(within(card).getByRole('combobox', { name: 'Environment' })).toBeInTheDocument();

    const button = sectionButton(card, 'Conditions for this run');
    await act(async () => {
      fireEvent.click(button);
    });
    expect(button).toHaveAttribute('aria-expanded', 'false');
    expect(within(card).queryByRole('combobox', { name: 'Environment' })).toBeNull();
    expect(document.getElementById(button.getAttribute('aria-controls')!)).toHaveAttribute('hidden');
    // STILL MOUNTED, deliberately — see `RunSection`'s header. Collapsing must not
    // discard a half-entered value or an open override form.
    expect(within(card).getByLabelText('Environment')).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(button);
    });
    expect(button).toHaveAttribute('aria-expanded', 'true');
    expect(within(card).getByRole('combobox', { name: 'Environment' })).toBeInTheDocument();
  });

  it('carries its count in the button\'s own accessible name, so a collapsed section says what is in it', async () => {
    const card = await showRun(RUN_WITH_UNCLASSIFIED);
    // Two of the five carry a value in this fixture; the denominator is the list length.
    expect(sectionButton(card, 'Conditions for this run').textContent).toContain(
      `2 of ${RUN_FIELDS.length} recorded`,
    );
    expect(sectionButton(card, 'Values this run inherits').textContent).toContain(
      '1 inherited · 0 overridden on this run',
    );
  });

  /*
   * A KNOWN LIMIT OF THIS GUARD, recorded rather than fixed, because narrowing the
   * pattern would weaken it. `/\d\s*%/` cannot distinguish a FABRICATED completion
   * figure ("60% complete") from a scientific value that legitimately contains a
   * percent sign — `"5% H2 in Ar"` at `context.thermodynamics.atmosphere` is a real
   * atmosphere string and would fail this test if a run carried it. That trade is
   * deliberate: a false failure is a visible, one-line diagnosis, while a percentage
   * this app invented about a scientist's record is the defect the repo's denominator
   * rule exists to prevent. If it ever fires on a legitimate value, scope the assertion
   * to the summary/header text — do not relax the pattern.
   */
  it('states no completion percentage anywhere on the card', async () => {
    const card = await showRun(RUN_WITH_UNCLASSIFIED);
    expect(card.textContent ?? '').not.toMatch(/\d\s*%/);
    // The direct-indexed-lookup trap: a missing map entry renders the word itself.
    expect(card.textContent ?? '').not.toContain('undefined');
    expect(card.textContent ?? '').not.toContain('NaN');
  });
});

// ---------------------------------------------------------------------------
// 4 — inherited presentation is #122's, unchanged
// ---------------------------------------------------------------------------

describe('an inherited value keeps the presentation the override slice established', () => {
  it('is still the named region, still says Inherited from record, still not editable in place', async () => {
    const card = await showRun(RUN_WITH_UNCLASSIFIED);
    const panel = within(card).getByRole('region', {
      name: 'Values inherited from the record',
    });
    expect(within(panel).getByText('sample.material.name')).toBeInTheDocument();
    expect(within(panel).getByText('Synthetic CuO powder')).toBeInTheDocument();
    expect(within(panel).getAllByText(/Inherited from record/).length).toBeGreaterThan(0);
    expect(panel.querySelectorAll('input, select, textarea')).toHaveLength(0);
    expect(
      within(panel).getByRole('button', { name: /Override for this run/ }),
    ).toBeInTheDocument();
  });

  it('keeps the overridden row\'s glyph, word and revert control', async () => {
    const card = await showRun(
      runFixture({
        id: 'RUNAAA',
        label: 'Run 1',
        version: 'ra.0',
        inherited: {
          'field:sample.material.name': {
            state: 'overridden',
            payload: envelope('Synthetic CuO pellet'),
            inherited_payload: envelope('Synthetic CuO powder'),
            displaced_payload: envelope('Synthetic CuO powder'),
            overridable: true,
          },
        },
      }),
    );
    const panel = within(card).getByRole('region', {
      name: 'Values inherited from the record',
    });
    const row = panel.querySelector('[data-state="overridden"]')!;
    expect(row.textContent).toContain('Overridden on this run');
    expect(row.querySelector('.run-inherited-state svg')).not.toBeNull();
    expect(
      within(panel).getByRole('button', { name: /Revert to inherited/ }),
    ).toBeInTheDocument();
    expect(sectionButton(card, 'Values this run inherits').textContent).toContain(
      '0 inherited · 1 overridden on this run',
    );
  });
});

// ---------------------------------------------------------------------------
// 5 — nothing to show, said honestly
// ---------------------------------------------------------------------------

describe('a run with nothing to show says so', () => {
  it('states that the record carries nothing to inherit — and does not render an empty panel', async () => {
    const card = await showRun(
      runFixture({ id: 'RUNAAA', label: 'Run 1', version: 'ra.0', fields: {}, inherited: {} }),
    );
    expect(
      within(card).queryByRole('region', { name: 'Values inherited from the record' }),
    ).toBeNull();
    const body = document.getElementById(
      sectionButton(card, 'Values this run inherits').getAttribute('aria-controls')!,
    )!;
    expect(body.textContent).toContain(
      'The record carries no values at the record-level field addresses this list shows',
    );
    expect(sectionButton(card, 'Values this run inherits').textContent).toContain(
      'no record-level fields in this list',
    );
    // And the card-level note, for the run that holds none of its own values either.
    expect(card.textContent).toContain('This run holds none of its own values yet');
  });

  it('distinguishes "resolved but absent" from "nothing resolved", with the server\'s own count', async () => {
    const card = await showRun(
      runFixture({
        id: 'RUNAAA',
        label: 'Run 1',
        version: 'ra.0',
        fields: {},
        inherited: {
          'field:sample.material.name': {
            state: 'absent',
            payload: null,
            inherited_payload: null,
            overridable: true,
          },
          'field:system.technique': {
            state: 'absent',
            payload: null,
            inherited_payload: null,
            overridable: true,
          },
        },
      }),
    );
    const body = document.getElementById(
      sectionButton(card, 'Values this run inherits').getAttribute('aria-controls')!,
    )!;
    expect(body.textContent).toContain('This run resolves 2 record-level field addresses');
    expect(body.textContent).toContain('none of them holds a value');
    // NOT the other sentence — the record did resolve addresses.
    expect(body.textContent).not.toContain('The record carries no values at the record-level');
  });

  it('never claims "carries nothing" about a value it merely cannot render in one line', async () => {
    const card = await showRun(
      runFixture({
        id: 'RUNAAA',
        label: 'Run 1',
        version: 'ra.0',
        fields: {},
        inherited: {
          'field:sample.composition': {
            state: 'inherited',
            payload: envelope({ CuO2: 0.4 }),
            inherited_payload: envelope({ CuO2: 0.4 }),
          },
        },
      }),
    );
    const body = document.getElementById(
      sectionButton(card, 'Values this run inherits').getAttribute('aria-controls')!,
    )!;
    expect(body.textContent).toContain('cannot show in one line');
    expect(body.textContent).not.toContain('carries no values');
    // The card-level note is withheld here: the record DOES carry something.
    expect(card.textContent).not.toContain('This run holds none of its own values yet');
  });
});

// ---------------------------------------------------------------------------
// 6 — the shape the SERVER actually sends, and the sentences it contradicts
// ---------------------------------------------------------------------------

/*
 * WHY THIS SECTION EXISTS, and why every fixture in it is measured rather than
 * composed. Section 5's fixtures use `inherited: {}` and `field:`-only maps, and both
 * are shapes the running app does not produce for the commonest run in the product.
 * Measured through the real app — `POST /api/experiments`, then `POST …/runs` with the
 * experiment's `If-Match`, then `GET …/runs` — a freshly created experiment's run comes
 * back with `inherited` holding EXACTLY ONE entry:
 *
 *   {'block:attribution': {'state': 'inherited', 'payload': {'contributors': []},
 *                          'inherited_payload': {'contributors': []},
 *                          'displaced_payload': None}}
 *
 * `inheritedTally` counts only `field:` addresses, so every field number was zero and
 * the card rendered three sentences that all spoke for THE RECORD — that it carries
 * nothing at the addresses a run inherits — while the server had resolved something at
 * `block:attribution`, an address that IS in `routes.EXPERIMENT_OVERRIDABLE_ADDRESSES`
 * and IS resolved by `workspace.resolve_inherited` (both measured).
 *
 * THE SECOND FIXTURE'S SHAPE IS MEASURED TOO. `resolve_inherited` on a draft carrying
 * `tags: ['synthetic', 'xanes']` emits `block:tags` with the BARE LIST as its payload —
 * not an envelope — which is why nothing here wraps it in `{value: …}`. The `absent`
 * field address beside it is the wire state `routes._resolution_state` returns when the
 * payload is `None`, which is reachable through a stored override at an address the
 * experiment no longer carries (its docstring says so); it is not an invented state.
 */

/** EXACTLY what `GET …/runs` returns for a run of a freshly created experiment. */
const RUN_OF_A_FRESH_EXPERIMENT = runFixture({
  id: 'RUNAAA',
  label: 'Run 1',
  version: 'ra.0',
  fields: {},
  inherited: {
    'block:attribution': {
      state: 'inherited',
      payload: { contributors: [] },
      inherited_payload: { contributors: [] },
      displaced_payload: null,
      // Overridable server-side, though this panel renders no control for a `block:`
      // address in either case — `overrideRows` excludes them, because there is no
      // honest one-line rendering of a whole object or list.
      overridable: true,
    },
  },
});

/** A record whose only content is a tags block, plus one address that resolves absent. */
const RUN_WITH_A_TAGGED_RECORD = runFixture({
  id: 'RUNAAA',
  label: 'Run 1',
  version: 'ra.0',
  fields: {},
  inherited: {
    'block:tags': {
      state: 'inherited',
      payload: ['synthetic', 'xanes'],
      inherited_payload: ['synthetic', 'xanes'],
      displaced_payload: null,
      overridable: true,
    },
    'field:sample.material.name': {
      state: 'absent',
      payload: null,
      inherited_payload: null,
      overridable: true,
    },
  },
});

/**
 * SENTENCES THAT SPEAK FOR THE WHOLE RECORD. Every one of these was rendered by this
 * branch for the fixtures above, and every one was contradicted by the same response.
 * They are matched as text, lower-cased and whitespace-collapsed, because JSX breaks a
 * sentence across text nodes and a naive `includes` would miss it.
 */
const CLAIMS_ABOUT_THE_WHOLE_RECORD = [
  'the record carries nothing at the addresses a run inherits',
  'the record carries no values at the addresses a run inherits',
  'nothing for this run to inherit',
  'nothing was hidden',
] as const;

function unscopedClaimsIn(el: HTMLElement): string[] {
  const text = (el.textContent ?? '').toLowerCase().replace(/\s+/g, ' ');
  return CLAIMS_ABOUT_THE_WHOLE_RECORD.filter((claim) => text.includes(claim));
}

describe('an empty inherited section never speaks for the record', () => {
  it('says nothing the server contradicts for a run that inherits only a block', async () => {
    const card = await showRun(RUN_OF_A_FRESH_EXPERIMENT);
    expect(unscopedClaimsIn(card)).toEqual([]);

    const body = document.getElementById(
      sectionButton(card, 'Values this run inherits').getAttribute('aria-controls')!,
    )!;
    // What is NOT shown is named, with the server's own address name.
    expect(body.textContent).toContain('also resolves 1 whole-block address that this list does not show');
    expect(body.textContent).toContain('attribution');
    // …and no claim is made about what that block holds. `{contributors: []}` holds nothing.
    expect(body.textContent).not.toContain('The record carries 1 value');

    // The collapsed summary describes THIS LIST, and discloses the address it omits.
    const summary = sectionButton(card, 'Values this run inherits').textContent ?? '';
    expect(summary).toContain('no record-level fields in this list');
    expect(summary).toContain('1 whole-block address not shown here');

    // The card-level note is scoped to the addresses this card can show.
    expect(card.textContent).toContain(
      'the record carries nothing at the record-level field addresses this card shows',
    );
  });

  it('counts what it says it counts, and stops claiming nothing was hidden', async () => {
    const card = await showRun(RUN_WITH_A_TAGGED_RECORD);
    expect(unscopedClaimsIn(card)).toEqual([]);

    const body = document.getElementById(
      sectionButton(card, 'Values this run inherits').getAttribute('aria-controls')!,
    )!;
    // ONE field address resolved, and the sentence names the set it counted. The old
    // copy said "1 record-level address" while two addresses had resolved.
    expect(body.textContent).toContain('This run resolves 1 record-level field address and');
    expect(body.textContent).not.toContain('resolves 2 record-level');
    // The block IS disclosed, by name, rather than covered by "nothing was hidden".
    expect(body.textContent).toContain('also resolves 1 whole-block address');
    expect(body.textContent).toContain('tags');
    // And no claim about the two tag values, which this surface cannot render.
    expect(body.textContent).not.toContain('synthetic, xanes');
  });

  /*
   * THE CANARY. It asserts nothing about the product: it renders the four sentences
   * this branch used to ship and checks that `unscopedClaimsIn` reports all four, then
   * checks that it reports none over the replacement copy. A detector that stopped
   * detecting — a phrase edited on one side only, a `textContent` that no longer
   * reaches, a normalisation bug — would make the two tests above pass vacuously, and
   * this is what fails instead.
   */
  it('the claim detector itself bites', () => {
    const old = document.createElement('div');
    old.innerHTML = `
      <p>This run holds none of its own values yet, and the record carries nothing at
         the addresses a run inherits.</p>
      <p>The record carries no values at the addresses a run inherits, so there is
         nothing for this run to inherit yet.</p>
      <p>Nothing was hidden and nothing failed to load.</p>`;
    expect(unscopedClaimsIn(old).slice().sort()).toEqual(
      [...CLAIMS_ABOUT_THE_WHOLE_RECORD].sort(),
    );

    const replacement = document.createElement('div');
    replacement.innerHTML = `
      <p>This run holds none of its own values yet, and the record carries nothing at the
         record-level field addresses this card shows.</p>
      <p>The record carries no values at the record-level field addresses this list shows,
         so there is nothing in this list yet.</p>
      <p>This run resolves 1 record-level field address and none of them holds a value.
         Nothing here failed to load.</p>
      <p>This run also resolves 1 whole-block address that this list does not show —
         attribution.</p>`;
    expect(unscopedClaimsIn(replacement)).toEqual([]);
  });
});
