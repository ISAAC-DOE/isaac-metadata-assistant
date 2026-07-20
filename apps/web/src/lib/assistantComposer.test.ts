import { describe, it, expect } from 'vitest';
import { compose, count, REVIEW_CATALOG } from './assistantComposer';
import { SOURCE_LABELS } from './assistant';
import {
  experimentDetail,
  draftResponse,
  pendingResponse,
  validateDryRun,
  auditNotExported,
  warningsDryRun,
  evidenceResponse,
  graphStatusUnavailable,
} from '../test/apiFixtures';
import type { GroundingState, RecordBundle } from './types';

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

describe('compose — only the review context is implemented in P25.1', () => {
  it('throws for any non-review context', () => {
    const notReview = { context: 'export' } as unknown as GroundingState;
    expect(() => compose(notReview)).toThrow('compose: context not implemented in P25.1');
  });
});
