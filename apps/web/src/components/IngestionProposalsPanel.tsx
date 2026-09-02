/*
 * INGESTION PROPOSALS — the review surface for a stored suggestion about one field.
 *
 * WHAT A PROPOSAL IS. A value, the official field path it is for, the deterministic
 * rule that produced them, and the note the content was read from. It is a SUGGESTION
 * awaiting a person's judgement: not a field value, not evidence, not a confirmation,
 * and it does not become one when it is accepted. Accepting records that one of the
 * three existing writers wrote the value; the field's value lives in the envelope that
 * writer produced. The server serialises `verified`, `is_evidence` and
 * `is_field_value` as constants so that guarantee survives the JSON boundary, and
 * `types.ts` types all three as the literal `false` so nothing here can branch on one
 * being true.
 *
 * NOTHING IN THIS BUILD PRODUCES A PROPOSAL, AND THIS PANEL SAYS SO RATHER THAN
 * LOOKING BROKEN. `routes.py` states it directly — "NOTHING WAS REWIRED TO FEED THEM.
 * There is no automatic producer" — so a record's proposal list is empty in every
 * deployment today. The empty state reports that as a fact about the build, exactly as
 * `UnmappedNotesPanel` reports that it manufactures no notes, instead of implying the
 * read failed. There is deliberately no create control here either: a review surface
 * that manufactured the queue it reviews would be reviewing itself.
 *
 * FIVE THINGS THIS PANEL WILL NOT DO, each of which it would be easy to do:
 *
 *   1. IT NEVER PRESENTS A PROPOSED VALUE AS THE RECORD'S VALUE. The proposed value is
 *      labelled as proposed, everywhere, in every state. What the record holds NOW is
 *      a SEPARATE, EXPLICIT read (`ShowsCurrentValue`), taken on demand, labelled with
 *      which route it came from and when — never inferred from the proposal.
 *   2. IT NEVER COLLAPSES `null` INTO `false`. `target_stale` and `still_current` are
 *      three-valued: `null` means the question could not be ANSWERED (the run the
 *      proposal names has been removed), which is a different fact from "nothing
 *      changed". Each has its own sentence, and the `null` sentence claims nothing.
 *   3. IT NEVER CLAIMS AN ACCEPTANCE THE SERVER DID NOT CONFIRM. Every act awaits the
 *      write's own response; the announcement and the refreshed list both come after
 *      it. A refusal produces the refusal's own sentence and no state change here.
 *   4. IT NEVER HIDES A CLOSED PROPOSAL BY DEFAULT. The filter starts at "All", and
 *      the counts state the record's true total whatever the filter says, because
 *      rejecting is a STATE and this API has no delete.
 *   5. IT NEVER DESTROYS WHAT IS BEING TYPED. Every refresh this panel performs is
 *      SILENT — it refreshes the list in place rather than blanking it — so a
 *      background change-feed update, a filter change or a refusal cannot take a
 *      half-written corrected value with it. `CLAUDE.md` §11 records this repository
 *      shipping the opposite three times.
 *
 * THE ACCEPT CONTROL, AND THE TWO DIFFERENT RULES ABOUT IT.
 *
 *   (a) PER PATH — implemented here. `docs/ingestion-proposal-contract.md` §6: "no
 *       Accept control is rendered for a path outside [the served set]", the same
 *       posture `_UNACCEPTABLE_READER_PATHS` takes at import time. The list response
 *       carries the server's own `target_field_paths` and
 *       `record_scoped_target_field_paths`, so this surface can be truthful about the
 *       path in front of the reader without transcribing either set. Where the
 *       server's answer makes acceptance PERMANENTLY impossible for this proposal —
 *       no write route for the path, a scope the writer cannot serve, or a target
 *       whose current content cannot be read at all — Accept is withheld and the
 *       reason is stated. The three refusing acts stay available in every one of
 *       them, because a proposal that cannot be applied must still be clearable
 *       (DEC-9's unclearable-queue defect).
 *
 *       THERE IS A FOURTH SERVER-OBSERVABLE REFUSAL AND IT IS NOT IN THAT LIST:
 *       `target_stale === true`, which the server answers `409 proposal_stale`. It is
 *       deliberately fail-OPEN, because unlike the other three it is not permanent —
 *       the value at a target that moved can move back, and this window's answer was
 *       taken when the list was read. `TargetState` says so on the card rather than
 *       leaving a live control standing next to a sentence that reads as its
 *       contradiction.
 *
 *   (b) PER DEPLOYMENT — deliberately NOT implemented, and that is the harder half.
 *       `accept` answers `409 human_actor_required` in every DEFAULT-CONFIGURED
 *       deployment. That is a claim about CONFIGURATION and not about the build:
 *       `FixtureEdgeVerifier` mints an actor from the process environment and the
 *       dependency then admits the request. `identity.py` records withdrawing exactly
 *       this over-claim once already. So Accept is rendered, the 409 is reported
 *       specifically and truthfully when it arrives, and nothing here asserts in
 *       either direction before asking. The server serves no capability flag for it;
 *       see the slice report for that gap.
 *
 * ONE VALIDATOR, THE RECORD'S. A proposal lives inside the experiment's own state
 * document, so every review carries the EXPERIMENT's version token — re-read from each
 * write's own response, and adopted from a 412's `current_version` so one refusal
 * cannot strand the panel a revision behind for good.
 */
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';

import { api, ApiError } from '../lib/api';
import { mutationFailureCopy, staleWriteCurrentVersion, statusOf } from '../lib/mutationErrors';
import type { RecordChangeSummary } from '../lib/recordChanges';
import type {
  ApiProposal,
  ApiProposalOrder,
  ApiProposalReviewAction,
  ApiProposalsResponse,
} from '../lib/types';
import { BackendDown, LoadingPanel } from './FetchStates';
import './ingestionProposals.css';

/** Same narrowing `UnmappedNotesPanel` uses — a non-`ApiError` throw still renders. */
function asApiError(err: unknown): ApiError {
  return err instanceof ApiError
    ? err
    : new ApiError(err instanceof Error ? err.message : String(err));
}

/** The `error` string the backend put in a refusal body, or `undefined`. */
function refusalCode(err: unknown): string | undefined {
  if (typeof err !== 'object' || err === null) return undefined;
  const body = (err as { body?: unknown }).body;
  if (typeof body !== 'object' || body === null) return undefined;
  const code = (body as { error?: unknown }).error;
  return typeof code === 'string' ? code : undefined;
}

/** A named list off a refusal body (e.g. `allowed` on `not_an_allowed_value`). */
function refusalList(err: unknown, key: string): string[] {
  if (typeof err !== 'object' || err === null) return [];
  const body = (err as { body?: unknown }).body;
  if (typeof body !== 'object' || body === null) return [];
  const value = (body as Record<string, unknown>)[key];
  return Array.isArray(value) ? value.map((entry) => String(entry)) : [];
}

/*
 * WHAT IS TRANSCRIBED HERE, STATED PLAINLY BECAUSE THE SLICE REPORT OVERSTATED IT.
 *
 * The report said "nothing transcribed". That is true of the two things it matters
 * for — the set of paths a proposal may target and the scope split between them, both
 * of which are read from the response on every render and never listed here — and it
 * is FALSE as a blanket claim about this file. Four label maps below are transcriptions
 * of server vocabularies, and two behavioural branches are: `proposal.state === 'open'`
 * gates the whole action area and `=== 'accepted'` gates the acceptance record.
 *
 * That is defensible and is not being changed. A label map is COPY, and copy is this
 * client's to write — an unmapped token renders verbatim rather than as a blank, so a
 * vocabulary that grows degrades to honest jargon instead of silence. The two state
 * branches are behaviour, but they test the ONE state the server itself singles out:
 * `_refuse_a_closed_proposal` tests `state != STATE_OPEN` directly rather than against
 * a set of the others, and `proposals.py` records deleting a `TERMINAL_STATES`
 * constant for being "a named set that reads as the rule while enforcing none of it".
 * Matching that shape is better than inventing a second one here.
 *
 * What must not happen is the claim outrunning the code, which is what the report did.
 */

/**
 * How each lifecycle state reads to a scientist.
 *
 * `rejected`, `superseded` and `withdrawn` all say "kept on the record", because the
 * single most likely misreading of this panel is that one of them removed something.
 * This API has no delete, and the note behind a proposal survives every outcome.
 *
 * THE VERBATIM FALLBACK IS DEFENCE, NOT A SUPPORTED CASE, and the distinction is the
 * one `types.ts` draws: `ApiProposal.state` is a CLOSED five-member union, because
 * `proposals.PROPOSAL_STATES` is closed server-side, so a token outside it cannot
 * arrive through the declared type. This client validates no response, so a payload
 * that violates the type still can — and honest jargon beats a blank chip or a
 * `undefined`. It is deliberately NOT the same claim as the FILTER's, which handles an
 * unrecognised member of the served `states` list as a real, reachable case.
 */
const STATE_LABELS: Readonly<Record<string, string>> = {
  open: 'Awaiting your judgement',
  accepted: 'Accepted — a value was written',
  rejected: 'Rejected — kept on the record',
  superseded: 'Superseded — kept on the record',
  withdrawn: 'Withdrawn — kept on the record',
};

function stateLabel(state: string): string {
  return STATE_LABELS[state] ?? state;
}

