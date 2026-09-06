# Working in this repository

This repo ships one thing: `skills/trz-expert`, a Claude Code skill that audits
Bulgarian payroll documents. Everything under `test/` exists to keep it honest.
`CONTRIBUTING.md` is the full guide — this file is the part that is easy to get
wrong without noticing.

## The rules that are not negotiable

**No rate from memory. Ever.** Not a minimum wage, not a contribution percentage,
not a threshold — not in the skill, not in the tests, not in an answer to the user.
Every figure comes from `skills/trz-expert/references/stavki.md` with a source, a
status and a date. If a figure is missing, ask; do not reconstruct it, and do not
convert one from another year.

**The reference file leads; the test model follows.** `test/trz_model.py` keeps its
own copy of the rates because Python cannot compute without them. When the two
disagree, `stavki.md` is right and the model is wrong — never the reverse.
`test/rates_test.py` enforces this and is the only test that reads the rates.

**No real payroll data, anywhere.** Payrolls are personal data under the GDPR and
sick-leave records are health data. Every fixture is invented and derived from a
seed. Need a realistic case? `python test/generate_wide.py --seed 12345`.

**A finding needs a basis.** Statutory reference for groups A–J; for group K say
plainly that it rests on arithmetic. Do not invent an article to fill the field.

**Two sides that check each other must not compute the same way.** `trz_model.py`
(the fixture generator) and `scripts/rates.py` (the auditor's own rate reader) get
their numbers by two different paths on purpose — one a hardcoded copy
`rates_test.py` cross-checks, the other extracted fresh from the reference text at
call time — so a mistake in one is not invisible to the other. This was learned the
hard way, not assumed: `sick_daily_base()` was once called by both the generator and
`structural_test.py`'s checker, so a wrong formula in it agreed with itself and
passed every payroll suite at 60 seeds (`test/scenarios.md`, the "не по-малко от"
incident). This is not a rule against all shared code — `scripts/audit.py`'s
composition-solving method is ported verbatim from `test/structural_test.py` on
purpose, because that algorithm is the thing both sides already agree should behave
identically, and `audit_test.py` cross-checks the port against the original directly
rather than trusting a copy to have survived intact. The line: never let two things
meant to catch each other's mistakes get their numbers from one formula; sharing an
algorithm both sides already agree is correct, and proving the copy is faithful, is a
different thing. Do not "simplify" this duplication away.

**Fail closed.** An ambiguous rate (`for_period()` on two disagreeing rows), an
unmapped column, an unconfirmed reference status, a legal reading with more than one
defensible answer, a test that only counts findings instead of pinning their
figures — every one of these refuses or downgrades rather than resolves the
ambiguity for you. If a change makes one of these "smarter" by picking an answer
silently, that is the wrong direction for this project.

## Commands

```sh
python test/rates_test.py     # rates vs. the reference file. No dependencies. Run on any skill edit.
python test/skill_test.py     # packaging: frontmatter, references, manifests, licences, dates
python test/checks_test.py    # suite 1: static payroll against the key in expected_findings.md
python test/eval_skill.py --selftest      # free: checks the refusal grading itself
python test/preflight_test.py # scripts/preflight.py: clean is silent, each shape defect found once
python test/k_checker_test.py # scripts/k_checker.py: K5/K6 vs. generate_wide.py's manifest, 60 seeds by default
python test/audit_test.py     # scripts/audit.py: I1/B4/F5 vs. the manifest, B1/I5/B5 vs. hand-built and suite-1 fixtures
python test/komplekt_test.py  # suite 5: ведомост -> обр. 1 -> обр. 6 -> внесено -> счетоводство, one link at a time
python test/lifecycle_test.py # suite 6: five months of the same people, one timeline break at a time
python test/run_tests.py      # all five, 50 seeds
python test/run_tests.py --seeds 300      # what CI runs
```

**Never run `test/eval_skill.py` unprompted.** It starts real Claude sessions and
costs about USD 5 per seed on Claude Fable 5.1 (the default), about USD 2 on Claude
Sonnet 5 (`--model claude-sonnet-5`) — see `test/scenarios.md` for the comparison.
It is the only test that exercises the *guidance* in
`SKILL.md` rather than the rules, so mention it when that guidance changes — and let
the user decide. Free modes: `--dry` shows what would be sent, `--selftest` proves the
grader discriminates, `--covering "id,id"` picks the cheapest seeds that inject the
scenarios you want measured. `--komplekt` sends a whole month's document set — ведомост,
договори, обр. 1, обр. 6, платежен файл — and is the only mode that exercises I9, I10 and
the cross-document half of A9; its keyword universe has never been calibrated against a
paid transcript, so triage every miss before believing it.
`--pair` runs the two-month fixture (the чл. 177/чл. 18
material no single sheet can hold); `--seeds-list "6,7,32"` runs exactly those seeds.
More than 10 seeds in one run is refused without `--allow-expensive`. Every graded seed
is saved to `/tmp/trz-eval/results/`; `--regrade` re-scores those files against the
current keywords for free, and a seed directory that holds a paid transcript is not
rebuilt without `--overwrite`.

Suites pass only when every injected defect is found and **nothing else is raised**.
A false positive fails exactly like a miss.

## Things that break quietly

- **Three manifests and a mirror.** `version` lives in
  `skills/trz-expert/.claude-plugin/plugin.json` (Claude Code),
  `skills/trz-expert/plugin.json` (Agent Plugins 1.0 — GitHub Copilot and the
  awesome-copilot gate) and `.claude-plugin/marketplace.json`, and all three must
  match. `.github/plugin/marketplace.json` is a byte-identical copy of the marketplace
  for VS Code and Copilot CLI, which look there first. The Agent Plugins manifest has a
  closed field set — no `metadata`, no `userConfig`, ASCII kebab-case keywords only.
  Both plugin manifests sit *inside* the skill directory on purpose: installing copies
  the source directory whole and honours no ignore file, so a `source` of `.` would
  ship `test/`, the fixtures and any local `.venv` to deliver one SKILL.md.
  `skill_test.py` fails if `source` stops being `./skills/trz-expert`, if the versions
  drift, or if the mirror does.
- **Two READMEs.** `README.md` and `README.bg.md` are the same document. A change to
  one that skips the other is a defect; the figures in them must agree.
- **The verification date is in the source plus seven copies** (stavki.md is the
  source; SKILL.md/plugin.json `metadata.rates_verified`, a badge plus a sentence in
  each README, and `.github/social-preview.html` are the copies). `skill_test.py`
  checks all of them — let it, rather than updating by hand and hoping.
  `compatibility` used to carry an eighth, prose copy; trimmed (2.19.3) because the
  field is meant to state environment requirements, and the date was already
  machine-readable in `metadata` — do not put it back there.
- **`stavki.md` is an index too, since 2.14.4** — statuses, the per-section
  verification-date table (now with a file column) and the changelog, plus a one-line
  "Ставки по теми" bullet per topic. The rate tables themselves are in
  `references/stavki/<topic>.md`. `test/rates_test.py`'s `TEXT`, `skills/trz-expert/scripts/preflight.py`'s
  `regime_boundaries()` and `test/findings.py`'s citation grounding all read the index
  plus every topic file concatenated, not the index alone - a rate or a citation moving
  into a topic file must not go blind to any of the three. `skill_test.py` pins the
  exact set of files under `references/stavki/` against the index's own linking bullets,
  the same way it does for `references/proverki/`.
- **The suite-1 fixture is generated.** If `test/generate_narrow.py` changes, rerun it
  to rebuild `test/vedomost_05_2026.xlsx` — `checks_test.py` rebuilds the fixture and
  fails on a stale file — and keep the machine-readable key in
  `test/expected_findings.md` in step: `checks_test.py` parses that table and asserts
  row, check, severity, stated and due to the cent.
- **Adding a check or a scenario** has a checklist in `CONTRIBUTING.md`. Prove a new
  check has teeth: break something on purpose, confirm the suite goes red, revert.
- **`proverki.md` is an index, not the checklist.** Since 2.14.4 it carries only every
  check's title, grouped A–K; the full text — basis, arithmetic, example — is in
  `references/proverki/<letter>.md`, loaded only for groups SKILL.md's step 3a leaves
  open. `skill_test.py`'s bullet-count regex still runs against the index (the title
  lines it needs are still there, just trimmed), but the set of files under
  `references/proverki/` is pinned separately, against the letters the index's check ids
  actually use — a stale or missing group file fails on its own, not just as a broken
  link. `test/findings.py`'s citation grounding reads every file under
  `references/proverki/` too, not only the index, since a citation can now live in either
  one. Edit the group file's content; keep the index's title line in step only if the
  title itself changed.
