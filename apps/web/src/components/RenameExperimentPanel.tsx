import './rename-experiment.css';
import { useEffect, useId, useRef, useState } from 'react';
import { ChevronDown, ChevronRight } from './icons';
import { api } from '../lib/api';
import { LABELS } from '../lib/labels';
import { statusOf } from '../lib/mutationErrors';
import type { ApiExperimentDetail } from '../lib/types';

/**
 * THE TITLE LIMIT THE SERVER DECLARES, mirrored so the form can STATE it.
 *
 * It is `max_length` on `RenameExperimentRequest.title` (`apps/api/isaac_api/routes.py`),
 * which is deliberately the same number `CreateExperimentRequest` uses — a rename
 * stricter than create would leave a title this application accepted impossible to
 * correct, which is the whole failure this panel exists to remove. The server remains
 * the authority and still refuses an over-long value with a typed 422; this constant
 * exists so the reader is told where the limit is BEFORE they hit it.
 */
const TITLE_MAX_LENGTH = 200;

/**
 * RENAME AN EXPERIMENT — the affordance that did not exist.
 *
 * `title` was written exactly once, by `POST /api/experiments`, and no operation could
 * change it. With `0001_experiments` applied to the hosted database that made every
 * mistakenly created experiment permanent, with its typo.
 *
 * ONLY THE TITLE, AND THAT IS A CONTRACT RATHER THAN A FIRST INSTALMENT. The create
 * form beside it also takes a free-text note, and `PATCH /api/experiments/{id}` refuses
 * that key with a 422: the server stores it at `source.description`, which it also
 * reads as the provenance marker deciding whether a record belongs to the managed
 * example dataset. There is nowhere here to type one, so the panel cannot promise an
 * edit the server would refuse.
 *
 * A COLLAPSED SECTION, NOT A MODAL AND NOT AN ALWAYS-OPEN FORM. It uses the same
 * `.field-group` / `.fg-header` / `.fg-body` shell every other section on this screen
 * uses, collapsed on arrival like all of them, so a scientist who never needs to rename
 * anything pays one line for it. A modal would need a focus trap, a scrim, an escape
 * contract and a restore-focus contract — four things to get right for one text box, on
 * a screen with nothing behind it worth dimming.
 *
 * THE REFRESH IS SILENT, AND THAT IS THE DEFECT THIS AVOIDS RATHER THAN A PREFERENCE.
 * The record screen unmounts its whole loaded body whenever its fetch is not in the
 * `data` state, so calling the LOADING variant of the reload after a save would destroy
 * this panel — status line, focus target and all — and blank the screen the reader was
 * looking at. `onSaved` is wired to the silent refetch for that reason; see the prop's
 * own note.
 */
