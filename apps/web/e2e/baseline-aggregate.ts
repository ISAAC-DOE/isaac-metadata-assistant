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
 * function over data, with no browser, no page and no Playwright — so it can
 * also run in the fast `vitest` suite, in milliseconds, in the `frontend` CI
 * job, on every pull request and on every push to `main`. Detection was already
 * complete; the latency was the defect.
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
  baselineKey,
  platformCount,
  type BaselineEntry,
  type BaselinePlatform,
} from './a11y-baseline';
import { LAYOUT_BASELINE, layoutKey, platformInstances, type LayoutFinding } from './layout-baseline';

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
        `  This is arithmetic over the file, not a measurement: correcting the number here does not\n` +
        `  loosen any assertion, and every per-cell count remains a one-node ratchet against a scan.`,
    });
  }
  return mismatches;
}

/**
 * The whole invariant, over the REAL baselines, in one call.
 *
 * `declaredA11y` and `declaredLayout` are parameters so a caller that wants to
 * check a hypothetical (the negative controls; a future consistency script)
 * uses the same code path the suite does.
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

/** Split a baseline key back into its two halves. Returns null on a malformed key. */
export function splitBaselineKey(key: string): { surfaceId: string; projectId: string } | null {
  const at = key.lastIndexOf('@');
  if (at <= 0 || at === key.length - 1) return null;
  return { surfaceId: key.slice(0, at), projectId: key.slice(at + 1) };
}

/** Re-exported so callers need one import for the whole invariant. */
export { baselineKey, layoutKey };
