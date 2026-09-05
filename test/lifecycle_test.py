#!/usr/bin/env python3
"""Suite 6: one person's timeline across months — I11.

Standalone, like `komplekt_test.py` and `preflight_test.py`.

    python test/lifecycle_test.py

The standard is the repository's: a clean five-month history must raise **no** finding,
and each planted timeline break must raise **its own** finding and nothing else.

What makes this suite different from every other one here is what it is *not* allowed to
use. Each month in the fixture is internally correct — the arithmetic reconciles, the
bases are right, every single sheet would pass suites 1-4 on its own. The only thing that
disagrees is the sequence: a figure that moved with no document behind it, a payment
after the employment ended, an employer-paid sick period starting twice for one spell, a
class that moved on the wrong side of an anniversary. So `reconcile()` below may only
compare a month against **another month** or against **an event**, never a row against
itself; a check that could be written inside one sheet belongs in another suite.
"""

import datetime
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import generate_lifecycle as G                                  # noqa: E402
from findings import Findings                                   # noqa: E402

CENT = 0.005

FAILURES = []


def check(condition, message):
    print(("  ok   " if condition else "  FAIL ") + message)
    if not condition:
        FAILURES.append(message)


def _events(lc, ident, kind):
    return [e for e in lc["events"] if e[0] == ident and e[2] == kind]


def reconcile(lc):
    """Walk each person's months in order and compare them with the events."""
    f = Findings()
    by_person = {}
    for sheet in lc["sheets"]:
        for item in sheet["rows"]:
            by_person.setdefault(item["person"]["ident"], []).append((sheet["month"], item))

    for ident, months in by_person.items():
        months.sort()
        person = months[0][1]["person"]

        # --- the salary moved: is there an annex dated for it? -----------------
        for (prev_m, prev), (m, cur) in zip(months, months[1:]):
            if abs(cur["salary"] - prev["salary"]) > CENT:
                window_start = datetime.date(G.YEAR, prev_m, 1)
                window_end = datetime.date(G.YEAR, m, 1)
                has_annex = any(window_start < datetime.date.fromisoformat(e[1]) <= window_end
                                for e in _events(lc, ident, "допълнително споразумение"))
                if not has_annex:
                    f.add("I11_salary_change_without_annex", f"{ident} {prev_m:02d}->{m:02d}",
                          "заплатата се променя между два месеца без допълнително "
                          "споразумение за тази дата",
                          stated=cur["salary"], due=prev["salary"])

        # --- accruals after the employment ended -------------------------------
        orders = _events(lc, ident, "заповед за прекратяване")
        end = datetime.date.fromisoformat(orders[0][1]) if orders else None
        if end:
            for m, item in months:
                if datetime.date(G.YEAR, m, 1) > end and (item["row"]["БРУТО"] or 0) > CENT:
                    f.add("I11_pay_after_termination", f"{ident} {m:02d}",
                          "начисления за месец след датата на прекратяване",
                          stated=r2(item["row"]["БРУТО"]), due=0.0)

        # --- severance with nothing behind it ----------------------------------
        for m, item in months:
            if (item["severance"] or 0) > CENT and not orders:
                f.add("I11_severance_without_termination", f"{ident} {m:02d}",
                      "обезщетение по чл. 224 без заповед за прекратяване",
                      stated=r2(item["severance"]), due=0.0)

        # --- one spell of sick leave, one set of employer-paid days ------------
        for (prev_m, prev), (m, cur) in zip(months, months[1:]):
            continuing = prev["sick_days"] > 0 and cur["sick_days"] > 0 and m == prev_m + 1
            if continuing and cur["employer_days"] > 0:
                f.add("I11_sick_days_restart", f"{ident} {m:02d}",
                      "болничен, продължаващ от предходния месец, започва отново от "
                      "първия ден за сметка на работодателя",
                      stated=cur["employer_days"], due=0)

        # --- the class against the anniversary ---------------------------------
        for m, item in months:
            due = G.seniority_pct(person["seniority_start"], datetime.date(G.YEAR, m, 1))
            if item["pct"] > due + 1e-9:
                f.add("I11_class_raised_early", f"{ident} {m:02d}",
                      "класът е вдигнат преди навършването на годината стаж",
                      stated=item["pct"], due=due)
            elif item["pct"] < due - 1e-9:
                f.add("I11_class_not_raised", f"{ident} {m:02d}",
                      "навършена е година стаж, а класът не е вдигнат",
                      stated=item["pct"], due=due)
    return f


