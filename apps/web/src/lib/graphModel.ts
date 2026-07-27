/*
 * graphModel — the ONE canonical model behind the Project Memory graph.
 *
 * P36R Slice 3 owns it; Slice 4 (deterministic command bar) and Slice 5
 * (Assistant graph intents) are additional FRONT-ENDS over this same module.
 * That is why it is deliberately pure: no React, no fetch, no DOM, no time, no
 * randomness. Every state mutation the UI can perform is a `GraphAction`, and
 * `applyGraphAction` is the single code path that applies one — so a pointer
 * click, a typed command and an Assistant proposal can never drift apart.
 *
 * Honesty rules encoded here, not just in copy:
 *  - Edges are NEVER invented. The only edge source is the payload's own
 *    `edges[]` (built by the backend from each file's `related.files[]`), and
 *    an edge whose endpoints are not both present as nodes is dropped, never
 *    repaired.
 *  - Identity is NEVER guessed. `resolveNode` returns `found` only when a tier
 *    matches exactly one node; otherwise it returns a bounded candidate list or
 *    an honest `not_found`.
 *  - `shortestPath` returns `null` when no path exists — it never approximates.
 *  - Layout is deterministic: the same payload always yields byte-identical
 *    coordinates (seeded spiral + a FIXED iteration count, no rAF, no clock).
 */
import type {
  ApiMemoryGraphEdge,
  ApiMemoryGraphNode,
  ApiMemoryGraphResponse,
} from './types';

// ----------------------------------------------------------------- constants

/** Hard cap on simultaneously rendered nodes. Reported honestly when it bites.
 *  The live projection is 220 nodes, so it is not binding today — it exists so
 *  a larger future snapshot degrades visibly instead of freezing the browser. */
export const MAX_RENDER_NODES = 260;
/** Bound on a neighborhood expansion (1-hop or 2-hop). */
export const MAX_NEIGHBORHOOD_NODES = 60;
/** Bound on the candidate list an ambiguous token may produce. */
export const MAX_CANDIDATES = 8;
/** FIXED layout iteration count — never time- or frame-dependent. A dense
 *  component expands only from its boundary, so too few iterations leave the
 *  informative core as an unreadable knot; 240 is where the ISAAC projection
 *  stops changing shape, and it costs ~20 ms. */
export const LAYOUT_ITERATIONS = 240;
/** Layout coordinate box: positions are normalised into ±LAYOUT_EXTENT/2. */
export const LAYOUT_EXTENT = 1000;
/** Base viewBox extent at scale 1. */
export const VIEW_EXTENT = 1100;
export const MIN_SCALE = 0.25;
/** P36V.1 Unit F — raised from 8 (800%) to 24 (2400%) so the symbol level has
 *  room to be READ, not just reached. At 800% the deepest layer's marks were
 *  ~6 px apart inside a dense file; the extra range is what makes a 462-symbol
 *  file legible. Nothing else about zoom changed: the step is still 1.25 and the
 *  clamp is still the only place a scale is bounded. */
export const MAX_SCALE = 24;
/** Distinct community colours. Beyond this rank a cluster is drawn neutral —
 *  112 clusters cannot be 112 legible hues, and pretending otherwise would be
 *  a colour-coded lie. */
export const PALETTE_SLOTS = 8;
/** EVERY visible node is labelled while the visible set is this small. */
export const LABEL_LIMIT = 45;
/** Above LABEL_LIMIT the canvas is not left mute. The most-connected
 *  HUB_LABEL_COUNT nodes keep their label, so the default overview always has
 *  text to orient by. 18 is the largest count that still reads as landmarks
 *  rather than noise on the 220-node ISAAC projection: it names each dense
 *  cluster's hub and stops. */
export const HUB_LABEL_COUNT = 18;

// ------------------------------------------------- level of detail (P36V.1 F)

/**
 * The three LOD levels of the Explore canvas, and the zoom thresholds between
 * them. Each level is driven by a REAL field of the data — nothing here invents
 * a hierarchy (see `lib/graphDeep.ts` for the evidence and the measurements):
 *
 *  `file`    — the served-file reference projection already fetched by
 *              `GET /api/memory/graph` (201 files + 19 concepts). This IS the
 *              file level; it is not re-derived.
 *  `cluster` — `community_id` / `community_names` from the deep payload, grouped
 *              per `source_file`. Measured: 188 of the 221 communities live
 *              entirely inside ONE file, so a community is a grouping INSIDE a
 *              file, not a container of files.
 *  `symbol`  — the individual deep nodes, connected by the payload's own edges.
 *              All 2,161 `contains` edges are within-file (0 cross-file), so
 *              file→symbol containment is real, not assumed.
 *
 * Thresholds are deliberately above the zoom levels the existing suites drive
 * (max 156%), so the deeper layers are opt-in by an actual zoom gesture.
 */
export type GraphLodLevel = 'file' | 'cluster' | 'symbol';
export const LOD_CLUSTER_SCALE = 1.75;
export const LOD_SYMBOL_SCALE = 4;

export function graphLodLevel(scale: number): GraphLodLevel {
  if (scale >= LOD_SYMBOL_SCALE) return 'symbol';
  if (scale >= LOD_CLUSTER_SCALE) return 'cluster';
  return 'file';
}

/** The next threshold above `scale`, or null at the deepest level. Used by the
 *  canvas's "Reveal Detail" control so one click lands exactly on a level
 *  boundary instead of asking for six 1.25× presses. */
export function nextLodScale(scale: number): number | null {
  if (scale < LOD_CLUSTER_SCALE) return LOD_CLUSTER_SCALE;
  if (scale < LOD_SYMBOL_SCALE) return LOD_SYMBOL_SCALE;
  return null;
}

/**
 * SCREEN-SPACE sizing — the core of the "zoom reveals structure instead of
 * magnifying it" fix.
 *
 * The bug: `FILE_RADIUS`, the edge stroke widths and the 11px label font were
 * constants in USER UNITS. The viewBox extent is `VIEW_EXTENT / scale`, so at
 * 477% every mark was 4.8× larger on screen — pure magnification, and labels
 * became enormous.
 *
 * The fix: sizes are declared as "user units at scale 1" — i.e. EXACTLY today's
 * constants — and divided by the live scale. Rendered size = units × scale = the
 * declared constant, invariant under zoom and bounded by the clamp below.
 *
 * WHAT THIS DOES AND DOES NOT PRESERVE at 100% zoom. An earlier version of this
 * comment claimed the default view was "pixel-identical" to P36R. That was
 * false and is corrected here:
 *   · IDENTICAL — every mark radius (9 / 11), the label font (11), the label
 *     baseline offset (24) and every position. Asserted in graph-deep-model.test.ts.
 *   · CHANGED — stroke widths. `vector-effect="non-scaling-stroke"` is new on the
 *     node shapes and the base edges (no stylesheet in this project had ever set
 *     `vector-effect`), so `stroke-width: 1.5` now renders as 1.5 DEVICE pixels
 *     instead of 1.5 user units ≈ 0.8 px on a 600 px canvas — roughly 1.8×
 *     thicker, and the same for the 1.1 edge and the 2.4 / 3 / 3.4 emphasis
 *     outlines. This is a deliberate trade: those widths are state-driven CSS
 *     rules, so they cannot be attributes, and in user units a 3.4 focus ring
 *     reached ~44 device pixels at the 2400 % clamp. Sub-pixel outlines that
 *     rasterised inconsistently now render at their declared width, bounded at
 *     every zoom. The default view Krish signed off therefore DID change, in this
 *     one respect, and the report says so rather than claiming otherwise.
 *
 * Deliberately NOT measured from the DOM: a size derived from
 * `getBoundingClientRect()` would make the render depend on layout, which is
 * exactly the kind of non-determinism this module refuses everywhere else.
 */
