# Remote branch inventory — 2026-08-20

**Nothing has been deleted. This is the mechanical proof that must precede a deletion, and the
exact command that would perform one.**

`CLAUDE.md`'s cleanup discipline is that a deletion is preceded by a `git rev-list --count` proof
that the branch contributes nothing `main` does not already have. A previous session applied that
to LOCAL branches (141 → 8, with three superseded ones RENAMED to `preserve/*` rather than
deleted). This is the same measurement for the REMOTE.

## Why the deletion is not performed here

`origin` is the shared organization remote `ISAAC-DOE/isaac-metadata-assistant`. Deleting 132 refs
from it is an outward-facing action on infrastructure other people use, and it is not this agent's
to take unilaterally — the same reason no agent applies a migration or authenticates to `/krish`.
The proof is the deliverable; the deletion is one command, below, for a human who wants it.

**It is also genuinely reversible from this file**, which is why the SHA is recorded beside every
branch rather than only the name. Any branch here can be recreated exactly:

```bash
git push origin <sha>:refs/heads/<branch>
```

## The measurement

```bash
for b in $(git branch -r --format='%(refname:short)' \
             | grep -v 'origin/HEAD$' | grep -v '^origin$' | grep -v 'origin/main'); do
  echo "$(git rev-list --count origin/main..$b)|$(git rev-parse $b)|$b"
done
```

`git fetch origin` was run immediately before, so `origin/main` is current.

**Result: 136 remote branches besides `main`. 132 contribute ZERO commits `main` does not have. 4 do not.**

## The 4 branches that are NOT fully merged — none is a deletion candidate

| commits ahead | branch | why it stays |
|---:|---|---|
| 2 | `origin/preserve/test-visual-responsive-sweep` | superseded work, deliberately renamed rather than deleted — this is its only copy |
| 4 | `origin/preserve/feat-run-page-api` | superseded work, deliberately renamed rather than deleted — this is its only copy |
| 13 | `origin/preserve/local-integration-qa` | superseded work, deliberately renamed rather than deleted — this is its only copy |
| 30 | `origin/feat/qc-answerable-and-server-stamped-attribution` | the OPEN pull request this session is working on |

`feat/qc-answerable-and-server-stamped-attribution` is the open PR. The three `preserve/*` branches
were deliberately renamed rather than deleted by an earlier session precisely because they are NOT
merged — they carry work that was superseded rather than landed, and the rename is what records
that. Deleting them would discard the only copy.

## The 132 fully-merged branches

Each contributes **0** commits that `origin/main` does not already contain. Every one was landed by
a merge commit, so its commits remain reachable from `main` and its GitHub pull request remains
readable after the ref is gone.

