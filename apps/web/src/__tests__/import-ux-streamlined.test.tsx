/*
 * THE STREAMLINED HISTORICAL IMPORT (2026-10-18) — one test per audit finding this slice
 * closed, each written to fail on the code before it (`0a275fd7`) and to pass after.
 *
 * Fixtures are UNMISTAKABLY FAKE: `ZZ`/`FAKE` names, the year 2099, invented ids.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter, useNavigate, useNavigationType } from 'react-router-dom';
import { HistoricalImport } from '../screens/HistoricalImport';
import { ImportCandidateRow } from '../components/ImportCandidateRow';
import { ImportConflicts } from '../components/ImportConflicts';
import { ImportScopeProvider, RuleScopeFields } from '../components/ImportScope';
import { TechniqueChooser } from '../components/ImportTechnique';
import { SignalSelection } from '../components/ImportRules';
import { Breakable } from '../components/Breakable';
import { api } from '../lib/api';
import { IMPORT_COPY, IMPORT_STAGE_COPY } from '../lib/historicalImportContent';
import { conflictDisposition, conflictTally, FIELD_NAME_UNITS, fieldNameUnit, signalState, type ConflictView } from '../lib/importStages';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import type {
  ApiImportCandidate,
  ApiImportListResponse,
  ApiImportSession,
  ApiImportSignalSelection,
  ApiImportSource,
  ApiImportUnitRow,
  ApiImportWorkflowStep,
} from '../lib/types';

const C = IMPORT_STAGE_COPY;

const WORKFLOW: ApiImportWorkflowStep[] = [
  { id: 'new_import', label: 'New Import', built: true, disclosure: null },
  { id: 'sources', label: 'Sources', built: true, disclosure: null },
  { id: 'parse', label: 'Parse', built: true, disclosure: null },
  { id: 'reconstruct', label: 'Reconstruct', built: true, disclosure: null },
  { id: 'review', label: 'Review', built: true, disclosure: null },
  { id: 'add_to_experiments', label: 'Add to Experiments', built: true, disclosure: null },
];

const SOURCE: ApiImportSource = {
  source_id: '01SRCZZ0000000000000000001',
  kind: 'synthetic_fixture',
  filename: 'FAKE-bundle_zz_2099.txt',
  reference: 'tests/fixtures/historical_import/FAKE-bundle_zz_2099.txt',
  parse_state: 'parsed',
  parse_detail: 'Read: 2 statement(s).',
  provenance: { bytes_read_by_this_application: true },
  media_type: null,
  size_bytes: null,
  sha256: null,
  fixture_name: 'FAKE-bundle_zz_2099.txt',
};

function candidate(overrides: Partial<ApiImportCandidate> = {}): ApiImportCandidate {
  return {
    candidate_id: '01CANDZZ000000000000000001',
    kind: 'field',
    determinism: 'deterministic',
    rule: 'FAKE rule sentence.',
    supporting_source_ids: [SOURCE.source_id],
    supporting_statements: [{ source_id: SOURCE.source_id, key: 'system.technique', value: 'XAS', locator: 'line 2' }],
    target_field_path: 'system.technique',
    proposed_value: 'XAS',
    disagreement: [],
    unresolved_reason: null,
    not_proposable_reason: null,
    proposable: true,
    ...overrides,
  };
}

const SENDABLE_A = candidate();
const SENDABLE_B = candidate({
  candidate_id: '01CANDZZ000000000000000002',
  target_field_path: 'sample.material.name',
  proposed_value: 'FAKE-ZZ-sample',
  supporting_statements: [{ source_id: SOURCE.source_id, key: 'sample.material.name', value: 'FAKE-ZZ-sample', locator: 'line 3' }],
});

function session(overrides: Partial<ApiImportSession> = {}): ApiImportSession {
  return {
    import_id: '01IMPZZ0000000000000000001',
    label: 'A FAKE 2099 ZZ import',
    created_utc: '2099-01-01T00:00:00Z',
    updated_utc: '2099-01-01T00:00:05Z',
    furthest_step: 'reconstruct',
    workflow: WORKFLOW,
    durability: 'FAKE durability sentence.',
    sources: [SOURCE],
    unreadable_source_count: 0,
    source_counts: { total: 1, parsed: 1, failed: 0, no_content_path: 0, unparsed: 0, parsable_by_this_build: 1 },
    parsed: [],
    unmapped_keys: [],
    reconstruction: {
      provider_id: 'deterministic_fake',
      reconstructed_utc: '2099-01-01T00:00:05Z',
      applied: false,
      candidates: [SENDABLE_A, SENDABLE_B],
    },
    unreadable_candidate_count: 0,
    proposed: {},
    parsers: [],
    provider: { provider_id: 'deterministic_fake', display_name: 'FAKE', applied: false },
    beamline_profile: { profile_id: 'empty', display_name: 'none', is_empty: true, conventions_encoded: 0 },
    available_fixtures: ['FAKE-bundle_zz_2099.txt'],
    available_archives: ['bl15_synthetic_mini_corpus'],
    default_archive: 'bl15_synthetic_mini_corpus',
    ...overrides,
  } as ApiImportSession;
}

function list(overrides: Partial<ApiImportListResponse> = {}): ApiImportListResponse {
  return {
    imports: [],
    total: 0,
    workflow: WORKFLOW,
    durability: 'FAKE durability sentence.',
    available_fixtures: [],
    available_archives: [],
    ...overrides,
  };
}

const seen: { url: string; method: string }[] = [];

function stub(routes: { list?: ApiImportListResponse; detail?: ApiImportSession | null; experiments?: unknown } = {}) {
  seen.length = 0;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(typeof input === 'string' ? input : (input as Request).url ?? input);
      const method = (init?.method ?? 'GET').toUpperCase();
      seen.push({ url, method });
      const json = (payload: unknown, status = 200) =>
        new Response(JSON.stringify(payload), { status, headers: { 'Content-Type': 'application/json', ETag: '"zz.1"' } });
      if (/\/api\/imports\/[^/]+$/.test(url) && method === 'DELETE') return new Response(null, { status: 204 });
      if (/\/api\/imports\/[^/]+$/.test(url) && method === 'GET') {
        if (routes.detail === null) return json({ error: 'import_not_found', message: 'No such import.' }, 404);
        return json({ import: routes.detail ?? session() });
      }
      if (url.endsWith('/api/imports')) return json(routes.list ?? list());
      if (url.includes('/api/experiments')) return json(routes.experiments ?? { experiments: [] });
      if (url.includes('/api/health')) return json({ status: 'ok', mode: 'synthetic-only' });
      throw new Error(`unexpected request: ${method} ${url}`);
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <HistoricalImport />
    </MemoryRouter>,
  );
}

/* ── C-14 · the open import and its stage are in the URL ───────────────────── */

