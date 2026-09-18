import { useCallback, useEffect, useRef, useState } from 'react';
import './activityHistory.css';
import { api } from '../lib/api';
import { LABELS, humanizeActivityToken as humanizeToken } from '../lib/labels';
import type { ApiActivityEvent, ApiActivityResponse } from '../lib/types';

/**
 * THE APPEND-ONLY ACTIVITY HISTORY, FOR A SCIENTIST — `ACT-003`, against `DEC-44`.
 *
 * ── WHAT THIS SURFACE IS FOR ────────────────────────────────────────────────
 *
 * One question: *what happened to this record, and in what order?* It is a
 * destination, not a workflow step — there is no derivable criterion for "the
 * history is finished", so it carries no tick, no lock and no `aria-current="step"`.
 * That is the same argument `workflow.py:128-149` makes for submission and the
 * capture group makes for itself, and it is why this lives in the sidebar's
 * destination list rather than in the workflow spine.
 *
 * ── READ-ONLY, STRUCTURALLY ─────────────────────────────────────────────────
 *
 * There is no control on this panel that writes anything, and there is no client
 * method that could: `api.listActivity` has no sibling mutator because
 * `activity.py` exposes none. An event is recorded by the act it describes.
 *
 * ── THE FOUR COUNTS ARE NEVER COLLAPSED ─────────────────────────────────────
 *
 * `total` (every act on the record), `matched` (those satisfying the filter) and
 * `returned` (those on this page) are three different facts, and every number
 * rendered here reads the SERVER's field — never `events.length`. `CLAUDE.md` §11
 * records the defect that rule exists for: a count taken from a fetched array
 * understates the truth the moment a page is smaller than the whole. A separate
 * `unreadable_entries` is disclosed rather than hidden, because a stored event this
 * build cannot parse must be counted; rendering it would mean inventing its content.
 *
 * ── `unattributed` IS SHOWN, NOT HIDDEN ─────────────────────────────────────
 *
 * `ACT-003`'s own requirement. Every event in every deployment of this build reads
 * `actor: "unattributed"`, because no trusted authentication boundary exists
 * (`EXT-01`) and a name read from a forwarded header would be a forgeable claim
 * rendered as a fact. Confirmed on the hosted deployment on 2026-09-17:
 * `actor_trust_basis: null`, `verifier_id: "unconfigured"`. So the panel says so in
 * words, once, at the top — rather than printing a literal nobody can interpret
 * beside every row, and rather than dropping the rows that "lack" an actor.
 */

/* THE HUMANIZER MOVED TO `lib/labels.ts`, and this note is why rather than a
 * silent import.
 *
 * It was defined HERE, with a comment saying "this is the ONLY place they are
 * turned into words" — true when it was written, and it stopped being true the
 * moment a SECOND surface rendered the same server vocabularies (`ACT-004`'s
 * activity summary on the Statistics Overview tab). Copying six lines would have
 * made two functions that agree today and are free to disagree later, which is
 * the defect this repository records as "one vocabulary, three copies": a rename
 * strands every copy but the one the author was looking at.
 *
 * So there is still exactly ONE humanizer for these tokens, and it is now
 * somewhere both surfaces can reach.
 *
 * ~~Its behaviour is unchanged — the `activity-history-panel` suite passes against
 * it untouched, which is the check that matters for a move.~~ **FALSE, and
 * corrected rather than deleted, because "behaviour is unchanged" is exactly the
 * claim a future session would rely on when judging whether this move was safe.**
 * The shared version added an initialism map, so a row on the `mcp` channel moved
 * **"Mcp" -> "MCP"** on THIS panel as well as on the Statistics summary that
 * prompted the map. The change is an improvement and is deliberate; the suite
 * passing is true and was never evidence of no change, because no test named
 * either spelling. What IS unchanged: every other token, and the fact that every
 * output word is an input word — casing only, so no name is invented. */

/** `{present: false}` and `{present: true, value: null}` are DIFFERENT FACTS and are
 *  rendered differently. Branching on `value` instead of `present` would collapse
 *  "there was nothing here" into "it was empty", which is the distinction the
 *  server's envelope exists to carry. */
function describeSide(side: { present: boolean; value: unknown }): string {
  if (!side.present) return LABELS.activityAbsent;
  const { value } = side;
  if (value === null) return LABELS.activityNull;
  if (typeof value === 'string') return value === '' ? LABELS.activityEmptyString : value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return JSON.stringify(value);
}

