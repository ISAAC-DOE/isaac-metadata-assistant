/*
 * P29.4 — ONE shared authoritative record-session state for a single record.
 *
 * WHY THIS EXISTS (and why it is NOT a new store): before P29.4 the assistant
 * (P29.1 session + P29.3 agent) and the manual workflow UI each read the record
 * independently — different fetches, different notions of "the current revision".
 * They could disagree on which version is live, and a staged assistant proposal
 * could survive a manual edit it no longer matched. This hook is the SMALLEST
 * sufficient owner that removes that gap: a per-record-route hook that COMPOSES
 * the pieces that already exist — the screen's existing bundle fetch (the single
 * source of `detail`, so there is NO second record cache), exactly ONE
 * `useRecordSync` poller (P27.6), the P29.1 ephemeral session, and the P29.3
 * AgentContext — behind one authoritative `version`/`recordRev`.
 *
 * It owns, for one record id:
 *   - the authoritative `version` (the ETag/If-Match token) and `recordRev`,
 *     taken verbatim from the screen's already-fetched `detail` (never re-fetched
 *     here — no duplicate record cache);
 *   - the derived P29.3 `AgentContext` (detail.workflow + evidence-classification
 *     + pending + version + rev), fetched from the two additive AgentContext
 *     inputs the screen bundle may not carry — the pending half as a BOUNDED
 *     PREFIX, never the complete list (see `AGENT_CONTEXT_PENDING_WINDOW`, which
 *     carries the measurement and the reason it could not be bounded earlier);
 *   - the P29.1 `session` snapshot (messages + the single staged proposal);
 *   - exactly ONE `useRecordSync` poller (screens no longer mount their own);
 *   - `refresh()`, a `conflict` flag (the record moved under the current view),
 *     an agent-context `degraded` flag, and the poller's own `syncDegraded`.
 *
 * On a poll change signal it (1) marks any staged proposal grounded in the OLD
 * revision STALE via `invalidateStaleProposals`, so a stale suggestion can never
 * be silently confirmed; (2) refreshes the session snapshot so the stale flag is
 * visible; (3) raises `conflict`; and (4) delegates to the screen's `onChange`
 * (which refetches its bundle or raises its own input-preserving banner). An
 * out-of-order/aborted extras fetch for a previous record can never clobber the
 * currently-selected one (the `currentRef` stale-guard pattern from useRecordSync).
 *
 * MANUAL-FIRST: if the AgentContext inputs fail to load, `degraded` is raised and
 * the AgentContext refuses dataset-specific intents — but this hook NEVER blocks
 * the manual workflow. The screen's own bundle drives fields/evidence/export.
 *
 * Truth-plane-free: this hook fetches only read endpoints and never validates,
 * exports, or writes; the only write path remains P29.3 `confirmProposal`.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from './api';
import { UNREADABLE_BLOCKER_LABEL, isAnswerablePendingItem } from './adapt';
import { useRecordSync } from './useRecordSync';
import { useChangeFeed } from './useChangeFeed';
import { isCaughtUp, summariseChanges, type RecordChangeSummary } from './recordChanges';
import {
  invalidateStaleProposals,
  loadSession,
  type Msg,
  type Proposal as SessionProposal,
} from './assistantSession';
import type {
  AgentContext,
  EvidenceView,
  PendingItem,
  WorkflowStep,
} from './assistantAgent';
import type {
  ApiChangeEntry,
  ApiEvidenceClassification,
  ApiExperimentDetail,
  ApiPendingItem,
} from './types';

/**
 * HOW MANY OPEN QUESTIONS THE AGENTCONTEXT ASKS FOR.
 *
 * THIS READ WAS THE LAST UNBOUNDED PIECE OF THE COMPLETION FLOW, and it was not a
 * per-screen mount cost. The effect below is keyed on `version`, which `GuidedCompletion`
 * adopts from every accepted answer, so an unbounded `api.getPending(id)` fired again
 * after EVERY SUBMISSION — on the very screen the pending bound was written for. Measured
 * at 1,000 runs, per accepted answer:
 *
 *   originally             POST 1,773,294 B + GET 1,772,692 B  =  3,545,986 B
 *   mutation bound only    POST    31,968 B + GET 1,772,692 B  =  1,804,660 B   (49.1%)
 *   with this change       POST    31,968 B + GET    29,590 B  =     61,558 B   (98.3%)
 *
 * The bounded figure is measured rather than divided down, and it is FLAT: 29,584 B at
 * 25 runs, 29,590 B at 1,000. `ISAAC_PERF_BENCH=1 .venv/bin/pytest
 * apps/api/tests/test_pending_reads_are_boundable.py -q -s -k benchmark` prints the
 * column.
 *
 * WHY IT COULD NOT BE BOUNDED BEFORE, and what changed. `assistantAgent.confirmProposal`
 * decided `submitAnswer` vs `editField` from MEMBERSHIP in this list, so a question
 * outside the window read as "already answered" and took the edit route — `422
 * unrecognized_field` on a legitimate first answer, with a reason naming the wrong cause.
 * That decision is now the SERVER's: the hinted route is attempted, and a `422
 * already_answered` / `not_yet_answered` is followed once to the operation its `answer_at`
 * names. Membership here is a hint, and being wrong costs one round trip.
 *
 * WHY 50 RATHER THAN 1. Both consumers of `ctx.pending` need only the head —
 * `identify_next_missing_field` reads `pending[0]`, and `confirmProposal` needs a hint —
 * so a window of one would be CORRECT. It would also be wrong on the common path: every
 * proposal for a question below the first would take the redirect, doubling the writes a
 * scientist makes one after another. 50 is `serialize.PENDING_WINDOW`, the window the
 * server volunteers on every mutation response and the page `GuidedCompletion` holds, so
 * the hint is right for every question inside the window — which is every question on
 * every record that exists today — and the redirect covers the tail of a large one.
 *
 * NOTHING IS HIDDEN BY IT. This list feeds the assistant's context only. The Review
 * Record and Export Readiness bundles still call `api.getPending` with no parameters,
 * because a screen reporting what is unresolved would UNDERSTATE it from a page; the
 * completion screen's own counters come from `pending_page.total`, which speaks for the
 * whole record. The one claim this window could have made false —
 * `identify_next_missing_field`'s "there are no pending fields" — is safe because the
 * window is a PREFIX FROM OFFSET 0: an empty prefix is an empty list.
 */
