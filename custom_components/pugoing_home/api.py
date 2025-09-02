"""PuGoing 云端 API 客户端。"""

from __future__ import annotations

import time
import logging
from typing import Any, Dict, List

import aiohttp
import async_timeout

from .pugoing_api.api import control_device, login as pugoing_login, process_rooms
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
            "token": "...",
        }
        """
        await self._async_ensure_token()
        devices_by_type = await self._async_fetch_devices()

        return {
            "devices_by_type": devices_by_type,
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
