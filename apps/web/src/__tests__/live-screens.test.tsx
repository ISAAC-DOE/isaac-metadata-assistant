import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, within } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { AppRoutes } from '../App';
import { RUN_COMMAND } from '../lib/api';
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
    const { findByText, getByText } = renderAt('/load');

    fireEvent.click(getByText(/structured formats only/));

    expect(await findByText(/Blocked by governance\./)).toBeInTheDocument();
    expect(getByText(new RegExp(uploadsBlocked.reason))).toBeInTheDocument();
    // the governance banner stays mounted alongside the blocked state
    expect(getByText(/Synthetic mode\./)).toBeInTheDocument();
  });

  it('uploads with the backend down → Backend Not Running with the run command, never governance copy', async () => {
    stubFetchDown();
    const { findByText, getByText, queryByText } = renderAt('/load');

    fireEvent.click(getByText(/structured formats only/));

    expect(await findByText('Backend Not Running')).toBeInTheDocument();
    expect(getByText(RUN_COMMAND)).toBeInTheDocument();
    // an unreachable backend must never masquerade as a governance refusal
    expect(queryByText(/Blocked by governance/)).toBeNull();
    expect(queryByText(new RegExp(uploadsBlocked.reason))).toBeNull();
  });

  it('Run Demo renders the real POST /api/demo/run steps — the old mock figures are gone', async () => {
    stubFetchRoutes({ 'POST /api/demo/run': { body: demoRunDraftOnly } });
    const { findByText, getByText, queryByText } = renderAt('/load');

    fireEvent.click(getByText('Run Demo'));

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
    // inline per-field evidence is still present in the main column (truth stays visible)
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

  // P33 S4 (D9/C2) — the needs-you banner is a NUMBERED list. Each item shows a
  // concise structured label as the primary line and its technical locator once
  // as a demoted mono token; a raw identifier is never the primary label.
  it('renders the needs-you banner as a numbered list with concise labels and locators shown once', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { container, findByText, getByText, getAllByText, queryByText } = renderAt(
      '/record/demo',
    );

    await findByText('5 Fields Need Your Confirmation');

    // an ordered (numbered) list, one <li> per pending item
    const list = container.querySelector('ol.needsyou-list');
    expect(list).not.toBeNull();
    expect(list!.querySelectorAll('li')).toHaveLength(5);
    // a visible ordinal accompanies each item
    expect(list!.querySelectorAll('.needsyou-num')).toHaveLength(5);

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

  it('shows live pending as Needs You and live draft fields; signals stay three labeled segments', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { container, findByText, getByText, getByLabelText } = renderAt('/record/demo');

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

    // draft groups fed by /draft
    expect(getByText('System & Instrument')).toBeInTheDocument();
    expect(getByText('HERFD-XAS')).toBeInTheDocument();

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
