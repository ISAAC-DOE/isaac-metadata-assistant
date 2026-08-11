/*
 * P26.5 · SearchDialog — the ⌘K command palette, a self-contained TopBar
 * affordance (visible "Search ⌘K" trigger + a focus-trapped role="dialog").
 *
 * It queries GET /api/search (via api.search) and renders TWO clearly
 * separated, self-labeled groups: Workspace (truth plane) and Project Memory
 * (advisory leads). The two groups are NEVER merged or ranked together — each
 * is independently honest, and a degraded memory plane is a quiet advisory
 * note (never role=alert, never a verdict color) while workspace results still
 * render. Every row navigates via the server-supplied `navigate_to` and closes
 * the dialog; nothing is ever fabricated (no fake rows, no verdict language —
 * `hasVerdictLanguage` is a defensive filter on every snippet).
 *
 * Interaction mirrors ResetDemoDialog: document-level ⌘K/Ctrl-K open,
 * capture-phase Escape (close + return focus to trigger) and Tab containment,
 * and it reuses the `.artifact-modal` shell.
 */

import './search-dialog.css';
import { useCallback, useEffect, useId, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, ApiError, isHostedBuild, RUN_COMMAND } from '../lib/api';
import { downCopy, DownTechnicalDetails, LoadingPanel } from './FetchStates';
import { hasVerdictLanguage } from '../lib/assistant';
import { Search } from './icons';
import { crossRecordTriage } from '../lib/crossRecordTriage';
import type { TriageIntent, TriageResult } from '../lib/crossRecordTriage';
import type { ApiSearchMatch, ApiSearchResponse } from '../lib/types';
import { useWorkspaceScope } from '../lib/workspaceScope';

/**
 * The four cross-record triage intents, each with its display label and the
 * SERVER-side filter it sends to GET /api/runtime/records. The provider filters
 * (justifying the P30.1 typed filters); the pure `crossRecordTriage` then formats
 * the SAFE, verdict-free summary + the /record/<id> handoff for each row.
 */
const TRIAGE_CHIPS: {
  intent: TriageIntent;
  label: string;
  filter: Parameters<typeof api.getRuntimeRecords>[0];
}[] = [
  { intent: 'needs_attention', label: 'Needs Attention', filter: { status: 'needs_attention' } },
  { intent: 'blocked', label: 'Blocked', filter: { workflow_state: 'blocked' } },
  { intent: 'has_conflict', label: 'Has Conflicts', filter: { has_conflict: true } },
  { intent: 'exportable', label: 'Ready to Export', filter: { status: 'ready_to_export' } },
];

type Triage =
  | { status: 'idle' }
  | { status: 'loading'; intent: TriageIntent }
  | { status: 'error'; intent: TriageIntent }
  | { status: 'data'; intent: TriageIntent; result: TriageResult };

/** A normalized query below this length never fetches (guarded client-side). */
const MIN_QUERY = 2;
/** Debounce well under the 1000ms `findBy*` window so results settle in tests. */
const DEBOUNCE_MS = 200;

type Results =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error'; error: ApiError }
  | { status: 'data'; data: ApiSearchResponse };

/**
 * The matched snippet, with the server's match offsets rendered as <mark>.
 * Defensive honesty: a snippet that somehow carries verdict language is never
 * rendered at all (the assistant/search planes never state a verdict).
 */
function Snippet({ match }: { match: ApiSearchMatch }) {
  const { snippet, offsets } = match;
  if (!snippet || hasVerdictLanguage(snippet)) return null;

  const spans = [...(offsets ?? [])]
    .filter(([s, e]) => s >= 0 && e <= snippet.length && s < e)
    .sort((a, b) => a[0] - b[0]);

  if (spans.length === 0) {
    // No usable offsets: still render inside a <mark> so the snippet is a
    // highlight element, not a bare text node that could shadow the label.
    return (
      <span className="search-snippet">
        <mark className="search-mark">{snippet}</mark>
      </span>
    );
  }

  const parts: ReactNode[] = [];
  let cursor = 0;
  spans.forEach(([s, e], i) => {
    if (s > cursor) parts.push(<span key={`t${i}`}>{snippet.slice(cursor, s)}</span>);
    parts.push(
      <mark key={`m${i}`} className="search-mark">
        {snippet.slice(s, e)}
      </mark>,
    );
    cursor = e;
  });
  if (cursor < snippet.length) parts.push(<span key="tail">{snippet.slice(cursor)}</span>);
  return <span className="search-snippet">{parts}</span>;
}

