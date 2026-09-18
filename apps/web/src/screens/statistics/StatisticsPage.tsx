import '../screens.css';
import './statistics.css';
import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { AppShell } from '../../components/AppShell';
import { TopBar } from '../../components/TopBar';
import { LeftNav } from '../../components/LeftNav';
import { BackendDown, LoadingPanel } from '../../components/FetchStates';
import { LABELS, formatInstant, humanizeActivityToken } from '../../lib/labels';
import { StatusChip } from '../../components/StatusChip';
import {
  BarChart3,
  CircleDashed,
  CircleHelp,
  FileJson,
  History,
  Inbox,
  LayoutList,
  List,
  Network,
  Settings,
  Shield,
  ShieldCheck,
  Table2,
} from '../../components/icons';
import { api } from '../../lib/api';
import { useFetch, type FetchState } from '../../lib/useFetch';
import { useWorkspaceScope } from '../../lib/workspaceScope';
import { subscribeWorkspaceRebuilt } from '../../lib/workspaceInvalidation';
import type { RuntimeRecord } from '../../lib/crossRecordTriage';
import type {
  ApiAboutResponse,
  ApiActivitySummary,
  ApiGraphStatus,
  ApiOpenApiResponse,
  ApiSchemaResponse,
} from '../../lib/types';
import {
  PORTAL_METRICS_UNAVAILABLE_COPY,
  PORTAL_METRICS_UNAVAILABLE_TITLE,
  PORTAL_METRIC_VIEWS,
  type PortalMetricsSource,
  unconfiguredPortalMetricsSource,
} from '../../lib/portalMetricsContract';
import {
  ROUTES,
  STATISTICS_TAB_PARAM,
  isStatisticsTab,
  type StatisticsTabId,
} from '../../lib/routes';
import { EVIDENCE_CLASS_CHIP } from '../../lib/status';
import {
  EVIDENCE_CLASSES,
  deriveApiSurface,
  deriveEvidenceTotals,
  deriveExportGate,
  deriveImportTotals,
  deriveMemoryFacts,
  deriveOpenQuestions,
  deriveRecentWork,
  deriveSchemaFacts,
  deriveWorkflowStages,
  deriveWorkspaceTotals,
  type RecentWorkItem,
} from '../../lib/statisticsModel';
import { RovingTabs } from '../settings/apiShared';
import {
  ChartEmpty,
  ChartError,
  ChartLoading,
  ChartSourceUnavailable,
  StatsBarChart,
  StatsColumnChart,
  StatsComparisonRows,
  StatsStackedBar,
  TechnicalDetails,
} from './StatsCharts';
import {
  FigureList,
  MiniBreakdown,
  StatCard,
  StatsSection,
  UnavailableNote,
} from './StatsPrimitives';
import { MyStats } from './MyStats';
import { RecordVerification, useVerificationReport } from './RecordVerification';

/**
 * Statistics — the read-only insights surface, in THREE tabs.
 *
 * ── THE 2026-09-15 REDESIGN, AND THE OBLIGATION IT DISCHARGES ──────────────
 *
 * `UX-017` demoted Statistics out of primary navigation on a MEASUREMENT: the
 * densest screen in the application. The project owner then returned it to the
 * sidebar, and `LeftNav.tsx` records the condition attached to that promotion —
 * *"the density finding is unretracted, and `Statistics` earns this slot only
 * once the page is scientist-first. `UX-017`'s measurement is the acceptance
 * bar, not a historical note."* This file is that work.
 *
 * MEASURED BEFORE, at 1440x900 in Chromium against a populated workspace (five
 * experiments, two import sessions, a verification report present): the one
 * `general` tab was **6,993 px** of main scroll carrying **598** text-bearing
 * elements, of which **303** were readable without opening a disclosure. One
 * section — `Record Verification` — was **3,049 px** of it, and it was the
 * FIRST thing under the page heading, so the opening viewport of a scientist's
 * statistics screen was an engineering QA program over a corpus of official
 * records and not one figure about their own workspace.
 *
 * WHAT CHANGED, in one sentence: the tab a scientist lands on now answers *how
 * much have I recorded, how much is ready, how much still needs me, what
 * changed recently*, and everything that describes the BUILD moved to a tab of
 * its own.
 *
 *   · `general` (**Overview**) — Workspace at a Glance (the headline figures,
 *     now first), Workflow Distribution, Open Questions, Evidence and
 *     Validation, Recent Work, Historical Imports, and the no-analytics
 *     disclosure.
 *   · `mine` (**My Stats**) — unchanged. See `MyStats.tsx`.
 *   · `build` (**Build & Verification**) — Record Verification and its
 *     safeguards, Platform Metrics, the four prose disclosures, and the
 *     Technical Details region (runtime, record schema, Project Memory, API
 *     surface).
 *
 * NOTHING WAS DELETED AND NOTHING BECAME UNREACHABLE. Every section keeps its
 * heading, its id, its states, its copy and its tests; `?tab=build` is a real
 * deep link, and an unrecognised `?tab=` still falls back to `general`, so every
 * existing `/statistics` link resolves exactly where it did.
 *
 * WHY A TAB RATHER THAN A MOVE INTO SETTINGS. The instruction that prompted this
 * was *"move general ISAAC/engineering statistics to Advanced Settings if they
 * are retained at all"*, and the goal it names is that a scientist's screen must
 * not mix "how this build is doing" with "how my science is doing". A tab
 * unmixes them. Physically relocating `RecordVerification` into `SettingsPage`
 * would have added an EIGHTH Settings tab while the same direction asks Settings
 * to shed surface, and would have re-homed roughly forty assertions — including
 * several honesty guards — across two suites for no reader-visible gain over a
 * tab. `Settings → Overview → Advanced & Developer Surfaces` links to
 * `?tab=build`, so the Settings route into it exists.
 *
 * ── THE DENSITY RULE THIS FILE NOW FOLLOWS ─────────────────────────────────
 *
 * ONE LINE PER SECTION BY DEFAULT; the explanation goes behind an accessible
 * disclosure. But the older rule at the foot of this file is UNCHANGED and
 * outranks it: **a sentence that qualifies a specific figure stays beside that
 * figure.** So the non-addability caveats, the truncation note and the
 * suppression disclosures are all still visible, in a compacted form that keeps
 * their meaning; what moved behind a `<summary>` is the longer restatement.
 *
 * COMPOSITION ONLY. Every number on the Overview and Build tabs is produced by
 * `lib/statisticsModel.ts` from one of five read-only GETs
 * (`/api/runtime/records`, `/api/graph/status`, `/api/about`, `/api/openapi`,
 * `/api/schema`); this file fetches them, formats the strings the primitives
 * display, and owns the states. It computes no figure of its own. The My Stats
 * tab reads NOTHING — see `MyStats.tsx`.
 *
 * A SIXTH read, `/api/runtime/verification`, feeds Record Verification alone. It
 * is issued from HERE — by `useVerificationReport`, not by `useFetch` — and its
 * state is handed to the section, which renders it and owns nothing else.
 *
 * TWO reasons for that split, and both are load-bearing. The section is mounted
 * inside the General tab panel, which UNMOUNTS on a switch to My Stats, so state
 * held there would re-read on every return to the tab — for a ~19-second program
 * run that in one of its modes opens a database connection. And the section needs
 * runtime states the shared 3-state hook cannot express: a run still in progress,
 * a result past the backend's own cache lifetime, a re-read in flight, and a
 * re-read that FAILED while a good earlier result is still on screen. Its figures
 * are decoded and derived by `lib/verificationContract.ts` (a report is a wire
 * document, not a projection of the workspace, so it fails closed on a body it
 * cannot read rather than being modelled beside the record derivations).
 *
 * It stays deliberately OUTSIDE the round tracker and the Refresh button below:
 * the report is a cached artifact of a program run, not a live view of this
 * workspace, and it discloses its own age. Re-reading it under a button that
 * announces "N of 5 reads failed" would make that sentence describe a denominator
 * it does not count. The section carries its own controls, whose accessible names
 * are its own so neither collides with this page's Refresh.
 *
 * The five fetches are deliberately INDEPENDENT — that independence is the
 * partial-failure design. One dead endpoint degrades the sections that read it
 * and nothing else; the page never blanks and never substitutes a plausible
 * value for one it did not receive. When (and only when) all five have failed,
 * one page-level failure state replaces the body rather than five identical
 * stacked copies of the same message.
 *
 * ONE SECTION READS NO ENDPOINT AT ALL. `Platform Metrics` renders the state of
 * an adapter boundary that is not connected in this build — see
 * `lib/portalMetricsContract.ts`. It issues no request, so it neither joins a
 * round nor can fail one, and it is present so a reader who wonders why there is
 * no platform-wide figure is told rather than left to infer.
 *
 * Nothing on this surface is telemetry: there is no request, visit, user, IP,
 * latency, uptime or database figure, because no such signal exists in this app
 * to read. Nothing here mutates, validates, exports, or gates anything —
 * `Refresh` issues exactly the same five GETs and nothing else.
 *
 * The "last read" timestamp is captured HERE, on the settle of each read,
 * because the derivations are pure and hold no clock. It is labelled as when
 * this page last read the API, which is the only thing a client-side clock can
 * honestly claim — it is not a server "data last changed" time.
 *
 * TWO clocks, deliberately. `lastSuccess` advances only when a read is
 * FULFILLED; `lastAttempt` advances on every settle, rejection included. The
 * displayed "Last Read From the API" time is `lastSuccess` and nothing else.
 * That separation is load-bearing rather than pedantic, because `Refresh` uses
 * `reloadSilent()`, which on rejection deliberately KEEPS the previous data and
 * stays in the `data` state so the page does not blank: if a rejected read
 * advanced the read clock, an unreachable backend would leave every figure on
 * screen at its old value while the meta row stamped it with the current time —
 * a reading that never happened. When any read in the latest round failed, the
 * page states that, names how many, and leaves the figures' timestamp at the
 * last read that actually returned a body.
 *
 * ── THE TWO TABS, and what belongs in each ─────────────────────────────────
 *
 * `general` holds material that is genuinely workspace- or build-derived:
 * Workspace at a Glance, Workflow Distribution, Evidence and Validation, and the
 * no-analytics disclosure. `mine` holds personal statistics, which this build
 * cannot produce — the honest gate lives in `MyStats.tsx` and is the whole of
 * that tab.
 *
 * ── THE ORDER OF THE GENERAL TAB, AND WHY IT CHANGED ───────────────────────
 *
 * RECORD VERIFICATION IS THE LEDE. It used to be the fifth section, roughly
 * 1,700px down a ~5,500px page at 1440x900 — so the corpus that ran, the
 * official-validation result, the format shadow, the mutation harness and the
 * protected distributions were all below the fold, behind four sections of
 * workspace counts. It now opens the tab, followed immediately by
 * `Verification Safeguards`, which `RecordVerification.tsx` renders as a sibling
 * `h2` (see its header for why that block may not be collapsed).
 *
 * THE SUPPORTING PROSE MOVED THE OTHER WAY, into five collapsed `<details>` at
 * the foot: How Verification Works · How to Interpret Results · Mutation
 * Methodology · Known Limitations · Technical Details. Every one is authored
 * copy that explains something; NOT ONE of them holds a measurement, and that
 * is the rule the split was made on. Where a sentence QUALIFIES a specific
 * figure — the suppression disclosures beside their histograms, the truncation
 * caveat above the glance grid, the "these five may not be added" notes — it
 * stayed where it was, because a caveat moved into a disclosure leaves the
 * visible figure reading as if it had none.
 *
 * WHAT DID NOT MOVE, and each is deliberate:
 *   · `Verification Safeguards` — six measured states, so it is a visible `h2`.
 *   · `About This Run` — measurements plus the report's OWN limitations list.
 *   · the no-analytics section — a governance claim, and `my-stats.test.tsx`
 *     pins that it is not inside a `<details>`. It is REDUCED to one sentence
 *     and the existing Settings link; the paragraph it used to carry about
 *     server-side logging is in `Known Limitations`, not deleted. See
 *     `NoAnalytics` for why that paragraph is load-bearing.
 *
 * BUILD INTERNALS MOVED INTO ONE COLLAPSED REGION. Project Memory's snapshot
 * counts and provenance commits, the API surface breakdown, and the two runtime
 * facts `/api/about` reports (runtime mode and persistence) are properties of the
 * DEPLOYMENT rather than answers to "how is this workspace doing", and they used
 * to sit in the main flow with equal weight to the record figures. They are now
 * inside `Technical Details`, collapsed by default. Nothing was deleted, nothing
 * became unreachable, and no figure changed its label or its scope on the way.
 *
 * The no-analytics section stays in the MAIN flow, uncollapsed. It is a
 * governance claim about what this application does and does not measure, not
 * clutter, and hiding a privacy statement behind a disclosure would weaken it.
 */

/** The one literal used wherever a figure genuinely was not returned. */
const UNAVAILABLE = 'Not Available';

/** Display formatting for a count. The model already guarantees finiteness. */
function count(value: number): string {
  return String(value);
}

/** A count, or the unavailable literal — never `0` standing in for absence. */
function countOrUnavailable(value: number | null): string {
  return value === null ? UNAVAILABLE : String(value);
}

function stringOrUnavailable(value: string | null): string {
  return value === null ? UNAVAILABLE : value;
}

/** A schema version as `v<n>`, or the unavailable literal. Matches how Project
 *  Memory renders the same field, so one number reads one way on both screens. */
function versionOrUnavailable(value: number | null): string {
  return value === null ? UNAVAILABLE : `v${value}`;
}

/**
 * Title Case for an API-reported token, so `synthetic-only` renders as
 * `Synthetic-Only` and `ephemeral` as `Ephemeral`. Only capitalisation changes:
 * the separators, and every character the API sent, are preserved, so this can
 * never turn an unexpected value into a different word.
 *
 * Takes `unknown` and returns `null` for anything that is not a non-empty
 * string. The types say `runtime_mode` and `persistence` are strings; the wire
 * does not. This function used to call `.replace()` on the value directly, and
 * there is NO ErrorBoundary anywhere in this app (`main.tsx` renders `<App/>`
 * bare), so a body carrying `runtime_mode: null` — or a number — threw during
 * render and blanked the WHOLE SPA, not just this card. A malformed field is now
 * an unavailable figure, which is what the rest of this page already does with
 * anything it did not receive; the pre-existing `SettingsPage.tsx` rows degrade
 * the same way by rendering the value verbatim rather than transforming it.
 */
function titleCaseTokenOrNull(value: unknown): string | null {
  if (typeof value !== 'string' || value.length === 0) return null;
  return value.replace(/[A-Za-z0-9]+/g, (word) => word.charAt(0).toUpperCase() + word.slice(1));
}

/* `formatInstant` now comes from `lib/labels` -- it used to be defined here as
   `when.toLocaleString()`, which rendered this page's clock in a different date
   vocabulary from the rest of the app (measured: "9/14/2026, 8:07:08 PM" here
   against "Sep 15, 2026" on an experiment card) and varied with the host locale.
   See its note there, including why `Report Generated` is deliberately left
   verbatim. */

/**
 * One round of reads: how many were STARTED while the page was busy, and how
 * many of those rejected. A page-level Refresh is a round of five; a single
 * section's Retry is a round of one — which is why the denominator is counted
 * rather than hard-coded.
 */
interface Round {
  attempted: number;
  failed: number;
}

const IDLE_ROUND: Round = Object.freeze({ attempted: 0, failed: 0 });

/**
 * What the live region says once a Refresh round drains.
 *
 * Every branch describes THIS round. None of them claims a reading at a time
 * when nothing was read: with a failure in the round, the sentence names how
 * many reads failed and dates the figures to `lastSuccess` — the last read that
 * actually returned a body — instead of to the moment the round ended.
 */
