import { describe, it, expect } from 'vitest';
import { titleCase, isTechnical, LABELS } from '../lib/labels';

describe('titleCase — Title Case labels', () => {
  it('title-cases plain label phrases', () => {
    expect(titleCase('my experiments')).toBe('My Experiments');
    expect(titleCase('needs attention')).toBe('Needs Attention');
    expect(titleCase('load materials')).toBe('Load Materials');
  });

  it('keeps minor words lowercase (except when leading)', () => {
    expect(titleCase('ready to export')).toBe('Ready to Export');
    expect(titleCase('evidence & file preview')).toBe('Evidence & File Preview');
  });

  it('title-cases hyphenated segments', () => {
    expect(titleCase('one-question card')).toBe('One-Question Card');
  });
});

describe('titleCase — technical identifiers pass through verbatim', () => {
  it('never re-cases known technical tokens', () => {
    expect(titleCase('sha256')).toBe('sha256');
    expect(titleCase('NO_LINKS')).toBe('NO_LINKS');
    expect(titleCase('Cu K-edge')).toBe('Cu K-edge');
    expect(titleCase('v1.05')).toBe('v1.05');
    expect(titleCase('ISAAC')).toBe('ISAAC');
    expect(titleCase('XANES')).toBe('XANES');
    expect(titleCase('Graphify')).toBe('Graphify');
  });

  it('never re-cases structural identifiers (paths / codes)', () => {
    expect(titleCase('system.facility.beamline')).toBe('system.facility.beamline');
    expect(titleCase('user_confirmation')).toBe('user_confirmation');
    expect(titleCase('records/01JQZ0.json')).toBe('records/01JQZ0.json');
  });
});

describe('isTechnical', () => {
  it('recognizes technical identifiers', () => {
    for (const t of ['sha256', 'NO_LINKS', 'Cu K-edge', 'v1.05', 'system.facility.beamline']) {
      expect(isTechnical(t)).toBe(true);
    }
  });

  it('does not flag ordinary words', () => {
    for (const w of ['experiments', 'beamline', 'review', 'confirm']) {
      expect(isTechnical(w)).toBe(false);
    }
  });
});

describe('LABELS vocabulary', () => {
  it('exposes Title Case UI labels', () => {
    expect(LABELS.screenReview).toBe('Review Record');
    expect(LABELS.chipConfirmed).toBe('Confirmed by You');
    expect(LABELS.chipNeedsYou).toBe('Needs You');
    expect(LABELS.groupReady).toBe('Ready to Export');
  });

  it('keeps the brand and technical version strings verbatim', () => {
    expect(LABELS.brand).toBe('ISAAC');
    expect(LABELS.version).toContain('isaac v0.1.0');
  });
});
