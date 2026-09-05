#!/usr/bin/env python3
"""Pre-flight check for a real payroll workbook, run before the audit.

This is not a second auditor. It is a gatekeeper: it answers whether the file can be
audited at all, and names what is missing so the answer is not discovered halfway
through. Half the checks in `references/proverki.md` come back „недостатъчни данни" for
reasons visible before the audit starts and fixable once.

Three rules shape the whole tool:

* **The original is never modified.** The workbook is evidence. It is opened, read and
  closed; nothing is written back, and the normalised extract of phase 3 will go to a
  separate file rather than into this one.
* **Nothing is guessed.** Period boundaries are read from `references/stavki.md`, the
  same file the skill takes its figures from, so this tool cannot drift from it. Values
  that are not in the workbook at all - КИД, квалификационна група, ТЗПБ - are reported
  as required inputs, never inferred from the numbers.
* **No personal data leaves the file.** The report is keyed by sheet, row and column
  header. Cell values are counted and classified, never echoed, and the name column is
  located precisely so that it can be left alone.

Code and comments here are English, per the repository convention. Two things are
Bulgarian because they are data rather than prose: the column headers, which are matched
by their real text, and the report itself, which is read by Bulgarian payroll staff and
has to use the same words as the audit it feeds.

Usage:
    python tools/preflight.py ВЕДОМОСТ.xlsx [--kid 62] [--group 3] [--tzpb 0.4]
                                            [--out report.md]

Exit codes: 0 auditable (warnings allowed), 1 blocked, 2 could not read the file.
"""

import argparse
import datetime as dt
import os
import re
import sys

try:
    import openpyxl
except ImportError:                                          # pragma: no cover
    sys.exit("openpyxl is required: pip install -r test/requirements.txt")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAVKI = os.path.join(ROOT, "skills", "trz-expert", "references", "stavki.md")

# --------------------------------------------------------------- column vocabulary
# concept -> (required, accepted header spellings). The canonical spellings are the ones
# test/trz_model.py generates, which mirror a real accounting-firm layout; the rest are
# the variants real exports use for the same quantity. test/preflight_test.py asserts
# every canonical name is still recognised here, so the two cannot drift apart silently.
CONCEPTS = {
    "име":            (True,  ["име", "имена", "трите имена", "служител", "работник",
                               "лице"]),
    "отработени дни": (True,  ["отраб. дни", "отработени дни", "изработени дни",
                               "раб. дни", "отработени"]),
    "основна":        (True,  ["основна за отработеното", "основна заплата",
                               "основно възнаграждение", "основна", "заплата"]),
    "бруто":          (True,  ["бруто", "брутно", "брутно възнаграждение",
                               "общо начислено", "всичко начислено"]),
    "осиг. доход":    (True,  ["осигурителен доход", "осиг. доход", "осиг доход",
                               "доход за осигуряване"]),
    "данъчна основа": (True,  ["данъчна основа", "основа за данък",
                               "облагаема основа"]),
    "данък":          (True,  ["ддфл", "данък", "данък общ доход", "дод"]),
    "лични вноски":   (True,  ["лични вноски общо", "лични осигуровки",
                               "осигуровки лице", "лични вноски"]),
    "нето":           (True,  ["нето за изплащане", "нето преди удръжки", "нето",
                               "сума за получаване", "за получаване"]),
    "вноски раб-л":   (False, ["вноски работодател общо", "вноски работодател",
                               "осигуровки работодател"]),
    "клас":           (False, ["клас сума", "клас %", "клас прослужено време",
                               "прослужено време", "стаж"]),
    "дни отпуск":     (False, ["дни платен отпуск", "дни отпуск", "отпуск дни"]),
    "дни болничен":   (False, ["дни болничен", "болнични дни", "дни временна "
                               "неработоспособност"]),
    "болнични":       (False, ["болнични (работодател)", "болнични работодател",
                               "обезщетение чл. 40, ал. 5"]),
    "изплатено":      (False, ["изплатено", "платено", "изплатена сума"]),
}

