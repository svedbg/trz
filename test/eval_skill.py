# -*- coding: utf-8 -*-
"""Evaluates the skill itself: runs Claude over a generated payroll and maps the
findings it reports back onto the manifest.

    python test/eval_skill.py --dry            # what would be sent, paying nothing
    python test/eval_skill.py --seeds 3        # three seeds
    python test/eval_skill.py --seed 42
    python test/eval_skill.py --seeds 5 --model sonnet

IT COSTS MONEY. One measured run on Opus: 18 turns, about 12 minutes and USD 2.4
for a single seed. Use --dry to see what will happen before paying.

How this differs from the other suites. They test the rules - arithmetic,
thresholds, composition logic - with independent Python against a generated
payroll. This one tests the guidance. Rewrite SKILL.md badly and only this will
show it.

Isolation, and why it is not complete. The model gets a directory in /tmp with
two files: the payroll and the contracts. The manifest stays in the repository,
the repository is not passed with --add-dir, and the openpyxl environment is a
separate venv outside it. The reason is blunt: `test/` holds a full
implementation of every check and a manifest with the answers; reading those
measures reading, not expertise.

Except the skill is installed as a symlink into that same repository, and the
model legitimately reads its reference files. So a path to `test/` exists and
cannot be closed without closing the skill itself. Isolation is therefore backed
by **detection**: the whole tool stream is recorded and checked for anything
reaching the manifest or the checking code. A run that reached them is reported
as tainted and does not enter the statistics.

How grading works. The scenario catalogue is NOT given to the model - otherwise
the task becomes label matching. All that is asked for is a list of findings:
where, severity, one sentence, and the two figures. Mapping them onto scenarios
happens here, by row and by keywords in the description. The keywords are below,
visible and arguable: that is judgement, not measurement, and it is reported as
such.

Hence three numbers rather than one:
  * located    - was a defect reported on this row at all (objective)
  * identified - does the description match what was injected (by keyword)
  * unattributed - everything the model found that was not injected; some of it
                   may be true observation, so it is printed for review rather
                   than counted as a false positive

The keyword patterns are Bulgarian because the skill reports in Bulgarian.
"""
import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trz_model as M                                          # noqa: E402
import generate_wide as G                                      # noqa: E402

VENV = "/tmp/trz-eval-venv"          # venv with openpyxl, outside the repository
WORKDIR = "/tmp/trz-eval"            # one directory per run

# --- keywords for the mapping. Each entry is a list: all of them must match ---
# --- the finding's description. Deliberately broad: the point is not to score ---
# --- a correct finding as a miss because it was worded differently. ---
KEYWORDS = {
    "K1_sum_omits_column":        [r"сбор|включ|извън|липсва|обхват|формула"],
    "K2_amount_in_day_column":    [r"сума|стойност|размер", r"дни|ден"],
    "K3_stale_contributions":     [r"вноск", r"процент|13\.?78|не отговар|твърд|изостан"],
    "K4_control_column_blind":    [r"изплат|разлика|контрол"],
    "K5_total_not_sum":           [r"сбор|сум|общо", r"ръчно|не отговар|различ|вписан|≠"],
    "K6_unrounded_accrual":       [r"закръгл|знак|цент|десетичн"],
    "K7_cost_from_net":           [r"разход"],
    "F9_sick_pay_in_insurable":   [r"болничен|болнични|неработоспособ|чл\.? ?40",
                                   r"осигурителн"],
    "F9_sick_pay_out_of_taxable": [r"болничен|болнични|неработоспособ|чл\.? ?40",
                                   r"данъчн|данък|облага"],
    "F9_sick_pay_amount":         [r"болничен|болнични|неработоспособ|чл\.? ?40",
                                   r"среднодневн|бонус|уговорен|база|по-висок"],
    "F9_missing_health_on_sick":  [r"здравн|ЗЗО", r"болничен|майчинств|неработоспособ"],
    "F10_in_kind_asymmetry":      [r"натура|карт"],
    "F10_excess_asymmetry":       [r"превишен|праг|застрахов|доброволн|30\.?6|60 лв"],
    "F7_relief_over_limit":       [r"облекчен|приспадн|лимит|10 ?%|чл\.? ?19|чл\.? ?42"],
    "F5_tzpb_below_due":          [r"ТЗПБ|трудова злополука"],
    "B4_cap_from_wrong_period":   [r"таван|максимал"],
    "C2_seniority_on_gross":      [r"клас", r"база|бруто|основна"],
    "E3_leave_without_seniority": [r"отпуск"],
    "I5_days_do_not_reconcile":   [r"дни|ден", r"норма|не се връзва|сбор|липсв|2[0-3]"],
}

