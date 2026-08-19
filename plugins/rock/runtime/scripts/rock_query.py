"""Query Rock RMS entities -- workflows, pages, blocks.

Usage:
  uv run scripts/rock_query.py workflows                    # list workflows
  uv run scripts/rock_query.py workflow "Volunteer Signup"   # get one workflow
  uv run scripts/rock_query.py workflow 234                  # get by ID
  uv run scripts/rock_query.py pages                         # list pages
  uv run scripts/rock_query.py page "/volunteers"            # get by route
  uv run scripts/rock_query.py page 456                      # get by ID
  uv run scripts/rock_query.py search "volunteer"            # search across entities

No read view prints its own answer. A list of entities is a `Listing`, one
entity is a `Detail`, `--json` is a `Raw`, and a tree or a single sentence is a
`Text`. Each is built, returned, and printed by `render` at the boundary, which
makes the return value the test surface rather than captured stdout.

The write commands at the bottom still print as they go, because each reports a
step that has already landed and a caller reading them needs them in order.
"""

import argparse
import json
import os
import sys
import traceback

from rock_client import RockClient, RockNotFound, api_errors_reported, odata_str
from rock_log import get_logger

log = get_logger("rock.query")

CONNECTION_STATES = {0: "Active", 1: "Inactive", 2: "Future", 3: "Connected"}
CONNECTION_STATE_FILTER = {v.lower(): k for k, v in CONNECTION_STATES.items()}
GENDERS = {1: "Male", 2: "Female"}
GROUP_MEMBER_STATUSES = {0: "Inactive", 1: "Active", 2: "Pending"}
EXPRESSION_TYPES = {0: "Filter", 1: "GroupAll", 2: "GroupAny", 3: "GroupAllFalse", 4: "GroupAnyFalse"}
FAMILY_GROUP_TYPE_ID = 10
KNOWN_RELATIONSHIPS_GROUP_TYPE_ID = 11
SEARCH_LIMIT = 10
CHOOSER_LIMIT = 5
# A child collection nobody passes a --limit for: blocks on a page, actions in
# an activity, fields in a report, sub-areas under a check-in group. It sits far
# above any real value, so it is a backstop against an unbounded response rather
# than a number anyone tunes -- and when it does bite, `tally` says so instead
# of printing the cap as the total.
CHILD_LIMIT = 200
CHILD_HINT = "this view has no --limit"
# What to do about a name that matched several things. Both choosers say it:
# the shared ladder's, and the one `person` builds from a people search.
CHOOSER_HINT = "narrow it, or pass the ID"
# `search` has no --limit to raise, so its cap needs different advice.
WIDEN = "narrow the term or list that entity directly"


# Rock rejects a filter past 100 expression nodes, and has no `in` operator to
# express this compactly. Measured: an or-chain of 15 ids alongside a
# substringof is accepted, 20 comes back a 400.
TYPE_CHUNK = 15


def groups_of_types(client, name_filter, type_ids, limit):
    """Groups matching a name, restricted to a set of group types.

    The restriction belongs in the query, not after it -- filtering afterwards
    spends the cap on rows that are about to be discarded. It goes in chunks
    because the whole type list in one or-chain exceeds Rock's node limit.
    """
    seen, rows = set(), []
    for i in range(0, len(type_ids), TYPE_CHUNK):
        types = " or ".join(f"GroupTypeId eq {t}" for t in type_ids[i:i + TYPE_CHUNK])
        for g in client.get("Groups", params={
            "$filter": f"{name_filter} and ({types})",
            "$select": "Id,Name",
            "$top": limit + 1,
        }) or []:
            if g["Id"] not in seen:
                seen.add(g["Id"])
                rows.append(g)
    return rows[:limit], len(rows) > limit


def get_capped(client, endpoint, params, limit):
    """Rows up to `limit`, and whether Rock held more than that.

    A bare $top returns the first N and says nothing about the rest, so a
    header printing len() of the result presents a cap as a total: `dataviews`
    announced "Data Views (100)" on an instance holding more than ten times
    that. Asking for one row more than will be shown is what makes the
    difference visible without a second count query.
    """
    rows = client.get(endpoint, params={**params, "$top": limit + 1}) or []
    return rows[:limit], len(rows) > limit


def first(client, endpoint, params):
    """The one row a probe wants, or None.

    A probe asks "is there one, and what is its id" -- a route that resolves to
    a page, an alias for a person, an exact name match ahead of a fuzzy one. It
    is the one collection fetch that does not report a `more`, because more is
    not something the caller can act on: it asked for one.

    So there are three ways to fetch a collection in this file and no fourth.
    `get_capped` for anything shown, `groups_of_types` for the chunked variant,
    and this. CI fails on a `$top` written anywhere else.
    """
    rows = client.get(endpoint, params={**params, "$top": 1}) or []
    return rows[0] if rows else None


def tally(rows, more, hint="raise --limit"):
    """A header count that admits when it is a cap rather than a total."""
    return f"first {len(rows)} — more exist, {hint}" if more else str(len(rows))


def _inactive(entity):
    """The suffix a row carries when Rock has it switched off."""
    return "" if entity.get("IsActive") else " [inactive]"


ID_WIDTH = 6
_LABEL_COLUMN = 2 + ID_WIDTH + 2
# A detail heading starts at the margin, its fields one step in, and each
# further depth one step past that. One number, so nothing drifts.
_DETAIL_INDENT = 2


def row(entity_id, label, indent=2):
    """One line of a listing: the id column, two spaces, then the label.

    Eighteen loops formatted this by hand and the width had drifted to three --
    `:5d` at eight of them, `:6d` at eight, `:8d` at one -- because each loop
    picked its own. A column chosen once lines up between commands as well as
    inside one, and CI fails on an id formatted anywhere but here.
    """
    return f"{' ' * indent}{entity_id:{ID_WIDTH}d}  {label}"


class Listing:
    """Rows an operator asked for, and whether Rock had more of them.

    A command builds one and returns it; the boundary renders it. Twenty-nine
    commands returned nothing and spoke only through `print`, so a test of one
    had to capture stdout and match formatted text. The return value is the
    test surface now.

    The count, the note that says it is a cap, the empty case and the column a
    label starts in are each written once here instead of once per command. The
    empty line derives from the title -- "Data Views" gives "No data views
    found." -- which is what all eight of them already said.
    """

    def __init__(self, title, more=False, hint="raise --limit", empty=None,
                 spaced=False):
        self.title = title
        self.more = more
        self.hint = hint
        self.empty = f"No {title.lower()} found." if empty is None else empty
        self.spaced = spaced
        self.rows = []

    def add(self, entity_id, label, *continued):
        """One row, plus any lines continuing it under the label column."""
        self.rows.append((entity_id, label, [c for c in continued if c]))
        return self

    def render(self):
        if not self.rows:
            if self.empty:
                print(self.empty)
            return
        print(f"{self.title} ({tally(self.rows, self.more, self.hint)}):\n")
        for entity_id, label, continued in self.rows:
            print(row(entity_id, label))
            for line in continued:
                print(f"{' ' * _LABEL_COLUMN}{line}")
            if self.spaced:
                print()


class Section:
    """A child list under a detail heading: a title, a count, and its lines.

    `rows` is what was fetched, and only its length is read from it. The lines
    arrive separately because they are not always one per row -- blocks on a
    page interleave a zone heading, and a family prints a line per member under
    a line per family.

    A section that ends up with no lines prints nothing, so a command no longer
    guards its own header with `if members:`. Twelve of them did.
    """

    def __init__(self, title, rows=None, more=False, hint="raise --limit"):
        self.title = title
        self.count = None if rows is None else tally(rows, more, hint)
        self.lines = []

    def add(self, text, depth=0):
        """One line under the section title. A blank one adds nothing."""
        if text:
            self.lines.append((depth, text))
        return self

    def row(self, entity_id, label, depth=0):
        """One line that leads with the id column, as a listing does."""
        self.lines.append((depth, row(entity_id, label, indent=0)))
        return self


class Detail:
    """One entity: a heading, the fields under it, and its child sections.

    Thirteen views printed this shape for themselves. Each carried its own
    two-space indent, its own `if x.get(...)` around every optional line, its
    own `if args.json` branch, and no return value, so a test of one had to
    capture stdout and match formatted text. The return value is the test
    surface now, the same way `Listing` did it for the eight list views.

    Depth is what nests: a field sits under the heading, and a line at depth 1
    sits under the field above it.
    """

    def __init__(self, heading):
        self.heading = heading
        self.parts = []

    def field(self, label, value):
        """A `Label: value` line. A missing value adds no line at all.

        `False` and `0` are values -- "Active: False" is the answer to a
        question somebody asked -- so only None and the empty string drop out.
        """
        if value is None or value == "":
            return self
        return self.line(f"{label}: {value}")

    def line(self, text, depth=0):
        """A line under the heading carrying no label of its own."""
        if text:
            self.parts.append((depth, text))
        return self

    def section(self, title, rows=None, more=False, hint="raise --limit"):
        """Open a child list and hand it back, for the caller to fill."""
        made = Section(title, rows, more, hint)
        self.parts.append((0, made))
        return made

    def render(self):
        print(self.heading)
        for depth, part in self.parts:
            if isinstance(part, str):
                print(f"{' ' * (_DETAIL_INDENT + 2 * depth)}{part}")
                continue
            if not part.lines:
                continue
            title = part.title if part.count is None else f"{part.title} ({part.count})"
            print(f"{' ' * _DETAIL_INDENT}{title}:")
            for line_depth, text in part.lines:
                print(f"{' ' * (_DETAIL_INDENT + 2 + 2 * line_depth)}{text}")


class Raw:
    """The entity as Rock sent it, for `--json`.

    Ten commands held the same three lines -- dump, print, return -- so ten
    commands each picked an indent and each answered a caller with nothing.
    """

    def __init__(self, entity):
        self.entity = entity

    def render(self):
        print(json.dumps(self.entity, indent=2))


