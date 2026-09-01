# Contributing

Bulgarian is welcome in issues and pull requests. The code and these guides are
in English so that people who do not read Bulgarian can still review them.

## The one rule that matters

**Never add a rate from memory.** Not a minimum wage, not a contribution
percentage, not a threshold. This repository exists because a payroll report that
confidently applies last year's figure is worse than no report: it reads as
authoritative and it is wrong.

Every figure in
[`skills/trz-expert/references/stavki.md`](skills/trz-expert/references/stavki.md)
carries a status:

| Status | Means |
| --- | --- |
| `ДВ` | verified against the statutory text, with the State Gazette issue cited |
| `официален` | from a state authority's site, not cross-checked against the Gazette |
| `вторичен` | from a professional accounting source; usable, verify if disputed |
| `за потвърждение` | working hypothesis. **Cannot support a `нарушение` finding.** |
| empty | missing. The skill asks the user instead of guessing. |

To add or change a rate:

1. Find the primary source. State Gazette issue and date if you have it.
2. Add or edit the row in `stavki.md` with its status.
3. Add a line to the changelog table at the bottom of the file, with the date and
   what you verified.
4. If a test needs the figure, update `test/trz_model.py` to match. The reference
   file is the source of truth; the model follows it, never the other way round.
5. Run `python test/rates_test.py`. It cross-checks 26 figures between the two
   and fails on any drift.

If you are downgrading a rate's status — because a source turned out weaker than
it looked — say so in the changelog. That is as valuable as adding one.

## Adding a check

Checks live in
[`references/proverki.md`](skills/trz-expert/references/proverki.md), grouped
A–K. A check needs three things:

* a statement of what passes and what does not;
* a statutory basis in
  [`references/normativna-baza.md`](skills/trz-expert/references/normativna-baza.md) —
  **except** group K, which rests on arithmetic and must say so rather than
  invent an article;
* a formula, if the check computes anything, in the formulas section.

If a check depends on a contested reading, write it as the skill is told to
behave: enumerate the possible readings, say what follows from each in money, and
have it ask. Do not pick one and present it as settled.

## Adding a test scenario

The structural suite injects a defect and requires it to be found exactly once.
To add one:

1. Write a mutation in `test/generate_wide.py`: take a clean row, break one
   thing, recompute the dependent cells the way a wrong file would. Return the
   row and the set of expected finding ids.
2. Register it in `SCENARIOS` in `test/trz_model.py` and in `ROW_MUTATIONS`.
3. Implement the detection in `test/structural_test.py`.
4. Document it in [`test/scenarios.md`](test/scenarios.md).
5. If the skill should also find it, add keyword patterns to `KEYWORDS` in
   `test/eval_skill.py`.
6. Run `python test/run_tests.py --seeds 300`. A run passes only when every
   injected defect is found and **no** finding is raised beyond them. False
   positives fail the suite like misses.

Prove the check has teeth: break something on purpose and confirm the suite goes
red. A check that has never failed has not been tested.

## Running the tests

```sh
python3 -m venv .venv && .venv/bin/pip install -r test/requirements.txt
git config core.hooksPath .githooks     # once

python test/run_tests.py                # all five suites, 50 seeds
python test/rates_test.py               # rates only, no dependencies
python test/skill_test.py               # packaging: frontmatter, manifests, licences
python test/eval_skill.py --dry         # what the skill eval would send, free
```

What runs when:

| Trigger | Runs |
| --- | --- |
| every commit (hook) | the rates cross-check |
| commit touching `test/*.py` | plus the payroll and formula suites, 25 seeds |
| push and pull request (CI) | packaging, leak guard, both suites at 300 seeds on Python 3.10–3.13 |
| by hand | `eval_skill.py` — it calls Claude and costs about USD 2.4 per seed |

`eval_skill.py` is the only test that exercises the skill rather than the rules.
Run it when you change the guidance in `SKILL.md`, because nothing else will
notice.

## Never commit real payroll data

Payrolls are personal data under the GDPR, and sick-leave records are health
data. Every fixture in this repository is invented and derived from a seed. CI
greps for numbers shaped like a national ID or a company ID and fails the build.

If you need a realistic case, generate one:

```sh
python test/generate_wide.py --seed 12345
```

## How a change lands

`main` is protected by a ruleset, so nobody pushes to it directly — not outside
contributors and not the maintainer. Every change goes through a pull request,
and the pull request cannot merge until CI is green: the packaging check, the
personal-data guard, and the payroll and formula suites on Python 3.10 through 3.13.

Approvals are not required, so a solo maintainer is not deadlocked, but the
status checks are. Linear history is enforced, so rebase rather than merge when
your branch falls behind:

```sh
git fetch origin && git rebase origin/main
```

Force-pushing to `main` and deleting it are blocked outright, as is rewriting a
`v*` release tag. Those are the rules that exist so that a bad afternoon cannot
lose history.

## Releasing

Bump `version` in **both** `skills/trz-expert/.claude-plugin/plugin.json` and
`.claude-plugin/marketplace.json` — users are pinned by it, and `skill_test.py`
fails if the two drift. If the rates changed, update `metadata.rates_verified` in
`plugin.json` to match the verification date in `stavki.md`; the same test checks
that too.

The plugin manifest lives inside the skill directory because that directory *is*
the plugin: `marketplace.json` points `source` at `./skills/trz-expert`, and an
install copies that directory whole — no ignore file is honoured, so a `source`
of `.` would hand every user `test/`, the fixtures and any local `.venv`. That is
also why `LICENSE-DOCS` is duplicated into the skill directory: an installed user
never sees the repository root, and CC BY 4.0 asks for its terms to travel with
the text. `skill_test.py` fails if the copy drifts from the root one.