# Which check groups stop being answerable when a concept is absent. Only groups the
# audit would otherwise run - this is the bridge into the report's closing section, and
# the wording matches „какво не е проверено" in SKILL.md on purpose.
DEPENDS = {
    "осиг. доход":    "B3, B4, F1, F2 - осигурителният доход не може да се сверява",
    "данъчна основа": "F6, I1 - данъчната основа не може да се сверява",
    "данък":          "F6, F7, I1 - данъкът не може да се сверява",
    "лични вноски":   "F2, I1 - разпределението на вноските не може да се провери",
    "нето":           "I1, K7 - вертикалната сверка не може да се затвори",
    "бруто":          "I2, K1 - хоризонталната сверка не може да се затвори",
    "клас":           "C1, C2, C3 - класът не може да се провери",
    "дни болничен":   "F9 - дните за сметка на работодателя не могат да се разделят",
    "изплатено":      "I9 - веригата до изплатеното не може да се затвори",
}

TOTALS_LABEL = re.compile(r"^\s*(общо|всичко|тотал|сума)\b", re.I)
MONTHS = {"януари": 1, "февруари": 2, "март": 3, "април": 4, "май": 5, "юни": 6,
          "юли": 7, "август": 8, "септември": 9, "октомври": 10, "ноември": 11,
          "декември": 12}


def norm(text):
    """Header text reduced to what identifies it: lowercase, no punctuation runs."""
    s = str(text or "").strip().lower().replace("ё", "е")
    s = re.sub(r"[«»\"'`]+", "", s)
    return re.sub(r"\s+", " ", s)


def regime_boundaries(path=STAVKI):
    """Period boundaries as (start, end) dates, read from the МОД table in stavki.md.

    Read rather than hardcoded: the mid-year split is the thing a copied sheet gets
    wrong, and a second copy of those dates here would be one more place to forget when
    the budget moves them. Same reason rates_test.py parses the file instead of trusting
    trz_model.py.
    """
    try:
        with open(path, encoding="utf8") as f:
            text = f.read()
    except OSError:
        return []
    seen, out = set(), []
    for a, b in re.findall(r"\|\s*(\d{2}\.\d{2}\.\d{4})\s*[–-]\s*(\d{2}\.\d{2}\.\d{4})",
                           text):
        if (a, b) in seen:
            continue
        seen.add((a, b))
        try:
            out.append((dt.datetime.strptime(a, "%d.%m.%Y").date(),
                        dt.datetime.strptime(b, "%d.%m.%Y").date()))
        except ValueError:
            continue
    return sorted(out)


def sheet_period(sheet_name, ws):
    """(year, month) for a sheet, from its name or the first few cells, else None.

    Real files label the month in the tab, in a title cell, or not at all. Nothing is
    inferred from the numbers: an unlabelled sheet is reported as unlabelled, because
    guessing the period picks the thresholds.
    """
    haystacks = [str(sheet_name)]
    for row in ws.iter_rows(min_row=1, max_row=4, max_col=12, values_only=True):
        haystacks += [str(v) for v in row if isinstance(v, str)]
    for h in haystacks:
        m = re.search(r"(\d{1,2})[-./](\d{4})", h)
        if m and 1 <= int(m.group(1)) <= 12:
            return int(m.group(2)), int(m.group(1))
        m = re.search(r"(\d{4})[-./](\d{1,2})(?!\d)", h)
        if m and 1 <= int(m.group(2)) <= 12:
            return int(m.group(1)), int(m.group(2))
        low = h.lower()
        for name, num in MONTHS.items():
            if name in low:
                y = re.search(r"(20\d{2})", h)
                if y:
                    return int(y.group(1)), num
    return None


def find_header_row(ws, limit=15):
    """The row that names the columns: the one matching most known concepts.

    Scored rather than assumed to be row 1, because real files carry a title, a company
    line and sometimes a blank before the headers start.
    """
    best, best_score = None, 0
    for r in range(1, min(limit, ws.max_row or 1) + 1):
        values = [c.value for c in ws[r]]
        score = sum(1 for v in values if classify(v))
        if score > best_score:
            best, best_score = r, score
    return (best, best_score) if best_score >= 3 else (None, best_score)


def classify(header):
    """The concept a header names, or None.

    Three passes, narrowest first: exact spelling, then substring, then every word of a
    spelling present in the header in any order. The last pass is what recognises
    „Болнични от работодател" as „Болнични (работодател)" - real headers insert a
    preposition, a bracket or a unit into the middle of an otherwise standard name, and
    matching on substrings alone sends them to the unknown list.
    """
    h = norm(header)
    if not h:
        return None
    for concept, (_, spellings) in CONCEPTS.items():
        if h in spellings:
            return concept
    for concept, (_, spellings) in CONCEPTS.items():
        for s in spellings:
            if len(s) >= 5 and s in h:
                return concept
    words = set(re.findall(r"\w+", h))
    for concept, (_, spellings) in CONCEPTS.items():
        for s in spellings:
            tokens = [t for t in re.findall(r"\w+", s) if len(t) > 2]
            if len(tokens) >= 2 and set(tokens) <= words:
                return concept
    return None


