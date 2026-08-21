# -*- coding: utf-8 -*-
"""Shared model for the structural test suite.

One source of truth for:
  * the rates of the two 2026 regimes (references/stavki.md),
  * working days per month (чл. 154 КТ),
  * money rounding,
  * the "clean" payroll — what every row looks like when nothing is wrong.

The generator builds from this model and then breaks it on purpose. The checker
recomputes from the same model and must find exactly what was broken.

Column names stay in Bulgarian: they are spreadsheet headers, i.e. data, and the
checker looks them up by their exact text. Everything else is English.

On the contested parts. How benefits in kind and the excess over the
social-expense threshold are treated has more than one defensible reading (see
proverki.md, F10). The model therefore does not fix an answer: a `policy` is
chosen per file and applied consistently. The suite tests **consistency**, not
doctrine — which is also how the skill is told to behave.
"""
from decimal import Decimal, ROUND_HALF_UP
import datetime

# ------------------------------------------------------------------ rounding

def r2(x):
    """Money: two decimals, half away from zero. Not banker's rounding."""
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# --------------------------------------------------------------------- rates
# references/stavki.md, verified 21.08.2026. 2026 is split into two regimes
# because the budget was adopted late: the thresholds change on 01.08.2026.
# Every figure here is cross-checked against the reference file by rates_test.py.

REGIMES = {
    "H1": dict(period="01.01-31.07.2026", max_insurable=2111.64,
               min_insurable_self=550.66, min_wage=620.20),
    "H2": dict(period="01.08-31.12.2026", max_insurable=2300.00,
               min_insurable_self=620.20, min_wage=620.20),
}

EMPLOYEE = {                  # чл. 6, ал. 1 и ал. 3 КСО; ЗЗО - third labour category
    "pension": 6.58,          # fund "Pensions", born after 31.12.1959
    "sickness": 1.40,         # general sickness and maternity
    "unemployment": 0.40,
    "health": 3.20,
    "upf": 2.20,              # supplementary mandatory pension fund
}
EMPLOYEE_TOTAL = 13.78        # the control sum that always holds

EMPLOYER_SOCIAL = 8.22 + 2.10 + 0.60      # 10.92, excluding the accident rate
EMPLOYER_UPF = 2.80
EMPLOYER_HEALTH = 4.80
TZPB_RANGE = (0.40, 1.10)                 # чл. 6, ал. 1, т. 5 КСО; exact % per КИД

TAX_RATE = 0.10                           # ЗДДФЛ
SENIORITY_RATE = 0.6                      # ПМС № 147 - % per year of service
SICK_DAYS_EMPLOYER = 2                    # чл. 40, ал. 5 КСО, from 01.01.2024
SICK_RATE = 0.70                          # чл. 40, ал. 5 КСО
HEALTH_ON_INCAPACITY = 4.80               # чл. 40, ал. 1, т. 5 ЗЗО - employer's cost
RELIEF_LIMIT = 0.10                       # чл. 42, ал. 3 във вр. с чл. 19 ЗДДФЛ

# 60 лв in euro, at the fixed rate. Derived rather than copied, so that
# rates_test.py can check it against the reference file.
# STATUS: unconfirmed. The exact conversion is 30.6773; whether the legislator
# adopted that or rounded it is not established. See stavki.md.
FIXED_EUR_RATE = 1.95583
SOCIAL_EXPENSE_THRESHOLD = r2(60 / FIXED_EUR_RATE)      # 30.68

TOL = 0.02          # money comparisons
TOL_STRICT = 0.005  # totals and control columns


def regime_for(year, month):
    return "H1" if (year, month) <= (2026, 7) else "H2"


# --------------------------------------------------------------- working days
# Bulgarian public holidays 2026. Rule of чл. 154, ал. 2 КТ: when a holiday falls
# on a Saturday or Sunday, the next working day is a day off.
HOLIDAYS_2026_FIXED = [
    (1, 1), (3, 3), (5, 1), (5, 6), (5, 24), (9, 6), (9, 22), (12, 24), (12, 25), (12, 26),
]
HOLIDAYS_2026_EASTER = [(4, 10), (4, 12), (4, 13)]   # Good Friday, Easter, Easter Monday


def _days_off_2026():
    days = set()
    for m, d in HOLIDAYS_2026_FIXED:
        dt = datetime.date(2026, m, d)
        if dt.weekday() >= 5:                 # falls on a weekend
            while dt.weekday() >= 5 or dt in days:
                dt += datetime.timedelta(days=1)
        days.add(dt)
    for m, d in HOLIDAYS_2026_EASTER:
        days.add(datetime.date(2026, m, d))
    return days


DAYS_OFF_2026 = _days_off_2026()


