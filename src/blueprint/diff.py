"""What changes between two blueprints (shown to the user before a change is saved)."""

from typing import Any, Dict, List

from src.blueprint.schema import Blueprint


def _names(blueprint: Blueprint) -> Dict[str, str]:
    return {key: node.label for key, node in blueprint.nodes().items()}


def diff_blueprints(old: Blueprint, new: Blueprint) -> Dict[str, Any]:
    old_nodes, new_nodes = old.nodes(), new.nodes()
    old_parents, new_parents = old.parents(), new.parents()

    added = sorted(set(new_nodes) - set(old_nodes))
    removed = sorted(set(old_nodes) - set(new_nodes))
    common = set(old_nodes) & set(new_nodes)
    renamed = [
        {"key": k, "from": old_nodes[k].label, "to": new_nodes[k].label}
        for k in sorted(common) if old_nodes[k].label != new_nodes[k].label
    ]
    moved = [
        {"key": k, "from": old_parents[k], "to": new_parents[k]}
        for k in sorted(common) if old_parents[k] != new_parents[k]
    ]
    kind_changed = [k for k in sorted(common) if old_nodes[k].kind != new_nodes[k].kind]

    def by_key(items: List[Any]) -> Dict[str, Any]:
        return {i.key: i for i in items}

    old_groups, new_groups = by_key(old.groups), by_key(new.groups)
    groups_changed = [
        k for k in sorted(set(old_groups) & set(new_groups))
        if sorted(old_groups[k].members) != sorted(new_groups[k].members)
    ]
    old_rules = {(r.pattern.lower(), r.category) for r in old.rules}
    new_rules = {(r.pattern.lower(), r.category) for r in new.rules}

    diff = {
        "name_changed": old.name != new.name,
        "instructions_changed": old.instructions != new.instructions,
        "categories": {
            "added": [{"key": k, "label": new_nodes[k].label} for k in added],
            "removed": [{"key": k, "label": old_nodes[k].label} for k in removed],
            "renamed": renamed,
            "moved": moved,
            "kind_changed": kind_changed,
        },
        "groups": {
            "added": sorted(set(new_groups) - set(old_groups)),
            "removed": sorted(set(old_groups) - set(new_groups)),
            "changed": groups_changed,
        },
        "dimensions": {
            "added": sorted(set(by_key(new.dimensions)) - set(by_key(old.dimensions))),
            "removed": sorted(set(by_key(old.dimensions)) - set(by_key(new.dimensions))),
        },
        "rules": {"added": len(new_rules - old_rules), "removed": len(old_rules - new_rules)},
    }
    diff["is_empty"] = not (
        diff["name_changed"] or diff["instructions_changed"] or added or removed or renamed or moved or kind_changed
        or groups_changed or diff["groups"]["added"] or diff["groups"]["removed"]
        or diff["dimensions"]["added"] or diff["dimensions"]["removed"]
        or diff["rules"]["added"] or diff["rules"]["removed"]
    )
    return diff
