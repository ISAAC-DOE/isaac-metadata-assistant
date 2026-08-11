/*
 * RECORD INFO + RELATIONSHIPS — what the two record-level sections may say, and
 * the sentences they must never say.
 *
 * The derivation is pinned next door in `record-identity.test.ts`. What this
 * file pins is the rendering, and every assertion below is about honesty rather
 * than layout:
 *
 *   · a value the exporter owns is shown AS A STAMP and offers no editor. There
 *     is no control to edit `timestamps.created_utc`, `record_id` or
 *     `isaac_record_version` — not a disabled one, none — because the exporter
 *     writes them and inviting an edit would misdescribe who owns the value;
 *   · a value this client does not fetch reads as not-fetched, NOT as missing;
 *   · a fan-out reads as "no single value" ONLY on the two values minted per
 *     record. The version and the classification trio have one value across every
 *     run, and saying they have none would be a false statement to a scientist;
 *   · a link target that is not a record id is refused with the schema's own
 *     reason, shown verbatim, and never resolved as though it were valid;
 *   · a target this app cannot find is described by the SET IT SEARCHED, never
 *     as "missing" or "invalid";
 *   · an off-enum relation renders (this is the direct-index trap: a
 *     `TABLE[token].label` lookup would render `undefined.label` and blank the
 *     panel);
 *   · there is no add / remove / edit control anywhere on the links section, and
 *     the panel says why rather than showing a dead one.
 */

import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, within, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { RecordInfoPanel, RecordLinksPanel } from '../components/RecordInfoPanel';
import { stubFetchRoutes } from '../test/apiFixtures';
import type { ApiArtifactsResponse, ApiDraftGroup, ApiExperimentDetail } from '../lib/types';

const ID_A = '01SYNTHTESTEXP000000000000';
const ID_B = '01SYNTHTESTDONE00000000000';

afterEach(() => {
  vi.unstubAllGlobals();
});

function detail(over: Partial<ApiExperimentDetail> = {}): ApiExperimentDetail {
  return {
    id: ID_A,
    title: 'Synthetic XANES — CuO',
    status: 'in_review',
    created_utc: '2099-04-02T09:00:00Z',
    pending_count: 0,
    evidenced_field_count: 26,
    exported: false,
    record_id: null,
    rev: 3,
    updated_utc: '2099-04-02T09:15:00Z',
    version: '1.0',
    draft_ok: true,
    artifact_refs: { record_filename: null, sidecar_filename: null },
    source_files: [],
    workflow: { steps: [], current_step: 'review_evidence' } as unknown as ApiExperimentDetail['workflow'],
    artifact: { state: 'none', reason: null },
    ...over,
  } as ApiExperimentDetail;
}

function artifacts(record: Record<string, unknown> | null): ApiArtifactsResponse {
  return {
    record,
    sidecar: null,
    record_filename: record === null ? null : `${ID_A}.json`,
    sidecar_filename: null,
    artifact: { state: record === null ? 'none' : 'current', reason: null },
  };
}

const EXPORTED_RECORD = {
  isaac_record_version: '1.05',
  record_id: ID_A,
  record_type: 'evidence',
  record_domain: 'characterization',
  source_type: 'facility',
  timestamps: { created_utc: '2099-03-05T21:05:48Z' },
};

/** The workspace list the link-target lookup reads (one exported record). */
const workspaceRoutes = {
  'GET /api/experiments': {
    body: {
      experiments: [
        {
          id: 'exp-1',
          title: 'Exported baseline',
          status: 'done',
          created_utc: '2099-01-15T09:00:00Z',
          pending_count: 0,
          evidenced_field_count: 26,
          exported: true,
          record_id: ID_B,
        },
      ],
    },
  },
};

function renderInfo(over: {
  detail?: ApiExperimentDetail;
  groups?: ApiDraftGroup[];
  record?: Record<string, unknown> | null;
} = {}) {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <RecordInfoPanel
        detail={over.detail ?? detail()}
        groups={over.groups ?? []}
        artifacts={artifacts(over.record ?? null)}
      />
    </MemoryRouter>,
  );
}

function renderLinks(record: Record<string, unknown> | null) {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <RecordLinksPanel artifacts={artifacts(record)} />
    </MemoryRouter>,
  );
}

