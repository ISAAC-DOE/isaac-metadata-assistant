import { describe, it, expect } from 'vitest';
import {
  EXPERIMENT_EDGE_KINDS,
  EXPERIMENT_NODE_KINDS,
  MAX_EXPERIMENT_NODES,
  MAX_SEARCH_RESULTS,
  MAX_VISIBLE_NODES,
  NODE_PRODUCERS,
  applyExperimentGraphAction,
  buildExperimentGraph,
  expandableNodeIds,
  fitExperimentViewport,
  initialExperimentGraphState,
  nodeIds,
  searchExperimentGraph,
  sectionTitleFor,
  viewBoxFor,
  visibleEdges,
  visibleNodeIds,
  type ExperimentGraph,
  type ExperimentGraphViewState,
} from '../lib/experimentGraph';
import {
  GRAPH_EXP_ID,
  GRAPH_LINK_TARGET,
  GRAPH_RECORD_ID,
  experimentGraphBundle,
  exportedExperimentGraphBundle,
  stressExperimentGraphBundle,
} from '../test/experimentGraphFixtures';

/*
 * The EXPERIMENT-SCOPED graph model.
 *
 * These are the assertions that stop the surface from drifting into a
 * plausible-looking lie: the closed vocabularies, the named producer for every
 * node kind, the ABSENCE of every speculative edge, the honest note when there
 * is nothing to draw, tutorial isolation, and the bounds under stress.
 */

function build(bundle = experimentGraphBundle()): ExperimentGraph {
  const result = buildExperimentGraph(bundle);
  if (!result.ok) throw new Error(`expected a graph, got a refusal: ${result.message}`);
  return result.graph;
}

describe('experiment graph — closed vocabularies', () => {
  it('emits ONLY the enumerated node kinds, on both the draft and the exported path', () => {
    for (const bundle of [experimentGraphBundle(), exportedExperimentGraphBundle()]) {
      const graph = build(bundle);
      for (const node of graph.nodes) {
        expect(EXPERIMENT_NODE_KINDS).toContain(node.kind);
      }
    }
  });

  it('emits ONLY the enumerated edge kinds, on both paths', () => {
    for (const bundle of [experimentGraphBundle(), exportedExperimentGraphBundle()]) {
      const graph = build(bundle);
      for (const edge of graph.edges) {
        expect(EXPERIMENT_EDGE_KINDS).toContain(edge.kind);
      }
    }
  });

  it('gives every node kind exactly one named deterministic producer', () => {
    for (const kind of EXPERIMENT_NODE_KINDS) {
      expect(NODE_PRODUCERS[kind]).toBeTruthy();
    }
    // And every node carries a producer string, not an empty placeholder.
    for (const node of build(exportedExperimentGraphBundle()).nodes) {
      expect(node.producer.length).toBeGreaterThan(10);
    }
  });

  it('never emits an edge whose endpoints are not both nodes', () => {
    const graph = build(exportedExperimentGraphBundle());
    for (const edge of graph.edges) {
      expect(graph.byId.has(edge.source)).toBe(true);
      expect(graph.byId.has(edge.target)).toBe(true);
    }
  });

  it('gives every edge a WHY sentence that is not a bare identifier', () => {
    const graph = build(exportedExperimentGraphBundle());
    expect(graph.edges.length).toBeGreaterThan(10);
    for (const edge of graph.edges) {
      expect(edge.why.length).toBeGreaterThan(20);
      expect(edge.why).not.toBe(edge.kind);
    }
  });
});

