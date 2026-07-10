import './evidence.css';
import { SOURCE_ICON } from './icons';
import type { FieldEvidence, SourceType } from '../lib/types';

const SRC_CLASS: Record<SourceType, string> = {
  spreadsheet: 'src-spreadsheet',
  file_listing: 'src-filelisting',
  derivation: 'src-derivation',
  user_confirmation: 'src-userconf',
  document: 'src-filelisting',
  screenshot: 'src-filelisting',
  web_form: 'src-filelisting',
};

/** A neutral chip + colored source-type icon + mono source_type label. */
export function SourceTypeToken({ sourceType }: { sourceType: SourceType }) {
  const Icon = SOURCE_ICON[sourceType];
  return (
    <span className={`src-token ${SRC_CLASS[sourceType]}`}>
      <Icon size={12} strokeWidth={2} aria-hidden="true" />
      {sourceType}
    </span>
  );
}

/**
 * One evidence entry — the compact citation on S3 field rows. Source type is
 * icon + mono label; user_confirmation carries the human motif, distinct from
 * machine-extracted evidence. Never hidden behind a hover-only tooltip.
 */
export function EvidenceRow({ evidence }: { evidence: FieldEvidence }) {
  return (
    <div className="ev-row">
      <SourceTypeToken sourceType={evidence.source_type} />
      {evidence.source_type === 'derivation' && evidence.rule && (
        <span className="ev-rule">rule: {evidence.rule}</span>
      )}
      {evidence.source_type === 'user_confirmation' && (
        <span className="ev-userconf">confirmed by you{evidence.answer ? ` · ${evidence.answer}` : ''}</span>
      )}
      {evidence.source_file && <span className="ev-file">{evidence.source_file}</span>}
      {evidence.locator && evidence.source_type !== 'derivation' && (
        <span className="ev-locator">{evidence.locator}</span>
      )}
      {evidence.quote && <span className="ev-quote">"{evidence.quote}"</span>}
    </div>
  );
}
