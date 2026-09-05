#!/usr/bin/env python3
"""Suite 5: the chain below the payroll — ведомост → обр. 1 → обр. 6 → внесено.

Standalone, like `preflight_test.py`: run it directly. `run_tests.py` owns the five
suites that work on a single workbook, and this one needs a directory of documents.

    python test/komplekt_test.py

The proving standard is the repository's, unchanged: a clean комплект must raise **no**
finding at all, and each planted break must raise **its own** finding and nothing else.
A false positive fails exactly like a miss.

Why a checker at all, when the real consumer of this fixture is the paid eval. Because
a fixture nothing verifies proves nothing: a break that leaves the documents reconciling
would be graded as "the model missed it" when the truth is the break never existed. This
file is what makes the fixture evidence — the same reason `structural_test.py` exists
next to `generate_wide.py`.

**Attribution before aggregation.** Every aggregate check runs only when nothing
per-person already explains the gap. One net paid twice moves the payment total as
surely as a short payment does; reporting both the person and the total would be the
error `SKILL.md` calls "several findings, one cause", committed by the suite that is
supposed to hold the skill to it.
"""

import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import generate_komplekt as G                                   # noqa: E402
from findings import Findings                                   # noqa: E402

CENT = 0.005            # a difference below this is rounding, not a finding

# One sentence per break, in the words a correct finding would use. Not the model's
# words - it has never run against this fixture - but the shape they must take for
# KOMPLEKT_KEYWORDS to recognise them. When a paid run shows real phrasings, calibrate
# the patterns against those and keep these as the floor.
CORRECT_REPORT = {
    "I9_ledger_differs":
        "Салдото по сметка 461 за ДЗПО-УПФ в оборотната ведомост е с 73.40 повече от "
        "декларираното по обр. 6 — начисление, което не е декларирано, или обратното",
    "A10_midmonth_annex":
        "Увеличената основна заплата по допълнителното споразумение е начислена за "
        "целия месец, а не пропорционално от датата на влизането му в сила",
    "I9_person_missing_in_d1":
        "Лице от ведомостта липсва в обр. 1 - не е подадена декларация за него",
    "I9_extra_person_in_d1":
        "Ред в обр. 1 за лице, което го няма във ведомостта",
    # The one sentence here that is not invented: Fable 5.1 wrote it on seed 1,
    # 05.09.2026, and it was verified correct. A real phrasing is worth more than a
    # plausible one - it is the wording the patterns actually have to survive.
    "I9_insurable_differs_in_d1":
        "В обр. 1 за Лице 2 (СЛ-002) т.21 осигурителен доход е 1647.25 при 1797.25 "
        "във ведомостта; вноските в същия ред на обр. 1 са върху 1797.25, така че "
        "т.21 е грешното число.",
    "I9_sick_days_differ_in_d1":
        "Дните в неработоспособност по т. 16.А се разминават с дните болничен по ведомостта",
    "I9_d6_not_sum_of_d1":
        "Обр. 6 по ДОО не е сборът на редовете на обр. 1 - разминаване 45.60",
    "I9_declared_not_paid":
        "Декларираното по обр. 6 за ЗО не е внесено изцяло - внесено е по-малко със 120.00",
    "I9_net_not_paid":
        "Нареденото по банка е по-малко от нетото за изплащане - недоплатено на лицето",
    "I10_duplicate_payment":
        "Нетото на лицето е наредено два пъти в платежния файл",
    "I10_iban_shared":
        "Един и същ IBAN при две лица в платежния файл",
}

FAILURES = []


def check(condition, message):
    print(("  ok   " if condition else "  FAIL ") + message)
    if not condition:
        FAILURES.append(message)


