"""Daily price refresh while the API runs: shortly after start-up, then every few hours (a refresh that already
happened today costs no request). Off when there is no Alpha Vantage key or FINANCE_PRICES=off."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

INITIAL_DELAY = 60
CHECK_EVERY = 6 * 3600


def enabled() -> bool:
    return bool(os.getenv("ALPHAVANTAGE_API_KEY")) and os.getenv("FINANCE_PRICES", "daily").lower() != "off"


def refresh_all_workspaces(max_requests: int = 20) -> None:
    """Prices are global; the valuation snapshots are written in every workspace that has positions."""
    from src.database.init import get_db_session, get_unscoped_session
    from src.database.models import Workspace
    from src.market.providers import AlphaVantage
    from src.services.portfolio_service import PortfolioService

    unscoped = get_unscoped_session()
    try:
        workspace_ids = [w.id for w in unscoped.query(Workspace).order_by(Workspace.id).all()]
    finally:
        unscoped.close()
    av = AlphaVantage()
    try:
        for workspace_id in workspace_ids:
            session = get_db_session(workspace_id)
            try:
                service = PortfolioService(session)
                prices = service.refresh_prices(av, max_requests=max_requests)
                valuations = service.write_valuations()
                if prices.get("updated") or valuations.get("written"):
                    logger.info("Prices: workspace %s, %d symbol(s) updated, %d valuation(s) written", workspace_id, len(prices.get("updated", [])), len(valuations.get("written", [])))
                if prices.get("stopped"):
                    break
            finally:
                session.close()
    finally:
        av.close()


class PriceScheduler:
    def __init__(self):
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        if enabled() and self._task is None:
            self._task = asyncio.create_task(self._run(), name="price-refresh")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None

    async def _run(self) -> None:
        await asyncio.sleep(INITIAL_DELAY)
        while True:
            try:
                await asyncio.to_thread(refresh_all_workspaces)
            except Exception:  # noqa: BLE001
                logger.exception("Prices: scheduled refresh failed")
            await asyncio.sleep(CHECK_EVERY)


scheduler = PriceScheduler()