describe('experiment graph — the no-speculative-edge rule', () => {
  const graph = build(exportedExperimentGraphBundle());
  const kinds = new Set(graph.edges.map((e) => e.kind));

  it('has no similarity, collaboration, campaign or instrument-identity edge kind', () => {
    for (const forbidden of [
      'similar_to',
      'same_sample_as',
      'same_campaign_as',
      'collaborated_with',
      'measured_on',
      'follows_in_time',
      'caused_by',
      'interpreted_as',
    ]) {
      expect(EXPERIMENT_EDGE_KINDS as readonly string[]).not.toContain(forbidden);
      expect(kinds.has(forbidden as never)).toBe(false);
    }
  });

  it('reads a declared link from the record and NEVER from a matching value', () => {
    const linked = graph.byId.get(nodeIds.linkedRecord(GRAPH_LINK_TARGET));
    expect(linked).toBeDefined();
    const edge = graph.edges.find((e) => e.target === linked!.id);
    expect(edge?.kind).toBe('links_to');
    // The relationship and its basis are quoted verbatim from the record.
    expect(edge?.label).toBe('same_sample_as · shared_material_batch');
    expect(edge?.why).toContain('Declared link: same_sample_as (basis: shared_material_batch)');
    expect(edge?.why).toContain('never because two records happened to look alike');
  });

  it('says "no declared links" honestly rather than inventing one', () => {
    const draft = build(experimentGraphBundle());
    const note = draft.notes.find((n) => n.kind === 'no_declared_links');
    expect(note).toBeDefined();
    expect(note!.text).toContain('declares no links');
    expect(draft.counts.linked_record).toBe(0);
  });

  it('records a contributor as a free string, explicitly not an entity', () => {
    const contributor = graph.nodes.find(
      (n) => n.kind === 'block_object' && n.label === 'Synthetic Fixture Author',
    );
    expect(contributor).toBeDefined();
    const line = contributor!.detail.find((d) => d.term === 'Not an entity');
    expect(line?.value).toContain('not resolved to a person');
    // …and no edge joins it to anything but its own section.
    const touching = graph.edges.filter(
      (e) => e.source === contributor!.id || e.target === contributor!.id,
    );
    expect(touching.every((e) => e.kind === 'contains')).toBe(true);
  });
});