class Text:
    """Text a command formatted itself, printed at the boundary like the rest.

    Three views build a tree rather than a heading with fields under it: a
    workflow with its activities and actions, the check-in hierarchy, and an
    audit. A tree is not a `Detail`, and forcing it into one would cost more
    than it saves. What still applies is the reason the detail views moved: a
    command that prints answers its caller with nothing. So these return the
    text they built, and so do the commands whose whole answer is one sentence.
    """

    def __init__(self, text):
        self.text = text

    def render(self):
        print(self.text)


def render(report):
    """Print what a read command returned. Nothing else on the read side prints.

    A command answers with a `Listing`, a `Detail`, a `Raw`, a `Text`, or a list
    of them where a view has two parts. The only thing asked of any of them is
    that it renders itself, and a list gets a blank line between its parts.

    There is no branch for `None`, because no command returns one: a name that
    resolves to nothing raises `LookupMiss` instead. A guard here would turn a
    command that forgot to return into a command that prints nothing, which is
    the failure this whole arrangement exists to make impossible.
    """
    parts = report if isinstance(report, list) else [report]
    for index, part in enumerate(parts):
        if index:
            print()
        part.render()


class LookupMiss(Exception):
    """What an operator named does not resolve to one entity.

    Carries the renderable that says so: a `Text` where nothing matched, a
    `Listing` where several did. The boundary renders it and exits 1, which is
    the answer to the question the footnote in a0d8743 left open. Naming a thing
    that is not there is a failed request. An empty collection is not -- `query
    workflows` on an instance holding none answered correctly -- and the two
    reach the boundary by different routes, so they can be told apart.

    A raise rather than a returned None, because eleven commands wrote the same
    `if not x: return` after the same call, and because a helper that reports a
    miss by printing is a second place the read side reaches stdout.
    """

    def __init__(self, report):
        self.report = report
        super().__init__("lookup miss")


def _resolve_name(client, endpoint, entity_id, field="Name"):
    """Look up a single entity's name field by ID. Returns '?' on failure."""
    if not entity_id:
        return "?"
    try:
        result = client.get(f"{endpoint}/{entity_id}", params={"$select": field})
        return result.get(field, "?") if result else "?"
    except Exception as _e:
        log.debug("lookup failed: %s", _e)
        return "?"


def _resolve_person_name(client, alias_id, cache=None):
    """Resolve PersonAliasId to 'FirstName LastName'. Uses optional cache dict."""
    if not alias_id:
        return "?"
    if cache is not None and alias_id in cache:
        return cache[alias_id]
    try:
        alias = client.get(f"PersonAlias/{alias_id}", params={"$select": "PersonId"})
        if alias:
            p = client.get(f"People/{alias['PersonId']}", params={"$select": "FirstName,LastName"})
            if p:
                name = f"{p['FirstName']} {p['LastName']}"
                if cache is not None:
                    cache[alias_id] = name
                return name
    except Exception as _e:
        log.debug("lookup failed: %s", _e)
    if cache is not None:
        cache[alias_id] = "?"
    return "?"


def _find_entity(client, endpoint, identifier, name_field="Name", label=None,
                 search=None):
    """The one entity an operator meant, or `LookupMiss` carrying the reason.

    Every command that takes a name-or-ID argument climbs the same ladder: try
    it as an ID, then as an exact name, then as a substring. Five commands used
    to climb it themselves, and they had drifted -- one skipped the exact match,
    so `attendance --group Ushers` could resolve to "Ushers Team"; one skipped
    the ID fetch, so a group ID that does not exist reported no attendance
    rather than no group; and the chooser was printed three times with the ID
    column at three different widths.

    `search` is the seam. It runs one OData filter and answers
    `(rows, more)` -- the same pair `get_capped` returns -- so a caller that has
    to restrict the search does that without a branch in here. `checkin` passes
    one that chunks a group-type or-chain past Rock's filter-size ceiling; the
    default asks `endpoint` directly.
    """
    label = label or endpoint.rstrip("s").lower()
    if search is None:
        def search(odata_filter, limit):
            return get_capped(client, endpoint, {"$filter": odata_filter}, limit)

    try:
        eid = int(identifier)
        result = client.get(f"{endpoint}/{eid}")
        if result:
            return result
    except (ValueError, RockNotFound):
        pass

    exact, _more = search(f"{name_field} eq '{odata_str(identifier)}'", 1)
    if exact:
        return exact[0]

    results, more = search(
        f"substringof('{odata_str(identifier)}', {name_field}) eq true",
        CHOOSER_LIMIT)
    if len(results) == 1:
        return results[0]
    if results:
        # A chooser that silently drops candidates is worse than a long one: the
        # entity somebody wants reads as not existing. So the count is in the
        # header, the same way every other capped collection says it.
        chooser = Listing(f"Multiple {label}s match '{identifier}'", more,
                          hint=CHOOSER_HINT)
        for r in results:
            chooser.add(r["Id"], r.get(name_field, "?"))
        raise LookupMiss(chooser)
    raise LookupMiss(Text(f"No {label} found matching '{identifier}'"))


def _people_filter(identifier):
    """The OData filter for whatever an operator typed to mean a person.

    An address is matched exactly; two words are a first and a last name; one
    word is a surname. `person` and `bgc --person` both accept the same
    argument, and they had two copies of this -- disagreeing about what "Smith"
    means is a difference nobody would have chosen.
    """
    if "@" in identifier:
        return f"Email eq '{odata_str(identifier)}'"
    parts = identifier.strip().split()
    if len(parts) >= 2:
        return (f"FirstName eq '{odata_str(parts[0])}' and "
                f"LastName eq '{odata_str(parts[-1])}'")
    return f"LastName eq '{odata_str(parts[0])}'"


def _enrich_actions_entity_types(actions, client):
    """Batch-resolve EntityType FriendlyNames for a list of actions."""
    eids = {a.get("EntityTypeId") for a in actions if a.get("EntityTypeId")}
    et_map = {}
    for eid in eids:
        try:
            et = client.get(f"EntityTypes/{eid}", params={"$select": "FriendlyName"})
            et_map[eid] = et or {}
        except Exception as _e:
            log.debug("entity type lookup failed: %s", _e)
            et_map[eid] = {}
    for action in actions:
        action["EntityType"] = et_map.get(action.get("EntityTypeId"), {})


def format_workflow_tree(wf):
    """Format a workflow type as a structural tree."""
    lines = [f"{wf['Name']} (ID: {wf['Id']})"]
    desc = wf.get("Description", "")
    if desc:
        lines.append(f"  {desc[:120]}")
    lines.append(f"  Category: {wf.get('CategoryName', 'none')}")
    lines.append(f"  Active: {wf.get('IsActive', False)}")

    activities = wf.get("ActivityTypes", [])
    for i, act in enumerate(_by_order(activities)):
        is_last_act = i == len(activities) - 1
        prefix = "└─" if is_last_act else "├─"
        activated = " (activated with workflow)" if act.get("IsActivatedWithWorkflow") else ""
        lines.append(f"  {prefix} Activity: {act['Name']}{activated}")

        actions = act.get("ActionTypes", [])
        for j, action in enumerate(_by_order(actions)):
            is_last = j == len(actions) - 1
            branch = "   " if is_last_act else "│  "
            ap = "└─" if is_last else "├─"
            entity_name = action.get("EntityType", {}).get("FriendlyName", "?")
            lines.append(f"  {branch} {ap} Action: {action['Name']} [{entity_name}]")

    return "\n".join(lines)


def _by_order(items):
    return sorted(items, key=lambda a: a.get("Order", 0))


def _load_workflow_tree(wf, client):
    """Load full workflow tree: activities, actions, and entity type names."""
    wf_id = wf["Id"]
    activities, activities_capped = get_capped(client, "WorkflowActivityTypes", {
        "$filter": f"WorkflowTypeId eq {wf_id}",
        "$orderby": "Order",
    }, CHILD_LIMIT)
    all_actions = []
    for act in activities:
        actions, actions_capped = get_capped(client, "WorkflowActionTypes", {
            "$filter": f"ActivityTypeId eq {act['Id']}",
            "$orderby": "Order",
        }, CHILD_LIMIT)
        act["ActionTypes"] = actions
        act["ActionTypesCapped"] = actions_capped
        all_actions.extend(actions)
    _enrich_actions_entity_types(all_actions, client)
    wf["ActivityTypes"] = activities
    wf["ActivityTypesCapped"] = activities_capped
    return wf


def _get_action_settings(client, action_id):
    """Fetch settings (attribute values) for a workflow action. Returns flat dict or None on error."""
    try:
        action = client.get(f"WorkflowActionTypes/{action_id}", params={
            "loadAttributes": "simple",
        })
        if not action:
            return None
        attr_values = action.get("AttributeValues", {})
        flat = {}
        for k, v in attr_values.items():
            if isinstance(v, dict):
                flat[k] = v.get("Value", "")
            else:
                flat[k] = str(v) if v else ""
        return flat
    except Exception as e:
        print(f"  Warning: could not load settings for action {action_id}: {e}", file=sys.stderr)
        return None


def cmd_workflows(args, client):
    params = {
        "$select": "Id,Name,Description,IsActive,CategoryId",
        "$orderby": "Name",
    }
    if args.category:
        params["$filter"] = f"Category/Name eq '{odata_str(args.category)}'"

    workflows, more = get_capped(client, "WorkflowTypes", params, args.limit)

    # Build category ID-to-name map for display
    cat_ids = {wf["CategoryId"] for wf in workflows if wf.get("CategoryId")}
    cat_names = {cid: _resolve_name(client, "Categories", cid) for cid in cat_ids}

    listing = Listing("Workflows", more)
    for wf in workflows:
        active = _inactive(wf)
        cat_name = cat_names.get(wf.get("CategoryId"), "")
        cat_str = f" ({cat_name})" if cat_name else ""
        listing.add(wf["Id"], f"{wf['Name']}{cat_str}{active}")
    return listing


