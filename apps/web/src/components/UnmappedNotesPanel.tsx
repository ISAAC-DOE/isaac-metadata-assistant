/*
 * UNMAPPED NOTES — the review surface for content that has no confident schema home.
 *
 * WHAT THIS PANEL IS FOR. A scientist writes things down that no rule can place: why
 * a scan was repeated, a column heading nothing recognised, an aside in a transcript.
 * Every pipeline in this application used to drop them silently. This is where they
 * land, and where a person decides what each one is.
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
 */
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';

import { api, ApiError } from '../lib/api';
import { mutationFailureCopy } from '../lib/mutationErrors';
import type { ApiNote, ApiNoteState, ApiNotesResponse } from '../lib/types';
import { BackendDown, LoadingPanel } from './FetchStates';
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

type ListState =
  | { status: 'loading' }
  | { status: 'error'; error: ApiError }
  | { status: 'data'; loaded: ApiNotesResponse };

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
        setMutationError(
          mutationFailureCopy(
            asApiError(err),
            'That review could not be recorded. The note is unchanged.',
          ),
        );
        setAnnouncement('');
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
        setMutationError(
          mutationFailureCopy(
            asApiError(err),
            'That note could not be captured. Nothing was written.',
          ),
        );
        setAnnouncement('');
        throw err;
      }
    },
    [experimentId, version, reload],
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
    const unreadable =
      loaded.unreadable_entries > 0
        ? ` · ${loaded.unreadable_entries} stored ${
            loaded.unreadable_entries === 1 ? 'entry' : 'entries'
          } this version cannot read, kept unchanged on the record`
        : '';
    return `${filtered}${unreadable}`;
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
            onChange={(e) => setFilter(e.target.value as 'all' | ApiNoteState)}
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
          <button type="button" className="btn btn-secondary" onClick={() => reload(false)}>
            Reload This Section
          </button>
        </div>
      )}

      <CaptureNote onCapture={capture} disabled={version === null} />

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
                  busy={busyNoteId === note.id || version === null}
                  onReview={review}
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
 */
function EmptyNotes({
  total,
  filtering,
  onClear,
}: {
  total: number;
  filtering: boolean;
  onClear: () => void;
}) {
  if (filtering) {
    return (
      <div className="notes-empty">
        <p>
          No notes are in this state. This record holds {total}{' '}
          {total === 1 ? 'note' : 'notes'} in total.
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
        No unmapped notes on this record. Notes appear here when something is
        captured that cannot be placed in a schema field — nothing is created
        automatically, and nothing is inferred from the record's contents.
      </p>
    </div>
  );
}

function CaptureNote({
  onCapture,
  disabled,
}: {
  onCapture: (text: string, source: string) => Promise<void>;
  disabled: boolean;
}) {
  const [text, setText] = useState('');
  const [saving, setSaving] = useState(false);
  const textId = useId();
  const hintId = useId();

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
    </div>
  );
}

function NoteCard({
  note,
  mappablePaths,
  busy,
  onReview,
}: {
  note: ApiNote;
  mappablePaths: string[];
  busy: boolean;
  onReview: (
    note: ApiNote,
    action: 'map' | 'edit' | 'keep' | 'dismiss',
    opts: { fieldPath?: string; text?: string; reason?: string },
    announce: string,
  ) => Promise<void>;
}) {
  const [open, setOpen] = useState<'map' | 'edit' | 'dismiss' | null>(null);
  /** No default selection. See rule 1 in the module header — nothing is proposed. */
  const [fieldPath, setFieldPath] = useState('');
  const [editText, setEditText] = useState(note.display_text);
  const [reason, setReason] = useState('');

  const pathId = useId();
  const editId = useId();
  const reasonId = useId();
  const bodyId = useId();

  const close = () => {
    setOpen(null);
    setFieldPath('');
    setEditText(note.display_text);
    setReason('');
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
          type="button"
          className="btn btn-secondary"
          disabled={busy}
          aria-expanded={open === 'edit'}
          aria-controls={open === 'edit' ? editId : undefined}
          onClick={() => {
            setEditText(note.display_text);
            setOpen(open === 'edit' ? null : 'edit');
          }}
        >
          Edit wording
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={busy}
          onClick={() =>
            onReview(
              note,
              'keep',
              {},
              'Kept as a note. It belongs to no field, and it stays on the record.',
            )
          }
        >
          Keep as note
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={busy}
          aria-expanded={open === 'dismiss'}
          aria-controls={open === 'dismiss' ? reasonId : undefined}
          onClick={() => setOpen(open === 'dismiss' ? null : 'dismiss')}
        >
          Dismiss
        </button>
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
          <p className="note-form-hint">
            This records where the content belongs. It does not write a value — a
            value still has to be entered and confirmed on the field itself.
          </p>
          <div className="note-form-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || fieldPath === ''}
              onClick={async () => {
                await onReview(
                  note,
                  'map',
                  { fieldPath },
                  `Mapped to ${fieldPath}. No value was written.`,
                );
                close();
              }}
            >
              Map This Note
            </button>
            <button type="button" className="btn btn-secondary" onClick={close}>
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
          <div className="note-form-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || editText.trim() === ''}
              onClick={async () => {
                await onReview(
                  note,
                  'edit',
                  { text: editText },
                  'Wording updated. The original capture is unchanged.',
                );
                close();
              }}
            >
              Save Wording
            </button>
            <button type="button" className="btn btn-secondary" onClick={close}>
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
            you do not have one — nothing is filled in on your behalf.
          </p>
          <div className="note-form-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy}
              onClick={async () => {
                await onReview(
                  note,
                  'dismiss',
                  { reason },
                  'Dismissed. The note is set aside and stays on the record.',
                );
                close();
              }}
            >
              Dismiss This Note
            </button>
            <button type="button" className="btn btn-secondary" onClick={close}>
              Cancel
            </button>
          </div>
        </div>
      )}
    </article>
  );
}
