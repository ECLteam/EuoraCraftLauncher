import logging
import logging.handlers
from pathlib import Path
from typing import Optional

class ColoredFormatter(logging.Formatter):
    """彩色日志格式器"""
    
    # ANSI 颜色代码
    COLORS = {
        'DEBUG': '\033[36m',    # 青色
        'INFO': '\033[32m',     # 绿色
        'WARNING': '\033[33m',  # 黄色
        'ERROR': '\033[31m',    # 红色
        'CRITICAL': '\033[35m', # 紫色
        'RESET': '\033[0m',     # 重置
        'BOLD': '\033[1m',      # 粗体
    }
    
    def format(self, record: logging.LogRecord) -> str:
        # 复制 record 避免修改原始数据
        record = logging.makeLogRecord(record.__dict__.copy())
        
        # 获取颜色
        levelname = record.levelname
        if levelname in self.COLORS:
            # 为级别名称和消息添加颜色
            record.levelname = f"{self.COLORS[levelname]}{self.COLORS['BOLD']}{levelname:8s}{self.COLORS['RESET']}"
            record.msg = f"{self.COLORS[levelname]}{record.msg}{self.COLORS['RESET']}"
        
        return super().format(record)


class LoggerManager:
    """全局日志管理器"""
    
    _instance: Optional['LoggerManager'] = None
    _initialized: bool = False
    
    def __new__(cls) -> 'LoggerManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, colored: bool = True):
        if LoggerManager._initialized:
            return
        
        self._root_logger = logging.getLogger("EuoraCraft-Launcher")
        self._root_logger.setLevel(logging.DEBUG)
        
        # 设置处理器和格式
        self._setup_handlers(colored)
        
        LoggerManager._initialized = True
    
    def _setup_handlers(self, colored: bool) -> None:
        """配置日志处理器"""
        if self._root_logger.handlers:
            return
        
        # 创建日志目录
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        
        # 统一格式器
        base_formatter = logging.Formatter(
            fmt='%(asctime)s [%(levelname)s] [%(name)s] [%(filename)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 控制台处理器（带颜色）
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # 根据参数选择是否启用颜色
        if colored:
            # 使用彩色格式器
            console_formatter = ColoredFormatter(
                fmt='%(asctime)s %(levelname)s [%(name)s] [%(filename)s:%(lineno)d] - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        else:
            # 使用普通格式器
            console_formatter = base_formatter
        
        console_handler.setFormatter(console_formatter)
        self._console_handler = console_handler
        
        # 文件处理器（无颜色）
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "EuoraCraft-Launcher.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(base_formatter)
        
        # 错误日志处理器
        error_handler = logging.handlers.RotatingFileHandler(
            log_dir / "error.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(base_formatter)
        
        # 添加所有处理器
        self._root_logger.addHandler(console_handler)
        self._root_logger.addHandler(file_handler)
        self._root_logger.addHandler(error_handler)
    
    def get_logger(self, name: Optional[str] = None) -> logging.Logger:
        """获取日志记录器"""
        if name:
            return self._root_logger.getChild(name)
        return self._root_logger
    
    def set_level(self, level: int) -> None:
        """动态修改日志级别"""
        self._root_logger.setLevel(level)
        self._console_handler.setLevel(level)

# 全局快捷函数
def get_logger(name: Optional[str] = None) -> logging.Logger:
    """快速获取日志记录器"""
    manager = LoggerManager()
    return manager.get_logger(name)