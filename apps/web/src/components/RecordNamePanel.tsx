/*
 * NAME AND NOTE — the one surface on which a scientist can correct what they called
 * a record.
 *
 * WHY IT EXISTS. `POST /api/experiments` wrote `title` once and `source.description`
 * once, and nothing anywhere could change either. Where this deployment stores
 * experiments in its own database — which the hosted one does — a misspelling in a
 * title was therefore a permanent property of a stored record, and the note beside it
 * was worse than permanent: no read operation published it at all, so a reader could
 * never see what they had written, let alone fix it.
 *
 * IT IS NOT BEHIND A DISCLOSURE, and that is the one place this panel deliberately
 * departs from its neighbours. Every other section in this column
 * (`RecordInfoPanel`, `RecordLinksPanel`, every draft block) is collapsed on arrival,
 * because they are reference material and progressive disclosure is right for
 * reference. This one carries an ACTION, and an action a reader has to discover behind
 * a chevron is not a reachable affordance — the whole finding this closes was that no
 * affordance existed. So the current name and note are always visible and the edit
 * control is always in the tab order; only the FORM is disclosed, by the button that
 * opens it.
 *
 * AN INLINE EXPANSION, NOT A MODAL — the same reasoning `CreateExperimentControl`
 * gives, and the same two fields, so it reuses that form's classes wholesale
 * (`queue.css`). A modal would need a focus trap, a scrim, an escape contract and a
 * restore-focus contract, for a form with two text boxes, on a screen with nothing
 * behind it worth dimming. Two forms for the same pair of fields must not look like
 * two different kinds of thing.
 *
 * WHAT IT CANNOT DO, STATED BECAUSE THE ABSENCE IS EASY TO READ AS UNFINISHED: it
 * cannot discard the record. No committed sentence authorises removing an experiment
 * row, and the panel offers nothing that implies one is coming. See the comment above
 * `rename_experiment` in `routes.py`.
 *
 * `null` AND `undefined` ARE DIFFERENT ANSWERS about the note, and this file keeps
 * them apart. `undefined` means the server never told us (a deployment older than the
 * rename operation), and the honest response is to withhold the editing control
 * rather than to offer overwriting a value we were never shown — offering it would
 * turn "we do not know" into a blank box whose Save would destroy real text.
 */

import './fields.css';
import './queue.css';
import './record-name.css';
import { useEffect, useId, useRef, useState } from 'react';
import { Pencil } from './icons';
import {
  CharacterCount,
  DESCRIPTION_MAX_LENGTH,
  TITLE_MAX_LENGTH,
} from './CharacterCount';
import { api } from '../lib/api';
import { LABELS } from '../lib/labels';
import { mutationFailureCopy, statusOf } from '../lib/mutationErrors';
import type { ApiExperimentDetail } from '../lib/types';

/**
 * The notice for a failed save.
 *
 * `412` IS NAMED SEPARATELY, and it is the only status that earns its own sentence.
 * It means somebody else changed this record while the form was open, which is a
 * cause the reader can act on and a cause no generic message conveys — "could not be
 * saved" would leave them retrying against a validator that will refuse again. Every
 * other failure falls through to `mutationFailureCopy`, which names a session that
 * ended when the error says so and otherwise repeats the fallback UNCHANGED: a save
 * that failed for an unknown reason must not be reported as one that failed for a
 * known one.
 *
 * `428` is deliberately NOT given a sentence. It means this client sent no validator,
 * which is a bug here rather than something the reader did, and inventing a
 * reader-facing cause for it would be a guess.
 */
function saveFailureCopy(err: unknown): string {
  if (statusOf(err) === 412) {
    return (
      'This record changed while you were editing, so nothing was saved. Reload to ' +
      'see the current name and note, then try again.'
    );
  }
  return mutationFailureCopy(err, 'The name and note could not be saved.');
}