/** Filter-option wording. Same fallback rule as `stateLabel`. */
const FILTER_LABELS: Readonly<Record<string, string>> = {
  open: 'Awaiting judgement',
  accepted: 'Accepted',
  rejected: 'Rejected',
  superseded: 'Superseded',
  withdrawn: 'Withdrawn',
};

/** The button wording for each review act. Unknown acts are not offered. */
const ACTION_LABELS: Readonly<Record<ApiProposalReviewAction, string>> = {
  accept: 'Accept as Proposed',
  reject: 'Reject',
  supersede: 'Supersede',
  withdraw: 'Withdraw',
};

/** What each refusing act means, said once so the three cannot drift apart. */
const ACTION_MEANINGS: Readonly<Record<'reject' | 'supersede' | 'withdraw', string>> = {
  reject: 'Reject records that the VALUE is wrong. Nothing is removed.',
  supersede:
    'Supersede records that a later judgement replaces this one. Nothing is removed, and ' +
    'nothing here creates the replacement.',
  withdraw:
    'Withdraw records that the proposal should not have been made — a judgement about the ' +
    'proposal, not about the value. Nothing is removed.',
};

/** Which writer applied an accepted value, in product words. */
const APPLIED_VIA_LABELS: Readonly<Record<string, string>> = {
  run_field: "the run's own field edit",
  run_override: "the run's override",
  record_enum_fields: "the record's own field write",
};

/**
 * The acts this client knows how to send. The SERVER's `review_actions` decides which
 * are offered; this is the intersection, so an act a future server adds is not
 * rendered as a button that would send a body this client never composed.
 */
const KNOWN_REVIEW_ACTIONS: readonly ApiProposalReviewAction[] = [
  'accept',
  'reject',
  'supersede',
  'withdraw',
];

function isKnownAction(value: string): value is ApiProposalReviewAction {
  return (KNOWN_REVIEW_ACTIONS as readonly string[]).includes(value);
}

/**
 * Why Accept cannot be offered for this proposal, or `null` when it can.
 *
 * EVERY BRANCH RESTS ON SOMETHING THE SERVER SAID, and none of them is a guess about
 * the deployment. `target_field_paths` and `record_scoped_target_field_paths` are the
 * server's own answer to "which paths may be targeted, and at which scope".
 *
 * THE THIRD BRANCH REPORTS WHAT WAS OBSERVED AND HEDGES THE CAUSE, deliberately. What
 * the server said is `current_target_digest: null`, and `routes._current_target_digest`
 * answers `null` for THREE reasons: the run is gone, `_proposal_target_state` raised,
 * or `proposals.target_digest` raised on unserialisable stored content. Withholding
 * Accept is right in all three — the acceptance precondition has nothing to compare
 * against in any of them — but only the first is the removed run, so the copy names it
 * as the reachable cause rather than asserting it as the fact. The first version
 * asserted it, which is a claim about a record this surface cannot make.
 *
 * THERE IS A FOURTH SERVER-OBSERVABLE CONDITION AND IT IS DELIBERATELY NOT HERE:
 * `target_stale === true`. Accepting such a proposal is refused `409 proposal_stale`
 * as things stand — but `target_stale` is derived from a digest taken when this window
 * was read, and a target that moved can move BACK, at which point the acceptance
 * succeeds. So it is rendered as a warning beside a live control rather than as a
 * withheld one: the three cases here are permanent for this proposal, and that one is
 * not. `TargetState` carries the sentence, and it is worded "as of this read".
 *
 * IT IS FAIL-OPEN WHEN THE SERVER DID NOT SAY, and the direction is the decision. If
 * `target_field_paths` is absent or empty this returns `null` — Accept is rendered and
 * the server answers. Withholding a control on the strength of a set we did not
 * receive would be this surface asserting a limitation it cannot observe, which is the
 * same over-claim in the opposite direction.
 *
 * IT SAYS NOTHING ABOUT `human_actor_required`. That refusal is a fact about
 * configuration, is not observable from this payload, and is reported when it arrives.
 */
export function acceptUnavailableReason(
  proposal: ApiProposal,
  served: { targetFieldPaths?: string[]; recordScopedTargetFieldPaths?: string[] },
): string | null {
  const targets = served.targetFieldPaths;
  const recordScoped = served.recordScopedTargetFieldPaths;
  if (proposal.run_id !== null && proposal.current_target_digest === null) {
    return (
      'The current content at this proposal’s target could not be read, so accepting it ' +
      'is withheld: there is nothing for the acceptance precondition to check against. ' +
      'For a proposal that names a run, the reachable cause is that the run is no ' +
      'longer on this record — a removed run keeps its id, it is never reissued, and ' +
      'the proposal is not re-aimed at another, because that would be inferring which ' +
      'run was meant. It can still be withdrawn.'
    );
  }
  if (!Array.isArray(targets) || targets.length === 0) return null;
  if (!targets.includes(proposal.target_field_path)) {
    return (
      'No write operation in this build accepts a value at this field path, so accepting ' +
      'could never write one. That is a limitation of this application and NOT a ' +
      'statement about the official ISAAC schema, which defines this field. The note ' +
      'behind this proposal is untouched.'
    );
  }
  if (!Array.isArray(recordScoped)) return null;
  const isRecordScoped = recordScoped.includes(proposal.target_field_path);
  if (isRecordScoped && proposal.run_id !== null) {
    return (
      'A value at this field path is written on the RECORD, and this proposal names a ' +
      'run. The value is never written somewhere other than where the proposal says it ' +
      'belongs, so this cannot be accepted as it stands.'
    );
  }
  if (!isRecordScoped && proposal.run_id === null) {
    return (
      "A value at this field path is applied through a run's writer, and this proposal " +
      'names no run. The value is never written somewhere other than where the proposal ' +
      'says it belongs, so this cannot be accepted as it stands.'
    );
  }
  return null;
}

/**
 * What a 412 means here, and what the panel does about it — `UnmappedNotesPanel`'s
 * `STALE_REVIEW_COPY`, for its reason. The held token is adopted from the refusal and
 * the list is refreshed SILENTLY, so nothing that was typed is unmounted.
 */
const STALE_REVIEW_COPY =
  'The record changed since this section was loaded, so that was not recorded — it can ' +
  'be your own edit elsewhere on this screen. Nothing was written: this section has ' +
  'picked up the current version and what you typed is still here, so try again.';

/**
 * The sentence for each refusal this operation can produce.
 *
 * EACH IS THE SERVER'S OWN DISTINCTION, KEPT. Four different conditions arrive as
 * `409` and their remedies differ completely — one is permanent for this deployment,
 * one is cleared by re-reading, one is permanent for this proposal, and one says the
 * value belongs somewhere other than where it would be written. Collapsing them into
 * "could not be recorded (409)" would send a reader round a loop for the first and
 * would blame the record for the second.
 */
function reviewRefusalCopy(err: unknown, action: ApiProposalReviewAction): string {
  const code = refusalCode(err);
  if (code === 'human_actor_required') {
    return (
      'Accepting writes a scientific value into this record, which is an attributable ' +
      'act — and this deployment establishes no attributable human actor, so the ' +
      'request was refused and NOTHING WAS WRITTEN. That is a fact about how this ' +
      'deployment is configured, not a fault in this record or in what you did, and ' +
      'retrying will not change it. Rejecting, superseding and withdrawing need no ' +
      'actor and still work.'
    );
  }
  if (code === 'proposal_stale') {
    return (
      'What this record holds at that field path has changed since this proposal was ' +
      'made, so accepting it now would write a judgement about content that is no ' +
      'longer there. Nothing was written. The proposal is still here: withdraw it, ' +
      'supersede it, or make a new one against the value that is there now.'
    );
  }
  if (code === 'target_run_removed') {
    return (
      'The run this proposal names no longer exists on this record, so there is nothing ' +
      'to write the value to. It is not re-aimed at another run — a removed run keeps ' +
      'its id and it is never reissued. Nothing was written; the proposal can still be ' +
      'withdrawn.'
    );
  }
  if (code === 'target_scope_mismatch') {
    return (
      'This proposal names a scope the write route for its field path does not serve, so ' +
      'the value is not written somewhere other than where the proposal says it belongs. ' +
      'Nothing was written; the proposal stays readable and can be withdrawn.'
    );
  }
  if (code === 'proposal_not_open') {
    return (
      'This proposal has already been reviewed, so a second act on it was refused and ' +
      'nothing was written. Every recorded judgement stays exactly as it was made; a ' +
      'later view is a new proposal, with its own history.'
    );
  }
  if (code === 'not_an_allowed_value') {
    const allowed = refusalList(err, 'allowed');
    return (
      'The official schema closes this field with a fixed list of values, and this value ' +
      'is not one of them, so nothing was written.' +
      (allowed.length > 0 ? ` The schema allows: ${allowed.join(', ')}.` : '')
    );
  }
  if (code === 'no_write_path_for_field') {
    return (
      'The write route that owns this field path refused it, so nothing was written. ' +
      'That is a limitation of this build and not a statement about the official ISAAC ' +
      'schema.'
    );
  }
  if (statusOf(err) === 428) {
    return (
      'This section does not currently hold the record’s version, so the request was ' +
      'not made and nothing was written. Reload this section and try again.'
    );
  }
  const verb =
    action === 'accept' ? 'That acceptance' : `That ${action === 'reject' ? 'rejection' : action}`;
  return mutationFailureCopy(err, `${verb} could not be recorded. Nothing was written.`);
}

