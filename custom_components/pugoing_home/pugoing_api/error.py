from typing import Optional


class PuGoingAPIError(Exception):
    """蒲公英 API 基础异常类"""

    def __init__(self, message: str, error_code: Optional[str] = None):
        super().__init__(message)
        self.error_code = error_code


class DeviceOfflineError(PuGoingAPIError):
    """设备离线异常"""

    def __init__(self, message: str = "Device is offline"):
        super().__init__(message, error_code="IOT_DEVICE_OFFLINE")


class PuGoingInvalidResponseError(PuGoingAPIError):
    """向蒲公英API请求数据时返回的数据异常"""

    def __init__(self, message: str = "Device is offline"):
        super().__init__(message, error_code="IOT_DEVICE_OFFLINE")



class InvalidParamsError(PuGoingAPIError):
    """请求参数无效异常"""

    def __init__(self, message: str = "Invalid parameters"):
        super().__init__(message, error_code="INVALIDATE_PARAMS")


class AccessTokenInvalidError(PuGoingAPIError):
    """Access token 无效异常"""

    def __init__(self, message: str = "Access token is invalid"):
        super().__init__(message, error_code="ACCESS_TOKEN_INVALIDATE")


class NoPermissionError(PuGoingAPIError):
    """没有权限访问该主机异常"""

    def __init__(self, message: str = "You do not have permission to access this host"):
        super().__init__(message, error_code="NO_PERMISSION")
