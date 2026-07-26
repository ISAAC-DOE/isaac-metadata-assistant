/*
 * P36V S-B — the Open Validator ACTION.
 *
 * Before this slice there was no Open Validator control anywhere in the app. The
 * string existed only as reply PROSE — `'Open Validate to run the deterministic
 * schema check.'`, appended by the composer to three routed truth answers — which
 * is exactly why the action read as nonfunctional: it was a sentence, not a
 * button.
 *
 * These tests pin the replacement contract:
 *   1. the SAME three chips, under the SAME conditions, now carry a typed
 *      `action` instead of the prose sentence — and no other chip in any catalog
 *      carries one (intent resolution is unchanged);
 *   2. the retired sentence is gone from every composed string, in either casing;
 *   3. the control surfaces from every RELEVANT Assistant mount (Record
 *      Workbench, Guided Completion, Ready to Export) and from no other;
 *   4. activating it lands on Governance & Safety → Validator with the Validator
 *      tab genuinely SELECTED (via a `?tab=` deep link the page now honours);
 *   5. it navigates through react-router, so the deployed base path is preserved
 *      and there is no full-page reload;
 *   6. it is a history PUSH — Back returns the reader where they were;
 *   7. arrival moves focus to the Validator's own heading;
 *   8. arriving AGAIN at the same Validator URL re-focuses (the control can never
 *      be perceptibly dead);
 *   9. nothing here mutates: no write request is issued, and the Validator's own
 *      POST /api/validate/record is NOT triggered by navigating to it.
 *
 * Every request stubbed is a read path (or the record screens' existing
 * validate/audit dry-runs, which those screens already issue on mount). No
 * assertion confirms a proposal or writes a field.
 */

import { describe, it, expect, afterEach, vi, type Mock } from 'vitest';
import { render, fireEvent, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, useHref, useLocation, useNavigate } from 'react-router-dom';

import { AppRoutes } from '../App';
import { GovernancePage } from '../screens/GovernancePage';
import {
  COMPLETE_CATALOG,
  EVIDENCE_CATALOG,
  EXPORT_CATALOG,
  MEMORY_CATALOG,
  MEMORY_UNAVAILABLE_CATALOG,
  OPEN_VALIDATOR_ACTION,
  REVIEW_CATALOG,
  compose,
} from '../lib/assistantComposer';
import type { GroundedChip, GroundingState } from '../lib/types';
import {
  bundleRoutes,
  evidenceBundleRoutes,
  exportReadyRoutes,
  graphStatusAvailable,
  graphStatusUnavailable,
  stubFetchRoutes,
} from '../test/apiFixtures';

// The retired prose, in BOTH the sentence-leading and mid-sentence casings the
// composer used. Neither may ever reappear in rendered output.
const RETIRED_PROSE = /open Validate\b/i;

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// A probe that surfaces the live router location (basename-stripped path +
// search), can step BACK through history, and can re-navigate to the Validator
// deep link. `useHref` additionally resolves the action target the way the router
// will, so the basename contribution is observable.
function RouterProbe() {
  const loc = useLocation();
  const navigate = useNavigate();
  const href = useHref(OPEN_VALIDATOR_ACTION.to);
  return (
    <div>
      <div data-testid="loc">{`${loc.pathname}${loc.search}`}</div>
      <div data-testid="href">{href}</div>
      <button type="button" onClick={() => navigate(-1)}>
        probe back
      </button>
      <button type="button" onClick={() => navigate(OPEN_VALIDATOR_ACTION.to)}>
        probe open validator
      </button>
    </div>
  );
}

function renderApp(
  entries: string[],
  opts: { index?: number; basename?: string } = {},
) {
  return render(
    <MemoryRouter
      initialEntries={entries}
      initialIndex={opts.index}
      basename={opts.basename}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
      <RouterProbe />
    </MemoryRouter>,
  );
}

/** Every non-GET request the stubbed fetch saw (there must be none of ours). */
function writeRequests(): string[] {
  const fetchMock = globalThis.fetch as Mock | undefined;
  if (!fetchMock?.mock) return [];
  return (fetchMock.mock.calls as [string, RequestInit?][])
    .filter(([, init]) => (init?.method ?? 'GET').toUpperCase() !== 'GET')
    .map(([url, init]) => `${(init?.method ?? 'GET').toUpperCase()} ${String(url)}`);
}