/**
 * A value as text.
 *
 * A string is shown as the scientist would read it; anything else is rendered as
 * deterministic JSON. A value that cannot be rendered at all says so rather than
 * showing `[object Object]`, which would be this surface inventing a rendering for
 * content it could not read.
 */
function renderValue(value: unknown): string {
  if (typeof value === 'string') return value;
  try {
    const text = JSON.stringify(value, null, 2);
    return text === undefined ? 'This value could not be shown.' : text;
  } catch {
    return 'This value could not be shown.';
  }
}

/** The JSON text an editor starts from. Empty when the value cannot be rendered. */
function jsonText(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2) ?? '';
  } catch {
    return '';
  }
}

/**
 * How the window's ORDER is disclosed — ONE string, so the wording cannot drift
 * between the control and the sentence a screen reader hears.
 *
 * IT IS SAID IN BOTH DIRECTIONS, INCLUDING THE DEFAULT. Saying it only for
 * `newest_first` would mean the count line is silent about order exactly when the
 * reader has not chosen one, so "no clause" would have to be read as "oldest first"
 * — an inference from an absence. Both are one short clause instead.
 *
 * IT RIDES THE COUNT LINE AND RAISES NO REGION OF ITS OWN. `.proposals-count` is
 * already `aria-live="polite"`, so changing the order changes that sentence and it
 * is announced once. A second live region for the same fact would announce it twice.
 */
function orderClause(order: ApiProposalOrder): string {
  return order === 'newest_first' ? ' · newest first' : ' · oldest first';
}

/** The label the order control and its option share. */
const ORDER_LABELS: Record<ApiProposalOrder, string> = {
  oldest_first: 'Oldest first',
  newest_first: 'Newest first',
};

/**
 * How `unreadable_entries` is disclosed — ONE string, used by the count line and by
 * both empty states, so two places on the same screen cannot say different things.
 *
 * It does NOT say "cannot read", because the server's single number covers two facts:
 * an entry the model refused, and an entry whose id another proposal already holds.
 * The copy says what is true of both — that they are not SHOWN — and names both
 * causes rather than asserting the one that is wrong half the time.
 */
function unreadableClause(count: number): string {
  if (count <= 0) return '';
  const noun = count === 1 ? 'entry' : 'entries';
  const asOne = count === 1 ? 'as a proposal' : 'as proposals';
  return (
    ` · ${count} stored ${noun} this version cannot show ${asOne}` +
    ' — either unreadable, or repeating an id another proposal already holds' +
    ' — kept unchanged on the record'
  );
}

type ListState =
  | { status: 'loading' }
  | { status: 'error'; error: ApiError }
  | { status: 'data'; loaded: ApiProposalsResponse };

export function IngestionProposalsPanel({
  experimentId,
  activity,
}: {
  experimentId: string;
  /**
   * The change-feed summary this screen already holds, or null.
   *
   * IDS AND STATES ONLY, NEVER CONTENT. A `proposal` feed entry is an ANNOUNCEMENT —
   * `change_feed.py` imports nothing from `proposals.py`, which makes "the feed
   * carries no proposal content" structural rather than promised — so this panel
   * re-reads through the list route and renders nothing from the summary itself.
   */
  activity?: RecordChangeSummary | null;
}) {
  return (
    <section className="proposals-section" aria-labelledby="ingestion-proposals-heading">
      <div className="proposals-head">
        <h2 className="proposals-title" id="ingestion-proposals-heading">
          Ingestion Proposals
        </h2>
        <p className="proposals-sub">
          Stored suggestions about one field each: a value, the field path it is for, and
          the rule that produced them. Nothing here is a field value, evidence or a
          confirmation — not even once it has been accepted — and nothing here is ever
          deleted. Rejecting, superseding and withdrawing are states, and the note behind
          a proposal survives all of them.
        </p>
      </div>
      {/* Keyed on the record so switching records rebuilds this panel's state rather
          than showing one record's proposals under another's heading. */}
      <ProposalsBrowser
        key={experimentId}
        experimentId={experimentId}
        activity={activity ?? null}
      />
    </section>
  );
}