# Paths this run has no business touching: the answers and the independent
# implementation of every check live there.
FORBIDDEN = re.compile(r"_manifest\.json|structural_test|checks_test|trz_model|"
                       r"generate_wide|generate_narrow|eval_skill|rates_test|"
                       r"expected_findings|scenarios\.md")


def ensure_venv():
    if os.path.exists(os.path.join(VENV, "bin", "python")):
        return
    subprocess.run(["python3", "-m", "venv", VENV], check=True)
    subprocess.run([os.path.join(VENV, "bin", "pip"), "install", "--quiet", "openpyxl"],
                   check=True)


def prepare(seed):
    """Generate a payroll and place it alone in an isolated directory."""
    xlsx, _, man = G.generate(seed)
    d = os.path.join(WORKDIR, f"seed-{seed}")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    shutil.copy(xlsx, os.path.join(d, "vedomost.xlsx"))
    with open(os.path.join(d, "dogovori.csv"), "w", newline="", encoding="utf8") as f:
        w = csv.writer(f)
        w.writerow(["Име", "Основна месечна заплата по договор", "Клас %"])
        for p in man["people"]:
            w.writerow([p["name"], f"{p['inputs']['monthly_salary']:.2f}",
                        p["inputs"]["seniority_pct"]])

    # The prompt is Bulgarian on purpose: that is what a real user would write,
    # and the skill is Bulgarian.
    prompt = f"""Направи ТРЗ проверка на ведомостта ./vedomost.xlsx. Ползвай скила trz-expert.

Какво имаш от дружеството:
- ./dogovori.csv — договорените основни месечни заплати и процентът клас по трудов договор
- приложимият процент ТЗПБ по КИД на дружеството е {man['tzpb_due']}%
- валутата е EUR

Работи само в тази директория. За Python ползвай {VENV}/bin/python — има openpyxl.

Освен обичайния отчет, запиши накрая и findings.json в тази директория: масив, по един обект
за всяка находка, само това и нищо друго във файла.

[{{"kade": "ред 12" или "файл", "red": 12 или null,
  "tezhest": "нарушение|риск|за проверка|дефект|бележка",
  "kratko": "едно изречение какво е сбъркано",
  "nachisleno": число или null, "dalzhimo": число или null}}]
"""
    with open(os.path.join(d, "prompt.txt"), "w", encoding="utf8") as f:
        f.write(prompt)
    leftovers = set(os.listdir(d)) - {"vedomost.xlsx", "dogovori.csv", "prompt.txt"}
    assert not leftovers, f"unexpected files in the isolated directory: {leftovers}"
    return d, man, prompt


