"""
Binary Sensor platform for PuGoing integration (integration_blueprint).
Dynamic add/remove Human Presence Sensors using DataUpdateCoordinator.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .entity import IntegrationBlueprintEntity

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import BlueprintDataUpdateCoordinator
    from .data import IntegrationBlueprintConfigEntry

_LOGGER = logging.getLogger(__name__)


# ----------------------------- setup ------------------------------------ #
async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntegrationBlueprintConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create HumanSensor entities and listen for changes."""
    coordinator: BlueprintDataUpdateCoordinator = entry.runtime_data.coordinator
    known_ids: set[str] = set()

    def _create_entity(dev: dict[str, Any]):
        return PuGoingHumanSensor(coordinator, dev)

    async def _async_add_initial() -> None:
        sensors: list[dict] = coordinator.data.get("devices_by_type", {}).get(
            "HumanSensor", []
        )
        entities = []
        for dev in sensors:
            yid = dev["yid"]
            known_ids.add(yid)
            entities.append(_create_entity(dev))
        if entities:
            async_add_entities(entities)
            _LOGGER.info("Added %d initial HumanSensor entities", len(entities))

    await _async_add_initial()

    # ---------------- listener: add & remove ---------------------------#
    def _handle_sensor_changes() -> None:
        sensors_now: list[dict] = coordinator.data.get("devices_by_type", {}).get(
            "HumanSensor", []
        )
        current_ids: set[str] = {dev["yid"] for dev in sensors_now}

        # Detect new sensors
        new_ids = current_ids - known_ids
        if new_ids:
            new_entities = [
                _create_entity(dev) for dev in sensors_now if dev["yid"] in new_ids
            ]
            known_ids.update(new_ids)
            async_add_entities(new_entities)
            _LOGGER.info("Dynamically added %d HumanSensor entities", len(new_entities))

        # Detect removed sensors
        removed_ids = known_ids - current_ids
        if removed_ids:
            reg = er.async_get(hass)
            for yid in removed_ids:
                unique_id = f"{yid}"
                ent_id = reg.async_get_entity_id("binary_sensor", DOMAIN, unique_id)
                if ent_id:
                    _LOGGER.info("Removing stale HumanSensor entity: %s", ent_id)
                    reg.async_remove(ent_id)
            known_ids.difference_update(removed_ids)

    coordinator.async_add_listener(_handle_sensor_changes)


# ----------------------------- entity ----------------------------------- #
class PuGoingHumanSensor(IntegrationBlueprintEntity, BinarySensorEntity):
    """Representation of a Human Presence Sensor."""

    _attr_device_class = BinarySensorDeviceClass.PRESENCE

    def __init__(
        self, coordinator: BlueprintDataUpdateCoordinator, device: dict[str, Any]
    ):
        super().__init__(coordinator)
        self._device_id = device["yid"]
        self._device_sn = device.get("sn", self._device_id)
        self._attr_unique_id = f"{self._device_id}"
        self._attr_name = device.get("dname", "Human Presence Sensor")

        self._last_state_text: str | None = device.get("dinfo")
        self._state: bool = self._parse_state(device)

    # ---------- helpers ---------- #
    @staticmethod
    def _parse_state(device: dict[str, Any]) -> bool:
        """根据 dinfo 判断是否有人."""
        dinfo = str(device.get("dinfo", ""))
        return "有人" in dinfo

    def _latest(self) -> dict[str, Any] | None:
        for dev in self.coordinator.data.get("devices_by_type", {}).get(
            "HumanSensor", []
        ):
            if dev["yid"] == self._device_id:
                return dev
        return None

    # ---------- required props ----- #
    @property
    def is_on(self) -> bool:
        latest = self._latest()
        if latest is None:
            return False

        dinfo = latest.get("dinfo")
        # 只有 dinfo 变化时才更新状态
        if dinfo != self._last_state_text:
            self._last_state_text = dinfo
            self._state = self._parse_state(latest)
            self.async_write_ha_state()
        return self._state

    @property
    def available(self) -> bool:
        return self._latest() is not None

    # ---------- extra attrs -------- #
    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        dev = self._latest()
        if dev is None:
            return None
        return {
            "sn": dev.get("sn"),
            "dpanel": dev.get("dpanel"),
            "room": dev.get("dloca"),
            "online": dev.get("online"),
            "raw_dinfo": dev.get("dinfo"),
        }

    @property
    def device_info(self) -> DeviceInfo:
        """让每个传感器各自成为一个设备."""
        dev = self._latest() or {}
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=dev.get("dname") or f"HumanSensor {self._device_id}",
            manufacturer="PuGoing",
            model=dev.get("dpanel", "HumanSensor"),
        )

    # ---------- HA 回调:实体已加入 ---------------- #
    async def async_added_to_hass(self) -> None:
        """实体注册完成后,自动把设备归到对应区域."""
        await super().async_added_to_hass()
        area_name = (self._latest() or {}).get("dloca")
        if not area_name:
            return

        area_reg = ar.async_get(self.hass)
        area = area_reg.async_get_area_by_name(area_name)
        if area is None:
            area = area_reg.async_create(area_name)

        dev_reg = dr.async_get(self.hass)
        device = dev_reg.async_get_device({(DOMAIN, self._device_id)})
        if device and device.area_id != area.id:
            dev_reg.async_update_device(device.id, area_id=area.id)
