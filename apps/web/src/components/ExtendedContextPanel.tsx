/*
 * EXTENDED CONTEXT — the `DEC-41` level-4 companion, made inspectable. `CTX-004`.
 *
 * ── WHAT THIS PANEL IS FOR ──────────────────────────────────────────────────
 *
 * The official ISAAC v1.05 record is an interoperable baseline, not a ceiling. When
 * an import reads something scientifically useful that the schema has no field for,
 * `DEC-41` says it lands at level 4: a structured, provenance-backed companion,
 * `records/<ULID>.context.json`, in the same architectural class as the evidence
 * sidecar. Each entry keeps four things — the concept, the source's own words, which
 * source, and where in it — and all four are required at construction, so an entry
 * that cannot say where it came from cannot exist.
 *
 * ── THE MEASURED GAP THIS CLOSES ────────────────────────────────────────────
 *
 * The companion was durable, was written to an export artifact, and was served on
 * the wire — and reached no scientist. Measured at `938e4829`:
 * `rg --text --files-with-matches "extended_context|extendedContext" apps/web/src/`
 * returned NOTHING, and `ApiArtifactsResponse` declared neither of the two keys
 * `GET .../artifacts` serves. So the only way to read it was developer-side JSON.
 *
 * Worse, and this is why the panel reads its own route rather than `bundle.artifacts`:
 * `get_artifacts` serves the companion only once a record has been EXPORTED. A record
 * that had imported extended context and had not yet exported had no read surface for
 * it at all. `GET .../extended-context` answers from the record's own durable state,
 * so it works from the moment the companion is written — which is exactly when a
 * scientist reviewing a fresh import wants to look.
 *
 * ── WHY IT LIVES IN THE FIELDS WORKSPACE ────────────────────────────────────
 *
 * Extended context is defined by what it is NOT: the information the record's fields
 * have no home for. That makes it legible only BESIDE those fields. A reader in
 * `Record Fields` is asking "what does this record say about the experiment?", and
 * the level-4 companion is the rest of that answer — the part the schema could not
 * take. Read in any other workspace it is a list of literals with nothing to be the
 * remainder of.
 *
 * The three workspaces it is NOT in, each for a positive reason rather than by
 * elimination:
 *
 *   * `capture` holds material AWAITING JUDGEMENT — notes and open proposals a
 *     scientist accepts, rejects or defers. A companion entry awaits nothing. It is
 *     append-only (`add_extended_context_entries` is the only writer; there is no
 *     remove and no replace), so putting it there would imply a triage that has no
 *     control and can never be finished.
 *   * `activity` is a history of ACTS. These are content, not acts.
 *   * `runs` would strand the experiment-scoped entries. The PRODUCER emits every
 *     entry experiment-scoped, because no run exists at read time.
 *
 *     ~~"which is most of them"~~ -- WITHDRAWN as unmeasured, and it was wrong in a
 *     direction worth recording: the APPLY path rebinds run scope
 *     (`routes.py:26069-26074`, pre-existing) for every entry whose `source` matches
 *     a unit's `acquisition_path`, so on a real BL15 import a large share becomes
 *     run-scoped. The conclusion never depended on the proportion -- ONE stranded
 *     experiment-scoped entry is enough, and a beamtime-wide reading is precisely the
 *     kind that has no run to be strung from -- so the quantifier bought nothing and
 *     asserted something nobody had counted.
 *
 * AND IT IS NOT A SIXTH WORKSPACE. `RECORD_VIEW_IDS` is five and `DEC-51` settles
 * that Activity-class surfaces live inside the Experiment with the global nav at
 * four items. A destination is for a task a reader comes to the screen to do; this
 * is reference material about the record they are already reading, which is the same
 * argument `RecordWorkbench` records for the `record-identity` group it sits above.
 *
 * ── WHERE IN THAT WORKSPACE, AND WHY ────────────────────────────────────────
 *
 * Immediately AFTER the draft blocks and BEFORE the `Record Identity` eyebrow. That
 * eyebrow marks where the science stops and reference material about the whole record
 * begins; extended context is science, so it belongs on the science side of it. The
 * reading order is then exactly `DEC-41`'s hierarchy: the fields the schema has, then
 * the scientifically useful statements it has no field for.
 *
 * It is deliberately NOT above the draft blocks. `RecordWorkbench` records that four
 * existing specs address "the first `.fg-header` on the screen" as the way to reach
 * the first DRAFT block; mounting anything above them would silently re-point that
 * selector at a section those specs know nothing about.
 *
 * ── FOUR THINGS THIS PANEL WILL NOT DO ──────────────────────────────────────
 *
 *   1. IT NEVER SAYS OR IMPLIES THAT AN ENTRY IS AN OFFICIAL FIELD VALUE. It does not
 *      render `official_path` as a field the entry fills — that key points at the
 *      REGISTRY's home for the concept, and an entry at level 4 is precisely one whose
 *      information is not there. It shows no validity, no pass/fail, no completion, and
 *      it carries the server's own `not_official` sentence verbatim rather than a
 *      paraphrase of it.
 *   2. IT NEVER INTERPRETS A LITERAL. No unit conversion, no rounding, no parsing, no
 *      classification, no "did you mean". `raw_literal` is rendered as it arrived
 *      (`CLAUDE.md` §5). `normalized_value` is shown ONLY when the server sent one, and
 *      always beside the named rule that produced it, because an unexplained
 *      normalisation is indistinguishable from a guess.
 *   3. IT NEVER SHOWS A VALUE WITHOUT ITS PROVENANCE. `source` and `locator` are on
 *      every card, never behind the disclosure. A literal stripped of where it came
 *      from is the prose dump `DEC-41` exists to prevent.
 *   4. IT NEVER REPORTS THE PAGE AS THE RECORD. Every count comes from the server's
 *      `total`/`matched`/`unreadable_entries`, never from `entries.length` — the rule
 *      `CLAUDE.md` §11's 2026-09-02 entry states, and the one that is easiest to break
 *      by accident on a paged list.
 *
 * ── THE RAW ENTRY IS UNDER DISCLOSURE, NOT THE DEFAULT ──────────────────────
 *
 * A native `<details>` per card, the repo idiom (`HelpPanel`, `AssistantPanel`,
 * `SchemaBrowser`, `ActivityHistoryPanel`'s actor note). Raw JSON as a scientist's
 * primary view is a defect that was just fixed on the Activity panel and must not come
 * back here. The default reading is the concept, the literal, and where it came from.
 *
 * ── THE EMPTY STATE IS THE COMMON CASE AND MUST NOT READ AS AN ERROR ────────
 *
 * Extended context arrives through historical import and through nothing else in this
 * build, so almost every record has none. `routes.get_artifacts` already refuses to
 * fold the companion into its `stale` decision for exactly this reason — folding it in
 * "would make every record without extended context report a missing artifact". This
 * panel carries that reasoning to the screen: `present: false` renders a sentence
 * stating a fact about the record, with no remedy, no absence-of-file, and no action.
 */
