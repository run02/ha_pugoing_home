"""Switch platform for PuGoing integration (integration_blueprint).

Dynamic add/remove Breaker entities using DataUpdateCoordinator.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
)
from homeassistant.const import (
    EntityCategory,
)
from .const import DOMAIN, LAMP_STATE_DEBOUNCE_SECONDS
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
    """Create Switch entities for every Breaker device and listen for changes."""
    coordinator: BlueprintDataUpdateCoordinator = entry.runtime_data.coordinator

    known_ids: set[str] = set()

    def _create_entity(dev: dict[str, Any]):
        return PuGoingBreakerSwitch(coordinator, dev)

    async def _async_add_initial() -> None:
        breakers = coordinator.data.get("devices_by_type", {}).get("Breaker", [])
        entities = []
        for dev in breakers:
            yid = dev["yid"]
            known_ids.add(yid)
            entities.append(_create_entity(dev))
        if entities:
            async_add_entities(entities)
            _LOGGER.info("Added %d initial Breaker entities", len(entities))

    await _async_add_initial()

    # ---------------- listener: add & remove ---------------------------#
    def _handle_breaker_changes() -> None:  # must be sync for coordinator listener
        breakers_now: list[dict] = coordinator.data.get("devices_by_type", {}).get(
            "Breaker", []
        )
        current_ids: set[str] = {dev["yid"] for dev in breakers_now}

        # Detect new breakers
        new_ids = current_ids - known_ids
        if new_ids:
            new_entities = [
                _create_entity(dev) for dev in breakers_now if dev["yid"] in new_ids
            ]
            known_ids.update(new_ids)
            async_add_entities(new_entities)
            _LOGGER.info("Dynamically added %d Breaker entities", len(new_entities))

        # Detect removed breakers
        removed_ids = known_ids - current_ids
        if removed_ids:
            reg = er.async_get(hass)
            for yid in removed_ids:
                unique_id = f"{yid}"
                ent_id = reg.async_get_entity_id("switch", DOMAIN, unique_id)
                if ent_id:
                    _LOGGER.info("Removing stale Breaker entity: %s", ent_id)
                    reg.async_remove(ent_id)
            known_ids.difference_update(removed_ids)

    coordinator.async_add_listener(_handle_breaker_changes)


# ----------------------------- entity: 断路器 --------------------------- #
class PuGoingBreakerSwitch(IntegrationBlueprintEntity, SwitchEntity):
    """Representation of a Breaker (断路器)."""
    # _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:power"  # 用醒目的 icon
    # _attr_device_class = None  # 不归类 outlet/light

    def __init__(
        self, coordinator: BlueprintDataUpdateCoordinator, device: dict[str, Any]
    ):
        super().__init__(coordinator)
        self._device_id = device["yid"]
        self._device_sn = device.get("sn", self._device_id)
        self._attr_unique_id = f"{self._device_id}"
        # 优先使用 danam，如果为空或不存在则使用 dname
        danam = device.get("danam", "")
        dname = device.get("dname", "Breaker")
        self._attr_name = danam if danam else dname
        self._state: bool = self._parse_state(device)
        self._last_manual_control: datetime | None = None

    # ---------- helpers ---------- #
    @staticmethod
    def _parse_state(device: dict[str, Any]) -> bool:
        return str(device.get("dinfo", "")) == "开"

    def _latest(self) -> dict[str, Any] | None:
        for dev in self.coordinator.data.get("devices_by_type", {}).get("Breaker", []):
            if dev["yid"] == self._device_id:
                return dev
        return None

    # ---------- required props ----- #
    @property
    def is_on(self) -> bool:
        if self._last_manual_control:
            if datetime.now() - self._last_manual_control < timedelta(
                seconds=LAMP_STATE_DEBOUNCE_SECONDS
            ):
                return self._state

        latest = self._latest()
        if latest is not None:
            self._state = self._parse_state(latest)
        return self._state

    @property
    def available(self) -> bool:
        return self._latest() is not None

    # ---------- control ------------ #
    async def async_turn_on(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.config_entry.runtime_data.client.async_set_breaker_state(
                self._device_id, sn=self._device_sn, on=True
            )
            self._state = True
            self._last_manual_control = datetime.now()
            self.async_write_ha_state()
        except PuGoingAPIError as e:
            _LOGGER.warning("Failed to turn on breaker %s: %s", self._device_id, e)

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.config_entry.runtime_data.client.async_set_breaker_state(
                self._device_id, sn=self._device_sn, on=False
            )
            self._state = False
            self._last_manual_control = datetime.now()
            self.async_write_ha_state()
        except PuGoingAPIError as e:
            _LOGGER.warning("Failed to turn off breaker %s: %s", self._device_id, e)

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
            "danam": dev.get("danam"),  # 添加 danam 信息
            "voltage": dev.get("dcap", "").split(";")[3] if dev.get("dcap") else None,
            "current": dev.get("dcap", "").split(";")[4] if dev.get("dcap") else None,
            "temperature": dev.get("dcap", "").split(";")[6]
            if dev.get("dcap")
            else None,
        }
    @property
    def device_info(self) -> DeviceInfo:
        """让每个断路器各自成为一个设备。"""
        dev = self._latest() or {}

        # 优先使用 danam，如果为空或不存在则使用 dname
        danam = dev.get("danam", "")
        dname = dev.get("dname", f"Breaker {self._device_id}")
        device_name = danam if danam else dname

        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device_name,
            manufacturer="PuGoing",
            model=dev.get("dpanel", "Breaker"),
        )
    # ---------- HA 回调：实体已加入 ---------------- #
    async def async_added_to_hass(self) -> None:
        """实体注册完成后，自动把设备归到对应区域。"""
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
