/**
 * THE ONE IMPLEMENTATION of "do the declared baseline totals still equal the
 * sum of the entries they claim to total".
 *
 * ── The defect this module exists to close ──────────────────────────────────
 *
 * `A11Y_BASELINE_TOTAL_NODES` is a hand-written scalar per platform. Every
 * per-cell count beside it is a MEASUREMENT — the axe scan reproduces it or the
 * build fails — but the total is ARITHMETIC, and arithmetic is the only thing
 * in either baseline file that can be wrong without any run disagreeing with it.
 *
 * That matters because of how the number is edited. Two branches open against
 * the same `main`; each adds a disjoint set of entry keys; each raises the total
 * to account for its own addition. When the deltas happen to be EQUAL, both
 * branches write the SAME resulting literal — and git merges identical changes
 * to one line without a conflict. The entry maps merge cleanly too, because the
 * keys are disjoint. The merged file therefore carries BOTH sets of new entries
 * and only ONE of the two increments, and nothing in the text of the merge
 * announces it.
 *
 * Two further properties made that survivable for longer than it should have:
 *
 *   1. GitHub does not re-run a pull request's checks when its BASE advances.
 *      Each branch's CI validated a `main` that did not yet contain the other,
 *      so the inconsistent state was never executed before the merge button.
 *   2. The only guard was `specs/a11y-axe.spec.ts`'s well-formedness test,
 *      which lives in the ~30-minute `browser-a11y` job. So the first signal
 *      arrived after the merge, on `main`, half an hour later.
 *
 * Neither property is a bug in the baseline. Together with a hand-maintained
 * aggregate they are what turned a bookkeeping slip into a red `main`.
 *
 * ── What is done about it, and what is deliberately NOT ─────────────────────
 *
 * The sum-versus-declared check is not new; `specs/a11y-axe.spec.ts` has always
 * had it, inline. What is new is that the check now lives HERE, as a pure
 * function over data, with no browser and no page — so it can also run in the
 * fast `vitest` suite, in the `frontend` CI job, on every pull request and on
 * every push to `main`. Detection was already complete; the latency was the
 * defect.
 *
 * TWO NUMBERS, STATED AS MEASURED. The check itself is ~6 ms locally and ~26 ms
 * in CI. The SIGNAL costs whatever its job costs: `frontend tests and build`
 * measured 3m06s and 3m48s on recent `main` runs, against `browser accessibility
 * and responsive baseline` at 26m13s and 26m42s. ~26 minutes to ~4, about 7x.
 * An earlier revision of this header said "in milliseconds" in a sentence about
 * feedback latency, which conflated the two.
 *
 * ON PLAYWRIGHT, corrected: an earlier revision claimed "no Playwright" in this
 * module's dependency chain. `e2e/surfaces.ts:46` DOES reference
 * `@playwright/test`. The true and sufficient claim is narrower — it is a
 * TYPE-ONLY inline `import(...)` in a type position, erased at transform time,
 * and there is no value import anywhere in the chain.
 * `src/__tests__/baseline-invariant-wiring.test.ts` asserts that, so a future
 * value import fails there rather than in CI only.
 *
 * The scan spec now calls this module instead of re-summing inline, so there is
 * exactly ONE implementation of the invariant rather than two that can drift.
 *
 * What is NOT done: the declared literal is not deleted. Deriving it — the way
 * `LAYOUT_BASELINE_TOTAL_INSTANCES` already derives its own — would make the
 * class of defect structurally impossible, and that was seriously considered.
 * It is rejected because the literal is the only artefact in the repository
 * that makes a DEBT INCREASE visible in a diff. Every per-cell count is a
 * ratchet against a measurement, so no growth can sneak past a scan; but a
 * slice that ADDS entries for a new surface adds new tolerated debt, and a
 * derived total would absorb that silently. Keeping the number and checking it
 * fast preserves the review signal and removes the slow feedback that made the
 * slip expensive.
 *
 * ── The residual risk, stated rather than implied ───────────────────────────
 *
 * A fast check still runs only when CI runs. If a pull request is merged
 * without its checks having seen the current base, this invariant fails on
 * `main` rather than on the pull request.
 *
 * The setting that would close that gap is "Require branches to be up to date
 * before merging", and `docs/branch-protection-request.md:74-81` DECLINES to
 * request it, for a reason that is measured rather than stylistic: the
 * generated memory snapshot already forces every open PR to regenerate after
 * every merge, and the rule would add a full ~30-minute CI re-run on every open
 * PR on top of that. This module is not an argument for reversing that. It is
 * the cheap half of the same protection — the half that costs milliseconds —
 * and it narrows what the expensive half would still buy.
 */