import { useCallback, useEffect, useId, useRef, useState } from 'react';

import { api, ApiError } from '../lib/api';
import { LABELS } from '../lib/labels';
import type { ApiExtendedContextEntry, ApiExtendedContextResponse } from '../lib/types';
import { BackendDown, LoadingPanel } from './FetchStates';
import { ChevronDown, ChevronRight } from './icons';
import { HelpTip } from './HelpTip';
// The collapsed mount reuses `FieldGroup`'s shell (`.field-group` / `.fg-header` /
// `.fg-body`), as `AssetReferencesPanel` does, rather than inventing a second
// disclosure idiom for this one workspace.
import './fields.css';
import './extendedContext.css';

/** Same narrowing the other panels use — a non-`ApiError` throw still renders a panel. */
function asApiError(err: unknown): ApiError {
  return err instanceof ApiError
    ? err
    : new ApiError(err instanceof Error ? err.message : String(err));
}

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; error: ApiError }
  | {
      status: 'data';
      /**
       * The MOST RECENT page's envelope. Every server-owned count on screen is read
       * from here — `total`, `matched`, `unreadable_entries`, `has_more`, `present`.
       */
      loaded: ApiExtendedContextResponse;
      /**
       * Every entry fetched so far, in stored order, ACROSS pages.
       *
       * Held separately from `loaded.entries` because `loaded` is one page and this is
       * what the reader can see. Which of the two a given count comes from is the whole
       * of `CTX-004`'s paging correctness — see `shownLine`.
       */
      shown: ApiExtendedContextEntry[];
      /** A "Show more" is in flight. The list stays rendered while it is. */
      appending: boolean;
      /**
       * A "Show more" that FAILED. Disclosed beside the list and NEVER allowed to
       * replace it — `CLAUDE.md` §11's 2026-09-10 rule, which this repository learned
       * by destroying a scientist's typed text with a failed background reload. The
       * entries already on screen are the reader's, and a failed request for MORE of
       * them is no reason to take them away.
       */
      appendError: ApiError | null;
    };

