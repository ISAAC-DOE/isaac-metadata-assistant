# Portal vocabulary snapshot

`portal_vocabulary_a1cb1c8.json` is a **verbatim copy** of `data/vocabulary.json` from the upstream ISAAC
repository, taken at commit `a1cb1c861f3e6eb506da33f27196b43312f240f6` (short `a1cb1c8`, 2026-10-25, "Merge pull
request #288 from changzhiai/fix-manifest").

- Source: https://github.com/ISAAC-DOE/isaac-ai-ready-record (`data/vocabulary.json`)
- SHA-256 of the copied file: `7d60a2f0383b936ac055c309596e2ba9afe9fb9a1b893fe217f88e7a52b8d0f8` (re-derive with `shasum -a 256`; `test_schema_proposals.py` pins it)
- It is a **labelled snapshot, not an authority**. The portal's own copy is the file the portal validates against and
  it may have moved since. `schema/isaac_record_v1.json` remains the authority on record structure (CLAUDE.md §1).
- It is used by Schema Proposals, to show which vocabulary lists the portal had and to check a drafted proposal
  against them, and by the LOCAL import (`local_import/bundle.allowed_values`) as the allowed values a field takes:
  the local export validates against the portal at this same commit (`local_import/portal.PINNED_COMMIT`), so the
  lists a question offers and `decide` accepts are exactly the ones that export accepts. No official-record
  validator reads it.
- It is deliberately NOT under `schema/` (that directory holds only the vendored official schema) and is refreshed only
  by replacing this file and the commit named here together.
