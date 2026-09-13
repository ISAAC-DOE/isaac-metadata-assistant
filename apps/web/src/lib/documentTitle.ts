/*
 * WCAG 2.4.2 *Page Titled* — the one success criterion no route in this SPA has
 * ever satisfied.
 *
 * ── WHAT WAS MEASURED, AND WHEN ─────────────────────────────────────────────
 *
 * Measured 2026-09-12 by the I-1 slice, re-measured by the orchestrator, and
 * re-measured again 2026-09-13 before this file was written:
 * `grep -ran 'document\.title\|useDocumentTitle' apps/web/src/` returned **0
 * hits**, and `index.html:7` is a static `<title>ISAAC Metadata
 * Assistant</title>`. So every one of the eleven routes — My Experiments, a
 * record's four workspaces, Complete, Evidence, Export Readiness, Project
 * Memory, Governance, Statistics, Settings — announced the same eight words to
 * a screen reader, to a browser tab strip, to a bookmark and to a window
 * switcher. The `-a` flag is not decoration: §11's durable rule is that a
 * zero-hit sweep of this tree without it is not a measurement at all.
 *
 * ── WHY THIS IS A TITLE AND NOT A SECOND HEADING ────────────────────────────
 *
 * The proportionate fix is a per-route `document.title`, NOT another `<h1>`.
 * `e2e/specs/structure.spec.ts` holds every surface to exactly one `<h1>` and is
 * right to: a second one would break the document outline to repair a
 * different criterion. Nothing in this file renders, and no heading moves.
 *
 * ── WHY THE STRINGS ARE NOT AUTHORED HERE ───────────────────────────────────
 *
 * Every segment is read from `LABELS` or from `RECORD_WORKSPACES` — the same
 * two sources the visible headings and the sidebar read. A title authored here
 * would be a second name for a destination that already has one, which is the
 * defect class `screenExport` and the retired `stepDraft…stepAudit` vocabulary
 * both exist to record. Rename a screen and its title follows; they cannot
 * drift.
 *
 * ── WHAT IS DELIBERATELY NOT CLAIMED ────────────────────────────────────────
 *
 * A record's title is known only once its bundle has loaded. Until then the
 * title names the WORKSPACE and nothing else — it does not guess the record's
 * name, show its id as a stand-in, or say "Loading". `composeDocumentTitle`
 * drops empty segments rather than emitting a separator with nothing after it.
 */

import { RECORD_WORKSPACES } from '../components/RecordWorkspaceNav';
import { LABELS } from './labels';
import { resolveRecordView, type RecordViewId } from './routes';

/**
 * The site name, and the ONE authored string in this module.
 *
 * It is the same eight words `index.html` already carries, so the first paint
 * (before React mounts) and every subsequent route agree on the suffix. Keeping
 * them equal is asserted by `__tests__/document-title.test.tsx`, which reads
 * `index.html` rather than trusting this constant.
 */
export const APP_TITLE = 'ISAAC Metadata Assistant';

/** The separator. `·` is the same one the record `<h1>` and the mode chip use. */
const SEP = ' · ';

/**
 * Page name first, site name last — the ordering WCAG's own technique G88
 * illustrates and the one a truncated tab strip degrades best under: the
 * segment that distinguishes this page from the last one survives truncation.
 *
 * Empty, whitespace-only and nullish segments are dropped, so a caller that
 * does not yet know a record's title emits `"Record Fields · ISAAC Metadata
 * Assistant"` rather than `"Record Fields ·  · ISAAC Metadata Assistant"`.
 */
export function composeDocumentTitle(
  segments: readonly (string | null | undefined)[],
): string {
  const kept = segments
    .map((s) => (s ?? '').trim())
    .filter((s) => s.length > 0);
  return [...kept, APP_TITLE].join(SEP);
}

/** The workspace label, read from the one registry the sidebar renders from. */
export function recordWorkspaceTitleSegment(view: RecordViewId): string {
  return RECORD_WORKSPACES.find((w) => w.id === view)?.label ?? view;
}

/**
 * THE ROUTE-DERIVED TITLE — the floor, applied on every navigation.
 *
 * It is deliberately computed from `pathname` + `search` alone, with no screen
 * state, for one reason: a per-screen hook that a screen FORGETS to call leaves
 * the previous route's title in the tab strip, which is a worse defect than the
 * static title it replaced (a stale title actively misidentifies the page). A
 * central resolver cannot be forgotten, because it is not the screen's to
 * remember.
 *
 * Screens with richer honest truth — today only the record screen, which knows
 * its record's name once loaded — REFINE this through `useDocumentTitle`. The
 * refinement's ordering guarantee, and the trap it avoids, are documented on
 * that hook.
 *
 * `null` means "this route resolves elsewhere" (`/` and the `*` fallback both
 * `<Navigate replace>`), and the caller leaves the title alone rather than
 * writing a title for a URL the reader is not on.
 */
export function routeDocumentTitle(pathname: string, search: string): string | null {
  const path = pathname.replace(/\/+$/, '') || '/';

  // Record sub-surfaces first: they are prefixes of `/record/:id`.
  if (/^\/record\/[^/]+\/complete$/.test(path)) {
    return composeDocumentTitle([LABELS.screenComplete]);
  }
  if (/^\/record\/[^/]+\/evidence$/.test(path)) {
    return composeDocumentTitle([LABELS.screenEvidence]);
  }
  if (/^\/record\/[^/]+\/export$/.test(path)) {
    return composeDocumentTitle([LABELS.screenExport]);
  }
  if (/^\/record\/[^/]+$/.test(path)) {
    // `resolveRecordView` is the SAME function `RecordWorkbench` resolves its
    // own `activeView` with — not a reimplementation of it. A bare
    // `/record/<id>` is therefore titled `Record Fields`, and a run deep link
    // carrying only `?run=<id>` is titled `Runs`, both because that is the
    // workspace actually rendered. Getting this wrong would put a false claim
    // about the page in the one place a reader cannot see the page to check it.
    return composeDocumentTitle([recordWorkspaceTitleSegment(resolveRecordView(search))]);
  }

  switch (path) {
    case '/experiments':
      return composeDocumentTitle([LABELS.screenExperiments]);
    case '/load':
      return composeDocumentTitle([LABELS.screenLoad]);
    case '/imports':
      // `navImports`, the SAME string the nav item and the page `<h1>` read.
      // A title authored here would be a second name for a destination that
      // already has one — the defect this module's header records.
      return composeDocumentTitle([LABELS.navImports]);
    case '/memory':
      return composeDocumentTitle([LABELS.navMemory]);
    case '/governance':
      return composeDocumentTitle([LABELS.navGovernance]);
    case '/statistics':
      return composeDocumentTitle([LABELS.navStatistics]);
    case '/settings':
      return composeDocumentTitle([LABELS.navSettings]);
    default:
      return null;
  }
}
