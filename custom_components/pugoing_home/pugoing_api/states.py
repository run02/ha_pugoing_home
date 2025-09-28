# import re

# from .const import Dkey
# from ..pugoing_dui.dui_models.common import SUPPORTED_COLORS

# import colorsys


# class AirConditionerState:
#     def __init__(self, power="1", mode="2", temperature="25", air_speed="1", air_direction_auto="1", fan_direction="1"):
#         self.power = power  # 1-开机, 2-关机
#         self.mode = mode  # 1-自动, 2-制冷, 3-除湿, 4-送风, 5-制热
#         self.temperature = temperature  # 19~30度
#         self.air_speed = air_speed  # 1-自动风量, 2-低风量, 3-中风量, 4-高风量
#         self.air_direction_auto = air_direction_auto  # 1-自动风向, 0-手动风向
#         self.fan_direction = fan_direction  # 1-向上, 2-中, 3-向下

#     def __repr__(self):
#         return f"AirConditionerState(power={self.power}, mode={self.mode}, temperature={self.temperature}, " \
#                f"air_speed={self.air_speed}, " \
#                f"air_direction_auto={self.air_direction_auto}, fan_direction={self.fan_direction})"


# class AirConditionerController:
#     # 空调的模式和风速等选项的静态常量
#     AC_POWER_ON = "1"
#     AC_POWER_OFF = "0"
#     AC_MODE_AUTO = "1"
#     AC_MODE_COOL = "2"
#     AC_MODE_DEHUMIDIFICATION = "3"
#     AC_MODE_BLOWING_IN = "4"
#     AC_MODE_HEAT = "5"

#     AC_AIR_SPEED_AUTO = "1"
#     AC_AIR_SPEED_LOW = "2"
#     AC_AIR_SPEED_MEDIUM = "3"
#     AC_AIR_SPEED_HIGH = "4"

#     AC_AIR_DIRECTION_AUTO = "1"
#     AC_AIR_DIRECTION_MANUAL = "0"

#     AC_FAN_DIRECTION_UP = "1"
#     AC_FAN_DIRECTION_MIDDLE = "2"
#     AC_FAN_DIRECTION_DOWN = "3"
#     AC_FAN_DIRECTION_AUTO = "0"

#     FAN_DIRECTION_DELTA_MAPPING = {
#         "SetUpWind": 1,  # 向上调整
#         "SetDownWind": -1  # 向下调整
#     }

#     def __init__(self, state_str: str):
#         """
#         初始化空调控制器,直接从state_str加载状态
#         """
#         self.state = None
#         self.parse_air_conditioner_state(state_str)

#     def build_command(self):
#         """
#         构建要发送到空调的命令
#         """
#         if int(self.state.air_speed)>4:
#             self.state.air_speed="1"
#         return f"{self.state.power}{self.state.mode}{self.state.temperature}" \
#                f"{self.state.air_speed}{self.state.air_direction_auto}{self.state.fan_direction}"

#     def get_temperature_value(self):
#         return int(self.state.temperature)

#     def get_mode_string(self):
#         mode = self.state.mode
#         return {
#             AirConditionerController.AC_MODE_AUTO: "AUTO",
#             AirConditionerController.AC_MODE_COOL: "COOL",
#             AirConditionerController.AC_MODE_DEHUMIDIFICATION: "DEHUMIDIFICATION",
#             AirConditionerController.AC_MODE_BLOWING_IN: "FAN",
#             AirConditionerController.AC_MODE_HEAT: "HEAT",
#         }.get(mode, "UNKNOWN")

#     def get_power_string(self):
#         return "ON" if self.state.power == AirConditionerController.AC_POWER_ON else "OFF"

#     def parse_air_conditioner_state(self, state_str: str):
#         """
#         从状态字符串中提取空调状态,返回 AirConditionerState 对象.
#         :param state_str: 类似于 "power:01;tem:28;mod:01;ws:04;rtem:20" 的状态字符串
#         :return: AirConditionerState 对象
#         """
#         # 定义正则表达式来提取键值对
#         pattern = re.compile(r'(power|tem|mod|ws|rtem):(\d+)')
#         state_dict = {match.group(1): match.group(2) for match in pattern.finditer(state_str)}

#         self.state = AirConditionerState(
#             power="1" if state_dict.get("power") == "01" else "0",  # 电源状态转换为 "1" 或 "0"
#             mode=str(int(state_dict.get("mod", "2"))),  # 默认模式为 "2"(制冷)
#             temperature=state_dict.get("tem", "25"),  # 默认温度为 "25"
#             air_speed=str(int(state_dict.get("ws", "1"))),  # 默认风速为 "1"(自动风量)
#             fan_direction=str(state_dict.get("rtem", "10"))[0],
#             air_direction_auto=str(state_dict.get("rtem", "10"))[1]
#         )
#         return self

