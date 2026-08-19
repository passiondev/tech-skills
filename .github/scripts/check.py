#!/usr/bin/env python3
"""Everything CI enforces. Run it locally before opening a pull request:

    python3 .github/scripts/check.py

There are no versions and no staging here, so review is the only safety
mechanism this project has (ADR 0010). These checks cover the failures a
reviewer cannot reliably catch by reading: a dependency that no longer
resolves, a hostname pasted into an example, three copies of a file drifting
apart. Everything else is the curator's job.

Exit 0 if clean, 1 otherwise. Every failure names the file and what to do.
"""

import ast
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "plugins"
SELF = Path(__file__).resolve().relative_to(ROOT)

failures = []
checks_run = 0


def fail(where, message):
    line = f"{where}: {message}"
    if line not in failures:  # the same manifest is read by several checks
        failures.append(line)


def check(name):
    """Decorator that runs a check and turns an unexpected crash into a failure."""
    def wrap(fn):
        global checks_run
        checks_run += 1
        try:
            fn()
        except Exception as exc:  # a check that cannot run is a failure
            fail(name, f"check itself failed: {type(exc).__name__}: {exc}")
        return fn
    return wrap


def load_json(path):
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        fail(path.relative_to(ROOT), f"is not valid JSON — {exc}")
        return None


def repo_files(under="", suffixes=None):
    """Every file this repository ships, under a prefix, as absolute paths.

    Asked of git rather than of the filesystem. A walk finds whatever the last
    command left lying about — `__pycache__` from a test run, a binary ruff
    cache whose files have no extension at all, a virtualenv full of somebody
    else's Python — and then every check that walks has to name each of those to
    skip it. None of them did. `secrets` was reading nine cache blobs looking
    for hostnames, and excluding itself by comparing a hardcoded path.

    What a public repository ships is what git tracks, and git already knows
    about the caches, because they carry their own ignore files. `under` is a
    literal prefix, so pass the trailing slash: "plugins/".

    A path in the index that is not on disk is dropped rather than returned. A
    file deleted but not yet staged is exactly that, and every caller here opens
    what it is given -- so returning the path would turn an ordinary moment
    mid-edit into a check that crashes instead of reporting.
    """
    listing = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"],
                             capture_output=True, text=True, check=False)
    if listing.returncode != 0:
        raise RuntimeError(f"git ls-files failed in {ROOT}: "
                           f"{listing.stderr.strip()[:200]}")
    return sorted(ROOT / rel for rel in listing.stdout.split("\0")
                  if rel and rel.startswith(under)
                  and (suffixes is None or Path(rel).suffix in suffixes)
                  and (ROOT / rel).is_file())


# ─────────────────────────────────────────────────────────────────────────────
# Manifests, sources, and the dependency graph
# ─────────────────────────────────────────────────────────────────────────────

MARKETPLACE = load_json(ROOT / ".claude-plugin" / "marketplace.json")
LISTED = {e["name"]: e for e in MARKETPLACE["plugins"]} if MARKETPLACE else {}


@check("marketplace")
def _manifests():
    if not MARKETPLACE:
        return
    for entry in MARKETPLACE["plugins"]:
        name = entry["name"]
        if " " in name:
            fail(name, "plugin names cannot contain spaces — use kebab-case")

        src = entry.get("source")
        if not isinstance(src, str) or not src.startswith("./"):
            fail(name, f"source should be a relative path like ./plugins/{name}, got {src!r}")
            continue
        if not (ROOT / src).is_dir():
            fail(name, f"source path does not exist: {src}")
            continue

        manifest = ROOT / src / ".claude-plugin" / "plugin.json"
        if not manifest.is_file():
            fail(name, f"no plugin.json at {manifest.relative_to(ROOT)}")
            continue
        pj = load_json(manifest)
        if pj is None:
            continue
        if pj.get("name") != name:
            fail(name, f"plugin.json says name={pj.get('name')!r}, marketplace says {name!r}")
        if not pj.get("description"):
            fail(name, "plugin.json has no description — it is what people see when browsing")


@check("dependencies")
def _dependencies():
    for name in LISTED:
        pj = load_json(PLUGINS / name / ".claude-plugin" / "plugin.json")
        if pj is None:
            continue
        for dep in pj.get("dependencies", []):
            if dep not in LISTED:
                fail(name, f'depends on "{dep}", which the marketplace does not list — '
                           "catalog may be stale")

    # Cycles would make an install order impossible.
    def walk(node, seen):
        if node in seen:
            fail("dependencies", f"cycle: {' -> '.join(seen + [node])}")
            return
        pj = load_json(PLUGINS / node / ".claude-plugin" / "plugin.json") or {}
        for dep in pj.get("dependencies", []):
            if dep in LISTED:
                walk(dep, seen + [node])

    for name in LISTED:
        walk(name, [])


