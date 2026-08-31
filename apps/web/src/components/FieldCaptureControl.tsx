import { useEffect, useId, useRef, useState } from 'react';
import { api } from '../lib/api';
import { mutationFailureCopy, statusOf } from '../lib/mutationErrors';
import type { DraftField, DraftFieldCapture } from '../lib/types';

/**
 * WHAT ONE FIELD ROW MAY SAY ABOUT ENTERING A VALUE — and the ONE case where it may
 * offer a control.
 *
 * ── The measurement this whole file is built on ─────────────────────────────
 *
 * `GET /draft` now returns a row for all 26 field paths this build can extract into or
 * write at, whether or not the record holds one. Measured over HTTP, on a record created
 * through `POST /api/experiments` with one run, at every write route the application
 * has:
 *
 *   | where a value can be entered                         | paths |
 *   |------------------------------------------------------|-------|
 *   | `POST .../answers` + `.../edit` — THE RECORD's        |   2   | system.domain, system.technique
 *   | `PATCH .../runs/{id}` — a run's own field             |   5   | context.*, timestamps.acquired_*
 *   | `POST .../runs/{id}/overrides` — one run's divergence |  13   | sample.*, system.facility.*, system.technique
 *   | nothing at all — 422 from all six routes              |   7   | system.configuration.* ×6, timestamps.created_utc
 *
 * ── Rule 1: a control is rendered ONLY where a RECORD-level route accepts a value ──
 *
 * This row lives on the RECORD screen, so a control here writes the RECORD's value.
 * Two of the four buckets above are a run's, and one of those two — the override —
 * is not even a way to state what the record is: `routes._record_enum_fields`'s own
 * docstring makes the point, that an override *"records a DIVERGENCE from an inherited
 * value the record does not hold"*. Rendering a box here that wrote a run override would
 * be a control claiming to do something other than what it does, which is worse than no
 * control. So the other three buckets get a SENTENCE saying where the value is entered,
 * and no input.
 *
 * That is the same rule `RunCard` already enforces from the other side (*"a control at
 * one of those paths would have exactly one possible outcome, a typed 422, so it must
 * never be offered"*) and the same rule `RunInheritedPanel` enforces with `overridable`.
 * `CLAUDE.md` §11 records what happens when it is broken: *"a panel told the scientist to
 * enter a value on 25 fields, and 7 accept none"*.
 *
 * ── Rule 2: the control is a CHOICE from the schema's own set, never a free box ──
 *
 * CORRECTED 2026-08-30: **the record-writable set is 14 paths, not 2, and only 2 of
 * them are closed enums.** This read "Both record-writable paths are closed enums
 * the official schema declares", which was true when the record routes accepted only
 * `system.domain` and `system.technique`. The campaign-sheet slice widened them to
 * fourteen; the twelve sample and facility paths are free text or numbers and carry
 * no `choices`, so `canEnterOnRecord` is false for them and this component renders
 * no control. That is a real gap — a text input for those twelve is its own slice —
 * and `captureHint` must say so without blaming a load failure. The two enum paths
 * are still enums, and the
 * values arrive on the wire in `capture.choices` — read from the vendored document at
 * request time, never transcribed here. That is what makes the act a user confirmation
 * over a bounded set rather than a guess (`CLAUDE.md` §5), and it means a schema refresh
 * moves this control without anybody editing it. A record-writable path arriving with NO
 * choices renders read-only: fail-closed, because this file has no way to know what such
 * a value may be.
 *
 * ── Rule 3: which operation to call is read from what the record HOLDS ──
 *
 * Measured: `POST .../answers` answers `422 already_answered` for a path that already
 * holds a value (and names `.../edit` in `answer_at`), and `POST .../edit` answers
 * `422 not_yet_answered` for one that does not (naming `.../answers`). So `present`
 * routes it. A refusal is NEVER silently retried against the other route — the server's
 * own message names the fix, and a client that guesses twice is a client that can write
 * something the reader did not ask for.
 */

/** True when a RECORD-level operation will accept a value here AND we know the set. */
export function canEnterOnRecord(capture: DraftFieldCapture | undefined): boolean {
  return Boolean(capture?.record_writable && capture.choices && capture.choices.length > 0);
}

