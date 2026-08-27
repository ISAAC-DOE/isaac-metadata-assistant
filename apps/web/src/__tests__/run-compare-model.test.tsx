/*
 * THE COMPARISON MODEL — `lib/runCompare.ts`, on its own.
 *
 * WHY THIS FILE EXISTS AT ALL. The model had NO unit tests. Every assertion about
 * it went through `run-compare.test.tsx`, which renders `RunsSection`, stubs
 * `fetch`, and reads categories back out of the DOM — so a defect in the model and
 * a defect in the table looked identical, and a case the surface happens not to
 * render could not be asserted at all. Widening a model whose only evidence is a
 * screen is how a claim about two documents becomes a claim about a screenshot.
 *
 * WHAT IS ASSERTED HERE, AND THE MUTATION EACH ONE CATCHES:
 *
 *   1. THE FIVE AXES ARE INDEPENDENT. Each one is exercised alone, with the other
 *      four held equal, so a `categoryOf` that collapsed any two of them goes red.
 *   2. `incomparable` IS AN ANSWER, NOT A DIFFERENCE. It is excluded from
 *      `differing` AND from `agreeing`, and the three headline numbers are asserted
 *      NOT to sum whenever it is non-zero.
 *   3. THE BREAKDOWN PARTITIONS. value + absentOnOne + review + provenance +
 *      evidence === differing, asserted as an identity rather than as five numbers.
 *   4. A RECORDED CONFLICT IS NOT A DIFFERENCE. It never sets a category, never
 *      enters `differing`, and it DOES list a row the three axes call the same.
 *   5. `unknown` IS NOT `neither`. A conflicts read that was not obtained can never
 *      be reported as "no conflict is stored" — the single most consequential thing
 *      this model could get quietly wrong.
 *   6. SUPPORT IS A SET, COUNTED AND DESCRIBED. Stored order never manufactures a
 *      difference; a duplicate citation is two citations; an entry this build
 *      cannot read is kept and counted, never dropped.
 *
 * There is a NEGATIVE CONTROL at the end. This repository has shipped a parity
 * test that passed an inverted disclosure, so a file whose assertions are all
 * "contains X" needs one case proving the assertions can fail.
 */

import { describe, expect, it } from 'vitest';

import {
  buildRunComparison,
  categoryWord,
  conflictWord,
  describeSupport,
  originsWord,
  reviewWord,
  supportWord,
  type CompareRow,
  type RunComparison,
} from '../lib/runCompare';
import type { ApiConflict, ApiRunInherited, ApiRunView } from '../lib/types';

/* ── fixtures ──────────────────────────────────────────────────────────────── */

/** A citation, shaped the way `FieldEvidence` is on the wire. */
const sheet = (file: string, locator: string) => ({
  source_type: 'spreadsheet',
  source_file: file,
  locator,
});

const confirmed = (answer: string) => ({
  source_type: 'user_confirmation',
  question: 'What is it?',
  answer,
  timestamp: '2099-04-02T09:05:00Z',
});

const env = (value: unknown, evidence: unknown[] = [], status = 'verified') => ({
  value,
  status,
  evidence,
});

function run(over: Partial<ApiRunView> = {}): ApiRunView {
  return {
    id: 'RUN001',
    experiment_id: 'demo',
    label: 'Run 1',
    ordinal: 1,
    created_utc: '2099-04-02T09:05:00Z',
    updated_utc: '2099-04-02T09:05:00Z',
    rev: 0,
    version: 'r1.0',
    record_id: null,
    fields: {},
    inherited: {},
    ...over,
  };
}

const inherited = (payload: unknown, state: ApiRunInherited['state'] = 'inherited'): ApiRunInherited => ({
  state,
  payload,
  inherited_payload: payload,
  overridable: true,
});

