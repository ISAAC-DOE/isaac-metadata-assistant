/*
 * UNMAPPED NOTES — the review surface for content that has no confident schema home.
 *
 * WHAT THIS PANEL IS FOR. A scientist writes things down that no rule can place: why
 * a scan was repeated, a column heading nothing recognised, an aside in a transcript.
 * This is the destination that now exists, and where a person decides what each note is.
 *
 * ~~"Every pipeline in this application drops such content silently, and STILL DOES —
 * nothing was rewired to feed this panel. Its only producer today is the capture box
 * below, which always sends `typed_note`; … so no note here yet carries a run, a
 * candidate path, or any source but that one."~~ — CORRECTED 2026-08-29. `POST
 * /api/experiments/{id}/transcript` writes one `source: "transcript"` note per segment
 * of a finalized transcript, carrying that capture's `run_id` and, when the reader
 * proposed exactly one, a `candidate_field_path` with its rule. So notes rendered here
 * DO already arrive with a run, a candidate path and a second source — which is why
 * this panel renders the candidate-with-its-rule at all (see rule 1 below). Struck
 * rather than rewritten: the same sentence stood in four backend files and this one,
 * and a reader who remembers any copy will otherwise re-derive the wrong conclusion.
 *
 * WHAT SURVIVES: the capture box below is still the only thing in the frontend that
 * calls `POST .../notes`, and it still always sends `typed_note`; `csv_column`,
 * `file_listing_line` and `extraction_residue` still have no producer anywhere, the
 * extractor's discarded `unrecognised_labels` being the intended first one.
 *
 * THE FOUR ACTIONS ARE PEERS. Map, Edit, Keep as Note and Dismiss are rendered as one
 * row of equally-weighted buttons, deliberately. "Keep as Note" is a first-class
 * outcome — some of what a scientist writes is prose about the experiment and belongs
 * to no field — so it is not styled as a fallback, and Dismiss is not styled as a
 * delete, because it is not one.
 *
 * THREE THINGS THIS PANEL WILL NOT DO, each of which it would be easy to do:
 *
 *   1. IT NEVER PROPOSES A FIELD. The mapping control offers exactly the paths the
 *      SERVER reported in `mappable_field_paths`, with no default selected and no
 *      pre-selection from the note's text. Where the server sent a
 *      `candidate_field_path`, it is shown as a proposal WITH the rule that produced
 *      it, and it still has to be chosen — a suggestion is not a decision.
 *   2. IT NEVER HIDES A DISMISSED NOTE BY DEFAULT. The filter starts at "All", and
 *      the counts state the record's true total whatever the filter says, so a
 *      reader can never conclude from this panel that a note is gone.
 *   3. IT NEVER SHOWS THE REVISED WORDING ALONE. When a note has been edited, both
 *      the current wording and the verbatim capture are on screen, because the
 *      capture is the thing the feature promised to keep.
 *
 * ONE VALIDATOR, THE RECORD'S. Every write carries the experiment's version token,
 * which is re-read from each write's own response rather than from the record bundle
 * — the same rule `RunsSection` follows for creating a run.
 *
 * PR-D (2026-09-03) ADDED A FIFTH ACT: "Propose a value from this note". It is the
 * named caller `api.createProposal`'s own doc comment said was next — see
 * `lib/api.ts`'s `createProposal`, and `docs/ingestion-proposal-contract.md` §11.2,
 * both corrected in the same change to say so. It is a PEER of the other four, per
 * this file's own "THE FOUR ACTIONS ARE PEERS" rule above, now five: proposing is no
 * more a fallback than mapping, keeping or dismissing is, and it is styled identically.
 * Unlike Map/Edit/Keep/Dismiss it does not change `note.state` at all — a proposal is
 * a SEPARATE record on the experiment (`state["proposals"]`), reviewed on the
 * Ingestion Proposals surface, never here. The note stays exactly as it was; the
 * proposal is what changed.
 */
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';

import { api, ApiError } from '../lib/api';
import { mutationFailureCopy, staleWriteCurrentVersion } from '../lib/mutationErrors';
import { markSelfMintedProposals } from '../lib/selfMintedProposals';
import { RUN_FIELDS, parseRunField, type RunFieldSpec } from '../lib/runFields';
import { RUNS_PAGE_SIZE } from '../lib/runPaging';
import type { ApiNote, ApiNoteState, ApiNotesResponse, ApiRunView } from '../lib/types';
import { BackendDown, LoadingPanel } from './FetchStates';
import { DiscardStaged } from './DiscardStaged';
import { DISCARD_COPY } from '../lib/discardContent';
import './unmappedNotes.css';

/** Same narrowing `RunsSection` uses — a non-`ApiError` throw still renders a panel. */
function asApiError(err: unknown): ApiError {
  return err instanceof ApiError
    ? err
    : new ApiError(err instanceof Error ? err.message : String(err));
}

/** The filter options. `all` is first and is the default — see rule 2 above. */
const FILTERS: readonly { id: 'all' | ApiNoteState; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'unreviewed', label: 'Not yet reviewed' },
  { id: 'mapped', label: 'Mapped' },
  { id: 'kept', label: 'Kept as notes' },
  { id: 'dismissed', label: 'Dismissed' },
];

/**
 * How each state reads to a scientist.
 *
 * `dismissed` says "Dismissed — kept on the record" rather than "Dismissed", because
 * the single most likely misreading of this panel is that dismissing removed
 * something. The state's own label is where that is cheapest to correct.
 */
const STATE_LABELS: Readonly<Record<ApiNoteState, string>> = {
  unreviewed: 'Not yet reviewed',
  mapped: 'Mapped to a field',
  kept: 'Kept as a note',
  dismissed: 'Dismissed — kept on the record',
};

/** Source vocabulary in product words. An unknown source is shown VERBATIM. */
const SOURCE_LABELS: Readonly<Record<string, string>> = {
  typed_note: 'Typed here',
  transcript: 'From a transcript',
  csv_column: 'An unrecognised CSV column',
  file_listing_line: 'A line of a file listing',
  extraction_residue: 'A label the extractor would not guess at',
};

function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source;
}

/**
 * How `unreadable_entries` is disclosed — ONE string, used by the count line and by
 * both empty states, so a reader cannot be told two different things by two places
 * on the same screen.
 *
 * IT DOES NOT SAY "CANNOT READ", AND THAT IS THE POINT. The server's single number
 * covers two different facts (`workspace._hydrate_notes`): an entry the note model
 * refused, and an entry whose id another note already holds. The second one this
 * build reads perfectly well — it just cannot let two notes answer to one id. So
 * the copy says what is actually true of both, which is that they are not SHOWN,
 * and it names both causes rather than asserting the one that is wrong half the
 * time. Separating them into two counts is a contract change and was deliberately
 * not made here.
 */
function unreadableClause(count: number): string {
  if (count <= 0) return '';
  const noun = count === 1 ? 'entry' : 'entries';
  const asNote = count === 1 ? 'as a note' : 'as notes';
  return (
    ` · ${count} stored ${noun} this version cannot show ${asNote}` +
    ' — either unreadable, or repeating an id another note already holds' +
    ' — kept unchanged on the record'
  );
}

/**
 * What a 412 means here, and what this panel did about it before: NOTHING.
 *
 * D2 — THE DEAD END. Every write on this panel carries the experiment's version
 * token, and the SUCCESS path adopted the new one from the write's own response. The
 * failure path did not, so one refusal left the held token permanently one revision
 * behind: the next attempt re-sent the same stale validator and was refused again, and
 * again, with no way out. The only remedy on screen was `Reload This Section`, which
 * put the list into `loading` — unmounting every note card and taking the rewritten
 * wording or the dismissal reason with it. Refuse, then destroy what was typed to
 * recover from the refusal.
 *
 * BOTH HALVES ARE FIXED, and they are separate fixes. (a) A 412 now ADOPTS the token
 * the server reports (`staleWriteCurrentVersion` — the same `current_version` the
 * route echoes as an `ETag` "so the client can refresh in one hop"), so the very next
 * attempt is made against the current record; and (b) the reload the banner offers is
 * SILENT, so the list is refreshed in place and nothing that was typed is unmounted.
 *
 * The copy names the likely cause rather than an unnamed third party, for the reason
 * `RunsSection` records: the other writer is very often this same reader, on this same
 * screen, seconds earlier.
 */
