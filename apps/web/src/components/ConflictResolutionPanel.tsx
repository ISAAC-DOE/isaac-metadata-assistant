/*
 * CONFLICTING EVIDENCE — the surface where a person can finally say which answer
 * they stand behind.
 *
 * ── THE DEFECT THIS PANEL EXISTS TO CLOSE ────────────────────────────────────
 *
 * `evidence_classify` flags an address the moment two distinct non-null answers
 * are recorded against it, and NOTHING in this application removes an evidence
 * entry: `POST .../answers` and `POST .../edit` each APPEND a user confirmation.
 * So a scientist who answers a question, notices a typo and answers it again has
 * manufactured a `conflicting_evidence` finding that persists forever. The
 * backend to clear it shipped; no screen called it, and the Evidence Support
 * panel one section above this one told the reader to "review the conflicting
 * sources and resolve them" with no control anywhere behind that instruction.
 *
 * ── WHAT A DECISION IS, AND THE FOUR THINGS IT IS NOT ────────────────────────
 *
 * It records WHICH of the already-recorded answers a person stands behind.
 *
 *   1. IT DOES NOT CHANGE THE FIELD'S VALUE. The backend deliberately does not do
 *      that — writing a value into a field has exactly one path in this
 *      application (a confirmed answer or correction, stored as user-confirmation
 *      evidence), and a decision is not a second one. Every place this panel names
 *      a decision it says so, because the single most likely misreading of this
 *      screen is that choosing a value applied it.
 *   2. IT REMOVES NOTHING. The competing citations stay exactly where they are, so
 *      a decided address is STILL LISTED here and still classifies as conflicting.
 *      `resolution_state` is what a reader branches on, never the absence of a row.
 *   3. IT DOES NOT BLOCK OR UNBLOCK ANYTHING. `POST .../submit`'s own contract says
 *      evidence conflicts "are reported, not blocked on" — blocking would refuse a
 *      record forever for the act of fixing a typo. So this panel never says
 *      "before export" and never presents a conflict as a gate.
 *   4. IT PICKS NO WINNER. Nothing here pre-selects a candidate, orders them by
 *      persuasiveness, marks one as likely, or fills the form from a previous
 *      decision when revising. The server's own ordering is preserved verbatim and
 *      is alphabetical by stored answer text — see {@link CandidateChoice}.
 *
 * ── THE THREE STATES THAT LOOK DECIDED AND ARE NOT ───────────────────────────
 *
 * `absent` (nobody decided), `stale` (a decision made over a DIFFERENT set of
 * answers — further competing evidence arrived since, so it no longer covers what
 * is on screen) and `deferred` (a person looked and declined to decide) are all
 * UNRESOLVED, and only `current` clears a conflict. The server writes
 * `counts.unresolved` out rather than leaving it to subtraction for exactly this
 * reason, and this panel reads that number rather than deriving a second one.
 *
 * A superseded decision is KEPT AND SHOWN, never deleted — both in the `stale`
 * case and in the append-only history of a revised one.
 *
 * ── SCOPE ───────────────────────────────────────────────────────────────────
 *
 * The record's own fields, or ONE run's own fields. An address a run inherits is
 * decided once, at the record, so it is described there and not under each run —
 * otherwise one disagreement could collect two decisions with different `run_id`s.
 * The run list is read for the selector; if that read fails the panel keeps
 * working at record scope and says the run scopes could not be listed, rather than
 * failing the whole section for a control.
 *
 * ── ONE VALIDATOR, THE RECORD'S ─────────────────────────────────────────────
 *
 * A decision is stored inside the experiment's own document, so every write here
 * carries the EXPERIMENT's version token even when the decision is about a run.
 * The token is re-read from each write's own response, and a 412 ADOPTS the
 * version the server reports and refreshes SILENTLY — the arrangement
 * `UnmappedNotesPanel` documents, for the reason it documents: the alternative is
 * a permanent dead end whose only escape destroys what the reader typed.
 *
 * NOTHING TYPED IS EVER DESTROYED BY A REFUSAL. A refused write leaves the
 * selection, the typed value and the rationale exactly where they are; only a
 * decision the server RECORDED clears the form that produced it.
 */
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';

import { api, ApiError } from '../lib/api';
import { mutationFailureCopy, staleWriteCurrentVersion } from '../lib/mutationErrors';
import { RUNS_PAGE_SIZE } from '../lib/runPaging';
import { SourceTypeToken } from './EvidenceRow';
import { DiscardStaged } from './DiscardStaged';
import { DISCARD_COPY } from '../lib/discardContent';
import type {
  ApiConflict,
  ApiConflictCandidate,
  ApiConflictResolution,
  ApiConflictsResponse,
  ApiResolutionState,
  ApiResolutionTransition,
  SourceType,
} from '../lib/types';
import './conflicts.css';

/** Same narrowing `UnmappedNotesPanel` uses — a non-`ApiError` throw still renders. */
function asApiError(err: unknown): ApiError {
  return err instanceof ApiError
    ? err
    : new ApiError(err instanceof Error ? err.message : String(err));
}