function announceRound(round: Round, lastSuccess: Date | null): string {
  if (round.failed === 0) {
    return lastSuccess === null
      ? 'Refresh finished.'
      : `Refresh finished. The page last read the API at ${formatInstant(lastSuccess)}.`;
  }
  const reads = `${round.failed} of ${round.attempted} reads failed`;
  return lastSuccess === null
    ? `Refresh finished, but ${reads} and no read has succeeded yet, so nothing on this page has been read from the API.`
    : `Refresh finished, but ${reads} — the figures shown were last read at ${formatInstant(lastSuccess)}.`;
}

/**
 * The lead sentence, which names WHICH workspace the figures below describe.
 *
 * IT USED TO NAME THE WRONG ONE, unconditionally: "the current example
 * workspace". The five built-in example records are created ONLY inside a
 * worked-example session — `apps/api/isaac_api/workspace.py:22-32` states it as a
 * structural property ("the NORMAL scope … is **never** auto-seeded: on a fresh
 * deployment it is empty and it stays empty until something explicitly creates a
 * record in it", against "a TUTORIAL scope … The five canonical worked-example
 * records live ONLY here") — so on every ordinary screen that sentence named this
 * scope after content this build never puts there. Same defect class, and same
 * correction, as the mode chip: see `components/TopBar.tsx`, "THE SCOPE DECIDES
 * THE LABEL".
 *
 * KEEP THE QUALIFIER THE QUOTE CARRIES. This conclusion used to read "so on every
 * ordinary screen that sentence asserted contents that are not there" — dropping
 * "on a fresh deployment" and turning a statement about what the build DOES into
 * one about what a directory HOLDS. Nothing here measures contents: there is no
 * startup migration, so a workspace that already held the five still lists them.
 *
 * THE QUOTE ABOVE IS NOW PARTLY STALE, AND THE LEAD IS NOT. `workspace.py`'s
 * "the NORMAL scope ... is **never** auto-seeded: on a fresh deployment it is empty
 * and it stays empty until something explicitly creates a record in it" was quoted
 * here when nothing COULD explicitly create one. `POST /api/experiments` now can,
 * so the second clause is doing real work rather than describing an empty
 * possibility — a fresh ordinary workspace is empty and stays empty *until a reader
 * creates something*, which is the case the quote always allowed for.
 *
 * WHY THE BRANCH IS UNAFFECTED. What this lead names is WHICH WORKSPACE the figures
 * describe, and that is still decided by the scope alone. The reason the ordinary
 * branch must not mention the built-in examples is unchanged: they are created only
 * inside a worked-example session, and the create route refuses a session header
 * with 409 and mints a ULID that can never be one of the five canonical ids. So the
 * ordinary scope can hold a reader's own records and still hold no example — which
 * is exactly what this sentence has always been careful to say.
 *
 * ONE SENTENCE CANNOT BE TRUE OF BOTH SCOPES, which is why this is a branch rather
 * than a rewording. The record read is keyed on the same `scope` value (see D1
 * below), so this page really does describe either workspace: only the session
 * scope holds examples, and only the ordinary scope can be named without them.
 *
 * THE TAB SPLIT DID CHANGE WHAT THIS SENTENCE PROMISES, and the previous version
 * of this comment denied it. It said "the tab split did not change this
 * sentence's subject … everything it lists is on the General ISAAC tab", and then
 * rendered that sentence ABOVE THE TABLIST on both tabs. So at `?tab=mine` the
 * page lead named workflow readiness, evidence, Project Memory and the API
 * surface — four things, none of which is on the panel the reader is looking at —
 * while the comment recorded the choice as deliberate. Both halves were true and
 * their conjunction was the defect: a lead that is correct about the page reads as
 * a promise about the panel, because it sits directly above it.
 *
 * So the lead is now TAB-SCOPED. The reasoning the old comment gave still stands
 * and is preserved: the General lead must not mention personal statistics,
 * because promising personal figures where nothing can qualify them is exactly
 * the claim this build cannot support. What changes is that the My Stats tab gets
 * its own lead instead of inheriting one about a panel it is not showing — and
 * that lead states the tab's condition rather than a figure, in the same terms
 * `MyStats.tsx` and `lib/myStatsContract.ts` use.
 *
 * The WORKSPACE clause stays on the General lead only. On My Stats it would be
 * actively misleading: that tab reads nothing at all, in either scope, so naming
 * a workspace there would imply the gate is a property of which workspace is open.
 *
 * AND IT MUST NOT REPEAT THE PANEL'S OWN SUBTITLE. The first version of the My
 * Stats lead opened with "What this tab will show once records are associated with
 * a signed-in account." — BYTE-IDENTICAL to `MyStats.tsx`'s `stats-mine-gate`
 * section `sub`, which renders a few lines below it in the same viewport. The
 * duplicate is dropped HERE rather than there, because the section subtitle is the
 * component's own self-description and is the only place that sentence appears
 * when `MyStats` is mounted on its own (which two tests do). `the page lead does
 * not repeat a section subtitle` in `my-stats.test.tsx` is the assertion that
 * keeps them distinct.
 *
 * `workspace` is computed AFTER the `mine` branch returns, not before it. It was
 * dead on that path — the My Stats lead names no workspace, by the paragraph above.
 */
function leadSentence(scope: string | null, tab: StatisticsTabId): string {
  if (tab === 'mine') {
    return (
      'This preview cannot tell whose records these are, so this tab states that ' +
      'rather than a figure.'
    );
  }
  if (tab === 'build') {
    /*
     * IT NAMES THE SUBJECT, NOT THE CONTENTS. The old `general` lead was a
     * six-topic table of contents three lines long, which is the form this
     * redesign is removing — and on THIS tab the honest lead is shorter still,
     * because the one thing a reader needs told is that nothing here is about
     * their workspace. `Record verification` is named because it is what opens
     * the tab; `Verification Safeguards` deliberately is not, for the reason
     * the struck version of this comment gave and which is unchanged: that
     * section renders only when a readable report is on screen, so naming it
     * would promise a heading that is legitimately absent.
     */
    return (
      'This tab describes the build, not your records: record verification over a ' +
      'corpus of official records, and what this deployment reports about itself.'
    );
  }
  /*
   * ── THE OVERVIEW LEAD IS ONE CLAUSE, AND WHAT IT DROPPED ─────────────────
   *
   * ~~'Record verification first, then a read-only view of {workspace},
   * workflow readiness, open questions, evidence, the official record schema,
   * Project Memory, and the API surface — and, for platform-wide figures, why
   * none is stated.'~~
   *
   * That sentence was CORRECT about the page it described and is struck rather
   * than reworded, because the reasoning behind it is still live and a future
   * session must not reinstate the form. It listed seven topics, of which four
   * are no longer on this tab at all, and it opened by naming the engineering
   * program that used to sit directly beneath it — the defect this function's
   * own header records, where a lead immediately above a panel reads as a
   * promise about that panel.
   *
   * A table of contents above a tablist is also the wrong instrument: the
   * section headings ARE the contents, they are `region` landmarks, and a
   * reader scanning them does not need them re-listed in prose first. So the
   * lead states the QUESTION this tab answers.
   *
   * THE WORKSPACE CLAUSE IS KEPT, and it is the one part of the old sentence
   * that was load-bearing. It branches for the same reason it always did: only
   * the worked-example scope holds the five built-in examples, and only the
   * ordinary scope can be named without them. See the note above for the full
   * argument, which is unchanged.
   */
  const workspace = scope === null ? 'this workspace' : 'the open worked-example workspace';
  /*
   * `needs attention`, NOT `needs you`. The product does say "3 fields still
   * need you" in the assistant's own sentences, and that phrasing was written
   * here first — but this screen is one tab away from `My Stats`, whose whole
   * content is that this build cannot tell whose records these are. A
   * second-person possessive in the page lead would be the softest possible
   * version of exactly the claim that tab exists to refuse. `Needs Attention`
   * is also already the product's word for this set (`LABELS`), so the lead and
   * the figure below it use one vocabulary.
   */
  return `How much is recorded in ${workspace}, how much is ready, and how much needs attention.`;
}

/**
 * A compact, localized failure note. Neutral rather than alarm-coloured, with
 * the recourse (a real button, keyboard reachable) still offered.
 *
 * THE RULE THIS PAGE FOLLOWS IS ONE ALARM PER FAILED SOURCE, NOT ONE PER PAGE.
 * The five reads are independent, so each dead source states itself ONCE, as a
 * full `BackendDown`, at the first section that reads it; every FURTHER section
 * reading that same source gets this compact note instead, because repeating the
 * identical alarm three times would be noise. Three simultaneously dead sources
 * therefore do produce three alarms — and that is the intent: they are three
 * different failures, and collapsing them into one panel would hide which
 * sources are actually down while the degraded banner above says "3 of 5 reads
 * failed". Only the ALL-FIVE-failed case collapses, into the single page-level
 * `BackendDown`, because there is then nothing left to localize.
 *
 * `/api/about` is the ONE deliberate exception, and it is quieter rather than
 * louder: its failure costs two supporting cards in the collapsed Technical
 * Details region, so it states itself with this note at its only reader. An alarm
 * panel there would out-shout the figures beside it that were read successfully.
 *
 * `/api/schema` WAS A SECOND, UNDOCUMENTED EXCEPTION and is no longer one. It has
 * a single reader, so this rule always prescribed a full `BackendDown` for it, and
 * rendering this note instead meant a dead schema announced nothing at all: this
 * component has no `role`, while `BackendDown` is `role="alert"`. It was not
 * recorded as an exception because it was not a decision. `RecordSchemaFacts` now
 * renders `BackendDown` like the other two sections in its region, and
 * `a dead /api/schema alarms ONCE, like its two siblings in this region` pins the
 * alarm count rather than only the message.
 *
 * (The earlier wording of this comment said the alarm is "stated once" full
 * stop, which read as a page-level promise the code never made — the code and
 * the comment are reconciled here in favour of the code, which is right.)
 */
function SectionUnavailable({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <UnavailableNote>
      <p>{message}</p>
      <div className="stats-retry">
        <button type="button" className="btn btn-secondary" onClick={onRetry}>
          Retry
        </button>
      </div>
    </UnavailableNote>
  );
}

/* ---- the two tabs ------------------------------------------------------ */

/**
 * `General ISAAC` became `Overview`, and the rename is the point rather than a
 * tidy-up: the old label named the SUBJECT (ISAAC in general) on the tab a
 * scientist lands on, which is exactly the mixing the redesign undoes. The tab
 * ID is untouched, so every existing `?tab=general` link is unaffected.
 */
const STATISTICS_TABS: { id: StatisticsTabId; label: string }[] = [
  { id: 'general', label: 'Overview' },
  { id: 'mine', label: 'My Stats' },
  { id: 'build', label: 'Build & Verification' },
];

const tabId = (id: StatisticsTabId) => `statistics-tab-${id}`;
const panelId = (id: StatisticsTabId) => `statistics-tabpanel-${id}`;

