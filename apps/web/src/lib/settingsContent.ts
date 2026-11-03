/**
 * Settings page content — the single source for the copy the Settings surface
 * renders.
 *
 * 2026-11-02 (owner's direction: no standing disclaimers). The Privacy &
 * Governance tab and its twelve concept cards, the Overview "Data Safety" card,
 * the governance-policy paragraphs and the API-key "what would have to exist"
 * lists were retired. What a reader needs to know about their data is now ONE
 * compact Data card on Overview (`dataRows`), written from what the running app
 * reports, in plain rows with no caveats. Nothing here may imply that uploads
 * are accepted, the portal or a model is connected, or real data is shown —
 * `db-recon-truthfulness`, `upload-claim-parity`, `hosted-truthfulness` and
 * `assistant-model-claim-parity` sweep every string in this file for that.
 */

/** The `GET /api/about` values the copy is allowed to depend on. */
export interface SettingsFacts {
  dataRegime: string;
  /**
   * Where this deployment stores EXPERIMENT RECORDS: `durable`, `ephemeral` or
   * `unavailable`. It is `GET /api/health`'s `experiment_storage.state`, served
   * by `/api/about` so the two cannot disagree — see the header note. Typed as
   * `string` on purpose: an unrecognised value must reach the copy and be NAMED,
   * not narrowed away at the type level into a branch that would then assert
   * something the backend never said.
   */
  persistence: string;
  recordSchemaVersion: string;
}

/** Structural adapter so this module needs no import from `lib/types`. */
export function settingsFactsFrom(about: {
  data_regime: string;
  persistence: string;
  record_schema_version: string;
}): SettingsFacts {
  return {
    dataRegime: about.data_regime,
    persistence: about.persistence,
    recordSchemaVersion: about.record_schema_version,
  };
}

/**
 * THE DATA CARD (Overview): at most four plain rows — where experiment records
 * are stored, what an export writes, how a walkthrough is kept, and what the
 * browser keeps. Each row is written from the reported `persistence`; an
 * unrecognised value is NAMED rather than narrowed into a branch that would
 * assert something the backend never said.
 */
export interface SettingsDataRow {
  label: string;
  text: string;
}

/**
 * EVERYTHING THIS APP KEEPS IN THE BROWSER, by storage key (review 2026-11-02,
 * Important 2: the row named two of seven, leaving out a name the reader types).
 * `settings-page.test.tsx` scans `src` for every `isaac.*` key handed to
 * `localStorage`/`sessionStorage` and fails when one is missing here, so a new key
 * cannot ship without this row saying so.
 */
export const BROWSER_STORAGE_KEYS: readonly { key: string; store: 'local' | 'session'; what: string }[] = [
  { key: 'isaac.tutorial.v1', store: 'local', what: 'whether you finished or dismissed the walkthrough' },
  { key: 'isaac.tutorial.session.v1', store: 'session', what: 'the walkthrough step this tab is on' },
  { key: 'isaac.record-last-view.v1', store: 'local', what: 'the view you last opened on up to 50 records' },
  { key: 'isaac.assistant-rail-collapsed', store: 'local', what: 'whether the Assistant panel is collapsed' },
  { key: 'isaac.transcriptCaptureGuidance.v1', store: 'local', what: 'whether the capture guidance is hidden' },
  { key: 'isaac.localImports.by', store: 'local', what: 'the name you enter for Local Imports' },
  { key: 'isaac.assistant.session.', store: 'session', what: 'this tab’s Assistant conversations' },
];

/** The Data card's "In Your Browser" row: one plain sentence over every key above. */
export const BROWSER_STORAGE_SENTENCE =
  'Your walkthrough progress, the view you last opened on up to 50 records, whether the ' +
  'Assistant panel is collapsed and the capture guidance hidden, the name you enter for ' +
  'Local Imports, and this tab’s Assistant conversations.';

