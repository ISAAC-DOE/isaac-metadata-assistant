import './screens.css';
import { useEffect, useRef, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import { TopBar } from '../components/TopBar';
import { LeftNav } from '../components/LeftNav';
import { RecordValidator } from '../components/RecordValidator';
import { SchemaBrowser } from '../components/SchemaBrowser';
import { LABELS } from '../lib/labels';
import { ROUTES } from '../lib/routes';

/**
 * Governance & Safety — the synthetic-only policy, the P36.3 standalone schema
 * Validator, and the read-only Schema Reference browser, organized as LOCAL
 * page tabs (Policy / Validator / Schema Reference) — never added to the global
 * LeftNav (which keeps its single `active="governance"` entry). Same tablist
 * pattern (CSS classes + roving-tabindex keyboard nav) as Project Memory's
 * internal tabs (`ProjectMemory.tsx`'s `SectionTabs`; screens.css
 * `.section-tabs`/`.section-tab`) — not a new UI paradigm.
 *
 * P36R S8 renamed the third tab from "Schema & Vocabulary" to "Schema
 * Reference" (plan §R7). The vocabulary is NOT empty — it is one of the three
 * subviews inside that tab (Fields · Conditional Rules · Vocabulary), so the
 * shorter name describes the surface without dropping anything from it.
 */
type GovernanceTab = 'policy' | 'validator' | 'schema';

const GOVERNANCE_TABS: { id: GovernanceTab; label: string }[] = [
  { id: 'policy', label: 'Policy' },
  { id: 'validator', label: 'Validator' },
  { id: 'schema', label: 'Schema Reference' },
];

const tabId = (id: GovernanceTab) => `governance-tab-${id}`;
const panelId = (id: GovernanceTab) => `governance-tabpanel-${id}`;

/**
 * P36V S-B — the `?tab=` deep-link parameter. The active tab is DERIVED from the
 * URL (it used to be `useState`, so the Validator was unreachable by link), which
 * is what lets the Assistant's Open Validator action land on the Validator tab
 * with the tab genuinely selected. Anything unrecognised — a typo, an empty
 * value, an absent param — falls back to `policy` without throwing.
 */
const TAB_PARAM = 'tab';

function isGovernanceTab(value: string | null): value is GovernanceTab {
  return GOVERNANCE_TABS.some((t) => t.id === value);
}

/** The Validator's own heading (`RecordValidator`'s `<h2 id>`), the focus target. */
const VALIDATOR_HEADING_ID = 'rec-val-heading';

export function GovernancePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const location = useLocation();

  const requestedTab = searchParams.get(TAB_PARAM);
  const activeTab: GovernanceTab = isGovernanceTab(requestedTab) ? requestedTab : 'policy';

  // An IN-PAGE tab activation must not have its focus stolen: the tablist's
  // roving tabindex deliberately moves focus to the newly selected TAB. This flag
  // marks a change that originated here so the arrival-focus effect below skips
  // it — arriving from elsewhere (a link, or the Assistant's Open Validator
  // action) still focuses the Validator.
  const inPageSelectRef = useRef(false);

  function selectTab(tab: GovernanceTab) {
    inPageSelectRef.current = true;
    const next = new URLSearchParams(searchParams);
    next.set(TAB_PARAM, tab);
    // `replace` for a within-page tab click: switching tabs is not a destination,
    // and pushing each one would bury the screen the reader arrived from behind a
    // stack of Back presses. The ARRIVING navigation (below / from the Assistant)
    // is the PUSH, so one Back returns there.
    setSearchParams(next, { replace: true });
  }

  // Arrival focus. `location.key` changes on EVERY navigation — including a
  // repeat navigation to the identical URL — so activating Open Validator while
  // already on the Validator tab still moves focus and scrolls the surface into
  // view (the control is never perceptibly dead). Focus goes to the Validator's
  // own heading; nothing here runs a validation or touches the record.
  useEffect(() => {
    if (inPageSelectRef.current) {
      inPageSelectRef.current = false;
      return;
    }
    if (activeTab !== 'validator') return;
    const heading = document.getElementById(VALIDATOR_HEADING_ID);
    if (!heading) return;
    heading.focus();
    // jsdom does not implement scrollIntoView — call it only where it exists.
    heading.scrollIntoView?.({ block: 'start' });
  }, [location.key, activeTab]);

  return (
    <AppShell
      variant="full"
      topBar={<TopBar variant="home" />}
      sidebar={<LeftNav active="governance" />}
      mainPad="pad"
      width="wide"
    >
      <div className="placeholder">
        <span className="eyebrow">Data Governance</span>
        <h1>{LABELS.navGovernance}</h1>

        <GovernanceSectionTabs active={activeTab} onSelect={selectTab} />
      </div>

      {activeTab === 'policy' && (
        <div
          className="placeholder"
          id={panelId('policy')}
          role="tabpanel"
          aria-labelledby={tabId('policy')}
          tabIndex={0}
        >
          {/* P2 — THE CANONICAL-HOME POINTER. Settings → Data & Privacy is the
              one place the collection / storage / retention / reset / export
              definitions are authored (`lib/settingsContent.ts`). This tab is
              the policy and the safety behaviour that follows from it. The
              pointer is deliberately a real Link and not prose: a reader who
              arrives here asking a data-handling question should be able to
              leave for the answer in one activation. */}
          <p className="gov-canonical">
            Settings › Data &amp; Privacy is the canonical home for what this build collects,
            stores, retains, resets, and exports. This tab states the governance policy and the
            safety behaviour it requires.{' '}
            <Link to={ROUTES.settingsTab('privacy')}>Open Data &amp; Privacy Settings</Link>
          </p>

          {/* P2 — LAYOUT. These three paragraphs used to be one 68ch column in a
              1200px `wide` main, so roughly half the page was empty and the tab
              underline ran far past the prose beneath it. They are now two
              measured columns that collapse to one when there is not room for
              two (`.gov-policy` in screens.css), and each is titled — the page
              had no structure below its h1 at all, so a reader scanning for
              "what happens to a file I pick?" had to read the whole thing.
              Every sentence is unchanged apart from the one clause noted below. */}
          <div className="gov-policy">
            <div className="gov-policy-col">
              {/* Slice 2A (I5). The first sentence used to read "This prototype is
                  synthetic-only by default", which stopped being true of the
                  DEPLOYMENT once a protected read-only diagnostic could run against
                  an isolated test database of production-derived records. The
                  sections below keep the claims apart: what the reader SEES stays
                  synthetic; what the deployment MAY DO is bounded and stated. Same
                  wording constraints as components/GovernanceBanner.tsx — "may
                  run", never "is running"; an isolated SLAC test database, never
                  the production database; and no claim that the app itself verified
                  that isolation (the guarantee is an external pg_hba grant).

                  R1b. The last clause used to read "and no file is read, parsed, or
                  inspected" — an ABSOLUTE claim, and false: this very page's
                  `validator` tab (below) mounts `RecordValidator`, which reads the
                  file you pick (`file.text()` / `FileReader`) and POSTs it to
                  `/api/validate/record`; `CsvReconcilePanel` does the same for a
                  campaign sheet. The refusal claim is still true of the UPLOAD path
                  (`POST /api/uploads` declares no multipart and parses nothing), so
                  it is kept and SCOPED, and the two readers are disclosed rather
                  than denied. `lib/settingsContent.ts`'s `no-real-experiment-data`
                  card already said this correctly; the three sites are now pinned to
                  one claim by `__tests__/upload-claim-parity.test.tsx`.

                  P2 — ONE CLAUSE LEFT THIS PARAGRAPH, AND IT WAS RELOCATED, NOT
                  DROPPED. It read "— and nothing on any screen here is sent to a
                  model or an index", which is a data-handling definition rather
                  than a governance policy, and it was the only sentence on this
                  tab making a claim about Project Memory's index. Both halves are
                  now in the canonical home: the MODEL half widened
                  `no-external-model-calls`'s last sentence from "Nothing you type"
                  to "Nothing you type, and nothing shown on any screen here"; the
                  INDEX half is a new sentence in `project-memory-boundary`. The
                  policy sentence it hung off — written approval before anything
                  may be read, indexed, or sent to a model — is untouched. */}
              <section className="gov-policy-section">
                <h2>Workspace Scope</h2>
                <p>
                  The visible workspace remains synthetic and uploads remain disabled. Real
                  SLAC/SSRL or private artifacts require written data-governance approval before
                  they can be read, indexed, or sent to any model. Adding a file to this workspace
                  is closed off entirely: every file upload is refused outright, whatever it
                  contains, and the refused request is never read, parsed, or inspected.
                </p>
              </section>
              <section className="gov-policy-section">
                <h2>What a Review Tool Reads</h2>
                <p>
                  Two review tools do read a file you paste or pick, and neither adds it to the
                  workspace: the Validator on the next tab, and campaign-sheet CSV reconciliation on
                  a record's evidence trail. Each checks the text in memory and discards it, and
                  records only the outcome — never the content.
                </p>
              </section>
            </div>
            <div className="gov-policy-col">
              {/* P2 — `<GovernanceBanner />` USED TO RENDER DIRECTLY BELOW THIS
                  PARAGRAPH, and it is gone from this screen only. It states the
                  same diagnostic paragraph in compact form — its own doc comment
                  says so ("substantively equivalent to the full paragraph on
                  Governance & Safety → Policy; keep them in step") — so this one
                  tab said all of it twice, about 40 lines apart, and the fuller
                  version is the one below (only it names what is withheld from
                  display). Its "Read Policy" button was also DEAD here: this page
                  passed no `onReadPolicy`, on the very screen that button exists
                  to navigate to.

                  The component is untouched and still mounts on
                  `screens/LoadMaterials.tsx`, where the button does navigate and
                  where the compact form is the only statement on the screen.
                  `db-recon-truthfulness.test.tsx` renders it directly, so its own
                  required/forbidden claims are unaffected by this removal — and
                  that file's Policy-tab suite still passes because every claim it
                  requires is in the prose here, not in the banner. */}
              <section className="gov-policy-section">
                <h2>Private Database Diagnostic</h2>
                <p>
                  Separately, this deployment may run a protected, read-only diagnostic against an
                  isolated SLAC test database containing production-derived records. PostgreSQL is
                  used only by that diagnostic path: records are processed transiently in pod
                  memory, only sanitized aggregate results are returned, and no record is modified.
                  No record ids, titles, scientific values, evidence, full JSON, or per-record
                  results are displayed, and nothing is sent to any model. Database-backed record
                  display remains disabled pending an explicit visibility decision.
                </p>
              </section>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'validator' && (
        <div
          className="governance-panel"
          id={panelId('validator')}
          role="tabpanel"
          aria-labelledby={tabId('validator')}
          tabIndex={0}
        >
          <RecordValidator />
        </div>
      )}

      {activeTab === 'schema' && (
        <div
          className="governance-panel"
          id={panelId('schema')}
          role="tabpanel"
          aria-labelledby={tabId('schema')}
          tabIndex={0}
        >
          <SchemaBrowser />
        </div>
      )}
    </AppShell>
  );
}

// --- local page tabs (mirrors ProjectMemory.tsx's SectionTabs pattern) -----
// A local tablist — Policy · Validator · Schema Reference — NOT part of the
// global LeftNav. Roving tabindex + arrow/Home/End keyboard navigation
// (automatic activation); native buttons carry Enter/Space activation.

function GovernanceSectionTabs({
  active,
  onSelect,
}: {
  active: GovernanceTab;
  onSelect: (tab: GovernanceTab) => void;
}) {
  function onKeyDown(e: ReactKeyboardEvent<HTMLButtonElement>, index: number) {
    let nextIndex: number | null = null;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      nextIndex = (index + 1) % GOVERNANCE_TABS.length;
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      nextIndex = (index - 1 + GOVERNANCE_TABS.length) % GOVERNANCE_TABS.length;
    } else if (e.key === 'Home') {
      nextIndex = 0;
    } else if (e.key === 'End') {
      nextIndex = GOVERNANCE_TABS.length - 1;
    }
    if (nextIndex === null) return;
    e.preventDefault();
    const next = GOVERNANCE_TABS[nextIndex];
    onSelect(next.id);
    // Move focus to the newly selected tab (roving tabindex).
    (document.getElementById(tabId(next.id)) as HTMLButtonElement | null)?.focus();
  }

  return (
    <div className="section-tabs" role="tablist" aria-label="Governance & Safety sections">
      {GOVERNANCE_TABS.map((tab, i) => {
        const selected = active === tab.id;
        return (
          <button
            key={tab.id}
            id={tabId(tab.id)}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-controls={selected ? panelId(tab.id) : undefined}
            tabIndex={selected ? 0 : -1}
            className={`section-tab${selected ? ' active' : ''}`}
            onClick={() => onSelect(tab.id)}
            onKeyDown={(e) => onKeyDown(e, i)}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
