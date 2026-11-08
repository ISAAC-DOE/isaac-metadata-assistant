# The November 2026 declutter: shared components, classes and copy rules

What the site-wide declutter changed that every later screen should follow. It records the
owner's brief ("less overbearing… too much text… too many buttons", remove the "ISAAC never…",
"local-first" and "it's just a demo" prose, themed controls, blue actions, use the full width) as
it landed in:

- #306: Schema Proposals as one page, plus the shared `Select` and `SegmentedControl`
- #308: the shell, Settings, Load, Governance, Home, Historical Import and Memory; the honesty tests now pin "no false claim"
- #310: the record workspaces, Complete, Evidence and Export
- #311: every remaining native `<select>` becomes `Select`

`docs/ui-handoff/design-system.md` is still the design bar; this note is the delta.

## New shared components (on main since #306)
- **`components/Select.tsx`**: the WAI-ARIA select-only combobox. It supports option groups, a `detail` line per option, type-ahead, and Escape/Tab. Escape stops propagation while the picker is open. It is labelled with `<label htmlFor>`. The themed-picker PR adds `density="compact"`, passes `data-*` through, and positions the popup as `fixed` so clipping parents don't cut it off.
- **`components/SegmentedControl.tsx`**: a radiogroup with roving tabindex. It allows "none chosen".
- **Test helpers in `src/test/controls.ts`**: `getSelect`, `chooseOption`, `selectValue`, `selectGroups`, plus `chooseValue`, `optionValues` and `optionElements` once the themed-picker PR lands. For e2e, `e2e/helpers/select.ts` arrives with that PR.
- **Rule:** don't add a native `<select>`. Use `Select`.

## `base.css` (PR #308)
- **`.btn-secondary`** is now the blue-tinted action look:
  - background `--action-tint`, border `--action-selected-border`, text `--action-hover`, regular weight;
  - hover: border `--action`, text `--action-pressed`;
  - active: `--action-selected-border` fill.
- **`.btn-primary`** is unchanged: one per view.
- **New `.btn-quiet`**: neutral text button for cancel and dismiss.
- **New `.btn-ghost`**: blue text button for tertiary actions.
- **`.btn-secondary[aria-disabled="true"]`** looks the same as `:disabled` at rest, on hover and on press. `interaction-states` pins this and fails if any sheet restyles a refused button's hover.
- **Global rule:** `input[type=radio], input[type=checkbox] { accent-color: var(--action); }`.

## `chrome.css` (PR #308)
- **Removed:** `.mode-chip-wrap`, `.mode-chip-popover*`, `.nav-footer`, `.nav-version`, `.statusbar-right`. The mode chip renders only in a worked-example session or when the mode is anomalous.
- **`.nav-item.ancestor`**: an outline with no fill, so it can't be mistaken for active.
- **≤1024px**: `.leftnav` is one row that scrolls sideways (`nowrap`, `overflow-x: auto`), and the active item is scrolled into view. `e2e/layout-allowlist.ts` declares it as `ALLOW-LEFTNAV-SCROLL`. The occlusion probe now scrolls a control into view inside a declared scroller before judging it.

## `screens.css`
- Rules each branch orphaned were removed. Record side: `.preexport-coverage*` and `.ready-heading .ready-note` are left over and listed.
- The type-scale ratchet `spacing` ceiling is now 2291 (the combined counter on main).

## Other shared files
- `assistant-drawer.css`: at ≤620px the trigger is icon-only, keeping its accessible name.
- `components/icons.tsx`: an `Ellipsis` export (record side).
- `screens/record-workbench.css`: new (record side).

## Copy rules
- No standing disclaimer prose. That means no "demo", "synthetic", "this build", "local-first", "never…" or "no language model".
- Never replace one with a false claim.
- A control that can't act here either shows a short reason when it's used, or is hidden.
- The honesty tests now pin "no false claim" against all of `src`: `upload-claim-parity`, `assistant-model-claim-parity`, `help-claim-parity`, `mode-chip`, `db-recon-truthfulness`, `hosted-truthfulness`, `help-and-honesty`, `reset-claim-parity`, `backend-down-state`. A new disclaimer sentence in Statistics or Local Imports is allowed. A false claim isn't.

## Working notes

- After any edit to a file the memory snapshot lists, run `python scripts/refresh_served_manifest.py`
  last, then `PYTHONPATH=src:apps/api python -m pytest apps/api/tests/test_committed_snapshot.py`.
- The e2e accessibility probe opens declared disclosures before scanning (`e2e/helpers/disclosures.ts`).
  A new collapsed section needs a declared count there, or axe silently stops covering it.

## Handoffs (open)
- **Statistics:** "Open Privacy Settings" now lands on Settings → Overview, because the Privacy tab is gone. Memory's "Nodes" figure is now "Source Graph Nodes", so consider matching it.
- **Local Imports:** none known.
- **`Select` polish, deferred from #311:**
  1. A controlled value that is not among the options shows a blank trigger.
  2. The popup re-measures on every scroll event; it could be throttled.
  3. The popup stays open when an inner scroll box scrolls its trigger out of view.
  4. Escape on a *closed* picker inside the assistant drawer still reaches the drawer. No picker sits there today.
  5. One z-index overlap that predates #311.
- **Browsers:** the pickers are tested in Chromium and jsdom only. Firefox and WebKit are not installed for Playwright here.
