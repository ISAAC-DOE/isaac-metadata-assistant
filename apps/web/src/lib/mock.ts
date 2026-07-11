/*
 * Synthetic SAMPLE data derived from the committed sample record + sidecar
 * (docs/samples/01JQZ0SYNTHXANESDEMO000000.{json,evidence.json}).
 *
 * S1/S2/S3/S4/S6 are wired to the live FastAPI backend (lib/api.ts) and must NOT
 * read this module. What remains here serves only the still-static S5 surface
 * (evidence trail + source preview). Every value traces to the committed
 * synthetic fixtures — nothing invented. A later task replaces these too.
 */

import type { EvidenceTrailEntry, SourcePreview } from './types';

export const DEMO_RECORD_ID = '01JQZ0SYNTHXANESDEMO000000';

// The sample record shown on the still-static S5 surface.
export const DEMO_SIDECAR_FILE = `${DEMO_RECORD_ID}.evidence.json`;

const FULL_SHA_PROCESSING =
  'c3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b345';
const FULL_SHA_MERGED =
  'b3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b234';

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

export const SIDECAR_ENTRY_SNIPPET = {
  source_type: 'user_confirmation',
  question: 'What is the sha256 of the processing notebook?',
  answer: FULL_SHA_PROCESSING,
  timestamp: '2099-03-05T21:00:00Z',
};
