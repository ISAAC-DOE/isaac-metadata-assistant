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
 *  - since Slice 2A the deployment may additionally run a protected, read-only
 *    diagnostic against an isolated SLAC test database containing
 *    production-derived records. So NO string here may describe the whole
 *    build, prototype, deployment or app as synthetic-only, or put real data
 *    out of scope, without stating that: the scope a claim can keep is the
 *    WORKSPACE. Whichever concept makes the capability statement ("may run …")
 *    must state every bound of it on that same surface — naming the capability
 *    without its bounds is the same over-claim in the other direction.
 *    `__tests__/db-recon-truthfulness.test.tsx` enforces both halves per
 *    concept, and re-scans every frontend source file for the same claim class.
 *  - `persistence: "ephemeral"` is a fixed literal about deployment intent, not
 *    a process-lifetime guarantee. Workspace state is written to files under a
 *    server-side working directory, so it outlives the process; only the
 *    deployment's temporary storage bounds it.
 *  - the app cannot tell whether the deployment restricts access. The optional
 *    shared key the backend can require is configured outside the browser, so
 *    the client may state the uncertainty but never a status.
 *  - access is FOUR separate things and the copy keeps them separate: (a) the
 *    edge in front of the deployment, which decides whether a browser reaches
 *    ISAAC at all; (b) app-managed identity and roles, which do not exist;
 *    (c) the optional shared bearer key the backend can require; (d) per-user
 *    API-key management, which no operation in this build provides. Collapsing
 *    them produced the old "no sign-in and no accounts" summary, which read as
 *    "this deployment is open" — the opposite of how it is operated.
 *  - a claim about (a) is a claim about how the deployment is CONFIGURED and
 *    OPERATED. Say so explicitly; the browser observes none of it.
 *  - infrastructure topology is never named. `apps/api/tests/
 *    test_about_and_openapi.py` withholds a fixed list of substrings from
 *    `GET /api/about`, and `src/__tests__/settings-page.test.tsx` re-asserts it
 *    on the rendered text of every tab. That list forbids naming the identity
 *    PRODUCT in front of a deployment, so the copy says "institutional single
 *    sign-on" and never the vendor; the operating institution and the fact that
 *    an edge exists are not on the withheld list and are stated plainly.
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
  | 'how-long-it-is-kept'
  | 'reset-and-deletion'
  | 'export-handling'
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
 * The twelve data/privacy concepts, in the order Data & Privacy presents them
 * (and the order Overview summarises them). Deterministic: same facts in, same
 * strings out, no time, no randomness, no locale.
 *
 * P2 (privacy consolidation) added `reset-and-deletion` and `export-handling`.
 * They are not decoration: this tab is meant to be the ONE place a reader can
 * answer "what is collected, stored, retained, reset, exported?", and until now
 * it answered five of those six. Deletion was described nowhere on any settings
 * surface, and export was named only in passing inside the `what-is-stored`
 * disclosure — so a reader asking "what happens to a record I export?" had to
 * infer it from a list of directory contents.
 *
 * P2 FOLLOW-UP added `how-long-it-is-kept`, which closes the LAST of those six.
 * `screens/GovernancePage.tsx` tells the reader in so many words that this tab is
 * the canonical home for what the build "retains", and there was no concept, no
 * heading and no duration anywhere behind that pointer — seven of the eight
 * topics the consolidation named had landed and retention had not. It sits
 * between `what-resets` and `reset-and-deletion` on purpose: what is stored,
 * where it resets, HOW LONG it lasts, how it is deliberately removed.
 */
