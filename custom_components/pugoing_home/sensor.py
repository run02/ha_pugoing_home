"""Sensor platform for IntelligentButler devices (PuGoing integration).

Creates temperature, humidity and illuminance sensors for every IntelligentButler
physical device discovered by the coordinator. Each physical device is grouped
into a single *device* in Home Assistant; the three sensor entities hang below
that device card.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Set

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import (
    UnitOfTemperature,
    PERCENTAGE,
)

# UnitOfIlluminance 的位置在 2024.4+ 版本Moved到 homeassistant.const。
# 为兼容旧版 HA，这里做一个 try/except 回退。
try:  # HA ≥2024.4
    from homeassistant.const import UnitOfIlluminance  # type: ignore
except ImportError:  # pragma: no cover – HA ≤2024.3
    UnitOfIlluminance = None  # type: ignore

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,   # ← 增加 entity_registry 别名 er
)

from .const import DOMAIN
from .entity import IntegrationBlueprintEntity

if TYPE_CHECKING:  # pragma: no cover
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import BlueprintDataUpdateCoordinator
    from .data import IntegrationBlueprintConfigEntry

_LOGGER = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Platform setup
# -----------------------------------------------------------------------------
async def async_setup_entry(
    hass: "HomeAssistant",
    entry: "IntegrationBlueprintConfigEntry",
    async_add_entities: "AddEntitiesCallback",
) -> None:
    """Set up IntelligentButler sensors based on a config entry."""
    coordinator: BlueprintDataUpdateCoordinator = entry.runtime_data.coordinator

    known_ids: Set[str] = set()  # Track devices already added

    def _create_entities(dev: Dict[str, Any]):
        """Create three sensor entities (temp/hum/lum) for one physical device."""
        return [
            ButlerTempSensor(coordinator, dev),
            ButlerHumiditySensor(coordinator, dev),
            ButlerLumSensor(coordinator, dev),
        ]

    async def _async_add_initial():
        butlers: List[Dict] = coordinator.data.get("devices_by_type", {}).get(
            "IntelligentButler", []
        )
        entities: List[SensorEntity] = []
        for dev in butlers:
            yid = dev["yid"]
            known_ids.add(yid)
            entities.extend(_create_entities(dev))

        if entities:
            async_add_entities(entities)
            _LOGGER.info("Added %d initial IntelligentButler sensor entities", len(entities))

    await _async_add_initial()

    # ------------------------ coordinator listener -------------------------#
    def _handle_butler_changes() -> None:
        """Handle runtime addition/removal of IntelligentButler devices."""
        butlers_now: List[Dict] = coordinator.data.get("devices_by_type", {}).get(
            "IntelligentButler", []
        )
        current_ids: Set[str] = {dev["yid"] for dev in butlers_now}

        # New devices
        new_ids = current_ids - known_ids
        if new_ids:
            new_entities: List[SensorEntity] = []
            for dev in butlers_now:
                if dev["yid"] in new_ids:
                    new_entities.extend(_create_entities(dev))
            known_ids.update(new_ids)
            async_add_entities(new_entities)
            _LOGGER.info("Dynamically added %d new IntelligentButler sensors", len(new_entities))

        # Removed devices
        removed_ids = known_ids - current_ids
        if removed_ids:
            dev_reg = dr.async_get(hass)
            ent_reg = er.async_get(hass)
            for yid in removed_ids:
                for kind in ("tem", "hum", "lum"):
                    unique_id = f"{yid}_{kind}"
                    ent_id = ent_reg.async_get_entity_id("sensor", DOMAIN, unique_id)
                    if ent_id:
                        ent_reg.async_remove(ent_id)
            # Remove device entries
            for yid in removed_ids:
                device = dev_reg.async_get_device({(DOMAIN, yid)})
                if device:
                    dev_reg.async_remove_device(device.id)
            known_ids.difference_update(removed_ids)

    coordinator.async_add_listener(_handle_butler_changes)


# -----------------------------------------------------------------------------
# Entity classes
# -----------------------------------------------------------------------------
class ButlerBaseSensor(IntegrationBlueprintEntity, SensorEntity):
    """Base class: binds three sensor entities to the same physical device."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: "BlueprintDataUpdateCoordinator", dev: Dict, kind: str):
        super().__init__(coordinator)
        self._kind = kind  # "tem" / "hum" / "lum"
        self._device_id = dev["yid"]
        self._attr_unique_id = f"{self._device_id}_{kind}"
        self._dev_initial = dev  # Keep a copy for early access

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _latest(self) -> Dict | None:
        """Return latest device dict from coordinator cache."""
        for d in self.coordinator.data.get("devices_by_type", {}).get("IntelligentButler", []):
            if d["yid"] == self._device_id:
                return d
        return None

    def _parse_cap(self) -> Dict[str, str]:
        dev = self._latest() or self._dev_initial
        cap_raw = dev.get("dcap", "")  # e.g. "wake:null;sen:5;tem:28;hum:57;lum:05"
        return {
            k: v for part in cap_raw.split(";") if (len(part_split := part.split(":")) == 2)
            for k, v in [part_split]
        }

    # ------------------------------------------------------------------
    # Device / area info
    # ------------------------------------------------------------------
    @property
    def device_info(self) -> DeviceInfo:  # type: ignore[override]
        dev = self._latest() or self._dev_initial
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=dev.get("dname", "语音主机"),
            manufacturer="PuGoing",
            model=dev.get("dpanel", "IntelligentButler"),
        )

    async def async_added_to_hass(self) -> None:
        """When entity is registered, automatically assign it to the correct area."""
        await super().async_added_to_hass()
        dev = self._latest() or self._dev_initial
        area_name = dev.get("dloca")
        if not area_name:
            return

        area_reg = ar.async_get(self.hass)
        area = area_reg.async_get_area_by_name(area_name) or area_reg.async_create(area_name)

        dev_reg = dr.async_get(self.hass)
        device = dev_reg.async_get_device({(DOMAIN, self._device_id)})
        if device and device.area_id != area.id:
            dev_reg.async_update_device(device.id, area_id=area.id)

    # ------------------------------------------------------------------
    # Sensor core
    # ------------------------------------------------------------------
    @property
    def native_value(self):  # type: ignore[override]
        parts = self._parse_cap()
        raw = parts.get(self._kind)
        if raw is None:
            return None
        try:
            return int(raw)
        except (ValueError, TypeError):
            return None

    @property
    def available(self) -> bool:  # type: ignore[override]
        return self._latest() is not None


class ButlerTempSensor(ButlerBaseSensor):
    """Temperature sensor (°C)."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_name = "温度"

    def __init__(self, coordinator, dev):
        super().__init__(coordinator, dev, "tem")


class ButlerHumiditySensor(ButlerBaseSensor):
    """Relative humidity sensor (%)."""

    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_name = "湿度" 

    def __init__(self, coordinator, dev):
        super().__init__(coordinator, dev, "hum")


class ButlerLumSensor(ButlerBaseSensor):
    """Illuminance sensor (lux)."""

    _attr_device_class = SensorDeviceClass.ILLUMINANCE
    _attr_native_unit_of_measurement = (
        UnitOfIlluminance.LUX if UnitOfIlluminance else "lx"  # HA <2024.4 fallback
    )
    _attr_name = "光照"

    def __init__(self, coordinator, dev):
        super().__init__(coordinator, dev, "lum")