const openValidator = () => screen.getByRole('button', { name: /Open Validator/ });

// ---------------------------------------------------------------------------
// 1 + 2 — composer contract: the same conditions, an action instead of prose
// ---------------------------------------------------------------------------

describe('P36V S-B · the composer offers an ACTION where it used to append prose', () => {
  // The three chips that carried `ROUTE_TO_VALIDATE` (review + export
  // blocking_paths, complete missing_field_behavior) — and only those.
  const CARRIERS: [string, GroundedChip[]][] = [
    ['review', REVIEW_CATALOG],
    ['export', EXPORT_CATALOG],
    ['complete', COMPLETE_CATALOG],
  ];
  const NON_CARRIERS: [string, GroundedChip[]][] = [
    ['evidence', EVIDENCE_CATALOG],
    ['memory', MEMORY_CATALOG],
    ['memory-unavailable', MEMORY_UNAVAILABLE_CATALOG],
  ];

  it('the action is a closed, bounded descriptor: one kind, a Title-Case label, an in-app route', () => {
    expect(OPEN_VALIDATOR_ACTION).toEqual({
      kind: 'open-validator',
      label: 'Open Validator',
      to: '/governance?tab=validator',
    });
    // the VISIBLE label is Title Case "Open Validator", never the retired
    // "Open Validate" / "Validate" wording
    expect(OPEN_VALIDATOR_ACTION.label).toBe('Open Validator');
    expect(OPEN_VALIDATOR_ACTION.label).not.toMatch(RETIRED_PROSE);
    // an in-app client route (never an absolute server path or external URL)
    expect(OPEN_VALIDATOR_ACTION.to.startsWith('/governance')).toBe(true);
    expect(OPEN_VALIDATOR_ACTION.to).not.toMatch(/^https?:/);
  });

  it('exactly the three chips that used to append the prose now carry the action', () => {
    const carrying: string[] = [];
    for (const [, catalog] of [...CARRIERS, ...NON_CARRIERS]) {
      for (const chip of catalog) {
        // resolve every chip against every context; only the matching context
        // returns non-null, so this enumerates the whole action surface.
        for (const state of ALL_STATES) {
          const answer = chip.resolve(state);
          if (answer?.action) carrying.push(`${state.context}:${chip.id}`);
        }
      }
    }
    expect(new Set(carrying)).toEqual(
      new Set([
        'review:blocking_paths',
        'export:blocking_paths',
        'complete:missing_field_behavior',
      ]),
    );
  });

  it('no chip in the evidence or memory catalogs offers an action (nothing new was surfaced)', () => {
    for (const [name, catalog] of NON_CARRIERS) {
      for (const chip of catalog) {
        for (const state of ALL_STATES) {
          expect(chip.resolve(state)?.action, `${name}:${chip.id}`).toBeUndefined();
        }
      }
    }
  });

  it('the retired prose sentence appears in NO composed string, in either casing', () => {
    for (const state of ALL_STATES) {
      const out = compose(state);
      expect(out.reply.text, state.context).not.toMatch(RETIRED_PROSE);
      for (const p of out.prompts) {
        expect(p.answer?.text ?? '', `${state.context}:${p.text}`).not.toMatch(RETIRED_PROSE);
      }
    }
  });

  it('a disabled chip (validate payload absent) offers no answer and therefore no action', () => {
    const out = compose({
      context: 'review',
      bundle: { validate: undefined },
    } as unknown as GroundingState);
    expect(out.prompts[1].answer).toBeUndefined();
  });
});