@check("departments")
def _departments():
    """A department bundle is dependencies and nothing else (ADR 0002)."""
    for name, entry in LISTED.items():
        if entry.get("category") != "department":
            continue
        pj = load_json(PLUGINS / name / ".claude-plugin" / "plugin.json") or {}
        if not pj.get("dependencies"):
            fail(name, "is a department bundle with no dependencies")
        if list((PLUGINS / name).glob("skills/*/SKILL.md")):
            fail(name, "is a department bundle but contains skills — bundles hold only dependencies")
        if (PLUGINS / name / "runtime").exists():
            fail(name, "is a department bundle but has a runtime")

    orphans = set(LISTED) - {"jira"}
    for name in LISTED:
        pj = load_json(PLUGINS / name / ".claude-plugin" / "plugin.json") or {}
        orphans -= set(pj.get("dependencies", []))
    orphans = {n for n in orphans if LISTED[n].get("category") != "department"}
    if orphans:
        fail("departments", f"capability plugins no department installs: {sorted(orphans)}")


# ─────────────────────────────────────────────────────────────────────────────
# Skills
# ─────────────────────────────────────────────────────────────────────────────

SKILLS = sorted(PLUGINS.glob("*/skills/*/SKILL.md"))
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def frontmatter(path):
    m = FRONTMATTER.match(path.read_text())
    if not m:
        return None
    # Deliberately not PyYAML: CI should not need a dependency to run.
    # Only `name:` is parsed strictly; folded scalars are handled by the
    # description check below rather than here.
    out = {}
    for line in m.group(1).splitlines():
        if re.match(r"^\w[\w-]*:", line):
            key, _, val = line.partition(":")
            out[key.strip()] = val.strip()
    return out


@check("skills")
def _skills():
    for path in SKILLS:
        rel = path.relative_to(ROOT)
        plugin, skill = path.parts[-4], path.parts[-2]
        fm = frontmatter(path)
        if fm is None:
            fail(rel, "has no YAML frontmatter")
            continue
        if fm.get("name") != skill:
            fail(rel, f'frontmatter name is {fm.get("name")!r} but the directory is {skill!r} — '
                      "they must match, the directory is what gets invoked")
        desc = fm.get("description", "")
        if not desc:
            fail(rel, "has no description — Claude cannot route to it")
        elif desc in (">", "|", ">-", "|-"):
            pass  # folded scalar; the body is on following lines
        elif len(desc) < 40:
            fail(rel, f"description is {len(desc)} characters — too thin to route on")
        if plugin not in LISTED:
            fail(rel, f"lives under plugins/{plugin}, which the marketplace does not list")


SKILL_PLUGIN = {p.parts[-2]: p.parts[-4] for p in SKILLS}

# A skill body naming another skill is a promise. Two ways it breaks here that
# it never broke upstream, where every skill sat in one flat directory:
#
#   1. Upstream writes `/tdd`. In a marketplace the command is `/dev:tdd` —
#      the bare form names nothing.
#   2. Departments install different plugins (ADR 0008), so `/plan:x` cited
#      from a `dev` skill is a dead pointer for Analytics, who ship `dev`
#      without `plan`.
#
# These are cited on purpose across a boundary some department does not have,
# and each sentence says so. Adding a fifth should be a decision, not a habit —
# soften the prose and add it here, or make the reference reachable.
OPTIONAL_REFS = {
    ("plugins/general/skills/grill-with-docs/SKILL.md", "domain-modeling"):
        "grilling works without the documents; the sentence names the department",
    ("plugins/plan/skills/wayfinder/SKILL.md", "prototype"):
        "one of five listed tactics; qualified with 'where dev is installed'",
}

# A catalogue names skills the reader may not have — that is the job, not a bug.
# `onboard` picks from the whole marketplace by what the person actually does,
# after checking `claude plugin list`, and says outright not to teach a skill
# their department lacks. The reachability rule is waived here; the spelling
# rules below are not.
CATALOGUE_FILES = {
    "plugins/general/skills/onboard/SKILL.md":
        "recommends across every plugin, after verifying what is installed",
}

SLASH_REF = re.compile(r"(?<![\w/:])/([a-z][a-z0-9-]{2,})(:([a-z][a-z0-9-]{2,}))?\b(?!/)")