def cmd_workflow(args, client):
    wf = _find_entity(client, "WorkflowTypes", args.identifier,
                      label="workflow")
    _load_workflow_tree(wf, client)
    return Raw(wf) if args.json else Text(format_workflow_tree(wf))


def cmd_pages(args, client):
    params = {
        "$select": "Id,InternalName,PageTitle,ParentPageId,LayoutId,IsSystem",
        "$orderby": "InternalName",
    }
    if args.site:
        params["$filter"] = f"Layout/SiteId eq {args.site}"

    pages, more = get_capped(client, "Pages", params, args.limit)

    listing = Listing("Pages", more)
    for p in pages:
        name = p.get("InternalName") or p.get("PageTitle") or "(untitled)"
        system = " [system]" if p.get("IsSystem") else ""
        listing.add(p["Id"], f"{name}{system}")
    return listing


def cmd_page(args, client):
    identifier = args.identifier

    # A route is the one thing a page answers to that no other entity has, so
    # it is the one step the shared ladder cannot do. It goes first because a
    # route is never a number and the ladder starts by trying one, so the two
    # probes cannot shadow each other. A route pointing at a page that is gone
    # falls through to the name search rather than out of the command.
    page = None
    if not identifier.lstrip("-").isdigit():
        route = first(client, "PageRoutes", {
            "$filter": f"Route eq '{odata_str(identifier.lstrip('/'))}'",
        })
        if route and route.get("PageId"):
            page = client.get(f"Pages/{route['PageId']}")
    if not page:
        page = _find_entity(client, "Pages", identifier,
                            name_field="InternalName", label="page")

    # Get blocks on this page
    blocks, blocks_capped = get_capped(client, "Blocks", {
        "$filter": f"PageId eq {page['Id']}",
        "$orderby": "Zone,Order",
    }, CHILD_LIMIT)
    if blocks:
        bt_ids = {b.get("BlockTypeId") for b in blocks if b.get("BlockTypeId")}
        bt_names = {btid: _resolve_name(client, "BlockTypes", btid) for btid in bt_ids}
        for b in blocks:
            b["BlockType"] = {"Name": bt_names.get(b.get("BlockTypeId"), "?")}

    # Get routes
    routes, routes_capped = get_capped(client, "PageRoutes", {
        "$filter": f"PageId eq {page['Id']}",
        "$select": "Route",
    }, CHILD_LIMIT)

    if args.json:
        page["Blocks"] = blocks or []
        page["Routes"] = routes or []
        return Raw(page)

    name = page.get("InternalName") or page.get("PageTitle") or "(untitled)"
    detail = Detail(f"{name} (ID: {page['Id']})")
    if routes:
        shown = ", ".join("/" + r["Route"] for r in routes)
        detail.field("Routes", shown + (", ..." if routes_capped else ""))
    detail.field("Layout ID", page.get("LayoutId"))

    zones = detail.section("Blocks", blocks, blocks_capped, hint=CHILD_HINT)
    current_zone = None
    for b in blocks:
        zone = b.get("Zone", "Main")
        if zone != current_zone:
            current_zone = zone
            zones.add(f"Zone: {zone}")
        bt_name = b.get("BlockType", {}).get("Name", "?")
        zones.add(f"{b['Name'] or bt_name} [{bt_name}]", depth=1)
    return detail


def cmd_search(args, client):
    query = args.query
    print(f"Searching for '{query}'...\n")

    # Search workflows
    workflows, wf_more = get_capped(client, "WorkflowTypes", {
        "$filter": f"substringof('{odata_str(query)}', Name) eq true or substringof('{odata_str(query)}', Description) eq true",
        "$select": "Id,Name,IsActive",
    }, SEARCH_LIMIT)
    wf_listing = Listing("Workflows", wf_more, WIDEN, empty="")
    for wf in workflows:
        wf_listing.add(wf["Id"], wf["Name"])

    # Search pages
    pages, pg_more = get_capped(client, "Pages", {
        "$filter": f"substringof('{odata_str(query)}', InternalName) eq true or substringof('{odata_str(query)}', PageTitle) eq true",
        "$select": "Id,InternalName,PageTitle",
    }, SEARCH_LIMIT)
    pg_listing = Listing("Pages", pg_more, WIDEN, empty="")
    for p in pages:
        name = p.get("InternalName") or p.get("PageTitle") or "(untitled)"
        pg_listing.add(p["Id"], name)

    # Search data views
    dvs, dv_more = get_capped(client, "DataViews", {
        "$filter": f"substringof('{odata_str(query)}', Name) eq true",
        "$select": "Id,Name",
    }, SEARCH_LIMIT)
    dv_listing = Listing("Data Views", dv_more, WIDEN, empty="")
    for dv in dvs:
        dv_listing.add(dv["Id"], dv["Name"])

    # Search groups
    groups, gp_more = get_capped(client, "Groups", {
        "$filter": f"substringof('{odata_str(query)}', Name) eq true and GroupTypeId ne {FAMILY_GROUP_TYPE_ID} and GroupTypeId ne {KNOWN_RELATIONSHIPS_GROUP_TYPE_ID}",
        "$select": "Id,Name",
    }, SEARCH_LIMIT)
    gp_listing = Listing("Groups", gp_more, WIDEN, empty="")
    for g in groups:
        gp_listing.add(g["Id"], g["Name"])

    found = [part for part in (wf_listing, pg_listing, dv_listing, gp_listing)
             if part.rows]
    return found or Listing("Results", empty="No results found.")


def _check_email(action, activity, settings, issues):
    prefix = f"Action '{action['Name']}' in '{activity['Name']}'"
    if not settings.get("To") and not settings.get("SendToEmailAddresses"):
        issues.append(f"{prefix}: SendEmail has no recipient")
    if not settings.get("Subject"):
        issues.append(f"{prefix}: SendEmail has no Subject")
    if not settings.get("Body"):
        issues.append(f"{prefix}: SendEmail has no Body")


def _check_sms(action, activity, settings, issues):
    prefix = f"Action '{action['Name']}' in '{activity['Name']}'"
    if not settings.get("To") and not settings.get("Recipient"):
        issues.append(f"{prefix}: SendSms has no recipient")
    if not settings.get("Message") and not settings.get("Body"):
        issues.append(f"{prefix}: SendSms has no message body")


def _audit_report(wf, issues, warnings):
    """What the audit found, as the tree and the two lists an operator reads."""
    lines = [f"Audit: {wf['Name']} (ID: {wf['Id']})",
             f"Status: {'Active' if wf.get('IsActive') else 'Inactive'}", ""]

    activities = sorted(wf.get("ActivityTypes", []), key=lambda a: a.get("Order", 0))
    if activities:
        lines.append("Structure:")
        if wf.get("ActivityTypesCapped"):
            lines.append(f"  (only the first {CHILD_LIMIT} activities are shown)")
        for i, act in enumerate(activities):
            is_last = i == len(activities) - 1
            prefix = "  └─" if is_last else "  ├─"
            activated = " (activated)" if act.get("IsActivatedWithWorkflow") else ""
            actions = sorted(act.get("ActionTypes", []), key=lambda a: a.get("Order", 0))
            count = tally(actions, act.get("ActionTypesCapped"), hint=CHILD_HINT)
            lines.append(f"{prefix} {act['Name']}{activated} [{count} actions]")
            for j, action in enumerate(actions):
                branch = "     " if is_last else "  │  "
                ap = "└─" if j == len(actions) - 1 else "├─"
                entity_name = (action.get("EntityType") or {}).get("FriendlyName", "?")
                lines.append(f"{branch} {ap} {action['Name']} [{entity_name}]")
        lines.append("")

    for title, marker, found in (("Issues", "✗", issues),
                                 ("Warnings", "!", warnings)):
        if found:
            lines.append(f"{title} ({len(found)}):")
            lines.extend(f"  {marker} {item}" for item in found)
            lines.append("")

    if not issues and not warnings:
        lines.append("✓ No issues found")
    return Text("\n".join(lines).rstrip("\n"))


def cmd_audit(args, client):
    wf = _find_entity(client, "WorkflowTypes", args.identifier,
                      label="workflow")
    _load_workflow_tree(wf, client)

    issues = []
    warnings = []

    if not wf.get("IsActive"):
        warnings.append("Workflow is inactive")

    activities = sorted(wf.get("ActivityTypes", []), key=lambda a: a.get("Order", 0))

    if not activities:
        issues.append("Workflow has no activities")
        return _audit_report(wf, issues, warnings)

    if not activities[0].get("IsActivatedWithWorkflow"):
        issues.append(f"First activity '{activities[0]['Name']}' is not activated with workflow")

    act_orders = [a.get("Order", 0) for a in activities]
    if len(act_orders) != len(set(act_orders)):
        issues.append(f"Duplicate activity orders: {act_orders}")

    reachable = set()
    for act in activities:
        if act.get("IsActivatedWithWorkflow"):
            reachable.add(str(act["Id"]))

    for act in activities:
        actions = _by_order(act.get("ActionTypes", []))

        if not actions:
            issues.append(f"Activity '{act['Name']}' (ID: {act['Id']}) has no actions")
            continue

        action_orders = [a.get("Order", 0) for a in actions]
        if len(action_orders) != len(set(action_orders)):
            issues.append(f"Duplicate action orders in '{act['Name']}': {action_orders}")

        for i, action in enumerate(actions):
            entity = action.get("EntityType") or {}
            entity_name = entity.get("FriendlyName", "")

            if not action.get("EntityTypeId") and not entity_name:
                issues.append(
                    f"Action '{action['Name']}' in '{act['Name']}' has no action type (broken reference)"
                )
                continue

            if action.get("IsActivityCompletedOnSuccess") and i < len(actions) - 1:
                warnings.append(
                    f"Action '{action['Name']}' completes activity but isn't last in '{act['Name']}'"
                )

            settings = None

            if entity_name and "activate" in entity_name.lower():
                settings = _get_action_settings(client, action["Id"])
                if settings:
                    for key in ("Activity", "ActivityType", "ActivityTypeGuid"):
                        val = settings.get(key, "")
                        if val:
                            reachable.add(str(val))

            if not args.skip_settings and entity_name:
                name_lower = entity_name.lower().replace(" ", "")
                if "sendemail" in name_lower or "sendsms" in name_lower:
                    if settings is None:
                        settings = _get_action_settings(client, action["Id"])
                    if settings is not None:
                        if "sendemail" in name_lower:
                            _check_email(action, act, settings, issues)
                        else:
                            _check_sms(action, act, settings, issues)

    for act in activities:
        if str(act["Id"]) not in reachable and not act.get("IsActivatedWithWorkflow"):
            warnings.append(f"Activity '{act['Name']}' (ID: {act['Id']}) may be unreachable")

    return _audit_report(wf, issues, warnings)


