/**
 * axe-core wiring.
 *
 * Two rules for this file:
 *
 *   1. NOTHING is ever disabled. `AxeBuilder` supports `.disableRules()`; this
 *      suite never calls it.
 *   2. Nothing is filtered here either. The scan returns everything it found;
 *      `../a11y-baseline.ts` decides, per (rule, surface, project) triple and
 *      per NODE COUNT, what is a recorded defect. Whole-`Result` filtering is
 *      what let a `'*'`-scoped entry hide 1,974 nodes in the first version of
 *      this suite, so the helpers below deliberately expose node-level detail.
 */

import AxeBuilder from '@axe-core/playwright';
import type { Page } from '@playwright/test';
import type { AxeResults, Result } from 'axe-core';
import {
  A11Y_BASELINE,
  baselineEntryFor,
  baselineVerdict,
  currentPlatform,
  expectedNodeCount,
  type BaselinePlatform,
  type BaselineVerdict,
} from '../a11y-baseline';

/**
 * WCAG 2.0/2.1 A + AA, plus Deque's `best-practice` pack.
 *
 * `best-practice` is included on purpose even though it is not normative — it
 * is what catches landmark, heading-order and region defects that WCAG states
 * only as advisory. Two of the six recorded findings come from it.
 */
export const AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'best-practice'] as const;

export async function scan(page: Page, options?: { include?: string; exclude?: string[] }): Promise<AxeResults> {
  let builder = new AxeBuilder({ page }).withTags([...AXE_TAGS]);
  if (options?.include) builder = builder.include(options.include);
  for (const sel of options?.exclude ?? []) builder = builder.exclude(sel);
  return builder.analyze();
}

/** Every axe target of a violation, one string per failing node. */
export function nodeTargets(v: Result): string[] {
  return v.nodes.map((n) => n.target.join(' '));
}

/**
 * The distinct foreground colours a `color-contrast` violation reported.
 *
 * axe puts them on the individual check results (`node.any[].data.fgColor`),
 * which is the only place the failing token is machine-readable — the node
 * HTML shows a class name, not a colour. This is what makes "a new too-light
 * token appeared" detectable even when the node count happens to be unchanged.
 */
export function violationForegrounds(v: Result): string[] {
  const out = new Set<string>();
  for (const node of v.nodes) {
    for (const check of [...node.any, ...node.all, ...node.none]) {
      const data = (check as unknown as { data?: { fgColor?: unknown } }).data;
      if (data && typeof data.fgColor === 'string') out.add(data.fgColor.toLowerCase());
    }
  }
  return [...out].sort();
}

export type FailureKind = Exclude<BaselineVerdict, 'ok'> | 'new-target' | 'new-foreground';

export interface BaselineFailure {
  readonly rule: string;
  readonly kind: FailureKind;
  readonly expected: number;
  readonly actual: number;
  /** The baseline column that produced `expected`. */
  readonly platform: BaselinePlatform;
  /** One line, naming surface, project, platform, rule and the exact delta. */
  readonly message: string;
}

/**
 * Compare a scan against the per-instance baseline. THE policy, in one place.
 *
 * Returns one failure per problem, empty when the page matches its recorded
 * state exactly. Deliberately not a filter over `Result` objects: axe emits one
 * `Result` per rule with every node inside, so anything that drops a whole
 * `Result` silently drops every node of that rule.
 *
 * `platform` selects which baseline column is enforced and defaults to the
 * current process's. It is named in every message, because "expected 6, got 7"
 * is unactionable when the file holds a number for each of two platforms and
 * the reader cannot see which one was consulted.
 */