def r2(x):
    return G.r2(x)


def main():
    tmp = tempfile.mkdtemp(prefix="lifecycle-test-")
    try:
        print("Suite 6 - one person's timeline across months")
        print("=" * 78)

        lc, man = G.build(None, os.path.join(tmp, "clean"))
        found = reconcile(lc)
        check(not found.items,
              f"a clean five-month history raises no finding at all, got "
              f"{sorted(i['id'] for i in found.items)}")
        check(man["months"] == G.MONTHS, f"all five months are written, got {man['months']}")
        for name in ("vedomosti.xlsx", "sabitiya.csv", "dogovori.csv"):
            check(os.path.exists(os.path.join(man["dir"], name)),
                  f"the history carries {name}")

        # Every month must also be correct on its own, or a timeline finding could be
        # an arithmetic error wearing a timeline costume.
        clean_rows = [i for s in lc["sheets"] for i in s["rows"]]
        check(all(abs(i["row"]["БРУТО"] - r2(sum(i["row"].get(c, 0) or 0
                                                 for c in G.M.ACCRUALS))) < CENT
                  for i in clean_rows),
              "and every month reconciles internally, so nothing here is arithmetic")

        print("-" * 78)
        for break_id, (_, why) in G.BREAKS.items():
            lc, _ = G.build(break_id, os.path.join(tmp, break_id))
            ids = sorted({i["id"] for i in reconcile(lc).items})
            extra = [i for i in ids if i != break_id]
            check(break_id in ids and not extra,
                  f"{break_id:36} ({why})"
                  + ("" if break_id in ids else "  NOT RAISED")
                  + (f"  ALSO RAISED {extra}" if extra else ""))
        print("-" * 78)

        combo = [g[0] for g in G.GROUPS]
        lc, _ = G.build(combo, os.path.join(tmp, "combo"))
        ids = sorted({i["id"] for i in reconcile(lc).items})
        check(ids == sorted(combo),
              f"one break from each of the {len(G.GROUPS)} groups at once -> exactly "
              f"those {len(combo)}, got {ids}")
        combo2 = [g[-1] for g in G.GROUPS]
        lc, _ = G.build(combo2, os.path.join(tmp, "combo2"))
        ids = sorted({i["id"] for i in reconcile(lc).items})
        check(ids == sorted(combo2), f"and the other member of each group, got {ids}")

        blob = ""
        for name in ("sabitiya.csv", "dogovori.csv"):
            blob += open(os.path.join(man["dir"], name), encoding="utf8").read()
        import re
        check(not re.search(r"(?<!\d)\d{10}(?!\d)", blob),
              "no ten-digit number anywhere that could be read as an ЕГН")

        a, _ = G.build(None, os.path.join(tmp, "seed-a"), seed=11)
        b, _ = G.build(None, os.path.join(tmp, "seed-b"), seed=12)
        check(a["people"][0]["salary"] != b["people"][0]["salary"],
              "a different seed builds a different history")
        check(not reconcile(a).items and not reconcile(b).items,
              "and both of them reconcile")

        print("=" * 78)
        if FAILURES:
            print(f"FAILED: {len(FAILURES)} check(s)")
            return 1
        print(f"OK: the clean history is silent and each of the {len(G.BREAKS)} timeline "
              f"breaks is found exactly once")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