import {
  A11Y_BASELINE,
  BASELINE_PLATFORMS,
  PROJECT_IDS,
  SCAN_PROJECT_IDS,
  allScanPairs,
  baselineKey,
  baselineVerdict,
  expectedNodeCount,
  isBaselined,
  platformCount,
  type BaselineEntry,
  type BaselinePlatform,
} from './a11y-baseline';
import { SURFACES } from './surfaces';
import { LAYOUT_BASELINE, platformInstances, type LayoutFinding } from './layout-baseline';

/** A `{ darwin, linux }` reading. Every total in this module is one of these. */
export type PlatformTotals = Readonly<Record<BaselinePlatform, number>>;

/**
 * Sum every recorded node count in an a11y baseline, per platform.
 *
 * Takes the entry list as a parameter rather than closing over the module-level
 * `A11Y_BASELINE`, so the negative controls can feed it a synthetic baseline
 * and prove the checker actually detects a mismatch. A checker that can only
 * ever be run against the one input it is supposed to validate cannot be shown
 * to be non-vacuous.
 */
export function sumA11yNodes(entries: readonly BaselineEntry[]): PlatformTotals {
  const total: Record<BaselinePlatform, number> = { darwin: 0, linux: 0 };
  for (const entry of entries) {
    for (const key of Object.keys(entry.counts)) {
      for (const platform of BASELINE_PLATFORMS) {
        total[platform] += platformCount(entry.counts[key], platform);
      }
    }
  }
  return total;
}

/** What `auditDarwinProvenance` found: how much of the darwin column is unmeasured. */
export interface DarwinProvenance {
  /** `sumA11yNodes(entries).darwin` — the whole declared darwin debt. */
  readonly totalNodes: number;
  /** The part of it sitting in cells nobody has measured on darwin. */
  readonly unverifiedNodes: number;
  /** Those cells, in the order the register lists them. */
  readonly unverifiedKeys: readonly string[];
  /**
   * Register entries that match NO cell in the baseline. A key survives a cell's
   * deletion silently otherwise, and a register that names cells which no longer
   * exist under-reports without ever disagreeing with anything.
   */
  readonly unknownKeys: readonly string[];
  /**
   * Register entries whose cell is a SCALAR. A scalar asserts both columns with one
   * number, so "the darwin half is carried forward" cannot be true of it in the sense
   * this register means; either the cell should be split or the key should go.
   */
  readonly scalarKeys: readonly string[];
  /** `unverifiedNodes / totalNodes`, 0 when there is nothing to divide. */
  readonly unverifiedFraction: number;
}

/**
 * HOW MUCH OF THE DARWIN COLUMN IS A READING, AND HOW MUCH IS CARRIED FORWARD.
 *
 * The defect this answers is recorded in full at `DARWIN_CARRIED_FORWARD` in
 * `a11y-baseline.ts`: a carried-forward darwin half is indistinguishable from a
 * measured one, and 15 cells were wrong for eleven days because of it (~~14~~; corrected
 * in independent review 2026-08-27 — `settings@width-320` collapsed too, and 19 of the
 * 168 cells moved in all, the other four being residual real differences), with every run
 * agreeing with every number. This does not FIX that — only a darwin run can — but it
 * makes the size of the exposure a number a reviewer can see.
 *
 * Takes both inputs as parameters, like every other function here, so the invariant
 * suite's negative controls can prove it is not vacuous by feeding it a register that
 * really does name unverified cells and checking the arithmetic changes.
 */
export function auditDarwinProvenance(
  entries: readonly BaselineEntry[],
  carriedForward: readonly string[]
): DarwinProvenance {
  const totalNodes = sumA11yNodes(entries).darwin;
  const unverifiedKeys: string[] = [];
  const unknownKeys: string[] = [];
  const scalarKeys: string[] = [];
  let unverifiedNodes = 0;

  for (const key of carriedForward) {
    const owning = entries.filter((entry) => key in entry.counts);
    if (owning.length === 0) {
      unknownKeys.push(key);
      continue;
    }
    unverifiedKeys.push(key);
    for (const entry of owning) {
      const count = entry.counts[key];
      if (typeof count === 'number') scalarKeys.push(key);
      unverifiedNodes += platformCount(count, 'darwin');
    }
  }

  return {
    totalNodes,
    unverifiedNodes,
    unverifiedKeys,
    unknownKeys,
    scalarKeys,
    unverifiedFraction: totalNodes === 0 ? 0 : unverifiedNodes / totalNodes,
  };
}

