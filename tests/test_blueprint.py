"""Blueprint schema: validation and navigation."""

import pytest
from pydantic import ValidationError

from src.blueprint import Blueprint, slugify

FAMILY = {
    "name": "Famiglia",
    "categories": [
        {"key": "figli", "label": "Figli", "children": [{"key": "scuola", "label": "Scuola"}, {"key": "sport", "label": "Sport"}]},
        {"key": "casa", "label": "Casa", "children": [{"key": "utenze", "label": "Utenze"}]},
        {"key": "svago", "label": "Svago", "children": [{"key": "ristoranti", "label": "Ristoranti"}, {"key": "shopping", "label": "Shopping"}]},
        {"key": "stipendio", "label": "Stipendio", "kind": "income"},
    ],
    "groups": [{"key": "minchiate", "label": "Minchiate", "members": ["svago"]}],
    "dimensions": [{"key": "per_chi", "label": "Per chi", "values": [{"key": "figli", "label": "Figli"}, {"key": "casa", "label": "Casa"}]}],
    "reports": [{"key": "spese_figli", "label": "Spese dei figli", "categories": ["figli"]}, {"key": "m", "label": "Minchiate", "group": "minchiate"}],
    "rules": [{"pattern": "esselunga", "category": "casa"}],
}


def make(**changes):
    return Blueprint.model_validate({**FAMILY, **changes})


def test_valid_blueprint_round_trips_through_json():
    blueprint = make()
    assert Blueprint.model_validate(blueprint.to_json()) == blueprint


def test_group_expands_to_descendants_and_leaves_are_listed():
    blueprint = make()
    assert blueprint.group_categories("minchiate") == {"svago", "ristoranti", "shopping"}
    assert blueprint.groups_of("ristoranti") == ["minchiate"]
    assert set(blueprint.leaf_keys()) == {"scuola", "sport", "utenze", "ristoranti", "shopping", "stipendio"}
    assert blueprint.descendants("figli") == {"figli", "scuola", "sport"}


def test_resolve_category_matches_keys_and_labels_ignoring_case_and_accents():
    blueprint = Blueprint.model_validate({"name": "x", "categories": [{"key": "caffe", "label": "Caffè"}]})
    assert blueprint.resolve_category("caffe") == "caffe"
    assert blueprint.resolve_category("CAFFÈ") == "caffe"
    assert blueprint.resolve_category("sconosciuta") is None


@pytest.mark.parametrize(
    "changes,message",
    [
        ({"categories": [{"key": "a", "label": "A"}, {"key": "a", "label": "B"}]}, "duplicate category key"),
        ({"categories": [{"key": "Bad Key", "label": "x"}]}, "lowercase"),
        ({"groups": [{"key": "g", "label": "G", "members": ["nope"]}]}, "unknown category"),
        ({"rules": [{"pattern": "x", "category": "nope"}]}, "unknown category"),
        ({"reports": [{"key": "r", "label": "R"}]}, "needs a group or a list"),
        ({"reports": [{"key": "r", "label": "R", "group": "nope"}]}, "unknown group"),
        ({"dimensions": [{"key": "d", "label": "D", "values": [{"key": "a", "label": "A"}, {"key": "a", "label": "B"}]}]}, "duplicate value"),
        ({"groups": [{"key": "g", "label": "G"}, {"key": "g", "label": "H"}]}, "duplicate group"),
    ],
)
def test_invalid_blueprints_are_rejected(changes, message):
    with pytest.raises(ValidationError, match=message):
        make(**changes)


def test_depth_is_limited():
    node = {"key": "n0", "label": "n"}
    for i in range(1, 6):
        node = {"key": f"n{i}", "label": "n", "children": [node]}
    with pytest.raises(ValidationError, match="deeper"):
        Blueprint.model_validate({"name": "x", "categories": [node]})


def test_attributes_are_a_free_extension_point():
    blueprint = Blueprint.model_validate(
        {"name": "Studio", "categories": [{"key": "ufficio", "label": "Ufficio", "attributes": {"deductible": True, "vat": 22}}]}
    )
    assert blueprint.nodes()["ufficio"].attributes == {"deductible": True, "vat": 22}


def test_from_category_names_builds_a_flat_blueprint_and_dedups_by_slug():
    blueprint = Blueprint.from_category_names("Personale", ["Groceries", "groceries", "Caffè", "caffe", ""])
    assert [(n.key, n.label) for n in blueprint.categories] == [("caffe", "Caffè"), ("groceries", "Groceries")]


def test_slugify():
    assert slugify("Spese d'ufficio") == "spese_d_ufficio"
    assert slugify("   ") == "x"