def cmd_actions(args, client):
    act_id = int(args.activity_id)

    act = client.get(f"WorkflowActivityTypes/{act_id}")
    if not act:
        return Text(f"Activity {act_id} not found")

    actions, actions_capped = get_capped(client, "WorkflowActionTypes", {
        "$filter": f"ActivityTypeId eq {act_id}",
        "$orderby": "Order",
    }, CHILD_LIMIT)
    _enrich_actions_entity_types(actions, client)

    detail = Detail(f"Activity: {act['Name']} (ID: {act['Id']})")
    detail.field("Activated with workflow",
                 act.get("IsActivatedWithWorkflow", False))
    detail.field("Actions", tally(actions, actions_capped, hint=CHILD_HINT))

    for action in actions:
        entity = action.get("EntityType") or {}
        detail.line(f"[{action.get('Order', '?')}] {action['Name']} "
                    f"(ID: {action['Id']})")
        detail.line(f"Type: {entity.get('FriendlyName', '?')}", depth=1)
        detail.line(f"Completes action: "
                    f"{action.get('IsActionCompletedOnSuccess', False)}", depth=1)
        detail.line(f"Completes activity: "
                    f"{action.get('IsActivityCompletedOnSuccess', False)}", depth=1)
        settings = _get_action_settings(client, action["Id"])
        if settings:
            detail.line("Settings:", depth=1)
            for k, v in settings.items():
                val = str(v)[:120] + ("..." if len(str(v)) > 120 else "")
                detail.line(f"{k}: {val}", depth=2)
    return detail


def cmd_attributes(args, client):
    wf = _find_entity(client, "WorkflowTypes", args.identifier,
                      label="workflow")

    attrs, attrs_capped = get_capped(client, "Attributes", {
        "$filter": f"EntityTypeQualifierColumn eq 'WorkflowTypeId' and EntityTypeQualifierValue eq '{wf['Id']}'",
        "$orderby": "Order",
    }, CHILD_LIMIT)

    if not attrs:
        return Text(f"No attributes on '{wf['Name']}' (ID: {wf['Id']})")

    # Resolve field type names
    ft_ids = {a.get("FieldTypeId") for a in attrs if a.get("FieldTypeId")}
    ft_names = {fid: _resolve_name(client, "FieldTypes", fid) for fid in ft_ids}

    detail = Detail(f"Attributes on '{wf['Name']}' (ID: {wf['Id']}, "
                    f"{tally(attrs, attrs_capped, hint=CHILD_HINT)}):")
    for attr in attrs:
        ft = ft_names.get(attr.get("FieldTypeId"), "?")
        req = " [required]" if attr.get("IsRequired") else ""
        grid = " [grid]" if attr.get("IsGridColumn") else ""
        detail.line(f"{attr.get('Order', '?'):3}  {attr['Key']} ({ft}){req}{grid}")
        # Two steps in, so a description cannot be misread as the next attribute.
        detail.line((attr.get("Description") or "")[:100], depth=2)
    return detail


def cmd_dataviews(args, client):
    params = {
        "$select": "Id,Name,Description,EntityTypeId,CategoryId",
        "$orderby": "Name",
    }
    if args.category:
        params["$filter"] = f"substringof('{odata_str(args.category)}', Name) eq true"

    dvs, more = get_capped(client, "DataViews", params, args.limit)

    listing = Listing("Data Views", more)
    for dv in dvs:
        listing.add(dv["Id"], dv["Name"])
    return listing


def _load_filter_tree(client, filter_id, depth=0):
    """Recursively load a data view filter and its children."""
    f = client.get(f"DataViewFilters/{filter_id}")
    if not f:
        return None

    entity_name = _resolve_name(client, "EntityTypes", f.get("EntityTypeId"),
                                field="FriendlyName")
    prefix = "  " * depth
    expr = EXPRESSION_TYPES.get(f.get("ExpressionType", 0), f"Type:{f.get('ExpressionType')}")

    lines = []
    if f.get("ExpressionType", 0) in (1, 2, 3, 4):
        lines.append(f"{prefix}[{expr}]")
    else:
        selection = f.get("Selection", "") or ""
        sel_short = selection[:120] + ("..." if len(selection) > 120 else "")
        related_dv = f.get("RelatedDataViewId")
        dv_note = f" (references DataView:{related_dv})" if related_dv else ""
        lines.append(f"{prefix}Filter [{entity_name}]: {sel_short}{dv_note}")

    children, children_capped = get_capped(client, "DataViewFilters", {
        "$filter": f"ParentId eq {filter_id}",
        "$select": "Id",
    }, CHILD_LIMIT)
    if children_capped:
        lines.append(f"{prefix}(only the first {CHILD_LIMIT} child filters are shown)")
    for child in children:
        child_lines = _load_filter_tree(client, child["Id"], depth + 1)
        if child_lines:
            lines.extend(child_lines)

    return lines


def cmd_dataview(args, client):
    dv = _find_entity(client, "DataViews", args.identifier, label="data view")
    if args.json:
        return Raw(dv)

    detail = Detail(f"{dv['Name']} (ID: {dv['Id']})")
    detail.line((dv.get("Description") or "")[:200])
    detail.field("Entity", _resolve_name(client, "EntityTypes",
                                        dv.get("EntityTypeId"),
                                        field="FriendlyName"))
    if dv.get("TransformEntityTypeId"):
        detail.field("Transform", _resolve_name(
            client, "EntityTypes", dv["TransformEntityTypeId"],
            field="FriendlyName"))
    if dv.get("CategoryId"):
        cat_name = _resolve_name(client, "Categories", dv["CategoryId"])
        if cat_name != "?":
            detail.field("Category", cat_name)

    persisted = dv.get("PersistedScheduleIntervalMinutes")
    if persisted:
        detail.field("Persisted", f"every {persisted} min (last: "
                                  f"{dv.get('PersistedLastRefreshDateTime', 'never')})")
    detail.field("Last run", f"{dv.get('LastRunDateTime', 'never')} "
                             f"({dv.get('TimeToRunDurationMilliseconds', 0)}ms)")

    filter_id = dv.get("DataViewFilterId")
    if filter_id:
        # The tree indents itself from zero and the section indents it once, so
        # the root filter lands where a section line lands and each child sits
        # one step further in.
        filters = detail.section("Filters")
        for line in _load_filter_tree(client, filter_id) or []:
            filters.add(line)
    return detail


def cmd_person(args, client):
    identifier = args.identifier

    person = None
    try:
        pid = int(identifier)
        person = client.get(f"People/{pid}")
        if person:
            return _person_detail(person, client)
    except (ValueError, RockNotFound):
        pass

    results, more = get_capped(client, "People",
                               {"$filter": _people_filter(identifier)},
                               SEARCH_LIMIT)

    if not results:
        raise LookupMiss(Text(f"No person found matching '{identifier}'"))

    if len(results) == 1:
        return _person_detail(results[0], client)

    # More than one match is a chooser, so it is a listing like any other, and
    # the same miss the shared ladder raises. The count is new: this branch
    # printed a header with no number in it, and a dropped candidate reads as a
    # person who does not exist.
    listing = Listing(f"People matching '{identifier}'", more,
                      hint=CHOOSER_HINT)
    campus_cache = {}
    for p in results:
        email = f" ({p.get('Email', '')})" if p.get("Email") else ""
        campus = ""
        if p.get("PrimaryCampusId"):
            cid = p["PrimaryCampusId"]
            if cid not in campus_cache:
                campus_cache[cid] = _resolve_name(client, "Campuses", cid)
            if campus_cache[cid] != "?":
                campus = f" [{campus_cache[cid]}]"
        listing.add(p["Id"], f"{p.get('FirstName', '')} {p.get('LastName', '')}"
                             f"{email}{campus}")
    raise LookupMiss(listing)


