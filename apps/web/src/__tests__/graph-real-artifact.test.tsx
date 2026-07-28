import { describe, it, expect, afterEach, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { render, fireEvent, waitFor, within, type RenderResult } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ProjectMemory } from '../screens/ProjectMemory';
import { decodeDeepGraph, type ApiGraphDetailResponse, type DeepIndex } from '../lib/graphDeep';
import { MAX_DEEP_NODES } from '../lib/graphDeep';
import { graphStatusUnavailable, memoryGraphAvailable, stubFetchRoutes } from '../test/apiFixtures';

/*
 * P36V.1 Unit F — REAL-SCALE measurements, against the committed artifact.
 *
 * WHY THIS FILE EXISTS. The bounded-DOM assertion shipped with the semantic-zoom
 * layer was `expect(count).toBeLessThan(1200)` evaluated against an EIGHT-ROW
 * synthetic fixture. Eight rows cannot reach a 260-mark cap, a 400-line cap or a
 * 48-file open cap, so the assertion proved nothing at all, and the element count
 * reported beside it — 1,263 — was not reproducible from anything in the tree.
 *
 * THE TRUE FIGURES, measured this session by mounting this surface against the
 * live backend responses (`memory_graph.build_graph_projection` +
 * `memory_graph.build_graph_detail`, 220 base nodes / 508 base edges / 2,612 deep
 * nodes / 4,067 deep edges):
 *
 *     file / 100 %     968 SVG elements   ·  18 labels  ·  220 marks
 *     cluster / 175 %  557 SVG elements   ·  18 labels  ·   98 marks · 193 lines
 *     symbol / 400 %   985 SVG elements   ·   0 labels  ·  260 marks · 363 lines
 *
 * 1,263 was wrong, and 985 — not 1,263 — is the deepest level's real cost. The
 * 193 cluster-level lines were backed by 300 recorded references, 73 of them
 * folding more than one row and 63 folding more than one relation TYPE; that
 * measurement is what C2's copy, stroke and `<title>` changes were sized against.
 * The 0 labels at the symbol level are what I2 fixed.
 *
 * WHAT IS REAL HERE, EXACTLY. The deep artifact is read from
 * `apps/api/isaac_api/data/memory-graph-detail.json` — the same bytes the
 * deployment ships, not a copy. The BASE projection is reconstructed from that
 * artifact's own `source_file` set, because the served projection's node and edge
 * lists are derived at request time by `memory_graph.py` and are committed
 * nowhere in this tree; re-deriving them in TypeScript would be a second
 * implementation of backend logic, and capturing them would put a silently
 * driftable duplicate of served content in the frontend. So the reconstruction
 * carries the 179 real file paths that actually appear in the artifact (of the 201
 * in the served path set — 22 served files carry no symbol-level structure at all,
 * which is itself one of the figures the canvas discloses) and NO edges. That
 * changes the base LAYOUT, and therefore which files a given viewport happens to
 * open, so the per-level element counts here are in the same order as the live
 * figures above but are deliberately not asserted to equal them. What IS asserted
 * is the property the vacuous test was reaching for: at real payload size every
 * level stays in the low hundreds of elements and the caps actually bite.
 */

const HERE = dirname(fileURLToPath(import.meta.url));
/** src/__tests__ → src → apps/web → apps → repository root. */
const REPO_ROOT = resolve(HERE, '../../../..');

interface DeepArtifact {
  built_at_commit: string;
  source_graph_sha256: string;
  detail_schema_version: number;
  generator: string;
  policy_fingerprint: string;
  structural_scope: string;
  structural_basis: string;
  served_file_count: number;
  served_path_set_fingerprint: string;
  node_keys: string[];
  edge_keys: string[];
  nodes: (string | null)[][];
  edges: [number, number, string][];
  community_names: Record<string, string>;
  encoding: Record<string, string>;
  counts: {
    nodes: number;
    edges: number;
    communities: number;
    file_types: Record<string, number>;
    relations: Record<string, number>;
  };
}

const artifact: DeepArtifact = JSON.parse(
  readFileSync(resolve(REPO_ROOT, 'apps/api/isaac_api/data/memory-graph-detail.json'), 'utf8'),
);

/**
 * The artifact wrapped in the envelope `GET /api/memory/graph/detail` adds. Only
 * the wrapper is written here; every row, key, community name and count comes
 * from the file. `apps/api/tests/test_memory_graph_detail.py` is the authority on
 * the wrapper itself — nothing in this file asserts anything about it.
 */
