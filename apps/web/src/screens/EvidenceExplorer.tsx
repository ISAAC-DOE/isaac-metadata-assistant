import './screens.css';
import { useState } from 'react';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { EvidenceTrailPanel } from '../components/EvidenceTrailPanel';
import { SourcePreview } from '../components/SourcePreview';
import { StatusBar } from '../components/StatusBar';
// S5 stays on committed synthetic sample data this slice; a later task wires it live.
import {
  DEMO_SIDECAR_FILE,
  EVIDENCE_DIRECT_TOTAL,
  SIDECAR_ENTRY_SNIPPET,
  SIDECAR_META,
  SOURCE_PROVENANCE,
  getEvidenceTrail,
  getSourcePreview,
} from '../lib/mock';

const RECORD_JSON = `{
  "asset_id": "processing_notebook",
  "content_role": "processing_script",
  "uri": "ssrl-archive://BL15-2/2099_run_000/notebooks/xanes_reduction_v2.ipynb",
  "media_type": "application/x-ipynb+json",
  "sha256": "c3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b345"
}`;

const SIDECAR_JSON = `"assets:processing_notebook": [
  { "source_type": "file_listing", "source_file": "raw_scan_listing.txt",
    "locator": "line 16, ssrl-archive://BL15-2/2099_run_000/notebooks/",
    "quote": "xanes_reduction_v2.ipynb" },
  { "source_type": "user_confirmation",
    "question": "What is the sha256 of the processing notebook?",
    "answer": "c3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b345",
    "timestamp": "2099-03-05T21:00:00Z" }
]`;

/**
 * S5 · Evidence & File Preview — "where did this come from?" answered in-app. The
 * Evidence Trail drives a live source preview with the cited line highlighted.
 * The sidecar is labeled an assistant convention throughout.
 */
export function EvidenceExplorer() {
  const entries = getEvidenceTrail();
  const preview = getSourcePreview();
  const [selectedKey, setSelectedKey] = useState('assets:processing_notebook');
  const selected = entries.find((e) => e.key === selectedKey) ?? entries[0];

  return (
    <AppShell
      variant="evidence"
      topBar={
        <TopBar
          variant="record"
          title="CuO / Cu K-edge XANES — evidence"
          filename={DEMO_SIDECAR_FILE}
        />
      }
      sidebar={
        <EvidenceTrailPanel
          entries={entries}
          directTotal={EVIDENCE_DIRECT_TOTAL}
          selectedKey={selectedKey}
          onSelect={setSelectedKey}
          meta={SIDECAR_META}
        />
      }
      statusBar={
        <StatusBar
          phase="Evidence Trail"
          phaseDot="idle"
          note="sidecar · assistant convention, not an official ISAAC standard · 26 direct paths counted in coverage"
        />
      }
      mainPad="none"
    >
      <SourcePreview
        entryTitle={selected.label}
        entryKey={selected.key}
        provenance={SOURCE_PROVENANCE}
        preview={preview}
        recordJson={RECORD_JSON}
        sidecarJson={SIDECAR_JSON}
        sidecarEntry={SIDECAR_ENTRY_SNIPPET}
      />
    </AppShell>
  );
}
