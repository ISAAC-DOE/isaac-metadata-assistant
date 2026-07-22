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
import { api, ApiError, RUN_COMMAND } from '../lib/api';
import { LoadingPanel } from './FetchStates';
import { hasVerdictLanguage } from '../lib/assistant';
import { Search } from './icons';
import type { ApiSearchMatch, ApiSearchResponse } from '../lib/types';

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
}

function ResultRow({ label, match, onSelect }: ResultRowProps) {
  return (
    <li className="search-result">
      <button type="button" className="search-result-btn" onClick={onSelect}>
        <span className="search-result-label">{label}</span>
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

  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const wasOpenRef = useRef(false);
  const titleId = useId();
  const wsHeadId = useId();
  const memHeadId = useId();

  const closeDialog = useCallback(() => setOpen(false), []);

  const openDialog = useCallback(() => {
    setQuery('');
    setDebounced('');
    setResults({ status: 'idle' });
    setOpen(true);
  }, []);

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
      <button
        type="button"
        ref={triggerRef}
        className="topbar-search"
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
                // Compact, honest backend-down state — server-derived truth only,
                // never fabricated results. Shows the exact command to start the
                // local backend (mirrors FetchStates.BackendDown), kept to a
                // single title element so it reads as one clear message.
                <div className="search-down" role="status">
                  <p className="search-down-title">
                    Search is unavailable — the backend is not reachable.
                  </p>
                  <p className="search-down-text">
                    The local ISAAC API is not responding. Start it, then try again:
                  </p>
                  <pre className="search-down-cmd mono">{RUN_COMMAND}</pre>
                </div>
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
