/**
 * Settings page content — the SINGLE source for every claim the Settings
 * surface makes (P36V PR3 slice B).
 *
 * Before this module the same six claims were authored two or three times
 * across the Overview / Data & Privacy / About tabs — twice character-for-
 * character (the data-regime and persistence paragraphs, via two local
 * helpers) and four more times as paraphrases that could drift apart with the
 * next edit. Every canonical definition now lives here exactly once, and each
 * tab renders it from here:
 *
 *   · `summary` — ONE line, rendered only by Overview. A pointer, never the
 *     definition. Intentionally shorter and differently worded than `detail`,
 *     which is why the two are modelled as separate fields rather than one
 *     string rendered in two places.
 *   · `detail`  — the canonical definition, rendered only by Data & Privacy.
 *   · `more`    — a secondary edge case behind a native disclosure, also
 *     Data & Privacy only. Only used where hiding the sentence cannot make the
 *     visible copy overstate what the code does (see the honesty notes below).
 *
 * HONESTY CONSTRAINTS these strings exist to protect — they describe what the
 * CODE does, not what the governance policy asks for:
 *
 *  - the app gates on runtime MODE, never on the CONTENTS of what it is handed.
 *    There is no real-vs-synthetic detector anywhere in the backend, so nothing
 *    here may imply that real data is recognised and turned away. That caveat
 *    stays in the always-visible `detail`, never behind a disclosure.
 *  - `persistence: "ephemeral"` is a fixed literal about deployment intent, not
 *    a process-lifetime guarantee. Workspace state is written to files under a
 *    server-side working directory, so it outlives the process; only the
 *    deployment's temporary storage bounds it.
 *  - the app cannot tell whether the deployment restricts access. The optional
 *    shared key the backend can require is configured outside the browser, so
 *    the client may state the uncertainty but never a status.
 *  - infrastructure topology is never named. `apps/api/tests/
 *    test_about_and_openapi.py` withholds a fixed list of substrings from
 *    `GET /api/about`, and `src/__tests__/settings-page.test.tsx` re-asserts it
 *    on the rendered text of every tab. Describe the access boundary
 *    provider-neutrally.
 *
 * Any value-dependent sentence is built from the facts the backend actually
 * reported. When the backend reports something the copy does not cover, the
 * fallback NAMES the reported value instead of repeating a claim the API
 * contradicts.
 */

