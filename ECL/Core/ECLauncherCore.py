from . import C_Libs, C_Downloader, C_FilesChecker
from typing import Callable, List, Dict, Union, Optional, Any
from shutil import rmtree
from pathlib import Path
import subprocess
import platform
from uuid import uuid4
import json
import re
from dataclasses import dataclass, field
from ..logger import get_logger

logger = get_logger("core")

@dataclass
class LaunchSettings:
    """游戏启动配置参数类"""
    java_path: Path
    game_path: Path
    version_name: str
    max_use_ram: int
    player_name: str
    user_type: str = "Legacy"
    auth_uuid: str = ""
    access_token: str = "None"
    first_set_lang: str = "zh_CN"
    set_lang: str = ""
    launcher_name: str = "ECL"
    launcher_version: str = "0.1145"
    default_version_type: bool = False
    custom_jvm_params: str = ""
    window_width: Union[int, str] = "${resolution_width}"
    window_height: Union[int, str] = "${resolution_height}"
    completes_file: bool = True
    download_max_thread: int = 64
    output_jvm_params: bool = False
    write_run_script: bool = False
    run_script_path: Path = Path(".")

class ECLauncherCore:
    """启动器核心类，负责游戏启动逻辑、参数拼接和进程管理"""
    
    def __init__(self):
        self.output_launcher_log = self.__default_output_log
        self.output_minecraft_instance = self.__default_output_log
        self.output_jvm_params = self.__default_output_log

        self.api_url = C_Libs.ApiUrl()
        self.downloader = C_Downloader.Downloader()
        self.files_checker = C_FilesChecker.FilesChecker(self.api_url, self.downloader)

        self.system_type = platform.system()
        self.instances: List[Dict[str, Union[str, bool, subprocess.Popen]]] = []

    @staticmethod
    def __default_output_log(log):
        logger.info(str(log))

    def set_api_url(self, api_url_dict: dict):
        """更新 API 镜像源地址"""
        self.api_url.update_from_dict(api_url_dict)

    def set_output_launcher_log(self, output_function: Callable[[str], None]) -> None:
        self.output_launcher_log = output_function

    def set_output_minecraft_instance(self, output_function: Callable[[dict], None]) -> None:
        self.output_minecraft_instance = output_function

    def set_output_jvm_params(self, output_function: Callable[[str], None]) -> None:
        self.output_jvm_params = output_function

    def _validate_params(self, settings: LaunchSettings):
        """校验启动参数合法性"""
        if re.search(r"[^a-zA-Z0-9\-_+.]", settings.player_name):
            raise ValueError("玩家名称包含非法字符")

        if settings.auth_uuid and not C_Libs.is_uuid3(settings.auth_uuid):
            raise ValueError("错误的 UUID, 必须是 UUID3")

        if not settings.java_path.is_file():
            raise FileNotFoundError(f"未找到 Java 可执行文件: {settings.java_path}")

        version_json_path = settings.game_path / "versions" / settings.version_name / f"{settings.version_name}.json"
        if not version_json_path.is_file():
            raise FileNotFoundError(f"未找到游戏版本配置文件: {version_json_path}")

    def _get_base_jvm_args(self, settings: LaunchSettings) -> List[str]:
        """构建基础 JVM 参数"""
        args = []
        if self.system_type == "Windows":
            args.append("-XX:HeapDumpPath=MojangTricksIntelDriversForPerformance_javaw.exe_minecraft.exe.heapdump")
            if platform.release() == "10":
                args.append("-Dos.name=Windows 10")
                args.append("-Dos.version=10.0")
        elif self.system_type == "Darwin":
            args.append("-XstartOnFirstThread")

        max_ram = max(256, settings.max_use_ram)
        args.extend([
            "-Xms256M",
            f"-Xmx{max_ram}M",
            "-Dstderr.encoding=UTF-8",
            "-Dstdout.encoding=UTF-8",
            "-Dfile.encoding=COMPAT",
            "-XX:+UseG1GC",
            "-XX:-UseAdaptiveSizePolicy",
            "-XX:-OmitStackTraceInFastThrow",
            "-Dfml.ignoreInvalidMinecraftCertificates=True",
            "-Dfml.ignorePatchDiscrepancies=True",
            "-Dlog4j2.formatMsgNoLookups=true"
        ])

        if settings.custom_jvm_params:
            args.extend([p for p in settings.custom_jvm_params.split(" ") if p])
        
        return args

    def _process_libraries(self, libs: List[Dict], game_path: Path, class_path_list: List[str], 
                           natives_path_list: List[Path], asm_versions: List[Path]):
        """处理依赖库"""
        for lib in libs:
            path_str = C_Libs.name_to_path(lib["name"])
            if not path_str:
                continue
            lib_path = (game_path / "libraries" / path_str).absolute()
            
            if str(lib_path) in class_path_list:
                continue
            
            if re.search(r"asm-\d+(?:\.\d+)*", lib_path.stem):
                asm_versions.append(lib_path)
                continue
            
            class_path_list.append(str(lib_path))
            
            if "classifiers" in lib.get("downloads", {}):
                for classifier in lib["downloads"]["classifiers"].values():
                    n_path = game_path / "libraries" / classifier["path"]
                    if n_path not in natives_path_list:
                        natives_path_list.append(n_path)

    def _handle_natives(self, settings: LaunchSettings, natives_path_list: List[Path]) -> Path:
        """解压 Natives 库"""
        natives_path = (settings.game_path / "versions" / settings.version_name / "natives").absolute()
        if natives_path.exists():
            rmtree(natives_path)
        natives_path.mkdir(parents=True, exist_ok=True)
        
        if natives_path_list:
            self.output_launcher_log(f"正在解压 Natives 库 ({len(natives_path_list)} 个)...")
            for n_lib in natives_path_list:
                C_Libs.unzip(n_lib, natives_path)
        return natives_path

    def _handle_language(self, settings: LaunchSettings):
        """设置游戏语言"""
        options_path = settings.game_path / "versions" / settings.version_name / "options.txt"
        if settings.set_lang or not options_path.exists():
            lang = settings.set_lang if settings.set_lang else settings.first_set_lang
            content = f"lang:{lang}"
            if options_path.is_file():
                old_content = options_path.read_text("utf-8")
                content = re.sub(r"^lang:\S+$", f"lang:{lang}", old_content, flags=re.MULTILINE)
            options_path.write_text(content, "utf-8")
            self.output_launcher_log(f"已设置游戏语言: {lang}")

    def _build_final_command(self, settings: LaunchSettings, jvm_args: List[str], class_path_list: List[str], 
                             version_json: Dict, version_jar: Path, asset_index_id: str, natives_path: Path) -> List[str]:
        """构建最终启动命令列表"""
        cp_delimiter = ";" if self.system_type == "Windows" else ":"
        
        auth_uuid = settings.auth_uuid
        if settings.user_type == "Legacy":
            auth_uuid = C_Libs.name_to_uuid(settings.player_name).hex

        # 准备替换字典
        replacements = {
            "${classpath}": cp_delimiter.join(class_path_list),
            "${library_directory}": str((settings.game_path / "libraries").absolute()),
            "${assets_root}": str((settings.game_path / "assets").absolute()),
            "${assets_index_name}": asset_index_id,
            "${natives_directory}": str(natives_path),
            "${game_directory}": str((settings.game_path / "versions" / settings.version_name).absolute()),
            "${launcher_name}": settings.launcher_name,
            "${launcher_version}": settings.launcher_version,
            "${version_type}": version_json.get("type", "release") if settings.default_version_type else settings.launcher_name,
            "${auth_player_name}": settings.player_name,
            "${user_type}": settings.user_type,
            "${auth_uuid}": auth_uuid,
            "${auth_access_token}": settings.access_token,
            "${user_properties}": "{}",
            "${classpath_separator}": cp_delimiter,
            "${primary_jar_name}": version_jar.name,
            "${version_name}": settings.version_name,
            "${resolution_width}": str(settings.window_width),
            "${resolution_height}": str(settings.window_height)
        }

        def replace_all(text: str) -> str:
            for k, v in replacements.items():
                text = text.replace(k, str(v))
            return text

        # 1. Java 路径
        final_cmd = [str(settings.java_path.absolute())]
        
        # 2. JVM 参数
        for arg in jvm_args:
            final_cmd.append(replace_all(arg))
            
        # 3. 主类
        final_cmd.append(version_json["mainClass"])
        
        # 4. 游戏参数
        if "arguments" in version_json and "game" in version_json["arguments"]:
            for arg in version_json["arguments"]["game"]:
                if isinstance(arg, str):
                    final_cmd.append(replace_all(arg))
        elif "minecraftArguments" in version_json:
            game_args = replace_all(version_json["minecraftArguments"]).split(" ")
            final_cmd.extend([a for a in game_args if a])
        
        return final_cmd

    def launch_minecraft(self, java_path: str | Path, game_path: str | Path, version_name: str, max_use_ram: int, player_name: str,
                         user_type: str = "Legacy", auth_uuid: str = "", access_token: str = "None",
                         first_set_lang: str = "zh_CN", set_lang: str = "", launcher_name: str = "ECL",
                         launcher_version: str = "0.1145", default_version_type: bool = False,
                         custom_jvm_params: str = "", window_width: int | str = "${resolution_width}",
                         window_height: int | str = "${resolution_height}",
                         completes_file: bool = True, download_max_thread: int = 64,
                         output_jvm_params: bool = False, write_run_script: bool = False, run_script_path: str | Path = "."):
        """启动游戏主入口"""
        try:
            settings = LaunchSettings(
                java_path=Path(java_path).absolute(),
                game_path=Path(game_path).absolute(),
                version_name=version_name,
                max_use_ram=max_use_ram,
                player_name=player_name,
                user_type=user_type,
                auth_uuid=auth_uuid,
                access_token=access_token,
                first_set_lang=first_set_lang,
                set_lang=set_lang,
                launcher_name=launcher_name,
                launcher_version=launcher_version,
                default_version_type=default_version_type,
                custom_jvm_params=custom_jvm_params,
                window_width=window_width,
                window_height=window_height,
                completes_file=completes_file,
                download_max_thread=download_max_thread,
                output_jvm_params=output_jvm_params,
                write_run_script=write_run_script,
                run_script_path=Path(run_script_path)
            )
            self._validate_params(settings)
            
            if settings.completes_file:
                self.output_launcher_log("正在检查文件完整性...")
                self.files_checker.check_files(settings.game_path, settings.version_name, settings.download_max_thread)

            jvm_args = self._get_base_jvm_args(settings)
            
            version_json_path = settings.game_path / "versions" / settings.version_name / f"{settings.version_name}.json"
            version_json = json.loads(version_json_path.read_text("utf-8"))

            # 解析版本参数 (新版 arguments 格式)
            if "arguments" in version_json:
                if "jvm" in version_json["arguments"]:
                    for arg in version_json["arguments"]["jvm"]:
                        if isinstance(arg, str):
                            jvm_args.append(arg)
            else:
                # 旧版格式
                jvm_args.extend(["-Djava.library.path=${natives_directory}", "-cp", "${classpath}"])

            if settings.window_width != "${resolution_width}" and settings.window_height != "${resolution_height}":
                jvm_args.extend(["--width", str(settings.window_width), "--height", str(settings.window_height)])

            # 处理依赖
            class_path_list, natives_path_list, asm_versions = [], [], []
            self._process_libraries(version_json["libraries"], settings.game_path, class_path_list, natives_path_list, asm_versions)

            version_jar = settings.game_path / "versions" / settings.version_name / f"{settings.version_name}.jar"
            asset_index_id = version_json.get("assetIndex", {}).get("id", "")

            # 继承版本处理
            game_data = C_Libs.find_version(version_json, settings.game_path, current_version_name=settings.version_name)
            if game_data:
                game_json, version_path = game_data
                if "arguments" in game_json and "jvm" in game_json["arguments"]:
                    for arg in game_json["arguments"]["jvm"]:
                        if isinstance(arg, str) and arg not in jvm_args:
                            jvm_args.append(arg)
                self._process_libraries(game_json["libraries"], settings.game_path, class_path_list, natives_path_list, asm_versions)
                if not version_jar.is_file():
                    version_jar = version_path / f"{version_path.name}.jar"
                if not asset_index_id:
                    asset_index_id = game_json.get("assetIndex", {}).get("id", "")

            if asm_versions:
                latest_asm = max(asm_versions, key=lambda p: float(p.stem.replace("asm-", "")))
                class_path_list.append(str(latest_asm.absolute()))
            class_path_list.append(str(version_jar.absolute()))

            # 在 launch_minecraft 方法中，构建 final_cmd_list 之前添加以下代码（约第 310 行前）

            # 检测是否为 Fabric 并添加 gameJarPath 参数
            if "fabric" in version_json.get("mainClass", "").lower():
                # 确保 version_jar 指向正确的文件（应该是 1.20.1.jar 重命名为 fabric-loader-0.18.4-1.20.1.jar）
                if not version_jar.exists():
                    # 如果当前版本文件夹没有，尝试使用继承版本的 jar
                    if game_data:
                        _, version_path = game_data
                        original_jar = version_path / f"{version_path.name}.jar"
                        if original_jar.exists():
                            version_jar = original_jar
                
                # 添加 Fabric 必需的 gameJarPath 参数
                jvm_args.append(f"-Dfabric.gameJarPath={version_jar}")
                logger.info(f"已添加 Fabric gameJarPath: {version_jar}")
            natives_path = self._handle_natives(settings, natives_path_list)
            self._handle_language(settings)

            # 构建最终命令列表
            final_cmd_list = self._build_final_command(settings, jvm_args, class_path_list, version_json, version_jar, asset_index_id, natives_path)
            
            if settings.write_run_script:
                suffix = ".bat" if self.system_type == "Windows" else (".command" if self.system_type == "Darwin" else ".sh")
                script_file = settings.run_script_path / f"run{suffix}"
                script_file.write_text(" ".join([f'"{a}"' if " " in a else a for a in final_cmd_list]), "utf-8")
                self.output_launcher_log(f"启动脚本已生成: {script_file}")

            if settings.output_jvm_params:
                self.output_jvm_params(" ".join([f'"{a}"' if " " in a else a for a in final_cmd_list]))
            else:
                self.output_launcher_log("正在启动游戏进程...")
                instance_info = {
                    "Name": settings.version_name,
                    "ID": uuid4().hex,
                    "Type": "MinecraftClient",
                    "StdIn": False,
                    "Instance": subprocess.Popen(final_cmd_list, start_new_session=True, cwd=str((settings.game_path / "versions" / settings.version_name).absolute()))
                }
                self.instances.append(instance_info)
                self.output_minecraft_instance(instance_info)

        except Exception as e:
            self.output_launcher_log(f"启动失败: {str(e)}")
            raise
