import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
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
    expect(getByText('draft ok: True')).toBeInTheDocument();

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
  it('keeps Evidence above the Assistant in DOM order (truth above advisory)', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { container, findByText } = renderAt('/record/demo');

    await findByText('5 Fields Need Your Confirmation');

    const evidence = container.querySelector('.ev-panel-card');
    const assistant = container.querySelector('.assistant');
    expect(evidence).not.toBeNull();
    expect(assistant).not.toBeNull();
    const position = evidence!.compareDocumentPosition(assistant!);
    expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    // and they are separated by the hard divider
    expect(container.querySelector('.right-divider')).not.toBeNull();
  });

  it('shows live pending as Needs You and live draft fields; signals stay three labeled segments', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    const { container, findByText, getByText, getByLabelText } = renderAt('/record/demo');

    // needs-you banner fed by /pending
    await findByText('5 Fields Need Your Confirmation');
    expect(getByText('What is the sha256 of the processing notebook?')).toBeInTheDocument();

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
});