/**
 * A recorded conflict, shaped the way `GET .../conflicts?run=` sends one.
 *
 * THE ADDRESS IS THE BARE DOTTED PATH, not `field:…`. That is the server's own key
 * — `conflict_report` walks `serialize.evidence_trail_from_draft`, whose `path` is
 * the draft's own key — and a model that prefixed it would index nothing and
 * report "no conflict" forever. Asserted explicitly further down.
 */
function conflict(address: string, over: Partial<ApiConflict> = {}): ApiConflict {
  return {
    address,
    run_id: 'RUN001',
    candidates: [],
    distinct_value_count: 2,
    evidence_count: 3,
    unavailable: false,
    explanation: 'Two distinct answers are cited at this address.',
    resolution_state: 'absent',
    resolved: false,
    resolution_stale: false,
    resolution: null,
    ...over,
  };
}

/** The row for one address, or a failure that names the address rather than `undefined`. */
function rowAt(comparison: RunComparison, address: string): CompareRow {
  for (const group of comparison.groups) {
    for (const row of group.rows) if (row.address === address) return row;
  }
  throw new Error(`no row for ${address} — rows: ${allRows(comparison).map((r) => r.address).join(', ')}`);
}

function allRows(comparison: RunComparison): CompareRow[] {
  return comparison.groups.flatMap((group) => group.rows);
}

/* ── 1. the five axes are independent ──────────────────────────────────────── */

