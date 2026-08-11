import './evidence.css';
import { sourceIcon } from './icons';
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

/**
 * A neutral chip + colored source-type icon + mono source_type label.
 *
 * Tolerates a source type this build does not know: the glyph falls back (see
 * `sourceIcon`) and the label still prints the stored string verbatim, so an
 * unrecognised kind is shown as itself rather than crashing the surface it is on.
 * This token is mounted on the record workbench field rows AND in the Evidence
 * sidecar detail, so the crash it used to cause had two blast radii, not one.
 */
export function SourceTypeToken({ sourceType }: { sourceType: SourceType }) {
  const Icon = sourceIcon(sourceType);
  const cls = SRC_CLASS[sourceType] ?? 'src-unknown';
  return (
    <span className={`src-token ${cls}`}>
      <Icon size={12} strokeWidth={2} aria-hidden="true" />
      {typeof sourceType === 'string' && sourceType ? sourceType : 'source type not recorded'}
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
