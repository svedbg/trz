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
regime, even the accident-insurance rate. Between six and eleven defects are
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
| `F9_sick_pay_out_of_insurable` | F9 | The чл. 40, ал. 5 КСО payment is left out of the insurable income | Solving the composition: чл. 3, ал. 1 НЕВДПОВ puts the element inside, and the stated figure is short by it |
| `F9_sick_pay_in_taxable` | F9 | The same payment is left inside the taxable base | Solving the composition of the taxable base: чл. 24, ал. 2, т. 14 ЗДДФЛ keeps it out |
| `F9_sick_pay_amount` | F9 | Sick pay computed on the bonus's other side of чл. 17, ал. 1 НСОРЗ | The base is remuneration of permanent character. Whether an uncharacterised bonus belongs to it has two lawful answers — a one-off is in none of the seven points, pay under an applied wage system is т. 2 — and `policy["bonus_in_base"]` carries the configured one. The mutation always writes the other, so both readings have teeth: configured **out**, the row overpays; configured **in**, it shorts the worker. The base is rebuilt from the contract so a defect elsewhere on the row is not counted twice |
| `F9_health_on_sick_days` | F9 | The чл. 40, ал. 1, т. 5 ЗЗО contribution on the wrong days | 4.8% × the self-employed minimum × days / norm, where the days are those the employer's чл. 40, ал. 5 pay does NOT cover — from the third working day, plus maternity. Two shapes, one id: missing entirely, or charged over all days including the employer-paid ones, which pays health twice (their pay is insurable income and carries it there). The second shape is the rule this model itself applied until the adversarial review held it against т. 17 of Декларация обр. 1, quoted in stavki.md all along |
| `F10_in_kind_asymmetry` | F10 | The benefit in kind is in one base but not the other | The composition of the two bases is solved separately and compared |
| `F10_excess_asymmetry` | F10 | The same, for the excess over the social-expense threshold | Same — but the practice is inferred **per base**, because reading В (`stavki.md`) puts the excess inside the insurable income and outside the taxable base. A file applying В throughout is correct and must produce no finding; the defect is a row that departs from what the other rows do |
| `F7_relief_over_limit` | F7 | Tax relief above 10% of the monthly taxable base | The amount deducted is solved from the equation and compared with the limit |
| `F7_relief_combined_limit` | F7 | Both чл. 19 relief groups capped against one shared 10% | The statute gives two independent 10% allowances against the same base; adding the groups together and capping once relieves less than is due. Only visible on a row carrying **both** instruments — with one, a shared cap and a per-group cap are the same number |
| `F7_relief_not_applied` | F7 | A personal contribution is withheld but reduces no taxable base | The relief was due (чл. 19, ал. 2 ЗДДФЛ) and none was given. The only scenario that leaves the file **internally consistent** — no control moves, every row agrees — so it is found by knowing the relief was due, not by spotting a contradiction |
| `F5_tzpb_below_due` | F5 | Employer contributions carry an accident rate below the applicable one | Implied rate: contributions / insurable income − 10.92% |
| `B4_cap_from_wrong_period` | B4 | The cap of the other half-year is applied | Capped rows sit at a threshold other than the applicable one |
| `C2_seniority_on_gross` | C2 | The supplement is computed on a wider base than the salary | Supplement ≠ the stated percentage × the base salary |
| `E3_leave_without_seniority` | E3 | Paid leave computed without the supplement | Leave ≠ daily base × (1 + supplement) × days |
| `F1_compensation_in_insurable` | F1 | The чл. 224 КТ compensation inside the insurable income | чл. 1, ал. 8, т. 7 НЕВДПОВ is an exhaustive list of the sums no contributions are due on, and чл. 224 is in it — the statute-settled mirror of the sick pay. Guarded even when the file's practice cannot be inferred, via `statutory_misplacements()` |
| `I5_days_do_not_reconcile` | I5 | The day counts do not reconcile with the month's norm | Sum of days ≠ working days in the month |
| `I1_vertical` | I1 | The net columns do not follow the rest of the row | Net before deductions ≠ gross − contributions − tax, or net payable ≠ net before deductions − the deduction columns. Two shapes, one id: the bottom half of the payslip is a pasted value from before a late bonus or чл. 224 compensation was added, or a deduction column is withheld but was never wired into the net formula |
| `F6_tax_amount` | F6 | The tax does not follow the taxable base the row states | Tax ≠ the rate × the stated base. The base itself is right and the net follows the wrong tax, so nothing else on the row disagrees with itself. Two shapes: the tax formula points at the base before the чл. 19 relief (granted in one column, taxed away in the next), or the tax is a pasted value |
| `A6_base_vs_contract` | A6 | The row is computed from a salary other than the contracted one | Base for the days worked ≠ contracted salary ÷ norm × days, in either direction — a stale salary before a raise, or a raise applied before the annex exists; `proverki.md` counts both. The row is self-consistent and the contract is the only witness. Injected only on rows without leave or sick days, where the same wrong salary would also move the leave and the sick pay and one defect would be reported three times |
| `F1_insurable_unexplained` | F1 | Insurable income that no composition of the row reaches | A pasted figure; the contributions on both sides and the taxable base follow it, so K3, F5 and F6 hold. Solving the composition finds no element, present or absent, that explains the gap — and the checker must say so rather than name the nearest element. The generator keeps the gap at least 0.50 from every element's value, or the finding would carry that element's id |
| `F6_taxable_unexplained` | F6 | Taxable base that no catalogued deviation reaches | A pasted base; the tax and the net follow it. Every named deviation of the taxable base — the three relief shapes, the sick pay inside, the compensation outside, either contested element flipped against the file's practice — is enumerated by `_taxable_explanations()` and the figure lands at least 0.50 from each, so the only honest verdict is „does not follow from the gross minus the contributions; none of the known deviations fits“ |
| `F6_compensation_out_of_taxable` | F6 | The чл. 224 КТ compensation left out of the taxable base | The mirror of `F1_compensation_in_insurable`: чл. 24, ал. 2, т. 8 ЗДДФЛ lists the exempt compensations and чл. 224 is not among them, so the sum is taxable. Solving the composition of the taxable base: the relieved base without the compensation matches, and no other catalogued deviation lands on the same figure |

