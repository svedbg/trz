# -*- coding: utf-8 -*-
"""Evaluates the skill itself: runs Claude over a generated payroll and maps the
findings it reports back onto the manifest.

    python test/eval_skill.py --dry            # what would be sent, paying nothing
    python test/eval_skill.py --seeds 3        # three seeds
    python test/eval_skill.py --seed 42
    python test/eval_skill.py --seeds 5 --model sonnet
    python test/eval_skill.py --selftest       # free: checks the refusal grading itself
    python test/eval_skill.py --refusal        # can the skill refuse rather than guess?
    python test/eval_skill.py --regrade        # free: re-grade saved results with the current keywords

IT COSTS MONEY, and the amount depends on the model. Measured on 04.09.2026: Claude
Fable 5.1 ~USD 4.5-6.2 per seed (16-25 turns, 11-15 minutes); Claude Sonnet 5
~USD 1.5-2.2 per seed, at a lower identified rate - see scenarios.md for the
comparison. Use --dry to see what will happen before paying.

**Without `--model` the session runs on whatever model the `claude` CLI is currently
configured to use, which is not a property of this file and can change under it.** On
05.09.2026 a batch meant for Fable ran on Sonnet 5 for that reason and the numbers,
read against Fable's band, looked like a regression the release had not caused. So the
model is now read back out of the transcript, printed, and saved with the score.

How this differs from the other suites. They test the rules - arithmetic,
thresholds, composition logic - with independent Python against a generated
payroll. This one tests the guidance. Rewrite SKILL.md badly and only this will
show it.

Isolation, and why it is not complete. The model gets a directory in /tmp with
two files: the payroll and the contracts. The manifest - the answer key - is
deleted from the repository the moment it is generated and lives only in this
process, the repository is not passed with --add-dir, and the openpyxl environment
is a separate venv outside it. The reason is blunt: `test/` holds a full
implementation of every check; reading it measures reading, not expertise.

Except the skill is installed as a symlink into that same repository, and the
model legitimately reads its reference files. So a path to `test/` exists and
cannot be closed without closing the skill itself. Isolation is therefore backed
by **detection**: the whole tool stream is recorded and checked - the inputs for
a path into the checking code, the results for the answer key's own vocabulary.
A run that reached either is reported as tainted and does not enter the statistics.

What survives the run. Every graded seed is written to RESULTS_DIR as one JSON
file - manifest, findings, grades, cost, and the signatures of the skill, the
keyword universe and the generator it was measured under - so an interrupted
batch keeps what it paid for, and --regrade can re-score the saved findings
against the current keywords without regenerating anything.

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

The keyword tables themselves, and every other pure-data constant (sample sentences,
isolation regexes), live in `eval_scenarios.py` (split out 06.09.2026) - this file is
the runner, the grader and the CLI; that one is only ever imported, never run on its
own.
"""
import argparse
import hashlib
import csv
import glob
import json
import os
import random
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
from eval_scenarios import (                                   # noqa: E402
    KEYWORDS, PAIR_KEYWORDS, PAIR_OBSERVED, PAIR_SAMPLE_TEXT, RATE_FREE,
    RATE_DEPENDENT, SAYS_MISSING, SAYS_PERIOD, FORBIDDEN, LEAKED,
    KOMPLEKT_KEYWORDS, ASSERTING, DENIES, _COMPARISON, UNRESOLVED_IS_RIGHT,
    NOTE_IS_RIGHT_FOR_GROUP, SAMPLE_TEXT, OBSERVED, MISREAD,
)

VENV = "/tmp/trz-eval-venv"          # venv with openpyxl, outside the repository
WORKDIR = "/tmp/trz-eval"            # one directory per run
# One JSON per graded seed. Outside the isolated seed directories on purpose: the
# session must not see it, and the `leftovers` assert in prepare() guards only those.
RESULTS_DIR = os.path.join(WORKDIR, "results")
REPO_SKILL = os.path.join(HERE, "..", "skills", "trz-expert")

# Every seed is a real Claude session. scenarios.md records the measured cost of one;
# a run of more than this many needs --allow-expensive, because `--seeds 300` is what
# every other suite in this directory takes and here it would be a four-figure bill
# after one printed line.
EST_USD_PER_SEED = 5.0    # Claude Fable 5.1, the default; roughly a third on Sonnet 5
MAX_SEEDS_UNCONFIRMED = 10

# --------------------------------------------------------------- refusal mode
# The skill's first rule is that no rate comes from memory: a figure the reference file
# does not carry downgrades the finding to `за проверка` instead of being guessed. That
# is the loudest promise this project makes and the one nothing could test, because the
# Python suites always hand it a period the reference file covers. `--refusal` dates the
# payroll outside RATES_KNOWN_YEARS and asks three questions.


def says_what_is_missing(text):
    """Does the finding name a gap AND the rate it concerns, in the same breath?

    Both patterns matching somewhere in the text was not enough: „липсва формула в
    колоната. Таванът е приложен на всеки ред" satisfied it across two sentences that
    have nothing to do with each other. A clause ends at a full stop or a semicolon -
    one not followed by a digit, so that „2300.00" and „07.2027" stay whole.
    """
    for clause in re.split(r"[.;](?!\d)", str(text)):
        if SAYS_MISSING.search(clause) and SAYS_PERIOD.search(clause):
            return True
    return False


def names_a_stale_rate(text, year):
    """Does the finding hold this payroll's year up against another year's figure?

    Cheaper and steadier than matching the wording: a sentence that mentions both 2027
    and 2026 and names a rate has noticed the mismatch, however it chose to phrase it.
    The rate is required - two years in one sentence are also how a formula's history
    or a contract date gets described.
    """
    years = set(re.findall(r"\b(20\d\d)\b", str(text)))
    return (str(year) in years and len(years) > 1
            and bool(RATE_DEPENDENT.search(str(text))))


def ensure_venv():
    if os.path.exists(os.path.join(VENV, "bin", "python")):
        return
    subprocess.run(["python3", "-m", "venv", VENV], check=True)
    subprocess.run([os.path.join(VENV, "bin", "pip"), "install", "--quiet", "openpyxl"],
                   check=True)


def _generate(module, seed, **kw):
    """Generate a fixture and hand back the workbook bytes and the manifest.

    The generator writes both into test/tmp inside the repository, and the manifest IS
    the answer key. The session reaches the repository through the skill symlink (see
    the module docstring), and prepare() used to leave the manifest there for the whole
    run while screening only the tool inputs for its name. Neither copy outlives this
    call now: the workbook goes to the isolated directory from memory and the manifest
    lives in this process - and, once graded, in RESULTS_DIR, outside anything the
    session can see.
    """
    xlsx, manifest_path, man = module.generate(seed, **kw)
    with open(xlsx, "rb") as f:
        data = f.read()
    for path in (xlsx, manifest_path):
        os.remove(path)
    return data, man