def invoke(d, model=None, timeout=1800):
    """Run the session with streaming, so that what it touched stays visible."""
    cmd = ["claude", "-p", open(os.path.join(d, "prompt.txt"), encoding="utf8").read(),
           "--output-format", "stream-json", "--verbose",
           "--permission-mode", "acceptEdits",
           "--allowedTools", "Read", "Write", "Edit", "Glob", "Grep", "Bash",
           "--disallowedTools", "WebSearch", "WebFetch"]
    if model:
        cmd += ["--model", model]
    started = time.time()
    with open(os.path.join(d, "stream.jsonl"), "w", encoding="utf8") as f:
        p = subprocess.run(cmd, cwd=d, stdout=f, stderr=subprocess.PIPE,
                           text=True, timeout=timeout)
    trace = dict(exit=p.returncode, seconds=round(time.time() - started),
                 tool_calls=0, touched=[])
    for line in open(os.path.join(d, "stream.jsonl"), encoding="utf8"):
        try:
            event = json.loads(line)
        except Exception:
            continue
        if event.get("type") == "assistant":
            for c in event.get("message", {}).get("content", []):
                if c.get("type") == "tool_use":
                    trace["tool_calls"] += 1
                    text = json.dumps(c.get("input", {}), ensure_ascii=False)
                    if FORBIDDEN.search(text):
                        trace["touched"].append(f"{c.get('name')}: {text[:120]}")
        elif event.get("type") == "result":
            trace.update(turns=event.get("num_turns"), cost=event.get("total_cost_usd"),
                         error=event.get("is_error"))
    if "turns" not in trace:
        trace.update(error=True, stderr=(p.stderr or "")[-500:])
    return trace


def read_findings(d):
    path = os.path.join(d, "findings.json")
    if not os.path.exists(path):
        return None, "findings.json was not written"
    text = open(path, encoding="utf8").read().strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        parsed = json.loads(text)
    except Exception as e:
        return None, f"findings.json is not valid JSON: {e}"
    if not isinstance(parsed, list):
        return None, "findings.json is not an array"
    return parsed, None


def location(finding, total_row):
    """Normalise a finding's location to a row number or 'file'.

    A finding placed on the total row is a statement about the file, not about a
    person, and counts as file-level.
    """
    row = finding.get("red")
    if not isinstance(row, int):
        where = str(finding.get("kade", ""))
        if "файл" in where.lower():
            return "file"
        m = re.search(r"(\d+)", where)
        row = int(m.group(1)) if m else None
    if row is None:
        return "file"
    return "file" if row >= total_row else row


def grade(man, findings):
    """Map the findings onto what was injected.

    A single finding may satisfy several expectations at the same location: all
    expectations on one row come from one mutation, and a model that reports both
    aspects in one sentence should not be penalised for being concise.
    """
    HDR, TOTAL = man["hdr"], man["total_row"]
    expected = [("file" if where == "file" else HDR + 1 + idx, ident)
                for where, idx, ident in man["expected"]]
    expected.sort(key=lambda x: -len(KEYWORDS.get(x[1], [])))

    places = defaultdict(list)
    for i, f in enumerate(findings):
        places[location(f, TOTAL)].append(i)

    attributed = set()
    result = []
    for where, ident in expected:
        here = places.get(where, [])
        patterns = KEYWORDS.get(ident, [])
        hit = None
        for i in here:
            text = str(findings[i].get("kratko", ""))
            if all(re.search(p, text, re.I) for p in patterns):
                hit = i
                break
        if hit is not None:
            attributed.add(hit)
            result.append((where, ident, "identified", findings[hit]))
        elif here:
            result.append((where, ident, "located only", findings[here[0]]))
        else:
            result.append((where, ident, "missed", None))
    unattributed = [f for i, f in enumerate(findings) if i not in attributed]
    return result, unattributed