export const MIN_MARK_UNITS_AT_SCALE_1 = 3;
export const MAX_MARK_UNITS_AT_SCALE_1 = 22;

/**
 * Convert a size expressed in user units at scale 1 into user units for `scale`,
 * clamped so the rendered size can never fall below MIN or exceed MAX.
 *
 * `screenBoundedUnits(u, s) * s ∈ [MIN, MAX]` for every s in [MIN_SCALE,
 * MAX_SCALE] — asserted directly in graph-model.test.ts.
 */
export function screenBoundedUnits(
  unitsAtScale1: number,
  scale: number,
  min: number = MIN_MARK_UNITS_AT_SCALE_1,
  max: number = MAX_MARK_UNITS_AT_SCALE_1,
): number {
  const bounded = Math.min(max, Math.max(min, unitsAtScale1));
  return bounded / clampScale(scale);
}

/** Reference mark sizes, in user units at scale 1. `file` / `concept` are the
 *  P36R constants verbatim, so mark RADII at 100% are unchanged (see the stroke
 *  caveat above for what did change). */
export const MARK_UNITS = {
  file: 9,
  concept: 11,
  /** a community cluster inside a file (the mid level) */
  cluster: 10,
  /** one deep node (the detail level) */
  symbol: 6,
} as const;
/** Label font size, in user units at scale 1 — mirrors the P36R 11px CSS rule,
 *  which is now applied as an attribute so it can track the zoom. */
export const LABEL_UNITS = 11;
/** Emphasis multiplier for the selected mark. Bounded by the same clamp. */
export const SELECTED_MARK_FACTOR = 1.35;

// --------------------------------------------------------------------- types

export type GraphMode = 'explore' | 'browse';
export type GraphTypeFilter = 'all' | 'file' | 'concept';

export interface GraphPoint {
  x: number;
  y: number;
}

export interface GraphNeighbor {
  id: string;
  relations: string[];
}

export interface GraphCommunityEntry {
  id: string;
  /** The upstream cluster label, verbatim. May be null, and may be a poor
   *  description of its members — see `isSingleton` / the UI's advisory copy. */
  name: string | null;
  file_count: number;
  /** files + concepts carrying this community id in THIS payload */
  node_count: number;
  isSingleton: boolean;
  /** rank by file_count desc, then id asc; drives the bounded colour palette */
  rank: number;
}

export interface GraphIndex {
  /** every node, sorted by id — the deterministic iteration order */
  nodes: ApiMemoryGraphNode[];
  byId: Map<string, ApiMemoryGraphNode>;
  /** de-duplicated, endpoint-verified edges, sorted */
  edges: ApiMemoryGraphEdge[];
  /** canonical "a\u0000b" keys — used to prove no rendered edge was invented */
  edgeKeys: Set<string>;
  adjacency: Map<string, GraphNeighbor[]>;
  byCommunity: Map<string, string[]>;
  communityById: Map<string, GraphCommunityEntry>;
  /** sorted by file_count desc, then id asc */
  communitiesBySize: GraphCommunityEntry[];
  /** sorted, de-duplicated relation values, verbatim from the payload */
  relationTypes: string[];
  /** the node ids actually laid out, ≤ MAX_RENDER_NODES */
  renderIds: string[];
  /** true when MAX_RENDER_NODES bit and some nodes are not on the canvas */
  renderTruncated: boolean;
  /** deterministic coordinates for every renderId */
  layout: Map<string, GraphPoint>;
  counts: {
    total: number;
    files: number;
    concepts: number;
    communities: number;
    singletonCommunities: number;
  };
}

export type GraphFocus =
  | { kind: 'neighbors'; nodeId: string; depth: 1 | 2; ids: string[]; truncated: boolean }
  /** `ids` is the sorted VISIBILITY set; `ordered` is the route start → end. */
  | { kind: 'path'; from: string; to: string; ids: string[]; ordered: string[] };

export type GraphNotice =
  | { kind: 'not_found'; token: string }
  | { kind: 'ambiguous'; token: string; candidates: string[] }
  /** cluster resolution has its own kinds: its candidates are CLUSTER ids, and
   *  offering them as node buttons would select the wrong thing entirely. */
  | { kind: 'community_not_found'; token: string }
  | { kind: 'community_ambiguous'; token: string; candidates: string[] }
  | { kind: 'relation_unknown'; tokens: string[] }
  | { kind: 'no_path'; from: string; to: string }
  | { kind: 'path_found'; from: string; to: string; hops: number }
  | {
      kind: 'neighborhood';
      nodeId: string;
      depth: 1 | 2;
      /** Nodes the surface ACTUALLY draws: the neighbourhood after the active
       *  type / cluster / search filters and the render bound. This is the same
       *  number the visible count line shows — announcing the raw neighbourhood
       *  size here said "14 nodes" while the canvas read "0 of 220". */
      count: number;
      /** The neighbourhood's own size, BEFORE those filters. Kept so the notice
       *  can explain a difference instead of leaving a bare, puzzling 0. */
      neighborhoodSize: number;
      truncated: boolean;
    };

export interface GraphViewport {
  cx: number;
  cy: number;
  scale: number;
}

export interface GraphViewState {
  mode: GraphMode;
  search: string;
  typeFilter: GraphTypeFilter;
  communityFilter: string; // 'all' | community id
  /** null = no relationship filter (every type). An ARRAY is the exact set the
   *  user chose — and `[]` therefore honestly means "none", not "all". */
  relationFilter: string[] | null;
  selectedId: string | null;
  focus: GraphFocus | null;
  view: GraphViewport;
  /** user-dragged node overrides; absent = the deterministic layout position */
  moved: Record<string, GraphPoint>;
  notice: GraphNotice | null;
}

/**
 * Every state mutation the graph UI can perform. Slice 4's command grammar and
 * Slice 5's Assistant intents parse INTO this union — they add no new mutation
 * surface, so there is exactly one place where graph state changes.
 */