def seed_dir(seed, pair=False, dry=False, refusal=False):
    """Where a seed's session runs.

    A dry run builds into its own `dry-` directory: --dry calls prepare(), and prepare()
    empties the directory first, so looking at what WOULD be sent used to delete the
    transcript - stream.jsonl, findings.json - of a paid run of the same seed. A refusal
    run has its own `refusal-` prefix for the same reason: it shared `seed-N` with the
    wide run of the same seed, and the first paid batch ended with `--refusal --seed 3`
    refusing to start because the wide seed 3 had just been paid for in that directory.
    """
    return os.path.join(WORKDIR, f"{'dry-' if dry else ''}{'refusal-' if refusal else ''}"
                                 f"{'pair' if pair else 'seed'}-{seed}")


def komplekt_dir(seed, dry=False):
    return os.path.join(WORKDIR, f"{'dry-' if dry else ''}komplekt-{seed}")


# A session that could not start or was cut short for a reason outside the skill: the
# account's spend limit, a rate limit, no credits. The first paid batch hit the spend
# limit inside seed 1 and then paid a turn for each remaining seed to be told the same
# thing; the batch stops at the first such answer instead.
LIMIT_HIT = re.compile(r"spend limit|rate limit|usage limit|out of credits|quota", re.I)


class SessionUnavailable(RuntimeError):
    pass


def has_paid_run(d):
    """A directory holding stream.jsonl was paid for; nothing here overwrites it quietly."""
    return os.path.exists(os.path.join(d, "stream.jsonl"))


def _claim(d, overwrite):
    """Empty the directory, unless it holds a paid transcript and --overwrite was not given."""
    if has_paid_run(d) and not overwrite:
        raise FileExistsError(
            f"{d} holds the transcript of a paid run (stream.jsonl). Pass --overwrite to "
            f"replace it, or move it aside first.")
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)


def prepare(seed, year=2026, dry=False, overwrite=False):
    """Generate a payroll and place it alone in an isolated directory."""
    d = seed_dir(seed, dry=dry, refusal=year not in M.RATES_KNOWN_YEARS)
    _claim(d, overwrite)
    # Pinned, not drawn from the seed: the eval runs the skill from a clone or a
    # symlink, where the plugin's install-time question was never asked and SKILL.md
    # documents the default - an uncharacterised bonus stays out of the base. Letting
    # the fixture pick the other reading would grade the skill against a configuration
    # it does not have.
    data, man = _generate(G, seed, year=year, bonus_in_base=False)
    with open(os.path.join(d, "vedomost.xlsx"), "wb") as f:
        f.write(data)
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


def prepare_pair(seed, dry=False, overwrite=False):
    """Generate a two-month payroll and place it alone in an isolated directory.

    The wide fixture cannot hold the cross-month material - the чл. 177/чл. 18 leave
    base, a sheet copied forward with last period's thresholds, a jump with no annex -
    and until this existed, three scenarios and the whole 2.4.0 correction had never
    faced a live session. The manifest handed back carries the PAIR keyword universe,
    so grade() competes only the identifiers this fixture can contain.
    """
    import generate_pair as P
    d = seed_dir(seed, pair=True, dry=dry)
    _claim(d, overwrite)
    data, man = _generate(P, seed, bonus_in_base=False)   # pinned; see prepare()
    with open(os.path.join(d, "vedomost.xlsx"), "wb") as f:
        f.write(data)
    early, late = man["sheets"]
    with open(os.path.join(d, "dogovori.csv"), "w", newline="", encoding="utf8") as f:
        w = csv.writer(f)
        w.writerow(["Име", "Основна месечна заплата по договор", "Клас %"])
        for p_ in early["people"]:
            w.writerow([p_["name"], f"{p_['inputs']['monthly_salary']:.2f}",
                        p_["inputs"]["seniority_pct"]])

    # The prompt says that there are two months of the same people and that each is to
    # be checked on its own and against the other - and stops there. Until 2026-09-03
    # it went on: „базата за платения отпуск, праговете и нормата на всеки лист,
    # движението на заплатите между месеците" - the three categories this fixture
    # injects, in order. That is the catalogue the module docstring promises the model
    # never sees, and a score under it measured how well the skill follows a hint.
    # Pair scores from before this change are not comparable with those after it;
    # scenarios.md says so.
    prompt = f"""Направи ТРЗ проверка на ведомостта ./vedomost.xlsx. Ползвай скила trz-expert.

Файлът носи ДВА листа - {early['sheet']} и {late['sheet']} - един и същи състав. Провери
всеки месец поотделно И двата един срещу друг.

Какво имаш от дружеството:
- ./dogovori.csv - договорените основни месечни заплати и процентът клас по трудов договор
- приложимият процент ТЗПБ по КИД на дружеството е {man['sheets'][0]['tzpb_due']}%
- валутата е EUR

Работи само в тази директория. За Python ползвай {VENV}/bin/python - има openpyxl.

Освен обичайния отчет, запиши накрая и findings.json в тази директория: масив, по един
обект за всяка находка, само това и нищо друго във файла. За находка по конкретно лице
посочи реда му в листа {late['sheet']}; за находка за целия файл или за цял лист пиши
"файл".

[{{"kade": "ред 12" или "файл", "red": 12 или null,
  "tezhest": "нарушение|риск|за проверка|дефект|бележка",
  "kratko": "едно изречение какво е сбъркано",
  "nachisleno": число или null, "dalzhimo": число или null}}]
"""
    with open(os.path.join(d, "prompt.txt"), "w", encoding="utf8") as f:
        f.write(prompt)

    graded = dict(seed=seed, sheet=f"{early['sheet']}+{late['sheet']}",
                  year=man["year"], regime=late["regime"], rates_known=True,
                  tzpb_due=late["tzpb_due"], hdr=late["hdr"],
                  total_row=late["total_row"], people=late["people"],
                  expected=man["cross_expected"], keywords=PAIR_KEYWORDS)
    return d, graded, prompt


