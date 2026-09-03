# -*- coding: utf-8 -*-
"""The findings ledger the checkers keep score in — one copy, imported by all three.

structural_test, pair_test and formula_test each carried an identical class once; a
change to how a finding is recorded then had to be made twice, and the two could
drift apart in silence — the shape of failure this suite exists to catch in payroll
files.

A finding needs a basis. CLAUDE.md states it as a rule that is not negotiable —
statutory reference for groups A–J, arithmetic said plainly for group K — and until
2026-09-03 nothing enforced it: this class had no basis field, and the static suite's
free-text `basis` was printed and never read. `BASIS` below is the one table; every
finding id the suites can raise has an entry, and `Findings.add` refuses an id that
has none. The statutory entries are **quoted** from the skill's reference files, not
typed here: `grounded()` requires each citation to appear verbatim in stavki.md,
proverki.md or normativna-baza.md, so a basis cannot be an article the reference
does not carry — the way an article gets invented to fill the field.
"""
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
REFERENCES = os.path.normpath(os.path.join(HERE, "..", "skills", "trz-expert", "references"))

# The one basis that is not a citation. Group K (file construction) and group I
# (arithmetic and cross-document consistency) are proven by the file's own numbers;
# normativna-baza.md, „Проверки без нормативно основание", says so and adds the
# contested material of F10, where the basis is the file's inconsistency with itself,
# never an article.
ARITHMETIC = "arithmetic"
ARITHMETIC_GROUPS = ("K", "I")
ARITHMETIC_PREFIXES = ("F10_",)

# Citations are quoted from the reference files - see grounded(). Several on one line
# are separated by ";".
BASIS = {
    # K - file construction. Proven by arithmetic; normativna-baza.md forbids inventing
    # a basis for these.
    "K1_sum_omits_column": ARITHMETIC,
    "K2_amount_in_day_column": ARITHMETIC,
    "K3_stale_contributions": ARITHMETIC,
    "K4_control_column_blind": ARITHMETIC,
    "K5_total_not_sum": ARITHMETIC,
    "K6_unrounded_accrual": ARITHMETIC,
    "K7_cost_from_net": ARITHMETIC,
    "K8_stale_thresholds": ARITHMETIC,
    "KF1_sum_omits_column": ARITHMETIC,
    "KF2_days_in_money_sum": ARITHMETIC,
    "KF3_hard_value_in_formula_column": ARITHMETIC,
    "KF4_tautological_control": ARITHMETIC,
    "KF5_constant_in_formula": ARITHMETIC,
    "KF_shape_deviates": ARITHMETIC,
    # I - arithmetic and cross-document consistency.
    "I1_vertical": ARITHMETIC,
    "I5_days_do_not_reconcile": ARITHMETIC,
    "I7_unexplained_jump": ARITHMETIC,
    # F10 - the contested material. The basis is the file's inconsistency, not a ruling
    # on which reading is right.
    "F10_in_kind_asymmetry": ARITHMETIC,
    "F10_excess_asymmetry": ARITHMETIC,
    "F10_practice_not_establishable": ARITHMETIC,
    # A-J - quoted from the reference files.
    "A6_base_vs_contract": "чл. 66 КТ; чл. 128 КТ",
    "B4_cap_from_wrong_period": "чл. 9 ЗБДОО за 2026 г",
    "C2_seniority_on_gross": "чл. 12, ал. 1 НСОРЗ",
    "E3_leave_without_seniority": "чл. 17, ал. 1 НСОРЗ",
    "E3_leave_base": "чл. 17, ал. 1 НСОРЗ; чл. 18, ал. 1 НСОРЗ; чл. 18, ал. 2 НСОРЗ",
    "F1_compensation_in_insurable": "чл. 1, ал. 8, т. 7 НЕВДПОВ",
    "F1_insurable_unexplained": "чл. 3, ал. 1 НЕВДПОВ; чл. 6, ал. 2 КСО",
    "F5_tzpb_below_due": "приложения № 2 и № 2А към ЗБДОО",
    "F6_taxable_unexplained": "чл. 42, ал. 2 ЗДДФЛ",
    "F6_tax_amount": "чл. 42, ал. 4 ЗДДФЛ",
    "F6_compensation_out_of_taxable": "чл. 24, ал. 2, т. 8 ЗДДФЛ",
    "F7_relief_over_limit": "чл. 19, ал. 2 във вр. с чл. 42, ал. 3 ЗДДФЛ",
    "F7_relief_combined_limit": "чл. 19, ал. 2 във вр. с чл. 42, ал. 3 ЗДДФЛ",
    "F7_relief_not_applied": "чл. 19, ал. 2 във вр. с чл. 42, ал. 3 ЗДДФЛ",
    "F9_sick_pay_out_of_insurable": "чл. 3, ал. 1 НЕВДПОВ",
    "F9_sick_pay_in_taxable": "чл. 24, ал. 2, т. 14 ЗДДФЛ",
    "F9_sick_pay_amount": "чл. 40, ал. 5 КСО; чл. 17, ал. 1 НСОРЗ",
    "F9_health_on_sick_days": "чл. 40, ал. 1, т. 5 ЗЗО",
}

