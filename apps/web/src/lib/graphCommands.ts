/*
 * graphCommands — the ONE boundary between untrusted text and the graph.
 *
 * Three front-ends feed the Project Memory graph with text a person (or a link)
 * supplied: the typed command bar (P36R Slice 4), the Assistant's bounded
 * natural-language graph intents (Slice 5), and the shareable URL. All three
 * are translated HERE into the SAME `GraphAction` values `graphModel.ts`
 * already defines, and are then applied by the SAME `applyGraphAction` reducer
 * a pointer click uses. There is no second state shape, no second resolver and
 * no second reducer — which is the whole point of the module: two front-ends
 * over one model cannot drift if neither owns a model.
 *
 * Security properties, by construction (proved by graph-commands.test.ts):
 *  - This is a FIXED-GRAMMAR parser. It reads strings and returns plain data.
 *    There is no `eval`, no `Function`, no dynamic `import()`, no string-bodied
 *    timer, no template/expression evaluator, no filesystem and no shell.
 *  - Command dispatch is a `switch` over literal verbs, never a lookup into an
 *    object keyed by user input — so `__proto__` / `constructor` are just
 *    unknown verbs, not a path to anything.
 *  - Nothing here mutates a record, an experiment or any truth-plane artifact;
 *    the only values produced are `GraphAction`s, which only ever change a
 *    read-only view of an already-fetched projection.
 *  - Identity is never guessed. Tokens are resolved by `graphModel`'s tiered
 *    `resolveNode` / `resolveCommunity`, which return a bounded candidate list
 *    or an honest miss rather than a best guess.
 */
import {
  MAX_CANDIDATES,
  applyGraphAction,
  communityOptionLabel,
  filteredNodeIds,
  graphLodLevel,
  neighborhood,
  resolveCommunity,
  resolveNode,
  shortestPath,
  visibleNodeIds,
  type GraphAction,
  type GraphIndex,
  type GraphMode,
  type GraphNotice,
  type GraphTypeFilter,
  type GraphViewState,
} from './graphModel';
import { relationDisplayLabel } from './displayLabels';
import type { DeepIndex } from './graphDeep';
import type { ApiMemoryGraphMeta } from './types';

// --------------------------------------------------------------- bounds

/** Longest command accepted. Anything longer is a syntax error, not a slow
 *  parse — the grammar has no construct that needs more. */
export const MAX_COMMAND_LENGTH = 240;
/** Longest `find` query carried in the URL. */
export const MAX_QUERY_LENGTH = 120;
/** Longest node/cluster token accepted from any source, including the URL. */
export const MAX_TOKEN_LENGTH = 256;
/** Most relation types a single `relation` command or URL parameter may name. */
export const MAX_RELATION_TOKENS = 8;
/** Ephemeral in-memory command history depth. Never persisted, never logged. */
export const MAX_HISTORY = 20;
/** Most completion suggestions offered at once. */
export const MAX_SUGGESTIONS = 6;

// ------------------------------------------------------------- catalog

export interface GraphCommandSpec {
  verb: string;
  syntax: string;
  summary: string;
  /** A directly-typeable example. Generic on purpose — real node ids come from
   *  the live index through `suggestCommands`, never from a hardcoded list. */
  example: string;
}

/**
 * The COMPLETE grammar. There is no other verb, and no way to reach behaviour
 * that is not listed here — the parser's `switch` has exactly these arms.
 */
export const GRAPH_COMMANDS: readonly GraphCommandSpec[] = [
  { verb: 'help', syntax: 'help', summary: 'List every command.', example: 'help' },
  {
    verb: 'find',
    syntax: 'find <text>',
    summary: 'Filter to nodes whose path or label contains the text.',
    example: 'find export',
  },
  {
    verb: 'select',
    syntax: 'select <node> · select none',
    summary: 'Select one node, or clear the selection.',
    example: 'select export.py',
  },
  {
    verb: 'neighbors',
    syntax: 'neighbors <node> [depth 1|2]',
    summary: 'Focus the 1-hop or 2-hop neighbourhood of a node.',
    example: 'neighbors export.py depth 2',
  },
  {
    verb: 'community',
    syntax: 'community <name|id> · community all',
    summary: 'Filter to one cluster.',
    example: 'community all',
  },
  {
    verb: 'type',
    syntax: 'type file|concept|all',
    summary: 'Filter by node type.',
    example: 'type file',
  },
  {
    verb: 'relation',
    syntax: 'relation <type>[, <type>] · relation all · relation none',
    summary: 'Restrict which reference types are drawn and travelled through.',
    example: 'relation imports',
  },
  {
    verb: 'path',
    syntax: 'path <node-a> -> <node-b>',
    summary: 'Shortest route between two nodes, or an honest no-route answer.',
    example: 'path export.py -> audit.py',
  },
  { verb: 'fit', syntax: 'fit', summary: 'Frame everything currently visible.', example: 'fit' },
  {
    verb: 'reset',
    syntax: 'reset',
    summary: 'Restore the default viewport and undo node drags.',
    example: 'reset',
  },
  {
    verb: 'clear',
    syntax: 'clear filters · clear focus',
    summary: 'Clear the filters, or the neighbourhood/path focus.',
    example: 'clear filters',
  },
] as const;

const VERB_LIST = GRAPH_COMMANDS.map((c) => c.verb).join(', ');

// -------------------------------------------------------------- parsing

export type CommandParse =
  /** Whitespace only — a no-op, not an error. */
  | { status: 'empty' }
  /** `help` — the bar shows the grammar; no graph state changes. */
  | { status: 'help' }
  /** A valid command. `actions` are applied in order by the SAME reducer a
   *  click uses; `echo` is the normalized command for the history line. */
  | { status: 'actions'; actions: GraphAction[]; echo: string }
  /** A syntax error that NAMES what was wrong. Nothing is applied. */
  | { status: 'error'; message: string };

const err = (message: string): CommandParse => ({ status: 'error', message });

/**
 * One entry in the command bar's EPHEMERAL results list. Held in React state
 * for the life of the mounted surface and nowhere else: never localStorage,
 * never sessionStorage, never a cookie, never sent to the backend, never
 * logged. `origin` distinguishes a typed command from an Assistant proposal the
 * user explicitly applied — both run through the same reducer.
 */
export interface GraphCommandHistoryEntry {
  id: number;
  command: string;
  origin: 'command' | 'assistant';
  status: 'ok' | 'error' | 'help';
  /** The honest one-line outcome, or null when the command produced no notice. */
  outcome: string | null;
}

/** Strip wrapping quotes/backticks and a trailing comma from a token. Never
 *  "corrects" the token itself — resolution stays `resolveNode`'s job. */