def _person_detail(person, client):
    """One person: their own fields, their family, and who they are tied to."""
    detail = Detail(f"{person.get('FirstName', '')} {person.get('LastName', '')} "
                    f"(ID: {person['Id']})")
    detail.field("Email", person.get("Email"))
    if person.get("Gender"):
        detail.field("Gender", GENDERS.get(person["Gender"], "Unknown"))
    if person.get("BirthDate"):
        detail.field("DOB", person["BirthDate"][:10])

    # Three fields Rock stores as an id somewhere else. Each was its own block
    # of lookup, compare against "?", print -- the same block three times.
    for label, key, endpoint, name_field in (
            ("Connection Status", "ConnectionStatusValueId", "DefinedValues", "Value"),
            ("Record Status", "RecordStatusValueId", "DefinedValues", "Value"),
            ("Campus", "PrimaryCampusId", "Campuses", "Name")):
        if person.get(key):
            resolved = _resolve_name(client, endpoint, person[key], field=name_field)
            if resolved != "?":
                detail.field(label, resolved)

    role_cache = {}
    try:
        families = client.get(f"Groups/GetFamilies/{person['Id']}")
        for fam in families or []:
            members, members_capped = get_capped(client, "GroupMembers", {
                "$filter": f"GroupId eq {fam['Id']}",
                "$select": "PersonId,GroupRoleId",
            }, CHILD_LIMIT)
            roles = {}
            for m in members:
                rid = m["GroupRoleId"]
                if rid not in role_cache:
                    role_cache[rid] = _resolve_name(client, "GroupTypeRoles", rid)
                roles[m["PersonId"]] = role_cache[rid]
            capped = f" (first {CHILD_LIMIT})" if members_capped else ""
            detail.field("Family", f"{fam['Name']} (ID: {fam['Id']}){capped}")
            for m in members:
                if m["PersonId"] == person["Id"]:
                    continue
                try:
                    p = client.get(f"People/{m['PersonId']}",
                                   params={"$select": "FirstName,LastName"})
                    if p:
                        detail.line(f"{roles.get(m['PersonId'], '?'):10s} "
                                    f"{p['FirstName']} {p['LastName']}", depth=1)
                except Exception as _e:
                    log.debug("lookup failed: %s", _e)
    except Exception as _e:
        log.debug("lookup failed: %s", _e)

    try:
        rel_group = first(client, "Groups", {
            "$filter": f"GroupTypeId eq {KNOWN_RELATIONSHIPS_GROUP_TYPE_ID} and Members/any(m: m/PersonId eq {person['Id']})",
            "$select": "Id",
        })
        if rel_group:
            members, members_capped = get_capped(client, "GroupMembers", {
                "$filter": f"GroupId eq {rel_group['Id']} and PersonId ne {person['Id']}",
                "$select": "PersonId,GroupRoleId",
            }, CHILD_LIMIT)
            related = detail.section("Known Relationships", members,
                                     members_capped, hint=CHILD_HINT)
            for m in members:
                try:
                    p = client.get(f"People/{m['PersonId']}",
                                   params={"$select": "FirstName,LastName"})
                    pname = f"{p['FirstName']} {p['LastName']}" if p else f"Person:{m['PersonId']}"
                    rid = m["GroupRoleId"]
                    if rid not in role_cache:
                        role_cache[rid] = _resolve_name(client, "GroupTypeRoles", rid)
                    related.add(f"{role_cache[rid]:20s} {pname}")
                except Exception as _e:
                    log.debug("lookup failed: %s", _e)
    except Exception as _e:
        log.debug("lookup failed: %s", _e)

    return detail


def cmd_group(args, client):
    group = _find_entity(client, "Groups", args.identifier, label="group")
    if args.json:
        return Raw(group)

    detail = Detail(f"{group['Name']} (ID: {group['Id']})")
    detail.line((group.get("Description") or "")[:200])
    if group.get("GroupTypeId"):
        gt_name = _resolve_name(client, "GroupTypes", group["GroupTypeId"])
        if gt_name != "?":
            detail.field("Type", gt_name)
    detail.field("Active", group.get("IsActive", False))
    for label, key, endpoint in (("Campus", "CampusId", "Campuses"),
                                 ("Schedule", "ScheduleId", "Schedules")):
        if group.get(key):
            resolved = _resolve_name(client, endpoint, group[key])
            if resolved != "?":
                detail.field(label, resolved)

    members, mem_more = get_capped(client, "GroupMembers", {
        "$filter": f"GroupId eq {group['Id']}",
        "$select": "PersonId,GroupRoleId,GroupMemberStatus",
    }, args.limit)
    roster = detail.section("Members", members, mem_more)
    role_cache = {}
    for m in members:
        rid = m.get("GroupRoleId")
        if rid not in role_cache:
            role_cache[rid] = _resolve_name(client, "GroupTypeRoles", rid)
        try:
            p = client.get(f"People/{m['PersonId']}",
                           params={"$select": "FirstName,LastName"})
            pname = f"{p['FirstName']} {p['LastName']}" if p else f"ID:{m['PersonId']}"
        except Exception as _e:
            log.debug("person lookup failed: %s", _e)
            pname = f"ID:{m['PersonId']}"
        status = GROUP_MEMBER_STATUSES.get(m.get("GroupMemberStatus"), "?")
        roster.add(f"{pname:30s} {role_cache[rid]:15s} [{status}]")
    return detail


def cmd_report(args, client):
    report = _find_entity(client, "Reports", args.identifier, label="report")
    if args.json:
        return Raw(report)

    detail = Detail(f"{report['Name']} (ID: {report['Id']})")
    detail.line((report.get("Description") or "")[:200])

    if report.get("DataViewId"):
        dv_name = _resolve_name(client, "DataViews", report["DataViewId"])
        if dv_name != "?":
            detail.field("Data View", f"{dv_name} (ID: {report['DataViewId']})")
        else:
            detail.field("Data View ID", report["DataViewId"])

    if report.get("CategoryId"):
        cat_name = _resolve_name(client, "Categories", report["CategoryId"])
        if cat_name != "?":
            detail.field("Category", cat_name)

    fields, fields_capped = get_capped(client, "ReportFields", {
        "$filter": f"ReportId eq {report['Id']}",
        "$select": "ReportFieldType,ShowInGrid,ColumnOrder,ColumnHeaderText,DataSelectComponentEntityTypeId",
    }, CHILD_LIMIT)
    columns = detail.section("Fields", fields, fields_capped, hint=CHILD_HINT)
    for f in sorted(fields, key=lambda x: x.get("ColumnOrder", 0)):
        header = f.get("ColumnHeaderText", "") or "(no header)"
        columns.add(f"{f.get('ColumnOrder', '?'):3}  {header}")
    return detail


def _short_type(exception_type):
    """`System.NullReferenceException` reads as `NullReferenceException`."""
    return exception_type.split(".")[-1] if "." in exception_type else exception_type


def cmd_exceptions(args, client):
    params = {"$orderby": "CreatedDateTime desc"}
    if args.type:
        params["$filter"] = f"substringof('{odata_str(args.type)}', ExceptionType) eq true"

    exceptions, more = get_capped(client, "ExceptionLogs", params, args.limit)

    if args.summary:
        if not exceptions:
            return Text("No exceptions found.")
        counts = {}
        for ex in exceptions:
            short = _short_type(ex.get("ExceptionType", "Unknown"))
            counts[short] = counts.get(short, 0) + 1
        # The counts below are over the rows fetched, not over the log. Saying
        # "last 50" made that sound deliberate; it was the cap.
        window = f"{len(exceptions)} most recent" + (" of more" if more else "")
        summary = Detail(f"Exception summary ({window}):")
        for etype, count in sorted(counts.items(), key=lambda x: -x[1]):
            summary.line(f"{count:4d}  {etype}")
        return summary

    listing = Listing("Exceptions", more, spaced=True)
    for ex in exceptions:
        dt = (ex.get("CreatedDateTime") or "")[:19]
        desc = (ex.get("Description") or "")[:120]
        url = ex.get("PageUrl", "")
        trace = ex["StackTrace"].split("\n")[:5] if (
            args.verbose and ex.get("StackTrace")) else []
        listing.add(ex["Id"], f"[{dt}] {_short_type(ex.get('ExceptionType', 'Unknown'))}",
                    desc, f"URL: {url}" if url else "",
                    *(line.strip() for line in trace))
    return listing


def cmd_exception(args, client):
    ex = client.get(f"ExceptionLogs/{args.id}")
    if not ex:
        return Text(f"Exception {args.id} not found")

    if args.json:
        return Raw(ex)

    dt = (ex.get("CreatedDateTime") or "")[:19]
    detail = Detail(f"Exception {ex['Id']} ({dt})")
    detail.field("Type", ex.get("ExceptionType", "Unknown"))
    detail.field("HTTP Status", ex.get("StatusCode"))
    detail.field("Source", ex.get("Source"))
    detail.field("Description", ex.get("Description"))
    detail.field("URL", ex.get("PageUrl"))

    if ex.get("StackTrace"):
        trace = detail.section("Stack Trace")
        for line in ex["StackTrace"].split("\n")[:15]:
            trace.add(line.strip())

    if ex.get("HasInnerException") and ex.get("Id"):
        inner = first(client, "ExceptionLogs", {
            "$filter": f"ParentId eq {ex['Id']}",
        })
        if inner:
            detail.field("Inner Exception", inner.get("ExceptionType", "?"))
            detail.line((inner.get("Description") or "")[:200], depth=1)
    return detail


def cmd_schedules(args, client):
    params = {
        "$select": "Id,Name,IsActive",
        "$orderby": "Name",
    }
    filters = []
    if args.active:
        filters.append("IsActive eq true")
    if args.query:
        filters.append(f"substringof('{odata_str(args.query)}', Name) eq true")
    if filters:
        params["$filter"] = " and ".join(filters)

    schedules, more = get_capped(client, "Schedules", params, args.limit)

    listing = Listing("Schedules", more)
    for s in schedules:
        active = _inactive(s)
        listing.add(s["Id"], f"{s['Name']}{active}")
    return listing


def cmd_schedule(args, client):
    schedule = _find_entity(client, "Schedules", args.identifier, label="schedule")
    if args.json:
        return Raw(schedule)

    detail = Detail(f"{schedule['Name']} (ID: {schedule['Id']})")
    detail.field("Active", schedule.get("IsActive", False))
    detail.field("Description", (schedule.get("Description") or "")[:200])
    for label, key in (("Start", "EffectiveStartDate"), ("End", "EffectiveEndDate")):
        if schedule.get(key):
            detail.field(label, schedule[key][:10])
    if schedule.get("CheckInStartOffsetMinutes"):
        detail.field("Check-in window",
                     f"-{schedule['CheckInStartOffsetMinutes']}min to "
                     f"+{schedule.get('CheckInEndOffsetMinutes', 0)}min")
    if schedule.get("CategoryId"):
        cat_name = _resolve_name(client, "Categories", schedule["CategoryId"])
        if cat_name != "?":
            detail.field("Category", cat_name)
    return detail


