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
* **K2 (amount in a day column)** - a day count is always a whole number; a value
  with a fractional part in one of the four day-count concepts (worked days, paid
  leave, sick leave, maternity leave) means an amount was typed where a day count
  belongs. Not the proverki.md text's second clause ("or above the norm"): the norm
  varies by contract and this script has no calendar for it, the same reason B1/B5
  stand in the sheet's own maximum instead of computing one.
* **I8 (duplicated people)** - flagged when a name repeats AND
  бруто/осигурителен доход/нето all agree exactly with an earlier row under that
  name. Read as "probably" a copy-pasted row, not settled as one: preflight.py's
  CONCEPTS has no identity column (no ЕГН, by design - it is personal data this
  tool never reads), so two different employees on identical МРЗ pay who happen to
  share a name cannot be told apart from a genuine duplicate by any column this
  script has. Under-reports rather than over-reports as a result: proverki/i.md's
  I8 is "a person appearing twice", broader than what a name-plus-three-figures
  match can prove. Never prints the name itself, the same rule preflight.py
  already follows for its own report.
* **F1 / F10 (insurable-income composition) and the two statutory placements it also
  settles** - ported from test/structural_test.py's "solve the composition" method:
  which subset of the contested elements (доход в натура, превишение над необлагаемия
  праг) explains the insurable income, alongside the two elements the law has already
  settled (болнични always in, чл. 224 always out - чл. 3, ал. 1 НЕВДПОВ and
  чл. 1, ал. 8, т. 7 НЕВДПОВ respectively). Never settles which contested reading is
  correct: the file's own practice is inferred from at least three usable rows with a
  clear (2/3) majority, and only rows that disagree with THAT are findings
  (F10_in_kind_asymmetry, F10_excess_asymmetry). Where the practice cannot be
  established at all, only the two statutory placements are still checked
  (F1_compensation_in_insurable, F9_sick_pay_out_of_insurable), by enumerating every
  placement of the contested elements rather than assuming one
  (F10_practice_not_establishable names the gap instead of guessing through it).
  Skipped entirely for a row with no accruals for work (чл. 6, ал. 2 КСО - a benefit
  alone creates no insurable income) or sitting at the insurable-income cap (many
  different compositions reach the same capped figure). Gated on the sheet having NO
  unrecognised columns at all: an unrecognised accrual or benefit column would make a
  real composition silently unreachable, exactly the false-positive risk that limited
  K1/K3/K4/K7 in k_checker.py - in practice this means a mapping.yaml that declares
  every administrative/breakdown column (row numbers, department, per-fund
  contribution breakdowns already summed into a total the mapping does recognise) as
  `ignore`; without one, a real file's incidental columns will commonly block this
  pass entirely, safely, rather than wrongly.

  F10_in_kind_asymmetry and F10_excess_asymmetry are **partial**: the same two ids
  can also be raised from the TAXABLE base's side (a different composition, over the
  чл. 19, ал. 2 relief - see below), which this script does not compute. Verified
  against test/structural_test.py's own reference implementation directly (not only
  test/generate_wide.py's manifest) across 300 seeds: zero false positives, and every
  miss traced to the taxable-side occurrence of the same id, none to the insurable
  side this script claims.

