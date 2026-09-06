#!/usr/bin/env python3
"""B, F and I, computed from a real workbook instead of read in prose.

The first external review of this skill's tools found the model rewrites all 86
checks as a fresh script every audit, and that its measured accuracy is worst on the
multi-step arithmetic - the checks in these three groups above all. This script
covers the subset of them that is both mechanical (a comparison against a rate, or a
row's own numbers against each other) and safe for a generic tool to claim: it never
guesses at column meaning beyond `preflight.py`'s CONCEPTS, and every rate it uses is
read fresh from `references/stavki.md` at call time via `rates.py`, never typed in
here - the one rule this whole project exists to enforce applies to this file exactly
as it does to the model's prose.

What is covered, and why the rest of each group is not:

* **I1 (vertical reconciliation)** - a payslip's own numbers must chain: БРУТО minus
  the personal contributions minus the tax gives НЕТО преди удръжки; that minus the
  three personal deductions gives НЕТО за изплащане. Pure row arithmetic, no rate
  needed beyond what the row already states.
* **I5, narrow** - an amount accrued for sick pay with zero sick days recorded is a
  contradiction regardless of any calendar. The fuller I5 ("do the day columns sum to
  the month's working-day norm") needs a public-holiday calendar this script does not
  have, so it is not attempted here.
* **B1 / B5 (minimum wage)** - основна and осигурителен доход each have a floor,
  read from `references/stavki/mrz-mod.md` for the row's own period.
* **B4 (maximum insurable income)** - a ceiling from the same file.
* **F5 (ТЗПБ)** - the accident-and-disease rate is rarely stated directly; it is
  extracted algebraically from the employer's total contributions the same way
  `proverki/f.md` describes, and compared against the rate the mapping declares for
  the company's КИД. Skipped for a row with sick or maternity days, because the
  employer's total there also carries the healthcare contribution on МОД (F9), which
  the same formula would misread as ТЗПБ.

Left to the model, for the same reason K1/K3/K4/K7 are left to it in k_checker.py:
B2/B3/B6 need a company-specific number (the МОД threshold, or another employer's
declaration) mapping.yaml does not carry; F1/F2/F3/F4/F6/F7/F9's composition/relief
logic needs the full accrual-and-benefit vocabulary AND a judgment call this script
is not positioned to make safely yet (a future increment); F8/F10 need information -
the annual reconciliation, the company's chosen reading of a contested asymmetry -
this script cannot see in one workbook.
"""
import argparse
import os
import sys

try:
    import openpyxl
    from openpyxl.utils import get_column_letter
except ImportError:                                          # pragma: no cover
    sys.exit("openpyxl is required: pip install -r test/requirements.txt")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import preflight as PF                                       # noqa: E402
import rates as R                                             # noqa: E402

SKILL_DIR = os.path.dirname(HERE)

TOL = 0.02                  # money comparisons: two cents, the rounding a chain of
                             # per-row roundings can legitimately accumulate

I1_VERTICAL = "I1_vertical"
I5_SICK_PAY_WITHOUT_DAYS = "I5_sick_pay_without_days"
B1_BELOW_MIN_WAGE = "B1_below_minimum_wage"
B4_ABOVE_MAX_INSURABLE = "B4_cap_from_wrong_period"
B5_INSURABLE_BELOW_MIN_WAGE = "B5_insurable_below_minimum_wage"
F5_TZPB_BELOW_DUE = "F5_tzpb_below_due"

DEDUCTION_CONCEPTS = ("удръжка доброволно осиг.", "удръжка живот", "удръжка карта")


