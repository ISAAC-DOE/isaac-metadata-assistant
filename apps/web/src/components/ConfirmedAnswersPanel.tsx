import './confirmed-answers.css';
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api, ApiError } from '../lib/api';
import { answerValuePreview, pendingItemToBlocker } from '../lib/adapt';
import { LABELS } from '../lib/labels';
import { isUnstorableFieldValue, officialShapeMismatch } from '../lib/mutationErrors';
import { ROUTES } from '../lib/routes';
import type {
  ApiAnswersResponse,
  ApiStructuredAnswer,
  ApiStructuredAnswersResponse,
  ApiStructuredUnit,
  StructuredAnswerKey,
} from '../lib/types';
import { Disclosure } from './Disclosure';
import { BackendDown, LoadingPanel } from './FetchStates';
import { GuidedPrompt } from './GuidedPrompt';
import { ShapeMismatchNotice } from './ShapeMismatchNotice';
import { StatusChip } from './StatusChip';
import { Pencil } from './icons';

/**
 * CONFIRMED ANSWERS — the reduced spectrum, QC verdict and descriptor a record HOLDS,
 * each correctable through the existing correction operation (QA audit A-01/A-04).
 *
 * ── THE DEFECT ──────────────────────────────────────────────────────────────
 *
 * These three answers were visible — and correctable — only during the visit that
 * answered them, because Guided Completion kept its answered rows in component state.
 * After a reload, Complete said "No open questions", Export Readiness (refusing the
 * record) said "Back to Complete →", and the reader went round that loop with no exit.
 * Record Fields, Runs and the Evidence Trail showed no editor and never showed the
 * confirmed value at all: no read operation served it. The correction routes worked;
 * nothing reached them.
 *
 * ── WHAT THIS DOES, AND DOES NOT DO ─────────────────────────────────────────
 *
 * It reads `GET .../structured-answers` — the record's own blocks when it has no runs,
 * each run's when it has them — and shows every confirmed value, in a one-line preview
 * and in full one click away. Edit opens the same `GuidedPrompt` the completion screen
 * uses, PREFILLED WITH THE STORED VALUE AND NOTHING ELSE; Save is `POST .../edit` (or a
 * run's), with the unit's own version as `If-Match`. Nothing is invented, defaulted or
 * prefilled from anywhere but the record.
 *
 * Edit is offered exactly where the server says the correction will be accepted
 * (`editable`), so no control here has only one possible outcome. An OPEN question is
 * not edited here — it is answered — so it links to Complete Metadata instead, which
 * is the screen that answers it. A confirmed answer the server will not let this form
 * correct (several descriptors, which the correction would collapse to one) is shown
 * read-only with the server's reason.
 */

export const CONFIRMED_ANSWERS_PAGE = 10;

const ORDER: readonly StructuredAnswerKey[] = ['series', 'qc', 'descriptor'] as const;

/** The question a CORRECTION asks — it is not the open-question prose, which asks for
 *  a value the record has never had. */
const CORRECT_QUESTION: Record<StructuredAnswerKey, string> = {
  series: 'Correct the reduced spectrum.',
  qc: 'Correct the QC verdict and the reasoning behind it.',
  descriptor: 'Correct the scientific descriptor.',
};

type State =
  | { status: 'loading' }
  | { status: 'error'; error: ApiError }
  | { status: 'data'; page: ApiStructuredAnswersResponse; units: ApiStructuredUnit[] };

function asApiError(err: unknown): ApiError {
  return err instanceof ApiError
    ? err
    : new ApiError(err instanceof Error ? err.message : String(err));
}

/** One answer's editor identity: unique across units, so two runs' spectra never share
 *  DOM ids, staged text or a "not applied" note. */
const rowKey = (unit: ApiStructuredUnit, key: StructuredAnswerKey) =>
  `structured:${unit.run_id ?? 'record'}:${key}`;

