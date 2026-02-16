from dataclasses import dataclass, fields, asdict
from pathlib import Path
from uuid import UUID
import hashlib
import zipfile
import json
import os
from typing import Optional, Tuple, Dict, Any

def name_to_path(name: str) -> Optional[str]:
    """将 Maven 格式的名称转换为文件路径"""
    at_index = name.find("@")
    suffix = "jar"
    if at_index != -1:
        suffix = name[at_index + 1:]
        name = name[0:at_index]
    
    parts = name.split(":")
    if len(parts) < 3:
        return None
        
    group_path = parts[0].replace('.', '/')
    artifact = parts[1]
    version = parts[2]
    
    if len(parts) == 4:
        classifier = parts[3]
        return f"{group_path}/{artifact}/{version}/{artifact}-{version}-{classifier}.{suffix}"
    
    return f"{group_path}/{artifact}/{version}/{artifact}-{version}.{suffix}"

def name_to_uuid(name: str) -> UUID:
    """将玩家昵称转换为离线模式 UUID"""
    return UUID(bytes=hashlib.md5(f"OfflinePlayer:{name}".encode("utf-8")).digest()[:16], version=3)

def is_uuid3(uuid_string: str) -> bool:
    """检测一个字符串是否为 UUID3 格式"""
    try:
        return UUID(uuid_string, version=3).version == 3
    except ValueError:
        return False

def unzip(zip_path: str | Path, unzip_path: str | Path) -> None:
    """解压文件函数，增加异常日志"""
    try:
        with zipfile.ZipFile(zip_path) as zip_object:
            zip_object.extractall(unzip_path)
    except (zipfile.BadZipFile, FileNotFoundError) as e:
        # 这里可以根据需要记录日志
        pass

def get_file_sha1(file_path: str | Path) -> str:
    """获取文件 Sha1，优化读取性能"""
    sha1 = hashlib.sha1()
    if os.path.isfile(file_path):
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                sha1.update(chunk)
    return sha1.hexdigest()

def find_version(version_json: Dict[str, Any], game_path: Path, current_version_name: str = None) -> Optional[Tuple[Dict[str, Any], Path]]:
    """寻找继承的原版游戏版本"""
    inherits_from = version_json.get("inheritsFrom")
    if not inherits_from:
        return None
        
    versions_dir = game_path / "versions"
    
    # 1. 优先检查当前版本文件夹（自包含模式）
    if current_version_name:
        local_json = versions_dir / current_version_name / f"{inherits_from}.json"
        if local_json.exists():
            try:
                return json.loads(local_json.read_text("utf-8")), versions_dir / current_version_name
            except Exception:
                pass

    if not versions_dir.exists():
        return None

    # 2. 检查独立的原版文件夹
    target_dir = versions_dir / inherits_from
    target_json = target_dir / f"{inherits_from}.json"
    if target_json.exists():
        try:
            return json.loads(target_json.read_text("utf-8")), target_dir
        except Exception:
            pass

    # 遍历查找 (针对目录名与 ID 不一致的情况)
    for version_path in versions_dir.iterdir():
        if not version_path.is_dir():
            continue
        game_json_path = version_path / f"{version_path.name}.json"
        if not game_json_path.is_file():
            continue
        try:
            game_json = json.loads(game_json_path.read_text("utf-8"))
            if game_json.get("id") == inherits_from:
                return game_json, version_path
        except Exception:
            continue
            
    return None

@dataclass
class ApiUrl:
    """Api 数据结构"""
    Meta: str = "https://launchermeta.mojang.com"
    Data: str = "https://launcher.mojang.com"
    Libraries: str = "https://libraries.minecraft.net"
    Assets: str = "https://resources.download.minecraft.net"
    Forge: str = "https://files.minecraftforge.net/maven"
    Fabric: str = "https://maven.fabricmc.net"
    FabricMeta: str = "https://meta.fabricmc.net"
    NeoForged: str = "https://maven.neoforged.net/releases"
    Quilt: str = "https://maven.quiltmc.org"
    QuiltMeta: str = "https://meta.quiltmc.org"

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, api_url_dict: Dict[str, str]) -> 'ApiUrl':
        valid_fields = {f.name for f in fields(cls)}
        kw = {k: v.strip("/") for k, v in api_url_dict.items() if k in valid_fields}
        return cls(**kw)

    def update_from_dict(self, api_url_dict: Dict[str, str]):
        valid_fields = {f.name for f in fields(self)}
        for k, v in api_url_dict.items():
            if k in valid_fields:
                setattr(self, k, v.strip("/"))