/**
 * What each state MEANS, in a sentence that says whether the conflict stands.
 *
 * Every one of the three unresolved states says so IN WORDS. Three modules on the
 * backend go out of their way to keep `deferred` from reading as a clearance
 * ("it does NOT clear the conflict", said three times in three files), and a chip
 * that merely looked different from `absent` would undo that in one glance.
 */
const STATE_COPY: Record<ApiResolutionState, { chip: string; standing: string }> = {
  absent: {
    chip: 'Not yet decided',
    standing: 'Nobody has recorded a decision about these answers.',
  },
  current: {
    chip: 'Decided',
    standing:
      'A decision covers exactly the answers listed here. It records which value is stood behind — it did not change the field’s value, and the competing entries are all still recorded.',
  },
  stale: {
    chip: 'Superseded — undecided again',
    standing:
      'A decision was recorded, but further competing evidence has arrived since, so it was made over a different set of answers and no longer covers this disagreement. This address is UNRESOLVED. The earlier decision is kept below, not deleted.',
  },
  deferred: {
    chip: 'Looked at, left undecided',
    standing:
      'Somebody looked at this and declined to decide. That is a recorded outcome in its own right, and it does NOT clear the conflict — this address is still UNRESOLVED.',
  },
};

/** Only one state clears a conflict. Read from the server's own vocabulary word. */
const isDecided = (state: ApiResolutionState): boolean => state === 'current';

/**
 * A stored answer as text.
 *
 * A string is shown as the scientist wrote it; anything else is JSON, because the
 * alternative is `[object Object]`. This is DISPLAY ONLY — nothing derived from it
 * is ever sent back. See `api.resolveConflict` for why the canonical form is never
 * recomputed on this side.
 */
function displayValue(value: unknown): string {
  return typeof value === 'string' ? value : JSON.stringify(value) ?? 'null';
}

/**
 * The disclosure for a candidate whose citation count and source list disagree.
 *
 * `evidence_count` counts every entry asserting the value; the safe projection
 * SKIPS an entry that names no source type, because there is nothing safe to name.
 * So a candidate can read "1 evidence entry" beside an empty source list, and a
 * reader who assumed the two were the same number would conclude a citation had
 * been withheld from them. The server states the difference as
 * `uncited_evidence_count` precisely so it does not have to be inferred; this
 * renders it rather than letting two numbers look like a discrepancy.
 */
function uncitedClause(candidate: ApiConflictCandidate): string {
  const n = candidate.uncited_evidence_count;
  if (n <= 0) return '';
  const entry = n === 1 ? 'entry' : 'entries';
  const names = n === 1 ? 'names' : 'name';
  return ` · ${n} ${entry} of the ${candidate.evidence_count} ${names} no source that can be shown safely, so nothing was withheld here — there is nothing to cite`;
}

/** `sources` carries whatever the server sent; an unknown type still renders. */
function sourceTypeOf(source: { source_type: string }): SourceType {
  return source.source_type as SourceType;
}

/**
 * What a 412 means here. Copy shared with `UnmappedNotesPanel`'s rule rather than
 * its literal: the panels describe different acts, and the claim that matters —
 * nothing was lost and nothing you typed was discarded — has to be true of THIS
 * panel's forms, which it is (see `submit` below).
 */
const STALE_WRITE_COPY =
  'The record changed since this section was loaded, so that decision was not recorded — it can be your own edit elsewhere on this screen. Nothing was lost: this section has picked up the current version, and your selection and anything you typed are still here, so try again.';

type ListState =
  | { status: 'loading' }
  | { status: 'error'; error: ApiError }
  | { status: 'data'; loaded: ApiConflictsResponse };

type RunsState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'data'; runs: { id: string; label: string }[] };

/** What one row asked for, and what came back. Keyed by the row's own key. */
interface RowFailure {
  key: string;
  /** The server's OWN sentence for this refusal, never a generic one. */
  message: string;
  /** The server's typed error code, when it sent one. Shown, not interpreted. */
  code: string | null;
}

/**
 * The typed refusal these two operations produce.
 *
 * `_conflict_refusal` in `routes.py` answers every bad request with
 * `{error, message, …}`, and its docstring says it is deliberately NOT the same
 * helper as the note routes' — "a shared helper would make the claim unverifiable
 * for either feature". This reader is local for the same reason: it is about ONE
 * contract, and a generic one in `mutationErrors.ts` would be a promise about
 * every route.
 *
 * Fail-closed and duck-typed, exactly as that module's helpers are: an
 * unrecognised body returns `null` and the caller falls back to a sentence that
 * claims less.
 */
