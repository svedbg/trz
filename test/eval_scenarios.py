# -*- coding: utf-8 -*-
"""Scenario data for eval_skill.py: keyword patterns, sample sentences, isolation
regexes - every module-level constant that is pure data, no control flow.

Split out of eval_skill.py (06.09.2026) so the file that runs and grades a session is
not also the file that carries ~400 lines of keyword tables. Nothing here computes
anything beyond building a regex or a set literal at import time - eval_skill.py's
grading functions score against these, its `prepare_komplekt` embeds one of them into a
manifest, and its CLI reads a couple directly, all by importing this module. Moving a
constant back out of here is safe as long as whatever imports it is updated to match -
nothing in this file depends on import order beyond what a normal module already
guarantees.
"""
import re
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trz_model as M                                          # noqa: E402

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
    # No bare „процент" - it matched any percentage-based finding, including an F5
    # ТЗПБ sentence that also happens to say „вноските" (04.09.2026).
    "K3_stale_contributions":     [r"вноск", r"13\.?78|не отговар|твърд|"
                                   r"изостан|вместо върху|друга база|върху база"],
    # The defect is a control cell that reads zero while the two figures it compares
    # differ. A bare `0` would match any zero digit and `0\.00` the tail of „250.00", so
    # the zero is taken only when nothing numeric touches it.
    # (?![.,]?\d), not (?![\d.,]): the old lookahead rejected a bare zero followed by a
    # sentence comma, so „контролната колона показва 0, докато разлика има" - the most
    # natural phrasing of this very check - could not match at all. Still refuses the 0
    # inside 0.5 and 1,0; „0,00" keeps its own branch. Found while reading the 05.09.2026
    # refusal run, which wrote exactly that sentence; note it did NOT change that run's
    # score, because the finding sat on the totals row and K4 is attributed to the row
    # whose difference the blind cell hides. The lookahead was wrong on its own terms.
    "K4_control_column_blind":    [r"изплат|разлика|контрол",
                                   r"нула|\b0[.,]00\b|(?<![\d.,])0(?![.,]?\d)|тъждеств|"
                                   r"винаги|равна на|скрива|"
                                   r"не (?:\w+ ){0,2}(?:улавя|отчита|показва)|"
                                   r"празн"],
    # „вместо" only before a COMMA-decimal figure, this file's convention for a total
    # ("1 234,58 вместо 1 234,56") - a bare `вместо \d` also matched a dot-decimal
    # amount in an unrelated C2 sentence (04.09.2026).
    "K5_total_not_sum":           [r"сбор|сум|общо",
                                   r"ръчно|не отговар|различ|вписан|≠|вместо\s+[\d ]*,\d|"
                                   r"по клетките|не е сбор|не съвпад|разминав"],
    # \bцент(а|ове|\b), not цент: the bare stem matches „процент" and claimed every
    # finding that mentions a percentage; \bцент alone still matched „централно".
    "K6_unrounded_accrual":       [r"закръгл|знак|\bцент(?:а|ове|\b)|десетичн"],
    # Live runs described the cost taken from the net as „занижен … изважда личната
    # удръжка" and „намален с личната част на картата" - the deduction named, the word
    # „нето" absent.
    "K7_cost_from_net":           [r"разход", r"нето|след удръжк|от нетото|удръжк|"
                                              r"занижен|намален|личната част"],
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
    # „надхвърля" (a live sentence from the Sonnet run, 04.09.2026) is a synonym of
    # „надвишава" the direction group did not carry.
    "F7_relief_over_limit":       [r"облекчен|приспадн|лимит|10 ?%|10 на сто|чл\.? ?19|"
                                   r"чл\.? ?42",
                                   r"\bнад\b|превиш|надвиш|надхвърля\w*|повече от|"
                                   r"без да е спазен|не е спазен|пълния размер|"
                                   r"целия размер|без ограничен|цял"],
    # No bare „приспадн" here: an I1 sentence about a deduction „не е приспадната от
    # нетото … 2211.09 вместо 2184.21" carried it and „вместо" and was credited here.
    "F7_relief_combined_limit":   [r"облекчен|лимит|10 ?%|10 на сто|чл\.? ?19",
                                   r"два|две|отделн|поотделно|груп|\bобщ|20 ?%|вместо|по-малк"],
    # A bare `0` matched any text containing a zero digit, i.e. almost everything;
    # `0\.00` was no better - it matches the tail of „250.00". And a bare „липсв" took
    # „не мога да проверя облекчението, липсва документ …" - a refusal - for the
    # finding; what must be missing is the relief itself.
    "F7_relief_not_applied":      [r"облекчен|приспадн|намал|чл\.? ?19|чл\.? ?42",
                                   r"не е приложен|не е ползван|не е намал"
                                   r"|не е приспаднат\w* от (?:месечната )?данъчн"
                                   r"|липсв\w*\s+(?:облекчен|приспад|намал)"
                                   r"|без облекчен|нула|не намал|не е отразен"],
    # „недовнесена ТЗПБ вноска" names the shortfall by the contribution, not the rate,
    # and carried none of „под|по-ниск|занижен" (Sonnet run, 04.09.2026).
    "F5_tzpb_below_due":          [r"ТЗПБ|трудова злополука",
                                   r"\bпод\b|по-ниск|занижен|вместо|по-малък|недовнес\w*|"
                                   r"недоплат\w*"],
    "B4_cap_from_wrong_period":   [r"таван|максимал",
                                   r"друг|предходн|предишн|полугоди|стар|изтекл|вместо|"
                                   r"31\.07|01\.08|неправилн|грешн"],
    # The supplement as SUBJECT (класът е начислен върху …), not „клас" as one of the
    # elements listed inside a sick-pay base: „(основна + клас + бонус)" is F9's story.
    # „Клас сумата е изчислена грешно" (Sonnet run, 04.09.2026) put a noun between
    # „клас" and the verb that the original group did not allow for.
    "C2_seniority_on_gross":      [r"класът|класа\b|клас\w*\s+(?:сумата\s+)?(?:е\s+)?"
                                   r"(?:начислен|изчислен|сметнат|начисляван|начислява|"
                                   r"върху)",
                                   r"база|бруто|основна|плюс|\+|отпуск|бонус"],
    "E3_leave_without_seniority": [r"отпуск",
                                   r"\bбез\b|липсва|не включва|клас|не е включен|не носи|"
                                   r"не съдържа"],
    # „18 + 2 + 2 = 22 при 21 работни дни" names the norm without the word.
    # „дните на реда са 20 вместо 22 - дните липсват от отчетността" is how the 2.8.0
    # refusal run described it, without „норма" or „не се връзва".
    "I5_days_do_not_reconcile":   [r"дни|ден",
                                   r"норма|не се връзва|не отговар|сбор|работни дни|"
                                   r"не съвпад|разминав|вместо \d|дните липсва|"
                                   r"дните на реда|броят (?:на )?дни|дни са \d|"
                                   # „само 19 отчетени дни от 21" - Fable 5.1, wide
                                   # seed 13, 05.09.2026. The shortfall stated as
                                   # „X … от Y", with the norm as the second number
                                   # and no word for it at all.
                                   r"\d+\s+(?:\S+\s+){0,2}(?:от|срещу)\s+\d+"],
    # The six scenarios that got their mutations on 03.09.2026 (they had checkers and
    # no generator). Each carries its subject and the shape of the defect; the shape
    # group is what keeps them apart from the F9/F7/K entries that share a subject.
    # The live phrasing of a net that does not follow: a deduction „не е удържана от
    # нетото", „не приспада", „не е приспаднат", the net „вместо" the right figure.
    # No bare „вместо" or „в повече" - both fire on any „X вместо Y" sentence
    # regardless of subject, and collided with a C2 finding that happened to phrase a
    # class-supplement error the same way (04.09.2026).
    "I1_vertical":                [r"нето|за получаване|изплат",
                                   r"минус|−|не се връзва|не отговар|не съвпад|разминав|"
                                   r"различ|аритмет|сверк|не следва от|не приспада|"
                                   r"не е приспадн|не е удържан|противоречи"],
    # The rate, not a generic mismatch word: an I1 sentence also says „данък" and
    # „разминаване", and would be credited here. A tax-amount finding names the rate.
    # A live run named neither the rate nor the word „ставка": „ДДФЛ … е сметнат върху
    # основата преди приспадането, а не върху … - надвнесен данък". The rate OR the
    # base it was applied to OR the direction of the tax error.
    # \bДДФЛ\b, not bare ДДФЛ - it matched inside „ЗДДФЛ" (the act itself, cited by
    # F7/F9/I1 too; Cyrillic letters carry no word boundary between them, so a bare
    # stem inside a longer word needs an explicit \b) and collided with an F7 sentence
    # naming чл. 19 вр. чл. 42, ал. 3 ЗДДФЛ (04.09.2026).
    "F6_tax_amount":              [r"данък|\bДДФЛ\b",
                                   r"10 ?%|10 на сто|ставк|не е 10|десет на сто|процент|"
                                   r"надвнесен|недовнесен|основата преди|основата след|"
                                   r"преди приспадането|след приспадането|върху основа"],
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
                                       r"извад|"
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
    # Two gaps from Fable 5.1, pair seed 7, 05.09.2026, on a finding that was not merely
    # right but named the checks itself: „Основна за отработеното в 08-2026 е 1360.47
    # EUR при 21 от 21 работни дни, а договорът и юли дават 764.78 EUR; допълнително
    # споразумение няма (A6/I7/I11)". It named the subject by the payroll's own column
    # („основна за отработеното", not „заплата"), and stated the discrepancy as „а
    # договорът … дават", where the pattern wanted the adjective „договорен". Both
    # widened at the phrasing; the third group still requires the missing document, so
    # nothing about K8 or E3 can reach this entry.
    "I7_unexplained_jump":  [r"заплата|възнаграждение|бруто|основна",
                             r"скок|скач|разлика|промяна|различн|мени се|повече|спрямо|"
                             r"по-висок|по-голям|ръст|увелич|нарасн|\+\d|"
                             r"(?:от|при|спрямо|срещу|а)\s+договор\w*",
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
# The комплект fixture: the chain below the payroll. These patterns are a FIRST CUT -
# unlike KEYWORDS and PAIR_KEYWORDS, no transcript has been graded against them yet, so
# a miss here is at least as likely to be a keyword gap as a model failure. Triage every
# gap against the saved transcript before believing the number, and re-grade for free.
KOMPLEKT_KEYWORDS = {
    "A10_midmonth_annex":         [r"споразумени|анекс|договор",
                                   r"заплата|възнаграждение|увеличени",
                                   r"целия месец|от началото|от 01|от 1|пропорционал|"
                                   r"от датата|част от месеца|не от"],
    "I9_person_missing_in_d1":    [r"обр\.? ?1|декларация ?1|декларацията",
                                   r"липсва|няма|без ред|не фигурира|не е подаден|"
                                   r"не присъства"],
    "I9_extra_person_in_d1":      [r"обр\.? ?1|декларация ?1",
                                   r"ведомост",
                                   r"няма|липсва|не фигурира|без съответств|непознат|"
                                   r"не присъства"],
    # „…т.21 осигурителен доход е 1647.25 при 1797.25 във ведомостта … т.21 е грешното
    # число" - seed 1 on Fable 5.1, 05.09.2026: correct, and better than the sentence
    # this pattern was written against, because it works out WHICH of the two figures
    # is wrong from the contributions on the same row. It stated the discrepancy as
    # „X при Y" and named it „грешното число", and neither reached the pattern. Widened
    # at the phrasing, not by dropping the requirement: the first pattern still has to
    # match, so no finding about other material can slip in through the second.
    "I9_insurable_differs_in_d1": [r"осигурителен доход|т\.? ?21",
                                   r"разлика|разминав|не съвпада|различ|по-малък|"
                                   r"по-нисък|занижен|грешн|вместо|при \d"],
    "I9_sick_days_differ_in_d1":  [r"болничн|неработоспособност|т\.? ?16",
                                   r"дни|дн\.",
                                   r"разминав|не съвпада|различ|повече|по-малко|"
                                   r"вместо"],
    "I9_d6_not_sum_of_d1":        [r"обр\.? ?6|декларация ?6",
                                   r"сбор|сума|общо|разминав|не съвпада|не е равн"],
    "I9_declared_not_paid":       [r"внесен|плат|превед|нареден|погасен",
                                   r"деклар|обр\.? ?6",
                                   r"разлика|по-малко|не съвпада|разминав|невнесен|"
                                   r"недовнесен"],
    "I9_net_not_paid":            [r"нето|заплата|възнаграждение",
                                   r"плат|нареден|превед|изплатен",
                                   r"по-малко|разлика|не съвпада|разминав|недоплат|"
                                   r"неизплатен"],
    "I9_ledger_differs":          [r"счетовод|оборотн|салдо|сметка 4\d\d|461|421",
                                   r"обр\.? ?6|деклар|внесен",
                                   r"разлика|разминав|не съвпада|повече|по-малко|"
                                   r"не излиза|не отговар"],
    "I10_duplicate_payment":      [r"два пъти|дублир|повторно|второ нареждане|"
                                   r"дважди|два записа|две нареждания"],
    "I10_iban_shared":            [r"IBAN|сметк",
                                   r"две лица|двама|повече от едно|едно и също|"
                                   r"един и същ|съвпада|споделен"],
}
# Suite 6 (test/generate_lifecycle.py + lifecycle_test.py): I11, the timeline across
# five months for the same five people. Never calibrated against a paid transcript, the
# same limitation KOMPLEKT_KEYWORDS above states for itself - lifecycle_test.py's own
# embedded eval-grading check proves each entry matches the sentence
# lifecycle_test.py's reconcile() itself would write, nothing more.
LIFECYCLE_KEYWORDS = {
    "I11_salary_change_without_annex": [r"заплата|възнаграждение",
                                        r"промен|повиш|увеличава се|различ",
                                        r"без.*(споразумение|анекс)|няма.*(споразумение|анекс)"],
    "I11_pay_after_termination":       [r"прекратяван|уволнен|напуснал|заповед за "
                                        r"прекратяване",
                                        r"начислен|заплата|плащане|брутото|сума",
                                        r"след.*(прекратяване|дата|напускане)"],
    "I11_severance_without_termination": [r"обезщетение.*(224|прекратяване)|чл\.? ?224",
                                          r"без.*(заповед|прекратяване)|няма.*(заповед|"
                                          r"прекратяване)"],
    "I11_sick_days_restart":           [r"болничен|болнични|неработоспособ",
                                        r"продължав|поредн|втори месец|същия спел",
                                        r"отново|повторно|втори път за сметка на "
                                        r"работодателя"],
    "I11_class_raised_early":          [r"клас",
                                        r"преди|рано|не е навършил|няма право",
                                        r"годин\w* стаж|навършва\w*|годишнина"],
    "I11_class_not_raised":            [r"клас",
                                        r"не е (?:вдигнат|повишен|променен|начислен)|"
                                        r"остава|не се променя",
                                        r"годин\w* стаж|навършва\w*|годишнина"],
}
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
# „…, за разлика от идентичния случай на ред 8, изчислен правилно." names a DIFFERENT
# row as the correct comparison, not this finding as correct - DENIES fired on it
# regardless, and a real чл. 40, ал. 1, т. 5 ЗЗО overcharge (2.7.0/Sonnet run,
# 04.09.2026) scored as a denial of itself. A comparison marker before the match means
# the "правилно" describes the OTHER thing named, not the finding's own subject.
_COMPARISON = re.compile(r"за разлика от|докато (?:при|на|за)|за разлика с|"
                         r"за сравнение с|спрямо ред", re.I)
# Scenarios whose correct finding IS a `за проверка`: the figure matches no composition
# of the row, so the honest report says the file does not explain it and asks - it does
# not assert a violation. Demanding `нарушение` there would score the right answer as
# „located only" and reward a skill that guesses a cause.
UNRESOLVED_IS_RIGHT = {"F1_insurable_unexplained", "F6_taxable_unexplained",
                       # Not unresolved but status-capped: the composition of the чл. 40,
                       # ал. 5 КСО base is `за потвърждение` in stavki.md, so a skill that
                       # computes the 23.63 EUR overpayment and writes `за проверка` is
                       # following its own cap rule. Seed 1 of the 04.09.2026 run did.
                       "F9_sick_pay_amount"}
# Group K findings are proven by arithmetic and normativna-baza.md gives them
# `дефект` OR `бележка`; a construction defect the model judged minor (a 0.05 EUR
# control-column blind spot) is still the finding.
NOTE_IS_RIGHT_FOR_GROUP = ("K",)
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
        "Приспадната лична вноска за допълнително доброволно осигуряване (278.44 EUR) "
        "надхвърля 10%-товия лимит от месечната данъчна основа (лимит 179.44 EUR) по "
        "чл. 19, ал. 2 вр. чл. 42, ал. 3 ЗДДФЛ",
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
        "Изведеният от вноските процент ТЗПБ е ефективно ~0.40% (виж AF спрямо "
        "осигурителния доход), а не декларираните от дружеството 0.50% — недовнесена "
        "ТЗПБ вноска за месеца",
    ]),
    # From the review of 03.09.2026 - correct descriptions the patterns missed outright:
    ("I5_days_do_not_reconcile", [
        "отработени 18 + отпуск 2 + болнични 2 = 22 при 21 работни дни в месеца",
        "Начислени болнични за сметка на работодателя 51.54 (= 2 дни × 70% × 36.81), но "
        "„Дни болничен“ = 0 и дните на реда са 20 вместо 22 — дните липсват от отчетността",
    ]),
    ("K5_total_not_sum", [
        "ОБЩО за колоната Карта е 1 234,58 вместо 1 234,56 по клетките",
    ]),
    ("K2_amount_in_day_column", [
        "в „Отработени дни“ стои 1 850,00 - това е пари, не бройка",
    ]),
    # From the 04.09.2026 run (2.7.0) - correct identifications scored „located only":
    ("I1_vertical", [
        "Нетото за изплащане (2118.31) не приспада личната част от картата 11.82, докато "
        "при всички други редове с такава удръжка тя е приспадната",
        "Удръжката за доброволно осигуряване 26.88 намалява данъчната основа, но не е "
        "приспадната от „НЕТО за изплащане“ (2211.09 вместо 2184.21)",
        "личната премия за застраховка Живот 211.44 EUR намалява данъчната основа, но не е "
        "удържана от нетото (нето за изплащане 4490.27 вместо 4278.83) — файлът си противоречи",
    ]),
    ("F6_tax_amount", [
        "премията за застраховка Живот 93.29 EUR е приспадната в колона Данъчна основа, но "
        "ДДФЛ 522.08 е сметнат върху основата преди приспадането (5220.83), а не върху "
        "5127.54 — надвнесен данък 9.33 EUR за сметка на лицето",
    ]),
    ("K7_cost_from_net", [
        "„Общ разход за труд“ е занижен с 40.29 — изважда личната удръжка за доброволно "
        "осигуряване, която е част от брутото",
        "Общият разход за труд на Здравка Влахова 2602.82 EUR е намален с личната част на "
        "картата",
    ]),
    ("F9_sick_pay_amount", [
        "Болничният за сметка на работодателя е изчислен като 70% x 2 дни x (основна + клас "
        "+ бонус 354.50)/21 отработени дни; по постоянната база (договор + клас) се получава "
        "139.26 EUR, т.е. 23.63 EUR в повече — бонусът е третиран като еднократен",
    ]),
    ("C2_seniority_on_gross", [
        "Клас сумата е изчислена грешно (34.21 вместо 549.23×4.2%=23.07 по чл. 12, ал. 8 "
        "НСОРЗ); грешката се пренася в брутото, осигурителния доход, данъка и нетото",
    ]),
    ("F9_health_on_sick_days", [
        "Здравната вноска при болничен е изчислена върху всички 3 дни болничен вместо "
        "само върху 1-я ден за сметка на ДОО (чл. 40, ал. 1, т. 5 ЗЗО, in fine) — "
        "надвнесено 2.30 EUR за сметка на работодателя, за разлика от идентичния случай "
        "на ред 8, изчислен правилно",
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
