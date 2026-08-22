# -*- coding: utf-8 -*-
"""Validates the packaging of the skill and the plugin manifests.

    python test/skill_test.py

What this guards. A skill is distributed as text: a SKILL.md with frontmatter,
reference files loaded on demand, and two JSON manifests that let people install
it with one command. None of that is exercised by the payroll suites, and all of
it breaks silently - a renamed reference file, a version bumped in one manifest
but not the other, a frontmatter field that Claude Code accepts but claude.ai
rejects. This file fails instead.

The frontmatter is deliberately restricted to the fields that travel: `name`,
`description`, `license`, `compatibility`, `metadata` and `allowed-tools` are the
set accepted by Claude Code, by claude.ai skill uploads, by the Skills API and by
the agentskills.io spec. A field outside that set is reported, because it makes
the skill Claude-Code-only for no benefit.
"""
import json
import os
import re
import sys

import yaml

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SKILL_DIR = os.path.join(ROOT, "skills", "trz-expert")
SKILL_MD = os.path.join(SKILL_DIR, "SKILL.md")
PLUGIN = os.path.join(ROOT, ".claude-plugin", "plugin.json")
MARKETPLACE = os.path.join(ROOT, ".claude-plugin", "marketplace.json")

# Fields that survive outside Claude Code. Anything else narrows distribution.
PORTABLE_FIELDS = {"name", "description", "license", "compatibility", "metadata",
                   "allowed-tools"}
DESCRIPTION_CAP = 1536      # description + when_to_use, per the skills reference
COMPATIBILITY_CAP = 500

problems = []
notes = []


def fail(msg):
    problems.append(msg)


def note(msg):
    notes.append(msg)


def read(path):
    with open(path, encoding="utf8") as f:
        return f.read()


# ---------------------------------------------------------------- SKILL.md
if not os.path.exists(SKILL_MD):
    fail(f"{SKILL_MD} is missing")
    print("\n".join(problems))
    sys.exit(1)

text = read(SKILL_MD)
match = re.match(r"---\n(.*?)\n---\n", text, re.S)
if not match:
    fail("SKILL.md has no YAML frontmatter delimited by --- lines")
    frontmatter = {}
else:
    try:
        frontmatter = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as e:
        fail(f"the frontmatter is not valid YAML: {e}")
        frontmatter = {}

extra = set(frontmatter) - PORTABLE_FIELDS
if extra:
    fail(f"frontmatter fields outside the portable set: {sorted(extra)} - they tie "
         f"the skill to Claude Code; the portable set is {sorted(PORTABLE_FIELDS)}")

name = frontmatter.get("name")
directory = os.path.basename(SKILL_DIR)
if name != directory:
    fail(f"frontmatter name {name!r} does not match the directory {directory!r}; "
         f"the directory name is what users type as /{directory}")

description = frontmatter.get("description", "")
if not description.strip():
    fail("description is empty - it is what Claude uses to decide when to load the "
         "skill, so an empty one means the skill never triggers by itself")
combined = len(description) + len(frontmatter.get("when_to_use", ""))
if combined > DESCRIPTION_CAP:
    fail(f"description (+ when_to_use) is {combined} characters, over the "
         f"{DESCRIPTION_CAP} cap - the listing is truncated and the tail is lost")
else:
    note(f"description: {combined}/{DESCRIPTION_CAP} characters")

compatibility = frontmatter.get("compatibility", "")
if len(compatibility) > COMPATIBILITY_CAP:
    fail(f"compatibility is {len(compatibility)} characters, over the "
         f"{COMPATIBILITY_CAP} cap")

if "license" not in frontmatter:
    fail("no license field in the frontmatter - a skill published without one "
         "cannot be reused legally")

if "allowed-tools" in frontmatter:
    note("allowed-tools is set: the skill pre-approves tools. For a public skill "
         "that reads other people's payroll, consider leaving it unset so the "
         "normal permission flow runs.")

# --- referenced files must exist ---------------------------------------------
body = text[match.end():] if match else text
referenced = set(re.findall(r"`(references/[^`]+\.md)`", body))
referenced |= set(re.findall(r"\((references/[^)]+\.md)\)", body))
if not referenced:
    fail("SKILL.md references no file under references/ - progressive disclosure is "
         "the point of the layout, so this is either a broken link or a lost file")
for rel in sorted(referenced):
    if not os.path.exists(os.path.join(SKILL_DIR, rel)):
        fail(f"SKILL.md points at {rel}, which does not exist")

on_disk = {f"references/{f}" for f in sorted(os.listdir(os.path.join(SKILL_DIR, "references")))
           if f.endswith(".md")}