export type GraphAction =
  | { kind: 'setMode'; mode: GraphMode }
  | { kind: 'select'; nodeId: string | null }
  | { kind: 'search'; query: string }
  | { kind: 'filterType'; value: GraphTypeFilter }
  | { kind: 'filterCommunity'; id: string }
  | { kind: 'filterRelation'; relations: string[] | null }
  | { kind: 'neighbors'; nodeId: string; depth: 1 | 2 }
  | { kind: 'path'; from: string; to: string }
  | { kind: 'pan'; dx: number; dy: number }
  | { kind: 'zoom'; factor: number }
  | { kind: 'moveNode'; nodeId: string; x: number; y: number }
  | { kind: 'fit' }
  | { kind: 'reset' }
  | { kind: 'clearFilters' }
  | { kind: 'clearFocus' }
  | { kind: 'dismissNotice' };

export type NodeResolution =
  | { status: 'found'; id: string }
  | { status: 'ambiguous'; candidates: string[] }
  | { status: 'not_found' };

/** The SAME three states as NodeResolution, for clusters: resolved, a bounded
 *  candidate list, or an honest miss. A cluster identity is never guessed
 *  either — `community <name>` must be able to fail out loud. */
export type CommunityResolution =
  | { status: 'found'; id: string }
  | { status: 'ambiguous'; candidates: string[] }
  | { status: 'not_found' };

// ----------------------------------------------------------------- utilities

const byIdAsc = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);

export function edgeKey(a: string, b: string): string {
  return a < b ? `${a}\u0000${b}` : `${b}\u0000${a}`;
}

const clampScale = (s: number): number => Math.min(MAX_SCALE, Math.max(MIN_SCALE, s));

/** True when an edge is allowed through the active relation filter. `null` is
 *  "no filter"; an empty array is an explicit "no relationship types". */
export function edgePassesRelations(
  edge: ApiMemoryGraphEdge,
  relations: readonly string[] | null,
): boolean {
  if (relations === null) return true;
  return edge.relations.some((r) => relations.includes(r));
}

// -------------------------------------------------------- deterministic layout

// The golden angle. A constant, not a random seed: node i starts at
// (R·sqrt((i+½)/n), i·GOLDEN_ANGLE), which spreads a sorted list evenly with no
// entropy at all — the "seed" is the node's own position in the sorted id list.
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
const GRAVITY = 0.008;

/** Radius of a laid-out component, per sqrt(node count). Keeps node DENSITY
 *  constant across components instead of stretching a 2-node pair to the size
 *  of a 60-node cluster. */
const COMPONENT_UNIT = 21;
/** Clearance between packed components. */
const COMPONENT_GAP = 26;
/** Radius the connected core is normalised into, as a fraction of the box. */
const CORE_RADIUS_FRACTION = 0.64;
/** Radius the first belt of unconnected nodes sits at. */
const BELT_START_FRACTION = 0.82;
const BELT_STEP = 44;
const BELT_SPACING = 46;

/** Undirected connected components over `ids`, each sorted, the list ordered by
 *  (size desc, first id asc). Deterministic, and the basis of the layout below. */
function componentsOf(
  ids: readonly string[],
  links: readonly (readonly [string, string])[],
): string[][] {
  const adj = new Map<string, string[]>();
  for (const id of ids) adj.set(id, []);
  for (const [a, b] of links) {
    adj.get(a)?.push(b);
    adj.get(b)?.push(a);
  }
  for (const list of adj.values()) list.sort(byIdAsc);
  const seen = new Set<string>();
  const out: string[][] = [];
  for (const id of ids) {
    if (seen.has(id)) continue;
    const comp: string[] = [];
    let frontier = [id];
    seen.add(id);
    while (frontier.length > 0) {
      const next: string[] = [];
      for (const cur of frontier) {
        comp.push(cur);
        for (const nb of adj.get(cur) ?? []) {
          if (seen.has(nb)) continue;
          seen.add(nb);
          next.push(nb);
        }
      }
      frontier = next;
    }
    out.push(comp.sort(byIdAsc));
  }
  return out.sort((a, b) => b.length - a.length || byIdAsc(a[0], b[0]));
}

/**
 * Fruchterman–Reingold relaxation of ONE connected component, seeded by a
 * golden-angle spiral over its sorted ids and run for a FIXED number of
 * iterations, then centred and scaled to `radius`.
 *
 * Deliberately per-component: run over the whole node set at once, the ~3 large
 * ISAAC components collapse into unreadable knots separated by empty space,
 * because accumulated repulsion from unrelated components swamps each
 * component's own internal structure. One component at a time is both better
 * looking and cheaper (O(n_c²) per component, not O(n²)).
 */
