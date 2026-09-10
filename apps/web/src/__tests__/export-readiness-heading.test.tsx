/*
 * THE EXPORT SCREEN MUST NOT ASSERT READINESS IT HAS NOT ESTABLISHED.
 *
 * MEASURED DEFECT, over HTTP against a record created by `POST /api/experiments`
 * on a local backend, then read in Chromium at `/record/<id>/export`:
 *
 *   GET /api/experiments/<id>  ->  status: needs_attention, pending_count: 3
 *   POST /api/experiments/<id>/validate -> { ok: false, dry_run: true,
 *       errors: [{ path: "$", message: "'descriptors' is a required property" }] }
 *
 *   document.querySelectorAll('h1')      ->  ["Ready to Export"]
 *   document.querySelectorAll('.record-surface') -> ["Ready to Export"]
 *   document.querySelector('.preexport-title')   -> "3 fields still block export"
 *
 * So the `<h1>` and the breadcrumb leaf — the two positions that name the page —
 * asserted export-readiness about a record whose own body, three elements lower,
 * reported three blockers and a failing dry run. The same destination ALSO had a
 * second name: the workflow spine, rendering the server's `ordered_steps`,
 * called it `Review Export Readiness` in the sidebar of the same screenshot.
 *
 * Two properties are pinned here, and they are separable on purpose:
 *
 *   1. THE DESTINATION'S NAME is the server's own step label, not a string
 *      authored beside it. So the step has one name, and that name asserts
 *      nothing about any particular record.
 *   2. THE HEADING STATES THIS RECORD'S STATE, and the affirmative form is
 *      reachable only when the pending count, the dry run and the SERVER's own
 *      readiness signal all agree.
 *
 * The negative direction is the load-bearing one: on a blocked record the string
 * `Ready to Export` must appear NOWHERE in the rendered screen. A test that only
 * checked the heading's new text would still pass if the words were merely moved.
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import {
  exportReadinessHeading,
  exportReadinessHeadingState,
} from '../screens/ExportReadiness';
import { LABELS } from '../lib/labels';
import { CANONICAL_STEPS, canonicalStepLabel } from '../lib/workflowSteps';
import {
  bundleRoutes,
  experimentDetail,
  exportReadyRoutes,
  fixtureWorkflow,
  pendingRoutes,
  stubFetchRoutes,
  validateDryRun,
  VERSION_FIELDS,
} from '../test/apiFixtures';

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

afterEach(() => {
  vi.unstubAllGlobals();
});

const READY_WORDS = 'Ready to Export';

// ---------------------------------------------------------------- the name

describe("the destination has ONE name, and it is the server's", () => {
  it('LABELS.screenExport IS the canonical step label, not a second string', () => {
    expect(LABELS.screenExport).toBe(canonicalStepLabel('review_export_readiness'));
    expect(LABELS.screenExport).toBe('Review Export Readiness');
  });

  it('the client mirror still matches the backend label it mirrors', () => {
    // `lib/workflowSteps.ts` mirrors `apps/api/isaac_api/workflow.py`
    // CANONICAL_LABELS. If that mirror drifts, the screen name drifts with it —
    // which is the point: one name, one place to change it.
    expect(CANONICAL_STEPS.map((s) => s.id)).toContain('review_export_readiness');
    expect(canonicalStepLabel('export')).toBe('Export');
    expect(() => canonicalStepLabel('not_a_step')).toThrow(/unknown canonical workflow step/);
  });

  it('the screen name is no longer a readiness claim', () => {
    expect(LABELS.screenExport).not.toContain(READY_WORDS);
    // ...while the QUEUE GROUP label, which describes records whose status
    // really is `ready_to_export`, deliberately keeps the words.
    expect(LABELS.groupReady).toBe(READY_WORDS);
  });
});

// ------------------------------------------------- the heading, both directions

describe('a BLOCKED record: the heading names the blocker and claims nothing', () => {
  it('names the blocker in the h1 and renders "Ready to Export" nowhere', async () => {
    stubFetchRoutes(bundleRoutes('demo')); // 5 pending, dry run fails
    const view = renderAt('/record/demo/export');

    // WAIT FOR THE LOADED BODY FIRST. The loading branch renders its own `<h1>`
    // carrying the bare destination name, so a `waitFor(getByRole('heading'))`
    // resolves against the placeholder and would pass while measuring nothing.
    // The body's own sentence for this condition is the marker AND the thing the
    // heading has to agree with, verbatim.
    expect(await view.findByText('5 fields still block export')).toBeInTheDocument();

    const h1 = view.getByRole('heading', { level: 1 });
    expect(h1.textContent).toBe('Review Export Readiness — 5 fields still block export');

    // THE NEGATIVE HALF. Not "the heading does not say it" — the words are not on
    // the screen at all, so they cannot have been relocated to a quieter place.
    expect(view.container.textContent).not.toContain(READY_WORDS);
    expect(view.container.querySelector('.record-surface')?.textContent).toBe(
      'Review Export Readiness',
    );
  });

  it('pending == 0 but a failing dry run is still not readiness', async () => {
    stubFetchRoutes({
      ...exportReadyRoutes('demo'),
      'POST /api/experiments/demo/validate': { body: validateDryRun }, // ok: false
    });
    const view = renderAt('/record/demo/export');

    // The blocked card's own <h2> is the marker; the heading reuses its words.
    expect(await view.findByText('Would Not Validate Yet')).toBeInTheDocument();

    const h1 = view.getByRole('heading', { level: 1 });
    expect(h1.textContent).toBe('Review Export Readiness — Would Not Validate Yet');
    expect(view.container.textContent).not.toContain(READY_WORDS);
  });

  it("the SERVER's readiness signal alone can withhold the affirmative", async () => {
    /*
     * pending == 0 AND the dry run passes, but `derive_workflow` has NOT marked
     * `review_export_readiness` satisfied. The two client-side inputs agree and
     * the server does not, so nothing is claimed: the heading falls back to the
     * destination's bare name. This is the branch that makes "never re-derive
     * readiness client-side" checkable rather than aspirational.
     */
    const base = '/api/experiments/demo';
    stubFetchRoutes({
      ...exportReadyRoutes('demo'),
      [`GET ${base}`]: {
        body: {
          ...experimentDetail,
          id: 'demo',
          status: 'ready_to_export',
          pending_count: 0,
          workflow: fixtureWorkflow({
            pending_count: 0,
            draft_ok: true,
            ready: false, // <- the server has not said ready
            exported: false,
            rev: VERSION_FIELDS.rev,
          }),
        },
      },
      ...pendingRoutes(base, { pending: [] }),
    });
    const view = renderAt('/record/demo/export');

    expect(await view.findByText(/All blockers are resolved/)).toBeInTheDocument();

    const h1 = view.getByRole('heading', { level: 1 });
    expect(h1.textContent).toBe('Review Export Readiness');
    expect(h1.textContent).not.toContain(READY_WORDS);

    /*
     * AND THE BODY'S OWN GATED SECTION *DOES* SAY `Ready to Export` HERE, which
     * is a disagreement worth naming rather than hiding. `.preexport-ready` is
     * gated on `pendingZero && dryRunOk` alone; the heading additionally requires
     * the server's signal, so the heading is strictly the more conservative of
     * the two and withholds where the section does not.
     *
     * Closing the section's gate too would remove the Export button on such a
     * record — a behaviour change, not a copy change — and the actual export is
     * server-gated regardless. So it is deliberately NOT done here, and this
     * assertion records the residue instead of pretending it away.
     */
    expect(view.container.querySelector('.preexport-ready-title')?.textContent).toBe(
      READY_WORDS,
    );
  });
});