@check("cross-references")
def _cross_references():
    departments = {}
    for name, entry in LISTED.items():
        if entry.get("category") != "department":
            continue
        seen = set()

        def walk(node):
            if node in seen:
                return
            seen.add(node)
            pj = load_json(PLUGINS / node / ".claude-plugin" / "plugin.json") or {}
            for dep in pj.get("dependencies", []):
                if dep in LISTED:
                    walk(dep)

        walk(name)
        departments[name] = seen

    for doc in sorted(PLUGINS.rglob("*.md")):
        rel = doc.relative_to(ROOT).as_posix()
        owner = doc.relative_to(PLUGINS).parts[0]
        for m in SLASH_REF.finditer(doc.read_text()):
            first, skill = m.group(1), m.group(3)
            if skill is None:
                if first in SKILL_PLUGIN:
                    fail(rel, f"writes `/{first}` — skills are invoked `/plugin:skill`, "
                              f"so this should be `/{SKILL_PLUGIN[first]}:{first}`")
                continue
            if skill not in SKILL_PLUGIN:
                fail(rel, f"references `/{first}:{skill}`, which is not a skill in this marketplace")
                continue
            if SKILL_PLUGIN[skill] != first:
                fail(rel, f"references `/{first}:{skill}` but {skill} lives in "
                          f"`{SKILL_PLUGIN[skill]}` — should be `/{SKILL_PLUGIN[skill]}:{skill}`")
                continue
            if (rel, skill) in OPTIONAL_REFS or rel in CATALOGUE_FILES:
                continue
            unreachable = sorted(d for d, closure in departments.items()
                                 if owner in closure and first not in closure)
            if unreachable:
                fail(rel, f"references `/{first}:{skill}`, but {', '.join(unreachable)} "
                          f"install `{owner}` without `{first}` — make the sentence say the "
                          "reference is conditional and add it to OPTIONAL_REFS, or drop it")

    for rel, why in CATALOGUE_FILES.items():
        if not (ROOT / rel).is_file():
            fail("cross-references", f"CATALOGUE_FILES names {rel} ({why}), which does not exist")

    # An exception list only stays honest if entries expire. Two ways one dies:
    # the reference goes away, or a dependency change makes it reachable after
    # all — the second is what happened when Analytics gained `plan`.
    for (rel, skill), why in OPTIONAL_REFS.items():
        path = ROOT / rel
        if not path.is_file() or f":{skill}`" not in path.read_text():
            fail("cross-references", f"OPTIONAL_REFS still excuses {rel} -> {skill} ({why}), "
                                     "but that reference is gone — delete the entry")
            continue
        owner, target = path.relative_to(PLUGINS).parts[0], SKILL_PLUGIN[skill]
        if not any(owner in c and target not in c for c in departments.values()):
            fail("cross-references", f"OPTIONAL_REFS excuses {rel} -> {skill} ({why}), but "
                                     f"every department with `{owner}` now installs `{target}` "
                                     "— delete the entry and drop the caveat from the prose")


# `disable-model-invocation: true` hides a skill from the model, and the model
# is what runs other skills — so the flag hides it from them too. "Run
# `/plan:to-spec`" inside a skill body is therefore an instruction the agent
# cannot carry out: a dead handoff. `cross-references` cannot see it, because a
# dead handoff is spelled correctly and points somewhere reachable.
#
# The rule is not "never name a user-invoked skill" — catalogues, boundary
# statements, and definitional citations all name them legitimately. It is
# "do not tell the agent to run one". Name the human as the runner instead.
USER_INVOKED = {}
for _path in SKILLS:
    _fm = FRONTMATTER.match(_path.read_text())
    if _fm and re.search(r"^disable-model-invocation:\s*true\s*$", _fm.group(1), re.M):
        USER_INVOKED[_path.parts[-2]] = _path.parts[-4]

INVOKE_VERB = re.compile(r"(?i)\b(run|invoke|call|launch|trigger|hands? off to|"
                         r"hand off to|handing off to|delegate to|defer to|use)\b")
HUMAN_RUNNER = re.compile(r"(?i)(user-invoked|the user (?:can |should |must )?runs?|"
                          r"let the user|tell (?:the user|them)|ask the user|recommend|"
                          r"they run|you run|typed? by hand|the person runs|not have)")

# Same shape and same discipline as OPTIONAL_REFS: an entry must name why the
# sentence is safe, and it expires when the sentence changes.
INVOCABLE_REFS = {}


@check("invocability")
def _invocability():
    for doc in sorted(PLUGINS.rglob("*.md")):
        rel = doc.relative_to(ROOT).as_posix()
        parts = doc.relative_to(PLUGINS).parts
        owner = parts[2] if len(parts) > 3 and parts[1] == "skills" else None
        text = doc.read_text()
        for skill, plugin in USER_INVOKED.items():
            if skill == owner:
                continue
            for m in re.finditer(r"(?:/%s:%s\b|`%s`)" % (plugin, skill, skill), text):
                start = max(text.rfind(".", 0, m.start()), text.rfind("\n", 0, m.start()))
                end = text.find(".", m.end())
                sentence = text[start + 1:end if end != -1 else len(text)].strip()
                if not INVOKE_VERB.search(sentence[:m.start() - (start + 1)]):
                    continue
                if HUMAN_RUNNER.search(sentence):
                    continue
                if (rel, skill) in INVOCABLE_REFS:
                    continue
                fail(rel, f"tells the agent to run `{skill}`, which is user-invoked and so "
                          f"cannot be reached by another skill — say the user runs it, or add "
                          f"(<file>, '{skill}') to INVOCABLE_REFS with the reason")

    for (rel, skill), why in INVOCABLE_REFS.items():
        path = ROOT / rel
        if not path.is_file() or skill not in path.read_text():
            fail("invocability", f"INVOCABLE_REFS still excuses {rel} -> {skill} ({why}), "
                                 "but that reference is gone — delete the entry")
        elif skill not in USER_INVOKED:
            fail("invocability", f"INVOCABLE_REFS excuses {rel} -> {skill} ({why}), but "
                                 f"`{skill}` is model-invoked now — delete the entry")


