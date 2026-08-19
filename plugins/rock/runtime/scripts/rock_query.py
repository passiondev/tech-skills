"""Query Rock RMS entities -- workflows, pages, blocks.

Usage:
  uv run scripts/rock_query.py workflows                    # list workflows
  uv run scripts/rock_query.py workflow "Volunteer Signup"   # get one workflow
  uv run scripts/rock_query.py workflow 234                  # get by ID
  uv run scripts/rock_query.py pages                         # list pages
  uv run scripts/rock_query.py page "/volunteers"            # get by route
  uv run scripts/rock_query.py page 456                      # get by ID
  uv run scripts/rock_query.py search "volunteer"            # search across entities

A command that answers with a list of entities builds a `Listing` and returns
it; `render` prints it at the boundary. The detail views still print for
themselves, which is the part of this that is half done.
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


def more_note(identifier):
    """A disambiguation list that silently drops candidates is worse than a
    long one: the entity someone wants reads as not existing."""
    return f"  ... and more match '{identifier}' — narrow it, or pass the ID."


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


ID_WIDTH = 6
_LABEL_COLUMN = 2 + ID_WIDTH + 2


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


def render(report):
    """Print what a command returned, and say whether it found anything.

    This is the only place a listing reaches stdout. A command that returns
    nothing printed for itself, which is still true of the detail views.
    """
    if report is None:
        return
    parts = report if isinstance(report, list) else [report]
    for index, part in enumerate(parts):
        if index:
            print()
        part.render()


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
    """The one entity an operator meant, or None with the reason printed.

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
        print(f"Multiple {label}s match '{identifier}':")
        for r in results:
            print(row(r["Id"], r.get(name_field, "?")))
        if more:
            print(more_note(identifier))
        return None
    print(f"No {label} found matching '{identifier}'")
    return None


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
        active = "" if wf.get("IsActive") else " [inactive]"
        cat_name = cat_names.get(wf.get("CategoryId"), "")
        cat_str = f" ({cat_name})" if cat_name else ""
        listing.add(wf["Id"], f"{wf['Name']}{cat_str}{active}")
    return listing


def cmd_workflow(args, client):
    wf = _find_entity(client, "WorkflowTypes", args.identifier,
                      label="workflow")
    if not wf:
        return
    _load_workflow_tree(wf, client)

    if args.json:
        print(json.dumps(wf, indent=2))
    else:
        print(format_workflow_tree(wf))


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
    if not page:
        return

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
        print(json.dumps(page, indent=2))
    else:
        name = page.get("InternalName") or page.get("PageTitle") or "(untitled)"
        print(f"{name} (ID: {page['Id']})")
        if routes:
            shown = ", ".join("/" + r["Route"] for r in routes)
            print(f"  Routes: {shown}" + (", ..." if routes_capped else ""))
        print(f"  Layout ID: {page.get('LayoutId')}")
        if blocks:
            print(f"  Blocks ({tally(blocks, blocks_capped, hint=CHILD_HINT)}):")
            current_zone = None
            for b in blocks:
                zone = b.get("Zone", "Main")
                if zone != current_zone:
                    current_zone = zone
                    print(f"    Zone: {zone}")
                bt_name = b.get("BlockType", {}).get("Name", "?")
                print(f"      {b['Name'] or bt_name} [{bt_name}]")


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


def _print_audit(wf, issues, warnings):
    active = "Active" if wf.get("IsActive") else "Inactive"
    print(f"Audit: {wf['Name']} (ID: {wf['Id']})")
    print(f"Status: {active}")
    print()

    activities = sorted(wf.get("ActivityTypes", []), key=lambda a: a.get("Order", 0))
    if activities:
        print("Structure:")
        if wf.get("ActivityTypesCapped"):
            print(f"  (only the first {CHILD_LIMIT} activities are shown)")
        for i, act in enumerate(activities):
            is_last = i == len(activities) - 1
            prefix = "  └─" if is_last else "  ├─"
            activated = " (activated)" if act.get("IsActivatedWithWorkflow") else ""
            actions = sorted(act.get("ActionTypes", []), key=lambda a: a.get("Order", 0))
            count = tally(actions, act.get("ActionTypesCapped"), hint=CHILD_HINT)
            print(f"{prefix} {act['Name']}{activated} [{count} actions]")
            for j, action in enumerate(actions):
                is_last_action = j == len(actions) - 1
                branch = "     " if is_last else "  │  "
                ap = "└─" if is_last_action else "├─"
                entity_name = (action.get("EntityType") or {}).get("FriendlyName", "?")
                print(f"{branch} {ap} {action['Name']} [{entity_name}]")
        print()

    if issues:
        print(f"Issues ({len(issues)}):")
        for issue in issues:
            print(f"  ✗ {issue}")
        print()

    if warnings:
        print(f"Warnings ({len(warnings)}):")
        for w in warnings:
            print(f"  ! {w}")
        print()

    if not issues and not warnings:
        print("✓ No issues found")