orphans = on_disk - referenced
if orphans:
    fail(f"reference files nothing points at: {sorted(orphans)} - they will never be "
         f"loaded, so either link them from SKILL.md or delete them")

lines = body.count("\n")
note(f"SKILL.md body: {lines} lines, {len(body) // 1000} KB "
     f"(loaded on invocation; the reference files load only when needed)")
if lines > 500:
    note("SKILL.md is over 500 lines - consider moving detail into references/, "
         "which loads on demand instead of on every invocation")

# ------------------------------------------------------------- the manifests
plugin = marketplace = None
for path, label in ((PLUGIN, "plugin.json"), (MARKETPLACE, "marketplace.json")):
    if not os.path.exists(path):
        fail(f".claude-plugin/{label} is missing - without it the skill cannot be "
             f"installed with /plugin, only copied by hand")
        continue
    try:
        data = json.loads(read(path))
    except json.JSONDecodeError as e:
        fail(f"{label} is not valid JSON: {e}")
        continue
    if label == "plugin.json":
        plugin = data
    else:
        marketplace = data

if plugin:
    for field in ("name", "description", "version", "author", "license"):
        if not plugin.get(field):
            fail(f"plugin.json has no {field}")
    if "category" in plugin:
        fail("plugin.json carries `category`, which belongs in marketplace.json and "
             "is ignored here")
    if plugin.get("metadata", {}).get("rates_verified"):
        stated = plugin["metadata"]["rates_verified"]
        rates = read(os.path.join(SKILL_DIR, "references", "stavki.md"))
        m = re.search(r"Последна сверка: \*\*(\d{2})\.(\d{2})\.(\d{4})\*\*", rates)
        if not m:
            fail("cannot find the verification date in references/stavki.md, so the "
                 "date advertised in plugin.json cannot be checked")
        else:
            in_file = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
            if in_file != stated:
                fail(f"plugin.json advertises rates verified {stated} while "
                     f"references/stavki.md says {in_file} - the manifest promises a "
                     f"freshness the reference file does not have")
            else:
                note(f"rates verification date agrees in both places: {in_file}")

if plugin and marketplace:
    entries = marketplace.get("plugins") or []
    if not entries:
        fail("marketplace.json lists no plugins")
    names = [e.get("name") for e in entries]
    if plugin.get("name") not in names:
        fail(f"marketplace.json does not list {plugin.get('name')!r}: {names}")
    for entry in entries:
        if entry.get("name") != plugin.get("name"):
            continue
        if entry.get("version") != plugin.get("version"):
            fail(f"version drift: plugin.json says {plugin.get('version')}, "
                 f"marketplace.json says {entry.get('version')} - users are pinned by "
                 f"whichever is read first, so they must match")
        source = entry.get("source")
        if isinstance(source, str):
            target = os.path.normpath(os.path.join(ROOT, source))
            if not os.path.isdir(target):
                fail(f"marketplace source {source!r} is not a directory")
            elif not os.path.exists(os.path.join(target, ".claude-plugin",
                                                 "plugin.json")):
                fail(f"marketplace source {source!r} has no .claude-plugin/plugin.json")
    if not marketplace.get("description"):
        fail("marketplace.json has no description - users see it when browsing")
    if not (marketplace.get("owner") or {}).get("name"):
        fail("marketplace.json has no owner.name")

# ------------------------------------------------------------------ licences
for path, label in ((os.path.join(ROOT, "LICENSE"), "LICENSE"),
                    (os.path.join(ROOT, "LICENSE-DOCS"), "LICENSE-DOCS")):
    if not os.path.exists(path):
        fail(f"{label} is missing - a public repository without a licence cannot be "
             f"reused legally, whatever the README says")

if plugin and os.path.exists(os.path.join(ROOT, "LICENSE")):
    spdx = plugin.get("license", "")
    for part in re.split(r"\s+(?:AND|OR)\s+", spdx):
        if part and part not in ("MIT", "CC-BY-4.0"):
            fail(f"plugin.json license {part!r} is not one of the licence files "
                 f"present in the repository")

# --------------------------------------------------------------------- report
print("Skill and packaging validation")
print("=" * 78)
for n in notes:
    print(f"  note  {n}")
if problems:
    print()
    for p in problems:
        print(f"  FAIL  {p}")
    print("=" * 78)
    print(f"FAILED: {len(problems)} problem(s)")
    sys.exit(1)
print("=" * 78)
print("OK: frontmatter portable, references linked, manifests consistent, licences present")