SIDECAR_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
PLUGIN_ROOT_PATH = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([\w./-]+)")
FILE_SUFFIX = re.compile(r"\.(md|py|sh|html|json|yaml|toml)$")


def _skill_relative(target, subdirs):
    """The part of a link target that has to resolve inside the skill, or None.

    A skill's markdown links two unlike things. `MAP-FORMAT.md` and
    `references/lava.md` are files it ships. `./src/ordering/CONTEXT.md` is an
    example of a layout in somebody else's repository, and `(url)` is a hole in
    a template. Only the first kind is ours to check, so: a bare sibling name,
    or a path into a directory this skill actually ships.
    """
    if target.startswith(("http", "#", "mailto:", "/", "$")):
        return None
    target = target.split("#")[0].removeprefix("./")
    if not target or not FILE_SUFFIX.search(target):
        return None
    head, _, rest = target.partition("/")
    if rest and head not in subdirs:
        return None
    return target


@check("skill-paths")
def _skill_paths():
    """A skill's own files must be reachable from the words that name them.

    Three failures, and no reader catches any of them by reading:

      * a link to a sidecar since renamed. The link still looks right.
      * a sidecar nothing names. Progressive disclosure is a pointer out of the
        SKILL.md, so a reference file no line points at is one no agent opens —
        which is what `plugins/rock/skills/lava/references/` had become.
      * a script named by a relative path. Two were, in two plugins. The working
        directory is the repository being worked on, not the plugin, so
        `scripts/hitl-loop.template.sh` resolved to nothing anywhere. The two
        jira skills already had the answer: `${CLAUDE_PLUGIN_ROOT}`.
    """
    skills = {}
    for path in repo_files("plugins/"):
        parts = path.relative_to(PLUGINS).parts
        if len(parts) > 3 and parts[1] == "skills":
            skills.setdefault(PLUGINS.joinpath(*parts[:3]), []).append(path)

    for directory, files in sorted(skills.items()):
        plugin = directory.relative_to(PLUGINS).parts[0]
        docs = [f for f in files if f.suffix == ".md"]
        scripts = [f for f in files if f.parent.name == "scripts"]
        subdirs = {f.relative_to(directory).parts[0] for f in files
                   if len(f.relative_to(directory).parts) > 1}
        for sidecar in docs:
            if sidecar.name == "SKILL.md":
                continue
            # Its own text does not count. A format document that quotes its own
            # filename would otherwise vouch for itself.
            elsewhere = "\n".join(doc.read_text() for doc in docs if doc != sidecar)
            if sidecar.name not in elsewhere:
                fail(sidecar.relative_to(ROOT),
                     "ships beside a skill that never names it — an agent reaches "
                     "a reference file only through a pointer to it")

        for doc in docs:
            where = doc.relative_to(ROOT).as_posix()
            for n, line in enumerate(doc.read_text().splitlines(), 1):
                for target in SIDECAR_LINK.findall(line):
                    inside = _skill_relative(target, subdirs)
                    if inside and not (doc.parent / inside).exists() \
                            and not (directory / inside).exists():
                        fail(f"{where}:{n}", f"links to `{target}`, which is not there")
                for named in PLUGIN_ROOT_PATH.findall(line):
                    if not (PLUGINS / plugin / named).exists():
                        fail(f"{where}:{n}", f"runs ${{CLAUDE_PLUGIN_ROOT}}/{named}, "
                                             f"which `{plugin}` does not ship")
                for script in scripts:
                    if script.name in line and "CLAUDE_PLUGIN_ROOT" not in line:
                        fail(f"{where}:{n}", f"names {script.name} by a relative path. "
                             "The working directory is the repository being worked on "
                             "— reach it through ${CLAUDE_PLUGIN_ROOT}")


@check("contamination")
def _contamination():
    vend = load_json(ROOT / "docs" / "vendored.json") or {}
    banned = set(vend.get("contaminated_skills", {}).get("names", []))
    banned |= set(vend.get("excluded_skills", {}))
    banned_files = set(vend.get("excluded_files", []))

    for path in SKILLS:
        skill = path.parts[-2]
        if skill in banned:
            fail(path.relative_to(ROOT),
                 f'"{skill}" is on the exclusion list in docs/vendored.json and must not ship')

    for bad in banned_files:
        for hit in PLUGINS.rglob(bad):
            fail(hit.relative_to(ROOT), "is an excluded file — see docs/vendored.json")