/** Open a collapsed section by its header, and hand back its body. */
function open(title: string): HTMLElement {
  const header = screen.getByRole('button', { name: new RegExp(title) });
  expect(header).toHaveAttribute('aria-expanded', 'false');
  fireEvent.click(header);
  expect(header).toHaveAttribute('aria-expanded', 'true');
  const section = header.closest('section');
  if (section === null) throw new Error('no section around the header');
  return section as HTMLElement;
}

/** The `.field-row` for one official path. */
function infoRow(section: HTMLElement, path: string): HTMLElement {
  const row = section.querySelector(`[data-record-info-path="${path}"]`);
  if (row === null) throw new Error(`no Record Info row for ${path}`);
  return row as HTMLElement;
}

describe('Record Info — the six top-level values, and where each comes from', () => {
  it('is collapsed on arrival and opens from the keyboard-reachable header', () => {
    renderInfo();
    const header = screen.getByRole('button', { name: /Record Info/ });
    expect(header).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('ISAAC record version')).toBeNull();
    fireEvent.click(header);
    expect(screen.getByText('ISAAC record version')).toBeInTheDocument();
  });

  it('shows every value from the exported record, each labelled and addressed', () => {
    renderInfo({ record: EXPORTED_RECORD, detail: detail({ exported: true, record_id: ID_A }) });
    const section = open('Record Info');
    expect(within(infoRow(section, 'isaac_record_version')).getByText('1.05')).toBeInTheDocument();
    expect(within(infoRow(section, 'record_id')).getByText(ID_A)).toBeInTheDocument();
    expect(within(infoRow(section, 'record_type')).getByText('evidence')).toBeInTheDocument();
    expect(
      within(infoRow(section, 'record_domain')).getByText('characterization'),
    ).toBeInTheDocument();
    expect(within(infoRow(section, 'source_type')).getByText('facility')).toBeInTheDocument();
    expect(
      within(infoRow(section, 'timestamps.created_utc')).getByText('2099-03-05T21:05:48Z'),
    ).toBeInTheDocument();
  });

  it('renders the created stamp AS A STAMP, with no control that invites an edit', () => {
    renderInfo({ record: EXPORTED_RECORD, detail: detail({ exported: true, record_id: ID_A }) });
    const section = open('Record Info');
    const row = infoRow(section, 'timestamps.created_utc');

    expect(within(row).getByText('Record stamp')).toBeInTheDocument();
    expect(within(row).getByText(/Written by the exporter/)).toBeInTheDocument();

    // Not editable — and not "disabled", which would still describe it as a
    // field somebody fills in. There is no control at all.
    expect(within(row).queryByRole('textbox')).toBeNull();
    expect(within(row).queryByRole('button')).toBeNull();
    expect(within(row).queryByRole('combobox')).toBeNull();
    expect(row.querySelector('input,textarea,select')).toBeNull();
  });

  it('marks the two other exporter-owned values as stamps, and the science-derived ones not', () => {
    renderInfo({ record: EXPORTED_RECORD, detail: detail({ exported: true }) });
    const section = open('Record Info');
    for (const path of ['isaac_record_version', 'record_id', 'timestamps.created_utc']) {
      expect(within(infoRow(section, path)).getByText('Record stamp')).toBeInTheDocument();
    }
    for (const path of ['record_type', 'record_domain', 'source_type']) {
      expect(within(infoRow(section, path)).queryByText('Record stamp')).toBeNull();
    }
  });

  it('reads absent values as absent, and keeps "not written" apart from "not read here"', () => {
    renderInfo();
    const section = open('Record Info');
    expect(
      within(infoRow(section, 'record_id')).getByText('not written yet'),
    ).toBeInTheDocument();
    expect(
      within(infoRow(section, 'record_type')).getByText('not read on this screen'),
    ).toBeInTheDocument();
    // No placeholder, no invented value, and no claim that the record lacks it.
    expect(section.textContent).not.toMatch(/unknown|n\/a|TBD|—\s*missing/i);
  });

  it('says "no single value" in a fan-out only where there is none, in the server’s own words', () => {
    const reason = 'This record’s runs each export their own official record.';
    renderInfo({
      detail: detail({
        exported: true,
        record_id: null,
        artifact_refs: { record_filename: null, sidecar_filename: null, reason },
      }),
    });
    const section = open('Record Info');

    // Minted per record: each run exports under its own id and is stamped as it
    // is written, so the experiment has no single one of either.
    for (const path of ['record_id', 'timestamps.created_utc']) {
      expect(
        within(infoRow(section, path)).getByText('no single value for this experiment'),
      ).toBeInTheDocument();
    }

    // Fixed for every run — by the exporter for the version, by the stored `meta`
    // rule for the trio. Telling a scientist these have no single value is a
    // false statement, and this panel made it for one commit.
    for (const path of ['isaac_record_version', 'record_type', 'record_domain', 'source_type']) {
      const row = infoRow(section, path);
      expect(within(row).getByText('not read on this screen')).toBeInTheDocument();
      expect(row.textContent).not.toMatch(/no single value/);
    }

    // The server's sentence still reaches every row, word for word — after that
    // row's own claim, not in place of one.
    const rows = Array.from(section.querySelectorAll<HTMLElement>('[data-record-info-path]'));
    expect(rows).toHaveLength(6);
    for (const row of rows) expect(row.textContent).toContain(reason);
  });

  it('quotes the schema’s own description where the schema gives one', () => {
    renderInfo({ record: EXPORTED_RECORD, detail: detail({ exported: true }) });
    const section = open('Record Info');
    expect(
      within(infoRow(section, 'record_type')).getByText(/Fundamental nature of the record/),
    ).toBeInTheDocument();
    // `isaac_record_version` carries NO description in the schema, so none is written.
    expect(
      infoRow(section, 'isaac_record_version').textContent,
    ).not.toMatch(/The official schema describes this as/);
  });
});

