import { describe, it, expect } from 'vitest';
import {
  RELATION_DISPLAY_LABELS,
  conceptDisplayTitle,
  isCodeOnlyGroup,
  isCodeToken,
  relationDisplayLabel,
  relationDisplayLabels,
  splitTrailingGroup,
} from '../lib/displayLabels';
import { isTechnical, titleCase } from '../lib/labels';

/*
 * P36V PR2 slice A — the display-only title derivation for project-memory
 * concept labels.
 *
 * The contract this file pins:
 *   · every one of the 19 REAL concept labels shipped in the committed snapshot
 *     has a checked before → after title (the table below is the record),
 *   · a trailing group is dropped ONLY when it is code end-to-end, and KEPT the
 *     moment it carries a prose word — deleting meaning is worse than leaving an
 *     identifier on screen,
 *   · the derivation is pure and never mutates its input,
 *   · adversarial shapes (empty, group-only, nested, unbalanced, mismatched,
 *     wholly technical) degrade to something honest, never to an empty title.
 */

/**
 * The 19 labels served by GET /api/memory/concepts from the committed snapshot
 * (apps/api/isaac_api/data/memory-snapshot.json → `concepts[].label`), verbatim,
 * with the title each one must render. Every row was read for lost meaning: no
 * row drops a word that is not an identifier.
 */
const REAL_LABELS: ReadonlyArray<readonly [raw: string, title: string]> = [
  // ── trailing group DROPPED (code end-to-end) ─────────────────────────────
  [
    'AI scientific consistency review (review.py NoOpReviewer)',
    'AI Scientific Consistency Review',
  ],
  ['Draft envelope format {value,status,evidence[]}', 'Draft Envelope Format'],
  ['Evidence sidecar (records/<ULID>.evidence.json)', 'Evidence Sidecar'],
  ['Golden must-validate example records (tests/fixtures/official/)', 'Golden Must-Validate Example Records'],
  // ── no trailing group at all ─────────────────────────────────────────────
  ['Committed synthetic intake fixtures', 'Committed Synthetic Intake Fixtures'],
  [
    'Deterministic vs LLM-assisted extraction split',
    'Deterministic vs LLM-Assisted Extraction Split',
  ],
  [
    'Extracted-value to draft-field / official JSON-path mapping',
    'Extracted-Value to Draft-Field / Official JSON-Path Mapping',
  ],
  // ── trailing group KEPT (prose, or an identifier mixed with prose) ────────
  ['Accepted artifact types (XANES intake)', 'Accepted Artifact Types (XANES intake)'],
  [
    'Export transform (export.py, deterministic, doubly gated)',
    'Export Transform (export.py, deterministic, doubly gated)',
  ],
  [
    'Extraction interface seam (src/isaac_records/extract, Phase 2 stubs)',
    'Extraction Interface Seam (src/isaac_records/extract, Phase 2 stubs)',
  ],
  ['Graphify (optional derived knowledge graph)', 'Graphify (optional derived knowledge graph)'],
  ['Implicit inferences (absorbing element, edge)', 'Implicit Inferences (absorbing element, edge)'],
  ['Memory/query plane (Graphify-central)', 'Memory/query Plane (Graphify-central)'],
  ['Official ISAAC schema v1.05 (authority)', 'Official ISAAC Schema v1.05 (authority)'],
  [
    'Per-artifact evidence capture (source_type + locator)',
    'Per-Artifact Evidence Capture (source_type + locator)',
  ],
  ['Truth plane (deterministic, Graphify-free)', 'Truth Plane (deterministic, Graphify-free)'],
  [
    'Two-layer architecture (draft to export to record + sidecar)',
    'Two-Layer Architecture (draft to export to record + sidecar)',
  ],
  ['Validation stack (5 staged authorities)', 'Validation Stack (5 staged authorities)'],
  [
    'examples/ artifact directory (gitignored real artifacts)',
    'examples/ Artifact Directory (gitignored real artifacts)',
  ],
];

