# -*- coding: utf-8 -*-
"""Generator of test payrolls with random data and deliberately injected defects.

    python test/generate_wide.py --seed 7

Writes `test/tmp/wide_<seed>.xlsx` and a manifest `..._manifest.json` listing
exactly what was broken. Everything is invented and derived from the seed:
names, company, salaries, days, benefit prices, month, accident-insurance rate.
Not a single figure comes from a real payroll.

Defects are injected as a mutation on a correctly computed row, with the
dependent cells recomputed the way the erring file would recompute them. The aim
is for each defect to produce one determinate set of findings - otherwise the
suite cannot tell a missed finding from a cascade.

Order of injection: file-level defects first (accident rate, applied cap),
because they touch every row, and only then the per-row ones. The reverse order
would wipe a mutation already made.

Separability. The check for the composition of the insurable income and the
taxable base works by solving which subset of the elements explains the stated
figure. The generator therefore guarantees that the subset sums of
{income in kind, threshold excess, sick pay, compensation} differ by enough -
otherwise the problem has more than one solution and the finding cannot be
located. That is not a concession by the suite: in a real file the same ambiguity
makes the conclusion unsafe, and the skill is required to say so rather than
guess.

Person and company names are Bulgarian because they are data. The rest is English.
"""
import argparse
import itertools
import json
import os
import random

import openpyxl
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

import trz_model as M
from trz_model import r2

HERE = os.path.dirname(os.path.abspath(__file__))
TMP = os.path.join(HERE, "tmp")
SEPARATION = 0.50      # minimum gap between two subset sums

# --- invented names. Deliberately unlike any real roster. ---
FIRST_M = ["Борислав", "Дарин", "Захари", "Ивайло", "Камен", "Лъчезар", "Никифор",
           "Орлин", "Тихомир", "Юлиан", "Явор", "Емил"]
FIRST_F = ["Ана", "Ваня", "Галина", "Емилия", "Жанета", "Красимира", "Магдалена",
           "Пенка", "Симона", "Христина", "Здравка", "Теодора"]
LAST = ["Аврамов", "Бакалов", "Влахов", "Гошев", "Даскалов", "Еленков", "Жеков",
        "Зидаров", "Кожухаров", "Лозанов", "Мутафчиев", "Ненов", "Орешков",
        "Пенчев", "Радулов", "Сивков", "Тошков", "Узунов", "Фандъков", "Хаджиев",
        "Цветков", "Чакъров", "Шивачев", "Янев"]
DEPARTMENTS = ["Разработка", "Внедряване", "Поддръжка", "Операции", "Администрация"]
COMPANIES = ["Тестова Дигитал", "Пробна Софтуер", "Примерна Интеграции",
             "Демонстрационна Системи", "Условна Технолоджи"]
MONTHS_BG = {6: "юни", 7: "юли", 8: "август", 9: "септември", 10: "октомври",
             11: "ноември"}


def _name(rnd, used):
    while True:
        if rnd.random() < 0.45:
            name = f"{rnd.choice(FIRST_F)} {rnd.choice(LAST)}а"
        else:
            name = f"{rnd.choice(FIRST_M)} {rnd.choice(LAST)}"
        if name not in used:
            used.add(name)
            return name


def _separable(values):
    """Do all subset sums differ by more than SEPARATION?"""
    vs = [v for v in values if v]
    sums = []
    for k in range(len(vs) + 1):
        for combo in itertools.combinations(vs, k):
            sums.append(r2(sum(combo)))
    sums.sort()
    return all(b - a > SEPARATION for a, b in zip(sums, sums[1:]))


def _usable_rows(people, cap_applicable, cap_effective):
    """How many rows let the file's practice be inferred, per element.

    A row is usable when it has accruals for work and does not sit at a cap -
    at the cap the same figure follows from many combinations and nothing is
    visible. The count matters: below three rows the practice cannot be
    established, and a defect that depends on it cannot be located - neither by
    the suite nor by a live auditor.
    """
    count = {"in_kind": 0, "excess": 0}
    for p in people:
        row = p["row"]
        work_base = r2(row["Основна за отработеното"] + row["Клас сума"]
                       + row["Бонус"] + row["Платен отпуск"])
        if work_base <= 0:
            continue
        if any(abs(row["Осигурителен доход"] - c) <= M.TOL
               for c in (cap_applicable, cap_effective)):
            continue
        if row["Карта (за сметка на работодателя)"]:
            count["in_kind"] += 1
        premium = row["Доброволно здравно осигуряване (премия)"]
        if premium and r2(premium - M.SOCIAL_EXPENSE_THRESHOLD) > 0:
            count["excess"] += 1
    return count


def _carries(row, element):
    if element == "in_kind":
        return row["Карта (за сметка на работодателя)"] > 0
    premium = row["Доброволно здравно осигуряване (премия)"]
    return bool(premium) and r2(premium - M.SOCIAL_EXPENSE_THRESHOLD) > 0


def _elements(row):
    premium = row["Доброволно здравно осигуряване (премия)"]
    return [row["Карта (за сметка на работодателя)"],
            r2(max(0.0, premium - M.SOCIAL_EXPENSE_THRESHOLD)) if premium else 0.0,
            row["Болнични (работодател)"],
            row["Обезщетение чл. 224"]]