def cmd_audit(args, client):
    wf = _find_entity(client, "WorkflowTypes", args.identifier,
                      label="workflow")
    if not wf:
        return
    _load_workflow_tree(wf, client)
    if not wf:
        return

    issues = []
    warnings = []

    if not wf.get("IsActive"):
        warnings.append("Workflow is inactive")

    activities = sorted(wf.get("ActivityTypes", []), key=lambda a: a.get("Order", 0))

    if not activities:
        issues.append("Workflow has no activities")
        _print_audit(wf, issues, warnings)
        return

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

    _print_audit(wf, issues, warnings)


def cmd_actions(args, client):
    act_id = int(args.activity_id)

    act = client.get(f"WorkflowActivityTypes/{act_id}")
    if not act:
        print(f"Activity {act_id} not found")
        return

    actions, actions_capped = get_capped(client, "WorkflowActionTypes", {
        "$filter": f"ActivityTypeId eq {act_id}",
        "$orderby": "Order",
    }, CHILD_LIMIT)
    _enrich_actions_entity_types(actions, client)
    print(f"Activity: {act['Name']} (ID: {act['Id']})")
    print(f"  Activated with workflow: {act.get('IsActivatedWithWorkflow', False)}")
    print(f"  Actions: {tally(actions, actions_capped, hint=CHILD_HINT)}")
    print()

    for action in actions:
        entity = action.get("EntityType") or {}
        entity_name = entity.get("FriendlyName", "?")
        print(f"  [{action.get('Order', '?')}] {action['Name']} (ID: {action['Id']})")
        print(f"      Type: {entity_name}")
        print(f"      Completes action: {action.get('IsActionCompletedOnSuccess', False)}")
        print(f"      Completes activity: {action.get('IsActivityCompletedOnSuccess', False)}")

        settings = _get_action_settings(client, action["Id"])
        if settings:
            print("      Settings:")
            for k, v in settings.items():
                val = str(v)[:120] + ("..." if len(str(v)) > 120 else "")
                print(f"        {k}: {val}")
        print()


def cmd_attributes(args, client):
    wf = _find_entity(client, "WorkflowTypes", args.identifier,
                      label="workflow")
    if not wf:
        return

    attrs, attrs_capped = get_capped(client, "Attributes", {
        "$filter": f"EntityTypeQualifierColumn eq 'WorkflowTypeId' and EntityTypeQualifierValue eq '{wf['Id']}'",
        "$orderby": "Order",
    }, CHILD_LIMIT)

    if not attrs:
        print(f"No attributes on '{wf['Name']}' (ID: {wf['Id']})")
        return

    # Resolve field type names
    ft_ids = {a.get("FieldTypeId") for a in attrs if a.get("FieldTypeId")}
    ft_names = {fid: _resolve_name(client, "FieldTypes", fid) for fid in ft_ids}

    print(f"Attributes on '{wf['Name']}' "
          f"(ID: {wf['Id']}, {tally(attrs, attrs_capped, hint=CHILD_HINT)}):\n")
    for attr in attrs:
        ft = ft_names.get(attr.get("FieldTypeId"), "?")
        req = " [required]" if attr.get("IsRequired") else ""
        grid = " [grid]" if attr.get("IsGridColumn") else ""
        print(f"  {attr.get('Order', '?'):3}  {attr['Key']} ({ft}){req}{grid}")
        if attr.get("Description"):
            print(f"       {attr['Description'][:100]}")


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
    if not dv:
        return

    if args.json:
        print(json.dumps(dv, indent=2))
        return

    print(f"{dv['Name']} (ID: {dv['Id']})")
    if dv.get("Description"):
        print(f"  {dv['Description'][:200]}")

    entity_name = _resolve_name(client, "EntityTypes", dv.get("EntityTypeId"),
                                field="FriendlyName")
    print(f"  Entity: {entity_name}")

    if dv.get("TransformEntityTypeId"):
        print(f"  Transform: " + _resolve_name(
            client, "EntityTypes", dv["TransformEntityTypeId"],
            field="FriendlyName"))

    if dv.get("CategoryId"):
        cat_name = _resolve_name(client, "Categories", dv["CategoryId"])
        if cat_name != "?":
            print(f"  Category: {cat_name}")

    persisted = dv.get("PersistedScheduleIntervalMinutes")
    if persisted:
        print(f"  Persisted: every {persisted} min (last: {dv.get('PersistedLastRefreshDateTime', 'never')})")
    print(f"  Last run: {dv.get('LastRunDateTime', 'never')} ({dv.get('TimeToRunDurationMilliseconds', 0)}ms)")

    filter_id = dv.get("DataViewFilterId")
    if filter_id:
        print(f"\n  Filters:")
        lines = _load_filter_tree(client, filter_id, depth=2)
        if lines:
            for line in lines:
                print(line)
    print()