describe('P36V S-A · conceptDisplayTitle — the 19 real concept labels', () => {
  it('covers every concept the committed snapshot serves', () => {
    expect(REAL_LABELS).toHaveLength(19);
    expect(new Set(REAL_LABELS.map(([raw]) => raw)).size).toBe(19);
  });

  it.each(REAL_LABELS)('%s → %s', (raw, title) => {
    expect(conceptDisplayTitle(raw)).toBe(title);
  });

  it('never returns an empty title for a real label, and never mutates its input', () => {
    for (const [raw] of REAL_LABELS) {
      const frozen = `${raw}`;
      expect(conceptDisplayTitle(raw).length).toBeGreaterThan(0);
      expect(raw).toBe(frozen); // pure: the caller's string is untouched
    }
  });

  it('is idempotent — re-deriving an already-derived title changes nothing further', () => {
    for (const [, title] of REAL_LABELS) {
      expect(conceptDisplayTitle(title)).toBe(title);
    }
  });

  it('drops a trailing group for exactly 4 of the 19, and keeps every prose-bearing one', () => {
    const dropped = REAL_LABELS.filter(([raw, title]) => !title.endsWith(')') && raw.endsWith(')'))
      .concat(REAL_LABELS.filter(([raw]) => raw.endsWith('}')))
      .map(([raw]) => raw);
    expect(dropped).toEqual([
      'AI scientific consistency review (review.py NoOpReviewer)',
      'Evidence sidecar (records/<ULID>.evidence.json)',
      'Golden must-validate example records (tests/fixtures/official/)',
      'Draft envelope format {value,status,evidence[]}',
    ]);

    // The prose-bearing groups are all still on screen, word for word.
    for (const fragment of [
      '(XANES intake)',
      '(export.py, deterministic, doubly gated)',
      '(src/isaac_records/extract, Phase 2 stubs)',
      '(optional derived knowledge graph)',
      '(absorbing element, edge)',
      '(Graphify-central)',
      '(authority)',
      '(source_type + locator)',
      '(deterministic, Graphify-free)',
      '(draft to export to record + sidecar)',
      '(5 staged authorities)',
      '(gitignored real artifacts)',
    ]) {
      const row = REAL_LABELS.find(([raw]) => raw.endsWith(fragment));
      expect(row, `no real label ends with ${fragment}`).toBeDefined();
      expect(conceptDisplayTitle(row![0])).toContain(fragment);
    }
  });

  it('preserves every technical token of the head verbatim — no path, version or acronym is re-cased', () => {
    for (const token of ['examples/', 'v1.05', 'ISAAC', 'AI', 'LLM', 'JSON', 'Memory/query']) {
      const row = REAL_LABELS.find(([raw]) => raw.includes(token));
      expect(row, `no real label contains ${token}`).toBeDefined();
      expect(conceptDisplayTitle(row![0])).toContain(token);
    }
  });
});

describe('P36V S-A · conceptDisplayTitle — adversarial inputs', () => {
  it('empty and whitespace-only input yield an empty string, never "undefined"', () => {
    expect(conceptDisplayTitle('')).toBe('');
    expect(conceptDisplayTitle('   ')).toBe('');
  });

  it('a label that is NOTHING but a group keeps the group — there is no head to fall back to', () => {
    expect(conceptDisplayTitle('(review.py)')).toBe('(review.py)');
    expect(conceptDisplayTitle('{value,status}')).toBe('{value,status}');
    expect(splitTrailingGroup('(review.py)')).toBeNull();
  });

  it('handles nested groups as one unit — prose anywhere inside protects the whole group', () => {
    expect(splitTrailingGroup('Foo (bar (baz.py))')).toEqual({
      head: 'Foo',
      open: '(',
      inner: 'bar (baz.py)',
      close: ')',
    });
    expect(conceptDisplayTitle('Foo (bar (baz.py))')).toBe('Foo (bar (baz.py))');
    // …and a nested group that is code all the way down is dropped as one unit.
    expect(conceptDisplayTitle('Foo bar (baz.py (qux.py))')).toBe('Foo Bar');
  });

  it('an unbalanced or mismatched delimiter is not a group — the label is title-cased whole', () => {
    expect(splitTrailingGroup('Foo (bar')).toBeNull();
    expect(conceptDisplayTitle('Foo (bar')).toBe('Foo (bar');
    expect(splitTrailingGroup('Truth plane)')).toBeNull();
    expect(conceptDisplayTitle('Truth plane)')).toBe('Truth Plane)');
    expect(splitTrailingGroup('Foo (bar]')).toBeNull();
    expect(conceptDisplayTitle('Foo (bar]')).toBe('Foo (bar]');
  });

  it('a wholly technical label passes through verbatim (titleCase already guarantees this)', () => {
    for (const raw of ['src/isaac_records/export.py', 'sha256', 'v1.05', 'QC_NONVALID_WITHOUT_EVIDENCE']) {
      expect(isTechnical(raw)).toBe(true);
      expect(conceptDisplayTitle(raw)).toBe(raw);
      expect(conceptDisplayTitle(raw)).toBe(titleCase(raw));
    }
  });

  it('an empty group carries no content, so it is dropped', () => {
    expect(conceptDisplayTitle('Truth plane ()')).toBe('Truth Plane');
    expect(isCodeOnlyGroup('')).toBe(true);
    expect(isCodeOnlyGroup('   ')).toBe(true);
  });
});

