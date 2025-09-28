# data.py
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.loader import Integration

    from .api import IntegrationBlueprintApiClient
    from .assist_mqtt_bridge import AssistMqttBridge
    from .coordinator import BlueprintDataUpdateCoordinator


type IntegrationBlueprintConfigEntry = ConfigEntry[IntegrationBlueprintData]


@dataclass
class IntegrationBlueprintData:
    """Data for the Blueprint integration."""

    client: IntegrationBlueprintApiClient
    coordinator: BlueprintDataUpdateCoordinator
    integration: Integration
    mqtt_bridge: AssistMqttBridge | None = None  # 👈 增加这个
