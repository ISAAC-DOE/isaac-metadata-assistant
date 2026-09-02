/*
 * THE CHANGE FEED'S POLLING BEHAVIOUR, MEASURED IN A REAL BROWSER — measurement, not
 * a gate. A `.bench.ts` for `run-scale.bench.ts`'s reasons: it spends minutes SITTING
 * STILL on purpose, and a test whose method is "wait two minutes" does not belong in a
 * suite anyone runs before pushing.
 *
 *     E2E_UVICORN=… npm run bench:runs -- change-feed-poll
 *
 * WHAT IT ANSWERS, and why the questions needed asking rather than reading:
 *
 *   1. HOW MANY REQUESTS DOES AN IDLE RECORD SCREEN ISSUE PER MINUTE? `useChangeFeed`
 *      declares an 8 s cadence with ±20% jitter, and `useRecordSync` declares the same
 *      8 s for a DIFFERENT poller. Two pollers on one screen is a number nobody has
 *      counted, and the arithmetic (60/8 × 2 = 15) is a prediction, not a measurement.
 *   2. DOES POLLING ACTUALLY STOP WHEN THE PAGE IS HIDDEN? Both hooks say they pause,
 *      and they ask DIFFERENT questions to decide it — `document.visibilityState ===
 *      'visible'` in one, `!document.hidden` in the other. The file that diverges says
 *      so and calls both correct; only running it says whether both actually stop.
 *   3. WHAT DOES ONE PROPOSAL EVENT COST? A `proposal` feed entry carries no content
 *      by construction, so SOMETHING has to re-read. The question is what: a bounded
 *      list re-read, or the record's whole bundle.
 *   4. WHAT HAPPENS WHEN THE FEED FAILS? The hook declares exponential backoff to
 *      60 s and `degraded` after three failures. This aborts every feed request at the
 *      transport layer and records the arrival time of each retry.
 *
 * HOW VISIBILITY IS DRIVEN, STATED PLAINLY BECAUSE IT IS THE ONE SIMULATED INPUT IN
 * THIS FILE. Playwright cannot background a tab in headless Chromium, so the hidden
 * state is produced by redefining `document.visibilityState` AND `document.hidden` and
 * dispatching `visibilitychange` — which is exactly the pair of predicates the two
 * hooks read, and exactly the event a real tab switch fires. It is a faithful
 * SIGNAL and it is not an OS-level tab switch; anything a browser does beyond firing
 * that event (throttling timers, for instance) is NOT reproduced here and would only
 * push the measured request count DOWN.
 *
 * EVERY WINDOW IS PAIRED WITH A CONTROL OF THE SAME LENGTH. A count during an event
 * window means nothing without the count during an equally long quiet window, because
 * two pollers are ticking through both.
 *
 * NO TIMING ASSERTION. Request counts and arrival ORDER are what is asserted; the
 * millisecond gaps are printed for reading, and `CLAUDE.md` §7 is why.
 */

import { test, expect } from './own-session-fixtures';
import { MUT_API_BASE, SEED } from './env';
import { TUTORIAL_SESSION_HEADER } from '../worked-example';

const TARGET = SEED.exported;

/** How long each observation window lasts, ms. Overridable for a quick sanity run. */
const WINDOW_MS = Number(process.env.E2E_BENCH_WINDOW_MS ?? 60_000);
/**
 * How many proposals the record holds. The cadence, pause and backoff numbers are
 * scale-INDEPENDENT (they are properties of a timer), but the MOUNT CATCH-UP is not:
 * the feed is bounded at 50 entries a page and a cursorless first poll walks the whole
 * order, so a record holding N proposals costs ceil((N + runs + 1) / 50) pages before
 * the client is current. Run this at 2 and again at 1000.
 */
const PROPOSALS = Number(process.env.E2E_BENCH_PROPOSALS ?? 2);
/** The backoff window has to outlast 8+16+32 s to show the ceiling being approached. */
const BACKOFF_MS = Number(process.env.E2E_BENCH_BACKOFF_MS ?? 150_000);

