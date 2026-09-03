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
`test/rates_test.py` enforces this and is the only test that reads the skill.

**No real payroll data, anywhere.** Payrolls are personal data under the GDPR and
sick-leave records are health data. Every fixture is invented and derived from a
seed. Need a realistic case? `python test/generate_wide.py --seed 12345`.

**A finding needs a basis.** Statutory reference for groups A–J; for group K say
plainly that it rests on arithmetic. Do not invent an article to fill the field.

## Commands

```sh
python test/rates_test.py     # rates vs. the reference file. No dependencies. Run on any skill edit.
python test/skill_test.py     # packaging: frontmatter, references, manifests, licences, dates
python test/checks_test.py    # suite 1: static payroll, asserts its own answer key
python test/eval_skill.py --selftest      # free: checks the refusal grading itself
python test/run_tests.py      # all five, 50 seeds
python test/run_tests.py --seeds 300      # what CI runs
```

**Never run `test/eval_skill.py` unprompted.** It starts real Claude sessions and
costs about USD 2.4 per seed. It is the only test that exercises the *guidance* in
`SKILL.md` rather than the rules, so mention it when that guidance changes — and let
the user decide. Free modes: `--dry` shows what would be sent, `--selftest` proves the
grader discriminates, `--covering "id,id"` picks the cheapest seeds that inject the
scenarios you want measured. `--pair` runs the two-month fixture (the чл. 177/чл. 18
material no single sheet can hold); `--seeds-list "6,7,32"` runs exactly those seeds.

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
- **The verification date is in eight places** (stavki.md, SKILL.md `compatibility`
  and `metadata`, plugin.json, a badge plus a sentence in each README, and
  `.github/social-preview.html`). `skill_test.py` checks all eight — let it, rather
  than updating by hand and hoping.
- **The suite-1 fixture is generated.** If `test/generate_narrow.py` changes, rerun it
  to rebuild `test/vedomost_05_2026.xlsx`, and keep `test/expected_findings.md` in
  step — `checks_test.py` asserts that key exactly.
- **Adding a check or a scenario** has a checklist in `CONTRIBUTING.md`. Prove a new
  check has teeth: break something on purpose, confirm the suite goes red, revert.
- **Hooks are opt-in:** `git config core.hooksPath .githooks` once.

## Language

Code, comments and documentation under `test/` are English. Two things stay
Bulgarian because they are *data*: the spreadsheet column headers the checkers look
up by exact text, and the prompt and keyword patterns in `eval_skill.py`. The skill
itself — `SKILL.md` and `references/*.md` — is Bulgarian throughout, because it
speaks to Bulgarian payroll staff and quotes Bulgarian statute.

## Branching

`main` is protected. Work on a branch and open a pull request; CI must be green.