/**
 * How many entries one request asks for.
 *
 * DERIVED FROM THE SERVER'S OWN WINDOW rather than chosen here: this asks for
 * `limit` entries and the server's default page is what it would have returned
 * anyway, so a page boundary on the screen is a page boundary on the wire. Sending
 * no `limit` at all would work identically for the FIRST read and would then give
 * this component no way to ask for the second page's size, so the number is stated
 * once and used for every request. It is deliberately not larger than the server's
 * default: a client that asked for more than the server volunteers would be choosing
 * a bound the server has an argument for and the client does not.
 */
const PAGE = 50;

/** `unknown` -> something renderable, without asserting a shape it may not have. */
function renderScalar(value: unknown): string {
  if (typeof value === 'string') return value;
  return JSON.stringify(value) ?? String(value);
}

/**
 * ONE ENTRY. Concept, literal, provenance — then everything else under disclosure.
 *
 * The pairs rendered outside the disclosure are exactly `DEC-41`'s four required
 * ones plus a normalisation WHEN AND ONLY WHEN the server sent one with its rule.
 * Everything optional is inside, because a card that renders eight `null`s is a card
 * nobody reads, and the four that are always there are the four that make the entry
 * auditable.
 */
function EntryCard({ entry }: { entry: ApiExtendedContextEntry }) {
  const scopeLine =
    entry.scope === 'run' && entry.run_id !== null
      ? `On run ${entry.run_id}`
      : 'On the record';
  /* `normalized_value` is shown ONLY WITH ITS RULE, and the condition is an AND for
     a reason rather than for tidiness: the server requires `normalization_rule`
     whenever `determinism` is not `read`, so a value arriving without one would mean
     something unexpected happened upstream — and rendering a cleaned reading whose
     derivation nobody can name is the guess §5 forbids. Better to show the literal
     alone, which is never wrong. */
  const showNormalized =
    entry.normalized_value !== null &&
    entry.normalized_value !== undefined &&
    entry.normalization_rule !== null;

  return (
    <li className="extctx-entry">
      <span className="extctx-concept">{entry.concept}</span>
      {/* THE SOURCE'S OWN WORDS. Never parsed, never converted, never shortened. */}
      <span className="extctx-literal">{entry.raw_literal}</span>
      <dl className="extctx-provenance">
        <div className="extctx-provenance-pair">
          <dt>Source</dt>
          <dd>{entry.source}</dd>
        </div>
        <div className="extctx-provenance-pair">
          <dt>Where in it</dt>
          <dd>{entry.locator}</dd>
        </div>
        <div className="extctx-provenance-pair">
          <dt>Scope</dt>
          <dd>{scopeLine}</dd>
        </div>
        {showNormalized && (
          <div className="extctx-provenance-pair">
            {/* THE RULE IS IN THE LABEL, not a footnote, so a cleaned reading can
                never appear without the name of what cleaned it. */}
            <dt>Read by {entry.normalization_rule} as</dt>
            <dd>
              {renderScalar(entry.normalized_value)}
              {entry.unit === null ? '' : ` ${entry.unit}`}
            </dd>
          </div>
        )}
      </dl>
      {entry.reason !== '' && <p className="extctx-lead">{entry.reason}</p>}
      <details className="extctx-details">
        <summary className="extctx-summary">Everything this entry records</summary>
        {/* THE RAW ENTRY, VERBATIM AND COMPLETE — including the keys that are null,
            because the server sends them deliberately: omitting one would make "this
            reader looked and found no unit" indistinguishable from "this reader does
            not report units". This is an audit view, and it is under a disclosure so
            that it is never the scientist's primary reading. */}
        <pre className="extctx-raw">{JSON.stringify(entry, null, 2)}</pre>
      </details>
    </li>
  );
}