describe('experiment graph — producers', () => {
  it('anchors on the EXPERIMENT before export and never invents a record id', () => {
    const graph = build(experimentGraphBundle());
    expect(graph.anchorId).toBe(nodeIds.experiment(GRAPH_EXP_ID));
    expect(graph.counts.record).toBe(0);
    expect(graph.notes.some((n) => n.kind === 'not_exported')).toBe(true);
  });

  it('anchors on the RECORD after export, with a produces edge from the experiment', () => {
    const graph = build(exportedExperimentGraphBundle());
    expect(graph.anchorId).toBe(nodeIds.record(GRAPH_RECORD_ID));
    const produces = graph.edges.find((e) => e.kind === 'produces');
    expect(produces?.source).toBe(nodeIds.experiment(GRAPH_EXP_ID));
    expect(produces?.target).toBe(nodeIds.record(GRAPH_RECORD_ID));
  });

  it('builds sections from the draft grouping and contains its fields', () => {
    const graph = build(experimentGraphBundle());
    const sample = graph.byId.get(nodeIds.section('Sample'));
    expect(sample?.kind).toBe('section');
    const contains = graph.edges.find(
      (e) => e.kind === 'contains' && e.source === sample!.id,
    );
    expect(contains?.target).toBe(nodeIds.field('sample.material.formula'));
    expect(contains?.why).toContain('Defined by schema field sample.material.formula');
  });

  it('maps a namespaced key and an official path onto the SAME eight sections', () => {
    expect(sectionTitleFor('sample.material.formula')).toBe('Sample');
    expect(sectionTitleFor('measurement.series[0]')).toBe('Measurement');
    expect(sectionTitleFor('series:averaged_spectrum')).toBe('Measurement');
    expect(sectionTitleFor('qc:status')).toBe('Measurement');
    expect(sectionTitleFor('assets:notebook')).toBe('Assets & Files');
    expect(sectionTitleFor('nonsense.path')).toBe('Other');
  });

  it('attaches evidence, its cited file, its rule and its confirmation', () => {
    const graph = build(experimentGraphBundle());

    const spreadsheet = graph.edges.find(
      (e) => e.kind === 'supported_by' && e.source === nodeIds.field('system.technique'),
    );
    expect(spreadsheet?.why).toContain('mock_campaign.csv');
    expect(spreadsheet?.why).toContain("Sheet 'Campaign Info', field=technique");

    const citedFiles = graph.edges.filter((e) => e.kind === 'cites').map((e) => e.target);
    expect(citedFiles).toContain(nodeIds.sourceFile('mock_campaign.csv'));
    expect(citedFiles).toContain(nodeIds.sourceFile('raw_scan_listing.txt'));

    const rule = graph.edges.find((e) => e.kind === 'derived_by_rule');
    expect(rule?.why).toContain('Derived by a documented rule');

    const confirmed = graph.edges.find((e) => e.kind === 'confirmed_by_user');
    expect(confirmed?.why).toContain('Confirmed by you on 2099-05-01T09:30:00Z');
  });

  it('keeps an implicit value out of the field space and says why', () => {
    const graph = build(experimentGraphBundle());
    const implicit = graph.byId.get(nodeIds.implicit('absorbing_element'));
    expect(implicit?.kind).toBe('implicit');
    const why = implicit!.detail.find((d) => d.term === 'Why it is not a field');
    expect(why?.value).toContain('no native path');
  });

  it('enumerates the exported record structure and joins an asset by natural key ONLY', () => {
    const graph = build(exportedExperimentGraphBundle());
    const labels = graph.nodes.filter((n) => n.kind === 'block_object').map((n) => n.label);
    expect(labels).toContain('averaged_spectrum');
    expect(labels).toContain('absorption');
    expect(labels).toContain('i0_monitor');
    expect(labels).toContain('incident_energy');

    // `assets:processing_notebook` (an evidence key) and `assets[0].asset_id`
    // are byte-identical, so they are ONE node, not two look-alikes.
    const joined = graph.byId.get(nodeIds.block('assets:processing_notebook'));
    expect(joined).toBeDefined();
    expect(joined!.detail.some((d) => d.value === 'assets[0]')).toBe(true);
    expect(graph.byId.has(nodeIds.block('assets[0]'))).toBe(false);
  });

  it('attaches a validation issue to the field it names, and the workflow chain', () => {
    const graph = build(experimentGraphBundle());
    const fails = graph.edges.filter((e) => e.kind === 'fails');
    expect(fails.length).toBe(2);
    const onField = fails.find((e) => e.source === nodeIds.field('sample.material.formula'));
    expect(onField).toBeDefined();
    expect(onField!.why).toContain('dry run against the official ISAAC schema');

    const precedes = graph.edges.filter((e) => e.kind === 'precedes');
    expect(precedes.length).toBe(4); // 5 canonical steps → 4 links
    expect(graph.counts.workflow_step).toBe(5);
    expect(graph.edges.filter((e) => e.kind === 'at_step').length).toBe(1);
  });

  it('marks an advisory warning as non-gating and never as a failure', () => {
    const graph = build(experimentGraphBundle());
    const advise = graph.edges.find((e) => e.kind === 'advises');
    expect(advise?.why).toContain('advisory and non-gating');
    const warning = graph.byId.get(advise!.target);
    expect(warning?.detail.find((d) => d.term === 'Gating')?.value).toContain('no');
    // The warning is reachable only through `advises`, never through `fails`.
    expect(graph.edges.some((e) => e.kind === 'fails' && e.target === warning!.id)).toBe(false);
  });

  it('classifies evidence support on its own axis and says so', () => {
    const graph = build(experimentGraphBundle());
    const classified = graph.edges.filter((e) => e.kind === 'classified_as');
    expect(classified.length).toBe(2);
    const cls = graph.byId.get(classified[0].target)!;
    expect(cls.detail.find((d) => d.term === 'Axis')?.value).toContain('not validity');
  });
});

