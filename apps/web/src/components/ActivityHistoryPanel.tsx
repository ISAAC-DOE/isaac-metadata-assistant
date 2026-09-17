import { useCallback, useEffect, useRef, useState } from 'react';
import './activityHistory.css';
import { api } from '../lib/api';
import { LABELS } from '../lib/labels';
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

/** The server's vocabularies arrive as snake_case tokens; this is the ONLY place
 *  they are turned into words, and it invents no vocabulary of its own.
 *
 *  A token with no entry is HUMANIZED generically rather than dropped or shown
 *  raw — `Title Case` from its own segments, so a server that adds an action keeps
 *  working and a scientist still reads English. That mirrors the humanizer
 *  `assistant_query` already uses, and the reason is `CLAUDE.md` §11's measured
 *  rule: a bare internal identifier rendered at a scientist is a defect, and the
 *  fix is the words the token already contains — never a guess at what it meant. */
function humanizeToken(token: string): string {
  return token
    .split('_')
    .filter((part) => part.length > 0)
    .map((part) => (part === 'qc' ? 'QC' : part.charAt(0).toUpperCase() + part.slice(1)))
    .join(' ');
}

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
        <time className="activity-when" dateTime={event.recorded_utc}>
          {event.recorded_utc}
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
  /* Guards a response from a PREVIOUS experiment id landing after a switch. The
     record screen unmounts this panel on a switch, so React would no-op the late
     setState anyway — this is hazard-class defence, and it is labelled as such
     rather than as a regression guard, exactly as the capture panel's are. */
  const wanted = useRef(experimentId);

  const load = useCallback(() => {
    wanted.current = experimentId;
    setState({ status: 'loading' });
    api
      .listActivity(experimentId)
      .then((body) => {
        if (wanted.current !== experimentId) return;
        setState({ status: 'data', body });
      })
      .catch(() => {
        if (wanted.current !== experimentId) return;
        setState({ status: 'error' });
      });
  }, [experimentId]);

  useEffect(load, [load]);

  return (
    <section className="activity-panel" aria-labelledby="activity-heading">
      <h2 id="activity-heading" className="activity-heading">
        {LABELS.activityTitle}
      </h2>
      <p className="activity-lead">{LABELS.activityLead}</p>
      {/* THE ACTOR DISCLOSURE, ONCE AND IN WORDS. See the module docstring: this
          is `ACT-003`'s "render `unattributed` honestly" requirement, discharged
          as a sentence a scientist can read rather than as a token on every row. */}
      <p className="activity-actor-note">{LABELS.activityActorUnattributed}</p>

      {state.status === 'loading' && <p className="activity-status">{LABELS.activityLoading}</p>}
      {state.status === 'error' && (
        <p className="activity-status activity-status-error">{LABELS.activityUnavailable}</p>
      )}
      {state.status === 'data' && (
        <>
          <p className="activity-counts">
            {/* EVERY NUMBER HERE IS THE SERVER'S. None is `events.length`. */}
            {state.body.total === 0
              ? LABELS.activityEmpty
              : `${state.body.returned} of ${state.body.total}`}
            {state.body.unreadable_entries > 0 && (
              <span className="activity-unreadable">
                {' '}
                {LABELS.activityUnreadable} {state.body.unreadable_entries}
              </span>
            )}
          </p>
          {state.body.total > 0 && (
            <ol className="activity-list">
              {state.body.events.map((e) => (
                <EventRow key={e.id} event={e} />
              ))}
            </ol>
          )}
        </>
      )}
    </section>
  );
}
