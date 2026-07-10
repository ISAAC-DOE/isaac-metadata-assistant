/*
 * Synthetic SAMPLE data derived from the committed sample record + sidecar
 * (docs/samples/01JQZ0SYNTHXANESDEMO000000.{json,evidence.json}).
 *
 * S1/S2/S3 are wired to the live FastAPI backend (lib/api.ts) and must NOT read
 * this module. What remains here serves only the still-static surfaces:
 * S4 (pending blockers + completion answers), S5 (evidence trail + source
 * preview), S6 (signals + artifacts + graph status), and their shared demo
 * constants. Every value traces to the committed synthetic fixtures — nothing
 * invented. A later task replaces these with live endpoints too.
 */

import type {
  Artifact,
  CompletionAnswer,
  EvidenceTrailEntry,
  GraphStatus,
  PendingBlocker,
  Signals,
  SourcePreview,
} from './types';

export const DEMO_RECORD_ID = '01JQZ0SYNTHXANESDEMO000000';

// The sample record shown on the still-static S4–S6 surfaces.
export const DEMO_TITLE = 'CuO / Cu K-edge XANES — 2099 spring campaign';
export const DEMO_RECORD_FILE = `${DEMO_RECORD_ID}.json`;
export const DEMO_SIDECAR_FILE = `${DEMO_RECORD_ID}.evidence.json`;

const FULL_SHA_PROCESSING =
  'c3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b345';
const FULL_SHA_MERGED =
  'b3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b234';

// --- S4 pending blockers (verbatim order: edge · series · 2 sha256 · descriptor)

export function getPendingBlockers(): PendingBlocker[] {
  return [
    {
      id: 'edge',
      kind: 'edge',
      label: 'Absorption Edge',
      path: 'implicit · edge',
      question: 'What is the absorption edge (e.g. K, L3)?',
      context:
        'This confirms the absorption edge for the scan. Proposed K from the Cu K-edge technique. The system will never generate this value for you.',
      inputType: 'enum',
      enumOptions: ['K', 'L1', 'L2', 'L3', 'M1'],
      demo_answer: { value: 'K', label: 'Demo answer (synthetic)' },
      suggestion: {
        text:
          'The incident-energy window 8970–9000 eV recorded in Configurations is consistent with a Cu K-edge — confirm K to store it as your evidence.',
        answeredFrom: 'files',
        locator: 'mock_campaign.csv · Configurations',
      },
    },
    {
      id: 'series',
      kind: 'series',
      label: 'Reduced-Spectrum Pointer',
      path: 'measurement.series',
      question: 'Which reduced spectrum should this record point to?',
      context:
        'This is the reduced spectrum the record cites. The system will never generate this value for you.',
      inputType: 'enum',
      enumOptions: ['CuO2_merged.xdi'],
      demo_answer: { value: 'CuO2_merged.xdi', label: 'Demo answer (synthetic)' },
      suggestion: {
        text:
          'The archive listing shows CuO2_merged.xdi in the reduced/ directory — that is the reduced spectrum this question is about.',
        answeredFrom: 'files',
        locator: 'raw_scan_listing.txt · L27',
      },
    },
    {
      id: 'assets.processing_notebook.sha256',
      kind: 'asset',
      label: 'Processing Notebook',
      path: 'assets.processing_notebook.sha256',
      question: 'What is the sha256 of the processing notebook?',
      context:
        'An asset can only be cited if it carries a hash. The file is …/xanes_reduction_v2.ipynb. The system will never generate this value for you.',
      inputType: 'hash',
      demo_answer: { value: FULL_SHA_PROCESSING, label: 'Demo answer (synthetic)' },
      suggestion: {
        text:
          "The archive listing shows xanes_reduction_v2.ipynb — that's the file this question is about. I can't produce its hash; paste it and I'll store your paste as user_confirmation evidence.",
        answeredFrom: 'files',
        locator: 'raw_scan_listing.txt · L16',
      },
    },
    {
      id: 'assets.merged_spectrum.sha256',
      kind: 'asset',
      label: 'Merged Spectrum',
      path: 'assets.merged_spectrum.sha256',
      question: 'What is the sha256 of the merged spectrum file?',
      context:
        'An asset can only be cited if it carries a hash. The file is …/CuO2_merged.xdi. The system will never generate this value for you.',
      inputType: 'hash',
      demo_answer: { value: FULL_SHA_MERGED, label: 'Demo answer (synthetic)' },
      suggestion: {
        text:
          "The archive listing shows CuO2_merged.xdi — that's the file this question is about. I can't produce its hash; paste it and I'll store your paste as user_confirmation evidence.",
        answeredFrom: 'files',
        locator: 'raw_scan_listing.txt · L27',
      },
    },
    {
      id: 'descriptors.xanes_inflection_point_energy',
      kind: 'descriptor',
      label: 'XANES Inflection-Point Energy',
      path: 'descriptors.xanes_inflection_point_energy',
      question: 'What is the XANES inflection-point energy and its uncertainty?',
      context:
        'This is a scientific descriptor measured from the spectrum. Enter the value, its unit, and σ. The system will never generate this value for you.',
      inputType: 'number',
      unit: 'eV',
      demo_answer: { value: '9001.2', label: 'Demo answer (synthetic)' },
    },
  ];
}

