"""Blueprint templates and stateless validation."""

from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Query

from src.blueprint import Blueprint, build_template, list_templates
from src.blueprint.templates import DEFAULT_LOCALE, LOCALES

router = APIRouter(prefix="/api", tags=["blueprints"])


@router.get("/blueprint-templates", summary="List starter blueprints")
async def templates(locale: str = Query(default=DEFAULT_LOCALE, description=f"One of {', '.join(LOCALES)}")) -> List[Dict[str, str]]:
    return list_templates(locale)


@router.get("/blueprint-templates/{key}", summary="A starter blueprint")
async def template(key: str, locale: str = DEFAULT_LOCALE) -> Dict[str, Any]:
    """A complete blueprint document to adapt; it is not saved anywhere."""
    try:
        return build_template(key, locale).to_json()
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown template {key!r}")


@router.post("/blueprints/validate", summary="Validate a blueprint without saving it")
async def validate(blueprint: Blueprint) -> Dict[str, Any]:
    """Returns the normalised document (defaults filled in) and its size. Invalid documents get a 422 saying why."""
    nodes = blueprint.nodes()
    return {
        "valid": True,
        "blueprint": blueprint.to_json(),
        "stats": {
            "categories": len(nodes),
            "leaf_categories": len(blueprint.leaf_keys()),
            "groups": len(blueprint.groups),
            "dimensions": len(blueprint.dimensions),
            "rules": len(blueprint.rules),
        },
    }
