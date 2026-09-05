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

## Commands

```sh
python test/rates_test.py     # rates vs. the reference file. No dependencies. Run on any skill edit.
python test/skill_test.py     # packaging: frontmatter, references, manifests, licences, dates
python test/checks_test.py    # suite 1: static payroll against the key in expected_findings.md
python test/eval_skill.py --selftest      # free: checks the refusal grading itself
python test/preflight_test.py # tools/preflight.py: clean is silent, each shape defect found once
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
- **The verification date is in the source plus eight copies** (stavki.md is the
  source; SKILL.md `compatibility` and `metadata`, plugin.json, a badge plus a sentence
  in each README, and `.github/social-preview.html` are the copies). `skill_test.py`
  checks all of them — let it, rather than updating by hand and hoping.
- **The suite-1 fixture is generated.** If `test/generate_narrow.py` changes, rerun it
  to rebuild `test/vedomost_05_2026.xlsx` — `checks_test.py` rebuilds the fixture and
  fails on a stale file — and keep the machine-readable key in
  `test/expected_findings.md` in step: `checks_test.py` parses that table and asserts
  row, check, severity, stated and due to the cent.
- **Adding a check or a scenario** has a checklist in `CONTRIBUTING.md`. Prove a new
  check has teeth: break something on purpose, confirm the suite goes red, revert.
- **`tools/` is not part of the skill.** `tools/preflight.py` checks whether a real
  payroll workbook can be audited at all — header row, formulas, period, missing
  columns, and the two values no file carries (КИД and ТЗПБ). It lives outside
  `skills/trz-expert` on purpose: SKILL.md promises prose only, and installing copies
  the skill directory whole. It never writes to the workbook — the file is evidence —
  and never guesses a period, because guessing the period picks the thresholds. Its
  column vocabulary is pinned against `trz_model.COLUMNS` by `preflight_test.py`.
- **Suite 6 may only compare a month with another month.** Every sheet in
  `test/generate_lifecycle.py` is internally correct on purpose — the arithmetic
  reconciles, the bases are right, each month would pass suites 1–4 alone. The only thing
  that disagrees is the sequence. A check in `lifecycle_test.py` that could be written
  inside one sheet belongs in another suite, and a break that stops corresponding to a
  bullet of I11 in `proverki.md` should be deleted rather than kept.
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
- **A company's layout is declared once** in a `mapping.yaml`
  (`tools/mapping.example.yaml`), not re-guessed monthly. A typo in a concept key
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
up by exact text, and the prompt and keyword patterns in `eval_skill.py`. The skill
itself — `SKILL.md` and `references/*.md` — is Bulgarian throughout, because it
speaks to Bulgarian payroll staff and quotes Bulgarian statute.

## Branching

`main` is protected. Work on a branch and open a pull request; CI must be green.
