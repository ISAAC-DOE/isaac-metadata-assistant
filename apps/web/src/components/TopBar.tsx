import './chrome.css';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AudioWaveform, Check, Copy, Shield, ChevronRight } from './icons';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import { StatusChip } from './StatusChip';
import { HelpPanel } from './HelpPanel';
import { SearchDialog } from './SearchDialog';
import { useHealth } from '../lib/useHealth';
import { useTutorialState } from '../lib/tutorialController';
import type { ChipKind } from '../lib/status';
import type { ApiHealth } from '../lib/types';

/**
 * An UNEXPECTED `health.mode`, capitalized for display, or `null` when the mode is
 * the expected one (or unknown).
 *
 * `synthetic-only` is the only mode this build boots in (`runtime_mode.py` refuses
 * to start in `real`), and a missing/failed health check tells us nothing. A real
 * value we did not anticipate must be surfaced, visibly and distinctly, rather than
 * masked: this chip is the only surface in the app that reports it.
 *
 * The MODE'S OWN NAME is untouched by any label change here: `synthetic-only` is
 * what `/api/health` reports, what `runtime_mode.py` enforces, and what the machine
 * contract carries. Only reader-facing words are decided in this file.
 */
function anomalousMode(mode: string | undefined): string | null {
  if (!mode || mode === 'synthetic-only') return null;
  return mode.charAt(0).toUpperCase() + mode.slice(1);
}

/**
 * The chip's text, or `null` when there is no chip.
 *
 * ~~Rendered in every scope, with a ~90-word governance disclosure in its accessible
 * name and a hover/focus popover.~~ RETIRED 2026-11-02 at the owner's direction
 * (standing disclaimers removed). The chip now renders only when it says something
 * the reader needs: inside a worked-example session (`Worked Example`), or when
 * `health.mode` is anomalous, which outranks the scope name so it is never masked.
 * On the ordinary scope there is no chip at all.
 *
 * Never renders a host, database name, user, secret name, connection detail, record
 * count, or any record content — the only inputs are `mode` and whether a session
 * is open (`db-recon-truthfulness.test.tsx` scans every health state for that).
 */
function chipText(health: ApiHealth | undefined, inExampleSession: boolean): string | null {
  const anomaly = anomalousMode(health?.mode);
  if (anomaly !== null) return anomaly;
  return inExampleSession ? LABELS.modeWorkedExample : null;
}

// Driven by the shared, cached health (`mode`) and the tutorial store (which scope
// is open). No extra fetch and no polling. The visible text is the whole name: no
// `aria-label`, so it cannot drift from what a sighted reader sees.
function WorkspaceChip() {
  const health = useHealth();
  // Read from the tutorial store rather than from health: `/api/health`'s `mode`
  // describes the DEPLOYMENT and is unchanged by a session.
  const inExampleSession = useTutorialState().sessionId !== null;
  const text = chipText(health, inExampleSession);
  if (text === null) return null;
  return (
    <span className="mode-chip">
      <Shield size={13} strokeWidth={2} aria-hidden="true" />
      {text}
    </span>
  );
}

/** A ULID — 26 Crockford base-32 characters, the id every record carries. */
const ULID_IN_TEXT = /\b[0-9A-HJKMNP-TV-Z]{26}\b/;

/**
 * The visible form of an id: its first six and last four characters around an
 * ellipsis, so a reader can still tell two records apart at a glance and nothing
 * claims to BE the whole id. Exported for the test that pins the rule.
 */
export function abbreviateId(id: string): string {
  return `${id.slice(0, 6)}…${id.slice(-4)}`;
}

