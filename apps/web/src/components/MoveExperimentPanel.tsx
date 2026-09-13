import './rename-experiment.css';
import './library.css';
import { useEffect, useId, useRef, useState } from 'react';
import { ChevronDown, ChevronRight } from './icons';
import { api } from '../lib/api';
import { LABELS } from '../lib/labels';
import { statusOf } from '../lib/mutationErrors';
import type { ApiExperimentDetail } from '../lib/types';

/**
 * FILE AN EXPERIMENT IN A FOLDER, MOVE IT, OR TAKE IT OUT OF EVERY FOLDER.
 *
 * IT IS `RenameExperimentPanel`'s SHAPE ON PURPOSE — same `.field-group` shell, same
 * collapsed-on-arrival section, same `staleAt` device for a 412, same silent-refresh
 * contract on `onSaved`. These two write the record's two organizational labels under
 * the same precondition, so a reader who has used one knows how the other behaves, and
 * a second focus/error/stale idiom for the same job would be a second thing to keep
 * right. Read that panel's notes for the reasoning behind each of those; they are not
 * restated here.
 *
 * IT IS A SEPARATE OPERATION FROM THE RENAME AT THE WIRE TOO, not a second field on
 * it. `PATCH /api/experiments/{id}`'s own contract says it writes the title and
 * nothing else, and a backend test quotes that sentence — so widening its body to
 * carry a folder would have falsified a committed claim in order to save a route.
 *
 * A FREE-TEXT BOX AND NOT A PICKER, and that follows from the model rather than from
 * effort. **A folder path comes into existence by being named**, so the field that
 * names it has to accept a path that does not exist yet; a picker over existing paths
 * could only ever file a record beside another one, which makes the first record in
 * any new folder unfileable. The existing paths are offered as a `<datalist>`
 * alongside, which suggests without restricting.
 *
 * FOUR THINGS THIS PANEL DELIBERATELY DOES NOT OFFER, because the build cannot do
 * them and `CLAUDE.md` §15 forbids implying it can: creating an EMPTY folder (there is
 * no folder entity to create — filing the first experiment is what makes a path
 * real); RENAMING a folder (that is one write per member with no transaction around
 * them, so half-renamed is reachable); DELETING one (moving the last member out is
 * what ends a path); and setting an OWNER or a permission (that needs a trusted
 * authentication boundary this deployment does not have). None of them is a disabled
 * control here — a disabled control says "not now", and the honest answer is "not at
 * all".
 *
 * CLEARING IS THE SAME ACT AS MOVING. An empty box unfiles, and there is no separate
 * "remove from folder" button: "put this nowhere" and "take this out of where it is"
 * are one thing, and two controls for it would be two preconditions to get right.
 */