def data_range(ws, header_row):
    """(first, last) data row: from under the headers to the row before the totals.

    The totals row is excluded because it is not a person, and every per-row check that
    treats it as one produces a finding against nobody.
    """
    first = header_row + 1
    last, totals = ws.max_row, None
    for r in range(first, (ws.max_row or first) + 1):
        for c in range(1, min(4, (ws.max_column or 1) + 1)):
            if TOTALS_LABEL.match(str(ws.cell(r, c).value or "")):
                totals = r
                break
        if totals:
            break
    if totals:
        last = totals - 1
    return first, last, totals


def scan(path, kid=None, group=None, tzpb=None):
    """Read the workbook and return everything the report needs. Never writes."""
    formulas = openpyxl.load_workbook(path, data_only=False)
    values = openpyxl.load_workbook(path, data_only=True)
    out = {"file": os.path.basename(path), "sheets": [], "boundaries": regime_boundaries(),
           "kid": kid, "group": group, "tzpb": tzpb}

    for name in formulas.sheetnames:
        wf, wv = formulas[name], values[name]
        header_row, score = find_header_row(wv)
        info = {"name": name, "header_row": header_row, "matched": score,
                "period": sheet_period(name, wv), "rows": 0, "totals_row": None,
                "known": {}, "unknown": [], "formula_cells": 0, "value_cells": 0,
                "merged": [], "name_col": None}
        out["sheets"].append(info)
        if header_row is None:
            continue

        for c in range(1, (wv.max_column or 1) + 1):
            raw = wv.cell(header_row, c).value
            if raw is None or not str(raw).strip():
                continue
            concept = classify(raw)
            if concept:
                info["known"].setdefault(concept, str(raw).strip())
                if concept == "име":
                    info["name_col"] = c
            else:
                info["unknown"].append(str(raw).strip())

        first, last, totals = data_range(wv, header_row)
        info["totals_row"], info["rows"] = totals, max(0, last - first + 1)

        # Formula coverage over the data block. A values-only export is not a defect in
        # itself, but it removes the evidence the K group works from, and the audit has
        # to say so rather than quietly checking less.
        for r in range(first, last + 1):
            for c in range(1, (wf.max_column or 1) + 1):
                v = wf.cell(r, c).value
                if isinstance(v, str) and v.startswith("="):
                    info["formula_cells"] += 1
                elif v is not None:
                    info["value_cells"] += 1

        info["merged"] = [str(rng) for rng in getattr(wf, "merged_cells", []).ranges
                          if rng.min_row >= header_row] if hasattr(
                              wf, "merged_cells") else []
    return out