describe('an EXPORTABLE record: the heading may say so', () => {
  it('states readiness once every source agrees', async () => {
    stubFetchRoutes(exportReadyRoutes('demo'));
    const view = renderAt('/record/demo/export');

    expect(await view.findByText(/All blockers are resolved/)).toBeInTheDocument();

    const h1 = view.getByRole('heading', { level: 1 });
    expect(h1.textContent).toBe('Review Export Readiness — Ready to Export');
    // And the body agrees, in its own gated section.
    expect(view.container.querySelector('.preexport-ready-title')?.textContent).toBe(
      READY_WORDS,
    );
  });
});

// ------------------------------------------------------------ the pure function

describe('exportReadinessHeadingState', () => {
  const ready = fixtureWorkflow({
    pending_count: 0,
    draft_ok: true,
    ready: true,
    exported: false,
    rev: 3,
  });
  const notReady = fixtureWorkflow({
    pending_count: 2,
    draft_ok: true,
    ready: false,
    exported: false,
    rev: 3,
  });

  it('reports the blocker count before anything else', () => {
    expect(
      exportReadinessHeadingState({
        exported: false,
        pendingCount: 6,
        dryRunOk: false,
        workflow: notReady,
      }),
    ).toBe('6 fields still block export');
    // The singular reads `1 field still block export` — the body's
    // `.preexport-title` pluralizes only `field`, and the heading reuses that
    // sentence VERBATIM rather than authoring a better-formed variant. Matching
    // the page is worth more here than matching a style guide: a heading that
    // improves the grammar is a heading that can drift from what it summarises.
    expect(
      exportReadinessHeadingState({
        exported: false,
        pendingCount: 1,
        dryRunOk: false,
        workflow: notReady,
      }),
    ).toBe('1 field still block export');
  });

  it('reports the dry run when nothing is pending', () => {
    expect(
      exportReadinessHeadingState({
        exported: false,
        pendingCount: 0,
        dryRunOk: false,
        workflow: notReady,
      }),
    ).toBe('Would Not Validate Yet');
  });

  it('claims nothing when the server has not said ready', () => {
    expect(
      exportReadinessHeadingState({
        exported: false,
        pendingCount: 0,
        dryRunOk: true,
        workflow: notReady,
      }),
    ).toBeNull();
    // A missing workflow is not permission to claim readiness either.
    expect(
      exportReadinessHeadingState({
        exported: false,
        pendingCount: 0,
        dryRunOk: true,
        workflow: null,
      }),
    ).toBeNull();
  });

  it('claims readiness only when all three agree', () => {
    expect(
      exportReadinessHeadingState({
        exported: false,
        pendingCount: 0,
        dryRunOk: true,
        workflow: ready,
      }),
    ).toBe(READY_WORDS);
  });

  it('an exported record reports the fact, never the aspiration', () => {
    expect(
      exportReadinessHeadingState({
        exported: true,
        pendingCount: 0,
        dryRunOk: false,
        workflow: notReady,
      }),
    ).toBe('Exported');
  });

  it('the full heading is destination + state, or destination alone', () => {
    expect(
      exportReadinessHeading({
        exported: false,
        pendingCount: 4,
        dryRunOk: false,
        workflow: notReady,
      }),
    ).toBe('Review Export Readiness — 4 fields still block export');
    expect(
      exportReadinessHeading({
        exported: false,
        pendingCount: 0,
        dryRunOk: true,
        workflow: notReady,
      }),
    ).toBe('Review Export Readiness');
  });
});
