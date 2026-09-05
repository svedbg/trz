#!/usr/bin/env python3
"""Tests for tools/preflight.py - the pre-flight check that runs before an audit.

Standalone, like skill_test.py: run it directly, not through run_tests.py, which owns
the five generated suites and says so in four places.

The proving standard is the repository's: a shape defect is planted on purpose and the
check has to find it. Every fixture here is built in memory from invented data - no real
payroll, no personal data, nothing written outside a temporary directory.

    python test/preflight_test.py
"""

import os
import shutil
import sys
import tempfile

import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)

import preflight as P                                          # noqa: E402
import trz_model as M                                          # noqa: E402

FAILURES = []


def check(condition, message):
    print(("  ok   " if condition else "  FAIL ") + message)
    if not condition:
        FAILURES.append(message)


def build(path, headers, rows, sheet="05.2026", header_row=1, totals=True,
          formulas=False, merged=None):
    """A minimal workbook with the shape asked for. Values are invented."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    for c, h in enumerate(headers, start=1):
        ws.cell(header_row, c, h)
    r = header_row
    for r, row in enumerate(rows, start=header_row + 1):
        for c, v in enumerate(row, start=1):
            ws.cell(r, c, v)
    if formulas:
        # A gross column that is actually computed, so formula coverage is non-zero.
        gross = headers.index("БРУТО") + 1
        for rr in range(header_row + 1, r + 1):
            ws.cell(rr, gross, f"=C{rr}")
    if totals:
        ws.cell(r + 1, 1, "Общо")
    for rng in (merged or []):
        ws.merge_cells(rng)
    wb.save(path)
    return path


HEADERS = ["Име", "Отраб. дни", "Основна за отработеното", "БРУТО",
           "Осигурителен доход", "Данъчна основа", "ДДФЛ", "Лични вноски общо",
           "НЕТО за изплащане"]
ROWS = [["Лице 1", 21, 1000.0, 1000.0, 1000.0, 900.0, 90.0, 100.0, 810.0],
        ["Лице 2", 21, 1200.0, 1200.0, 1200.0, 1080.0, 108.0, 120.0, 972.0]]


def main():
    tmp = tempfile.mkdtemp(prefix="preflight-test-")
    try:
        print("Pre-flight check")
        print("=" * 78)

        # ---------------------------------------------------------- vocabulary drift
        # Every canonical header the generated payrolls use must still be recognised, or
        # a rename in trz_model.py silently sends real columns to the unknown list.
        wanted = {"Име", "Отраб. дни", "Основна за отработеното", "Клас сума", "БРУТО",
                  "Осигурителен доход", "Данъчна основа", "ДДФЛ", "Лични вноски общо",
                  "НЕТО за изплащане", "Изплатено", "Дни болничен",
                  "Болнични (работодател)", "Вноски работодател общо"}
        missing = sorted(w for w in wanted if w not in M.COLUMNS)
        check(not missing, f"the canonical names this test pins still exist in "
                           f"trz_model.COLUMNS{' - missing ' + str(missing) if missing else ''}")
        unrecognised = sorted(w for w in wanted if P.classify(w) is None)
        check(not unrecognised,
              f"preflight recognises every canonical column it depends on"
              f"{' - not ' + str(unrecognised) if unrecognised else ''}")

        # Real-world spellings the token pass exists for.
        check(P.classify("Болнични от работодател") == "болнични",
              "„Болнични от работодател“ maps to the sick-pay concept")
        check(P.classify("Брутно възнаграждение") == "бруто",
              "„Брутно възнаграждение“ maps to gross")
        check(P.classify("Отдел") is None, "an unrelated header stays unknown")

        # ------------------------------------------------------------- the happy path
        good = build(os.path.join(tmp, "ok.xlsx"), HEADERS, ROWS, formulas=True)
        data = P.scan(good, kid="62", group="3", tzpb="0.4")
        s = data["sheets"][0]
        check(s["header_row"] == 1, "header row found")
        check(s["rows"] == 2, f"two data rows counted, got {s['rows']}")
        check(s["totals_row"] == 4, f"totals row found at 4, got {s['totals_row']}")
        check(s["period"] == (2026, 5), f"period read from the tab, got {s['period']}")
        check(s["formula_cells"] > 0, "formulas detected when present")
        text, blocking = P.report(data)
        check(not blocking, f"a well-formed file does not block, got {blocking}")
        check("не е променян" in text, "the report states the file was not modified")
        check("Лице 1" not in text, "no cell value from the name column reaches the report")

        # -------------------------------------------------------- planted shape defects
        # Each one is the reason a real audit stalls, and each must be caught.
        vals = build(os.path.join(tmp, "values.xlsx"), HEADERS, ROWS, formulas=False)
        t, _ = P.report(P.scan(vals))
        check("няма нито една формула" in t,
              "a values-only export is called out, so the K group is not claimed")

        no_period = build(os.path.join(tmp, "nop.xlsx"), HEADERS, ROWS, sheet="Лист1")
        t, b = P.report(P.scan(no_period))
        check(any("период" in x for x in b),
              "an unlabelled period blocks rather than being guessed from the numbers")

        thin = build(os.path.join(tmp, "thin.xlsx"), ["A", "B", "C"],
                     [[1, 2, 3]], sheet="05.2026")
        t, b = P.report(P.scan(thin))
        check(any("заглавен ред" in x for x in b),
              "a sheet with no recognisable header row blocks")

        short = build(os.path.join(tmp, "short.xlsx"), HEADERS[:4], [r[:4] for r in ROWS])
        t, b = P.report(P.scan(short))
        check(any("Осигурителен" in x or "осиг" in x for x in b),
              "a missing required column blocks and is named")
        check("F1" in t or "B3" in t,
              "the report says which checks the missing column costs")

        no_totals = build(os.path.join(tmp, "nt.xlsx"), HEADERS, ROWS, totals=False)
        t, _ = P.report(P.scan(no_totals))
        check("ред с общи суми не е намерен" in t, "a missing totals row is reported")

        mg = build(os.path.join(tmp, "merged.xlsx"), HEADERS, ROWS, merged=["A2:B2"])
        t, _ = P.report(P.scan(mg))
        check("слети клетки" in t, "merged cells inside the data range are reported")

        # ------------------------------------------------------- boundaries from stavki
        bounds = P.regime_boundaries()
        check(len(bounds) >= 2,
              f"period boundaries are read from stavki.md, got {len(bounds)}")
        mid = [a for a, _ in bounds if (a.month, a.day) != (1, 1)]
        check(bool(mid), "at least one mid-year boundary is known, so K8 can be warned")
        if mid:
            a = max(mid)
            aug = build(os.path.join(tmp, "aug.xlsx"), HEADERS, ROWS,
                        sheet=f"{a.month:02d}.{a.year}")
            t, _ = P.report(P.scan(aug))
            check("средата на годината" in t,
                  f"a sheet dated {a:%m.%Y} is warned about the mid-year threshold change")

        # ---------------------------------------------------------- it never writes
        before = os.path.getmtime(good), os.path.getsize(good)
        P.scan(good)
        check((os.path.getmtime(good), os.path.getsize(good)) == before,
              "scanning does not touch the workbook")

        print("=" * 78)
        if FAILURES:
            print(f"FAILED: {len(FAILURES)} check(s)")
            return 1
        print("OK: pre-flight reads the shape, names what is missing, writes nothing")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