describe('Relationships — the links block, read from the record', () => {
  it('renders each link with its relation, target and basis', async () => {
    stubFetchRoutes(workspaceRoutes);
    renderLinks({
      ...EXPORTED_RECORD,
      links: [
        {
          rel: 'same_sample_as',
          target: ID_B,
          basis: 'same_sample_id',
          notes: 'Two runs of one experiment share a sample id.',
        },
        { rel: 'derived_from', target: ID_B, basis: 'analysis_pipeline_output' },
      ],
    });
    const section = open('Relationships');
    const items = within(section).getAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(within(items[0]).getByText('same sample as')).toBeInTheDocument();
    expect(within(items[0]).getByText('same_sample_as')).toBeInTheDocument();
    expect(within(items[0]).getByText('same sample id')).toBeInTheDocument();
    expect(
      within(items[0]).getByText('Two runs of one experiment share a sample id.'),
    ).toBeInTheDocument();
    expect(within(items[1]).getByText('derived from')).toBeInTheDocument();
    expect(await within(section).findAllByText(/Points at/)).toHaveLength(2);
  });

  it('says what a target points at when the workspace holds that record', async () => {
    stubFetchRoutes(workspaceRoutes);
    renderLinks({ links: [{ rel: 'derived_from', target: ID_B, basis: 'unspecified' }] });
    const section = open('Relationships');
    const link = await within(section).findByRole('link', { name: /Exported baseline/ });
    expect(link).toHaveAttribute('href', '/record/exp-1');
  });

  it('describes an unresolvable target by the set it searched, never as missing', async () => {
    stubFetchRoutes(workspaceRoutes);
    const other = '01ZZZZZZZZZZZZZZZZZZZZZZZZ';
    renderLinks({ links: [{ rel: 'derived_from', target: other, basis: 'unspecified' }] });
    const section = open('Relationships');
    const note = await within(section).findByText(/Not in this workspace’s experiment list/);
    expect(note.textContent).toMatch(/does not include the records exported per run/);
    expect(note.textContent).toMatch(/cannot say whether the target exists/);
    // The id is still shown, and it is NOT called invalid or missing.
    expect(within(section).getByText(other)).toBeInTheDocument();
    expect(within(section).queryByText(/Not a record id/)).toBeNull();
    expect(section.textContent).not.toMatch(/target is missing|does not exist|invalid target/i);
  });

  it('says so plainly when the workspace list cannot be read', async () => {
    stubFetchRoutes({ 'GET /api/experiments': { status: 500, body: { detail: 'boom' } } });
    renderLinks({ links: [{ rel: 'derived_from', target: ID_B, basis: 'unspecified' }] });
    const section = open('Relationships');
    expect(
      await within(section).findByText(/could not read the workspace’s experiment list/),
    ).toBeInTheDocument();
  });

  it('refuses a target that is not a record id, with the schema’s own reason', async () => {
    const calls = stubFetchRoutes(workspaceRoutes);
    renderLinks({
      links: [{ rel: 'derived_from', target: 'not-a-ulid', basis: 'unspecified' }],
    });
    const section = open('Relationships');
    expect(within(section).getByText('Not a record id')).toBeInTheDocument();
    // Shown exactly as stored — never trimmed, upper-cased or padded into shape.
    expect(within(section).getByText('not-a-ulid')).toBeInTheDocument();
    expect(within(section).getByText(/26 characters, digits and capital letters/)).toBeInTheDocument();
    expect(within(section).getByText('Incomplete')).toBeInTheDocument();
    // A malformed target is never looked up as though it were resolvable.
    await waitFor(() => expect(calls).not.toContain('GET /api/experiments'));
  });

  it('reports a link with no target as incomplete, and invents no identifier', () => {
    stubFetchRoutes(workspaceRoutes);
    renderLinks({ links: [{ rel: 'derived_from', basis: 'unspecified' }] });
    const section = open('Relationships');
    expect(within(section).getByText('No target id')).toBeInTheDocument();
    expect(within(section).getByText('Incomplete')).toBeInTheDocument();
    expect(
      within(section).getByText(/No identifier is invented to fill it/),
    ).toBeInTheDocument();
  });

  it('renders a relation the schema does not list instead of blanking (the lookup trap)', async () => {
    stubFetchRoutes(workspaceRoutes);
    renderLinks({ links: [{ rel: 'supersedes', target: ID_B, basis: 'invented_basis' }] });
    const section = open('Relationships');
    await within(section).findByText(/Points at/);
    // Twice: the humanised text and the stored token. A relation with no
    // underscore is its own humanisation, which is exactly right — nothing was
    // renamed.
    expect(within(section).getAllByText('supersedes')).toHaveLength(2);
    expect(
      within(section).getByText(/Not one of the eight relations the official schema lists/),
    ).toBeInTheDocument();
    expect(
      within(section).getByText(/Not one of the twelve bases the official schema lists/),
    ).toBeInTheDocument();
  });

  it('names a wrong-typed relation as present, never as one the record does not carry', async () => {
    stubFetchRoutes(workspaceRoutes);
    renderLinks({ links: [{ rel: 5, target: ID_B, basis: 'unspecified' }] });
    const section = open('Relationships');
    await within(section).findByText(/Points at/);
    expect(within(section).getByText('Not a relation')).toBeInTheDocument();
    // Shown exactly as stored, like a malformed target is.
    expect(within(section).getByText('5')).toBeInTheDocument();
    // The absent-member sentence would be false here: a relation IS present.
    expect(section.textContent).not.toMatch(/No relation\. The official schema requires one/);
    expect(within(section).getByText('Incomplete')).toBeInTheDocument();
  });

  it('flags a relation the enum does not hold EXACTLY, instead of trimming it in', async () => {
    stubFetchRoutes(workspaceRoutes);
    renderLinks({ links: [{ rel: 'derived_from ', target: ID_B, basis: 'unspecified' }] });
    const section = open('Relationships');
    await within(section).findByText(/Points at/);
    expect(
      within(section).getByText(/Not one of the eight relations the official schema lists/),
    ).toBeInTheDocument();
  });

  it('reports a record that declares none, distinctly from one it cannot read', () => {
    renderLinks(EXPORTED_RECORD);
    const section = open('Relationships');
    expect(
      within(section).getByText(/declares no relationship to another record/),
    ).toBeInTheDocument();
  });

  it('does not claim an unexported record declares none', () => {
    renderLinks(null);
    const section = open('Relationships');
    expect(
      within(section).getByText(/which is not the same as the record declaring none/),
    ).toBeInTheDocument();
    expect(section.textContent).not.toMatch(/declares no relationship to another record\./);
  });

  it('offers no add / remove / edit control, and says why', async () => {
    stubFetchRoutes(workspaceRoutes);
    renderLinks({ links: [{ rel: 'derived_from', target: ID_B, basis: 'unspecified' }] });
    const section = open('Relationships');
    await within(section).findByText(/Points at/);
    expect(
      within(section).getByText(/no operation in this API writes a record’s/),
    ).toBeInTheDocument();
    // The section header is the only button, and there are no dead controls.
    const buttons = within(section).getAllByRole('button');
    expect(buttons).toHaveLength(1);
    expect(buttons[0]).toHaveAttribute('aria-expanded');
    expect(section.querySelector('input,textarea,select')).toBeNull();
    expect(within(section).queryByRole('button', { name: /add|remove|delete|new link/i })).toBeNull();
  });
});