- **`skills/trz-expert/scripts/` ships with the plugin, since 2.16.0.** It used to be
  `tools/` at the repo root, outside `skills/trz-expert`, because installing a plugin
  copies the skill directory whole and `SKILL.md` once promised prose only. That promise
  cost every installed user the two scripts entirely — they could only ever be reached
  from a cloned checkout, never from `/plugin install`. `scripts/preflight.py` checks
  whether a real payroll workbook can be audited at all — header row, formulas, period,
  missing columns, and the two values no file carries (КИД and ТЗПБ). It never writes to
  the workbook — the file is evidence — and never guesses a period, because guessing the
  period picks the thresholds. Its column vocabulary is pinned against `trz_model.COLUMNS`
  by `preflight_test.py`. Two shapes added 2026-09 close a real gap between the 15
  `generate_shapes.py` scenarios already covered and a document-ingestion review that
  found it: `data_range()` used to stop at the FIRST row matching a totals label, so a
  department subtotal earlier in the block silently truncated every real employee row
  after it out of the audited range with no signal at all - now blocking
  (`MULTIPLE_TOTALS_CANDIDATES`, S16), on the same "ambiguous → refuse, never guess"
  principle as everywhere else here. A wholly blank row inside the data block (a spacer,
  or an inserted employee never filled in) was invisible to every formula/cached-value
  counter, since there is nothing in an empty row for either to count - now reported
  (`BLANK_DATA_ROW`, S17). Two other reviewed gaps turned out not to be gaps: multiple
  header rows already score by concept match rather than assume row 1, and Excel-serial
  vs. text dates are moot since `sheet_period()` only reads string cells.
  `scripts/k_checker.py` sits beside it, same reasoning, and
  computes only K5 (a hand-typed total) and K6 (rounding) from a real workbook — the two
  group-K checks that ask nothing about any column but the one being checked. It walks
  every header on the sheet, not only `preflight.py`'s known concepts: limiting it to
  those once meant 0 of 28 injected K5 defects were found, because a real file's benefit
  and deduction columns are not all in that closed vocabulary. `test/k_checker_test.py`
  checks it against `generate_wide.py`'s manifest, not only a hand-built fixture, for
  exactly that reason. Moving the directory took `sys.path` edits in both test files,
  `preflight.py`'s own `SKILL_DIR`-relative path to `stavki.md`, and the pre-commit
  hook's trigger regex - a change under `scripts/` that stops matching that regex would
  go untested locally again, the exact failure mode the move was meant to close.
