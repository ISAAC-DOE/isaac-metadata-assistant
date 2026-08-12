/*
 * HIGH-RUN-COUNT BENCHMARK — measurement, not a gate.
 *
 * WHY THIS IS A `.bench.ts` AND NOT A `.spec.ts`. Both Playwright configs select on
 * `testMatch: /.*\.spec\.ts$/`, so this file is collected by NEITHER by default. That
 * is deliberate twice over: it creates up to 1000 runs (minutes, not seconds), and its
 * output is a MEASUREMENT to read, not a pass/fail contract to enforce. A benchmark
 * wired into CI becomes a flaky test that fails on a busy runner and teaches everyone
 * to ignore it.
 *
 * Run it explicitly:
 *
 *     npm run bench:runs                      # 25,50,100,250,500
 *     E2E_BENCH_COUNTS=25,100,1000 npm run bench:runs
 *
 * WHAT IT ANSWERS, and why the question needed asking. `RunsSection` renders
 * `runs.map(...)` with no bound. Before choosing between "load more", pagination and
 * windowing, the roadmap requires the envelope be MEASURED rather than assumed — so
 * this reports, per run count: the API's own time and payload, the time from
 * navigation until the Runs section is interactive, the rendered card count, the DOM
 * node count, and expand/collapse latency on the FIRST and LAST card.
 *
 * FIRST **AND** LAST IS THE POINT. A list that degrades does so at its tail: the last
 * card is the one furthest down the DOM, and measuring only the first would report the
 * cheapest case and call it the envelope.
 *
 * THE NUMBERS ARE LOCAL AND THEY ARE NOT A PROMISE. They come from one machine, one
 * Chromium, one synthetic record, with the backend on loopback. They establish SHAPE —
 * linear, superlinear, or a cliff — and the count at which a scientist would notice.
 * Do not quote them as "ISAAC supports N runs"; quote the shape and the tested ceiling.
 *
 * WHAT IT DELIBERATELY DOES NOT MEASURE: memory. `performance.memory` is a
 * Chromium-only, coarsely-quantised estimate that reports the whole renderer process,
 * and reading it here would produce an authoritative-looking number that cannot be
 * compared across runs. Long-task counts are collected instead, which are observable
 * and attributable.
 */

import { test, expect, openRecord } from './own-session-fixtures';
import { MUT_API_BASE, SEED } from './env';
import { TUTORIAL_SESSION_HEADER } from '../worked-example';

/** Run counts to measure, ascending. Each is reached by topping up from the previous. */
const COUNTS = (process.env.E2E_BENCH_COUNTS ?? '25,50,100,250,500')
  .split(',')
  .map((n) => Number(n.trim()))
  .filter((n) => Number.isFinite(n) && n > 0)
  .sort((a, b) => a - b);

/** The example record carrying real record-level content, so `inherited` is realistic. */
const TARGET = SEED.fresh;

interface Row {
  runs: number;
  apiMs: number;
  apiKiB: number;
  inheritedPerRun: number;
  loadMs: number;
  cards: number;
  domNodes: number;
  expandFirstMs: number;
  expandLastMs: number;
  longTasks: number;
}

function table(rows: Row[]): string {
  const head =
    '  runs |   API ms |  payload KiB | inh/run |  load ms | cards | DOM nodes | expand 1st | expand last | long tasks';
  const sep = '  '.padEnd(head.length, '-');
  const body = rows.map(
    (r) =>
      `${String(r.runs).padStart(6)} |` +
      `${r.apiMs.toFixed(0).padStart(9)} |` +
      `${r.apiKiB.toFixed(0).padStart(13)} |` +
      `${String(r.inheritedPerRun).padStart(8)} |` +
      `${r.loadMs.toFixed(0).padStart(9)} |` +
      `${String(r.cards).padStart(6)} |` +
      `${String(r.domNodes).padStart(10)} |` +
      `${r.expandFirstMs.toFixed(0).padStart(11)} |` +
      `${r.expandLastMs.toFixed(0).padStart(12)} |` +
      `${String(r.longTasks).padStart(11)}`
  );
  return [head, sep, ...body].join('\n');
}