## Suite 4: the formula layer

The first real audit this skill performed found every one of its defects in the
formulas — a cap typed by hand on 13 of 24 rows, a days column added into a money sum,
a `Diff` control algebraically always zero, `=31.88*0.02+31.88` inlined on every row —
and no suite could have caught any of them, because every fixture was a value-only
export. `generate_formula.py` writes those shapes on purpose; `formula_test.py` finds
them **from the formulas alone**.

| id | shape | how it is found |
| --- | --- | --- |
| `KF1_sum_omits_column` | the gross formula skips an accrual column | the gross must reference every accrual column, present or empty — the omission is a defect with a delay fuse |
| `KF2_days_in_money_sum` | a day-count cell inside the gross | money formulas must not reference day columns |
| `KF3_hard_value_in_formula_column` | a typed value in a column of formulas | shape uniformity: the one row whose "formula" is a literal |
| `KF4_tautological_control` | `Разлика = A−B` while `B = =A` | one level of reference resolution proves the control can detect nothing |
| `KF5_constant_in_formula` | a parameter inlined as a literal on one row | shape uniformity again: strip the row digits and the deviating row carries numbers where the others carry a `$`-reference |
| `KF_shape_deviates` | a formula of a different shape on one row, with no literal in it | shape uniformity's third bin — not a typed value, not an inlined literal, simply not the column's formula: an insurable income that skips the `MIN` against the cap, or a net that forgets the tax term |