def _files_recorded(list_name, listed, shipped, base):
    """Compare one hand-written file list against what is on disk beside it.

    Both directions are worth a failure, for different reasons. A shipped file
    the list does not name is a file with no recorded provenance, which is the
    single thing this manifest exists to prevent. A name with no file behind it
    is a stale entry, and stale entries are how a manifest stops being read:
    `config.yaml` was listed as "unchanged" for the life of the plugin, and
    nothing would have noticed the day it stopped existing.
    """
    have = {str(path.relative_to(base)) for path in shipped}
    for name in sorted(have - set(listed)):
        fail((base / name).relative_to(ROOT),
             f"is shipped but absent from `{list_name}` in docs/vendored.json — "
             "every file records where it came from")
    for name in sorted(set(listed) - have):
        fail("docs/vendored.json",
             f"`{list_name}` lists {name}, which this repository no longer ships")


@check("provenance")
def _provenance():
    vend = load_json(ROOT / "docs" / "vendored.json") or {}
    shipped = repo_files("plugins/")
    recorded = {(v["plugin"], k) for k, v in vend.get("skills", {}).items()}
    on_disk = {(p.parts[-4], p.parts[-2]) for p in shipped if p.name == "SKILL.md"}
    for plugin, skill in sorted(on_disk - recorded):
        fail(f"{plugin}/{skill}", "is not in docs/vendored.json — every skill records where it came from")
    for plugin, skill in sorted(recorded - on_disk):
        fail(f"{plugin}/{skill}", "is in docs/vendored.json but not on disk")

    # The skill entries and the runtime entry both list filenames. Nothing read
    # either list until now, so 54 of them were a comment that happened to be
    # valid JSON.
    for skill, entry in sorted(vend.get("skills", {}).items()):
        directory = ROOT / "plugins" / entry["plugin"] / "skills" / skill
        _files_recorded(f'skills["{skill}"].files', entry.get("files", []),
                        [p for p in shipped if directory in p.parents], directory)
    _files_recorded("runtime.files", vend.get("runtime", {}).get("files", {}),
                    repo_files("plugins/rock/runtime/"), ROOT)


# ─────────────────────────────────────────────────────────────────────────────
# Nothing internal, ever (ADR 0001)
# ─────────────────────────────────────────────────────────────────────────────

TEXT_SUFFIXES = {".md", ".py", ".sh", ".json", ".yaml", ".yml", ".toml", ".txt", ""}

# Hosts it is fine to name, because they are public and nothing about them
# reveals how we work. Adding to this list is a curator decision: the question
# to ask is not "is this host safe" but "would a stranger learn anything about
# Passion's systems from seeing it here."
ALLOWED_HOSTS = re.compile(
    r"^(www\.)?("
    # code, packages, tooling
    r"github\.com|raw\.githubusercontent\.com|api\.github\.com"
    r"|astral\.sh|cdn\.jsdelivr\.net|cdn\.tailwindcss\.com"
    # Atlassian's own docs, and the two placeholder tenants
    r"|id\.atlassian\.com|developer\.atlassian\.com"
    r"|yoursite\.atlassian\.net|mycompany\.atlassian\.net"
    # reference material cited by vendored skills
    r"|en\.wikipedia\.org|reddit\.com|asd-ste100\.org"
    # reserved-for-documentation names, and schema namespaces
    r"|example\.com|example\.org|example\.net|api\.example\.com"
    r"|json-schema\.org|spdx\.org|schemas\.[\w.-]+|docs\.[\w.-]+"
    r"|localhost"
    r")$"
)

CREDENTIAL_NAME = r"(?i)\w*(password|passwd|secret|api[_-]?token|access[_-]?token|private[_-]?key)"
# No \b before the keyword: ROCK_PASSWORD has no word boundary before PASSWORD.

PATTERNS = [
    # A concrete Atlassian tenant that is not one of the placeholders above.
    (re.compile(r"https?://([\w-]+)\.atlassian\.net"), "names a specific Atlassian site"),
    # Anything that looks like a real internal host.
    (re.compile(r"https?://([\w-]+\.)+[a-z]{2,}"), "names a host"),
    # Credential-shaped assignment to a bare value. Config and prose only —
    # in source, `self._password = password` is an assignment, not a leak.
    (re.compile(CREDENTIAL_NAME + r"\s*[=:]\s*([^\s\"'{}$<>,)]{8,})"),
     "looks like a committed credential"),
    # Credential-shaped assignment to a quoted literal. Everywhere, including
    # source, because a quoted literal is a value rather than a reference.
    (re.compile(CREDENTIAL_NAME + r"\s*[=:]\s*[\"']([^\s\"'{}$<>]{8,})[\"']"),
     "looks like a committed credential"),
    (re.compile(r"\bATATT[A-Za-z0-9_\-]{10,}"), "looks like an Atlassian API token"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}"), "looks like a GitHub token"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "is a private key"),
    # An issue key names a real project and a real ticket in someone's tracker,
    # which ADR 0001 counts as ticket content. One reached main before this
    # rule existed and shipped publicly through every CI run.
    (re.compile(r"\b([A-Z]{2,10})-\d+\b"), "looks like a real issue key"),
]

