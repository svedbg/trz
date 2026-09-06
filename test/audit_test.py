# -*- coding: utf-8 -*-
"""Proves scripts/audit.py has teeth, three ways.

Part 1 runs it against test/generate_wide.py's actual injected fixtures across many
seeds and compares counts against the manifest exactly, the way test/k_checker_test.py
does for K5/K6 - no less, no more. I1, B4 and F5 all have a scenario there.

Part 2 runs it against test/vedomost_05_2026.xlsx (suite 1's static fixture) and checks
against test/expected_findings.md's own key: B1 at row 6, B4 at row 9, and - the point
of keeping this fixture in the mix at all - row 13 (Стефка Ангелова, part-time, 4 hours
against a full-time norm of 8) must raise **nothing**. It did, once: v1 of this script
compared "основна" against the full МРЗ with no notion of part-time work at all, and
this exact row is what caught it before anyone else did.

Part 3 is a hand-built fixture for I5 (narrow) and B5, neither of which
test/generate_wide.py injects on its own, plus the partial-month gate B1/B5 both lean
on: a real office where nobody that month has a full, undiminished attendance would
make the "highest declared day-count on the sheet" proxy for "the month's working-day
norm" wrong too - so one row deliberately sits below the true norm here without being
underpaid, pinning that the gate does not fire on it regardless.

Part 1 also covers the insurable-income composition (F1/F9/F10's insurable-side, see
scripts/audit.py's docstring): F1_insurable_unexplained, F1_compensation_in_insurable
and F9_sick_pay_out_of_insurable never arise from the taxable side, so they are
compared against the manifest exactly, the same as I1/B4/F5. F10_in_kind_asymmetry and
F10_excess_asymmetry CAN also arise from the taxable side, which this script does not
compute (a future increment, see the docstring) - so those two are checked only for
false positives (every one raised must be in the manifest), not for an exact count.
That split was verified once, directly against test/structural_test.py's own
reference implementation rather than the manifest, across 300 seeds: zero mismatches
on the insurable side once the taxable-side occurrences were excluded from the
reference's own output.

The composition pass needs a mapping that declares every administrative/breakdown
column `generate_wide.py`'s canonical layout carries but `preflight.py`'s CONCEPTS does
not name (row numbers, department, the per-fund contribution breakdowns already summed
into a column CONCEPTS does recognise) - without it the pass's own safety gate (no
unrecognised columns at all) refuses to run, by design.
"""
import argparse
import os
import sys

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "skills", "trz-expert", "scripts"))

import audit as A                                              # noqa: E402
import generate_wide as GW                                      # noqa: E402
import preflight as PF                                         # noqa: E402

STATIC_FIXTURE = os.path.join(HERE, "vedomost_05_2026.xlsx")

# The administrative/breakdown columns generate_wide.py's canonical layout carries that
# preflight.py's CONCEPTS deliberately does not name (the per-fund breakdowns are
# already summed into columns CONCEPTS does recognise; the rest is never money at all).
# A real company's mapping.yaml plays the same role for its own layout.
WIDE_IGNORE = ["№", "Отдел", "Разлика", "ДОО пенсии", "ДОО ОЗМ", "ДОО безработица",
               "ЗО лична", "ДЗПО-УПФ лична", "ДЗПО-УПФ работодател", "ЗО работодател",
               "ЗО при болничен/майчинство", "Общ разход за труд",
               "Вноски работодател ДОО+ТЗПБ"]
WIDE_HDR = 5           # generate_wide.py's own header row constant


def _wide_mapping():
    return PF.Mapping({"kid": "62", "group": 3, "tzpb": 0.4, "ignore": WIDE_IGNORE})


failures = []


def fail(msg):
    failures.append(msg)
    print(f"FAIL {msg}")


# ------------------------------------------------------------- part 1: generate_wide
FILE_LEVEL_IDS = ("B4_cap_from_wrong_period", "F5_tzpb_below_due")
ROW_LEVEL_IDS = ("I1_vertical", "F1_insurable_unexplained",
                 "F1_compensation_in_insurable", "F9_sick_pay_out_of_insurable")
