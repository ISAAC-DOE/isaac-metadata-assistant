/*
 * THE RECORD-IDENTITY MODEL — the derivation the two record-level sections
 * render, tested where it is decided rather than through the DOM.
 *
 * Three properties are what this file exists for, and each of them is a way the
 * surface could lie to a scientist:
 *
 *  1. A TARGET IS NOT REPAIRED OR GUESSED. `links[].target` carries the same
 *     `^[0-9A-Z]{26}$` pattern `record_id` does; anything else is reported as
 *     what it is and never completed, trimmed into shape, or dropped.
 *  2. "NOT WRITTEN YET", "NOT READ HERE" AND "NOT IN THE RECORD" ARE THREE
 *     DIFFERENT CLAIMS. Collapsing them would let the panel assert a record is
 *     missing a required value when the truth is only that this client does not
 *     fetch it.
 *  3. A MALFORMED ARTIFACT DOES NOT TAKE THE SCREEN DOWN. The record is a file
 *     this process did not write.
 */

import { describe, it, expect } from 'vitest';
import {
  LINK_BASES,
  LINK_RELATIONS,
  isRecordId,
  readLinks,
  recordInfoRows,
  resolveTarget,
} from '../lib/recordIdentity';
import type {
  ApiArtifactsResponse,
  ApiDraftGroup,
  ApiExperimentDetail,
  ApiExperimentSummary,
} from '../lib/types';

const ID_A = '01SYNTHTESTEXP000000000000';
const ID_B = '01SYNTHTESTDONE00000000000';

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

const NO_GROUPS: ApiDraftGroup[] = [];

function rowFor(rows: ReturnType<typeof recordInfoRows>, path: string) {
  const row = rows.find((r) => r.path === path);
  if (row === undefined) throw new Error(`no row for ${path}`);
  return row;
}

describe('isRecordId — the schema pattern, exactly', () => {
  it('accepts the 26-character shape the official schema declares', () => {
    expect(isRecordId(ID_A)).toBe(true);
    expect(isRecordId('ILOU'.padEnd(26, 'Z'))).toBe(true); // not Crockford-restricted
  });

  it('refuses a trailing newline — the hole `ids.py` documents in Python', () => {
    // `src/isaac_records/ids.py` uses `\A…\Z` because Python's `$` also matches
    // before a trailing newline, and the vendored schema's own `^…$` therefore
    // accepts this string. JavaScript's `$` does not, and this pins that.
    expect(isRecordId(`${ID_A}\n`)).toBe(false);
    expect(isRecordId(`\n${ID_A}`)).toBe(false);
  });

  it('refuses the near-misses a person actually types', () => {
    expect(isRecordId('')).toBe(false);
    expect(isRecordId(ID_A.slice(0, 25))).toBe(false);
    expect(isRecordId(`${ID_A}0`)).toBe(false);
    expect(isRecordId(ID_A.toLowerCase())).toBe(false);
    expect(isRecordId(` ${ID_A}`)).toBe(false);
    expect(isRecordId(null)).toBe(false);
    expect(isRecordId(42)).toBe(false);
  });
});

