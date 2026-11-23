---
name: ISAAC questions
description: One card, one question, its answer, for one beamline scientist at a time.
colors:
  ground: "#f4f5f7"
  card: "#ffffff"
  sunk: "#f7f8fa"
  line: "#e2e5e9"
  line-strong: "#cfd4da"
  control-line: "#858e99"
  ink: "#14181d"
  ink-2: "#444d59"
  ink-3: "#59626e"
  action: "#1d5bd1"
  action-hover: "#184cb0"
  action-press: "#143f92"
  action-tint: "#ebf1fc"
  on-action: "#ffffff"
  ok: "#1d6a42"
  ok-bg: "#e9f5ee"
  ok-line: "#b9dfc9"
  warn: "#7f5300"
  warn-bg: "#fbf3e1"
  warn-line: "#ead39b"
  bad: "#9a2a20"
  bad-bg: "#fcecea"
  bad-line: "#f0c3bd"
typography:
  headline:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "30px"
    fontWeight: 650
    lineHeight: 1.3
    letterSpacing: "-0.012em"
  title:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "24px"
    fontWeight: 650
    lineHeight: 1.3
    fontFeature: "tnum"
  section:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "18px"
    fontWeight: 650
  body:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "18px"
    fontWeight: 400
    lineHeight: 1.6
  control:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "16px"
    fontWeight: 550
    lineHeight: 1.3
  label:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 600
  meta:
    fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 400
  quote:
    fontFamily: "ui-monospace, 'SF Mono', Menlo, Consolas, monospace"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.55
rounded:
  control: "10px"
  card: "14px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "10px"
  lg: "14px"
  xl: "18px"
  block: "28px"
  card-x: "40px"
  card-y: "36px"
components:
  button-primary:
    backgroundColor: "{colors.action}"
    textColor: "{colors.on-action}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "10px 18px"
    height: "46px"
  button-primary-hover:
    backgroundColor: "{colors.action-hover}"
  button-primary-active:
    backgroundColor: "{colors.action-press}"
  button:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    typography: "{typography.control}"
    rounded: "{rounded.control}"
    padding: "10px 18px"
    height: "46px"
  button-hover:
    backgroundColor: "{colors.sunk}"
  button-chosen:
    backgroundColor: "{colors.ok-bg}"
    textColor: "{colors.ok}"
  input:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "10px 14px"
    height: "46px"
  card:
    backgroundColor: "{colors.card}"
    textColor: "{colors.ink}"
    rounded: "{rounded.card}"
    padding: "36px 40px 32px"
  link-quiet:
    textColor: "{colors.action}"
    typography: "{typography.control}"
  saved-line:
    backgroundColor: "{colors.ok-bg}"
    textColor: "{colors.ok}"
    rounded: "{rounded.control}"
    padding: "12px 16px"
  toast:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.card}"
    rounded: "{rounded.pill}"
    padding: "10px 18px"
---

# Design System: ISAAC questions

## Overview

**Creative North Star: "The Plain Form"**

A category-standard form played straight: a white card on a soft grey ground, near-black text, one blue for the thing to do next, and green only once something is saved. Nothing decorates. The page is one centered column (760px shell, about 720px of card) holding one question at a time; everything that is not the question, the suggestion, its evidence line and the answer controls sits behind a single disclosure.

Density is low and type is large: 18px body at 1.6 line height, a 30px question, 46px controls. The system reads as calm and finished rather than branded; the only identity is the plain text wordmark "ISAAC" in the top line. Light and dark are both first-class, switched by `prefers-color-scheme` with every role re-declared on `:root`.

Values from the scientist's own files are shown in monospace and tabular numerals so they read as quoted data, not interface.

**Key Characteristics:**
- One card per screen; the question is the largest text on the page.
- One blue action colour; green is reserved for saved state; amber for "don't know" and changed suggestions; red for errors.
- System sans throughout; monospace only for quoted file lines and key hints.
- Flat surfaces with one soft ambient shadow on cards; hairline borders do the structural work.
- Disclosures marked by a CSS-drawn chevron that rotates open.
- Tables with tabular numerals and right-aligned numeric columns.

## Colors

A neutral cool-grey ramp with a single saturated blue and three status hues, each status carried as a text/fill/border triple.

### Primary
- **Form Blue** (action): the primary button, link-style actions, disclosure summaries, caret colour and the focus ring. Hover and press step darker (action-hover, action-press); action-tint is the text-selection wash.

### Secondary
- **Saved Green** (ok, ok-bg, ok-line): only for an answer that has been saved: the chosen option button, the saved status line, the done dot in the list, the progress bar fill and the saved answer text in list rows.

### Tertiary
- **Unsure Amber** (warn, warn-bg, warn-line): "Saved as: don't know", a suggestion that changed since it was accepted, and the half-filled list dot.
- **Error Red** (bad, bad-bg, bad-line): inline card errors and the failure toast.

