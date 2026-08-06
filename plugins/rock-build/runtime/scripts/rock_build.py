"""Build Rock RMS entities from JSON definitions.

Reads a JSON build plan from stdin or a file and creates entities via the Rock API.
Handles sequential creation with parent-child ID dependencies.

Usage:
  echo '{"operation": "create_workflow", ...}' | uv run scripts/rock_build.py
  uv run scripts/rock_build.py /tmp/build-plan.json
"""

import json
import sys
import traceback
from pathlib import Path

from rock_client import RockClient, odata_str
from rock_catalog import load_catalog
from rock_log import get_logger

log = get_logger("rock.build")


def resolve_action_type(catalog, name):
    """Find an action component EntityType ID by friendly name."""
    name_lower = name.lower().replace(" ", "")
    for ac in catalog.get("action_components", []):
        ac_name = ac["name"].lower().replace(" ", "")
        ac_class = ac["class_name"].lower().split(".")[-1]
        if ac_name == name_lower or ac_class == name_lower:
            return ac["entity_type_id"]
    # Partial match
    for ac in catalog.get("action_components", []):
        if name_lower in ac["name"].lower() or name_lower in ac["class_name"].lower():
            return ac["entity_type_id"]
    return None


def _resolve_catalog_entry(catalog, section, name):
    """Find a catalog entry ID by exact or partial name match."""
    name_lower = name.lower()
    for item in catalog.get(section, []):
        if item["name"].lower() == name_lower:
            return item["id"]
    for item in catalog.get(section, []):
        if name_lower in item["name"].lower():
            return item["id"]
    return None


def resolve_field_type(catalog, name):
    """Find a FieldType ID by name."""
    return _resolve_catalog_entry(catalog, "field_types", name)


def resolve_block_type(catalog, name):
    """Find a BlockType ID by name."""
    return _resolve_catalog_entry(catalog, "block_types", name)


def resolve_category(client, name):
    """Find a category by name."""
    params = {"$filter": f"Name eq '{odata_str(name)}'", "$top": 1}
    cats = client.get("Categories", params=params)
    if cats:
        return cats[0]["Id"]
    return None


def resolve_layout(catalog, name, site_id=None):
    """Find a layout by name."""
    name_lower = name.lower()
    for layout in catalog.get("layouts", []):
        if layout["name"].lower() == name_lower:
            if site_id and layout.get("site_id") != site_id:
                continue
            return layout["id"]
    for layout in catalog.get("layouts", []):
        if name_lower in layout["name"].lower():
            if site_id and layout.get("site_id") != site_id:
                continue
            return layout["id"]
    return None


def _next_order(client, endpoint, filter_str):
    """Get the next Order value for a child entity (max + 1, or 0 if none)."""
    existing = client.get(endpoint, params={
        "$filter": filter_str,
        "$select": "Order",
        "$orderby": "Order desc",
        "$top": 1,
    })
    return (existing[0]["Order"] + 1) if existing else 0


def set_attribute_values(client, endpoint, entity_id, settings):
    """Set attribute values on an entity, trying both POST and PUT endpoints."""
    for attr_key, attr_value in settings.items():
        try:
            client.post(f"{endpoint}/{entity_id}/AttributeValues", {
                "Key": attr_key,
                "Value": str(attr_value),
            })
        except Exception:
            try:
                client.put(f"{endpoint}/AttributeValue/{entity_id}", {
                    "Key": attr_key,
                    "Value": str(attr_value),
                })
            except Exception as e2:
                print(f"  Warning: could not set {attr_key}: {e2}")


class BuildResult:
    def __init__(self):
        self.created = []
        self.failed = None

    def add(self, entity_type, name, entity_id):
        self.created.append({"type": entity_type, "name": name, "id": entity_id})
        log.info("created %s: %s (id: %s)", entity_type, name, entity_id)

    def fail(self, entity_type, name, error):
        self.failed = {"type": entity_type, "name": name, "error": str(error)}
        log.error("failed %s: %s -- %s\n%s", entity_type, name, error, traceback.format_exc())

    def report(self):
        print("\nBuild results:")
        for item in self.created:
            print(f"  ✓ {item['type']}: {item['name']} (id: {item['id']})")
        if self.failed:
            print(f"  ✗ {self.failed['type']}: {self.failed['name']} -- {self.failed['error']}")
            print(f"\n{len(self.created)} of {len(self.created) + 1} entities created.")
        else:
            print(f"\n{len(self.created)} entities created successfully.")

    @property
    def success(self):
        return self.failed is None


