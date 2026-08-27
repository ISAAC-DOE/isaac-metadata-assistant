import { describe, it, expect } from 'vitest';
import { pendingSummary } from '../lib/adapt';
import type { ApiPendingItem } from '../lib/types';

/*
 * P33 S4 (D9/C2) — presentation-only summary formatter for the missing-fields
 * banner. It NEVER rewrites/guesses the backend question's meaning: it renders a
 * concise label from the structured `kind`, surfaces the technical locator once,
 * demotes raw identifiers out of the primary label, and falls back to the full
 * original question when no safe structured label exists. It is pure — it does
 * not mutate the pending item, and the underlying question is unchanged.
 */

const asset = {
  id: 'ssrl-archive://BL15-2/2099_run_000/raw/',
  kind: 'asset',
  question: 'What is the sha256 of ssrl-archive://BL15-2/2099_run_000/raw/?',
  about: 'ssrl-archive://BL15-2/2099_run_000/raw/',
} satisfies ApiPendingItem;

const descriptor = {
  id: 'd1',
  kind: 'descriptor',
  question:
    'Provide at least one descriptor (e.g. XANES inflection-point energy + uncertainty) — an evidence record requires descriptors.',
  about: 'required_for_evidence_record',
} satisfies ApiPendingItem;

describe('pendingSummary — P33 S4 (D9/C2)', () => {
  it('asset: concise structured label (not the raw question echo) + locator surfaced once', () => {
    const s = pendingSummary(asset);
    expect(s.label).not.toBe(asset.question); // concise, not a verbatim echo
    expect(s.label.length).toBeLessThan(asset.question.length);
    expect(s.locator).toBe(asset.about); // the technical locator, once
  });

  it('descriptor: the raw identifier is demoted — never the primary label', () => {
    const s = pendingSummary(descriptor);
    expect(s.label).not.toBe('required_for_evidence_record');
    expect(s.label.toLowerCase()).not.toContain('required_for_evidence_record');
  });

  it('unknown kind: falls back safely to the full original question', () => {
    const unknown = { id: 'u1', kind: 'mystery', question: 'Some other question?', about: null } as unknown as ApiPendingItem;
    expect(pendingSummary(unknown).label).toBe('Some other question?');
  });

  it('is pure — does not mutate the pending item', () => {
    const copy = { ...asset };
    pendingSummary(asset);
    expect(asset).toEqual(copy);
  });
});