- **`scripts/audit.py` (2.18.0, extended 2.19.0 and 2.19.5) covers I1, I5 (narrow),
  I8, K2, B1, B4, B5, F5, and F1/F9/F10's insurable-income-side composition - not the
  rest of B/F/I/K.**
  Each is mechanical (a row's own numbers, or a rate read fresh from
  `references/stavki/` via `scripts/rates.py`, never typed into either file) and safe
  for a generic tool - B2/B3/B6 need a company-specific number `mapping.yaml` doesn't
  carry, F2/F3/F4 need a birth date or labour-category classification no payroll
  column carries, F6/F7/F9's remaining (taxable-base) piece needs the same
  composition method PLUS every placement of the чл. 19, ал. 2 relief enumerated
  against it - a future increment, not attempted yet because
  `test/structural_test.py` needed several seed-specific bug fixes to get that
  combination right even against the synthetic model - F8 needs the annual
  reconciliation one workbook can't hold, and K1/K3/K4/K7/K8 are `k_checker.py`'s
  same closed-vocabulary risk.
  Building it against `generate_wide.py` at scale (not just a hand-built fixture)
  found a real, pre-existing `preflight.py` vocabulary bug before it ever shipped:
  "НЕТО преди удръжки"/"НЕТО за изплащане" and "Вноски работодател ДОО+ТЗПБ"/"Вноски
  работодател общо" both collapsed into one concept each, raising the blocking
  `DUPLICATE_CONCEPT` signal on every realistic fixture and stopping every check cold -
  split now, the same way "Клас %"/"Клас сума" already were. B1/B5 also went through
  two rounds of false positives from partial attendance (part-time hours, then a
  partial month from leave/sick days) before landing on "the highest count declared
  on the sheet" as the least-wrong stand-in for the full-time/full-month norm this
  script has no public-holiday calendar to compute directly - the suite-1 fixture's
  own part-time row (Стефка Ангелова) caught the first one. The insurable-composition
  pass (ported from `test/structural_test.py`'s "solve the composition" method) is
  gated on the sheet having zero unrecognised columns - a real company's mapping.yaml
  has to declare every administrative/breakdown column as `ignore` for it to run at
  all, same reasoning, and `F10_in_kind_asymmetry`/`F10_excess_asymmetry` are only
  half-covered (the taxable-base side of the same two ids is the deferred piece) -
  verified directly against `test/structural_test.py`'s own reference implementation,
  not only the manifest, because the two share ids with a check this file doesn't do.
- **`scripts/finding.py` is the one place `audit.py` and `k_checker.py` build a
  finding.** Before it, the two scripts built findings as ad hoc dicts with different
  field names for the same idea, and neither carried a `basis` field at all - a real
  gap against the "a finding needs a basis" rule above. `make_finding()` refuses to
  build a finding whose id has no entry in its `BASIS` table and no basis passed
  explicitly, so the rule is enforced at construction, not left to whoever renders the
  report afterward. `test/findings.py` imports this table for the ids `audit.py`/
  `k_checker.py` raise instead of keeping a second, driftable copy - the same
  single-owner principle CLAUDE.md states for rates, applied to citations. `severity`
  defaults to `дефект` when the basis is arithmetic (otchet.md's own hard rule for
  group K and internal-contradiction findings) and stays `None` for a citation basis -
  `scripts/rates.py` deliberately does not read a stavki.md row's status, so which
  severity a statutory finding earns under otchet.md's status-caps-severity rule stays
  the model's to apply, unchanged from before this module existed. `confidence`
  defaults to `изчислено` on every finding either script raises - provenance, not a
  second severity; otchet.md's `Увереност` field asks the model to keep it when a
  script's finding is repeated in prose.
- **`test/eval_skill.py`'s `grade()` checks a live model's own `nachisleno`/`dalzhimo`
  against ground truth, for the wide fixture only.** `structural_test.py`'s checker
  already computes both figures for nearly every scenario it detects (`Findings.add()`'s
  two numeric arguments) - `_generate()` now also runs that checker against the fixture
  it just built and stores the result as `man["expected_amounts"]`, so grading a live
  session's own stated/due numbers needs no second, driftable copy of "the right
  answer" taught to every one of `generate_wide.py`'s 28 mutations. A mismatch is
  reported in `amount_mismatches`, never folded into the identified/located/missed
  score: inventing a tolerance that decides pass/fail would be exactly the kind of
  silent resolution CLAUDE.md's "fail closed" rule forbids. Pair and komplekt have no
  equivalent oracle yet - `expected_amounts` is absent there, and `_amount_mismatch()`
  is a no-op with nothing to compare against.
- **`scripts/audit.py`'s `check()` returns `(findings, coverage)`, not findings alone.**
  A finding says what is wrong; nothing said what was actually looked at, and a clean
  sheet reads identically to one the composition pass never ran on at all. Coverage is
  one dict per sheet: rows found, and - for the insurable-income composition pass
  specifically, the one check here gated on the whole sheet having zero unrecognised
  columns - whether it ran, why not when it didn't, and how many of its rows were
  evaluated versus skipped at the cap or with no accruals for work. `coverage_report()`
  renders it under its own "Обхват" heading; `otchet.md`'s new "Удостоверение за одита"
  asks the model's own report to state the same kind of thing for the checks it does in
  prose - counts, never a percentage, same reasoning as "Без процент на покритие"
  already gave the coverage table above it. Four call sites needed the tuple
  (`audit.py`'s own `main()`, three in `audit_test.py`); nothing else calls `check()`.
- **Suite 6 may only compare a month with another month.** Every sheet in
  `test/generate_lifecycle.py` is internally correct on purpose — the arithmetic
  reconciles, the bases are right, each month would pass suites 1–4 alone. The only thing
  that disagrees is the sequence. A check in `lifecycle_test.py` that could be written
  inside one sheet belongs in another suite, and a break that stops corresponding to a
  bullet of I11 in `proverki/i.md` should be deleted rather than kept.
- **The комплект chain is built forward, and that is what makes it testable.** In
  `test/generate_komplekt.py` обр. 1 comes from the payroll, обр. 6 from обр. 1 and the
  payments from обр. 6 — so a break stops the copying at one link and the other three
  still agree. Break that ordering and one mutation lights up three checks, which is
  exactly what a real filing compiled from wrong data does NOT do. `ORDER` and `GROUPS`
  encode it; `komplekt_test.py` asserts that one break from each group at once stays
  separable. `breaks_for_seed()` is the single answer to "which links does this seed
  break" — the eval and `--covering` both call it rather than each keeping a copy.
- **Pre-flight reports signals, not prose.** Every check emits a stable id
  (`NO_PERIOD`, `DUPLICATE_CONCEPT`, …) and the Bulgarian report is rendered from
  them. Assert on ids: `test/generate_shapes.py` plants one shape defect per fixture
  and the suite requires a clean file to raise **nothing** and each defect to raise
  its own signal and nothing else — a false positive fails like a miss, as everywhere
  else here. Adding a shape means a mutation in `generate_shapes.py`, its signal in
  `SHAPES`, and proving it: break the detection, watch it go red, revert.
- **A company's layout is declared once** in a `mapping.yaml`, templated by
  `scripts/mapping.example.yaml`, not re-guessed monthly. A typo in a concept key
  blocks rather than doing nothing quietly, and a mapping pointing at a column that is
  no longer there is reported as stale. The file holds headers and КИД only — no
  personal data — so it belongs in version control.
- **Hooks are opt-in:** `git config core.hooksPath .githooks` once.
- **A fourth channel with no manifest.** `.agents/skills/trz-expert/SKILL.md` is what
  Codex CLI's repository-skill discovery finds — no plugin, no marketplace, just that
  path. It is a pointer, not a copy: its body names the five canonical files by exact
  path and tells Codex to go read them, and its frontmatter `description` must equal
  `skills/trz-expert/SKILL.md`'s. `skill_test.py` checks both; a rename on one side
  without the other breaks it.

## Language

Code, comments and documentation under `test/` are English. Two things stay
Bulgarian because they are *data*: the spreadsheet column headers the checkers look
up by exact text, and the prompt and keyword patterns in `eval_scenarios.py` (split
out of `eval_skill.py` in 2026-09). The skill
itself — `SKILL.md` and `references/*.md` — is Bulgarian throughout, because it
speaks to Bulgarian payroll staff and quotes Bulgarian statute.

## Branching

`main` is protected. Work on a branch and open a pull request; CI must be green.
