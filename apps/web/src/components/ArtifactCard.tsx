import './artifact.css';
import { FileText, FileJson, Download } from './icons';
import { StatusChip } from './StatusChip';
import { LABELS } from '../lib/labels';
import type { Artifact } from '../lib/types';
import type { MouseEvent } from 'react';

interface ArtifactCardProps {
  artifact: Artifact;
  // Receives the click event so the caller can capture e.currentTarget as the
  // focus-restore target — a mouse click doesn't reliably focus the button
  // first (macOS Safari/Firefox), so document.activeElement alone isn't safe.
  onView?: (e: MouseEvent<HTMLButtonElement>) => void;
  onDownload?: () => void;
}

/**
 * One export artifact. The record and the sidecar are different kinds of thing —
 * two separate cards, never blended. The sidecar is clearly secondary and
 * clearly non-official; it never carries a verdict chip.
 */
export function ArtifactCard({ artifact, onView, onDownload }: ArtifactCardProps) {
  const isRecord = artifact.kind === 'record';
  return (
    <section
      className="card artifact"
      aria-label={isRecord ? LABELS.officialRecord : LABELS.evidenceTrail}
    >
      <div className="artifact-head">
        <span className={`artifact-icon ${artifact.kind}`} aria-hidden="true">
          {isRecord ? <FileText size={18} strokeWidth={2} /> : <FileJson size={18} strokeWidth={2} />}
        </span>
        <div>
          <div className="artifact-title">
            {isRecord ? LABELS.officialRecord : LABELS.evidenceTrail}
          </div>
          <div className="artifact-sub">
            {isRecord ? 'schema-clean · ISAAC v1.05' : LABELS.sidecarNotOfficial}
          </div>
        </div>
        {isRecord && artifact.verdict === 'pass' ? (
          <span className="artifact-badge">
            <StatusChip kind="pass" />
          </span>
        ) : (
          artifact.pathCount !== undefined && (
            <span className="artifact-pathcount">{artifact.pathCount} paths</span>
          )
        )}
      </div>

      <div className="artifact-path">{artifact.path}</div>

      <div className="artifact-actions">
        <button
          type="button"
          className={`btn ${isRecord ? 'btn-primary' : 'btn-secondary'}`}
          onClick={onDownload}
          disabled={!onDownload}
        >
          <Download size={14} strokeWidth={2} aria-hidden="true" />
          {LABELS.actionDownload}
        </button>
        <button type="button" className="btn btn-secondary" onClick={onView} disabled={!onView}>
          {isRecord ? LABELS.actionViewJson : LABELS.actionView}
        </button>
      </div>
    </section>
  );
}