const STALE_REVIEW_COPY =
  'The record changed since this section was loaded, so that was not recorded — it can ' +
  'be your own edit elsewhere on this screen. Nothing was lost: this section has picked ' +
  'up the current version and what you typed is still here, so try again.';

type ListState =
  | { status: 'loading' }
  | { status: 'error'; error: ApiError }
  | { status: 'data'; loaded: ApiNotesResponse };

/**
 * "Propose a value from this note"'s two capability reads, both SERVED, never
 * transcribed here — `GET .../proposals` reports the paths this build can target
 * and which of them are record-scoped; `null` means the read failed, which is a
 * different fact from "nothing is proposable" (`targetFieldPaths: []`) and is
 * rendered as a different sentence.
 */
type ProposalCapabilities = {
  targetFieldPaths: string[];
  recordScopedTargetFieldPaths: string[];
} | null;

/**
 * THE RULE SENTENCE FOR A HUMAN-MAPPED PROPOSAL. `rule` is required and must be
 * "the sentence that produced this value and this target, not an identifier" —
 * for an extracted candidate that sentence describes the extraction rule; for
 * this act there is no extraction rule, and the honest sentence says exactly
 * that: a person read the note and chose the value directly. It is a FIXED
 * constant rather than something a scientist types, because composing a
 * provenance sentence is a burden this act does not need to impose — the act
 * itself IS the provenance.
 */
const HUMAN_PROPOSED_RULE =
  'A person read this note directly and entered this value for the field by hand; ' +
  'no automated rule matched it.';

/**
 * A short, deterministic, NON-cryptographic digest of a proposed value — used only
 * to build `client_request_key` so an accidental double click on "Propose This
 * Value" dedupes to one proposal rather than two. It carries no security property;
 * exactly-once enforcement is the server's, inside `record_lock` (contract §2,
 * DEC-13) — this only has to be STABLE for the same (note, path, value) triple
 * within one click, which a plain hash over the value's JSON serialisation is.
 *
 * m8, INDEPENDENT REVIEW OF PR-D — THE COLLISION BEHAVIOUR, NAMED RATHER THAN
 * LEFT IMPLICIT. This is a 32-bit hash (`hash >>> 0`), not a cryptographic one,
 * so two DIFFERENT values for the SAME (note, path) CAN — with vanishing but
 * non-zero probability — produce the SAME `client_request_key`. If that ever
 * happens: proposing value A stores it under key K; proposing DIFFERENT value B
 * for the same note+path later computes the SAME key K, and the server's
 * dedup (contract §2 DEC-13 — "a key already present … returns the EXISTING
 * proposal") returns A's proposal with `deduplicated: true` — the reader is
 * told "already proposed" while the record still holds A, not B. Nothing is
 * corrupted (A is a real, previously-confirmed proposal; B is simply not
 * stored), but the CONFIRMATION is misleading for that one request. Two things
 * bound the risk to theoretical: the key space this collision would need to
 * land in is scoped to ONE (note_id, field_path) pair — not the record, not
 * the experiment — and a real note is proposed against a handful of paths at
 * most, nowhere near the ~2^16 distinct values against one pair before a
 * birthday-bound collision becomes plausible. Upgrading to a wider,
 * collision-resistant digest (e.g. a truncated `SubtleCrypto` SHA-256) would
 * close this to a cryptographic margin; not done here because the risk this
 * function actually has to cover — an accidental double click on the SAME
 * value — cannot manifest it at all (identical value ⇒ identical digest by
 * construction), and a wider digest is a separate, reviewable change.
 */
function stableValueDigest(value: unknown): string {
  const json = JSON.stringify(value) ?? 'undefined';
  let hash = 5381;
  for (let index = 0; index < json.length; index += 1) {
    hash = (Math.imul(hash, 33) + json.charCodeAt(index)) | 0;
  }
  return (hash >>> 0).toString(16);
}

export function UnmappedNotesPanel({ experimentId }: { experimentId: string }) {
  return (
    <section className="notes-section" aria-labelledby="unmapped-notes-heading">
      <div className="notes-head">
        <h2 className="notes-title" id="unmapped-notes-heading">
          Unmapped Notes
        </h2>
        <p className="notes-sub">
          Content captured against this record that has no confident schema home.
          Nothing here is a field value or evidence, and nothing here is ever
          deleted — dismissing a note sets it aside and keeps it on the record.
        </p>
      </div>
      {/* Keyed on the record so switching records rebuilds this panel's state
          rather than showing one record's notes under another's heading. */}
      <NotesBrowser key={experimentId} experimentId={experimentId} />
    </section>
  );
}

