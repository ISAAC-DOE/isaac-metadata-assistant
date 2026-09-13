/*
 * FOLDERS, DERIVED FROM THE EXPERIMENT LIST AND FROM NOTHING ELSE.
 *
 * There is no folder entity on the server and no folder endpoint on the client.
 * Every function here is a pure projection of one `ApiExperimentSummary[]`, which
 * means the folder tree a reader sees is, by construction, exactly the set of
 * paths their experiments name. A folder cannot be stale, cannot be orphaned,
 * cannot disagree with its members, and cannot exist while empty — not because
 * something reconciles it, but because there is nothing to reconcile.
 *
 * THE FOUR THINGS THIS MODULE DELIBERATELY CANNOT DO, listed because a UI built
 * on it must not imply any of them:
 *
 *   * CREATE AN EMPTY FOLDER. A path materialises when an experiment is filed
 *     under it. "New folder" as a standalone act does not exist, and a control
 *     offering one would be offering a button with nothing behind it.
 *   * RENAME A FOLDER. Renaming a path means rewriting every member — N
 *     independent versioned writes with no transaction around them. Half-renamed
 *     is a reachable state, so the capability is not offered rather than offered
 *     unsafely.
 *   * OWN OR SHARE A FOLDER. That needs a trusted authentication boundary this
 *     deployment does not have.
 *   * DELETE A FOLDER. Moving the last member out is what ends a path; there is
 *     no separate act, and no confirmation dialog should suggest there is.
 *
 * SEPARATOR PARITY IS LOAD-BEARING. `FOLDER_SEPARATOR` here must equal
 * `workspace.FOLDER_SEPARATOR` on the server, because the server joins with it
 * and this module splits on it. A mismatch would not error — it would silently
 * render every nested path as one flat name. `__tests__/experiment-library.test.ts`
 * pins the literal against the value the server actually returns for a nested
 * path, so the two cannot drift apart quietly.
 */

import type { ApiExperimentSummary } from './types';

/** Must equal `workspace.FOLDER_SEPARATOR`. See the separator-parity note above. */
export const FOLDER_SEPARATOR = '/';

/** The sentinel for "not in any folder". The server sends `''` for this. */
export const UNFILED = '';

export interface FolderNode {
  /** The full path, e.g. `Cu K-edge/2026 campaign`. */
  path: string;
  /** The last segment — what a breadcrumb or a row shows. */
  name: string;
  /** Immediate child folder paths, sorted. */
  children: string[];
  /**
   * Experiments filed at EXACTLY this path. A record in `a/b` is not counted in
   * `a` — see `totalCount` for the other question, and note that the two being
   * separate is the point: a folder heading that silently included descendants
   * would make "3 experiments" and a list of one row disagree on screen.
   */
  directCount: number;
  /** Experiments at this path or any path beneath it. */
  totalCount: number;
}

/**
 * Split a stored path into its segments. `''` yields `[]`.
 *
 * TOTAL BY CONSTRUCTION, and that is not defensive padding. The first version took
 * `path: string` and called `.split` on it; a row whose `folder` was not a string
 * threw `TypeError: path.split is not a function` and — because this app has no
 * ErrorBoundary anywhere — would have taken the whole Library down. Found by the
 * test that asserts exactly this, after `lib/library.ts` had been hardened and this
 * module had not: **hardening one of two modules that read the same field is how a
 * response-shape crash survives a fix for itself.**
 *
 * A non-string reads as UNFILED, which is `_as_str`'s policy server-side and the
 * bucket a missing key was already in. Nothing is coerced: `String(7)` would
 * manufacture a folder called `7` that no scientist named.
 */
export function folderSegments(path: unknown): string[] {
  if (typeof path !== 'string' || path === '') return [];
  return path.split(FOLDER_SEPARATOR).filter((s) => s.length > 0);
}

/**
 * Every ancestor path of `path`, shallowest first, EXCLUDING `path` itself.
 * `'a/b/c'` → `['a', 'a/b']`. `''` → `[]`.
 */
export function ancestorPaths(path: string): string[] {
  const segments = folderSegments(path);
  const out: string[] = [];
  for (let i = 1; i < segments.length; i += 1) {
    out.push(segments.slice(0, i).join(FOLDER_SEPARATOR));
  }
  return out;
}

/**
 * The breadcrumb trail for `path`: every ancestor AND the path itself, shallowest
 * first, each with the name to render. `''` yields `[]` — the caller renders its
 * own root crumb, because what the root is called is a product decision (`All
 * experiments`) and not a fact about the data.
 */
