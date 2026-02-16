import os
import sys
import webview
from ..logger import get_logger

logger = get_logger("ui")

def rp(rel):
    """获取资源文件的绝对路径，兼容 PyInstaller"""
    return os.path.join(getattr(sys, '_MEIPASS', os.path.abspath('.')), rel)

class Api:
    """供前端调用的 JS API"""
    def __init__(self):
        pass

    def minimize_window(self):
        if webview.windows:
            webview.windows[0].minimize()
        
    def close_window(self):
        if webview.windows:
            webview.windows[0].destroy()

def on_closed():
    logger.info("窗口已关闭")
    
def on_loaded():
    logger.info("窗口已加载完成")
    if webview.windows:
        webview.windows[0].show()

def run_ui(config=None, debug=False):
    """启动 UI 界面"""
    ui_config = config[0].get("ui", {}) if config else {}
    width = ui_config.get("width", 1000)
    height = ui_config.get("height", 700)
    title = ui_config.get("title", "EuoraCraft Launcher")
    
    api = Api()
    
    # 注意：这里路径需要根据 ECL/ui/ui.py 的位置调整
    # 如果 dist 还在根目录的 ui/dist，则路径为 ../../ui/dist/index.html
    # 如果 dist 也会移动到 ECL/ui/dist，则路径为 ./dist/index.html
    # 目前假设 dist 仍在原位置 ui/dist
    html_path = rp('ui/dist/index.html')
    
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