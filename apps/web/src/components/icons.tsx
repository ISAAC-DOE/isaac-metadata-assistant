/*
 * Centralized line-icons (icons-and-symbols.md). Precise, technical, line-based
 * only — no sparkle / wand / "magic AI" glyphs. Each glyph reinforces color and
 * is always paired with a text label at the call site (never icon-only signal).
 */
import {
  BookMarked,
  Check,
  User,
  UserCheck,
  CornerDownRight,
  CircleDashed,
  CircleAlert,
  EyeOff,
  TriangleAlert,
  Shield,
  ShieldCheck,
  FileText,
  FileJson,
  Table2,
  List,
  MessageSquare,
  Lock,
  Pencil,
  ChevronRight,
  ChevronLeft,
  ChevronDown,
  ExternalLink,
  Copy,
  Play,
  Plus,
  Settings,
  Network,
  Upload,
  AudioWaveform,
  CircleHelp,
  Circle,
  Compass,
  Download,
  LayoutList,
  BarChart3,
  Search,
  X,
  ZoomIn,
  ZoomOut,
  Maximize2,
  RotateCcw,
  // The three Compare Runs glyphs. Each is a plain geometric mark and none of
  // them is a verdict: `Equal` says two things are the same, not that they are
  // right; `ArrowLeftRight` says two things differ, not which one to prefer;
  // `Columns2` is the two-column layout itself. Deliberately NOT a scale, a
  // trophy, a thumb or an arrow that points up — every one of those would rank one
  // run above the other, which is the thing that surface must never do.
  Equal,
  ArrowLeftRight,
  Columns2,
  // THE FOLDER GLYPH, for the Experiment Library. A plain outline folder, and
  // it is the ONE place in this app where a folder metaphor is drawn — so it
  // carries a risk this file's other glyphs do not: a reader who sees a folder
  // expects Drive, and ISAAC has no empty folders, no folder rename, no sharing
  // and no folder owner. The mark is therefore always paired with the text of
  // the path, never used as a standalone control, and the screen states what a
  // folder IS (`LABELS.libraryFolderModelNote`). Deliberately NOT `FolderPlus`,
  // which would name an act — creating an empty folder — that cannot happen.
  Folder as FolderIcon,
  // The Library's filter mark. `SlidersHorizontal`, not `Filter`: a funnel says
  // "things have been removed", and these chips are lenses over one list whose
  // counts are stated over the WHOLE list beside each one.
  SlidersHorizontal,
  // The four provenance glyphs this file did not already have. Each is a plain
  // line mark and none of them is a verdict: `CornerRightUp` points at the record
  // an inherited value lives on, `Cpu` is a processor outline (deliberately NOT a
  // sparkle or a wand — this file's own rule), `Quote` is a citation mark, and
  // `Inbox` is content that is waiting to be placed.
  CornerRightUp,
  Cpu,
  Quote,
  Inbox,
  // The Workspace Activity glyph (`ACT-004`). A clock with a counter-clockwise
  // arrow: *what has already happened*, which is exactly what an append-only audit
  // history holds. Deliberately NOT `Activity` (Lucide's ECG line), which reads as
  // a live signal or a health trace — this section counts recorded acts and states
  // no trend and no health at all, the same reasoning that chose `BarChart3` for
  // the Statistics destination over a trend or gauge mark.
  History,
  // 2026-09-22 — the shared state + navigation primitives. `Hourglass` is
  // "Awaiting Judgment" (time passing, not a verdict); `Minus` is "Not
  // Applicable"; `ArrowLeft` is the focused capture views' way back to Capture
  // Home; `Mic` names the local recorder beside its text label.
  Hourglass,
  Minus,
  ArrowLeft,
  Mic,
  type LucideIcon,
} from 'lucide-react';
import type { SourceType } from '../lib/types';
import type { ChipKind } from '../lib/status';

