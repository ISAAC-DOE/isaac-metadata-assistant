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
};

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

  /** Actions. Plain verbs, no progress language for work that does not happen. */
  actionStart: 'Start an Import',
  actionAddReference: 'Record a Reference',
  actionAddFixture: 'Add an Example Source',
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
  addWholeLead:
    'Send every candidate that can be sent to one record, in a single step. Each ' +
    'becomes an open proposal you review there — no value is written, and nothing ' +
    'is applied for you.',

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