export function StatisticsPage() {
  /*
   * THE ACTIVE TAB IS DERIVED FROM THE URL, not held in `useState`.
   *
   * A tab in component state cannot be linked to, bookmarked, reloaded back into,
   * or reached from another surface — and that is not hypothetical here: the
   * Governance & Safety Validator shipped exactly that way and had to be fixed
   * (`GovernancePage.tsx`, "the Validator was unreachable by link"). This uses the
   * same `?tab=` parameter and the same fallback discipline: anything
   * unrecognised — a typo, an empty value, an absent param — resolves to
   * `general` without throwing.
   */
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get(STATISTICS_TAB_PARAM);
  const activeTab: StatisticsTabId = isStatisticsTab(requestedTab) ? requestedTab : 'general';

  function selectTab(tab: StatisticsTabId) {
    const next = new URLSearchParams(searchParams);
    next.set(STATISTICS_TAB_PARAM, tab);
    /* `replace` for a within-page tab click, matching Governance: switching tabs
       is not a destination, and pushing each one would bury the screen the reader
       arrived from behind a stack of Back presses. Copying the existing params
       (rather than building a fresh URL from `ROUTES.statisticsTab`) is what keeps
       any other query parameter on the URL alive. */
    setSearchParams(next, { replace: true });
  }

  /*
   * Round tracking. `useFetch` exposes no completion callback, so the five
   * fetchers are wrapped here: `track` is what `useFetch` actually calls, on the
   * initial load, on `reload()` and on `reloadSilent()` alike, which makes every
   * request's start and settle — and crucially whether it was FULFILLED or
   * REJECTED — observable without issuing a second request. This is the only
   * reason the page holds state at all.
   */
  const [pending, setPending] = useState(0);
  /** When a read last actually RETURNED A BODY. A rejection never advances it. */
  const [lastSuccess, setLastSuccess] = useState<Date | null>(null);
  /** When a read last settled, fulfilled or rejected. */
  const [lastAttempt, setLastAttempt] = useState<Date | null>(null);
  /** How the latest round went: reads started, and how many did not answer. */
  const [round, setRound] = useState<Round>(IDLE_ROUND);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshMessage, setRefreshMessage] = useState('');

  /*
   * The arithmetic lives in refs; the state only MIRRORS them for rendering. Two
   * of the five reads can settle in the same tick, so a functional
   * `setState(n => n + 1)` chain would be correct while anything that had to
   * READ the resulting value in that same tick (which of the round's reads have
   * failed so far) would not.
   */
  const pendingRef = useRef(0);
  const roundRef = useRef<Round>(IDLE_ROUND);

  function settle(fulfilled: boolean): void {
    pendingRef.current -= 1;
    if (!fulfilled) {
      roundRef.current = { ...roundRef.current, failed: roundRef.current.failed + 1 };
    }
    const now = new Date();
    setPending(pendingRef.current);
    setRound(roundRef.current);
    setLastAttempt(now);
    /* ONLY a fulfilled read advances the read clock. A rejection is an attempt,
       and an attempt is not a reading: advancing it here is precisely what let a
       failed Refresh stamp the current time onto figures nobody had just read. */
    if (fulfilled) setLastSuccess(now);
  }

  function track<T>(request: Promise<T>): Promise<T> {
    /* A read that joins an IDLE page opens a new round, so the previous round's
       tally — which described reads this one supersedes — is cleared. */
    if (pendingRef.current === 0) roundRef.current = IDLE_ROUND;
    pendingRef.current += 1;
    roundRef.current = { ...roundRef.current, attempted: roundRef.current.attempted + 1 };
    setPending(pendingRef.current);
    setRound(roundRef.current);
    return request.then(
      (value) => {
        settle(true);
        return value;
      },
      (error: unknown) => {
        settle(false);
        // Rethrown: this wrapper OBSERVES a read, it never swallows one, so
        // `useFetch` still renders its own error state for a hard reload and
        // still keeps the previous data for a silent one.
        throw error;
      },
    );
  }

  /*
   * D1 — the RECORD read is keyed on the workspace scope, the other three are not.
   *
   * `GET /api/runtime/records` is scope-sensitive exactly as the experiment list
   * is: nothing in the ordinary workspace, the five built-in examples inside a
   * worked-example session. With an empty dependency list this page read once, so
   * opening or leaving a session left every record-derived figure on it describing
   * a workspace that was no longer being addressed. This is a LIST-shaped surface,
   * so the right answer is to re-read (unlike the record surfaces, which leave —
   * see `lib/workspaceScope.ts`).
   *
   * The graph status, the About payload, the OpenAPI document and the official
   * record schema are properties of the build rather than of a workspace, so
   * they are deliberately left unkeyed.
   *
   * THE READS ARE NOT KEYED ON THE TAB, and that is deliberate rather than an
   * oversight: they are issued on mount regardless of which tab is showing, so
   * switching tabs never costs a round trip and never resets the read clock. The
   * My Stats tab adds no read of its own — it has nothing to read.
   */
  const scope = useWorkspaceScope();
  const records = useFetch(() => track(api.getRuntimeRecords()), [scope]);
  const graph = useFetch(() => track(api.getGraphStatus()), []);
  const about = useFetch(() => track(api.getAbout()), []);
  const openapi = useFetch(() => track(api.getOpenApi()), []);
  const schema = useFetch(() => track(api.getSchema()), []);
  /*
   * THE SIXTH TRACKED READ, added 2026-09-15 with the Historical Imports
   * figures — and it is TRACKED, unlike the verification read below.
   *
   * It is keyed on `scope` for the same reason the record read is: an import
   * session belongs to a workspace, so leaving or entering a worked-example
   * session changes the answer. The other four are properties of the BUILD and
   * stay unkeyed.
   *
   * IT JOINS THE ROUND, which is what makes `Refresh` honest. The round's
   * denominator has always been COUNTED rather than hard-coded (see `Round`),
   * precisely so a read could be added without the "N of M reads failed"
   * sentence going wrong — an untracked read would have left the page stamping
   * `Last Read From the API` onto a figure that Refresh never re-read.
   */
  const imports = useFetch(() => track(api.listImports()), [scope]);
  /*
   * THE SEVENTH TRACKED READ, added 2026-09-18 with Workspace Activity (`ACT-004`).
   *
   * Keyed on `scope` for the record read's reason: activity is stored inside each
   * experiment's own document, so a worked-example session and the ordinary
   * workspace have entirely different histories.
   *
   * IT JOINS THE ROUND, so `Refresh` re-reads it and the "N of M reads failed"
   * sentence counts it. The denominator has always been COUNTED rather than
   * hard-coded (see `Round`) precisely so a read could be added without that
   * sentence going wrong.
   */
  const activity = useFetch(() => track(api.getActivitySummary()), [scope]);
  /*
   * The SIXTH read, and it is deliberately NOT a `useFetch` and NOT tracked.
   *
   * It lives HERE rather than inside `RecordVerification` because the section is
   * mounted inside the General tab panel, which unmounts when the reader opens
   * My Stats — state held in the section would re-read on every return, and
   * "switching tabs is free" is a rule this page is tested against. This
   * component outlives both panels.
   */
  const verification = useVerificationReport();

  /*
   * ...AND the record read also listens for a workspace REBUILD, which the scope
   * key cannot cover.
   *
   * The guarded reset (`components/ResetDemoDialog.tsx`, in the worked-example bar
   * that `AppShell` mounts on EVERY surface including this one) rewrites the record
   * set without changing the scope — same session, different records. So `[scope]`
   * is unchanged by it and every record-derived figure on this page — the four
   * record cards, the workflow spine, the evidence totals, the export gate — went
   * on describing the records the reset had just discarded. My Experiments already
   * subscribed; this page renders the same workspace-derived data one click away
   * from the control and did not.
   *
   * SILENT on purpose, exactly as the queue's is: the figures stay on screen while
   * the fresh ones arrive, so the page does not blank and the reader does not lose
   * their scroll position. Only the RECORD read is re-issued — the graph status, the
   * About payload, the OpenAPI document and the official record schema are
   * properties of the build and a reset cannot change them.
   */
  const { reloadSilent: reloadRecordsSilent } = records;
  useEffect(() => subscribeWorkspaceRebuilt(reloadRecordsSilent), [reloadRecordsSilent]);

  /*
   * ...AND SO DOES THE ACTIVITY READ, for the same reason and not by analogy: the
   * guarded reset destroys the record documents, and the activity history lives
   * INSIDE those documents (`activity.py` names this as the one act it cannot
   * record, because the row would have to be written to the thing being deleted).
   * So a reset takes every figure in this section to zero, and leaving the old
   * counts on screen would state activity for records that no longer exist.
   * SILENT, as the record read's is.
   */
  const { reloadSilent: reloadActivitySilent } = activity;
  useEffect(() => subscribeWorkspaceRebuilt(reloadActivitySilent), [reloadActivitySilent]);

  /*
   * Did the latest round come back complete? This reads the round's own TALLY,
   * not a comparison of the two clocks: a round whose failing read settles
   * BEFORE its succeeding ones leaves `lastAttempt` equal to `lastSuccess`, so a
   * clock comparison would silently under-report a partial failure.
   */
  const degraded = round.failed > 0;

  // Refresh completes when the round drains. No polling anywhere on this page.
  useEffect(() => {
    if (!refreshing || pending !== 0) return;
    setRefreshing(false);
    setRefreshMessage(announceRound(round, lastSuccess));
  }, [refreshing, pending, round, lastSuccess]);

  function refreshAll() {
    if (refreshing) return;
    // Silent reloads: current data stays on screen, so the page does not blank
    // and scroll position is kept. SEVEN GETs, no write, nothing else.
    records.reloadSilent();
    graph.reloadSilent();
    about.reloadSilent();
    openapi.reloadSilent();
    schema.reloadSilent();
    imports.reloadSilent();
    activity.reloadSilent();
    setRefreshing(true);
    setRefreshMessage('Refreshing — re-reading the API.');
  }

  const allFailed =
    records.status === 'error' &&
    graph.status === 'error' &&
    about.status === 'error' &&
    openapi.status === 'error' &&
    schema.status === 'error' &&
    imports.status === 'error' &&
    activity.status === 'error';

  function retryAll() {
    records.reload();
    graph.reload();
    about.reload();
    openapi.reload();
    schema.reload();
    imports.reload();
    activity.reload();
  }

  return (
    <AppShell
      variant="full"
      topBar={<TopBar variant="home" />}
      sidebar={<LeftNav active="statistics" />}
      mainPad="pad"
      width="wide"
    >
      <div className="placeholder">
        <span className="eyebrow">Workspace Insights</span>
        <h1>Statistics</h1>
        <p>{leadSentence(scope, activeTab)}</p>

        {/* The app's shared page-tab pattern, reused rather than reimplemented:
            `RovingTabs` is the same component the Settings code-sample tabs use
            and the same contract Project Memory's and Governance's local tablists
            implement (automatic activation, Arrow/Home/End, exactly one tab in the
            tab order, `aria-controls` on the selected tab only) — and it wears the
            same `.section-tabs` / `.section-tab` styling those three pages do.
            NOT a fourth paradigm. */}
        <RovingTabs
          className="section-tabs"
          tabClassName="section-tab"
          label="Statistics sections"
          tabs={STATISTICS_TABS}
          active={activeTab}
          onSelect={selectTab}
          tabId={tabId}
          panelId={panelId}
        />
      </div>

      {activeTab === 'general' && (
        <div
          className="statistics"
          id={panelId('general')}
          role="tabpanel"
          aria-labelledby={tabId('general')}
          tabIndex={0}
        >
          <ReadMeta
            lastSuccess={lastSuccess}
            lastAttempt={lastAttempt}
            round={round}
            degraded={degraded}
            allFailed={allFailed}
            refreshing={refreshing}
            refreshMessage={refreshMessage}
            onRefresh={refreshAll}
          />

          {allFailed ? (
            <BackendDown
              error={records.status === 'error' ? records.error : undefined}
              onRetry={retryAll}
            />
          ) : (
            <>
              {/* THE HEADLINE FIGURES ARE THE LEDE. They used to be the fourth
                  thing on this tab, roughly 3,700 px down, behind an
                  engineering QA program. */}
              <WorkspaceGlance records={records} imports={imports} />
              <WorkflowDistribution records={records} />
              <OpenQuestions records={records} />
              <EvidenceAndValidation records={records} />
              <RecentWork records={records} />
              {/* `ACT-004`. It sits beside Recent Work because both answer "what
                  happened lately", and the two are DIFFERENT questions rather than
                  two renderings of one: Recent Work orders records by when their
                  state last changed, this counts the acts their own append-only
                  histories recorded. Each section's `sub` says which. */}
              <WorkspaceActivity activity={activity} />
              <HistoricalImports imports={imports} />
              <NoAnalytics />
            </>
          )}
        </div>
      )}

      {activeTab === 'build' && (
        <div
          className="statistics"
          id={panelId('build')}
          role="tabpanel"
          aria-labelledby={tabId('build')}
          tabIndex={0}
        >
          <ReadMeta
            lastSuccess={lastSuccess}
            lastAttempt={lastAttempt}
            round={round}
            degraded={degraded}
            allFailed={allFailed}
            refreshing={refreshing}
            refreshMessage={refreshMessage}
            onRefresh={refreshAll}
          />

          {allFailed ? (
            <BackendDown
              error={records.status === 'error' ? records.error : undefined}
              onRetry={retryAll}
            />
          ) : (
            <>
              {/* `RecordVerification` renders TWO sections — itself and, when a
                  readable report is on screen, `Verification Safeguards` — so
                  the first two `h2`s of this tab come out of one component. */}
              <RecordVerification verification={verification} />
              <PlatformMetrics />
              {/* ---- the collapsed disclosures, all supporting copy ---------- */}
              <HowVerificationWorks />
              <HowToInterpretResults />
              <MutationMethodology />
              <KnownLimitations />
              <TechnicalDetails
                id="stats-technical"
                title="Technical Details"
                sub="What this build reports about itself: the runtime mode, the served memory snapshot, the official record schema, and the shape of the API."
              >
                <RuntimeFacts about={about} />
                <RecordSchemaFacts schema={schema} />
                <ProjectMemoryFacts graph={graph} />
                <ApiSurface openapi={openapi} />
              </TechnicalDetails>
            </>
          )}
        </div>
      )}

      {activeTab === 'mine' && (
        <div
          className="statistics"
          id={panelId('mine')}
          role="tabpanel"
          aria-labelledby={tabId('mine')}
          tabIndex={0}
        >
          <MyStats />
        </div>
      )}
    </AppShell>
  );
}

/* ---- the read-state header, shared by the two data tabs ---------------- */

/**
 * The read clock, the Refresh control, the round's failure note and the live
 * region — EXTRACTED verbatim from the `general` panel when the Build tab was
 * split out, because both tabs display figures produced by the same six reads
 * and a tab that showed figures without their read state would be the weaker
 * half of the honesty this row exists for.
 *
 * EVERY BRANCH AND EVERY LABEL IS UNCHANGED. `Last Read From the API` is still
 * rendered from `lastSuccess` alone; the `Last Read Attempt` and
 * `Reading From the API` branches are still the two cases where there is a
 * time but no reading, and neither a time nor a reading; and the degraded note
 * is still suppressed when every read failed, because the page-level
 * `BackendDown` already says so and there are then no figures left to caveat.
 *
 * ONE INSTANCE AT A TIME. Only one panel is mounted, so there is exactly one
 * `role="status"` region in the tree — and it is present from that panel's
 * FIRST render, which is the property the original comment insisted on: a live
 * region that appears together with its message is unreliable.
 */
