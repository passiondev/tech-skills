"""Rock RMS schema catalog -- introspect and cache available building blocks.

Usage:
  uv run scripts/rock_catalog.py refresh   # pull fresh catalog from Rock
  uv run scripts/rock_catalog.py show      # display catalog summary
  uv run scripts/rock_catalog.py status    # test connection
"""

import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from rock_client import RockClient, load_config
from rock_log import get_logger

log = get_logger("rock.catalog")

import rock_paths

rock_paths.ensure()
CATALOG_PATH = rock_paths.CATALOG


def load_catalog():
    try:
        with open(CATALOG_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def save_catalog(catalog):
    with open(CATALOG_PATH, "w") as f:
        json.dump(catalog, f, indent=2)


def fetch_action_components(client, config):
    """Pull workflow action component EntityTypes from Rock."""
    prefixes = config.get("catalog", {}).get("action_assemblies", ["Rock"])

    # Try EntityTypes with IsComponent filter (not available in all Rock versions)
    actions = []
    try:
        all_types = client.get("EntityTypes", params={
            "$filter": "IsComponent eq true",
            "$select": "Id,Name,FriendlyName,AssemblyName",
            "$top": 500,
        })
        if all_types:
            for et in all_types:
                name = et.get("Name", "")
                assembly = et.get("AssemblyName", "")
                if not any(name.startswith(f"{p}.Workflow.Action") for p in prefixes):
                    if "WorkflowAction" not in name:
                        continue
                actions.append({
                    "entity_type_id": et["Id"],
                    "name": et.get("FriendlyName") or name.split(".")[-1],
                    "class_name": name,
                    "assembly": assembly,
                })
    except (RuntimeError, ValueError) as e:
        log.info("IsComponent filter unavailable, will fall back: %s", e)

    # Fallback: scan existing workflow action types for their entity types
    if not actions:
        print("  Component filter empty, falling back to existing workflow scan...")
        existing = client.get("WorkflowActionTypes", params={
            "$select": "EntityTypeId",
            "$top": 1000,
        })
        if existing:
            seen_ids = set()
            entity_type_ids = []
            for wa in existing:
                eid = wa.get("EntityTypeId")
                if eid and eid not in seen_ids:
                    seen_ids.add(eid)
                    entity_type_ids.append(eid)
            for eid in entity_type_ids:
                try:
                    et = client.get(f"EntityTypes/{eid}")
                    if et:
                        actions.append({
                            "entity_type_id": et["Id"],
                            "name": et.get("FriendlyName") or et.get("Name", "").split(".")[-1],
                            "class_name": et.get("Name", ""),
                            "assembly": et.get("AssemblyName", ""),
                        })
                except Exception:
                    continue

    return sorted(actions, key=lambda a: a["name"])


def fetch_block_types(client):
    """Pull all registered BlockTypes."""
    blocks = client.get("BlockTypes", params={
        "$select": "Id,Name,Description,Category",
        "$top": 500,
        "$orderby": "Name",
    })
    if not blocks:
        return []
    return [{
        "id": b["Id"],
        "name": b.get("Name", ""),
        "description": b.get("Description", ""),
        "category": b.get("Category", ""),
    } for b in blocks]


def fetch_field_types(client):
    """Pull all registered FieldTypes."""
    fields = client.get("FieldTypes", params={
        "$select": "Id,Name,Description,Assembly,Class",
        "$top": 200,
        "$orderby": "Name",
    })
    if not fields:
        return []
    return [{
        "id": f["Id"],
        "name": f.get("Name", ""),
        "description": f.get("Description", ""),
        "class_name": f.get("Class", ""),
    } for f in fields]


def fetch_categories(client):
    """Pull workflow and page categories."""
    cats = client.get("Categories", params={
        "$select": "Id,Name,ParentCategoryId,EntityTypeId",
        "$top": 500,
        "$orderby": "Name",
    })
    if not cats:
        return []
    return [{
        "id": c["Id"],
        "name": c.get("Name", ""),
        "parent_id": c.get("ParentCategoryId"),
        "entity_type_id": c.get("EntityTypeId"),
    } for c in cats]


def fetch_sites(client):
    """Pull sites for page creation context."""
    sites = client.get("Sites", params={
        "$select": "Id,Name,IsActive",
        "$top": 20,
    })
    if not sites:
        return []
    return [{
        "id": s["Id"],
        "name": s.get("Name", ""),
        "is_active": s.get("IsActive", False),
    } for s in sites]


def fetch_layouts(client):
    """Pull page layouts."""
    layouts = client.get("Layouts", params={
        "$select": "Id,Name,SiteId,FileName",
        "$top": 100,
    })
    if not layouts:
        return []
    return [{
        "id": l["Id"],
        "name": l.get("Name", ""),
        "site_id": l.get("SiteId"),
        "file_name": l.get("FileName", ""),
    } for l in layouts]


def refresh(client):
    """Pull full catalog from Rock instance."""
    config = load_config()
    print("Refreshing Rock catalog...")

    print("  Fetching action components...")
    actions = fetch_action_components(client, config)
    print(f"    {len(actions)} action types")

    print("  Fetching block types...")
    blocks = fetch_block_types(client)
    print(f"    {len(blocks)} block types")

    print("  Fetching field types...")
    fields = fetch_field_types(client)
    print(f"    {len(fields)} field types")

    print("  Fetching categories...")
    categories = fetch_categories(client)
    print(f"    {len(categories)} categories")

    print("  Fetching sites...")
    sites = fetch_sites(client)
    print(f"    {len(sites)} sites")

    print("  Fetching layouts...")
    layouts = fetch_layouts(client)
    print(f"    {len(layouts)} layouts")

    catalog = {
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "instance_url": client.base_url,
        "action_components": actions,
        "block_types": blocks,
        "field_types": fields,
        "categories": categories,
        "sites": sites,
        "layouts": layouts,
    }

    save_catalog(catalog)
    log.info("catalog refreshed: %d actions, %d blocks, %d fields, %d categories",
             len(actions), len(blocks), len(fields), len(categories))
    print(f"\nCatalog saved to {CATALOG_PATH.name}")
    return catalog


def show():
    """Display catalog summary."""
    catalog = load_catalog()
    if not catalog:
        print("No catalog found. Refresh it: rock_catalog.py refresh")
        sys.exit(1)

    print(f"Rock RMS Catalog (refreshed: {catalog['refreshed_at'][:19]})")
    print(f"Instance: {catalog['instance_url']}\n")

    actions = catalog.get("action_components", [])
    print(f"Action Components ({len(actions)}):")
    for a in actions[:30]:
        print(f"  {a['name']:40s} {a['class_name']}")
    if len(actions) > 30:
        print(f"  ... and {len(actions) - 30} more")

    print()
    blocks = catalog.get("block_types", [])
    print(f"Block Types ({len(blocks)}):")
    for b in blocks[:20]:
        cat = f" [{b['category']}]" if b.get("category") else ""
        print(f"  {b['name']:40s}{cat}")
    if len(blocks) > 20:
        print(f"  ... and {len(blocks) - 20} more")

    print()
    fields = catalog.get("field_types", [])
    print(f"Field Types ({len(fields)}):")
    for f in fields[:15]:
        print(f"  {f['name']:40s}")
    if len(fields) > 15:
        print(f"  ... and {len(fields) - 15} more")

    print()
    sites = catalog.get("sites", [])
    print(f"Sites ({len(sites)}):")
    for s in sites:
        active = "active" if s.get("is_active") else "inactive"
        print(f"  {s['name']:40s} ({active})")


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run scripts/rock_catalog.py [status|refresh|show]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "status":
        client = RockClient()
        try:
            campuses = client.get("Campuses", params={"$top": 1})
            print(f"Connected to Rock RMS at {client.base_url}")
            if campuses:
                print(f"  Campus: {campuses[0].get('Name', 'unknown')}")
            # Try to get Rock version
            try:
                version = client.get("Utility/GetRockSemanticVersionNumber")
                if version:
                    print(f"  Version: {version}")
            except Exception:
                pass
            catalog = load_catalog()
            if catalog:
                print(f"  Catalog: {catalog['refreshed_at'][:19]}")
                print(f"  Actions: {len(catalog.get('action_components', []))}")
                print(f"  Blocks:  {len(catalog.get('block_types', []))}")
                print(f"  Fields:  {len(catalog.get('field_types', []))}")
            else:
                print("  Catalog: not cached (refresh it: rock_catalog.py refresh)")
        except Exception as e:
            print(f"Failed to connect: {e}")
            sys.exit(1)

    elif cmd == "refresh":
        client = RockClient()
        refresh(client)

    elif cmd == "show":
        show()

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