const AGENT_CONTEXT_PENDING_WINDOW = 50;

/** The additive AgentContext inputs the hook fetches (not always in the screen's
 *  bundle): the pending blockers and the evidence-support classification. */
interface AgentExtras {
  pending: ApiPendingItem[];
  classification: ApiEvidenceClassification;
}

export interface UseRecordSessionOptions {
  /**
   * The authoritative record detail from the screen's EXISTING bundle fetch —
   * the single source of `version`/`rev`/`workflow`. Undefined while the bundle
   * is still loading (the hook is then inert: no poll, no extras). Passing it in
   * (rather than re-fetching) is what keeps this from becoming a second cache.
   */
  detail: ApiExperimentDetail | undefined;
  /**
   * The screen's poll-change handler. Called with the FRESH detail on a change
   * signal so the screen can silently refetch its bundle (read-only surfaces) or
   * raise an input-preserving "changed elsewhere" banner (the completion form).
   */
  onChange?: (detail: ApiExperimentDetail) => void;
  /**
   * WHICH PARTS OF THE RECORD MOVED — the bounded change feed's signal, and a
   * DIFFERENT question from `onChange` above.
   *
   * `onChange` answers "the record moved, here is the whole fresh detail" and is
   * what a screen refetches its bundle from. This answers "these runs and these
   * suggestions moved", without composing a draft or fetching the record at all,
   * so a screen can decline to refetch when nothing it renders is affected.
   *
   * IT IS NEVER CALLED WITH NOTHING. A poll that finds no news makes no call, so a
   * surface cannot mistake a quiet poll for a change.
   *
   * THE SUMMARY CARRIES IDS AND KINDS AND NO CONTENT. It is not a record, not a
   * proposal, and not a substitute for reading either from the route that owns it.
   *
   * ── WHERE THE CALLER MOUNTS THIS HOOK MATTERS, AND IT IS NOT OBVIOUS. ───────────
   *
   * The feed cursor and `activity` live in THIS hook, so they live exactly as long as
   * the component that calls it. Measured across the four record screens:
   *
   *   · `RecordWorkbench`, `EvidenceExplorer` — the hook is in the OUTER routed
   *     component, and their refresh is `bundle.reloadSilent()`, which never unmounts
   *     it. The cursor persists across a refresh.
   *   · `ExportReadiness` — the hook is in the INNER `LoadedExport`, but its refresh
   *     is `runFetch(false)`, which leaves `load.name === 'data'`; the component is
   *     re-rendered in place, NOT remounted, so the cursor persists here too.
   *   · `GuidedCompletion` — the hook is in the INNER `LoadedCompletion`, and its
   *     `reload` is `useFetch`'s, which sets `{status: 'loading'}` and therefore
   *     UNMOUNTS it. The cursor and `activity` are destroyed and the next poll is a
   *     full cursorless resync.
   *
   * THE LIVE CONSEQUENCE, stated because it is a trap rather than a curiosity: a
   * screen that wires `onEntitiesChanged` to a refresh path which unmounts the owner
   * gets a SILENTLY DEAD notice — the callback refreshes, the remount discards
   * `activity`, the resync filters every entry against the new revision, and nothing
   * is ever shown. `GuidedCompletion` is the only screen in that position and it
   * deliberately passes NO handler (see its own note); anything added later must check
   * which side of this line it is on before wiring one.
   */
  onEntitiesChanged?: (summary: RecordChangeSummary) => void;
  /** When false the hook is fully inert (no poll, no fetch). Default true. */
  enabled?: boolean;
}

