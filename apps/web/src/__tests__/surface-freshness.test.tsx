/*
 * FRESHNESS AUDIT — the Evidence Graph and Compare Runs.
 *
 * These two surfaces had already been through the honesty sweeps: the
 * official-schema mislabelling, the `unavailable` no-verdict attribution, the
 * `producer` line, the `.sr-only` page overflow and the graph mode on resize are
 * all fixed and pinned elsewhere. What had never been checked is whether either
 * surface still describes the record AFTER something changes it.
 *
 * Three defects were found by measurement and are pinned here. Every one of them
 * is a surface making a statement that was true when it was rendered and false
 * when it was read, which is the class this programme keeps finding.
 *
 * ── 1 · THE GRAPH PRINTED A FRESH VERSION OVER STALE RUNS ───────────────────
 *
 * `EvidenceGraphPanel` renders, verbatim:
 *
 *     Built from this record at version <token>.
 *     Nothing here is cached across a version change.
 *
 * The token is `detail.version`, which the ≤8s poller DOES refresh —
 * `EvidenceExplorer` passes `onChange: () => bundle.reloadSilent()`. The RUNS the
 * graph draws came from a separate `useFetch(… api.listRuns …, [id])` whose deps
 * are the record id alone, so they refreshed never. The two halves of one
 * sentence were therefore fed by two reads with different ages, and the older one
 * was the one being described.
 *
 * The consequence is specific rather than general. A run removed from another
 * surface stayed drawn — its node, its whole subtree and its `has_run` edge —
 * under a version number that had already moved past its deletion. The second
 * sentence stayed true the whole time: the CACHE really is evicted on a version
 * change (`rekeyRunCheckStore`), and `key={freshnessKey}` really does remount.
 * That is what made it hard to see. The cache was honest; the props were not.
 *
 * ── 2 · …AND THE GRAPH WAS THE ONE SURFACE WITH NO WAY TO SAY OTHERWISE ─────
 *
 * `LiveSyncNote` — "Live updates paused / that refresh did not reach the ISAAC
 * API — this is the last loaded state" plus a Refresh — was rendered on the
 * evidence LIST branch only. On the graph branch a degraded poller (three
 * consecutive failures) and a failed silent refetch were both silent, on the one
 * surface in the app that asserts the version it was built from, and with no
 * manual recourse anywhere on screen.
 *
 * ── 3 · COMPARE RUNS RE-LABELLED ONE PAIR'S VERDICTS AS ANOTHER'S ───────────
 *
 * `CompareFindings` holds both check responses in local state with no eviction,
 * and the element carried no `key`, so React preserved that state across every
 * prop change. Change one of the two compared runs and `FindingsResult` re-renders
 * the OLD pair's responses under the NEW pair's labels: "Reported for Run 3 only"
 * listing findings that were read from Run 2, beside "Read-only check of run
 * version r2.0" — Run 2's version, on a panel headed by Run 3. Save a run and the
 * same state survives a version bump.
 *
 * The Evidence Graph had already solved exactly this: `readRunCheck` refuses a
 * cached verdict whose run version has moved. Two surfaces in one product
 * disagreed about whether a stale verdict may be shown, and this file pins them
 * to the same answer.
 *
 * ── The change SIGNAL, per mutation — and it is NOT eight out of eight ──────
 *
 * ~~"every one of the eight mutations moves `detail.version`, because the
 * backend's authoritative signature hashes `runs` and `notes` along with the
 * draft — so the change SIGNAL was never the missing piece"~~ — WRITTEN HERE
 * FIRST AND THEN MEASURED FALSE, and struck rather than deleted because the
 * exception is the one a reader is most likely to assume away.
 *
 * `workspace._authoritative_signature` hashes exactly
 * `{title, source, draft, record_id, runs, notes}` (`workspace.py:1499-1529`),
 * and every mutating handler in `routes.py` writes through `_save_versioned`.
 * So the rule is mechanical: a handler that writes into one of those six moves
 * `rev`, and a handler that does not, cannot. Measured, handler by handler:
 *
 *   answer a question          `exp.draft` / `run.draft`            MOVES
 *   correct a value            `apply_corrections` -> `exp.draft`   MOVES
 *   asset add/edit/remove      `exp.draft["assets"]` + run copies   MOVES
 *   conflict resolution        top-level `draft["conflict_…"]`      MOVES
 *   transcript capture         `exp.notes`                          MOVES
 *   accept a candidate         `PATCH /runs/{id}` -> `run.draft`    MOVES
 *   remove a run               `exp.remove_run`                     MOVES
 *   FIRST submit, unexported   materialisation sets `record_id`     MOVES
 *   submit / RESUBMIT, already
 *     fully materialised       five INSERTs, submission tables ONLY  DOES NOT
 *
 * The last row is the correction. `POST /submit` only touches the experiment
 * document through `_materialise_pending_units`, and it skips units that are
 * already materialised (`routes.py:10934`); `submission_store.record_submission`
 * writes five rows and reads `exp.to_state()` as an immutable snapshot. Since
 * exported records are immutable and nothing republishes them, the ORDINARY
 * resubmission — submit, edit, submit again — moves `rev` on the edit and not on
 * either submit. A submission is therefore invisible to the ETag poller, which
 * answers 304 forever.
 *
 * THAT IS NOT A DEFECT ON EITHER OF THESE TWO SURFACES, and the reason is worth
 * stating rather than assuming: neither draws anything sourced from a submission.
 * `EVIDENCE_NODE_KINDS` is a closed list of ten and holds no submission kind, and
 * `RunCompare` renders run documents and run checks. A signal nothing consumes is
 * not a missed refresh. It is recorded here so that the first surface which DOES
 * show revision or submission state knows, before it is built, that the record
 * poller will not tell it anything.
 *
 * ── What else was audited and found CORRECT, so nobody re-derives it ────────
 *
 *   · no staged assistant proposal, unaccepted transcript candidate or CSV
 *     preview reaches either surface. `EvidenceGraphInput` carries only
 *     server-read values, and `RunCompare` is entirely props plus one
 *     `api.getRun`. A suggestion becomes visible only by becoming stored state;
 *   · `EVIDENCE_GRAPH_DISCLOSURE` is still rendered from the exported constant,
 *     so a paraphrase cannot satisfy the test that asserts it, and all ten
 *     `EDGE_PRODUCERS` entries name a stored schema, evidence, provenance or
 *     validation source — the disclosure is true of every edge kind that can be
 *     constructed, because `Builder.addEdge` refuses any other producer;
 *   · COMPARE RUNS IS NOT IN THE POLLER'S REFRESH PATH AT ALL, and that is
 *     `RunsSection`'s own documented design, not an oversight found here: the
 *     section owns its fetch and offers `Reload This Section`. So a mutation made
 *     ELSEWHERE does not reach it, and this file deliberately does not change
 *     that — what it fixes is the narrower thing that was false, which is a
 *     verdict presented under the wrong run's name.
 *
 * ── Honest scope ────────────────────────────────────────────────────────────
 *
 * jsdom lays nothing out. Every assertion below is a DOM or request-log
 * assertion, driven through the real screens with `fetch` stubbed and the poll
 * clock advanced by hand — not a CSS or geometry claim.
 */