#     @staticmethod
#     def get_mode_from_string(mode_string):
#         return {
#             "AUTO": AirConditionerController.AC_MODE_AUTO,
#             "COOL": AirConditionerController.AC_MODE_COOL,
#             "DEHUMIDIFICATION": AirConditionerController.AC_MODE_DEHUMIDIFICATION,
#             "FAN": AirConditionerController.AC_MODE_BLOWING_IN,
#             "HEAT": AirConditionerController.AC_MODE_HEAT,
#         }.get(mode_string.upper(), None)

#     def set_fan_direction(self, command_name: str):
#         """
#         根据风向控制命令调整风向,command_name 包含 SetUpWind,SetDownWind,SetUpAndDownWind.
#         """
#         if command_name == "SetUpAndDownWind":
#             # 设置为自动摆风模式
#             self.state.fan_direction = AirConditionerController.AC_FAN_DIRECTION_AUTO
#         else:
#             # 获取当前的风向值,并将其转换为整数
#             current_direction = int(self.state.fan_direction)
#             delta = AirConditionerController.FAN_DIRECTION_DELTA_MAPPING.get(command_name, 0)

#             # 调整风向,并确保风向在上下(1-3)之间移动
#             new_direction = current_direction + delta
#             if new_direction < 1:
#                 new_direction = 1
#             elif new_direction > 3:
#                 new_direction = 3

#             # 更新风向状态
#             self.state.fan_direction = str(new_direction)

#         # 返回当前风向状态
#         return self.build_command()

#     def set_wind_speed(self, speed: int):
#         self.state.air_speed = str(speed)[0]
#         return self.build_command()

#     def turn_on(self):
#         self.state.power = AirConditionerController.AC_POWER_ON
#         return self.build_command()

#     def turn_off(self):
#         self.state.power = AirConditionerController.AC_POWER_OFF
#         return self.build_command()

#     def set_mode(self, mode: str):
#         self.state.mode = AirConditionerController.get_mode_from_string(mode)
#         return self.build_command()

#     def set_temperature(self, temperature: int, scale: str = "CELSIUS"):
#         # 如果是华氏度,则将其转换为摄氏度
#         if scale.upper() == "FAHRENHEIT":
#             temperature = round((temperature - 32) * 5 / 9)  # 四舍五入成整数

#         # 确保是两位整数的摄氏度,并转成字符串
#         self.state.temperature = str(int(temperature)).zfill(2)
#         return self.build_command()

#     @classmethod
#     def to_temperature(cls, temperature: int, scale: str = "CELSIUS"):
#         # 如果是华氏度,则将其转换为摄氏度
#         if scale.upper() == "FAHRENHEIT":
#             temperature = round((temperature - 32) * 5 / 9)  # 四舍五入成整数
#         # 确保是两位整数的摄氏度,并转成字符串
#         return str(int(temperature)).zfill(2)

#     @classmethod
#     def to_mode(cls, mode):
#         if mode == "COOL":
#             return Dkey.VRV_MCOLD
#         elif mode == "HEAT":
#             return Dkey.VRV_MHOT
#         else:
#             return Dkey.VRV_MAUTO

#     def adjust_temperature(self, value: int, scale: str = "CELSIUS"):
#         # 将当前温度从字符串转换为整数
#         current_temp = int(self.state.temperature)

#         # 根据 scale 来决定加减的单位
#         if scale.upper() == "FAHRENHEIT":
#             # 如果是华氏度,将调整的值转换为摄氏度再进行加减
#             value = int(value * 5 / 9)

#         # 调整后的温度
#         new_temp = current_temp + value

#         # 确保是两位整数的摄氏度,并转成字符串
#         self.state.temperature = str(int(new_temp)).zfill(2)

#         return self.build_command()

#     def adjust_temperature1(self, value: int, scale: str = "CELSIUS"):
#         self.adjust_temperature(value, scale)
#         return self.state.temperature


# def get_closest_color_name(r, g, b):
#     """
#     根据RGB值获取最接近的颜色名称
#     """
#     min_diff = None
#     closest_color = None
#     closest_color_name = None

#     # 遍历支持的颜色并找到最接近的颜色
#     for color_name, color_info in SUPPORTED_COLORS.items():
#         rc, gc, bc = color_info["rgb"]
#         diff = (r - rc) ** 2 + (g - gc) ** 2 + (b - bc) ** 2
#         if min_diff is None or diff < min_diff:
#             min_diff = diff
#             closest_color = color_info["name"]
#             closest_color_name = color_name

#     return closest_color_name, closest_color


