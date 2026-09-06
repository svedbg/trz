# -*- coding: utf-8 -*-
"""Proves tools/k_checker.py has teeth, two ways.

Part 1 is a self-contained fixture rather than test/generate_shapes.py's: K5 and K6 are
checked from *values*, never formulas, so the fixture needs no formula caching at all -
every cell, including the totals row, is a plain number chosen to already be
self-consistent. It also pins the two 2.14.0 regressions directly: one shape plants K5
in a column outside tools/preflight.py's concept vocabulary (0 of 28 found against real
fixtures before the fix), another plants an unrounded value that flows into a second,
known-concept column the way a class supplement flows into gross (found twice before
the fix - a cause and its consequence counted as two findings, which otchet.md and
test/structural_test.py both forbid).

Part 2 runs the checker against test/generate_wide.py's actual injected fixtures across
many seeds and compares the count against the manifest, the way structural_test.py does
for the model's own checks - no less, no more.

    python test/k_checker_test.py               # both parts, 60 wide seeds
    python test/k_checker_test.py --seeds 300    # CI's depth
"""
import argparse
import os
import sys

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import k_checker as KC                                        # noqa: E402
import generate_wide as GW                                     # noqa: E402

HEADERS = ["Име", "Отраб. дни", "Основна за отработеното", "Клас сума", "БРУТО",
           "Осигурителен доход", "Данъчна основа", "ДДФЛ", "Лични вноски общо",
           "НЕТО за изплащане", "Карта (за сметка на работодателя)", "Клас %"]
ROWS = [
    ["Лице 1", 21, 1000.00, 50.00, 1050.00, 1050.00, 945.00, 94.50, 105.00, 850.50, 40.00, 5.0],
    ["Лице 2", 18, 1200.00, 96.00, 1296.00, 1296.00, 1166.40, 116.64, 129.60, 1049.76, 40.00, 8.0],
    ["Лице 3", 21, 900.00, 18.00, 918.00, 918.00, 826.20, 82.62, 91.80, 743.58, 40.00, 2.0],
]
HEADER_ROW = 1
# Left out of the totals row's default per-column sum, the way a real export leaves it:
# a percentage column's total is not one more sum, it just isn't sensible as one.
NOT_SUMMED = {"Клас %"}

failures = []


def fail(msg):
    failures.append(msg)
    print(f"FAIL {msg}")


def build(path, mutate=None):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "05.2026"
    for c, h in enumerate(HEADERS, start=1):
        ws.cell(HEADER_ROW, c, h)
    for i, row in enumerate(ROWS):
        for c, v in enumerate(row, start=1):
            ws.cell(HEADER_ROW + 1 + i, c, v)
    totals_row = HEADER_ROW + 1 + len(ROWS)
    ws.cell(totals_row, 1, "Общо")
    for c in range(2, len(HEADERS) + 1):
        if HEADERS[c - 1] in NOT_SUMMED:
            continue
        ws.cell(totals_row, c, round(sum(row[c - 1] for row in ROWS), 2))
    if mutate:
        mutate(ws, totals_row)
    wb.save(path)
    return path


def s_k5_total_not_sum(ws, totals_row):
    """K5 in a *known* concept column - the 2.14.0 fixture, kept as a baseline."""
    col = HEADERS.index("НЕТО за изплащане") + 1
    ws.cell(totals_row, col, ws.cell(totals_row, col).value + 1.00)


def s_k5_unknown_column(ws, totals_row):
    """K5 in a column tools/preflight.py's CONCEPTS does not name at all.

    „Карта (за сметка на работодателя)" classifies to no concept - exactly the shape
    that went 0 for 28 against test/generate_wide.py's fixtures in 2.14.0, because the
    check walked only the known-concept columns.
    """
    col = HEADERS.index("Карта (за сметка на работодателя)") + 1
    ws.cell(totals_row, col, ws.cell(totals_row, col).value + 5.00)


def s_k6_unrounded_accrual(ws, totals_row):
    """K6 alone: the unrounded cell does not flow anywhere else on this fixture."""
    col = HEADERS.index("Клас сума") + 1
    old = ws.cell(HEADER_ROW + 1, col).value
    new = 63.87696
    ws.cell(HEADER_ROW + 1, col, new)
    ws.cell(totals_row, col, round(ws.cell(totals_row, col).value - old + new, 6))


