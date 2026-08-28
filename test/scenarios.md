# Scenarios in the structural suite

Suite 1 (`vedomost_05_2026.xlsx` + `checks_test.py`) tests whether the skill knows
the **rates and the working-time regimes**: minimum wage, the length-of-service
supplement, overtime, night work, public holidays, employer-paid sick days, the
cap on insurable income, vertical arithmetic, an attachment. Its answer key is
`expected_findings.md`.

This suite tests something else: whether the skill sees defects in the
**construction of the file and in the composition of the insurable income and the
taxable base**. Those are the findings you cannot reach by comparing a rate — you
reach them by reconciling the file against itself.

## Why the data is random

The payroll is generated from a seed. Every seed changes the company, the people,
the salaries, the days, the price of the benefits, the month, the threshold
regime, even the accident-insurance rate. Between five and nine defects are
injected, drawn at random from the catalogue below, onto randomly chosen rows.

The reason is not convenience. A static fixture allows a check that passes by
accident — because of one particular rounding, one particular column order,
because the cap happens to bind exactly there. A hundred different payrolls drag
such checks into the light. That is how three bugs in the checks themselves
surfaced:

- The sum of five separately rounded contributions drifts from 13.78% of the
  insurable income by up to 0.03. At a tolerance of 0.02 that produces a phantom
  violation every few hundred rows. The exact control is the sum of the
  components; the percentage is indicative.
- Once the maximum insurable income is reached, the composition of the base is
  not recoverable — the same figure follows from many different combinations. The
  check is obliged to stay silent rather than guess.
- When the day counts do not reconcile with the month's norm, every check that
  divides by days is inapplicable. Otherwise one error in the days produces five
  apparent errors in the money.

## Nothing from a real file

The first names, surnames, companies and every amount are invented and derived
from the seed. The company ID is `000000000`. The thresholds and percentages are
statutory values (minimum wage, maximum insurable income, 13.78%, 10% tax, 0.6%
per year of service) and come from `references/stavki.md`, not from anyone's
payroll.

## Language of the code

The code under `test/` is English — identifiers, comments, docstrings, scenario
ids. Two things stay Bulgarian because they are **data**, not code: the column
headers of the generated workbook, which the checker looks up by their exact text,
and the prompt sent to the model in `eval_skill.py`. The keyword patterns there
are Bulgarian too, because the skill reports in Bulgarian.

## Catalogue

The groups match `references/proverki.md`.

| id | Group | Defect | How it is caught |
| --- | --- | --- | --- |
| `K1_sum_omits_column` | K1 | An accrual column sits outside the gross formula | БРУТО ≠ the sum of the accrual columns; the check names the column left out |
| `K2_amount_in_day_column` | K2 | An amount typed into a column meant for days | A value in a day column with a fractional part, or above the month's norm |
| `K3_stale_contributions` | K3 | Contributions left over from an earlier period | The contributions are not a percentage of the stated insurable income |
| `K4_control_column_blind` | K4 | The control column reads zero while paid is below net | The „Разлика“ column ≠ net − paid |
| `K5_total_not_sum` | K5 | A hand-typed total in the ОБЩО row | The total ≠ the sum of the cells in its column |
| `K6_unrounded_accrual` | K6 | An accrual with more than two decimals | The value ≠ itself rounded to two decimals |
| `K7_cost_from_net` | K7 | Cost of labour computed from net after deductions | Cost ≠ gross + employer contributions + benefits; short by exactly what was withheld |
| `F9_sick_pay_in_insurable` | F9 | The чл. 40, ал. 5 КСО payment is inside the insurable income | Solving the composition: the element sits in a base on which no contributions are due |
| `F9_sick_pay_out_of_taxable` | F9 | The same payment is removed from the taxable base | Solving the composition of the taxable base |
| `F9_sick_pay_amount` | F9 | Sick pay computed from the agreed daily rate when the month's average daily gross is higher | The two measures of чл. 40, ал. 5 КСО are computed separately and the larger is owed; the base is rebuilt from the contract so a defect elsewhere on the row is not counted twice |
| `F9_missing_health_on_sick` | F9 | No health contribution under чл. 40, ал. 1, т. 5 ЗЗО for days of incapacity | 4.8% × the self-employed minimum × days / norm |
| `F10_in_kind_asymmetry` | F10 | The benefit in kind is in one base but not the other | The composition of the two bases is solved separately and compared |
| `F10_excess_asymmetry` | F10 | The same, for the excess over the social-expense threshold | Same |
| `F7_relief_over_limit` | F7 | Tax relief above 10% of the monthly taxable base | The amount deducted is solved from the equation and compared with the limit |
| `F5_tzpb_below_due` | F5 | Employer contributions carry an accident rate below the applicable one | Implied rate: contributions / insurable income − 10.92% |
| `B4_cap_from_wrong_period` | B4 | The cap of the other half-year is applied | Capped rows sit at a threshold other than the applicable one |
| `C2_seniority_on_gross` | C2 | The supplement is computed on a wider base than the salary | Supplement ≠ the stated percentage × the base salary |
| `E3_leave_without_seniority` | E3 | Paid leave computed without the supplement | Leave ≠ daily base × (1 + supplement) × days |
| `I5_days_do_not_reconcile` | I5 | The day counts do not reconcile with the month's norm | Sum of days ≠ working days in the month |