def reconcile(k):
    """Walk the chain and return the findings. Nothing else in this file computes."""
    f = Findings()

    # --- the contract against the payroll, before the chain -----------------
    # A6 compares the payroll against "the last effective annex" and passes a row that
    # applied the right salary from the wrong date. The annex names a date; the days
    # before it are owed at the old rate.
    for person in k["people"]:
        a = person.get("annex")
        if not a:
            continue
        # days_worked == norm for the person carrying the annex (see _add_annex), so
        # the base owed is simply each rate over its own days.
        due = r2((a["old"] * a["days_before"] + a["new"] * a["days_after"]) / k["norm"])
        stated = r2(person["row"]["Основна за отработеното"])
        if abs(stated - due) > CENT:
            f.add("A10_midmonth_annex", person["ident"],
                  "допълнителното споразумение е приложено за целия месец, а не от "
                  "датата, на която влиза в сила",
                  stated=stated, due=due)

    # --- transition 1: ведомост -> обр. 1, per person -----------------------
    by_ident = {p["ident"]: p for p in k["people"]}
    filed = {}
    for row in k["d1"]:
        filed.setdefault(row["ident"], []).append(row)

    for ident, person in by_ident.items():
        rows = filed.get(ident)
        if not rows:
            f.add("I9_person_missing_in_d1", ident,
                  "лице във ведомостта без ред в обр. 1")
            continue
        row = rows[0]
        stated, due = row["osig_dohod"], r2(person["row"]["Осигурителен доход"])
        if abs(stated - due) > CENT:
            f.add("I9_insurable_differs_in_d1", ident,
                  "т. 21 на обр. 1 се разминава с осигурителния доход по ведомостта",
                  stated=stated, due=due)
        stated, due = row["dni_nerabotosposobnost"], int(person["row"]["Дни болничен"])
        if stated != due:
            f.add("I9_sick_days_differ_in_d1", ident,
                  "т. 16.А на обр. 1 се разминава с дните болничен по ведомостта",
                  stated=stated, due=due)

    for ident in filed:
        if ident not in by_ident:
            f.add("I9_extra_person_in_d1", ident,
                  "ред в обр. 1 за лице, което го няма във ведомостта")

    # --- transition 2: обр. 1 -> обр. 6, in total ---------------------------
    # Обр. 6 is a summary, so a difference here names no person - it says one of the two
    # declarations was compiled from another number.
    for line in k["d6"]:
        key = G._KEY_BY_NAME[line["vid"]]
        due = r2(sum(row[f"vnoski_{key}"] for row in k["d1"]))
        if abs(line["dalzhimo"] - due) > CENT:
            f.add("I9_d6_not_sum_of_d1", line["vid"],
                  "обр. 6 не е сборът на редовете на обр. 1 по този вид задължение",
                  stated=line["dalzhimo"], due=due)

    # --- transition 3: обр. 6 -> внесено ------------------------------------
    paid_nap = {}
    for order in k["payments"]:
        if order["vid"].startswith("НАП "):
            paid_nap[order["vid"][4:]] = r2(paid_nap.get(order["vid"][4:], 0)
                                            + order["suma"])
    for line in k["d6"]:
        got = paid_nap.get(line["vid"], 0.0)
        if abs(got - line["dalzhimo"]) > CENT:
            f.add("I9_declared_not_paid", line["vid"],
                  "декларирано по обр. 6 и внесено по сметка не съвпадат",
                  stated=got, due=line["dalzhimo"])

    # --- transition 4: нето -> платежен файл, per person --------------------
    orders = {}
    for order in k["payments"]:
        if order["vid"] == "заплата":
            orders.setdefault(order["poluchatel"], []).append(order)
    for ident, person in by_ident.items():
        mine = orders.get(ident, [])
        due = r2(person["row"]["НЕТО за изплащане"])
        if len(mine) > 1:
            f.add("I10_duplicate_payment", ident,
                  "едно и също нето, наредено повече от веднъж",
                  stated=r2(sum(o["suma"] for o in mine)), due=due)
            continue
        got = r2(sum(o["suma"] for o in mine))
        if abs(got - due) > CENT:
            f.add("I9_net_not_paid", ident,
                  "нареденото по банка не е нетото по ведомостта",
                  stated=got, due=due)

    # --- transition 5: внесено -> счетоводна статия -------------------------
    # Liabilities, not cost: the balance owed to НАП by kind and the balance owed to
    # staff must come out of the same figures the declarations do. The cost of labour
    # is K7's and is not recomputed here - checking it twice reports one defect twice.
    booked = {x["smetka"]: x["salddo"] for x in k.get("ledger", [])}
    for line in k["d6"]:
        account = f"461 {line['vid']}"
        if account in booked and abs(booked[account] - line["dalzhimo"]) > CENT:
            f.add("I9_ledger_differs", account,
                  "салдото по сметката за задължение към НАП не излиза от обр. 6",
                  stated=booked[account], due=line["dalzhimo"])
    staff = booked.get("421 Персонал")
    if staff is not None:
        due = r2(sum(p["row"]["НЕТО за изплащане"] for p in k["people"]))
        if abs(staff - due) > CENT:
            f.add("I9_ledger_differs", "421 Персонал",
                  "салдото по задължението към персонала не е сборът на нетата",
                  stated=staff, due=due)

    # --- master data: the account, not the money ----------------------------
    seen = {}
    for person in k["people"]:
        seen.setdefault(person["iban"], []).append(person["ident"])
    for iban, idents in seen.items():
        if len(idents) > 1:
            f.add("I10_iban_shared", ", ".join(sorted(idents)),
                  "един IBAN при повече от едно лице")

    return f


def r2(x):
    return G.r2(x)