interface ResultRowProps {
  label: string;
  match: ApiSearchMatch;
  onSelect: () => void;
  /**
   * P33 S6 (D12) — the owning experiment/record this match belongs to, shown so
   * two results with the SAME field label (e.g. "Beamline" on two experiments)
   * are distinguishable. Purely presentational: it reads an already-present field
   * on the result object and never affects ranking or retrieval.
   */
  context?: string;
}

function ResultRow({ label, match, onSelect, context }: ResultRowProps) {
  return (
    <li className="search-result">
      <button type="button" className="search-result-btn" onClick={onSelect}>
        <span className="search-result-label">{label}</span>
        {context && <span className="search-result-context">in {context}</span>}
        <span className="search-result-reason">{match.reason}</span>
        {/* The snippet is shown only when it adds context beyond the label — a
            snippet identical to the label is redundant, so it is not repeated. */}
        {match.snippet && match.snippet !== label && <Snippet match={match} />}
      </button>
    </li>
  );
}

export function SearchDialog() {
  const navigate = useNavigate();

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [results, setResults] = useState<Results>({ status: 'idle' });
  const [triage, setTriage] = useState<Triage>({ status: 'idle' });

  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const wasOpenRef = useRef(false);
  const titleId = useId();
  const wsHeadId = useId();
  const memHeadId = useId();
  const triageHeadId = useId();

  const closeDialog = useCallback(() => setOpen(false), []);

  const openDialog = useCallback(() => {
    setQuery('');
    setDebounced('');
    setResults({ status: 'idle' });
    setTriage({ status: 'idle' });
    setOpen(true);
  }, []);

  // P30.3 — run one cross-record triage intent: fetch the SAFE runtime-record
  // projection (server-filtered for this intent), then format it through the
  // pure, deterministic `crossRecordTriage`. The result reflects the fetch time
  // (Workspace-derived, current-by-construction on the backend) — a LEAD, not
  // record truth. A fetch failure degrades to an honest "unavailable" state that
  // never blocks the query search below. Never mutates and never rules a verdict.
  const runTriage = useCallback(
    (intent: TriageIntent, filter: Parameters<typeof api.getRuntimeRecords>[0]) => {
      setTriage({ status: 'loading', intent });
      api
        .getRuntimeRecords(filter)
        .then(({ records }) => {
          setTriage({ status: 'data', intent, result: crossRecordTriage(records, intent) });
        })
        .catch(() => {
          setTriage({ status: 'error', intent });
        });
    },
    [],
  );

  // Global ⌘K / Ctrl-K opens the palette from anywhere (always mounted).
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault();
        setOpen(true);
      }
    }
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, []);

  // Debounce the raw input into the query actually sent to the backend.
  useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => setDebounced(query), DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [query, open]);

  const normalized = debounced.trim();
  const tooShort = normalized.length > 0 && normalized.length < MIN_QUERY;
  const shouldFetch = normalized.length >= MIN_QUERY;

  // Fetch on each settled (debounced) query — but never for an empty or
  // too-short query (the honest client-side guard: no fabricated request).
  useEffect(() => {
    if (!open || !shouldFetch) {
      setResults({ status: 'idle' });
      return;
    }
    let alive = true;
    setResults({ status: 'loading' });
    api
      .search(normalized)
      .then((data) => {
        if (alive) setResults({ status: 'data', data });
      })
      .catch((err: unknown) => {
        if (!alive) return;
        const error =
          err instanceof ApiError
            ? err
            : new ApiError(err instanceof Error ? err.message : String(err));
        setResults({ status: 'error', error });
      });
    return () => {
      alive = false;
    };
  }, [open, shouldFetch, normalized]);

  // Move focus into the searchbox on open; return it to the trigger on close.
  useEffect(() => {
    if (open) {
      inputRef.current?.focus();
      wasOpenRef.current = true;
    } else if (wasOpenRef.current) {
      triggerRef.current?.focus();
      wasOpenRef.current = false;
    }
  }, [open]);

  // Escape closes; Tab / Shift+Tab are contained within the dialog. Capture
  // phase so the palette handles the keys first (mirrors ResetDemoDialog).
  useEffect(() => {
    if (!open) return;
    const modal = dialogRef.current;
    if (!modal) return;

    const focusable = () =>
      Array.from(
        modal.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), textarea, input:not([disabled]), select, [tabindex]:not([tabindex="-1"])',
        ),
      );

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.stopPropagation();
        closeDialog();
        return;
      }
      if (e.key !== 'Tab') return;
      // Always contain Tab inside the dialog (preventDefault so focus can never
      // leave the modal), cycling with wraparound over the focusable items.
      e.preventDefault();
      const items = focusable();
      if (items.length === 0) {
        modal!.focus();
        return;
      }
      const active = document.activeElement as HTMLElement | null;
      const idx = active ? items.indexOf(active) : -1;
      const delta = e.shiftKey ? -1 : 1;
      const next = items[(idx + delta + items.length) % items.length] ?? items[0];
      next.focus();
    }

    document.addEventListener('keydown', onKeyDown, true);
    return () => document.removeEventListener('keydown', onKeyDown, true);
  }, [open, closeDialog]);

  const select = useCallback(
    (to: string) => {
      navigate(to);
      closeDialog();
    },
    [navigate, closeDialog],
  );

  return (
    <div role="search" className="topbar-search-region">
      {/*
        FINDING A11Y-02 (A1) fix. The accessible name must NOT depend on CSS.
        `chrome.css`'s `max-width: 640px` block hides `.topbar-search-label` and
        `.topbar-search-kbd`, and the icon is `aria-hidden`, so below the
        breakpoint (and at 200% browser zoom, which lays out at 640px) the
        button computed NO accessible name at all.

        `aria-label` rather than an extra visually-hidden span: aria-label
        OVERRIDES the element's content, so the name is exactly "Search" at
        every width instead of "Search Search ⌘K" wherever the visible label is
        shown. It also holds if the stylesheet fails to load or the breakpoint
        moves — a visually-hidden span would put the name back under CSS
        control, which is the class of bug being fixed here. WCAG 2.5.3
        (label in name) holds: the visible label reads "Search" and the
        accessible name IS "Search".
      */}
      <button
        type="button"
        ref={triggerRef}
        className="topbar-search"
        aria-label="Search"
        aria-haspopup="dialog"
        onClick={openDialog}
      >
        <Search size={14} strokeWidth={2} aria-hidden="true" />
        <span className="topbar-search-label">Search</span>
        <kbd className="topbar-search-kbd">⌘K</kbd>
      </button>

      {open && (
        <div className="artifact-modal-backdrop search-backdrop" onClick={closeDialog}>
          <div
            ref={dialogRef}
            className="artifact-modal search-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            tabIndex={-1}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="artifact-modal-head search-dialog-head">
              <h2 id={titleId} className="artifact-modal-title">
                Search
              </h2>
              <span className="artifact-modal-sub">records and memory leads</span>
            </div>

            <div className="search-input-wrap">
              <Search size={16} strokeWidth={2} aria-hidden="true" className="search-input-icon" />
              <input
                ref={inputRef}
                type="search"
                className="search-input"
                autoComplete="off"
                spellCheck={false}
                aria-label="Search experiments and project memory"
                placeholder="Search experiments and project memory…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>

            <div className="search-body">
              {/* Cross-record triage is the zero-query "quick actions" surface;
                  typing switches the palette to search mode (so the two never
                  compete, and the plane labels below stay unambiguous). */}
              {query.trim() === '' && (
                <TriagePanel
                  triage={triage}
                  headId={triageHeadId}
                  onRun={runTriage}
                  onSelect={select}
                />
              )}

              {normalized.length === 0 && (
                <p className="search-hint">
                  Type to search workspace records and project-memory leads.
                </p>
              )}

              {tooShort && (
                <p className="search-hint">Enter at least 2 characters to search.</p>
              )}

              {shouldFetch && results.status === 'loading' && (
                <LoadingPanel label="Searching…" />
              )}

              {shouldFetch && results.status === 'error' && (
                <SearchDown error={results.error} />
              )}

              {shouldFetch && results.status === 'data' && (
                <SearchResults data={results.data} wsHeadId={wsHeadId} memHeadId={memHeadId} onSelect={select} />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * The compact failure state for the palette. It renders the SAME `downCopy` and
 * the SAME Technical Details disclosure as `BackendDown`, so the two render
 * sites cannot drift apart: a hosted build never shows the local run command
 * here either, and an expired session says so here too. Kept `role="status"`
 * (not `alert`) — the dialog already has the reader's attention.
 */
function SearchDown({ error }: { error: ApiError }) {
  /* The same third argument `BackendDown` passes, so the two sites cannot drift on
     the `example_workspace_ended` branch either. The palette's own reads are search
     reads, so that branch is unreachable from here today — passing the scope keeps
     the "ONE source of copy" property true rather than true by coincidence. The
     palette renders no navigation of its own; the copy names the walkthrough's home
     in words, which needs no link. */
  const scope = useWorkspaceScope();
  const copy = downCopy(error, isHostedBuild, scope);
  return (
    <div className="search-down" role="status">
      <p className="search-down-title">
        Search is unavailable — no server-derived results can be shown.
      </p>
      {copy.lines.map((line) => (
        <p className="search-down-text" key={line}>
          {line}
        </p>
      ))}
      {/* Compile-time guard — see the identical note in FetchStates.BackendDown. */}
      {!isHostedBuild && copy.showRunCommand && (
        <pre className="search-down-cmd mono">{RUN_COMMAND}</pre>
      )}
      {copy.offerReload && (
        <button
          type="button"
          className="btn btn-secondary search-down-action"
          onClick={() => window.location.reload()}
        >
          Reload
        </button>
      )}
      <DownTechnicalDetails error={error} />
    </div>
  );
}

interface TriagePanelProps {
  triage: Triage;
  headId: string;
  onRun: (intent: TriageIntent, filter: Parameters<typeof api.getRuntimeRecords>[0]) => void;
  onSelect: (to: string) => void;
}

/**
 * The CROSS-RECORD triage surface — a deterministic consumer of the P30.1 runtime
 * projection. Four intent chips fetch the SAFE projection and format it through
 * `crossRecordTriage`; each match is a navigable row that HANDS OFF to a direct
 * Workspace load (`/record/<id>`), where the authoritative record is loaded — the
 * triage row is a lead, never the record truth.
 *
 * It is a THIRD, self-labeled surface, kept separate from both the Workspace-search
 * (truth) and Project-Memory (advisory) groups below — it is Workspace-derived and
 * never merged with the memory plane. It never renders a verdict, never presents an
 * inferred candidate as fact, and never picks a conflict winner (the pure function
 * guarantees this; the summaries only count and flag for human review).
 */
function TriagePanel({ triage, headId, onRun, onSelect }: TriagePanelProps) {
  return (
    <section className="search-triage" aria-labelledby={headId}>
      <h3 id={headId} className="search-group-head">
        Cross-record triage
      </h3>
      <p className="search-group-sub">
        Workspace-derived · current as of this fetch. A lead across all records — open
        one to load the authoritative record. Never a verdict.
      </p>

      <div className="search-triage-chips" role="group" aria-label="Cross-record triage filters">
        {TRIAGE_CHIPS.map((chip) => {
          const active = triage.status !== 'idle' && triage.intent === chip.intent;
          const loading = triage.status === 'loading' && triage.intent === chip.intent;
          return (
            <button
              key={chip.intent}
              type="button"
              className="search-triage-chip"
              aria-pressed={active}
              onClick={() => onRun(chip.intent, chip.filter)}
            >
              {chip.label}
              {loading && <span className="search-triage-chip-spin" aria-hidden="true" />}
            </button>
          );
        })}
      </div>

      {triage.status === 'loading' && <LoadingPanel label="Triaging records…" />}

      {triage.status === 'error' && (
        // Honest degradation — the cross-record projection could not be fetched.
        // A quiet status note (never role=alert / verdict color); the query search
        // below is completely unaffected.
        <p className="search-triage-unavailable" role="status">
          Cross-record triage is unavailable right now — the runtime projection could not
          be loaded. Search below is unaffected.
        </p>
      )}

      {triage.status === 'data' && (
        <div className="search-triage-result">
          <p className="search-triage-summary">{triage.result.text}</p>
          {triage.result.matches.length > 0 && (
            <ul className="search-result-list">
              {triage.result.matches.map((m) => (
                <li key={m.experiment_id} className="search-result">
                  <button
                    type="button"
                    className="search-result-btn"
                    onClick={() => onSelect(m.navigate_to)}
                  >
                    <span className="search-result-label">{m.title}</span>
                    <span className="search-result-reason">{m.reason}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

interface SearchResultsProps {
  data: ApiSearchResponse;
  wsHeadId: string;
  memHeadId: string;
  onSelect: (to: string) => void;
}

function SearchResults({ data, wsHeadId, memHeadId, onSelect }: SearchResultsProps) {
  const { workspace, memory } = data;

  // Grand-empty: a valid query that matched nothing in EITHER available group.
  // Honest — never a fabricated row.
  const grandEmpty =
    workspace.available &&
    memory.available &&
    workspace.results.length === 0 &&
    memory.results.length === 0;

  if (grandEmpty) {
    return <p className="search-empty">No matches for “{data.query}”.</p>;
  }

  return (
    <div className="search-groups">
      {/* Workspace — the truth plane. */}
      <section className="search-group search-group-workspace" aria-labelledby={wsHeadId}>
        <h3 id={wsHeadId} className="search-group-head">
          Workspace
        </h3>
        <p className="search-group-sub">Records and evidence in this project.</p>
        {workspace.results.length > 0 ? (
          <ul className="search-result-list">
            {workspace.results.map((r) => (
              <ResultRow
                key={`${r.experiment_id}:${r.match.field}`}
                label={r.label}
                match={r.match}
                // The owning experiment/record title — shown only when it adds
                // information beyond the label itself (never repeated verbatim).
                context={r.title && r.title !== r.label ? r.title : undefined}
                onSelect={() => onSelect(r.navigate_to)}
              />
            ))}
          </ul>
        ) : (
          <p className="search-group-empty">No workspace matches.</p>
        )}
      </section>

      {/* Project Memory — advisory leads, visually distinct, never merged with
          truth and never verdict-colored. */}
      <section className="search-group search-group-memory" aria-labelledby={memHeadId}>
        {/* The plane label reads "Project Memory" but is rendered as two styled
            word-spans, so the heading is never a single text node that would
            collide with the verbatim leads-not-verdict note below (which itself
            begins "Project memory …"). */}
        <h3 id={memHeadId} className="search-group-head">
          <span className="search-group-head-word">Project</span>{' '}
          <span className="search-group-head-word">Memory</span>
        </h3>
        {memory.available ? (
          <>
            <p className="search-group-note">{memory.note}</p>
            {memory.results.length > 0 ? (
              <ul className="search-result-list">
                {memory.results.map((r) => (
                  <ResultRow
                    key={`${r.id ?? r.path}:${r.match.field}`}
                    label={r.label}
                    match={r.match}
                    onSelect={() => onSelect(r.navigate_to)}
                  />
                ))}
              </ul>
            ) : (
              <p className="search-group-empty">No memory leads.</p>
            )}
          </>
        ) : (
          <p className="search-memory-unavailable">
            Project memory is unavailable right now — no leads can be shown. Workspace results
            above are unaffected.
          </p>
        )}
      </section>
    </div>
  );
}