function ProposalsBrowser({
  experimentId,
  activity,
}: {
  experimentId: string;
  activity: RecordChangeSummary | null;
}) {
  const [list, setList] = useState<ListState>({ status: 'loading' });
  const [filter, setFilter] = useState<string>('all');
  /**
   * WHICH END OF THE RECORD'S PROPOSAL ORDER THIS PANEL IS READING FROM.
   *
   * The default is the SERVER'S default and this panel does not restate it in a
   * request — see the fetch below. It matters that the default is unchanged: this
   * list has always read oldest-first, a review queue reads chronologically, and
   * flipping every existing reader's queue is not something an accessibility fix to
   * one arrival note gets to decide.
   *
   * `newest_first` exists because the arrival announcement was otherwise a dead end.
   * `workspace.py::_sorted_proposals` orders `(proposed_utc, proposal_id)` oldest
   * first, a freshly created proposal carries the LATEST `proposed_utc` on the
   * record and therefore sorts LAST, and this panel's default view is the first
   * window. On a record already holding a full window the arrived proposal is not in
   * the view at all — so the panel could truthfully say something arrived and leave
   * the reader no way to see it without paging to the end.
   */
  const [order, setOrder] = useState<ApiProposalOrder>('oldest_first');
  const [version, setVersion] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [announcement, setAnnouncement] = useState('');
  /**
   * THE VISIBLE HALF OF AN ARRIVAL ANNOUNCEMENT — see the effect that sets it,
   * below. `null` means nothing is being said; dismissing sets it back to `null`
   * without touching `announcement` (the sr-only region), which is a one-shot
   * utterance and needs no dismissal of its own.
   */
  const [arrivalNote, setArrivalNote] = useState<string | null>(null);
  /**
   * THE RUNNING TOTAL BEHIND `arrivalNote`, ACCUMULATED SINCE THE LAST DISMISS.
   *
   * A second arrival while the first note is still standing used to render the
   * SAME sentence a second time — invisible, because the text had not changed —
   * so a reader who dismissed nothing still lost the second arrival. The note is
   * now built from this running total rather than from one arrival's own delta,
   * and it is reset ONLY by Dismiss — never by this panel's own review acts,
   * because a proposal counted here may still be sitting unreviewed regardless
   * of what this reader just accepted, rejected, superseded or withdrew on a
   * DIFFERENT proposal. See `dismissArrivalNote` below.
   */
  const arrivalTotalRef = useRef(0);

  /**
   * Put a sentence into the live region SO THAT IT IS ACTUALLY ANNOUNCED.
   *
   * A `role="status"` region announces a CHANGE to its content. Withdrawing P1 and
   * then withdrawing P2 produced a byte-identical string, React saw no change,
   * mutated no text node, and the second act was announced to nobody — the reader
   * who most needs the confirmation gets it once and then silence. That is not
   * hypothetical here: the four act sentences are per-ACT, and a queue is reviewed
   * one card after another.
   *
   * TWO THINGS MAKE CONSECUTIVE ACTS DISTINGUISHABLE. The sentence names the FIELD
   * PATH, which is the part a scientist can act on and which usually differs; and
   * when it does not, an alternating trailing NO-BREAK SPACE guarantees the string
   * differs from the one before it. The marker is whitespace — it changes no word,
   * is not spoken, and is not visible in a `sr-only` region — and it is preferred
   * to a counter for exactly that reason: a counter would be read aloud.
   */
  const announce = useCallback((sentence: string) => {
    setAnnouncement((previous) =>
      previous.endsWith('\u00A0') ? sentence : `${sentence}\u00A0`,
    );
  }, []);
  /**
   * The window being shown. `null` is the first window; anything else is a
   * `next_cursor` a previous window returned. `back` is the stack of cursors walked
   * through to get here, so Previous is exact rather than re-derived.
   */
  const [cursor, setCursor] = useState<string | null>(null);
  const [back, setBack] = useState<(string | null)[]>([]);

  /** Discards an out-of-order response rather than letting it overwrite a newer one. */
  const generationRef = useRef(0);
  /** Suppresses the loading blank on a reload this panel caused itself. */
  const silentRef = useRef(false);

  /*
   * ARRIVAL DETECTION — WHY IT READS `by_state.open` RATHER THAN DIFFING THE WINDOW.
   *
   * The obvious mechanism is "an id in the freshly loaded window that was not in
   * the previous one". It was checked against the server and rejected, because a
   * newly arrived proposal is NOT guaranteed to land inside the window this panel
   * is looking at.
   *
   * `sorted_proposals` (`workspace.py::_sorted_proposals`) orders OLDEST FIRST —
   * `(proposed_utc, proposal_id)` — and `list_proposals` (`routes.py`) walks that
   * order from the cursor forward. A newly arrived proposal has the LATEST
   * `proposed_utc` of anything on the record, so it sorts LAST, not first. The
   * panel's default view is `cursor=null`, i.e. the FIRST `_PROPOSAL_WINDOW_DEFAULT`
   * (50) entries — the OLDEST 50. On any record already holding 50+ proposals, a
   * new arrival is never in that window at all, however many times it is re-read;
   * it only becomes visible once a reader has paged all the way to the last
   * window. A window-diff mechanism would therefore announce nothing for the
   * ordinary case this slice exists to handle, and readers of records with fewer
   * than 50 proposals would get an inconsistent experience depending on which
   * page and filter they happened to have open.
   *
   * `by_state`, by contrast, is computed by `_proposals_payload` over
   * `exp.proposals` — the WHOLE record — on every list response, REGARDLESS of the
   * `state` filter or the cursor. A freshly created proposal is always `open`
   * (`proposals.STATE_OPEN`), and the four review acts this panel can perform each
   * move a proposal OUT of `open`, never in — there is no path in this build that
   * creates a proposal already reviewed. So an INCREASE in `by_state.open` between
   * two loads can only mean a proposal arrived from elsewhere: it cannot be
   * produced by this panel's own accept/reject/supersede/withdraw, and it is
   * insensitive to which filter or page is currently open. That is the mechanism
   * implemented below.
   */
  /** The `by_state.open` count as of the last successfully loaded response, for
   *  ANY reason (signal, filter, page, this panel's own act). `null` only before
   *  the very first successful load — the guard against announcing on hydration. */
  const lastOpenCountRef = useRef<number | null>(null);
  /**
   * True only while the fetch about to run was started BY THE SIGNAL EFFECT below,
   * as opposed to a filter change, a page change, `reload(false)`'s Retry, or this
   * panel's own review act (`review`/`recoverFromStale` call `reload(true)`
   * directly, never through this ref). Read once at the top of the fetch effect
   * and immediately reset, so it is tied to exactly the request it was set for and
   * cannot leak onto an unrelated later request.
   */
  const arrivalReloadRef = useRef(false);

  const filterId = useId();
  const orderId = useId();

  useEffect(() => {
    let alive = true;
    const generation = ++generationRef.current;
    const isArrivalReload = arrivalReloadRef.current;
    arrivalReloadRef.current = false;
    if (!silentRef.current) setList({ status: 'loading' });
    silentRef.current = false;

    api
      .listProposals(experimentId, {
        ...(filter === 'all' ? {} : { state: filter as never }),
        ...(cursor === null ? {} : { after: cursor }),
        // OMITTED AT THE DEFAULT, so the server's own default is what answers rather
        // than a copy of it kept here. The same rule `limit` follows in `api.ts`.
        ...(order === 'oldest_first' ? {} : { order }),
      })
      .then((loaded) => {
        if (!alive || generation !== generationRef.current) return;
        setList({ status: 'data', loaded });
        setVersion(loaded.experiment_version);

        const openNow = loaded.by_state.open ?? 0;
        const previousOpen = lastOpenCountRef.current;
        /*
         * SUPPRESSED: initial hydration (`previousOpen === null`); a reload this
         * panel caused itself (`isArrivalReload === false` — filter/page changes,
         * `reload(false)`'s Retry, and this panel's own review acts never set the
         * ref); an UNCHANGED count (`openNow === previousOpen` — nothing this
         * panel can read moved either way, so there is nothing to say); and a
         * count that fell (`openNow < previousOpen` — a review act ELSEWHERE
         * moved a proposal out of `open`, which is not an arrival). Repeated
         * polling with an unchanged count and duplicate signals are both already
         * excluded upstream: `proposalSignal`'s own dedupe (below) means this
         * effect is not even re-entered for either.
         *
         * `n` IS A LOWER BOUND, NOT AN EXACT COUNT, and the sentence says so.
         * `openNow > previousOpen` is sound evidence that AT LEAST one arrival
         * happened (nothing this panel does can raise `open`) — but it is a NET
         * delta over the whole interval between two reads, and an arrival landing
         * beside an unrelated review act ELSEWHERE nets to a smaller rise, or to
         * none at all if the two exactly offset. A same-count `3 -> 3` where one
         * proposal arrived and a different one was reviewed by someone else in
         * the same window is invisible to this mechanism, by construction — see
         * the `net-offset` test, which pins that this panel says nothing false
         * about that case rather than overclaiming a count it cannot know.
         */
        if (isArrivalReload && previousOpen !== null && openNow > previousOpen) {
          const n = openNow - previousOpen;
          arrivalTotalRef.current += n;
          const total = arrivalTotalRef.current;
          // The SPOKEN sentence is per-arrival (this arrival's own delta) so a
          // screen-reader user hears each arrival as it happens, even while the
          // VISIBLE note (below) already reflects an earlier, undismissed one.
          const spoken =
            `At least ${n} ${n === 1 ? 'proposed change' : 'proposed changes'} arrived and ` +
            `${n === 1 ? 'is' : 'are'} ready to review.`;
          // The VISIBLE note is the RUNNING TOTAL since the last Dismiss (M3) —
          // never content, never a field path: `total` and the fixed words below
          // are the only things this can ever say, by construction of what it
          // reads.
          const cumulative =
            `At least ${total} ${total === 1 ? 'proposed change' : 'proposed changes'} arrived ` +
            `and ${total === 1 ? 'is' : 'are'} ready to review.`;
          announce(spoken);
          setArrivalNote(cumulative);
        }
        lastOpenCountRef.current = openNow;
      })
      .catch((err: unknown) => {
        if (!alive || generation !== generationRef.current) return;
        setList({ status: 'error', error: asApiError(err) });
      });

    return () => {
      alive = false;
    };
  }, [experimentId, filter, cursor, order, reloadNonce, announce]);

  const reload = useCallback((silent: boolean) => {
    silentRef.current = silent;
    setReloadNonce((n) => n + 1);
  }, []);

  /*
   * THE CHANGE-FEED HOOK-UP, AND THE TWO PROPERTIES THAT MAKE IT SAFE.
   *
   * A `proposal` entry in the record's change feed says only that a proposal moved —
   * its id and its current state, with no content, by construction. So the response is
   * to RE-READ this list, which is the only thing that can show what moved.
   *
   * (1) IT IS SILENT. `reload(true)` refreshes the window in place; it never blanks
   *     the list, so a half-written corrected value in an open editor is untouched.
   *     `CLAUDE.md` §11 records three banners that promised "your input is kept" beside
   *     a refresh that destroyed it, and a poller wired to a form is the fastest way to
   *     reintroduce that.
   * (2) IT RAISES NO NOTICE OF ITS OWN. `RecordActivityNote` already tells the reader
   *     that something changed elsewhere; a second announcement from here would be two
   *     notices for one fact.
   *
   * KEYED ON THE POSITION AS WELL AS THE IDS. `summariseChanges` reports the set of
   * proposal ids that moved, and one proposal can move twice — created, then reviewed
   * — which would leave an id-only key unchanged and the second move unread. The
   * position moves with every act, so the pair is what distinguishes them.
   *
   * THE POSITION IS `proposalRev`, AND IT USED TO BE `highestRev`. That was wrong in
   * the direction that loses a change rather than the one that costs a read. The feed
   * is ordered `(changed_at_rev, kind, entity_id)` and a page boundary may fall
   * anywhere, so one page can end `[proposal@4, experiment@9]` and the next begin
   * `[proposal@9]`: under `highestRev` both batches key `9:P1`, the key does not
   * change, and P1's SECOND move is never read. `proposalRev` is the furthest position
   * a PROPOSAL entry in the batch actually occupied — `4:P1` then `9:P1` — so the two
   * are distinguishable. It is also strictly less noisy, since it no longer moves for
   * an unrelated run or record change riding in the same page.
   */
  const proposalSignal =
    activity !== null && activity.proposalIds.length > 0
      ? `${activity.proposalRev}:${activity.proposalIds.join(',')}`
      : null;
  const lastSignalRef = useRef<string | null>(null);
  useEffect(() => {
    if (proposalSignal === null || proposalSignal === lastSignalRef.current) return;
    lastSignalRef.current = proposalSignal;
    // Marks the reload this triggers as one that MAY raise an arrival
    // announcement — see `arrivalReloadRef` and the fetch effect that reads it.
    // A duplicate `proposalSignal` never reaches here at all (the guard above),
    // so "repeated polling with no new ids" never sets this ref in the first
    // place, on top of the count-based guard inside the fetch effect.
    arrivalReloadRef.current = true;
    reload(true);
  }, [proposalSignal, reload]);

  /**
   * Turn a refused write into a state a reader can act from.
   *
   * On a 412 it adopts the token the server reported and refreshes SILENTLY, so the
   * counts and states catch up while every open editor, and everything typed into one,
   * stays exactly where it is. On any other failure it changes nothing and returns the
   * refusal's own sentence: this must never claim a recovery it did not make.
   */
  const recoverFromStale = useCallback(
    (err: unknown, action: ApiProposalReviewAction): string => {
      const current = staleWriteCurrentVersion(err);
      if (current === null) return reviewRefusalCopy(err, action);
      setVersion(current);
      reload(true);
      return STALE_REVIEW_COPY;
    },
    [reload],
  );

  /**
   * Run one review act and refresh.
   *
   * THE REFRESH IS NOT A PATCH-IN-PLACE. The response carries the reviewed proposal,
   * but the record's per-state counts and its version have both moved, and splicing
   * the proposal into local state while leaving the counts stale would put two
   * disagreeing numbers on the same screen.
   *
   * NOTHING IS ANNOUNCED BEFORE THE SERVER ANSWERS. The announcement and the refresh
   * both follow the awaited write, so a refusal can never leave a sentence on screen
   * claiming an act that did not happen.
   */
  const review = useCallback(
    async (
      proposal: ApiProposal,
      action: ApiProposalReviewAction,
      opts: { acceptedFrom?: 'candidate' | 'edited'; value?: unknown; reason?: string },
      announced: string,
    ) => {
      if (!version) return;
      setBusyId(proposal.proposal_id);
      setRefusal(null);
      try {
        const written = await api.reviewProposal(experimentId, proposal.proposal_id, {
          experimentVersion: version,
          action,
          ...opts,
        });
        // Adopted from this write's own response rather than left to arrive with the
        // refetch: between the two the held token is one revision stale, and every
        // button on every other card is still live, so a reader acting twice quickly
        // would meet a 412 this component's own bookkeeping manufactured.
        setVersion(written.experiment_version);
        announce(announced);
        reload(true);
      } catch (err: unknown) {
        setRefusal(recoverFromStale(err, action));
        setAnnouncement('');
        /*
         * RETHROWN, so a caller can tell "recorded" from "refused". The editors that
         * hold typed input close themselves only on success; if this resolved on
         * failure, a refusal would close the editor and take the corrected value with
         * it while the banner truthfully said nothing was written.
         */
        throw err;
      } finally {
        setBusyId(null);
      }
    },
    [experimentId, version, reload, recoverFromStale, announce],
  );

  /**
   * The last successfully loaded window, kept across a reload.
   *
   * The live region and the counts must stay MOUNTED to be announced at all, so the
   * toolbar renders off this snapshot while a reload is in flight.
   */
  const lastLoadedRef = useRef<ApiProposalsResponse | null>(null);
  if (list.status === 'data') lastLoadedRef.current = list.loaded;
  const loaded = list.status === 'data' ? list.loaded : lastLoadedRef.current;

  const countLine = useMemo(() => {
    if (!loaded) return '';
    const total = `${loaded.total} ${loaded.total === 1 ? 'proposal' : 'proposals'} on this record`;
    const shown = `Showing ${loaded.returned} of ${total}`;
    return `${shown}${orderClause(order)}${unreadableClause(loaded.unreadable_entries)}`;
  }, [loaded, order]);

  /** The filter options: "All" plus whatever states the SERVER reports. */
  const filterOptions = useMemo(() => {
    const states = loaded?.states ?? [];
    return [{ id: 'all', label: 'All' }, ...states.map((s) => ({ id: s, label: FILTER_LABELS[s] ?? s }))];
  }, [loaded]);

  /**
   * Move the view to a different end of the list, SILENTLY and from the first window.
   *
   * THE CURSOR HAS TO BE DROPPED AND THIS IS NOT TIDINESS. A `next_cursor` belongs to
   * the order it was issued under; the server refuses one from the other direction
   * (`422 cursor_order_mismatch`) rather than answering from the wrong side, so
   * changing `order` while holding a cursor would turn the panel's next read into a
   * refusal. Rewinding to the first window is also what the reader asked for: the
   * whole point of the other direction is what is at the FRONT of it.
   *
   * SILENT, for rule 5 above — changing the order refreshes the list in place and
   * never blanks it, so a half-written corrected value in an open editor survives.
   * The cost is the same one the filter control states: for the duration of the read
   * the counts still describe the previous view.
   */
  const changeOrder = useCallback((next: ApiProposalOrder) => {
    silentRef.current = true;
    setCursor(null);
    setBack([]);
    setOrder(next);
  }, []);

  const offeredActions = useMemo<ApiProposalReviewAction[]>(() => {
    const served = loaded?.review_actions;
    if (!Array.isArray(served)) return [...KNOWN_REVIEW_ACTIONS];
    return served.filter(isKnownAction);
  }, [loaded]);

  return (
    <div className="proposals-browser">
      <div className="proposals-toolbar">
        <div className="proposals-control">
          <label className="proposals-control-label" htmlFor={filterId}>
            Show
          </label>
          <select
            id={filterId}
            className="proposals-filter"
            value={filter}
            onChange={(e) => {
              /* SILENT, so changing the filter does not blank the list and take an
                 open editor's text with it. The cost, stated because it is real: for
                 the duration of the read the counts still describe the previous
                 selection. A visibly transient number is a better trade than a
                 silently destroyed value. */
              silentRef.current = true;
              setCursor(null);
              setBack([]);
              setFilter(e.target.value);
            }}
          >
            {filterOptions.map((f) => (
              <option key={f.id} value={f.id}>
                {f.label}
                {loaded && f.id !== 'all'
                  ? ` (${(loaded.by_state as Record<string, number>)[f.id] ?? 0})`
                  : ''}
              </option>
            ))}
          </select>
        </div>
        {/*
          THE ORDER CONTROL — a visible, keyboard-reachable, labelled `select`, sitting
          beside the state filter because it is the same kind of thing: it changes what
          this window shows and changes nothing on the record.

          IT RAISES NO ANNOUNCEMENT OF ITS OWN. The count line beside it already
          carries the order (`orderClause`) and is already `aria-live="polite"`, so
          changing this select changes that sentence and it is spoken once. A second
          region for the same fact would say it twice, which is the defect the arrival
          note's own comment records avoiding.
        */}
        <div className="proposals-control">
          <label className="proposals-control-label" htmlFor={orderId}>
            Order
          </label>
          <select
            id={orderId}
            className="proposals-order"
            value={order}
            onChange={(e) => changeOrder(e.target.value as ApiProposalOrder)}
          >
            <option value="oldest_first">{ORDER_LABELS.oldest_first}</option>
            <option value="newest_first">{ORDER_LABELS.newest_first}</option>
          </select>
        </div>
        {/* Mounted in every state and BLANKED rather than left stale while a reload is
            in flight: a live region remounted with its content is never announced, and
            holding the previous window's numbers through a read is worse than none. */}
        <p className="proposals-count" aria-live="polite" aria-atomic="true">
          {list.status === 'loading' ? '' : countLine}
        </p>
      </div>

      {/* The ACT announcement, separate from the counts. A screen-reader user who
          activates Withdraw needs to hear that the proposal was withdrawn AND KEPT;
          the count line cannot carry that, because it reads the same either way. */}
      <p className="sr-only" role="status" aria-live="polite">
        {announcement}
      </p>

      {/*
        THE VISIBLE HALF OF AN ARRIVAL, for a reader who is not using a screen
        reader — the sr-only region above already spoke this same sentence once.
        No `role`/`aria-live` here: giving it one would announce the sentence a
        second time, from a second region, for one event.

        NO ANIMATION, so `prefers-reduced-motion` needs nothing further — there is
        nothing here to reduce. It never steals focus: it appears in place, and
        Dismiss is an ordinary tab stop rather than one this component moves focus
        to. Layout is flex/wrap only, no fixed pixel width, so it does not overflow
        a narrow viewport — matching the toolbar it sits beside.
      */}
      {arrivalNote !== null && (
        <div className="proposals-arrival-note" role="note">
          <span className="proposals-arrival-note-text">{arrivalNote}</span>
          {/*
            THE ACTION THAT MAKES THE SENTENCE ACTIONABLE, and without it the sentence
            was a dead end on exactly the records it was written for. The arrival is
            detected from `by_state.open`, which is the WHOLE record — deliberately, so
            it is insensitive to the window — and the window it is announced into is
            the OLDEST 50. On a record already holding that many, the proposal this
            note is about is not on screen and no amount of re-reading puts it there.

            IT DOES TWO THINGS AND ITS LABEL NAMES BOTH. The order moves to
            `newest_first`, which is what puts the arrival in the first window; and the
            filter moves to `open`, which is the state the sentence actually counted —
            a reader sitting on `Accepted` would otherwise activate this and be shown a
            window with none of the arrivals in it. Discarding a reader's filter
            silently is the quiet side effect `EmptyProposals`' two-handler split
            exists to avoid, so this control declares it in its own label rather than
            doing it quietly. Both controls stay where they are and either can be put
            straight back.

            IT ANNOUNCES NOTHING ITSELF. The count line carries both the order and
            (through the filter's own `select`) the selection, and it is already a live
            region; the sr-only region above has already spoken this arrival once. A
            third utterance for one event is the defect this note's own comment records
            avoiding.
          */}
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => {
              // Silent, and the cursor is dropped: see `changeOrder`. The filter is
              // set through the same silent path for the reason the filter control
              // states — a loud reload would unmount every open editor.
              changeOrder('newest_first');
              setFilter('open');
              // THE RUNNING TOTAL IS CLEARED HERE FOR THE SAME REASON DISMISS
              // CLEARS IT, and the reason is worth stating because the two
              // controls do opposite things with the same reset. `arrivalTotalRef`
              // accumulates arrivals the reader has not ACKNOWLEDGED — not
              // arrivals they have not reviewed; Dismiss's own comment below is
              // explicit that it marks nothing reviewed, and neither does this.
              // Being taken to the window that holds them is an acknowledgement,
              // so leaving the total standing would make the NEXT arrival say
              // "at least 3" while counting two the reader was already shown.
              arrivalTotalRef.current = 0;
              setArrivalNote(null);
            }}
          >
            Show Open, Newest First
          </button>
          {/*
            Dismiss clears the RUNNING TOTAL (M3) — and ONLY the running total.
            It does not mark anything reviewed and it never touches `proposals`,
            `filter`, `cursor` or triggers a reload: the arrived proposals may
            still be sitting unreviewed after this click, exactly as before it.
          */}
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => {
              arrivalTotalRef.current = 0;
              setArrivalNote(null);
            }}
          >
            Dismiss
          </button>
        </div>
      )}

      {refusal && (
        <div className="proposals-error" role="alert">
          <span className="proposals-error-text">{refusal}</span>
          {/* SILENT — the loud reload would unmount every card and destroy the
              corrected value the reader was offered this control to recover. */}
          <button type="button" className="btn btn-secondary" onClick={() => reload(true)}>
            Reload This Section
          </button>
        </div>
      )}

      {list.status === 'loading' && (
        <LoadingPanel label="Loading this record's ingestion proposals…" />
      )}
      {list.status === 'error' && (
        <BackendDown error={list.error} onRetry={() => reload(false)} />
      )}
      {list.status === 'data' &&
        (list.loaded.proposals.length === 0 ? (
          <EmptyProposals
            total={list.loaded.total}
            unreadable={list.loaded.unreadable_entries}
            filtering={filter !== 'all'}
            paging={cursor !== null}
            /*
             * TWO HANDLERS, NOT ONE, AND THE FIRST VERSION HAD ONE. A single handler
             * meant "Back to the First Page" also did `setFilter('all')` — a control
             * that promises paging silently discarding the reader's filter, which is
             * the class of quiet side effect this panel is otherwise careful about.
             * Rewinding the window and clearing the filter are different acts and each
             * control now does only its own.
             */
            onRewind={() => {
              silentRef.current = true;
              setCursor(null);
              setBack([]);
            }}
            onClearFilter={() => {
              silentRef.current = true;
              setCursor(null);
              setBack([]);
              setFilter('all');
            }}
          />
        ) : (
          <>
            <ul className="proposals-list">
              {list.loaded.proposals.map((proposal) => (
                <li key={proposal.proposal_id}>
                  <ProposalCard
                    experimentId={experimentId}
                    proposal={proposal}
                    served={{
                      targetFieldPaths: list.loaded.target_field_paths,
                      recordScopedTargetFieldPaths:
                        list.loaded.record_scoped_target_field_paths,
                    }}
                    offeredActions={offeredActions}
                    acceptedFromValues={list.loaded.accepted_from_values}
                    busy={busyId === proposal.proposal_id || version === null}
                    onReview={review}
                  />
                </li>
              ))}
            </ul>
            <Pager
              hasMore={list.loaded.has_more}
              nextCursor={list.loaded.next_cursor}
              canGoBack={back.length > 0}
              onNext={(next) => {
                silentRef.current = true;
                setBack((stack) => [...stack, cursor]);
                setCursor(next);
              }}
              onPrevious={() => {
                silentRef.current = true;
                setBack((stack) => {
                  setCursor(stack.length > 0 ? stack[stack.length - 1] : null);
                  return stack.slice(0, -1);
                });
              }}
            />
          </>
        ))}
    </div>
  );
}

