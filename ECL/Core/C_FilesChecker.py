from pathlib import Path
from typing import Callable, List, Tuple, Optional, Dict, Any, Union
import json
import requests
from . import C_Libs, C_Downloader
from ..logger import get_logger

logger = get_logger("checker")

class FilesChecker:
    """文件检查器，负责校验游戏本体、依赖库和资源的完整性"""
    
    def __init__(self, api_url: C_Libs.ApiUrl | None = None, downloader: C_Downloader.Downloader | None = None):
        self.api_url = api_url if api_url else C_Libs.ApiUrl()
        self.downloader = downloader if downloader else C_Downloader.Downloader()
        self.output_log = self.__default_output_log

    @staticmethod
    def __default_output_log(log: str):
        logger.info(log)

    def set_output_log(self, output_function: Callable[[str], None]) -> None:
        self.output_log = output_function

    def __find_api(self, get_url: str, get_path: str) -> List[str]:
        """根据 URL 模式匹配对应的镜像源，返回 [镜像链接, 原始链接]"""
        if not get_url: return []
        
        mapping = {
            "libraries.minecraft.net": self.api_url.Libraries,
            "resources.download.minecraft.net": self.api_url.Assets,
            "launchermeta.mojang.com": self.api_url.Meta,
            "launcher.mojang.com": self.api_url.Data,
            "files.minecraftforge.net": self.api_url.Forge,
            "maven.fabricmc.net": self.api_url.Fabric,
            "meta.fabricmc.net": self.api_url.FabricMeta,
            "maven.neoforged.net": self.api_url.NeoForged,
            "maven.quiltmc.org": self.api_url.Quilt,
            "meta.quiltmc.org": self.api_url.QuiltMeta
        }
        
        urls = []
        for domain, mirror in mapping.items():
            if domain in get_url:
                # 特殊处理 BMCLAPI 的资源下载路径
                if domain == "resources.download.minecraft.net" and "bangbang93" in mirror:
                    asset_hash = get_url.split("/")[-1]
                    urls.append(f"{mirror}/{asset_hash}")
                else:
                    urls.append(f"{mirror}/{get_path}")
                break
        
        if get_url not in urls:
            urls.append(get_url)
        return urls

    def __download_inherited_json(self, game_path: Path, version_id: str, target_version_name: str) -> bool:
        """当本地缺少继承的原版 JSON 时，自动下载到当前版本文件夹"""
        self.output_log(f"正在补全原版配置 {version_id}...")
        manifest_url = f"{self.api_url.Meta}/mc/game/version_manifest.json"
        try:
            resp = requests.get(manifest_url, timeout=10)
            resp.raise_for_status()
            manifest = resp.json()
            
            version_info = next((v for v in manifest["versions"] if v["id"] == version_id), None)
            if not version_info:
                logger.error(f"未在官方清单中找到版本: {version_id}")
                return False
            
            # 下载到当前版本文件夹下，文件名为 原版ID.json
            target_dir = game_path / "versions" / target_version_name
            target_dir.mkdir(parents=True, exist_ok=True)
            target_json = target_dir / f"{version_id}.json"
            
            urls = self.__find_api(version_info["url"], f"versions/{version_id}/{version_id}.json")
            return self.downloader.download_manager([(urls, str(target_json))], 1)
        except Exception as e:
            logger.error(f"补全原版 JSON 失败: {e}")
            return False

    def __check_game_jar(self, game_path: Path, version_name: str, version_json: dict, target_version_name: str = None) -> List[Tuple[List[str], str]]:
        """检查游戏核心 Jar 文件"""
        download_list = []
        client_download = version_json.get("downloads", {}).get("client", {})
        if not client_download:
            return download_list

        save_version_name = target_version_name or version_name
        jar_path = game_path / "versions" / save_version_name / f"{save_version_name}.jar"
        
        sha1 = client_download.get("sha1")
        url = client_download.get("url")

        if not jar_path.exists() or (sha1 and C_Libs.get_file_sha1(jar_path) != sha1):
            urls = self.__find_api(url, f"versions/{version_name}/{version_name}.jar")
            download_list.append((urls, str(jar_path)))
        
        return download_list

    def __check_libraries(self, game_path: Path, version_json: dict) -> List[Tuple[List[str], str]]:
        """检查依赖库文件"""
        download_list = []
        for lib in version_json.get("libraries", []):
            downloads = lib.get("downloads", {})
            artifact = downloads.get("artifact", {})
            
            # 1. 处理带有 downloads 字段的库 (通常是原版库)
            if artifact:
                path = artifact.get("path") or C_Libs.name_to_path(lib["name"])
                full_path = game_path / "libraries" / path
                if not full_path.exists() or (artifact.get("sha1") and C_Libs.get_file_sha1(full_path) != artifact["sha1"]):
                    urls = self.__find_api(artifact.get("url"), path)
                    download_list.append((urls, str(full_path)))
            
            # 2. 处理没有 downloads 字段但有 name 的库 (通常是 Fabric/Forge 库)
            elif "name" in lib:
                path = C_Libs.name_to_path(lib["name"])
                if path:
                    full_path = game_path / "libraries" / path
                    if not full_path.exists():
                        # 如果库定义里有 url，则使用它作为基础下载地址
                        lib_url = lib.get("url", "https://libraries.minecraft.net/")
                        urls = self.__find_api(f"{lib_url.rstrip('/')}/{path}", path)
                        download_list.append((urls, str(full_path)))

            # 3. 处理 Natives 分类器
            classifiers = downloads.get("classifiers", {})
            for classifier in classifiers.values():
                c_path = classifier.get("path")
                c_full_path = game_path / "libraries" / c_path
                if not c_full_path.exists() or (classifier.get("sha1") and C_Libs.get_file_sha1(c_full_path) != classifier["sha1"]):
                    urls = self.__find_api(classifier.get("url"), c_path)
                    download_list.append((urls, str(c_full_path)))
        
        return download_list

    def __check_assets(self, game_path: Path, version_json: dict) -> List[Tuple[List[str], str]]:
        """检查游戏资源文件"""
        download_list = []
        asset_index = version_json.get("assetIndex", {})
        if not asset_index: 
            return download_list

        index_id = asset_index["id"]
        index_path = game_path / "assets" / "indexes" / f"{index_id}.json"
        index_url = asset_index["url"]

        # 强制重新下载索引（解决损坏问题）
        urls = self.__find_api(index_url, f"indexes/{index_id}.json")
        if not self.downloader.download_manager([(urls, str(index_path))], 1):
            logger.error("资源索引下载失败")
            return download_list

        if index_path.exists():
            try:
                with open(index_path, "r", encoding="utf-8") as f:
                    objects = json.load(f).get("objects", {})
                
                total = len(objects)
                logger.info(f"校验 {total} 个资源文件...")
                
                for name, info in objects.items():
                    h = info["hash"]
                    rel = f"objects/{h[:2]}/{h}"
                    full = game_path / "assets" / rel
                    # 严格校验：如果不存在或哈希不匹配，一律重新下载
                    if not full.exists():
                        primary_url = f"https://resources.download.minecraft.net/{h[:2]}/{h}"
                        urls = self.__find_api(primary_url, rel)
                        download_list.append((urls, str(full)))
                    elif C_Libs.get_file_sha1(full) != h:
                        # 哈希不匹配，删除并重新下载
                        full.unlink(missing_ok=True)
                        primary_url = f"https://resources.download.minecraft.net/{h[:2]}/{h}"
                        urls = self.__find_api(primary_url, rel)
                        download_list.append((urls, str(full)))
                        
            except Exception as e:
                logger.error(f"解析资源失败: {e}")
        return download_list    

    def check_files(self, game_path: str | Path, version_name: str, download_max_thread: int):
        """执行完整的文件检查和下载流程"""
        game_path = Path(game_path)
        json_path = game_path / "versions" / version_name / f"{version_name}.json"
        
        if not json_path.exists():
            raise FileNotFoundError(f"找不到版本配置文件: {json_path}")

        with open(json_path, "r", encoding="utf-8") as f:
            version_json = json.load(f)

        total_list = []
        self.output_log(f"开始校验版本: {version_name}")

        # 1. 检查当前版本的 Jar 和库
        total_list.extend(self.__check_game_jar(game_path, version_name, version_json))
        total_list.extend(self.__check_libraries(game_path, version_json))

        # 2. 处理继承版本 (Fabric/Forge)
        inherits_from = version_json.get("inheritsFrom")
        if inherits_from:
            # 优先从当前文件夹查找
            game_data = C_Libs.find_version(version_json, game_path, current_version_name=version_name)
            if not game_data:
                # 自动补全原版 JSON 到当前文件夹
                if self.__download_inherited_json(game_path, inherits_from, target_version_name=version_name):
                    game_data = C_Libs.find_version(version_json, game_path, current_version_name=version_name)
            
            if game_data:
                g_json, _ = game_data
                self.output_log(f"正在校验继承的原版版本: {inherits_from}")
                # 将原版 Jar 下载到当前版本文件夹下，并重命名为当前版本名，实现自包含
                total_list.extend(self.__check_game_jar(game_path, inherits_from, g_json, target_version_name=version_name))
                total_list.extend(self.__check_libraries(game_path, g_json))
                total_list.extend(self.__check_assets(game_path, g_json))
            else:
                logger.error(f"无法获取继承版本 {inherits_from} 的配置，将跳过原版文件校验")
        else:
            total_list.extend(self.__check_assets(game_path, version_json))

        if total_list:
            self.output_log(f"发现 {len(total_list)} 个文件缺失或损坏，开始下载...")
            self.downloader.download_manager(total_list, download_max_thread)
        else:
            self.output_log("所有文件校验通过")
