"""Rates read fresh from references/stavki.md and references/stavki/*.md - never
hardcoded, and never cached across a process.

scripts/audit.py needs numbers this file's siblings do not: how much is the minimum
wage this month, the maximum insurable income, the contribution percentages, the tax
rate. None of them may be typed into Python by hand - that is exactly the "rate from
memory" CONTRIBUTING.md forbids, only moved from the model's head into a script instead
of out of it. So every value here is extracted from the reference text at call time,
the same way test/rates_test.py cross-checks trz_model.py: a pattern that does not
match exactly once returns None, and the caller must refuse rather than guess.

Two kinds of lookup:

* **Period-scoped** (`for_period`): a table row states a date range and a value: the
  minimum wage table gives one row per calendar year, the insurable-income tables one
  row per half-year (2025 and 2026 both split their year in two because each year's
  budget was adopted late). The date ranges are read from the table itself, not
  assumed, so a payroll from a year this file has never seen returns None instead of
  reusing the nearest row - the same refusal `tools/preflight.py`'s `regime_boundaries()`
  already relies on callers to handle.
* **Flat** (`FLAT_PATTERNS`): a single current percentage or rate with no date range of
  its own in the table (the contribution percentages, the tax rate, the relief limit).
  These carry a status in the file (`ДВ`, `официален`, ...) that this module does not
  read - a check using one is responsible for citing it in the finding, the way every
  other check in this skill does.

EUR only. Every period-scoped table here carries EUR figures from 2026 onward; a
period before 01.01.2026 returns None the same way a period stavki.md has no row for
would, and the model falls back to reasoning about the leva figures in prose - this
module does not convert.
"""
import datetime as dt
import os
import re

_DATE = r"(\d{2}\.\d{2}\.\d{4})"
_RANGE = rf"\|\s*{_DATE}\s*[–-]\s*{_DATE}\s*\|"


def _read_all(skill_dir):
    """references/stavki.md concatenated with every file under references/stavki/ -
    the index plus every topic, the same set test/rates_test.py's TEXT reads.
    """
    parts = []
    stavki_md = os.path.join(skill_dir, "references", "stavki.md")
    with open(stavki_md, encoding="utf8") as f:
        parts.append(f.read())
    subdir = os.path.join(skill_dir, "references", "stavki")
    if os.path.isdir(subdir):
        for fn in sorted(os.listdir(subdir)):
            if fn.endswith(".md"):
                with open(os.path.join(subdir, fn), encoding="utf8") as f:
                    parts.append(f.read())
    return "\n".join(parts)


def _parse(s):
    return dt.datetime.strptime(s, "%d.%m.%Y").date()


# name -> a regex whose first two groups are the row's date range and whose third
# group is the value, in EUR. Written against the *shape* of each table's row, not
# against any specific year, so a new row for a later period is read the same way an
# existing one is:
#   - the МРЗ table's value column reads "1213 лв. / **620.20 EUR**" - EUR is second
#     and bold, right after the date range;
#   - the insurable-income tables read "550.66 EUR | **2111.64 EUR**" - the maximum is
#     bold and in the third column, the self-employed minimum plain in the second.
PERIOD_PATTERNS = {
    "min_wage_month": rf"{_RANGE}\s*[\d.,]+\s*лв\.\s*/\s*\*\*([\d.]+) EUR\*\*",
    "max_insurable":  rf"{_RANGE}\s*[\d.]+\s*EUR\s*\|\s*\*\*([\d.]+) EUR\*\*",
}

