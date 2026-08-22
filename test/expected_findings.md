# Answer key for the static payroll

`vedomost_05_2026.xlsx` is entirely invented. It holds 10 people for May 2026 —
nine with deliberately injected defects and one wholly correct row, which serves
as the control against false positives.

The period is chosen on purpose: May 2026 falls in the 01.01–31.07.2026 regime,
and its norm is 18 working days / 144 hours (21 weekdays minus 1, 6 and 25 May,
because 24 May is a Sunday — чл. 154, ал. 2 КТ).

## Injected defects

| Row | Person | Defect | Check | Basis |
| --- | --- | --- | --- | --- |
| 6 | Иван Петров | Base pay 610.00 against a minimum wage of 620.20 | B1 | ПМС № 243, ДВ бр. 98/2025 |
| 7 | Мария Георгиева | 0% supplement for 12 years of service (7.2% due) | C1 | ПМС № 147; чл. 12 НСОРЗ |
| 8 | Георги Иванов | 10 overtime hours paid without the premium | D4 | чл. 262, ал. 1, т. 1 КТ |
| 9 | Елена Димитрова | Insurable income 3815.00, the cap never applied | B4 | чл. 9 ЗБДОО 2026 |
| 10 | Петър Стоянов | 60 night hours with no supplement | D6 | чл. 8 НСОРЗ |
| 11 | Анна Тодорова | 3 sick days at the employer's expense instead of 2 | F9 | чл. 40, ал. 5 КСО |
| 12 | Димитър Николов | Net does not reconcile with gross minus the deductions | I1 | arithmetic |
| 14 | Николай Христов | 8 hours on a public holiday paid at single rate | D7 | чл. 264 КТ |
| 15 | Виктор Маринов | An attachment of 500.00 against a net of 723.53 | G2 | чл. 446 ГПК |

## The control row

| Row | Person | What is special |
| --- | --- | --- |
| 13 | Стефка Ангелова | Part time, 4 hours, salary 310.10 = half the minimum wage. Everything correct. Must produce no finding. |

## What a correct result looks like

- **Nine out of nine** injected defects found.
- **Zero** findings on row 13.
- Row 15 comes out as **`за проверка`, not `нарушение`.** The чл. 446 ГПК
  thresholds are not in `references/stavki.md`, and the number of dependants is
  missing from the payroll. The skill is obliged to refuse a firm conclusion and
  to say exactly what it lacks. Declaring it a violation is a defect in the skill,
  even when the conclusion happens to be right.

## Known limitations of this suite

- Row 11 carries a tenth, unplanned defect: the stated supplement is 3.6% while
  the amount accrued is 0.00. It appeared as a side effect of constructing the
  row. The skill catches it as a separate C2 finding.
- The check on overtime limits (D3) is inapplicable, because a single month was
  supplied. It needs the accumulated volume for the year.
- The contract-versus-payroll check (A6) is inapplicable — this suite ships no
  employment contracts.