def random_inputs(rnd, norm, regime):
    """One random but plausible person."""
    kind = rnd.random()
    if kind < 0.15:
        salary = r2(rnd.uniform(regime["min_wage"], regime["min_wage"] * 1.4))
    elif kind < 0.7:
        salary = r2(rnd.uniform(1200, 2600))
    else:
        salary = r2(rnd.uniform(2600, 9000))

    pct = rnd.choice([0, 0, 0.6, 1.2, 1.8, 2.4, 3.0, 4.2, 4.8, 6.0, 7.2, 9.0])
    sick = rnd.choice([0] * 8 + [2, 3, 5])
    leave = 0 if sick else rnd.choice([0, 0, 1, 2, 3, 5, 8, 11])
    leave = min(leave, norm - sick)
    worked = norm - leave - sick

    has_card = rnd.random() < 0.6
    has_premium = rnd.random() < 0.8
    return dict(
        monthly_salary=salary, seniority_pct=pct,
        days_worked=worked, days_leave=leave, days_sick=sick, days_maternity=0,
        bonus=r2(rnd.uniform(50, 400)) if rnd.random() < 0.18 else 0.0,
        compensation_224=0.0,
        card_employer=r2(rnd.uniform(38, 72)) if has_card else 0.0,
        card_employee=r2(rnd.uniform(3, 12)) if has_card else 0.0,
        premium=r2(rnd.uniform(32.9, 44.5)) if has_premium else 0.0,
        personal_contribution=r2(rnd.uniform(20, 120)) if rnd.random() < 0.15 else 0.0,
    )


def make_person(rnd, norm, regime, tzpb, policy):
    """Return (inputs, clean row) with separable elements guaranteed."""
    for _ in range(30):
        inp = random_inputs(rnd, norm, regime)
        row = M.clean_row(inp, regime, tzpb, policy, norm)
        if _separable(_elements(row)):
            row["_norm"] = norm
            return inp, row
        # nudge the benefits rather than re-rolling the whole person
        for _ in range(20):
            inp["card_employer"] = r2(rnd.uniform(38, 72)) if inp["card_employer"] else 0.0
            inp["premium"] = r2(rnd.uniform(32.9, 44.5)) if inp["premium"] else 0.0
            row = M.clean_row(inp, regime, tzpb, policy, norm)
            if _separable(_elements(row)):
                row["_norm"] = norm
                return inp, row
    inp["card_employer"] = inp["card_employee"] = 0.0
    inp["premium"] = 0.0
    row = M.clean_row(inp, regime, tzpb, policy, norm)
    row["_norm"] = norm
    return inp, row


# =====================================================================
#                             mutations
# Each returns (new row, set of expected ids) or None if the row does not
# qualify for this defect.
# =====================================================================

def _recompute_downstream(row, inp, regime, tzpb, policy, *,
                          insurable=None, taxable=None):
    """Recompute contributions, tax, net and cost after the gross or the bases
    change - the way a file whose downstream columns are formulas would."""
    gross = row["БРУТО"]
    in_kind = row["Карта (за сметка на работодателя)"]
    premium = row["Доброволно здравно осигуряване (премия)"]
    excess = r2(max(0.0, premium - M.SOCIAL_EXPENSE_THRESHOLD)) if premium else 0.0
    work_base = r2(row["Основна за отработеното"] + row["Клас сума"]
                   + row["Бонус"] + row["Платен отпуск"])
    sick_pay = row["Болнични (работодател)"]
    add_insurable, add_taxable = M.additions_for(policy, in_kind, excess, work_base)

    if insurable is None:
        insurable = r2(min(regime["max_insurable"],
                           r2(work_base + sick_pay + add_insurable)))
    row["Осигурителен доход"] = insurable

    for column, key in M.EMPLOYEE_COLUMNS:
        row[column] = r2(insurable * M.EMPLOYEE[key] / 100.0)
    employee_total = r2(sum(row[c] for c, _ in M.EMPLOYEE_COLUMNS))
    row["Лични вноски общо"] = employee_total

    if taxable is None:
        # the sick pay is inside the gross and outside the taxable base
        before = r2(gross + add_taxable - sick_pay - employee_total)
        limit = r2(before * M.RELIEF_LIMIT)
        deduction = row["Удръжка доброволно осиг. (лична)"]
        relief = r2(min(deduction, limit)) if deduction else 0.0
        taxable = r2(before - relief)
    row["Данъчна основа"] = taxable
    row["ДДФЛ"] = r2(taxable * M.TAX_RATE)

    row["НЕТО преди удръжки"] = r2(gross - employee_total - row["ДДФЛ"])
    row["НЕТО за изплащане"] = r2(row["НЕТО преди удръжки"]
                                  - row["Удръжка доброволно осиг. (лична)"]
                                  - row["Удръжка карта (лична част)"])
    row["Изплатено"] = row["НЕТО за изплащане"]
    row["Разлика"] = 0.0

    row["Вноски работодател ДОО+ТЗПБ"] = r2(insurable * (M.EMPLOYER_SOCIAL + tzpb) / 100.0)
    row["ДЗПО-УПФ работодател"] = r2(insurable * M.EMPLOYER_UPF / 100.0)
    row["ЗО работодател"] = r2(insurable * M.EMPLOYER_HEALTH / 100.0)
    row["Вноски работодател общо"] = r2(row["Вноски работодател ДОО+ТЗПБ"]
                                       + row["ДЗПО-УПФ работодател"]
                                       + row["ЗО работодател"]
                                       + row["ЗО при болничен/майчинство"])
    row["Общ разход за труд"] = r2(gross + row["Вноски работодател общо"]
                                   + in_kind + premium)
    return row


