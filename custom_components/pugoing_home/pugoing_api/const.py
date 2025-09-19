from enum import Enum

DEVELOPING = True
GA_HTTP_BASE = "http://ga-bp1cljdupfvjxc2b3eytg.aliyunga0019.com"

urls = {
    "domestic": {
        "fetchSnList": "http://wx.xq.cspugoing.com/Manage/device/listsys",
        "fetchSnAndRoomList": "http://wx.xq.cspugoing.com/Manage/room/rooms",
        "fetchDevicesByRoom": "http://wx.xq.cspugoing.com/Manage/room/finddevbyroom",
        "controlDevice": "http://wx.xq.cspugoing.com/Manage/device/plataction",
        "login": "http://wx.xq.cspugoing.com/Manage/Index/login",
        "fetchDeviceByYid": "http://wx.xq.cspugoing.com/Manage/device/devbyyid",
        "fetchScenesBySn": "http://wx.xq.cspugoing.com/Manage/Scene/listsys",
        "executeScene": "http://wx.xq.cspugoing.com/Manage/Scene/scaction",
    },
    "international": {
        "fetchSnList": f"{GA_HTTP_BASE}/Manage/device/listsys",
        "fetchSnAndRoomList": f"{GA_HTTP_BASE}/Manage/room/rooms",
        "fetchDevicesByRoom": f"{GA_HTTP_BASE}/Manage/room/finddevbyroom",
        "controlDevice": f"{GA_HTTP_BASE}/Manage/device/plataction",
        "login": f"{GA_HTTP_BASE}/Manage/Index/login",
        "fetchDeviceByYid": f"{GA_HTTP_BASE}/Manage/device/devbyyid",
    },
}

# 选择环境 ('domestic' 或 'international')
environment = "domestic"
selectedUrls = urls[environment]
api_version = "old"

class Dpanel(str, Enum):
    LAMP = "Lamp"
    LAMP_RGBCW = "LampRGBCW"
    VRV = "VRV"
    CURTAIN_PG = "CurtainPG"
    CURTAIN = "Curtain"
    CURTAIN1 = "Curtain1"
    CURTAIN2 = "Curtain1"
    LampBri = "LampBri"


class Dkey(str, Enum):
    LAMP_OPEN = "LAMP_OPEN"
    LAMP_CLOSE = "LAMP_CLOSE"
    LAMP_BRI = "LAMP_BRI"
    LAMP_CCT = "LAMP_CCT"
    LAMP_RGB = "LAMP_RGB"
    CL_OPEN = "CL_OPEN"
    CL_PAUSE = "CL_PAUSE"
    CL_CLOSE = "CL_CLOSE"
    CL_POS = "CL_POS"

    VRV_OPEN = "VRV_OPEN"
    VRV_CLOSE = "VRV_CLOSE"
    VRV_MCOLD = "VRV_MCOLD"  # 制冷
    VRV_MHOT = "VRV_MHOT"  # 制热
    VRV_MAUTO = "VRV_MAUTO"  # 制热
    VRV_T = "VRV_T"  # 温度
    VRV_MWIND = "VRV_MWIND"  # 风扇
    
    
    DLQ_OPEN="DLQ_OPEN" #断路器打开
    DLQ_CLOSE="DLQ_CLOSE" #断路器关闭