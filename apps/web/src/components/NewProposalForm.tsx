/*
 * NEW PROPOSAL — the creation surface on the Ingestion Proposals panel itself.
 *
 * WHY IT EXISTS, IN THE PROJECT OWNER'S WORDS (2026-09-15): "there's no way to
 * actually add an ingestion proposal … there should at least be a service button to
 * the point of at least I can show, okay, this is something that can be added once
 * the blocker is removed."
 *
 * THE PREMISE OF THAT REQUEST WAS MEASURED AND IS FALSE, WHICH IS WHY THIS IS A REAL
 * FORM AND NOT A DISABLED PLACEHOLDER. `POST /api/experiments/{id}/proposals` is a
 * registered, working route; it was exercised over HTTP against a local backend on a
 * record created through `POST /api/experiments`, in both scopes, and it answered
 * `200` with `state: "open"`, `verified: false`, `is_evidence: false`,
 * `is_field_value: false` — and the record's `technique` still read `None`
 * afterwards. Nothing about CREATION is blocked. What IS blocked is ACCEPTANCE
 * (`409 human_actor_required`, a configuration fact — no trusted authentication
 * boundary exists in this build), and that is disclosed below rather than hidden or
 * faked.
 *
 * WHAT WAS ACTUALLY MISSING WAS DISCOVERABILITY, NOT CAPABILITY. The act already
 * existed — `UnmappedNotesPanel`'s per-note "Propose a Value from This Note", PR-D,
 * 2026-09-03 — but only inside one note's collapsed action row, one panel up, and
 * only for a record that already holds a note. A reader looking at the proposals
 * queue saw no way in at all, which is exactly what the owner reported.
 *
 * ~~"This panel still has NO create control of its own — a review surface that
 * manufactured the queue it reviews would be reviewing itself."~~ — WITHDRAWN
 * 2026-09-15, and struck rather than deleted because it was a deliberate design
 * decision and a future session must see that it was reversed, not forgotten. The
 * argument it made survives in the one place it was really about: nothing here
 * REVIEWS what it creates. A proposal minted here lands `open`, is decided by the
 * same review acts as any other, and this form has no path to accept, reject or
 * supersede anything. What the old rule actually cost was a scientist who could not
 * find the door.
 *
 * THE NOTE ANCHOR IS NOT A FORMALITY AND IS NOT BYPASSED. `note_id` is required by
 * the server, and the reason is the feature's whole point: the verbatim words live
 * on a note that survives every outcome including rejection, so refusing a proposal
 * can never destroy the content behind it. This form therefore offers exactly two
 * ways to satisfy it — cite a note this record already holds, or write a source note
 * now and propose from that — and no third way that invents a value from nowhere.
 * Writing the note is a REAL `POST .../notes`, the same operation the capture box
 * performs, not a hidden field on the proposal.
 *
 * WHAT IT WILL NOT DO:
 *
 *   1. IT NEVER INFERS A RUN. The scope comes from the server's own
 *      `record_scoped_target_field_paths`, never from "there is only one run", and a
 *      run-scoped target with no run chosen is refused HERE, before the request, so
 *      the reader is not sent to the server to be told something this form knows.
 *   2. IT NEVER INVENTS A TARGET OR A SHAPE. Every option in the field picker comes
 *      from the server's `target_field_paths` on this load. A typed control appears
 *      only where `RUN_FIELDS` carries the official schema's declared type for that
 *      path; every other path falls back to JSON, because a guessed type is a guess.
 *   3. IT NEVER CLAIMS THE VALUE WAS WRITTEN. Storing a proposal changes no field,
 *      and the form says so before you submit and again after.
 *   4. IT NEVER LOSES WHAT YOU TYPED. Nothing here is unmounted by a background
 *      refresh, and a refused write leaves every box exactly as it was —
 *      `CLAUDE.md` §11 records this repository shipping the opposite three times.
 */
import { useCallback, useEffect, useId, useRef, useState } from 'react';

