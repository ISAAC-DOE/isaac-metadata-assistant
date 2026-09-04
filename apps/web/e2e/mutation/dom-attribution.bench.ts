/*
 * WHICH ELEMENTS ARE THE DOM, per screen, at a high run count.
 *
 * `docs/run-scale-measurements.md` §1 attributed the record screen's 16,134 nodes to the
 * pending banner with a per-class probe — and that probe WAS NEVER COMMITTED, which is why
 * the document has an arithmetic correction in it instead of a re-measurement ("it is NOT
 * independently re-measurable"). This file is that probe, committed.
 *
 * It reports the top classes by element count on each screen, so an attribution is read off
 * a measurement rather than inferred from a total.
 */

import { test, expect, openRecord } from './own-session-fixtures';
import { MUT_API_BASE, SEED } from './env';
import { TUTORIAL_SESSION_HEADER } from '../worked-example';

const COUNT = Number(process.env.E2E_BENCH_COUNTS ?? '1000');
const TARGET = SEED.fresh;

/** Top `n` class names by element count, plus the page total. */
const PROBE = (n: number) => {
  const tally: Record<string, number> = {};
  for (const el of Array.from(document.getElementsByTagName('*'))) {
    const cls = (el.getAttribute('class') ?? '').trim();
    for (const c of cls.split(/\s+/)) {
      if (c) tally[c] = (tally[c] ?? 0) + 1;
    }
  }
  const top = Object.entries(tally)
    .sort((a, b) => b[1] - a[1])
    .slice(0, n);
  return { total: document.getElementsByTagName('*').length, top };
};

test('attribute the DOM by class at a high run count', async ({ page, request, session }) => {
  test.setTimeout(60 * 60 * 1000);
  const headers = { [TUTORIAL_SESSION_HEADER]: session };
  const runsUrl = `${MUT_API_BASE}/experiments/${TARGET}/runs`;

  const readRuns = async () => {
    const res = await request.get(runsUrl, { headers });
    expect(res.ok()).toBeTruthy();
    return (await res.json()) as { runs: { id: string }[]; experiment_version: string };
  };

  const s0 = await readRuns();
  let version = s0.experiment_version;
  let have = s0.runs.length;
  while (have < COUNT) {
    const res = await request.post(runsUrl, {
      headers: { ...headers, 'If-Match': `"${version}"` },
      data: {},
    });
    expect(res.ok(), `POST /runs at ${have}: ${res.status()}`).toBeTruthy();
    version = ((await res.json()) as { experiment_version?: string }).experiment_version ??
      (await readRuns()).experiment_version;
    have += 1;
  }

  const report: string[] = [];
  const probe = async (label: string) => {
    const { total, top } = await page.evaluate(PROBE, 14);
    report.push(`${label}: total=${total}\n  ${top.map(([c, n]) => `${c}×${n}`).join(', ')}`);
  };

  /*
   * ── THE `record` PROBE NOW MEASURES ONE WORKSPACE, NOT THE WHOLE SCREEN. ───
   *
   * `/record/<id>` used to be one column holding everything. It is now four
   * lazily-mounted `?view=` workspaces, and this probe opens `runs` — so the
   * number below counts the run list and Validate & Review, and counts NONE of:
   *
   *   · Record Fields — the four draft blocks, the Record Identity sections
   *     (Rename, Record Description, Record Info, Relationships) and Asset
   *     References;
   *   · Capture & Proposals — transcript capture, unmapped notes, ingestion
   *     proposals;
   *   · Graph.
   *
   * SO THIS FIGURE IS NOT COMPARABLE TO ANY `record` NUMBER RECORDED BEFORE THAT
   * SPLIT, including the ones in `docs/run-scale-measurements.md`. It is still the
   * right probe for the question this bench asks — where the DOM goes as runs
   * scale — because the run list is on this workspace; it is the wrong number to
   * quote as "the record screen's DOM cost". Re-run the other three workspaces
   * before making that claim, rather than adding this one to a remembered total.
   */
  await openRecord(page, TARGET, 'runs');
  await expect(page.getByRole('heading', { name: 'Runs', exact: true })).toBeVisible({
    timeout: 300_000,
  });
  await probe('record');

  await page.goto(`/record/${TARGET}/export`);
  await expect(page.getByRole('heading', { name: /Export/i }).first()).toBeVisible({
    timeout: 300_000,
  });
  /*
   * WAIT FOR THE SKELETONS TO GO, and this line is here because the first version of this
   * probe did not have it and reported 152 nodes for a screen that settles at 21,253. The
   * heading renders while the fetches are still out, so a probe gated on the heading
   * measures the LOADING state and reads as a flat, healthy number — the most misleading
   * possible result, because it looks like an answer.
   */
  await page
    .locator('.skeleton')
    .first()
    .waitFor({ state: 'detached', timeout: 300_000 })
    .catch(() => undefined);
  await page.waitForLoadState('networkidle', { timeout: 300_000 }).catch(() => undefined);
  await probe('export-readiness');

  await page.goto(`/record/${TARGET}/complete`);
  await page
    .locator('.skeleton')
    .first()
    .waitFor({ state: 'detached', timeout: 300_000 })
    .catch(() => undefined);
  await page.waitForLoadState('networkidle', { timeout: 300_000 }).catch(() => undefined);
  await probe('guided-completion');

  await page.goto(`/record/${TARGET}/evidence?view=graph`);
  await page
    .locator('[data-testid="evgraph-counts"]')
    .waitFor({ state: 'visible', timeout: 300_000 });
  await probe('evidence-graph');

  // eslint-disable-next-line no-console
  console.log(`\n[dom-attr] runs=${COUNT}\n${report.join('\n')}\n`);
});
