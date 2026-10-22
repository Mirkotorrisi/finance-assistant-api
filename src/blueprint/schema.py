"""Blueprint: the declarative document that says how a project's spending is organised.

A blueprint holds a category tree (stable keys, labels editable), named groups that span categories
(e.g. a "minchiate" group), cross-cutting dimensions (e.g. "per chi": figli / casa), saved report views,
seed merchant rules and free-text instructions for the classifier. It is validated here and stored as JSON
on the workspace.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Literal, Optional, Set

from pydantic import BaseModel, Field, field_validator, model_validator

SCHEMA_VERSION = 1
KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_]{0,63}$")
MAX_DEPTH = 4
MAX_CATEGORIES = 500


def slugify(text: str) -> str:
    """Lowercase ascii key: 'Spese d\'ufficio' -> 'spese_d_ufficio'."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")
    return slug[:64] or "x"


def _check_key(value: str, what: str) -> str:
    if not KEY_RE.match(value):
        raise ValueError(f"{what} key {value!r} must be lowercase letters, digits or underscores (max 64)")
    return value


class CategoryNode(BaseModel):
    key: str
    label: str = Field(min_length=1, max_length=120)
    description: str = ""
    examples: List[str] = Field(default_factory=list)
    kind: Literal["expense", "income"] = "expense"
    attributes: Dict[str, Any] = Field(default_factory=dict)  # free extension point, e.g. {"deductible": true}
    children: List["CategoryNode"] = Field(default_factory=list)

    @field_validator("key")
    @classmethod
    def _key(cls, v: str) -> str:
        return _check_key(v, "category")


class Group(BaseModel):
    key: str
    label: str = Field(min_length=1, max_length=120)
    description: str = ""
    members: List[str] = Field(default_factory=list)  # category keys; a parent includes its descendants

    @field_validator("key")
    @classmethod
    def _key(cls, v: str) -> str:
        return _check_key(v, "group")


class DimensionValue(BaseModel):
    key: str
    label: str = Field(min_length=1, max_length=120)

    @field_validator("key")
    @classmethod
    def _key(cls, v: str) -> str:
        return _check_key(v, "dimension value")


class Dimension(BaseModel):
    key: str
    label: str = Field(min_length=1, max_length=120)
    description: str = ""
    values: List[DimensionValue] = Field(min_length=1)

    @field_validator("key")
    @classmethod
    def _key(cls, v: str) -> str:
        return _check_key(v, "dimension")


class Rule(BaseModel):
    pattern: str = Field(min_length=1, max_length=200)
    category: str


class Report(BaseModel):
    """A saved view: either a group or an explicit list of categories."""

    key: str
    label: str = Field(min_length=1, max_length=120)
    group: Optional[str] = None
    categories: List[str] = Field(default_factory=list)

    @field_validator("key")
    @classmethod
    def _key(cls, v: str) -> str:
        return _check_key(v, "report")


class Settings(BaseModel):
    detect_transfers: bool = True


class Blueprint(BaseModel):
    schema_version: Literal[1] = SCHEMA_VERSION
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    instructions: str = Field(default="", max_length=4000)
    categories: List[CategoryNode] = Field(default_factory=list)
    groups: List[Group] = Field(default_factory=list)
    dimensions: List[Dimension] = Field(default_factory=list)
    reports: List[Report] = Field(default_factory=list)
    rules: List[Rule] = Field(default_factory=list)
    settings: Settings = Field(default_factory=Settings)

    # ------------------------------------------------------------------ validation

    @model_validator(mode="after")
    def _validate_references(self) -> "Blueprint":
        seen: Set[str] = set()

        def walk(nodes: List[CategoryNode], depth: int) -> None:
            if depth > MAX_DEPTH:
                raise ValueError(f"category tree is deeper than {MAX_DEPTH} levels")
            for node in nodes:
                if node.key in seen:
                    raise ValueError(f"duplicate category key {node.key!r}")
                seen.add(node.key)
                walk(node.children, depth + 1)

        walk(self.categories, 1)
        if len(seen) > MAX_CATEGORIES:
            raise ValueError(f"too many categories (max {MAX_CATEGORIES})")

        def unique(keys: List[str], what: str) -> None:
            dupes = {k for k in keys if keys.count(k) > 1}
            if dupes:
                raise ValueError(f"duplicate {what} key(s): {', '.join(sorted(dupes))}")

        unique([g.key for g in self.groups], "group")
        unique([d.key for d in self.dimensions], "dimension")
        unique([r.key for r in self.reports], "report")
        for dim in self.dimensions:
            unique([v.key for v in dim.values], f"value of dimension {dim.key!r}")

        for group in self.groups:
            for member in group.members:
                if member not in seen:
                    raise ValueError(f"group {group.key!r} references unknown category {member!r}")
        for rule in self.rules:
            if rule.category not in seen:
                raise ValueError(f"rule {rule.pattern!r} points to unknown category {rule.category!r}")
        group_keys = {g.key for g in self.groups}
        for report in self.reports:
            if report.group is not None and report.group not in group_keys:
                raise ValueError(f"report {report.key!r} references unknown group {report.group!r}")
            if report.group is None and not report.categories:
                raise ValueError(f"report {report.key!r} needs a group or a list of categories")
            for cat in report.categories:
                if cat not in seen:
                    raise ValueError(f"report {report.key!r} references unknown category {cat!r}")
        return self

    # ------------------------------------------------------------------ navigation

    def nodes(self) -> Dict[str, CategoryNode]:
        """Every category by key."""
        out: Dict[str, CategoryNode] = {}

        def walk(items: List[CategoryNode]) -> None:
            for n in items:
                out[n.key] = n
                walk(n.children)

        walk(self.categories)
        return out

    def parents(self) -> Dict[str, Optional[str]]:
        out: Dict[str, Optional[str]] = {}

        def walk(items: List[CategoryNode], parent: Optional[str]) -> None:
            for n in items:
                out[n.key] = parent
                walk(n.children, n.key)

        walk(self.categories, None)
        return out

    def leaf_keys(self) -> List[str]:
        return [k for k, n in self.nodes().items() if not n.children]

    def descendants(self, key: str) -> Set[str]:
        """``key`` plus every category below it."""
        node = self.nodes().get(key)
        if node is None:
            return set()
        found = {key}
        for child in node.children:
            found |= self.descendants(child.key)
        return found

    def group_categories(self, group_key: str) -> Set[str]:
        group = next((g for g in self.groups if g.key == group_key), None)
        if group is None:
            return set()
        keys: Set[str] = set()
        for member in group.members:
            keys |= self.descendants(member)
        return keys

    def groups_of(self, category_key: str) -> List[str]:
        return [g.key for g in self.groups if category_key in self.group_categories(g.key)]

    def resolve_category(self, text: str) -> Optional[str]:
        """Category key for a free-text category name (matches key or label, ignoring case/accents)."""
        wanted = slugify(text)
        nodes = self.nodes()
        if wanted in nodes:
            return wanted
        for key, node in nodes.items():
            if slugify(node.label) == wanted:
                return key
        return None

    # ------------------------------------------------------------------ construction

    @classmethod
    def from_category_names(cls, name: str, names: List[str]) -> "Blueprint":
        """A flat blueprint from category names found in existing data."""
        seen: Dict[str, str] = {}
        for raw in names:
            if raw and slugify(raw) not in seen:
                seen[slugify(raw)] = raw.strip()
        return cls(
            name=name,
            categories=[CategoryNode(key=k, label=label) for k, label in sorted(seen.items())],
        )

    def to_json(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")