/**
 * A timestamp a scientist reads, with the machine value kept where machines look.
 *
 * TWO DEFECTS IN ONE, both found by registering this surface for the responsive
 * sweep (`ACT-003`'s own accepted round trip), and both mine:
 *
 *  1. LAYOUT. The raw `recorded_utc` is an unbreakable ~20-character token
 *     (`2099-01-01T00:00:00Z`) in a `flex-wrap` row with no `overflow-wrap`, so it
 *     sets a min-content floor that widened the content column and squeezed the
 *     workflow spine's own flex children — CI reported `scrollWidth 200 vs
 *     clientWidth 1` on `span.spine-meta`, a sibling ABOVE this panel. A too-wide
 *     child clips its neighbours, not itself.
 *  2. COPY. An ISO-8601 string with a `T` and a `Z` is a WIRE FORMAT. Rendering it
 *     at a scientist is the same defect class as rendering `Q6` — `CLAUDE.md` §11's
 *     rule — and it was hiding behind a real layout failure.
 *
 * `toLocaleString` is used with an explicit option set rather than a hand-rolled
 * format, so this invents no date vocabulary; an unparseable value falls back to the
 * stored string rather than to a guess or an empty cell.
 */
function readableWhen(iso: string): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return iso;
  return at.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function EventRow({ event }: { event: ApiActivityEvent }) {
  const showsChange = event.before.present || event.after.present;
  return (
    <li className="activity-row">
      <p className="activity-row-head">
        <span className="activity-action">{humanizeToken(event.action)}</span>
        <span className="activity-object">{humanizeToken(event.object_type)}</span>
        {/* The channel is the half of `DEC-44` that is knowable today, so it is
            shown plainly: a scientist can tell their own typing from an agent's
            write and from an archive import. */}
        <span className="activity-channel">{humanizeToken(event.channel)}</span>
        {/* The machine value stays in `dateTime` — that attribute exists for it —
            so nothing is lost by showing the readable form. */}
        <time className="activity-when" dateTime={event.recorded_utc}>
          {readableWhen(event.recorded_utc)}
        </time>
      </p>
      {event.field_path && <p className="activity-field">{event.field_path}</p>}
      {showsChange && (
        <p className="activity-change">
          <span className="activity-before">{describeSide(event.before)}</span>
          <span className="activity-arrow" aria-hidden="true">
            {' → '}
          </span>
          {/* The global utility from `styles/base.css`, not a local copy. */}
          <span className="sr-only">{LABELS.activityChangedTo}</span>
          <span className="activity-after">{describeSide(event.after)}</span>
        </p>
      )}
    </li>
  );
}