def cmd_person(args, client):
    identifier = args.identifier

    person = None
    try:
        pid = int(identifier)
        person = client.get(f"People/{pid}")
        if person:
            _print_person(person, client)
            return
    except (ValueError, RockNotFound):
        pass

    results, more = get_capped(client, "People",
                               {"$filter": _people_filter(identifier)},
                               SEARCH_LIMIT)

    if not results:
        print(f"No person found matching '{identifier}'")
        return

    if len(results) == 1:
        _print_person(results[0], client)
    else:
        print(f"People matching '{identifier}':\n")
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
            print(row(p["Id"],
                      f"{p.get('FirstName', '')} {p.get('LastName', '')}"
                      f"{email}{campus}"))
        if more:
            print(more_note(identifier))


def _print_person(person, client):
    print(f"{person.get('FirstName', '')} {person.get('LastName', '')} (ID: {person['Id']})")
    if person.get("Email"):
        print(f"  Email: {person['Email']}")
    if person.get("Gender") and person["Gender"] != 0:
        print(f"  Gender: {GENDERS.get(person['Gender'], 'Unknown')}")
    if person.get("BirthDate"):
        print(f"  DOB: {person['BirthDate'][:10]}")
    if person.get("ConnectionStatusValueId"):
        val = _resolve_name(client, "DefinedValues", person["ConnectionStatusValueId"], field="Value")
        if val != "?":
            print(f"  Connection Status: {val}")
    if person.get("RecordStatusValueId"):
        val = _resolve_name(client, "DefinedValues", person["RecordStatusValueId"], field="Value")
        if val != "?":
            print(f"  Record Status: {val}")
    if person.get("PrimaryCampusId"):
        campus = _resolve_name(client, "Campuses", person["PrimaryCampusId"])
        if campus != "?":
            print(f"  Campus: {campus}")

    # Family
    role_cache = {}
    try:
        families = client.get(f"Groups/GetFamilies/{person['Id']}")
        if families:
            for fam in families:
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
                print(f"  Family: {fam['Name']} (ID: {fam['Id']}){capped}")
                for m in members:
                    if m["PersonId"] == person["Id"]:
                        continue
                    try:
                        p = client.get(f"People/{m['PersonId']}", params={"$select": "FirstName,LastName"})
                        if p:
                            print(f"    {roles.get(m['PersonId'], '?'):10s} {p['FirstName']} {p['LastName']}")
                    except Exception as _e:
                        log.debug("lookup failed: %s", _e)
    except Exception as _e:
        log.debug("lookup failed: %s", _e)

    # Known relationships
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
            if members:
                capped = f" (first {CHILD_LIMIT})" if members_capped else ""
                print(f"  Known Relationships:{capped}")
                for m in members:
                    try:
                        p = client.get(f"People/{m['PersonId']}", params={"$select": "FirstName,LastName"})
                        pname = f"{p['FirstName']} {p['LastName']}" if p else f"Person:{m['PersonId']}"
                        rid = m["GroupRoleId"]
                        if rid not in role_cache:
                            role_cache[rid] = _resolve_name(client, "GroupTypeRoles", rid)
                        print(f"    {role_cache[rid]:20s} {pname}")
                    except Exception as _e:
                        log.debug("lookup failed: %s", _e)
    except Exception as _e:
        log.debug("lookup failed: %s", _e)


