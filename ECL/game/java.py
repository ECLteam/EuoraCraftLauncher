import os
import re
import sys
import subprocess
import platform
from dataclasses import dataclass, field
from typing import List, Optional, Set, Dict
from pathlib import Path

from ..logger import get_logger

logger = get_logger("launcher")
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    import winreg
    IS_WINDOWS = True
except ImportError:
    IS_WINDOWS = False
    winreg = None


@dataclass
class JavaInfo:
    path: str 
    version: str      
    major_version: int  
    java_type: str    
    arch: str
    sources: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        self._unique_key = self._generate_unique_key()
    
    def _generate_unique_key(self) -> str:
        bin_dir = os.path.dirname(self.path)
        java_home = os.path.dirname(bin_dir)
        return f"{java_home.lower()}_{self.major_version}"
    
    def __str__(self):
        sources_str = ",".join(self.sources)
        return f"{self.java_type} {self.major_version} ({self.version}), {self.arch}, 来源:[{sources_str}], 路径: {self.path}"


class JavaDetector:
    COMMON_JAVA_PATHS = [
        r"C:\Program Files\Java",
        r"C:\Program Files (x86)\Java",
        r"C:\Program Files\Eclipse Adoptium",
        r"C:\Program Files\Microsoft",
        r"C:\Program Files\Amazon Corretto",
        r"C:\Program Files\Zulu",
        r"C:\Program Files\BellSoft\Liberica",
        r"C:\Program Files\JavaSoft",
        os.path.expanduser(r"~\AppData\Local\Packages\Microsoft.4297127D64EC6_8wekyb3d8bbwe\LocalCache\Local\runtime"),
        os.path.expanduser(r"~\AppData\Local\Programs\Eclipse Adoptium"),
    ]
    
    MC_JAVA_COMPATIBILITY = {
        (0, 11): [8],
        (12, 16): [8],
        (17, 20): [17],
        (20, 20): [21], 
        (21, 999): [21, 25, 17],
    }
    
    def __init__(self):
        self.java_list: List[JavaInfo] = []
        self._candidate_cache: Dict[str, tuple] = {} 
    
    def detect_all(self) -> List[JavaInfo]:
        logger.debug("开始扫描 Java...")
        
        if IS_WINDOWS:
            self._scan_registry()
        self._scan_environment()
        self._scan_common_directories()
        self._validate_and_deduplicate()
        self.java_list.sort(key=lambda x: x.major_version, reverse=True)
        
        logger.info(f"扫描完成，共找到 {len(self.java_list)} 个有效 Java")
        return self.java_list
    
    def _add_candidate(self, path: str, source: str):
        if not os.path.exists(path):
            return
            
        # 标准化路径
        normalized = os.path.normpath(os.path.abspath(path))
        
        bin_dir = os.path.dirname(normalized).lower()
        if bin_dir in self._candidate_cache:
            existing_path, existing_source = self._candidate_cache[bin_dir]
            if "javaw" in normalized.lower():
                self._candidate_cache[bin_dir] = (normalized, source)
        else:
            self._candidate_cache[bin_dir] = (normalized, source)
    
    def _scan_registry(self):
        if not IS_WINDOWS:
            return
            
        logger.debug("正在读取注册表...")
        
        registry_configs = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\JavaSoft\Java Runtime Environment", "JRE"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\JavaSoft\Java Development Kit", "JDK"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\JavaSoft\JDK", "JDK"),
        ]
        
        if platform.machine().endswith('64'):
            registry_configs.extend([
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\JavaSoft\Java Runtime Environment", "JRE"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\JavaSoft\Java Development Kit", "JDK"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\JavaSoft\JDK", "JDK"),
            ])
        
        for hkey, sub_path, java_type in registry_configs:
            try:
                with winreg.OpenKey(hkey, sub_path) as key:
                    index = 0
                    while True:
                        try:
                            version_name = winreg.EnumKey(key, index)
                            version_key_path = f"{sub_path}\\{version_name}"
                            
                            with winreg.OpenKey(hkey, version_key_path) as version_key:
                                try:
                                    java_home, _ = winreg.QueryValueEx(version_key, "JavaHome")
                                    if java_home and os.path.exists(java_home):
                                        javaw_path = os.path.join(java_home, "bin", "javaw.exe")
                                        java_path = os.path.join(java_home, "bin", "java.exe")
                                        
                                        target = javaw_path if os.path.exists(javaw_path) else java_path
                                        if os.path.exists(target):
                                            self._add_candidate(target, f"registry_{java_type}")
                                except (FileNotFoundError, OSError):
                                    pass
                            index += 1
                        except OSError:
                            break
            except FileNotFoundError:
                pass
            except Exception as e:
                logger.error(f"注册表读取错误: {e}")
    
    def _scan_environment(self):
        logger.debug("正在检查环境变量...")
        java_home = os.environ.get("JAVA_HOME")
        if java_home:
            for exe in ["javaw.exe", "java.exe"]:
                full = os.path.join(java_home, "bin", exe)
                if os.path.exists(full):
                    self._add_candidate(full, "env_java_home")
                    break
        path_env = os.environ.get("Path", "")
        for path_dir in path_env.split(os.pathsep):
            path_dir = path_dir.strip('"')
            if not path_dir:
                continue
            for exe in ["javaw.exe", "java.exe"]:
                full = os.path.join(path_dir, exe)
                if os.path.exists(full):
                    self._add_candidate(full, "env_path")
    
    def _scan_common_directories(self):
        logger.debug("正在扫描常见安装目录...")
        
        for base_path in self.COMMON_JAVA_PATHS:
            if not os.path.exists(base_path):
                continue
                
            try:
                for item in os.listdir(base_path):
                    item_path = os.path.join(base_path, item)
                    if not os.path.isdir(item_path):
                        continue
                    for exe in ["javaw.exe", "java.exe"]:
                        full = os.path.join(item_path, "bin", exe)
                        if os.path.exists(full):
                            self._add_candidate(full, "common_path")
                            break
                    
                    if any(x in base_path.lower() for x in ["microsoft", "runtime"]):
                        try:
                            for sub in os.listdir(item_path):
                                sub_path = os.path.join(item_path, sub)
                                if os.path.isdir(sub_path):
                                    for exe in ["javaw.exe", "java.exe"]:
                                        full = os.path.join(sub_path, "bin", exe)
                                        if os.path.exists(full):
                                            self._add_candidate(full, "common_path_deep")
                                            break
                        except (PermissionError, OSError):
                            pass
                            
            except (PermissionError, OSError):
                continue
    
    def _validate_and_deduplicate(self):
        logger.debug(f"发现 {len(self._candidate_cache)} 个唯一目录，开始验证...")
        
        validated: Dict[str, JavaInfo] = {}
        
        for path, source in self._candidate_cache.values():
            info = self._validate_java(path, source)
            if info:
                if info._unique_key in validated:
                    validated[info._unique_key].sources.extend(info.sources)
                else:
                    validated[info._unique_key] = info
        
        self.java_list = list(validated.values())
    
    def _validate_java(self, path: str, source: str) -> Optional[JavaInfo]:
        try:
            exec_path = path.replace("javaw.exe", "java.exe").replace("javaw", "java")
            
            result = subprocess.run(
                [exec_path, "-version"],
                capture_output=True,
                timeout=10,
                encoding='utf-8',
                errors='ignore'
            )
            
            output = result.stderr if result.stderr else result.stdout
            if not output:
                return None
            
            return self._parse_version_output(path, output, source, exec_path)
            
        except Exception:
            return None
    
    def _is_jdk(self, java_home: str, output: str) -> bool:
        if os.path.exists(os.path.join(java_home, "jmods")):
            return True
        if os.path.exists(os.path.join(java_home, "lib", "tools.jar")):
            return True
        if "jdk" in output.lower() or "development" in output.lower():
            return True
        return False
    
    def _parse_version_output(self, path: str, output: str, source: str, exec_path: str) -> Optional[JavaInfo]:
        try:
            # 提取版本号
            version_match = re.search(r'version\s+"(\d+[\.\d]*[_\+]?\d*)"', output, re.IGNORECASE)
            if not version_match:
                return None
            
            version_str = version_match.group(1)
            
            # 解析主版本号
            if version_str.startswith("1."):  # 1.8.0_xxx -> 8
                major = int(version_str.split(".")[1])
            else:
                major = int(version_str.split(".")[0])
            
            bin_dir = os.path.dirname(exec_path)
            java_home = os.path.dirname(bin_dir)
            
            java_type = "JDK" if self._is_jdk(java_home, output) else "JRE"
            
            # 判断架构
            arch = "64-bit"
            if any(x in output for x in ["32-Bit", "i586", "i686", "x86"]):
                arch = "32-bit"
            elif any(x in output for x in ["64-Bit", "amd64", "x86_64"]):
                arch = "64-bit"
            elif platform.machine().endswith('64'):
                arch = "64-bit" 
            
            return JavaInfo(
                path=path,
                version=version_str,
                major_version=major,
                java_type=java_type,
                arch=arch,
                sources=[source]
            )
            
        except Exception:
            return None
    
    def get_recommended_java(self, mc_version: str) -> Optional[JavaInfo]:
        if not self.java_list:
            return None
        
        try:
            # 解析 MC 版本号 1.20.1 -> 20（次要版本）
            parts = mc_version.split('.')
            if len(parts) < 2:
                return self.java_list[0]  # 默认最新
            
            major = int(parts[1])
            minor = int(parts[2]) if len(parts) > 2 else 0
            
            # 特殊处理 1.20.5+（需要 Java 21）
            if major == 20 and minor >= 5:
                required = [21, 25]  # 21 或更高
            elif major >= 21:
                required = [21, 25]
            elif major >= 17:
                required = [17]
            elif major >= 12:
                required = [8]  # 1.12-1.16 用 Java 8 最稳定
            else:
                required = [8]
            
            # 寻找匹配的 Java（优先完全匹配，其次更高版本）
            for req in required:
                for java in self.java_list:
                    if java.major_version == req:
                        return java
            
            logger.warning(f"未找到适合 MC {mc_version} 的 Java {required}，使用最新版本（可能不兼容！）")
            return self.java_list[0]
            
        except Exception:
            return self.java_list[0]

def get_java_list():
    detector = JavaDetector()
    java_list = detector.detect_all()
    
    if not java_list:
        return False
    else:
        return java_list


if __name__ == "__main__":
    get_java_list()
