"""Canonical shape for a finding raised by this repo's own deterministic checkers
(audit.py, k_checker.py) - not the model's prose report, which otchet.md governs.

Before this, audit.py and k_checker.py each built findings as ad hoc dicts with
different field names for the same idea (audit.py's `row`+`sheet` vs k_checker.py's
single `ref`; k_checker.py's K5 `stated`/`computed` vs K6's bare `value`), and neither
carried a `basis` field at all - a real gap against CLAUDE.md's not-negotiable rule
that a finding needs a basis. `make_finding()` is the one place that builds a finding
dict for either script, so the shape cannot drift between them again, and it refuses
to build one with no basis rather than silently omitting the field.

The BASIS table below is scoped to the ids these two scripts raise. It is not a
second copy of test/findings.py's own table - that file imports this one for the ids
they share and keeps its own entries only for ids no script here raises (I7, I9-I11,
the A/C/E/F group citations no automated check yet computes). One citation per id,
owned by whichever side actually raises the id, the same principle CLAUDE.md states
for rates: the reference file leads, and nothing downstream keeps a second, driftable
copy of a fact instead of importing the one copy.
"""

SEVERITIES = ("нарушение", "риск", "за проверка", "дефект", "бележка")

# The one value a finding raised by audit.py or k_checker.py can have for `confidence`.
# Not a second severity, and not a percentage - otchet.md already grades legal
# certainty through severity's own status-caps-severity rule (a finding capped by an
# unconfirmed stavki.md row is `за проверка` regardless of how sure the model is).
# What `confidence` draws instead is provenance: every finding either script raises
# came from code comparing a row's own numbers, or a rate read fresh from stavki.md at
# call time - never a model judgement call. otchet.md's „Увереност" field asks the
# model to keep this value when it repeats a script's finding in prose, rather than
# relabel it `изведено` (derived) just because it is now written in words.
CONFIDENCE_COMPUTED = "изчислено"

# The one basis that is not a citation - group K (file construction) and the
# arithmetic/cross-document half of group I, per normativna-baza.md's
# „Проверки без нормативно основание". test/findings.py's grounded() enforces that
# this literal string is admissible only for those groups (and the F10 ids, which are
# the file's inconsistency with itself, never a ruling on which reading is right).
ARITHMETIC = "arithmetic"

# Citations are quoted verbatim from skills/trz-expert/references/*; test/findings.py's
# grounded() (run at import time, by both this module's own self-test below and
# test/findings.py's) fails the whole test suite if one stops matching the text there.
BASIS = {
    # I - a row's own numbers, or two rows compared, never a memory-derived amount.
    "I1_vertical": ARITHMETIC,
    "I5_sick_pay_without_days": ARITHMETIC,
    "I8_duplicated_people": ARITHMETIC,
    # K - file construction, proven by arithmetic.
    "K2_amount_in_day_column": ARITHMETIC,
    "K5_total_not_sum": ARITHMETIC,
    "K6_unrounded_accrual": ARITHMETIC,
    # B - minimum/maximum thresholds, statutory.
    "B1_below_minimum_wage": "чл. 244, т. 1 КТ",
    "B5_insurable_below_minimum_wage": "чл. 244, т. 1 КТ",
    "B4_cap_from_wrong_period": "чл. 9 ЗБДОО за 2026 г",
    # F - insurable-income composition and the accident-insurance rate.
    "F5_tzpb_below_due": "приложения № 2 и № 2А към ЗБДОО",
    "F1_insurable_unexplained": "чл. 3, ал. 1 НЕВДПОВ; чл. 6, ал. 2 КСО",
    "F1_compensation_in_insurable": "чл. 1, ал. 8, т. 7 НЕВДПОВ",
    "F9_sick_pay_out_of_insurable": "чл. 3, ал. 1 НЕВДПОВ",
    "F10_in_kind_asymmetry": ARITHMETIC,
    "F10_excess_asymmetry": ARITHMETIC,
    "F10_practice_not_establishable": ARITHMETIC,
}


def make_finding(id, text, *, sheet=None, row=None, ref=None, person=None,
                  basis=None, stated=None, due=None, severity=None,
                  confidence=CONFIDENCE_COMPUTED, action=None, **extra):
    """Build one finding as a plain dict - a dict, not a dataclass, because every
    existing caller (audit_test.py, k_checker_test.py) already indexes a finding with
    f["id"], f["row"], f["text"] and a dict needs no migration there.

    `basis` defaults to this module's BASIS table by id; a caller may still pass one
    explicitly (k_checker.py's report() prints per-check text that already differs
    from audit.py's, and a future check outside this table's scope would need to),
    but an id with neither raises rather than building a finding with no basis at
    all - the CLAUDE.md rule enforced at construction, not left to whoever renders
    the report later.

    `difference` is derived from stated/due, never accepted as its own argument: a
    caller cannot pass a difference that disagrees with stated - due.

    `severity` defaults to `дефект` when the basis is arithmetic - otchet.md states
    this as a hard rule with no cap to check ("група K и находките за вътрешно
    противоречие ... тежестта им остава дефект"), so it costs nothing to bake in here
    instead of leaving every caller to repeat it. A citation basis leaves severity
    None: which severity a statutory finding earns depends on the *status* of the
    stavki.md row it stands on (otchet.md's status-caps-severity table), and
    scripts/rates.py deliberately does not read that status - "a check using one is
    responsible for citing it in the finding" is that module's own docstring, and
    duplicating its status-reading here to guess a severity would cross a boundary
    the rest of this codebase drew on purpose. The model still applies that rule in
    prose, unchanged from before this module existed.

    `confidence` defaults to CONFIDENCE_COMPUTED: every finding either caller raises
    is, by construction, a row's own numbers or a rate read fresh from stavki.md -
    never a model judgement call.
    """
    basis = basis if basis is not None else BASIS.get(id)
    if not basis:
        raise KeyError(f"{id}: no entry in finding.BASIS and none given - a finding "
                        f"needs a basis (CLAUDE.md's not-negotiable rule)")
    if severity is None and basis == ARITHMETIC:
        severity = "дефект"
    if severity is not None and severity not in SEVERITIES:
        raise ValueError(f"{id}: unknown severity {severity!r}")
    difference = None if stated is None or due is None else round(due - stated, 2)
    out = {
        "id": id, "text": text, "sheet": sheet, "row": row, "ref": ref,
        "person": person, "basis": basis, "stated": stated, "due": due,
        "difference": difference, "severity": severity,
        "confidence": confidence, "action": action,
    }
    out.update(extra)
    return out