function layoutComponent(
  comp: readonly string[],
  links: readonly (readonly [string, string])[],
  radius: number,
): Map<string, GraphPoint> {
  const n = comp.length;
  const out = new Map<string, GraphPoint>();
  if (n === 0) return out;
  if (n === 1) {
    out.set(comp[0], { x: 0, y: 0 });
    return out;
  }

  const idx = new Map<string, number>();
  comp.forEach((id, i) => idx.set(id, i));
  const box = 1000;
  const half = box / 2;

  const pos = new Float64Array(n * 2);
  for (let i = 0; i < n; i += 1) {
    const r = half * Math.sqrt((i + 0.5) / n);
    const a = GOLDEN_ANGLE * i;
    pos[i * 2] = r * Math.cos(a);
    pos[i * 2 + 1] = r * Math.sin(a);
  }

  const flat: number[] = [];
  for (const [a, b] of links) {
    const ia = idx.get(a);
    const ib = idx.get(b);
    if (ia === undefined || ib === undefined || ia === ib) continue;
    flat.push(ia, ib);
  }

  const k = Math.sqrt((box * box) / n);
  const disp = new Float64Array(n * 2);

  for (let it = 0; it < LAYOUT_ITERATIONS; it += 1) {
    disp.fill(0);

    for (let i = 0; i < n; i += 1) {
      const xi = pos[i * 2];
      const yi = pos[i * 2 + 1];
      for (let j = i + 1; j < n; j += 1) {
        let dx = xi - pos[j * 2];
        let dy = yi - pos[j * 2 + 1];
        let d2 = dx * dx + dy * dy;
        if (d2 < 1e-9) {
          // Coincident points: separate them by a deterministic, index-derived
          // nudge rather than a random jitter.
          dx = (i + 1) * 1e-4;
          dy = (j + 1) * 1e-4;
          d2 = dx * dx + dy * dy;
        }
        const d = Math.sqrt(d2);
        const f = (k * k) / d;
        const ux = (dx / d) * f;
        const uy = (dy / d) * f;
        disp[i * 2] += ux;
        disp[i * 2 + 1] += uy;
        disp[j * 2] -= ux;
        disp[j * 2 + 1] -= uy;
      }
    }

    for (let l = 0; l < flat.length; l += 2) {
      const a = flat[l];
      const b = flat[l + 1];
      let dx = pos[a * 2] - pos[b * 2];
      let dy = pos[a * 2 + 1] - pos[b * 2 + 1];
      let d = Math.sqrt(dx * dx + dy * dy);
      if (d < 1e-9) {
        dx = 1e-4;
        dy = 0;
        d = 1e-4;
      }
      const f = (d * d) / k;
      const ux = (dx / d) * f;
      const uy = (dy / d) * f;
      disp[a * 2] -= ux;
      disp[a * 2 + 1] -= uy;
      disp[b * 2] += ux;
      disp[b * 2 + 1] += uy;
    }

    // Gravity holds a sparse component together; the component is alone here,
    // so it cannot be pushed out of frame by anything else.
    for (let i = 0; i < n; i += 1) {
      disp[i * 2] -= pos[i * 2] * GRAVITY;
      disp[i * 2 + 1] -= pos[i * 2 + 1] * GRAVITY;
    }

    const temp = box * 0.1 * (1 - it / LAYOUT_ITERATIONS);
    for (let i = 0; i < n; i += 1) {
      const dx = disp[i * 2];
      const dy = disp[i * 2 + 1];
      const d = Math.sqrt(dx * dx + dy * dy);
      if (d <= 1e-12) continue;
      const factor = Math.min(d, temp) / d;
      pos[i * 2] += dx * factor;
      pos[i * 2 + 1] += dy * factor;
    }
  }

  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (let i = 0; i < n; i += 1) {
    minX = Math.min(minX, pos[i * 2]);
    maxX = Math.max(maxX, pos[i * 2]);
    minY = Math.min(minY, pos[i * 2 + 1]);
    maxY = Math.max(maxY, pos[i * 2 + 1]);
  }
  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;
  const span = Math.max(maxX - minX, maxY - minY, 1e-6);
  const scale = (radius * 2) / span;
  for (let i = 0; i < n; i += 1) {
    out.set(comp[i], { x: (pos[i * 2] - cx) * scale, y: (pos[i * 2 + 1] - cy) * scale });
  }
  return out;
}

/** Deterministic circle packing: largest first at the origin, each subsequent
 *  component on the first non-overlapping slot of an expanding ring scan. */
function packCentres(radii: readonly number[]): GraphPoint[] {
  const centres: GraphPoint[] = [];
  const ANGLES = 48;
  for (let i = 0; i < radii.length; i += 1) {
    if (i === 0) {
      centres.push({ x: 0, y: 0 });
      continue;
    }
    const r = radii[i];
    let placed: GraphPoint | null = null;
    for (let ring = 1; ring <= 400 && !placed; ring += 1) {
      const R = ring * 14;
      for (let a = 0; a < ANGLES; a += 1) {
        const angle = (2 * Math.PI * a) / ANGLES;
        const cand = { x: R * Math.cos(angle), y: R * Math.sin(angle) };
        let ok = true;
        for (let j = 0; j < centres.length; j += 1) {
          const dx = cand.x - centres[j].x;
          const dy = cand.y - centres[j].y;
          if (Math.hypot(dx, dy) < r + radii[j] + COMPONENT_GAP) {
            ok = false;
            break;
          }
        }
        if (ok) {
          placed = cand;
          break;
        }
      }
    }
    centres.push(placed ?? { x: 0, y: 0 });
  }
  return centres;
}

/**
 * Deterministic layout in two regions.
 *
 * Region 1 — the CONNECTED core: each connected component is relaxed on its own
 * (see `layoutComponent`), scaled to a radius proportional to sqrt(its size) so
 * node density is constant, then the components are packed without overlap and
 * the whole core is normalised into a fixed radius.
 *
 * Region 2 — the UNCONNECTED belt: 52 of the 201 served files and all 19
 * concepts have no recorded reference at all. Left in a force simulation they
 * settle into a repulsion/gravity equilibrium ring and squeeze the informative
 * core into a few unreadable pixels. They are placed on concentric belts OUTSIDE
 * the core instead — which is also the honest reading of the data: these nodes
 * genuinely have no edges, and the picture now says so.
 *
 * Deterministic by construction: no Math.random, no Date, no rAF, no settling
 * loop. Same (ids, edges) ⇒ identical coordinates (see graph-model.test.ts).
 */
export function computeLayout(
  ids: readonly string[],
  edges: readonly ApiMemoryGraphEdge[],
): Map<string, GraphPoint> {
  const all = [...ids].sort(byIdAsc);
  const out = new Map<string, GraphPoint>();
  if (all.length === 0) return out;
  if (all.length === 1) {
    out.set(all[0], { x: 0, y: 0 });
    return out;
  }

  const present = new Set(all);
  const pairSeen = new Set<string>();
  const links: [string, string][] = [];
  const sortedEdges = [...edges].sort(
    (p, q) => byIdAsc(p.source, q.source) || byIdAsc(p.target, q.target),
  );
  for (const e of sortedEdges) {
    if (e.source === e.target) continue;
    if (!present.has(e.source) || !present.has(e.target)) continue;
    const key = edgeKey(e.source, e.target);
    if (pairSeen.has(key)) continue;
    pairSeen.add(key);
    links.push([e.source, e.target]);
  }

  const comps = componentsOf(all, links);
  const multi = comps.filter((c) => c.length > 1);
  const belt = comps.filter((c) => c.length === 1).map((c) => c[0]).sort(byIdAsc);
  const half = LAYOUT_EXTENT / 2;

  if (multi.length > 0) {
    const radii = multi.map((c) => COMPONENT_UNIT * Math.sqrt(c.length));
    const centres = packCentres(radii);
    const raw = new Map<string, GraphPoint>();
    multi.forEach((comp, i) => {
      const member = new Set(comp);
      const own = links.filter(([a, b]) => member.has(a) && member.has(b));
      const local = layoutComponent(comp, own, radii[i]);
      for (const [id, p] of local) {
        raw.set(id, { x: p.x + centres[i].x, y: p.y + centres[i].y });
      }
    });

    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;
    for (const p of raw.values()) {
      minX = Math.min(minX, p.x);
      maxX = Math.max(maxX, p.x);
      minY = Math.min(minY, p.y);
      maxY = Math.max(maxY, p.y);
    }
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;
    const span = Math.max(maxX - minX, maxY - minY, 1e-6);
    const target = belt.length > 0 ? half * CORE_RADIUS_FRACTION * 2 : LAYOUT_EXTENT;
    const scale = target / span;
    for (const id of all) {
      const p = raw.get(id);
      if (p) out.set(id, { x: (p.x - cx) * scale, y: (p.y - cy) * scale });
    }
  }

  // Unconnected nodes: concentric belts, evenly spaced, deterministic by id.
  if (belt.length > 0) {
    const start = multi.length > 0 ? half * BELT_START_FRACTION : half * 0.35;
    let placed = 0;
    let ring = 0;
    while (placed < belt.length) {
      const r = start + ring * BELT_STEP;
      const capacity = Math.max(1, Math.floor((2 * Math.PI * r) / BELT_SPACING));
      const take = Math.min(capacity, belt.length - placed);
      for (let i = 0; i < take; i += 1) {
        // The 0.37 rad per-ring offset staggers successive belts so nodes on
        // adjacent rings do not line up radially.
        const angle = -Math.PI / 2 + (2 * Math.PI * i) / take + ring * 0.37;
        out.set(belt[placed + i], { x: r * Math.cos(angle), y: r * Math.sin(angle) });
      }
      placed += take;
      ring += 1;
    }
  }

  return out;
}