def report(data):
    """The pre-flight report, in Bulgarian, and whether anything blocks the audit."""
    L, blocking = [], []
    L.append(f"# Предварителна проверка — `{data['file']}`\n")
    L.append("Проверката е само за четене: файлът не е променян.\n")

    for s in data["sheets"]:
        L.append(f"\n## Лист „{s['name']}“\n")
        if s["header_row"] is None:
            L.append(f"- **Заглавният ред не е намерен** (разпознати {s['matched']} "
                     f"колони). Одитът не може да тръгне по този лист.")
            blocking.append(f"лист „{s['name']}“: няма разпознаваем заглавен ред")
            continue

        L.append(f"- заглавен ред: {s['header_row']}; редове с данни: {s['rows']}"
                 + (f"; ред с общи суми: {s['totals_row']}" if s["totals_row"]
                    else "; **ред с общи суми не е намерен** (K5 няма какво да сверява)"))

        period = s["period"]
        if period:
            y, m = period
            L.append(f"- период: {m:02d}.{y}")
            for a, b in data["boundaries"]:
                if a.year == y and a <= dt.date(y, m, 1) <= b and (a.month, a.day) != (1, 1):
                    L.append(f"  - режимът за периода започва на {a:%d.%m.%Y} — "
                             f"праговете се сменят в средата на годината; лист, копиран "
                             f"от предходния месец, носи чужди прагове (K8)")
        else:
            L.append("- **периодът не е обявен на листа** — не се извежда от числата; "
                     "подай го, иначе всяка проверка срещу праг е недостатъчни данни")
            blocking.append(f"лист „{s['name']}“: неизвестен период")

        total = s["formula_cells"] + s["value_cells"]
        share = (100.0 * s["formula_cells"] / total) if total else 0.0
        if s["formula_cells"] == 0:
            L.append("- **няма нито една формула** — файлът е експорт само със "
                     "стойности. Групата K (конструкция на файла) отпада почти изцяло: "
                     "обхват на сумите, твърди стойности, слепи контроли. Одитът остава "
                     "възможен, но го казва изрично.")
        else:
            L.append(f"- формули: {s['formula_cells']} от {total} клетки "
                     f"({share:.0f}%) — конструкцията може да се провери")

        if s["merged"]:
            L.append(f"- **слети клетки в обхвата на данните**: {len(s['merged'])} "
                     f"({', '.join(s['merged'][:5])}) — редовете се разместват при "
                     f"четене; разделѝ ги в работно копие, не в оригинала")

        missing = [c for c, (req, _) in CONCEPTS.items() if req and c not in s["known"]]
        if missing:
            L.append(f"- **липсващи задължителни колони**: {', '.join(missing)}")
            blocking += [f"лист „{s['name']}“: липсва колона „{c}“" for c in missing]
        absent = [c for c in DEPENDS if c not in s["known"]]
        if absent:
            L.append("- проверки, които няма да могат да се направят:")
            L += [f"  - няма „{c}“ → {DEPENDS[c]}" for c in absent]
        if s["unknown"]:
            L.append(f"- неразпознати колони ({len(s['unknown'])}) — опиши ги в "
                     f"`mapping.yaml` (фаза 2) или ги назови при подаването: "
                     + ", ".join(f"„{u}“" for u in s["unknown"][:12])
                     + (" …" if len(s["unknown"]) > 12 else ""))
        if s["name_col"]:
            L.append(f"- колоната с имена е {s['name_col']} — съдържанието ѝ не се "
                     f"възпроизвежда в този доклад")

    L.append("\n## Данни, които ги няма във файла\n")
    for label, value, why in (
            ("КИД на дружеството", data["kid"],
             "без него B3 (МОД) е недостатъчни данни — не се сравнява с чужд бранш"),
            ("квалификационна група", data["group"],
             "МОД се чете по група; редът от приложението към ЗБДОО се подава заедно с КИД"),
            ("ТЗПБ %", data["tzpb"],
             "без него F5 е недостатъчни данни; изведеният от вноските процент се сверява "
             "с приложението към ЗБДОО")):
        L.append(f"- **{label}**: " + (f"`{value}`" if value not in (None, "")
                                       else f"не е подаден — {why}"))

    L.append("\n## Заключение\n")
    if blocking:
        L.append("Одитът **не може** да тръгне, докато не се отстрани:")
        L += [f"- {b}" for b in blocking]
    else:
        L.append("Файлът е годен за одит. Ограниченията по-горе влизат в секцията "
                 "„какво не е проверено“ на отчета.")
    return "\n".join(L) + "\n", blocking


def main(argv=None):
    ap = argparse.ArgumentParser(description="Pre-flight check for a payroll workbook.")
    ap.add_argument("workbook")
    ap.add_argument("--kid", help="КИД code of the company, e.g. 62")
    ap.add_argument("--group", help="qualification group for the МОД row")
    ap.add_argument("--tzpb", help="accident-insurance percentage for the КИД")
    ap.add_argument("--out", help="write the report here instead of stdout")
    a = ap.parse_args(argv)

    if not os.path.exists(a.workbook):
        print(f"няма такъв файл: {a.workbook}", file=sys.stderr)
        return 2
    try:
        data = scan(a.workbook, a.kid, a.group, a.tzpb)
    except Exception as exc:                                  # noqa: BLE001
        print(f"файлът не може да бъде прочетен: {exc}", file=sys.stderr)
        return 2

    text, blocking = report(data)
    if a.out:
        with open(a.out, "w", encoding="utf8") as f:
            f.write(text)
        print(f"докладът е записан в {a.out}")
    else:
        print(text)
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