# def get_closest_color_from_hsb(color: dict):
#     r, g, b = colorsys.hsv_to_rgb(color.get("hue"), color.get("saturation"), color.get("brightness"))
#     return get_closest_color_name(r, g, b)[0]


# def get_hsb_from_color_name(color_name: str):
#     r, g, b = SUPPORTED_COLORS.get(color_name).get("rgb")
#     hue, saturation, brightness = colorsys.rgb_to_hsv(r, g, b)

#     # 将 hue 转换回 0-360 范围
#     hue *= 360

#     return {
#         "value": {
#             "hue": round(hue, 1),  # 保留一位小数
#             "saturation": round(saturation, 4),  # 保留四位小数
#             "brightness": round(brightness, 4)  # 保留四位小数
#         }
#     }


# def hsb_to_rgb_hex(hsb: dict) -> str:
#     # 获取 HSB 值
#     hue = hsb.get("hue") / 360  # hue 范围需要在 0-1 之间
#     saturation = hsb.get("saturation")
#     brightness = hsb.get("brightness")

#     # 使用 colorsys.hsv_to_rgb 将 HSB 转换为 RGB,结果为 0-1 之间的值
#     r, g, b = colorsys.hsv_to_rgb(hue, saturation, brightness)

#     # 将 RGB 转换为 0-255 范围的整数
#     r = int(r * 255)
#     g = int(g * 255)
#     b = int(b * 255)

#     # 转换为十六进制字符串,不带 #
#     return f"{r:02x}{g:02x}{b:02x}"


# def extract_percentage(text):
#     match = re.search(r'(\d+)%', text)  # 匹配包含数字和百分号的部分
#     if match:
#         return int(match.group(1))  # 提取匹配到的数字部分并转换为整数
#     return 0


# class DimmableLight:
#     MODE_RGB = "RGB模式"
#     MODE_BRIGHTNESS_COLOR_TEMP = "色温和亮度模式"

#     def __init__(self, raw_data: str):
#         self.raw_data = raw_data
#         self.power_state = None
#         self.mode = None
#         self.brightness = None
#         self.color_temp = None
#         self.color_temp_100 = None
#         self.rgb = None
#         self.color_name = None
#         self.color = None
#         self.parse_state()

#     def parse_state(self):
#         """
#         解析 RGBCW 字符串,提取灯的状态,模式,亮度,色温和RGB值.
#         :return: dict 包含灯的状态信息
#         """
#         if not self.raw_data.startswith("RGBCW:"):
#             raise ValueError("无效的 RGBCW 数据")

#         # 去掉前缀 "RGBCW:"
#         data = self.raw_data[6:]

#         # 提取各个字段
#         power_hex = data[:2]  # 04 或 03
#         mode_hex = data[2:4]  # 04(RGB模式)或 03(色温和亮度模式)
#         brightness_hex = data[4:6]  # 64(亮度)
#         color_temp_hex = data[6:8]  # 63(色温)
#         r_hex = data[8:10]  # 红色
#         g_hex = data[10:12]  # 绿色
#         b_hex = data[12:14]  # 蓝色

#         # 解析电源状态
#         self.power_state = "on" if power_hex == "03" else "off"

#         # 解析模式
#         if mode_hex == "03":
#             self.mode = DimmableLight.MODE_BRIGHTNESS_COLOR_TEMP
#         elif mode_hex == "04":
#             self.mode = DimmableLight.MODE_RGB
#         else:
#             self.mode = "未知模式"

#         # 解析亮度和色温(16进制转10进制)
#         self.brightness = int(brightness_hex, 16)

#         self.color_temp_100 = int(color_temp_hex, 16)

#         min_temp = 2700
#         max_temp = 10000

#         # 将 0-100 的 color_temp_100 映射到 2700-10000
#         self.color_temp = int(min_temp + (max_temp - min_temp) * (self.color_temp_100 / 100))

#         # 解析RGB值
#         self.rgb = {
#             "R": round(int(r_hex, 16) / 100 * 255),
#             "G": round(int(g_hex, 16) / 100 * 255),
#             "B": round(int(b_hex, 16) / 100 * 255)
#         }
#         hue, saturation, brightness = colorsys.rgb_to_hsv(self.rgb["R"], self.rgb["G"], self.rgb["B"])

#         # 将 hue 转换回 0-360 范围
#         hue *= 360

#         self.color = {
#             "hue": round(hue, 1),  # 保留一位小数
#             "saturation": round(saturation, 4),  # 保留四位小数
#             "brightness": round(brightness, 4)  # 保留四位小数
#         }

#         # 将RGB值转换为最近的颜色名称并添加中文描述
#         self.color_name, _ = get_closest_color_name(self.rgb["R"], self.rgb["G"], self.rgb["B"])