import { describe, it, expect, afterEach, beforeEach, vi, type Mock } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { AppRoutes } from '../App';
import { RunCompare } from '../components/RunCompare';
import { api, ApiError } from '../lib/api';
import { POLL_INTERVAL_MS } from '../lib/useRecordSync';
import {
  evidenceBundleRoutes,
  experimentDetail,
  experimentDetailChanged,
  liveDetailRoute,
  runFixture,
  runsPage,
  stubFetchRoutes,
  type RouteEntry,
} from '../test/apiFixtures';
import type { ApiRunView } from '../lib/types';

const ID = 'demo';
const BASE = `/api/experiments/${ID}`;

/** Advance fake timers (default 0 → flush pending microtasks only). */
async function settle(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

function renderAt(path: string) {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AppRoutes />
    </MemoryRouter>,
  );
}

const runOne = () => runFixture({ id: 'RUN001', label: 'Run 1', ordinal: 1, version: 'r1.0' });
const runTwo = () => runFixture({ id: 'RUN002', label: 'Run 2', ordinal: 2, version: 'r2.0' });
const runThree = () => runFixture({ id: 'RUN003', label: 'Run 3', ordinal: 3, version: 'r3.0' });

/** Which run nodes the graph actually drew, by run id. */
const drawnRunIds = (root: ParentNode): string[] =>
  [...root.querySelectorAll('g[data-node-id^="run:"]')].map(
    (g) => (g.getAttribute('data-node-id') ?? '').slice('run:'.length),
  );

