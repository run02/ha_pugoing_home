import asyncio
import aiohttp
import json
import logging
from datetime import datetime
from collections import defaultdict
from .const import selectedUrls, DEVELOPING, api_version
from .utils import LoggerUtility
from .error import DeviceOfflineError, NoPermissionError, PuGoingInvalidResponseError

lib_logger = LoggerUtility(name="lib_logger", log_level=logging.DEBUG)
# lib_logger = LoggerUtility(name="lib_logger", log_level=logging.INFO)


def build_token_headers(token):
    return {"Authorization": f"Bearer {token}"} if api_version == "next" else {}


def build_token_payload(token, data=None):
    if api_version != "next":
        base = data or {}
        base["token"] = token
        return base
    return data


async def fetch_device_by_yid(token, sn, yid) -> dict:
    data = build_token_payload(token, {"sn": sn, "yid": yid})
    headers = build_token_headers(token)

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                selectedUrls["fetchDeviceByYid"], json=data, headers=headers, timeout=15
            ) as response:
                result = await response.json()
                if result.get("ack") == 1:
                    device_info = result["data"]["ackinfo"]
                    if isinstance(device_info, list) and len(device_info) > 0:
                        return device_info[0]
                    else:
                        raise PuGoingInvalidResponseError("查询设备状态时应答的数据为空")
                elif result.get("ack") == 0:
                    error_message = result.get("msg", "Unknown error")
                    if error_message == "主机不在线":
                        raise DeviceOfflineError()
                    elif error_message == "您没有此权限访问该主机":
                        raise NoPermissionError()
                    lib_logger.error(f"Request failed with message: {error_message}")
                else:
                    lib_logger.error(f"Request failed with message: {result.get('msg')}")
                    raise Exception(f"Request failed with message: {result.get('msg')}")
        except Exception as e:
            lib_logger.error(f"Error during fetch_device_by_yid: {e}")
            raise e


async def fetch_sn_list(token):
    data = build_token_payload(token)
    headers = build_token_headers(token)

    async with aiohttp.ClientSession() as session:
        async with session.post(
            selectedUrls["fetchSnList"], json=data, headers=headers, timeout=15
        ) as response:
            result = await response.json()
            if result.get("ack") == 1:
                return result["data"]["list"]
            else:
                lib_logger.error(f"Request failed with message: {result.get('msg')}")
                raise Exception(f"Request failed with message: {result.get('msg')}")


async def fetch_devices_by_room(token, sn, room_name):
    data = build_token_payload(token, {"sn": sn, "roomname": room_name})
    headers = build_token_headers(token)

    async with aiohttp.ClientSession() as session:
        async with session.post(
            selectedUrls["fetchDevicesByRoom"], json=data, headers=headers, timeout=15
        ) as response:
            result = await response.json()
            if result.get("ack") == 1:
                return result["data"]["list"]
            else:
                lib_logger.error(f"Request failed with message: {result.get('msg')}")
                raise Exception(f"Request failed with message: {result.get('msg')}")

async def fetch_scenes_by_sn(token: str, sn: str):
    """根据主机 SN 获取场景列表"""
    data = build_token_payload(token, {"sn": sn})
    headers = build_token_headers(token)

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                selectedUrls["fetchScenesBySn"], json=data, headers=headers, timeout=15
            ) as response:
                result = await response.json()
                if result.get("ack") == 1:
                    return result["data"]["list"]
                else:
                    error_message = result.get("msg", "Unknown error")
                    if error_message == "主机不在线":
                        raise DeviceOfflineError()
                    elif error_message == "您没有此权限访问该主机":
                        raise NoPermissionError()
                    lib_logger.error(f"fetch_scenes_by_sn failed: {error_message}")
                    return []
        except Exception as e:
            lib_logger.error(f"Error during fetch_scenes_by_sn: {e}")
            raise e


async def control_device(sn, fm, dvcm, dkey, yid, token, digv=None):
    data = {"sn": sn, "fm": fm, "dvcm": dvcm, "dkey": dkey, "yid": yid}
    if digv is not None:
        data["digv"] = digv
    data = build_token_payload(token, data)
    headers = build_token_headers(token)

    lib_logger.debug("control data: ", data)

    async with aiohttp.ClientSession() as session:
        async with session.post(
            selectedUrls["controlDevice"], json=data, headers=headers, timeout=15
        ) as response:
            result = await response.json()
            if result.get("ack") == 0:
                error_message = result.get("msg", "Unknown error")
                if error_message == "主机不在线":
                    raise DeviceOfflineError()
                elif error_message == "您没有此权限访问该主机":
                    raise NoPermissionError()
                lib_logger.error(f"Request failed with message: {result.get('msg')}")
            else:
                lib_logger.info("Device control successful:", result)
            return result


