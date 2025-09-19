# custom_components/integration_blueprint/button.py

from __future__ import annotations
import logging
from typing import Any, TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.helpers import entity_registry as er
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


# ----------------------------- setup ------------------------------------ #
async def async_setup_entry(
    hass: HomeAssistant,
    entry: IntegrationBlueprintConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create Button entities for every Scene."""
    coordinator: BlueprintDataUpdateCoordinator = entry.runtime_data.coordinator

    known_ids: set[str] = set()

    def _create_entity(sn: str, sc: dict[str, Any]):
        return PuGoingSceneButton(coordinator, sn, sc)

    async def _async_add_initial() -> None:
        scenes_by_sn: dict[str, list[dict]] = coordinator.data.get("scenes_by_sn", {})
        entities = []
        for sn, scenes in scenes_by_sn.items():
            for sc in scenes:
                sid = sc["sid"]
                if sid in known_ids:
                    continue
                known_ids.add(sid)
                entities.append(_create_entity(sn, sc))
        if entities:
            async_add_entities(entities)
            _LOGGER.info("Added %d initial Scene buttons", len(entities))

    await _async_add_initial()

    # ---------------- listener: 动态更新 ---------------------------#
    def _handle_scene_changes() -> None:
        scenes_by_sn: dict[str, list[dict]] = coordinator.data.get("scenes_by_sn", {})
        current_ids: set[str] = {
            sc["sid"] for scenes in scenes_by_sn.values() for sc in scenes
        }

        # 新增
        new_ids = current_ids - known_ids
        if new_ids:
            new_entities = []
            for sn, scenes in scenes_by_sn.items():
                for sc in scenes:
                    if sc["sid"] in new_ids:
                        new_entities.append(_create_entity(sn, sc))
                        known_ids.add(sc["sid"])
            async_add_entities(new_entities)
            _LOGGER.info("Dynamically added %d Scene buttons", len(new_entities))

        # 删除
        removed_ids = known_ids - current_ids
        if removed_ids:
            reg = er.async_get(hass)
            for sid in removed_ids:
                unique_id = f"scene_{sid}"
                ent_id = reg.async_get_entity_id("button", DOMAIN, unique_id)
                if ent_id:
                    _LOGGER.info("Removing stale Scene button: %s", ent_id)
                    reg.async_remove(ent_id)
            known_ids.difference_update(removed_ids)

    coordinator.async_add_listener(_handle_scene_changes)


# ----------------------------- entity ----------------------------------- #
class PuGoingSceneButton(IntegrationBlueprintEntity, ButtonEntity):
    """无状态场景按钮，按下即触发场景。"""

    def __init__(self, coordinator, sn: str, scene: dict[str, Any]):
        super().__init__(coordinator)
        self._sn = sn
        self._sid = scene["sid"]
        self._scene = scene
        self._attr_unique_id = f"scene_{self._sid}"
        self._attr_name = scene.get("sna", "场景")

    async def async_press(self, **kwargs: Any) -> None:
        try:
            await self.coordinator.config_entry.runtime_data.client.async_execute_scene(
                sn=self._sn,
                sid=self._sid,
            )
            _LOGGER.info("Executed scene %s (%s)", self._scene.get("sna"), self._sid)
        except PuGoingAPIError as e:
            _LOGGER.warning("Failed to execute scene %s: %s", self._sid, e)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return {
            "sn": self._sn,
            "sid": self._sid,
            "room": self._scene.get("room"),
            "last_info": self._scene.get("sinfo"),
        }

    @property
    def device_info(self) -> DeviceInfo:
        """让每个场景按钮单独成设备。"""
        return DeviceInfo(
            identifiers={(DOMAIN, f"scene_{self._sid}")},
            name=self._scene.get("sna") or f"Scene {self._sid}",
            manufacturer="PuGoing",
            model="Scene",
        )