// Status-chip glyphs (status-system.md).
export const CHIP_ICON: Record<ChipKind, LucideIcon> = {
  verified: Check,
  confirmed: UserCheck,
  inferred: CornerDownRight,
  missing: CircleDashed,
  needsYou: CircleAlert,
  pass: Check,
  fail: TriangleAlert,
  exported: Check,
  mentorReview: MessageSquare,
  draft: Pencil,
  // Evidence-support axis (P28.5) — distinct glyphs so the class is never
  // signalled by color alone, and a candidate never wears the confirmed check.
  evSupported: ShieldCheck,
  evCandidate: CornerDownRight,
  evInsufficient: CircleAlert,
  evConflicting: TriangleAlert,
  evUnknown: CircleHelp,
  // `EyeOff`, not `CircleHelp`: "unknown" is a question about the record, this is
  // the server saying it could not SEE what is stored. Distinct from every other
  // glyph on this axis, so the two are never told apart by colour alone.
  evUnreadable: EyeOff,
  // Reconciliation axis (P31.3) — distinct glyphs so the state is never signalled
  // by color alone, and an absent value never wears the confirmed check.
  reconMatch: Check,
  reconConflict: TriangleAlert,
  reconAbsent: CircleDashed,
  // ORIGIN axis. Eight distinct glyphs, because these chips are deliberately all
  // the same neutral colour (see `CHIP_META`) — the glyph and the label are the
  // ONLY things telling one origin from another, so no two may share one.
  // NOTHING here is a check mark: an origin is never an approval.
  //
  // `origManual` WAS `UserCheck`, directly beneath that sentence. Lucide's
  // `UserCheck` is a torso, a head, and `polyline points="16 11 18 13 22 9"` — a
  // check mark, drawn at the same 13px / 2.2 stroke as `revSupported: Check` on
  // the review axis. So a field a person typed and nobody confirmed rendered as
  // `[check] Entered by a person` beside `[warn] Needs review`, and the check is
  // the higher-contrast, faster-read mark of the two.
  //
  // That is this model's central invariant defeated in the one channel still
  // open to it. The Python signature forbids an origin reaching the review-state
  // decision; the palette makes all eight origin chips neutral; the glyph was
  // the only remaining way to encode approval on the origin axis, and it was
  // using the approval glyph. The test named below makes this mechanical rather
  // than a matter of remembering.
  origManual: User,
  origFile: FileText,
  origVoice: AudioWaveform,
  origInherited: CornerRightUp,
  origAssistant: Cpu,
  origDerived: CornerDownRight,
  origEvidence: Quote,
  // `DEC-43`. `BookMarked` — a decision somebody wrote down and can be looked up —
  // and deliberately NOT a warning mark. The origin axis is neutral by construction
  // (see the paragraph above): an alarming glyph here would encode a judgement about
  // the VALUE, when what this origin states is where the value came from. That the
  // number was not measured is carried by the chip's own words, "Domain Guidance,
  // Not Measured", which is a claim a reader does not have to decode a picture for.
  origDomainGuidance: BookMarked,
  origUnknown: CircleDashed,
  // REVIEW axis.
  revSupported: Check,
  revNeedsReview: CircleAlert,
  revConflict: TriangleAlert,
  revUnmapped: Inbox,
  // A PERSON decided. `UserCheck` rather than `Check`, which `revSupported`
  // wears: the glyph says who settled it, not that the value is established.
  revResolved: UserCheck,
};

// Evidence source-type glyphs (icons-and-symbols.md).
export const SOURCE_ICON: Record<SourceType, LucideIcon> = {
  spreadsheet: Table2,
  file_listing: List,
  derivation: CornerDownRight,
  user_confirmation: UserCheck,
  document: FileText,
  screenshot: FileText,
  web_form: FileText,
};

/**
 * The glyph for a source type, for a value that MIGHT NOT BE IN THE MAP.
 *
 * `SOURCE_ICON[st]` is typed total over `SourceType`, and that type is a
 * compile-time promise about server data — which is not a promise at all.
 * Measured on `77820bf`: one evidence entry citing an unlisted source type (a
 * plain `instrument_log`) made `SOURCE_ICON[...]` `undefined`, React threw
 * "Element type is invalid", and because there is no ErrorBoundary anywhere in
 * this app the ENTIRE Evidence view rendered as an empty DOM — every valid entry
 * lost to one unknown string.
 *
 * `CircleHelp` is deliberate and is not a placeholder for the source type: the
 * type itself is still rendered verbatim next to it at every call site, so the
 * reader sees the real stored string and a glyph that says "this client does not
 * know this kind" — never a guess at which kind it might be.
 */
export function sourceIcon(sourceType: string | undefined): LucideIcon {
  return SOURCE_ICON[sourceType as SourceType] ?? CircleHelp;
}

export {
  Check,
  UserCheck,
  CornerDownRight,
  CircleDashed,
  CircleAlert,
  EyeOff,
  TriangleAlert,
  Shield,
  ShieldCheck,
  FileText,
  FileJson,
  Table2,
  List,
  MessageSquare,
  Lock,
  Pencil,
  ChevronRight,
  ChevronLeft,
  ChevronDown,
  ExternalLink,
  Copy,
  Play,
  Plus,
  Settings,
  Network,
  Upload,
  AudioWaveform,
  CircleHelp,
  Circle,
  Compass,
  Download,
  LayoutList,
  // The Statistics destination glyph: a plain axis-and-bars mark. Chosen over the
  // trend/gauge-shaped alternatives because that surface states counts only — it
  // carries no trend line, gauge or health score (see the statistics screen).
  BarChart3,
  Search,
  X,
  ZoomIn,
  ZoomOut,
  Maximize2,
  RotateCcw,
  Equal,
  ArrowLeftRight,
  Columns2,
  FolderIcon,
  SlidersHorizontal,
  /*
   * NEWLY EXPORTED for the Historical Import destination. The glyph itself is
   * unchanged and has been imported above since the provenance work — its own
   * comment there calls it "content that is waiting to be placed", which is both
   * an unmapped note (`revUnmapped`, the existing use) and a source bundle
   * nothing has read yet.
   *
   * SHARING ONE MARK ACROSS THOSE TWO IS CONSISTENT RATHER THAN A COLLISION:
   * they are the same fact in two places. Both sites pair it with a text label,
   * which is this file's standing rule, so nothing is signalled by the glyph
   * alone.
   */
  Inbox,
  History,
  CornerRightUp,
  Hourglass,
  Minus,
  ArrowLeft,
  Mic,
};
export type { LucideIcon };