// Minimal but shape-faithful states for each context, enough to resolve every
// chip. Cast once at the boundary (the composer reads only the fields present).
const ALL_STATES: GroundingState[] = [
  {
    context: 'review',
    bundle: {
      pending: [],
      validate: { ok: false, errors: [{ path: '$.assets', message: 'required' }] },
      evidence: [],
    },
  },
  {
    context: 'export',
    bundle: {
      audit: { records: [], text: '' },
      validate: { ok: false, errors: [] },
      warnings: { advisory: true, gating: false, warnings: [] },
    },
  },
  {
    context: 'evidence',
    bundle: { evidence: [], artifacts: { record_filename: null, sidecar_filename: null } },
    selectedPath: undefined,
  },
  { context: 'complete', detail: {}, pending: [] },
  { context: 'memory', graph: graphStatusAvailable },
  { context: 'memory', graph: graphStatusUnavailable },
] as unknown as GroundingState[];

// ---------------------------------------------------------------------------
// 3 — the control surfaces from every RELEVANT mount, and from no other
// ---------------------------------------------------------------------------

describe('P36V S-B · the Open Validator control surfaces from every relevant Assistant mount', () => {
  type Routes = ReturnType<typeof bundleRoutes>;
  const MOUNTS: [string, string, () => Routes, string][] = [
    ['Record Workbench', '/record/demo', () => bundleRoutes('demo'), "What's left before export?"],
    [
      'Ready to Export',
      '/record/demo/export',
      () => exportReadyRoutes('demo'),
      "What's left before export?",
    ],
    [
      'Guided Completion',
      '/record/demo/complete',
      () => bundleRoutes('demo'),
      'What if I leave one missing?',
    ],
  ];

  for (const [name, path, routes, chipLabel] of MOUNTS) {
    it(`${name}: the routed truth chip renders a real Open Validator BUTTON in the proposed-action region`, async () => {
      stubFetchRoutes(routes());
      const { container } = renderApp([path]);

      const assistant = (await waitFor(() => {
        const el = container.querySelector('.assistant');
        expect(el).not.toBeNull();
        return el as HTMLElement;
      })) as HTMLElement;
      const panel = within(assistant);

      // no action is offered before the chip is activated
      expect(panel.queryByRole('button', { name: /Open Validator/ })).toBeNull();

      fireEvent.click((await panel.findByText(chipLabel)).closest('button')!);

      const go = await panel.findByRole('button', { name: /Open Validator/ });
      expect(go.tagName).toBe('BUTTON');
      // it is a proposed ACTION, not a chat message, and it never implies that
      // anything already happened
      const region = go.closest('.assistant-proposed') as HTMLElement;
      expect(region).not.toBeNull();
      expect(region.textContent).toMatch(/not applied/i);
      expect(go.closest('.assistant-log')).toBeNull();
      expect(go.closest('.assistant-msg')).toBeNull();
      // P36V — the region's ACCESSIBLE NAME is its visible eyebrow, so a screen
      // reader hears exactly what a sighted reader sees. It must NOT claim the
      // action "needs your confirmation": Open Validator navigates and writes
      // nothing, so there is nothing to confirm. Guards both the drift (name
      // detached from visible text) and the specific untrue wording.
      const eyebrow = region.querySelector('.assistant-proposed-eyebrow') as HTMLElement;
      expect(eyebrow).not.toBeNull();
      expect(region.getAttribute('aria-labelledby')).toBe(eyebrow.id);
      expect(region.getAttribute('aria-label')).toBeNull();
      expect(eyebrow.textContent?.trim()).toBe('Proposed Action — Not Applied');
      // Scoped to the region NAME. (A staged proposal card may truthfully say
      // "Needs Your Confirmation" about itself; the region name may not, because
      // this region also holds navigation, which confirms nothing.)
      expect(eyebrow.textContent).not.toMatch(/needs your confirmation/i);
      // the dead prose it replaced is gone from the whole panel
      expect(assistant.textContent).not.toMatch(RETIRED_PROSE);
      // and the control states plainly that offering it changes nothing
      expect(region.textContent).toMatch(/no field is written/i);
      expect(region.textContent).toMatch(/no check is run/i);

      // rendering it mutated nothing: the only non-GET calls are the record
      // screens' own pre-existing validate/audit DRY RUNS, never a write
      for (const req of writeRequests()) {
        expect(req).toMatch(/\/(validate|audit)$/);
      }
    });
  }

  it('Evidence Explorer offers no Open Validator control (its catalog carries no action)', async () => {
    stubFetchRoutes(evidenceBundleRoutes('demo'));
    const { container } = renderApp(['/record/demo/evidence']);
    const assistant = (await waitFor(() => {
      const el = container.querySelector('.assistant');
      expect(el).not.toBeNull();
      return el as HTMLElement;
    })) as HTMLElement;
    const panel = within(assistant);

    for (const chip of EVIDENCE_CATALOG) {
      const pill = panel.queryByText(chip.label);
      if (pill) fireEvent.click(pill.closest('button')!);
    }
    expect(panel.queryByRole('button', { name: /Open Validator/ })).toBeNull();
    expect(assistant.textContent).not.toMatch(RETIRED_PROSE);
  });
});