/**
 * THE RECORD'S ID IN THE TOP BAR — SECONDARY, AND ONE PRESS FROM COPIED.
 *
 * WHAT CHANGED (2026-10-12 clutter audit). The bar printed the full 26-character
 * ULID — or `<ULID>.json` / `<ULID>.evidence.json` / `draft · <ULID>` — in mono
 * beside the record's name, on every record surface. The NAME tells a scientist
 * which record this is; the id is what they need when they quote it or look it
 * up. So the name stays primary and the id becomes a compact control: it shows
 * the id head…tail (`docs/ui-handoff/design-system.md`: "Truncate mono
 * identifiers gracefully … with a reveal/copy affordance; never silently drop
 * characters") and copies the FULL ID on press.
 *
 * IT COPIES THE ID AND NOTHING ELSE (corrected in review, 2026-10-18). The first
 * version copied the whole display string, so on Complete/Export the clipboard
 * held "draft · 01M5…" and on an exported Evidence screen "<ULID>.evidence.json"
 * — not the identifier the control is named for. The matched ULID is what is
 * copied, what the accessible name states, and what the tooltip shows; the
 * surrounding filename stays available as the tooltip's second line.
 *
 * THE OUTCOME IS ANNOUNCED BY A REGION THAT EXISTS BEFORE THE PRESS. A
 * `role="status"` region inserted together with its text is not reliably
 * announced, so the region is mounted with the control and only its TEXT changes.
 * When copying fails, the full id is REVEALED inline as selectable text — a
 * keyboard or touch reader cannot open a hover tooltip, so the fallback must not
 * depend on one.
 *
 * A filename with no ULID in it (a short id like `demo`, or a data file's own
 * name) is rendered exactly as before: there is nothing to abbreviate, and a copy
 * control for a word a reader can already read in full would be clutter.
 *
 * It keeps the `record-file` class, so the phone band in `chrome.css` that drops
 * the file crumb still drops it.
 */
function RecordFile({ filename }: { filename: string }) {
  const [copied, setCopied] = useState<'idle' | 'copied' | 'failed'>('idle');
  const match = ULID_IN_TEXT.exec(filename);
  const id = match?.[0] ?? null;
  useEffect(() => {
    if (copied !== 'copied') return;
    const timer = window.setTimeout(() => setCopied('idle'), 2000);
    return () => window.clearTimeout(timer);
  }, [copied]);

  if (id === null) return <span className="record-file">{filename}</span>;

  const copy = () => {
    const clipboard = typeof navigator === 'undefined' ? undefined : navigator.clipboard;
    if (!clipboard?.writeText) {
      setCopied('failed');
      return;
    }
    clipboard.writeText(id).then(
      () => setCopied('copied'),
      () => setCopied('failed'),
    );
  };

  return (
    <span className="record-file record-file-wrap">
      <button
        type="button"
        className="record-file-copy"
        title={filename === id ? id : `${id}\n${filename}`}
        aria-label={`${LABELS.actionCopyRecordId} ${id}`}
        onClick={copy}
      >
        <span aria-hidden="true">{abbreviateId(id)}</span>
        {copied === 'copied' ? (
          <Check size={12} strokeWidth={2.4} aria-hidden="true" />
        ) : (
          <Copy size={12} strokeWidth={2} aria-hidden="true" />
        )}
      </button>
      {copied === 'failed' && <span className="record-file-full">{id}</span>}
      <span className="sr-only" role="status">
        {copied === 'copied'
          ? LABELS.recordIdCopied
          : copied === 'failed'
            ? LABELS.recordIdCopyFailed
            : ''}
      </span>
    </span>
  );
}

// The identity mark doubles as the home crumb — a real link back to the queue,
// so no surface is a dead end from the top-left.
function Brand() {
  return (
    <Link to={ROUTES.experiments} className="brand" aria-label={`${LABELS.brand} — ${LABELS.navExperiments}`}>
      <span className="brand-tile" aria-hidden="true">
        <AudioWaveform size={17} strokeWidth={2.2} />
      </span>
      {LABELS.brand}
    </Link>
  );
}

interface TopBarProps {
  /**
   * ~~`'breadcrumb'`~~ — RETIRED 2026-10-12. It was the chrome of `/load` and the
   * not-found page: a single leaf crumb, no left navigation and no Help, so a
   * reader who reached either had the brand mark as the only way out and no help
   * at all. Both now carry `home` and the primary navigation, which is the same
   * chrome as every other screen; no caller of this variant remained.
   */
  variant: 'home' | 'record';
  title?: string;
  filename?: string;
  stateChip?: ChipKind;
  /** Record id — when present on a record sub-surface, the record title becomes a
   * breadcrumb link back to Review Record (/record/:id). */
  recordId?: string;
  /** Leaf crumb naming the current sub-surface (e.g. "Evidence & File Preview").
   * Rendered as the current, non-link crumb after the linked record title. */
  surface?: string;
}