function NotesBrowser({ experimentId }: { experimentId: string }) {
  const [list, setList] = useState<ListState>({ status: 'loading' });
  const [filter, setFilter] = useState<'all' | ApiNoteState>('all');
  const [version, setVersion] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);
  const [busyNoteId, setBusyNoteId] = useState<string | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  /**
   * WHAT JUST HAPPENED, for the live region. Held as state rather than derived,
   * because the announcement is about an ACT and there is nothing in the refreshed
   * list that distinguishes "this note was just dismissed" from "this note was
   * dismissed last week".
   */
  const [announcement, setAnnouncement] = useState('');

  /** Discards an out-of-order response rather than letting it overwrite a newer one. */
  const generationRef = useRef(0);
  /** Suppresses the loading blank on a reload this panel caused itself. */
  const silentRef = useRef(false);

  const filterId = useId();

  useEffect(() => {
    let alive = true;
    const generation = ++generationRef.current;
    if (!silentRef.current) setList({ status: 'loading' });
    silentRef.current = false;

    api
      .listNotes(experimentId, filter === 'all' ? {} : { state: filter })
      .then((loaded) => {
        if (!alive || generation !== generationRef.current) return;
        setList({ status: 'data', loaded });
        setVersion(loaded.experiment_version);
      })
      .catch((err: unknown) => {
        if (!alive || generation !== generationRef.current) return;
        setList({ status: 'error', error: asApiError(err) });
      });

    return () => {
      alive = false;
    };
  }, [experimentId, filter, reloadNonce]);

  const reload = useCallback((silent: boolean) => {
    silentRef.current = silent;
    setReloadNonce((n) => n + 1);
  }, []);

  /**
   * Turn a refused write into a state a reader can act from — see `STALE_REVIEW_COPY`.
   *
   * On a 412 it adopts the token the server reported and refreshes the list SILENTLY,
   * so the counts and states catch up while every open form, and everything typed into
   * one, stays exactly where it is. On any other failure it changes nothing and returns
   * the caller's own sentence: this must never claim a recovery it did not make.
   */
  const recoverFromStale = useCallback(
    (err: unknown, fallback: string): string => {
      const current = staleWriteCurrentVersion(err);
      if (current === null) return mutationFailureCopy(asApiError(err), fallback);
      setVersion(current);
      reload(true);
      return STALE_REVIEW_COPY;
    },
    [reload],
  );

  /**
   * Runs one review act and refreshes.
   *
   * THE REFRESH IS NOT OPTIONAL AND IS NOT A PATCH-IN-PLACE. The response carries
   * the reviewed note, but the record's per-state counts and its version have both
   * moved, and splicing the note into local state while leaving the counts stale
   * would put two disagreeing numbers on the same screen.
   */
  const review = useCallback(
    async (
      note: ApiNote,
      action: 'map' | 'edit' | 'keep' | 'dismiss',
      opts: { fieldPath?: string; text?: string; reason?: string },
      announce: string,
    ) => {
      if (!version) return;
      setBusyNoteId(note.id);
      setMutationError(null);
      try {
        const written = await api.reviewNote(experimentId, note.id, {
          experimentVersion: version,
          action,
          ...opts,
        });
        /*
         * THE NEW VERSION IS ADOPTED FROM THIS WRITE'S OWN RESPONSE, not left to
         * arrive with the refetch below. Between the write and the refetch the held
         * token is one revision stale, and every button on every OTHER note card is
         * still live — so a scientist reviewing two notes quickly would have the
         * second act refused with a 412 that nothing was actually wrong with. The
         * refusal would be safe (nothing is lost, and the banner says so), but it
         * would be an error message manufactured by this component's own bookkeeping.
         * `RunsSection` advances the token from the create response for the same
         * reason.
         */
        setVersion(written.experiment_version);
        setAnnouncement(announce);
        reload(true);
      } catch (err: unknown) {
        setMutationError(recoverFromStale(err, 'That review could not be recorded. The note is unchanged.'));
        setAnnouncement('');
        /*
         * RETHROWN, EXACTLY AS `capture` BELOW RETHROWS, AND FOR THE SAME REASON.
         *
         * A caller has to be able to tell "recorded" from "refused", because the
         * two forms that carry typed input close themselves afterwards. If this
         * resolved on failure, a 412 would leave the banner saying the note is
         * unchanged — true — while the form closed and took the scientist's
         * rewritten paragraphs or dismissal reason with it. The note surviving is
         * not the promise; what they typed surviving is.
         */
        throw err;
      } finally {
        setBusyNoteId(null);
      }
    },
    [experimentId, version, reload],
  );

  const capture = useCallback(
    async (text: string, source: string) => {
      if (!version) return;
      setMutationError(null);
      try {
        const written = await api.captureNote(experimentId, {
          experimentVersion: version,
          text,
          source,
        });
        // Adopted from this write's own response — see the note in `review` above.
        setVersion(written.experiment_version);
        setAnnouncement('Note captured. It is on the record and not yet reviewed.');
        reload(true);
      } catch (err: unknown) {
        setMutationError(recoverFromStale(err, 'That note could not be captured. Nothing was written.'));
        setAnnouncement('');
        throw err;
      }
    },
    [experimentId, version, reload],
  );

  /*
   * THE TARGET-PATH CAPABILITY, FETCHED ONCE PER MOUNT — this panel already fetches
   * the notes list unconditionally on mount, so one more read on the same
   * always-visible destination is not a new category of cost. `null` (not `[]`) is
   * the read-failed state and renders a DIFFERENT sentence than "this build has no
   * proposable paths"; see `ProposalCapabilities` above.
   *
   * THE RUN LIST IS DELIBERATELY NOT FETCHED HERE. It used to be, eagerly, and
   * `runs-live-refresh-integration.test.tsx`'s "first paint reads the runs ONCE"
   * invariant caught it: `RunsSection` already reads this record's runs on mount,
   * so fetching them again here doubled a read the Record Workbench asserts happens
   * exactly once. It is fetched LAZILY instead — see `ensureRunsForPropose` below —
   * the moment a reader actually opens a propose form, which is the earliest point
   * a run-scoped path can be chosen.
   */
  const [proposalCapabilities, setProposalCapabilities] = useState<ProposalCapabilities>(null);
  /** The PANEL-LEVEL version of `NoteCard`'s own `canPropose` — used only to
   *  decide whether the one-time banner below renders. See m12. */
  const canProposeAnywhere =
    proposalCapabilities !== null && proposalCapabilities.targetFieldPaths.length > 0;
  const [runsForPropose, setRunsForPropose] = useState<ApiRunView[]>([]);
  const runsForProposeFetchedRef = useRef(false);

  /** Idempotent: a second call while the first is in flight, or after it
   *  succeeded, does nothing. A failed read may be retried by a later open. */
  const ensureRunsForPropose = useCallback(() => {
    if (runsForProposeFetchedRef.current) return;
    runsForProposeFetchedRef.current = true;
    /*
     * F2, INDEPENDENT REVIEW OF PR-D (post-merge). Bounded at `RUNS_PAGE_SIZE`,
     * the same first-page size every other `listRuns` call in this app asks
     * for — omitting `limit` returns EVERY run on the record (`routes.py`,
     * measured; `omitting_limit_returns_MORE_THAN_ONE_PAGE_of_runs`), which
     * this picker has no reason to ask for. UNLIKE the label lookup in
     * `IngestionProposalsPanel`, a run beyond this page is not merely shown
     * less prettily — it is NOT OFFERED as an option here at all, so this
     * picker never implies it has listed every run on the record; a record
     * with more than `RUNS_PAGE_SIZE` runs needs its target run's id entered
     * some other way (an MCP call, or a future paged picker), not a claim this
     * dropdown does not make.
     */
    api
      .listRuns(experimentId, { limit: RUNS_PAGE_SIZE })
      .then((res) => setRunsForPropose(res.runs))
      .catch(() => {
        // Left empty, which reads as "no runs available" — fail-closed, never
        // letting a reader submit a proposal naming a run this read could not
        // confirm exists. Un-set the guard so a later open may retry the read.
        runsForProposeFetchedRef.current = false;
      });
  }, [experimentId]);

  useEffect(() => {
    let alive = true;
    api
      .listProposals(experimentId, { limit: 1 })
      .then((res) => {
        if (!alive) return;
        setProposalCapabilities({
          targetFieldPaths: res.target_field_paths,
          recordScopedTargetFieldPaths: res.record_scoped_target_field_paths,
        });
      })
      .catch(() => {
        if (alive) setProposalCapabilities(null);
      });
    return () => {
      alive = false;
    };
  }, [experimentId]);

  /**
   * Mint a proposal from a note this record already holds.
   *
   * NEVER TOUCHES `note.state` OR TRIGGERS A NOTES-LIST RELOAD — a proposal is a
   * separate record on the experiment; the note that cited it is unchanged, and
   * `list.loaded.notes` has nothing to re-fetch. The EXPERIMENT version DOES
   * move (the write is inside the same `record_lock` as every other write here),
   * so it is adopted from the response exactly as every other write on this
   * panel adopts its own — the next act on ANY note uses the current token.
   */
  const proposeValue = useCallback(
    async (
      note: ApiNote,
      opts: { fieldPath: string; runId?: string; value: unknown; clientRequestKey: string },
    ) => {
      if (!version) throw new Error('no record version held yet');
      setMutationError(null);
      try {
        const written = await api.createProposal(experimentId, {
          experimentVersion: version,
          noteId: note.id,
          targetFieldPath: opts.fieldPath,
          proposedValue: opts.value,
          rule: HUMAN_PROPOSED_RULE,
          ...(opts.runId !== undefined ? { runId: opts.runId } : {}),
          clientRequestKey: opts.clientRequestKey,
        });
        setVersion(written.experiment_version);
        // Same-tab courtesy, not a server fact — see `lib/selfMintedProposals.ts`.
        markSelfMintedProposals(experimentId, [written.proposal.proposal_id]);
        setAnnouncement(
          written.deduplicated
            ? 'This value was already proposed from this note — no second proposal was ' +
                'created. Review it in Ingestion Proposals.'
            : 'Proposal stored. Review it in Ingestion Proposals.',
        );
        return written;
      } catch (err: unknown) {
        setMutationError(
          recoverFromStale(err, 'That proposal could not be stored. Nothing was written.'),
        );
        setAnnouncement('');
        throw err;
      }
    },
    [experimentId, version, recoverFromStale],
  );

  /**
   * The last successfully loaded page, kept across a reload.
   *
   * The live region and the counts must stay MOUNTED to be announced at all — a
   * region that is unmounted and remounted with new content is not read out. So the
   * toolbar renders off this snapshot while a reload is in flight.
   */
  const lastLoadedRef = useRef<ApiNotesResponse | null>(null);
  if (list.status === 'data') lastLoadedRef.current = list.loaded;
  const loaded = list.status === 'data' ? list.loaded : lastLoadedRef.current;

  const countLine = useMemo(() => {
    if (!loaded) return '';
    const total = `${loaded.total} ${loaded.total === 1 ? 'note' : 'notes'} on this record`;
    const filtered =
      filter === 'all' ? total : `Showing ${loaded.returned} of ${total}`;
    return `${filtered}${unreadableClause(loaded.unreadable_entries)}`;
  }, [loaded, filter]);

  return (
    <div className="notes-browser">
      <div className="notes-toolbar">
        <div className="notes-control">
          <label className="notes-control-label" htmlFor={filterId}>
            Show
          </label>
          <select
            id={filterId}
            className="notes-filter"
            value={filter}
            onChange={(e) => {
              /*
               * SILENT, so changing the filter does not unmount an open form and take
               * the rewrite with it. The effect below shows the loading state only when
               * `silentRef` is unset, and that is what destroyed the text: a filter
               * change is a list-changing act, but it is not a reason to discard what
               * the reader typed into a form that is still on screen.
               *
               * The cost, stated because it is real: for the duration of the read the
               * counts beside each filter still describe the PREVIOUS selection. That
               * is a visibly transient number, which is a better trade than a silently
               * destroyed paragraph.
               */
              silentRef.current = true;
              setFilter(e.target.value as 'all' | ApiNoteState);
            }}
          >
            {FILTERS.map((f) => (
              <option key={f.id} value={f.id}>
                {f.label}
                {loaded && f.id !== 'all' ? ` (${loaded.by_state[f.id] ?? 0})` : ''}
              </option>
            ))}
          </select>
        </div>
        {/*
          MOUNTED IN EVERY STATE, and blanked rather than left stale while a reload is
          in flight. A live region that is remounted with its content is never
          announced, and holding yesterday's numbers through a reload is worse than
          showing none.
        */}
        <p className="notes-count" aria-live="polite" aria-atomic="true">
          {list.status === 'loading' ? '' : countLine}
        </p>
      </div>

      {/*
        THE ACT ANNOUNCEMENT, separate from the counts. A screen-reader user who
        activates Dismiss needs to hear that the note was set aside AND KEPT; the
        count line cannot carry that, because it says the same thing before and after.
      */}
      <p className="sr-only" role="status" aria-live="polite">
        {announcement}
      </p>

      {mutationError && (
        <div className="notes-error" role="alert">
          {mutationError}
          {/*
            SILENT — `reload(true)`, not `reload(false)`. D2: the loud reload sets
            `{status:'loading'}`, which unmounts the whole `<ul>` of note cards and so
            destroys the rewritten wording or the dismissal reason the reader was
            offered this control to recover. The refresh itself is unchanged; what
            changed is that it no longer blanks the list to perform it, which is the
            only thing that made it destructive.
          */}
          <button type="button" className="btn btn-secondary" onClick={() => reload(true)}>
            Reload This Section
          </button>
        </div>
      )}

      <CaptureNote
        onCapture={capture}
        disabled={version === null}
        /* THIS PANEL'S ONE ACT-ANNOUNCEMENT CHANNEL, above. A discard is an act the
           reader took and its outcome belongs in the same region every other act's
           does — not in a second polite region competing with it. */
        onAnnounce={setAnnouncement}
      />

      {/*
        m12, INDEPENDENT REVIEW OF PR-D — SAID ONCE, AT THE PANEL, NOT ONCE PER
        NOTE CARD. Every `NoteCard` used to render its OWN copy of this sentence
        when proposing was unavailable, so a record with a dozen unreviewed
        notes repeated the identical explanation a dozen times. The reason is a
        fact about this BUILD (or this read), not about any one note, so it is
        stated here once; `NoteCard` now renders no button and no text of its
        own in this case — see the comment beside its own `canPropose` check.
      */}
      {!canProposeAnywhere && (
        <p className="notes-propose-unavailable-banner">
          {proposalCapabilities === null
            ? 'Proposing a value from a note could not be offered: the set of ' +
              'proposable fields could not be read.'
            : 'Proposing a value from a note is not offered: this build accepts ' +
              'no proposal target yet.'}
        </p>
      )}

      {list.status === 'loading' && (
        <LoadingPanel label="Loading this record's unmapped notes…" />
      )}
      {list.status === 'error' && (
        <BackendDown error={list.error} onRetry={() => reload(false)} />
      )}
      {list.status === 'data' &&
        (list.loaded.notes.length === 0 ? (
          <EmptyNotes
            total={list.loaded.total}
            unreadable={list.loaded.unreadable_entries}
            filtering={filter !== 'all'}
            onClear={() => setFilter('all')}
          />
        ) : (
          <ul className="notes-list">
            {list.loaded.notes.map((note) => (
              <li key={note.id}>
                <NoteCard
                  note={note}
                  mappablePaths={list.loaded.mappable_field_paths}
                  valueWritablePaths={list.loaded.value_writable_field_paths}
                  // `?? []` because this key is newer than the others: a server that
                  // predates it must degrade to the run-level sentence, which is the
                  // MILD direction (a reader is told they need a run when they may
                  // not), never to a claim that no run is needed when one is.
                  recordWritablePaths={list.loaded.record_writable_field_paths ?? []}
                  proposalCapabilities={proposalCapabilities}
                  runsForPropose={runsForPropose}
                  onEnsureRunsForPropose={ensureRunsForPropose}
                  busy={busyNoteId === note.id || version === null}
                  onReview={review}
                  onPropose={proposeValue}
                />
              </li>
            ))}
          </ul>
        ))}
    </div>
  );
}