def cmd_registrations(args, client):
    params = {
        "$select": "Id,Name,StartDateTime,EndDateTime,MaxAttendees,IsActive,RegistrationTemplateId",
        "$orderby": "StartDateTime desc",
    }
    filters = []
    if args.active:
        filters.append("IsActive eq true")
    if args.query:
        filters.append(f"substringof('{odata_str(args.query)}', Name) eq true")
    if filters:
        params["$filter"] = " and ".join(filters)

    regs, more = get_capped(client, "RegistrationInstances", params, args.limit)

    listing = Listing("Registration Instances", more)
    for r in regs:
        active = _inactive(r)
        start = (r.get("StartDateTime") or "")[:10]
        end = (r.get("EndDateTime") or "")[:10]
        date_range = f" ({start} to {end})" if start else ""
        max_att = f" [max: {r['MaxAttendees']}]" if r.get("MaxAttendees") else ""
        listing.add(r["Id"], f"{r['Name']}{active}{date_range}{max_att}")
    return listing


def cmd_registration(args, client):
    reg = _find_entity(client, "RegistrationInstances", args.identifier, label="registration")
    if args.json:
        return Raw(reg)

    detail = Detail(f"{reg['Name']} (ID: {reg['Id']})")
    detail.field("Active", reg.get("IsActive", False))
    for label, key in (("Start", "StartDateTime"), ("End", "EndDateTime")):
        if reg.get(key):
            detail.field(label, reg[key][:19])
    detail.field("Max Attendees", reg.get("MaxAttendees"))
    if reg.get("Cost"):
        detail.field("Cost", f"${reg['Cost']}")
    detail.field("Contact", reg.get("ContactEmail"))

    if reg.get("RegistrationTemplateId"):
        tmpl_name = _resolve_name(client, "RegistrationTemplates",
                                  reg["RegistrationTemplateId"])
        if tmpl_name != "?":
            detail.field("Template",
                         f"{tmpl_name} (ID: {reg['RegistrationTemplateId']})")
        else:
            detail.field("Template ID", reg["RegistrationTemplateId"])

    if reg.get("RegistrationWorkflowTypeId"):
        wf_name = _resolve_name(client, "WorkflowTypes",
                               reg["RegistrationWorkflowTypeId"])
        if wf_name != "?":
            detail.field("Workflow",
                         f"{wf_name} (ID: {reg['RegistrationWorkflowTypeId']})")

    detail.field("Details", (reg.get("Details") or "")[:200])
    return detail


def cmd_connections(args, client):
    params = {
        "$orderby": "CreatedDateTime desc",
    }
    filters = []
    if args.state and args.state.lower() in CONNECTION_STATE_FILTER:
        filters.append(f"ConnectionState eq {CONNECTION_STATE_FILTER[args.state.lower()]}")
    if args.opportunity:
        filters.append(f"substringof('{odata_str(args.opportunity)}', ConnectionOpportunity/Name) eq true")
    if filters:
        params["$filter"] = " and ".join(filters)

    requests, more = get_capped(client, "ConnectionRequests", params, args.limit)

    opp_cache = {}
    status_cache = {}
    person_cache = {}

    listing = Listing("Connection Requests", more, spaced=True)
    for cr in requests:
        dt = (cr.get("CreatedDateTime") or "")[:10]
        person = _resolve_person_name(client, cr.get("PersonAliasId"), person_cache)
        connector = _resolve_person_name(client, cr.get("ConnectorPersonAliasId"), person_cache) if cr.get("ConnectorPersonAliasId") else "unassigned"
        state = CONNECTION_STATES.get(cr.get("ConnectionState"), "?")

        opp_id = cr.get("ConnectionOpportunityId")
        if opp_id and opp_id not in opp_cache:
            opp_cache[opp_id] = _resolve_name(client, "ConnectionOpportunities", opp_id)
        opp_name = opp_cache.get(opp_id, "?")

        status_id = cr.get("ConnectionStatusId")
        if status_id and status_id not in status_cache:
            status_cache[status_id] = _resolve_name(client, "ConnectionStatuses", status_id)
        status_name = status_cache.get(status_id, "?")

        listing.add(cr["Id"], f"[{state:9s}] {person:25s} -> {connector}",
                    f"{opp_name} | {status_name} | {dt}",
                    (cr.get("Comments") or "")[:100])
    return listing


def cmd_block(args, client):
    block_id = int(args.id)
    block = client.get(f"Blocks/{block_id}", params={"loadAttributes": "simple"})
    if not block:
        return Text(f"Block {block_id} not found")

    if args.json:
        return Raw(block)

    detail = Detail(f"{block.get('Name', '(unnamed)')} (ID: {block['Id']})")
    if block.get("BlockTypeId"):
        bt_name = _resolve_name(client, "BlockTypes", block["BlockTypeId"])
        if bt_name != "?":
            detail.field("Block Type", bt_name)
    detail.field("Zone", block.get("Zone", "?"))
    detail.field("Order", block.get("Order", "?"))
    detail.field("Page ID", block.get("PageId"))

    avs = block.get("AttributeValues", {})
    settings = detail.section("Attributes", avs)
    for key, val in avs.items():
        v = val.get("Value", "") if isinstance(val, dict) else (str(val) if val else "")
        if not v:
            continue
        # Truncate long values but show more for HTML/Lava
        max_len = 300 if key.lower() in ("query", "formattedoutput", "template",
                                         "lavatemplate") else 150
        settings.add(f"{key}: {v[:max_len]}" + ("..." if len(v) > max_len else ""))
    return detail


def cmd_bgc(args, client):
    params = {
        "$orderby": "RequestDate desc",
    }
    filters = []
    if args.status:
        filters.append(f"substringof('{odata_str(args.status)}', Status) eq true")
    if args.person:
        # Find person first
        try:
            pid = int(args.person)
            alias = first(client, "PersonAlias", {
                "$filter": f"PersonId eq {pid}", "$select": "Id",
            })
            if alias:
                filters.append(f"PersonAliasId eq {alias['Id']}")
        except (ValueError, RockNotFound):
            person = first(client, "People", {
                "$filter": _people_filter(args.person), "$select": "Id",
            })
            if person:
                alias = first(client, "PersonAlias", {
                    "$filter": f"PersonId eq {person['Id']}", "$select": "Id",
                })
                if alias:
                    filters.append(f"PersonAliasId eq {alias['Id']}")
    if filters:
        params["$filter"] = " and ".join(filters)

    checks, more = get_capped(client, "BackgroundChecks", params, args.limit)

    person_cache = {}

    listing = Listing("Background Checks", more)
    for bc in checks:
        req_date = (bc.get("RequestDate") or "")[:10]
        resp_date = (bc.get("ResponseDate") or "")[:10]
        person = _resolve_person_name(client, bc.get("PersonAliasId"), person_cache)
        status = bc.get("Status", "?")
        found = " [RECORD FOUND]" if bc.get("RecordFound") else ""
        pkg = bc.get("PackageName", "")
        pkg_str = f" ({pkg})" if pkg else ""

        listing.add(bc["Id"], f"{person:25s} [{status}]{found}{pkg_str}",
                    f"Requested: {req_date}  "
                    f"Responded: {resp_date or 'pending'}")
    return listing


def _checkin_area(args, client, checkin_group_types):
    """One check-in area, with the locations and sub-areas under it.

    The group type restriction belongs in the query rather than after it.
    Filtering afterwards spent the cap on rows that were about to be discarded:
    a common word can match hundreds of groups of every type, and if no check-in
    group landed in the first ten the command answered "No check-in area found"
    for areas that plainly exist.
    """
    checkin_type_ids = sorted(gt["Id"] for gt in checkin_group_types)

    def among_checkin_types(odata_filter, limit):
        if not checkin_type_ids:
            return get_capped(client, "Groups", {"$filter": odata_filter,
                                                 "$select": "Id,Name"}, limit)
        return groups_of_types(client, odata_filter, checkin_type_ids, limit)

    group = _find_entity(client, "Groups", args.area, label="check-in area",
                         search=among_checkin_types)
    detail = Detail(f"{group['Name']} (ID: {group['Id']})")
    detail.field("Active", group.get("IsActive", False))

    group_locs, locs_capped = get_capped(client, "GroupLocations", {
        "$filter": f"GroupId eq {group['Id']}",
        "$select": "LocationId",
    }, CHILD_LIMIT)
    places = detail.section("Locations", group_locs, locs_capped, hint=CHILD_HINT)
    for gl in group_locs:
        loc_name = _resolve_name(client, "Locations", gl["LocationId"])
        if loc_name != "?":
            places.add(f"{loc_name} (ID: {gl['LocationId']})")
        else:
            places.add(f"Location ID: {gl['LocationId']}")

    children, children_capped = get_capped(client, "Groups", {
        "$filter": f"ParentGroupId eq {group['Id']}",
        "$select": "Id,Name,IsActive",
        "$orderby": "Order",
    }, CHILD_LIMIT)
    sub = detail.section("Sub-areas", children, children_capped, hint=CHILD_HINT)
    for child in children:
        sub.row(child["Id"], f"{child['Name']}{_inactive(child)}")
    return detail