def _num(ws, meta, r):
    if meta is None:
        return None
    v = ws.cell(r, meta["col"]).value
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def check(path, mapping=None, kid=None, group=None, tzpb=None):
    """Findings as a list of dicts. Never writes; reads the workbook once, values only."""
    mapping = mapping or PF.Mapping()
    data = PF.analyse(path, mapping, kid, group, tzpb)
    wb = openpyxl.load_workbook(path, data_only=True)
    findings = []

    flat = R.load_flat(SKILL_DIR)
    employer_no_tzpb = flat.get("employer_no_tzpb_pct")
    declared_tzpb = tzpb if tzpb is not None else mapping.tzpb

    for s in data["sheets"]:
        if s["header_row"] is None or not s["first_row"]:
            continue
        ws = wb[s["name"]]
        last = (s["totals_row"] - 1) if s["totals_row"] else ws.max_row
        if last < s["first_row"]:
            continue
        known = s["known"]

        min_wage = max_insurable = None
        other_caps = []
        if s["period"]:
            year, month = s["period"]
            min_wage = R.for_period(SKILL_DIR, "min_wage_month", year, month)
            max_insurable = R.for_period(SKILL_DIR, "max_insurable", year, month)
            other_caps = R.other_periods_in_year(SKILL_DIR, "max_insurable", year, month)

        # B1/B5 only compare against the full МРЗ for a row working full time -
        # чл. 1, ал. 2 НСОРЗ prorates the minimum for contracted part-time work, and
        # this sheet may not say who is full-time except by comparison. Neither has a
        # public-holiday calendar to compute the true month norm (see the module
        # docstring), so the highest declared hours on the sheet stands in for "full
        # time" instead: the *mode* was tried first and rejected - in a small office
        # where nobody that month has zero leave or sick days, the most common day
        # count is itself a partial one, and comparing against it still produced false
        # positives at scale against test/generate_wide.py. The max is right whenever
        # at least one row that month is undiminished, which a full working month
        # almost always has one of.
        hours_meta = known.get("часове на ден")
        full_time_hours = None
        if hours_meta is not None:
            hours_values = [_num(ws, hours_meta, r) for r in range(s["first_row"], last + 1)]
            hours_values = [h for h in hours_values if h is not None]
            if hours_values:
                full_time_hours = max(hours_values)

        days_meta = known.get("отработени дни")
        full_month_days = None
        if days_meta is not None:
            day_values = [_num(ws, days_meta, r) for r in range(s["first_row"], last + 1)]
            day_values = [d for d in day_values if d is not None]
            if day_values:
                full_month_days = max(day_values)

        for r in range(s["first_row"], last + 1):
            osnovna = _num(ws, known.get("основна"), r)
            osig = _num(ws, known.get("осиг. доход"), r)
            bruto = _num(ws, known.get("бруто"), r)
            danak = _num(ws, known.get("данък"), r)
            lichni = _num(ws, known.get("лични вноски"), r)
            neto_pre = _num(ws, known.get("нето преди удръжки"), r)
            neto = _num(ws, known.get("нето"), r)
            vnoski_rab = _num(ws, known.get("вноски раб-л"), r)
            dni_bolnichen = _num(ws, known.get("дни болничен"), r)
            dni_maichinstvo = _num(ws, known.get("дни майчинство"), r)
            bolnichni = _num(ws, known.get("болнични"), r)
            ref = f"{s['name']}!{r}"

            # --- I1: vertical reconciliation ---------------------------------
            if None not in (bruto, lichni, danak, neto_pre):
                expected_pre = round(bruto - lichni - danak, 2)
                if abs(neto_pre - expected_pre) > TOL:
                    findings.append({
                        "id": I1_VERTICAL, "sheet": s["name"], "row": r,
                        "text": f"{ref}: НЕТО преди удръжки е {neto_pre:.2f}, а "
                                f"БРУТО − лични вноски − данък = {expected_pre:.2f}",
                    })
            if None not in (neto_pre, neto):
                deductions = sum(_num(ws, known.get(c), r) or 0
                                 for c in DEDUCTION_CONCEPTS)
                expected_neto = round(neto_pre - deductions, 2)
                if abs(neto - expected_neto) > TOL:
                    findings.append({
                        "id": I1_VERTICAL, "sheet": s["name"], "row": r,
                        "text": f"{ref}: НЕТО за изплащане е {neto:.2f}, а "
                                f"НЕТО преди удръжки − удръжките = {expected_neto:.2f}",
                    })

            # --- I5, narrow: sick pay accrued with zero sick days ------------
            if bolnichni and bolnichni > TOL and dni_bolnichen == 0:
                findings.append({
                    "id": I5_SICK_PAY_WITHOUT_DAYS, "sheet": s["name"], "row": r,
                    "text": f"{ref}: болнични от работодателя {bolnichni:.2f}, но "
                            f"дни болничен е 0",
                })

            # A row's own hours below the sheet's modal (full-time) hours, or its own
            # worked days below the modal (full-month) days, means B1/B5 cannot
            # compare it against the full МРЗ without the missing fraction - skip
            # rather than prorate a number this script was not given.
            row_hours = _num(ws, hours_meta, r) if hours_meta is not None else None
            row_days = _num(ws, days_meta, r) if days_meta is not None else None
            part_time = (
                (full_time_hours is not None and row_hours is not None
                 and row_hours < full_time_hours - TOL)
                or (full_month_days is not None and row_days is not None
                    and row_days < full_month_days - TOL))

            # --- B1: основна below the minimum wage --------------------------
            if (not part_time and min_wage is not None and osnovna is not None
                    and osnovna < min_wage - TOL):
                findings.append({
                    "id": B1_BELOW_MIN_WAGE, "sheet": s["name"], "row": r,
                    "text": f"{ref}: основна {osnovna:.2f} под МРЗ {min_wage:.2f} "
                            f"за периода",
                })

            # --- B5: осиг. доход below the minimum wage -----------------------
            if (not part_time and min_wage is not None and osig is not None
                    and osig < min_wage - TOL):
                findings.append({
                    "id": B5_INSURABLE_BELOW_MIN_WAGE, "sheet": s["name"], "row": r,
                    "text": f"{ref}: осигурителен доход {osig:.2f} под МРЗ "
                            f"{min_wage:.2f} за периода",
                })

            # --- B4: осиг. доход above the maximum insurable income, or capped at a
            # neighbouring period's threshold instead of this period's own ----------
            if max_insurable is not None and osig is not None:
                if osig > max_insurable + TOL:
                    findings.append({
                        "id": B4_ABOVE_MAX_INSURABLE, "sheet": s["name"], "row": r,
                        "text": f"{ref}: осигурителен доход {osig:.2f} над "
                                f"максималния {max_insurable:.2f} за периода",
                    })
                elif osig < max_insurable - TOL and any(
                        abs(osig - oc) < TOL for oc in other_caps):
                    findings.append({
                        "id": B4_ABOVE_MAX_INSURABLE, "sheet": s["name"], "row": r,
                        "text": f"{ref}: осигурителен доход {osig:.2f} съвпада с "
                                f"максималния за друг период, не {max_insurable:.2f} "
                                f"за този",
                    })

            # --- F5: ТЗПБ extracted below the declared rate -------------------
            # Skipped on sick/maternity days: the employer's total there also carries
            # the ЗО по т. 5 contribution on МОД (F9), which this algebra would
            # misread as part of ТЗПБ.
            has_sick_or_maternity = bool(dni_bolnichen) or bool(dni_maichinstvo)
            if (declared_tzpb is not None and employer_no_tzpb is not None
                    and vnoski_rab is not None and osig and osig > TOL
                    and not has_sick_or_maternity):
                implied_tzpb = round(vnoski_rab / osig * 100.0 - employer_no_tzpb, 4)
                if implied_tzpb < declared_tzpb - 0.05:
                    findings.append({
                        "id": F5_TZPB_BELOW_DUE, "sheet": s["name"], "row": r,
                        "text": f"{ref}: изведен ТЗПБ {implied_tzpb:.2f}% под "
                                f"декларирания {declared_tzpb:.2f}%",
                    })
    return findings