/**
 * Paging over a BOUNDED list.
 *
 * The next window is the server's `next_cursor`, never an offset this client computed.
 * "There are more" is `has_more`, never `returned === limit`, which would be a second
 * definition of the same fact and would go wrong at exactly the boundary.
 */
function Pager({
  hasMore,
  nextCursor,
  canGoBack,
  onNext,
  onPrevious,
}: {
  hasMore: boolean;
  nextCursor: string | null;
  canGoBack: boolean;
  onNext: (cursor: string) => void;
  onPrevious: () => void;
}) {
  if (!hasMore && !canGoBack) return null;
  return (
    <div className="proposals-pager">
      <button
        type="button"
        className="btn btn-secondary"
        disabled={!canGoBack}
        onClick={onPrevious}
      >
        Previous Page
      </button>
      <button
        type="button"
        className="btn btn-secondary"
        disabled={!hasMore || nextCursor === null}
        onClick={() => nextCursor !== null && onNext(nextCursor)}
      >
        Next Page
      </button>
      {hasMore && (
        <span className="proposals-pager-note">
          This record holds more proposals than this window shows.
        </span>
      )}
    </div>
  );
}

/**
 * The three empty states are kept apart.
 *
 * "This record has no proposals", "nothing matches the filter you chose" and "this
 * window is past the end" are different facts, and collapsing them lets a filtered or
 * paged view read as an empty record.
 *
 * ALL THREE CARRY THE UNREADABLE DISCLOSURE, because `total` counts only the entries
 * this build could turn into proposals, and an empty state is exactly where a reader
 * stops looking.
 */