describe('experiment graph — a stale exported artifact', () => {
  it('renders the stale state rather than presenting it as current', () => {
    const graph = build(exportedExperimentGraphBundle('stale'));
    expect(graph.notes.some((n) => n.kind === 'artifact_stale')).toBe(true);
    const record = graph.byId.get(nodeIds.record(GRAPH_RECORD_ID));
    expect(record?.fromStaleArtifact).toBe(true);
    const series = graph.nodes.find((n) => n.label === 'averaged_spectrum');
    expect(series?.fromStaleArtifact).toBe(true);
  });

  it('does NOT mark anything stale when the artifact is current', () => {
    const graph = build(exportedExperimentGraphBundle('current'));
    expect(graph.notes.some((n) => n.kind === 'artifact_stale')).toBe(false);
    expect(graph.nodes.every((n) => !n.fromStaleArtifact)).toBe(true);
  });
});

describe('experiment graph — tutorial isolation', () => {
  it('refuses to build when the bundle was read in a different workspace scope', () => {
    const sessionBundle = experimentGraphBundle();
    const result = buildExperimentGraph(sessionBundle, {
      readIn: 'fixtureSessionId0000000',
      current: null,
    });
    expect(result.ok).toBe(false);
    if (result.ok) throw new Error('unreachable');
    expect(result.reason).toBe('workspace_scope_changed');
    expect(result.message).toContain('worked-example session');
  });

  it('refuses in BOTH directions — entering a session is as disqualifying as leaving one', () => {
    const entering = buildExperimentGraph(experimentGraphBundle(), {
      readIn: null,
      current: 'fixtureSessionId0000000',
    });
    expect(entering.ok).toBe(false);
  });

  it('builds normally when both scopes agree, in the ordinary workspace and in a session', () => {
    expect(buildExperimentGraph(experimentGraphBundle(), { readIn: null, current: null }).ok).toBe(
      true,
    );
    expect(
      buildExperimentGraph(experimentGraphBundle(), {
        readIn: 'fixtureSessionId0000000',
        current: 'fixtureSessionId0000000',
      }).ok,
    ).toBe(true);
  });
});