describe('C-14 · an import and its stage are deep-linkable', () => {
  it('opens the import named in the URL, at the stage the URL names', async () => {
    stub({ detail: session() });
    renderAt('/imports?import=01IMPZZ0000000000000000001&stage=conflicts');
    await screen.findByRole('tablist', { name: C.stagesLabel });
    expect(screen.getByRole('tab', { selected: true }).textContent).toContain(C.conflicts.title);
    // The list was never what the reader was shown.
    expect(screen.queryByRole('heading', { name: 'Imports', level: 2 })).toBeNull();
  });

  it('a link to an import that no longer exists says so in words, with the way back', async () => {
    stub({ detail: null });
    renderAt('/imports?import=01IMPZZGONE00000000000000');
    expect(await screen.findByRole('heading', { name: IMPORT_COPY.goneTitle })).toBeTruthy();
    expect(screen.getByText(IMPORT_COPY.goneBody)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Back to imports' }));
    expect(await screen.findByRole('heading', { name: 'Imports', level: 2 })).toBeTruthy();
  });

  it('each list row is a real link to its import, with a six-stage meter in words', async () => {
    stub({
      list: list({
        total: 1,
        imports: [
          {
            import_id: '01IMPZZ0000000000000000001',
            label: 'A FAKE 2099 ZZ import',
            created_utc: '2099-01-01T00:00:00Z',
            updated_utc: '2099-01-01T00:00:00Z',
            furthest_step: 'reconstruct',
            source_count: 1,
            parsed_source_count: 1,
            candidate_count: 9,
            proposed_count: 0,
          },
        ],
      }),
    });
    renderAt('/imports');
    const link = await screen.findByRole('link', { name: 'A FAKE 2099 ZZ import' });
    expect(link.getAttribute('href')).toBe('/imports?import=01IMPZZ0000000000000000001');
    const row = link.closest('li')!;
    // `reconstruct` is the stage it OWNS — Runs & Candidates — not the Conflicts view of it
    // (review, 2026-10-18: "4 of 6 · Conflicts" read as progress the reader had not made).
    expect(row.querySelectorAll('.hi-meter-seg.is-reached')).toHaveLength(3);
    expect(row.textContent).toContain(`3 of 6 · ${C.runs.title}`);
    // ~~"1 source · 1 read · 9 candidates · 0 sent to review"~~ — the counts sentence is gone.
    expect(row.textContent).not.toMatch(/candidates/);
  });
});

/* ── the landing is ONE widget ─────────────────────────────────────────────── */

describe('landing · one widget with the start control in it', () => {
  it('the name field and Start an Import are inside the Imports widget, with How it works behind its info', async () => {
    stub({});
    renderAt('/imports');
    const heading = await screen.findByRole('heading', { name: 'Imports', level: 2 });
    const widget = heading.closest('section.widget') as HTMLElement;
    expect(widget).not.toBeNull();
    expect(within(widget).getByRole('button', { name: IMPORT_COPY.actionStart })).toBeTruthy();
    expect(within(widget).getByRole('textbox')).toBeTruthy();
    const info = within(widget).getByRole('button', { name: 'How Historical Import works' });
    expect(info.getAttribute('aria-expanded')).toBe('false');
    // The durability sentence is in the DOM while the info panel is shut.
    expect(document.body.textContent).toContain('FAKE durability sentence.');
    // ONE intro sentence, and no eyebrow above the page title.
    expect(document.querySelector('.hi-page-head .eyebrow')).toBeNull();
    expect((document.querySelector('.hi-lead')?.textContent ?? '').split(/[.!?](\s|$)/).filter((t) => t && t.trim()).length).toBe(1);
  });
});

/* ── C-15 · discard asks, and leaves no stray request behind ───────────────── */

describe('C-15 · Discard This Import asks first', () => {
  it('opens a dialog naming what is lost and what is kept, with the safe button focused', async () => {
    stub({ detail: session() });
    renderAt('/imports?import=01IMPZZ0000000000000000001');
    await screen.findByRole('tablist', { name: C.stagesLabel });
    fireEvent.click(screen.getByRole('button', { name: IMPORT_COPY.actionDiscard }));
    const dialog = screen.getByRole('alertdialog', { name: IMPORT_COPY.discardDialogTitle });
    expect(dialog.textContent).toContain(IMPORT_COPY.discardWhatGoes);
    expect(dialog.textContent).toContain(IMPORT_COPY.discardWhatStays);
    expect(dialog.textContent).toContain('A FAKE 2099 ZZ import');
    await waitFor(() => expect(document.activeElement).toBe(within(dialog).getByRole('button', { name: IMPORT_COPY.discardKeep })));
    // Escape keeps it — and NOTHING was deleted.
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(seen.some((r) => r.method === 'DELETE')).toBe(false);
  });

  it('confirming deletes once, returns to the list, and never re-reads the import it removed', async () => {
    stub({ detail: session() });
    renderAt('/imports?import=01IMPZZ0000000000000000001');
    await screen.findByRole('tablist', { name: C.stagesLabel });
    fireEvent.click(screen.getByRole('button', { name: IMPORT_COPY.actionDiscard }));
    const dialog = screen.getByRole('alertdialog');
    const getsBefore = seen.filter((r) => r.method === 'GET' && /\/api\/imports\/[^/]+$/.test(r.url)).length;
    fireEvent.click(within(dialog).getByRole('button', { name: IMPORT_COPY.actionDiscard }));
    await screen.findByRole('heading', { name: 'Imports', level: 2 });
    expect(seen.filter((r) => r.method === 'DELETE')).toHaveLength(1);
    // THE STRAY `GET … 404` the audit measured: no read of the session after it was removed.
    const getsAfter = seen.filter((r) => r.method === 'GET' && /\/api\/imports\/[^/]+$/.test(r.url)).length;
    expect(getsAfter).toBe(getsBefore);
  });
});

/* ── C-17 · acceptance unavailable is said BEFORE sending ──────────────────── */

describe('C-17 · the acceptance note is on the Add stage before anything is sent', () => {
  it('shows it from the session capability, before a send', async () => {
    stub({
      detail: session({
        capabilities: {
          historical_file_ingestion: { enabled: false, reason: 'governance_not_approved' },
          proposal_acceptance: { available: false, reason: 'no_verifier_configured' },
        },
      }),
    });
    renderAt('/imports?import=01IMPZZ0000000000000000001&stage=add');
    await screen.findByRole('tablist', { name: C.stagesLabel });
    const panel = document.querySelector('[role="tabpanel"]:not([hidden])') as HTMLElement;
    expect(panel.textContent).toContain(C.acceptanceBefore);
    expect(seen.some((r) => r.url.includes('add-to-experiment'))).toBe(false);
  });

  it('says nothing about acceptance when the capability is available', async () => {
    stub({
      detail: session({
        capabilities: {
          historical_file_ingestion: { enabled: false, reason: 'governance_not_approved' },
          proposal_acceptance: { available: true, reason: null },
        },
      }),
    });
    renderAt('/imports?import=01IMPZZ0000000000000000001&stage=add');
    await screen.findByRole('tablist', { name: C.stagesLabel });
    expect(document.body.textContent).not.toContain(C.acceptanceBefore);
  });
});

/* ── C-16 · what this deployment can read, where files are chosen ──────────── */

describe('C-16 · choosing your own files explains what can and cannot be read', () => {
  it('says files are recorded by name only, why, and offers the example archive', async () => {
    stub({
      detail: session({
        sources: [],
        reconstruction: null,
        capabilities: {
          historical_file_ingestion: { enabled: false, reason: 'governance_not_approved' },
          proposal_acceptance: { available: false, reason: 'no_verifier_configured' },
        },
      }),
    });
    renderAt('/imports?import=01IMPZZ0000000000000000001&stage=sources');
    await screen.findByRole('tablist', { name: C.stagesLabel });
    const files = screen.getByRole('region', { name: C.filesTitle });
    expect(files.textContent).toContain(C.filesNotReadable);
    expect(files.textContent).toContain(C.filesNotReadableHelp);
    expect(within(files).getByRole('button', { name: C.filesTryExampleAction })).toBeTruthy();
  });
});

/* ── C-25 · the form stays usable, and what was sent survives a reload ─────── */

describe('C-25 · Add to Experiment after a send', () => {
  it('keeps the form for another record and lists what this import sent, from the session', async () => {
    stub({
      detail: session({
        proposed: {
          [SENDABLE_A.candidate_id]: { experiment_id: '01RECZZ0000000000000000001', proposal_id: 'P1', note_id: 'N1', proposed_utc: '2099-01-01T00:00:06Z' },
          [SENDABLE_B.candidate_id]: { experiment_id: '01RECZZ0000000000000000001', proposal_id: 'P2', note_id: 'N2', proposed_utc: '2099-01-01T00:00:06Z' },
        },
      }),
      experiments: { experiments: [{ id: '01RECZZ0000000000000000001', title: 'FAKE record ZZ' }] },
    });
    renderAt('/imports?import=01IMPZZ0000000000000000001&stage=add');
    await screen.findByRole('tablist', { name: C.stagesLabel });
    const panel = document.querySelector('[role="tabpanel"]:not([hidden])') as HTMLElement;
    // ~~"Everything this import can send has been sent." with no form~~ — the form stays.
    expect(within(panel).getByRole('button', { name: IMPORT_COPY.actionAddWhole })).toBeTruthy();
    const sent = within(panel).getByRole('region', { name: C.sentSoFarTitle });
    expect(sent.textContent).toContain('2 proposals on');
    expect(await within(sent).findByRole('link', { name: 'FAKE record ZZ' })).toBeTruthy();
  });
});

/* ── C-05/C-06/C-07 · the candidate row ────────────────────────────────────── */

describe('C-05 · C-06 · C-07 · a candidate row reads plainly', () => {
  const FULL =
    '~~An old sentence~~ CORRECTED 2026-09-16 by the slice that did X. THE ENGINEERING ' +
    'RATIONALE IN CAPITALS, citing DEC-47 and Q6, describing nine targets never acquired.';

  it('shows the short reason, with the full rationale behind "Why, in detail", mounted on first open', () => {
    const row = candidate({
      candidate_id: 'stem::acquisition_method',
      proposable: false,
      proposed_value: null,
      target_field_path: 'system.technique',
      not_proposable_reason: FULL,
      not_proposable_summary: 'The files name a method, not a technique — yours to choose.',
    });
    const { container } = render(
      <MemoryRouter>
        <ul>
          <ImportCandidateRow candidate={row} filenameOf={(id) => id} />
        </ul>
      </MemoryRouter>,
    );
    // Open the row, the way a reader reaches its detail.
    fireEvent.click(container.querySelector('.hi-cand-row > .disclosure-trigger, .hi-cand-row .disclosure-trigger')!);
    const blocked = container.querySelector('.hi-blocked')!;
    expect(blocked.textContent).toBe('The files name a method, not a technique — yours to choose.');
    expect(blocked.textContent).not.toContain('DEC-');
    const why = screen.getByRole('button', { name: C.whyInDetail });
    expect(why.getAttribute('aria-expanded')).toBe('false');
    /* MOUNTED ON FIRST OPEN (independent review, 2026-10-18): 161 of these bodies made the
       opened Runs stage 13,625 elements. It is per-candidate engineering rationale — the
       short reason above is what a reader must see — so it is mounted when asked for, and
       stays mounted after. MUTATION: rendering the body eagerly makes the first line RED. */
    expect(container.textContent).not.toContain(FULL);
    fireEvent.click(why);
    expect(container.textContent).toContain(FULL);
    fireEvent.click(why);
    expect(container.textContent).toContain(FULL);
  });

  it('a value the sources agree on and that is not sent shows the READING, never "No value has been selected"', () => {
    const row = candidate({
      candidate_id: 'stem::filter',
      proposable: false,
      proposed_value: null,
      target_field_path: null,
      agreement: 'sources_agree',
      distinct_sources: 2,
      supporting_statements: [{ source_id: SOURCE.source_id, key: 'filter', value: 'filter10', locator: 'name' }],
      not_proposable_reason: 'FAKE full reason.',
      not_proposable_summary: 'FAKE short reason.',
    });
    const { container } = render(
      <MemoryRouter>
        <ul>
          <ImportCandidateRow candidate={row} filenameOf={(id) => id} />
        </ul>
      </MemoryRouter>,
    );
    const summary = container.querySelector('.hi-cand-summary')!;
    expect(summary.textContent).toContain('filter10');
    expect(summary.textContent).toContain(C.readNotSent);
    expect(summary.textContent).not.toContain(C.conflicts.noValue);
  });

  it('a value in a field whose name states a unit carries the unit', () => {
    const row = candidate({
      candidate_id: 'stem::potential_magnitude',
      target_field_path: 'context.electrochemistry.potential_setpoint_V',
      proposed_value: 0.06,
    });
    const { container } = render(
      <MemoryRouter>
        <ul>
          <ImportCandidateRow candidate={row} filenameOf={(id) => id} />
        </ul>
      </MemoryRouter>,
    );
    expect(container.querySelector('.hi-cand-value')?.textContent).toBe('0.06 V');
  });
});

/* ── C-12 · C-22 · a conflict with nothing to choose is not open work ──────── */

function view(overrides: Partial<ConflictView> = {}): ConflictView {
  return {
    key: 'C1',
    kind: 'structural',
    topic: 'macro_declared_not_acquired',
    subject: 'ZZ_stem',
    explanation: 'A macro said it was about to record this measurement and no matching file is in the import.',
    readings: [
      { value: 'ZZ_stem', role: 'planned_acquisition', roleMeaning: null, sources: [{ path: 'zz.mac', locator: 'l1' }], sourceType: 'macro' },
      { value: 'no acquisition file of this name is present', role: 'absence_of_a_source', roleMeaning: null, sources: [{ path: 'zz', locator: '-' }], sourceType: null },
    ],
    distinct: null,
    recommendation: null,
    resolution: null,
    target: { conflict_id: 'C1' },
    resolvable: true,
    forbidden: false,
    stem: 'ZZ_stem',
    groupToken: null,
    ...overrides,
  };
}

describe('C-12 · C-22 · noted and preserved conflicts', () => {
  it('one stated reading against an absence is NOTED; a forbidden one is PRESERVED; neither is open', () => {
    expect(conflictDisposition(view())).toBe('noted');
    expect(conflictDisposition(view({ forbidden: true }))).toBe('preserved');
    const open = view({
      readings: [
        { value: 'after500Cycling', role: 'human_label', roleMeaning: null, sources: [{ path: 'a', locator: 'l' }], sourceType: null },
        { value: 'beforeCycling', role: 'instrument_header', roleMeaning: null, sources: [{ path: 'b', locator: 'l' }], sourceType: null },
      ],
    });
    expect(conflictDisposition(open)).toBe('open');
  });

  it('a noted conflict offers no "Which reading is right?" and says why there is nothing to choose', () => {
    const { container } = render(
      <ImportConflicts conflicts={[view()]} importId="IMPZZ" busy={null} onAct={async () => true} destinations={{ rows: [], failed: false, reload: async () => {} }} />,
    );
    expect(container.textContent).toContain(C.conflicts.notedKind);
    expect(container.textContent).toContain(C.conflicts.notedRow);
    expect(container.textContent).not.toContain(C.resolve.choose);
    // The row is kept, one press away — not deleted.
    expect(container.querySelector('li.hi-conflict')).not.toBeNull();
  });

  it('the session tally counts only open conflicts as "to decide"', () => {
    const tally = conflictTally(session({ reconstruction: null }));
    expect(tally).toEqual({ open: 0, resolved: 0, preserved: 0, noted: 0 });
  });
});

/* ── C-13 · where a rule is kept ───────────────────────────────────────────── */

describe('C-13 · the rule scopes explain themselves and can make the record they need', () => {
  it('with no record, a stored scope says why and offers New record from this import', async () => {
    const onAct = vi.fn(async (_name: string, run: () => Promise<unknown>) => {
      await run();
      return true;
    });
    const createRecord = vi.fn(async () => '01RECZZNEW00000000000000');
    const setExperimentId = vi.fn();
    render(
      <ImportScopeProvider value={{ targetId: null, createRecord, onAct, busy: null }}>
        <RuleScopeFields
          scope="experiment"
          setScope={() => {}}
          experimentId=""
          setExperimentId={setExperimentId}
          destinations={{ rows: [], failed: false, reload: async () => {} }}
        />
      </ImportScopeProvider>,
    );
    expect(screen.getByText(C.scopeNeedsRecord)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: IMPORT_COPY.actionNewRecord }));
    await waitFor(() => expect(setExperimentId).toHaveBeenCalledWith('01RECZZNEW00000000000000'));
    expect(createRecord).toHaveBeenCalledTimes(1);
  });

  it('names the record a stored rule would be kept on', () => {
    render(
      <ImportScopeProvider value={{ targetId: '01RECZZ0000000000000000001', createRecord: async () => '', onAct: async () => true, busy: null }}>
        <RuleScopeFields
          scope="import"
          setScope={() => {}}
          experimentId=""
          setExperimentId={() => {}}
          destinations={{ rows: [{ id: '01RECZZ0000000000000000001', title: 'FAKE record ZZ' }], failed: false, reload: async () => {} }}
        />
      </ImportScopeProvider>,
    );
    expect(screen.getByText(`${C.scopeOptions.experiment} — FAKE record ZZ`)).toBeTruthy();
  });
});

