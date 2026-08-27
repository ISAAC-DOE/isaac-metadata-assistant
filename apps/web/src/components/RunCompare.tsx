/*
 * COMPARE TWO RUNS — the surface, and the four things it must never become.
 *
 * 1. IT NEVER SAYS WHY. Every sentence this component can render is a statement
 *    about what two documents contain at one address. There is no "because", no
 *    "due to", no "explains", no "better", no "worse", no "improved" and no
 *    ranking of one run over the other — not in a summary, not in a row, not in
 *    the findings section. A scientist reading a difference here is being handed
 *    an observation to check, not a conclusion to accept, and this is the single
 *    easiest place in the product to accidentally do science on their behalf.
 *    `run-compare.test.tsx` renders every state this file can produce and scans
 *    the rendered text against a causal/evaluative vocabulary; that test is a
 *    guard on this paragraph, not on a wording preference.
 *
 * 2. IT NEVER FLATTENS INHERITED AND OVERRIDDEN INTO "THESE DIFFER". Two runs can
 *    disagree at an address because one holds its own value where the other reads
 *    the record's — which is a different fact from two runs holding different own
 *    values, and a different fact again from two runs holding the SAME value from
 *    different sources. `lib/runCompare.ts` keeps value, provenance and evidence
 *    as three independent axes for exactly this reason, and every row states each
 *    axis that has something to say. The words are `RunInheritedPanel`'s own
 *    ("Inherited from record", "Overridden on this run"), reused rather than
 *    reinvented: a second vocabulary for one distinction is a second thing to
 *    learn and a second thing to get wrong.
 *
 * 3. IT NEVER RENDERS ABSENCE AS A VALUE. "This run records nothing here" is its
 *    own category with its own glyph, its own word and its own sentence, and it is
 *    never counted among the value differences. A blank cell beside a filled one,
 *    labelled "differs", is the defect this rule exists to prevent.
 *
 * 4. IT NEVER SHOWS ONLY DIFFERENCES. The summary always states how many addresses
 *    were compared and how many are the same on both runs, and the same-on-both
 *    rows are one control away — a comparison that can only enumerate differences
 *    cannot answer "are these two runs the same apart from temperature?", which is
 *    the question most readers actually arrive with.
 *
 * WHERE THE SELECTION LIVES, AND WHY IT IS NOT A PICKER. The run list is BOUNDED
 * and paged for measured reasons (`docs/run-scale-measurements.md`: 7.47 MiB at
 * 1000 runs), so a dropdown listing every run would reintroduce the exact download
 * that slice removed — and would do it in a control that is invisible until it is
 * opened. The picker is therefore the run list itself: each card carries a Compare
 * toggle, and the reader reaches the second run with the same search, filters and
 * paging they already use. Nothing here ever calls `listRuns` at all.
 *
 * THE TWO RUNS ARE READ FROM THE PAGE WHEN THEY ARE ON IT. A comparison assembled
 * from cards the reader just clicked costs ZERO requests FOR THE TWO RUNS. Only a
 * deep link — where the ids arrive before any run does — costs anything there, and
 * it costs exactly one `getRun` per run that is not on the loaded page, never a
 * list read. The resolution deliberately WAITS for the first page rather than
 * racing it: firing two reads for runs that are already in flight is two requests
 * to learn what was about to arrive, and the page read is already on its way.
 *
 * "ZERO REQUESTS" IS NARROWED RATHER THAN LEFT STANDING, because it stopped being
 * the whole truth the moment the record-context band arrived. A comparison of two
 * on-page runs now costs FOUR bounded reads — `listConflicts` and `getPendingPage`
 * per run — issued once per compared pair, only while the panel is on screen, and
 * never repeated on a Focus Run round trip. Still no `listRuns`, ever.
 *
 * IT IS READ-ONLY, AND IT SAYS SO ON SCREEN. Nothing here writes, overrides,
 * reverts, exports or submits. `Check both runs` is the one control that reaches
 * the server for anything beyond reading the two runs, and the check route itself
 * writes nothing — the panel repeats the run card's own scope sentence rather than
 * inventing a softer one.
 */

import './run-compare.css';
import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, ApiError } from '../lib/api';
import { RECORD_ADDRESS_PARAM, RECORD_RUN_PARAM, RUN_COMPARE_MAX } from '../lib/routes';
import {
  buildRunComparison,
  categoryWord,
  conflictWord,
  evidenceWord,
  originWord,
  originsWord,
  reviewWord,
  supportWord,
  type CompareBlock,
  type CompareCategory,
  type CompareConflict,
  type CompareRow,
  type CompareSide,
  type RunComparison,
} from '../lib/runCompare';
import { formatCreatedDate } from '../lib/labels';
import { runFindingText } from '../lib/runFields';
import {
  ArrowLeftRight,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  CircleDashed,
  CircleHelp,
  CornerDownRight,
  Columns2,
  Equal,
  Pencil,
  Shield,
  type LucideIcon,
} from './icons';
import { LoadingPanel } from './FetchStates';
import { StatusChip } from './StatusChip';
import type {
  ApiConflictsResponse,
  ApiPendingItem,
  ApiPendingPage,
  ApiRunCheckFinding,
  ApiRunCheckResponse,
  ApiRunView,
} from '../lib/types';

/**
 * The glyph for each comparison category. ALWAYS paired with the word and with a
 * surface treatment (`run-compare.css`), never used alone and never the only
 * carrier of the distinction — the repo's system-wide rule, restated here because
 * a table is where a designer is most tempted to tint a row and stop.
 */
const CATEGORY_ICON: Record<CompareCategory, LucideIcon> = {
  same: Equal,
  value: ArrowLeftRight,
  'absent-on-one': CircleDashed,
  review: Shield,
  provenance: CornerDownRight,
  evidence: Pencil,
  incomparable: CircleHelp,
};

/**
 * HOW MANY OPEN QUESTIONS THIS PANEL LISTS PER RUN, and the count is not the bound
 * that matters. `GET /pending` grew a page block precisely because a record's
 * questions grow with its runs (measured: 3,000 entries / 1.77 MB at 1,000 runs),
 * so this asks for a WINDOW and reads `pending_page.total` for the real number.
 * The window is small on purpose: this is a comparison, not the completion screen,
 * and five is enough to recognise what is outstanding before going there.
 */
const CONTEXT_PENDING_PREVIEW = 5;

/**
 * THE RECORD CONTEXT FOR ONE RUN. Every field is separately fallible and every
 * failure is carried rather than swallowed — a panel that renders nothing where a
 * read failed is a panel asserting there was nothing to show.
 */
interface SideContext {
  conflicts: ApiConflictsResponse | null;
  conflictsMessage: string | null;
  pending: ApiPendingItem[];
  pendingPage: ApiPendingPage | null;
  pendingMessage: string | null;
}

type ContextState =
  | { status: 'loading' }
  | { status: 'ready'; a: SideContext; b: SideContext };

function readMessage(err: unknown): string {
  const text = err instanceof Error ? err.message.trim() : '';
  return text === '' ? 'The read did not complete.' : text;
}

/**
 * TWO BOUNDED READS FOR ONE RUN, AND NEITHER CAN REJECT.
 *
 * `Promise.all` over two `.catch`-terminated chains rather than `allSettled`,
 * because each read has its own place to put its own failure and neither may take
 * the other down: a conflicts read that 500s must not remove the open-question
 * count from the screen, and the reverse.
 *
 * NOTHING HERE LISTS RUNS. The comparison's read discipline (see the file header)
 * is unchanged: a run already on the page costs nothing, a deep-linked run costs
 * one `getRun`, and this adds exactly two per run, once per compared pair.
 */
async function readSideContext(experimentId: string, runId: string): Promise<SideContext> {
  const side: SideContext = {
    conflicts: null,
    conflictsMessage: null,
    pending: [],
    pendingPage: null,
    pendingMessage: null,
  };
  await Promise.all([
    api
      .listConflicts(experimentId, { runId })
      .then((res) => {
        side.conflicts = res;
      })
      .catch((err: unknown) => {
        side.conflictsMessage = readMessage(err);
      }),
    api
      .getPendingPage(experimentId, { runId, limit: CONTEXT_PENDING_PREVIEW })
      .then((res) => {
        side.pending = res.pending;
        side.pendingPage = res.page ?? null;
      })
      .catch((err: unknown) => {
        side.pendingMessage = readMessage(err);
      }),
  ]);
  return side;
}

/** One selected run, once the panel has tried to obtain it. */
type SideState =
  | { status: 'waiting' }
  | { status: 'loading' }
  | { status: 'run'; run: ApiRunView }
  | { status: 'missing'; message: string };