NO_FALSE_POSITIVE_IDS = ("F10_in_kind_asymmetry", "F10_excess_asymmetry")
# K2's recall is partial by design (see audit.py's module docstring: an amount that
# happens to be a whole number in a day column has no fractional-part signal to catch
# it), so a miss here is expected and not a failure - only a false positive is.
PARTIAL_RECALL_IDS = ("K2_amount_in_day_column",)


def run_wide(seeds):
    mapping = _wide_mapping()
    counts = {i: dict(tp=0, fn=0, fp=0) for i in FILE_LEVEL_IDS}
    row_counts = {i: dict(injected=0, found=0) for i in ROW_LEVEL_IDS}
    fp_counts = {i: 0 for i in NO_FALSE_POSITIVE_IDS}
    partial_counts = {i: dict(injected=0, found=0) for i in PARTIAL_RECALL_IDS}
    mismatches = []
    for seed in range(1, seeds + 1):
        try:
            path, _, man = GW.generate(seed, None, 2026)
            findings = A.check(path, mapping=mapping, tzpb=man["tzpb_due"])
        except Exception as exc:                              # noqa: BLE001
            mismatches.append(f"seed {seed}: exception {exc!r}")
            continue
        got_ids = {f["id"] for f in findings}
        expected_ids_at_row = {(WIDE_HDR + 1 + idx if where == "row" else "file", x)
                               for where, idx, x in man["expected"]}
        for i in NO_FALSE_POSITIVE_IDS:
            for f in findings:
                if f["id"] == i and (f["row"], i) not in expected_ids_at_row:
                    fp_counts[i] += 1
                    mismatches.append(f"seed {seed} {i} row {f['row']}: false "
                                      f"positive (not in the manifest at that row)")
        for i in FILE_LEVEL_IDS:
            injected = any(x == i for _, _, x in man["expected"])
            found = i in got_ids
            if injected and found:
                counts[i]["tp"] += 1
            elif injected and not found:
                counts[i]["fn"] += 1
                mismatches.append(f"seed {seed} {i}: missed")
            elif not injected and found:
                counts[i]["fp"] += 1
                mismatches.append(f"seed {seed} {i}: false positive")
        for i in ROW_LEVEL_IDS:
            exp_rows = sum(1 for _, _, x in man["expected"] if x == i)
            got_rows = sum(1 for f in findings if f["id"] == i)
            row_counts[i]["injected"] += exp_rows
            row_counts[i]["found"] += got_rows
            if exp_rows != got_rows:
                mismatches.append(f"seed {seed} {i}: expected {exp_rows}, "
                                  f"got {got_rows}")
        for i in PARTIAL_RECALL_IDS:
            exp_rows = {WIDE_HDR + 1 + idx for where, idx, x in man["expected"]
                       if where == "row" and x == i}
            got_rows = {f["row"] for f in findings if f["id"] == i}
            partial_counts[i]["injected"] += len(exp_rows)
            partial_counts[i]["found"] += len(exp_rows & got_rows)
            fp_rows = got_rows - exp_rows
            if fp_rows:
                mismatches.append(f"seed {seed} {i}: false positive at rows "
                                  f"{sorted(fp_rows)}")

        # B1/B5 have no generate_wide.py scenario - any finding here at all, across
        # a random fixture with random partial attendance, would be the false
        # positive part 2 exists to catch directly against a hand-checked row.
        for spurious_id in ("B1_below_minimum_wage", "B5_insurable_below_minimum_wage"):
            if spurious_id in got_ids:
                mismatches.append(f"seed {seed}: {spurious_id} fired with no "
                                  f"scenario injected for it")

    for i in FILE_LEVEL_IDS:
        c = counts[i]
        print(f"  {i:28s} tp={c['tp']:4d} fn={c['fn']:3d} fp={c['fp']:3d}")
    for i in ROW_LEVEL_IDS:
        c = row_counts[i]
        print(f"  {i:28s} injected={c['injected']:4d} found={c['found']:4d}")
    for i in NO_FALSE_POSITIVE_IDS:
        print(f"  {i:28s} false positives={fp_counts[i]:4d} (recall is partial by "
              f"design - see the module docstring)")
    for i in PARTIAL_RECALL_IDS:
        c = partial_counts[i]
        print(f"  {i:28s} injected={c['injected']:4d} found={c['found']:4d} "
              f"(a miss is expected here; a false positive is not)")

    if mismatches:
        for m in mismatches[:20]:
            fail(m)
        if len(mismatches) > 20:
            fail(f"... and {len(mismatches) - 20} more mismatches")
    else:
        print(f"  -> OK: I1/B4/F5/F1/F9(insurable) match the manifest exactly, "
              f"F10(insurable side) has zero false positives, K2 has zero false "
              f"positives (recall partial by design), B1/B5 silent, across {seeds} "
              f"seeds")


