/*
 * RECORD DESCRIPTION — the capture surface for what the whole record is.
 *
 * ── THE DEFECT THIS CLOSES ───────────────────────────────────────────────────
 *
 * A scientist creating a record in-product could not say where it was measured, what
 * it was measured on, who contributed, or what campaign it belongs to. The twelve
 * facility/sample paths were accepted at exactly ONE route — a RUN's override, which
 * records a divergence from a value the record does not hold — and `system.domain` /
 * `system.technique` had a record-level route that no screen anywhere reached
 * (`rg -a` for every plausible spelling returned zero hits). A record could be
 * finished and exported, and could not be described.
 *
 * ── WHAT IT WRITES, AND THROUGH WHAT ─────────────────────────────────────────
 *
 * `POST /api/experiments/{id}/answers` for a value the record does not yet hold and
 * `POST /api/experiments/{id}/edit` to correct one it does — the EXISTING confirmed
 * write path, with the RECORD's `If-Match`. There is no new write route and no second
 * concurrency scheme. The server draws that line and refuses the wrong side of it
 * (`already_answered` / `not_yet_answered`), so a save partitions its keys by what the
 * server last reported and sends at most two requests.
 *
 * ── FIVE THINGS THIS PANEL WILL NOT DO ───────────────────────────────────────
 *
 * 1. IT NEVER PROPOSES A VALUE. No default is selected, nothing is prefilled from
 *    another field, and nothing is derived: `system.domain` is not inferred from
 *    `system.technique` (that classification exists nowhere in this repository) and a
 *    facility name is not inferred from a beamline.
 * 2. IT NEVER TRANSCRIBES A VOCABULARY. Every closed list — the 37 techniques, the two
 *    domains, the four contributor roles — is read from the vendored schema the server
 *    already publishes at `GET /api/schema`. When that read fails, the pickers say they
 *    are unavailable; they do not degrade to a free-text box, because a value outside
 *    the schema's list produces a record that cannot export.
 * 3. IT NEVER SILENTLY OVERWRITES. A `412` stale write shows the conflict, adopts the
 *    version the server reported, and disables Save until the reader re-reads — with
 *    everything they typed still on screen.
 * 4. IT NEVER CLAIMS A SAVE IT DID NOT MAKE. A save that lands one request and fails
 *    the other says exactly that and names which values landed.
 * 5. IT NEVER SHRINKS A LIST IT COULD NOT READ. A stored contributor whose shape this
 *    build cannot present is COUNTED and disclosed, and while any such entry exists the
 *    contributor editor is read-only — replacing the block would delete what could not
 *    be shown.
 *
 * ── AN EMPTY BOX IS NOT A DELETE ─────────────────────────────────────────────
 *
 * The record-level write operations deliberately do not build clearing: un-saying a
 * confirmed record-level value is a real operation with its own questions (what it
 * means for a run that inherited it), and the server drops a blank rather than removing
 * the field. So emptying a box sends nothing, and the panel says so instead of letting
 * a reader believe it erased something.
 */
import { useCallback, useEffect, useId, useMemo, useState } from 'react';

import { api, ApiError } from '../lib/api';
import {
  mutationFailureCopy,
  staleWriteCurrentVersion,
  statusOf,
} from '../lib/mutationErrors';
import {
  RECORD_ATTRIBUTION_ADDRESS,
  RECORD_FIELDS,
  RECORD_FIELD_GROUPS,
  RECORD_TAGS_ADDRESS,
  contributorRoleOptions,
  contributorRows,
  holdsAValue,
  parseRecordField,
  recordFieldFacts,
  tagRows,
  type ContributorRow,
  type RecordFieldFacts,
} from '../lib/recordFields';
import type { ApiDraftResponse, ApiRunsResponse, JsonSchemaNode } from '../lib/types';
import { BackendDown, LoadingPanel } from './FetchStates';
import { ChevronDown, ChevronRight } from './icons';
import './record-description.css';

/** Same narrowing `UnmappedNotesPanel` uses — a non-`ApiError` throw still renders. */
function asApiError(err: unknown): ApiError {
  return err instanceof ApiError
    ? err
    : new ApiError(err instanceof Error ? err.message : String(err));
}

/**
 * How many override-holding runs one page of the runs list is asked for.
 *
 * A BOUND, AND THE DISCLOSURE THAT GOES WITH IT. `docs/run-scale-measurements.md`
 * makes a record's runs a real payload cost, and this panel must not become a second
 * unbounded read of them — so it asks the SERVER to filter (`overrides=any`) and takes
 * one page. When more runs hold an override than this page carries, the panel says so
 * IN WORDS: a per-field count derived from a truncated page and rendered as though it
 * were the whole record is exactly the understatement this repository has shipped
 * before. `matched` is the server's true count and is what the disclosure quotes.
 */
const OVERRIDE_SAMPLE = 25;

