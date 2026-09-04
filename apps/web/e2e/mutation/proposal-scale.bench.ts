/*
 * THE INGESTION-PROPOSAL READ PATH, MEASURED — measurement, not a gate.
 *
 * WHY IT IS A `.bench.ts`. Same reason as `run-scale.bench.ts`: both Playwright
 * configs select `*.spec.ts`, so nothing collects this by default. It creates up to
 * `_MAX_PROPOSALS_PER_RECORD` proposals (minutes, not seconds) and its output is a
 * MEASUREMENT to read, not a pass/fail contract. Run it explicitly:
 *
 *     E2E_BENCH_COUNTS=25 npm run bench:runs -- proposal-scale
 *     E2E_BENCH_COUNTS=25,100,250,500,1000 npm run bench:runs -- proposal-scale
 *
 * WHAT IT ANSWERS. `routes.py` DECLARES four bounds on this path —
 * `_PROPOSAL_WINDOW_DEFAULT` 50, `_PROPOSAL_WINDOW_MAX` 200,
 * `_MAX_PROPOSALS_PER_RECORD` 1000, `_MAX_PROPOSAL_BYTES` 256 KiB — and their own
 * comments say, in the repository's own words, "THIS NUMBER IS NOT DERIVED FROM A
 * MEASUREMENT, AND SAYING SO IS PART OF IT" and "NOTHING HERE HAS MEASURED A PARSE OR
 * A HASH COST at any document size". So this file measures what the declared bounds
 * actually cost and whether they are actually enforced — it READS none of them off
 * the source as a claim, it probes each one over HTTP.
 *
 * FIGURES CONTENTION CANNOT MOVE ARE PREFERRED. `CLAUDE.md` §7 records a wall-clock
 * measurement being excluded from every verdict because concurrent agents contaminated
 * it. Bytes, entry counts, request counts, DOM node counts and status codes are
 * deterministic for a given workload; milliseconds on a shared laptop are not. Both
 * are printed, and the header line records the machine's load so a reader can discount
 * the millisecond columns. No assertion in this file is a timing assertion.
 *
 * WHAT IT DELIBERATELY DOES NOT MEASURE: memory, for `run-scale.bench.ts`'s reason.
 */

import { test, expect } from './own-session-fixtures';
import { MUT_API_BASE, SEED } from './env';
import { TUTORIAL_SESSION_HEADER } from '../worked-example';

const COUNTS = (process.env.E2E_BENCH_COUNTS ?? '25,100,250,500,1000')
  .split(',')
  .map((n) => Number(n.trim()))
  .filter((n) => Number.isFinite(n) && n > 0)
  .sort((a, b) => a - b);

/** The record the proposals are hung on. Exported, so no other axis interferes. */
const TARGET = SEED.exported;

/** Bytes on the wire, not UTF-16 code units — `text.length` is the latter. */
const bytes = (s: string) => Buffer.byteLength(s, 'utf8');

/** Median of three, sorted; the middle sample. */
const median3 = (xs: number[]) => xs.slice().sort((a, b) => a - b)[1];

interface Row {
  held: number;
  /** `GET /proposals` with NO `limit` — what the panel itself issues. */
  defMs: number;
  defBytes: number;
  defReturned: number;
  defTotal: number;
  defHasMore: boolean;
  /** `limit=200`, the declared window maximum. */
  maxMs: number;
  maxBytes: number;
  maxReturned: number;
  /** `limit=1` — the per-window floor, i.e. the fixed part of the body. */
  oneBytes: number;
  /** Walking the whole list at `limit=200`: requests and total bytes. */
  walkRequests: number;
  walkBytes: number;
  walkMs: number;
  /** `GET /proposals/{id}` for the FIRST and the LAST proposal in feed order. */
  detailFirstMs: number;
  detailLastMs: number;
  detailBytes: number;
  /** `GET /changes` with no limit (server default 50). */
  feedMs: number;
  feedBytes: number;
  feedReturned: number;
  feedRemaining: number;
  feedProposalEntries: number;
  /** One `proposal` entry, re-serialised on its own. */
  feedProposalEntryBytes: number;
  /** `GET /changes?limit=200`. */
  feed200Bytes: number;
  feed200Returned: number;
  /** Browser: cards rendered, whole-document DOM nodes, and goto -> count line. */
  cards: number;
  domNodes: number;
  openMs: number;
}

