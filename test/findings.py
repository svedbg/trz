# -*- coding: utf-8 -*-
"""The findings ledger both checkers keep score in — one copy, imported by both.

structural_test and pair_test each carried an identical class; a change to how a
finding is recorded then had to be made twice, and the two could drift apart in
silence — the shape of failure this suite exists to catch in payroll files.
"""


class Findings:
    def __init__(self):
        self.items = []
        self._seen = set()

    def add(self, ident, where, text, stated=None, due=None):
        if (where, ident) in self._seen:
            return                     # one finding per (location, kind)
        self._seen.add((where, ident))
        self.items.append(dict(id=ident, where=where, text=text, stated=stated, due=due))

    def keys(self):
        return {(f["where"], f["id"]) for f in self.items}
