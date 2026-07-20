import { describe, it, expect } from 'vitest';
import { compose, count, EXPORT_CATALOG, REVIEW_CATALOG } from './assistantComposer';
import { SOURCE_LABELS } from './assistant';
import {
  experimentDetail,
  draftResponse,
  pendingResponse,
  validateDryRun,
  validateReadyDryRun,
  validateExported,
  auditNotExported,
  auditExported,
  warningsDryRun,
  artifactsNull,
  evidenceResponse,
  graphStatusUnavailable,
} from '../test/apiFixtures';
import type {
  ApiEvidenceEntry,
  ApiPendingItem,
  ExportReadinessBundle,
  GroundingState,
  RecordBundle,
} from './types';

// A full, shape-faithful review bundle (verbatim from the API fixtures). Only
// pending / validate / evidence are read by the review composer; the rest are
// present so the state is a real RecordBundle.
function reviewState(overrides: Partial<RecordBundle> = {}): GroundingState {
  const base = {
    detail: experimentDetail,
    groups: draftResponse.groups,
    pending: pendingResponse.pending,
    validate: validateDryRun,
    audit: auditNotExported,
    warnings: warningsDryRun,
    evidence: evidenceResponse.evidence,
    graph: graphStatusUnavailable,
  } as unknown as RecordBundle;
  return { context: 'review', bundle: { ...base, ...overrides } };
}

const VERDICT = /\b(PASS|FAIL)\b/;
const INVALID_AGAINST = /\b(in)?valid against\b/i;

describe('count() — deterministic pluralization', () => {
  it('singular at n=1, default +s plural otherwise', () => {
    expect(count(0, 'field')).toBe('0 fields');
    expect(count(1, 'field')).toBe('1 field');
    expect(count(2, 'field')).toBe('2 fields');
  });

  it('uses an explicit irregular plural when provided', () => {
    expect(count(1, 'evidence entry', 'evidence entries')).toBe('1 evidence entry');
    expect(count(2, 'evidence entry', 'evidence entries')).toBe('2 evidence entries');
    expect(count(1, 'path')).toBe('1 path');
    expect(count(2, 'path')).toBe('2 paths');
  });
});

describe('REVIEW_CATALOG — the three review chips (order + source labels)', () => {
  it('is exactly [pending_summary, blocking_paths, field_provenance] in order', () => {
    expect(REVIEW_CATALOG.map((c) => c.id)).toEqual([
      'pending_summary',
      'blocking_paths',
      'field_provenance',
    ]);
  });

  it('maps each chip to its approved source and label', () => {
    expect(REVIEW_CATALOG.map((c) => c.source)).toEqual(['workflow', 'schema', 'files']);
    expect(REVIEW_CATALOG.map((c) => c.label)).toEqual([
      'What still needs me?',
      "What's left before export?",
      'Trace a field to its source',
    ]);
  });
});

describe('SOURCE_LABELS — exact approved Title-Case map', () => {
  it('has the seven approved friendly labels', () => {
    expect(SOURCE_LABELS).toEqual({
      schema: 'Schema Rules',
      audit: 'Evidence Audit',
      files: 'Evidence & Sources',
      advisory: 'Advisory Checks',
      workflow: 'Workflow & Artifacts',
      graph: 'Project Memory',
      git: 'Project History',
    });
  });
});

