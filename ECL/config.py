import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, List
from .logger import get_logger
from . import __version__ , __version_type__

logger = get_logger("config")

class ConfigManager:
    """配置管理器，负责配置的加载、保存、校验以及环境变量覆盖"""
    
    DEFAULT_CONFIG = [
        {
            "launcher": {
                "version": __version__,
                "version_type": __version_type__,
                "debug": False
            },
            "ui": {
                "width": 900,
                "height": 600,
                "title": "EuoraCraft Launcher"
            }
        }
    ]

    def __init__(self, config_path: str = "setting.json"):
        self.config_path = Path(config_path)
        # 优先检测 .env.dev，其次是 .env
        self.env_path = self._find_env_file()
        self.config: List[Dict[str, Any]] = []

    def _find_env_file(self) -> Optional[Path]:
        """查找可用的环境配置文件"""
        for env_name in [".env.dev", ".env"]:
            path = Path(env_name)
            if path.exists():
                return path
        return None

    def _load_env(self) -> Dict[str, str]:
        """读取环境配置文件并返回字典"""
        env_vars = {}
        if self.env_path and self.env_path.exists():
            logger.info("检测到环境配置文件 %s，正在读取...", self.env_path)
            try:
                with open(self.env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            key, value = line.split("=", 1)
                            env_vars[key.strip()] = value.strip()
            except Exception as e:
                logger.error("读取 .env 文件失败: %s", e)
        return env_vars

    def _apply_env_overrides(self, config: List[Dict[str, Any]]):
        """使用环境变量覆盖配置"""
        env_vars = self._load_env()
        if not env_vars or not config:
            return

        # 映射规则: ECL_SECTION_KEY -> config[0][section][key]
        # 例如: ECL_LAUNCHER_DEBUG=false -> config[0]["launcher"]["debug"] = False
        for env_key, env_val in env_vars.items():
            if not env_key.startswith("ECL_"):
                continue
            
            parts = env_key.split("_")
            if len(parts) < 3:
                continue
            
            section = parts[1].lower()
            key = "_".join(parts[2:]).lower()
            
            if section in config[0] and key in config[0][section]:
                original_val = config[0][section][key]
                # 类型转换
                if isinstance(original_val, bool):
                    new_val = env_val.lower() in ("true", "1", "yes")
                elif isinstance(original_val, int):
                    try:
                        new_val = int(env_val)
                    except ValueError:
                        continue
                else:
                    new_val = env_val
                
                config[0][section][key] = new_val
                logger.info("环境变量覆盖配置: [%s][%s] -> %s", section, key, new_val)

    def load(self) -> List[Dict[str, Any]]:
        """加载配置文件，并应用环境变量覆盖"""
        if not self.config_path.exists():
            logger.warning("配置文件不存在，正在生成默认配置...")
            self.config = self.DEFAULT_CONFIG
            self.save(self.config)
            logger.info("默认配置文件已生成：%s", self.config_path)
        else:
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
                logger.info("配置文件读取完成")
            except Exception as e:
                logger.error("读取配置文件失败: %s", e)
                raise

        # 应用 .env 覆盖
        self._apply_env_overrides(self.config)
        
        return self.config

    def save(self, config: List[Dict[str, Any]]) -> None:
        """保存配置到文件"""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error("保存配置文件失败: %s", e)
            raise

    def validate(self) -> Optional[str]:
        """校验配置有效性"""
        if not self.config or not isinstance(self.config, list) or len(self.config) == 0:
            return "配置结构错误：配置应为非空列表"

        try:
            launcher_cfg = self.config[0].get("launcher", {})
            version = launcher_cfg.get("version")
            if not version or not re.match(r"^\d+\.\d+\.\d+$", version):
                return f"版本号格式错误: '{version}'，应为数字.数字.数字（如 1.0.0）"
        except Exception as e:
            return f"配置校验异常: {str(e)}"
        
        return None

    def get_launcher_config(self) -> Dict[str, Any]:
        return self.config[0].get("launcher", {}) if self.config else {}

    def get_ui_config(self) -> Dict[str, Any]:
        return self.config[0].get("ui", {}) if self.config else {}