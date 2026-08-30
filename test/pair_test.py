# -*- coding: utf-8 -*-
"""Suite 3: the cross-month checks, over a two-sheet payroll.

    python test/pair_test.py --seed 7
    python test/pair_test.py --seed 7 --quiet

`generate_pair.py` builds July and August 2026 into one workbook with one roster, and
breaks the things that can only be broken across months. This file has to find exactly
those and nothing else.

People are identified by row, never by name, as in `structural_test.py`. The names in
these fixtures are invented, but the report is the part a person pastes into an issue, and
a row number carries the same information.

The I7 finding prints no figures. Its evidence is a pay figure rather than a discrepancy
in one - the same row implying two different monthly bases - and writing that to stdout is
clear-text logging of exactly the kind CodeQL flags, whatever the data behind it happens
to be. The two amounts stay in the returned finding, so nothing driving the suite loses
them; they are simply not printed. Reproduce a case with its seed and the numbers are one
`--seed` away.

Everything here is derived from the two sheets, never from the manifest. The manifest is
opened once, at the end, to score the run. That is not fastidiousness: the checks are
meant to be the ones a person could perform with the file alone, and a check that quietly
reads the answer key proves nothing about the file.

Two of the three checks turn on a distinction worth stating. The norm of a sheet - how
many days it was built on - is not the same as the norm of its month. When a sheet is
copied forward, the first stops following the second, and every row then reconciles
perfectly against a month that is not its own. So the norm is *derived* from the day
sums and then compared with the calendar; deriving it from the calendar instead would
turn one file-level defect into a row-level finding against every person on the sheet.
"""
import argparse
import json
import os
import sys
from collections import Counter

import openpyxl

import trz_model as M
from trz_model import r2

HERE = os.path.dirname(os.path.abspath(__file__))
TOL = 0.02
SALARY_TOL = 1.00        # a month's rounding moves an implied salary by a few cents


class Findings:
    def __init__(self):
        self.items = []
        self._seen = set()

    def add(self, ident, where, text, stated=None, due=None, figures=True):
        """`figures=False` keeps the two amounts out of the printed report.

        They stay in the returned finding, so the suite and anything driving it still
        have them; what changes is that they are not written to stdout. See the note in
        the module docstring - this is the one finding whose evidence is a pay figure
        rather than a discrepancy in one.
        """
        if (where, ident) in self._seen:
            return
        self._seen.add((where, ident))
        self.items.append(dict(id=ident, where=where, text=text, stated=stated, due=due,
                               figures=figures))

    def keys(self):
        return {(f["where"], f["id"]) for f in self.items}


def read_sheet(ws):
    """Every row of one sheet, by column name, plus the header and total row numbers."""
    hdr = next(r for r in range(1, 12)
               if ws.cell(row=r, column=1).value == "№")
    col = {ws.cell(row=hdr, column=c).value: c for c in range(1, ws.max_column + 1)}
    rows = []
    r = hdr + 1
    while ws.cell(row=r, column=col["Име"]).value not in (None, "", "ОБЩО"):
        v = {}
        for name, c in col.items():
            if name is None:
                continue
            value = ws.cell(row=r, column=c).value
            v[name] = 0.0 if value in (None, "") and name not in ("Име", "Отдел") else value
        v["_row"] = r
        rows.append(v)
        r += 1
    return hdr, r, rows


def derived_norm(rows):
    """The number of days the sheet was actually built on.

    The day columns of a correct sheet sum to the month's norm on every row. Taking the
    most common sum recovers that figure from the file, which is the only way to notice
    that it belongs to a different month.
    """
    sums = Counter(r2(sum(row[c] for c in M.DAY_COLUMNS)) for row in rows)
    return sums.most_common(1)[0][0]


def implied_salary(row, sheet_norm):
    """The monthly salary the row implies: daily rate scaled back up to the month."""
    worked = row["Отраб. дни"]
    return None if not worked else row["Основна за отработеното"] / worked * sheet_norm


def work_pay(row):
    return r2(row["Основна за отработеното"] + row["Клас сума"]
              + row["Бонус"] + row["Платен отпуск"])