describe('the axes do not collapse into one another', () => {
  it('the same value from the same source with the same citations is `same`', () => {
    const a = run({ fields: { 'context.environment': env('in_situ', [sheet('s.csv', 'A1')]) } });
    const b = run({ id: 'R2', fields: { 'context.environment': env('in_situ', [sheet('s.csv', 'A1')]) } });
    const row = rowAt(buildRunComparison(a, b), 'context.environment');
    expect(row.category).toBe('same');
    expect(row.listed).toBe(false);
    expect(row.value).toBe('equal');
    expect(row.review).toBe('same');
    expect(row.provenance).toBe('same');
    expect(row.evidence).toBe('same');
  });

  it('a value difference outranks every other axis and is stated once', () => {
    const a = run({ fields: { 'context.temperature_K': env(300) } });
    const b = run({ id: 'R2', fields: { 'context.temperature_K': env(450, [confirmed('450')]) } });
    const row = rowAt(buildRunComparison(a, b), 'context.temperature_K');
    expect(row.category).toBe('value');
    // The other axes still hold their own answers — the category is a rendering
    // choice over a partition, never an erasure of what the row also knows.
    expect(row.review).toBe('differs');
    expect(row.evidence).toBe('differs');
  });

  it('absence is `absent-on-one` and never a value difference', () => {
    const a = run({ fields: { 'context.environment': env('in_situ') } });
    const b = run({ id: 'R2', fields: {} });
    const row = rowAt(buildRunComparison(a, b), 'context.environment');
    expect(row.category).toBe('absent-on-one');
    expect(row.value).toBe('one-absent');
    // The three "is this a difference about a value" axes all stand down, so one
    // absence can never be counted twice.
    expect(row.provenance).toBe('not-applicable');
    expect(row.evidence).toBe('not-applicable');
    expect(row.review).toBe('not-applicable');
  });

  it('an address in neither run is an agreeing row, not a difference', () => {
    const row = rowAt(buildRunComparison(run(), run({ id: 'R2' })), 'timestamps.acquired_end_utc');
    expect(row.value).toBe('both-absent');
    expect(row.category).toBe('same');
    expect(row.listed).toBe(false);
  });

  it('REVIEW alone: same value, same citations count, different review state', () => {
    // `reviewStateFor`'s rule: `supported` needs a verified status AND >= 1
    // citation. Same value, same origin set, same count — only the status moves.
    const a = run({ fields: { 'context.environment': env('in_situ', [sheet('s.csv', 'A1')]) } });
    const b = run({
      id: 'R2',
      fields: { 'context.environment': env('in_situ', [sheet('s.csv', 'A1')], 'needs_confirmation') },
    });
    const row = rowAt(buildRunComparison(a, b), 'context.environment');
    expect(row.review).toBe('differs');
    expect(row.category).toBe('review');
    expect(row.a.reviewState).toBe('supported');
    expect(row.b.reviewState).toBe('needs_review');
    // ...and it is not mistaken for a value or a source difference.
    expect(row.value).toBe('equal');
    expect(row.provenance).toBe('same');
  });

  it('PROVENANCE alone: same value, same review state, different cited origin', () => {
    /*
     * THE ROW THAT PROVES THE RUN-FIELD ARM CHANGED. `provenanceRelation` used to
     * return `not-applicable` for every run-level field, because inheritance was
     * the only thing it compared — so one run's temperature read out of a
     * spreadsheet and the other's answered by a person reported NO difference at
     * all. Revert that short-circuit and this goes red.
     */
    const a = run({ fields: { 'context.temperature_K': env(300, [sheet('s.csv', 'A1')]) } });
    const b = run({ id: 'R2', fields: { 'context.temperature_K': env(300, [confirmed('300')]) } });
    const row = rowAt(buildRunComparison(a, b), 'context.temperature_K');
    expect(row.scope).toBe('run-field');
    expect(row.provenance).toBe('differs');
    expect(row.category).toBe('provenance');
    expect(row.a.origins).toEqual(['file']);
    expect(row.b.origins).toEqual(['manual']);
    // Both are supported (verified + a citation), so this is not a review difference.
    expect(row.review).toBe('same');
  });

  it('EVIDENCE alone: same value, same origin, same count, different entries', () => {
    /*
     * THE ROW THAT PROVES THE EVIDENCE AXIS WIDENED. Two spreadsheet citations of
     * the same file at different locators: same status, same count, same origin
     * set, same review state. Before the widening this compared `status` and
     * `evidenceCount` only and reported `same`. Delete `supportSignature` from
     * `evidenceRelation` and this goes red.
     */
    const a = run({ fields: { 'context.environment': env('in_situ', [sheet('s.csv', 'A1')]) } });
    const b = run({ id: 'R2', fields: { 'context.environment': env('in_situ', [sheet('s.csv', 'B7')]) } });
    const row = rowAt(buildRunComparison(a, b), 'context.environment');
    expect(row.evidence).toBe('differs');
    expect(row.category).toBe('evidence');
    expect(row.value).toBe('equal');
    expect(row.provenance).toBe('same');
    expect(row.review).toBe('same');
    expect(row.a.evidenceCount).toBe(1);
    expect(row.b.evidenceCount).toBe(1);
  });

  it('inheritance is still its own provenance answer at a record-level address', () => {
    const payload = env('Synthetic CuO powder');
    const a = run({ inherited: { 'field:sample.material.name': inherited(payload) } });
    const b = run({
      id: 'R2',
      inherited: { 'field:sample.material.name': inherited(payload, 'overridden') },
    });
    const row = rowAt(buildRunComparison(a, b), 'field:sample.material.name');
    expect(row.category).toBe('provenance');
    expect(row.a.origin).toBe('inherited');
    expect(row.b.origin).toBe('overridden');
    // The server's word, mirrored into the origin SET as well — and only on the
    // side that actually inherits.
    expect(row.a.origins).toContain('inherited');
    expect(row.b.origins).not.toContain('inherited');
  });

  it('`unresolved` is not `absent`, and the two carry different origins', () => {
    const a = run({ inherited: { 'field:descriptors.notes': inherited(env('a note')) } });
    const b = run({ id: 'R2', inherited: {} });
    const row = rowAt(buildRunComparison(a, b), 'field:descriptors.notes');
    expect(row.b.origin).toBe('unresolved');
    expect(row.category).toBe('absent-on-one');
  });
});

/* ── 2 & 3. the tally ──────────────────────────────────────────────────────── */