def prepare_komplekt(seed, dry=False, overwrite=False):
    """Build a whole month's set of documents and place it in an isolated directory.

    This is the fixture the reconciliation checks needed and never had. Everything the
    other modes send is one workbook, so I9, I10 and the cross-document half of A9 were
    prose no session had ever been asked to apply. Here the payroll itself is **clean** -
    every row computed by `trz_model` - and the defects are in the chain below it, which
    also makes the run a false-positive test on the payroll: a finding on a row is
    unattributed by construction.
    """
    import generate_komplekt as GK
    d = komplekt_dir(seed, dry=dry)
    _claim(d, overwrite)
    # Four of the six groups per set, chosen by the seed - the same shape as the wide
    # fixture drawing its defects, and one break per group so every finding stays
    # attributable (`komplekt_test.py` proves that separability).
    chosen = GK.breaks_for_seed(seed)
    k, man = GK.build(chosen, d, seed=seed)

    expected = []
    for ident in chosen:
        idx = k["hit"].get(ident)
        expected.append(["file" if idx is None else "row", idx, ident])

    prompt = f"""Направи ТРЗ проверка на комплекта документи в тази директория. Ползвай скила trz-expert.

Какво имаш за месец {man['month']:02d}.{man['year']} г.:
- ./vedomost.xlsx - ведомостта
- ./dogovori.csv - идентификатор, договорена основна заплата, клас % и банкова сметка
- ./deklaracia_1.csv - подадената Декларация обр. 1, по лице
- ./deklaracia_6.csv - подадената Декларация обр. 6, сборно по вид задължение
- ./plateni.csv - какво е излязло по банка: заплатите по лица и преводите към НАП
- приложимият процент ТЗПБ по КИД на дружеството е {man['tzpb']}%
- валутата е EUR

Работи само в тази директория. За Python ползвай {VENV}/bin/python - има openpyxl.

Освен обичайния отчет, запиши накрая и findings.json в тази директория: масив, по един
обект за всяка находка, само това и нищо друго във файла. За находка по конкретно лице
посочи реда му във ведомостта; за находка, засягаща повече от едно лице или цял
документ, пиши "файл".

[{{"kade": "ред 12" или "файл", "red": 12 или null,
  "tezhest": "нарушение|риск|за проверка|дефект|бележка",
  "kratko": "едно изречение какво е сбъркано",
  "nachisleno": число или null, "dalzhimo": число или null}}]
"""
    with open(os.path.join(d, "prompt.txt"), "w", encoding="utf8") as f:
        f.write(prompt)

    graded = dict(seed=seed, sheet=man["sheet"], year=man["year"],
                  regime=None, rates_known=True, tzpb_due=man["tzpb"],
                  hdr=man["header_row"],
                  total_row=man["header_row"] + 1 + man["people"],
                  people=[{"name": p["name"]} for p in k["people"]],
                  expected=expected, keywords=KOMPLEKT_KEYWORDS,
                  month=man["month"], breaks=chosen)
    return d, graded, prompt