// ------------------------------------------------------------------- indexing

/**
 * Build the deterministic index the whole graph UI reads from.
 *
 * Note the edge handling: an edge is kept ONLY when both of its endpoints are
 * present as nodes in the same payload. Nothing is repaired, inferred, or
 * synthesised — that is the "no invented edges" rule as code.
 */
export function buildGraphIndex(data: ApiMemoryGraphResponse): GraphIndex {
  const nodes = [...data.nodes].sort((a, b) => byIdAsc(a.id, b.id));
  const byId = new Map(nodes.map((n) => [n.id, n] as const));

  const edges: ApiMemoryGraphEdge[] = [];
  const edgeKeys = new Set<string>();
  const rawEdges = [...data.edges].sort(
    (p, q) => byIdAsc(p.source, q.source) || byIdAsc(p.target, q.target),
  );
  for (const e of rawEdges) {
    if (e.source === e.target) continue;
    if (!byId.has(e.source) || !byId.has(e.target)) continue;
    const key = edgeKey(e.source, e.target);
    if (edgeKeys.has(key)) continue;
    edgeKeys.add(key);
    edges.push({ source: e.source, target: e.target, relations: [...e.relations].sort(byIdAsc) });
  }

  const adjacency = new Map<string, GraphNeighbor[]>();
  for (const n of nodes) adjacency.set(n.id, []);
  for (const e of edges) {
    adjacency.get(e.source)?.push({ id: e.target, relations: e.relations });
    adjacency.get(e.target)?.push({ id: e.source, relations: e.relations });
  }
  for (const list of adjacency.values()) list.sort((a, b) => byIdAsc(a.id, b.id));

  const byCommunity = new Map<string, string[]>();
  for (const n of nodes) {
    const cid = n.community_id;
    if (!cid) continue;
    if (!byCommunity.has(cid)) byCommunity.set(cid, []);
    byCommunity.get(cid)!.push(n.id);
  }
  for (const list of byCommunity.values()) list.sort(byIdAsc);

  const communitiesBySize: GraphCommunityEntry[] = [...data.communities]
    .sort((a, b) => b.file_count - a.file_count || byIdAsc(a.id, b.id))
    .map((c, i) => ({
      id: c.id,
      name: c.name,
      file_count: c.file_count,
      node_count: byCommunity.get(c.id)?.length ?? 0,
      isSingleton: c.file_count <= 1,
      rank: i,
    }));
  const communityById = new Map(communitiesBySize.map((c) => [c.id, c] as const));

  const relationTypes = [...new Set(edges.flatMap((e) => e.relations))].sort(byIdAsc);

  // Deterministic render prefix: most-connected first, ties broken by id, so a
  // cap (when it ever bites) keeps the structurally informative nodes.
  const degree = (id: string) => adjacency.get(id)?.length ?? 0;
  const renderOrder = nodes
    .map((n) => n.id)
    .sort((a, b) => degree(b) - degree(a) || byIdAsc(a, b));
  const renderIds = renderOrder.slice(0, MAX_RENDER_NODES).sort(byIdAsc);
  const renderTruncated = renderOrder.length > MAX_RENDER_NODES;
  const renderSet = new Set(renderIds);
  const layout = computeLayout(
    renderIds,
    edges.filter((e) => renderSet.has(e.source) && renderSet.has(e.target)),
  );

  return {
    nodes,
    byId,
    edges,
    edgeKeys,
    adjacency,
    byCommunity,
    communityById,
    communitiesBySize,
    relationTypes,
    renderIds,
    renderTruncated,
    layout,
    counts: {
      total: nodes.length,
      files: nodes.filter((n) => n.kind === 'file').length,
      concepts: nodes.filter((n) => n.kind === 'concept').length,
      communities: communitiesBySize.length,
      singletonCommunities: communitiesBySize.filter((c) => c.isSingleton).length,
    },
  };
}

// ------------------------------------------------------------------ resolution

/**
 * Resolve a user token (typed, clicked, or proposed by the Assistant) to a node.
 * Tiered exact→prefix→substring; a tier that matches more than one node returns
 * a BOUNDED candidate list and stops. Identity is never guessed.
 */
export function resolveNode(token: string, index: GraphIndex): NodeResolution {
  const raw = token.trim();
  if (!raw) return { status: 'not_found' };
  if (index.byId.has(raw)) return { status: 'found', id: raw };

  const needle = raw.toLowerCase();
  const exact: string[] = [];
  const basename: string[] = [];
  const prefix: string[] = [];
  const substring: string[] = [];
  for (const node of index.nodes) {
    const lid = node.id.toLowerCase();
    const label = (node.label ?? '').toLowerCase();
    const base = lid.slice(lid.lastIndexOf('/') + 1);
    if (lid === needle || label === needle) exact.push(node.id);
    else if (base === needle) basename.push(node.id);
    else if (lid.startsWith(needle) || label.startsWith(needle)) prefix.push(node.id);
    else if (lid.includes(needle) || label.includes(needle)) substring.push(node.id);
  }
  for (const tier of [exact, basename, prefix, substring]) {
    if (tier.length === 1) return { status: 'found', id: tier[0] };
    if (tier.length > 1) return { status: 'ambiguous', candidates: tier.slice(0, MAX_CANDIDATES) };
  }
  return { status: 'not_found' };
}

/**
 * Resolve a cluster token — an id, or a cluster name — the same tiered,
 * never-guessing way `resolveNode` resolves a node. Candidates are offered
 * largest-cluster-first (`communitiesBySize` order) and bounded.
 *
 * This exists so the reducer, the command bar (`community <name|id>`) and the
 * Assistant share ONE cluster resolver: without it a bad token silently yields
 * an empty view with nothing said.
 */
