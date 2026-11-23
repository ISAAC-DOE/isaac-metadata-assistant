# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
One expert beamline scientist at a time (first: Angel, the IrOxBase beamtime's scientist), answering on a laptop browser in short sittings of 10 to 15 questions, whenever they have a few minutes. They know the experiment far better than the software does; they do not know ISAAC's schema vocabulary.

## Product Purpose
A password-protected page that asks the scientist the questions blocking their historical beamtime's records from export, one card at a time. Every click saves. Answers are downloaded by the ISAAC team and imported back into the local bundle with `isaac bundle site import`. Success: each answer is right, quick, and needs no follow-up email.

## Positioning
Every question arrives with the evidence behind it, quoted from the scientist's own files and logbook with file and line, and with the skill's suggested answer that the scientist confirms or corrects. The page never fills a value in for them.

## Operating Context
- Sign-in: one shared site password plus the person's name.
- Data: `data/site-data.json` (format `isaac.question_site`, see `docs/question-site-contract.md`): a `beamtime` header block (folder, readers used, element/edge, logbook facts with file and line), and cards with title, detail, suggestion (value, confidence, reason, evidence quotes), context blocks (quotes, value tables, curve images), and the answer shape (choice, yes/no, text, number).
- Hosting: Vercel, Node functions plus static files, no build step, no framework, no third-party requests.

## Capabilities and Constraints
- Plain JavaScript modules and one stylesheet; every server string set with textContent.
- Strict CSP: no external fonts, scripts or images.
- Answers save on every click; a 409 shows a colleague's newer answer instead of overwriting.
- Keyboard shortcuts (Y, D, S) with guards.

## Brand Commitments
Plain "ISAAC" wordmark in text. No official ISAAC, SSRL or DOE logos or colors (confirmed 22 Nov 2026).

## Evidence on Hand
Real beamtime data lives outside the repo and is never committed; the repo's sample data under `apps/question-site/data/` is synthetic.

## Product Principles
1. The question first, in plain words; the evidence directly beneath it.
2. Provenance is always visible: which beamtime, which file, which line.
3. Confirming a correct suggestion is one click; correcting it is never more than two.
4. Nothing is guessed or pre-filled on the scientist's behalf.
5. Concise: no repeated text, no software jargon (no header codes, no field paths).

## Accessibility & Inclusion
WCAG 2.2 AA: keyboard-complete, visible focus, 4.5:1 text contrast, screen-reader status for saves.