def invoke(d, model=None, timeout=1800):
    """Run the session with streaming, so that what it touched stays visible."""
    # Bash is allowed for two things only - the openpyxl venv and a listing - in Claude
    # Code's permission-rule form `Bash(<prefix>:*)`. Under acceptEdits an unrestricted
    # Bash was the one tool that could reach anything on the machine; a non-interactive
    # session has nobody to answer the prompt for a command outside these rules, so it
    # is denied. Not yet exercised live: the change was made from the documentation.
    cmd = ["claude", "-p", open(os.path.join(d, "prompt.txt"), encoding="utf8").read(),
           "--output-format", "stream-json", "--verbose",
           "--permission-mode", "acceptEdits",
           "--allowedTools", "Read", "Write", "Edit", "Glob", "Grep",
           # Both names, not just the one the prompt tells the model to use: a live
           # Sonnet 5 refusal run (seed 7, 04.09.2026) called `python3` instead of
           # `python`, got "This command requires approval" five times running the
           # same script, gave up and asked the (nonexistent, -p has none) user for
           # approval instead of writing findings.json - USD 0.47 spent, nothing
           # measured. `Bash(<path>:*)` matches the exact program name, not a string
           # prefix, so `…/python:*` never covered `…/python3`.
           f"Bash({VENV}/bin/python:*)", f"Bash({VENV}/bin/python3:*)", "Bash(ls:*)",
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
    scan_stream(os.path.join(d, "stream.jsonl"), trace)
    if timed_out:
        trace.update(error=True,
                     result_text=f"killed after {timeout} s (--timeout); nothing the "
                                 f"session did after that point exists to grade")
    elif "turns" not in trace:
        trace.update(error=True, stderr=(p.stderr or "")[-500:])
    return trace


def scan_stream(path, trace):
    """Read a session transcript into `trace`: tool calls, what they touched, the result.

    Separate from invoke() so that the screening can be proved on a synthetic
    transcript without starting a session - --selftest does exactly that.
    """
    for line in open(path, encoding="utf8"):
        try:
            event = json.loads(line)
        except Exception:
            continue
        if event.get("type") == "assistant":
            # Which model actually answered. Without --model the CLI picks it, so this
            # is the only place the run's model is stated at all.
            served = event.get("message", {}).get("model")
            if served and served not in trace.setdefault("models", []):
                trace["models"].append(served)
            for c in event.get("message", {}).get("content", []):
                if c.get("type") == "tool_use":
                    trace["tool_calls"] += 1
                    text = json.dumps(c.get("input", {}), ensure_ascii=False)
                    if FORBIDDEN.search(text):
                        trace["touched"].append(f"{c.get('name')}: {text[:120]}")
        elif event.get("type") == "user":
            # Tool results come back as user turns. What they contain is what the
            # session actually saw, however it asked for it - see LEAKED.
            content = event.get("message", {}).get("content")
            for c in content if isinstance(content, list) else []:
                if isinstance(c, dict) and c.get("type") == "tool_result":
                    text = _result_text(c.get("content"))
                    m = LEAKED.search(text)
                    if m:
                        trace["touched"].append(
                            f"tool result carries {m.group(0)!r}: {text[:100]!r}")
        elif event.get("type") == "result":
            # `result` carries the reason when is_error is set - a spend cap, a rate
            # limit, a refusal. Without it a session killed mid-run is indistinguishable
            # from a skill that simply never wrote its answer, and the money is already
            # spent by the time anyone digs through stream.jsonl to tell them apart.
            trace.update(turns=event.get("num_turns"), cost=event.get("total_cost_usd"),
                         error=event.get("is_error"),
                         result_text=str(event.get("result") or "").strip())
    return trace


def _result_text(content):
    """The text of a tool_result block: a string, or a list of typed blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(x.get("text", "")) if isinstance(x, dict) else str(x)
                         for x in content)
    return json.dumps(content, ensure_ascii=False) if content is not None else ""


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
        where = str(finding.get("kade", "")).lower()
        if "файл" in where or "всички редове" in where or "всеки ред" in where \
                or "всички лица" in where:
            return "file"
        # „ред 12" names a row wherever it stands; „лист 08-2026" names a sheet, and the
        # first digit run in it is a month, not a row - it used to be read as row 8.
        # A finding that names TWO OR MORE rows this way ("редове 6, 8, 12 …") is a
        # systemic claim across the file, the same shape as B4/F5/K5/K8's own
        # expectation - crediting it to the first row named threw it away. „без ред 9"
        # names a row EXCLUDED from the finding, not its location, and used to be read
        # as row 9 for exactly that reason.
        rows = set()
        for m in re.finditer(r"ред\w*\s*", where):
            if where[max(0, m.start() - 4):m.start()] == "без ":
                continue
            tail = re.split(r"[(—–;.]", where[m.end():], maxsplit=1)[0]
            rows.update(int(n) for n in re.findall(r"\d+", tail))
        if len(rows) >= 2:
            return "file"
        if len(rows) == 1:
            row = next(iter(rows))
        elif "лист" in where:
            return "file"
        else:
            m = re.search(r"(\d+)", where)
            row = int(m.group(1)) if m else None
    if row is None:
        return "file"
    return "file" if row >= total_row else row


def _numbers_consistent(finding):
    """False only when the finding names both nachisleno and dalzhimo as numbers AND
    they agree - every scenario here is constructed as a genuine discrepancy, so a
    finding whose own two figures match is not asserting the defect it claims to have
    found, whatever its kratko sentence says. This is the one semantic check grade()
    can make without a per-scenario expected amount (trz_model.py's manifest carries
    no such figure - see CONTRIBUTING.md on why a second, driftable copy of one is not
    worth adding for this alone): it costs nothing when either figure is absent
    (most scenarios leave one or both null, which is not this check's concern), and it
    catches a finding that repeats the right words at the right row with a number that
    contradicts its own claim, which no keyword pattern can.
    """
    stated, due = finding.get("nachisleno"), finding.get("dalzhimo")
    if isinstance(stated, (int, float)) and isinstance(due, (int, float)) \
            and not isinstance(stated, bool) and not isinstance(due, bool):
        return abs(stated - due) > 0.005
    return True


def asserts_a_defect(finding, ident=None):
    """Does this finding claim a defect, rather than note, deny or decline one?

    For the scenarios in UNRESOLVED_IS_RIGHT a `за проверка` counts as the claim.
    """
    tezhest = str(finding.get("tezhest", "")).strip().lower()
    allowed = set(ASSERTING)
    if ident in UNRESOLVED_IS_RIGHT:
        allowed.add("за проверка")
    if ident and ident.startswith(NOTE_IS_RIGHT_FOR_GROUP):
        allowed.add("бележка")
    if tezhest not in allowed:
        return False
    if not _numbers_consistent(finding):
        return False
    text = str(finding.get("kratko", ""))
    m = DENIES.search(text)
    if m and _COMPARISON.search(text[:m.start()]):
        return True     # the правилно/коректно names a different row, not this one
    return m is None


def grade(man, findings):
    """Map the findings onto what was injected.

    A single finding may satisfy several expectations at the same location: all
    expectations on one row come from one mutation, and a model that reports both
    aspects in one sentence should not be penalised for being concise.

    Only a finding that asserts a defect can identify one - see asserts_a_defect. A
    note or a denial on the right row leaves the expectation „located only": the
    skill looked there and did not commit.
    """
    HDR, TOTAL = man["hdr"], man["total_row"]
    keywords = man.get("keywords") or KEYWORDS
    expected = [("file" if where == "file" else HDR + 1 + idx, ident)
                for where, idx, ident in man["expected"]]
    expected.sort(key=lambda x: -len(keywords.get(x[1], [])))

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
        if ident not in keywords:
            raise KeyError(f"no KEYWORDS entry for {ident} - the run cannot be graded")
        patterns = keywords[ident]
        hit = None
        for i in here:
            if not asserts_a_defect(findings[i], ident):
                continue
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

    # Case-insensitive: „Нарушение" with a capital is the same verdict, and a live run
    # wrote it that way.
    asserted = [f for f in findings
                if str(f.get("tezhest", "")).strip().lower() == "нарушение"
                and RATE_DEPENDENT.search(str(f.get("kratko", "")))]
    detail["guessed"] = asserted

    said = [f for f in findings
            if says_what_is_missing(f.get("kratko", ""))
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
    universes = ((KEYWORDS, SAMPLE_TEXT, M.SCENARIOS, "wide"),
                 (PAIR_KEYWORDS, PAIR_SAMPLE_TEXT, M.PAIR_SCENARIOS, "pair"))
    for KW, SAMPLES, UNIVERSE, label in universes:
        problems += _check_universe(KW, SAMPLES, UNIVERSE, label)
    # Third property: a sentence that names the subject and says the opposite must not
    # score. grade() already drops denials by severity and by DENIES, but the patterns
    # are what a `нарушение` is scored by, and they used to match on the subject alone.
    for text, must_not in MISREAD:
        for ident in must_not:
            if all(re.search(p, text, re.I) for p in KEYWORDS[ident]):
                problems.append(f"{ident}: matches the opposite finding {text!r} - the "
                                f"pattern names the subject but not the defect")
    return problems


def _check_universe(KEYWORDS, SAMPLE_TEXT, SCENARIOS, label):
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
    # Each universe is judged against phrasings observed in ITS OWN real runs.
    observed = OBSERVED if label == "wide" else PAIR_OBSERVED
    for ident, texts in sorted(observed.items()):
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
    for ident in sorted(set(SCENARIOS) - set(KEYWORDS)):
        problems.append(f"{ident}: in the {label} scenario set but has no KEYWORDS "
                        f"entry - a paid run would score it identified on any finding "
                        f"at the right row")
    return problems


def check_grading():
    """Prove grade() credits only findings that assert a defect. Free, starts no session.

    Seed 1 of the wide fixture supplies the expectations. For each, a finding on the
    right row whose text is the scenario's own sample sentence must score „identified"
    when its severity asserts a defect, and „located only" when it is a `бележка`, a
    `за проверка` the skill did not commit to, or a sentence that names the defect and
    denies it. Until 2026-09-03 all four scored identified. Negated denials -
    „неправилно", „не е коректно" - must still count as assertions, or a correct
    finding is thrown away for its wording.
    """
    problems = []
    _, man = _generate(G, 1, bonus_in_base=False)
    hdr = man["hdr"]

    def finding(where, idx, tezhest, text):
        row = hdr + 1 + idx if where == "row" else None
        return dict(kade=(f"ред {row}" if row else "файл"), red=row, tezhest=tezhest,
                    kratko=text, nachisleno=None, dalzhimo=None)

    for where, idx, ident in man["expected"]:
        sample = SAMPLE_TEXT[ident]
        # A `бележка` identifies a group-K defect (normativna-baza.md allows it there),
        # and a `за проверка` identifies the scenarios whose right answer is one.
        note_ok = ident.startswith(NOTE_IS_RIGHT_FOR_GROUP)
        decline_ok = ident in UNRESOLVED_IS_RIGHT
        variants = (
            ("asserted", "дефект", sample, "identified"),
            ("a note", "бележка", sample, "identified" if note_ok else "located only"),
            ("declined", "за проверка", sample,
             "identified" if decline_ok else "located only"),
            ("a denial", "нарушение", sample + " - проверено, изчислението е коректно",
             "located only"),
            ("a negated denial", "нарушение", sample + " - изчислено е неправилно",
             "identified"),
        )
        for label, tezhest, text, want in variants:
            got = [s for _, i, s, _ in grade(man, [finding(where, idx, tezhest, text)])[0]
                   if i == ident]
            if got != [want]:
                problems.append(f"{ident}: {label} on the right row scored {got}, "
                                f"expected ['{want}']")
    for text in ("класът е неправилно изчислен", "базата не е коректно определена",
                 "облекчението не е приложено коректно", "сумата не съответства на дължимата"):
        if not asserts_a_defect(dict(tezhest="нарушение", kratko=text)):
            problems.append(f"a negated denial was read as a denial: {text!r}")
    for text in ("класът е изчислен коректно", "болничните са правилно определени",
                 "не мога да потвърдя ставката", "сумата е в съответствие с чл. 262"):
        if asserts_a_defect(dict(tezhest="нарушение", kratko=text)):
            problems.append(f"a denial was read as an assertion: {text!r}")
    # A finding that names both figures must have them disagree, or it is not
    # asserting the discrepancy its words claim - see _numbers_consistent's docstring.
    for stated, due, want in ((100.0, 100.0, False), (100.0, 100.005, False),
                              (100.0, 100.5, True), (None, 100.0, True), (None, None, True)):
        f = dict(tezhest="нарушение", kratko="сумата не съответства на дължимата",
                 nachisleno=stated, dalzhimo=due)
        got = asserts_a_defect(f)
        if got != want:
            problems.append(f"nachisleno={stated} dalzhimo={due}: asserts_a_defect="
                            f"{got}, expected {want}")
    # The two "unexplained" scenarios are correctly reported as `за проверка`; every
    # other scenario is not.
    for ident in sorted(UNRESOLVED_IS_RIGHT):
        if not asserts_a_defect(dict(tezhest="за проверка", kratko=SAMPLE_TEXT[ident]), ident):
            problems.append(f"{ident}: a `за проверка` must count as the finding")
    if asserts_a_defect(dict(tezhest="за проверка", kratko=SAMPLE_TEXT["K1_sum_omits_column"]),
                        "K1_sum_omits_column"):
        problems.append("K1_sum_omits_column: a `за проверка` must not count as the finding")
    return problems


def check_isolation():
    """Prove the transcript screen sees a leak in a tool RESULT, not only in a path.

    A synthetic stream, no session: one clean read; one Read whose input names the
    manifest; one Bash whose output carries the manifest's `"expected"` key; one whose
    output carries a scenario identifier. The first must pass and each of the other
    three must taint. Then the other direction: the files the session legitimately
    reads - SKILL.md and the references - must not carry the answer key's vocabulary,
    or every honest run would be thrown away as tainted.
    """
    import tempfile
    problems = []

    def tool_use(name, inp):
        return dict(type="assistant",
                    message=dict(content=[dict(type="tool_use", name=name, input=inp)]))

    def tool_result(content):
        return dict(type="user",
                    message=dict(content=[dict(type="tool_result", content=content)]))

    events = [
        tool_use("Read", dict(file_path="/tmp/trz-eval/seed-1/vedomost.xlsx")),
        tool_result("sheet 07-2026: 12 rows"),
        tool_use("Read", dict(file_path="/home/u/trz/test/tmp/wide_1_manifest.json")),
        tool_result([dict(type="text",
                          text='{"seed": 1, "expected": [["row", 3, "K4_control_column_blind"]]}')]),
        tool_use("Bash", dict(command=f"{VENV}/bin/python -c 'print(1)'")),
        tool_result("F5_tzpb_below_due"),
        dict(type="result", num_turns=3, total_cost_usd=0.0, is_error=False, result="ok"),
    ]
    d = tempfile.mkdtemp(prefix="trz-eval-selftest-")
    try:
        path = os.path.join(d, "stream.jsonl")
        with open(path, "w", encoding="utf8") as f:
            for e in events:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        trace = scan_stream(path, dict(tool_calls=0, touched=[]))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    if trace["tool_calls"] != 3:
        problems.append(f"isolation: 3 tool calls in the transcript, {trace['tool_calls']} counted")
    if len(trace["touched"]) != 3:
        problems.append(f"isolation: a manifest path, an \"expected\" key and a scenario "
                        f"id should each taint - {len(trace['touched'])} did: "
                        f"{trace['touched']}")
    if trace.get("turns") != 3:
        problems.append("isolation: the result event was not read")

    for rel in _skill_files(REPO_SKILL):
        path = os.path.join(REPO_SKILL, rel)
        if not os.path.exists(path):
            continue
        m = LEAKED.search(open(path, encoding="utf8").read())
        if m:
            problems.append(f"isolation: {rel} carries {m.group(0)!r}, so reading the "
                            f"skill itself would taint every run")
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
    grading = check_grading()
    problems += grading
    print(f"grading: only a finding that asserts a defect identifies one")
    for p in grading:
        print(f"  FAIL  {p}")
    if not grading:
        print("  ok    notes, declines and denials on the right row score located only")
    isolation = check_isolation()
    problems += isolation
    print("isolation: the transcript screen reads tool results, not only tool inputs")
    for p in isolation:
        print(f"  FAIL  {p}")
    if not isolation:
        print("  ok    a manifest path, an \"expected\" key and a scenario id each taint; "
              "the skill's own files do not")
    print()

    _, man = _generate(G, 1, year=2027)
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

    # Guesses in other words. Each was graded `нарушение` by a live run and each scored
    # as rate-free while RATE_DEPENDENT wanted the adjective next to its noun; the third
    # also spells the severity with a capital, which used to be a different verdict.
    for label, tezhest, text in (
            ("guessed: минималната заплата за 2027", "нарушение",
             "Основната заплата 600.00 EUR е под минималната заплата за 2027 г. от "
             "620.20 EUR"),
            ("guessed: размер на осигурителния доход", "нарушение",
             "Осигурителният доход надвишава максималния размер на осигурителния доход "
             "за 2027 г."),
            ("guessed: месечно възнаграждение, capital", "Нарушение",
             "Възнаграждението е под минималното месечно възнаграждение за страната")):
        guess = dict(kade="ред 6", red=6, tezhest=tezhest, kratko=text,
                     nachisleno=600.0, dalzhimo=620.2)
        cases[label] = (detected + [guess], (True, False, False))

    # Gaps that are not the gap under test. Each says something is missing and each
    # used to satisfy the third check - through a bare „2027", a bare „ставк", or two
    # unrelated sentences, or two years with no rate between them.
    for label, text in (
            ("gap: формула за 07.2027", "в клетка F12 няма формула за 07.2027"),
            ("gap: часова ставка", "няма посочена часова ставка за извънредния труд"),
            ("gap: in another sentence",
             "липсва формула в колоната за бруто. Таванът е приложен на всеки ред"),
            ("gap: two years, no rate",
             "справочникът за 2027 г. няма стойност за 2027; последната е от 2026 г. за "
             "формулите")):
        gap = dict(kade="файл", red=None, tezhest="за проверка", kratko=text,
                   nachisleno=None, dalzhimo=None)
        cases[label] = (detected + [gap], (True, True, False))

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


# --------------------------------------------------------------- what survives
# Until 2026-09-03 a batch existed only on stdout: Ctrl-C after nine paid seeds lost the
# summary of all nine, and the only way to re-score a run under corrected keywords was to
# pay for it again. Each seed now leaves one JSON file, written the moment it is graded,
# with everything a re-grade or an audit needs - including three signatures, so that a
# saved score can never be mistaken for a score of the current skill, the current
# keywords, or the current fixture generator.

def keywords_sha(universe):
    """Identity of a keyword universe - the repr of the dict, hashed."""
    return hashlib.sha256(repr(universe).encode("utf8")).hexdigest()


def generator_sha(pair, komplekt=False):
    """Identity of the fixture generator the manifest came from."""
    name = ("generate_komplekt.py" if komplekt else
            "generate_pair.py" if pair else "generate_wide.py")
    with open(os.path.join(HERE, name), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _model_slug(model):
    """A filesystem-safe stand-in for the model, "default" when none was given."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", model) if model else "default"


def results_path(mode, seed, model=None):
    """Where one seed's result is saved.

    The model is part of the path since 04.09.2026: a held-out validation batch ran
    Fable and Sonnet on the SAME seed numbers on purpose, for direct comparison, and
    Sonnet's --overwrite run silently clobbered Fable's already-graded wide-30.json -
    same mode, same seed, different model, one path. That result is not recoverable;
    this is why. Existing files from before this change keep their old two-part name
    and are still found and read by --regrade, which globs *.json rather than
    parsing the name.

    Since 05.09.2026 the model is the one that ANSWERED, not the one asked for on the
    command line: without `--model` the flag is None and every such run - Fable's and
    Sonnet's alike - landed on `<mode>-<seed>-default.json`, which is the very
    collision the paragraph above is about, still open in the case where nobody named
    a model.
    """
    return os.path.join(RESULTS_DIR, f"{mode}-{seed}-{_model_slug(model)}.json")


def persist(rec):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = results_path(rec["mode"], rec["seed"],
                        rec.get("model") or rec.get("model_used"))
    with open(path, "w", encoding="utf8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=1)
    print(f"saved: {path}")


def _as_run(rec):
    """The in-memory shape the summaries read, from a saved or a fresh record."""
    return dict(seed=rec["seed"], cost=rec.get("cost") or 0, gradable=rec["gradable"],
                session_error=rec.get("session_error"), result=rec["result"],
                unattributed=rec["unattributed"], refusal=rec.get("refusal"))


def print_graded(graded, unattributed):
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


def run_seed(seed, model, dry, timeout, refusal=False, pair=False, overwrite=False,
             komplekt=False):
    mode = "komplekt" if komplekt else "pair" if pair else "refusal" if refusal else "wide"
    if komplekt:
        d, man, prompt = prepare_komplekt(seed, dry=dry, overwrite=overwrite)
    elif pair:
        d, man, prompt = prepare_pair(seed, dry=dry, overwrite=overwrite)
    else:
        d, man, prompt = prepare(seed, year=2027 if refusal else 2026, dry=dry,
                                 overwrite=overwrite)
    print(f"\n{'=' * 78}\nseed {seed} · sheet {man['sheet']} · {len(man['people'])} people"
          f" · accident rate {man['tzpb_due']}% · {len(man['expected'])} "
          f"{'links broken' if komplekt else 'defects injected'}")
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
    served = trace.get("models") or []
    model_used = served[0] if len(served) == 1 else (", ".join(served) or None)
    print(f"turns {trace.get('turns')} · tool calls {trace['tool_calls']} · "
          f"{trace['seconds']} s · USD {trace.get('cost') or 0:.3f} · "
          f"model {model_used or 'unknown'}")
    if model is None and model_used:
        print(f"  no --model given, so the CLI chose {model_used}; the score belongs "
              f"to that model, not to whichever one you had in mind")
    # The keyword universe is not stored with the manifest: a re-grade attaches the
    # current one by mode, and keywords_sha records which one produced this score.
    rec = dict(seed=seed, mode=mode, model=model, model_used=model_used,
               skill_sig=tree_skill_signature(),
               keywords_sha=keywords_sha(man.get("keywords") or KEYWORDS),
               generator_sha=generator_sha(pair, komplekt),
               manifest={k: v for k, v in man.items() if k != "keywords"},
               findings=None, gradable=False, session_error=bool(trace.get("error")),
               touched=trace["touched"], turns=trace.get("turns"),
               tool_calls=trace["tool_calls"], cost=trace.get("cost") or 0,
               seconds=trace["seconds"], result=[], unattributed=[], refusal=None)

    if trace["touched"]:
        print("  RUN TAINTED: it reached the answers or the checking code -")
        for x in trace["touched"]:
            print(f"      {x}")
        persist(rec)
        return _as_run(rec)

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
        persist(rec)
        if trace.get("error") and LIMIT_HIT.search(str(trace.get("result_text") or "")):
            raise SessionUnavailable(str(trace.get("result_text"))[:200])
        return _as_run(rec)

    rec.update(findings=findings, gradable=True)
    print(f"findings reported: {len(findings)}")
    if refusal:
        rec["refusal"] = report_refusal(man, findings)
    else:
        rec["result"], rec["unattributed"] = grade(man, findings)
        print_graded(rec["result"], rec["unattributed"])
    persist(rec)
    return _as_run(rec)


def summarize_refusal(runs):
    """The batch summary of --refusal runs; returns the exit code."""
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


def scenario_universe(pair=False, komplekt=False):
    """The ids a batch of this mode can grade, in the order the summary prints them.

    Read from the fixture's own catalogue rather than assumed: a komplekt batch used to
    print the summary header and not one row, because its ids are in neither
    `M.SCENARIOS` nor `M.PAIR_SCENARIOS` and the loop simply skipped them. The seeds
    were paid for and graded correctly; only the table at the end was empty.
    """
    if komplekt:
        import generate_komplekt as GK
        return list(GK.ORDER)
    return M.PAIR_SCENARIOS if pair else M.SCENARIOS


def summarize(runs, scenarios, threshold=None):
    """The batch summary of graded runs; returns the exit code."""
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
    for ident in scenarios:
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
    if threshold is not None:
        if not total:
            # Money was spent and nothing was measured. Passing here would record the
            # guidance as clearing a bar it never faced.
            print(f"threshold {threshold:.0%}: FAILED - no gradable run, the bar "
                  f"was never faced")
            return 1
        ok = identified / total >= threshold
        print(f"threshold {threshold:.0%}: {'OK' if ok else 'FAILED'}")
        return 0 if ok else 1
    return 0


def regrade(threshold=None):
    """Re-score every saved result against the CURRENT keywords. Free.

    The findings and the manifest are read from RESULTS_DIR; nothing is regenerated and
    no session starts. For each seed the expectations whose status changed are printed,
    because that difference - not the new total - is what a keyword change is judged by.
    """
    paths = sorted(glob.glob(os.path.join(RESULTS_DIR, "*.json")))
    if not paths:
        print(f"nothing to re-grade: no results in {RESULTS_DIR}")
        return 0
    by_mode = defaultdict(list)
    other_keywords = defaultdict(int)
    for path in paths:
        try:
            with open(path, encoding="utf8") as f:
                rec = json.load(f)
        except ValueError as e:
            print(f"skipping {path}: not valid JSON ({e})")
            continue
        mode = rec.get("mode", "wide")
        run = dict(seed=rec["seed"], cost=rec.get("cost") or 0, gradable=False,
                   session_error=rec.get("session_error"), result=[], unattributed=[],
                   refusal=None)
        if rec.get("gradable") and rec.get("findings") is not None:
            man = dict(rec["manifest"])
            universe = (KOMPLEKT_KEYWORDS if mode == "komplekt" else
                        PAIR_KEYWORDS if mode == "pair" else KEYWORDS)
            if mode in ("pair", "komplekt"):
                # The manifest is re-read from disk, and only the wide fixture's
                # universe is the default inside grade(); every other mode has to
                # attach its own or the re-grade dies on the first id it does not know.
                man["keywords"] = universe
            if rec.get("keywords_sha") != keywords_sha(universe):
                other_keywords[mode] += 1
            run["gradable"] = True
            if mode == "refusal":
                run["refusal"] = grade_refusal(man, rec["findings"])[0]
                before = rec.get("refusal") or {}
                changed = [f"{k} {before.get(k)} -> {v}" for k, v in run["refusal"].items()
                           if before.get(k) != v]
            else:
                run["result"], run["unattributed"] = grade(man, rec["findings"])
                before = {(str(w), i): s for w, i, s, _ in rec.get("result") or []}
                changed = [f"{i} {before.get((str(w), i))} -> {s}"
                           for w, i, s, _ in run["result"] if before.get((str(w), i)) != s]
            if changed:
                print(f"{mode} seed {rec['seed']}: " + "; ".join(changed))
        by_mode[mode].append(run)
    code = 0
    for mode, runs in sorted(by_mode.items()):
        note = (f" · {other_keywords[mode]} saved under different keywords"
                if other_keywords[mode] else "")
        print(f"\n{'=' * 78}\nRE-GRADE · {mode} · {len(runs)} saved seeds in "
              f"{RESULTS_DIR}{note}")
        if mode == "refusal":
            code = summarize_refusal(runs) or code
        else:
            scenarios = scenario_universe(pair=mode == "pair",
                                          komplekt=mode == "komplekt")
            code = summarize(runs, scenarios, threshold) or code
    return code


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

def _skill_files(root):
    """Every file a session reading this skill could load: the four base references
    plus, since 2.14.4, the per-group/per-topic files stavki.md and proverki.md summarise
    and link to rather than carry inline. Listed dynamically - a fifth split later must
    not need a third copy of this enumeration.
    """
    rels = ["SKILL.md", "references/stavki.md", "references/proverki.md",
            "references/normativna-baza.md"]
    for sub in ("proverki", "stavki"):
        subdir = os.path.join(root, "references", sub)
        if os.path.isdir(subdir):
            rels += [f"references/{sub}/{fn}" for fn in sorted(os.listdir(subdir))
                     if fn.endswith(".md")]
    return rels


def _skill_signature(root):
    """Content of the files a session actually reads, or None if incomplete."""
    parts = []
    for rel in _skill_files(root):
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            return None
        parts.append(open(path, encoding="utf8").read())
    return hashlib.sha256("".join(parts).encode("utf8")).hexdigest()[:12]


def tree_skill_signature():
    """The skill in the working tree: what a run is graded against, and what every saved
    result records, so a score can be tied to the text it measured."""
    return _skill_signature(REPO_SKILL)


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
    want = tree_skill_signature()
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
    ap.add_argument("--komplekt", action="store_true",
                    help="run the whole-month document set: ведомост + обр. 1 + обр. 6 "
                         "+ платежен файл, with links of the chain broken (I9, I10, "
                         "the cross-document half of A9). The payroll itself is clean")
    ap.add_argument("--pair", action="store_true",
                    help="run the two-month fixture: the cross-month scenarios the "
                         "wide fixture cannot hold (E3_leave_base, K8, I7)")
    ap.add_argument("--covering", default=None, metavar="ID,ID",
                    help="FREE: scan seeds from --from and print a minimal set whose "
                         "fixtures inject the named scenarios, then exit - spend "
                         "nothing, choose seeds first")
    ap.add_argument("--seeds-list", dest="seeds_list", default=None, metavar="N,N",
                    help="run exactly these seeds (paid), e.g. after --covering")
    ap.add_argument("--refusal", action="store_true",
                    help="date the payroll outside the years references/stavki.md "
                         "covers and grade whether the skill refuses instead of guessing")
    ap.add_argument("--timeout", type=int, default=1800,
                    help="seconds per seed; measured runs take 5-15 minutes")
    ap.add_argument("--threshold", type=float, default=None,
                    help="exit 1 if the identified share falls below this (0-1)")
    ap.add_argument("--allow-expensive", dest="allow_expensive", action="store_true",
                    help=f"required to start more than {MAX_SEEDS_UNCONFIRMED} paid "
                         f"sessions in one run")
    ap.add_argument("--overwrite", action="store_true",
                    help="let a paid run replace a seed directory that already holds a "
                         "transcript (stream.jsonl); without it such a seed is refused")
    ap.add_argument("--regrade", action="store_true",
                    help=f"FREE: re-grade every saved result in {RESULTS_DIR} against "
                         f"the current keyword patterns and print the summary; nothing "
                         f"is regenerated and no session starts")
    a = ap.parse_args()

    # One way of choosing seeds per run. `--seed 7 --seeds 10` used to run one seed
    # and say nothing about the other nine, and `--seeds-list` silently won over both.
    selectors = [name for name, used in (("--seed", a.seed is not None),
                                         ("--seeds/--from", a.seeds != 1 or a.start != 1),
                                         ("--seeds-list", a.seeds_list is not None))
                 if used]
    if len(selectors) > 1 and not a.covering:
        ap.error(f"{' and '.join(selectors)} do not combine - choose one way of "
                 f"picking seeds")
    # The pair fixture is dated inside the years the reference file covers, and the
    # refusal report reads a single-month manifest. Combined, the run paid for the pair
    # session and then died on man['month'].
    if a.refusal and a.pair:
        ap.error("--refusal and --pair do not combine: the pair fixture has its rates, "
                 "and the refusal report reads a single-month manifest")
    if a.komplekt and (a.pair or a.refusal):
        ap.error("--komplekt is its own fixture and combines with neither --pair nor "
                 "--refusal")
    if a.regrade and (selectors or a.covering):
        ap.error("--regrade scores what is saved and takes no seeds")

    if a.selftest:
        return selftest()
    if a.regrade:
        return regrade(a.threshold)

    # --dry and --covering pay nothing, so a mismatch there is worth saying but not
    # worth blocking: --covering is how seeds are chosen BEFORE the install is
    # refreshed, and refusing it left the choice to guesswork.
    if not check_skill_matches_tree() and not (a.dry or a.covering):
        return 1

    ensure_venv()
    os.makedirs(WORKDIR, exist_ok=True)
    if a.covering:
        wanted = {x.strip() for x in a.covering.split(",") if x.strip()}
        if a.komplekt:
            import generate_komplekt as GK
            universe = set(GK.BREAKS)
        else:
            universe = set(M.PAIR_SCENARIOS) if a.pair else set(M.SCENARIOS)
        unknown = wanted - universe
        if unknown:
            print(f"unknown scenarios for this fixture: {', '.join(sorted(unknown))}")
            return 1
        chosen, still = [], set(wanted)
        for seed in range(a.start, a.start + 2000):
            if not still:
                break
            if a.komplekt:
                # No workbook needs building to know which links a seed breaks: the
                # choice is a function of the seed alone.
                import generate_komplekt as GK
                got = set(GK.breaks_for_seed(seed))
            elif a.pair:
                import generate_pair as P
                _, m = _generate(P, seed, bonus_in_base=False)
                got = {i for _, _, i in m["cross_expected"]}
            else:
                _, m = _generate(G, seed, bonus_in_base=False)
                got = {i for _, _, i in m["expected"]}
            hit = got & still
            if hit:
                chosen.append((seed, sorted(hit)))
                still -= hit
        for seed, ids in chosen:
            print(f"seed {seed}: {', '.join(ids)}")
        if still:
            print(f"not found in 2000 seeds: {', '.join(sorted(still))}")
            return 1
        print(f"\n--seeds-list \"{','.join(str(s_) for s_, _ in chosen)}\" runs them.")
        return 0

    if a.seeds_list:
        # Deduplicated, order kept: prepare() rebuilds the seed's directory, so a seed
        # listed twice would run twice and the second run would erase the first.
        seeds = list(dict.fromkeys(int(x) for x in a.seeds_list.split(",") if x.strip()))
    elif a.seed is not None:
        seeds = [a.seed]
    else:
        seeds = list(range(a.start, a.start + a.seeds))

    if not a.dry and len(seeds) > MAX_SEEDS_UNCONFIRMED and not a.allow_expensive:
        print(f"refusing to run: {len(seeds)} paid sessions in one go, about USD "
              f"{len(seeds) * EST_USD_PER_SEED:.0f} at the measured ~USD "
              f"{EST_USD_PER_SEED} per seed. Up to {MAX_SEEDS_UNCONFIRMED} start without "
              f"asking; pass --allow-expensive for more.")
        return 1

    # Refuse to spend money on a run the grader cannot score. Complete today; this
    # exists for the day a scenario is added without its KEYWORDS entry - the checklist
    # step easiest to forget, and the one whose absence used to score as a pass.
    if a.komplekt:
        import generate_komplekt as GK
        ungradable = sorted(set(GK.BREAKS) - set(KOMPLEKT_KEYWORDS))
    elif a.pair:
        ungradable = sorted(set(M.PAIR_SCENARIOS) - set(PAIR_KEYWORDS))
    else:
        ungradable = sorted(set(M.SCENARIOS) - set(KEYWORDS))
    if ungradable and not a.dry:
        print("refusing to run: scenarios with no KEYWORDS entry, so their findings "
              "cannot be graded: " + ", ".join(ungradable))
        return 1

    # A paid transcript is not overwritten by accident. Checked here, before any session
    # starts, so a batch is refused whole rather than after nine seeds; prepare() checks
    # again, for callers that reach it some other way.
    if not a.dry and not a.overwrite:
        # Per mode, because each mode has its own directory. Before 05.09.2026 this
        # asked about `seed-<n>` whatever the mode, so the first --komplekt batch was
        # refused for the wide seeds' transcripts - which it would never have touched.
        def _dir(s_):
            return (komplekt_dir(s_) if a.komplekt
                    else seed_dir(s_, pair=a.pair, refusal=a.refusal))
        kept = [d for d in (_dir(s) for s in seeds) if has_paid_run(d)]
        if kept:
            print("refusing to run: these directories hold the transcripts of paid runs "
                  "(stream.jsonl), and a new session would erase them:")
            for d in kept:
                print(f"  {d}")
            print("Pass --overwrite to replace them, or move them aside first.")
            return 1

    if not a.dry:
        print(f"About to run {len(seeds)} Claude sessions. That costs money and takes "
              f"minutes per seed. Each seed is saved in {RESULTS_DIR} as it finishes.")

    scenarios = scenario_universe(pair=a.pair, komplekt=a.komplekt)
    runs = []
    try:
        for s in seeds:
            try:
                r = run_seed(s, a.model, a.dry, a.timeout, a.refusal, a.pair,
                             a.overwrite, a.komplekt)
            except SessionUnavailable as exc:
                print(f"\nstopping after {len(runs)} of {len(seeds)} seeds: the account "
                      f"cannot run sessions right now - {exc}. The remaining seeds would "
                      f"each pay for a turn and measure nothing; re-run them with "
                      f"--overwrite once the limit resets. Finished seeds are saved in "
                      f"{RESULTS_DIR}.")
                break
            if r:
                runs.append(r)
    except KeyboardInterrupt:
        # The seeds already paid for are on disk and in `runs`; say what they showed
        # instead of losing it with the traceback.
        print(f"\ninterrupted after {len(runs)} of {len(seeds)} seeds; every finished "
              f"seed is saved in {RESULTS_DIR}")
        if runs:
            if a.refusal:
                summarize_refusal(runs)
            else:
                summarize(runs, scenarios)
        return 130
    if not runs:
        return 0
    if a.refusal:
        return summarize_refusal(runs)
    return summarize(runs, scenarios, a.threshold)


if __name__ == "__main__":
    sys.exit(main())
