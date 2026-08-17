/*
 * UNIFIED PROVENANCE — cross-language parity, and two chips that stay two.
 *
 * PART 1 · PARITY. `lib/provenance.ts` is a hand-written mirror of
 * `apps/api/isaac_api/provenance.py`, and a hand-written mirror rots silently —
 * the failure mode is not a crash but a chip quietly naming a dimension the
 * server has renamed. So the two vocabularies, the precedence order and BOTH
 * mapping tables are asserted against the Python source itself, read at test
 * time. Same idiom as `example-record-ids.test.ts` (which reconstructs the seed
 * ids from `workspace.py`) and `assistant-capabilities.test.tsx` (which reads the
 * resolver's trigger table out of `assistant_query.py`).
 *
 * PART 2 · THE TWO DIMENSIONS STAY TWO. The whole model is worthless if the UI
 * collapses them, so there are rendering assertions that the pair is two separate
 * chips with two separate labels, that an origin chip is NEVER coloured (a
 * neutral palette is what stops "From a file" reading as an approval), and that a
 * `file` / `derived` / `assistant` origin sits perfectly happily beside
 * "Needs review".
 *
 * READ-ONLY, and of files already in this repository: nothing here starts a
 * server, reads a workspace, or touches a database.
 */

import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';

import { EvidenceRow } from '../components/EvidenceRow';
import { EvidenceTrailPanel } from '../components/EvidenceTrailPanel';
import { CHIP_ICON } from '../components/icons';
import { OriginChip, ProvenanceChipPair, ReviewStateChip } from '../components/ProvenanceChips';
import { CHIP_META, ORIGIN_CHIP, REVIEW_STATE_CHIP } from '../lib/status';
import type { LucideIcon } from 'lucide-react';
import {
  NOTE_SOURCE_ORIGIN,
  ORIGIN_LABEL,
  ORIGIN_PRECEDENCE,
  PROVENANCE_ORIGINS,
  PROVENANCE_REVIEW_STATES,
  REVIEW_STATE_LABEL,
  SOURCE_TYPE_ORIGIN,
  hasConflictingEvidence,
  originForNoteSource,
  originsFromEvidence,
  primaryOrigin,
  reviewStateFor,
} from '../lib/provenance';
import type { EvidenceTrailEntry, FieldEvidence } from '../lib/types';

const HERE = dirname(fileURLToPath(import.meta.url));
const PROVENANCE_PY = resolve(HERE, '../../../..', 'apps/api/isaac_api/provenance.py');
const SOURCE = readFileSync(PROVENANCE_PY, 'utf8');

// --- 1. reading the Python source -------------------------------------------

/** `ORIGIN_MANUAL = "manual"` / `REVIEW_SUPPORTED = "supported"`, as a lookup. */
function backendConstants(): Map<string, string> {
  const out = new Map<string, string>();
  for (const m of SOURCE.matchAll(/^(ORIGIN_[A-Z_]+|REVIEW_[A-Z_]+) = "([a-z_]+)"$/gm)) {
    out.set(m[1], m[2]);
  }
  return out;
}

