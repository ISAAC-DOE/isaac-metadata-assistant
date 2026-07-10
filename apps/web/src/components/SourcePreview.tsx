import './evidence.css';
import { useState } from 'react';
import { List, Copy } from './icons';
import { LABELS } from '../lib/labels';
import type { SourcePreview as SourcePreviewData } from '../lib/types';

type Tab = 'source' | 'record' | 'sidecar';

interface SourcePreviewProps {
  entryTitle: string;
  entryKey: string;
  provenance: string;
  preview: SourcePreviewData;
  recordJson: string;
  sidecarJson: string;
  sidecarEntry: {
    source_type: string;
    question: string;
    answer: string; // full sha256, never silently truncated
    timestamp: string;
  };
}

/**
 * Read-only viewer: the cited line highlighted in the REAL source, plus record
 * and sidecar JSON tabs. Long hashes live in a horizontally-scrollable mono
 * field with a copy affordance — never silently truncated; the page body never
 * scrolls sideways.
 */
export function SourcePreview({
  entryTitle,
  entryKey,
  provenance,
  preview,
  recordJson,
  sidecarJson,
  sidecarEntry,
}: SourcePreviewProps) {
  const [tab, setTab] = useState<Tab>('source');

  return (
    <section className="preview" aria-label="Source preview (read-only)">
      <h2 className="preview-prov-title">
        {entryTitle}
        <span className="preview-prov-key">{entryKey}</span>
      </h2>
      <p className="preview-prov-text">{provenance}</p>

      <div className="tabs" role="tablist" aria-label="Preview source">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'source'}
          className={`tab${tab === 'source' ? ' active' : ''}`}
          onClick={() => setTab('source')}
        >
          {LABELS.tabSource}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'record'}
          className={`tab${tab === 'record' ? ' active' : ''}`}
          onClick={() => setTab('record')}
        >
          {LABELS.tabRecord}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'sidecar'}
          className={`tab${tab === 'sidecar' ? ' active' : ''}`}
          onClick={() => setTab('sidecar')}
        >
          {LABELS.tabSidecar}
        </button>
      </div>

      {tab === 'source' && (
        <div className="preview-file">
          <div className="preview-file-head">
            <span className="preview-file-name">
              <List size={13} strokeWidth={2} aria-hidden="true" />
              {preview.file}
            </span>
            <span className="preview-readonly">{LABELS.readOnly}</span>
          </div>
          <div className="preview-lines scroll-x">
            {preview.lines.map((line) => {
              const cited = line.n === preview.citedLine;
              return (
                <div key={line.n} className={`preview-line${cited ? ' cited' : ''}`}>
                  <span className="ln">{line.n}</span>
                  <span>{line.text}</span>
                  {cited && <span className="cited-tag">{LABELS.cited}</span>}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {tab === 'record' && <pre className="preview-json scroll-x">{recordJson}</pre>}
      {tab === 'sidecar' && <pre className="preview-json scroll-x">{sidecarJson}</pre>}

      <div className="sidecar-entry">
        <div className="sidecar-entry-head">
          Sidecar Entry
          <span className="sidecar-entry-tag mono">{sidecarEntry.source_type} · sha256</span>
        </div>
        <div className="sidecar-obj">
          <div>
            <span className="k">"source_type"</span>: <span className="s">"{sidecarEntry.source_type}"</span>,
          </div>
          <div>
            <span className="k">"question"</span>: <span className="s">"{sidecarEntry.question}"</span>,
          </div>
          <div>
            <span className="k">"answer"</span>:
          </div>
          <div className="hash-field">
            <span className="hash mono">"{sidecarEntry.answer}"</span>
            <button
              type="button"
              className="copy-btn"
              aria-label="Copy sha256"
              onClick={() => {
                void navigator.clipboard?.writeText(sidecarEntry.answer);
              }}
            >
              <Copy size={13} strokeWidth={2} aria-hidden="true" />
            </button>
          </div>
          <div>
            <span className="k">"timestamp"</span>: <span className="s">"{sidecarEntry.timestamp}"</span>
          </div>
        </div>
      </div>
    </section>
  );
}
