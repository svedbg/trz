## What this changes

<!-- One or two sentences. If it changes a rate, say which and from when. -->

## Checklist

- [ ] `python test/run_tests.py` passes (all five suites, 0–4)
- [ ] No real payroll data anywhere — fixtures are generated, not collected
- [ ] If a **rate** changed: the source is cited in `stavki.md` with a status, the
      changelog table has a new line, and `test/rates_test.py` passes
- [ ] If a **check** changed: it has a statutory basis in `normativna-baza.md`, or
      it is a group-K check and says plainly that it rests on arithmetic
- [ ] If a **test scenario** was added: I broke it on purpose once and confirmed
      the suite goes red
- [ ] If the **guidance in SKILL.md** changed: I ran `python test/eval_skill.py`
      (or I am saying here why not — it costs about USD 2.4 per seed)
- [ ] If a **release**: `version` bumped in all three of
      `skills/trz-expert/.claude-plugin/plugin.json`, `skills/trz-expert/plugin.json`
      and `.claude-plugin/marketplace.json`, and the latter copied over
      `.github/plugin/marketplace.json`

## Anything you are unsure about

<!-- Genuinely useful. A stated doubt is worth more than false confidence, and
     the reference files have a status for exactly that reason. -->