// S4 completion snapshot: edge + series answered, processing-notebook current.
export function getCompletionAnswers(): CompletionAnswer[] {
  return [
    { id: 'edge', label: 'Absorption Edge', storedValue: 'K', confirmed: true },
    {
      id: 'series',
      label: 'Reduced-Spectrum Pointer',
      storedValue: 'CuO2_merged.xdi',
      confirmed: true,
    },
  ];
}

export const COMPLETION_CURRENT_INDEX = 2; // 0-based → Question 3 of 5

// --- S5 evidence trail ------------------------------------------------

export const SIDECAR_META = {
  record_id: DEMO_RECORD_ID,
  schema_version: '1.05',
  generated_utc: '2026-07-06T23:05:48Z',
};

export function getEvidenceTrail(): EvidenceTrailEntry[] {
  return [
    {
      key: 'system.facility.facility_name',
      label: 'system.facility.facility_name',
      value: 'SSRL',
      status: 'verified',
      sourceTypes: ['spreadsheet'],
      namespaced: false,
      resolved: true,
      evidence: [
        {
          source_type: 'spreadsheet',
          source_file: 'mock_campaign.csv',
          locator: "Sheet 'Campaign Info', field=facility_name",
          quote: 'SSRL',
        },
      ],
    },
    {
      key: 'system.facility.beamline',
      label: 'system.facility.beamline',
      value: '15-2',
      status: 'verified',
      sourceTypes: ['spreadsheet'],
      namespaced: false,
      resolved: true,
      evidence: [
        {
          source_type: 'spreadsheet',
          source_file: 'mock_campaign.csv',
          locator: "Sheet 'Campaign Info', field=beamline",
          quote: '15-2',
        },
      ],
    },
    {
      key: 'sample.material.formula',
      label: 'sample.material.formula',
      value: 'CuO2',
      status: 'verified',
      sourceTypes: ['spreadsheet'],
      namespaced: false,
      resolved: true,
      evidence: [
        {
          source_type: 'spreadsheet',
          source_file: 'mock_campaign.csv',
          locator: "Sheet 'Sample', field=formula",
          quote: 'CuO2',
        },
      ],
    },
    {
      key: 'system.technique',
      label: 'system.technique',
      value: 'HERFD-XAS',
      status: 'verified',
      sourceTypes: ['spreadsheet'],
      namespaced: false,
      resolved: true,
      evidence: [
        {
          source_type: 'spreadsheet',
          source_file: 'mock_campaign.csv',
          locator: "Sheet 'Campaign Info', field=technique",
          quote: 'HERFD-XAS',
        },
      ],
    },
    {
      key: 'system.domain',
      label: 'system.domain',
      value: 'experimental',
      status: 'inferred',
      sourceTypes: ['derivation'],
      namespaced: false,
      resolved: true,
      evidence: [
        {
          source_type: 'derivation',
          rule:
            'system.domain = experimental for a facility-source record (meta.source_type=facility ⇒ physical experiment)',
        },
      ],
    },
    {
      key: 'assets:processing_notebook',
      label: 'Processing Notebook',
      value: FULL_SHA_PROCESSING,
      status: 'verified',
      sourceTypes: ['file_listing', 'user_confirmation'],
      namespaced: true,
      resolved: true,
      evidence: [
        {
          source_type: 'file_listing',
          source_file: 'raw_scan_listing.txt',
          locator: 'line 16, ssrl-archive://BL15-2/2099_run_000/notebooks/',
          quote: 'xanes_reduction_v2.ipynb',
        },
        {
          source_type: 'user_confirmation',
          question:
            'What is the sha256 of ssrl-archive://BL15-2/2099_run_000/notebooks/xanes_reduction_v2.ipynb?',
          answer: FULL_SHA_PROCESSING,
          timestamp: '2099-03-05T21:00:00Z',
        },
      ],
    },
    {
      key: 'assets:reduced_spectrum',
      label: 'Merged Spectrum',
      value: FULL_SHA_MERGED,
      status: 'verified',
      sourceTypes: ['file_listing', 'user_confirmation'],
      namespaced: true,
      resolved: true,
      evidence: [
        {
          source_type: 'file_listing',
          source_file: 'raw_scan_listing.txt',
          locator: 'line 27, ssrl-archive://BL15-2/2099_run_000/reduced/',
          quote: 'CuO2_merged.xdi',
        },
        {
          source_type: 'user_confirmation',
          question:
            'What is the sha256 of ssrl-archive://BL15-2/2099_run_000/reduced/CuO2_merged.xdi?',
          answer: FULL_SHA_MERGED,
          timestamp: '2099-03-05T21:00:00Z',
        },
      ],
    },
    {
      key: 'descriptors:xanes_inflection_point_energy',
      label: 'Inflection-Point Energy',
      value: '9001.2',
      status: 'verified',
      sourceTypes: ['user_confirmation'],
      namespaced: true,
      resolved: true,
      evidence: [
        {
          source_type: 'user_confirmation',
          question: 'Descriptor value + uncertainty?',
          answer: '9001.2',
          timestamp: '2099-03-05T21:00:00Z',
        },
      ],
    },
    {
      key: 'implicit:edge',
      label: 'Absorption Edge',
      value: 'K',
      status: 'verified',
      sourceTypes: ['derivation', 'user_confirmation'],
      namespaced: true,
      resolved: true,
      evidence: [
        {
          source_type: 'derivation',
          rule:
            'edge requires scientific confirmation; incident-energy window 8970–9000 eV recorded from Configurations',
        },
        {
          source_type: 'user_confirmation',
          question: 'What is the absorption edge (e.g. K, L3)?',
          answer: 'K',
          timestamp: '2099-03-05T21:00:00Z',
        },
      ],
    },
  ];
}

