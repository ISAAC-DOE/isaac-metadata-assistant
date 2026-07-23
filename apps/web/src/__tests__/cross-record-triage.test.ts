/*
 * P30.3 — cross-record deterministic triage (the consumer for the P30.1 provider).
 *
 * TEST-FIRST (orchestrator-authored, RED until `crossRecordTriage` exists). A pure
 * deterministic function over the SAFE runtime-record projection (from
 * GET /api/runtime/records). It answers cross-record triage intents ("which records
 * need attention / are blocked / have conflicts / are exportable now") with SAFE
 * summaries + a navigate handoff — it never reads current-record scientific truth,
 * never presents an inferred candidate as fact, never uses Project Memory, and
 * never renders a verdict. Opening a match hands off to a direct Workspace load
 * (the summary is a lead, not the record truth).
 */

import { describe, expect, it } from 'vitest';
import { crossRecordTriage, type RuntimeRecord } from '../lib/crossRecordTriage';

const RECS: RuntimeRecord[] = [
  { experiment_id: 'A', title: 'Alpha', status: 'needs_attention', pending_count: 5, exported: false, record_id: null,
    workflow: { current_step: 'complete_metadata', blocked: true, reopened: false },
    evidence_counts: { supported: 3, inferred_candidate: 1, insufficient_evidence: 0, conflicting_evidence: 0, unknown: 2 },
    artifact_state: 'none', record_rev: 4, updated_utc: '2026-07-01T00:00:00Z', navigate_to: '/record/A' },
  { experiment_id: 'B', title: 'Beta', status: 'ready_to_export', pending_count: 0, exported: false, record_id: null,
    workflow: { current_step: 'export', blocked: false, reopened: false },
    evidence_counts: { supported: 9, inferred_candidate: 0, insufficient_evidence: 0, conflicting_evidence: 0, unknown: 0 },
    artifact_state: 'none', record_rev: 7, updated_utc: '2026-07-02T00:00:00Z', navigate_to: '/record/B' },
  { experiment_id: 'C', title: 'Gamma', status: 'in_review', pending_count: 0, exported: false, record_id: null,
    workflow: { current_step: 'review_export_readiness', blocked: false, reopened: true },
    evidence_counts: { supported: 5, inferred_candidate: 0, insufficient_evidence: 1, conflicting_evidence: 2, unknown: 0 },
    artifact_state: 'none', record_rev: 11, updated_utc: '2026-07-03T00:00:00Z', navigate_to: '/record/C' },
  { experiment_id: 'D', title: 'Delta', status: 'done', pending_count: 0, exported: true, record_id: 'D',
    workflow: { current_step: null, blocked: false, reopened: false },
    evidence_counts: { supported: 9, inferred_candidate: 0, insufficient_evidence: 0, conflicting_evidence: 0, unknown: 0 },
    artifact_state: 'stale', record_rev: 13, updated_utc: '2026-07-04T00:00:00Z', navigate_to: '/record/D' },
];

const ids = (r: { matches: { experiment_id: string }[] }) => r.matches.map((m) => m.experiment_id).sort();

describe('P30.3 crossRecordTriage', () => {
  it('needs_attention → the needs-attention records only', () => {
    expect(ids(crossRecordTriage(RECS, 'needs_attention'))).toEqual(['A']);
  });

  it('blocked → records with a blocked workflow step', () => {
    expect(ids(crossRecordTriage(RECS, 'blocked'))).toEqual(['A']);
  });

  it('has_conflict → records with >=1 conflicting_evidence (never picks a winner)', () => {
    const r = crossRecordTriage(RECS, 'has_conflict');
    expect(ids(r)).toEqual(['C']);
    // the summary must NOT assert a resolved value — it just flags the conflict count
    expect(JSON.stringify(r)).not.toMatch(/winner|resolved|correct value/i);
  });

  it('exportable → ready_to_export records', () => {
    expect(ids(crossRecordTriage(RECS, 'exportable'))).toEqual(['B']);
  });

  it('each match carries ONLY safe summary fields + a navigate handoff', () => {
    const r = crossRecordTriage(RECS, 'needs_attention');
    for (const m of r.matches) {
      expect(Object.keys(m).sort()).toEqual(['experiment_id', 'navigate_to', 'reason', 'title']);
      expect(m.navigate_to).toBe(`/record/${m.experiment_id}`); // handoff to direct Workspace load
    }
  });

  it('never renders a verdict and never surfaces an inferred value as a fact', () => {
    for (const intent of ['needs_attention', 'blocked', 'has_conflict', 'exportable']) {
      const r = crossRecordTriage(RECS, intent);
      expect(/\b(PASS|FAIL)\b/.test(r.text)).toBe(false);
      // record A has an inferred_candidate; triage may COUNT it but must not present a value as confirmed
      expect(r.text.toLowerCase()).not.toContain('confirmed value');
    }
  });

  it('an unknown intent returns an honest empty result, never a fabricated match', () => {
    const r = crossRecordTriage(RECS, 'bogus_intent');
    expect(r.matches).toEqual([]);
    expect(r.text).toBeTruthy();
  });

  it('is pure and deterministic (same input → identical output; input unmutated)', () => {
    const before = JSON.stringify(RECS);
    const a = crossRecordTriage(RECS, 'has_conflict');
    const b = crossRecordTriage(RECS, 'has_conflict');
    expect(a).toEqual(b);
    expect(JSON.stringify(RECS)).toBe(before);
  });
});
