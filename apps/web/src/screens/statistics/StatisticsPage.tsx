import '../screens.css';
import './statistics.css';
import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { AppShell } from '../../components/AppShell';
import { TopBar } from '../../components/TopBar';
import { LeftNav } from '../../components/LeftNav';
import { BackendDown, LoadingPanel } from '../../components/FetchStates';
import { LABELS, formatInstant } from '../../lib/labels';
import { Widget, WidgetGrid } from '../../components/Widget';
import {
  BarChart3,
  BarChartHorizontal,
  FileJson,
  Info,
  List,
  ListOrdered,
  Network,
  Settings,
  Table2,
} from '../../components/icons';
import { api } from '../../lib/api';
import { useFetch, type FetchState } from '../../lib/useFetch';
import { useWorkspaceScope } from '../../lib/workspaceScope';
import { subscribeWorkspaceRebuilt } from '../../lib/workspaceInvalidation';
import type {
  ApiAboutResponse,
  ApiGraphStatus,
  ApiOpenApiResponse,
  ApiSchemaResponse,
} from '../../lib/types';
import {
  ROUTES,
  STATISTICS_TAB_PARAM,
  isStatisticsTab,
  type StatisticsTabId,
} from '../../lib/routes';
import {
  deriveApiSurface,
  deriveMemoryFacts,
  deriveSchemaFacts,
  type MemoryFreshness,
} from '../../lib/statisticsModel';
import { RovingTabs } from '../settings/apiShared';
import { OverviewDashboard } from './OverviewWidgets';
import {
  StatsComparisonRows,
} from './StatsCharts';
import {
  FigureList,
  HeadlineFigure,
  StatCard,
  UnavailableNote,
} from './StatsPrimitives';
import { MyStats } from './MyStats';
import { disabledCurrentUserSource } from '../../lib/currentUserContract';
import { personalStatisticsSourceFor } from '../../lib/myStatsContract';
import { RecordVerification, useVerificationReport } from './RecordVerification';

/**
 * Statistics — the read-only insights surface, in THREE tabs.
 *
 * ── THE 2026-10-12 WIDGET REDESIGN — READ THIS BEFORE THE HISTORY BELOW ────
 *
 * The project owner's verdict on the 2026-09-15 layout: still "a whole bunch of
 * spam", and Build & Verification "is not a good way to portray those
 * statistics". The direction: WIDGETS — each answers one question, states one
 * headline, and keeps its breakdowns and timelines one click away INSIDE the
 * widget. Every tab is now a `WidgetGrid` of `components/Widget.tsx` cards.
 *
 *   · Overview — Records (status · workflow · export gate), Open Questions,
 *     Evidence Support, Workspace Activity (a real 7 · 30 · 365-day range, plus
 *     the most-recently-updated list that used to be Recent Work), Historical
 *     Imports, and the no-analytics claim.
 *   · Build & Verification — Record Verification (validators · mutation ·
 *     format issues · about this run), Verification Safeguards, Runtime,
 *     Project Memory, Record Schema, API Surface, Platform Metrics.
 *   · My Stats — the gate, and the prepared views behind one expansion.
 *
 * WHAT MOVED, AND THE RULE IT MOVED BY. The four free-standing prose
 * disclosures (How Verification Works, How to Interpret Results, Mutation
 * Methodology, Known Limitations), the Technical Details region and the two
 * Overview restatement disclosures are GONE AS CONTAINERS; every paragraph they
 * held is now inside the info panel of the widget whose figures it explains,
 * verbatim unless a note at the site says otherwise. The rule that governed the
 * old disclosures governs the info panels unchanged — PROSE MAY BE COLLAPSED, A
 * MEASUREMENT MAY NOT — and a sentence that QUALIFIES a figure (the
 * non-addability lines, the subset line, the truncation caveat, the unreadable
 * counts) stays visible beside that figure.
 *
 * WHAT A VIEW IS. A widget's view switcher swaps between named presentations of
 * the same source — a breakdown, a ranking, a list — and its headline stays
 * visible whichever is selected. That is a different act from collapsing a
 * finding behind an explanation, which is why measurements may live in a view
 * and may not live in an info panel. Inactive views are `hidden`, not
 * unmounted.
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
      'Your own records and activity.'
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
      'Record verification, and what this deployment reports about itself.'
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
 * louder: its failure costs two small facts — the `Runtime` widget's two cards
 * (in the collapsed Technical Details region until 2026-10-12) — so it states
 * itself with this note at its only reader. An alarm panel there would out-shout
 * the widgets beside it whose figures were read successfully.
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

/**
 * MY STATS IS OFFERED ONLY WHEN IT CAN DRAW SOMETHING (2026-11-02). Personal
 * figures need records associated with a verified account, and until a source
 * can return them the tab held nothing but a statement of that absence. So the
 * tab is not shown, and `?tab=mine` resolves to Overview like any other value
 * the page cannot open. The moment a configured source reports `ready`, the tab
 * returns unchanged — `MyStats` itself is untouched.
 */