export const EVIDENCE_DIRECT_TOTAL = 26;

// Read-only source preview for the selected (assets:processing_notebook) entry.
export function getSourcePreview(): SourcePreview {
  return {
    file: 'raw_scan_listing.txt',
    citedLine: 16,
    lines: [
      { n: 13, text: '2099-03-15 09:18 1.1M raw/scan_0044.dat' },
      { n: 14, text: '2099-03-15 09:20 1.1M raw/scan_0045.dat' },
      { n: 15, text: '2099-03-15 09:21 240K notebooks/' },
      { n: 16, text: '2099-03-15 09:22  88K notebooks/xanes_reduction_v2.ipynb' },
      { n: 17, text: '2099-03-15 09:40 240K reduced/CuO2_merged.xdi' },
      { n: 18, text: '2099-03-15 09:41 4.0K raw/ (directory)' },
    ],
  };
}

export const SOURCE_PROVENANCE =
  'Identified in the archive listing (file_listing), and its hash was supplied by you (user_confirmation). Two sources are preserved side by side — the machine lead and the human confirmation.';

// --- S6 signals + artifacts -------------------------------------------

export function getSignals(): Signals {
  return {
    validation: {
      verdict: 'pass',
      ok: true,
      schemaVersion: 'v1.05',
      exitCode: 0,
      errors: [],
    },
    coverage: { resolved: 26, total: 26, dangling: [] },
    advisory: {
      advisory: true,
      gating: false,
      warnings: [
        {
          code: 'NO_LINKS',
          where: 'record.links',
          message: 'no relationships declared',
        },
      ],
    },
  };
}

export function getArtifacts(): Artifact[] {
  return [
    {
      kind: 'record',
      path: `records/${DEMO_RECORD_ID}.json`,
      verdict: 'pass',
    },
    {
      kind: 'sidecar',
      path: `records/${DEMO_RECORD_ID}.evidence.json`,
      pathCount: 26,
    },
  ];
}

export const SIDECAR_ENTRY_SNIPPET = {
  source_type: 'user_confirmation',
  question: 'What is the sha256 of the processing notebook?',
  answer: FULL_SHA_PROCESSING,
  timestamp: '2099-03-05T21:00:00Z',
};

// --- memory (S6 still-static freshness dot) -----------------------------

export function getGraphStatus(): GraphStatus {
  return { status: 'fresh', plane: 'memory' };
}