describe('experiment graph — the reducer', () => {
  const graph = build(experimentGraphBundle());
  const initial = initialExperimentGraphState(graph);

  const apply = (
    state: ExperimentGraphViewState,
    ...actions: Parameters<typeof applyExperimentGraphAction>[1][]
  ) => actions.reduce((s, a) => applyExperimentGraphAction(s, a, graph), state);

  it('starts anchored, with only the anchor expanded', () => {
    expect(initial.expanded).toEqual([graph.anchorId]);
    expect(initial.selectedId).toBe(graph.anchorId);
  });

  it('draws the anchor NEIGHBOURHOOD on first paint, not the whole graph', () => {
    const visible = visibleNodeIds(initial, graph);
    expect(visible).toContain(graph.anchorId);
    expect(visible.length).toBeGreaterThan(1);
    expect(visible.length).toBeLessThan(graph.nodes.length);
  });

  it('reveals more on expand, and never draws a half edge', () => {
    const section = nodeIds.section('Sample');
    const before = visibleNodeIds(initial, graph);
    expect(before).not.toContain(nodeIds.field('sample.material.formula'));

    const after = apply(initial, { kind: 'expand', nodeId: section });
    const visible = visibleNodeIds(after, graph);
    expect(visible).toContain(nodeIds.field('sample.material.formula'));

    const set = new Set(visible);
    for (const edge of visibleEdges(visible, graph)) {
      expect(set.has(edge.source) && set.has(edge.target)).toBe(true);
    }
  });

  it('collapses back, and refuses to collapse the anchor', () => {
    const section = nodeIds.section('Sample');
    const expanded = apply(initial, { kind: 'expand', nodeId: section });
    const collapsed = apply(expanded, { kind: 'collapse', nodeId: section });
    expect(visibleNodeIds(collapsed, graph)).not.toContain(
      nodeIds.field('sample.material.formula'),
    );

    const anchorCollapse = apply(initial, { kind: 'collapse', nodeId: graph.anchorId });
    expect(anchorCollapse).toBe(initial);
  });

  it('never selects a node that is not in this graph — identity is not guessed', () => {
    const unchanged = apply(initial, { kind: 'select', nodeId: 'field:not.a.real.path' });
    expect(unchanged).toBe(initial);
    expect(unchanged.selectedId).toBe(graph.anchorId);
  });

  it('reveal makes an off-screen node visible AND selected', () => {
    const target = nodeIds.sourceFile('mock_campaign.csv');
    expect(visibleNodeIds(initial, graph)).not.toContain(target);
    const revealed = apply(initial, { kind: 'reveal', nodeId: target });
    expect(revealed.selectedId).toBe(target);
    expect(visibleNodeIds(revealed, graph)).toContain(target);
    expect(revealed.search).toBe('');
  });

  it('clamps zoom and resets to the initial expansion', () => {
    let state = initial;
    for (let i = 0; i < 60; i += 1) state = apply(state, { kind: 'zoom', factor: 2 });
    expect(state.view.scale).toBeLessThanOrEqual(24);
    for (let i = 0; i < 60; i += 1) state = apply(state, { kind: 'zoom', factor: 0.5 });
    expect(state.view.scale).toBeGreaterThanOrEqual(0.25);

    const reset = apply(state, { kind: 'reset' });
    expect(reset.expanded).toEqual([graph.anchorId]);
    expect(reset.selectedId).toBe(graph.anchorId);
  });

  it('hides a kind on request but never hides the anchor', () => {
    const hidden = apply(
      apply(initial, { kind: 'expand', nodeId: nodeIds.section('Sample') }),
      { kind: 'toggleKind', nodeKind: 'field' },
    );
    const visible = visibleNodeIds(hidden, graph);
    expect(visible).not.toContain(nodeIds.field('sample.material.formula'));
    expect(visible).toContain(graph.anchorId);
  });

  it('marks a drawn node that still has undrawn neighbours as expandable', () => {
    const expandable = expandableNodeIds(initial, graph);
    expect(expandable.has(nodeIds.section('Sample'))).toBe(true);
    expect(expandable.has(graph.anchorId)).toBe(false); // already expanded
  });

  it('is deterministic — the same input yields identical ids, edges and coordinates', () => {
    const a = build(exportedExperimentGraphBundle());
    const b = build(exportedExperimentGraphBundle());
    expect(a.nodes.map((n) => n.id)).toEqual(b.nodes.map((n) => n.id));
    expect(a.edges.map((e) => `${e.kind}|${e.source}|${e.target}`)).toEqual(
      b.edges.map((e) => `${e.kind}|${e.source}|${e.target}`),
    );
    for (const node of a.nodes) {
      expect(a.layout.get(node.id)).toEqual(b.layout.get(node.id));
    }
  });
});

describe('experiment graph — the viewBox is aspect-aware', () => {
  const graph = build(experimentGraphBundle());

  it('emits a viewBox matching the measured box, not a square', () => {
    const box = viewBoxFor({ cx: 0, cy: 0, scale: 2 }, { width: 800, height: 400 });
    expect(box).toBe('-200 -100 400 200');
  });

  it('fits against BOTH dimensions, so a wide short canvas does not crop', () => {
    const ids = visibleNodeIds(initialExperimentGraphState(graph), graph);
    const wide = fitExperimentViewport(ids, graph, { width: 900, height: 300 });
    const tall = fitExperimentViewport(ids, graph, { width: 300, height: 900 });
    // The limiting dimension differs, so the two scales differ — a square
    // viewBox would have produced the same number for both.
    expect(wide.scale).not.toBe(tall.scale);
    expect(wide.cx).toBe(tall.cx);
  });

  it('frames every visible node inside the box it was fitted to', () => {
    const box = { width: 820, height: 460 };
    const state = initialExperimentGraphState(graph);
    const ids = visibleNodeIds(state, graph);
    const view = fitExperimentViewport(ids, graph, box);
    const halfW = box.width / view.scale / 2;
    const halfH = box.height / view.scale / 2;
    for (const id of ids) {
      const p = graph.layout.get(id);
      if (!p) continue;
      expect(Math.abs(p.x - view.cx)).toBeLessThanOrEqual(halfW);
      expect(Math.abs(p.y - view.cy)).toBeLessThanOrEqual(halfH);
    }
  });
});

