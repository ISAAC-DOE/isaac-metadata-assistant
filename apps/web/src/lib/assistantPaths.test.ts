/*
 * P36V.1 Unit B — the TypeScript half of the validation-path formatter contract.
 *
 * The SAME case table is replayed by the Python half in
 * `apps/api/tests/test_assistant_paths.py`. The two producers of the Assistant's
 * blocker copy live in different runtimes, so literal code sharing is impossible;
 * the shared table is what makes drift a test failure rather than a silent
 * divergence in what a hosted reader sees.
 *
 * The defect being pinned: `src/isaac_records/official.py:71` renders a root-level
 * JSON Schema violation as the literal locator `$` (an empty `absolute_path` deque
 * joins to `""`, and the `or "$"` fallback substitutes the literal). Both producers
 * interpolated that straight into a user-facing sentence. `official.py` is truth
 * core and is NOT edited: this is display-only.
 */

import { describe, it, expect } from 'vitest';
import { hasVerdictLanguage } from './assistant';
import {
  NO_BLOCKING_ISSUES,
  NO_PATH_TECHNICAL,
  RECORD_LEVEL_LABEL,
  ROOT_MARKER,
  SEGMENT_SEPARATOR,
  UNKNOWN_LOCATION_LABEL,
  VALIDATION_UNAVAILABLE_MESSAGE,
  VALIDATION_UNAVAILABLE_SUMMARY,
  blockingSummary,
  classifyValidationPath,
  classifyValidationPaths,
  count,
  isValidationUnavailable,
  joinCapped,
  technicalPaths,
} from './assistantPaths';
import SHARED from '../test/validation-path-cases.json';

interface SharedCase {
  name: string;
  paths: unknown[];
  locations: { kind: string; label: string; technical: string }[];
  technical: string[];
  summary: string;
}

interface UnavailableCase {
  name: string;
  errors: unknown[];
  unavailable: boolean;
}

const CASES = SHARED.cases as unknown as SharedCase[];
const UNAVAILABLE_CASES = SHARED.unavailable_cases as unknown as UnavailableCase[];

describe('shared cross-language case table (TypeScript side)', () => {
  it('the table is non-trivial — a stub table must not silently pass both suites', () => {
    expect(CASES.length).toBeGreaterThanOrEqual(15);
    // it must actually exercise the reported defect and the degenerate inputs
    const inputs = JSON.stringify(CASES.map((c) => c.paths));
    expect(inputs).toContain('"$"');
    expect(inputs).toContain('null');
    expect(inputs).toContain('"$$"'); // a $ surviving as a whole segment (M2)
    expect(UNAVAILABLE_CASES.length).toBeGreaterThanOrEqual(6);
    expect(UNAVAILABLE_CASES.some((c) => c.unavailable)).toBe(true);
    expect(UNAVAILABLE_CASES.some((c) => !c.unavailable)).toBe(true);
  });

  for (const c of CASES) {
    it(`case: ${c.name}`, () => {
      expect(classifyValidationPaths(c.paths)).toEqual(c.locations);
      expect(technicalPaths(c.paths)).toEqual(c.technical);
      expect(blockingSummary(c.paths)).toBe(c.summary);
    });
  }

  it('NO raw "$" reaches a primary summary, in ANY table case', () => {
    for (const c of CASES) {
      expect(blockingSummary(c.paths), c.name).not.toContain('$');
    }
  });

  it('a raw "$" IS preserved in the Technical Details payload where it was reported', () => {
    const rootCases = CASES.filter((c) => c.paths.some((p) => p === '$'));
    expect(rootCases.length).toBeGreaterThan(0);
    for (const c of rootCases) {
      expect(technicalPaths(c.paths), c.name).toContain('$');
    }
  });

  it('every summary passes the verdict-language guard', () => {
    for (const c of CASES) {
      expect(hasVerdictLanguage(blockingSummary(c.paths)), c.name).toBe(false);
    }
  });

  for (const c of UNAVAILABLE_CASES) {
    it(`crash sentinel: ${c.name}`, () => {
      expect(isValidationUnavailable(c.errors)).toBe(c.unavailable);
    });
  }
});

// ---------------------------------------------------------------------------
// IMPORTANT-2 — the no-raw-`$` invariant, enforced GENERALLY
//
// The module header asserts the raw `$` never reaches a primary label. Both suites
// used to assert that only over the shared table's inputs, so the property was
// enforced NOWHERE in general — and the reviewer falsified it with `$$`, `a.$.b`
// and `assets.$`, which the leading-marker strip left untouched. This corpus is
// GENERATED (the SAME construction `test_assistant_paths.py::_generated_locators`
// uses), so a change that re-admits a bare `$` into a label fails here even if
// nobody adds a table case for its exact shape.
// ---------------------------------------------------------------------------