def m_sum_omits_column(row, inp, regime, tzpb, policy, rnd):
    """Gross leaves out an accrual column - here the чл. 224 compensation."""
    row = dict(row)
    for _ in range(40):
        amount = r2(rnd.uniform(120, 900))
        trial = dict(row, **{"Обезщетение чл. 224": amount})
        if _separable(_elements(trial)):
            row = trial
            break
    else:
        return None
    row["БРУТО"] = r2(row["Основна за отработеното"] + row["Клас сума"] + row["Бонус"]
                      + row["Платен отпуск"] + row["Болнични (работодател)"])
    return _recompute_downstream(row, inp, regime, tzpb, policy), \
        {"K1_sum_omits_column"}


def m_amount_in_day_column(row, inp, regime, tzpb, policy, rnd):
    """The sick-pay amount typed into the column meant for sick days."""
    if not inp["days_sick"] or not row["Болнични (работодател)"]:
        return None
    row = dict(row)
    row["Дни болничен"] = row["Болнични (работодател)"]
    return row, {"K2_amount_in_day_column", "I5_days_do_not_reconcile"}


def m_stale_contributions(row, inp, regime, tzpb, policy, rnd):
    """Contributions are hardcoded values from an earlier period."""
    row = dict(row)
    stale = r2(row["Осигурителен доход"] * rnd.uniform(0.86, 0.95))
    if row["Осигурителен доход"] - stale < 5:
        return None
    for column, key in M.EMPLOYEE_COLUMNS:
        row[column] = r2(stale * M.EMPLOYEE[key] / 100.0)
    employee_total = r2(sum(row[c] for c, _ in M.EMPLOYEE_COLUMNS))
    row["Лични вноски общо"] = employee_total

    in_kind = row["Карта (за сметка на работодателя)"]
    premium = row["Доброволно здравно осигуряване (премия)"]
    excess = r2(max(0.0, premium - M.SOCIAL_EXPENSE_THRESHOLD)) if premium else 0.0
    work_base = r2(row["Основна за отработеното"] + row["Клас сума"] + row["Бонус"]
                   + row["Платен отпуск"])
    _, add_taxable = M.additions_for(policy, in_kind, excess, work_base)
    before = r2(row["БРУТО"] + add_taxable - row["Болнични (работодател)"]
                - employee_total)
    limit = r2(before * M.RELIEF_LIMIT)
    deduction = row["Удръжка доброволно осиг. (лична)"]
    relief = r2(min(deduction, limit)) if deduction else 0.0
    row["Данъчна основа"] = r2(before - relief)
    row["ДДФЛ"] = r2(row["Данъчна основа"] * M.TAX_RATE)
    row["НЕТО преди удръжки"] = r2(row["БРУТО"] - employee_total - row["ДДФЛ"])
    row["НЕТО за изплащане"] = r2(row["НЕТО преди удръжки"]
                                  - row["Удръжка доброволно осиг. (лична)"]
                                  - row["Удръжка карта (лична част)"])
    row["Изплатено"] = row["НЕТО за изплащане"]
    return row, {"K3_stale_contributions"}


def m_control_column_blind(row, inp, regime, tzpb, policy, rnd):
    """Paid is below net while the control column still reads zero."""
    row = dict(row)
    row["Изплатено"] = r2(row["НЕТО за изплащане"] - rnd.choice([0.05, 0.13, 0.40, 1.00]))
    row["Разлика"] = 0.0
    return row, {"K4_control_column_blind"}


def m_unrounded_accrual(row, inp, regime, tzpb, policy, rnd):
    """The seniority supplement is unrounded and flows into the gross."""
    if not inp["seniority_pct"]:
        return None
    raw = row["Основна за отработеното"] * inp["seniority_pct"] / 100.0
    if abs(raw - r2(raw)) < 0.002:
        return None                     # no visible tail - nothing to detect
    row = dict(row)
    row["Клас сума"] = raw
    row["БРУТО"] = (row["Основна за отработеното"] + row["Клас сума"] + row["Бонус"]
                    + row["Платен отпуск"] + row["Обезщетение чл. 224"]
                    + row["Болнични (работодател)"])
    row = _recompute_downstream(row, inp, regime, tzpb, policy)
    row["Изплатено"] = r2(row["НЕТО за изплащане"])
    row["Разлика"] = r2(row["НЕТО за изплащане"] - row["Изплатено"])
    return row, {"K6_unrounded_accrual"}