def cmd_group(args, client):
    group = _find_entity(client, "Groups", args.identifier, label="group")
    if not group:
        return

    if args.json:
        print(json.dumps(group, indent=2))
        return

    print(f"{group['Name']} (ID: {group['Id']})")
    if group.get("Description"):
        print(f"  {group['Description'][:200]}")

    # Group type
    if group.get("GroupTypeId"):
        gt_name = _resolve_name(client, "GroupTypes", group["GroupTypeId"])
        if gt_name != "?":
            print(f"  Type: {gt_name}")

    print(f"  Active: {group.get('IsActive', False)}")
    if group.get("CampusId"):
        campus_name = _resolve_name(client, "Campuses", group["CampusId"])
        if campus_name != "?":
            print(f"  Campus: {campus_name}")
    if group.get("ScheduleId"):
        sched_name = _resolve_name(client, "Schedules", group["ScheduleId"])
        if sched_name != "?":
            print(f"  Schedule: {sched_name}")

    # Members
    members, mem_more = get_capped(client, "GroupMembers", {
        "$filter": f"GroupId eq {group['Id']}",
        "$select": "PersonId,GroupRoleId,GroupMemberStatus",
    }, args.limit)
    if members:
        role_cache = {}
        print(f"  Members ({tally(members, mem_more)}):")
        for m in members:
            rid = m.get("GroupRoleId")
            if rid not in role_cache:
                role_cache[rid] = _resolve_name(client, "GroupTypeRoles", rid)
            try:
                p = client.get(f"People/{m['PersonId']}", params={"$select": "FirstName,LastName"})
                pname = f"{p['FirstName']} {p['LastName']}" if p else f"ID:{m['PersonId']}"
            except Exception as _e:
                log.debug("person lookup failed: %s", _e)
                pname = f"ID:{m['PersonId']}"
            status = GROUP_MEMBER_STATUSES.get(m.get("GroupMemberStatus"), "?")
            print(f"    {pname:30s} {role_cache[rid]:15s} [{status}]")


def cmd_report(args, client):
    report = _find_entity(client, "Reports", args.identifier, label="report")
    if not report:
        return

    if args.json:
        print(json.dumps(report, indent=2))
        return

    print(f"{report['Name']} (ID: {report['Id']})")
    if report.get("Description"):
        print(f"  {report['Description'][:200]}")

    if report.get("DataViewId"):
        dv_name = _resolve_name(client, "DataViews", report["DataViewId"])
        if dv_name != "?":
            print(f"  Data View: {dv_name} (ID: {report['DataViewId']})")
        else:
            print(f"  Data View ID: {report['DataViewId']}")

    if report.get("CategoryId"):
        cat_name = _resolve_name(client, "Categories", report["CategoryId"])
        if cat_name != "?":
            print(f"  Category: {cat_name}")

    # Report fields
    fields, fields_capped = get_capped(client, "ReportFields", {
        "$filter": f"ReportId eq {report['Id']}",
        "$select": "ReportFieldType,ShowInGrid,ColumnOrder,ColumnHeaderText,DataSelectComponentEntityTypeId",
    }, CHILD_LIMIT)
    if fields:
        print(f"  Fields ({tally(fields, fields_capped, hint=CHILD_HINT)}):")
        for f in sorted(fields, key=lambda x: x.get("ColumnOrder", 0)):
            header = f.get("ColumnHeaderText", "") or "(no header)"
            print(f"    {f.get('ColumnOrder', '?'):3}  {header}")