function cleanToken(raw: string): string {
  let t = raw.trim();
  while (t.length >= 2 && /^["'`]/.test(t) && t[t.length - 1] === t[0]) t = t.slice(1, -1).trim();
  return t.replace(/,+$/, '').trim();
}

/**
 * Parse one command line into `GraphAction`s.
 *
 * Deliberately INDEX-FREE: it is purely syntactic. Whether a node, cluster or
 * relation token actually exists is decided later by the reducer's resolvers,
 * so a typed command, a clicked control and an Assistant proposal all fail (and
 * report candidates) through exactly the same code.
 */
export function parseGraphCommand(raw: string): CommandParse {
  if (typeof raw !== 'string') return err('A command must be text.');
  const line = raw.replace(/\s+/g, ' ').trim();
  if (line === '') return { status: 'empty' };
  if (line.length > MAX_COMMAND_LENGTH) {
    return err(
      `A command may be at most ${MAX_COMMAND_LENGTH} characters — this one is ${line.length}. Nothing was run.`,
    );
  }

  const gap = line.indexOf(' ');
  const verb = (gap === -1 ? line : line.slice(0, gap)).toLowerCase();
  const rest = gap === -1 ? '' : line.slice(gap + 1).trim();

  // A `switch` over literal verbs — never a lookup keyed by user input.
  switch (verb) {
    case 'help':
    case '?':
      return { status: 'help' };

    case 'find': {
      if (rest === '') return err('`find` needs some text — for example `find export`.');
      if (rest.length > MAX_QUERY_LENGTH) {
        return err(`A \`find\` query may be at most ${MAX_QUERY_LENGTH} characters.`);
      }
      return { status: 'actions', actions: [{ kind: 'search', query: rest }], echo: `find ${rest}` };
    }

    case 'select': {
      if (rest === '') {
        return err('`select` needs a node — for example `select export.py`, or `select none`.');
      }
      if (rest.toLowerCase() === 'none') {
        return { status: 'actions', actions: [{ kind: 'select', nodeId: null }], echo: 'select none' };
      }
      const token = cleanToken(rest);
      if (token.length > MAX_TOKEN_LENGTH) return err(tooLong('node'));
      return {
        status: 'actions',
        actions: [{ kind: 'select', nodeId: token }],
        echo: `select ${token}`,
      };
    }

    case 'neighbours':
    case 'neighbors': {
      if (rest === '') {
        return err('`neighbors` needs a node — for example `neighbors export.py depth 2`.');
      }
      let body = rest;
      let depth: 1 | 2 = 1;
      const tail = /\s+depth\s+(\S+)$/i.exec(body);
      if (tail) {
        if (tail[1] !== '1' && tail[1] !== '2') {
          return err(`\`depth\` accepts 1 or 2 — got \`${tail[1]}\`. Nothing was run.`);
        }
        depth = tail[1] === '2' ? 2 : 1;
        body = body.slice(0, tail.index).trim();
      }
      const token = cleanToken(body);
      if (token === '') {
        return err('`neighbors` needs a node before `depth` — for example `neighbors export.py depth 2`.');
      }
      if (token.length > MAX_TOKEN_LENGTH) return err(tooLong('node'));
      return {
        status: 'actions',
        actions: [{ kind: 'neighbors', nodeId: token, depth }],
        echo: `neighbors ${token}${depth === 2 ? ' depth 2' : ''}`,
      };
    }

    case 'community': {
      if (rest === '') {
        return err('`community` needs a cluster name or id — or `community all` to clear it.');
      }
      const token = cleanToken(rest);
      if (token.length > MAX_TOKEN_LENGTH) return err(tooLong('cluster'));
      const id = token.toLowerCase() === 'all' ? 'all' : token;
      return {
        status: 'actions',
        actions: [{ kind: 'filterCommunity', id }],
        echo: `community ${id}`,
      };
    }

    case 'type': {
      const value = rest.toLowerCase();
      if (value === '') return err('`type` needs a value — `file`, `concept`, or `all`.');
      if (value !== 'file' && value !== 'concept' && value !== 'all') {
        return err(`\`type\` accepts file, concept, or all — got \`${rest}\`. Nothing was run.`);
      }
      return {
        status: 'actions',
        actions: [{ kind: 'filterType', value: value as GraphTypeFilter }],
        echo: `type ${value}`,
      };
    }

    case 'relation': {
      if (rest === '') {
        return err(
          '`relation` needs a relationship type — or `relation all` for every type, `relation none` for none.',
        );
      }
      const lowered = rest.toLowerCase();
      if (lowered === 'all') {
        return {
          status: 'actions',
          actions: [{ kind: 'filterRelation', relations: null }],
          echo: 'relation all',
        };
      }
      if (lowered === 'none') {
        return {
          status: 'actions',
          actions: [{ kind: 'filterRelation', relations: [] }],
          echo: 'relation none',
        };
      }
      const tokens = rest
        .split(/[,\s]+/)
        .map((t) => cleanToken(t))
        .filter((t) => t !== '');
      if (tokens.length === 0) return err('`relation` needs at least one relationship type.');
      if (tokens.length > MAX_RELATION_TOKENS) {
        return err(`\`relation\` accepts at most ${MAX_RELATION_TOKENS} types at once.`);
      }
      if (tokens.some((t) => t.length > MAX_TOKEN_LENGTH)) return err(tooLong('relationship type'));
      return {
        status: 'actions',
        actions: [{ kind: 'filterRelation', relations: tokens }],
        echo: `relation ${tokens.join(', ')}`,
      };
    }

    case 'path': {
      if (rest === '') {
        return err('`path` needs two nodes — for example `path export.py -> audit.py`.');
      }
      // A typed arrow is accepted alongside `->`; nothing else separates.
      const parts = rest.replace(/→/g, '->').split('->');
      if (parts.length !== 2) {
        return err(
          '`path` needs exactly one `->` between two nodes — for example `path export.py -> audit.py`.',
        );
      }
      const from = cleanToken(parts[0]);
      const to = cleanToken(parts[1]);
      if (from === '' || to === '') {
        return err('`path` needs a node on BOTH sides of `->` — for example `path export.py -> audit.py`.');
      }
      if (from.length > MAX_TOKEN_LENGTH || to.length > MAX_TOKEN_LENGTH) return err(tooLong('node'));
      return { status: 'actions', actions: [{ kind: 'path', from, to }], echo: `path ${from} -> ${to}` };
    }

    case 'fit':
      if (rest !== '') return err('`fit` takes no arguments.');
      return { status: 'actions', actions: [{ kind: 'fit' }], echo: 'fit' };

    case 'reset':
      if (rest !== '') return err('`reset` takes no arguments.');
      return { status: 'actions', actions: [{ kind: 'reset' }], echo: 'reset' };

    case 'clear': {
      const what = rest.toLowerCase();
      if (what === '') {
        return err('`clear` needs a target — `clear filters` or `clear focus`.');
      }
      if (what === 'filters' || what === 'filter') {
        return { status: 'actions', actions: [{ kind: 'clearFilters' }], echo: 'clear filters' };
      }
      if (what === 'focus') {
        return { status: 'actions', actions: [{ kind: 'clearFocus' }], echo: 'clear focus' };
      }
      return err(`\`clear\` accepts filters or focus — got \`${rest}\`. Nothing was run.`);
    }

    default:
      return err(`Unknown command \`${verb}\`. Supported commands: ${VERB_LIST}. Type \`help\` for the syntax.`);
  }
}

const tooLong = (what: string): string =>
  `That ${what} is longer than ${MAX_TOKEN_LENGTH} characters, so it was not run.`;

// ---------------------------------------------------------- suggestions

export interface CommandSuggestion {
  /** The full command line this suggestion would produce. */
  value: string;
  /** Short right-hand hint (syntax or node kind). Never a claim. */
  hint: string;
}

function nodeSuggestions(token: string, index: GraphIndex, prefix: string): CommandSuggestion[] {
  const needle = token.trim().toLowerCase();
  const matches = index.nodes
    .filter((n) => {
      if (needle === '') return true;
      const id = n.id.toLowerCase();
      return id.includes(needle) || (n.label ?? '').toLowerCase().includes(needle);
    })
    .slice(0, MAX_SUGGESTIONS);
  return matches.map((n) => ({ value: `${prefix}${n.id}`, hint: n.kind }));
}

/**
 * Bounded completions for the current input. Pure: a function of the typed text
 * and the already-fetched index — no fetch, no history, no ranking model.
 */
export function suggestCommands(raw: string, index: GraphIndex): CommandSuggestion[] {
  const line = raw.replace(/\s+/g, ' ').trimStart();
  const gap = line.indexOf(' ');

  if (gap === -1) {
    const typed = line.toLowerCase();
    return GRAPH_COMMANDS.filter((c) => c.verb.startsWith(typed))
      .slice(0, MAX_SUGGESTIONS)
      .map((c) => ({
        value: c.verb === 'fit' || c.verb === 'reset' || c.verb === 'help' ? c.verb : `${c.verb} `,
        hint: c.syntax,
      }));
  }

  const verb = line.slice(0, gap).toLowerCase();
  const rest = line.slice(gap + 1);
  const restLower = rest.trim().toLowerCase();

  if (verb === 'type') {
    return ['file', 'concept', 'all']
      .filter((v) => v.startsWith(restLower))
      .map((v) => ({ value: `type ${v}`, hint: 'node type' }));
  }
  if (verb === 'clear') {
    return ['filters', 'focus']
      .filter((v) => v.startsWith(restLower))
      .map((v) => ({ value: `clear ${v}`, hint: 'clear target' }));
  }
  if (verb === 'relation') {
    return [...index.relationTypes, 'all', 'none']
      .filter((v) => v.toLowerCase().startsWith(restLower))
      .slice(0, MAX_SUGGESTIONS)
      .map((v) => ({ value: `relation ${v}`, hint: 'relationship type' }));
  }
  if (verb === 'community') {
    const entries = index.communitiesBySize
      .filter((c) => {
        if (restLower === '') return true;
        return (c.name ?? '').toLowerCase().includes(restLower) || c.id.includes(restLower);
      })
      .slice(0, MAX_SUGGESTIONS);
    return entries.map((c) => ({
      value: `community ${c.name ?? c.id}`,
      hint: communityOptionLabel(c),
    }));
  }
  if (verb === 'select' || verb === 'neighbors' || verb === 'neighbours') {
    return nodeSuggestions(rest, index, `${verb} `);
  }
  if (verb === 'path') {
    const arrow = rest.indexOf('->');
    if (arrow === -1) return nodeSuggestions(rest, index, 'path ');
    const left = rest.slice(0, arrow).trim();
    return nodeSuggestions(rest.slice(arrow + 2), index, `path ${left} -> `);
  }
  return [];
}

// -------------------------------------------------------- notice summary

/**
 * A one-line, plain-text rendering of a reducer notice, for the command bar's
 * compact history. The canvas's live region renders the same notices richly;
 * this is the terse form, and it never says more than the notice does.
 */
export function summarizeNotice(notice: GraphNotice | null): string | null {
  if (!notice) return null;
  switch (notice.kind) {
    case 'not_found':
      return `No node matches "${notice.token}" — nothing was selected.`;
    case 'ambiguous':
      return `"${notice.token}" matches ${notice.candidates.length} nodes — no identity was assumed. Pick one above.`;
    case 'community_not_found':
      return `No cluster matches "${notice.token}" — the cluster filter was left as it was.`;
    case 'community_ambiguous':
      return `"${notice.token}" matches ${notice.candidates.length} clusters — none was assumed.`;
    case 'relation_unknown':
      return `Not a relationship type in this projection: ${notice.tokens.join(', ')}.`;
    case 'no_path':
      return `No route connects ${notice.from} and ${notice.to} in this projection.`;
    case 'path_found':
      return `${notice.hops}-step route from ${notice.from} to ${notice.to}.`;
    case 'neighborhood': {
      const shown = `${notice.count} node${notice.count === 1 ? '' : 's'} shown`;
      const bound = notice.truncated ? ' (display bound reached)' : '';
      // `count` is what is drawn; `neighborhoodSize` is the neighbourhood
      // itself. Saying only the second one is how "14 nodes" got announced over
      // a canvas reading "0 of 220".
      if (notice.count < notice.neighborhoodSize) {
        return (
          `${notice.depth}-hop neighbourhood of ${notice.nodeId} — ${notice.neighborhoodSize} node` +
          `${notice.neighborhoodSize === 1 ? '' : 's'} in it, ${shown} under the current filters${bound}.`
        );
      }
      return `${notice.depth}-hop neighbourhood of ${notice.nodeId} — ${shown}${bound}.`;
    }
    default:
      return null;
  }
}

/**
 * The terse spoken outcome of ONE applied command.
 *
 * Seven of the eleven verbs (`find`, `select`, `community`, `type`, `relation`,
 * `fit`, `clear`) leave the reducer's `notice` null, so before this they were
 * announced as nothing at all — a screen-reader user got silence for every
 * filter and selection they ran. This is the single string used BOTH for the
 * live-region announcement and for the compact history line, so the two can
 * never say different things.
 *
 * Every number in it is read back out of the state the reducer actually
 * produced, using the SAME selectors the visible count line uses.
 */
export function describeCommandOutcome(
  echo: string,
  next: GraphViewState,
  index: GraphIndex,
): string {
  const noticed = summarizeNotice(next.notice);
  if (noticed) return noticed;
  const shown =
    next.mode === 'explore'
      ? visibleNodeIds(next, index).length
      : filteredNodeIds(next, index).length;
  const tail = `${shown} of ${index.counts.total} nodes shown.`;
  const verb = echo.split(' ')[0].toLowerCase();
  switch (verb) {
    case 'select':
      return next.selectedId
        ? `Selected ${next.selectedId}. ${tail}`
        : `Selection cleared. ${tail}`;
    case 'fit':
      return `Framed the visible nodes — ${tail}`;
    case 'reset':
      return `Viewport reset and node drags undone — ${tail}`;
    case 'clear':
      return `${echo.toLowerCase() === 'clear focus' ? 'Focus cleared' : 'Filters cleared'} — ${tail}`;
    default:
      return `${echo} — ${tail}`;
  }
}

// -------------------------------------------------------------- URL state

/**
 * The COMPLETE set of graph query parameters. Anything not on this list is not
 * read, and every value is validated below before it becomes an action.
 */
export const GRAPH_URL_PARAMS = [
  'gmode',
  'gq',
  'gtype',
  'gcomm',
  'grel',
  'gnode',
  'gnbr',
  'gdepth',
  'gfrom',
  'gto',
] as const;

export type GraphUrlParam = (typeof GRAPH_URL_PARAMS)[number];
export type ParamReader = (name: GraphUrlParam) => string | null;

/** A bounded string, or null. Over-long values are DROPPED at the boundary
 *  rather than truncated — a truncated node id is a different node id. */
function bounded(value: string | null, max: number): string | null {
  if (typeof value !== 'string') return null;
  const t = value.trim();
  if (t === '' || t.length > max) return null;
  return t;
}

/**
 * Decode URL parameters into actions.
 *
 * This is the validation boundary for link-supplied state: every parameter is
 * read by name from a fixed list, length-bounded, and — where the grammar has a
 * closed set — checked against that set. Node and cluster tokens are NOT
 * validated here on purpose: they go on to `resolveNode` / `resolveCommunity`
 * in the reducer, which is the one place identity is decided, and which reports
 * an honest miss instead of guessing.
 */
export function decodeGraphActions(get: ParamReader): GraphAction[] {
  const actions: GraphAction[] = [];

  const mode = get('gmode');
  if (mode === 'explore' || mode === 'browse') actions.push({ kind: 'setMode', mode });

  const type = get('gtype');
  if (type === 'file' || type === 'concept' || type === 'all') {
    actions.push({ kind: 'filterType', value: type });
  }

  const comm = bounded(get('gcomm'), MAX_TOKEN_LENGTH);
  if (comm) actions.push({ kind: 'filterCommunity', id: comm });

  const rel = get('grel');
  if (typeof rel === 'string') {
    const tokens = rel
      .split(',')
      .map((t) => t.trim())
      .filter((t) => t !== '' && t.length <= MAX_TOKEN_LENGTH)
      .slice(0, MAX_RELATION_TOKENS);
    // An EMPTY `grel=` is the honest "no relationship types", not "all types" —
    // `relationFilter: []` is a real state the reducer already models. Absent
    // means no filter at all.
    actions.push({ kind: 'filterRelation', relations: tokens });
  }

  const q = bounded(get('gq'), MAX_QUERY_LENGTH);
  if (q) actions.push({ kind: 'search', query: q });

  const nbr = bounded(get('gnbr'), MAX_TOKEN_LENGTH);
  const from = bounded(get('gfrom'), MAX_TOKEN_LENGTH);
  const to = bounded(get('gto'), MAX_TOKEN_LENGTH);
  const node = bounded(get('gnode'), MAX_TOKEN_LENGTH);
  if (nbr) {
    // ABSENT `gdepth` ⇒ the documented default of 1. PRESENT but outside {1,2}
    // ⇒ the link asked for something the grammar does not have, so the whole
    // neighbourhood request is DROPPED. Coercing `gdepth=99` to 1 was the one
    // URL value silently corrected into a different, plausible-looking view
    // instead of refused — `neighbors x depth 3` is already refused by the
    // parser with "Nothing was run", and every other out-of-set parameter here
    // is dropped rather than repaired.
    const rawDepth = get('gdepth');
    if (rawDepth === null || rawDepth === '1' || rawDepth === '2') {
      actions.push({ kind: 'neighbors', nodeId: nbr, depth: rawDepth === '2' ? 2 : 1 });
    }
  } else if (from && to) {
    actions.push({ kind: 'path', from, to });
  } else if (node) {
    actions.push({ kind: 'select', nodeId: node });
  }

  return actions;
}

/**
 * Encode the SHAREABLE part of the view: mode, filters, search, and the current
 * selection or focus. The viewport (pan / zoom) and node drags are deliberately
 * NOT encoded — they are a local reading position, not state worth pinning a
 * link to, and encoding them would make every drag a history entry.
 */
export function encodeGraphParams(state: GraphViewState): Record<string, string> {
  const out: Record<string, string> = { gmode: state.mode };
  const search = state.search.trim();
  // DROPPED, never truncated. A truncated query is a strictly BROADER filter, so
  // a truncated link would show its recipient MORE nodes than its author saw —
  // the one direction a shareable link must never fail in. Every writer of
  // `search` is itself bounded to MAX_QUERY_LENGTH (the search input's
  // `maxLength`, the `find` grammar, `findProposal`, and `gq` on the way in), so
  // this is a boundary guard rather than a reachable path.
  if (search !== '' && search.length <= MAX_QUERY_LENGTH) out.gq = search;
  if (state.typeFilter !== 'all') out.gtype = state.typeFilter;
  if (state.communityFilter !== 'all') out.gcomm = state.communityFilter;
  if (state.relationFilter !== null) out.grel = state.relationFilter.join(',');
  if (state.focus?.kind === 'neighbors') {
    out.gnbr = state.focus.nodeId;
    out.gdepth = String(state.focus.depth);
  } else if (state.focus?.kind === 'path') {
    out.gfrom = state.focus.from;
    out.gto = state.focus.to;
  } else if (state.selectedId) {
    out.gnode = state.selectedId;
  }
  return out;
}

/** A stable string identity for the graph parameters in a URL — used to tell an
 *  EXTERNAL change (back/forward, an applied Assistant proposal) from the echo
 *  of a write this surface just made. */
export function graphParamKey(get: ParamReader): string {
  return GRAPH_URL_PARAMS.map((k) => `${k}=${get(k) ?? ''}`).join('&');
}

/** The default mode a URL with no `gmode` implies, given the viewport. Narrow
 *  viewports open in Browse — a 220-node canvas is not a phone surface. */
export function defaultGraphMode(): GraphMode {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return 'explore';
  return window.matchMedia('(max-width: 860px)').matches ? 'browse' : 'explore';
}

// ------------------------------------------------- natural-language intents

/**
 * The FROZEN intent catalog. This is pattern matching over a closed list — no
 * model, no provider, no embedding, no vector search, no scoring. Every intent
 * below is a literal RegExp evaluated in this fixed order, first match wins.
 */
export const GRAPH_INTENTS = [
  'graph_neighbors',
  'graph_path',
  'graph_community_contents',
  'graph_community',
  'graph_relation',
  'graph_type',
  'graph_find',
  'graph_reset',
  'graph_clear_filters',
] as const;

export type GraphIntentName = (typeof GRAPH_INTENTS)[number];

export interface GraphIntentContext {
  /**
   * The LIVE view state of the mounted graph surface, verbatim.
   *
   * It is the WHOLE state on purpose. Every count a proposal states is produced
   * by folding that proposal's own actions onto this state with the real
   * `applyGraphAction` and then asking the model's own `visibleNodeIds` — the
   * exact reducer and the exact selector the "Apply to Graph" button runs. A
   * narrower context (say, just the cluster and relationship filters) forces a
   * PARALLEL estimate, and a parallel estimate drifts: it announced "Focusing it
   * draws 14 nodes" while `type concept` was active and the canvas then read
   * "0 of 220 nodes shown".
   */
  state: GraphViewState;
}

// --- what applying would ACTUALLY show ---------------------------------------

interface ApplyOutcome {
  /** ids the canvas would draw */
  ids: string[];
  /** ids passing the filters before the render bound (the Browse count) */
  matched: number;
  /** restrictions already in force that this proposal does NOT itself set */
  carried: string[];
}

/**
 * Restrictions that were ALREADY active and are still narrowing the result.
 *
 * A dimension the proposal's own actions set is excluded twice over: by the
 * before/after comparison, and by the action-kind check — so "show only
 * concepts" never reports the concept filter it is itself proposing as an
 * obstacle to itself.
 */
function carriedRestrictions(
  before: GraphViewState,
  after: GraphViewState,
  actions: readonly GraphAction[],
): string[] {
  const kinds = new Set(actions.map((a) => a.kind));
  const owns = (kind: GraphAction['kind']): boolean => kinds.has(kind) || kinds.has('clearFilters');
  const out: string[] = [];
  if (!owns('filterType') && after.typeFilter !== 'all' && after.typeFilter === before.typeFilter) {
    out.push(`the node-type filter \`type ${after.typeFilter}\``);
  }
  if (
    !owns('filterCommunity') &&
    after.communityFilter !== 'all' &&
    after.communityFilter === before.communityFilter
  ) {
    out.push('the cluster filter');
  }
  const search = after.search.trim();
  if (!owns('search') && search !== '' && after.search === before.search) {
    out.push(`the search "${search}"`);
  }
  // Focus is compared by identity: the reducer preserves the same object for a
  // filter action and builds a new one for `neighbors` / `path`.
  if (
    !owns('neighbors') &&
    !owns('path') &&
    !owns('clearFocus') &&
    after.focus &&
    after.focus === before.focus
  ) {
    out.push(
      after.focus.kind === 'neighbors'
        ? `the focus on ${after.focus.nodeId}`
        : `the route focus ${after.focus.from} → ${after.focus.to}`,
    );
  }
  return out;
}

/**
 * Fold `actions` through the REAL reducer, from the REAL live state, and read
 * the result with the model's own selectors.
 *
 * This is deliberately not an approximation of what Apply does — it is what
 * Apply does. `applyGraphAction` and `visibleNodeIds` are the same functions the
 * surface calls, so a number derived here cannot disagree with the number the
 * canvas shows one click later.
 */
function outcomeOf(
  actions: readonly GraphAction[],
  index: GraphIndex,
  ctx: GraphIntentContext,
): ApplyOutcome {
  const before = ctx.state;
  let after = before;
  for (const action of actions) after = applyGraphAction(after, action, index);
  return {
    ids: visibleNodeIds(after, index),
    matched: filteredNodeIds(after, index).length,
    carried: carriedRestrictions(before, after, actions),
  };
}

const listOf = (parts: readonly string[]): string => parts.join(', ');

/**
 * The one sentence every count-bearing proposal ends with: what applying it
 * would ACTUALLY put on screen. A result of zero is stated as zero, with the
 * filters responsible named and the command that clears them offered — never
 * dressed up as a successful navigation with a misleading number attached.
 */
function applyOutcomeSentence(o: ApplyOutcome, total: number, focal?: string): string {
  if (o.ids.length === 0) {
    if (o.carried.length > 0) {
      return (
        `Applying it would show NOTHING: ${o.carried.length === 1 ? 'the active restriction' : 'the active restrictions'} — ` +
        `${listOf(o.carried)} — leave${o.carried.length === 1 ? 's' : ''} nothing to draw. ` +
        `Clear ${o.carried.length === 1 ? 'it' : 'them'} first with \`clear filters\` if that is not what you meant.`
      );
    }
    return (
      `Applying it would show NOTHING — no node in this projection survives it. ` +
      `That is the result itself, not a filter hiding something.`
    );
  }
  const including = focal && o.ids.includes(focal) ? `, including ${focal} itself` : '';
  const bound =
    o.matched > o.ids.length
      ? ` ${o.matched} match in Browse; the canvas draws ${o.ids.length} of them because of its display bound.`
      : '';
  const carried =
    o.carried.length > 0
      ? ` ${o.carried.length === 1 ? 'The active restriction' : 'The active restrictions'} — ${listOf(o.carried)} — still appl${o.carried.length === 1 ? 'ies' : 'y'}.`
      : '';
  return `Applying it shows ${o.ids.length} of the ${total} nodes${including}.${bound}${carried}`;
}

export type GraphProposalStatus =
  /** Resolved. `actions` may be applied — after the user asks for it. */
  | 'ready'
  /** The token matched several nodes/clusters. `choices` are bounded and each
   *  is itself a fully-resolved proposal. Nothing is applied. */
  | 'ambiguous'
  /** Nothing matched, or there is no route. Nothing to apply — said plainly. */
  | 'unresolved';

export interface GraphProposalChoice {
  label: string;
  proposal: GraphProposal;
}

export interface GraphProposal {
  intent: GraphIntentName;
  status: GraphProposalStatus;
  /** The SAME `GraphAction`s the equivalent typed command produces. */
  actions: GraphAction[];
  /** The equivalent command-bar command, shown so the two front-ends are
   *  visibly one thing. Null when there is nothing to run. */
  command: string | null;
  title: string;
  explanation: string;
  choices: GraphProposalChoice[];
}

/**
 * What the mounted graph surface exposes to its owner (Project Memory), so an
 * explicitly-applied Assistant proposal reaches the SAME reducer, the SAME URL
 * writer and the SAME results history as a typed command. Nothing here reads or
 * writes a record; the graph is a read-only view of an already-fetched
 * projection.
 */
export interface GraphSurfaceContext {
  index: GraphIndex;
  meta: ApiMemoryGraphMeta;
  /** The live view state, read on demand — the consumer never stores it. */
  peek(): GraphViewState;
  /** Apply actions from outside the surface. Called only from an explicit user
   *  action; never during classification or render. */
  apply(command: string | null, actions: GraphAction[]): void;
}

/** The Assistant-side contract. A mount that does not pass one has no graph
 *  capability at all — the four record surfaces pass nothing. */
export interface AssistantGraphCapability {
  /** Bounded, deterministic, offline classification. Null ⇒ not a graph
   *  question ⇒ the Assistant's normal path runs, untouched. */
  classify(question: string): GraphProposal | null;
  /** Applies the proposal's actions to the live graph. Called ONLY from the
   *  explicit "Apply to Graph" control — never during classification. */
  apply(proposal: GraphProposal): void;
  /** One-line provenance of the projection being navigated. */
  provenance: string;
}

const short12 = (v: string | null | undefined): string => (v ? v.slice(0, 12) : '—');

/** The projection's own provenance, for a proposal card. */
export function describeGraphProvenance(meta: ApiMemoryGraphMeta): string {
  const p = meta.provenance;
  return `served-file projection · commit ${short12(p.built_at_commit)} · source sha256 ${short12(
    p.source_graph_sha256,
  )} · ${p.provider}`;
}

/** Collapse whitespace and drop trailing sentence punctuation. Case is kept —
 *  node ids are case-bearing, and `resolveNode` matches case-insensitively. */
function normalizeQuestion(raw: string): string {
  if (typeof raw !== 'string') return '';
  return raw.replace(/\s+/g, ' ').trim().replace(/[?!.]+$/, '').trim();
}

/** Strip a leading article from an extracted token. Deterministic, documented,
 *  and never applied to the middle of a token. */
function stripArticle(token: string): string {
  return cleanToken(token).replace(/^(?:the|a|an)\s+/i, '').trim();
}

const unresolved = (
  intent: GraphIntentName,
  title: string,
  explanation: string,
): GraphProposal => ({ intent, status: 'unresolved', actions: [], command: null, title, explanation, choices: [] });

/**
 * Resolve a node token for an intent, or explain honestly. Ambiguity produces a
 * BOUNDED choice list where every entry is the same proposal resolved to one
 * specific node — never a guess, never a silent pick.
 */
function withNode(
  token: string,
  index: GraphIndex,
  intent: GraphIntentName,
  onFound: (id: string) => GraphProposal,
): GraphProposal {
  if (token === '') {
    return unresolved(intent, 'No node was named', 'I could not tell which node you meant, so nothing was resolved.');
  }
  const r = resolveNode(token, index);
  if (r.status === 'found') return onFound(r.id);
  if (r.status === 'ambiguous') {
    return {
      intent,
      status: 'ambiguous',
      actions: [],
      command: null,
      title: `"${token}" matches ${r.candidates.length} nodes`,
      explanation:
        `"${token}" matches ${r.candidates.length} nodes in this projection, so no identity was assumed. ` +
        `Pick the one you meant and I will propose the same navigation for it.`,
      choices: r.candidates.slice(0, MAX_CANDIDATES).map((id) => ({ label: id, proposal: onFound(id) })),
    };
  }
  return unresolved(
    intent,
    `No node matches "${token}"`,
    `No node in this projection matches "${token}". Nothing was changed and no approximate match was substituted. ` +
      `Project Memory covers only the files this deployment serves, so the node may simply not be in it.`,
  );
}

function neighborsProposal(
  id: string,
  depth: 1 | 2,
  index: GraphIndex,
  ctx: GraphIntentContext,
): GraphProposal {
  const actions: GraphAction[] = [{ kind: 'neighbors', nodeId: id, depth }];
  const hood = neighborhood(id, depth, index, ctx.state.relationFilter);
  const others = Math.max(0, hood.ids.length - 1);
  return {
    intent: 'graph_neighbors',
    status: 'ready',
    actions,
    command: `neighbors ${id}${depth === 2 ? ' depth 2' : ''}`,
    title: `Focus the ${depth}-hop neighbourhood of ${id}`,
    explanation:
      `${id} has ${others} node${others === 1 ? '' : 's'} within ${depth} hop${depth === 1 ? '' : 's'} ` +
      `in this served-file projection${ctx.state.relationFilter ? ' under the current relationship filter' : ''}` +
      `${hood.truncated ? ', and the neighbourhood reached its display bound' : ''}. ` +
      // The second figure is not the neighbourhood size: it is what the reducer
      // and `visibleNodeIds` produce from the LIVE state, because the focus set
      // is then intersected with whatever type / cluster / search filter is on.
      `${applyOutcomeSentence(outcomeOf(actions, index, ctx), index.counts.total, id)} ` +
      `A reference between two files is a navigational lead, not a scientific relationship.`,
    choices: [],
  };
}

function pathProposal(
  from: string,
  to: string,
  index: GraphIndex,
  ctx: GraphIntentContext,
): GraphProposal {
  const route = shortestPath(from, to, index, ctx.state.relationFilter);
  if (route === null) {
    return unresolved(
      'graph_path',
      `No route connects ${from} and ${to}`,
      `No route connects ${from} and ${to} in this projection${ctx.state.relationFilter ? ' under the current relationship filter' : ''} — ` +
        `they sit in separate components. That is the honest answer, not a display limit, and no connection was invented.`,
    );
  }
  const actions: GraphAction[] = [{ kind: 'path', from, to }];
  const hops = route.length - 1;
  const shown = route.slice(0, 6).join(' → ');
  return {
    intent: 'graph_path',
    status: 'ready',
    actions,
    command: `path ${from} -> ${to}`,
    title: `Show the ${hops}-step route from ${from} to ${to}`,
    explanation:
      `A ${hops}-step route exists: ${shown}${route.length > 6 ? ' …' : ''}. ` +
      `${applyOutcomeSentence(outcomeOf(actions, index, ctx), index.counts.total)} ` +
      `A route means these files reference one another in the project source — a navigational lead, never a scientific relationship.`,
    choices: [],
  };
}

function communityProposal(
  id: string,
  index: GraphIndex,
  note: string,
  ctx: GraphIntentContext,
): GraphProposal {
  const entry = index.communityById.get(id);
  const label = entry ? communityOptionLabel(entry) : `cluster ${id}`;
  const members = index.byCommunity.get(id) ?? [];
  const actions: GraphAction[] = [{ kind: 'filterCommunity', id }];
  return {
    intent: 'graph_community',
    status: 'ready',
    actions,
    command: `community ${id}`,
    title: `Filter the graph to ${label}`,
    explanation:
      `${label}${note} holds ${members.length} node${members.length === 1 ? '' : 's'} in this projection. ` +
      `${applyOutcomeSentence(outcomeOf(actions, index, ctx), index.counts.total)} ` +
      `Clusters are derived automatically by the upstream graph builder and named after one representative node — ` +
      `advisory groupings, not categories the schema recognises.`,
    choices: [],
  };
}

function communityForToken(
  token: string,
  index: GraphIndex,
  ctx: GraphIntentContext,
): GraphProposal {
  const c = resolveCommunity(token, index);
  if (c.status === 'found') return communityProposal(c.id, index, '', ctx);
  if (c.status === 'ambiguous') {
    return {
      intent: 'graph_community',
      status: 'ambiguous',
      actions: [],
      command: null,
      title: `"${token}" matches ${c.candidates.length} clusters`,
      explanation: `"${token}" matches ${c.candidates.length} clusters, so none was assumed. Pick the one you meant:`,
      choices: c.candidates.map((id) => ({
        label: index.communityById.get(id) ? communityOptionLabel(index.communityById.get(id)!) : id,
        proposal: communityProposal(id, index, '', ctx),
      })),
    };
  }
  // Not a cluster name — try reading it as a NODE and using that node's cluster.
  const n = resolveNode(token, index);
  const forNode = (id: string): GraphProposal => {
    const node = index.byId.get(id);
    if (!node?.community_id) {
      return unresolved(
        'graph_community',
        `${id} is in no cluster`,
        `${id} carries no cluster in this projection, so there is no cluster to filter to. Nothing was changed.`,
      );
    }
    return communityProposal(node.community_id, index, ` (the cluster holding ${id})`, ctx);
  };
  if (n.status === 'found') return forNode(n.id);
  if (n.status === 'ambiguous') {
    return {
      intent: 'graph_community',
      status: 'ambiguous',
      actions: [],
      command: null,
      title: `"${token}" matches ${n.candidates.length} nodes`,
      explanation:
        `"${token}" is not a cluster name, and it matches ${n.candidates.length} nodes — so no cluster was assumed. ` +
        `Pick the node whose cluster you meant:`,
      choices: n.candidates.map((id) => ({ label: id, proposal: forNode(id) })),
    };
  }
  return unresolved(
    'graph_community',
    `No cluster or node matches "${token}"`,
    `No cluster name and no node in this projection matches "${token}", so no cluster was chosen. Nothing was changed.`,
  );
}

function relationProposal(token: string, index: GraphIndex): GraphProposal {
  const needle = token.toLowerCase();
  const exact = index.relationTypes.filter((r) => r.toLowerCase() === needle);
  const prefix = index.relationTypes.filter((r) => r.toLowerCase().startsWith(needle));
  const sub = index.relationTypes.filter((r) => r.toLowerCase().includes(needle));
  const ready = (rel: string): GraphProposal => ({
    intent: 'graph_relation',
    status: 'ready',
    actions: [{ kind: 'filterRelation', relations: [rel] }],
    command: `relation ${rel}`,
    title: `Draw only ${rel} references`,
    explanation:
      `${rel} is one of the ${index.relationTypes.length} relationship types the backend recorded in this projection. ` +
      `Restricting to it also stops neighbourhoods and routes travelling through the other types.`,
    choices: [],
  });
  for (const tier of [exact, prefix, sub]) {
    if (tier.length === 1) return ready(tier[0]);
    if (tier.length > 1) {
      return {
        intent: 'graph_relation',
        status: 'ambiguous',
        actions: [],
        command: null,
        title: `"${token}" matches ${tier.length} relationship types`,
        explanation: `"${token}" matches ${tier.length} of this projection's relationship types, so none was assumed. Pick one:`,
        choices: tier.slice(0, MAX_CANDIDATES).map((r) => ({ label: r, proposal: ready(r) })),
      };
    }
  }
  return unresolved(
    'graph_relation',
    `"${token}" is not a relationship type here`,
    `This projection records ${index.relationTypes.length} relationship type${index.relationTypes.length === 1 ? '' : 's'}` +
      `${index.relationTypes.length > 0 ? ` — ${index.relationTypes.join(', ')}` : ''}. "${token}" is not one of them, so the filter was left as it was.`,
  );
}

function findProposal(
  query: string,
  type: GraphTypeFilter,
  index: GraphIndex,
  ctx: GraphIntentContext,
): GraphProposal {
  if (query.trim() === '') {
    return unresolved(
      'graph_find',
      'No search text was given',
      'I could not tell what to search for, so no filter was proposed.',
    );
  }
  // The SAME bound the `find` grammar and the `gq` parameter enforce. Without it
  // an over-long query becomes a `search` the URL encoder must then drop, which
  // silently widens a shared link.
  if (query.length > MAX_QUERY_LENGTH) {
    return unresolved(
      'graph_find',
      'That search text is too long',
      `A graph search is bounded to ${MAX_QUERY_LENGTH} characters, and this one is ${query.length}. ` +
        `Nothing was proposed and nothing was truncated — a shortened query is a different, broader filter.`,
    );
  }
  const actions: GraphAction[] = [];
  const parts: string[] = [];
  if (type !== 'all') {
    actions.push({ kind: 'filterType', value: type });
    parts.push(`type ${type}`);
  }
  actions.push({ kind: 'search', query });
  parts.push(`find ${query}`);
  // The count comes from folding these actions through the real reducer — NOT
  // from a private copy of the search predicate. The copy that used to live here
  // scanned every node in the index, ignoring the active cluster/type filter and
  // the render bound, and it had already drifted from `matchesFilters` by a
  // missing `.trim()`. That rule has one home: `graphModel`.
  return {
    intent: 'graph_find',
    status: 'ready',
    actions,
    command: parts.join(' · '),
    title: `Filter the graph to "${query}"`,
    explanation:
      `${applyOutcomeSentence(outcomeOf(actions, index, ctx), index.counts.total)} ` +
      `This is a text filter over the served-file projection — a set of leads to look at, not a statement that they are related in any scientific sense.`,
    choices: [],
  };
}

// --- the bounded pattern set. Literal RegExps, fixed order, first match wins.

const RE_NEIGHBORS =
  /^(?:can you |please |could you )?(?:show|list|display|find|give)?\s*(?:me )?(?:the )?(?:(\d)[-\s]hop )?neighbou?rs?(?:hood)?\s+(?:of|for)\s+(.+?)(?:\s+(?:at\s+)?depth\s+(\d))?$/i;
const RE_CONNECTED_TO =
  /^(?:can you |please )?(?:show|list|display)?\s*(?:me )?(?:what|which nodes?|which files?)\s+(?:is|are)\s+connected\s+to\s+(.+)$/i;
const RE_CONNECTIONS_OF =
  /^(?:can you |please )?(?:show|list|display)\s+(?:me )?(?:the )?connections?\s+(?:of|for)\s+(.+)$/i;

const RE_PATH =
  /^(?:can you |please )?(?:show|find|give|trace)?\s*(?:me )?(?:a |the )?(?:shortest )?(?:path|route)\s+(?:from\s+)?(.+?)\s+to\s+(.+)$/i;
const RE_HOW_CONNECTED = /^how\s+(?:is|are)\s+(.+?)\s+connected\s+to\s+(.+)$/i;
const RE_IS_CONNECTED = /^is\s+(.+?)\s+connected\s+to\s+(.+)$/i;

const RE_COMMUNITY_CONTENTS =
  /^(?:what|which nodes?|which files?)\s+(?:does|is|are)?\s*(?:this|the current|the selected|that)\s+(?:community|cluster)\s*(?:contain|hold|include|have|in it)?$/i;
const RE_COMMUNITY_CONTENTS_ALT =
  /^(?:what|which nodes?|which files?)\s+(?:is|are)\s+in\s+(?:this|the current|the selected|that)\s+(?:community|cluster)$/i;

const RE_COMMUNITY_FOR =
  /^(?:can you |please )?(?:show|display|filter to|focus on|open)\s+(?:me )?(?:the )?(?:community|cluster)\s+(?:for|of|containing|holding|with)\s+(.+)$/i;
const RE_COMMUNITY_NAMED =
  /^(?:can you |please )?(?:show|display|filter to|focus on|open)\s+(?:me )?(?:the )?(?:community|cluster)\s+(.+)$/i;
const RE_WHICH_COMMUNITY =
  /^(?:which|what)\s+(?:community|cluster)\s+(?:is|does)\s+(.+?)\s+(?:in|belong to)$/i;

const RE_ALL_RELATIONS = /^(?:show|display|include)\s+(?:me\s+)?all\s+relationships?(?:\s+types?)?$/i;
const RE_RELATION_ONLY =
  /^(?:only\s+)?(?:show|display|draw|filter to|keep)\s+(?:only\s+)?(?:the\s+)?(.+?)\s+relationships?$/i;
const RE_RELATION_OF_TYPE =
  /^(?:only\s+)?(?:show|display|draw|filter to|keep)\s+(?:only\s+)?relationships?\s+(?:of\s+type\s+)?(.+)$/i;

const RE_TYPE_ONLY = /^(?:show|display|filter to)\s+only\s+(files?|concepts?)$/i;
const RE_TYPE_BOTH = /^(?:show|display)\s+(?:both\s+)?files\s+and\s+concepts$/i;

const RE_FIND_RELATED =
  /^(?:find|show|list)\s+(?:me\s+)?(?:the\s+|all\s+)?(files?|nodes?|concepts?)\s+(?:related|connected|linked)\s+to\s+(.+)$/i;
const RE_SEARCH_GRAPH = /^(?:search|find\s+in)\s+(?:the\s+)?graph\s+for\s+(.+)$/i;

const RE_RESET = /^reset\s+(?:the\s+)?graph(?:\s+view)?$/i;
const RE_CLEAR_FILTERS = /^clear\s+(?:the\s+|all\s+)?(?:graph\s+)?filters$/i;

/**
 * Classify a free-form question against the bounded graph intent catalog.
 *
 * NOT an LLM. There is no model, no provider, no network call, no embedding and
 * no learned scoring anywhere in this function or anything it calls — only the
 * literal RegExps above, evaluated in a fixed order, plus `graphModel`'s
 * deterministic resolvers. It returns `null` for ANYTHING it does not
 * confidently recognise, and the Assistant then runs its normal path unchanged:
 * a miss is deliberately preferred to hijacking an ordinary memory question.
 */
export function classifyGraphQuestion(
  question: string,
  index: GraphIndex,
  ctx: GraphIntentContext,
): GraphProposal | null {
  const q = normalizeQuestion(question);
  if (q === '' || q.length > MAX_COMMAND_LENGTH * 2) return null;

  // 1 — neighbourhood
  const nbr = RE_NEIGHBORS.exec(q);
  if (nbr) {
    const depthToken = nbr[3] ?? nbr[1];
    if (depthToken && depthToken !== '1' && depthToken !== '2') {
      return unresolved(
        'graph_neighbors',
        `Depth ${depthToken} is not available`,
        `Neighbourhoods are bounded to 1 or 2 hops in this projection, so depth ${depthToken} was not run.`,
      );
    }
    const depth: 1 | 2 = depthToken === '2' ? 2 : 1;
    return withNode(stripArticle(nbr[2]), index, 'graph_neighbors', (id) =>
      neighborsProposal(id, depth, index, ctx),
    );
  }
  const conn = RE_CONNECTED_TO.exec(q) ?? RE_CONNECTIONS_OF.exec(q);
  if (conn) {
    return withNode(stripArticle(conn[1]), index, 'graph_neighbors', (id) =>
      neighborsProposal(id, 1, index, ctx),
    );
  }

  // 2 — shortest path
  const path = RE_PATH.exec(q) ?? RE_HOW_CONNECTED.exec(q) ?? RE_IS_CONNECTED.exec(q);
  if (path) {
    const fromToken = stripArticle(path[1]);
    const toToken = stripArticle(path[2]);
    return withNode(fromToken, index, 'graph_path', (a) =>
      withNode(toToken, index, 'graph_path', (b) => pathProposal(a, b, index, ctx)),
    );
  }

  // 3 — "what does this cluster contain"
  if (RE_COMMUNITY_CONTENTS.test(q) || RE_COMMUNITY_CONTENTS_ALT.test(q)) {
    const active =
      ctx.state.communityFilter !== 'all'
        ? ctx.state.communityFilter
        : (ctx.state.selectedId
            ? (index.byId.get(ctx.state.selectedId)?.community_id ?? null)
            : null);
    if (!active) {
      return unresolved(
        'graph_community_contents',
        'No cluster is in focus',
        'No cluster is currently filtered to and no selected node carries one, so there is no "this cluster" to describe. ' +
          'Name one — for example `community <name>` — or select a node first.',
      );
    }
    const entry = index.communityById.get(active);
    const members = index.byCommunity.get(active) ?? [];
    const shown = members.slice(0, 8);
    const actions: GraphAction[] = [{ kind: 'filterCommunity', id: active }];
    return {
      intent: 'graph_community_contents',
      status: 'ready',
      actions,
      command: `community ${active}`,
      title: `Describe ${entry ? communityOptionLabel(entry) : `cluster ${active}`}`,
      explanation:
        `${entry ? communityOptionLabel(entry) : `Cluster ${active}`} holds ${members.length} node${members.length === 1 ? '' : 's'} in this projection` +
        `${shown.length > 0 ? `: ${shown.join(', ')}${members.length > shown.length ? `, and ${members.length - shown.length} more` : ''}` : ''}. ` +
        `${applyOutcomeSentence(outcomeOf(actions, index, ctx), index.counts.total)} ` +
        `Clusters are automatically derived, advisory groupings — not schema categories.`,
      choices: [],
    };
  }

  // 4 — cluster by name, by member node, or "which cluster is X in"
  const commFor = RE_COMMUNITY_FOR.exec(q) ?? RE_WHICH_COMMUNITY.exec(q);
  if (commFor) return communityForToken(stripArticle(commFor[1]), index, ctx);
  const commNamed = RE_COMMUNITY_NAMED.exec(q);
  if (commNamed) {
    const token = stripArticle(commNamed[1]);
    if (token.toLowerCase() === 'all' || token.toLowerCase() === 'clusters') {
      return {
        intent: 'graph_community',
        status: 'ready',
        actions: [{ kind: 'filterCommunity', id: 'all' }],
        command: 'community all',
        title: 'Show every cluster',
        explanation: `Clears the cluster filter, showing all ${index.counts.communities} clusters again.`,
        choices: [],
      };
    }
    return communityForToken(token, index, ctx);
  }

  // 5 — relationship-type filter
  if (RE_ALL_RELATIONS.test(q)) {
    return {
      intent: 'graph_relation',
      status: 'ready',
      actions: [{ kind: 'filterRelation', relations: null }],
      command: 'relation all',
      title: 'Draw every relationship type',
      explanation: `Clears the relationship filter, drawing all ${index.relationTypes.length} recorded types again.`,
      choices: [],
    };
  }
  const relOnly = RE_RELATION_ONLY.exec(q) ?? RE_RELATION_OF_TYPE.exec(q);
  if (relOnly) return relationProposal(stripArticle(relOnly[1]), index);

  // 6 — node-type filter
  const typeOnly = RE_TYPE_ONLY.exec(q);
  if (typeOnly) {
    const value: GraphTypeFilter = /^file/i.test(typeOnly[1]) ? 'file' : 'concept';
    const actions: GraphAction[] = [{ kind: 'filterType', value }];
    return {
      intent: 'graph_type',
      status: 'ready',
      actions,
      command: `type ${value}`,
      title: `Show only ${value === 'file' ? 'files' : 'concepts'}`,
      explanation:
        `This projection holds ${index.counts.files} file${index.counts.files === 1 ? '' : 's'} and ` +
        `${index.counts.concepts} concept${index.counts.concepts === 1 ? '' : 's'}. ` +
        `${applyOutcomeSentence(outcomeOf(actions, index, ctx), index.counts.total)} ` +
        `Concepts carry no references here, so filtering to them shows nodes with no lines.`,
      choices: [],
    };
  }
  if (RE_TYPE_BOTH.test(q)) {
    const actions: GraphAction[] = [{ kind: 'filterType', value: 'all' }];
    return {
      intent: 'graph_type',
      status: 'ready',
      actions,
      command: 'type all',
      title: 'Show files and concepts',
      explanation:
        `Clears the node-type filter: all ${index.counts.total} nodes become eligible again. ` +
        `${applyOutcomeSentence(outcomeOf(actions, index, ctx), index.counts.total)}`,
      choices: [],
    };
  }

  // 7 — text filter
  const related = RE_FIND_RELATED.exec(q);
  if (related) {
    const noun = related[1].toLowerCase();
    const type: GraphTypeFilter = noun.startsWith('file')
      ? 'file'
      : noun.startsWith('concept')
        ? 'concept'
        : 'all';
    return findProposal(stripArticle(related[2]), type, index, ctx);
  }
  const searched = RE_SEARCH_GRAPH.exec(q);
  if (searched) return findProposal(stripArticle(searched[1]), 'all', index, ctx);

  // 8 — viewport / filter resets
  if (RE_RESET.test(q)) {
    return {
      intent: 'graph_reset',
      status: 'ready',
      actions: [{ kind: 'reset' }],
      command: 'reset',
      title: 'Reset the graph view',
      explanation:
        'Restores the default viewport and undoes any node you dragged. The search, filters and current focus are ' +
        'not touched — "clear the filters" does that.',
      choices: [],
    };
  }
  if (RE_CLEAR_FILTERS.test(q)) {
    return {
      intent: 'graph_clear_filters',
      status: 'ready',
      actions: [{ kind: 'clearFilters' }],
      command: 'clear filters',
      title: 'Clear the graph filters',
      explanation:
        'Clears the search, the node-type filter, the cluster filter, the relationship filter and any neighbourhood or route focus. ' +
        'The viewport is left where it is — "reset the graph" does that.',
      choices: [],
    };
  }

  // Anything else is NOT a graph question as far as this catalog is concerned.
  return null;
}

// --------------------------------------------- suggested commands (P36V.1 G)

/*
 * The visible "Suggested Commands" row beside the command bar.
 *
 * Every suggestion is a line of the grammar ABOVE — parsed by
 * `parseGraphCommand` and applied by `applyGraphAction`. There is no second
 * vocabulary, no second resolver and no second reducer, so a suggestion cannot
 * reach behaviour the typed bar cannot reach, and cannot mean something
 * different from the identical line typed by hand.
 *
 * A suggestion is offered ONLY after it has been folded through the real parser
 * and the real reducer ON THE LIVE STATE and shown to produce something: a
 * suggestion that resolves to nothing, or errors on Run, is worse than no
 * suggestion at all (`foldsToSomething`).
 *
 * Clicking a suggestion INSERTS its exact canonical command into the bar and
 * waits for an explicit Run. The single exception is a viewport-only view
 * action, allowlisted by `DIRECTLY_RUNNABLE_SUGGESTIONS` and demoted to an
 * insertion if it is not on that list — so no click can silently apply a filter,
 * a focus, a path or a selection, and nothing here can touch a record.
 */

/** Most suggestions offered at once. The row sits above the canvas and must not
 *  grow into it. */
export const MAX_SUGGESTED_COMMANDS = 6;

/**
 * `find` topics offered when nothing is selected, in preference order. A topic
 * is offered only when it actually matches nodes in the LIVE projection, so this
 * list can never put a dead suggestion on screen — it only expresses which real
 * matches are worth surfacing first.
 */
export const SUGGESTED_FIND_TOPICS: readonly string[] = [
  'validation',
  'export',
  'evidence',
  'schema',
  'audit',
  'record',
  'memory',
  'assistant',
];

/** Reference types preferred for the "show only …" suggestion. Falls back to
 *  whatever the projection actually records; never names a type it does not. */
const PREFERRED_SUGGESTED_RELATIONS: readonly string[] = ['imports', 'calls', 'references'];

/**
 * The ONLY commands a single click may run without an explicit Run.
 *
 * `fit` reframes the viewport and does nothing else: it sets no filter, moves no
 * node, changes no selection, creates no focus and cannot write anything. Every
 * other verb — including `reset`, which undoes node drags, and `clear filters`,
 * which discards a narrowed view — is INSERTED and waits for the user.
 */
export const DIRECTLY_RUNNABLE_SUGGESTIONS: readonly string[] = ['fit'];

/** Reducer notices that mean the token did NOT resolve. A candidate producing
 *  one of these is dropped before it is ever offered. */
const REFUSAL_NOTICES: ReadonlySet<GraphNotice['kind']> = new Set<GraphNotice['kind']>([
  'not_found',
  'ambiguous',
  'community_not_found',
  'community_ambiguous',
  'relation_unknown',
  'no_path',
]);

export type GraphSuggestionEffect =
  /** puts `command` in the bar; the user presses Run */
  | 'insert'
  /** runs `command` on the click — viewport-only view actions only */
  | 'run'
  /** opens About This Graph at Technical Details; changes no graph state */
  | 'help';

export interface GraphSuggestedCommand {
  /** stable key for React and for tests */
  id: string;
  /** human-readable Title Case label */
  label: string;
  /** the EXACT canonical command line. Null only for the `help` effect. */
  command: string | null;
  /** one short line: what it does. Never a claim about the science. */
  detail: string;
  effect: GraphSuggestionEffect;
  /** true when `command` is deliberately INCOMPLETE and needs one more token
   *  before it can run — the bar inserts it and opens the completion list. */
  partial: boolean;
}

export interface GraphSuggestionContext {
  /** the live view state, verbatim — the same object the reducer produced */
  state: GraphViewState;
  /** the decoded deep layer, once Unit F has fetched it */
  deep?: DeepIndex | null;
  /** Unit F's pinned deep mark (`deepSelectedId`), read — never duplicated */
  deepSelectedId?: string | null;
}

interface SuggestionCandidate extends GraphSuggestedCommand {
  /** A COMPLETE command used only to PROVE resolvability. For a `partial`
   *  suggestion it is the resolvable core the insertion is a prefix of, since
   *  the incomplete line itself is (correctly) a syntax error. */
  verify: string | null;
}

/**
 * Would this command actually do something on the live state?
 *
 * Folded through the REAL parser and the REAL reducer — not a private estimate.
 * A refusal notice means the token did not resolve; an empty filtered set means
 * the command would leave nothing on screen. Either way the suggestion is not
 * offered.
 */
function foldsToSomething(command: string, index: GraphIndex, state: GraphViewState): boolean {
  const parsed = parseGraphCommand(command);
  if (parsed.status === 'help') return true;
  if (parsed.status !== 'actions') return false;
  let next = state;
  for (const action of parsed.actions) next = applyGraphAction(next, action, index);
  if (next.notice && REFUSAL_NOTICES.has(next.notice.kind)) return false;
  return filteredNodeIds(next, index).length > 0;
}

/** Capitalise a single lowercase word from the fixed topic list. Deterministic,
 *  and never applied to data — cluster names and node ids render verbatim. */
const topicLabel = (topic: string): string => topic.charAt(0).toUpperCase() + topic.slice(1);

const anyFilterActive = (s: GraphViewState): boolean =>
  s.search.trim() !== '' ||
  s.typeFilter !== 'all' ||
  s.communityFilter !== 'all' ||
  s.relationFilter !== null ||
  s.focus !== null;

/** The one non-command suggestion: a harmless disclosure of the exact counts,
 *  snapshot fingerprint and render bounds. Opens a dialog; changes nothing. */
const technicalDetailsCandidate = (): SuggestionCandidate => ({
  id: 'technical-details',
  label: 'View Technical Details',
  command: null,
  detail:
    'Opens About This Graph at Technical Details — the exact counts, the snapshot fingerprint, ' +
    'the projection layers and the render bounds. It changes nothing.',
  effect: 'help',
  partial: false,
  verify: null,
});

/**
 * Suggestions for the currently SELECTED base node.
 *
 * `path <id> -> ` is inserted deliberately unfinished: the completion list then
 * offers real destinations for the missing token, which is strictly better than
 * this row guessing one.
 */
function selectionCandidates(index: GraphIndex, state: GraphViewState): SuggestionCandidate[] {
  const id = state.selectedId;
  const node = id ? index.byId.get(id) : undefined;
  if (!id || !node) return [];
  const out: SuggestionCandidate[] = [];
  const degree = (index.adjacency.get(id) ?? []).length;
  // Zoomed past the first level-of-detail threshold, a neighbourhood focus
  // SUSPENDS the deeper layers (GraphCanvas keeps the projection the focus was
  // computed over). Saying so is cheaper than letting the canvas surprise the
  // reader who pressed the suggestion.
  const focusNote =
    graphLodLevel(state.view.scale) === 'file'
      ? ''
      : ' At this zoom a focus returns the canvas to the file projection.';

  if (degree > 0) {
    const one = neighborhood(id, 1, index, state.relationFilter).ids.length;
    const two = neighborhood(id, 2, index, state.relationFilter).ids.length;
    out.push({
      id: 'neighbors-1',
      label: 'Show 1-Hop Neighbors',
      command: `neighbors ${id}`,
      detail: `Focuses the ${one} nodes one reference away from ${id}, inclusive.${focusNote}`,
      effect: 'insert',
      partial: false,
      verify: `neighbors ${id}`,
    });
    // Offered only when it would actually widen the set — a depth-2 focus that
    // draws the same nodes as depth 1 is a suggestion that does nothing.
    if (two > one) {
      out.push({
        id: 'neighbors-2',
        label: 'Show 2-Hop Neighbors',
        command: `neighbors ${id} depth 2`,
        detail: `Widens the focus to two references away — ${two} nodes in this projection.${focusNote}`,
        effect: 'insert',
        partial: false,
        verify: `neighbors ${id} depth 2`,
      });
    }
  }

  const cid = node.community_id;
  if (cid && index.communityById.has(cid) && state.communityFilter !== cid) {
    out.push({
      id: 'community-of-selected',
      label: 'Show This Cluster',
      command: `community ${cid}`,
      detail:
        `Filters to the cluster holding ${id}. Clusters are automatically derived, advisory ` +
        'groupings — not categories the schema recognises.',
      effect: 'insert',
      partial: false,
      verify: `community ${cid}`,
    });
  }

  out.push({
    id: 'path-start',
    label: 'Start a Path From Here',
    command: `path ${id} -> `,
    detail:
      'Puts an unfinished path command in the bar with this node as the start — choose a ' +
      'destination from the completions, then press Run.',
    effect: 'insert',
    partial: true,
    verify: `select ${id}`,
  });

  out.push({
    id: 'select-none',
    label: 'Clear the Selection',
    command: 'select none',
    detail: 'Deselects this node. No filter, focus or viewport is touched.',
    effect: 'insert',
    partial: false,
    verify: 'select none',
  });

  out.push(technicalDetailsCandidate());
  return out;
}

/**
 * Suggestions for Unit F's pinned DEEP mark — a cluster or a symbol.
 *
 * Deliberately re-expressed in terms of the mark's FILE and CLUSTER. The
 * grammar's `resolveNode` addresses the served-file projection: a symbol name is
 * not a node in it, so `select export_record` would honestly answer "no node
 * matches" — a suggestion that does nothing. Every entry here therefore names
 * something the grammar can actually resolve, and the labels say which.
 *
 * Returns null when the mark cannot be resolved, or when nothing about it is
 * addressable, so the caller falls back to the general set rather than showing
 * an almost-empty row.
 */
function deepMarkCandidates(
  index: GraphIndex,
  deep: DeepIndex,
  deepSelectedId: string,
  state: GraphViewState,
): SuggestionCandidate[] | null {
  const symbol = deep.byId.get(deepSelectedId) ?? null;
  const cluster = symbol ? null : (deep.clusterByKey.get(deepSelectedId) ?? null);
  if (!symbol && !cluster) return null;
  const sourceFile = symbol ? symbol.sourceFile : cluster!.sourceFile;
  const communityId = symbol ? symbol.communityId : cluster!.communityId;
  const what = symbol ? 'symbol' : 'cluster';
  const out: SuggestionCandidate[] = [];

  if (index.byId.has(sourceFile)) {
    out.push({
      id: 'deep-select-file',
      label: 'Select the File It Is In',
      command: `select ${sourceFile}`,
      detail:
        `${sourceFile} is the file this ${what} belongs to. Commands address files and concepts, ` +
        'not symbol names, so its file is what can be named here.',
      effect: 'insert',
      partial: false,
      verify: `select ${sourceFile}`,
    });
    if ((index.adjacency.get(sourceFile) ?? []).length > 0) {
      out.push({
        id: 'deep-neighbors',
        label: "Show Its File's Neighbors",
        command: `neighbors ${sourceFile}`,
        detail:
          `Focuses the files ${sourceFile} references. A focus returns the canvas to the file ` +
          'projection it was computed over.',
        effect: 'insert',
        partial: false,
        verify: `neighbors ${sourceFile}`,
      });
    }
  }

  if (communityId && index.communityById.has(communityId) && state.communityFilter !== communityId) {
    out.push({
      id: 'deep-community',
      label: 'Show This Cluster',
      command: `community ${communityId}`,
      detail:
        `Filters the file projection to the cluster this ${what} carries. Clusters are ` +
        'automatically derived, advisory groupings — not categories the schema recognises.',
      effect: 'insert',
      partial: false,
      verify: `community ${communityId}`,
    });
  }

  if (index.byId.has(sourceFile)) {
    out.push({
      id: 'deep-path-start',
      label: 'Start a Path From Its File',
      command: `path ${sourceFile} -> `,
      detail:
        'Puts an unfinished path command in the bar with this file as the start — choose a ' +
        'destination from the completions, then press Run.',
      effect: 'insert',
      partial: true,
      verify: `select ${sourceFile}`,
    });
  }

  if (out.length === 0) return null;
  out.push(technicalDetailsCandidate());
  return out;
}

/** The largest cluster that can be named unambiguously, or null. */
function clusterCandidate(
  index: GraphIndex,
  state: GraphViewState,
  resolves: (command: string) => boolean,
): SuggestionCandidate | null {
  for (const entry of index.communitiesBySize) {
    if (state.communityFilter === entry.id) continue;
    // Prefer the cluster's own NAME as the token when the name resolves to
    // exactly this cluster; otherwise its id. Never a partial name.
    const named =
      entry.name !== null && resolveCommunity(entry.name, index).status === 'found'
        ? entry.name
        : null;
    const command = `community ${named ?? entry.id}`;
    if (!resolves(command)) continue;
    return {
      id: 'community-largest',
      // Cluster names render VERBATIM — they are arbitrary upstream data
      // (`test_export.py`, `SHE_work_function_eV`), never re-cased.
      label: named ? `Show the ${named} Cluster` : 'Show the Largest Cluster',
      command,
      detail:
        `Filters to ${communityOptionLabel(entry)}. Clusters are automatically derived, advisory ` +
        'groupings — not categories the schema recognises.',
      effect: 'insert',
      partial: false,
      verify: command,
    };
  }
  return null;
}

/** One reference-type filter, named from the values the payload actually has. */
function relationCandidate(
  index: GraphIndex,
  state: GraphViewState,
  resolves: (command: string) => boolean,
): SuggestionCandidate | null {
  const rel =
    PREFERRED_SUGGESTED_RELATIONS.find((r) => index.relationTypes.includes(r)) ??
    index.relationTypes[0];
  if (!rel) return null;
  const active = state.relationFilter;
  if (active && active.length === 1 && active[0] === rel) return null;
  const command = `relation ${rel}`;
  if (!resolves(command)) return null;
  return {
    id: 'relation-common',
    label: `Show Only ${relationDisplayLabel(rel)} References`,
    command,
    detail:
      'Draws only that reference type, and stops neighbourhoods and routes travelling through ' +
      'the others.',
    effect: 'insert',
    partial: false,
    verify: command,
  };
}

/** The set offered when nothing is selected: real search topics, a real
 *  cluster, a real reference type, and the two safe view/filter resets. */
function generalCandidates(
  index: GraphIndex,
  state: GraphViewState,
  resolves: (command: string) => boolean,
): SuggestionCandidate[] {
  const out: SuggestionCandidate[] = [];
  const current = state.search.trim().toLowerCase();
  for (const topic of SUGGESTED_FIND_TOPICS) {
    if (out.length >= 2) break;
    if (topic === current) continue;
    const command = `find ${topic}`;
    if (!resolves(command)) continue;
    out.push({
      id: `find-${topic}`,
      label: `Find ${topicLabel(topic)}`,
      command,
      detail: `Filters to files and concepts whose path or label contains "${topic}".`,
      effect: 'insert',
      partial: false,
      verify: command,
    });
  }

  const cluster = clusterCandidate(index, state, resolves);
  if (cluster) out.push(cluster);
  const relation = relationCandidate(index, state, resolves);
  if (relation) out.push(relation);

  out.push({
    id: 'fit',
    label: 'Fit to View',
    command: 'fit',
    detail:
      'Frames everything currently visible. A view action: it runs as soon as you press it, and ' +
      'changes no filter, no selection and no record.',
    effect: 'run',
    partial: false,
    verify: 'fit',
  });

  // Offered only when something is actually narrowing the view — otherwise it
  // is a control that visibly does nothing.
  if (anyFilterActive(state)) {
    out.push({
      id: 'clear-filters',
      label: 'Clear Filters',
      command: 'clear filters',
      detail:
        'Clears the search, the node-type, cluster and reference-type filters, and any ' +
        'neighbourhood or route focus. The viewport is left where it is.',
      effect: 'insert',
      partial: false,
      verify: 'clear filters',
    });
  }

  return out;
}

/**
 * The bounded, context-aware suggestion set for the mounted surface.
 *
 * Pure: a function of the already-fetched index and the live state. No fetch, no
 * history, no ranking model, no LLM. The set changes when the selection, the
 * pinned deep mark, the filters or the zoom level change, and returns to the
 * general set the moment the selection clears.
 */
export function suggestedGraphCommands(
  index: GraphIndex,
  ctx: GraphSuggestionContext,
): GraphSuggestedCommand[] {
  const state = ctx.state;
  const resolves = (command: string): boolean => foldsToSomething(command, index, state);

  const deepList =
    ctx.deep && ctx.deepSelectedId
      ? deepMarkCandidates(index, ctx.deep, ctx.deepSelectedId, state)
      : null;
  const candidates =
    deepList ??
    (state.selectedId && index.byId.has(state.selectedId)
      ? selectionCandidates(index, state)
      : generalCandidates(index, state, resolves));

  const out: GraphSuggestedCommand[] = [];
  const seen = new Set<string>();
  for (const candidate of candidates) {
    if (out.length >= MAX_SUGGESTED_COMMANDS) break;
    if (candidate.effect === 'help') {
      out.push(strip(candidate, 'help'));
      continue;
    }
    if (!candidate.command || seen.has(candidate.command)) continue;
    if (candidate.verify && !resolves(candidate.verify)) continue;
    // A `run` candidate is DEMOTED to an insertion unless it is on the
    // viewport-only allowlist. The allowlist is the gate, not the author's
    // intention, so a future candidate cannot become click-runnable by accident.
    const effect: GraphSuggestionEffect =
      candidate.effect === 'run' && !DIRECTLY_RUNNABLE_SUGGESTIONS.includes(candidate.command)
        ? 'insert'
        : candidate.effect;
    seen.add(candidate.command);
    out.push(strip(candidate, effect));
  }
  return out;
}

/** Drop the internal `verify` field — it is a construction detail, not UI. */
function strip(
  candidate: SuggestionCandidate,
  effect: GraphSuggestionEffect,
): GraphSuggestedCommand {
  return {
    id: candidate.id,
    label: candidate.label,
    command: candidate.command,
    detail: candidate.detail,
    effect,
    partial: candidate.partial,
  };
}

/**
 * The spoken name of a suggestion: its label PLUS what pressing it does. The
 * insert / run distinction lives in the accessible name itself, so it is never
 * carried by a visual tag alone.
 */
export function suggestionActionSentence(s: GraphSuggestedCommand): string {
  if (s.effect === 'help') return 'opens About This Graph at Technical Details';
  const command = (s.command ?? '').trim();
  if (s.effect === 'run') {
    return `runs the view command "${command}" straight away — it only reframes the viewport`;
  }
  if (s.partial) {
    return `puts the unfinished command "${command}" in the command bar; choose a destination, then press Run`;
  }
  return `puts the command "${command}" in the command bar; press Run to apply it`;
}
