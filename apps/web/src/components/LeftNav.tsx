import './chrome.css';
import { Link } from 'react-router-dom';
import { BarChart3, Inbox, LayoutList, Settings } from './icons';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';
import type { LucideIcon } from './icons';

export type NavKey =
  | 'experiments'
  | 'imports'
  | 'memory'
  | 'governance'
  | 'statistics'
  | 'settings';

/**
 * THE PRIMARY DESTINATIONS — THREE, down from five (2026-09-13).
 *
 * ── WHAT WAS MEASURED ───────────────────────────────────────────────────────
 *
 * Five top-level slots, and two of them were not scientists' destinations:
 *
 * * **Project Memory** (`UX-015`/**DEC-19**) — ~7,800 lines and **578 test
 *   cases, the largest single test mass in the application** — renders a graph
 *   of *this repository's own source code*. It occupied one of five slots in a
 *   scientist's primary navigation.
 * * **Statistics** (`UX-017`) — the densest screen in the application
 *   (**3,820 px, 422 visible text elements**), of which the scientist-relevant
 *   half is per-record summary that belongs beside the records.
 *
 * ── WHAT THIS CHANGE IS AND IS NOT ──────────────────────────────────────────
 *
 * **It is a NAVIGATION change, not a deletion.** `DEC-19` says so in terms for
 * Project Memory: *"Capability and tests PRESERVED."* Both routes are untouched,
 * both screens render exactly as before, every deep link and bookmark still
 * resolves, and not one of those 578 test cases is removed. What changes is
 * which three things a scientist is offered first.
 *
 * **Nothing became unreachable, and that ordering was deliberate.** §19's own
 * sequencing rule for a demotion is: provide the capability elsewhere first,
 * verify nothing becomes inaccessible, and only then remove it from primary
 * navigation. Both destinations are linked from `Settings & API → Overview`
 * before this list shrank — see `SettingsPage`'s advanced-surfaces section —
 * which is what makes `NAV_PARENT` below true rather than decorative.
 *
 * ── WHAT WAS DELIBERATELY *NOT* DEMOTED, AND WHY ────────────────────────────
 *
 * **Governance & Safety stays.** The authorizing direction lists three
 * top-level destinations (`Experiments`, `Historical Import`, `Settings`) and
 * §19 enumerates the surfaces to demote — the Evidence Graph, Project Memory,
 * Statistics, and the schema/API/agent developer surfaces. **Governance is
 * named in neither list.** It is a scientist-facing honesty surface rather than
 * a developer one, and inferring its removal from a list that does not mention
 * it would be taking a product decision nobody took. Raised in the ledger as an
 * open question for Krish instead.
 *
 * ~~**`Historical Import` is NOT added here.** It is one of the three named
 * top-level destinations, and there is no import pipeline behind it yet. §15's
 * *"build nothing that implies any of it exists"* forbids offering the slot
 * before the destination; adding it would be a nav item that teaches a
 * scientist a capability this build does not have.~~
 *
 * **REVERSED 2026-09-13, and kept struck rather than deleted because "this is
 * deliberately absent" is exactly the kind of claim a future session acts on —
 * by re-deleting it.** The decline was CORRECT when it was written and its
 * condition is now met: the destination exists. `HIST-001`, `HIST-004` and
 * `HIST-003a` shipped in the same change that adds this item — nine HTTP
 * operations over an import session, a review surface over them, and a
 * deterministic reconstruction whose output enters the existing proposal review
 * pipeline. So the item no longer teaches a capability this build lacks.
 *
 * **AND THE HALF OF §15 THE DECLINE RESTED ON IS STILL LOAD-BEARING, which is
 * why the destination says what it cannot do rather than implying otherwise.**
 * It cannot open a file a scientist points at; it cannot parse a `.mac` or a
 * spreadsheet (`BL15-001`/`HIST-002` are blocked on a corpus this repository
 * does not hold, and §5 forbids designing a parser against zero examples); it
 * encodes no beamline convention (`BL15-002`, same block); and it does not
 * create an experiment for you (`HIST-005`). Every one of those is stated on the
 * surface, per source or per step, rather than in a banner — because the answer
 * differs per source and a banner would be wrong for half of them.
 *
 * **THE ORDER IS THE PRODUCT'S**, not alphabetical and not by age: `Experiments`
 * is the home, `Historical Import` is the second pillar, and the two
 * scientist-facing destinations sit together above `Governance & Safety` and
 * `Settings & API`.
 */
