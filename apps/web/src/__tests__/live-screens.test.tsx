import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, within } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { AppRoutes } from '../App';
import { RUN_COMMAND } from '../lib/api';
import { NEEDSYOU_VISIBLE, NEEDSYOU_VISIBLE_GROUPS } from '../screens/RecordWorkbench';
import {
  EXP_ID,
  bundleRoutes,
  demoRunDraftOnly,
  experimentSummary,
  exportedSummary,
  stubFetchDown,
  stubFetchRoutes,
  uploadsBlocked,
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

// A tiny probe that surfaces the live router pathname, so a test can prove a
// click routed to an EXISTING route without stubbing the destination screen.
function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="pathname">{loc.pathname}</div>;
}

function renderAtWithLocation(path: string) {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
      <LocationProbe />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('S1 · My Experiments renders live queue groups from injected data', () => {
  it('groups experiments by server-derived status; empty groups hidden', async () => {
    stubFetchRoutes({
      'GET /api/experiments': {
        body: { experiments: [experimentSummary, exportedSummary] },
      },
    });
    const { findByText, queryByText, getByText } = renderAt('/experiments');

    // group headers from the server statuses present (and only those)
    expect(await findByText('Needs Attention')).toBeInTheDocument();
    expect(getByText('Done')).toBeInTheDocument();
    expect(queryByText('In Review')).toBeNull();
    expect(queryByText('Ready to Export')).toBeNull();

    // rows carry the live titles + server-derived trailing state
    expect(getByText('Synthetic XANES — CuO (Cu K-edge) Demo')).toBeInTheDocument();
    expect(getByText('5 Fields Need You')).toBeInTheDocument();
    expect(getByText('Synthetic XANES — CuO baseline (exported)')).toBeInTheDocument();
    expect(getByText('Exported')).toBeInTheDocument();

    // subcount comes from the live list
    expect(getByText('2 experiments · 0 ready to export')).toBeInTheDocument();
  });

  it('backend down → visible "Backend Not Running" with the exact run command, never fake rows', async () => {
    stubFetchDown();
    const { findByText, queryByText, getByText } = renderAt('/experiments');
    expect(await findByText('Backend Not Running')).toBeInTheDocument();
    expect(getByText(RUN_COMMAND)).toBeInTheDocument();
    // no mock/fake experiment rows appear
    expect(queryByText(/Cu K-edge/)).toBeNull();
    expect(queryByText('Needs Attention')).toBeNull();
  });
});

describe('S2 · Load Materials', () => {
  it('local structured files are approval-gated: the 403 governance message shows verbatim', async () => {
    stubFetchRoutes({ 'POST /api/uploads': { status: 403, body: uploadsBlocked } });
    const { findByText, getByText, getByRole, container } = renderAt('/load');

    // P36V.2 F1 — the control is a plain button and the panel has NO file input,
    // so no picker can open and no file is ever chosen, sent or read. The copy
    // now says exactly that, and is selected on here so it cannot drift back.
    expect(container.querySelector('input[type="file"]')).toBeNull();
    fireEvent.click(getByRole('button', { name: /opens no file picker/i }));

    expect(await findByText(/Blocked by governance\./)).toBeInTheDocument();
    expect(getByText(new RegExp(uploadsBlocked.reason))).toBeInTheDocument();
    // the governance banner stays mounted alongside the blocked state.
    // Slice 2A (I5) requalified its headline "Synthetic mode." → "Synthetic
    // workspace." (the deployment may run a read-only test-DB diagnostic, so an
    // unqualified mode claim over-stated it). Same assertion, new anchor.
    expect(getByText(/Synthetic workspace\./)).toBeInTheDocument();
  });

  it('uploads with the backend down → Backend Not Running with the run command, never governance copy', async () => {
    stubFetchDown();
    const { findByText, getByText, getByRole, queryByText } = renderAt('/load');

    fireEvent.click(getByRole('button', { name: /opens no file picker/i }));

    expect(await findByText('Backend Not Running')).toBeInTheDocument();
    expect(getByText(RUN_COMMAND)).toBeInTheDocument();
    // an unreachable backend must never masquerade as a governance refusal
    expect(queryByText(/Blocked by governance/)).toBeNull();
    expect(queryByText(new RegExp(uploadsBlocked.reason))).toBeNull();
  });

  it('the example run renders the real POST /api/demo/run steps — the old mock figures are gone', async () => {
    stubFetchRoutes({ 'POST /api/demo/run': { body: demoRunDraftOnly } });
    const { findByText, getByText, queryByText } = renderAt('/load');

    fireEvent.click(getByText('Run the Worked Example'));

    // the returned pipeline steps, verbatim details
    expect(await findByText('Build Draft')).toBeInTheDocument();
    expect(getByText('26 evidenced fields, 5 pending blocker(s)')).toBeInTheDocument();
    expect(getByText('Validate Draft')).toBeInTheDocument();
    expect(getByText('draft ok: true')).toBeInTheDocument();

    // paused honestly + a route into the new record
    expect(getByText('paused for your input · your turn')).toBeInTheDocument();
    expect(getByText('Open the Record →')).toBeInTheDocument();
    expect(getByText(EXP_ID)).toBeInTheDocument();

    // inherited fix: the non-summing mock runner figures must not render
    expect(queryByText('26 fields')).toBeNull();
    expect(queryByText('12 verified · 3 inferred')).toBeNull();
  });
});

describe('S3 · Review Record (live bundle)', () => {
  // P33 S4 (D8) — the right rail is the assistant ONLY. The former right-rail
  // "Evidence for selected field" panel + its truth/advisory divider are gone;
  // deterministic evidence lives inline on the field rows (main column).
  it('the right rail is the assistant only — no evidence panel, no truth/advisory divider', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { container, findByText } = renderAt('/record/demo');

    await findByText('5 Fields Need Your Confirmation');

    const rail = container.querySelector('.record-right');
    expect(rail).not.toBeNull();
    // the assistant IS the rail's content
    expect(rail!.querySelector('.assistant')).not.toBeNull();
    // the removed right-rail evidence panel + hard divider must not reappear
    expect(container.querySelector('.ev-panel-card')).toBeNull();
    expect(container.querySelector('.right-divider')).toBeNull();
    // inline per-field evidence is still present in the main column (truth stays
    // visible). P33 HQA#5: groups start collapsed, so expand one to reveal its
    // field rows and their inline evidence.
    fireEvent.click(container.querySelector('.fg-header') as HTMLButtonElement);
    expect(container.querySelector('.field-evidence')).not.toBeNull();
  });

  // P33 S4 (D8) — the whole-record Evidence Trail affordance moved beneath the
  // workflow spine and reuses the EXISTING /evidence route (no new route/system).
  it('an Evidence Trail affordance sits beneath the workflow spine and routes to the existing /evidence route', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { container, findByText, getByTestId } = renderAtWithLocation('/record/demo');

    await findByText('5 Fields Need Your Confirmation');

    const aside = container.querySelector('.record-aside');
    expect(aside).not.toBeNull();
    const spine = aside!.querySelector('.spine');
    const link = aside!.querySelector('.evidence-trail-link');
    expect(spine).not.toBeNull();
    expect(link).not.toBeNull();
    // it sits AFTER the spine in DOM order (beneath the workflow)
    const pos = spine!.compareDocumentPosition(link!);
    expect(pos & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // it names the Evidence Trail and shows the live entry count from /evidence
    expect(within(link as HTMLElement).getByText('Evidence Trail')).toBeInTheDocument();

    // clicking it navigates to the EXISTING /evidence route (ROUTES.evidence),
    // never a new route or evidence system
    expect(getByTestId('pathname').textContent).toBe('/record/demo');
    fireEvent.click(link!);
    expect(getByTestId('pathname').textContent).toBe('/record/demo/evidence');
  });

  /*
   * P33 S4 (D9/C2) — the needs-you banner names each question with a concise
   * structured label and its technical locator once as a demoted mono token; a raw
   * identifier is never the primary label.
   *
   * ~~"a NUMBERED list"~~ — WITHDRAWN, and the reason is a measured defect rather
   * than a preference. The flat numbered list rendered the SAME THREE QUESTIONS
   * TWICE, byte-identical, on a record with two runs — Run A and Run B each own a
   * `series`, a `qc` and a `descriptor`, and nothing in the row said which run it
   * belonged to, so a reader could not resolve the ambiguity without leaving the
   * page. The ordinals made that worse rather than better: they implied six
   * distinct things. The list is now grouped by the OWNER the server named
   * (`run_id`/`run_label`, record-level first) and the ordinals are gone, because
   * the order is the server's and carries nothing a reader can act on.
   *
   * WHAT DID NOT CHANGE, and is still asserted below: the label/locator treatment
   * of each question, and the bound.
   */
  it('groups the needs-you banner by owner, with concise labels and locators shown once', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { container, findByText, getByText, getAllByText, queryByText } = renderAt(
      '/record/demo',
    );

    await findByText('5 Fields Need Your Confirmation');

    // ONE row per owner. These five pending items are all record-level (no
    // `run_id`), so they are one group — and all five are still named inside it.
    const list = container.querySelector('ul.needsyou-list');
    expect(list).not.toBeNull();
    expect(list!.querySelectorAll(':scope > li.needsyou-group')).toHaveLength(1);
    expect(list!.querySelectorAll('.needsyou-item')).toHaveLength(5);
    // ...and the owner is NAMED, which is the whole point of the grouping.
    expect(
      [...list!.querySelectorAll('.needsyou-owner')].map((el) => el.textContent),
    ).toEqual(['This record']);

    // concise structured labels are the primary line (3 asset blockers, plus the
    // structured series + descriptor) — never the verbose question echo
    expect(getAllByText('Asset Hash')).toHaveLength(3);
    expect(getByText('Reduced Spectrum')).toBeInTheDocument();
    expect(getByText('Scientific Descriptor')).toBeInTheDocument();
    expect(queryByText('What is the sha256 of the processing notebook?')).toBeNull();

    // the descriptor's raw identifier is demoted to the locator, shown exactly once
    const raw = [...container.querySelectorAll('.needsyou-about')].filter(
      (el) => el.textContent === 'required_for_evidence_record',
    );
    expect(raw).toHaveLength(1);
    // and it is never rendered as a primary label
    const primaries = [...container.querySelectorAll('.needsyou-q')].map((el) => el.textContent);
    expect(primaries).not.toContain('required_for_evidence_record');
  });

  /*
   * THE BANNER IS BOUNDED, AND THE BOUND IS THE MOST EXPENSIVE THING ON THIS SCREEN
   * AT SCALE.
   *
   * This list was UNBOUNDED and no test noticed, because every fixture in the suite
   * has five pending items. A scale benchmark measured what that costs: at 1000 runs
   * the record screen held 16,134 DOM nodes, ~15,000 of them this list (3,002 items ×
   * five nodes). Every run card together was 50, capped by the Run browser's own
   * paging. So `docs/run-scale-measurements.md`'s conclusion "the DOM is not the
   * problem" was true when measured — the run count WAS the card count then — and
   * stopped being true when runs began paging and this did not.
   *
   * TWO PROPERTIES, and the second is the one that makes truncation acceptable: the
   * list is a prefix, and the screen SAYS SO with both numbers. A truncated list that
   * read as complete would be worse than the slow one — a scientist counting eleven
   * items and concluding eleven questions remain would be wrong by three thousand.
   */
  it('bounds the banner by BOTH rows and questions, and states the remainder in words', async () => {
    const many = Array.from({ length: 64 }, (_, i) => ({
      id: 'series',
      blocker_key: `01RUN${String(i).padStart(21, '0')}:series`,
      run_id: `01RUN${String(i).padStart(21, '0')}`,
      run_label: `Run ${i + 1}`,
      kind: 'series',
      question: 'Provide the reduced spectrum.',
      about: 'reduced_spectrum',
      demo_answer: null,
      inferability: {
        field: 'reduced_spectrum',
        state: 'needs_user_input' as const,
        explanation: 'x',
        value: null,
        provenance: null,
        detail: {},
      },
    }));
    stubFetchRoutes({
      ...bundleRoutes('demo'),
      'GET /api/experiments/demo/pending': { body: { pending: many } },
    });
    const { container, findByText, getByText } = renderAt('/record/demo');

    // THE TITLE CARRIES THE FULL COUNT. It is the one number a reader acts on.
    await findByText('64 Fields Need Your Confirmation');

    const list = container.querySelector('ul.needsyou-list')!;
    /*
     * TWO BOUNDS, AND THIS FIXTURE IS THE CASE WHERE THE SECOND ONE BINDS.
     *
     * `NEEDSYOU_VISIBLE` (10) bounds how many QUESTIONS are named;
     * `NEEDSYOU_VISIBLE_GROUPS` (3) bounds how many OWNERS get a row. These 64
     * questions belong to 64 DIFFERENT runs — one each — so the row bound is
     * reached first and three questions are named, not ten. That is the intended
     * behaviour rather than a shortfall: a banner listing ten runs is the wall of
     * rows this compaction exists to remove, and a reader cannot act on run 7 from
     * here in any case. What makes it acceptable is the same thing that made the
     * old truncation acceptable, and it is asserted immediately below: the screen
     * SAYS the list is a prefix, with both numbers, and both numbers are the
     * record's own (`pendingTotal`) rather than the window's.
     *
     * The other binding order is covered by the case above: five questions all
     * owned by the RECORD are one row, and all five are named.
     */
    expect(list.querySelectorAll(':scope > li.needsyou-group')).toHaveLength(
      NEEDSYOU_VISIBLE_GROUPS,
    );
    expect(list.querySelectorAll('.needsyou-item')).toHaveLength(NEEDSYOU_VISIBLE_GROUPS);
    /* THE QUESTION BUDGET IS NOT THE BINDING BOUND HERE, and saying so mechanically
       is what stops this test reading as though it were: three named questions is
       well inside ten, so a change that raised or removed `NEEDSYOU_VISIBLE` would
       not move a single assertion above. */
    expect(NEEDSYOU_VISIBLE_GROUPS).toBeLessThan(NEEDSYOU_VISIBLE);
    // Each row NAMES ITS RUN, which is the ambiguity the flat list could not resolve.
    expect(
      [...list.querySelectorAll('.needsyou-owner')].map((el) => el.textContent),
    ).toEqual(['Run 1', 'Run 2', 'Run 3']);
    // AND THE REMAINDER IS STATED IN WORDS, not as an ellipsis — a screen-reader user
    // who has just heard "64" needs to be told this list is a prefix of it.
    expect(getByText(/Showing the first 3 of 64/)).toBeInTheDocument();
    expect(getByText(/61 more are waiting/)).toBeInTheDocument();
  });

  it('gives every listed pending item a DISTINCT React key, across runs', async () => {
    /*
     * A run-owned question's `id` is its KIND — `series`, `qc`, `descriptor` — so this
     * list keyed on `p.id` produced N identical `<li key="series">` on a record with N
     * runs. Duplicate keys are a React reconciliation hazard and a console error, on
     * the first screen a scientist opens.
     *
     * ASSERTED THROUGH THE CONSOLE, because that is where React reports it and because
     * a DOM assertion cannot see a key at all. `blocker_key` is the identity that
     * exists for exactly this — the same fix the completion screen needed, in a place
     * nobody had looked.
     */
    const errors: string[] = [];
    const spy = vi.spyOn(console, 'error').mockImplementation((...args: unknown[]) => {
      errors.push(args.map(String).join(' '));
    });
    try {
      const pending = ['01RUNAAAAAAAAAAAAAAAAAAAAA', '01RUNBBBBBBBBBBBBBBBBBBBBB'].map((rid) => ({
        id: 'series',
        blocker_key: `${rid}:series`,
        run_id: rid,
        run_label: rid,
        kind: 'series',
        question: 'Provide the reduced spectrum.',
        about: 'reduced_spectrum',
        demo_answer: null,
        inferability: {
          field: 'reduced_spectrum',
          state: 'needs_user_input' as const,
          explanation: 'x',
          value: null,
          provenance: null,
          detail: {},
        },
      }));
      stubFetchRoutes({
        ...bundleRoutes('demo'),
        'GET /api/experiments/demo/pending': { body: { pending } },
      });
      const { findByText } = renderAt('/record/demo');
      await findByText('2 Fields Need Your Confirmation');
      const duplicates = errors.filter((e) => /same key|duplicate key/i.test(e));
      expect(duplicates, duplicates.join('\n')).toHaveLength(0);
    } finally {
      spy.mockRestore();
    }
  });

  it('shows live pending as Needs You and live draft fields; signals stay three labeled segments', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { container, findByText, getAllByLabelText, getByText, getByLabelText } =
      renderAt('/record/demo');

    // needs-you banner fed by /pending — concise structured label + the technical
    // locator surfaced verbatim (proves the live pending item drives the banner).
    // Scoped to the banner: the assistant reply lists the same locators, so a
    // page-wide query would legitimately match twice.
    await findByText('5 Fields Need Your Confirmation');
    const banner = container.querySelector('.needsyou-banner') as HTMLElement;
    expect(within(banner).getAllByText('Asset Hash').length).toBeGreaterThan(0);
    expect(
      within(banner).getByText(
        'ssrl-archive://BL15-2/2099_run_000/notebooks/xanes_reduction_v2.ipynb',
      ),
    ).toBeInTheDocument();

    // draft groups fed by /draft. P33 HQA#5: groups start collapsed, so the
    // human-facing group label shows in the (collapsed) header; expanding it
    // reveals the live field value.
    expect(getByText('System & Instrument')).toBeInTheDocument();
    fireEvent.click(container.querySelector('.fg-header') as HTMLButtonElement);
    /*
     * THE VALUE THE RECORD HOLDS, scoped to the row that states it.
     *
     * `HERFD-XAS` matches TWICE on this screen and BOTH matches are correct, so the
     * scoping is not a query working around noise. The second is an `<option>` in the
     * enum picker `FieldCaptureControl` renders whenever the served `capture` reports
     * the path record-writable AND carries the official schema's own closed set — which
     * `GET .../draft` does for `system.technique` on every response. The shared fixture
     * carried no `capture` at all until it was corrected to match the wire, so this
     * screen had never rendered that control in any test; the picker is asserted below
     * rather than queried away.
     */
    expect(
      [...container.querySelectorAll('.field-value')].map((node) => node.textContent),
    ).toContain('HERFD-XAS');
    const pickers = getAllByLabelText('Change this value') as HTMLSelectElement[];
    expect(pickers.map((select) => select.value)).toContain('HERFD-XAS');

    // three signals: separate labeled segments, never merged; dry-run carries the
    // live server result as a note, no reserved verdict chip pre-export
    expect(getByLabelText('Validation signal').textContent).toContain('dry-run · 2 errors');
    expect(getByLabelText('Coverage signal').textContent).toContain('not exported yet');
    expect(getByLabelText('Advisory signal').textContent).toContain('1 advisory · non-gating');
    expect(container.querySelector('.chip-pass')).toBeNull();
    expect(container.querySelector('.chip-fail')).toBeNull();
  });

  it('backend down → the workbench shows the down state, not a fake record', async () => {
    stubFetchDown();
    const { findByText, queryByText } = renderAt('/record/demo');
    expect(await findByText('Backend Not Running')).toBeInTheDocument();
    expect(queryByText(/Fields Need Your Confirmation/)).toBeNull();
  });

  it('the WorkflowSpine loading skeleton never fabricates field counts before live data arrives', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    // assert synchronously, before the stubbed fetch promises resolve — this is
    // the skeleton the spine renders while the bundle is still loading
    const { findByText, queryByText } = renderAt('/record/demo');
    expect(queryByText(/26 fields/)).toBeNull();
    expect(queryByText(/reviewing \d+ fields/)).toBeNull();
    expect(queryByText(/5 fields need you/)).toBeNull();
    expect(queryByText(/\d+ fields need you/)).toBeNull();
    // let the stubbed fetch settle so the effect update happens inside act()
    await findByText('5 Fields Need Your Confirmation');
  });
});