test('measure the high-run-count envelope', async ({ page, request, session }) => {
  // Minutes, by construction: creating 500+ runs is hundreds of round trips.
  test.setTimeout(30 * 60 * 1000);

  const headers = { [TUTORIAL_SESSION_HEADER]: session };
  const runsUrl = `${MUT_API_BASE}/experiments/${TARGET}/runs`;

  /** Current experiment version — every run create needs it as a strong validator. */
  const readRuns = async () => {
    const res = await request.get(runsUrl, { headers });
    expect(res.ok(), `GET /runs: ${res.status()}`).toBeTruthy();
    return (await res.json()) as {
      runs: { id: string; inherited?: Record<string, unknown> }[];
      experiment_version: string;
    };
  };

  let state = await readRuns();
  let version = state.experiment_version;
  let have = state.runs.length;
  const rows: Row[] = [];

  /*
   * THE LONG-TASK OBSERVER IS INSTALLED ONCE, OUTSIDE THE LOOP, AND THAT PLACEMENT IS
   * THE WHOLE POINT — it used to be inside.
   *
   * `addInitScript` REGISTERS a script; it does not replace the previous one. Every
   * registration runs on every subsequent navigation. So installing it per iteration
   * meant the k-th row navigated with k observers attached to one document, each
   * incrementing the same `window.__longTasks`, and the column reported k x the real
   * count. An independent review caught it and I reproduced it standalone: after four
   * registrations, a SINGLE long task read as 4.
   *
   * That inflated the published table — the 500-run row was iteration 5, so its
   * reported "5 long tasks" was 1 — and `docs/run-scale-measurements.md` read a trend
   * off it ("0 -> 5 -> 14"). Registered once, the script still runs on each navigation,
   * so the counter resets per document and exactly one observer is attached. The
   * numbers become comparable across rows, which is the only thing that made the
   * column worth having.
   *
   * The observer still counts long tasks caused by the two expand/collapse clicks
   * below, not only by load. `longTasks` is therefore a per-row total for the whole
   * visit, and the doc must not attribute it wholly to response parse/render.
   */
  await page.addInitScript(() => {
    (window as unknown as { __longTasks: number }).__longTasks = 0;
    try {
      new PerformanceObserver((list) => {
        (window as unknown as { __longTasks: number }).__longTasks += list.getEntries().length;
      }).observe({ entryTypes: ['longtask'] });
    } catch {
      /* longtask unsupported: the column reads 0 and says so by being 0 everywhere */
    }
  });

  for (const target of COUNTS) {
    // --- top up to `target` runs, out of band -------------------------------
    while (have < target) {
      const res = await request.post(runsUrl, {
        headers: { ...headers, 'If-Match': `"${version}"` },
        data: {},
      });
      expect(res.ok(), `POST /runs at ${have}: ${res.status()} ${await res.text()}`).toBeTruthy();
      const body = (await res.json()) as { experiment_version?: string };
      version = body.experiment_version ?? (await readRuns()).experiment_version;
      have += 1;
    }

    // --- the API's own cost, measured separately from the browser's ---------
    const apiSamples: number[] = [];
    let apiBytes = 0;
    let inheritedPerRun = 0;
    for (let i = 0; i < 3; i += 1) {
      const t0 = Date.now();
      const res = await request.get(runsUrl, { headers });
      const text = await res.text();
      apiSamples.push(Date.now() - t0);
      apiBytes = text.length;
      if (i === 0) {
        const parsed = JSON.parse(text) as { runs: { inherited?: Record<string, unknown> }[] };
        inheritedPerRun = Object.keys(parsed.runs[0]?.inherited ?? {}).length;
      }
    }
    apiSamples.sort((a, b) => a - b);

    // --- navigate, and time until the Runs section is actually usable -------
    const tLoad = Date.now();
    await openRecord(page, TARGET);
    await expect(page.getByRole('heading', { name: 'Runs', exact: true })).toBeVisible({
      timeout: 120_000,
    });
    // "Interactive" means EVERY card is present and Add Run is enabled — not that the
    // first card painted. A first-paint measurement would be flat by construction and
    // would report nothing about the tail, which is where a list degrades.
    const cards = page.locator('article.run-card');
    await expect(cards).toHaveCount(target, { timeout: 120_000 });
    await expect(page.getByRole('button', { name: 'Add Run' })).toBeEnabled({ timeout: 120_000 });
    const loadMs = Date.now() - tLoad;

    const domNodes = await page.evaluate(() => document.getElementsByTagName('*').length);

    // --- expand latency, first and last ------------------------------------
    const expand = async (index: number) => {
      const card = cards.nth(index);
      const head = card.locator('button.run-card-header');
      await head.scrollIntoViewIfNeeded();
      const t = Date.now();
      await head.click();
      // The inherited panel is the heavy child, and it mounts only when expanded.
      await card.locator('section.run-inherited').waitFor({ state: 'visible', timeout: 120_000 });
      const ms = Date.now() - t;
      await head.click(); // collapse again, so the next measurement starts level
      return ms;
    };
    const expandFirstMs = await expand(0);
    const expandLastMs = await expand(target - 1);

    const longTasks = await page.evaluate(
      () => (window as unknown as { __longTasks?: number }).__longTasks ?? 0
    );

    rows.push({
      runs: target,
      apiMs: apiSamples[1],
      apiKiB: apiBytes / 1024,
      inheritedPerRun,
      loadMs,
      cards: await cards.count(),
      domNodes,
      expandFirstMs,
      expandLastMs,
      longTasks,
    });

    // Printed AS WE GO, not only at the end: a run that times out at 500 still leaves
    // every smaller measurement on the record.
    // eslint-disable-next-line no-console
    console.log(`\n[run-scale] measured through ${target} runs\n${table(rows)}\n`);
  }

  // eslint-disable-next-line no-console
  console.log(`\n[run-scale] FINAL\n${table(rows)}\n`);

  // The ONE assertion, and it is a sanity check on the harness rather than a
  // performance gate: if the page did not render the runs it was given, every number
  // above describes something other than what was asked for.
  expect(rows[rows.length - 1].cards).toBe(COUNTS[COUNTS.length - 1]);
});