def cmd_exceptions(args, client):
    params = {"$orderby": "CreatedDateTime desc"}
    if args.type:
        params["$filter"] = f"substringof('{odata_str(args.type)}', ExceptionType) eq true"

    exceptions, more = get_capped(client, "ExceptionLogs", params, args.limit)

    if args.summary:
        if not exceptions:
            print("No exceptions found.")
            return None
        # Group by ExceptionType and count
        counts = {}
        for ex in exceptions:
            et = ex.get("ExceptionType", "Unknown")
            short = et.split(".")[-1] if "." in et else et
            counts[short] = counts.get(short, 0) + 1
        # The counts below are over the rows fetched, not over the log. Saying
        # "last 50" made that sound deliberate; it was the cap.
        window = f"{len(exceptions)} most recent" + (" of more" if more else "")
        print(f"Exception summary ({window}):\n")
        for etype, count in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"  {count:4d}  {etype}")
        return None

    listing = Listing("Exceptions", more, spaced=True)
    for ex in exceptions:
        dt = (ex.get("CreatedDateTime") or "")[:19]
        etype = ex.get("ExceptionType", "Unknown")
        short_type = etype.split(".")[-1] if "." in etype else etype
        desc = (ex.get("Description") or "")[:120]
        url = ex.get("PageUrl", "")
        trace = ex["StackTrace"].split("\n")[:5] if (
            args.verbose and ex.get("StackTrace")) else []
        listing.add(ex["Id"], f"[{dt}] {short_type}", desc,
                    f"URL: {url}" if url else "",
                    *(line.strip() for line in trace))
    return listing


def cmd_exception(args, client):
    ex = client.get(f"ExceptionLogs/{args.id}")
    if not ex:
        print(f"Exception {args.id} not found")
        return

    if args.json:
        print(json.dumps(ex, indent=2))
        return

    dt = (ex.get("CreatedDateTime") or "")[:19]
    print(f"Exception {ex['Id']} ({dt})")
    print(f"  Type: {ex.get('ExceptionType', 'Unknown')}")
    if ex.get("StatusCode"):
        print(f"  HTTP Status: {ex['StatusCode']}")
    if ex.get("Source"):
        print(f"  Source: {ex['Source']}")
    if ex.get("Description"):
        print(f"  Description: {ex['Description']}")
    if ex.get("PageUrl"):
        print(f"  URL: {ex['PageUrl']}")
    if ex.get("StackTrace"):
        print(f"  Stack Trace:")
        for line in ex["StackTrace"].split("\n")[:15]:
            print(f"    {line.strip()}")
    if ex.get("HasInnerException") and ex.get("Id"):
        inner = first(client, "ExceptionLogs", {
            "$filter": f"ParentId eq {ex['Id']}",
        })
        if inner:
            print(f"  Inner Exception: {inner.get('ExceptionType', '?')}")
            if inner.get("Description"):
                print(f"    {inner['Description'][:200]}")


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
        active = "" if s.get("IsActive") else " [inactive]"
        listing.add(s["Id"], f"{s['Name']}{active}")
    return listing


def cmd_schedule(args, client):
    schedule = _find_entity(client, "Schedules", args.identifier, label="schedule")
    if not schedule:
        return

    if args.json:
        print(json.dumps(schedule, indent=2))
        return

    print(f"{schedule['Name']} (ID: {schedule['Id']})")
    print(f"  Active: {schedule.get('IsActive', False)}")
    if schedule.get("Description"):
        print(f"  Description: {schedule['Description'][:200]}")
    if schedule.get("EffectiveStartDate"):
        print(f"  Start: {schedule['EffectiveStartDate'][:10]}")
    if schedule.get("EffectiveEndDate"):
        print(f"  End: {schedule['EffectiveEndDate'][:10]}")
    if schedule.get("CheckInStartOffsetMinutes"):
        print(f"  Check-in window: -{schedule['CheckInStartOffsetMinutes']}min to +{schedule.get('CheckInEndOffsetMinutes', 0)}min")
    if schedule.get("CategoryId"):
        cat_name = _resolve_name(client, "Categories", schedule["CategoryId"])
        if cat_name != "?":
            print(f"  Category: {cat_name}")


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
        active = "" if r.get("IsActive") else " [inactive]"
        start = (r.get("StartDateTime") or "")[:10]
        end = (r.get("EndDateTime") or "")[:10]
        date_range = f" ({start} to {end})" if start else ""
        max_att = f" [max: {r['MaxAttendees']}]" if r.get("MaxAttendees") else ""
        listing.add(r["Id"], f"{r['Name']}{active}{date_range}{max_att}")
    return listing