/**
 * `collapsedByDefault` is the only mount today, and the prop exists so a test (or a
 * later surface) can render the panel open without this file growing a second shape.
 * `AssetReferencesPanel` carries the same prop with the opposite default, for the
 * same reason its note gives: the workspace's footer should be one line, not a
 * browser, and the cost of a reader being wrong about that is one click.
 */
export function ExtendedContextPanel({
  experimentId,
  collapsedByDefault = true,
}: {
  experimentId: string;
  collapsedByDefault?: boolean;
}) {
  const [expanded, setExpanded] = useState(!collapsedByDefault);
  const [state, setState] = useState<LoadState>({ status: 'loading' });
  const bodyId = useId();
  /* Keyed against the record so a stale response from the PREVIOUS record can never
     land in this one's state. `AssetReferencesPanel` solves the same hazard with a
     `key` at the call site; this panel is mounted once per workspace and hidden
     rather than unmounted on a workspace switch, so it guards the id itself.

     IT ALSO GUARDS THE OFFSET, which is why the token carries it: a "Show more" and
     a record switch can be in flight together, and a page-2 response must not be
     appended to a different record's page 1. */
  const requested = useRef(`${experimentId}::0`);

  /**
   * THE FIRST PAGE. Replaces everything — this is the read a reader ASKED for, so it
   * is allowed to show a spinner and to replace what is on screen.
   */
  const load = useCallback(() => {
    const token = `${experimentId}::0`;
    requested.current = token;
    setState({ status: 'loading' });
    api
      .getExtendedContext(experimentId, { limit: PAGE, offset: 0 })
      .then((loaded) => {
        if (requested.current !== token) return;
        setState({
          status: 'data',
          loaded,
          shown: loaded.entries,
          appending: false,
          appendError: null,
        });
      })
      .catch((err: unknown) => {
        if (requested.current !== token) return;
        setState({ status: 'error', error: asApiError(err) });
      });
  }, [experimentId]);

  useEffect(load, [load]);

  /**
   * THE NEXT PAGE, BY `offset` — AND THIS IS THE `CTX-004` PAGING FIX.
   *
   * ── THE DEFECT THIS REPLACES, MEASURED ──────────────────────────────────────
   *
   * The first version paged by GROWING `limit` and never sent `offset` at all. The
   * server clamps `limit` at `EXTENDED_CONTEXT_LIMIT_MAX = 200` and computes
   * `has_more` from `matched`, so on a record holding 300 entries — well inside the
   * 1,000-per-import ceiling — every click past the third re-fetched the SAME first
   * 200 rows and left the button on screen forever. Measured over HTTP:
   *
   *     ask limit=200  -> limit=200 returned=200 has_more=true  highest=e0199
   *     ask limit=250  -> limit=200 returned=200 has_more=true  highest=e0199
   *     ask limit=1000 -> limit=200 returned=200 has_more=true  highest=e0199
   *
   * Highest entry index ever rendered: 199 of 299. So 100 of 300 entries were
   * unreachable from the website, behind a permanently dead control — while
   * `isaac_get_extended_context`'s own description tells an AGENT to "page with
   * `offset`", and an agent could read all of them. A scientist having strictly less
   * access to their own record than a language model is the wrong way round.
   *
   * It is also, exactly, the defect class the commit before this branch's base is
   * named for: `d308b827`, "the count named 150 facts a reader could not reach".
   *
   * ── THE FIX, AND WHY IT IS `shown.length` RATHER THAN A PAGE COUNTER ────────
   *
   * `offset` is the number of entries already held, read off the accumulated list
   * rather than from a separately-incremented counter. A counter is a second
   * expression of the same quantity and would be free to disagree with the array the
   * moment any response returned fewer rows than it asked for — which is the normal
   * last page. Derived, it cannot.
   *
   * `offset` paging is SOUND here for a structural reason rather than a hopeful one:
   * the companion is append-only (`add_extended_context_entries` is the only writer;
   * there is no remove and no replace), so an arrival lands AFTER every offset
   * already read and shifts none of them.
   *
   * ── IT IS NOT DESTRUCTIVE, AND THAT IS THE OTHER HALF ───────────────────────
   *
   * The list stays rendered while the request is in flight and stays rendered if it
   * FAILS. `CLAUDE.md` §11 records this repository destroying a scientist's typed
   * text with exactly the naive shape (`setState({status:'error'})` on a background
   * read), and the remedy both sibling panels now carry is the one here: a failure
   * that arrives while something is on screen is disclosed BESIDE it, never in place
   * of it.
   */
  const loadMore = useCallback(() => {
    if (state.status !== 'data' || state.appending) return;
    const offset = state.shown.length;
    const token = `${experimentId}::${offset}`;
    requested.current = token;
    setState({ ...state, appending: true, appendError: null });
    api
      .getExtendedContext(experimentId, { limit: PAGE, offset })
      .then((next) => {
        if (requested.current !== token) return;
        setState((prev) =>
          prev.status !== 'data'
            ? prev
            : {
                status: 'data',
                loaded: next,
                shown: [...prev.shown, ...next.entries],
                appending: false,
                appendError: null,
              },
        );
      })
      .catch((err: unknown) => {
        if (requested.current !== token) return;
        setState((prev) =>
          prev.status !== 'data'
            ? prev
            : { ...prev, appending: false, appendError: asApiError(err) },
        );
      });
  }, [experimentId, state]);

  /* THE COUNT ON THE HEADER IS THE SERVER'S `total`, NEVER `entries.length`, and it
     is `null` until the read answers. A collapsed header with no count is the honest
     state of a list nobody has finished reading; a `0` this panel has not established
     would be a claim about the record. */
  const total = state.status === 'data' ? state.loaded.total : null;

  const Chevron = expanded ? ChevronDown : ChevronRight;
  return (
    <section
      className="field-group extctx-collapsible"
      aria-label={LABELS.extendedContextHeading}
    >
      {/* `h2 > button[aria-expanded][aria-controls]`, the accordion shape `RunCard`
          documents and `AssetReferencesPanel` follows — a real heading landmark, not
          a div with an onClick. `h2` because the sections around it in this workspace
          are `h2`s and this is their peer. */}
      <h2 className="fg-heading">
        <button
          type="button"
          className="fg-header"
          aria-expanded={expanded}
          aria-controls={bodyId}
          onClick={() => setExpanded((v) => !v)}
        >
          <Chevron className="fg-chevron" size={16} strokeWidth={2} aria-hidden="true" />
          <span className="fg-block">{LABELS.extendedContextHeading}</span>
          <span className="fg-summary">
            {total === null
              ? ''
              : `${total} ${total === 1 ? 'entry' : 'entries'}`}
          </span>
        </button>
      </h2>
      <div id={bodyId} className="fg-body extctx-body" hidden={!expanded}>
        {state.status === 'loading' && <LoadingPanel label="Reading extended context…" />}
        {state.status === 'error' && <BackendDown error={state.error} onRetry={load} />}
        {state.status === 'data' && (
          <Loaded
            loaded={state.loaded}
            shown={state.shown}
            appending={state.appending}
            appendError={state.appendError}
            onMore={loadMore}
          />
        )}
      </div>
    </section>
  );
}