// ---------------------------------------------------------------------------
// 4 + 5 + 6 + 7 + 9 — navigation behaviour
// ---------------------------------------------------------------------------

/** Open the Guided Completion assistant and activate its routed truth chip. */
async function completionWithAction(opts: { basename?: string } = {}) {
  const prefix = opts.basename ?? '';
  const rendered = renderApp([`${prefix}/record/demo/complete`], opts);
  const assistant = (await waitFor(() => {
    const el = rendered.container.querySelector('.assistant');
    expect(el).not.toBeNull();
    return el as HTMLElement;
  })) as HTMLElement;
  const panel = within(assistant);
  fireEvent.click((await panel.findByText('What if I leave one missing?')).closest('button')!);
  await panel.findByRole('button', { name: /Open Validator/ });
  return rendered;
}

describe('P36V S-B · activating Open Validator lands on Governance & Safety → Validator', () => {
  it('selects the Validator TAB (not just the /governance route) and mounts the validator', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    await completionWithAction();

    fireEvent.click(openValidator());

    // the route AND the deep-link parameter that selects the tab
    await waitFor(() =>
      expect(screen.getByTestId('loc').textContent).toBe('/governance?tab=validator'),
    );
    // the tab is genuinely SELECTED — never merely the default Policy tab
    expect(screen.getByRole('tab', { name: 'Validator' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByRole('tab', { name: 'Policy' })).toHaveAttribute('aria-selected', 'false');
    // …and the Validator surface itself is mounted
    expect(screen.getByRole('heading', { name: 'Standalone Validator' })).toBeInTheDocument();
    expect(screen.getByLabelText(/candidate record \(json\)/i)).toBeInTheDocument();

    // 9 — navigating there ran NO validation and wrote nothing
    expect(writeRequests().some((r) => r.includes('/api/validate/record'))).toBe(false);
    for (const req of writeRequests()) expect(req).toMatch(/\/(validate|audit)$/);
  });

  it('moves focus to the Validator heading on arrival', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    await completionWithAction();

    fireEvent.click(openValidator());

    const heading = await screen.findByRole('heading', { name: 'Standalone Validator' });
    await waitFor(() => expect(heading).toHaveFocus());
    // a programmatic target only — never added to the Tab order
    expect(heading).toHaveAttribute('tabindex', '-1');
  });

  it('preserves the deployed base path and does NOT reload the page (client-side router nav)', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const before = `${window.location.pathname}${window.location.search}`;
    await completionWithAction({ basename: '/krish' });

    // the router resolves the action's target UNDER the basename …
    expect(screen.getByTestId('href').textContent).toBe('/krish/governance?tab=validator');

    const go = openValidator();
    // … the control is a BUTTON, not an <a href> and not a form submit, so no
    // full-page navigation can occur …
    expect(go.tagName).toBe('BUTTON');
    expect(go.getAttribute('type')).toBe('button');
    expect(go.hasAttribute('href')).toBe(false);
    expect(go.closest('form')).toBeNull();

    fireEvent.click(go);

    // … it resolves inside the basename and the Validator tab is selected …
    await waitFor(() =>
      expect(screen.getByTestId('loc').textContent).toBe('/governance?tab=validator'),
    );
    expect(screen.getByRole('tab', { name: 'Validator' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    // … and the document itself never navigated (jsdom would have to reload)
    expect(`${window.location.pathname}${window.location.search}`).toBe(before);
  });

  it('is a history PUSH: Back returns to the screen the reader came from', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    await completionWithAction();

    fireEvent.click(openValidator());
    await waitFor(() =>
      expect(screen.getByTestId('loc').textContent).toBe('/governance?tab=validator'),
    );

    fireEvent.click(screen.getByRole('button', { name: 'probe back' }));
    await waitFor(() =>
      expect(screen.getByTestId('loc').textContent).toBe('/record/demo/complete'),
    );
  });
});

// ---------------------------------------------------------------------------
// 8 — arriving again at the Validator is never a dead no-op
// ---------------------------------------------------------------------------

describe('P36V S-B · arriving at the Validator again still does something perceptible', () => {
  it('re-navigating to the same Validator URL re-focuses the Validator heading', async () => {
    const { getByRole, getByTestId } = renderApp(['/governance?tab=validator']);

    const heading = getByRole('heading', { name: 'Standalone Validator' });
    await waitFor(() => expect(heading).toHaveFocus());

    // move focus away, then arrive AGAIN at the identical URL
    (getByRole('button', { name: 'probe back' }) as HTMLButtonElement).focus();
    expect(heading).not.toHaveFocus();

    fireEvent.click(getByRole('button', { name: 'probe open validator' }));

    await waitFor(() => expect(heading).toHaveFocus());
    expect(getByTestId('loc').textContent).toBe('/governance?tab=validator');
    expect(getByRole('tab', { name: 'Validator' })).toHaveAttribute('aria-selected', 'true');
  });
});

// ---------------------------------------------------------------------------
// GovernancePage deep-link derivation + preserved tablist behaviour
// ---------------------------------------------------------------------------

function renderGovernance(entry: string) {
  return render(
    <MemoryRouter
      initialEntries={[entry]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <GovernancePage />
    </MemoryRouter>,
  );
}

describe('P36V S-B · Governance & Safety derives its tab from the URL', () => {
  it('?tab=validator selects Validator; ?tab=schema selects Schema Reference', async () => {
    renderGovernance('/governance?tab=validator');
    expect(screen.getByRole('tab', { name: 'Validator' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByRole('heading', { name: 'Standalone Validator' })).toBeInTheDocument();
  });

  it('an unknown, empty, or absent tab value falls back to Policy without throwing', () => {
    for (const entry of ['/governance', '/governance?tab=', '/governance?tab=bogus', '/governance?tab=VALIDATOR']) {
      const { unmount } = renderGovernance(entry);
      expect(screen.getByRole('tab', { name: 'Policy' }), entry).toHaveAttribute(
        'aria-selected',
        'true',
      );
      expect(screen.queryByText('Standalone Validator')).toBeNull();
      unmount();
    }
  });

  it('an in-page tab click keeps the tablist roving-tabindex focus (never stolen by arrival focus)', () => {
    renderGovernance('/governance');
    const policy = screen.getByRole('tab', { name: 'Policy' });
    policy.focus();
    fireEvent.keyDown(policy, { key: 'ArrowRight' });

    const validator = screen.getByRole('tab', { name: 'Validator' });
    expect(validator).toHaveAttribute('aria-selected', 'true');
    // the existing keyboard contract: focus lands on the newly selected TAB, not
    // on the Validator heading (arrival focus applies to ARRIVALS only)
    expect(validator).toHaveFocus();
    expect(screen.getByRole('heading', { name: 'Standalone Validator' })).not.toHaveFocus();
  });

  it('an in-page tab click REPLACES history, so Back leaves Governance instead of stepping tabs', async () => {
    stubFetchRoutes({ 'GET /api/graph/status': { body: graphStatusUnavailable } });
    renderApp(['/experiments', '/governance'], { index: 1 });

    fireEvent.click(await screen.findByRole('tab', { name: 'Validator' }));
    await waitFor(() =>
      expect(screen.getByTestId('loc').textContent).toBe('/governance?tab=validator'),
    );

    fireEvent.click(screen.getByRole('button', { name: 'probe back' }));
    await waitFor(() => expect(screen.getByTestId('loc').textContent).toBe('/experiments'));
  });
});