def working_days(year, month):
    """Working days in the month: weekdays minus public holidays."""
    d = datetime.date(year, month, 1)
    n = 0
    while d.month == month:
        if d.weekday() < 5 and d not in DAYS_OFF_2026:
            n += 1
        d += datetime.timedelta(days=1)
    return n


# ------------------------------------------------------------------- columns
# A wide western layout - the shape a payroll kept in Excel by an accounting firm
# tends to have. Headers are Bulgarian because they are data; the order and the
# presence of helper and control columns mirror the real thing.
COLUMNS = [
    "№", "Име", "Отдел",
    "Отраб. дни", "Дни платен отпуск", "Дни болничен", "Дни майчинство",
    "Основна за отработеното", "Клас %", "Клас сума", "Бонус",
    "Платен отпуск", "Обезщетение чл. 224", "Болнични (работодател)",
    "БРУТО",
    "ДОО пенсии", "ДОО ОЗМ", "ДОО безработица", "ЗО лична", "ДЗПО-УПФ лична",
    "Лични вноски общо",
    "Осигурителен доход", "Данъчна основа", "ДДФЛ",
    "Удръжка доброволно осиг. (лична)", "Удръжка карта (лична част)",
    "НЕТО преди удръжки", "НЕТО за изплащане", "Изплатено", "Разлика",
    "Вноски работодател ДОО+ТЗПБ", "ДЗПО-УПФ работодател", "ЗО работодател",
    "ЗО при болничен/майчинство", "Вноски работодател общо",
    "Карта (за сметка на работодателя)", "Доброволно здравно осигуряване (премия)",
    "Общ разход за труд",
]
COL = {name: i + 1 for i, name in enumerate(COLUMNS)}     # name -> 1-based index

ACCRUALS = ["Основна за отработеното", "Клас сума", "Бонус",
            "Платен отпуск", "Обезщетение чл. 224", "Болнични (работодател)"]
DAY_COLUMNS = ["Отраб. дни", "Дни платен отпуск", "Дни болничен", "Дни майчинство"]
SUMMED_COLUMNS = [c for c in COLUMNS if c not in ("№", "Име", "Отдел", "Клас %")]

# The five employee contribution columns, paired with their rate key.
EMPLOYEE_COLUMNS = (("ДОО пенсии", "pension"), ("ДОО ОЗМ", "sickness"),
                    ("ДОО безработица", "unemployment"), ("ЗО лична", "health"),
                    ("ДЗПО-УПФ лична", "upf"))


# ---------------------------------------------------------- the clean payroll