const SEGMENT_POOL = ['a', '$', '', ' ', '0', '$$', '.', 'b_c'];

function generatedLocators(): string[] {
  const out: string[] = [];
  let level: string[][] = SEGMENT_POOL.map((s) => [s]);
  for (let depth = 0; depth < 3; depth += 1) {
    for (const parts of level) {
      const body = parts.join('.');
      out.push(body, `$${body}`, `$.${body}`);
    }
    level = level.flatMap((parts) => SEGMENT_POOL.map((s) => [...parts, s]));
  }
  return out;
}

const GENERATED = generatedLocators();

describe('IMPORTANT-2 · no bare "$" can reach a label or a summary, for ANY locator', () => {
  it('the generated corpus is large and really contains root markers', () => {
    expect(GENERATED.length).toBeGreaterThan(500);
    expect(GENERATED).toContain('$');
    expect(GENERATED).toContain('$$');
    expect(GENERATED.some((g) => g.endsWith('.$'))).toBe(true);
    expect(GENERATED.some((g) => g.includes('.$.'))).toBe(true);
    // the same size the Python suite generates — the two corpora are the same shape
    expect(GENERATED.length).toBe(1752);
  });

  it('holds over every generated locator', () => {
    for (const raw of GENERATED) {
      const loc = classifyValidationPath(raw);
      expect(loc.label, raw).not.toContain(ROOT_MARKER);
      // a label is always a real phrase — never blank, never invisible
      expect(loc.label.trim(), raw).not.toBe('');
      if (loc.kind === 'field') {
        expect(loc.label.split(SEGMENT_SEPARATOR), raw).not.toContain(ROOT_MARKER);
      } else {
        expect([RECORD_LEVEL_LABEL, UNKNOWN_LOCATION_LABEL], raw).toContain(loc.label);
      }
      expect(blockingSummary([raw]), raw).not.toContain(ROOT_MARKER);
    }
    // and over the whole corpus at once
    expect(blockingSummary(GENERATED)).not.toContain(ROOT_MARKER);
  });

  it('a "$" inside any segment is never described as a field location', () => {
    for (const raw of ['$$', 'a.$.b', 'assets.$', '$.$', '$.a.$', '$$$']) {
      const loc = classifyValidationPath(raw);
      expect(loc.kind, raw).toBe('unknown');
      expect(loc.label, raw).toBe(UNKNOWN_LOCATION_LABEL);
      // the exact string is still preserved for the disclosure
      expect(loc.technical, raw).toBe(raw);
    }
  });

  it('the documented injectivity BOUND is the one that actually holds (M2)', () => {
    // these collisions are REAL and are now documented rather than denied
    const sameRecord = new Set(
      ['$', '$.', '$..', '$ '].map((p) => classifyValidationPath(p).label),
    );
    expect([...sameRecord]).toEqual([RECORD_LEVEL_LABEL]);
    const separatorCollision = new Set(
      ['a → b', 'a.b', 'a..b'].map((p) => classifyValidationPath(p).label),
    );
    expect([...separatorCollision]).toEqual(['a → b']);
    // …and injectivity DOES hold for the locator shapes official.py can emit
    const emitted = [
      '$',
      'a',
      'a.b',
      'a.b.c',
      'assets.0.sha256',
      'sample.material.formula',
      'measurement.series.0.data_points.42.uncertainty.standard_error',
    ];
    const labels = emitted.map((p) => classifyValidationPath(p).label);
    expect(new Set(labels).size).toBe(labels.length);
  });
});

// ---------------------------------------------------------------------------
// IMPORTANT-1 — the validation-CRASH sentinel is not a validation issue
// ---------------------------------------------------------------------------

describe('IMPORTANT-1 · isValidationUnavailable', () => {
  it('is total — never throws, and never true for a non-list / empty list', () => {
    for (const raw of [undefined, null, 'x', 7, {}, [], [null], [7], [{ message: 7 }]]) {
      expect(() => isValidationUnavailable(raw)).not.toThrow();
      expect(isValidationUnavailable(raw), JSON.stringify(raw ?? null)).toBe(false);
    }
  });

  it('without it, the sentinel WOULD read as a confident validation issue', () => {
    const sentinel = [{ path: '$', message: VALIDATION_UNAVAILABLE_MESSAGE }];
    expect(blockingSummary(sentinel.map((e) => e.path))).toBe(
      '1 record-level validation issue may be blocking export.',
    );
    expect(isValidationUnavailable(sentinel)).toBe(true);
  });

  it('the unavailable summary claims no count, no location and no verdict', () => {
    expect(VALIDATION_UNAVAILABLE_SUMMARY).not.toContain('$');
    expect(VALIDATION_UNAVAILABLE_SUMMARY).not.toContain('validation issue');
    expect(VALIDATION_UNAVAILABLE_SUMMARY).not.toContain('blocking export');
    expect(VALIDATION_UNAVAILABLE_SUMMARY).toContain('could not be completed');
    expect(VALIDATION_UNAVAILABLE_SUMMARY).not.toMatch(/\d/);
    expect(hasVerdictLanguage(VALIDATION_UNAVAILABLE_SUMMARY)).toBe(false);
  });
});

