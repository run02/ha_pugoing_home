import logging

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers import entity_registry as er

_LOGGER = logging.getLogger(__name__)
def get_entity_by_device_id(hass, device_id: str):
    reg = er.async_get(hass)
    # 你的 unique_id 格式是 f"{device_id}"
    unique_id = f"{device_id}"
    entity_id = reg.async_get_entity_id("light", "pugoing_home", unique_id)
    if entity_id:
        return hass.states.get(entity_id)  # 返回状态对象,可以取 attributes
    return None


"""
http://localhost:8123/pugoing_ha

"""
class PuGoingApiMainView(HomeAssistantView):
    url = "/pugoing_ha"
    name = "pugoing_ha"
    requires_auth = False

    async def get(self, request):
        return web.json_response({"message": "Main endpoint"})



class PuGoingApiSub2View(HomeAssistantView):
    url = "/pugoing_ha/sub2"
    name = "pugoing_ha_sub2"
    requires_auth = False

    async def get(self, request):
        return web.json_response({"message": "Sub2 endpoint"})

class PuGoingApiPublishView(HomeAssistantView):
    """接收外部调用的 Publish API,例如:开灯/关灯 or 仅更新状态"""

    url = "/pugoing_ha/publish"
    name = "pugoing_ha_publish"
    requires_auth = False

    async def post(self, request):
        """接收 JSON: {"device_id": "...", "action": "on", "act": "update|control"}"""
        hass = request.app["hass"]  # 拿到 HA 实例
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        device_id = data.get("device_id")
        action = data.get("action")
        act = data.get("act", "control")  # 默认 control

        if not device_id or not action:
            return web.json_response(
                {"error": "missing device_id or action"}, status=400
            )

        dev = get_entity_by_device_id(hass, device_id)
        if not dev:
            return web.json_response(
                {"error": f"device {device_id} not found"}, status=404
            )
        dpanel = dev.attributes.get("dpanel", "Unknown")
        print(f"dpanel: {dpanel}")

        entity_id = dev.entity_id
        new_state = "on" if action.lower() in ("on", "open", "1") else "off"
        if dpanel == "Lamp":
            print("is lamp")
        try:
            if act == "update":
                # 仅更新状态,不调用服务
                hass.states.async_set(
                    entity_id,
                    new_state,
                    dev.attributes,
                )
                msg = f"{entity_id} state updated to {new_state.upper()}"
            # 默认 act=control,调用服务真正控制
            elif new_state == "on":
                await hass.services.async_call(
                    "light",
                    "turn_on",
                    {"entity_id": entity_id},
                    blocking=True,
                )
                msg = f"{entity_id} turned ON"
            else:
                await hass.services.async_call(
                    "light",
                    "turn_off",
                    {"entity_id": entity_id},
                    blocking=True,
                )
                msg = f"{entity_id} turned OFF"

            _LOGGER.info(msg)
            return web.json_response({"result": msg})
        except Exception as e:
            _LOGGER.exception("Publish API failed: %s", e)
            return web.json_response({"error": str(e)}, status=500)
