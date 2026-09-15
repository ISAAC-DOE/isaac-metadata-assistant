import { describe, it, expect } from 'vitest';
import { titleCase, isTechnical, LABELS, formatInstant } from '../lib/labels';

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
    // The environment half is DERIVED (see `lib/runtimeContext.ts`); under the
    // default test env (no VITE_API_BASE) that derivation is the local build.
    expect(LABELS.version).toBe('isaac v0.1.0 · local dev');
  });
});

describe('formatInstant — one date vocabulary, and a fixed one', () => {
  /*
   * WHY THIS EXISTS. `StatisticsPage` defined its own `formatInstant` returning
   * `when.toLocaleString()`, so the page clock read "9/14/2026, 8:07:08 PM"
   * (measured in Chromium) while an experiment card two screens away read
   * "Sep 15, 2026". `SHORT_MONTHS`'s own comment in `lib/labels.ts` already
   * forbids locale formatting for display -- "never `Date`/`Intl` locale
   * formatting … deterministic across environments" -- and a client-side clock
   * is the same kind of value as that badge.
   */
  it('renders the app date style plus a wall clock', () => {
    // Constructed from local parts, so the expectation is timezone-independent:
    // the function reads local getters and the fixture is built from local args.
    const when = new Date(2026, 8, 14, 20, 7, 8);
    expect(formatInstant(when)).toBe('Sep 14, 2026, 8:07:08 PM');
  });

  it('pads minutes and seconds, and renders midnight and noon as 12', () => {
    expect(formatInstant(new Date(2026, 0, 1, 0, 5, 9))).toBe('Jan 1, 2026, 12:05:09 AM');
    expect(formatInstant(new Date(2026, 11, 31, 12, 0, 0))).toBe('Dec 31, 2026, 12:00:00 PM');
    // 13:00 is 1 PM, not 13 PM — the modulo is easy to write backwards.
    expect(formatInstant(new Date(2026, 5, 30, 13, 45, 0))).toBe('Jun 30, 2026, 1:45:00 PM');
  });

  it('MUTATION-GUARDED: uses the shared month names, not the host locale', () => {
    /*
     * MUTATION: reverting the body to `when.toLocaleString()` makes this RED.
     * The assertion is the PROPERTY rather than one string: a month name from
     * `SHORT_MONTHS` must appear, and the numeric `M/D/YYYY` shape must not,
     * because that shape is what a locale rendering produces here and is what
     * the page used to show.
     */
    const rendered = formatInstant(new Date(2026, 8, 14, 20, 7, 8));
    expect(rendered).toMatch(/^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) /);
    expect(rendered, 'a numeric locale date shape leaked back in').not.toMatch(/^\d+\/\d+\//);
  });
});
