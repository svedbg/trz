# -*- coding: utf-8 -*-
"""Suite 1: the checks of references/proverki.md against the May 2026 payroll.

Rates: references/stavki.md, regime 01.01-31.07.2026.

This suite tests knowledge of the rates and of the working-time regimes -
minimum wage, the length-of-service supplement, overtime, night work, public
holidays, employer-paid sick days, the cap, vertical arithmetic, an attachment.
The answer key is in expected_findings.md; suite 2 covers the construction of
the file instead.

Column names and statutory citations stay Bulgarian, because both are quoted
from the domain. The code is English.
"""
import os

import openpyxl

# --- rates (stavki.md, period 01.01-31.07.2026) ---
MIN_WAGE = 620.20        # ПМС 243, ДВ бр.98/18.11.2025                    [ДВ]
MIN_WAGE_HOUR = 3.74     # same                                            [ДВ]
MAX_INSURABLE = 2111.64  # чл.9 ЗБДОО 2026, ДВ бр.68/28.07.2026            [ДВ]
MIN_INSURABLE_ACTIVITY = None   # Приложение №1 - MISSING from the reference
SENIORITY_MIN = 0.006    # ПМС 147, ДВ бр.56/10.07.2007                    [ДВ]
NIGHT_HOUR = round(0.0015 * MIN_WAGE, 4)   # чл.8 НСОРЗ = 0.9303
OVERTIME_WORKDAY = 0.50  # чл.262 ал.1 т.1 КТ                              [ДВ]
HOLIDAY_MULTIPLIER = 2.0  # чл.264 КТ - double rate                        [ДВ]
SICK_DAYS_EMPLOYER = 2   # чл.40 ал.5 КСО                                  [ДВ]
SICK_RATE = 0.70         # чл.40 ал.5 КСО                                  [ДВ]
EMPLOYEE_TOTAL = 0.1378  # [secondary source]
TAX_RATE = 0.10          # [secondary source]

WORK_DAYS, NORM_HOURS, FULL_DAY = 18, 144, 8
TOL = 0.02

HERE = os.path.dirname(os.path.abspath(__file__))
wb = openpyxl.load_workbook(os.path.join(HERE, "vedomost_05_2026.xlsx"), data_only=True)
ws = wb.active
HDR = 5
COL = {ws.cell(row=HDR, column=c).value: c for c in range(1, ws.max_column + 1)}


def get(r, name):
    return ws.cell(row=r, column=COL[name]).value


findings = []


def report(severity, row, person, check, basis, stated, due, action):
    findings.append(dict(
        severity=severity, row=row, person=person, check=check, basis=basis,
        stated=stated, due=due,
        difference=(None if stated is None or due is None else round(due - stated, 2)),
        action=action))


rows = [r for r in range(HDR + 1, ws.max_row + 1) if isinstance(get(r, "№"), int)]