def check(xlsx, manifest, quiet=False):
    wb = openpyxl.load_workbook(xlsx, data_only=True)
    early_name, late_name = wb.sheetnames[0], wb.sheetnames[1]
    _, _, early = read_sheet(wb[early_name])
    late_hdr, _, late = read_sheet(wb[late_name])

    early_month, early_year = (int(x) for x in early_name.split("-"))
    late_month, late_year = (int(x) for x in late_name.split("-"))
    F = Findings()

    # ---------------------------------------------- K8: was the sheet copied?
    early_norm, late_norm = derived_norm(early), derived_norm(late)
    calendar = {early_name: M.working_days(early_year, early_month),
                late_name: M.working_days(late_year, late_month)}
    for name, built_on in ((early_name, early_norm), (late_name, late_norm)):
        if abs(built_on - calendar[name]) < 1e-9:
            continue
        other = calendar[early_name if name == late_name else late_name]
        why = " - the norm of the other sheet's month, so this one was copied forward" \
            if abs(built_on - other) < 1e-9 else ""
        F.add("K8_stale_thresholds", "file",
              f"sheet „{name}“ is built on {built_on:g} working days while its month has "
              f"{calendar[name]:g}{why}", built_on, calendar[name])

    # The thresholds carried with it. The cap of the wrong period is visible whenever a
    # row sits on it, which is the case the copy actually costs money.
    applicable = {name: M.REGIMES[M.regime_for(year, month)]["max_insurable"]
                  for name, year, month in ((early_name, early_year, early_month),
                                            (late_name, late_year, late_month))}
    for name, rows in ((early_name, early), (late_name, late)):
        due = applicable[name]
        other = applicable[early_name if name == late_name else late_name]
        if other == due:
            continue
        capped = [r for r in rows if abs(r["Осигурителен доход"] - other) <= TOL]
        if capped:
            F.add("K8_stale_thresholds", "file",
                  f"in sheet „{name}“ {len(capped)} row(s) are capped at {other:.2f} - "
                  f"the maximum insurable income of the other period - instead of "
                  f"{due:.2f}", other, due)

    # ------------------------------------- the roster, matched across the sheets
    by_name = {r["Име"]: r for r in early}
    pairs = [(by_name[r["Име"]], r) for r in late if r["Име"] in by_name]

    for before, after in pairs:
        row_no = after["_row"]

        # --- I7: a jump with nothing to explain it -------------------------
        # The comparison is the implied monthly salary, not the gross. A gross may
        # legitimately move with a bonus, with leave, with sick days, or simply because
        # the two months hold a different number of working days. The salary behind it
        # may not, unless something was agreed - and an annex would be in the file.
        was, now = (implied_salary(before, early_norm), implied_salary(after, late_norm))
        if was and now and abs(now - was) > SALARY_TOL:
            F.add("I7_unexplained_jump", row_no,
                  f"the row implies a different monthly base in „{late_name}“ than in "
                  f"„{early_name}“, with the same contract and nothing in the file to "
                  f"explain the change", now, was, figures=False)

        # --- чл. 177 КТ: the base for paid leave ---------------------------
        days_leave = after["Дни платен отпуск"]
        if not days_leave:
            continue
        paid_days = before["Отраб. дни"] + before["Дни платен отпуск"]
        if paid_days < 10:
            continue          # чл. 177 looks further back; the fixture never builds this
        due_daily = M.leave_daily_base(work_pay(before), paid_days)
        due = r2(due_daily * days_leave)
        stated = after["Платен отпуск"]
        if abs(stated - due) <= TOL:
            continue
        worked = after["Отраб. дни"]
        contract_daily = (after["Основна за отработеното"] / worked
                          * (1 + after["Клас %"] / 100.0)) if worked else 0.0
        why = " - from the contracted daily rate, not from the preceding month" \
            if abs(stated - r2(contract_daily * days_leave)) <= TOL else ""
        F.add("E3_leave_from_contract", row_no,
              f"paid leave for {days_leave:g} days{why}; чл. 177 КТ measures it "
              f"against the average daily gross of „{early_name}“ ({due_daily:.4f})",
              stated, due)

    # ----------------------------------------------------------------- scoring
    man = manifest if isinstance(manifest, dict) else json.load(
        open(manifest, encoding="utf8"))
    expected = {("file" if where == "file" else late_hdr + 1 + idx, ident)
                for where, idx, ident in man["cross_expected"]}
    found = F.keys()
    missed, extra = expected - found, found - expected

    if not quiet:
        print(f"=== {os.path.basename(xlsx)} · „{early_name}“ + „{late_name}“ · "
              f"{len(pairs)} people · built on {early_norm:g} and {late_norm:g} days "
              f"(the calendar says {calendar[early_name]:g} and "
              f"{calendar[late_name]:g}) ===")
        print(f"\nFINDINGS ({len(F.items)}):")
        for f in sorted(F.items, key=lambda x: (str(x["where"]), x["id"])):
            where = "file" if f["where"] == "file" else f"row {f['where']}"
            print(f"  [{where:8}] {f['id']:24} {f['text']}")
            if f["due"] is not None and f["figures"]:
                print(f"{'':13} stated {f['stated']} | due {f['due']}")
        if missed:
            print(f"\nMISSED ({len(missed)}):")
            for where, ident in sorted(missed, key=str):
                print(f"  {where} · {ident} — {M.PAIR_SCENARIOS.get(ident, ('', '?'))[1]}")
        if extra:
            print(f"\nFALSE POSITIVES ({len(extra)}):")
            for where, ident in sorted(extra, key=str):
                print(f"  {where} · {ident}")
        print(f"\ninjected {len(expected)} · found {len(expected & found)} · "
              f"missed {len(missed)} · extra {len(extra)}")

    return dict(injected=len(expected), found=len(expected & found),
                missed=sorted(f"{a}:{b}" for a, b in missed),
                extra=sorted(f"{a}:{b}" for a, b in extra),
                findings=len(F.items))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    sys.path.insert(0, HERE)
    import generate_pair as P

    xlsx, manifest_path, _ = P.generate(a.seed)
    result = check(xlsx, manifest_path, quiet=a.quiet)
    sys.exit(0 if not result["missed"] and not result["extra"] else 1)
