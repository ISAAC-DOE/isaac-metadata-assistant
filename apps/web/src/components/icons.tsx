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
  Download,
  LayoutList,
  Search,
  X,
  ZoomIn,
  ZoomOut,
  Maximize2,
  RotateCcw,
  Diamond,
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

export {
  Check,
  UserCheck,
  CornerDownRight,
  CircleDashed,
  CircleAlert,
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
  Download,
  LayoutList,
  Search,
  X,
  ZoomIn,
  ZoomOut,
  Maximize2,
  RotateCcw,
  Diamond,
};
export type { LucideIcon };
