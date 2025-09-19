"""Light platform for PuGoing integration (integration_blueprint).

Dynamic add/remove Lamp entities using DataUpdateCoordinator.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.light import (
    ColorMode,
    LightEntity,
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN as ATTR_COLOR_TEMP,
    ATTR_RGB_COLOR,
)
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
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
    """Create Light entities for every Lamp device and listen for changes."""
    coordinator: BlueprintDataUpdateCoordinator = entry.runtime_data.coordinator

    known_ids: set[str] = set()

    def _create_entity(dev: dict[str, Any]):
        # dpanel 来区分：普通灯 / 调光灯
        if dev.get("dpanel") == "LampRGBCW":
            return PuGoingRGBCWLight(coordinator, dev)
        return PuGoingLampLight(coordinator, dev)

    async def _async_add_initial() -> None:
        lamps = [
            device
            for key, devices in coordinator.data.get("devices_by_type", {}).items()
            if "Lamp" in key
            for device in devices
        ]
        entities = []
        for dev in lamps:
            yid = dev["yid"]
            known_ids.add(yid)
            entities.append(_create_entity(dev))
        if entities:
            async_add_entities(entities)
            _LOGGER.info("Added %d initial Lamp entities", len(entities))

    await _async_add_initial()

    # ---------------- listener: add & remove ---------------------------#
    def _handle_lamp_changes() -> None:  # must be sync for coordinator listener
        lamps_now: list[dict] = [
            device
            for key, devices in coordinator.data.get("devices_by_type", {}).items()
            if "Lamp" in key
            for device in devices
        ]
        current_ids: set[str] = {dev["yid"] for dev in lamps_now}

        # Detect new lamps
        new_ids = current_ids - known_ids
        if new_ids:
            new_entities = [
                _create_entity(dev) for dev in lamps_now if dev["yid"] in new_ids
            ]
            known_ids.update(new_ids)
            async_add_entities(new_entities)
            _LOGGER.info("Dynamically added %d Lamp entities", len(new_entities))

        # Detect removed lamps
        removed_ids = known_ids - current_ids
        if removed_ids:
            reg = er.async_get(hass)
            for yid in removed_ids:
                unique_id = f"{yid}"
                ent_id = reg.async_get_entity_id("light", DOMAIN, unique_id)
                if ent_id:
                    _LOGGER.info("Removing stale Lamp entity: %s", ent_id)
                    reg.async_remove(ent_id)
            known_ids.difference_update(removed_ids)

    coordinator.async_add_listener(_handle_lamp_changes)


# ----------------------------- entity: 普通灯 --------------------------- #
class PuGoingLampLight(IntegrationBlueprintEntity, LightEntity):
    """Representation of a single Lamp device (开关灯)."""

    _attr_supported_color_modes = {ColorMode.ONOFF}
    _attr_color_mode = ColorMode.ONOFF

    def __init__(
        self, coordinator: BlueprintDataUpdateCoordinator, device: dict[str, Any]
    ):
        super().__init__(coordinator)
        self._device_id = device["yid"]
        self._device_sn = device.get("sn", self._device_id)
        self._attr_unique_id = f"{self._device_id}"
        self._attr_name = device.get("dname", "Lamp")
        self._state: bool = self._parse_state(device)
        self._last_manual_control: datetime | None = None

    # ---------- helpers ---------- #
    @staticmethod
    def _parse_state(device: dict[str, Any]) -> bool:
        return str(device.get("dinfo", "")).startswith("开")

    def _latest(self) -> dict[str, Any] | None:
        for dev in self.coordinator.data.get("devices_by_type", {}).get("Lamp", []):
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
            await (
                self.coordinator.config_entry.runtime_data.client.async_set_lamp_state(
                    self._device_id, sn=self._device_sn, on=True
                )
            )
            self._state = True
            self._last_manual_control = datetime.now()
            self.async_write_ha_state()
        except PuGoingAPIError as e:
            _LOGGER.warning("Failed to turn on lamp %s: %s", self._device_id, e)

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            await (
                self.coordinator.config_entry.runtime_data.client.async_set_lamp_state(
                    self._device_id, sn=self._device_sn, on=False
                )
            )
            self._state = False
            self._last_manual_control = datetime.now()
            self.async_write_ha_state()
        except PuGoingAPIError as e:
            _LOGGER.warning("Failed to turn off lamp %s: %s", self._device_id, e)

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
        """让每盏灯各自成为一个设备。"""
        dev = self._latest() or {}
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=dev.get("dname") or f"Lamp {self._device_id}",
            manufacturer="PuGoing",
            model=dev.get("dpanel", "Lamp"),
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


# ----------------------------- entity: RGBCW 调光调色灯 --------------------------- #
class PuGoingRGBCWLight(PuGoingLampLight):
    """调光调色灯，支持亮度、色温、RGB。"""

    _attr_supported_color_modes = {
        ColorMode.BRIGHTNESS,
        ColorMode.COLOR_TEMP,
        ColorMode.RGB,
    }
    _attr_color_mode = ColorMode.BRIGHTNESS

    def __init__(
        self, coordinator: BlueprintDataUpdateCoordinator, device: dict[str, Any]
    ):
        super().__init__(coordinator, device)
        self._attr_name = device.get("dname", "RGBCW Lamp")
        self._brightness: int | None = None
        self._color_temp: int | None = None
        self._rgb_color: tuple[int, int, int] | None = None
        self._parse_rgbcw(device)

    # ---------- 解析 RGBCW ---------- #
    def _parse_rgbcw(self, device: dict[str, Any]) -> None:
        raw = str(device.get("dnlp", ""))
        if not raw.startswith("RGBCW:"):
            return
        data = raw[6:]
        if len(data) < 14:
            return

        try:
            power_hex = data[:2]  # 04 / 03
            mode_hex = data[2:4]  # 04=RGB / 03=亮度+色温
            brightness_hex = data[4:6]
            color_temp_hex = data[6:8]
            r_hex = data[8:10]
            g_hex = data[10:12]
            b_hex = data[12:14]

            self._state = power_hex == "03"

            if mode_hex == "03":
                self._attr_color_mode = ColorMode.COLOR_TEMP
            elif mode_hex == "04":
                self._attr_color_mode = ColorMode.RGB

            self._brightness = int(brightness_hex, 16) * 255 // 100
            self._color_temp = 153 + int(color_temp_hex, 16)  # 大概映射到 mired
            self._rgb_color = (
                round(int(r_hex, 16) / 100 * 255),
                round(int(g_hex, 16) / 100 * 255),
                round(int(b_hex, 16) / 100 * 255),
            )
        except Exception as e:
            _LOGGER.debug("Failed to parse RGBCW data: %s", e)

    def _latest(self) -> dict[str, Any] | None:
        for dev in self.coordinator.data.get("devices_by_type", {}).get(
            "LampRGBCW", []
        ):
            if dev["yid"] == self._device_id:
                self._parse_rgbcw(dev)
                return dev
        return None

    # ---------- required props ----- #
    @property
    def brightness(self) -> int | None:
        return self._brightness

    @property
    def color_temp(self) -> int | None:
        return self._color_temp

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        return self._rgb_color

    # ---------- control ------------ #
    async def async_turn_on(self, **kwargs: Any) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        color_temp = kwargs.get(ATTR_COLOR_TEMP)
        rgb_color = kwargs.get(ATTR_RGB_COLOR)

        try:
            await self.coordinator.config_entry.runtime_data.client.async_set_dimmer_state(
                self._device_id,
                sn=self._device_sn,
                on=True,
                brightness=int(brightness * 100 / 255) if brightness else None,
                color_temp=int(color_temp * 100 / 255) if color_temp else None,
                rgb_hex="%02X%02X%02X" % rgb_color if rgb_color else None,
            )
            self._state = True
            if brightness:
                self._brightness = brightness
            if color_temp:
                self._color_temp = color_temp
            if rgb_color:
                self._rgb_color = rgb_color
            self._last_manual_control = datetime.now()
            self.async_write_ha_state()
        except PuGoingAPIError as e:
            _LOGGER.warning("Failed to set RGBCW lamp %s: %s", self._device_id, e)

    async def async_turn_off(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.config_entry.runtime_data.client.async_set_dimmer_state(
                self._device_id, sn=self._device_sn, on=False
            )
            self._state = False
            self._last_manual_control = datetime.now()
            self.async_write_ha_state()
        except PuGoingAPIError as e:
            _LOGGER.warning("Failed to turn off RGBCW lamp %s: %s", self._device_id, e)
