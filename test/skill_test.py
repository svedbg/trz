# -*- coding: utf-8 -*-
"""Validates the packaging of the skill and the plugin manifests.

    python test/skill_test.py

What this guards. A skill is distributed as text: a SKILL.md with frontmatter,
reference files loaded on demand, and the JSON manifests that let people install
it with one command - a Claude Code plugin manifest, an Agent Plugins 1.0 manifest
for GitHub Copilot, and a marketplace file that exists at two paths. None of that
is exercised by the payroll suites, and all of it breaks silently - a renamed
reference file, a version bumped in one manifest but not the others, a frontmatter
field that Claude Code accepts but claude.ai rejects. This file fails instead.

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
# The social-preview card quotes the scenario count, which only the test model knows.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trz_model  # noqa: E402  (stdlib only; rates_test.py relies on the same)

SKILL_DIR = os.path.join(ROOT, "skills", "trz-expert")
SKILL_MD = os.path.join(SKILL_DIR, "SKILL.md")
# The plugin root is the skill directory itself, so that installing the plugin
# copies the skill and nothing else - not `test/`, not a local `.venv`.
PLUGIN = os.path.join(SKILL_DIR, ".claude-plugin", "plugin.json")
MARKETPLACE = os.path.join(ROOT, ".claude-plugin", "marketplace.json")
# The same plugin in the Agent Plugins 1.0 shape, which GitHub Copilot and the
# awesome-copilot marketplace gate read; and the same marketplace at the path VS Code
# and Copilot CLI check before `.claude-plugin/`.
AGENT_MANIFEST = os.path.join(SKILL_DIR, "plugin.json")
MARKETPLACE_MIRROR = os.path.join(ROOT, ".github", "plugin", "marketplace.json")

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


def read_bytes(path):
    # For the "byte-identical" copies. Text mode would translate line endings and
    # let a CRLF/LF drift between two copies pass as equal.
    with open(path, "rb") as f:
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
        fail(f"{os.path.relpath(path, ROOT)} is missing - without it the skill cannot "
             f"be installed with /plugin, only copied by hand")
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

    # The install-time question. Claude Code asks it when the plugin is enabled and
    # substitutes the answer into SKILL.md as ${user_config.<key>}. Two ways for that
    # to break without anyone noticing: a key declared and never read (the installer
    # is asked a question whose answer is discarded), and a key read and never
    # declared (the placeholder reaches the user as literal text and the skill acts on
    # a value nobody set). Both are checked here, in both directions.
    TYPES = ("string", "number", "boolean", "directory", "file")
    user_config = plugin.get("userConfig") or {}
    if not user_config:
        fail("plugin.json declares no userConfig - if the install-time question was "
             "removed on purpose, remove the section in SKILL.md that reads its answer")
    for key, spec in user_config.items():
        if not isinstance(spec, dict):
            fail(f"userConfig.{key} is not an object")
            continue
        for field in ("type", "title", "description"):
            if not spec.get(field):
                fail(f"userConfig.{key} has no {field} - the enable dialog shows all "
                     f"three, and a field without them is unanswerable")
        if spec.get("type") not in TYPES:
            fail(f"userConfig.{key} has type {spec.get('type')!r}; Claude Code offers "
                 f"{list(TYPES)}")
        if "default" not in spec:
            fail(f"userConfig.{key} has no default - an installer who dismisses the "
                 f"dialog leaves the skill reading an empty value")
        if spec.get("sensitive"):
            fail(f"userConfig.{key} is marked sensitive, and sensitive values are not "
                 f"substituted into skill content - SKILL.md would never see it")
        if "${user_config.%s}" % key not in text:
            fail(f"userConfig.{key} is declared but SKILL.md never reads "
                 f"${{user_config.{key}}} - the installer is asked and the answer "
                 f"goes nowhere")
    for ref in sorted(set(re.findall(r"\$\{user_config\.([A-Za-z0-9_]+)\}", text))):
        if ref not in user_config:
            fail(f"SKILL.md reads ${{user_config.{ref}}}, which plugin.json does not "
                 f"declare - it reaches the reader as literal text")

    # The default is not only declared, it is *described* - in SKILL.md, in both
    # READMEs and, as its mirror image, in the eval fixture. Flip it in the manifest
    # alone and every test stays green while every other place describes the opposite
    # reading. That is the drift class this file already guards for the verification
    # date, which is why that one is checked in its source plus all eight copies.
    for key, spec in user_config.items():
        if not isinstance(spec, dict) or "default" not in spec:
            continue
        canonical = f"Стойност по подразбиране: `{json.dumps(spec['default'])}`"
        if canonical not in text:
            fail(f"SKILL.md does not carry the line {canonical!r} for "
                 f"userConfig.{key} - without it the manifest default and the skill's "
                 f"own account of it drift apart unnoticed")

    spec = user_config.get("bonus_outside_base")
    if isinstance(spec, dict) and "default" in spec:
        outside = bool(spec["default"])
        for label, path, phrase in (
                ("README.md", os.path.join(ROOT, "README.md"),
                 "The default is **outside**" if outside
                 else "The default is **inside**"),
                ("README.bg.md", os.path.join(ROOT, "README.bg.md"),
                 "По подразбиране е **вън**" if outside
                 else "По подразбиране е **вътре**")):
            # Both READMEs are hard-wrapped, so any phrase can arrive with a
            # newline in the middle of it. Compare on collapsed whitespace.
            if " ".join(phrase.split()) not in " ".join(read(path).split()):
                fail(f"{label} does not say {phrase!r}, but plugin.json declares "
                     f"bonus_outside_base default {spec['default']!r}")
        # The eval pins the fixture to the reading a cloned skill actually applies,
        # which is the mirror of this default. Out of step, it grades the skill
        # against a configuration it does not have.
        pin = f"bonus_in_base={not outside}"
        if pin not in read(os.path.join(ROOT, "test", "eval_skill.py")):
            fail(f"eval_skill.py does not pin its fixture to {pin}, which is what the "
                 f"declared default implies - the eval would grade the skill against "
                 f"the other reading")

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
        # The entry repeats the manifest's author, licence and homepage, and a
        # browser of the marketplace reads the entry, never the manifest. Its
        # `description` and `keywords` are deliberately not compared: the listing
        # carries a shorter description written for browsing and a subset of the
        # keywords, so a difference there is design, not drift.
        for field in ("author", "license", "homepage"):
            if entry.get(field) != plugin.get(field):
                fail(f"marketplace drift: the trz-expert entry's {field} is "
                     f"{entry.get(field)!r}, .claude-plugin/plugin.json says "
                     f"{plugin.get(field)!r} - the listing describes the bundle it "
                     f"installs")
        source = entry.get("source")
        if isinstance(source, str):
            target = os.path.normpath(os.path.join(ROOT, source))
            if not os.path.isdir(target):
                fail(f"marketplace source {source!r} is not a directory")
            elif not os.path.exists(os.path.join(target, ".claude-plugin",
                                                 "plugin.json")):
                fail(f"marketplace source {source!r} has no .claude-plugin/plugin.json")
            elif target != SKILL_DIR:
                # Installing copies the source directory whole, and honours no ignore
                # file. Point it at the repository root and every install carries
                # `test/`, the fixtures and whatever `.venv` the author happened to
                # have - megabytes, to deliver one SKILL.md.
                fail(f"marketplace source {source!r} is not the skill directory - it "
                     f"must be ./skills/trz-expert, or the install ships the whole "
                     f"repository")
    if not marketplace.get("description"):
        fail("marketplace.json has no description - users see it when browsing")
    if not (marketplace.get("owner") or {}).get("name"):
        fail("marketplace.json has no owner.name")

# Copilot CLI looks for the marketplace at `.github/plugin/marketplace.json` before
# `.claude-plugin/`, and VS Code looks only there. One marketplace, two paths: the copy
# is byte-identical, in the manner of LICENSE-DOCS, so there is nothing to keep in step
# by hand - a version bumped in one and not the other would pin Copilot users to the
# old release while Claude Code users move on.
if not os.path.exists(MARKETPLACE_MIRROR):
    fail(".github/plugin/marketplace.json is missing - VS Code finds the marketplace "
         "nowhere else; copy .claude-plugin/marketplace.json there")
elif os.path.exists(MARKETPLACE) and read_bytes(MARKETPLACE_MIRROR) != read_bytes(MARKETPLACE):
    fail(".github/plugin/marketplace.json has drifted from .claude-plugin/marketplace.json "
         "- they are one marketplace at two paths, and Copilot reads the .github copy "
         "(compared byte for byte: a line-ending change counts)")

# ------------------------------------------- the Agent Plugins 1.0 manifest
# Copilot CLI installs the plugin from `.claude-plugin/plugin.json` on its own, but the
# awesome-copilot marketplace gate never looks there: it wants `plugin.json` at the
# plugin root in the Agent Plugins 1.0 shape - `$schema` first and a closed field set,
# so `metadata` and `userConfig` cannot travel in it. The file sits inside the skill
# directory, which keeps the plugin root where it was and the install carrying nothing
# but the skill. Every field it repeats from the Claude manifest is compared here: two
# manifests describing one bundle drift exactly the way two READMEs do.
AGENT_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
AGENT_FIELDS = {"$schema", "name", "version", "description", "author", "homepage",
                "repository", "license", "keywords", "extensions"}
AGENT_AUTHOR_FIELDS = {"name", "email", "url"}
AGENT_NAME = re.compile(r"(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?")
# The external-plugin gate caps the listing description at 500 and accepts only
# lowercase kebab-case keywords, at most ten of at most 30 characters. A submission is
# copied from this file, so the file obeys the gate rather than Copilot's looser 1024.
AGENT_DESCRIPTION_CAP = 500
AGENT_KEYWORD = re.compile(r"[a-z0-9-]{1,30}")

agent = None
if not os.path.exists(AGENT_MANIFEST):
    fail("skills/trz-expert/plugin.json is missing - without it the plugin has no Agent "
         "Plugins manifest, and the awesome-copilot gate reports no manifest at all")
else:
    try:
        agent = json.loads(read(AGENT_MANIFEST))
    except json.JSONDecodeError as e:
        fail(f"skills/trz-expert/plugin.json is not valid JSON: {e}")

if agent is not None and not isinstance(agent, dict):
    fail("skills/trz-expert/plugin.json is not a JSON object")
    agent = None

if agent:
    if agent.get("$schema") != AGENT_SCHEMA:
        fail(f"skills/trz-expert/plugin.json $schema is {agent.get('$schema')!r}; the "
             f"Agent Plugins gate wants exactly {AGENT_SCHEMA!r}, and Copilot reads the "
             f"field to opt into spec semantics")
    extra = set(agent) - AGENT_FIELDS
    if extra:
        fail(f"skills/trz-expert/plugin.json carries {sorted(extra)}, which the Agent "
             f"Plugins 1.0 schema does not allow - it closes the field set, so a validator "
             f"rejects the file. `metadata` and `userConfig` live in "
             f".claude-plugin/plugin.json only")
    for field in ("name", "version", "description"):
        if not isinstance(agent.get(field), str) or not agent[field].strip():
            fail(f"skills/trz-expert/plugin.json has no {field}")

    agent_name = agent.get("name")
    if isinstance(agent_name, str) and (len(agent_name) > 64
                                        or not AGENT_NAME.fullmatch(agent_name)):
        fail(f"skills/trz-expert/plugin.json name {agent_name!r} breaks the Agent Plugins "
             f"pattern: 1-64 characters of lowercase letters, digits, dots and hyphens, "
             f"no leading or trailing separator, no `--` or `..`")

    agent_description = agent.get("description")
    if isinstance(agent_description, str) and len(agent_description) > AGENT_DESCRIPTION_CAP:
        fail(f"skills/trz-expert/plugin.json description is {len(agent_description)} "
             f"characters; the marketplace listing caps it at {AGENT_DESCRIPTION_CAP}")

    author = agent.get("author")
    if not isinstance(author, dict) or not author.get("name"):
        fail("skills/trz-expert/plugin.json has no author.name - the external-plugin gate "
             "requires it")
    elif set(author) - AGENT_AUTHOR_FIELDS:
        fail(f"skills/trz-expert/plugin.json author carries "
             f"{sorted(set(author) - AGENT_AUTHOR_FIELDS)}; the schema allows only "
             f"{sorted(AGENT_AUTHOR_FIELDS)}")

    for field in ("repository", "homepage"):
        value = agent.get(field)
        if value is not None and not str(value).startswith("https://github.com/"):
            fail(f"skills/trz-expert/plugin.json {field} {value!r} is not an https "
                 f"github.com URL, which is what the external-plugin gate accepts")
    if "repository" not in agent:
        fail("skills/trz-expert/plugin.json has no repository - the external-plugin gate "
             "requires it")

    keywords = agent.get("keywords")
    if not isinstance(keywords, list) or not keywords:
        fail("skills/trz-expert/plugin.json has no keywords - the external-plugin gate "
             "requires at least one")
    else:
        if len(keywords) > 10:
            fail(f"skills/trz-expert/plugin.json lists {len(keywords)} keywords; the gate "
                 f"allows ten")
        bad = [k for k in keywords if not isinstance(k, str) or not AGENT_KEYWORD.fullmatch(k)]
        if bad:
            fail(f"skills/trz-expert/plugin.json keywords {bad} are not lowercase "
                 f"kebab-case ASCII of at most 30 characters - the gate rejects them; "
                 f"Cyrillic keywords belong in .claude-plugin/plugin.json")

    if plugin:
        for field in ("name", "version", "description", "author", "homepage",
                      "repository", "license"):
            if agent.get(field) != plugin.get(field):
                fail(f"manifest drift: skills/trz-expert/plugin.json {field} is "
                     f"{agent.get(field)!r}, .claude-plugin/plugin.json says "
                     f"{plugin.get(field)!r} - they describe the same bundle, and "
                     f"Copilot users are pinned by the first, Claude Code users by "
                     f"the second")

# ----------------------------------------------- metadata shared with SKILL.md
# The Claude manifest and the SKILL.md frontmatter both carry a `metadata` block
# describing the same skill. `jurisdiction` and `language` are the same fact stated
# twice, under the same key, and the key is `language` in both - the manifest's
# documented name. The frontmatter once said `reference_language`, and nothing
# compared them.
if plugin:
    skill_meta = frontmatter.get("metadata") or {}
    plugin_meta = plugin.get("metadata") or {}
    for key in ("jurisdiction", "language"):
        if skill_meta.get(key) != plugin_meta.get(key):
            fail(f"metadata drift: SKILL.md frontmatter metadata.{key} is "
                 f"{skill_meta.get(key)!r}, .claude-plugin/plugin.json metadata.{key} "
                 f"is {plugin_meta.get(key)!r} - one fact under one key in both")

# ------------------------------------- the rates-verification date, everywhere
# `references/stavki.md` is the source of truth for the date, and eight copies of it
# are advertised elsewhere: two manifest/frontmatter fields, the compatibility line, a
# badge and a sentence in each README, and the social-preview image every visitor to
# the repository page sees. A copy that is not updated with the reference file
# promises a freshness the rates do not have. The social preview was added after it
# was found two updates behind - the check before it did not know about that copy.
# DATE_COPIES below is the count the messages quote; it is asserted against the list,
# so adding a copy here without changing the wording is caught.
DATE_COPIES = 8
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July",
             "August", "September", "October", "November", "December"]
MONTHS_BG = ["януари", "февруари", "март", "април", "май", "юни", "юли",
             "август", "септември", "октомври", "ноември", "декември"]

rates_text = read(os.path.join(SKILL_DIR, "references", "stavki.md"))
verified = re.search(r"Последна сверка на ставките: \*\*(\d{2})\.(\d{2})\.(\d{4})\*\*",
                     rates_text)
if not verified:
    fail("cannot find „Последна сверка на ставките: **dd.mm.yyyy**“ in "
         "references/stavki.md - it is "
         "the source of truth for the verification date, so none of the places that "
         "advertise it can be checked")
else:
    day, month, year = verified.group(1), verified.group(2), verified.group(3)
    iso, dotted = f"{year}-{month}-{day}", f"{day}.{month}.{year}"
    stale = []
    copies = 0

    for label, stated in (
            ("plugin.json metadata.rates_verified",
             (plugin or {}).get("metadata", {}).get("rates_verified")),
            ("SKILL.md frontmatter metadata.rates_verified",
             (frontmatter.get("metadata") or {}).get("rates_verified"))):
        copies += 1
        if stated is None:
            note(f"{label} is not set - nothing to keep in step")
        elif str(stated) != iso:
            stale.append(f"{label} says {stated}, references/stavki.md says {iso}")

    # The compatibility line is a frontmatter field, so it is read from the parsed
    # frontmatter rather than grepped out of the whole file - a grep over SKILL.md
    # would be satisfied by the date appearing anywhere in the body.
    copies += 1
    if dotted not in str(compatibility):
        stale.append(f"SKILL.md frontmatter compatibility does not carry {dotted}")

    # The prose copies. Each is matched in the exact shape it is written in, so that a
    # half-edit - badge updated, sentence forgotten - is still caught.
    for label, path, pattern in (
            ("README.md badge", os.path.join(ROOT, "README.md"),
             rf"rates%20verified-{year}--{month}--{day}-"),
            ("README.md body", os.path.join(ROOT, "README.md"),
             rf"\b{int(day)} {MONTHS_EN[int(month) - 1]} {year}\b"),
            ("README.bg.md badge", os.path.join(ROOT, "README.bg.md"),
             rf"-{year}--{month}--{day}-"),
            ("README.bg.md body", os.path.join(ROOT, "README.bg.md"),
             rf"\b{int(day)} {MONTHS_BG[int(month) - 1]} {year}"),
            (".github/social-preview.html", os.path.join(ROOT, ".github",
                                                         "social-preview.html"),
             rf"ставки: {re.escape(dotted)}")):
        copies += 1
        if not os.path.exists(path):
            fail(f"{path} is missing, so {label} cannot be checked")
        elif not re.search(pattern, read(path)):
            stale.append(f"{label} does not carry {dotted}")

    if copies != DATE_COPIES:
        fail(f"this file checks {copies} copies of the verification date but its "
             f"messages, CLAUDE.md and the pre-commit hook say {DATE_COPIES} - update "
             f"DATE_COPIES and the prose together")
    if stale:
        for s in stale:
            fail(f"rates-verification date out of step: {s}")
        fail(f"the date lives in references/stavki.md plus {DATE_COPIES} copies and they "
             f"must move together; the reference file is the one that leads")
    else:
        note(f"rates verification date {dotted} agrees in the source plus all "
             f"{DATE_COPIES} copies")

# ------------------------------------------------- the social-preview figures
# The card GitHub shows when the repository link is shared quotes three numbers: how
# many checks the skill runs, how many defect scenarios the generated suite injects,
# and how many injected defects the scenario suite found at 3000 seeds. Each is a
# claim about something that moves. The check count is read from
# references/proverki.md, the scenario count from the test model, and the defect
# total from the README - which is the only place the 3000-seed run is recorded, since
# it is far too expensive to repeat here; the card copies the README's figure, it does
# not recompute one. The two READMEs must also agree with each other on all three
# per-suite figures.
SOCIAL_PREVIEW = os.path.join(ROOT, ".github", "social-preview.html")
CARD_FACT = re.compile(r'<div class="n">([^<]*)</div>\s*<div class="l">([^<]*)</div>')
CHECK_BULLET = re.compile(r"^- \*\*[A-K]\d+\.", re.M)
# "the three generated suites at 3000 seeds: N injected defects in suite 2,
# N in suite 3 and N in suite 4" - hard-wrapped, so matched on collapsed
# whitespace. The card carries the first figure: suite 2 is the one the scenarios
# counted next to it on the card feed.
README_TOTALS = (
    ("README.md", r"3000 seeds: ([\d ]+?) injected defects in suite 2, ([\d ]+?) in "
                  r"suite 3 and ([\d ]+?) in suite 4"),
    ("README.bg.md", r"3000 семена: ([\d ]+?) вкарани дефекта в комплект 2, ([\d ]+?) "
                     r"в комплект 3 и ([\d ]+?) в комплект 4"),
)


def digits(s):
    return int(re.sub(r"\D", "", s))


def grouped(n):
    # 41518 -> "41 518", the way the card and the READMEs write it.
    return f"{n:,}".replace(",", " ")


if not os.path.exists(SOCIAL_PREVIEW):
    fail(".github/social-preview.html is missing - the card's figures cannot be checked")
else:
    facts = {}
    for number, label in CARD_FACT.findall(read(SOCIAL_PREVIEW)):
        facts[label.split()[0]] = number.strip()
    for key in ("проверки", "сценария", "дефекта"):
        if key not in facts:
            fail(f".github/social-preview.html shows no „{key}“ figure - the card's "
                 f"layout changed, so update CARD_FACT and the labels this test expects")

    check_count = len(CHECK_BULLET.findall(read(os.path.join(SKILL_DIR, "references",
                                                             "proverki.md"))))
    if "проверки" in facts and digits(facts["проверки"]) != check_count:
        fail(f".github/social-preview.html claims {facts['проверки']} checks; "
             f"references/proverki.md lists {check_count} `- **X1.` bullets")

    scenario_count = len(trz_model.SCENARIOS)
    if "сценария" in facts and digits(facts["сценария"]) != scenario_count:
        fail(f".github/social-preview.html claims {facts['сценария']} scenarios; "
             f"trz_model.SCENARIOS has {scenario_count}")

    totals = {}
    for label, pattern in README_TOTALS:
        m = re.search(pattern, " ".join(read(os.path.join(ROOT, label)).split()))
        if not m:
            fail(f"{label} no longer states the per-suite defect counts at 3000 seeds in "
                 f"the shape this test reads - the card's defect total cannot be checked")
        else:
            totals[label] = tuple(digits(g) for g in m.groups())
    if len(totals) == 2 and totals["README.md"] != totals["README.bg.md"]:
        fail(f"the READMEs disagree on the 3000-seed defect counts: README.md says "
             f"{totals['README.md']}, README.bg.md says {totals['README.bg.md']}")
    if "дефекта" in facts and "README.md" in totals:
        expected = totals["README.md"][0]
        if digits(facts["дефекта"]) != expected:
            fail(f".github/social-preview.html claims {facts['дефекта']} defects; the "
                 f"README states {grouped(expected)} for suite 2 at 3000 seeds, and the "
                 f"card copies the README")
    if facts and len(totals) == 2:
        note(f"social preview: {check_count} checks, {scenario_count} scenarios, "
             f"{grouped(totals['README.md'][0])} defects - all agree with their sources")

# ------------------------------------------------------ the Codex CLI pointer
# Codex CLI auto-discovers a repository skill at .agents/skills/<name>/SKILL.md - no
# manifest, no install step, just that file's presence. Unlike a Claude Code plugin
# (copied elsewhere before it runs), Codex reads the live repository, so the pointer
# below tells it to go read the canonical skill instead of carrying a second copy that
# could drift from it silently.
CODEX_DIR = os.path.join(ROOT, ".agents", "skills", "trz-expert")
CODEX_SKILL_MD = os.path.join(CODEX_DIR, "SKILL.md")
if not os.path.exists(CODEX_SKILL_MD):
    fail(f"{CODEX_SKILL_MD} is missing - Codex CLI's repository-skill discovery finds "
         f"nothing there")
else:
    codex_text = read(CODEX_SKILL_MD)
    codex_match = re.match(r"---\n(.*?)\n---\n", codex_text, re.S)
    if not codex_match:
        fail(f"{CODEX_SKILL_MD} has no YAML frontmatter delimited by --- lines")
        codex_frontmatter = {}
    else:
        try:
            codex_frontmatter = yaml.safe_load(codex_match.group(1)) or {}
        except yaml.YAMLError as e:
            fail(f"the Codex pointer's frontmatter is not valid YAML: {e}")
            codex_frontmatter = {}
    codex_name = codex_frontmatter.get("name")
    codex_directory = os.path.basename(CODEX_DIR)
    if codex_name != codex_directory:
        fail(f"Codex pointer frontmatter name {codex_name!r} does not match its "
             f"directory {codex_directory!r}")
    # The two descriptions are the same trigger, kept as one string by hand; a change
    # to one that misses the other silently un-syncs when Codex decides to load the
    # skill from when Claude Code does.
    if codex_frontmatter.get("description") != description:
        fail("the Codex pointer's description has drifted from skills/trz-expert/"
             "SKILL.md's - they are the same trigger for two readers of the same skill")
    # The paths the pointer sends Codex to read. Named literally, not derived, so a
    # rename of any of the four files breaks this the moment the pointer is not
    # updated in the same commit - exactly the silent drift this file exists to catch.
    for rel in ("skills/trz-expert/SKILL.md", "skills/trz-expert/references/stavki.md",
               "skills/trz-expert/references/proverki.md",
               "skills/trz-expert/references/normativna-baza.md"):
        if rel not in codex_text:
            fail(f"the Codex pointer no longer names {rel} - Codex would not be told "
                 f"to read it")

# ------------------------------------------------------------------ licences
# The repository is dual-licensed - CC BY 4.0 for the skill prose, MIT for the Python
# under `test/` - but only the skill directory is published as the plugin. So the
# repository needs both licence files and the bundle needs the one that covers what it
# actually carries, travelling *with* it: an install never sees the repository root.
for path, label in ((os.path.join(ROOT, "LICENSE"), "LICENSE"),
                    (os.path.join(ROOT, "LICENSE-DOCS"), "LICENSE-DOCS")):
    if not os.path.exists(path):
        fail(f"{label} is missing - a public repository without a licence cannot be "
             f"reused legally, whatever the README says")

BUNDLED_LICENCE = os.path.join(SKILL_DIR, "LICENSE-DOCS")
if not os.path.exists(BUNDLED_LICENCE):
    fail("skills/trz-expert/LICENSE-DOCS is missing - the skill directory is what gets "
         "installed, and CC BY 4.0 requires its terms to travel with the text")
elif os.path.exists(os.path.join(ROOT, "LICENSE-DOCS")):
    if read_bytes(BUNDLED_LICENCE) != read_bytes(os.path.join(ROOT, "LICENSE-DOCS")):
        fail("skills/trz-expert/LICENSE-DOCS has drifted from the root LICENSE-DOCS - "
             "they are one licence, and installed users only ever read the copy "
             "(compared byte for byte: a line-ending change counts)")

if plugin:
    # Only what the bundle carries may be declared. `MIT AND CC-BY-4.0` was right when
    # the whole repository was the plugin; now no MIT-licensed file ships.
    spdx = plugin.get("license", "")
    for part in re.split(r"\s+(?:AND|OR)\s+", spdx):
        if part and part != "CC-BY-4.0":
            fail(f"plugin.json license {part!r} covers nothing the installed plugin "
                 f"contains - the bundle is the skill directory, which is CC BY 4.0")
    if spdx != frontmatter.get("license"):
        fail(f"licence drift: plugin.json says {spdx!r}, SKILL.md frontmatter says "
             f"{frontmatter.get('license')!r} - they describe the same files")

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