describe('compose({context:"review"}) — full fixture bundle', () => {
  const out = compose(reviewState());

  it('emits three prompts whose text == chip label and answeredFrom == chip source', () => {
    expect(out.prompts.map((p) => p.text)).toEqual([
      'What still needs me?',
      "What's left before export?",
      'Trace a field to its source',
    ]);
    expect(out.prompts.map((p) => p.answeredFrom)).toEqual(['workflow', 'schema', 'files']);
  });

  it('pending_summary echoes the count + first ≤3 abouts + "…and K more"', () => {
    expect(out.prompts[0].answer).toEqual({
      text:
        '5 fields still need you: ' +
        'ssrl-archive://BL15-2/2099_run_000/notebooks/xanes_reduction_v2.ipynb, ' +
        'ssrl-archive://BL15-2/2099_run_000/raw/scan_0044.dat, ' +
        'ssrl-archive://BL15-2/2099_run_000/reduced/CuO2_merged.xdi, …and 2 more.',
      answeredFrom: 'workflow',
    });
  });

  it('blocking_paths echoes a path count + paths + routes to Validate; never echoes validity', () => {
    expect(out.prompts[1].answer).toEqual({
      text:
        '2 paths are listed as blocking export: $.assets, $.measurement.series. ' +
        'Open Validate to run the deterministic schema check.',
      answeredFrom: 'schema',
    });
  });

  it('field_provenance traces the first evidenced field to its cited source', () => {
    expect(out.prompts[2].answer).toEqual({
      text:
        "system.technique traces to mock_campaign.csv (locator: Sheet 'Campaign Info', " +
        'field=technique) — source type: spreadsheet.',
      answeredFrom: 'files',
    });
  });

  it('reply is the first non-null answer in priority order (pending → blocking → provenance)', () => {
    expect(out.reply).toEqual(out.prompts[0].answer);
    expect(out.reply.answeredFrom).toBe('workflow');
  });
});

describe('compose review — degraded / edge branches', () => {
  it('pending empty → present-but-honest message (chip still enabled)', () => {
    const out = compose(reviewState({ pending: [] }));
    expect(out.prompts[0].answer).toEqual({
      text: 'No pending fields are listed for this record.',
      answeredFrom: 'workflow',
    });
  });

  it('pending absent → chip disabled (answer undefined); reply falls through to blocking', () => {
    const out = compose(reviewState({ pending: undefined }));
    expect(out.prompts[0].answer).toBeUndefined();
    expect(out.reply.answeredFrom).toBe('schema');
    expect(out.reply.text).toContain('listed as blocking export');
  });

  it('validate errors empty → no-blocking-paths message, still routes to Validate', () => {
    const out = compose(reviewState({ validate: { ...validateDryRun, errors: [] } }));
    expect(out.prompts[1].answer).toEqual({
      text:
        'No blocking paths are listed in the current validation response. ' +
        'Open Validate to run the deterministic schema check.',
      answeredFrom: 'schema',
    });
  });

  it('validate is a singular path → grammatical "1 path is listed"', () => {
    const out = compose(
      reviewState({
        validate: { ...validateDryRun, errors: [{ path: '$.assets', message: 'required' }] },
      }),
    );
    expect(out.prompts[1].answer!.text).toBe(
      '1 path is listed as blocking export: $.assets. ' +
        'Open Validate to run the deterministic schema check.',
    );
  });

  it('validate absent → blocking chip disabled (answer undefined)', () => {
    const out = compose(reviewState({ validate: undefined }));
    expect(out.prompts[1].answer).toBeUndefined();
  });

  it('evidence none → honest no-cited-source message', () => {
    const out = compose(reviewState({ evidence: [] }));
    expect(out.prompts[2].answer).toEqual({
      text: 'No cited source is recorded for a field yet.',
      answeredFrom: 'files',
    });
  });

  it('pending + validate both absent → reply falls through to provenance (files)', () => {
    const out = compose(reviewState({ pending: undefined, validate: undefined, evidence: [] }));
    expect(out.reply).toEqual({
      text: 'No cited source is recorded for a field yet.',
      answeredFrom: 'files',
    });
  });
});

describe('compose — no-verdict guarantee across every composed string', () => {
  const states: GroundingState[] = [
    reviewState(),
    reviewState({ pending: [] }),
    reviewState({ pending: undefined }),
    reviewState({ validate: { ...validateDryRun, errors: [] } }),
    reviewState({ validate: undefined }),
    reviewState({ evidence: [] }),
  ];

  it('no reply/prompt/answer string states PASS/FAIL or "(in)valid against"', () => {
    for (const state of states) {
      const out = compose(state);
      const strings = [
        out.reply.text,
        ...out.prompts.flatMap((p) => [p.text, p.answer?.text ?? '']),
      ];
      for (const s of strings) {
        expect(s).not.toMatch(VERDICT);
        expect(s).not.toMatch(INVALID_AGAINST);
      }
    }
  });

  it('never echoes validate.ok as a validity claim', () => {
    const out = compose(reviewState());
    const all = [out.reply.text, ...out.prompts.map((p) => p.answer?.text ?? '')].join(' ');
    expect(all).not.toMatch(/\b(valid|invalid)\b/i);
  });
});