def get_workflow_entity_type_id(client):
    """Get the EntityType ID for WorkflowType (needed for attributes)."""
    results = client.get("EntityTypes", params={
        "$filter": "Name eq 'Rock.Model.WorkflowType'",
        "$select": "Id",
        "$top": 1,
    })
    if not results:
        # Try alternate naming
        results = client.get("EntityTypes", params={
            "$filter": "Name eq 'Rock.Model.Workflow.WorkflowType'",
            "$select": "Id",
            "$top": 1,
        })
    if results:
        return results[0]["Id"]
    return None


def create_workflow(plan, client, catalog):
    """Create a workflow type with activities, actions, forms, and attributes."""
    result = BuildResult()
    wf = plan["workflow"]

    # Resolve category
    category_id = None
    if "category" in wf:
        category_id = resolve_category(client, wf["category"])
        if not category_id:
            print(f"  Warning: category '{wf['category']}' not found, creating without category")

    # 1. Create WorkflowType
    wf_data = {
        "Name": wf["name"],
        "Description": wf.get("description", ""),
        "IsActive": wf.get("is_active", True),
        "IsPersisted": wf.get("is_persisted", True),
        "WorkTerm": wf.get("work_term", "Workflow"),
        "ProcessingIntervalSeconds": wf.get("processing_interval", None),
    }
    if category_id:
        wf_data["CategoryId"] = category_id

    try:
        wf_id = client.post("WorkflowTypes", wf_data)
        result.add("WorkflowType", wf["name"], wf_id)
    except Exception as e:
        result.fail("WorkflowType", wf["name"], e)
        result.report()
        return result

    # 2. Create Attributes on the WorkflowType
    wf_entity_type_id = get_workflow_entity_type_id(client)
    attr_ids = {}

    for attr_def in wf.get("attributes", []):
        field_type_id = resolve_field_type(catalog, attr_def.get("field_type", "Text"))
        if not field_type_id:
            result.fail("Attribute", attr_def["key"], f"Unknown field type: {attr_def.get('field_type')}")
            result.report()
            return result

        attr_data = {
            "EntityTypeId": wf_entity_type_id,
            "EntityTypeQualifierColumn": "WorkflowTypeId",
            "EntityTypeQualifierValue": str(wf_id),
            "FieldTypeId": field_type_id,
            "Key": attr_def["key"],
            "Name": attr_def.get("name", attr_def["key"]),
            "Description": attr_def.get("description", ""),
            "IsRequired": attr_def.get("is_required", False),
            "Order": attr_def.get("order", len(attr_ids)),
            "IsGridColumn": attr_def.get("is_grid_column", False),
        }

        try:
            attr_id = client.post("Attributes", attr_data)
            attr_ids[attr_def["key"]] = attr_id
            result.add("Attribute", attr_def["key"], attr_id)
        except Exception as e:
            result.fail("Attribute", attr_def["key"], e)
            result.report()
            return result

    # 3. Create Activities and Actions
    for act_order, act_def in enumerate(wf.get("activities", [])):
        act_data = {
            "WorkflowTypeId": wf_id,
            "Name": act_def["name"],
            "Description": act_def.get("description", ""),
            "IsActivatedWithWorkflow": act_def.get("is_activated_with_workflow", act_order == 0),
            "Order": act_def.get("order", act_order),
            "IsActive": True,
        }

        try:
            act_id = client.post("WorkflowActivityTypes", act_data)
            result.add("ActivityType", act_def["name"], act_id)
        except Exception as e:
            result.fail("ActivityType", act_def["name"], e)
            result.report()
            return result

        # Actions within this activity
        for action_order, action_def in enumerate(act_def.get("actions", [])):
            entity_type_id = resolve_action_type(catalog, action_def["action_type"])
            if not entity_type_id:
                result.fail("ActionType", action_def["name"],
                            f"Unknown action type: {action_def['action_type']}")
                result.report()
                return result

            action_data = {
                "ActivityTypeId": act_id,
                "Name": action_def["name"],
                "EntityTypeId": entity_type_id,
                "Order": action_def.get("order", action_order),
                "IsActionCompletedOnSuccess": action_def.get("complete_on_success", True),
                "IsActivityCompletedOnSuccess": action_def.get("complete_activity_on_success", False),
            }

            try:
                action_id = client.post("WorkflowActionTypes", action_data)
                result.add("ActionType", action_def["name"], action_id)
            except Exception as e:
                result.fail("ActionType", action_def["name"], e)
                result.report()
                return result

            set_attribute_values(client, "WorkflowActionTypes", action_id,
                                action_def.get("settings", {}))

            # Create form if specified
            form_def = action_def.get("form")
            if form_def:
                form_data = {
                    "WorkflowActionTypeId": action_id,
                    "Header": form_def.get("header", ""),
                    "Footer": form_def.get("footer", ""),
                    "AllowNotes": form_def.get("allow_notes", False),
                }

                try:
                    form_id = client.post("WorkflowActionForms", form_data)
                    result.add("Form", f"form on {action_def['name']}", form_id)
                except Exception as e:
                    result.fail("Form", f"form on {action_def['name']}", e)
                    result.report()
                    return result

                # Form attributes (fields shown on the form)
                for field_order, field_key in enumerate(form_def.get("attributes", [])):
                    attr_id = attr_ids.get(field_key)
                    if not attr_id:
                        print(f"  Warning: form attribute '{field_key}' not found in workflow attributes")
                        continue

                    form_attr_data = {
                        "WorkflowActionFormId": form_id,
                        "AttributeId": attr_id,
                        "Order": field_order,
                        "IsVisible": True,
                        "IsReadOnly": False,
                        "IsRequired": True,
                        "HideLabel": False,
                    }

                    try:
                        fa_id = client.post("WorkflowActionFormAttributes", form_attr_data)
                        result.add("FormAttribute", field_key, fa_id)
                    except Exception as e:
                        result.fail("FormAttribute", field_key, e)
                        result.report()
                        return result

    result.report()
    return result