/**
 * The version token the panel claims the graph was built from.
 *
 * Read out of the `<code>` element rather than by parsing the sentence: the
 * token itself contains a `.` (`"<generation>.<rev>"`), so a regex ending at the
 * sentence's full stop silently truncates `1.0` to `1`.
 */
const claimedVersion = (): string =>
  screen.getByTestId('evgraph-freshness').querySelector('code')?.textContent ?? '';

/** How many times the runs listing was requested. */
const runsReads = (): number =>
  ((globalThis.fetch as Mock).mock.calls as [string, RequestInit?][]).filter(([url]) =>
    /\/experiments\/demo\/runs(\?|$)/.test(String(url)),
  ).length;

/*
 * TEARDOWN, AND WHY IT UNMOUNTS FIRST.
 *
 * Vitest's default hook order is `stack`, so a file-level `afterEach` runs
 * BEFORE the one `src/test/setup.ts` registers — the one that calls RTL's
 * `cleanup()`. Restoring real timers, real `Math.random` and the real global
 * `fetch` therefore happens while these screens are still MOUNTED and still
 * hold a live `useRecordSync` poller. Unmounting first closes that window: the
 * tree is torn down while its own stubs are still installed, and only then is
 * anything global put back.
 *
 * `document.hidden` is restored too. `Object.defineProperty` is not a mock, so
 * neither `restoreAllMocks` nor `unstubAllGlobals` undoes it, and leaving an own
 * accessor on `document` outlives every test in this file.
 */
function restoreEnvironment() {
  cleanup();
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  delete (document as unknown as Record<string, unknown>).hidden;
}

