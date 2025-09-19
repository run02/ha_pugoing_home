"""PuGoing 云端 API 客户端。"""

from __future__ import annotations

import time
import logging
from typing import Any, Dict, List

import aiohttp
import async_timeout

from .pugoing_api.api import (
    control_device,
    execute_scene,
    login as pugoing_login,
    process_rooms,
)
from .pugoing_api.const import Dkey, Dpanel

_LOGGER = logging.getLogger(__name__)

TOKEN_LIFETIME = 24 * 3600     # token 24 小时有效期
TOKEN_BUF = 5 * 60             # 过期前 5 分钟自动续

# ---------------- 自定义异常 ---------------- #
class IntegrationBlueprintApiClientError(Exception):
    """API 统一异常基类。"""


class IntegrationBlueprintApiClientCommunicationError(IntegrationBlueprintApiClientError):
    """通信异常（如超时、解析失败）。"""


class IntegrationBlueprintApiClientAuthenticationError(IntegrationBlueprintApiClientError):
    """鉴权失败异常（用户名密码错误等）。"""


# ---------------- 客户端主体 ---------------- #
class IntegrationBlueprintApiClient:
    """封装 PuGoing 登录与设备拉取/控制逻辑。"""

    def __init__(
        self,
        username: str,
        password: str,
        session: aiohttp.ClientSession,
    ) -> None:
        self._username = username
        self._password = password
        self._session = session

        self._token: str | None = None
        self._token_ts: float | None = None     # token 获取时间戳

    # ====== 主流程入口 ====== #
    async def async_get_data(self) -> Dict[str, Any]:
        """
        返回结构：
        {
            "devices_by_type": { "Lamp": [...], "Switch": [...], ... },
            "scenes_by_sn": { "10D07A48A61A": [ {...}, {...} ] },
            "token": "...",
        }
        """
        await self._async_ensure_token()

        # 一口气获取设备和场景
        result = await process_rooms(self._token)

        return {
            "devices_by_type": result.get("devices", {}),
            "scenes_by_sn": result.get("scenes", {}),
            "token": self._token,
        }

    # ====== 拉设备列表 ====== #
    async def _async_fetch_devices(self) -> Dict[str, List[dict]]:
        """拿到分类好的设备列表。"""
        _LOGGER.debug("Fetching device list with token %s", self._token)
        try:
            async with async_timeout.timeout(15):
                return await process_rooms(self._token)
        except Exception as exc:
            _LOGGER.error("Device fetch failed: %s", exc)
            raise IntegrationBlueprintApiClientCommunicationError(str(exc)) from exc

    # ====== 登录流程 ====== #
    async def _async_login(self) -> None:
        """登录并缓存 token。"""
        _LOGGER.debug("Logging in as %s", self._username)
        try:
            async with async_timeout.timeout(10):
                self._token = await pugoing_login(self._username, self._password)
                self._token_ts = time.time()
                _LOGGER.info("Login ok, token=%s", self._token)
        except Exception as exc:
            _LOGGER.error("Login failed: %s", exc)
            raise IntegrationBlueprintApiClientAuthenticationError(str(exc)) from exc

    async def _async_ensure_token(self) -> None:
        """如果 token 不存在或即将过期则自动续。"""
        if (
            self._token is None
            or self._token_ts is None
            or (time.time() - self._token_ts) > (TOKEN_LIFETIME - TOKEN_BUF)
        ):
            await self._async_login()

    # ====== 控制灯光（开关） ====== #
    async def async_set_lamp_state(
        self,
        device_id: str,
        sn: str,
        on: bool,
        brightness: int | None = None,  # 预留参数，暂不处理
    ) -> None:
        """设置灯光设备状态（目前仅支持开关）。"""
        await self._async_ensure_token()

        key = Dkey.LAMP_OPEN if on else Dkey.LAMP_CLOSE

        try:
            async with async_timeout.timeout(10):
                result = await control_device(sn, 'uip', "", key, device_id, self._token, None)
                _LOGGER.info("Device control successful: %s", result)
        except Exception as e:
            _LOGGER.error("Failed to control lamp %s: %s", device_id, e)
            raise IntegrationBlueprintApiClientCommunicationError(str(e)) from e
        # ====== 控制调光调色灯 ====== #

    async def async_set_dimmer_state(
        self,
        device_id: str,
        sn: str,
        on: bool | None = None,  # 开关
        brightness: int | None = None,  # 0-100
        color_temp: int | None = None,  # 0-100
        rgb_hex: str | None = None,  # "FF0000"
    ) -> None:
        """
        设置调光调色灯状态：
        - 开关：on=True/False
        - 亮度：传 0-100，实际值=整数✖2.54
        - 色温：传 0-100，实际值=(整数✖3.47)+153
        - RGB：传 hex 字符串，比如 "FF0000"
        """
        await self._async_ensure_token()

        tasks: list[tuple[str, str | None]] = []

        # 开关
        if on is True:
            tasks.append((Dkey.LAMP_OPEN, None))
        elif on is False:
            tasks.append((Dkey.LAMP_CLOSE, None))

        # 亮度
        if brightness is not None:
            if 0 <= brightness <= 100:
                bri_value = str(int(brightness * 2.54))
                tasks.append((Dkey.LAMP_BRI, bri_value))
            else:
                raise ValueError("Brightness must be 0-100")

        # 色温
        if color_temp is not None:
            if 0 <= color_temp <= 100:
                cct_value = str(int(color_temp * 3.47 + 153))
                tasks.append((Dkey.LAMP_CCT, cct_value))
            else:
                raise ValueError("Color temp must be 0-100")

        # RGB
        if rgb_hex is not None:
            if len(rgb_hex) == 6:  # 简单校验
                tasks.append((Dkey.LAMP_RGB, rgb_hex.upper()))
            else:
                raise ValueError("RGB must be a 6-digit hex string, e.g., 'FF0000'")

        # 执行控制
        try:
            async with async_timeout.timeout(10):
                for key, extra in tasks:
                    result = await control_device(
                        sn,
                        "uip",
                        "",
                        key,
                        device_id,
                        self._token,
                        extra,
                    )
                    _LOGGER.info(
                        "Dimmer control: key=%s extra=%s result=%s",
                        key,
                        extra,
                        result,
                    )
        except Exception as e:
            _LOGGER.error("Failed to control dimmer lamp %s: %s", device_id, e)
            raise IntegrationBlueprintApiClientCommunicationError(str(e)) from e

    # ====== 控制窗帘（开关） ====== #
    async def async_set_curtain_state(
        self,
        device_id: str,
        sn: str,
        action: str | None = None,  # "open" / "close" / "stop"
        position: int | None = None,  # 0-100
    ) -> None:
        """设置窗帘设备状态（支持开、关、暂停、定位）。"""
        await self._async_ensure_token()

        # -------- key 映射 -------- #
        key = None
        if action == "open":
            key = Dkey.CL_OPEN
        elif action == "close":
            key = Dkey.CL_CLOSE
        elif action == "stop":
            key = Dkey.CL_PAUSE
        elif position is not None:
            key = Dkey.CL_POS
        else:
            raise ValueError(
                f"Invalid curtain command: action={action}, position={position}"
            )

        # -------- 附加参数 -------- #
        # 一般卷帘定位需要传百分比位置，这里可以塞进 value 或 extra 参数
        extra_value = None
        if key == Dkey.CL_POS and position is not None:
            extra_value = str(position)  # 设备协议需要百分比字符串，比如 "65"

        try:
            async with async_timeout.timeout(10):
                result = await control_device(
                    sn,
                    "uip",  # 协议/接口类型
                    "",
                    key,
                    device_id,
                    self._token,
                    extra_value or None,
                )        
                _LOGGER.info(
                    "Curtain control successful: %s (action=%s pos=%s)",
                    result,
                    action,
                    position,
                )
        except Exception as e:
            _LOGGER.error("Failed to control curtain %s: %s", device_id, e)
            raise IntegrationBlueprintApiClientCommunicationError(str(e)) from e

    # ====== 执行场景 ====== #
    async def async_execute_scene(self, sn: str, sid: str) -> dict:
        """执行场景"""
        await self._async_ensure_token()
        try:
            async with async_timeout.timeout(10):
                result = await execute_scene(self._token, sn, sid)
                _LOGGER.info(
                    "Execute scene successful: %s (sn=%s, sid=%s)", result, sn, sid
                )
                return result
        except Exception as e:
            _LOGGER.error("Failed to execute scene sn=%s sid=%s: %s", sn, sid, e)
            raise IntegrationBlueprintApiClientCommunicationError(str(e)) from e

    # ====== 控制空调（VRV） ====== #
    async def async_set_vrv_state(
        self,
        device_id: str,
        sn: str,
        power: bool | None = None,  # True=开，False=关
        mode: str | None = None,  # "cool" / "heat" / "dry" / "fan_only"
        fan_mode: str | None = None,  # "high" / "medium" / "low"
        temperature: int | None = None,  # 16-30
    ) -> None:
        """设置空调状态：开关/模式/风速/温度。"""
        await self._async_ensure_token()

        tasks = []

        # 开关
        if power is True:
            tasks.append((Dkey.VRV_OPEN, None))
        elif power is False:
            tasks.append((Dkey.VRV_CLOSE, None))

        # 模式
        if mode == "cool":
            tasks.append((Dkey.VRV_MCOLD, None))
        elif mode == "heat":
            tasks.append((Dkey.VRV_MHOT, None))
        elif mode == "dry":
            tasks.append(("VRV_MDRY", None))
        elif mode == "fan_only":
            tasks.append((Dkey.VRV_MWIND, None))

        # 风速
        if fan_mode == "high":
            tasks.append(("VRV_WSH", None))
        elif fan_mode == "medium":
            tasks.append(("VRV_WSM", None))
        elif fan_mode == "low":
            tasks.append(("VRV_WSL", None))

        # 温度
        if temperature is not None:
            if 16 <= temperature <= 30:
                tasks.append((f"VRV_T{temperature}", None))
            else:
                raise ValueError("VRV temperature must be 16-30")

        try:
            async with async_timeout.timeout(10):
                for key, extra in tasks:
                    result = await control_device(
                        sn,
                        "uip",
                        "",
                        key,
                        device_id,
                        self._token,
                        extra,
                    )
                    _LOGGER.info(
                        "VRV control: key=%s extra=%s result=%s", key, extra, result
                    )
        except Exception as e:
            _LOGGER.error("Failed to control VRV %s: %s", device_id, e)
            raise IntegrationBlueprintApiClientCommunicationError(str(e)) from e
