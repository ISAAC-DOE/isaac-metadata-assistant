/*
 * THE RECORD-LIFECYCLE DEFECTS AN INDEPENDENT QA AUDIT MEASURED IN A REAL BROWSER
 * (2026-10-11, at `1879baef`), each pinned against the screen a scientist uses.
 *
 *   A-02  a record with runs exported files that could not be retrieved — filenames
 *         with no View or Download, and nothing at all after a reload;
 *   A-06  "regenerate the record" named a control that does not exist;
 *   A-01  a confirmed spectrum / QC verdict / descriptor could be seen and fixed only
 *   A-04  in the visit that answered it — Complete and Export sent the reader in a loop;
 *   A-03  a series the official schema refuses was refused only at export, as raw text;
 *   A-05  the rail's Capture/Proposals/Runs/Activity links did nothing on Complete and
 *   A-20  Export, and Export dropped the Evidence Trail row;
 *   A-07  answering the last question left the spine on "Complete Metadata" until reload.
 *
 * Every API response here is a fixture shaped like the real server's; the backend half
 * of each contract is pinned in `apps/api/tests/test_run_artifacts_read.py`,
 * `test_structured_answers_read.py` and `test_structured_answer_official_shape.py`.
 */
import { describe, it, expect, afterEach, vi, type Mock } from 'vitest';
import { render, fireEvent, waitFor, within, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppRoutes } from '../App';
import {
  FAN_OUT_RUN_IDS,
  bundleRoutes,
  completePendingPage,
  exportedReadyRoutes,
  experimentDetail,
  fanOutExportedRoutes,
  fanOutRunArtifacts,
  fixtureWorkflow,
  pendingResponse,
  pendingRoutes,
  stubFetchRoutes,
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

/*
 * THE PER-TEST DEADLINE IS RAISED FOR THIS FILE, AND THE WAITS INSIDE IT ARE NOT
 * WIDENED TO MATCH. Every test here renders a whole record screen through the real
 * router — Export Readiness, Complete, or the Record Fields workspace with its eight
 * self-fetching panels — and on a contended host one such mount measured ~9 s against
 * vitest's 5 s default, while the same test runs in ~3 s on a quiet one. A raised
 * deadline changes nothing a test asserts; it only stops a slow machine from reading
 * as a failed product. The explicit `findBy*` timeouts stay below it, so a genuine
 * absence still fails on its own query, naming what was missing.
 */
vi.setConfig({ testTimeout: 20_000 });

const BASE = '/api/experiments/demo';

const SERIES = [
  {
    series_id: 'example_series',
    independent_variables: [{ name: 'incident_energy', unit: 'eV', values: [1, 2] }],
    channels: [{ name: 'absorption', unit: 'mu_normalized', role: 'primary_signal', values: [0.1, 0.2] }],
  },
];
const QC = { status: 'valid', evidence: 'I0 stable.' };
const DESCRIPTOR = {
  name: 'inflection_point_energy',
  kind: 'absolute',
  source: 'manual',
  value: 9001.2,
  unit: 'eV',
  uncertainty: { sigma: 0.01 },
};

function structuredAnswers(series: unknown = SERIES) {
  return {
    experiment_id: 'demo',
    experiment_version: '1.0',
    level: 'record',
    units: [
      {
        run_id: null,
        run_label: null,
        version: '1.0',
        edit_at: 'POST /api/experiments/{experiment_id}/edit',
        exported: false,
        answers: {
          series: { state: 'confirmed', value: series, editable: true },
          qc: { state: 'confirmed', value: QC, editable: true },
          descriptor: {
            state: 'confirmed',
            value: DESCRIPTOR,
            editable: true,
            label: 'scientist_entered',
            count: 1,
          },
        },
      },
    ],
    total: 1,
    returned: 1,
    offset: 0,
    limit: 10,
  };
}

/** A Complete screen with NOTHING open — the state the audit's loop arrived in. */
function nothingOpenRoutes() {
  return {
    ...bundleRoutes('demo'),
    [`GET ${BASE}`]: {
      body: {
        ...experimentDetail,
        id: 'demo',
        pending_count: 0,
        workflow: fixtureWorkflow({ pending_count: 0, draft_ok: false, ready: false, exported: false, rev: 3 }),
      },
    },
    ...pendingRoutes(BASE, { pending: [] }),
  };
}

/* ── A-02 / A-06 · exported run records are retrievable, and say if they changed ── */

describe('A-02 · a fan-out record’s exported files can be viewed and downloaded after a reload', () => {
  it('lists every exported run with View and Download, read from the server on load', async () => {
    const calls = stubFetchRoutes(fanOutExportedRoutes('demo'));
    const { container } = renderAt('/record/demo/export');
    // Waited for on a FILENAME (a cheap text query) and then located by its landmark:
    // a role query recomputes every accessible name in this large screen on each poll,
    // which is what made the first version of this wait time out on a cold start.
    await screen.findByText(`${FAN_OUT_RUN_IDS[0]}.json`, undefined, { timeout: 4000 });
    const region = container.querySelector<HTMLElement>('section.run-artifacts')!;
    expect(region.getAttribute('aria-labelledby')).toBe('run-artifacts-heading');
    expect(within(region).getByRole('heading', { name: 'Exported Run Records' })).toBeInTheDocument();
    expect(calls.some((c) => c.startsWith(`GET ${BASE}/run-artifacts`))).toBe(true);
    for (const runId of FAN_OUT_RUN_IDS) {
      expect(within(region).getByText(`${runId}.json`)).toBeInTheDocument();
      expect(within(region).getByText(`${runId}.evidence.json`)).toBeInTheDocument();
    }
    for (const label of ['Run 1', 'Run 2']) {
      expect(
        within(region).getByRole('button', { name: `Download official record for ${label}` }),
      ).toBeEnabled();
      expect(
        within(region).getByRole('button', { name: `View evidence sidecar for ${label}` }),
      ).toBeEnabled();
    }
  });

  it('View opens the ONE dialog with that run’s written content and names the run', async () => {
    stubFetchRoutes(fanOutExportedRoutes('demo'));
    renderAt('/record/demo/export');
    // Waited for on a filename, for the reason the first test in this block gives.
    await screen.findByText(`${FAN_OUT_RUN_IDS[1]}.json`, undefined, { timeout: 4000 });
    fireEvent.click(screen.getByRole('button', { name: 'View official record for Run 2' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText(/Run 2/)).toBeInTheDocument();
    expect(dialog.textContent).toContain(FAN_OUT_RUN_IDS[1]);
    expect(dialog.textContent).not.toContain(FAN_OUT_RUN_IDS[0]);
  });

  it('Download hands the browser the written file under its own basename', async () => {
    stubFetchRoutes(fanOutExportedRoutes('demo'));
    const created: Blob[] = [];
    const createObjectURL = vi.fn((b: Blob) => {
      created.push(b);
      return 'blob:x';
    });
    vi.stubGlobal('URL', { ...URL, createObjectURL, revokeObjectURL: vi.fn() });
    const clicked: string[] = [];
    const orig = HTMLAnchorElement.prototype.click;
    HTMLAnchorElement.prototype.click = function () {
      clicked.push(this.download);
    };
    try {
      renderAt('/record/demo/export');
      await screen.findByText(`${FAN_OUT_RUN_IDS[0]}.json`, undefined, { timeout: 4000 });
      fireEvent.click(
        screen.getByRole('button', { name: 'Download evidence sidecar for Run 1' }),
      );
      expect(clicked).toEqual([`${FAN_OUT_RUN_IDS[0]}.evidence.json`]);
      const text = await new Promise<string>((resolve) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.readAsText(created[0]);
      });
      expect(JSON.parse(text).record_id).toBe(FAN_OUT_RUN_IDS[0]);
    } finally {
      HTMLAnchorElement.prototype.click = orig;
    }
  });

  it('A-06 · a run changed since export says so on ITS row, and nothing offers to regenerate', async () => {
    stubFetchRoutes({
      ...fanOutExportedRoutes('demo'),
      [`GET ${BASE}/run-artifacts`]: { body: fanOutRunArtifacts('demo', { stale: FAN_OUT_RUN_IDS[1] }) },
    });
    const { container } = renderAt('/record/demo/export');
    const region = await screen.findByRole('region', { name: 'Exported Run Records' });
    const rows = region.querySelectorAll('.run-artifact');
    expect(rows).toHaveLength(2);
    expect(rows[0].getAttribute('data-state')).toBe('current');
    expect(within(rows[0] as HTMLElement).queryByText('Changed Since Export')).toBeNull();
    expect(within(rows[1] as HTMLElement).getByText('Changed Since Export')).toBeInTheDocument();
    expect(rows[1].textContent).toMatch(/does not include the later changes/);
    expect(container.textContent).not.toMatch(/regenerate/i);
  });

  it('CONTROL — a record with no runs never asks for run artifacts', async () => {
    const calls = stubFetchRoutes(exportedReadyRoutes('demo'));
    renderAt('/record/demo/export');
    await screen.findByText('Valid against official ISAAC schema v1.05.');
    expect(calls.some((c) => c.includes('/run-artifacts'))).toBe(false);
    expect(screen.queryByRole('region', { name: 'Exported Run Records' })).toBeNull();
  });
});

/* ── A-01 / A-04 · confirmed structured answers are visible and correctable later ── */

describe('A-01 · nothing open is no longer a dead end', () => {
  it('Complete shows every confirmed answer from the RECORD, not from this visit', async () => {
    stubFetchRoutes({
      ...nothingOpenRoutes(),
      [`GET ${BASE}/structured-answers`]: { body: structuredAnswers() },
    });
    renderAt('/record/demo/complete');
    const panel = await screen.findByRole('region', { name: 'Confirmed Answers' });
    expect(within(panel).getByText('Reduced Spectrum')).toBeInTheDocument();
    expect(within(panel).getByText(/example_series · 1 channel/)).toBeInTheDocument();
    expect(within(panel).getByText('valid')).toBeInTheDocument();
    expect(within(panel).getByText(/9001\.2 eV/)).toBeInTheDocument();
    for (const label of ['Reduced Spectrum', 'QC Verdict', 'Scientific Descriptor']) {
      expect(within(panel).getByRole('button', { name: `Edit ${label}` })).toBeEnabled();
    }
  });

  it('Edit opens the STORED value — nothing invented — and Save corrects it through /edit', async () => {
    let edits = 0;
    const calls = stubFetchRoutes({
      ...nothingOpenRoutes(),
      [`GET ${BASE}/structured-answers`]: () => ({ body: structuredAnswers() }),
      [`POST ${BASE}/edit`]: () => {
        edits += 1;
        return {
          body: {
            pending: [],
            pending_page: completePendingPage([]),
            status: 'in_review',
            rev: 4,
            updated_utc: '2099-04-02T09:16:00Z',
            version: '1.1',
            workflow: fixtureWorkflow({ pending_count: 0, draft_ok: true, ready: true, exported: false, rev: 4 }),
            invalidation: {
              changed: true,
              rev: 4,
              changed_fields: ['series'],
              reopened_steps: [],
              artifact: { state: 'none', reason: null },
              reason: 'Updated 1 field(s); no downstream steps reopened.',
            },
          },
        };
      },
    });
    renderAt('/record/demo/complete');
    fireEvent.click(await screen.findByRole('button', { name: 'Edit Reduced Spectrum' }));
    const box = (await screen.findByLabelText('Series JSON')) as HTMLTextAreaElement;
    expect(JSON.parse(box.value)).toEqual(SERIES);
    const corrected = [{ ...SERIES[0], series_id: 'corrected_series' }];
    fireEvent.change(box, { target: { value: JSON.stringify(corrected) } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(edits).toBe(1));
    const editCall = ((globalThis.fetch as Mock).mock.calls as [string, RequestInit][]).find(
      ([url, init]) => url.endsWith('/demo/edit') && init?.method === 'POST',
    )!;
    expect(JSON.parse(String(editCall[1].body))).toEqual({
      answers: { series: corrected },
      confirmed_by_user: true,
    });
    expect((editCall[1].headers as Record<string, string>)['If-Match']).toBe('"1.0"');
    // The panel RE-READS the record after the correction rather than patching locally.
    await waitFor(() =>
      expect(calls.filter((c) => c.startsWith(`GET ${BASE}/structured-answers`)).length).toBe(2),
    );
  });

  it('A-03 · a correction the official schema refuses names each part and the schema’s words', async () => {
    stubFetchRoutes({
      ...nothingOpenRoutes(),
      [`GET ${BASE}/structured-answers`]: { body: structuredAnswers() },
      [`POST ${BASE}/edit`]: {
        status: 422,
        body: {
          error: 'official_shape_mismatch',
          experiment_id: 'demo',
          key: 'series',
          keys: ['series'],
          schema_errors: [
            {
              key: 'series',
              path: 'measurement.series.0',
              message: "'independent_variables' is a required property",
            },
          ],
          schema_errors_more: false,
          message: 'x',
        },
      },
    });
    renderAt('/record/demo/complete');
    fireEvent.click(await screen.findByRole('button', { name: 'Edit Reduced Spectrum' }));
    const box = await screen.findByLabelText('Series JSON');
    fireEvent.change(box, { target: { value: '[{"series_id": "x"}]' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    const notice = await screen.findByTestId('shape-mismatch-notice');
    expect(notice.textContent).toContain('measurement.series.0');
    // VERBATIM — the schema's own sentence, not a paraphrase.
    expect(notice.textContent).toContain("'independent_variables' is a required property");
    expect(notice.textContent).toMatch(/the stored value is unchanged/);
  });

  it('an OPEN question links to Complete instead of offering a correction that would refuse', async () => {
    const open = structuredAnswers();
    open.units[0].answers.series = { state: 'open', value: null, editable: false } as never;
    stubFetchRoutes({
      ...bundleRoutes('demo'),
      [`GET ${BASE}/structured-answers`]: { body: open },
    });
    renderAt('/record/demo');
    const panel = await screen.findByRole('region', { name: 'Confirmed Answers' });
    expect(within(panel).getByText('Not answered yet')).toBeInTheDocument();
    expect(within(panel).queryByRole('button', { name: 'Edit Reduced Spectrum' })).toBeNull();
    expect(
      within(panel).getByRole('link', { name: /Answer in/ }).getAttribute('href'),
    ).toBe('/record/demo/complete');
  });
});

/* ── A-03 · the answering path names what the official schema refused ── */

describe('A-03 · an answer the official schema refuses is explained at answer time', () => {
  it('names each failing record path with the schema’s message, and the question stays open', async () => {
    const seriesQuestion = {
      id: 'series',
      kind: 'series',
      question: 'Provide the reduced spectrum.',
      about: 'reduced_spectrum',
      demo_answer: null,
    };
    stubFetchRoutes({
      ...bundleRoutes('demo'),
      ...pendingRoutes(BASE, { pending: [seriesQuestion] }),
      [`POST ${BASE}/answers`]: {
        status: 422,
        body: {
          error: 'official_shape_mismatch',
          experiment_id: 'demo',
          key: 'series',
          keys: ['series'],
          schema_errors: [
            { key: 'series', path: 'measurement.series.0', message: "'channels' is a required property" },
          ],
          schema_errors_more: false,
          message: 'x',
        },
      },
    });
    renderAt('/record/demo/complete');
    const box = await screen.findByLabelText('Series JSON');
    fireEvent.change(box, { target: { value: '[{"series_id": "x"}]' } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    const notice = await screen.findByTestId('shape-mismatch-notice');
    expect(notice.textContent).toContain("'channels' is a required property");
    expect(notice.textContent).toMatch(/the question is still open/);
  });
});

/* ── A-05 / A-20 · the rail navigates from the sub-screens, and is the same everywhere ── */

describe('A-05 · rail destinations reach the record screen from Complete and Export', () => {
  const railHrefs = () => {
    const capture = screen.getByRole('navigation', { name: 'Data Capture' });
    const workspaces = screen.getByRole('navigation', { name: 'Record workspaces' });
    const href = (nav: HTMLElement, name: string) =>
      within(nav).getByRole('link', { name }).getAttribute('href');
    return {
      capture: href(capture, 'Capture'),
      proposals: href(capture, 'Proposals'),
      runs: href(capture, 'Runs'),
      activity: href(workspaces, 'Activity'),
    };
  };

  it('on /complete every row points at /record/<id>, never at /complete itself', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    renderAt('/record/demo/complete');
    await screen.findByRole('navigation', { name: 'Record workspaces' });
    expect(railHrefs()).toEqual({
      capture: '/record/demo?view=capture',
      proposals: '/record/demo?view=proposals',
      runs: '/record/demo?view=runs',
      activity: '/record/demo?view=activity',
    });
  });

  it('on /export too — and the Evidence Trail row is there, as on every record screen', async () => {
    stubFetchRoutes(exportedReadyRoutes('demo'));
    renderAt('/record/demo/export');
    const workspaces = await screen.findByRole('navigation', { name: 'Record workspaces' });
    expect(railHrefs().runs).toBe('/record/demo?view=runs');
    expect(
      within(workspaces).getByRole('link', { name: /^Evidence Trail/ }).getAttribute('href'),
    ).toBe('/record/demo/evidence');
  });

  it('CONTROL — on the record screen itself the row still copies the record’s own query', async () => {
    stubFetchRoutes(bundleRoutes('demo'));
    renderAt('/record/demo?view=fields&at=field%3Asample.material.name');
    const capture = await screen.findByRole('navigation', { name: 'Data Capture' });
    const runs = within(capture).getByRole('link', { name: 'Runs' }).getAttribute('href')!;
    expect(runs.startsWith('/record/demo?')).toBe(true);
    expect(runs).toContain('view=runs');
    expect(runs).toContain('at=');
  });
});

/* ── A-07 · the spine follows the server's re-derived workflow after an answer ── */

describe('A-07 · answering the last question moves the workflow without a reload', () => {
  it('adopts the workflow the answer response carries', async () => {
    const only = [pendingResponse.pending[0]];
    stubFetchRoutes({
      ...bundleRoutes('demo'),
      [`GET ${BASE}`]: {
        body: {
          ...experimentDetail,
          id: 'demo',
          pending_count: 1,
          workflow: fixtureWorkflow({ pending_count: 1, draft_ok: false, ready: false, exported: false, rev: 3 }),
        },
      },
      ...pendingRoutes(BASE, { pending: only }),
      [`POST ${BASE}/answers`]: {
        body: {
          pending: [],
          pending_page: completePendingPage([]),
          status: 'ready_to_export',
          rev: 4,
          updated_utc: '2099-04-02T09:16:00Z',
          version: '1.1',
          workflow: fixtureWorkflow({ pending_count: 0, draft_ok: true, ready: true, exported: false, rev: 4 }),
          invalidation: {
            changed: true,
            rev: 4,
            changed_fields: [only[0].id],
            reopened_steps: [],
            artifact: { state: 'none', reason: null },
            reason: 'Updated 1 field(s); no downstream steps reopened.',
          },
        },
      },
    });
    const { container } = renderAt('/record/demo/complete');
    const step = () => container.querySelector('.spine-step:nth-child(2)')!;
    await screen.findByText(only[0].question);
    expect(step().textContent).toMatch(/Current requirement/);
    fireEvent.change(screen.getByLabelText('Asset Hash'), { target: { value: 'a1'.repeat(32) } });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    await screen.findByText('All Fields Resolved');
    await waitFor(() => expect(step().textContent).toMatch(/Complete$/));
    expect(step().textContent).not.toMatch(/Current requirement/);
    // …and the later steps are no longer reported locked.
    const export_ = container.querySelector('.spine-step:nth-child(5)')!;
    expect(export_.textContent).not.toMatch(/Locked/);
  });
});


/* ── independent review of this slice: I-2, I-3 and minor (c) ── */

function editResponse(version: string, stale = false) {
  return {
    pending: [],
    pending_page: completePendingPage([]),
    status: 'done',
    rev: 5,
    updated_utc: '2099-04-02T09:20:00Z',
    version,
    workflow: fixtureWorkflow({ pending_count: 0, draft_ok: true, ready: true, exported: true, rev: 5 }),
    invalidation: {
      changed: true,
      rev: 5,
      changed_fields: ['series'],
      reopened_steps: [],
      artifact: stale
        ? { state: 'stale', reason: 'This record has changed since it was exported.' }
        : { state: 'none', reason: null },
      reason: 'Updated 1 field(s); no downstream steps reopened.',
    },
  };
}

describe('review I-3 · an EXPORTED unit says its file will not change BEFORE the edit', () => {
  it('states it above the answers, again in the editor, and after the save', async () => {
    const exported = structuredAnswers();
    exported.units[0].exported = true;
    stubFetchRoutes({
      ...nothingOpenRoutes(),
      [`GET ${BASE}/structured-answers`]: { body: exported },
      [`POST ${BASE}/edit`]: { body: editResponse('1.1', true) },
    });
    renderAt('/record/demo/complete');
    const panel = await screen.findByRole('region', { name: 'Confirmed Answers' });
    // BEFORE: visible without opening anything.
    expect(within(panel).getByText(/official record has been exported/)).toBeInTheDocument();
    expect(within(panel).getByText(/will not include it/)).toBeInTheDocument();
    fireEvent.click(within(panel).getByRole('button', { name: 'Edit Reduced Spectrum' }));
    expect(
      await within(panel).findByText(/The exported official record will not change/),
    ).toBeInTheDocument();
    const box = (await screen.findByLabelText('Series JSON')) as HTMLTextAreaElement;
    fireEvent.change(box, {
      target: { value: JSON.stringify([{ ...SERIES[0], series_id: 'after_export' }]) },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    // AFTER: kept, beside the row it is about.
    expect(
      await within(panel).findByText(/Saved\. The exported file no longer matches this record/),
    ).toBeInTheDocument();
  });

  it('CONTROL — a unit that was never exported carries no such note', async () => {
    stubFetchRoutes({
      ...nothingOpenRoutes(),
      [`GET ${BASE}/structured-answers`]: { body: structuredAnswers() },
    });
    renderAt('/record/demo/complete');
    const panel = await screen.findByRole('region', { name: 'Confirmed Answers' });
    expect(within(panel).queryByText(/has been exported/)).toBeNull();
  });
});

describe('review I-2 · a descriptor the form cannot carry back is shown, not offered', () => {
  it('renders the stored descriptor and the server’s reason, with no Edit control', async () => {
    const rich = structuredAnswers();
    rich.units[0].answers.descriptor = {
      state: 'confirmed',
      value: { ...DESCRIPTOR, value: '42', definition: 'first-derivative maximum' },
      editable: false,
      label: 'scientist_entered',
      count: 1,
      reason:
        'This value cannot be corrected here without changing it: it carries `definition`, which the form does not show. Saving the form would change or drop part of it, so it is shown read-only.',
    } as never;
    stubFetchRoutes({
      ...nothingOpenRoutes(),
      [`GET ${BASE}/structured-answers`]: { body: rich },
    });
    renderAt('/record/demo/complete');
    const panel = await screen.findByRole('region', { name: 'Confirmed Answers' });
    expect(within(panel).getByText(/it carries `definition`/)).toBeInTheDocument();
    expect(within(panel).queryByRole('button', { name: 'Edit Scientific Descriptor' })).toBeNull();
    // The other two are still correctable.
    expect(within(panel).getByRole('button', { name: 'Edit Reduced Spectrum' })).toBeEnabled();
  });
});

describe('review minor (c) · paging never costs the reader an open editor or their place', () => {
  const runUnit = (i: number) => ({
    run_id: `RUN${String(i).padStart(23, '0')}`,
    run_label: `Run ${i}`,
    version: `v${i}`,
    edit_at: 'POST /api/experiments/{experiment_id}/runs/{run_id}/edit',
    exported: false,
    answers: structuredAnswers().units[0].answers,
  });
  const runPage = (from: number, to: number, total: number) => ({
    experiment_id: 'demo',
    experiment_version: '1.0',
    level: 'run',
    units: Array.from({ length: to - from }, (_, k) => runUnit(from + k + 1)),
    total,
    returned: to - from,
    offset: from,
    limit: 10,
  });

  it('a failed Show More keeps an open editor and what was typed in it', async () => {
    stubFetchRoutes({
      ...nothingOpenRoutes(),
      [`GET ${BASE}/structured-answers`]: (_init?: RequestInit, path?: string) =>
        path && path.includes('offset=')
          ? { status: 503, body: { error: 'experiment_storage_unavailable' } }
          : { body: runPage(0, 10, 12) },
    });
    renderAt('/record/demo/complete');
    const panel = await screen.findByRole('region', { name: 'Confirmed Answers' });
    fireEvent.click(within(panel).getByRole('button', { name: 'Edit Reduced Spectrum for Run 1' }));
    const box = (await screen.findByLabelText('Series JSON')) as HTMLTextAreaElement;
    fireEvent.change(box, { target: { value: '[{"series_id": "half-typed"' } });
    fireEvent.click(within(panel).getByRole('button', { name: 'Show More Runs' }));
    await waitFor(() =>
      expect(within(panel).getAllByRole('button', { name: /Retry|Try Again/i }).length).toBeGreaterThan(0),
    );
    expect((screen.getByLabelText('Series JSON') as HTMLTextAreaElement).value).toBe(
      '[{"series_id": "half-typed"',
    );
  });

  it('a save on a later page re-reads ONLY that run and keeps every loaded page', async () => {
    const calls = stubFetchRoutes({
      ...nothingOpenRoutes(),
      [`GET ${BASE}/structured-answers`]: (_init?: RequestInit, path?: string) => {
        if (path && path.includes('run_id=')) {
          const fresh = runUnit(11);
          fresh.version = 'v11b';
          return { body: { ...runPage(10, 11, 1), units: [fresh] } };
        }
        return path && path.includes('offset=10')
          ? { body: runPage(10, 12, 12) }
          : { body: runPage(0, 10, 12) };
      },
      [`GET ${BASE}/runs/RUN00000000000000000000011`]: { body: { run: { version: 'v11' } } },
      [`POST ${BASE}/runs/RUN00000000000000000000011/edit`]: { body: editResponse('1.1') },
    });
    renderAt('/record/demo/complete');
    const panel = await screen.findByRole('region', { name: 'Confirmed Answers' });
    fireEvent.click(within(panel).getByRole('button', { name: 'Show More Runs' }));
    await within(panel).findByText('Run 12');
    fireEvent.click(within(panel).getByRole('button', { name: 'Edit Reduced Spectrum for Run 11' }));
    const box = (await screen.findByLabelText('Series JSON')) as HTMLTextAreaElement;
    fireEvent.change(box, {
      target: { value: JSON.stringify([{ ...SERIES[0], series_id: 'run11_fixed' }]) },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(calls.some((c) => c.includes('/structured-answers?') && c.includes('run_id='))).toBe(true),
    );
    // Every page is still on screen — the save did not send the reader back to page one.
    expect(within(panel).getByText('Run 1')).toBeInTheDocument();
    expect(within(panel).getByText('Run 12')).toBeInTheDocument();
  });
});

describe('re-review (minor) · a stored value is labelled by what its evidence IS', () => {
  it('an extraction reads “From Recorded Evidence”, never “Confirmed by You”', async () => {
    const extracted = structuredAnswers();
    (extracted.units[0].answers.qc as Record<string, unknown>).confirmation = 'from_evidence';
    (extracted.units[0].answers.series as Record<string, unknown>).confirmation = 'confirmed';
    (extracted.units[0].answers.descriptor as Record<string, unknown>).confirmation = 'no_evidence';
    stubFetchRoutes({
      ...nothingOpenRoutes(),
      [`GET ${BASE}/structured-answers`]: { body: extracted },
    });
    renderAt('/record/demo/complete');
    const panel = await screen.findByRole('region', { name: 'Confirmed Answers' });
    const row = (label: string) =>
      within(panel).getByText(label, { selector: '.confirmed-label' }).closest('li')!;
    expect(within(row('QC Verdict')).getByText('From Recorded Evidence')).toBeInTheDocument();
    expect(within(row('QC Verdict')).queryByText('Confirmed by You')).toBeNull();
    expect(within(row('Reduced Spectrum')).getByText('Confirmed by You')).toBeInTheDocument();
    expect(within(row('Scientific Descriptor')).getByText('Origin Not Recorded')).toBeInTheDocument();
  });
});
