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
 * from cards the reader just clicked costs ZERO requests. Only a deep link — where
 * the ids arrive before any run does — costs anything, and it costs exactly one
 * `getRun` per run that is not on the loaded page, never a list read. The
 * resolution deliberately WAITS for the first page rather than racing it: firing
 * two reads for runs that are already in flight is two requests to learn what was
 * about to arrive, and the page read is already on its way.
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
import { RECORD_RUN_PARAM, RUN_COMPARE_MAX } from '../lib/routes';
import {
  buildRunComparison,
  categoryWord,
  evidenceWord,
  originWord,
  type CompareCategory,
  type CompareRow,
  type CompareSide,
  type RunComparison,
} from '../lib/runCompare';
import { runFindingText } from '../lib/runFields';
import {
  ArrowLeftRight,
  CircleDashed,
  CircleHelp,
  CornerDownRight,
  Columns2,
  Equal,
  Pencil,
  type LucideIcon,
} from './icons';
import { LoadingPanel } from './FetchStates';
import { StatusChip } from './StatusChip';
import type { ApiRunCheckResponse, ApiRunView } from '../lib/types';

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
  provenance: CornerDownRight,
  evidence: Pencil,
  incomparable: CircleHelp,
};

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

  const comparison = useMemo(
    () => (runA !== undefined && runB !== undefined ? buildRunComparison(runA, runB) : null),
    [runA, runB],
  );

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
              />
              {comparison.blocks.length > 0 && (
                /*
                  THE SAME BOUNDARY `overrideRows` DRAWS, disclosed rather than
                  denied. A block payload is an object or a list; this table has no
                  honest one-line rendering for one, so it is named and not compared.
                */
                <p className="rc-note">
                  {comparison.blocks.length} whole-block address
                  {comparison.blocks.length === 1 ? '' : 'es'} resolved by these runs{' '}
                  {comparison.blocks.length === 1 ? 'is' : 'are'} not compared here —{' '}
                  <span className="mono">{comparison.blocks.join(', ')}</span>. A block is an
                  object or a list, and this table has no one-line rendering for one.
                </p>
              )}
              <CompareFindings experimentId={experimentId} runA={runA!} runB={runB!} />
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
      {tally.differing === 0 && (
        /*
          THE DENOMINATOR IS `agreeing`, NOT `compared`. It used to be `compared`,
          which silently included the addresses this table could not read — so a
          pair of runs with one unreadable address was described as agreeing "at
          every one of the 10 addresses compared here" when only 9 had been.
        */
        <p className="rc-summary-line">
          These two runs record the same value, from the same source, with the same status and
          the same number of evidence entries, at every one of the {tally.agreeing} address
          {tally.agreeing === 1 ? '' : 'es'} this table was able to compare.
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

function CompareTable({
  comparison,
  runA,
  runB,
  showAgreeing,
}: {
  comparison: RunComparison;
  runA: ApiRunView;
  runB: ApiRunView;
  showAgreeing: boolean;
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
            : `Addresses where ${runA.label} and ${runB.label} differ${comparison.tally.incomparable > 0 ? `, and ${comparison.tally.incomparable} this table could not compare` : ''}. ${comparison.tally.agreeing} further address${comparison.tally.agreeing === 1 ? ' is' : 'es are'} the same on both runs and ${comparison.tally.agreeing === 1 ? 'is' : 'are'} not listed.`}
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
              <Row key={row.key} row={row} runA={runA} runB={runB} />
            ))}
          </tbody>
        ))}
      </table>
    </div>
  );
}

function Row({ row, runA, runB }: { row: CompareRow; runA: ApiRunView; runB: ApiRunView }) {
  const Glyph = CATEGORY_ICON[row.category];
  return (
    <tr className="rc-row" data-category={row.category} data-address={row.address}>
      <th scope="row" className="rc-addr">
        <span className="rc-addr-path mono">{row.path}</span>
        <span className="rc-addr-scope">
          {row.scope === 'run-field' ? "the run's own field" : 'record-level address'}
        </span>
      </th>
      <SideCell row={row} side={row.a} run={runA} />
      <SideCell row={row} side={row.b} run={runB} />
      <td className="rc-rel">
        <span className="rc-rel-state" data-category={row.category}>
          <Glyph size={13} strokeWidth={2.2} aria-hidden="true" />
          {categoryWord(row.category)}
        </span>
        <span className="rc-rel-text">
          <RelationText row={row} runA={runA} runB={runB} />
        </span>
      </td>
    </tr>
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
function SideCell({ row, side, run }: { row: CompareRow; side: CompareSide; run: ApiRunView }) {
  const [searchParams] = useSearchParams();
  const search = new URLSearchParams(searchParams);
  search.set(RECORD_RUN_PARAM, run.id);
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
    case 'provenance':
      return (
        <>
          Both runs report the same value, from different places: {a} —{' '}
          {originWord(row.a.origin).toLowerCase()}; {b} — {originWord(row.b.origin).toLowerCase()}.
          A run that overrides an address keeps its own value when the record changes; a run that
          inherits follows it.
        </>
      );
    case 'evidence':
      return (
        <>
          Same value on both runs. What each run records beside it differs — {a}:{' '}
          {row.a.status ?? 'no status recorded'}, {evidenceWord(row.a)}; {b}:{' '}
          {row.b.status ?? 'no status recorded'}, {evidenceWord(row.b)}. This counts entries; it
          does not weigh them.
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
}: {
  experimentId: string;
  runA: ApiRunView;
  runB: ApiRunView;
}) {
  const [check, setCheck] = useState<CheckState>({ status: 'idle' });
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
        THE ONE SENTENCE THAT KEEPS THIS PANEL HONEST. Two verdicts side by side
        read as a scoreboard unless they are told not to. Each check is a read of
        ONE run at ONE version; neither says anything about the other run, and
        nothing here relates a finding to a difference in the table above.
      */}
      <p className="rc-note">
        Each verdict is a read of one run at the version named beside it. Neither check examined
        the other run, and no finding below is connected to any row in the table above.
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
    (showAgreeing
      ? 'All compared addresses are listed.'
      : 'Only the addresses that differ are listed.')
  );
}