def cmd_registration(args, client):
    reg = _find_entity(client, "RegistrationInstances", args.identifier, label="registration")
    if not reg:
        return

    if args.json:
        print(json.dumps(reg, indent=2))
        return

    print(f"{reg['Name']} (ID: {reg['Id']})")
    print(f"  Active: {reg.get('IsActive', False)}")
    if reg.get("StartDateTime"):
        print(f"  Start: {reg['StartDateTime'][:19]}")
    if reg.get("EndDateTime"):
        print(f"  End: {reg['EndDateTime'][:19]}")
    if reg.get("MaxAttendees"):
        print(f"  Max Attendees: {reg['MaxAttendees']}")
    if reg.get("Cost"):
        print(f"  Cost: ${reg['Cost']}")
    if reg.get("ContactEmail"):
        print(f"  Contact: {reg['ContactEmail']}")

    # Registration template
    if reg.get("RegistrationTemplateId"):
        tmpl_name = _resolve_name(client, "RegistrationTemplates", reg["RegistrationTemplateId"])
        if tmpl_name != "?":
            print(f"  Template: {tmpl_name} (ID: {reg['RegistrationTemplateId']})")
        else:
            print(f"  Template ID: {reg['RegistrationTemplateId']}")

    # Linked workflow
    if reg.get("RegistrationWorkflowTypeId"):
        wf_name = _resolve_name(client, "WorkflowTypes", reg["RegistrationWorkflowTypeId"])
        if wf_name != "?":
            print(f"  Workflow: {wf_name} (ID: {reg['RegistrationWorkflowTypeId']})")

    if reg.get("Details"):
        print(f"  Details: {reg['Details'][:200]}")


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
        print(f"Block {block_id} not found")
        return

    if args.json:
        print(json.dumps(block, indent=2))
        return

    print(f"{block.get('Name', '(unnamed)')} (ID: {block['Id']})")
    if block.get("BlockTypeId"):
        bt_name = _resolve_name(client, "BlockTypes", block["BlockTypeId"])
        if bt_name != "?":
            print(f"  Block Type: {bt_name}")
    print(f"  Zone: {block.get('Zone', '?')}")
    print(f"  Order: {block.get('Order', '?')}")
    if block.get("PageId"):
        print(f"  Page ID: {block['PageId']}")

    avs = block.get("AttributeValues", {})
    if avs:
        print(f"  Attributes ({len(avs)}):")
        for key, val in avs.items():
            if isinstance(val, dict):
                v = val.get("Value", "")
            else:
                v = str(val) if val else ""
            if not v:
                continue
            # Truncate long values but show more for HTML/Lava
            max_len = 300 if key.lower() in ("query", "formattedoutput", "template", "lavatemplate") else 150
            display = v[:max_len] + ("..." if len(v) > max_len else "")
            print(f"    {key}: {display}")


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
        # Show specific check-in area (group) with locations and schedules
        # Restrict by group type in the query rather than after it. Filtering
        # afterwards spent the cap on rows that were about to be discarded: a
        # common word can match hundreds of groups of every type, and if no
        # check-in group landed in the first ten the command answered "No
        # check-in area found" for areas that plainly exist.
        checkin_type_ids = sorted(gt["Id"] for gt in checkin_group_types)

        def among_checkin_types(odata_filter, limit):
            if not checkin_type_ids:
                return get_capped(client, "Groups", {"$filter": odata_filter,
                                                     "$select": "Id,Name"}, limit)
            return groups_of_types(client, odata_filter, checkin_type_ids, limit)

        group = _find_entity(client, "Groups", args.area, label="check-in area",
                             search=among_checkin_types)
        if not group:
            return

        print(f"{group['Name']} (ID: {group['Id']})")
        print(f"  Active: {group.get('IsActive', False)}")

        # Locations
        group_locs, locs_capped = get_capped(client, "GroupLocations", {
            "$filter": f"GroupId eq {group['Id']}",
            "$select": "LocationId",
        }, CHILD_LIMIT)
        if group_locs:
            print(f"  Locations ({tally(group_locs, locs_capped, hint=CHILD_HINT)}):")
            for gl in group_locs:
                loc_name = _resolve_name(client, "Locations", gl["LocationId"])
                if loc_name != "?":
                    print(f"    {loc_name} (ID: {gl['LocationId']})")
                else:
                    print(f"    Location ID: {gl['LocationId']}")

        # Child groups (sub-areas)
        children, children_capped = get_capped(client, "Groups", {
            "$filter": f"ParentGroupId eq {group['Id']}",
            "$select": "Id,Name,IsActive",
            "$orderby": "Order",
        }, CHILD_LIMIT)
        if children:
            print(f"  Sub-areas ({tally(children, children_capped, hint=CHILD_HINT)}):")
            for child in children:
                active = "" if child.get("IsActive") else " [inactive]"
                print(row(child["Id"], f"{child['Name']}{active}", indent=4))
        return

    # Default: show check-in group type hierarchy
    if not checkin_group_types:
        print("No check-in group types found.")
        return

    print("Check-in Configuration:\n")
    if types_capped:
        print(f"  (only the first {CHILD_LIMIT} check-in group types are shown)\n")
    for gt in checkin_group_types:
        print(f"  Group Type: {gt['Name']} (ID: {gt['Id']})")
        # Top-level groups of this type
        top_groups, top_capped = get_capped(client, "Groups", {
            "$filter": f"GroupTypeId eq {gt['Id']} and ParentGroupId eq null",
            "$select": "Id,Name,IsActive",
            "$orderby": "Order",
        }, CHILD_LIMIT)
        if top_capped:
            print(f"    (only the first {CHILD_LIMIT} are shown)")
        for g in top_groups:
            active = "" if g.get("IsActive") else " [inactive]"
            print(row(g["Id"], f"{g['Name']}{active}", indent=4))
            # First level children
            children, children_capped = get_capped(client, "Groups", {
                "$filter": f"ParentGroupId eq {g['Id']}",
                "$select": "Id,Name,IsActive",
                "$orderby": "Order",
            }, CHILD_LIMIT)
            if children_capped:
                print(f"      (only the first {CHILD_LIMIT} are shown)")
            for child in children:
                ca = "" if child.get("IsActive") else " [inactive]"
                print(row(child["Id"], f"{child['Name']}{ca}", indent=6))
        print()


