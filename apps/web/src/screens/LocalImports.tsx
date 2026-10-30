import './screens.css';
import './local-imports.css';
import { useCallback, useEffect, useId, useMemo, useRef, useState, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { BackendDown, LoadingPanel } from '../components/FetchStates';
import { Copy } from '../components/icons';
import { LABELS } from '../lib/labels';
import { api, type ApiError } from '../lib/api';
import { useFetch } from '../lib/useFetch';
import { statusOf } from '../lib/mutationErrors';
import { LOCAL_BUNDLE_PARAM, ROUTES } from '../lib/routes';
import {
  ABSORBER_EDGES,
  CHECK_STATUS_LABEL,
  KIND_LABEL,
  LOCAL_IMPORTS_COPY as COPY,
  LOCAL_LIMITS,
  answerText,
  clampText,
  groupBySuggestion,
  ianaZones,
  localImportsBuildEnabled,
  localReasonCodeOf,
  localReasonOf,
  perGroupScopes,
  regroupCommand,
  rememberName,
  rememberedName,
  sectionQuestions,
  shownValue,
  type ApiLocalAnswerPreview,
  type ApiLocalAnswerRecorded,
  type ApiLocalQuestions,
  type LocalAnswerInput,
  type LocalAthenaSelection,
  type LocalBeamlineReading,
  type LocalBundleCheck,
  type LocalBundleSummary,
  type LocalMergeCandidate,
  type LocalOwnSuggestion,
  type LocalScope,
  type LocalQuestion,
  type LocalSuggestion,
  type LocalValueRule,
} from '../lib/localImports';

/**
 * LOCAL IMPORTS — the import progress of every bundle in the folder this server was started
 * with, and one bundle's questions (`?bundle=<folder name>`).
 *
 * WHAT THIS SCREEN WILL NOT DO, each pinned by a test:
 *
 *   1. IT NEVER CLAIMS AN ANSWER IT HAS NOT READ BACK. After a write it reads the questions
 *      again from the bundle; nothing is marked answered on the strength of the click.
 *   2. A SUGGESTION IS NEVER SHOWN AS AN ANSWER. Every one is labelled "Suggested — not
 *      confirmed" with who made it; a hint (a folder name, a related reading) cannot be
 *      accepted at all.
 *   3. AN ANSWER FOR MORE THAN ONE RUN NEVER WRITES BLIND. "Same for all", a bulk accept, and
 *      accepting a value for one group first ask the server what the answer would be written to
 *      (a dry run that writes nothing) and list every group and run, marking the runs whose files
 *      have no reading; only "Write these answers" writes, against the version that list was read at.
 *   4. IT SENDS NOTHING ANYWHERE. Every request goes to the server on this computer, which
 *      writes the bundle with the command line's own code.
 */
export function LocalImports() {
  const [params] = useSearchParams();
  const bundle = params.get(LOCAL_BUNDLE_PARAM);
  const enabled = localImportsBuildEnabled();
  return (
    <AppShell
      variant="full"
      topBar={<TopBar variant="home" />}
      sidebar={<LeftNav active="localImports" />}
      mainPad="pad"
      width="wide"
    >
      <div className="li-screen">
        <header className="li-head">
          <h1 className="page-title">{LABELS.navLocalImports}</h1>
          <p className="li-lead">{COPY.lead}</p>
          <p className="li-boundary">{COPY.boundary}</p>
        </header>
        {!enabled ? (
          <div className="li-notice" role="note">
            <p>{COPY.notInThisBuild}</p>
          </div>
        ) : bundle ? (
          <BundleQuestions name={bundle} />
        ) : (
          <Overview />
        )}
      </div>
    </AppShell>
  );
}

// --- shared bits -------------------------------------------------------------------------------

function NotServed() {
  return (
    <div className="li-notice" role="note">
      <p>{COPY.notOnThisServer}</p>
      <p>{COPY.howToStart}</p>
      <pre className="li-command">{COPY.startCommand}</pre>
    </div>
  );
}

function CheckChip({ check }: { check: LocalBundleCheck }) {
  return (
    <span className="li-chip" title={`${check.status}: ${check.statement}`} data-status={check.status}>
      <span className="sr-only">Bundle check: </span>
      {CHECK_STATUS_LABEL[check.status] ?? check.status}
    </span>
  );
}

function beamlineText(readings: LocalBeamlineReading[] | undefined): string {
  if (!readings || readings.length === 0) return 'Not recorded in this bundle';
  return readings.map((r) => `${shownValue(r.value)} (${r.basis ?? 'unknown basis'})`).join('; ');
}

function namesText(names: string[], total?: number, limit = 6): string {
  if (names.length === 0) return '—';
  const shown = names.slice(0, limit).join(', ');
  const more = (total ?? names.length) - Math.min(limit, names.length);
  return more > 0 ? `${shown}, and ${more} more` : shown;
}

/**
 * A read that failed. A refusal (any 4xx) or a page that is not ISAAC's is said in the server's own
 * words (or as "not this server") — never as a sign-in problem: this page runs only on this
 * computer, where there is no sign-in. A server that is down or broken gets the shared down state.
 */
function LocalFailure({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  const refused = error.htmlIntercept || (error.status !== undefined && error.status >= 400 && error.status < 500);
  if (!refused) return <BackendDown error={error} onRetry={onRetry} />;
  const reason = error.htmlIntercept ? COPY.notIsaac : localReasonOf(error);
  return (
    <div className="li-notice" role="alert" data-testid="li-refused">
      <p>
        {COPY.failedToRead}
        {error.status ? ` (HTTP ${error.status})` : ''}
      </p>
      {reason && <p>{reason}</p>}
      {onRetry && (
        <p className="li-actions">
          <button type="button" className="btn btn-secondary" onClick={onRetry}>
            {COPY.retry}
          </button>
        </p>
      )}
    </div>
  );
}

/** A command the person runs in the command line, with a copy button. */
function CommandBlock({ command, label }: { command: string; label: string }) {
  const [said, setSaid] = useState('');
  async function copy() {
    try {
      await navigator.clipboard.writeText(command);
      setSaid(COPY.copied);
    } catch {
      setSaid(COPY.copyRefused);
    }
  }
  return (
    <div className="li-command-block" role="group" aria-label={label}>
      <pre className="li-command">{command}</pre>
      <p className="li-actions">
        <button type="button" className="btn btn-secondary" onClick={copy}>
          <Copy size={14} strokeWidth={2} aria-hidden="true" /> {COPY.copyCommand}
          <span className="sr-only">: {command}</span>
        </button>
        <span className="li-meta" role="status">
          {said}
        </span>
      </p>
    </div>
  );
}

// --- the overview --------------------------------------------------------------------------------

function Overview() {
  const list = useFetch(() => api.listLocalBundles(), []);
  if (list.status === 'loading') return <LoadingPanel label="Reading the local bundles…" />;
  if (list.status === 'error') {
    if (list.error.status === 404) return <NotServed />;
    return <LocalFailure error={list.error} onRetry={list.reload} />;
  }
  const { bundles, not_bundles: notBundles, directory_name: dir } = list.data;
  return (
    <section className="li-panel" aria-labelledby="li-overview-title">
      <h2 id="li-overview-title" className="li-h2">
        {COPY.overviewTitle}
      </h2>
      <p className="li-meta">
        {bundles.length} bundle(s) in the folder {dir}
        {notBundles ? `; ${notBundles} other entr${notBundles === 1 ? 'y is' : 'ies are'} not a bundle` : ''}.{' '}
        {list.data.statement}
      </p>
      {bundles.length === 0 ? (
        <p className="li-note">{COPY.noBundles}</p>
      ) : (
        <ul className="li-list">
          {bundles.map((b) => (
            <BundleCard key={b.name} bundle={b} />
          ))}
        </ul>
      )}
    </section>
  );
}

function BundleCard({ bundle }: { bundle: LocalBundleSummary }) {
  const titleId = useId();
  return (
    <li className="li-card" aria-labelledby={titleId}>
      <div className="li-card-head">
        <h3 id={titleId} className="li-h3">
          {bundle.name}
        </h3>
        <CheckChip check={bundle.check} />
      </div>
      <dl className="li-dl">
        <dt>Beamtime (imported folder)</dt>
        <dd>{bundle.source_label ?? '—'}</dd>
        <dt>Beamline</dt>
        <dd>{beamlineText(bundle.beamline)}</dd>
        <dt>Bundle format</dt>
        <dd>{bundle.format_version ?? '—'}</dd>
        <dt>Runs</dt>
        <dd>{bundle.counts?.runs ?? '—'}</dd>
        <dt>Record groups proposed</dt>
        <dd>{bundle.record_groups ?? 0}</dd>
        <dt>Answers recorded</dt>
        <dd>{bundle.scientist_decisions ?? 0}</dd>
      </dl>
      {bundle.check.status !== 'VALID' && <p className="li-note">{bundle.check.statement}</p>}
      <ProgressBlock name={bundle.name} />
      <p className="li-actions">
        <Link className="btn btn-primary" to={ROUTES.localImportBundle(bundle.name)}>
          {COPY.openQuestions}
          <span className="sr-only"> for {bundle.name}</span>
        </Link>
      </p>
    </li>
  );
}

function ProgressBlock({ name }: { name: string }) {
  const progress = useFetch(() => api.getLocalBundleProgress(name), [name]);
  if (progress.status === 'loading') return <p className="li-meta">Reading progress…</p>;
  if (progress.status === 'error') {
    return <p className="li-note">Progress could not be read: {localReasonOf(progress.error) ?? progress.error.message}</p>;
  }
  const p = progress.data.progress;
  return (
    <div className="li-progress">
      <dl className="li-dl">
        <dt>Questions open</dt>
        <dd>
          {p.questions && typeof p.questions.total === 'number'
            ? `${p.questions.total} (${p.questions.blocking ?? 0} blocking export, ${p.questions.optional ?? 0} optional)`
            : 'Not available for this bundle'}
        </dd>
        <dt>Record groups</dt>
        <dd>
          {p.record_groups.total
            ? Object.entries(p.record_groups.by_status)
                .map(([s, n]) => `${n} ${s.replace(/_/g, ' ')}`)
                .join(', ')
            : 'None proposed yet'}
        </dd>
        <dt>Processing results</dt>
        <dd>
          {p.processing_results.total
            ? Object.entries(p.processing_results.by_state)
                .map(([s, n]) => `${n} ${s.replace(/_/g, ' ')}`)
                .join(', ')
            : 'None yet'}
        </dd>
      </dl>
      {p.minimum_for_one_group && (
        <p className="li-note">
          {COPY.nearestRecord}: group {p.minimum_for_one_group.group_id} needs {p.minimum_for_one_group.blocking_questions}{' '}
          blocking answer(s), plus: {p.minimum_for_one_group.plus_decisions.join('; ')}.
          {p.minimum_for_one_group.blocked ? ` ${p.minimum_for_one_group.blocked}.` : ''}
        </p>
      )}
      {p.blocks_export.length > 0 && (
        <>
          <h4 className="li-h4">{COPY.blocksExport}</h4>
          <ul className="li-bullets">
            {p.blocks_export.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </>
      )}
      {p.last_validation.reports.length > 0 && (
        <details className="li-details">
          <summary>
            {COPY.lastValidation} ({p.last_validation.reports.length} group(s))
          </summary>
          <p className="li-meta">{p.last_validation.statement}</p>
          <ul className="li-bullets">
            {p.last_validation.reports.map((r) => (
              <li key={r.group_id}>
                {r.group_id}: {r.verdict ?? 'no verdict'} (written {r.written_utc}
                {r.older_than_bundle ? '; older than the bundle, so answers given since are not reflected' : ''})
                {r.missing_required.length ? ` — missing: ${r.missing_required.join(', ')}` : ''}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

// --- one bundle's questions -------------------------------------------------------------------

/** Where focus goes once the questions have been read again after a write. */
interface FocusPlan {
  /** The card that wrote (a question id, or a capture decision's id). */
  id: string;
  /** Every card's id, in the order shown, when it wrote. */
  order: string[];
}

interface WriteHandlers {
  name: string;
  by: string;
  version: string;
  /** No name typed: the name field is focused and its error said (again, on every attempt). */
  needName: () => void;
  /** A write the server recorded: say it, adopt the version it returned, read the questions again. */
  onWritten: (id: string, message: string, versions: { sentWith: string; now?: string }) => void;
  /** Read the questions again after a refusal (412, or a question answered elsewhere). */
  onReread: (id: string, message: string | null) => void;
}

function BundleQuestions({ name }: { name: string }) {
  const [blockingOnly, setBlockingOnly] = useState(false);
  const [kind, setKind] = useState('');
  const [offset, setOffset] = useState(0);
  const [by, setByState] = useState(rememberedName);
  const [nameError, setNameError] = useState(0);
  const [announcement, setAnnouncement] = useState('');
  const questionsHeading = useRef<HTMLHeadingElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const sectionRef = useRef<HTMLElement>(null);
  const questions = useFetch(
    () => api.getLocalBundleQuestions(name, { blockingOnly, kind: kind || undefined, offset }),
    [name, blockingOnly, kind, offset],
  );
  const byId = useId();

  const setBy = (v: string) => {
    setByState(v);
    rememberName(v);
    if (v.trim()) setNameError(0);
  };
  const needName = useCallback(() => {
    setNameError((n) => n + 1);
    nameRef.current?.focus();
  }, []);

  /*
   * THE VERSION A WRITE RETURNED IS USED AT ONCE. Every write answers with the bundle's new
   * `bundle_version`; waiting for the background read to bring it meant a second quick answer was
   * sent with the old one and refused (412). The version a write was SENT with is remembered as
   * superseded, so a read that arrives with it (older than the write) cannot put it back.
   */
  const [versions, setVersions] = useState<{ superseded: string[]; adopted: string | null }>({
    superseded: [],
    adopted: null,
  });
  const shownData = questions.status === 'data' ? questions.data : null;
  const dataVersion = shownData?.bundle.bundle_version ?? '';
  const version =
    versions.adopted !== null && versions.superseded.includes(dataVersion) ? versions.adopted : dataVersion;

  const order = useMemo(() => {
    if (shownData === null) return [];
    const d = shownData;
    return [
      ...sectionQuestions(d.questions).flatMap((sec) => sec.questions.map((q) => q.question_id)),
      ...d.capture.merge_candidates.map((m) => m.merge_candidate_id),
      ...d.capture.athena_selections.map((a) => a.processing_id),
    ];
  }, [shownData]);
  const orderRef = useRef(order);
  orderRef.current = order;

  /*
   * AFTER A WRITE THE QUESTIONS ARE READ AGAIN SILENTLY — the cards stay mounted, so what a person
   * typed survives — and "Refreshed" is said only once that read has ARRIVED; a read that fails
   * says so instead. Messages from several quick writes are all said (none replaces another), and
   * only the LATEST read speaks, so an earlier one cannot leave "Reading…" on the page.
   */
  const { reloadSilent } = questions;
  const pendingMessages = useRef<string[]>([]);
  const pendingPlan = useRef<FocusPlan | null>(null);
  const ticket = useRef(0);
  const [focusPlan, setFocusPlan] = useState<FocusPlan | null>(null);
  const reread = useCallback(
    (message: string | null, plan: FocusPlan | null) => {
      if (message) pendingMessages.current.push(message);
      if (plan) pendingPlan.current = plan;
      const mine = ++ticket.current;
      setAnnouncement([...pendingMessages.current, COPY.refreshing].join(' '));
      void reloadSilent().then((outcome) => {
        if (mine !== ticket.current) return;
        const said = pendingMessages.current;
        pendingMessages.current = [];
        const next = pendingPlan.current;
        pendingPlan.current = null;
        if (outcome === 'applied') {
          setAnnouncement([...said, COPY.refreshed].join(' '));
          if (next) setFocusPlan(next);
        } else if (outcome === 'failed') {
          setAnnouncement([...said, COPY.refreshFailed].join(' '));
        } else {
          setAnnouncement(said.join(' '));
        }
      });
    },
    [reloadSilent],
  );
  const onWritten = useCallback(
    (id: string, message: string, v: { sentWith: string; now?: string }) => {
      const now = v.now;
      if (now && now !== v.sentWith) {
        setVersions((cur) => ({ superseded: [...cur.superseded, v.sentWith].slice(-50), adopted: now }));
      }
      reread(message, { id, order: orderRef.current });
    },
    [reread],
  );
  const onReread = useCallback(
    (id: string, message: string | null) => reread(message, message ? { id, order: orderRef.current } : null),
    [reread],
  );

  /*
   * FOCUS KEEPS THE PERSON'S PLACE. Once the questions have been read again: the card that wrote, if
   * it is still asked (its "Answered" line); else the next open question after it (or the one before
   * it, at the end of the list); only when none is left, the Questions heading.
   */
  useEffect(() => {
    if (!focusPlan || shownData === null) return;
    setFocusPlan(null);
    const root = sectionRef.current;
    if (!root) return;
    const cards = new Map(
      [...root.querySelectorAll<HTMLElement>('[data-card-id]')].map((el) => [el.dataset.cardId ?? '', el]),
    );
    const own = cards.get(focusPlan.id);
    if (own) {
      (own.querySelector<HTMLElement>('[data-li-recorded]') ?? own.querySelector<HTMLElement>('[data-li-title]'))?.focus();
      return;
    }
    const at = focusPlan.order.indexOf(focusPlan.id);
    const candidates = at < 0 ? [] : [...focusPlan.order.slice(at + 1), ...focusPlan.order.slice(0, at).reverse()];
    for (const id of candidates) {
      const el = cards.get(id)?.querySelector<HTMLElement>('[data-li-title]');
      if (el) {
        el.focus();
        return;
      }
    }
    questionsHeading.current?.focus();
  }, [focusPlan, shownData]);

  /* Previous / Next questions: once the new page has arrived, focus its heading. */
  const pageFocus = useRef(false);
  const onPage = useCallback((next: number) => {
    pageFocus.current = true;
    setOffset(next);
  }, []);
  useEffect(() => {
    if (pageFocus.current && shownData !== null) {
      pageFocus.current = false;
      questionsHeading.current?.focus();
    }
  }, [shownData]);

  const hasData = shownData !== null;
  return (
    <section
      className="li-panel"
      ref={sectionRef}
      aria-labelledby={hasData ? 'li-questions-title' : undefined}
      aria-label={hasData ? undefined : COPY.questionsTitle}
    >
      <p className="li-meta">
        <Link to={ROUTES.localImports}>{COPY.backToAll}</Link>
      </p>
      <p className="sr-only" role="status" aria-live="polite">
        {announcement}
      </p>
      {announcement && (
        <div className="li-notice" data-testid="li-announcement">
          <p>{announcement}</p>
        </div>
      )}
      <div className="li-field li-name">
        <label htmlFor={byId}>{COPY.yourName}</label>
        <input
          id={byId}
          ref={nameRef}
          className="input"
          value={by}
          autoComplete="name"
          maxLength={LOCAL_LIMITS.nameMax}
          onChange={(e) => setBy(e.target.value)}
          aria-invalid={nameError ? true : undefined}
          aria-describedby={`${byId}-hint${nameError ? ` ${byId}-err` : ''}`}
        />
        <p id={`${byId}-hint`} className="li-hint">
          {COPY.yourNameHint}
        </p>
        {nameError > 0 && (
          // keyed by the attempt, so a repeat click is announced again
          <p key={nameError} id={`${byId}-err`} className="li-error" role="alert" data-testid="li-name-error">
            {COPY.nameNeeded}
          </p>
        )}
      </div>
      <div className="li-filters" role="group" aria-label="Filter the questions">
        <label className="li-check">
          <input
            type="checkbox"
            checked={blockingOnly}
            onChange={(e) => {
              setBlockingOnly(e.target.checked);
              setOffset(0);
            }}
          />
          Only questions that block export
        </label>
        <label className="li-inline">
          Question type{' '}
          <select
            className="input li-select"
            value={kind}
            onChange={(e) => {
              setKind(e.target.value);
              setOffset(0);
            }}
          >
            <option value="">All types</option>
            {Object.entries(KIND_LABEL).map(([k, label]) => (
              <option key={k} value={k}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {questions.status === 'loading' && <LoadingPanel label="Reading the questions…" />}
      {questions.status === 'error' &&
        (questions.error.status === 404 && localReasonCodeOf(questions.error) !== 'bundle_not_found' ? (
          <NotServed />
        ) : questions.error.status === 404 ? (
          <div className="li-notice" role="alert">
            <p>{localReasonOf(questions.error) ?? 'No bundle by that name.'}</p>
          </div>
        ) : (
          <LocalFailure error={questions.error} onRetry={questions.reload} />
        ))}
      {questions.status === 'data' && (
        <QuestionsBody
          data={questions.data}
          headingRef={questionsHeading}
          handlers={{ name, by, version, needName, onWritten, onReread }}
          onPage={onPage}
        />
      )}
    </section>
  );
}

function QuestionsBody({
  data,
  headingRef,
  handlers,
  onPage,
}: {
  data: ApiLocalQuestions;
  headingRef: React.RefObject<HTMLHeadingElement>;
  handlers: WriteHandlers;
  onPage: (offset: number) => void;
}) {
  const sections = useMemo(() => sectionQuestions(data.questions), [data.questions]);
  const b = data.bundle;
  return (
    <>
      <div className="li-card li-bundle-head">
        <dl className="li-dl">
          <dt>Folder</dt>
          <dd>{b.name}</dd>
          <dt>Beamtime (imported folder)</dt>
          <dd>{b.source_label ?? '—'}</dd>
          <dt>Beamline</dt>
          <dd>{beamlineText(b.beamline)}</dd>
          <dt>Export rules used</dt>
          <dd title={data.blocking_basis.source}>ISAAC record schema ({data.blocking_basis.schema})</dd>
        </dl>
        <p className="li-meta">{data.statement}</p>
        {data.exposures_recorded > 0 && (
          <p className="li-meta">
            This page noted in the bundle that these suggestions were shown to you ({data.exposures_recorded}), as the
            command line does, so that a later independent check knows you had seen them.
          </p>
        )}
      </div>
      <h2 id="li-questions-title" className="li-h2" tabIndex={-1} ref={headingRef}>
        {COPY.questionsTitle}{' '}
        <span className="li-count">
          ({data.counts.blocking} blocking export, {data.counts.conflicts_affecting_a_record} conflicts affecting a
          record, {data.counts.optional} optional)
        </span>
      </h2>
      {data.minimum_for_one_group && (
        <p className="li-note">
          {COPY.nearestRecord}: group {data.minimum_for_one_group.group_id} needs{' '}
          {data.minimum_for_one_group.blocking_questions} blocking answer(s), plus{' '}
          {data.minimum_for_one_group.plus_decisions.join('; ')}.
        </p>
      )}
      {data.total === 0 && <p className="li-note">No open questions match.</p>}
      {sections.map((s) => (
        <section key={s.id} className="li-section" aria-labelledby={`li-sec-${s.id}`}>
          <h3 id={`li-sec-${s.id}`} className="li-h3">
            {s.title} <span className="li-count">({s.questions.length})</span>
          </h3>
          {s.id === 'settles-many' && <p className="li-note">{COPY.settlesManyLead}</p>}
          <ol className="li-list">
            {s.questions.map((q) => (
              <QuestionCard key={q.question_id} q={q} handlers={handlers} />
            ))}
          </ol>
        </section>
      ))}
      {(data.omitted_before > 0 || data.omitted_after > 0) && (
        <p className="li-actions">
          <span className="li-meta">
            Questions {data.offset + 1}–{data.offset + data.returned} of {data.total}.
          </span>
          {data.omitted_before > 0 && (
            <button type="button" className="btn btn-secondary" onClick={() => onPage(Math.max(0, data.offset - data.limit))}>
              Previous questions
            </button>
          )}
          {data.omitted_after > 0 && (
            <button type="button" className="btn btn-secondary" onClick={() => onPage(data.offset + data.limit)}>
              Next questions
            </button>
          )}
        </p>
      )}
      <CaptureSection data={data} handlers={handlers} />
    </>
  );
}

// --- one question -----------------------------------------------------------------------------

function SuggestionItem({ s }: { s: LocalSuggestion }) {
  return (
    <div className="li-suggestion">
      <p className="li-suggestion-head">
        {s.acceptable && <span className="li-chip">{COPY.suggestedNotConfirmed}</span>}
        <span>
          {s.who_label}
          {s.model_id ? ` (${s.model_id})` : ''}
        </span>
      </p>
      <p className="li-value">
        <span className="sr-only">Value: </span>
        <code>{shownValue(s.value)}</code>
        {s.targets && s.targets > 1 ? <span className="li-meta"> — for {s.targets} of the values asked about</span> : null}
      </p>
      <dl className="li-dl li-dl-tight">
        <dt>File</dt>
        <dd>{s.relative_path ?? 'not recorded'}</dd>
        <dt>Where in the file</dt>
        <dd>{s.locator ?? 'not recorded'}</dd>
        {s.run_names && s.run_names.length > 0 && (
          <>
            <dt>Run</dt>
            <dd>{namesText(s.run_names)}</dd>
          </>
        )}
      </dl>
      {s.quote && (
        <blockquote className="li-quote">
          <span className="sr-only">Quoted from the file: </span>
          {s.quote}
        </blockquote>
      )}
      {s.note && <p className="li-hint">{s.note}</p>}
    </div>
  );
}

/** One scope's own suggestion(s), each with who made it, its file and its quote. Never confirmed. */
function OwnSuggestions({ own, total }: { own: LocalOwnSuggestion[]; total?: number }) {
  if (own.length === 0) return <p className="li-meta">{COPY.groupNoSuggestion}</p>;
  return (
    <ul className="li-choices">
      {own.map((o, i) => (
        <li key={i} className="li-own">
          <span className="li-chip">{o.from_own_files === true ? COPY.groupOwnSuggestion : COPY.groupOtherSuggestion}</span>{' '}
          <code>{shownValue(o.value)}</code>
          {o.targets > 1 ? ` (for ${o.targets} runs)` : ''} — {o.who_label}
          {o.model_id ? ` (${o.model_id})` : ''}
          {o.relative_path || o.locator ? `, ${o.relative_path ?? 'file not recorded'} @ ${o.locator ?? 'no locator'}` : ''}
          <span className="li-provenance">{o.provenance_label}</span>
          {o.quote && (
            <blockquote className="li-quote">
              <span className="sr-only">Quoted from the file: </span>
              {o.quote}
            </blockquote>
          )}
        </li>
      ))}
      {total !== undefined && total > own.length && (
        <li className="li-meta">
          and {total - own.length} more suggestion(s) for this group
        </li>
      )}
    </ul>
  );
}

function ValueInput({
  id,
  rule,
  value,
  onChange,
  label,
}: {
  id: string;
  rule: LocalValueRule | null;
  value: string;
  onChange: (v: string) => void;
  label: string;
}) {
  const allowed = rule?.allowed ?? null;
  return (
    <div className="li-field">
      <label htmlFor={id}>
        {label}
        {rule?.unit ? ` (in ${rule.unit})` : ''}
      </label>
      {allowed ? (
        <select id={id} className="input li-select" value={value} onChange={(e) => onChange(e.target.value)}>
          <option value="">Choose one…</option>
          {allowed.map((a) => (
            <option key={answerText(a)} value={answerText(a)}>
              {shownValue(a)}
            </option>
          ))}
        </select>
      ) : (
        <span className="li-with-unit">
          <input
            id={id}
            className="input"
            value={value}
            maxLength={LOCAL_LIMITS.valueMax}
            inputMode={rule?.numeric ? 'decimal' : undefined}
            onChange={(e) => onChange(e.target.value)}
          />
          {rule?.unit && <span aria-hidden="true">{rule.unit}</span>}
        </span>
      )}
      {rule?.numeric && <p className="li-hint">A number{rule.integer ? ' (a whole number)' : ''}.</p>}
    </div>
  );
}

/** A form whose Enter (in its text field) does what its submit button does. */
function AnswerForm({ onAnswer, children }: { onAnswer: () => void; children: ReactNode }) {
  return (
    <form
      className="li-form"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        onAnswer();
      }}
    >
      {children}
    </form>
  );
}

/**
 * Each run of one scope, from the QUESTION's own description of it, with what its files suggest —
 * and, marked, the runs whose files have no reading at all, which the answer is written to as well.
 * `null` when the question does not describe the scope run by run.
 */
function RunReadings({ scope }: { scope: LocalScope | undefined }) {
  if (!scope) return null;
  const perRun =
    (scope.per_target ?? []).length > 0
      ? (scope.per_target ?? []).map((t) => ({ key: t.target_id, name: t.run_name, own: t.own_suggestions }))
      : scope.target_count === 1 && scope.run_names.length === 1
        ? [{ key: scope.scope, name: scope.run_names[0], own: scope.own_suggestions ?? [] }]
        : [];
  if (perRun.length === 0) return null;
  const notListed = scope.target_count - perRun.length;
  return (
    <ul className="li-choices li-run-readings" data-testid="li-preview-runs">
      {perRun.map((r) => (
        <li key={r.key} data-no-reading={r.own.length === 0 ? 'true' : undefined}>
          <span className="li-run-names">Run {r.name ?? 'without a name'}</span>
          {r.own.length === 0 ? (
            <span className="li-meta">
              <span className="li-chip">{COPY.noReadingChip}</span> {COPY.previewNoReading}
            </span>
          ) : (
            <span className="li-meta">
              {COPY.previewHasReading} {[...new Set(r.own.map((o) => shownValue(o.value)))].join(' or ')}
            </span>
          )}
        </li>
      ))}
      {notListed > 0 && <li className="li-meta">and {notListed} more run(s) not listed here</li>}
    </ul>
  );
}

function PreviewBox({
  preview,
  scopes,
  busy,
  onWrite,
  onCancel,
  boxRef,
  titleId,
}: {
  preview: ApiLocalAnswerPreview;
  scopes: LocalScope[];
  busy: boolean;
  onWrite: () => void;
  onCancel: () => void;
  boxRef: React.RefObject<HTMLDivElement>;
  titleId: string;
}) {
  const differing = preview.by_scope.filter((g) => g.differs);
  const otherValues = [
    ...new Set(
      differing.flatMap((g) => g.differing_targets.flatMap((t) => t.own_suggestions.map((o) => shownValue(o.value)))),
    ),
  ].filter((v) => v !== shownValue(preview.value));
  const byKey = new Map(scopes.map((sc) => [sc.scope, sc]));
  // a few groups: every run is listed; many: each group's runs behind its own disclosure
  const inline = preview.by_scope.length <= 3;
  return (
    <div className="li-preview" role="group" tabIndex={-1} ref={boxRef} aria-labelledby={titleId}>
      <p id={titleId} className="li-preview-title">
        {COPY.previewTitle} ({preview.by_scope.length} {preview.by_scope.length === 1 ? 'group' : 'groups'},{' '}
        {preview.would_record.length} value(s)):
      </p>
      {differing.length > 0 && (
        <p className="li-warning" data-testid="li-preview-differs">
          {differing.length} of these {preview.scopes_total} groups’ files suggest {otherValues.join(' or ')}, not{' '}
          {shownValue(preview.value)}. Writing this answer for all of them would record {shownValue(preview.value)} for those
          groups too.
        </p>
      )}
      <ul className="li-bullets">
        {preview.by_scope.map((g) => (
          <li key={g.scope} className={g.differs ? 'li-differs' : undefined}>
            {g.label}
            {g.run_names.length ? ` — ${namesText(g.run_names, g.run_count)}` : ''}
            {g.differs && (
              <>
                {' '}
                <span className="li-chip">{COPY.filesSuggestOtherwise}</span>
                <ul className="li-choices">
                  {g.differing_targets.map((t) => (
                    <li key={t.target_id}>
                      <span className="li-run-names">Run {t.run_name ?? 'without a name'}</span>
                      <OwnSuggestions own={t.own_suggestions} />
                    </li>
                  ))}
                </ul>
              </>
            )}
            {!g.compared && g.own_suggestions.length > 0 && <OwnSuggestions own={g.own_suggestions} />}
            {inline ? (
              <RunReadings scope={byKey.get(g.scope)} />
            ) : (
              byKey.get(g.scope) && (
                <details className="li-details">
                  <summary>Its runs</summary>
                  <RunReadings scope={byKey.get(g.scope)} />
                </details>
              )
            )}
          </li>
        ))}
      </ul>
      {preview.unchanged.length > 0 && (
        <p className="li-meta">{preview.unchanged.length} value(s) already answered the same way, so not written again.</p>
      )}
      <p className="li-meta">
        Value: <code>{shownValue(preview.value)}</code>. {preview.statement}
      </p>
      <details className="li-details">
        <summary>{COPY.previewIds}</summary>
        <p className="li-meta li-ids">
          Written to: {preview.would_record.join(', ') || 'none'}
          {preview.unchanged.length > 0 ? `. Unchanged: ${preview.unchanged.join(', ')}` : ''}.
        </p>
      </details>
      <p className="li-actions">
        <button type="button" className="btn btn-primary" disabled={busy} onClick={onWrite}>
          {COPY.previewWrite}
        </button>
        <button type="button" className="btn btn-secondary" disabled={busy} onClick={onCancel}>
          {COPY.previewCancel}
        </button>
      </p>
    </div>
  );
}

function PerGroupRow({
  g,
  busy,
  confirm,
  onAcceptOne,
  onAnswerThis,
}: {
  g: LocalScope;
  busy: boolean;
  confirm: boolean;
  onAcceptOne: (g: LocalScope, value: unknown) => void;
  onAnswerThis: (g: LocalScope) => void;
}) {
  const perRun = g.mixed && (g.per_target ?? []).length > 0;
  return (
    <tr>
      <th scope="row" className="li-col-group">
        <span className="li-run-names">{namesText(g.run_names, g.run_count, 3)}</span>
        <span className="li-group-id">{g.group_id ? `group ${g.group_id}` : g.label}</span>
      </th>
      <td className="li-col-suggestion">
        {perRun ? (
          <ul className="li-choices" data-testid="li-per-run">
            {(g.per_target ?? []).map((t) => (
              <li key={t.target_id}>
                <span className="li-run-names">Run {t.run_name ?? 'without a name'}</span>
                <OwnSuggestions own={t.own_suggestions} />
              </li>
            ))}
          </ul>
        ) : (
          <OwnSuggestions own={g.own_suggestions ?? []} total={g.own_suggestions_total} />
        )}
      </td>
      <td className="li-col-actions">
        <ul className="li-choices">
          {/* one value for the whole group only where its runs agree; a mixed group is answered by the person */}
          {g.has_unanimous_value && !g.mixed && (
            <li>
              <button
                type="button"
                className="btn btn-secondary li-accept"
                disabled={busy}
                title={`${confirm ? 'Confirm' : 'Accept'} ${shownValue(g.unanimous_value)}`}
                onClick={() => onAcceptOne(g, g.unanimous_value)}
              >
                {confirm ? 'Confirm' : 'Accept'} {shownValue(g.unanimous_value)}
                <span className="sr-only"> for {g.label}</span>
              </button>
            </li>
          )}
          <li>
            <button type="button" className="btn btn-secondary li-accept" disabled={busy} onClick={() => onAnswerThis(g)}>
              {COPY.answerThisGroup}
              <span className="sr-only"> ({g.label})</span>
            </button>
          </li>
        </ul>
      </td>
    </tr>
  );
}

function PerGroupTable({
  groups,
  busy,
  titleId,
  confirm,
  onAcceptOne,
  onAcceptMany,
  onAnswerThis,
}: {
  groups: LocalScope[];
  busy: boolean;
  titleId: string;
  confirm: boolean;
  onAcceptOne: (g: LocalScope, value: unknown) => void;
  onAcceptMany: (value: unknown, scopes: string[]) => void;
  onAnswerThis: (g: LocalScope) => void;
}) {
  const { withSuggestion, mixed, without, counts, ownFiles } = groupBySuggestion(groups);
  const head = (
    <thead>
      <tr>
        <th scope="col">Runs (group)</th>
        <th scope="col">What its readings suggest</th>
        <th scope="col" className="li-col-actions">
          Answer
        </th>
      </tr>
    </thead>
  );
  const row = (g: LocalScope) => (
    <PerGroupRow key={g.scope} g={g} busy={busy} confirm={confirm} onAcceptOne={onAcceptOne} onAnswerThis={onAnswerThis} />
  );
  return (
    <div className="li-per-group" role="group" aria-labelledby={titleId}>
      <p className="li-warning">{COPY.suggestionsDiffer}</p>
      <h5 id={titleId} className="li-h5">
        {COPY.perGroupTitle} ({groups.length})
      </h5>
      <p className="li-meta" data-testid="li-suggestion-counts">
        {[
          ...counts.map((c) => `${shownValue(c.value)}: ${c.groups} group(s)`),
          ...(mixed.length ? [`runs disagree within the group: ${mixed.length} group(s)`] : []),
          `nothing suggested: ${without.length} group(s)`,
        ].join(' · ')}
      </p>
      {counts.some((c) => (ownFiles[c.key] ?? []).length > 0) && (
        <ul className="li-choices">
          {counts
            .filter((c) => (ownFiles[c.key] ?? []).length > 0)
            .map((c) => (
              <li key={c.key}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={busy}
                  onClick={() => onAcceptMany(c.value, ownFiles[c.key])}
                >
                  {confirm ? 'Confirm' : 'Accept'} {shownValue(c.value)} for the {ownFiles[c.key].length} group(s) whose own files
                  all suggest it
                </button>
              </li>
            ))}
          <li className="li-hint">
            Each lists exactly those groups in a preview before anything is written. A group counts only when every
            one of its runs that suggests anything suggests this value from its own files.
          </li>
        </ul>
      )}
      {withSuggestion.length > 0 && (
        <table className="li-table li-table-groups">
          {head}
          <tbody>{withSuggestion.map(row)}</tbody>
        </table>
      )}
      {mixed.length > 0 && (
        <>
          <h5 className="li-h5">
            {COPY.mixedTitle} ({mixed.length})
          </h5>
          <p className="li-hint">{COPY.mixedNote}</p>
          <table className="li-table li-table-groups" data-testid="li-mixed-groups">
            {head}
            <tbody>{mixed.map(row)}</tbody>
          </table>
        </>
      )}
      {without.length > 0 && (
        <details className="li-details">
          <summary>
            {COPY.nothingSuggestedRows} ({without.length})
          </summary>
          <table className="li-table li-table-groups">
            {head}
            <tbody>{without.map(row)}</tbody>
          </table>
        </details>
      )}
    </div>
  );
}

interface SubmitScope {
  /** Exactly this one group (`only`). */
  scope?: string;
  /** Exactly these groups (`only_scopes`), always through the preview. */
  scopes?: string[];
  /** Preview first even for one group (an accepted value is written to every run of the group). */
  preview?: boolean;
}

function QuestionCard({ q, handlers }: { q: LocalQuestion; handlers: WriteHandlers }) {
  const d = q.display;
  const uid = useId();
  const groups = perGroupScopes(q);
  const multi = groups.length > 1;
  // U1: where the groups' own files suggest different values, no scope is chosen for the person
  const [scopeMode, setScopeMode] = useState<'all' | 'one' | null>(multi && d.suggestions_differ ? null : 'all');
  // which group "This group only" is for: none until the person chooses one
  const [only, setOnly] = useState('');
  const [groupGone, setGroupGone] = useState(false);
  const [value, setValue] = useState('');
  const optionalFields = Object.keys(d.fields);
  const [field, setField] = useState(optionalFields[0] ?? '');
  const [positions, setPositions] = useState<number[]>([]);
  const [element, setElement] = useState(d.suggested_absorber?.element ?? '');
  const [edge, setEdge] = useState(d.suggested_absorber?.edge ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ text: string; n: number } | null>(null);
  const [status, setStatus] = useState('');
  const [recorded, setRecorded] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ input: LocalAnswerInput; result: ApiLocalAnswerPreview } | null>(null);
  const previewRef = useRef<HTMLDivElement>(null);
  const errorRef = useRef<HTMLParagraphElement>(null);
  const titleRef = useRef<HTMLHeadingElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const valueId = `${uid}-v`;
  const zones = useMemo(() => (d.answer_kind === 'clock_zone' ? ianaZones() : []), [d.answer_kind]);

  /*
   * THE CHOSEN GROUP MUST STILL BE ASKED ABOUT. A question's id does not change when one of its
   * groups is answered, so after answering group A "this group only" the card stays mounted with A
   * chosen while A is no longer listed — the dropdown showed the first remaining group while the
   * next Answer sent A, which the server refused. The choice is cleared (a new one is required),
   * and the dropdown and what is sent read the same value.
   */
  const onlyListed = groups.some((g) => g.scope === only);
  const chosen = onlyListed ? only : '';
  useEffect(() => {
    if (only !== '' && !onlyListed) {
      setOnly('');
      setGroupGone(true);
    }
  }, [only, onlyListed]);

  useEffect(() => {
    if (preview) previewRef.current?.focus();
  }, [preview]);
  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);

  const say = (text: string) => setError((cur) => ({ text, n: (cur?.n ?? 0) + 1 }));

  const acceptable = d.suggestions.filter((s) => s.acceptable);
  const others = d.suggestions.filter((s) => !s.acceptable);
  const fieldSuggestions = field ? (d.field_suggestions[field] ?? []) : [];
  const rule = d.answer_kind === 'optional_values' ? (d.fields[field] ?? null) : d.value_rule;
  const selected = groups.find((g) => g.scope === chosen);
  const perGroupTable = multi && d.suggestions_differ && (d.answer_kind === 'field_value' || d.answer_kind === 'confirm_value');

  function fail(err: unknown) {
    const code = localReasonCodeOf(err);
    if (statusOf(err) === 412) {
      // said HERE, on the card that was refused — another card's "Recorded" is not replaced
      say(COPY.staleWrite);
      handlers.onReread(q.question_id, null);
      return;
    }
    if (statusOf(err) === 404 && code === 'not_found_in_bundle') {
      say(COPY.goneElsewhere);
      handlers.onReread(q.question_id, COPY.goneElsewhere);
      return;
    }
    say(localReasonOf(err) ?? 'The answer could not be recorded. Nothing was written.');
  }

  function recordedMessage(n: number) {
    return `Recorded ${n} answer(s) to “${q.text.slice(0, 80)}”.`;
  }

  function written(result: ApiLocalAnswerRecorded, sentWith: string) {
    const message = recordedMessage(result.result.recorded.length);
    setRecorded(message);
    handlers.onWritten(q.question_id, message, { sentWith, now: result.bundle_version });
  }

  async function submit(decision: string, extra: Partial<LocalAnswerInput> = {}, how: SubmitScope = {}) {
    setError(null);
    setStatus('');
    opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (!handlers.by.trim()) {
      handlers.needName();
      return;
    }
    if (how.scope === undefined && how.scopes === undefined && multi && scopeMode === null) {
      say(COPY.chooseScope);
      return;
    }
    if (how.scope === undefined && how.scopes === undefined && multi && scopeMode === 'one' && !chosen) {
      say(groupGone ? COPY.groupGone : COPY.chooseGroup);
      return;
    }
    if (extra.element !== undefined && extra.element.trim().length > LOCAL_LIMITS.elementMax) {
      say(`Element: at most ${LOCAL_LIMITS.elementMax} characters (a chemical symbol, for example Fe).`);
      return;
    }
    const oneScope = how.scopes ? undefined : (how.scope ?? (multi && scopeMode === 'one' ? chosen : undefined));
    const input: LocalAnswerInput = {
      decision,
      by: handlers.by.trim(),
      expected_version: handlers.version,
      ...(oneScope ? { only: oneScope } : {}),
      ...(how.scopes ? { only_scopes: how.scopes } : {}),
      ...(d.answer_kind === 'optional_values' ? { field } : {}),
      ...extra,
      ...(extra.note !== undefined ? { note: clampText(extra.note, LOCAL_LIMITS.noteMax) } : {}),
    };
    // every answer that writes to more than one run — several groups, a group of several runs, an
    // accepted value, or targets this page did not describe one by one — is previewed first, listing
    // every group and run; only an answer for exactly one run is written at once
    const oneGroup = oneScope ? groups.find((g) => g.scope === oneScope) : undefined;
    const needsPreview =
      how.preview === true ||
      how.scopes !== undefined ||
      (oneScope !== undefined && (oneGroup?.target_count ?? 1) > 1) ||
      (oneScope === undefined && (multi || d.settles_many || d.targets_described < d.targets_total));
    setBusy(true);
    try {
      if (needsPreview) {
        const result = await api.previewLocalAnswer(handlers.name, q.question_id, input);
        setPreview({ input, result });
      } else {
        const result = await api.answerLocalQuestion(handlers.name, q.question_id, input);
        written(result, input.expected_version);
      }
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  async function confirmPreview() {
    if (!preview) return;
    setBusy(true);
    setError(null);
    const sentWith = preview.result.bundle_version;
    try {
      const result = await api.answerLocalQuestion(handlers.name, q.question_id, {
        ...preview.input,
        expected_version: sentWith,
      });
      setPreview(null);
      // the SERVER's count of what it recorded, never the preview's
      written(result, sentWith);
    } catch (err) {
      setPreview(null);
      fail(err);
    } finally {
      setBusy(false);
    }
  }

  function cancelPreview() {
    setPreview(null);
    setStatus(COPY.previewCancelled);
    // back to the control that opened the preview, if it is still there; else the question itself
    const back = opener.current;
    requestAnimationFrame(() => {
      if (back && back.isConnected && !(back as HTMLButtonElement).disabled) back.focus();
      else titleRef.current?.focus();
    });
  }

  const answerButton = (primary = true) => (
    <p className="li-actions">
      <button type="submit" className={`btn ${primary ? 'btn-primary' : 'btn-secondary'}`} disabled={busy}>
        {COPY.answer}
      </button>
    </p>
  );

  const answerControls: ReactNode = (() => {
    switch (d.answer_kind) {
      case 'confirm_value':
        return (
          <>
            {d.distinct_extracted_values.length > 0 && (
              <p className="li-actions">
                <button type="button" className="btn btn-primary" disabled={busy} onClick={() => submit('confirm')}>
                  {COPY.acceptSuggestion}
                </button>
                <span className="li-meta">
                  Confirms each run’s own extracted value:{' '}
                  {d.distinct_extracted_values.map((v) => `${shownValue(v.value)} (${v.targets})`).join(', ')}.
                </span>
              </p>
            )}
            <AnswerForm onAnswer={() => submit('correct', { value })}>
              <ValueInput id={valueId} rule={rule} value={value} onChange={setValue} label="Or correct it" />
              {answerButton(false)}
            </AnswerForm>
          </>
        );
      case 'conflict':
        return (
          <>
            {acceptable.length > 0 && (
              <ul className="li-choices">
                {acceptable.map((s, i) => (
                  <li key={i}>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      disabled={busy}
                      onClick={() => submit('confirm', { value: answerText(s.value) })}
                    >
                      Use this reading: {shownValue(s.value)}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <AnswerForm onAnswer={() => submit('correct', { value })}>
              <ValueInput id={valueId} rule={rule} value={value} onChange={setValue} label="Or another value" />
              {answerButton()}
            </AnswerForm>
          </>
        );
      case 'optional_values':
        return (
          <AnswerForm onAnswer={() => submit('correct', { value })}>
            <div className="li-field">
              <label htmlFor={`${uid}-f`}>Field</label>
              <select id={`${uid}-f`} className="input li-select" value={field} onChange={(e) => setField(e.target.value)}>
                {optionalFields.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>
            </div>
            {fieldSuggestions.map((s, i) => (
              <SuggestionItem key={i} s={s} />
            ))}
            <ValueInput id={valueId} rule={rule} value={value} onChange={setValue} label="Value" />
            {answerButton()}
          </AnswerForm>
        );
      case 'counter_positions':
        return (
          <>
            <fieldset className="li-fieldset">
              <legend>Filename positions asked about (check the ones that are run counters)</legend>
              {(q.positions ?? []).map((p) => (
                <label key={p} className="li-check">
                  <input
                    type="checkbox"
                    checked={positions.includes(p)}
                    onChange={(e) =>
                      setPositions((cur) => (e.target.checked ? [...cur, p].sort((a, b) => a - b) : cur.filter((x) => x !== p)))
                    }
                  />
                  Position {p}
                </label>
              ))}
            </fieldset>
            <p className="li-actions">
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy || positions.length === 0}
                onClick={() => submit('set_counter_positions', { positions })}
              >
                The checked positions are run counters
              </button>
              <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => submit('set_not_counter_positions')}>
                None of these is a counter
              </button>
            </p>
            <p className="li-hint">{COPY.counterAfter}</p>
            <CommandBlock command={regroupCommand(handlers.name)} label="Command that proposes the groups again" />
          </>
        );
      case 'clock_zone':
        return (
          <AnswerForm onAnswer={() => submit('set_clock_time_zone', { value })}>
            <div className="li-field">
              <label htmlFor={`${uid}-z`}>Time zone the instrument clock was set to (IANA name, e.g. America/Los_Angeles, or UTC)</label>
              <input id={`${uid}-z`} className="input" list={`${uid}-zones`} value={value} onChange={(e) => setValue(e.target.value)} />
              {zones.length > 0 && (
                <datalist id={`${uid}-zones`}>
                  {zones.map((z) => (
                    <option key={z} value={z} />
                  ))}
                </datalist>
              )}
              <p className="li-hint">No file states it, so nothing is suggested.</p>
            </div>
            {answerButton()}
          </AnswerForm>
        );
      case 'absorber':
        return (
          <AnswerForm onAnswer={() => submit('set_absorber', { element, edge })}>
            {d.suggested_absorber && (
              <p className="li-meta">
                <span className="li-chip">{COPY.suggestedNotConfirmed}</span> Element {d.suggested_absorber.element}, edge{' '}
                {d.suggested_absorber.edge} — {d.suggested_absorber.basis}.
              </p>
            )}
            <div className="li-row">
              <div className="li-field">
                <label htmlFor={`${uid}-el`}>Element</label>
                <input
                  id={`${uid}-el`}
                  className="input li-short"
                  value={element}
                  maxLength={LOCAL_LIMITS.elementMax}
                  onChange={(e) => setElement(e.target.value)}
                />
              </div>
              <div className="li-field">
                <label htmlFor={`${uid}-ed`}>Edge</label>
                <select id={`${uid}-ed`} className="input li-select" value={edge} onChange={(e) => setEdge(e.target.value)}>
                  <option value="">Choose…</option>
                  {ABSORBER_EDGES.map((e) => (
                    <option key={e} value={e}>
                      {e}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <p className="li-actions">
              <button type="submit" className="btn btn-primary" disabled={busy}>
                {d.suggested_absorber && element === d.suggested_absorber.element && edge === d.suggested_absorber.edge
                  ? COPY.acceptSuggestion
                  : COPY.answer}
              </button>
            </p>
          </AnswerForm>
        );
      case 'field_value':
      default:
        return (
          <>
            {acceptable.length > 0 && (
              <ul className="li-choices">
                {acceptable.map((s, i) => (
                  <li key={i}>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      disabled={busy}
                      onClick={() =>
                        submit('correct', {
                          value: answerText(s.value),
                          note: `Accepted the suggestion shown (${s.who_label}${s.relative_path ? `, ${s.relative_path}` : ''}${s.locator ? ` @ ${s.locator}` : ''}).`,
                        })
                      }
                    >
                      {COPY.acceptSuggestion}: {shownValue(s.value)}
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <AnswerForm onAnswer={() => submit('correct', { value })}>
              <ValueInput id={valueId} rule={rule} value={value} onChange={setValue} label="Your answer" />
              {answerButton()}
            </AnswerForm>
          </>
        );
    }
  })();

  return (
    <li className="li-card li-question" aria-labelledby={`${uid}-t`} data-card-id={q.question_id}>
      <div className="li-card-head">
        <span className="li-chip">{q.blocking ? COPY.chipBlocks : COPY.chipOptional}</span>
        <span className="li-meta">{KIND_LABEL[q.kind] ?? q.kind}</span>
      </div>
      <h4 id={`${uid}-t`} className="li-h4 li-question-text" tabIndex={-1} ref={titleRef} data-li-title>
        {q.text}
      </h4>
      {recorded && (
        <p className="li-recorded" tabIndex={-1} data-li-recorded>
          {COPY.answeredHere} {recorded}
        </p>
      )}
      <dl className="li-dl">
        <dt>Record (runs)</dt>
        <dd>{d.record_run_names.length ? namesText(d.record_run_names) : 'The whole beamtime'}</dd>
        {q.target_field_path && (
          <>
            <dt>Field</dt>
            <dd>
              <code>{q.target_field_path}</code>
            </dd>
          </>
        )}
        <dt>Applies to</dt>
        <dd>
          {q.applies_to.groups} group(s), {q.applies_to.runs} run(s); answering records {q.applies_to.targets} value(s)
        </dd>
        <dt>Why</dt>
        <dd>{q.why}</dd>
      </dl>

      <div className="li-suggestions">
        <h5 className="li-h5">{COPY.suggestedNotConfirmed}</h5>
        {acceptable.length === 0 && d.answer_kind !== 'absorber' ? (
          <p className="li-meta">{COPY.noSuggestion}</p>
        ) : (
          acceptable.map((s, i) => <SuggestionItem key={i} s={s} />)
        )}
        {d.suggestions_total > d.suggestions.length && (
          <p className="li-meta">
            Showing {d.suggestions.length} of {d.suggestions_total} suggestions and hints.
          </p>
        )}
        <p className="li-hint">{d.suggestion_statement}</p>
        {others.length > 0 && (
          <details className="li-details">
            <summary>
              {COPY.otherReadings} ({others.length})
            </summary>
            {others.map((s, i) => (
              <SuggestionItem key={i} s={s} />
            ))}
          </details>
        )}
      </div>

      {rule?.allowed && (
        <p className="li-meta">
          {COPY.allowedAnswers}: {rule.allowed.map(shownValue).join(', ')}
        </p>
      )}

      {perGroupTable && (
        <PerGroupTable
          groups={groups}
          busy={busy}
          titleId={`${uid}-pg`}
          confirm={d.answer_kind === 'confirm_value'}
          onAcceptOne={(g, v) =>
            d.answer_kind === 'confirm_value'
              ? // offered only where every run's own extracted value IS v, so confirming confirms v
                submit('confirm', {}, { scope: g.scope, preview: true })
              : submit(
                  'correct',
                  {
                    value: answerText(v),
                    note: `Accepted the value every run of this group with a reading suggests (${(g.own_suggestions ?? [])
                      .map((o) => `${o.provenance_label}; ${o.who_label}${o.relative_path ? `, ${o.relative_path}` : ''}${o.locator ? ` @ ${o.locator}` : ''}`)
                      .join(' | ')}).`,
                  },
                  { scope: g.scope, preview: true },
                )
          }
          onAcceptMany={(value, scopes) =>
            d.answer_kind === 'confirm_value'
              ? submit('confirm', {}, { scopes })
              : submit('correct', { value: answerText(value) }, { scopes })
          }
          onAnswerThis={(g) => {
            setScopeMode('one');
            setOnly(g.scope);
            setGroupGone(false);
            document.getElementById(valueId)?.focus();
          }}
        />
      )}

      {multi && (
        <fieldset className="li-fieldset">
          <legend>Answer for</legend>
          <label className="li-radio">
            <input type="radio" name={`${uid}-scope`} checked={scopeMode === 'all'} onChange={() => setScopeMode('all')} />
            {COPY.sameForAll} ({groups.length})
          </label>
          <label className="li-radio">
            <input type="radio" name={`${uid}-scope`} checked={scopeMode === 'one'} onChange={() => setScopeMode('one')} />
            {COPY.thisGroupOnly}
          </label>
          {scopeMode === 'one' && (
            <>
              <select
                className="input li-select"
                aria-label="Which group"
                value={chosen}
                onChange={(e) => {
                  setOnly(e.target.value);
                  setGroupGone(false);
                }}
              >
                <option value="">Choose a group…</option>
                {groups.map((g) => (
                  <option key={g.scope} value={g.scope}>
                    {g.label}: {namesText(g.run_names, g.run_count, 3)}
                  </option>
                ))}
              </select>
              {groupGone && !chosen && (
                <p className="li-hint" data-testid="li-group-gone">
                  {COPY.groupGone}
                </p>
              )}
              {selected && (
                <div className="li-selected-group" data-testid="li-selected-group">
                  <OwnSuggestions own={selected.own_suggestions ?? []} total={selected.own_suggestions_total} />
                </div>
              )}
            </>
          )}
        </fieldset>
      )}

      {answerControls}

      {error && (
        <p key={error.n} className="li-error" role="alert" tabIndex={-1} ref={errorRef}>
          {error.text}
        </p>
      )}
      <p className="li-meta" role="status" data-testid="li-card-status">
        {status}
      </p>

      {preview && (
        <PreviewBox
          preview={preview.result}
          scopes={q.display.scopes}
          busy={busy}
          onWrite={confirmPreview}
          onCancel={cancelPreview}
          boxRef={previewRef}
          titleId={`${uid}-pv`}
        />
      )}

      <details className="li-details">
        <summary>Command-line equivalent</summary>
        <pre className="li-command">{q.answer_command}</pre>
      </details>
    </li>
  );
}

// --- capture decisions -------------------------------------------------------------------------

function CaptureSection({ data, handlers }: { data: ApiLocalQuestions; handlers: WriteHandlers }) {
  const { merge_candidates: merges, athena_selections: athena } = data.capture;
  if (merges.length === 0 && athena.length === 0) return null;
  return (
    <section className="li-section" aria-labelledby="li-capture-title">
      <h3 id="li-capture-title" className="li-h3">
        {COPY.captureTitle}
      </h3>
      {merges.length > 0 && (
        <>
          <h4 className="li-h4">{COPY.mergeTitle}</h4>
          <p className="li-hint">{COPY.mergeAfter}</p>
          <CommandBlock command={regroupCommand(handlers.name)} label="Command that proposes the groups again" />
          <ol className="li-list">
            {merges.map((m) => (
              <MergeCard key={m.merge_candidate_id} m={m} handlers={handlers} />
            ))}
          </ol>
        </>
      )}
      {athena.length > 0 && (
        <>
          <h4 className="li-h4">{COPY.athenaTitle}</h4>
          <ol className="li-list">
            {athena.map((a) => (
              <AthenaCard key={a.processing_id} a={a} handlers={handlers} />
            ))}
          </ol>
        </>
      )}
    </section>
  );
}

function useDecision(id: string, handlers: WriteHandlers) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ text: string; n: number } | null>(null);
  const [recorded, setRecorded] = useState<string | null>(null);
  const say = (text: string) => setError((cur) => ({ text, n: (cur?.n ?? 0) + 1 }));
  async function record(input: Omit<Parameters<typeof api.recordLocalDecision>[1], 'by' | 'expected_version'>, done: string) {
    setError(null);
    if (!handlers.by.trim()) {
      handlers.needName();
      return;
    }
    setBusy(true);
    const sentWith = handlers.version;
    try {
      const result = await api.recordLocalDecision(handlers.name, { ...input, by: handlers.by.trim(), expected_version: sentWith });
      setRecorded(done);
      handlers.onWritten(id, done, { sentWith, now: result.bundle_version });
    } catch (err) {
      if (statusOf(err) === 412) {
        say(COPY.staleWrite);
        handlers.onReread(id, null);
      } else if (statusOf(err) === 404 && localReasonCodeOf(err) === 'not_found_in_bundle') {
        say(COPY.goneElsewhere);
        handlers.onReread(id, COPY.goneElsewhere);
      } else {
        say(localReasonOf(err) ?? 'The decision could not be recorded. Nothing was written.');
      }
    } finally {
      setBusy(false);
    }
  }
  const feedback = (
    <>
      {recorded && (
        <p className="li-recorded" tabIndex={-1} data-li-recorded>
          {COPY.answeredHere} {recorded}
        </p>
      )}
      {error && (
        <p key={error.n} className="li-error" role="alert">
          {error.text}
        </p>
      )}
    </>
  );
  return { busy, record, feedback };
}

function MergeCard({ m, handlers }: { m: LocalMergeCandidate; handlers: WriteHandlers }) {
  const { busy, record, feedback } = useDecision(m.merge_candidate_id, handlers);
  const [first, ...rest] = m.group_ids;
  return (
    <li className="li-card" data-card-id={m.merge_candidate_id}>
      <p className="li-question-text" tabIndex={-1} data-li-title>
        {m.question ?? `Merge or keep apart: groups ${m.group_ids.join(', ')}`}
      </p>
      <ul className="li-bullets">
        {m.groups.map((g) => (
          <li key={g.group_id}>
            Group {g.group_id}: {namesText(g.run_names)}
          </li>
        ))}
      </ul>
      <p className="li-actions">
        <button
          type="button"
          className="btn btn-secondary"
          disabled={busy}
          onClick={() => record({ target: m.merge_candidate_id, decision: 'keep_apart' }, `Recorded: ${m.group_ids.join(', ')} stay apart.`)}
        >
          {COPY.keepApart}
        </button>
        {first && rest.length > 0 && (
          <button
            type="button"
            className="btn btn-secondary"
            disabled={busy}
            onClick={() => record({ target: first, decision: 'merge', merge_with: rest }, `Recorded: merge ${m.group_ids.join(', ')}.`)}
          >
            {COPY.mergeThem}
          </button>
        )}
      </p>
      {feedback}
    </li>
  );
}

function AthenaCard({ a, handlers }: { a: LocalAthenaSelection; handlers: WriteHandlers }) {
  const { busy, record, feedback } = useDecision(a.processing_id, handlers);
  const [version, setVersion] = useState(a.versions[0]?.version_id ?? '');
  const id = useId();
  return (
    <li className="li-card" data-card-id={a.processing_id}>
      <p className="li-question-text" tabIndex={-1} data-li-title>
        {COPY.athenaQuestion} {a.processing_id}
        {a.run_names.length ? ` (runs ${namesText(a.run_names)})` : ''}?
      </p>
      <div className="li-field">
        <label htmlFor={id}>Athena version</label>
        <select id={id} className="input li-select" value={version} onChange={(e) => setVersion(e.target.value)}>
          {a.versions.map((v) => (
            <option key={v.version_id} value={v.version_id}>
              {v.version_id}
              {v.project_file ? ` — ${v.project_file}` : ''}
              {v.athena_group ? ` (${v.athena_group})` : ''}
            </option>
          ))}
        </select>
      </div>
      <p className="li-actions">
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy || !version}
          onClick={() =>
            record({ target: a.processing_id, decision: 'select_athena_version', value: version }, `Recorded: ${version} is the final result.`)
          }
        >
          {COPY.selectAthena}
        </button>
      </p>
      {feedback}
    </li>
  );
}