function table(rows: Row[]): string {
  const head =
    '   held | def ms | def B | ret | more | 200 ms |  200 B | ret | limit1 B | walk req | walk B | walk ms | det1 ms | detN ms | det B | feed ms | feed B | ret | rem | prop | 1 entry B | f200 B | ret | cards | DOM nodes | open ms';
  const body = rows.map((r) =>
    [
      String(r.held).padStart(7),
      r.defMs.toFixed(0).padStart(6),
      String(r.defBytes).padStart(6),
      String(r.defReturned).padStart(3),
      String(r.defHasMore).padStart(5),
      r.maxMs.toFixed(0).padStart(6),
      String(r.maxBytes).padStart(7),
      String(r.maxReturned).padStart(3),
      String(r.oneBytes).padStart(8),
      String(r.walkRequests).padStart(8),
      String(r.walkBytes).padStart(7),
      r.walkMs.toFixed(0).padStart(7),
      r.detailFirstMs.toFixed(0).padStart(7),
      r.detailLastMs.toFixed(0).padStart(7),
      String(r.detailBytes).padStart(6),
      r.feedMs.toFixed(0).padStart(7),
      String(r.feedBytes).padStart(6),
      String(r.feedReturned).padStart(3),
      String(r.feedRemaining).padStart(4),
      String(r.feedProposalEntries).padStart(4),
      String(r.feedProposalEntryBytes).padStart(9),
      String(r.feed200Bytes).padStart(6),
      String(r.feed200Returned).padStart(3),
      String(r.cards).padStart(5),
      String(r.domNodes).padStart(9),
      r.openMs.toFixed(0).padStart(7),
    ].join(' |'),
  );
  return [head, ''.padEnd(head.length, '-'), ...body].join('\n');
}