### Neutral
- **Soft Grey Ground** (ground): page background behind every card.
- **Card White** (card): cards, list panels, inputs and secondary buttons.
- **Sunk** (sunk): hover fill for rows and secondary buttons, table header background.
- **Hairline** (line) and **Strong Hairline** (line-strong): card and row borders, dividers, the empty progress track; key-hint outlines.
- **Control Edge** (control-line): borders of inputs, buttons, selects and empty list dots, held at 3:1 or better against the card.
- **Ink** (ink), **Ink 2** (ink-2), **Ink 3** (ink-3): primary text; secondary text (lead, reason, labels, table headers); metadata (scope line, citations, top line, hints). All meet 4.5:1 on card and ground.

Dark mode re-declares every role on `:root` under `prefers-color-scheme: dark`: ground #101317, card #181c22, ink #eef1f4, action #7aa7f5 with dark text on it (#0c1525), ok #7fd1a2, and the shadow drops to a single 1px edge.

### Named Rules
**The One Blue Rule.** Blue means "you can act here" and nothing else. One filled blue button per view (the suggestion's "Yes, that's right", the list's "Answer the next N", sign-in); every other action is a white bordered button or a blue text link.

**The Green Means Saved Rule.** Green appears only after a save succeeds. A suggestion, a likely answer or a confidence level is never green.

## Typography

**Body Font:** system-ui stack (system-ui, -apple-system, Segoe UI, Roboto, Helvetica Neue, Arial)
**Mono Font:** ui-monospace stack (SF Mono, Menlo, Consolas)

**Character:** The platform's own sans at generous sizes, so the page feels like a well-made native form; monospace marks a line lifted verbatim from a file.

### Hierarchy
- **Headline** (650, 30px, 1.3, -0.012em, balanced wrap): the question, and the list greeting. 24px under 640px.
- **Title** (650, 24px, 1.3, tabular): the suggested value, prefixed by "Suggested:" in 500 weight ink-2.
- **Section** (650, 18px): list section headings, followed by a tabular count in 400 ink-3.
- **Body** (400, 18px, 1.6; 17px under 640px): lead and reason sentences, capped at 64ch.
- **Control** (550 to 600, 16px, 1.3): buttons, links, disclosure summaries, inputs.
- **Label** (600, 15px, ink-2, sentence case): "Or a different answer", field labels, evidence subheadings.
- **Meta** (400, 14 to 15px, ink-3): top line, scope line, citations, hints, captions.
- **Quote** (mono 15px, 1.55, pre-wrap): the evidence line; its file and line cite below in 14px sans.

### Named Rules
**The Tabular Values Rule.** Any number a scientist might compare (suggested values, counts, progress, "Question 3 of 10", table cells) uses tabular numerals.

**The Sentence Case Rule.** Labels are short sentences in sentence case at 15px/600. No uppercase tracking, no category words above headings.

## Layout

A single centered column: shell max-width 760px with 20px side padding (14px under 640px), 72px bottom padding. Above the card, a thin top line (ISAAC, position, signer) at 15px and a provenance line (beamline, edge, dates; folder) at 14px. The card holds the question flow vertically: headline, scope (8px), suggestion block (28px), answer block (28px), quiet links row (26px, separated by a hairline), disclosures (22px). The pager sits 18px below the card with "All questions" left and Previous/Next right; a shortcut line is centered under it.

The list view stacks a greeting card (progress bar, primary start button, sitting-size select) above grouped row panels (34px section gaps). Sign-in narrows to 460px at 8vh from the top.

Under 640px: card padding drops to 24px 20px, the pager stacks with full-width buttons, typed-answer Save goes full width, the signer's name hides, and wide tables show a "swipe sideways" hint under a horizontally scrolling wrapper.

## Elevation & Depth

Flat by default. Cards and the list panel carry one soft ambient shadow and a hairline border; nothing else is raised except the floating toast. In dark mode the shadow reduces to a single dark edge and borders carry the separation.

### Shadow Vocabulary
- **Card ambient** (`box-shadow: 0 1px 2px rgba(16, 24, 40, 0.05), 0 6px 20px rgba(16, 24, 40, 0.06)`): cards only.
- **Card ambient, dark** (`box-shadow: 0 1px 2px rgba(0, 0, 0, 0.35)`).

### Named Rules
**The Hairline First Rule.** Structure comes from 1px borders and the grey ground, not from shadow. Do not add elevation to buttons, rows or status lines.

## Shapes

Gently rounded throughout: 14px on cards and the list panel, 10px on controls, status lines, table wrappers and figures, full pills for the progress bar and toast, circles for list status dots. Borders are 1px; the only 2px strokes are the drawn marks: the disclosure chevron (a 7px corner of two borders, rotated -45deg closed, 45deg open), the check mark on a chosen answer (a rotated L), and the focus outline.

## Components

### Buttons
Quietly solid, sized for a laptop trackpad.
- **Shape:** gently curved (10px), min-height 46px, padding 10px 18px, 16px/550.
- **Primary:** Form Blue fill, white text, 600 weight; full width under the suggestion. Hover and press step darker. Carries a key hint (Y) outlined in currentColor when shortcuts are on.
- **Secondary:** card fill with control-line border, ink text; hover to sunk fill and ink-3 border, press to line fill. Options sit in a wrapping row with 10px gaps, or stack full width when any option is longer than 28 characters.
- **Chosen:** ok-bg fill, ok border and text, preceded by a drawn check. Applies to the primary button too once accepted.
- **Disabled:** 55% opacity.
- **Transitions:** background and border, 120ms ease-out.

### Answer choices (the flashcard flow)

The page opens straight on the first open question and moves through them like flashcards. Every answer is a full-width choice button (56px tall, 12px radius, 18px label) with a numbered key chip; the keys 1–9 pick the matching choice. The suggested answer comes first with a 2px Form Blue border and a "Suggested" pill. One click saves the answer, the choice turns Saved Green with a drawn check, and the next card slides in (220ms, from 10px right; none under reduced motion). Short answer lists (up to three beyond the common ones) are shown whole; longer ones sit behind "More answers (N)". A thin blue bar above the card shows how far through the questions the person is.

### Links and disclosures
- **Quiet links:** blue 550 text, no underline at rest, underline on hover (offset 3px). "I don't know" and "Skip for now" share a row under a hairline; chosen "I don't know" turns ok green.
- **Disclosures:** blue summary with the drawn chevron (160ms rotate), no native marker. Used for "More answers (N)", "Add a note" and "Show the evidence and context".

### Inputs / Fields
- **Style:** card fill, control-line border, 10px radius, 46px tall, 16px text, blue caret; textarea 96px min, vertical resize.
- **Focus:** 2px Form Blue outline at 1px offset (2px offset elsewhere).
- **Labels:** 15px/600 ink-2 above the field.

### Cards / Containers
- **Corner Style:** 14px.
- **Background:** card white on ground.
- **Shadow Strategy:** card ambient (see Elevation).
- **Border:** 1px hairline.
- **Internal Padding:** 36px 40px 32px; 24px 20px 22px under 640px.

### Status lines
- **Saved:** ok-bg fill, ok-line border, ok text, 10px radius, 12px 16px; "by name, date · Clear" in ink-2 at 15px on the right.
- **Unsure:** the same shape in the amber triple.
- **Error:** the same shape in the red triple, role alert.
- **Toast:** ink pill on the bottom centre, 15px/550, slides up 12px with opacity (220ms expo-out); red variant for failures.

### Evidence quote
Mono 15px line in ink, pre-wrapped, then a 14px ink-3 cite with the file name in ink-2 and the line number. Shown once under the suggestion; the rest lives in the evidence disclosure.

### Values table
Wrapped in a 10px-radius hairline box that scrolls horizontally (min table width 520px, thin scrollbar). 15px tabular numerals; header row in sunk with ink-2 600 text; 8px 12px cells with hairline row rules. Numeric columns, header included, are right-aligned and never wrap; text columns break only at underscores.

### Question list
A single bordered panel of full-width rows (14px 20px, sunk on hover) with a 12px status dot in an 18px column: empty ring, filled green when saved, amber when unsure. Title at 550, meta at 15px ink-3, saved answer in ok green.

### Progress
Tabular "N of M" line with percentage, over an 8px pill track in line with an ok-green fill (300ms expo-out width).

## Do's and Don'ts

### Do:
- **Do** keep one filled blue button per view and make every other action a bordered white button or a blue text link.
- **Do** reserve green for saved answers and amber for "don't know" or a changed suggestion.
- **Do** set every colour through the `:root` custom properties and give each new role a dark-mode value in the `prefers-color-scheme` block.
- **Do** use tabular numerals for counts and values, and right-align numeric table columns including their headers.
- **Do** draw marks (chevrons, checks) with 2px CSS borders in currentColor.
- **Do** keep controls at 46px minimum height and text at or above 4.5:1.

### Don't:
- **Don't** add a second accent colour or colour a suggestion by confidence.
- **Don't** put labels in uppercase tracking or place category words above the question.
- **Don't** load web fonts, icon fonts or remote images; the CSP forbids them and the system stack is the type.
- **Don't** use official ISAAC, SSRL or DOE logos or colours; the wordmark is plain text.
- **Don't** raise anything but cards and the toast; no shadows on buttons, rows or status lines.
- **Don't** stack context panels or chips on the card; extra context goes behind the one evidence disclosure.
