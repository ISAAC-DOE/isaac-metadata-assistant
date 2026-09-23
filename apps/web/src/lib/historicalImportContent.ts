/*
 * HISTORICAL IMPORT — the surface's CLAIM-BEARING copy, in one place.
 *
 * ~~every authored string the surface renders~~ — **FALSE, corrected 2026-09-13 after an
 * independent review measured it (M-6).** At least six authored, user-visible strings live
 * in `screens/HistoricalImport.tsx` itself — form labels and step headings such as
 * `Name this import (optional)`, `Checksum (optional)`, `Read the Sources`,
 * `Sources disagree`, `No value was chosen`, `Send it to which record?`.
 *
 * THE DISTINCTION MATTERS BECAUSE OF WHAT THIS MODULE IS FOR: it exists so the surface's
 * CLAIMS sit inside the `upload-claim-parity` ratchet. A header promising "every authored
 * string" tells the next reader that adding copy to the screen is safe because the ratchet
 * covers it. It does not. Copy that makes a claim about what this build reads, refuses or
 * stores belongs HERE; a field label does not have to.
 *
 * WHY A CONTENT MODULE AND NOT INLINE JSX. `transcriptCaptureContent.ts`,
 * `settingsContent.ts` and `mcpConnectContent.ts` each exist for this reason and
 * it applies here more sharply than to any of them: this surface makes CLAIMS
 * ABOUT WHAT THE APPLICATION DOES WITH FILES, and that claim class has been
 * measured false in this repository four separate times. Keeping the strings in
 * a module lets `__tests__/upload-claim-parity.test.tsx` read them WITHOUT
 * rendering — so this surface joins the ratchet that already holds the other
 * seven, and a future false phrasing here fails the same test that caught the
 * others.
 *
 * ── WHAT MAY AND MAY NOT BE SAID HERE, AND WHY ──────────────────────────────
 *
 * The absolute forms are BANNED, and the ban is not stylistic — the sentences
 * *"no file is read, parsed, or inspected"* and *"this application declares no
 * upload endpoint"* both SHIPPED and were both FALSE: `RecordValidator` and
 * `CsvReconcilePanel` read a file the reader picks, and `POST /api/uploads` is
 * declared (it answers an unconditional 403). So every claim below is SCOPED —
 * to an import source, to this workflow — and none of them says anything about
 * the application as a whole.
 *
 * ── AND THE HARDER RULE: SAY WHAT IS NOT BUILT, PER THING ───────────────────
 *
 * `HIST-004`'s own banned pattern is *"Upload Files → Spinner → Mysterious
 * JSON"*, and §15's *"build nothing that implies any of it exists"* binds. A
 * destination that can hold a bundle and cannot parse most of it must SAY SO —
 * and it must say so per source and per step rather than in a banner, because
 * the answer genuinely differs per source: a committed example source IS read,
 * and a reference is not. One banner would be false for half the manifest.
 */

/** The reconstruction's two warrants, in product words. */
export const DETERMINISM_LABELS: Readonly<Record<string, string>> = {
  deterministic: 'Read from a source',
  inferred: 'Inferred by a rule',
};

/** A manifest entry's parse state, in product words. */
export const PARSE_STATE_LABELS: Readonly<Record<string, string>> = {
  parsed: 'Read',
  failed: 'Could not be read',
  unparsed: 'Not read yet',
  no_content_path: 'Held as a pointer',
};

/*
 * A source kind, in product words.
 *
 * ── WHY `synthetic_fixture` IS NOT CALLED A FIXTURE HERE ────────────────────
 *
 * `__tests__/product-facing-language.test.tsx` retires that phrasing as
 * product copy, and it is RIGHT to: "fixture" is this project's test-harness
 * vocabulary, not a scientist's. The first version of this surface used it and
 * the ratchet caught it — which is the guard working, not an obstacle.
 *
 * `Example source` is the replacement, and it reuses the register the app already
 * has: the built-in records are `Worked Example`, and that file's own header
 * records `reference source file` as the established phrasing for a committed
 * file the app reads. The WIRE VALUE `synthetic_fixture` is unchanged — it is a
 * contract value a client branches on, not copy anybody reads.
 */
