/*
 * P36R Slice 4 — the deterministic graph command bar.
 *
 * A FIXED grammar, parsed by `lib/graphCommands.ts` into the SAME `GraphAction`
 * values the visual controls dispatch. There is no interpreter here: this file
 * reads text, hands it to the parser, and renders what came back. It cannot
 * execute anything — no `eval`, no `Function`, no dynamic import, no shell, no
 * filesystem, no network.
 *
 * It is NOT a chat: the results area is a compact, bounded, ephemeral list of
 * what each command did. The history lives in React state for the life of the
 * mounted surface only — never localStorage, never sessionStorage, never logged,
 * never sent anywhere.
 *
 * Announcements reuse the surface's ONE polite live region (owned by
 * MemoryGraphCard). Nothing here creates a second one.
 */
import { useCallback, useId, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { CircleHelp, CornerDownRight, X } from '../../components/icons';
import {
  MAX_COMMAND_LENGTH,
  suggestCommands,
  suggestionActionSentence,
  type CommandSuggestion,
  type GraphCommandHistoryEntry,
  type GraphSuggestedCommand,
} from '../../lib/graphCommands';
import type { GraphIndex } from '../../lib/graphModel';
import type { GraphHelpExpand } from './GraphHelp';

/** How many past results stay visible. The area is a compact log, not a feed. */
const VISIBLE_HISTORY = 5;

interface GraphCommandBarProps {
  index: GraphIndex;
  history: GraphCommandHistoryEntry[];
  /**
   * P36V.1 G — the bounded, context-aware suggestion set, built by
   * `suggestedGraphCommands` from the SAME grammar and the SAME live state the
   * bar itself runs against. This component renders them and inserts them; it
   * decides nothing about which ones exist.
   */
  suggestions: GraphSuggestedCommand[];
  onRun: (raw: string) => void;
  onClearHistory: () => void;
  onOpenHelp: (expand?: GraphHelpExpand) => void;
}

export function GraphCommandBar({
  index,
  history,
  suggestions: suggested,
  onRun,
  onClearHistory,
  onOpenHelp,
}: GraphCommandBarProps) {
  const [text, setText] = useState('');
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(-1);
  // Ephemeral recall cursor over the commands typed in THIS mounted session.
  const [recall, setRecall] = useState(-1);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const listId = useId();
  const suggestId = useId();
  const optionId = (i: number) => `${listId}-opt-${i}`;

  const suggestions = useMemo<CommandSuggestion[]>(
    () => (open ? suggestCommands(text, index) : []),
    [open, text, index],
  );

  const typedCommands = useMemo(
    () => history.filter((h) => h.origin === 'command').map((h) => h.command),
    [history],
  );

  const accept = useCallback((s: CommandSuggestion) => {
    setText(s.value);
    setActiveIdx(-1);
    setOpen(!s.value.endsWith(' ') ? false : true);
    inputRef.current?.focus();
  }, []);

  const run = useCallback(() => {
    const raw = text;
    if (raw.trim() === '') return;
    onRun(raw);
    setText('');
    setOpen(false);
    setActiveIdx(-1);
    setRecall(-1);
  }, [text, onRun]);

  /**
   * Pressing a suggestion.
   *
   * INSERT is the default and the only path for anything that filters, focuses,
   * selects or routes: the exact canonical command lands in the input and the
   * user still has to press Run. `run` is reachable only for a command the
   * model's own allowlist has already vetted as viewport-only, and even then it
   * goes through `onRun` → `parseGraphCommand` → the one reducer, exactly like a
   * typed line. `help` opens a dialog and touches no graph state.
   */
  const applySuggestion = useCallback(
    (s: GraphSuggestedCommand) => {
      if (s.effect === 'help') {
        onOpenHelp('technical');
        return;
      }
      if (!s.command) return;
      if (s.effect === 'run') {
        onRun(s.command);
        return;
      }
      setText(s.command);
      // An unfinished command opens the completion list on the token it is
      // missing, so the destination comes from the index rather than a guess.
      setOpen(s.partial);
      setActiveIdx(-1);
      setRecall(-1);
      inputRef.current?.focus();
    },
    [onOpenHelp, onRun],
  );

  function onKeyDown(e: ReactKeyboardEvent<HTMLInputElement>) {
    // While the completion list is open the arrows move through it. With the
    // list closed they walk the ephemeral history — one rule, no overlap.
    if (open && suggestions.length > 0 && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      e.preventDefault();
      const delta = e.key === 'ArrowDown' ? 1 : -1;
      const n = suggestions.length;
      setActiveIdx((i) => (i === -1 ? (delta === 1 ? 0 : n - 1) : (i + delta + n) % n));
      return;
    }
    if (!open && (e.key === 'ArrowUp' || e.key === 'ArrowDown') && typedCommands.length > 0) {
      e.preventDefault();
      const n = typedCommands.length;
      const next = e.key === 'ArrowUp' ? Math.min(recall + 1, n - 1) : Math.max(recall - 1, -1);
      setRecall(next);
      setText(next === -1 ? '' : typedCommands[n - 1 - next]);
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      if (open && activeIdx >= 0 && suggestions[activeIdx]) accept(suggestions[activeIdx]);
      else run();
      return;
    }
    if (e.key === 'Tab' && open && activeIdx >= 0 && suggestions[activeIdx]) {
      e.preventDefault();
      accept(suggestions[activeIdx]);
      return;
    }
    if (e.key === 'Escape') {
      e.stopPropagation();
      if (open) {
        setOpen(false);
        setActiveIdx(-1);
      } else if (text !== '') {
        setText('');
      }
    }
  }

  const shown = history.slice(-VISIBLE_HISTORY).reverse();

  return (
    <div className="graph-cmd">
      <div className="graph-cmd-row">
        <label className="graph-cmd-field">
          <span className="memory-graph-visually-hidden">Graph command</span>
          <span className="graph-cmd-prompt mono" aria-hidden="true">
            &gt;
          </span>
          <input
            ref={inputRef}
            type="text"
            className="graph-cmd-input mono"
            role="combobox"
            aria-expanded={open && suggestions.length > 0}
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={
              open && activeIdx >= 0 && suggestions[activeIdx] ? optionId(activeIdx) : undefined
            }
            aria-describedby={`${listId}-help`}
            autoComplete="off"
            spellCheck={false}
            maxLength={MAX_COMMAND_LENGTH}
            placeholder="find export · neighbors <node> depth 2 · path a -> b · help"
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setOpen(true);
              setActiveIdx(-1);
              setRecall(-1);
            }}
            onKeyDown={onKeyDown}
            onBlur={() => window.setTimeout(() => setOpen(false), 120)}
          />
        </label>
        <button type="button" className="btn btn-secondary graph-cmd-run" onClick={run}>
          <CornerDownRight size={14} strokeWidth={2} aria-hidden="true" />
          Run
        </button>
        <button
          type="button"
          className="graph-cmd-help"
          onClick={() => onOpenHelp('commands')}
          aria-label="Graph command syntax"
        >
          <CircleHelp size={13} strokeWidth={2} aria-hidden="true" />
          Syntax
        </button>
      </div>

      <p className="graph-cmd-hint" id={`${listId}-help`}>
        A fixed set of commands over this projection — nothing is executed and no record is changed.
        Type <span className="mono">help</span> for the full list; ↑ recalls what you typed here.
      </p>

      {open && suggestions.length > 0 && (
        <ul className="graph-cmd-suggestions" role="listbox" id={listId} aria-label="Command completions">
          {suggestions.map((s, i) => (
            <li
              key={s.value}
              id={optionId(i)}
              role="option"
              aria-selected={i === activeIdx}
              className={`graph-cmd-suggestion${i === activeIdx ? ' active' : ''}`}
            >
              <button
                type="button"
                className="graph-cmd-suggestion-btn"
                tabIndex={-1}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => accept(s)}
              >
                <span className="mono">{s.value.trim()}</span>
                <span className="graph-cmd-suggestion-hint">{s.hint}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* P36V.1 G — Suggested Commands. Rendered AFTER the completion list in
          document order on purpose: the list is absolutely positioned at its
          static position, so putting this block above it would push the
          completions down the page, away from the input they complete. */}
      {suggested.length > 0 && (
        <div className="graph-cmd-suggest">
          <p className="graph-cmd-suggest-title" id={suggestId}>
            Suggested Commands
          </p>
          <ul className="graph-cmd-suggest-list" aria-labelledby={suggestId}>
            {suggested.map((s) => (
              <li key={s.id}>
                <button
                  type="button"
                  className={`graph-cmd-suggest-btn${s.effect === 'insert' ? '' : ' is-view'}`}
                  /* The insert / run distinction is in the accessible NAME, not
                     only in the visual tag — a screen-reader user must know
                     whether a press fills the bar or acts immediately. */
                  aria-label={`${s.label} — ${suggestionActionSentence(s)}`}
                  title={s.detail}
                  onClick={() => applySuggestion(s)}
                >
                  <span className="graph-cmd-suggest-label">{s.label}</span>
                  <span className="graph-cmd-suggest-foot">
                    <span className="graph-cmd-suggest-cmd mono" aria-hidden="true">
                      {s.command === null ? 'about this graph' : s.command.trim()}
                      {s.partial ? ' …' : ''}
                    </span>
                    {/* A WORD, never a colour or an icon alone. */}
                    <span className="graph-cmd-suggest-mode">
                      {s.effect === 'insert' ? 'fills the bar' : s.effect === 'run' ? 'runs now' : 'opens help'}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
          <p className="graph-cmd-suggest-note">
            Clicking a suggestion puts its exact command in the bar above; you press Run. Only{' '}
            <span className="graph-cmd-suggest-mode">runs now</span> acts on the click, and only for
            a view action that reframes the canvas.
          </p>
        </div>
      )}

      {shown.length > 0 && (
        <div className="graph-cmd-history">
          <div className="graph-cmd-history-head">
            <span className="graph-cmd-history-title">
              Recent commands — this session only, never saved
            </span>
            <button type="button" className="graph-cmd-history-clear" onClick={onClearHistory}>
              <X size={12} strokeWidth={2} aria-hidden="true" />
              Clear
            </button>
          </div>
          <ol className="graph-cmd-history-list">
            {shown.map((entry) => (
              <li key={entry.id} className={`graph-cmd-history-item is-${entry.status}`}>
                <span className="graph-cmd-history-cmd mono">
                  {entry.origin === 'assistant' ? 'assistant · ' : ''}
                  {entry.command}
                </span>
                {entry.outcome && <span className="graph-cmd-history-out">{entry.outcome}</span>}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