function ReadMeta({
  lastSuccess,
  lastAttempt,
  round,
  degraded,
  allFailed,
  refreshing,
  refreshMessage,
  onRefresh,
}: {
  lastSuccess: Date | null;
  lastAttempt: Date | null;
  round: Round;
  degraded: boolean;
  allFailed: boolean;
  refreshing: boolean;
  refreshMessage: string;
  onRefresh: () => void;
}) {
  return (
    <>
      <div className="stats-meta">
        {/* Three mutually exclusive states, and the labels are not
            interchangeable. `Last Read From the API` is rendered from
            `lastSuccess` ONLY, so it can never date the figures to an attempt
            that returned nothing. With no successful read at all there is a
            time but no reading, so the row says `Last Read Attempt`; before
            the first settle there is neither, and a placeholder there would be
            a fabricated reading time. */}
        {lastSuccess !== null ? (
          <p className="stats-meta-read">
            <span className="stats-meta-label">Last Read From the API</span>
            <time className="mono" dateTime={lastSuccess.toISOString()}>
              {formatInstant(lastSuccess)}
            </time>
          </p>
        ) : lastAttempt !== null ? (
          <p className="stats-meta-read">
            <span className="stats-meta-label">Last Read Attempt</span>
            <time className="mono" dateTime={lastAttempt.toISOString()}>
              {formatInstant(lastAttempt)}
            </time>
          </p>
        ) : (
          <p className="stats-meta-read">
            <span className="stats-meta-label">Reading From the API</span>
          </p>
        )}
        <button type="button" className="btn btn-secondary" onClick={onRefresh} aria-busy={refreshing}>
          {refreshing ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>
      {/* The failure of a round is stated in the page's own words, next to the
          timestamp it qualifies. Suppressed when EVERY read failed, because
          the page-level `BackendDown` below already says so and there are then
          no figures left to caveat. Neutral (`UnavailableNote`), not an alert:
          each affected section carries its own alert and its own Retry. */}
      {degraded && !allFailed && lastAttempt !== null && (
        <div className="stats-block">
          <UnavailableNote>
            <p>
              {round.failed} of {round.attempted} reads failed on the most recent attempt, at{' '}
              {formatInstant(lastAttempt)}.{' '}
              {lastSuccess !== null
                ? 'Nothing was substituted for what did not arrive, so any figure a failed read feeds is either absent or older than the last-read time above.'
                : 'No read has succeeded yet, so nothing on this page has been read from the API.'}
            </p>
          </UnavailableNote>
        </div>
      )}
      {/* Present from FIRST render so a change to its text is what gets
          announced — a live region that appears with its message is
          unreliable. This page never auto-polls, so it only ever speaks in
          response to the reader pressing Refresh. */}
      <p className="sr-only" role="status">
        {refreshMessage}
      </p>
    </>
  );
}

/* ---- 1 · Workspace at a Glance ---------------------------------------- */

/** What `useFetch` hands back: the 3-state union plus its two reload controls. */
type Fetched<T> = FetchState<T> & { reload: () => void; reloadSilent: () => void };

type RecordsBody = { records: RuntimeRecord[]; total: number };
type RecordsFetch = Fetched<RecordsBody>;
type AboutFetch = Fetched<ApiAboutResponse>;
type GraphFetch = Fetched<ApiGraphStatus>;
type OpenApiFetch = Fetched<ApiOpenApiResponse>;
type SchemaFetch = Fetched<ApiSchemaResponse>;
/* The import list is read for its COUNTS only, so the fetch is typed against
   the envelope this page actually consumes rather than against the full
   session-summary shape — `deriveImportTotals` validates what it reads and
   returns `null` for anything it could not read, which is what lets a body
   this build does not recognise degrade to an unavailable figure instead of
   throwing during render. */
type ImportsFetch = Fetched<unknown>;
/* `ACT-004`. TYPED, unlike `ImportsFetch` above, because this body is read by key
   rather than passed to a tolerant derivation — the summary route's shape is
   pinned by `test_activity_summary.py` in both directions. */
type ActivityFetch = Fetched<ApiActivitySummary>;

/**
 * The at-a-glance row — the KPI form, deliberately not a chart.
 *
 * Headline numbers with no shared scale and no ordering between them are a row
 * of stat tiles; a bar chart of "Total / Need Attention / Ready / Exported"
 * would put a total and its own subsets on one axis, which invites reading the
 * parts as a partition of the whole when `Total Records` is the API's workspace
 * denominator and the other three describe only the records received.
 *
 * ── IT IS THE FIRST THING ON THE TAB NOW, AND IT GAINED TWO TILES ─────────
 *
 * `Open Questions` and `Historical Imports` are here because the four
 * questions this tab exists to answer are *how much is recorded, how much is
 * ready, how much still needs attention, and what have I brought in* — and two
 * of those four were answerable only by scrolling to a section further down.
 * Neither tile is a new measurement: `Open Questions` is `deriveOpenQuestions`'
 * own total, restated at the top and still stated in full in its own section,
 * and `Historical Imports` is the import list's own `total`.
 *
 * THE IMPORT TILE COUNTS SESSIONS AND IS NEVER ADDED TO A RECORD COUNT. An
 * import session is a working area; this build creates no experiment from one
 * automatically, so a reader must not add the two tiles together. The tile's
 * own note says `sessions`, and the Historical Imports section below states it
 * again beside the figure.
 *
 * EACH TILE STATES ITS OWN READ STATE. The records read and the imports read
 * are independent, so one dead source empties its own tiles and leaves the
 * others standing — the page's partial-failure rule applied at tile
 * granularity. A tile whose read has not settled says it is reading; a tile
 * whose read failed says the figure is not available. Neither ever shows `0`,
 * which would be a figure nobody measured.
 *
 * The two runtime cards this section used to carry (`Runtime Mode`,
 * `Persistence`) moved into `Technical Details` on the Build tab: they are
 * facts about the build, not about the workspace.
 */
function WorkspaceGlance({ records, imports }: { records: RecordsFetch; imports: ImportsFetch }) {
  return (
    <StatsSection
      id="stats-glance"
      title="Workspace at a Glance"
      sub="Counts for the records this workspace holds right now."
      icon={<LayoutList size={18} strokeWidth={2} aria-hidden="true" />}
    >
      {records.status === 'loading' && <LoadingPanel label="Loading the workspace summary…" />}
      {records.status === 'error' && <BackendDown error={records.error} onRetry={records.reload} />}
      {records.status === 'data' && <GlanceRecordCards body={records.data} imports={imports} />}
    </StatsSection>
  );
}

/**
 * The two runtime facts `/api/about` reports about this build, inside Technical
 * Details.
 *
 * Each is stated only if the response actually carried a usable string. A
 * malformed field becomes the same unavailable literal every other absent figure
 * on this page uses, in the neutral `quiet` tone — not an error, and not a
 * guessed default such as "Synthetic-Only", which would be the one substitution
 * this project forbids outright. Rendering never throws on this body.
 */
function RuntimeFacts({ about }: { about: AboutFetch }) {
  return (
    <StatsSection
      id="stats-runtime"
      title="Runtime"
      sub="What this build reports about its own data regime and storage."
      icon={<Settings size={18} strokeWidth={2} aria-hidden="true" />}
      headingLevel={3}
    >
      {about.status === 'loading' && (
        <LoadingPanel label="Loading the runtime mode and persistence…" />
      )}
      {about.status === 'error' && (
        <SectionUnavailable
          message="This build's runtime mode and persistence could not be read from the API, so neither is stated here."
          onRetry={about.reload}
        />
      )}
      {about.status === 'data' && <GlanceRuntimeCards body={about.data} />}
    </StatsSection>
  );
}

function GlanceRuntimeCards({ body }: { body: ApiAboutResponse }) {
  const runtimeMode = titleCaseTokenOrNull(body.runtime_mode);
  const persistence = titleCaseTokenOrNull(body.persistence);
  return (
    <div className="stats-cards stats-cards-pair">
      <StatCard
        label="Runtime Mode"
        value={runtimeMode ?? UNAVAILABLE}
        note={
          runtimeMode === null
            ? 'the API answered without a usable runtime mode, so none is stated.'
            : 'the data regime this build reports.'
        }
        tone={runtimeMode === null ? 'quiet' : 'neutral'}
      />
      <StatCard
        label="Persistence"
        value={persistence ?? UNAVAILABLE}
        note={
          persistence === null
            ? 'the API answered without a usable storage class, so none is stated.'
            : 'the storage class this build reports.'
        }
        tone={persistence === null ? 'quiet' : 'neutral'}
      />
    </div>
  );
}

function GlanceRecordCards({
  body,
  imports,
}: {
  body: { records: RuntimeRecord[]; total: number };
  imports: ImportsFetch;
}) {
  const totals = deriveWorkspaceTotals(body);
  const questions = deriveOpenQuestions(body.records);

  /* NOT defensive any more, and the comment here said it was. It read "the workspace
     always holds its canonical synthetic records ... so this branch is not reachable
     through the shipped product", which stopped being true when the five examples moved
     into a worked-example session: the ORDINARY scope starts with no records, so opening
     Statistics without a walkthrough open reaches this branch as the normal case. The
     rendered sentence is measured (`totals.total === 0`, derived from the same body the
     cards are built from), so it stays as it is — only the claim about reachability was
     wrong. */
  if (totals.total === 0) {
    return (
      <div className="stats-empty">
        <p className="stats-empty-title">No Records Yet</p>
        <p className="stats-note">
          The workspace holds no records, so there is nothing to summarise here.
        </p>
        <p className="stats-actions">
          <Link to={ROUTES.experiments}>Go to My Experiments</Link>
        </p>
      </div>
    );
  }

  return (
    <>
      {/* ABOVE the grid, and it names the exception explicitly.
          Two things were wrong with this note when it sat BELOW the cards and
          said "every breakdown below describes only the records received":
          `Need Attention`, `Ready to Export` and `Exported` are in the grid the
          note followed, so the very counts most at risk of being read as
          workspace-wide were the ones its own wording excluded — while sitting
          beside a `Total Records` that IS workspace-wide. It now precedes what it
          qualifies and states the one figure it does not apply to. */}
      {body.records.length !== totals.total && (
        <div className="stats-block stats-block-lead">
          <UnavailableNote>
            This page received {count(body.records.length)} of the {count(totals.total)} records the
            API reports. Total Records below is the API&rsquo;s own workspace total; every other
            count on this page — the cards beside it and every breakdown further down — describes
            only the {count(body.records.length)} records received.
          </UnavailableNote>
        </div>
      )}
      <div className="stats-cards stats-cards-glance">
        <StatCard
          label="Total Records"
          value={count(totals.total)}
          note="the workspace total the API reports."
        />
        <StatCard
          label={LABELS.groupNeedsAttention}
          value={count(totals.needsAttention)}
          note="open questions remain."
          tone={totals.needsAttention > 0 ? 'attention' : 'neutral'}
        />
        <StatCard
          label={LABELS.groupReady}
          value={count(totals.readyToExport)}
          note="no open questions and the export dry-run passes."
          tone={totals.readyToExport > 0 ? 'good' : 'neutral'}
        />
        <StatCard
          label="Exported"
          value={count(totals.exported)}
          note="an official record has been written."
        />
        {/* QUESTIONS, not records — the note says so, and the section below
            states the same total with its four record-counted companions. */}
        <StatCard
          label="Open Questions"
          value={count(questions.totalOpenQuestions)}
          note="questions still awaiting an answer, across the records received."
          tone={questions.totalOpenQuestions > 0 ? 'attention' : 'neutral'}
        />
        <ImportSessionsCard imports={imports} />
        {totals.unknownStatus > 0 && (
          <StatCard
            label="Unrecognized Status"
            value={count(totals.unknownStatus)}
            note="a status this page cannot place; counted, not folded into a known bucket."
            tone="attention"
          />
        )}
      </div>
    </>
  );
}

/**
 * The one headline tile fed by a different read, so it states its own state.
 *
 * A failed or unsettled import read must not empty the five record tiles
 * beside it, and it must not render `0` — which would claim the workspace holds
 * no import session when what is true is that this page did not read one. The
 * `quiet` tone is this page's existing not-available treatment and is
 * deliberately not an error treatment: the section below carries the alarm and
 * the Retry for this source.
 */
function ImportSessionsCard({ imports }: { imports: ImportsFetch }) {
  if (imports.status === 'loading') {
    return (
      <StatCard
        label="Historical Imports"
        value="Reading…"
        note="the import sessions have not been read yet."
        tone="quiet"
      />
    );
  }
  if (imports.status === 'error') {
    return (
      <StatCard
        label="Historical Imports"
        value={UNAVAILABLE}
        note="the import sessions could not be read, so no count is stated."
        tone="quiet"
      />
    );
  }
  const totals = deriveImportTotals(imports.data);
  return (
    <StatCard
      label="Historical Imports"
      value={countOrUnavailable(totals.sessions)}
      note="import sessions — working areas, never records."
      tone={totals.sessions === null ? 'quiet' : 'neutral'}
    />
  );
}

/* ---- 2 · Workflow Distribution ---------------------------------------- */

function WorkflowDistribution({ records }: { records: RecordsFetch }) {
  return (
    <StatsSection
      id="stats-workflow"
      title="Workflow Distribution"
      sub="Where the records stand in the five-step workflow. Each record is counted once, at its first unsatisfied step."
      icon={<BarChart3 size={18} strokeWidth={2} aria-hidden="true" />}
    >
      {records.status === 'loading' && (
        <ChartLoading label="Loading the workflow distribution…" />
      )}
      {records.status === 'error' && (
        <ChartError
          message="The workspace records could not be read, so there is no workflow distribution to show."
          onRetry={records.reload}
        />
      )}
      {records.status === 'data' && <WorkflowBars records={records.data.records} />}
    </StatsSection>
  );
}

/**
 * FORM CHOICE — a horizontal bar chart over a shared value axis.
 *
 * The job is comparing counts across up to seven named buckets whose labels are
 * long ("Review Export Readiness"), which is the horizontal bar's exact case: the
 * label gets a line of real text that wraps, and one axis lets the eye compare
 * lengths. A column chart would clip or rotate those names; a single stacked bar
 * would turn five records into five indistinguishable 20% slices and hide the
 * zeros the canonical axis is deliberately keeping.
 *
 * AND IT IS NOT THE ROW OF PROGRESS BARS THIS SECTION USED TO DRAW. The old
 * `StageBars` scaled every bar against the TOTAL, drew no axis and offered no
 * table, so six buckets over five records were six near-empty tracks that could
 * not be read as numbers. The scale is now a nice maximum over the LARGEST
 * bucket, gridlines and tick labels are shared across the rows, and the figure
 * carries both a summary sentence and a data table.
 */
function WorkflowBars({ records }: { records: RuntimeRecord[] }) {
  if (records.length === 0) {
    return (
      <ChartEmpty title="No Records to Distribute">
        No records were returned, so there is no distribution to show. No bar is drawn rather than a
        row of zeros.
      </ChartEmpty>
    );
  }
  const stages = deriveWorkflowStages(records);
  return (
    <StatsBarChart
      caption={`Records by current workflow step, out of ${count(records.length)} counted`}
      rows={stages.map((stage) => ({ key: stage.id, label: stage.label, value: stage.count }))}
      unit="records"
      total={records.length}
      categoryHeader="Workflow Step"
      note="Bars share one scale, marked beneath them. The scale runs to the largest bucket, not to the total, so small differences stay visible."
    />
  );
}

/* ---- 3 · Open Questions ------------------------------------------------ */

/**
 * The one figure the safe record projection carries that this page used to
 * discard: `pending_count`.
 *
 * It is the quantity that DRIVES the status distribution above — `needs_attention`
 * is exactly "open questions remain" — so the page stated the consequence four
 * times and never the cause. Nothing new is fetched for it.
 */
function OpenQuestions({ records }: { records: RecordsFetch }) {
  return (
    <StatsSection
      id="stats-questions"
      title="Open Questions"
      sub="How many answers the records are still waiting for, counted in questions rather than in records."
      icon={<CircleHelp size={18} strokeWidth={2} aria-hidden="true" />}
    >
      {records.status === 'loading' && <LoadingPanel label="Loading the open-question counts…" />}
      {records.status === 'error' && (
        <SectionUnavailable
          message="The workspace records could not be read, so no open-question count is stated."
          onRetry={records.reload}
        />
      )}
      {records.status === 'data' && <OpenQuestionFigures records={records.data.records} />}
    </StatsSection>
  );
}

/**
 * FORM CHOICE — a figure list, for the same reason the export gate is one.
 *
 * These five numbers sit on THREE different axes. `Total Open Questions` counts
 * questions; the next three count records; `Most on One Record` is a maximum,
 * not a tally of anything. Putting them on one shared scale would invite adding
 * a question total to a record count, and a stacked bar would assert a
 * partition that does not exist — a record with a blocked step may also have
 * open questions, and usually does.
 */
function OpenQuestionFigures({ records }: { records: RuntimeRecord[] }) {
  const questions = deriveOpenQuestions(records);

  if (questions.recordsCounted === 0) {
    return (
      <p className="stats-note">
        No records were returned, so there is no open-question count to state.
      </p>
    );
  }

  return (
    <>
      <FigureList
        rows={[
          {
            label: 'Total Open Questions',
            value: count(questions.totalOpenQuestions),
            mono: true,
          },
          {
            label: 'Records With Open Questions',
            value: count(questions.recordsWithOpenQuestions),
            mono: true,
          },
          { label: 'Most on One Record', value: count(questions.mostOnOneRecord), mono: true },
          {
            label: 'Records With a Blocked Step',
            value: count(questions.recordsWithBlockedStep),
            mono: true,
          },
          {
            label: 'Records With a Reopened Step',
            value: count(questions.recordsWithReopenedStep),
            mono: true,
          },
        ]}
      />
      {questions.recordsWithUnreadableCount > 0 && (
        <div className="stats-block">
          <UnavailableNote>
            <p>
              {count(questions.recordsWithUnreadableCount)} of the{' '}
              {count(questions.recordsCounted)} records received carried no usable question count,
              so they contribute nothing to the total above. Nothing was assumed for them, and they
              were not counted as zero.
            </p>
          </UnavailableNote>
        </div>
      )}
      {/*
        ── THE CAVEAT STAYS VISIBLE; THE RESTATEMENT IS DISCLOSED ──────────
        Two paragraphs used to sit here, and between them they said one thing a
        reader must not miss (these five are on different axes and may not be
        added) and several things that explain why. The operative sentence is
        now one line and is still visible, because this file's own rule is that
        a sentence qualifying a specific figure is part of what the figure
        MEANS and may not be collapsed. Everything that merely restates it is
        behind the disclosure, verbatim — nothing was deleted.
      */}
      <p className="stats-note">
        Total Open Questions counts QUESTIONS; the other four count RECORDS. None of the five may be
        added together.
      </p>
      <TechnicalDetails
        variant="prose"
        id="stats-questions-reading"
        title="How These Five Are Counted"
        sub="Which figure counts questions, which count records, and why they do not sum."
      >
        {/* THE RECORD COUNT IS DELIBERATELY NOT REPEATED HERE. The paragraph
            this replaces read "across the {'{'}count(questions.recordsCounted){'}'} records
            received" — a MEASUREMENT, and this file's rule is that a closed
            disclosure may hold prose and never a figure, because a closed
            disclosure is not scanned by axe and is skipped by a reader
            scanning the page. The figure it named is still stated, visibly,
            in the list above. */}
        <p className="stats-note">
          Total Open Questions counts QUESTIONS across the records received. Records With Open
          Questions, Records With a Blocked Step and Records With a Reopened Step count RECORDS.
          Most on One Record is the largest single record&rsquo;s question count, and is neither a
          total nor a share of one.
        </p>
        <p className="stats-note">
          A blocked step and a reopened step are separate axes and overlap each other and the
          question counts, so none of these five may be added together. Each reports only whether a
          record has at least one such step — the workspace projection reduces all five steps to one
          flag apiece, so it does not name the step. No question text, field name or answer is read
          here.
        </p>
      </TechnicalDetails>
    </>
  );
}

/* ---- 4 · Evidence and Validation -------------------------------------- */

function EvidenceAndValidation({ records }: { records: RecordsFetch }) {
  return (
    <StatsSection
      id="stats-evidence"
      title="Evidence and Validation"
      sub="Two separate readings of the same records: how well their fields are supported by evidence, and where each record stands against the export gate."
      icon={<ShieldCheck size={18} strokeWidth={2} aria-hidden="true" />}
    >
      {records.status === 'loading' && (
        <ChartLoading label="Loading evidence and export-gate counts…" />
      )}
      {records.status === 'error' && (
        <ChartError
          message="The workspace records could not be read, so neither the evidence counts nor the export-gate counts can be stated."
          onRetry={records.reload}
        />
      )}
      {records.status === 'data' && (
        <div className="stats-columns">
          <EvidenceGroup records={records.data.records} />
          <ExportGateGroup records={records.data.records} />
        </div>
      )}
    </StatsSection>
  );
}

/**
 * FORM CHOICE — chips for the counts, and ONE stacked bar for the composition.
 *
 * These are two different questions and they are answered separately rather than
 * twice. The chip row states each class's COUNT with the app's own status glyph
 * and colour, which is where those hues belong (a `StatusChip` carries an icon
 * and a label, so colour is never alone). The stacked bar states each class's
 * SHARE of one whole, which is the part-to-whole job and the one thing a row of
 * counts cannot show at a glance: the five classes are mutually exclusive and
 * exhaustive over classified fields, so they genuinely sum to the total.
 */
function EvidenceGroup({ records }: { records: RuntimeRecord[] }) {
  const evidence = deriveEvidenceTotals(records);
  return (
    <div className="stats-group">
      <h3>Evidence Support</h3>
      {evidence.recordsCounted === 0 ? (
        <p className="stats-note">
          No records were returned, so no fields were classified and no count is stated.
        </p>
      ) : (
        <>
          {/* EVIDENCE_CLASSES order is severity precedence, not count order —
              iterated as given, never re-sorted. */}
          <MiniBreakdown
            label="Fields by Evidence-Support Class"
            items={EVIDENCE_CLASSES.map((cls) => {
              const n = evidence[cls.field];
              return {
                key: cls.key,
                chip: <StatusChip kind={EVIDENCE_CLASS_CHIP[cls.key]} />,
                count: n,
                noun: n === 1 ? 'field' : 'fields',
              };
            })}
          />
          {/* A composition needs a whole. With no classified field there is no
              denominator, so the stack is omitted rather than drawn empty — the
              chip row above still states the five zeros as measurements. */}
          {evidence.totalFields > 0 && (
            <div className="stats-block">
              <StatsStackedBar
                caption="Share of classified fields by evidence-support class"
                rows={EVIDENCE_CLASSES.map((cls) => ({
                  key: cls.key,
                  label: evidenceClassLabel(cls.key),
                  value: evidence[cls.field],
                }))}
                total={evidence.totalFields}
                unit="fields"
                categoryHeader="Evidence-Support Class"
                note="Segment shade marks position in the order above — it is not a magnitude and it does not rank severity. The class name carries the meaning."
              />
            </div>
          )}
          <FigureList
            rows={[
              { label: 'Total Fields Counted', value: count(evidence.totalFields), mono: true },
              { label: 'Records Counted', value: count(evidence.recordsCounted), mono: true },
            ]}
          />
          <p className="stats-note">
            Every number in this group counts FIELDS across the records counted, not records. One
            record contributes many fields.
          </p>
        </>
      )}
    </div>
  );
}

/**
 * The evidence-class name as words, for the legend and the data table.
 *
 * The chip row above renders `StatusChip`, which supplies its own label from
 * `LABELS`; a chart legend cannot embed a chip (a swatch keys the ramp step), so
 * it needs the class name as a plain string. Derived from the backend's own
 * histogram key rather than authored per class, so a class added to
 * `EVIDENCE_CLASSES` cannot arrive here with no name at all.
 */
function evidenceClassLabel(key: string): string {
  return key
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

/**
 * The schema's top-level property names as words, for the by-section chart.
 *
 * PRESENTATION ONLY — nothing renames a schema property. `SchemaSectionCount`
 * still carries `section` verbatim from the document (`statisticsModel.ts:449`),
 * the Schema Reference browser still renders these names in the mono face as the
 * exact tokens they are, and the note beneath the chart already points a reader
 * there. What is fixed is that Statistics was rendering them in the PROSE face,
 * under a column called "Section" — so `isaac_record_version`, `record_id`,
 * `record_type`, `record_domain` and `source_type` appeared as if they were the
 * words for these groups, and the chart's `sr-only` summary read them aloud that
 * way to a screen-reader user.
 *
 * The set is not closed — it is whatever the vendored schema declares — so an
 * UNMAPPED PROPERTY FALLS BACK TO ITS OWN NAME rather than to a generated
 * phrase. `evidenceClassLabel` above may de-snake a key mechanically because its
 * key set is the backend's own histogram; doing the same here would invent
 * English for whatever a future schema revision adds, and a name this build has
 * never seen is exactly the thing not to guess at.
 */
const SCHEMA_SECTION_LABELS: Readonly<Record<string, string>> = Object.freeze({
  isaac_record_version: 'ISAAC Record Version',
  record_id: 'Record Identifier',
  record_type: 'Record Type',
  record_domain: 'Record Domain',
  source_type: 'Source Type',
  timestamps: 'Timestamps',
  sample: 'Sample',
  system: 'System',
  context: 'Context',
  measurement: 'Measurement',
  links: 'Links',
  assets: 'Assets',
  descriptors: 'Descriptors',
  computation: 'Computation',
  attribution: 'Attribution',
  tags: 'Tags',
});

function schemaSectionLabel(section: string): string {
  return SCHEMA_SECTION_LABELS[section] ?? section;
}

/**
 * FORM CHOICE — a figure list, and DELIBERATELY NOT A CHART.
 *
 * Every chart form for these five numbers would state something false.
 * `Stale Artifacts` is a SUBSET OF `Exported`, not a fifth bucket, so a stacked
 * bar would imply a partition that does not exist and a bar chart on one shared
 * axis would invite adding the rows up. The four status counts alone would chart
 * honestly, but splitting the five across a chart and a list would separate the
 * very rows whose relationship the copy below has to explain. So they stay a
 * labelled list with the overlap stated in words.
 *
 * "OVERLAPS the four status rows" is what this used to say, and it is looser than
 * the truth in a way that matters: it implies a record could be stale while
 * sitting in `Ready Now` or one of the two blocked rows, which cannot happen.
 * `artifact_state` returns `none` unless `exp.exported()`
 * (`apps/api/isaac_api/dependencies.py:56-57`), and `status()` returns `DONE` if
 * and only if `exported()` is true (`workspace.py:549-566`, checked) — which is
 * also the field `deriveExportGate` buckets on. So stale ⊆ Exported, and the
 * overlap is with exactly ONE row. The decision not to chart is unchanged; only
 * the reason is stated at its real strength.
 */
function ExportGateGroup({ records }: { records: RuntimeRecord[] }) {
  const gate = deriveExportGate(records);
  return (
    <div className="stats-group">
      <h3>Export Gate</h3>
      {records.length === 0 ? (
        <p className="stats-note">
          No records were returned, so there is no export-gate position to state.
        </p>
      ) : (
        <>
          <FigureList
            rows={[
              { label: 'Exported', value: count(gate.exported), mono: true },
              { label: 'Ready Now', value: count(gate.readyNow), mono: true },
              {
                label: 'Blocked by the Export Gate',
                value: count(gate.blockedByGate),
                mono: true,
              },
              {
                label: 'Blocked by Open Questions',
                value: count(gate.blockedByQuestions),
                mono: true,
              },
              { label: 'Stale Artifacts', value: count(gate.staleArtifacts), mono: true },
            ]}
          />
          {/* The SUBSET caveat is the one a reader cannot be allowed to miss —
              adding Stale Artifacts to the four above double-counts a record —
              so it stays visible in one line. The glossary of what each
              position means, and the two supporting facts, are disclosed
              verbatim below. */}
          <p className="stats-note">
            Stale Artifacts is a subset of Exported, not a fifth bucket, so these five may not be
            added together.
          </p>
          <TechnicalDetails
            variant="prose"
            id="stats-gate-reading"
            title="What Each Position Means"
            sub="The definition behind each export-gate row, and what the positions are recomputed from."
          >
            <p className="stats-note">
              Ready Now means no open questions remain and the official export dry-run passes.
              Blocked by the Export Gate means no open questions remain but the dry-run does not
              pass. Blocked by Open Questions means the gate has not been reached yet. Stale
              Artifacts is a subset of Exported — a record whose exported file no longer matches its
              draft is counted in both — which is why these five are not charted on a shared scale.
            </p>
            <p className="stats-note">
              These positions are recomputed from the current drafts on every read and are never
              stored, so there is no saved verdict and no not-yet-run state to report.
            </p>
            <p className="stats-note">Evidence support and schema validation are separate signals.</p>
          </TechnicalDetails>
        </>
      )}
    </div>
  );
}

/* ---- Recent Work ------------------------------------------------------- */

/** How many rows the list shows. A short list is the point: this answers "what
 *  changed lately", and a full inventory is what My Experiments is for. */
const RECENT_WORK_ROWS = 5;

/**
 * The most recently updated records in this workspace.
 *
 * ── WHY THIS SECTION EXISTS ────────────────────────────────────────────────
 *
 * Of the four questions a scientist brings to this screen — how much have I
 * recorded, how much is ready, how much still needs attention, what changed
 * lately — the page answered the first three and not the fourth. Every other
 * section states a COUNT, and a count cannot tell you which record moved.
 *
 * ── WHAT IT IS CAREFUL NOT TO CLAIM ────────────────────────────────────────
 *
 * IT IS NOT "WHAT YOU TOUCHED", and the heading, the supporting line and the
 * column label all say `updated` rather than anything second-person. This build
 * has no trusted user identity and no record carries an author, which is the
 * whole content of the My Stats tab; a "your recent activity" list would be the
 * per-person claim that tab exists to refuse, dressed as a convenience.
 * `statistics-nav.test.tsx` bans six phrasings of exactly that claim across
 * this screen, and this section is inside the scanned tree.
 *
 * IT IS NOT AN ORDERING THE SERVER GAVE. `GET /api/runtime/records` is not
 * sorted by this page's key, so the sort is `deriveRecentWork`'s and is stated
 * as such. A record whose `updated_utc` cannot be read is EXCLUDED and counted
 * rather than placed at either end — putting it last would assert it is the
 * oldest, putting it first that it is the newest, and the response said
 * neither.
 *
 * IT SHOWS ONLY WHAT THE PROJECTION ALREADY SHOWS ELSEWHERE. Title, status and
 * the record's own route are the three fields My Experiments and the
 * cross-record triage chips already render from this same body; no draft value,
 * no evidence and no field name is read here.
 *
 * `updated_utc` IS THE RECORD'S, NOT THIS PAGE'S CLOCK. It is rendered through
 * `formatInstant`, the same formatter the rest of the app uses, so one instant
 * reads one way everywhere.
 */
function RecentWork({ records }: { records: RecordsFetch }) {
  return (
    <StatsSection
      id="stats-recent"
      title="Recent Work"
      sub="The records updated most recently, newest first."
      icon={<List size={18} strokeWidth={2} aria-hidden="true" />}
    >
      {records.status === 'loading' && <LoadingPanel label="Loading the most recent updates…" />}
      {records.status === 'error' && (
        <SectionUnavailable
          message="The workspace records could not be read, so no recent updates are listed."
          onRetry={records.reload}
        />
      )}
      {records.status === 'data' && <RecentWorkList records={records.data.records} />}
    </StatsSection>
  );
}

function RecentWorkList({ records }: { records: RuntimeRecord[] }) {
  const recent = deriveRecentWork(records, RECENT_WORK_ROWS);

  if (recent.items.length === 0) {
    return (
      <p className="stats-note">
        {recent.undatedRecords > 0
          ? `None of the ${count(recent.undatedRecords)} records received carried a readable update time, so no order can be stated for them.`
          : 'No records were returned, so there is nothing recent to list.'}
      </p>
    );
  }

  return (
    <>
      <ul className="stats-recent">
        {recent.items.map((item) => (
          <RecentWorkRow item={item} key={item.experimentId} />
        ))}
      </ul>
      {/* ONE line, and it carries the two things the list cannot show: how many
          records the five were chosen from, and whether any was left out of the
          ordering. Both qualify the list directly, so neither is disclosed. */}
      <p className="stats-note">
        The {count(Math.min(RECENT_WORK_ROWS, recent.items.length))} most recently updated of the{' '}
        {count(recent.datedRecords)} records with a readable update time.
        {recent.undatedRecords > 0
          ? ` ${count(recent.undatedRecords)} more carried none and are not ordered here.`
          : ''}
      </p>
      <p className="stats-actions">
        <Link to={ROUTES.experiments}>Open My Experiments</Link>
      </p>
    </>
  );
}

/**
 * One row: the record's title, its status as the app's own chip, and when it
 * was last updated.
 *
 * The TITLE is the link, not a separate "Open" affordance — it is the row's own
 * name and is what a reader aims at. A row whose projection carried no route is
 * still listed, as plain text: the record exists and was updated, and dropping
 * it would under-report the workspace to hide a missing link.
 */
function RecentWorkRow({ item }: { item: RecentWorkItem }) {
  const when = new Date(item.updatedUtc);
  const readable = Number.isFinite(when.getTime());
  return (
    <li className="stats-recent-row">
      <span className="stats-recent-title">
        {item.navigateTo === null ? item.title : <Link to={item.navigateTo}>{item.title}</Link>}
      </span>
      {/* The status word comes from the app's own vocabulary (`LABELS`), so a
          status reads identically here and on My Experiments. A status this
          page cannot place is rendered as the server's own token rather than
          mapped onto a neighbouring one. */}
      <span className="stats-recent-status">
        <RecordStatusWord status={item.status} />
      </span>
      {readable ? (
        <time className="stats-recent-when mono" dateTime={when.toISOString()}>
          {formatInstant(when)}
        </time>
      ) : (
        <span className="stats-recent-when">{UNAVAILABLE}</span>
      )}
    </li>
  );
}

/**
 * The record status as a word, in a neutral pill — DELIBERATELY NOT a
 * `StatusChip`, and the restraint is the point.
 *
 * `StatusChip`'s kinds are a different vocabulary with reserved meanings:
 * `pass` owns the reserved verdict green, and `signals.css`' own rule is that
 * it is used only for a verdict. `Ready to Export` is a workflow POSITION, not
 * a validation verdict — the export gate section says so in as many words —
 * and painting it in verdict green here would be this row claiming something
 * the deterministic core alone may claim. `mentorReview` and `draft` are
 * likewise about other things. So the status is rendered as its own word.
 *
 * THE WORDS ARE `LABELS`', the same four strings My Experiments' facets use, so
 * there is ONE vocabulary and not a fifth copy authored here. Tone is
 * decoration only: the word is always present and the pill is fully readable
 * with all colour removed.
 *
 * AN UNRECOGNISED STATUS IS RENDERED VERBATIM. Mapping it onto a neighbouring
 * one would assert a position the server did not report, and dropping the row
 * would lose a record the workspace does hold — the same choice
 * `deriveWorkspaceTotals` already makes with its `Unrecognized Status` count.
 */
const RECORD_STATUS_WORD: Readonly<Record<string, string>> = Object.freeze({
  needs_attention: LABELS.groupNeedsAttention,
  in_review: LABELS.groupInReview,
  ready_to_export: LABELS.groupReady,
  done: LABELS.groupDone,
});

function RecordStatusWord({ status }: { status: string }) {
  const known = RECORD_STATUS_WORD[status];
  const tone =
    status === 'needs_attention' ? 'attention' : status === 'ready_to_export' ? 'good' : 'neutral';
  return (
    <span className="stats-recent-state" data-tone={known === undefined ? 'quiet' : tone}>
      {known ?? (status.length > 0 ? status : UNAVAILABLE)}
    </span>
  );
}

/* ---- Workspace Activity (`ACT-004`) ------------------------------------ */

/** How many ranked kinds the two breakdown rows show. FOUR, because this section
 *  earns its place on the Overview tab only by staying compact (`DEC-25`), and the
 *  TRUE number of kinds is stated beside the row when there are more. */
const ACTIVITY_KINDS_SHOWN = 4;

/**
 * The window in words, DERIVED FROM THE PAYLOAD and never from a constant here.
 *
 * `ACT-004`'s sixth rule: it must be impossible for the figure and its label to
 * disagree. The server computes the window at request time and reports `days`
 * beside the count; this turns that same number into the label, so the two cannot
 * come apart. A literal "7" anywhere in this file would be a second source.
 */
function windowPhrase(days: number): string {
  return days === 1 ? 'the Last Day' : `the Last ${count(days)} Days`;
}

/** The unit noun, agreeing with its count. `1 changes` is the kind of small
 *  wrongness that makes a surface read as generated rather than written.
 *
 *  THIS FUNCTION EXISTED AND FOUR VISIBLE SENTENCES DID NOT USE IT, which an
 *  independent review found and which is worse than not having written it: the
 *  docstring above states the rule that the sentences below were breaking, and one
 *  of this slice's own tests was ASSERTING the ungrammatical string. The four are
 *  now built by the four functions beneath this one, so the agreement is in one
 *  place per sentence rather than inline in JSX where it was forgotten. */
function plural(n: number): string {
  return n === 1 ? 'change' : 'changes';
}

/** A per-record count with its noun, as ONE string. */
function changeCount(n: number): string {
  return `${count(n)} ${plural(n)}`;
}

/*
 * THE FOUR SENTENCES THAT AGREE WITH THEIR OWN COUNTS.
 *
 * Each is a whole sentence rather than a noun, because the number governs more than
 * the noun: `1 stored entry ... is counted ... It is kept in its record` moves the
 * verb, the pronoun and the possessive too, and a `plural()` call spliced into JSX
 * fixes only the first of those. Written as functions so each reads as prose and so
 * a test can exercise both arms without rendering a page.
 *
 * `attributedSentence` is UNREACHABLE in this build — `attribution.attributed_events`
 * is structurally 0 while `ACT-005` is blocked on `EXT-01` — and is corrected anyway,
 * because the day that seam is wired is the day the sentence renders, and a defect
 * waiting behind a feature flag is still a defect.
 */

function unreadableEntriesSentence(n: number): string {
  return n === 1
    ? '1 stored entry could not be read and is counted in none of the figures above. It is kept in its record untouched — saying what it contains would mean inventing it.'
    : `${count(n)} stored entries could not be read and are counted in none of the figures above. They are kept in their records untouched — saying what one contains would mean inventing it.`;
}

function unreadableTimestampSentence(n: number): string {
  return n === 1
    ? '1 recorded act carries a time this build could not read. It is in the all-time total and in neither window figure, because placing it inside or outside the window would be a guess.'
    : `${count(n)} recorded acts carry a time this build could not read. They are in the all-time total and in neither window figure, because placing one inside or outside the window would be a guess.`;
}

function furtherKindsSentence(n: number, what: string): string {
  return n === 1
    ? `1 further ${what} is not listed.`
    : `${count(n)} further ${what}s are not listed.`;
}

function attributedSentence(n: number): string {
  return n === 1
    ? '1 of these changes does carry an actor.'
    : `${count(n)} of these changes do carry an actor.`;
}

/**
 * The caption above the changed-record list — WHICH RECORDS, HOW MANY, AND OVER
 * WHAT WINDOW.
 *
 * ── TWO DEFECTS IT CLOSES, BOTH FOUND BY INDEPENDENT REVIEW ────────────────
 *
 * 1. THE LIST NAMED NO WINDOW. Its rows are window-scoped (each count is
 *    `events_in_window`) and it sat under an `All Time` figure, so on a workspace
 *    with 5,000 recorded acts and 12 this week, a list describing the 12 read as a
 *    description of the 5,000. The caption now states the window in every branch —
 *    including the branches that have data, which is the asymmetry that made this
 *    sharp: the zero case already named it.
 *
 * 2. THE EMPTY BRANCH WAS CHOSEN BY `rows.length`. `rows` is the bounded array;
 *    `total` is how many records changed. They differ whenever the list is capped,
 *    so at `record_rows = 0` the section rendered `Records Changed 7` beside
 *    *No record changed* beside *The 0 busiest of the 7*. Latent — `RECORD_ROWS` is
 *    5 and the route exposes no parameter — but it was guarded by a CONSTANT rather
 *    than by the predicate, and the honest predicate is `total`.
 *
 * The `returned === 0 && total > 0` branch is therefore a real sentence rather than
 * an impossible one: it says records changed and none are shown, which is the only
 * truthful thing to say in that state.
 */
function changedCaption(total: number, returned: number, window: string): string {
  const over = `in ${window}`;
  if (total === 0) return `No record changed ${over}.`;
  if (returned === 0) {
    return `${count(total)} ${total === 1 ? 'record' : 'records'} changed ${over}, and none are listed here.`;
  }
  if (total > returned) {
    return `The ${count(returned)} busiest of the ${count(total)} records that changed ${over}. Open a record to see its own history.`;
  }
  return `The ${count(total)} ${total === 1 ? 'record' : 'records'} that changed ${over}.`;
}

/**
 * WORKSPACE ACTIVITY — a summary of the append-only history, never a replacement
 * for it.
 *
 * ── WHAT THIS SECTION IS, AND THE LINE IT MUST NOT CROSS ───────────────────
 *
 * `DEC-44` authorizes exactly this in the same sentence that forbids its opposite:
 * *"Statistics may SUMMARIZE this history; Statistics must never be its source of
 * truth."* So every figure here is a COUNT, the payload carries no event id and no
 * `before`/`after` pair (the route's own shape refuses to), and every record named
 * is a LINK into that record's own Activity workspace, which is where the acts
 * themselves are. A count that advertised content with no control to reach it is
 * the dead end an Impeccable pass over the Activity panel already caught once
 * (`d308b827` — "the count named 150 facts a reader could not reach").
 *
 * ── WHY IT IS HERE AND NOT ON MY STATS ─────────────────────────────────────
 *
 * `MyStats.tsx` enumerates six things that tab must never do, and the first is "no
 * workspace total presented as personal". Every figure below is a WORKSPACE total —
 * there is no per-person activity in this build and there cannot be, because no
 * event carries an actor. Putting it there would have been precisely the relabelled
 * workspace count that file exists to make unrepresentable.
 *
 * ── ONE READ, AND EVERY COUNT COMES FROM THE SERVER ────────────────────────
 *
 * `GET /api/activity/summary`. Not one figure below is computed from a fetched
 * array: `changed_records.total` is how many records changed and
 * `changed_records.returned` is how many rows arrived, and this component renders
 * both rather than `rows.length` — `CLAUDE.md` §11's measured defect. Likewise
 * `actions_with_events` is the true number of distinct kinds, so "and N more" is
 * never derived from the four that are shown.
 *
 * ── THREE QUALIFICATIONS STAY VISIBLE, BESIDE THE FIGURES ──────────────────
 *
 * The density rule sends explanation behind a disclosure; the older rule outranks
 * it — *a sentence that qualifies a specific figure stays beside that figure*. The
 * scope line (these totals cover N records, and when truncated, which N), the
 * unreadable counts, and the attribution sentence are all qualifications of the
 * numbers above them, so all three are rendered in the flow. They are single lines.
 *
 * ── THE FIGURE THIS SECTION REFUSES TO RENDER ──────────────────────────────
 *
 * A number of collaborators. Every event in this build is `unattributed` — no
 * trusted authentication boundary exists, so `ACT-005` is blocked on `EXT-01` and
 * nothing may truthfully name a person. A "0 collaborators" figure would be a claim
 * about the PEOPLE where the true statement is about the DEPLOYMENT, so the wire
 * carries event counts and a (currently empty) list of names, and this section says
 * the true thing in words instead. The sentence is `LABELS.activityActorUnattributed`
 * — the SAME string the record's own Activity panel shows, not a second copy of one
 * claim.
 */
function WorkspaceActivity({ activity }: { activity: ActivityFetch }) {
  return (
    <StatsSection
      id="stats-activity"
      title="Workspace Activity"
      sub="Recorded acts across this workspace's records. Each record's own activity history remains the record of what happened; this only counts it."
      icon={<History size={18} strokeWidth={2} aria-hidden="true" />}
    >
      {activity.status === 'loading' && (
        <LoadingPanel label="Loading the recorded activity…" />
      )}
      {activity.status === 'error' && (
        <SectionUnavailable
          message="The workspace's recorded activity could not be read, so no counts are shown. Each record's own Activity view is unaffected."
          onRetry={activity.reload}
        />
      )}
      {activity.status === 'data' && <ActivityFigures summary={activity.data} />}
    </StatsSection>
  );
}

function ActivityFigures({ summary }: { summary: ApiActivitySummary }) {
  const { window: win, scope, totals, changed_records: changed, attribution } = summary;

  /* THE EMPTY WORKSPACE IS ITS OWN ANSWER, and it is a different one from "nothing
     has been recorded". A workspace with no records has nothing to summarise; a
     workspace whose records have never been touched has been summarised and the
     answer is zero. Rendering a grid of zeros for the first would state a fact about
     activity when the fact is about records. */
  if (scope.experiments_in_scope === 0) {
    return (
      <>
        <p className="stats-note">
          This workspace holds no records yet, so there is no recorded activity to
          summarise.
        </p>
        <p className="stats-actions">
          <Link to={ROUTES.experiments}>Open My Experiments</Link>
        </p>
      </>
    );
  }

  const rankedActions = summary.ranked_actions.slice(0, ACTIVITY_KINDS_SHOWN);
  const rankedChannels = summary.ranked_channels.slice(0, ACTIVITY_KINDS_SHOWN);
  const moreActions = summary.actions_with_events - rankedActions.length;
  /* DERIVED THE SAME WAY as `moreActions`, from the server's own count of distinct
     kinds minus what is shown — so a slice and its disclosure cannot disagree. */
  const moreChannels = summary.channels_with_events - rankedChannels.length;

  return (
    <>
      <FigureList
        rows={[
          {
            label: `Changes in ${windowPhrase(win.days)}`,
            value: count(totals.events_in_window),
            mono: true,
          },
          {
            label: 'Records Changed',
            /* `changed_records.total`, NEVER `rows.length`. The list below is
               capped; this number is not. */
            value: count(changed.total),
            mono: true,
          },
          {
            label: 'Recorded Acts, All Time',
            value: count(totals.events_all_time),
            mono: true,
          },
        ]}
      />

      {/* BOTH BREAKDOWN LABELS NAME THE WINDOW, and both name it EXPLICITLY rather
          than by reference to the label above. `by_action` and `by_channel` are
          incremented only for events inside the window, so a label reading just
          "What Changed" under a `Recorded Acts, All Time` figure invited a reader
          to take a breakdown summing to 12 as a description of 5,000 — found by
          independent review, reproduced in jsdom and over HTTP. The channel row
          could have leaned on "those changes" (it renders only when the action row
          does, because every counted event carries both), but a truth claim that
          depends on two elements staying adjacent is one refactor from being
          false. */}
      {rankedActions.length > 0 && (
        <MiniBreakdown
          label={`What Changed in ${windowPhrase(win.days)}`}
          items={rankedActions.map((entry) => ({
            key: entry.name,
            /* The server's token, turned into words by the ONE humanizer both
               activity surfaces use. No vocabulary is authored here. */
            chip: (
              <span className="stats-recent-state" data-tone="neutral">
                {humanizeActivityToken(entry.name)}
              </span>
            ),
            count: entry.count,
            noun: plural(entry.count),
          }))}
        />
      )}
      {moreActions > 0 && (
        <p className="stats-note">
          {furtherKindsSentence(moreActions, 'kind of change')} Open a record's Activity
          view for its full history.
        </p>
      )}

      {rankedChannels.length > 0 && (
        <MiniBreakdown
          label={`Through Which Surface, in ${windowPhrase(win.days)}`}
          items={rankedChannels.map((entry) => ({
            key: entry.name,
            chip: (
              <span className="stats-recent-state" data-tone="neutral">
                {humanizeActivityToken(entry.name)}
              </span>
            ),
            count: entry.count,
            noun: plural(entry.count),
          }))}
        />
      )}
      {/* THE CHANNEL ROW'S OWN "AND N MORE" GUARD, which did not exist and was safe
          only by COINCIDENCE: `ACTIVITY_CHANNELS` has exactly four members and
          `ACTIVITY_KINDS_SHOWN` is four, so nothing could be dropped. A fifth
          channel would have been silently omitted with no disclosure — the precise
          defect the actions row above already had a guard for. `DEC-44` fixes the
          vocabulary at four, so this is expected never to render; it is here so the
          section does not depend on two unrelated constants agreeing. */}
      {moreChannels > 0 && (
        <p className="stats-note">{furtherKindsSentence(moreChannels, 'surface')}</p>
      )}

      {changed.total > 0 ? (
        <ul className="stats-recent">
          {changed.rows.map((row) => (
            <li className="stats-recent-row" key={row.experiment_id}>
              {/* THE DRILL-DOWN. The title is the link, as it is in Recent Work,
                  and it goes to the record's OWN activity history — the source of
                  truth this section only counts. */}
              <span className="stats-recent-title">
                <Link to={ROUTES.recordView(row.experiment_id, 'activity')}>
                  {row.title}
                </Link>
              </span>
              {/* ONE text node, not a visible number beside an `sr-only` gloss.
                  The first draft split it that way and the window phrase then
                  appeared TWICE in the row's text — once for the eye and once for
                  a screen reader — which is a duplication a `textContent` sweep
                  sees and a reader eventually does too. The window is already
                  stated above the list and again below it, so the row needs only
                  its own count. */}
              <span className="stats-recent-state" data-tone="neutral">
                {changeCount(row.events_in_window)}
              </span>
              <ActivityWhen recordedUtc={row.last_event_utc} />
            </li>
          ))}
        </ul>
      ) : null}
      {/* ONE CAPTION, ALL BRANCHES, AND IT IS CHOSEN BY `total` — never by
          `rows.length`. See `changedCaption` for the two defects that shape it. It
          sits BELOW the list, where the note it replaces sat, so a reader meets the
          rows and then their scope in the same order they always did. */}
      <p className="stats-note">
        {changedCaption(changed.total, changed.returned, windowPhrase(win.days).toLowerCase())}
      </p>

      {/* ── the qualifications, each beside the figures it qualifies ───────── */}
      <p className="stats-note">
        {scope.truncated
          ? `These figures cover the ${count(scope.experiments_summarized)} most recently created of the ${count(scope.experiments_in_scope)} records in this workspace; the rest are not counted here.`
          : `These figures cover all ${count(scope.experiments_summarized)} records in this workspace.`}
      </p>
      {summary.incomplete ? <p className="stats-note">{summary.incomplete.message}</p> : null}
      {totals.unreadable_entries > 0 && (
        <p className="stats-note">
          {unreadableEntriesSentence(totals.unreadable_entries)}
        </p>
      )}
      {totals.events_with_unreadable_timestamp > 0 && (
        <p className="stats-note">
          {unreadableTimestampSentence(totals.events_with_unreadable_timestamp)}
        </p>
      )}
      {/* THE SAME SENTENCE THE RECORD'S OWN ACTIVITY PANEL SHOWS, not a second copy.
          It is rendered unconditionally rather than only when
          `attributed_events === 0`, because it states a property of the DEPLOYMENT:
          a conditional would make its disappearance the signal that somebody had
          been named, which is a thing this build cannot do. */}
      <p className="stats-note">{LABELS.activityActorUnattributed}</p>
      {attribution.attributed_events > 0 && (
        <p className="stats-note">{attributedSentence(attribution.attributed_events)}</p>
      )}
    </>
  );
}

/**
 * The last recorded act's time, formatted by the app's one formatter.
 *
 * A TIME THAT WILL NOT PARSE IS RENDERED AS UNAVAILABLE, never as an invented
 * instant and never as the raw wire string. The server already reports such an
 * event in its own `events_with_unreadable_timestamp` bucket, so this is the
 * client's half of the same rule: a value it cannot read is named as unread.
 */
function ActivityWhen({ recordedUtc }: { recordedUtc: string }) {
  const when = new Date(recordedUtc);
  if (!Number.isFinite(when.getTime())) {
    return <span className="stats-recent-when">{UNAVAILABLE}</span>;
  }
  return (
    <time className="stats-recent-when mono" dateTime={when.toISOString()}>
      {formatInstant(when)}
    </time>
  );
}

/* ---- Historical Imports ------------------------------------------------ */

/**
 * The import sessions this workspace holds.
 *
 * AN IMPORT SESSION IS NOT A RECORD, and that is the one thing this section
 * must not let a reader conclude. A session is a working area holding source
 * entries and the candidates read out of them; `POST .../propose` puts a
 * candidate in front of a person as an OPEN PROPOSAL and writes no value, and
 * nothing in this build creates an experiment from a session automatically. So
 * the figures here are counted in SESSIONS, are never added to a record count,
 * and the note says so beside them rather than in a disclosure.
 *
 * NO FILENAME, DIGEST OR PATH CAN REACH THIS SECTION. `GET /api/imports`
 * serves summaries carrying counts and never the bundle — its own contract
 * description says so — and `deriveImportTotals` reduces what arrives to four
 * integers before this component sees it.
 */
function HistoricalImports({ imports }: { imports: ImportsFetch }) {
  return (
    <StatsSection
      id="stats-imports"
      title="Historical Imports"
      sub="Import sessions in this workspace, counted in sessions rather than in records."
      icon={<Inbox size={18} strokeWidth={2} aria-hidden="true" />}
    >
      {imports.status === 'loading' && <LoadingPanel label="Loading the import sessions…" />}
      {imports.status === 'error' && (
        <BackendDown error={imports.error} onRetry={imports.reload} />
      )}
      {imports.status === 'data' && <ImportFigures body={imports.data} />}
    </StatsSection>
  );
}

function ImportFigures({ body }: { body: unknown }) {
  const totals = deriveImportTotals(body);

  if (totals.sessions === 0 && totals.summariesReceived === 0) {
    return (
      <>
        <p className="stats-note">
          This workspace holds no import session, so there is nothing to summarise here.
        </p>
        <p className="stats-actions">
          <Link to={ROUTES.imports}>{LABELS.navImports}</Link>
        </p>
      </>
    );
  }

  return (
    <>
      <FigureList
        rows={[
          { label: 'Import Sessions', value: countOrUnavailable(totals.sessions), mono: true },
          {
            label: 'Sessions With a Source Recorded',
            value: count(totals.sessionsWithSources),
            mono: true,
          },
          {
            label: 'Sessions With a Candidate Sent to Review',
            value: count(totals.sessionsWithProposals),
            mono: true,
          },
        ]}
      />
      {/* A caveat about the figures, so it is visible rather than disclosed:
          the API's own total and the summaries this page received are separate
          numbers, exactly as `Total Records` and the records received are. */}
      {totals.sessions !== null && totals.sessions !== totals.summariesReceived && (
        <div className="stats-block">
          <UnavailableNote>
            This page received {count(totals.summariesReceived)} of the{' '}
            {count(totals.sessions)} import sessions the API reports. The two counts beneath
            Import Sessions describe only the summaries received.
          </UnavailableNote>
        </div>
      )}
      <p className="stats-note">
        These count SESSIONS, never records: a session is a working area, and nothing here creates
        an experiment or writes a value. A candidate sent to review is an open proposal awaiting a
        person&rsquo;s judgement.
      </p>
      <p className="stats-actions">
        <Link to={ROUTES.imports}>{LABELS.navImports}</Link>
      </p>
    </>
  );
}

/* ---- Technical Details · Record Schema --------------------------------- */

/**
 * The shape of the official ISAAC record schema this build validates against.
 *
 * A BUILD PROPERTY, not a workspace one, which is why it sits inside Technical
 * Details beside the runtime facts and the API surface: the numbers do not
 * change when a record does. Every figure is a count of the schema's own
 * structure — no record is read to produce any of them.
 */
function RecordSchemaFacts({ schema }: { schema: SchemaFetch }) {
  return (
    <StatsSection
      id="stats-schema"
      title="Record Schema"
      sub="The shape of the official record schema this build validates against, and the controlled vocabularies served beside it."
      icon={<Table2 size={18} strokeWidth={2} aria-hidden="true" />}
      headingLevel={3}
    >
      {schema.status === 'loading' && <LoadingPanel label="Loading the official record schema…" />}
      {/*
        `BackendDown`, MATCHING ITS TWO SIBLINGS IN THIS REGION, not the compact
        note it used to render.

        `/api/schema` has exactly ONE reader, so the rule stated on
        `SectionUnavailable` — a full alarm at the first section that reads a dead
        source, the compact note only at FURTHER readers — already prescribed this.
        The compact note here was a violation of that rule rather than an exception
        to it, and it had a consequence beyond tidiness: `SectionUnavailable` renders
        no `role`, so a dead `/api/schema` announced nothing to a screen reader while
        the banner above stated "1 of 5 reads failed". `/api/about`'s exception does
        not transfer — its rationale is that its two cards sit BESIDE record cards
        that were read successfully, whereas a dead schema empties this whole section
        including its chart, exactly as a dead `/api/graph/status` empties Project
        Memory and a dead `/api/openapi` empties API Surface.
      */}
      {schema.status === 'error' && <BackendDown error={schema.error} onRetry={schema.reload} />}
      {schema.status === 'data' && <SchemaBody body={schema.data} />}
    </StatsSection>
  );
}

/**
 * FORM CHOICE — figures for the totals, comparison rows for the sections.
 *
 * The totals sit on different axes (sections, fields, rules, files, terms) and
 * are a labelled list for the same reason the export gate is. The section
 * breakdown IS one whole divided into named parts whose labels come from the
 * document and can be any length, which is the compact comparison row's case —
 * the same form the API surface uses for its groups, and for the same reason.
 */
function SchemaBody({ body }: { body: ApiSchemaResponse }) {
  const facts = deriveSchemaFacts(body);

  if (facts.totalFields === 0) {
    return (
      <>
        <p className="stats-note">
          The schema this build served declares no fields, so there is no breakdown to show.
        </p>
        <p className="stats-actions">
          <Link to={`${ROUTES.governance}?tab=schema`}>Open Schema Reference</Link>
        </p>
      </>
    );
  }

  return (
    <>
      <FigureList
        rows={[
          { label: 'Schema Title', value: stringOrUnavailable(facts.schemaTitle) },
          { label: 'Schema Version', value: stringOrUnavailable(facts.schemaVersion), mono: true },
          /* "FIELDS", NOT "SECTIONS". These two labelled the schema's top-level
             properties as sections, and on the real document 5 of the 6 the root
             requires are scalar strings — `isaac_record_version`, `record_id`,
             `record_type` and so on — which are fields by any reading and are not
             sections of anything. The model's own field names (`topLevelFields`,
             `requiredTopLevelFields`) already said so. The chart below still says
             "section", correctly: it groups each top-level field WITH ITS
             DESCENDANTS, which is what makes a scalar field a one-field group. */
          { label: 'Top-Level Fields', value: count(facts.topLevelFields), mono: true },
          { label: 'Fields at Every Depth', value: count(facts.totalFields), mono: true },
          {
            label: 'Required Top-Level Fields',
            value: count(facts.requiredTopLevelFields),
            mono: true,
          },
          {
            label: 'Fields With Enumerated Values',
            value: count(facts.fieldsWithEnumeratedValues),
            mono: true,
          },
          { label: 'Conditional Rules', value: count(facts.conditionalRules), mono: true },
          { label: 'Vocabulary Files', value: count(facts.vocabularyFiles), mono: true },
          { label: 'Vocabulary Terms', value: count(facts.vocabularyTerms), mono: true },
        ]}
      />
      <div className="stats-block">
        <StatsComparisonRows
          caption="Fields by top-level section, in the schema's own declaration order"
          rows={facts.bySection.map((row) => ({
            key: row.section,
            label: schemaSectionLabel(row.section),
            value: row.count,
          }))}
          unit="fields"
          total={facts.totalFields}
          categoryHeader="Section"
        />
      </div>
      <p className="stats-note">
        Required Top-Level Fields counts what the schema&rsquo;s own root requires. Requiredness
        deeper in the document is not added to it: a field marked required inside an optional
        section is required only once that section is present, so a single total across depths would
        state an obligation the schema does not impose. Fields at Every Depth is counted through the
        schema&rsquo;s <span className="mono">properties</span> and array items; fields declared only
        inside a <span className="mono">oneOf</span> alternative are not listed, so this is a count of
        the fields this view can enumerate rather than of every field the document can express. The
        Schema Reference browser walks the document the same way, so the two screens state the same
        number.
      </p>
      <p className="stats-note">
        Vocabulary Terms counts the entries in the vocabulary files this build serves alongside the
        schema. It is a property of those files, not a measurement of any stored data.
      </p>
      <p className="stats-actions">
        <Link to={`${ROUTES.governance}?tab=schema`}>Open Schema Reference</Link>
      </p>
    </>
  );
}

/* ---- Technical Details · Project Memory -------------------------------- */

function ProjectMemoryFacts({ graph }: { graph: GraphFetch }) {
  return (
    <StatsSection
      id="stats-memory"
      title="Project Memory"
      sub="What the served memory snapshot reports about itself. This is the memory and query plane — it is never the authority on record validity."
      icon={<Network size={18} strokeWidth={2} aria-hidden="true" />}
      headingLevel={3}
    >
      {graph.status === 'loading' && <LoadingPanel label="Loading Project Memory provenance…" />}
      {graph.status === 'error' && (
        <BackendDown error={graph.error} onRetry={graph.reload} />
      )}
      {graph.status === 'data' && <MemoryBody graph={graph.data} />}
    </StatsSection>
  );
}

function MemoryBody({ graph }: { graph: Parameters<typeof deriveMemoryFacts>[0] }) {
  const facts = deriveMemoryFacts(graph);
  const noCounts =
    facts.servedFiles === null &&
    facts.concepts === null &&
    facts.communities === null &&
    facts.nodes === null &&
    facts.edges === null;

  return (
    <>
      <FigureList
        rows={[
          {
            // The served PATH SET (`file_count`), NOT the content manifest —
            // the two are different sets and the label must name which one.
            // Project Memory states the SAME field under this SAME label
            // (`ProjectMemory.tsx` `MemoryFigures`); one number, one name.
            label: 'Served Files (Path Set)',
            value: countOrUnavailable(facts.servedFiles),
            mono: true,
          },
          { label: 'Concepts', value: countOrUnavailable(facts.concepts), mono: true },
          { label: 'Communities', value: countOrUnavailable(facts.communities), mono: true },
          { label: 'Nodes', value: countOrUnavailable(facts.nodes), mono: true },
          { label: 'Edges', value: countOrUnavailable(facts.edges), mono: true },
          {
            // Same label AND same rendering as Project Memory's own row for this
            // field (`ProjectMemory.tsx` `MemoryFigures`): a `v` prefix, so a
            // schema version in a column of counts cannot be read as a count.
            label: 'Snapshot Schema Version',
            value: versionOrUnavailable(facts.snapshotSchemaVersion),
            mono: true,
          },
        ]}
      />
      {noCounts && (
        <div className="stats-block">
          <UnavailableNote>
            This build served no snapshot overview, so none of the graph counts above is available.
            No count is inferred and none is shown as zero.
          </UnavailableNote>
        </div>
      )}

      {facts.freshness === 'point_in_time' && (
        <>
          <p className="stats-note">
            <span className="stats-freshness-label">Point-in-Time Snapshot</span> — the snapshot was
            built from a different commit than the one this build reports, so it describes the
            repository at that earlier point and not necessarily the running app.
          </p>
          <FigureList
            rows={[
              {
                label: 'Source Graph Commit',
                value: stringOrUnavailable(facts.sourceGraphCommit),
                mono: true,
              },
              {
                label: 'Deployed App Commit',
                value: stringOrUnavailable(facts.deployedAppCommit),
                mono: true,
              },
            ]}
          />
        </>
      )}
      {facts.freshness === 'current' && (
        <p className="stats-note">
          <span className="stats-freshness-label">Built From This Commit</span> — the snapshot's
          source commit matches the commit this build reports.
        </p>
      )}
      {facts.freshness === 'undetermined' && (
        <div className="stats-block">
          <UnavailableNote>
            Whether this snapshot describes the running build cannot be determined in this
            environment: the two commits needed for the comparison were not both reported. This is
            not a claim that the snapshot is current.
          </UnavailableNote>
        </div>
      )}

      <p className="stats-actions">
        <Link to={ROUTES.memory}>Open Project Memory</Link>
      </p>
    </>
  );
}

/* ---- Technical Details · API Surface ----------------------------------- */

function ApiSurface({ openapi }: { openapi: OpenApiFetch }) {
  return (
    <StatsSection
      id="stats-api"
      title="API Surface"
      sub="The shape of the API this build documents, read from its own generated contract. These are the operations that exist — not traffic, which is not recorded anywhere."
      icon={<FileJson size={18} strokeWidth={2} aria-hidden="true" />}
      headingLevel={3}
    >
      {openapi.status === 'loading' && <LoadingPanel label="Loading the API contract…" />}
      {openapi.status === 'error' && (
        <BackendDown error={openapi.error} onRetry={openapi.reload} />
      )}
      {openapi.status === 'data' && <ApiSurfaceBody doc={openapi.data} />}
    </StatsSection>
  );
}

/**
 * FORM CHOICE — two different forms for two differently-shaped breakdowns of the
 * same contract, because the shape of the LABELS decides the form.
 *
 * By METHOD: at most five categories whose names are three to six characters
 * (`GET`, `DELETE`). Columns are right — the names sit under the marks with no
 * wrapping, rotation or truncation, and heights compare against one baseline.
 * Only the sole maximum is labelled on its cap; the y-axis carries the rest
 * approximately and the table exactly.
 *
 * By GROUP: as many categories as the document has tags, with names that come
 * from the contract itself and can be anything. Compact comparison rows are
 * right — the name gets a wrapping line of real text, and the tracks stay short
 * enough that ten groups still fit without a per-row axis strip.
 */
function ApiSurfaceBody({ doc }: { doc: Parameters<typeof deriveApiSurface>[0] }) {
  const surface = deriveApiSurface(doc);

  if (surface.operationCount === 0) {
    return (
      <>
        <p className="stats-note">
          The contract this build served documents no operations, so there is no breakdown to show.
        </p>
        <p className="stats-actions">
          <Link to={ROUTES.settingsTab('explorer')}>Open Endpoint Explorer</Link>
        </p>
      </>
    );
  }

  return (
    <>
      <FigureList
        rows={[
          {
            label: 'Documented Operations',
            value: count(surface.operationCount),
            mono: true,
          },
          { label: 'Groups', value: count(surface.groupCount), mono: true },
        ]}
      />
      <div className="stats-block">
        <StatsColumnChart
          caption="Documented operations by HTTP method"
          rows={surface.byMethod.map((row) => ({
            key: row.method,
            label: row.method.toUpperCase(),
            value: row.count,
          }))}
          unit="operations"
          total={surface.operationCount}
          categoryHeader="HTTP Method"
        />
      </div>
      <div className="stats-block">
        <StatsComparisonRows
          caption="Documented operations by group, in the contract's own tag order"
          rows={surface.byGroup.map((row) => ({
            key: row.group,
            label: row.group,
            value: row.count,
          }))}
          unit="operations"
          total={surface.operationCount}
          categoryHeader="Group"
        />
      </div>
      <p className="stats-actions">
        <Link to={ROUTES.settingsTab('explorer')}>Open Endpoint Explorer</Link>
      </p>
    </>
  );
}

/* ---- 5 · Platform Metrics (an inactive adapter boundary) --------------- */

/**
 * The wider-platform figures this deployment has no source for.
 *
 * THE SECTION EXISTS BECAUSE THE ABSENCE NEEDS STATING. Every figure above is
 * scoped to this workspace or this build, and a reader who wants to know how
 * ISAAC is doing across the platform would otherwise conclude either that the
 * question is unasked or that the answer is on some other screen. It is neither.
 *
 * NOTHING HERE ISSUES A REQUEST. The state is read from
 * `lib/portalMetricsContract.ts`, whose only implementation holds no URL, no
 * host and no token, and this component does not join the page's fetch rounds —
 * so it can neither slow a Refresh nor be counted among reads that failed.
 *
 * The state is PROBED THROUGH THE REAL BOUNDARY (`platformRecordTotal()`) rather
 * than hard-coded, so wiring a source later changes this section's behaviour
 * instead of requiring it to be rewritten. Only `unavailable` has a rendering:
 * this build's source cannot return `ready` or `loading`, and writing branches
 * for payloads no adapter produces is how a placeholder chart gets shipped.
 */
function PlatformMetrics({
  source = unconfiguredPortalMetricsSource,
}: {
  source?: PortalMetricsSource;
}) {
  const probe = source.platformRecordTotal();

  return (
    <StatsSection
      id="stats-platform"
      title="Platform Metrics"
      sub="Figures about the wider ISAAC platform, as distinct from this workspace and this build."
      icon={<CircleDashed size={18} strokeWidth={2} aria-hidden="true" />}
    >
      <ChartSourceUnavailable title={PORTAL_METRICS_UNAVAILABLE_TITLE}>
        {probe.status === 'unavailable'
          ? PORTAL_METRICS_UNAVAILABLE_COPY[probe.reason]
          : /* Reachable only if a source is wired that this build does not ship.
               It states the state it received and draws nothing, which is the
               only honest thing to do with a payload no view here can read. */
            `The platform metrics source reported "${probe.status}", and this page has no view built for it, so nothing is shown.`}
      </ChartSourceUnavailable>
      <ul className="stats-plan-grid">
        {PORTAL_METRIC_VIEWS.map((view) => (
          <li className="stats-plan-card" key={view.id}>
            <h3 className="stats-plan-title">{view.title}</h3>
            <p className="stats-plan-desc">{view.description}</p>
          </li>
        ))}
      </ul>
      <p className="stats-note">
        Each description names the unit it would count. None of these figures is being withheld from
        you and none of them is zero — this application has no source to read one from, so it states
        that instead of a number.
      </p>
    </StatsSection>
  );
}

/* ---- No analytics ------------------------------------------------------ */

/**
 * Absence of telemetry is a PRIVACY FEATURE, so this section is informational,
 * not a failure: neutral colours, no alert role, no warning glyph, no empty
 * chart, no zero-filled placeholder. The shield is the privacy mark this app
 * already uses, and it is decorative.
 *
 * IT STAYS IN THE MAIN FLOW. Project Memory and the API surface moved into a
 * collapsed Technical Details region; this did not, because it is a claim about
 * what the application measures and stores, and a governance claim behind a
 * disclosure is a weaker claim. It sits directly after the record figures, where
 * a reader wondering why there is no traffic figure will look.
 *
 * SCOPE IS THE WHOLE POINT of the copy below. An earlier version of this section
 * claimed the preview "does not track visits, users, source IPs, request
 * history, or behavioral analytics" — and the last three clauses were not the
 * app's to make. `Dockerfile` starts `uvicorn` with default settings, so the web
 * server writes an access line (client address, method, path, status) for every
 * request; `apps/api/isaac_api/routes.py` writes metadata-only per-operation
 * outcome lines, which is request history by any reasonable reading; and a
 * hosted deployment sits behind an identity gateway whose logs the browser
 * cannot see at all. So every claim here is scoped to THIS APPLICATION — what it
 * ships, measures and stores — and server-side logging is named rather than
 * denied. The narrower privacy wording this app had already vetted lives in
 * `lib/settingsContent.ts` (`no-telemetry`, `no-real-experiment-data`); this
 * section states the same boundary for the page's own subject and links there
 * instead of authoring a third variant.
 *
 * ── REDUCED TO ONE SENTENCE, AND THE OTHER PARAGRAPH RELOCATED ─────────────
 *
 * Statistics is not where this application's privacy policy is explained — that
 * is `Settings › Data & Privacy`, which this section has always linked to. What
 * has to stay HERE is the one claim a reader of this page needs: why there is no
 * traffic figure on a page of figures. So the body is now that single sentence.
 *
 * THE SERVER-SIDE-LOGGING PARAGRAPH WAS NOT DELETED. It is the CORRECTION of a
 * claim this section shipped falsely once already, and dropping it would restate
 * a narrow truth in a place where it reads as a wide one. It is rendered in full,
 * verbatim, in `KnownLimitations` below, and the section's own supporting line
 * points there — so the scope is disclosed at the claim and stated in full one
 * disclosure away. `statistics-page.test.tsx` pins both halves, in both places.
 *
 * The section stays OUT of any `<details>` regardless: `my-stats.test.tsx`
 * asserts `section[aria-labelledby="stats-no-analytics"]` has no `<details>`
 * ancestor, and a governance claim behind a disclosure is a weaker claim.
 */
function NoAnalytics() {
  return (
    <StatsSection
      id="stats-no-analytics"
      title="This Application Collects No Analytics"
      sub="Scoped to this application — what it ships, measures and stores. Server-side logs belong to whoever operates the deployment; what this page can and cannot say about them is stated under Known Limitations, on the Build & Verification tab."
      icon={<Shield size={18} strokeWidth={2} aria-hidden="true" />}
    >
      <p className="stats-note">
        This application ships no analytics SDK, no tracking pixel, and makes no third-party
        network request; it stores no per-user or per-operation metric, which is why this page
        shows no figure for visits, traffic or request volume — no such figure exists in this app
        to read.
      </p>
      <p className="stats-actions">
        <Link to={ROUTES.settingsTab('privacy')}>Open Data &amp; Privacy Settings</Link>
        {/*
          ── THE POINTER IS NOW A LINK, BECAUSE THE TARGET MOVED TABS ────────
          The supporting line above used to end "under Known Limitations
          BELOW", and that word was true of a one-tab page. `Known Limitations`
          is now on `?tab=build`, so "below" would have been false — and this
          is the one pointer on the page that must not go wrong: the paragraph
          it points at is the CORRECTION of a claim this section shipped
          falsely once (see the header), so a reader who cannot reach it is
          left with the narrow claim and nothing to scope it.
        */}
        <Link to={ROUTES.statisticsTab('build')}>Read Known Limitations</Link>
      </p>
    </StatsSection>
  );
}

/* ---- the collapsed disclosures ---------------------------------------- */

/*
 * FIVE `<details>`, closed by default, at the foot of the General tab.
 *
 * ── THE RULE THAT DECIDES WHAT MAY GO IN ONE ───────────────────────────────
 *
 * PROSE MAY BE COLLAPSED; A MEASUREMENT MAY NOT. Everything below is authored
 * copy that explains how something works or what it does not establish. Nothing
 * below states a count, a state, a timestamp or any other figure — because a
 * disclosure is not scanned by axe when it is closed, is skipped by a reader
 * scanning headings, and reads as optional. Collapsing a finding is hiding it.
 *
 * That rule is why `Verification Safeguards` is a visible `h2` section
 * (`RecordVerification.tsx`) and why `About This Run` stays inside Record
 * Verification: six tri-state readings and eleven provenance rows respectively.
 *
 * ── AND WHY A CAVEAT STAYS BESIDE ITS FIGURE ───────────────────────────────
 *
 * A sentence that qualifies a specific number is not "supporting prose" — it is
 * part of what that number means. The histogram suppression disclosures, the
 * truncation caveat above the glance grid, the "these five may not be added
 * together" notes and the mutation panel's "reported below rather than promised
 * here" all stayed in place for that reason. Moving them here would leave the
 * visible figure reading as complete.
 *
 * They are `TechnicalDetails variant="prose"`, which is the SAME component the
 * build-internals region uses — one disclosure treatment on the surface — with a
 * different root class so the suites that address `details.stats-technical`
 * through strict-mode locators still resolve to exactly one element. See
 * `StatsCharts.tsx`.
 */

/**
 * What the verification program actually does, moved out of the section's own
 * supporting line (which used to carry all three programs in one 60-word
 * sentence, directly above the corpus banner) and out of the re-read control
 * (which carried the cache-and-polling paragraph).
 */
function HowVerificationWorks() {
  return (
    <TechnicalDetails
      variant="prose"
      id="stats-how-verification"
      title="How Verification Works"
      sub="What the program at the top of this page runs, and how its result reaches this screen."
    >
      <p className="stats-note">
        An automated program runs three things over a corpus of official ISAAC records: ISAAC&rsquo;s
        own official-schema validator; a stricter format-aware second validator; and a harness that
        injects small deterministic changes into a copy of each record and checks that the validator
        reacts the way that change was designed to make it react. The report it produces is
        aggregate: it carries no record identifier, title, field value, evidence entry or per-record
        outcome, so there is no slot on this screen for one.
      </p>
      <p className="stats-note">
        This report is produced by a program run that is kept off the request path, so it is read as
        a cached result and states its own age. Nothing on this screen polls: it is read once when
        the page opens, and again only when the control in Record Verification is pressed.
      </p>
      <p className="stats-note">
        Two corpora can produce this same report, and they carry very different weight — a public
        reference preflight over already-published upstream example records, and an authorized
        sample of the records this application holds. Which one ran is stated at the top of Record
        Verification before any count — as a product name AND as the value the report itself sent,
        verbatim — and a value this build does not recognise becomes its own label rather than
        being mapped onto either shipped one.
      </p>
    </TechnicalDetails>
  );
}

/**
 * How to read what the figures above mean — the reading rules that were
 * previously only implicit, or stated once beside one chart and nowhere else.
 *
 * Every sentence here restates something the visible page already carries; none
 * of them is the only place a caveat appears.
 */
function HowToInterpretResults() {
  return (
    <TechnicalDetails
      variant="prose"
      id="stats-interpretation"
      title="How to Interpret Results"
      sub="The reading rules behind the figures above — what may be compared, what may not be added, and what a zero means."
    >
      <p className="stats-note">
        The two validators are never added together. Each states its own number of records, and the
        shared scale in the side-by-side chart runs to the largest single count rather than to any
        total. The official validator is the authority; the format shadow is advisory, reports
        issues the official schema tolerates, and gates nothing.
      </p>
      <p className="stats-note">
        A zero is the good reading wherever this page counts things that went wrong. The harness
        self-checks and the two statement counts under Verification Safeguards all count events
        nobody wants, so a zero there is stated calmly and affirmatively rather than as an empty
        panel.
      </p>
      <p className="stats-note">
        A safeguard that does not apply is not a safeguard that held. The three safeguard states
        have three distinct words and none of them stands in for another: a check that never arose
        is reported as not applicable, never as verified.
      </p>
      <p className="stats-note">
        Where a breakdown withholds small categories, the bars you can see are not the whole
        distribution. The withheld occurrences are carried by a bar of their own and the number of
        withheld categories is stated beside that chart, so the visible shares deliberately do not
        add to 100%.
      </p>
      <p className="stats-note">
        Nothing on this screen validates, exports or gates anything. It reports what a program
        measured; it decides nothing about any record.
      </p>
    </TechnicalDetails>
  );
}

/**
 * The harness vocabulary, glossed.
 *
 * DELIBERATELY NOT the mutation panel's own intro sentence, which stays visible
 * in Record Verification. That sentence exists so the panel makes no flat
 * "records are never altered" claim, and `record-verification.test.tsx` pins its
 * presence AND the absence of the claim it replaced. What is here is the naming
 * — what a change type is against what a trial is, what the two accounting
 * identities assert, and what the run's checks on itself are called.
 */
function MutationMethodology() {
  return (
    <TechnicalDetails
      variant="prose"
      id="stats-mutation-method"
      title="Mutation Methodology"
      sub="What a change type, a trial and a self-check are, and how the seven trial counts are meant to add up."
    >
      <p className="stats-note">
        Each trial pairs one change type with one record. The harness works on a copy, applies the
        change to that copy, and compares what the validator then reports against what the change
        was designed to make it report. Change Types Defined counts the kinds of change the harness
        has available; Trials Attempted counts the pairings it tried. They are different quantities
        and neither is a share of the other.
      </p>
      <p className="stats-note">
        A trial recorded as skipped for not applying is counted in its own row rather than folded
        into either the expected or the unexpected group, so a skip can never be read as a change
        that behaved as designed.
      </p>
      <p className="stats-note">
        The seven trial counts are meant to satisfy two accounting identities. Both are printed as
        arithmetic beside the figures, computed from the values that actually arrived, and stated
        plainly when they do not hold — a single tidy total would have hidden exactly that.
      </p>
      <p className="stats-note">
        The run also checks itself. The rows under Checks on the Verification Run Itself are counts
        of trials that tripped one of those checks; the backend calls them oracles, a word that
        means nothing on a product screen, so each row is named for what it counts instead. Whether
        the source records in this process were in fact left unmodified is one of those checks, and
        it is reported as a measurement in Verification Safeguards rather than promised in advance.
      </p>
      {/* THE SCOPE OF THAT MEASUREMENT, STATED RATHER THAN ASSUMED. The
          safeguard it points at is "Source Records Unchanged in Memory", and the
          sentence has to carry the same limit the label now does: the backend
          compares each record object with itself before and after its trials and
          checks that the mutated clone shares no container with it. Nothing
          re-reads a stored copy afterwards — on the datastore path the
          connection is closed before the first record is even handed to the
          sweep. Reported here because a reader who is told a check exists, and
          not what it compares, supplies the stronger reading themselves. */}
      <p className="stats-note">
        That check compares the records as this process held them, before and after each trial. It
        is not a re-read of stored records, and nothing on this page establishes one. What is
        separately measured about writing is in the same panel: the transaction was read-only, and
        the counts of statements that would have changed data or structure are printed there.
      </p>
    </TechnicalDetails>
  );
}

/**
 * What this page does not establish.
 *
 * IT CARRIES THE SERVER-SIDE-LOGGING PARAGRAPH, verbatim, out of the
 * no-analytics section. That paragraph is the correction of a claim this app
 * shipped falsely once — see `NoAnalytics` — so it is relocated rather than
 * shortened, and the section it came from points here in its own supporting
 * line.
 */
function KnownLimitations() {
  return (
    <TechnicalDetails
      variant="prose"
      id="stats-limitations"
      title="Known Limitations"
      sub="What the figures on this page do not establish, and what this page cannot speak for."
    >
      <p className="stats-note">
        Server-side logs are a different matter, and this page does not speak for them. The backend
        writes a metadata-only outcome line per operation, the web server it runs under writes an
        access line per request, and a hosted deployment sits behind an identity gateway that keeps
        records of its own. Those belong to whoever operates the deployment, the browser cannot see
        them, and nothing here is a claim about what they contain or how long they are kept.
      </p>
      <p className="stats-note">
        Record Verification reports a cached result. Once it is older than the lifetime the API
        holds one for, the next read starts a fresh run and is still answered with the earlier
        result — so a superseded report looks no different from a current one. Its age is stated
        with it, and a note appears beside the age once it is past that lifetime.
      </p>
      <p className="stats-note">
        Every figure on this page is read from this build&rsquo;s own API and describes either this
        workspace or this build. None of them is a platform-wide figure; Platform Metrics states why
        this deployment can produce none.
      </p>
      <p className="stats-note">
        This page mutates nothing and gates nothing. Refresh re-issues the same read-only reads and
        does nothing else, and no control on this screen writes, validates or exports anything.
      </p>
    </TechnicalDetails>
  );
}