def m_cost_from_net(row, inp, regime, tzpb, policy, rnd):
    """The cost of labour is computed from net after deductions."""
    deductions = r2(row["Удръжка доброволно осиг. (лична)"]
                    + row["Удръжка карта (лична част)"])
    if deductions < 1.0:
        return None
    row = dict(row)
    row["Общ разход за труд"] = r2(row["Общ разход за труд"] - deductions)
    return row, {"K7_cost_from_net"}


def m_sick_pay_out_of_insurable(row, inp, regime, tzpb, policy, rnd):
    """The first-days sick pay is left out of the insurable income.

    чл. 3, ал. 1 НЕВДПОВ puts it in, so leaving it out understates the
    contributions and т. 21 of Декларация обр. 1 by 70% of the daily base per day.
    """
    if not row["Болнични (работодател)"]:
        return None
    row = dict(row)
    in_kind = row["Карта (за сметка на работодателя)"]
    premium = row["Доброволно здравно осигуряване (премия)"]
    excess = r2(max(0.0, premium - M.SOCIAL_EXPENSE_THRESHOLD)) if premium else 0.0
    work_base = r2(row["Основна за отработеното"] + row["Клас сума"] + row["Бонус"]
                   + row["Платен отпуск"])
    add_insurable, _ = M.additions_for(policy, in_kind, excess, work_base)
    if r2(work_base + add_insurable + row["Болнични (работодател)"]) \
            > regime["max_insurable"] - 1.0:
        # the correct figure touches the cap: the composition is no longer
        # recoverable and the finding cannot be located, by the suite or by a
        # live auditor
        return None
    insurable = r2(work_base + add_insurable)
    if abs(insurable - row["Осигурителен доход"]) < 1.0:
        return None                      # too small to tell from rounding
    return _recompute_downstream(row, inp, regime, tzpb, policy, insurable=insurable), \
        {"F9_sick_pay_out_of_insurable"}


def m_sick_pay_in_taxable(row, inp, regime, tzpb, policy, rnd):
    """The first-days sick pay is left inside the taxable base.

    чл. 24, ал. 2, т. 14 ЗДДФЛ keeps it out, so leaving it in overtaxes the person
    by 10% of the sick pay.
    """
    if not row["Болнични (работодател)"]:
        return None
    row = dict(row)
    in_kind = row["Карта (за сметка на работодателя)"]
    premium = row["Доброволно здравно осигуряване (премия)"]
    excess = r2(max(0.0, premium - M.SOCIAL_EXPENSE_THRESHOLD)) if premium else 0.0
    work_base = r2(row["Основна за отработеното"] + row["Клас сума"] + row["Бонус"]
                   + row["Платен отпуск"])
    _, add_taxable = M.additions_for(policy, in_kind, excess, work_base)
    # the correct base subtracts the sick pay here; this one does not
    before = r2(row["БРУТО"] + add_taxable - row["Лични вноски общо"])
    limit = r2(before * M.RELIEF_LIMIT)
    deduction = row["Удръжка доброволно осиг. (лична)"]
    relief = r2(min(deduction, limit)) if deduction else 0.0
    return _recompute_downstream(row, inp, regime, tzpb, policy,
                                 insurable=row["Осигурителен доход"],
                                 taxable=r2(before - relief)), \
        {"F9_sick_pay_in_taxable"}


def m_sick_pay_from_agreed(row, inp, regime, tzpb, policy, rnd):
    """Sick pay taken from the agreed daily rate when the month's gross is higher.

    чл. 40, ал. 5 КСО owes 70% of the month's average daily gross and treats the agreed
    rate only as a floor. A payroll that keeps one daily rate per person computes the
    floor and stops, which shorts everyone whose month carried a bonus. The defect is
    invisible without the contract and the month's other accruals side by side, which
    is why it survives in real files.
    """
    if not inp["days_sick"] or not row["Болнични (работодател)"]:
        return None
    if not inp["bonus"]:
        return None                     # without a bonus the two measures coincide
    employer_days = min(inp["days_sick"], M.SICK_DAYS_EMPLOYER)
    agreed = inp["monthly_salary"] * (1 + inp["seniority_pct"] / 100.0) / row["_norm"]
    short = r2(agreed * employer_days * M.SICK_RATE)
    if abs(short - row["Болнични (работодател)"]) < 0.10:
        return None                     # too small to tell from rounding
    row = dict(row)
    row["Болнични (работодател)"] = short
    row["БРУТО"] = r2(row["Основна за отработеното"] + row["Клас сума"] + row["Бонус"]
                      + row["Платен отпуск"] + row["Обезщетение чл. 224"] + short)
    return _recompute_downstream(row, inp, regime, tzpb, policy), \
        {"F9_sick_pay_amount"}


def m_missing_health_on_sick(row, inp, regime, tzpb, policy, rnd):
    """The health contribution for days of incapacity is missing."""
    if not row["ЗО при болничен/майчинство"]:
        return None
    row = dict(row)
    row["ЗО при болничен/майчинство"] = 0.0
    row["Вноски работодател общо"] = r2(row["Вноски работодател ДОО+ТЗПБ"]
                                       + row["ДЗПО-УПФ работодател"]
                                       + row["ЗО работодател"])
    row["Общ разход за труд"] = r2(row["БРУТО"] + row["Вноски работодател общо"]
                                   + row["Карта (за сметка на работодателя)"]
                                   + row["Доброволно здравно осигуряване (премия)"])
    return row, {"F9_missing_health_on_sick"}


