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
 * MUTATION-TESTED. Each load-bearing assertion here was verified by breaking the
 * component in the exact way it claims to catch and confirming the failure; the
 * mutations and their output are in the slice report. `the assertion helper itself
 * bites` below is the standing canary: it runs the same detector over a DOM that DOES
 * contain a forbidden path, so a helper that silently stopped detecting anything
 * cannot leave this file green.
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
  stubFetchRoutes,
  VERSION_FIELDS,
  type RouteEntry,
} from '../test/apiFixtures';

configure({ asyncUtilTimeout: 5_000 });

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

function runsBody(runs: unknown[]) {
  return { runs, experiment_version: VERSION_FIELDS.version };
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
    fireEvent.click(within(cardFor(runId)).getByRole('button', { name: /Run \d/ }));
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
    expect(body.textContent).toContain('The record carries no values at the addresses a run inherits');
    expect(sectionButton(card, 'Values this run inherits').textContent).toContain(
      'nothing for this run to inherit',
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
          'field:sample.material.name': { state: 'absent', payload: null, inherited_payload: null },
          'field:system.technique': { state: 'absent', payload: null, inherited_payload: null },
        },
      }),
    );
    const body = document.getElementById(
      sectionButton(card, 'Values this run inherits').getAttribute('aria-controls')!,
    )!;
    expect(body.textContent).toContain('This run resolves 2 record-level addresses');
    expect(body.textContent).toContain('none of them holds a value');
    // NOT the other sentence — the record did resolve addresses.
    expect(body.textContent).not.toContain('The record carries no values at the addresses');
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
