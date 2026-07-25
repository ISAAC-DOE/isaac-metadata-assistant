/*
 * P36R Slice 6 — the graph help drawer.
 *
 * Concise, not a documentation wall: what the graph is and is NOT, how to read
 * it, how to drive it, and where the honesty boundaries are. The focus contract
 * is the one AssistantDrawer already proved — capture-phase keydown, Escape to
 * close, Tab cycling contained in the panel, focus restored to the `i` trigger
 * by the owner's onClose.
 */
import { useEffect, useId, useRef } from 'react';
import { X } from '../../components/icons';
import type { ApiMemoryGraphMeta } from '../../lib/types';
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
            About this graph
          </h3>
          <button type="button" className="graph-help-close" aria-label="Close graph help" onClick={onClose}>
            <X size={16} strokeWidth={2} aria-hidden="true" />
          </button>
        </div>

        <p className="graph-help-lead">
          This is a reference map of the project's <em>served files and concepts</em> — which file
          mentions or imports which other file. It is memory-plane material: leads to verify. It is
          not a record, not a validation result, and it says nothing about whether any experiment is
          correct.
        </p>

        <div className="graph-help-section">
          <h4>What it does not represent</h4>
          <p>
            Not scientific relationships, not causality, not provenance of a measured value, and not
            the truth plane. A connection between two files says those files reference each other in
            the project source — nothing more.
          </p>
        </div>

        <div className="graph-help-section">
          <h4>Where the data comes from</h4>
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
              {meta.counts.files} files, {meta.counts.reference_edges} references. This is what you
              see.
            </li>
            <li>
              <span className="graph-help-term">3 · Concepts</span> — {meta.counts.concepts} curated
              concepts anchored in project docs. They carry no edges in this projection.
            </li>
            <li>
              <span className="graph-help-term">4 · Clusters</span> —{' '}
              {meta.counts.communities_rendered} automatically-derived groupings, shown as colour and
              as a filter.
            </li>
          </ul>
        </div>

        <div className="graph-help-section">
          <h4>Node shapes</h4>
          <ul className="graph-help-list">
            <li>
              <span className="graph-help-term">Circle</span> — a file.
            </li>
            <li>
              <span className="graph-help-term">Diamond</span> — a concept.
            </li>
          </ul>
          <p className="graph-help-example">Shape, not colour, carries this distinction.</p>
        </div>

        <div className="graph-help-section">
          <h4>Cluster colours</h4>
          <p>
            The {paletteSlots} largest clusters get a distinct colour; every other node is drawn
            neutral grey. {communityCount} clusters exist and {singletonCount} of them contain a
            single file, so colouring all of them would be unreadable and would imply a structure the
            data does not have. Cluster names come from one representative node and are advisory
            labels, not categories.
          </p>
        </div>

        <div className="graph-help-section">
          <h4>Relationship types</h4>
          <p>
            {relationTypes.length > 0
              ? relationTypes.join(' · ')
              : 'No relationship types are present in this projection.'}
          </p>
          <p className="graph-help-example">
            Values are the backend's own; nothing is renamed or collapsed. The Relationships filter
            restricts which references are drawn, and which connections a neighbourhood or path may
            travel through.
          </p>
        </div>

        <div className="graph-help-section">
          <h4>Finding things</h4>
          <ul className="graph-help-list">
            <li>
              <span className="graph-help-term">Search</span> — matches a file path or concept label
              anywhere in the string.
            </li>
            <li>
              <span className="graph-help-term">Filters</span> — node type, cluster, and relationship
              type. They combine; the count line always says how many nodes survive.
            </li>
            <li>
              <span className="graph-help-term">Neighbourhood</span> — from a selected node, show
              everything 1 hop or 2 hops away (bounded at {MAX_NEIGHBORHOOD_NODES} nodes).
            </li>
            <li>
              <span className="graph-help-term">Path</span> — the shortest route between two nodes.
              Ambiguous input lists candidates instead of guessing; no route is reported as no route.
            </li>
          </ul>
          <p className="graph-help-example">
            example · path from src/isaac_records/export.py to src/isaac_records/audit.py
          </p>
        </div>

        <div className="graph-help-section">
          <h4>Moving around the canvas</h4>
          <ul className="graph-help-list">
            <li>Drag the background to pan; drag a node to move it.</li>
            <li>
              <span className="graph-help-term">Fit</span> frames everything currently visible;{' '}
              <span className="graph-help-term">Reset</span> restores the default view and undoes
              node drags.
            </li>
            <li>
              Every visible node is labelled once {LABEL_LIMIT} or fewer are shown. Above that up to{' '}
              {HUB_LABEL_COUNT} of the most-connected nodes stay labelled as landmarks — plus the
              selected node and its connections — so the overview always has something to read.
            </li>
            <li>
              Nodes with no recorded reference are parked on the outer rings. The ring is where they
              are put, not a relationship between them.
            </li>
            <li>
              At most {MAX_RENDER_NODES} nodes are drawn at once; if that bound is ever reached the
              canvas says so instead of quietly hiding nodes.
            </li>
          </ul>
        </div>

        <div className="graph-help-section">
          <h4>Keyboard</h4>
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

        <div className="graph-help-section">
          <h4>Explore vs Browse</h4>
          <p>
            Explore is the visual canvas. Browse is the same graph as text — a searchable list,
            keyboard selection, connected nodes and raw node data. Browse is permanent, not a
            fallback: every graph capability is reachable there without a pointer.
          </p>
        </div>

        <div className="graph-help-section">
          <h4>Snapshot</h4>
          <p className="graph-help-example">
            commit {meta.provenance.built_at_commit ?? '—'} · source sha256{' '}
            {meta.provenance.source_graph_sha256 ?? '—'} · schema v
            {meta.provenance.snapshot_schema_version ?? '—'} · {meta.provenance.provider} ·
            integrity {meta.provenance.integrity}
          </p>
        </div>

        <p className="graph-help-note">
          Project Memory is advisory. Nothing here validates a record, completes a field, or
          authorises an export — those decisions belong to the official schema and the deterministic
          validators, never to this graph.
        </p>

        <p className="graph-help-placeholder">
          Command syntax — reserved. A deterministic command bar is planned for a later slice; its
          grammar and examples will be documented in this section.
        </p>
      </div>
    </div>
  );
}