# --------------------------------------------------------- part 2: the static fixture
def run_static():
    if not os.path.exists(STATIC_FIXTURE):
        fail(f"{STATIC_FIXTURE} is missing - run test/generate_narrow.py first")
        return
    findings = A.check(STATIC_FIXTURE, kid="62", group="3", tzpb=0.4)
    by_row = {}
    for f in findings:
        by_row.setdefault(f["row"], set()).add(f["id"])

    expected = {
        6: {"B1_below_minimum_wage"},
        9: {"B4_cap_from_wrong_period"},
    }
    for row, ids in expected.items():
        got = by_row.get(row, set())
        if got != ids:
            fail(f"suite-1 row {row}: expected {ids}, got {got or '{}'}")
        else:
            print(f"  ok   row {row:2d} -> {sorted(ids)}")

    # Стефка Ангелова, row 13: part-time, 4 hours against 8 full-time. Documented in
    # expected_findings.md as "Everything correct. Must produce no finding." - and
    # the exact row that caught v1 of this script comparing "основна" against the
    # full МРЗ with no notion of part-time work.
    if 13 in by_row:
        fail(f"suite-1 row 13 (documented part-time, correct): raised {by_row[13]}")
    else:
        print("  ok   row 13 (part-time, correct) -> nothing")


# ------------------------------------------------------- part 3: hand-built fixture
HEADERS = ["Име", "Отраб. дни", "Основна за отработеното", "БРУТО",
           "Осигурителен доход", "Данъчна основа", "ДДФЛ", "Лични вноски общо",
           "НЕТО преди удръжки", "НЕТО за изплащане", "Дни болничен",
           "Болнични (работодател)",
           # The insurable-income composition (F1/F9/F10) refuses to run at all
           # unless every one of COMPOSITION_CONCEPTS is a recognised column (see
           # audit.py's module docstring) - added zero-valued here so the
           # composition pass engages for every shape below, not only a
           # dedicated one, the same way a real file's columns are all present
           # whether or not a given row uses them.
           "Клас сума", "Бонус", "Платен отпуск", "Обезщетение чл. 224",
           "Карта (за сметка на работодателя)",
           "Доброволно здравно осигуряване (премия)"]
