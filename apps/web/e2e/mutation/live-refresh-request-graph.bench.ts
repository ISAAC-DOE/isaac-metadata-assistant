/*
 * WHAT ONE LIVE EVENT COSTS THE RECORD SCREEN, IN A REAL BROWSER — measurement, not a
 * gate. A `.bench.ts` for `run-scale.bench.ts`'s reasons: it creates runs and then
 * SITS STILL waiting for two 8 s pollers, and a test whose method is "wait half a
 * minute" does not belong in a suite anyone runs before pushing.
 *
 *     E2E_UVICORN=/…/.venv/bin/uvicorn npm run bench:runs -- live-refresh-request-graph
 *     E2E_BENCH_RUNS=25 …            # how many runs the record holds
 *
 * ── WHY IT EXISTS BESIDE THE VITEST FILE ────────────────────────────────────────
 *
 * `apps/web/src/__tests__/live-refresh-request-graph.test.tsx` counts the same request
 * graph and is the GUARD; it runs in jsdom against a fetch stub, so its counts are
 * exact and its BYTES do not exist — there is no wire, no serialisation and no server.
 * Bytes and server timings are the numbers that make the case for bounding the read at
 * all, and they can only be taken here.
 *
 * ── WHAT IS MEASURED, AND WHAT IS DELIBERATELY NOT ──────────────────────────────
 *
 * Measured: request COUNT per route, RESPONSE BODY BYTES per route (from Playwright's
 * own `request.sizes()`, not from a body this file reads and could disturb), and the
 * DOM node count of the loaded screen. Those are deterministic for a given workload.
 *
 * NOT asserted: milliseconds. `CLAUDE.md` §7 records a wall-clock figure being excluded
 * from every verdict because concurrent agents contaminated it; the same discipline
 * applies here. Server timings ARE printed, for reading, with the machine's load beside
 * them — no assertion in this file is a timing assertion.
 *
 * NOT measured at all, and stated rather than left to be discovered: browser update
 * LATENCY (event → DOM change) is not separable here from the poll cadence, which is
 * 8 s with ±20 % jitter and dominates it by two orders of magnitude; and long tasks,
 * because `PerformanceObserver('longtask')` is not delivered in this harness's headless
 * Chromium for the durations involved. Neither is estimated.
 */

import { test, expect } from './own-session-fixtures';
import { MUT_API_BASE, SEED } from './env';
import { TUTORIAL_SESSION_HEADER } from '../worked-example';

/** How many runs the record under test holds. More runs → a longer question list. */
const RUNS = Number(process.env.E2E_BENCH_RUNS ?? 25);
/** How long to watch after the out-of-band edit. Two cadences plus slack. */
const WATCH_MS = Number(process.env.E2E_BENCH_WATCH_MS ?? 25_000);

const TARGET = SEED.ready;

interface Hit {
  key: string;
  at: number;
  bytes: number;
}

