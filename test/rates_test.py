# -*- coding: utf-8 -*-
"""Cross-checks the rates in `trz_model.py` against `references/stavki.md`.

    python test/rates_test.py

Why it exists. The skill has one first rule: no rate from memory, every figure
comes from stavki.md. The test model, however, is Python and keeps its own copy
of the same numbers - it cannot compute anything otherwise. That is a second
source of truth, and two sources drift apart. Update stavki.md and the other
suites keep passing on yesterday's figures with nothing to say about it.

This file closes that hole. It is also the only test worth running on **every**
change to the skill, because it is the only one that reads the skill.

Result: per rate, whether it was located in the reference file and whether it
matches the model. A value that cannot be located is also a failure: it means the
reference file was restructured and the correspondence is no longer verifiable.

The patterns match Bulgarian text, because the reference file is Bulgarian.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trz_model as M                                          # noqa: E402

RATES_FILE = os.path.normpath(os.path.join(
    HERE, "..", "skills", "trz-expert", "references", "stavki.md"))

with open(RATES_FILE, encoding="utf8") as f:
    TEXT = f.read()


def extract(pattern):
    """The first captured group as a number, or None."""
    m = re.search(pattern, TEXT)
    return float(m.group(1).replace(",", ".")) if m else None


# Default tolerance: recorded values are compared, not computed ones. A larger
# tolerance is given explicitly where the reference file holds the exact value
# while the model works with the money amount rounded to two decimals.
TOLERANCE = 0.001

# --- what is cross-checked: (label, pattern in stavki.md, value in the model) --
CHECKS = [
    ("minimum wage 2026, monthly",
     r"01\.01\.2026 – 31\.12\.2026 \|[^|]*\*\*([\d.]+) EUR\*\*",
     M.REGIMES["H1"]["min_wage"]),
    ("maximum insurable income, 01.01-31.07.2026",
     r"01\.01\.2026 – 31\.07\.2026 \|[^|]*\|\s*\*\*([\d.]+) EUR\*\*",
     M.REGIMES["H1"]["max_insurable"]),
    ("minimum insurable income, self-employed, 01.01-31.07.2026",
     r"01\.01\.2026 – 31\.07\.2026 \|\s*([\d.]+) EUR",
     M.REGIMES["H1"]["min_insurable_self"]),
    ("maximum insurable income, 01.08-31.12.2026",
     r"01\.08\.2026 – 31\.12\.2026 \|[^|]*\|\s*\*\*([\d.]+) EUR\*\*",
     M.REGIMES["H2"]["max_insurable"]),
    ("minimum insurable income, self-employed, 01.08-31.12.2026",
     r"01\.08\.2026 – 31\.12\.2026 \|\s*([\d.]+) EUR",
     M.REGIMES["H2"]["min_insurable_self"]),

    ("pension fund - employee share",
     r"Пенсии — родени след 1959 г\. \|[^|]*\|[^|]*\|\s*([\d.]+)\s*\|",
     M.EMPLOYEE["pension"]),
    ("pension fund - employer share",
     r"Пенсии — родени след 1959 г\. \|[^|]*\|\s*([\d.]+)\s*\|",
     8.22),
    ("sickness and maternity - employee share",
     r"Общо заболяване и майчинство \|[^|]*\|[^|]*\|\s*([\d.]+)\s*\|",
     M.EMPLOYEE["sickness"]),
    ("sickness and maternity - employer share",
     r"Общо заболяване и майчинство \|[^|]*\|\s*([\d.]+)\s*\|",
     2.10),
    ("unemployment - employee share",
     r"\| Безработица \|[^|]*\|[^|]*\|\s*([\d.]+)\s*\|",
     M.EMPLOYEE["unemployment"]),
    ("unemployment - employer share",
     r"\| Безработица \|[^|]*\|\s*([\d.]+)\s*\|",
     0.60),
    ("health insurance - employee share",
     r"\| Здравно осигуряване \| 8\.00 \|[^|]*\|\s*([\d.]+)\s*\|",
     M.EMPLOYEE["health"]),
    ("health insurance - employer share",
     r"\| Здравно осигуряване \| 8\.00 \|\s*([\d.]+)\s*\|",
     M.EMPLOYER_HEALTH),
    ("supplementary pension fund - employee share",
     r"ДЗПО — УПФ \|[^|]*\|[^|]*\|\s*([\d.]+)\s*\|",
     M.EMPLOYEE["upf"]),
    ("supplementary pension fund - employer share",
     r"ДЗПО — УПФ \|[^|]*\|\s*([\d.]+)\s*\|",
     M.EMPLOYER_UPF),

    ("control sum of the employee contributions",
     r"Лични вноски, трета категория \|\s*\*\*([\d.]+)%\*\*",
     M.EMPLOYEE_TOTAL),
    ("rounding allowance when summing the five contributions",
     r"осигурителния доход с до \*\*([\d.]+)\*\*",
     0.03),
    ("income tax rate",
     r"\| Данъчна ставка \|\s*\*\*([\d.]+)%\*\*",
     M.TAX_RATE * 100),
    ("length-of-service supplement per year",
     r"Минимален размер за всяка година придобит стаж \|\s*\*\*([\d.]+)%\*\*",
     M.SENIORITY_RATE),
    ("sick days at the employer's expense",
     r"Режимът е \*\*(\d+) работни дни",
     M.SICK_DAYS_EMPLOYER),
    ("rate for the first sick days",
     r"неработоспособност (\d+) на сто от среднодневното брутно възнаграждение",
     M.SICK_RATE * 100),
    ("health insurance during incapacity and maternity",
     r"\| Размер \|\s*\*\*([\d.]+)%\*\*, изцяло за сметка на работодателя",
     M.HEALTH_ON_INCAPACITY),
    ("limit of the чл. 19 ЗДДФЛ relief",
     r"удържани от работодателя \| до \*\*([\d.]+)%\*\*",
     M.RELIEF_LIMIT * 100),
    ("social-expense threshold in euro, 2026 - now confirmed",
     r"Същият праг \*\*в евро за 2026 г\.\*\* \| \*\*([\d.]+) EUR\*\*",
     M.SOCIAL_EXPENSE_THRESHOLD),
    ("the чл. 12/13 ЗВЕРБ conversion behind it",
     r"60 ÷ 1\.95583 = ([\d.]+)…",
     60 / M.FIXED_EUR_RATE, 0.0001),
    ("fixed euro rate",
     r"фиксиран курс \*\*([\d.]+) лв\. за 1 евро\*\*",
     M.FIXED_EUR_RATE),

    ("minimum wage per hour, 2026",
     r"01\.01\.2026 – 31\.12\.2026 \|[^|]*\|[^|]*?\*\*([\d.]+) EUR\*\*",
     M.REGIMES["H1"]["min_wage_hour"]),
    ("night-hour supplement 2026 - 0.15% of the minimum wage",
     r"\| 2026 \| 620\.20 EUR \| ([\d.]+) →",
     round(M.NIGHT_FACTOR * M.REGIMES["H1"]["min_wage"], 4), 0.0001),
    ("overtime premium on working days",
     r"\| Работни дни \| \*\*\+([\d.]+)%\*\*",
     M.OVERTIME_WORKDAY * 100),
    ("night-work floor after the euro changeover",
     r"\| 2026 \| 620\.20 EUR \|[^|]*\| ([\d.]+) EUR \|",
     M.NIGHT_FLOOR),
]

# --- rules the reference states in words, with no figure to extract ----------
# чл. 264 КТ writes the doubling as „удвоения размер“ and gives no numeral, so there is
# nothing for a regex to capture. Guard the wording instead: if the rule is ever
# restated, the constant in the model has to be revisited by hand rather than silently
# kept.
PHRASES = [
    ("work on a public holiday is paid at double",
     r"от удвоения размер на трудовото му възнаграждение",
     "M.HOLIDAY_MULTIPLIER", M.HOLIDAY_MULTIPLIER, 2.0),
]

# --- rates the reference file explicitly marks as unconfirmed ---------------
UNCONFIRMED = [
]


def main():
    print(f"Cross-check against {os.path.relpath(RATES_FILE, os.path.join(HERE, '..'))}")
    print("=" * 78)
    failed = []
    for check in CHECKS:
        label, pattern, in_model = check[:3]
        tolerance = check[3] if len(check) > 3 else TOLERANCE
        in_reference = extract(pattern)
        if in_reference is None:
            print(f"  NOT FOUND   {label}")
            print("              the reference file holds no value matching this "
                  "pattern - either it changed or the row was restructured")
            failed.append(label)
            continue
        if abs(in_reference - in_model) > tolerance:
            print(f"  MISMATCH    {label}")
            print(f"              stavki.md: {in_reference} | trz_model.py: {in_model}")
            failed.append(label)
        else:
            print(f"  ok          {label:58} {in_reference}")

    print()
    for label, pattern, name, in_model, expected in PHRASES:
        if not re.search(pattern, TEXT):
            print(f"  CHANGED     {label}")
            print(f"              the reference file no longer states this rule in "
                  f"these words. {name} rests on it - re-read the section before "
                  f"trusting the constant.")
            failed.append(label)
        elif in_model != expected:
            print(f"  MISMATCH    {label}")
            print(f"              the wording still says double, but {name} is "
                  f"{in_model}, not {expected}")
            failed.append(label)
        else:
            print(f"  ok          {label:58} {name} = {in_model}")

    print()
    for label, pattern, constant in UNCONFIRMED:
        if re.search(pattern, TEXT):
            print(f"  ok          {label} - still marked `за потвърждение`;")
            print(f"              {constant} is a working hypothesis, findings resting "
                  f"on it are `за проверка`")
        else:
            print(f"  CHANGED     {label}")
            print(f"              the status in the reference file is no longer "
                  f"`за потвърждение`. If it has been confirmed, verify {constant} "
                  f"and drop it from this list.")
            failed.append(label)

    print("=" * 78)
    total = len(CHECKS) + len(PHRASES) + len(UNCONFIRMED)
    if failed:
        print(f"FAILED: {len(failed)} of {total}")
        print("A rate in the reference file has drifted from test/trz_model.py. Fix "
              "the model, not the reference - the reference is the source of truth.")
        return 1
    print(f"OK: {total} rates match the reference file")
    return 0


if __name__ == "__main__":
    sys.exit(main())
