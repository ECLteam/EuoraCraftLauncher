from . import C_Libs, C_Downloader, C_FilesChecker
from typing import Callable
from shutil import rmtree
from pathlib import Path
import subprocess
import platform
from uuid import uuid4
import json
import re
import requests
from ..logger import get_logger

logger = get_logger("ECLauncherCore")

class ECLauncherCore:
    def __init__(self):
        self.output_launcher_log = self.__default_output_log
        self.output_minecraft_instance = self.__default_output_log
        self.output_jvm_params = self.__default_output_log

        self.api_url = C_Libs.ApiUrl()
        self.downloader = C_Downloader.Downloader()
        self.files_checker = C_FilesChecker.FilesChecker(self.api_url, self.downloader)

        self.system_type = platform.system()  # 获取系统类型

        self.instances: list[dict[str, str | bool | subprocess.Popen]] = []  # 游戏进程列表

    @staticmethod
    def __default_output_log(log):
        logger.info(log)

    def set_api_url(self, api_url_dict: dict):
        self.api_url.update_from_dict(api_url_dict)

    def set_output_launcher_log(self, output_function: Callable[[str], None]) -> None:
        self.output_launcher_log = output_function

    def set_output_minecraft_instance(self, output_function: Callable[[dict[str, str | bool | subprocess.Popen]], None]) -> None:
        self.output_minecraft_instance = output_function

    def set_output_jvm_params(self, output_function: Callable[[str], None]) -> None:
        self.output_jvm_params = output_function

    def launch_minecraft(self, java_path: str | Path, game_path: str | Path, version_name: str, max_use_ram: int, player_name: str,
                         user_type: str = "legacy", auth_uuid: str = "", access_token: str = "None",
                         first_set_lang: str = "zh_CN", set_lang: str = "", launcher_name: str = "ECL",
                         launcher_version: str = "0.1145", default_version_type: bool = False,
                         custom_jvm_params: str = "", window_width: int | str = "${resolution_width}",
                         window_height: int | str = "${resolution_width}",
                         completes_file: bool = True, download_max_thread: int = 32,
                         output_jvm_params: bool = False, write_run_script: bool = False, run_script_path: str | Path = "."):
        if re.search(r"[^a-zA-Z0-9\-_+.]", player_name):  # 检测用户名是否合法
            error_meg = "玩家名称不能包含数字、减号、下划线、加号或英文句号(小数点)以外的字符"
            self.output_launcher_log(error_meg)
            raise ValueError(error_meg)

        if auth_uuid != "" and not C_Libs.is_uuid3(auth_uuid):  # 检测是否定义了UUID3,是否合法
            error_msg = "错误的 UUID, UUID 必须是 UUID3"
            self.output_launcher_log(error_msg)
            raise ValueError(error_msg)

        java_path = Path(java_path)
        game_path = Path(game_path)
        version_json = game_path / "versions" / version_name / f"{version_name}.json"

        if not java_path.is_file():
            error_msg = f"未找到 Java 可执行文件 {java_path}"
            self.output_launcher_log(error_msg)
            raise FileExistsError(error_msg)

        if not version_json.is_file():
            error_msg = f"未找到游戏 {version_name}"
            self.output_launcher_log(error_msg)
            raise FileExistsError(error_msg)

        if max_use_ram < 256:
            max_use_ram = 256

        if completes_file:
            self.files_checker.check_files(game_path, version_name, download_max_thread)

        jvm_params_list = []
        cp_delimiter = ":"  # ClassPath分隔符
        run_script_suffix = ".sh"
        self.output_launcher_log(f"系统平台 {self.system_type}")

        if self.system_type == "Windows":  # 判断是否为Windows
            run_script_suffix = ".bat"
            cp_delimiter = ";"
            jvm_params_list.append("-XX:HeapDumpPath=MojangTricksIntelDriversForPerformance_javaw.exe_minecraft.exe.heapdump")
        elif self.system_type == "Darwin":  # 判断是否为MacOS(OSX)
            run_script_suffix = ".command"
            jvm_params_list.append(f"-XstartOnFirstThread")

        jvm_params_list.append(f"-Xms256M -Xmx{max_use_ram}M -Dstderr.encoding=UTF-8 -Dstdout.encoding=UTF-8 -Dfile.encoding=COMPAT -XX:+UseZGC -XX:-UseAdaptiveSizePolicy -XX:-OmitStackTraceInFastThrow -Dfml.ignoreInvalidMinecraftCertificates=True -Dfml.ignorePatchDiscrepancies=True -Dlog4j2.formatMsgNoLookups=true")

        if custom_jvm_params:  # 添加自定义Jvm
            for a_jvm_param in custom_jvm_params.split(" "):
                if not a_jvm_param: continue
                jvm_params_list.append(a_jvm_param.replace(" ", ""))

        version_json = json.loads(version_json.read_text("utf-8"))

        if "arguments" in version_json:
            if "jvm" in version_json["arguments"]:
                for arguments_jvm in version_json["arguments"]["jvm"]:  # 遍历Json中的Jvm参数
                    if type(arguments_jvm) is not str: continue
                    if "${classpath_separator}" in arguments_jvm:  # 这个判断针对NeoForged的,为-p参数的依赖两边加双引号
                        jvm_params_list.append(f"\"{arguments_jvm.replace(' ', '')}\"")
                    else:
                        jvm_params_list.append(arguments_jvm.replace(" ", ""))
            if "game" in version_json["arguments"]:
                for arguments_game in version_json["arguments"]["game"]:  # 遍历Json中的Jvm参数
                    if type(arguments_game) is not str: continue
                    jvm_params_list.append(arguments_game.replace(" ", ""))
        elif "minecraftArguments" in version_json:
            jvm_params_list.append("-Djava.library.path=${natives_directory} -cp ${classpath}")
            jvm_params_list.append(version_json["minecraftArguments"])

        if window_width != "${resolution_width}" != window_height:
            jvm_params_list.append(f"--width {window_width} --height {window_height}")
        class_path_list = []
        asm_versions = []  # 处理ASM库版本冲突
        natives_path_list = []

        for libraries in version_json["libraries"]:  # 遍历依赖
            libraries_path = game_path / "libraries" / C_Libs.name_to_path(libraries["name"])
            if str(libraries_path) in class_path_list: continue  # 防止重复添加
            if re.search(r"asm-\d+(?:\.\d+)*", libraries_path.stem):  # 处理ASM库版本冲突
                asm_versions.append(libraries_path)
                continue
            class_path_list.append(str(libraries_path))
            if "classifiers" not in libraries.get("downloads", {}): continue  # 查找natives
            for classifiers in libraries["downloads"]["classifiers"].values():
                natives_path = game_path / "libraries" / classifiers["path"]
                if natives_path in natives_path_list: continue  # 防止重复添加
                natives_path_list.append(natives_path)


        version_jar = game_path / "versions" / version_name / f"{version_name}.jar"
        asset_index_id = ""

        if "id" in version_json.get("assetIndex", {}):
            asset_index_id = version_json["assetIndex"]["id"]

        game_json = C_Libs.find_version(version_json, game_path)

        if game_json:
            game_json, version_path = game_json
            if "arguments" in game_json:
                if "jvm" in game_json["arguments"]:
                    for arguments_jvm in game_json["arguments"]["jvm"]:  # 遍历Json中的Jvm参数
                        if type(arguments_jvm) is not str: continue
                        arguments_jvm = arguments_jvm.replace(" ", "")
                        if arguments_jvm in jvm_params_list: continue # 防止重复添加
                        jvm_params_list.append(arguments_jvm)
                if "game" in game_json["arguments"]:
                    for arguments_game in game_json["arguments"]["game"]:  # 遍历Json中的Jvm参数
                        if type(arguments_game) is not str: continue
                        arguments_game = arguments_game.replace(" ", "")
                        if arguments_game in jvm_params_list: continue  # 防止重复添加
                        jvm_params_list.append(arguments_game)
            elif "minecraftArguments" not in version_json and "minecraftArguments" in version_jar:
                jvm_params_list.append("-Djava.library.path=${natives_directory} -cp ${classpath}")
                jvm_params_list.append(game_json["minecraftArguments"])

            for libraries in game_json["libraries"]:  # 遍历依赖
                libraries_path = game_path / "libraries" / C_Libs.name_to_path(libraries["name"])
                if str(libraries_path) in class_path_list: continue  # 防止重复添加
                if re.search(r"asm-\d+(?:\.\d+)*", libraries_path.stem) and libraries_path not in asm_versions:  # Fuck ASM!!!
                    asm_versions.append(libraries_path)
                    continue
                class_path_list.append(str(libraries_path))
                if "classifiers" not in libraries.get("downloads", {}): continue  # 查找natives
                for classifiers in libraries["downloads"]["classifiers"].values():
                    natives_path = game_path / "libraries" / classifiers["path"]
                    if natives_path in natives_path_list: continue  # 防止重复添加
                    natives_path_list.append(natives_path)

            if not version_jar.is_file():
                version_jar = version_path / f"{version_path.name}.jar"

            if not asset_index_id:
                asset_index_id = game_json["assetIndex"]["id"]

        asm_version = 0
        asm_path = ""

        for get_asm in asm_versions:  # Fuck ASM!!!
            get_asm_version = float(get_asm.stem.replace("asm-", ""))
            if get_asm_version > asm_version:
                asm_version = get_asm_version
                asm_path = str(get_asm)
        if asm_path:
            class_path_list.append(asm_path)

        class_path_list.append(str(version_jar))
        jvm_params = f'"{java_path}" {" ".join(jvm_params_list)}'
        class_path = f'"{cp_delimiter.join(class_path_list)}" {version_json["mainClass"]}'
        natives_path = game_path / "versions" / version_name / "natives"
        is_set_lang = False

        if  natives_path.is_dir():
            rmtree(natives_path)
            natives_path.mkdir(parents=True, exist_ok=True)
        else:
            is_set_lang = True
            natives_path.mkdir(parents=True, exist_ok=True)

        self.output_launcher_log(f"需要解压 {len(natives_path_list)} 个文件")
        for a_natives in natives_path_list:
            C_Libs.unzip(a_natives, natives_path)

        if is_set_lang or set_lang:  # 设置游戏语言
            options_contents = lang = f"lang:{set_lang}" if set_lang else f"lang:{first_set_lang}"
            options_path = game_path / "versions" / version_name / "options.txt"
            if options_path.is_file():
                options_contents = options_path.read_text("utf-8")
                options_contents = re.sub(r"^lang:\S+$", lang, options_contents, flags=re.MULTILINE)
            options_path.write_text(options_contents, "utf-8")
            self.output_launcher_log(f"设置游戏语言为 {lang}")

        if user_type == "legacy":  # 离线模式设置唯一标识id
            auth_uuid = C_Libs.name_to_uuid(player_name).hex
            self.output_launcher_log(f"未设置 UUID, 生成 UUID 为 {auth_uuid}")

        jvm_params = C_Libs.replace_last(
            jvm_params.replace("${classpath}", class_path)  # 把-cp参数内容换成拼接好的依赖路径
            .replace("${library_directory}", f'"{game_path / "libraries"}"', 1)  # 依赖文件夹路径
            .replace("${assets_root}", f'"{game_path / "assets"}"')  # 资源文件夹路径
            .replace("${assets_index_name}", asset_index_id)  # 资源索引id
            .replace("${natives_directory}", f'"{natives_path}"')  # 依赖库文件夹路径
            .replace("${game_directory}", f'"{game_path / "versions" / version_name}"')  # 游戏文件存储路径
            .replace("${launcher_name}", f'"{launcher_name}"')  # 启动器名字
            .replace("${launcher_version}", f'"{launcher_version}"')  # 启动器版本
            # .replace("${version_name}", f'"{version_name}"', -1)
            .replace("${version_type}", f'"{version_json.get("type", launcher_name)}"' if default_version_type else f'"{launcher_name}"')  # 版本类型
            .replace("${auth_player_name}", f'"{player_name}"')  # 玩家名字
            .replace("${user_type}", user_type)  # 登录方式
            .replace("${auth_uuid}", auth_uuid)
            .replace("${auth_access_token}", access_token)  # 正版登录令牌
            .replace("${user_properties}", "{}")  # 老版本的用户配置项
            .replace("${classpath_separator}", cp_delimiter)  # NeoForged的占位符,替换为ClassPath的分隔符
            .replace("${library_directory}", f'{game_path/ "libraries"}')  # NeoForged的占位符,获取依赖文件夹路径
            .replace("${primary_jar_name}", version_jar.name)  # NeoForged的占位符,替换为游戏本体Jar文件名
            ,
            "${version_name}",
            f'"{version_name}"'  # 版本名字
        ).replace("${version_name}", version_name)  # NeoForged的占位符,替换为游戏版本名称

        if write_run_script:
            run_script_path = Path(run_script_path) / f"run{run_script_suffix}"
            self.output_launcher_log(f"生成的启动脚本在 {run_script_path}")
            run_script_path.write_text(jvm_params, "utf-8")
        if output_jvm_params:
            self.output_launcher_log("输出启动参数")
            self.output_jvm_params(jvm_params)
        else:
            self.output_launcher_log("正在启动游戏...")
            instance_info = {
                "Name": version_name,
                "ID": uuid4().hex,
                "Type": "MinecraftClient",
                "StdIn": False,
                "Instance": subprocess.Popen(
                    jvm_params,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,
                    text=True,
                    errors="ignore"
                )  # 启动游戏
            }
            self.instances.append(instance_info)
            self.output_minecraft_instance(instance_info)

    def scan_versions_in_path(self, base_path: str | Path) -> list[dict]:
        base_path = Path(base_path)
        if not base_path.is_dir():
            return [{"folder": str(base_path), "status": "failure", "loader_type": None, "version": None, "error": "路径不存在或不是目录"}]
        
        # 严格检查：必须是包含 versions 目录的 Minecraft 路径
        versions_dir = base_path / "versions"
        if not versions_dir.is_dir():
            return [{"folder": str(base_path), "status": "failure", "loader_type": None, "version": None, "error": "未找到 versions 目录，不是有效的 Minecraft 安装路径"}]
        
        results = []
        for child in versions_dir.iterdir():
            if not child.is_dir():
                continue
            folder_name = child.name
            # 查找版本目录下的 json 文件（名字和目录名一致）
            json_file = child / f"{folder_name}.json"
            if not json_file.exists():
                # 尝试找任意 json 文件
                json_files = list(child.glob("*.json"))
                if not json_files:
                    continue  # 跳过没有 json 的目录
                json_file = json_files[0]
            
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                loader_type = data.get("type", "Unknown")
                version = data.get("id", "Unknown")
                results.append({
                    "folder": folder_name,
                    "status": "success",
                    "loader_type": loader_type,
                    "version": version,
                    "error": None
                })
            except Exception as e:
                results.append({
                    "folder": folder_name,
                    "status": "failure",
                    "loader_type": None,
                    "version": None,
                    "error": f"解析JSON失败: {e}"
                })
        return results

    @staticmethod
    def get_version_list() -> list[dict]:
        try:
            url = "https://launchermeta.mojang.com/mc/game/version_manifest.json"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get("versions", [])
        except Exception as e:
            logger.error("获取 Minecraft 版本列表失败: %s", e)
            return []

    @staticmethod
    def get_fabric_loader_list() -> list[str]:
        try:
            url = "https://meta.fabricmc.net/v2/versions/loader"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            versions = [item.get("version", "") for item in data if item.get("version")]
            return versions
        except Exception as e:
            logger.error("获取 Fabric Loader 版本列表失败: %s", e)
            return []

    def install(self, version_id: str, loader: str = None, loader_version: str = None) -> bool:
        try:
            game_path = Path("./.minecraft")
            versions_dir = game_path / "versions"
            version_dir = versions_dir / version_id
            version_dir.mkdir(parents=True, exist_ok=True)
            
            # 获取版本元数据
            versions = self.get_version_list()
            version_info = None
            for v in versions:
                if v.get("id") == version_id:
                    version_info = v
                    break
            
            if not version_info:
                logger.error("未找到版本 %s", version_id)
                return False
            
            # 下载版本 JSON
            version_url = version_info.get("url")
            if not version_url:
                return False
            
            response = requests.get(version_url, timeout=30)
            response.raise_for_status()
            version_json = response.json()
            
            # 保存原版 JSON
            vanilla_json_path = version_dir / f"{version_id}.json"
            vanilla_json_path.write_text(json.dumps(version_json, indent=2), encoding="utf-8")
            
            # 如果是 Fabric，下载 Fabric 版本 JSON
            if loader == "fabric":
                fabric_version = loader_version or self.get_fabric_loader_list()[0]
                fabric_url = f"https://meta.fabricmc.net/v2/versions/loader/{version_id}/{fabric_version}/profile/json"
                
                try:
                    fabric_response = requests.get(fabric_url, timeout=30)
                    fabric_response.raise_for_status()
                    fabric_json = fabric_response.json()
                    
                    # 保存 Fabric JSON
                    fabric_version_name = f"{version_id}-fabric-{fabric_version}"
                    fabric_dir = versions_dir / fabric_version_name
                    fabric_dir.mkdir(parents=True, exist_ok=True)
                    fabric_json_path = fabric_dir / f"{fabric_version_name}.json"
                    fabric_json_path.write_text(json.dumps(fabric_json, indent=2), encoding="utf-8")
                    
                    logger.info("Fabric 版本 %s 安装成功", fabric_version_name)
                    return True
                except Exception as e:
                    logger.error("下载 Fabric 版本失败: %s", e)
                    return False
            
            logger.info("原版版本 %s 安装成功", version_id)
            return True
        except Exception as e:
            logger.error("安装版本失败: %s", e)
            return False