def run_seed(seed, model, dry, timeout):
    d, man, prompt = prepare(seed)
    print(f"\n{'=' * 78}\nseed {seed} · sheet {man['sheet']} · {len(man['people'])} people"
          f" · accident rate {man['tzpb_due']}% · {len(man['expected'])} defects injected")
    print(f"directory: {d}")
    if dry:
        print("-" * 78)
        print(prompt.rstrip())
        print("-" * 78)
        print("injected (NOT given to the model):")
        for where, idx, ident in man["expected"]:
            loc = "file" if where == "file" else f"row {man['hdr'] + 1 + idx}"
            print(f"  {loc:9} {ident}")
        return None

    trace = invoke(d, model=model, timeout=timeout)
    print(f"turns {trace.get('turns')} · tool calls {trace['tool_calls']} · "
          f"{trace['seconds']} s · USD {trace.get('cost') or 0:.3f}")
    if trace["touched"]:
        print("  RUN TAINTED: it reached the answers or the checking code -")
        for x in trace["touched"]:
            print(f"      {x}")
        return dict(seed=seed, cost=trace.get("cost") or 0, gradable=False,
                    result=[], unattributed=[])

    findings, error = read_findings(d)
    if findings is None:
        print(f"  RUN NOT GRADABLE: {error}")
        return dict(seed=seed, cost=trace.get("cost") or 0, gradable=False,
                    result=[], unattributed=[])

    graded, unattributed = grade(man, findings)
    print(f"findings reported: {len(findings)}")
    for where, ident, status, f in graded:
        loc = "file" if where == "file" else f"row {where}"
        mark = {"identified": "  +", "located only": "  ~", "missed": "  -"}[status]
        print(f"{mark} {loc:9} {ident:30} {status}")
        if f:
            print(f"      model: {str(f.get('kratko'))[:100]}")
    if unattributed:
        print(f"  unattributed findings ({len(unattributed)}) - for review, not counted "
              f"as errors:")
        for f in unattributed:
            print(f"      [{f.get('kade') or f.get('red')}] "
                  f"{str(f.get('kratko'))[:95]}")
    return dict(seed=seed, cost=trace.get("cost") or 0, gradable=True,
                result=graded, unattributed=unattributed)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--from", dest="start", type=int, default=1)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--dry", action="store_true",
                    help="prepare and print only, pay nothing")
    ap.add_argument("--timeout", type=int, default=1800,
                    help="seconds per seed; measured runs take 5-15 minutes")
    ap.add_argument("--threshold", type=float, default=None,
                    help="exit 1 if the identified share falls below this (0-1)")
    a = ap.parse_args()

    ensure_venv()
    os.makedirs(WORKDIR, exist_ok=True)
    seeds = [a.seed] if a.seed else list(range(a.start, a.start + a.seeds))

    if not a.dry:
        print(f"About to run {len(seeds)} Claude sessions. That costs money and takes "
              f"minutes per seed.")

    runs = [r for r in (run_seed(s, a.model, a.dry, a.timeout) for s in seeds) if r]
    if not runs:
        return 0

    per_scenario = defaultdict(lambda: [0, 0, 0])       # identified, located, missed
    cost = 0.0
    not_gradable = 0
    for r in runs:
        cost += r["cost"]
        if not r["gradable"]:
            not_gradable += 1
            continue
        for _, ident, status, _ in r["result"]:
            i = {"identified": 0, "located only": 1, "missed": 2}[status]
            per_scenario[ident][i] += 1

    print(f"\n{'=' * 78}\nSUMMARY over {len(runs)} seeds · USD {cost:.2f}")
    if not_gradable:
        print(f"non-gradable runs: {not_gradable} (tainted, or findings.json missing "
              f"or invalid)")
    print(f"{'scenario':30} {'identified':>11} {'located':>9} {'missed':>8}")
    identified = located = missed = 0
    for ident in M.SCENARIOS:
        a_, b_, c_ = per_scenario.get(ident, [0, 0, 0])
        if a_ + b_ + c_ == 0:
            continue
        identified += a_
        located += b_
        missed += c_
        print(f"{ident:30} {a_:>11} {b_:>9} {c_:>8}")
    total = identified + located + missed
    if total:
        print(f"{'TOTAL':30} {identified:>11} {located:>9} {missed:>8}")
        print(f"\nidentified: {identified}/{total} = {identified / total:.0%} · "
              f"located at all: {(identified + located) / total:.0%} · "
              f"missed: {missed / total:.0%}")
        extra = sum(len(r["unattributed"]) for r in runs)
        print(f"unattributed findings: {extra} - review them; some may be correct")
    if a.threshold is not None and total:
        ok = identified / total >= a.threshold
        print(f"threshold {a.threshold:.0%}: {'OK' if ok else 'FAILED'}")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
