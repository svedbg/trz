# trz — Bulgarian payroll audit skill for Claude Code

A [Claude Code](https://claude.com/claude-code) skill that turns Claude into a senior
ТРЗ (payroll) specialist for Bulgaria. Give it a ведомост, a фиш, a трудов договор or a
work schedule, and it checks the numbers against the Кодекс на труда, КСО, ЗДДФЛ and the
Наредба за структурата и организацията на работната заплата.

**Read this first:** the rates shipped here are current as of **21 August 2026**. МРЗ,
осигурителни прагове and контribution rates change every year — and in 2025 and 2026 they
changed *mid-year*, because both budgets were adopted late. Check
[`skills/trz-ekspert/references/stavki.md`](skills/trz-ekspert/references/stavki.md)
before trusting any figure.

## Why this exists

Payroll software already computes salaries. What it does not do is tell you whether the
result is lawful — whether the клас is right for someone's actual service, whether the
осигурителен доход got capped, whether the болничен was charged for two days or three.
Those are the checks a ТРЗ specialist does by hand, and they are exactly the kind of
mechanical, rule-heavy work an LLM can do reliably *if* it is stopped from inventing
numbers.

## The two rules that make it trustworthy

Most of the design is defensive. An LLM that confidently applies last year's МРЗ produces
a report that reads as authoritative and is wrong — worse than no report at all. So:

**1. No rate from memory, ever.** Every figure comes from `references/stavki.md`, where
each row carries a status (`ДВ` = verified against the State Gazette, `вторичен` =
professional source, `за проверка` = working hypothesis) and the issue number it came
from. If a rate is missing or unverified, the skill downgrades the finding from
`нарушение` to `за проверка` and states exactly what it is missing. It never guesses.

**2. Arithmetic runs as code, not in the model's head.** The skill writes a Python script
that applies the checklist row by row and returns a table. The result is reproducible and
you can read the script. Mental arithmetic is allowed only for single cases — one
contract, one severance calculation.

## What it checks

Ten groups, roughly seventy checks, in
[`references/proverki.md`](skills/trz-ekspert/references/proverki.md):

| | |
| --- | --- |
| **A** | Employment contract — required elements, probation, fixed terms, contract ↔ payroll agreement |
| **B** | Minimum thresholds — МРЗ, hourly МРЗ, МОД by economic activity, максимален осигурителен доход |
| **C** | Pay structure — клас прослужено време, its base, benefits disguised as bonuses |
| **D** | Working time — overtime detection and limits, its premium, night work, official holidays, СИРВ, rest periods |
| **E** | Leave — entitlement, pro-rating, pay basis, time-barring |
| **F** | Contributions and tax — insurance base, employer/employee split, tax base, reliefs, sick pay |
| **G** | Deductions — legal basis, protected minimum under чл. 446 ГПК, order of attachment |
| **H** | Termination — severance under чл. 220, 221, 222, 224, and the base each is computed on |
| **I** | Consistency — vertical and horizontal reconciliation, payroll ↔ payslip ↔ schedule ↔ declarations |
| **J** | Formalities — payment deadlines, payslip issuance, personnel file |

Every finding carries a severity (`нарушение` / `риск` / `за проверка` / `бележка`), the
specific article it rests on, the arithmetic, and a remedial action. A finding without a
statutory reference does not go in the report.

## Install

```sh
git clone https://github.com/svedbg/trz.git
ln -s "$PWD/trz/skills/trz-ekspert" ~/.claude/skills/trz-ekspert
```

A symlink rather than a copy, so `git pull` brings you updated rates. For a project-scoped
install, put it under `.claude/skills/` in the repository instead.

Then in Claude Code:

```
> analyse the payroll at ./vedomost_06_2026.xlsx
```

or invoke it directly with `/trz-ekspert`.

## Test it

The repository ships a synthetic payroll with nine deliberate defects and one clean
control row:

```sh
pip install -r test/requirements.txt
python test/generate_vedomost.py     # rebuilds vedomost_05_2026.xlsx
python test/proverki_test.py         # runs the checks
```

Expected: nine of nine defects found, zero findings on the control row, and the
attachment case reported as `за проверка` rather than `нарушение` — because the чл. 446
ГПК thresholds are deliberately absent from the rate file. The full answer key is in
[`test/expected_findings.md`](test/expected_findings.md).

The test data is fabricated. No real payroll, no real person, no ЕГН.

## What you have to fill in yourself

`references/stavki.md` is complete except for one table: **МОД by economic activity**.
That table is Приложение № 1 / № 1А to the ЗБДОО, several hundred rows keyed by КИД code
and qualification group, and it changes annually. Copy the row for your КИД when you need
it. There is a blank table waiting for it.

One other item is unverified, and it is unverified for an interesting reason: **the
employer/employee split of the pension contribution** (11.02/8.78 and 8.22/6.58). This is
not a disagreement between sources — it is a gap in the statute. КСО чл. 6, ал. 1 was
raised to 19.8% and 14.8% effective 01.01.2018, but чл. 6, ал. 3, т. 8 and 9 — the
provisions that split precisely that contribution — still carry 9.9/7.9 and 7.1/5.7, the
pre-increase figures. Two independent official consolidated editions, from the МТСП and
the НОИ, give the same text.

The figures used in practice come out exactly if the two percentage points are split 0.56
employer / 0.44 employee, and that reconstruction fits both age cohorts to the decimal.
The reference file documents this in full. Practical impact is nil: the totals are
verified, every payroll system uses these figures, and employee contributions sum to
exactly 13.78% — which is the control the skill checks against.

## Personal data

Payroll files are personal data under GDPR, and sick-leave records are health data. The
skill is instructed not to send file contents to external services, to reproduce the
minimum needed to justify a finding, and not to write derivative files outside the working
directory you point it at. That is instruction, not enforcement — you remain the
controller.

## Not legal advice

This is an expert payroll opinion, not legal advice. It does not replace a lawyer and it
does not protect you from findings by the Labour Inspectorate or the НАП. Statutory
references should be checked against the redaction in force for the period you are
auditing.

## Bulgarian

Същото на български: [README.bg.md](README.bg.md).