/**
 * The one sentence a row may show about entering a value, or `null` when the row
 * renders a control instead.
 *
 * COMPOSED FROM SERVED FACTS, per path, never "true on average". Each branch is a
 * different claim and the order is deliberate: the record-level answer comes first
 * because it is the only one that needs no run, then the two run answers, then the
 * refusals. Reading them in any other order could tell a reader to go to a run for a
 * value they can enter where they are.
 *
 * EVERY SENTENCE IS ABOUT WHERE A VALUE MAY BE **ENTERED**, AND NEVER ABOUT WHETHER
 * THE RECORD HOLDS ONE. That distinction was got wrong and is corrected here, because
 * the row this sentence sits under RENDERS THE VALUE two lines above it. Measured over
 * HTTP on a fixture-seeded record — which is every worked example a reader opens —
 * `timestamps.created_utc` is `2099-03-05T20:15:00Z` and `system.configuration.n_scans`
 * is `6`, both `present: true`, and both are refused by all six write routes. The
 * earlier copy opened *"This version records no value here"*, so the screen displayed a
 * value and denied it in the same row. `capture` says nothing about presence and cannot
 * be asked to; the fix is to say the true thing it does describe — that no operation in
 * this build ACCEPTS one — which reads correctly whether the row is filled or empty.
 */
export function captureHint(
  capture: DraftFieldCapture | undefined,
  /**
   * Whether the caller is actually rendering the control. `false` on a screen that
   * cannot write — one that holds no record version token — where the sentence must
   * still say WHERE the value is entered rather than falling silent, which would leave
   * the reader with no account of a field at all.
   */
  offeringControl = false,
  /**
   * The field's official path, when the caller has it.
   *
   * It gates ONE sentence: the exporter's, which is a claim about
   * `timestamps.created_utc` alone and about no other path. Without it the last branch
   * would tell any unwritable path outside an open namespace that an exporter stamps
   * it — and that branch is reachable by more than one path today. A schema this
   * process cannot read makes `_schema_open_namespaces()` fail closed to `()`, at which
   * point all six `system.configuration.*` rows arrive with `open_namespace: null` and
   * would have been told the export-stamp story. Omitted, the branch says only what is
   * true of every path that reaches it.
   */
  path?: string,
): string | null {
  if (capture === undefined) {
    // The server did not say. Claim nothing — an absent fact is not a refusal, and a
    // sentence here would be this client inventing one.
    return null;
  }
  if (offeringControl) return null;
  if (capture.record_writable) {
    if (canEnterOnRecord(capture)) {
      // A route accepts it and the set is known — this reader simply is not on a screen
      // that can write. Points at the one that can, and promises nothing here.
      return 'A value for this field is entered and confirmed on this record, on the Record Fields view.';
    }
    // ── CORRECTED 2026-08-30: THIS BLAMED A CAUSE THAT CANNOT HAPPEN ─────────────
    // It read: *"The choice cannot be offered right now, because the set of values the
    // official schema allows here did not load."* That asserts a TRANSIENT load
    // failure, and "right now" invites a retry that can never succeed.
    //
    // It is unreachable for the reason it gave, and the server's fail-closed design is
    // what makes it unreachable: `_record_writable_fields()` returns an EMPTY mapping
    // when the vendored schema cannot be read, so an unreadable schema makes
    // `record_writable` FALSE at every path and this branch is never entered.
    // Measured: with `Path.read_text` raising, `capture_facts` reports
    // `record_writable` on 0 of 26 paths; normally it reports 14, of which 12 carry no
    // `choices`. So `record_writable && !choices` means one thing only — the schema WAS
    // read and declares no fixed list of values at this path.
    //
    // That became the ordinary case rather than the exotic one when the campaign-sheet
    // slice widened the record routes from the 2 schema-enum paths to 14: the twelve
    // sample and facility paths are free-text or numeric, and always will be.
    //
    // NOT YET OFFERED HERE, and said plainly rather than implied: this component
    // renders a `<select>`, so it has no control for a free-text path. A text input for
    // those twelve is a real addition and belongs in its own reviewed slice; until then
    // this sentence must not suggest the value is unavailable or that waiting helps.
    return 'A value for this field is entered and confirmed on this record. The official schema declares no fixed list of values here, so it is typed rather than chosen — and this screen does not offer that input yet.';
  }
  if (capture.run_field_writable) {
    return 'A value for this field is entered on a run rather than on the record — in the Runs section on this screen.';
  }
  if (capture.run_overridable) {
    return 'No operation in this version accepts a value for this field on the record itself. A run of this record can record its own value for it, entered on that run — and that value belongs to that run, not to the record.';
  }
  if (capture.open_namespace) {
    return `There is nothing to type here: no operation in this version accepts a value at this path. The official schema leaves ${capture.open_namespace} open and names no fields inside it, and whether a value there belongs to the experiment or to each run is an open scientific question for a person to settle. This application does not decide it.`;
  }
  if (path === CREATED_UTC_PATH) {
    return 'There is nothing to type here: no operation in this version accepts a value at this path. When the record is exported, the exporter keeps a value the draft already holds and stamps the export time only when it holds none.';
  }
  return 'There is nothing to type here: no operation in this version accepts a value at this path.';
}

