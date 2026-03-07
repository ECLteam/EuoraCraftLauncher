import os
import sys
import webview
import base64
import requests
import json
from pathlib import Path
from typing import Dict, Any, List
from tkinter import filedialog, Tk
from ..logger import get_logger
from ..game import java
from ..Core.ECLauncherCore import ECLauncherCore

logger = get_logger("ui")

def rp(rel):
    # 获取资源文件的绝对路径
    return os.path.join(getattr(sys, '_MEIPASS', os.path.abspath('.')), rel)

def make_json_safe(obj: Any) -> Any:
    # 处理 Path、set 等类型，确保可序列化为 JSON
    if isinstance(obj, Path):
        return str(obj)
    elif isinstance(obj, (set, tuple)):
        return [make_json_safe(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: make_json_safe(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [make_json_safe(item) for item in obj]
    elif isinstance(obj, (int, float, str, bool, type(None))):
        return obj
    else:
        # 其他类型转为字符串
        return str(obj)

class Api:
    # 前端调用的 JS API
    
    def __init__(self, config_manager):
        self._config_manager = config_manager
        # 确保配置已加载
        self._ensure_config_loaded()
    
    def _ensure_config_loaded(self):
        try:
            if not self._config_manager.config:
                logger.info("配置未加载，自动调用load()")
                self._config_manager.load()
        except Exception as e:
            logger.error("加载配置失败: %s", e)
    
    def __dir__(self):
        return [
            'minimize_window',
            'close_window',
            'get_window_position',
            'set_window_position',
            'get_launcher_config',
            'get_background_config',
            'get_background_image',
            'update_background_config',
            'update_background_image',
            'load_image_from_url',
            'load_image_from_local',
            'select_local_image',
            'get_game_config',
            'update_game_config',
            'get_java_list',
            'get_theme_config',
            'update_theme_config',
            'get_download_config',
            'update_download_config',
            'select_directory',
            'scan_versions_in_path',
            'get_minecraft_versions',
            'get_fabric_versions',
            'install_version',
            'ping'
        ]

    def ping(self) -> Dict[str, Any]:
        return {
            "success": True,
            "data": {"status": "ok", "message": "API连接正常"},
            "message": "Pong"
        }

    def minimize_window(self) -> Dict[str, Any]:
        try:
            if webview.windows:
                webview.windows[0].minimize()
                return {"success": True, "message": "窗口已最小化"}
            return {"success": False, "message": "窗口未找到"}
        except Exception as e:
            logger.error("最小化窗口失败: %s", e)
            return {"success": False, "message": str(e)}
        
    def close_window(self) -> Dict[str, Any]:
        try:
            if webview.windows:
                webview.windows[0].destroy()
                return {"success": True, "message": "窗口已关闭"}
            return {"success": False, "message": "窗口未找到"}
        except Exception as e:
            logger.error("关闭窗口失败: %s", e)
            return {"success": False, "message": str(e)}

    def get_window_position(self) -> Dict[str, Any]:
        try:
            if webview.windows:
                window = webview.windows[0]
                x, y = window.x, window.y
                width, height = window.width, window.height
                return {
                    "success": True,
                    "data": {
                        "x": x,
                        "y": y,
                        "width": width,
                        "height": height
                    },
                    "message": "获取窗口位置成功"
                }
            return {"success": False, "message": "窗口未找到", "data": None}
        except Exception as e:
            logger.error("获取窗口位置失败: %s", e)
            return {"success": False, "message": str(e), "data": None}

    def set_window_position(self, x: int, y: int) -> Dict[str, Any]:
        try:
            if webview.windows:
                window = webview.windows[0]
                window.move(x, y)
                return {
                    "success": True,
                    "message": f"窗口位置已设置为 ({x}, {y})"
                }
            return {"success": False, "message": "窗口未找到"}
        except Exception as e:
            logger.error("设置窗口位置失败: %s", e)
            return {"success": False, "message": str(e)}

    def get_launcher_config(self) -> Dict[str, Any]:
        try:
            self._ensure_config_loaded()
            config = self._config_manager.get_launcher_config()
            safe_config = make_json_safe(config)
            logger.debug("返回启动器配置: %s", safe_config)
            return {
                "success": True,
                "data": safe_config,
                "message": "获取成功"
            }
        except Exception as e:
            logger.error("获取启动器配置失败: %s", e)
            return {"success": False, "message": str(e), "data": None}

    def get_background_config(self) -> Dict[str, Any]:
        try:
            self._ensure_config_loaded()
            config = self._config_manager.get_background_config()
            # 确保数据可JSON序列化
            safe_config = make_json_safe(config)
            logger.debug("返回背景图配置: %s", safe_config)
            return {
                "success": True,
                "data": safe_config,
                "message": "获取成功"
            }
        except Exception as e:
            logger.error("获取背景图配置失败: %s", e)
            return {"success": False, "message": str(e), "data": None}

    def get_background_image(self) -> Dict[str, Any]:
        try:
            self._ensure_config_loaded()
            config = self._config_manager.get_background_config()
            path_str = config.get("path", "")
            
            if not path_str:
                return {"success": False, "message": "未设置背景图", "data": None}
                
            path = Path(path_str)
            if not path.exists():
                return {"success": False, "message": f"背景图文件不存在: {path_str}", "data": None}
                
            with open(path, 'rb') as f:
                image_data = f.read()
            
            mime_map = {
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg'
            }
            mime_type = mime_map.get(path.suffix.lower(), 'image/jpeg')
            base64_data = base64.b64encode(image_data).decode('utf-8')
            
            return {
                "success": True,
                "data": {
                    "base64": f"data:{mime_type};base64,{base64_data}",
                    "path": str(path),
                    "type": config.get("type", "local")
                },
                "message": "获取成功"
            }
        except Exception as e:
            logger.error("获取背景图数据失败: %s", e)
            return {"success": False, "message": str(e), "data": None}

    def update_background_config(self, background_config: Dict[str, Any]) -> Dict[str, Any]:
        try:
            self._ensure_config_loaded()
            
            # 如果是本地图片，读取并转为base64存储（供前端立即显示）
            if background_config.get("type") == "local" and background_config.get("path"):
                path = background_config["path"]
                if os.path.exists(path):
                    with open(path, "rb") as f:
                        image_data = f.read()
                    background_config["image_base64"] = base64.b64encode(image_data).decode("utf-8")
            
            self._config_manager.update_background_config(background_config)
            logger.info("背景图配置已更新: %s", background_config.get("type"))
            
            # 同步模糊值到主题配置
            if "blur" in background_config:
                # 获取当前主题配置
                current_theme = self._config_manager.get_theme_config()
                # 更新模糊值
                current_theme["blur_amount"] = background_config["blur"]
                # 保存主题配置
                self._config_manager.update_theme_config(current_theme)
                logger.info("同步背景模糊值到主题配置: %s", background_config["blur"])
            
            return {"success": True, "message": "背景图更新成功"}
        except Exception as e:
            logger.error("更新背景图配置失败: %s", e)
            return {"success": False, "message": str(e)}

    def update_background_image(self, image_type: str, image_path: str) -> Dict[str, Any]:
        return self.update_background_config({
            "type": image_type,
            "path": image_path,
            "opacity": 0.8,
            "blur": 0
        })

    def load_image_from_url(self, url: str) -> Dict[str, Any]:
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            content_type = response.headers.get('content-type', '')
            if not content_type.startswith('image/'):
                return {"success": False, "message": "URL不是图片类型", "data": None}
            
            ext = content_type.split('/')[-1] if '/' in content_type else 'jpg'
            bg_dir = Path("backgrounds")
            bg_dir.mkdir(exist_ok=True)
            
            file_name = f"bg_{hash(url) % 10000}.{ext}"
            file_path = bg_dir / file_name
            
            with open(file_path, 'wb') as f:
                f.write(response.content)
            
            abs_path = str(file_path.absolute())
            logger.info("网络图片已保存: %s", abs_path)
            
            return {
                "success": True,
                "data": {"path": abs_path},
                "message": "图片下载成功"
            }
        except Exception as e:
            logger.error("加载网络图片失败: %s", e)
            return {"success": False, "message": str(e), "data": None}

    def load_image_from_local(self, file_path: str) -> Dict[str, Any]:
        try:
            if not isinstance(file_path, str):
                file_path = str(file_path)
            
            path_obj = Path(file_path)
            if not path_obj.exists():
                return {"success": False, "message": f"文件不存在: {file_path}", "data": None}
            
            valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
            if path_obj.suffix.lower() not in valid_extensions:
                return {"success": False, "message": f"不支持的图片格式: {path_obj.suffix}", "data": None}
            
            return {
                "success": True,
                "data": {"path": str(path_obj.absolute())},
                "message": "图片验证成功"
            }
        except Exception as e:
            logger.error("验证本地图片失败: %s", e)
            return {"success": False, "message": str(e), "data": None}

    def select_local_image(self) -> Dict[str, Any]:
        try:
            window = webview.windows[0] if webview.windows else None
            if not window:
                return {"success": False, "message": "窗口未找到", "data": None}
            
            result = window.create_file_dialog(
                dialog_type=webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=('Image files (*.jpg;*.jpeg;*.png;*.gif;*.webp)', 'All files (*.*)')
            )
            
            if result and isinstance(result, (list, tuple)) and len(result) > 0:
                return self.load_image_from_local(str(result[0]))
            elif result and isinstance(result, str):
                return self.load_image_from_local(result)
            else:
                return {"success": False, "message": "用户取消选择", "data": None}
        except Exception as e:
            logger.error("选择本地图片失败: %s", e)
            return {"success": False, "message": str(e), "data": None}

    def get_game_config(self) -> Dict[str, Any]:
        try:
            self._ensure_config_loaded()
            config = self._config_manager.get_game_config()
            
            # 转换minecraft_path为minecraft_paths（前端期望数组）
            if "minecraft_path" in config and isinstance(config["minecraft_path"], str):
                config["minecraft_paths"] = [config["minecraft_path"]]
            elif "minecraft_paths" not in config:
                config["minecraft_paths"] = ["./.minecraft"]
            
            # 确保java_auto_select字段存在
            if "java_auto_select" not in config:
                config["java_auto_select"] = True
            
            # 确保java_path字段存在
            if "java_path" not in config:
                config["java_path"] = ""
            
            # 确保memory_size字段存在
            if "memory_size" not in config:
                config["memory_size"] = 2048
            
            safe_config = make_json_safe(config)
            logger.debug("返回游戏配置: %s", safe_config)
            return {
                "success": True,
                "data": safe_config,
                "message": "获取成功"
            }
        except Exception as e:
            logger.error("获取游戏配置失败: %s", e)
            return {"success": False, "message": str(e), "data": None}

    def update_game_config(self, game_config: Dict[str, Any]) -> Dict[str, Any]:
        try:
            self._ensure_config_loaded()
            
            # 转换minecraft_paths为minecraft_path（取第一个路径）
            if "minecraft_paths" in game_config and isinstance(game_config["minecraft_paths"], list):
                if len(game_config["minecraft_paths"]) > 0:
                    game_config["minecraft_path"] = game_config["minecraft_paths"][0]
                else:
                    game_config["minecraft_path"] = "./.minecraft"
                # 移除minecraft_paths字段，避免后端混淆
                del game_config["minecraft_paths"]
            
            self._config_manager.update_game_config(game_config)
            return {"success": True, "message": "游戏配置更新成功"}
        except Exception as e:
            logger.error("更新游戏配置失败: %s", e)
            return {"success": False, "message": str(e)}

    def get_java_list(self) -> Dict[str, Any]:
        try:
            # 调用java模块的get_java_list函数
            java_list = java.get_java_list()
            
            if java_list is False or not java_list:
                return {
                    "success": True,
                    "data": [],
                    "message": "未找到Java安装"
                }
            
            # 将JavaInfo对象转换为字典
            java_dicts = []
            for java_info in java_list:
                java_dict = {
                    "path": java_info.path,
                    "version": java_info.version,
                    "major_version": java_info.major_version,
                    "java_type": java_info.java_type,
                    "arch": java_info.arch,
                    "sources": java_info.sources
                }
                java_dicts.append(java_dict)
            
            return {
                "success": True,
                "data": java_dicts,
                "message": f"找到 {len(java_dicts)} 个Java安装"
            }
        except Exception as e:
            logger.error("获取Java列表失败: %s", e)
            return {"success": False, "message": str(e), "data": None}

    def get_theme_config(self) -> Dict[str, Any]:
        try:
            self._ensure_config_loaded()
            config = self._config_manager.get_theme_config()
            safe_config = make_json_safe(config)
            logger.debug("返回主题配置: %s", safe_config)
            return {
                "success": True,
                "data": safe_config,
                "message": "获取成功"
            }
        except Exception as e:
            logger.error("获取主题配置失败: %s", e)
            return {"success": False, "message": str(e), "data": None}

    def update_theme_config(self, theme_config: Dict[str, Any]) -> Dict[str, Any]:
        try:
            self._ensure_config_loaded()
            self._config_manager.update_theme_config(theme_config)
            return {"success": True, "message": "主题配置更新成功"}
        except Exception as e:
            logger.error("更新主题配置失败: %s", e)
            return {"success": False, "message": str(e)}

    def get_download_config(self) -> Dict[str, Any]:
        try:
            self._ensure_config_loaded()
            config = self._config_manager.get_download_config()
            safe_config = make_json_safe(config)
            logger.debug("返回下载配置: %s", safe_config)
            return {
                "success": True,
                "data": safe_config,
                "message": "获取成功"
            }
        except Exception as e:
            logger.error("获取下载配置失败: %s", e)
            return {"success": False, "message": str(e), "data": None}

    def update_download_config(self, download_config: Dict[str, Any]) -> Dict[str, Any]:
        try:
            self._ensure_config_loaded()
            self._config_manager.update_download_config(download_config)
            return {"success": True, "message": "下载配置更新成功"}
        except Exception as e:
            logger.error("更新下载配置失败: %s", e)
            return {"success": False, "message": str(e)}

    def select_directory(self) -> Dict[str, Any]:
        try:
            root = Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            
            selected_dir = filedialog.askdirectory(title="选择目录")
            root.destroy()
            
            if selected_dir:
                return {
                    "success": True,
                    "data": {"path": selected_dir},
                    "message": "目录选择成功"
                }
            else:
                return {"success": False, "message": "用户取消选择", "data": None}
        except Exception as e:
            logger.error("选择目录失败: %s", e)
            return {"success": False, "message": str(e), "data": None}

    def scan_versions_in_path(self, path: str | List[str] | List[Dict[str, str]]) -> Dict[str, Any]:
        try:
            actual_path = path
            # 处理新格式: [{"name": "xxx", "path": "xxx"}]
            while isinstance(actual_path, list) and len(actual_path) > 0:
                first = actual_path[0]
                if isinstance(first, dict) and "path" in first:
                    actual_path = first["path"]
                    break
                actual_path = first
            
            # 兼容旧格式: 直接是字符串
            if isinstance(actual_path, list):
                if len(actual_path) == 0:
                    return {"success": False, "message": "路径列表为空", "data": None}
                actual_path = actual_path[0]
            
            if not isinstance(actual_path, (str, Path)):
                actual_path = str(actual_path)
            
            if not actual_path or not isinstance(actual_path, (str, Path)):
                return {"success": False, "message": f"无效的路径类型: {type(actual_path)}", "data": None}

            core = ECLauncherCore()
            versions = core.scan_versions_in_path(actual_path)
            safe_versions = make_json_safe(versions)
            logger.debug("在路径 %s 中扫描到 %d 个版本", actual_path, len(versions))
            return {
                "success": True,
                "data": safe_versions,
                "message": f"扫描完成，共找到 {len(versions)} 个版本"
            }
        except Exception as e:
            logger.error("扫描版本失败: %s", e)
            return {"success": False, "message": str(e), "data": None}

    def get_minecraft_versions(self) -> Dict[str, Any]:
        try:
            versions = ECLauncherCore.get_version_list()
            version_list = []
            for v in versions:
                version_list.append({
                    "id": v.get("id", ""),
                    "type": v.get("type", "release"),
                    "releaseTime": v.get("releaseTime", ""),
                    "url": v.get("url", "")
                })
            return {
                "success": True,
                "data": version_list,
                "message": f"获取到 {len(version_list)} 个版本"
            }
        except Exception as e:
            logger.error("获取 Minecraft 版本列表失败: %s", e)
            return {"success": False, "message": str(e), "data": []}

    def get_fabric_versions(self) -> Dict[str, Any]:
        try:
            versions = ECLauncherCore.get_fabric_loader_list()
            return {
                "success": True,
                "data": versions[:20] if versions else [],
                "message": f"获取到 {len(versions)} 个 Fabric 版本"
            }
        except Exception as e:
            logger.error("获取 Fabric 版本列表失败: %s", e)
            return {"success": False, "message": str(e), "data": []}

    def install_version(self, version_id: str, options: Dict[str, Any] = None) -> Dict[str, Any]:
        try:
            options = options or {}
            game_path = options.get("gamePath")
            loader = options.get("loader", "")
            loader_version = options.get("loaderVersion", "")
            
            config = self._config_manager.get_game_config()
            if not game_path:
                game_path = config.get("minecraft_path", "./.minecraft")
            
            core = ECLauncherCore(game_path)
            
            if loader == "fabric":
                result = core.install(version_id, "fabric", loader_version or None)
            else:
                result = core.install(version_id)
            
            return {
                "success": result,
                "data": {"version": version_id, "loader": loader or "vanilla"},
                "message": "安装任务已启动" if result else "安装失败"
            }
        except Exception as e:
            logger.error("安装版本失败: %s", e)
            return {"success": False, "message": str(e), "data": None}

def on_closed():
    logger.info("窗口已关闭")
    
def on_loaded():
    logger.info("窗口已加载完成")
    if webview.windows:
        webview.windows[0].show()

def run_ui(config=None, debug=False, config_manager=None):
    # 确保配置管理器已加载
    if config_manager:
        try:
            if not config_manager.config:
                config_manager.load()
                logger.info("配置已加载")
        except Exception as e:
            logger.error("启动时加载配置失败: %s", e)
    
    ui_config = config[0].get("ui", {}) if config else {}
    width = ui_config.get("width", 1000)
    height = ui_config.get("height", 700)
    title = ui_config.get("title", "EuoraCraft Launcher")
    
    api = Api(config_manager)
    
    html_path = "http://localhost:5173"
    # rp('ui/dist/index.html')
    
    window = webview.create_window(
        title,
        url=html_path,
        js_api=api,
        width=width, 
        height=height,
        frameless=True, 
        easy_drag=False,
        hidden=True, 
        shadow=True,
        text_select=False
    )
    
    window.events.minimized += lambda: logger.info("窗口已最小化")
    window.events.restored += lambda: logger.info("窗口已还原")
    window.events.loaded += on_loaded
    window.events.closed += on_closed
    
    webview.start(debug=debug)
    logger.info('程序已退出')