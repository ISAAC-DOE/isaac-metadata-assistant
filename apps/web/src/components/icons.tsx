/*
 * Centralized line-icons (icons-and-symbols.md). Precise, technical, line-based
 * only — no sparkle / wand / "magic AI" glyphs. Each glyph reinforces color and
 * is always paired with a text label at the call site (never icon-only signal).
 */
import {
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
};
export type { LucideIcon };
