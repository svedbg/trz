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
python test/run_tests.py      # all four, 50 seeds
python test/run_tests.py --seeds 300      # what CI runs
```

**Never run `test/eval_skill.py` unprompted.** It starts real Claude sessions and
costs about USD 2.4 per seed. It is the only test that exercises the *guidance* in
`SKILL.md` rather than the rules, so mention it when that guidance changes — and let
the user decide. `--dry` is free and shows what would be sent.

Suites pass only when every injected defect is found and **nothing else is raised**.
A false positive fails exactly like a miss.

## Things that break quietly

- **Two manifests.** `version` lives in both `.claude-plugin/plugin.json` and
  `.claude-plugin/marketplace.json` and must match.
- **Two READMEs.** `README.md` and `README.bg.md` are the same document. A change to
  one that skips the other is a defect; the figures in them must agree.
- **The verification date is in seven places** (stavki.md, SKILL.md `compatibility`
  and `metadata`, plugin.json, and a badge plus a sentence in each README).
  `skill_test.py` checks all seven — let it, rather than updating by hand and hoping.
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
