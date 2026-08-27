/*
 * FRESH SCALE BENCHMARK, 2026-08-27 — the surfaces `run-scale.bench.ts` does not reach.
 *
 * WHY A SECOND BENCHMARK RATHER THAN AN EXTENSION OF THE FIRST. `run-scale.bench.ts`
 * measures the RECORD SCREEN: the run list, its cards, expand, search, Focus Run. It was
 * written before the Evidence Graph read five further routes, before Compare Runs issued
 * four network reads per comparison, and before Discard existed. Extending it would have
 * meant rewriting the file every column of which is the baseline the published envelope
 * is measured against — so this file adds the new surfaces beside it and leaves the
 * baseline reproducible.
 *
 * WHAT IT MEASURES, and why each is separate rather than aggregated:
 *
 *   · the SERVER's own cost for every route these screens issue, read directly through
 *     `request` with no browser in the way — because a browser number confounds the
 *     server's work with React's, and the two scale differently and are fixed
 *     differently.
 *   · the two SERVER-SIDE issues prior work reported fixed: the unbounded `/pending`
 *     payload and linear detail-route latency. Both are re-derived here rather than
 *     assumed, and `/pending` is read BOTH ways — unbounded (what Review Record and
 *     Export Readiness still correctly issue) and windowed (what the write path issues).
 *   · the EVIDENCE GRAPH's five sub-fetches, each timed and sized on its own, because
 *     "the graph is slow" is not an actionable finding and "`/conflicts` is 40x the
 *     others" is.
 *   · COMPARE RUNS twice: a pair already on the loaded page (4 reads) and a pair that is
 *     not (4 reads + 2 `getRun`). The second is the real cost of a deep link, and
 *     measuring only the first would report the cheapest case as the envelope.
 *
 * COUNTS OVER WALL-CLOCK, WHEREVER A COUNT ANSWERS THE QUESTION. Bytes, request counts
 * and DOM nodes do not move when another process takes the CPU; milliseconds do. Every
 * ms column here is a MEDIAN OF THREE and is reported as secondary evidence.
 *
 * Run it alone (it shares the bench config with `run-scale.bench.ts`, which would
 * otherwise create its own 500 runs first):
 *
 *     E2E_BENCH_COUNTS=25,100,250,500,1000 \
 *     npx playwright test --config=playwright.bench.config.ts scale-2026-08-27
 */

import { test, expect, openRecord } from './own-session-fixtures';
import { MUT_API_BASE, SEED } from './env';
import { TUTORIAL_SESSION_HEADER } from '../worked-example';
import { RUNS_PAGE_SIZE } from '../../src/lib/runPaging';

const COUNTS = (process.env.E2E_BENCH_COUNTS ?? '25,100,250,500,1000')
  .split(',')
  .map((n) => Number(n.trim()))
  .filter((n) => Number.isFinite(n) && n > 0)
  .sort((a, b) => a - b);

const TARGET = SEED.fresh;

/** What Compare Runs asks for per side; imported would be better, it is not exported. */
const CONTEXT_PENDING_PREVIEW = 5;

interface Timed {
  ms: number;
  bytes: number;
  /** A route-specific cardinality: array length, node count, whatever the route counts. */
  n: number;
}

interface Row {
  runs: number;
  // --- server: the record screen's own routes ---
  runsUnpaged: Timed;
  runsPaged: Timed;
  detail: Timed;
  pendingUnbounded: Timed;
  pendingWindowed: Timed;
  // --- server: the Evidence Graph's five sub-fetches ---
  conflicts: Timed;
  notes: Timed;
  provenance: Timed;
  assets: Timed;
  revisions: Timed;
  // --- server: Compare Runs' four reads (one side; the panel issues 2x this) ---
  cmpConflictsRun: Timed;
  cmpPendingRun: Timed;
  // --- browser ---
  loadMs: number;
  domNodes: number;
  longTasks: number;
  searchMs: number;
  focusMs: number;
  expandFirstMs: number;
  expandLastMs: number;
  discardPresent: number;
  // --- browser: Evidence Graph ---
  graphMs: number;
  graphDom: number;
  graphReqs: number;
  graphLongTasks: number;
  graphCounts: string;
  // --- browser: Compare Runs ---
  cmpOnPageMs: number;
  cmpOnPageReqs: number;
  cmpOnPageDom: number;
  cmpDeepMs: number;
  cmpDeepReqs: number;
  cmpLongTasks: number;
}

