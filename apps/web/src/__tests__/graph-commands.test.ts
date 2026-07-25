import { describe, it, expect } from 'vitest';
import {
  GRAPH_COMMANDS,
  GRAPH_INTENTS,
  GRAPH_URL_PARAMS,
  MAX_COMMAND_LENGTH,
  classifyGraphQuestion,
  decodeGraphActions,
  describeCommandOutcome,
  describeGraphProvenance,
  encodeGraphParams,
  graphParamKey,
  parseGraphCommand,
  suggestCommands,
  summarizeNotice,
  type GraphIntentContext,
} from '../lib/graphCommands';
import {
  applyGraphAction,
  buildGraphIndex,
  filteredNodeIds,
  initialGraphViewState,
  visibleNodeIds,
  type GraphAction,
  type GraphIndex,
  type GraphViewState,
} from '../lib/graphModel';
import { memoryGraphAvailable } from '../test/apiFixtures';

/*
 * P36R Slices 4 + 5 — the ONE text→action boundary.
 *
 * The command grammar, the bounded natural-language intent catalog and the URL
 * codec are three front-ends over the SAME `GraphAction` union and the SAME
 * `applyGraphAction` reducer. These tests hold that line: identical inputs
 * produce identical actions, an unresolvable token is refused honestly rather
 * than guessed, and the parser is structurally incapable of executing anything.
 */

const index: GraphIndex = buildGraphIndex(memoryGraphAvailable as never);

/** An intent context over a given live view state — the WHOLE state, because
 *  that is what the classifier folds its proposed actions onto. */
const ctxOf = (patch: Partial<GraphViewState> = {}): GraphIntentContext => ({
  state: { ...initialGraphViewState(), ...patch },
});

const ctx: GraphIntentContext = ctxOf();

/** Fold actions through the real reducer, exactly as every front-end does. */
function run(actions: GraphAction[], from: GraphViewState = initialGraphViewState()): GraphViewState {
  return actions.reduce((s, a) => applyGraphAction(s, a, index), from);
}

function actionsOf(command: string): GraphAction[] {
  const parsed = parseGraphCommand(command);
  if (parsed.status !== 'actions') throw new Error(`expected actions, got ${parsed.status}`);
  return parsed.actions;
}

// --- 1. the grammar ---------------------------------------------------------

describe('command grammar — every supported command', () => {
  it('parses `find` into a search action', () => {
    expect(actionsOf('find export')).toEqual([{ kind: 'search', query: 'export' }]);
    // The rest of the line is the query verbatim, spaces and all.
    expect(actionsOf('find  export   pipeline ')).toEqual([
      { kind: 'search', query: 'export pipeline' },
    ]);
  });

  it('parses `select` and `select none`', () => {
    expect(actionsOf('select src/fake_mod.py')).toEqual([
      { kind: 'select', nodeId: 'src/fake_mod.py' },
    ]);
    expect(actionsOf('select none')).toEqual([{ kind: 'select', nodeId: null }]);
    // Wrapping backticks/quotes are stripped; the identity itself is untouched.
    expect(actionsOf('select `src/fake_mod.py`')).toEqual([
      { kind: 'select', nodeId: 'src/fake_mod.py' },
    ]);
  });

  it('parses `neighbors` with and without an explicit depth, and both spellings', () => {
    expect(actionsOf('neighbors src/fake_mod.py')).toEqual([
      { kind: 'neighbors', nodeId: 'src/fake_mod.py', depth: 1 },
    ]);
    expect(actionsOf('neighbors src/fake_mod.py depth 2')).toEqual([
      { kind: 'neighbors', nodeId: 'src/fake_mod.py', depth: 2 },
    ]);
    expect(actionsOf('neighbours src/fake_mod.py depth 2')).toEqual([
      { kind: 'neighbors', nodeId: 'src/fake_mod.py', depth: 2 },
    ]);
  });

  it('parses `community`, `community all`, and `type`', () => {
    expect(actionsOf('community Export Pipeline')).toEqual([
      { kind: 'filterCommunity', id: 'Export Pipeline' },
    ]);
    expect(actionsOf('community all')).toEqual([{ kind: 'filterCommunity', id: 'all' }]);
    expect(actionsOf('type file')).toEqual([{ kind: 'filterType', value: 'file' }]);
    expect(actionsOf('type concept')).toEqual([{ kind: 'filterType', value: 'concept' }]);
    expect(actionsOf('type all')).toEqual([{ kind: 'filterType', value: 'all' }]);
  });

  it('parses `relation` in its three forms', () => {
    expect(actionsOf('relation imports')).toEqual([
      { kind: 'filterRelation', relations: ['imports'] },
    ]);
    expect(actionsOf('relation imports, references')).toEqual([
      { kind: 'filterRelation', relations: ['imports', 'references'] },
    ]);
    expect(actionsOf('relation all')).toEqual([{ kind: 'filterRelation', relations: null }]);
    // `none` is a real, honest state: no relationship types, so no lines.
    expect(actionsOf('relation none')).toEqual([{ kind: 'filterRelation', relations: [] }]);
  });

  it('parses `path` with `->` (and a typed arrow)', () => {
    expect(actionsOf('path src/fake_mod.py -> src/other_mod.py')).toEqual([
      { kind: 'path', from: 'src/fake_mod.py', to: 'src/other_mod.py' },
    ]);
    expect(actionsOf('path src/fake_mod.py → src/other_mod.py')).toEqual([
      { kind: 'path', from: 'src/fake_mod.py', to: 'src/other_mod.py' },
    ]);
  });

  it('parses `fit`, `reset`, `clear filters`, `clear focus`', () => {
    expect(actionsOf('fit')).toEqual([{ kind: 'fit' }]);
    expect(actionsOf('reset')).toEqual([{ kind: 'reset' }]);
    expect(actionsOf('clear filters')).toEqual([{ kind: 'clearFilters' }]);
    expect(actionsOf('clear focus')).toEqual([{ kind: 'clearFocus' }]);
  });

  it('treats `help` as its own outcome and whitespace as a no-op', () => {
    expect(parseGraphCommand('help').status).toBe('help');
    expect(parseGraphCommand('   ').status).toBe('empty');
    expect(parseGraphCommand('').status).toBe('empty');
  });

  it('documents exactly the verbs it implements — the help catalog cannot drift', () => {
    for (const spec of GRAPH_COMMANDS) {
      const parsed = parseGraphCommand(spec.example);
      expect(
        parsed.status,
        `catalog example \`${spec.example}\` must parse`,
      ).not.toBe('error');
    }
    // And nothing outside the catalog parses.
    expect(parseGraphCommand('export').status).toBe('error');
    expect(parseGraphCommand('delete src/fake_mod.py').status).toBe('error');
  });
});