def _asymmetry(row, inp, regime, tzpb, policy, element, ident, usable=99):
    """Make the element visible in only one of the two bases.

    `usable` is how many rows let the practice be inferred. Below four the
    practice stops being establishable once this row is spoiled, and a live
    auditor would ask rather than conclude - so the defect is not injected.
    """
    if usable < 4:
        return None
    in_kind = row["Карта (за сметка на работодателя)"]
    premium = row["Доброволно здравно осигуряване (премия)"]
    excess = r2(max(0.0, premium - M.SOCIAL_EXPENSE_THRESHOLD)) if premium else 0.0
    value = in_kind if element == "in_kind" else excess
    if value < 1.0:
        return None
    work_base = r2(row["Основна за отработеното"] + row["Клас сума"] + row["Бонус"]
                   + row["Платен отпуск"])
    if work_base <= 0:
        return None
    sick_pay = row["Болнични (работодател)"]
    # if the cap is reached, the composition of the insurable income is not
    # recognisable and the defect cannot be located. The sick pay counts towards
    # the cap too - without it a row that is in fact unusable looks usable.
    if r2(work_base + sick_pay + in_kind + excess) > regime["max_insurable"] - 1.0:
        return None
    # The defect is a departure from the file's own practice in exactly ONE base -
    # not an asymmetry between the two bases, which under reading В is correct.
    in_insurable = policy["in_kind_in_bases"] if element == "in_kind" \
        else policy["excess_in_insurable"]
    add_insurable, add_taxable = M.additions_for(policy, in_kind, excess, work_base)
    row = dict(row)
    if in_insurable:
        # taken out of the insurable income only; the taxable base stays as the file's
        # practice has it
        insurable = r2(min(regime["max_insurable"],
                           r2(work_base + sick_pay + add_insurable - value)))
        row = _recompute_downstream(row, inp, regime, tzpb, policy, insurable=insurable)
    else:
        # the element is in neither base for this file, so it is added to the taxable
        # base only. The relief is limited against that same base, so that the file is
        # not inconsistent in a third respect as well - the suite measures one defect
        # at a time.
        insurable = row["Осигурителен доход"]
        employee_total = r2(sum(r2(insurable * M.EMPLOYEE[k] / 100.0) for k in M.EMPLOYEE))
        before = r2(row["БРУТО"] + add_taxable + value - sick_pay - employee_total)
        limit = r2(before * M.RELIEF_LIMIT)
        deduction = row["Удръжка доброволно осиг. (лична)"]
        relief = r2(min(deduction, limit)) if deduction else 0.0
        row = _recompute_downstream(row, inp, regime, tzpb, policy,
                                    insurable=insurable, taxable=r2(before - relief))
    return row, {ident}


def m_in_kind_asymmetry(row, inp, regime, tzpb, policy, rnd, usable=99):
    return _asymmetry(row, inp, regime, tzpb, policy, "in_kind",
                      "F10_in_kind_asymmetry", usable)


def m_excess_asymmetry(row, inp, regime, tzpb, policy, rnd, usable=99):
    return _asymmetry(row, inp, regime, tzpb, policy, "excess",
                      "F10_excess_asymmetry", usable)


def m_relief_over_limit(row, inp, regime, tzpb, policy, rnd):
    """The tax relief is applied above the percentage limit."""
    row = dict(row)
    in_kind = row["Карта (за сметка на работодателя)"]
    premium = row["Доброволно здравно осигуряване (премия)"]
    excess = r2(max(0.0, premium - M.SOCIAL_EXPENSE_THRESHOLD)) if premium else 0.0
    work_base = r2(row["Основна за отработеното"] + row["Клас сума"] + row["Бонус"]
                   + row["Платен отпуск"])
    if work_base <= 0:
        return None
    _, add_taxable = M.additions_for(policy, in_kind, excess, work_base)
    before = r2(row["БРУТО"] + add_taxable - row["Болнични (работодател)"]
                - row["Лични вноски общо"])
    contribution = r2(before * M.RELIEF_LIMIT + rnd.uniform(30, 150))
    row["Удръжка доброволно осиг. (лична)"] = contribution
    row["Данъчна основа"] = r2(before - contribution)
    row["ДДФЛ"] = r2(row["Данъчна основа"] * M.TAX_RATE)
    row["НЕТО преди удръжки"] = r2(row["БРУТО"] - row["Лични вноски общо"] - row["ДДФЛ"])
    row["НЕТО за изплащане"] = r2(row["НЕТО преди удръжки"] - contribution
                                  - row["Удръжка карта (лична част)"])
    row["Изплатено"] = row["НЕТО за изплащане"]
    return row, {"F7_relief_over_limit"}