export interface RecordSession {
  /** The authoritative ETag/If-Match token (undefined until `detail` arrives). */
  version: string | undefined;
  /**
   * The authoritative record revision — DERIVED from the same `version` string
   * the context/If-Match uses, so the two can never disagree (undefined until
   * `detail` arrives).
   */
  recordRev: number | undefined;
  /**
   * The derived P29.3 AgentContext. Undefined until the record `detail` arrives
   * AND its AgentContext inputs have SETTLED (loaded or failed) — never a
   * half-built context, so a healthy slow-network mount never flashes degraded.
   */
  context: AgentContext | undefined;
  /**
   * The AgentContext inputs are still in-flight on a healthy mount (no failure
   * yet). Distinct from `degraded`: loading is NOT degraded.
   */
  loading: boolean;
  /** The P29.1 session snapshot (messages + the single staged proposal). */
  session: { messages: Msg[]; proposal: SessionProposal | null };
  /** The poller's own degraded state (drives the LiveSyncNote). */
  syncDegraded: boolean;
  /** The AGENT-CONTEXT degraded state: the AgentContext inputs failed to load. */
  degraded: boolean;
  /** True when the record moved under the current view and has not been adopted. */
  conflict: boolean;
  /** Re-fetch the AgentContext inputs and reload the session snapshot. */
  refresh: () => void;
  /** Pass-through to the poller's imperative immediate check. */
  checkNow: () => void;
  /**
   * THE OUTSTANDING COALESCED SUMMARY of what has moved since this view last
   * adopted a revision, or `null` when nothing is outstanding.
   *
   * PRESENTATION STATE, NOT A CACHE, and the distinction is the reason this hook
   * can hold it at all: it is a handful of ids and kinds describing what is now
   * STALE. The entities themselves continue to live in exactly one place — the
   * screen's own bundle — and nothing renders a value from this.
   *
   * CLEARED BY EXACTLY ONE THING: the view catching up, i.e. `recordRev` reaching the
   * `highestRev` the summary reported. (Also on a record id change, where it belongs
   * to a different record.) So a reader who acts on the notice sees it go away and one
   * who does not keeps seeing it.
   *
   * ~~"and by `refresh()`"~~ — `refresh()` used to clear it unconditionally, and that
   * was a permanent loss of a still-true notice: the feed cursor has already advanced
   * past those entries, so nothing re-reports them. See `refresh()` for the full
   * reasoning; this sentence is corrected in place because it is the description a
   * caller reads.
   */
  activity: RecordChangeSummary | null;
  /**
   * THE SAME SUMMARY, ASKED A DIFFERENT QUESTION: did a PROPOSAL move? — `null` when
   * the latest summary named none.
   *
   * IT IS NOT `activity`, AND WIRING A PROPOSAL SURFACE TO `activity` IS THE DEFECT
   * THIS FIELD EXISTS TO PREVENT. `activity` answers "is what is on screen out of
   * date", which is a statement about the RECORD read, and it is therefore null once
   * that read has caught up. A record refetch adopts NO proposal state — the list
   * lives behind its own route and its own component — so on the ordinary path (the
   * record poller resolving before the feed poller; measured, see
   * `recordChanges.ChangeFloors`) `activity` is null at exactly the moment a
   * colleague's proposal has arrived and the panel most needs to re-read. Reading it
   * from here instead is what makes the refresh work rather than work-if-it-wins-a-race.
   *
   * IDS, STATES AND A POSITION. NO CONTENT, EVER — a `proposal` feed entry carries
   * none by construction (`change_feed.py` imports nothing from `proposals.py`), so a
   * consumer must re-read through the route that owns the list. Key a refresh on
   * `proposalRev` + the ids; never on `highestRev`, which can reach past the
   * proposals in its own batch.
   */
  proposalActivity: RecordChangeSummary | null;
  /**
   * THE SAME SUMMARY, ASKED A THIRD QUESTION: did a RUN move, relative to where the
   * RUN LIST read stands? — `null` when the latest run-floored summary named none.
   *
   * IT IS NOT `activity`, AND FOR EXACTLY THE REASON `proposalActivity` IS NOT.
   * `RunsSection` issues its own paged `api.listRuns` read; the record bundle does not
   * carry the list it renders. So a record refetch adopts no run-list state, and on the
   * ordinary ordering — the record poller resolving before the feed poller, measured in
   * `recordChanges.ChangeFloors` — the record floor has already risen past the `run`
   * entry by the time the feed delivers it, and a floor never comes back down. The
   * entry is dropped permanently and the run list is never told.
   *
   * IDS AND A POSITION. NO RUN CONTENT, EVER — a `run` feed entry carries none, so a
   * consumer must re-read through the route that owns the list. Key a refresh on
   * `runRev` + `runIds`; never on `highestRev`, which can reach past the runs in its
   * own batch (see `RecordChangeSummary.runRev`).
   *
   * IT IS DELIVERED ONCE. The run floor advances as a signal is handed on, so a
   * cursorless resync — which returns every entity at its current position — does not
   * re-report a run this hook has already reported. That is a DIVERGENCE from the
   * proposal floor, which deliberately does not advance, and the divergence is safe
   * only because this summary feeds no announced sentence: `activity` and
   * `describeChangeSummary` are computed from the RECORD-floored summary, which this
   * does not touch. See `handleFeed` for the measurement that made the proposal floor
   * stateless and why it does not apply here.
   */
  runActivity: RecordChangeSummary | null;
  /** The CHANGE FEED poller's degraded state — separate from `syncDegraded`. */
  feedDegraded: boolean;
}

