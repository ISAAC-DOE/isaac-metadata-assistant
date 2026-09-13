/*
 * A TEST MAY NOT MOCK `localStorage` OR `sessionStorage` ON THE INSTANCE, BECAUSE IN
 * THIS ENVIRONMENT THAT SILENTLY DOES NOTHING.
 *
 * ── THE MEASUREMENT THIS EXISTS FOR ─────────────────────────────────────────
 *
 * Two forms look equivalent and are not. Measured directly in this project's own
 * vitest environment, calling `getItem` once through each store:
 *
 *     vi.spyOn(window.localStorage, 'getItem')      ->  INSTANCE_CALLS=0
 *     vi.spyOn(window.sessionStorage, 'getItem')    ->  SESSION_INSTANCE_CALLS=0
 *     vi.spyOn(Storage.prototype,  'getItem')       ->  PROTOTYPE_CALLS=1
 *
 * and, for plain assignment:
 *
 *     window.localStorage.getItem = () => { throw }  ->  MOCK_CALLED=false THREW=false
 *
 * An own-property assignment does not shadow `Storage.prototype`, and an instance spy
 * neither intercepts NOR RECORDS. So a test using either form is injecting no fault and
 * observing no call — while reading exactly like fault-injection coverage.
 *
 * ── WHY A TEST AND NOT A NOTE, and the two live instances that prove it ─────
 *
 * This was found twice on one day, in two files written by different slices:
 *
 * 1. `assistant-drawer-collapse.test.tsx` had TWO storage-refusing tests that had
 *    injected nothing since they were written, in BOTH polarities. The write-side one
 *    asserted `not.toThrow()` against a `setItem` that never threw. The defect was
 *    concealed by an ACCIDENTAL AGREEMENT: the code's `catch` returned the same value as
 *    its default, so the two matched without the mock ever working.
 *
 * 2. `current-user-contract.test.ts` — worse, because it is an IDENTITY contract. Its
 *    title is "sends no request and reads no cookie or browser storage when asked", and
 *    both storage assertions were TRUE BY CONSTRUCTION. Proved two-sided: with a mutant
 *    that made the disabled source read `localStorage`, the old spy form PASSED (exit 0)
 *    and the repaired form FAILED naming the store. Its own comment already articulated
 *    the principle — "THE SPY IS PROVED TO WORK, so 'not called' means something" — and
 *    applied it to `document.cookie` while leaving the two storage spies unproven in the
 *    same `try`. *Proving one spy is not proving the spies.*
 *
 * A prose note would not have found either. The form is mechanically detectable, so it
 * is mechanically refused.
 *
 * ── WHAT THIS DOES NOT CLAIM ────────────────────────────────────────────────
 *
 * It refuses a FORM, not an absence of coverage. A test can still mock the prototype and
 * assert nothing useful. The companion discipline — assert the spy was CALLED, so a
 * fault never injected is not mistaken for a fault tolerated — cannot be checked by
 * pattern and is enforced by review.
 */

import { describe, expect, it, vi } from 'vitest';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, resolve } from 'node:path';

const SRC = resolve(__dirname, '..');

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      out.push(...sourceFiles(full));
    } else if (/\.(ts|tsx)$/.test(entry)) {
      out.push(full);
    }
  }
  return out;
}

/** `-a`-equivalent: read bytes, so a NUL-bearing file cannot hide from this sweep. */
function text(file: string): string {
  return readFileSync(file, 'latin1');
}

/** The two ineffective forms, and deliberately not a search for the word "localStorage". */
const INSTANCE_SPY = /vi\s*\.\s*spyOn\s*\(\s*(?:window\s*\.\s*)?(?:local|session)Storage\s*,/g;
const INSTANCE_ASSIGN =
  /(?:window\s*\.\s*)?(?:local|session)Storage\s*\.\s*(?:getItem|setItem|removeItem|clear|key)\s*=[^=]/g;

/** Strip comments, so the prose ABOVE (and in the files that document the defect) is not
 *  counted as a live occurrence — the mistake a phantom-token sweep made earlier today,
 *  reporting four hits that were all inside the comments explaining the four fixes. */
function withoutComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
}