# Everyone this month took at least a little leave or sick time - nobody has the true
# 22-day calendar norm, so the highest count on the sheet (20) is itself partial. Row
# 3 sits at 20 with основна scaled down for it, correctly, and must not be flagged.
# Five of the six composition columns are zero for everyone; Лице 2 carries a real,
# non-zero Клас сума (50.00, an always-in element, never one of CONTESTED) so the
# composition pass is proven to add a genuine element correctly, not only to match
# trivially on an all-zero row. Осигурителен доход for that row is 1000.00 =
# основна (950.00) + клас (50.00) - I1 never reads Осигурителен доход, so this does
# not need a matching change to БРУТО/данъчна основа/данък/нето. No shape below
# touches Лице 2, so this stays untouched and correct in every shape, including clean.
ROWS = [
    ["Лице 1", 18, 900.00, 900.00, 900.00, 810.00, 81.00, 90.00, 729.00, 729.00, 0, 0.00,
     0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
    ["Лице 2", 19, 950.00, 950.00, 1000.00, 855.00, 85.50, 95.00, 769.50, 769.50, 0, 0.00,
     50.00, 0.00, 0.00, 0.00, 0.00, 0.00],
    ["Лице 3", 20, 1127.45, 1127.45, 1127.45, 1014.70, 101.47, 112.75, 913.23, 913.23, 0, 0.00,
     0.00, 0.00, 0.00, 0.00, 0.00, 0.00],
]
HEADER_ROW = 1


def build(path, mutate=None):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "06.2026"
    for c, h in enumerate(HEADERS, start=1):
        ws.cell(HEADER_ROW, c, h)
    for i, row in enumerate(ROWS):
        for c, v in enumerate(row, start=1):
            ws.cell(HEADER_ROW + 1 + i, c, v)
    if mutate:
        mutate(ws)
    wb.save(path)
    return path


def s_i5_sick_pay_without_days(ws):
    """Sick pay accrued, zero sick days recorded - the narrow I5 shape.

    Since the composition columns went live, this same edit is also a genuine
    F9: the accrual sits outside Осигурителен доход, which never moved. The two
    are not independent violations - if the accrual is legitimate the days are
    wrong (F9 is real, I5 names why); if the accrual is bogus, removing it would
    clear both - but they are independent OBSERVATIONS a human auditor needs
    both of, and fixing one does not silently fix the finding for the other, so
    SHAPES expects both rather than pretending this edit only ever meant one
    thing.
    """
    name_row = HEADER_ROW + 1
    ws.cell(name_row, HEADERS.index("Болнични (работодател)") + 1, 45.00)
    # Дни болничен stays 0


def s_b5_insurable_below_min_wage(ws):
    """Insurable income below the minimum wage, full attendance - a real B5.

    Дropping Осигурителен доход to 500.00 while основна (1127.45) and every
    composition column stay put also makes the row's own composition
    unexplainable - a real file with income this far below the norm would
    fail both checks, so F1_insurable_unexplained is expected here too.
    """
    row = HEADER_ROW + 3        # Лице 3, the one with full (highest) attendance
    ws.cell(row, HEADERS.index("Осигурителен доход") + 1, 500.00)


def s_f9_sick_pay_out_of_insurable(ws):
    """Sick pay from the employer (чл. 40, ал. 5 КСО), correctly logged with sick
    days > 0 - unlike s_i5_sick_pay_without_days, this is not a zero-days
    contradiction - but Осигурителен доход is left unchanged, so it does not carry
    the accrual. чл. 3, ал. 1 НЕВДПОВ puts sick pay inside insurable income
    unconditionally: no majority-practice inference is needed, unlike the contested
    elements (доход в натура, превишение), so this fires even alone in the sheet.

    Hand-verified: work_base for Лице 1 is основна (900.00) plus the six
    zero-valued composition columns, i.e. 900.00. With болнични = 45.00 correctly
    inside, insurable income should be 945.00; the sheet still states 900.00 - the
    exact 45.00 gap `audit.py`'s "removed" branch is built to explain.
    """
    row = HEADER_ROW + 1        # Лице 1
    ws.cell(row, HEADERS.index("Болнични (работодател)") + 1, 45.00)
    ws.cell(row, HEADERS.index("Дни болничен") + 1, 3)
    # Осигурителен доход stays at 900.00 - excludes the sick pay


def s_k2_amount_in_day_column(ws):
    """An amount typed into "Дни болничен" instead of a day count - the fractional
    part (.32) is the signal; Болнични (работодател) stays 0, so I5 does not also
    fire (that check needs a nonzero amount there, which this shape has none of).
    """
    row = HEADER_ROW + 3        # Лице 3
    ws.cell(row, HEADERS.index("Дни болничен") + 1, 45.32)


def s_i8_duplicated_person(ws):
    """Лице 2's row becomes an exact copy of Лице 1's - every column, not only
    name/бруто/осиг.доход/нето, so the row stays internally consistent (I1 would
    otherwise fire on a name+pay copied from one person with deductions left from
    another). This is the shape a copy-pasted row actually makes.
    """
    src, dst = HEADER_ROW + 1, HEADER_ROW + 2        # Лице 1 -> Лице 2
    for c in range(1, len(HEADERS) + 1):
        ws.cell(dst, c, ws.cell(src, c).value)


def s_i8_same_name_different_pay(ws):
    """Лице 2 gets Лице 1's name but keeps its OWN pay - two different employees who
    happen to share a name, not a copied row. Must NOT fire I8: audit.py requires
    бруто/осиг.доход/нето to also match, not the name alone.
    """
    src, dst = HEADER_ROW + 1, HEADER_ROW + 2
    ws.cell(dst, HEADERS.index("Име") + 1, ws.cell(src, HEADERS.index("Име") + 1).value)


SHAPES = {
    None: {},
    "s_i5_sick_pay_without_days": {A.I5_SICK_PAY_WITHOUT_DAYS: 1,
                                   A.F9_SICK_PAY_OUT_OF_INSURABLE: 1},
    "s_b5_insurable_below_min_wage": {A.B5_INSURABLE_BELOW_MIN_WAGE: 1,
                                      A.F1_INSURABLE_UNEXPLAINED: 1},
    "s_f9_sick_pay_out_of_insurable": {A.F9_SICK_PAY_OUT_OF_INSURABLE: 1},
    "s_k2_amount_in_day_column": {A.K2_AMOUNT_IN_DAY_COLUMN: 1},
    "s_i8_duplicated_person": {A.I8_DUPLICATED_PEOPLE: 1},
    "s_i8_same_name_different_pay": {},
}

# Which figures must appear (as "%.2f") in the text of a given id's finding, for a
# given shape - not just that the id fired, but that it named the right numbers.
# {shape: {id: [figures]}}. Pins the arithmetic hand-computed in each shape's own
# docstring, which the count-only check above cannot: deleting a composition column
# from work_base left every count in SHAPES unchanged while the wrong number was
# reported (proved by sabotage, see the PR this was added in).
EXPECTED_TEXT = {
    # Fires via the "removed" branch (audit.py: expected_insurable minus el[k] equals
    # the stated insurable income) - that branch's text names only el[k], not the
    # insurable figure itself.
    "s_i5_sick_pay_without_days": {
        A.F9_SICK_PAY_OUT_OF_INSURABLE: [45.00]},
    "s_b5_insurable_below_min_wage": {
        A.F1_INSURABLE_UNEXPLAINED: [500.00, 1127.45]},
    "s_f9_sick_pay_out_of_insurable": {
        A.F9_SICK_PAY_OUT_OF_INSURABLE: [45.00]},
    "s_k2_amount_in_day_column": {
        A.K2_AMOUNT_IN_DAY_COLUMN: [45.32]},
}


def run_hand_built(tmpdir):
    for name, expected in SHAPES.items():
        path = os.path.join(tmpdir, f"{name or 'clean'}.xlsx")
        build(path, mutate=globals()[name] if name else None)
        findings = A.check(path, kid="62", group="3", tzpb=0.4)
        got = {}
        for f in findings:
            got[f["id"]] = got.get(f["id"], 0) + 1
        label = name or "clean"
        if got != expected:
            fail(f"{label}: expected {expected or '{}'}, got {got or '{}'}")
            continue
        for ident, figures in EXPECTED_TEXT.get(name, {}).items():
            texts = [f["text"] for f in findings if f["id"] == ident]
            for figure in figures:
                needle = f"{figure:.2f}"
                if not any(needle in t for t in texts):
                    fail(f"{label}: {ident}'s finding text does not carry {needle} - "
                        f"got {texts}")
        print(f"ok   {label:32s} -> {got or 'nothing'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=60)
    a = ap.parse_args()

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        run_hand_built(tmp)
    print()
    run_static()
    print()
    run_wide(a.seeds)

    print("=" * 78)
    if failures:
        print(f"FAILED: {len(failures)} check(s)")
        sys.exit(1)
    print("OK: I1/B4/F5 match generate_wide.py's manifest exactly, the suite-1 "
          "fixture matches expected_findings.md including the part-time row that "
          "must stay silent, and the hand-built shapes for I5/B5/F9/I8 each fire "
          "once with the right figures")