export function RecordNamePanel({
  detail,
  onSaved,
}: {
  detail: ApiExperimentDetail;
  /** Called after a successful save so the screen can refetch. The panel does not
   *  mutate the detail it was handed: one owner of that state, and it is the screen. */
  onSaved: () => void;
}) {
  const formId = useId();
  const headingId = `${formId}-heading`;
  const titleId = `${formId}-title`;
  const noteId = `${formId}-note`;
  const titleCountId = `${formId}-title-count`;
  const noteCountId = `${formId}-note-count`;
  const noteHintId = `${formId}-note-hint`;
  const errorId = `${formId}-error`;
  const statusId = `${formId}-status`;

  // `undefined` = the server did not report a note. See the file header.
  const reported = detail.description;
  const noteKnown = reported !== undefined;

  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState(detail.title);
  const [note, setNote] = useState(reported ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const titleRef = useRef<HTMLInputElement>(null);
  const noteRef = useRef<HTMLTextAreaElement>(null);
  const openRef = useRef<HTMLButtonElement>(null);
  const returning = useRef(false);

  const titleOver = title.length - TITLE_MAX_LENGTH;
  const noteOver = note.length - DESCRIPTION_MAX_LENGTH;

  /*
   * FOCUS MOVES WITH THE FORM, IN BOTH DIRECTIONS, and it has to be an effect for
   * the reason `CreateExperimentControl` records: on close, the opener button does not
   * exist at the moment the handler runs, so a `.focus()` call there silently does
   * nothing and focus falls to `<body>`. `returning` distinguishes "closed by Cancel
   * or Save" from "never opened", so a first render does not steal focus.
   */
  useEffect(() => {
    if (open) {
      titleRef.current?.focus();
    } else if (returning.current) {
      returning.current = false;
      openRef.current?.focus();
    }
  }, [open]);

  const openForm = () => {
    // RE-SEED FROM THE RECORD EVERY TIME, never from the last edit. A reader who
    // cancelled, or whose save lost a race, must not reopen onto their abandoned
    // draft as though it were the stored value.
    setTitle(detail.title);
    setNote(reported ?? '');
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
    /*
     * OVER-LONG IS REFUSED HERE, LOUDLY, RATHER THAN TRUNCATED SILENTLY. The same
     * D5 reasoning as the create form: neither control carries `maxLength`, because
     * `maxLength` cuts a pasted paragraph without saying so and the reader's next act
     * is to save text that is missing its end. Nothing typed is altered or dropped at
     * any point — it stays in the box, over the limit, until they shorten it.
     */
    if (titleOver > 0 || noteOver > 0) {
      const which = titleOver > 0 ? 'title' : 'note';
      const limit = titleOver > 0 ? TITLE_MAX_LENGTH : DESCRIPTION_MAX_LENGTH;
      const over = titleOver > 0 ? titleOver : noteOver;
      setError(
        `The ${which} is ${over} character${over === 1 ? '' : 's'} over the ` +
          `${limit}-character limit, so nothing was sent. Shorten it and try again — ` +
          'what you typed is still here, and none of it has been cut.',
      );
      (titleOver > 0 ? titleRef.current : noteRef.current)?.focus();
      return;
    }
    const trimmed = title.trim();
    if (!trimmed) {
      // Checked here as well as at the server, because the server's answer would be a
      // round trip for a condition the form can already see. It is not INSTEAD of the
      // server's check: `PATCH /api/experiments/{id}` refuses a whitespace-only title
      // with a typed `422 invalid_title` of its own.
      setError(LABELS.renameRecordTitleRequired);
      titleRef.current?.focus();
      return;
    }

    /*
     * ONLY WHAT CHANGED IS SENT, and that is a correctness requirement rather than an
     * optimisation. The operation reads an ABSENT key as "leave that field alone" and
     * an explicit value as "set it", so sending both keys unconditionally would make
     * every rename also rewrite the note — harmless when we know the note, and a
     * silent destruction of text when we do not. Which is why the note is only ever
     * sent when the server told us what it currently is.
     */
    const body: { title?: string; description?: string | null } = {};
    if (trimmed !== detail.title) body.title = trimmed;
    if (noteKnown && note.trim() !== (reported ?? '')) {
      // An emptied box CLEARS the note. `''` and `null` mean the same thing to the
      // server; `''` is sent because it is what the box holds.
      body.description = note.trim();
    }
    if (body.title === undefined && body.description === undefined) {
      // Nothing changed. Closing is the honest outcome — the operation would answer
      // `422` for a body naming neither field, and reporting that as a failure would
      // be telling the reader something went wrong when nothing did.
      close();
      return;
    }

    setBusy(true);
    setError(null);
    try {
      await api.renameExperiment(detail.id, body, detail.version);
      setBusy(false);
      returning.current = true;
      setOpen(false);
      setSaved(true);
      onSaved();
    } catch (err) {
      setBusy(false);
      setError(saveFailureCopy(err));
    }
  };

  const readState = (
    <>
      <dl className="record-name-rows">
        <dt>{LABELS.renameRecordNameLabel}</dt>
        <dd className="record-name-value">{detail.title}</dd>
        <dt>{LABELS.renameRecordNoteLabel}</dt>
        <dd className={reported ? 'record-name-value' : 'record-name-absent'}>
          {reported
            ? reported
            : noteKnown
              ? LABELS.renameRecordNoteEmpty
              : LABELS.renameRecordNoteUnknown}
        </dd>
      </dl>
      <p className="record-name-hint">{LABELS.renameRecordHint}</p>
      <div className="record-name-actions">
        <button ref={openRef} type="button" className="btn btn-secondary" onClick={openForm}>
          <Pencil size={14} strokeWidth={2} aria-hidden="true" />
          {LABELS.actionRenameRecord}
        </button>
      </div>
      {/* `role="status"` and not `role="alert"`: a save that worked is not an alert,
          and it must still be announced, because the form it replaced has gone and a
          keyboard user would otherwise have no signal that anything happened. */}
      {saved && (
        <p className="record-name-saved" id={statusId} role="status">
          {LABELS.renameRecordSaved}
        </p>
      )}
    </>
  );

  const form = (
    <form className="create-experiment" onSubmit={submit} aria-labelledby={headingId}>
      <div className="create-experiment-field">
        <label className="create-experiment-label" htmlFor={titleId}>
          {LABELS.renameRecordNameLabel}
        </label>
        <input
          ref={titleRef}
          id={titleId}
          className="create-experiment-input"
          type="text"
          value={title}
          required
          aria-invalid={error !== null || undefined}
          aria-describedby={error !== null ? `${errorId} ${titleCountId}` : titleCountId}
          onChange={(e) => {
            setTitle(e.target.value);
            if (error !== null) setError(null);
          }}
        />
        <CharacterCount id={titleCountId} length={title.length} limit={TITLE_MAX_LENGTH} />
      </div>

      {/* The note box is rendered ONLY when the server told us what the note is. See
          the file header: a blank box over an unknown value is a Save that destroys. */}
      {noteKnown && (
        <div className="create-experiment-field">
          <label className="create-experiment-label" htmlFor={noteId}>
            {LABELS.renameRecordNoteLabel}
          </label>
          <textarea
            ref={noteRef}
            id={noteId}
            className="create-experiment-input create-experiment-textarea"
            value={note}
            rows={2}
            aria-describedby={`${noteHintId} ${noteCountId}`}
            onChange={(e) => {
              setNote(e.target.value);
              if (error !== null) setError(null);
            }}
          />
          <span className="create-experiment-hint" id={noteHintId}>
            {LABELS.createExperimentDescriptionHint}
          </span>
          <CharacterCount
            id={noteCountId}
            length={note.length}
            limit={DESCRIPTION_MAX_LENGTH}
          />
        </div>
      )}

      {/* `role="alert"`: the message appears after a submit the reader already made,
          so it has to be announced rather than waited to be found. */}
      {error !== null && (
        <p className="create-experiment-error" id={errorId} role="alert">
          {error}
        </p>
      )}

      <div className="create-experiment-actions">
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {LABELS.renameRecordSubmit}
        </button>
        <button type="button" className="btn btn-secondary" onClick={close} disabled={busy}>
          {LABELS.renameRecordCancel}
        </button>
      </div>
    </form>
  );

  return (
    <section className="field-group" aria-labelledby={headingId}>
      {/* A `div`, not a `button`: this header discloses nothing, so making it
          activatable would put a control in the tab order that does nothing. It reuses
          `.fg-header`'s geometry so it lines up with the collapsible sections below
          it, and `record-name.css` removes that class's hover feedback, which would
          otherwise promise interactivity this header does not have. */}
      <div className="fg-header record-name-header">
        <span className="fg-block" id={headingId}>
          {LABELS.renameRecordSection}
        </span>
      </div>
      <div className="fg-body record-name-body">{open ? form : readState}</div>
    </section>
  );
}