describe('the Evidence Graph describes the version it says it was built from', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // Pin `useRecordSync`'s ±20% jitter so the poll lands on the exact interval.
    vi.spyOn(Math, 'random').mockReturnValue(0.5);
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => false });
  });
  afterEach(restoreEnvironment);

  it('a run removed elsewhere stops being drawn on the poll that moves the version', async () => {
    const live = liveDetailRoute(ID);
    // The runs listing answers TWO runs, and then — after the record has moved —
    // one. This is a run removed from another surface, which is the mutation the
    // graph kept drawing.
    let removed = false;
    const runsRoute: RouteEntry = () => ({
      body: runsPage(removed ? [runOne()] : [runOne(), runTwo()]),
    });

    stubFetchRoutes({
      ...evidenceBundleRoutes(ID),
      [`GET ${BASE}`]: live.route,
      [`GET ${BASE}/runs`]: runsRoute,
    });

    const { container } = renderAt(`/record/${ID}/evidence?view=graph`);
    await settle();

    expect(drawnRunIds(container).sort()).toEqual(['RUN001', 'RUN002']);
    expect(claimedVersion()).toBe(experimentDetail.version);
    const readsAtStart = runsReads();

    // An unchanged tick must cost nothing: a 304 is not a reason to re-read runs.
    await settle(POLL_INTERVAL_MS);
    expect(runsReads()).toBe(readsAtStart);
    expect(drawnRunIds(container).sort()).toEqual(['RUN001', 'RUN002']);

    // The run is removed elsewhere and the record moves.
    removed = true;
    live.bump();
    await settle(POLL_INTERVAL_MS);

    // THE DEFECT: before this slice the version below advanced while the run
    // above stayed drawn, so the panel asserted a version at which that run did
    // not exist.
    expect(claimedVersion()).toBe(experimentDetailChanged.version);
    expect(drawnRunIds(container)).toEqual(['RUN001']);
    expect(runsReads()).toBe(readsAtStart + 1);
  });

  it('a FAILED re-read no longer lets the panel assert the new version over the old rows', async () => {
    /*
     * THE HALF THE RE-READ FIX LEFT OPEN, and it is the same false statement on
     * the other branch.
     *
     * The runs are a SEPARATE fetch from the bundle the version comes from, so
     * `/runs` can fail while the version poll succeeds. `reloadSilent` is built
     * to keep the old data and raise `refreshFailed` — correct, and deliberate.
     * But the version ref advanced BEFORE the await, and `EvidenceGraphPanel`
     * printed `detail.version` unconditionally, so the screen showed:
     *
     *     claimedVersion            = 2.0
     *     drawn run rows            = [RUN001, RUN002]   (read at 1.0)
     *     refresh-failed note       = on screen
     *     "Built from this record at version 2.0."
     *
     * The `LiveSyncNote` is a real mitigation and it is not a correction: it
     * sits BESIDE a sentence that still asserts the new version over the old
     * rows. So the sentence itself now names both versions.
     */
    const live = liveDetailRoute(ID);
    let failRuns = false;
    const runsRoute: RouteEntry = () =>
      failRuns
        ? { status: 503, body: { detail: 'runs listing is down' } }
        : { body: runsPage([runOne(), runTwo()]) };

    stubFetchRoutes({
      ...evidenceBundleRoutes(ID),
      [`GET ${BASE}`]: live.route,
      [`GET ${BASE}/runs`]: runsRoute,
    });

    const { container } = renderAt(`/record/${ID}/evidence?view=graph`);
    await settle();

    expect(drawnRunIds(container).sort()).toEqual(['RUN001', 'RUN002']);
    expect(claimedVersion()).toBe(experimentDetail.version);
    // One read, one version: the sentence is the unqualified one, everywhere.
    expect(screen.queryByTestId('evgraph-freshness-runs')).toBeNull();
    expect(screen.getByTestId('evgraph-freshness').textContent).toContain(
      'Nothing here is cached across a version change.',
    );

    // The record moves and the runs re-read FAILS.
    failRuns = true;
    live.bump();
    await settle(POLL_INTERVAL_MS);

    // `reloadSilent` did its job: the rows are kept and the screen never blanked.
    expect(drawnRunIds(container).sort()).toEqual(['RUN001', 'RUN002']);
    expect(screen.queryByText(/Loading this experiment's runs/)).toBeNull();
    // The note is on screen — necessary, and on its own not sufficient.
    expect(
      screen.getByText(/this is the last loaded state, not a newly checked one/i),
    ).toBeInTheDocument();

    // THE ASSERTION THAT WAS RED. The headline still names the record's version,
    // because the evidence, classification and findings here really are at it —
    // printing the runs' older token alone would trade one false claim for
    // another — and it now names the run rows' OWN, older version beside it.
    expect(claimedVersion()).toBe(experimentDetailChanged.version);
    expect(screen.getByTestId('evgraph-freshness-runs').textContent).toBe(
      experimentDetail.version,
    );
    expect(screen.getByTestId('evgraph-freshness').textContent).toContain(
      'The run rows are OLDER',
    );
  });

  it('a re-read that LANDS clears the qualification and restores the plain sentence', async () => {
    // The other direction, because a qualification that never goes away is just
    // a permanent hedge — and a hedge is its own kind of false statement.
    const live = liveDetailRoute(ID);
    let failRuns = false;
    const runsRoute: RouteEntry = () =>
      failRuns
        ? { status: 503, body: { detail: 'runs listing is down' } }
        : { body: runsPage([runOne(), runTwo()]) };

    stubFetchRoutes({
      ...evidenceBundleRoutes(ID),
      [`GET ${BASE}`]: live.route,
      [`GET ${BASE}/runs`]: runsRoute,
    });

    renderAt(`/record/${ID}/evidence?view=graph`);
    await settle();

    failRuns = true;
    live.bump();
    await settle(POLL_INTERVAL_MS);
    expect(screen.getByTestId('evgraph-freshness-runs')).toBeInTheDocument();

    // The reader presses Refresh on the note; the runs listing is back.
    failRuns = false;
    fireEvent.click(screen.getByRole('button', { name: /refresh/i }));
    await settle();

    expect(claimedVersion()).toBe(experimentDetailChanged.version);
    expect(screen.queryByTestId('evgraph-freshness-runs')).toBeNull();
    expect(screen.getByTestId('evgraph-freshness').textContent).toContain(
      'Nothing here is cached across a version change.',
    );
  });

  it('the refetch is SILENT — the graph keeps its rows WHILE the re-read is in flight', async () => {
    /*
     * WHY THIS TEST HOLDS THE RESPONSE OPEN, stated because the obvious version
     * of it measures nothing.
     *
     * The claim being defended is that the fix compares `detail.version` in an
     * effect instead of putting it in the `useFetch` deps array, because a deps
     * change flips `useFetch` back to `status: 'loading'` and this branch renders
     * a LoadingPanel for that state — blanking a read-only screen on every
     * detected change, which is exactly what `reloadSilent` exists to prevent.
     *
     * An earlier revision of this test asserted that after `settle()` no loading
     * panel was on screen. MEASURED, that assertion passes with the deps-array
     * version too: the stub resolves in the same flush, so the loading state
     * exists for zero observable moments and the test was green against the
     * defect it named. The claim in the comment was true; the test under it was
     * not testing it.
     *
     * So the runs response is HELD OPEN across the poll. Now the two designs
     * differ where a reader would see the difference: `reloadSilent` keeps the
     * previous rows on screen for the whole in-flight window, and the deps-array
     * version renders `Loading this experiment's runs…` for it.
     */
    const live = liveDetailRoute(ID);
    let hold = false;
    let release: () => void = () => undefined;
    const runsRoute: RouteEntry = async () => {
      if (hold) await new Promise<void>((resolve) => (release = resolve));
      return { body: runsPage([runOne(), runTwo()]) };
    };
    stubFetchRoutes({
      ...evidenceBundleRoutes(ID),
      [`GET ${BASE}`]: live.route,
      [`GET ${BASE}/runs`]: runsRoute,
    });

    const { container } = renderAt(`/record/${ID}/evidence?view=graph`);
    await settle();
    expect(drawnRunIds(container).length).toBe(2);
    const readsAtStart = runsReads();

    hold = true;
    live.bump();
    await settle(POLL_INTERVAL_MS);

    // IN FLIGHT: the re-read has been issued and has not answered.
    expect(runsReads()).toBe(readsAtStart + 1);
    expect(screen.queryByText(/Loading this experiment's runs/)).toBeNull();
    expect(drawnRunIds(container).length).toBe(2);
    expect(screen.getByTestId('evgraph-freshness')).toBeInTheDocument();

    // …and it still lands.
    release();
    await settle();
    expect(drawnRunIds(container).length).toBe(2);
    expect(screen.queryByText(/Loading this experiment's runs/)).toBeNull();
  });

  it('a degraded poller is stated ON THE GRAPH, with a Refresh that re-reads both fetches', async () => {
    stubFetchRoutes({
      ...evidenceBundleRoutes(ID),
      [`GET ${BASE}/runs`]: { body: runsPage([runOne()]) },
    });
    const poll = vi
      .spyOn(api, 'checkRecordVersion')
      .mockRejectedValue(new ApiError('down', { unreachable: true }));

    renderAt(`/record/${ID}/evidence?view=graph`);
    await settle();
    expect(screen.getByTestId('evgraph-freshness')).toBeInTheDocument();
    expect(screen.queryByText(/Live updates paused/)).toBeNull();

    // Three consecutive failures at 8s, +16s, +32s → degraded.
    await settle(POLL_INTERVAL_MS);
    await settle(POLL_INTERVAL_MS * 2);
    await settle(POLL_INTERVAL_MS * 4);
    expect(poll).toHaveBeenCalledTimes(3);

    // BEFORE THIS SLICE the graph branch rendered no note at all.
    expect(screen.getByText(/Live updates paused/)).toBeInTheDocument();
    expect(screen.getByText(/last loaded state/)).toBeInTheDocument();

    // …and its Refresh reloads the runs as well as the bundle, because the
    // version claim is only as fresh as the older of the two.
    const before = runsReads();
    fireEvent.click(screen.getByText('Refresh'));
    await settle();
    expect(runsReads()).toBeGreaterThan(before);
  });
});

describe("Compare Runs never shows one pair's verdicts as another's", () => {
  afterEach(restoreEnvironment);

  const verdict = (errors: string[], version: string) => ({
    ok: false,
    draft: { ok: false, errors },
    official: { ok: false, errors: [], dry_run: true },
    blockers: [],
    checked_run_version: version,
  });

  /** Mount `RunCompare` alone, with the selection and the loaded page as props. */
  function mountCompare(compareIds: string[], loadedRuns: ApiRunView[]) {
    const view = render(
      <MemoryRouter
        initialEntries={[`/record/${ID}`]}
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
      >
        <RunCompare
          experimentId={ID}
          compareIds={compareIds}
          loadedRuns={loadedRuns}
          listReady
          hidden={false}
          onSetCompareIds={() => undefined}
        />
      </MemoryRouter>,
    );
    const rerenderWith = (ids: string[], runs: ApiRunView[]) =>
      view.rerender(
        <MemoryRouter
          initialEntries={[`/record/${ID}`]}
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <RunCompare
            experimentId={ID}
            compareIds={ids}
            loadedRuns={runs}
            listReady
            hidden={false}
            onSetCompareIds={() => undefined}
          />
        </MemoryRouter>,
      );
    return { view, rerenderWith };
  }

  it('changing one of the compared runs discards the previous pair’s verdicts', async () => {
    stubFetchRoutes({
      [`POST ${BASE}/runs/RUN001/check`]: { body: verdict(['run one finding'], 'r1.0') },
      [`POST ${BASE}/runs/RUN002/check`]: { body: verdict(['run two finding'], 'r2.0') },
      [`POST ${BASE}/runs/RUN003/check`]: { body: verdict(['run three finding'], 'r3.0') },
    });

    const runs = [runOne(), runTwo(), runThree()] as unknown as ApiRunView[];
    const { view, rerenderWith } = mountCompare(['RUN001', 'RUN002'], runs);

    fireEvent.click(screen.getByRole('button', { name: 'Check both runs' }));
    expect(await screen.findByText(/Reported for both runs|Reported for Run 2 only/)).toBeInTheDocument();
    expect(view.container.textContent).toContain('run two finding');
    expect(view.container.textContent).toContain('Read-only check of run version r2.0');

    // Swap Run 2 out for Run 3. Nothing has been checked for Run 3.
    rerenderWith(['RUN001', 'RUN003'], runs);

    /*
     * THE DEFECT. Without a key, `check` survived — so Run 2's findings were
     * re-rendered under the heading "Reported for Run 3 only", and Run 2's
     * version was printed beside Run 3's label. Both of those are false
     * statements about a run the reader is looking at.
     */
    expect(view.container.textContent).not.toContain('run two finding');
    expect(view.container.textContent).not.toContain('Read-only check of run version r2.0');
    expect(screen.getByRole('button', { name: 'Check both runs' })).toBeInTheDocument();
  });

  it('a run whose version has moved discards its verdict rather than displaying it', async () => {
    stubFetchRoutes({
      [`POST ${BASE}/runs/RUN001/check`]: { body: verdict(['run one finding'], 'r1.0') },
      [`POST ${BASE}/runs/RUN002/check`]: { body: verdict(['run two finding'], 'r2.0') },
    });

    const before = [runOne(), runTwo()] as unknown as ApiRunView[];
    const { view, rerenderWith } = mountCompare(['RUN001', 'RUN002'], before);

    fireEvent.click(screen.getByRole('button', { name: 'Check both runs' }));
    expect(await screen.findByText(/Read-only check of run version r1\.0/)).toBeInTheDocument();

    /*
     * A card save: `RunsSection.replaceRun` substitutes a NEW run object with a
     * NEW version, which is why the table above recomputes. The verdicts below
     * it used to survive that — a check of `r1.0` presented beside a run that is
     * now `r1.1`, which is the same thing the Evidence Graph's `readRunCheck`
     * refuses to serve.
     */
    const saved = [{ ...runOne(), version: 'r1.1', rev: 1 }, runTwo()] as unknown as ApiRunView[];
    rerenderWith(['RUN001', 'RUN002'], saved);

    expect(view.container.textContent).not.toContain('Read-only check of run version r1.0');
    expect(view.container.textContent).not.toContain('run one finding');
    expect(screen.getByRole('button', { name: 'Check both runs' })).toBeInTheDocument();
  });
});
