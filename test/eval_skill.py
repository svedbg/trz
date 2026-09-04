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

IT COSTS MONEY. One measured run on Opus: 18 turns, about 12 minutes and USD 2.4
for a single seed. Use --dry to see what will happen before paying.

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
"""
import argparse
import hashlib
import csv
import glob
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
# One JSON per graded seed. Outside the isolated seed directories on purpose: the
# session must not see it, and the `leftovers` assert in prepare() guards only those.
RESULTS_DIR = os.path.join(WORKDIR, "results")
REPO_SKILL = os.path.join(HERE, "..", "skills", "trz-expert")

# Every seed is a real Claude session. scenarios.md records the measured cost of one;
# a run of more than this many needs --allow-expensive, because `--seeds 300` is what
# every other suite in this directory takes and here it would be a four-figure bill
# after one printed line.
EST_USD_PER_SEED = 2.4
MAX_SEEDS_UNCONFIRMED = 10

# --- keywords for the mapping. Each entry is a list: all of them must match ---
# --- the finding's description. Deliberately broad: the point is not to score ---
# --- a correct finding as a miss because it was worded differently. ---
#
# But never a single group. Every entry that named only the defect's SUBJECT - „отпуск",
# „разход", „ТЗПБ", „таван|максимал", „натура|карт" - scored the opposite direction as
# an identification: „ТЗПБ е приложен над дължимия процент", „осигурителният доход не
# надвишава максималния за периода", „не мога да потвърдя общия разход за труд". Since
# 2026-09-03 each entry carries at least two groups, and one of them must say what is
# wrong - the direction, the reason, or the shape of the mistake. MISREAD below holds
# those opposite-direction sentences so that --selftest keeps them out.

# The sick-pay scenarios share a subject group. „по болест" and „първите три дни" are
# how a live run named it without any of the words the group used to demand.
_SICK = r"болничен|болнични|неработоспособ|чл\.? ?40|болест|първите (?:три|3) дни"

KEYWORDS = {
    "K1_sum_omits_column":        [r"сбор|включ|извън|липсва|обхват|формула|не влиза",
                                   r"колон|бруто|БРУТО"],
    # „това е пари, не бройка" is a correct description that carried none of
    # „сума|стойност|размер".
    "K2_amount_in_day_column":    [r"сума|стойност|размер|пари|парич", r"дни|ден"],
    "K3_stale_contributions":     [r"вноск", r"процент|13\.?78|не отговар|твърд|"
                                   r"изостан|вместо върху|друга база|върху база"],
    # The defect is a control cell that reads zero while the two figures it compares
    # differ. A bare `0` would match any zero digit and `0\.00` the tail of „250.00", so
    # the zero is taken only when nothing numeric touches it.
    "K4_control_column_blind":    [r"изплат|разлика|контрол",
                                   r"нула|\b0[.,]00\b|(?<![\d.,])0(?![\d.,])|тъждеств|"
                                   r"винаги|не улавя|равна на|не отчита|не показва|скрива"],
    # „вместо" only before a figure: „вместо да бъде изключена" is how a sick-pay
    # finding reads, „1 234,58 вместо 1 234,56" is how this one does.
    "K5_total_not_sum":           [r"сбор|сум|общо",
                                   r"ръчно|не отговар|различ|вписан|≠|вместо \d|по клетките|"
                                   r"не е сбор|не съвпад|разминав"],
    # \bцент(а|ове|\b), not цент: the bare stem matches „процент" and claimed every
    # finding that mentions a percentage; \bцент alone still matched „централно".
    "K6_unrounded_accrual":       [r"закръгл|знак|\bцент(?:а|ове|\b)|десетичн"],
    "K7_cost_from_net":           [r"разход", r"нето|след удръжк|от нетото"],
    # осигурител\w*, not осигурителн - see _RATE_NAMES.
    "F9_sick_pay_out_of_insurable": [_SICK, r"осигурител\w*"],
    "F9_sick_pay_in_taxable":     [_SICK, r"данъчн|данък|облага|облож"],
    # The second pattern must require the CORRECTED reading, not merely allow it.
    # „среднодневното брутно е по-високо, защото месецът носеше бонус" is the story this
    # scenario was inverted to refute, and it matches „среднодневн", „уговорен", „база"
    # and „бонус" alike - so those cannot be the discriminator. What only the right
    # answer carries is the direction (paid too much) or the reason (a one-off is not
    # in чл. 17, ал. 1).
    "F9_sick_pay_amount":         [_SICK,
                                   r"в повече|завишен|надплатен|надвзет|"
                                   r"постоянен характер|еднократ|чл\.? ?17"],
    "F9_health_on_sick_days":     [r"здравн|ЗЗО", r"болничен|майчинств|неработоспособ|"
                                   r"болест|плат[а-я]* от работодателя|"
                                   r"за сметка на работодателя"],
    "F1_compensation_in_insurable": [r"чл\.? ?224|обезщетени",
                                     r"осигурител\w* доход|вноск|НЕВДПОВ"],
    # The asymmetry itself, not merely the card: „картата е в двете бази" is the
    # opposite finding.
    "F10_in_kind_asymmetry":      [r"натура|карт",
                                   r"едната|само в|асиметри|не и в|не е включен|"
                                   r"не влиза в|липсва (?:в|от)"],
    # Two groups. With one - „превишен|праг|застрахов|доброволн|…" - a description of
    # a чл. 19 relief applied to a voluntary-insurance premium scored as this scenario
    # too (it said „доброволно"), and --selftest could not see it because the
    # phrasing that proved it was the second of two identical keys in OBSERVED. The
    # threshold is written „60,00 лв." as often as „60 лв", and a finding that puts the
    # excess in one base „but not the other" need not repeat the word „праг".
    "F10_excess_asymmetry":       [r"превишен|над (?:необлагаем|праг)|30[.,]?68|"
                                   r"60(?:[.,]00)? ?лв",
                                   r"праг|застрахов|доброволн|натура|карт|превишен|"
                                   r"едната|само в|не и в|асиметри"],
    # The second pattern discriminates over_limit from the other two F7 scenarios, but
    # „над" alone was too narrow: a live run described this defect as „приложено с
    # пълния размер на удръжката, без да е спазен лимитът" and scored as located only.
    # „10 на сто" is the statute's own spelling of the limit.
    "F7_relief_over_limit":       [r"облекчен|приспадн|лимит|10 ?%|10 на сто|чл\.? ?19|"
                                   r"чл\.? ?42",
                                   r"над|превиш|надвиш|повече от|без да е спазен"
                                   r"|не е спазен|пълния размер|целия размер"
                                   r"|без ограничен|цял"],
    "F7_relief_combined_limit":   [r"облекчен|приспадн|лимит|10 ?%|10 на сто|чл\.? ?19",
                                   r"два|две|отделн|поотделно|груп|\bобщ|20 ?%|вместо|по-малк"],
    # A bare `0` matched any text containing a zero digit, i.e. almost everything;
    # `0\.00` was no better - it matches the tail of „250.00". And a bare „липсв" took
    # „не мога да проверя облекчението, липсва документ …" - a refusal - for the
    # finding; what must be missing is the relief itself.
    "F7_relief_not_applied":      [r"облекчен|приспадн|намал|чл\.? ?19|чл\.? ?42",
                                   r"не е приложен|не е ползван|не е намал"
                                   r"|не е приспадн|липсв\w*\s+(?:облекчен|приспад|намал)"
                                   r"|без облекчен|нула|не намал|не е отразен"],
    "F5_tzpb_below_due":          [r"ТЗПБ|трудова злополука",
                                   r"\bпод\b|по-ниск|занижен|вместо|по-малък"],
    "B4_cap_from_wrong_period":   [r"таван|максимал",
                                   r"друг|предходн|предишн|полугоди|стар|изтекл|вместо|"
                                   r"31\.07|01\.08|неправилн|грешн"],
    "C2_seniority_on_gross":      [r"клас", r"база|бруто|основна"],
    "E3_leave_without_seniority": [r"отпуск",
                                   r"\bбез\b|липсва|не включва|клас|не е включен|не носи|"
                                   r"не съдържа"],
    # „18 + 2 + 2 = 22 при 21 работни дни" names the norm without the word.
    "I5_days_do_not_reconcile":   [r"дни|ден",
                                   r"норма|не се връзва|не отговар|сбор|работни дни|"
                                   r"не съвпад|разминав"],
    # The six scenarios that got their mutations on 03.09.2026 (they had checkers and
    # no generator). Each carries its subject and the shape of the defect; the shape
    # group is what keeps them apart from the F9/F7/K entries that share a subject.
    "I1_vertical":                [r"нето|за получаване|изплат",
                                   r"минус|−|не се връзва|не отговар|не съвпад|разминав|"
                                   r"различ|аритмет|сверк|не следва от"],
    # The rate, not a generic mismatch word: an I1 sentence also says „данък" and
    # „разминаване", and would be credited here. A tax-amount finding names the rate.
    "F6_tax_amount":              [r"данък|ДДФЛ",
                                   r"10 ?%|10 на сто|ставк|не е 10|десет на сто|процент"],
    "A6_base_vs_contract":        [r"договор|споразумени|уговорен",
                                   r"основн|заплата|възнаграждени",
                                   r"разминав|различ|не отговар|по-ниск|по-висок|\bпод\b|"
                                   r"\bнад\b|вместо|друга заплата|друг размер"],
    "F1_insurable_unexplained":   [r"осигурител\w* доход",
                                   r"не се обяснява|необясним|никаква комбинация|"
                                   r"нито една комбинация|не се получава|не следва|"
                                   r"не може да се изведе|няма обяснение|не отговаря на"],
    "F6_taxable_unexplained":     [r"данъчн\w* основа",
                                   r"не се обяснява|необясним|никаква комбинация|"
                                   r"нито една комбинация|не се получава|не следва|"
                                   r"не може да се изведе|няма обяснение|никакво третиране"],
    "F6_compensation_out_of_taxable": [r"чл\.? ?224|обезщетени",
                                       r"данъчн|облага|данък",
                                       r"извън|вън от|не е включен|липсва|изключен|"
                                       r"необлага|не влиза|пропусн|оставен"],
}

# The pair fixture's scenarios live in their own keyword universe. grade() only ever
# competes identifiers from ONE manifest, so discrimination is enforced within each
# dict separately - folding these into KEYWORDS would fail the selftest the moment two
# leave-scenarios coexist (E3_leave_without_seniority matches on „отпуск" alone).
#
# No token from a single transcript. The launch version of K8 carried „режима 01",
# „нормата на юли" and „от юли", and I7 „при договорен" - the exact words of the first
# live run, which made the pattern a memory of one session rather than a description
# of the defect. The forms below are generic: the previous period, a copy carried
# forward, the header that declares the norm, a rise against the contract.
PAIR_KEYWORDS = {
    "K8_stale_thresholds":  [r"копира\w*|пренесен\w*|стар\w*|предходн\w*|предишн\w*|"
                             r"друг[а-я]* (?:месец|период)|до 31\.07|от 01\.08|вместо|"
                             r"шапк\w*|заглавн\w*|обявява",
                             r"праг|норма|таван|максимал"],
    "I7_unexplained_jump":  [r"заплата|възнаграждение|бруто",
                             r"скок|скач|разлика|промяна|различн|мени се|повече|спрямо|"
                             r"по-висок|по-голям|ръст|увелич|нарасн|\+\d|"
                             r"(?:от|при|спрямо|срещу) договорен",
                             r"споразумение|обяснение|основание|документ|анекс"],
    "E3_leave_base":        [r"отпуск",
                             r"чл\.? ?1[78]|бонус|преми\w*|предходн|предишн|среднодневн|"
                             r"изречение|изр\.|10 (отработени )?дни|средномесечн|уговорен|"
                             r"постоянен характер|еднократ"],
}

# Phrasings from live pair runs (01-02.09.2026 and the review of 03.09.2026), kept as
# regression cases: every one was a correct identification that the patterns of the
# day under-scored.
PAIR_OBSERVED = {
    "K8_stale_thresholds": [
        "лист 08-2026 прилага максималния осигурителен доход 2111.64 EUR от режима "
        "01.01–31.07.2026 вместо 2300.00 EUR, с което при шест лица на тавана са "
        "невнесени общо 369.48 EUR",
        "лист 08-2026 е сметнат изцяло на нормата на юли — шапката обявява 23 работни "
        "дни, а август 2026 има 21",
        "листът 08-2026 прилага тавана 2111.64 EUR от предишния месец, а за август "
        "таванът е 2300.00 EUR",
    ],
    "I7_unexplained_jump": [
        "основната за отработеното през август е 7983.53 EUR срещу договорени 5622.37 "
        "EUR — с 2361.16 EUR (+42%) повече без документ, а брутото скача без обяснение",
        "основната заплата за август е 6243.78 EUR при договорена 3824.98 EUR (+63.2% "
        "спрямо юли) без представено допълнително споразумение",
        "основната заплата за август е с 42% по-висока от договорената без анекс към "
        "трудовия договор",
    ],
    "E3_leave_base": [
        "базата за платения отпуск през август включва премията от 07-2026, която не е "
        "с постоянен характер",
    ],
}

PAIR_SAMPLE_TEXT = {
    "K8_stale_thresholds": "листът за август е сметнат по нормата и максималния осигурителен доход на юли - копиран е напред със старите прагове",
    "I7_unexplained_jump": "подразбиращата се месечна заплата скача между юли и август без допълнително споразумение във файла, което да обясни промяната",
    "E3_leave_base": "платеният отпуск през август носи и бонуса от юли, а той не е в нито една от седемте точки на чл. 17, ал. 1 НСОРЗ",
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
RATE_FREE = ("I1_vertical",
             "K1_sum_omits_column", "K2_amount_in_day_column", "K4_control_column_blind",
             "K5_total_not_sum", "K6_unrounded_accrual", "K7_cost_from_net",
             "I5_days_do_not_reconcile", "C2_seniority_on_gross",
             "E3_leave_without_seniority")

# 2. What must not be asserted. A finding graded `нарушение` that leans on one of these
#    is the failure the rule exists to prevent: last year's threshold applied to this
#    year's payroll, stated with the confidence of a checked figure.
#    The adjective may stand a few words from its noun: „минималната заплата за 2027 г.",
#    „максималния размер на осигурителния доход", „минималното месечно възнаграждение"
#    were all graded `нарушение` by a live run and all scored as rate-free while the
#    pattern demanded the words adjacent.
#    „осигурител\w*", not „осигурителн": the bare masculine „осигурителен доход" does not
#    contain the stem with н, and it is the form a heading or a statute uses.
_RATE_NAMES = (r"\bМРЗ\b|\bМОД\b|таван\w*|"
               r"минимал\w*(?:\s+\w+){0,3}\s+(?:заплата|възнаграждение|осигурител\w*)|"
               r"максимал\w*(?:\s+\w+){0,4}\s+осигурител\w*|"
               r"осигурител\w*\s+праг\w*")
RATE_DEPENDENT = re.compile(_RATE_NAMES, re.I)

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
#    observation about formulas counted as a statement about rates. A bare "2027" and a
#    bare "ставк" went the same way: "в клетка F12 няма формула за 07.2027" and "няма
#    посочена часова ставка за извънредния труд" are gaps, but not the gap under test.
#    What is missing has to be a rate the reference file would carry.
SAYS_PERIOD = re.compile(_RATE_NAMES + r"|праг\w*", re.I)


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

# Paths this run has no business touching: the answers and the independent
# implementation of every check live there.
FORBIDDEN = re.compile(r"_manifest\.json|structural_test|checks_test|trz_model|"
                       r"generate_wide|generate_narrow|generate_pair|pair_test|"
                       r"run_tests|skill_test|eval_skill|rates_test|"
                       r"expected_findings|scenarios\.md")

# The answer key's own vocabulary, looked for in what the tools RETURNED. FORBIDDEN
# screens the inputs - a path - and a path can be spelled in ways a regex does not
# foresee (a glob, a variable, `cat *json`). What cannot be disguised is the content:
# the manifest's `"expected"` key, spelled as JSON spells it, and the scenario
# identifiers, which occur nowhere the session may legitimately read - not in SKILL.md,
# not in the reference files. Either one in a tool result means the run saw the answers.
LEAKED = re.compile(r'"expected"|' + "|".join(
    re.escape(i) for i in list(M.SCENARIOS) + list(M.PAIR_SCENARIOS)))


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
           f"Bash({VENV}/bin/python:*)", "Bash(ls:*)",
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
        if "файл" in where:
            return "file"
        # „ред 12" names a row wherever it stands; „лист 08-2026" names a sheet, and the
        # first digit run in it is a month, not a row - it used to be read as row 8.
        m = re.search(r"ред\s*(\d+)", where)
        if m:
            row = int(m.group(1))
        elif "лист" in where:
            return "file"
        else:
            m = re.search(r"(\d+)", where)
            row = int(m.group(1)) if m else None
    if row is None:
        return "file"
    return "file" if row >= total_row else row


# Severities that assert a defect. A finding is a claim that something is wrong; a
# `бележка` is an observation and, in a payroll whose year the reference file covers,
# `за проверка` is a finding the skill declined to commit to. Neither identifies an
# injected defect - until 2026-09-03 grade() never read this field, and a note saying
# the row was computed correctly scored as an identification because it stood on the
# right row and mentioned the right word.
ASSERTING = {"нарушение", "риск", "дефект"}

# Sentences that deny a defect while naming it. „коректно"/„правилно" are denials
# unless negated (неправилно, не е коректно), and „не мога да проверя" is a refusal,
# not a finding. Kept narrow on purpose: Bulgarian negation is easy to over-match, and
# the structured field above is the primary signal.
_VERB = r"(?:изчислен|начислен|приложен|определен|отразен|сметнат|внесен|удържан)"
DENIES = re.compile(
    r"(?<!не)(?<!не )(?<!не е )(?<!не са )(?<!не бе )"
    rf"(?:{_VERB}\w*\s+(?:е\s+|са\s+)?(?:коректн|правилн)|(?:коректн|правилн)\w*\s+{_VERB})"
    r"|не мога да (?:проверя|потвърдя|установя|преценя)"
    r"|не (?:е|представлява|съставлява) нарушение|няма (?:нарушение|разминаване|отклонение)"
    r"|(?<!не )(?:е в съответствие|съответств(?:а|ува) на)", re.I)


# Scenarios whose correct finding IS a `за проверка`: the figure matches no composition
# of the row, so the honest report says the file does not explain it and asks - it does
# not assert a violation. Demanding `нарушение` there would score the right answer as
# „located only" and reward a skill that guesses a cause.
UNRESOLVED_IS_RIGHT = {"F1_insurable_unexplained", "F6_taxable_unexplained"}


def asserts_a_defect(finding, ident=None):
    """Does this finding claim a defect, rather than note, deny or decline one?

    For the scenarios in UNRESOLVED_IS_RIGHT a `за проверка` counts as the claim.
    """
    tezhest = str(finding.get("tezhest", "")).strip().lower()
    if tezhest not in ASSERTING and not (tezhest == "за проверка"
                                         and ident in UNRESOLVED_IS_RIGHT):
        return False
    return not DENIES.search(str(finding.get("kratko", "")))


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
    "K3_stale_contributions": "личните осигурителни вноски са изчислени върху база около 1989.20 вместо върху обявения в същия ред осигурителен доход, докато вноските на работодателя са върху обявения",
    "F9_sick_pay_out_of_insurable": "болничните за първите дни стоят извън осигурителния доход, а върху тях се дължат вноски",
    "F9_sick_pay_in_taxable": "болничните за първите дни са в данъчната основа, а са необлагаем доход",
    "F9_sick_pay_amount": "болничните са сметнати върху база, в която е вкаран бонусът за месеца - той е еднократен, не е в нито една от седемте точки на чл. 17, ал. 1 НСОРЗ и не влиза в нея",
    "F9_health_on_sick_days": "здравната вноска по чл. 40, ал. 1, т. 5 ЗЗО е начислена за 2 дни, платени от работодателя по чл. 40, ал. 5 КСО, които т. 17 на Декларация обр. 1 изключва от базата - здравното за тези дни е платено два пъти",
    "F1_compensation_in_insurable": "обезщетението по чл. 224 КТ е включено в осигурителния доход, а чл. 1, ал. 8, т. 7 НЕВДПОВ не дължи вноски върху него - внесено в повече и от двете страни",
    "F10_in_kind_asymmetry": "картата в натура е в едната база, но не и в другата",
    "F10_excess_asymmetry": "превишението над необлагаемия праг влиза само в едната от двете бази",
    "F7_relief_over_limit": "приспаднато е облекчение над месечния лимит от 10 на сто",
    "F7_relief_not_applied": "удържана е лична вноска, но облекчението не е приложено и основата не е намалена",
    "F7_relief_combined_limit": "приспаднато е само 108.04 EUR облекчение вместо дължимите 216.08 EUR",
    "F5_tzpb_below_due": "изведеният процент ТЗПБ е под приложимия за икономическата дейност",
    "B4_cap_from_wrong_period": "приложен е максималният осигурителен доход от другото полугодие",
    "I1_vertical": "нетото не е брутно минус лични осигуровки, данък и удръжки - разминаването е 10.30 EUR",
    "F6_tax_amount": "удържаният данък е 61.08 при 10% от данъчната основа 618.55 = 61.86",
    "A6_base_vs_contract": "основната заплата за отработеното време е 1 320.00 при договорена 1 500.00 - разминава се с договора",
    "F1_insurable_unexplained": "осигурителният доход 1 640.00 не се получава от никаква комбинация от начисленията и придобивките на лицето",
    "F6_taxable_unexplained": "данъчната основа 1 402.10 не се получава от облагаемия доход минус вноските при никакво третиране на елементите",
    "F6_compensation_out_of_taxable": "обезщетението по чл. 224 КТ е оставено извън данъчната основа, а то е облагаем доход - чл. 24, ал. 2, т. 8 ЗДДФЛ не го освобождава",
}


# Phrasings taken from real graded runs, kept as regression cases. A pattern that
# stops matching one of these has lost recall on wording a model actually produced -
# which is how the tightening in the previous commit turned a correct finding into
# „located only" and cost a seed's worth of signal.
#
# A list of pairs, not a dict literal: a dict literal with the same key twice keeps
# the second value and says nothing, and that is exactly what happened here - the
# „238.61 EUR при лимит 10%" phrasing below was silently dropped and the
# discrimination failure it exposes (it also matched F10_excess_asymmetry) went
# unreported by --selftest.
_OBSERVED_PAIRS = (
    # From the 01-02.09.2026 targeted run - correct identifications the launch
    # patterns under-scored, kept so the recall cannot regress:
    ("F7_relief_not_applied", [
        "удържаната лична вноска 65.66 EUR не е приспадната от месечната данъчна "
        "основа",
        "удържаната премия (129.00) не е намалила данъчната основа - облекчението "
        "не е приложено",
    ]),
    ("F7_relief_over_limit", [
        "данъчната основа е намалена с цялата удръжка за доброволно осигуряване "
        "238.61 EUR при лимит 10%",
        "Облекчението по чл. 19, ал. 2 ЗДДФЛ е приложено с пълния размер на удръжката "
        "276.21 EUR, без да е спазен лимитът",
    ]),
    ("F9_sick_pay_in_taxable", [
        "Сумата по чл. 40, ал. 5 КСО (185.47) е включена в данъчната основа, вместо да "
        "бъде изключена като необлагаема",
        "обезщетението за първите три дни по болест е обложено с данък",
    ]),
    ("F10_excess_asymmetry", [
        "Превишението над необлагаемия праг 30.68 EUR (4.69) е добавено в данъчната "
        "основа, но не и в осигурителния доход",
        "сумата над 30,68 EUR е включена в осигурителния доход, но не и в данъчната "
        "основа",
        "частта над 60,00 лв. е добавена само в едната от двете бази",
    ]),
    ("F5_tzpb_below_due", [
        "ТЗПБ е приложен 0.80% вместо потвърдените 1.1% при всичките 11 лица",
    ]),
    # From the review of 03.09.2026 - correct descriptions the patterns missed outright:
    ("I5_days_do_not_reconcile", [
        "отработени 18 + отпуск 2 + болнични 2 = 22 при 21 работни дни в месеца",
    ]),
    ("K5_total_not_sum", [
        "ОБЩО за колоната Карта е 1 234,58 вместо 1 234,56 по клетките",
    ]),
    ("K2_amount_in_day_column", [
        "в „Отработени дни“ стои 1 850,00 - това е пари, не бройка",
    ]),
)
OBSERVED = dict(_OBSERVED_PAIRS)
assert len(OBSERVED) == len(_OBSERVED_PAIRS), "a scenario is listed twice in OBSERVED"

# Sentences that name a scenario's subject and say the OPPOSITE - the row is fine, the
# figure is over rather than under, the check could not be made. Each is paired with the
# scenarios it must not score as; check_keywords() enforces it. These are the sentences
# that were scoring as identifications while every entry had a single keyword group.
MISREAD = (
    ("ТЗПБ е приложен над дължимия процент", ("F5_tzpb_below_due",)),
    ("осигурителният доход не надвишава максималния за периода",
     ("B4_cap_from_wrong_period",)),
    ("не мога да потвърдя общия разход за труд", ("K7_cost_from_net",)),
    ("не мога да проверя облекчението, липсва документ за доброволното осигуряване",
     ("F10_excess_asymmetry", "F7_relief_not_applied")),
    ("платеният отпуск е изчислен коректно", ("E3_leave_without_seniority",)),
    ("картата е в двете бази", ("F10_in_kind_asymmetry",)),
    ("изплатено съвпада с нетото", ("K4_control_column_blind",)),
    ("централно зададен процент", ("K6_unrounded_accrual",)),
)


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
        variants = (
            ("asserted", "дефект", sample, "identified"),
            ("a note", "бележка", sample, "located only"),
            ("declined", "за проверка", sample, "located only"),
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

    for rel in ("SKILL.md", "references/stavki.md", "references/proverki.md",
                "references/normativna-baza.md"):
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


def generator_sha(pair):
    """Identity of the fixture generator the manifest came from."""
    name = "generate_pair.py" if pair else "generate_wide.py"
    with open(os.path.join(HERE, name), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def results_path(mode, seed):
    return os.path.join(RESULTS_DIR, f"{mode}-{seed}.json")


def persist(rec):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = results_path(rec["mode"], rec["seed"])
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


def run_seed(seed, model, dry, timeout, refusal=False, pair=False, overwrite=False):
    mode = "pair" if pair else "refusal" if refusal else "wide"
    if pair:
        d, man, prompt = prepare_pair(seed, dry=dry, overwrite=overwrite)
    else:
        d, man, prompt = prepare(seed, year=2027 if refusal else 2026, dry=dry,
                                 overwrite=overwrite)
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
    # The keyword universe is not stored with the manifest: a re-grade attaches the
    # current one by mode, and keywords_sha records which one produced this score.
    rec = dict(seed=seed, mode=mode, model=model, skill_sig=tree_skill_signature(),
               keywords_sha=keywords_sha(man.get("keywords") or KEYWORDS),
               generator_sha=generator_sha(pair),
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
            universe = PAIR_KEYWORDS if mode == "pair" else KEYWORDS
            if mode == "pair":
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
            scenarios = M.PAIR_SCENARIOS if mode == "pair" else M.SCENARIOS
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
        universe = set(M.PAIR_SCENARIOS) if a.pair else set(M.SCENARIOS)
        unknown = wanted - universe
        if unknown:
            print(f"unknown scenarios for this fixture: {', '.join(sorted(unknown))}")
            return 1
        chosen, still = [], set(wanted)
        for seed in range(a.start, a.start + 2000):
            if not still:
                break
            if a.pair:
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
    ungradable = (sorted(set(M.PAIR_SCENARIOS) - set(PAIR_KEYWORDS)) if a.pair
                  else sorted(set(M.SCENARIOS) - set(KEYWORDS)))
    if ungradable and not a.dry:
        print("refusing to run: scenarios with no KEYWORDS entry, so their findings "
              "cannot be graded: " + ", ".join(ungradable))
        return 1

    # A paid transcript is not overwritten by accident. Checked here, before any session
    # starts, so a batch is refused whole rather than after nine seeds; prepare() checks
    # again, for callers that reach it some other way.
    if not a.dry and not a.overwrite:
        kept = [d for d in (seed_dir(s, pair=a.pair, refusal=a.refusal) for s in seeds)
                if has_paid_run(d)]
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

    scenarios = M.PAIR_SCENARIOS if a.pair else M.SCENARIOS
    runs = []
    try:
        for s in seeds:
            try:
                r = run_seed(s, a.model, a.dry, a.timeout, a.refusal, a.pair, a.overwrite)
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