export function resolveCommunity(token: string, index: GraphIndex): CommunityResolution {
  const raw = token.trim();
  if (!raw) return { status: 'not_found' };
  if (index.communityById.has(raw)) return { status: 'found', id: raw };

  const needle = raw.toLowerCase();
  const exact: string[] = [];
  const prefix: string[] = [];
  const substring: string[] = [];
  for (const entry of index.communitiesBySize) {
    const name = (entry.name ?? '').toLowerCase();
    if (!name) continue;
    if (name === needle) exact.push(entry.id);
    else if (name.startsWith(needle)) prefix.push(entry.id);
    else if (name.includes(needle)) substring.push(entry.id);
  }
  for (const tier of [exact, prefix, substring]) {
    if (tier.length === 1) return { status: 'found', id: tier[0] };
    if (tier.length > 1) return { status: 'ambiguous', candidates: tier.slice(0, MAX_CANDIDATES) };
  }
  return { status: 'not_found' };
}

// ------------------------------------------------------------------ traversal

/**
 * Deterministic BFS shortest path over the UNDIRECTED edge set. Adjacency is
 * pre-sorted by node id, so among equal-length paths the lexicographically
 * first-discovered one always wins. Returns null — honestly — when the two
 * nodes are not connected in this projection.
 */
export function shortestPath(
  from: string,
  to: string,
  index: GraphIndex,
  relations: readonly string[] | null = null,
): string[] | null {
  if (!index.byId.has(from) || !index.byId.has(to)) return null;
  if (from === to) return [from];
  const allow = (rels: string[]) => relations === null || rels.some((r) => relations.includes(r));

  const prev = new Map<string, string>();
  const visited = new Set<string>([from]);
  let frontier = [from];
  while (frontier.length > 0) {
    const next: string[] = [];
    for (const id of frontier) {
      for (const nb of index.adjacency.get(id) ?? []) {
        if (visited.has(nb.id) || !allow(nb.relations)) continue;
        visited.add(nb.id);
        prev.set(nb.id, id);
        if (nb.id === to) {
          const path = [to];
          let cur = to;
          while (prev.has(cur)) {
            cur = prev.get(cur)!;
            path.push(cur);
          }
          return path.reverse();
        }
        next.push(nb.id);
      }
    }
    frontier = next;
  }
  return null;
}

/** Bounded 1-hop / 2-hop neighborhood, including the focal node. */
export function neighborhood(
  nodeId: string,
  depth: 1 | 2,
  index: GraphIndex,
  relations: readonly string[] | null = null,
): { ids: string[]; truncated: boolean } {
  if (!index.byId.has(nodeId)) return { ids: [], truncated: false };
  const allow = (rels: string[]) => relations === null || rels.some((r) => relations.includes(r));

  const seen = new Set<string>([nodeId]);
  const ordered = [nodeId];
  let frontier = [nodeId];
  let truncated = false;
  for (let d = 0; d < depth; d += 1) {
    const next: string[] = [];
    for (const id of frontier) {
      for (const nb of index.adjacency.get(id) ?? []) {
        if (seen.has(nb.id) || !allow(nb.relations)) continue;
        if (ordered.length >= MAX_NEIGHBORHOOD_NODES) {
          truncated = true;
          continue;
        }
        seen.add(nb.id);
        ordered.push(nb.id);
        next.push(nb.id);
      }
    }
    frontier = next;
  }
  return { ids: [...ordered].sort(byIdAsc), truncated };
}

// -------------------------------------------------------------------- palette

/** Colour slot for a community, or null when the cluster is beyond the bounded
 *  palette (drawn neutral — never a fabricated 112-hue rainbow). */
export function communityColorIndex(communityId: string | null, index: GraphIndex): number | null {
  if (!communityId) return null;
  const entry = index.communityById.get(communityId);
  if (!entry || entry.rank >= PALETTE_SLOTS) return null;
  return entry.rank;
}

/** Honest, never-authoritative label for a cluster in a control or legend.
 *  The file count is a separate `·` segment on purpose: upstream names already
 *  carry their own parenthetical (`Official schema v1.05 (28)`), and appending
 *  a second `(13)` would read as two numbers of the same kind. */
export function communityOptionLabel(entry: GraphCommunityEntry): string {
  const name = entry.name ?? 'unnamed cluster';
  return `${name} · ${entry.file_count} file${entry.file_count === 1 ? '' : 's'}`;
}

/** `communityOptionLabel`, plus the cluster id when another cluster in `peers`
 *  carries the SAME name — the id is what actually distinguishes them in the
 *  data, so it is shown rather than a nicer invented name. */
export function communityLabelAmong(
  entry: GraphCommunityEntry,
  peers: readonly GraphCommunityEntry[],
): string {
  const name = entry.name ?? 'unnamed cluster';
  const collides = peers.some((p) => p.id !== entry.id && (p.name ?? 'unnamed cluster') === name);
  if (!collides) return communityOptionLabel(entry);
  return `${name} · cluster ${entry.id} · ${entry.file_count} file${entry.file_count === 1 ? '' : 's'}`;
}

/**
 * The nodes that keep a label when the visible set is too large to label in
 * full: most-connected first, ties broken by sorted id, bounded at `count`.
 *
 * Deliberately the SAME ordering the render cap uses, so "what stays labelled"
 * and "what survives the cap" can never disagree.
 */
export function hubLabelIds(
  visible: readonly string[],
  index: GraphIndex,
  count: number = HUB_LABEL_COUNT,
): string[] {
  if (count <= 0) return [];
  const degree = (id: string) => index.adjacency.get(id)?.length ?? 0;
  return [...visible].sort((a, b) => degree(b) - degree(a) || byIdAsc(a, b)).slice(0, count);
}

// ------------------------------------------------------- canvas label placement

/** Longest label the canvas paints before eliding. */
export const CANVAS_LABEL_MAX_CHARS = 26;
/** Mirrors `.memory-graph-node-label { font-size: 11px }` — SVG user units. */
const LABEL_FONT_UNITS = 11;
/** Mean advance per character of the UI font at that size, in user units. */
const LABEL_CHAR_UNITS = 5.9;
/** Mirrors the canvas `<text y={CONCEPT_RADIUS + 13}>` baseline offset. */
const LABEL_BASELINE_UNITS = 24;
/** How many hub candidates the placer may consider per label it will keep. */
const LABEL_CANDIDATE_FACTOR = 3;

/** The canvas label for a node: the basename for a file, the label for a
 *  concept, elided. Lives here (not in the component) so the width estimate
 *  below and the text actually drawn can never drift apart. */
export function canvasNodeLabel(node: ApiMemoryGraphNode): string {
  const raw = node.label ?? node.id;
  const base = node.kind === 'file' ? raw.slice(raw.lastIndexOf('/') + 1) || raw : raw;
  return base.length > CANVAS_LABEL_MAX_CHARS ? `${base.slice(0, CANVAS_LABEL_MAX_CHARS - 1)}…` : base;
}

interface LabelBox {
  x0: number;
  x1: number;
  y0: number;
  y1: number;
}

