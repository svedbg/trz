# -*- coding: utf-8 -*-
"""Пуска целия тестов комплект.

    python test/run_tests.py                 # 50 семена
    python test/run_tests.py --semena 200    # по-дълго
    python test/run_tests.py --ot 500 --semena 100

Три комплекта:

0. `stavki_test.py` — сверява ставките в `trz_model.py` срещу
   `references/stavki.md`. Единственият тест, който чете самия скил, и затова
   единственият, който има смисъл при **всяка** промяна по него. Не изисква
   външни библиотеки.

1. `proverki_test.py` върху `vedomost_05_2026.xlsx` — статична ведомост в тесен
   layout с девет вкарани дефекта по ставките и по режимите на труд (МРЗ, клас,
   извънреден, нощен, празник, болнични, таван, аритметика, запор). Отговорите са
   в `expected_findings.md`.

2. `struktura_test.py` върху генерирани ведомости в широк layout — всяко семе
   дава друга фирма, други хора, други заплати, друг месец, друг процент ТЗПБ и
   друг набор дефекти. Проверява конструкцията на файла и състава на базите.
   Сценариите са описани в `scenarii.md`.

Отчита се и покритието: колко пъти всеки сценарий е бил вкарван при пуснатите
семена. Сценарий с нула вкарвания значи, че не е тестван — не че минава.
"""
import argparse
import collections
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trz_model as M                                    # noqa: E402
import generate_struktura as G                           # noqa: E402
from struktura_test import proveri                       # noqa: E402


def komplekt_0():
    print("=" * 78)
    print("КОМПЛЕКТ 0 — ставките в модела срещу справочника на скила")
    print("=" * 78)
    p = subprocess.run([sys.executable, os.path.join(HERE, "stavki_test.py")],
                       capture_output=True, text=True)
    for l in p.stdout.splitlines():
        if l.startswith(("  РАЗМИНАВА", "  НЕНАМЕРЕНА", "  ПРОМЯНА", "ПАДНА", "OK:")) \
                or l.startswith("              "):
            print("  " + l.strip())
    print(f"  -> {'OK' if p.returncode == 0 else 'ПАДНА'}")
    return p.returncode == 0


def komplekt_1():
    print("=" * 78)
    print("КОМПЛЕКТ 1 — статична ведомост, ставки и режими на труд")
    print("=" * 78)
    p = subprocess.run([sys.executable, os.path.join(HERE, "proverki_test.py")],
                       capture_output=True, text=True)
    if p.returncode != 0:
        print(p.stdout[-2000:], p.stderr[-2000:])
        return False
    posledni = [l for l in p.stdout.splitlines() if l.strip()][-3:]
    for l in posledni:
        print("  " + l)
    # очакваме девет вкарани дефекта, открити, и нула находки по контролния ред
    ok = "Лица с нарушения" in p.stdout
    print(f"  -> {'OK' if ok else 'ПАДНА'}")
    return ok


def komplekt_2(ot, kolko, tiho=True):
    print()
    print("=" * 78)
    print(f"КОМПЛЕКТ 2 — генерирани ведомости, семена {ot}..{ot + kolko - 1}")
    print("=" * 78)
    pokritie = collections.Counter()
    mesetsi = collections.Counter()
    padnali = []
    obshto_vkarani = obshto_nameren = obshto_nahodki = 0
    for seed in range(ot, ot + kolko):
        xlsx, mpath, man = G.generirai(seed)
        for _, _, ident in man["ochakvani"]:
            pokritie[ident] += 1
        mesetsi[man["mesec"]] += 1
        rez = proveri(xlsx, mpath, tiho=tiho)
        obshto_vkarani += rez["vkarani"]
        obshto_nameren += rez["nameren"]
        obshto_nahodki += rez["nahodki"]
        if rez["propusnati"] or rez["izlishni"]:
            padnali.append((seed, rez))

    print(f"  семена: {kolko} · вкарани дефекти: {obshto_vkarani} · "
          f"намерени: {obshto_nameren} · всички находки: {obshto_nahodki}")
    print(f"  месеци: {dict(sorted(mesetsi.items()))}")
    print("\n  покритие по сценарии:")
    for ident in M.SCENARII:
        n = pokritie.get(ident, 0)
        znak = "  " if n else "!!"
        print(f"  {znak} {ident:28} {n:4d}  {M.SCENARII[ident][1]}")
    netestvani = [i for i in M.SCENARII if not pokritie.get(i)]
    if netestvani:
        print(f"\n  ВНИМАНИЕ: {len(netestvani)} сценария не са вкарвани при тези семена "
              f"— увеличи --semena")
    if padnali:
        print(f"\n  ПАДНАЛИ СЕМЕНА ({len(padnali)}):")
        for seed, rez in padnali:
            print(f"    seed {seed}: пропуснати {rez['propusnati']} "
                  f"| излишни {rez['izlishni']}")
    else:
        print(f"\n  -> OK: нула пропуснати, нула фалшиви положителни на {kolko} семена")
    return not padnali and not netestvani


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--semena", type=int, default=50)
    ap.add_argument("--ot", type=int, default=1)
    ap.add_argument("--podrobno", action="store_true", help="печата находките на всяко семе")
    a = ap.parse_args()

    ok0 = komplekt_0()
    print()
    ok1 = komplekt_1()
    ok2 = komplekt_2(a.ot, a.semena, tiho=not a.podrobno)
    print()
    print("=" * 78)
    print(f"РЕЗУЛТАТ: комплект 0 {'OK' if ok0 else 'ПАДНА'} · "
          f"комплект 1 {'OK' if ok1 else 'ПАДНА'} · "
          f"комплект 2 {'OK' if ok2 else 'ПАДНА'}")
    sys.exit(0 if (ok0 and ok1 and ok2) else 1)