describe('P36V S-A · isCodeToken — what counts as safe to hide', () => {
  it('treats structural identifiers as code', () => {
    for (const token of [
      'review.py',
      'records/<ULID>.evidence.json',
      'tests/fixtures/official/',
      'src/isaac_records/extract,',
      'source_type',
      'v1.05',
      'XANES',
      'AI',
      'NoOpReviewer',
      'value,status,evidence[]',
      '<ULID>',
    ]) {
      expect(isCodeToken(token), token).toBe(true);
    }
  });

  it('treats prose as prose — including curated vocabulary words isTechnical() protects for CASING', () => {
    for (const token of [
      'intake',
      'deterministic',
      'deterministic,',
      'doubly',
      'gated',
      'authority',
      'locator',
      'optional',
      'Phase',
      '2',
      '5',
      'gitignored',
      'Graphify-central',
    ]) {
      expect(isCodeToken(token), token).toBe(false);
    }
    // `Graphify` / `spreadsheet` / `derivation` are in labels.ts TECHNICAL so
    // they are never re-cased — but they are ordinary words on screen, and
    // hiding one would delete meaning. isCodeToken must disagree with
    // isTechnical here, and that disagreement is the point.
    for (const token of ['Graphify', 'spreadsheet', 'derivation']) {
      expect(isTechnical(token), token).toBe(true);
      expect(isCodeToken(token), token).toBe(false);
    }
  });

  it('a bare connector abstains: it neither authorises nor blocks a drop', () => {
    expect(isCodeOnlyGroup('source_type + other_id')).toBe(true);
    expect(isCodeOnlyGroup('source_type + locator')).toBe(false);
    expect(isCodeOnlyGroup('+')).toBe(false); // connectors alone are not code
    expect(isCodeOnlyGroup('· —')).toBe(false);
  });
});

/* ---------------------------------------------------------------------------
 * Relationship-type display labels (P36V PR2 slice B).
 *
 * The contract, and why it is drawn exactly here:
 *
 *  · Graph relation values are a CLOSED set. Measured against the committed
 *    snapshot (`apps/api/isaac_api/data/memory-snapshot.json`, every
 *    `file_detail[*].related.files[*].relation`) there are exactly five, with
 *    these occurrence counts: references 389 · imports 382 · calls 160 ·
 *    imports_from 69 · shares_data_with 2. Because the set is closed and
 *    enumerable, each member gets an explicit, hand-checked label.
 *  · Cluster / community names are NOT a closed vocabulary — 104 distinct values
 *    in the same snapshot, arbitrary data drawn from a representative node. A
 *    mechanical snake_case → Title Case rule over them fabricates readings
 *    ("She Work Function Ev" for `SHE_work_function_eV`, "Test Export.py" for
 *    `test_export.py`, "Record Id" for `record_id`). They are therefore never
 *    renamed, and the tests below prove the map REFUSES to touch them.
 *  · Anything outside the five passes through VERBATIM. Not title-cased, not
 *    de-underscored, not abbreviated. An unmeasured vocabulary is not ours to
 *    rename, and the fallthrough is the whole safety property.
 * ------------------------------------------------------------------------- */

/** The five values, and the label each must render. This table IS the record. */
const REAL_RELATIONS: ReadonlyArray<readonly [raw: string, label: string]> = [
  ['references', 'References'],
  ['imports', 'Imports'],
  ['calls', 'Calls'],
  ['imports_from', 'Imports From'],
  ['shares_data_with', 'Shares Data With'],
];