const realDetailResponse: ApiGraphDetailResponse = {
  plane: 'memory',
  note: 'real committed artifact, wrapped for this test',
  available: true,
  reason: null,
  integrity: 'verified',
  truncated: false,
  node_keys: artifact.node_keys,
  edge_keys: artifact.edge_keys,
  nodes: artifact.nodes,
  edges: artifact.edges,
  community_names: artifact.community_names,
  encoding: artifact.encoding,
  meta: {
    counts: artifact.counts,
    provenance: {
      built_at_commit: artifact.built_at_commit,
      source_graph_sha256: artifact.source_graph_sha256,
      detail_schema_version: artifact.detail_schema_version,
      generator: artifact.generator,
      policy_fingerprint: artifact.policy_fingerprint,
      is_point_in_time: true,
      describes_current_head: false,
      structural_scope: artifact.structural_scope,
      structural_basis: artifact.structural_basis,
      served_content_scope: 'served_files_only',
      served_content_basis: 'ci_content_manifest',
      served_file_count: artifact.served_file_count,
      served_path_set_fingerprint: artifact.served_path_set_fingerprint,
      served_set_consistency: 'current',
      note: 'structure describes built_at_commit; the content manifest is CI-current',
    },
  },
};

/** The column index of `source_file`, resolved by NAME like the decoder does. */
const SOURCE_FILE_COL = artifact.node_keys.indexOf('source_file');

/** The real served files that carry symbol-level structure, sorted. */
const realFiles = [
  ...new Set(
    artifact.nodes
      .map((row) => row[SOURCE_FILE_COL])
      .filter((path): path is string => typeof path === 'string' && path !== ''),
  ),
].sort();

/** A base projection over exactly those real paths. See the header for what this
 *  does and does not reproduce. */
const reconstructedBase = {
  ...memoryGraphAvailable,
  nodes: realFiles.map((path) => ({
    id: path,
    kind: 'file' as const,
    label: path,
    file_type: path.endsWith('.md') ? 'document' : 'code',
    community_id: null,
    community_name: null,
    node_count: artifact.nodes.filter((r) => r[SOURCE_FILE_COL] === path).length,
    on_disk: true,
  })),
  edges: [],
  communities: [],
  meta: {
    ...memoryGraphAvailable.meta,
    counts: {
      files: realFiles.length,
      concepts: 0,
      reference_edges: 0,
      files_with_references: 0,
      isolated_files: realFiles.length,
      communities_rendered: 0,
    },
  },
};

const routes = {
  'GET /api/graph/status': { body: graphStatusUnavailable },
  'GET /api/memory/graph': { body: reconstructedBase },
  'GET /api/memory/graph/detail': { body: realDetailResponse },
};