def main():
    tmp = tempfile.mkdtemp(prefix="komplekt-test-")
    try:
        print("Suite 5 - the chain below the payroll")
        print("=" * 78)

        # ------------------------------------------------- the clean set is silent
        k, man = G.build(None, os.path.join(tmp, "clean"))
        found = reconcile(k)
        check(not found.items,
              f"a clean комплект raises no finding at all, got "
              f"{sorted(i['id'] for i in found.items)}")
        for name in ("vedomost.xlsx", "dogovori.csv", "deklaracia_1.csv",
                     "deklaracia_6.csv", "plateni.csv", "oborotna.csv"):
            check(os.path.exists(os.path.join(man["dir"], name)),
                  f"the set carries {name}")

        # ---------------------------------------------- one broken link at a time
        print("-" * 78)
        for break_id, (_, why) in G.BREAKS.items():
            k, _ = G.build(break_id, os.path.join(tmp, break_id))
            ids = sorted({i["id"] for i in reconcile(k).items})
            extra = [i for i in ids if i != break_id]
            check(break_id in ids and not extra,
                  f"{break_id:30} ({why})"
                  + ("" if break_id in ids else "  NOT RAISED")
                  + (f"  ALSO RAISED {extra}" if extra else ""))
        print("-" * 78)

        # ------------------------------------- several breaks, still one finding each
        # The paid eval injects more than one break per set, the way the wide fixture
        # injects six to eleven defects. That is only meaningful if the findings stay
        # separable: one break per group, all at once, must produce exactly those ids.
        print("-" * 78)
        combo = [g[0] for g in G.GROUPS]
        k, _ = G.build(combo, os.path.join(tmp, "combo"))
        ids = sorted({i["id"] for i in reconcile(k).items})
        check(ids == sorted(combo),
              f"one break from each of the {len(G.GROUPS)} groups at once -> exactly "
              f"those {len(combo)} findings, got {ids}")
        combo2 = [g[-1] for g in G.GROUPS]
        k, _ = G.build(combo2, os.path.join(tmp, "combo2"))
        ids = sorted({i["id"] for i in reconcile(k).items})
        check(ids == sorted(combo2),
              f"and the other member of each group likewise, got {ids}")
        check(G.build(list(reversed(combo)), os.path.join(tmp, "combo3"))[1]["breaks"]
              == list(reversed(combo)),
              "the order they are asked for in does not change which are applied")
        k, _ = G.build(list(reversed(combo)), os.path.join(tmp, "combo4"))
        check(sorted({i["id"] for i in reconcile(k).items}) == sorted(combo),
              "and reversing that order changes nothing about the findings")
        print("-" * 78)

        # ------------------------------------------------------- no personal data
        blob = ""
        for name in os.listdir(man["dir"]):
            path = os.path.join(man["dir"], name)
            if name.endswith(".csv"):
                blob += open(path, encoding="utf8").read()
        check("ЕГН" not in blob, "no field is called ЕГН anywhere in the set")
        # Ten digits in a row is the shape of an ЕГН. A date is 16.07.2026 - ten
        # characters, but never ten consecutive digits, which is why the check is on
        # the digits and not on the length.
        # Exactly ten digits standing alone is the shape of an ЕГН. A date carries
        # separators and the test IBANs carry eighteen digits in a row, so neither is
        # caught by the negative lookarounds - and neither should be.
        check(not re.search(r"(?<!\d)\d{10}(?!\d)", blob),
              "no ten-digit number anywhere that could be read as an ЕГН")
        check("BG00TEST" in blob, "the IBANs are the reserved test shape")

        # ------------------------------------------- the seed drives the whole set
        a, _ = G.build(None, os.path.join(tmp, "seed-a"), seed=7)
        b, _ = G.build(None, os.path.join(tmp, "seed-b"), seed=8)
        check(a["people"][0]["monthly_salary"] != b["people"][0]["monthly_salary"],
              "a different seed builds a different set")
        check(not reconcile(a).items and not reconcile(b).items,
              "and both of them reconcile")

        # ------------------------------ the paid eval can recognise a correct report
        # KOMPLEKT_KEYWORDS is what a paid session is scored against, and a pattern that
        # matches nothing turns every seed into a miss no triage can distinguish from a
        # model failure. This grades a synthetic, CORRECT report - one sentence per
        # break, in the words the finding would use - and requires every one to be
        # identified. It costs nothing and starts no session.
        print("-" * 78)
        import eval_skill as E
        for break_id in G.BREAKS:
            seed = next((s_ for s_ in range(1, 400)
                         if break_id in G.breaks_for_seed(s_)), None)
            if seed is None:
                check(False, f"{break_id}: no seed in 400 injects it")
                continue
            _, man, _ = E.prepare_komplekt(seed, dry=True, overwrite=True)
            findings = [dict(kade="файл" if where == "file" else f"ред {man['hdr'] + 1 + idx}",
                             red=None if where == "file" else man["hdr"] + 1 + idx,
                             tezhest="нарушение", kratko=CORRECT_REPORT[ident])
                        for where, idx, ident in man["expected"]]
            graded, unattributed = E.grade(man, findings)
            verdict = dict((ident, v) for _, ident, v, _ in graded)
            check(verdict.get(break_id) == "identified" and not unattributed,
                  f"{break_id:30} a correct sentence grades as identified"
                  f" (seed {seed}, got {verdict.get(break_id)}"
                  f"{', ' + str(len(unattributed)) + ' unattributed' if unattributed else ''})")
        print("-" * 78)

        print("=" * 78)
        if FAILURES:
            print(f"FAILED: {len(FAILURES)} check(s)")
            return 1
        print(f"OK: the clean set is silent and each of the {len(G.BREAKS)} broken links "
              f"is found exactly once")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
