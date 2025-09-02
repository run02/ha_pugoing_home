# custom_components/pugoing_home/assist_mqtt_bridge.py
"""独立使用 paho-mqtt 的 Assist ↔ MQTT 桥接。

功能：
* 连接 47.123.5.29:1883
* 订阅 /test/1        （收到文本→调用 Assist）
* 把执行结果发布 /test/1/response
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

import paho.mqtt.client as mqtt
from homeassistant.components import conversation
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.core import Context  
from homeassistant.components.conversation import ConversationResult
_LOGGER = logging.getLogger(__name__)
# -----------------------------------------------------------
# 兼容各种版本的辅助函数
# -----------------------------------------------------------
def _extract_speech(resp) -> str:
    """从 response 对象或 dict 中安全提取 plain.speech."""
    try:
        # 新版：resp.speech.plain.speech
        return (
            getattr(getattr(getattr(resp, "speech", None), "plain", None), "speech", "")
            or ""
        ).strip()
    except Exception:  # noqa: BLE001
        pass

    # 旧版：dict 形式
    if isinstance(resp, dict):
        return (
            resp.get("speech", {})
            .get("plain", {})
            .get("speech", "")
            .strip()
        )
    return ""


def _extract_intent_type(intent) -> str | None:
    """安全获取 intent.intent_type."""
    if intent is None:
        return None
    # 新版 dataclass
    t = getattr(intent, "intent_type", None)
    if t:
        return t
    # 旧版 dict
    if isinstance(intent, dict):
        return intent.get("intent_type")
    return None



class AssistMqttBridge:
    """paho-mqtt 线程 + Home Assistant 协程的安全桥接。"""

    _HOST = "47.123.5.29"
    _PORT = 1883
    _SUB_TOPIC = "/test/1"
    _PUB_TOPIC = "/test/1/response"
    _LANG = "zh-CN"

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._client: mqtt.Client | None = None
        self._thread: threading.Thread | None = None

    # ------------------------ 生命周期 ------------------------ #
    async def start(self) -> None:
        """创建并启动 paho-mqtt 客户端（独立线程跑 loop）。"""
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

    # 注意：stop 只能在协程里调用，因为需要等待线程结束
    async def _async_stop(self, *_args) -> None:  # noqa: D401
        """停止 MQTT 循环并等待线程退出。"""
        if self._client:
            self._client.disconnect()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        _LOGGER.info("Assist-MQTT bridge stopped")

    # ---------------------- paho 回调 ----------------------- #
    # 这些回调运行在 MQTT 线程里，不能直接调用任何异步 API，
    # 必须使用 hass.loop.call_soon_threadsafe 进入主循环。

    def _on_connect(self, client, _userdata, _flags, rc):  # noqa: N802
        if rc == 0:
            _LOGGER.info("MQTT connected")
            client.subscribe(self._SUB_TOPIC, qos=0)
        else:
            _LOGGER.warning("MQTT connect failed rc=%s", rc)

    def _on_disconnect(self, _client, _userdata, rc):  # noqa: N802
        _LOGGER.warning("MQTT disconnected rc=%s", rc)

    def _on_message(self, _client, _userdata, msg):  # noqa: N802
        text = msg.payload.decode(errors="ignore").strip()
        if not text:
            _LOGGER.debug("Empty payload ignored")
            return

        _LOGGER.debug("Voice command: %s", text)

        # 在 HA 事件循环中处理
        self.hass.loop.call_soon_threadsafe(
            self._schedule_assist, text
        )

    # ---------------------- Assist 调用 --------------------- #
    def _schedule_assist(self, text: str) -> None:
        """包装成 task，留在主线程执行协程。"""
        self.hass.async_create_task(self._assist_and_respond(text))

    # -----------------------------------------------------------
    # 修改后的 _assist_and_respond
    # -----------------------------------------------------------
    async def _assist_and_respond(self, text: str) -> None:
        try:
            result: ConversationResult = await conversation.async_converse(
                hass=self.hass,
                text=text,
                conversation_id="mqtt_bridge",
                context=Context(),
                language=self._LANG,
                agent_id=None,
            )

            speech = _extract_speech(result.response) or "（Assist 无回复）"
            intent_type = _extract_intent_type(getattr(result, "intent", None))

            # intent_input 在旧版才有；若缺就用原文
            intent_input = getattr(result, "intent_input", None) or text

            payload = {
                "ok": True,
                "speech": speech,
                "intent_input": intent_input,
                "intent": intent_type,
            }
            _LOGGER.info("Assist success: %s → %s", text, speech)

        except Exception as exc:  # noqa: BLE001
            _LOGGER.exception("Assist failed: %s", exc)
            payload = {"ok": False, "error": str(exc)}

        if self._client:
            self._client.publish(
                self._PUB_TOPIC,
                json.dumps(payload, ensure_ascii=False),
                qos=0,
                retain=False,
            )
