# -*- coding: utf-8 -*-
"""Runs the whole test suite.

    python test/run_tests.py                 # 50 seeds
    python test/run_tests.py --seeds 200     # longer
    python test/run_tests.py --from 500 --seeds 100

Four suites:

0. `rates_test.py` - cross-checks the rates in `trz_model.py` against
   `references/stavki.md`. The only test that reads the skill itself, and
   therefore the only one worth running on **every** change to it. No
   dependencies.

1. `checks_test.py` over `vedomost_05_2026.xlsx` - a static payroll in a narrow
   layout with nine injected defects in the rates and the working-time regimes
   (minimum wage, length-of-service supplement, overtime, night work, public
   holiday, sick days, the cap, arithmetic, an attachment). The answer key is in
   `expected_findings.md`.

2. `structural_test.py` over generated payrolls in a wide layout - every seed
   gives a different company, different people, different salaries, a different
   month, a different accident rate and a different set of defects. It checks the
   construction of the file and the composition of the bases. The scenarios are
   described in `scenarios.md`.

4. `formula_test.py` over `generate_formula.py`'s workbooks - the only fixture
   whose computed columns carry REAL formulas. Checks the formula layer the way
   group K states it: the gross's coverage, day cells in money sums, typed values
   inside formula columns, tautological controls, inlined parameters. Value
   exports cannot hold any of these, and the first real audit found ALL of its
   defects in exactly this layer.

3. `pair_test.py` over a two-sheet payroll - July and August 2026, one roster,
   the months the thresholds change between. It covers the three checks that
   cannot be expressed in a single sheet: a copied sheet keeping the previous
   month's norm and thresholds (K8), a jump in someone's implied salary between
   adjacent months (I7), and paid leave computed on the wrong side of чл. 17, ал. 1
   НСОРЗ for the preceding month's bonus (E3). That last one runs in both polarities:
   the plugin asks at install time whether an uncharacterised bonus is a one-off or
   т. 2 pay, each seed draws one reading, and the suite fails if a run never used
   both. Suite 3 also asserts the чл. 18, ал. 2 coefficient
   directly: the fixture and the checker share the function that applies it, so no
   number of seeds can see it missing.

Not included: `eval_skill.py`. That one calls Claude, so it needs authentication
and costs money per run. It is run by hand when the guidance in SKILL.md changes.

Coverage is reported too: how many times each scenario was injected across the
seeds that ran. A scenario with zero injections was not tested - which is not the
same as passing.
"""
import argparse
import collections
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trz_model as M                                    # noqa: E402
import generate_wide as G                                 # noqa: E402
import generate_pair as P                                 # noqa: E402
from structural_test import check, selftest_sick_base     # noqa: E402
from pair_test import check as check_pair                 # noqa: E402
from pair_test import selftest_leave_base                 # noqa: E402
import generate_formula as GF                              # noqa: E402
from formula_test import check as check_formula            # noqa: E402


def suite_rates():
    print("=" * 78)
    print("SUITE 0 - the rates in the model against the skill's reference file")
    print("=" * 78)
    p = subprocess.run([sys.executable, os.path.join(HERE, "rates_test.py")],
                       capture_output=True, text=True)
    for line in p.stdout.splitlines():
        if line.startswith(("  MISMATCH", "  NOT FOUND", "  CHANGED", "FAILED", "OK:")) \
                or line.startswith("              "):
            print("  " + line.strip())
    print(f"  -> {'OK' if p.returncode == 0 else 'FAILED'}")
    return p.returncode == 0


def suite_static():
    print()
    print("=" * 78)
    print("SUITE 1 - static payroll, rates and working-time regimes")
    print("=" * 78)
    p = subprocess.run([sys.executable, os.path.join(HERE, "checks_test.py")],
                       capture_output=True, text=True)
    # The exit code is the result: checks_test.py asserts its own answer key and exits
    # non-zero on a missed finding or a false positive. Deciding this by grepping the
    # output for a line that prints unconditionally would pass a run that found nothing.
    if p.returncode != 0:
        print(p.stdout[-2000:], p.stderr[-2000:])
        print("  -> FAILED")
        return False
    for line in [l for l in p.stdout.splitlines() if l.strip()][-3:]:
        print("  " + line)
    print("  -> OK")
    return True


