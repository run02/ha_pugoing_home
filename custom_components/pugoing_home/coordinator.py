"""DataUpdateCoordinator for integration_blueprint."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    IntegrationBlueprintApiClientAuthenticationError,
    IntegrationBlueprintApiClientError,
)

if TYPE_CHECKING:
    from .data import IntegrationBlueprintConfigEntry

_LOGGER = logging.getLogger(__name__)

# https://developers.home-assistant.io/docs/integration_fetching_data#coordinated-single-api-poll-for-data-for-all-entities
class BlueprintDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    config_entry: IntegrationBlueprintConfigEntry

    async def _async_update_data(self) -> Any:
        """统一拉取并缓存所有设备数据."""
        try:
            data = await self.config_entry.runtime_data.client.async_get_data()
            return data
        except IntegrationBlueprintApiClientAuthenticationError as exc:
            raise ConfigEntryAuthFailed(exc) from exc
        except IntegrationBlueprintApiClientError as exc:
            raise UpdateFailed(exc) from exc