export function ConfirmedAnswersPanel({
  experimentId,
  runId,
  onCorrected,
  headingLevel = 2,
}: {
  experimentId: string;
  /** Show only this run's answers (the run screen). Omitted: the record, or every run. */
  runId?: string;
  /** Called with the correction's response, so the host can adopt the new version and
   *  the server's re-derived workflow rather than re-deriving either. */
  onCorrected?: (resp: ApiAnswersResponse) => void;
  headingLevel?: 2 | 3;
}) {
  const [state, setState] = useState<State>({ status: 'loading' });
  const [editing, setEditing] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<{ row: string; error: ApiError } | null>(null);
  const [notApplied, setNotApplied] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  /* A FAILED "Show More" IS ITS OWN STATE (review, minor c). It used to flip the whole
     panel to its error branch, which unmounted an open editor and took the reader's
     typed correction with it — over a read of OTHER runs that changed nothing here. */
  const [moreError, setMoreError] = useState<ApiError | null>(null);
  /* A re-read of one unit after a save that did not land is said, never shown as data. */
  const [refreshFailed, setRefreshFailed] = useState(false);
  /* Rows whose correction landed on an EXPORTED unit — the after-the-fact note (I-3). */
  const [savedPastExport, setSavedPastExport] = useState<Set<string>>(new Set());

  const load = useCallback(() => {
    api
      .getStructuredAnswers(experimentId, { limit: CONFIRMED_ANSWERS_PAGE, runId })
      .then((page) => setState({ status: 'data', page, units: page.units }))
      .catch((err: unknown) => setState({ status: 'error', error: asApiError(err) }));
  }, [experimentId, runId]);

  useEffect(() => {
    setState({ status: 'loading' });
    load();
  }, [load]);

  const loadMore = () => {
    if (state.status !== 'data') return;
    setLoadingMore(true);
    api
      .getStructuredAnswers(experimentId, {
        limit: CONFIRMED_ANSWERS_PAGE,
        offset: state.units.length,
        runId,
      })
      .then((next) =>
        setState((prev) => {
          if (prev.status !== 'data') return prev;
          const held = new Set(prev.units.map((u) => u.run_id));
          return {
            status: 'data',
            page: next,
            units: [...prev.units, ...next.units.filter((u) => !held.has(u.run_id))],
          };
        }),
      )
      .catch((err: unknown) => setMoreError(asApiError(err)))
      .finally(() => setLoadingMore(false));
  };

  /*
   * RE-READ ONE UNIT, in place (review, minor c). A save used to call `load()`, which
   * re-read page one and dropped every page "Show More" had added — so correcting run 14
   * sent the reader back to runs 1–10. Only the unit that changed is re-read (`run_id`
   * filter; a record with no runs has one unit and is read whole), and it replaces its
   * own row; nothing else on screen moves.
   */
  const refreshUnit = (unit: ApiStructuredUnit) => {
    setRefreshFailed(false);
    api
      .getStructuredAnswers(experimentId, { limit: 1, runId: unit.run_id ?? undefined })
      .then((fresh) => {
        const next = fresh.units[0];
        if (next === undefined) return;
        setState((prev) =>
          prev.status !== 'data'
            ? prev
            : {
                ...prev,
                units: prev.units.map((u) => (u.run_id === next.run_id ? next : u)),
              },
        );
      })
      .catch(() => setRefreshFailed(true));
  };

  const save = (unit: ApiStructuredUnit, key: StructuredAnswerKey, value: unknown) => {
    const row = rowKey(unit, key);
    setSaving(true);
    setSaveError(null);
    setNotApplied(null);
    const answer = unit.answers[key];
    // A DESCRIPTOR KEEPS ITS OUTPUT LABEL. The correction rebuilds the descriptor block,
    // and without the label it falls back to the server's default — a change the reader
    // did not ask for, made by saving something else.
    const body: Record<string, unknown> = { [key]: value };
    if (key === 'descriptor' && typeof answer.label === 'string' && answer.label !== '') {
      body.descriptor_label = answer.label;
    }
    api
      .editField(experimentId, body, unit.version, unit.run_id ?? undefined)
      .then((resp) => {
        onCorrected?.(resp);
        if (resp.invalidation?.changed !== true) {
          // 200 with nothing changed: the stored value did not become the typed one.
          setNotApplied(row);
          return;
        }
        setEditing(null);
        if (unit.exported) setSavedPastExport((prev) => new Set(prev).add(row));
        // RE-READ rather than patched locally: the server owns the stored value and the
        // unit's new version, and a correction can change both.
        refreshUnit(unit);
      })
      .catch((err: unknown) => setSaveError({ row, error: asApiError(err) }))
      .finally(() => setSaving(false));
  };

  const Heading = headingLevel === 2 ? 'h2' : 'h3';

  if (state.status === 'loading') {
    return <LoadingPanel label="Loading the confirmed answers from the ISAAC API…" />;
  }
  if (state.status === 'error') {
    return (
      <section className="confirmed-answers" aria-labelledby="confirmed-answers-heading">
        <Heading className="confirmed-answers-title" id="confirmed-answers-heading">
          {LABELS.confirmedAnswersHeading}
        </Heading>
        <BackendDown error={state.error} onRetry={load} />
      </section>
    );
  }

  const { page, units } = state;
  return (
    <section className="confirmed-answers" aria-labelledby="confirmed-answers-heading">
      <Heading className="confirmed-answers-title" id="confirmed-answers-heading">
        {LABELS.confirmedAnswersHeading}
      </Heading>
      <p className="confirmed-answers-lead">
        The reduced spectrum, QC verdict and scientific descriptor this record holds
        {page.level === 'run' ? ', run by run' : ''}. Each stored one can be corrected here
        unless it holds something this form cannot carry back; nothing is filled in for you.
      </p>
      {refreshFailed && (
        <div className="completion-submit-error" role="alert">
          Your correction was saved, but this panel could not re-read it — the values shown
          may be the earlier ones.{' '}
          <button type="button" className="btn btn-secondary confirmed-inline-btn" onClick={load}>
            Reload
          </button>
        </div>
      )}
      {units.map((unit) => (
        <div className="confirmed-unit" key={unit.run_id ?? 'record'}>
          {unit.run_label !== null && (
            <div className="confirmed-unit-label">{unit.run_label}</div>
          )}
          {/*
            REVIEW I-3 — SAID BEFORE ANY EDIT, NOT ONLY AFTER. Correcting an exported unit
            answers 200 and its exported file stays exactly as written, which is the
            immutability guarantee — but re-export then answers 409 `record_exists`, so the
            change can never reach an official record. A scientist must know that before
            choosing to edit, not discover it from a stale banner afterwards.
          */}
          {unit.exported && (
            <p className="confirmed-exported-note" role="note">
              {unit.run_label !== null ? 'This run’s' : 'This record’s'} official record has
              been exported. A correction here changes the working copy only — the exported
              file is fixed, and will not include it.
            </p>
          )}
          <ul className="confirmed-list">
            {ORDER.map((key) => {
              const row = rowKey(unit, key);
              return (
                <AnswerRow
                  key={row}
                  experimentId={experimentId}
                  unit={unit}
                  answerKey={key}
                  answer={unit.answers[key]}
                  editing={editing === row}
                  anyEditing={editing !== null}
                  saving={saving}
                  onEdit={() => {
                    setEditing(row);
                    setSaveError(null);
                    setNotApplied(null);
                  }}
                  onCancel={() => {
                    setEditing(null);
                    setSaveError(null);
                    setNotApplied(null);
                  }}
                  onSave={(value) => save(unit, key, value)}
                  error={saveError?.row === row ? saveError.error : null}
                  notApplied={notApplied === row}
                  savedPastExport={savedPastExport.has(row)}
                  onRefresh={() => {
                    setEditing(null);
                    setSaveError(null);
                    load();
                  }}
                />
              );
            })}
          </ul>
        </div>
      ))}
      {units.length < page.total && (
        <div className="confirmed-more">
          <span className="confirmed-more-note">
            Showing {units.length} of {page.total} runs.
          </span>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={loadMore}
            disabled={loadingMore}
          >
            {loadingMore ? 'Loading…' : 'Show More Runs'}
          </button>
        </div>
      )}
      {moreError && <BackendDown error={moreError} onRetry={loadMore} />}
    </section>
  );
}

