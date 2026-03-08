"""Health-check routes."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    summary="Health check",
    response_description="API health status",
)
async def health():
    """Return a simple status object confirming the API is running."""
    return {"status": "healthy"}