/** The approximate box a node's label occupies, in layout units. */
export function labelBox(
  id: string,
  index: GraphIndex,
  moved: Readonly<Record<string, GraphPoint>> = {},
): LabelBox | null {
  const node = index.byId.get(id);
  const pos = moved[id] ?? index.layout.get(id);
  if (!node || !pos) return null;
  const halfWidth = (canvasNodeLabel(node).length * LABEL_CHAR_UNITS) / 2;
  const top = pos.y + LABEL_BASELINE_UNITS - LABEL_FONT_UNITS;
  return { x0: pos.x - halfWidth, x1: pos.x + halfWidth, y0: top, y1: top + LABEL_FONT_UNITS * 1.3 };
}

const boxesOverlap = (a: LabelBox, b: LabelBox): boolean =>
  a.x0 < b.x1 && b.x0 < a.x1 && a.y0 < b.y1 && b.y0 < a.y1;

/**
 * The labels actually painted when the visible set is above LABEL_LIMIT:
 * hub-ranked candidates, accepted greedily only while the label box does not
 * collide with one already accepted.
 *
 * The collision pass is not decoration. The highest-degree nodes are precisely
 * the ones packed into a cluster's core, so labelling the top 18 outright put
 * 14 overlapping label pairs on the ISAAC projection — a smear in the middle of
 * each cluster, which is noise, not orientation. Rejecting a colliding
 * candidate and moving down the ranking yields the same number of landmarks,
 * spread out and readable.
 *
 * Deterministic: fixed candidate order, fixed geometry, no measurement of the
 * live DOM. The same (visible, layout, drags) always yields the same set.
 */
export function placedLabelIds(
  visible: readonly string[],
  index: GraphIndex,
  moved: Readonly<Record<string, GraphPoint>> = {},
  count: number = HUB_LABEL_COUNT,
): string[] {
  if (count <= 0) return [];
  const out: string[] = [];
  const boxes: LabelBox[] = [];
  for (const id of hubLabelIds(visible, index, count * LABEL_CANDIDATE_FACTOR)) {
    if (out.length >= count) break;
    const box = labelBox(id, index, moved);
    if (!box || boxes.some((b) => boxesOverlap(box, b))) continue;
    boxes.push(box);
    out.push(id);
  }
  return out;
}

// ------------------------------------------------------------------- selectors

export function initialGraphViewState(mode: GraphMode = 'explore'): GraphViewState {
  return {
    mode,
    search: '',
    typeFilter: 'all',
    communityFilter: 'all',
    relationFilter: null,
    selectedId: null,
    focus: null,
    view: { cx: 0, cy: 0, scale: 1 },
    moved: {},
    notice: null,
  };
}

/** Does this node survive the search / type / community filters? */
export function matchesFilters(node: ApiMemoryGraphNode, state: GraphViewState): boolean {
  if (state.typeFilter !== 'all' && node.kind !== state.typeFilter) return false;
  if (state.communityFilter !== 'all' && (node.community_id ?? '') !== state.communityFilter) {
    return false;
  }
  const needle = state.search.trim().toLowerCase();
  if (needle) {
    const haystack = `${node.label ?? ''} ${node.id}`.toLowerCase();
    if (!haystack.includes(needle)) return false;
  }
  return true;
}

/** Every node id passing the filters — the Browse list's source (NOT capped by
 *  MAX_RENDER_NODES: the textual list can show everything). */
export function filteredNodeIds(state: GraphViewState, index: GraphIndex): string[] {
  const focusSet = state.focus ? new Set(state.focus.ids) : null;
  return index.nodes
    .filter((n) => (focusSet ? focusSet.has(n.id) : true))
    .filter((n) => matchesFilters(n, state))
    .map((n) => n.id);
}

/** Every node id drawn on the canvas — the filtered set ∩ the render bound. */
export function visibleNodeIds(state: GraphViewState, index: GraphIndex): string[] {
  const rendered = new Set(index.renderIds);
  return filteredNodeIds(state, index).filter((id) => rendered.has(id));
}

/**
 * The edges drawn for a visible set. Every returned edge is an object taken
 * from `index.edges`, which came from the payload — this function can only ever
 * REMOVE edges, never create one.
 */
export function visibleEdges(
  state: GraphViewState,
  index: GraphIndex,
  visible: ReadonlySet<string>,
): ApiMemoryGraphEdge[] {
  return index.edges.filter(
    (e) =>
      visible.has(e.source) &&
      visible.has(e.target) &&
      edgePassesRelations(e, state.relationFilter),
  );
}

/** A node's current position: the user's drag override, else the layout. */
export function nodePosition(
  id: string,
  state: GraphViewState,
  index: GraphIndex,
): GraphPoint | undefined {
  return state.moved[id] ?? index.layout.get(id);
}

/** The connected nodes of `id`, honouring the active relation filter. */
export function connectedNodes(
  id: string,
  state: GraphViewState,
  index: GraphIndex,
): GraphNeighbor[] {
  return (index.adjacency.get(id) ?? []).filter((nb) =>
    edgePassesRelations({ source: id, target: nb.id, relations: nb.relations }, state.relationFilter),
  );
}

/** Viewport that frames `ids`; falls back to the identity view when empty. */
export function fitViewport(
  ids: readonly string[],
  state: GraphViewState,
  index: GraphIndex,
): GraphViewport {
  const pts = ids
    .map((id) => nodePosition(id, state, index))
    .filter((p): p is GraphPoint => p !== undefined);
  if (pts.length === 0) return { cx: 0, cy: 0, scale: 1 };
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (const p of pts) {
    minX = Math.min(minX, p.x);
    maxX = Math.max(maxX, p.x);
    minY = Math.min(minY, p.y);
    maxY = Math.max(maxY, p.y);
  }
  const pad = 60;
  const w = Math.max(maxX - minX + pad * 2, 120);
  const h = Math.max(maxY - minY + pad * 2, 120);
  return {
    cx: (minX + maxX) / 2,
    cy: (minY + maxY) / 2,
    scale: clampScale(VIEW_EXTENT / Math.max(w, h)),
  };
}

/** The SVG viewBox string for a viewport. */
export function viewBoxOf(view: GraphViewport): string {
  const extent = VIEW_EXTENT / view.scale;
  return `${view.cx - extent / 2} ${view.cy - extent / 2} ${extent} ${extent}`;
}

// --------------------------------------------------------------------- reducer

/**
 * The ONE code path for graph state. Pointer interactions, filter controls, the
 * Slice-4 command bar and Slice-5 Assistant proposals all funnel through here.
 */