function toWorkflowSteps(detail: ApiExperimentDetail): WorkflowStep[] {
  return detail.workflow.ordered_steps.map((s) => ({
    id: s.id,
    label: s.label,
    state: s.state,
    current: s.current,
    reopened: s.reopened,
    blocked: s.blocked,
    reason: s.reason,
  }));
}

function toEvidenceViews(classification: ApiEvidenceClassification | undefined): EvidenceView[] {
  if (!classification) return [];
  return classification.field_results.map((f) => ({
    field: f.field,
    classification: f.classification,
    value_state: f.value_state,
    explanation: f.explanation,
    // Only the safe source_type is carried into the agent context.
    sources: (f.sources ?? []).map((s) => ({ source_type: s.source_type })),
  }));
}

/**
 * Derive the record revision from the authoritative `version` string so the rev
 * and the version can NEVER disagree — the optimistic-concurrency token has the
 * form `"<generation>.<rev>"`, so the trailing segment is the rev. This is the
 * SAME source the `If-Match` header uses, which closes the rev/version desync
 * window: if a local edit advances the version before the bundle refetch updates
 * `detail.rev`, a proposal staged at the old rev is still correctly detected as
 * stale (its `sourceRev` no longer matches the version-derived rev). Falls back
 * to `detail.rev` only when the version is absent or unparseable.
 */
function deriveRev(
  version: string | undefined,
  detail: ApiExperimentDetail | undefined,
): number | undefined {
  if (version) {
    const parsed = Number(version.split('.').pop());
    if (Number.isFinite(parsed)) return parsed;
  }
  return detail?.rev;
}

/**
 * The agent's view of the open questions.
 *
 * AN UNREADABLE ENTRY IS KEPT, AND THAT IS THE DELIBERATE CHOICE. `GET /pending` serves
 * one entry per stored blocker, including a blocker it could not read as a question
 * (`unavailable: true`, `id`/`kind`/`question` null — see
 * `serialize._unreadable_blocker`). Filtering those out here was the smaller change and
 * would have made the assistant answer "there are no pending fields — none is currently
 * blocking" over a record that is refused for exactly that entry
 * (`assistantAgent.identify_next_missing_field`). So it is carried, with `id` null —
 * there IS no answer key — and `unreadable: true`, which is the flag that branch reads
 * instead of offering to stage a value nothing could apply.
 *
 * **ONE PREDICATE, AND IT IS `adapt.isAnswerablePendingItem`.** ~~`p.unavailable ===
 * true || p.id === null`~~ was a SECOND, divergent definition of the same question, and
 * an independent review measured both ways it diverged. (i) For an entry carrying prose
 * and no kind — which the server marks `unavailable` — the two disagreed, so
 * `GuidedCompletion` said "cannot be answered" while this hook said `unreadable: false`
 * and `assistantAgent` offered to stage a value under the answer key `"blocker"`, which
 * `POST /answers` refuses **422 `unrecognized_field`**: an offer that could never be
 * fulfilled. (ii) On a truthy-non-boolean `unavailable` the shared predicate fails
 * CLOSED (`if (item.unavailable) return false`) and `=== true` failed OPEN. And the
 * `p.id === null` half was an INFERENCE from a pattern of nulls — exactly what
 * `serialize._unreadable_blocker` serves a wire field to avoid, and what this
 * repository's post-check-payload rule forbids.
 */
function toPendingItems(pending: ApiPendingItem[] | undefined): PendingItem[] {
  if (!pending) return [];
  return pending.map((p) => ({
    id: p.id,
    unreadable: !isAnswerablePendingItem(p),
    // The agent renders a human label; prefer the same about → question → id
    // ladder the composer uses so the two never disagree on a field's name.
    // For an unreadable entry every rung is null, so the ladder ends at the server's
    // own reason — never at an invented name for a question nobody could read.
    label:
      (typeof p.about === 'string' && p.about.trim() !== '' && p.about) ||
      (typeof p.question === 'string' && p.question.trim() !== '' && p.question) ||
      p.id ||
      p.unavailable_reason ||
      UNREADABLE_BLOCKER_LABEL,
    // CARRIED, because `confirmProposal` routes a run-owned answer to the run and reads
    // ownership from here. Dropped, it sent every answer to the record route, which
    // refuses a run-owned key with `409 belongs_to_a_run` once a record has runs.
    run_id: p.run_id ?? null,
    // The identity key, so `confirmProposal` can find the RIGHT entry rather than the
    // first of that kind — see `Proposal.blockerKey`.
    blocker_key: p.blocker_key,
  }));
}