/** Identity, context/breadcrumb, the mode chip (worked-example session or an
 * anomalous mode only), Help, and the ⌘K search command palette. Search is real
 * (P26): the SearchDialog affordance is mounted on every variant so ⌘K opens the
 * API-backed palette from any surface. */
export function TopBar({ variant, title, filename, stateChip, recordId, surface }: TopBarProps) {
  return (
    <header className="topbar">
      <Brand />

      {variant === 'home' && (
        <>
          <div className="topbar-spacer" />
          <div className="topbar-right">
            <SearchDialog />
            <WorkspaceChip />
            <HelpPanel />
          </div>
        </>
      )}

      {variant === 'record' && (
        <>
          <div className="record-context">
            {/*
              QA-017 — the record breadcrumb had exactly one segment (the page's own
              name), with the ancestor reachable only by clicking `Brand`, which reads
              as a logo rather than a crumb. This adds `My Experiments` as its own
              LINKED crumb, ahead of the title, on every `variant="record"` render —
              whether or not the caller passes `recordId` — because the not-loaded and
              loaded Review Record screens are exactly the two callers that omit it
              (`RecordWorkbench.tsx`), and both are the "one segment" case.

              HIDDEN BELOW 1024px, DELIBERATELY, not as an oversight. The narrow-width
              layout of `.record-context` above is the product of measured, exact-pixel
              fixes (C1/I4/LAYOUT-01/LAYOUT-02) that this file documents in detail; adding
              width here would re-open exactly the overflow class those fixes closed,
              and re-measuring the whole band was out of this slice's scope. `.record-
              ancestor-link` is hidden in the same `@media (max-width: 1024px)` block
              that already hides this crumb's decorative `<svg>` separators, so the
              narrow-width layout is BYTE-IDENTICAL to before this change. The `Brand`
              logo link remains the way back at every width. */}
            {/*
              `aria-label` OPENS WITH THE VISIBLE TEXT (WCAG 2.5.3) AND THEN
              DISAMBIGUATES — found necessary, not stylistic: `FetchStates.tsx`'s
              error panel renders its own "the one affordance offered" link with
              the identical visible text and NO `aria-label`, so its accessible
              name is the bare `LABELS.navExperiments` string. On the record
              screen's own not-found/no-session error state that link and this
              crumb are both mounted, and `getByRole('link', { name:
              LABELS.navExperiments })` — an existing, unmodified test —
              correctly failed on "found multiple elements" until this crumb's
              name became distinct.
            */}
            <Link
              to={ROUTES.experiments}
              className="record-ancestor-link"
              aria-label={`${LABELS.navExperiments} breadcrumb`}
            >
              {LABELS.navExperiments}
            </Link>
            <ChevronRight size={14} strokeWidth={2} aria-hidden="true" style={{ color: 'var(--text-disabled)' }} />
            {recordId ? (
              // Sub-surface: the record title is an ancestor crumb linking back to
              // Review Record. The current sub-surface is the leaf below.
              <Link to={ROUTES.record(recordId)} className="record-title record-title-link">
                {title}
              </Link>
            ) : (
              // No sub-surface context: this title IS the current page (leaf).
              <span className="record-title" aria-current="page">
                {title}
              </span>
            )}
            {surface && (
              <>
                <ChevronRight
                  size={14}
                  strokeWidth={2}
                  aria-hidden="true"
                  style={{ color: 'var(--text-disabled)' }}
                />
                <span className="record-surface" aria-current="page">
                  {surface}
                </span>
              </>
            )}
            {stateChip && <StatusChip kind={stateChip} />}
            {filename && <RecordFile filename={filename} />}
          </div>
          <div className="topbar-spacer" />
          <div className="topbar-right">
            <SearchDialog />
            <WorkspaceChip />
            {/* Help was mounted on the `home` variant ONLY, so it was unreachable on
                every record surface — exactly where a first-time scientist is when the
                questions it answers arise ("what does Review Evidence mean?", "why did
                export refuse?"). Same trigger, same panel, same `topbar-right` slot as
                `home`: no second help surface and no change to this bar's structure.
                `breadcrumb` is deliberately left without it — that variant is the
                approval-gated on-ramp, whose own copy is the disclosure a reader needs
                there. Pinned by `__tests__/help-claim-parity.test.tsx` §4. */}
            <HelpPanel />
          </div>
        </>
      )}
    </header>
  );
}