# `ABC` is the placeholder every skill uses; `ADR` is our own decision records.
# The rest are standards tokens that share the shape and say nothing about us.
ISSUE_KEY_OK = {"ABC", "ADR", "UTF", "ISO", "RFC", "SHA", "AES", "RSA",
                "HTTP", "TLS", "ASD", "STE", "ES", "PEP"}

# The unquoted rule does not apply to source: assigning one variable to another
# trips it constantly and never means anything.
SOURCE_SUFFIXES = {".py", ".sh"}
UNQUOTED_RULE = PATTERNS[2][0]

# Words that make a credential-shaped line obviously a placeholder or a variable.
PLACEHOLDER = re.compile(
    r"(?i)(your_|<|\{|\$|\.\.\.|example|placeholder|password\s*[=:]\s*$|"
    r"_env\b|environ|getenv|require\(|HINTS|foo@bar)"
)


@check("secrets")
def _secrets():
    for path in repo_files(suffixes=TEXT_SUFFIXES):
        rel = path.relative_to(ROOT)
        if rel == SELF:
            continue  # this file necessarily contains the patterns
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for n, line in enumerate(lines, 1):
            for pattern, why in PATTERNS:
                if pattern is UNQUOTED_RULE and path.suffix in SOURCE_SUFFIXES:
                    continue
                m = pattern.search(line)
                if not m:
                    continue
                if why == "names a host":
                    host = re.sub(r"^https?://", "", m.group(0)).split("/")[0]
                    if ALLOWED_HOSTS.match(host):
                        continue
                if why == "names a specific Atlassian site" and ALLOWED_HOSTS.match(
                        m.group(0).split("//")[1]):
                    continue
                if why.startswith("looks like a committed") and PLACEHOLDER.search(line):
                    continue
                if why == "looks like a real issue key" and m.group(1) in ISSUE_KEY_OK:
                    continue
                fail(f"{rel}:{n}", f"{why} — {line.strip()[:80]}")


# ─────────────────────────────────────────────────────────────────────────────
# Runtime invariants (ADR 0016)
# ─────────────────────────────────────────────────────────────────────────────

@check("passion_env")
def _passion_env():
    copies = [p for p in repo_files("plugins/") if p.name == "passion_env.py"]
    if len(copies) < 2:
        fail("passion_env", f"expected several copies, found {len(copies)}")
        return
    texts = {c.read_text() for c in copies}
    if len(texts) != 1:
        listing = "\n    ".join(str(c.relative_to(ROOT)) for c in copies)
        fail("passion_env", "copies have drifted apart. They must be byte-identical:\n    " + listing)


@check("write-guard")
def _write_guard():
    """Every write in rock_query.py must be listed in WRITE_COMMANDS (ADRs 0016, 0023)."""
    src = (PLUGINS / "rock" / "runtime" / "scripts" / "rock_query.py").read_text()

    m = re.search(r"WRITE_COMMANDS = \{(.*?)\n\}", src, re.S)
    if not m:
        fail("rock_query.py", "WRITE_COMMANDS is gone — the read-only boundary is unenforced")
        return
    guarded = set(re.findall(r'"([\w-]+)":', m.group(1)))

    if "_guard_writes(parsed.command)" not in src:
        fail("rock_query.py", "_guard_writes is no longer called from main()")

    # Find every cmd_* function that issues a write, and map it to its subcommand.
    writes = set()
    for fn in re.finditer(r"^def (cmd_\w+)\(.*?(?=^def |\Z)", src, re.S | re.M):
        if re.search(r"client\.(post|put|patch|delete)\(", fn.group(0)):
            writes.add(fn.group(1))

    registered = dict(re.findall(r'add_parser\(\s*"([\w-]+)".*?\n.*?set_defaults\(func=(cmd_\w+)\)',
                                 src, re.S))
    registered.update(dict(re.findall(r'"([\w-]+)"[^\n]*\n(?:[^\n]*\n)*?[^\n]*set_defaults\(func=(cmd_\w+)\)',
                                      src)))
    writing_commands = {cmd for cmd, fn in registered.items() if fn in writes}

    missing = writing_commands - guarded
    if missing:
        fail("rock_query.py", f"these subcommands write but are not in WRITE_COMMANDS: "
                              f"{sorted(missing)} — running the script directly would reach them")
    stale = guarded - set(registered)
    if stale:
        fail("rock_query.py", f"WRITE_COMMANDS lists subcommands that no longer exist: {sorted(stale)}")


def _by_function(tree):
    """Every node in the tree, tagged with the function it sits inside.

    `ast.walk` is breadth-first, so an outer function is visited before the
    functions nested in it and the inner name overwrites the outer one. A node
    at module level is not in the mapping at all.
    """
    owner = {}
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for node in ast.walk(fn):
                owner[id(node)] = fn.name
    return owner


