/*
 * ONE RUN, as a collapsible card.
 *
 * COLLAPSED it answers the four questions a scientist scanning a list of runs
 * actually has: which run is this, what conditions was it taken under, how much
 * of it is filled in, and is anything wrong with it. The conditions read as one
 * instrument-log line in mono (`in_situ · 300 K · 2026-01-31T09:00:00Z`) —
 * the one place on this surface where mono type carries identity rather than
 * demoting a path, because that line IS how a run is told apart from its
 * siblings.
 *
 * EXPANDED it is TWO COLLAPSIBLE SECTIONS, and it used to be one flat list. The
 * first is the short form over the five run-level fields the run may hold itself;
 * the second is what it inherits from its record. Each carries a count of something
 * enumerated in its own button, so a collapsed section says what is in it, and each
 * can be put away — a card with fourteen inherited rows above a five-field form was
 * a wall the reader had to scroll past to reach whichever half they came for. (Fourteen
 * is measured against the committed seed draft, not the thirteen overridable addresses:
 * see the exception named below.)
 *
 * WHAT SECTION ONE OFFERS A CONTROL FOR IS DECIDED ELSEWHERE, and that is the point.
 * The field list is `RUN_FIELDS`, which is the frontend transcription of
 * `routes.RUN_WRITABLE_FIELD_PATHS` — pinned against it by
 * `apps/api/tests/test_run_api.py`, not re-derived here. An UNCLASSIFIED field
 * (`workspace.field_level`'s real third answer: the six `system.configuration.*`
 * paths and `timestamps.created_utc`) therefore never becomes a control THERE,
 * because a control at one of those has exactly one possible outcome — a typed 422 —
 * and handing a scientist one is the defect. `run-relevance.test.tsx` pins it, from
 * the direction it could actually fail: a run carrying those paths in its own
 * `run.fields`.
 *
 * THAT GUARANTEE IS SECTION ONE'S, NOT THE WHOLE CARD'S, AND THIS HEADER USED TO CLAIM
 * OTHERWISE — while the card offered exactly one such control two sections down. The
 * known exception, named rather than smoothed over: section two renders one row per
 * address `workspace.resolve_inherited` reports, and that key set is every path in the
 * experiment's own draft that `field_level` calls experiment-level. `field_level` is a
 * segment-aware PREFIX test, while `EXPERIMENT_OVERRIDABLE_ADDRESSES` applies a second
 * gate — membership in `EXTRACTOR_FIELD_MAP`. `field:system.domain` passes the first
 * and fails the second, and the committed seed draft carries it, so the panel renders
 * 14 rows where 13 addresses are overridable and `system.domain`'s Override control
 * can only ever return `422 not_overridable` (verified, and pinned server-side in both
 * directions).
 *
 * IT IS LEFT AS IT IS, DELIBERATELY. Suppressing that one row here means either
 * transcribing the backend's admissible-address set into this bundle — a second copy
 * of a classification this file must not own, and the exact thing the paragraph above
 * refuses — or changing what the route resolves, which is a backend decision. The
 * refusal is at least rendered in the server's own words (`RunInheritedPanel` shows
 * the typed message verbatim) rather than as a generic failure.
 *
 * THAT PANEL USED TO BE READ-ONLY and this
 * header used to say so ("it has no controls at all, which is the strongest
 * available statement that those values are not this run's to edit here"). It is
 * no longer true and is not softened: a run may now record its own value at one
 * inherited address, and revert to inheriting again. The panel is
 * `RunInheritedPanel`, and its header states the four domain properties the UI
 * has to stay faithful to — above all that nothing is copied down. Values in it
 * are still not EDITED in place: an override is a separate, confirmed act with
 * its own control, and the record's own value stays visible beside it.
 *
 * ACCESSIBILITY, the parts that are decisions rather than defaults:
 *   * A real accordion — `h3 > button[aria-expanded][aria-controls]` over a
 *     panel with `role="region"` and `aria-labelledby` pointing back at the
 *     button. Not a div with an onClick, and not `aria-selected`.
 *   * The autosave status lives in ONE `role="status"` region per card, so two runs
 *     saving at once are two independent regions rather than one contradictory
 *     stream. It is OUTSIDE the collapsible panel, with Retry Save, so a write the
 *     server refuses is reported and recoverable in either state.
 *     STATED PRECISELY, because the earlier wording said these "announce as two
 *     runs": the region carries no accessible name and no run identity, so a screen
 *     reader hears "Saved" twice and not which run each belongs to. Giving it a name
 *     is a real improvement and is deliberately not smuggled in under a comment fix.
 *   * Every state is a glyph plus words. `Conflict` is not "the amber one".
 *   * A field that will not be sent is marked `aria-invalid` AND says why in
 *     text associated by `aria-describedby`.
 */