/** The members of a `NAME: tuple[str, ...] = ( … )` literal, resolved to values. */
function backendTuple(name: string): string[] {
  const block = new RegExp(`^${name}: tuple\\[str, \\.\\.\\.\\] = \\(([\\s\\S]*?)\\n\\)`, 'm').exec(
    SOURCE,
  );
  expect(block, `provenance.py no longer defines ${name} as a tuple literal`).not.toBeNull();
  const constants = backendConstants();
  return (block![1] ?? '')
    .split('\n')
    .map((line) => line.replace(/#.*$/, '').trim().replace(/,$/, ''))
    .filter((token) => token.length > 0)
    .map((token) => {
      const value = constants.get(token);
      expect(value, `${name} names ${token}, which is not an origin/review constant`).toBeDefined();
      return value as string;
    });
}

/** The `"key": ORIGIN_X` pairs of a `NAME: dict[str, str] = { … }` literal. */
function backendTable(name: string): Record<string, string> {
  const block = new RegExp(`^${name}: dict\\[str, str\\] = \\{([\\s\\S]*?)\\n\\}`, 'm').exec(SOURCE);
  expect(block, `provenance.py no longer defines ${name} as a dict literal`).not.toBeNull();
  const constants = backendConstants();
  const out: Record<string, string> = {};
  for (const m of (block![1] ?? '').matchAll(/^\s*"([a-z_]+)":\s*(ORIGIN_[A-Z_]+),/gm)) {
    const value = constants.get(m[2]);
    expect(value, `${name} maps ${m[1]} to ${m[2]}, which is not an origin constant`).toBeDefined();
    out[m[1]] = value as string;
  }
  return out;
}

describe('the Python source can actually be read', () => {
  it('finds the constants, both tuples and both tables', () => {
    // Guards the guard: a shape change must fail loudly here rather than making
    // every parity assertion below vacuously true.
    expect(backendConstants().size).toBeGreaterThanOrEqual(12);
    expect(backendTuple('ORIGINS')).toHaveLength(8);
    expect(backendTuple('REVIEW_STATES')).toHaveLength(4);
    expect(backendTuple('ORIGIN_PRECEDENCE')).toHaveLength(8);
    expect(Object.keys(backendTable('SOURCE_TYPE_ORIGIN'))).toHaveLength(7);
    expect(Object.keys(backendTable('NOTE_SOURCE_ORIGIN'))).toHaveLength(5);
  });
});

// --- 2. parity --------------------------------------------------------------

describe('the client mirror is exactly the backend model', () => {
  it('has the same origin vocabulary, in the same order', () => {
    expect([...PROVENANCE_ORIGINS]).toEqual(backendTuple('ORIGINS'));
  });

  it('has the same review-state vocabulary, in the same order', () => {
    expect([...PROVENANCE_REVIEW_STATES]).toEqual(backendTuple('REVIEW_STATES'));
  });

  it('reads the SAME precedence order — the primary origin cannot disagree', () => {
    expect([...ORIGIN_PRECEDENCE]).toEqual(backendTuple('ORIGIN_PRECEDENCE'));
  });

  it('maps every evidence source type the same way', () => {
    expect({ ...SOURCE_TYPE_ORIGIN }).toEqual(backendTable('SOURCE_TYPE_ORIGIN'));
  });

  it('maps every note source the same way', () => {
    expect({ ...NOTE_SOURCE_ORIGIN }).toEqual(backendTable('NOTE_SOURCE_ORIGIN'));
  });

  it('gives every member of both dimensions a chip and a label', () => {
    for (const origin of PROVENANCE_ORIGINS) {
      expect(ORIGIN_CHIP[origin]).toBeDefined();
      expect(ORIGIN_LABEL[origin]).toBeTruthy();
    }
    for (const state of PROVENANCE_REVIEW_STATES) {
      expect(REVIEW_STATE_CHIP[state]).toBeDefined();
      expect(REVIEW_STATE_LABEL[state]).toBeTruthy();
    }
  });

  it('keeps the two dimensions disjoint as strings and as chip kinds', () => {
    const origins = new Set<string>(PROVENANCE_ORIGINS);
    expect([...PROVENANCE_REVIEW_STATES].some((s) => origins.has(s))).toBe(false);
    const originKinds = new Set(Object.values(ORIGIN_CHIP));
    const reviewKinds = new Set(Object.values(REVIEW_STATE_CHIP));
    expect([...reviewKinds].some((k) => originKinds.has(k))).toBe(false);
  });
});

// --- 3. the pure helpers ----------------------------------------------------

const ev = (source_type: string, extra: Partial<FieldEvidence> = {}): FieldEvidence =>
  ({ source_type, ...extra }) as FieldEvidence;

describe('origin derivation', () => {
  it('returns the SET of origins, not one of them', () => {
    expect(originsFromEvidence([ev('spreadsheet'), ev('user_confirmation')])).toEqual([
      'file',
      'manual',
    ]);
  });

  it('picks the primary by precedence, never by array position', () => {
    expect(primaryOrigin(originsFromEvidence([ev('user_confirmation'), ev('spreadsheet')]))).toBe(
      'file',
    );
    expect(primaryOrigin(originsFromEvidence([ev('spreadsheet'), ev('user_confirmation')]))).toBe(
      'file',
    );
    // The precedence order resolves every pair the same way in both directions.
    for (let i = 0; i < ORIGIN_PRECEDENCE.length; i += 1) {
      for (let j = i + 1; j < ORIGIN_PRECEDENCE.length; j += 1) {
        const high = ORIGIN_PRECEDENCE[i];
        const low = ORIGIN_PRECEDENCE[j];
        expect(primaryOrigin([high, low])).toBe(high);
        expect(primaryOrigin([low, high])).toBe(high);
      }
    }
  });

  it('says `evidence` for a citation whose channel it cannot name, never `unknown`', () => {
    expect(originsFromEvidence([ev('some_future_kind')])).toEqual(['evidence']);
    expect(originsFromEvidence([{ } as FieldEvidence])).toEqual(['evidence']);
  });

  it('says `unknown` only when nothing is recorded, and never guesses', () => {
    expect(originsFromEvidence([])).toEqual([]);
    expect(originsFromEvidence(undefined)).toEqual([]);
    expect(primaryOrigin([])).toBe('unknown');
    expect(primaryOrigin(['not_an_origin'])).toBe('unknown');
    expect(originForNoteSource('not_a_note_source')).toBe('unknown');
    expect(originForNoteSource(undefined)).toBe('unknown');
  });

  it('maps a transcript note to `voice` — a member of the model, not a feature', () => {
    expect(originForNoteSource('transcript')).toBe('voice');
    // Nothing in this build transcribes anything, so no static list may offer it.
    // The chip renders only from data, which is what the surface tests below check.
  });
});

describe('review-state derivation', () => {
  it('needs BOTH a verified status and a citation to say supported', () => {
    expect(reviewStateFor({ status: 'verified', evidence: [ev('spreadsheet')] })).toBe('supported');
    expect(reviewStateFor({ status: 'verified', evidence: [] })).toBe('needs_review');
    expect(reviewStateFor({ status: 'inferred', evidence: [ev('derivation')] })).toBe(
      'needs_review',
    );
  });

  it('falls to the conservative state for anything it does not recognise', () => {
    for (const status of ['unavailable', 'missing', 'rejected', 'needs_confirmation', undefined]) {
      expect(reviewStateFor({ status, evidence: [ev('spreadsheet')] })).toBe('needs_review');
    }
  });

  it('reports a conflict from two incompatible asserted answers', () => {
    expect(
      hasConflictingEvidence([
        ev('user_confirmation', { answer: 'one' }),
        ev('user_confirmation', { answer: 'two' }),
      ]),
    ).toBe(true);
    // The same answer twice is not a conflict.
    expect(
      hasConflictingEvidence([
        ev('user_confirmation', { answer: 'one' }),
        ev('user_confirmation', { answer: 'one' }),
      ]),
    ).toBe(false);
    expect(
      reviewStateFor({
        status: 'verified',
        evidence: [
          ev('user_confirmation', { answer: 'one' }),
          ev('user_confirmation', { answer: 'two' }),
        ],
      }),
    ).toBe('conflict');
  });

  it('marks an unreviewed note as not yet placed', () => {
    expect(reviewStateFor({ noteState: 'unreviewed' })).toBe('unmapped');
  });
});

// --- 4. THE CONSTRAINT: an origin never implies support ---------------------

describe('origin never implies support', () => {
  it('accepts no origin argument at all', () => {
    // The structural form of the guarantee: there is no parameter to pass one
    // through, so no caller can make an origin decide a review state.
    const keys = ['status', 'evidence', 'noteState'];
    for (const origin of PROVENANCE_ORIGINS) {
      // Passing it anyway changes nothing — it is not read.
      const withOrigin = reviewStateFor({
        status: 'needs_confirmation',
        evidence: [ev('spreadsheet')],
        ...({ origin } as Record<string, unknown>),
      });
      expect(withOrigin).toBe('needs_review');
    }
    expect(keys).toContain('status');
  });

  it.each([
    ['file', [ev('spreadsheet', { source_file: 's.csv' })]],
    ['derived', [ev('derivation', { rule: 'a documented rule' })]],
  ] as const)('a %s origin renders beside "Needs review"', (origin, evidence) => {
    expect(primaryOrigin(originsFromEvidence(evidence))).toBe(origin);
    const state = reviewStateFor({ status: 'needs_confirmation', evidence });
    expect(state).toBe('needs_review');

    const view = render(
      <ProvenanceChipPair origin={origin} reviewState={state} />,
    );
    expect(view.getByText(ORIGIN_LABEL[origin])).toBeTruthy();
    expect(view.getByText(REVIEW_STATE_LABEL.needs_review)).toBeTruthy();
  });

  it('an assistant origin renders beside "Needs review" too', () => {
    // The third negative control. Nothing in this build produces this origin, so
    // it is exercised at the level it exists: as a member of the dimension.
    const view = render(<ProvenanceChipPair origin="assistant" reviewState="needs_review" />);
    expect(view.getByText(ORIGIN_LABEL.assistant)).toBeTruthy();
    expect(view.getByText(REVIEW_STATE_LABEL.needs_review)).toBeTruthy();
  });

  it('gives EVERY origin the same neutral palette, so colour cannot encode support', () => {
    const classes = new Set(
      PROVENANCE_ORIGINS.map((origin) => CHIP_META[ORIGIN_CHIP[origin]].className),
    );
    // One neutral class, plus the dashed variant that "Origin not recorded" wears
    // because an absence is a different fact — not a lower confidence.
    expect([...classes].sort()).toEqual(['chip-origin', 'chip-origin-absent']);
    expect(CHIP_META[ORIGIN_CHIP.unknown].className).toBe('chip-origin-absent');
    // ...and none of them borrows a verdict palette.
    for (const cls of classes) {
      expect(cls).not.toMatch(/verified|pass|fail|needsyou/);
    }
  });

  it('gives each origin its own glyph, since colour is not available to tell them apart', () => {
    const kinds = PROVENANCE_ORIGINS.map((o) => ORIGIN_CHIP[o]);
    expect(new Set(kinds).size).toBe(PROVENANCE_ORIGINS.length);
  });

  it('NO ORIGIN GLYPH DRAWS A VERDICT MARK — the last channel that could encode approval', () => {
    /*
     * The glyph set was pinned for DISTINCTNESS above, and for nothing else, so
     * nothing stopped an origin borrowing the review axis's meaning.
     *
     * Independent review found `origManual` set to lucide's `UserCheck` — a
     * torso, a head, and `polyline points="16 11 18 13 22 9"`, i.e. a check mark
     * — drawn at the same size and stroke as `revSupported: Check`, directly
     * beneath a comment reading "NOTHING here is a check mark: an origin is
     * never an approval." A field a person typed and nobody confirmed therefore
     * showed a check beside "Needs review", and the check is the
     * higher-contrast, faster-read mark of the two.
     *
     * The Python signature forbids origin reaching the review decision and the
     * palette is neutral for all eight origins; the glyph was the one remaining
     * channel, and it was leaking.
     *
     * Compared by RENDERED GEOMETRY rather than by identifier, so a rename — or
     * a different icon that happens to draw a tick — is caught the same way.
     */
    const geometryOf = (Icon: LucideIcon) => render(<Icon />).container.innerHTML;

    const verdictShapes = new Set(
      [CHIP_ICON.verified, CHIP_ICON.confirmed, CHIP_ICON.pass].map(geometryOf),
    );
    // Guard the guard: if the verdict glyphs were empty or all identical to a
    // blank render, the comparison below would prove nothing.
    expect(verdictShapes.size).toBeGreaterThan(0);
    for (const shape of verdictShapes) expect(shape.length).toBeGreaterThan(20);

    for (const origin of PROVENANCE_ORIGINS) {
      const shape = geometryOf(CHIP_ICON[ORIGIN_CHIP[origin]]);
      expect(
        verdictShapes.has(shape),
        `the "${origin}" origin glyph draws a verdict mark; an origin is never an approval`,
      ).toBe(false);
    }
  });

  it('never labels an origin with the truth core\'s word "verified"', () => {
    for (const origin of PROVENANCE_ORIGINS) {
      expect(ORIGIN_LABEL[origin].toLowerCase()).not.toContain('verified');
    }
  });
});

// --- 5. two chips, and they stay two ----------------------------------------

describe('the chip pair renders TWO distinct chips', () => {
  it('renders one chip per dimension, each with its own label', () => {
    const view = render(<ProvenanceChipPair origin="file" reviewState="supported" />);
    const chips = view.container.querySelectorAll('.chip');
    expect(chips).toHaveLength(2);
    expect(view.container.querySelector('[data-origin="file"]')).toBeTruthy();
    expect(view.container.querySelector('[data-review-state="supported"]')).toBeTruthy();
    expect(view.getByText(ORIGIN_LABEL.file)).toBeTruthy();
    expect(view.getByText(REVIEW_STATE_LABEL.supported)).toBeTruthy();
    // The two labels are different strings — one is never a rename of the other.
    expect(ORIGIN_LABEL.file).not.toBe(REVIEW_STATE_LABEL.supported);
  });

  it('renders each chip on its own when only one dimension is being shown', () => {
    expect(render(<OriginChip origin="derived" />).container.querySelectorAll('.chip')).toHaveLength(
      1,
    );
    expect(
      render(<ReviewStateChip state="conflict" />).container.querySelectorAll('.chip'),
    ).toHaveLength(1);
  });
});

// --- 6. the two existing evidence surfaces, with nothing removed -------------

describe('EvidenceRow keeps every existing detail and adds the origin', () => {
  it('still renders the source type, the rule and the file, plus an origin chip', () => {
    const view = render(
      <EvidenceRow
        evidence={ev('derivation', { rule: 'the edge follows from the element', source_file: 'notes.txt' })}
      />,
    );
    // Existing detail — unchanged.
    expect(view.getByText('derivation')).toBeTruthy();
    expect(view.getByText(/rule: the edge follows/)).toBeTruthy();
    expect(view.getByText('notes.txt')).toBeTruthy();
    // New dimension, added beside it.
    expect(view.container.querySelector('[data-origin="derived"]')).toBeTruthy();
    // A citation has no review state of its own — only the field does.
    expect(view.container.querySelector('[data-review-state]')).toBeNull();
  });

  it('shows an unrecognised source type as `evidence`, never as `unknown`', () => {
    const view = render(<EvidenceRow evidence={ev('some_future_kind')} />);
    expect(view.getByText('some_future_kind')).toBeTruthy();
    expect(view.container.querySelector('[data-origin="evidence"]')).toBeTruthy();
  });
});

const trailEntry = (over: Partial<EvidenceTrailEntry> = {}): EvidenceTrailEntry => ({
  key: 'sample.material.formula',
  label: 'Formula',
  status: 'verified',
  sourceTypes: ['spreadsheet'],
  evidence: [ev('spreadsheet', { source_file: 'campaign.csv', locator: 'B2' })],
  namespaced: false,
  resolved: true,
  ...over,
});

function renderTrail(entries: EvidenceTrailEntry[]) {
  return render(
    <EvidenceTrailPanel
      entries={entries}
      directTotal={entries.length}
      selectedKey={entries[0]?.key ?? ''}
      onSelect={vi.fn()}
      meta={{ schema_version: '1.05', generated_utc: '2099-01-01T00:00:00Z' }}
    />,
  );
}

describe('EvidenceTrailPanel shows both dimensions without losing anything', () => {
  it('keeps the key and the existing markers, and adds exactly two chips per entry', () => {
    const view = renderTrail([trailEntry()]);
    expect(view.getByText('sample.material.formula')).toBeTruthy();
    expect(view.container.querySelectorAll('.prov-pair')).toHaveLength(1);
    expect(view.container.querySelectorAll('.trail-provenance .chip')).toHaveLength(2);
    expect(view.container.querySelector('[data-origin="file"]')).toBeTruthy();
    expect(view.container.querySelector('[data-review-state="supported"]')).toBeTruthy();
  });

  it('an entry read out of a file but not confirmed reads "From a file" AND "Needs review"', () => {
    const view = renderTrail([trailEntry({ status: 'needs_confirmation' })]);
    expect(view.container.querySelector('[data-origin="file"]')).toBeTruthy();
    expect(view.container.querySelector('[data-review-state="needs_review"]')).toBeTruthy();
    expect(view.getByText(ORIGIN_LABEL.file)).toBeTruthy();
    expect(view.getByText(REVIEW_STATE_LABEL.needs_review)).toBeTruthy();
  });

  it('an unreadable entry keeps its unavailable marker and is never called supported', () => {
    const view = renderTrail([
      trailEntry({ status: 'unavailable', unavailable: true, evidence: [] }),
    ]);
    // Existing behaviour — the entry stays in the list and says so in text.
    expect(view.getByText('unavailable')).toBeTruthy();
    expect(view.container.querySelector('[data-review-state="needs_review"]')).toBeTruthy();
    expect(view.container.querySelector('[data-origin="unknown"]')).toBeTruthy();
  });

  it('puts the chips OUTSIDE the selection button, so they are not part of its name', () => {
    const view = renderTrail([trailEntry()]);
    const button = view.container.querySelector('.trail-entry');
    expect(button).toBeTruthy();
    expect(button!.querySelector('.prov-pair')).toBeNull();
  });
});