def cmd_checkin(args, client):
    # Check-in areas are GroupTypes with a specific purpose.
    # A production instance matched half again as many types as the 20 that used
    # to be asked for, and what got dropped were whole check-in areas no
    # subcommand could then see. CHILD_LIMIT sits far past that number, and the
    # line below says so if it ever binds.
    checkin_group_types, types_capped = get_capped(client, "GroupTypes", {
        "$filter": "substringof('Check', Name) eq true",
        "$select": "Id,Name",
        "$orderby": "Name",
    }, CHILD_LIMIT)

    if args.area:
        return _checkin_area(args, client, checkin_group_types)

    if not checkin_group_types:
        return Text("No check-in group types found.")

    # The hierarchy is three levels deep with a cap note possible at each, which
    # is a tree rather than a heading with fields under it. It builds its lines
    # and returns them, the way the workflow tree and the audit do.
    lines = ["Check-in Configuration:", ""]
    if types_capped:
        lines.append(f"  (only the first {CHILD_LIMIT} check-in group types are shown)")
        lines.append("")
    for gt in checkin_group_types:
        lines.append(f"  Group Type: {gt['Name']} (ID: {gt['Id']})")
        top_groups, top_capped = get_capped(client, "Groups", {
            "$filter": f"GroupTypeId eq {gt['Id']} and ParentGroupId eq null",
            "$select": "Id,Name,IsActive",
            "$orderby": "Order",
        }, CHILD_LIMIT)
        if top_capped:
            lines.append(f"    (only the first {CHILD_LIMIT} are shown)")
        for g in top_groups:
            lines.append(row(g["Id"], f"{g['Name']}{_inactive(g)}", indent=4))
            children, children_capped = get_capped(client, "Groups", {
                "$filter": f"ParentGroupId eq {g['Id']}",
                "$select": "Id,Name,IsActive",
                "$orderby": "Order",
            }, CHILD_LIMIT)
            if children_capped:
                lines.append(f"      (only the first {CHILD_LIMIT} are shown)")
            for child in children:
                lines.append(row(child["Id"],
                                 f"{child['Name']}{_inactive(child)}", indent=6))
        lines.append("")
    return Text("\n".join(lines).rstrip("\n"))


def cmd_attendance(args, client):
    params = {
        "$orderby": "OccurrenceDate desc",
    }
    filters = []
    if args.group:
        group = _find_entity(client, "Groups", args.group, label="group")
        filters.append(f"GroupId eq {group['Id']}")
    if args.date:
        filters.append(f"OccurrenceDate eq datetime'{args.date}'")
    if filters:
        params["$filter"] = " and ".join(filters)

    occurrences, more = get_capped(client, "AttendanceOccurrences", params,
                                   args.limit)

    group_cache = {}
    location_cache = {}

    listing = Listing("Attendance Occurrences", more)
    for occ in occurrences:
        occ_date = (occ.get("OccurrenceDate") or "")[:10]

        gid = occ.get("GroupId")
        if gid and gid not in group_cache:
            group_cache[gid] = _resolve_name(client, "Groups", gid)
        group_name = group_cache.get(gid, "?")

        lid = occ.get("LocationId")
        if lid and lid not in location_cache:
            location_cache[lid] = _resolve_name(client, "Locations", lid)
        loc_name = location_cache.get(lid, "")

        did_not = " [DID NOT OCCUR]" if occ.get("DidNotOccur") else ""
        loc_str = f" @ {loc_name}" if loc_name else ""

        listing.add(occ["Id"], f"{occ_date}  {group_name}{loc_str}{did_not}")
    return listing


def cmd_occurrence(args, client):
    occ = client.get(f"AttendanceOccurrences/{args.id}")
    if not occ:
        return Text(f"Occurrence {args.id} not found")

    if args.json:
        return Raw(occ)

    occ_date = (occ.get("OccurrenceDate") or "")[:10]
    detail = Detail(f"Occurrence {occ['Id']} ({occ_date})")

    for label, endpoint, key in (("Group", "Groups", "GroupId"),
                                 ("Location", "Locations", "LocationId"),
                                 ("Schedule", "Schedules", "ScheduleId")):
        if occ.get(key):
            name = _resolve_name(client, endpoint, occ[key])
            if name != "?":
                detail.field(label, f"{name} (ID: {occ[key]})")
            else:
                detail.field(f"{label} ID", occ[key])

    if occ.get("DidNotOccur"):
        detail.field("Status", "DID NOT OCCUR")

    attendees, att_more = get_capped(client, "Attendances", {
        "$filter": f"OccurrenceId eq {occ['Id']}",
        "$select": "PersonAliasId,DidAttend,StartDateTime,RSVP",
    }, args.limit)

    if attendees:
        # "N total" from a capped fetch misstates the attendance rate itself,
        # not just the list length, so say plainly when the roll is cut short.
        did_attend = sum(1 for a in attendees if a.get("DidAttend"))
        cut = " — more exist, raise --limit" if att_more else ""
        detail.field("Attendees",
                     f"{did_attend} attended / {len(attendees)} total{cut}")
        if args.names:
            person_cache = {}
            for a in attendees:
                pname = _resolve_person_name(client, a.get("PersonAliasId"),
                                             person_cache)
                attended = "Y" if a.get("DidAttend") else "N"
                rsvp = f" RSVP:{a['RSVP']}" if a.get("RSVP") else ""
                detail.line(f"{pname:30s} [{attended}]{rsvp}", depth=1)
    return detail


def cmd_block_set(args, client):
    block_id = int(args.id)
    block = client.get(f"Blocks/{block_id}")
    if not block:
        print(f"Block {block_id} not found")
        sys.exit(1)

    print(f"Setting {args.key}={args.value[:80]}{'...' if len(args.value) > 80 else ''} on block {block_id}")

    # Rock routes this by convention rather than through OData, and binds both
    # arguments from the query string. The two shapes this replaced — a JSON
    # body to Blocks/{id}/AttributeValues, then to Blocks/AttributeValue/{id} —
    # are not routes at all: both answer "The OData path is invalid." So
    # block-set had never once changed a block setting, and said "Done." only
    # when the second 404 was also swallowed.
    try:
        client.set_attribute_value("Blocks", block_id, args.key, args.value)
        log.info("block-set ok block=%d key=%s", block_id, args.key)
        print("Done.")
    except Exception as e:
        log.error("block-set failed block=%d key=%s\n%s", block_id, args.key, traceback.format_exc())
        print(f"Error setting attribute: {e}")
        print(f"  Rock rejects a key it does not know. Check it against: "
              f"rock.sh query block {block_id}")
        # Exit non-zero. The caller is a skill reporting what it changed, and a
        # setting that did not land must not read as one that did -- the whole
        # fault this command was fixed for.
        sys.exit(1)


def cmd_person_create(args, client):
    data = {
        "FirstName": args.first,
        "LastName": args.last,
        "IsSystem": False,
    }
    if args.email:
        data["Email"] = args.email
    if args.connection_status:
        data["ConnectionStatusValueId"] = int(args.connection_status)
    if args.record_status:
        data["RecordStatusValueId"] = int(args.record_status)
    if args.campus:
        data["CampusId"] = int(args.campus)

    try:
        pid = client.post("People", data)
        print(f"Created person: {args.first} {args.last} (ID: {pid})")
    except Exception as e:
        print(f"Error creating person: {e}")


def cmd_person_update(args, client):
    pid = int(args.id)
    person = client.get(f"People/{pid}")
    if not person:
        print(f"Person {pid} not found")
        return

    field_map = {
        "firstname": "FirstName", "lastname": "LastName", "email": "Email",
        "nickname": "NickName", "campus": "CampusId",
        "connectionstatus": "ConnectionStatusValueId",
        "recordstatus": "RecordStatusValueId",
        "maritalstatus": "MaritalStatusValueId",
        "birthdate": "BirthDate", "gender": "Gender",
    }

    data = {}
    for kv in args.fields:
        if "=" not in kv:
            print(f"Invalid field format: {kv} (expected key=value)")
            return
        key, value = kv.split("=", 1)
        mapped = field_map.get(key.lower(), key)
        data[mapped] = value

    if not data:
        print("No fields to update.")
        return

    # PATCH, not PUT. Rock's PUT replaces the whole person record, so a
    # three-field update used to null everything else on the row, wipe who
    # created it, and hand it a new Guid. See RockClient.put.
    try:
        client.patch(f"People/{pid}", data)
        pname = f"{person.get('FirstName', '')} {person.get('LastName', '')}"
        print(f"Updated {pname} (ID: {pid}): {', '.join(f'{k}={v}' for k, v in data.items())}")
    except Exception as e:
        print(f"Error updating person: {e}")


def cmd_exception_clear(args, client):
    params = {"$select": "Id", "$orderby": "CreatedDateTime asc"}
    filters = []
    if args.before:
        filters.append(f"CreatedDateTime lt datetime'{args.before}T00:00:00'")
    if args.type:
        filters.append(f"substringof('{odata_str(args.type)}', ExceptionType) eq true")
    if filters:
        params["$filter"] = " and ".join(filters)

    exceptions, more = get_capped(client, "ExceptionLogs", params, args.limit)
    if not exceptions:
        print("No exceptions matching criteria.")
        return

    # `--limit` bounds one run. Without this line a caller reads "Deleting 500"
    # and a clean log; what they have is 500 fewer and no idea how many are left.
    print(f"Deleting {len(exceptions)} exception logs..."
          + (f" More than {args.limit} match, so run this again." if more else ""))
    deleted = 0
    errors = 0
    for ex in exceptions:
        try:
            client.delete(f"ExceptionLogs/{ex['Id']}")
            deleted += 1
        except Exception as _e:
            log.debug("exception delete failed id=%d: %s", ex['Id'], _e)
            errors += 1
    log.info("exception-clear deleted=%d errors=%d", deleted, errors)
    print(f"Deleted {deleted}/{len(exceptions)} exceptions." + (f" ({errors} errors)" if errors else ""))


# Four of this script's subcommands write to Rock. `rock.sh` sets
# ROCK_ALLOW_WRITES=1 and nothing else does, so the copy of this script sitting
# in $ROCK_HOME cannot be run by hand into a write. The guard used to mark the
# boundary between two plugins; there is one now, and what it marks is the
# boundary between the entry point and everything else. See ADR 0023.
WRITE_COMMANDS = {
    "person-create": "creates a person record",
    "person-update": "modifies a person record",
    "block-set": "changes a block's settings",
    "exception-clear": "deletes exception logs",
}