# What a citation must contain to count as one: an article, a paragraph sign, an
# annex, a decree or a point of the declaration form. „ЗДДФЛ" alone is an act, not a
# reference.
_ANCHOR = re.compile(r"чл\.\s*\d|§\s*\d|приложени[ея]\s*№|ПМС\s*№|т\.\s*\d+\s+от\s+Декларация")

# normativna-baza.md lists articles per act in tables whose rows carry the article
# without the act's abbreviation - „| Официални празници | чл. 154 |" under the
# heading „Кодекс на труда". These headings tell which act each table belongs to, so
# the rows can be read as „чл. 154 КТ".
_ACT_BY_HEADING = {
    "Кодекс на труда": "КТ",
    "Наредба за структурата и организацията на работната заплата": "НСОРЗ",
    "Наредба за работното време, почивките и отпуските": "НРВПО",
    "Кодекс за социално осигуряване": "КСО",
}


def _squash(text):
    return " ".join(text.split())


def _map_expansions(text):
    out = []
    act = None
    for line in text.splitlines():
        if line.startswith("## "):
            act = _ACT_BY_HEADING.get(line[3:].strip())
            continue
        if act and line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 2:
                continue
            for ref in re.split(r",\s*(?=чл\.)", cells[-1]):
                ref = ref.strip()
                if ref.startswith("чл.") and act not in ref:
                    out.append(f"{ref} {act}")
    return " ; ".join(out)


def _reference_text():
    parts = []
    for name in ("stavki.md", "proverki.md", "normativna-baza.md"):
        with open(os.path.join(REFERENCES, name), encoding="utf8") as f:
            text = f.read()
        parts.append(_squash(text))
        if name == "normativna-baza.md":
            parts.append(_map_expansions(text))
    return " \n ".join(parts)


_REFERENCE = None


def reference_text():
    global _REFERENCE
    if _REFERENCE is None:
        _REFERENCE = _reference_text()
    return _REFERENCE


def group_of(ident):
    m = re.match(r"([A-K])", ident)
    return m.group(1) if m else None


def grounded(ident, basis):
    """None when the basis is admissible for this finding id, else what is wrong.

    Arithmetic is admissible for groups K and I and for the F10 consistency checks;
    everywhere else the basis is one or more citations, each of which must appear
    verbatim in the reference files (whitespace aside) and must name an article, a
    paragraph, an annex, a decree or a point of the declaration form.
    """
    group = group_of(ident)
    if group is None:
        return f"{ident}: finding id does not start with a check group letter"
    if not str(basis or "").strip():
        return f"{ident}: empty basis"
    if _squash(basis) == ARITHMETIC:
        if group in ARITHMETIC_GROUPS or ident.startswith(ARITHMETIC_PREFIXES):
            return None
        return (f"{ident}: group {group} needs a statutory reference, not "
                f"'{ARITHMETIC}' - see normativna-baza.md")
    ref = reference_text()
    for part in str(basis).split(";"):
        part = _squash(part)
        if not part:
            return f"{ident}: empty citation in {basis!r}"
        if not _ANCHOR.search(part):
            return (f"{ident}: '{part}' names no article, annex, decree or point - an "
                    f"act alone is not a reference")
        if part not in ref:
            return (f"{ident}: '{part}' is not quoted anywhere in "
                    f"skills/trz-expert/references - add it there with a source and a "
                    f"status before citing it, never the other way round")
    return None


def check_table():
    """Every entry in BASIS admissible, and every scenario the suites inject present."""
    problems = [p for p in (grounded(i, b) for i, b in BASIS.items()) if p]
    import trz_model as M
    known = set(M.SCENARIOS) | set(M.PAIR_SCENARIOS) | set(M.FORMULA_SCENARIOS)
    problems += [f"{i}: injected by a suite but has no entry in findings.BASIS"
                 for i in sorted(known - set(BASIS))]
    return problems


_problems = check_table()
if _problems:
    raise ImportError("findings.BASIS is not usable:\n  " + "\n  ".join(_problems))


class Findings:
    def __init__(self):
        self.items = []
        self._seen = set()

    def add(self, ident, where, text, stated=None, due=None):
        if ident not in BASIS:
            raise KeyError(f"{ident}: no entry in findings.BASIS - a finding needs a basis")
        if (where, ident) in self._seen:
            return                     # one finding per (location, kind)
        self._seen.add((where, ident))
        self.items.append(dict(id=ident, where=where, text=text, stated=stated, due=due,
                               basis=BASIS[ident]))

    def keys(self):
        return {(f["where"], f["id"]) for f in self.items}