function typedRefusal(err: unknown): { code: string; message: string } | null {
  if (typeof err !== 'object' || err === null) return null;
  if ((err as { status?: unknown }).status !== 422) return null;
  const body = (err as { body?: unknown }).body;
  if (typeof body !== 'object' || body === null) return null;
  const code = (body as { error?: unknown }).error;
  const message = (body as { message?: unknown }).message;
  if (typeof code !== 'string' || typeof message !== 'string' || message === '') return null;
  return { code, message };
}

/** The row key. Scope-qualified, so switching scope cannot reuse a row's state. */
const rowKey = (conflict: ApiConflict): string =>
  `${conflict.run_id ?? ''}::${conflict.address}`;

export function ConflictResolutionPanel({ experimentId }: { experimentId: string }) {
  return (
    <section className="conflicts" aria-labelledby="conflicting-evidence-heading">
      <div className="conflicts-head">
        <h2 className="conflicts-title" id="conflicting-evidence-heading">
          Conflicting Evidence
        </h2>
        <p className="conflicts-sub">
          Addresses whose own evidence records more than one different answer, with
          every competing answer and the citations behind it. Recording a decision
          says which value you stand behind; it does not change the field’s value,
          it removes no evidence, and a conflict blocks neither export nor
          submission.
        </p>
      </div>
      {/* Keyed on the record, so switching records rebuilds this panel's state
          rather than showing one record's disagreements under another's heading. */}
      <ConflictBrowser key={experimentId} experimentId={experimentId} />
    </section>
  );
}