`K2_amount_in_day_column` produces two findings, not one: the amount in the day
column, and the days that no longer reconcile. That is how it goes in reality too
— the number takes the day's place and the day disappears.

## Running it

```sh
pip install -r test/requirements.txt

python test/run_tests.py                   # all three suites, 50 seeds
python test/run_tests.py --seeds 300       # longer
python test/structural_test.py --seed 42   # one seed, with the findings
python test/generate_wide.py --seed 42     # generate only, with the answers
```

A run is OK only when every injected defect is found on every seed and **not a
single** finding is raised beyond them. False positives fail the suite exactly
like misses.

`run_tests.py` also prints coverage — how many times each scenario was injected. A
scenario with zero injections did not pass, it was not tested; at low seed counts
some scenarios find no suitable row and are skipped.

## Evaluating the skill itself

Everything above tests the **rules** — the arithmetic, the thresholds, the
composition logic — with independent Python. But the skill is instructions to a
language model. Rewrite `SKILL.md` badly and not one of the tests above will fail.

`eval_skill.py` closes that. It runs Claude with the skill over a generated
payroll and maps the findings it reports back onto the manifest.

```sh
python test/eval_skill.py --dry           # what would be sent, paying nothing
python test/eval_skill.py --seeds 3       # three seeds
python test/eval_skill.py --seed 42 --model sonnet
```

**It costs money.** A measured run on Opus: 18 turns, about 12 minutes and USD 2.4
for one seed. Hence it is not in `run_tests.py` and not in CI.

**It paid for itself on the first graded run.** Seed 7 scored 7 of 7, and among the
findings it reported that were *not* injected was this one: the sick pay for the first
days was computed from the agreed daily rate while the month's average daily gross was
higher, because the row carried a bonus. That was not a defect in the payroll — it was
a defect in `trz_model.py`, which had implemented the "не по-малко от" floor of
чл. 40, ал. 5 КСО as if it were the whole rule. The suites could not see it: the
generator and the checker computed the sick pay with the same formula, so they agreed
with each other and agreed wrongly. A round trip cannot find a mistake in its own
premise, and that is the one thing an independent reader can. The rule is now in
`sick_daily_base()` and `F9_sick_pay_amount` guards it.

Three decisions in its construction are worth knowing.

**Isolation.** The model gets a directory in `/tmp` with two files: the workbook
and `dogovori.csv`, holding the contracted salaries and supplement percentages —
what an auditor legitimately has. The manifest stays in the repository, the
repository is not passed with `--add-dir`, and the openpyxl environment is a
separate venv outside it. The reason is blunt: `test/` holds a full implementation
of every check and a manifest with the answers. A run that reads those measures
reading, not expertise.

That isolation is not complete, and the harness says so. The skill is installed as
a symlink into the same repository and the model legitimately reads its reference
files, so a path to `test/` exists and cannot be closed without closing the skill.
So the whole tool stream is recorded and screened: a run that reached the answers
is reported as tainted and kept out of the statistics.

**The scenario catalogue is not given to the model.** Otherwise the task becomes
label matching. All that is asked for is a list of findings: where, severity, one
sentence and the two figures. The mapping happens in the harness, by row and by
keywords in the description.

**The result is three numbers, not one.** The keywords are judgement, not
measurement, and are reported as such:

| Measure | What it means |
| --- | --- |
| located | was a defect reported on this row at all — objective |
| identified | does the description match what was injected — by keyword, visible in `eval_skill.py` |
| unattributed | everything the model found that was not injected |