export function auditScan(
  results: AxeResults,
  surfaceId: string,
  projectId: string,
  platform: BaselinePlatform = currentPlatform()
): BaselineFailure[] {
  const where = `${surfaceId} @ ${projectId} on ${platform}`;
  const failures: BaselineFailure[] = [];
  const fired = new Set<string>();
  // How to write the corrected number back: bare for a triple that is the same
  // on both platforms, `{ darwin: …, linux: … }` for one that is not.
  const edit = (n: number) =>
    `'${surfaceId}@${projectId}': ${n}  (or { …, ${platform}: ${n} } if the other platform differs)`;

  for (const v of results.violations) {
    fired.add(v.id);
    const actual = v.nodes.length;
    const expected = expectedNodeCount(v.id, surfaceId, projectId, platform);
    const verdict = baselineVerdict(v.id, surfaceId, projectId, actual, platform);

    if (verdict === 'new') {
      failures.push({
        rule: v.id,
        kind: 'new',
        expected,
        actual,
        platform,
        message:
          `NEW  ${where}: rule "${v.id}" is not baselined here at all, and fired on ${actual} node(s).\n` +
          `${formatViolation(v)}\n` +
          `     → Fix apps/web/src, or add ${edit(actual)} to the "${v.id}" ` +
          `entry in e2e/a11y-baseline.ts with a note explaining the defect.`,
      });
      continue;
    }
    if (verdict === 'grew') {
      failures.push({
        rule: v.id,
        kind: 'grew',
        expected,
        actual,
        platform,
        message:
          `GREW ${where}: rule "${v.id}" grew from ${expected} to ${actual} node(s) (+${actual - expected}) ` +
          `against the ${platform} column.\n` +
          `${formatViolation(v)}\n` +
          `     → A regression: this surface got worse. Fix it, or — if the extra node(s) are ` +
          `deliberate and understood — update the ${platform} count in e2e/a11y-baseline.ts: ${edit(actual)}. ` +
          `Do NOT change the other platform's number to match; it was measured separately.`,
      });
      continue;
    }
    if (verdict === 'improved') {
      failures.push({
        rule: v.id,
        kind: 'improved',
        expected,
        actual,
        platform,
        message:
          `IMPROVED ${where}: rule "${v.id}" fell from ${expected} to ${actual} node(s) ` +
          `(-${expected - actual}) against the ${platform} column. Not a bug — but the baseline is ` +
          `now wrong, and a stale number would re-admit the defect. Lower the ${platform} count in ` +
          `e2e/a11y-baseline.ts: ${edit(actual)}.`,
      });
      continue;
    }

    // Count matches. Same number of nodes is not the same defect, so check identity too.
    const entry = baselineEntryFor(v.id);
    if (entry?.targetPattern) {
      const re = new RegExp(entry.targetPattern);
      const strays = nodeTargets(v).filter((t) => !re.test(t));
      if (strays.length) {
        failures.push({
          rule: v.id,
          kind: 'new-target',
          expected,
          actual,
          platform,
          message:
            `NEW TARGET ${where}: rule "${v.id}" still fails on ${actual} node(s), but ` +
            `${strays.length} of them are element(s) the baseline never recorded:\n` +
            strays.map((t) => `       - ${t}`).join('\n') +
            `\n     → Expected targets to match /${entry.targetPattern}/.`,
        });
      }
    }
    if (entry?.foregrounds) {
      const known = new Set(entry.foregrounds.map((c) => c.toLowerCase()));
      const strays = violationForegrounds(v).filter((c) => !known.has(c));
      if (strays.length) {
        failures.push({
          rule: v.id,
          kind: 'new-foreground',
          expected,
          actual,
          platform,
          message:
            `NEW COLOUR ${where}: rule "${v.id}" fails on ${actual} node(s) as recorded, but ` +
            `with foreground colour(s) the baseline never recorded: ${strays.join(', ')}.\n` +
            `     → A new too-light token (or a new opacity composite) has appeared. Fix it, or ` +
            `add it to \`foregrounds\` in e2e/a11y-baseline.ts with its measured ratio.`,
        });
      }
    }
  }

  // Rules the baseline expects here that did not fire at all: expected N, actual 0.
  for (const entry of A11Y_BASELINE) {
    if (fired.has(entry.rule)) continue;
    const expected = expectedNodeCount(entry.rule, surfaceId, projectId, platform);
    if (expected === 0) continue;
    failures.push({
      rule: entry.rule,
      kind: 'improved',
      expected,
      actual: 0,
      platform,
      message:
        `FIXED? ${where}: rule "${entry.rule}" is baselined at ${expected} node(s) here on ${platform} ` +
        `but did not fire at all. If it is fixed, delete '${surfaceId}@${projectId}' from that entry in ` +
        `e2e/a11y-baseline.ts (and delete the whole entry once its last pair is gone). If it is fixed ` +
        `only on ${platform}, the pair becomes a per-platform count with the other column unchanged.`,
    });
  }

  return failures;
}

/**
 * How many offending nodes a failure message lists before truncating.
 *
 * IT WAS 4, AND THAT NUMBER COST A WHOLE INVESTIGATION. When the Run vertical
 * slice grew `record-detail@tablet-768x1024` from 14 to 16 `color-contrast`
 * nodes, CI printed four nodes — all four of them pre-existing debt
 * (`.section-tab`, `.needsyou-about`, `.evidence-trail-link-count`) — and
 * "… and 9 more node(s)". The two NEW nodes, which are the entire point of a
 * regression message, were inside the truncated part, so the only way to find out
 * what had regressed was to re-run the scan locally against two commits. The
 * baseline's whole design is "tell the author exactly what got worse"; a limit
 * that hides the delta defeats it.
 *
 * 24 is chosen against the actual numbers rather than as a round figure: the
 * largest baselined count in this repository is `settings-explorer@tablet-768x1024`
 * at 62, so this is deliberately NOT "print everything" — a 62-node dump would
 * bury the signal again. It is comfortably above every *delta* the baseline has
 * ever reported, which is the thing a reader needs to see.
 */
const MAX_REPORTED_NODES = 24;

/** A compact, greppable rendering of one violation for failure output. */
export function formatViolation(v: Result): string {
  const nodes = v.nodes
    .slice(0, MAX_REPORTED_NODES)
    .map((n) => `      - ${n.target.join(' ')}\n        ${n.html.replace(/\s+/g, ' ').slice(0, 160)}`)
    .join('\n');
  const more =
    v.nodes.length > MAX_REPORTED_NODES
      ? `\n      … and ${v.nodes.length - MAX_REPORTED_NODES} more node(s)`
      : '';
  return `  [${v.impact ?? 'unknown'}] ${v.id} — ${v.help} (${v.nodes.length} node(s))\n    ${v.helpUrl}\n${nodes}${more}`;
}
