# GitHub settings — recommendations

Suggested repository configuration for presenting this prototype to mentors/reviewers. These are
**recommendations** to apply in the GitHub UI, not automation — this phase deliberately adds no CI
or workflow files. Confirm visibility and any public exposure with the project owner first, given
the data-governance obligations.

---

## Repository description

Short (the GitHub "About" field):

> Turn experiment metadata into validated, evidence-grounded official ISAAC records — a deterministic,
> no-guessing authoring assistant (synthetic-data prototype).

## Topics / tags

Suggested topics: `isaac`, `metadata`, `scientific-data`, `data-validation`, `jsonschema`,
`xanes`, `synchrotron`, `provenance`, `python`, `research-prototype`.

## Visibility

The repository is currently **public**. Public visibility does **not** grant reuse rights — the
license is still pending (see the README "License & provenance" section). Because it targets a
domain with real data governance, keep every real artifact out of git and confirm that no sensitive
data exists anywhere in history; all committed data must be clearly synthetic (see
[`data-governance.md`](data-governance.md)).

## Default branch & protection

- Default branch: `main`.
- Suggested branch protection on `main` once collaborators are added:
  - require a pull request before merging,
  - require at least one review,
  - require the test suite to pass (once CI is approved and added),
  - disallow force-pushes to `main`.

These are suggestions for when the repo has more than one contributor; a solo prototype can defer
them.

## README badges

None yet. Badges should be **meaningful**, and there is no CI to report on. Add a build/test badge
only after CI is approved and wired up — a badge that points at nothing is worse than no badge.

## Releases & versioning

- The package version is `0.1.0` (`pyproject.toml`). Treat the current state as an early prototype.
- When a milestone is worth marking (e.g. a mentor demo), create a lightweight annotated git tag
  (`v0.1.0`) and/or a GitHub release with a short note. Keep the version in `pyproject.toml` in sync.

## Issue templates

Optional and easy to over-engineer. If issues start accumulating, a single lightweight template is
enough — and it should include a **"no real data"** reminder:

> **Do not paste real or private experiment data.** Reproduce with the synthetic fixtures in
> `tests/fixtures/synthetic/` and describe the problem abstractly if it only appears on real data.

Skip heavier automation (multiple templates, actions bots) unless the project explicitly asks for it.

## Not recommended for this phase

- CI/CD workflows (`.github/workflows/`) — defer until explicitly approved.
- Dependabot / security-scanning bots — defer for an early-stage research prototype.
- A license file — **pending mentor/project decision** (see the README "License & provenance"
  section). Do not add MIT/Apache/etc. without approval.