def create_page(plan, client, catalog):
    """Create a page with route and blocks."""
    result = BuildResult()
    pg = plan["page"]

    # Resolve layout
    layout_id = pg.get("layout_id")
    if not layout_id and "layout" in pg:
        layout_id = resolve_layout(catalog, pg["layout"])
    if not layout_id:
        result.fail("Page", pg["name"], "Could not resolve layout")
        result.report()
        return result

    # Resolve parent page
    parent_id = pg.get("parent_page_id")
    if not parent_id and "parent_page" in pg:
        routes = client.get("PageRoutes", params={
            "$filter": f"Route eq '{pg['parent_page'].lstrip('/')}'",
            "$select": "PageId",
            "$top": 1,
        })
        if routes:
            parent_id = routes[0]["PageId"]

    # 1. Create Page
    page_data = {
        "InternalName": pg["name"],
        "PageTitle": pg.get("title", pg["name"]),
        "LayoutId": layout_id,
        "DisplayInNavWhen": pg.get("display_in_nav", 2),  # 2 = When Allowed
        "IsSystem": False,
    }
    if parent_id:
        page_data["ParentPageId"] = parent_id

    try:
        page_id = client.post("Pages", page_data)
        result.add("Page", pg["name"], page_id)
    except Exception as e:
        result.fail("Page", pg["name"], e)
        result.report()
        return result

    # 2. Create route
    route = pg.get("route")
    if route:
        try:
            route_id = client.post("PageRoutes", {
                "PageId": page_id,
                "Route": route.lstrip("/"),
            })
            result.add("PageRoute", route, route_id)
        except Exception as e:
            result.fail("PageRoute", route, e)
            result.report()
            return result

    # 3. Create blocks
    for block_order, block_def in enumerate(pg.get("blocks", [])):
        block_type_id = block_def.get("block_type_id")
        if not block_type_id:
            block_type_id = resolve_block_type(catalog, block_def["block_type"])
        if not block_type_id:
            result.fail("Block", block_def.get("name", "unknown"),
                        f"Unknown block type: {block_def.get('block_type')}")
            result.report()
            return result

        block_data = {
            "PageId": page_id,
            "BlockTypeId": block_type_id,
            "Zone": block_def.get("zone", "Main"),
            "Name": block_def.get("name", ""),
            "Order": block_def.get("order", block_order),
            "IsSystem": False,
        }

        try:
            block_id = client.post("Blocks", block_data)
            result.add("Block", block_def.get("name", f"block-{block_order}"), block_id)
        except Exception as e:
            result.fail("Block", block_def.get("name", f"block-{block_order}"), e)
            result.report()
            return result

        set_attribute_values(client, "Blocks", block_id,
                            block_def.get("settings", {}))

    result.report()
    return result


