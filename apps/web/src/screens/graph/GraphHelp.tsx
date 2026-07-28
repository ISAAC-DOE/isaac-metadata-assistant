/*
 * About This Graph — the graph help dialog.
 *
 * P36R S6 shipped the drawer; P36V PR2 slice B restructured its content into ten
 * named prose sections. P36V.1 Unit G rebuilt it as IN-PRODUCT HELP rather than a
 * document: the first screenful now answers what the graph shows, what it does
 * NOT show, what the marks mean, and how to drive it — in short bullets and
 * visual rows — and the reference material (exact counts, the snapshot
 * fingerprint, the projection-layer chain, the builder's raw relationship
 * identifiers, the render bounds, the detailed keyboard table) moved into ONE
 * collapsed Technical Details disclosure.
 *
 * WHAT DID NOT MOVE, and must never move: the two boundary statements.
 *   1. Project Memory is advisory — leads to verify, never a verdict.
 *   2. Structural staleness — the graph's STRUCTURE is a point-in-time index of
 *      `built_at_commit`, while content integrity is a separate axis. A
 *      2,612-node symbol map reads as a map of the current code and is not one.
 * Both stay in the first viewport, un-collapsed. Concision is about removing
 * repetition and relocating reference data; a caveat behind a closed disclosure
 * is a caveat withheld.
 *
 * P36V.1 Unit G also closed a documentation gap Unit F reported: nothing here
 * described semantic zoom, its three levels, the Reveal Detail control, the
 * lazily-fetched symbol layer, the fact that deep marks are not draggable, or
 * that search matches files rather than symbol names. Every keyboard shortcut
 * listed below was re-checked against `GraphCanvas.tsx`'s own handlers.
 *
 * The focus contract is untouched: capture-phase keydown, Escape to close, Tab
 * cycling contained in the panel, focus restored to the invoking control by the
 * owner's onClose.
 */
import { useEffect, useId, useRef } from 'react';
import { X } from '../../components/icons';
import type { ApiMemoryGraphMeta } from '../../lib/types';
import { relationDisplayLabel } from '../../lib/displayLabels';
import { GRAPH_COMMANDS } from '../../lib/graphCommands';
import {
  HUB_LABEL_COUNT,
  LABEL_LIMIT,
  LOD_CLUSTER_SCALE,
  LOD_SYMBOL_SCALE,
  MAX_NEIGHBORHOOD_NODES,
  MAX_RENDER_NODES,
  MAX_SCALE,
} from '../../lib/graphModel';
import {
  DEEP_HUB_LABEL_COUNT,
  DEEP_LABEL_LIMIT,
  MAX_DEEP_EDGES,
  MAX_DEEP_NEIGHBORS,
  MAX_DEEP_NODES,
  MAX_OPEN_FILES,
} from '../../lib/graphDeep';

/**
 * Which disclosure the dialog opens expanded.
 *
 * `commands` — opened from the bar's "Syntax" control or by typing `help`, where
 * the grammar IS what was asked for. `technical` — opened from the "View
 * Technical Details" suggestion. Absent — the plain "About This Graph" trigger:
 * everything reference-shaped stays closed.
 */
export type GraphHelpExpand = 'commands' | 'technical';

interface GraphHelpProps {
  meta: ApiMemoryGraphMeta;
  relationTypes: string[];
  paletteSlots: number;
  communityCount: number;
  singletonCount: number;
  expand?: GraphHelpExpand | null;
  onClose: () => void;
}

const pct = (scale: number): string => `${Math.round(scale * 100)}%`;