/** What the runs list said about record-level values a run has diverged from. */
interface OverrideSummary {
  /** Address -> how many of the EXAMINED runs hold an override there. */
  byAddress: Record<string, number>;
  /** How many runs hold at least one override, per the server. */
  matched: number;
  /** How many of them this page examined. */
  examined: number;
  /** How many runs the record has in total. */
  total: number;
}

interface Loaded {
  version: string;
  /** Path -> the value the server reports the record holds. */
  stored: Record<string, unknown>;
  /** The raw stored payloads, addressed as the write operations address them. */
  blocks: Record<string, unknown>;
  /** The vendored schema, or `null` when it could not be read. */
  schema: JsonSchemaNode | null;
  /** The bounded override picture, or `null` when the runs list could not be read. */
  overrides: OverrideSummary | null;
}

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; error: ApiError }
  | { status: 'ready'; loaded: Loaded };

/** What a save produced. Every variant states what DID happen, never only what failed. */
type SaveState =
  | { kind: 'idle' }
  | { kind: 'saving' }
  | { kind: 'saved'; count: number }
  | { kind: 'stale'; landed: string[]; atVersion: string }
  | { kind: 'failed'; message: string; landed: string[]; perKey: Record<string, string> };

const NOTHING_TO_SAVE = 'Nothing has changed, so nothing was sent.';

/**
 * The one sentence a reader needs about a blank box, stated where they would otherwise
 * conclude the opposite.
 */
const BLANK_IS_NOT_A_DELETE =
  'Emptying a box does not remove a stored value — this screen has no way to un-say a ' +
  'confirmed value, so a blank box is simply not sent.';

export function RecordDescriptionPanel({ experimentId }: { experimentId: string }) {
  const [expanded, setExpanded] = useState(false);
  const bodyId = useId();
  const Chevron = expanded ? ChevronDown : ChevronRight;

  return (
    <section className="field-group" aria-label="Record Description (record-level values)">
      <button
        type="button"
        className="fg-header"
        aria-expanded={expanded}
        aria-controls={expanded ? bodyId : undefined}
        onClick={() => setExpanded((open) => !open)}
      >
        <Chevron className="fg-chevron" size={16} strokeWidth={2} aria-hidden="true" />
        <span className="fg-block">Record Description</span>
        <span className="record-section-key">record-level</span>
        <span className="record-section-summary">
          technique, facility, sample, contributors and tags — every run inherits these
        </span>
      </button>
      {expanded && (
        <div className="fg-body" id={bodyId}>
          {/* Keyed on the record so switching records rebuilds this editor's state
              rather than showing one record's typed values under another's heading. */}
          <RecordDescriptionEditor key={experimentId} experimentId={experimentId} />
        </div>
      )}
    </section>
  );
}