/* ── C-10 · the technique is the scientist's choice ────────────────────────── */

const SCHEMA = {
  properties: {
    system: { properties: { technique: { type: 'string', enum: ['XAS', 'HERFD-XAS', 'XES', 'RIXS', 'XRD'] } } },
  },
};

describe('C-10 · choosing the record’s technique', () => {
  it('preselects nothing, shows what the files say beside it, and saves the choice as a record answer', async () => {
    vi.spyOn(api, 'getSchema').mockResolvedValue({ schema: SCHEMA } as never);
    vi.spyOn(api, 'getDraft').mockResolvedValue({ groups: [] } as never);
    vi.spyOn(api, 'getExperiment').mockResolvedValue({ id: 'R', version: 'v.7' } as never);
    const answer = vi.spyOn(api, 'submitAnswer').mockResolvedValue({} as never);
    const edit = vi.spyOn(api, 'editField').mockResolvedValue({} as never);
    render(
      <TechniqueChooser
        experimentId="01RECZZ0000000000000000001"
        recordTitle="FAKE record ZZ"
        evidence={[{ value: 'Zz_XAS.mac', places: 3 }]}
        shortList={['XAS', 'HERFD-XAS', 'XES', 'RIXS']}
      />,
    );
    const select = (await screen.findByRole('combobox', { name: C.techniqueLabel })) as HTMLSelectElement;
    await waitFor(() => expect(select.disabled).toBe(false));
    expect(select.value).toBe('');
    expect(screen.getByText('Zz_XAS.mac')).toBeTruthy();
    // The schema's own list, the four the registry names first.
    expect(within(select).getAllByRole('option').map((o) => (o as HTMLOptionElement).value)).toEqual([
      '',
      'XAS',
      'HERFD-XAS',
      'XES',
      'RIXS',
      'XRD',
    ]);
    const save = screen.getByRole('button', { name: C.techniqueSave }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    fireEvent.change(select, { target: { value: 'HERFD-XAS' } });
    fireEvent.click(save);
    await waitFor(() =>
      expect(answer).toHaveBeenCalledWith('01RECZZ0000000000000000001', { 'system.technique': 'HERFD-XAS' }, 'v.7'),
    );
    expect(edit).not.toHaveBeenCalled();
    expect(await screen.findByText(C.techniqueSaved('HERFD-XAS', 'FAKE record ZZ'))).toBeTruthy();
  });

  it('corrects a technique the record already holds through the edit operation', async () => {
    vi.spyOn(api, 'getSchema').mockResolvedValue({ schema: SCHEMA } as never);
    vi.spyOn(api, 'getDraft').mockResolvedValue({
      groups: [{ fields: [{ path: 'system.technique', value: 'XAS' }] }],
    } as never);
    vi.spyOn(api, 'getExperiment').mockResolvedValue({ id: 'R', version: 'v.8' } as never);
    const answer = vi.spyOn(api, 'submitAnswer').mockResolvedValue({} as never);
    const edit = vi.spyOn(api, 'editField').mockResolvedValue({} as never);
    render(<TechniqueChooser experimentId="R" recordTitle="FAKE" evidence={[]} shortList={[]} />);
    expect(await screen.findByText(C.techniqueCurrent('XAS'))).toBeTruthy();
    const select = screen.getByRole('combobox', { name: C.techniqueLabel }) as HTMLSelectElement;
    await waitFor(() => expect(select.disabled).toBe(false));
    expect(select.value).toBe('');
    fireEvent.change(select, { target: { value: 'XES' } });
    fireEvent.click(screen.getByRole('button', { name: C.techniqueSave }));
    await waitFor(() => expect(edit).toHaveBeenCalledWith('R', { 'system.technique': 'XES' }, 'v.8'));
    expect(answer).not.toHaveBeenCalled();
  });

  it('offers no free-text fallback when the schema cannot be read', async () => {
    vi.spyOn(api, 'getSchema').mockRejectedValue(new Error('down'));
    vi.spyOn(api, 'getDraft').mockResolvedValue({ groups: [] } as never);
    render(<TechniqueChooser experimentId="R" recordTitle="FAKE" evidence={[]} shortList={[]} />);
    expect(await screen.findByText(C.techniqueUnavailable)).toBeTruthy();
    expect(screen.queryByRole('combobox')).toBeNull();
    expect(screen.queryByRole('textbox')).toBeNull();
  });
});

/* ── C-27 · a long bucket is paged ─────────────────────────────────────────── */

describe('C-27 · a long review bucket mounts nothing until opened, then one page', () => {
  it('holds 30 unmapped rows behind the bucket, then shows 25 and Show 5 more', async () => {
    const unmapped = Array.from({ length: 30 }, (_, i) =>
      candidate({
        candidate_id: `ZZ_stem_${i}::unknown_token`,
        proposable: false,
        proposed_value: null,
        target_field_path: null,
        review_status: 'unmapped',
        not_proposable_reason: 'FAKE full reason.',
        not_proposable_summary: 'FAKE short reason.',
      }),
    );
    stub({
      detail: session({
        reconstruction: { provider_id: 'x', reconstructed_utc: '2099-01-01T00:00:00Z', applied: false, candidates: unmapped },
      }),
    });
    renderAt('/imports?import=01IMPZZ0000000000000000001&stage=review');
    await screen.findByRole('tablist', { name: C.stagesLabel });
    const panel = document.querySelector('[role="tabpanel"]:not([hidden])') as HTMLElement;
    expect(panel.querySelectorAll('li.hi-cand')).toHaveLength(0);
    fireEvent.click(within(panel).getByRole('button', { name: new RegExp(C.bucketTitles.unmapped) }));
    expect(panel.querySelectorAll('li.hi-cand')).toHaveLength(25);
    fireEvent.click(within(panel).getByRole('button', { name: /Show 5 more/ }));
    expect(panel.querySelectorAll('li.hi-cand')).toHaveLength(30);
  });
});

/* ── C-29 · a filename wraps at its own separators, text unchanged ─────────── */

describe('C-29 · Breakable', () => {
  it('adds break opportunities after separators and leaves the text exactly as it was', () => {
    const text = '05_02_ZZ2_base_after500Cycling_filter20_800mV_001.dat';
    const { container } = render(<Breakable text={text} />);
    expect(container.textContent).toBe(text);
    expect(container.querySelectorAll('wbr').length).toBe(8);
    // A decimal point is not a break.
    const { container: n } = render(<Breakable text="0.06" />);
    expect(n.querySelectorAll('wbr').length).toBe(0);
  });
});

/* ── C-26 · confirming a channel says so where it was pressed ──────────────── */

describe('C-26 · Confirm This Channel gives feedback in place', () => {
  it('after a successful act, a confirmation sits where the button was, and takes focus', async () => {
    vi.spyOn(api, 'recordImportRule').mockResolvedValue({} as never);
    const sel: ApiImportSignalSelection = {
      selector_id: 'herfd',
      system_id: 'FAKE',
      status: 'proposed',
      reason_code: 'one_live_channel',
      reason: 'Exactly one FAKE channel carries live signal.',
      primary_channel: 'Vortex1',
      assignments: [],
      channels: [{ channel: 'Vortex1', scans_present: 2, scans_with_edge: 2, share: 1, edge_fraction: 1, liveness: 'live', reason: '' }],
      elements: [{ element: 'Zz', edge: 'K', source_path: 'FAKE/notes.txt', locator: 'line 1', role: 'absorber', rule: 'r' }],
      thresholds: {},
      authority: 'suggestion',
      rule_ref: null,
      evidence_not_used: [],
      writes_a_record_field: false,
    } as ApiImportSignalSelection;
    const onAct = vi.fn(async (_n: string, run: () => Promise<unknown>) => {
      await run();
      return true;
    });
    render(
      <SignalSelection
        unit={{ stem: 'FAKE_07', acquisition_path: 'FAKE/07.dat' } as ApiImportUnitRow}
        selection={sel}
        importId="IMPZZ"
        busy={null}
        onAct={onAct}
        destinations={{ rows: [], failed: false, reload: async () => {} }}
        state={signalState(sel)}
      />,
    );
    expect(screen.queryByText(C.signalRecorded)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: C.signalConfirm }));
    const done = await screen.findByText(C.signalRecorded);
    await waitFor(() => expect(document.activeElement).toBe(done));
  });

  it('a refused act claims nothing', async () => {
    const sel = { status: 'proposed', reason: 'r', assignments: [], channels: [{ channel: 'Vortex1', liveness: 'live' }], elements: [{ element: 'Zz', edge: 'K' }] } as unknown as ApiImportSignalSelection;
    render(
      <SignalSelection
        unit={{ stem: 'FAKE_07', acquisition_path: 'FAKE/07.dat' } as ApiImportUnitRow}
        selection={sel}
        importId="IMPZZ"
        busy={null}
        onAct={async () => false}
        destinations={{ rows: [], failed: false, reload: async () => {} }}
        state={signalState(sel)}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: C.signalConfirm }));
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByText(C.signalRecorded)).toBeNull();
  });
});

