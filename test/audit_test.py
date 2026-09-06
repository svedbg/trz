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

STATIC_FIXTURE = os.path.join(HERE, "vedomost_05_2026.xlsx")

failures = []


def fail(msg):
    failures.append(msg)
    print(f"FAIL {msg}")


# ------------------------------------------------------------- part 1: generate_wide
FILE_LEVEL_IDS = ("B4_cap_from_wrong_period", "F5_tzpb_below_due")
ROW_LEVEL_IDS = ("I1_vertical",)


def run_wide(seeds):
    counts = {i: dict(tp=0, fn=0, fp=0) for i in FILE_LEVEL_IDS}
    row_counts = {i: dict(injected=0, found=0) for i in ROW_LEVEL_IDS}
    mismatches = []
    for seed in range(1, seeds + 1):
        try:
            path, _, man = GW.generate(seed, None, 2026)
            findings = A.check(path, kid="62", group="3", tzpb=man["tzpb_due"])
        except Exception as exc:                              # noqa: BLE001
            mismatches.append(f"seed {seed}: exception {exc!r}")
            continue
        got_ids = {f["id"] for f in findings}
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

    if mismatches:
        for m in mismatches[:20]:
            fail(m)
        if len(mismatches) > 20:
            fail(f"... and {len(mismatches) - 20} more mismatches")
    else:
        print(f"  -> OK: I1/B4/F5 match the manifest exactly, B1/B5 silent, across "
              f"{seeds} seeds")


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
           "Болнични (работодател)"]
# Everyone this month took at least a little leave or sick time - nobody has the true
# 22-day calendar norm, so the highest count on the sheet (20) is itself partial. Row
# 3 sits at 20 with основна scaled down for it, correctly, and must not be flagged.
ROWS = [
    ["Лице 1", 18, 900.00, 900.00, 900.00, 810.00, 81.00, 90.00, 729.00, 729.00, 0, 0.00],
    ["Лице 2", 19, 950.00, 950.00, 950.00, 855.00, 85.50, 95.00, 769.50, 769.50, 0, 0.00],
    ["Лице 3", 20, 1127.45, 1127.45, 1127.45, 1014.70, 101.47, 112.75, 913.23, 913.23, 0, 0.00],
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
    """Sick pay accrued, zero sick days recorded - the narrow I5 shape."""
    name_row = HEADER_ROW + 1
    ws.cell(name_row, HEADERS.index("Болнични (работодател)") + 1, 45.00)
    # Дни болничен stays 0


def s_b5_insurable_below_min_wage(ws):
    """Insurable income below the minimum wage, full attendance - a real B5."""
    row = HEADER_ROW + 3        # Лице 3, the one with full (highest) attendance
    ws.cell(row, HEADERS.index("Осигурителен доход") + 1, 500.00)


SHAPES = {
    None: {},
    "s_i5_sick_pay_without_days": {A.I5_SICK_PAY_WITHOUT_DAYS: 1},
    "s_b5_insurable_below_min_wage": {A.B5_INSURABLE_BELOW_MIN_WAGE: 1},
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
        else:
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
          "must stay silent, and the hand-built shapes for I5/B5 each fire once")