interface Hit {
  key: string;
  at: number;
}

test('measure the change feed poller: cadence, pause, event cost and backoff', async ({
  page,
  request,
  session,
}) => {
  test.setTimeout(60 * 60 * 1000);

  const headers = { [TUTORIAL_SESSION_HEADER]: session };
  const json = { ...headers, 'content-type': 'application/json' };
  const base = `${MUT_API_BASE}/experiments/${TARGET}`;
  // eslint-disable-next-line no-console
  const log = (s: string) => console.log(s);

  // ---- every API request the PAGE makes, with its arrival time ------------
  const hits: Hit[] = [];
  page.on('request', (r) => {
    const u = r.url();
    if (!u.includes('/api/')) return;
    const key = u
      .replace(/^.*\/api\//, '/')
      .replace(/\?.*$/, '')
      .replace(/\/[0-9A-HJKMNP-TV-Z]{26}/gi, '/{id}');
    hits.push({ key, at: Date.now() });
  });

  const since = (t0: number, t1: number) => hits.filter((h) => h.at >= t0 && h.at < t1);
  const tallyOf = (rows: Hit[]) => {
    const m = new Map<string, number>();
    for (const h of rows) m.set(h.key, (m.get(h.key) ?? 0) + 1);
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  };
  const fmt = (rows: Hit[]) =>
    `${rows.length} total — ${tallyOf(rows).map(([k, n]) => `${k}x${n}`).join(', ') || '(none)'}`;

  const setVisibility = async (visible: boolean) => {
    await page.evaluate((v) => {
      Object.defineProperty(document, 'visibilityState', {
        configurable: true,
        get: () => (v ? 'visible' : 'hidden'),
      });
      Object.defineProperty(document, 'hidden', { configurable: true, get: () => !v });
      document.dispatchEvent(new Event('visibilitychange'));
    }, visible);
  };

  const detailVersion = async (): Promise<string> => {
    const res = await request.get(base, { headers });
    return ((await res.json()) as { version: string }).version;
  };

  // A note and a couple of proposals, so the panel has something to show. The request
  // COUNTS below are about the poller, not about the list size.
  const NOTE_TEXT = 'Synthetic beamline log naming the technique as XAS.';
  const noteRes = await request.post(`${base}/notes`, {
    headers: { ...json, 'If-Match': `"${await detailVersion()}"` },
    data: { text: NOTE_TEXT, source: 'typed_note' },
  });
  expect(noteRes.status()).toBe(201);
  const noteId = ((await noteRes.json()) as { note: { id: string } }).note.id;

  const probe = await request.get(`${base}/proposals?limit=1`, { headers });
  const PATH = ((await probe.json()) as { record_scoped_target_field_paths: string[] })
    .record_scoped_target_field_paths[0];

  let version = await detailVersion();
  const createOne = async (n: number) => {
    const res = await request.post(`${base}/proposals`, {
      headers: { ...json, 'If-Match': `"${version}"` },
      data: {
        note_id: noteId,
        target_field_path: PATH,
        proposed_value: 'XAS',
        rule: `poll bench ${n}`,
      },
    });
    expect(res.status(), `POST /proposals -> ${res.status()} ${await res.text()}`).toBe(200);
    version = ((await res.json()) as { experiment_version: string }).experiment_version;
  };
  const tCreate = Date.now();
  for (let i = 1; i <= PROPOSALS; i += 1) await createOne(i);
  const createMs = Date.now() - tCreate;

  const feedProbe = (await (
    await request.get(`${base}/changes?limit=200`, { headers })
  ).json()) as { returned: number; remaining: number; has_more: boolean };
  const feedEntries = feedProbe.returned + feedProbe.remaining;

  const out: string[] = [];

  // =======================================================================
  // 0 · MOUNT CATCH-UP. A cursorless first poll starts at the beginning of the
  //     order, and `useChangeFeed` fast-follows `has_more` at
  //     CHANGE_FEED_DRAIN_DELAY_MS. This measures what that costs on THIS record.
  //
  //     "Caught up" is defined observably rather than by reading client state: the
  //     drain fires every ~250 ms, the ordinary cadence every ~8 s, so a gap longer
  //     than 6 s after at least one request means the burst is over.
  // =======================================================================
  const tMount = Date.now();
  await page.goto(`/record/${TARGET}`);
  await expect(page.getByRole('heading', { name: 'Ingestion Proposals' })).toBeVisible({
    timeout: 180_000,
  });
  await expect(page.locator('.proposals-count')).not.toBeEmpty({ timeout: 180_000 });
  const panelReadyMs = Date.now() - tMount;

  const feedHits = () => hits.filter((h) => h.key.endsWith('/changes') && h.at >= tMount);
  const deadline = Date.now() + 180_000;
  for (;;) {
    await page.waitForTimeout(500);
    const f = feedHits();
    if (f.length > 0 && Date.now() - f[f.length - 1].at > 6_000) break;
    if (Date.now() > deadline) break;
  }
  const caught = feedHits();
  const caughtGaps = caught.map((h, i) => (i === 0 ? h.at - tMount : h.at - caught[i - 1].at));
  out.push(
    `0 · MOUNT CATCH-UP on a record holding ${PROPOSALS} proposals ` +
      `(${feedEntries} feed entries; created in ${createMs} ms)\n` +
      `    panel showed its count line: ${panelReadyMs} ms after goto\n` +
      `    /changes requests before the burst ended: ${caught.length}\n` +
      `    first /changes at ${caught.length === 0 ? 'n/a' : `${caught[0].at - tMount} ms`}; ` +
      `last at ${caught.length === 0 ? 'n/a' : `${caught[caught.length - 1].at - tMount} ms`}\n` +
      `    gaps (ms, first is from goto): ${caughtGaps.join(', ') || '(none)'}`,
  );

  // =======================================================================
  // 1 · IDLE. Nothing is touched; both pollers tick.
  // =======================================================================
  const idleFrom = Date.now();
  await page.waitForTimeout(WINDOW_MS);
  const idleTo = Date.now();
  const idle = since(idleFrom, idleTo);
  const idleFeed = idle.filter((h) => h.key.endsWith('/changes'));
  const feedGaps = idleFeed
    .map((h, i) => (i === 0 ? null : h.at - idleFeed[i - 1].at))
    .filter((g): g is number => g !== null);
  out.push(
    `1 · IDLE, ${(idleTo - idleFrom) / 1000}s, nothing mutated\n` +
      `    all API requests: ${fmt(idle)}\n` +
      `    per minute (scaled): ${((idle.length * 60_000) / (idleTo - idleFrom)).toFixed(1)}\n` +
      `    /changes requests: ${idleFeed.length}` +
      ` (${((idleFeed.length * 60_000) / (idleTo - idleFrom)).toFixed(1)} / min)\n` +
      `    /changes inter-arrival gaps (ms): ${feedGaps.join(', ') || '(fewer than two)'}`,
  );

  // =======================================================================
  // 2 · HIDDEN.
  // =======================================================================
  await setVisibility(false);
  const hidFrom = Date.now();
  await page.waitForTimeout(WINDOW_MS);
  const hidTo = Date.now();
  const hidden = since(hidFrom, hidTo);
  out.push(
    `2 · HIDDEN, ${(hidTo - hidFrom) / 1000}s (visibilityState='hidden', hidden=true, event fired)\n` +
      `    all API requests: ${fmt(hidden)}\n` +
      `    /changes requests: ${hidden.filter((h) => h.key.endsWith('/changes')).length}`,
  );

  // =======================================================================
  // 3 · BACK TO VISIBLE — does it poll immediately rather than after a cadence?
  // =======================================================================
  const wakeFrom = Date.now();
  await setVisibility(true);
  await page.waitForTimeout(4_000);
  const wake = since(wakeFrom, Date.now());
  const firstFeed = wake.find((h) => h.key.endsWith('/changes'));
  out.push(
    `3 · WAKE, first 4s after visibilitychange -> visible\n` +
      `    all API requests: ${fmt(wake)}\n` +
      `    first /changes after wake: ${
        firstFeed === undefined ? 'none within 4 s' : `${firstFeed.at - wakeFrom} ms`
      }`,
  );

  // =======================================================================
  // 4 · CONTROL then EVENT, two windows of the same length.
  // =======================================================================
  const ctlFrom = Date.now();
  await page.waitForTimeout(20_000);
  const ctlTo = Date.now();
  const control = since(ctlFrom, ctlTo);

  const evFrom = Date.now();
  const heldBefore = (
    (await (await request.get(`${base}/proposals?limit=1`, { headers })).json()) as {
      total: number;
    }
  ).total;
  await createOne(3);
  await expect(page.locator('.proposals-count')).toContainText(`of ${heldBefore + 1} proposal`, {
    timeout: 120_000,
  });
  const settledAt = Date.now();
  // Keep the window the SAME LENGTH as the control so the counts are comparable.
  const remain = ctlTo - ctlFrom - (settledAt - evFrom);
  if (remain > 0) await page.waitForTimeout(remain);
  const evTo = Date.now();
  const event = since(evFrom, evTo);

  out.push(
    `4 · ONE PROPOSAL EVENT vs a QUIET CONTROL of the same length\n` +
      `    control  (${(ctlTo - ctlFrom) / 1000}s, nothing mutated): ${fmt(control)}\n` +
      `    event    (${(evTo - evFrom) / 1000}s, one proposal created out of band): ${fmt(event)}\n` +
      `    create -> panel count line updated: ${settledAt - evFrom} ms`,
  );

  // =======================================================================
  // 5 · BACKOFF. Every feed request is aborted at the transport layer.
  // =======================================================================
  await page.route(
    (url) => url.href.includes('/changes'),
    async (route) => {
      await route.abort('failed');
    },
  );
  const boFrom = Date.now();
  await page.waitForTimeout(BACKOFF_MS);
  const boTo = Date.now();
  const backoff = since(boFrom, boTo);
  const boFeed = backoff.filter((h) => h.key.endsWith('/changes'));
  const boGaps = boFeed.map((h, i) => (i === 0 ? h.at - boFrom : h.at - boFeed[i - 1].at));
  out.push(
    `5 · BACKOFF, ${(boTo - boFrom) / 1000}s with every /changes request aborted\n` +
      `    all API requests: ${fmt(backoff)}\n` +
      `    /changes attempts: ${boFeed.length}\n` +
      `    gaps between successive /changes attempts (ms): ${boGaps.join(', ') || '(none)'}\n` +
      `    requests/min during failure: ${(
        (backoff.length * 60_000) /
        (boTo - boFrom)
      ).toFixed(1)}`,
  );

  // =======================================================================
  // 6 · WHO ACTUALLY PAYS FOR AN EVENT? The feed is STILL being aborted here, so
  //     `useChangeFeed` cannot learn anything. A proposal is created anyway. If the
  //     record's whole bundle is refetched regardless, the bundle refetch belongs to
  //     `useRecordSync` (which polls `GET /experiments/{id}` and refetches on a
  //     version change) and NOT to the change feed — a proposal create advances the
  //     record's rev. Attribution matters: one is a pre-existing cost of any write,
  //     the other would be a defect in this feature.
  // =======================================================================
  const blindFrom = Date.now();
  await createOne(99);
  await page.waitForTimeout(20_000);
  const blind = since(blindFrom, Date.now());
  out.push(
    `6 · ONE PROPOSAL EVENT WITH THE FEED STILL ABORTED, 20s\n` +
      `    all API requests: ${fmt(blind)}\n` +
      `    (compare with 4's control and event windows above)`,
  );

  log(`\n[change-feed-poll] RESULTS\n\n${out.join('\n\n')}\n`);

  // The only assertions: shape, never duration.
  expect(
    hidden.filter((h) => h.key.endsWith('/changes')).length,
    'a hidden page must issue no change-feed requests',
  ).toBe(0);
  expect(boFeed.length, 'a failing feed must not stop retrying entirely').toBeGreaterThan(0);
});