def m_relief_not_applied(row, inp, regime, tzpb, policy, rnd):
    """A personal contribution is withheld, but it reduces no taxable base.

    чл. 19, ал. 2 във вр. с чл. 42, ал. 3 ЗДДФЛ reduces the monthly base by personal
    premiums the employer withholds. Withholding them and then taxing as though they
    had not been withheld overtaxes the person every month.

    This one is the opposite of most defects in the suite: it leaves the file perfectly
    self-consistent. The base is exactly „облагаем доход − лични вноски“, every row is
    treated the same way and no control column moves. Nothing contradicts anything -
    which is why it survives in real payrolls and why the checker has to know the
    relief was due rather than infer it from an inconsistency.
    """
    deduction = row["Удръжка доброволно осиг. (лична)"]
    if not deduction:
        return None
    row = dict(row)
    in_kind = row["Карта (за сметка на работодателя)"]
    premium = row["Доброволно здравно осигуряване (премия)"]
    excess = r2(max(0.0, premium - M.SOCIAL_EXPENSE_THRESHOLD)) if premium else 0.0
    work_base = r2(row["Основна за отработеното"] + row["Клас сума"] + row["Бонус"]
                   + row["Платен отпуск"])
    if work_base <= 0:
        return None
    _, add_taxable = M.additions_for(policy, in_kind, excess, work_base)
    before = r2(row["БРУТО"] + add_taxable - row["Болнични (работодател)"]
                - row["Лични вноски общо"])
    applied = r2(min(deduction, r2(before * M.RELIEF_LIMIT)))
    if applied < 1.0:
        return None                      # too small to tell from rounding
    return _recompute_downstream(row, inp, regime, tzpb, policy,
                                 insurable=row["Осигурителен доход"],
                                 taxable=before), \
        {"F7_relief_not_applied"}


def m_seniority_on_gross(row, inp, regime, tzpb, policy, rnd):
    """The seniority supplement is computed on a wider base than the salary."""
    pct = inp["seniority_pct"]
    if not pct:
        return None
    delta = r2((row["Платен отпуск"] + row["Бонус"]) * pct / 100.0)
    if delta < 0.10:                     # without leave and bonus there is no gap
        return None
    row = dict(row)
    wider = r2(row["Основна за отработеното"] + row["Платен отпуск"] + row["Бонус"])
    row["Клас сума"] = r2(wider * pct / 100.0)
    row["БРУТО"] = r2(row["Основна за отработеното"] + row["Клас сума"] + row["Бонус"]
                      + row["Платен отпуск"] + row["Обезщетение чл. 224"]
                      + row["Болнични (работодател)"])
    return _recompute_downstream(row, inp, regime, tzpb, policy), \
        {"C2_seniority_on_gross"}


def m_leave_without_seniority(row, inp, regime, tzpb, policy, rnd):
    """Paid leave is computed without the seniority uplift."""
    if not inp["seniority_pct"] or not inp["days_leave"]:
        return None
    daily = inp["monthly_salary"] / row["_norm"]
    without = r2(daily * inp["days_leave"])
    if abs(without - row["Платен отпуск"]) < 0.10:
        return None
    row = dict(row)
    row["Платен отпуск"] = without
    row["БРУТО"] = r2(row["Основна за отработеното"] + row["Клас сума"] + row["Бонус"]
                      + row["Платен отпуск"] + row["Обезщетение чл. 224"]
                      + row["Болнични (работодател)"])
    return _recompute_downstream(row, inp, regime, tzpb, policy), \
        {"E3_leave_without_seniority"}


def m_days_do_not_reconcile(row, inp, regime, tzpb, policy, rnd):
    """The sick days are not recorded although the amount is accrued."""
    if not inp["days_sick"]:
        return None
    row = dict(row)
    row["Дни болничен"] = 0
    return row, {"I5_days_do_not_reconcile"}


ROW_MUTATIONS = [
    ("K1_sum_omits_column", m_sum_omits_column),
    ("K2_amount_in_day_column", m_amount_in_day_column),
    ("K3_stale_contributions", m_stale_contributions),
    ("K4_control_column_blind", m_control_column_blind),
    ("K6_unrounded_accrual", m_unrounded_accrual),
    ("K7_cost_from_net", m_cost_from_net),
    ("F9_sick_pay_out_of_insurable", m_sick_pay_out_of_insurable),
    ("F9_sick_pay_in_taxable", m_sick_pay_in_taxable),
    ("F9_sick_pay_amount", m_sick_pay_from_agreed),
    ("F9_missing_health_on_sick", m_missing_health_on_sick),
    ("F10_in_kind_asymmetry", m_in_kind_asymmetry),
    ("F10_excess_asymmetry", m_excess_asymmetry),
    ("F7_relief_over_limit", m_relief_over_limit),
    ("F7_relief_not_applied", m_relief_not_applied),
    ("C2_seniority_on_gross", m_seniority_on_gross),
    ("E3_leave_without_seniority", m_leave_without_seniority),
    ("I5_days_do_not_reconcile", m_days_do_not_reconcile),
]

# Defects whose localisation goes through the file's practice for the benefits.
NEEDS_PRACTICE = ("F9_sick_pay_out_of_insurable", "F10_in_kind_asymmetry",
                  "F10_excess_asymmetry", "F9_sick_pay_in_taxable",
                  "F7_relief_over_limit", "F7_relief_not_applied")