export function folderBreadcrumbs(path: string): { path: string; name: string }[] {
  const segments = folderSegments(path);
  return segments.map((name, i) => ({
    path: segments.slice(0, i + 1).join(FOLDER_SEPARATOR),
    name,
  }));
}

/**
 * The whole folder tree the given experiments materialise.
 *
 * INTERMEDIATE PATHS ARE SYNTHESISED, and that is not the same as inventing a
 * folder. A record filed at `a/b/c` with nothing at `a` or `a/b` means those two
 * paths ARE named — by that record's own path — so they are real levels of a real
 * path, with `directCount: 0` and a non-zero `totalCount`. The alternative would
 * be a breadcrumb trail with holes in it.
 *
 * Returned as a `Map` keyed by full path, so a caller can look up one node
 * without walking. Children and roots are sorted by name, case-insensitively and
 * numerically aware, so `Run 2` precedes `Run 10`.
 */
export function buildFolderTree(summaries: ApiExperimentSummary[]): Map<string, FolderNode> {
  const nodes = new Map<string, FolderNode>();

  const ensure = (path: string): FolderNode => {
    const existing = nodes.get(path);
    if (existing) return existing;
    const segments = folderSegments(path);
    const node: FolderNode = {
      path,
      name: segments[segments.length - 1] ?? '',
      children: [],
      directCount: 0,
      totalCount: 0,
    };
    nodes.set(path, node);
    return node;
  };

  for (const summary of summaries) {
    // READ THROUGH `folderSegments`, WHICH IS TOTAL, rather than off the field. A
    // row whose `folder` is not a string reads as unfiled — the same policy the
    // server applies to a wrong-typed persisted value, and for the same reason: a
    // malformed value already served must be READ, not allowed to crash a reader
    // who did nothing wrong. Re-joining the normalised segments also means a value
    // carrying stray separators projects onto the same node its own breadcrumb
    // would, so the tree and the trail cannot disagree.
    const path = folderSegments(summary.folder).join(FOLDER_SEPARATOR);
    if (!path) continue; // unfiled: materialises no folder, by design
    ensure(path).directCount += 1;
    // Every level of this path, itself included, gains one toward its total.
    for (const ancestor of [...ancestorPaths(path), path]) {
      ensure(ancestor).totalCount += 1;
    }
  }

  // Parent/child wiring is a second pass BECAUSE `ensure` may have created a
  // parent after its child. Doing it inline would drop the edge whenever a deeper
  // path was seen first, which is a list-order dependency and therefore a bug
  // that only some workspaces would show.
  for (const path of nodes.keys()) {
    const segments = folderSegments(path);
    if (segments.length < 2) continue;
    const parent = segments.slice(0, -1).join(FOLDER_SEPARATOR);
    ensure(parent).children.push(path);
  }
  for (const node of nodes.values()) {
    node.children.sort((a, b) => compareNames(nodes.get(a)?.name ?? a, nodes.get(b)?.name ?? b));
  }
  return nodes;
}

/** The top-level folder paths of a tree, sorted for display. */
export function rootFolders(tree: Map<string, FolderNode>): string[] {
  return [...tree.keys()]
    .filter((path) => folderSegments(path).length === 1)
    .sort((a, b) => compareNames(a, b));
}

/**
 * Is `candidate` inside `folder` (or equal to it)?
 *
 * SEGMENT-AWARE, NOT `startsWith`. A naive prefix test puts `Cu K-edge 2` inside
 * `Cu K-edge`, which would show a reader rows that are not there — so the
 * comparison requires the separator to follow.
 */
export function isWithinFolder(candidate: unknown, folder: string): boolean {
  if (!folder) return true; // the root contains everything, filed or not
  // A non-string candidate is UNFILED, so it is inside no folder but the root —
  // which the branch above has already answered. Guarded here rather than trusted,
  // for the reason `folderSegments` records.
  if (typeof candidate !== 'string') return false;
  if (candidate === folder) return true;
  return candidate.startsWith(folder + FOLDER_SEPARATOR);
}

/**
 * Natural-ish name ordering: case-insensitive, and numerically aware so `Run 2`
 * sorts before `Run 10`. `Intl.Collator` with `numeric` does both and is
 * deterministic for a fixed locale list; `undefined` locales would make the order
 * depend on the reader's machine, which is exactly the non-determinism
 * `formatCreatedDate` avoids for dates.
 */
const NAME_COLLATOR = new Intl.Collator('en', { numeric: true, sensitivity: 'base' });

export function compareNames(a: string, b: string): number {
  return NAME_COLLATOR.compare(a, b);
}
