"""Switch platform for PuGoing integration (integration_blueprint)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers import (
    area_registry as ar,
)
from homeassistant.helpers import (
    device_registry as dr,
)
from homeassistant.helpers import (
    entity_registry as er,
)
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, LAMP_STATE_DEBOUNCE_SECONDS
from .entity import IntegrationBlueprintEntity
from .pugoing_api.error import PuGoingAPIError

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import BlueprintDataUpdateCoordinator
    from .data import IntegrationBlueprintConfigEntry

DCAP_VOLTAGE_INDEX = 3
DCAP_CURRENT_INDEX = 4
DCAP_TEMPERATURE_INDEX = 6

_LOGGER = logging.getLogger(__name__)


# ----------------------------- setup ------------------------------------ #
async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntegrationBlueprintConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create switch entities for every breaker device and listen for changes."""
    coordinator: BlueprintDataUpdateCoordinator = entry.runtime_data.coordinator
    known_ids: set[str] = set()

    def _create_entity(device: dict[str, Any]) -> PuGoingBreakerSwitch:
        """Create a breaker entity from raw device data."""
        return PuGoingBreakerSwitch(coordinator, device)

    async def _async_add_initial() -> None:
        """Add breaker entities discovered during initial setup."""
        breakers = coordinator.data.get("devices_by_type", {}).get("Breaker", [])
        entities: list[PuGoingBreakerSwitch] = []
        for device in breakers:
            yid = device["yid"]
            known_ids.add(yid)
            entities.append(_create_entity(device))
        if entities:
            async_add_entities(entities)
            _LOGGER.info("Added %d initial breaker entities", len(entities))

    await _async_add_initial()

    def _handle_breaker_changes() -> None:
        """Handle dynamic additions and removals reported by the coordinator."""
        devices_by_type = coordinator.data.get("devices_by_type", {})
        breakers_now: list[dict[str, Any]] = devices_by_type.get("Breaker", [])
        current_ids: set[str] = {device["yid"] for device in breakers_now}

        # Detect new breakers
        new_ids = current_ids - known_ids
        if new_ids:
            new_entities = [
                _create_entity(device)
                for device in breakers_now
                if device["yid"] in new_ids
            ]
            known_ids.update(new_ids)
            async_add_entities(new_entities)
            _LOGGER.info("Dynamically added %d breaker entities", len(new_entities))

        # Detect removed breakers
        removed_ids = known_ids - current_ids
        if not removed_ids:
            return

        reg = er.async_get(hass)
        for yid in removed_ids:
            unique_id = f"{yid}"
            ent_id = reg.async_get_entity_id("switch", DOMAIN, unique_id)
            if ent_id:
                _LOGGER.info("Removing stale breaker entity: %s", ent_id)
                reg.async_remove(ent_id)
        known_ids.difference_update(removed_ids)

    coordinator.async_add_listener(_handle_breaker_changes)