# Of those, only these spoil the sample the practice is inferred from.
SPOILS_SAMPLE = ("F9_sick_pay_out_of_insurable", "F10_in_kind_asymmetry",
                 "F10_excess_asymmetry")


# =====================================================================


def generate(seed, month=None, year=2026):
    rnd = random.Random(seed)
    month = month or rnd.choice([6, 7, 8, 9, 10, 11])
    norm = M.working_days(year, month)
    # A year the reference file has no thresholds for is built the way a real payroll is
    # built every January: by copying last year's file forward, so it carries the last
    # published regime. Whether those thresholds still apply is exactly what the skill
    # cannot know, and the whole point of the fixture is that it must not guess.
    rates_known = year in M.RATES_KNOWN_YEARS
    regime_id = M.regime_for(year, month) if rates_known else "H2"
    regime = M.REGIMES[regime_id]
    tzpb = rnd.choice([0.4, 0.5, 0.7, 1.1])
    # One of the three readings of the excess, applied to the whole file. В is the
    # asymmetric one and must produce no finding when it is applied consistently.
    reading = rnd.choice(list(M.EXCESS_READINGS))
    policy = dict(in_kind_in_bases=rnd.random() < 0.5,
                  excess_in_insurable=M.EXCESS_READINGS[reading]["insurable"],
                  excess_in_taxable=M.EXCESS_READINGS[reading]["taxable"],
                  excess_reading=reading)
    company = rnd.choice(COMPANIES)
    n = rnd.randint(9, 15)

    # --- file-level defects are decided BEFORE the rows ---------------------
    file_defects = []
    tzpb_effective = tzpb
    if rnd.random() < 0.45:
        candidate = round(tzpb - rnd.choice([0.1, 0.2, 0.3]), 2)
        if candidate >= 0.1:
            tzpb_effective = candidate
            file_defects.append("F5_tzpb_below_due")

    cap_effective = regime["max_insurable"]
    # Applying "the cap from the other half-year" presupposes a published cap for this
    # year to be wrong about. With no rates there is nothing to be wrong against, and
    # the finding the skill owes is that it cannot tell - not a violation.
    if rates_known and rnd.random() < 0.35:
        cap_effective = M.REGIMES["H2" if regime_id == "H1" else "H1"]["max_insurable"]
        file_defects.append("B4_cap_from_wrong_period")
    regime_effective = dict(regime, max_insurable=cap_effective)

    used = set()
    people = []
    for _ in range(n):
        inp, row = make_person(rnd, norm, regime_effective, tzpb_effective, policy)
        people.append(dict(name=_name(rnd, used), department=rnd.choice(DEPARTMENTS),
                           inputs=inp, row=row))

    # one person on maternity leave for the whole month: no accruals, health only
    if n >= 10:
        inp = dict(monthly_salary=r2(rnd.uniform(1300, 2400)),
                   seniority_pct=rnd.choice([0, 1.2, 2.4]),
                   days_worked=0, days_leave=0, days_sick=0, days_maternity=norm,
                   bonus=0.0, compensation_224=0.0, card_employer=0.0,
                   card_employee=0.0, premium=r2(rnd.uniform(32.9, 44.5)),
                   personal_contribution=0.0)
        row = M.clean_row(inp, regime_effective, tzpb_effective, policy, norm)
        row["_norm"] = norm
        people.append(dict(name=_name(rnd, used), department=rnd.choice(DEPARTMENTS),
                           inputs=inp, row=row))
        rnd.shuffle(people)

    # B4 is a finding only if the wrong cap is actually visible somewhere
    if "B4_cap_from_wrong_period" in file_defects:
        visible = any(p["row"]["Осигурителен доход"] > regime["max_insurable"] + M.TOL
                      or (abs(p["row"]["Осигурителен доход"] - cap_effective) < M.TOL
                          and cap_effective < regime["max_insurable"])
                      for p in people)
        if not visible:
            file_defects.remove("B4_cap_from_wrong_period")

    # --- per-row defects ----------------------------------------------------
    expected = []
    free = list(range(len(people)))
    rnd.shuffle(free)
    candidates = ROW_MUTATIONS[:]
    rnd.shuffle(candidates)
    how_many = rnd.randint(5, 9)
    injected = 0
    spoiled = {"in_kind": 0, "excess": 0}      # rows whose vote is already wrong
    for ident, fn in candidates:
        if injected >= how_many or not free:
            break
        # recomputed per defect: every mutation already made can change which
        # row sits at a cap and which does not
        usable = _usable_rows(people, regime["max_insurable"], cap_effective)
        for idx in list(free):
            person = people[idx]
            if ident in NEEDS_PRACTICE:
                # The practice for every element the row carries must stay
                # establishable AFTER the mutation. Hence a fourth usable row:
                # the spoiled row either drops out of the sample (its figure no
                # longer matches any clean combination) or votes the other way.
                # Either way three clean rows must remain.
                if any(_carries(person["row"], el) and usable[el] < 4 + spoiled[el]
                       for el in ("in_kind", "excess")):
                    continue
            if ident.startswith("F10_"):
                el = "in_kind" if "in_kind" in ident else "excess"
                result = fn(person["row"], person["inputs"], regime_effective,
                            tzpb_effective, policy, rnd, usable=usable[el])
            else:
                result = fn(person["row"], person["inputs"], regime_effective,
                            tzpb_effective, policy, rnd)
            if result is None:
                continue
            new_row, ids = result
            new_row["_norm"] = norm
            if ident in SPOILS_SAMPLE:
                for el in ("in_kind", "excess"):
                    if _carries(person["row"], el):
                        spoiled[el] += 1
            person["row"] = new_row
            person["defects"] = sorted(ids)
            free.remove(idx)
            expected += [["row", idx, i] for i in sorted(ids)]
            injected += 1
            break

    # --- write --------------------------------------------------------------
    os.makedirs(TMP, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = f"{month:02d}-{year}"
    ws["A1"] = f'ВЕДОМОСТ ЗА РАБОТНИ ЗАПЛАТИ — "{company}" ЕООД'
    ws["A2"] = (f"Месец: {MONTHS_BG[month]} {year} г.  |  Работни дни: {norm}  |  "
                f"Валута: EUR  |  ЕИК: 000000000 (тестов)")
    ws["A3"] = f"Икономическа дейност: тестова  |  ТЗПБ по КИД: {tzpb}%"
    ws["A1"].font = Font(bold=True, size=12)

    HDR = 5
    for i, column in enumerate(M.COLUMNS, start=1):
        cell = ws.cell(row=HDR, column=i, value=column)
        cell.font = Font(bold=True, size=8)
        cell.alignment = Alignment(wrap_text=True, vertical="top")

    for offset, person in enumerate(people):
        r = HDR + 1 + offset
        ws.cell(row=r, column=M.COL["№"], value=offset + 1)
        ws.cell(row=r, column=M.COL["Име"], value=person["name"])
        ws.cell(row=r, column=M.COL["Отдел"], value=person["department"])
        for column in M.COLUMNS:
            if column in ("№", "Име", "Отдел"):
                continue
            v = person["row"].get(column, 0)
            ws.cell(row=r, column=M.COL[column],
                    value=(v if v else (0 if column in M.DAY_COLUMNS else None)))

    total_row = HDR + 1 + len(people)
    ws.cell(row=total_row, column=M.COL["Име"], value="ОБЩО").font = Font(bold=True)
    for column in M.SUMMED_COLUMNS:
        s = r2(sum(p["row"].get(column, 0) or 0 for p in people))
        ws.cell(row=total_row, column=M.COL[column], value=s).font = Font(bold=True)

    if rnd.random() < 0.4:
        column = rnd.choice(["Карта (за сметка на работодателя)",
                             "Доброволно здравно осигуряване (премия)",
                             "Удръжка карта (лична част)"])
        s = r2(sum(p["row"].get(column, 0) or 0 for p in people))
        if s > 0:
            file_defects.append("K5_total_not_sum")
            ws.cell(row=total_row, column=M.COL[column],
                    value=r2(s + len(people) * 0.004 + 0.02))

    for i, column in enumerate(M.COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = max(9, min(15, len(column) // 2 + 6))

    path = os.path.join(TMP, f"wide_{seed}.xlsx")
    wb.save(path)

    expected += [["file", None, i] for i in file_defects]

    manifest = dict(
        seed=seed, file=os.path.basename(path), sheet=ws.title,
        year=year, month=month, norm_days=norm, regime=regime_id,
        rates_known=rates_known,
        max_insurable=regime["max_insurable"],
        min_insurable_self=regime["min_insurable_self"],
        tzpb_due=tzpb, policy=policy, hdr=HDR, total_row=total_row,
        people=[dict(row=HDR + 1 + i, name=p["name"], inputs=p["inputs"],
                     defects=p.get("defects", [])) for i, p in enumerate(people)],
        expected=expected,
    )
    manifest_path = os.path.join(TMP, f"wide_{seed}_manifest.json")
    with open(manifest_path, "w", encoding="utf8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    return path, manifest_path, manifest


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--month", type=int, default=None, choices=[6, 7, 8, 9, 10, 11])
    ap.add_argument("--year", type=int, default=2026,
                    help="a year outside RATES_KNOWN_YEARS builds the refusal fixture")
    a = ap.parse_args()
    path, manifest_path, man = generate(a.seed, a.month, a.year)
    print(f"written:  {path}")
    print(f"manifest: {manifest_path}")
    print(f"{man['month']:02d}.{man['year']} · regime {man['regime']} · "
          f"{man['norm_days']} working days · {len(man['people'])} people · "
          f"accident rate {man['tzpb_due']}%")
    if not man["rates_known"]:
        print(f"rates: NONE published for {man['year']} in references/stavki.md - the "
              f"file carries the {man['regime']} thresholds rolled forward")
    print(f"policy: {man['policy']}")
    print(f"injected defects ({len(man['expected'])}):")
    for where, idx, ident in man["expected"]:
        loc = "file" if where == "file" else f"row {man['hdr'] + 1 + idx}"
        print(f"  {loc:9} {ident:28} {M.SCENARIOS[ident][1]}")