/**
 * The one path the exporter sentence above is true of.
 *
 * Named rather than inlined so the branch reads as the single-path claim it is.
 * `recordIdentity.ts` holds the same literal for its own reason; this is copy routing,
 * not a second definition of anything the server derives.
 */
const CREATED_UTC_PATH = 'timestamps.created_utc';

/**
 * The control itself. Rendered by `FieldRow` only when {@link canEnterOnRecord} holds.
 *
 * EVERY STATE IS WORDS, not a colour and not a spinner alone: idle, saving, saved,
 * refused, and the one named refusal (a stale write). `mutationFailureCopy` supplies the
 * session sentence for an intercepted or unauthenticated write, so this control reads
 * the same as every other write in the app rather than blaming the value.
 *
 * A 412 IS NEVER TURNED INTO A SILENT OVERWRITE. The record moved and nothing was
 * written; the select keeps the reader's choice, says so, and stops offering Save until a
 * DIFFERENT record version arrives — a condition it can observe rather than a delay it
 * guesses at. `onSaved` refreshes the record silently, which is what supplies that
 * version. (The same device `RenameExperimentPanel` uses; see its `staleAt`.)
 *
 * BLANK IS NOT A DELETE, AND THE COPY SAYS SO. The empty option means "nothing chosen",
 * and choosing it does not send a request: no operation in this build clears a
 * record-level field, so a control that appeared to clear one would be promising a
 * removal that never happens. Save stays disabled until a real value is chosen.
 */