describe('recordInfoRows — six addresses, and one state each', () => {
  it('covers exactly the schema-required top-level set', () => {
    const paths = recordInfoRows({
      detail: detail(),
      groups: NO_GROUPS,
      artifacts: artifacts(null),
    }).map((r) => r.path);
    expect(paths).toEqual([
      'isaac_record_version',
      'record_id',
      'record_type',
      'record_domain',
      'source_type',
      'timestamps.created_utc',
    ]);
  });

  it('reads every value out of the exported record when there is one', () => {
    const rows = recordInfoRows({
      detail: detail({ exported: true, record_id: ID_A }),
      groups: NO_GROUPS,
      artifacts: artifacts({
        isaac_record_version: '1.05',
        record_id: ID_A,
        record_type: 'evidence',
        record_domain: 'characterization',
        source_type: 'facility',
        timestamps: { created_utc: '2099-03-05T21:05:48Z' },
      }),
    });
    expect(rows.map((r) => r.value)).toEqual([
      '1.05',
      ID_A,
      'evidence',
      'characterization',
      'facility',
      '2099-03-05T21:05:48Z',
    ]);
    expect(new Set(rows.map((r) => r.source))).toEqual(new Set(['from_record']));
  });

  it('separates "not written yet" from "not read here" before export', () => {
    const rows = recordInfoRows({
      detail: detail(),
      groups: NO_GROUPS,
      artifacts: artifacts(null),
    });
    expect(rowFor(rows, 'record_id').source).toBe('written_at_export');
    expect(rowFor(rows, 'isaac_record_version').source).toBe('written_at_export');
    expect(rowFor(rows, 'timestamps.created_utc').source).toBe('written_at_export');
    // The classification trio is REAL on the draft; this client simply does not
    // fetch it. Reporting it as `written_at_export` would be a false claim about
    // the record, and reporting it as missing would be worse.
    expect(rowFor(rows, 'record_type').source).toBe('not_read_here');
    expect(rowFor(rows, 'record_domain').source).toBe('not_read_here');
    expect(rowFor(rows, 'source_type').source).toBe('not_read_here');
    expect(rows.every((r) => r.value === null)).toBe(true);
  });

  it('shows a created stamp the DRAFT already carries, and says the exporter keeps it', () => {
    const groups: ApiDraftGroup[] = [
      {
        title: 'Timestamps',
        fields: [
          {
            path: 'timestamps.created_utc',
            label: 'Created Utc',
            value: '2099-01-02T03:04:05Z',
            status: 'verified',
            evidence_count: 1,
            source_types: ['spreadsheet'],
          },
        ],
      },
    ];
    const row = rowFor(
      recordInfoRows({ detail: detail(), groups, artifacts: artifacts(null) }),
      'timestamps.created_utc',
    );
    expect(row.value).toBe('2099-01-02T03:04:05Z');
    expect(row.source).toBe('from_draft');
    expect(row.note).toMatch(/stamps the export time only when it holds none/);
  });

  it('ignores a draft created stamp that is honestly missing', () => {
    const groups: ApiDraftGroup[] = [
      {
        title: 'Timestamps',
        fields: [
          {
            path: 'timestamps.created_utc',
            label: 'Created Utc',
            value: null,
            status: 'missing',
            evidence_count: 0,
            source_types: [],
          },
        ],
      },
    ];
    const row = rowFor(
      recordInfoRows({ detail: detail(), groups, artifacts: artifacts(null) }),
      'timestamps.created_utc',
    );
    expect(row.value).toBeNull();
    expect(row.source).toBe('written_at_export');
  });

  it('reports a required value the exported record does not carry, without claiming why', () => {
    const row = rowFor(
      recordInfoRows({
        detail: detail({ exported: true }),
        groups: NO_GROUPS,
        artifacts: artifacts({ record_id: ID_A }),
      }),
      'record_type',
    );
    expect(row.value).toBeNull();
    expect(row.source).toBe('missing_from_record');
  });

  it('gives the fan-out its own state, carrying the server’s own sentence', () => {
    const reason = 'This record’s runs each export their own official record.';
    const rows = recordInfoRows({
      detail: detail({
        exported: true,
        record_id: null,
        artifact_refs: { record_filename: null, sidecar_filename: null, reason },
      }),
      groups: NO_GROUPS,
      artifacts: artifacts(null),
    });
    expect(rows.every((r) => r.source === 'no_single_value')).toBe(true);
    expect(rows.every((r) => r.note === reason)).toBe(true);
    expect(rows.every((r) => r.value === null)).toBe(true);
  });

  it('never renders a container as a value', () => {
    const row = rowFor(
      recordInfoRows({
        detail: detail({ exported: true }),
        groups: NO_GROUPS,
        artifacts: artifacts({ record_type: { nested: true } }),
      }),
      'record_type',
    );
    expect(row.value).toBeNull();
    expect(row.source).toBe('missing_from_record');
  });
});