describe('the tally counts what it can see and nothing else', () => {
  it('an address it cannot compare is in neither headline number', () => {
    const list = env([{ path: 'a.dat' }]);
    const a = run({ inherited: { 'field:assets.files': inherited(list) } });
    const b = run({ id: 'R2', inherited: { 'field:assets.files': inherited(list) } });
    const comparison = buildRunComparison(a, b);
    const row = rowAt(comparison, 'field:assets.files');
    expect(row.value).toBe('incomparable');
    expect(row.category).toBe('incomparable');
    // Listed — the reader must see that an address exists which is not compared —
    // and simultaneously NOT a difference.
    expect(row.listed).toBe(true);
    const { tally } = comparison;
    expect(tally.incomparable).toBe(1);
    expect(tally.differing).toBe(0);
    // The three headline numbers deliberately do NOT sum to `compared` here.
    expect(tally.differing + tally.agreeing).toBe(tally.compared - 1);
  });

  it('the breakdown partitions the differing rows, as an identity', () => {
    const a = run({
      fields: {
        'context.temperature_K': env(300),
        'context.environment': env('in_situ', [sheet('s.csv', 'A1')]),
        'context.thermodynamics.atmosphere': env('He'),
      },
      inherited: {
        'field:sample.form': inherited(env('powder', [sheet('s.csv', 'C1')])),
        'field:assets.files': inherited(env([{ path: 'a.dat' }])),
      },
    });
    const b = run({
      id: 'R2',
      fields: {
        'context.temperature_K': env(450),
        'context.environment': env('in_situ', [confirmed('in_situ')]),
      },
      inherited: {
        'field:sample.form': inherited(env('powder', [sheet('s.csv', 'C1')], 'needs_confirmation')),
        'field:assets.files': inherited(env([{ path: 'a.dat' }])),
      },
    });
    const { tally } = buildRunComparison(a, b);
    expect(tally.value + tally.absentOnOne + tally.review + tally.provenance + tally.evidence).toBe(
      tally.differing,
    );
    expect(tally.differing + tally.agreeing + tally.incomparable).toBe(tally.compared);
    // Each of the four difference kinds is actually present, so the identity above
    // is not being satisfied by four zeroes.
    expect(tally.value).toBeGreaterThan(0);
    expect(tally.absentOnOne).toBeGreaterThan(0);
    expect(tally.review).toBeGreaterThan(0);
    expect(tally.provenance).toBeGreaterThan(0);
  });

  it('`bothAbsent` is part of `agreeing`, never a difference', () => {
    const { tally } = buildRunComparison(run(), run({ id: 'R2' }));
    expect(tally.differing).toBe(0);
    expect(tally.bothAbsent).toBe(tally.compared);
    expect(tally.agreeing).toBe(tally.compared);
  });

  it('two empty runs produce the five run-level rows and no difference', () => {
    const comparison = buildRunComparison(run(), run({ id: 'R2' }));
    // `RUN_FIELDS` is unioned in so "neither run records a temperature" is a row
    // rather than an omission — the fact a reader asking "are these the same apart
    // from temperature?" needs.
    expect(comparison.tally.compared).toBe(5);
    expect(allRows(comparison).every((row) => row.scope === 'run-field')).toBe(true);
    expect(comparison.blocks).toEqual([]);
  });
});

/* ── 4 & 5. a recorded conflict is not a difference ────────────────────────── */

