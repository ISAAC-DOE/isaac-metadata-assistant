/**
 * BASELINE AGGREGATE CONSISTENCY — the fast half of the accessibility baseline.
 *
 * This is a `vitest` file, not a Playwright spec, and the distinction is the
 * whole point of it. `specs/a11y-axe.spec.ts` needs a browser, a seeded
 * backend, a built frontend and five viewport projects; it costs ~30 minutes in
 * the `browser-a11y` CI job. The checks BELOW need none of that — they are
 * arithmetic and string shape over two committed data files — so they run in
 * the `frontend` job in milliseconds, on every pull request and on every push
 * to `main`.
 *
 * Everything here was previously enforced ONLY inside that 30-minute job, which
 * meant an inconsistent baseline was merged first and discovered afterwards.
 * See `../baseline-aggregate.ts` for the exact merge mechanism that made a
 * hand-maintained total go stale without a git conflict.
 *
 * Naming: `*.invariant.test.ts`, deliberately NOT `*.spec.ts`. Both Playwright
 * configs discover tests with `testMatch: /.*\.spec\.ts$/`, so this file is
 * invisible to them and can never be collected into a browser run.
 */

import { describe, expect, it } from 'vitest';

import {
  A11Y_BASELINE,
  A11Y_BASELINE_DARWIN_UNVERIFIED_NODES,
  A11Y_BASELINE_TOTAL_NODES,
  BASELINE_PLATFORMS,
  DARWIN_CARRIED_FORWARD,
  DARWIN_MEASUREMENT,
  PROJECT_IDS,
  SCAN_PROJECT_IDS,
  type BaselineEntry,
  type PlatformCount,
} from '../a11y-baseline';
import {
  LAYOUT_BASELINE,
  LAYOUT_BASELINE_TOTAL_INSTANCES,
  LAYOUT_SWEEP_WIDTH_IDS,
  type LayoutFinding,
} from '../layout-baseline';
import {
  a11yBaselineKeys,
  auditA11yWellFormedness,
  auditAggregate,
  auditDarwinProvenance,
  auditEntryShapes,
  auditBaselineAggregates,
  layoutBaselineKeys,
  splitBaselineKey,
  sumA11yNodes,
  sumLayoutInstances,
} from '../baseline-aggregate';
import { SURFACES } from '../surfaces';

describe('declared baseline totals equal the entries they total', () => {
  it('reports no mismatch for the committed baselines, on either platform', () => {
    const mismatches = auditBaselineAggregates(A11Y_BASELINE_TOTAL_NODES, LAYOUT_BASELINE_TOTAL_INSTANCES);
    expect(mismatches.map((m) => m.message).join('\n\n')).toBe('');
    expect(mismatches).toEqual([]);
  });

  // Stated separately from the combined audit above so a failure names WHICH
  // baseline drifted without the reader parsing a joined message.
  it('A11Y_BASELINE_TOTAL_NODES equals the sum of every recorded node count', () => {
    const computed = sumA11yNodes(A11Y_BASELINE);
    for (const platform of BASELINE_PLATFORMS) {
      expect(
        computed[platform],
        `A11Y_BASELINE_TOTAL_NODES.${platform} = ${A11Y_BASELINE_TOTAL_NODES[platform]}, entries sum to ${computed[platform]}`
      ).toBe(A11Y_BASELINE_TOTAL_NODES[platform]);
    }
  });

  it('LAYOUT_BASELINE_TOTAL_INSTANCES equals the sum of every recorded offender', () => {
    const computed = sumLayoutInstances(LAYOUT_BASELINE);
    for (const platform of BASELINE_PLATFORMS) {
      expect(computed[platform]).toBe(LAYOUT_BASELINE_TOTAL_INSTANCES[platform]);
    }
  });

  /*
   * The layout total is DERIVED in `layout-baseline.ts` (`totalInstancesOn`),
   * so the assertion above compares a derivation against an independent
   * re-derivation. That is worth keeping rather than dismissing as circular:
   * the two walk the `instances` shape by different code, and this is what
   * would catch the derivation being changed to skip per-platform objects —
   * exactly the bug `platformInstances` exists to prevent.
   */
  /*
   * This slot used to hold `expect(A11Y_TOTAL.darwin).not.toBe(LAYOUT_TOTAL.darwin)`,
   * titled "so neither test can pass by coincidence". Independent review was
   * right that it guarded nothing: each test above compares a declared total to
   * ITS OWN computed sum, so neither's passing depends on the two totals
   * differing — and the assertion would have gone red for free the day a11y debt
   * happened to land on the layout figure.
   *
   * Replaced with the property that title was reaching for: the two summers
   * really are different functions over different data, so one cannot be
   * standing in for the other.
   */
  it('the two summers are genuinely different functions, not one aliased twice', () => {
    expect(sumA11yNodes(A11Y_BASELINE)).not.toEqual(sumLayoutInstances(LAYOUT_BASELINE));
    // And each is non-trivial: a summer that always returned zero would satisfy
    // every "declared equals computed" test if the declared totals were zero too.
    expect(sumA11yNodes(A11Y_BASELINE).darwin).toBeGreaterThan(0);
    expect(sumLayoutInstances(LAYOUT_BASELINE).darwin).toBeGreaterThan(0);
  });

  // M4: the combined entry point is the one a future consistency script would
  // call, so at least one control must prove IT reports a real drift rather than
  // only the per-baseline helper underneath it.
  it('the COMBINED audit reports a stale a11y total (not only auditAggregate)', () => {
    const stale = {
      darwin: A11Y_BASELINE_TOTAL_NODES.darwin + 1,
      linux: A11Y_BASELINE_TOTAL_NODES.linux,
    };
    const mismatches = auditBaselineAggregates(stale, LAYOUT_BASELINE_TOTAL_INSTANCES);
    expect(mismatches).toHaveLength(1);
    expect(mismatches[0].platform).toBe('darwin');
    expect(mismatches[0].drift).toBe(-1);
    expect(mismatches[0].message).toContain('A11Y_BASELINE_TOTAL_NODES');
  });
});