import './runs.css';
import { useEffect, useId, useRef, useState } from 'react';
import { StatusChip } from './StatusChip';
import { RunInheritedPanel } from './RunInheritedPanel';
import { RunSection } from './RunSection';
import { inheritedTally, type InheritedTally } from '../lib/runOverrides';
import { Check, ChevronDown, ChevronRight, CircleAlert, RotateCcw, TriangleAlert } from './icons';
import { api } from '../lib/api';
import {
  RUN_FIELDS,
  envelopeText,
  parseRunField,
  runConditionsSummary,
  runFilledCount,
  runFindingText,
  type RunFieldSpec,
} from '../lib/runFields';
import { useRunAutosave, type RunSaveStatus } from '../lib/useRunAutosave';
import type { ApiRunCheckFinding, ApiRunCheckResponse, ApiRunView } from '../lib/types';

/** The glyph for each save state. Paired with words; never used alone. */
const SAVE_ICON: Record<Exclude<RunSaveStatus, 'idle'>, typeof Check> = {
  saving: RotateCcw,
  saved: Check,
  failed: TriangleAlert,
  conflict: CircleAlert,
};

type CheckState =
  | { status: 'idle' }
  | { status: 'busy' }
  | { status: 'data'; data: ApiRunCheckResponse }
  | { status: 'error'; message: string };

