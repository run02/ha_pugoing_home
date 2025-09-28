"""
Cover platform for PuGoing integration (integration_blueprint).

Dynamic add/remove Curtain entities using DataUpdateCoordinator.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.cover import (
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.helpers import (
    area_registry as ar,
)
from homeassistant.helpers import (
    device_registry as dr,
)
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CURTAIN_STATE_DEBOUNCE_SECONDS, DOMAIN
from .entity import IntegrationBlueprintEntity
from .pugoing_api.error import PuGoingAPIError

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
    """Create Cover entities for every CurtainPG device and listen for changes."""
    coordinator: BlueprintDataUpdateCoordinator = entry.runtime_data.coordinator

    known_ids: set[str] = set()

    def _create_entity(dev: dict[str, Any]):
        return PuGoingCurtain(coordinator, dev)

    async def _async_add_initial() -> None:
        curtains: list[dict] = coordinator.data.get("devices_by_type", {}).get(
            "CurtainPG", []
        )
        entities = []
        for dev in curtains:
            yid = dev["yid"]
            known_ids.add(yid)
            entities.append(_create_entity(dev))
        if entities:
            async_add_entities(entities)
            _LOGGER.info("Added %d initial Curtain entities", len(entities))

    await _async_add_initial()

    # ---------------- listener: add & remove ---------------------------#
    def _handle_changes() -> None:  # must be sync for coordinator listener
        curtains_now: list[dict] = coordinator.data.get("devices_by_type", {}).get(
            "CurtainPG", []
        )
        current_ids: set[str] = {dev["yid"] for dev in curtains_now}

        # Detect new
        new_ids = current_ids - known_ids
        if new_ids:
            new_entities = [
                _create_entity(dev) for dev in curtains_now if dev["yid"] in new_ids
            ]
            known_ids.update(new_ids)
            async_add_entities(new_entities)
            _LOGGER.info("Dynamically added %d Curtain entities", len(new_entities))

        # Detect removed
        removed_ids = known_ids - current_ids
        if removed_ids:
            reg = er.async_get(hass)
            for yid in removed_ids:
                unique_id = f"{yid}"
                ent_id = reg.async_get_entity_id("cover", DOMAIN, unique_id)
                if ent_id:
                    _LOGGER.info("Removing stale Curtain entity: %s", ent_id)
                    reg.async_remove(ent_id)
            known_ids.difference_update(removed_ids)

    coordinator.async_add_listener(_handle_changes)


# ----------------------------- entity ----------------------------------- #
class PuGoingCurtain(IntegrationBlueprintEntity, CoverEntity):
    """Representation of a single CurtainPG device."""

    _attr_supported_features = (
        CoverEntityFeature.OPEN
        | CoverEntityFeature.CLOSE
        | CoverEntityFeature.STOP
        | CoverEntityFeature.SET_POSITION
    )

    def __init__(
        self, coordinator: BlueprintDataUpdateCoordinator, device: dict[str, Any]
    ):
        super().__init__(coordinator)
        self._device_id = device["yid"]
        self._device_sn = device.get("sn", self._device_id)
        self._attr_unique_id = f"{self._device_id}"
        self._attr_name = device.get("dname", "Curtain")
        self._position: int | None = self._parse_position(device)
        self._last_manual_control: datetime | None = None

    # ---------- helpers ---------- #
    @staticmethod
    def _parse_position(device: dict[str, Any]) -> int | None:
        # 示例: "打开65%" → 65
        dinfo = str(device.get("dinfo", ""))
        if "打开" in dinfo and "%" in dinfo:
            try:
                return int(dinfo.split("打开")[1].replace("%", ""))
            except (IndexError, ValueError):
                return None
        elif "关闭" in dinfo:
            return 0
        return None

    def _latest(self) -> dict[str, Any] | None:
        for dev in self.coordinator.data.get("devices_by_type", {}).get(
            "CurtainPG", []
        ):
            if dev["yid"] == self._device_id:
                return dev
        return None

    # ---------- required props ----- #
    @property
    def current_cover_position(self) -> int | None:
        if self._last_manual_control:
            if datetime.now() - self._last_manual_control < timedelta(
                seconds=CURTAIN_STATE_DEBOUNCE_SECONDS
            ):
                return self._position

        latest = self._latest()
        if latest is not None:
            self._position = self._parse_position(latest)
        return self._position

    @property
    def is_closed(self) -> bool | None:
        if self._position is None:
            return None
        return self._position == 0

    @property
    def available(self) -> bool:
        return self._latest() is not None

    # ---------- control ------------ #
    async def async_open_cover(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.config_entry.runtime_data.client.async_set_curtain_state(
                self._device_id, action="open", sn=self._device_sn
            )
            self._position = 100
            self._last_manual_control = datetime.now()
            self.async_write_ha_state()
        except PuGoingAPIError as e:
            _LOGGER.warning("Failed to open curtain %s: %s", self._device_id, e)

    async def async_close_cover(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.config_entry.runtime_data.client.async_set_curtain_state(
                self._device_id, action="close", sn=self._device_sn
            )
            self._position = 0
            self._last_manual_control = datetime.now()
            self.async_write_ha_state()
        except PuGoingAPIError as e:
            _LOGGER.warning("Failed to close curtain %s: %s", self._device_id, e)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.config_entry.runtime_data.client.async_set_curtain_state(
                self._device_id, action="stop", sn=self._device_sn
            )
            self._last_manual_control = datetime.now()
        except PuGoingAPIError as e:
            _LOGGER.warning("Failed to stop curtain %s: %s", self._device_id, e)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        position = kwargs.get("position")
        if position is None:
            return
        try:
            await self.coordinator.config_entry.runtime_data.client.async_set_curtain_state(
                self._device_id, position=position, sn=self._device_sn
            )
            self._position = position
            self._last_manual_control = datetime.now()
            self.async_write_ha_state()
        except PuGoingAPIError as e:
            _LOGGER.warning(
                "Failed to set curtain %s to %s: %s", self._device_id, position, e
            )

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
        }

    @property
    def device_info(self) -> DeviceInfo:
        """让每个窗帘各自成为一个设备."""
        dev = self._latest() or {}
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=dev.get("dname") or f"Curtain {self._device_id}",
            manufacturer="PuGoing",
            model=dev.get("dpanel", "CurtainPG"),
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
