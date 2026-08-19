"""Build Rock RMS entities from JSON definitions.

Reads a JSON build plan from stdin or a file and creates entities via the Rock API.
Handles sequential creation with parent-child ID dependencies.

Usage:
  echo '{"operation": "create_workflow", ...}' | uv run scripts/rock_build.py
  uv run scripts/rock_build.py /tmp/build-plan.json

Reached only through rock-build's rock.sh, which sets ROCK_ALLOW_WRITES; every
operation here refuses without it (ADR 0016).

Partial updates use PATCH, never PUT. RockClient.put explains why at length —
the short version is that Rock's PUT replaces the whole entity, so a partial
body nulls the fields you left out, wipes the created-by audit, and gives the
row a new Guid.
"""

import json
import os
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


def resolve_group_type(client, name):
    """Find a GroupType ID by name (substring match, as check-in areas rely on)."""
    gts = client.get("GroupTypes", params={
        "$filter": f"substringof('{odata_str(name)}', Name) eq true",
        "$select": "Id",
        "$top": 1,
    })
    return gts[0]["Id"] if gts else None


def resolve_group_role(client, group_id, role_name):
    """Find a GroupTypeRole ID by name, within the group's own type.

    Role names are only unique inside a group type — "Member" and "Leader"
    exist many times over — so the group's GroupTypeId has to come first.
    """
    group = client.get(f"Groups/{group_id}", params={"$select": "GroupTypeId"})
    if not group or not group.get("GroupTypeId"):
        return None
    roles = client.get("GroupTypeRoles", params={
        "$filter": f"GroupTypeId eq {group['GroupTypeId']} and "
                   f"Name eq '{odata_str(role_name)}'",
        "$select": "Id",
        "$top": 1,
    })
    return roles[0]["Id"] if roles else None


def resolve_data_view(client, name):
    """Find a DataView ID by name."""
    views = client.get("DataViews", params={
        "$filter": f"Name eq '{odata_str(name)}'",
        "$select": "Id",
        "$top": 1,
    })
    return views[0]["Id"] if views else None


# Rock.Model.GroupMemberStatus. Sending nothing means 0 — Inactive — so every
# code path here sets it explicitly.
MEMBER_STATUS = {"inactive": 0, "active": 1, "pending": 2}