describe('a recorded conflict and a value difference stay different things', () => {
  const withConflict = (address: string, over: Partial<ApiConflict> = {}) =>
    buildRunComparison(
      run({ fields: { 'context.environment': env('in_situ', [sheet('s.csv', 'A1')]) } }),
      run({ id: 'R2', fields: { 'context.environment': env('in_situ', [sheet('s.csv', 'A1')]) } }),
      { a: { conflicts: [conflict(address, over)] }, b: { conflicts: [] } },
    );

  it('keys on the BARE dotted path the server uses, not on `field:`', () => {
    // Prefix the lookup key and every conflict silently disappears — the row reads
    // `neither`, the count reads 0, and nothing anywhere says a read was wasted.
    expect(rowAt(withConflict('context.environment'), 'context.environment').conflict).toBe('one');
    expect(rowAt(withConflict('field:context.environment'), 'context.environment').conflict).toBe(
      'neither',
    );
  });

  it('lists a row the three axes call the same, without calling it a difference', () => {
    const comparison = withConflict('context.environment');
    const row = rowAt(comparison, 'context.environment');
    // The category is untouched: the two runs record the same thing.
    expect(row.category).toBe('same');
    // ...and yet it is on screen, because a decision is outstanding there.
    expect(row.listed).toBe(true);
    expect(row.conflict).toBe('one');
    const { tally } = comparison;
    expect(tally.differing).toBe(0);
    expect(tally.conflicted).toBe(1);
    expect(tally.conflictedAgreeing).toBe(1);
    expect(tally.conflictedUnresolved).toBe(1);
    // The row is in `agreeing`, which is what makes the caption's exception real.
    expect(tally.agreeing).toBe(tally.compared);
  });

  it('a decided conflict is still listed and is no longer counted as awaiting one', () => {
    const decided = withConflict('context.environment', {
      resolution_state: 'current',
      resolved: true,
    });
    expect(rowAt(decided, 'context.environment').conflict).toBe('one');
    expect(decided.tally.conflicted).toBe(1);
    expect(decided.tally.conflictedUnresolved).toBe(0);

    // `stale` and `deferred` are BOTH still awaiting a decision. Treating either as
    // settled is the mistake `ApiConflictCounts.unresolved` is written out to stop.
    for (const state of ['stale', 'deferred'] as const) {
      const open = withConflict('context.environment', {
        resolution_state: state,
        resolved: state === 'stale',
        resolution_stale: state === 'stale',
      });
      expect(open.tally.conflictedUnresolved).toBe(1);
    }
  });

  it('`unknown` is never reported as `neither`', () => {
    /*
     * THE MOST CONSEQUENTIAL THING THIS MODEL COULD GET QUIETLY WRONG. With one
     * run's conflicts read missing, "no conflict is stored here" is a claim about a
     * set nobody looked at. Default `conflictIndex(undefined)` to an empty map and
     * this goes red in both directions at once.
     */
    const bothMissing = buildRunComparison(run(), run({ id: 'R2' }));
    expect(rowAt(bothMissing, 'context.environment').conflict).toBe('unknown');
    expect(bothMissing.tally.conflictsUnknown).toBe(true);
    expect(bothMissing.tally.conflicted).toBe(0);

    // ONE side read is still not enough: the other side's answer is unknown.
    const oneMissing = buildRunComparison(run(), run({ id: 'R2' }), { a: { conflicts: [] } });
    expect(rowAt(oneMissing, 'context.environment').conflict).toBe('unknown');
    expect(oneMissing.tally.conflictsUnknown).toBe(true);

    // Both read and empty IS an answer, and is a different one.
    const bothRead = buildRunComparison(run(), run({ id: 'R2' }), {
      a: { conflicts: [] },
      b: { conflicts: [] },
    });
    expect(rowAt(bothRead, 'context.environment').conflict).toBe('neither');
    expect(bothRead.tally.conflictsUnknown).toBe(false);
  });

  it('a conflict on both runs is `both` and is still one address, not two', () => {
    const comparison = buildRunComparison(
      run({ fields: { 'context.environment': env('in_situ') } }),
      run({ id: 'R2', fields: { 'context.environment': env('in_situ') } }),
      {
        a: { conflicts: [conflict('context.environment')] },
        b: { conflicts: [conflict('context.environment')] },
      },
    );
    expect(rowAt(comparison, 'context.environment').conflict).toBe('both');
    expect(comparison.tally.conflicted).toBe(1);
  });

  it('the conflict sentence names no other run and quotes no value', () => {
    const c = rowAt(withConflict('context.environment'), 'context.environment').a.conflict!;
    const text = conflictWord(c);
    expect(text).toContain('2 different answers are cited here');
    expect(text).toContain('No decision is recorded');
    // It is about ONE run's own citations. It never mentions the other run, and it
    // never reproduces a competing value — deciding is another surface's act.
    expect(text).not.toContain('Run 2');
    expect(text).not.toContain('in_situ');
  });
});