describe('relationDisplayLabel — the closed five-value map', () => {
  it('maps every relation value present in the served projection', () => {
    for (const [raw, label] of REAL_RELATIONS) {
      expect(relationDisplayLabel(raw), raw).toBe(label);
    }
  });

  it('the exported map is EXACTLY those five keys — no invented sixth', () => {
    expect(Object.keys(RELATION_DISPLAY_LABELS).sort()).toEqual(
      REAL_RELATIONS.map(([raw]) => raw).sort(),
    );
    expect(Object.entries(RELATION_DISPLAY_LABELS).sort()).toEqual(
      [...REAL_RELATIONS].map(([raw, label]) => [raw, label]).sort(),
    );
  });

  it('passes an UNKNOWN value through verbatim — never guessed, never re-cased', () => {
    // `relates_to` is real: it is the concept↔concept relation the Concepts tab
    // renders. The served snapshot never populates it, so its vocabulary was
    // never measured — and an unmeasured value is displayed as written.
    for (const token of [
      'relates_to',
      'anchored_in',
      'depends_on',
      'IMPORTS',
      'Imports',
      'imports ',
      'imports_from_module',
      'shares-data-with',
      'référence',
      '',
      'a',
      '_',
      'x_y_z',
    ]) {
      expect(relationDisplayLabel(token), token).toBe(token);
    }
  });

  it('never applies a snake_case → Title Case rule to a value it does not know', () => {
    // These are the exact shapes a mechanical rule destroys. Every one must come
    // back untouched: the cluster-name vocabulary is not the relation vocabulary,
    // and this map must not be usable as a general humaniser.
    for (const token of [
      'SHE_work_function_eV',
      'test_export.py',
      'record_id',
      'cell_type',
      'slab_model',
      'transition_state',
      'Per-artifact evidence capture (source_type + locator)',
    ]) {
      expect(relationDisplayLabel(token), token).toBe(token);
    }
    // …and specifically NOT the fabrications.
    expect(relationDisplayLabel('SHE_work_function_eV')).not.toBe('She Work Function Ev');
    expect(relationDisplayLabel('cell_type')).not.toBe('Cell Type');
  });

  it('is prototype-safe: an inherited key is not a relation label', () => {
    // A bare object lookup would resolve `constructor` / `toString` up the
    // prototype chain and return a function, which React would then try to
    // render. The map must treat them as unknown values like any other.
    for (const token of ['constructor', 'toString', '__proto__', 'hasOwnProperty']) {
      expect(relationDisplayLabel(token), token).toBe(token);
    }
  });

  it('does not mutate its input, the list it is given, or the map itself', () => {
    const relations = ['imports', 'relates_to', 'calls'];
    const before = JSON.stringify(relations);
    const mapBefore = JSON.stringify(RELATION_DISPLAY_LABELS);

    const out = relationDisplayLabels(relations);

    expect(out).toEqual(['Imports', 'relates_to', 'Calls']);
    expect(JSON.stringify(relations)).toBe(before); // the caller's array is intact
    expect(out).not.toBe(relations); // a new array, not an in-place rewrite
    expect(JSON.stringify(RELATION_DISPLAY_LABELS)).toBe(mapBefore);
  });

  it('the label map is frozen, so a caller CANNOT rewrite the shared vocabulary', () => {
    // `Readonly<Record<…>>` is erased at runtime: it stops a TypeScript caller
    // and nothing else, which is why the JSON comparison above could never have
    // failed. `Object.freeze` makes the invariant real.
    expect(Object.isFrozen(RELATION_DISPLAY_LABELS)).toBe(true);
    const target = RELATION_DISPLAY_LABELS as Record<string, string>;
    expect(() => {
      target.calls = 'Invokes';
    }).toThrow(TypeError); // strict mode — every ES module is strict
    expect(() => {
      target.brand_new = 'Invented';
    }).toThrow(TypeError);
    expect(relationDisplayLabel('calls')).toBe('Calls');
    expect(relationDisplayLabel('brand_new')).toBe('brand_new'); // still verbatim
  });

  it('relationDisplayLabels preserves order and length, duplicates included', () => {
    expect(relationDisplayLabels([])).toEqual([]);
    expect(relationDisplayLabels(['calls', 'calls', 'zzz'])).toEqual(['Calls', 'Calls', 'zzz']);
  });

  it('is deterministic and idempotent on its own output for unmapped values', () => {
    for (const token of ['relates_to', 'zzz_unknown']) {
      expect(relationDisplayLabel(relationDisplayLabel(token))).toBe(token);
    }
    // A mapped value's LABEL is not itself a key, so a double application is a
    // no-op rather than a second transformation.
    expect(relationDisplayLabel(relationDisplayLabel('imports'))).toBe('Imports');
  });
});
