# Phase 23 — Tiny Cleanup (plan)

Date: 2026-07-16
Status: Approved for implementation
Base commit: 17b5fff

Goal: clean up the small remaining Phase 22 issues and current-doc honesty
bugs before Project Memory (Phase 24) starts.

Arc context and scope decisions:
`docs/superpowers/plans/2026-07-16-phases-23-26-arc-decisions.md`

## Slices

### P23A — Honest completion copy

Fix the post-export / zero-question state where the completion screen can
show `0 / 0`.

- Do not show `0 / 0`.
- Use clear, honest copy (e.g. "No open questions." / "All required
  confirmations are complete." / "Nothing else is required for this
  record.").
- Keep the normal counter when there are actual open questions.
- Add/update tests.

Known location: `apps/web/src/screens/GuidedCompletion.tsx` counter renders
at ~lines 200 and 241 (`{answered.length} / {total}`).

### P23B — Breadcrumb link in export loading state

Fix the transient non-link breadcrumb in the export loading/error state.

- Pass the record id to `TopBar` where appropriate.
- Sweep nearby loading/error branches for the same issue.
- Add/update navigation tests.
- Do not redesign routing.

Known location: `apps/web/src/screens/ExportReadiness.tsx` loading/error
branch near line 82.

### P23C — Amber advisory contrast

Evaluate and, if safe, improve advisory/needs-you amber text contrast.

- Keep the same hue family and semantic meaning.
- Do not use PASS green or FAIL red.
- Target at least WCAG AA (4.5:1) for normal text where feasible.
- Document computed contrast ratios in the slice report.
- Spot-check advisory, needs-you, assistant caveat, and runner/chrome
  usages.
- Add/update tests if style-token tests exist.

Known location: `apps/web/src/styles/tokens.css` — `--advisory-text`
(#9a6f24) on `--advisory-bg` (#f9f1df); `--needsyou-text` on
`--needsyou-bg` (line ~82).

### P23D — Health build identity

Add additive commit/build identity to `/api/health`.

- Current health fields unchanged.
- New `commit` field: `ISAAC_BUILD_COMMIT` first, `RAILWAY_GIT_COMMIT_SHA`
  fallback, `null` locally when neither exists.
- No auth behavior changes; no deployment architecture changes.
- API tests for env override and null default.
- Docs note in `docs/deployment.md`.
- If Railway does not automatically expose the commit env var, report it;
  leave the field null and document the limitation rather than changing
  Railway config (unless the change is tiny and explicitly safe).

Known location: `apps/api/isaac_api/routes.py` health route (~line 90).

### P23E — Docs truth micro-fixes

Fix only current misleading docs. Targets to inspect and update if still
wrong:

- README CI description
- `docs/project-memory-map.md` outdated "no web app" / "UI back burner"
  claims
- `docs/operator-playbook.md` stale claims
- `docs/query-cookbook.md` stale real-data/UI claims
- `docs/deployment.md` stale "rate limiting deferred to Phase 21" note
- `docs/ui-local-dev.md` missing P22 navigation/Help behavior
- any current doc that says frontend CI is absent
- any current doc presenting pre-P21/pre-P22 behavior as current

Do not broadly rewrite historical design handoff snapshots, dated planning
docs, or mentor-decision history. If a historical doc is confusing but
should not be rewritten, add a minimal "historical snapshot" note only if
necessary.

## Non-goals

Project Memory implementation, new Graphify endpoints, assistant changes
beyond docs if necessary, search, real-data upload, truth-path changes,
schema changes, deployment architecture changes, auth changes, broad visual
redesign, dark theme, Storybook, visual regression SaaS, rate limiting,
record indexing, related records, graph explorer.

## Verification before final push

- full Python tests, full API tests, full frontend tests, frontend build
- official validation PASS; audit 33/33
- no schema diff; no truth-path diff under `src/isaac_records/`
- no `examples/` or `graphify-out/` staged; no real/private data touched
- no deployment/auth config changes
- CI green after push; Vercel deployed/READY; Railway health 200
- health response checked for new commit field behavior

## After Phase 23

Run only P24.0 — Project Memory design mini-spec (regenerate Graphify
locally, inspect artifacts, produce spec in `docs/superpowers/specs/`),
then stop for user review before any P24 implementation.