describe('experiment graph — search within this experiment', () => {
  const graph = build(exportedExperimentGraphBundle());

  it('matches on the label and reports what matched', () => {
    const hits = searchExperimentGraph('absorption', graph);
    expect(hits.length).toBeGreaterThan(0);
    expect(hits[0].matchedOn).toContain('absorption');
  });

  it('matches on an already-server-derived detail value', () => {
    const hits = searchExperimentGraph('mock_campaign.csv', graph);
    expect(hits.some((h) => h.kind === 'source_file' || h.kind === 'evidence')).toBe(true);
  });

  it('returns nothing rather than a near match', () => {
    expect(searchExperimentGraph('absorbtion', graph)).toEqual([]);
    expect(searchExperimentGraph('   ', graph)).toEqual([]);
  });

  it('is bounded', () => {
    const hits = searchExperimentGraph('e', graph);
    expect(hits.length).toBeLessThanOrEqual(MAX_SEARCH_RESULTS);
  });
});

/*
 * THE HARNESS DEADLINE, on the two tests below that declare a time budget.
 *
 * `buildMs < 6000` sat ABOVE vitest's 5,000 ms default, which `vite.config.ts`
 * never overrides — so between 5 s and 6 s the ceiling could not adjudicate: the
 * harness fired first and reported "Test timed out in 5000ms", naming no budget.
 * The `interactionMs < 2000` ceiling below is nominally under the default, but
 * the deadline covers the whole test INCLUDING the untimed `build()` prelude,
 * so a slow build could pre-empt it in the same way.
 *
 * The ceilings are UNCHANGED — 6,000 and 2,000 are still the claims. Only the
 * harness limit moves, to the 30,000 ms this repository already uses elsewhere,
 * so that the ceiling is what fails first. This is a pure-model file and the
 * rest of it stays on the strict default; only these two tests are annotated.
 */
describe('experiment graph — a large but plausible experiment', () => {
  it('stays bounded, and SAYS it is bounded rather than truncating silently', () => {
    const started = performance.now();
    const graph = build(stressExperimentGraphBundle());
    const buildMs = performance.now() - started;

    expect(graph.nodes.length).toBeLessThanOrEqual(MAX_EXPERIMENT_NODES);
    if (graph.truncated) {
      expect(graph.notes.some((n) => n.kind === 'node_cap')).toBe(true);
    }
    // A generous ceiling: this is a smoke guard against an accidental
    // quadratic, not a benchmark. The measured local figure is far below it.
    expect(buildMs).toBeLessThan(6000);
  }, 30000);

  it('keeps INTERACTION responsive on it — 60 actions plus every derivation', () => {
    const graph = build(stressExperimentGraphBundle());
    let state = initialExperimentGraphState(graph);
    const expandTargets = graph.nodes.slice(0, 30).map((n) => n.id);

    const started = performance.now();
    for (const id of expandTargets) {
      state = applyExperimentGraphAction(state, { kind: 'expand', nodeId: id }, graph);
      const visible = visibleNodeIds(state, graph);
      visibleEdges(visible, graph);
      expandableNodeIds(state, graph);
    }
    for (let i = 0; i < 30; i += 1) {
      state = applyExperimentGraphAction(state, { kind: 'zoom', factor: 1.1 }, graph);
    }
    searchExperimentGraph('channel', graph);
    const interactionMs = performance.now() - started;

    expect(visibleNodeIds(state, graph).length).toBeLessThanOrEqual(MAX_VISIBLE_NODES);
    expect(interactionMs).toBeLessThan(2000);
  }, 30000);

  it('bounds what is DRAWN even when far more is expanded', () => {
    const graph = build(stressExperimentGraphBundle());
    let state = initialExperimentGraphState(graph);
    for (const node of graph.nodes) {
      state = applyExperimentGraphAction(state, { kind: 'expand', nodeId: node.id }, graph);
    }
    expect(visibleNodeIds(state, graph).length).toBeLessThanOrEqual(MAX_VISIBLE_NODES);
  });
});
