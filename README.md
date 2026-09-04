# trz — Bulgarian payroll audit skill for Claude Code, GitHub Copilot and Codex CLI

[![tests](https://github.com/svedbg/trz/actions/workflows/tests.yml/badge.svg)](https://github.com/svedbg/trz/actions/workflows/tests.yml)
[![licence: MIT + CC BY 4.0](https://img.shields.io/badge/licence-MIT%20%2B%20CC--BY--4.0-blue)](#licence)
[![rates verified](https://img.shields.io/badge/rates%20verified-2026--09--01-green)](skills/trz-expert/references/stavki.md)

An agent skill for [Claude Code](https://claude.com/claude-code),
[GitHub Copilot](https://github.com/features/copilot) and
[OpenAI Codex CLI](https://developers.openai.com/codex) that turns the assistant into a senior
payroll specialist for Bulgaria — ТРЗ, as the payroll-and-wages function is called there. Give it
a payroll register (ведомост), a payslip (фиш), an employment contract or a work schedule, and
it checks the numbers against the Labour Code (КТ), the Social Security Code (КСО), the
Personal Income Taxes Act (ЗДДФЛ) and the Ordinance on the Structure and Organisation of Wages
(НСОРЗ).

**Read this first:** the rates shipped here are current as of **1 September 2026**. The minimum
wage, the social-security thresholds and the contribution rates change every year — and in
2025 and 2026 they changed *mid-year*, because both budgets were adopted late. Check
[`skills/trz-expert/references/stavki.md`](skills/trz-expert/references/stavki.md) before
trusting any figure.

## Why this exists

Payroll software already computes salaries. What it does not do is tell you whether the result
is lawful — whether the length-of-service supplement matches someone's actual service, whether
the insurable income got capped, whether sick leave was charged to the employer for two days
or three. Those are the checks a payroll specialist does by hand, and they are exactly the
kind of mechanical, rule-heavy work an LLM can do reliably *if* it is stopped from inventing
numbers.

## The two rules that make it trustworthy

Most of the design is defensive. An LLM that confidently applies last year's minimum wage
produces a report that reads as authoritative and is wrong — worse than no report at all. So:

**1. No rate from memory, ever.** Every figure comes from `references/stavki.md`, where each
row carries a status (`ДВ` = verified against the State Gazette, `официален` = a state
authority's site, `вторичен` = professional source, `за потвърждение` = working hypothesis)
and the issue number it came from. If a rate is missing or unverified, the skill downgrades
the finding from `нарушение` (violation) to `за проверка` (needs checking) and states exactly
what it is missing. It never guesses.

**2. Arithmetic runs as code, not in the model's head.** The skill writes a Python script
that applies the checklist row by row and returns a table. The result is reproducible and
you can read the script. Mental arithmetic is allowed only for single cases — one
contract, one severance calculation.

## What it checks

Eleven groups, 78 checks, in
[`references/proverki.md`](skills/trz-expert/references/proverki.md):

| | |
| --- | --- |
| **A** | Employment contract — required elements, probation, fixed terms, contract ↔ payroll agreement |
| **B** | Minimum thresholds — the minimum wage and its hourly rate, the minimum insurance thresholds (МОД) by economic activity, the cap on insurable income |
| **C** | Pay structure — the length-of-service supplement (клас прослужено време), its base, benefits disguised as bonuses |
| **D** | Working time — overtime detection and limits, its premium, night work, public holidays, aggregated calculation of working time (СИРВ), rest periods |
| **E** | Leave — entitlement, pro-rating, pay basis, time-barring |
| **F** | Contributions and tax — insurance base, employer/employee split, tax base, reliefs, sick pay |
| **G** | Deductions — legal basis, protected minimum under чл. 446 ГПК (Code of Civil Procedure), order of attachment |
| **H** | Termination — severance under чл. 220, 221, 222 and 224 КТ, and the base each is computed on |
| **I** | Consistency — vertical and horizontal reconciliation, payroll ↔ payslip ↔ schedule ↔ declarations |
| **J** | Formalities — payment deadlines, payslip issuance, personnel file |
| **K** | File construction — sums that skip a column, hardcoded values that stopped following, control columns that cannot fail, hand-typed totals, amounts entered in day columns, unrounded accruals, cost computed from net |

Every finding carries a severity — `нарушение` (violation), `риск` (risk), `за проверка`
(needs checking), `дефект` (defect) or `бележка` (note) — the specific article it rests on,
the arithmetic, and a remedial action. A finding without a statutory reference does not go in
the report.

Group K is the exception, and deliberately so: those findings rest on arithmetic, not on a
statute, and the skill is told to say that rather than invent an article. They matter
because a construction defect is usually the *cause* and a finding in groups B, C, E or F
is the *effect* — the payroll formula that omits one column is why a severance payment
never reaches the net.

## The third rule: an internal contradiction needs no interpretation

Much of Bulgarian payroll law has more than one defensible reading. Whether a benefit in
kind belongs in the social-security base, how the excess over the social-expense threshold
is treated, which severance payments are insurable — pick one and declare it correct, and
you have written an opinion that can be argued away.

There is a stronger move: check whether the file is consistent **with itself**. If the same
amount sits inside one base and outside the other on the same row, at least one of the two
is wrong — under *every* reading. That finding needs no ruling on the contested question
and cannot be dismissed by interpretation. The skill is told to look for contradictions
inside the file first and to compare against the statute second, and when it does have to
touch a contested question, to enumerate the possible readings with the money each implies
and ask which one the company applies.

## Install

In Claude Code, two commands:

```
/plugin marketplace add svedbg/trz
/plugin install trz-expert@trz-bg
```

`/plugin marketplace update trz-bg` later brings updated rates. This is the path to use if
you just want the skill: it costs about 270 tokens of context per session and loads the rest
only when it runs.

In GitHub Copilot CLI, the same marketplace and the same skill:

```
copilot plugin marketplace add svedbg/trz
copilot plugin install trz-expert@trz-bg
```

`copilot plugin update trz-expert` brings updated rates there. The plugin also carries an
[Agent Plugins 1.0](https://agent-plugins.org) manifest, so any client that reads that
format finds it, and VS Code reads the marketplace from `.github/plugin/marketplace.json`,
which is the same file. Copilot asks no question when enabling, so the default described
next applies — and the report says so.

**Enabling it asks one question.** Whether a „Бонус“ column the file does not characterise
should be read as a one-off payment — outside the base for paid leave and sick pay — or as
pay under an applied wage system, which чл. 17, ал. 1, т. 2 НСОРЗ puts inside it. The
default is **outside**, which is what чл. 17 gives for a one-off. The question is narrow on
purpose: it settles only the case the file leaves open. A contract, a collective agreement
or internal wage rules that say which kind of payment it is override the setting, and no
value of it can take a supplement of permanent character out of the base. Change it later
with `/plugin`. Cloned rather than installed, there is no setting and the default applies —
the skill says so in the report rather than deciding quietly.

In [Codex CLI](https://developers.openai.com/codex), no install step at all: clone the
repository and Codex's repository-skill discovery finds
[`.agents/skills/trz-expert/SKILL.md`](.agents/skills/trz-expert/SKILL.md) on its own. That
file is a short pointer, not a second copy — it tells Codex to read the same
`skills/trz-expert/` that Claude Code and Copilot install from, so there is exactly one
copy of the guidance to keep current. Invoke it with `$trz-expert` or let a payroll
question select it. For a personal skill available in every repository you work in,
copy the same directory to `~/.agents/skills/trz-expert/` instead.

**If you want to work on it**, clone and symlink instead, so your edits are live:

```sh
git clone https://github.com/svedbg/trz.git
ln -s "$PWD/trz/skills/trz-expert" ~/.claude/skills/trz-expert
```

Pick one or the other, not both — otherwise two copies of the same skill compete for the
same name. For a project-scoped install, put the skill under `.claude/skills/` in your own
repository and commit it, so everyone working there gets it.

Then in Claude Code:

```
> analyse the payroll at ./vedomost_06_2026.xlsx
```

or invoke it directly with `/trz-expert`.

The skill pre-approves no tools. Reading your files and running an analysis script both go
through the normal permission prompt — deliberately, for something that reads salary data.

## Test it

```sh
pip install -r test/requirements.txt
python test/run_tests.py              # all five suites
python test/run_tests.py --seeds 300  # longer randomised run
python test/skill_test.py             # packaging: frontmatter, references, manifests
```

**Suite 1 — rates and working-time regimes.** A static payroll in a narrow layout with nine
deliberate defects and two clean control rows, one of them paid at exactly the statutory
minimum for overtime, night and holiday work: below-minimum wage, a missing length-of-service
supplement, unpaid overtime premium, an uncapped social-security base, night hours with no
supplement, three employer-paid sick days instead of two, a net that does not reconcile, a
public holiday paid at single rate, and an attachment. Expected: nine of nine found, zero
findings on the control rows, and the attachment reported as `за проверка` rather than
`нарушение` — because the чл. 446 ГПК thresholds are deliberately absent from the rate file.
Answer key: [`test/expected_findings.md`](test/expected_findings.md).

**Suite 2 — file construction and base composition.** Payrolls in a wide layout, generated
from a seed. Every seed changes the company, the people, the salaries, the month, the rate
regime, the occupational-accident insurance rate (ТЗПБ) and which defects are injected —
twenty-eight scenarios drawn from real audits: the sick-pay compensation sitting in the
social-security base and outside the tax base at the same time, an amount typed into a day
column, a control column that reads zero while money is missing, a total typed by hand, the
cost of labour computed from net after deductions, the cap from the wrong half of the year, a
benefit in one base but not the other. Catalogue: [`test/scenarios.md`](test/scenarios.md).

**Suite 3 — two months in one file.** July and August 2026 on two sheets with one roster,
also generated from a seed. The months are not arbitrary: the 2026 budget was adopted late,
so the thresholds change on 1 August, and two adjacent sheets therefore need different
figures — copying the first forward is at once the most natural thing for a person to do and
demonstrably wrong. Three scenarios that no single sheet can hold, because in one sheet a
stale threshold looks exactly like the threshold, a jump has nothing to jump from, and the
base for paid leave is in the month before: a sheet still built on the previous month's norm
and thresholds (K8), an implied monthly salary that moves between the months with no annex in
the file (I7), and paid leave computed on a base the preceding month's bonus was let into —
чл. 17, ал. 1 НСОРЗ enumerates in seven points what the leave is measured against, and a
bonus agreed for the one month is in none of them (E3).

**Suite 4 — the formula layer.** The only fixture whose computed columns carry real
formulas, and it exists because the first real audit this skill performed found every one
of its defects there: a cap typed by hand in a column of formulas, a days column added
into a money sum, a control column algebraically always zero, a parameter inlined as a
literal. Value exports — which is what every other fixture is — cannot hold any of these.
The checker judges the formulas alone, structure rather than arithmetic, since nothing in
openpyxl evaluates them.

A run passes only when **every** injected defect is found and **no** finding is raised
beyond them. False positives fail the suite exactly like misses: a skill that sees
violations everywhere is as useless as one that sees none.

Current state, the three generated suites at 3000 seeds: 29 550 injected defects in
suite 2, 6 855 in suite 3 and 8 994 in suite 4, every one of them found, zero false
positives.
Randomisation earned its keep — it exposed three bugs in the checks themselves, including
one where five separately rounded contributions drift up to 0.03 from 13.78% of the base and
a two-cent tolerance produces a phantom violation every few hundred rows. A static fixture
would never have shown it.

All test data is fabricated and derived from the seed. No real payroll, no real person, no
national identity number (ЕГН).

### Running them when the skill changes

One more suite reads the skill itself, and it is the only one that does. `run_tests.py` puts
it first and numbers it zero, because a drift here makes the other four meaningless:

```sh
python test/rates_test.py    # no dependencies — reads markdown
```

It parses `references/stavki.md` and asserts that every rate in `test/trz_model.py` matches
it. This closes a real hole: the model needs its own copy of the figures to compute
anything, which makes it a second source of truth, and updating the reference file would
otherwise leave the tests passing happily with last year's numbers. A restructured table
fails the check too — if the value can no longer be located, the correspondence is no longer
verifiable.

The other four suites (1–4) test Python, not markdown. Editing `SKILL.md` cannot change
their result, so running them on every prose edit is theatre. The split is wired into the
pre-commit hook:

```sh
git config core.hooksPath .githooks   # once
python3 -m venv .venv && .venv/bin/pip install -r test/requirements.txt
```

Every commit runs the rate check. Commits that touch the skill, a manifest, a licence, a
README or the social card also run the packaging test; commits that touch `test/*.py` also
run all five suites (0–4) at 25 seeds. Nothing is skipped silently: if the environment
cannot run a check, the hook says so and stops rather than passing quietly. `--no-verify`
overrides it.

CI ([`.github/workflows/tests.yml`](.github/workflows/tests.yml)) runs the rate check, the
packaging test, the grader's self-test, the personal-data guards (text files and the inside
of every tracked workbook) and all five suites (0–4) at 300 seeds on push and pull request;
a weekly run repeats the suites at 3000 seeds, and a monthly one checks that the verification
date has not gone stale — not because the code changes by itself but because the rates do.

### What none of this tests

The suites validate the *rules*: the arithmetic, the thresholds, the composition logic. They
do not test the skill, because the skill is instructions to a language model and the checkers
are independent Python. A rewrite of `SKILL.md` that makes the guidance worse will not fail a
single assertion.

That gap is what `test/eval_skill.py` addresses. It runs Claude with the skill against a
generated workbook and maps the findings it reports back onto the manifest:

```sh
python test/eval_skill.py --dry       # show what would be sent, pay nothing
python test/eval_skill.py --seeds 3   # three seeds
```

Measured on 04.09.2026: Claude Fable 5.1, the default, about USD 4.5–6.2 per seed
(16–25 turns, 11–15 minutes); Claude Sonnet 5, about USD 1.5–2.2, at a lower identified
rate. So it is not in `run_tests.py` and not in CI. Run it when the guidance in
`SKILL.md` changes, which is the only thing that can move its result.

Three decisions in it are worth knowing. The model gets a directory in `/tmp` holding the
workbook and a contracts CSV — what an auditor legitimately has — while the manifest is
deleted the moment it is generated and lives only in the harness process, the repo is never
passed with `--add-dir`, and the openpyxl environment is a
separate venv outside it: `test/` contains a full implementation of every check and an answer
key, and a run that reads those measures reading, not expertise. The scenario catalogue is
not given to the model either, or the task becomes label matching. And the result is three
numbers rather than one — found on the right row (objective), correctly identified (keyword
matching, which is judgement and is reported as such), and unattributed findings, which are
printed for review rather than counted as false positives, because the workbook is random and
some of them may be true observations that simply were not injected on purpose.

Details and the keyword sets: [`test/scenarios.md`](test/scenarios.md).

## What you have to fill in yourself

Three things, and the skill will tell you when it needs them rather than guessing.

**Minimum insurance thresholds (МОД) by economic activity.** Annex 1 / 1A to the State Social
Security Budget Act (ЗБДОО), several hundred rows keyed by economic-activity code (КИД, the
Bulgarian NACE) and qualification group, changing annually. Copy the row for your КИД when you
need it. There is a blank table waiting for it.

**The occupational-accident insurance rate (ТЗПБ) for your КИД** (Annexes 2 / 2A). The range
0.4–1.1% is verified; which end you sit on is not. The skill derives the percentage the
payroll actually applied and asks you to confirm it, because at a few hundred thousand of
insurable income every tenth of a point is real money — this is routinely the largest
unverified number in an audit.

**The social-expense threshold in euro for 2026 — resolved on 30 August 2026.** Until 2025 it
was 60 BGN per person per month for voluntary insurance premiums paid at the employer's
expense. It is **30.68 EUR**: articles 12 and 13 of the euro-adoption act divide by the full
1.95583 and round on the third decimal, and НАП publishes exactly that figure. The skill no
longer computes three variants and no longer downgrades the finding. What remains unverified
is not the threshold but the *treatment* of the excess over it — see below.

One other item is unverified, and it is unverified for an interesting reason: **the
employer/employee split of the pension contribution** (11.02/8.78 and 8.22/6.58). This is not
a disagreement between sources — it is a gap in the statute. Чл. 6, ал. 1 КСО was raised to
19.8% and 14.8% effective 01.01.2018, but чл. 6, ал. 3, т. 8 and 9 — the provisions that split
precisely that contribution — still carry 9.9/7.9 and 7.1/5.7, the pre-increase figures. Two
independent official consolidated editions, from the Ministry of Labour and Social Policy
(МТСП) and the National Social Security Institute (НОИ), give the same text.

The figures used in practice come out exactly if the two percentage points are split 0.56
employer / 0.44 employee, and that reconstruction fits both age cohorts to the decimal.
The reference file documents this in full. Practical impact is nil: the totals are
verified, every payroll system uses these figures, and employee contributions sum to
exactly 13.78% — which is the control the skill checks against.

Since 30 August 2026 the figures also have an official footing, though not the one that
would close the gap: НОИ publishes 11.02/8.78 and 8.22/6.58 verbatim in its 1 August 2026
guidance — but for a *different* group, the civil servants, judges and prosecutors being
aligned from 1 January 2027. It confirms these are the values the institution applies. It
is still not a provision about employees under an employment contract, so the reference
keeps the caveat: what is missing is the citation, not the number.

## Personal data

Payroll files are personal data under GDPR, and sick-leave records are health data. The
skill is instructed not to send file contents to external services, to reproduce the
minimum needed to justify a finding, and not to write derivative files outside the working
directory you point it at. That is instruction, not enforcement — you remain the
controller.

## Licence

Two licences, because the repository holds two kinds of thing:

| What | Licence |
| --- | --- |
| the skill directory `skills/trz-expert/` — `SKILL.md`, `references/*.md`, the two plugin manifests and `LICENSE-DOCS` itself — plus the Codex pointer, `.agents/skills/trz-expert/SKILL.md` | [CC BY 4.0](LICENSE-DOCS) |
| the source repository around it — all Python under `test/`, the git hook, the CI workflow | [MIT](LICENSE) |

**What an install carries is CC BY 4.0 alone.** The plugin's source is
`./skills/trz-expert`, not the repository root, so a `/plugin install` copies the skill,
its three reference files, the two manifests and a copy of `LICENSE-DOCS` — and no
MIT-licensed file at all. That is why both `plugin.json` files declare `CC-BY-4.0` rather
than the repository's pair: a bundle may only declare what it actually contains.

Use it, change it, ship it commercially. Keep the attribution, and if you change the
reference material say that you did — someone downstream needs to know whose verification
date they are trusting.

## Contributing

The most useful thing you can send is a rate correction with its source: rates change every
year and the reference file goes stale on its own.
[`CONTRIBUTING.md`](CONTRIBUTING.md) has the process, including how statuses work and why
the reference file — not the test model — is the source of truth. Security and personal-data
matters are in [`SECURITY.md`](SECURITY.md).

## Not legal advice

This is an expert payroll opinion, not legal advice. It does not replace a lawyer and it does
not protect you from findings by the Labour Inspectorate (ГИТ) or the National Revenue Agency
(НАП). Statutory references should be checked against the redaction in force for the period
you are auditing.

## Bulgarian

The same document in Bulgarian: [README.bg.md](README.bg.md) — същото на български.
