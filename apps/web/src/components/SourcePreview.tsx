import './evidence.css';
import { useState } from 'react';
import { List, Copy, Check } from './icons';
import { SourceTypeToken } from './EvidenceRow';
import { LABELS } from '../lib/labels';
import type { ApiSourcePreview, EvidenceTrailEntry, FieldEvidence } from '../lib/types';

type Tab = 'source' | 'record' | 'sidecar';

interface SourcePreviewProps {
  entry: EvidenceTrailEntry;
  provenance: string;
  /** The source fixture the entry cites, or null when it cites no file. */
  preview: ApiSourcePreview | null;
  /** 1-based line numbers to highlight for THIS entry (empty for field-cited). */
  citedLines: number[];
  /** Pretty-printed record / sidecar JSON, or null before export. */
  recordJson: string | null;
  sidecarJson: string | null;
}

/** A sha256 / long hex value — copyable, never silently truncated. */
function isHash(value: unknown): value is string {
  return typeof value === 'string' && /^[0-9a-f]{32,}$/i.test(value);
}

/**
 * Read-only viewer: the cited line highlighted in the REAL source, plus the
 * record and sidecar JSON. Full hashes live in a horizontally-scrollable mono
 * field with a copy affordance — never silently truncated; the page body never
 * scrolls sideways. Honest empty states before export / when the entry cites no
 * file.
 */
export function SourcePreview({
  entry,
  provenance,
  preview,
  citedLines,
  recordJson,
  sidecarJson,
}: SourcePreviewProps) {
  const [tab, setTab] = useState<Tab>('source');
  const cited = new Set(citedLines);

  return (
    <section className="preview" aria-label="Source preview (read-only)">
      <h2 className="preview-prov-title">
        {entry.label}
        <span className="preview-prov-key">{entry.key}</span>
      </h2>
      <p className="preview-prov-text">{provenance}</p>

      <div className="tabs" role="tablist" aria-label="Preview source">
        <PreviewTab id="source" tab={tab} setTab={setTab} label={LABELS.tabSource} />
        <PreviewTab id="record" tab={tab} setTab={setTab} label={LABELS.tabRecord} />
        <PreviewTab id="sidecar" tab={tab} setTab={setTab} label={LABELS.tabSidecar} />
      </div>

      {tab === 'source' &&
        (preview ? (
          <div className="preview-file">
            <div className="preview-file-head">
              <span className="preview-file-name">
                <List size={13} strokeWidth={2} aria-hidden="true" />
                {preview.name}
              </span>
              <span className="preview-readonly">{LABELS.readOnly}</span>
            </div>
            <div className="preview-lines scroll-x">
              {preview.lines.map((line) => {
                const isCited = cited.has(line.n);
                return (
                  <div key={line.n} className={`preview-line${isCited ? ' cited' : ''}`}>
                    <span className="ln">{line.n}</span>
                    <span>{line.text}</span>
                    {isCited && <span className="cited-tag">{LABELS.cited}</span>}
                  </div>
                );
              })}
            </div>
          </div>
        ) : (
          <p className="preview-empty" role="note">
            This entry has no file-level source — it was confirmed by you or derived
            by a documented rule. See the sidecar entry below for its provenance.
          </p>
        ))}

      {tab === 'record' &&
        (recordJson ? (
          <pre className="preview-json scroll-x">{recordJson}</pre>
        ) : (
          <p className="preview-empty" role="note">
            Not exported yet — the official ISAAC record is written on export.
          </p>
        ))}

      {tab === 'sidecar' &&
        (sidecarJson ? (
          <pre className="preview-json scroll-x">{sidecarJson}</pre>
        ) : (
          <p className="preview-empty" role="note">
            Not exported yet — the evidence sidecar is written on export. The draft
            evidence below is what it will preserve.
          </p>
        ))}

      <SidecarEntryDetails entry={entry} />
    </section>
  );
}

function PreviewTab({
  id,
  tab,
  setTab,
  label,
}: {
  id: Tab;
  tab: Tab;
  setTab: (t: Tab) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={tab === id}
      className={`tab${tab === id ? ' active' : ''}`}
      onClick={() => setTab(id)}
    >
      {label}
    </button>
  );
}

/**
 * The raw sidecar entry for the selected field, rendered faithfully. Any sha256 /
 * long-hex value (the entry value, or a user_confirmation answer) gets a
 * horizontally-scrollable mono field + copy button. The sidecar is labeled an
 * assistant convention, never an official ISAAC standard.
 */
function SidecarEntryDetails({ entry }: { entry: EvidenceTrailEntry }) {
  return (
    <div className="sidecar-entry">
      <div className="sidecar-entry-head">
        Sidecar Entry
        <span className="sidecar-entry-tag mono">{entry.key}</span>
      </div>
      <p className="sidecar-convention" role="note">
        {LABELS.sidecarConvention}
      </p>

      {isHash(entry.value) && <HashField k="value" value={entry.value} />}

      <div className="sidecar-obj">
        {entry.evidence.length === 0 && <div className="sidecar-none">No citations recorded.</div>}
        {entry.evidence.map((ev, i) => (
          <EvidenceObject key={i} ev={ev} />
        ))}
      </div>
    </div>
  );
}

function EvidenceObject({ ev }: { ev: FieldEvidence }) {
  return (
    <div className="sidecar-ev">
      <SourceTypeToken sourceType={ev.source_type} />
      {ev.source_file && <KV k="source_file" v={ev.source_file} />}
      {ev.locator && <KV k="locator" v={ev.locator} />}
      {ev.quote && <KV k="quote" v={`"${ev.quote}"`} />}
      {ev.question && <KV k="question" v={ev.question} wrap />}
      {ev.answer &&
        (isHash(ev.answer) ? (
          <HashField k="answer" value={ev.answer} />
        ) : (
          <KV k="answer" v={ev.answer} />
        ))}
      {ev.timestamp && <KV k="timestamp" v={ev.timestamp} />}
      {ev.rule && <KV k="rule" v={ev.rule} wrap />}
    </div>
  );
}

function KV({ k, v, wrap }: { k: string; v: string; wrap?: boolean }) {
  return (
    <div className={wrap ? 'sidecar-kv wrap' : 'sidecar-kv'}>
      <span className="k">"{k}"</span>: <span className="s">{wrap ? v : `"${v}"`}</span>
    </div>
  );
}

/** A copyable full hash — mono, horizontally scrollable, never truncated. */
function HashField({ k, value }: { k: string; value: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void navigator.clipboard?.writeText(value);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="sidecar-kv">
      <span className="k">"{k}"</span>:
      <div className="hash-field">
        <span className="hash mono">"{value}"</span>
        <button type="button" className="copy-btn" aria-label="Copy sha256" onClick={copy}>
          {copied ? (
            <Check size={13} strokeWidth={2.4} aria-hidden="true" />
          ) : (
            <Copy size={13} strokeWidth={2} aria-hidden="true" />
          )}
        </button>
      </div>
    </div>
  );
}