describe('compose — review + export wired; other contexts still throw', () => {
  it('throws for contexts not yet implemented (evidence / complete / memory)', () => {
    for (const context of ['evidence', 'complete', 'memory'] as const) {
      const notWired = { context } as unknown as GroundingState;
      expect(() => compose(notWired)).toThrow('compose: context not implemented yet');
    }
  });
});

// --- Fix 6a: field_provenance must never render undefined/null/empty ---------
describe('field_provenance — deterministic, never renders undefined/null/empty (6a)', () => {
  const provenance = (evidence: unknown) =>
    compose(reviewState({ evidence: evidence as unknown as ApiEvidenceEntry[] })).prompts[2]
      .answer!;

  it('first sub-entry lacks source_file → traces to the LATER usable file', () => {
    const answer = provenance([
      {
        path: 'sample.material.formula',
        value: 'CuO2',
        status: 'verified',
        evidence: [
          { source_type: 'user_confirmation', question: 'confirm?', answer: 'yes' },
          { source_type: 'spreadsheet', source_file: 'campaign.csv', locator: 'row 3' },
        ],
      },
    ]);
    expect(answer).toEqual({
      text:
        'sample.material.formula traces to campaign.csv (locator: row 3) — source type: spreadsheet.',
      answeredFrom: 'files',
    });
    expect(answer.text).not.toContain('undefined');
    expect(answer.text).not.toContain('null');
  });

  it('file-trace with a usable source_file but empty source_type → omits the "source type" clause', () => {
    const answer = provenance([
      {
        path: 'system.technique',
        value: 'X',
        status: 'verified',
        evidence: [{ source_type: '', source_file: 'campaign.csv', locator: "Sheet 'A'" }],
      },
    ]);
    expect(answer).toEqual({
      text: "system.technique traces to campaign.csv (locator: Sheet 'A').",
      answeredFrom: 'files',
    });
    expect(answer.text).not.toContain('source type');
    expect(answer.text).not.toMatch(/\s\.$/);
    expect(answer.text).not.toContain('undefined');
    expect(answer.text).not.toContain('null');
  });

  it('no entry has a usable source_file but source types exist → honest fallback (no file trace)', () => {
    const answer = provenance([
      {
        path: 'system.domain',
        value: 'experimental',
        status: 'inferred',
        evidence: [
          { source_type: 'derivation', rule: 'r1' },
          { source_type: 'user_confirmation', question: 'q', answer: 'a' },
        ],
      },
    ]);
    expect(answer).toEqual({
      text:
        'system.domain has 2 evidence entries but no cited source file — ' +
        'source types: derivation, user_confirmation.',
      answeredFrom: 'files',
    });
    expect(answer.text).not.toContain('traces to');
    expect(answer.text).not.toContain('undefined');
    expect(answer.text).not.toContain('null');
  });

  it('evidenced entry with neither a usable source_file nor usable source types → stable string', () => {
    const answer = provenance([
      {
        path: 'implicit:absorbing_element',
        value: 'Cu',
        status: 'inferred',
        evidence: [{ source_type: '', rule: 'derived' }],
      },
    ]);
    expect(answer).toEqual({
      text: 'No cited source file is recorded for this field.',
      answeredFrom: 'files',
    });
    expect(answer.text).not.toContain('undefined');
    expect(answer.text).not.toContain('null');
  });

  it('empty/whitespace source_file on the only sub-entry → treated as absent (no "traces to")', () => {
    const answer = provenance([
      {
        path: 'system.technique',
        value: 'X',
        status: 'verified',
        evidence: [{ source_type: 'spreadsheet', source_file: '   ', locator: 'loc' }],
      },
    ]);
    expect(answer).toEqual({
      text:
        'system.technique has 1 evidence entry but no cited source file — source type: spreadsheet.',
      answeredFrom: 'files',
    });
    expect(answer.text).not.toContain('traces to');
    expect(answer.text).not.toContain('undefined');
    expect(answer.text).not.toContain('null');
  });

  it('sweep: none of these provenance states ever emit "undefined" or "null"', () => {
    const states: unknown[] = [
      [
        {
          path: 'a.b',
          value: null,
          status: 'inferred',
          evidence: [{ source_type: 'derivation', rule: 'r' }],
        },
      ],
      [
        {
          path: 'c.d',
          value: null,
          status: 'verified',
          evidence: [
            { source_type: 'user_confirmation', question: 'q', answer: 'a' },
            { source_type: 'spreadsheet', source_file: 'f.csv' },
          ],
        },
      ],
      [
        {
          path: 'e.f',
          value: null,
          status: 'inferred',
          evidence: [{ source_type: '', source_file: '' }],
        },
      ],
      [],
    ];
    for (const evidence of states) {
      const answer = provenance(evidence);
      expect(answer.text).not.toContain('undefined');
      expect(answer.text).not.toContain('null');
      expect(answer.text).not.toContain('traces to  ');
    }
  });
});