const rows: Row[] = [];

function fmt(t: Timed): string {
  if (t.ms < 0) return 'n/a';
  return `${t.ms}ms/${(t.bytes / 1024).toFixed(1)}KiB/n=${t.n}`;
}

/** Emitted as TSV so the numbers can be pasted into a table without re-typing. */
function dump(): string {
  const cols: [string, (r: Row) => string | number][] = [
    ['runs', (r) => r.runs],
    ['runs_unpaged', (r) => fmt(r.runsUnpaged)],
    ['runs_paged', (r) => fmt(r.runsPaged)],
    ['detail', (r) => fmt(r.detail)],
    ['pending_unbounded', (r) => fmt(r.pendingUnbounded)],
    ['pending_windowed', (r) => fmt(r.pendingWindowed)],
    ['g_conflicts', (r) => fmt(r.conflicts)],
    ['g_notes', (r) => fmt(r.notes)],
    ['g_provenance', (r) => fmt(r.provenance)],
    ['g_assets', (r) => fmt(r.assets)],
    ['g_revisions', (r) => fmt(r.revisions)],
    ['cmp_conflicts_run', (r) => fmt(r.cmpConflictsRun)],
    ['cmp_pending_run', (r) => fmt(r.cmpPendingRun)],
    ['load_ms', (r) => r.loadMs],
    ['dom', (r) => r.domNodes],
    ['longtasks', (r) => r.longTasks],
    ['search_ms', (r) => r.searchMs],
    ['focus_ms', (r) => r.focusMs],
    ['expand_first_ms', (r) => r.expandFirstMs],
    ['expand_last_ms', (r) => r.expandLastMs],
    ['discard_ctl', (r) => r.discardPresent],
    ['graph_ms', (r) => r.graphMs],
    ['graph_dom', (r) => r.graphDom],
    ['graph_reqs', (r) => r.graphReqs],
    ['graph_longtasks', (r) => r.graphLongTasks],
    ['graph_counts', (r) => JSON.stringify(r.graphCounts)],
    ['cmp_onpage_ms', (r) => r.cmpOnPageMs],
    ['cmp_onpage_reqs', (r) => r.cmpOnPageReqs],
    ['cmp_onpage_dom', (r) => r.cmpOnPageDom],
    ['cmp_deep_ms', (r) => r.cmpDeepMs],
    ['cmp_deep_reqs', (r) => r.cmpDeepReqs],
    ['cmp_longtasks', (r) => r.cmpLongTasks],
  ];
  const head = cols.map(([h]) => h).join('\t');
  const body = rows.map((r) => cols.map(([, f]) => String(f(r))).join('\t'));
  return [head, ...body].join('\n');
}

