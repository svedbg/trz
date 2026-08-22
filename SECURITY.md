# Security and privacy

## Reporting

Open a [security advisory](https://github.com/svedbg/trz/security/advisories/new)
for anything you would rather not discuss in public. For everything else, a
normal issue is fine.

## What this repository is, in security terms

It ships text, not a service: a skill (markdown), reference files (markdown), and
a Python test suite. There is no server, no network call, no credential, and no
telemetry. The skill instructs Claude to write and run analysis scripts locally;
those scripts are generated per case rather than shipped here.

Two consequences worth knowing.

**The skill pre-approves no tools.** The frontmatter deliberately sets no
`allowed-tools`, so reading your payroll files and running a script both go
through Claude Code's normal permission flow and you see each one. A skill that
reads other people's salary data should not be able to skip that.

**Its findings are advisory.** The skill produces an expert payroll opinion, not
legal advice, and it can be wrong. Do not wire it into anything that pays people
or files declarations without a human reading the report.

## Code scanning

CodeQL runs on every push, over both the Python and the workflow files. Alerts
are not visible to people without access to this repository's security tab, so
any standing dismissal is recorded here instead of only in the GitHub UI.

| Rule | Where | Why it is dismissed |
| --- | --- | --- |
| `py/clear-text-logging-sensitive-data` | `test/structural_test.py:474` and `:476` | Test-only. The taint source is `c["monthly_salary"]` at line 207, which comes from the manifest `generate_wide.py` writes from a seed. `check()` cannot run without that manifest, so every salary printed there is invented. |

Two notes on that dismissal, because it is the kind that ages badly.

It was not silenced by renaming the field. Calling a salary something else to stop
a scanner recognising it is how a real finding gets hidden a year later.

And CodeQL is right about the pattern in general: a payroll audit quotes salary
figures, so any report the skill produces contains them. That is inherent to the
job, and it is why the skill is told to reproduce the minimum needed to justify a
finding and to keep file contents off external services — see below.

An alert of this rule that appears anywhere other than the test harness is a real
finding. Do not extend the dismissal to it.

## Personal data

Payroll files are personal data under the GDPR, and sick-leave records are health
data. The skill is instructed not to send file contents to external services, to
reproduce the minimum needed to justify a finding, and not to write derivative
files outside the working directory you point it at. That is instruction, not
enforcement — you remain the controller.

Nothing in this repository contains real payroll data. Every fixture is invented
and derived from a seed, the company ID in the generated files is `000000000`,
and CI fails the build on any number shaped like a national or company ID. If you
ever find something that looks like real data here, treat it as a security issue
and report it as above.
