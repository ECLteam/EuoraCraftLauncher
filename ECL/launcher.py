import sys
import os
import logging
import colorama
from .logger import get_logger, LoggerManager
from .config import ConfigManager
from .ui.ui import run_ui
from .game.java import get_java_list

logger = get_logger("launcher")

class EuoraCraftLauncher:
    # 启动器主类
    
    def __init__(self):
        self.config_manager = ConfigManager()
        self.config = None
        self.debug_mode = False

    def _init_platform(self):
        logger.info("当前工作系统：%s", sys.platform)
        match sys.platform:
            case "win32":
                colorama.init()
                logger.info("已初始化 colorama")
            case "linux":
                logger.info("未支持Linux")
                sys.exit(0)
            case "darwin":
                logger.info("未支持macOS")
                sys.exit(0)
            case _:
                logger.warning("未知平台：%s", sys.platform)
                raise RuntimeError(f"不支持的操作系统平台: {sys.platform}")

    def _log_environment_info(self):
        logger.info("当前工作目录：%s", os.getcwd())
        logger.info("执行文件路径：%s", sys.executable)
        logger.info("程序目录：%s", os.path.dirname(sys.executable))

    def _handle_version_info(self):
        launcher_cfg = self.config_manager.get_launcher_config()
        version = launcher_cfg.get("version", "未知")
        version_type = launcher_cfg.get("version_type", "unknown")
        
        logger.info("启动器版本: v%s", version)
        logger.info("启动器版本类型: %s", version_type)
        
        match version_type:
            case "dev":
                logger.warning("当前为开发版本，可能存在不稳定因素，请谨慎使用！")
            case "beta":
                logger.info("当前为测试版本，可能存在部分问题，请注意反馈！")
            case "release":
                logger.info("当前为正式版本，祝您使用愉快！")
            case _:
                logger.warning("未知的版本类型：%s, 请移除配置文件并重启启动器", version_type)

    def initialize(self):
        logger.info("EuoraCraft Launcher 启动中...")
        try:
            self._init_platform()
            self._log_environment_info()
            
            # 加载并校验配置
            self.config = self.config_manager.load()
            error = self.config_manager.validate()
            if error:
                logger.error("配置校验失败: %s", error)
                sys.exit(1)
            
            self._handle_version_info()
            
            # 设置调试模式
            launcher_cfg = self.config_manager.get_launcher_config()
            self.debug_mode = bool(launcher_cfg.get("debug", False))
            logger.info("调试模式: %s", self.debug_mode)
            
            if self.debug_mode:
                LoggerManager().set_level(logging.DEBUG)
                logger.debug("调试模式已启用")
                import json
                logger.debug("完整配置内容：\n%s", json.dumps(self.config, ensure_ascii=False, indent=2))
            
            # 获取 Java 列表
            self.java_list = get_java_list()
            if not self.java_list:
                logger.warning("未找到任何 Java 安装")
            logger.debug("Java 列表: %s", self.java_list)
                
        except Exception as e:
            logger.error("初始化启动器时出错: %s", e)
            sys.exit(1)

    def run(self):
        self.initialize()
        run_ui(self.config, self.debug_mode, self.config_manager)