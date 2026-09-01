/*
 * THE CHANGE-FEED CLASSIFIER — the decisions `useChangeFeed` deliberately does not make.
 *
 * These are pure-function tests on purpose. The properties that matter here — that a
 * scientist's own save is not reported back to them, that a proposal's content cannot
 * reach a surface through this path, and that the announcement makes no latency claim —
 * are properties of a function, and asserting them through a rendered component would
 * make them hostage to whatever else that component does.
 */

import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, it, expect } from 'vitest';
import {
  RECORD_ACTIVITY_CADENCE_CLAIM,
  RECORD_ACTIVITY_INPUT_SAFETY_CLAIM,
  describeChangeSummary,
  needsCanonicalRefetch,
  summariseChanges,
} from '../lib/recordChanges';
import type { ApiChangeEntry } from '../lib/types';

const run = (id: string, at: number): ApiChangeEntry => ({
  kind: 'run',
  entity_id: id,
  changed_at_rev: at,
  version: `gen.${at}`,
  rev: at,
  generation: 'gen',
  updated_utc: '2026-08-30T12:00:00Z',
});

const experiment = (at: number): ApiChangeEntry => ({
  kind: 'experiment',
  entity_id: 'EXP',
  changed_at_rev: at,
  version: `gen.${at}`,
  rev: at,
  generation: 'gen',
  updated_utc: '2026-08-30T12:00:00Z',
});

/** Exactly the key set the server pins in
 *  `test_a_proposal_entry_carries_NO_CONTENT_over_the_wire`. */
const proposal = (id: string, at: number, state = 'open'): ApiChangeEntry => ({
  kind: 'proposal',
  entity_id: id,
  changed_at_rev: at,
  updated_utc: '2026-08-30T12:00:00Z',
  state,
});

describe('summariseChanges — what is news to a view that already holds a revision', () => {
  it('reports nothing for entries at or below the revision on screen', () => {
    /*
     * THE SELF-SAVE CASE, WHICH IS ALSO THE FIRST-POLL CASE. A first poll carries no
     * cursor and so returns EVERY entity at its current position. A view holding rev 9
     * has already adopted all of it, and announcing "this record changed" on mount
     * would be false on every record in the product.
     */
    expect(summariseChanges([experiment(9), run('R1', 4), run('R2', 9)], 9)).toBeNull();
  });

  it('reports an entry strictly above the revision on screen', () => {
    const s = summariseChanges([experiment(10), run('R1', 10)], 9)!;
    expect(s).not.toBeNull();
    expect(s.recordMoved).toBe(true);
    expect(s.runIds).toEqual(['R1']);
  });

  it('splits one page by kind, de-duplicates and sorts', () => {
    const s = summariseChanges(
      [run('R2', 5), run('R1', 5), run('R1', 6), proposal('P2', 5), proposal('P1', 5)],
      0,
    )!;
    expect(s.runIds).toEqual(['R1', 'R2']);
    expect(s.proposalIds).toEqual(['P1', 'P2']);
    expect(s.recordMoved).toBe(false);
  });

  it('files a kind this build does not know rather than dropping it', () => {
    // `feed_kinds()` is served so a client learns the set from the server. A build
    // that silently ignored a fourth kind would under-report a real change.
    const s = summariseChanges([{ kind: 'note', entity_id: 'N1', changed_at_rev: 3 }], 0)!;
    expect(s.otherKinds).toEqual(['note']);
    expect(s.recordMoved).toBe(false);
  });

  it('treats an unreadable sequence position as news rather than discarding it', () => {
    // Withholding a change because its coordinate could not be compared is the
    // failure mode that loses one. `changed_at_rev` is typed `number`, so this is
    // a payload a server could send that the type does not describe.
    const bad = { kind: 'run', entity_id: 'R1' } as unknown as ApiChangeEntry;
    expect(summariseChanges([bad], 100)!.runIds).toEqual(['R1']);
  });

  it('filters nothing when the screen has not said where it stands', () => {
    // `undefined` is not `0`. A floor of 0 would suppress every entity whose
    // position was never recorded, which is every entity of a pre-sequence document.
    const s = summariseChanges([run('R1', 0)], undefined)!;
    expect(s.runIds).toEqual(['R1']);
  });

  it('passes a lifecycle state through verbatim and never invents one', () => {
    const s = summariseChanges(
      [proposal('P1', 5, 'accepted'), proposal('P2', 5, 'a_state_this_build_never_heard_of')],
      0,
    )!;
    expect(s.proposalStates).toEqual(['a_state_this_build_never_heard_of', 'accepted']);

    // An absent state is absent, not defaulted to "open".
    const noState = { kind: 'proposal', entity_id: 'P3', changed_at_rev: 5 } as ApiChangeEntry;
    expect(summariseChanges([noState], 0)!.proposalStates).toEqual([]);
  });
});

