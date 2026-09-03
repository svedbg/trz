# Answer key for the static payroll

`vedomost_05_2026.xlsx` is entirely invented. It holds 11 people for May 2026 —
nine with deliberately injected defects and two wholly correct rows, which serve
as the controls against false positives. Row 11 carries a control of a
different kind: a treatment that *looks* inconsistent and is correct — see below.

The period is chosen on purpose: May 2026 falls in the 01.01–31.07.2026 regime,
and its norm is 18 working days / 144 hours (21 weekdays minus 1, 6 and 25 May,
because 24 May is a Sunday — чл. 154, ал. 2 КТ).

## Injected defects

| Row | Person | Defect | Check | Basis |
| --- | --- | --- | --- | --- |
| 6 | Иван Петров | Base pay 610.00 against a minimum wage of 620.20 | B1 | ПМС № 243, ДВ бр. 98/2025 |
| 7 | Мария Георгиева | 0% supplement for 12 years of service (7.2% due) | C1 | ПМС № 147; чл. 12 НСОРЗ |
| 8 | Георги Иванов | 10 overtime hours paid without the premium | D4 | чл. 262, ал. 1, т. 1 КТ; чл. 7 НСОРЗ for the base |
| 9 | Елена Димитрова | Insurable income 3815.00, the cap never applied | B4 | чл. 9 ЗБДОО 2026 |
| 10 | Петър Стоянов | 60 night hours with no supplement | D6 | чл. 8 НСОРЗ |
| 11 | Анна Тодорова | 3 sick days at the employer's expense instead of 2 | F9 | чл. 40, ал. 5 КСО |
| 12 | Димитър Николов | Net does not reconcile with gross minus the deductions | I1 | arithmetic |
| 14 | Николай Христов | 8 hours on a public holiday paid at single rate | D7 | чл. 264 КТ |
| 15 | Виктор Маринов | An attachment of 500.00 against a net of 723.53 | G2 | чл. 446 ГПК |

## The control rows

| Row | Person | What is special |
| --- | --- | --- |
| 13 | Стефка Ангелова | Part time, 4 hours, salary 310.10 = half the minimum wage. Everything correct. Must produce no finding. |
| 16 | Росица Кънчева | Overtime, night work and a public holiday paid at **exactly** the statutory minimum: 8 overtime hours at 6.475 × 1.5 = 77.70, 8 holiday hours at 6.475 × 2 = 103.60, 16 night hours at 0.9303 = 14.88 — on the чл. 7 НСОРЗ base, (900.00 + 32.40) / 144. Everything correct. Must produce no finding. |

Row 16 is the anchor for the rates the checker applies. Every other row with those
hours pays nothing above the single rate, so a checker with a wrong premium, a wrong
night rate or a wrong base fired on them exactly like a right one — a copy of the test
model with overtime at +25% and the holiday multiplier at 1.5 passed this suite. A row
paid to the cent at the minimum turns any upward drift into a false positive here.
Downward drift is `rates_test.py`'s job: the constants are read against `stavki.md`,
and the worked examples the reference states are recomputed from them.

## The second control: the sick-pay asymmetry on row 11

The injected defect on row 11 is the third employer-paid sick day (F9). The
**treatment** of the sum is correct, and it is a control in its own right:

| Base | Row 11 | Rule | Source |
| --- | --- | --- | --- |
| Осиг. доход | 836.56 — the whole gross, sick pay included | inside | чл. 3, ал. 1 НЕВДПОВ |
| Данъчна основа | 618.55 = 836.56 − 102.73 − 115.28 | outside | чл. 24, ал. 2, т. 14 ЗДДФЛ |

The same sum is inside one base and outside the other, and **both are right**: the
asymmetry is prescribed by statute, not a defect in the file. Reporting it — under
F1, F6, F9 or the internal-consistency rule — is a false positive and fails the suite
exactly as a finding on row 13 does.

Until 31.08.2026 the fixture carried the inverted treatment: an insurable income of
733.83, the gross minus the sick pay, and the sick pay left inside the taxable base.
That was never one of the injected defects — it was simply wrong, and it survived
because this suite checked only the *number* of employer-paid sick days and never the
composition of the two bases. `checks_test.py` now checks both: **F1**, that the
insurable income is the whole gross up to the ceiling, and **F6**, that the taxable
base subtracts the sick pay. Both were confirmed to go red against the old fixture
before it was corrected.

## Consequential findings

Two further findings follow from the injected ones rather than being injected
themselves. Both are expected, and `checks_test.py` asserts them alongside the
nine — a run that stops producing them has changed behaviour and fails.

| Row | Check | Why it follows |
| --- | --- | --- |
| 9 | B4 → **F2** | The insurable income was never capped, so the contributions computed from it are wrong too. One defect, two findings. |
| 11 | **C2** | The stated supplement is 3.6% while the amount accrued is 0.00. It appeared as a side effect of constructing the row. |

So the correct total is **11 findings: 9 injected + 2 consequential.**

## What a correct result looks like

- **Nine out of nine** injected defects found, plus the two consequential ones.
- **Zero** findings on rows 13 and 16.
- Row 15 comes out as **`за проверка`, not `нарушение`.** The чл. 446 ГПК
  thresholds are not in `references/stavki.md`, and the number of dependants is
  missing from the payroll. The skill is obliged to refuse a firm conclusion and
  to say exactly what it lacks. Declaring it a violation is a defect in the skill,
  even when the conclusion happens to be right.

## Known limitations of this suite

- The check on overtime limits (D3) is inapplicable, because a single month was
  supplied. It needs the accumulated volume for the year.
- The contract-versus-payroll check (A6) is inapplicable — this suite ships no
  employment contracts.