Left to the model for now, a future increment: F6/F7/F9's remaining piece needs the
same composition method PLUS every placement of the чл. 19, ал. 2 relief enumerated
against it - test/structural_test.py needed several seed-specific bug fixes to get
that combination right even against the synthetic model with fixed column names, and
a wrong compliance finding from a rushed port is worse than the model computing it in
prose. Left to the model permanently, for the same reason K1/K3/K4/K7 are left to
k_checker.py: B2/B3/B6 need a company-specific number (the МОД threshold, or another
employer's declaration) mapping.yaml does not carry; F2/F3/F4 need a birth date or a
labour-category classification no payroll column carries; F8 needs the annual
reconciliation, which one month cannot show; K1/K3/K4/K7/K8 are k_checker.py's own
closed-vocabulary risk.
"""
import argparse
import os
import re
import sys
from collections import Counter

try:
    import openpyxl
    from openpyxl.utils import get_column_letter
except ImportError:                                          # pragma: no cover
    sys.exit("openpyxl is required: pip install -r test/requirements.txt")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import finding as FN                                          # noqa: E402
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
F1_INSURABLE_UNEXPLAINED = "F1_insurable_unexplained"
F1_COMPENSATION_IN_INSURABLE = "F1_compensation_in_insurable"
F9_SICK_PAY_OUT_OF_INSURABLE = "F9_sick_pay_out_of_insurable"
F10_IN_KIND_ASYMMETRY = "F10_in_kind_asymmetry"
F10_EXCESS_ASYMMETRY = "F10_excess_asymmetry"
F10_PRACTICE_NOT_ESTABLISHABLE = "F10_practice_not_establishable"
K2_AMOUNT_IN_DAY_COLUMN = "K2_amount_in_day_column"
I8_DUPLICATED_PEOPLE = "I8_duplicated_people"

# The four day-count concepts preflight.py's CONCEPTS names. A day count is always a
# whole number; a value with a fractional part in one of these means an amount was
# typed where a day count belongs (proverki/k.md's K2) - the same shape
# test/generate_wide.py's m_amount_in_day_column() injects (a sick-pay amount typed
# into "Дни болничен"). Not attempting the proverki.md text's second clause ("or above
# the norm"): the norm varies by contract and this script has no calendar, the same
# reason B1/B5 stand in the sheet's own maximum rather than compute one.
DAY_CONCEPTS = ("отработени дни", "дни отпуск", "дни болничен", "дни майчинство")

# A header carrying one of these words names a BALANCE, an ENTITLEMENT or an AVERAGE,
# not the count of days this row actually states - a different quantity that is
# legitimately fractional (a proportional leave entitlement under чл. 155, ал. 2 КТ,
# 20 x 5/12 = 8.33; an average). preflight.classify()'s substring pass reads a
# DAY_CONCEPTS spelling out of "Остатък дни отпуск" or "Средно отработени дни" just
# the same as out of the plain concept header, so K2 excludes by the header's own
# wording rather than trusting the concept name alone.
K2_HEADER_EXCLUDE = re.compile(r"остатък|полагаем|неизползван|среден|средно|баланс",
                               re.I)

DEDUCTION_CONCEPTS = ("удръжка доброволно осиг.", "удръжка живот", "удръжка карта")

# The concepts the insurable-income composition needs every one of, to run at all on a
# sheet - see the module docstring for why an unrecognised accrual/benefit column makes
# a real composition silently unreachable.
COMPOSITION_CONCEPTS = ("основна", "клас", "бонус", "платен отпуск", "болнични",
                       "обезщетение чл. 224", "карта работодател",
                       "доброволно здравно осиг. премия", "осиг. доход")
CONTESTED = ("in_kind", "excess")
_NAMES = {"in_kind": "доходът в натура", "excess": "превишението над необлагаемия праг",
          "sick_pay": "болничните от работодателя (чл. 40, ал. 5 КСО)",
          "comp_224": "обезщетението по чл. 224 КТ"}
_ID_FOR = {"comp_224": F1_COMPENSATION_IN_INSURABLE, "sick_pay": F9_SICK_PAY_OUT_OF_INSURABLE,
           "in_kind": F10_IN_KIND_ASYMMETRY, "excess": F10_EXCESS_ASYMMETRY}


def _num(ws, meta, r):
    if meta is None:
        return None
    v = ws.cell(r, meta["col"]).value
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _subsets(elements):
    """All subsets of [(name, value)] as [(frozenset(names), sum)]. Ported verbatim
    from test/structural_test.py - the same method, the same rounding.
    """
    out = [(frozenset(), 0.0)]
    for name, v in elements:
        if not v:
            continue
        out += [(frozenset(m | {name}), round(s + v, 2)) for m, s in out]
    return out


def _statutory_misplacements(work_base, insurable, el, tol):
    """Which of the two STATUTE-SETTLED elements (болнични always in, чл. 224 always
    out) sits on the unlawful side of the insurable income, without assuming a
    placement for the CONTESTED elements (in_kind, excess) at all - every combination
    of theirs is tried, and an element is reported only when every combination
    reaching the declared figure puts it on the unlawful side. Ported from
    test/structural_test.py's statutory_misplacements().
    """
    sums = [s for _, s in _subsets([("in_kind", el["in_kind"]), ("excess", el["excess"])])]
    matches = []
    for sick_in in ((True, False) if el["sick_pay"] else (True,)):
        for comp_in in ((False, True) if el["comp_224"] else (False,)):
            base = round(work_base + (el["sick_pay"] if sick_in else 0.0)
                         + (el["comp_224"] if comp_in else 0.0), 2)
            if any(abs(round(base + s, 2) - insurable) <= tol for s in sums):
                matches.append((sick_in, comp_in))
    out = set()
    if matches and el["sick_pay"] and all(not si for si, _ in matches):
        out.add("sick_pay")
    if matches and el["comp_224"] and all(ci for _, ci in matches):
        out.add("comp_224")
    return out


def check(path, mapping=None, kid=None, group=None, tzpb=None):
    """(findings, coverage): findings as a list of dicts, coverage as one dict per
    sheet describing how many rows this script actually evaluated against how many
    are there - never writes, reads the workbook once, values only.

    A finding says what is wrong; coverage says what was looked at, which a reader
    cannot get from the findings alone - a clean sheet and an unevaluated one both
    raise nothing. The insurable-income composition pass in particular is gated on
    the whole sheet (any unrecognised column blocks it entirely, see the module
    docstring) and skips individual rows at the cap or with no accruals for work -
    both silent before this return value existed.
    """
    mapping = mapping or PF.Mapping()
    data = PF.analyse(path, mapping, kid, group, tzpb)
    wb = openpyxl.load_workbook(path, data_only=True)
    findings = []
    coverage = []

    flat = R.load_flat(SKILL_DIR)
    employer_no_tzpb = flat.get("employer_no_tzpb_pct")
    declared_tzpb = tzpb if tzpb is not None else mapping.tzpb

    for s in data["sheets"]:
        if s["header_row"] is None or not s["first_row"]:
            coverage.append(dict(sheet=s["name"], rows_total=0,
                                 skip_reason="no header row found"))
            continue
        ws = wb[s["name"]]
        last = (s["totals_row"] - 1) if s["totals_row"] else ws.max_row
        if last < s["first_row"]:
            coverage.append(dict(sheet=s["name"], rows_total=0,
                                 skip_reason="no data row found"))
            continue
        known = s["known"]
        sheet_cov = dict(sheet=s["name"], rows_total=last - s["first_row"] + 1,
                         composition_ran=False, composition_gate_reason=None,
                         composition_rows_evaluated=0,
                         composition_rows_skipped_no_work=0,
                         composition_rows_skipped_at_cap=0,
                         composition_rows_skipped_no_value=0)
        coverage.append(sheet_cov)

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

            # --- K2: an amount typed into a column meant for days -------------
            # 0.005, not the money TOL (0.02): a typed amount always ends in exactly
            # two decimals, so its fractional part can be as small as .01 or .99 away
            # from the nearest whole number - a threshold of 0.01 or looser missed
            # those at the boundary (172.01 read as "close enough" to 172).
            #
            # preflight.classify()'s substring pass reads "дни отпуск" out of
            # "Остатък дни отпуск" or "Полагаеми дни отпуск" (a leave BALANCE or
            # ENTITLEMENT, legitimately fractional under чл. 155, ал. 2 КТ's
            # proportional accrual - 20 x 5/12 = 8.33) and "отработени дни" out of
            # "Средно отработени дни" (an average). Those are a different quantity
            # from the concept, not a typo, so K2_HEADER_EXCLUDE skips them by the
            # header's own wording - found by adversarial review asking exactly this
            # question, not by any suite here.
            for concept in DAY_CONCEPTS:
                meta = known.get(concept)
                if meta is None or K2_HEADER_EXCLUDE.search(meta["header"]):
                    continue
                v = _num(ws, meta, r)
                if v is not None and abs(v - round(v)) > 0.005:
                    findings.append(FN.make_finding(
                        K2_AMOUNT_IN_DAY_COLUMN, sheet=s["name"], row=r,
                        text=f"{ref}: „{meta['header']}“ ({concept}) е {v:.2f} — "
                             f"дробна част в колона за дни означава, че там е "
                             f"въведена сума, не брой дни",
                    ))

            # --- I1: vertical reconciliation ---------------------------------
            if None not in (bruto, lichni, danak, neto_pre):
                expected_pre = round(bruto - lichni - danak, 2)
                if abs(neto_pre - expected_pre) > TOL:
                    findings.append(FN.make_finding(
                        I1_VERTICAL, sheet=s["name"], row=r,
                        stated=neto_pre, due=expected_pre,
                        text=f"{ref}: НЕТО преди удръжки е {neto_pre:.2f}, а "
                             f"БРУТО − лични вноски − данък = {expected_pre:.2f}",
                    ))
            if None not in (neto_pre, neto):
                deductions = sum(_num(ws, known.get(c), r) or 0
                                 for c in DEDUCTION_CONCEPTS)
                expected_neto = round(neto_pre - deductions, 2)
                if abs(neto - expected_neto) > TOL:
                    findings.append(FN.make_finding(
                        I1_VERTICAL, sheet=s["name"], row=r,
                        stated=neto, due=expected_neto,
                        text=f"{ref}: НЕТО за изплащане е {neto:.2f}, а "
                             f"НЕТО преди удръжки − удръжките = {expected_neto:.2f}",
                    ))

            # --- I5, narrow: sick pay accrued with zero sick days ------------
            if bolnichni and bolnichni > TOL and dni_bolnichen == 0:
                findings.append(FN.make_finding(
                    I5_SICK_PAY_WITHOUT_DAYS, sheet=s["name"], row=r,
                    text=f"{ref}: болнични от работодателя {bolnichni:.2f}, но "
                         f"дни болничен е 0",
                ))

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
                findings.append(FN.make_finding(
                    B1_BELOW_MIN_WAGE, sheet=s["name"], row=r,
                    stated=osnovna, due=min_wage,
                    text=f"{ref}: основна {osnovna:.2f} под МРЗ {min_wage:.2f} "
                         f"за периода",
                ))

            # --- B5: осиг. доход below the minimum wage -----------------------
            if (not part_time and min_wage is not None and osig is not None
                    and osig < min_wage - TOL):
                findings.append(FN.make_finding(
                    B5_INSURABLE_BELOW_MIN_WAGE, sheet=s["name"], row=r,
                    stated=osig, due=min_wage,
                    text=f"{ref}: осигурителен доход {osig:.2f} под МРЗ "
                         f"{min_wage:.2f} за периода",
                ))

            # --- B4: осиг. доход above the maximum insurable income, or capped at a
            # neighbouring period's threshold instead of this period's own ----------
            if max_insurable is not None and osig is not None:
                if osig > max_insurable + TOL:
                    findings.append(FN.make_finding(
                        B4_ABOVE_MAX_INSURABLE, sheet=s["name"], row=r,
                        stated=osig, due=max_insurable,
                        text=f"{ref}: осигурителен доход {osig:.2f} над "
                             f"максималния {max_insurable:.2f} за периода",
                    ))
                elif osig < max_insurable - TOL and any(
                        abs(osig - oc) < TOL for oc in other_caps):
                    findings.append(FN.make_finding(
                        B4_ABOVE_MAX_INSURABLE, sheet=s["name"], row=r,
                        stated=osig, due=max_insurable,
                        text=f"{ref}: осигурителен доход {osig:.2f} съвпада с "
                             f"максималния за друг период, не {max_insurable:.2f} "
                             f"за този",
                    ))

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
                    findings.append(FN.make_finding(
                        F5_TZPB_BELOW_DUE, sheet=s["name"], row=r,
                        stated=implied_tzpb, due=declared_tzpb,
                        text=f"{ref}: изведен ТЗПБ {implied_tzpb:.2f}% под "
                             f"декларирания {declared_tzpb:.2f}%",
                    ))

        # --- I8: duplicated people ------------------------------------------
        # A copy-pasted row, not two different people who happen to share a name:
        # flagged only when the name AND бруто/осиг. доход/нето all agree exactly,
        # the same way F1/F9/F10 above never print the name column's own content
        # (preflight.py's own rule: the name column is not reproduced in a report).
        name_meta = known.get("име")
        if (name_meta is not None and "бруто" in known and "осиг. доход" in known
                and "нето" in known):
            seen = {}
            for r in range(s["first_row"], last + 1):
                name = ws.cell(r, name_meta["col"]).value
                if not isinstance(name, str) or not name.strip():
                    continue
                key_name = " ".join(name.split()).casefold()
                bruto_r = _num(ws, known.get("бруто"), r)
                osig_r = _num(ws, known.get("осиг. доход"), r)
                neto_r = _num(ws, known.get("нето"), r)
                if None in (bruto_r, osig_r, neto_r):
                    continue
                fig = (bruto_r, osig_r, neto_r)
                # One finding per repeated row, not one per EARLIER match: three
                # identical rows are one copy-pasted error repeated twice, not three
                # things to fix, the same "one cause, not N findings" principle
                # otchet.md states for the report as a whole - so stop at the first
                # match instead of reporting against every earlier occurrence.
                for other_r, other_fig in seen.get(key_name, []):
                    if all(abs(a - b) <= TOL for a, b in zip(fig, other_fig)):
                        findings.append(FN.make_finding(
                            I8_DUPLICATED_PEOPLE, sheet=s["name"], row=r,
                            text=f"{s['name']}!{r}: същото име и същите "
                                 f"бруто/осиг. доход/нето като ред {other_r} — "
                                 f"може да е копиран ред, а може и да са две "
                                 f"лица със същото име и еднакво заплащане; "
                                 f"провери преди да заключиш",
                        ))
                        break
                seen.setdefault(key_name, []).append((r, fig))

        # --- F1/F10/F9(insurable)/F1(compensation): insurable-income composition --
        # A second pass, over every row again: the file's practice for the contested
        # elements can only be inferred after every row's own composition is solved
        # once. See the module docstring for the method and its two hard limits
        # (nothing decided at the cap, nothing decided without accruals for work).
        if all(c in known for c in COMPOSITION_CONCEPTS) and not s["unknown"]:
            sheet_cov["composition_ran"] = True
            social_threshold = flat.get("social_expense_threshold_eur")
            rows_data = []
            for r in range(s["first_row"], last + 1):
                osnovna_c = _num(ws, known.get("основна"), r) or 0.0
                klas_c = _num(ws, known.get("клас"), r) or 0.0
                bonus_c = _num(ws, known.get("бонус"), r) or 0.0
                leave_c = _num(ws, known.get("платен отпуск"), r) or 0.0
                work_base = round(osnovna_c + klas_c + bonus_c + leave_c, 2)
                el = {
                    "in_kind": _num(ws, known.get("карта работодател"), r) or 0.0,
                    "excess": 0.0,
                    "sick_pay": _num(ws, known.get("болнични"), r) or 0.0,
                    "comp_224": _num(ws, known.get("обезщетение чл. 224"), r) or 0.0,
                }
                premium = _num(ws, known.get("доброволно здравно осиг. премия"), r) or 0.0
                if premium and social_threshold is not None:
                    el["excess"] = round(max(0.0, premium - social_threshold), 2)
                osig_c = _num(ws, known.get("осиг. доход"), r)
                if osig_c is None:
                    sheet_cov["composition_rows_skipped_no_value"] += 1
                    continue
                at_cap = (max_insurable is not None
                         and any(abs(osig_c - c) < 0.005
                                 for c in [max_insurable] + other_caps))
                no_work = work_base <= 0
                inside_unique = None
                if not at_cap and not no_work:
                    matches = [mask for mask, sm in
                              _subsets([(k, el[k]) for k in CONTESTED])
                              if abs(round(work_base + el["sick_pay"] + sm, 2)
                                    - osig_c) <= TOL]
                    if len(matches) == 1:
                        inside_unique = matches[0]
                rows_data.append(dict(row=r, work_base=work_base, el=el,
                                      insurable=osig_c, at_cap=at_cap,
                                      no_work=no_work, inside_unique=inside_unique))

            def practice_for(el_name):
                sample = [el_name in d["inside_unique"] for d in rows_data
                         if d["inside_unique"] is not None and d["el"][el_name]]
                if len(sample) < 3:
                    return None, len(sample)
                value, count = Counter(sample).most_common(1)[0]
                if count / len(sample) < 2 / 3:
                    return None, len(sample)
                return value, len(sample)

            practice = {}
            for el_name in CONTESTED:
                value, size = practice_for(el_name)
                practice[el_name] = value
                if value is None and any(d["el"][el_name] for d in rows_data):
                    findings.append(FN.make_finding(
                        F10_PRACTICE_NOT_ESTABLISHABLE, sheet=s["name"], row=None,
                        text=f"{s['name']}: практиката на файла за "
                             f"{_NAMES[el_name]} в осигурителния доход не може да "
                             f"се изведе от самия файл ({size} използваеми реда)",
                    ))

            for d in rows_data:
                if d["no_work"]:
                    sheet_cov["composition_rows_skipped_no_work"] += 1
                    continue
                if d["at_cap"]:
                    sheet_cov["composition_rows_skipped_at_cap"] += 1
                    continue                # B4 already covers the cap
                sheet_cov["composition_rows_evaluated"] += 1
                el = d["el"]
                practice_clear = not any(el[k] and practice[k] is None
                                        for k in CONTESTED)
                allowed = {k for k in CONTESTED if practice[k] and el[k]}
                allowed_sum = round(sum(el[k] for k in allowed), 2)
                inside_expected = allowed | ({"sick_pay"} if el["sick_pay"] else set())
                expected_insurable = round(d["work_base"] + el["sick_pay"]
                                          + allowed_sum, 2)
                ref = f"{s['name']}!{d['row']}"

                if practice_clear and abs(d["insurable"] - expected_insurable) > TOL:
                    added = [k for k, v in el.items()
                            if v and k not in inside_expected
                            and abs(round(expected_insurable + v, 2)
                                    - d["insurable"]) <= TOL]
                    removed = [k for k in inside_expected
                              if abs(round(expected_insurable - el[k], 2)
                                    - d["insurable"]) <= TOL]
                    if len(added) == 1:
                        k = added[0]
                        findings.append(FN.make_finding(
                            _ID_FOR[k], sheet=s["name"], row=d["row"],
                            text=f"{ref}: {_NAMES[k]} ({el[k]:.2f}) е вътре в "
                                 f"осигурителния доход, докато другите редове го "
                                 f"оставят вън",
                        ))
                    elif len(removed) == 1:
                        k = removed[0]
                        findings.append(FN.make_finding(
                            _ID_FOR[k], sheet=s["name"], row=d["row"],
                            text=f"{ref}: {_NAMES[k]} ({el[k]:.2f}) е вън от "
                                 f"осигурителния доход, докато другите редове го "
                                 f"включват",
                        ))
                    else:
                        findings.append(FN.make_finding(
                            F1_INSURABLE_UNEXPLAINED, sheet=s["name"], row=d["row"],
                            stated=d["insurable"], due=expected_insurable,
                            text=f"{ref}: осигурителният доход {d['insurable']:.2f} "
                                 f"не съвпада с работната база {d['work_base']:.2f} "
                                 f"плюс допустимото по практиката на файла "
                                 f"({expected_insurable:.2f})",
                        ))
                elif el["sick_pay"] or el["comp_224"]:
                    wrong_side = _statutory_misplacements(d["work_base"],
                                                          d["insurable"], el, TOL)
                    if "sick_pay" in wrong_side:
                        findings.append(FN.make_finding(
                            F9_SICK_PAY_OUT_OF_INSURABLE, sheet=s["name"], row=d["row"],
                            text=f"{ref}: {_NAMES['sick_pay']} "
                                 f"({el['sick_pay']:.2f}) е вън от осигурителния "
                                 f"доход {d['insurable']:.2f} — нито една "
                                 f"комбинация от спорните елементи го достига с "
                                 f"тях вътре",
                        ))
                    if "comp_224" in wrong_side:
                        findings.append(FN.make_finding(
                            F1_COMPENSATION_IN_INSURABLE, sheet=s["name"], row=d["row"],
                            text=f"{ref}: {_NAMES['comp_224']} "
                                 f"({el['comp_224']:.2f}) е вътре в осигурителния "
                                 f"доход {d['insurable']:.2f} — нито една "
                                 f"комбинация от спорните елементи го достига без "
                                 f"него",
                        ))
        else:
            missing = [c for c in COMPOSITION_CONCEPTS if c not in known]
            reasons = []
            if missing:
                reasons.append("липсващи понятия: " + ", ".join(missing))
            if s["unknown"]:
                reasons.append(f"{len(s['unknown'])} неразпознати колони")
            sheet_cov["composition_gate_reason"] = "; ".join(reasons)
    return findings, coverage


def report(path, findings):
    L = [f"# B/F/I/K — `{os.path.basename(path)}`\n",
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


def coverage_report(coverage):
    """How many rows this script actually evaluated, per sheet - not a percentage
    (otchet.md's "Без процент на покритие" applies here just as much as to the model's
    own report: a denominator like "86 checks" is not uniform across files, and this
    script only ever claims the mechanical subset anyway). Counts only: found, ran,
    skipped and why.
    """
    L = ["\n## Обхват\n"]
    for c in coverage:
        L.append(f"\n### Лист „{c['sheet']}“\n")
        if c.get("skip_reason"):
            L.append(f"- {c['skip_reason']} — този лист не е обходен от скрипта")
            continue
        L.append(f"- редове с данни: {c['rows_total']}")
        if not c["composition_ran"]:
            L.append(f"- съставът на осигурителния доход (F1/F9/F10) не е проверен "
                     f"за целия лист — {c['composition_gate_reason']}")
            continue
        evaluated = c["composition_rows_evaluated"]
        skipped_no_work = c["composition_rows_skipped_no_work"]
        skipped_cap = c["composition_rows_skipped_at_cap"]
        skipped_no_value = c["composition_rows_skipped_no_value"]
        L.append(f"- съставът на осигурителния доход: {evaluated} от "
                 f"{c['rows_total']} реда проверени"
                 + (f"; {skipped_no_work} без начисления за труд (чл. 6, ал. 2 КСО)"
                    if skipped_no_work else "")
                 + (f"; {skipped_cap} на тавана (много съставки водят до същата сума)"
                    if skipped_cap else "")
                 + (f"; {skipped_no_value} без стойност в „Осигурителен доход“"
                    if skipped_no_value else ""))
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
        findings, coverage = check(a.workbook, mapping, a.kid, a.group, tzpb)
    except Exception as exc:                                  # noqa: BLE001
        print(f"файлът не може да бъде прочетен: {exc}", file=sys.stderr)
        return 2

    text = report(a.workbook, findings) + coverage_report(coverage)
    if a.out:
        with open(a.out, "w", encoding="utf8") as f:
            f.write(text)
        print(f"докладът е записан в {a.out}")
    else:
        print(text)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