def add_workflow_action(plan, client, catalog):
    """Add an action to an existing workflow activity."""
    result = BuildResult()
    mod = plan["modification"]
    activity_id = mod["activity_type_id"]
    action_def = mod["action"]

    entity_type_id = resolve_action_type(catalog, action_def["action_type"])
    if not entity_type_id:
        result.fail("ActionType", action_def["name"],
                     f"Unknown action type: {action_def['action_type']}")
        result.report()
        return result

    next_order = _next_order(client, "WorkflowActionTypes", f"ActivityTypeId eq {activity_id}")

    action_data = {
        "ActivityTypeId": activity_id,
        "Name": action_def["name"],
        "EntityTypeId": entity_type_id,
        "Order": action_def.get("order", next_order),
        "IsActionCompletedOnSuccess": action_def.get("complete_on_success", True),
        "IsActivityCompletedOnSuccess": action_def.get("complete_activity_on_success", False),
    }

    try:
        action_id = client.post("WorkflowActionTypes", action_data)
        result.add("ActionType", action_def["name"], action_id)
    except Exception as e:
        result.fail("ActionType", action_def["name"], e)
        result.report()
        return result

    set_attribute_values(client, "WorkflowActionTypes", action_id,
                        action_def.get("settings", {}))

    result.report()
    return result


def add_page_block(plan, client, catalog):
    """Add a block to an existing page."""
    result = BuildResult()
    mod = plan["modification"]
    page_id = mod["page_id"]
    block_def = mod["block"]

    block_type_id = block_def.get("block_type_id")
    if not block_type_id:
        block_type_id = resolve_block_type(catalog, block_def["block_type"])
    if not block_type_id:
        result.fail("Block", block_def.get("name", "unknown"),
                     f"Unknown block type: {block_def.get('block_type')}")
        result.report()
        return result

    zone = block_def.get("zone", "Main")
    next_order = _next_order(client, "Blocks", f"PageId eq {page_id} and Zone eq '{odata_str(zone)}'")

    block_data = {
        "PageId": page_id,
        "BlockTypeId": block_type_id,
        "Zone": zone,
        "Name": block_def.get("name", ""),
        "Order": block_def.get("order", next_order),
        "IsSystem": False,
    }

    try:
        block_id = client.post("Blocks", block_data)
        result.add("Block", block_def.get("name", "new block"), block_id)
    except Exception as e:
        result.fail("Block", block_def.get("name", "new block"), e)
        result.report()
        return result

    set_attribute_values(client, "Blocks", block_id,
                        block_def.get("settings", {}))

    result.report()
    return result


def update_workflow(plan, client, catalog):
    """Update properties on an existing workflow type."""
    result = BuildResult()
    mod = plan["modification"]
    wf_id = mod["workflow_type_id"]
    updates = mod["updates"]

    field_map = {
        "name": "Name", "description": "Description", "is_active": "IsActive",
        "is_persisted": "IsPersisted", "processing_interval": "ProcessingIntervalSeconds",
    }

    data = {}
    for key, value in updates.items():
        if key == "category":
            cat_id = resolve_category(client, value)
            if cat_id:
                data["CategoryId"] = cat_id
            else:
                result.fail("WorkflowType", str(wf_id), f"Category not found: {value}")
                result.report()
                return result
        else:
            data[field_map.get(key, key)] = value

    try:
        client.put(f"WorkflowTypes/{wf_id}", data)
        result.add("WorkflowType", f"updated {wf_id}", wf_id)
    except Exception as e:
        result.fail("WorkflowType", str(wf_id), e)

    result.report()
    return result


def update_activity(plan, client, catalog):
    """Update properties on an existing workflow activity."""
    result = BuildResult()
    mod = plan["modification"]
    act_id = mod["activity_type_id"]
    updates = mod["updates"]

    field_map = {
        "name": "Name", "description": "Description",
        "is_activated_with_workflow": "IsActivatedWithWorkflow",
        "order": "Order", "is_active": "IsActive",
    }

    data = {field_map.get(k, k): v for k, v in updates.items()}

    try:
        client.put(f"WorkflowActivityTypes/{act_id}", data)
        result.add("ActivityType", f"updated {act_id}", act_id)
    except Exception as e:
        result.fail("ActivityType", str(act_id), e)

    result.report()
    return result