export function useRecordSession(
  id: string,
  { detail, onChange, onEntitiesChanged, enabled = true }: UseRecordSessionOptions,
): RecordSession {
  const version = detail?.version;
  // Derived from `version`, NOT read from `detail.rev` independently, so the rev
  // the AgentContext/confirmProposal staleness guard uses always matches the
  // If-Match token (no rev/version desync window).
  const recordRev = deriveRev(version, detail);
  const active = enabled && !!id && !!version;

  // The additive AgentContext inputs + their honest degraded flag.
  const [extras, setExtras] = useState<AgentExtras | null>(null);
  const [contextDegraded, setContextDegraded] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [refreshNonce, setRefreshNonce] = useState(0);

  /*
   * THE LATEST "SOMETHING MOVED" SUMMARY, RAW.
   *
   * IT IS NOT A SECOND STORE, and the test that would fail if it became one is
   * explicit about it: this holds ids and kinds, never an entity. Nothing renders a
   * field, a value or a proposal from it, and the screen's bundle stays the single
   * source of everything the record actually contains.
   *
   * ~~IT USED TO BE `activity` ITSELF~~ — the state and the notice were one value, and
   * separating them is what makes the two-floor fix expressible. Two consumers want
   * DIFFERENT questions answered about the same summary: `RecordActivityNote` wants
   * "is what is on screen out of date" (a statement about the RECORD read), and
   * `IngestionProposalsPanel` wants "did a proposal move" (a statement about a read
   * the record refetch does not touch). Storing only the first answer meant the second
   * consumer could not be served at all on the path where the record read had already
   * caught up — which the browser measurement in `recordChanges.ChangeFloors` shows is
   * the ordinary path.
   */
  const [latest, setLatest] = useState<RecordChangeSummary | null>(null);

  /*
   * THE LATEST RUN-FLOORED SUMMARY — a SECOND raw summary over the SAME entries, and
   * the reason it is a second value rather than a second reading of the first.
   *
   * `latest` above is computed with the run floor set to the RECORD's revision, which
   * is byte-identical to what this hook did before a run floor existed. That is
   * deliberate: `latest` drives `activity`, and `activity` drives a visible banner
   * whose sentence is announced into a live region. Widening what survives the filter
   * there would change that sentence, and `change-feed-preserves-unsaved-input.test.tsx`
   * exists because a changing sentence is re-announced.
   *
   * This one is computed with the run list's OWN floor, and feeds `runActivity` only.
   * Nothing renders from it and nothing announces it; a run surface uses it to decide
   * whether to re-read its own paged list.
   */
  const [latestRun, setLatestRun] = useState<RecordChangeSummary | null>(null);

  // The P29.1 session snapshot. Re-read imperatively after a change/refresh so a
  // proposal marked stale by a revision change is immediately visible.
  const [session, setSession] = useState(() => loadSession(id));

  // Stale-guard: the CURRENT record id, read at response-resolve time so an
  // out-of-order/aborted extras fetch for a previous record cannot clobber the
  // currently-selected one (the useRecordSync currentRef pattern).
  const currentRef = useRef(id);
  currentRef.current = id;

  /*
   * WHERE THE PROPOSAL READ STANDS — the second floor, and the reason the change feed
   * could not refresh the proposals panel before it existed.
   *
   * See `recordChanges.ChangeFloors` for the measurement. In one sentence: `recordRev`
   * rises whenever the RECORD poller refetches, and a proposal act moves the record's
   * rev too, so on the ordinary ordering the record poller raised the floor past the
   * proposal entry before the feed poll delivered it — and a floor never comes back
   * down, so the entry was dropped permanently.
   *
   * SEEDED FROM `recordRev`, ONCE PER RECORD, AND NOT FROM `-1`. Seeding from `-1`
   * would make the first (cursorless) poll report every proposal on the record as
   * news, which is a false notice and a redundant list read on every mount. Seeding
   * from the revision the bundle arrived at is correct because `IngestionProposalsPanel`
   * mounts only once `bundle.status === 'data'` and issues its own first read then —
   * so its list already reflects every proposal at or below that position. If the two
   * disagree it is in the safe direction: the panel's read can only be at or AFTER
   * this revision, so at worst one already-held proposal is re-read silently.
   *
   * IT IS THEN FIXED FOR THE LIFE OF THE RECORD SCREEN, and never advanced — not by a
   * record refetch, which is the defect, and NOT by reporting a proposal onward either,
   * which was tried and withdrawn. `handleFeed` carries the measurement: a floor that
   * advanced made a replayed batch arrive NARROWER than the one before it, which
   * changed the outstanding notice's sentence and re-announced it. Deduplicating a
   * replay is already the job of the sentence comparison in `RecordActivityNote` and
   * the `proposalRev`+ids key in the panel, and both do it without making this
   * stateful.
   *
   * A REF, NOT STATE, because nothing renders from it and a `setState` here would
   * re-run the poll effect it is read inside. Assigned during render in the same
   * style as `currentRef` above, so a record switch cannot leave the previous
   * record's position in place for one poll.
   */
  const proposalFloorRef = useRef<{ id: string; rev: number | undefined }>({
    id,
    rev: undefined,
  });
  if (proposalFloorRef.current.id !== id) proposalFloorRef.current = { id, rev: undefined };
  if (proposalFloorRef.current.rev === undefined && recordRev !== undefined) {
    proposalFloorRef.current.rev = recordRev;
  }

  /*
   * WHERE THE RUN LIST READ STANDS — the third floor, and the reason a run change
   * could be dropped exactly the way a proposal change was.
   *
   * `RunsSection` fetches the run list itself (`api.listRuns`, its own paging), so the
   * record bundle refetch adopts none of it. Measured against the RECORD floor, a `run`
   * entry is filtered the moment the record poller wins the race — and it wins the
   * ordinary case, per the browser measurement in `recordChanges.ChangeFloors`. The
   * entry is then gone for good.
   *
   * SEEDED FROM `recordRev`, ONCE PER RECORD, for `proposalFloorRef`'s reason: the run
   * list mounts once `bundle.status === 'data'` and issues its own first read then, so
   * every run at or below that revision is already on screen. Seeding from `-1` would
   * make the first cursorless poll report every run of the record as news.
   *
   * IT DOES ADVANCE, WHICH IS THE OPPOSITE OF THE PROPOSAL FLOOR, AND THE DIFFERENCE IS
   * NOT AN INCONSISTENCY. The proposal floor was made stateless because advancing it
   * narrowed a REPLAYED batch, which changed `activity`'s rendered sentence and
   * re-announced it into a live region — see `handleFeed`. This floor cannot do that:
   * the summary it governs (`latestRun`) feeds no sentence, no banner and no live
   * region. What it does instead is what the proposal side gets from
   * `IngestionProposalsPanel`'s `proposalRev`+ids key — a signal delivered once — with
   * the same effect and one less thing for a consumer to remember.
   *
   * A REF, NOT STATE: nothing renders from it, and a `setState` here would re-run the
   * poll effect it is read inside.
   */
  const runFloorRef = useRef<{ id: string; rev: number | undefined }>({
    id,
    rev: undefined,
  });
  if (runFloorRef.current.id !== id) runFloorRef.current = { id, rev: undefined };
  if (runFloorRef.current.rev === undefined && recordRev !== undefined) {
    runFloorRef.current.rev = recordRev;
  }

  // Latest onChange without re-subscribing the poller effect.
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  // Same, for the feed's callback: a screen passing an inline arrow must not
  // re-subscribe the poller (and so restart its cadence) on every render.
  const onEntitiesChangedRef = useRef(onEntitiesChanged);
  onEntitiesChangedRef.current = onEntitiesChanged;

  // Reload the session snapshot whenever the record changes.
  useEffect(() => {
    setSession(loadSession(id));
    setConflict(false);
    // A summary belongs to ONE record. Carrying it across would tell a reader that
    // the record they just opened had changed elsewhere, which would be false — and
    // would hand the proposals panel another record's proposal ids to re-read on.
    setLatest(null);
    // Same argument, same reason, for the run-floored summary: its ids name runs that
    // belong to the record being left.
    setLatestRun(null);
  }, [id]);

  // Fetch the AgentContext inputs (pending + evidence classification). Keyed on
  // the authoritative version so an adopted revision re-derives the context. A
  // failure raises the agent `degraded` flag ONLY — the manual workflow, driven
  // by the screen's own bundle, is never blocked here.
  useEffect(() => {
    if (!active) return;
    const startedFor = id;
    let alive = true;
    Promise.all([
      // A BOUNDED PREFIX — see `AGENT_CONTEXT_PENDING_WINDOW`. The page block is
      // deliberately discarded: neither consumer of `ctx.pending` may total or count the
      // list, so carrying a total here would only invite one to start.
      api.getPendingPage(id, { limit: AGENT_CONTEXT_PENDING_WINDOW }),
      api.getEvidenceClassification(id),
    ])
      .then(([page, classification]) => {
        if (!alive || currentRef.current !== startedFor) return; // superseded → drop
        setExtras({ pending: page.pending, classification });
        setContextDegraded(false);
      })
      .catch(() => {
        if (!alive || currentRef.current !== startedFor) return;
        setContextDegraded(true); // honest agent degrade; manual UI unaffected
      });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, version, active, refreshNonce]);

  // A change signal was adopted (version advanced) → no longer in conflict.
  useEffect(() => {
    setConflict(false);
  }, [version]);

  /*
   * THE NOTICE IS DERIVED, NOT STORED — and it USED TO BE AN EFFECT THAT CLEARED
   * STORED STATE. The rule is unchanged and is still `isCaughtUp`; only where it is
   * evaluated moved, and the move is what removes a defect the old shape had.
   *
   * The rule, unchanged: the notice stands until the view has caught up to
   * `highestRev` — the furthest position the summary reported — rather than being
   * cleared on any `version` change. A refetch that lands on a revision still BELOW
   * the change would otherwise clear a notice that is still true, telling a reader
   * they are current when they are not.
   *
   * WHY DERIVED. An effect can only clear state AFTER a commit that already rendered
   * it, so a summary arriving already-caught-up put `RecordActivityNote` — a visible
   * banner with a Refresh button — on screen for one frame and announced its sentence
   * into a live region, before removing it. That path was unreachable while one floor
   * governed every kind (an already-caught-up entry was filtered out upstream and no
   * summary was produced). Under two floors it is the ORDINARY path for a colleague's
   * proposal, so the latent flicker would have become the common case. Deriving it
   * means there is no such commit: the notice is null in the same render in which the
   * summary is adopted.
   *
   * IT STILL STOPS THE NOTICE BEING STICKY on the path that deliberately does NOT
   * refetch: a proposal-only summary above the record's rev leaves that rev where it
   * was, so the notice correctly stays until the reader acts on it — and their Refresh
   * moves the rev, which re-evaluates this without any screen having to remember to.
   */
  const activity = latest !== null && !isCaughtUp(latest, recordRev) ? latest : null;

  // The ONE poller for this record. On a change signal, invalidate any staged
  // proposal grounded in the OLD revision, surface the stale flag, raise
  // `conflict`, then delegate to the screen's handler (refetch or banner).
  const handleChanged = useCallback(
    (fresh: ApiExperimentDetail) => {
      // Use the version-derived rev of the FRESH detail so it matches the rev a
      // proposal was staged against (also version-derived) — the two staleness
      // signals stay on the same axis.
      const freshRev = deriveRev(fresh.version, fresh);
      if (freshRev !== undefined) invalidateStaleProposals(id, freshRev);
      setSession(loadSession(id));
      setConflict(true);
      onChangeRef.current?.(fresh);
    },
    [id],
  );

  const { degraded: syncDegraded, checkNow } = useRecordSync(id, version, {
    onChanged: handleChanged,
    enabled,
  });

  /*
   * THE ONE CHANGE-FEED POLLER FOR THIS RECORD, mounted here for the same reason
   * `useRecordSync` is: a per-screen poller means four screens agreeing to run one
   * each and nothing enforcing it. This hook is already the single owner of
   * record-scoped polling, so the feed joins it rather than starting a second
   * ownership story.
   *
   * IT IS GATED ON `active`, WHICH IS `enabled && !!id && !!version`. So it does not
   * poll before the screen's bundle has arrived (no target yet), does not poll on a
   * screen that has disabled the session, and stops on unmount — and the hook itself
   * additionally pauses while the tab is hidden and resumes from the cursor it holds.
   *
   * WHAT IT MAY DO WITH WHAT IT LEARNS, exhaustively: raise `activity` for the
   * notice, and call the screen's `onEntitiesChanged` so the screen can refetch its
   * own canonical read. IT MAY NOT WRITE, and no path from here reaches a mutation
   * — which is what makes "the client's own save cannot trigger a further save"
   * structural rather than a promise about timing.
   *
   * IT DELIBERATELY DOES NOT CALL `onChange`. That callback carries a fresh
   * `ApiExperimentDetail` and is the record poller's to fire; the feed never fetches
   * the record, so it has no detail to pass and must not pretend otherwise.
   */
  const handleFeed = useCallback(
    (entries: ApiChangeEntry[]) => {
      /*
       * TWO FLOORS, BECAUSE THERE ARE TWO INDEPENDENT READS ON THIS SCREEN. The record
       * floor is the revision THIS VIEW holds, which is what makes a scientist's own
       * save the ordinary filtered case rather than a special one. The proposal floor
       * is where the PROPOSAL read stands, which a record refetch does not move — see
       * `recordChanges.ChangeFloors` for the browser measurement that says so.
       */
      const summary = summariseChanges(entries, {
        record: recordRev,
        proposal: proposalFloorRef.current.rev,
        /*
         * THE RECORD'S OWN REVISION, NOT THE RUN FLOOR, AND THAT IS THE POINT OF
         * COMPUTING THIS SUMMARY SEPARATELY FROM THE RUN ONE BELOW.
         *
         * This summary is what `activity` and therefore `RecordActivityNote` are
         * derived from, and that banner's sentence is announced into a live region.
         * Passing the run floor here would widen what survives, change the sentence
         * on a replayed batch, and re-announce it — the exact defect
         * `change-feed-preserves-unsaved-input.test.tsx` pins, arrived at from the
         * other direction. With `run: recordRev` this call is byte-identical to what
         * it was before a run floor existed, which is the property that lets the run
         * floor be added without touching a single announced string.
         */
        run: recordRev,
      });

      /*
       * THE RUN SURFACE'S OWN QUESTION, over the SAME entries, with the run list's own
       * floor — see `runFloorRef`. It is asked BEFORE the early return below, because
       * the two questions have different answers: a batch in which the record poller
       * has already filtered the `run` entry produces `summary === null` and a
       * perfectly real run signal, which is precisely the case the run floor exists
       * for and the case that used to be lost.
       */
      const runSummary = summariseChanges(entries, {
        record: recordRev,
        proposal: proposalFloorRef.current.rev,
        run: runFloorRef.current.rev,
      });
      if (runSummary && runSummary.runIds.length > 0) {
        // DELIVERED ONCE: advance past the runs just reported so a cursorless resync
        // does not hand the same ids to the run list again. Safe here and not on the
        // proposal floor for the reason `runFloorRef` sets out — nothing announces this.
        if (runSummary.runRev > (runFloorRef.current.rev ?? -1)) {
          runFloorRef.current.rev = runSummary.runRev;
        }
        setLatestRun(runSummary);
      }

      if (!summary) return; // nothing newer than what is on screen — say nothing

      /*
       * THE PROPOSAL FLOOR IS NOT ADVANCED HERE, AND IT WAS, AND THE TEST THAT CAUGHT
       * IT IS THE FLOODING GUARD.
       *
       * The rejected version raised the floor to `summary.proposalRev` each time a
       * proposal was reported onward, to keep a cursorless resync from re-reporting it.
       * It worked, and it broke something better protected elsewhere: a REPLAYED batch
       * then arrived NARROWER than the one before it — the proposal filtered, the
       * record's own entry not — so an outstanding notice went from "1 suggestion
       * changed" to "this record changed" and `RecordActivityNote` re-announced into a
       * live region, which is precisely what
       * `change-feed-preserves-unsaved-input.test.tsx`'s "does not re-announce when a
       * later poll says the same thing" exists to prevent. A stateful floor made the
       * SENTENCE stateful, and the sentence is what a screen-reader user hears.
       *
       * A replay needs no floor of its own, because two mechanisms already handle it
       * and both are the ones designed for it: `RecordActivityNote` compares the
       * rendered SENTENCE as a string and announces nothing when it is unchanged, and
       * `IngestionProposalsPanel` keys its silent re-read on `proposalRev` + the ids,
       * which a replay reproduces exactly. An identical batch is therefore already
       * silent and already costs no request. Adding a third mechanism bought nothing
       * and cost the second one its stability.
       */

      // Held RAW. Whether it is worth SHOWING is a separate question, asked once, at
      // the derivation below — never here, and never in an effect that would have to
      // undo a commit that already put a banner on screen.
      setLatest(summary);
      onEntitiesChangedRef.current?.(summary);
    },
    [recordRev],
  );

  const { degraded: feedDegraded } = useChangeFeed(id, {
    onChanges: handleFeed,
    enabled: active,
  });

  const refresh = useCallback(() => {
    setConflict(false);
    /*
     * THE NOTICE IS NOT CLEARED HERE, AND IT USED TO BE — unconditionally.
     *
     * The wording that stood here read: "The reader has acted on the notice. It is
     * cleared here rather than left for the version to clear, because a refresh that
     * finds nothing new would otherwise leave a notice standing about a change
     * already taken on board." Both halves are wrong, and the second contradicts the
     * `highestRev` effect above, which is the published reasoning for exactly this.
     *
     * A refresh that finds nothing new has NOT taken the change on board. `recordRev`
     * is then unchanged and still below `activity.highestRev`, so the notice is STILL
     * TRUE — and clearing it tells a reader they are current when they are not, which
     * is the one thing that effect exists to prevent. Clearing it here made the loss
     * PERMANENT rather than momentary: the feed cursor has already advanced past
     * those entries, so nothing will report them again, and the only route back is a
     * cursorless resync this hook never asks for.
     *
     * So the clear is left entirely to the `highestRev` effect, which fires the
     * instant the view actually catches up — and it does catch up on this path,
     * because `refresh()`'s only caller (`RecordWorkbench.onAgentRefresh`) pairs it
     * with `bundle.reloadSilent()`, whose fresh `detail` advances `version`.
     */
    setSession(loadSession(id));
    setRefreshNonce((n) => n + 1);
  }, [id]);

  // The AgentContext inputs have SETTLED once they either loaded (`extras`) or
  // failed (`contextDegraded`). Until then we are LOADING, not degraded.
  const settled = !!extras || contextDegraded;
  const loading = active && !settled;

  const context = useMemo<AgentContext | undefined>(() => {
    // Only expose a context once the record detail is present AND its inputs have
    // settled — never a half-built context mid-load (which would flash degraded).
    if (!detail || !settled) return undefined;
    return {
      experimentId: id,
      // Version-derived (see deriveRev) so rev and version never disagree.
      recordRev: deriveRev(detail.version, detail) ?? detail.rev,
      version: detail.version,
      workflow: {
        current_step: detail.workflow.current_step,
        ordered_steps: toWorkflowSteps(detail),
      },
      evidence: toEvidenceViews(extras?.classification),
      pending: toPendingItems(extras?.pending),
      // Degraded ONLY when a fetch actually FAILED — loading is never degraded.
      degraded: contextDegraded,
    };
  }, [detail, id, extras, contextDegraded, settled]);

  return {
    version,
    recordRev,
    context,
    loading,
    session,
    syncDegraded,
    // True ONLY after an AgentContext-input fetch actually failed — a healthy
    // slow-network mount stays `loading`, never flashes the degraded banner.
    degraded: contextDegraded,
    conflict,
    refresh,
    checkNow,
    activity,
    // Deliberately derived from `latest` rather than from `activity`: the whole point
    // is that it survives the record read catching up.
    proposalActivity: latest !== null && latest.proposalIds.length > 0 ? latest : null,
    /*
     * FROM `latestRun`, NOT FROM `latest`, and never filtered by `isCaughtUp`. The
     * record read catching up says nothing about whether the RUN LIST has: it is a
     * different read, behind a different route, in a different component. Filtering
     * this on the record's revision would null it at exactly the moment a colleague's
     * run edit arrived on the ordinary ordering — which is the whole defect.
     */
    runActivity: latestRun !== null && latestRun.runIds.length > 0 ? latestRun : null,
    feedDegraded,
  };
}
