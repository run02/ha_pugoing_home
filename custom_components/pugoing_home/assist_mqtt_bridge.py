# custom_components/pugoing_home/assist_mqtt_bridge.py

import json
import logging
import threading
from typing import Any

import paho.mqtt.client as mqtt
from homeassistant.components import conversation
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, Context
from homeassistant.components.conversation import ConversationResult

_LOGGER = logging.getLogger(__name__)


def _extract_speech(resp) -> str:
    """从 response 对象或 dict 中安全提取 plain.speech."""
    try:
        return (
            getattr(getattr(getattr(resp, "speech", None), "plain", None), "speech", "")
            or ""
        ).strip()
    except Exception:
        pass
    if isinstance(resp, dict):
        return resp.get("speech", {}).get("plain", {}).get("speech", "").strip()
    return ""


def _extract_intent_type(intent) -> str | None:
    """安全获取 intent.intent_type."""
    if intent is None:
        return None
    t = getattr(intent, "intent_type", None)
    if t:
        return t
    if isinstance(intent, dict):
        return intent.get("intent_type")
    return None


class AssistMqttBridge:
    """paho-mqtt 线程 + Home Assistant 协程的安全桥接."""

    _HOST = "47.123.5.29"
    _PORT = 1883
    _LANG = "zh-CN"

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._client: mqtt.Client | None = None
        self._thread: threading.Thread | None = None
        self._subscribed: set[str] = set()  # 已经订阅过的主题集合

    # ------------------------ 生命周期 ------------------------ #
    async def start(self) -> None:
        """创建并启动 paho-mqtt 客户端."""
        self._client = mqtt.Client()
        self._client.enable_logger(_LOGGER)

        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect

        self._client.connect(self._HOST, self._PORT, keepalive=30)

        self._thread = threading.Thread(
            target=self._client.loop_forever, name="assist_mqtt_loop", daemon=True
        )
        self._thread.start()
        _LOGGER.info("Assist-MQTT bridge thread started")

        # 当 HA 关闭时停止
        self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._async_stop)

    async def _async_stop(self, *_args) -> None:
        """停止 MQTT 循环并等待线程退出."""
        if self._client:
            self._client.disconnect()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        _LOGGER.info("Assist-MQTT bridge stopped")

    # ---------------------- 动态订阅 ----------------------- #
    def subscribe_device(self, xqid: str) -> None:
        """订阅一个新的 ha/{xqid} 主题."""
        if not self._client:
            return
        topic = f"/ha/{xqid}"
        if topic not in self._subscribed:
            self._client.subscribe(topic, qos=0)
            self._subscribed.add(topic)
            _LOGGER.info("Subscribed to device topic %s", topic)

    # ---------------------- paho 回调 ----------------------- #
    def _on_connect(self, client, _userdata, _flags, rc):  # noqa: N802
        if rc == 0:
            _LOGGER.info("MQTT connected")
            # 已知的 topic 会在 subscribe_device 时动态添加
        else:
            _LOGGER.warning("MQTT connect failed rc=%s", rc)

    def _on_disconnect(self, _client, _userdata, rc):  # noqa: N802
        _LOGGER.warning("MQTT disconnected rc=%s", rc)

    def _on_message(self, _client, _userdata, msg):  # noqa: N802
        text = msg.payload.decode(errors="ignore").strip()
        if not text:
            _LOGGER.debug("Empty payload ignored")
            return

        _LOGGER.debug("Voice command on %s: %s", msg.topic, text)

        # 提取 xqid (ha/{xqid})
        try:
            _, xqid = msg.topic.split("/", 1)
        except ValueError:
            _LOGGER.warning("Unexpected topic format: %s", msg.topic)
            return

        self.hass.loop.call_soon_threadsafe(self._schedule_assist, text, xqid)

    # ---------------------- Assist 调用 --------------------- #
    def _schedule_assist(self, text: str, xqid: str) -> None:
        """包装成 task，留在主线程执行协程."""
        self.hass.async_create_task(self._assist_and_respond(text, xqid))

    async def _assist_and_respond(self, text: str, xqid: str) -> None:
        try:
            result: ConversationResult = await conversation.async_converse(
                hass=self.hass,
                text=text,
                conversation_id=f"mqtt_bridge_{xqid}",
                context=Context(),
                language=self._LANG,
                agent_id=None,
            )

            speech = _extract_speech(result.response) or "（Assist 无回复）"
            intent_type = _extract_intent_type(getattr(result, "intent", None))
            intent_input = getattr(result, "intent_input", None) or text

            payload = {
                "ok": True,
                "speech": speech,
                "intent_input": intent_input,
                "intent": intent_type,
            }
            _LOGGER.info("Assist success [%s]: %s → %s", xqid, text, speech)

        except Exception as exc:
            _LOGGER.exception("Assist failed: %s", exc)
            payload = {"ok": False, "error": str(exc)}

        if self._client:
            self._client.publish(
                f"ha/{xqid}/response",
                json.dumps(payload, ensure_ascii=False),
                qos=0,
                retain=False,
            )