function EmptyProposals({
  total,
  unreadable,
  filtering,
  paging,
  onRewind,
  onClearFilter,
}: {
  total: number;
  unreadable: number;
  filtering: boolean;
  paging: boolean;
  /** Rewind to the first window. Leaves the state filter exactly as it is. */
  onRewind: () => void;
  /** Clear the state filter (and rewind, since the windows are the filter's). */
  onClearFilter: () => void;
}) {
  const disclosure = unreadableClause(unreadable);
  if (paging) {
    return (
      <div className="proposals-empty">
        <p>
          This window holds no proposals. This record holds {total}{' '}
          {total === 1 ? 'proposal' : 'proposals'} in total{disclosure}.
          {filtering && ' The state filter is still applied.'}
        </p>
        <button type="button" className="btn btn-secondary" onClick={onRewind}>
          Back to the First Page
        </button>
        {filtering && (
          <button type="button" className="btn btn-secondary" onClick={onClearFilter}>
            Show All Proposals
          </button>
        )}
      </div>
    );
  }
  if (filtering) {
    return (
      <div className="proposals-empty">
        <p>
          No proposals are in this state. This record holds {total}{' '}
          {total === 1 ? 'proposal' : 'proposals'} in total{disclosure}.
        </p>
        <button type="button" className="btn btn-secondary" onClick={onClearFilter}>
          Show All Proposals
        </button>
      </div>
    );
  }
  return (
    <div className="proposals-empty">
      <p>
        No ingestion proposals on this record{disclosure}. Nothing in this build creates
        one: the transcript reader stores what it reads as unmapped notes, and no other
        pipeline proposes a value. Proposals appear here only when something proposes
        one, and nothing is ever inferred from this record's contents.
      </p>
    </div>
  );
}

/** Which editor, if any, is open on a card. Only one at a time. */
type OpenEditor = null | { kind: 'edited' } | { kind: 'reason'; action: 'reject' | 'supersede' | 'withdraw' };