import { api } from '../lib/api';
import { LABELS } from '../lib/labels';
import { mutationFailureCopy, staleWriteCurrentVersion } from '../lib/mutationErrors';
import { markSelfMintedProposals } from '../lib/selfMintedProposals';
import { RUNS_PAGE_SIZE } from '../lib/runPaging';
import {
  HUMAN_PROPOSED_RULE,
  parseProposedValue,
  proposalFieldGroup,
  proposalFieldLabel,
  proposalFieldSpec,
  stableValueDigest,
} from '../lib/proposalAuthoring';
import type { ApiNote, ApiProposalCreated, ApiRunView } from '../lib/types';

/**
 * WHAT STORING A PROPOSAL DOES AND DOES NOT DO — one string, rendered before the
 * submit control, because the single most likely misreading of this form is that it
 * writes the value. It is the claim `IngestionProposalsPanel`'s own subtitle makes
 * about the queue, said here about the act.
 */
export const NEW_PROPOSAL_EFFECT_CLAIM =
  'Storing this writes no field. Every field on this record, and on every run, is ' +
  'left byte-for-byte unchanged: a proposal is a suggestion awaiting a person’s ' +
  'judgement, it is not a value, not evidence and not a confirmation, and it is ' +
  'inert to export.';

/**
 * ACCEPTANCE IS A DIFFERENT ACT AND IT IS GENUINELY BLOCKED — disclosed here, at the
 * moment a reader is about to create something, rather than left to be discovered on
 * the review card. It is a CONFIGURATION fact, not a build defect and not a bug in
 * this form: no application change can close it.
 */
export const NEW_PROPOSAL_ACCEPTANCE_DISCLOSURE =
  'Creating a proposal works. Accepting one does not, in this deployment: the accept ' +
  'operation answers "human_actor_required" because no trusted authentication ' +
  'boundary is configured, so nothing here can establish who is accepting. That is a ' +
  'fact about how this deployment is configured, not about this record — the ' +
  'proposal is stored either way, and rejecting, superseding and withdrawing are ' +
  'unaffected.';

/**
 * THE UNAVAILABLE CASE, WORDED SO IT NAMES WHAT WOULD ENABLE IT. Reached only when
 * the server reported an EMPTY `target_field_paths` — a real answer, not a failed
 * read — which means this build has no write route for any proposable field. The
 * control is shown in its real place and says so, rather than being hidden (a reader
 * learns nothing from an absence) or offered and then failing (which is worse).
 */
export const NEW_PROPOSAL_UNAVAILABLE_REASON =
  'This deployment reported no proposable field paths at all, so there is nothing a ' +
  'proposal could target. A proposal must name a field this build can eventually ' +
  'write, and the server publishes that list itself — it is not decided here. ' +
  'When a deployment serves a non-empty list, this control becomes a working form ' +
  'with no further change.';

type NotesState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'data'; notes: ApiNote[] };

/** How a note reads in the picker. The verbatim text is the only useful handle. */
function noteOptionLabel(note: ApiNote): string {
  const text = (note.display_text ?? note.text ?? '').replace(/\s+/g, ' ').trim();
  const shown = text.length > 72 ? `${text.slice(0, 71)}…` : text;
  // A note whose text this build could not read is NAMED, never blanked: a blank
  // option is one a reader can see the count of and cannot choose.
  return shown === '' ? `(no readable text) · ${note.id}` : shown;
}

