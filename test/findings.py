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
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REFERENCES = os.path.normpath(os.path.join(HERE, "..", "skills", "trz-expert", "references"))
SCRIPTS = os.path.normpath(os.path.join(HERE, "..", "skills", "trz-expert", "scripts"))
sys.path.insert(0, SCRIPTS)
import finding as FN                                          # noqa: E402

# The one basis that is not a citation. Group K (file construction) and group I
# (arithmetic and cross-document consistency) are proven by the file's own numbers;
# normativna-baza.md, „Проверки без нормативно основание", says so and adds the
# contested material of F10, where the basis is the file's inconsistency with itself,
# never an article.
ARITHMETIC = "arithmetic"
ARITHMETIC_GROUPS = ("K", "I")
ARITHMETIC_PREFIXES = ("F10_",)

# Citations are quoted from the reference files - see grounded(). Several on one line
# are separated by ";". Entries for ids skills/trz-expert/scripts/audit.py and
# k_checker.py themselves raise (I1_vertical, K2/K5/K6, B1/B4/B5, F1/F5/F9/F10) live in
# scripts/finding.BASIS, imported below, not copied here - CLAUDE.md's "reference file
# leads" rule applied to citations, not only rates: one owner per fact, so a citation
# cannot drift between what the script asserts and what this file grades it against.
BASIS = {
    **FN.BASIS,
    # K - file construction. Proven by arithmetic; normativna-baza.md forbids inventing
    # a basis for these. K1/K3/K4/K7/K8 and the KF ids are not computed by any script
    # (k_checker.py's own module docstring explains why) - only their citation lives
    # here.
    "K1_sum_omits_column": ARITHMETIC,
    "K3_stale_contributions": ARITHMETIC,
    "K4_control_column_blind": ARITHMETIC,
    "K7_cost_from_net": ARITHMETIC,
    "K8_stale_thresholds": ARITHMETIC,
    "KF1_sum_omits_column": ARITHMETIC,
    "KF2_days_in_money_sum": ARITHMETIC,
    "KF3_hard_value_in_formula_column": ARITHMETIC,
    "KF4_tautological_control": ARITHMETIC,
    "KF5_constant_in_formula": ARITHMETIC,
    "KF_shape_deviates": ARITHMETIC,
    # I - arithmetic and cross-document consistency.
    "I5_days_do_not_reconcile": ARITHMETIC,
    "I7_unexplained_jump": ARITHMETIC,
    # I9/I10 - the chain below the payroll (suite 5, the комплект). Document against
    # document: proverki.md says so itself for transitions 1, 2 and 4, and the paid
    # leg is a comparison of two figures too - what обр. 6 declares against what left
    # the account. The obligation behind it is cited in the report, not here.
    "I9_person_missing_in_d1": ARITHMETIC,
    "I9_extra_person_in_d1": ARITHMETIC,
    "I9_insurable_differs_in_d1": ARITHMETIC,
    "I9_sick_days_differ_in_d1": ARITHMETIC,
    "I9_d6_not_sum_of_d1": ARITHMETIC,
    "I9_declared_not_paid": ARITHMETIC,
    "I9_net_not_paid": ARITHMETIC,
    "I9_ledger_differs": ARITHMETIC,
    "I10_duplicate_payment": ARITHMETIC,
    "I10_iban_shared": ARITHMETIC,
    # I11 - the timeline (suite 6). A change compared with the document that should
    # stand behind it, or one month compared with the next: the basis is the sequence
    # itself, which is arithmetic in the same sense group I always is.
    "I11_salary_change_without_annex": ARITHMETIC,
    "I11_pay_after_termination": ARITHMETIC,
    "I11_severance_without_termination": ARITHMETIC,
    "I11_sick_days_restart": ARITHMETIC,
    "I11_class_raised_early": ARITHMETIC,
    "I11_class_not_raised": ARITHMETIC,
    # A-J - quoted from the reference files.
    "A6_base_vs_contract": "чл. 66 КТ; чл. 128 КТ",
    "A10_midmonth_annex": "чл. 66 КТ; чл. 128 КТ",
    "C2_seniority_on_gross": "чл. 12, ал. 1 НСОРЗ",
    "E3_leave_without_seniority": "чл. 17, ал. 1 НСОРЗ",
    "E3_leave_base": "чл. 17, ал. 1 НСОРЗ; чл. 18, ал. 1 НСОРЗ; чл. 18, ал. 2 НСОРЗ",
    "F6_taxable_unexplained": "чл. 42, ал. 2 ЗДДФЛ",
    "F6_tax_amount": "чл. 42, ал. 4 ЗДДФЛ",
    "F6_compensation_out_of_taxable": "чл. 24, ал. 2, т. 8 ЗДДФЛ",
    "F7_relief_over_limit": "чл. 19, ал. 2 във вр. с чл. 42, ал. 3 ЗДДФЛ",
    "F7_relief_combined_limit": "чл. 19, ал. 2 във вр. с чл. 42, ал. 3 ЗДДФЛ",
    "F7_relief_not_applied": "чл. 19, ал. 2 във вр. с чл. 42, ал. 3 ЗДДФЛ",
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
    # stavki.md and proverki.md are index/summary files; the full text - and any citation
    # quoted inside it - lives in the per-group/per-topic files under these two
    # subdirectories. Read every one, so a citation moving with its bullet does not stop
    # being grounded.
    for sub in ("proverki", "stavki"):
        subdir = os.path.join(REFERENCES, sub)
        if os.path.isdir(subdir):
            for fn in sorted(os.listdir(subdir)):
                if fn.endswith(".md"):
                    with open(os.path.join(subdir, fn), encoding="utf8") as f:
                        parts.append(_squash(f.read()))
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
