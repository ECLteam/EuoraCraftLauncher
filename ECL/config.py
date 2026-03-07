import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, List
from .logger import get_logger
from . import __version__ , __version_type__

logger = get_logger("config")

class ConfigManager:
    # 配置管理器 - 处理配置文件的读写
    
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
                "title": "EuoraCraft Launcher",
                "background": {
                    "type": "default",
                    "path": "",
                    "opacity": 0.8,
                    "blur": 0
                }
            },
            "game": {
                "minecraft_paths": ["./.minecraft"],
                "java_auto_select": True,
                "java_path": "",
                "memory_size": 4096
            },
            "download": {
                "mirror_source": "official",
                "download_threads": 4
            },
            "theme": {
                "mode": "system",
                "primary_color": "#87CEEB",
                "blur_amount": 6
            }
        }
    ]

    def __init__(self, config_path: str = "setting.json"):
        # 直接使用 Path 对象，不再担心递归问题
        self._config_path = Path(config_path).resolve()
        self._env_path = self._find_env_file()
        self.config: List[Dict[str, Any]] = []
        logger.debug("ConfigManager初始化完成，配置文件路径: %s", str(self._config_path))
    
    @property
    def config_path(self) -> Path:
        return self._config_path
    
    @property
    def env_path(self) -> Optional[Path]:
        return self._env_path

    def _find_env_file(self) -> Optional[Path]:
        # 找 .env 文件
        try:
            for env_name in [".env.dev", ".env"]:
                path = Path(env_name).resolve()
                if path.exists():
                    logger.debug("找到环境配置文件: %s", str(path))
                    return path
            return None
        except Exception as e:
            logger.error("查找环境配置文件失败: %s", e)
            return None

    def _load_env(self) -> Dict[str, str]:
        # 读取 .env 文件内容
        env_vars = {}
        env_path = self.env_path
        
        if env_path and env_path.exists():
            logger.info("检测到环境配置文件 %s，正在读取...", str(env_path))
            try:
                with open(env_path, "r", encoding="utf-8") as f:
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
        # 用环境变量覆盖配置项
        env_vars = self._load_env()
        if not env_vars or not config:
            return

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
        # 加载配置
        if not self.config_path.exists():
            logger.warning("配置文件不存在，正在生成默认配置...")
            self.config = self.DEFAULT_CONFIG.copy()
            self.save(self.config)
            logger.info("默认配置文件已生成：%s", str(self.config_path))
        else:
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.config = json.load(f)
                logger.info("配置文件读取完成")
            except Exception as e:
                logger.error("读取配置文件失败: %s", e)
                raise

        self._apply_env_overrides(self.config)
        return self.config

    def save(self, config: List[Dict[str, Any]]) -> None:
        # 保存配置
        try:
            safe_config = self._make_config_safe_for_json(config)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(safe_config, f, ensure_ascii=False, indent=2)
            logger.debug("配置已保存到: %s", str(self.config_path))
        except Exception as e:
            logger.error("保存配置文件失败: %s", e)
            raise
    
    def _make_config_safe_for_json(self, obj: Any) -> Any:
        # 处理 Path 对象等，确保能序列化为 JSON
        if isinstance(obj, Path):
            return str(obj)
        elif isinstance(obj, dict):
            return {key: self._make_config_safe_for_json(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._make_config_safe_for_json(item) for item in obj]
        return obj

    def validate(self) -> Optional[str]:
        # 检查配置是否正确
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

    # 配置获取方法
    def get_launcher_config(self) -> Dict[str, Any]:
        return self.config[0].get("launcher", {}) if self.config else {}

    def get_ui_config(self) -> Dict[str, Any]:
        return self.config[0].get("ui", {}) if self.config else {}

    def get_background_config(self) -> Dict[str, Any]:
        ui_config = self.get_ui_config()
        return ui_config.get("background", {
            "type": "default",
            "path": "",
            "opacity": 0.8,
            "blur": 0
        })

    def update_background_config(self, background_config: Dict[str, Any]) -> None:
        if not self.config:
            self.config = self.DEFAULT_CONFIG.copy()
        
        if "ui" not in self.config[0]:
            self.config[0]["ui"] = {}
        
        self.config[0]["ui"]["background"] = background_config
        self.save(self.config)
        logger.info("背景图配置已更新: %s", background_config.get("type", "unknown"))

    def get_game_config(self) -> Dict[str, Any]:
        game_config = self.config[0].get("game", {
            "minecraft_paths": ["./.minecraft"],
            "java_auto_select": True,
            "java_path": "",
            "memory_size": 4096
        })
        
        # 保持向后兼容性
        if "minecraft_path" in game_config and "minecraft_paths" not in game_config:
            game_config["minecraft_paths"] = [game_config["minecraft_path"]]
            del game_config["minecraft_path"]
        elif "minecraft_paths" not in game_config:
            game_config["minecraft_paths"] = ["./.minecraft"]
        
        return game_config

    def update_game_config(self, game_config: Dict[str, Any]) -> None:
        if not self.config:
            self.config = self.DEFAULT_CONFIG.copy()
        
        # 合并配置而不是完全替换
        current_game_config = self.config[0].get("game", {})
        updated_config = {**current_game_config, **game_config}
        
        # 确保路径是列表格式
        if "minecraft_path" in updated_config and isinstance(updated_config["minecraft_path"], str):
            updated_config["minecraft_paths"] = [updated_config["minecraft_path"]]
            del updated_config["minecraft_path"]
        elif "minecraft_paths" not in updated_config:
            updated_config["minecraft_paths"] = ["./.minecraft"]
        
        self.config[0]["game"] = updated_config
        self.save(self.config)
        logger.info("游戏配置已更新")

    def get_theme_config(self) -> Dict[str, Any]:
        return self.config[0].get("theme", {
            "mode": "system",
            "primary_color": "#87CEEB",
            "blur_amount": 6
        })

    def update_theme_config(self, theme_config: Dict[str, Any]) -> None:
        if not self.config:
            self.config = self.DEFAULT_CONFIG.copy()
        
        # 只保留必要的主题配置项
        filtered_config = {
            "mode": theme_config.get("mode", "system"),
            "primary_color": theme_config.get("primary_color", "#87CEEB"),
            "blur_amount": theme_config.get("blur_amount", 6)
        }
        
        self.config[0]["theme"] = filtered_config
        self.save(self.config)
        logger.info("主题配置已更新")

    def get_download_config(self) -> Dict[str, Any]:
        return self.config[0].get("download", {
            "mirror_source": "official",
            "download_threads": 4
        })

    def update_download_config(self, download_config: Dict[str, Any]) -> None:
        if not self.config:
            self.config = self.DEFAULT_CONFIG.copy()
        
        self.config[0]["download"] = download_config
        self.save(self.config)
        logger.info("下载配置已更新")

    def __repr__(self) -> str:
        return f"ConfigManager(config_path='{str(self.config_path)}')"