/* ── 6. support is a set, counted and described ────────────────────────────── */

describe('cited support is described and counted, never judged', () => {
  it('stored order does not manufacture a difference', () => {
    const one = [sheet('s.csv', 'A1'), confirmed('powder')];
    const other = [confirmed('powder'), sheet('s.csv', 'A1')];
    const row = rowAt(
      buildRunComparison(
        run({ fields: { 'context.environment': env('in_situ', one) } }),
        run({ id: 'R2', fields: { 'context.environment': env('in_situ', other) } }),
      ),
      'context.environment',
    );
    expect(row.evidence).toBe('same');
    expect(row.category).toBe('same');
  });

  it('a duplicate citation is two citations, not one', () => {
    // A Set-based signature would collapse these and report `same` beside a count
    // of 2 against a count of 1 — two numbers on one row disagreeing.
    const row = rowAt(
      buildRunComparison(
        run({
          fields: {
            'context.environment': env('in_situ', [sheet('s.csv', 'A1'), sheet('s.csv', 'A1')]),
          },
        }),
        run({ id: 'R2', fields: { 'context.environment': env('in_situ', [sheet('s.csv', 'A1')]) } }),
      ),
      'context.environment',
    );
    expect(row.a.evidenceCount).toBe(2);
    expect(row.b.evidenceCount).toBe(1);
    expect(row.evidence).toBe('differs');
  });

  it('an entry this build cannot read is kept and counted, never dropped', () => {
    const row = rowAt(
      buildRunComparison(
        run({ fields: { 'context.environment': env('in_situ', [{ id: 'EV-1' }, 7, null]) } }),
        run({ id: 'R2', fields: { 'context.environment': env('in_situ', []) } }),
      ),
      'context.environment',
    );
    expect(row.a.support).toHaveLength(3);
    expect(row.a.undescribableSupport).toBe(3);
    expect(row.a.evidenceCount).toBe(3);
    expect(supportWord(row.a.support[0])).toBe('an entry this build could not read');
    /*
     * ...AND A PAYLOAD THIS BUILD COULD NOT FULLY READ IS NEVER `supported`.
     *
     * An earlier version of this case asserted `supported` here, with the comment
     * "an unreadable citation still counts toward `supported` on the server's
     * rule". THAT WAS MEASURED FALSE AND IS RECORDED RATHER THAN QUIETLY
     * REPLACED. `serialize._readable_evidence` drops `7` and `null` (neither is a
     * dict) and reports the payload `unavailable`; `provenance.review_state` then
     * demotes it — "A PARTIALLY UNREADABLE PAYLOAD IS NEVER SUPPORT"
     * (`provenance.py:425-441`), a comment that exists because a green Supported
     * chip once sat directly beneath a row already marked unavailable. This table
     * renders exactly that pairing one element apart, so it must reach the same
     * answer.
     *
     * `{ id: 'EV-1' }` IS READABLE and is deliberately in the fixture: it is a
     * dict the server reads fine and that only THIS build cannot describe. The two
     * predicates are different and must not be collapsed — `undescribableSupport`
     * is 3, and the demotion is driven by the other two entries.
     */
    expect(row.a.reviewState).toBe('needs_review');

    // The demotion is the ONLY thing that moved: a readable citation beside a
    // verified status is still `supported`.
    const clean = rowAt(
      buildRunComparison(
        run({ fields: { 'context.environment': env('in_situ', [{ id: 'EV-1' }]) } }),
        run({ id: 'R2', fields: { 'context.environment': env('in_situ', [{ id: 'EV-1' }]) } }),
      ),
      'context.environment',
    );
    expect(clean.a.reviewState).toBe('supported');
  });

  it('describes source, file, locator and rule verbatim and ranks nothing', () => {
    expect(describeSupport(sheet('sheet.csv', 'B2'))).toMatchObject({
      sourceType: 'spreadsheet',
      sourceFile: 'sheet.csv',
      locator: 'B2',
      confirmation: false,
      undescribable: false,
    });
    expect(supportWord(describeSupport(sheet('sheet.csv', 'B2')))).toBe(
      'spreadsheet — sheet.csv · B2',
    );
    expect(supportWord(describeSupport(confirmed('powder')))).toBe('answered in this application');
    expect(
      supportWord(describeSupport({ source_type: 'derivation', rule: 'edge_from_element' })),
    ).toBe('derivation — rule edge_from_element');
    // A citation whose channel cannot be named is described as one, NOT as absent.
    expect(describeSupport({ source_file: 'x.csv' }).undescribable).toBe(false);
    expect(supportWord(describeSupport({ source_file: 'x.csv' }))).toBe(
      'a citation naming no source kind — x.csv',
    );
  });

  it('no word in the description vocabulary ranks one kind of support above another', () => {
    const words = [
      supportWord(describeSupport(sheet('s.csv', 'A1'))),
      supportWord(describeSupport(confirmed('x'))),
      supportWord(describeSupport({})),
      originsWord({ ...rowAt(buildRunComparison(run(), run({ id: 'R2' })), 'context.environment').a, origins: ['file', 'manual'] }),
      reviewWord('supported'),
      reviewWord('needs_review'),
      categoryWord('review'),
      categoryWord('evidence'),
    ].join(' | ');
    for (const banned of ['better', 'worse', 'stronger', 'weaker', 'preferred', 'reliable']) {
      expect(words.toLowerCase()).not.toContain(banned);
    }
  });
});