/**
 * Sum every recorded layout offender, per platform. Same contract as above.
 *
 * Reads each list through `platformInstances`, the same accessor
 * `layout-baseline.ts` uses for its own derivation, rather than re-deciding
 * what a bare array versus a per-platform object means. Two readers of one
 * shape is how the shapes drift apart.
 */
export function sumLayoutInstances(findings: readonly LayoutFinding[]): PlatformTotals {
  const total: Record<BaselinePlatform, number> = { darwin: 0, linux: 0 };
  for (const finding of findings) {
    for (const list of Object.values(finding.instances)) {
      for (const platform of BASELINE_PLATFORMS) {
        total[platform] += platformInstances(list, platform).length;
      }
    }
  }
  return total;
}

/** One platform's disagreement between a declared total and the measured sum. */
export interface AggregateMismatch {
  readonly platform: BaselinePlatform;
  readonly declared: number;
  readonly computed: number;
  /** `computed - declared`. Positive means the entries grew and the total did not. */
  readonly drift: number;
  readonly message: string;
}

/**
 * Compare a declared per-platform total against the sum of its entries.
 *
 * Returns EVERY mismatch rather than throwing on the first, because the merge
 * failure mode this exists for moves both columns at once and reporting one of
 * them would send whoever is fixing it back for a second run.
 */
export function auditAggregate(
  label: string,
  declared: PlatformTotals,
  computed: PlatformTotals
): readonly AggregateMismatch[] {
  const mismatches: AggregateMismatch[] = [];
  for (const platform of BASELINE_PLATFORMS) {
    const d = declared[platform];
    const c = computed[platform];
    if (d === c) continue;
    const drift = c - d;
    // A NON-FINITE SUM IS A STRUCTURAL DEFECT, NOT AN ARITHMETIC ONE, and saying
    // otherwise is worse than saying nothing. A per-platform count written
    // `{ darwin: 3 }` with no `linux` makes `platformCount` return `undefined`
    // for the missing half and the sum becomes `NaN`. The arithmetic branch
    // below would then print "Set the total to NaN" — advice that leaves the
    // suite red forever, since `NaN !== NaN`. The browser suite has a dedicated
    // shape check for this (`specs/a11y-axe.spec.ts`, the per-platform
    // `hasOwnProperty` assertion); the fast suite reaches this function first,
    // so it must diagnose rather than mislead.
    if (!Number.isFinite(c)) {
      mismatches.push({
        platform,
        declared: d,
        computed: c,
        drift,
        message:
          `${label}.${platform} cannot be checked: the entries do not sum to a finite number.\n` +
          `  This is a SHAPE defect, not a stale total. The usual cause is a per-platform count\n` +
          `  written as an object that is missing the "${platform}" key — every platform in\n` +
          `  BASELINE_PLATFORMS must be measured, or the count must be a bare number meaning\n` +
          `  "identical on all of them". Find the offending key in e2e/a11y-baseline.ts and give it\n` +
          `  a "${platform}" number. Do NOT change the total; there is no number that would help.`,
      });
      continue;
    }
    mismatches.push({
      platform,
      declared: d,
      computed: c,
      drift,
      message:
        `${label}.${platform} is ${d}, but its entries sum to ${c} ` +
        `(${drift > 0 ? '+' : ''}${drift}).\n` +
        (drift > 0
          ? `  The entries grew by ${drift} more than the total records. The usual cause is a MERGE:\n` +
            `  two branches each raised this literal to the same value for different reasons, so git\n` +
            `  merged the line without a conflict while both sets of entries survived. Do not "fix"\n` +
            `  this by lowering an entry — every entry is a measurement. Raise the total to ${c}.\n`
          : `  The total records ${-drift} more than the entries hold. Either an entry was deleted\n` +
            `  (a defect went away — good, and the total should fall) or a count was lowered.\n` +
            `  Set the total to ${c}.\n`) +
        `  The constant lives in e2e/a11y-baseline.ts. This is arithmetic over that file, not a\n` +
        `  measurement: correcting the number does not loosen any assertion, and every per-cell\n` +
        `  count remains a one-node ratchet against a real scan.`,
    });
  }
  return mismatches;
}

