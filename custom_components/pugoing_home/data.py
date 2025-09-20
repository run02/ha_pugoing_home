# data.py
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.loader import Integration

    from .api import IntegrationBlueprintApiClient
    from .coordinator import BlueprintDataUpdateCoordinator
    from .assist_mqtt_bridge import AssistMqttBridge


type IntegrationBlueprintConfigEntry = ConfigEntry[IntegrationBlueprintData]


@dataclass
class IntegrationBlueprintData:
    """Data for the Blueprint integration."""

    client: IntegrationBlueprintApiClient
    coordinator: BlueprintDataUpdateCoordinator
    integration: Integration
    mqtt_bridge: Optional[AssistMqttBridge] = None  # 👈 增加这个