def s_k6_chains_into_gross(ws, totals_row):
    """The same unrounded class supplement, now also carried into БРУТО.

    Real files compute gross from the columns feeding it, so an unrounded component is
    visible in two columns for the same row - one defect, and 2.14.0 counted it as two
    K6 findings.
    """
    klas_col = HEADERS.index("Клас сума") + 1
    gross_col = HEADERS.index("БРУТО") + 1
    old_klas = ws.cell(HEADER_ROW + 1, klas_col).value
    old_gross = ws.cell(HEADER_ROW + 1, gross_col).value
    new_klas = 63.87696
    delta = new_klas - old_klas
    ws.cell(HEADER_ROW + 1, klas_col, new_klas)
    ws.cell(HEADER_ROW + 1, gross_col, old_gross + delta)
    ws.cell(totals_row, klas_col,
            round(ws.cell(totals_row, klas_col).value + delta, 6))
    ws.cell(totals_row, gross_col,
            round(ws.cell(totals_row, gross_col).value + delta, 6))


def s_k5_percent_average_is_not_a_defect(ws, totals_row):
    """A real layout's totals row holds the *average* of a percentage column, not
    its sum - the 2.14.1 false positive. Walking every header for K5 (the fix for
    s_k5_unknown_column, above) made a percentage column eligible for the same sum
    check as any other, and a hand-typed average then read as K5.
    """
    col = HEADERS.index("Клас %") + 1
    values = [row[col - 1] for row in ROWS]
    ws.cell(totals_row, col, round(sum(values) / len(values), 2))


SHAPES = {
    None: {},
    "s_k5_total_not_sum": {KC.K5_TOTAL_NOT_SUM: 1},
    "s_k5_unknown_column": {KC.K5_TOTAL_NOT_SUM: 1},
    "s_k5_percent_average_is_not_a_defect": {},
    "s_k6_unrounded_accrual": {KC.K6_UNROUNDED_ACCRUAL: 1},
    "s_k6_chains_into_gross": {KC.K6_UNROUNDED_ACCRUAL: 1},   # one row, not two columns
}


def run_fixture(tmpdir):
    for name, expected in SHAPES.items():
        path = os.path.join(tmpdir, f"{name or 'clean'}.xlsx")
        build(path, mutate=globals()[name] if name else None)
        findings = KC.check(path)
        got = {}
        for f in findings:
            got[f["id"]] = got.get(f["id"], 0) + 1
        label = name or "clean"
        if got != expected:
            fail(f"{label}: expected {expected or '{}'}, got {got or '{}'}")
        else:
            print(f"ok   {label:24s} -> {got or 'nothing'}")

    # the report renders without raising, for both the silent and the found case
    clean_path = os.path.join(tmpdir, "clean.xlsx")
    KC.report(clean_path, KC.check(clean_path))
    dirty_path = os.path.join(tmpdir, "s_k5_total_not_sum.xlsx")
    text = KC.report(dirty_path, KC.check(dirty_path))
    if "K5" not in text:
        fail("report() does not mention K5 for a workbook with a K5 finding")


def run_wide(seeds):
    """K5/K6 counts against test/generate_wide.py's manifest, seeds 1..seeds.

    No less, no more: a seed's expected K5/K6 count is exactly how many the manifest
    says were injected, and any count the checker reports for the other id is a false
    positive on this seed.
    """
    ids = (KC.K5_TOTAL_NOT_SUM, KC.K6_UNROUNDED_ACCRUAL)
    mismatches = []
    injected = {i: 0 for i in ids}
    found = {i: 0 for i in ids}
    for seed in range(1, seeds + 1):
        try:
            path, _, man = GW.generate(seed, None, 2026)
            expected = {i: sum(1 for _, _, ident in man["expected"] if ident == i)
                        for i in ids}
            got = {i: 0 for i in ids}
            for f in KC.check(path):
                if f["id"] in got:
                    got[f["id"]] += 1
        except Exception as exc:                              # noqa: BLE001
            mismatches.append(f"seed {seed}: exception {exc!r}")
            continue
        for i in ids:
            injected[i] += expected[i]
            found[i] += got[i]
            if expected[i] != got[i]:
                mismatches.append(f"seed {seed} {i}: expected {expected[i]}, "
                                  f"got {got[i]}")
    for i in ids:
        print(f"  {i:24s} injected: {injected[i]:4d}  found: {found[i]:4d}")
    if mismatches:
        for m in mismatches[:20]:
            fail(m)
        if len(mismatches) > 20:
            fail(f"... and {len(mismatches) - 20} more mismatches")
    else:
        print(f"  -> OK: K5 and K6 match test/generate_wide.py's manifest exactly "
              f"across {seeds} seeds")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=60)
    a = ap.parse_args()

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        run_fixture(tmp)
    print()
    run_wide(a.seeds)

    print("=" * 78)
    if failures:
        print(f"FAILED: {len(failures)} check(s)")
        sys.exit(1)
    print("OK: clean is silent, K5 and K6 are each found exactly once per defect, "
          "and match generate_wide.py's manifest exactly")
