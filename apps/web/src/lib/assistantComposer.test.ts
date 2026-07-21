import { describe, it, expect } from 'vitest';
import {
  compose,
  count,
  COMPLETE_CATALOG,
  EVIDENCE_CATALOG,
  EXPORT_CATALOG,
  REVIEW_CATALOG,
} from './assistantComposer';
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
  artifactsExported,
  evidenceResponse,
  evidenceExported,
  graphStatusUnavailable,
} from '../test/apiFixtures';
import type {
  ApiEvidenceEntry,
  ApiPendingItem,
  EvidenceBundle,
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

describe('compose — review + export + evidence + complete + memory all wired', () => {
  it('evidence is WIRED — compose does NOT throw for it (P25.5)', () => {
    const wired = {
      context: 'evidence',
      bundle: {
        detail: experimentDetail,
        evidence: evidenceExported.evidence,
        artifacts: artifactsNull,
        graph: graphStatusUnavailable,
        sourcePreviews: {},
      },
    } as unknown as GroundingState;
    expect(() => compose(wired)).not.toThrow();
  });

  it('complete is now WIRED — compose does NOT throw for it (P25.6)', () => {
    const wired = {
      context: 'complete',
      detail: experimentDetail,
      pending: pendingResponse.pending,
    } as unknown as GroundingState;
    expect(() => compose(wired)).not.toThrow();
  });

  it('memory is now WIRED — compose does NOT throw for it (P25.7)', () => {
    // P25.7 wired the last context; memory no longer throws. It requires a graph
    // status (chosen by availability), so pass the shape-faithful fixture.
    const wired = {
      context: 'memory',
      graph: graphStatusUnavailable,
    } as unknown as GroundingState;
    expect(() => compose(wired)).not.toThrow();
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

// --- P25.5: Evidence Explorer context ----------------------------------------

// A full, shape-faithful evidence bundle (verbatim from the API fixtures). The
// evidence composer reads only evidence + artifacts (+ the caller's
// selectedPath); the rest are present so the state is a real EvidenceBundle.
// `evidenceExported` carries system.technique (1 entry), assets:processing_notebook
// (2 entries: file_listing + user_confirmation), implicit:absorbing_element (1).
function evidenceState(
  overrides: Partial<EvidenceBundle> = {},
  selectedPath?: string,
): GroundingState {
  const base = {
    detail: experimentDetail,
    evidence: evidenceExported.evidence,
    artifacts: artifactsNull,
    graph: graphStatusUnavailable,
    sourcePreviews: {},
  } as unknown as EvidenceBundle;
  return { context: 'evidence', bundle: { ...base, ...overrides }, selectedPath };
}

const NOTEBOOK_PATH = 'assets:processing_notebook';
const RECORD_PATH = artifactsExported.record_path;
const SIDECAR_PATH = artifactsExported.sidecar_path;

describe('EVIDENCE_CATALOG — the three evidence chips (order + source labels)', () => {
  it('is exactly [evidence_multiplicity, sidecar_convention, artifact_paths] in order', () => {
    expect(EVIDENCE_CATALOG.map((c) => c.id)).toEqual([
      'evidence_multiplicity',
      'sidecar_convention',
      'artifact_paths',
    ]);
  });

  it('maps each chip to its approved source and label', () => {
    expect(EVIDENCE_CATALOG.map((c) => c.source)).toEqual(['files', 'files', 'workflow']);
    expect(EVIDENCE_CATALOG.map((c) => c.label)).toEqual([
      'Why multiple evidence entries?',
      'What is the evidence sidecar?',
      'Where are the exported artifacts?',
    ]);
  });
});

describe('evidence_multiplicity — count + source types agree; no provenance leak', () => {
  const multiplicity = (state: GroundingState) => compose(state).prompts[0].answer;

  it('no selectedPath → "Select a field…" guidance (chip enabled)', () => {
    expect(multiplicity(evidenceState())).toEqual({
      text: 'Select a field in the Evidence Trail to see its supporting entries.',
      answeredFrom: 'files',
    });
  });

  it('selectedPath not found → same "Select a field…" guidance', () => {
    expect(multiplicity(evidenceState({}, 'no.such.path'))).toEqual({
      text: 'Select a field in the Evidence Trail to see its supporting entries.',
      answeredFrom: 'files',
    });
  });

  it('entry with 0 evidence entries → honest "no separate evidence entries recorded"', () => {
    const state = evidenceState(
      {
        evidence: [
          { path: 'sample.empty', value: 'x', status: 'verified', evidence: [] },
        ] as unknown as ApiEvidenceEntry[],
      },
      'sample.empty',
    );
    expect(multiplicity(state)).toEqual({
      text: 'sample.empty has no separate evidence entries recorded.',
      answeredFrom: 'files',
    });
  });

  it('1 entry → singular; NO "Multiple entries" sentence', () => {
    const answer = multiplicity(evidenceState({}, 'system.technique'))!;
    expect(answer).toEqual({
      text: 'system.technique has 1 evidence entry: spreadsheet.',
      answeredFrom: 'files',
    });
    expect(answer.text).not.toContain('Multiple entries');
  });

  it('2 entries → plural + the exact restrained "separate support" sentence', () => {
    const answer = multiplicity(evidenceState({}, NOTEBOOK_PATH))!;
    expect(answer).toEqual({
      text:
        'assets:processing_notebook has 2 evidence entries: file_listing, user_confirmation. ' +
        'Multiple entries can provide separate support for the same field.',
      answeredFrom: 'files',
    });
    // the appended sentence is the exact restrained wording — never a
    // correctness/verdict word. (Word boundaries so the legitimate source-type
    // token `user_confirmation` is not a false positive.)
    expect(answer.text).not.toMatch(/\b(corroborate|prove|confirm|validate)\b/i);
  });

  it('>3 entries → capped list "…and K more" with exact K and total count matching', () => {
    const state = evidenceState(
      {
        evidence: [
          {
            path: 'sample.many',
            value: 'v',
            status: 'verified',
            evidence: [
              { source_type: 'spreadsheet' },
              { source_type: 'file_listing' },
              { source_type: 'document' },
              { source_type: 'derivation' },
              { source_type: 'user_confirmation' },
            ],
          },
        ] as unknown as ApiEvidenceEntry[],
      },
      'sample.many',
    );
    const answer = multiplicity(state)!;
    expect(answer.text).toBe(
      'sample.many has 5 evidence entries: spreadsheet, file_listing, document, …and 2 more. ' +
        'Multiple entries can provide separate support for the same field.',
    );
    // shown count (5) and the remaining count (2, i.e. 5 − 3 shown) both agree
    expect(answer.text).toContain('5 evidence entries');
    expect(answer.text).toContain('…and 2 more');
  });

  it('duplicate source types are preserved honestly (both listed, count matches)', () => {
    const state = evidenceState(
      {
        evidence: [
          {
            path: 'sample.dup',
            value: 'v',
            status: 'verified',
            evidence: [{ source_type: 'spreadsheet' }, { source_type: 'spreadsheet' }],
          },
        ] as unknown as ApiEvidenceEntry[],
      },
      'sample.dup',
    );
    expect(multiplicity(state)!.text).toBe(
      'sample.dup has 2 evidence entries: spreadsheet, spreadsheet. ' +
        'Multiple entries can provide separate support for the same field.',
    );
  });

  it('unusable source_type → token becomes "unspecified source"; count still matches', () => {
    const state = evidenceState(
      {
        evidence: [
          {
            path: 'sample.bad',
            value: 'v',
            status: 'verified',
            evidence: [{ source_type: '' }, { source_type: 'spreadsheet' }],
          },
        ] as unknown as ApiEvidenceEntry[],
      },
      'sample.bad',
    );
    expect(multiplicity(state)!.text).toBe(
      'sample.bad has 2 evidence entries: unspecified source, spreadsheet. ' +
        'Multiple entries can provide separate support for the same field.',
    );
  });

  it('NEVER leaks source_file / locator / quote into the multiplicity text', () => {
    const answer = multiplicity(evidenceState({}, NOTEBOOK_PATH))!;
    // the notebook entry carries a source_file + locator + quote — none may appear
    expect(answer.text).not.toContain('raw_scan_listing.txt');
    expect(answer.text).not.toContain('line 16');
    expect(answer.text).not.toContain('xanes_reduction_v2.ipynb');
    expect(answer.text).not.toContain('ssrl-archive');
  });
});

describe('sidecar_convention — exact wording, never an official standard or a verdict', () => {
  const out = compose(evidenceState());
  const answer = out.prompts[1].answer!;

  it('emits the exact approved sidecar wording', () => {
    expect(answer).toEqual({
      text:
        'The evidence sidecar is an ISAAC assistant convention, not part of the official ISAAC ' +
        'schema. It preserves field-level evidence that the official record has no dedicated ' +
        'place to store.',
      answeredFrom: 'files',
    });
  });

  it('the source label resolves to "Evidence & Sources"', () => {
    expect(SOURCE_LABELS[answer.answeredFrom]).toBe('Evidence & Sources');
  });

  it('never calls it an official ISAAC standard, and carries no verdict/validity word', () => {
    expect(answer.text).not.toContain('official ISAAC standard');
    expect(answer.text).not.toMatch(/\b(PASS|FAIL|valid|invalid)\b/i);
  });
});

describe('artifact_paths — safe, never renders undefined/null/empty', () => {
  const artifacts = (state: GroundingState) => compose(state).prompts[2].answer!;

  it('both paths present → names record + sidecar', () => {
    const answer = artifacts(evidenceState({ artifacts: artifactsExported }));
    expect(answer).toEqual({
      text: `Exported: record ${RECORD_PATH} and its evidence sidecar ${SIDECAR_PATH}.`,
      answeredFrom: 'workflow',
    });
  });

  it('record only → names record, states no sidecar path', () => {
    const answer = artifacts(
      evidenceState({
        artifacts: { record: null, sidecar: null, record_path: RECORD_PATH, sidecar_path: null },
      }),
    );
    expect(answer.text).toBe(
      `Exported: record ${RECORD_PATH}. No evidence sidecar path is recorded.`,
    );
  });

  it('sidecar only → names sidecar, states no record path', () => {
    const answer = artifacts(
      evidenceState({
        artifacts: { record: null, sidecar: null, record_path: null, sidecar_path: SIDECAR_PATH },
      }),
    );
    expect(answer.text).toBe(
      `Exported: evidence sidecar ${SIDECAR_PATH}. No record path is recorded.`,
    );
  });

  it('neither (artifactsNull) → honest not-exported message', () => {
    const answer = artifacts(evidenceState({ artifacts: artifactsNull }));
    expect(answer).toEqual({
      text: 'Not exported yet — export writes the record plus its evidence sidecar.',
      answeredFrom: 'workflow',
    });
  });

  it('empty-string / null / undefined path values each produce a safe message', () => {
    const variants = [
      { record_path: '', sidecar_path: '' },
      { record_path: null, sidecar_path: null },
      { record_path: undefined, sidecar_path: undefined },
      { record_path: '   ', sidecar_path: '   ' },
    ];
    for (const v of variants) {
      const answer = artifacts(
        evidenceState({
          artifacts: { record: null, sidecar: null, ...v } as unknown as EvidenceBundle['artifacts'],
        }),
      );
      expect(answer.text).toBe(
        'Not exported yet — export writes the record plus its evidence sidecar.',
      );
      expect(/undefined|null/.test(answer.text)).toBe(false);
    }
  });
});

describe('compose evidence — no-verdict / no-undefined sweep over every composed string', () => {
  const states: GroundingState[] = [
    evidenceState(),
    evidenceState({}, 'system.technique'),
    evidenceState({}, NOTEBOOK_PATH),
    evidenceState({}, 'implicit:absorbing_element'),
    evidenceState({}, 'no.such.path'),
    evidenceState({ artifacts: artifactsExported }),
    evidenceState({
      artifacts: { record: null, sidecar: null, record_path: RECORD_PATH, sidecar_path: null },
    }),
    evidenceState({
      artifacts: { record: null, sidecar: null, record_path: null, sidecar_path: SIDECAR_PATH },
    }),
    evidenceState({
      evidence: [
        { path: 'p.empty', value: 'x', status: 'verified', evidence: [] },
      ] as unknown as ApiEvidenceEntry[],
    }),
  ];

  it('no composed string states PASS/FAIL/valid/invalid or contains "undefined"/"null"', () => {
    for (const state of states) {
      const out = compose(state);
      const strings = [
        out.reply.text,
        ...out.prompts.flatMap((p) => [p.text, p.answer?.text ?? '']),
      ];
      for (const s of strings) {
        expect(s).not.toMatch(/\b(PASS|FAIL|valid|invalid)\b/i);
        expect(s).not.toContain('undefined');
        expect(s).not.toContain('null');
      }
    }
  });

  it('the panel reply is the first non-null answer (multiplicity guidance leads)', () => {
    const out = compose(evidenceState());
    expect(out.reply).toEqual(out.prompts[0].answer);
    expect(out.reply.answeredFrom).toBe('files');
  });
});

// --- P25.6: Complete Missing Fields context ----------------------------------

// A shape-faithful complete state (Q-D: {detail, pending} ONLY — no
// validate/audit/graph). The composer reads pending + selectedPendingId; detail
// is present so the state is a real `complete` GroundingState.
function completeState(
  pending: unknown = pendingResponse.pending,
  selectedPendingId?: string,
): GroundingState {
  return {
    context: 'complete',
    detail: experimentDetail,
    pending: pending as unknown as ApiPendingItem[],
    selectedPendingId,
  } as unknown as GroundingState;
}

const CP = pendingResponse.pending; // 5 fixture pending items; item 0 = notebook
const CP_SUMMARY =
  `5 fields need you: ${CP[0].about}, ${CP[1].about}, ${CP[2].about}, …and 2 more. ` +
  'Confirm or skip each below.';
const CP_EXPLAIN_0 =
  `${CP[0].question} — about ${CP[0].about}. Answer via propose → stage → confirm below.`;
const MISSING_BEHAVIOR =
  'Leaving a field missing keeps it honest-missing — never guessed. Whether it blocks export ' +
  'is a schema question — open Validate to run the deterministic schema check.';

describe('COMPLETE_CATALOG — the three complete chips (order + source labels)', () => {
  it('is exactly [pending_summary, explain_pending_item, missing_field_behavior] in order', () => {
    expect(COMPLETE_CATALOG.map((c) => c.id)).toEqual([
      'pending_summary',
      'explain_pending_item',
      'missing_field_behavior',
    ]);
  });

  it('maps each chip to its approved source and label', () => {
    expect(COMPLETE_CATALOG.map((c) => c.source)).toEqual(['workflow', 'workflow', 'schema']);
    expect(COMPLETE_CATALOG.map((c) => c.label)).toEqual([
      'Which fields still need me?',
      'What does this question want?',
      'What if I leave one missing?',
    ]);
    // the missing-field chip is the routed truth-question chip
    expect(COMPLETE_CATALOG.find((c) => c.id === 'missing_field_behavior')!.routed).toBe(true);
  });
});

describe('compose({context:"complete"}) — full fixture (current item = pending[0])', () => {
  const out = compose(completeState(CP, CP[0].id));

  it('emits three prompts whose text == chip label and answeredFrom == chip source', () => {
    expect(out.prompts.map((p) => p.text)).toEqual([
      'Which fields still need me?',
      'What does this question want?',
      'What if I leave one missing?',
    ]);
    expect(out.prompts.map((p) => p.answeredFrom)).toEqual(['workflow', 'workflow', 'schema']);
  });

  it('pending_summary echoes the count + first ≤3 abouts + "…and K more" + the CTA', () => {
    expect(out.prompts[0].answer).toEqual({ text: CP_SUMMARY, answeredFrom: 'workflow' });
  });

  it('explain_pending_item echoes the SELECTED question + about + the propose→stage→confirm line', () => {
    expect(out.prompts[1].answer).toEqual({ text: CP_EXPLAIN_0, answeredFrom: 'workflow' });
  });

  it('missing_field_behavior is the routed static schema answer', () => {
    expect(out.prompts[2].answer).toEqual({ text: MISSING_BEHAVIOR, answeredFrom: 'schema' });
  });

  it('reply is the first non-null answer in priority order (pending summary leads)', () => {
    expect(out.reply).toEqual(out.prompts[0].answer);
    expect(out.reply.answeredFrom).toBe('workflow');
  });
});

describe('compose complete — pending_summary echo variants + empty + disabled', () => {
  const summary = (pending: unknown) => compose(completeState(pending)).prompts[0].answer;

  it('empty pending → present-but-honest message (chip still enabled)', () => {
    expect(summary([])).toEqual({
      text: 'This draft currently has no pending fields listed.',
      answeredFrom: 'workflow',
    });
  });

  it('pending absent → chip disabled (answer undefined); reply falls to explain guidance', () => {
    // pass pending explicitly absent (bypasses the builder's fixture default)
    const out = compose({
      context: 'complete',
      detail: experimentDetail,
      pending: undefined,
    } as unknown as GroundingState);
    expect(out.prompts[0].answer).toBeUndefined();
    expect(out.reply.text).toBe('Select a field below to see what it asks.');
    expect(out.reply.answeredFrom).toBe('workflow');
  });

  it('singular grammar: 1 pending → "1 field needs you"', () => {
    expect(summary([{ id: 'z', kind: 'asset', question: 'q', about: 'only-one' }])!.text).toBe(
      '1 field needs you: only-one. Confirm or skip each below.',
    );
  });

  it('about → question → id fallback ladder; count and displayed list agree (>3 → "…and K more")', () => {
    const answer = summary([
      { id: 'x1', kind: 'asset', question: 'q1', about: 'A1' },
      { id: 'x2', kind: 'asset', question: 'q2-question?', about: null },
      { id: 'x3', kind: 'series', question: '', about: null },
      { id: 'x4', kind: 'descriptor', question: 'q4', about: 'A4' },
    ])!;
    expect(answer.text).toBe('4 fields need you: A1, q2-question?, x3, …and 1 more. Confirm or skip each below.');
    expect(answer.text).not.toContain('unnamed pending field');
    expect(answer.text).not.toContain('undefined');
    expect(answer.text).not.toContain('null');
  });
});

describe('compose complete — explain_pending_item (selection, missing about, none selected)', () => {
  const explain = (pending: unknown, selectedPendingId?: string) =>
    compose(completeState(pending, selectedPendingId)).prompts[1].answer!;

  it('no selectedPendingId → "Select a field below…" guidance (chip enabled)', () => {
    expect(explain(CP)).toEqual({
      text: 'Select a field below to see what it asks.',
      answeredFrom: 'workflow',
    });
  });

  it('selectedPendingId not found in pending → same guidance', () => {
    expect(explain(CP, 'no.such.id').text).toBe('Select a field below to see what it asks.');
  });

  it('selected item lacks a usable about → drops the "— about" clause (never "about undefined")', () => {
    const answer = explain(
      [{ id: 'series', kind: 'series', question: 'Which reduced spectrum?', about: null }],
      'series',
    );
    expect(answer.text).toBe('Which reduced spectrum? Answer via propose → stage → confirm below.');
    expect(answer.text).not.toContain('about');
    expect(answer.text).not.toContain('undefined');
    expect(answer.text).not.toContain('null');
  });

  it('selects the item by id (not by position) — the descriptor item, not pending[0]', () => {
    const answer = explain(CP, CP[4].id);
    expect(answer.text).toBe(
      `${CP[4].question} — about ${CP[4].about}. Answer via propose → stage → confirm below.`,
    );
  });
});

describe('compose complete — missing_field_behavior (static, routed, schema)', () => {
  it('emits the exact approved copy and routes to the deterministic schema check', () => {
    const out = compose(completeState(CP, CP[0].id));
    expect(out.prompts[2].answer).toEqual({ text: MISSING_BEHAVIOR, answeredFrom: 'schema' });
    expect(out.prompts[2].answer!.text).toContain('open Validate to run the deterministic schema check');
    expect(out.prompts[2].answer!.text).not.toContain('valid against');
  });
});

describe('compose complete — no-verdict guarantee across every composed string', () => {
  const states: GroundingState[] = [
    completeState(CP, CP[0].id),
    completeState(CP),
    completeState([]),
    completeState(undefined),
    completeState([{ id: 'z', kind: 'asset', question: 'q', about: 'only-one' }], 'z'),
  ];

  it('no reply/prompt/answer string states PASS/FAIL or "(in)valid against"; none render undefined/null', () => {
    for (const state of states) {
      const out = compose(state);
      const strings = [
        out.reply.text,
        ...out.prompts.flatMap((p) => [p.text, p.answer?.text ?? '']),
      ];
      for (const s of strings) {
        expect(s).not.toMatch(VERDICT);
        expect(s).not.toMatch(INVALID_AGAINST);
        expect(s).not.toContain('undefined');
        expect(s).not.toContain('null');
      }
    }
  });
});