/**
 * The whole invariant, over the REAL baselines, in one call.
 *
 * `declaredA11y` and `declaredLayout` are parameters rather than reads of the
 * module constants so that a caller checking a HYPOTHETICAL total goes through
 * this same code path — which is what the "declared total is stale" negative
 * control in the invariant suite does.
 */
export function auditBaselineAggregates(
  declaredA11y: PlatformTotals,
  declaredLayout: PlatformTotals
): readonly AggregateMismatch[] {
  return [
    ...auditAggregate('A11Y_BASELINE_TOTAL_NODES', declaredA11y, sumA11yNodes(A11Y_BASELINE)),
    ...auditAggregate('LAYOUT_BASELINE_TOTAL_INSTANCES', declaredLayout, sumLayoutInstances(LAYOUT_BASELINE)),
  ];
}

/**
 * EVERY WELL-FORMEDNESS CHECK ON `A11Y_BASELINE` THAT NEEDS NO BROWSER.
 *
 * ── Why this exists, and why it is not just the aggregate check ─────────────
 *
 * The first version of this module moved ONE check out of the ~30-minute
 * `browser-a11y` job — the declared-total-equals-sum comparison. Independent
 * review pointed out that the module's own justification ("there is no reason a
 * data error should cost half an hour") applied equally to the rest of
 * `specs/a11y-axe.spec.ts`'s well-formedness test, which is just as pure and
 * just as cheap and stayed behind: duplicate rule names, the `note.length`
 * floor, empty `counts`, `targetPattern` regex validity, lower-case-hex
 * `foregrounds`, the per-platform completeness rule, and — most valuably — the
 * RATCHET INVERSION, which proves every recorded count is one node from red on
 * both sides and touches no page at all.
 *
 * They are all here now. The spec calls this function instead of keeping its own
 * copy, so there is ONE implementation rather than two that can drift — the same
 * reason `sumA11yNodes` exists.
 *
 * ── Why it returns strings instead of asserting ─────────────────────────────
 *
 * So it can be called from Playwright's `expect` and from vitest's `expect`
 * without importing either. A test framework in a data module would put
 * `@playwright/test` into the fast suite's dependency chain, which is the exact
 * thing `src/__tests__/baseline-invariant-wiring.test.ts` asserts against.
 *
 * Every problem is reported, not just the first: a baseline edit that breaks
 * three cells should say so once rather than over three runs.
 */
export function auditA11yWellFormedness(): readonly string[] {
  const problems: string[] = [
    // The parameterizable half, run over the real baseline. Split out so the
    // negative controls can feed it a BROKEN baseline and prove it detects —
    // see `auditEntryShapes`.
    ...auditEntryShapes(A11Y_BASELINE, new Set(SURFACES.map((s) => s.id)), new Set(SCAN_PROJECT_IDS)),
  ];
  const say = (ok: boolean, message: string) => {
    if (!ok) problems.push(message);
  };

  for (const entry of A11Y_BASELINE) {
    for (const key of Object.keys(entry.counts)) {
      const parts = splitBaselineKey(key);
      if (!parts) continue; // already reported by `auditEntryShapes`
      const { surfaceId, projectId } = parts;
      const raw = entry.counts[key];

      for (const platform of BASELINE_PLATFORMS) {
        const n = platformCount(raw, platform);

        // THE INVERSION. For every recorded instance, on every platform, the
        // policy must be exactly one node wide on each side. No ranges, no
        // tolerance: the ±1 that font metrics produce is recorded as a second
        // exact number, never as slack around the first.
        say(
          baselineVerdict(entry.rule, surfaceId, projectId, n, platform) === 'ok',
          `${entry.rule} @ ${key} [${platform}]: ${n} must be ok`
        );
        say(
          baselineVerdict(entry.rule, surfaceId, projectId, n + 1, platform) === 'grew',
          `${entry.rule} @ ${key} [${platform}]: ${n + 1} nodes MUST fail — that is the whole point of the baseline`
        );
        say(
          baselineVerdict(entry.rule, surfaceId, projectId, n - 1, platform) === 'improved',
          `${entry.rule} @ ${key} [${platform}]: ${n - 1} nodes must read as "improved", so a ` +
            `partially-fixed defect updates this file instead of rotting`
        );
      }
    }

    // …and no entry may tolerate anything on a pair it did not record, on
    // either platform.
    for (const { surfaceId, projectId } of allScanPairs()) {
      if (entry.counts[baselineKey(surfaceId, projectId)] !== undefined) continue;
      for (const platform of BASELINE_PLATFORMS) {
        say(
          baselineVerdict(entry.rule, surfaceId, projectId, 1, platform) === 'new',
          `${entry.rule} is not recorded at ${surfaceId}@${projectId}, so one node there MUST read ` +
            `as new on ${platform}`
        );
        say(
          !isBaselined(entry.rule, surfaceId, projectId, platform),
          `${entry.rule} must not read as baselined at ${surfaceId}@${projectId} on ${platform}`
        );
        say(
          expectedNodeCount(entry.rule, surfaceId, projectId, platform) === 0,
          `${entry.rule} must expect 0 nodes at ${surfaceId}@${projectId} on ${platform}`
        );
      }
    }
  }

  // Sanity: the grid the counts are keyed against is the grid the suite scans.
  say(
    allScanPairs().length === SURFACES.length * SCAN_PROJECT_IDS.length,
    `the scan grid is ${allScanPairs().length} pairs but should be ${SURFACES.length} surfaces x ` +
      `${SCAN_PROJECT_IDS.length} projects`
  );
  say(
    SCAN_PROJECT_IDS.length === PROJECT_IDS.length + 2,
    `SCAN_PROJECT_IDS must be the ${PROJECT_IDS.length} Playwright projects plus the two narrow widths`
  );

  return problems;
}