// --- 2. syntax errors name what was wrong -----------------------------------

describe('command grammar — syntax errors', () => {
  const messageOf = (line: string): string => {
    const parsed = parseGraphCommand(line);
    if (parsed.status !== 'error') throw new Error(`expected an error for \`${line}\``);
    return parsed.message;
  };

  it('names the unknown verb and lists the supported ones', () => {
    const msg = messageOf('frobnicate everything');
    expect(msg).toMatch(/Unknown command `frobnicate`/);
    expect(msg).toMatch(/find/);
    expect(msg).toMatch(/path/);
  });

  it('names a missing argument', () => {
    expect(messageOf('find')).toMatch(/`find` needs some text/);
    expect(messageOf('select')).toMatch(/`select` needs a node/);
    expect(messageOf('neighbors')).toMatch(/`neighbors` needs a node/);
    expect(messageOf('community')).toMatch(/`community` needs a cluster/);
    expect(messageOf('type')).toMatch(/`type` needs a value/);
    expect(messageOf('relation')).toMatch(/`relation` needs a relationship type/);
    expect(messageOf('path')).toMatch(/`path` needs two nodes/);
    expect(messageOf('clear')).toMatch(/`clear` needs a target/);
  });

  it('names a bad enumerated value', () => {
    expect(messageOf('type files')).toMatch(/accepts file, concept, or all — got `files`/);
    expect(messageOf('neighbors src/fake_mod.py depth 3')).toMatch(/accepts 1 or 2 — got `3`/);
    expect(messageOf('clear everything')).toMatch(/accepts filters or focus/);
  });

  it('names a malformed `path`', () => {
    expect(messageOf('path a')).toMatch(/needs exactly one `->`|needs two nodes/);
    expect(messageOf('path a -> b -> c')).toMatch(/exactly one `->`/);
    expect(messageOf('path -> b')).toMatch(/on BOTH sides/);
  });

  it('rejects arguments where the command takes none', () => {
    expect(messageOf('fit now')).toMatch(/`fit` takes no arguments/);
    expect(messageOf('reset everything')).toMatch(/`reset` takes no arguments/);
  });

  it('bounds the input length instead of parsing unboundedly', () => {
    expect(messageOf(`find ${'x'.repeat(MAX_COMMAND_LENGTH + 10)}`)).toMatch(/at most 240 characters/);
  });
});

// --- 3. security — arbitrary execution is structurally impossible -----------