test('measure the ingestion-proposal read path and the change feed', async ({
  page,
  request,
  session,
}) => {
  test.setTimeout(120 * 60 * 1000);

  const headers = { [TUTORIAL_SESSION_HEADER]: session };
  const json = { ...headers, 'content-type': 'application/json' };
  const base = `${MUT_API_BASE}/experiments/${TARGET}`;

  // eslint-disable-next-line no-console
  const log = (s: string) => console.log(s);

  const detailVersion = async (): Promise<string> => {
    const res = await request.get(base, { headers });
    expect(res.ok(), `GET /experiments -> ${res.status()}`).toBeTruthy();
    return ((await res.json()) as { version: string }).version;
  };

  // ---- one note, cited by every proposal ---------------------------------
  // Every proposal must cite a note (`note_id` is required and never invented). One
  // note is enough and is the realistic shape: an extraction pass over one document.
  const NOTE_TEXT =
    'Synthetic beamline log for the committed XANES seed. It records the technique ' +
    'as XAS on every line of the campaign sheet, which is what these proposals read.';
  const noteRes = await request.post(`${base}/notes`, {
    headers: { ...json, 'If-Match': `"${await detailVersion()}"` },
    data: { text: NOTE_TEXT, source: 'typed_note' },
  });
  expect(noteRes.status(), `POST /notes -> ${noteRes.status()} ${await noteRes.text()}`).toBe(201);
  const noteId = ((await noteRes.json()) as { note: { id: string } }).note.id;

  // ---- the target path, read from the SERVER rather than transcribed -----
  const probe = await request.get(`${base}/proposals?limit=1`, { headers });
  expect(probe.ok(), `GET /proposals -> ${probe.status()}`).toBeTruthy();
  const probeBody = (await probe.json()) as {
    total: number;
    record_scoped_target_field_paths: string[];
    window_default: number;
    window_max: number;
    max_per_record: number;
  };
  const PATH = probeBody.record_scoped_target_field_paths[0];
  expect(PATH, 'this build must offer at least one record-scoped target path').toBeTruthy();
  log(
    `\n[proposal-scale] server-declared bounds: window_default=${probeBody.window_default} ` +
      `window_max=${probeBody.window_max} max_per_record=${probeBody.max_per_record} ` +
      `target=${PATH}\n`,
  );

  let version = await detailVersion();
  let held = probeBody.total;

  /** Create one proposal, chaining the version off the create's own response. */
  const createOne = async (n: number) => {
    const res = await request.post(`${base}/proposals`, {
      headers: { ...json, 'If-Match': `"${version}"` },
      data: {
        note_id: noteId,
        target_field_path: PATH,
        proposed_value: 'XAS',
        rule: `bench rule ${n}`,
        start_char: NOTE_TEXT.indexOf('XAS'),
        end_char: NOTE_TEXT.indexOf('XAS') + 3,
      },
    });
    expect(res.status(), `POST /proposals #${n} -> ${res.status()} ${await res.text()}`).toBe(200);
    const body = (await res.json()) as { deduplicated: boolean; experiment_version: string };
    expect(body.deduplicated, 'each create must MINT a proposal').toBe(false);
    version = body.experiment_version;
  };

  const rows: Row[] = [];

  for (const target of COUNTS) {
    const tTopUp = Date.now();
    while (held < target) {
      await createOne(held + 1);
      held += 1;
    }
    const topUpMs = Date.now() - tTopUp;

    // ---- the default window, which is what the panel asks for ------------
    const defSamples: number[] = [];
    let defBytes = 0;
    let defBody!: { total: number; returned: number; has_more: boolean; next_cursor: string | null; proposals: { proposal_id: string }[] };
    for (let i = 0; i < 3; i += 1) {
      const t0 = Date.now();
      const res = await request.get(`${base}/proposals`, { headers });
      const text = await res.text();
      defSamples.push(Date.now() - t0);
      expect(res.ok(), `GET /proposals -> ${res.status()}`).toBeTruthy();
      defBytes = bytes(text);
      defBody = JSON.parse(text);
    }

    // ---- the declared window maximum -------------------------------------
    const maxSamples: number[] = [];
    let maxBytes = 0;
    let maxReturned = 0;
    for (let i = 0; i < 3; i += 1) {
      const t0 = Date.now();
      const res = await request.get(`${base}/proposals?limit=200`, { headers });
      const text = await res.text();
      maxSamples.push(Date.now() - t0);
      maxBytes = bytes(text);
      maxReturned = (JSON.parse(text) as { returned: number }).returned;
    }

    // ---- limit=1: the fixed part of the body -----------------------------
    const oneRes = await request.get(`${base}/proposals?limit=1`, { headers });
    const oneBytes = bytes(await oneRes.text());

    // ---- walking the entire list at the declared maximum -----------------
    const tWalk = Date.now();
    let walkRequests = 0;
    let walkBytes = 0;
    let after: string | null = null;
    for (;;) {
      const url = `${base}/proposals?limit=200${after === null ? '' : `&after=${after}`}`;
      const res = await request.get(url, { headers });
      const text = await res.text();
      expect(res.ok(), `walk GET -> ${res.status()}`).toBeTruthy();
      walkRequests += 1;
      walkBytes += bytes(text);
      const body = JSON.parse(text) as { has_more: boolean; next_cursor: string | null };
      if (!body.has_more || body.next_cursor === null) break;
      after = body.next_cursor;
      expect(walkRequests, 'the walk must terminate well inside the declared bound').toBeLessThan(
        60,
      );
    }
    const walkMs = Date.now() - tWalk;

    // ---- detail, first and last in order ---------------------------------
    const allRes = await request.get(`${base}/proposals?limit=200`, { headers });
    const firstId = ((await allRes.json()) as { proposals: { proposal_id: string }[] })
      .proposals[0].proposal_id;
    // The LAST proposal in order needs the last window, which the walk just found.
    let lastId = firstId;
    {
      let cur: string | null = null;
      for (;;) {
        const res = await request.get(
          `${base}/proposals?limit=200${cur === null ? '' : `&after=${cur}`}`,
          { headers },
        );
        const b = (await res.json()) as {
          has_more: boolean;
          next_cursor: string | null;
          proposals: { proposal_id: string }[];
        };
        if (b.proposals.length > 0) lastId = b.proposals[b.proposals.length - 1].proposal_id;
        if (!b.has_more || b.next_cursor === null) break;
        cur = b.next_cursor;
      }
    }
    const timeDetail = async (id: string) => {
      const s: number[] = [];
      let n = 0;
      for (let i = 0; i < 3; i += 1) {
        const t0 = Date.now();
        const res = await request.get(`${base}/proposals/${id}`, { headers });
        const text = await res.text();
        s.push(Date.now() - t0);
        expect(res.ok(), `GET /proposals/{id} -> ${res.status()}`).toBeTruthy();
        n = bytes(text);
      }
      return { ms: median3(s), n };
    };
    const dFirst = await timeDetail(firstId);
    const dLast = await timeDetail(lastId);

    // ---- the change feed --------------------------------------------------
    const feedSamples: number[] = [];
    let feedBytes = 0;
    let feedBody!: {
      changes: { kind: string }[];
      returned: number;
      remaining: number;
      has_more: boolean;
      limit: number;
    };
    for (let i = 0; i < 3; i += 1) {
      const t0 = Date.now();
      const res = await request.get(`${base}/changes`, { headers });
      const text = await res.text();
      feedSamples.push(Date.now() - t0);
      expect(res.ok(), `GET /changes -> ${res.status()}`).toBeTruthy();
      feedBytes = bytes(text);
      feedBody = JSON.parse(text);
    }
    const oneProposalEntry = feedBody.changes.find((c) => c.kind === 'proposal');
    const feedProposalEntryBytes =
      oneProposalEntry === undefined ? 0 : bytes(JSON.stringify(oneProposalEntry));

    const feed200 = await request.get(`${base}/changes?limit=200`, { headers });
    const feed200Text = await feed200.text();
    const feed200Body = JSON.parse(feed200Text) as { returned: number };

    /*
     * THE BROWSER, AT THIS COUNT. Measured INSIDE the ladder rather than only at the
     * end, because "the DOM is bounded" is a claim about every count and
     * `docs/run-scale-measurements.md` records that exact conclusion expiring when it
     * was checked on one screen and generalised.
     *
     * The page is navigated AWAY afterwards, so the two pollers this screen mounts are
     * not running during the next top-up — otherwise every millisecond column below
     * would include a background poll this bench did not intend to measure.
     */
    const tOpenScale = Date.now();
    /* `?view=capture` — the record screen's four workspaces are lazily-mounted
       `?view=` destinations, and the proposals panel lives on Capture & Proposals.
       A bare `/record/<id>` opens Record Fields, where it is not in the DOM at all,
       so the wait below would hang for its full timeout rather than fail. */
    await page.goto(`/record/${TARGET}?view=capture`);
    await expect(page.getByRole('heading', { name: 'Ingestion Proposals' })).toBeVisible({
      timeout: 300_000,
    });
    await expect(page.locator('.proposals-count')).not.toBeEmpty({ timeout: 300_000 });
    const openMsScale = Date.now() - tOpenScale;
    const cardsAtScale = await page.locator('article.proposal-card').count();
    const domAtScale = await page.evaluate(() => document.getElementsByTagName('*').length);
    await page.goto('about:blank');

    rows.push({
      held: target,
      cards: cardsAtScale,
      domNodes: domAtScale,
      openMs: openMsScale,
      defMs: median3(defSamples),
      defBytes,
      defReturned: defBody.returned,
      defTotal: defBody.total,
      defHasMore: defBody.has_more,
      maxMs: median3(maxSamples),
      maxBytes,
      maxReturned,
      oneBytes,
      walkRequests,
      walkBytes,
      walkMs,
      detailFirstMs: dFirst.ms,
      detailLastMs: dLast.ms,
      detailBytes: dFirst.n,
      feedMs: median3(feedSamples),
      feedBytes,
      feedReturned: feedBody.returned,
      feedRemaining: feedBody.remaining,
      feedProposalEntries: feedBody.changes.filter((c) => c.kind === 'proposal').length,
      feedProposalEntryBytes,
      feed200Bytes: bytes(feed200Text),
      feed200Returned: feed200Body.returned,
    });

    log(
      `\n[proposal-scale] through ${target} held (top-up ${topUpMs} ms, ` +
        `total reported ${defBody.total})\n${table(rows)}\n`,
    );
  }

  log(`\n[proposal-scale] FINAL API TABLE\n${table(rows)}\n`);

  // =========================================================================
  // ARE THE DECLARED BOUNDS ACTUALLY ENFORCED? Probed, never read off source.
  // =========================================================================
  const enforcement: string[] = [];

  const overMax = await request.get(`${base}/proposals?limit=201`, { headers });
  enforcement.push(`limit=201 -> HTTP ${overMax.status()}`);
  const atMax = await request.get(`${base}/proposals?limit=200`, { headers });
  enforcement.push(
    `limit=200 -> HTTP ${atMax.status()}, returned ${((await atMax.json()) as { returned: number }).returned}`,
  );
  const zero = await request.get(`${base}/proposals?limit=0`, { headers });
  enforcement.push(`limit=0 -> HTTP ${zero.status()}`);
  const omitted = await request.get(`${base}/proposals`, { headers });
  const omittedBody = (await omitted.json()) as { returned: number; total: number };
  enforcement.push(
    `limit omitted at ${omittedBody.total} held -> returned ${omittedBody.returned}`,
  );
  const badCursor = await request.get(`${base}/proposals?after=NOTAPROPOSALID`, { headers });
  enforcement.push(`after=<unknown> -> HTTP ${badCursor.status()}`);

  const feedOverMax = await request.get(`${base}/changes?limit=1000`, { headers });
  const feedOverBody = (await feedOverMax.json()) as { limit: number; returned: number };
  enforcement.push(
    `changes limit=1000 -> HTTP ${feedOverMax.status()}, server limit ${feedOverBody.limit}, returned ${feedOverBody.returned}`,
  );

  log(`\n[proposal-scale] BOUND ENFORCEMENT (list + feed)\n  ${enforcement.join('\n  ')}\n`);

  // ---- the per-proposal byte ceiling, on a record with NO proposals -------
  // A separate record, so a 256 KiB value cannot consume the per-RECORD ceiling of
  // the one every table above was measured on.
  const alt = `${MUT_API_BASE}/experiments/${SEED.exportedAlt}`;
  const altVersion = async () => {
    const r = await request.get(alt, { headers });
    return ((await r.json()) as { version: string }).version;
  };
  const altNoteRes = await request.post(`${alt}/notes`, {
    headers: { ...json, 'If-Match': `"${await altVersion()}"` },
    data: { text: NOTE_TEXT, source: 'typed_note' },
  });
  expect(altNoteRes.status()).toBe(201);
  const altNoteId = ((await altNoteRes.json()) as { note: { id: string } }).note.id;

  /**
   * Probe the per-proposal ceiling and report THE SERVER'S OWN ARITHMETIC.
   *
   * The refusal names `max_bytes` and the `bytes` the rejected payload rendered to, so
   * the exact ceiling is derivable from ONE refusal rather than bisected — and the
   * bisection is the thing to avoid here, because every ACCEPTED probe permanently
   * consumes part of the record's `_MAX_PROPOSAL_STATE_BYTES`.
   */
  const byteProbe = async (valueLen: number) => {
    const res = await request.post(`${alt}/proposals`, {
      headers: { ...json, 'If-Match': `"${await altVersion()}"` },
      data: {
        note_id: altNoteId,
        target_field_path: PATH,
        proposed_value: 'X'.repeat(valueLen),
        rule: 'byte-ceiling probe',
      },
    });
    const text = await res.text();
    let parsed: Record<string, unknown> = {};
    try {
      const b = JSON.parse(text) as Record<string, unknown>;
      parsed = (b.detail as Record<string, unknown>) ?? b;
    } catch {
      /* leave empty; the raw prefix is printed instead */
    }
    return {
      line:
        `proposed_value of ${valueLen} B -> HTTP ${res.status()}` +
        (parsed.error === undefined
          ? ` ${text.slice(0, 120)}`
          : ` ${String(parsed.error)}` +
            (parsed.max_bytes === undefined
              ? ''
              : ` (server: bytes=${String(parsed.bytes)} max_bytes=${String(parsed.max_bytes)})`)),
      status: res.status(),
      bytes: typeof parsed.bytes === 'number' ? parsed.bytes : undefined,
      maxBytes: typeof parsed.max_bytes === 'number' ? parsed.max_bytes : undefined,
    };
  };

  const byteFindings: string[] = [];
  const small = await byteProbe(1024);
  byteFindings.push(small.line);
  const atDeclared = await byteProbe(256 * 1024);
  byteFindings.push(atDeclared.line);
  const overDeclared = await byteProbe(1024 * 1024);
  byteFindings.push(overDeclared.line);
  // The largest VALUE the route accepts, computed from the refusal's own numbers and
  // then CONFIRMED by an actual create — never reported from the arithmetic alone.
  if (atDeclared.bytes !== undefined && atDeclared.maxBytes !== undefined) {
    const overshoot = atDeclared.bytes - atDeclared.maxBytes;
    const predicted = 256 * 1024 - overshoot;
    const confirmAccept = await byteProbe(predicted);
    const confirmRefuse = await byteProbe(predicted + 1);
    byteFindings.push(
      `derived largest accepted value = ${predicted} B (declared ceiling ${atDeclared.maxBytes} B ` +
        `minus ${overshoot} B of envelope); confirmed: ${confirmAccept.line}; ${confirmRefuse.line}`,
    );
  }
  log(`\n[proposal-scale] PER-PROPOSAL BYTE CEILING\n  ${byteFindings.join('\n  ')}\n`);

  // ---- the per-record STATE-BYTE ceiling, on a third, untouched record ---
  //
  // A DIFFERENT BOUND FROM THE ROW COUNT, and `routes.py` says so: "whichever binds
  // first refuses". At 1,000 minimal proposals the ROW bound binds (probed below); this
  // probes the other side of the fork, by making each proposal as large as the
  // per-proposal ceiling allows and counting how many fit.
  const third = `${MUT_API_BASE}/experiments/${SEED.ready}`;
  const thirdVersion = async () =>
    ((await (await request.get(third, { headers })).json()) as { version: string }).version;
  const thirdNote = await request.post(`${third}/notes`, {
    headers: { ...json, 'If-Match': `"${await thirdVersion()}"` },
    data: { text: NOTE_TEXT, source: 'typed_note' },
  });
  expect(thirdNote.status()).toBe(201);
  const thirdNoteId = ((await thirdNote.json()) as { note: { id: string } }).note.id;
  /*
   * 2 KiB OF HEADROOM UNDER THE LARGEST ACCEPTED VALUE, AND THE HEADROOM IS THE
   * LESSON. The first version of this probe used the exact derived maximum (262,095 B)
   * with a rule string ONE BYTE LONGER than the one that maximum was derived with, so
   * every create was refused `value_too_large` and the probe reported "0 accepted" —
   * a plausible non-answer that looked like a finding about the per-RECORD ceiling
   * while actually being about the per-PROPOSAL one. It was caught only because the
   * refusal named the wrong error code. The headroom makes the probe insensitive to
   * the rule's length, and the assertion below makes a repeat impossible to publish.
   */
  const BIG = 262095 - 2048;
  let fitted = 0;
  let stateRefusal = '(never refused within the probe budget)';
  for (let i = 0; i < 30; i += 1) {
    const res = await request.post(`${third}/proposals`, {
      headers: { ...json, 'If-Match': `"${await thirdVersion()}"` },
      data: {
        note_id: thirdNoteId,
        target_field_path: PATH,
        proposed_value: 'Y'.repeat(BIG),
        rule: 'state-ceiling probe',
      },
    });
    if (res.status() === 200) {
      fitted += 1;
      continue;
    }
    const body = (await res.text()).slice(0, 300);
    stateRefusal = `HTTP ${res.status()} ${body}`;
    // THE PROBE MUST FAIL FOR THE REASON IT IS PROBING. A `value_too_large` here means
    // the per-PROPOSAL ceiling refused a single create and this probe measured nothing
    // about the per-RECORD one — exactly the wrong answer it returned the first time.
    expect(
      body,
      'the state-byte probe was refused by the per-PROPOSAL ceiling, so it measured ' +
        'nothing about the per-record one — shrink BIG and re-run',
    ).not.toContain('value_too_large');
    break;
  }
  log(
    `\n[proposal-scale] PER-RECORD STATE-BYTE CEILING (each proposal ${BIG} B)\n` +
      `  proposals accepted before refusal: ${fitted}\n` +
      `  refusal: ${stateRefusal}\n`,
  );

  // ---- the per-record row ceiling ---------------------------------------
  // Only meaningful if the ladder actually reached the declared maximum.
  if (held >= probeBody.max_per_record) {
    const overflow = await request.post(`${base}/proposals`, {
      headers: { ...json, 'If-Match': `"${version}"` },
      data: {
        note_id: noteId,
        target_field_path: PATH,
        proposed_value: 'XAS',
        rule: 'one past the declared ceiling',
      },
    });
    const text = await overflow.text();
    log(
      `\n[proposal-scale] PER-RECORD ROW CEILING\n` +
        `  create at ${held} held -> HTTP ${overflow.status()} ${text.slice(0, 400)}\n`,
    );
  } else {
    log(
      `\n[proposal-scale] PER-RECORD ROW CEILING: NOT PROBED — the ladder stopped at ` +
        `${held}, below the declared ${probeBody.max_per_record}.\n`,
    );
  }

  // =========================================================================
  // THE BROWSER, at the largest count reached.
  // =========================================================================
  const tally = new Map<string, number>();
  page.on('request', (r) => {
    const u = r.url();
    if (!u.includes('/api/')) return;
    const path = u.replace(/^.*\/api\//, '/').replace(/\?.*$/, '');
    const query = u.includes('?') ? u.replace(/^[^?]*\?/, '') : '';
    const bounded = /(^|&)limit=/.test(query);
    const key = (
      path + (path.endsWith('/proposals') ? (bounded ? '?limit=…' : ' [DEFAULT WINDOW]') : '')
    ).replace(/\/[0-9A-HJKMNP-TV-Z]{26}/gi, '/{id}');
    tally.set(key, (tally.get(key) ?? 0) + 1);
  });

  const tOpen = Date.now();
  /* `?view=capture` — the record screen's four workspaces are lazily-mounted
     `?view=` destinations, and the proposals panel lives on Capture & Proposals.
     A bare `/record/<id>` opens Record Fields, where it is not in the DOM at all,
     so the wait below would hang for its full timeout rather than fail. */
  await page.goto(`/record/${TARGET}?view=capture`);
  await expect(page.getByRole('heading', { name: 'Ingestion Proposals' })).toBeVisible({
    timeout: 300_000,
  });
  await expect(page.locator('.proposals-count')).not.toBeEmpty({ timeout: 300_000 });
  const openMs = Date.now() - tOpen;

  const cards = page.locator('article.proposal-card');
  const cardCount = await cards.count();
  const domNodes = await page.evaluate(() => document.getElementsByTagName('*').length);
  const proposalNodes = await page.evaluate(
    () => document.querySelectorAll('[class*="proposal"]').length,
  );
  const countLine = (await page.locator('.proposals-count').textContent()) ?? '';
  const openTally = [...tally.entries()].sort((a, b) => b[1] - a[1]);

  log(
    `\n[proposal-scale] BROWSER at ${held} held\n` +
      `  open-to-count-line: ${openMs} ms\n` +
      `  article.proposal-card: ${cardCount}\n` +
      `  DOM nodes (whole document): ${domNodes}\n` +
      `  nodes whose class mentions "proposal": ${proposalNodes}\n` +
      `  count line: ${JSON.stringify(countLine)}\n` +
      `  api requests: ${openTally.map(([k, n]) => `${k}x${n}`).join(', ')}\n`,
  );

  // =========================================================================
  // UNSAVED FORM STATE, under a real background refresh at this scale.
  //
  // THE OUT-OF-BAND ACT IS A WITHDRAW, NOT A CREATE, AND THE REASON IS A MEASUREMENT.
  // At `_MAX_PROPOSALS_PER_RECORD` a create is REFUSED (422 `too_many_proposals`,
  // probed above) — so a create-driven version of this check is unrunnable at exactly
  // the scale it most needs to run at. A withdraw is a state transition on a row that
  // already exists: it moves the record's rev, publishes a `proposal` feed entry, and
  // adds no row, so it works identically at 25 held and at the ceiling.
  // =========================================================================
  const TYPED = 'a half-written reason that must survive the background refresh';
  const firstCard = cards.first();
  await firstCard.getByRole('button', { name: 'Reject…', exact: true }).click();
  const form = firstCard.locator('.proposal-form');
  await expect(form).toBeVisible({ timeout: 60_000 });
  await form.getByLabel('Reason (optional)').fill(TYPED);

  // The SECOND card's proposal, withdrawn by a second client. It is in the first
  // window, so its state change is observable on screen.
  const secondCard = cards.nth(1);
  const secondLabel = (await secondCard.getAttribute('aria-label')) ?? '';
  const windowNow = (await (
    await request.get(`${base}/proposals?limit=2`, { headers })
  ).json()) as { proposals: { proposal_id: string; state: string }[] };
  const victimId = windowNow.proposals[1].proposal_id;

  // Snapshot the tally so the event window is a DIFFERENCE, not a running total that
  // still carries the page load's own requests.
  const tallyAtEvent = new Map(tally);
  const tEvent = Date.now();
  const withdrawn = await request.post(`${base}/proposals/${victimId}/review`, {
    headers: { ...json, 'If-Match': `"${await detailVersion()}"` },
    data: { confirmed_by_user: true, action: 'withdraw', reason: 'bench: background act' },
  });
  expect(
    withdrawn.ok(),
    `out-of-band withdraw -> ${withdrawn.status()} ${await withdrawn.text()}`,
  ).toBeTruthy();
  await expect(cards.nth(1)).toHaveAttribute('data-state', 'withdrawn', { timeout: 180_000 });
  const eventToScreenMs = Date.now() - tEvent;
  const survived = await form.getByLabel('Reason (optional)').inputValue();

  log(
    `\n[proposal-scale] BACKGROUND REFRESH UNDER LOAD (${held} held)\n` +
      `  second card before: ${JSON.stringify(secondLabel)}\n` +
      `  withdraw -> card state on screen: ${eventToScreenMs} ms (feed cadence 8 s + jitter)\n` +
      `  typed value in card 1 survived: ${survived === TYPED}\n` +
      `  cards still rendered: ${await cards.count()}\n` +
      `  requests during the event window: ${[...tally.entries()]
        .map(([k, n]) => [k, n - (tallyAtEvent.get(k) ?? 0)] as const)
        .filter(([, n]) => n > 0)
        .sort((a, b) => b[1] - a[1])
        .map(([k, n]) => `${k}x${n}`)
        .join(', ')}\n`,
  );
  expect(survived, 'the silent refresh must not destroy unsaved input').toBe(TYPED);
});