export const SOURCE_KIND_LABELS: Readonly<Record<string, string>> = {
  reference: 'Reference',
  synthetic_fixture: 'Example source',
  archive: 'Archive',
};

/**
 * An archive's id as a reader names it — `bl15_synthetic_mini_corpus` becomes
 * "BL15 synthetic mini corpus" (2026-09-23). The exact id stays one press away behind a
 * `?`, because it is what an operator types and what the server logs.
 */
export function archiveLabel(id: string): string {
  const bare = id.startsWith('staged:') ? id.slice('staged:'.length) : id;
  const words = bare
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((w) => (/^[a-z]+\d+$/i.test(w) ? w.toUpperCase() : w.toLowerCase()));
  if (words.length === 0) return id;
  const text = words.join(' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export const IMPORT_COPY = {
  /** The eyebrow above the page title. Names the goal, not the mechanism. */
  eyebrow: 'Recover Historical Science',

  /**
   * The lead. It says what the destination is FOR and immediately says the one
   * thing that decides how a reader should use it — every candidate is a
   * suggestion, and a person decides each one.
   */
  /*
   * M-9 — THE PROMISE AND THE CAPABILITY ARE STILL IN THE SAME SENTENCE.
   *
   * This used to read "...from the files your work is already scattered across —
   * filenames, notes, sheets, run logs — ...", naming FOUR source classes on the
   * INDEX while the honest correction (`formatsNote`) rendered one step downstream
   * on the Sources step. Of those four, one layout is read. An independent review
   * raised it (M-9) and it is a §15 matter, not a style one: "build nothing that
   * implies any of it exists". The fix — stating the honest limit ("one layout",
   * "reference") on the SAME screen as the decision to start — is unchanged here;
   * only the SENTENCE COUNT dropped.
   *
   * CUT FROM THREE SENTENCES TO TWO, 2026-09-15. The owner: "the text is still
   * stopping midway through half the block, and it's not really something that
   * looks good" — measured, this paragraph wrapped at roughly half the card's
   * width, leaving a dead column beside it. What moved out is the ARCHITECTURE
   * detail ("put every candidate through the same review and validation as
   * anything else in ISAAC", "keeping its pointer, checksum and your notes for a
   * later build") — restated in the collapsed "How Historical Import works"
   * disclosure (`HistoricalImport.tsx`'s `ImportList`), not deleted. What STAYS
   * here, because M-9 and this file's own header both require it to sit beside
   * the decision rather than only downstream: the honest capability limit ("one
   * layout" / "reference") and the one claim that governs how to read every
   * candidate this screen ever produces ("Nothing here becomes a value on its
   * own"). `__tests__/historical-import.test.tsx`'s M-9 test still asserts both
   * substrings are in `.hi-lead` itself, unchanged.
   */
  lead:
    'Reconstruct candidate experiment metadata from files your work is already ' +
    'scattered across — today it reads one layout and records anything else as a ' +
    'reference. Nothing here becomes a value on its own: each candidate is a ' +
    'suggestion you accept, correct or refuse.',

  /**
   * THE SCOPED FILE CLAIM. Both halves are true and neither is an absolute.
   *
   * A reference really is stored as a pointer and this workflow really does not
   * open it — measured: `POST /api/imports/{id}/sources` records the string and
   * the parse operation leaves such an entry in `no_content_path`, with no
   * filesystem call of any kind. It says "this workflow", never "this
   * application": the Validator and the campaign-sheet preview both read a file a
   * reader picks, on other screens, and a sentence denying that would be the
   * exact defect `upload-claim-parity.test.tsx` exists to catch.
   */
  sourcesLead:
    'A source you record as a reference is stored as a pointer: this workflow keeps ' +
    'where the file is and what you say identifies it, and does not open the file it ' +
    'names. So a reference cannot contribute a value, and the list below says that ' +
    'against the entry rather than in a banner.',

  /**
   * Why an example source is readable when a reference is not. The asymmetry is the
   * feature's whole honesty boundary, so it is explained rather than left to be
   * inferred from two different-looking rows.
   */
  fixturesLead:
    'An example source is a file ISAAC ships for this purpose, inside the application ' +
    'itself. Those are read — each one says in its own first lines that it is made up ' +
    'and was never produced by an instrument. They are here so this workflow can be ' +
    'exercised end to end on content nobody has to trust.',

  /** A digest is recorded, never verified. The three banned words are named. */
  digestNote:
    'A checksum you enter is recorded as what you say identifies the file. Its shape is ' +
    'checked and nothing else: no checksum is computed here, for a reference or for an ' +
    'example source, so nothing on this screen means a file was verified, checked or ' +
    'matched.',

  /**
   * THE BLOCKED PARSERS, NAMED. `BL15-001` and `HIST-002` are blocked on a
   * corpus this repository does not hold, and `CLAUDE.md` §5 forbids designing
   * against zero examples. A reader who expects a `.mac` parser is told, in
   * product words, that there is not one and why — which is a better answer than
   * a disabled control implying one is nearly ready.
   */
  formatsNote:
    'One layout is read today and it is the one ISAAC’s own example sources are ' +
    'written in. ' +
    'Beamline macro files and spreadsheets are not read here: no example of either is ' +
    'available to build against, and a reader written without one would be guessing at ' +
    'a layout. Record those files as references in the meantime — the pointer, the ' +
    'checksum and your notes are kept, and a later build that can read them has ' +
    'somewhere to start.',

  /** The parse step, before it has run. States what it will and will not do. */
  parseLead:
    'Reading applies every reader this build has to every source that has one, and ' +
    'reports what each source said and what it passed over. A line it could not read is ' +
    'listed with the reason rather than dropped. Nothing about any record changes.',

  /**
   * THE RECONSTRUCTION, and what it is. "No language model is involved" is a
   * statement about THIS operation and is measured: the provider is
   * `deterministic_fake`, no provider is configured anywhere in this build, and
   * every model seam answers `501`.
   */
  reconstructLead:
    'Reconstruction reads what the sources said and proposes what they add up to. It is ' +
    'deterministic and offline: no language model is involved, and no request leaves ' +
    'this deployment. A key becomes a candidate for an official ISAAC field only when ' +
    'the key IS that field’s path, exactly — there is no alias list and no ' +
    'guessing, so every key it could not place is listed instead.',

  /**
   * THE BEAMLINE PROFILE. `BL15-002` is blocked, and the constraint that a
   * profile must never become an unofficial validator is stated to the reader
   * rather than only in the code.
   */
  profileNote:
    'No beamline conventions are applied. A beamline profile would let the same source ' +
    'be read the same way twice — filename patterns, column names, local terminology — ' +
    'and this build’s profile is empty, because encoding a convention nobody has ' +
    'measured would be inventing one. A profile is a reading aid either way and never ' +
    'decides whether a value is valid: the official ISAAC schema does that.',

  /** Where sources disagree. Says what was NOT done, which is the useful part. */
  disagreementNote:
    'Where two sources state different values for the same field, nothing is chosen. ' +
    'Every competing value is listed with the source that asserts it, and the decision ' +
    'is yours.',

  /** The review step. The one thing an import can do to a record. */
  reviewLead:
    'Sending a candidate to review stores it on a record you choose as an open ' +
    'proposal, together with the source’s own words. It writes no value: the ' +
    'record’s fields are exactly what they were, and the proposal becomes a value ' +
    'only when someone accepts it on that record.',

  /** Empty states. */
  emptyTitle: 'No imports yet',
  emptyBody:
    'Start an import to assemble the files a past experiment is scattered across, see ' +
    'what ISAAC can read out of them, and review what it thinks they say.',
  emptySourcesBody:
    'Add the files this experiment is scattered across. A reference is a pointer to ' +
    'where a file lives; an example source is a file ISAAC ships so you can see the ' +
    'whole workflow work.',
  emptyCandidatesBody:
    'Nothing has been reconstructed yet. Read the sources first — a reference on its ' +
    'own carries nothing for a reconstruction to work from.',
  /* When the sources HAVE been read and only the reconstruction is missing, the line
     above would tell a reader to do what they already did (independent review,
     2026-09-23). */
  emptyCandidatesReadBody:
    'The sources have been read, and nothing has been reconstructed from them yet. ' +
    'Reconstruct the candidates in Runs & Candidates.',

  /** Actions. Plain verbs, no progress language for work that does not happen. */
  actionStart: 'Start an Import',
  actionAddReference: 'Record a Reference',
  actionAddFixture: 'Add an Example Source',
  /** The whole-archive entry — the only control that reaches the corpus review. */
  actionAddArchive: 'Add an Archive',
  /**
   * WHAT ADDING AN ARCHIVE ACTUALLY DOES, said before it is pressed.
   *
   * It is ONE bundle entry for a whole folder, which is the thing a reader would
   * otherwise have to infer from a manifest that stays at one row while hundreds of
   * files are walked. It names no count, because the count is a property of the
   * archive and is reported after the walk rather than promised before it.
   */
  addArchiveNote:
    'One entry for the whole archive. Reading it walks every file inside, groups them into measurements, and reports what it found — including anything it could not place and anything the sources disagree about.',
  actionParse: 'Read the Sources',
  actionReconstruct: 'Reconstruct Candidates',
  actionPropose: 'Send to Review',
  /** `HIST-005` — the whole import at once, onto one record. */
  actionAddWhole: 'Add This Import to a Record',
  actionRemoveSource: 'Remove',
  actionDiscard: 'Discard This Import',
  actionOpen: 'Open',

  /**
   * The one thing a reader has to be told before they discard. The session is
   * the working area; the proposals are not in it.
   */
  discardNote:
    'Discarding removes this working area. Every proposal you have already sent stays on ' +
    'the record it was sent to, and so does the note behind it.',

  /** What a candidate that cannot be sent says, when the server gave no reason. */
  notProposableFallback:
    'This candidate cannot be sent to review, and the reason was not reported.',

  /** After a successful send. Never says "applied". */
  proposedNote: 'Sent. It is now an open proposal on that record, awaiting review.',

  /** After a send that found the proposal already there. */
  deduplicatedNote:
    'That record already held this proposal, so nothing new was created. It is still ' +
    'open and awaiting review.',

  /**
   * `HIST-005`'s lead. It has TWO jobs and both are load-bearing.
   *
   * It says what the step does — every candidate that can be sent, in one go —
   * and it says what the step does NOT do, because "Add This Import to a Record"
   * is a name a reader can hear as "apply it". Nothing is applied: each candidate
   * becomes an OPEN proposal you review on that record, one decision at a time.
   */
  /*
   * TIGHTENED 2026-09-15 — 172 characters to 157, saying the same two things.
   * Kept because the project owner asked for a streamlined, low-text UI; NOT
   * kept for the reason the first version of this comment gave.
   *
   * *** THE STATED REASON WAS WRONG AND IS CORRECTED RATHER THAN DELETED,
   * because it is a measurement error a future reader will otherwise repeat. ***
   * The edit was made to clear the one `line-length` finding Impeccable's
   * in-browser detector attributes to this panel (54 findings with the panel, 52
   * without), and the comment claimed the first wording was "86 characters per
   * line" and the new one "78". **The detector does not measure that.** All
   * TWENTY `line-length` findings on this screen report the identical number,
   * 86 — twenty paragraphs of different lengths cannot all be 86 characters per
   * line. It is measuring the COLUMN (≈557px ÷ average glyph width), so it says
   * "this measure is 86 characters wide" and every element in the column
   * inherits the same verdict. Shortening the text moved it not at all: the
   * finding is still present and still reads 86.
   *
   * SO THE FINDING IS DECLINED, WITH ITS REASON. The only thing that would clear
   * it is a narrower column, and the owner's recorded direction is "don't cap
   * prose narrow". It is the same measure residue the execution ledger already
   * carries against the global `68ch` rule, shared identically by the other
   * nineteen prose elements here, and it is a screen-wide type decision rather
   * than this panel's to take.
   *
   * BOTH CLAIMS SURVIVE THE CUT, which is what limited how far it could go: the
   * "nothing is applied" half is the reason this copy exists at all — "Add This
   * Import to a Record" is a name a reader can hear as "apply it" — and
   * `historical-import.test.tsx` asserts "no value is written" appears in this
   * panel, so neither clause could be the thing that went.
   */
  addWholeLead:
    'Send every candidate that can be sent to one record in one step. Each becomes ' +
    'an open proposal you review there — nothing is applied and no value is written.',

  /**
   * What the run field is for HERE, and it differs from the per-candidate one
   * on purpose. One run is given for the whole import and used only for the
   * values a run owns; the values the record owns ignore it.
   */
  addWholeRunNote:
    'Used only for the values a run owns. The values the record owns ignore it. If ' +
    'this import has a value a run owns and no run is named, nothing is sent at all.',

  /** The heading over the report of what the batch did. */
  addWholeResultTitle: 'What was sent',

  /**
   * What a batch that sent nothing NEW says. Reached when every candidate was
   * already on that record — a second click, or a batch after sending by hand.
   */
  addWholeNothingNew:
    'That record already held every one of these proposals, so nothing new was ' +
    'created. They are still open and awaiting review.',
} as const;

export type ImportCopyKey = keyof typeof IMPORT_COPY;

/**
 * THE STAGE FLOW'S OWN WORDS (owner QA H1, 2026-09-22).
 *
 * An opened import used to render every stage's explanation at once. The owner's
 * brief: one stage in focus, each with at most ONE short heading and ONE short
 * sentence visible, and every longer explanation behind a `HelpTip` or a
 * `Disclosure`. So each stage carries exactly a `title`, a one-sentence `lead` and a
 * `help` definition — and nothing in `help` is a blocking error, an uncertainty, a
 * consequence or a conflict (DEC-35): those stay on the surface.
 *
 * The stage names are the OWNER's, and they are deliberately not the server's
 * workflow step labels: the server's six steps describe what the backend DOES (Parse,
 * Reconstruct), and these describe what a scientist is LOOKING AT. Each stage maps to
 * one server step for "how far has this session got" (`importStages.ts`).
 */
export const IMPORT_STAGE_COPY = {
  stagesLabel: 'Import stages',
  sources: {
    title: 'Source Bundle',
    lead: 'The files this import reads from. Adding one changes no record.',
    help: 'A source is either a file ISAAC ships and can read, an archive it walks, or a pointer to a file it does not open.',
  },
  read: {
    title: 'What ISAAC Read',
    lead: 'What each source said, and what it passed over. No record changes.',
    help: 'Reading applies every reader this build has to every source that has one. A line it could not read is listed with the reason rather than dropped.',
  },
  runs: {
    title: 'Runs & Candidates',
    leadArchive: 'Each measurement ISAAC found, grouped by sample. Open one to see its values and where each came from.',
    leadFixture: 'What the sources add up to. Open a candidate to see the sources behind it.',
    help: 'A candidate is a suggestion, not a value. It becomes a value only when someone accepts its proposal on a record.',
  },
  conflicts: {
    title: 'Conflicts',
    lead: 'Where sources disagree. Every reading is kept, and nothing is chosen until you decide.',
    help: 'There is no ranking of sources. A macro is the plan, a header is what the instrument recorded, a filename is a human label, and the notes are a later reading.',
    none: 'No source disagrees with another in this import.',
    noValue: 'No value has been selected.',
    review: 'Review Sources',
    fieldKindTitle: 'A field with more than one stated value',
    fieldKindMeaning:
      'Two or more files state a different value for the same field. Every value is kept, with the file that states it, and nothing is chosen.',
  },
  review: {
    title: 'Review',
    lead: 'What can go forward now, and what still needs a decision.',
    help: 'Only candidates marked Ready to Send can become proposals. The others say why they cannot.',
  },
  add: {
    title: 'Add to Experiment',
    lead: 'Send every ready candidate to one record as open proposals. No value is written.',
    help: 'Each sent candidate becomes an open proposal on the record, with a note carrying the source’s own words.',
  },
  stateLabels: {
    ready: 'Ready to Send',
    needsReview: 'Needs Review',
    conflict: 'Sources Conflict',
    unmapped: 'Unmapped',
    resolved: 'Resolved',
    sourcesAgree: 'Sources Agree',
    notRecorded: 'Not Recorded',
    stated: 'Stated in a Source',
    notBuilt: 'Not Built',
    reached: 'Reached',
    ambiguous: 'Ambiguous',
    stale: 'Stale Rule',
    suggested: 'Suggested',
    sent: 'Sent',
    variesByScan: 'Varies by Scan',
    severalPerScan: 'Several per Scan',
    variesByFile: 'Varies by File',
  },
  /*
   * PER-SCAN VARIATION (2026-09-22, `bl15.mapping.RULE_CARDINALITY`). Neither agreement
   * nor conflict: each scan has its own value, as the concept is expected to, and every
   * scan's reading is kept.
   */
  variation: {
    eachScan: 'Each scan’s reading',
    eachItem: 'Each reading, scan by scan',
    eachFile: 'Each file’s reading',
    why: 'This value is expected to differ from scan to scan, so different scans stating different values is not a disagreement. Two sources that disagree about the same scan would be a conflict.',
    whyItem:
      'A scan states several of these — one per column or motor — so different values are different items, not a disagreement. Two sources that disagree about the same item of the same scan would be a conflict.',
    whyFile: 'Each file names its own pieces, so different files stating different values is not a disagreement.',
    conflictsNote:
      'are stated once per scan, column, motor or file, as they are expected to be, and are not conflicts. Each reading is kept under Runs & Candidates.',
  },
  bucketTitles: {
    ready: 'Ready to Send',
    /* NAMED FOR THE SET IT COUNTS (2026-09-23): field values whose sources disagree —
       distinct from the Conflicts tab's count, which also holds the findings about which
       measurement a file is, and from what the Add stage cannot send. */
    conflict: 'Field Values in Conflict',
    needsReview: 'Needs Review',
    resolved: 'Resolved',
    unmapped: 'Unmapped',
    /* A candidate this import already sent (2026-09-23) — its own group, never "Ready". */
    sent: 'Sent',
  },
  summaryTitle: 'At a Glance',
  statementsTitle: 'What It Said',
  skippedTitle: 'Passed Over',
  sourcesColumn: {
    file: 'File',
    kind: 'Kind',
    read: 'Read?',
    actions: 'Actions',
  },
  moreSources: 'What counts as a source',
  conventionsTitle: 'Naming Conventions',
  conventionsHelp:
    'A convention says what a filename token means. It is chosen by the source’s own name and never by who ran a measurement.',
  temperatureTitle: 'Temperature',
  temperatureStated: 'Kept exactly as written — never converted to a number, and no number is offered.',
  temperatureWhy: 'Why no temperature is filled in',
  peopleTitle: 'People Named in the Notes',
  peopleHelp:
    'Recorded as provenance only. A person is never the reason a file is read one way or another, and is never the actor of anything in ISAAC.',
  signalTitle: 'HERFD Signal',
  signalHelp:
    'Per run, ISAAC suggests a primary channel only when exactly one carries live signal and one element is established. A suggestion is never a decision.',
  qualityTitle: 'Data Quality Notes',
  qualityNote: 'Kept word for word. Never read as a QC verdict.',
  allCounts: 'All counts, and where each came from',
  mapping: 'What the official schema can take',
  ceiling: 'What cannot be finished here',
  extended: 'Kept in the extended context',
  leftOut: 'What this import left out',
  layers: {
    sourceFact: 'Source Facts',
    normalized: 'Normalized Reading',
    suggested: 'Suggested Resolution',
    confirmed: 'Scientist-Confirmed Resolution',
    nonAuthoritative: 'Not authoritative',
    normalizedNone: 'None — these readings are compared exactly as written.',
    noSuggestion: 'No suggestion — the evidence does not point one way.',
    notYet: 'Not resolved yet.',
  },
  resolve: {
    choose: 'Which reading is right?',
    scope: 'Apply it',
    groupTitle: 'Resolve a Whole Sample Group',
    groupLead:
      'Choose which kind of source is right for every conflict of this kind in one sample group. It applies only where exactly one reading comes from that kind of source, and every reading is kept.',
    groupWhich: 'Which sample group?',
    groupRole: 'Which kind of source is right?',
    groupSubmit: 'Record This Choice for the Group',
    submit: 'Record This Choice',
    forbidden:
      'Both acquisitions are kept, and nothing will be chosen: nobody can say which one is right.',
    fixtureOnly:
      'This build records a choice between readings for archive imports only. Enter the value on the record yourself.',
  },
  rulesTitle: 'Reading Rules',
  rulesHelp:
    'A rule records how to read sources — never a value. Rules are versioned, never edited, and applied only where you choose.',
  rulesNone: 'No reading rule has been recorded for this import.',
  suggestionsTitle: 'Suggested From Other Experiments',
  adopt: 'Adopt for This Experiment',
  confirmedBy: 'Confirmed by',
  unattributed: 'Unattributed',
  /* The owner's own three phrases (QA H1). A rule for an Experiment or a convention
     is stored on the Experiment chosen just below, so "this" is that one. */
  scopeOptions: {
    import: 'Apply only here',
    experiment: 'Use as a rule for this Experiment',
    profile: 'Use as a rule for this convention',
  },
  whichExperiment: 'Which experiment?',
  bindingTitle: 'Read Some Runs With Another Convention',
  bindingOne: 'One naming convention is registered in this build, so there is nothing to switch to.',
  bindingSubmit: 'Record This Convention',
  signalConfirm: 'Confirm This Channel',
  signalAssign: 'Record Channel Assignment',
  addSummaryTitle: 'What Will Be Sent',
  addResultTitle: 'What Happened',
  createRuns: 'Make one run per measurement',
  openProposals: 'Open Proposals on This Record',
  acceptanceNote:
    'Accepting a proposal needs a reviewer this deployment can identify, and it cannot identify one yet. The proposals stay open on the record until it can.',
  runsPresent: 'Measurements that already had a run',
  runsCreated: 'Runs created',
  dqnCaptured: 'Data Quality Notes kept as run notes',
  reread: 'This import was re-read under this record’s own reading rules first.',
  searchLabel: 'Search measurements',
  whereFrom: 'Where each value came from',
  sharedLegacy: 'Shares its legacy number with another acquisition — both are kept, and neither is preferred.',
  discardTitle: 'This Working Area',
  fields: {
    convention: 'Convention',
    fromRun: 'From run',
    toRun: 'To run',
    element: 'Element',
    edge: 'Edge',
    record: 'Which record?',
    run: 'Which run?',
  },
} as const;
