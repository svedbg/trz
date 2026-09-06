# -*- coding: utf-8 -*-
"""Proves tools/k_checker.py has teeth: clean is silent, K5 and K6 each found once.

A self-contained fixture rather than test/generate_shapes.py's: K5 and K6 are checked
from *values*, never formulas, so the fixture needs no formula caching at all - every
cell, including the totals row, is a plain number chosen to already be self-consistent.
That is also the honest shape of a real export with no formulas left in it, which is
exactly the file group K exists to still be able to check.
"""
import os
import sys

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import k_checker as KC                                        # noqa: E402

HEADERS = ["Име", "Отраб. дни", "Основна за отработеното", "Клас сума", "БРУТО",
           "Осигурителен доход", "Данъчна основа", "ДДФЛ", "Лични вноски общо",
           "НЕТО за изплащане"]
ROWS = [
    ["Лице 1", 21, 1000.00, 50.00, 1050.00, 1050.00, 945.00, 94.50, 105.00, 850.50],
    ["Лице 2", 18, 1200.00, 96.00, 1296.00, 1296.00, 1166.40, 116.64, 129.60, 1049.76],
    ["Лице 3", 21, 900.00, 18.00, 918.00, 918.00, 826.20, 82.62, 91.80, 743.58],
]
HEADER_ROW = 1

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
        ws.cell(totals_row, c, round(sum(row[c - 1] for row in ROWS), 2))
    if mutate:
        mutate(ws, totals_row)
    wb.save(path)
    return path


def s_k5_total_not_sum(ws, totals_row):
    col = HEADERS.index("НЕТО за изплащане") + 1
    ws.cell(totals_row, col, ws.cell(totals_row, col).value + 1.00)


def s_k6_unrounded_accrual(ws, totals_row):
    col = HEADERS.index("Клас сума") + 1
    old = ws.cell(HEADER_ROW + 1, col).value
    new = 63.87696
    ws.cell(HEADER_ROW + 1, col, new)
    ws.cell(totals_row, col, round(ws.cell(totals_row, col).value - old + new, 6))


SHAPES = {
    None: set(),
    "s_k5_total_not_sum": {KC.K5_TOTAL_NOT_SUM},
    "s_k6_unrounded_accrual": {KC.K6_UNROUNDED_ACCRUAL},
}


def run(tmpdir):
    for name, expected in SHAPES.items():
        path = os.path.join(tmpdir, f"{name or 'clean'}.xlsx")
        build(path, mutate=globals()[name] if name else None)
        findings = KC.check(path)
        got = {f["id"] for f in findings}
        label = name or "clean"
        if got != expected:
            fail(f"{label}: expected {expected or '{}'}, got {got or '{}'}")
        else:
            print(f"ok   {label:24s} -> {sorted(got) or 'nothing'}")

    # the report renders without raising, for both the silent and the found case
    clean_path = os.path.join(tmpdir, "clean.xlsx")
    KC.report(clean_path, KC.check(clean_path))
    dirty_path = os.path.join(tmpdir, "s_k5_total_not_sum.xlsx")
    text = KC.report(dirty_path, KC.check(dirty_path))
    if "K5" not in text:
        fail("report() does not mention K5 for a workbook with a K5 finding")


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        run(tmp)
    print("=" * 78)
    if failures:
        print(f"FAILED: {len(failures)} check(s)")
        sys.exit(1)
    print("OK: clean is silent, K5 and K6 are each found exactly once, nothing else "
          "is raised")