/* ── blocks: named, not compared, and now described by key ─────────────────── */

describe('block addresses are excluded and the exclusion says what is inside', () => {
  const blocked = (payloadA: unknown, payloadB: unknown) =>
    buildRunComparison(
      run({ inherited: { 'block:measurement': inherited(payloadA) } }),
      run({ id: 'R2', inherited: { 'block:measurement': inherited(payloadB) } }),
    );

  it('never becomes a row and never becomes a value', () => {
    const comparison = blocked({ series: {} }, { series: {} });
    expect(allRows(comparison).some((row) => row.address.startsWith('block:'))).toBe(false);
    expect(comparison.blocks).toHaveLength(1);
    expect(comparison.blocks[0].name).toBe('measurement');
  });

  it('names the top-level keys of each side and which are on one side only', () => {
    const [block] = blocked({ series: {}, qc: {} }, { series: {} }).blocks;
    expect(block.keysA).toEqual(['qc', 'series']);
    expect(block.keysB).toEqual(['series']);
    expect(block.onlyA).toEqual(['qc']);
    expect(block.onlyB).toEqual([]);
    expect(block.unnamedA).toBe(false);
  });

  it('a payload with no nameable keys says so instead of inventing indices', () => {
    // `Object.keys` on a list yields "0", "1" — positional claims the payload never
    // made. A list, a scalar and `null` all land in `unnamed`.
    for (const payload of [[{ a: 1 }], 'a string', 7, null]) {
      const [block] = blocked(payload, { series: {} }).blocks;
      expect(block.unnamedA).toBe(true);
      expect(block.keysA).toEqual([]);
      // With one side unnamed, "only on Run 2" is withheld: it would be read off a
      // comparison with nothing on the other side.
      expect(block.onlyB).toEqual([]);
    }
  });

  it('a block only one run resolves is stated as that, not as an empty one', () => {
    const comparison = buildRunComparison(
      run({ inherited: { 'block:measurement': inherited({ series: {} }) } }),
      run({ id: 'R2', inherited: {} }),
    );
    const [block] = comparison.blocks;
    expect(block.presentOnA).toBe(true);
    expect(block.presentOnB).toBe(false);
    expect(block.unnamedB).toBe(false);
  });
});