export function FieldCaptureControl({
  field,
  experimentId,
  version,
  onSaved,
}: {
  field: DraftField;
  experimentId: string;
  /** The RECORD's current version token — both operations here are the record's. */
  version: string;
  /**
   * Refresh the record. MUST be the SILENT refetch: `RecordWorkbench` unmounts its whole
   * loaded body while its fetch is not in the `data` state, so the loading variant would
   * destroy this control mid-announcement and drop focus to `<body>` — the same trap
   * `RenameExperimentPanel.onSaved` documents.
   */
  onSaved: () => void;
}) {
  const choices = field.capture?.choices ?? [];
  const current = typeof field.value === 'string' ? field.value : '';
  const [choice, setChoice] = useState(current);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [staleAt, setStaleAt] = useState<string | null>(null);
  const selectRef = useRef<HTMLSelectElement>(null);

  const baseId = useId();
  const selectId = `${baseId}-value`;
  const errorId = `${baseId}-error`;
  const statusId = `${baseId}-status`;
  const noteId = `${baseId}-note`;

  const isStale = staleAt !== null && staleAt === version;

  /*
   * THE BOX FOLLOWS THE RECORD ONLY WHILE THE READER HAS CHOSEN NOTHING, and that
   * condition is the whole of this effect rather than a refinement of it.
   *
   * A plain `setChoice(current)` on every change of the stored value was what this
   * used to be, and it CONTRADICTED THE REFUSAL MESSAGE ONE LINE BELOW. `RecordWorkbench`
   * holds a record session that silently refetches the whole bundle on any change
   * signal, and the 412 branch calls `onSaved()` itself — so the common stale-write
   * path is precisely the one where the stored value changes while a choice is held.
   * The reader would see `STALE_MESSAGE`'s *"Nothing you chose has been lost"* beside a
   * select the effect had just reset to somebody else's value.
   *
   * `serverValue` remembers what the record held when the reader last agreed with it.
   * A choice that still equals that is not an edit, so the new stored value is adopted;
   * a choice that differs is unsent work and is kept. What the record now holds is not
   * hidden by keeping it: the row RENDERS the stored value two lines above this control,
   * which is where `STALE_MESSAGE` sends the reader to look.
   */
  const serverValue = useRef(current);
  useEffect(() => {
    if (serverValue.current === current) return;
    const agreedWith = serverValue.current;
    serverValue.current = current;
    setChoice((chosen) => (chosen === agreedWith ? current : chosen));
  }, [current]);

  useEffect(() => {
    if (staleAt !== null && staleAt !== version) {
      setStaleAt(null);
      setError((held) => (held === STALE_MESSAGE ? null : held));
    }
  }, [version, staleAt]);

  const submit = async (event: { preventDefault: () => void }) => {
    event.preventDefault();
    if (busy || choice === '') return;
    setBusy(true);
    setError(null);
    try {
      /* `present` decides the operation, because the server does: measured, `answers`
         refuses an already-held value and `edit` refuses one that is not held yet. */
      const write = field.present ? api.editField : api.submitAnswer;
      await write(experimentId, { [field.path]: choice }, version);
      setBusy(false);
      setSaved(true);
      setStaleAt(null);
      /* FOCUS IS MOVED BEFORE THE REFRESH LANDS, and it is not a flourish. Save is
         disabled while `busy` and disabled again the moment the refreshed record makes
         `choice === current` — so a reader who ACTIVATED it would be left focused on a
         disabled control, which drops focus to `<body>`. The select is the same control
         group and still exists, so focus stays where the reader is working. The
         confirmation is announced by the live region either way. */
      selectRef.current?.focus();
      onSaved();
    } catch (err) {
      setBusy(false);
      setSaved(false);
      if (statusOf(err) === 412) {
        setStaleAt(version);
        setError(STALE_MESSAGE);
        onSaved();
        return;
      }
      /* Anything else is reported as whatever the API layer could establish, and is NOT
         reinterpreted into a friendlier cause. The server's own 422 message names the
         allowed values when it refuses one, which is more useful than anything this
         file could say about it. */
      setError(
        mutationFailureCopy(
          err,
          err instanceof Error && err.message ? err.message : FAILED_MESSAGE,
        ),
      );
    }
  };

  return (
    <form className="field-capture" onSubmit={submit}>
      <label className="field-capture-label" htmlFor={selectId}>
        {field.present ? 'Change this value' : 'Record this value'}
      </label>
      <div className="field-capture-controls">
        <select
          ref={selectRef}
          id={selectId}
          className="field-capture-select"
          value={choice}
          aria-invalid={error !== null || undefined}
          /* The note is ALWAYS described, the same way the rename panel's character
             count always is: a reader arriving on this control by keyboard hears that
             the set comes from the official schema and that nothing is filled in for
             them, rather than having to find the sentence below it. */
          aria-describedby={error !== null ? `${errorId} ${noteId}` : noteId}
          onChange={(e) => {
            setChoice(e.target.value);
            setSaved(false);
            // A stale-write refusal is not cleared by choosing again: the held version
            // is still the rejected one. Every other error is fixable here, so it goes.
            if (error !== null && !isStale) setError(null);
          }}
        >
          {/* NOT a placeholder — it is the honest rendering of a value the record does
              not hold. Choosing it sends nothing; see the header on why a blank is not
              a delete here. */}
          <option value="">— not recorded —</option>
          {choices.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
        <button
          type="submit"
          className="btn btn-secondary"
          disabled={busy || isStale || choice === '' || choice === current}
        >
          {busy ? 'Saving…' : 'Save'}
        </button>
      </div>
      {/* ALWAYS MOUNTED, empty when there is nothing to say: a live region inserted
          together with its content is announced unreliably. */}
      <p className="field-capture-status" id={statusId} role="status">
        {saved && !busy && error === null ? 'Saved to this record.' : ''}
      </p>
      {error !== null && (
        <p className="field-capture-error" id={errorId} role="alert">
          {error}
        </p>
      )}
      <p className="field-capture-note" id={noteId}>
        The value you choose is stored with your confirmation as its evidence. These are
        the values the official ISAAC schema allows here; nothing else is accepted, and
        nothing is filled in for you.
      </p>
    </form>
  );
}

const STALE_MESSAGE =
  'This record changed somewhere else, so nothing was written. It has been refreshed — ' +
  'check what it now holds and choose again. Nothing you chose has been lost.';

const FAILED_MESSAGE = 'The value could not be saved, and nothing was written.';