// --- Fix 6b: pending count and displayed list must agree ---------------------
describe('pending_summary — count and displayed list agree (6b)', () => {
  const summary = (pending: unknown) =>
    compose(reviewState({ pending: pending as unknown as ApiPendingItem[] })).prompts[0].answer!;

  it('every item has about → labels are the abouts (existing-fixture path, derived from the fixture)', () => {
    const out = compose(reviewState());
    const first3 = pendingResponse.pending.slice(0, 3).map((p) => p.about);
    expect(out.prompts[0].answer!.text).toBe(
      `5 fields still need you: ${first3.join(', ')}, …and 2 more.`,
    );
  });

  it('exactly one item lacks about → it still appears (question fallback); count still equals total', () => {
    const answer = summary([
      { id: 'a1', kind: 'asset', question: 'q1?', about: 'about-one' },
      { id: 'a2', kind: 'asset', question: 'q2-question?', about: null },
    ]);
    expect(answer.text).toBe('2 fields still need you: about-one, q2-question?.');
    expect(answer.text).toContain('q2-question?');
  });

  it('all items lack about → labels come from question/id; no empty segment after the colon', () => {
    const answer = summary([
      { id: 'id-1', kind: 'asset', question: 'question-1?', about: null },
      { id: 'id-2', kind: 'series', question: '', about: undefined },
    ]);
    expect(answer.text).toBe('2 fields still need you: question-1?, id-2.');
    expect(answer.text).not.toContain(', ,');
    expect(answer.text).not.toMatch(/:\s*[,.]/);
    expect(answer.text).not.toContain('unnamed pending field');
  });

  it('more than three mixed-shape items → first 3 labels + "…and K more" (K = length - 3)', () => {
    const pending = [
      { id: 'x1', kind: 'asset', question: 'q1', about: 'A1' },
      { id: 'x2', kind: 'asset', question: 'q2', about: null },
      { id: 'x3', kind: 'series', question: '', about: null },
      { id: 'x4', kind: 'descriptor', question: 'q4', about: 'A4' },
      { id: 'x5', kind: 'edge', question: 'q5', about: 'A5' },
    ];
    const K = pending.length - 3;
    const answer = summary(pending);
    expect(K).toBe(2);
    expect(answer.text).toBe(`5 fields still need you: A1, q2, x3, …and ${K} more.`);
    expect(answer.text).toContain(`…and ${K} more`);
  });

  it('singular grammar: 1 pending → "1 field still needs you"', () => {
    const answer = summary([{ id: 'z', kind: 'asset', question: 'q', about: 'only-one' }]);
    expect(answer.text).toBe('1 field still needs you: only-one.');
  });

  it('plural grammar: 2 pending → "2 fields still need you"', () => {
    const answer = summary([
      { id: 'z1', kind: 'asset', question: 'q1', about: 'one' },
      { id: 'z2', kind: 'asset', question: 'q2', about: 'two' },
    ]);
    expect(answer.text).toBe('2 fields still need you: one, two.');
  });

  it('exact "…and K more" for a known count of 7 → K = 4', () => {
    const pending = Array.from({ length: 7 }, (_, i) => ({
      id: `p${i}`,
      kind: 'asset',
      question: `q${i}`,
      about: `A${i}`,
    }));
    const answer = summary(pending);
    expect(answer.text).toBe('7 fields still need you: A0, A1, A2, …and 4 more.');
  });
});

// --- P25.4: Ready to Export context ------------------------------------------