Two design limits, on the record. openpyxl writes formulas without cached values and
evaluates nothing, so this suite checks **structure, not arithmetic** — which is also
why the paid eval does not use this fixture yet: a live session opening it with
`data_only=True` sees `None` everywhere; a faithful eval fixture needs Excel-produced
caches. And the shape-uniformity check needs a majority to deviate from, so a file
where EVERY row inlines the same constant (the live audit's `+1.84`) reads as uniform —
that shape is caught only by the parameter-cell convention, not by comparison.

`K2_amount_in_day_column` produces two findings, not one: the amount in the day
column, and the days that no longer reconcile. That is how it goes in reality too
— the number takes the day's place and the day disappears.

## Running it

```sh
pip install -r test/requirements.txt

python test/run_tests.py                   # all five suites (0–4), 50 seeds
python test/run_tests.py --seeds 300       # longer
python test/structural_test.py --seed 42   # one seed, with the findings
python test/generate_wide.py --seed 42     # generate only, with the answers
```

A run is OK only when every injected defect is found on every seed and **not a
single** finding is raised beyond them. False positives fail the suite exactly
like misses.

`run_tests.py` also prints coverage — how many times each scenario was injected. A
scenario with zero injections did not pass, it was not tested; at low seed counts
some scenarios find no suitable row and are skipped. Below 100 seeds that is printed
as a warning and the run still passes — the pre-commit hook runs 25, and a rare
scenario legitimately finds no row in 25 payrolls. From 100 seeds up a scenario at zero
fails the run, because at that depth it means the mutation can no longer break anything.

A seed that raises an exception is recorded as a failing seed with the exception's
text; the remaining seeds and suites still run, and the `RESULT` line is always
printed. The workbooks of a run go to a per-run directory under `test/tmp` that is
removed at the end; the single-seed commands above write to `test/tmp` itself and
leave their files there for inspection.

## The two-month suite

```sh
python test/pair_test.py --seed 7
python test/generate_pair.py --seed 7     # generate only, with the answers
```

Three of the documented checks cannot be expressed in one sheet, and until this fixture
none of them had a scenario. In a single sheet a stale threshold looks exactly like the
threshold, a jump has nothing to jump from, and the base for paid leave is in the month
before.

`generate_pair.py` writes **July and August 2026** into one workbook with one roster. The
months are not arbitrary: the 2026 budget was adopted late, so the thresholds change on
1 August. Two adjacent sheets therefore need different figures, and copying the first
forward is both the most natural thing for a person to do and demonstrably wrong. July
carries no paid leave — it is the base month, and its gross has to be unambiguous for
August's leave to be measured against it.

| id | Group | Defect | How it is caught |
| --- | --- | --- | --- |
| `K8_stale_thresholds` | K8 | The later sheet keeps the earlier sheet's norm and thresholds | Two independent signs: the day sums reconcile to the other month's norm, and rows sit on the other period's cap |
| `I7_unexplained_jump` | I7 | Someone's pay jumps between adjacent months | The **implied monthly salary** — base pay ÷ days worked × the sheet's norm — changes with no annex in the file |
| `E3_leave_base` | E3 | Paid leave computed on the bonus's other side of чл. 17, ал. 1 НСОРЗ | чл. 18: the preceding month's чл. 17, ал. 1 pay over its **worked** days, corrected by the ratio of the two months' norms (ал. 2). Same two readings and same both-polarity mutation as `F9_sick_pay_amount`. Paying the leave from the contract is **not** a defect — with the ал. 2 coefficient the norms cancel and the correct base lands on the leave month's contracted daily rate. A third shape on a July under 10 worked days: изр. първо misapplied where изр. второ sends the base to the agreed salary over the year's average monthly working days |

**The sheet's norm is not the month's norm**, and the distinction carries the suite. When
a sheet is copied forward, the first stops following the second, and every row then
reconciles perfectly against a month that is not its own. So the norm is derived from the
day sums and only then compared with the calendar. Deriving it from the calendar instead
would turn one file-level defect into a row-level finding against every person on the
sheet — the cascade the single-sheet suite already learned to avoid.

The same reasoning drives I7. A gross may legitimately move with a bonus, with leave,
with sick days, or simply because the two months hold a different number of working days.
The salary behind it may not, so that is what is compared.

Everything is read from the two sheets. The manifest is opened once, at the end, to score
the run — a check that quietly consults the answer key proves nothing about the file.

Each check was blinded in turn to confirm it carries its own weight. Removing the
preceding-month base turns every leave row red (21/21 seeds); comparing gross instead of
the implied salary turns every jump red (24/24). K8 is the interesting one: silencing the
derived-norm evidence changes nothing, because the cap evidence catches it independently,
and only silencing both makes it fail (12/12). Two witnesses to the same defect, which is
why it is stated as two signs above.

That test had to be built carefully. The first attempt patched the model *before*
generating the fixtures, so the generator and the checker moved together and everything
stayed green — the identical failure this repository has now hit twice for real. Fixtures
are built first, and only then is the checker blinded.

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
python test/eval_skill.py --regrade       # re-score the saved results, paying nothing
```

**It costs money.** A measured run on Opus: 18 turns, about 12 minutes and USD 2.4
for one seed. Hence it is not in `run_tests.py` and not in CI.

**The 2.7.0 run (04.09.2026).** Five seeds chosen with `--covering` for the new scenarios
and the changed guidance (1, 3, 9, 14, 16 — 42 injected defects), USD 24.09, about 11
minutes and USD 4.7 per seed on this model (the USD 2.4 above was an earlier model's
price). Located 42 of 42, missed none. Identified 33 as graded live; nine „located only",
of which eight were the grader, not the skill: the model wrote „нетото не приспада",
„надвнесен данък … върху основата преди приспадането", „разходът е занижен — изважда
личната удръжка", and a `бележка` for a 0.05 EUR control-column defect (allowed for group
K), and reported the sick-pay base overpayment as `за проверка` because the base's
composition is `за потвърждение` in the reference — its own cap rule. Those phrasings are
regression cases now; re-graded offline the same records score 41 of 42. The ninth is the
K2 sentence that also carries the I5 expectation and does not name the norm. **No false
`нарушение` in five payrolls**: every unattributed finding was a correct consequence of an
injected defect (seed 14's nine cap rows are its file-level B4), a `за проверка` that
asks for a document, or a note. One thing it found in the fixture itself: the чл. 224
compensation was a uniform random amount, and the skill said on every seed that it
matched no whole number of days at any base. It is whole days now. A second fixture
lesson from the 3000-seed run that followed: the relief-over-limit mutation could land
two cents from „the card outside the base plus the lawful relief", and the checker rightly
called the base unexplained — the mutation now checks its base against every other
candidate's (`_taxable_alternatives`).

**The refusal seed of that batch (seed 3, a 2027 payroll, USD 6.17)** scored 2 of 3: the
arithmetic survived (8 of 8 rate-free defects identified) and the report named what was
missing, but one `нарушение` leaned on a rate it did not have — „занижен осигурителен доход
… под тавана", the 2026 cap applied to 2027. An insurable income below the accruals is a
finding only if the accruals are below the cap *of that period*; without it, `за проверка`.
The first rule in SKILL.md now says so, in the same words as the 2.6.0 lesson about a
missing contribution, and F1 repeats it. **Proved on 2.8.0 with the same seed (USD 4.90):** no violation asserted
on a rate it lacks, the МРЗ comparison written as `за проверка` naming the missing 2027
figure, 8 of 8 rate-free defects identified — the eighth after one more phrasing joined
the I5 pattern („дните на реда са 20 вместо 22"). 3 of 3.

**Claude Sonnet 5 (04.09.2026), five fresh seeds (20, 21, 22, 24, 25 - never used for
calibration before), USD 8.89, about USD 1.8 and 15-20 turns per seed - roughly a third
the cost of Claude Fable 5.1 above.** Live 28 of 50 = 56%. Triaging every gap found four
real grader defects, not model failures, confirmed harmless against the untouched Fable
records (still 41/42 after the fix): `location()` collapsed a systemic finding named by
row list („редове 6, 8, 12, …" or „всички редове … (без ред 9 - …)") to a single row -
for the exclusion phrasing, the excluded row; Sonnet tends to name every affected row
where Fable tends to write „file", so this one hit Sonnet's transcripts far harder than
Fable's ever had reason to. `DENIES` read „за разлика от … ред 8, изчислен правилно"
(unlike row 8, which WAS correct) as the model denying its OWN finding - the comparison
names a different row's correct example, not this row's outcome. Three keyword gaps
(„недовнесена вноска" for F5, a noun between subject and verb in „клас сумата е
изчислена грешно" for C2, „надхвърля" for F7) each collided with another scenario once
widened and were fixed at the collision, not by dropping the recall - see the commit for
detail. Re-graded offline with all four fixes: **33 of 50 = 66%.** Zero false
`нарушение` in five payrolls, same as Fable. The gap to Fable's 98% is real and clusters
in checks needing a multi-step derivation carried through several numbers (K3, K7,
F6_tax_amount, I1) - nothing in the misses points at unclear guidance.

**Claude Sonnet 5 again (05.09.2026), seeds 1-3 on 2.11.1, USD 4.78.** Live 16 of 29 =
**55%**, located at all 83%, zero false `нарушение` — inside the band the five-seed
Sonnet batch above recorded (56% live, 66% re-graded), so the 2.11.1 guidance changes
cost nothing measurable. Read it as a Sonnet number and only that. Re-graded after the
three keyword fixes the Fable batch below produced: **17 of 29 = 59%**.

**Claude Fable 5.1, held-out seeds 11-13, on 2.12.0, USD 15.98.** Live 30 of 35;
re-graded after triage **34 of 35 = 97%**, located 100%, **missed 0**, zero false
`нарушение`. The batch stopped after two seeds on the account's spend limit — the runner
says so, saves what it has, and seed 13 ran afterwards with `--overwrite`, which is the
whole reason that flag refuses to clobber a paid transcript by default.

The one that is **not** a keyword gap and is left as it stands: `F10_in_kind_asymmetry`
on seed 13. The model reported something else on that row — a чл. 224 compensation equal
to five days' leave on someone with a full month worked and no termination document,
which is a fair observation — and never addressed the benefit in kind. That is a miss
wearing "located only", and widening a pattern to cover it would be scoring a different
finding as if it were the injected one.

The other four gaps were keyword gaps, each fixed at the phrasing rather than by
dropping the requirement that keeps the pattern honest:

| id | what the model wrote | why it missed |
| --- | --- | --- |
| `K4_control_column_blind` | „а колоната Разлика **не го** показва" | a pronoun between the negation and the verb — the same shape as the C2 gap the Sonnet batch found |
| `F6_compensation_out_of_taxable` | „е **извадено** от данъчната основа" | a verb the „изключен / вън от / не влиза" list did not carry |
| `I1_vertical` | „не е **приспаднета** от нетото" | the participle agreed with a feminine noun and was misspelt; the pattern required the `-ат` ending |
| `I5_days_do_not_reconcile` | „само **19 отчетени дни от 21**" | the shortfall stated as „X … от Y", with the norm as the second number and no word for it at all |

**The two-month fixture, Fable 5.1, seed 7, USD 4.98.** Live 1 of 2; re-graded **2 of 2**.
The gap was `I7_unexplained_jump`, on a finding that named the checks itself:

> „Основна за отработеното в 08-2026 е 1360.47 EUR при 21 от 21 работни дни, а
> договорът и юли дават 764.78 EUR; допълнително споразумение няма (A6/I7/I11)."

Two patterns missed it at once. It named the subject by the payroll's own column —
„основна за отработеното", not „заплата" or „бруто" — and stated the discrepancy as
„а договорът … дават", where the pattern wanted the adjective „договорен". Both widened;
the third group still requires the missing document, so nothing about K8 or E3 reaches
this entry.

Re-grading every saved result with all six fixes moved six findings from "located only"
to "identified" across **both** models and **all three** fixtures, and moved **nothing**
in the other direction — which is the check that they widened recall without widening
what counts as a match.

**Where 2.12.0 stands, in one table.** Every figure below is after triage, and every
triage decision is above.

| fixture · model | seeds | identified | located | missed | USD |
| --- | --- | --- | --- | --- | --- |
| комплект · Fable 5.1 | 1, 2 | **8/8 = 100%** | 100% | 0 | 9.50 |
| two-month · Fable 5.1 | 7 | **2/2 = 100%** | 100% | 0 | 4.98 |
| wide · Fable 5.1 | 11-13 (held out) | **34/35 = 97%** | 100% | 0 | 15.98 |
| wide · Sonnet 5 (on 2.11.1) | 1-3 | 17/29 = 59% | 90% | 5 | 4.78 |

Zero false `нарушение` in any of them.

**And read the model, not the intent.** This batch was meant for Fable. Nobody passed
`--model`, the `claude` CLI was configured for Sonnet 5, and the run said "default"
everywhere while producing a number that looks like a collapse against Fable's 98% and
is ordinary against Sonnet's 56%. Two things now stop that: the model that ANSWERED is
read out of the transcript, printed after each seed and saved in the record, and the
results file is named by it — until now a Fable default run and a Sonnet default run
both wrote `wide-<seed>-default.json`, which is the collision `results_path` was
already documented to prevent for the named case. The three seeds above were renamed
and backfilled by hand.

**What a run leaves behind.** Each seed's session runs in `/tmp/trz-eval/seed-<n>`
(`pair-<n>` for the two-month fixture, `refusal-seed-<n>` for a refusal run - it shared
`seed-<n>` with the wide run until the first paid batch collided on seed 3) and leaves its
transcript there — `stream.jsonl`,
`findings.json`. A directory holding a transcript was paid for, so a new run of the same
seed is refused unless `--overwrite` is given; `--dry` builds into `dry-seed-<n>` and
never touches it. A session that ends with the account's spend or rate limit stops the
batch at once - the first paid batch hit the limit inside seed 1 and then paid a turn for
each remaining seed to be told the same thing. Since 2026-09-03 every seed is also written, the moment it is graded, to
`/tmp/trz-eval/results/<mode>-<seed>.json`: the manifest, the findings, the grades, the
cost, and three signatures — of the skill in the working tree, of the keyword universe
and of the fixture generator — so a saved score cannot be mistaken for a score of the
current text. Ctrl-C mid-batch prints the summary over the seeds already finished and
exits 130; nothing paid for is lost. `--regrade` re-scores every saved file against the
*current* keywords, prints which expectations changed status per seed and the summary,
and regenerates nothing — the way to see what a keyword change does to a run without
paying for the run again.

**It paid for itself on the first graded run.** Seed 7 scored 7 of 7, and among the
findings it reported that were *not* injected was this one: the sick pay for the first
days was computed from the agreed daily rate while the month's average daily gross was
higher, because the row carried a bonus. That was not a defect in the payroll — it was
a defect in `trz_model.py`, which had implemented the "не по-малко от" floor of
чл. 40, ал. 5 КСО as if it were the whole rule. The suites could not see it: the
generator and the checker computed the sick pay with the same formula, so they agreed
with each other and agreed wrongly. A round trip cannot find a mistake in its own
premise, and that is the one thing an independent reader can. The rule is now in
`sick_daily_base()` and `F9_sick_pay_amount` guards it — and because generator and
checker both call that function, `selftest_sick_base()` in `structural_test.py` pins it
against closed-form arithmetic before suite 2 runs a single seed. It had to: a copy of the
model returning 110% of the right daily base passed every payroll suite at 60 seeds.

**Then the same round trip hid the correction's own mistake.** The fix put every accrual
into the "брутно" measure, bonus included, and that is not what the base is. чл. 17, ал. 1
НСОРЗ enumerates seven points and a bonus is in none of them; чл. 18, ал. 1 divides by the
days **worked**; and чл. 18, ал. 2 corrects the result by the ratio of the two months'
norms, which on an unchanged contract cancels out to the leave month's contracted daily
rate. The model overcorrected on all three counts, and the two scenarios standing on it,
`F9_sick_pay_amount` and the pair fixture's leave base, scored a payroll that had paid
correctly as defective. Nothing in the suites could tell, for exactly the reason above. It
came from a reader again, not from a run.

**A practice that cannot be inferred is not a reason to go silent.** Twice in this change a
seed lost findings that way: seed 1162 to an unestablishable practice for the insurable
income, seed 165 to one for the taxable base. Both were the same mistake — gating a check on
a question it does not depend on. The sick pay's place in either base is settled by statute
(чл. 3, ал. 1 НЕВДПОВ, чл. 24, ал. 2, т. 14 ЗДДФЛ) and neither relief scenario is about what
the base contains. So the checker no longer stops: it asks whether some admissible
composition reaches the declared figure and whether one reaches it without the element, and
for the taxable base it enumerates the placements the unknown element could have and keeps
the verdict the arithmetic singles out. An element being enumerated is not offered as its own
deviation, or the unknown itself turns into an asymmetry finding.

That debt is paid. `F1_compensation_in_insurable` has its mutation (a leaver's
compensation pulled into the insurable income — one row in five now carries a real чл. 224
amount, `COMPENSATION_RATE` in the generator says why), the statutory escape hatch covers
both settled elements symmetrically, and the
placement logic lives in `statutory_misplacements()`, pinned directly by `run_tests`'
selftest — directly, because the generator's own NEEDS_PRACTICE gate refuses to build the
only state the hatch runs in, so seeds prove nothing about it.

Still parked, with the reason on record: чл. 17, ал. 2 НСОРЗ (a periodic or annual payment
made after the leave obliges recalculation of leave already paid) is stated in the skill's
E3 but tested by nothing — a faithful fixture needs a correction column the layout does not
have, and adding one touches every fixture and answer key. чл. 18, ал. 1, изр. второ is NOT
parked: the pair fixture now gives one July in eight fewer than 10 worked days, the clean
rows use the agreed-salary fallback, and the mutation misapplies изр. първо to them.

Both scenarios now inject the opposite error — and, since the plugin asks at install time
which of the two lawful readings to apply, they inject it in **both** polarities. Each seed
draws `policy["bonus_in_base"]`, the fixture is built consistently under it, the checker is
told it (told, not inferred: it is the auditor's configuration, not a property of the file),
and the mutation writes whichever side the file did not use. `run_tests.py` prints the split
and fails the suite if a run never exercised one of the two — coverage of one reading is not
coverage. The statute itself is quoted in `stavki.md`, where a status caps what a finding may
claim. The two bases are not equally well founded, and the split is recorded
there: чл. 17 and чл. 18 are `ДВ` and cover чл. 177 and чл. 228 КТ only, so carrying the
same composition to the чл. 40, ал. 5 КСО base is an analogy, held at `за потвърждение`.

Three decisions in its construction are worth knowing.

**Isolation.** The model gets a directory in `/tmp` with two files: the workbook
and `dogovori.csv`, holding the contracted salaries and supplement percentages —
what an auditor legitimately has. The manifest — the answer key — is deleted from
`test/tmp` the moment the generator writes it and lives only in the harness process
(and, graded, in the results file, which the session cannot see); the repository is
not passed with `--add-dir`, and the openpyxl environment is a separate venv outside
it. Bash is allowed for that venv's python and `ls` only. The reason is blunt: `test/`
holds a full implementation of every check. A run that reads it measures reading,
not expertise.

That isolation is not complete, and the harness says so. The skill is installed as
a symlink into the same repository and the model legitimately reads its reference
files, so a path to `test/` exists and cannot be closed without closing the skill.
So the whole tool stream is recorded and screened twice over: the tool *inputs* for
a path into the checking code, and the tool *results* for the answer key's own
vocabulary — the manifest's `"expected"` key and the scenario identifiers, which
occur nowhere the session may legitimately read. A run that reached either is
reported as tainted and kept out of the statistics. `--selftest` proves the screen
on a synthetic transcript, and proves that the skill's own files do not trip it.

**The scenario catalogue is not given to the model.** Otherwise the task becomes
label matching. All that is asked for is a list of findings: where, severity, one
sentence and the two figures. The mapping happens in the harness, by row and by
keywords in the description.

The pair prompt broke that rule until 2026-09-03: after "check each month and the two
against each other" it went on to name "the paid-leave base, the thresholds and the norm
on each sheet, the movement of salaries between the months" — the three categories the
fixture injects, in order. The sentence is gone. **Pair scores from before that date are
not comparable with those after it**: the earlier ones measured how well the skill
follows a hint, the later ones whether it looks there unprompted. The first live pair
run (01–02.09.2026) is such an earlier score.

**The result is three numbers, not one.** The keywords are judgement, not
measurement, and are reported as such:

| Measure | What it means |
| --- | --- |
| located | was a defect reported on this row at all — objective |
| identified | does the description match what was injected — by keyword, visible in `eval_skill.py` — **and** does the finding assert a defect: severity `нарушение`, `риск` or `дефект`, and a sentence that does not deny it. A `бележка` saying the row is correct stands on the right row and mentions the right word; it is „located", not „identified" |
| unattributed | everything the model found that was not injected |

Every keyword entry has at least two groups, and one of them names what is *wrong* —
the direction, the reason, the shape of the mistake. An entry naming only the subject
scored the opposite finding as identified („ТЗПБ е приложен над дължимия процент" for
a rate applied *below* the due one); `--selftest` holds those sentences and fails the
moment one of them scores again.

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

**The grading is itself tested, for free.** `--selftest` builds thirteen synthetic
reports — a skill that refused, one that guessed a rate, one that went silent, one that
did both wrong, the two phrasings a live run actually produced, three guesses worded
with the adjective a few words from its noun ("минималната заплата за 2027 г.",
"максималния размер на осигурителния доход", "минималното месечно възнаграждение", one
of them graded "Нарушение" with a capital), and four gaps that are not the gap under
test ("няма формула за 07.2027", "няма посочена часова ставка", a gap and a rate in two
unrelated sentences, two years with no rate between them) — and asserts the three checks
separate them. The third check requires the gap and the rate it concerns in one clause.
It runs in CI. The reason is that the run it guards costs real money and a quarter of an
hour, and a grader that passes everything is much the likeliest way for a check like this
to be quietly useless; without the self-test that would be discovered only after paying
for it.

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

## How much of `proverki.md` the suites reach

**32 of the 86 checks** have a test behind them: 14 implemented in suite 1's static
checker (11 of them in the answer key, three — F1, F6 on the composition, I2 — asserted
to stay silent on a correct row), 21 across the generated suites, six shared between the
two (B4, C2, F1, F6, F9, I1), and three — A10, I9, I10 — added by suite 5, the
комплект. The number is worth stating
plainly, because a green run is easy to read as "the skill is tested" when what it
means is "the tested part of the skill still works".

Coverage is not spread evenly, and the shape of the gap is not accidental. Group K
sits at 8 of 10 because file construction is exactly what a generated workbook can
express. Two groups sit at zero:

- **H — termination and severance.** A month's payroll shows the payment, not the
  entitlement. To inject a defect here the fixture would need the event behind it:
  a termination on a given ground, a notice period, a service record, a base drawn
  from a month the sheet does not contain. That is a different fixture, not another
  scenario in this one — the two-month workbook exists because paid leave needed
  the preceding month, and severance needs considerably more than that.
- **J — deadlines and formalities.** These are checks about *when* something was
  done and whether it was filed, and a spreadsheet of amounts carries neither.
  They are answered from dates and documents outside the payroll.

The rest of the gap is ordinary and closable: `B2`, `B3`, `C3`–`C6`, `E1`, `E2`
and the like are all expressible in a monthly sheet and simply have no scenario yet.
Nothing about the fixtures blocks them. `A6`, `I1`, `F1` and `F6` were in that list
until their checker branches — present since the suite was written — got the
mutations that let them fire.

Two things this does **not** mean. An uncovered check is not an unimplemented one —
`proverki.md` describes all 86 and the skill is asked to apply all 86; what is
missing is the proof that it does. And the count is of checks, not of risk: the
covered ones were chosen because they are the errors that actually turn up in real
payrolls, which is why the suites keep finding bugs in themselves.

## Suite 5: the chain below the payroll

Until 05.09.2026 this section said the opposite of what it says now: I9, I10, I11 and
the cross-document half of A9 had **no fixture at all**, because every workbook in this
repository was a single payroll and those checks reconcile the payroll against the
documents downstream of it. `generate_komplekt.py` writes those documents.

A комплект is one month: `vedomost.xlsx`, `dogovori.csv`, `deklaracia_1.csv`,
`deklaracia_6.csv` and `plateni.csv`. The chain is built forward — обр. 1 from the
payroll, обр. 6 from обр. 1, the payments from обр. 6 and the nets — so a break stops
the copying at exactly one link and the other three still agree with each other.
Without that ordering one mutation would light up three checks and "its own signal and
nothing else" could not be asserted at all. `komplekt_test.py` requires a clean set to
raise **nothing**, each break to raise its own finding alone, and one break from each
of the seven groups at once to produce exactly those seven.

| id | check | the break |
| --- | --- | --- |
| `A10_midmonth_annex` | A10 | a raise effective the 16th paid from the 1st — everything below it is computed from the wrong base and agrees with itself, and only the contract disagrees |
| `I9_person_missing_in_d1` | I9, transition 1 | someone in the payroll has no row in обр. 1 |
| `I9_extra_person_in_d1` | I9, transition 1 | обр. 1 carries a person the payroll does not |
| `I9_insurable_differs_in_d1` | I9, transition 1 | т. 21 is not the payroll's insurable income |
| `I9_sick_days_differ_in_d1` | I9, transition 1 | т. 16.А is not the payroll's sick days |
| `I9_d6_not_sum_of_d1` | I9, transition 2 | обр. 6 is not the sum of the обр. 1 rows |
| `I9_declared_not_paid` | I9, transition 3 | less reached НАП than обр. 6 declares |
| `I9_ledger_differs` | I9, transition 4 | the trial balance owes НАП something обр. 6 does not — liabilities, never the cost of labour, which is K7's |
| `I9_net_not_paid` | I9, the net leg | someone was paid less than their net |
| `I10_duplicate_payment` | I10 | one net paid twice |
| `I10_iban_shared` | I10 and A9 | two people, one bank account — A9 calls it master data, I10 is where it becomes visible |

**The payroll itself is clean.** Every row comes from `trz_model`, so the whole set is
also a false-positive test: a finding on a row is unattributed by construction. That is
the half of the standard the other suites get from their answer key and this one gets
from its silence.

`eval_skill.py --komplekt` sends the whole directory to a live session. Its keyword
universe, `KOMPLEKT_KEYWORDS`, is a **first cut** — no paid transcript has been graded
against it, so a miss there is at least as likely to be a keyword gap as a model
failure; triage each one against the saved transcript and re-grade for free. What the
suite can prove without paying is that a *correct* report is recognised:
`komplekt_test.py` grades one synthetic, correctly-worded sentence per break and
requires every one to come back identified, so a pattern that matches nothing can never
reach a paid run.

### The first paid run on it

**Claude Fable 5.1, seeds 1 and 2, on 2.12.0, USD 9.50** (USD 4.91 and 4.59; 20 and 22
turns; about ten minutes each). Live **7 of 8 identified, 8 of 8 located, none missed**.
Re-graded after one keyword fix: **8 of 8**.

The fix is the whole point of writing this down. `I9_insurable_differs_in_d1` was
graded "located only" on seed 1 for a finding that was not merely correct but better
than the sentence the pattern had been written against:

> „В обр. 1 за Лице 2 (СЛ-002) т.21 осигурителен доход е 1647.25 при 1797.25 във
> ведомостта; вноските в същия ред на обр. 1 са върху 1797.25, така че т.21 е
> грешното число."

It works out **which** of the two figures is wrong, from the contributions on the same
row, and the fixture agrees — the break moves т. 21 alone and leaves the dues computed
from the payroll. The pattern wanted „разлика / разминава / занижен" and got „X при Y"
and „грешното число". Widened at the phrasing rather than by dropping the requirement:
the first pattern must still match, so nothing about other material reaches it through
the second. That sentence is now the one `komplekt_test.py` grades for this break — the
only entry in `CORRECT_REPORT` that is not invented, and worth more than the invented
ones because it is wording a model actually produced.

Two things worth recording beyond the score:

- **The root-cause discipline held.** Seed 1's unattributed findings are the
  consequences of the person missing from обр. 1 — обр. 6 short by exactly that
  person's contributions, the transfers to НАП short by 990.80 „от които 870.80" —
  written as consequences of one cause, not as three independent defects.
- **The document-is-data rule fired unprompted.** Seed 2 reported that cell A3 of the
  payroll asserts „ТЗПБ по КИД: 0.5%" — a rate stated inside the audited file — as a
  `бележка`, which is exactly what `SKILL.md` requires and nothing in the prompt asked
  for.

The unattributed findings are otherwise the missing-data list the fixture cannot
supply: no КИД, no dates of birth (so УПФ cannot be confirmed), no hire dates behind
the class percentages, no dates in the payment file, and no formulas in the workbook.
None of them is a false `нарушение` on a clean row.

**What is still not reached.** The statutory half of `A9` — НКПД, category of labour and
the agreed working time — is checked against documents no fixture writes. `I11` was on
this list until suite 6 below.

## Why `SKILL.md` can be trimmed at all

It could not be, before. `SKILL.md` is loaded on every invocation and the reference files
load on demand, so moving a rule out of it is a real change: a sentence in a reference is
read when the model opens that file, not necessarily at the moment it decides. Most of
what is in `SKILL.md` is there because a paid run showed the model got it wrong without
it, so "shorten the prompt" and "keep what the runs bought" pull against each other.

`PAID_GUIDANCE` is what makes the trade safe to make at all: it searches the whole skill —
`SKILL.md` and every reference — so a rule may *move* and may not *vanish*. 491 → 346
lines, with the report contract in `references/otchet.md`, the чл. 17 rule beside the text
of чл. 17 in `stavki.md`, and the spreadsheet detail in `proverki.md` where the K group
already is. All eleven pinned rules survive: five in `SKILL.md`, five in `otchet.md`, one
in `stavki.md`.

What is **not** proven by any of this is that the model still applies the five rules that
moved as reliably from a file it must open as from the prompt it always has. Only a paid
run says that, and the honest reading of the current numbers — 34/35 and 8/8 — is that
they were measured on the 491-line version.

## The fourth review, item by item

Kept here because "we looked at it and decided not to" is worth as much as "we did it",
and only one of the two survives in a diff.

| # | asked for | what happened |
| --- | --- | --- |
| 1 | an I11 end-to-end test | suite 6 |
| 2 | stronger provenance in `stavki.md` | 16 КТ rows and the чл. 446 ГПК scale verified verbatim, `вторичен` → `ДВ`; per-section verification dates. The *structured* source model was not built — see below |
| 3 | a canonical normalised payroll schema | the mapping must now be stated before any arithmetic, and `tools/preflight.py` already emits a normalised extract with a cell reference per value |
| 4 | an explicit `AMBIGUOUS` state | answered without a sixth state: a column whose meaning is uncertain makes its dependent checks `недостатъчни данни`, naming the column |
| 5 | LLM eval as a regression gate | refused as a PR gate; answered by `PAID_GUIDANCE`, which is free, and a dispatch-only paid job |
| 6 | cause → consequences in the output | **open.** The prose rule is in `otchet.md`; putting it in `findings.json` changes the eval contract mid-measurement and should follow a paid run, not precede one |
| 7 | I9 through to the ledger | the eleventh break in the комплект |
| 8 | evidence contracts for A5 and J | A5, J1, J2, J3 |
| 9 | J4 is too broad | split into five groups, each with its own evidence and result |
| 10 | an applicability matrix before the analysis | step 3а |
| 11 | a messy-workbook suite | five pathologies: error cells, hidden rows, hidden sheet, hidden columns, numbers as text, plus external links. **Partly open** — subtotal rows inside the data, copied sheets and named ranges have no fixture yet |
| 12 | a raw-value layer | already there: the audit reads the workbook twice, and K6 exists precisely because the displayed value is not the stored one |
| 13 | `Decimal` everywhere | **refused.** `r2()` already quantizes through `Decimal` with `ROUND_HALF_UP`, so the rounding is exact rather than float; converting the intermediate arithmetic is a large refactor with real regression risk and nothing measurable to gain |
| 14 | rules as executable metadata | **refused.** It splits the source of truth: `proverki.md` is what the skill reads, and a parallel machine-readable copy is the drift class this repository exists to prevent |
| 15 | `proverki.md` split into `rules/` | **deferred.** Still one navigable file |
| 16 | a shorter `SKILL.md` | 491 → 346 lines, with `PAID_GUIDANCE` making the move safe |
| 17 | an audit contract | the report opens with files, sizes, **sha256**, the reference file's verification date, the skill version and the applied setting |

Two are open on purpose (6 and the rest of 11), three are refused with a reason (13, 14,
15). Everything else is in the tree.

## What guards the guidance between paid runs

The paid eval is the only thing that measures whether `SKILL.md` still works, and it
cannot gate a pull request: the score moves ten points on one seed, and this repository
fails a suite for a single false positive. So a rewrite could make the guidance worse and
every check would stay green.

What *can* be free is refusing to let a rewrite silently **delete** a rule a paid run
already bought. `skill_test.PAID_GUIDANCE` pins eleven sentences by a short distinctive
phrase, each next to the incident that produced it — the first refusal run's missing
contribution, the 2.7.0 run measuring a 2027 payroll against the 2026 cap, the `вторичен`
row that produced a `нарушение` against a correct payroll, and so on. None of them can be
re-derived by reading the statute; each cost a run.

It is emphatically **not** a test that the guidance is good — it cannot be. It is the
difference between rewording a rule and losing it: rewording is free, and the phrase is
updated in the same commit. Losing one is what nothing noticed before.

## Suite 6: one person's timeline across months

`I11` is the last check `proverki.md` describes that no fixture could reach. The комплект
proves the chain *below* one month; this proves the chain *along* the months, which is a
different axis and needs a different fixture: five sheets for the same people, plus
`sabitiya.csv` — the вписване, the анекс, the заповед за отпуск, the болничен лист, the
заповед за прекратяване — which is what is supposed to explain what changes between them.

**Every month is internally correct on purpose.** The arithmetic reconciles, the bases are
right, each sheet would pass suites 1–4 on its own, and the suite asserts that before it
asserts anything else. The only thing that disagrees is the sequence. So `reconcile()`
may compare a month with another month or with an event, never a row with itself — a
check that could be written inside one sheet belongs in another suite.

| id | the break | the bullet of I11 it comes from |
| --- | --- | --- |
| `I11_salary_change_without_annex` | pay rises between months, no annex dated for it | „заплатата се променя … а допълнително споразумение за тази дата няма" |
| `I11_pay_after_termination` | a salary in a month after the termination date | „обезщетение при прекратяване, а лицето продължава да получава заплата" |
| `I11_severance_without_termination` | чл. 224 compensation with no order behind it | the same bullet, from the other side |
| `I11_sick_days_restart` | a spell continuing into the next month pays the employer's first days twice | „болничен … в следващия започва отново от първия ден" |
| `I11_class_raised_early` | the class moves before the anniversary | „клас, който се вдига без навършена година стаж" |
| `I11_class_not_raised` | the anniversary passes and the class does not move | „или не се вдига, когато е навършена" |

Each break maps onto a sentence in the skill, which is the test that keeps the suite
honest: a break that stops corresponding to one should be deleted rather than kept.

**Two bugs the suite found in its own generator before it found anything else.** The
first clean history was not clean — it paid the employer's two sick days in both months
of one continuous spell, which is precisely `I11_sick_days_restart`, planted by accident.
And the person carrying the class anniversary was also the person terminated in August,
so the month where the raise should appear had no row at all and `I11_class_not_raised`
could never fire. Both are the reason the clean fixture is asserted silent first.