export function MoveExperimentPanel({
  detail,
  onSaved,
  /**
   * Every folder path that already exists anywhere in the workspace, for the
   * `<datalist>`. SUGGESTIONS ONLY — the box accepts a path that is not in this list,
   * which is how a new folder is made. An empty array is fine and simply offers
   * nothing, which is the state of a workspace where nothing has been filed yet.
   */
  existingFolders = [],
}: {
  detail: ApiExperimentDetail;
  /**
   * Refresh the record. MUST be a SILENT refetch — one that leaves the loaded screen
   * mounted, for the reason `RenameExperimentPanel.onSaved` records: the record screen
   * unmounts its whole loaded body whenever its fetch leaves the `data` state, so a
   * loading reload would destroy this panel mid-announcement and drop focus to
   * `<body>`.
   */
  onSaved: () => void;
  existingFolders?: readonly string[];
}) {
  const [expanded, setExpanded] = useState(false);
  const [open, setOpen] = useState(false);
  const [folder, setFolder] = useState(detail.folder ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  /** The validator a 412 was returned FOR — see `RenameExperimentPanel.staleAt`. */
  const [staleAt, setStaleAt] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const openRef = useRef<HTMLButtonElement>(null);
  const formId = useId();
  const fieldId = `${formId}-folder`;
  const listId = `${formId}-list`;
  const hintId = `${formId}-hint`;
  const errorId = `${formId}-error`;
  const statusId = `${formId}-status`;
  const bodyId = `${formId}-body`;

  const isStale = staleAt !== null && staleAt === detail.version;

  const returning = useRef(false);
  useEffect(() => {
    if (open) {
      inputRef.current?.focus();
    } else if (returning.current) {
      returning.current = false;
      openRef.current?.focus();
    }
  }, [open]);

  useEffect(() => {
    if (staleAt !== null && staleAt !== detail.version) {
      setStaleAt(null);
      setError(null);
    }
  }, [detail.version, staleAt]);

  const openForm = () => {
    setFolder(detail.folder ?? '');
    setError(null);
    setSaved(false);
    setOpen(true);
  };

  const close = () => {
    returning.current = true;
    setOpen(false);
    setError(null);
  };

  const submit = async (event: { preventDefault: () => void }) => {
    event.preventDefault();
    if (busy) return; // a second Enter while the first request is in flight
    setBusy(true);
    setError(null);
    /*
     * SENT EVEN WHEN IT LOOKS UNCHANGED, and NOTHING IS VALIDATED HERE — both on the
     * rename panel's reasoning, and the second one more strongly.
     *
     * The rename checks length locally because it can state the limit precisely. This
     * panel deliberately does NOT re-implement `normalize_folder_path`: that function
     * trims, drops empty levels, and refuses five distinct conditions with five typed
     * reasons. A second copy of those rules in TypeScript would be a second thing to
     * keep in step with the server, and the failure mode when they drift is the worst
     * available — a client that refuses a path the server would have accepted, or
     * accepts one it will not. The server's refusal is typed, names which rule and
     * says nothing was changed, and is surfaced verbatim below.
     *
     * An empty box sends `''`, which the server reads as "unfile" exactly as `null`.
     */
    try {
      const trimmed = folder.trim();
      await api.moveExperimentToFolder(detail.id, trimmed === '' ? null : trimmed, detail.version);
      setBusy(false);
      setSaved(true);
      setStaleAt(null);
      close();
      onSaved();
    } catch (err) {
      setBusy(false);
      if (statusOf(err) === 412) {
        setStaleAt(detail.version);
        setError(LABELS.renameStale);
        onSaved();
        return;
      }
      // Whatever the API layer could establish, unreinterpreted. For a 422 that is
      // the server's own typed sentence, which names the rule and ends "Nothing was
      // changed." — a move that failed for an unknown reason must not be described as
      // one that failed for a known one.
      setError(
        err instanceof Error && err.message
          ? err.message
          : 'The folder could not be changed. Nothing was changed.',
      );
    }
  };

  const Chevron = expanded ? ChevronDown : ChevronRight;
  const current = detail.folder ?? '';

  return (
    <section className="field-group" aria-label="Folder (folder)">
      <h2 className="fg-heading">
        <button
          type="button"
          className="fg-header"
          aria-expanded={expanded}
          aria-controls={expanded ? bodyId : undefined}
          onClick={() => {
            // Collapsing retires the confirmation with the panel that carried it, for
            // the reason the rename panel records: a "Folder saved." still sitting
            // there on a later visit would report an act from a session the reader may
            // not remember making.
            setSaved(false);
            setExpanded((isOpen) => !isOpen);
          }}
        >
          <Chevron className="fg-chevron" size={16} strokeWidth={2} aria-hidden="true" />
          <span className="fg-block">{LABELS.libraryMoveLabel}</span>
          <span className="record-section-key">folder</span>
          <span className="record-section-summary">where this experiment is filed</span>
        </button>
      </h2>
      {expanded && (
        <div className="fg-body" id={bodyId}>
          {/* ALWAYS MOUNTED, empty when there is nothing to say — a live region
              inserted together with its content is announced unreliably, and this is
              the one place the reader is told the move actually landed. */}
          <p className="rename-status" id={statusId} role="status">
            {saved ? 'Folder saved.' : ''}
          </p>
          {open ? (
            <form className="library-move" onSubmit={submit} aria-labelledby={`${formId}-heading`}>
              <h3 className="library-move-label" id={`${formId}-heading`}>
                {LABELS.libraryMoveAction}
              </h3>
              <label className="library-move-label" htmlFor={fieldId}>
                {LABELS.libraryMoveLabel}
              </label>
              <input
                ref={inputRef}
                id={fieldId}
                className="library-move-input"
                type="text"
                value={folder}
                list={existingFolders.length > 0 ? listId : undefined}
                aria-invalid={error !== null || undefined}
                aria-describedby={error !== null ? `${errorId} ${hintId}` : hintId}
                onChange={(e) => {
                  setFolder(e.target.value);
                  // A stale-write refusal is NOT cleared by typing: the validator is
                  // still the rejected one. Every other error is the reader's to fix
                  // in the box, so it goes as soon as they start.
                  if (error !== null && !isStale) setError(null);
                }}
              />
              {existingFolders.length > 0 && (
                /* SUGGESTIONS, NOT A CONSTRAINT. A `<datalist>` leaves the box free
                   text, which it has to be — a new folder is made by naming one that
                   does not exist yet. */
                <datalist id={listId}>
                  {existingFolders.map((path) => (
                    <option key={path} value={path} />
                  ))}
                </datalist>
              )}
              <p className="library-move-hint" id={hintId}>
                {LABELS.libraryMoveHint}
              </p>
              {error !== null && (
                <p className="library-move-error" id={errorId} role="alert">
                  {error}
                </p>
              )}
              <div className="library-move-actions">
                <button type="submit" className="btn btn-primary" disabled={busy || isStale}>
                  {LABELS.libraryMoveSubmit}
                </button>
                <button type="button" className="btn btn-secondary" onClick={close} disabled={busy}>
                  {LABELS.libraryMoveCancel}
                </button>
              </div>
            </form>
          ) : (
            <>
              <p className="rename-current">
                {/* THE UNFILED STATE IS NAMED, NOT BLANK. An empty line here would
                    read as a value that failed to load; "Not in a folder" is the
                    state, and it is a real state rather than a missing one. */}
                <span className="rename-current-name">
                  {current === '' ? LABELS.libraryUnfiled : current}
                </span>
              </p>
              <p className="rename-hint">{LABELS.libraryFolderModelNote}</p>
              <div className="rename-actions">
                <button
                  ref={openRef}
                  type="button"
                  className="btn btn-secondary"
                  onClick={openForm}
                >
                  {LABELS.libraryMoveAction}
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}