def update_action(plan, client, catalog):
    """Update properties and/or settings on an existing workflow action."""
    result = BuildResult()
    mod = plan["modification"]
    action_id = mod["action_type_id"]

    updates = mod.get("updates", {})
    if updates:
        field_map = {
            "name": "Name", "order": "Order",
            "complete_on_success": "IsActionCompletedOnSuccess",
            "complete_activity_on_success": "IsActivityCompletedOnSuccess",
        }

        data = {}
        for key, value in updates.items():
            if key == "action_type":
                entity_type_id = resolve_action_type(catalog, value)
                if entity_type_id:
                    data["EntityTypeId"] = entity_type_id
                else:
                    result.fail("ActionType", str(action_id), f"Unknown action type: {value}")
                    result.report()
                    return result
            else:
                data[field_map.get(key, key)] = value

        try:
            client.put(f"WorkflowActionTypes/{action_id}", data)
            result.add("ActionType", f"updated {action_id}", action_id)
        except Exception as e:
            result.fail("ActionType", str(action_id), e)
            result.report()
            return result

    settings = mod.get("settings", {})
    if settings:
        set_attribute_values(client, "WorkflowActionTypes", action_id, settings)
        result.add("Settings", f"updated on {action_id}", action_id)

    result.report()
    return result


def delete_action(plan, client, catalog):
    """Delete a workflow action."""
    result = BuildResult()
    action_id = plan["modification"]["action_type_id"]

    try:
        client.delete(f"WorkflowActionTypes/{action_id}")
        result.add("ActionType", f"deleted {action_id}", action_id)
    except Exception as e:
        result.fail("ActionType", str(action_id), e)

    result.report()
    return result


def delete_activity(plan, client, catalog):
    """Delete a workflow activity and all its actions."""
    result = BuildResult()
    act_id = plan["modification"]["activity_type_id"]

    actions = client.get("WorkflowActionTypes", params={
        "$filter": f"ActivityTypeId eq {act_id}",
        "$select": "Id,Name",
    })

    for action in (actions or []):
        try:
            client.delete(f"WorkflowActionTypes/{action['Id']}")
            result.add("ActionType", f"deleted {action['Name']}", action["Id"])
        except Exception as e:
            result.fail("ActionType", action.get("Name", str(action["Id"])), e)
            result.report()
            return result

    try:
        client.delete(f"WorkflowActivityTypes/{act_id}")
        result.add("ActivityType", f"deleted {act_id}", act_id)
    except Exception as e:
        result.fail("ActivityType", str(act_id), e)

    result.report()
    return result


def reorder_actions(plan, client, catalog):
    """Set new ordering on actions within an activity."""
    result = BuildResult()
    mod = plan["modification"]

    for i, action_id in enumerate(mod["action_order"]):
        try:
            client.put(f"WorkflowActionTypes/{action_id}", {"Order": i})
            result.add("ActionType", f"reordered {action_id} -> {i}", action_id)
        except Exception as e:
            result.fail("ActionType", str(action_id), e)
            result.report()
            return result

    result.report()
    return result


def move_action(plan, client, catalog):
    """Move an action to a different activity."""
    result = BuildResult()
    mod = plan["modification"]
    action_id = mod["action_type_id"]
    new_activity_id = mod["target_activity_type_id"]

    next_order = _next_order(client, "WorkflowActionTypes", f"ActivityTypeId eq {new_activity_id}")

    try:
        client.put(f"WorkflowActionTypes/{action_id}", {
            "ActivityTypeId": new_activity_id,
            "Order": mod.get("order", next_order),
        })
        result.add("ActionType", f"moved {action_id} to activity {new_activity_id}", action_id)
    except Exception as e:
        result.fail("ActionType", str(action_id), e)

    result.report()
    return result