function Loaded({
  loaded,
  shown,
  appending,
  appendError,
  onMore,
}: {
  /** The MOST RECENT page. Every server-owned count is read from here. */
  loaded: ApiExtendedContextResponse;
  /** Every entry fetched so far, across pages. What the reader can actually see. */
  shown: ApiExtendedContextEntry[];
  appending: boolean;
  appendError: ApiError | null;
  onMore: () => void;
}) {
  /*
   * -- THREE EMPTY STATES, NOT TWO -- `CTX-004`, corrected after review ---------
   *
   * The first version had two, and the missing third made the panel say the opposite
   * of the truth in the one surface built to disclose loss. Each of these is a
   * different fact and a reader acts on them differently:
   *
   *  1. `present: false` -- NO companion document. The ordinary case, since extended
   *     context arrives through historical import and nothing else in this build.
   *  2. `present: true`, no readable entries, `unreadable_entries > 0` -- a companion
   *     that holds rows this build cannot read. They are preserved in the record and
   *     counted; nothing is invented about what they say.
   *  3. `present: true`, no readable entries, `unreadable_entries === 0` -- a
   *     companion document that ACCOUNTS FOR NOTHING. This is the case that was
   *     missing.
   *
   * -- WHAT CASE 3 USED TO SAY, AND WHY IT WAS TWO LIES IN ONE SENTENCE ---------
   *
   * It read: *"This record holds an extended context companion with no entry this
   * build can present. Nothing has been discarded - see the count above."*
   *
   *  * **"Nothing has been discarded" is not something this panel can know.**
   *    `extended_context.hydrate` returns an empty-but-present companion for a
   *    persisted document whose `entries` is not a list, and for one whose `entries`
   *    is an empty list -- and in the first of those the stored content really was
   *    dropped, with no count recording it. Asserting no loss there is false; the
   *    honest position is that this build cannot say either way.
   *  * **"see the count above" pointed at a line that is not on screen.** It meant
   *    the `unreadable_entries` row, which is gated on `> 0` and therefore absent in
   *    precisely this case. The only count above reads `0 entries on this record`.
   *
   * So case 3 now states the observable facts, names what it cannot determine, and
   * directs the reader at the artifact itself rather than at an absent number.
   * Nothing is reconstructed from the document, which is the S5 position and also the
   * only one available: the content is gone or was never there, and those look
   * identical from here.
   */
  if (!loaded.present) {
    /* ONE LINE, AND THE EXPLANATION ONE `?` AWAY (owner QA F3, 2026-09-22). The
       full sentence used to be the whole empty state, three lines flush against the
       card edge. It is still rendered — verbatim, inside the tip — because it is
       what stops an empty panel reading as a missing file. */
    return (
      <p className="extctx-empty">
        {LABELS.extendedContextEmptyShort}{' '}
        <HelpTip subject={LABELS.extendedContextHeading} label="Why This Is Empty">
          <span>{LABELS.extendedContextEmpty}</span>
        </HelpTip>
      </p>
    );
  }

  /*
   * HOW MANY ARE ON SCREEN -- read from `shown`, and this is a DELIBERATE INVERSION
   * of the rule three lines down, not an exception to it.
   *
   * The rule is that no count describing the RECORD may come from an array; `total`,
   * `matched` and `unreadable_entries` are therefore always the server's. But "how
   * many can I see right now" is a fact ABOUT the array and about nothing else, and
   * once pages accumulate the server's `returned` describes only the LAST page -- so
   * using it here would have under-reported the screen by every page but one. The
   * two halves of `N of M shown` come from two different places on purpose.
   */
  const shownCount = shown.length;

  return (
    <>
      {/* THE SERVER'S OWN SENTENCE, VERBATIM. Not paraphrased and not shortened: it
          is the artifact's definition of itself, and every softening of it is a step
          toward a reader treating a level-4 literal as a field value. */}
      <p className="extctx-not-official">{loaded.not_official}</p>

      <ul className="extctx-counts">
        {/* EVERY NUMBER DESCRIBING THE RECORD IS THE SERVER'S. `total` is what the
            record holds, and it is stated even when the page shows all of it, because
            a reader must be able to tell a complete list from a first page without
            counting rows. */}
        <li className="extctx-count">
          {loaded.total} {loaded.total === 1 ? 'entry' : 'entries'} on this record
        </li>
        {shownCount > 0 && shownCount < loaded.total && (
          <li className="extctx-count">Showing the first {shownCount}</li>
        )}
        {loaded.concept_count > 0 && (
          <li className="extctx-count">
            {loaded.concept_count}{' '}
            {loaded.concept_count === 1 ? 'concept' : 'concepts'}
          </li>
        )}
        {/* COUNTED, NEVER RENDERED. The server preserves these rows untouched and
            cannot say what one contains without inventing it; neither can this panel,
            so it reports that the record holds more than the list can show and stops
            there. */}
        {loaded.unreadable_entries > 0 && (
          <li className="extctx-count">
            {loaded.unreadable_entries}{' '}
            {loaded.unreadable_entries === 1 ? 'entry' : 'entries'} this build cannot
            read &mdash; kept in the record, not shown here
          </li>
        )}
      </ul>

      {shownCount === 0 ? (
        loaded.unreadable_entries > 0 ? (
          /* CASE 2 -- a companion whose rows this build cannot read. The number is
             named INLINE rather than by pointing at another line: the count row above
             IS rendered in this case, but a sentence that depends on a neighbour being
             present is a sentence that goes wrong when the neighbour's condition
             changes, which is exactly how case 3 came to cite an absent row. */
          <p className="extctx-empty">
            This record holds an extended context companion, and this build cannot
            read{' '}
            {loaded.unreadable_entries === 1
              ? 'its one entry'
              : `any of its ${loaded.unreadable_entries} entries`}
            . They are kept in the record exactly as they were found. Nothing here is
            reconstructed from them, because nothing can say what one contains without
            inventing it.
          </p>
        ) : (
          /* CASE 3 -- present, and accounting for nothing. See the block above for the
             two false claims this replaces. It asserts no loss and denies none. */
          <p className="extctx-empty">
            This record holds an extended context companion that lists no entries, and
            records none as unreadable. This build cannot say what it held &mdash; an
            empty list and a document whose entries could not be read at all look the
            same from here &mdash; so nothing is reconstructed from it and nothing is
            claimed about it. The document itself is kept exactly as it was found.
          </p>
        )
      ) : (
        <ul className="extctx-list">
          {shown.map((entry) => (
            <EntryCard key={entry.entry_id} entry={entry} />
          ))}
        </ul>
      )}

      {/* A FAILED "SHOW MORE", DISCLOSED BESIDE THE LIST AND NEVER IN PLACE OF IT.
          `CLAUDE.md` S11's 2026-09-10 rule: the entries already on screen are the
          reader's, and a failed request for MORE of them is no reason to take them
          away. */}
      {appendError !== null && (
        <p className="extctx-count" role="status">
          Those additional entries could not be read just now
          {appendError.message === '' ? '' : `: ${appendError.message}`}. Nothing
          already shown has changed &mdash; try again.
        </p>
      )}

      {loaded.has_more && (
        <div className="extctx-more">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={onMore}
            disabled={appending}
          >
            {appending ? 'Reading…' : 'Show more'}
          </button>
          {/* TWO NUMBERS FROM TWO PLACES, ON PURPOSE -- see `shownCount` above.
              `shownCount` is what the reader can see and comes from the accumulated
              array; `total` is what the record holds and comes from the server. */}
          <span>
            {shownCount} of {loaded.total} shown
          </span>
        </div>
      )}
    </>
  );
}
