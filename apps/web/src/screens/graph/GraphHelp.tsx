/*
 * P36R Slice 6 — the graph help drawer. Content restructured in P36V PR2 slice B.
 *
 * Concise, not a documentation wall: what the graph is and is NOT, how to read
 * it, how to drive it, and where the honesty boundaries are. The focus contract
 * is the one AssistantDrawer already proved — capture-phase keydown, Escape to
 * close, Tab cycling contained in the panel, focus restored to the invoking
 * control by the owner's onClose. That MECHANISM is untouched here.
 *
 * P36V PR2 slice B restructured the CONTENT into ten named sections, in this
 * order: What This Graph Shows · What It Does Not Show · Graph Data · Node Types
 * · Cluster Colors · Relationship Types · How to Explore · Command Bar ·
 * Keyboard Controls · Technical Details. Nine carry an `<h4>`; Technical Details
 * is a `<details>` whose `<summary>` carries its title as plain text (see the
 * comment at that section). Command Bar has ONE nested `<h5>` — "Asking the
 * Assistant" — so the Assistant material is findable without becoming an
 * eleventh top-level section. It folded in the twelve previous
 * headings and the unheaded blocks WITHOUT dropping a fact, and it absorbed four
 * disclosures the graph surface used to stack above its own canvas: the
 * un-embedded source graph's figures and the four-layer projection chain (→
 * Graph Data), the full cluster caveat (→ Cluster Colors), and the provenance
 * fingerprint (→ Technical Details, collapsed).
 *
 * One fact was CORRECTED rather than moved. The old "Relationship types" section
 * said "nothing is renamed or collapsed". Relationship values are now displayed
 * through a closed five-value label map, so that sentence had become false: the
 * section now shows the readable label AND the backend's own value side by side
 * and says which of the two the filter and the `relation` command match.
 */
import { useEffect, useId, useRef } from 'react';
import { X } from '../../components/icons';
import type { ApiMemoryGraphMeta } from '../../lib/types';
import { relationDisplayLabel } from '../../lib/displayLabels';
import { GRAPH_COMMANDS } from '../../lib/graphCommands';
import {
  HUB_LABEL_COUNT,
  LABEL_LIMIT,
  MAX_NEIGHBORHOOD_NODES,
  MAX_RENDER_NODES,
} from '../../lib/graphModel';

interface GraphHelpProps {
  meta: ApiMemoryGraphMeta;
  relationTypes: string[];
  paletteSlots: number;
  communityCount: number;
  singletonCount: number;
  onClose: () => void;
}