def cmd_attendance(args, client):
    params = {
        "$orderby": "OccurrenceDate desc",
    }
    filters = []
    if args.group:
        group = _find_entity(client, "Groups", args.group, label="group")
        if not group:
            return
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
        print(f"Occurrence {args.id} not found")
        return

    if args.json:
        print(json.dumps(occ, indent=2))
        return

    occ_date = (occ.get("OccurrenceDate") or "")[:10]
    print(f"Occurrence {occ['Id']} ({occ_date})")

    for label, endpoint, key in [("Group", "Groups", "GroupId"), ("Location", "Locations", "LocationId"), ("Schedule", "Schedules", "ScheduleId")]:
        if occ.get(key):
            name = _resolve_name(client, endpoint, occ[key])
            if name != "?":
                print(f"  {label}: {name} (ID: {occ[key]})")
            else:
                print(f"  {label} ID: {occ[key]}")

    if occ.get("DidNotOccur"):
        print("  Status: DID NOT OCCUR")

    # Attendees
    attendees, att_more = get_capped(client, "Attendances", {
        "$filter": f"OccurrenceId eq {occ['Id']}",
        "$select": "PersonAliasId,DidAttend,StartDateTime,RSVP",
    }, args.limit)

    if attendees:
        # "N total" from a capped fetch misstates the attendance rate itself,
        # not just the list length, so say plainly when the roll is cut short.
        did_attend = sum(1 for a in attendees if a.get("DidAttend"))
        cut = " — more exist, raise --limit" if att_more else ""
        print(f"  Attendees: {did_attend} attended / {len(attendees)} total{cut}")
        if args.names:
            person_cache = {}
            for a in attendees:
                aid = a.get("PersonAliasId")
                pname = _resolve_person_name(client, aid, person_cache)
                attended = "Y" if a.get("DidAttend") else "N"
                rsvp = f" RSVP:{a['RSVP']}" if a.get("RSVP") else ""
                print(f"    {pname:30s} [{attended}]{rsvp}")


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
        except Exception:
            log.error("cmd=%s failed\n%s", parsed.command, traceback.format_exc())
            raise


if __name__ == "__main__":
    main()