const ITEMS: { key: NavKey; label: string; icon: LucideIcon; to: string }[] = [
  { key: 'experiments', label: LABELS.navExperiments, icon: LayoutList, to: ROUTES.experiments },
  /*
   * `Inbox` — "content that is waiting to be placed", which is `icons.tsx`'s own
   * description of that glyph and is exactly what a source bundle is.
   *
   * DELIBERATELY NOT `Upload`, which this file also exports: nothing about this
   * destination uploads anything, and a glyph that said so would be the first
   * false claim a reader met. Not `FolderIcon` either — that mark is reserved for
   * the Library's virtual folder path and its own comment explains why a folder
   * metaphor is already carrying risk here.
   *
   * THE GLYPH IS REUSED (`revUnmapped` wears it too) AND THAT IS CONSISTENT
   * RATHER THAN A COLLISION: an unmapped note and an unparsed source bundle are
   * the same fact in two places — content ISAAC holds and has not placed. Both
   * sites pair it with a text label, which is this file's standing rule.
   */
  { key: 'imports', label: LABELS.navImports, icon: Inbox, to: ROUTES.imports },
  /*
   * `Statistics` IS BACK IN THE PRIMARY LIST, 2026-09-15, BY THE PROJECT
   * OWNER'S DECISION — and the reasoning that demoted it on 2026-09-13 is left
   * standing above rather than deleted, because it was not wrong about what it
   * measured.
   *
   * That decline measured the SCREEN (3,820 px, 422 visible text elements) and
   * concluded the slot was not earned. The owner's instruction is about the
   * DESTINATION: a scientist does want to know how much is recorded, how much
   * is ready and how much still needs them, and there is nowhere else in the
   * product that answers it. Those are different questions, and only one of
   * them is an agent's to answer.
   *
   * SO THE PROMOTION CARRIES AN OBLIGATION, stated here so a future session
   * cannot read the slot as settled while the screen behind it is not: the
   * density finding is unretracted, and `Statistics` earns this slot only once
   * the page is scientist-first. `UX-017`'s measurement is the acceptance bar,
   * not a historical note.
   *
   * `BarChart3` is already exported by `icons.tsx` and is paired with a text
   * label, which is this file's standing rule.
   */
  { key: 'statistics', label: LABELS.navStatistics, icon: BarChart3, to: ROUTES.statistics },
  { key: 'settings', label: LABELS.navSettings, icon: Settings, to: ROUTES.settings },
];

/**
 * WHERE A DEMOTED DESTINATION NOW LIVES — so a reader standing on one is not
 * looking at a navigation list with nothing marked in it.
 *
 * The demoted item's parent slot is tinted, and **`aria-current` is deliberately
 * NOT set on it.** `aria-current="page"` means *this link points at the page you
 * are on*, and on Project Memory the Settings link does not. Claiming otherwise
 * would tell a screen-reader user they are somewhere they are not — a smaller
 * version of exactly the honesty defect class this application keeps finding. So
 * the ancestor gets a visual affordance and no assertion; the class name says
 * which it is.
 */
const NAV_PARENT: Partial<Record<NavKey, NavKey>> = {
  memory: 'settings',
  /*
   * `governance` JOINS THE DEMOTED SET AND `statistics` LEAVES IT (2026-09-15).
   *
   * Governance & Safety is not a place a scientist goes to do their job; it is
   * where they go to check what this build does with their data. That is a
   * question asked once and then trusted, which is a Settings question and not
   * a fifth primary destination — and the top-level list is supposed to stay
   * very small.
   *
   * NOTHING ABOUT THE CAPABILITY MOVES. The route is unchanged, every existing
   * deep link into it still resolves (`?tab=validator` from My Experiments and
   * from the assistant's own composer, `?tab=schema` from Statistics), and the
   * Record Validator is reachable in exactly as many clicks from the surfaces
   * that actually send a reader there. Only the nav slot is withdrawn.
   */
  governance: 'settings',
};

interface LeftNavProps {
  active: NavKey;
}

/**
 * Top-level destinations. Active item = tint + weight + label colour (no
 * coloured rail). A demoted destination's parent slot is tinted as an ANCESTOR
 * — see `NAV_PARENT` for why that is a weaker claim than `active`.
 */
export function LeftNav({ active }: LeftNavProps) {
  const ancestor = NAV_PARENT[active];
  return (
    <nav className="leftnav" aria-label="Primary">
      {ITEMS.map(({ key, label, icon: Icon, to }) => {
        const isActive = key === active;
        const isAncestor = !isActive && key === ancestor;
        return (
          <Link
            key={key}
            to={to}
            className={`nav-item${isActive ? ' active' : ''}${isAncestor ? ' ancestor' : ''}`}
            aria-current={isActive ? 'page' : undefined}
          >
            <Icon size={16} strokeWidth={2} aria-hidden="true" />
            {label}
          </Link>
        );
      })}

      <div className="nav-footer">
        <span className="nav-version">{LABELS.version}</span>
      </div>
    </nav>
  );
}
