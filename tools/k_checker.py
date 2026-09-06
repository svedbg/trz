#!/usr/bin/env python3
"""K5 and K6, computed instead of read: the two group-K checks safe to automate.

Group K (`references/proverki.md`) has eight checks and none of them cites a statute -
they compare the file with itself. That should make all eight easy to hand to code, but
most of them need something a generic tool cannot promise: K1 needs the full set of
accrual columns, and a real file legitimately carries accrual columns this tool's closed
concept vocabulary (`tools/preflight.py`'s CONCEPTS) does not name - a bonus, a
severance payment, a benefit. Flagging БРУТО for not equalling the columns this tool
happens to recognise would be a false positive on every clean file that has one more
accrual column than the vocabulary does, and this project treats a false positive as no
better than a miss (CONTRIBUTING.md). K3, K4, K7 and K8 fail the same test for other
reasons: K3 needs to know contributions are stale rather than merely fixed, K4 needs the
control column's formula, K7 needs a number the workbook does not carry, K8 needs the
neighbouring sheet.

K5 (a hand-typed total) and K6 (rounding beyond two decimals) ask nothing about any
column but the one being checked, so they carry no such risk - a totals row either sums
its column or it does not, and a money cell either rounds to two decimals or it does,
regardless of what else the file contains. That is the whole scope of this script.

Reuses tools/preflight.py's column resolution (Mapping, analyse()) so a company's layout
is declared once, in one file, not twice.

Usage:
    python tools/k_checker.py ВЕДОМОСТ.xlsx [--mapping tools/mapping.example.yaml]
                              [--kid 62] [--group 3] [--tzpb 0.4] [--out report.md]

Exit codes: 0 nothing found, 1 at least one finding, 2 could not read the file.
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

K5_TOTAL_NOT_SUM = "K5_total_not_sum"
K6_UNROUNDED_ACCRUAL = "K6_unrounded_accrual"

ROUND_EPS = 1e-9
SUM_EPS = 0.01                   # a cent: what a rate rounded before multiplying costs


def check(path, mapping=None, kid=None, group=None, tzpb=None):
    """Findings as a list of dicts. Never writes; reads the workbook once, values only.

    K6 is checked over every data row, K5 only where a totals row was found - the same
    boundaries tools/preflight.py already established, so a sheet it could not make
    sense of is silently skipped here rather than guessed at twice.
    """
    data = PF.analyse(path, mapping, kid, group, tzpb)
    wb = openpyxl.load_workbook(path, data_only=True)
    findings = []

    for s in data["sheets"]:
        if s["header_row"] is None or not s["first_row"]:
            continue
        ws = wb[s["name"]]
        last_data_row = (s["totals_row"] - 1) if s["totals_row"] else ws.max_row
        if last_data_row < s["first_row"]:
            continue

        for concept, meta in sorted(s["known"].items()):
            col, letter = meta["col"], get_column_letter(meta["col"])

            for r in range(s["first_row"], last_data_row + 1):
                v = ws.cell(r, col).value
                if isinstance(v, (int, float)) and not isinstance(v, bool) \
                        and abs(v - round(v, 2)) > ROUND_EPS:
                    findings.append({
                        "id": K6_UNROUNDED_ACCRUAL, "sheet": s["name"],
                        "ref": f"{letter}{r}", "concept": concept, "value": v,
                    })

            if s["totals_row"]:
                stated = ws.cell(s["totals_row"], col).value
                if isinstance(stated, (int, float)) and not isinstance(stated, bool):
                    computed = sum(
                        cv for cv in (ws.cell(r, col).value
                                      for r in range(s["first_row"], last_data_row + 1))
                        if isinstance(cv, (int, float)) and not isinstance(cv, bool))
                    if abs(stated - computed) > SUM_EPS:
                        findings.append({
                            "id": K5_TOTAL_NOT_SUM, "sheet": s["name"],
                            "ref": f"{letter}{s['totals_row']}", "concept": concept,
                            "stated": stated, "computed": round(computed, 2),
                        })
    return findings


def report(path, findings):
    L = [f"# K5/K6 — `{os.path.basename(path)}`\n",
         "Само две от осемте проверки на група K: другите шест изискват знание извън "
         "тази електронна таблица, а тук грешният отговор е по-лош от липсващия.\n"]
    if not findings:
        L.append("Нищо не е намерено.")
        return "\n".join(L) + "\n"
    by_sheet = {}
    for f in findings:
        by_sheet.setdefault(f["sheet"], []).append(f)
    for sheet, items in by_sheet.items():
        L.append(f"\n## Лист „{sheet}“\n")
        for f in items:
            if f["id"] == K5_TOTAL_NOT_SUM:
                L.append(f"- **K5** {f['ref']} ({f['concept']}): редът с общите суми "
                         f"показва {f['stated']:g}, сборът на клетките е {f['computed']:g}")
            else:
                L.append(f"- **K6** {f['ref']} ({f['concept']}): {f['value']!r} не се "
                         f"закръгля до {round(f['value'], 2):g}")
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
        findings = check(a.workbook, mapping, a.kid, a.group, a.tzpb)
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