export function RunCard({
  experimentId,
  run,
  expanded,
  onToggle,
  onRun,
  focusOnMount,
  onFocused,
}: {
  experimentId: string;
  run: ApiRunView;
  expanded: boolean;
  onToggle: () => void;
  /** Adopt a run the server returned (a save or a refresh). */
  onRun: (run: ApiRunView) => void;
  /** True for the run that was just added — focus moves to its header. */
  focusOnMount?: boolean;
  onFocused?: () => void;
}) {
  const baseId = useId();
  const headerId = `${baseId}-header`;
  const panelId = `${baseId}-panel`;

  const autosave = useRunAutosave({
    experimentId,
    run,
    onRun,
    // Once the server has taken a value, the box stops showing what was TYPED and
    // shows what was STORED. Without this, `1e3` stays in the input while the
    // header's conditions line reads `1000 K` — the same field, two renderings, and
    // no way for the reader to tell which one the record holds.
    onSaved: (saved) =>
      setDraft((prev) => {
        const next = { ...prev };
        let changed = false;
        for (const [path, sentValue] of Object.entries(saved)) {
          if (!(path in next)) continue;
          /*
           * ONLY IF THE BOX STILL HOLDS WHAT WAS SENT. Clearing by path alone
           * reverted the input under the reader's fingers: type `301`, the PATCH
           * leaves, type `301.5`, and `301`'s 200 snapped the box back to `301` with
           * the cursor reset — while `301.5` sat queued and about to be sent. Nothing
           * was lost, but the number on screen was one nobody had typed, and a
           * keystroke in that window appended to the reverted string.
           *
           * The comparison is on the PARSED value rather than the raw text, because
           * the point is exactly that the two can differ in presentation: `1e3` was
           * sent as `1000`, and dropping the draft is what makes the box show `1000`.
           */
          const spec = RUN_FIELDS.find((f) => f.path === path);
          if (spec === undefined) continue;
          const stillTheSame = parseRunField(spec, next[path]);
          if (stillTheSame.ok && stillTheSame.value === sentValue) {
            delete next[path];
            changed = true;
          }
        }
        return changed ? next : prev;
      }),
  });

  /*
   * The text currently in each box, for the fields the reader has touched.
   * Untouched fields read straight from the run, so a value written by anything
   * else (a save's response, a refresh) shows up without this component having
   * to reconcile two copies of it.
   */
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [check, setCheck] = useState<CheckState>({ status: 'idle' });

  // A refresh replaced the run wholesale, so the boxes must stop showing the
  // text the reader chose not to keep.
  const { adoptedNonce } = autosave;
  useEffect(() => {
    setDraft({});
    setFieldErrors({});
  }, [adoptedNonce]);

  const headerRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!focusOnMount) return;
    headerRef.current?.focus();
    onFocused?.();
    // Runs once for the run that was just created; `onFocused` clears the flag.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusOnMount]);

  const onFieldChange = (spec: RunFieldSpec, raw: string) => {
    setDraft((prev) => ({ ...prev, [spec.path]: raw }));
    const parsed = parseRunField(spec, raw);
    if (!parsed.ok) {
      // Held on screen, not sent. The server never sees a value this build
      // cannot even shape, and the reader is told which box and why.
      setFieldErrors((prev) => ({ ...prev, [spec.path]: parsed.error }));
      return;
    }
    setFieldErrors((prev) => {
      if (prev[spec.path] === undefined) return prev;
      const next = { ...prev };
      delete next[spec.path];
      return next;
    });
    autosave.queue(spec.path, parsed.value);
  };

  const runCheck = () => {
    setCheck({ status: 'busy' });
    api
      .checkRun(experimentId, run.id)
      .then((data) => setCheck({ status: 'data', data }))
      .catch((err: unknown) =>
        setCheck({
          status: 'error',
          message: err instanceof Error ? err.message : 'The check could not be run.',
        }),
      );
  };

  const conditions = runConditionsSummary(run);
  const filled = runFilledCount(run);
  const Chevron = expanded ? ChevronDown : ChevronRight;

  /*
   * WHAT THIS RUN INHERITS, COUNTED — never guessed and never a percentage.
   *
   * `inheritedTally` calls `overrideRows` for the numbers about rows, so the count in
   * the section header and the rows inside it are the same list read twice rather
   * than two readings of the same data. It is also what chooses the empty state
   * below: `shown === 0` is precisely "the panel would render nothing", because the
   * panel renders `overrideRows` and nothing else.
   */
  const tally = inheritedTally(run);

  /*
   * A CLIENT-REFUSED FIELD IS A CARD-LEVEL FACT, for exactly the reason a
   * server-refused one is (see the note above the header).
   *
   * `onFieldChange` returns before `autosave.queue` when `parseRunField` refuses the
   * text, so the hook's status is not touched at all. If the previous state was
   * `saved`, the live region went on reading "Saved" while this card held an edit
   * that would never be sent — and the hook's own definition of that word is "the
   * server answered 200 to a PATCH carrying every edit this hook held, AND NOTHING
   * HAS BEEN TYPED SINCE". Something had been typed since.
   *
   * The error text itself lives inside `{expanded && …}`, so collapsing the card
   * removed the only indication, and nothing clears `fieldErrors` outside a refresh:
   * the card sat at `300 K · 1 of 3 set · Saved` indefinitely while holding "abc".
   * This is the same defect finding I3 fixed for server refusals; client refusals
   * were left out of that rule and are brought under it here.
   */
  const invalidPaths = Object.keys(fieldErrors);
  const heldInvalid = invalidPaths.length > 0;
  const notSentLabel =
    invalidPaths.length === 1 ? 'Change not sent' : `${invalidPaths.length} changes not sent`;

  /*
   * HELD-INVALID IS ADDITIVE, NEVER A REPLACEMENT — and the first version of this got
   * that wrong in the one way that matters most.
   *
   * It read `showHeldInvalid ? notSentLabel : autosave.label`, which SUPPRESSED
   * `failed` and `conflict` in the live region while a comment two lines up claimed it
   * "does not suppress `saving`/`failed`/`conflict`". Measured consequence: with an
   * invalid field held and a 412 on another field, the region said only "Change not
   * sent" and the header said both — so the header and the region disagreed about
   * which state was current, and **the word `Conflict` never reached the live region
   * at all**. For a screen-reader user the one state that requires their decision was
   * announced nowhere.
   *
   * THE ONE STATE IT STILL REPLACES IS `saved`, and that asymmetry is the whole point
   * rather than an inconsistency. `Saved` is defined as "the server took every edit
   * this hook held AND NOTHING HAS BEEN TYPED SINCE" — holding an unparseable entry
   * makes the second half false, so the word must go. `saving`, `failed` and
   * `conflict` all remain true about a different edit, so they stay and the
   * held-invalid fact is added beside them.
   */
  const suppressedSaved = heldInvalid && autosave.status === 'saved';
  const transportLabel = suppressedSaved ? null : autosave.label;
  const showHeldInvalid = heldInvalid;
  const SaveIcon =
    transportLabel !== null
      ? SAVE_ICON[autosave.status as Exclude<RunSaveStatus, 'idle'>]
      : heldInvalid
        ? TriangleAlert
        : null;
  /*
   * ONE SENTENCE, ASSEMBLED IN A FIXED ORDER: the transport state, then WHY it
   * failed, then the separate fact that this card is also holding something it will
   * not send. The cause stays adjacent to the state it explains — an earlier draft
   * concatenated the held-invalid clause into the middle and produced
   * "Save failed · Change not sent · Request failed (428)", which reads as though the
   * 428 were the reason the unparseable value was not sent.
   */
  const statusText =
    [transportLabel, autosave.failureMessage, showHeldInvalid ? notSentLabel : null]
      .filter((part): part is string => part !== null && part !== '')
      .join(' · ') || null;

  return (
    <article className="run-card" data-run-id={run.id}>
      <h3 className="run-card-heading">
        <button
          ref={headerRef}
          id={headerId}
          type="button"
          className="run-card-header"
          aria-expanded={expanded}
          aria-controls={panelId}
          onClick={onToggle}
        >
          <Chevron className="run-card-chevron" size={16} strokeWidth={2} aria-hidden="true" />
          <span className="run-card-name">{run.label}</span>
          <span className="run-card-conditions">
            {conditions ?? <span className="run-card-conditions-empty">No conditions recorded yet</span>}
          </span>
          {/*
            THE DENOMINATOR DISCLOSES ITS SCOPE, because this project has a written
            rule against one that does not: a coverage figure must be "enumerated
            from the record's own content" (`docs/evidence-sidecar-audit.md:172`,
            `docs/mentor-decisions.md:57`), and the status bar already carries a
            dedicated affordance for exactly this — `.statusbar-cover-scope`, "the
            record-specific denominator disclosure sitting beside the figure it
            qualifies".

            "1 of 3 set" said none of that, and the disclosure is MORE necessary now
            rather than less. The gap it originally named — this screen offered three
            of the five paths `RUN_WRITABLE_FIELD_PATHS` accepts — is closed: the
            screen offers all five. The gap that MATTERS is the one that remains and
            is much larger: a valid ISAAC record needs far more than five fields, most
            of them inherited from the experiment. So "5 of 5" is still displayable on
            a run whose Check Run fails, which is exactly the completion claim the bare
            number was never entitled to make.

            Not deleted when the smaller gap closed, because the sentence a reader
            needs is "this counts the fields on this screen, not the record" — and
            that is true of five as it was of three.
          */}
          <span className="run-card-progress">
            {filled} of {RUN_FIELDS.length}{' '}
            <span className="run-card-progress-scope">run fields on this screen</span>
          </span>
          <CheckSummaryChip check={check} />
          {/*
            A REFUSED WRITE IS A HEADER FACT, not a panel one. `failed` used to
            be rendered only inside the expanded panel, so a save that was
            refused after the reader collapsed the card was announced nowhere
            and recoverable nowhere — the card read exactly as if nothing had
            happened. It sits beside `conflict` because they are the same kind
            of claim: this run holds an edit the server has not taken. Inside
            the header button on purpose — that puts the words into the
            header's accessible name, so reaching the collapsed card by
            keyboard alone says what is wrong with it.
          */}
          {autosave.status === 'failed' && <StatusChip kind="fail" label="Save failed" />}
          {autosave.status === 'conflict' && <StatusChip kind="needsYou" label="Conflict" />}
          {/* Same reasoning as the two above, and the same place: in the header
              button, so the collapsed card says it in its accessible name. */}
          {showHeldInvalid && <StatusChip kind="needsYou" label={notSentLabel} />}
        </button>
      </h3>

      {/*
        THE AUTOSAVE READOUT — one live region per card, OUTSIDE the collapsible
        panel so it exists in both states and in the accessibility tree before
        it has anything to say. (A region added to the DOM at the same moment it
        is populated is not reliably announced.) It is empty until this card has
        something to report, so a reader is not told "Saved" about a run they
        have not touched, and it takes no vertical space while empty.

        RETRY SAVE LIVES HERE TOO, rather than in the panel's action row. The
        state it belongs to is exactly the state in which the reader may not be
        able to see the panel: requiring them to expand a card to reach the only
        control that re-sends a refused edit puts a step between the problem and
        its remedy for no benefit. It cannot be a second control inside the
        header — that button already owns the whole row, and a button inside a
        button is not valid.
      */}
      <div className="run-card-save" data-save-status={autosave.status}>
        <p className="run-save-status" role="status" data-save-status={autosave.status}>
          {/* `statusText` already carries the state, WHY it failed, and any
              held-invalid edit, in that order — see where it is built. The cause is
              part of it because "Save failed" with no reason made a 428, a 404 after a
              workspace reset in another tab, and an unreachable backend one
              indistinguishable state whose only control was a Retry that would loop. */}
          {statusText && SaveIcon && (
            <>
              <SaveIcon className="run-save-icon" size={14} strokeWidth={2.2} aria-hidden="true" />
              {statusText}
            </>
          )}
        </p>
        {autosave.status === 'failed' && (
          <button type="button" className="btn btn-secondary" onClick={autosave.retryNow}>
            Retry Save
          </button>
        )}
      </div>

      {/*
        THE ONE LIMIT THE APP CANNOT ENGINEER AWAY, SAID ON SCREEN.
        Save state now outlives this card, so an edit abandoned by switching tabs still
        reaches the server and its outcome still comes back. It does NOT outlive the
        PAGE: nothing in a browser can promise that, because `beforeunload` cannot hold
        a tab open for a fetch and `sendBeacon` can carry neither an `If-Match`
        precondition nor a readable response, both of which a compare-and-swap write
        needs. A reload deliberately discards held edits rather than replaying them over
        a document that may have moved.
        Shown ONLY while something is unacknowledged — a permanent warning about work at
        risk would be false most of the time, and this project has enough copy that was
        true when written. Two file headers claimed this sentence existed before it did;
        `run-workspace.test.tsx` now pins it so the claim stays checkable.

        TWO CORRECTIONS A REVIEWER MADE TO THE FIRST VERSION OF THIS, and they had to be
        made together because fixing either alone made the other worse:

        · IT SAID "discards anything the server has not yet acknowledged", which
          OVER-CLAIMS. What is certainly lost is anything not yet SENT. An edit in flight
          when the tab closes may well have been committed — the browser simply never
          learns, which is the exact distinction this branch built `unresolvedAttempt`
          for and which the conflict panel two elements away already draws. Asserting
          loss where the honest answer is unknown fate is the same mistake as
          "Nothing you typed was written".
        · IT WAS GATED ON `pendingCount > 0`, and `send()` empties the pending map before
          dispatching — so the note VANISHED for the whole in-flight window and flickered
          back if the request failed. Absent in exactly the state it describes. Gating on
          the transport state instead covers both sub-states of `saving`.
      */}
      {(autosave.status === 'saving' ||
        autosave.status === 'failed' ||
        autosave.status === 'conflict' ||
        heldInvalid) && (
        <p className="run-card-session-note">
          Changes this tab has not finished saving live here only. If you close the tab or
          reload, anything still unsent is lost — and anything already sent may or may not
          have been saved.
        </p>
      )}

      {expanded && (
        <div id={panelId} className="run-card-body" role="region" aria-labelledby={headerId}>
          {/*
            A RUN WITH NOTHING TO SHOW SAYS SO, rather than presenting five empty
            boxes under a heading and letting the reader work out whether that is the
            product or a rendering failure.

            THE CONDITION IS NARROW ON PURPOSE. It is stated only when this run holds
            none of its own values AND the panel below would render nothing AND
            nothing was withheld as unrenderable — because in the withheld case the
            record DOES carry something at an inherited address, and "the record
            carries none" would then be false. That branch is stated by the inherited
            section's own empty text instead, which is where the fact lives.

            AND THE SENTENCE IS SCOPED TO THE FIELD ADDRESSES THIS CARD SHOWS, which is
            a correction rather than a wording preference. It used to end "the record
            carries nothing at the addresses a run inherits", and a freshly created
            experiment's run resolves `block:attribution` — measured on the running app —
            so the claim was contradicted by the server's own resolution while every
            number in `tally` stayed zero. The condition is unchanged: the note is most
            useful in exactly that case, and the block addresses are named by the
            inherited section's own disclosure below rather than denied here.
          */}
          {filled === 0 && tally.shown === 0 && tally.withheld === 0 && (
            <p className="run-section-note">
              This run holds none of its own values yet, and the record carries nothing at the
              record-level field addresses this card shows. The fields below are the ones this
              run can hold; everything else on the record is entered on the record.
            </p>
          )}

          {/*
            SECTION ONE — THE RUN'S OWN FIELDS, AND ONLY THOSE.
            The list is `RUN_FIELDS`, and it is iterated as a closed list rather than
            derived from `run.fields`. That is the whole relevance filter for this
            half of the card, and it is a load-bearing choice rather than a
            convenience: `run.fields` is the run's raw draft field map, so anything a
            future extractor writes into it would become a control here — including
            `system.configuration.*` and `timestamps.created_utc`, which
            `workspace.field_level` classifies as UNCLASSIFIED and which
            `RUN_WRITABLE_FIELD_PATHS` therefore excludes. A control at one of those
            paths would have exactly one possible outcome, a typed 422, so it must
            never be offered. Pinned by `run-relevance.test.tsx`.
          */}
          <RunSection
            title="Conditions for this run"
            /*
              A COUNT OF THINGS ENUMERATED, WITH ITS SCOPE ATTACHED. `filled` counts
              `RUN_FIELDS` entries this run carries a value for and the denominator is
              that list's own length, so both halves are read off the list rendered
              below. It is deliberately NOT a completion figure: a valid ISAAC record
              needs far more than these five, most of them entered on the record — the
              same disclosure the collapsed header carries, for the same reason.
            */
            summary={`${filled} of ${RUN_FIELDS.length} recorded — the run-level fields on this screen`}
          >
            <div className="run-fields">
              {RUN_FIELDS.map((spec) => {
                const fieldId = `${baseId}-${spec.path}`;
                const errorId = `${fieldId}-error`;
                const hintId = `${fieldId}-hint`;
                const error = fieldErrors[spec.path];
                const value = draft[spec.path] ?? envelopeText(run.fields?.[spec.path]);
                const describedBy =
                  [error ? errorId : null, spec.hint ? hintId : null].filter(Boolean).join(' ') ||
                  undefined;
                return (
                  <div className="run-field" key={spec.path}>
                    <label className="run-field-label" htmlFor={fieldId}>
                      {spec.label}
                      {spec.unit ? <span className="run-field-unit"> ({spec.unit})</span> : null}
                    </label>
                    <div className="run-field-control">
                      {spec.kind === 'enum' ? (
                        <select
                          id={fieldId}
                          className="run-input"
                          value={value}
                          aria-invalid={error !== undefined || undefined}
                          aria-describedby={describedBy}
                          onChange={(e) => onFieldChange(spec, e.target.value)}
                        >
                          {/* The empty option is how a value is CLEARED. It is not
                              a placeholder: choosing it sends `null`. */}
                          <option value="">Not set</option>
                          {spec.options?.map((option) => (
                            <option key={option} value={option}>
                              {option}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <input
                          id={fieldId}
                          className="run-input"
                          type="text"
                          inputMode={spec.kind === 'number' ? 'decimal' : undefined}
                          value={value}
                          aria-invalid={error !== undefined || undefined}
                          aria-describedby={describedBy}
                          onChange={(e) => onFieldChange(spec, e.target.value)}
                        />
                      )}
                      <span className="run-field-path">{spec.path}</span>
                      {spec.hint && (
                        <span className="run-field-hint" id={hintId}>
                          {spec.hint}
                        </span>
                      )}
                      {error && (
                        <span className="run-field-error" id={errorId}>
                          <TriangleAlert size={13} strokeWidth={2.2} aria-hidden="true" />
                          {error}
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </RunSection>

          {/*
            SECTION TWO — WHAT THE RUN INHERITS, WITH #122's PRESENTATION UNTOUCHED.

            THE INHERITED PANEL IS NO LONGER READ-ONLY, and the copy it used to carry
            was already false for a row it could render. It said, flatly, "Change an
            inherited value on the experiment, not here", while `inheritedFieldRows`
            admitted `state === 'overridden'` — the run's OWN value — beside it. That
            was unreachable when it was written (no HTTP route reached
            `set_run_override`), which is exactly why it was easy to write and easy to
            miss. Both routes exist now, so the panel drives them and says what they
            actually do; see `RunInheritedPanel` for the four domain properties it has
            to stay faithful to.

            NOTHING ABOUT THE PANEL ITSELF IS CHANGED HERE — not a label, not a
            treatment, not a control. It is wrapped in a disclosure and given an
            honest alternative for the case where it would render nothing at all,
            which is the one thing it could not say for itself: `overrideRows` empty
            made the whole panel `return null`, so a run inheriting nothing showed no
            heading, no sentence and no explanation, and the reader could not tell
            that apart from a section that failed to load.

            THE SECTION TITLE IS NOT THE PANEL'S OWN EYEBROW, and the difference is
            deliberate rather than a near-miss. `RunInheritedPanel` names itself
            "Inherited from the record" (eyebrow) and "Values inherited from the
            record" (region), both set by #122 and neither touched here; repeating
            either verbatim one line above them would read as a rendering fault. This
            names the same thing from the RUN's side, which is whose card it is.
          */}
          <RunSection
            title="Values this run inherits"
            summary={inheritedSummary(tally)}
          >
            {tally.shown > 0 ? (
              <RunInheritedPanel experimentId={experimentId} run={run} onRun={onRun} />
            ) : (
              <InheritedEmpty tally={tally} />
            )}
          </RunSection>

          {autosave.status === 'conflict' && (
            <div className="run-conflict" role="alert">
              <CircleAlert className="run-conflict-icon" size={18} strokeWidth={2.2} aria-hidden="true" />
              <div className="run-conflict-body">
                <p className="run-conflict-title">This run changed somewhere else</p>
                {/*
                  TWO DIFFERENT TRUTHS, AND THE CARD USED TO TELL ONLY THE FIRST.
                  A 412 on a FIRST attempt does mean nothing of yours was written.
                  A 412 on a RETRY does not: the retried attempt exists because no
                  response reached this browser, and a response can be lost after
                  the server has committed — so the earlier write may be exactly
                  what moved this run. Saying "Nothing you typed was written" there
                  would be a confident false statement about the reader's data, and
                  Refresh would then contradict it by showing the value present.
                */}
                {autosave.retriedBeforeConflict ? (
                  <p className="run-conflict-text">
                    Your last change may or may not have been saved — the first attempt got no
                    reply, so this browser cannot tell. Refresh to see exactly what the server
                    holds; it replaces what is in these boxes.
                  </p>
                ) : (
                  <p className="run-conflict-text">
                    Nothing you typed was written. Refresh to load the version the server holds —
                    it replaces what is in these boxes.
                  </p>
                )}
              </div>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={autosave.refresh}
                disabled={autosave.refreshing}
              >
                {autosave.refreshing ? 'Refreshing…' : 'Refresh This Run'}
              </button>
            </div>
          )}

          <div className="run-card-actions">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={runCheck}
              disabled={check.status === 'busy'}
            >
              {check.status === 'busy' ? 'Checking…' : 'Check Run'}
            </button>
            {/*
              The save readout and Retry Save used to live here. They are at
              card level now — see the note above the header — because both of
              them have to work on a card the reader has collapsed.
            */}
          </div>

          <CheckResult check={check} />
        </div>
      )}
    </article>
  );
}

/**
 * The inherited section's one-line summary. COUNTS ONLY — never a completion figure.
 *
 * Both numbers are read off the rows the panel renders (see {@link inheritedTally}),
 * and the zero is stated rather than omitted: "0 overridden on this run" is a fact a
 * reader can act on, while an absent clause is indistinguishable from a clause this
 * build forgot to render.
 *
 * THE EMPTY SUMMARY USED TO READ "nothing for this run to inherit", AND THAT WAS
 * FALSE FOR THE COMMONEST RUN IN THE PRODUCT. A freshly created experiment's run
 * resolves exactly one address — `block:attribution` — which this list does not
 * render, so `shown` was 0 while the run inherited something (measured; see
 * {@link InheritedTally.blocks}). This summary now describes THIS LIST, which is all
 * it can see, and names the block addresses it is not showing rather than denying
 * they exist.
 */
function inheritedSummary(tally: InheritedTally): string {
  if (tally.shown > 0) {
    return `${tally.inherited} inherited · ${tally.overridden} overridden on this run`;
  }
  if (tally.blocks.length > 0) {
    return `no record-level fields in this list · ${tally.blocks.length} whole-block address${
      tally.blocks.length === 1 ? '' : 'es'
    } not shown here`;
  }
  return 'no record-level fields in this list';
}

/**
 * WHAT AN EMPTY INHERITED SECTION SAYS, and why it is three sentences and not one.
 *
 * The three cases are genuinely different facts about a scientist's record, and a
 * single sentence would state one of them when another holds:
 *
 *   * NOTHING RESOLVED — the record carries no value at any record-level FIELD
 *     address, so there is nothing in this list yet.
 *   * EVERYTHING RESOLVED IS `absent` — the server resolved N field addresses and
 *     neither the record nor this run carries anything at any of them. That is a
 *     different statement from the first, and the count is the server's own.
 *   * SOMETHING IS WITHHELD — the record DOES carry a value at one or more of those
 *     addresses, and this surface has no honest one-line rendering for it (an object
 *     or an array). Saying "carries nothing" here would be false; see
 *     `isUnrenderableValue`.
 *
 * EVERY ONE OF THE THREE IS SCOPED TO THE FIELD ADDRESSES THIS LIST SHOWS, and that
 * scoping is a FIX, measured against the running app rather than reasoned about. All
 * three used to be claims about THE RECORD — "the record carries no values at the
 * addresses a run inherits", "nothing was hidden" — while `inheritedTally` counted
 * only `field:` addresses. A freshly created experiment's run resolves exactly
 * `block:attribution` (state `inherited`), an address that IS in
 * `routes.EXPERIMENT_OVERRIDABLE_ADDRESSES` and IS resolved by
 * `workspace.resolve_inherited`, so all three sentences contradicted the server's own
 * answer in the same response. Two repairs were possible and the choice is deliberate:
 * counting blocks in the field numbers would make them count rows nobody can see and
 * would route an EMPTY block through the withheld sentence, which sends the reader to
 * the record to read a value that is not there. Scoping states less and states it
 * truly — and the block addresses are then NAMED rather than denied.
 *
 * WHAT WAS DELETED AND NOT REPLACED: "Nothing was hidden". It was false as written —
 * `overrideRows` excludes every `block:` address by design — and the honest form of it
 * is the disclosure sentence below, which says what is not shown instead of asserting
 * that nothing is.
 *
 * ITS ONE KNOWN LIMIT, stated because the reader of this file should not have to
 * discover it: the block disclosure appears only when this section would otherwise be
 * EMPTY. A section with field rows still drops its block addresses silently, exactly
 * as it drops `withheld` rows — the same pre-existing gap, deliberately not widened
 * or narrowed here.
 *
 * None of the three says anything about whether the run is complete, valid or ready.
 */
function InheritedEmpty({ tally }: { tally: InheritedTally }) {
  if (tally.withheld > 0) {
    return (
      <>
        <p className="run-section-empty">
          The record carries {tally.withheld} value
          {tally.withheld === 1 ? '' : 's'} at an address this run inherits that this list cannot
          show in one line. Nothing is hidden from the record itself — open the record to read it.
        </p>
        <InheritedBlocksNote tally={tally} />
      </>
    );
  }
  if (tally.resolved === 0) {
    return (
      <>
        <p className="run-section-empty">
          The record carries no values at the record-level field addresses this list shows, so
          there is nothing in this list yet. Record-level values are entered on the record, and
          every run reads them live.
        </p>
        <InheritedBlocksNote tally={tally} />
      </>
    );
  }
  return (
    <>
      <p className="run-section-empty">
        This run resolves {tally.resolved} record-level field address
        {tally.resolved === 1 ? '' : 'es'} and none of them holds a value — neither the record nor
        this run carries anything at those. Nothing here failed to load.
      </p>
      <InheritedBlocksNote tally={tally} />
    </>
  );
}

/**
 * THE ADDRESSES THIS LIST DOES NOT SHOW, named — not a count of values.
 *
 * It states two things and neither is about content: how many `block:` addresses the
 * server resolved for this run, and what they are called. It does NOT say the record
 * carries a value at any of them, because it cannot: `{contributors: []}` is the live
 * payload of the commonest one and there is nothing in it to read.
 *
 * THE VERB IS "resolves", COPIED FROM THE SERVER'S OWN WORD, and not "inherits". A
 * block address is overridable server-side (`block:attribution`, `block:tags` are both
 * in `EXPERIMENT_OVERRIDABLE_ADDRESSES`), so a run reached over the API may hold its
 * own value at one — "inherits" would then be false, while "resolves" is true in every
 * state the server reports.
 */
function InheritedBlocksNote({ tally }: { tally: InheritedTally }) {
  if (tally.blocks.length === 0) return null;
  const plural = tally.blocks.length !== 1;
  return (
    <p className="run-section-empty">
      This run also resolves {tally.blocks.length} whole-block address{plural ? 'es' : ''} that
      this list does not show — {tally.blocks.join(', ')}. A block is an object or a list, and
      this surface has no honest one-line rendering for one.
    </p>
  );
}

/**
 * The collapsed-header verdict chip. Absent until a check has actually run.
 *
 * IT USED TO ATTRIBUTE THE FAILURE TO THE WRONG THING. The label was
 * `${blockers.length} Blocking` whenever the count was non-zero, but `ok` is
 * `draft.ok && official.ok` — so a run with two open blockers AND a schema error
 * read "2 Blocking", and the schema error was invisible on the collapsed card. The
 * count is only used now when it is the WHOLE story.
 */
function CheckSummaryChip({ check }: { check: CheckState }) {
  if (check.status !== 'data') return null;
  const { data } = check;
  if (data.ok) return <StatusChip kind="pass" label="Check Passed" />;
  if (data.official?.unavailable === true) {
    return <StatusChip kind="needsYou" label="Could Not Be Checked" />;
  }
  const n = data.blockers?.length ?? 0;
  const schemaFailed =
    data.official?.ok === false || (data.official?.errors?.length ?? 0) > 0;
  const draftFailed = data.draft?.ok === false || (data.draft?.errors?.length ?? 0) > 0;
  if (n > 0 && !schemaFailed && !draftFailed) {
    return <StatusChip kind="fail" label={`${n} Blocking`} />;
  }
  return <StatusChip kind="fail" label="Check Failed" />;
}

/**
 * The Check Run findings.
 *
 * WHAT THIS MUST NEVER SAY, and the reason it is spelled out here rather than
 * left to whoever edits the copy next: a check is a read of the run through the
 * existing draft validator and the official-schema DRY RUN. It writes nothing,
 * exports nothing and submits nothing. "Passed" here means the two deterministic
 * validators found nothing blocking at the version named below it — not that
 * anything was produced, filed or accepted.
 */
function CheckResult({ check }: { check: CheckState }) {
  if (check.status === 'idle' || check.status === 'busy') return null;
  if (check.status === 'error') {
    return (
      <div className="run-check run-check-error" role="alert">
        <TriangleAlert size={16} strokeWidth={2.2} aria-hidden="true" />
        <span>{check.message}</span>
      </div>
    );
  }

  const { data } = check;
  const draftErrors = data.draft?.errors ?? [];
  const officialErrors = data.official?.errors ?? [];
  /*
   * "COULD NOT BE CHECKED" IS NOT "FAILED", and the card used to say the second.
   * `_validate_unit` sets `unavailable` on the two branches whose own comment reads
   * "no verdict, not a schema violation" — an unreadable written artifact, or an
   * exception during the dry run. `ok` is `false` in both (fail-closed, correct), and
   * the card turned that into `Check Failed`, asserting a schema verdict the server
   * had explicitly declined to give. Nothing here upgrades the outcome: it is still
   * not a pass, and the blockers and draft findings are still shown.
   */
  const unavailable = data.official?.unavailable === true;

  return (
    <section className="run-check" aria-label="Check result">
      <div className="run-check-head">
        {data.ok ? (
          <StatusChip kind="pass" label="Check Passed" />
        ) : unavailable ? (
          <StatusChip kind="needsYou" label="Could Not Be Checked" />
        ) : (
          <StatusChip kind="fail" label="Check Failed" />
        )}
        <span className="run-check-scope">
          Read-only check of run version {data.checked_run_version}. Nothing was written,
          submitted or exported.
        </span>
      </div>

      <FindingList title="Blocking" findings={data.blockers ?? []} />
      <FindingList title="Draft checks" findings={draftErrors} />
      {/*
        THE TITLE NAMES WHICH DOCUMENT WAS READ, and it used to lie in one direction.
        It was hard-coded to "Official schema (dry run)". `_validate_unit`
        (`routes.py:3901`) returns `dry_run: false` for a MATERIALISED unit, where it
        validates the record already written to `records/` — so after an export the
        card described findings about a filed artifact as a dry run. The default is
        the cautious one: `dry_run` is optional on the wire, and an absent flag is not
        evidence of a dry run, so the unqualified heading is used rather than a
        claim about which document it was.
      */}
      <FindingList
        title={
          data.official?.dry_run === true
            ? 'Official schema (dry run)'
            : data.official?.dry_run === false
              ? 'Official schema (the record already written)'
              : 'Official schema'
        }
        findings={officialErrors}
      />

      {data.ok && (data.blockers?.length ?? 0) === 0 && (
        <p className="run-check-clean">
          The draft and official-schema checks found nothing blocking this run.
        </p>
      )}
    </section>
  );
}

function FindingList({ title, findings }: { title: string; findings: ApiRunCheckFinding[] }) {
  if (findings.length === 0) return null;
  return (
    <div className="run-check-group">
      <p className="run-check-group-title">
        {title} · {findings.length}
      </p>
      <ul className="run-check-list">
        {findings.map((finding, i) => {
          const text = runFindingText(finding);
          return (
            <li key={i} className={text === null ? 'run-check-item run-check-item-opaque' : 'run-check-item'}>
              {/* A finding this build cannot describe is still COUNTED and still
                  shown. Dropping it would quietly shrink the number of things
                  standing between this run and a valid record. */}
              {text ?? 'The server reported a finding this build cannot describe.'}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
