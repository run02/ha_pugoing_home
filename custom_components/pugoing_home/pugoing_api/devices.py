class DeviceBase:
    def __init__(self, dcap=None):
        self.dcap = dcap
        if dcap:
            self.parse_dcap(dcap)
        else:
            self.initialize_defaults()

    def parse_dcap(self, dcap):
        raise NotImplementedError("Subclasses must implement parse_dcap method.")

    def initialize_defaults(self):
        pass

class TemperatureControlPanel(DeviceBase):
    # 映射关系
    MODE_MAP = {
        "01": "COOL",
        "02": "DEHUMIDIFICATION",
        "04": "FAN",
        "08": "HEAT",
        "00": "AUTO"
    }
    MODE_MAP_REVERSE = {v: k for k, v in MODE_MAP.items()}

    WIND_SPEED_MAP = {
        "01": "HIGH",
        "02": "MEDIUM",
        "03": "MEDIUM_HIGH",
        "04": "LOW",
        "05": "MEDIUM_LOW",
        "06": "AUTO"
    }
    WIND_SPEED_MAP_REVERSE = {v: k for k, v in WIND_SPEED_MAP.items()}

    POWER_MAP = {
        "00": "OFF",
        "01": "ON"
    }
    POWER_MAP_REVERSE = {v: k for k, v in POWER_MAP.items()}

    def initialize_defaults(self):
        self.power = "OFF"
        self.temperature = 25
        self.mode = "AUTO"
        self.wind_speed = "AUTO"
        self.room_temperature = None

    def parse_dcap(self, dcap):
        # 解析 dcap 字符串
        params = dict(item.split(":") for item in dcap.split(";") if item)
        self.power = self.POWER_MAP.get(params.get("power", "00"), "OFF")
        self.temperature = int(params.get("tem", 25))
        mod_code = params.get("mod")
        self.mode = self.MODE_MAP.get(mod_code, "UNKNOWN") if mod_code else "UNKNOWN"
        ws_code = params.get("ws")
        self.wind_speed = self.WIND_SPEED_MAP.get(ws_code, "UNKNOWN") if ws_code else "UNKNOWN"
        rtem = params.get("rtem")
        self.room_temperature = int(rtem) if rtem else None
        return self

    # 控制方法

    def open(self):
        """开启设备"""
        return "VRV_OPEN"

    def close(self):
        """关闭设备"""
        return "VRV_CLOSE"

    def set_mode(self, mode):
        """
        设置模式
        参数:
            mode (str): 模式名称,取值为 "AUTO", "COOL", "DEHUMIDIFICATION", "FAN", "HEAT"
        返回:
            str: 对应的 dkey
        """
        mode = mode.upper()
        mode_code = self.MODE_MAP_REVERSE.get(mode)
        if not mode_code:
            raise ValueError(f"未知的模式:{mode}")
        mode_dkey_map = {
            "COOL": "VRV_MCOLD",
            "HEAT": "VRV_MHOT",
            "DEHUMIDIFICATION": "VRV_MDRY",
            "FAN": "VRV_MWIND",
            "AUTO": "VRV_MAUTO"  # 假设有对应的 dkey
        }
        dkey = mode_dkey_map.get(mode)
        if not dkey:
            raise ValueError(f"模式 {mode} 没有对应的 dkey")
        return dkey

    def set_wind_speed(self, speed):
        """
        设置风速
        参数:
            speed (str): 风速名称,取值为 "HIGH", "MEDIUM", "LOW", "AUTO"
        返回:
            str: 对应的 dkey
        """
        if type(speed) is int:
            speed=["AUTO","LOW","MEDIUM","HIGH"][speed]
        speed = speed.upper()
        speed_code = self.WIND_SPEED_MAP_REVERSE.get(speed)
        if not speed_code:
            raise ValueError(f"未知的风速:{speed}")
        speed_dkey_map = {
            "HIGH": "VRV_WSH",
            "MEDIUM": "VRV_WSM",
            "LOW": "VRV_WSL",
            # 如果有其他风速对应的 dkey,可以在这里添加
            "AUTO": "VRV_WSAUTO"  # 假设有对应的 dkey
        }
        dkey = speed_dkey_map.get(speed)
        if not dkey:
            raise ValueError(f"风速 {speed} 没有对应的 dkey")
        return dkey

    def set_temperature(self, temp):
        """
        设置温度
        参数:
            temp (int): 温度值,16-30 之间的整数
        返回:
            str: 对应的 dkey
        """
        if not isinstance(temp, int) or not (16 <= temp <= 30):
            raise ValueError("温度必须是16到30之间的整数")
        return f"VRV_T{temp}"


    def activate_dehumidification(self):
        """除湿模式"""
        return "VRV_MDRY"

    def activate_fan_mode(self):
        """送风模式"""
        return "VRV_MWIND"

    def activate_cooling(self):
        """制冷模式"""
        return "VRV_MCOLD"

    def activate_heating(self):
        """制热模式"""
        return "VRV_MHOT"