async def fetch_sn_and_room_list(token):
    data = build_token_payload(token)
    headers = build_token_headers(token)

    async with aiohttp.ClientSession() as session:
        async with session.post(
            selectedUrls["fetchSnAndRoomList"], json=data, headers=headers, timeout=15
        ) as response:
            result = await response.json()
            if result.get("ack") == 1:
                return result["data"]["list"]
            else:
                lib_logger.error(f"Request failed with message: {result.get('msg')}")
                raise Exception(f"Request failed with message: {result.get('msg')}")


async def categorize_devices_by_panel(token, sn, room_name):
    devices = await fetch_devices_by_room(token, sn, room_name)
    categorized_devices = {}

    for device in devices:
        panel_type = device.get("dpanel", "Unknown")
        device["sn"] = sn
        categorized_devices.setdefault(panel_type, []).append(device)

    return categorized_devices


def merge_dicts(dict_list):
    merged_dict = defaultdict(list)
    for d in dict_list:
        for key, value in d.items():
            merged_dict[key].extend(value)
    return dict(merged_dict)


async def process_rooms(token):
    sn_room_list = await fetch_sn_and_room_list(token)
    lib_logger.debug(
        "Retrieved sn_room_list:", json.dumps(sn_room_list, ensure_ascii=False)
    )

    if not sn_room_list:
        return {"event": {"header": None, "payload": None}}

    devices_all = []
    scenes_all = {}

    for sn_room in sn_room_list:
        sn = sn_room["sn"]

        # 获取场景
        try:
            scenes = await fetch_scenes_by_sn(token, sn)
            if scenes:
                scenes_all[sn] = scenes
        except Exception as e:
            lib_logger.error(f"Error fetching scenes for sn {sn}: {str(e)}")

        # 获取设备
        room_list = sn_room["room"]
        for room in room_list:
            try:
                devices = await categorize_devices_by_panel(token, sn, room["name"])
                if devices:
                    devices_all.append(devices)
            except Exception as e:
                lib_logger.error(f"Error processing room {room['name']}: {str(e)}")

    lib_logger.debug("Processed devices:", json.dumps(devices_all, ensure_ascii=False))
    lib_logger.debug("Processed scenes:", json.dumps(scenes_all, ensure_ascii=False))

    return {
        "devices": merge_dicts(devices_all),
        "scenes": scenes_all,
    }


async def get_devices_by_hotel_room_name(name: str, token: str) -> dict:
    sn_list, sn_room_list = await asyncio.gather(
        fetch_sn_list(token), fetch_sn_and_room_list(token)
    )

    sn = ""
    for item in sn_list:
        room_name = item.get("name", "")
        if not isinstance(room_name, str):
            continue
        room_num = room_name.split("|")[1] if "|" in room_name else room_name
        if room_num == name:
            sn = item.get("sn")
            break

    room_list = next((item.get("room", []) for item in sn_room_list if item.get("sn") == sn), [])

    tasks = [categorize_devices_by_panel(token, sn, room['name']) for room in room_list]
    devices_all = []

    try:
        results = await asyncio.gather(*tasks)
        for i, devices in enumerate(results):
            if devices:
                devices_all.append(devices)
    except Exception as e:
        lib_logger.error(f"Error processing rooms: {str(e)}")

    return merge_dicts(devices_all)


async def login(username: str, password: str):
    data = {"account": username, "pwd": password}

    async with aiohttp.ClientSession() as session:
        async with session.post(selectedUrls["login"], json=data, timeout=15) as response:
            if response.status != 200:
                lib_logger.error("Login request failed with status code: %s", response.status)
                raise Exception(f"Login request failed with status code: {response.status}")

            result = await response.json()
            if result.get("ack") == 1:
                return result["data"]["token"]
            else:
                lib_logger.error(f"Login failed with message: {result.get('msg')}")
                raise Exception(f"Login failed with message: {result.get('msg')}")
async def execute_scene(token: str, sn: str, sid: str) -> dict:
    """执行指定场景"""
    data = build_token_payload(token, {"sn": sn, "sid": sid})
    headers = build_token_headers(token)

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                selectedUrls["executeScene"],  # 记得在 const.py 里配置这个URL
                json=data,
                headers=headers,
                timeout=15,
            ) as response:
                result = await response.json()
                if result.get("ack") == 1:
                    return result
                else:
                    error_message = result.get("msg", "Unknown error")
                    lib_logger.error(f"Execute scene failed: {error_message}")
                    raise PuGoingInvalidResponseError(error_message)
        except Exception as e:
            lib_logger.error(f"Error during execute_scene: {e}")
            raise e
