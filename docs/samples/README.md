# Sample records — SYNTHETIC Phase-4 demo output

These files are **synthetic demo outputs**, safe to commit and NOT real data. They were
produced by the Phase-4 end-to-end path — `build_draft` (deterministic extraction of the
committed synthetic fixtures `tests/fixtures/synthetic/{mock_campaign.csv,raw_scan_listing.txt}`)
→ `complete.apply_answers` (applying the simulated human answers in
`tests/fixtures/synthetic/xanes_completion_answers.json`, each recorded as `user_confirmation`
evidence) → `export.export_draft` (schema-gated) — using the fixed reproducible record id
`01JQZ0SYNTHXANESDEMO000000`. `01JQZ0SYNTHXANESDEMO000000.json` is the official ISAAC v1.05
record (it passes `validate_official` and `isaac audit`), and
`01JQZ0SYNTHXANESDEMO000000.evidence.json` is its evidence sidecar; nothing in either file was
guessed by the system — every value traces to a committed synthetic fixture, the fake year-2099
session makes the data unmistakably not real, and no real SLAC/SSRL data was involved.
