# -*- coding: utf-8 -*-
"""Runs the whole test suite.

    python test/run_tests.py                 # 50 seeds
    python test/run_tests.py --seeds 200     # longer
    python test/run_tests.py --from 500 --seeds 100

Three suites:

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
from structural_test import check                         # noqa: E402


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
    if p.returncode != 0:
        print(p.stdout[-2000:], p.stderr[-2000:])
        return False
    for line in [l for l in p.stdout.splitlines() if l.strip()][-3:]:
        print("  " + line)
    ok = "People with violations" in p.stdout
    print(f"  -> {'OK' if ok else 'FAILED'}")
    return ok


def suite_structural(start, count, quiet=True):
    print()
    print("=" * 78)
    print(f"SUITE 2 - generated payrolls, seeds {start}..{start + count - 1}")
    print("=" * 78)
    coverage = collections.Counter()
    months = collections.Counter()
    failures = []
    total_injected = total_found = total_findings = 0
    for seed in range(start, start + count):
        xlsx, manifest_path, man = G.generate(seed)
        for _, _, ident in man["expected"]:
            coverage[ident] += 1
        months[man["month"]] += 1
        result = check(xlsx, manifest_path, quiet=quiet)
        total_injected += result["injected"]
        total_found += result["found"]
        total_findings += result["findings"]
        if result["missed"] or result["extra"]:
            failures.append((seed, result))

    print(f"  seeds: {count} · injected defects: {total_injected} · "
          f"found: {total_found} · all findings: {total_findings}")
    print(f"  months: {dict(sorted(months.items()))}")
    print("\n  coverage per scenario:")
    for ident in M.SCENARIOS:
        n = coverage.get(ident, 0)
        mark = "  " if n else "!!"
        print(f"  {mark} {ident:30} {n:4d}  {M.SCENARIOS[ident][1]}")
    untested = [i for i in M.SCENARIOS if not coverage.get(i)]
    if untested:
        print(f"\n  WARNING: {len(untested)} scenarios were never injected at these "
              f"seeds - raise --seeds")
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
    print()
    print("=" * 78)
    print(f"RESULT: suite 0 {'OK' if ok0 else 'FAILED'} · "
          f"suite 1 {'OK' if ok1 else 'FAILED'} · "
          f"suite 2 {'OK' if ok2 else 'FAILED'}")
    sys.exit(0 if (ok0 and ok1 and ok2) else 1)