def member_status(value):
    """Map a status name to its enum value. Returns None if it is not one."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value in MEMBER_STATUS.values() else None
    return MEMBER_STATUS.get(str(value).strip().lower())


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
    """Set attribute values on an entity.

    Rock routes this one by convention, not by OData, and binds both arguments
    from the query string: POST /api/{Entity}/AttributeValue/{id} with
    attributeKey and attributeValue. Neither is optional — omit attributeKey and
    the request stops matching the route at all and 404s.

    An unrecognised key is a 400 and nothing is written, so a failure here has
    to propagate. The version this replaced sent a JSON body to two routes that
    do not exist, caught both 404s, printed `Warning: could not set X`, and let
    the entity count as created — which is how a workflow could be reported
    built with not one of its actions configured.
    """
    for attr_key, attr_value in settings.items():
        client.post(f"{endpoint}/AttributeValue/{entity_id}", params={
            "attributeKey": attr_key,
            "attributeValue": "" if attr_value is None else str(attr_value),
        })


def apply_settings(result, client, endpoint, entity_id, label, settings):
    """set_attribute_values, with any failure recorded on the build result.

    Returns False when a setting did not land. The caller must stop there: the
    entity exists but is not configured, and reporting success anyway is the
    failure mode this whole function exists to prevent.
    """
    if not settings:
        return True
    try:
        set_attribute_values(client, endpoint, entity_id, settings)
        return True
    except Exception as e:
        result.fail("Settings", label, e)
        result.report()
        return False


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

            if not apply_settings(result, client, "WorkflowActionTypes", action_id,
                                  action_def["name"], action_def.get("settings", {})):
                return result

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

        if not apply_settings(result, client, "Blocks", block_id,
                              block_def.get("name", f"block-{block_order}"),
                              block_def.get("settings", {})):
            return result

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

    if not apply_settings(result, client, "WorkflowActionTypes", action_id,
                          action_def["name"], action_def.get("settings", {})):
        return result

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

    if not apply_settings(result, client, "Blocks", block_id,
                          block_def.get("name", "new block"),
                          block_def.get("settings", {})):
        return result

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
        client.patch(f"WorkflowTypes/{wf_id}", data)
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
        client.patch(f"WorkflowActivityTypes/{act_id}", data)
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
            client.patch(f"WorkflowActionTypes/{action_id}", data)
            result.add("ActionType", f"updated {action_id}", action_id)
        except Exception as e:
            result.fail("ActionType", str(action_id), e)
            result.report()
            return result

    settings = mod.get("settings", {})
    if settings:
        if not apply_settings(result, client, "WorkflowActionTypes", action_id,
                              str(action_id), settings):
            return result
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
            client.patch(f"WorkflowActionTypes/{action_id}", {"Order": i})
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
        client.patch(f"WorkflowActionTypes/{action_id}", {
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
        group_type_id = resolve_group_type(client, area["group_type"])

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
                client.patch(f"Groups/{group_id}", {"ScheduleId": sched_id})
                result.add("Schedule", f"schedule {sched_id} on group", group_id)
            except Exception as e:
                result.fail("Schedule", str(sched_id), e)
                result.report()
                return result

    result.report()
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Groups
#
# Group work was the gap that sent people back to older tooling: rock-build
# could create a check-in area, which is a Group, and then had no way to touch
# a group, its members, or its sync. These are the operations that were
# missing, not a new abstraction over them.
# ─────────────────────────────────────────────────────────────────────────────

GROUP_FIELDS = {
    "name": "Name", "description": "Description", "is_active": "IsActive",
    "is_public": "IsPublic", "is_security_role": "IsSecurityRole",
    "campus_id": "CampusId", "parent_group_id": "ParentGroupId",
    "schedule_id": "ScheduleId", "group_capacity": "GroupCapacity",
    "order": "Order",
}


def create_group(plan, client, catalog):
    """Create a group.

    Plan format:
    {
        "operation": "create_group",
        "group": {
            "name": "Guest Services",
            "group_type": "Serving Team",   // or "group_type_id": 25
            "parent_group_id": 8,           // optional
            "campus_id": 1,                 // optional
            "description": "...",           // optional
            "settings": {"AllowGuests": "True"}   // optional attribute values
        }
    }
    """
    result = BuildResult()
    grp = plan["group"]

    group_type_id = grp.get("group_type_id")
    if not group_type_id and grp.get("group_type"):
        group_type_id = resolve_group_type(client, grp["group_type"])
    if not group_type_id:
        result.fail("Group", grp["name"],
                    f"Could not resolve GroupType: {grp.get('group_type')}")
        result.report()
        return result

    data = {
        "Name": grp["name"],
        "GroupTypeId": group_type_id,
        "IsActive": grp.get("is_active", True),
        "IsPublic": grp.get("is_public", True),
        "IsSecurityRole": grp.get("is_security_role", False),
        "Order": grp.get("order", 0),
    }
    for key in ("parent_group_id", "campus_id", "description", "schedule_id",
                "group_capacity"):
        if grp.get(key) is not None:
            data[GROUP_FIELDS[key]] = grp[key]

    try:
        group_id = client.post("Groups", data)
        result.add("Group", grp["name"], group_id)
    except Exception as e:
        result.fail("Group", grp["name"], e)
        result.report()
        return result

    if not apply_settings(result, client, "Groups", group_id, grp["name"],
                          grp.get("settings", {})):
        return result

    result.report()
    return result


def update_group(plan, client, catalog):
    """Update properties on an existing group.

    Plan format:
    {
        "operation": "update_group",
        "modification": {"group_id": 31, "updates": {"name": "...", "is_active": false}}
    }
    """
    result = BuildResult()
    mod = plan["modification"]
    group_id = mod["group_id"]

    data = {GROUP_FIELDS.get(k, k): v for k, v in mod["updates"].items()}
    if not data:
        result.fail("Group", str(group_id), "No fields to update")
        result.report()
        return result

    try:
        client.patch(f"Groups/{group_id}", data)
        result.add("Group", f"updated {group_id}", group_id)
    except Exception as e:
        result.fail("Group", str(group_id), e)
        result.report()
        return result

    if not apply_settings(result, client, "Groups", group_id, str(group_id),
                          mod.get("settings", {})):
        return result

    result.report()
    return result


def add_group_member(plan, client, catalog):
    """Add a person to a group.

    Plan format:
    {
        "operation": "add_group_member",
        "modification": {
            "group_id": 31,
            "person_id": 42,
            "role": "Leader",        // or "group_role_id": 3
            "status": "active",      // active | inactive | pending
            "note": "..."            // optional
        }
    }

    Rock validates this on save — a duplicate member, or one who fails the
    group's requirements, comes back as a validation error rather than a
    silent success.
    """
    result = BuildResult()
    mod = plan["modification"]
    group_id = mod["group_id"]
    person_id = mod["person_id"]
    label = f"person {person_id} in group {group_id}"

    role_id = mod.get("group_role_id")
    if not role_id and mod.get("role"):
        role_id = resolve_group_role(client, group_id, mod["role"])
    if not role_id:
        result.fail("GroupMember", label,
                    f"Could not resolve role {mod.get('role')!r} in group {group_id}")
        result.report()
        return result

    status = member_status(mod.get("status", "active"))
    if status is None:
        result.fail("GroupMember", label,
                    f"Unknown status {mod.get('status')!r} — "
                    f"expected one of {', '.join(MEMBER_STATUS)}")
        result.report()
        return result

    data = {
        "GroupId": group_id,
        "PersonId": person_id,
        "GroupRoleId": role_id,
        "GroupMemberStatus": status,
        "IsNotified": mod.get("is_notified", False),
        "IsArchived": False,
    }
    if mod.get("note"):
        data["Note"] = mod["note"]
    if mod.get("order") is not None:
        data["GroupOrder"] = mod["order"]

    try:
        member_id = client.post("GroupMembers", data)
        result.add("GroupMember", label, member_id)
    except Exception as e:
        result.fail("GroupMember", label, e)

    result.report()
    return result


GROUP_MEMBER_FIELDS = {
    "role": "GroupRoleId", "group_role_id": "GroupRoleId", "note": "Note",
    "is_notified": "IsNotified", "is_archived": "IsArchived",
    "order": "GroupOrder", "guest_count": "GuestCount",
}


def update_group_member(plan, client, catalog):
    """Update a group membership — its role, status, or note.

    Plan format:
    {
        "operation": "update_group_member",
        "modification": {"group_member_id": 88, "updates": {"status": "inactive"}}
    }
    """
    result = BuildResult()
    mod = plan["modification"]
    member_id = mod["group_member_id"]

    data = {}
    for key, value in mod["updates"].items():
        if key == "status":
            status = member_status(value)
            if status is None:
                result.fail("GroupMember", str(member_id),
                            f"Unknown status {value!r} — "
                            f"expected one of {', '.join(MEMBER_STATUS)}")
                result.report()
                return result
            data["GroupMemberStatus"] = status
        else:
            data[GROUP_MEMBER_FIELDS.get(key, key)] = value

    if not data:
        result.fail("GroupMember", str(member_id), "No fields to update")
        result.report()
        return result

    try:
        client.patch(f"GroupMembers/{member_id}", data)
        result.add("GroupMember", f"updated {member_id}", member_id)
    except Exception as e:
        result.fail("GroupMember", str(member_id), e)

    result.report()
    return result


def remove_group_member(plan, client, catalog):
    """Delete a group membership.

    Plan format:
    {
        "operation": "remove_group_member",
        "modification": {"group_member_id": 88}
    }

    This deletes the row. Groups whose type keeps history expect an archive
    instead, which is `update_group_member` with `{"is_archived": true}` —
    the history and the attendance stay attached that way.
    """
    result = BuildResult()
    member_id = plan["modification"]["group_member_id"]

    try:
        client.delete(f"GroupMembers/{member_id}")
        result.add("GroupMember", f"removed {member_id}", member_id)
    except Exception as e:
        result.fail("GroupMember", str(member_id), e)

    result.report()
    return result


def create_group_sync(plan, client, catalog):
    """Point a group's role at a data view, so Rock keeps the roster in step.

    Plan format:
    {
        "operation": "create_group_sync",
        "modification": {
            "group_id": 31,
            "role": "Member",                  // or "group_type_role_id": 3
            "data_view": "Active Adults",      // or "sync_data_view_id": 71
            "add_user_accounts": false,        // optional
            "schedule_interval_minutes": 720,  // optional
            "welcome_email_id": 4,             // optional SystemCommunication
            "exit_email_id": 5                 // optional SystemCommunication
        }
    }
    """
    result = BuildResult()
    mod = plan["modification"]
    group_id = mod["group_id"]
    label = f"sync on group {group_id}"

    role_id = mod.get("group_type_role_id")
    if not role_id and mod.get("role"):
        role_id = resolve_group_role(client, group_id, mod["role"])
    if not role_id:
        result.fail("GroupSync", label,
                    f"Could not resolve role {mod.get('role')!r} in group {group_id}")
        result.report()
        return result

    data_view_id = mod.get("sync_data_view_id")
    if not data_view_id and mod.get("data_view"):
        data_view_id = resolve_data_view(client, mod["data_view"])
    if not data_view_id:
        result.fail("GroupSync", label,
                    f"Could not resolve data view {mod.get('data_view')!r}")
        result.report()
        return result

    data = {
        "GroupId": group_id,
        "GroupTypeRoleId": role_id,
        "SyncDataViewId": data_view_id,
    }
    for key, field in (("add_user_accounts", "AddUserAccountsDuringSync"),
                       ("schedule_interval_minutes", "ScheduleIntervalMinutes"),
                       ("welcome_email_id", "WelcomeSystemCommunicationId"),
                       ("exit_email_id", "ExitSystemCommunicationId")):
        if mod.get(key) is not None:
            data[field] = mod[key]

    try:
        sync_id = client.post("GroupSyncs", data)
        result.add("GroupSync", label, sync_id)
    except Exception as e:
        result.fail("GroupSync", label, e)

    result.report()
    return result


# ─────────────────────────────────────────────────────────────────────────────
# The escape hatch
# ─────────────────────────────────────────────────────────────────────────────

API_METHODS = ("GET", "POST", "PATCH", "PUT", "DELETE")


def api_request(plan, client, catalog):
    """Send one arbitrary request to the Rock API.

    Every named operation above encodes what Rock wants for one kind of change.
    Rock has hundreds of entities and this plugin covers a dozen, so without a
    way out, anything uncovered means no answer at all — which is what drove
    people back to tooling most of the department does not have. This is that
    way out. It is deliberately thin: no field maps, no name resolution, no
    conveniences. What you write is what Rock receives.

    Plan format:
    {
        "operation": "api_request",
        "request": {
            "method": "PATCH",
            "endpoint": "GroupRequirements/12",
            "params": {"attributeKey": "..."},   // optional query string
            "body": {"...": "..."},              // optional JSON body
            "full_replace": true                 // required for PUT only
        }
    }

    PUT needs `full_replace: true` and a body holding the entity's every field,
    Id and Guid and CreatedDateTime included. That is not ceremony: Rock's PUT
    replaces the row, so a partial body is the bug this operation was written
    alongside. GET is here because reading the entity is the only way to build
    that body honestly.
    """
    result = BuildResult()
    req = plan.get("request") or {}
    method = str(req.get("method", "")).strip().upper()
    endpoint = str(req.get("endpoint", "")).strip()
    label = f"{method} {endpoint}".strip() or "api_request"

    if method not in API_METHODS:
        result.fail("Request", label,
                    f"method must be one of {', '.join(API_METHODS)}, got {method!r}")
        result.report()
        return result

    if not endpoint:
        result.fail("Request", label, "endpoint is required, e.g. \"GroupSyncs/12\"")
        result.report()
        return result

    # An endpoint is a path under /api/, and nothing else. Anything that could
    # aim the authenticated session somewhere else, or climb out of /api/, is
    # refused rather than normalised.
    if "://" in endpoint or endpoint.startswith("/") or ".." in endpoint.split("/"):
        result.fail("Request", label,
                    "endpoint must be a path under /api/ — no scheme, no leading "
                    "slash, no '..'")
        result.report()
        return result

    if method == "PUT" and req.get("full_replace") is not True:
        result.fail("Request", label,
                    "PUT replaces the whole entity in Rock: every field absent from "
                    "the body is set to null, the created-by audit is lost, and the "
                    "row gets a new Guid. Use PATCH to change some fields. If you "
                    "really mean to replace the entity, read it first and send it "
                    "back whole with \"full_replace\": true.")
        result.report()
        return result

    params = req.get("params")
    body = req.get("body")

    print(f"  {method} /api/{endpoint}" + (f"  params={params}" if params else ""))

    try:
        if method == "GET":
            print(json.dumps(client.get(endpoint, params=params), indent=2, default=str))
            result.add("Response", label, endpoint)
        elif method == "POST":
            result.add("Response", label, client.post(endpoint, body, params=params))
        elif method == "PATCH":
            client.patch(endpoint, body)
            result.add("Response", label, endpoint)
        elif method == "PUT":
            client.put(endpoint, body)
            result.add("Response", label, endpoint)
        else:
            client.delete(endpoint)
            result.add("Response", label, endpoint)
    except Exception as e:
        result.fail("Request", label, e)

    result.report()
    return result


def require_writes_enabled(operation):
    """Refuse to run unless ROCK_ALLOW_WRITES is set.

    rock-build's rock.sh sets it and is the only documented way in. Nothing
    else sets it — see ADR 0016. The check matters because both plugins install
    into the same runtime directory, so this script sits on disk beside the
    read-only ones and could otherwise be run by hand.
    """
    if os.environ.get("ROCK_ALLOW_WRITES") == "1":
        return
    print(
        f"Refusing to run '{operation}': everything in this script changes Rock, "
        f"and ROCK_ALLOW_WRITES is not set.\n"
        f"Run it through the rock-build plugin's rock.sh, which sets it.",
        file=sys.stderr,
    )
    sys.exit(2)


OPERATIONS = {
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
    "create_group": create_group,
    "update_group": update_group,
    "add_group_member": add_group_member,
    "update_group_member": update_group_member,
    "remove_group_member": remove_group_member,
    "create_group_sync": create_group_sync,
    "api_request": api_request,
}

# Operations that resolve a name through the catalog cache.
NEEDS_CATALOG = {"create_workflow", "create_page", "add_action", "add_block",
                 "update_action"}


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

    operation = plan.get("operation")
    handler = OPERATIONS.get(operation)
    if not handler:
        print(f"Error: unknown operation: {operation}")
        print(f"Supported: {', '.join(OPERATIONS)}")
        sys.exit(1)

    require_writes_enabled(operation)

    # The catalog resolves names to IDs for the things Rock does not let you
    # look up by name — action components, field types, block types, layouts.
    # Operations that resolve nothing should not be blocked by a stale or
    # missing cache.
    catalog = load_catalog()
    if catalog is None and operation in NEEDS_CATALOG:
        print("Error: no catalog found. Refresh it: rock_catalog.py refresh")
        sys.exit(1)

    client = RockClient()

    log.info("build operation=%s", operation)
    result = handler(plan, client, catalog or {})

    if not result.success:
        sys.exit(1)


if __name__ == "__main__":
    main()