function AnswerRow({
  experimentId,
  unit,
  answerKey,
  answer,
  editing,
  anyEditing,
  saving,
  onEdit,
  onCancel,
  onSave,
  error,
  notApplied,
  savedPastExport,
  onRefresh,
}: {
  experimentId: string;
  unit: ApiStructuredUnit;
  answerKey: StructuredAnswerKey;
  answer: ApiStructuredAnswer;
  editing: boolean;
  anyEditing: boolean;
  saving: boolean;
  onEdit: () => void;
  onCancel: () => void;
  onSave: (value: unknown) => void;
  error: ApiError | null;
  notApplied: boolean;
  savedPastExport: boolean;
  onRefresh: () => void;
}) {
  const blocker = pendingItemToBlocker({
    id: answerKey,
    kind: answerKey,
    question: CORRECT_QUESTION[answerKey],
    about: null,
    demo_answer: null,
    run_id: unit.run_id,
    run_label: unit.run_label,
    blocker_key: rowKey(unit, answerKey),
  });
  const forRun = unit.run_label !== null ? ` for ${unit.run_label}` : '';

  if (editing) {
    const mismatch = error ? officialShapeMismatch(error) : null;
    return (
      <li className="confirmed-row editing">
        {unit.exported && (
          <p className="confirmed-exported-note" role="note">
            Saving changes this working copy only. The exported official record will not
            change.
          </p>
        )}
        <GuidedPrompt
          blocker={blocker}
          index={0}
          total={1}
          submitting={saving}
          initialValue={answer.value}
          initialStaged
          confirmLabel={LABELS.actionSave}
          dontKnowLabel={LABELS.actionCancel}
          hideBlankHint
          onConfirm={onSave}
          onDontKnow={onCancel}
        />
        {mismatch && (
          <ShapeMismatchNotice findings={mismatch.findings} more={mismatch.more} correcting />
        )}
        {error && !mismatch && error.status === 412 && (
          <div className="completion-submit-error" role="alert">
            This record changed elsewhere. Nothing was applied. Refresh to load the current
            value, then correct it again.
            <button
              type="button"
              className="btn btn-secondary confirmed-inline-btn"
              onClick={onRefresh}
            >
              Refresh
            </button>
          </div>
        )}
        {error && !mismatch && error.status !== 412 && (
          <div className="completion-submit-error" role="alert">
            {isUnstorableFieldValue(error)
              ? 'That correction was not applied — this field still holds the value it held before, and nothing was written. Check the value and try again.'
              : `That correction could not be applied (${error.status ?? 'error'}). Nothing was changed — try again.`}
          </div>
        )}
        {notApplied && (
          <div className="completion-submit-error" role="alert">
            Nothing was applied — this field still holds its previously confirmed value, and
            nothing was invented in its place. Try again, or Cancel to keep it.
          </div>
        )}
      </li>
    );
  }

  return (
    <li className="confirmed-row" data-state={answer.state}>
      <span className="confirmed-label">{blocker.label}</span>
      {answer.state === 'confirmed' ? (
        <>
          <span className="confirmed-value">
            {answerValuePreview(answerKey, answer.value)}
          </span>
          <span className="confirmed-trailing">
            {/* RE-REVIEW (minor): the chip says what the value's OWN evidence is. It read
                "Confirmed by You" for every stored value, and canonical seeds 1 and 4 hold
                a QC verdict whose only evidence is a spreadsheet row — a confirmation that
                never happened. An unknown or absent answer claims nothing. */}
            <StatusChip
              kind={
                answer.confirmation === 'confirmed'
                  ? 'confirmed'
                  : answer.confirmation === 'from_evidence'
                    ? 'origEvidence'
                    : 'origUnknown'
              }
            />
            {answer.editable ? (
              <button
                type="button"
                className="answered-edit"
                onClick={onEdit}
                aria-label={`${LABELS.actionEdit} ${blocker.label}${forRun}`}
                disabled={anyEditing}
              >
                <Pencil size={13} strokeWidth={2.2} aria-hidden="true" />
                {LABELS.actionEdit}
              </button>
            ) : null}
          </span>
          {!answer.editable && answer.reason && (
            <p className="confirmed-reason">{answer.reason}</p>
          )}
          {savedPastExport && (
            <p className="confirmed-exported-note" role="status">
              Saved. The exported file no longer matches this record — it is fixed, so it
              does not include this change.
            </p>
          )}
          <Disclosure
            summary={`Show the stored ${blocker.label.toLowerCase()}`}
            className="confirmed-stored"
          >
            <pre className="mono confirmed-json">{JSON.stringify(answer.value, null, 2)}</pre>
          </Disclosure>
        </>
      ) : answer.state === 'open' ? (
        <>
          <span className="confirmed-value confirmed-missing">Not answered yet</span>
          <span className="confirmed-trailing">
            <Link className="confirmed-answer-link" to={ROUTES.complete(experimentId)}>
              Answer in {LABELS.screenComplete}
            </Link>
          </span>
        </>
      ) : (
        <span className="confirmed-value confirmed-missing">Not set</span>
      )}
    </li>
  );
}

/**
 * The same panel, mounted only once its disclosure is OPENED — for the run card.
 *
 * A run card is a working surface the reader may never want this on, and every
 * mounted panel is a read. Mounting on open means a card that is never expanded
 * here costs nothing, and the read happens exactly when someone asks to see the
 * run's confirmed answers. It is otherwise the same component with `runId` set.
 */
export function RunConfirmedAnswers({
  experimentId,
  runId,
  onCorrected,
}: {
  experimentId: string;
  runId: string;
  onCorrected?: (resp: ApiAnswersResponse) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Disclosure
      summary="Confirmed Answers for This Run"
      open={open}
      onOpenChange={setOpen}
      className="confirmed-run-disclosure"
    >
      {open && (
        <ConfirmedAnswersPanel
          experimentId={experimentId}
          runId={runId}
          onCorrected={onCorrected}
          headingLevel={3}
        />
      )}
    </Disclosure>
  );
}