function ProposalCard({
  experimentId,
  proposal,
  served,
  offeredActions,
  acceptedFromValues,
  busy,
  onReview,
}: {
  experimentId: string;
  proposal: ApiProposal;
  served: { targetFieldPaths?: string[]; recordScopedTargetFieldPaths?: string[] };
  offeredActions: ApiProposalReviewAction[];
  acceptedFromValues: string[];
  busy: boolean;
  onReview: (
    proposal: ApiProposal,
    action: ApiProposalReviewAction,
    opts: { acceptedFrom?: 'candidate' | 'edited'; value?: unknown; reason?: string },
    announce: string,
  ) => Promise<void>;
}) {
  const [editor, setEditor] = useState<OpenEditor>(null);
  /**
   * The corrected value, as JSON text. Held here rather than lifted, so a SILENT
   * refresh of the list — which re-renders this card with a fresh `proposal` prop but
   * does not unmount it — leaves what is being typed exactly where it is.
   */
  const [editedText, setEditedText] = useState('');
  const [editedError, setEditedError] = useState<string | null>(null);
  const [reason, setReason] = useState('');
  const [historyOpen, setHistoryOpen] = useState(false);

  const editorId = useId();
  const isOpen = proposal.state === 'open';
  const unavailable = acceptUnavailableReason(proposal, served);
  /*
   * THE TWO ACCEPT HALVES ARE GATED INDEPENDENTLY, AND THEY WERE NOT.
   *
   * `canEditAccept` used to be `canAccept && …includes('edited')`, so the correction
   * path was reachable only when the server ALSO offered `candidate`. Two consequences,
   * one a defect and one a hole in the tests. The defect: a server serving
   * `accepted_from_values: ['edited']` — "the proposed value must be corrected before
   * it is written" — would get NO accept control at all, which is the opposite of what
   * it asked for. The hole: mutating `includes('candidate')` to `true` SURVIVED all 47
   * tests, because only the `edited` half was pinned and it was pinned through this
   * conjunction. Both halves are now separate and both are pinned.
   */
  const acceptPossible =
    isOpen && offeredActions.includes('accept') && unavailable === null;
  const canAccept = acceptPossible && acceptedFromValues.includes('candidate');
  const canEditAccept = acceptPossible && acceptedFromValues.includes('edited');

  async function run(
    action: ApiProposalReviewAction,
    opts: { acceptedFrom?: 'candidate' | 'edited'; value?: unknown; reason?: string },
    announce: string,
    onDone?: () => void,
  ) {
    try {
      await onReview(proposal, action, opts, announce);
      onDone?.();
    } catch {
      /* The panel renders the refusal and keeps every editor open — see `review`. */
    }
  }

  return (
    /*
     * THE CARD CARRIES ITS OWN ACCESSIBLE NAME, so a reader moving by region hears
     * WHICH proposal they are in. Without it every card was an unnamed `article` and
     * each contributed an identical `<h3>Proposed value</h3>`, so a heading list read
     * as N copies of the same entry with nothing to tell them apart. The name is the
     * field path and the state — the two facts that distinguish one card from the
     * next — and not the proposal id, which is an opaque token nobody can act on.
     */
    <article
      className="proposal-card"
      data-state={proposal.state}
      aria-label={`Proposal for ${proposal.target_field_path} — ${stateLabel(proposal.state)}`}
    >
      <header className="proposal-card-head">
        <span className="proposal-state">{stateLabel(proposal.state)}</span>
        <span className="proposal-path mono">{proposal.target_field_path}</span>
        <span className="proposal-scope">
          {proposal.run_id === null ? 'On the record' : `On run ${proposal.run_id}`}
        </span>
        <span className="proposal-when">Proposed {proposal.proposed_utc}</span>
      </header>

      {/* THE CLAIM THIS CARD MUST NOT LET A READER MISS, and it is made in every
          state including `accepted` — because `is_field_value` is false there too. */}
      <p className="proposal-nature">
        A suggestion about this field. It is not the field&rsquo;s value and not evidence
        for it.
      </p>

      <div className="proposal-value">
        <h3 className="proposal-value-label">Proposed value</h3>
        <pre className="proposal-value-body">{renderValue(proposal.proposed_value)}</pre>
      </div>

      <p className="proposal-rule">
        <span className="proposal-rule-label">Rule that produced it: </span>
        {proposal.rule}
      </p>

      <p className="proposal-origin">
        <span className="proposal-origin-label">From: </span>
        {proposal.source} · note <span className="mono">{proposal.note_id}</span>
      </p>

      {proposal.excerpt !== null ? (
        <blockquote className="proposal-excerpt">{proposal.excerpt}</blockquote>
      ) : proposal.start_char !== null ? (
        <p className="proposal-excerpt-absent">
          This proposal records a span of the note, but the words at it could not be read
          back. The note itself is unchanged and still listed.
        </p>
      ) : null}

      <TargetState proposal={proposal} acceptOffered={canAccept || canEditAccept} />

      <CurrentValue experimentId={experimentId} proposal={proposal} />

      {proposal.state === 'accepted' && <AcceptanceRecord proposal={proposal} />}

      {isOpen && unavailable !== null && (
        <p className="proposal-unavailable" role="note">
          <span className="proposal-unavailable-label">Cannot be accepted: </span>
          {unavailable}
        </p>
      )}

      {isOpen ? (
        <>
          <div className="proposal-actions">
            {canAccept && (
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy}
                onClick={() =>
                  run(
                    'accept',
                    { acceptedFrom: 'candidate' },
                    `The proposed value for ${proposal.target_field_path} was accepted as it ` +
                      'stands and written to the record.',
                  )
                }
              >
                {ACTION_LABELS.accept}
              </button>
            )}
            {canEditAccept && (
              <button
                type="button"
                className="btn btn-secondary"
                aria-expanded={editor?.kind === 'edited'}
                aria-controls={editor?.kind === 'edited' ? `${editorId}-edited` : undefined}
                disabled={busy}
                onClick={() => {
                  setEditedError(null);
                  setEditor((open) => {
                    if (open?.kind === 'edited') return null;
                    // Prefilled ONCE, and only when the box is empty, so re-opening
                    // never overwrites what is already being typed.
                    setEditedText((text) => (text === '' ? jsonText(proposal.proposed_value) : text));
                    return { kind: 'edited' };
                  });
                }}
              >
                Correct the Value, Then Accept
              </button>
            )}
            {offeredActions
              .filter((action): action is 'reject' | 'supersede' | 'withdraw' => action !== 'accept')
              .map((action) => (
                <button
                  key={action}
                  type="button"
                  className="btn btn-secondary"
                  aria-expanded={editor?.kind === 'reason' && editor.action === action}
                  aria-controls={
                    editor?.kind === 'reason' && editor.action === action
                      ? `${editorId}-reason`
                      : undefined
                  }
                  disabled={busy}
                  onClick={() =>
                    setEditor((open) =>
                      open?.kind === 'reason' && open.action === action
                        ? null
                        : { kind: 'reason', action },
                    )
                  }
                >
                  {ACTION_LABELS[action]}…
                </button>
              ))}
          </div>

          {editor?.kind === 'edited' && (
            <div className="proposal-form" id={`${editorId}-edited`}>
              <label className="proposal-form-label" htmlFor={`${editorId}-edited-input`}>
                The corrected value, as JSON
              </label>
              <textarea
                id={`${editorId}-edited-input`}
                className="proposal-form-input mono"
                rows={5}
                value={editedText}
                onChange={(e) => {
                  setEditedText(e.target.value);
                  setEditedError(null);
                }}
              />
              <p className="proposal-form-hint">
                Entered as JSON so the type is never guessed: a text value is quoted, for
                example <span className="mono">&quot;CuO&quot;</span>. Accepting this way
                records that the proposed value was WRONG and that this is the corrected
                one — a different claim from accepting it as it stands, and the record
                keeps both apart.
              </p>
              {editedError && (
                <p className="proposal-form-error" role="alert">
                  {editedError}
                </p>
              )}
              <div className="proposal-form-actions">
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy}
                  onClick={() => {
                    let parsed: unknown;
                    try {
                      parsed = JSON.parse(editedText) as unknown;
                    } catch {
                      setEditedError(
                        'That is not valid JSON, so it was not sent and nothing was written. ' +
                          'A text value needs quotes around it.',
                      );
                      return;
                    }
                    if (parsed === null) {
                      setEditedError(
                        'A null would CLEAR the field, and clearing a confirmed value is a ' +
                          'different act with its own questions. It was not sent.',
                      );
                      return;
                    }
                    void run(
                      'accept',
                      { acceptedFrom: 'edited', value: parsed },
                      `The corrected value for ${proposal.target_field_path} was accepted ` +
                        'and written to the record.',
                      () => {
                        setEditor(null);
                        setEditedText('');
                      },
                    );
                  }}
                >
                  Accept the Corrected Value
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={busy}
                  onClick={() => setEditor(null)}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {editor?.kind === 'reason' && (
            <div className="proposal-form" id={`${editorId}-reason`}>
              <p className="proposal-form-meaning">{ACTION_MEANINGS[editor.action]}</p>
              <label className="proposal-form-label" htmlFor={`${editorId}-reason-input`}>
                Reason (optional)
              </label>
              <input
                id={`${editorId}-reason-input`}
                className="proposal-form-input"
                type="text"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
              <p className="proposal-form-hint">
                Stored only if you write one. Nothing is composed on your behalf, and a
                blank is left absent rather than stored as an empty reason.
              </p>
              <div className="proposal-form-actions">
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy}
                  onClick={() => {
                    const action = editor.action;
                    void run(
                      action,
                      { reason },
                      `The proposal for ${proposal.target_field_path} was ${
                        action === 'reject'
                          ? 'rejected'
                          : action === 'supersede'
                            ? 'superseded'
                            : 'withdrawn'
                      } and kept on the record.`,
                      () => {
                        setEditor(null);
                        setReason('');
                      },
                    );
                  }}
                >
                  Confirm {ACTION_LABELS[editor.action]}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={busy}
                  onClick={() => setEditor(null)}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* THE PENDING PATH IS TAKING NO ACTION, and it is said rather than left to
              be inferred. There is no "defer" act in this contract, and inventing one
              would be a state the record cannot store. */}
          <p className="proposal-pending-note">
            Leaving this proposal alone leaves it awaiting judgement. There is no
            &ldquo;decide later&rdquo; act to record — taking no action is that.
          </p>
        </>
      ) : (
        <p className="proposal-closed-note">
          This proposal has been reviewed. Every recorded judgement stays exactly as it
          was made, so it cannot be reviewed again — a later view is a new proposal.
        </p>
      )}

      <div className="proposal-history">
        <button
          type="button"
          className="proposal-history-toggle"
          aria-expanded={historyOpen}
          /* Set only while the list exists — `aria-controls` naming an id that is not
             in the document is a dangling reference, and the two editor toggles above
             already guard theirs the same way. */
          aria-controls={historyOpen ? `${editorId}-history` : undefined}
          onClick={() => setHistoryOpen((open) => !open)}
        >
          {historyOpen ? 'Hide' : 'Show'} history ({proposal.history.length}{' '}
          {proposal.history.length === 1 ? 'act' : 'acts'})
        </button>
        {historyOpen && (
          <ol className="proposal-history-list" id={`${editorId}-history`}>
            {proposal.history.map((entry, index) => (
              <li key={`${entry.action}-${entry.at}-${index}`}>
                <span className="proposal-history-act">{entry.action}</span>{' '}
                <span className="proposal-history-when">{entry.at}</span>
                {entry.from_state !== null && (
                  <span className="proposal-history-move">
                    {' '}
                    · from {entry.from_state} to {entry.to_state}
                  </span>
                )}
                {entry.accepted_from !== null && (
                  <span className="proposal-history-move">
                    {' '}
                    · accepted as {entry.accepted_from}
                  </span>
                )}
                {entry.reason !== null && (
                  <span className="proposal-history-reason"> · reason: {entry.reason}</span>
                )}
                <span className="proposal-history-actor">
                  {' '}
                  ·{' '}
                  {entry.actor_subject !== null
                    ? `by ${entry.actor_subject}`
                    : 'recorded without an attributed actor'}
                </span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </article>
  );
}

/**
 * What the server says about the target, in the server's own three-valued terms.
 *
 * `null` IS NOT `false`, AND EACH GETS ITS OWN SENTENCE. `false` says the target has
 * not moved; `true` says it has; `null` says the question could not be answered, which
 * happens when the run this proposal names has been removed. A single boolean sentence
 * covering `false` and `null` would be the comfortable one of the two, and it would be
 * wrong exactly when a scientist most needs it to be right.
 *
 * EVERY SENTENCE IS QUALIFIED "AS OF THIS READ". Both values are derived by
 * re-digesting the target when the list was fetched, and nothing here re-checks them.
 */
function TargetState({
  proposal,
  acceptOffered,
}: {
  proposal: ApiProposal;
  /**
   * Whether an Accept control is on this card.
   *
   * IT IS HERE ONLY SO THE COPY CANNOT CONTRADICT THE CONTROL BESIDE IT. The stale
   * sentence said "accepting is refused while that is so" directly above an enabled
   * Accept button, which reads as a defect in one of the two. It is not: the fail-open
   * is deliberate (see `acceptUnavailableReason`), and what was missing was the
   * sentence saying so.
   */
  acceptOffered: boolean;
}) {
  const stale = proposal.target_stale;
  return (
    <p className="proposal-target-state">
      {stale === null
        ? proposal.run_id !== null
          ? 'Whether the value at this field path has changed CANNOT BE ANSWERED: the run this proposal names is no longer on this record. That is not the same as “nothing changed”.'
          : 'Whether the value at this field path has changed CANNOT BE ANSWERED: this record’s content at it could not be read. That is not the same as “nothing changed”.'
        : stale
          ? 'As of this read, the value at this field path had CHANGED since this proposal was made, and accepting is refused while that is so — nothing would be written.' +
            (acceptOffered
              ? ' Accept is still offered because this was read a moment ago and the value at the target can move back; the server decides, and it says so if it refuses.'
              : '')
          : 'As of this read, the value at this field path was unchanged since this proposal was made.'}
    </p>
  );
}

/**
 * What an acceptance actually did, and whether it still stands.
 *
 * `still_current` IS THE POINT OF THIS BLOCK. `accepted` is terminal, and the value it
 * wrote can be corrected afterwards through the ordinary write routes — so without
 * this an accepted proposal reads as a standing claim about the record's present
 * content. `null` again gets its own sentence and claims nothing.
 *
 * THE `null` SENTENCE BRANCHES ON `run_id`, AND THE FIRST VERSION DID NOT — it stated
 * "the run it names is no longer on this record" unconditionally. A RECORD-scoped
 * accepted proposal (`run_id: null`) with `still_current: null` is reachable:
 * `applied_target_digest` is `str | None` on the model, and `_current_target_digest`
 * answers `null` whenever the target could not be digested, not only when a run was
 * removed. So the branch asserted a run that may never have existed. `TargetState`
 * above already had the two-branch shape; this now mirrors it, which is the point —
 * one derived read, two renderers, and they must not disagree about what `null` means.
 */
function AcceptanceRecord({ proposal }: { proposal: ApiProposal }) {
  const via = proposal.applied_via;
  const by = proposal.accepted_by;
  return (
    <div className="proposal-acceptance">
      <p className="proposal-acceptance-line">
        {proposal.accepted_from === 'edited'
          ? 'Accepted with a CORRECTED value — the proposed one was wrong.'
          : 'Accepted as proposed.'}{' '}
        {via !== null && `The value was written through ${APPLIED_VIA_LABELS[via] ?? via}.`}
      </p>
      <div className="proposal-value">
        <h3 className="proposal-value-label">Value that was written</h3>
        <pre className="proposal-value-body">{renderValue(proposal.accepted_value)}</pre>
      </div>
      <p className="proposal-acceptance-line">
        {proposal.still_current === null
          ? proposal.run_id !== null
            ? 'Whether the record still holds what this acceptance wrote CANNOT BE ANSWERED: the run this proposal names is no longer on this record. That is not the same as “it still holds it”.'
            : 'Whether the record still holds what this acceptance wrote CANNOT BE ANSWERED: the content at its field path could not be read back. That is not the same as “it still holds it”.'
          : proposal.still_current
            ? 'As of this read, the record still held what this acceptance wrote.'
            : 'As of this read, the record NO LONGER held what this acceptance wrote — it has been changed since.'}
      </p>
      <p className="proposal-acceptance-line">
        {by === null
          ? 'No accept act is recorded against this proposal.'
          : by.subject !== null
            ? `Accepted by ${by.subject} at ${by.at}.`
            : `Accepted at ${by.at}, recorded without an attributed actor — no name is substituted.`}
      </p>
    </div>
  );
}

/** What the on-demand current-value read is doing, or what it found. */
type CurrentValueState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; error: ApiError }
  | { status: 'data'; label: string; value: unknown; present: boolean };

/**
 * WHAT THE RECORD HOLDS AT THIS PATH NOW — a SEPARATE, EXPLICIT read.
 *
 * WHY IT IS NOT PART OF THE PROPOSAL. The proposals list carries a DIGEST of the
 * target (`current_target_digest`) and not its value, so this surface has no truthful
 * side-by-side to draw from that payload. It could have shown the proposed value under
 * a heading implying it was the record's — the exact defect this repository keeps
 * shipping — or it could ask. It asks.
 *
 * WHY IT IS ON DEMAND. One read per card on mount would be N requests for a panel
 * whose ordinary state is empty. Pressing the button is a person asking a question,
 * and the answer is labelled with WHICH route answered it and that it was read then,
 * not with the proposal.
 *
 * THE TWO ROUTES ARE NOT INTERCHANGEABLE, and using the wrong one would be a
 * fabrication rather than an inaccuracy. A record-scoped proposal's target is the
 * RECORD's own draft field; a run-scoped proposal's target is that RUN's — its own
 * value, its override, or what it inherits — and reading the record's draft for a run
 * would report a value that run may not have.
 */
function CurrentValue({
  experimentId,
  proposal,
}: {
  experimentId: string;
  proposal: ApiProposal;
}) {
  const [state, setState] = useState<CurrentValueState>({ status: 'idle' });
  const regionId = useId();

  const look = useCallback(async () => {
    setState({ status: 'loading' });
    try {
      if (proposal.run_id === null) {
        const draft = await api.getDraft(experimentId);
        const row = draft.groups
          .flatMap((group) => group.fields)
          .find((field) => field.path === proposal.target_field_path);
        if (row === undefined) {
          setState({
            status: 'data',
            label: 'This record’s draft does not describe this field path.',
            value: undefined,
            present: false,
          });
          return;
        }
        setState({
          status: 'data',
          label: "The record's own draft, read just now",
          value: row.value,
          // `present === false` is the group skeleton — the SHAPE of a value this
          // record does not have. `undefined` is a server that did not say, which is
          // treated the same way as a missing value rather than as a present one.
          present: row.present === true,
        });
        return;
      }
      const { run } = await api.getRun(experimentId, proposal.run_id);
      /*
       * THE RESOLUTION IS CONSULTED FIRST, AND THE FIRST VERSION HAD IT BACKWARDS.
       *
       * It read `run.fields[path]` and, if present, reported it as "this run's own
       * value" without consulting `inherited` at all. `workspace.resolved_run_draft`
       * composes a run in four layers and says the ordering IS the rule: layer 1 is
       * the run's own draft, layer 2 is every experiment-level address through
       * `resolve_inherited`, and *"layer 2 is applied ON TOP of layer 1, so if a run's
       * own draft somehow carries an experiment-level field directly, the resolution
       * wins"*. For the 17 run-applied targets that are `field:` overrides, reading
       * the run's own map first therefore reported the LOSING value as the current
       * one — a specific, checkable falsehood on the one control whose entire job is
       * to say what the record holds.
       *
       * `payload` is the EFFECTIVE value in both resolved states — `resolve_inherited`
       * sets it to a copy of the experiment's payload when there is no override and to
       * the override's payload when there is — and `resolved_run_draft` SKIPS a
       * resolution whose `payload is None`. So the run's own field survives in exactly
       * one case, `payload == null`, which is what the fall-through below covers.
       */
      const resolved = run.inherited?.[`field:${proposal.target_field_path}`];
      const resolvedPayload = (resolved?.payload ?? null) as { value?: unknown } | null;
      if (resolved !== undefined && resolvedPayload !== null) {
        setState({
          status: 'data',
          label:
            resolved.state === 'overridden'
              ? "This run's override of the record's value, read just now"
              : 'Inherited from the record, read just now',
          value: resolvedPayload.value,
          present: true,
        });
        return;
      }
      const own = run.fields?.[proposal.target_field_path];
      if (own !== undefined) {
        setState({
          status: 'data',
          label: "This run's own value, read just now",
          value: own.value,
          present: true,
        });
        return;
      }
      setState({
        status: 'data',
        label:
          resolved === undefined
            ? "This run's response does not describe this field path."
            : 'Neither this run nor the record holds a value at this field path.',
        value: undefined,
        present: false,
      });
    } catch (err: unknown) {
      setState({ status: 'error', error: asApiError(err) });
    }
  }, [experimentId, proposal.run_id, proposal.target_field_path]);

  return (
    <div className="proposal-current">
      <button
        type="button"
        className="btn btn-secondary proposal-current-button"
        aria-controls={regionId}
        aria-expanded={state.status !== 'idle'}
        onClick={() => void look()}
      >
        {state.status === 'idle' ? 'Show What the Record Holds Now' : 'Read It Again'}
      </button>
      <div id={regionId} className="proposal-current-body" aria-live="polite">
        {state.status === 'loading' && <span>Reading the current value…</span>}
        {state.status === 'error' && (
          <span>
            The current value could not be read ({state.error.message}). Nothing about this
            proposal changed.
          </span>
        )}
        {state.status === 'data' && (
          <>
            <p className="proposal-current-label">{state.label}</p>
            {state.present ? (
              <pre className="proposal-value-body">{renderValue(state.value)}</pre>
            ) : (
              <p className="proposal-current-absent">
                No value is stored at this field path.
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