/** The `GET /api/about` values the copy is allowed to depend on. */
export interface SettingsFacts {
  dataRegime: string;
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

export type SettingsConceptId =
  | 'synthetic-data-only'
  | 'no-real-experiment-data'
  | 'what-is-stored'
  | 'what-resets'
  | 'no-telemetry'
  | 'no-external-model-calls'
  | 'project-memory-boundary'
  | 'record-truth-boundary'
  | 'authentication-boundary';

export interface SettingsDisclosure {
  /** Title Case — it is the disclosure's own accessible name. */
  label: string;
  text: string;
}

export interface SettingsConcept {
  id: SettingsConceptId;
  /** Title Case card heading. */
  heading: string;
  /** Overview only — one line. */
  summary: string;
  /** Data & Privacy only — the canonical definition. */
  detail: string;
  /** Data & Privacy only — a secondary edge case, collapsed by default. */
  more?: SettingsDisclosure;
}

/**
 * The nine data/privacy concepts, in the order Data & Privacy presents them
 * (and the order Overview summarises them). Deterministic: same facts in, same
 * strings out, no time, no randomness, no locale.
 */
export function settingsConcepts(facts: SettingsFacts): SettingsConcept[] {
  const { dataRegime, persistence, recordSchemaVersion } = facts;
  const syntheticOnly = dataRegime === 'synthetic-only';
  const ephemeral = persistence === 'ephemeral';

  return [
    {
      id: 'synthetic-data-only',
      heading: 'Synthetic Data Only',
      summary: syntheticOnly
        ? 'Synthetic-only mode — file upload is refused outright, and the app cannot tell real data from synthetic.'
        : `The backend reports the data regime as "${dataRegime}".`,
      detail: syntheticOnly
        ? 'Only unmistakably synthetic data is in scope, and this build runs in synthetic-only mode: file upload is refused outright. What the app enforces is that mode, not the contents of what it is handed — it cannot tell real data from synthetic, so keeping real artifacts out is a responsibility of whoever operates it, not a check the software performs.'
        : `The backend reports the data regime as "${dataRegime}". This screen states only what the backend reports.`,
    },
    {
      id: 'no-real-experiment-data',
      heading: 'No Real Experiment Data',
      summary:
        'Out of scope for this prototype — and the upload block never checks whether what it blocked was real.',
      detail:
        'Real or private facility artifacts are out of scope for this prototype and require written data-governance approval before they could be read, indexed, or sent anywhere. What the code enforces is narrower than that policy: file upload is refused outright, with no file parsed at all, while the CSV preview and the record validator do read what you paste or pick — in memory, never stored, and logged only as an outcome, never as content. Nothing in the app inspects that text to judge whether it is real.',
    },
    {
      id: 'what-is-stored',
      heading: 'What Is Stored',
      summary: 'Just the synthetic workspace, held on the server for this deployment.',
      detail:
        'Only the synthetic workspace is stored. It is held on the server for this deployment and is not shared between deployments.',
      more: {
        label: 'What the Workspace Contains',
        text: 'Experiments, their drafts, the answers you confirm, exported records, and evidence sidecars.',
      },
    },
    {
      id: 'what-resets',
      heading: 'What Resets',
      summary: ephemeral
        ? "No database — the workspace is files on the server, discarded with the deployment's temporary storage."
        : `The backend reports persistence as "${persistence}".`,
      detail: ephemeral
        ? 'There is no database. Workspace state is written as files in a working directory on the server, so restarting the backend process does not by itself clear it. The backend reports that storage as ephemeral: it is not durable, is not shared between deployments, and is discarded whenever the temporary storage it sits on goes away — this screen cannot say when that will be.'
        : `The backend reports persistence as "${persistence}". This screen states only what the backend reports.`,
      more: {
        label: 'Assistant Conversations',
        text: 'Assistant conversations are more ephemeral still: they exist only in the open browser tab and are never written down or logged.',
      },
    },
    {
      id: 'no-telemetry',
      heading: 'No Telemetry or Analytics',
      summary: 'Nothing about your session is measured or transmitted anywhere.',
      detail:
        'Nothing about your session is measured, collected, or transmitted: no analytics, no usage tracking, and no cloud sync. The app makes no third-party network requests at all and loads nothing from a CDN.',
    },
    {
      id: 'no-external-model-calls',
      heading: 'No External Model Calls',
      summary: 'No language model at all — the assistant answers from a bounded local catalog.',
      detail:
        'There is no language model in this build. The assistant answers from a bounded, deterministic catalog over local data, and refuses anything outside it rather than guessing. Nothing you type is sent to a model provider.',
    },
    {
      id: 'project-memory-boundary',
      heading: 'Project Memory Boundary',
      summary: 'Project Memory returns leads to verify, never a correctness ruling.',
      detail:
        'Project Memory reads a committed, sanitized snapshot of served repository content. It returns navigational leads and provenance to verify — never a correctness ruling — and it cannot mark a record valid, change one, or authorize an export.',
    },
    {
      id: 'record-truth-boundary',
      heading: 'Record Truth Boundary',
      summary: 'Only the deterministic core can decide validity or authorize an export.',
      detail: `Validity and export are decided only by the official ISAAC v${recordSchemaVersion} schema and the deterministic validators, working from evidence you confirmed. No advisory surface — not the assistant, not Project Memory — can override that.`,
    },
    {
      id: 'authentication-boundary',
      heading: 'Authentication Boundary',
      summary:
        'No sign-in and no accounts, and this screen cannot report whether access is restricted.',
      detail:
        'The app has no accounts, no sign-in, and no user profiles, and none of this is configurable here. Access can be restricted in two places: by the environment this build is deployed into, and by an optional shared key the backend requires when an operator sets one. This screen has no way to report whether either restriction is active.',
      more: {
        label: 'About That Shared Key',
        text: 'The key belongs to the deployment rather than to any user, and the app never displays it.',
      },
    },
  ];
}

/**
 * About-tab copy. Identity and provenance only: the two-plane architecture and
 * the no-guessing principle. Deliberately does NOT restate a Data & Privacy
 * definition — Record Truth Boundary owns "what decides validity and export",
 * while this owns "which plane each surface belongs to".
 */
export interface SettingsAboutCopy {
  /** Title Case inline label for the truth-vs-memory paragraph. */
  truthVsMemoryLabel: string;
  truthVsMemory: string;
  /** Title Case inline label for the no-guessing paragraph. */
  noGuessingLabel: string;
  noGuessing: string;
  /** Caption under the identity figures. */
  identityCaption: string;
}

export function settingsAboutCopy(facts: SettingsFacts): SettingsAboutCopy {
  return {
    truthVsMemoryLabel: 'Truth vs. Memory',
    truthVsMemory: `This app has two planes. The deterministic core — the official ISAAC v${facts.recordSchemaVersion} schema, the draft validator, and the export/audit pipeline — is the truth plane. Project Memory, Graphify, and the assistant are the memory plane: they surface context and provenance to verify.`,
    noGuessingLabel: 'No-Guessing',
    noGuessing:
      'Every finalized field carries either cited evidence or an explicit user confirmation — nothing scientific is invented.',
    identityCaption:
      'Read from the running app and rendered verbatim — this screen computes none of these values. A build with no deploy identity injected says so rather than showing a plausible-looking commit.',
  };
}

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