function myStatsAvailable(): boolean {
  return personalStatisticsSourceFor(disabledCurrentUserSource.get()).workflowCounts().status === 'ready';
}

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
  const showMine = myStatsAvailable();
  const tabs = showMine ? STATISTICS_TABS : STATISTICS_TABS.filter((tab) => tab.id !== 'mine');
  const activeTab: StatisticsTabId =
    isStatisticsTab(requestedTab) && (requestedTab !== 'mine' || showMine) ? requestedTab : 'general';

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
  /*
   * THE RANGE IS THE READER'S SPAN, AND THE SERVER'S BOUNDARY (2026-10-12).
   *
   * The Workspace Activity widget offers 7 · 30 · 365 days. `undefined` is the
   * default and sends NO parameter, so the default read is byte-for-byte the URL
   * it always was; a chosen span is sent as `window_days`. The widget's label is
   * still read from the RESPONSE's `window.days`, never from this state, so a
   * figure and its window cannot disagree even while a re-read is in flight.
   *
   * A range change is a ROUND OF ONE — `track` opens a new round when the page
   * is idle — so the "N of M reads failed" sentence stays true of what it counts.
   */
  const [activityDays, setActivityDays] = useState<number | undefined>(undefined);
  const activity = useFetch(
    () => track(api.getActivitySummary(activityDays)),
    [scope, activityDays],
  );
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
        {/* ~~`<span className="eyebrow">Workspace Insights</span>`~~ — REMOVED
            2026-10-12. A kicker above the page heading restated the heading in
            smaller type; the heading carries its own weight, and the lead
            sentence beneath it says what the tab is for. */}
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
          tabs={tabs}
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
            tab={activeTab}
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
            <OverviewDashboard
              records={records}
              activity={activity}
              imports={imports}
              activityDays={activityDays}
              onActivityDays={setActivityDays}
            />
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
            tab={activeTab}
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
            <WidgetGrid>
              {/* `RecordVerification` renders TWO widgets — itself and, when a
                  readable report is on screen, `Verification Safeguards` — so
                  the first two `h2`s of this tab come out of one component. */}
              <RecordVerification verification={verification} />
              {/* THE BUILD FACTS ARE NO LONGER COLLAPSED. They sat inside one
                  closed `Technical Details` region, which made four small,
                  self-describing facts cost a click AND a scroll; as widgets
                  each states its own headline and keeps its breakdown inside.
                  The prose that region's supporting line carried is in each
                  widget's info panel. */}
              {/* PAIRED BY HEIGHT (review, 2026-10-18): Project Memory and Record
                  Schema share a row, API Surface takes one, and the two short
                  facts — this build's runtime and the wider platform's absent
                  figures — share the last, so no short widget sits beside a
                  tall one over a block of empty space. */}
              <ProjectMemoryFacts graph={graph} />
              <RecordSchemaFacts schema={schema} />
              <ApiSurface openapi={openapi} />
              <RuntimeFacts about={about} />
            </WidgetGrid>
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
  tab,
  lastSuccess,
  lastAttempt,
  round,
  degraded,
  allFailed,
  refreshing,
  refreshMessage,
  onRefresh,
}: {
  tab: StatisticsTabId;
  lastSuccess: Date | null;
  lastAttempt: Date | null;
  round: Round;
  degraded: boolean;
  allFailed: boolean;
  refreshing: boolean;
  refreshMessage: string;
  onRefresh: () => void;
}) {
  /*
   * THE PAGE'S OWN INFO PANEL (2026-10-12). Two paragraphs of the retired
   * `Known Limitations` disclosure are about the PAGE rather than about any one
   * widget — what every figure here is read from, and that nothing here writes —
   * so they sit behind an info toggle beside the read clock and the Refresh they
   * describe, on both data tabs. The other two paragraphs went to the widgets
   * they qualify: server-side logging to the no-analytics widget, the cached
   * report to Record Verification. Prose only, per the info-panel rule.
   */
  const [aboutOpen, setAboutOpen] = useState(false);
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
        <div className="stats-meta-tools">
          <button
            type="button"
            className="widget-info-toggle"
            aria-label="About These Figures"
            title="About These Figures"
            aria-expanded={aboutOpen}
            aria-controls="stats-page-about"
            onClick={() => setAboutOpen((open) => !open)}
          >
            <Info size={16} strokeWidth={2} aria-hidden="true" />
          </button>
          <button type="button" className="btn btn-secondary" onClick={onRefresh} aria-busy={refreshing}>
            {refreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>
      <div className="widget-info stats-page-about" id="stats-page-about" hidden={!aboutOpen}>
        <p>
          Every figure on this page is read from the API and describes either this workspace or
          this deployment.
        </p>
        <p>
          This page mutates nothing and gates nothing. Refresh re-issues the same read-only reads
          and does nothing else, and no control on this screen writes, validates or exports
          anything.
        </p>
        {tab === 'build' ? (
          /* From the retired `How Verification Works` disclosure, and kept OUT of
             the Record Verification widget on purpose: it names the corpus that
             did not run, which that widget must never do. */
          <p>
            Two corpora can produce the verification report, and they carry very different weight —
            a public reference preflight over already-published upstream example records, and an
            authorized sample of the records this application holds. Which one ran is stated at
            the top of Record Verification before any count — as a product name AND as the value
            the report itself sent, verbatim — and a value this build does not recognise becomes
            its own label rather than being mapped onto either shipped one.
          </p>
        ) : null}
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

type AboutFetch = Fetched<ApiAboutResponse>;
type GraphFetch = Fetched<ApiGraphStatus>;
type OpenApiFetch = Fetched<ApiOpenApiResponse>;
type SchemaFetch = Fetched<ApiSchemaResponse>;


/**
 * The two runtime facts `/api/about` reports about this build.
 *
 * Each is stated only if the response actually carried a usable string. A
 * malformed field becomes the same unavailable literal every other absent figure
 * on this page uses, in the neutral `quiet` tone — not an error, and not a
 * guessed default such as "Synthetic-Only", which would be the one substitution
 * this project forbids outright. Rendering never throws on this body.
 *
 * `/api/about` IS THE PAGE'S ONE QUIET SOURCE: its failure costs two small facts,
 * so it states itself with the compact note rather than an alarm panel.
 */
function RuntimeFacts({ about }: { about: AboutFetch }) {
  return (
    <Widget
      id="stats-runtime"
      title="Runtime"
      /* NO SUPPORTING LINE SINCE 2026-10-18: "This build's data regime and
         storage." restated the two labels beneath it word for word. It shares
         the tab's last row with Platform Metrics, the other short widget. */
      icon={<Settings size={18} strokeWidth={2} aria-hidden="true" />}
      info={
        /* The two sentences that sat under the two values until 2026-10-18.
           When a value is NOT usable its sentence stays visible beside it,
           because then it qualifies the figure rather than defining it. */
        <p>
          Runtime Mode is the data regime this build reports, and Persistence is the storage class
          this build reports.
        </p>
      }
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
    </Widget>
  );
}

function GlanceRuntimeCards({ body }: { body: ApiAboutResponse }) {
  const runtimeMode = titleCaseTokenOrNull(body.runtime_mode);
  const persistence = titleCaseTokenOrNull(body.persistence);
  return (
    <div className="stats-cards stats-cards-pair stats-cards-inline">
      <StatCard
        label="Runtime Mode"
        value={runtimeMode ?? UNAVAILABLE}
        compact={runtimeMode !== null}
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
        compact={persistence !== null}
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



/* ---- Open Questions ---------------------------------------------------- */



/* ---- Evidence Support -------------------------------------------------- */



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


/* ---- Recent Work ------------------------------------------------------- */







/* ---- Workspace Activity (`ACT-004`) ------------------------------------ */





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













/* ---- Historical Imports ------------------------------------------------ */



/* ---- Build · Record Schema --------------------------------------------- */

/**
 * The shape of the official ISAAC record schema this build validates against.
 *
 * A BUILD PROPERTY, not a workspace one: the numbers do not change when a record
 * does. Every figure is a count of the schema's own structure — no record is read
 * to produce any of them. Since 2026-10-12 a widget whose headline is the field
 * total and whose two views are the counts and the by-section breakdown; the two
 * qualifying paragraphs are its info panel, verbatim.
 *
 * `BackendDown` on failure — `/api/schema` has exactly ONE reader, so the page's
 * one-alarm-per-source rule prescribes the full alarm here (a compact note would
 * carry no `role` and a dead schema would announce nothing).
 */
function RecordSchemaFacts({ schema }: { schema: SchemaFetch }) {
  const facts = schema.status === 'data' ? deriveSchemaFacts(schema.data) : null;
  const populated = facts !== null && facts.totalFields > 0;
  return (
    <Widget
      id="stats-schema"
      title="Record Schema"
      sub="The official record schema this build validates against."
      icon={<Table2 size={18} strokeWidth={2} aria-hidden="true" />}
      info={
        <>
          <p>
            Required Top-Level Fields counts what the schema&rsquo;s own root requires.
            Requiredness deeper in the document is not added to it: a field marked required inside
            an optional section is required only once that section is present, so a single total
            across depths would state an obligation the schema does not impose.
          </p>
          <p>
            Fields at Every Depth is counted through the schema&rsquo;s{' '}
            <span className="mono">properties</span> and array items; fields declared only inside a{' '}
            <span className="mono">oneOf</span> alternative are not listed, so this is a count of
            the fields this view can enumerate rather than of every field the document can express.
            The Schema Reference browser walks the document the same way, so the two screens state
            the same number.
          </p>
          <p>
            Vocabulary Terms counts the entries in the vocabulary files this build serves alongside
            the schema. It is a property of those files, not a measurement of any stored data.
          </p>
        </>
      }
      headline={
        populated ? (
          <HeadlineFigure label="Fields at Every Depth" value={count(facts.totalFields)} />
        ) : null
      }
      views={
        populated
          ? [
              {
                id: 'summary',
                label: 'Summary',
                icon: <List size={14} strokeWidth={2} aria-hidden="true" />,
                content: <SchemaFigures facts={facts} part="summary" />,
              },
              {
                id: 'rules',
                label: 'Fields & Vocabulary',
                icon: <ListOrdered size={14} strokeWidth={2} aria-hidden="true" />,
                content: <SchemaFigures facts={facts} part="rules" />,
              },
              {
                id: 'sections',
                label: 'By Section',
                icon: <BarChartHorizontal size={14} strokeWidth={2} aria-hidden="true" />,
                content: (
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
                ),
              },
            ]
          : undefined
      }
      footer={
        schema.status === 'data' ? (
          <Link to={`${ROUTES.governance}?tab=schema`}>Open Schema Reference</Link>
        ) : undefined
      }
    >
      {schema.status === 'loading' && <LoadingPanel label="Loading the official record schema…" />}
      {schema.status === 'error' && <BackendDown error={schema.error} onRetry={schema.reload} />}
      {facts !== null && !populated && (
        <p className="stats-note">
          The schema this build served declares no fields, so there is no breakdown to show.
        </p>
      )}
    </Widget>
  );
}

/**
 * FORM CHOICE — figures for the totals. They sit on different axes (sections,
 * fields, rules, files, terms) and are a labelled list for the same reason the
 * export gate is. The headline, `Fields at Every Depth`, is not repeated here.
 */
function SchemaFigures({
  facts,
  part,
}: {
  facts: ReturnType<typeof deriveSchemaFacts>;
  /**
   * SINCE 2026-10-18 THE EIGHT FIGURES ARE TWO VIEWS — which schema (title,
   * version), and its fields, rules and vocabulary. Same rows, same order,
   * same labels; only where the list is cut moved.
   */
  part: 'summary' | 'rules';
}) {
  const rows = [
        { label: 'Schema Title', value: stringOrUnavailable(facts.schemaTitle) },
        { label: 'Schema Version', value: stringOrUnavailable(facts.schemaVersion), mono: true },
        /* "FIELDS", NOT "SECTIONS": on the real document 5 of the 6 top-level
           properties the root requires are scalar strings, which are fields by
           any reading. The By Section view still says "section", correctly — it
           groups each top-level field WITH ITS DESCENDANTS. */
        { label: 'Top-Level Fields', value: count(facts.topLevelFields), mono: true },
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
      ];
  return <FigureList rows={part === 'summary' ? rows.slice(0, 2) : rows.slice(2)} />;
}

/* ---- Build · Project Memory ------------------------------------------- */

/**
 * What the served memory snapshot reports about itself. The memory and query
 * plane — never the authority on record validity, which its supporting line
 * says. The freshness line stays VISIBLE beside the counts, because it decides
 * what those counts describe (the running build, or an earlier commit).
 */
function ProjectMemoryFacts({ graph }: { graph: GraphFetch }) {
  const facts = graph.status === 'data' ? deriveMemoryFacts(graph.data) : null;
  const freshness = facts !== null ? facts.freshness : null;
  return (
    <Widget
      id="stats-memory"
      title="Project Memory"
      sub="The served memory snapshot — never the authority on validity."
      icon={<Network size={18} strokeWidth={2} aria-hidden="true" />}
      info={<MemoryInfo freshness={freshness} />}
      /* TWO VIEWS SINCE 2026-10-18: what the snapshot serves, and the size of
         the graph it carries. The same six figures under the same six labels;
         the freshness state stays in the body, visible under both. */
      views={facts !== null ? memoryViews(facts) : undefined}
      footer={graph.status === 'data' ? <Link to={ROUTES.memory}>Open Project Memory</Link> : undefined}
    >
      {graph.status === 'loading' && <LoadingPanel label="Loading Project Memory provenance…" />}
      {graph.status === 'error' && (
        <BackendDown error={graph.error} onRetry={graph.reload} />
      )}
      {graph.status === 'data' && <MemoryBody graph={graph.data} />}
    </Widget>
  );
}

/**
 * The prose behind Project Memory's info toggle (2026-10-18 density round).
 *
 * The freshness STATE stays visible beside the counts — it decides what they
 * describe — as one line. The sentence explaining HOW that state was reached
 * moved here, worded for the state actually shown, so the panel never explains
 * an undetermined comparison under a snapshot whose commits were both reported.
 */
function MemoryInfo({ freshness }: { freshness: MemoryFreshness | null }) {
  return (
    <>
      <p>
        The memory plane helps with context and navigation. It is never the authority on whether a
        record is valid — the official schema and the validators are.
      </p>
      {freshness === 'undetermined' && (
        <p>
          Whether this snapshot describes the running build cannot be determined in this
          environment: the two commits needed for the comparison were not both reported.
        </p>
      )}
      {freshness === 'point_in_time' && (
        <p>
          The snapshot was built from a different commit than the one this build reports, so it
          describes the repository at that point and not necessarily the running app. Both commits
          are shown beside the counts.
        </p>
      )}
      {freshness === 'current' && (
        <p>
          Freshness compares the commit the snapshot was built from with the commit this build
          reports; here the two are the same.
        </p>
      )}
    </>
  );
}

function memoryViews(facts: ReturnType<typeof deriveMemoryFacts>) {
  return [
    {
      id: 'snapshot',
      label: 'Snapshot',
      icon: <List size={14} strokeWidth={2} aria-hidden="true" />,
      content: (
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
            {
              // Same label AND same rendering as Project Memory's own row for
              // this field (`ProjectMemory.tsx` `MemoryFigures`): a `v` prefix,
              // so a schema version in a column of counts cannot be read as a
              // count.
              label: 'Snapshot Schema Version',
              value: versionOrUnavailable(facts.snapshotSchemaVersion),
              mono: true,
            },
          ]}
        />
      ),
    },
    {
      id: 'graph',
      label: 'Graph',
      icon: <Network size={14} strokeWidth={2} aria-hidden="true" />,
      content: (
        <FigureList
          rows={[
            { label: 'Concepts', value: countOrUnavailable(facts.concepts), mono: true },
            { label: 'Communities', value: countOrUnavailable(facts.communities), mono: true },
            { label: LABELS.sourceGraphNodes, value: countOrUnavailable(facts.nodes), mono: true },
            { label: 'Edges', value: countOrUnavailable(facts.edges), mono: true },
          ]}
        />
      ),
    },
  ];
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
      {noCounts && (
        <div className="stats-block">
          <UnavailableNote>
            This build served no snapshot overview, so none of the graph counts in this widget is
            available.
            No count is inferred and none is shown as zero.
          </UnavailableNote>
        </div>
      )}

      {facts.freshness === 'point_in_time' && (
        <>
          <p className="stats-note stats-state-line">
            <span className="stats-freshness-label">Point-in-Time Snapshot</span> — built from a
            different commit, so not necessarily the running app.
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
        <p className="stats-note stats-state-line">
          <span className="stats-freshness-label">Built From This Commit</span> — the snapshot's
          source commit matches the commit this build reports.
        </p>
      )}
      {/* ONE LINE SINCE 2026-10-18. The state and its disclaimer stay visible;
          why it could not be determined is behind the widget's info toggle. */}
      {facts.freshness === 'undetermined' && (
        <p className="stats-note stats-state-line">
          <span className="stats-freshness-label">Freshness Undetermined</span> — not a claim that
          the snapshot is current.
        </p>
      )}
    </>
  );
}

/* ---- Build · API Surface ---------------------------------------------- */

/**
 * The shape of the API this build documents, read from its own generated
 * contract. These are the operations that EXIST — not traffic, which this
 * application records nowhere, and the supporting line says so where the
 * headline is read.
 *
 * FORM CHOICE — ~~two different forms for two differently-shaped breakdowns of
 * the same contract~~. Until 2026-10-18 By METHOD was a column chart: at most
 * five short names (`GET`, `DELETE`), which sit under columns without
 * wrapping. That was right on its own terms and is withdrawn for DENSITY, not
 * for correctness: a column chart's plot and axis cost ~200px to show three
 * numbers, it labelled only the largest column, and the two views of one
 * widget drew the same quantity in two different forms. Both views are now
 * compact comparison rows — every value printed as text on its own row, one
 * shared scale, and the same data table and summary sentence as before.
 *
 * By GROUP: as many categories as the document has tags, with names that come
 * from the contract itself and can be anything — the name gets a wrapping
 * line of real text.
 */
function ApiSurface({ openapi }: { openapi: OpenApiFetch }) {
  const surface = openapi.status === 'data' ? deriveApiSurface(openapi.data) : null;
  const populated = surface !== null && surface.operationCount > 0;
  return (
    <Widget
      id="stats-api"
      title="API Surface"
      sub="Documented operations — not traffic, which is recorded nowhere."
      /* Full width since 2026-10-18, so Project Memory and Record Schema — two
         widgets of near-equal height — share the row above it. */
      span="full"
      icon={<FileJson size={18} strokeWidth={2} aria-hidden="true" />}
      headline={
        populated ? (
          <>
            <HeadlineFigure label="Documented Operations" value={count(surface.operationCount)} />
          </>
        ) : null
      }
      views={
        populated
          ? [
              {
                id: 'method',
                label: 'By Method',
                icon: <BarChart3 size={14} strokeWidth={2} aria-hidden="true" />,
                content: (
                  <StatsComparisonRows
                    caption="Documented operations by HTTP method"
                    /* The tab reads "By Method" under the headline "Documented
                       Operations"; the caption restated both, so it is kept for
                       assistive technology. By Group keeps its caption visible,
                       because "in the contract's own tag order" says something
                       neither the tab nor the headline does. */
                    captionHidden
                    rows={surface.byMethod.map((row) => ({
                      key: row.method,
                      label: row.method.toUpperCase(),
                      value: row.count,
                    }))}
                    unit="operations"
                    total={surface.operationCount}
                    categoryHeader="HTTP Method"
                  />
                ),
              },
              {
                id: 'group',
                label: 'By Group',
                icon: <BarChartHorizontal size={14} strokeWidth={2} aria-hidden="true" />,
                /* `Groups` sat beside the headline until 2026-10-18; it is the
                   count of the rows this view draws, so it is stated here. */
                content: (
                  <>
                  <FigureList rows={[{ label: 'Groups', value: count(surface.groupCount), mono: true }]} />
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
                  </>
                ),
              },
            ]
          : undefined
      }
      footer={
        openapi.status === 'data' ? (
          <Link to={ROUTES.settingsTab('explorer')}>Open Endpoint Explorer</Link>
        ) : undefined
      }
    >
      {openapi.status === 'loading' && <LoadingPanel label="Loading the API contract…" />}
      {openapi.status === 'error' && (
        <BackendDown error={openapi.error} onRetry={openapi.reload} />
      )}
      {surface !== null && !populated && (
        <p className="stats-note">
          The contract this build served documents no operations, so there is no breakdown to show.
        </p>
      )}
    </Widget>
  );
}