The unattributed ones are **not counted automatically as false positives**; they
are printed for review. The generated payroll is random and some of what the model
finds may be a true observation about it that simply was not injected on purpose.
Counting them automatically here would be self-deception.

## Testing the refusal

```sh
python test/eval_skill.py --selftest            # free, starts no session
python test/eval_skill.py --refusal --seed 3    # costs a seed
```

The skill's first rule is that no rate comes from memory: a figure the reference file
does not carry downgrades the finding from `нарушение` to `за проверка`, with the
missing value named. It is the loudest promise this project makes, and until this mode
existed nothing tested it — every suite handed the skill a period `stavki.md` covers, so
the refusal path never ran.

`--refusal` dates the payroll **2027**, a year the reference file has no thresholds for.
The generated file carries the last published regime rolled forward, which is how a real
January payroll is produced: by copying December's. Whether those thresholds still apply
is precisely what the skill cannot know. Nothing in the prompt mentions the year or the
gap; the workbook simply says 2027 and the skill either notices or does not.

Three separate questions, because they fail separately:

| Check | What it means | Why it is not the others |
| --- | --- | --- |
| the arithmetic still lands | the rate-free defects — the K group, the day counts, the supplement against the contract — are still found | A skill that goes quiet when it loses its rate book is not being careful, it is being useless |
| refuses on rates | nothing is graded `нарушение` on a figure the reference file lacks for the period | This is the failure the rule exists to prevent: last year's threshold applied to this year, with the confidence of a checked number |
| says what is missing | the report names the absent figures | Omitting a conclusion is not the same as reporting that it cannot be reached. The user has to be told |

`B4_cap_from_wrong_period` is not injected in this mode. Applying "the cap from the other
half-year" presupposes a published cap for this year to be wrong against; with no rates
there is nothing to be wrong about, and the finding the skill owes is that it cannot tell.

**The grading is itself tested, for free.** `--selftest` builds six synthetic reports — a
skill that refused, one that guessed a rate, one that went silent, one that did both
wrong, and the two phrasings a live run actually produced — and asserts the three checks
separate them. It runs in CI. The reason is that the run it guards costs real money and a
quarter of an hour, and a grader that passes everything is much the likeliest way for a
check like this to be quietly useless; without the self-test that would be discovered
only after paying for it.

**First live run: 3/3, and the grader needed fixing anyway.** Seed 3, July 2027, USD 2.44.
Six of six rate-free defects found, nothing asserted as `нарушение` on a rate, and the
gap named twice over:

> Ведомостта е за юли 2027 г., но прилага максимален осигурителен доход 2300.00 EUR —
> точно стойността за 01.08–31.12.2026 г.; справочникът не съдържа праг за 2027 г.

> Здравната вноска … е изчислена върху МОД за самоосигуряващи се 620.20 EUR — също
> стойността за 01.08–31.12.2026 г., пренесена в ведомост за юли 2027 г.

Those two sentences are the whole point of the mode, and the third check matched
*neither* of them. It passed on a lesser finding about the social-expense threshold,
because the pattern did not know the phrase „не съдържа“. A check that would have failed
the best possible answer is not a check, so the third one now also accepts a finding that
holds the payroll's year up against another year's figure — naming what was put in the
gap is a better answer than naming the gap. Re-grading the saved report then exposed the
opposite fault: „нито една клетка не съдържа формула“ scored as a statement about rates,
because the companion pattern carried a bare „осигурителен доход“, which appears in half
the findings in any payroll report. Both are fixed and both are now self-test cases.

## What is deliberately not tested

- **Which of the contested readings is the right one.** Whether the benefit in
  kind and the excess over the social-expense threshold belong in the insurable
  income and in the taxable base has more than one defensible answer (see
  `proverki.md`, F10). The generator picks a policy for the whole file, applies it
  consistently, and then breaks it on one row. The check catches the broken
  consistency without ruling on the doctrine. That is also the right behaviour for
  the skill: a finding that needs no interpretation is stronger than one that
  depends on it.
- **Formulas.** The generated files hold values only. Not because formulas do not
  matter — the opposite, in a real file the defect is often visible only there —
  but because a check that works without formulas works always. When the formulas
  are there, the skill is required to read them (`SKILL.md`, "How to read a
  spreadsheet"); the suite measures the harder case.
- **Rates and working-time regimes.** That is suite 1's job.