/**
 * The two empty states are kept apart.
 *
 * "This record has no notes" and "nothing matches the filter you chose" are
 * different facts, and collapsing them lets a filtered view read as an empty record
 * — which, in a feature whose whole promise is that nothing is silently lost, is the
 * most damaging thing this panel could say.
 *
 * BOTH STATES CARRY THE UNREADABLE DISCLOSURE, because `total` counts only the
 * entries this build could turn into notes. "This record holds 3 notes IN TOTAL"
 * and "No unmapped notes ON THIS RECORD" are both false while a stored entry sits
 * outside that count, and an empty state is exactly where a reader stops looking —
 * so it cannot be the one surface that leaves the number out.
 */
function EmptyNotes({
  total,
  unreadable,
  filtering,
  onClear,
}: {
  total: number;
  unreadable: number;
  filtering: boolean;
  onClear: () => void;
}) {
  const disclosure = unreadableClause(unreadable);
  if (filtering) {
    return (
      <div className="notes-empty">
        <p>
          No notes are in this state. This record holds {total}{' '}
          {total === 1 ? 'note' : 'notes'} in total{disclosure}.
        </p>
        <button type="button" className="btn btn-secondary" onClick={onClear}>
          Show All Notes
        </button>
      </div>
    );
  }
  return (
    <div className="notes-empty">
      <p>
        No unmapped notes on this record{disclosure}. Notes appear here when
        something is captured that cannot be placed in a schema field — nothing is
        created automatically, and nothing is inferred from the record's contents.
      </p>
    </div>
  );
}