def clean_row(inp, regime, tzpb, policy, norm_days):
    """Compute one correct row from its inputs.

    inp: monthly_salary, seniority_pct, days_*, bonus, compensation_224,
         card_employer, card_employee, premium, personal_contribution
    policy: in_kind_in_bases / excess_in_bases (bool) - see the module docstring
    Returns dict: column name -> value.
    """
    ms = inp["monthly_salary"]
    pct = inp["seniority_pct"]
    wd, pl = inp["days_worked"], inp["days_leave"]
    sd, md = inp["days_sick"], inp["days_maternity"]
    daily = ms / norm_days
    uplift = 1 + pct / 100.0

    base = r2(daily * wd)
    seniority = r2(base * pct / 100.0)
    leave = r2(daily * uplift * pl)
    sick_days_employer = min(sd, SICK_DAYS_EMPLOYER)
    sick_pay = r2(daily * uplift * sick_days_employer * SICK_RATE)
    bonus = r2(inp["bonus"])
    comp_224 = r2(inp["compensation_224"])

    gross = r2(base + seniority + bonus + leave + comp_224 + sick_pay)

    # --- insurable income --------------------------------------------------
    # The чл. 40, ал. 5 КСО payment is not insurable income (НЕВДПОВ); neither is
    # the чл. 224 КТ compensation. Both are taxable, however.
    in_kind = r2(inp["card_employer"]) if inp["card_employer"] else 0.0
    premium = r2(inp["premium"]) if inp["premium"] else 0.0
    excess = r2(max(0.0, premium - SOCIAL_EXPENSE_THRESHOLD)) if premium else 0.0

    work_base = r2(base + seniority + bonus + leave)
    if work_base <= 0:
        # A person with no accruals for work this month (a full month of
        # maternity leave): there is nothing for the benefits to attach to,
        # because there is no income from labour activity (чл. 6, ал. 2 КСО).
        additions = 0.0
    else:
        additions = ((in_kind if policy["in_kind_in_bases"] else 0.0)
                     + (excess if policy["excess_in_bases"] else 0.0))
    insurable = r2(min(regime["max_insurable"], r2(work_base + additions)))

    contributions = {k: r2(insurable * p / 100.0) for k, p in EMPLOYEE.items()}
    employee_total = r2(sum(contributions.values()))

    # --- taxable base ------------------------------------------------------
    # Whatever enters the insurable income as income in kind or as excess also
    # enters the taxable base. Compensations and sick pay are taxable.
    taxable_before = r2(gross + additions - employee_total)
    limit = r2(taxable_before * RELIEF_LIMIT)
    relief = r2(min(inp["personal_contribution"], limit)) \
        if inp["personal_contribution"] else 0.0
    taxable = r2(taxable_before - relief)
    tax = r2(taxable * TAX_RATE)

    net_before = r2(gross - employee_total - tax)
    net = r2(net_before - inp["personal_contribution"] - inp["card_employee"])

    # --- employer contributions -------------------------------------------
    er_social = r2(insurable * (EMPLOYER_SOCIAL + tzpb) / 100.0)
    er_upf = r2(insurable * EMPLOYER_UPF / 100.0)
    er_health = r2(insurable * EMPLOYER_HEALTH / 100.0)
    er_health_sick = r2(regime["min_insurable_self"] * HEALTH_ON_INCAPACITY / 100.0
                        * (sd + md) / norm_days) if (sd + md) else 0.0
    er_total = r2(er_social + er_upf + er_health + er_health_sick)

    cost = r2(gross + er_total + in_kind + premium)

    return {
        "Отраб. дни": wd, "Дни платен отпуск": pl,
        "Дни болничен": sd, "Дни майчинство": md,
        "Основна за отработеното": base, "Клас %": pct, "Клас сума": seniority,
        "Бонус": bonus, "Платен отпуск": leave, "Обезщетение чл. 224": comp_224,
        "Болнични (работодател)": sick_pay, "БРУТО": gross,
        "ДОО пенсии": contributions["pension"], "ДОО ОЗМ": contributions["sickness"],
        "ДОО безработица": contributions["unemployment"],
        "ЗО лична": contributions["health"], "ДЗПО-УПФ лична": contributions["upf"],
        "Лични вноски общо": employee_total,
        "Осигурителен доход": insurable, "Данъчна основа": taxable, "ДДФЛ": tax,
        "Удръжка доброволно осиг. (лична)": r2(inp["personal_contribution"]),
        "Удръжка карта (лична част)": r2(inp["card_employee"]),
        "НЕТО преди удръжки": net_before, "НЕТО за изплащане": net,
        "Изплатено": net, "Разлика": 0.0,
        "Вноски работодател ДОО+ТЗПБ": er_social, "ДЗПО-УПФ работодател": er_upf,
        "ЗО работодател": er_health, "ЗО при болничен/майчинство": er_health_sick,
        "Вноски работодател общо": er_total,
        "Карта (за сметка на работодателя)": in_kind,
        "Доброволно здравно осигуряване (премия)": premium,
        "Общ разход за труд": cost,
    }


# ------------------------------------------------------------------ scenarios
# id -> (check in proverki.md, one-line description)
SCENARIOS = {
    "K1_sum_omits_column":        ("K1", "gross does not include every accrual column"),
    "K2_amount_in_day_column":    ("K2", "an amount typed into a column meant for days"),
    "K3_stale_contributions":     ("K3", "contributions left over from another period"),
    "K4_control_column_blind":    ("K4", "control column reads zero while money is missing"),
    "K5_total_not_sum":           ("K5", "total row differs from the sum of the cells"),
    "K6_unrounded_accrual":       ("K6", "accrual with more than two decimals"),
    "K7_cost_from_net":           ("K7", "cost of labour computed from net after deductions"),
    "F9_sick_pay_in_insurable":   ("F9", "sick pay for the first days inside the insurable income"),
    "F9_sick_pay_out_of_taxable": ("F9", "sick pay for the first days removed from the taxable base"),
    "F9_missing_health_on_sick":  ("F9", "no health contribution for days of incapacity"),
    "F10_in_kind_asymmetry":      ("F10", "income in kind in one base but not the other"),
    "F10_excess_asymmetry":       ("F10", "threshold excess in one base but not the other"),
    "F7_relief_over_limit":       ("F7", "tax relief above the monthly percentage limit"),
    "F5_tzpb_below_due":          ("F5", "employer contributions carry an accident rate below the applicable one"),
    "B4_cap_from_wrong_period":   ("B4", "maximum insurable income taken from the other half-year"),
    "C2_seniority_on_gross":      ("C2", "length-of-service supplement computed on a wider base"),
    "E3_leave_without_seniority": ("E3", "paid leave computed without the supplement"),
    "I5_days_do_not_reconcile":   ("I5", "day counts do not add up to the month's norm"),
}