export function ActivityHistoryPanel({ experimentId }: { experimentId: string }) {
  const [state, setState] = useState<
    { status: 'loading' } | { status: 'error' } | { status: 'data'; body: ApiActivityResponse }
  >({ status: 'loading' });
  /*
   * PAGES ALREADY READ, oldest-appended. The server answers newest-first and hands
   * back `next_before_seq`, so "older" is a cursor walk rather than an offset — the
   * same shape the proposals list uses, and it cannot skip or duplicate an entry when
   * a new act lands between two reads.
   *
   * WHY THIS EXISTS AT ALL: the first version rendered one page and reported
   * "50 of 200", which named 150 facts a reader could not reach. A count that
   * advertises hidden content with no control to reach it is a dead end, not a
   * deliberate scope boundary — found by an Impeccable pass over this panel.
   */
  const [older, setOlder] = useState<ApiActivityEvent[]>([]);

  const [cursor, setCursor] = useState<number | null>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);
  /* Announced to screen readers, which otherwise hear NOTHING when a read finishes or
     a page arrives — the panel's own status text is not a live region. The alternating
     NBSP is `IngestionProposalsPanel.announce()`'s idiom: an identical string is not
     re-announced, so the toggle forces it. */
  const [announcement, setAnnouncement] = useState('');
  const announce = useCallback((sentence: string) => {
    setAnnouncement((prev) => (prev.endsWith('\u00a0') ? sentence : `${sentence}\u00a0`));
  }, []);
  /* Guards a response from a PREVIOUS experiment id landing after a switch. The
     record screen unmounts this panel on a switch, so React would no-op the late
     setState anyway — this is hazard-class defence, and it is labelled as such
     rather than as a regression guard, exactly as the capture panel's are. */
  const wanted = useRef(experimentId);

  const load = useCallback(() => {
    wanted.current = experimentId;
    setState({ status: 'loading' });
    setOlder([]);
    setCursor(null);
    api
      .listActivity(experimentId)
      .then((body) => {
        if (wanted.current !== experimentId) return;
        setState({ status: 'data', body });
        setCursor(body.next_before_seq);
        announce(
          body.total === 0
            ? LABELS.activityEmpty
            : `${LABELS.activityShowing} ${body.returned} ${LABELS.activityOf} ${body.total} ${LABELS.activityEntries}.`,
        );
      })
      .catch(() => {
        if (wanted.current !== experimentId) return;
        setState({ status: 'error' });
        announce(LABELS.activityUnavailable);
      });
  }, [experimentId, announce]);

  /*
   * ONE PAGE OLDER. Appends rather than replaces, so the reader never loses what they
   * were looking at — and a failed page leaves the list exactly as it was, which is
   * the destructive-silent-failure rule §11 records for the proposals and notes
   * panels: a background failure must not destroy what is on screen.
   */
  const loadOlder = useCallback(() => {
    if (cursor === null || loadingOlder) return;
    setLoadingOlder(true);
    api
      .listActivity(experimentId, { beforeSeq: cursor })
      .then((body) => {
        if (wanted.current !== experimentId) return;
        setOlder((prev) => [...prev, ...body.events]);
        setCursor(body.next_before_seq);
        setLoadingOlder(false);
        announce(`${LABELS.activityShowing} ${body.returned} ${LABELS.activityEntries}.`);
      })
      .catch(() => {
        if (wanted.current !== experimentId) return;
        setLoadingOlder(false);
        announce(LABELS.activityUnavailable);
      });
  }, [cursor, experimentId, loadingOlder, announce]);

  useEffect(load, [load]);

  /*
   * HOW MANY ROWS THE READER CAN SEE — counted from the rendered rows, deliberately.
   *
   * I FIRST WROTE THIS AS A SUM OF THE SERVER'S `returned` VALUES, with a comment
   * citing §11's `pendingTotal` rule, and a negative control proved that guard was an
   * EQUIVALENT MUTANT: swapping it back to array lengths failed no test, because in
   * every fixture `returned` equals `events.length`.
   *
   * The mutant passing was informative rather than merely embarrassing — it showed the
   * rule was MIS-APPLIED. §11's defect is taking the TOTAL from a fetched page, which
   * understates outstanding work; that rule is honoured two lines below, where the
   * total is `state.body.total` and never a length. But `shown` is a claim about WHAT
   * IS ON SCREEN, so the rendered rows are its only honest source: a server `returned`
   * that disagreed with the rows delivered would make this sentence describe a list
   * the reader is not looking at.
   *
   * So: TOTAL from the server, always. SHOWN from the DOM's own content, always.
   */
  const shown = state.status === 'data' ? state.body.events.length + older.length : 0;

  return (
    <section className="activity-panel" aria-labelledby="activity-heading">
      <h2 id="activity-heading" className="activity-heading">
        {LABELS.activityTitle}
      </h2>
      <p className="activity-lead">{LABELS.activityLead}</p>
      {/* THE ACTOR DISCLOSURE, BEHIND A NATIVE `<details>` — the repo idiom
          (`HelpPanel`, `AssistantPanel`, `FetchStates`, `SchemaBrowser`):
          keyboard-operable with no ARIA and announced as a disclosure.
          `ACT-003`'s requirement is that `unattributed` be rendered HONESTLY, and
          the sentence behind this is UNCHANGED and still in the DOM — a closed
          `<details>` is reachable by `querySelectorAll`, by find-in-page and by a
          screen reader. What changed is that ~40 words of standing explanation
          stop being permanent furniture for a reader who has met them once, which
          is the owner's own direction: honest prose goes behind a collapsible
          rather than being capped or deleted. The SUMMARY still states the fact,
          so nothing is hidden behind a neutral label. */}
      <details className="activity-actor-details">
        <summary className="activity-actor-summary">{LABELS.activityWhyUnattributed}</summary>
        <p className="activity-actor-note">{LABELS.activityActorUnattributed}</p>
      </details>
      {/* The only live region on this panel. Without it a screen-reader user hears
          nothing when a read finishes or an older page arrives, because the status
          text below is static. */}
      <p className="sr-only" role="status" aria-live="polite">
        {announcement}
      </p>

      {state.status === 'loading' && <p className="activity-status">{LABELS.activityLoading}</p>}
      {state.status === 'error' && (
        <p className="activity-status activity-status-error">{LABELS.activityUnavailable}</p>
      )}
      {state.status === 'data' && (
        <>
          <p className="activity-counts">
            {/* THE TOTAL IS THE SERVER'S, ALWAYS — `state.body.total`, never a page
                length, which is §11's `pendingTotal` rule. `shown` is the opposite and
                deliberately so: it counts the rendered rows, because it describes what
                the reader is looking at (see `shown`'s own note). A NOUN is attached,
                because "50 of 200" is a bare fraction and a reader mid-task should not
                have to infer what it counts. */}
            {state.body.total === 0
              ? LABELS.activityEmpty
              : `${LABELS.activityShowing} ${shown} ${LABELS.activityOf} ${state.body.total} ${LABELS.activityEntries}.`}
            {state.body.unreadable_entries > 0 && (
              <span className="activity-unreadable">
                {' '}
                {LABELS.activityUnreadable} {state.body.unreadable_entries}
              </span>
            )}
          </p>
          {state.body.total > 0 && (
            <>
              <ol className="activity-list">
                {[...state.body.events, ...older].map((e) => (
                  <EventRow key={e.id} event={e} />
                ))}
              </ol>
              {cursor !== null ? (
                <button
                  type="button"
                  className="btn btn-secondary activity-older"
                  onClick={loadOlder}
                  disabled={loadingOlder}
                >
                  {loadingOlder ? LABELS.activityLoadingOlder : LABELS.activityShowOlder}
                </button>
              ) : (
                /* Said explicitly rather than by the control simply vanishing: a
                   missing button is ambiguous between "no more" and "broken". */
                <p className="activity-counts">{LABELS.activityAllShown}</p>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}