describe('summariseChanges — NO proposal content can travel this path', () => {
  it('carries ids and kinds only, even when handed fields it does not expect', () => {
    /*
     * THE STRUCTURAL GUARANTEE, ASSERTED OVER THE OUTPUT. `change_feed.py` cannot
     * emit these — its proposal collector reads four stored attributes and the module
     * imports nothing from `proposals.py`. This is the client-side counterpart: even
     * if a future server field arrived, the summary is BUILT rather than spread, so
     * nothing unlisted reaches a surface.
     */
    const leaky = {
      ...proposal('P1', 5),
      proposed_value: 'LEAKCANARYVALUE',
      target_field_path: 'field:system.technique',
      rule: 'synthetic fixture rule',
      note_excerpt: 'a sentence a scientist wrote',
    } as unknown as ApiChangeEntry;

    const s = summariseChanges([leaky], 0)!;
    const serialised = JSON.stringify(s);
    for (const leak of [
      'LEAKCANARYVALUE',
      'field:system.technique',
      'synthetic fixture rule',
      'a sentence a scientist wrote',
    ]) {
      expect(serialised).not.toContain(leak);
    }
    expect(s.proposalIds).toEqual(['P1']);

    // And the announcement built from it carries none of it either.
    expect(describeChangeSummary(s)).not.toContain('LEAKCANARYVALUE');
  });
});

describe('describeChangeSummary — one coalesced sentence, and no claim it cannot keep', () => {
  it('states counts, not entities, and pluralises', () => {
    const one = describeChangeSummary(summariseChanges([proposal('P1', 5)], 0)!);
    expect(one).toContain('1 suggestion changed');

    const many = describeChangeSummary(
      summariseChanges([proposal('P1', 5), proposal('P2', 5), run('R1', 5), run('R2', 5)], 0)!,
    );
    expect(many).toContain('2 suggestions changed');
    expect(many).toContain('2 runs changed');
  });

  it('says "this record changed" only when that is the only thing to say', () => {
    // The record's own entry moves on any act inside it, so naming it beside the
    // runs it contains would report one change twice.
    const withRuns = describeChangeSummary(
      summariseChanges([experiment(5), run('R1', 5)], 0)!,
    );
    expect(withRuns).toContain('1 run changed');
    expect(withRuns).not.toContain('this record changed');

    const alone = describeChangeSummary(summariseChanges([experiment(5)], 0)!);
    expect(alone).toContain('this record changed');
  });

  it('makes NO latency claim, anywhere in the copy this slice ships', () => {
    /*
     * THE RULE THIS REPOSITORY KEEPS RE-LEARNING. "Real-time", "live" and "instantly"
     * are claims about LATENCY; no latency figure is measured anywhere here, and the
     * cadence is jittered, backs off to a minute and stops while the tab is hidden.
     * `useChangeFeed`'s own header records the heading that had to be corrected for
     * exactly this. The copy may describe the MECHANISM and nothing else.
     */
    /* A NEGATIVE LOOKBEHIND, NOT A LOOKAHEAD, AND THE FIRST VERSION HAD IT BACKWARDS.
       The cadence claim ENDS "…rather than instantly", which DENIES the claim — so a
       pattern forbidding the bare word failed on the one string in this slice that is
       most careful about it. What must be forbidden is asserting instantaneity, not
       mentioning it; "rather than instantly" is the disclaimer, not the claim. */
    const forbidden = [
      /real[- ]?time/i,
      /\blive\b/i,
      /(?<!rather than )\binstantly\b/i,
      /(?<!rather than )\bimmediately\b/i,
    ];
    const copy = [
      describeChangeSummary(summariseChanges([experiment(5), proposal('P1', 5)], 0)!),
      RECORD_ACTIVITY_CADENCE_CLAIM,
      RECORD_ACTIVITY_INPUT_SAFETY_CLAIM,
    ];
    for (const text of copy) {
      for (const pattern of forbidden) {
        expect(text, `"${text}" makes a latency claim`).not.toMatch(pattern);
      }
    }
    // And the cadence claim says what it IS instead: a periodic check, tied to the
    // tab being visible, explicitly NOT instant.
    expect(RECORD_ACTIVITY_CADENCE_CLAIM).toContain('rather than instantly');
  });

  it('tells the reader that what is on screen predates the change', () => {
    expect(describeChangeSummary(summariseChanges([experiment(5)], 0)!)).toContain(
      'loaded before that',
    );
  });
});