// A full, shape-faithful export bundle (verbatim from the API fixtures). Only
// audit / validate / warnings are read by the export composer; the rest are
// present so the state is a real ExportReadinessBundle. Defaults describe the
// POST-export state (audit has a record, dry-run has passed).
function exportState(overrides: Partial<ExportReadinessBundle> = {}): GroundingState {
  const base = {
    detail: experimentDetail,
    pending: pendingResponse.pending,
    validate: validateExported,
    audit: auditExported,
    warnings: warningsDryRun,
    graph: graphStatusUnavailable,
    artifacts: artifactsNull,
  } as unknown as ExportReadinessBundle;
  return { context: 'export', bundle: { ...base, ...overrides } };
}

const twoWarnings = {
  advisory: true as const,
  gating: false as const,
  warnings: [
    { code: 'NO_LINKS', where: 'record.links', message: 'no relationships declared' },
    { code: 'THIN_DESCRIPTORS', where: 'record.descriptors', message: 'few descriptors present' },
  ],
};

describe('EXPORT_CATALOG — the three export chips (order + source labels)', () => {
  it('is exactly [coverage_vs_validity, blocking_paths, advisory_detail] in order', () => {
    expect(EXPORT_CATALOG.map((c) => c.id)).toEqual([
      'coverage_vs_validity',
      'blocking_paths',
      'advisory_detail',
    ]);
  });

  it('maps each chip to its approved source and label', () => {
    expect(EXPORT_CATALOG.map((c) => c.source)).toEqual(['audit', 'schema', 'advisory']);
    expect(EXPORT_CATALOG.map((c) => c.label)).toEqual([
      'Is coverage the same as valid?',
      "What's left before export?",
      'Explain the advisory warning',
    ]);
    // the blocker is the routed truth-question chip
    expect(EXPORT_CATALOG.find((c) => c.id === 'blocking_paths')!.routed).toBe(true);
  });
});

describe('compose({context:"export"}) — post-export fixture bundle', () => {
  const out = compose(exportState());

  it('emits three prompts whose text == chip label and answeredFrom == chip source', () => {
    expect(out.prompts.map((p) => p.text)).toEqual([
      'Is coverage the same as valid?',
      "What's left before export?",
      'Explain the advisory warning',
    ]);
    expect(out.prompts.map((p) => p.answeredFrom)).toEqual(['audit', 'schema', 'advisory']);
  });

  it('coverage_vs_validity echoes evidence_present/evidence_expected live (33/33), never a verdict', () => {
    expect(out.prompts[0].answer).toEqual({
      text:
        'Coverage is 33/33 evidenced fields. It describes how many expected fields carry evidence; ' +
        'the schema check is separate.',
      answeredFrom: 'audit',
    });
  });

  it('blocking_paths (post-export, 0 errors) → no-blocking message, still routes to Validate', () => {
    expect(out.prompts[1].answer).toEqual({
      text:
        'No blocking paths are listed in the current validation response. ' +
        'Open Validate to run the deterministic schema check.',
      answeredFrom: 'schema',
    });
  });

  it('advisory_detail echoes the first warning verbatim, flagged advisory/non-gating', () => {
    expect(out.prompts[2].answer).toEqual({
      text: 'NO_LINKS — no relationships declared (advisory, non-gating; where: record.links).',
      answeredFrom: 'advisory',
    });
  });

  it('reply is the first non-null answer in priority order (coverage → blocking → advisory)', () => {
    expect(out.reply).toEqual(out.prompts[0].answer);
    expect(out.reply.answeredFrom).toBe('audit');
  });
});

describe('compose export — coverage echo variants + pre-export fallback + disabled chip', () => {
  it('interpolates any live present/expected pair (11/14), not just the fixture', () => {
    const out = compose(
      exportState({
        audit: {
          records: [
            {
              name: 'r.json',
              ok: true,
              schema_errors: [],
              evidence_present: 11,
              evidence_expected: 14,
              uncovered: [],
              dangling: [],
            },
          ],
          text: '',
        },
      }),
    );
    expect(out.prompts[0].answer!.text).toBe(
      'Coverage is 11/14 evidenced fields. It describes how many expected fields carry evidence; ' +
        'the schema check is separate.',
    );
  });

  it('pre-export (records:[]) → honest empty-coverage fallback (chip still enabled)', () => {
    const out = compose(exportState({ audit: auditNotExported }));
    expect(out.prompts[0].answer).toEqual({
      text: 'No coverage figures yet — coverage appears after export.',
      answeredFrom: 'audit',
    });
    // pre-export the fallback is the panel reply (coverage is the lead chip)
    expect(out.reply).toEqual(out.prompts[0].answer);
  });

  it('audit payload absent → coverage chip DISABLED (answer undefined); reply falls to blocking', () => {
    const out = compose(exportState({ audit: undefined }));
    expect(out.prompts[0].answer).toBeUndefined();
    expect(out.reply.answeredFrom).toBe('schema');
  });
});