export function applyGraphAction(
  state: GraphViewState,
  action: GraphAction,
  index: GraphIndex,
): GraphViewState {
  switch (action.kind) {
    case 'setMode':
      return state.mode === action.mode ? state : { ...state, mode: action.mode };

    case 'select': {
      if (action.nodeId === null) return { ...state, selectedId: null, notice: null };
      // Resolves exactly like `neighbors` and `path`. A pointer click passes an
      // exact id and hits `byId` on the first tier, so this costs nothing there;
      // what it buys is that a TYPED or PROPOSED token (`select <node>`, "show
      // me X") reaches the one resolver and the one notice-builder instead of
      // each caller growing its own copy.
      const resolved = resolveNode(action.nodeId, index);
      if (resolved.status === 'not_found') {
        return { ...state, notice: { kind: 'not_found', token: action.nodeId } };
      }
      if (resolved.status === 'ambiguous') {
        return {
          ...state,
          notice: { kind: 'ambiguous', token: action.nodeId, candidates: resolved.candidates },
        };
      }
      return { ...state, selectedId: resolved.id, notice: null };
    }

    case 'search':
      return { ...state, search: action.query, notice: null };

    case 'filterType':
      return { ...state, typeFilter: action.value, notice: null };

    case 'filterCommunity': {
      if (action.id === 'all' || action.id === '') {
        return { ...state, communityFilter: 'all', notice: null };
      }
      // By id OR by name, and an unusable token says so. Without this a garbage
      // `community <name>` filtered the view down to nothing with no notice —
      // an empty canvas that looks like an answer.
      const resolved = resolveCommunity(action.id, index);
      if (resolved.status === 'not_found') {
        return { ...state, notice: { kind: 'community_not_found', token: action.id } };
      }
      if (resolved.status === 'ambiguous') {
        return {
          ...state,
          notice: {
            kind: 'community_ambiguous',
            token: action.id,
            candidates: resolved.candidates,
          },
        };
      }
      return { ...state, communityFilter: resolved.id, notice: null };
    }

    case 'filterRelation': {
      if (action.relations === null) return { ...state, relationFilter: null, notice: null };
      // Unknown relation values are never honoured — the filter can only name
      // types the payload actually contains — but they are not swallowed either:
      // dropping them silently turns `relation bogus` into a blank canvas with
      // no explanation.
      const known: string[] = [];
      const unknown: string[] = [];
      for (const r of action.relations) {
        (index.relationTypes.includes(r) ? known : unknown).push(r);
      }
      const allowed = [...new Set(known)].sort(byIdAsc);
      return {
        ...state,
        relationFilter: allowed,
        notice:
          unknown.length > 0
            ? { kind: 'relation_unknown', tokens: [...new Set(unknown)].sort(byIdAsc) }
            : null,
      };
    }

    case 'neighbors': {
      const resolved = resolveNode(action.nodeId, index);
      if (resolved.status === 'not_found') {
        return { ...state, notice: { kind: 'not_found', token: action.nodeId } };
      }
      if (resolved.status === 'ambiguous') {
        return {
          ...state,
          notice: { kind: 'ambiguous', token: action.nodeId, candidates: resolved.candidates },
        };
      }
      const hood = neighborhood(resolved.id, action.depth, index, state.relationFilter);
      const expanded: GraphViewState = {
        ...state,
        selectedId: resolved.id,
        focus: {
          kind: 'neighbors',
          nodeId: resolved.id,
          depth: action.depth,
          ids: hood.ids,
          truncated: hood.truncated,
        },
        notice: null,
      };
      // The announced count is the count actually RENDERED, not the size of the
      // neighbourhood: the focus set is intersected with the active filters by
      // `matchesFilters`, so under `type concept` (or a live search) a 14-node
      // neighbourhood legitimately draws 0 — and announcing 14 there was a
      // number the surface contradicted in the very next line.
      const visible = visibleNodeIds(expanded, index);
      return {
        ...expanded,
        notice: {
          kind: 'neighborhood',
          nodeId: resolved.id,
          depth: action.depth,
          count: visible.length,
          neighborhoodSize: hood.ids.length,
          truncated: hood.truncated,
        },
        // Frame the result. Without this the canvas keeps its previous viewport
        // and a 3-node answer is a speck in the middle of an empty field.
        view: fitViewport(visible, expanded, index),
      };
    }

    case 'path': {
      const a = resolveNode(action.from, index);
      if (a.status === 'not_found') {
        return { ...state, notice: { kind: 'not_found', token: action.from } };
      }
      if (a.status === 'ambiguous') {
        return {
          ...state,
          notice: { kind: 'ambiguous', token: action.from, candidates: a.candidates },
        };
      }
      const b = resolveNode(action.to, index);
      if (b.status === 'not_found') {
        return { ...state, notice: { kind: 'not_found', token: action.to } };
      }
      if (b.status === 'ambiguous') {
        return {
          ...state,
          notice: { kind: 'ambiguous', token: action.to, candidates: b.candidates },
        };
      }
      const path = shortestPath(a.id, b.id, index, state.relationFilter);
      if (path === null) {
        return {
          ...state,
          focus: null,
          notice: { kind: 'no_path', from: a.id, to: b.id },
        };
      }
      const routed: GraphViewState = {
        ...state,
        selectedId: a.id,
        focus: { kind: 'path', from: a.id, to: b.id, ids: [...path].sort(byIdAsc), ordered: path },
        notice: { kind: 'path_found', from: a.id, to: b.id, hops: path.length - 1 },
      };
      return { ...routed, view: fitViewport(visibleNodeIds(routed, index), routed, index) };
    }

    case 'pan':
      return { ...state, view: { ...state.view, cx: state.view.cx + action.dx, cy: state.view.cy + action.dy } };

    case 'zoom':
      return { ...state, view: { ...state.view, scale: clampScale(state.view.scale * action.factor) } };

    case 'moveNode': {
      if (!index.byId.has(action.nodeId)) return state;
      return {
        ...state,
        moved: { ...state.moved, [action.nodeId]: { x: action.x, y: action.y } },
      };
    }

    case 'fit':
      return { ...state, view: fitViewport(visibleNodeIds(state, index), state, index) };

    case 'reset':
      return { ...state, view: { cx: 0, cy: 0, scale: 1 }, moved: {} };

    case 'clearFilters':
      return {
        ...state,
        search: '',
        typeFilter: 'all',
        communityFilter: 'all',
        relationFilter: null,
        focus: null,
        notice: null,
      };

    case 'clearFocus':
      return { ...state, focus: null, notice: null };

    case 'dismissNotice':
      return state.notice === null ? state : { ...state, notice: null };

    default: {
      // Exhaustiveness: a new action variant must be handled above. This is a
      // COMPILE-TIME check only.
      const never: never = action;
      void never;
      // At RUNTIME an unrecognised action must leave the state untouched.
      // Returning `never` (i.e. the action object) put `undefined` in
      // `state.view`, and `viewBoxOf(undefined)` then threw and white-screened
      // the tab — reachable as soon as Slice 4 parses free text and URL state.
      return state;
    }
  }
}