def _string_literals(src, skip_docstrings=False):
    """Every string constant in the source, docstrings optionally left out.

    f-strings arrive in pieces -- f"Blocks/{id}/AttributeValues" yields
    "Blocks/" and "/AttributeValues" as separate constants -- which is what we
    want, since the interesting half is the literal tail.
    """
    tree = ast.parse(src)
    docs = set()
    if skip_docstrings:
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if not isinstance(body, list) or not body:
                continue
            if not isinstance(node, (ast.Module, ast.ClassDef,
                                     ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            first = body[0]
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                docs.add(id(first.value))
    return [n for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docs]


@check("rock-write-shapes")
def _rock_write_shapes():
    """The two request shapes Rock will not forgive (ADR 0022).

    Rock's PUT is a full-entity replace: `ApiController<T>.Put` hands the posted
    object to `CurrentValues.SetValues`, so every column absent from the body is
    set to null. A partial PUT therefore 400s where a nulled column is required,
    and silently corrupts the row where it is not — losing the created-by audit
    and replacing the Guid. Partial updates use PATCH. The single PUT the
    runtime keeps is inside `api_request`, which refuses to send one without an
    explicit `full_replace` acknowledgement.

    This check is now the backstop rather than the guard. `client.put` takes a
    required keyword-only `full_replace`, so a caller who meant `patch` gets a
    TypeError before a request leaves the process. That matters because the
    allow-list below is a pair of strings: renaming the file or the function
    would have silently stopped this check from guarding anything, and a
    signature cannot be renamed around.

    Attribute values are the other one. There is no `{Entity}/{id}/AttributeValues`
    route; both shapes that look plausible answer "The OData path is invalid."
    The real route binds from the query string.
    """
    put_is_deliberate = {("plugins/rock/runtime/scripts/rock_build.py", "api_request")}

    for path in sorted(PLUGINS.rglob("*.py")):
        rel = path.relative_to(ROOT)
        src = path.read_text()

        # Split on any def, indented or not, so a PUT inside a class method is
        # attributed to that method rather than to whatever function came before
        # it. Both runtime scripts define classes.
        for fn in re.finditer(r"^[ \t]*def (\w+)\(.*?(?=^[ \t]*def |\Z)", src, re.S | re.M):
            if "client.put(" not in fn.group(0):
                continue
            if (str(rel), fn.group(1)) in put_is_deliberate:
                continue
            fail(f"{rel}", f"{fn.group(1)}() sends a PUT. Rock's PUT replaces the whole "
                           f"entity — use client.patch for a partial update")

        # Only a string the code actually sends is a defect. Prose naming the
        # dead route is documentation, and matching on the text of a line cannot
        # tell the two apart. The parse tree can: comments are not in it at all,
        # and a docstring is a statement we can identify and skip.
        for node in _string_literals(src, skip_docstrings=True):
            if "/AttributeValues" in node.value:
                fail(f"{rel}:{node.lineno}",
                     "there is no {Entity}/{id}/AttributeValues route — attribute "
                     "values go to POST {Entity}/AttributeValue/{id} with "
                     "attributeKey and attributeValue as query parameters")


def _bare_table_read(node):
    """The table name, if this call fetches a whole Rock table by name.

    `client.get("Groups", ...)` asks for every group. `client.get(f"Groups/{id}")`
    asks for one and is fine, and so is `row.get("Description")` — a dict lookup
    that happens to share the method name. Two tests separate them, either of
    which is enough: the receiver is the client this file always calls `client`,
    or the call passes OData `params` alongside a table-shaped name. The second
    is what catches a fetch written against a differently-named client.
    """
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get" and node.args):
        return None
    endpoint = node.args[0]
    if not (isinstance(endpoint, ast.Constant) and isinstance(endpoint.value, str)):
        return None
    if "/" in endpoint.value or not re.fullmatch(r"[A-Z][A-Za-z]+", endpoint.value):
        return None
    receiver = node.func.value
    is_client = isinstance(receiver, ast.Name) and receiver.id == "client"
    has_odata = any(kw.arg == "params" for kw in node.keywords)
    return endpoint.value if (is_client or has_odata) else None


@check("rock-query-caps")
def _rock_query_caps():
    """A collection the read side shows is fetched through one of three functions.

    `rock_query.py` answers questions about a Rock instance with tens of
    thousands of people in it. A fetch written by hand there has two ways to
    mislead, and both shipped: a `$top` of its own, which returns the first N
    and prints N as though it were the total, and no bound at all, which asks
    an instance-sized table for every row.

    So the file has three ways to fetch a collection and no fourth:
    `get_capped` for anything a person will see, which reads one row past the
    limit and reports whether it found one; `groups_of_types` for the same thing
    chunked past Rock's filter-size ceiling; and `first` for a probe that wants
    one row and does not care what else matched.

    Two shapes fail here. A `$top` outside those three is a fourth cap, and a
    `client.get` on a bare table name outside those three is an unbounded read
    of that table — `client.get("Groups", ...)` rather than
    `client.get(f"Groups/{id}")`. What this does not catch is a named action
    route that happens to return a list, such as `Groups/GetFamilies/{id}`;
    those are bounded by the entity they hang off, and a check that guessed at
    which ones were not would fail on the wrong thing.

    The write side is deliberately out of scope. `rock_build.py` uses `$top: 1`
    to turn a name into an id and never prints a count, and `rock_catalog.py`
    pages with `$top` and `$skip` precisely so it can fetch every row. Neither
    can mislead anyone about how much it found.
    """
    rel = "plugins/rock/runtime/scripts/rock_query.py"
    path = ROOT / rel
    fetchers = {"get_capped", "groups_of_types", "first"}

    if not path.exists():
        fail(rel, "is missing — this check guards it by path, so a move has to "
                  "update the path here as well")
        return

    tree = ast.parse(path.read_text())
    defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    for missing in sorted(fetchers - defined):
        fail(rel, f"{missing}() is gone. It is one of the three fetchers this "
                  f"check allows, so removing it silently stops the guard from "
                  f"guarding — remove it from the allow-list here too")

    owner = _by_function(tree)
    for node in ast.walk(tree):
        inside = owner.get(id(node))
        if inside in fetchers:
            continue

        if isinstance(node, ast.Constant) and node.value == "$top":
            fail(f"{rel}:{node.lineno}",
                 f"{inside or '<module>'}() sets its own $top. That returns the "
                 f"first N and says nothing about the rest — fetch through "
                 f"get_capped, which reports whether more matched, or first, "
                 f"which asks for one row on purpose")

        table = _bare_table_read(node)
        if table:
            fail(f"{rel}:{node.lineno}",
                 f"{inside or '<module>'}() reads the whole {table} table with "
                 f"no bound. Fetch through get_capped, which reports whether "
                 f"more matched, or first, which asks for one row on purpose")


def _formatted_id(node):
    """True if this f-string field pads an entity Id into a column.

    `f"{wf['Id']:5d}"` is a listing's id column. `f"(ID: {gt['Id']})"` is prose
    with an id in it and has no format spec at all, which is the line between
    the two: a width is only ever chosen for a column.
    """
    if not (isinstance(node, ast.FormattedValue) and node.format_spec):
        return False
    return any(isinstance(n, ast.Constant) and n.value == "Id"
               for n in ast.walk(node.value))


@check("rock-listing-rows")
def _rock_listing_rows():
    """The read side's id column is decided in one function.

    Eighteen loops in `rock_query.py` formatted a row of "id  label" by hand,
    and the width had drifted to three: `:5d` at eight of them, `:6d` at eight,
    `:8d` at one. Nothing was wrong with any single line, which is why it drifted
    -- each loop picked a width and none of them could see the others.

    `row()` picks it once. A padded Id anywhere else is a nineteenth loop, and
    the drift starts again from there, so this fails on one.

    An id in prose is untouched: `f"(ID: {gt['Id']})"` has no format spec, and a
    width is only ever chosen for a column.
    """
    rel = "plugins/rock/runtime/scripts/rock_query.py"
    path = ROOT / rel

    if not path.exists():
        fail(rel, "is missing — this check guards it by path, so a move has to "
                  "update the path here as well")
        return

    tree = ast.parse(path.read_text())
    if "row" not in {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}:
        fail(rel, "row() is gone. It is the one place this check allows an id "
                  "column to be formatted, so removing it silently stops the "
                  "guard from guarding")

    owner = _by_function(tree)
    for node in ast.walk(tree):
        if owner.get(id(node)) == "row" or not _formatted_id(node):
            continue
        fail(f"{rel}:{node.lineno}",
             f"{owner.get(id(node)) or '<module>'}() pads an Id into a column of "
             f"its own. Build the line with row(), which is where the width is "
             f"chosen for every listing")


@check("no-repo-writes")
def _no_repo_writes():
    """Nothing may write into a repository — attachments, screenshots, plans (ADR 0001)."""
    for path in repo_files("plugins/", {".py"}):
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if re.search(r"REPO_ROOT|Path\(__file__\)\.parent\.parent\s*/\s*[\"'](?!\.)", line):
                if "rock_paths" in line or "sys.path" in line:
                    continue
                fail(f"{path.relative_to(ROOT)}:{n}",
                     f"resolves a path relative to the repo or plugin — "
                     f"use rock_paths or CLAUDE_PLUGIN_DATA — {line.strip()[:70]}")


@check("executables")
def _executables():
    """Entry points must be runnable. `.template.sh` files are copied, not run."""
    import os
    for path in repo_files("plugins/", {".sh"}):
        if path.name.endswith(".template.sh"):
            continue
        if not os.access(path, os.X_OK):
            fail(path.relative_to(ROOT), "is not executable — chmod +x it")


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if failures:
        print(f"✗ {len(failures)} problem(s):\n", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        print(file=sys.stderr)
        sys.exit(1)
    print(f"✓ {checks_run} checks passed — {len(LISTED)} plugins, {len(SKILLS)} skills")