describe('classifyValidationPath — per-locator classification', () => {
  it('the bare root marker is a RECORD-level location, not a field', () => {
    expect(classifyValidationPath('$')).toEqual({
      kind: 'record',
      label: RECORD_LEVEL_LABEL,
      technical: '$',
    });
    expect(RECORD_LEVEL_LABEL).not.toContain('$');
  });

  it('a nested locator keeps every segment verbatim (no invented field name)', () => {
    const loc = classifyValidationPath('sample.material.formula');
    expect(loc.kind).toBe('field');
    // each rendered segment appears verbatim in the source locator
    for (const seg of loc.label.split(' → ')) {
      expect('sample.material.formula'.split('.')).toContain(seg);
    }
  });

  it('an underscored segment is NOT rewritten, so two distinct locators cannot collapse', () => {
    expect(classifyValidationPath('a.standard_error').label).toBe('a → standard_error');
    expect(classifyValidationPath('a.standard error').label).toBe('a → standard error');
    expect(classifyValidationPath('a.standard_error').label).not.toBe(
      classifyValidationPath('a.standard error').label,
    );
  });

  it('an absent / non-string / empty locator claims no location and invents none', () => {
    for (const raw of [undefined, null, 7, {}, [], '', '   ']) {
      expect(classifyValidationPath(raw)).toEqual({
        kind: 'unknown',
        label: UNKNOWN_LOCATION_LABEL,
        technical: NO_PATH_TECHNICAL,
      });
    }
  });

  it('is total — it never throws for any input shape', () => {
    for (const raw of [NaN, Infinity, () => 0, Symbol('x'), new Map()]) {
      expect(() => classifyValidationPath(raw)).not.toThrow();
    }
  });

  it('preserves the reported locator byte-for-byte, including surrounding whitespace', () => {
    expect(classifyValidationPath('  sample.id  ').technical).toBe('  sample.id  ');
    expect(classifyValidationPath('  sample.id  ').label).toBe('sample → id');
  });
});

describe('blockingSummary — counts and caps', () => {
  it('an empty locator list is the honest empty answer, not a zero-count sentence', () => {
    expect(blockingSummary([])).toBe(NO_BLOCKING_ISSUES);
  });

  it('the stated count always matches the locator count, even past the ≤3 display cap', () => {
    const many = ['a', 'b', 'c', 'd', 'e', 'f', 'g'];
    const text = blockingSummary(many);
    expect(text.startsWith('7 validation issues')).toBe(true);
    expect(text).toContain('…and 4 more');
    expect(technicalPaths(many)).toHaveLength(7);
  });

  it('all-root uses the record-level wording; any non-root switches to the located wording', () => {
    expect(blockingSummary(['$', '$', '$'])).toBe(
      '3 record-level validation issues may be blocking export.',
    );
    expect(blockingSummary(['$', '$', 'assets'])).toBe(
      '3 validation issues may be blocking export: the record itself, the record itself, assets.',
    );
  });

  it('never states a verdict and never echoes an ok/valid conclusion', () => {
    const text = blockingSummary(['$', 'assets.0.sha256']);
    expect(hasVerdictLanguage(text)).toBe(false);
    expect(text).not.toMatch(/\bvalid\b/i);
    expect(text).not.toMatch(/\binvalid\b/i);
    // hedged, so it never reads as a determination
    expect(text).toContain('may be blocking export');
  });
});

describe('shared text helpers (one implementation per language)', () => {
  it('count pluralizes deterministically, with no "(s)" placeholder', () => {
    expect(count(1, 'validation issue')).toBe('1 validation issue');
    expect(count(2, 'validation issue')).toBe('2 validation issues');
    expect(count(1, 'evidence entry', 'evidence entries')).toBe('1 evidence entry');
    expect(count(3, 'evidence entry', 'evidence entries')).toBe('3 evidence entries');
    expect(count(0, 'field')).toBe('0 fields');
  });

  it('joinCapped shows ≤3 and reports the remainder', () => {
    expect(joinCapped([])).toBe('');
    expect(joinCapped(['a'])).toBe('a');
    expect(joinCapped(['a', 'b', 'c'])).toBe('a, b, c');
    expect(joinCapped(['a', 'b', 'c', 'd'])).toBe('a, b, c, …and 1 more');
  });
});