def selftest_model():
    """Facts the seeds cannot check, because both sides of the round trip share them.

    The calendar: чл. 154, ал. 2 substitution, pinned on the months where the December
    cluster interacts with a weekend - the old algorithm assigned a substitute before
    it had collected all the holidays and gave December 2028, 2033 and 2034 one
    working day too many. May 2026 = 18 is the anchor the static fixture documents;
    May 2027 exercises a fixed holiday falling ON an Easter day. The other two lines
    pin the regime-year guard (a 2025 payroll must not silently get 2026 thresholds)
    and the relief clamp (a negative base earns zero relief, not a negative one).
    """
    # All twelve months of 2026, not a sample. The generator writes the norm it computed
    # into the manifest and the checker read it back from there, so a wrong month passed
    # both sides identically: September at 21 and November at 20 (real: 20 and 21) left
    # 120 seeds green, and the yearly-average pin in suite 3 was satisfied by the
    # compensating pair. Derived by hand from чл. 154, ал. 1 and ал. 2 КТ: weekdays
    # minus the holidays that fall on them, with a Sunday holiday moved to the next
    # working day (24 May, 6 September, 26 December). Sum 249, average 20.75.
    for (y, m), want in {(2026, 1): 21, (2026, 2): 20, (2026, 3): 21, (2026, 4): 20,
                         (2026, 5): 18, (2026, 6): 22, (2026, 7): 23, (2026, 8): 21,
                         (2026, 9): 20, (2026, 10): 22, (2026, 11): 21, (2026, 12): 20,
                         (2027, 5): 17,
                         (2028, 12): 18, (2033, 12): 19, (2034, 12): 18}.items():
        got = M.working_days(y, m)
        if got != want:
            raise AssertionError(f"working_days({y}, {m}) = {got}, expected {want}")
    if M.regime_for(2025, 6) is not None:
        raise AssertionError("regime_for(2025, ...) must be None - the model has no "
                             "2025 thresholds and must not borrow 2026's")
    if M.relief_for(-100.0, 50.0, 0.0) != 0.0:
        raise AssertionError("relief_for on a negative base must be 0.0, not negative")
    # The statutory-placement hatch, pinned directly: the generator cannot produce the
    # only state it runs in (NEEDS_PRACTICE refuses that combination), so seeds prove
    # nothing about it. Three hand-built rows with an in_kind whose practice is
    # unknown: sick pay left out; the чл. 224 compensation pulled in; and a figure two
    # placements explain, where the honest answer is silence.
    from structural_test import statutory_misplacements
    el = dict(in_kind=50.0, excess=0.0, sick_pay=80.0, comp_224=300.0)
    for insurable, want in ((1000.0 + 50.0, {"sick_pay"}),          # sick missing
                            (1000.0 + 80.0 + 50.0 + 300.0, {"comp_224"}),
                            (1000.0 + 80.0 + 50.0, set())):         # lawful exactly
        got = statutory_misplacements(1000.0, insurable, el)
        if got != want:
            raise AssertionError(f"statutory_misplacements at {insurable}: "
                                 f"{got} != {want}")
    ambiguous = dict(in_kind=300.0, excess=0.0, sick_pay=80.0, comp_224=300.0)
    got = statutory_misplacements(1000.0, 1000.0 + 80.0 + 300.0, ambiguous)
    if got != set():
        raise AssertionError(f"a figure two placements explain must stay silent, "
                             f"got {got}")
    return 16 + 2 + 4


