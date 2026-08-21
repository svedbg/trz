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
| **K** | File construction — sums that skip a column, hardcoded values that stopped following, control columns that cannot fail, hand-typed totals, amounts entered in day columns, unrounded accruals, cost computed from net |

Every finding carries a severity (`нарушение` / `риск` / `за проверка` / `дефект` /
`бележка`), the specific article it rests on, the arithmetic, and a remedial action. A
finding without a statutory reference does not go in the report.

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

```sh
pip install -r test/requirements.txt
python test/run_tests.py              # both suites
python test/run_tests.py --semena 300 # longer randomised run
```

**Suite 1 — rates and working-time regimes.** A static payroll in a narrow layout with nine
deliberate defects and one clean control row: below-minimum wage, missing длъжност class,
unpaid overtime premium, an uncapped social-security base, night hours with no supplement,
three employer-paid sick days instead of two, a net that does not reconcile, a public
holiday paid at single rate, and an attachment. Expected: nine of nine found, zero findings
on the control row, and the attachment reported as `за проверка` rather than `нарушение` —
because the чл. 446 ГПК thresholds are deliberately absent from the rate file. Answer key:
[`test/expected_findings.md`](test/expected_findings.md).

**Suite 2 — file construction and base composition.** Payrolls in a wide layout, generated
from a seed. Every seed changes the company, the people, the salaries, the month, the rate
regime, the ТЗПБ percentage and which defects are injected — eighteen scenarios drawn from
real audits: the sick-pay compensation sitting in the social-security base and outside the
tax base at the same time, an amount typed into a day column, a control column that reads
zero while money is missing, a total typed by hand, the cost of labour computed from net
after deductions, the cap from the wrong half of the year, a benefit in one base but not the
other. Catalogue: [`test/scenarii.md`](test/scenarii.md).

A run passes only when **every** injected defect is found and **no** finding is raised
beyond them. False positives fail the suite exactly like misses: a skill that sees
violations everywhere is as useless as one that sees none.

Current state: 3000 seeds, 25 887 injected defects, 25 887 found, zero false positives.
Randomisation earned its keep — it exposed three bugs in the checks themselves, including
one where five separately rounded contributions drift up to 0.03 from 13.78% of the base and
a two-cent tolerance produces a phantom violation every few hundred rows. A static fixture
would never have shown it.

All test data is fabricated and derived from the seed. No real payroll, no real person, no
ЕГН.

## What you have to fill in yourself

Three things, and the skill will tell you when it needs them rather than guessing.

**МОД by economic activity.** Приложение № 1 / № 1А to the ЗБДОО, several hundred rows keyed
by КИД code and qualification group, changing annually. Copy the row for your КИД when you
need it. There is a blank table waiting for it.

**The ТЗПБ percentage for your КИД** (приложения № 2 / № 2А). The range 0.4–1.1% is
verified; which end you sit on is not. The skill derives the percentage the payroll actually
applied and asks you to confirm it, because at a few hundred thousand of insurable income
every tenth of a point is real money — this is routinely the largest unverified number in an
audit.

**The social-expense threshold in euro for 2026.** Until 2025 it was 60 лв per person per
month for voluntary insurance premiums paid at the employer's expense. The exact conversion
is 30.6773 EUR; whether the legislator adopted that or rounded it is not verified here. The
amount matters because the excess over the threshold enters the bases, so it moves both
contributions and tax for every person with such a benefit. The skill computes all three
variants and marks the finding `за проверка` rather than picking one.

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