// --- the selectivity gate, at its REAL sites ---------------------------------

/** Deliberately NOT `import.meta.url`: under jsdom that is an http URL, not a file
 *  one. Duplicated from the sibling guards rather than exported, so no file can
 *  silently change another's scan. */
function locateSrcDir(): string {
  const candidates = [join(process.cwd(), 'src'), join(process.cwd(), 'apps', 'web', 'src')];
  const found = candidates.find((dir) => existsSync(join(dir, 'main.tsx')));
  if (found === undefined) throw new Error(`cannot locate apps/web/src from ${process.cwd()}`);
  return found;
}

const SRC_DIR = locateSrcDir();
const rawSource = (path: string) => readFileSync(join(SRC_DIR, path), 'utf8');

/** The three read-only record screens, which are the gate's only production sites. */
const GATE_SCREENS = [
  'screens/RecordWorkbench.tsx',
  'screens/EvidenceExplorer.tsx',
  'screens/ExportReadiness.tsx',
] as const;

describe('needsCanonicalRefetch — one gate, pinned where the screens actually use it', () => {
  it('decides on the record, its runs and unknown kinds — and never on a proposal', () => {
    const of = (over: Partial<Parameters<typeof needsCanonicalRefetch>[0]>) =>
      needsCanonicalRefetch({
        recordMoved: false,
        runIds: [],
        proposalIds: [],
        proposalStates: [],
        otherKinds: [],
        highestRev: 1,
        ...over,
      });

    expect(of({ recordMoved: true })).toBe(true);
    expect(of({ runIds: ['R1'] })).toBe(true);
    expect(of({ otherKinds: ['note'] })).toBe(true);
    // THE ONE FALSE CASE, and it is the whole reason the gate exists: none of the
    // three screens renders a proposal's content, so a proposal-only page is
    // announced and refetches nothing.
    expect(of({ proposalIds: ['P1'], proposalStates: ['open'] })).toBe(false);
    // …and `summariseChanges` would still have called that NEWS, which is what makes
    // these two different questions rather than one written twice.
    const proposalOnly = summariseChanges([proposal('P1', 5)], 0)!;
    expect(proposalOnly).not.toBeNull();
    expect(needsCanonicalRefetch(proposalOnly)).toBe(false);
  });

  it('is CALLED by all three screens, and its expression exists in exactly one file', () => {
    /*
     * THE FINDING THIS TEST EXISTS FOR. The predicate `summary.recordMoved ||
     * summary.runIds.length > 0 || summary.otherKinds.length > 0` was written out FOUR
     * times: once inline in each of the three screens, and a fourth time as a local
     * `gate` inside `change-feed-mount.test.tsx` — which is what the selectivity tests
     * actually exercised. So a screen whose gate drifted would have failed nothing:
     * the suite would have gone on proving that a COPY of the rule behaves.
     *
     * Two assertions, because either alone is escapable. Every screen must reach the
     * shared function (so the behaviour is the tested one), and the expression must
     * appear in no source file at all (so a fifth copy cannot quietly reappear beside
     * the call). `recordChanges.ts` holds the rule as the function BODY, which the
     * second assertion allows for by exempting that one file — and by requiring the
     * definition to be there, so the exemption cannot become a hole.
     */
    for (const screen of GATE_SCREENS) {
      const src = rawSource(screen);
      expect(src, `${screen} does not call the shared gate`).toContain(
        'needsCanonicalRefetch(summary)',
      );
      expect(src, `${screen} does not import the shared gate`).toMatch(
        /import \{[^}]*needsCanonicalRefetch/,
      );
    }

    // The inline expression, in any of the three screens or anywhere else it could be
    // re-copied. Matched loosely on whitespace so a reformat cannot hide one.
    const inline = /recordMoved\s*\|\|[\s\S]{0,80}?runIds\.length\s*>\s*0/;
    for (const screen of GATE_SCREENS) {
      expect(rawSource(screen), `${screen} still writes the gate out inline`).not.toMatch(
        inline,
      );
    }
    // And the ONE place it is allowed to live really does live there.
    expect(rawSource('lib/recordChanges.ts')).toMatch(inline);
  });
});