def suite_structural(start, count, quiet=True):
    print()
    print("=" * 78)
    print(f"SUITE 2 - generated payrolls, seeds {start}..{start + count - 1}")
    print("=" * 78)
    try:
        cases = selftest_model()
        print(f"  calendar, regime guard and relief clamp, {cases} facts pinned "
              f"against arithmetic: ok")
        # Shared by generator and checker, hence invisible to every seed - see the
        # docstring. Pinned here the way suite 3 pins the чл. 18 leave base.
        cases = selftest_sick_base()
        print(f"  чл. 40, ал. 5 КСО daily base, {cases} cases pinned against "
              f"arithmetic: ok")
    except AssertionError as exc:
        print(f"  model selftest: FAILED - {exc}")
        return False
    coverage = collections.Counter()
    months = collections.Counter()
    readings = collections.Counter()
    failures = []
    total_injected = total_found = total_findings = 0
    for seed in range(start, start + count):
        xlsx, manifest_path, man = G.generate(seed)
        for _, _, ident in man["expected"]:
            coverage[ident] += 1
        months[man["month"]] += 1
        readings["т. 2 (вътре)" if man["policy"]["bonus_in_base"]
                 else "еднократен (вън)"] += 1
        result = check(xlsx, manifest_path, quiet=quiet)
        total_injected += result["injected"]
        total_found += result["found"]
        total_findings += result["findings"]
        if result["missed"] or result["extra"]:
            failures.append((seed, result))

    print(f"  seeds: {count} · injected defects: {total_injected} · "
          f"found: {total_found} · all findings: {total_findings}")
    print(f"  months: {dict(sorted(months.items()))}")
    print(f"  bonus reading (чл. 17, ал. 1): {dict(sorted(readings.items()))}")
    print("\n  coverage per scenario:")
    for ident in M.SCENARIOS:
        n = coverage.get(ident, 0)
        mark = "  " if n else "!!"
        print(f"  {mark} {ident:30} {n:4d}  {M.SCENARIOS[ident][1]}")
    if len(readings) < 2:
        failures.append(("readings", {"missed": ["one reading of чл. 17, ал. 1 never "
                                                 "ran at these seeds"], "extra": []}))
    untested = [i for i in M.SCENARIOS if not coverage.get(i)]
    if untested:
        print(f"\n  WARNING: {len(untested)} scenarios were never injected at these "
              f"seeds, so they were not tested: {', '.join(untested)}")
        print("  Two things cause this and they are not the same. At a low seed count "
              "the generator may find no suitable row - raise --seeds. But a scenario "
              "that stays at zero on a long run means its mutation can no longer break "
              "anything: the model now produces what the mutation was going to write. "
              "Check what changed in trz_model.py before raising the seeds further.")
    if failures:
        print(f"\n  FAILING SEEDS ({len(failures)}):")
        for seed, result in failures:
            print(f"    seed {seed}: missed {result['missed']} "
                  f"| extra {result['extra']}")
    else:
        print(f"\n  -> OK: zero missed, zero false positives across {count} seeds")
    return not failures and not untested