/**
 * THE PARAMETERIZABLE HALF of the well-formedness audit: everything decidable
 * from an entry list plus the legal surface and project vocabularies.
 *
 * It takes its inputs rather than reading the module constants for exactly the
 * reason `sumA11yNodes` does — **a checker that can only ever be run against the
 * one input it is meant to validate has not been shown to detect anything.** The
 * negative controls feed this deliberately broken baselines.
 *
 * WHAT IS DELIBERATELY NOT HERE, and cannot be: the ratchet inversion
 * (`baselineVerdict(n+1) === 'grew'`, and the "not recorded means new" sweep).
 * Those call `baselineVerdict`/`isBaselined`/`expectedNodeCount`, which read the
 * module-level `A11Y_BASELINE` themselves, so passing a different entry list
 * would compare one baseline's counts against another's verdicts and prove
 * nothing. They stay in `auditA11yWellFormedness`, over the real data, and are
 * self-referential by nature — stated rather than papered over.
 */
export function auditEntryShapes(
  entries: readonly BaselineEntry[],
  legalSurfaceIds: ReadonlySet<string>,
  legalProjectIds: ReadonlySet<string>
): readonly string[] {
  const problems: string[] = [];
  const say = (ok: boolean, message: string) => {
    if (!ok) problems.push(message);
  };
  const seenRules = new Set<string>();

  for (const entry of entries) {
    say(/^[a-z0-9-]+$/.test(entry.rule), `"${entry.rule}" is not a valid axe rule id`);
    say(!seenRules.has(entry.rule), `duplicate baseline entry for "${entry.rule}"`);
    seenRules.add(entry.rule);
    say(entry.note.length > 60, `baseline entry "${entry.rule}" must carry a real explanation`);

    // An entry with no counts tolerates nothing, which means it is dead weight
    // pretending to document something.
    const keys = Object.keys(entry.counts);
    say(keys.length > 0, `baseline entry "${entry.rule}" records no (surface, project) pair`);

    // Identity guard: a count alone cannot tell "the same 31 buttons" from
    // "31 different elements", so every entry must pin one or the other.
    say(
      Boolean(entry.targetPattern) || Boolean(entry.foregrounds?.length),
      `baseline entry "${entry.rule}" must pin WHICH nodes fail — a targetPattern or, for ` +
        `color-contrast, the exact set of failing foreground colours. A bare count would let a ` +
        `different element fail the same rule the same number of times and stay green.`
    );
    if (entry.targetPattern) {
      try {
        new RegExp(entry.targetPattern);
      } catch {
        say(false, `baseline entry "${entry.rule}" has an invalid targetPattern regex`);
      }
    }
    for (const c of entry.foregrounds ?? []) {
      say(/^#[0-9a-f]{6}$/.test(c), `"${entry.rule}" foreground "${c}" is not lower-case hex`);
    }

    for (const key of keys) {
      const parts = splitBaselineKey(key);
      if (!parts) {
        say(false, `"${entry.rule}" baseline key "${key}" is not surfaceId@projectId`);
        continue;
      }
      const { surfaceId, projectId } = parts;
      say(legalSurfaceIds.has(surfaceId), `"${entry.rule}" baselines unknown surface "${surfaceId}"`);
      say(legalProjectIds.has(projectId), `"${entry.rule}" baselines unknown project "${projectId}"`);

      const raw = entry.counts[key];
      // A per-platform count must carry EVERY platform. A partial object would
      // silently read `undefined` on the missing one and, through
      // `platformCount`, become a `NaN` comparison that never says "grew".
      if (typeof raw !== 'number') {
        for (const p of BASELINE_PLATFORMS) {
          say(
            Object.prototype.hasOwnProperty.call(raw, p),
            `"${entry.rule}" @ ${key} is a per-platform count but has no "${p}" number. Every ` +
              `platform in BASELINE_PLATFORMS must be measured, or the count must be a bare number ` +
              `meaning "identical on all of them".`
          );
        }
        const pair = raw as Record<string, number>;
        say(
          pair.darwin !== pair.linux,
          `"${entry.rule}" @ ${key} is written per-platform but both numbers are the same. Write a ` +
            `bare number instead — a per-platform pair should mark a real measured difference.`
        );
      }

      for (const platform of BASELINE_PLATFORMS) {
        const n = platformCount(raw, platform);
        say(
          Number.isInteger(n) && n >= 1,
          `"${entry.rule}" @ ${key} [${platform}]: count must be a positive integer, got ${n}`
        );
      }
    }
  }

  return problems;
}

/**
 * The `${surfaceId}@${projectId}` keys of each baseline, SEPARATELY.
 *
 * Separately, because the two files are keyed against DIFFERENT grids and a
 * single combined list would have to check both against the union — which
 * would accept `evidence@width-375` in the a11y baseline, where no scan ever
 * visits 375 as a named width, and accept `evidence@width-390` in the layout
 * baseline for the same wrong reason. The union is exactly the check that
 * cannot fail, so it is not the check that is made.
 *
 *   * a11y   → `SCAN_PROJECT_IDS`      (5 projects + width-390 + width-320)
 *   * layout → `PROJECT_IDS` + `LAYOUT_SWEEP_WIDTH_IDS` (7 widths, incl. 375
 *              and 640, which the a11y sweep does not scan)
 *
 * Used by the fast suite so a typo'd surface id or a retired project is
 * rejected in milliseconds rather than after a ~30-minute browser job.
 */
export function a11yBaselineKeys(): readonly string[] {
  const keys = new Set<string>();
  for (const entry of A11Y_BASELINE) for (const key of Object.keys(entry.counts)) keys.add(key);
  return [...keys].sort();
}

export function layoutBaselineKeys(): readonly string[] {
  const keys = new Set<string>();
  for (const finding of LAYOUT_BASELINE) for (const key of Object.keys(finding.instances)) keys.add(key);
  return [...keys].sort();
}

/**
 * Split a baseline key back into its two halves. Returns null on a malformed key.
 *
 * THE ONE SPLITTER. `specs/a11y-axe.spec.ts` used to do its own
 * `key.split('@')`, which disagrees with this on a surface id containing `@`:
 * `'a@b@c'` splits to `{'a@b', 'c'}` here and to `['a','b']` there, silently
 * dropping `'c'`. Pathological today — no surface id contains `@` — but
 * `sumLayoutInstances` two functions up carries the comment "Two readers of one
 * shape is how the shapes drift apart", and it would be a poor module that broke
 * its own rule. The spec now imports this.
 *
 * `lastIndexOf` rather than `indexOf` because the PROJECT half is the closed,
 * known vocabulary (`SCAN_PROJECT_IDS`, `LAYOUT_SWEEP_WIDTH_IDS`) and the
 * surface half is the open one.
 */
export function splitBaselineKey(key: string): { surfaceId: string; projectId: string } | null {
  const at = key.lastIndexOf('@');
  if (at <= 0 || at === key.length - 1) return null;
  return { surfaceId: key.slice(0, at), projectId: key.slice(at + 1) };
}