def report(path, findings):
    L = [f"# B/F/I — `{os.path.basename(path)}`\n",
         "Само механичните проверки, изброени в докстринга на скрипта; останалите "
         "от групите остават на анализа.\n"]
    if not findings:
        L.append("Нищо не е намерено.")
        return "\n".join(L) + "\n"
    by_sheet = {}
    for f in findings:
        by_sheet.setdefault(f["sheet"], []).append(f)
    for sheet, items in by_sheet.items():
        L.append(f"\n## Лист „{sheet}“\n")
        for f in items:
            L.append(f"- **{f['id']}** {f['text']}")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("workbook")
    ap.add_argument("--mapping", help="mapping.yaml describing this company's layout")
    ap.add_argument("--kid", help="КИД code of the company, e.g. 62")
    ap.add_argument("--group", help="qualification group for the МОД row")
    ap.add_argument("--tzpb", help="accident-insurance percentage for the КИД")
    ap.add_argument("--out", help="write the report here instead of stdout")
    a = ap.parse_args(argv)

    if not os.path.exists(a.workbook):
        print(f"няма такъв файл: {a.workbook}", file=sys.stderr)
        return 2
    mapping = None
    if a.mapping:
        try:
            mapping = PF.Mapping.load(a.mapping)
        except Exception as exc:                              # noqa: BLE001
            print(f"описът не може да бъде прочетен: {exc}", file=sys.stderr)
            return 2
    try:
        tzpb = float(a.tzpb) if a.tzpb is not None else None
        findings = check(a.workbook, mapping, a.kid, a.group, tzpb)
    except Exception as exc:                                  # noqa: BLE001
        print(f"файлът не може да бъде прочетен: {exc}", file=sys.stderr)
        return 2

    text = report(a.workbook, findings)
    if a.out:
        with open(a.out, "w", encoding="utf8") as f:
            f.write(text)
        print(f"докладът е записан в {a.out}")
    else:
        print(text)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