/* ── the negative control ──────────────────────────────────────────────────── */

/**
 * PROOF THAT THE ASSERTIONS ABOVE HAVE THE RIGHT POLARITY.
 *
 * This repository has shipped a parity test whose first version passed an INVERTED
 * disclosure — every assertion green, the claim backwards. A file whose assertions
 * are almost all "this equals that" needs one case that mechanically demonstrates
 * the same assertions going red on the wrong answer, rather than a reader taking
 * it on trust.
 *
 * Each pair below is the SAME assertion run against the correct model and against
 * the plausible wrong one, written out in full so the wrong one is visible rather
 * than described.
 */
describe('negative control: the assertions above can fail', () => {
  it('a conflict-carrying agreeing row would be INVISIBLE under the pre-widening `listed`', () => {
    const comparison = buildRunComparison(
      run({ fields: { 'context.environment': env('in_situ') } }),
      run({ id: 'R2', fields: { 'context.environment': env('in_situ') } }),
      { a: { conflicts: [conflict('context.environment')] }, b: { conflicts: [] } },
    );
    const row = rowAt(comparison, 'context.environment');
    expect(row.listed).toBe(true);

    // The mutation: `listed = category !== 'same'`, which is what the field meant
    // before a conflict could list a row. Under it the row is hidden by default.
    const preWidening = row.category !== 'same';
    expect(preWidening).toBe(false);
    expect(preWidening).not.toBe(row.listed);
  });

  it('the old `differing` formula WOULD have counted that row as a disagreement', () => {
    const comparison = buildRunComparison(
      run({ fields: { 'context.environment': env('in_situ') } }),
      run({ id: 'R2', fields: { 'context.environment': env('in_situ') } }),
      { a: { conflicts: [conflict('context.environment')] }, b: { conflicts: [] } },
    );
    expect(comparison.tally.differing).toBe(0);

    // The mutation: `rows.filter(r => r.listed && r.category !== 'incomparable')`,
    // which was exactly right until `listed` widened. It now reports a
    // disagreement between two runs that record the same thing.
    const oldFormula = allRows(comparison).filter(
      (r) => r.listed && r.category !== 'incomparable',
    ).length;
    expect(oldFormula).toBe(1);
    expect(oldFormula).not.toBe(comparison.tally.differing);
  });

  it('an unread conflicts response WOULD read as "no conflict" under an empty-map default', () => {
    const comparison = buildRunComparison(run(), run({ id: 'R2' }));
    expect(rowAt(comparison, 'context.environment').conflict).toBe('unknown');

    // The mutation: treating `undefined` as an empty list. Both produce a row with
    // no conflict attached, and only one of them says nobody looked.
    const asEmpty = buildRunComparison(run(), run({ id: 'R2' }), {
      a: { conflicts: [] },
      b: { conflicts: [] },
    });
    expect(rowAt(asEmpty, 'context.environment').conflict).toBe('neither');
    expect(rowAt(asEmpty, 'context.environment').conflict).not.toBe(
      rowAt(comparison, 'context.environment').conflict,
    );
  });

  it('the pre-widening EVIDENCE axis WOULD call two different citations the same', () => {
    const a = run({ fields: { 'context.environment': env('in_situ', [sheet('s.csv', 'A1')]) } });
    const b = run({ id: 'R2', fields: { 'context.environment': env('in_situ', [sheet('s.csv', 'B7')]) } });
    const row = rowAt(buildRunComparison(a, b), 'context.environment');
    expect(row.evidence).toBe('differs');

    // The mutation: compare status and count only, which is what the axis did.
    const preWidening =
      row.a.status === row.b.status && row.a.evidenceCount === row.b.evidenceCount;
    expect(preWidening).toBe(true);
    // The two verdicts disagree, which is the whole point: the old axis calls this
    // pair `same` and the widened one calls it `differs`.
    expect(preWidening).not.toBe(row.evidence === 'same');
  });
});