describe('compose export — blocking_paths routing (shares §5.1 template; never echoes validity)', () => {
  it('2 errors → path count + first paths + route (from validateDryRun)', () => {
    const out = compose(exportState({ validate: validateDryRun }));
    expect(out.prompts[1].answer).toEqual({
      text:
        '2 paths are listed as blocking export: $.assets, $.measurement.series. ' +
        'Open Validate to run the deterministic schema check.',
      answeredFrom: 'schema',
    });
  });

  it('1 error → grammatical "1 path is listed"', () => {
    const out = compose(
      exportState({
        validate: { ...validateDryRun, errors: [{ path: '$.assets', message: 'required' }] },
      }),
    );
    expect(out.prompts[1].answer!.text).toBe(
      '1 path is listed as blocking export: $.assets. ' +
        'Open Validate to run the deterministic schema check.',
    );
  });

  it('0 errors (validateReadyDryRun) → no-blocking message', () => {
    const out = compose(exportState({ validate: validateReadyDryRun }));
    expect(out.prompts[1].answer!.text).toBe(
      'No blocking paths are listed in the current validation response. ' +
        'Open Validate to run the deterministic schema check.',
    );
  });

  it('validate absent → blocking chip disabled (answer undefined)', () => {
    const out = compose(exportState({ validate: undefined }));
    expect(out.prompts[1].answer).toBeUndefined();
  });
});

describe('compose export — advisory_detail (echo, pluralized "…and K more", empty, disabled)', () => {
  it('multiple warnings → first echoed + ". …and K more" (K = length - 1)', () => {
    const out = compose(exportState({ warnings: twoWarnings }));
    expect(out.prompts[2].answer!.text).toBe(
      'NO_LINKS — no relationships declared (advisory, non-gating; where: record.links). …and 1 more.',
    );
  });

  it('no warnings → honest "No advisory warnings on this record."', () => {
    const out = compose(
      exportState({ warnings: { advisory: true, gating: false, warnings: [] } }),
    );
    expect(out.prompts[2].answer).toEqual({
      text: 'No advisory warnings on this record.',
      answeredFrom: 'advisory',
    });
  });

  it('warnings payload absent → advisory chip disabled (answer undefined)', () => {
    const out = compose(exportState({ warnings: undefined }));
    expect(out.prompts[2].answer).toBeUndefined();
  });
});

describe('compose export — no-verdict guarantee across every composed string', () => {
  const states: GroundingState[] = [
    exportState(),
    exportState({ audit: auditNotExported }),
    exportState({ audit: undefined }),
    exportState({ validate: validateDryRun }),
    exportState({ validate: validateReadyDryRun }),
    exportState({ validate: undefined }),
    exportState({ warnings: twoWarnings }),
    exportState({ warnings: { advisory: true, gating: false, warnings: [] } }),
  ];

  it('no reply/prompt/answer string states PASS/FAIL or "(in)valid against"', () => {
    for (const state of states) {
      const out = compose(state);
      const strings = [
        out.reply.text,
        ...out.prompts.flatMap((p) => [p.text, p.answer?.text ?? '']),
      ];
      for (const s of strings) {
        expect(s).not.toMatch(VERDICT);
        expect(s).not.toMatch(INVALID_AGAINST);
      }
    }
  });

  it('never echoes validate.ok as a valid/invalid claim (even when validate.ok is true)', () => {
    const out = compose(exportState({ validate: validateExported }));
    const all = [out.reply.text, ...out.prompts.map((p) => p.answer?.text ?? '')].join(' ');
    expect(all).not.toMatch(/\b(valid|invalid)\b/i);
  });
});