export function GraphHelp({
  meta,
  relationTypes,
  paletteSlots,
  communityCount,
  singletonCount,
  expand = null,
  onClose,
}: GraphHelpProps) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const titleId = useId();

  // Escape closes; Tab / Shift+Tab cycle inside the panel. Capture phase so the
  // dialog handles the key before anything beneath it (mirrors AssistantDrawer).
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
        return;
      }
      const panel = panelRef.current;
      if (e.key !== 'Tab' || !panel) return;
      e.preventDefault();
      const items = Array.from(
        panel.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), textarea, input:not([disabled]), select, [tabindex]:not([tabindex="-1"])',
        ),
      );
      if (items.length === 0) {
        panel.focus();
        return;
      }
      const last = items.length - 1;
      const active = document.activeElement as HTMLElement | null;
      const idx = active ? items.indexOf(active) : -1;
      let next: HTMLElement;
      if (idx === -1) next = e.shiftKey ? items[last] : items[0];
      else next = items[(idx + (e.shiftKey ? -1 : 1) + items.length) % items.length] ?? items[0];
      next.focus();
    }
    document.addEventListener('keydown', onKeyDown, true);
    return () => document.removeEventListener('keydown', onKeyDown, true);
  }, [onClose]);

  // Move focus into the panel on open. Focus RESTORATION is the owner's job
  // (it holds the trigger ref and calls onClose from every close path).
  useEffect(() => {
    panelRef.current?.focus();
  }, []);

  const u = meta.underlying_graph;
  const underlyingKnown = u.node_count != null && u.edge_count != null && u.community_count != null;
  const commit = meta.provenance.built_at_commit;
  const shortCommit = commit ? commit.slice(0, 7) : null;
  const counts = meta.counts;
  const plural = (n: number, one: string, many: string): string => (n === 1 ? one : many);

  return (
    <div
      className="graph-help-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        className="graph-help-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <div className="graph-help-head">
          <h3 className="graph-help-title" id={titleId}>
            About This Graph
          </h3>
          <button type="button" className="graph-help-close" aria-label="Close graph help" onClick={onClose}>
            <X size={16} strokeWidth={2} aria-hidden="true" />
          </button>
        </div>

        <p className="graph-help-lead">
          A reference map of this project's <em>served files and concepts</em> — and, zoomed in, the
          symbols inside them.
        </p>

        <div className="graph-help-section">
          <h4>What You Are Viewing</h4>
          <p>
            {counts.files} {plural(counts.files, 'file', 'files')} this deployment serves,{' '}
            {counts.concepts} {plural(counts.concepts, 'concept', 'concepts')} anchored in its docs,
            and {counts.reference_edges}{' '}
            {plural(counts.reference_edges, 'reference', 'references')} recorded between them, in{' '}
            {counts.communities_rendered}{' '}
            {plural(counts.communities_rendered, 'cluster', 'clusters')}. A line between two files
            means those files reference each other in the project source — that, and nothing more.
            It is a served-file reference projection only, never the full source graph.
          </p>
        </div>

        <div className="graph-help-section">
          <h4>What It Does Not Show</h4>
          <ul className="graph-help-list">
            <li>Not scientific relationships, and not causality.</li>
            <li>Not the provenance of a measured value.</li>
            <li>Not the truth plane: it is not a record and not a validation result.</li>
            <li>It says nothing about whether any experiment is correct.</li>
          </ul>
        </div>

        {/* THE TWO BOUNDARY STATEMENTS. Visible, in the first viewport, never
            inside a disclosure. See the file header. */}
        <div className="graph-help-note graph-help-boundary">
          <p>
            Project Memory is <strong>advisory</strong>: it returns leads to verify, never a verdict.
            Nothing here validates a record, completes a field, or authorises an export — those
            decisions belong to the official schema and the deterministic validators.
          </p>
          <p>
            Structure and content are <strong>two separate axes</strong>. The structure — which
            files, symbols and references exist — is a point-in-time index of{' '}
            {shortCommit ? (
              <>
                commit <span className="mono">{shortCommit}</span>
              </>
            ) : (
              'a commit the snapshot does not name'
            )}
            , so anything added, renamed or removed since then is absent from it, including work that
            exists in this running app. Content integrity — that the served files still hash to what
            the snapshot recorded — is a different check, reported in Technical Details. A current
            integrity check does not make the structure current.
          </p>
        </div>

        <div className="graph-help-section">
          <h4>Node Types</h4>
          <ul className="graph-help-list graph-help-legend graph-help-cols">
            <li>
              <span className="graph-help-swatch shape-file" aria-hidden="true" />
              <span className="graph-help-term">Circle</span> — a file; zoomed in, a cluster of
              symbols inside one file. The zoom level says which, because the shape is the same.
            </li>
            <li>
              <span className="graph-help-swatch shape-concept" aria-hidden="true" />
              <span className="graph-help-term">Diamond</span> — a concept.
            </li>
            <li>
              <span className="graph-help-swatch shape-symbol" aria-hidden="true" />
              <span className="graph-help-term">Rounded Square</span> — zoomed in: one symbol inside
              a file.
            </li>
            <li>
              <span className="graph-help-swatch shape-region" aria-hidden="true" />
              <span className="graph-help-term">Dashed Outline</span> — the file that the marks
              inside it belong to.
            </li>
            <li>
              <span className="graph-help-swatch shape-line" aria-hidden="true" />
              <span className="graph-help-term">Line</span> — a reference between two files. No
              direction is claimed.
            </li>
            <li>
              <span className="graph-help-swatch shape-arrow" aria-hidden="true" />
              <span className="graph-help-term">Line With an Arrow</span> — a directed reference;
              dashed means several.
            </li>
          </ul>
          <p className="graph-help-example">
            Shape, not colour, carries every distinction here. Only the {paletteSlots} largest
            clusters get a colour, everything else is neutral grey, so colour is a grouping hint and
            never the only carrier of meaning.
          </p>
          <p className="graph-help-example">
            Clusters are derived automatically by the upstream graph builder and named after one
            representative node: advisory groupings, not categories the schema recognises. Nodes with
            no recorded reference sit on the outer rings — where they are parked, not a relationship
            between them.
          </p>
        </div>

        <div className="graph-help-section">
          <h4>Relationships</h4>
          {relationTypes.length > 0 ? (
            <ul className="graph-help-list graph-help-cols">
              {relationTypes.map((rel) => (
                <li key={rel} title={rel}>
                  <span className="graph-help-term">{relationDisplayLabel(rel)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p>No relationship types are present in this projection.</p>
          )}
          <p className="graph-help-example">
            The filter restricts which references are drawn, and which a neighbourhood or route may
            travel through. The backend's own value for each is in Technical Details.
          </p>
        </div>

        <div className="graph-help-section">
          <h4>Quick Guide</h4>
          <ul className="graph-help-list graph-help-cols">
            <li>
              <span className="graph-help-term">Pan</span> — drag the background; drag a file node to
              move it.
            </li>
            <li>
              <span className="graph-help-term">Zoom</span> — the{' '}
              <span className="graph-help-kbd">+</span> / <span className="graph-help-kbd">-</span>{' '}
              buttons or keys. <span className="graph-help-term">Fit to View</span> frames what is
              visible; <span className="graph-help-term">Reset View</span> also undoes node drags.
            </li>
            <li>
              <span className="graph-help-term">Reveal Detail</span> — one press steps to the next
              zoom level, centred on your selection or the nearest visible node.
            </li>
            <li>
              <span className="graph-help-term">Hover or Focus</span> — describes a mark; the pointer
              and the keyboard give the identical description.
            </li>
            <li>
              <span className="graph-help-term">Select</span> — click a node or press{' '}
              <span className="graph-help-kbd">Enter</span> on it. On a symbol,{' '}
              <span className="graph-help-kbd">Enter</span> pins it and lists its references as text.
            </li>
            <li>
              <span className="graph-help-term">Search</span> — matches a file path or concept label
              anywhere in the string. It does not match symbol names.
            </li>
            <li>
              <span className="graph-help-term">Filters</span> — node type, cluster and reference
              type. Active ones stay visible as chips even with the panel closed.
            </li>
            <li>
              <span className="graph-help-term">Neighbourhood</span> — from a selected node,
              everything 1 hop or 2 hops away.
            </li>
            <li>
              <span className="graph-help-term">Find a Path</span> — the shortest route between two
              nodes. Ambiguous input lists candidates instead of guessing; no route is reported as no
              route.
            </li>
            <li>
              <span className="graph-help-kbd">Esc</span> closes this panel.
            </li>
          </ul>
          <p className="graph-help-example">
            Browse is permanent, not a fallback: the same graph as text, with keyboard selection,
            connected nodes and raw node data, symbol layer included.
          </p>
        </div>

        <div className="graph-help-section">
          <h4>Zoom Levels</h4>
          <p>
            Zooming reveals structure rather than magnifying the same marks — three levels, each
            drawn from a real field of the data:
          </p>
          <ul className="graph-help-list">
            <li>
              <span className="graph-help-term">Files</span> — below {pct(LOD_CLUSTER_SCALE)}: the
              served-file projection above.
            </li>
            <li>
              <span className="graph-help-term">Clusters</span> — {pct(LOD_CLUSTER_SCALE)} to{' '}
              {pct(LOD_SYMBOL_SCALE)}: groups of symbols inside each file, from the graph's own
              communities.
            </li>
            <li>
              <span className="graph-help-term">Symbols</span> — {pct(LOD_SYMBOL_SCALE)} and above:
              individual symbols and the references between them, direction preserved.
            </li>
          </ul>
          <ul className="graph-help-list">
            <li>
              The symbol layer is <strong>fetched only</strong> on your first zoom past the first
              level. Without that artifact the canvas stays on the file projection and says so —
              nothing is aggregated or estimated in its place.
            </li>
            <li>
              Cluster and symbol marks are <strong>not draggable</strong>: their position is derived
              from their file's, so moving one alone would misrepresent containment.
            </li>
            <li>
              A neighbourhood or route focus keeps the file projection it was computed over, so the
              deeper levels stay closed until the focus is cleared.
            </li>
          </ul>
        </div>

        {/* The command grammar is generated from the SAME catalog the parser and
            the completion list read (`GRAPH_COMMANDS`), so the help can never
            document a command that does not exist, or miss one. */}
        <div className="graph-help-section">
          <h4>Commands</h4>
          <p>
            The command bar accepts a fixed list and nothing else. Each command does what a control
            on this page does — it runs no code, reads no files, and changes no record.
          </p>
          <p className="graph-help-example">
            examples · <span className="mono">find export</span> ·{' '}
            <span className="mono">neighbors src/isaac_records/export.py depth 2</span> ·{' '}
            <span className="mono">path a -&gt; b</span> ·{' '}
            <span className="mono">relation imports</span> ·{' '}
            <span className="mono">clear filters</span>
          </p>
          <p>
            <span className="graph-help-term">Suggested Commands</span>, under the bar, fits a few
            to what you have selected. Clicking one puts that exact command in the bar and waits for
            you to press Run. The two exceptions act on the click itself and are labelled as such:{' '}
            <span className="graph-help-term">Fit to View</span> reframes the canvas, and{' '}
            <span className="graph-help-term">View Technical Details</span> opens this panel.
          </p>
          <p className="graph-help-example">
            An unknown node lists nothing rather than guessing; an ambiguous one lists the
            candidates and stops. History stays in this tab for this visit only — it is never saved
            and never sent anywhere.
          </p>
          <details className="graph-help-sub-details" open={expand === 'commands'}>
            <summary>Every Command</summary>
            <ul className="graph-help-list graph-help-commands">
              {GRAPH_COMMANDS.map((c) => (
                <li key={c.verb}>
                  <span className="graph-help-kbd mono">{c.syntax}</span> {c.summary}
                </li>
              ))}
            </ul>
            <p className="graph-help-example">
              Sharing a link: the address bar is updated by commands and by applied Assistant
              proposals, not by every control. Typing in the search box or changing a filter leaves
              the URL where the last command left it — run the equivalent command (or re-run{' '}
              <span className="mono">fit</span>) before copying the link if you want the view you are
              looking at. The zoom level and pan position are never encoded.
            </p>
          </details>
          {/* A findable heading nested INSIDE Commands: the Assistant is a second
              text front-end onto the same bounded action set. */}
          <h5 className="graph-help-subheading">Asking the Assistant</h5>
          <p>
            The Assistant recognises a bounded set of graph questions here — neighbours, routes,
            clusters, reference filters, resets — resolves them against this same projection, and
            offers an explicit <span className="graph-help-term">Apply to Graph</span>. It never
            changes the graph before you apply it, never guesses an ambiguous name, and refuses
            anything outside that list rather than improvising.
          </p>
        </div>

        {/* Collapsed by default: reference data. The exact counts, the snapshot
            fingerprint, the projection-layer chain, the builder's raw identifiers
            and the render bounds are the last thing a first-time reader needs and
            the first thing a reviewer asks for. Closed, not absent — and note
            that NO boundary or honesty statement lives in here. */}
        <details
          className="graph-help-section graph-help-technical"
          open={expand === 'technical'}
        >
          {/* Plain text, NOT a nested <h4>. A heading inside <summary> makes the
              disclosure's accessible name a heading node, which assistive tech
              announces awkwardly. */}
          <summary>Technical Details</summary>
          <p className="graph-help-example">
            commit {commit ?? '—'} · source sha256 {meta.provenance.source_graph_sha256 ?? '—'} ·
            schema v{meta.provenance.snapshot_schema_version ?? '—'} · {meta.provenance.provider} ·
            integrity {meta.provenance.integrity}
          </p>
          <p className="graph-help-technical-heading">Projection layers</p>
          <ul className="graph-help-list">
            <li>
              <span className="graph-help-term">1 · Source graph</span> —{' '}
              {underlyingKnown
                ? `${u.node_count} nodes / ${u.edge_count} edges / ${u.community_count} clusters`
                : 'the full upstream graph'}
              , built by Graphify. It is <strong>not embedded</strong> in this deployment.
            </li>
            <li>
              <span className="graph-help-term">2 · Served-file projection</span> — the subset of
              that graph covering only files this deployment is allowed to serve:{' '}
              {counts.files} {plural(counts.files, 'file', 'files')}, {counts.reference_edges}{' '}
              {plural(counts.reference_edges, 'reference', 'references')}. This is what you see.
            </li>
            <li>
              <span className="graph-help-term">3 · Concepts</span> — {counts.concepts} curated
              concepts anchored in project docs. They carry no edges in this projection.
            </li>
            <li>
              <span className="graph-help-term">4 · Clusters</span> —{' '}
              {counts.communities_rendered} automatically-derived groupings, advisory only, shown as
              colour and as a filter. {communityCount} clusters exist and {singletonCount} of them
              contain a single file, so only the {paletteSlots} largest are coloured.
            </li>
          </ul>
          {relationTypes.length > 0 && (
            <>
              <p className="graph-help-technical-heading">Relationship values</p>
              <ul className="graph-help-list graph-help-legend graph-help-cols">
                {relationTypes.map((rel) => (
                  <li key={rel}>
                    <span className="graph-help-term">{relationDisplayLabel(rel)}</span>{' '}
                    <span className="graph-help-kbd mono">{rel}</span>
                  </li>
                ))}
              </ul>
              <p className="graph-help-example">
                The readable label is display only; the value beside it is the backend's own, and it
                is what the Relationship Types filter and the <span className="mono">relation</span>{' '}
                command match. No value is collapsed into another, and a value with no readable label
                is shown exactly as the backend wrote it.
              </p>
            </>
          )}
          <p className="graph-help-technical-heading">Keyboard</p>
          <ul className="graph-help-list graph-help-keys">
            <li>
              <span className="graph-help-kbd">Tab</span> reaches the canvas; the arrow keys then pan
              it.
            </li>
            <li>
              <span className="graph-help-kbd">+</span> (or{' '}
              <span className="graph-help-kbd">=</span>) zooms in,{' '}
              <span className="graph-help-kbd">-</span> (or{' '}
              <span className="graph-help-kbd">_</span>) zooms out,{' '}
              <span className="graph-help-kbd">0</span> resets the view and{' '}
              <span className="graph-help-kbd">f</span> fits it. These four work while the canvas has
              focus and while any mark does.
            </li>
            <li>
              <span className="graph-help-kbd">Tab</span> again reaches the marks;{' '}
              <span className="graph-help-kbd">Home</span> and{' '}
              <span className="graph-help-kbd">End</span> jump to the first and last, the arrow keys
              move between them, and <span className="graph-help-kbd">Enter</span> or{' '}
              <span className="graph-help-kbd">Space</span> selects a file node or pins a symbol.
            </li>
            <li>
              In the command bar, <span className="graph-help-kbd">↑</span> recalls what you typed
              there, <span className="graph-help-kbd">Tab</span> accepts the highlighted completion
              and <span className="graph-help-kbd">Esc</span> closes the completion list, then clears
              the input.
            </li>
            <li>
              <span className="graph-help-kbd">Esc</span> closes this panel.
            </li>
          </ul>
          <p className="graph-help-technical-heading">Bounds</p>
          <ul className="graph-help-list">
            <li>
              Every visible node is labelled once {LABEL_LIMIT} or fewer are shown. Above that up to{' '}
              {HUB_LABEL_COUNT} of the most-connected nodes stay labelled as landmarks — plus the
              selected node and its connections — so the overview always has something to read.
            </li>
            <li>
              At most {MAX_RENDER_NODES} nodes are drawn at once; if that bound is ever reached the
              canvas says so instead of quietly hiding nodes.
            </li>
            <li>A neighbourhood expansion is bounded at {MAX_NEIGHBORHOOD_NODES} nodes.</li>
            <li>
              The deeper levels draw at most {MAX_DEEP_NODES} marks and {MAX_DEEP_EDGES} lines at
              once, opening at most {MAX_OPEN_FILES.cluster} files at the cluster level and{' '}
              {MAX_OPEN_FILES.symbol} at the symbol level. Zoom is clamped at {pct(MAX_SCALE)}.
            </li>
            <li>
              A symbol's local neighbourhood is bounded at {MAX_DEEP_NEIGHBORS} entries, and the
              deeper levels label at most {DEEP_HUB_LABEL_COUNT} landmark marks once more than{' '}
              {DEEP_LABEL_LIMIT} are drawn. Both bounds are stated on the canvas when they bite.
            </li>
            <li>
              A pinned symbol is released when you zoom out of the level that drew it, so no panel
              describes a mark that is gone. Browse keeps it — there it is the way in, not a canvas
              selection. In Browse, <strong>Load Symbol-Level Detail</strong> fetches the symbol layer
              on request and each file row then expands to its symbols.
            </li>
            <li>
              Layout is deterministic: the same payload always yields the same coordinates. There is
              no physics loop and no randomness. Positions inside a file are that layout, not a claim
              about the code's structure.
            </li>
            <li>
              What is a recorded graph object depends on the level, and the canvas says which. At the
              symbol level one mark is one recorded symbol and one line is one recorded reference. At
              the cluster level a mark is a <em>group</em> of symbols and a line <em>summarises</em>{' '}
              the references between two groups — one line can stand for several, of more than one
              kind — so a cluster-level line is a real count over real references, not a single
              recorded edge.
            </li>
          </ul>
        </details>
      </div>
    </div>
  );
}
