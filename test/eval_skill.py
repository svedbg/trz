# -*- coding: utf-8 -*-
"""Evaluates the skill itself: runs Claude over a generated payroll and maps the
findings it reports back onto the manifest.

    python test/eval_skill.py --dry            # what would be sent, paying nothing
    python test/eval_skill.py --seeds 3        # three seeds
    python test/eval_skill.py --seed 42
    python test/eval_skill.py --seeds 5 --model sonnet
    python test/eval_skill.py --selftest       # free: checks the refusal grading itself
    python test/eval_skill.py --refusal        # can the skill refuse rather than guess?

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
import hashlib
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
REPO_SKILL = os.path.join(HERE, "..", "skills", "trz-expert")

# --- keywords for the mapping. Each entry is a list: all of them must match ---
# --- the finding's description. Deliberately broad: the point is not to score ---
# --- a correct finding as a miss because it was worded differently. ---
KEYWORDS = {
    "K1_sum_omits_column":        [r"сбор|включ|извън|липсва|обхват|формула",
                                   r"колон|бруто|БРУТО"],
    "K2_amount_in_day_column":    [r"сума|стойност|размер", r"дни|ден"],
    "K3_stale_contributions":     [r"вноск", r"процент|13\.?78|не отговар|твърд|изостан"],
    "K4_control_column_blind":    [r"изплат|разлика|контрол"],
    "K5_total_not_sum":           [r"сбор|сум|общо", r"ръчно|не отговар|различ|вписан|≠"],
    # \bцент, not цент: the latter matches „процент" and quietly claimed every
    # finding that mentions a percentage.
    "K6_unrounded_accrual":       [r"закръгл|знак|\bцент|десетичн"],
    "K7_cost_from_net":           [r"разход"],
    "F9_sick_pay_out_of_insurable": [r"болничен|болнични|неработоспособ|чл\.? ?40",
                                   r"осигурителн"],
    "F9_sick_pay_in_taxable":     [r"болничен|болнични|неработоспособ|чл\.? ?40",
                                   r"данъчн|данък|облага"],
    # The second pattern must require the CORRECTED reading, not merely allow it.
    # „среднодневното брутно е по-високо, защото месецът носеше бонус" is the story this
    # scenario was inverted to refute, and it matches „среднодневн", „уговорен", „база"
    # and „бонус" alike - so those cannot be the discriminator. What only the right
    # answer carries is the direction (paid too much) or the reason (a one-off is not
    # in чл. 17, ал. 1).
    "F9_sick_pay_amount":         [r"болничен|болнични|неработоспособ|чл\.? ?40",
                                   r"в повече|завишен|надплатен|надвзет|"
                                   r"постоянен характер|еднократ|чл\.? ?17"],
    "F9_missing_health_on_sick":  [r"здравн|ЗЗО", r"болничен|майчинств|неработоспособ"],
    "F10_in_kind_asymmetry":      [r"натура|карт"],
    "F10_excess_asymmetry":       [r"превишен|праг|застрахов|доброволн|30\.?6|60 лв"],
    # The second pattern discriminates over_limit from the other two F7 scenarios, but
    # „над" alone was too narrow: a live run described this defect as „приложено с
    # пълния размер на удръжката, без да е спазен лимитът" and scored as located only.
    "F7_relief_over_limit":       [r"облекчен|приспадн|лимит|10 ?%|чл\.? ?19|чл\.? ?42",
                                   r"над|превиш|надвиш|повече от|без да е спазен"
                                   r"|не е спазен|пълния размер|целия размер"
                                   r"|без ограничен"],
    "F7_relief_combined_limit":   [r"облекчен|приспадн|лимит|10 ?%|чл\.? ?19",
                                   r"два|две|отделн|поотделно|груп|общ|20 ?%|вместо|по-малк"],
    # A bare `0` matched any text containing a zero digit, i.e. almost everything;
    # `0\.00` was no better - it matches the tail of „250.00".
    "F7_relief_not_applied":      [r"облекчен|приспадн|намал|чл\.? ?19|чл\.? ?42",
                                   r"не е приложен|не е ползван|не е намален"
                                   r"|липсв|без облекчен|нула|не намал"],
    "F5_tzpb_below_due":          [r"ТЗПБ|трудова злополука"],
    "B4_cap_from_wrong_period":   [r"таван|максимал"],
    "C2_seniority_on_gross":      [r"клас", r"база|бруто|основна"],
    "E3_leave_without_seniority": [r"отпуск"],
    "I5_days_do_not_reconcile":   [r"дни|ден", r"норма|не се връзва|не отговарят|сбор"],
}

# --------------------------------------------------------------- refusal mode
# The skill's first rule is that no rate comes from memory: a figure the reference file
# does not carry downgrades the finding to `за проверка` instead of being guessed. That
# is the loudest promise this project makes and the one nothing could test, because the
# Python suites always hand it a period the reference file covers. `--refusal` dates the
# payroll outside RATES_KNOWN_YEARS and asks three questions.

# 1. What must still be found. These rest on the file agreeing with itself and with the
#    contract, so taking the rate book away must not silence them. A skill that goes
#    quiet when it loses its rates is not being careful, it is being useless.
RATE_FREE = ("K1_sum_omits_column", "K2_amount_in_day_column", "K4_control_column_blind",
             "K5_total_not_sum", "K6_unrounded_accrual", "K7_cost_from_net",
             "I5_days_do_not_reconcile", "C2_seniority_on_gross",
             "E3_leave_without_seniority")

# 2. What must not be asserted. A finding graded `нарушение` that leans on one of these
#    is the failure the rule exists to prevent: last year's threshold applied to this
#    year's payroll, stated with the confidence of a checked figure.
RATE_DEPENDENT = re.compile(
    r"МРЗ|минимална\w*\s+работна\s+заплата|минимално\w*\s+възнаграждение|"
    r"максимал\w*\s+осигурителен\s+доход|таван|\bМОД\b|"
    r"минимал\w*\s+осигурителен\s+доход|осигурителн\w*\s+праг", re.I)

# 3. What must be said. Omitting a conclusion is not the same as reporting that it
#    cannot be reached; the user has to be told.
#
#    Two phrasings count, and the second is the sharper one. A skill can name the gap -
#    "the reference file has no threshold for this year" - or it can name what was put
#    in the gap's place: "this is the 2026 figure, sitting in a 2027 payroll". The
#    second is a better answer, because it says what actually happened.
#
#    Both are here because of what the first live run showed. It passed this check, but
#    on a secondary sentence about the social-expense threshold, while the two findings
#    that were precisely the behaviour under test - the cap and the self-employed
#    minimum, both identified as the 01.08-31.12.2026 values carried into a July 2027
#    payroll - matched nothing. One said "справочникът не съдържа праг за 2027 г.",
#    a phrase the pattern did not know. A check that would have failed the best possible
#    answer is not a check.
SAYS_MISSING = re.compile(
    r"липсва\w*|няма|не\s+съдържа\w*|не\s+разполага\w*|непотвърд\w*|"
    r"не\s+са\s+(публикувани|известни|обнародвани|налични)|"
    r"не\s+е\s+(известен|известна|публикуван\w*|наличен|налична)|"
    r"без\s+публикуван\w*", re.I)
#    The companion pattern names what is missing, and stays narrow on purpose. It once
#    carried a bare "осигурителен доход", which appears in half the findings in any
#    payroll report - and duly matched "нито една клетка не съдържа формула", an
#    observation about formulas counted as a statement about rates.
SAYS_PERIOD = re.compile(r"2027|ставк\w*|праг\w*|\bМРЗ\b|\bМОД\b|"
                         r"минимална работна заплата", re.I)


def names_a_stale_rate(text, year):
    """Does the finding hold this payroll's year up against another year's figure?

    Cheaper and steadier than matching the wording: a sentence that mentions both 2027
    and 2026 has noticed the mismatch, however it chose to phrase it.
    """
    years = set(re.findall(r"\b(20\d\d)\b", str(text)))
    return str(year) in years and len(years) > 1

# Paths this run has no business touching: the answers and the independent
# implementation of every check live there.
FORBIDDEN = re.compile(r"_manifest\.json|structural_test|checks_test|trz_model|"
                       r"generate_wide|generate_narrow|generate_pair|pair_test|"
                       r"run_tests|skill_test|eval_skill|rates_test|"
                       r"expected_findings|scenarios\.md")


def ensure_venv():
    if os.path.exists(os.path.join(VENV, "bin", "python")):
        return
    subprocess.run(["python3", "-m", "venv", VENV], check=True)
    subprocess.run([os.path.join(VENV, "bin", "pip"), "install", "--quiet", "openpyxl"],
                   check=True)


def prepare(seed, year=2026):
    """Generate a payroll and place it alone in an isolated directory."""
    # Pinned, not drawn from the seed: the eval runs the skill from a clone or a
    # symlink, where the plugin's install-time question was never asked and SKILL.md
    # documents the default - an uncharacterised bonus stays out of the base. Letting
    # the fixture pick the other reading would grade the skill against a configuration
    # it does not have.
    xlsx, _, man = G.generate(seed, year=year, bonus_in_base=False)
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
    timed_out = False
    with open(os.path.join(d, "stream.jsonl"), "w", encoding="utf8") as f:
        try:
            p = subprocess.run(cmd, cwd=d, stdout=f, stderr=subprocess.PIPE,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            # One slow seed must not take the batch down with it. The seeds already
            # paid for keep their results; this one is reported below as ended in an
            # error, which run_seed prints as not gradable and not the skill's fault.
            # The partial stream is still parsed - a session can taint itself before
            # it times out, and that must not go unreported.
            p = None
            timed_out = True
    trace = dict(exit=p.returncode if p is not None else None,
                 seconds=round(time.time() - started),
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
            # `result` carries the reason when is_error is set - a spend cap, a rate
            # limit, a refusal. Without it a session killed mid-run is indistinguishable
            # from a skill that simply never wrote its answer, and the money is already
            # spent by the time anyone digs through stream.jsonl to tell them apart.
            trace.update(turns=event.get("num_turns"), cost=event.get("total_cost_usd"),
                         error=event.get("is_error"),
                         result_text=str(event.get("result") or "").strip())
    if timed_out:
        trace.update(error=True,
                     result_text=f"killed after {timeout} s (--timeout); nothing the "
                                 f"session did after that point exists to grade")
    elif "turns" not in trace:
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
        # No patterns must mean "cannot grade", never "matches everything": all() over
        # an empty list is True, and with the .get default a scenario missing from
        # KEYWORDS was scored identified by ANY finding at the right location. main()
        # refuses to start a paid run in that state; this raise is the belt to that
        # suspenders, for callers that reach grade() some other way.
        if ident not in KEYWORDS:
            raise KeyError(f"no KEYWORDS entry for {ident} - the run cannot be graded")
        patterns = KEYWORDS[ident]
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


def grade_refusal(man, findings):
    """Grade a payroll dated outside the years the reference file covers.

    Returns (results, detail): three named checks, each True or False, and the evidence
    for the ones that failed. Detection is graded too, but only over RATE_FREE - what a
    skill without rates still owes is the arithmetic.
    """
    detail = {}

    survived, missed = [], []
    for where, ident, status, finding in grade(man, findings)[0]:
        if ident not in RATE_FREE:
            continue
        (survived if status == "identified" else missed).append((where, ident, status))
    detail["arithmetic"] = dict(found=survived, missed=missed)

    asserted = [f for f in findings
                if str(f.get("tezhest", "")).strip() == "нарушение"
                and RATE_DEPENDENT.search(str(f.get("kratko", "")))]
    detail["guessed"] = asserted

    said = [f for f in findings
            if (SAYS_MISSING.search(str(f.get("kratko", "")))
                and SAYS_PERIOD.search(str(f.get("kratko", ""))))
            or names_a_stale_rate(f.get("kratko", ""), man["year"])]
    detail["said_missing"] = said

    return dict(arithmetic_survives=not missed,
                refuses_on_rates=not asserted,
                says_what_is_missing=bool(said)), detail


def report_refusal(man, findings):
    results, detail = grade_refusal(man, findings)
    print(f"\nrefusal grading · payroll dated {man['month']:02d}.{man['year']}, a year "
          f"references/stavki.md has no rates for")

    found, missed = detail["arithmetic"]["found"], detail["arithmetic"]["missed"]
    mark = "  +" if results["arithmetic_survives"] else "  -"
    print(f"{mark} the arithmetic still lands: {len(found)} of {len(found) + len(missed)} "
          f"rate-free defects identified")
    for where, ident, status in missed:
        print(f"      MISSED {ident} at "
              f"{'file' if where == 'file' else f'row {where}'} ({status})")

    mark = "  +" if results["refuses_on_rates"] else "  -"
    print(f"{mark} no violation asserted on a rate it does not have"
          + ("" if results["refuses_on_rates"]
             else f" - {len(detail['guessed'])} did"))
    for f in detail["guessed"]:
        print(f"      GUESSED [{f.get('kade')}] {str(f.get('kratko'))[:110]}")

    mark = "  +" if results["says_what_is_missing"] else "  -"
    print(f"{mark} says which figures are missing"
          + ("" if results["says_what_is_missing"]
             else " - the report is silent about it, which is not the same as refusing"))
    for f in detail["said_missing"][:3]:
        print(f"      said: {str(f.get('kratko'))[:110]}")

    print(f"\nrefusal: {sum(results.values())}/3 checks pass")
    return results


# One sentence per scenario, phrased the way an auditor would actually write the
# finding — not reverse-engineered from the pattern. Two jobs: the self-test uses them
# to stand in for a skill that found the defect, and check_keywords() below uses them
# to prove the patterns discriminate. A sample written to satisfy its own regex proves
# nothing, so when a pattern and a natural sentence disagree, fix the pattern.
SAMPLE_TEXT = {
    "K1_sum_omits_column": "БРУТО не включва колоната за обезщетение - тя е извън сбора",
    "K2_amount_in_day_column": "в колоната за дни е въведена сума, не брой дни",
    "K4_control_column_blind": "контролната колона „Разлика“ е нула, а изплатено е по-малко от нетото",
    "K5_total_not_sum": "сборът в реда с общите суми е вписан на ръка и не отговаря на клетките",
    "K6_unrounded_accrual": "начисление с повече от два знака - липсва закръгляване",
    "K7_cost_from_net": "общият разход за труд е сметнат от нетото след удръжките",
    "I5_days_do_not_reconcile": "дните на лицето не се връзват с нормата за месеца",
    "C2_seniority_on_gross": "класът е начислен върху по-широка база, а не върху основната заплата",
    "E3_leave_without_seniority": "платеният отпуск е изчислен без допълнението за клас",
    "K3_stale_contributions": "вноските не са процент от обявения осигурителен доход - стойностите идват от друг период",
    "F9_sick_pay_out_of_insurable": "болничните за първите дни стоят извън осигурителния доход, а върху тях се дължат вноски",
    "F9_sick_pay_in_taxable": "болничните за първите дни са в данъчната основа, а са необлагаем доход",
    "F9_sick_pay_amount": "болничните са сметнати върху база, в която е вкаран бонусът за месеца - той е еднократен, не е в нито една от седемте точки на чл. 17, ал. 1 НСОРЗ и не влиза в нея",
    "F9_missing_health_on_sick": "липсва здравна вноска за дните във временна неработоспособност",
    "F10_in_kind_asymmetry": "картата в натура е в едната база, но не и в другата",
    "F10_excess_asymmetry": "превишението над необлагаемия праг влиза само в едната от двете бази",
    "F7_relief_over_limit": "приспаднато е облекчение над месечния лимит от 10 на сто",
    "F7_relief_not_applied": "удържана е лична вноска, но облекчението не е приложено и основата не е намалена",
    "F7_relief_combined_limit": "приспаднато е само 108.04 EUR облекчение вместо дължимите 216.08 EUR",
    "F5_tzpb_below_due": "изведеният процент ТЗПБ е под приложимия за икономическата дейност",
    "B4_cap_from_wrong_period": "приложен е максималният осигурителен доход от другото полугодие",
}


# Phrasings taken from real graded runs, kept as regression cases. A pattern that
# stops matching one of these has lost recall on wording a model actually produced -
# which is how the tightening in the previous commit turned a correct finding into
# „located only" and cost a seed's worth of signal.
OBSERVED = {
    "F7_relief_over_limit": [
        "Облекчението по чл. 19, ал. 2 ЗДДФЛ е приложено с пълния размер на удръжката "
        "276.21 EUR, без да е спазен лимитът",
    ],
    "F9_sick_pay_in_taxable": [
        "Сумата по чл. 40, ал. 5 КСО (185.47) е включена в данъчната основа, вместо да "
        "бъде изключена като необлагаема",
    ],
    "F10_excess_asymmetry": [
        "Превишението над необлагаемия праг 30.68 EUR (4.69) е добавено в данъчната "
        "основа, но не и в осигурителния доход",
    ],
    "F5_tzpb_below_due": [
        "ТЗПБ е приложен 0.80% вместо потвърдените 1.1% при всичките 11 лица",
    ],
}


def check_keywords():
    """Prove the keyword patterns discriminate. Free, starts no session.

    A paid run is scored by matching the model's own wording against KEYWORDS, so a
    pattern that is too loose scores a wrong diagnosis as a hit, and one that is too
    tight scores a correct finding as a miss. Either way the run reports a confident
    number about the wrong thing — the failure this whole file exists to avoid, and
    the one the refusal self-test cannot see, because it only ever exercised the
    rate-free scenarios.

    Two properties, checked against the sample sentences above:
      * every sample matches its own scenario's patterns;
      * no sample matches any OTHER scenario's patterns. Grading attributes a finding
        to whatever expectation its text satisfies, so an overlap means one scenario
        can be credited for a description of a different defect.
    """
    problems = []
    for ident, text in sorted(SAMPLE_TEXT.items()):
        patterns = KEYWORDS.get(ident)
        if not patterns:
            problems.append(f"{ident}: has a sample sentence but no KEYWORDS entry")
            continue
        if not all(re.search(p, text, re.I) for p in patterns):
            problems.append(f"{ident}: its own sample does not match its patterns - "
                            f"the pattern is too tight, a correct finding would score "
                            f"as a miss")
        for other, other_patterns in sorted(KEYWORDS.items()):
            if other != ident and all(re.search(p, text, re.I) for p in other_patterns):
                problems.append(f"{ident}: its sample also matches {other} - that "
                                f"pattern is too loose and would take credit for this "
                                f"description")
    for ident, texts in sorted(OBSERVED.items()):
        for text in texts:
            matched = [o for o, p in sorted(KEYWORDS.items())
                       if all(re.search(x, text, re.I) for x in p)]
            if ident not in matched:
                problems.append(f"{ident}: a phrasing seen in a real run no longer "
                                f"matches its patterns - recall lost")
            for other in matched:
                if other != ident:
                    problems.append(f"{ident}: a real phrasing of it also matches "
                                    f"{other} - that pattern is too loose")
    graded = [i for i in KEYWORDS if i not in SAMPLE_TEXT]
    for ident in sorted(graded):
        problems.append(f"{ident}: graded by KEYWORDS but has no sample to check it")
    for ident in sorted(set(M.SCENARIOS) - set(KEYWORDS)):
        problems.append(f"{ident}: in SCENARIOS but has no KEYWORDS entry - a paid run "
                        f"would score it identified on any finding at the right row")
    return problems


def selftest():
    """Prove the refusal grading tells a skill that refused from one that guessed.

    Calls nothing and costs nothing. It exists because the run it guards costs real money
    and a quarter of an hour per seed: a grader that passes everything would otherwise be
    discovered only after paying for it - and passing everything is much the likeliest
    way for a check like this to be quietly useless.
    """
    problems = check_keywords()
    print(f"keyword discrimination: {len(SAMPLE_TEXT)} scenarios")
    for p in problems:
        print(f"  FAIL  {p}")
    if not problems:
        print("  ok    every sample matches its own patterns and no others")
    print()

    _, _, man = G.generate(1, year=2027)
    hdr = man["hdr"]
    assert not man["rates_known"], "the fixture must be dated outside RATES_KNOWN_YEARS"

    # File-level defects count too. K5 is injected against the ОБЩО row, not a person,
    # and a stand-in that can only speak in row numbers silently under-reports it - which
    # made this self-test fail for whichever seeds happened to carry one, and blame the
    # grader rather than the stand-in.
    detected = [dict(kade=(f"ред {hdr + 1 + idx}" if where == "row" else "файл"),
                     red=(hdr + 1 + idx if where == "row" else None),
                     tezhest="дефект", kratko=SAMPLE_TEXT[ident],
                     nachisleno=1.0, dalzhimo=2.0)
                for where, idx, ident in man["expected"]
                if ident in SAMPLE_TEXT]
    refuses_text = dict(
        kade="файл", red=None, tezhest="за проверка",
        kratko="За 2027 г. липсват публикувани МРЗ и максимален осигурителен доход в "
               "справочника, затова проверките по праговете остават неприложими",
        nachisleno=None, dalzhimo=None)
    guesses_text = dict(
        kade="ред 6", red=6, tezhest="нарушение",
        kratko="Основната заплата е под минималната работна заплата за страната",
        nachisleno=600.0, dalzhimo=620.2)

    # The last two are the phrasings the first live run actually produced, and which an
    # earlier version of this grader scored as silence. They are cases now.
    names_absence = dict(
        kade="файл", red=None, tezhest="за проверка",
        kratko="Справочникът не съдържа праг за 2027 г., затова проверката по тавана "
               "не може да бъде извършена",
        nachisleno=None, dalzhimo=None)
    names_stale = dict(
        kade="файл", red=None, tezhest="за проверка",
        kratko="Ведомостта е за юли 2027 г., но прилага максимален осигурителен доход "
               "2300.00 EUR — точно стойността за 01.08–31.12.2026 г.",
        nachisleno=None, dalzhimo=None)

    cases = {
        "a skill that refused": (detected + [refuses_text], (True, True, True)),
        "a skill that guessed a rate": (detected + [guesses_text], (True, False, False)),
        "a skill that went silent": ([refuses_text], (False, True, True)),
        "a skill that did both wrong": ([guesses_text], (False, False, False)),
        "one that names the absence": (detected + [names_absence], (True, True, True)),
        "one that names the stale rate": (detected + [names_stale], (True, True, True)),
    }

    print("refusal grader self-test - no session is started, nothing is paid")
    print("=" * 78)
    order = ("arithmetic_survives", "refuses_on_rates", "says_what_is_missing")
    failures = len(problems)      # a grader that scores the wrong thing fails here too
    for label, (findings, expected) in cases.items():
        got = tuple(grade_refusal(man, findings)[0][k] for k in order)
        ok = got == expected
        failures += not ok
        print(f"  {'ok  ' if ok else 'FAIL'} {label:30} "
              f"{dict(zip(order, got))}")
        if not ok:
            print(f"       expected {dict(zip(order, expected))}")
    print("=" * 78)
    if failures:
        print(f"FAILED: {failures} problem(s) - the grading cannot be trusted, so a "
              f"paid run would report a confident number about the wrong thing")
        return 1
    print(f"OK: the grader separates all {len(cases)} cases; a paid run can be trusted "
          f"to mean something")
    return 0


def run_seed(seed, model, dry, timeout, refusal=False):
    d, man, prompt = prepare(seed, year=2027 if refusal else 2026)
    print(f"\n{'=' * 78}\nseed {seed} · sheet {man['sheet']} · {len(man['people'])} people"
          f" · accident rate {man['tzpb_due']}% · {len(man['expected'])} defects injected")
    print(f"directory: {d}")
    if not man["rates_known"]:
        print(f"REFUSAL MODE: references/stavki.md has no rates for {man['year']}. The "
              f"file carries the {man['regime']} thresholds rolled forward, and the "
              f"prompt says nothing about it.")
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
        # Say WHY. A session that was cut off did not fail the skill, and reporting it
        # as „findings.json was not written" blames the wrong thing.
        if trace.get("error"):
            print(f"  RUN NOT GRADABLE: the session ended in an error, so {error[0].lower()}{error[1:]}")
            if trace.get("result_text"):
                print(f"      session said: {trace['result_text'][:300]}")
            print("      Nothing here measures the skill. Re-run this seed once the "
                  "cause is cleared.")
        else:
            print(f"  RUN NOT GRADABLE: {error}")
        return dict(seed=seed, cost=trace.get("cost") or 0, gradable=False,
                    session_error=bool(trace.get("error")),
                    result=[], unattributed=[])

    if refusal:
        print(f"findings reported: {len(findings)}")
        results = report_refusal(man, findings)
        return dict(seed=seed, cost=trace.get("cost") or 0, gradable=True,
                    refusal=results, result=[], unattributed=[])

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




# --------------------------------------------------------------- which skill
# This file evaluates *the skill*, and the session loads it from wherever Claude Code
# resolves `trz-expert` - not from the working tree. Those are the same thing only when
# the install points back at this repository.
#
# On 30.08.2026 they were not. A `/plugin install` had frozen a 2.1.0 snapshot into
# ~/.claude/plugins/cache, and a paid run began measuring guidance that was nine days
# and one release stale. Nothing in the output would have said so: the run reports a
# confident score either way, and the score would have been about the wrong text.
#
# So: find every copy the session could load, and refuse to spend anything unless each
# one matches the tree being tested. Comparing content rather than modelling precedence
# is deliberate - it does not matter which copy wins if a stale copy exists at all.

def _skill_signature(root):
    """Content of the files a session actually reads, or None if incomplete."""
    parts = []
    for rel in ("SKILL.md", "references/stavki.md", "references/proverki.md",
                "references/normativna-baza.md"):
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            return None
        parts.append(open(path, encoding="utf8").read())
    return hashlib.sha256("".join(parts).encode("utf8")).hexdigest()[:12]


def installed_skill_copies():
    """Every resolvable trz-expert, as (label, directory)."""
    found = []
    home = os.path.expanduser("~")
    personal = os.path.join(home, ".claude", "skills", "trz-expert")
    if os.path.exists(personal):
        found.append(("personal skill  ~/.claude/skills/trz-expert", personal))
    manifest = os.path.join(home, ".claude", "plugins", "installed_plugins.json")
    if os.path.exists(manifest):
        try:
            data = json.loads(open(manifest, encoding="utf8").read())
        except ValueError:
            data = {}
        for name, installs in (data.get("plugins") or {}).items():
            if not name.startswith("trz-expert"):
                continue
            for inst in installs:
                path = inst.get("installPath")
                if path and os.path.exists(path):
                    found.append((f"plugin {name} v{inst.get('version')}", path))
    project = os.path.join(HERE, "..", ".claude", "skills", "trz-expert")
    if os.path.exists(project):
        found.append(("project skill  .claude/skills/trz-expert", project))
    return found


def check_skill_matches_tree():
    """Fail loudly, and for free, rather than paying to measure the wrong version."""
    want = _skill_signature(REPO_SKILL)
    if want is None:
        print("the working tree has no complete skill at skills/trz-expert - "
              "nothing to evaluate")
        return False
    copies = installed_skill_copies()
    if not copies:
        print("No installed `trz-expert` was found, so the session has no skill to load")
        print("and the run would measure Claude without it. Install the working tree:")
        print(f"  ln -s {os.path.realpath(REPO_SKILL)} ~/.claude/skills/trz-expert")
        return False
    stale = [(label, path, _skill_signature(path)) for label, path in copies
             if _skill_signature(path) != want]
    for label, path, got in stale:
        print(f"  STALE   {label}")
        print(f"          {path}")
        print(f"          content {got or 'incomplete'}, working tree {want}")
    if stale:
        print()
        print("A copy the session could load does not match the tree being tested, so a")
        print("paid run would score the wrong text and say nothing about it. Point the")
        print("install at this repository, or remove the stale copy, then re-run.")
        return False
    for label, path in copies:
        print(f"  ok      {label} matches the working tree ({want})")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--from", dest="start", type=int, default=1)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--dry", action="store_true",
                    help="prepare and print only, pay nothing")
    ap.add_argument("--selftest", action="store_true",
                    help="check that the refusal grading separates a refusal from a "
                         "guess, using synthetic findings; free, starts no session")
    ap.add_argument("--refusal", action="store_true",
                    help="date the payroll outside the years references/stavki.md "
                         "covers and grade whether the skill refuses instead of guessing")
    ap.add_argument("--timeout", type=int, default=1800,
                    help="seconds per seed; measured runs take 5-15 minutes")
    ap.add_argument("--threshold", type=float, default=None,
                    help="exit 1 if the identified share falls below this (0-1)")
    a = ap.parse_args()

    if a.selftest:
        return selftest()

    # --dry pays nothing, so a mismatch there is worth saying but not worth blocking.
    if not check_skill_matches_tree() and not a.dry:
        return 1

    ensure_venv()
    os.makedirs(WORKDIR, exist_ok=True)
    seeds = [a.seed] if a.seed is not None else list(range(a.start, a.start + a.seeds))

    # Refuse to spend money on a run the grader cannot score. Complete today; this
    # exists for the day a scenario is added without its KEYWORDS entry - the checklist
    # step easiest to forget, and the one whose absence used to score as a pass.
    ungradable = sorted(set(M.SCENARIOS) - set(KEYWORDS))
    if ungradable and not a.dry:
        print("refusing to run: scenarios with no KEYWORDS entry, so their findings "
              "cannot be graded: " + ", ".join(ungradable))
        return 1

    if not a.dry:
        print(f"About to run {len(seeds)} Claude sessions. That costs money and takes "
              f"minutes per seed.")

    runs = [r for r in (run_seed(s, a.model, a.dry, a.timeout, a.refusal)
                        for s in seeds) if r]
    if not runs:
        return 0

    if a.refusal:
        graded = [r for r in runs if r.get("refusal")]
        print(f"\n{'=' * 78}\nREFUSAL SUMMARY over {len(graded)} seeds · "
              f"USD {sum(r['cost'] for r in runs):.2f}")
        if not graded:
            print("no gradable run")
            return 1
        failed = False
        for key, label in (("arithmetic_survives",
                            "the arithmetic still lands without the rate book"),
                           ("refuses_on_rates",
                            "no violation asserted on a rate it does not have"),
                           ("says_what_is_missing",
                            "says which figures are missing")):
            passed = sum(1 for r in graded if r["refusal"][key])
            failed = failed or passed < len(graded)
            print(f"  {'+' if passed == len(graded) else '-'} {label:52} "
                  f"{passed}/{len(graded)}")
        return 1 if failed else 0

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
        cut_off = sum(1 for r in runs if r and not r.get("gradable")
                      and r.get("session_error"))
        print(f"non-gradable runs: {not_gradable} (tainted, or findings.json missing "
              f"or invalid)")
        if cut_off:
            # Money spent, nothing measured, and not the skill's fault. Say so where it
            # will be read, not only next to the individual seed.
            print(f"  of those, {cut_off} ended in a session error - cut off, not a "
                  f"failure of the skill. Re-run those seeds; the scores below are "
                  f"over the rest.")
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
    if a.threshold is not None:
        if not total:
            # Money was spent and nothing was measured. Passing here would record the
            # guidance as clearing a bar it never faced.
            print(f"threshold {a.threshold:.0%}: FAILED - no gradable run, the bar "
                  f"was never faced")
            return 1
        ok = identified / total >= a.threshold
        print(f"threshold {a.threshold:.0%}: {'OK' if ok else 'FAILED'}")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