export function settingsConcepts(facts: SettingsFacts): SettingsConcept[] {
  const { dataRegime, persistence, recordSchemaVersion } = facts;
  const syntheticOnly = dataRegime === 'synthetic-only';
  const ephemeral = persistence === 'ephemeral';

  return [
    {
      // Slice 2A (I5) — the fourth surface of the same defect, and the one that
      // rendered DIRECTLY ABOVE the already-corrected `no-real-experiment-data`
      // card on Data & Privacy, so the tab contradicted itself in one screenful.
      //
      // The heading was 'Synthetic Data Only' and the detail opened "Only
      // unmistakably synthetic data is in scope, and this build runs in
      // synthetic-only mode". The SCOPE half of that sentence was the false
      // part: it is a flat claim about the whole build, and the deployment may
      // now run a protected, read-only diagnostic over an isolated test
      // database of production-derived records. The heading now names what the
      // card is actually about — the runtime MODE — and the scope sentence is
      // gone.
      //
      // The `id` is unchanged: `hosted-truthfulness.test.tsx` looks the concept
      // up by it, and the concept itself did not change — only the accuracy of
      // its claims.
      //
      // What must NOT be lost, and is asserted in
      // `__tests__/db-recon-truthfulness.test.tsx` and
      // `__tests__/hosted-truthfulness.test.tsx`: mode-not-content enforcement,
      // "it cannot tell real data from synthetic", real mode refusing to start
      // with its guardrail reason, and operator responsibility. All four are
      // still in the always-visible `detail`, never behind a disclosure.
      //
      // The mode token `synthetic-only` is KEPT on purpose — it is the name
      // `GET /api/health` reports and what the operator configured, exactly as
      // the Help popover keeps it. The rule is not "never say synthetic-only",
      // it is "never leave it standing as an unqualified whole-deployment
      // claim", so the diagnostic is named on this same card.
      //
      // WHAT MOVED, AND WHY IT IS NOT A WEAKENING. This card used to end with
      // the full 55-word capability paragraph — the SAME paragraph, verbatim,
      // that `no-real-experiment-data` ends with. At 1440px the two render as
      // adjacent columns, so the tab whose entire purpose is consolidation
      // showed one reader the identical sentence twice, side by side. Reported
      // in review as exactly that.
      //
      // The paragraph now lives ONCE, in `no-real-experiment-data`, which is
      // the card a reader takes as the guarantee about real data and therefore
      // the card the diagnostic is the exception TO. This card keeps a POINTER
      // and names where the full statement is.
      //
      // The machine rule is unchanged and still holds: a unit that makes the
      // capability statement ("may run a protected, read-only diagnostic")
      // must state every bound of it, and the unit that makes it does. This
      // card no longer makes it, so it is in exactly the position `what-resets`
      // has occupied since Slice 2A — it REFERS to the diagnostic, which keeps
      // its mode token from ever standing unqualified, without restating a
      // capability it is not the home of. `__tests__/db-recon-truthfulness.test.tsx`
      // §11 and §12 were re-pointed to assert that split, and §12 gained a
      // duplication guard so the paragraph cannot come back twice.
      //
      // Same load-bearing wording constraints as components/GovernanceBanner.tsx
      // and screens/GovernancePage.tsx: "may run", never "is running"
      // (configuration is not reachability); an isolated SLAC test database,
      // never the production database; and no claim that the app verified that
      // isolation — the guarantee is an external pg_hba grant.
      id: 'synthetic-data-only',
      heading: 'Synthetic-Only Mode',
      summary: syntheticOnly
        ? 'Synthetic-only mode — file upload is refused outright, and the app cannot tell real data from synthetic.'
        : `The backend reports the data regime as "${dataRegime}".`,
      detail: syntheticOnly
        ? 'This deployment runs in synthetic-only mode: file upload is refused outright, and the records in this workspace are synthetic. Real mode intentionally refuses to start, because the ingestion and governance guardrails it would need do not exist yet. What the app enforces is that mode, not the contents of what it is handed — it cannot tell real data from synthetic, so keeping real artifacts out of the workspace is a responsibility of whoever operates it, not a check the software performs. The mode is not the whole picture: a protected, read-only diagnostic may separately read production-derived records from an isolated SLAC test database. Every bound on that is stated once on this tab, by the card No Real Experiment Data in the Workspace, rather than a second time here.'
        : `The backend reports the data regime as "${dataRegime}". This screen states only what the backend reports.`,
    },
    {
      // Slice 2A (I5). The heading was "No Real Experiment Data" and the detail
      // opened "Real or private facility artifacts are out of scope for this
      // prototype" — both flat, whole-deployment claims that stopped being true
      // once a protected, read-only diagnostic could run against an isolated
      // test database of production-derived records. The scope is now stated as
      // the WORKSPACE, and the diagnostic is named with its bounds rather than
      // left to be inferred from a promise the deployment no longer keeps.
      //
      // The `id` is unchanged: `hosted-truthfulness.test.tsx` and
      // `screens/statistics/StatisticsPage.tsx` refer to it, and nothing about
      // the concept itself changed — only the accuracy of its claims.
      //
      // What must NOT be lost from the previous copy: the upload block is a MODE
      // gate, not a content check, and the second half of `detail` still says so
      // ("Nothing in the app inspects that text to judge whether it is real"),
      // still in the always-visible text and never behind a disclosure.
      //
      // Same load-bearing wording constraints as components/GovernanceBanner.tsx
      // and screens/GovernancePage.tsx: "may run", never "is running"
      // (configuration is not reachability); an isolated SLAC test database,
      // never the production database; and no claim that the app verified that
      // isolation — the guarantee is an external pg_hba grant.
      //
      // THIS CARD IS THE TAB'S SINGLE HOME FOR THE CAPABILITY STATEMENT. The
      // closing paragraph — "Separately, this deployment may run …" through
      // "…pending an explicit visibility decision" — is the ONE copy of it on
      // Data & Privacy. `synthetic-data-only` used to end with the same 55 words
      // verbatim, and at 1440px the two render side by side; the duplicate is
      // gone and that card now points here. Do not restore it there, and do not
      // delete it here: `db-recon-truthfulness.test.tsx` §10 requires every
      // bound in this `detail`, and §12 requires the paragraph to appear on the
      // tab exactly once.
      id: 'no-real-experiment-data',
      heading: 'No Real Experiment Data in the Workspace',
      summary:
        'Kept out of the workspace — the upload block never checks whether what it blocked was real, and the separate read-only diagnostic displays no record.',
      detail:
        'Real or private facility artifacts are out of scope for this workspace and require written data-governance approval before they could be read, indexed, or sent anywhere. What the code enforces is narrower than that policy: file upload is refused outright, with no file parsed at all, while the CSV preview and the record validator do read what you paste or pick — in memory, never stored, and logged only as an outcome, never as content. Nothing in the app inspects that text to judge whether it is real. Separately, this deployment may run a protected, read-only diagnostic against an isolated SLAC test database containing production-derived records: those records are processed transiently in pod memory, only sanitized aggregate results are returned, no record is modified, no per-record content is displayed, and nothing is sent to any model. Database-backed record display remains disabled pending an explicit visibility decision.',
    },
    {
      // WHAT WAS INCOMPLETE, and why the correction is an addition rather than a
      // rewording. Both strings said the workspace is the ONLY thing stored
      // ("Just the example workspace" / "Only the example workspace is stored").
      // That was true while the five built-in examples were materialised into the
      // ordinary workspace on every read. It stopped being true when they moved
      // into a per-session scope: the server now also creates a temporary
      // directory for each worked-example session and writes that session's own
      // copies of the examples into it, plus everything answered, edited or
      // exported inside it. A reader asking "what is stored?" was being told about
      // one of the two places.
      //
      // Every clause below is checked against the backend, and nothing stronger is
      // claimed than the code enforces:
      //
      //  · TWO PLACES, both files on the server. `workspace.py:10-13` gives the
      //    layout under the workspace root (this cited `:16-19`, which is the
      //    status-is-derived-on-read paragraph, not the layout block);
      //    `scope_root` (`:170-180`) returns
      //    `workspace_root()` for the ordinary scope and
      //    `workspace_root()/_tutorial/<session_id>` for a session.
      //  · ITS OWN COPY OF THE EXAMPLES. `create_tutorial_session`
      //    (`:996-1024`) mints the directory and calls `ensure_tutorial_seeded`
      //    (`:864-903`), which materialises the five canonical scenarios into THAT
      //    session; the module docstring states "one independent copy per session"
      //    (`:26-31`).
      //  · ANSWERS, EDITS AND EXPORTS GO THERE, not into the workspace. Every path
      //    an `Experiment` writes is rooted at its own scope: `Experiment.dir` is
      //    `scope_root(self.session_id)/self.id` (`:413-415`), and `records_dir`
      //    — which holds the exported record and its evidence sidecar — hangs off
      //    that (`:417-419`).
      //  · WHEN IT GOES AWAY, and why the copy hedges the first arm. Every exit
      //    path calls `DELETE /api/tutorial/sessions/{id}` (`routes.py:762-779` →
      //    `dispose_tutorial_session`, `workspace.py:1058-1066`), but that call is
      //    BEST EFFORT BY DESIGN — `lib/tutorialController.ts:355-369` swallows a
      //    failure and leaves the directory "for the backend's TTL sweep to
      //    reclaim". So the copy says the app discards it and names the fallback,
      //    rather than promising a deletion that a dropped request would not
      //    perform. The fallback is `sweep_stale_tutorial_sessions`
      //    (`workspace.py:1069-1113`), which runs when a session is OPENED
      //    (`routes.py:719-723`), not on a timer — hence "the next time a
      //    walkthrough is opened" rather than a promised deletion time.
      //
      // Deliberately NOT stated: the TTL's value. `TUTORIAL_TTL_HOURS = 24`
      // (`workspace.py:128`) is a backend constant this module is not given — the
      // API reports it as `ttl_hours` when a session is created — and this file's
      // rule is that a value-dependent sentence is built from facts the backend
      // actually reported (see the header). A hardcoded "24 hours" here would be a
      // second copy of a number that can change without this file.
      //
      // Also NOT stated: any filesystem path. No other product surface names one,
      // and `POST /api/demo/reset` deliberately keeps paths out of its response.
      id: 'what-is-stored',
      heading: 'What Is Stored',
      summary:
        'The workspace, plus a temporary directory for each walkthrough that is opened.',
      detail:
        'Two things are stored, both as files on the server for this deployment, and neither is shared between deployments. The first is the workspace itself. The second is a temporary directory the server creates for each worked-example walkthrough: opening one writes that walkthrough its own copy of the five built-in example records, and every answer, edit and exported artifact you produce inside it is written there rather than into the workspace. The app discards that directory when the walkthrough ends; if that request does not reach the server the directory simply expires, and an expired one is removed the next time a walkthrough is opened.',
      more: {
        label: 'What the Workspace Contains',
        text: 'Experiments, their drafts, the answers you confirm, exported records, and evidence sidecars.',
      },
    },
    {
      // Slice 2A (I5). The summary opened "No database —" and the detail opened
      // "There is no database." Both were flat claims about the DEPLOYMENT, and
      // both stopped being true: the deployment may be configured with an
      // isolated SLAC test database that a protected, read-only diagnostic
      // reads. Rendered two cards below `no-real-experiment-data`, which names
      // that database, "There is no database" was a visible self-contradiction
      // on one tab.
      //
      // The claim is now scoped to what this card is about — where the WORKSPACE
      // lives — and the test database is placed outside that scope explicitly,
      // because "what resets" is exactly the question a reader would carry to it.
      //
      // This surface refers to the diagnostic; it does not make the CAPABILITY
      // statement ("may run …"). The surfaces that make that statement must
      // carry all of its bounds — see `__tests__/db-recon-truthfulness.test.tsx`,
      // which enforces precisely that split. Here only the storage-relevant
      // bounds are stated, and none of them is weaker than the full paragraph.
      id: 'what-resets',
      heading: 'What Resets',
      summary: ephemeral
        ? "The workspace is files on the server, not a database — discarded with the deployment's temporary storage."
        : `The backend reports persistence as "${persistence}".`,
      detail: ephemeral
        ? "The workspace is not stored in a database. Workspace state is written as files in a working directory on the server, so restarting the backend process does not by itself clear it. The backend reports that storage as ephemeral: it is not durable, is not shared between deployments, and is discarded whenever the temporary storage it sits on goes away — this screen cannot say when that will be. The isolated SLAC test database that the protected, read-only diagnostic may read is not the workspace's storage: nothing from it is written here, no record is modified, and only sanitized aggregate results are returned."
        : `The backend reports persistence as "${persistence}". This screen states only what the backend reports.`,
      more: {
        // Was "they exist only in the open browser tab and are never written down or
        // logged." The second half was false: `lib/assistantSession.ts` writes the
        // transcript to `sessionStorage` under `isaac.assistant.session.<id>` (see
        // `writeStorage`), so it IS written down and it DOES survive a reload. The
        // true, and still strong, statement is where it is written, how long it lives,
        // and what is stripped first — not that nothing is stored.
        label: 'Assistant Conversations',
        text: 'Assistant conversations stay in the browser tab that created them, but they are not held only in memory: the transcript is written to sessionStorage in that tab, so it survives a page reload and is erased when the tab closes. It is never sent to a server, never logged, and never written to localStorage or IndexedDB. Only the most recent 40 messages are kept. Credentials, absolute file paths, long hex digests and record verdicts are removed before anything is stored — and "removed" means the whole message text is withheld, not that the offending fragment is snipped out of it: deciding where a file path ends cannot be done reliably, and a partial redaction that guesses wrong would leak. So a question or answer containing any of those is not stored at all, and the archived copy says so in place of the text. The answer you were given at the time is unaffected.',
      },
    },
    {
      // P2 FOLLOW-UP — RETENTION, which `GovernancePage.tsx` advertises this tab
      // as canonical for and which no settings surface stated at all.
      //
      // WRITTEN FROM THE CODE. Every clause, with what establishes it:
      //
      //  · ONE STATED MAXIMUM AGE, and it belongs to the walkthrough.
      //    `TUTORIAL_TTL_HOURS` (`workspace.py:128`) bounds a session's life and
      //    is returned as `ttl_hours` by `POST /api/tutorial/sessions`
      //    (`routes.py:836`). NOTHING else in the backend has an age limit —
      //    `sweep_stale_tutorial_sessions` (`workspace.py:1206-1247`) is the only
      //    expiry mechanism there is, and it can only ever look inside
      //    `tutorial_namespace_root()`.
      //  · THE NUMBER IS DELIBERATELY NOT PRINTED. Same rule `what-is-stored`
      //    already follows: a value-dependent sentence is built from a fact the
      //    backend reported to THIS module, and this module is given three facts,
      //    none of them a TTL. A hardcoded "24 hours" would be a second copy of a
      //    constant that can change without this file.
      //  · AND THE COPY SAYS SO, because the first draft did not and was wrong.
      //    It read "reports that figure when the walkthrough opens", which a
      //    reader takes as "so I will be told what it is". They will not:
      //    `ttl_hours` reaches the client (`lib/types.ts:842`) and NO screen
      //    renders it — grep the frontend and the only hits are this comment and
      //    that type. Promising a number the product never shows is the same
      //    over-claim class as the retired absolute upload claim, one indirection
      //    smaller. The sentence now states the limit exists, says where it is
      //    set, and admits the number is not on screen.
      //  · WHAT BECOMES OF AN EXPIRED ONE IS NOT RESTATED. `what-is-stored`
      //    already says it is removed the next time a walkthrough is opened. This
      //    card names that card instead of authoring a near-duplicate sentence on
      //    the same tab — the defect the consolidation exists to prevent.
      //  · THE WORKSPACE HAS NO EXPIRY OF ITS OWN. There is no timer, no
      //    scheduled deletion and no retention period over `workspace_root()`;
      //    its life is the life of the directory. On the deployed pod that
      //    directory is an `emptyDir` (`docs/deployment.md:29-31`), so a restart
      //    takes it. The copy does NOT put a duration on that, because
      //    `what-resets` already says this screen cannot say when the temporary
      //    storage goes away, and contradicting it one card later would be worse
      //    than saying nothing.
      //  · THE VERIFICATION REPORT. `_VERIFICATION_STATE` (`routes.py:4993`) is a
      //    module-level singleton holding `_cached` in the process's own memory,
      //    so a restart takes it; `CACHE_TTL_SECONDS` (`verification.py:156`)
      //    bounds how long a result is served before a recomputation is offered,
      //    and `metadata.cache_age_seconds` is rendered as "Report Age"
      //    (`screens/statistics/RecordVerification.tsx:770`). The seconds are not
      //    printed here for the same reason the TTL hours are not — and note that
      //    `lib/verificationContract.ts:954` is a client-side MIRROR of that
      //    constant, not a fact the backend reported, so it is not a licence to
      //    print "an hour" on this tab either.
      //  · THE DIAGNOSTIC RETAINS NOTHING. `verification.py:1032` — private
      //    records are streamed and discarded, never retained. This card REFERS
      //    to the diagnostic (which is what keeps a mode token from standing
      //    unqualified) and does not make the capability statement, so it owes no
      //    bounds; `no-real-experiment-data` is still the one home for those.
      //    Same split `what-resets` has held since Slice 2A.
      //  · EXPERIMENTS ARE DEPLOYMENT-DEPENDENT, AND DURABILITY IS NOT CLAIMED.
      //    `GET /api/health` reports `experiment_storage.state`
      //    (`routes.py:910`), and `screens/ExperimentsHome.tsx` renders the
      //    matching sentence from `lib/labels.ts:522-549` — one of three,
      //    including the `unavailable` one.
      //
      //    CORRECTED 2026-08-09, and the correction is to this comment only; no
      //    copy and no condition below it changed. This block used to say that
      //    `unavailable` is "the state the deployed pod is in today" and that the
      //    migration "has not been applied anywhere". Both were true when written
      //    and are false now: Dean applied `0001_experiments` to the hosted
      //    database on 2026-08-09, and `/api/health` on `/krish` reports
      //    `{backend: "postgres", durable: true, state: "durable"}` — measured, see
      //    `docs/evidence/hosted-0001-verification-2026-08-09.md`.
      //
      //    WHAT DOES NOT CHANGE IS THE DEPENDENCE, which is the only thing this
      //    card ever asserted. `unavailable` is still a reachable live state — of a
      //    fresh environment, of a rolled-back one, and of the window before any
      //    future migration — and in it the create still returns `503` having
      //    written nothing: `docs/create-experiment-persistence.md` §0.1, "What the
      //    app does when the migration has NOT been applied", is the table that
      //    says so, and the `postgres-migration` CI job proves it on every PR. So
      //    this card states the DEPENDENCE and names the surface that resolves it,
      //    rather than promising rows that persist. It could not do otherwise even
      //    if it wanted to: `SettingsFacts` carries `/api/about` values and
      //    `experiment_storage` is on `/api/health`, so this module has never been
      //    told which state is live — which is exactly why a stale belief about
      //    the hosted deployment could sit in this comment without ever reaching a
      //    reader. The `detail` sentence below is phrased as a CONDITION —
      //    "where a database is configured but is not accepting the work" — so it
      //    stays true whichever state is live. The sentence that does assert a
      //    state lives in `lib/labels.ts` and is chosen from
      //    `experiment_storage.state` alone.
      //  · "NOTHING IS KEPT FOR A WHILE AND THEN LOST" is the precise consequence
      //    of that 503 and is worth the words: a create that fails writes nothing
      //    at all, rather than quietly leaving something temporary behind.
      //
      //  · WHAT THE TWO BROWSER ENTRIES HOLD, itemised rather than promised
      //    away. `tutorialPreference.ts:16-21` states its own exhaustive list —
      //    tutorial id, version, boolean, completion timestamp — and
      //    `tutorialSession.ts:27-32` holds `sessionId` plus `index`. An earlier
      //    draft said neither holds "a credential", which is a claim this file
      //    should not make: the worked-example session id travels in
      //    `X-Isaac-Tutorial-Session` and is what addresses that session's
      //    directory, so whether it counts as one is an argument, not a fact. The
      //    copy now enumerates the four and the two instead, which is stronger
      //    than the denial it replaces and cannot be argued with.
      //
      // WHY THE BROWSER HALF IS BEHIND `more`. Hiding it cannot make the visible
      // copy overstate: the visible copy makes no claim about the browser, and
      // localStorage has no maximum age either, so "one stated maximum age" holds
      // with the disclosure shut. The last visible sentence still points at it, so
      // the reader is never left thinking the server is the whole story.
      id: 'how-long-it-is-kept',
      heading: 'How Long It Is Kept',
      summary:
        'Only a walkthrough has a stated maximum age; everything else lasts as long as the server, the deployment, or the browser holding it.',
      detail:
        'Only one thing in this build has a stated maximum age, and it is the worked-example walkthrough: the server sets how long an unfinished one may sit and states that limit to the page when the walkthrough opens, though no screen here shows the number. What Is Stored describes what becomes of one that passes it. Nothing else is kept to a schedule. The workspace has no expiry of its own and lasts as long as the working directory it sits in, which is the directory What Resets is about. The verification report is held in the server process memory for a bounded period before a recomputation is offered, is shown with its own age, and is gone when that process restarts; the protected, read-only diagnostic keeps none of what it reads. How long an experiment lasts depends on where this deployment stores experiments, and My Experiments states which before you make one — where a database is configured but is not accepting the work, nothing is kept for a while and then lost, because the attempt fails and nothing is written. Your browser also keeps two small things on lifetimes of their own.',
      more: {
        label: 'What the Browser Keeps',
        text: 'Two things, and they expire differently. Whether this browser has finished the walkthrough is written to localStorage, so it outlives the tab and the browser being restarted and lasts until the site data is cleared; it describes this browser only, is filed under no account, and does not follow you to another device. The pointer to a walkthrough still in progress goes to sessionStorage instead and dies with the tab, as do the assistant conversations described under What Resets. Neither holds a record, a scientific value, or an identity value: the completion entry holds the walkthrough id, a version, a flag and the time you finished, and the pointer holds the session the server minted and which step you had reached.',
      },
    },
    {
      // P2 — DELETION, which no settings surface described at all.
      //
      // Every clause is checked against the code, and nothing stronger is
      // claimed than it enforces.
      //
      // THAT SENTENCE WAS ONCE FALSE, AND RECORDING IT HERE IS THE POINT. The
      // reset clause below said the server "writes nothing" when the plan is
      // stale, and the detail text repeated it to the reader. C2 made the
      // `plan_digest` precondition PER RECORD — re-checked inside each record's
      // own lock, immediately before that record is touched — so a write landing
      // mid-reset is refused rather than destroyed, and the reset stops there
      // with earlier records already restored. A self-certifying comment cannot
      // check itself, and nothing else pinned this string;
      // `__tests__/reset-claim-parity.test.tsx` now does.
      //
      //  · CONFINED TO A WALKTHROUGH. `POST /api/demo/reset` requires the
      //    worked-example session header and refuses without it, so the control
      //    renders only inside `components/TutorialSessionBar.tsx` and addresses
      //    a directory namespace that contains nothing else.
      //  · PREVIEW IS READ-ONLY, and execution carries the preview's own
      //    `plan_digest` — 428 when absent, 412 when stale — so a reset
      //    authorised against figures that have since moved is REFUSED rather
      //    than run (`components/ResetDemoDialog.tsx`'s `doExecute`). It does
      //    NOT say "writes nothing": an absent digest, and a stale one caught by
      //    the workspace-wide check, write nothing; a stale plan caught by the
      //    per-record check refuses after restoring the records the loop had
      //    already reached, and no field on `DemoResetResponse` tells a reader
      //    which of the two happened.
      //  · THE TYPED PHRASE IS NOT NAMED HERE ON PURPOSE. The dialog's own
      //    field states it (`TYPED_GATE`); the backend phrase is different and
      //    is deliberately never surfaced. Printing either here would put a
      //    second, driftable copy of a destructive gate on a settings screen.
      //  · THE BROWSER-SIDE CLEAR. A successful execute calls `clearAllSessions()`,
      //    which erases the assistant transcripts this tab holds in
      //    sessionStorage — the one effect of a reset that is NOT server-side,
      //    and therefore the one a reader would not otherwise expect.
      //  · ENDING A WALKTHROUGH. `DELETE /api/tutorial/sessions/{id}` discards
      //    the session directory and everything in it. It is best effort (see
      //    `what-is-stored`), which is why the expiry fallback is stated there
      //    and not promised again here.
      //  · WHAT HAS NO DELETE. There is exactly one DELETE operation in the
      //    whole API (the session discard above); nothing removes the workspace,
      //    a record, or an exported artifact.
      id: 'reset-and-deletion',
      heading: 'Reset and Deletion',
      summary:
        'Deliberate removal reaches only a walkthrough — nothing here deletes the workspace, a record, or an exported file.',
      detail:
        "Deliberate removal is narrow in this build, and everything it can reach sits inside a worked-example walkthrough. Reset Worked Example rebuilds that walkthrough's own copies of the built-in example records: it previews the effect without changing anything, requires a typed confirmation, and is checked against the figures you were shown — if the walkthrough moved in between, the server refuses rather than act on figures that no longer describe it, and shows you the refreshed ones. When it does run it permanently discards the confirmed answers, the progress, and the exported artifacts inside that walkthrough, and it also clears the assistant conversations this browser tab is holding. Ending a walkthrough discards its whole temporary directory along with everything in it. Nothing in this build deletes the workspace itself, an individual record, or a single exported artifact — no operation offers it.",
    },
    {
      // P2 — EXPORT, which was named only inside `what-is-stored`'s collapsed
      // disclosure ("exported records, and evidence sidecars") as one item in a
      // list of directory contents. That answers "is it stored?" and not "where
      // does it go?", which is the question a reader actually brings here.
      //
      //  · TWO FILES, SERVER-SIDE. `_write_record` (`routes.py`) writes
      //    `<id>.json` and `<id>.evidence.json` into `Experiment.records_dir`,
      //    which hangs off the experiment's own scope — the same scope the
      //    record already lives in, so an export moves nothing between scopes.
      //  · THE DOWNLOAD IS PURELY CLIENT-SIDE. `screens/ExportReadiness.tsx`'s
      //    `download()` builds a `Blob` from data already in the page and uses
      //    an object URL; there is no request, no service, and no third party.
      //  · AND THEN IT STOPS BEING OURS. Stated plainly rather than left
      //    implied: once the file is on the reader's machine, nothing on this
      //    tab describes what happens to it. Claiming otherwise would be the
      //    same over-reach as the retired absolute upload claim.
      id: 'export-handling',
      heading: 'Exporting a Record',
      summary:
        'An export writes two files on the server; downloading one happens in your browser and puts the copy beyond this app.',
      detail:
        'Exporting writes two files into the same server-side directory the record already lives in: the official ISAAC record and its evidence sidecar. Nothing leaves the deployment in the process — there is no upload, no third-party service, and no model involved. Downloading either file happens entirely in your browser: it is assembled from data already on the screen and saved to your machine. From that point the copy on your machine is outside this app, and nothing stated on this tab describes what happens to it.',
    },
    {
      // P2 — THE SCOPE SENTENCE, relocated rather than re-authored.
      //
      // The first sentence used to read "Nothing about your session is measured,
      // collected, or transmitted" with no subject bound to it. Statistics had
      // ALREADY had to retract exactly that shape: its no-analytics section once
      // claimed the preview "does not track visits, users, source IPs, request
      // history, or behavioral analytics", which is false of the deployment —
      // `uvicorn` writes an access line per request, `routes.py` writes
      // metadata-only per-operation outcome lines, and a hosted deployment sits
      // behind an identity gateway the browser cannot see. That correction was
      // relocated into Statistics' Known Limitations, and Statistics' section
      // links HERE for the full statement — so the full statement now has to
      // include the scope. The wording is taken from the already-vetted
      // paragraph in `screens/statistics/StatisticsPage.tsx` rather than
      // invented a third time.
      //
      // It stays in the always-visible `detail`. A caveat that keeps the visible
      // sentence from overstating what the code does may never go behind `more`.
      id: 'no-telemetry',
      heading: 'No Telemetry or Analytics',
      summary: 'This application measures and transmits nothing about your session.',
      detail:
        'Nothing about your session is measured, collected, or transmitted by this application: no analytics, no usage tracking, and no cloud sync. The app makes no third-party network requests at all and loads nothing from a CDN. Server-side logs are a separate matter and this claim does not cover them: the backend writes a metadata-only outcome line per operation, the web server it runs under writes an access line per request, and a hosted deployment sits behind an identity gateway that keeps records of its own. Those belong to whoever operates the deployment, the browser cannot see them, and nothing here is a claim about what they contain or how long they are kept.',
    },
    {
      id: 'no-external-model-calls',
      heading: 'No External Model Calls',
      // "local catalog" / "over local data" read against "external provider"
      // here, but "local" is still a locality word this app cannot claim on a
      // deployment — so both name WHERE the catalog and the data actually are.
      summary:
        'No language model at all — the assistant answers from a bounded in-repository catalog.',
      // P2 — the last sentence absorbed the MODEL half of a clause relocated off
      // Governance & Safety → Policy ("nothing on any screen here is sent to a
      // model or an index"). "Nothing you type" was narrower than what Governance
      // was promising, so the wider subject moved with it rather than being
      // quietly dropped. The INDEX half landed on `project-memory-boundary`.
      detail:
        "There is no language model in this build. The assistant answers from a bounded, deterministic catalog over the deployment's own data, and refuses anything outside it rather than guessing. Nothing you type, and nothing shown on any screen here, is sent to a model provider.",
    },
    {
      id: 'project-memory-boundary',
      heading: 'Project Memory Boundary',
      summary: 'Project Memory returns leads to verify, never a correctness ruling.',
      // P2 — the second sentence is the INDEX half of the clause relocated off
      // Governance & Safety → Policy. It is a statement about direction: the
      // snapshot is built from repository content by `scripts/build_memory_snapshot.py`
      // before the app runs and is served read-only, so no screen writes into it.
      detail:
        'Project Memory reads a committed, sanitized snapshot of served repository content. Nothing you type, confirm, or export is added to that snapshot — it is built before the app runs and no screen writes into it. It returns navigational leads and provenance to verify — never a correctness ruling — and it cannot mark a record valid, change one, or authorize an export.',
    },
    {
      id: 'record-truth-boundary',
      heading: 'Record Truth Boundary',
      summary: 'Only the deterministic core can decide validity or authorize an export.',
      detail: `Validity and export are decided only by the official ISAAC v${recordSchemaVersion} schema and the deterministic validators, working from evidence you confirmed. No advisory surface — not the assistant, not Project Memory — can override that.`,
    },
    {
      // FINDING F — "institutional single sign-on" WEAKENED to "an interactive
      // sign-in step". The stronger phrase's plainest reading is "your
      // institutional account signs you in", and nothing observed supports it:
      // the one unauthenticated observation of the deployment's login flow
      // (`docs/developer-guide-k8s.md`, the 2026-08-01 correction) found only an
      // Email-or-Username field and an ORCID button at the identification stage,
      // with later stages UNOBSERVED. The fix is to weaken, NOT to specify —
      // naming the identity product is forbidden on every Settings tab by
      // `settings-page.test.tsx`'s withheld list and by the backend's own.
      // The final clause states the retraction rather than leaving the reader to
      // notice the missing word.
      id: 'authentication-boundary',
      heading: 'Authentication Boundary',
      summary:
        'Access is controlled by the deployment, not by ISAAC accounts — and this screen cannot report whether access is restricted.',
      detail:
        'Four separate things, deliberately not merged into one. First, access to a deployed ISAAC instance is controlled in front of ISAAC, at the network edge where it is operated. The SLAC-hosted deployment is configured to sit behind an interactive sign-in step, so a browser session is established there before any ISAAC page loads — a statement about how the deployment is operated, never something this app verified, because the browser cannot see the edge, and deliberately not a claim about which account signs you in. Second, ISAAC itself does not manage user accounts, profiles, or application roles, and none of that is configurable here. Third, the backend can additionally require one shared bearer key on every operation except the liveness check; it belongs to the deployment rather than to a person, and this screen has no way to report whether either restriction is active. Fourth, there is no per-user API-key management in this build: no operation creates, lists, revokes, or rotates a credential.',
      more: {
        label: 'About That Shared Key',
        text: 'The backend reads it once at startup from its own environment and compares it on each request. The app never displays it, and nothing on this screen can create, replace, or reveal one.',
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

// --- API Access / Endpoint Explorer canonical copy (P36V-1 slice 13) ---------

/**
 * The API surfaces had the SAME four claims authored in four places: the
 * key-unavailable status was in the API-Keys lead, in an access row, in Quick
 * Start's Authentication note AND in Connect an Agent; the browser-session /
 * headless-credential boundary was in two of those. Each claim now lives here
 * exactly once and is rendered from here exactly once — `settings-page.test.tsx`
 * counts every string below across all five tabs and requires a total of 1.
 *
 * Nothing here asserts a value the generated contract carries. Counts, media
 * types, error codes, the base path and the operation list stay derived from
 * `GET /api/openapi` in `lib/apiDocsModel.ts`; these strings only say what the
 * BUILD does and does not have, which the contract cannot report about itself.
 */
export const API_ACCESS_COPY = {
  /** THE status, on the API Access banner. Nothing else restates the reason.
   *
   *  Slice 2A (I5): was "…in This Synthetic Preview". Nothing about API keys
   *  turns on the data regime, so the word "Synthetic" was carrying no meaning
   *  here — it was only labelling the whole build as synthetic, which is the
   *  unqualified whole-application claim this slice removed everywhere else.
   *  "This Build" states the same scope without the claim. */
  statusHeading: 'API Key Management Is Not Available in This Build',
  statusBody:
    'This API has no operation that creates, lists, revokes, or rotates a credential, so no key can be issued from this screen — and there is never a key here to reveal, copy, or store. The Endpoint Explorer tab is the proof: it lists every operation this build has.',
  /** The disabled Create control's own reason — short, because the banner owns
   *  the explanation. Always visible AND `aria-describedby`-associated.
   *
   *  It NAMES the section it points at rather than its position. "See the status
   *  above" was true in both current source orders, but a positional reference is
   *  the construction slice 12 had to remove elsewhere on this very surface (the
   *  Endpoint Explorer "above" became false the moment it moved to its own tab),
   *  and it reads as nonsense once the two-column grid stacks. */
  createDisabledReason:
    'Disabled: there is no operation for this button to call — see the API Key Management status on this tab.',
  /** Lead-in to the collapsed Technical Requirements disclosure. */
  requirementsNote:
    'What would have to exist before a key could be issued. Each is a backend and security contract this prototype does not have; none of them is stubbed out behind this screen, and they belong to a later, separately authorized phase.',
  /** The intentional empty state of Your API Keys. */
  emptyTitle: 'No keys to show.',
  emptyBody:
    'This list is empty by design, not by circumstance — nothing failed to load.',
  /**
   * The ONE explanation of the Endpoint Explorer's per-operation Auth marker.
   * It replaced a two-sentence authentication paragraph that was repeated on
   * every single endpoint's detail pane; the marker itself is now compact
   * metadata, and this legend is stated once for the whole tab.
   */
  authMarkerLegend:
    "Auth reports whether the contract documents a 401 for an operation. Where a deployment enables authentication those operations need the deployment's credential, and the liveness check is the one that stays reachable without it.",
  /**
   * FINDING B — the prerequisite Connect an Agent never stated.
   *
   * That guide is eight steps under the lead "only what this build actually
   * supports", and it is a `<details>` a reader can open on its own. Slice 13
   * de-duplicated the tab's boundaries out to the access rows, which was right
   * for the SHARED claims — but it left the guide able to be read start to
   * finish without ever meeting the fact that disqualifies the whole procedure
   * on this deployment. Pointing at a sibling component is not enough when the
   * sibling holds the precondition.
   *
   * So the fact is carried HERE, in the guide itself, and stated once: this is
   * a new canonical string, which means `settings-page.test.tsx`'s duplication
   * guard counts it across all five surfaces and requires exactly 1.
   *
   * It is conditional on purpose. The API, the contract and the bearer seam are
   * real; a self-run deployment answers a program directly, which is what
   * `docs/developer-guide-k8s.md` tells a developer to do instead. Claiming the
   * API is unreachable everywhere would be the same defect inverted.
   */
  connectPrerequisite:
    'One thing has to be true before any of these steps applies: the deployment has to answer a program at all. A deployment that answers only browser sessions — as the SLAC-hosted one is documented to — will not answer a call made outside one, with or without a credential, so no agent can connect to it and nothing obtainable from this screen changes that. What follows describes a deployment that does answer a program directly, such as one run locally.',
  /**
   * FINDING E — the requirement that is not the application's.
   *
   * The five requirements below it are all app-owned, and a reader takes the
   * list as the full path to shipping. It is the app half: even with all five
   * built, a program still has to be able to reach the API, and that is the
   * deployment's to arrange rather than something this codebase can implement.
   * Stated as a boundary on the list, so the list itself stays true.
   *
   * No positional reference ("the list above"): slice 12 had to retire exactly
   * that construction on this surface once the content moved.
   */
  requirementsBoundary:
    "Those five are the application's to build, and building all five would still not be enough on its own. One requirement is not ours: a program has to be able to reach the API in the first place, and a deployment that answers only browser sessions does not let it — that part belongs to whoever operates the deployment.",
  /**
   * THE OTHER MECHANISM, named — the mirror of `MCP_CONNECT_COPY.restApiPointer`.
   *
   * "Connect an Agent" and the "Connect Your Agent" tab are one word and two
   * tabs apart, describe different protocols, and made unreconciled claims
   * about authentication to the same reader: this guide says every call carries
   * a credential in a header when a deployment enables authentication, and that
   * tab says there is no configured way to authenticate a caller. Each is true
   * of its own path, and neither said so relative to the other.
   *
   * Authored here rather than inline so the duplication guard counts it like
   * every other canonical string on this tab, and so the two directions can be
   * read side by side in one module diff.
   */
  connectMcpPointer:
    'This guide is about calling the HTTP API from a program you write. Pointing your own Claude at ISAAC’s machine-callable tool interface is a different mechanism with a different answer about authentication, and the Connect Your Agent tab describes it — including the fact that no agent can reach this deployment yet.',
} as const;

/**
 * How access works today — one question per row, each answer stated here and
 * nowhere else on either API tab. The bearer-header name and the 401 counts are
 * deliberately absent: Quick Start derives those from the contract.
 */
export const API_ACCESS_ROWS: readonly { term: string; detail: string }[] = [
  {
    // FINDING C — the modality was wrong under a heading reading "How Access
    // Works Today". "Required on every operation except the liveness check" is
    // true of a deployment that SETS the key; where none is set the backend
    // requires it on ZERO operations, because `auth.py`'s middleware returns
    // `call_next` immediately when the expected value is empty. The trailing
    // "cannot see whether it is switched on" rescued the sentence only for a
    // reader who got that far. This file already had the right modality one
    // concept away ("the backend CAN ADDITIONALLY require…"); both branches are
    // now stated, and the epistemic limit is kept rather than dropped.
    term: 'Current Access Model',
    detail:
      'One credential belonging to the whole deployment, set on the server before the app starts. A deployment that sets one requires it on every operation except the liveness check; a deployment that sets none requires it on no operation at all, and refuses nothing for want of it. It identifies the deployment, not a person, and this screen cannot see which of the two it is running on.',
  },
  {
    // FINDING A — this was stated unconditionally, and on the deployment the
    // reader is looking at it is false: a key enables none of it, because a
    // call made outside a browser session does not arrive
    // (`docs/developer-guide-k8s.md`: "Scripted access (curl) to the deployed
    // URL won't work without a browser session; test against a local run or
    // `docker run` instead"). The missing CONDITION is added rather than the
    // capability denied — the second sentence must not become the opposite
    // over-claim, because the API and the bearer seam are real and a
    // self-run deployment does answer a program directly.
    //
    // The second sentence is adapted from `External Agent Access` below, which
    // is the sharpest true sentence on this tab; it is deliberately NOT copied
    // verbatim, since every row is counted exactly once across all five
    // surfaces by `settings-page.test.tsx`.
    term: 'What an API Key Would Enable',
    detail:
      'On a deployment that answers a program directly, a program running outside this browser — a script, a notebook, or an agent — could call the operations listed on the Endpoint Explorer tab directly, without a person driving the interface. Where a deployment instead answers only browser sessions, as the SLAC-hosted one is documented to, a key would enable none of that: the call does not reach these operations at all, whether or not it carries a credential.',
  },
  {
    term: 'External Agent Access',
    detail:
      'Not through anything you can obtain here. Whoever operates this deployment holds the single credential; the app cannot issue a second one, and browsing this page does not give a program a way in.',
  },
  {
    // Added when the client-side bearer seam was removed. The rows above were
    // already careful about what the DEPLOYMENT may require; none of them said
    // what THIS PAGE sends, and a reader could reasonably assume the interface
    // authenticates itself somehow. It does not, and the reason is worth being
    // explicit about rather than leaving as an absence.
    //
    // The removed seam read `import.meta.env.VITE_API_KEY`, which Vite
    // substitutes at BUILD time — the value would have been compiled into the
    // JavaScript served to every visitor. This row exists so that "the browser
    // sends no credential" reads as a decision with a reason, not an oversight
    // someone should helpfully fix.
    //
    // The copy deliberately avoids the word this surface's leak guard forbids
    // (`settings-page.test.tsx` FORBIDDEN). That guard caught the first draft of
    // this row and it was right to: the sentence is about what the interface
    // sends, and it can make that point without the vocabulary the guard exists
    // to keep off this screen. The guard was not relaxed to admit the prose.
    term: 'What This Interface Sends',
    detail:
      'No credential of any kind. This page attaches no authorization header to any request, and there is no build setting that would make it — a value compiled into a web page is readable by everyone the page is served to, so it could never have been kept private. Where a deployment does require the shared credential, this interface is not the thing that would satisfy it; a program calling the API directly is.',
  },
  {
    term: 'Hosted Authentication Boundary',
    detail:
      "Signing in through a deployment's identity layer with a browser is not the same thing as headless authentication: that gives a person an interactive session, not a credential a program can present on its own.",
  },
];

/** The contract that would have to exist first. Requirements, never a roadmap
 *  promise, and collapsed so they never lead the surface. */
export const API_KEY_REQUIREMENTS: readonly string[] = [
  'Durable storage for credentials, holding a hash rather than the value, so a stored credential cannot be read back.',
  'Per-key identity, so a key names who or what holds it instead of standing for the whole deployment.',
  'Revocation and expiry, so a key can be withdrawn without restarting the service.',
  'Scopes, so a key issued for reading cannot be used to write or export.',
  'A record of use, so a key that leaks can be traced and cut off.',
];