test('measure the record screen live-refresh request graph', async ({ page, request, session }) => {
  test.setTimeout(30 * 60 * 1000);

  const headers = { [TUTORIAL_SESSION_HEADER]: session };
  const json = { ...headers, 'content-type': 'application/json' };
  const base = `${MUT_API_BASE}/experiments/${TARGET}`;
  // eslint-disable-next-line no-console
  const log = (s: string) => console.log(s);

  /*
   * NOTE ON DOUBLED COUNTS. The dev server renders under React `StrictMode`, which
   * mounts every effect twice — so the browser figures below are ~2× the number of
   * distinct reads a production build issues. That is a property of the harness, not of
   * the code, it applies EQUALLY to the before and after runs, and the exact per-read
   * counts are the vitest ones. The bytes are what this file is for.
   */
  const hits: Hit[] = [];
  page.on('requestfinished', (r) => {
    const u = r.url();
    if (!u.includes('/api/')) return;
    const path = u.replace(/^.*\/api\//, '/').replace(/\/[0-9A-HJKMNP-TV-Z]{26}/gi, '/{id}');
    // Keep the QUERY: `?limit=10` versus no query at all is the entire point of the
    // change under measurement, and a key that stripped it would hide it.
    void r
      .sizes()
      .then((s) => hits.push({ key: `${r.method()} ${path}`, at: Date.now(), bytes: s.responseBodySize }))
      .catch(() => {
        /* a request whose sizes are unavailable is recorded with none rather than dropped */
        hits.push({ key: `${r.method()} ${path}`, at: Date.now(), bytes: 0 });
      });
  });

  const since = (t0: number) => hits.filter((h) => h.at >= t0);
  const report = (label: string, rows: Hit[]) => {
    const m = new Map<string, { n: number; bytes: number }>();
    for (const h of rows) {
      const e = m.get(h.key) ?? { n: 0, bytes: 0 };
      m.set(h.key, { n: e.n + 1, bytes: e.bytes + h.bytes });
    }
    const total = rows.reduce((a, h) => a + h.bytes, 0);
    log(`\n#### ${label} — ${rows.length} requests, ${total} response bytes`);
    for (const [k, v] of [...m.entries()].sort((a, b) => b[1].bytes - a[1].bytes)) {
      log(`  ${String(v.n).padStart(3)}  ${String(v.bytes).padStart(9)} B  ${k}`);
    }
    return { requests: rows.length, bytes: total };
  };

  const detailVersion = async (): Promise<string> =>
    ((await (await request.get(base, { headers })).json()) as { version: string }).version;

  // ---- build a record with enough runs that its question list is worth bounding ----
  let version = await detailVersion();
  for (let i = 0; i < RUNS; i += 1) {
    const res = await request.post(`${base}/runs`, {
      headers: { ...json, 'If-Match': `"${version}"` },
      data: { label: `bench run ${i}` },
    });
    expect(res.ok(), `POST /runs #${i}: ${res.status()} ${await res.text()}`).toBeTruthy();
    version = ((await res.json()) as { experiment_version: string }).experiment_version;
  }
  const pendingProbe = (await (
    await request.get(`${base}/pending`, { headers })
  ).json()) as { pending: unknown[] };
  log(`\nrecord ${TARGET}: ${RUNS} runs, ${pendingProbe.pending.length} open questions`);

  // ---- A · first paint -------------------------------------------------------
  const tMount = Date.now();
  await page.goto(`/record/${TARGET}`);
  await expect(page.getByRole('heading', { name: 'Runs' })).toBeVisible({ timeout: 180_000 });
  await page.waitForTimeout(2_000); // let the mount's fan-out finish arriving
  const paint = report('A · first paint', since(tMount));
  const domNodes = await page.evaluate(() => document.getElementsByTagName('*').length);
  log(`  DOM nodes after first paint: ${domNodes}`);

  // ---- B · ONE out-of-band edit, watched for two cadences ---------------------
  //
  // A SECOND CLIENT makes the change, which is the scenario the whole feature is for.
  // The page is not touched, so everything counted below is the pollers' doing.
  const runs = (await (
    await request.get(`${base}/runs?limit=1`, { headers })
  ).json()) as { runs: { id: string; version: string }[] };
  const run = runs.runs[0];

  const tEdit = Date.now();
  const patched = await request.patch(`${base}/runs/${run.id}`, {
    headers: { ...json, 'If-Match': `"${run.version}"` },
    data: { label: 'bench run edited elsewhere', confirmed_by_user: true },
  });
  expect(patched.ok(), `PATCH run: ${patched.status()} ${await patched.text()}`).toBeTruthy();

  await page.waitForTimeout(WATCH_MS);
  const event = report(`B · one run edited by another client, watched ${WATCH_MS} ms`, since(tEdit));

  // ---- C · a QUIET control window of the same length --------------------------
  //
  // A count during an event window means nothing without the count during an equally
  // long quiet window: two pollers are ticking through both.
  const tQuiet = Date.now();
  await page.waitForTimeout(WATCH_MS);
  const quiet = report(`C · CONTROL: ${WATCH_MS} ms with nothing happening`, since(tQuiet));

  log(
    `\nSUMMARY  paint=${paint.requests}req/${paint.bytes}B  ` +
      `event=${event.requests}req/${event.bytes}B  quiet=${quiet.requests}req/${quiet.bytes}B  ` +
      `dom=${domNodes}  runs=${RUNS}  questions=${pendingProbe.pending.length}`,
  );

  // The ONE assertion, and it is the slice's invariant rather than a number: no live
  // event may issue the unbounded question read. A count would be a timing assertion.
  const unbounded = since(tEdit).filter((h) => h.key === `GET /experiments/{id}/pending`);
  expect(
    unbounded.map((h) => h.key),
    'a live event must never issue the unbounded GET /pending',
  ).toEqual([]);
});
