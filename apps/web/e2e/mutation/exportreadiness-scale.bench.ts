/*
 * TWO GAPS THE MAIN SWEEP LEFT, MEASURED RATHER THAN REASONED ABOUT.
 *
 * 1. THE EXPORT READINESS SCREEN. `scale-2026-08-27.bench.ts` measures the record screen,
 *    the Evidence Graph and Compare Runs. It does NOT open Export Readiness, which is the
 *    one screen that mounts `RevisionHistoryPanel` — and that panel `.map`s
 *    `lifecycle.scientific_readiness.failing_units` with NO BOUND. Reading the source says
 *    that list is one entry per failing unit; only opening the screen says what it costs.
 *    This counts the `<li>`s directly rather than inferring them from the DOM total.
 *
 * 2. THE RECORD SCREEN'S REQUEST COUNT. `load ms` grows 709 → 6,251 while every route it
 *    issues is either flat or ~200 ms, so the arithmetic did not close. A request count is
 *    the missing term and, unlike the milliseconds, it does not move under CPU contention.
 *
 * Two counts only — the smallest and the largest — because the question is "does this grow
 * with runs", which two points answer and five points answer no better.
 */

import { test, expect, openRecord } from './own-session-fixtures';
import { MUT_API_BASE, SEED } from './env';
import { TUTORIAL_SESSION_HEADER } from '../worked-example';

const COUNTS = (process.env.E2E_BENCH_COUNTS ?? '25,1000')
  .split(',')
  .map((n) => Number(n.trim()))
  .filter((n) => Number.isFinite(n) && n > 0)
  .sort((a, b) => a - b);

const TARGET = SEED.fresh;

test('measure Export Readiness and the record screen request count', async ({
  page,
  request,
  session,
}) => {
  test.setTimeout(60 * 60 * 1000);

  const headers = { [TUTORIAL_SESSION_HEADER]: session };
  const runsUrl = `${MUT_API_BASE}/experiments/${TARGET}/runs`;

  const readRuns = async () => {
    const res = await request.get(runsUrl, { headers });
    expect(res.ok(), `GET /runs: ${res.status()}`).toBeTruthy();
    return (await res.json()) as { runs: { id: string }[]; experiment_version: string };
  };

  const s0 = await readRuns();
  let version = s0.experiment_version;
  let have = s0.runs.length;

  /*
   * REQUESTS ARE TALLIED PER URL, not just totalled. "31 requests" cannot distinguish a
   * screen that issues 31 different routes once from one that issues the same route 31
   * times, and only the second is a defect.
   */
  let tally = new Map<string, number>();
  page.on('request', (r) => {
    const u = r.url();
    if (!u.includes('/api/')) return;
    // Collapse the record id and any query so repeats of ONE route group together.
    /*
     * THE QUERY IS KEPT FOR `/pending`, and dropped everywhere else.
     *
     * `/pending` and `/pending?limit=50` are the SAME PATH and are two completely
     * different costs — 2.9 MiB against 49.6 KiB at 1,000 runs. Collapsing them made the
     * record screen read `pending×3` with no way to tell whether that was three windowed
     * reads or three unbounded ones, i.e. 150 KiB or 8.7 MiB. Bounded/unbounded is exactly
     * the distinction this sweep is about, so it is the one query that survives.
     */
    const path = u.replace(/^.*\/api\//, '/').replace(/\?.*$/, '');
    const query = u.includes('?') ? u.replace(/^[^?]*\?/, '') : '';
    const bounded = /(^|&)limit=/.test(query);
    const key = (path + (path.endsWith('/pending') ? (bounded ? '?limit=…' : ' [UNBOUNDED]') : ''))
      .replace(/\/[0-9A-HJKMNP-TV-Z]{26}/gi, '/{id}');
    tally.set(key, (tally.get(key) ?? 0) + 1);
  });

  const out: string[] = [];

  for (const target of COUNTS) {
    while (have < target) {
      const res = await request.post(runsUrl, {
        headers: { ...headers, 'If-Match': `"${version}"` },
        data: {},
      });
      expect(res.ok(), `POST /runs at ${have}: ${res.status()}`).toBeTruthy();
      version = ((await res.json()) as { experiment_version?: string }).experiment_version ??
        (await readRuns()).experiment_version;
      have += 1;
    }

    // ---- the record screen, with its requests attributed ------------------
    tally = new Map();
    const tRec = Date.now();
    await openRecord(page, TARGET);
    await expect(page.getByRole('heading', { name: 'Runs', exact: true })).toBeVisible({
      timeout: 300_000,
    });
    await expect(page.getByRole('button', { name: 'Add Run' })).toBeEnabled({ timeout: 300_000 });
    const recMs = Date.now() - tRec;
    const recTally = [...tally.entries()].sort((a, b) => b[1] - a[1]);
    const recTotal = recTally.reduce((s, [, n]) => s + n, 0);

    // ---- Export Readiness -------------------------------------------------
    tally = new Map();
    const tExp = Date.now();
    await page.goto(`/record/${TARGET}/export`);
    await expect(page.getByRole('heading', { name: /Export/i }).first()).toBeVisible({
      timeout: 300_000,
    });
    // The revision panel is the reason this screen is here; wait for it specifically so
    // the DOM below is taken with it mounted rather than racing it.
    await page
      .locator('.revhist-failing, .revhist-unknown, [class^="revhist"]')
      .first()
      .waitFor({ state: 'attached', timeout: 300_000 })
      .catch(() => undefined);
    const expMs = Date.now() - tExp;
    const expTally = [...tally.entries()].sort((a, b) => b[1] - a[1]);
    const expTotal = expTally.reduce((s, [, n]) => s + n, 0);

    const expDom = await page.evaluate(() => document.getElementsByTagName('*').length);
    const failingLis = await page.evaluate(
      () => document.querySelectorAll('ul.revhist-failing > li').length
    );

    out.push(
      [
        `runs=${target}`,
        `record: ${recMs}ms, ${recTotal} api requests`,
        `  ${recTally.map(([k, n]) => `${k}×${n}`).join(', ')}`,
        `export-readiness: ${expMs}ms, ${expTotal} api requests, dom=${expDom}, ul.revhist-failing>li=${failingLis}`,
        `  ${expTally.map(([k, n]) => `${k}×${n}`).join(', ')}`,
      ].join('\n')
    );
    // eslint-disable-next-line no-console
    console.log(`\n[er-scale]\n${out.join('\n')}\n`);
  }

  // eslint-disable-next-line no-console
  console.log(`\n[er-scale] FINAL\n${out.join('\n')}\n`);
});