export function dataRows(facts: SettingsFacts): SettingsDataRow[] {
  const { persistence } = facts;
  const records =
    persistence === 'durable'
      ? "Stored in this deployment's database, so they survive a restart."
      : persistence === 'ephemeral'
        ? 'Stored as files on this server, for this deployment only.'
        : persistence === 'unavailable'
          ? 'A database is configured for them, and the server reports that records are not reaching it.'
          : `The server reports their storage as “${persistence}”.`;
  return [
    { label: 'Experiment Records', text: records },
    {
      label: 'Exports',
      /* Exported files live in the server's working directory, never in the
         database (`GET /api/about`: "not held in a database, whatever `persistence`
         reports"). On a durable deployment that is said, so the Records row beside
         it ("survive a restart") is not read as covering them too. A download goes
         to the reader's computer, not to "the browser". */
      text:
        persistence === 'durable'
          ? 'An export writes the official record and its evidence sidecar as files on the server, outside the database. Download a copy to keep it.'
          : 'An export writes the official record and its evidence sidecar on the server. A download saves a copy to your computer.',
    },
    {
      label: 'Walkthroughs',
      text: 'Each runs in its own temporary workspace, discarded when it ends or expires.',
    },
    { label: 'In Your Browser', text: BROWSER_STORAGE_SENTENCE },
  ];
}

/** This Build's info panel: the no-guessing principle. */
export const NO_GUESSING = {
  label: 'No-Guessing',
  text: 'Every finalized field carries either cited evidence or an explicit user confirmation — nothing scientific is invented.',
} as const;

/** The `GET /api/about` response keys behind the identity labels above. */
export const ABOUT_RESPONSE_FIELDS: readonly string[] = [
  'app_version',
  'build_commit',
  'record_schema_version',
  'runtime_mode',
  'data_regime',
  'persistence',
  'core',
];

/** The endpoints every value on this screen comes from. */
export const SETTINGS_SOURCE_ENDPOINTS: readonly string[] = ['GET /api/about', 'GET /api/openapi'];

/** Repository documentation references — inert names, never fetched or rendered. */
export const REPO_DOCS: readonly string[] = [
  'CLAUDE.md',
  'AGENTS.md',
  'README.md',
  'docs/mentor-brief.md',
  'schema/PROVENANCE.md',
];

export const REPO_DOCS_CAPTION = 'Tracked in the repository, not served as pages by this app.';

// --- API Access / Endpoint Explorer canonical copy (P36V-1 slice 13) ---------

/**
 * API Access (Integrations): ONE plain state line, and the functional legend for
 * the Endpoint Explorer's Auth column. ~~`statusHeading` "No API Keys in This
 * Build", `statusBody`, `credentialLine`, `requirementsNote`, `requirementsBoundary`,
 * `connectPrerequisite`, `connectMcpPointer`, `API_ACCESS_ROWS`,
 * `API_KEY_REQUIREMENTS`, `OVERVIEW_SAFETY_ROWS`, `GOVERNANCE_POLICY`,
 * `PRIVACY_QUESTIONS` and `syntheticWorkspaceRow`~~ — retired 2026-11-02 with the
 * Privacy & Governance tab (owner's direction: no standing disclaimers).
 */
export const API_ACCESS_COPY = {
  stateLine:
    'API keys are not set up on this server. An administrator configures access in the deployment settings.',
  authMarkerLegend:
    "Auth reports whether the contract documents a 401 for an operation. Where a deployment enables authentication those operations need the deployment's credential, and the liveness check is the one that stays reachable without it.",
} as const;

/**
 * Widget titles, one-line descriptions and the few structural labels. Titles
 * are Title Case; descriptions are one sentence and name a TOPIC — none of them
 * is the canonical statement of a fact, which is what lets a description sit
 * above the rows that ARE.
 */
export const SETTINGS_WIDGET_COPY = {
  dataTitle: 'Data',

  buildTitle: 'This Build',
  buildRuntime: 'Runtime',
  provenanceLive: 'read per request',
  provenanceFixed: 'fixed for this build',
  provenanceLegend:
    'A value marked with the clock is read per request from the running deployment; an unmarked one is fixed for this build.',

  walkthroughNotFinished: 'Not Finished',
  walkthroughFinished: 'Finished',

  apiTitle: 'API Access',
  apiSetup: 'Setup and Reference',

  relatedTitle: 'Related Tools',
  explorerTitle: 'Endpoint Explorer',
  explorerSub:
    'Every operation this build exposes, read from the OpenAPI document the app generates for itself.',
  memoryTitle: 'Project Memory',
  memorySub: "A snapshot of this project's own source and documentation.",
  validatorTitle: 'Validator',
  validatorSub: 'Check a JSON record against the official schema without adding it to My Experiments.',
  validatorOpen: 'Open the Validator',
  schemaTitle: 'Schema Reference',
  schemaSub: 'The canonical official ISAAC schema.',
  technicalTitle: 'Technical Details',
} as const;