/* ── one table of field-name units, on both sides ─────────────────────────── */

describe('the unit a schema field’s name states is ONE table, server and client', () => {
  it('`routes._FIELD_NAME_UNITS` and `importStages.FIELD_NAME_UNITS` hold the same pairs, in order', () => {
    /* The note text (server) and the candidate value (client) both append a unit read off
       the field's own name; two hand-kept copies could drift (review, 2026-10-18). Parsed
       from the Python source rather than imported, because the server is not a JS module.
       MUTATION: adding a pair to either side alone makes this RED. */
    const src = readFileSync(join(__dirname, '../../../api/isaac_api/routes.py'), 'utf8');
    const block = src.slice(src.indexOf('_FIELD_NAME_UNITS: tuple'), src.indexOf('def _field_name_unit'));
    const pairs = [...block.matchAll(/\("([^"]+)",\s*"([^"]+)"\)/g)].map((m) => [m[1], m[2]]);
    expect(pairs.length).toBeGreaterThan(5);
    expect(pairs).toEqual(FIELD_NAME_UNITS.map(([a, b]) => [a, b]));
    expect(fieldNameUnit('context.electrochemistry.potential_setpoint_V')).toBe('V');
    expect(fieldNameUnit('context.temperature_K')).toBe('K');
    expect(fieldNameUnit('sample.material.name')).toBeNull();
  });
});