export function GraphHelp({
  meta,
  relationTypes,
  paletteSlots,
  communityCount,
  singletonCount,
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
          A reference map of this project's <em>served files and concepts</em> — which file mentions
          or imports which other file. It is memory-plane material: leads to verify.
        </p>

        <div className="graph-help-section">
          <h4>What This Graph Shows</h4>
          <p>
            Files this deployment serves, the concepts anchored in its docs, and the references
            recorded between them. A line between two files means those files reference each other
            in the project source — that, and nothing more.
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

        <p className="graph-help-note">
          Project Memory is advisory. Nothing here validates a record, completes a field, or
          authorises an export — those decisions belong to the official schema and the deterministic
          validators, never to this graph.
        </p>

        <div className="graph-help-section">
          <h4>Graph Data</h4>
          <p>
            This tab is a served-file reference projection only, never the full source graph. Four
            layers stand between the two:
          </p>
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
              {/* Pluralised the same way the surface's own count line does
                  (`MemoryGraphCard`'s `memory-graph-counts`): a one-edge
                  projection read "1 references" here while reading "1 reference"
                  three lines up the page. */}
              {meta.counts.files} file{meta.counts.files === 1 ? '' : 's'},{' '}
              {meta.counts.reference_edges} reference
              {meta.counts.reference_edges === 1 ? '' : 's'}. This is what you see.
            </li>
            <li>
              <span className="graph-help-term">3 · Concepts</span> — {meta.counts.concepts} curated
              concepts anchored in project docs. They carry no edges in this projection.
            </li>
            <li>
              <span className="graph-help-term">4 · Clusters</span> —{' '}
              {meta.counts.communities_rendered} automatically-derived groupings, advisory only,
              shown as colour and as a filter.
            </li>
          </ul>
        </div>

        <div className="graph-help-section">
          <h4>Node Types</h4>
          <ul className="graph-help-list graph-help-legend">
            <li>
              <span className="graph-help-swatch shape-file" aria-hidden="true" />
              <span className="graph-help-term">Circle</span> — a file.
            </li>
            <li>
              <span className="graph-help-swatch shape-concept" aria-hidden="true" />
              <span className="graph-help-term">Diamond</span> — a concept.
            </li>
          </ul>
          <p className="graph-help-example">Shape, not colour, carries this distinction.</p>
        </div>

        <div className="graph-help-section">
          <h4>Cluster Colors</h4>
          <p>
            The {paletteSlots} largest clusters get a distinct colour; every other node is drawn
            neutral grey. {communityCount} clusters exist and {singletonCount} of them contain a
            single file, so colouring all of them would be unreadable and would imply a structure the
            data does not have.
          </p>
          <p className="graph-help-example">
            Clusters are derived automatically by the upstream graph builder and named after one
            representative node. They are advisory labels, not categories the schema recognises — and
            the name is shown exactly as the builder wrote it, never tidied up.
          </p>
        </div>

        <div className="graph-help-section">
          <h4>Relationship Types</h4>
          {relationTypes.length > 0 ? (
            <ul className="graph-help-list graph-help-legend">
              {relationTypes.map((rel) => (
                <li key={rel}>
                  <span className="graph-help-term">{relationDisplayLabel(rel)}</span>{' '}
                  <span className="graph-help-kbd mono">{rel}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p>No relationship types are present in this projection.</p>
          )}
          <p className="graph-help-example">
            The readable label is display only; the value beside it is the backend's own, and it is
            what the Relationship Types filter and the <span className="mono">relation</span> command
            match. No value is collapsed into another, and a value with no readable label is shown
            exactly as the backend wrote it. The filter restricts which references are drawn, and
            which connections a neighbourhood or path may travel through.
          </p>
        </div>

        <div className="graph-help-section">
          <h4>How to Explore</h4>
          <p>
            <span className="graph-help-term">Explore</span> is the visual canvas.{' '}
            <span className="graph-help-term">Browse</span> is the same graph as text — a searchable
            list, keyboard selection, connected nodes and raw node data. Browse is permanent, not a
            fallback: every graph capability is reachable there without a pointer.
          </p>
          <ul className="graph-help-list">
            <li>
              <span className="graph-help-term">Search</span> — matches a file path or concept label
              anywhere in the string.
            </li>
            <li>
              <span className="graph-help-term">Filters</span> — node type, cluster, and relationship
              type, behind the Filters button. They combine, the button reports how many are on, and
              the count line always says how many nodes survive.
            </li>
            <li>
              <span className="graph-help-term">Neighbourhood</span> — from a selected node, show
              everything 1 hop or 2 hops away. Bounded; see Technical Details.
            </li>
            <li>
              <span className="graph-help-term">Find a Path</span> — the shortest route between two
              nodes. Ambiguous input lists candidates instead of guessing; no route is reported as no
              route.
            </li>
            <li>
              Drag the background to pan; drag a node to move it.{' '}
              <span className="graph-help-term">Fit to View</span> frames everything currently
              visible; <span className="graph-help-term">Reset View</span> restores the default view
              and undoes node drags.
            </li>
            <li>
              Nodes with no recorded reference are parked on the outer rings. The ring is where they
              are put, not a relationship between them.
            </li>
          </ul>
          <p className="graph-help-example">
            example · path from src/isaac_records/export.py to src/isaac_records/audit.py
          </p>
        </div>

        {/* P36R S4 — the command grammar, generated from the SAME catalog the
            parser and the completion list read (`GRAPH_COMMANDS`), so the help
            can never document a command that does not exist, or miss one. */}
        <div className="graph-help-section">
          <h4>Command Bar</h4>
          <p>
            The command bar accepts this fixed list and nothing else. Each command does exactly what
            a control on this page does — it runs no code, reads no files, and changes no record.
          </p>
          <ul className="graph-help-list graph-help-commands">
            {GRAPH_COMMANDS.map((c) => (
              <li key={c.verb}>
                <span className="graph-help-kbd mono">{c.syntax}</span> {c.summary}
              </li>
            ))}
          </ul>
          <p className="graph-help-example">
            examples · <span className="mono">find export</span> ·{' '}
            <span className="mono">neighbors src/isaac_records/export.py depth 2</span> ·{' '}
            <span className="mono">path src/isaac_records/export.py -&gt; src/isaac_records/audit.py</span>{' '}
            · <span className="mono">relation imports</span> ·{' '}
            <span className="mono">clear filters</span>
          </p>
          <p className="graph-help-example">
            An unknown node lists nothing rather than guessing; an ambiguous one lists the candidates
            and stops. The command history is kept in this browser tab for this visit only — it is
            never saved and never sent anywhere.
          </p>
          <p className="graph-help-example">
            Sharing a link: the address bar is updated by commands and by applied Assistant
            proposals, not by every control. Typing in the search box or changing a filter leaves the
            URL where the last command left it — run the equivalent command (or re-run{' '}
            <span className="mono">fit</span>) before copying the link if you want the view you are
            looking at.
          </p>
          {/* A findable heading, nested INSIDE Command Bar rather than an
              eleventh top-level section: the Assistant is a second text
              front-end onto the same bounded action set, so it belongs under
              this heading — but as an unheaded trailing paragraph it read as a
              footnote about the command bar itself, which mis-scoped it. */}
          <h5 className="graph-help-subheading">Asking the Assistant</h5>
          <p>
            On this tab the Assistant also recognises a bounded set of graph questions — neighbours,
            routes, clusters, relationship filters, and resets. It resolves them against this same
            projection, explains what it found, and offers an explicit{' '}
            <span className="graph-help-term">Apply to Graph</span>. It never changes the graph
            before you apply it, never guesses an ambiguous name, and refuses anything outside that
            list rather than improvising.
          </p>
        </div>

        <div className="graph-help-section">
          <h4>Keyboard Controls</h4>
          <ul className="graph-help-list">
            <li>
              <span className="graph-help-kbd">Tab</span> reaches the canvas; arrow keys then pan it.
            </li>
            <li>
              <span className="graph-help-kbd">+</span> / <span className="graph-help-kbd">-</span>{' '}
              zoom, <span className="graph-help-kbd">0</span> resets,{' '}
              <span className="graph-help-kbd">f</span> fits.
            </li>
            <li>
              <span className="graph-help-kbd">Tab</span> again reaches the nodes; arrow keys move
              between them and <span className="graph-help-kbd">Enter</span> selects.
            </li>
            <li>
              <span className="graph-help-kbd">Esc</span> closes this panel.
            </li>
          </ul>
        </div>

        {/* Collapsed by default: the snapshot fingerprint and the render bounds
            are the last thing a first-time reader needs and the first thing a
            reviewer asks for. Closed, not absent. */}
        <details className="graph-help-section graph-help-technical">
          {/* Plain text, NOT a nested <h4>. A heading inside <summary> makes the
              disclosure's accessible name a heading node, which assistive tech
              announces awkwardly (and some AT reports the heading and the button
              as two separate things saying the same words). The summary is
              already a named, keyboard-operable control; it carries the section's
              title itself and is styled to match the other section headings. */}
          <summary>Technical Details</summary>
          <p className="graph-help-example">
            commit {meta.provenance.built_at_commit ?? '—'} · source sha256{' '}
            {meta.provenance.source_graph_sha256 ?? '—'} · schema v
            {meta.provenance.snapshot_schema_version ?? '—'} · {meta.provenance.provider} ·
            integrity {meta.provenance.integrity}
          </p>
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
              Layout is deterministic: the same payload always yields the same coordinates. There is
              no physics loop and no randomness.
            </li>
          </ul>
        </details>
      </div>
    </div>
  );
}