def _guard_writes(command):
    if command not in WRITE_COMMANDS or os.environ.get("ROCK_ALLOW_WRITES") == "1":
        return
    print(
        f"Refusing to run '{command}': it {WRITE_COMMANDS[command]}, and it was not "
        f"reached through rock.sh.\n"
        f"Run it as `rock.sh query {command} ...` — the entry point is what logs the "
        f"call and enables the write.",
        file=sys.stderr,
    )
    sys.exit(2)


def main():
    parser = argparse.ArgumentParser(description="Query Rock RMS entities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_wfs = subparsers.add_parser("workflows", help="List workflow types")
    p_wfs.add_argument("--category", help="Filter by category name")
    p_wfs.add_argument("--limit", type=int, default=100)
    p_wfs.set_defaults(func=cmd_workflows)

    p_wf = subparsers.add_parser("workflow", help="Get a workflow by name or ID")
    p_wf.add_argument("identifier", help="Workflow name or ID")
    p_wf.add_argument("--json", action="store_true", help="Output raw JSON")
    p_wf.set_defaults(func=cmd_workflow)

    p_pgs = subparsers.add_parser("pages", help="List pages")
    p_pgs.add_argument("--site", type=int, help="Filter by site ID")
    p_pgs.add_argument("--limit", type=int, default=100)
    p_pgs.set_defaults(func=cmd_pages)

    p_pg = subparsers.add_parser("page", help="Get a page by name, route, or ID")
    p_pg.add_argument("identifier", help="Page name, route, or ID")
    p_pg.add_argument("--json", action="store_true", help="Output raw JSON")
    p_pg.set_defaults(func=cmd_page)

    p_search = subparsers.add_parser("search", help="Search across entities")
    p_search.add_argument("query", help="Search text")
    p_search.set_defaults(func=cmd_search)

    p_audit = subparsers.add_parser("audit", help="Audit a workflow for issues")
    p_audit.add_argument("identifier", help="Workflow name or ID")
    p_audit.add_argument("--skip-settings", action="store_true",
                         help="Skip per-action settings checks (faster)")
    p_audit.set_defaults(func=cmd_audit)

    p_actions = subparsers.add_parser("actions", help="Show detailed actions for an activity")
    p_actions.add_argument("activity_id", help="Activity type ID")
    p_actions.set_defaults(func=cmd_actions)

    p_attrs = subparsers.add_parser("attributes", help="Show workflow attributes")
    p_attrs.add_argument("identifier", help="Workflow name or ID")
    p_attrs.set_defaults(func=cmd_attributes)

    p_dvs = subparsers.add_parser("dataviews", help="List data views")
    p_dvs.add_argument("--category", help="Filter by name substring")
    p_dvs.add_argument("--limit", type=int, default=100)
    p_dvs.set_defaults(func=cmd_dataviews)

    p_dv = subparsers.add_parser("dataview", help="Get a data view by name or ID")
    p_dv.add_argument("identifier", help="Data view name or ID")
    p_dv.add_argument("--json", action="store_true", help="Output raw JSON")
    p_dv.set_defaults(func=cmd_dataview)

    p_person = subparsers.add_parser("person", help="Look up a person by name, email, or ID")
    p_person.add_argument("identifier", help="Person name, email, or ID")
    p_person.set_defaults(func=cmd_person)

    p_group = subparsers.add_parser("group", help="Get a group by name or ID")
    p_group.add_argument("identifier", help="Group name or ID")
    p_group.add_argument("--json", action="store_true", help="Output raw JSON")
    p_group.add_argument("--limit", type=int, default=50, help="Max members to show")
    p_group.set_defaults(func=cmd_group)

    p_report = subparsers.add_parser("report", help="Get a report by name or ID")
    p_report.add_argument("identifier", help="Report name or ID")
    p_report.add_argument("--json", action="store_true", help="Output raw JSON")
    p_report.set_defaults(func=cmd_report)

    p_exs = subparsers.add_parser("exceptions", help="List recent exception logs")
    p_exs.add_argument("--type", help="Filter by exception type substring")
    p_exs.add_argument("--summary", action="store_true", help="Group by type with counts")
    p_exs.add_argument("--verbose", action="store_true", help="Show stack traces")
    p_exs.add_argument("--limit", type=int, default=50)
    p_exs.set_defaults(func=cmd_exceptions)

    p_ex = subparsers.add_parser("exception", help="Get exception detail by ID")
    p_ex.add_argument("id", type=int, help="Exception log ID")
    p_ex.add_argument("--json", action="store_true", help="Output raw JSON")
    p_ex.set_defaults(func=cmd_exception)

    p_scheds = subparsers.add_parser("schedules", help="List schedules")
    p_scheds.add_argument("--active", action="store_true", help="Active only")
    p_scheds.add_argument("--query", help="Filter by name substring")
    p_scheds.add_argument("--limit", type=int, default=100)
    p_scheds.set_defaults(func=cmd_schedules)

    p_sched = subparsers.add_parser("schedule", help="Get a schedule by name or ID")
    p_sched.add_argument("identifier", help="Schedule name or ID")
    p_sched.add_argument("--json", action="store_true", help="Output raw JSON")
    p_sched.set_defaults(func=cmd_schedule)

    p_regs = subparsers.add_parser("registrations", help="List registration instances")
    p_regs.add_argument("--active", action="store_true", help="Active only")
    p_regs.add_argument("--query", help="Filter by name substring")
    p_regs.add_argument("--limit", type=int, default=50)
    p_regs.set_defaults(func=cmd_registrations)

    p_reg = subparsers.add_parser("registration", help="Get a registration instance by name or ID")
    p_reg.add_argument("identifier", help="Registration name or ID")
    p_reg.add_argument("--json", action="store_true", help="Output raw JSON")
    p_reg.set_defaults(func=cmd_registration)

    p_conns = subparsers.add_parser("connections", help="List connection requests")
    p_conns.add_argument("--state", help="Filter by state (active, inactive, future, connected)")
    p_conns.add_argument("--opportunity", help="Filter by opportunity name substring")
    p_conns.add_argument("--limit", type=int, default=50)
    p_conns.set_defaults(func=cmd_connections)

    p_block = subparsers.add_parser("block", help="Get block with attributes by ID")
    p_block.add_argument("id", help="Block ID")
    p_block.add_argument("--json", action="store_true", help="Output raw JSON")
    p_block.set_defaults(func=cmd_block)

    p_bgc = subparsers.add_parser("bgc", help="List background checks")
    p_bgc.add_argument("--status", help="Filter by status substring")
    p_bgc.add_argument("--person", help="Filter by person name or ID")
    p_bgc.add_argument("--limit", type=int, default=50)
    p_bgc.set_defaults(func=cmd_bgc)

    p_checkin = subparsers.add_parser("checkin", help="Show check-in configuration")
    p_checkin.add_argument("--area", help="Specific check-in area name or ID")
    p_checkin.set_defaults(func=cmd_checkin)

    p_att = subparsers.add_parser("attendance", help="List attendance occurrences")
    p_att.add_argument("--group", help="Filter by group name or ID")
    p_att.add_argument("--date", help="Filter by date (YYYY-MM-DD)")
    p_att.add_argument("--limit", type=int, default=50)
    p_att.set_defaults(func=cmd_attendance)

    p_occ = subparsers.add_parser("occurrence", help="Get attendance occurrence detail")
    p_occ.add_argument("id", type=int, help="Occurrence ID")
    p_occ.add_argument("--names", action="store_true", help="Show attendee names")
    p_occ.add_argument("--json", action="store_true", help="Output raw JSON")
    p_occ.add_argument("--limit", type=int, default=200, help="Max attendees to show")
    p_occ.set_defaults(func=cmd_occurrence)

    p_bset = subparsers.add_parser("block-set", help="Set a block attribute value")
    p_bset.add_argument("id", help="Block ID")
    p_bset.add_argument("key", help="Attribute key")
    p_bset.add_argument("value", help="Attribute value")
    p_bset.set_defaults(func=cmd_block_set)

    p_pcreate = subparsers.add_parser("person-create", help="Create a new person record")
    p_pcreate.add_argument("--first", required=True, help="First name")
    p_pcreate.add_argument("--last", required=True, help="Last name")
    p_pcreate.add_argument("--email", help="Email address")
    p_pcreate.add_argument("--connection-status", help="ConnectionStatusValueId")
    p_pcreate.add_argument("--record-status", help="RecordStatusValueId")
    p_pcreate.add_argument("--campus", help="CampusId")
    p_pcreate.set_defaults(func=cmd_person_create)

    p_pupdate = subparsers.add_parser("person-update", help="Update a person's fields")
    p_pupdate.add_argument("id", help="Person ID")
    p_pupdate.add_argument("fields", nargs="+", help="Field=value pairs (e.g. Email=foo@bar.com)")
    p_pupdate.set_defaults(func=cmd_person_update)

    p_exclear = subparsers.add_parser("exception-clear", help="Delete exception logs")
    p_exclear.add_argument("--before", help="Delete exceptions before date (YYYY-MM-DD)")
    p_exclear.add_argument("--type", help="Filter by exception type substring")
    p_exclear.add_argument("--limit", type=int, default=500, help="Max exceptions to delete per run")
    p_exclear.set_defaults(func=cmd_exception_clear)

    parsed = parser.parse_args()
    _guard_writes(parsed.command)
    log.info("cmd=%s args=%s", parsed.command, " ".join(sys.argv[2:]))
    with api_errors_reported():
        client = RockClient()
        try:
            render(parsed.func(parsed, client))
            log.info("cmd=%s ok", parsed.command)
        except LookupMiss as miss:
            # A name that resolves to nothing, or to several things, is a failed
            # request rather than an empty answer. An empty collection comes back
            # as a `Listing` with no rows and still exits 0.
            render(miss.report)
            log.info("cmd=%s no match", parsed.command)
            sys.exit(1)
        except Exception:
            log.error("cmd=%s failed\n%s", parsed.command, traceback.format_exc())
            raise


if __name__ == "__main__":
    main()
