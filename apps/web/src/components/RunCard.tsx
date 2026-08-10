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
 * EXPANDED it is a short form over three run-level fields and a read-only panel
 * of what the run inherits from its experiment. The inherited panel is not
 * styled as a disabled version of the form: it has no controls at all, which is
 * the strongest available statement that those values are not this run's to
 * edit here.
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
import { Check, ChevronDown, ChevronRight, CircleAlert, RotateCcw, TriangleAlert } from './icons';
import { api } from '../lib/api';
import {
  RUN_FIELDS,
  envelopeText,
  inheritedFieldRows,
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
    onSaved: (paths) =>
      setDraft((prev) => {
        const next = { ...prev };
        let changed = false;
        for (const path of paths) {
          if (path in next) {
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
  const inherited = inheritedFieldRows(run);
  const Chevron = expanded ? ChevronDown : ChevronRight;

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

  // `heldInvalid` WINS over `saved` and loses to nothing, because it is the only one
  // of the two that is still true. It does not suppress `saving`/`failed`/`conflict`:
  // those describe a different edit that really is in flight or really was refused.
  const showHeldInvalid = heldInvalid && autosave.status !== 'saving';
  const SaveIcon = showHeldInvalid
    ? TriangleAlert
    : autosave.status === 'idle'
      ? null
      : SAVE_ICON[autosave.status];
  const statusText = showHeldInvalid ? notSentLabel : autosave.label;

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

            "1 of 3 set" said none of that. Three is the number of run-level fields
            THIS SCREEN offers; the backend accepts five (`RUN_WRITABLE_FIELD_PATHS`),
            and a valid ISAAC record needs far more than either, most of it inherited.
            So "3 of 3 set" was displayable on a run whose Check Run fails — a
            completion claim the number was never entitled to make.
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
          {statusText && SaveIcon && (
            <>
              <SaveIcon className="run-save-icon" size={14} strokeWidth={2.2} aria-hidden="true" />
              {statusText}
              {/* WHY IT FAILED, in the server's or the transport's own words. The
                  card used to render "Save failed" and nothing else, so a 428, a
                  404 after a workspace reset in another tab, and an unreachable
                  backend were one indistinguishable state whose only control was a
                  Retry that would loop. */}
              {autosave.failureMessage !== null && (
                <span className="run-save-cause"> · {autosave.failureMessage}</span>
              )}
            </>
          )}
        </p>
        {autosave.status === 'failed' && (
          <button type="button" className="btn btn-secondary" onClick={autosave.retryNow}>
            Retry Save
          </button>
        )}
      </div>

      {expanded && (
        <div id={panelId} className="run-card-body" role="region" aria-labelledby={headerId}>
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

          {inherited.length > 0 && (
            <section className="run-inherited" aria-label="Values inherited from the experiment">
              <p className="run-inherited-eyebrow">Inherited from Experiment</p>
              {/*
                THE SECOND SENTENCE USED TO BE FALSE FOR A ROW THIS LIST RENDERS.
                `inheritedFieldRows` admits `state === 'overridden'`, whose payload is
                the RUN's own value, and the row labels itself "Overridden by This
                Run" — inside a panel that said, flatly, "read by every run. Change
                them on the experiment, not here." Unreachable today (no HTTP route
                reaches `set_run_override`, so `resolve_inherited` cannot report
                `overridden` through this API), which is exactly why it was easy to
                write and easy to miss: the copy was already wrong for the branch
                that ships.
              */}
              <p className="run-inherited-note">
                Entered once on the experiment and read by every run that does not override
                them. Change an inherited value on the experiment, not here; a row marked
                “Overridden by This Run” is this run's own value, not the experiment's.
              </p>
              <ul className="run-inherited-list">
                {inherited.map((row) => (
                  <li className="run-inherited-row" key={row.address}>
                    <span className="run-inherited-path">{row.path}</span>
                    <span className="run-inherited-value">{row.text}</span>
                    <span className="run-inherited-state">
                      {row.state === 'overridden' ? 'Overridden by This Run' : 'Inherited from Experiment'}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}

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
