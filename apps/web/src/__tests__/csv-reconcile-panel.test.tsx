/**
 * P31.3 — CSV reconciliation + evidence review UI (RECONCILIATION-ONLY).
 *
 * TEST-FIRST (orchestrator-authored; RED until `CsvReconcilePanel` exists). Per the
 * 2026-07-22 human decision, this is a REVIEW surface, never a write surface:
 * uploading a synthetic campaign-sheet CSV shows each mapped value reconciled against
 * the current record (matches / conflicts / absent) as EVIDENCE, and never mutates the
 * official record. The confirmable fields are series/descriptor/edge/asset only, so a
 * CSV FIELD_MAP official field is never manually editable — every item is read-only.
 *
 * The honesty contract these tests pin:
 *   - a visible "review evidence, not a write" banner + synthetic/public-only warning;
 *   - match/conflict/absent shown with a TEXT label (never colour-only);
 *   - both values preserved on conflict; no winner;
 *   - NO Stage / Confirm / Apply / Apply All / Import / Overwrite control anywhere;
 *   - one bounded upload request carrying the current If-Match; no mutation call;
 *   - typed ingress errors render safely (no server path / stack);
 *   - keyboard-reachable file selection + actions.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

import { CsvReconcilePanel } from '../components/CsvReconcilePanel';
import { stubFetchRoutes, stubFetchDown } from '../test/apiFixtures';

const EXP = 'demo';
const VERSION = 'gen000001.3';
const PREVIEW_URL = `POST /api/experiments/${EXP}/ingestion/csv/preview`;

function previewFixture(overrides: Record<string, unknown> = {}) {
  return {
    format: 'isaac_campaign_csv',
    source_name: 'campaign.csv',
    parser_id: 'isaac.extract.structured',
    parser_version: '1',
    source_record_rev: 3,
    row_count: 3,
    recognized_header_count: 5,
    unknown_header_warnings: [
      { code: 'unknown_header', header: 'mystery', message: "Unknown column 'mystery' is ignored (never mapped)." },
    ],
    candidate_count: 3,
    reconciliation_summary: { matches_current: 1, conflicts_with_current: 1, absent_from_record: 1 },
    candidates: [
      {
        field: 'system.facility.beamline', field_label: 'Beamline', experiment_id: EXP,
        proposed_value: '15-2', current_value: '15-2', reconciliation_state: 'matches_current',
        evidence_classification: 'supported', locator: 'row 2, field=beamline', column: 'value',
        source_name: 'campaign.csv', source_format: 'csv', parser_id: 'isaac.extract.structured',
        parser_version: '1', source_record_rev: 3, stale: false, value_state: 'candidate',
        status: 'verified', explanation: 'This value matches the current record; no change is needed.',
      },
      {
        field: 'sample.material.formula', field_label: 'Formula', experiment_id: EXP,
        proposed_value: 'Cu2O', current_value: 'CuO2', reconciliation_state: 'conflicts_with_current',
        evidence_classification: 'supported', locator: 'row 3, field=formula', column: 'value',
        source_name: 'campaign.csv', source_format: 'csv', parser_id: 'isaac.extract.structured',
        parser_version: '1', source_record_rev: 3, stale: false, value_state: 'candidate',
        status: 'verified',
        explanation: 'This value differs from the current record. The record is left unchanged and this disagreement needs human review.',
      },
      {
        field: 'context.temperature_K', field_label: 'Temperature K', experiment_id: EXP,
        proposed_value: 310, current_value: null, reconciliation_state: 'absent_from_record',
        evidence_classification: 'unknown', locator: 'row 4, field=temperature_K', column: 'value',
        source_name: 'campaign.csv', source_format: 'csv', parser_id: 'isaac.extract.structured',
        parser_version: '1', source_record_rev: 3, stale: false, value_state: 'candidate',
        status: 'verified',
        explanation: 'The record has no confirmed value here; this value is unconfirmed and was not written to the record.',
      },
    ],
    warnings: [],
    ...overrides,
  };
}

function renderPanel(props: Partial<{ version: string; onOpenRecord: () => void }> = {}) {
  return render(
    <CsvReconcilePanel experimentId={EXP} version={props.version ?? VERSION} onOpenRecord={props.onOpenRecord} />,
  );
}

function fileInput(): HTMLInputElement {
  const input = document.querySelector('input[type="file"]');
  if (!input) throw new Error('no file input rendered');
  return input as HTMLInputElement;
}

async function selectCsv(text = 'section,field,value,unit,notes\nsystem,beamline,15-2,,\n', name = 'campaign.csv') {
  const file = new File([text], name, { type: 'text/csv' });
  // jsdom File.text() resolves the contents the panel reads before upload.
  fireEvent.change(fileInput(), { target: { files: [file] } });
}

beforeEach(() => {
  vi.restoreAllMocks();
});

// --- pre-upload honesty surface ------------------------------------------------

describe('CsvReconcilePanel — pre-upload', () => {
  it('shows the synthetic/public-only warning', () => {
    renderPanel();
    expect(screen.getByText(/synthetic|public/i)).toBeInTheDocument();
    expect(screen.getByText(/do not upload real|private/i)).toBeInTheDocument();
  });

  it('states this is review evidence, not a write to the record', () => {
    renderPanel();
    expect(
      screen.getByText(/does not change the official record|review evidence/i),
    ).toBeInTheDocument();
  });

  it('states the CSV-only rule and the campaign-sheet format name', () => {
    renderPanel();
    expect(screen.getByText(/\.csv|CSV only|campaign metadata sheet/i)).toBeInTheDocument();
  });

  it('exposes a keyboard-reachable file input labelled for upload', () => {
    renderPanel();
    const input = fileInput();
    expect(input).toHaveAttribute('accept', expect.stringContaining('.csv'));
    // A visible, focusable control triggers the input (button, not a bare div).
    expect(screen.getByRole('button', { name: /upload|choose|select.*(csv|sheet)/i })).toBeInTheDocument();
  });

  it('exposes NO write controls before upload', () => {
    renderPanel();
    for (const bad of [/stage/i, /confirm/i, /^apply/i, /apply all/i, /import/i, /overwrite/i]) {
      expect(screen.queryByRole('button', { name: bad })).toBeNull();
    }
  });
});

// --- FE-2: no phantom tab stop on the hidden file input -----------------------

describe('FE-2 accessibility', () => {
  it('the hidden file input is removed from the tab order (tabIndex -1)', () => {
    renderPanel();
    const input = screen.getByLabelText('Upload a campaign metadata sheet (CSV)');
    expect(input.tabIndex).toBe(-1);
  });

  it('the visible "Upload CSV File" button remains keyboard-reachable', () => {
    renderPanel();
    const button = screen.getByRole('button', { name: /upload csv file/i });
    expect(button.tabIndex).toBe(0);
  });

  it('the hidden input keeps its accessible name and file type', () => {
    renderPanel();
    const input = screen.getByLabelText('Upload a campaign metadata sheet (CSV)') as HTMLInputElement;
    expect(input).toHaveAccessibleName('Upload a campaign metadata sheet (CSV)');
    expect(input.type).toBe('file');
  });
});

// --- upload + reconciliation review -------------------------------------------

describe('CsvReconcilePanel — reconciliation review', () => {
  it('sends exactly one bounded upload carrying the current If-Match and no mutation call', async () => {
    const hits = stubFetchRoutes({ [PREVIEW_URL]: { body: previewFixture() } });
    renderPanel();
    await selectCsv();
    await screen.findByText(/Beamline/);
    const previews = hits.filter((h) => h === PREVIEW_URL);
    expect(previews).toHaveLength(1);
    // the request used text/csv + the quoted If-Match, and hit NO answers/edit route.
    const calls = (globalThis.fetch as unknown as { mock: { calls: unknown[][] } }).mock.calls;
    const [, init] = calls.find(([u]) => String(u).includes('/ingestion/csv/preview'))!;
    const headers = (init as RequestInit).headers as Record<string, string>;
    expect(headers['Content-Type']).toMatch(/text\/csv/);
    expect(headers['If-Match']).toBe(`"${VERSION}"`);
    expect(calls.some(([u]) => /\/answers|\/edit/.test(String(u)))).toBe(false);
  });

  it('double-activating the input does not fire duplicate uploads for one file', async () => {
    const hits = stubFetchRoutes({ [PREVIEW_URL]: { body: previewFixture() } });
    renderPanel();
    await selectCsv();
    await screen.findByText(/Beamline/);
    // a second change event with the SAME (already-processed) selection must not re-upload
    fireEvent.change(fileInput(), { target: { files: [] } });
    await waitFor(() => expect(hits.filter((h) => h === PREVIEW_URL)).toHaveLength(1));
  });

  it('renders official fields with match / conflict / absent shown as TEXT (not colour-only)', async () => {
    stubFetchRoutes({ [PREVIEW_URL]: { body: previewFixture() } });
    renderPanel();
    await selectCsv();
    await screen.findByText(/Beamline/);
    // official path present for traceability
    expect(screen.getByText('system.facility.beamline')).toBeInTheDocument();
    // each state carries a readable word, never colour alone
    expect(screen.getByText(/matches/i)).toBeInTheDocument();
    expect(screen.getByText(/conflict/i)).toBeInTheDocument();
    expect(screen.getByText(/absent|not in the record|no.*value/i)).toBeInTheDocument();
  });

  it('shows both the proposed and current value for a conflict (no winner chosen)', async () => {
    stubFetchRoutes({ [PREVIEW_URL]: { body: previewFixture() } });
    renderPanel();
    await selectCsv();
    const formulaRow = (await screen.findByText('sample.material.formula')).closest('*')!.parentElement!;
    const scope = within(formulaRow.parentElement ?? formulaRow);
    expect(scope.getByText('Cu2O')).toBeInTheDocument(); // proposed
    expect(scope.getByText('CuO2')).toBeInTheDocument(); // current — preserved, not overwritten
  });

  it('shows the evidence classification and the row+column locator', async () => {
    stubFetchRoutes({ [PREVIEW_URL]: { body: previewFixture() } });
    renderPanel();
    await selectCsv();
    await screen.findByText(/Beamline/);
    expect(screen.getAllByText(/supported/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/row 2/)).toBeInTheDocument();
  });

  it('surfaces an unknown-header warning without mapping it', async () => {
    stubFetchRoutes({ [PREVIEW_URL]: { body: previewFixture() } });
    renderPanel();
    await selectCsv();
    await screen.findByText(/Beamline/);
    expect(screen.getByText(/mystery/)).toBeInTheDocument();
    expect(screen.getByText(/ignored|never mapped|not mapped/i)).toBeInTheDocument();
  });

  it('exposes NO write controls after reconciliation, only safe review actions', async () => {
    stubFetchRoutes({ [PREVIEW_URL]: { body: previewFixture() } });
    renderPanel();
    await selectCsv();
    await screen.findByText(/Beamline/);
    for (const bad of [/stage/i, /^confirm/i, /^apply/i, /apply all/i, /^import/i, /overwrite/i]) {
      expect(screen.queryByRole('button', { name: bad })).toBeNull();
    }
    // safe actions exist
    expect(screen.getByRole('button', { name: /discard|clear|upload another/i })).toBeInTheDocument();
  });

  it('states a reconciled official field is not editable through the app (read-only evidence)', async () => {
    stubFetchRoutes({ [PREVIEW_URL]: { body: previewFixture() } });
    renderPanel();
    await selectCsv();
    await screen.findByText(/Beamline/);
    // No per-field "edit"/"apply" affordance for a FIELD_MAP official field.
    expect(screen.queryByRole('button', { name: /edit this field|apply this|write/i })).toBeNull();
    expect(
      screen.getByText(/review only|cannot be updated|not.*editable|evidence only/i),
    ).toBeInTheDocument();
  });
});

// --- errors, staleness, discard ------------------------------------------------

describe('CsvReconcilePanel — errors & lifecycle', () => {
  it('renders a typed ingress error safely (no server path / stack)', async () => {
    stubFetchRoutes({
      [PREVIEW_URL]: { status: 422, body: { error: 'duplicate_header', message: 'A header column name is duplicated.' } },
    });
    renderPanel();
    await selectCsv();
    const msg = await screen.findByText(/duplicated|could not|invalid|rejected/i);
    expect(msg).toBeInTheDocument();
    const blob = document.body.textContent ?? '';
    for (const bad of ['/data/', '/Users/', 'Traceback', 'isaac-workspace']) {
      expect(blob).not.toContain(bad);
    }
  });

  it('shows a backend-unreachable state without crashing', async () => {
    stubFetchDown();
    renderPanel();
    await selectCsv();
    expect(await screen.findByText(/unreachable|unavailable|could not reach|try again|retry/i)).toBeInTheDocument();
  });

  it('marks the reconciliation stale when the record version advances', async () => {
    stubFetchRoutes({ [PREVIEW_URL]: { body: previewFixture() } });
    const { rerender } = renderPanel();
    await selectCsv();
    await screen.findByText(/Beamline/);
    // the live record advanced under the shown preview
    rerender(<CsvReconcilePanel experimentId={EXP} version={'gen000001.4'} />);
    expect(await screen.findByText(/out of date|stale|record.*changed|re-?upload|re-?run/i)).toBeInTheDocument();
  });

  it('discards the preview and returns to the upload prompt', async () => {
    stubFetchRoutes({ [PREVIEW_URL]: { body: previewFixture() } });
    renderPanel();
    await selectCsv();
    await screen.findByText(/Beamline/);
    fireEvent.click(screen.getByRole('button', { name: /discard|clear/i }));
    await waitFor(() => expect(screen.queryByText('system.facility.beamline')).toBeNull());
    expect(screen.getByRole('button', { name: /upload|choose|select.*(csv|sheet)/i })).toBeInTheDocument();
  });
});