def create_checkin_area(plan, client, catalog):
    """Create a check-in area group with location and schedule links.

    Plan format:
    {
        "operation": "create_checkin_area",
        "checkin_area": {
            "name": "Navigation Check-in",
            "group_type_id": 15,       // or "group_type": "Check in by Age"
            "parent_group_id": 123,     // optional, nest under existing area
            "campus_id": 1,             // optional
            "description": "...",       // optional
            "locations": [42, {"name": "Room 101"}],  // location IDs or names
            "schedules": [99, {"name": "Sunday 9am"}] // schedule IDs or names
        }
    }
    """
    result = BuildResult()
    area = plan["checkin_area"]

    # Resolve group type
    group_type_id = area.get("group_type_id")
    if not group_type_id and "group_type" in area:
        gts = client.get("GroupTypes", params={
            "$filter": f"substringof('{odata_str(area['group_type'])}', Name) eq true",
            "$select": "Id",
            "$top": 1,
        })
        if gts:
            group_type_id = gts[0]["Id"]

    if not group_type_id:
        result.fail("Group", area["name"], "Could not resolve GroupType")
        result.report()
        return result

    # Create group
    group_data = {
        "Name": area["name"],
        "GroupTypeId": group_type_id,
        "IsActive": True,
        "IsPublic": area.get("is_public", True),
    }
    if area.get("parent_group_id"):
        group_data["ParentGroupId"] = area["parent_group_id"]
    if area.get("campus_id"):
        group_data["CampusId"] = area["campus_id"]
    if area.get("description"):
        group_data["Description"] = area["description"]

    try:
        group_id = client.post("Groups", group_data)
        result.add("Group", area["name"], group_id)
    except Exception as e:
        result.fail("Group", area["name"], e)
        result.report()
        return result

    # Link locations
    for loc_ref in area.get("locations", []):
        loc_id = loc_ref if isinstance(loc_ref, int) else None
        if not loc_id and isinstance(loc_ref, dict):
            loc_name = loc_ref.get("name", "")
            if loc_name:
                locs = client.get("Locations", params={
                    "$filter": f"Name eq '{odata_str(loc_name)}'",
                    "$select": "Id",
                    "$top": 1,
                })
                if locs:
                    loc_id = locs[0]["Id"]
        if loc_id:
            try:
                gl_id = client.post("GroupLocations", {
                    "GroupId": group_id,
                    "LocationId": loc_id,
                })
                result.add("GroupLocation", f"location {loc_id}", gl_id)
            except Exception as e:
                result.fail("GroupLocation", str(loc_id), e)
                result.report()
                return result

    # Link schedules via group's ScheduleId (single) or GroupSchedules
    schedules = area.get("schedules", [])
    if schedules:
        # Resolve first schedule as primary
        first = schedules[0]
        sched_id = first if isinstance(first, int) else None
        if not sched_id and isinstance(first, dict):
            sname = first.get("name", "")
            if sname:
                found = client.get("Schedules", params={
                    "$filter": f"substringof('{odata_str(sname)}', Name) eq true",
                    "$select": "Id",
                    "$top": 1,
                })
                if found:
                    sched_id = found[0]["Id"]
        if sched_id:
            try:
                client.put(f"Groups/{group_id}", {"ScheduleId": sched_id})
                result.add("Schedule", f"schedule {sched_id} on group", group_id)
            except Exception as e:
                result.fail("Schedule", str(sched_id), e)
                result.report()
                return result

    result.report()
    return result


def main():
    # Read build plan from stdin or file argument
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        plan_path = Path(sys.argv[1]).resolve()
        allowed = Path("/tmp").resolve()
        if not plan_path.is_relative_to(allowed):
            print(f"Error: build plan must be under /tmp/, got: {plan_path}")
            sys.exit(1)
        try:
            with open(plan_path) as f:
                plan = json.load(f)
        except FileNotFoundError:
            print(f"Error: file not found: {plan_path}")
            sys.exit(1)
    else:
        plan = json.load(sys.stdin)

    catalog = load_catalog()
    if not catalog:
        print("Error: no catalog found. Refresh it: rock_catalog.py refresh")
        sys.exit(1)
    client = RockClient()

    operations = {
        "create_workflow": create_workflow,
        "create_page": create_page,
        "add_action": add_workflow_action,
        "add_block": add_page_block,
        "update_workflow": update_workflow,
        "update_activity": update_activity,
        "update_action": update_action,
        "delete_action": delete_action,
        "delete_activity": delete_activity,
        "reorder_actions": reorder_actions,
        "move_action": move_action,
        "create_checkin_area": create_checkin_area,
    }

    operation = plan.get("operation")
    log.info("build operation=%s", operation)
    handler = operations.get(operation)
    if not handler:
        print(f"Error: unknown operation: {operation}")
        print(f"Supported: {', '.join(operations)}")
        sys.exit(1)
    result = handler(plan, client, catalog)

    if not result.success:
        sys.exit(1)


if __name__ == "__main__":
    main()