/*
 * ── HOW MUCH OF THE DARWIN COLUMN IS A READING ──────────────────────────────
 *
 * `A11Y_BASELINE_TOTAL_NODES` catches a total that disagrees with its cells. It
 * cannot catch a CELL that disagrees with reality, and on the darwin half nothing
 * could: no CI job runs macOS (`grep -rn 'macos\|darwin' .github/workflows/` returns
 * nothing; every `runs-on:` is `ubuntu-latest`), so the only judge of that column is a
 * developer's laptop. 15 cells were wrong for eleven days as a result (~~14~~; corrected in
 * independent review 2026-08-27, see `baseline-aggregate.ts`) — a linux-only
 * transcription writes a linux delta into one half of a pair and leaves the other at a
 * number nothing has measured since, and the two halves look identical afterwards.
 *
 * `DARWIN_CARRIED_FORWARD` is the register that makes them look different, and these
 * tests are what stop the register itself rotting. They do NOT fail on unverified
 * debt — an unverified number is still the best number available and deleting it would
 * lose the ratchet. They fail when the register stops describing the file.
 */
describe('the darwin column says how much of itself is measured', () => {
  it('the declared unverified-node count equals the register it totals', () => {
    const provenance = auditDarwinProvenance(A11Y_BASELINE, DARWIN_CARRIED_FORWARD);
    expect(provenance.unverifiedNodes).toBe(A11Y_BASELINE_DARWIN_UNVERIFIED_NODES);
  });

  it('the declared darwin total is the one the provenance audit reads', () => {
    // Ties the two literals together, so `A11Y_BASELINE_DARWIN_UNVERIFIED_NODES`
    // can never be a fraction of a total that has since moved.
    const provenance = auditDarwinProvenance(A11Y_BASELINE, DARWIN_CARRIED_FORWARD);
    expect(provenance.totalNodes).toBe(A11Y_BASELINE_TOTAL_NODES.darwin);
  });

  it('every registered key names a cell that still exists', () => {
    // A cell can be deleted (its defect fixed) while its key survives here. The
    // register would then under-report without disagreeing with anything.
    const provenance = auditDarwinProvenance(A11Y_BASELINE, DARWIN_CARRIED_FORWARD);
    expect(provenance.unknownKeys).toEqual([]);
  });

  it('no registered key names a SCALAR cell', () => {
    // A scalar asserts BOTH columns with one number, so "its darwin half is carried
    // forward" is not a statement this file can make about it. Either the cell splits
    // or the key goes.
    const provenance = auditDarwinProvenance(A11Y_BASELINE, DARWIN_CARRIED_FORWARD);
    expect(provenance.scalarKeys).toEqual([]);
  });

  /*
   * THE CURRENT STATE, ASSERTED RATHER THAN ASSUMED — and it is the reason the four
   * tests above are not vacuous today. The register is EMPTY because the 2026-08-27
   * darwin run scanned all 168 cells and corrected 19 of them, not because nobody has
   * filled it in. If a later slice transcribes a linux figure and correctly registers
   * the cell, THIS test is the one that fails, and its failure is the prompt to update
   * both literals in the same edit.
   */
  it('reports that NO darwin node is currently carried forward', () => {
    const provenance = auditDarwinProvenance(A11Y_BASELINE, DARWIN_CARRIED_FORWARD);
    expect(provenance.unverifiedKeys).toEqual([]);
    expect(provenance.unverifiedFraction).toBe(0);
    expect(provenance.totalNodes).toBeGreaterThan(0);
  });

  /*
   * THE REGISTER IS OPT-IN, AND THAT IS THE HOLE THIS CLOSES.
   *
   * Independent review, 2026-08-27. Everything above is a ROT guard: it fails when the
   * register stops describing the file. Nothing fails when the register is simply not
   * WRITTEN — and that is precisely how the 15 fake splits arrived. A future author
   * transcribes a linux figure from CI, turns a scalar into `{ darwin: <old>, linux:
   * <new> }`, does not add the key here, and every test in this describe block stays
   * green: `unverifiedNodes` is still 0 because the register is still empty, and
   * `A11Y_BASELINE_TOTAL_NODES.darwin` does not move because the darwin half did not.
   * The register makes DECLARED debt visible; it cannot see UNDECLARED debt, which is
   * the only kind that has ever occurred here.
   *
   * A split is the shape that transcription creates, so the split SET is what to pin.
   * FOUR cells are genuinely per-platform today, all measured on both faces. A fifth
   * cannot appear without editing this list, and editing it is the moment to decide
   * whether the new darwin half was measured or carried forward — and, if carried
   * forward, to register it above.
   *
   * It is a ratchet over a LIST, not an assertion that four is correct forever: a real
   * font-metrics difference is welcome to become the fifth. What it forbids is one
   * arriving unremarked.
   *
   * ── IT WAS SIX, AND THIS EDIT IS THE PROCEDURE THE GUARD ASKS FOR ──────────────
   *
   * The discard/evidence-graph branch (2026-08-27) moved four of the six, and the list
   * is updated here in the same change, with provenance for each:
   *
   *   REMOVED  settings-explorer@desktop-1280x800  {darwin 44, linux 43} -> scalar 44
   *   REMOVED  settings-explorer@laptop-1024x768   {darwin 45, linux 43} -> scalar 44
   *   REMOVED  settings-explorer@width-390         {darwin 52, linux 51} -> scalar 52
   *
   *     All three COLLAPSE because linux caught up: the 71st operation
   *     (`POST /api/experiments/{id}/discard`) took each linux half to the darwin
   *     half's value — 44/44/52, transcribed from CI job 98470544956 — and a darwin run
   *     on 2026-08-27 re-read 44/44/52 on this host. Equal halves are rejected by
   *     `auditA11yWellFormedness`, so a scalar is not a choice here; it is the only
   *     legal encoding, and it means two measurements agreeing rather than one asserted.
   *
   *   ADDED    settings-explorer@mobile-375x812    scalar 50 -> {darwin 51, linux 50}
   *
   *     A REAL, MEASURED difference, and the one cell in this family where the two
   *     faces moved in opposite directions. CI job 98470544956 reported no change at
   *     `mobile-375x812`, so linux stays 50; the darwin run reads 51. The darwin half
   *     is measured, so it does NOT go in `DARWIN_CARRIED_FORWARD` and
   *     `A11Y_BASELINE_DARWIN_UNVERIFIED_NODES` stays 0.
   *
   * The seven `evidence-graph` cells changed in the same branch and are deliberately
   * NOT here: they are darwin-measured scalars, which assert both columns. That is the
   * file's existing encoding for a one-platform reading (see the note at those cells),
   * and minting a split for them would be the exact anti-pattern this guard forbids —
   * a linux half nothing measured.
   *
   * The persistence-truthfulness branch (2026-08-28) moved five more, taking the set
   * from four to seven. Both halves of every cell below were MEASURED at the same
   * commit `dad8715` — linux from CI run 33134705411 / job 98731972499, darwin from a
   * local macOS run on this host (Playwright 1.62.1 + bundled Chromium, backend started
   * as CI starts it) — so nothing here is carried forward and
   * `A11Y_BASELINE_DARWIN_UNVERIFIED_NODES` stays 0.
   *
   *   REMOVED  settings-explorer@mobile-375x812    {darwin 51, linux 50} -> scalar 66
   *
   *     COLLAPSES for the same reason the three above did in 2026-08-27: the two faces
   *     landed on the same number (66/66). Note this cell has now been a split and a
   *     scalar twice; that it oscillates is not instability in the app, it is a cell
   *     sitting one node from a wrap boundary on one face.
   *
   *   ADDED    settings-explorer@desktop-1280x800  scalar 44 -> {darwin 53, linux 54}
   *   ADDED    settings-explorer@laptop-1024x768   scalar 44 -> {darwin 53, linux 54}
   *   ADDED    settings-explorer@tablet-768x1024   scalar 58 -> {darwin 68, linux 69}
   *   ADDED    settings-explorer@width-320         scalar 51 -> {darwin 68, linux 67}
   *
   *     All four are real, measured, one-node platform differences. `width-320` is the
   *     one where DARWIN IS THE HIGHER HALF — the opposite direction from the other
   *     three — which is the concrete reason this branch did not transcribe the linux
   *     column across. Had it done so, four of these eight cells would have been wrong,
   *     and this one wrong in a direction no rule of thumb would have caught.
   *
   *   ── SECOND MOVE, SAME BRANCH, 2026-08-28 ─────────────────────────────────────
   *
   *   The review fix for #192 widened the `/api/about` description's paragraph 3 from
   *   2,054 to 2,550 characters WITHOUT changing its paragraph count (5 before, 5
   *   after, computed both times). All seven cells moved anyway. The coupling is
   *   therefore to description LENGTH, not to paragraph structure — the constraint
   *   written to prevent this churn was necessary but not sufficient, and that is the
   *   durable lesson: editing ANY OpenAPI description in this app re-baselines seven
   *   cells on two platforms, at roughly one CI round-trip each.
   *
   *   Both faces re-measured at `c75c42f`: darwin locally on this host, linux from CI
   *   job 99018666402. The split set churns again, in BOTH directions:
   *
   *     desktop-1280x800  {55, 55} -> SCALAR 55   split collapses
   *     width-320         {73, 73} -> SCALAR 73   split collapses
   *     mobile-375x812    scalar   -> {71, 72}    scalar becomes split
   *     width-390         scalar   -> {73, 72}    scalar becomes split, DARWIN HIGHER
   *     zoom-200          scalar   -> {67, 68}    scalar becomes split
   *     laptop-1024x768   {55, 57}                a gap of TWO
   *     tablet-768x1024   {71, 72}
   *
   *   Two of these refute rules of thumb this file has entertained before.
   *   `laptop-1024x768` differs by TWO, so "every one by exactly +/-1, the signature of
   *   a single wrap boundary" fails again. And `width-390` has darwin as the HIGHER
   *   half, so the direction is not consistent either. Nothing here was predicted from
   *   the other column; every number was read off a run.
   *
   *     The whole family moved for ONE cause, established by controlled experiment and
   *     not inferred: the `GET /api/about` OpenAPI `description=` grew from 2 paragraphs
   *     to ~~6~~ **5** — corrected 2026-08-28, having been asserted rather than counted;
   *     `len([p for p in description.split('\n\n') if p.strip()])` reads 2 on
   *     `origin/main` and 5 here — and the Endpoint Explorer renders operation
   *     descriptions as
   *     `<p class="api-docs-description">`. Reverting `routes.py` alone to `origin/main`,
   *     with every frontend change still applied, put the surface back to its old
   *     numbers. A BACKEND DOCSTRING IS RENDERED PRODUCT TEXT.
   *
   *     THE CONTROL WAS RUN FOR ALL SEVEN CELLS, not one. An earlier revision of this
   *     paragraph reported the experiment on `desktop-1280x800` and asserted the other
   *     six shared its cause; an independent review flagged that as inference wearing
   *     the word "measured", by the same standard this file applies to a darwin half.
   *     The control was therefore re-run across the whole family on 2026-08-28, and
   *     every one of the seven returned to its exact pre-change value — tablet 68 -> 58,
   *     mobile 66 -> 51, zoom-200 64 -> 53, and so on for the rest. Each of those is the
   *     number this file held before the change, so the attribution is now a
   *     measurement on all seven and not an extrapolation from one.
   *
   *   ── THIRD MOVE, 2026-08-29, AND THE ONLY ONE WHERE HALF THE SET IS *NOT*
   *      MEASURED ON BOTH FACES ────────────────────────────────────────────────
   *
   *   The base commit `542d757` edited `routes.py`'s `GET /api/about` description AND
   *   `settingsContent.ts` and did NOT re-baseline — the third time in four days that an
   *   OpenAPI description moved these seven cells, and the second time it was committed
   *   without them. The 2026-08-29 slice measured DARWIN only (a local macOS sweep, and
   *   the settings-explorer figures additionally reproduced in an isolated
   *   `-g "Endpoint Explorer"` re-run) and, per this file's own rule, did not touch the
   *   linux column: this is a TEXT-LENGTH change, the wrap-dependent case where deriving
   *   the other platform is forbidden.
   *
   *     desktop-1280x800  scalar 55 -> {darwin 57, linux 55}   scalar becomes split
   *     width-320         scalar 73 -> {darwin 76, linux 73}   scalar becomes split
   *     mobile-375x812    {71, 72}  -> {darwin 73, linux 72}
   *     zoom-200          {67, 68}  -> {darwin 70, linux 68}
   *     width-390         {73, 72}  -> {darwin 74, linux 72}
   *     laptop-1024x768   {55, 57}  -> SCALAR 57                split collapses
   *     tablet-768x1024   {71, 72}  -> SCALAR 72                split collapses
   *
   *   READ THE FIVE SPLITS DIFFERENTLY FROM EVERY OTHER SPLIT IN THIS FILE. The name of
   *   this test says the set is "measured on both faces", and for these five that is NOT
   *   true: the darwin half is a 2026-08-29 reading and the linux half is a 2026-08-28
   *   reading of a source state that has since changed. They are KNOWN-STALE linux
   *   halves, not measured platform differences, and CI will report five GREW messages
   *   naming its own figures — transcribe those.
   *
   *   THE REGISTER THAT WOULD RECORD THIS DOES NOT EXIST, and that is stated rather than
   *   invented around. `DARWIN_CARRIED_FORWARD` exists because the usual direction is
   *   "CI handed us a linux figure and the darwin half was left standing". This is the
   *   MIRROR case and there is no `LINUX_CARRIED_FORWARD`. Adding one is a real change
   *   to this file's machinery and was out of that slice's scope; the file's own
   *   precedent for the mirror case is prose at the cells (see the 2026-08-03 note,
   *   "THE LINUX COLUMN IN THESE 26 ENTRIES IS THE PRE-FIX NUMBER AND IS KNOWN TO BE TOO
   *   HIGH"), and that is what was done. `A11Y_BASELINE_DARWIN_UNVERIFIED_NODES` stays
   *   0, correctly: every DARWIN half here is a reading.
   *
   *   THE TWO COLLAPSES ARE NOT MEASUREMENTS EITHER, and they are the sharper case. At
   *   laptop and tablet the NEW darwin number happens to equal the OLD linux number (57
   *   and 72), and `auditEntryShapes` rejects a per-platform pair whose halves are equal
   *   — so a scalar was the only legal expression, and a scalar in this file MEANS
   *   "identical on both platforms". Those two cells therefore assert a linux value no
   *   run has produced since `542d757`. That is the type system's limitation, already
   *   recorded in `a11y-baseline.ts`'s 2026-08-04 note, and not a claim about linux.
   */
  it('the set of per-platform SPLIT cells is exactly the eight recorded, and no others', () => {
    const splits: string[] = [];
    for (const entry of A11Y_BASELINE) {
      for (const [key, count] of Object.entries(entry.counts)) {
        if (typeof count !== 'number') splits.push(`${entry.rule} @ ${key}`);
      }
    }
    expect(
      splits.sort(),
      'a `{ darwin, linux }` cell asserts that the two platforms were MEASURED separately. ' +
        'If you are adding one because CI reported a linux figure and you left the darwin ' +
        'half standing, that half is carried forward: add the key to DARWIN_CARRIED_FORWARD ' +
        'and move A11Y_BASELINE_DARWIN_UNVERIFIED_NODES in the same edit. If you measured ' +
        'both, add it here and say where the darwin reading came from.'
    ).toEqual(
      [
        'color-contrast @ memory-graph@zoom-200',
        'color-contrast @ settings-about@width-320',
        // The five below carry a MEASURED darwin half beside a KNOWN-STALE linux one
        // (2026-08-29; see the note above). They are not platform differences yet.
        'color-contrast @ settings-explorer@desktop-1280x800',
        'color-contrast @ settings-explorer@mobile-375x812',
        'color-contrast @ settings-explorer@width-320',
        'color-contrast @ settings-explorer@width-390',
        'color-contrast @ settings-explorer@zoom-200',
        'color-contrast @ validator@zoom-200',
      ].sort()
    );
  });

  it('records where the darwin column came from', () => {
    expect(DARWIN_MEASUREMENT.runs).toBeGreaterThanOrEqual(2);
    expect(DARWIN_MEASUREMENT.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(DARWIN_MEASUREMENT.command).toContain('a11y-axe.spec.ts');
    expect(DARWIN_MEASUREMENT.command).toContain('a11y-narrow.spec.ts');
  });

  /*
   * NEGATIVE CONTROLS. Four assertions of `[]` and a `0` prove nothing on their own —
   * a function that returned empty for every input would satisfy all of them. Each
   * control below feeds the SAME function a register that really does name something
   * and asserts the exact reading changes.
   */
  it('counts the DARWIN half of a registered split, not the linux half', () => {
    const entries: readonly BaselineEntry[] = [
      {
        rule: 'color-contrast',
        impact: 'serious',
        note: 'Synthetic entry used only by this control; it describes no real defect.',
        targetPattern: '^synthetic$',
        counts: { 'fake@desktop-1280x800': { darwin: 7, linux: 90 } },
      },
    ];
    const provenance = auditDarwinProvenance(entries, ['fake@desktop-1280x800']);
    expect(provenance.totalNodes).toBe(7);
    expect(provenance.unverifiedNodes).toBe(7);
    expect(provenance.unverifiedFraction).toBe(1);
    expect(provenance.unknownKeys).toEqual([]);
    expect(provenance.scalarKeys).toEqual([]);
  });

  it('reports a registered key that names no cell', () => {
    const entries: readonly BaselineEntry[] = [
      {
        rule: 'color-contrast',
        impact: 'serious',
        note: 'Synthetic entry used only by this control; it describes no real defect.',
        targetPattern: '^synthetic$',
        counts: { 'fake@desktop-1280x800': { darwin: 7, linux: 90 } },
      },
    ];
    const provenance = auditDarwinProvenance(entries, ['gone@zoom-200']);
    expect(provenance.unknownKeys).toEqual(['gone@zoom-200']);
    expect(provenance.unverifiedKeys).toEqual([]);
    expect(provenance.unverifiedNodes).toBe(0);
  });

  it('reports a registered key whose cell is a scalar', () => {
    const entries: readonly BaselineEntry[] = [
      {
        rule: 'color-contrast',
        impact: 'serious',
        note: 'Synthetic entry used only by this control; it describes no real defect.',
        targetPattern: '^synthetic$',
        counts: { 'fake@desktop-1280x800': 11 },
      },
    ];
    const provenance = auditDarwinProvenance(entries, ['fake@desktop-1280x800']);
    expect(provenance.scalarKeys).toEqual(['fake@desktop-1280x800']);
    expect(provenance.unverifiedNodes).toBe(11);
  });

  it('reports a fraction between 0 and 1 when only part of the column is unverified', () => {
    const entries: readonly BaselineEntry[] = [
      {
        rule: 'color-contrast',
        impact: 'serious',
        note: 'Synthetic entry used only by this control; it describes no real defect.',
        targetPattern: '^synthetic$',
        counts: {
          'fake@desktop-1280x800': { darwin: 3, linux: 4 },
          'fake@zoom-200': { darwin: 9, linux: 4 },
        },
      },
    ];
    const provenance = auditDarwinProvenance(entries, ['fake@desktop-1280x800']);
    expect(provenance.totalNodes).toBe(12);
    expect(provenance.unverifiedNodes).toBe(3);
    expect(provenance.unverifiedFraction).toBeCloseTo(0.25, 10);
  });
});

/*
 * ── NEGATIVE CONTROLS ───────────────────────────────────────────────────────
 *
 * A consistency check that has only ever been run against a consistent input
 * has not been shown to detect anything. Each control below feeds the SAME
 * function the suite uses a deliberately broken input and asserts the exact
 * defect is reported — including the specific two-branch merge that motivated
 * this file.
 */
describe('the aggregate checker detects the failures it claims to', () => {
  // `PlatformCount`, not `number`: two of the controls below feed a genuine
  // `{ darwin, linux }` pair, which is the shape most likely to be summed by
  // array position or by the wrong column.
  const entry = (rule: string, counts: Record<string, PlatformCount>): BaselineEntry => ({
    rule,
    impact: 'serious',
    note: 'Synthetic entry used only by the negative controls in this file; it describes no real defect.',
    targetPattern: '^synthetic$',
    counts,
  });

  it('THE MERGE COLLISION: two branches, two disjoint additions, one increment', () => {
    // `main` before either branch: one entry, three nodes, total 3.
    const base = [entry('color-contrast', { 'alpha@desktop-1280x800': 3 })];
    const baseTotal = sumA11yNodes(base);
    expect(baseTotal.darwin).toBe(3);

    // Branch A adds one node on a NEW pair and raises the total 3 -> 4.
    // Branch B adds one node on a DIFFERENT new pair and also writes 4 —
    // the same literal, for an unrelated reason.
    const declaredByBothBranches = { darwin: 4, linux: 4 };

    // git merges the identical one-line change without a conflict, and the two
    // entry additions touch different keys so they merge cleanly too. The
    // merged file holds BOTH additions and ONE increment.
    const merged = [
      entry('color-contrast', {
        'alpha@desktop-1280x800': 3,
        'beta@desktop-1280x800': 1, // from branch A
        'gamma@desktop-1280x800': 1, // from branch B
      }),
    ];

    const mismatches = auditAggregate('A11Y_BASELINE_TOTAL_NODES', declaredByBothBranches, sumA11yNodes(merged));

    // Both platforms are wrong by exactly one — the increment that was lost.
    expect(mismatches).toHaveLength(BASELINE_PLATFORMS.length);
    for (const m of mismatches) {
      expect(m.declared).toBe(4);
      expect(m.computed).toBe(5);
      expect(m.drift).toBe(1);
      // The message must name the merge, because a reader who has just seen a
      // clean merge will not otherwise suspect one.
      expect(m.message).toContain('MERGE');
      expect(m.message).toContain('Raise the total to 5');
    }
  });

  it('detects a total left BEHIND its entries (debt added, number not updated)', () => {
    const mismatches = auditAggregate(
      'A11Y_BASELINE_TOTAL_NODES',
      { darwin: 10, linux: 10 },
      sumA11yNodes([entry('color-contrast', { 'alpha@desktop-1280x800': 12 })])
    );
    expect(mismatches.map((m) => m.drift)).toEqual([2, 2]);
  });

  it('detects a total left AHEAD of its entries (defect fixed, number not lowered)', () => {
    const mismatches = auditAggregate(
      'A11Y_BASELINE_TOTAL_NODES',
      { darwin: 10, linux: 10 },
      sumA11yNodes([entry('color-contrast', { 'alpha@desktop-1280x800': 7 })])
    );
    expect(mismatches.map((m) => m.drift)).toEqual([-3, -3]);
    for (const m of mismatches) expect(m.message).toContain('Set the total to 7');
  });

  it('detects a drift on ONE platform only, and names that platform alone', () => {
    const mismatches = auditAggregate(
      'A11Y_BASELINE_TOTAL_NODES',
      { darwin: 5, linux: 5 },
      sumA11yNodes([entry('color-contrast', { 'alpha@desktop-1280x800': { darwin: 5, linux: 6 } })])
    );
    expect(mismatches).toHaveLength(1);
    expect(mismatches[0].platform).toBe('linux');
    expect(mismatches[0].drift).toBe(1);
  });

  it('diagnoses a MISSING PLATFORM as a shape defect, not as a stale total', () => {
    // A per-platform count with one half missing makes the sum `NaN`. The
    // arithmetic branch would print "Set the total to NaN" — advice that leaves
    // the suite red forever, because `NaN !== NaN`. It must diagnose instead.
    const broken = [
      entry('color-contrast', {
        // Deliberately malformed: `linux` is absent. Cast because the type
        // system correctly forbids writing this, which is exactly why a test
        // has to prove what happens when someone does it anyway.
        'alpha@desktop-1280x800': { darwin: 3 } as unknown as PlatformCount,
      }),
    ];
    const mismatches = auditAggregate('A11Y_BASELINE_TOTAL_NODES', { darwin: 3, linux: 3 }, sumA11yNodes(broken));
    expect(mismatches).toHaveLength(1);
    expect(mismatches[0].platform).toBe('linux');
    expect(Number.isFinite(mismatches[0].computed)).toBe(false);
    expect(mismatches[0].message).toContain('SHAPE defect');
    expect(mismatches[0].message).toContain('missing the "linux" key');
    // The misleading advice must NOT appear.
    expect(mismatches[0].message).not.toContain('Set the total to NaN');
  });

  it('counts per-platform pairs on the right side of the pair, not by array position', () => {
    const totals = sumA11yNodes([
      entry('color-contrast', {
        'alpha@desktop-1280x800': { darwin: 2, linux: 9 },
        'beta@desktop-1280x800': 1,
      }),
    ]);
    expect(totals).toEqual({ darwin: 3, linux: 10 });
  });

  it('sums layout offenders by LIST LENGTH per platform, including per-platform lists', () => {
    const findings: LayoutFinding[] = [
      {
        id: 'SYNTHETIC-01',
        kind: 'clipped',
        selector: 'synthetic',
        note: 'Synthetic finding used only by the negative controls in this file.',
        instances: {
          'alpha@desktop-1280x800': ['a', 'b'],
          'beta@desktop-1280x800': { darwin: ['a'], linux: ['a', 'b', 'c'] },
        },
      },
    ];
    expect(sumLayoutInstances(findings)).toEqual({ darwin: 3, linux: 5 });
  });
});

/*
 * ── SHAPE CHECKS THAT NEEDED NO BROWSER AND WERE WAITING FOR ONE ────────────
 *
 * These duplicate nothing: `specs/a11y-axe.spec.ts` validates keys against the
 * scan grid, but only inside the browser job. A typo'd surface id is a data
 * error in a committed file and there is no reason its rejection should cost
 * half an hour. The browser test keeps its own copies — it must, because it is
 * the thing that runs the scan — and these run first and fail sooner.
 */
/*
 * ── THE REST OF THE WELL-FORMEDNESS TEST, WHICH ALSO NEEDED NO BROWSER ──────
 *
 * The first version of this file moved ONE check out of the ~30-minute
 * `browser-a11y` job. Independent review pointed out that its own justification
 * — "there is no reason a data error should cost half an hour" — applied just as
 * well to everything else in `specs/a11y-axe.spec.ts`'s well-formedness test,
 * which stayed behind: duplicate rule names, the `note.length` floor, empty
 * `counts`, `targetPattern` regex validity, hex `foregrounds`, per-platform
 * completeness, and the RATCHET INVERSION — arguably the most valuable check in
 * the file, and one that touches no page at all.
 *
 * `auditA11yWellFormedness` is now the single implementation of all of it, and
 * the browser spec calls the same function. Two runners, one implementation.
 */
describe('the a11y baseline file is well-formed', () => {
  it('reports no problem for the committed baseline', () => {
    expect(auditA11yWellFormedness().join('\n')).toBe('');
  });

  /*
   * NEGATIVE CONTROLS for the shape half. `auditEntryShapes` takes its inputs
   * rather than reading the module constants precisely so these can exist — a
   * checker only ever run against valid data has not been shown to detect
   * anything, which is the same lesson `sumA11yNodes` was parameterized for.
   *
   * The ratchet-inversion half of the audit is NOT covered here and cannot be:
   * `baselineVerdict` reads the module-level `A11Y_BASELINE` itself, so feeding
   * a different entry list would compare one baseline's counts against
   * another's verdicts. That limit is stated at `auditEntryShapes` rather than
   * hidden.
   */
  const SURFACE = new Set(['record-detail']);
  const PROJECT = new Set(['desktop-1280x800']);
  const good = {
    rule: 'color-contrast',
    impact: 'serious' as const,
    note: 'A synthetic entry long enough to clear the sixty-character explanation floor this audit imposes.',
    targetPattern: '^synthetic$',
    counts: { 'record-detail@desktop-1280x800': 3 },
  };

  const only = (over: Partial<typeof good>) =>
    auditEntryShapes([{ ...good, ...over } as BaselineEntry], SURFACE, PROJECT);

  it('accepts a well-formed synthetic entry, so the rejections below mean something', () => {
    expect(only({})).toEqual([]);
  });

  it.each([
    ['an invalid rule id', { rule: 'Color Contrast' }, 'not a valid axe rule id'],
    ['a too-short note', { note: 'too short' }, 'must carry a real explanation'],
    ['no recorded pair', { counts: {} }, 'records no (surface, project) pair'],
    ['neither targetPattern nor foregrounds', { targetPattern: undefined }, 'must pin WHICH nodes fail'],
    ['an invalid targetPattern regex', { targetPattern: '([' }, 'invalid targetPattern regex'],
    ['a non-hex foreground', { targetPattern: undefined, foregrounds: ['#GGGGGG'] }, 'not lower-case hex'],
    ['an unknown surface', { counts: { 'no-such-surface@desktop-1280x800': 1 } }, 'unknown surface'],
    ['an unknown project', { counts: { 'record-detail@no-such-project': 1 } }, 'unknown project'],
    ['a malformed key', { counts: { 'nokeyseparator': 1 } }, 'is not surfaceId@projectId'],
    ['a zero count', { counts: { 'record-detail@desktop-1280x800': 0 } }, 'must be a positive integer'],
    [
      'a per-platform pair missing a platform',
      { counts: { 'record-detail@desktop-1280x800': { darwin: 3 } as unknown as PlatformCount } },
      'has no "linux" number',
    ],
    [
      'a per-platform pair whose halves are equal',
      { counts: { 'record-detail@desktop-1280x800': { darwin: 3, linux: 3 } } },
      'both numbers are the same',
    ],
  ])('rejects %s', (_label, override, expected) => {
    const found = only(override as Partial<typeof good>);
    expect(found.join('\n')).toContain(expected);
  });

  it('rejects a duplicate rule entry across two entries', () => {
    const found = auditEntryShapes([good as BaselineEntry, good as BaselineEntry], SURFACE, PROJECT);
    expect(found.join('\n')).toContain('duplicate baseline entry');
  });

  it('checks a non-trivial number of things, so an empty result means something', () => {
    // A guard against the audit silently becoming a no-op — e.g. if
    // `A11Y_BASELINE` were emptied, or an early `return` crept in. The floor is
    // deliberately far below the real figure rather than pinned to it, so
    // ordinary baseline edits do not churn this number.
    expect(A11Y_BASELINE.length).toBeGreaterThan(0);
    expect(a11yBaselineKeys().length).toBeGreaterThan(50);
  });
});

describe('no layout baseline entry tolerates nothing on either platform', () => {
  /*
   * REVIEW FINDING, 2026-08-25. `fixedOnDarwin` in `e2e/layout-baseline.ts` was
   * fully variadic, so `fixedOnDarwin()` typechecked and produced
   * `{darwin: [], linux: []}` — a key that tolerates nothing anywhere. That is
   * not "fixed on darwin"; it is a dead key that reads as a recorded finding, and
   * nothing rejected it. The helper's first argument is now REQUIRED, which closes
   * the helper route. This closes the OTHER route: a pair written out by hand.
   *
   * Note what an empty pair is NOT: `darwin: []` beside a non-empty `linux` is
   * the whole point of `fixedOnDarwin` and is legal. Only empty on BOTH sides is
   * a dead key.
   */
  const emptyOnBothPlatforms = (finding: LayoutFinding, key: string): boolean => {
    const instances = finding.instances[key];
    if (Array.isArray(instances)) return instances.length === 0;
    const perPlatform = instances as Record<(typeof BASELINE_PLATFORMS)[number], readonly string[]>;
    return BASELINE_PLATFORMS.every((platform) => perPlatform[platform].length === 0);
  };

  it('the committed LAYOUT_BASELINE has no such entry', () => {
    const dead: string[] = [];
    for (const finding of LAYOUT_BASELINE) {
      for (const key of Object.keys(finding.instances)) {
        if (emptyOnBothPlatforms(finding, key)) dead.push(`${finding.id} / ${key}`);
      }
    }
    expect(
      dead,
      'an entry that tolerates nothing on either platform excuses nothing and asserts nothing — ' +
        'delete the key instead of recording an empty one:\n' +
        dead.join('\n')
    ).toEqual([]);
  });

  it('and the check rejects one, so the empty result above means something', () => {
    const synthetic = {
      ...LAYOUT_BASELINE[0],
      instances: { 'record-detail@width-320': { darwin: [], linux: [] } },
    } as unknown as LayoutFinding;
    expect(emptyOnBothPlatforms(synthetic, 'record-detail@width-320')).toBe(true);
    // A bare empty array is the same defect written the other way.
    const bare = {
      ...LAYOUT_BASELINE[0],
      instances: { 'record-detail@width-320': [] },
    } as unknown as LayoutFinding;
    expect(emptyOnBothPlatforms(bare, 'record-detail@width-320')).toBe(true);
    // And `darwin: []` beside a real linux list is legal, not a defect.
    const fixedOnDarwinShape = {
      ...LAYOUT_BASELINE[0],
      instances: { 'record-detail@width-320': { darwin: [], linux: ['div.screen-card'] } },
    } as unknown as LayoutFinding;
    expect(emptyOnBothPlatforms(fixedOnDarwinShape, 'record-detail@width-320')).toBe(false);
  });
});

describe('every baseline key names a real surface and a real scan project', () => {
  const surfaceIds = new Set(SURFACES.map((s) => s.id));
  // The two grids, kept apart on purpose — see `a11yBaselineKeys` for why a
  // union would be a check that cannot fail.
  const a11yProjects = new Set<string>(SCAN_PROJECT_IDS);
  const layoutProjects = new Set<string>([...PROJECT_IDS, ...LAYOUT_SWEEP_WIDTH_IDS]);

  const allKeys = () => [...a11yBaselineKeys(), ...layoutBaselineKeys()];

  const badSurfaces = (keys: readonly string[]) =>
    keys
      .map((key) => ({ key, parts: splitBaselineKey(key) }))
      .filter(({ parts }) => parts && !surfaceIds.has(parts.surfaceId))
      .map(({ key }) => key);

  const badProjects = (keys: readonly string[], legal: ReadonlySet<string>) =>
    keys
      .map((key) => ({ key, parts: splitBaselineKey(key) }))
      .filter(({ parts }) => parts && !legal.has(parts.projectId))
      .map(({ key }) => key);

  it('parses every key into a surface half and a project half', () => {
    for (const key of allKeys()) {
      expect(splitBaselineKey(key), `"${key}" is not a valid surfaceId@projectId key`).not.toBeNull();
    }
  });

  it('names only surfaces that e2e/surfaces.ts actually scans', () => {
    expect(
      badSurfaces(allKeys()),
      `these baseline keys name a surface id that does not exist in e2e/surfaces.ts, so they can ` +
        `never be reached by a scan and silently tolerate nothing while looking like coverage`
    ).toEqual([]);
  });

  it('keys the a11y baseline only against projects the axe sweep runs', () => {
    expect(
      badProjects(a11yBaselineKeys(), a11yProjects),
      `SCAN_PROJECT_IDS is the axe grid: the five Playwright projects plus width-390 and ` +
        `width-320. A key naming any other width belongs to the layout sweep, not here.`
    ).toEqual([]);
  });

  it('keys the layout baseline only against projects or widths the layout sweep runs', () => {
    expect(
      badProjects(layoutBaselineKeys(), layoutProjects),
      `The layout grid is the five Playwright projects (layout-responsive.spec.ts) plus ` +
        `LAYOUT_SWEEP_WIDTH_IDS (layout-widths.spec.ts).`
    ).toEqual([]);
  });

  it('the two grids genuinely differ, so neither check can pass by sharing the other s list', () => {
    // Five width ids are legal for LAYOUT and for nothing else. Three of them
    // (1280/1024/768) are widths the axe sweep also covers, but under its
    // PROJECT names (`desktop-1280x800`, …) — which is precisely the collision
    // the `width-` namespacing exists to prevent, so they are correctly absent
    // from the axe grid. 375 and 640 are swept for layout alone.
    //
    // If this list ever empties, the two checks above have collapsed into one
    // and stopped distinguishing the mistake they exist to catch.
    expect([...layoutProjects].filter((p) => !a11yProjects.has(p)).sort()).toEqual([
      'width-1024',
      'width-1280',
      'width-375',
      'width-640',
      'width-768',
    ]);
  });

  it('keeps the scan grid the two extra narrow widths wide', () => {
    // Mirrors the tail of the browser well-formedness test. If a sixth
    // viewport project is added, every recorded count needs a reading for it
    // and this fails immediately rather than after a full sweep.
    expect(SCAN_PROJECT_IDS.length).toBe(PROJECT_IDS.length + 2);
  });
});