function ConflictBrowser({ experimentId }: { experimentId: string }) {
  const [list, setList] = useState<ListState>({ status: 'loading' });
  const [runsState, setRunsState] = useState<RunsState>({ status: 'loading' });
  /** `null` = the record's own fields. Never inferred from the only run. */
  const [scope, setScope] = useState<string | null>(null);
  const [version, setVersion] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [failure, setFailure] = useState<RowFailure | null>(null);
  const [announcement, setAnnouncement] = useState('');

  /** Discards an out-of-order response rather than letting it overwrite a newer one. */
  const generationRef = useRef(0);
  /** Suppresses the loading blank on a reload this panel caused itself. */
  const silentRef = useRef(false);

  const scopeSelectId = useId();

  useEffect(() => {
    let alive = true;
    api
      .listRuns(experimentId, { limit: RUNS_PAGE_SIZE })
      .then((page) => {
        if (!alive) return;
        setRunsState({
          status: 'data',
          runs: page.runs.map((run) => ({ id: run.id, label: run.label })),
        });
      })
      // NON-BLOCKING. The run list only draws a scope control; failing the whole
      // section because a control could not be drawn would hide the record's own
      // conflicts for a reason that has nothing to do with them.
      .catch(() => {
        if (alive) setRunsState({ status: 'error' });
      });
    return () => {
      alive = false;
    };
  }, [experimentId]);

  useEffect(() => {
    let alive = true;
    const generation = ++generationRef.current;
    if (!silentRef.current) setList({ status: 'loading' });
    silentRef.current = false;

    api
      .listConflicts(experimentId, scope === null ? {} : { runId: scope })
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
  }, [experimentId, scope, reloadNonce]);

  const reload = useCallback((silent: boolean) => {
    silentRef.current = silent;
    setReloadNonce((n) => n + 1);
  }, []);

  /**
   * Turn a refused write into something a reader can act from.
   *
   * THREE BRANCHES, EACH CLAIMING ONLY WHAT IT KNOWS.
   *
   *  - A 412 adopts the version the server reported and refreshes SILENTLY, so the
   *    counts and states catch up while every open form, and everything typed into
   *    one, stays exactly where it is.
   *  - A typed 422 renders THE SERVER'S OWN SENTENCE, with its error code beside
   *    it. This is the one that matters most on this panel: fifteen distinct
   *    refusals exist, and "that could not be recorded" would tell a scientist
   *    nothing about which one they hit or what to change.
   *  - Anything else falls through to `mutationFailureCopy`, which names an ended
   *    session where a signal establishes one and otherwise returns the caller's
   *    own sentence. It never reinterprets a failure it cannot name.
   */
  const describeFailure = useCallback(
    (err: unknown, key: string, fallback: string): RowFailure => {
      const current = staleWriteCurrentVersion(err);
      if (current !== null) {
        setVersion(current);
        reload(true);
        return { key, message: STALE_WRITE_COPY, code: 'stale_write' };
      }
      const refusal = typedRefusal(err);
      if (refusal !== null) {
        return { key, message: refusal.message, code: refusal.code };
      }
      return { key, message: mutationFailureCopy(asApiError(err), fallback), code: null };
    },
    [reload],
  );

  /**
   * Record one decision and refresh.
   *
   * THE REFRESH IS NOT A PATCH-IN-PLACE. The response carries the decision, but the
   * per-state counts and the record's version have both moved, and splicing the
   * decision into local state while leaving the counts stale would put two
   * disagreeing numbers on one screen.
   *
   * RETHROWN ON FAILURE, exactly as `UnmappedNotesPanel.review` rethrows and for the
   * same reason: the row has to be able to tell "recorded" from "refused", because
   * the form that carries the selection and the typed value clears itself only on
   * the first.
   */
  const submit = useCallback(
    async (
      conflict: ApiConflict,
      decision: {
        outcome: 'resolved' | 'deferred';
        chosenValue?: unknown;
        chosenFrom?: 'candidate' | 'edited';
        rationale?: string;
      },
      announce: string,
    ) => {
      if (!version) return;
      const key = rowKey(conflict);
      setBusyKey(key);
      setFailure(null);
      try {
        const written = await api.resolveConflict(experimentId, {
          experimentVersion: version,
          address: conflict.address,
          ...(conflict.run_id ? { runId: conflict.run_id } : {}),
          ...decision,
        });
        /*
         * ADOPTED FROM THIS WRITE'S OWN RESPONSE, not left to arrive with the
         * refetch. Between the two the held token is one revision stale and every
         * other row's controls are live, so a scientist deciding two addresses
         * quickly would have the second refused by a 412 this component's own
         * bookkeeping manufactured.
         */
        setVersion(written.experiment_version);
        setAnnouncement(announce);
        reload(true);
      } catch (err: unknown) {
        setFailure(
          describeFailure(
            err,
            key,
            'That decision could not be recorded. Nothing was written, and the evidence is unchanged.',
          ),
        );
        setAnnouncement('');
        throw err;
      } finally {
        setBusyKey(null);
      }
    },
    [experimentId, version, reload, describeFailure],
  );

  /**
   * The last successfully loaded page, kept across a reload.
   *
   * The live region and the counts must stay MOUNTED to be announced at all — a
   * region unmounted and remounted with new content is not read out.
   */
  const lastLoadedRef = useRef<ApiConflictsResponse | null>(null);
  if (list.status === 'data') lastLoadedRef.current = list.loaded;
  const loaded = list.status === 'data' ? list.loaded : lastLoadedRef.current;

  const countLine = useMemo(() => {
    if (!loaded) return '';
    const { counts } = loaded;
    const addresses = `${counts.conflicting_addresses} ${
      counts.conflicting_addresses === 1 ? 'address' : 'addresses'
    } in conflict`;
    /*
     * `unresolved` IS THE SERVER'S NUMBER, not a subtraction done here. It counts
     * every address that is not `current` — the `stale` and `deferred` ones
     * included — and the backend writes it out explicitly because deriving it at
     * three call sites is how three call sites come to disagree about whether a
     * superseded decision still counts as unresolved. It does.
     */
    return (
      `${addresses} · ${counts.unresolved} still unresolved · ${counts.resolved} decided` +
      ` · ${counts.stale} superseded · ${counts.deferred} left undecided`
    );
  }, [loaded]);

  const runs = runsState.status === 'data' ? runsState.runs : [];

  return (
    <div className="conflicts-browser">
      <div className="conflicts-toolbar">
        {runs.length > 0 && (
          <div className="conflicts-control">
            <label className="conflicts-control-label" htmlFor={scopeSelectId}>
              Fields described
            </label>
            <select
              id={scopeSelectId}
              className="conflicts-scope"
              value={scope ?? ''}
              onChange={(e) => setScope(e.target.value === '' ? null : e.target.value)}
            >
              <option value="">This record’s own fields</option>
              {runs.map((run) => (
                <option key={run.id} value={run.id}>
                  {run.label}
                </option>
              ))}
            </select>
          </div>
        )}
        {/*
          MOUNTED IN EVERY STATE, and blanked rather than left stale while a reload
          is in flight — a live region remounted with its content is never
          announced, and holding the previous scope's numbers is worse than none.
        */}
        <p className="conflicts-count" aria-live="polite" aria-atomic="true">
          {list.status === 'loading' ? '' : countLine}
        </p>
      </div>

      {runsState.status === 'error' && (
        <p className="conflicts-disclosure" role="note">
          This record’s runs could not be listed, so only the record’s own fields are
          described here. A run’s own fields may hold disagreements this view is not
          showing.
        </p>
      )}

      {/*
        The ACT announcement, separate from the counts. A screen-reader user who
        records a decision needs to hear WHAT was recorded and that the evidence was
        left alone; the count line cannot carry that.
      */}
      <p className="sr-only" role="status" aria-live="polite">
        {announcement}
      </p>

      {list.status === 'loading' && (
        <p className="conflicts-loading" role="status">
          Loading this record’s conflicting evidence from the ISAAC API…
        </p>
      )}

      {list.status === 'error' && (
        <div className="conflicts-down" role="note">
          <p>
            The conflicting evidence could not be read, so this section is not
            describing this record. Nothing was changed.
          </p>
          <p className="conflicts-down-detail">{list.error.message}</p>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => reload(false)}
          >
            Retry This Section
          </button>
        </div>
      )}

      {list.status === 'data' && (
        <>
          {list.loaded.unreadable_resolution_entries > 0 && (
            <p className="conflicts-disclosure" role="note">
              {list.loaded.unreadable_resolution_entries} recorded{' '}
              {list.loaded.unreadable_resolution_entries === 1 ? 'decision' : 'decisions'}{' '}
              stored on this record could not be read by this build. They are kept on
              the record untouched and counted here rather than shown, because saying
              what one contains would mean inventing it.
            </p>
          )}

          {list.loaded.resolutions_without_conflict.length > 0 && (
            <div className="conflicts-disclosure" role="note">
              <p>
                Decisions recorded at addresses this view carries no conflict at.
                They are reported rather than silently omitted:
              </p>
              <ul className="conflicts-orphans">
                {list.loaded.resolutions_without_conflict.map((entry) => (
                  <li key={entry.resolution_id}>
                    <span className="mono">{entry.address}</span> — recorded as{' '}
                    {entry.outcome === 'resolved' ? 'decided' : 'left undecided'}
                    {entry.orphaned_run
                      ? ' · the run this decision belongs to has been removed from this record, so it is reachable from no run view'
                      : ''}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {list.loaded.conflicts.length === 0 ? (
            <p className="conflicts-empty" role="note">
              No address in this view records two different answers. That is a
              statement about this record’s evidence only — it is not a validity,
              completeness or export verdict, and none of those is decided here.
            </p>
          ) : (
            <ul className="conflicts-list">
              {list.loaded.conflicts.map((conflict) => {
                const key = rowKey(conflict);
                return (
                  <li key={key}>
                    <ConflictRow
                      conflict={conflict}
                      runLabel={
                        conflict.run_id === null
                          ? null
                          : (runs.find((r) => r.id === conflict.run_id)?.label ??
                            conflict.run_id)
                      }
                      busy={busyKey === key || version === null}
                      failure={failure?.key === key ? failure : null}
                      onSubmit={submit}
                      /* THIS PANEL'S ONE ACT-ANNOUNCEMENT CHANNEL, above. Discarding a
                         decision form is an act, and its outcome belongs in the same
                         region a recorded decision's does. */
                      onAnnounce={setAnnouncement}
                    />
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

/**
 * The selection model. `none` IS THE STARTING STATE AND IT IS NEVER LEFT BY
 * DEFAULT — see the rule in the module header and {@link CandidateChoice}.
 */
type Choice =
  | { kind: 'none' }
  | { kind: 'candidate'; index: number }
  | { kind: 'edited' }
  | { kind: 'defer' };

const NO_CHOICE: Choice = { kind: 'none' };

/** The radio's `value`, which is the only place a choice is encoded as a string. */
function choiceToValue(choice: Choice): string {
  if (choice.kind === 'candidate') return `candidate:${choice.index}`;
  if (choice.kind === 'edited') return 'edited';
  if (choice.kind === 'defer') return 'defer';
  return '';
}

function ConflictRow({
  conflict,
  runLabel,
  busy,
  failure,
  onSubmit,
  onAnnounce,
}: {
  conflict: ApiConflict;
  /** `null` when this address belongs to the record's own fields. */
  runLabel: string | null;
  busy: boolean;
  failure: RowFailure | null;
  onSubmit: (
    conflict: ApiConflict,
    decision: {
      outcome: 'resolved' | 'deferred';
      chosenValue?: unknown;
      chosenFrom?: 'candidate' | 'edited';
      rationale?: string;
    },
    announce: string,
  ) => Promise<void>;
  /** Push a sentence into the panel's own `role="status"` region. */
  onAnnounce: (text: string) => void;
}) {
  /*
   * NOTHING IS SELECTED, AND NOTHING EVER BECOMES SELECTED WITHOUT AN ACT.
   *
   * Not on mount, not after a refresh, and NOT WHEN REVISING — a recorded decision
   * is displayed above this form and is deliberately not loaded into it, because a
   * pre-filled radio is a recommendation whatever its provenance, and because the
   * whole point of revising is that the earlier answer is under question.
   */
  const [choice, setChoice] = useState<Choice>(NO_CHOICE);
  const [editedValue, setEditedValue] = useState('');
  const [rationale, setRationale] = useState('');
  const [confirmed, setConfirmed] = useState(false);

  const groupId = useId();
  const editedId = useId();
  const rationaleId = useId();
  const confirmId = useId();
  const failureId = useId();
  const editedHintId = useId();

  const state = conflict.resolution_state;
  const copy = STATE_COPY[state];

  const editedReady = editedValue.trim() !== '';
  const chosen =
    choice.kind === 'candidate'
      ? conflict.candidates[choice.index]
      : undefined;
  const ready =
    !busy &&
    confirmed &&
    (choice.kind === 'defer' ||
      (choice.kind === 'candidate' && chosen !== undefined) ||
      (choice.kind === 'edited' && editedReady));

  const revising = conflict.resolution !== null;

  /*
   * THE FOUR INPUTS OF THIS FORM, AND ONE CONTROL THAT EMPTIES THEM.
   *
   * There was no way to put this form back to its resting state. Every input is
   * deliberately sticky — nothing is pre-selected, a refusal clears nothing (the empty
   * `catch` below is the whole mechanism by which a refusal is not also a data loss),
   * and the only path that clears them is a decision the server RECORDED. So a reader
   * who selected an answer, typed a value and wrote a paragraph of reasoning, and then
   * decided they were not the person to decide this, had to undo each of the four by
   * hand — and could not unselect a radio at all.
   *
   * `confirmed` is reset with the rest. It is the "I am recording this decision myself"
   * attestation, and leaving it ticked over emptied inputs would carry an assertion
   * across an act that withdrew everything it was about.
   *
   * NOTHING IS SENT. The decision this clears was never recorded, so there is nothing
   * to withdraw at the server and no request that would mean anything — see
   * `DiscardStaged`, which cannot make one.
   */
  const hasStagedDecision =
    choice.kind !== 'none' || editedValue !== '' || rationale !== '' || confirmed;
  const discardStagedDecision = () => {
    setChoice(NO_CHOICE);
    setEditedValue('');
    setRationale('');
    setConfirmed(false);
  };

  const run = async () => {
    if (!ready) return;
    const decision =
      choice.kind === 'defer'
        ? ({ outcome: 'deferred' } as const)
        : choice.kind === 'edited'
          ? ({
              outcome: 'resolved',
              chosenValue: editedValue,
              chosenFrom: 'edited',
            } as const)
          : ({
              outcome: 'resolved',
              // THE SERVER'S OWN `value`, ROUND-TRIPPED UNTOUCHED. See
              // `api.resolveConflict`: canonicalising on this side would be a second
              // definition of "the same value".
              chosenValue: chosen!.value,
              chosenFrom: 'candidate',
            } as const);
    const announce =
      choice.kind === 'defer'
        ? `Recorded that ${conflict.address} was looked at and left undecided. This does not clear the conflict, and no evidence was changed.`
        : `Recorded that ${conflict.address} stands behind ${displayValue(
            choice.kind === 'edited' ? editedValue : chosen!.value,
          )}. The field’s value was not changed and no evidence was removed.`;
    try {
      await onSubmit(
        conflict,
        { ...decision, ...(rationale.trim() === '' ? {} : { rationale }) },
        announce,
      );
      // RECORDED, so the inputs this act consumed are cleared. A refusal reaches
      // the `catch` below and clears nothing at all.
      setChoice(NO_CHOICE);
      setEditedValue('');
      setRationale('');
      setConfirmed(false);
    } catch {
      /*
       * REFUSED. The selection, the typed value and the rationale all stay exactly
       * where they are; the panel's own notice says what happened. This empty catch
       * is the whole mechanism by which a refusal is not also a data loss.
       */
    }
  };

  return (
    <article className="conflict" data-state={state}>
      <header className="conflict-head">
        <span className="conflict-address mono">{conflict.address}</span>
        <span className="conflict-scope">
          {runLabel === null ? 'This record’s own fields' : `Run · ${runLabel}`}
        </span>
        <span
          className="conflict-state"
          data-decided={isDecided(state) ? 'yes' : 'no'}
        >
          {copy.chip}
        </span>
      </header>

      <p className="conflict-standing">{copy.standing}</p>
      {/* The server's own deterministic sentence, rendered rather than paraphrased.
          It names counts and the rule and quotes no value — the values are below,
          where a reader expects scientific content. */}
      <p className="conflict-explanation">{conflict.explanation}</p>

      {conflict.unavailable && (
        <p className="conflicts-disclosure" role="note">
          Part of this entry’s stored evidence could not be read, so the answers
          below may not be the whole disagreement.
        </p>
      )}

      <CandidateChoice
        conflict={conflict}
        groupId={groupId}
        choice={choice}
        onChoose={setChoice}
        editedId={editedId}
        editedHintId={editedHintId}
        editedValue={editedValue}
        onEditedValue={setEditedValue}
        disabled={busy}
        describedBy={failure ? failureId : undefined}
      />

      <div className="conflict-field">
        <label className="conflicts-control-label" htmlFor={rationaleId}>
          Why (optional)
        </label>
        <textarea
          id={rationaleId}
          className="conflict-rationale"
          rows={2}
          value={rationale}
          disabled={busy}
          onChange={(e) => setRationale(e.target.value)}
          placeholder="Stored word for word beside the decision. Left out entirely if you write nothing."
        />
      </div>

      <div className="conflict-confirm">
        <input
          type="checkbox"
          id={confirmId}
          checked={confirmed}
          disabled={busy}
          onChange={(e) => setConfirmed(e.target.checked)}
        />
        <label htmlFor={confirmId}>
          I am recording this decision myself. It will be stored with its history and
          can be revised, and it changes no field value and removes no evidence.
        </label>
      </div>

      {failure && (
        <div className="conflict-failure" role="alert" id={failureId}>
          <p>{failure.message}</p>
          {failure.code !== null && (
            <p className="conflict-failure-code">
              The ISAAC API refused this as <span className="mono">{failure.code}</span>.
            </p>
          )}
        </div>
      )}

      <button
        type="button"
        className="btn btn-primary conflict-submit"
        disabled={!ready}
        aria-describedby={failure ? failureId : undefined}
        onClick={run}
      >
        {revising ? 'Record a Revised Decision' : 'Record This Decision'}
      </button>

      {/* BELOW the primary, quiet: the two are not peers. Recording a decision is the
          act this card exists for; emptying the form is the way out of it. */}
      <DiscardStaged
        staged={hasStagedDecision && !busy}
        copy={DISCARD_COPY.conflictDecision}
        onDiscard={discardStagedDecision}
        onAnnounce={onAnnounce}
      />

      {conflict.resolution !== null && (
        <RecordedDecision resolution={conflict.resolution} />
      )}
    </article>
  );
}

/**
 * The competing answers, and the three things a person may do about them.
 *
 * NOTHING IS PRE-SELECTED AND NOTHING IS RANKED. The candidates are rendered in
 * THE SERVER'S OWN ORDER, which is alphabetical by the stored answer's canonical
 * text — not by citation count, not by which one the field currently holds. That
 * ordering is preserved verbatim precisely because any reordering here would be a
 * recommendation, and three backend modules assert that nothing in this
 * application picks a winner.
 *
 * "A DIFFERENT VALUE" IS A DIFFERENT CLAIM, not a fallback. Picking a recorded
 * answer says "this citation is the right one"; typing a value says "every
 * recorded answer is wrong and the value is this". The server refuses to collapse
 * them, so this control does not either — they are peers, and the typed value is
 * sent as `edited` whatever it happens to equal.
 */
function CandidateChoice({
  conflict,
  groupId,
  choice,
  onChoose,
  editedId,
  editedHintId,
  editedValue,
  onEditedValue,
  disabled,
  describedBy,
}: {
  conflict: ApiConflict;
  groupId: string;
  choice: Choice;
  onChoose: (choice: Choice) => void;
  editedId: string;
  editedHintId: string;
  editedValue: string;
  onEditedValue: (value: string) => void;
  disabled: boolean;
  describedBy: string | undefined;
}) {
  const selected = choiceToValue(choice);
  const orderNoteId = `${groupId}-order`;
  return (
    <fieldset
      className="conflict-choice"
      aria-describedby={[orderNoteId, describedBy].filter(Boolean).join(' ') || undefined}
    >
      <legend className="conflict-choice-legend">
        Which answer do you stand behind?
      </legend>
      <p className="conflict-choice-note" id={orderNoteId}>
        Listed in the order the ISAAC API returned them, which is alphabetical by
        the stored answer and carries no ranking. Nothing is selected for you, and
        the number of citations behind an answer is not a vote.
      </p>
      {conflict.candidates.map((candidate, index) => {
        const value = `candidate:${index}`;
        const metaId = `${groupId}-meta-${index}`;
        return (
          <div className="conflict-candidate" key={candidate.canonical}>
            <input
              type="radio"
              id={`${groupId}-${index}`}
              name={groupId}
              value={value}
              checked={selected === value}
              disabled={disabled}
              aria-describedby={metaId}
              onChange={() => onChoose({ kind: 'candidate', index })}
            />
            <label htmlFor={`${groupId}-${index}`} className="conflict-candidate-label">
              <span className="conflict-candidate-value mono">
                {displayValue(candidate.value)}
              </span>
            </label>
            <p className="conflict-candidate-meta" id={metaId}>
              {candidate.evidence_count}{' '}
              {candidate.evidence_count === 1 ? 'evidence entry' : 'evidence entries'}{' '}
              assert this answer{uncitedClause(candidate)}
            </p>
            {candidate.sources.length > 0 && (
              <div className="conflict-sources" aria-label="Safe source references">
                {candidate.sources.map((source, i) => (
                  <span className="conflict-source" key={`${source.source_type}-${i}`}>
                    <SourceTypeToken sourceType={sourceTypeOf(source)} />
                    {source.locator && (
                      <span className="conflict-locator">{source.locator}</span>
                    )}
                  </span>
                ))}
              </div>
            )}
          </div>
        );
      })}

      <div className="conflict-candidate">
        <input
          type="radio"
          id={`${groupId}-edited`}
          name={groupId}
          value="edited"
          checked={selected === 'edited'}
          disabled={disabled}
          onChange={() => onChoose({ kind: 'edited' })}
        />
        <label htmlFor={`${groupId}-edited`} className="conflict-candidate-label">
          A different value — none of the recorded answers is right
        </label>
        {selected === 'edited' && (
          <div className="conflict-edited">
            <label className="conflicts-control-label" htmlFor={editedId}>
              The value you stand behind
            </label>
            <input
              type="text"
              id={editedId}
              className="conflict-edited-input"
              value={editedValue}
              disabled={disabled}
              aria-describedby={editedHintId}
              onChange={(e) => onEditedValue(e.target.value)}
            />
            <p className="conflict-choice-note" id={editedHintId}>
              Recorded as text, exactly as typed. It is stored as the value you stand
              behind — it does not become the field’s value, and it adds no evidence.
              To change what the record says, answer or correct the field itself.
            </p>
          </div>
        )}
      </div>

      <div className="conflict-candidate">
        <input
          type="radio"
          id={`${groupId}-defer`}
          name={groupId}
          value="defer"
          checked={selected === 'defer'}
          disabled={disabled}
          onChange={() => onChoose({ kind: 'defer' })}
        />
        <label htmlFor={`${groupId}-defer`} className="conflict-candidate-label">
          I looked and I am not deciding yet
        </label>
        {selected === 'defer' && (
          <p className="conflict-choice-note">
            Recorded as a decision to defer. It does NOT clear this conflict — the
            address stays in this list as unresolved, and every competing answer
            stays exactly where it is.
          </p>
        )}
      </div>
    </fieldset>
  );
}

/**
 * The decision already on the record, WITH the acts that produced it.
 *
 * Shown in full whatever its state, and shown BESIDE the form rather than inside
 * it. A superseded decision is the thing this feature promises not to lose: a
 * `stale` one is kept and displayed under a heading that says it no longer covers
 * the answers above, and every revision keeps the value it superseded.
 */
function RecordedDecision({ resolution }: { resolution: ApiConflictResolution }) {
  const headingId = useId();
  return (
    <div className="conflict-decision" aria-labelledby={headingId}>
      <h3 className="conflict-decision-title" id={headingId}>
        {resolution.stale ? 'The decision that was superseded' : 'The decision on record'}
      </h3>
      <dl className="conflict-decision-list">
        <dt>Outcome</dt>
        <dd>
          {resolution.outcome === 'resolved'
            ? 'A value was chosen'
            : 'Looked at and left undecided'}
        </dd>

        <dt>Value stood behind</dt>
        <dd>
          {resolution.outcome === 'resolved' ? (
            <>
              <span className="mono">{displayValue(resolution.chosen_value)}</span>
              {resolution.chosen_from === 'edited'
                ? ' — typed in, because none of the recorded answers was right'
                : ' — one of the answers already recorded against this address'}
            </>
          ) : (
            'None. A deferred decision records that nobody chose.'
          )}
        </dd>

        <dt>Reason given</dt>
        <dd>{resolution.rationale ?? 'None was written, and none was composed on anybody’s behalf.'}</dd>

        <dt>Recorded</dt>
        <dd>{resolution.recorded_utc}</dd>

        <dt>By</dt>
        <dd>
          {resolution.attributed && resolution.subject !== null
            ? resolution.subject
            : 'Nobody is named. This deployment establishes no identity, so the decision is recorded as unattributed rather than under a name nothing vouched for.'}
        </dd>
      </dl>

      <p className="conflict-decision-note">
        This is a record of a choice. It is not the field’s value and not an evidence
        entry — the ISAAC API states both on the wire — and the competing entries it
        was decided between are all still on the record.
      </p>

      <h4 className="conflict-history-title">
        History — {resolution.history.length}{' '}
        {resolution.history.length === 1 ? 'act' : 'acts'}, appended, never rewritten
      </h4>
      <ol className="conflict-history">
        {resolution.history.map((entry, index) => (
          <li key={`${entry.action}-${entry.at}-${index}`}>
            <TransitionLine entry={entry} />
          </li>
        ))}
      </ol>
    </div>
  );
}

/**
 * One act, in words.
 *
 * A REVISION NAMES WHAT IT SUPERSEDED, which is what makes "appends rather than
 * replaces" visible rather than merely claimed. `superseded_chosen_value` is
 * `null` on its own for two different reasons — a revision away from `deferred`
 * genuinely superseded no value — and `from_outcome` is what disambiguates them,
 * so it is read rather than the null being reported bare.
 */
function TransitionLine({ entry }: { entry: ApiResolutionTransition }) {
  const outcomeWord = (outcome: string) =>
    outcome === 'resolved' ? 'a chosen value' : 'left undecided';
  if (entry.action === 'record') {
    return (
      <>
        <span className="conflict-history-at">{entry.at}</span> — first recorded as{' '}
        {outcomeWord(entry.to_outcome)}.
      </>
    );
  }
  return (
    <>
      <span className="conflict-history-at">{entry.at}</span> — revised from{' '}
      {outcomeWord(entry.from_outcome ?? '')} to {outcomeWord(entry.to_outcome)}.{' '}
      {entry.from_outcome === 'deferred' ? (
        <>The decision it replaced chose no value, so nothing was superseded.</>
      ) : (
        <>
          It superseded{' '}
          <span className="mono">{displayValue(entry.superseded_chosen_value)}</span>,
          which is kept here rather than overwritten.
        </>
      )}
    </>
  );
}