# name -> a regex with one group: the current value, no date range of its own. Copied
# from test/rates_test.py's CHECKS where a pattern there already isolates the same
# figure - kept identical on purpose, so the two are cross-checked against the same
# text by construction rather than by two people remembering to keep them in step.
FLAT_PATTERNS = {
    "employee_total_pct":       r"Лични вноски, трета категория \|\s*\*\*([\d.]+)%\*\*",
    "employer_no_tzpb_pct":     r"без ТЗПБ, трета категория \|\s*\*\*([\d.]+)%\*\*",
    "tax_rate_pct":             r"\| Данъчна ставка \|\s*\*\*([\d.]+)%\*\*",
    "relief_limit_pct":         r"удържани от работодателя \| до \*\*([\d.]+)%\*\*",
    "sick_days_employer":       r"Режимът е \*\*(\d+) работни дни",
    "sick_rate_pct":            r"неработоспособност (\d+) на сто от среднодневното "
                                r"брутно възнаграждение",
    "health_on_incapacity_pct": r"\| Размер \|\s*\*\*([\d.]+)%\*\* — т\. 5: вноските "
                                r"са за сметка на работодателя",
    "tzpb_min_pct":             r"\| Трудова злополука и професионална болест \| "
                                r"\*\*([\d.]+) – [\d.]+%\*\*",
    "tzpb_max_pct":             r"\| Трудова злополука и професионална болест \| "
                                r"\*\*[\d.]+ – ([\d.]+)%\*\*",
    "social_expense_threshold_eur": r"Същият праг \*\*в евро за 2026 г\.\*\* \| "
                                r"\*\*([\d.]+) EUR\*\*",
}


def _extract_one(text, pattern):
    found = re.findall(pattern, text)
    return float(found[0].replace(",", ".")) if len(found) == 1 else None


def load_flat(skill_dir):
    """Every FLAT_PATTERNS rate found in the current reference text, as {name: value}.

    A name absent from the result means its pattern did not match exactly once - the
    reference file changed shape, or does not (yet) state that rate. Callers index
    with .get(name) and refuse the check the missing rate feeds, never a default.
    """
    text = _read_all(skill_dir)
    return {name: v for name, pat in FLAT_PATTERNS.items()
            if (v := _extract_one(text, pat)) is not None}


def other_periods_in_year(skill_dir, name, year, month):
    """Every PERIOD_PATTERNS value for `name` whose row falls in `year` but whose
    range does NOT contain (year, month) - the neighbouring half-year's threshold, for
    checks like B4 that must also catch a cap copied from the *other* half rather than
    only a cap the row exceeds outright. A row sitting exactly on one of these, while
    under its own period's value, is copied from the wrong period - not just wrong by
    an unexplained amount.
    """
    text = _read_all(skill_dir)
    pattern = PERIOD_PATTERNS[name]
    target = dt.date(year, month, 1)
    out = []
    for m in re.finditer(pattern, text):
        try:
            start, end = _parse(m.group(1)), _parse(m.group(2))
        except ValueError:
            continue
        if (start.year == year or end.year == year) and not (start <= target <= end):
            out.append(float(m.group(3).replace(",", ".")))
    return out


def for_period(skill_dir, name, year, month):
    """The PERIOD_PATTERNS value of `name` whose table row's date range contains the
    first of (year, month), or None when no row does - a period this file has no
    rate for, not a guess at the nearest one.

    Every OTHER value this module returns is guarded against matching more than
    once (load_flat()'s docstring states the same contract for FLAT_PATTERNS); this
    one used to return the first match via re.finditer() instead, so two rows that
    both cover the same period - a duplicated or decoy line above the real one, the
    same failure test/rates_test.py's extract() exists to catch in the reference
    file itself - would silently hand back whichever came first, not necessarily the
    right one. Collecting every match and refusing on a genuine disagreement between
    them keeps that same guarantee here: an ambiguous period is None, not a guess.
    """
    text = _read_all(skill_dir)
    pattern = PERIOD_PATTERNS[name]
    target = dt.date(year, month, 1)
    values = []
    for m in re.finditer(pattern, text):
        try:
            start, end = _parse(m.group(1)), _parse(m.group(2))
        except ValueError:
            continue
        if start <= target <= end:
            values.append(float(m.group(3).replace(",", ".")))
    if len(set(values)) > 1:
        return None
    return values[0] if values else None