/* ── review follow-ups (2026-10-18) ─────────────────────────────────────────── */

function NavProbe() {
  const type = useNavigationType();
  const navigate = useNavigate();
  return (
    <>
      <span data-testid="nav-type">{type}</span>
      <button type="button" onClick={() => navigate(-1)}>
        probe-back
      </button>
    </>
  );
}

function renderWithProbe(path: string) {
  return render(
    <MemoryRouter initialEntries={['/imports', path]} initialIndex={1} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <HistoricalImport />
      <NavProbe />
    </MemoryRouter>,
  );
}

describe('review follow-ups', () => {
  it('`?import=` with no value is the list, not a crash', async () => {
    stub({});
    renderAt('/imports?import=');
    expect(await screen.findByRole('heading', { name: 'Imports', level: 2 })).toBeTruthy();
  });

  it('a click on a stage tab is a history step; an arrow-key move is not', async () => {
    stub({ detail: session() });
    renderWithProbe('/imports?import=01IMPZZ0000000000000000001&stage=sources');
    await screen.findByRole('tablist', { name: C.stagesLabel });
    fireEvent.click(screen.getByRole('tab', { name: new RegExp(C.read.title) }));
    await waitFor(() => expect(screen.getByTestId('nav-type').textContent).toBe('PUSH'));
    fireEvent.keyDown(screen.getByRole('tab', { selected: true }), { key: 'ArrowRight' });
    await waitFor(() => expect(screen.getByTestId('nav-type').textContent).toBe('REPLACE'));
    expect(screen.getByRole('tab', { selected: true }).textContent).toContain(C.runs.title);
  });

  it('the list is read again when Back returns to it', async () => {
    stub({ detail: session() });
    renderWithProbe('/imports?import=01IMPZZ0000000000000000001');
    await screen.findByRole('tablist', { name: C.stagesLabel });
    const listReads = () => seen.filter((r) => r.method === 'GET' && /\/api\/imports$/.test(r.url)).length;
    const before = listReads();
    fireEvent.click(screen.getByRole('button', { name: 'probe-back' }));
    await screen.findByRole('heading', { name: 'Imports', level: 2 });
    await waitFor(() => expect(listReads()).toBeGreaterThan(before));
  });

  it('on Add, the technique sits inside the send form, ABOVE the primary send button', async () => {
    vi.spyOn(api, 'getSchema').mockResolvedValue({ schema: SCHEMA } as never);
    stub({
      detail: session({
        archive: { run_candidate_unit_count: 0, units_page: { rows: [] }, shared_candidate_ids: [] } as never,
      }),
      experiments: { experiments: [{ id: '01RECZZ0000000000000000001', title: 'FAKE record ZZ' }] },
    });
    renderAt('/imports?import=01IMPZZ0000000000000000001&stage=add');
    await screen.findByRole('tablist', { name: C.stagesLabel });
    const form = document.querySelector('form.hi-addwhole') as HTMLElement;
    const technique = form.querySelector('.hi-technique');
    const submit = within(form).getByRole('button', { name: IMPORT_COPY.actionAddWhole });
    expect(technique).not.toBeNull();
    expect(technique!.compareDocumentPosition(submit) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(technique!.textContent).toContain('record chosen above');
  });
});