describe('readLinks — the record’s own array, read defensively', () => {
  it('reads a complete link and marks it complete', () => {
    const [link] = readLinks({
      links: [
        {
          rel: 'same_sample_as',
          target: ID_B,
          basis: 'same_sample_id',
          notes: 'Two runs of one experiment.',
        },
      ],
    });
    expect(link.rel).toEqual({ token: 'same_sample_as', text: 'same sample as', known: true });
    expect(link.basis.known).toBe(true);
    expect(link.target).toEqual({ state: 'ok', id: ID_B });
    expect(link.notes).toBe('Two runs of one experiment.');
    expect(link.complete).toBe(true);
  });

  it('reports a missing target as incomplete and invents nothing', () => {
    const [link] = readLinks({ links: [{ rel: 'derived_from', basis: 'unspecified' }] });
    expect(link.target).toEqual({ state: 'absent' });
    expect(link.complete).toBe(false);
  });

  it('reports a wrong-shaped target verbatim rather than repairing it', () => {
    const [lower, short, spaced, numeric] = readLinks({
      links: [
        { rel: 'follows', target: ID_B.toLowerCase(), basis: 'unspecified' },
        { rel: 'follows', target: 'ABC', basis: 'unspecified' },
        { rel: 'follows', target: ` ${ID_B} `, basis: 'unspecified' },
        { rel: 'follows', target: 12345, basis: 'unspecified' },
      ],
    });
    expect(lower.target).toEqual({ state: 'malformed', text: ID_B.toLowerCase() });
    expect(short.target).toEqual({ state: 'malformed', text: 'ABC' });
    // NOT trimmed into validity: the stored value is what is reported.
    expect(spaced.target).toEqual({ state: 'malformed', text: ` ${ID_B} ` });
    expect(numeric.target.state).toBe('malformed');
    expect([lower, short, spaced, numeric].every((l) => l.complete)).toBe(false);
  });

  it('flags a relation or basis the schema does not list, without renaming it', () => {
    const [link] = readLinks({
      links: [{ rel: 'supersedes', target: ID_B, basis: 'a_new_basis' }],
    });
    expect(link.rel).toEqual({ token: 'supersedes', text: 'supersedes', known: false });
    expect(link.basis.known).toBe(false);
    expect(LINK_RELATIONS).not.toContain('supersedes');
    expect(LINK_BASES).not.toContain('a_new_basis');
  });

  it('survives a record whose links block is not what the schema declares', () => {
    expect(readLinks(null)).toEqual([]);
    expect(readLinks({})).toEqual([]);
    expect(readLinks({ links: 'derived_from' })).toEqual([]);
    expect(readLinks({ links: [null, 'x', 7, []] })).toEqual([]);
    expect(readLinks({ links: [{}] })).toHaveLength(1);
  });

  it('transcribes the schema’s two closed vocabularies', () => {
    expect(LINK_RELATIONS).toHaveLength(8);
    expect(LINK_BASES).toHaveLength(12);
    expect(LINK_RELATIONS).toContain('intended_comparison_target');
    expect(LINK_BASES).toContain('analysis_pipeline_output');
  });
});

describe('resolveTarget — what this app can and cannot say', () => {
  const workspace: ApiExperimentSummary[] = [
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
  ];

  it('names what a target points at when the workspace holds it', () => {
    expect(resolveTarget(ID_B, workspace)).toEqual({
      state: 'resolved',
      experimentId: 'exp-1',
      title: 'Exported baseline',
    });
  });

  it('says only that it did not find it — never that the target is missing', () => {
    expect(resolveTarget(ID_A, workspace)).toEqual({ state: 'not_in_workspace' });
  });

  it('distinguishes an unreadable workspace list from an absent target', () => {
    expect(resolveTarget(ID_A, null)).toEqual({ state: 'unreadable' });
  });

  it('matches on record_id, not on the experiment id that holds it', () => {
    expect(resolveTarget('exp-1', workspace)).toEqual({ state: 'not_in_workspace' });
  });
});