export function NewProposalForm({
  experimentId,
  experimentVersion,
  targetFieldPaths,
  recordScopedTargetFieldPaths,
  onCreated,
  onVersionAdvanced,
  onStaleRecovered,
}: {
  experimentId: string;
  /** The RECORD's current version token, as the last load reported it. */
  experimentVersion: string | null;
  /** The server's own answer to "what may I target?", never transcribed here. */
  targetFieldPaths: string[];
  recordScopedTargetFieldPaths: string[];
  /** Called after the server confirmed the write. The panel adopts the new version,
   *  refreshes SILENTLY and announces; this form does none of those itself. */
  onCreated: (created: ApiProposalCreated) => void;
  /** Called when a FIRST write (the source note) moved the record's version and a
   *  SECOND is still to come, so the panel is never left holding a stale token. */
  onVersionAdvanced: (version: string) => void;
  /** Called with the server's reported current version after a 412, so the panel can
   *  adopt it and refresh. Returns nothing; this form composes its own sentence. */
  onStaleRecovered: (version: string) => void;
}) {
  const fieldId = useId();
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const [sourceMode, setSourceMode] = useState<'existing' | 'new'>('new');
  const [noteId, setNoteId] = useState('');
  const [newNoteText, setNewNoteText] = useState('');
  const [fieldPath, setFieldPath] = useState('');
  const [runId, setRunId] = useState('');
  const [valueText, setValueText] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [notes, setNotes] = useState<NotesState>({ status: 'idle' });
  const [runs, setRuns] = useState<ApiRunView[]>([]);
  const runsFetchedRef = useRef(false);

  /*
   * BOTH READS ARE LAZY AND HAPPEN ON OPEN, NOT ON MOUNT. `RunsSection` already
   * reads this record's runs on first paint and
   * `runs-live-refresh-integration.test.tsx` asserts that happens exactly ONCE, so
   * an eager read here would break an invariant another screen owns. The earliest
   * point either list can matter is the moment a reader opens this form.
   */
  useEffect(() => {
    if (!open) return;
    let alive = true;
    setNotes((prev) => (prev.status === 'data' ? prev : { status: 'loading' }));
    api
      .listNotes(experimentId)
      .then((res) => {
        if (!alive) return;
        setNotes({ status: 'data', notes: res.notes });
        // DEFAULTED ONLY IN THE DIRECTION THAT INVENTS NOTHING. With no note on the
        // record the only possible source is a new one, so that mode is preselected;
        // with notes present the reader chooses, and no note is preselected.
        setSourceMode(res.notes.length === 0 ? 'new' : 'existing');
      })
      .catch(() => {
        if (alive) setNotes({ status: 'error' });
      });
    return () => {
      alive = false;
    };
  }, [open, experimentId]);

  useEffect(() => {
    if (!open || runsFetchedRef.current) return;
    runsFetchedRef.current = true;
    api
      .listRuns(experimentId, { limit: RUNS_PAGE_SIZE })
      .then((res) => setRuns(res.runs))
      .catch(() => {
        // Left empty, which reads as "no runs available" — fail-closed, never letting
        // a reader submit a proposal naming a run this read could not confirm exists.
        // Un-set the guard so a later open may retry.
        runsFetchedRef.current = false;
      });
  }, [open, experimentId]);

  const close = useCallback(
    (discard: boolean) => {
      setOpen(false);
      setError(null);
      if (discard) {
        setNoteId('');
        setNewNoteText('');
        setFieldPath('');
        setRunId('');
        setValueText('');
      }
      triggerRef.current?.focus();
    },
    [],
  );

  const isRecordScoped = recordScopedTargetFieldPaths.includes(fieldPath);
  const needsRun = fieldPath !== '' && !isRecordScoped;
  const spec = proposalFieldSpec(fieldPath);

  const sourceReady =
    sourceMode === 'existing' ? noteId !== '' : newNoteText.trim() !== '';
  const submittable =
    !busy &&
    experimentVersion !== null &&
    fieldPath !== '' &&
    valueText.trim() !== '' &&
    sourceReady &&
    !(needsRun && runId === '');

  const submit = async () => {
    if (!submittable || experimentVersion === null) return;
    /*
     * REFUSED HERE, BEFORE THE REQUEST. A run-scoped target with no run chosen is a
     * thing this form already knows is wrong; sending it to be told
     * `target_requires_a_run` would spend a round trip and a version to learn
     * nothing. The server enforces it too — this does not replace that check, it
     * just does not waste the reader's time reaching it.
     */
    if (needsRun && runId === '') {
      setError(
        'Choose the run this value is about. A value at this field path is applied ' +
          'through a run’s writer, so the proposal must name the run — it is ' +
          'never inferred, even when this record has exactly one run. Nothing was sent.',
      );
      return;
    }
    const parsed = parseProposedValue(fieldPath, valueText);
    if (!parsed.ok) {
      setError(parsed.error);
      return;
    }
    setError(null);
    setBusy(true);
    let version = experimentVersion;
    // Whether an inner handler already composed the sentence. Read instead of the
    // `error` STATE, which the closure captured before this call began and which a
    // `setError` inside the try has not yet updated.
    let reported = false;
    try {
      /*
       * STEP ONE, ONLY WHEN THE READER ASKED FOR IT: store the source note. This is
       * the same `POST .../notes` the capture box performs, with the same
       * `typed_note` source, and the text is sent UNTRIMMED for that operation's own
       * stated reason — trimming in the client would make the server's "stored
       * exactly as sent" promise true of a string the scientist did not write.
       *
       * IT IS TWO REQUESTS AND NOT ONE TRANSACTION, WHICH IS WORTH STATING. If the
       * proposal then fails, the NOTE REMAINS on the record — it is not rolled back,
       * because there is no operation that would un-store it and inventing a delete
       * for a scientist's own words is the last thing this feature should do. The
       * failure message below says so rather than letting a reader think nothing
       * happened.
       */
      let resolvedNoteId = noteId;
      let noteWasStored = false;
      if (sourceMode === 'new') {
        const captured = await api.captureNote(experimentId, {
          experimentVersion: version,
          text: newNoteText,
          source: 'typed_note',
        });
        resolvedNoteId = captured.note.id;
        version = captured.experiment_version;
        noteWasStored = true;
        onVersionAdvanced(version);
      }
      try {
        const created = await api.createProposal(experimentId, {
          experimentVersion: version,
          noteId: resolvedNoteId,
          targetFieldPath: fieldPath,
          proposedValue: parsed.value,
          rule: HUMAN_PROPOSED_RULE,
          ...(needsRun ? { runId } : {}),
          /*
           * BYTE-IDENTICAL TO THE SIBLING SURFACE'S KEY, and that is the point
           * rather than a coincidence. `UnmappedNotesPanel` mints
           * `note-propose:<note>:<path>:<digest>` for the same act, so the same
           * (note, path, value) proposed from either surface dedupes to ONE
           * proposal instead of two. The digest is the shared
           * `stableValueDigest` over the PARSED value, never the raw text, so
           * `300` and ` 300 ` are one act.
           */
          clientRequestKey:
            `note-propose:${resolvedNoteId}:${fieldPath}:` + stableValueDigest(parsed.value),
        });
        // Same-tab courtesy, not a server fact — see `lib/selfMintedProposals.ts`.
        markSelfMintedProposals(experimentId, [created.proposal.proposal_id]);
        onCreated(created);
        close(true);
      } catch (err: unknown) {
        if (noteWasStored) {
          // NAMED, NOT GLOSSED. The reader performed one successful write and one
          // failed one, and a message saying only "that failed" would be false about
          // the first half.
          reported = true;
          setError(
            'Your source note WAS stored on this record and is safe — it is on the ' +
              'Unmapped Notes list above. The proposal that was to cite it was refused, ' +
              'so no proposal exists yet. ' +
              refusalSentence(err),
          );
        } else {
          reported = true;
          setError(refusalSentence(err));
        }
        throw err;
      }
    } catch (err: unknown) {
      // Reached for the NOTE write's own failure (the proposal's is already
      // reported above and rethrown only to skip the success path).
      if (!reported) setError(refusalSentence(err));
    } finally {
      setBusy(false);
    }
  };

  /** A refused write, turned into a sentence a reader can act from. */
  function refusalSentence(err: unknown): string {
    const current = staleWriteCurrentVersion(err);
    if (current !== null) {
      onStaleRecovered(current);
      return (
        'This record changed while you were filling this in, so nothing was written. ' +
        'The panel has caught up with the current version and everything you typed is ' +
        'still here — submit again to store it against the record as it now stands.'
      );
    }
    return mutationFailureCopy(
      err,
      'That proposal could not be stored, and nothing was written.',
    );
  }

  /*
   * THE TRIGGER IS ABSENT ONLY WHEN THE PANEL HAS NEVER LOADED. Once the server has
   * answered, the control is on screen in both outcomes — working when it serves
   * targets, and named-as-unavailable with its reason when it serves none. A control
   * that is simply missing teaches a reader nothing, which is the state the project
   * owner reported.
   */
  if (targetFieldPaths.length === 0) {
    return (
      <div className="new-proposal">
        <div className="new-proposal-bar">
          <span className="new-proposal-unavailable-label">
            {LABELS.newProposalUnavailable}
          </span>
        </div>
        <details className="new-proposal-why">
          <summary>Why?</summary>
          <p className="proposal-form-hint">{NEW_PROPOSAL_UNAVAILABLE_REASON}</p>
        </details>
      </div>
    );
  }

  if (!open) {
    return (
      <div className="new-proposal">
        <div className="new-proposal-bar">
          <button
            type="button"
            ref={triggerRef}
            className="btn btn-primary"
            aria-expanded={false}
            aria-controls={fieldId}
            onClick={() => {
              setOpen(true);
              setError(null);
            }}
          >
            {LABELS.newProposalAction}
          </button>
          <p className="new-proposal-lede">
            Suggest a value for one field, citing the note it was read from. It is
            stored for review and writes nothing.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="new-proposal">
      <div className="new-proposal-bar">
        <button
          type="button"
          ref={triggerRef}
          className="btn btn-primary"
          aria-expanded
          aria-controls={fieldId}
          onClick={() => close(false)}
        >
          {LABELS.newProposalAction}
        </button>
        <p className="new-proposal-lede">
          Suggest a value for one field, citing the note it was read from. It is
          stored for review and writes nothing.
        </p>
      </div>

      <div className="proposal-form new-proposal-form" id={fieldId}>
        {/* --- 1. the source note, the anchor everything else hangs from ------- */}
        <span className="proposal-form-label" id={`${fieldId}-source-label`}>
          {LABELS.newProposalSourceGroup}
        </span>
        <div
          className="new-proposal-source-modes"
          role="radiogroup"
          aria-labelledby={`${fieldId}-source-label`}
        >
          <label className="new-proposal-radio" htmlFor={`${fieldId}-source-existing`}>
            <input
              type="radio"
              id={`${fieldId}-source-existing`}
              name={`${fieldId}-source`}
              checked={sourceMode === 'existing'}
              disabled={notes.status === 'data' && notes.notes.length === 0}
              onChange={() => {
                setSourceMode('existing');
                setError(null);
              }}
            />
            <span>{LABELS.newProposalSourceExisting}</span>
          </label>
          <label className="new-proposal-radio" htmlFor={`${fieldId}-source-new`}>
            <input
              type="radio"
              id={`${fieldId}-source-new`}
              name={`${fieldId}-source`}
              checked={sourceMode === 'new'}
              onChange={() => {
                setSourceMode('new');
                setError(null);
              }}
            />
            <span>{LABELS.newProposalSourceNew}</span>
          </label>
        </div>

        {sourceMode === 'existing' && (
          <>
            {notes.status === 'loading' && (
              <p className="proposal-form-hint">Reading this record&rsquo;s notes&hellip;</p>
            )}
            {notes.status === 'error' && (
              <p className="proposal-form-error" role="alert">
                This record&rsquo;s notes could not be read, so no note can be cited
                right now. Nothing was written. Write a source note instead, or close
                this and try again.
              </p>
            )}
            {notes.status === 'data' && notes.notes.length === 0 && (
              <p className="proposal-form-hint">
                This record holds no notes yet, so there is nothing to cite. Write a
                source note instead — a proposal always names the note its content
                came from, and that note is what keeps the words safe whatever the
                review decides.
              </p>
            )}
            {notes.status === 'data' && notes.notes.length > 0 && (
              <>
                <label className="proposal-form-label" htmlFor={`${fieldId}-note`}>
                  {LABELS.newProposalPickNote}
                </label>
                <select
                  id={`${fieldId}-note`}
                  className="proposal-form-input"
                  value={noteId}
                  onChange={(e) => {
                    setNoteId(e.target.value);
                    setError(null);
                  }}
                >
                  <option value="">Choose a note&hellip;</option>
                  {notes.notes.map((note) => (
                    <option key={note.id} value={note.id}>
                      {noteOptionLabel(note)}
                    </option>
                  ))}
                </select>
              </>
            )}
          </>
        )}

        {sourceMode === 'new' && (
          <>
            <label className="proposal-form-label" htmlFor={`${fieldId}-new-note`}>
              {LABELS.newProposalWriteNote}
            </label>
            <textarea
              id={`${fieldId}-new-note`}
              className="proposal-form-input"
              rows={3}
              value={newNoteText}
              onChange={(e) => {
                setNewNoteText(e.target.value);
                setError(null);
              }}
            />
            <p className="proposal-form-hint">
              This is stored as a note on the record first, exactly as typed, and the
              proposal cites it. The note is kept whatever happens to the proposal
              &mdash; including if it is rejected &mdash; which is why the citation is
              required and never invented.
            </p>
          </>
        )}

        {/* --- 2. the target field, from the server's own list ----------------- */}
        <label className="proposal-form-label" htmlFor={`${fieldId}-path`}>
          {LABELS.newProposalField}
        </label>
        <select
          id={`${fieldId}-path`}
          className="proposal-form-input"
          value={fieldPath}
          onChange={(e) => {
            setFieldPath(e.target.value);
            setRunId('');
            setError(null);
            // The value box's CONTROL TYPE can change with the field (a typed
            // enum/number/datetime control where a spec exists, JSON text
            // otherwise) — clearing it stops a JSON-quoted string or a bare number
            // surviving into a control shaped for the other kind.
            setValueText('');
          }}
        >
          {/* No pre-selection. A person chooses; nothing is proposed for them. */}
          <option value="">Choose a field&hellip;</option>
          {groupPaths(targetFieldPaths).map(([group, paths]) => (
            <optgroup key={group} label={group}>
              {paths.map((path) => (
                <option key={path} value={path}>
                  {proposalFieldLabel(path)} &mdash; {path}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
        {fieldPath !== '' && (
          <p className="proposal-form-hint">
            <span className="new-proposal-target-label">{proposalFieldLabel(fieldPath)}</span>{' '}
            <span className="mono">{fieldPath}</span> &mdash;{' '}
            {isRecordScoped
              ? 'recorded on the record, so this proposal names no run.'
              : 'recorded on a run, so this proposal must name the run it is about.'}
          </p>
        )}
        <p className="proposal-form-hint">
          This is the server&rsquo;s own list of the paths this build can target with a
          proposal &mdash; a subset of the official schema, not every field it defines.
          Whether a field belongs to the record or to a run is the server&rsquo;s answer
          too; it is never worked out from how many runs this record happens to have.
        </p>

        {/* --- 3. the run, when and only when the target needs one ------------- */}
        {needsRun && (
          <>
            <label className="proposal-form-label" htmlFor={`${fieldId}-run`}>
              {LABELS.newProposalRun}
            </label>
            {runs.length === 0 ? (
              <p className="proposal-form-error" role="alert">
                This field is applied through a run&rsquo;s writer, and this record has
                no runs yet (or they could not be read). Create a run in the Runs
                workspace before proposing a value here &mdash; it is never inferred.
              </p>
            ) : (
              <select
                id={`${fieldId}-run`}
                className="proposal-form-input"
                value={runId}
                onChange={(e) => {
                  setRunId(e.target.value);
                  setError(null);
                }}
              >
                <option value="">Choose a run&hellip;</option>
                {runs.map((run) => (
                  <option key={run.id} value={run.id}>
                    {run.label}
                  </option>
                ))}
              </select>
            )}
          </>
        )}

        {/* --- 4. the value ---------------------------------------------------- */}
        {fieldPath !== '' && spec !== null && (
          <>
            <label className="proposal-form-label" htmlFor={`${fieldId}-value`}>
              {spec.label}
              {spec.unit ? ` (${spec.unit})` : ''}
            </label>
            {spec.kind === 'enum' ? (
              <select
                id={`${fieldId}-value`}
                className="proposal-form-input"
                value={valueText}
                onChange={(e) => {
                  setValueText(e.target.value);
                  setError(null);
                }}
              >
                <option value="">Choose a value&hellip;</option>
                {spec.options?.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            ) : (
              <input
                id={`${fieldId}-value`}
                className="proposal-form-input"
                type="text"
                inputMode={spec.kind === 'number' ? 'decimal' : undefined}
                value={valueText}
                onChange={(e) => {
                  setValueText(e.target.value);
                  setError(null);
                }}
              />
            )}
            {spec.hint && <p className="proposal-form-hint">{spec.hint}</p>}
          </>
        )}

        {fieldPath !== '' && spec === null && (
          <>
            <label className="proposal-form-label" htmlFor={`${fieldId}-value`}>
              {LABELS.newProposalValueJson}
            </label>
            <textarea
              id={`${fieldId}-value`}
              className="proposal-form-input mono"
              rows={2}
              value={valueText}
              onChange={(e) => {
                setValueText(e.target.value);
                setError(null);
              }}
            />
            <p className="proposal-form-hint">
              Entered as JSON so the type is never guessed: a text value is quoted, for
              example <span className="mono">&quot;CuO&quot;</span>. This build carries
              no declared shape for this path, and a guessed one would be a guess.
            </p>
          </>
        )}

        {/* --- 5. the explanation that will be stored -------------------------- */}
        <span className="proposal-form-label">{LABELS.newProposalRuleHeading}</span>
        <p className="proposal-form-meaning new-proposal-rule">{HUMAN_PROPOSED_RULE}</p>
        <p className="proposal-form-hint">
          Every proposal carries a sentence saying what produced it &mdash; an
          explanation, not a code or an identifier. You are entering this value by
          hand, so that is the sentence stored, shown here in full rather than left for
          you to find on the review card.
        </p>

        {/* --- 6. what this does, and what is genuinely blocked ---------------- */}
        <p className="proposal-form-hint">{NEW_PROPOSAL_EFFECT_CLAIM}</p>
        <details className="new-proposal-why">
          <summary>What happens after you store it?</summary>
          <p className="proposal-form-hint">{NEW_PROPOSAL_ACCEPTANCE_DISCLOSURE}</p>
        </details>

        {error !== null && (
          <p className="proposal-form-error" role="alert">
            {error}
          </p>
        )}

        <div className="proposal-form-actions">
          <button
            type="button"
            className="btn btn-primary"
            disabled={!submittable}
            onClick={() => void submit()}
          >
            {busy ? LABELS.newProposalSubmitBusy : LABELS.newProposalSubmit}
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => close(true)}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * The picker's options, grouped by the path's top-level block, each group's paths in
 * the order the server sent them. The grouping is presentation only — no path is
 * renamed, reordered across groups, or omitted.
 */
function groupPaths(paths: string[]): [string, string[]][] {
  const groups: [string, string[]][] = [];
  for (const path of paths) {
    const group = proposalFieldGroup(path);
    const existing = groups.find(([name]) => name === group);
    if (existing) existing[1].push(path);
    else groups.push([group, [path]]);
  }
  return groups;
}
