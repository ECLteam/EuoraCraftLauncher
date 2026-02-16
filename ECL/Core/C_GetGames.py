from typing import Callable, Optional, Dict, List
import requests
from . import C_Libs, C_Downloader
from ..logger import get_logger

logger = get_logger("get_games")

class GetGames:
    """获取游戏版本列表的类"""
    
    def __init__(self, api_url: C_Libs.ApiUrl | None = None, downloader: C_Downloader.Downloader | None = None):
        self.api_url = api_url if api_url else C_Libs.ApiUrl()
        self.downloader = downloader if downloader else C_Downloader.Downloader()
        self.output_log = self.__default_output_log

    @staticmethod
    def __default_output_log(log: str):
        logger.info(log)

    def set_output_log(self, output_function: Callable[[str], None]) -> None:
        self.output_log = output_function

    def set_api_url(self, api_url_dict: dict):
        self.api_url.update_from_dict(api_url_dict)

    def get_version_list(self) -> Optional[Dict]:
        """从远程 API 获取 Minecraft 版本列表"""
        url = f"{self.api_url.Meta}/mc/game/version_manifest.json"
        try:
            logger.debug(f"正在获取版本列表: {url}")
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"获取版本列表失败: {e}")
            return None