| sha | branch |
|---|---|
| `007727352398f55161e0ac92f1bd8dee08a13d8f` | `origin/feat/record-info-and-links` |
| `057d02476b4363f40818d7916a1e3a74b47032ca` | `origin/fix/list-degradation-disclosure` |
| `05cd7eb9925da099cc4257a13938707423e7cec7` | `origin/fix/sha256-exactness` |
| `0773f5e3b6ace6ead26b712f26c06754a53a23cc` | `origin/feat/suggestion-no-guessing` |
| `085b455a87dca2c564ccc61917f43e26e99e6c65` | `origin/fix/false-success-signals` |
| `127cc1e92e9340ce18a4bc84fd2d418e3a09cc56` | `origin/docs/dean-response-2026-08-12` |
| `159767673d2438c180c3cc01eb7a5bf312505208` | `origin/docs/workflow-vocabulary-deferral` |
| `16358aef03d10a740d99bd59d1c1ce3a6e377557` | `origin/fix/empty-measurement-consistency` |
| `171ce9d07ee0f26e4b0f7acb9699778c9a76d85e` | `origin/test/browser-a11y-responsive-baseline` |
| `1bf8f44a546f3b2af9065cc660f781dbd7cdd0b7` | `origin/feat/autosave-ownership` |
| `1c2311ba256f0780eafa5b6c43b6ec64c2fed744` | `origin/feat/run-fields-complete-writable-set` |
| `1d9b3df4fd62800d6136f037322c4e9a48b7a324` | `origin/feat/mcp-server` |
| `1db436b7ea2427bd9025cb3f4449e304b20e8789` | `origin/test/browser-mutation-completion` |
| `1e5ed627c47a2924d4e15c0ddbfc8f0cf3a608b6` | `origin/fix/startup-not-found-semantics` |
| `1fdd3ce2698e406773d35e7843cc97a04ebb7be6` | `origin/feat/run-scale-api` |
| `20120de460822b640a165d96c88df58bb8094e81` | `origin/chore/migration-0003-0004-approval` |
| `213e44daadc0f6501e61c6d04cb36c49de39b114` | `origin/feat/asset-references` |
| `216fa80792ad974b902d0cc98d37c524458a1812` | `origin/test/handler-concurrency-negative-controls` |
| `2211d6c617f842ec9087fd3cc3df7fcdc9befb39` | `origin/feat/identity-trust-seam` |
| `2302276a12270bf0bb830b4c903f72a8b58275fc` | `origin/feat/evidence-graph` |
| `248784c85b389f9ef4b63e0a63cff808a6111d19` | `origin/docs/truthfulness-security-sweep` |
| `2613cb810f31f27ef5f849694c375b4584985789` | `origin/docs/0002-rewitness` |
| `26528456c67d827a83479e2291c4e27c1b85184c` | `origin/feat/identity-probe-and-authority-discovery` |
| `29b95aa7bcd3628ea38d0c94fbbb553b36e80ff6` | `origin/fix/durable-compare-and-swap` |
| `2a32e14f21e80847bb9c573dce57b0169eb8ddb8` | `origin/feat/tutorial-scope-isolation` |
| `2ae33ab531cb0dd58cb392b424600642887ee671` | `origin/fix/graphify-metric-disclosure` |
| `2bc4753a916db98b69cf37a10fe1a3da4b105e2e` | `origin/fix/verification-evidence-honesty` |
| `2c48052e404e6268fa6f643bd7e7df2864404149` | `origin/fix/sub-resource-404-truthfulness` |
| `2ce9236a9f3b89ae57a161252529379526f00af2` | `origin/feat/run-domain-model` |
| `2df9085e7cfb9688342d32850f2329fbb709bd3f` | `origin/fix/edit-structured-answer-types` |
| `2f8f1b4165ea81a7dd5512f427ed700f20a5ee52` | `origin/docs/session-2026-08-18-phase-context` |
| `33066b01f84c48dff8a683e570d70a6f3f3b6592` | `origin/feat/revision-history` |
| `35158e8149687225cd6df0f37e9eca87bcfc8ff8` | `origin/docs/run-scope-decision-packet` |
| `35a1daa053c9b4336732e90f23290e50227b6ed6` | `origin/test/lifecycle-concurrency` |
| `3686df13e9a80a63f88b002b5f589569128f8ab0` | `origin/fix/run-card-responsive` |
| `3794a5e09d99456f0d66ce7985c0f4ad20a92529` | `origin/fix/db-recon-leak-scan-escaping` |
| `390b873941673b1bfb18b4b868f975d167788e36` | `origin/feat/statistics-visual-first` |
| `3b2dcf59b5c05eee2bdb455bb91e84fb5a415e58` | `origin/feat/transcript-capture` |
| `3bf2347444b6608b34d18577fd2f16cc92680212` | `origin/fix/schema-string-gate-exactness` |
| `3d4f4ba2dc3240ae1a3b51ade757dd6e91b02a68` | `origin/feat/runs-shadow-write` |
| `3e658361a2718c42d2a30e3a65f33eaf60ebce05` | `origin/docs/hosted-qa-checklist` |
| `3e9c29d7b1b997baf6eb09552e01f6d7450e7603` | `origin/chore/identity-observation-and-probe-removal` |
| `3eb502280d79b3219e4071b0be71b8e707f1179d` | `origin/fix/baseline-closure-a11y-g3-zoom` |
| `43837b9c522e5ab69bb4044c9a0f18ec7ebdcf1f` | `origin/docs/migration-approval-packet` |
| `497e8dbcba3ee4cf1dd9486f38a222a7deb49fe1` | `origin/feat/mcp-slice` |
| `4b4e1371b28a94e9b6252c22f4fbea095a8864a4` | `origin/feat/run-vertical-slice` |
| `4caa5d6605d4c449520500e2ed503a848ce20573` | `origin/fix/statistics-coldstart-and-privacy-layout` |
| `4dd4ef2617a9adb8af5a5811eae954a33643a420` | `origin/feat/run-override-routes` |
| `4e489447fd1191598b7678e145cfa131ca8e250b` | `origin/docs/public-safety-opsec-redaction` |
| `5174f61d3d24e1259886b37e862f8453e69643f3` | `origin/fix/validation-truthfulness` |
| `5386b7b3c85ea89f2bda5446de8f9748a1ef7442` | `origin/test/truth-path-guard-scope` |
| `54518c9ca4f292e6d62de928360953c4d45c5212` | `origin/feat/my-experiments-polish` |
| `57dee17785450d8e0d8eff63e189746011082efb` | `origin/feat/connect-agent` |
| `5b337509225cedb901b4dca798cd90f5f89f0d2c` | `origin/fix/reset-safety` |
| `5bfe3d5e3c789b08ddf6d2bdac24895c20b9060d` | `origin/docs/0001-applied-addendum` |
| `5e099eb98a0663e78afdab47c6c67478db3b62ed` | `origin/fix/ended-worked-example-copy` |
| `5fe3dbb6173c2813ce0088bb6563f3e7168820f3` | `origin/fix/retention-and-narrow-axe` |
| `60eb274a640310ddb7ad6f904cad6b6c604acdc5` | `origin/docs/identity-seam-reversal` |
| `61c733846d269510e7b794a2bcc5885651e154f3` | `origin/feat/parity-slice` |
| `6265bf6837f0febfe34d30519c399d4c2635e5fb` | `origin/fix/statistics-honesty-and-polish` |
| `628f6efd4199b1f56fe6dd1d0fd6dfed90df84a5` | `origin/feat/provider-seams` |
| `656202d4b454848be7df9bfbd61db9b72c095587` | `origin/ci/release-gate` |
| `6ca56f161119d52d3c0ddb28fbb6cf7dabcd5e8e` | `origin/feat/private-verification-wiring` |
| `702c7df816eaf7a005d7a043f93546dbb85aa94b` | `origin/docs/mcp-capability-audit` |
| `709a8edd49bb05879fef7a737fa5bef790e4508d` | `origin/feat/guided-tutorial` |
| `70cd222b909f87f14dcd7374a98b3446afda68e7` | `origin/feat/deterministic-mutation-harness` |
| `7378f42994a422cb13924c85bac0fa8d917f14a0` | `origin/fix/silent-input-loss` |
| `73f4b4232ef6d5b86bbf2134a42a53b6e8856dff` | `origin/feat/unmapped-notes` |
| `76ed36163eb21d62eb654e919e570bc806ee611d` | `origin/docs/poster-evidence-package` |
| `771915349dd5f28cc095446a9364943f85896c83` | `origin/feat/submit-slice` |
| `7aec5efa11c46e7ef4f5469f4f46ee13c1e4f814` | `origin/docs/baseline-closure` |
| `7c7fa47c8f06a0c8ab8316eb089c2a305faab934` | `origin/docs/branch-protection-request` |
| `7d2afb43dada1a181c0f11444bcf6539edb3cb0b` | `origin/test/browser-mutation-coverage` |
| `7e550a50550606f76b02306dad0addfcb17f8268` | `origin/feat/experiment-graph` |
| `7f4e357e23b57aee241afdfd754f8f8772341eb5` | `origin/feat/compare-runs` |
| `807d110778a0d7ef780fe9b943be62436ee47c26` | `origin/test/run-workspace-async-timeout` |
| `80dc046e8ce4d4e33eb941f48a134b36fed02120` | `origin/fix/openapi-prose-truth` |
| `8961413cc68549aa664dfd19edcac9b1475dd8a6` | `origin/feat/available-metrics-and-adapters` |
| `8cfcb3184032d5a2eaef7ee24d3fc4223d713e58` | `origin/feat/validate-review` |
| `8e59dbaa4c1a69c21b2e1727719055a22fc483a6` | `origin/docs/baseline-definition-and-governance` |
| `90b8643d0ce29e505f12a403e9ed408dd8caae4f` | `origin/feat/run-override-ui` |
| `90f1110454ffe9feed6b9357eb181e1d0e5d6d37` | `origin/docs/actor-seam-survey` |
| `9218b36747f745da1de81e2420c44de688849dc6` | `origin/docs/migration-reverification` |
| `95caf9e6b74f3db35050bc9e5a131b891a813dd5` | `origin/test/graph-timeout-adjudication` |
| `9739c626a6a462d666f97177983eedb6a9502aa7` | `origin/feat/export-fan-out` |
| `9a8651eda25811d0723ac270d8b08ebb14b4e990` | `origin/docs/scale-remeasured` |
| `9abb44c5b1a44e816b6d2259265033372b498f5a` | `origin/feat/record-verification` |
| `9c86a759f29a4861c80d8f248c0fd78e76069d52` | `origin/feat/conflict-resolution` |
| `9ca3ca8a106b5c293f85de3f0b271879c86ba8b7` | `origin/docs/checklist-correction` |
| `9d4788d8bd5acd1c55e4a1f051f6f6df304ceee1` | `origin/feat/run-removal` |
| `9f728a5165796df94818ceee73a5d42f40ff9d30` | `origin/feat/statistics-shell` |
| `a52e15f7429b2258e080750f79bffae73601a235` | `origin/feat/provenance-model` |
| `a5541e4b443fa4894c1fc0f989faeb69bfdc8c2b` | `origin/feat/run-query-filter` |
| `ada4bee97824ee5ec0f48242966587b51092bba3` | `origin/fix/a11y-baseline-aggregate-invariant` |
| `adcd30a09fcccb85e2b3325b6d557949b6513366` | `origin/feat/run-relevance-filtering` |
| `ade33cf629f05f934b9e63f864bab7635661e59a` | `origin/fix/cache-correctness-and-openapi-claims` |
| `b2bf3e749ecaf4b421e1745d91463a9c9d052fca` | `origin/fix/honesty-and-dead-controls` |
| `b3b76cdcda97e678463fb2c615369a74d03cd624` | `personal` |
| `b3b76cdcda97e678463fb2c615369a74d03cd624` | `personal/main` |
| `b88333cf7ed66f2d48efb9834c5f072aa128023a` | `origin/fix/exact-identifier-semantics` |
| `bb9041d1cb635f88e203d1761ac7aa365a12b5de` | `origin/docs/session-checkpoint-2026-08-18` |
| `bdff8f5a1490d671722e9f886c4119ddbe2a6e4d` | `origin/fix/attribution-uploaded-by` |
| `c1ae21bfa332ed881e0dd9b9640852924e94ce09` | `origin/ci/concurrency-cancel-superseded` |
| `c366c7a02061e49984d9c8a6543ee435aa55ef2e` | `origin/test/validator-qa-package` |
| `c581214005ed29d0c86f4dbc3e6c00a3c4542dd5` | `origin/fix/no-client-bearer` |
| `c91d95e8b888e6671b02b7e0d4414f5fb937a2eb` | `origin/fix/edit-refuses-unstorable-hash` |
| `cc9fbe0580b762c964c989b878a0ba2b3d65d34f` | `origin/fix/evidence-item-isolation` |
| `cd78b3725782040eadc35cab516719f47bb19a0d` | `origin/feat/p36v1-hosted-qa-fix-forward` |
| `ce0221b15aba573bc14f6b66125d5db59ced3883` | `origin/feat/deterministic-validation-and-db-recon` |
| `ce4191e8f0d5a46dd4ec8efb4049c050b277e3ba` | `origin/feat/privacy-consolidation-governance` |
| `cf339f1332ed6d86b004eed14e4166ac7bea826c` | `origin/feat/conflict-resolution-ui` |
| `d21a757df3ec8f241cb0602ce7bea48112a21861` | `origin/feat/verification-disclosure-and-graphify-benchmark` |
| `d53ea6a07dfca2927c9533e063c4c6b3862118a6` | `origin/docs/ai-integration-decision-packet` |
| `dafa0fd80b49718f81d5d707a96129812408514c` | `origin/feat/my-experiments-create` |
| `de8749376bc993a132019529bf7f436cd56f6e9d` | `origin/docs/pod-restart-durability` |
| `e181963ad958e1e878c790f66897d822bb10a9c1` | `origin/feat/guided-demo-entry` |
| `e21d1832be2ab55a32a753374212698ae63467f2` | `origin/fix/session-expiry` |
| `e4778a711c8d82cad005fe031d42d68caba18f5d` | `origin/docs/angel-packet-refresh` |
| `e7fd755b9ceeaa1e8f9ad567835537fca9b697d5` | `origin/feat/deployed-postgres-recon` |
| `e8270ce55910c4b05fffce3538b588073a9136ea` | `origin/test/truthpath-characterization` |
| `e98e77dee034f1b2ff9e72ed25f5d2382bff54fe` | `origin/feat/validate-and-review` |
| `edb4cf797ecc4076668c0818280d35946fa77757` | `origin/feat/run-browser-ui` |
| `f057ac81b04f5062dac698500c46b44828187332` | `origin/test/visual-sweep-port` |
| `f188c23e09385c45cc3557477e7e244079412d11` | `origin/fix/reset-write-window` |
| `f193508a9c7d9cc151fc899af2cb03c550ced54b` | `origin/fix/migration-anchor-proof` |
| `f5da173828213d8bbfb2a783ca000a8559ec0bcf` | `origin/fix/input-loss-round-2` |
| `f66673ce6e5c5c0c527f1906b119f234c55984c0` | `origin/docs/capture-spec-restale` |
| `f7c3992f5f82b70cf51e96449ff8141839774873` | `origin/fix/graph-indigo-visible` |
| `f8bf976281621cb4c17643ab11c5f8875fb4d9bb` | `origin/fix/hosted-session-down-state` |
| `f91c91496bcb68ad2b290467e0d563d88620c42f` | `origin/fix/hydration-race-404` |
| `fd36bf23adab07dfc5c5a0204f4d5b5cc41ef724` | `origin/fix/settings-api-honesty` |
| `fe0376dfb90de7a32a11eab0350161d94d0c0b79` | `origin/docs/phase-closure` |

## The command, if a human wants it

```bash
# Re-run the measurement FIRST — this file is a snapshot and `main` moves.
for b in $(git branch -r --format='%(refname:short)' \
             | grep -v 'origin/HEAD$' | grep -v '^origin$' | grep -v 'origin/main'); do
  if [ "$(git rev-list --count origin/main..$b)" = "0" ]; then
    echo "${b#origin/}"
  fi
done > /tmp/merged.txt

# Read it, then delete in one push rather than 132.
xargs -a /tmp/merged.txt git push origin --delete
```

**Re-run the measurement rather than trusting the table above.** A branch that was merged when this
was written is still merged; a branch that has since gained a commit is not, and this file cannot
know that.