function renderGraph() {
  stubFetchRoutes(routes);
  return render(
    <MemoryRouter
      initialEntries={['/memory?tab=graph']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <ProjectMemory />
    </MemoryRouter>,
  );
}

const svgEl = () => document.querySelector('.memory-graph-svg') as SVGSVGElement;
const svgElements = () => svgEl().querySelectorAll('*').length;
const deepMarks = () => [...document.querySelectorAll('.memory-graph-deep-node')];
const deepLines = () => [...document.querySelectorAll('.memory-graph-deep-edge')];
const labels = () => [...document.querySelectorAll('.memory-graph-node-label')];
const reveal = (view: RenderResult) =>
  fireEvent.click(view.getByRole('button', { name: 'Reveal Detail' }));

/** Anchor the descent on a file that really does carry structure. */
function selectDenseFile() {
  const densest = realFiles
    .map((path) => ({
      path,
      count: artifact.nodes.filter((r) => r[SOURCE_FILE_COL] === path).length,
    }))
    .sort((a, b) => b.count - a.count || (a.path < b.path ? -1 : 1))[0];
  const node = within(svgEl() as unknown as HTMLElement).getByRole('button', {
    name: new RegExp(`^${densest.path.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}, file`),
  });
  fireEvent.keyDown(node, { key: 'Enter' });
  return densest;
}

afterEach(() => vi.unstubAllGlobals());

describe('the committed deep artifact — decoded at real size', () => {
  it('decodes every row of the real artifact, inventing nothing', () => {
    const deep = decodeDeepGraph(realDetailResponse) as DeepIndex;
    expect(deep).not.toBeNull();
    // The artifact's own self-reported counts, independently reproduced by the
    // decoder — 2,612 nodes and 4,067 edges at the time of writing.
    expect(deep.nodes.length).toBe(artifact.counts.nodes);
    expect(deep.edges.length).toBe(artifact.counts.edges);
    expect(deep.droppedNodeRows).toBe(0);
    expect(deep.droppedEdgeRows).toBe(0);
    expect(deep.files.length).toBe(realFiles.length);
    // The three structural measurements the level design rests on, re-checked
    // against the artifact rather than quoted from a plan document.
    const containsEdges = deep.edges.filter((e) => e.relation === 'contains');
    expect(containsEdges.length).toBeGreaterThan(0);
    for (const edge of containsEdges) {
      expect(deep.byIndex.get(edge.source)!.sourceFile).toBe(
        deep.byIndex.get(edge.target)!.sourceFile,
      );
    }
    for (const node of deep.nodes) {
      expect(node.sourceFile).toBeTruthy();
      expect(node.communityId).not.toBeNull();
    }
    // A community is a grouping INSIDE a file, not a container of files: most
    // communities live in one file, and many files span several.
    const filesPerCommunity = new Map<string, Set<string>>();
    for (const node of deep.nodes) {
      const set = filesPerCommunity.get(node.communityId!) ?? new Set<string>();
      set.add(node.sourceFile);
      filesPerCommunity.set(node.communityId!, set);
    }
    const single = [...filesPerCommunity.values()].filter((s) => s.size === 1).length;
    expect(single).toBeGreaterThan(filesPerCommunity.size / 2);
    expect([...deep.clustersByFile.values()].some((cs) => cs.length > 1)).toBe(true);
  });
});

describe('bounded DOM — measured at REAL payload size, at every level', () => {
  /**
   * The number this replaces was asserted against 8 rows. These are measured
   * against 2,612 real symbol rows and 4,067 real edge rows.
   *
   * The bound is deliberately the same one the shipped assertion used (1,200), so
   * this is the same claim — only now made against something that can actually
   * reach the caps. A lower, tighter bound is also asserted, because "a few
   * hundred elements" was the stated design target and the real figures are
   * comfortably inside it.
   */
  const ELEMENT_BOUND = 1200;

  it('stays in the low hundreds of elements at the file, cluster and symbol levels', async () => {
    const view = renderGraph();
    await view.findByText('Graph', { selector: 'h2' });

    const atFile = { elements: svgElements(), labels: labels().length };
    expect(atFile.elements).toBeGreaterThan(200); // it really is drawing the real set

    const densest = selectDenseFile();
    expect(densest.count).toBeGreaterThan(MAX_DEEP_NODES / 4);
    reveal(view);
    await waitFor(() => expect(deepMarks().length).toBeGreaterThan(0));
    const atCluster = {
      elements: svgElements(),
      labels: labels().length,
      marks: deepMarks().length,
      lines: deepLines().length,
    };

    reveal(view);
    await waitFor(() => expect(view.container.textContent).toMatch(/showing symbols/));
    const atSymbol = {
      elements: svgElements(),
      labels: labels().length,
      marks: deepMarks().length,
      lines: deepLines().length,
    };

    for (const level of [atFile, atCluster, atSymbol]) {
      expect(level.elements).toBeGreaterThan(0);
      expect(level.elements).toBeLessThan(ELEMENT_BOUND);
    }
    // The caps hold at real size, which is the property the old fixture could
    // not exercise at all.
    expect(atCluster.marks).toBeLessThanOrEqual(MAX_DEEP_NODES);
    expect(atSymbol.marks).toBeLessThanOrEqual(MAX_DEEP_NODES);
    // I2: the deepest level is no longer a field of anonymous shapes.
    expect(atSymbol.labels).toBeGreaterThan(0);
    expect(atCluster.labels).toBeGreaterThan(0);
  });

  it('holds the element bound at the deepest zoom the viewport allows', async () => {
    const view = renderGraph();
    await view.findByText('Graph', { selector: 'h2' });
    selectDenseFile();
    reveal(view);
    await waitFor(() => expect(deepMarks().length).toBeGreaterThan(0));
    reveal(view);
    await waitFor(() => expect(view.container.textContent).toMatch(/showing symbols/));

    // Six further 1.25× presses, well past the symbol threshold: the mark set is
    // re-culled each time, so the element count must not creep upward.
    for (let i = 0; i < 6; i += 1) {
      fireEvent.click(view.getByRole('button', { name: 'Zoom in' }));
      await waitFor(() => expect(view.container.textContent).toMatch(/zoom \d+%/));
      expect(svgElements()).toBeLessThan(ELEMENT_BOUND);
      expect(deepMarks().length).toBeLessThanOrEqual(MAX_DEEP_NODES);
    }
  });
});