def suite_pair(start, count, quiet=True):
    print()
    print("=" * 78)
    print(f"SUITE 3 - two-month payrolls, seeds {start}..{start + count - 1}")
    print("=" * 78)
    coverage = collections.Counter()
    readings = collections.Counter()
    failures = []
    # Asserted before the seeds, and deliberately not through them: the fixture and
    # the checker share leave_daily_base, so no number of seeds can tell whether the
    # чл. 18, ал. 2 coefficient is there. See the docstring in pair_test.
    try:
        cases = selftest_leave_base()
        print(f"  чл. 18 НСОРЗ, {cases} cases asserted against arithmetic: ok")
    except AssertionError as exc:
        print(f"  чл. 18 НСОРЗ: FAILED - {exc}")
        failures.append(("selftest", {"missed": [str(exc)], "extra": []}))
    injected = found = 0
    for seed in range(start, start + count):
        xlsx, _, man = P.generate(seed)
        readings["т. 2 (вътре)" if man["policy"]["bonus_in_base"]
                 else "еднократен (вън)"] += 1
        for _, _, ident in man["cross_expected"]:
            coverage[ident] += 1
        result = check_pair(xlsx, man, quiet=quiet)
        injected += result["injected"]
        found += result["found"]
        if result["missed"] or result["extra"]:
            failures.append((seed, result))

    print(f"  seeds: {count} · injected defects: {injected} · found: {found}")
    print(f"  bonus reading (чл. 17, ал. 1): {dict(sorted(readings.items()))}")
    if len(readings) < 2:
        failures.append(("readings", {"missed": ["one reading of чл. 17, ал. 1 never "
                                                 "ran at these seeds"], "extra": []}))
    print("\n  coverage per scenario:")
    for ident in M.PAIR_SCENARIOS:
        n = coverage.get(ident, 0)
        print(f"  {'  ' if n else '!!'} {ident:26} {n:4d}  {M.PAIR_SCENARIOS[ident][1]}")
    untested = [i for i in M.PAIR_SCENARIOS if not coverage.get(i)]
    if untested:
        print(f"\n  WARNING: never injected at these seeds: {', '.join(untested)}")
    if failures:
        print(f"\n  FAILING SEEDS ({len(failures)}):")
        for seed, result in failures:
            print(f"    seed {seed}: missed {result['missed']} "
                  f"| extra {result['extra']}")
    else:
        print(f"\n  -> OK: zero missed, zero false positives across {count} seeds")
    return not failures and not untested


def suite_formula(start, count, quiet=True):
    print()
    print("=" * 78)
    print(f"SUITE 4 - the formula layer, seeds {start}..{start + count - 1}")
    print("=" * 78)
    coverage = collections.Counter()
    failures = []
    injected = found = 0
    for seed in range(start, start + count):
        xlsx, mpath, man = GF.generate(seed)
        for _, _, ident in man["expected"]:
            coverage[ident] += 1
        result = check_formula(xlsx, mpath, quiet=quiet)
        injected += result["injected"]
        found += result["found"]
        if result["missed"] or result["extra"]:
            failures.append((seed, result))
    print(f"  seeds: {count} · injected defects: {injected} · found: {found}")
    print("\n  coverage per scenario:")
    for ident in M.FORMULA_SCENARIOS:
        n = coverage.get(ident, 0)
        print(f"  {'  ' if n else '!!'} {ident:34} {n:4d}  "
              f"{M.FORMULA_SCENARIOS[ident][1]}")
    untested = [i for i in M.FORMULA_SCENARIOS if not coverage.get(i)]
    if untested:
        print(f"\n  WARNING: never injected at these seeds: {', '.join(untested)}")
    if failures:
        print(f"\n  FAILING SEEDS ({len(failures)}):")
        for seed, result in failures:
            print(f"    seed {seed}: missed {result['missed']} "
                  f"| extra {result['extra']}")
    else:
        print(f"\n  -> OK: zero missed, zero false positives across {count} seeds")
    return not failures and not untested


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=50)
    ap.add_argument("--from", dest="start", type=int, default=1)
    ap.add_argument("--verbose", action="store_true",
                    help="print the findings of every seed")
    a = ap.parse_args()

    ok0 = suite_rates()
    print()
    ok1 = suite_static()
    ok2 = suite_structural(a.start, a.seeds, quiet=not a.verbose)
    ok3 = suite_pair(a.start, a.seeds, quiet=not a.verbose)
    ok4 = suite_formula(a.start, a.seeds, quiet=not a.verbose)
    print()
    print("=" * 78)
    print(f"RESULT: suite 0 {'OK' if ok0 else 'FAILED'} · "
          f"suite 1 {'OK' if ok1 else 'FAILED'} · "
          f"suite 2 {'OK' if ok2 else 'FAILED'} · "
          f"suite 3 {'OK' if ok3 else 'FAILED'} · "
          f"suite 4 {'OK' if ok4 else 'FAILED'}")
    sys.exit(0 if (ok0 and ok1 and ok2 and ok3 and ok4) else 1)
