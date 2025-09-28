"""Climate platform for PuGoing integration."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.climate.const import FAN_HIGH, FAN_LOW, FAN_MEDIUM
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .entity import IntegrationBlueprintEntity
from .pugoing_api.error import PuGoingAPIError

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import BlueprintDataUpdateCoordinator
    from .data import IntegrationBlueprintConfigEntry

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntegrationBlueprintConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: BlueprintDataUpdateCoordinator = entry.runtime_data.coordinator
    devices = coordinator.data.get("devices_by_type", {}).get("VRV", [])

    entities = [PuGoingVRVClimate(coordinator, dev) for dev in devices]
    if entities:
        async_add_entities(entities)
        _LOGGER.info("Added %d VRV Climate entities", len(entities))


class PuGoingVRVClimate(IntegrationBlueprintEntity, ClimateEntity):
    """Representation of a VRV AC device."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.COOL,
        HVACMode.HEAT,
        HVACMode.DRY,
        HVACMode.FAN_ONLY,
    ]
    _attr_fan_modes = [FAN_HIGH, FAN_MEDIUM, FAN_LOW]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
    )
    _attr_min_temp = 16
    _attr_max_temp = 30

    def __init__(
        self, coordinator: BlueprintDataUpdateCoordinator, device: dict[str, Any]
    ):
        super().__init__(coordinator)
        self._device_id = device["yid"]
        self._device_sn = device.get("sn", self._device_id)
        self._attr_unique_id = f"{self._device_id}"
        self._attr_name = device.get("dname", "VRV")

        # 初始状态
        self._hvac_mode: str = HVACMode.OFF
        self._fan_mode: str = FAN_MEDIUM
        self._temperature: int = 26

        # 消抖用缓存
        self._last_values: dict[str, Any] = {}
        self._last_change: dict[str, float] = {}

    # -------- required props -------- #
    @property
    def hvac_mode(self) -> str:
        return self._hvac_mode

    @property
    def fan_mode(self) -> str:
        return self._fan_mode

    @property
    def target_temperature(self) -> float:
        return self._temperature

    @property
    def target_temperature_step(self) -> float:
        """Return the temperature step."""
        return 1.0

    # -------- control -------- #
    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        try:
            if hvac_mode == HVACMode.OFF:
                await self.coordinator.config_entry.runtime_data.client.async_set_vrv_state(
                    self._device_id, sn=self._device_sn, power=False
                )
                self._hvac_mode = HVACMode.OFF
            else:
                await self.coordinator.config_entry.runtime_data.client.async_set_vrv_state(
                    self._device_id, sn=self._device_sn, power=True, mode=hvac_mode
                )
                self._hvac_mode = hvac_mode
            self.async_write_ha_state()
        except PuGoingAPIError as e:
            _LOGGER.warning("Failed to set hvac_mode for %s: %s", self._device_id, e)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        try:
            await self.coordinator.config_entry.runtime_data.client.async_set_vrv_state(
                self._device_id, sn=self._device_sn, fan_mode=fan_mode
            )
            self._fan_mode = fan_mode
            self.async_write_ha_state()
        except PuGoingAPIError as e:
            _LOGGER.warning("Failed to set fan_mode for %s: %s", self._device_id, e)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        try:
            await self.coordinator.config_entry.runtime_data.client.async_set_vrv_state(
                self._device_id, sn=self._device_sn, temperature=int(temp)
            )
            self._temperature = int(temp)
            self.async_write_ha_state()
        except PuGoingAPIError as e:
            _LOGGER.warning("Failed to set temperature for %s: %s", self._device_id, e)

    # -------- update from coordinator -------- #
    async def async_update(self) -> None:
        dev = next(
            (
                d
                for d in self.coordinator.data.get("devices_by_type", {}).get("VRV", [])
                if d["yid"] == self._device_id
            ),
            None,
        )
        if not dev:
            return

        dcap = dev.get("dcap", "")
        caps = dict(item.split(":") for item in dcap.split(";") if ":" in item)

        power = caps.get("power")
        mode = caps.get("mod")
        temp = caps.get("tem")
        fan = caps.get("ws")

        new_values = {
            "hvac_mode": HVACMode.OFF if power == "00" else self._map_mode(mode),
            "temperature": int(temp) if temp and temp.isdigit() else self._temperature,
            "fan_mode": self._map_fan(fan) if fan else self._fan_mode,
        }

        now = time.time()
        for key, val in new_values.items():
            if self._last_values.get(key) != val:
                # 状态变化了,重置计时器
                self._last_change[key] = now
                self._last_values[key] = val
            # 状态一致,判断是否超过10秒
            elif now - self._last_change.get(key, 0) >= 10:
                setattr(self, f"_{key}", val)

    # -------- extra attrs -------- #
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        dev = next(
            (
                d
                for d in self.coordinator.data.get("devices_by_type", {}).get("VRV", [])
                if d["yid"] == self._device_id
            ),
            {},
        )
        return {
            "sn": dev.get("sn"),
            "dpanel": dev.get("dpanel"),
            "room": dev.get("dloca"),
            "online": dev.get("online"),
            "dcap": dev.get("dcap"),
        }

    @property
    def device_info(self) -> DeviceInfo:
        dev = next(
            (
                d
                for d in self.coordinator.data.get("devices_by_type", {}).get("VRV", [])
                if d["yid"] == self._device_id
            ),
            {},
        )
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=dev.get("dname") or f"VRV {self._device_id}",
            manufacturer="PuGoing",
            model=dev.get("dpanel", "VRV"),
        )

    # -------- helper map -------- #
    def _map_mode(self, mode: str | None) -> str:
        mapping = {
            "01": HVACMode.HEAT,
            "02": HVACMode.COOL,
            "03": HVACMode.DRY,
            "04": HVACMode.FAN_ONLY,
        }
        return mapping.get(mode, HVACMode.OFF)

    def _map_fan(self, fan: str | None) -> str:
        mapping = {
            "01": FAN_LOW,
            "02": FAN_MEDIUM,
            "03": FAN_HIGH,
            "04": FAN_HIGH,  # fallback
        }
        return mapping.get(fan, FAN_MEDIUM)
