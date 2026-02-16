from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List, Tuple, Optional, Union, Any
from pathlib import Path
import threading
import requests
import time
from ..logger import get_logger

logger = get_logger("downloader")

class Downloader:
    """下载器类，支持多线程下载和断点续传"""
    
    def __init__(self, max_retries: int = 3, chunk_size: int = 8192):
        self.download_status = True
        self.__download_total: List[Tuple[Any, str]] = []
        self.__download_done: List[str] = []
        self.output_progress = self.__default_output_progress
        self.output_log = self.__default_output_log
        self.lock = threading.Lock()
        self.max_retries = max_retries
        self.chunk_size = chunk_size

        # 配置requests会话
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Euora Craft Launcher"
        })

    def __default_output_progress(self, total_files: list, downloaded_files: list):
        with self.lock:
            total = len(total_files)
            done = len(downloaded_files)
            if total > 0:
                logger.info(f"下载进度: {done}/{total} ({done / total * 100:.1f}%)")

    @staticmethod
    def __default_output_log(log: str):
        logger.info(log)

    def set_output_progress(self, output_function: Callable[[list, list], None]) -> None:
        def safe_output(total: list, done: list):
            with self.lock:
                output_function(total, done)
        self.output_progress = safe_output

    def set_output_log(self, output_function: Callable[[str], None]) -> None:
        self.output_log = output_function

    def set_download_status(self, set_status: bool) -> None:
        with self.lock:
            self.download_status = set_status

    def __get_file_size(self, url: str) -> Optional[int]:
        """获取文件大小，支持重试"""
        for attempt in range(self.max_retries):
            try:
                response = self.session.head(url, timeout=10, allow_redirects=True)
                response.raise_for_status()
                content_length = response.headers.get("Content-Length")
                if content_length:
                    return int(content_length)

                response = self.session.get(url, stream=True, timeout=10)
                response.raise_for_status()
                content_length = response.headers.get("Content-Length")
                if content_length:
                    return int(content_length)
                return 0
            except requests.exceptions.RequestException as e:
                if attempt == self.max_retries - 1:
                    # 只有在所有重试都失败后才记录调试日志，避免 404 刷屏
                    logger.debug(f"获取文件大小失败 {url}: {str(e)}")
                    return None
                time.sleep(1)
        return None

    def __download_stream(self, url: str, file_path: Path, start_byte: int = 0) -> bool:
        """流式下载文件"""
        for attempt in range(self.max_retries):
            try:
                headers = {}
                if start_byte > 0:
                    headers["Range"] = f"bytes={start_byte}-"

                file_path.parent.mkdir(parents=True, exist_ok=True)

                with self.session.get(url, headers=headers, stream=True, timeout=30) as response:
                    response.raise_for_status()
                    if start_byte > 0 and response.status_code != 206:
                        return False

                    with file_path.open("ab" if start_byte > 0 else "wb") as f:
                        for chunk in response.iter_content(chunk_size=self.chunk_size):
                            with self.lock:
                                if not self.download_status:
                                    return False
                            if chunk:
                                f.write(chunk)
                    return True
            except requests.exceptions.RequestException:
                if attempt == self.max_retries - 1:
                    return False
                time.sleep(1)
            except IOError as e:
                logger.error(f"文件写入失败 {file_path}: {str(e)}")
                return False
        return False

    def __download_single_file(self, urls: Union[str, List[str]], save_path: str) -> bool:
        """下载单个文件，支持备用链接"""
        if isinstance(urls, str):
            urls = [urls]
            
        save_file_path = Path(save_path)
        temp_path = save_file_path.with_name(save_file_path.name + ".tmp")

        try:
            save_file_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"创建目录失败 {save_file_path.parent}: {str(e)}")
            return False

        for download_url in urls:
            if not download_url: continue
            
            file_size = self.__get_file_size(download_url)
            # 如果无法获取大小（可能是 404），尝试下一个链接
            if file_size is None:
                continue

            downloaded_size = 0
            if temp_path.exists():
                try:
                    downloaded_size = temp_path.stat().st_size
                    if downloaded_size >= file_size > 0:
                        temp_path.unlink(missing_ok=True)
                        downloaded_size = 0
                except Exception:
                    temp_path.unlink(missing_ok=True)
                    downloaded_size = 0

            if self.__download_stream(download_url, temp_path, downloaded_size):
                try:
                    final_size = temp_path.stat().st_size
                    if file_size > 0 and final_size != file_size:
                        continue # 大小不匹配，尝试下一个链接
                    
                    if save_file_path.exists():
                        save_file_path.unlink(missing_ok=True)
                    temp_path.rename(save_file_path)
                    return True
                except Exception:
                    continue
        
        return False

    def download_manager(self, download_list: List[Tuple[Union[str, List[str]], str]], max_threads: int) -> bool:
        """下载管理器"""
        if not download_list or max_threads <= 0:
            logger.warning("下载列表为空或线程数无效")
            return False

        logger.info(f"开始下载 {len(download_list)} 个文件，使用 {max_threads} 个线程")

        with self.lock:
            self.__download_total = download_list
            self.__download_done.clear()

        successful_downloads = 0
        try:
            with ThreadPoolExecutor(max_workers=max_threads) as executor:
                future_to_url = {
                    executor.submit(self.__download_single_file, urls, save_path): (urls, save_path)
                    for urls, save_path in self.__download_total
                }

                for future in as_completed(future_to_url):
                    urls, save_path = future_to_url[future]
                    try:
                        success = future.result()
                        if success:
                            with self.lock:
                                self.__download_done.append(save_path)
                                successful_downloads += 1
                            self.output_progress(self.__download_total, self.__download_done)
                        else:
                            logger.error(f"下载失败: {save_path}")
                    except Exception as e:
                        logger.error(f"任务执行异常: {str(e)}")
        except Exception as e:
            logger.error(f"下载管理器异常: {str(e)}")

        total_files = len(self.__download_total)
        logger.info(f"下载统计: {successful_downloads}/{total_files}")

        with self.lock:
            return successful_downloads == total_files