export function RunCompare({
  experimentId,
  compareIds,
  loadedRuns,
  listReady,
  hidden,
  onSetCompareIds,
}: {
  experimentId: string;
  /** The ids in the URL, in order, already de-duplicated. May exceed two. */
  compareIds: readonly string[];
  /** The runs currently on the loaded page — the free source for a selection. */
  loadedRuns: readonly ApiRunView[];
  /** True once the first page read has settled, either way. */
  listReady: boolean;
  /** True when Focus Run owns the screen. The live region still mounts. */
  hidden: boolean;
  onSetCompareIds: (ids: string[]) => void;
}) {
  const headingId = useId();
  const selected = compareIds.slice(0, RUN_COMPARE_MAX);
  const ignored = compareIds.slice(RUN_COMPARE_MAX);

  /*
   * THE RUNS THIS PANEL HAS OBTAINED, KEYED BY ID — read directly for a deep link,
   * or COPIED FROM THE PAGE at the moment they were selected.
   *
   * The copy is why the second half exists, and it is not an optimisation. The
   * list under this panel is a page, and searching, filtering or paging replaces
   * it: pick two runs, then type in the search box, and both cards leave the
   * page. Reading the selection only from the page would blank the comparison the
   * reader is looking at, in response to a gesture aimed at the list — and the
   * ids in the URL would still say two runs were being compared.
   *
   * `resolve` still PREFERS the page, so this is a fallback and never a
   * shadow copy that can disagree with what is on screen: while a run is on the
   * page, the page's copy is the one rendered, and a save made through its card
   * is reflected here immediately. Only once a run has left the page does its
   * entry here get used, and then it is honestly a snapshot of the run as it was
   * last read — the same staleness any read of a run already has.
   */
  const [fetched, setFetched] = useState<Record<string, SideState>>({});

  /*
   * The loaded page, readable from an effect that must NOT re-run when it
   * changes. Depending on the array would restart the resolution on every append
   * — and each restart would consider issuing the reads again.
   */
  const loadedRef = useRef<readonly ApiRunView[]>(loadedRuns);
  loadedRef.current = loadedRuns;

  /*
   * The selection as ONE dependency value. `\u0000` is a separator no run id can
   * contain, so `['A B']` and `['A', 'B']` cannot collapse to the same key.
   *
   * WRITTEN AS AN ESCAPE, NEVER AS A LITERAL NUL BYTE. The runtime string is
   * identical, but a raw NUL in the SOURCE makes the whole file binary to `grep`
   * and `rg` — they drop every hit in it and still exit 0. This repository has
   * already had an audit come back clean that way. A file that silently opts out
   * of every future secret, ULID or vocabulary sweep is not an acceptable price
   * for a separator.
   */
  const selectedKey = selected.join('\u0000');

  useEffect(() => {
    if (!listReady) return;
    let alive = true;
    for (const id of selected) {
      const onPage = loadedRef.current.find((run) => run.id === id);
      if (onPage !== undefined) {
        // ALREADY IN HAND — no request, and kept against the moment it leaves
        // the page. See the note on `fetched` above for why this is a fallback
        // rather than a second source of truth.
        setFetched((prev) => ({ ...prev, [id]: { status: 'run', run: onPage } }));
        continue;
      }
      setFetched((prev) => (prev[id] === undefined ? { ...prev, [id]: { status: 'loading' } } : prev));
      api
        .getRun(experimentId, id)
        .then((res) => {
          if (alive) setFetched((prev) => ({ ...prev, [id]: { status: 'run', run: res.run } }));
        })
        .catch((err: unknown) => {
          if (!alive) return;
          /*
           * A 404 IS NOT A STATEMENT ABOUT THE RECORD, and it is not a statement
           * about the other run either. It says this one id does not resolve; the
           * panel then says exactly that beside a control that removes it, and
           * everything else on the screen is untouched.
           */
          const message =
            err instanceof ApiError && err.status === 404
              ? ''
              : err instanceof Error
                ? err.message
                : String(err);
          setFetched((prev) => ({ ...prev, [id]: { status: 'missing', message } }));
        });
    }
    return () => {
      alive = false;
    };
    // `selectedKey` stands in for `selected`, which is a fresh array each render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [experimentId, listReady, selectedKey]);

  const resolve = (id: string): SideState => {
    const onPage = loadedRuns.find((run) => run.id === id);
    if (onPage !== undefined) return { status: 'run', run: onPage };
    return fetched[id] ?? { status: 'waiting' };
  };

  const states = selected.map(resolve);
  const runA = states[0]?.status === 'run' ? states[0].run : undefined;
  const runB = states[1]?.status === 'run' ? states[1].run : undefined;

  /*
   * THE COMPOSITE IDENTITY OF THIS COMPARISON — which two runs, at which two
   * versions. Everything downstream that can go stale is keyed on it.
   *
   * It was already the `key` on `CompareFindings`, for the reasons written out
   * below that element. It is lifted to a value here because a second thing now
   * depends on it (the record context) and because a third now needs to READ it: a
   * finding can only be attached to a table row if the verdicts and the table are
   * known to describe the same two runs, and a React `key` is not readable.
   */
  const compareKey =
    runA !== undefined && runB !== undefined
      ? `${runA.id}@${runA.version}|${runB.id}@${runB.version}`
      : '';

  const [context, setContext] = useState<{ key: string; state: ContextState } | null>(null);
  const [rereadNonce, setRereadNonce] = useState(0);
  /*
   * WHICH READ HAS ALREADY BEEN ISSUED, so that returning from Focus Run does not
   * re-issue it. `hidden` is in the effect's dependencies (nothing is read while
   * the panel is not on screen) and toggles every time the reader opens and closes
   * a run — without this the same four requests would fire on every round trip.
   */
  const contextReadRef = useRef('');

  /*
   * WHICH PAIR, AT WHICH VERSIONS, ON WHICH ATTEMPT — the identity BOTH the
   * de-duplication ref and the stored response are keyed on.
   *
   * THE NONCE IS IN THE KEY, and that is what lets the response be matched by key
   * instead of by an `alive` flag. Read again re-issues under a NEW key, so a
   * first read that answers after the second was issued can no longer be mistaken
   * for it.
   */
  const contextKey = compareKey === '' ? '' : `${compareKey}#${rereadNonce}`;

  useEffect(() => {
    if (contextKey === '' || hidden) return;
    if (contextReadRef.current === contextKey) return;
    contextReadRef.current = contextKey;
    setContext({ key: contextKey, state: { status: 'loading' } });
    void Promise.all([
      readSideContext(experimentId, selected[0]),
      readSideContext(experimentId, selected[1]),
    ]).then(([a, b]) => {
      /*
       * NO `alive` FLAG, AND ITS REMOVAL IS A FIX RATHER THAN A TIDY-UP.
       *
       * `hidden` is in this effect's dependencies, so entering Focus Run tore the
       * effect down — and an `alive = false` cleanup then DISCARDED a read that
       * was already in flight while `contextReadRef` went on saying it had been
       * issued. Coming back re-ran the effect, matched the ref and returned: the
       * panel sat on `{ status: 'loading' }` permanently, telling the reader it
       * was "reading what else this record holds" when nothing was in flight and
       * nothing ever would be. There is no recovery control in that state — `Read
       * again` lives in the band the loading branch replaces — so it was a false
       * progress claim with no way out, and the conflicts axis stayed `unknown`
       * for the rest of the session.
       *
       * The response is matched by KEY instead. A pair (or a Read again) that has
       * moved on leaves `prev.key` different and this answer is dropped, which is
       * everything `alive` was there to do; a read that was merely hidden and
       * un-hidden still lands. Nothing is re-requested to achieve it.
       */
      setContext((prev) =>
        prev !== null && prev.key === contextKey && prev.state.status === 'loading'
          ? { key: contextKey, state: { status: 'ready', a, b } }
          : prev,
      );
    });
    // `selected` is a fresh array per render; `contextKey` names the same two runs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [experimentId, contextKey, hidden]);

  /*
   * THE CONTEXT ONLY COUNTS FOR THE PAIR IT WAS READ FOR. A key mismatch is
   * treated as "not obtained", never as "obtained and empty" — which is the whole
   * difference between a row saying nothing is stored and a row saying nobody
   * looked.
   */
  const ready =
    context !== null && context.key === contextKey && context.state.status === 'ready'
      ? context.state
      : null;
  const contextLoading =
    context !== null && context.key === contextKey && context.state.status === 'loading';

  const comparison = useMemo(
    () =>
      runA !== undefined && runB !== undefined
        ? buildRunComparison(runA, runB, {
            a: { conflicts: ready?.a.conflicts?.conflicts },
            b: { conflicts: ready?.b.conflicts?.conflicts },
          })
        : null,
    [runA, runB, ready],
  );

  /*
   * THE TWO CHECK RESPONSES, HELD BESIDE THE PAIR THEY DESCRIBE.
   *
   * They used to live inside `CompareFindings`, evicted by a React `key`. The
   * eviction is unchanged in effect and is now STATED rather than delegated: a
   * stored key that is not `compareKey` reads as `idle`, so a verdict computed for
   * a previous pair can neither be displayed under the current pair's labels nor
   * attached to a row of the current pair's table. Storing it here is what lets a
   * finding reach the row it names.
   */
  const [check, setCheck] = useState<{ key: string; state: CheckState }>({
    key: '',
    state: { status: 'idle' },
  });
  const checkState: CheckState =
    check.key === compareKey ? check.state : { status: 'idle' };

  const [showAgreeing, setShowAgreeing] = useState(false);

  const remove = (id: string) => onSetCompareIds(compareIds.filter((other) => other !== id));

  const announcement = announce({
    hidden,
    selected,
    states,
    comparison,
    showAgreeing,
  });

  return (
    <>
      {/*
        ONE LIVE REGION, MOUNTED IN EVERY STATE INCLUDING NONE.

        It is outside every conditional on purpose. A region that arrives carrying
        its own content is generally not announced, so a region created at the
        moment the first run is selected would stay silent for the one event a
        reader most needs spoken — the event their own click caused. This is the
        same defect the runs toolbar was measured to have and fixed; it is not
        re-introduced one component along.

        `aria-live="polite"` rather than `role="status"`: the record screen already
        carries a `role="status"` region per run card and one in the runs toolbar,
        and a fourth answering to the same name makes "the status region"
        ambiguous to anything that addresses one by role — including this repo's
        own specs.
      */}
      <p className="rc-live" aria-live="polite" aria-atomic="true">
        {announcement}
      </p>

      {!hidden && selected.length === 1 && (
        <PickingBar
          state={states[0]}
          id={selected[0]}
          onRemove={() => remove(selected[0])}
        />
      )}

      {!hidden && selected.length >= RUN_COMPARE_MAX && (
        <section className="rc-panel" aria-labelledby={headingId}>
          <div className="rc-head">
            <h3 className="rc-title" id={headingId}>
              <Columns2 size={16} strokeWidth={2} aria-hidden="true" />
              Comparing two runs
            </h3>
            {/*
              THE SCOPE SENTENCE, AND IT IS NOT A REASSURANCE. It states two facts a
              reader would otherwise have to infer: nothing on this surface writes,
              and nothing on it evaluates. The second half is the one that matters —
              a table headed "Comparison" invites the reading that the app has an
              opinion about which run is right.
            */}
            <p className="rc-scope">
              A read-only side-by-side of what each run records. Nothing here changes
              either run, and nothing here says which value is correct — that is what
              Check Run and the official-schema gate are for.
            </p>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => onSetCompareIds([])}
            >
              Clear comparison
            </button>
          </div>

          {ignored.length > 0 && (
            /*
              MORE THAN TWO IDS IN THE LINK. Silently comparing the first two would
              make a link that names four runs render as a comparison of two with no
              indication that half of it was dropped. The extra ids are NAMED, and
              the reason is stated once — see `RUN_COMPARE_MAX`.
            */
            <p className="rc-note" role="status">
              This link names {compareIds.length} runs. A comparison here is between two, so{' '}
              {ignored.length === 1 ? 'this run is' : 'these runs are'} not compared:{' '}
              <span className="mono">{ignored.join(', ')}</span>.
            </p>
          )}

          <div className="rc-sides">
            {selected.map((id, index) => (
              <SideHeader
                key={id}
                index={index}
                id={id}
                state={states[index]}
                onRemove={() => remove(id)}
              />
            ))}
          </div>

          {comparison === null ? (
            <UnresolvedComparison states={states} ids={selected} />
          ) : (
            <>
              <RecordContext
                runA={runA!}
                runB={runB!}
                ready={ready}
                loading={contextLoading}
                onReread={() => setRereadNonce((n) => n + 1)}
              />
              <CompareSummary
                comparison={comparison}
                showAgreeing={showAgreeing}
                onShowAgreeing={setShowAgreeing}
              />
              <CompareTable
                comparison={comparison}
                runA={runA!}
                runB={runB!}
                showAgreeing={showAgreeing}
                findings={checkState.status === 'data' ? findingsByPath(checkState) : null}
              />
              {comparison.blocks.length > 0 && (
                <BlockDisclosure
                  blocks={comparison.blocks}
                  labelA={runA!.label}
                  labelB={runB!.label}
                />
              )}
              {/*
                KEYED ON WHICH RUNS AND WHICH VERSIONS, and it was not.

                THE KEY IS NOW `compareKey`, HELD IN STATE BESIDE THE RESPONSES
                RATHER THAN PASSED AS A REACT `key`. Everything below is unchanged
                about WHY the eviction exists and what it prevents; only the
                mechanism moved, because a finding cannot be attached to a table
                row unless something can READ which pair the verdicts describe, and
                a React `key` cannot be read. `checkState` above is the eviction:
                a stored key that is not the current pair reads as `idle`.

                `CompareFindings` holds the two check responses in local state
                with no eviction of any kind, and this element carried no `key`,
                so React preserved that state across every prop change. Two
                measured consequences, both of them a stale verdict presented as
                a current one:

                  · save a run after "Check both runs" and the old verdicts stay
                    on screen. `RunsSection.replaceRun` substitutes a NEW run
                    object with a NEW `version`, so the table above recomputes
                    and the verdicts below it do not;
                  · change ONE of the two compared runs and the verdicts fetched
                    for the previous pair are re-rendered under the NEW runs'
                    labels — `FindingsResult` takes `labelA`/`labelB` from the
                    current props while `check.a`/`check.b` are the old
                    responses. That is a mislabelling, not merely staleness.

                The only thing that stopped either being silent is the
                `Read-only check of run version {res.checked_run_version}` line
                beside each verdict, which named a version the reader had to
                notice for themselves.

                The key resets the panel to `idle` — the reader is offered the
                check again — which is the same discipline the Evidence Graph
                already applies through `readRunCheck`: a cached verdict whose
                run version has moved is not served, it is evicted
                (`lib/evidenceGraph.ts`, RunCheckStore). Two surfaces in one
                product should not disagree about whether a stale verdict may be
                displayed.

                WHAT THE KEY OMITS, NAMED RATHER THAN LEFT TO BE REDISCOVERED:
                `experimentId`. Two experiments would have to hold runs with the
                SAME id AND the same version for the stale state to survive a
                change of record, and run ids are ULIDs minted per run — so it
                is not reachable in this product as built. It is written down
                because the reasoning is an argument about id generation rather
                than a property of this component, and the next surface that
                keys on a run identity should not have to re-derive it. Adding
                it costs one interpolation if that ever stops holding.
              */}
              <CompareFindings
                experimentId={experimentId}
                runA={runA!}
                runB={runB!}
                state={checkState}
                onState={(next) => setCheck({ key: compareKey, state: next })}
              />
            </>
          )}
        </section>
      )}
    </>
  );
}

/* ── selection ─────────────────────────────────────────────────────────────── */

/**
 * ONE RUN CHOSEN, ONE STILL TO GO — shown ABOVE the list, which stays exactly as
 * it was. The list is the picker: the reader searches, filters and pages to the
 * second run with the controls they were already using, and nothing here fetches
 * anything to populate a chooser.
 */
function PickingBar({
  state,
  id,
  onRemove,
}: {
  state: SideState;
  id: string;
  onRemove: () => void;
}) {
  const label = state.status === 'run' ? state.run.label : id;
  return (
    <div className="rc-picking">
      <p className="rc-picking-text">
        <Columns2 size={14} strokeWidth={2} aria-hidden="true" />
        <span>
          <strong>{label}</strong> is selected for comparison. Choose one more run — the search,
          filters and paging above all still work, and Compare on any card adds it.
        </span>
      </p>
      <button type="button" className="btn btn-secondary" onClick={onRemove}>
        Cancel comparison
      </button>
    </div>
  );
}

function SideHeader({
  index,
  id,
  state,
  onRemove,
}: {
  index: number;
  id: string;
  state: SideState;
  onRemove: () => void;
}) {
  const label = state.status === 'run' ? state.run.label : id;
  return (
    <div className="rc-side" data-side={index === 0 ? 'a' : 'b'}>
      <p className="rc-side-eyebrow">{index === 0 ? 'First run' : 'Second run'}</p>
      <p className="rc-side-label">{label}</p>
      <p className="rc-side-id mono">{id}</p>
      <button type="button" className="btn btn-secondary" onClick={onRemove}>
        {/*
          "Replace" rather than "Remove", because removing one of two returns the
          reader to the list with the other one still selected — which is the
          gesture they actually want when a comparison is nearly right. The run is
          named in the accessible name and APPENDED after the visible word, the
          WCAG 2.5.3 ordering every control in this area uses.
        */}
        Replace<span className="sr-only"> {label}</span>
      </button>
    </div>
  );
}

/**
 * A comparison that cannot be drawn, and WHICH SIDE could not be obtained.
 *
 * Never a blank panel and never a claim about the record: an id that does not
 * resolve says nothing about whether the record exists, and the record screen
 * around this section is proof that it does.
 */
function UnresolvedComparison({
  states,
  ids,
}: {
  states: readonly SideState[];
  ids: readonly string[];
}) {
  const missing = states
    .map((state, i) => ({ state, id: ids[i] }))
    .filter((entry) => entry.state.status === 'missing');
  if (missing.length > 0) {
    return (
      <div className="rc-unresolved" role="alert">
        {missing.map(({ state, id }) => (
          <p key={id}>
            No run with the id <span className="mono">{id}</span> is in this record. It may have
            been deleted, or the link may be for a different record.
            {state.status === 'missing' && state.message !== ''
              ? ` The server said: ${state.message}`
              : ''}{' '}
            Replace it to compare something else.
          </p>
        ))}
      </div>
    );
  }
  return <LoadingPanel label="Loading the two runs to compare…" />;
}

/* ── the record context these two runs sit in ──────────────────────────────── */

/**
 * WHAT ELSE THE RECORD HOLDS ABOUT EACH RUN — open questions, and recorded
 * conflicts. Two facts per run, neither of which the table above can see.
 *
 * WHY THIS IS NOT IN THE TABLE. An open question does not belong to an address a
 * comparison can put in a row. `ApiPendingItem` carries `kind`, `about` and an
 * `id` that is a URI for assets and a kind for everything else — none of which is
 * the official path a row is keyed by — so attaching a question to a row would
 * mean matching prose against an address and calling the guess a fact. The
 * questions are therefore reported PER RUN, where the data actually is, and the
 * panel says so rather than leaving the omission to be noticed.
 *
 * WHAT IT DELIBERATELY DOES NOT COMPARE. Neither number is subtracted from the
 * other, and there is no "Run 1 is further along". Both are stated side by side
 * and the reader draws their own conclusion — the same refusal the verdicts below
 * make, for the same reason.
 */
function RecordContext({
  runA,
  runB,
  ready,
  loading,
  onReread,
}: {
  runA: ApiRunView;
  runB: ApiRunView;
  ready: { a: SideContext; b: SideContext } | null;
  loading: boolean;
  onReread: () => void;
}) {
  const headingId = useId();
  if (loading) {
    return (
      <p className="rc-note" role="status">
        Reading what else this record holds about these two runs…
      </p>
    );
  }
  if (ready === null) {
    return (
      <p className="rc-note">
        Open questions and recorded conflicts have not been read for these two runs. The table
        below compares what each run holds and says nothing either way about them.
      </p>
    );
  }
  /*
   * THE FRESHNESS CHECK, AND IT IS A REAL ONE RATHER THAN A RESTATEMENT.
   *
   * Each conflicts response carries the `record_rev` it was computed at. The two
   * reads are issued together but answered separately, so a record that changes
   * between them yields two different revisions — and the union of two views of
   * different documents is not a view of either. It is DISCLOSED rather than
   * hidden, and rather than being made to look current by showing only one.
   */
  const revA = ready.a.conflicts?.record_rev ?? null;
  const revB = ready.b.conflicts?.record_rev ?? null;
  const split = revA !== null && revB !== null && revA !== revB;
  return (
    <section className="rc-context" aria-labelledby={headingId}>
      <div className="rc-context-head">
        <h4 className="rc-context-title" id={headingId}>
          What else this record holds about each run
        </h4>
        <button type="button" className="btn btn-secondary" onClick={onReread}>
          Read again
        </button>
      </div>
      {/*
        THE ONE SENTENCE THAT STOPS THIS READING AS A SURVEY OF EVERYTHING.
        A conflict at an address a run INHERITS is stored once, at the record, and
        decided there; `GET .../conflicts?run=` describes a run's own fields only.
        Saying nothing here would let an empty conflict line read as "there are
        none anywhere", which is a claim neither read supports.
      */}
      <p className="rc-context-scope">
        Read for each run on its own, once. Conflicts recorded against the record rather than
        against a run are not read here — they are the same for both runs and are decided on the
        record. Nothing on this panel is written, and no run was changed by reading it.
      </p>
      {split && (
        <p className="rc-note" role="status">
          These two reads answered at different revisions of the record — {runA.label} at
          revision {revA}, {runB.label} at revision {revB}. The record changed while they were
          being read. Use Read again for one revision.
        </p>
      )}
      <div className="rc-context-sides">
        <ContextSide run={runA} side={ready.a} />
        <ContextSide run={runB} side={ready.b} />
      </div>
    </section>
  );
}

function ContextSide({ run, side }: { run: ApiRunView; side: SideContext }) {
  /*
   * THE REVISION IS THE PRECISE IDENTITY; THE DATE IS CONTEXT. `run.rev` and
   * `run.version` are what a stale screen is recognised by, and they are exact —
   * so the date is rendered readably and the exact instant the server sent stays
   * on the `<time>` element rather than being dropped.
   */
  const updated = formatCreatedDate(run.updated_utc);
  const counts = side.conflicts?.counts;
  const page = side.pendingPage;
  const openCount = page !== null ? page.total : side.pending.length;
  return (
    <div className="rc-context-side">
      <p className="rc-context-label">{run.label}</p>
      {/*
        THE RUN'S OWN REVISION, STATED. A comparison is a read of two documents at
        two particular moments; naming the moment is what makes a stale screen
        recognisable as one instead of looking like a current answer.
      */}
      <p className="rc-context-rev">
        Revision {run.rev} · version <span className="mono">{run.version}</span>
        {updated !== undefined ? (
          <>
            {' '}
            · updated <time dateTime={run.updated_utc}>{updated.display}</time>
          </>
        ) : null}
      </p>

      {side.pendingMessage !== null ? (
        <p className="rc-context-fail" role="status">
          Open questions could not be read for this run. {side.pendingMessage} Nothing is claimed
          about how many are outstanding.
        </p>
      ) : (
        <>
          <p className="rc-context-fact">
            <strong>{openCount}</strong> open question{openCount === 1 ? '' : 's'} owned by this
            run
            {page !== null && page.record_total !== openCount ? (
              <> · {page.record_total} open on the whole record</>
            ) : null}
          </p>
          {side.pending.length > 0 && (
            <ul className="rc-context-list">
              {side.pending.map((item, index) => (
                <li key={item.blocker_key ?? `${item.id ?? 'entry'}#${index}`}>
                  {item.unavailable === true
                    ? `An entry this build could not read${item.unavailable_reason ? ` — ${item.unavailable_reason}` : ''}`
                    : (item.question ?? item.about ?? item.kind ?? 'An entry carrying no question text')}
                </li>
              ))}
              {page !== null && page.withheld > 0 && (
                <li className="rc-context-more">
                  {page.withheld} further open question{page.withheld === 1 ? '' : 's'} on this
                  run are not listed here.
                </li>
              )}
            </ul>
          )}
        </>
      )}

      {side.conflictsMessage !== null ? (
        <p className="rc-context-fail" role="status">
          Recorded conflicts could not be read for this run. {side.conflictsMessage} The table
          below says nothing either way about them.
        </p>
      ) : counts === undefined ? null : (
        <>
          <p className="rc-context-fact">
            <strong>{counts.conflicting_addresses}</strong> address
            {counts.conflicting_addresses === 1 ? '' : 'es'} on this run cite more than one
            answer
            {counts.conflicting_addresses > 0 ? (
              <>
                {' '}
                · {counts.resolved} decided · {counts.unresolved} still awaiting a decision
              </>
            ) : null}
          </p>
          {side.conflicts !== null && side.conflicts.unreadable_resolution_entries > 0 && (
            <p className="rc-context-fail">
              {side.conflicts.unreadable_resolution_entries} stored decision
              {side.conflicts.unreadable_resolution_entries === 1 ? '' : 's'} could not be read by
              this build. They are counted rather than described: saying what one contains would
              mean inventing it.
            </p>
          )}
          {side.conflicts !== null && side.conflicts.resolutions_without_conflict.length > 0 && (
            <p className="rc-context-fail">
              {side.conflicts.resolutions_without_conflict.length} recorded decision
              {side.conflicts.resolutions_without_conflict.length === 1 ? ' names' : 's name'} an
              address this run carries no conflict at.
            </p>
          )}
        </>
      )}
    </div>
  );
}

/* ── the blocks this table does not compare ────────────────────────────────── */

/**
 * THE SAME BOUNDARY `overrideRows` DRAWS, disclosed rather than denied — and the
 * disclosure now says what is in each block.
 *
 * A block payload is an object or a list; this table has no honest one-line
 * rendering for one, so it is still named and still not compared. What is stated
 * instead is which top-level KEYS each run's payload carries, which is checkable
 * by opening either run and asserts nothing about what is under them. Two payloads
 * are never deep-equalled into "the same": a verdict the reader cannot see is a
 * verdict they cannot check.
 */
function BlockDisclosure({
  blocks,
  labelA,
  labelB,
}: {
  blocks: readonly CompareBlock[];
  labelA: string;
  labelB: string;
}) {
  return (
    <div className="rc-blocks">
      <p className="rc-note">
        {blocks.length} whole-block address{blocks.length === 1 ? '' : 'es'} resolved by these
        runs {blocks.length === 1 ? 'is' : 'are'} not compared here. A block is an object or a
        list, and this table has no one-line rendering for one. What each run records inside one
        is listed by name below; nothing is said about the values under those names.
      </p>
      <ul className="rc-block-list">
        {blocks.map((block) => (
          <li key={block.name}>
            <span className="mono">{block.name}</span>
            {' — '}
            <BlockKeys block={block} labelA={labelA} labelB={labelB} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function BlockKeys({
  block,
  labelA,
  labelB,
}: {
  block: CompareBlock;
  labelA: string;
  labelB: string;
}) {
  const side = (label: string, present: boolean, unnamed: boolean, keys: string[]) => {
    if (!present) return `${label} does not resolve it`;
    if (unnamed) return `${label} records something here that is not a set of named keys`;
    if (keys.length === 0) return `${label} records it with no keys`;
    return `${label} records ${keys.join(', ')}`;
  };
  const only =
    block.onlyA.length === 0 && block.onlyB.length === 0
      ? null
      : [
          block.onlyA.length > 0 ? `${block.onlyA.join(', ')} only on ${labelA}` : null,
          block.onlyB.length > 0 ? `${block.onlyB.join(', ')} only on ${labelB}` : null,
        ]
          .filter((part): part is string => part !== null)
          .join('; ');
  return (
    <>
      {side(labelA, block.presentOnA, block.unnamedA, block.keysA)};{' '}
      {side(labelB, block.presentOnB, block.unnamedB, block.keysB)}.
      {only !== null && <> Named on one run only: {only}.</>}
    </>
  );
}

/* ── summary ───────────────────────────────────────────────────────────────── */

/**
 * THE COUNTS, AND EVERY ONE OF THEM IS A COUNT OF ROWS IN THE TABLE BELOW.
 *
 * There is no similarity score and there must not be one: similarity has no
 * denominator, and a percentage over "how much of two runs is the same" would be
 * exactly the invented figure this repo's denominator rule forbids. The four
 * breakdown numbers PARTITION the differing rows — a row that differs in value and
 * in provenance is counted once, under value, and says both things in its own cell.
 *
 * AND THE THREE HEADLINE NUMBERS DO NOT HAVE TO SUM. `incomparable` is neither a
 * difference nor an agreement, so it is stated as its own number instead of being
 * absorbed by whichever of the other two would balance the line.
 *
 * THE AGREEING COUNT IS ALWAYS STATED, EVEN WHEN THOSE ROWS ARE HIDDEN. A reader
 * asking "are these the same apart from temperature?" is asking about the number
 * that a differences-only comparison never shows them.
 */
function CompareSummary({
  comparison,
  showAgreeing,
  onShowAgreeing,
}: {
  comparison: RunComparison;
  showAgreeing: boolean;
  onShowAgreeing: (next: boolean) => void;
}) {
  const { tally } = comparison;
  const toggleId = useId();
  const parts: string[] = [];
  if (tally.value > 0) {
    parts.push(`${tally.value} hold different values`);
  }
  if (tally.absentOnOne > 0) {
    parts.push(`${tally.absentOnOne} recorded on one run only`);
  }
  if (tally.review > 0) {
    parts.push(`${tally.review} the same value in a different review state`);
  }
  if (tally.provenance > 0) {
    parts.push(`${tally.provenance} the same value from a different source`);
  }
  if (tally.evidence > 0) {
    parts.push(`${tally.evidence} the same value with different record-keeping`);
  }
  if (tally.incomparable > 0) {
    parts.push(`${tally.incomparable} not compared here`);
  }
  return (
    <div className="rc-summary">
      {/*
        THREE NUMBERS THAT DO NOT HAVE TO SUM, and the fourth clause is why.

        An `incomparable` row is not a difference and not an agreement — the table
        could not read it — so it is stated on its own rather than being folded into
        whichever of the other two would make the arithmetic tidy. Folding it into
        `differ in some way` was the earlier behaviour and it put a disagreement on
        screen that nothing had observed.
      */}
      <p className="rc-summary-line">
        <strong>{tally.compared}</strong> address{tally.compared === 1 ? '' : 'es'} listed ·{' '}
        <strong>{tally.differing}</strong> differ in some way ·{' '}
        <strong>{tally.agreeing}</strong> the same on both runs
        {tally.bothAbsent > 0 && (
          <>
            {' '}
            (<span>{tally.bothAbsent} of those where neither run records a value</span>)
          </>
        )}
        {tally.incomparable > 0 && (
          <>
            {' '}
            · <strong>{tally.incomparable}</strong> this table could not compare
          </>
        )}
      </p>
      {parts.length > 0 && (
        <ul className="rc-breakdown">
          {parts.map((part) => (
            <li key={part}>{part}</li>
          ))}
        </ul>
      )}
      {tally.conflictsUnknown && (
        /*
          NEVER AN ABSENT LINE. With the conflicts read missing for a run, every row
          below is silent about recorded conflicts — and silence in a comparison
          reads as "there are none". This says which it is, once.
        */
        <p className="rc-summary-line">
          Recorded conflicts were not read for at least one of these runs, so nothing below says
          either way whether one is stored at an address.
        </p>
      )}
      {tally.conflicted > 0 && (
        /*
          A SIXTH NUMBER THAT SUMS WITH NOTHING, and the sentence says why.

          A recorded conflict is a fact about ONE run's own citations at one
          address. It is not a disagreement between the two runs, so it is not in
          `differ in some way`; it is not an agreement either. Folding it into
          either would put a claim on screen that neither read supports — the same
          mistake `incomparable` is stated separately to avoid.
        */
        <p className="rc-summary-line">
          <strong>{tally.conflicted}</strong> address
          {tally.conflicted === 1 ? '' : 'es'} carry a conflict recorded against one of these
          runs&rsquo; own citations — {tally.conflictedUnresolved} still awaiting a decision.
          That is not a disagreement between the two runs: it never sets the comparison a row
          is listed under, and it is in none of the numbers above. An address may carry one and
          also differ on some axis, and it is then among the differences above for that
          difference alone.
          {tally.conflictedAgreeing > 0 && (
            <>
              {' '}
              {tally.conflictedAgreeing} of them are addresses where the two runs record the same
              thing, and {tally.conflictedAgreeing === 1 ? 'it is' : 'they are'} listed below
              anyway.
            </>
          )}
        </p>
      )}
      {tally.differing === 0 && (
        /*
          THE DENOMINATOR IS `agreeing`, NOT `compared`. It used to be `compared`,
          which silently included the addresses this table could not read — so a
          pair of runs with one unreadable address was described as agreeing "at
          every one of the 10 addresses compared here" when only 9 had been.
        */
        <p className="rc-summary-line">
          These two runs record the same value, from the same source, in the same review state,
          with the same status and the same cited entries, at every one of the {tally.agreeing}{' '}
          address{tally.agreeing === 1 ? '' : 'es'} this table was able to compare.
          {tally.incomparable > 0
            ? ` ${tally.incomparable} further address${tally.incomparable === 1 ? '' : 'es'} could not be compared and ${tally.incomparable === 1 ? 'is' : 'are'} listed below.`
            : ''}{' '}
          That is what this table can see; it is not a statement that the runs are identical.
        </p>
      )}
      <label className="rc-toggle" htmlFor={toggleId}>
        <input
          id={toggleId}
          type="checkbox"
          checked={showAgreeing}
          onChange={(e) => onShowAgreeing(e.target.checked)}
        />
        Also show the {tally.agreeing} address{tally.agreeing === 1 ? '' : 'es'} that are the same
        on both runs
      </label>
    </div>
  );
}

/* ── the table ─────────────────────────────────────────────────────────────── */

/** " and N this table could not compare", or nothing at all when there are none. */
function incomparableClause(n: number): string {
  if (n === 0) return '';
  return `, and ${n} ${n === 1 ? 'address' : 'addresses'} this table could not compare`;
}

/**
 * THE EXCEPTION TO "the same on both runs and are not listed".
 *
 * A row carrying a recorded conflict IS listed even when the two runs agree, so
 * without this the caption would describe a table the reader can see contradicts
 * it. Empty when there are none, which is every comparison with no conflicts read
 * or none recorded — the caption is then byte-identical to what it always was.
 */
function agreeingConflictClause(n: number): string {
  if (n === 0) return '';
  /* NO "because". `run-compare.test.tsx`'s vocabulary scan bans the word outright,
     and the ban is not negotiable for a caption merely because the causality here
     is about the table rather than about the science — a scanner with exceptions is
     a scanner nobody trusts. A colon states the same fact and reads better. */
  return `, except ${n} listed anyway: a conflict is recorded at ${n === 1 ? 'it' : 'them'}`;
}

/**
 * EVERY FINDING THAT NAMES AN ADDRESS, INDEXED BY THAT ADDRESS — and the count of
 * every finding that names none.
 *
 * THE ATTACHMENT RULE IS EXACTLY ONE THING: the finding object carries a `path`,
 * and that path equals a row's own path. Nothing is matched on prose, nothing is
 * matched on a prefix, and a bare-string finding is never attached — the union
 * `ApiRunCheckFinding` includes a plain string precisely because the contract does
 * not say what an element is, and reading an address out of a sentence would be a
 * guess presented as a link.
 *
 * WHAT IS NOT ATTACHED IS COUNTED, not dropped. The panel below still lists every
 * finding of both runs, and the table says how many of them name no address, so
 * "no finding is attached to this row" can never be read as "no finding exists".
 */
interface RowFindings {
  a: Map<string, string[]>;
  b: Map<string, string[]>;
  /**
   * FINDINGS THAT NAME NO ADDRESS AT ALL, and nothing else.
   *
   * IT USED TO ALSO COUNT A FINDING THIS BUILD COULD NOT DESCRIBE, which made the
   * sentence built on it say that an undescribable finding "names no address" —
   * a claim about a `path` the number had not looked at, in a panel that counts
   * those separately one paragraph below. The two are different facts and are
   * counted in different places.
   *
   * IT IS DELIBERATELY NOT "findings not shown on a row". A finding may name a
   * path this table has no row for — the comparison's rows are the addresses the
   * two runs RESOLVE, and an official-schema error can name any path in the
   * document — and this number cannot see that, because the rows are not in
   * scope here. The sentence beside it is written to that limit rather than past
   * it: it says a named path is shown on that row WHERE THIS TABLE LISTS THE
   * ADDRESS, which is checkable, instead of promising an attachment that may not
   * exist.
   */
  unattached: number;
}

function pathFindings(res: ApiRunCheckResponse): { byPath: Map<string, string[]>; unattached: number } {
  const all = [
    ...(res.blockers ?? []),
    ...(res.draft?.errors ?? []),
    ...(res.official?.errors ?? []),
  ];
  const byPath = new Map<string, string[]>();
  let unattached = 0;
  for (const finding of all as ApiRunCheckFinding[]) {
    const text = runFindingText(finding);
    const path =
      finding !== null && typeof finding === 'object' && typeof finding.path === 'string'
        ? finding.path.trim()
        : '';
    if (path === '') {
      unattached += 1;
      continue;
    }
    // A finding that names an address but that this build cannot describe is NOT
    // counted here — `findingTexts`'s `opaque` is where it is counted, and saying
    // it names no address would be false about the one field this loop did read.
    if (text === null) continue;
    const list = byPath.get(path);
    if (list === undefined) byPath.set(path, [text]);
    else list.push(text);
  }
  return { byPath, unattached };
}

function findingsByPath(check: { a: ApiRunCheckResponse; b: ApiRunCheckResponse }): RowFindings {
  const a = pathFindings(check.a);
  const b = pathFindings(check.b);
  return { a: a.byPath, b: b.byPath, unattached: a.unattached + b.unattached };
}

function CompareTable({
  comparison,
  runA,
  runB,
  showAgreeing,
  findings,
}: {
  comparison: RunComparison;
  runA: ApiRunView;
  runB: ApiRunView;
  showAgreeing: boolean;
  findings: RowFindings | null;
}) {
  const groups = comparison.groups
    .map((group) => ({
      ...group,
      // `listed`, not "differs": a row this table could not read is shown by
      // default too, because hiding it would be the table quietly asserting that
      // there is nothing there to see.
      shown: showAgreeing ? group.rows : group.rows.filter((row) => row.listed),
    }))
    .filter((group) => group.shown.length > 0);

  if (groups.length === 0) {
    return (
      <p className="rc-note">
        No address differs between these two runs. Tick the box above to see the{' '}
        {comparison.tally.agreeing} that are the same.
      </p>
    );
  }

  return (
    /*
      A FOCUSABLE SCROLL CONTAINER. The table can be wider than a phone, so it
      scrolls horizontally — and a scrollable region that cannot take keyboard
      focus is unreachable by keyboard alone (axe `scrollable-region-focusable`).
      `role="group"` rather than `region`: a landmark named the same as another
      landmark trips `landmark-unique`, and this needs a name, not a landmark.
    */
    <div
      className="rc-tablewrap"
      tabIndex={0}
      role="group"
      aria-label={`Comparison of ${runA.label} and ${runB.label}`}
    >
      <table className="rc-table">
        {/*
          THE CAPTION SAYS WHAT THE TABLE IS SHOWING AND WHAT IT IS WITHHOLDING,
          and it counts the third category rather than folding it into "differ".
          The default view lists rows that differ AND rows this table could not
          compare, so calling it "addresses where they differ" would misdescribe
          the rows the reader can see.
        */}
        <caption className="rc-caption">
          {showAgreeing
            ? `Every address listed for ${runA.label} and ${runB.label} — ${comparison.tally.differing} that differ, ${comparison.tally.agreeing} that are the same${incomparableClause(comparison.tally.incomparable)}.`
            : `Addresses where ${runA.label} and ${runB.label} differ${comparison.tally.incomparable > 0 ? `, and ${comparison.tally.incomparable} this table could not compare` : ''}. ${comparison.tally.agreeing} further address${comparison.tally.agreeing === 1 ? ' is' : 'es are'} the same on both runs and ${comparison.tally.agreeing === 1 ? 'is' : 'are'} not listed${agreeingConflictClause(comparison.tally.conflictedAgreeing)}.`}
        </caption>
        <thead>
          <tr>
            <th scope="col">Address</th>
            <th scope="col">{runA.label}</th>
            <th scope="col">{runB.label}</th>
            <th scope="col">Comparison</th>
          </tr>
        </thead>
        {groups.map((group) => (
          <tbody key={group.id}>
            <tr className="rc-group">
              <th colSpan={4} scope="colgroup">
                {group.title}
                <span className="rc-group-count">
                  {group.shown.length} of {group.rows.length} shown
                </span>
              </th>
            </tr>
            {group.shown.map((row) => (
              <Row key={row.key} row={row} runA={runA} runB={runB} findings={findings} />
            ))}
          </tbody>
        ))}
      </table>
    </div>
  );
}

function Row({
  row,
  runA,
  runB,
  findings,
}: {
  row: CompareRow;
  runA: ApiRunView;
  runB: ApiRunView;
  findings: RowFindings | null;
}) {
  const Glyph = CATEGORY_ICON[row.category];
  /*
   * PROGRESSIVE DISCLOSURE, NOT MORE COLUMNS. Four dimensions arrived; four columns
   * did not. The table keeps its four headers at every width, and everything the
   * widening added — the cited entries, the two provenance dimensions, the recorded
   * conflict in full, and any finding that names this address — lives in one
   * expandable row per address. A dense table that has to scroll sideways to be
   * read at all is a table nobody reads.
   */
  const [open, setOpen] = useState(false);
  const detailId = useId();
  const findingsA = findings?.a.get(row.path) ?? [];
  const findingsB = findings?.b.get(row.path) ?? [];
  // A SIDE WITH NO VALUE CAN STILL CARRY CITATIONS, so the toggle is offered for
  // one. Without the last two clauses the panel that now describes those entries
  // is unreachable on the one row shape that has them and nothing else.
  const hasDetail =
    row.a.present ||
    row.b.present ||
    row.a.conflict !== null ||
    row.b.conflict !== null ||
    row.a.support.length > 0 ||
    row.b.support.length > 0 ||
    findingsA.length > 0 ||
    findingsB.length > 0;
  return (
    <>
      <tr className="rc-row" data-category={row.category} data-address={row.address}>
        <th scope="row" className="rc-addr">
          <span className="rc-addr-path mono">{row.path}</span>
          <span className="rc-addr-scope">
            {row.scope === 'run-field' ? "the run's own field" : 'record-level address'}
          </span>
        </th>
        <SideCell row={row} side={row.a} run={runA} findings={findingsA} />
        <SideCell row={row} side={row.b} run={runB} findings={findingsB} />
        <td className="rc-rel">
          <span className="rc-rel-state" data-category={row.category}>
            <Glyph size={13} strokeWidth={2.2} aria-hidden="true" />
            {categoryWord(row.category)}
          </span>
          <span className="rc-rel-text">
            <RelationText row={row} runA={runA} runB={runB} />
          </span>
          {(row.conflict === 'one' || row.conflict === 'both') && (
            /*
              THE RECORDED CONFLICT, MARKED SEPARATELY FROM THE CATEGORY — because
              it is a separate fact. The category says what the two RUNS record; this
              says that ONE run's own citations at this address assert more than one
              answer. It never becomes the category, never changes the counts, and
              its words never say the two runs disagree.
            */
            <span className="rc-conflict" data-state={conflictState(row)}>
              <CircleAlert size={12} strokeWidth={2.2} aria-hidden="true" />
              {row.conflict === 'both'
                ? 'A conflict is recorded on both runs here'
                : `A conflict is recorded on ${row.a.conflict !== null ? runA.label : runB.label} here`}
              {/*
                WHETHER IT HAS BEEN DECIDED, IN WORDS. `data-state` tints this mark
                green for `current` and amber otherwise, and for one commit that
                tint was the ONLY carrier of the difference: both marks read "A
                conflict is recorded … here" and the decision state appeared only
                inside the detail row, which is collapsed by default. A decided
                conflict and an undecided one are not a colour apart — this repo's
                own rule is glyph plus words plus surface — so the word is here.

                `conflictState` is `current` only when EVERY recorded conflict on
                this row is currently decided, which is why the other arm says "not
                currently decided" about the row rather than about one side: on a
                `both` row with one decision and one outstanding, that is exactly
                what is true, and naming a side would need a claim per side that
                the mark does not make.
              */}
              {conflictState(row) === 'current'
                ? ' — decided, and the decision still covers these answers'
                : ' — not currently decided'}
            </span>
          )}
          {/*
            THE `unknown` ARM IS DELIBERATELY NOT A ROW MARK.

            An unread conflicts response is one fact about the whole comparison, not
            one fact per address; repeating it on every row of a fifty-row table is
            the wall this widening is written to avoid, and it would drown the rows
            that DO carry a recorded conflict. It is stated once, prominently, in
            two places a reader cannot miss — beside the run it failed for in the
            context band, and in the summary above the table. Rule: never silent,
            never fifty times.
          */}
          {hasDetail && (
            <button
              type="button"
              className="rc-detail-toggle"
              aria-expanded={open}
              /*
                POINTED AT THE PANEL ONLY WHILE THE PANEL EXISTS. The detail row is
                unmounted when collapsed, so an unconditional `aria-controls` is a
                dangling IDREF on every closed row of the table — and this repo
                already settled the pattern six times over (`RecordInfoPanel`,
                `RenameExperimentPanel`, `DiscardStaged`, `RunCard`,
                `AssetReferencesPanel`, `UnmappedNotesPanel` all write
                `open ? id : undefined`). One surface should not disagree.
              */
              aria-controls={open ? detailId : undefined}
              onClick={() => setOpen((prev) => !prev)}
            >
              {open ? (
                <ChevronDown size={12} strokeWidth={2.2} aria-hidden="true" />
              ) : (
                <ChevronRight size={12} strokeWidth={2.2} aria-hidden="true" />
              )}
              {open ? 'Hide what each run records here' : 'Show what each run records here'}
              {/* WCAG 2.5.3: the visible words come first, the address after. */}
              <span className="sr-only"> for {row.path}</span>
            </button>
          )}
        </td>
      </tr>
      {hasDetail && open && (
        <tr className="rc-detail-row" data-detail-for={row.address}>
          <td colSpan={4}>
            <div className="rc-detail" id={detailId}>
              <SideDetail row={row} side={row.a} label={runA.label} findings={findingsA} />
              <SideDetail row={row} side={row.b} label={runB.label} findings={findingsB} />
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

/** Which decision state to surface on the row mark. The worse-known of the two. */
function conflictState(row: CompareRow): string {
  const states = [row.a.conflict?.resolutionState, row.b.conflict?.resolutionState].filter(
    (state): state is string => state !== undefined,
  );
  if (states.length === 0) return 'none';
  // `current` only when EVERY recorded conflict here is currently decided. One
  // undecided address is undecided, whatever the other run recorded.
  return states.every((state) => state === 'current') ? 'current' : 'open';
}

/**
 * ONE RUN'S SIDE OF THE EXPANDED DETAIL — described, never judged.
 *
 * Four things, each read from stored content: where the citations say the value
 * came from, what the provenance mirror says establishes it, WHICH entries are
 * cited, and the recorded conflict in full. Nothing here compares the two runs: the
 * comparison is the row above, and repeating it as a judgement about one side
 * ("better supported") is the one thing this block exists not to do.
 */
function SideDetail({
  row,
  side,
  label,
  findings,
}: {
  row: CompareRow;
  side: CompareSide;
  label: string;
  findings: string[];
}) {
  return (
    <div className="rc-detail-side">
      <p className="rc-detail-label">{label}</p>
      {side.present ? (
        <>
          {/*
            TWO SEPARATE FACTS, NEVER RUN TOGETHER. `originsWord` is what the stored
            CITATIONS say produced the value; `originWord` is whether this RUN holds
            it or reads the record's. They answered the same label for one commit —
            "Inherited from the record · inherited from record" — which reads as a
            rendering fault and hides that they are different questions.
          */}
          <p className="rc-detail-line">
            <span className="rc-detail-key">Where it came from</span> {originsWord(side)}
          </p>
          {row.scope === 'record-level' && (
            <p className="rc-detail-line">
              <span className="rc-detail-key">How this run holds it</span>{' '}
              {originWord(side.origin)}
            </p>
          )}
          <p className="rc-detail-line">
            {/*
              NAMED AS THIS BUILD'S OWN READING, not as a verdict from the server.
              `lib/provenance.ts` computes it from the citations stored on the run and
              deliberately cannot report a recorded decision; saying so is what stops a
              reader treating it as the record's official position.
            */}
            <span className="rc-detail-key">What establishes it</span> {reviewWord(side.reviewState)}
            {' — read from the citations stored on this run, not a decision anybody recorded.'}
          </p>
          <p className="rc-detail-line">
            <span className="rc-detail-key">Recorded status</span>{' '}
            {side.status ?? 'no status recorded'} · {evidenceWord(side)}
          </p>
          {side.support.length > 0 && (
            <ul className="rc-detail-list">
              {side.support.map((entry, index) => (
                <li key={`${entry.key}#${index}`}>{supportWord(entry)}</li>
              ))}
            </ul>
          )}
          {side.undescribableSupport > 0 && (
            <p className="rc-detail-fail">
              {side.undescribableSupport} of the entries above could not be read by this build.
              They are counted rather than described.
            </p>
          )}
        </>
      ) : (
        /*
          NO VALUE IS NOT THE SAME AS NOTHING RECORDED, and this branch used to say
          it was: it rendered "There is nothing cited here to describe" for EVERY
          side without a value, while `supportOf` reads the envelope's citations
          whether or not it carries one. A draft field with `status:
          needs_confirmation`, no value and two spreadsheet citations is an
          ordinary ISAAC shape — the extractor records what it read and asks — and
          on an `On one run only` row (which is listed by default, and expandable
          because the OTHER side has a value) this panel asserted that the run's
          own stored citations were not there. The sentence is now conditioned on
          the citations it is about, and they are listed when they exist.

          The two provenance dimensions are deliberately still not shown here:
          `provenanceOf` computes them only for a side that holds a value, the
          review AXIS reads `not-applicable` whenever either side is absent, and a
          chip saying what "establishes" a value there is no value for would be a
          claim about nothing.
        */
        <>
          <p className="rc-detail-line">
            {originWord(side.origin)}.{' '}
            {side.support.length === 0
              ? 'There is nothing cited here to describe.'
              : 'No value is recorded, and these entries are cited beside it.'}
          </p>
          {side.support.length > 0 && (
            <>
              <p className="rc-detail-line">
                <span className="rc-detail-key">Recorded status</span>{' '}
                {side.status ?? 'no status recorded'} · {evidenceWord(side)}
              </p>
              <ul className="rc-detail-list">
                {side.support.map((entry, index) => (
                  <li key={`${entry.key}#${index}`}>{supportWord(entry)}</li>
                ))}
              </ul>
            </>
          )}
          {side.undescribableSupport > 0 && (
            <p className="rc-detail-fail">
              {side.undescribableSupport} of the entries above could not be read by this build.
              They are counted rather than described.
            </p>
          )}
        </>
      )}
      {side.conflict !== null && <ConflictDetail conflict={side.conflict} />}
      {findings.length > 0 && (
        <div className="rc-detail-findings">
          <p className="rc-detail-key">
            Reported by the last check of this run, at this address
          </p>
          <ul className="rc-detail-list">
            {findings.map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function ConflictDetail({ conflict }: { conflict: CompareConflict }) {
  return (
    <div className="rc-detail-conflict">
      <p className="rc-detail-key">Recorded conflict on this run</p>
      <p className="rc-detail-line">{conflictWord(conflict)}</p>
      {/* The server's own deterministic sentence, which quotes no value. */}
      <p className="rc-detail-line">{conflict.explanation}</p>
      {conflict.unavailable && (
        <p className="rc-detail-fail">
          Part of the stored evidence at this address could not be read, so what is counted here
          is not everything that is stored.
        </p>
      )}
      {/*
        WHERE IT IS DECIDED, AND WHY NOT HERE. This panel is read-only. Showing the
        competing answers would invite a choice it cannot record, and recording one
        needs the record's own version token.
      */}
      <p className="rc-detail-line">
        The competing answers are not listed here. This panel is read-only; a decision is
        recorded on the record&rsquo;s own conflict surface.
      </p>
    </div>
  );
}

/**
 * ONE RUN'S CELL — the value, where it came from, and what is recorded beside it.
 *
 * THE LINK IS ON DIFFERING ROWS ONLY, and that is a deliberate limit rather than
 * an omission. A difference the reader cannot navigate to is a claim they cannot
 * check, so every difference carries a way to open the run it was read from; an
 * agreeing row has nothing to check, and eighty links to rows nobody disputes is a
 * keyboard path through noise. The link opens Focus Run for that run — where this
 * exact address is rendered, with its provenance, by the card's own panels — and it
 * PRESERVES the comparison in the URL, so leaving focus returns to this table.
 */
function SideCell({
  row,
  side,
  run,
  findings,
}: {
  row: CompareRow;
  side: CompareSide;
  run: ApiRunView;
  findings: string[];
}) {
  const [searchParams] = useSearchParams();
  const search = new URLSearchParams(searchParams);
  search.set(RECORD_RUN_PARAM, run.id);
  /*
   * THE LINK NOW NAMES THE ADDRESS AS WELL AS THE RUN, and the destination uses it.
   *
   * "Open" used to carry `run.id` alone, so a reader following a difference at
   * `sample.material.name` landed on a run card and had to find the address
   * themselves — on a record with many resolved addresses that is the difference
   * between a link and a hint. `RunsSection` reads this parameter, brings the
   * matching `[data-address]` row into view and marks it; it is a scroll target and
   * nothing else, so a stale or unknown address changes nothing on the page.
   */
  search.set(RECORD_ADDRESS_PARAM, row.address);
  return (
    <td className="rc-cell" data-present={side.present}>
      <span className="rc-value">
        {side.text !== null ? (
          side.text
        ) : side.unrenderable ? (
          <span className="rc-value-none">A list or an object — not shown in one line</span>
        ) : (
          <span className="rc-value-none">No value recorded on this run</span>
        )}
      </span>
      <span className="rc-origin" data-origin={side.origin}>
        {side.origin === 'overridden' ? (
          <Pencil size={11} strokeWidth={2.2} aria-hidden="true" />
        ) : side.origin === 'inherited' ? (
          <CornerDownRight size={11} strokeWidth={2.2} aria-hidden="true" />
        ) : side.origin === 'own' ? (
          <Pencil size={11} strokeWidth={2.2} aria-hidden="true" />
        ) : (
          <CircleDashed size={11} strokeWidth={2.2} aria-hidden="true" />
        )}
        {originWord(side.origin)}
      </span>
      {side.present && (
        // COUNTED, NEVER JUDGED. A number of evidence entries says how much is
        // recorded beside a value; it says nothing about whether the value is right.
        <span className="rc-meta">
          {side.status ?? 'no status recorded'} · {evidenceWord(side)}
        </span>
      )}
      {findings.length > 0 && (
        /*
          A FINDING IS ATTACHED ONLY WHERE IT NAMED THIS ADDRESS ITSELF. It is
          reported as what the check said, at this address, on this run — never as
          an explanation of the difference beside it, which nothing here knows.
        */
        <span className="rc-cell-finding">
          {findings.length} finding{findings.length === 1 ? '' : 's'} at this address
        </span>
      )}
      {row.listed && (
        <Link className="rc-open" to={{ search: `?${search.toString()}` }}>
          Open
          <span className="sr-only">
            {' '}
            {run.label} at {row.path}
          </span>
        </Link>
      )}
    </td>
  );
}

/**
 * THE SENTENCE FOR ONE ROW.
 *
 * Every branch is a statement of what the two documents contain. None of them
 * offers a reason, a consequence, or a preference — read the four rules at the top
 * of this file before adding a branch, and read `run-compare.test.tsx`'s
 * vocabulary scan before choosing its words.
 */
function RelationText({
  row,
  runA,
  runB,
}: {
  row: CompareRow;
  runA: ApiRunView;
  runB: ApiRunView;
}) {
  const a = runA.label;
  const b = runB.label;
  switch (row.category) {
    case 'incomparable':
      return (
        <>
          At least one run holds a list or an object at this address. This table shows one line
          per value, so it does not compare them — open each run to read what is there.
        </>
      );
    case 'absent-on-one': {
      const filled = row.a.present ? a : b;
      const emptySide = row.a.present ? row.b : row.a;
      const empty = row.a.present ? b : a;
      return (
        <>
          {/*
            ABSENCE IS NAMED AS ABSENCE. "One holds a value and the other holds a
            different one" and "one holds a value and the other holds none" are
            different facts, and only the first is a disagreement about a value.
          */}
          {filled} records a value here; {empty} records none.{' '}
          {emptySide.origin === 'unresolved'
            ? `This address is not in ${empty}'s resolution at all, which is not the same as ${empty} resolving it and carrying nothing.`
            : 'That is an absence, not a different value.'}
        </>
      );
    }
    case 'value':
      return (
        <>
          {row.sameTextDifferentType ? (
            <>
              Both runs show the same text, and the two values are of different JSON types —{' '}
              {a} holds a {typeof row.a.value}, {b} holds a {typeof row.b.value}.
            </>
          ) : (
            <>The two runs record different values at this address.</>
          )}
          {row.provenance === 'differs' && (
            <>
              {' '}
              They also differ in source: {a} — {originWord(row.a.origin).toLowerCase()}; {b} —{' '}
              {originWord(row.b.origin).toLowerCase()}.
            </>
          )}
          {row.provenance === 'same' && row.a.origin === 'inherited' && (
            <>
              {' '}
              Both runs read this address from the record and no override is recorded on either,
              so the two values reported here came from the same place.
            </>
          )}
        </>
      );
    case 'review':
      return (
        <>
          {/*
            BOTH STATES, NAMED, AND NEITHER RANKED. "Supported" is not a pass and
            "Needs review" is not a failure — `lib/provenance.ts` says so in its own
            words — so this states what each side reads as and stops.
          */}
          Both runs report the same value. What is recorded as establishing it reads
          differently: {a} — {reviewWord(row.a.reviewState).toLowerCase()}; {b} —{' '}
          {reviewWord(row.b.reviewState).toLowerCase()}. Each is read from the citations stored
          on that run, and neither is a schema, completion or export verdict.
        </>
      );
    case 'provenance':
      /*
       * TWO DIFFERENT PROVENANCE DIFFERENCES, AND THEY GET DIFFERENT SENTENCES.
       *
       * The axis now compares the run's INHERITANCE STATE and the ORIGINS its stored
       * citations name. Only one branch below is about inheritance; running both
       * through the inheritance sentence produced "from different places: Run 1 —
       * inherited from record; Run 2 — inherited from record", which names two
       * different places by writing the same words twice.
       */
      if (row.a.origin !== row.b.origin) {
        return (
          <>
            Both runs report the same value, from different places: {a} —{' '}
            {originWord(row.a.origin).toLowerCase()}; {b} —{' '}
            {originWord(row.b.origin).toLowerCase()}. A run that overrides an address keeps its
            own value when the record changes; a run that inherits follows it.
          </>
        );
      }
      return (
        <>
          Both runs report the same value. The citations stored beside it name different
          sources: {a} — {originsWord(row.a).toLowerCase()}; {b} —{' '}
          {originsWord(row.b).toLowerCase()}. Where a value came from is not a statement about
          whether it is backed.
        </>
      );
    case 'evidence':
      return (
        <>
          Same value on both runs. What each run records beside it differs — {a}:{' '}
          {row.a.status ?? 'no status recorded'}, {evidenceWord(row.a)}; {b}:{' '}
          {row.b.status ?? 'no status recorded'}, {evidenceWord(row.b)}.
          {row.a.supportSignature !== row.b.supportSignature
            ? ' The entries cited on each are not the same set — open the row to read them.'
            : ''}{' '}
          This counts and lists entries; it does not weigh them.
        </>
      );
    case 'same':
      if (row.value === 'both-absent') {
        return <>Neither run records a value at this address.</>;
      }
      return (
        <>
          Same value, same source, same status and the same number of evidence entries on both
          runs.
        </>
      );
  }
}

/* ── validation findings ───────────────────────────────────────────────────── */

type CheckState =
  | { status: 'idle' }
  | { status: 'busy' }
  | { status: 'data'; a: ApiRunCheckResponse; b: ApiRunCheckResponse }
  | { status: 'error'; message: string };

/**
 * THE TWO RUNS' VALIDATION FINDINGS, SIDE BY SIDE — and the one comparison this
 * component deliberately does NOT make.
 *
 * It shows which findings are reported for both runs and which for one, because
 * that is what the two responses contain. It does NOT declare a winner, does not
 * say one run is closer to valid, and does not connect a finding on one run to a
 * value difference on another row — every one of those would be an inference this
 * application has no basis for.
 *
 * IT IS OPT-IN, AND THAT IS ABOUT HONESTY AS WELL AS COST. A check is a read of a
 * run against the deterministic validators at a particular version; running it
 * automatically as a side effect of opening a comparison would put a verdict on
 * screen that the reader did not ask for and cannot date. Two requests, on a
 * click, with the version each was computed over stated beside it.
 */
function CompareFindings({
  experimentId,
  runA,
  runB,
  state: check,
  onState: setCheck,
}: {
  experimentId: string;
  runA: ApiRunView;
  runB: ApiRunView;
  /** Held by `RunCompare` beside the pair it describes. See `checkState` there. */
  state: CheckState;
  onState: (next: CheckState) => void;
}) {
  const headingId = useId();

  const run = () => {
    setCheck({ status: 'busy' });
    Promise.all([api.checkRun(experimentId, runA.id), api.checkRun(experimentId, runB.id)])
      .then(([a, b]) => setCheck({ status: 'data', a, b }))
      .catch((err: unknown) =>
        setCheck({
          status: 'error',
          message: err instanceof Error ? err.message : 'The checks could not be run.',
        }),
      );
  };

  return (
    <section className="rc-findings" aria-labelledby={headingId}>
      <h4 className="rc-findings-title" id={headingId}>
        Validation findings
      </h4>
      {check.status === 'idle' && (
        <p className="rc-note">
          Each run can be read against the deterministic validators. The two checks are separate
          reads of two runs; this panel lists what each one reported and which findings both
          reported. Nothing is written, submitted or exported.
        </p>
      )}
      {check.status === 'error' && (
        <p className="rc-note" role="alert">
          {check.message} Neither run was changed.
        </p>
      )}
      {check.status !== 'data' && (
        <button
          type="button"
          className="btn btn-secondary"
          onClick={run}
          disabled={check.status === 'busy'}
        >
          {check.status === 'busy' ? 'Checking both runs…' : 'Check both runs'}
        </button>
      )}
      {check.status === 'data' && (
        <FindingsResult a={check.a} b={check.b} labelA={runA.label} labelB={runB.label} />
      )}
    </section>
  );
}

/** Every finding of one check, as text, with undescribable ones kept and counted. */
function findingTexts(res: ApiRunCheckResponse): { described: string[]; opaque: number } {
  const all = [...(res.blockers ?? []), ...(res.draft?.errors ?? []), ...(res.official?.errors ?? [])];
  const described: string[] = [];
  let opaque = 0;
  for (const finding of all) {
    const text = runFindingText(finding);
    // A finding this build cannot describe is COUNTED, never dropped — the same
    // rule the run card applies, and for the same reason: the number of things
    // standing between a run and a valid record must not quietly shrink.
    if (text === null) opaque += 1;
    else described.push(text);
  }
  return { described, opaque };
}

function FindingsResult({
  a,
  b,
  labelA,
  labelB,
}: {
  a: ApiRunCheckResponse;
  b: ApiRunCheckResponse;
  labelA: string;
  labelB: string;
}) {
  const fa = findingTexts(a);
  const fb = findingTexts(b);
  const unattached = findingsByPath({ a, b }).unattached;
  const setB = new Set(fb.described);
  const setA = new Set(fa.described);
  const both = [...new Set(fa.described.filter((text) => setB.has(text)))].sort();
  const onlyA = [...new Set(fa.described.filter((text) => !setB.has(text)))].sort();
  const onlyB = [...new Set(fb.described.filter((text) => !setA.has(text)))].sort();

  return (
    <>
      <div className="rc-verdicts">
        <Verdict res={a} label={labelA} />
        <Verdict res={b} label={labelB} />
      </div>
      {/*
        THE ONE SENTENCE THAT KEEPS THIS PANEL HONEST, AND IT IS NOW NARROWER
        BECAUSE THE BEHAVIOUR IS.

        It used to end "no finding below is connected to any row in the table
        above", which was true and is no longer: a finding that carries its own
        `path` is shown on the row whose address that path IS. Leaving the sentence
        standing would have made the panel deny something the table does one
        element away — the kind of stale claim this repository has shipped before.

        What is unchanged is everything that mattered about it. Two verdicts side by
        side read as a scoreboard unless they are told not to; each check is a read
        of ONE run at ONE version; and an attachment is an address match, never a
        claim that the finding explains a difference.

        AND THE REPLACEMENT IS NARROWER AGAIN, because the first version of it was
        not true either. It said a finding naming an official path "is also shown on
        that row above" — unconditionally — while the table's rows are only the
        addresses the two runs RESOLVE. An official-schema error naming a path
        neither run resolves reaches no row at all, and the sentence promised a
        reader they would find it there. The clause is now conditioned on the table
        listing the address, which is something the reader can check on the screen
        in front of them.
      */}
      <p className="rc-note">
        Each verdict is a read of one run at the version named beside it. Neither check examined
        the other run. A finding that names an official path is also shown on that row above,
        wherever this table lists that address — that is an address match and nothing more; no
        finding here is offered as the reason two runs differ. {unattached}{' '}
        finding{unattached === 1 ? '' : 's'} name no address and appear only in this panel.
      </p>
      <FindingGroup title={`Reported for both runs`} findings={both} />
      <FindingGroup title={`Reported for ${labelA} only`} findings={onlyA} />
      <FindingGroup title={`Reported for ${labelB} only`} findings={onlyB} />
      {(fa.opaque > 0 || fb.opaque > 0) && (
        <p className="rc-note">
          {fa.opaque + fb.opaque} finding{fa.opaque + fb.opaque === 1 ? '' : 's'} could not be
          described by this build ({labelA}: {fa.opaque}; {labelB}: {fb.opaque}) and{' '}
          {fa.opaque + fb.opaque === 1 ? 'is' : 'are'} not matched between the two runs.
        </p>
      )}
      {both.length === 0 && onlyA.length === 0 && onlyB.length === 0 && (
        <p className="rc-note">
          Neither check reported a finding this build can describe.
        </p>
      )}
    </>
  );
}

function Verdict({ res, label }: { res: ApiRunCheckResponse; label: string }) {
  const unavailable = res.official?.unavailable === true;
  return (
    <p className="rc-verdict">
      <span className="rc-verdict-label">{label}</span>
      {res.ok ? (
        <StatusChip kind="pass" label="Check Passed" />
      ) : unavailable ? (
        <StatusChip kind="needsYou" label="Could Not Be Checked" />
      ) : (
        <StatusChip kind="fail" label="Check Failed" />
      )}
      <span className="rc-verdict-scope">
        Read-only check of run version {res.checked_run_version}. Nothing was written, submitted
        or exported.
      </span>
    </p>
  );
}

function FindingGroup({ title, findings }: { title: string; findings: string[] }) {
  if (findings.length === 0) return null;
  return (
    <div className="rc-finding-group">
      <p className="rc-finding-title">
        {title} · {findings.length}
      </p>
      <ul className="rc-finding-list">
        {findings.map((text) => (
          <li key={text}>{text}</li>
        ))}
      </ul>
    </div>
  );
}

/* ── the announcement ──────────────────────────────────────────────────────── */

/**
 * WHAT THE LIVE REGION SAYS. One utterance per selection change, and it names the
 * runs rather than saying "selection changed" — a reader who cannot see the panel
 * needs to know WHICH two runs are being compared and how many addresses differ,
 * which is precisely the information the visual summary carries.
 */
function announce({
  hidden,
  selected,
  states,
  comparison,
  showAgreeing,
}: {
  hidden: boolean;
  selected: readonly string[];
  states: readonly SideState[];
  comparison: RunComparison | null;
  showAgreeing: boolean;
}): string {
  if (hidden || selected.length === 0) return '';
  const nameOf = (i: number) => {
    const state = states[i];
    return state?.status === 'run' ? state.run.label : selected[i];
  };
  if (selected.length === 1) {
    return `${nameOf(0)} selected for comparison. Choose one more run to compare.`;
  }
  const missing = states
    .map((state, i) => ({ state, i }))
    .filter((entry) => entry.state.status === 'missing');
  if (missing.length > 0) {
    return `No run with the id ${missing.map((entry) => selected[entry.i]).join(' or ')} is in this record.`;
  }
  if (comparison === null) return 'Loading two runs to compare.';
  const { tally } = comparison;
  return (
    `Comparing ${nameOf(0)} and ${nameOf(1)}. ` +
    // The same three numbers the summary shows, and the same refusal to let them
    // be two: an address this table could not read is not an address that differs.
    `${tally.differing} of ${tally.compared} addresses differ; ${tally.agreeing} are the same` +
    (tally.incomparable > 0 ? `; ${tally.incomparable} could not be compared. ` : '. ') +
    // A RECORDED CONFLICT IS SPOKEN SEPARATELY, for the reason it is COUNTED
    // separately: it is not one of the differences, and a reader who cannot see
    // the panel must not be told a number that quietly includes it.
    (tally.conflicted > 0
      ? `${tally.conflicted} of them carry a conflict recorded against one run's own citations. `
      : '') +
    (showAgreeing
      ? 'All compared addresses are listed.'
      : tally.conflicted > 0
        ? 'Only the addresses that differ, and the ones carrying a recorded conflict, are listed.'
        : 'Only the addresses that differ are listed.')
  );
}