# ----------------------------- entity: 断路器 --------------------------- #
class PuGoingBreakerSwitch(IntegrationBlueprintEntity, SwitchEntity):
    """Representation of a breaker device."""

    _attr_icon = "mdi:power"

    def __init__(
        self, coordinator: BlueprintDataUpdateCoordinator, device: dict[str, Any]
    ) -> None:
        """Initialise the breaker entity from coordinator data."""
        super().__init__(coordinator)
        self._device_id = device["yid"]
        self._device_sn = device.get("sn", self._device_id)
        self._attr_unique_id = f"{self._device_id}"
        # 优先用 danam, 如果为空或不存在则使用 dname
        danam = device.get("danam", "")
        dname = device.get("dname", "Breaker")
        self._attr_name = danam if danam else dname
        self._state: bool = self._parse_state(device)
        self._last_manual_control: datetime | None = None

    # ---------- helpers ---------- #
    @staticmethod
    def _parse_state(device: dict[str, Any]) -> bool:
        """Parse the on/off state from the device payload."""
        return str(device.get("dinfo", "")) == "开"

    def _latest(self) -> dict[str, Any] | None:
        """Return the latest coordinator payload for this device."""
        for dev in self.coordinator.data.get("devices_by_type", {}).get("Breaker", []):
            if dev["yid"] == self._device_id:
                return dev
        return None

    # ---------- required props ----- #
    @property
    def is_on(self) -> bool:
        """Return whether the breaker is currently on."""
        if self._last_manual_control and (
            datetime.now(tz=UTC) - self._last_manual_control
            < timedelta(seconds=LAMP_STATE_DEBOUNCE_SECONDS)
        ):
            return self._state

        latest = self._latest()
        if latest is not None:
            self._state = self._parse_state(latest)
        return self._state

    @property
    def available(self) -> bool:
        """Return whether the breaker still exists in the coordinator data."""
        return self._latest() is not None

    # ---------- control ------------ #
    async def async_turn_on(self, **_kwargs: Any) -> None:
        """Turn on the breaker, updating local state optimistically."""
        client = self.coordinator.config_entry.runtime_data.client
        try:
            await client.async_set_breaker_state(
                self._device_id,
                sn=self._device_sn,
                on=True,
            )
            self._state = True
            self._last_manual_control = datetime.now(tz=UTC)
            self.async_write_ha_state()
        except PuGoingAPIError as err:
            _LOGGER.warning("Failed to turn on breaker %s: %s", self._device_id, err)

    async def async_turn_off(self, **_kwargs: Any) -> None:
        """Turn off the breaker, updating local state optimistically."""
        client = self.coordinator.config_entry.runtime_data.client
        try:
            await client.async_set_breaker_state(
                self._device_id,
                sn=self._device_sn,
                on=False,
            )
            self._state = False
            self._last_manual_control = datetime.now(tz=UTC)
            self.async_write_ha_state()
        except PuGoingAPIError as err:
            _LOGGER.warning("Failed to turn off breaker %s: %s", self._device_id, err)

    # ---------- extra attrs -------- #
    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional diagnostic attributes for the breaker."""
        dev = self._latest()
        if dev is None:
            return None
        diagnostics = dev.get("dcap")
        metrics = diagnostics.split(";") if diagnostics else []
        return {
            "sn": dev.get("sn"),
            "dpanel": dev.get("dpanel"),
            "room": dev.get("dloca"),
            "online": dev.get("online"),
            "danam": dev.get("danam"),
            "voltage": metrics[DCAP_VOLTAGE_INDEX]
            if len(metrics) > DCAP_VOLTAGE_INDEX
            else None,
            "current": metrics[DCAP_CURRENT_INDEX]
            if len(metrics) > DCAP_CURRENT_INDEX
            else None,
            "temperature": metrics[DCAP_TEMPERATURE_INDEX]
            if len(metrics) > DCAP_TEMPERATURE_INDEX
            else None,
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Expose each breaker as an individual device."""
        dev = self._latest() or {}
        # 优先使用 danam, 如果为空或不存在则使用 dname
        danam = dev.get("danam", "")
        dname = dev.get("dname", f"Breaker {self._device_id}")
        device_name = danam if danam else dname

        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=device_name,
            manufacturer=dev.get("dsign", "PuGoing"),
            model=dev.get("dpanel", "Breaker"),
        )

    # ---------- HA 回调: 实体已加入 ---------------- #
    async def async_added_to_hass(self) -> None:
        """Assign the breaker to the correct area once it is registered."""
        await super().async_added_to_hass()

        reg = dr.async_get(self.hass)
        device = reg.async_get_device(identifiers={(DOMAIN, self._device_id)})
        if device is None:
            return

        dev = self._latest()
        if dev is None:
            return

        area_name = dev.get("dloca")
        if not area_name:
            return

        area_reg = ar.async_get(self.hass)
        area = area_reg.async_get_area_by_name(area_name)
        if area is None:
            area = area_reg.async_create(area_name)

        if device.area_id != area.id:
            reg.async_update_device(device.id, area_id=area.id)