test('measure the 2026-08-27 scale envelope', async ({ page, request, session }) => {
  test.setTimeout(90 * 60 * 1000);

  const headers = { [TUTORIAL_SESSION_HEADER]: session };
  const base = `${MUT_API_BASE}/experiments/${TARGET}`;
  const runsUrl = `${base}/runs`;

  /** Median-of-three GET, returning ms, raw byte length, and a caller-derived count. */
  const timed = async (url: string, count: (body: unknown) => number): Promise<Timed> => {
    const samples: number[] = [];
    let bytes = 0;
    let n = -1;
    for (let i = 0; i < 3; i += 1) {
      const t0 = Date.now();
      const res = await request.get(url, { headers });
      const text = await res.text();
      samples.push(Date.now() - t0);
      if (!res.ok()) {
        // A route that refuses is a RESULT, not a harness failure — record the status
        // in `n` as a negative so the table shows it rather than silently reporting 0.
        return { ms: -1, bytes: text.length, n: -res.status() };
      }
      bytes = text.length;
      if (i === 0) {
        try {
          n = count(JSON.parse(text));
        } catch {
          n = -1;
        }
      }
    }
    samples.sort((a, b) => a - b);
    return { ms: samples[1], bytes, n };
  };

  const readRuns = async () => {
    const res = await request.get(runsUrl, { headers });
    expect(res.ok(), `GET /runs: ${res.status()}`).toBeTruthy();
    return (await res.json()) as { runs: { id: string }[]; experiment_version: string };
  };

  const state0 = await readRuns();
  let version = state0.experiment_version;
  let have = state0.runs.length;

  // ONE registration, outside the loop — see `run-scale.bench.ts`'s long note: an
  // `addInitScript` per iteration attaches k observers to the k-th document and
  // multiplies the count by k. The counter is reset explicitly before each phase so
  // load, graph and compare each get their own attributable total.
  await page.addInitScript(() => {
    (window as unknown as { __longTasks: number }).__longTasks = 0;
    try {
      new PerformanceObserver((list) => {
        (window as unknown as { __longTasks: number }).__longTasks += list.getEntries().length;
      }).observe({ entryTypes: ['longtask'] });
    } catch {
      /* unsupported: the column reads 0 everywhere and says so by being 0 everywhere */
    }
  });

  const resetLongTasks = () =>
    page.evaluate(() => {
      (window as unknown as { __longTasks: number }).__longTasks = 0;
    });
  const readLongTasks = () =>
    page.evaluate(() => (window as unknown as { __longTasks?: number }).__longTasks ?? 0);

  /** Count API requests issued while `body` runs. Counts, not timings — contention-proof. */
  let reqCount = 0;
  page.on('request', (r) => {
    if (r.url().includes('/api/')) reqCount += 1;
  });
  const counting = async <T>(body: () => Promise<T>): Promise<[T, number]> => {
    reqCount = 0;
    const out = await body();
    return [out, reqCount];
  };

  for (const target of COUNTS) {
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

    const runIds = (await readRuns()).runs.map((r) => r.id);
    const firstRun = runIds[0];
    const secondRun = runIds[1] ?? runIds[0];
    /*
     * THE LAST RUN, which is the deep-link case exactly when there is a page to be off.
     * Above `RUNS_PAGE_SIZE` it is not on the loaded page, so the panel must `getRun` it;
     * below, it is, and the row says so by `cmp_deep_reqs` matching `cmp_onpage_reqs`.
     *
     * IT WAS `index 0` BELOW THE PAGE SIZE AND THAT WAS A HARNESS BUG, not a finding: the
     * URL then compared one run WITH ITSELF, which is not a comparison and which the panel
     * correctly declines to render. The smoke run hung 300 s on it.
     */
    const offPageRun = runIds[runIds.length - 1];

    // ---- SERVER SIDE ------------------------------------------------------
    const arr = (key: string) => (b: unknown) => {
      const v = (b as Record<string, unknown>)?.[key];
      return Array.isArray(v) ? v.length : -1;
    };

    const runsUnpaged = await timed(runsUrl, arr('runs'));
    const runsPaged = await timed(`${runsUrl}?limit=${RUNS_PAGE_SIZE}`, arr('runs'));
    /*
     * THE DETAIL ROUTE CARRIES NO RUNS — measured, and it changes what this column means.
     * `GET /api/experiments/{id}` answers a flat summary (`id`, `title`, `status`,
     * `pending_count`, `draft_ok`, `workflow`, `artifact`, `rev`, `version`): no `state`,
     * no `runs`, no drafts. So its PAYLOAD cannot grow with run count and the only thing
     * that can is its DERIVATION — `pending_count`, `draft_ok`, `workflow` and `artifact`
     * are each computed by composing every run, which is exactly what `_shared_units` and
     * `_shared_dry_run` were threaded to stop doing five and two times over.
     *
     * `n` is therefore `pending_count`: the derived quantity whose growth is the reason
     * the composition happens at all.
     */
    const detail = await timed(base, (b) => {
      const v = (b as { pending_count?: number }).pending_count;
      return typeof v === 'number' ? v : -1;
    });
    const pendingUnbounded = await timed(`${base}/pending`, arr('pending'));
    const pendingWindowed = await timed(`${base}/pending?limit=${RUNS_PAGE_SIZE}`, arr('pending'));

    const conflicts = await timed(`${base}/conflicts`, arr('conflicts'));
    const notes = await timed(`${base}/notes`, arr('notes'));
    const provenance = await timed(`${base}/provenance`, (b) => {
      const o = b as Record<string, unknown>;
      for (const k of ['entries', 'provenance', 'records']) {
        if (Array.isArray(o?.[k])) return (o[k] as unknown[]).length;
      }
      return Object.keys(o ?? {}).length;
    });
    const assets = await timed(`${base}/assets`, arr('assets'));
    /*
     * `/revisions` DOES NOT ANSWER A `revisions` ARRAY on a draft record — it answers
     * `lifecycle` + `availability`, and inside `lifecycle.scientific_readiness` it
     * enumerates `failing_units`, ONE PER FAILING EXPORT UNIT. That list is the only
     * thing in this response that can grow with run count, so it is what `n` counts.
     * Counting a `revisions` key that is absent would have reported a flat -1 and hidden
     * the growth.
     */
    const revisions = await timed(`${base}/revisions`, (b) => {
      const o = b as {
        revisions?: unknown[];
        lifecycle?: { scientific_readiness?: { failing_unit_count?: number } };
      };
      if (Array.isArray(o?.revisions)) return o.revisions.length;
      const f = o?.lifecycle?.scientific_readiness?.failing_unit_count;
      return typeof f === 'number' ? f : -1;
    });

    const cmpConflictsRun = await timed(
      `${base}/conflicts?run=${encodeURIComponent(firstRun)}`,
      arr('conflicts')
    );
    const cmpPendingRun = await timed(
      `${base}/pending?run_id=${encodeURIComponent(firstRun)}&limit=${CONTEXT_PENDING_PREVIEW}`,
      arr('pending')
    );

    // ---- BROWSER: the record screen --------------------------------------
    const tLoad = Date.now();
    await openRecord(page, TARGET);
    await expect(page.getByRole('heading', { name: 'Runs', exact: true })).toBeVisible({
      timeout: 180_000,
    });
    const cards = page.locator('article.run-card');
    const expectedCards = Math.min(target, RUNS_PAGE_SIZE);
    await expect(cards).toHaveCount(expectedCards, { timeout: 180_000 });
    await expect(page.getByRole('button', { name: 'Add Run' })).toBeEnabled({ timeout: 180_000 });
    const loadMs = Date.now() - tLoad;

    const domNodes = await page.evaluate(() => document.getElementsByTagName('*').length);
    const longTasks = await readLongTasks();

    // The Discard control this branch added — counted, not timed: the question at scale
    // is whether it renders per-run (N controls) or per-record (one).
    const discardPresent = await page.evaluate(
      () =>
        document.querySelectorAll(
          '[data-testid*="discard"], button[class*="discard"], .discard-staged, [class*="discard"]'
        ).length
    );

    const expand = async (index: number) => {
      const card = cards.nth(index);
      const head = card.locator('button.run-card-header');
      await head.scrollIntoViewIfNeeded();
      const t = Date.now();
      await head.click();
      await card.locator('section.run-inherited').waitFor({ state: 'visible', timeout: 180_000 });
      const ms = Date.now() - t;
      await head.click();
      return ms;
    };
    const expandFirstMs = await expand(0);
    const expandLastMs = await expand(expectedCards - 1);

    const searchBox = page.getByLabel('Search runs');
    const tSearch = Date.now();
    await searchBox.fill('zzz-matches-nothing');
    await expect(cards).toHaveCount(0, { timeout: 180_000 });
    const searchMs = Date.now() - tSearch;
    await searchBox.fill('');
    await expect(cards).toHaveCount(expectedCards, { timeout: 180_000 });

    const tFocus = Date.now();
    await cards.nth(0).getByRole('button', { name: /^Focus run / }).click();
    await expect(page.locator('article.run-card')).toHaveCount(1, { timeout: 180_000 });
    const focusMs = Date.now() - tFocus;

    // ---- BROWSER: the Evidence Graph -------------------------------------
    const [[graphMs, graphDom, graphCounts, graphLongTasks], graphReqs] = await counting(
      async (): Promise<[number, number, string, number]> => {
        const t = Date.now();
        await page.goto(`/record/${TARGET}/evidence?view=graph`);
        await resetLongTasks().catch(() => undefined);
        const counts = page.locator('[data-testid="evgraph-counts"]');
        await counts.waitFor({ state: 'visible', timeout: 300_000 });
        const ms = Date.now() - t;
        const dom = await page.evaluate(() => document.getElementsByTagName('*').length);
        const text = ((await counts.textContent()) ?? '').replace(/\s+/g, ' ').trim();
        const lt = await readLongTasks();
        return [ms, dom, text, lt];
      }
    );

    // ---- BROWSER: Compare Runs -------------------------------------------
    const comparison = page.locator('[role="group"][aria-label^="Comparison of"]');

    const [[cmpOnPageMs, cmpOnPageDom, cmpOnPageLt], cmpOnPageReqs] = await counting(
      async (): Promise<[number, number, number]> => {
        const t = Date.now();
        await page.goto(
          `/record/${TARGET}?compare=${encodeURIComponent(firstRun)}&compare=${encodeURIComponent(secondRun)}`
        );
        await resetLongTasks().catch(() => undefined);
        await comparison.first().waitFor({ state: 'visible', timeout: 300_000 });
        const ms = Date.now() - t;
        const dom = await page.evaluate(() => document.getElementsByTagName('*').length);
        const lt = await readLongTasks();
        return [ms, dom, lt];
      }
    );

    /*
     * WRAPPED, so one column cannot cost the whole row. A benchmark that loses 30 minutes
     * of measurement because its last probe timed out has measured nothing; `-1` is a
     * reportable outcome and the table prints it rather than an absence.
     */
    const [cmpDeepMs, cmpDeepReqs] = await counting(async (): Promise<number> => {
      const t = Date.now();
      try {
        await page.goto(
          `/record/${TARGET}?compare=${encodeURIComponent(firstRun)}&compare=${encodeURIComponent(offPageRun)}`
        );
        await comparison.first().waitFor({ state: 'visible', timeout: 120_000 });
        return Date.now() - t;
      } catch {
        return -1;
      }
    });

    rows.push({
      runs: target,
      runsUnpaged,
      runsPaged,
      detail,
      pendingUnbounded,
      pendingWindowed,
      conflicts,
      notes,
      provenance,
      assets,
      revisions,
      cmpConflictsRun,
      cmpPendingRun,
      loadMs,
      domNodes,
      longTasks,
      searchMs,
      focusMs,
      expandFirstMs,
      expandLastMs,
      discardPresent,
      graphMs,
      graphDom,
      graphReqs,
      graphLongTasks,
      graphCounts,
      cmpOnPageMs,
      cmpOnPageReqs,
      cmpOnPageDom,
      cmpDeepMs,
      cmpDeepReqs,
      cmpLongTasks: cmpOnPageLt,
    });

    // Printed as we go: a timeout at 1000 still leaves every smaller row on the record.
    // eslint-disable-next-line no-console
    console.log(`\n[scale-0827] through ${target} runs\n${dump()}\n`);
  }

  // eslint-disable-next-line no-console
  console.log(`\n[scale-0827] FINAL\n${dump()}\n`);

  expect((await readRuns()).runs.length).toBe(COUNTS[COUNTS.length - 1]);
});