describe('storage mocks must actually intercept', () => {
  it('MEASURED HERE, not quoted: an instance spy records nothing and a prototype spy records', () => {
    /*
     * The premise of every assertion below, re-measured on each run rather than
     * trusted from the comment. If a future jsdom or vitest makes the instance form
     * work, THIS test fails first and says the ban can be lifted — which is the
     * difference between a guard and a superstition.
     */
    const inst = vi.spyOn(window.localStorage, 'getItem');
    window.localStorage.getItem('probe');
    const instCalls = inst.mock.calls.length;
    inst.mockRestore();

    const proto = vi.spyOn(Storage.prototype, 'getItem');
    window.localStorage.getItem('probe');
    window.sessionStorage.getItem('probe');
    const protoCalls = proto.mock.calls.length;
    proto.mockRestore();

    expect(
      { instCalls, protoCalls },
      'the instance/prototype asymmetry this guard rests on has changed — re-measure ' +
        'before trusting either form, and if the instance form now works, retire the ban',
    ).toEqual({ instCalls: 0, protoCalls: 2 });
  });

  /*
   * THE ONE EXEMPTION, AND IT IS THIS FILE. The premise test above uses the
   * instance form ON PURPOSE — it is the only way to measure that the form does
   * not work — so the sweep would flag the guard for containing the thing it
   * bans. Named explicitly rather than hidden behind a broader pattern, and kept
   * to ONE path so that widening it later is a visible decision.
   *
   * The exemption is bounded by the vacuity guard below: if the walk ever stops
   * seeing files, this exemption cannot make a broken sweep look clean.
   */
  const SELF = '__tests__/storage-mock-is-effective.test.ts';

  it('no file under src/ spies on a Storage INSTANCE or assigns over its methods', () => {
    const offenders: string[] = [];
    const files = sourceFiles(SRC);
    let exempted = 0;
    for (const file of files) {
      if (relative(SRC, file) === SELF) {
        exempted += 1;
        continue;
      }
      const body = withoutComments(text(file));
      for (const [label, re] of [
        ['instance spy', INSTANCE_SPY],
        ['assignment over a method', INSTANCE_ASSIGN],
      ] as const) {
        const hits = body.match(re);
        if (hits) offenders.push(`${relative(SRC, file)}: ${label} (${hits.length}) — ${hits[0]!.trim()}`);
      }
    }
    expect(
      offenders,
      'these mocks inject nothing in this environment and record nothing, so any ' +
        'assertion resting on them is true by construction. Use ' +
        'vi.spyOn(Storage.prototype, ...) and tell the stores apart by the receiver.',
    ).toEqual([]);
    // The exemption must have been USED, or its path has drifted and this sweep is
    // quietly exempting nothing while claiming to exempt one file.
    expect(exempted, `the self-exemption path no longer matches any file: ${SELF}`).toBe(1);
  });

  it('POLARITY CONTROL — the two ban patterns actually MATCH the forms they forbid', () => {
    /*
     * *** THIS FILE SHIPPED WITHOUT THIS TEST AND WAS THEREFORE UNPROVEN — the exact
     * failure it was written to prevent. Found by independent review (I-3). ***
     *
     * Measured: replacing BOTH patterns with `/ZZZ_NEVER_MATCHES/g` left the file
     * GREEN at 3 passed, exit 0. The vacuity guard below checks the WALK (>250
     * files, a prototype spy exists somewhere) and never the PREDICATES, and the one
     * file containing the banned form is the `SELF` exemption, which is skipped — so
     * nothing in the suite ever fed either regex a string it must catch.
     *
     * "A fault never injected is not a fault tolerated" is this file's own sentence,
     * one level up.
     */
    const MUST_CATCH_SPY = [
      "vi.spyOn(window.localStorage, 'getItem')",
      "vi.spyOn(localStorage, 'setItem')",
      "vi.spyOn(window.sessionStorage, 'removeItem')",
      "vi.spyOn( sessionStorage , 'clear')",
    ];
    for (const sample of MUST_CATCH_SPY) {
      expect(new RegExp(INSTANCE_SPY.source).test(sample), `INSTANCE_SPY missed: ${sample}`).toBe(
        true,
      );
    }

    const MUST_CATCH_ASSIGN = [
      "window.localStorage.getItem = () => null",
      'localStorage.setItem = fn',
      'window.sessionStorage.removeItem = noop',
      'sessionStorage.clear = () => {}',
    ];
    for (const sample of MUST_CATCH_ASSIGN) {
      expect(
        new RegExp(INSTANCE_ASSIGN.source).test(sample),
        `INSTANCE_ASSIGN missed: ${sample}`,
      ).toBe(true);
    }

    // ...AND THE WORKING FORM IS NOT CAUGHT, or the ban would forbid the remedy it
    // tells people to use — which is the other way to be useless.
    const MUST_NOT_CATCH = [
      "vi.spyOn(Storage.prototype, 'getItem')",
      "vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {})",
      // an equality COMPARISON is not an assignment
      'expect(window.localStorage.getItem("k") === null).toBe(true)',
    ];
    for (const sample of MUST_NOT_CATCH) {
      expect(new RegExp(INSTANCE_SPY.source).test(sample), `INSTANCE_SPY false-positive: ${sample}`).toBe(
        false,
      );
      expect(
        new RegExp(INSTANCE_ASSIGN.source).test(sample),
        `INSTANCE_ASSIGN false-positive: ${sample}`,
      ).toBe(false);
    }
  });

  it('VACUITY GUARD — the sweep actually reads a meaningful number of files', () => {
    // Without this, a broken `sourceFiles` walk returning [] would report a clean tree.
    const files = sourceFiles(SRC);
    expect(files.length).toBeGreaterThan(250);
    // ...and it can SEE the working form, so the patterns are looking at real content
    // rather than at a mis-rooted directory.
    const usesPrototypeSomewhere = files.some((f) =>
      /spyOn\(Storage\.prototype/.test(withoutComments(text(f))),
    );
    expect(usesPrototypeSomewhere, 'the sweep found no prototype spy anywhere — suspect the walk').toBe(true);
  });
});