describe('command bar — security', () => {
  const parserSources = import.meta.glob('../lib/graphCommands.ts', {
    query: '?raw',
    import: 'default',
    eager: true,
  }) as Record<string, string>;
  const barSources = import.meta.glob('../screens/graph/GraphCommandBar.tsx', {
    query: '?raw',
    import: 'default',
    eager: true,
  }) as Record<string, string>;
  /*
   * The WIRING handles exactly the same untrusted text — the typed command, the
   * `gq`/`gnode`/`gnbr` link parameters and the Assistant question all pass
   * through these three files on their way to the reducer and back out as
   * rendered strings. Scanning only the parser and the bar left the surfaces
   * that actually put that text on the page unscanned.
   */
  const wiringSources = import.meta.glob(
    [
      '../screens/MemoryGraphCard.tsx',
      '../screens/ProjectMemory.tsx',
      '../components/AssistantPanel.tsx',
    ],
    { query: '?raw', import: 'default', eager: true },
  ) as Record<string, string>;

  /** Comments describe the rule and would otherwise trip the scan reading it. */
  const stripComments = (source: string): string =>
    source.replace(/\/\*[\s\S]*?\*\//g, (b) => b.replace(/[^\n]/g, ' ')).replace(/^\s*\/\/.*$/gm, '');

  it('the parser path contains no evaluator of any kind', () => {
    const files = { ...parserSources, ...barSources, ...wiringSources };
    expect(Object.keys(files).length).toBe(5);
    const forbidden: [RegExp, string][] = [
      [/\beval\s*\(/, 'eval()'],
      [/\bnew\s+Function\b/, 'new Function'],
      [/\bFunction\s*\(/, 'Function()'],
      [/\bimport\s*\(/, 'dynamic import()'],
      [/\brequire\s*\(/, 'require()'],
      [/\bsetTimeout\s*\(\s*['"`]/, 'string-bodied setTimeout'],
      [/\bsetInterval\s*\(\s*['"`]/, 'string-bodied setInterval'],
      [/dangerouslySetInnerHTML/, 'dangerouslySetInnerHTML'],
      [/\.innerHTML\b/, 'innerHTML'],
      [/\bfetch\s*\(/, 'fetch()'],
      [/\bXMLHttpRequest\b/, 'XMLHttpRequest'],
      [/\blocalStorage\b/, 'localStorage'],
      [/\bsessionStorage\b/, 'sessionStorage'],
      [/console\.(log|info|warn|error)\s*\(/, 'console logging of command text'],
    ];
    const offenders: string[] = [];
    for (const [path, source] of Object.entries(files)) {
      const clean = stripComments(source);
      for (const [re, label] of forbidden) {
        if (re.test(clean)) offenders.push(`${path}: ${label}`);
      }
    }
    expect(offenders, `evaluator/exfiltration primitives found:\n${offenders.join('\n')}`).toEqual([]);
  });

  it('dispatches on a literal switch, never a table keyed by user input', () => {
    const source = stripComments(Object.values(parserSources)[0]);
    expect(source).toMatch(/switch \(verb\)/);
    // A prototype-walking token is therefore just an unknown verb.
    for (const hostile of ['__proto__', 'constructor', 'prototype', 'toString']) {
      const parsed = parseGraphCommand(hostile);
      expect(parsed.status).toBe('error');
    }
  });

  it('rejects hostile input as a syntax error rather than executing it', () => {
    const hostile = [
      'eval(1+1)',
      'require("fs").readFileSync("/etc/passwd")',
      '<script>alert(1)</script>',
      'process.exit(1)',
      '$(rm -rf /)',
      '`rm -rf /`',
      'window.location="http://example.com"',
      '__proto__.polluted = 1',
      'constructor.constructor("return 1")()',
      'javascript:alert(1)',
      '../../etc/passwd',
      'DROP TABLE records;',
    ];
    for (const line of hostile) {
      const parsed = parseGraphCommand(line);
      expect(parsed.status, `\`${line}\` must not parse into an action`).toBe('error');
    }
    // Nothing was executed, and no global was created or clobbered.
    expect((globalThis as Record<string, unknown>).polluted).toBeUndefined();
    expect(({} as Record<string, unknown>).polluted).toBeUndefined();
  });

  it('treats a hostile string in an ARGUMENT as inert data, never code', () => {
    // `find` takes free text by design. It becomes a search string and nothing
    // else — no execution, no navigation, no mutation of anything but the view.
    const actions = actionsOf('find "); process.exit(1); //');
    expect(actions).toEqual([{ kind: 'search', query: '"); process.exit(1); //' }]);
    const next = run(actions);
    expect(next.search).toBe('"); process.exit(1); //');
    // A hostile node token resolves to nothing — it is never approximated.
    const missing = run(actionsOf('select <script>alert(1)</script>'));
    expect(missing.selectedId).toBeNull();
    expect(missing.notice).toEqual({ kind: 'not_found', token: '<script>alert(1)</script>' });
  });

  it('never mutates a record: every produced action is a view action', () => {
    const viewKinds = new Set([
      'setMode',
      'select',
      'search',
      'filterType',
      'filterCommunity',
      'filterRelation',
      'neighbors',
      'path',
      'pan',
      'zoom',
      'moveNode',
      'fit',
      'reset',
      'clearFilters',
      'clearFocus',
      'dismissNotice',
    ]);
    for (const spec of GRAPH_COMMANDS) {
      const parsed = parseGraphCommand(spec.example);
      if (parsed.status !== 'actions') continue;
      for (const action of parsed.actions) expect(viewKinds.has(action.kind)).toBe(true);
    }
  });
});

// --- 4. honest resolution ---------------------------------------------------

describe('command execution — honest resolution', () => {
  it('reports an ambiguous node with bounded candidates and changes nothing', () => {
    const before = initialGraphViewState();
    const after = run(actionsOf('select mod'), before);
    expect(after.selectedId).toBeNull();
    expect(after.notice?.kind).toBe('ambiguous');
    if (after.notice?.kind === 'ambiguous') {
      expect(after.notice.candidates).toEqual(['src/fake_mod.py', 'src/other_mod.py']);
    }
    expect(after.search).toBe(before.search);
    expect(after.focus).toBeNull();
  });

  it('reports a missing node honestly and selects nothing', () => {
    const after = run(actionsOf('select does/not/exist.py'));
    expect(after.selectedId).toBeNull();
    expect(after.notice).toEqual({ kind: 'not_found', token: 'does/not/exist.py' });
  });

  it('reports no route as no route — never a fabricated connection', () => {
    const after = run(actionsOf('path src/fake_mod.py -> docs/fake-note.md'));
    expect(after.focus).toBeNull();
    expect(after.notice).toEqual({
      kind: 'no_path',
      from: 'src/fake_mod.py',
      to: 'docs/fake-note.md',
    });
  });

  it('finds a real route and focuses it', () => {
    const after = run(actionsOf('path src/fake_mod.py -> src/other_mod.py'));
    expect(after.focus?.kind).toBe('path');
    expect(after.notice).toMatchObject({ kind: 'path_found', hops: 1 });
  });

  it('reports an unknown cluster and an unknown relationship type instead of blanking the view', () => {
    const comm = run(actionsOf('community nope'));
    expect(comm.communityFilter).toBe('all');
    expect(comm.notice).toEqual({ kind: 'community_not_found', token: 'nope' });

    const rel = run(actionsOf('relation bogus'));
    expect(rel.notice).toEqual({ kind: 'relation_unknown', tokens: ['bogus'] });
  });

  it('summarizes each notice for the compact history without adding a claim', () => {
    expect(summarizeNotice(null)).toBeNull();
    expect(summarizeNotice({ kind: 'not_found', token: 'x' })).toMatch(/No node matches "x"/);
    expect(summarizeNotice({ kind: 'no_path', from: 'a', to: 'b' })).toMatch(/No route connects a and b/);
    expect(summarizeNotice({ kind: 'path_found', from: 'a', to: 'b', hops: 2 })).toMatch(/2-step route/);
  });
});

// --- 5. completions ---------------------------------------------------------

describe('command completions', () => {
  it('offers the verbs first, then the values each verb accepts', () => {
    expect(suggestCommands('', index).map((s) => s.value.trim())).toContain('find');
    expect(suggestCommands('ne', index).map((s) => s.value.trim())).toEqual(['neighbors']);
    expect(suggestCommands('type ', index).map((s) => s.value)).toEqual([
      'type file',
      'type concept',
      'type all',
    ]);
    expect(suggestCommands('relation ', index).map((s) => s.value)).toContain('relation imports');
    expect(suggestCommands('clear ', index).map((s) => s.value)).toEqual([
      'clear filters',
      'clear focus',
    ]);
  });

  it('completes node ids from the live index only — never an invented one', () => {
    const values = suggestCommands('select mod', index).map((s) => s.value);
    expect(values).toEqual(['select src/fake_mod.py', 'select src/other_mod.py']);
    expect(suggestCommands('select zzzz', index)).toEqual([]);
  });

  it('completes the right side of a path', () => {
    const values = suggestCommands('path src/fake_mod.py -> other', index).map((s) => s.value);
    expect(values).toEqual(['path src/fake_mod.py -> src/other_mod.py']);
  });
});

// --- 6. URL state -----------------------------------------------------------

describe('URL state', () => {
  const reader = (record: Record<string, string>) => (k: string) => record[k] ?? null;

  it('round-trips a filtered, focused view through encode → decode', () => {
    const state = run([
      { kind: 'setMode', mode: 'browse' },
      { kind: 'filterType', value: 'file' },
      { kind: 'search', query: 'mod' },
      { kind: 'neighbors', nodeId: 'src/fake_mod.py', depth: 2 },
    ]);
    const encoded = encodeGraphParams(state);
    expect(encoded).toMatchObject({
      gmode: 'browse',
      gtype: 'file',
      gq: 'mod',
      gnbr: 'src/fake_mod.py',
      gdepth: '2',
    });
    const restored = run(decodeGraphActions(reader(encoded) as never));
    expect(encodeGraphParams(restored)).toEqual(encoded);
    expect(restored.focus).toEqual(state.focus);
    expect(restored.search).toBe(state.search);
    expect(restored.typeFilter).toBe(state.typeFilter);
    expect(restored.mode).toBe('browse');
  });

  it('round-trips a path focus and a relation filter', () => {
    const state = run([
      { kind: 'filterRelation', relations: ['imports'] },
      { kind: 'path', from: 'src/fake_mod.py', to: 'src/other_mod.py' },
    ]);
    const encoded = encodeGraphParams(state);
    expect(encoded).toMatchObject({ grel: 'imports', gfrom: 'src/fake_mod.py', gto: 'src/other_mod.py' });
    const restored = run(decodeGraphActions(reader(encoded) as never));
    expect(restored.relationFilter).toEqual(['imports']);
    expect(restored.focus?.kind).toBe('path');
  });

  it('does not encode the viewport or node drags — a link is state, not a scroll position', () => {
    const state = run([
      { kind: 'zoom', factor: 2 },
      { kind: 'pan', dx: 100, dy: 50 },
      { kind: 'moveNode', nodeId: 'src/fake_mod.py', x: 12, y: 13 },
    ]);
    expect(Object.keys(encodeGraphParams(state))).toEqual(['gmode']);
  });

  it('validates at the boundary: unknown enum values and over-long tokens are dropped', () => {
    const actions = decodeGraphActions(
      reader({
        gmode: 'evil',
        gtype: 'executable',
        gq: 'x'.repeat(500),
        gcomm: 'y'.repeat(500),
      }) as never,
    );
    expect(actions).toEqual([]);
  });

  it('reads ONLY the documented parameters — an unknown one cannot reach the reducer', () => {
    const seen: string[] = [];
    const spy = (record: Record<string, string>) => (k: string) => {
      seen.push(k);
      return record[k] ?? null;
    };
    decodeGraphActions(spy({}) as never);
    // `gdepth` is read only once `gnbr` named a node, so exercise that too.
    decodeGraphActions(spy({ gnbr: 'src/fake_mod.py' }) as never);
    expect(new Set(seen)).toEqual(new Set(GRAPH_URL_PARAMS));
    for (const key of seen) expect(GRAPH_URL_PARAMS as readonly string[]).toContain(key);
  });

  it('passes node tokens through the reducer resolver rather than trusting the link', () => {
    const after = run(decodeGraphActions(reader({ gnode: '<script>alert(1)</script>' }) as never));
    expect(after.selectedId).toBeNull();
    expect(after.notice?.kind).toBe('not_found');
  });

  it('DROPS an over-long search rather than truncating it into a broader link', () => {
    // A truncated query is a strictly wider filter, so a truncated link would
    // show its recipient MORE nodes than its author saw — the one direction a
    // shareable link must never fail in.
    const long = 'z'.repeat(500);
    const encoded = encodeGraphParams({ ...initialGraphViewState(), search: long });
    expect(encoded.gq).toBeUndefined();
    expect(Object.keys(encoded)).toEqual(['gmode']);
    // At exactly the bound it is still carried, whole.
    const atBound = 'z'.repeat(120);
    expect(encodeGraphParams({ ...initialGraphViewState(), search: atBound }).gq).toBe(atBound);
  });

  it('drops a `gdepth` outside {1,2} instead of silently correcting it to 1', () => {
    // Every other out-of-set parameter is dropped; this was the one that was
    // repaired into a different, plausible-looking view.
    expect(decodeGraphActions(reader({ gnbr: 'src/fake_mod.py', gdepth: '99' }) as never)).toEqual([]);
    expect(decodeGraphActions(reader({ gnbr: 'src/fake_mod.py', gdepth: '' }) as never)).toEqual([]);
    // Absent is the documented default of 1, not a correction.
    expect(decodeGraphActions(reader({ gnbr: 'src/fake_mod.py' }) as never)).toEqual([
      { kind: 'neighbors', nodeId: 'src/fake_mod.py', depth: 1 },
    ]);
    expect(decodeGraphActions(reader({ gnbr: 'src/fake_mod.py', gdepth: '2' }) as never)).toEqual([
      { kind: 'neighbors', nodeId: 'src/fake_mod.py', depth: 2 },
    ]);
    // …and it matches what the typed grammar does with the same request.
    expect(parseGraphCommand('neighbors src/fake_mod.py depth 99').status).toBe('error');
  });

  it('distinguishes an empty relation filter from an absent one', () => {
    expect(decodeGraphActions(reader({ grel: '' }) as never)).toEqual([
      { kind: 'filterRelation', relations: [] },
    ]);
    expect(decodeGraphActions(reader({}) as never)).toEqual([]);
  });

  it('produces a stable identity string for the graph parameters', () => {
    expect(graphParamKey(reader({ gmode: 'explore' }) as never)).toContain('gmode=explore');
    expect(graphParamKey(reader({}) as never)).toBe(
      GRAPH_URL_PARAMS.map((k) => `${k}=`).join('&'),
    );
  });
});

// --- 7. the Assistant intent catalog ---------------------------------------

describe('Assistant graph intents — the bounded catalog', () => {
  it('recognises a neighbourhood question, with and without a depth', () => {
    const p = classifyGraphQuestion('Show neighbors of `src/fake_mod.py`.', index, ctx);
    expect(p?.intent).toBe('graph_neighbors');
    expect(p?.status).toBe('ready');
    expect(p?.actions).toEqual([{ kind: 'neighbors', nodeId: 'src/fake_mod.py', depth: 1 }]);

    const deep = classifyGraphQuestion('Show neighbors of src/fake_mod.py at depth 2', index, ctx);
    expect(deep?.actions).toEqual([{ kind: 'neighbors', nodeId: 'src/fake_mod.py', depth: 2 }]);

    const alt = classifyGraphQuestion('What is connected to src/fake_mod.py?', index, ctx);
    expect(alt?.intent).toBe('graph_neighbors');
  });

  it('recognises a path question and reports a real route', () => {
    const p = classifyGraphQuestion(
      'Find a path from src/fake_mod.py to src/other_mod.py',
      index,
      ctx,
    );
    expect(p?.intent).toBe('graph_path');
    expect(p?.status).toBe('ready');
    expect(p?.actions).toEqual([
      { kind: 'path', from: 'src/fake_mod.py', to: 'src/other_mod.py' },
    ]);
    expect(p?.explanation).toMatch(/1-step route/);
  });

  it('says "no route" honestly and offers nothing to apply', () => {
    const p = classifyGraphQuestion(
      'Find a path from src/fake_mod.py to docs/fake-note.md',
      index,
      ctx,
    );
    expect(p?.status).toBe('unresolved');
    expect(p?.actions).toEqual([]);
    expect(p?.explanation).toMatch(/No route connects/);
    expect(p?.explanation).toMatch(/no connection was invented/);
  });

  it('recognises a cluster question by name and by member node', () => {
    const byName = classifyGraphQuestion('Show the cluster Export Pipeline', index, ctx);
    expect(byName?.intent).toBe('graph_community');
    expect(byName?.actions).toEqual([{ kind: 'filterCommunity', id: '131' }]);

    const byNode = classifyGraphQuestion('Show the community for src/fake_mod.py', index, ctx);
    expect(byNode?.actions).toEqual([{ kind: 'filterCommunity', id: '131' }]);

    const which = classifyGraphQuestion('Which cluster is src/other_mod.py in', index, ctx);
    expect(which?.actions).toEqual([{ kind: 'filterCommunity', id: '55' }]);
  });

  it('answers "what does this cluster contain" only when a cluster is actually in focus', () => {
    const none = classifyGraphQuestion('What does this community contain?', index, ctx);
    expect(none?.status).toBe('unresolved');
    expect(none?.explanation).toMatch(/No cluster is currently filtered to/);

    const active = classifyGraphQuestion(
      'What does this community contain?',
      index,
      ctxOf({ communityFilter: '131' }),
    );
    expect(active?.status).toBe('ready');
    expect(active?.explanation).toMatch(/src\/fake_mod\.py/);
  });

  it('recognises a relationship filter, and lists candidates for an ambiguous type', () => {
    const exact = classifyGraphQuestion('Only show imports relationships', index, ctx);
    expect(exact?.intent).toBe('graph_relation');
    expect(exact?.actions).toEqual([{ kind: 'filterRelation', relations: ['imports'] }]);

    const all = classifyGraphQuestion('Show all relationships', index, ctx);
    expect(all?.actions).toEqual([{ kind: 'filterRelation', relations: null }]);

    const missing = classifyGraphQuestion('Only show mentions relationships', index, ctx);
    expect(missing?.status).toBe('unresolved');
    expect(missing?.explanation).toMatch(/not one of them/);
  });

  it('recognises node-type filters and the "files related to X" form', () => {
    expect(classifyGraphQuestion('Show only concepts', index, ctx)?.actions).toEqual([
      { kind: 'filterType', value: 'concept' },
    ]);
    const related = classifyGraphQuestion('Find files related to validation.', index, ctx);
    expect(related?.intent).toBe('graph_find');
    expect(related?.actions).toEqual([
      { kind: 'filterType', value: 'file' },
      { kind: 'search', query: 'validation' },
    ]);
  });

  it('recognises reset and clear-filters, and keeps them honestly distinct', () => {
    const reset = classifyGraphQuestion('Reset the graph.', index, ctx);
    expect(reset?.actions).toEqual([{ kind: 'reset' }]);
    expect(reset?.explanation).toMatch(/filters and current focus are\s+not touched/);

    const cleared = classifyGraphQuestion('Clear the filters', index, ctx);
    expect(cleared?.actions).toEqual([{ kind: 'clearFilters' }]);
  });

  it('lists BOUNDED candidates for an ambiguous node and proposes nothing', () => {
    const p = classifyGraphQuestion('Show neighbors of mod', index, ctx);
    expect(p?.status).toBe('ambiguous');
    expect(p?.actions).toEqual([]);
    expect(p?.choices.map((c) => c.label)).toEqual(['src/fake_mod.py', 'src/other_mod.py']);
    // Each candidate is the SAME navigation, resolved — never a guess.
    expect(p?.choices[0].proposal.actions).toEqual([
      { kind: 'neighbors', nodeId: 'src/fake_mod.py', depth: 1 },
    ]);
    expect(p?.choices[0].proposal.status).toBe('ready');
  });

  it('says a missing node is missing, and proposes nothing', () => {
    const p = classifyGraphQuestion('Show neighbors of nowhere/at/all.py', index, ctx);
    expect(p?.status).toBe('unresolved');
    expect(p?.actions).toEqual([]);
    expect(p?.explanation).toMatch(/No node in this projection matches/);
    expect(p?.explanation).toMatch(/no approximate match was substituted/);
  });

  it('returns null for anything outside the catalog — the normal path is not hijacked', () => {
    const outside = [
      'What is missing from this record?',
      'Is this ready to export?',
      'Where did the beamline value come from?',
      'Summarize the evidence for sample_id',
      'What does project memory know about provenance?',
      'Write me a poem about XANES',
      'Delete every record',
      '',
      '   ',
    ];
    for (const q of outside) {
      expect(classifyGraphQuestion(q, index, ctx), `must not intercept: ${q}`).toBeNull();
    }
  });

  it('exposes a frozen intent catalog and never emits an intent outside it', () => {
    expect(GRAPH_INTENTS.length).toBe(9);
    const asked = [
      'Show neighbors of src/fake_mod.py',
      'Find a path from src/fake_mod.py to src/other_mod.py',
      'Show the cluster Export Pipeline',
      'What does this community contain?',
      'Only show imports relationships',
      'Show only concepts',
      'Find files related to validation',
      'Reset the graph',
      'Clear the filters',
    ];
    for (const q of asked) {
      const p = classifyGraphQuestion(q, index, ctxOf({ communityFilter: '131' }));
      expect(p).not.toBeNull();
      expect(GRAPH_INTENTS).toContain(p!.intent);
    }
  });

  it('renders the projection provenance rather than claiming a source', () => {
    const line = describeGraphProvenance(memoryGraphAvailable.meta as never);
    expect(line).toMatch(/served-file projection/);
    expect(line).toMatch(/commit caab1d0a69c1/);
    expect(line).toMatch(/sanitized-snapshot/);
  });

  it('never renders reserved verdict language', () => {
    for (const q of [
      'Show neighbors of src/fake_mod.py',
      'Find a path from src/fake_mod.py to docs/fake-note.md',
      'Show the cluster Export Pipeline',
    ]) {
      const p = classifyGraphQuestion(q, index, ctx)!;
      const text = `${p.title} ${p.explanation}`;
      expect(text).not.toMatch(/\b(PASS|FAIL)\b/);
      expect(text).not.toMatch(/\b(in)?valid against\b/i);
    }
  });
});

// --- 7b. a stated count is the count applying produces ----------------------

/*
 * The regression this section exists for: `neighborsProposal` reported
 * `neighborhood(...).length` while the reducer intersects the focus set with
 * `matchesFilters`, and `findProposal` counted over EVERY node in the index.
 * Under `type concept` the Assistant said "Focusing it draws 14 nodes" and the
 * canvas then read "0 of 220 nodes shown" — a false quantitative claim in the
 * Assistant's own voice, contradicted one click later.
 *
 * The fix is structural: proposals fold their own actions through the real
 * reducer and read the model's own `visibleNodeIds`. These tests hold that line
 * across a MATRIX of non-default filter states, which is precisely where a
 * parallel estimate drifts and a default-state test sees nothing.
 */
describe('proposal counts — stated equals applied, under any filter state', () => {
  /** The count the proposal states, read out of its own explanation. */
  const statedCount = (explanation: string): number => {
    if (/would show NOTHING/.test(explanation)) return 0;
    const m = /Applying it shows (\d+) of the \d+ nodes/.exec(explanation);
    if (!m) throw new Error(`no stated count in: ${explanation}`);
    return Number(m[1]);
  };

  const filterStates: [string, Partial<GraphViewState>][] = [
    ['no filters', {}],
    ['type concept', { typeFilter: 'concept' }],
    ['type file', { typeFilter: 'file' }],
    ['cluster 131', { communityFilter: '131' }],
    ['search "mod"', { search: 'mod' }],
    ['search that matches nothing', { search: 'zzzznomatch' }],
    ['browse mode', { mode: 'browse' }],
    ['type concept + cluster 55', { typeFilter: 'concept', communityFilter: '55' }],
  ];

  const questions = [
    'Show neighbors of src/fake_mod.py',
    'Show neighbors of src/fake_mod.py at depth 2',
    'Find a path from src/fake_mod.py to src/other_mod.py',
    'Show the cluster Export Pipeline',
    'Show the community for src/fake_mod.py',
    'Show only concepts',
    'Show files and concepts',
    'Find files related to mod',
    'Search the graph for mod',
  ];

  it.each(filterStates)(
    'every ready proposal states what applying produces — %s',
    (_label, patch) => {
      const c = ctxOf(patch);
      for (const question of questions) {
        const p = classifyGraphQuestion(question, index, c);
        expect(p, `no intent matched: ${question}`).not.toBeNull();
        if (p!.status !== 'ready') continue;
        // Applied EXACTLY as the surface applies it: the same reducer, folded
        // onto the same live state.
        const applied = run(p!.actions, c.state);
        expect(
          statedCount(p!.explanation),
          `${question} @ ${JSON.stringify(patch)}\n${p!.explanation}`,
        ).toBe(visibleNodeIds(applied, index).length);
      }
    },
  );

  it('the two cases the review reproduced live now state zero, and say why', () => {
    // `type concept` active: the neighbourhood is two FILES, so applying draws
    // none of them. The old text said "Focusing it draws 2 nodes".
    const typed = classifyGraphQuestion(
      'Show neighbors of src/fake_mod.py',
      index,
      ctxOf({ typeFilter: 'concept' }),
    )!;
    expect(typed.status).toBe('ready');
    expect(typed.explanation).toMatch(/would show NOTHING/);
    expect(typed.explanation).toMatch(/the node-type filter `type concept`/);
    expect(typed.explanation).toMatch(/clear filters/);
    expect(run(typed.actions, ctxOf({ typeFilter: 'concept' }).state)).toMatchObject({
      notice: { kind: 'neighborhood', count: 0 },
    });

    // A search that matches nothing: same class of bug, same honest answer.
    const searched = classifyGraphQuestion(
      'Show neighbors of src/fake_mod.py',
      index,
      ctxOf({ search: 'zzzznomatch' }),
    )!;
    expect(searched.explanation).toMatch(/would show NOTHING/);
    expect(searched.explanation).toMatch(/the search "zzzznomatch"/);
  });

  it('states a real, non-zero count with the focal node accounted for', () => {
    const p = classifyGraphQuestion('Show neighbors of src/fake_mod.py', index, ctx)!;
    expect(p.explanation).toMatch(/Applying it shows 2 of the 5 nodes, including src\/fake_mod\.py itself/);
    expect(visibleNodeIds(run(p.actions), index).length).toBe(2);
  });

  it('`find` counts through the reducer, not over the whole index', () => {
    // Cluster 131 holds src/fake_mod.py and concept-provenance; only the first
    // contains "mod". Counting over `index.nodes` (as the removed copy did)
    // would have said 2 — both `*_mod.py` files — and drawn 1.
    const c = ctxOf({ communityFilter: '131' });
    const p = classifyGraphQuestion('Search the graph for mod', index, c)!;
    expect(p.explanation).toMatch(/Applying it shows 1 of the 5 nodes/);
    expect(p.explanation).toMatch(/the cluster filter/);
    expect(visibleNodeIds(run(p.actions, c.state), index).length).toBe(1);
  });

  it('reports a carried restriction only when the proposal did not set it itself', () => {
    // "Show only concepts" IS the type filter — it must not describe itself as
    // an obstacle to itself.
    const p = classifyGraphQuestion('Show only concepts', index, ctxOf({ typeFilter: 'concept' }))!;
    expect(p.explanation).not.toMatch(/still applies/);
    // …but a cluster filter it did NOT set is named.
    const withCluster = classifyGraphQuestion(
      'Show only concepts',
      index,
      ctxOf({ communityFilter: '131' }),
    )!;
    expect(withCluster.explanation).toMatch(/the cluster filter/);
  });

  it('bounds the search text instead of proposing a query the URL must drop', () => {
    const long = 'z'.repeat(200);
    const p = classifyGraphQuestion(`Search the graph for ${long}`, index, ctx)!;
    expect(p.status).toBe('unresolved');
    expect(p.actions).toEqual([]);
    expect(p.explanation).toMatch(/bounded to 120 characters/);
    expect(p.explanation).toMatch(/a shortened query is a different, broader filter/);
  });
});

// --- 7c. the reducer's own announced count ----------------------------------

describe('reducer notice — the announced count is the count rendered', () => {
  it('announces what the canvas draws, and names the neighbourhood size separately', () => {
    const filtered: GraphViewState = { ...initialGraphViewState(), typeFilter: 'concept' };
    const after = applyGraphAction(
      filtered,
      { kind: 'neighbors', nodeId: 'src/fake_mod.py', depth: 1 },
      index,
    );
    // The neighbourhood really is two nodes; NONE of them survive `type concept`.
    expect(after.notice).toEqual({
      kind: 'neighborhood',
      nodeId: 'src/fake_mod.py',
      depth: 1,
      count: 0,
      neighborhoodSize: 2,
      truncated: false,
    });
    expect(visibleNodeIds(after, index).length).toBe(0);
    expect(filteredNodeIds(after, index).length).toBe(0);
    // The spoken summary says both figures rather than the flattering one.
    expect(summarizeNotice(after.notice)).toMatch(
      /2 nodes in it, 0 nodes shown under the current filters/,
    );
  });

  it('says only the one figure when nothing is filtered out', () => {
    const after = applyGraphAction(
      initialGraphViewState(),
      { kind: 'neighbors', nodeId: 'src/fake_mod.py', depth: 1 },
      index,
    );
    expect(after.notice).toMatchObject({ count: 2, neighborhoodSize: 2 });
    expect(summarizeNotice(after.notice)).toBe(
      '1-hop neighbourhood of src/fake_mod.py — 2 nodes shown.',
    );
  });

  it('describes a command the reducer left no notice on, using the same counts', () => {
    const after = run(actionsOf('type file'));
    expect(after.notice).toBeNull();
    expect(describeCommandOutcome('type file', after, index)).toBe(
      'type file — 3 of 5 nodes shown.',
    );
    expect(describeCommandOutcome('select src/other_mod.py', run(actionsOf('select src/other_mod.py')), index)).toMatch(
      /^Selected src\/other_mod\.py\./,
    );
    expect(describeCommandOutcome('clear filters', run(actionsOf('clear filters')), index)).toMatch(
      /^Filters cleared —/,
    );
    expect(describeCommandOutcome('fit', run(actionsOf('fit')), index)).toMatch(/^Framed/);
    // …and a notice, when there is one, is never contradicted by a second line.
    const hood = run(actionsOf('neighbors src/fake_mod.py'));
    expect(describeCommandOutcome('neighbors src/fake_mod.py', hood, index)).toBe(
      summarizeNotice(hood.notice),
    );
  });
});

// --- 8. the shared action model (the point of the whole slice) --------------

describe('one action model — command bar and Assistant cannot drift', () => {
  const pairs: [string, string][] = [
    ['Show neighbors of src/fake_mod.py', 'neighbors src/fake_mod.py'],
    ['Show neighbors of src/fake_mod.py at depth 2', 'neighbors src/fake_mod.py depth 2'],
    [
      'Find a path from src/fake_mod.py to src/other_mod.py',
      'path src/fake_mod.py -> src/other_mod.py',
    ],
    ['Show the cluster Export Pipeline', 'community 131'],
    ['Only show imports relationships', 'relation imports'],
    ['Show all relationships', 'relation all'],
    ['Show only concepts', 'type concept'],
    ['Reset the graph', 'reset'],
    ['Clear the filters', 'clear filters'],
  ];

  it.each(pairs)('"%s" produces the same GraphActions as `%s`', (question, command) => {
    const proposal = classifyGraphQuestion(question, index, ctx);
    expect(proposal, `no intent matched: ${question}`).not.toBeNull();
    expect(proposal!.actions).toEqual(actionsOf(command));
  });

  it('the multi-action form matches the equivalent command SEQUENCE', () => {
    const proposal = classifyGraphQuestion('Find files related to validation', index, ctx)!;
    expect(proposal.actions).toEqual([...actionsOf('type file'), ...actionsOf('find validation')]);
  });

  it('applying either front-end through the reducer yields identical state', () => {
    for (const [question, command] of pairs) {
      const viaAssistant = run(classifyGraphQuestion(question, index, ctx)!.actions);
      const viaCommand = run(actionsOf(command));
      expect(viaAssistant).toEqual(viaCommand);
    }
  });

  it('every proposal advertises the equivalent command, and it parses', () => {
    for (const [question] of pairs) {
      const proposal = classifyGraphQuestion(question, index, ctx)!;
      expect(proposal.command).not.toBeNull();
      const reparsed = parseGraphCommand(proposal.command!);
      expect(reparsed.status).toBe('actions');
      if (reparsed.status === 'actions') expect(reparsed.actions).toEqual(proposal.actions);
    }
  });
});