for r in rows:
    name = get(r, "Име")
    years = get(r, "Стаж (г.)")
    hours_per_day = get(r, "Раб. време (ч/ден)")
    days_worked = get(r, "Отраб. дни")
    overtime_hours = get(r, "Извънр. часове (раб. дни)") or 0
    holiday_hours = get(r, "Часове на празник") or 0
    night_hours = get(r, "Нощни часове") or 0
    sick_days = get(r, "Дни болничен от работодател") or 0
    base_pay = get(r, "Основна заплата")
    seniority_pct = get(r, "Клас %") or 0
    seniority_sum = get(r, "Клас сума") or 0
    overtime_premium = get(r, "Доп. извънреден") or 0
    holiday_premium = get(r, "Доп. празник") or 0
    night_premium = get(r, "Доп. нощен") or 0
    sick_pay = get(r, "Болнични от работодател") or 0
    gross = get(r, "БРУТО")
    insurable = get(r, "Осиг. доход")
    employee_contributions = get(r, "Лични осигуровки")
    taxable = get(r, "Данъчна основа")
    tax = get(r, "ДДФЛ")
    deductions = get(r, "Удръжки") or 0
    net = get(r, "НЕТО")

    part_time = hours_per_day / FULL_DAY
    hourly = base_pay / (days_worked * hours_per_day) if days_worked else None

    # --- B1 minimum wage ---
    due_min = round(MIN_WAGE * part_time, 2)
    if base_pay + 1e-9 < due_min - TOL:
        report("нарушение", r, name, "B1 base pay below the minimum wage",
               "чл.244 т.1 КТ; ПМС №243 от 13.11.2025, ДВ бр.98/2025",
               base_pay, due_min,
               "Top up to the minimum wage and sign an annex to the contract.")

    # --- B3 minimum insurable income by activity: not verifiable, see the summary ---

    # --- B4 maximum insurable income ---
    if insurable > MAX_INSURABLE + TOL:
        report("нарушение", r, name, "B4 insurable income above the maximum",
               "чл.9 ЗБДОО за 2026 г., ДВ бр.68 от 28.07.2026",
               insurable, MAX_INSURABLE,
               "Cap the insurable income at 2111.64 EUR and correct the "
               "contributions (Декларация обр. 1 и 6).")

    # --- C1/C2 length-of-service supplement ---
    if years and years >= 1:
        due_pct = round(years * SENIORITY_MIN * 100, 2)
        if seniority_pct + 1e-9 < due_pct:
            report("нарушение", r, name,
                   f"C1 supplement: {seniority_pct}% applied for {years} years of service",
                   "ПМС №147 от 29.06.2007, ДВ бр.56/2007; чл.12 ал.1 НСОРЗ",
                   round(base_pay * seniority_pct / 100, 2),
                   round(base_pay * due_pct / 100, 2),
                   f"Accrue at least {due_pct}% on the base salary.")
        else:
            expected = round(base_pay * seniority_pct / 100, 2)
            if abs(seniority_sum - expected) > TOL:
                report("нарушение", r, name,
                       "C2 supplement: the amount does not match the stated percentage",
                       "чл.12 ал.1 НСОРЗ", seniority_sum, expected,
                       "Recompute the supplement on the base salary.")

    # --- D4 overtime ---
    if overtime_hours:
        due = round(hourly * overtime_hours * (1 + OVERTIME_WORKDAY), 2)
        if overtime_premium + TOL < due:
            report("нарушение", r, name,
                   f"D4 {overtime_hours} overtime hours on working days without the premium",
                   "чл.262 ал.1 т.1 КТ (+50%)", overtime_premium, due,
                   "Accrue the premium.")

    # --- D6 night work ---
    if night_hours:
        due = round(NIGHT_HOUR * night_hours, 2)
        if night_premium + TOL < due:
            report("нарушение", r, name,
                   f"D6 {night_hours} night hours without the supplement",
                   "чл.8 НСОРЗ (0.15% of the minimum wage per hour)",
                   night_premium, due, "Accrue the night supplement.")

    # --- D7 work on a public holiday ---
    if holiday_hours:
        due = round(hourly * holiday_hours * HOLIDAY_MULTIPLIER, 2)
        if holiday_premium + TOL < due:
            report("нарушение", r, name,
                   f"D7 {holiday_hours} hours on a public holiday below the double rate",
                   "чл.264 КТ", holiday_premium, due, "Top up to the double rate.")

    # --- F9 sick days ---
    if sick_days > SICK_DAYS_EMPLOYER:
        per_day = round(sick_pay / sick_days, 2) if sick_days else 0
        report("нарушение", r, name,
               f"F9 the employer pays {sick_days} sick days instead of {SICK_DAYS_EMPLOYER}",
               "чл.40 ал.5 КСО, изм. ДВ бр.106/2023, в сила от 01.01.2024",
               sick_pay, round(per_day * SICK_DAYS_EMPLOYER, 2),
               "The first 2 working days are at the employer's expense; the rest "
               "are paid by the state fund.")

    # --- F2 employee contributions ---
    expected = round(min(insurable, MAX_INSURABLE) * EMPLOYEE_TOTAL, 2)
    if abs(employee_contributions - expected) > 0.05:
        report("нарушение", r, name,
               "F2 employee contributions are not 13.78% of the insurable income "
               "(capped)", "чл.6 ал.1 и ал.3 КСО", employee_contributions, expected,
               "Recompute the contributions.")

    # --- F6 taxable base and tax ---
    expected_base = round(gross - employee_contributions, 2)
    if abs(taxable - expected_base) > TOL:
        report("нарушение", r, name,
               "F6 taxable base is not gross minus employee contributions", "ЗДДФЛ",
               taxable, expected_base, "Correct the taxable base.")
    expected_tax = round(taxable * TAX_RATE, 2)
    if abs(tax - expected_tax) > TOL:
        report("нарушение", r, name, "F6 tax is not 10% of the taxable base", "ЗДДФЛ",
               tax, expected_tax, "Correct the tax.")

    # --- I2 the accruals add up to the gross ---
    accrual_sum = round(base_pay + seniority_sum + overtime_premium + holiday_premium
                        + night_premium + sick_pay, 2)
    if abs(gross - accrual_sum) > TOL:
        report("нарушение", r, name, "I2 the accruals do not add up to the gross",
               "arithmetic consistency", gross, accrual_sum,
               "Check the accruals by type.")

    # --- I1 vertical reconciliation ---
    expected_net = round(gross - employee_contributions - tax - deductions, 2)
    if abs(net - expected_net) > TOL:
        report("нарушение", r, name,
               "I1 net is not gross minus contributions minus tax minus deductions",
               "arithmetic consistency", net, expected_net,
               "Correct the amount paid.")

    # --- G2 protected minimum income ---
    if deductions > 0:
        report("за проверка", r, name,
               f"G2 deduction of {deductions:.2f} EUR against a net before deductions "
               f"of {round(gross - employee_contributions - tax, 2):.2f} EUR",
               "чл.446 ГПК - the thresholds are NOT in references/stavki.md",
               deductions, None,
               "Enter the чл.446 ГПК thresholds and the number of dependants, then "
               "recompute.")

# --- report ---
ORDER = {"нарушение": 0, "риск": 1, "за проверка": 2, "бележка": 3}
findings.sort(key=lambda f: (ORDER[f["severity"]], f["row"]))
print(f"FINDINGS: {len(findings)}\n" + "=" * 100)
for f in findings:
    print(f"[{f['severity'].upper():11}] row {f['row']:2d} · {f['person']}")
    print(f"  {f['check']}")
    print(f"  Basis: {f['basis']}")
    if f["due"] is not None:
        print(f"  Stated {f['stated']:.2f} | due {f['due']:.2f} | "
              f"difference {f['difference']:+.2f} EUR")
    print(f"  Action: {f['action']}\n")

affected = sorted({f["person"] for f in findings if f["severity"] == "нарушение"})
underpaid = sum(f["difference"] for f in findings
                if f["severity"] == "нарушение" and f["difference"]
                and f["difference"] > 0 and "above the maximum" not in f["check"])
print("=" * 100)
print(f"People with violations: {len(affected)} of {len(rows)}")
print(f"Underpaid to the workers (excluding insurance corrections): {underpaid:.2f} EUR")
print(f"People with no findings: "
      f"{sorted(set(get(r, 'Име') for r in rows) - {f['person'] for f in findings})}")
if MIN_INSURABLE_ACTIVITY is None:
    print("B3 minimum insurable income by economic activity: NOT APPLICABLE - "
          "Приложение №1 to the ЗБДОО is not in references/stavki.md")