function RecordDescriptionEditor({ experimentId }: { experimentId: string }) {
  const [load, setLoad] = useState<LoadState>({ status: 'loading' });
  const [reloadNonce, setReloadNonce] = useState(0);
  const [save, setSave] = useState<SaveState>({ kind: 'idle' });
  const [text, setText] = useState<Record<string, string>>({});
  const [contribs, setContribs] = useState<ContributorRow[]>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [touched, setTouched] = useState(false);

  const formId = useId();
  const statusId = `${formId}-status`;
  const summaryId = `${formId}-summary`;

  useEffect(() => {
    let live = true;
    setLoad({ status: 'loading' });
    (async () => {
      try {
        // THREE READS, ALL EXISTING ROUTES. The detail carries the record's version
        // token (the `If-Match` every write here takes); the draft carries the stored
        // field values AND the record-level block payloads; the schema carries the
        // closed lists. The schema read is allowed to fail on its own without taking
        // the panel down — see `schema: null` below.
        const [detail, draft, schema, runs] = await Promise.all([
          api.getExperiment(experimentId),
          api.getDraft(experimentId),
          api.getSchema().then(
            (r) => r.schema,
            () => null,
          ),
          // BOUNDED, SERVER-FILTERED, AND ALLOWED TO FAIL ON ITS OWN. It answers a
          // question about OTHER records' runs, so a failure here must not take down
          // the editor for the record in front of the reader.
          api.listRuns(experimentId, { overrides: 'any', limit: OVERRIDE_SAMPLE }).then(
            (r) => r,
            () => null,
          ),
        ]);
        if (!live) return;
        const loaded = toLoaded(detail.version, draft, schema, runs);
        setLoad({ status: 'ready', loaded });
        setText(initialText(loaded));
        setContribs(contributorRows(loaded.blocks[RECORD_ATTRIBUTION_ADDRESS]).rows);
        setTags(tagRows(loaded.blocks[RECORD_TAGS_ADDRESS]).rows);
        setTouched(false);
      } catch (err) {
        if (live) setLoad({ status: 'error', error: asApiError(err) });
      }
    })();
    return () => {
      live = false;
    };
  }, [experimentId, reloadNonce]);

  const reload = useCallback(() => {
    setSave({ kind: 'idle' });
    setReloadNonce((n) => n + 1);
  }, []);

  const loaded = load.status === 'ready' ? load.loaded : null;
  const facts = useMemo<Record<string, RecordFieldFacts>>(() => {
    const out: Record<string, RecordFieldFacts> = {};
    for (const spec of RECORD_FIELDS) out[spec.path] = recordFieldFacts(loaded?.schema, spec.path);
    return out;
  }, [loaded]);
  const roles = useMemo(() => contributorRoleOptions(loaded?.schema), [loaded]);

  const attribution = loaded?.blocks[RECORD_ATTRIBUTION_ADDRESS];
  const storedContributors = useMemo(() => contributorRows(attribution), [attribution]);
  const storedTags = useMemo(
    () => tagRows(loaded?.blocks[RECORD_TAGS_ADDRESS]),
    [loaded],
  );
  /*
   * THE CONTRIBUTOR EDITOR IS FAIL-CLOSED IN THREE CASES, each of which would
   * otherwise DESTROY something on save, because a block write replaces the whole
   * block:
   *
   *  - an entry this build cannot read (a non-object, or a non-string name/role) —
   *    replacing the list would delete it;
   *  - a stored `attribution.uploaded_by`, which is server-owned: echoing it back is
   *    refused by the write, and dropping it would discard a field no client may
   *    author. Not reachable through this application today, and guarded anyway;
   *  - no role vocabulary (the schema read failed), because a role outside the
   *    schema's four produces a contributor an exported record cannot hold.
   */
  const attributionHasUploadedBy =
    typeof attribution === 'object' &&
    attribution !== null &&
    Object.prototype.hasOwnProperty.call(attribution, 'uploaded_by');
  const contributorsReadOnlyReason = storedContributors.unreadable
    ? `This record stores ${storedContributors.unreadable} contributor ${
        storedContributors.unreadable === 1 ? 'entry' : 'entries'
      } this screen cannot present. Editing the list here would replace the whole block and remove ${
        storedContributors.unreadable === 1 ? 'it' : 'them'
      }, so the list is read-only until that entry is corrected elsewhere.`
    : attributionHasUploadedBy
      ? 'This record stores a server-owned `attribution.uploaded_by`. No client may author that field, so the contributor list is read-only here rather than being rewritten without it.'
      : roles === null
        ? 'The official schema could not be read, so the contributor roles it allows are unknown. Roles are chosen from that list and are never free text, so the list is read-only until the schema loads.'
        : null;

  const tagsReadOnlyReason = storedTags.unreadable
    ? `This record stores ${storedTags.unreadable} tag ${
        storedTags.unreadable === 1 ? 'entry' : 'entries'
      } this screen cannot present, and saving would replace the whole list. The tags are read-only until that is corrected elsewhere.`
    : null;

  const isStale = save.kind === 'stale';

  const changes = useMemo(() => {
    if (!loaded) return { values: {}, errors: {} as Record<string, string> };
    return collectChanges({
      loaded,
      facts,
      text,
      contribs,
      tags,
      contributorsEditable: contributorsReadOnlyReason === null,
      tagsEditable: tagsReadOnlyReason === null,
      storedContributors: storedContributors.rows,
      storedTags: storedTags.rows,
    });
  }, [
    loaded,
    facts,
    text,
    contribs,
    tags,
    contributorsReadOnlyReason,
    tagsReadOnlyReason,
    storedContributors,
    storedTags,
  ]);

  const changedKeys = Object.keys(changes.values);
  const localErrors = changes.errors;
  const perKeyErrors = save.kind === 'failed' ? save.perKey : {};

  const onSubmit = useCallback(
    async (event: { preventDefault: () => void }) => {
      event.preventDefault();
      if (!loaded || save.kind === 'saving' || isStale) return;
      if (Object.keys(localErrors).length > 0) return; // the summary already says why
      if (changedKeys.length === 0) {
        setSave({ kind: 'failed', message: NOTHING_TO_SAVE, landed: [], perKey: {} });
        return;
      }
      setSave({ kind: 'saving' });

      // PARTITIONED BY WHAT THE SERVER LAST REPORTED, not by anything remembered: a
      // key the record already holds must go to the correction operation, and one it
      // does not must go to the answering operation. Sending either to the other is a
      // typed 422 the reader did nothing to earn.
      const toAnswer: Record<string, unknown> = {};
      const toEdit: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(changes.values)) {
        const current = key.startsWith('block:')
          ? loaded.blocks[key]
          : loaded.stored[key];
        (blockHoldsSomething(key, current) ? toEdit : toAnswer)[key] = value;
      }

      let version = loaded.version;
      const landed: string[] = [];
      try {
        if (Object.keys(toAnswer).length > 0) {
          const written = await api.submitAnswer(experimentId, toAnswer, version);
          version = written.version;
          landed.push(...Object.keys(toAnswer));
        }
        if (Object.keys(toEdit).length > 0) {
          const written = await api.editField(experimentId, toEdit, version);
          version = written.version;
          landed.push(...Object.keys(toEdit));
        }
        setSave({ kind: 'saved', count: landed.length });
        reloadAfterWrite();
      } catch (err) {
        const current = staleWriteCurrentVersion(err);
        if (statusOf(err) === 412) {
          // THE ONE FAILURE A READER CANNOT FIX BY TYPING. The token is adopted so a
          // re-read has something newer to hold, Save stays disabled, and nothing they
          // typed is discarded.
          setSave({ kind: 'stale', landed, atVersion: current ?? version });
          return;
        }
        setSave({
          kind: 'failed',
          message: mutationFailureCopy(
            err,
            asApiError(err).message || 'The record could not be updated.',
          ),
          landed,
          perKey: perKeyMessages(err),
        });
      }

      function reloadAfterWrite() {
        // A SILENT RE-READ. The panel's own stored values have to come from the server
        // again — the next save partitions on them, and partitioning on what this
        // component believes it wrote is how a second save gets routed to the wrong
        // operation.
        setReloadNonce((n) => n + 1);
      }
    },
    [changes, changedKeys.length, experimentId, isStale, loaded, localErrors, save.kind],
  );

  if (load.status === 'loading') return <LoadingPanel label="Loading the record's description…" />;
  if (load.status === 'error') return <BackendDown error={load.error} onRetry={reload} />;

  const summaryEntries = [
    ...Object.entries(localErrors),
    ...Object.entries(perKeyErrors),
  ];

  return (
    <form className="rdesc" onSubmit={onSubmit} aria-describedby={statusId}>
      <p className="rdesc-lead">
        These values belong to the record, and every run inherits them by reference —
        change one here and it changes for every run that has not recorded its own
        override. {BLANK_IS_NOT_A_DELETE}
      </p>
      <p className="rdesc-lead">{overrideLead(loaded?.overrides ?? null)}</p>

      {/* ALWAYS MOUNTED, empty when there is nothing to say. A live region inserted
          together with its content is announced unreliably, and this is the one place
          the reader is told a save actually landed. */}
      <p className="rdesc-status" id={statusId} role="status">
        {statusSentence(save)}
      </p>

      {summaryEntries.length > 0 && (
        <div className="rdesc-summary" id={summaryId} role="alert">
          <p className="rdesc-summary-title">
            {summaryEntries.length === 1
              ? 'One value was not accepted:'
              : `${summaryEntries.length} values were not accepted:`}
          </p>
          <ul className="rdesc-summary-list">
            {summaryEntries.map(([key, message]) => (
              <li key={key}>
                <a href={`#${controlId(formId, key)}`}>{labelFor(key)}</a> — {message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {save.kind === 'stale' && (
        <div className="rdesc-conflict" role="alert">
          <p>
            This record changed somewhere else while you were editing, so nothing further
            was written.{' '}
            {save.landed.length > 0
              ? `${save.landed.length} value${save.landed.length === 1 ? '' : 's'} had already been saved before that happened: ${save.landed.map(labelFor).join(', ')}.`
              : 'No value from this save was written.'}{' '}
            Everything you typed is still here. Re-read the record to see what it says
            now, then save again — nothing is overwritten in the meantime.
          </p>
          <button type="button" className="btn btn-secondary" onClick={reload}>
            Re-read this record
          </button>
        </div>
      )}

      {RECORD_FIELD_GROUPS.map((group) => (
        <fieldset className="rdesc-group" key={group.id}>
          <legend className="rdesc-legend">{group.title}</legend>
          <div className="rdesc-rows">
            {RECORD_FIELDS.filter((spec) => spec.group === group.id).map((spec) => (
              <FieldRow
                key={spec.path}
                id={controlId(formId, spec.path)}
                label={spec.label}
                path={spec.path}
                facts={facts[spec.path]}
                schemaLoaded={loaded !== null && loaded.schema !== null}
                value={text[spec.path] ?? ''}
                stored={loaded?.stored[spec.path]}
                overrideNote={overrideNote(loaded?.overrides ?? null, `field:${spec.path}`)}
                error={localErrors[spec.path] ?? perKeyErrors[spec.path]}
                disabled={save.kind === 'saving' || isStale}
                onChange={(next) => {
                  setTouched(true);
                  setText((prev) => ({ ...prev, [spec.path]: next }));
                }}
              />
            ))}
          </div>
        </fieldset>
      ))}

      <ContributorsEditor
        formId={formId}
        rows={contribs}
        roles={roles}
        readOnlyReason={contributorsReadOnlyReason}
        error={perKeyErrors[RECORD_ATTRIBUTION_ADDRESS]}
        disabled={save.kind === 'saving' || isStale}
        onChange={(rows) => {
          setTouched(true);
          setContribs(rows);
        }}
      />

      <TagsEditor
        formId={formId}
        rows={tags}
        readOnlyReason={tagsReadOnlyReason}
        error={perKeyErrors[RECORD_TAGS_ADDRESS]}
        disabled={save.kind === 'saving' || isStale}
        onChange={(rows) => {
          setTouched(true);
          setTags(rows);
        }}
      />

      <div className="rdesc-actions">
        <button
          type="submit"
          className="btn btn-primary"
          disabled={save.kind === 'saving' || isStale}
        >
          {save.kind === 'saving' ? 'Saving…' : 'Save record description'}
        </button>
        <span className="rdesc-pending-count">
          {changedKeys.length === 0
            ? touched
              ? 'No unsaved changes.'
              : ''
            : `${changedKeys.length} unsaved change${changedKeys.length === 1 ? '' : 's'}.`}
        </span>
      </div>
    </form>
  );
}

/* ---- rows ---------------------------------------------------------------- */

function FieldRow({
  id,
  label,
  path,
  facts,
  schemaLoaded,
  value,
  stored,
  overrideNote: overrideText,
  error,
  disabled,
  onChange,
}: {
  id: string;
  label: string;
  path: string;
  facts: RecordFieldFacts;
  schemaLoaded: boolean;
  value: string;
  stored: unknown;
  overrideNote: string | null;
  error?: string;
  disabled: boolean;
  onChange: (next: string) => void;
}) {
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hintId, error ? errorId : null].filter(Boolean).join(' ');
  // A CLOSED LIST IS ONLY A PICKER WHEN THE SCHEMA SAID SO. When the schema could not
  // be read this renders a stated inability rather than a text box, because a value
  // outside the list produces a record that cannot export.
  const pickerUnavailable = !schemaLoaded && facts.allowed === null;

  return (
    <div className="rdesc-row">
      <label className="rdesc-label" htmlFor={id}>
        {label}
      </label>
      {facts.allowed ? (
        <select
          id={id}
          className="rdesc-input"
          value={value}
          disabled={disabled}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          onChange={(e) => onChange(e.target.value)}
        >
          {/* NO DEFAULT IS SELECTED. An empty option means "not answered", and picking
              it sends nothing — it is not a way to clear a stored value. */}
          <option value="">— not set —</option>
          {facts.allowed.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      ) : (
        <input
          id={id}
          className="rdesc-input"
          type="text"
          inputMode={
            facts.declaredType === 'number' || facts.declaredType === 'integer'
              ? 'decimal'
              : undefined
          }
          value={value}
          disabled={disabled}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
      <span className="rdesc-hint" id={hintId}>
        <span className="mono">{path}</span>
        {' · '}
        {pickerUnavailable
          ? 'the official schema could not be read, so what it allows here is unknown'
          : facts.allowed
            ? `one of ${facts.allowed.length} values the official schema allows`
            : facts.declaredType === null
              ? 'the official schema declares no type here, so what you type is stored exactly as typed'
              : `the official schema declares this a ${facts.declaredType}`}
        {holdsAValue(stored) ? ' · currently set' : ' · not set'}
        {overrideText}
      </span>
      {error && (
        <p className="rdesc-error" id={errorId}>
          {error}
        </p>
      )}
    </div>
  );
}

function ContributorsEditor({
  formId,
  rows,
  roles,
  readOnlyReason,
  error,
  disabled,
  onChange,
}: {
  formId: string;
  rows: readonly ContributorRow[];
  roles: readonly string[] | null;
  readOnlyReason: string | null;
  error?: string;
  disabled: boolean;
  onChange: (rows: ContributorRow[]) => void;
}) {
  const id = controlId(formId, RECORD_ATTRIBUTION_ADDRESS);
  const errorId = `${id}-error`;
  return (
    <fieldset className="rdesc-group" id={id}>
      <legend className="rdesc-legend">Contributors</legend>
      <p className="rdesc-hint">
        Who contributed to this record, and in what role. WHO recorded it is not stored:
        this application receives no verified user identity, so no name is attached to
        the confirmation rather than an unverified one being attached.
      </p>
      {readOnlyReason && (
        <p className="rdesc-readonly" role="note">
          {readOnlyReason}
        </p>
      )}
      {rows.length === 0 && !readOnlyReason && (
        <p className="rdesc-empty">No contributors are recorded on this record.</p>
      )}
      <ul className="rdesc-list">
        {rows.map((row, index) => (
          <li className="rdesc-list-row" key={`${index}-${row.name}-${row.role}`}>
            <label className="rdesc-label" htmlFor={`${id}-name-${index}`}>
              Name
            </label>
            <input
              id={`${id}-name-${index}`}
              className="rdesc-input"
              type="text"
              value={row.name}
              disabled={disabled || readOnlyReason !== null}
              onChange={(e) =>
                onChange(rows.map((r, i) => (i === index ? { ...r, name: e.target.value } : r)))
              }
            />
            <label className="rdesc-label" htmlFor={`${id}-role-${index}`}>
              Role
            </label>
            <select
              id={`${id}-role-${index}`}
              className="rdesc-input"
              value={row.role}
              disabled={disabled || readOnlyReason !== null}
              onChange={(e) =>
                onChange(rows.map((r, i) => (i === index ? { ...r, role: e.target.value } : r)))
              }
            >
              <option value="">— not set —</option>
              {(roles ?? []).map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
              {/* A STORED ROLE THIS BUILD DOES NOT OFFER IS STILL SHOWN, so selecting a
                  row does not silently change a value nobody edited. */}
              {row.role !== '' && !(roles ?? []).includes(row.role) && (
                <option value={row.role}>{row.role}</option>
              )}
            </select>
            <button
              type="button"
              className="btn btn-secondary rdesc-remove"
              disabled={disabled || readOnlyReason !== null}
              onClick={() => onChange(rows.filter((_r, i) => i !== index))}
            >
              Remove <span className="sr-only">contributor {index + 1}</span>
            </button>
          </li>
        ))}
      </ul>
      <button
        type="button"
        className="btn btn-secondary"
        disabled={disabled || readOnlyReason !== null}
        onClick={() => onChange([...rows, { name: '', role: '' }])}
      >
        Add a contributor
      </button>
      {error && (
        <p className="rdesc-error" id={errorId}>
          {error}
        </p>
      )}
    </fieldset>
  );
}

function TagsEditor({
  formId,
  rows,
  readOnlyReason,
  error,
  disabled,
  onChange,
}: {
  formId: string;
  rows: readonly string[];
  readOnlyReason: string | null;
  error?: string;
  disabled: boolean;
  onChange: (rows: string[]) => void;
}) {
  const id = controlId(formId, RECORD_TAGS_ADDRESS);
  const errorId = `${id}-error`;
  return (
    <fieldset className="rdesc-group" id={id}>
      <legend className="rdesc-legend">Tags</legend>
      <p className="rdesc-hint">
        Free-form grouping labels. A record may carry several; they are the record's
        own, and every run inherits them.
      </p>
      {readOnlyReason && (
        <p className="rdesc-readonly" role="note">
          {readOnlyReason}
        </p>
      )}
      {rows.length === 0 && !readOnlyReason && (
        <p className="rdesc-empty">No tags are recorded on this record.</p>
      )}
      <ul className="rdesc-list">
        {rows.map((tag, index) => (
          <li className="rdesc-list-row" key={`${index}-${tag}`}>
            <label className="rdesc-label" htmlFor={`${id}-${index}`}>
              Tag {index + 1}
            </label>
            <input
              id={`${id}-${index}`}
              className="rdesc-input"
              type="text"
              value={tag}
              disabled={disabled || readOnlyReason !== null}
              onChange={(e) =>
                onChange(rows.map((t, i) => (i === index ? e.target.value : t)))
              }
            />
            <button
              type="button"
              className="btn btn-secondary rdesc-remove"
              disabled={disabled || readOnlyReason !== null}
              onClick={() => onChange(rows.filter((_t, i) => i !== index))}
            >
              Remove <span className="sr-only">tag {index + 1}</span>
            </button>
          </li>
        ))}
      </ul>
      <button
        type="button"
        className="btn btn-secondary"
        disabled={disabled || readOnlyReason !== null}
        onClick={() => onChange([...rows, ''])}
      >
        Add a tag
      </button>
      {error && (
        <p className="rdesc-error" id={errorId}>
          {error}
        </p>
      )}
    </fieldset>
  );
}

/* ---- pure helpers -------------------------------------------------------- */

/** A DOM id for one key. Keys carry dots and colons, which are legal in an `id`. */
function controlId(formId: string, key: string): string {
  return `${formId}-${key.replace(/[.:]/g, '-')}`;
}

/** The human name of one key, for an error summary a person reads. */
export function labelFor(key: string): string {
  if (key === RECORD_ATTRIBUTION_ADDRESS) return 'Contributors';
  if (key === RECORD_TAGS_ADDRESS) return 'Tags';
  return RECORD_FIELDS.find((spec) => spec.path === key)?.label ?? key;
}

/** Whether the record currently holds something at this key — the `/answers` vs `/edit` split. */
export function blockHoldsSomething(key: string, current: unknown): boolean {
  if (!key.startsWith('block:')) return holdsAValue(current);
  // THE SEEDED EMPTY BLOCK IS NOT A STORED VALUE, and this mirrors the server's own
  // predicate rather than guessing at it: `POST /api/experiments` seeds
  // `attribution: {"contributors": []}`, so treating key presence as "answered" would
  // route the FIRST contributor to the correction operation and earn a 422.
  return !carriesNothing(current);
}

function carriesNothing(value: unknown): boolean {
  if (value === null || value === undefined) return true;
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === 'string') return value.length === 0;
  if (typeof value === 'object') {
    return Object.values(value as Record<string, unknown>).every(carriesNothing);
  }
  return false;
}

function toLoaded(
  version: string,
  draft: ApiDraftResponse,
  schema: JsonSchemaNode | null,
  runs: ApiRunsResponse | null,
): Loaded {
  const stored: Record<string, unknown> = {};
  for (const group of draft.groups ?? []) {
    for (const field of group.fields ?? []) stored[field.path] = field.value;
  }
  return {
    version,
    stored,
    blocks: draft.record_blocks ?? {},
    schema,
    overrides: runs === null ? null : summariseOverrides(runs),
  };
}

/**
 * Which record-level addresses the runs on THIS PAGE have diverged from.
 *
 * IT COUNTS WHAT IT EXAMINED AND SAYS SO. `matched` is the server's own count of runs
 * holding an override; `examined` is how many this page carried. The panel renders
 * both, because a per-address count taken from a truncated page and shown as though it
 * described the record would be an understatement — and understating how many runs
 * have diverged is the direction that misleads.
 */
export function summariseOverrides(runs: ApiRunsResponse): OverrideSummary {
  const byAddress: Record<string, number> = {};
  for (const run of runs.runs ?? []) {
    for (const [address, resolution] of Object.entries(run.inherited ?? {})) {
      if (resolution?.state === 'overridden') {
        byAddress[address] = (byAddress[address] ?? 0) + 1;
      }
    }
  }
  return {
    byAddress,
    matched: runs.matched ?? 0,
    examined: runs.returned ?? (runs.runs ?? []).length,
    total: runs.total ?? 0,
  };
}

function initialText(loaded: Loaded): Record<string, string> {
  const out: Record<string, string> = {};
  for (const spec of RECORD_FIELDS) {
    const value = loaded.stored[spec.path];
    out[spec.path] = value === null || value === undefined ? '' : String(value);
  }
  return out;
}

/**
 * What this save would send, and what it refuses to send.
 *
 * A BLANK IS NEVER A CHANGE — see `parseRecordField`. A value equal to the stored one
 * is never a change either, so a save re-sends nothing the record already holds and a
 * reader is never told "1 unsaved change" about a value they have not altered.
 */
export function collectChanges(input: {
  loaded: Loaded;
  facts: Record<string, RecordFieldFacts>;
  text: Record<string, string>;
  contribs: readonly ContributorRow[];
  tags: readonly string[];
  contributorsEditable: boolean;
  tagsEditable: boolean;
  storedContributors: readonly ContributorRow[];
  storedTags: readonly string[];
}): { values: Record<string, unknown>; errors: Record<string, string> } {
  const values: Record<string, unknown> = {};
  const errors: Record<string, string> = {};
  for (const spec of RECORD_FIELDS) {
    const parsed = parseRecordField(
      input.facts[spec.path] ?? { declaredType: null, allowed: null },
      input.text[spec.path] ?? '',
    );
    if (!parsed.ok) {
      errors[spec.path] = parsed.error;
      continue;
    }
    if (parsed.value === null) continue; // blank: not a change and not a delete
    if (parsed.value === input.loaded.stored[spec.path]) continue;
    values[spec.path] = parsed.value;
  }

  if (input.contributorsEditable) {
    const rows = input.contribs.map((r) => ({ name: r.name.trim(), role: r.role.trim() }));
    const incomplete = rows.some((r) => r.name === '' || r.role === '');
    if (incomplete) {
      // REFUSED LOCALLY, AND SAID SO. The official schema requires both, and a
      // contributor missing either cannot be keyed to its evidence — so it would be
      // stored and then refused at the export gate, which is a worse place to find out.
      errors[RECORD_ATTRIBUTION_ADDRESS] =
        'Every contributor needs both a name and a role. Nothing was sent.';
    } else if (!sameContributors(rows, input.storedContributors)) {
      values[RECORD_ATTRIBUTION_ADDRESS] = mergeAttribution(
        input.loaded.blocks[RECORD_ATTRIBUTION_ADDRESS],
        rows,
      );
    }
  }

  if (input.tagsEditable) {
    const rows = input.tags.map((t) => t.trim()).filter((t) => t !== '');
    if (rows.length !== new Set(rows).size) {
      errors[RECORD_TAGS_ADDRESS] =
        'The official schema requires tags to be unique. Nothing was sent.';
    } else if (rows.join(' ') !== [...input.storedTags].join(' ')) {
      values[RECORD_TAGS_ADDRESS] = rows;
    }
  }

  return { values, errors };
}

function sameContributors(
  a: readonly ContributorRow[],
  b: readonly ContributorRow[],
): boolean {
  if (a.length !== b.length) return false;
  return a.every((row, i) => row.name === b[i].name && row.role === b[i].role);
}

/**
 * The attribution payload to send — the edited rows, with everything else PRESERVED.
 *
 * A BLOCK WRITE REPLACES THE WHOLE BLOCK, so building `{contributors: rows}` from
 * scratch would delete a contributor's `affiliation`, `orcid`, `email` and `notes` —
 * every optional property the official schema declares — and any other key the block
 * carries. Each edited row therefore keeps the stored object it came from and updates
 * only `name` and `role`; a row the reader added is a fresh `{name, role}` and nothing
 * is invented to fill it.
 */
export function mergeAttribution(stored: unknown, rows: readonly ContributorRow[]): unknown {
  const base =
    typeof stored === 'object' && stored !== null && !Array.isArray(stored)
      ? (stored as Record<string, unknown>)
      : {};
  const previous = Array.isArray(base.contributors) ? (base.contributors as unknown[]) : [];
  const contributors = rows.map((row, index) => {
    const prior = previous[index];
    const carried =
      typeof prior === 'object' && prior !== null && !Array.isArray(prior)
        ? (prior as Record<string, unknown>)
        : {};
    return { ...carried, name: row.name, role: row.role };
  });
  return { ...base, contributors };
}

/**
 * The one sentence about runs that have diverged, with its own limits attached.
 *
 * NEVER "no run overrides these", which this cannot know from a bounded page. The
 * three states it can honestly report are: the runs list could not be read; the server
 * says no run holds an override; and N runs do, of which this page examined M.
 */
export function overrideLead(overrides: OverrideSummary | null): string {
  if (overrides === null) {
    return (
      "This record's runs could not be read, so this screen cannot say whether any run " +
      'has recorded its own value in place of one of these. Saving here still changes ' +
      'the record, and a run that has diverged still keeps its own value.'
    );
  }
  if (overrides.matched === 0) {
    return `No run has recorded its own value in place of any of these (${overrides.total} run${overrides.total === 1 ? '' : 's'}).`;
  }
  const scope =
    overrides.examined < overrides.matched
      ? ` This screen examined ${overrides.examined} of them, so the per-field counts below are a floor, not a total.`
      : '';
  return (
    `${overrides.matched} of ${overrides.total} run${overrides.total === 1 ? '' : 's'} ` +
    'have recorded their own value in place of a record-level one. Those runs keep ' +
    `their value at the addresses they overrode; the rest follow this record.${scope}`
  );
}

/** The per-row note about runs that overrode THIS address, or nothing to say. */
export function overrideNote(
  overrides: OverrideSummary | null,
  address: string,
): string | null {
  if (overrides === null) return null;
  const count = overrides.byAddress[address] ?? 0;
  if (count === 0) return null;
  const floor = overrides.examined < overrides.matched ? ' or more' : '';
  return ` · ${count}${floor} run${count === 1 && floor === '' ? '' : 's'} override this`;
}

/** The status line. Every variant states what DID happen, never only what failed. */
function statusSentence(save: SaveState): string {
  switch (save.kind) {
    case 'saving':
      return 'Saving…';
    case 'saved':
      return `Saved ${save.count} value${save.count === 1 ? '' : 's'} to this record.`;
    case 'stale':
      return 'Nothing further was saved — this record changed somewhere else.';
    case 'failed':
      return save.landed.length > 0
        ? `${save.landed.length} value${save.landed.length === 1 ? '' : 's'} were saved before this failed: ${save.landed.map(labelFor).join(', ')}.`
        : save.message;
    default:
      return '';
  }
}

/**
 * The server's own words, per key, out of a typed refusal.
 *
 * IT READS THE SERVER'S REFUSAL RATHER THAN RESTATING IT. `not_an_allowed_value`
 * carries `allowed` per field, `invalid_field_value` carries `expected_types` per
 * field, and `invalid_block_payload` names one `address` and may carry the draft
 * validator's own `findings`. Anything this cannot read yields no per-key message and
 * falls through to the generic notice, which claims less.
 */
export function perKeyMessages(err: unknown): Record<string, string> {
  const body = (err as { body?: unknown })?.body;
  if (typeof body !== 'object' || body === null) return {};
  const record = body as Record<string, unknown>;
  const out: Record<string, string> = {};
  const keys = Array.isArray(record.keys)
    ? record.keys.filter((k): k is string => typeof k === 'string')
    : [];
  if (record.error === 'not_an_allowed_value') {
    const allowed = (record.allowed ?? {}) as Record<string, unknown>;
    for (const key of keys) {
      const values = allowed[key];
      out[key] = Array.isArray(values)
        ? `The official schema allows only: ${values.join(', ')}.`
        : 'The official schema does not allow that value.';
    }
    return out;
  }
  if (record.error === 'invalid_field_value') {
    const expected = (record.expected_types ?? {}) as Record<string, unknown>;
    for (const key of keys) {
      const type = expected[key];
      out[key] =
        typeof type === 'string'
          ? `The official schema declares this a ${type}, and what was sent is not one.`
          : 'This value cannot be stored — it is too large, too deeply nested, or not representable in JSON.';
    }
    return out;
  }
  if (record.error === 'invalid_block_payload' && typeof record.address === 'string') {
    const findings = Array.isArray(record.findings)
      ? record.findings.filter((f): f is string => typeof f === 'string')
      : [];
    out[record.address] =
      findings.length > 0
        ? findings.join(' ')
        : typeof record.message === 'string'
          ? record.message
          : 'This block was refused.';
    return out;
  }
  if (record.error === 'already_answered' || record.error === 'not_yet_answered') {
    for (const key of keys) {
      out[key] =
        record.error === 'already_answered'
          ? 'This value changed elsewhere while you were editing. Re-read the record and try again.'
          : 'This record no longer holds a value here. Re-read the record and try again.';
    }
    return out;
  }
  return out;
}
