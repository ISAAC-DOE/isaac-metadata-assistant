/*
 * HISTORICAL IMPORT — every authored string the surface renders, in one place.
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
};

export const IMPORT_COPY = {
  /** The eyebrow above the page title. Names the goal, not the mechanism. */
  eyebrow: 'Recover Historical Science',

  /**
   * The lead. It says what the destination is FOR and immediately says the one
   * thing that decides how a reader should use it — every candidate is a
   * suggestion, and a person decides each one.
   */
  lead:
    'Reconstruct candidate experiment metadata from the files your work is already ' +
    'scattered across — filenames, notes, sheets, run logs — and put every candidate ' +
    'through the same review and validation as anything else in ISAAC. Nothing here ' +
    'becomes a value on its own: each candidate is a suggestion you accept, correct or ' +
    'refuse.',

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

  /** Actions. Plain verbs, no progress language for work that does not happen. */
  actionStart: 'Start an Import',
  actionAddReference: 'Record a Reference',
  actionAddFixture: 'Add an Example Source',
  actionParse: 'Read the Sources',
  actionReconstruct: 'Reconstruct Candidates',
  actionPropose: 'Send to Review',
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
} as const;

export type ImportCopyKey = keyof typeof IMPORT_COPY;
