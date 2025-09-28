import logging
import sys


class LoggerUtility:
    def __init__(self, name: str, log_level=logging.INFO):
        # 初始化 logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(log_level)

        # 处理日志输出
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter("%(levelname)s - %(message)s")  # 不带时间戳
        handler.setFormatter(formatter)
        handler.setLevel(log_level)  # 设置日志的打印级别
        self.logger.addHandler(handler)

        # 防止重复添加 handler
        self.logger.propagate = False

    # 日志方法,拼接传入的 *args
    def info(self, *args, **kwargs):
        message = " ".join(str(arg) for arg in args)  # 将 *args 转换为字符串并拼接
        self.logger.info(message, **kwargs)

    def debug(self, *args, **kwargs):
        message = " ".join(str(arg) for arg in args)  # 将 *args 转换为字符串并拼接
        self.logger.debug(message, **kwargs)

    def error(self, *args, **kwargs):
        message = " ".join(str(arg) for arg in args)  # 将 *args 转换为字符串并拼接
        self.logger.error(message, **kwargs)

    def set_level(self, log_level: int):
        """动态设置日志级别"""
        self.logger.setLevel(log_level)
        for handler in self.logger.handlers:
            handler.setLevel(log_level)