export function RenameExperimentPanel({
  detail,
  onSaved,
}: {
  detail: ApiExperimentDetail;
  /**
   * Refresh the record. MUST be a SILENT refetch — one that leaves the loaded screen
   * mounted. A reload that flips this screen back to its loading state unmounts this
   * panel mid-announcement and drops focus to `<body>`.
   */
  onSaved: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState(detail.title);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  /**
   * The validator a 412 was returned FOR.
   *
   * A stale-write refusal is the one failure a reader cannot fix by editing the text,
   * and clearing its message on the next keystroke — which is what every other error
   * here does — would hide the refusal while leaving the client holding exactly the
   * validator that was just rejected. The next Save would then re-send it and be
   * refused again, with the message flickering each time. So the token is remembered:
   * the message stands, and Save stays disabled, until a refreshed `detail` arrives
   * carrying a DIFFERENT version. That is a condition the panel can observe rather
   * than a delay it guesses at.
   */
  const [staleAt, setStaleAt] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const openRef = useRef<HTMLButtonElement>(null);
  const formId = useId();
  const titleId = `${formId}-title`;
  const countId = `${formId}-count`;
  const errorId = `${formId}-error`;
  const statusId = `${formId}-status`;
  const bodyId = `${formId}-body`;

  const over = title.length - TITLE_MAX_LENGTH;
  const isStale = staleAt !== null && staleAt === detail.version;

  /*
   * FOCUS MOVES WITH THE FORM, IN BOTH DIRECTIONS, AND IT HAS TO BE AN EFFECT.
   *
   * Opening: focus lands on the box the reader now has to type in. Closing: focus
   * returns to the control that opened it. Written as an effect keyed on `open`
   * rather than as a `.focus()` inside the handlers, because at the moment Cancel
   * runs the opener button does not exist — the form is what is mounted — so the ref
   * is null and focus would fall to `<body>`. It has to run after the re-render that
   * puts the button back. `returning` distinguishes "closed by Cancel or Save" from
   * "never opened", so a first render does not steal focus to a button nobody pressed.
   */
  const returning = useRef(false);
  useEffect(() => {
    if (open) {
      inputRef.current?.focus();
    } else if (returning.current) {
      returning.current = false;
      openRef.current?.focus();
    }
  }, [open]);

  /*
   * THE STALE MESSAGE CLEARS WHEN — AND ONLY WHEN — THE THING IT DESCRIBES STOPS
   * BEING TRUE. It says the validator this client holds was rejected, so it survives
   * a keystroke and survives time; what retires it is a refreshed record carrying a
   * different version, which is exactly the condition under which a retry can now
   * succeed. Written as an effect on `detail.version` rather than cleared optimistically
   * inside the catch, because the refresh is asynchronous and may itself fail.
   */
  useEffect(() => {
    if (staleAt !== null && staleAt !== detail.version) {
      setStaleAt(null);
      setError((current) => (current === LABELS.renameStale ? null : current));
    }
  }, [detail.version, staleAt]);

  const openForm = () => {
    setTitle(detail.title);
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
    /*
     * TOO LONG IS REFUSED HERE, LOUDLY, RATHER THAN TRUNCATED SILENTLY BY THE BROWSER.
     * `maxLength` on the control would cut a pasted title at the limit without saying
     * so, and the reader's next act would be to save a name that is missing its end.
     * Nothing typed is altered or dropped at any point — the text stays in the box,
     * over the limit, until they shorten it. This is not INSTEAD of the server's
     * check: the same request is still refused with a 422 if it ever arrives.
     */
    if (over > 0) {
      setError(
        `The title is ${over} character${over === 1 ? '' : 's'} over the ` +
          `${TITLE_MAX_LENGTH}-character limit, so nothing was sent. Shorten it and try ` +
          'again — what you typed is still here, and none of it has been cut.',
      );
      inputRef.current?.focus();
      return;
    }
    const trimmed = title.trim();
    if (!trimmed) {
      // Checked here as well as at the server, because the server's answer would
      // arrive as a round trip for a condition the form can already see. The server
      // refuses a whitespace-only title with a typed 422 of its own.
      setError(LABELS.renameTitleRequired);
      inputRef.current?.focus();
      return;
    }
    /*
     * SENT EVEN WHEN IT LOOKS UNCHANGED, deliberately. A local "nothing changed, close
     * silently" branch has to compare the typed value against the stored one, and the
     * obvious comparison — trimmed input against untrimmed stored title — reports
     * "unchanged" for a value that is not, then closes the form having written nothing
     * while the reader believes they saved. The server already treats a re-sent title
     * as a true no-op: it rewrites nothing, does not advance the revision, and returns
     * the same ETag. Letting it decide costs one request and removes the whole class
     * of bug.
     */
    setBusy(true);
    setError(null);
    try {
      await api.renameExperiment(detail.id, trimmed, detail.version);
      setBusy(false);
      setSaved(true);
      setStaleAt(null);
      close();
      onSaved();
    } catch (err) {
      setBusy(false);
      if (statusOf(err) === 412) {
        // THE ONE NAMED CAUSE, and it is read from the status rather than inferred:
        // the server answers 412 only when the validator this client held is no longer
        // current. The form stays open with the reader's text in it, and the record is
        // refreshed so a retry has something newer to hold.
        setStaleAt(detail.version);
        setError(LABELS.renameStale);
        onSaved();
        return;
      }
      // Anything else is reported as whatever the API layer could establish. It is
      // NOT reinterpreted into a friendlier cause: a rename that failed for an unknown
      // reason must not be described as one that failed for a known one.
      setError(err instanceof Error && err.message ? err.message : LABELS.renameFailed);
    }
  };

  const Chevron = expanded ? ChevronDown : ChevronRight;

  return (
    <section className="field-group" aria-label="Experiment Name (name)">
      {/* A REAL HEADING LANDMARK — see `FieldGroup`'s own note for the measurement.
          `h2` at the level of this workspace's other sections, so the outline under
          the screen's single `h1` stays contiguous. A transparent wrapper: `.fg-heading`
          resets margin and type, so nothing about this header's appearance changes. */}
      <h2 className="fg-heading">
        <button
          type="button"
          className="fg-header"
          aria-expanded={expanded}
          aria-controls={expanded ? bodyId : undefined}
          onClick={() => {
            // Collapsing retires the confirmation with the panel that carried it: a
            // "Name saved." still sitting there on a later visit would report an act
            // from a session the reader may not remember making.
            setSaved(false);
            setExpanded((isOpen) => !isOpen);
          }}
        >
          <Chevron className="fg-chevron" size={16} strokeWidth={2} aria-hidden="true" />
          <span className="fg-block">Experiment Name</span>
          {/* The same two quiet spans `RecordInfoPanel` uses, and for its reason:
              `.fg-sublabel` / `.fg-summary` paint a colour already below the contrast
              threshold on this screen. */}
          <span className="record-section-key">name</span>
          <span className="record-section-summary">what this experiment is called</span>
        </button>
      </h2>
      {expanded && (
        <div className="fg-body" id={bodyId}>
          {/* ALWAYS MOUNTED, empty when there is nothing to say. A live region
              inserted together with its content is announced unreliably, and this is
              the one place the reader is told the rename actually landed. */}
          <p className="rename-status" id={statusId} role="status">
            {saved ? LABELS.renameSaved : ''}
          </p>
          {open ? (
            <form className="rename-form" onSubmit={submit} aria-labelledby={`${formId}-heading`}>
              <h3 className="rename-label" id={`${formId}-heading`}>
                {LABELS.renameFormTitle}
              </h3>
              <div className="rename-field">
                <label className="rename-label" htmlFor={titleId}>
                  {LABELS.renameTitleLabel}
                </label>
                <input
                  ref={inputRef}
                  id={titleId}
                  className="rename-input"
                  type="text"
                  value={title}
                  required
                  aria-invalid={error !== null || undefined}
                  /* The count is always described, so a screen-reader user hears the
                     limit and their position in it on focus rather than having to
                     find it. */
                  aria-describedby={error !== null ? `${errorId} ${countId}` : countId}
                  onChange={(e) => {
                    setTitle(e.target.value);
                    // A stale-write refusal is NOT cleared by typing: the validator is
                    // still the rejected one, so clearing the message would hide a
                    // refusal that is still true. Every other error is the reader's to
                    // fix in the box, so it goes as soon as they start.
                    if (error !== null && !isStale) setError(null);
                  }}
                />
                {/* NOT a live region: announcing a new number on every keystroke is
                    noise. The two facts a screen-reader user needs — that there is a
                    limit and where they are in it — arrive through `aria-describedby`
                    on focus and through the `role="alert"` refusal on submit. Over the
                    limit it says so IN WORDS, so the state survives a reader who cannot
                    distinguish the two colours. */}
                <span
                  className="rename-hint rename-count"
                  id={countId}
                  data-over={over > 0 ? 'true' : undefined}
                >
                  {over > 0
                    ? `${title.length} characters — ${over} over the ${TITLE_MAX_LENGTH}-character limit. Nothing has been cut; shorten it to save the name.`
                    : `${title.length} of ${TITLE_MAX_LENGTH} characters`}
                </span>
              </div>
              {error !== null && (
                <p className="rename-error" id={errorId} role="alert">
                  {error}
                </p>
              )}
              <div className="rename-actions">
                <button type="submit" className="btn btn-primary" disabled={busy || isStale}>
                  {LABELS.renameSubmit}
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={close}
                  disabled={busy}
                >
                  {LABELS.renameCancel}
                </button>
              </div>
            </form>
          ) : (
            <>
              <p className="rename-current">
                <span className="rename-current-name">{detail.title}</span>
              </p>
              <p className="rename-hint">{LABELS.renameHint}</p>
              <div className="rename-actions">
                <button
                  ref={openRef}
                  type="button"
                  className="btn btn-secondary"
                  onClick={openForm}
                >
                  {LABELS.actionRenameExperiment}
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}