function CaptureNote({
  onCapture,
  disabled,
  onAnnounce,
}: {
  onCapture: (text: string, source: string) => Promise<void>;
  disabled: boolean;
  /** Push a sentence into the panel's own `role="status"` region. */
  onAnnounce: (text: string) => void;
}) {
  const [text, setText] = useState('');
  const [saving, setSaving] = useState(false);
  const textId = useId();
  const hintId = useId();
  const boxRef = useRef<HTMLTextAreaElement>(null);

  const submit = async () => {
    if (!text.trim() || saving) return;
    setSaving(true);
    try {
      /*
       * THE TEXT IS SENT UNTRIMMED. The blank check above is about whether there is
       * anything to send at all; once there is, what the scientist typed goes to the
       * server exactly as typed, because "stored verbatim" has to be true of the
       * string they wrote and not of a tidied version of it.
       */
      await onCapture(text, 'typed_note');
      setText('');
    } catch {
      /* The browser already surfaced the failure; the text is kept so it is not lost. */
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="notes-capture">
      <label className="notes-control-label" htmlFor={textId}>
        Capture a note
      </label>
      <textarea
        id={textId}
        ref={boxRef}
        className="notes-capture-input"
        aria-describedby={hintId}
        rows={2}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Something worth keeping that has no field to go in"
      />
      <p className="notes-capture-hint" id={hintId}>
        Stored word for word. It is not a field value and not evidence, and it will
        not appear in an exported record.
      </p>
      <button
        type="button"
        className="btn btn-primary"
        disabled={disabled || saving || text.trim() === ''}
        onClick={submit}
      >
        {saving ? 'Capturing…' : 'Capture Note'}
      </button>
      {/*
        THE ONE BOX ON THIS PANEL WITH NO WAY OUT OF IT — until now. The three review
        forms on each note card each have a `Cancel` that clears them, and the panel's
        own copy tells the reader so; this box, which is where every typed note in the
        application starts, had neither. It is offered only while something is typed,
        and never while a capture is in flight: a control that emptied the box during a
        request would leave the reader unable to tell whether the note they no longer
        see was stored.
      */}
      <DiscardStaged
        staged={text !== '' && !saving}
        copy={DISCARD_COPY.noteCapture}
        onDiscard={() => setText('')}
        onAnnounce={onAnnounce}
        onFocusAfterDiscard={() => boxRef.current?.focus()}
      />
    </div>
  );
}

/**
 * WHAT THIS PANEL MAY PROMISE ABOUT ENTERING THE VALUE — one sentence, chosen per path.
 *
 * THE SENTENCE THIS REPLACES WAS FALSE FOR 7 OF THE 25 MAPPABLE PATHS. After choosing a
 * field the hint read, for every path: *"This records where the content belongs. It does
 * not write a value — a value still has to be entered and confirmed on the field
 * itself."* The first half is true everywhere. The second half describes an ACTION, and
 * for the six `system.configuration.*` paths and `timestamps.created_utc` no request in
 * this build can perform it — measured over HTTP against all ~~five~~ six write routes,
 * every one of which answers 422. (The count read five until 2026-08-29;
 * `POST .../runs/{run_id}/edit` was missing from the enumeration and accepts none of the
 * 25, so re-measuring over six moved no path in either direction.) So the screen whose
 * whole purpose is to stop captured content being thrown away was sending the scientist
 * to a locked door, and the one thing they could reasonably conclude on finding it
 * locked is that the note has no home.
 *
 * IT IS PER PATH, NOT ON AVERAGE, because a hint is read about the field in front of you.
 * `value_writable_field_paths` is the server's own subset — derived in `routes.py` from
 * the admissible-address sets the write routes actually enforce, so the sentence and
 * the refusal cannot drift. Nothing is transcribed here.
 *
 * AND IT SAYS WHERE, which the old copy did not. "On the field itself" pointed at no
 * screen a person could find.
 *
 * ~~"AND IT SAYS 'ON A RUN' … Both write routes are a run's: `PATCH .../runs/{run_id}`
 * for a run's own field and `POST .../runs/{run_id}/overrides` for a record-level
 * one."~~ — CORRECTED 2026-08-29. That was true of all 18 writable paths when it was
 * written and is now false for one of them. `system.technique` is also answered at
 * `POST /api/experiments/{id}/answers` and corrected at `POST /api/experiments/{id}/edit`,
 * which are the RECORD's — measured over HTTP, `{"system.technique": "XAS"}` returns 200
 * on a record with ZERO runs. So a reader mapping a note to `system.technique` was being
 * sent to a run they do not need and may not have. It is the MILD direction of the same
 * defect the paragraph above describes, and it is the same defect: a sentence true on
 * average, read about one field.
 *
 * SO THERE ARE THREE OUTCOMES, NOT TWO, and the third is served rather than transcribed:
 * `record_writable_field_paths` is the server's sub-subset a record-level operation
 * accepts. A client-side list of "which one is the record's" would be free to drift the
 * moment the server's derivation changed, and nothing would fail — which is precisely
 * how the two-outcome version of this function came to be wrong.
 *
 * WHY THE UNWRITABLE SEVEN ARE NOT SIMPLY GIVEN A ROUTE, which would be the better fix:
 * `system.configuration` is a designated OPEN namespace the vendored schema declares no
 * properties for, and `CLAUDE.md` §15 records those six fields as an open external
 * question — classifying them here would be deciding it rather than reporting it. That is
 * a product decision, and this is the honest sentence until it is made.
 */
export function valueWriteHint(
  fieldPath: string,
  valueWritablePaths: string[],
  recordWritablePaths: string[] = [],
): string {
  if (fieldPath === '') {
    // NOTHING CHOSEN YET, so nothing may be said about a specific field. The half that
    // is true of every path is said, and no more.
    return 'This records where the content belongs. It does not write a value.';
  }
  if (!valueWritablePaths.includes(fieldPath)) {
    return (
      'This records where the content belongs. It does not write a value, and this ' +
      'version has nowhere to enter one for this field — mapping files the note and ' +
      'keeps its text on the record in full, which is all it can do here.'
    );
  }
  // THE RECORD-LEVEL ARM IS CHECKED AGAINST THE WRITABLE SET FIRST, deliberately. The
  // server derives `record_writable_field_paths` as a SUBSET of the writable set, so
  // the two can never disagree — but reading them in the other order would let a
  // hypothetical inconsistency render as "enter it on this record" for a path nothing
  // accepts, which is the locked-door failure this whole function exists to end.
  // Ordering it this way makes the worst case the mild direction instead.
  return recordWritablePaths.includes(fieldPath)
    ? 'This records where the content belongs. It does not write a value — a value for ' +
        'this field is entered and confirmed on this record. No run is needed.'
    : 'This records where the content belongs. It does not write a value — a value for ' +
        'this field is entered and confirmed on a run of this record.';
}

function NoteCard({
  note,
  mappablePaths,
  valueWritablePaths,
  recordWritablePaths,
  proposalCapabilities,
  runsForPropose,
  onEnsureRunsForPropose,
  busy,
  onReview,
  onPropose,
}: {
  note: ApiNote;
  mappablePaths: string[];
  /**
   * The SERVER's per-path answer to "may a value then be entered here?", served
   * alongside `mappablePaths` and never re-derived. See `valueWriteHint` for the
   * false sentence this exists to replace.
   */
  valueWritablePaths: string[];
  /**
   * And the server's per-path answer to "WHERE — on a run, or on the record?". A
   * subset of `valueWritablePaths`, also served rather than derived here.
   */
  recordWritablePaths: string[];
  /** The server's own proposable-path vocabulary. `null` ⇒ the read failed. */
  proposalCapabilities: ProposalCapabilities;
  /** For choosing a run when a proposal target is run-scoped. `[]` may mean
   *  "not fetched yet" or "genuinely none" — both render the same honest case. */
  runsForPropose: ApiRunView[];
  /** Triggers the lazy run-list read the first time it is genuinely needed. See
   *  `NotesBrowser`'s `ensureRunsForPropose` for why it is not fetched eagerly. */
  onEnsureRunsForPropose: () => void;
  busy: boolean;
  onReview: (
    note: ApiNote,
    action: 'map' | 'edit' | 'keep' | 'dismiss',
    opts: { fieldPath?: string; text?: string; reason?: string },
    announce: string,
  ) => Promise<void>;
  onPropose: (
    note: ApiNote,
    opts: { fieldPath: string; runId?: string; value: unknown; clientRequestKey: string },
  ) => Promise<{ deduplicated: boolean }>;
}) {
  const [open, setOpen] = useState<'map' | 'edit' | 'dismiss' | 'propose' | null>(null);
  /** No default selection. See rule 1 in the module header — nothing is proposed. */
  const [fieldPath, setFieldPath] = useState('');
  const [editText, setEditText] = useState(note.display_text);
  const [reason, setReason] = useState('');

  /* ---- "Propose a value from this note" form state ------------------------ */
  const [proposeFieldPath, setProposeFieldPath] = useState('');
  const [proposeRunId, setProposeRunId] = useState('');
  const [proposeValueText, setProposeValueText] = useState('');
  const [proposeError, setProposeError] = useState<string | null>(null);
  const [proposeBusy, setProposeBusy] = useState(false);

  /*
   * D3 — WHAT A FORM HOLDS IS NOT DISCARDED BY CLOSING IT, only by Cancel and by a
   * write that consumed it.
   *
   * WHAT WAS WRONG. `Edit wording`'s own handler ran `setEditText(note.display_text)`
   * BEFORE opening, and `close()` reset all three inputs — so a reader who rewrote a
   * paragraph, then pressed `Map to a field` or `Dismiss` to check something, then came
   * back to `Edit wording`, found the box holding the ORIGINAL again. No confirmation,
   * no notice, and the rewrite was not recoverable from anywhere on the screen.
   *
   * THE RULE NOW. Closing a form — by its own toggle, or by opening a sibling — keeps
   * what is in it. Only two things clear an input: the form's own `Cancel`, which is a
   * reader saying so; and a review the server RECORDED, which consumed it.
   *
   * THE SERVER STAYS AUTHORITATIVE, which is why this resync exists rather than a bare
   * initial value. When a write lands, the list refreshes and this card is handed a new
   * `note`; if its wording moved, the held text is replaced. Adjusting state during
   * render (rather than in an effect) is React's own documented shape for this, and it
   * avoids rendering one frame of the superseded text.
   *
   * BUT ONLY IF THE READER HAS NOT TOUCHED THE BOX -- and the first version of this
   * resync had no such condition, which made it contradict the panel's own 412 banner.
   * An independent review found the composition: a 412 fires a silent reload, and a
   * concurrent change to THIS note's wording is the plausible cause of that 412 -- so
   * the resync fired exactly when `STALE_REVIEW_COPY` was on screen saying "what you
   * typed is still here". Two fixes in the same change, one falsifying the other.
   *
   * "Stale by definition" was the justification, and it is only true of text the reader
   * has not edited. A rewrite in progress is not stale; it is unsaved. So the server's
   * wording is adopted when the box still matches what the server last sent, and
   * otherwise the reader keeps what they wrote and the banner's claim stays true. The
   * two ways a box IS cleared are unchanged: the form's own Cancel, and a review the
   * server recorded.
   */
  const serverText = useRef(note.display_text);
  if (serverText.current !== note.display_text) {
    const untouched = editText === serverText.current;
    serverText.current = note.display_text;
    if (untouched) setEditText(note.display_text);
  }

  const pathId = useId();
  const editId = useId();
  const reasonId = useId();
  const bodyId = useId();
  const proposeId = useId();

  const mapRef = useRef<HTMLButtonElement>(null);
  const editRef = useRef<HTMLButtonElement>(null);
  const dismissRef = useRef<HTMLButtonElement>(null);
  const proposeRef = useRef<HTMLButtonElement>(null);

  /*
   * FOCUS RETURNS TO THE CONTROL THAT OPENED THE FORM, AND IT HAS TO BE AN EFFECT.
   *
   * Every path out of a form — Cancel, and a review that was recorded — unmounts
   * the form while focus is on a button INSIDE it, so focus falls to `<body>` and a
   * keyboard user dismissing the third note on a record is returned to the top of
   * the document. The same contract `NewExperimentForm` keeps, and for the reason
   * it records: a `.focus()` call inside the handler silently does nothing, because
   * the trigger does not exist at that moment — it has to run AFTER the re-render
   * that puts the button back.
   *
   * `returningTo` holds WHICH trigger, and doubles as `NewExperimentForm`'s
   * `returning` flag: null means "no form was open", so a first render, and a
   * `keep` (which has no form), never steal focus to a button nobody pressed.
   */
  const returningTo = useRef<'map' | 'edit' | 'dismiss' | 'propose' | null>(null);
  useEffect(() => {
    if (open !== null) return;
    const returning = returningTo.current;
    if (returning === null) return;
    returningTo.current = null;
    const trigger =
      returning === 'map'
        ? mapRef.current
        : returning === 'edit'
          ? editRef.current
          : returning === 'dismiss'
            ? dismissRef.current
            : proposeRef.current;
    trigger?.focus();
  }, [open]);

  /**
   * Close the open form. `discard` is what clears its input — see the D3 note above.
   *
   * `which` is passed rather than read from `open`, because the two callers know
   * different things: a `Cancel` button knows which form it is inside, and a recorded
   * review knows which ACT succeeded (`keep` has no form and consumes nothing).
   */
  const closeForm = (which: 'map' | 'edit' | 'dismiss' | 'propose' | null, discard: boolean) => {
    if (open !== null) returningTo.current = open;
    setOpen(null);
    if (!discard) return;
    if (which === 'map') setFieldPath('');
    if (which === 'edit') setEditText(note.display_text);
    if (which === 'dismiss') setReason('');
    if (which === 'propose') {
      setProposeFieldPath('');
      setProposeRunId('');
      setProposeValueText('');
      setProposeError(null);
    }
  };

  /**
   * Runs one review act, AND CLOSES THE FORM ONLY IF IT WAS RECORDED.
   *
   * `onReview` rethrows on failure — see the comment on `review` — so this is where
   * "the note is unchanged" stops meaning "and so is everything you typed". A 412
   * from a concurrent capture in another tab must leave the rewritten wording, or
   * the dismissal reason, on screen and editable; the banner above the list is
   * already saying what happened. `CaptureNote` swallows its own rethrow the same
   * way and for the same reason, so the two write paths have one shape.
   */
  const runReview = async (
    action: 'map' | 'edit' | 'keep' | 'dismiss',
    opts: { fieldPath?: string; text?: string; reason?: string },
    announce: string,
  ) => {
    try {
      await onReview(note, action, opts, announce);
      // Recorded, so the input this act consumed is cleared. Anything typed into a
      // DIFFERENT form is not — `keep` in particular consumes nothing at all.
      closeForm(action === 'keep' ? null : action, true);
    } catch {
      /*
       * Refused. The banner reports it; the form and its typed input stay put — and
       * since D2 the banner's own remedy no longer unmounts this card either, so
       * "stays put" is true of the remedy as well as of the refusal.
       */
    }
  };

  /* ---- "Propose a value from this note" — derived state and its one write ---- */

  /** Absent, with a reason, rather than disabled — the same rule `DiscardStaged`
   *  and every other absent-when-inapplicable control in this app follows. */
  const canPropose = proposalCapabilities !== null && proposalCapabilities.targetFieldPaths.length > 0;
  const proposeIsRecordScoped =
    proposalCapabilities !== null &&
    proposalCapabilities.recordScopedTargetFieldPaths.includes(proposeFieldPath);
  const proposeNeedsRun = proposeFieldPath !== '' && !proposeIsRecordScoped;
  /*
   * m13, INDEPENDENT REVIEW OF PR-D — TYPED ENTRY WHERE A SPEC EXISTS, JSON ONLY
   * AS THE FALLBACK. `RUN_FIELDS` is `RunCard`'s own closed, five-path,
   * server-verified writable set (each entry backed by the official schema's
   * declared type — an enum, a number, or an ISO date-time) — the exact same
   * spec `RunCard` itself uses to render its controls. A proposal TARGET path
   * that happens to be one of those five gets the SAME typed control
   * (`parseRunField` does the parsing either way), so a scientist proposing
   * `context.temperature_K` types `300`, not `300` wrapped in JSON quoting
   * rules they have to remember. A target OUTSIDE that five — `system.technique`,
   * `sample.*`, `system.facility.*`, and anything future the server's
   * `target_field_paths` widens to — has no client-side spec for its shape at
   * all, and the honest fallback for a shape this file does not know is JSON
   * text, exactly as before: never a guess at a type the schema did not confirm.
   */
  const proposeFieldSpec: RunFieldSpec | null =
    RUN_FIELDS.find((spec) => spec.path === proposeFieldPath) ?? null;

  const runPropose = async () => {
    if (proposeBusy || proposeFieldPath === '') return;
    if (proposeNeedsRun && proposeRunId === '') return;
    let parsedValue: unknown;
    if (proposeFieldSpec !== null) {
      const parsed = parseRunField(proposeFieldSpec, proposeValueText);
      if (!parsed.ok) {
        setProposeError(parsed.error);
        return;
      }
      parsedValue = parsed.value;
    } else {
      try {
        parsedValue = JSON.parse(proposeValueText) as unknown;
      } catch {
        setProposeError(
          'That is not valid JSON, so it was not sent and nothing was written. A text ' +
            'value needs quotes around it, for example "CuO".',
        );
        return;
      }
    }
    if (parsedValue === null) {
      setProposeError(
        'A null value cannot be proposed here — clearing a field is a different act ' +
          'with its own questions. Nothing was sent.',
      );
      return;
    }
    setProposeError(null);
    setProposeBusy(true);
    try {
      const clientRequestKey =
        `note-propose:${note.id}:${proposeFieldPath}:` + stableValueDigest(parsedValue);
      await onPropose(note, {
        fieldPath: proposeFieldPath,
        ...(proposeNeedsRun ? { runId: proposeRunId } : {}),
        value: parsedValue,
        clientRequestKey,
      });
      closeForm('propose', true);
    } catch {
      /* Refused, or a 412. The panel-level banner reports it (including, on a 412,
         that the version was reloaded); this form and its typed input stay put. */
    } finally {
      setProposeBusy(false);
    }
  };

  return (
    <article className="note-card" data-state={note.state} data-note-id={note.id}>
      <div className="note-card-head">
        <span className="note-state" data-state={note.state}>
          {STATE_LABELS[note.state]}
        </span>
        <span className="note-source">{sourceLabel(note.source)}</span>
        <span className="note-captured mono">{note.captured_utc}</span>
        {note.run_id && <span className="note-run">Run {note.run_id}</span>}
      </div>

      <p className="note-text" id={bodyId}>
        {note.display_text}
      </p>

      {/*
        WHEN AN EDIT EXISTS, THE ORIGINAL IS ON SCREEN TOO. The capture is what this
        feature promised to keep; showing only the corrected wording would make that
        promise true in the store and false to the person reading it.
      */}
      {note.revised_text !== null && (
        <p className="note-original">
          <span className="note-original-label">Captured as:</span> {note.text}
        </p>
      )}

      {note.mapped_field_path && (
        <p className="note-mapped">
          Mapped to <span className="mono">{note.mapped_field_path}</span>. This
          records where the content belongs; it does not set the field's value.
        </p>
      )}

      {/*
        A PROPOSAL IS SHOWN WITH THE RULE THAT PRODUCED IT, or not at all. An
        unexplained suggestion is a guess wearing a field name, and the server refuses
        to store one — so there is no case where this renders a path with no reason.
      */}
      {note.candidate_field_path && (
        <p className="note-candidate">
          Suggested field: <span className="mono">{note.candidate_field_path}</span>
          <span className="note-candidate-rule"> — {note.candidate_rule}</span>
        </p>
      )}

      <div className="note-actions">
        <button
          ref={mapRef}
          type="button"
          className="btn btn-secondary"
          disabled={busy}
          aria-expanded={open === 'map'}
          aria-controls={open === 'map' ? pathId : undefined}
          onClick={() => setOpen(open === 'map' ? null : 'map')}
        >
          Map to a field
        </button>
        <button
          ref={editRef}
          type="button"
          className="btn btn-secondary"
          disabled={busy}
          aria-expanded={open === 'edit'}
          aria-controls={open === 'edit' ? editId : undefined}
          /* NO `setEditText` HERE. Re-opening this form used to overwrite the reader's
             rewrite with the note's stored wording — see the D3 note above. The box is
             seeded once, and re-seeded only when the SERVER's wording moves. */
          onClick={() => setOpen(open === 'edit' ? null : 'edit')}
        >
          Edit wording
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={busy}
          onClick={() =>
            runReview(
              'keep',
              {},
              'Kept as a note. It belongs to no field, and it stays on the record.',
            )
          }
        >
          Keep as note
        </button>
        <button
          ref={dismissRef}
          type="button"
          className="btn btn-secondary"
          disabled={busy}
          aria-expanded={open === 'dismiss'}
          aria-controls={open === 'dismiss' ? reasonId : undefined}
          onClick={() => setOpen(open === 'dismiss' ? null : 'dismiss')}
        >
          Dismiss
        </button>
        {/*
          m12, INDEPENDENT REVIEW OF PR-D — ABSENT, WITH NO PER-CARD REASON.
          When proposing is unavailable the button is simply absent here — the
          ONE explanatory sentence for "why" is the panel-level banner
          (`NotesBrowser`, right above the notes list), stated once rather than
          repeated identically on every card in the list. "Absent, never
          disabled" is unchanged: this is not a disabled control claiming
          something exists and then refusing it.
        */}
        {canPropose && (
          <button
            ref={proposeRef}
            type="button"
            className="btn btn-secondary"
            disabled={busy}
            aria-expanded={open === 'propose'}
            aria-controls={open === 'propose' ? proposeId : undefined}
            onClick={() => {
              // Idempotent (see `ensureRunsForPropose`) — safe to call on every
              // open, including a re-open, rather than tracking "was it opened
              // before" here too.
              onEnsureRunsForPropose();
              setOpen(open === 'propose' ? null : 'propose');
            }}
          >
            Propose a value from this note
          </button>
        )}
      </div>

      {open === 'map' && (
        <div className="note-form" id={pathId}>
          <label className="notes-control-label" htmlFor={`${pathId}-select`}>
            Field this note belongs to
          </label>
          <select
            id={`${pathId}-select`}
            className="note-field-select"
            value={fieldPath}
            onChange={(e) => setFieldPath(e.target.value)}
          >
            {/* No pre-selection. A person chooses; nothing is proposed for them. */}
            <option value="">Choose a field…</option>
            {mappablePaths.map((path) => (
              <option key={path} value={path}>
                {path}
              </option>
            ))}
          </select>
          {/*
            THE LIST IS A SUBSET, AND SAYING SO IS NOT OPTIONAL. The server offers
            the paths THIS BUILD can map a note to, which is fewer than the official
            schema defines. A scientist who does not find their target and is not
            told why concludes the note has no home and dismisses it — the one
            outcome this panel is built to avoid. So the shortfall is stated where
            they are looking, and the alternative it names is a real one: keeping
            the note is a first-class outcome, not a consolation.
          */}
          <p className="note-form-hint">
            {valueWriteHint(fieldPath, valueWritablePaths, recordWritablePaths)}
          </p>
          <p className="note-form-hint">
            This list is not every field in the ISAAC schema — it is the set this
            version can map a note to. If the field you want is missing, that does
            not mean the schema has no such field, and it does not mean this note
            has nowhere to go: keep it as a note and it stays on the record, in
            full, for whoever reads it next.
          </p>
          <div className="note-form-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || fieldPath === ''}
              onClick={() =>
                runReview(
                  'map',
                  { fieldPath },
                  `Mapped to ${fieldPath}. No value was written. ${valueWriteHint(
                    fieldPath,
                    valueWritablePaths,
                    recordWritablePaths,
                  )}`,
                )
              }
            >
              Map This Note
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => closeForm('map', true)}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {open === 'edit' && (
        <div className="note-form" id={editId}>
          <label className="notes-control-label" htmlFor={`${editId}-input`}>
            Corrected wording
          </label>
          <textarea
            id={`${editId}-input`}
            className="notes-capture-input"
            rows={3}
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
          />
          <p className="note-form-hint">
            The original capture is kept unchanged and stays visible on this note.
            The review state is not affected — correcting a typo is not a decision.
          </p>
          {/* SAID ON SCREEN, because the behaviour changed and a reader cannot see it
              (D3). Closing this form used to discard the rewrite silently. */}
          {/* SCOPED, because the first version of this sentence was an ABSOLUTE and
              therefore false. It said "Only Cancel discards it" while a failed
              re-read of the list still unmounts every card and every open form -- and
              at the time, so did changing the filter (now silent). An independent
              review found the filter case; the failed-read case is disclosed here
              rather than denied, since it is the one this panel cannot prevent. */}
          <p className="note-form-hint">
            Closing this form, or opening another one on this note, keeps what you have
            typed here, and so does changing the filter above. Cancel discards it — as
            does a failed re-read of the list, which replaces the whole list.
          </p>
          <div className="note-form-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || editText.trim() === ''}
              onClick={() =>
                runReview(
                  'edit',
                  { text: editText },
                  'Wording updated. The original capture is unchanged.',
                )
              }
            >
              Save Wording
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => closeForm('edit', true)}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {open === 'dismiss' && (
        <div className="note-form" id={reasonId}>
          <label className="notes-control-label" htmlFor={`${reasonId}-input`}>
            Why (optional)
          </label>
          <input
            id={`${reasonId}-input`}
            className="note-reason-input"
            type="text"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <p className="note-form-hint">
            Dismissing sets this note aside. It is not deleted: it stays on the
            record, stays readable, and keeps its history. Leave the reason blank if
            you do not have one — nothing is filled in on your behalf. Closing this
            form keeps what you typed; only Cancel discards it.
          </p>
          <div className="note-form-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy}
              onClick={() =>
                runReview(
                  'dismiss',
                  { reason },
                  'Dismissed. The note is set aside and stays on the record.',
                )
              }
            >
              Dismiss This Note
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => closeForm('dismiss', true)}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {open === 'propose' && canPropose && proposalCapabilities !== null && (
        <div className="note-form" id={proposeId}>
          <label className="notes-control-label" htmlFor={`${proposeId}-path`}>
            Field this value is for
          </label>
          <select
            id={`${proposeId}-path`}
            className="note-field-select"
            value={proposeFieldPath}
            onChange={(e) => {
              setProposeFieldPath(e.target.value);
              setProposeRunId('');
              setProposeError(null);
              // The value box's CONTROL TYPE can change with the field (a typed
              // enum/number/datetime control for a `RUN_FIELDS` path, JSON text
              // otherwise) — clearing it here stops a JSON-quoted string or a
              // bare number surviving into a control shaped for the other kind.
              setProposeValueText('');
            }}
          >
            {/* No pre-selection, even when `note.candidate_field_path` names one —
                the same rule the Map form follows: a person chooses. */}
            <option value="">Choose a field…</option>
            {proposalCapabilities.targetFieldPaths.map((path) => (
              <option key={path} value={path}>
                {path}
              </option>
            ))}
          </select>
          <p className="note-form-hint">
            This is the server&rsquo;s own list of the paths this build can target with
            a proposal — a subset of the official schema, not every field it defines.
          </p>

          {proposeFieldPath !== '' && proposeNeedsRun && (
            <>
              <label className="notes-control-label" htmlFor={`${proposeId}-run`}>
                Run this value is about
              </label>
              {runsForPropose.length === 0 ? (
                <p className="note-form-hint" role="alert">
                  This field is applied through a run&rsquo;s writer, and this record
                  has no runs yet (or they could not be read). Create a run from the
                  Runs section before proposing a value here — it is never inferred.
                </p>
              ) : (
                <select
                  id={`${proposeId}-run`}
                  className="note-field-select"
                  value={proposeRunId}
                  onChange={(e) => setProposeRunId(e.target.value)}
                >
                  <option value="">Choose a run…</option>
                  {runsForPropose.map((run) => (
                    <option key={run.id} value={run.id}>
                      {run.label}
                    </option>
                  ))}
                </select>
              )}
              <p className="note-form-hint">
                Required: a value at this field path is applied through a run&rsquo;s
                writer, so the proposal must name the run it is about. It is never
                inferred, even when this record has exactly one run.
              </p>
            </>
          )}

          {proposeFieldPath !== '' && proposeFieldSpec !== null && (
            <>
              {/*
                m13 — THE TYPED CONTROL, when `RUN_FIELDS` declares a spec for
                this path: the same enum/number/datetime shapes `RunCard` uses,
                parsed by the same `parseRunField`. No JSON, no quoting rule to
                remember.
              */}
              <label className="notes-control-label" htmlFor={`${proposeId}-value`}>
                {proposeFieldSpec.label}
                {proposeFieldSpec.unit ? ` (${proposeFieldSpec.unit})` : ''}
              </label>
              {proposeFieldSpec.kind === 'enum' ? (
                <select
                  id={`${proposeId}-value`}
                  className="note-field-select"
                  value={proposeValueText}
                  onChange={(e) => {
                    setProposeValueText(e.target.value);
                    setProposeError(null);
                  }}
                >
                  <option value="">Choose a value…</option>
                  {proposeFieldSpec.options?.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id={`${proposeId}-value`}
                  className="note-reason-input"
                  type="text"
                  inputMode={proposeFieldSpec.kind === 'number' ? 'decimal' : undefined}
                  value={proposeValueText}
                  onChange={(e) => {
                    setProposeValueText(e.target.value);
                    setProposeError(null);
                  }}
                />
              )}
              <p className="note-form-hint">
                <span className="mono">{proposeFieldSpec.path}</span> — the same field
                the Runs section itself edits, entered the same way.
                {proposeFieldSpec.hint ? ` ${proposeFieldSpec.hint}` : ''} This does not
                write the value — it stores a proposal for someone to accept or reject
                on the Ingestion Proposals screen.
              </p>
            </>
          )}

          {proposeFieldPath !== '' && proposeFieldSpec === null && (
            <>
              {/*
                THE JSON FALLBACK — no client-side spec exists for this path's
                shape, so the type is never guessed. See the `proposeFieldSpec`
                comment above for exactly which paths this covers.
              */}
              <label className="notes-control-label" htmlFor={`${proposeId}-value`}>
                The value, as JSON
              </label>
              <textarea
                id={`${proposeId}-value`}
                className="notes-capture-input mono"
                rows={3}
                value={proposeValueText}
                onChange={(e) => {
                  setProposeValueText(e.target.value);
                  setProposeError(null);
                }}
              />
              <p className="note-form-hint">
                Entered as JSON so the type is never guessed: a text value is quoted,
                for example <span className="mono">&quot;CuO&quot;</span>. This does
                not write the value — it stores a proposal for someone to accept or
                reject on the Ingestion Proposals screen.
              </p>
            </>
          )}

          {proposeError !== null && (
            <p className="note-form-error" role="alert">
              {proposeError}
            </p>
          )}

          <div className="note-form-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={
                busy ||
                proposeBusy ||
                proposeFieldPath === '' ||
                proposeValueText.trim() === '' ||
                (proposeNeedsRun && proposeRunId === '')
              }
              onClick={() => void runPropose()}
            >
              {proposeBusy ? 'Proposing…' : 'Propose This Value'}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => closeForm('propose', true)}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </article>
  );
}
