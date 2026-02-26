import sys
import logging
import re
import shlex
import threading
import webbrowser
import time
import json
import os
import select
import socket
import subprocess
import base64
import ctypes
import warnings
import atexit
import asyncio
try:
    from urllib3.exceptions import InsecureRequestWarning
    warnings.simplefilter('ignore', InsecureRequestWarning)
except ImportError:
    pass

import flet as ft

# ---------------------------------------------------------------------
# 兼容性补丁: 修复部分 Flet 版本缺少 ft.colors 的问题
# ---------------------------------------------------------------------
try:
    ft.colors
except AttributeError:
    class _ColorsPatch:
        # Material 3 Color Roles
        SURFACE_VARIANT = "surfaceVariant"
        SURFACE = "surface"
        OUTLINE = "outline"
        
        # Standard Colors
        GREEN = "green"
        GREY = "grey"
        BLACK = "black"
        RED = "red"
        BLUE = "blue"
        WHITE = "white"
        TRANSPARENT = "transparent"
        AMBER = "amber"
        
        @staticmethod
        def with_opacity(opacity: float, color: str):
            # 简易实现，仅支持 BLACK 的透明度处理，因为代码中只用到了 black
            if str(color).lower() == "black":
                alpha = int(opacity * 255)
                return f"#{alpha:02x}000000"
            return color 
            
    ft.colors = _ColorsPatch
# ---------------------------------------------------------------------

# 检查程序是否被打包成EXE
def is_frozen():
    return getattr(sys, 'frozen', False)

def _pip_install(pkgs):
    # 如果是打包后的EXE，直接返回False，绝对不能运行pip
    if is_frozen():
        print(f"打包环境下无法安装依赖: {pkgs}，请确保构建时已包含。")
        return False
    try:
        print(f"需要安装依赖包: {', '.join(pkgs)}")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', *pkgs])
        return True
    except Exception as e:
        print(f"安装失败: {e}")
        return False

def _win_dpapi_encrypt(plaintext):
    try:
        if not isinstance(plaintext, (bytes, bytearray)):
            plaintext = str(plaintext).encode('utf-8')
        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", ctypes.c_uint), ("pbData", ctypes.c_void_p)]
        CryptProtectData = ctypes.windll.crypt32.CryptProtectData
        CryptProtectData.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.c_wchar_p, ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(DATA_BLOB)]
        CryptProtectData.restype = ctypes.c_bool
        in_blob = DATA_BLOB(len(plaintext), ctypes.cast(ctypes.create_string_buffer(plaintext), ctypes.c_void_p))
        out_blob = DATA_BLOB()
        ok = CryptProtectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob))
        if not ok:
            return None
        buf = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)
        return "enc:" + base64.b64encode(buf).decode('ascii')
    except Exception:
        return None

def _win_dpapi_decrypt(ciphertext):
    try:
        if not isinstance(ciphertext, str):
            return None
        if not ciphertext.startswith("enc:"):
            return None
        raw = base64.b64decode(ciphertext[4:])
        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", ctypes.c_uint), ("pbData", ctypes.c_void_p)]
        CryptUnprotectData = ctypes.windll.crypt32.CryptUnprotectData
        CryptUnprotectData.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.POINTER(ctypes.c_wchar_p), ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(DATA_BLOB)]
        CryptUnprotectData.restype = ctypes.c_bool
        in_blob = DATA_BLOB(len(raw), ctypes.cast(ctypes.create_string_buffer(raw), ctypes.c_void_p))
        out_blob = DATA_BLOB()
        desc = ctypes.c_wchar_p()
        ok = CryptUnprotectData(ctypes.byref(in_blob), ctypes.byref(desc), None, None, None, 0, ctypes.byref(out_blob))
        if not ok:
            return None
        buf = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)
        try:
            return buf.decode('utf-8')
        except Exception:
            return buf.decode('utf-8', errors='ignore')
    except Exception:
        return None


def _install_asyncio_shutdown_silencer():
    try:
        import asyncio.base_events as _be
    except Exception:
        return

    if getattr(_be, "_ssh_pf_asyncio_silenced", False):
        return

    original = _be.BaseEventLoop.call_exception_handler

    def _patched(self, context):
        exc = context.get("exception")
        msg = context.get("message", "")
        text = ""
        if exc is not None:
            text = str(exc)
        if msg:
            text = text + " " + str(msg)
        lower_text = text.lower()
        if "cannot schedule new futures" in lower_text and "shutdown" in lower_text:
            return
        return original(self, context)

    _be.BaseEventLoop.call_exception_handler = _patched
    _be._ssh_pf_asyncio_silenced = True

warnings.filterwarnings('ignore', message='.*TripleDES has been moved.*')
try:
    import paramiko
except ImportError:
    if not is_frozen() and _pip_install(['paramiko>=2.7.0']):
        import paramiko
    else:
        raise

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException, ElementClickInterceptedException
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

# 确保 pyperclip 可用
try:
    import pyperclip
except ImportError:
    if not is_frozen() and _pip_install(['pyperclip']):
        import pyperclip
    else:
        pyperclip = None

# 信号模拟类
class Signal:
    def __init__(self, callback=None):
        self.callback = callback
    def connect(self, callback):
        self.callback = callback
    def emit(self, *args):
        if self.callback:
            self.callback(*args)

class FletSSHPortForwarder:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "AutoDL 一键连接"
        self.page.theme = ft.Theme(font_family="DengXian")
        
        # --- 【修改点：拦截关闭信号】 ---
        self.page.window_prevent_close = True
        self.page.on_window_event = self._on_window_event
        
        self.save_window_timer = None
        # 初始化快照，给定默认值，防止用户打开后从未移动过窗口就关闭
        self._window_snapshot = {
            "maximized": False,
            "minimized": False,
            "top": 100,
            "left": 100,
            "width": 1100,
            "height": 850
        }
        # ---------------------------
        
        # --- 【修改点 1：绑定窗口事件监听】 ---
        # 监听窗口的移动和大小改变事件，实现实时保存
        self.page.on_window_event = self._on_window_event
        # -----------------------------------

        # 状态初始化
        self.ssh_client = None
        self.forward_thread = None
        self.is_connected = False
        self.stop_event = threading.Event()
        self.client_threads = []
        self.server_socket = None
        self.is_connecting = False
        self.reconnecting = False
        self._last_connect_args = None
        self.refreshing = False
        self.port_forwarding_setup = False
        self.autodl_refresh_lock = threading.Lock()
        self.autodl_busy = False
        self._renew_cancel = False
        self.last_auto_refresh_time = 0
        
        self.running = True
        
        # AutoDL相关初始化
        self.autodl_driver = None
        self.is_autodl_initializing = False  # 增加初始化标志位
        self.is_autodl_logged_in = False
        # 配置目录
        base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        self.portable_base_dir = base_dir
        self.config_dir = os.path.join(self.portable_base_dir, 'configs')
        self._init_config_directory()
        self.current_theme = 'light'
        self._load_theme_pref()
        self.await_running_device_id = None
        self.await_running_remark = None
        self.await_running_deadline = None
        self.last_device_hash = None
        self.encryption_enabled = False
        self._load_encryption_pref()
        self.encryption_prompted = False
        self._load_encryption_prompted()
        self.autodl_config_dir = self.config_dir
        self.autodl_credentials_file = os.path.join(self.config_dir, 'autodl_credentials.json')
        
        # 初始化日志文件记录
        self._init_file_logging()
        
        self._migrate_autodl_configs_to_unified()
        self._cleanup_old_sessions()
        self.device_map_file = os.path.join(self.config_dir, 'device_map.json')
        self.readme_path = self._ensure_readme_file()
        
        # 信号
        self.update_status_signal = Signal()
        self.connection_status_signal = Signal()
        self.autodl_status_signal = Signal()
        self.autodl_login_signal = Signal()
        self.update_device_table_signal = Signal()
        
        # 窗口位置记忆文件
        self.window_settings_file = os.path.join(self.config_dir, 'window_settings.json')
        
        # UI 构建
        self.setup_ui()
        
        # 连接信号
        self.update_status_signal.connect(self.update_status)
        self.connection_status_signal.connect(self.update_connection_status)
        self.autodl_status_signal.connect(self.update_autodl_status)
        self.autodl_login_signal.connect(self.update_autodl_login_status)
        self.update_device_table_signal.connect(self.update_device_table)
        
        # 加载配置
        self.load_config_list()
        self.load_autodl_credentials()
        self.apply_theme()
        
        # 如果自动登录选中，尝试登录
        if SELENIUM_AVAILABLE and self.auto_login_checkbox.value:
            threading.Timer(0.1, lambda: self.autodl_login(None)).start()
        
        self.update_delete_button_state()
        self._start_background_tasks()
        print("程序初始化完成")

    def _init_config_directory(self):
        """初始化配置目录"""
        try:
            if not os.path.exists(self.config_dir):
                os.makedirs(self.config_dir, exist_ok=True)
                self.update_status(f'配置目录已创建: {self.config_dir}')
        except PermissionError as e:
            self.update_status(f'权限不足: 无法创建程序目录的配置文件 ({str(e)})，已回退到用户目录')
            self.config_dir = os.path.join(os.path.expanduser('~'), '.ssh_port_forwarder', 'configs')
            try:
                os.makedirs(self.config_dir, exist_ok=True)
                self.update_status(f'已使用用户目录: {self.config_dir}')
            except Exception as e2:
                self.update_status(f'严重警告: 无法创建用户目录配置: {str(e2)}')
                self.config_dir = None
        except Exception as e:
            self.update_status(f'警告: 创建配置目录出错: {str(e)}，尝试使用用户目录')
            self.config_dir = os.path.join(os.path.expanduser('~'), '.ssh_port_forwarder', 'configs')
            try:
                os.makedirs(self.config_dir, exist_ok=True)
                self.update_status(f'已使用用户目录: {self.config_dir}')
            except Exception as e2:
                self.update_status(f'严重警告: 无法创建用户目录配置: {str(e2)}')
                self.config_dir = None

    def _migrate_autodl_configs_to_unified(self):
        try:
            old_dir = os.path.join(self.portable_base_dir, 'autodl_configs')
            if os.path.isdir(old_dir):
                # 迁移 credentials.json
                try:
                    name = 'credentials.json'
                    src = os.path.join(old_dir, name)
                    if os.path.exists(src):
                        dst = os.path.join(self.config_dir, 'autodl_credentials.json')
                        if not os.path.exists(dst):
                            os.makedirs(self.config_dir, exist_ok=True)
                            import shutil
                            shutil.copyfile(src, dst)
                            self.update_status('已迁移 credentials.json 到统一配置目录')
                        else:
                            pass
                except Exception:
                    pass
                
                # 迁移 cookies.json
                try:
                    name = 'cookies.json'
                    src = os.path.join(old_dir, name)
                    if os.path.exists(src):
                        dst = os.path.join(self.config_dir, 'autodl_cookies.json')
                        if not os.path.exists(dst):
                            os.makedirs(self.config_dir, exist_ok=True)
                            import shutil
                            shutil.copyfile(src, dst)
                            self.update_status('已迁移 cookies.json 到统一配置目录')
                except Exception:
                    pass
        except Exception:
            pass

    def _get_readme_source_path(self):
        try:
            base = getattr(sys, '_MEIPASS', None)
            if base:
                p = os.path.join(base, 'README.md')
                if os.path.exists(p):
                    return p
        except Exception:
            pass
        try:
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'README.md')
            if os.path.exists(p):
                return p
        except Exception:
            pass
        return None

    def _ensure_readme_file(self):
        try:
            target = os.path.join(self.portable_base_dir, 'README.md')
            if os.path.exists(target):
                return target
            
            def copy_readme_async():
                try:
                    src = self._get_readme_source_path()
                    if src and os.path.exists(src):
                        import shutil
                        try:
                            shutil.copyfile(src, target)
                        except Exception:
                            pass
                    if not os.path.exists(target):
                        try:
                            with open(target, 'w', encoding='utf-8') as f:
                                f.write('AutoDL 一键连接使用说明\n\n- 在左侧填写 SSH 信息与端口后保存配置\n- 点击连接按钮建立端口转发\n- 问号按钮打开本说明文件\n')
                        except Exception:
                            pass
                except Exception:
                    pass
            
            t = threading.Thread(target=copy_readme_async, daemon=True)
            t.start()
            
            return target
        except Exception:
            return os.path.join(self.portable_base_dir, 'README.md')

    def _encryption_pref_path(self):
        try:
            return os.path.join(self.config_dir or self.portable_base_dir, 'encryption_enabled.flag')
        except Exception:
            return os.path.join(self.portable_base_dir, 'encryption_enabled.flag')

    def _load_encryption_pref(self):
        try:
            p = self._encryption_pref_path()
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as f:
                    v = f.read().strip()
                    self.encryption_enabled = (v == '1')
        except Exception:
            pass

    def _set_encryption_pref(self, enabled):
        try:
            self.encryption_enabled = bool(enabled)
            p = self._encryption_pref_path()
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'w', encoding='utf-8') as f:
                f.write('1' if self.encryption_enabled else '0')
        except Exception:
            pass

    def _encryption_prompted_path(self):
        try:
            return os.path.join(self.config_dir or self.portable_base_dir, 'encryption_prompted.flag')
        except Exception:
            return os.path.join(self.portable_base_dir, 'encryption_prompted.flag')

    def _load_encryption_prompted(self):
        try:
            p = self._encryption_prompted_path()
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as f:
                    v = f.read().strip()
                    self.encryption_prompted = (v == '1')
        except Exception:
            pass

    def _set_encryption_prompted(self, prompted):
        try:
            self.encryption_prompted = bool(prompted)
            p = self._encryption_prompted_path()
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, 'w', encoding='utf-8') as f:
                f.write('1' if self.encryption_prompted else '0')
        except Exception:
            pass

    def _theme_pref_path(self):
        try:
            return os.path.join(self.config_dir or self.portable_base_dir, 'theme.pref')
        except Exception:
            return os.path.join(self.portable_base_dir, 'theme.pref')

    def _load_theme_pref(self):
        try:
            p = self._theme_pref_path()
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as f:
                    self.current_theme = f.read().strip()
        except Exception:
            pass

    def _save_theme_pref(self):
        try:
            p = self._theme_pref_path()
            with open(p, 'w', encoding='utf-8') as f:
                f.write(self.current_theme)
        except Exception:
            pass

    def _migrate_autodl_configs_to_unified(self):
        # ... (existing code omitted, not modifying this function)
        pass

    def _cleanup_old_sessions(self):
        """清理残留的临时文件和目录"""
        try:
            if not self.config_dir or not os.path.exists(self.config_dir):
                return
            import shutil
            # 1. 清理 chrometmp- 开头的临时目录
            for name in os.listdir(self.config_dir):
                path = os.path.join(self.config_dir, name)
                if name.startswith('chrometmp-') and os.path.isdir(path):
                    try:
                        shutil.rmtree(path, ignore_errors=True)
                    except Exception:
                        pass
            
            # 2. 清理旧的 chromedriver.exe (如果存在且不是配置指定的)
            # 注意：这里只清理显然是临时残留的，或者 size 异常小的
            local_driver = os.path.join(self.config_dir, 'chromedriver.exe')
            if os.path.exists(local_driver):
                try:
                    # 如果文件太小(小于1MB)可能是下载失败的残留
                    if os.path.getsize(local_driver) < 1024 * 1024:
                        os.remove(local_driver)
                except Exception:
                    pass
        except Exception:
            pass

    def _start_background_tasks(self):
        def refresh_time_loop():
            while self.running:
                time.sleep(1)
                self._update_refresh_time_label()
        threading.Thread(target=refresh_time_loop, daemon=True).start()
        
        def auto_refresh_loop():
            while self.running:
                interval = 1.5 if self.await_running_device_id else 10
                time.sleep(interval)
                self._auto_refresh_tick()
        threading.Thread(target=auto_refresh_loop, daemon=True).start()

    # --- 【修改点 2：新增窗口事件处理函数】 ---
    def _get_page_attr(self, name, default=None):
        """安全获取 Page 属性，兼容不同版本的 Flet 命名差异"""
        try:
            if hasattr(self.page, name):
                return getattr(self.page, name)
            elif hasattr(self.page, "window"):
                # 兼容 page.window.xxx 格式
                return getattr(self.page.window, name.replace("window_", ""), default)
            return default
        except Exception:
            return default

    def _take_window_snapshot(self):
        """
        仅在窗口状态健康时更新快照
        """
        try:
            # 安全获取属性，兼容不同版本的 Flet
            w_top = self._get_page_attr("window_top")
            w_left = self._get_page_attr("window_left")
            w_width = self._get_page_attr("window_width")
            w_height = self._get_page_attr("window_height")
            w_maximized = self._get_page_attr("window_maximized", False)
            w_minimized = self._get_page_attr("window_minimized", False)

            # 如果 Flet 对象已经销毁，或者核心位置属性为 None，直接放弃更新
            if not self.page or w_top is None:
                return

            # 如果是最小化状态，绝对不要更新坐标，保留上一次的快照
            if w_minimized:
                self._window_snapshot["minimized"] = True
                return

            # 更新最大化状态
            self._window_snapshot["maximized"] = w_maximized

            # 如果不是最大化，必须更新精确坐标
            if not w_maximized:
                # 过滤非法坐标 (Windows 贴边可能会出现负值，但在合理范围内，排除极值即可)
                if w_left is not None and w_top is not None:
                    if w_left > -10000 and w_top > -10000:
                        self._window_snapshot["top"] = w_top
                        self._window_snapshot["left"] = w_left
                        self._window_snapshot["width"] = w_width
                        self._window_snapshot["height"] = w_height
                    
            self._window_snapshot["minimized"] = False
            
        except Exception:
            pass

    def _on_window_event(self, e):
        """
        核心逻辑：
        1. 移动/调整大小时 -> 疯狂更新快照 (记录正确值)
        2. 关闭时 -> 只负责写入硬盘 (使用最后一次正确的快照)，绝对不读当前值
        """
        # --- 情况 A: 窗口关闭 ---
        if e.data == "close":
            # 【重点】这里删除了 self._take_window_snapshot()
            # 直接保存最后一次已知的正确状态
            self._save_window_settings()
            self.page.window_destroy()
            return

        # --- 情况 B: 窗口状态改变 (移动、缩放) ---
        if e.data in ["move", "resize", "maximize", "unmaximize", "restore"]:
            # 只有在这里，窗口还活着的时候，才去读取并更新快照
            self._take_window_snapshot()
            
            if self.save_window_timer:
                self.save_window_timer.cancel()
            
            # 防抖保存 (避免拖拽时频繁写入硬盘)
            self.save_window_timer = threading.Timer(0.4, self._save_window_settings)
            self.save_window_timer.start()

    def _save_window_settings(self):
        """保存窗口状态"""
        # 使用快照数据进行落盘
        st = self._window_snapshot
        if not st:
            return
            
        # 1. 最小化时绝对不保存，防止捕获到系统隐藏坐标（如 -32000）
        if st.get("minimized"):
            return
            
        try:
            os.makedirs(os.path.dirname(self.window_settings_file), exist_ok=True)

            current_settings = {}
            if os.path.exists(self.window_settings_file):
                try:
                    with open(self.window_settings_file, 'r', encoding='utf-8') as f:
                        current_settings = json.load(f)
                except Exception:
                    pass

            # 2. 最大化逻辑分离：最大化时不覆盖坐标，只更新标记
            is_maximized = st.get("maximized", False)
            
            if is_maximized:
                current_settings["maximized"] = True
            else:
                current_settings["maximized"] = False
                width = st.get("width")
                height = st.get("height")
                top = st.get("top")
                left = st.get("left")

                # 3. 正常尺寸才保存坐标，并确保非负（规避污染）
                if width and width > 100 and height and height > 100:
                    current_settings["width"] = width
                    current_settings["height"] = height
                    if top is not None: current_settings["top"] = max(0, top)
                    if left is not None: current_settings["left"] = max(0, left)

            with open(self.window_settings_file, 'w', encoding='utf-8') as f:
                json.dump(current_settings, f, ensure_ascii=False, indent=2)
        except Exception:
            logging.exception("save window settings failed")

    def _set_page_attr(self, name, value):
        """安全设置 Page 属性，处理不同版本的 Flet 命名差异"""
        try:
            if hasattr(self.page, name):
                setattr(self.page, name, value)
            elif hasattr(self.page, "window") and hasattr(self.page.window, name.replace("window_", "")):
                # 兼容 page.window.xxx 格式
                setattr(self.page.window, name.replace("window_", ""), value)
        except Exception:
            pass

    def _load_window_settings(self):
        """加载窗口设置"""
        try:
            if os.path.exists(self.window_settings_file):
                with open(self.window_settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    
                    # 1. 恢复宽高
                    w = settings.get("width", 1100)
                    h = settings.get("height", 850)
                    if w > 100: self._set_page_attr("window_width", w)
                    if h > 100: self._set_page_attr("window_height", h)
                    
                    # 2. 恢复位置（增加非负校验，防止飞出屏幕）
                    t = settings.get("top")
                    l = settings.get("left")
                    if t is not None and t >= 0:
                        self._set_page_attr("window_top", t)
                    else:
                        self._set_page_attr("window_top", 100) # 兜底坐标
                        
                    if l is not None and l >= 0:
                        self._set_page_attr("window_left", l)
                    else:
                        self._set_page_attr("window_left", 100) # 兜底坐标
                        
                    # 3. 恢复最大化状态 (此处保留逻辑，但会被下方的强制全屏覆盖)
                    if settings.get("maximized", False):
                        self._set_page_attr("window_maximized", True)
            else:
                # 首次运行默认值
                self._set_page_attr("window_width", 1100)
                self._set_page_attr("window_height", 850)
                self._set_page_attr("window_top", 100)
                self._set_page_attr("window_left", 100)
            
            # --- 【强制指令：每次启动默认全屏】 ---
            self._set_page_attr("window_maximized", True)
            # ------------------------------------
            
            # --- 【新增代码：加载完立即同步到快照】 ---
            # 这一步非常关键！确保如果用户打开APP后不移动直接关闭，保存的数据也是正确的
            # 使用 _get_page_attr 安全获取属性，兼容不同版本的 Flet
            self._window_snapshot = {
                "maximized": self._get_page_attr("window_maximized", False),
                "minimized": self._get_page_attr("window_minimized", False),
                "top": self._get_page_attr("window_top", 100),
                "left": self._get_page_attr("window_left", 100),
                "width": self._get_page_attr("window_width", 1100),
                "height": self._get_page_attr("window_height", 850)
            }
            # ----------------------------------------
        except Exception:
            logging.exception("load window settings failed")
    # ----------------------------------------

    def setup_ui(self):
        # 加载并应用窗口设置
        self._load_window_settings()
        
        # 标题栏
        self.title_text = ft.Text("AutoDL 一键连接", size=20, weight=ft.FontWeight.BOLD)
        self.theme_button = ft.IconButton(icon=ft.Icons.DARK_MODE, on_click=self.toggle_theme)
        self.help_button = ft.IconButton(icon=ft.Icons.HELP_OUTLINE, on_click=self.open_readme)
        title_bar = ft.Row(
            controls=[
                self.title_text,
                ft.Container(expand=True),
                self.theme_button,
                self.help_button,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        title_container = ft.Container(
            content=title_bar,
            padding=ft.padding.symmetric(vertical=10, horizontal=14),
            bgcolor=ft.colors.SURFACE_VARIANT,
            border=ft.border.all(1, ft.colors.OUTLINE),
            border_radius=10,
        )
        
        # 右侧面板
        self.status_label = ft.Text("状态: 未连接", size=13, weight=ft.FontWeight.BOLD)
        self.log_listview = ft.ListView(expand=True, spacing=5, auto_scroll=True)
        
        # 任务状态栏（续费等长任务时显示）
        self._task_spinner = ft.ProgressRing(width=16, height=16, stroke_width=2)
        self._task_status_text = ft.Text("", size=12)
        self._task_cancel_btn = ft.TextButton("取消", on_click=self._on_renew_cancel, style=ft.ButtonStyle(color="red"))
        self._task_bar = ft.Container(
            content=ft.Row(
                controls=[self._task_spinner, self._task_status_text, self._task_cancel_btn],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            visible=False,
            padding=ft.padding.symmetric(vertical=4),
        )
        
        self.config_combo = ft.Dropdown(
            label="备用连接",
            options=[],
            expand=True,
            on_change=self.on_config_combo_change,
        )
        self.save_config_button = ft.ElevatedButton("保存", on_click=self.save_config)
        self.delete_config_button = ft.ElevatedButton("删除", on_click=self.delete_config)
        self.delete_all_button = ft.ElevatedButton("删除全部", on_click=self.delete_all_configs)
        config_row = ft.Row(
            controls=[
                ft.Text("备用连接", weight=ft.FontWeight.BOLD, width=80),
                self.config_combo,
                self.save_config_button,
                self.delete_config_button,
                self.delete_all_button,
            ],
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
        )
        
        self.ssh_info_input = ft.TextField(
            label="ssh -p 端口 用户名@主机地址",
            expand=True,
            on_change=self.auto_parse_ssh_info,
        )
        self.remote_port_input = ft.TextField(
            width=120,
            content_padding=10,
            text_size=14,
        )
        self.password_input = ft.TextField(
            label="SSH 密码",
            password=True,
            can_reveal_password=False,
            expand=True,
        )
        self.show_password_checkbox = ft.Checkbox(
            label="显示",
            on_change=self.toggle_password_visibility,
        )
        password_row = ft.Row(
            controls=[self.password_input, self.show_password_checkbox],
            spacing=10,
            expand=True,
        )
        self.auto_open_browser_checkbox = ft.Checkbox(
            label="连接成功后自动打开浏览器",
            value=True,
        )
        
        self.connect_button = ft.ElevatedButton("连接", on_click=self.toggle_connection)
        self.disconnect_button = ft.ElevatedButton("断开", on_click=self.disconnect, disabled=True)
        buttons_row = ft.Row(
            controls=[self.connect_button, self.disconnect_button],
            spacing=10,
        )
        
        right_column = ft.Column(
            controls=[
                self.status_label,
                ft.Container(content=self.log_listview, height=200, expand=True),
                self._task_bar,
                ft.Divider(),
                config_row,
                ft.Column(
                    controls=[
                        ft.Row([ft.Text("SSH 连接", width=80, weight=ft.FontWeight.BOLD), self.ssh_info_input]),
                        ft.Row([ft.Text("远程端口", width=80, weight=ft.FontWeight.BOLD), self.remote_port_input]),
                        ft.Row([ft.Text("密码", width=80, weight=ft.FontWeight.BOLD), password_row]),
                        self.auto_open_browser_checkbox,
                    ],
                    spacing=10,
                ),
                ft.Divider(),
                buttons_row,
            ],
            spacing=10,
            expand=True,
        )
        
        # 左侧面板 (AutoDL)
        autodl_title = ft.Text("AutoDL 设备管理", size=16, weight=ft.FontWeight.BOLD)
        self.autodl_status_label = ft.Text("未登录", size=12, color=ft.colors.GREY)
        self._login_collapse_btn = ft.IconButton(
            icon=ft.Icons.EXPAND_LESS,
            tooltip="折叠登录区",
            icon_size=18,
            on_click=self._toggle_login_area,
        )
        title_status_row = ft.Row(
            controls=[autodl_title, self._login_collapse_btn, ft.Container(expand=True), self.autodl_status_label],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        
        self.autodl_username_input = ft.TextField(label="AutoDL用户名", expand=True)
        self.autodl_password_input = ft.TextField(label="密码", password=True, can_reveal_password=False, expand=True)
        self.remember_password_checkbox = ft.Checkbox(label="记住密码")
        self.show_autodl_password_checkbox = ft.Checkbox(label="显示密码", on_change=self.toggle_autodl_password_visibility)
        self.auto_login_checkbox = ft.Checkbox(label="启动时自动登录")
        self.silent_refresh_checkbox = ft.Checkbox(label="静默自动刷新日志")
        self.visible_radio = ft.Radio(value="visible", label="可视浏览器")
        self.headless_radio = ft.Radio(value="headless", label="静默模式")
        self.browser_mode_group = ft.RadioGroup(
            content=ft.Row([self.visible_radio, self.headless_radio]),
            value="visible",
            on_change=self._persist_login_prefs,
        )
        self.autodl_login_button = ft.ElevatedButton("登录", on_click=lambda e: self.autodl_login(None))
        self.autodl_logout_button = ft.ElevatedButton("登出", on_click=self.autodl_logout, disabled=True)
        
        login_row1 = ft.Row(
            controls=[self.autodl_username_input, self.autodl_password_input, self.autodl_login_button, self.autodl_logout_button],
            spacing=10,
        )
        login_row2 = ft.Row(
            controls=[
                self.remember_password_checkbox,
                self.show_autodl_password_checkbox,
                self.auto_login_checkbox,
                self.silent_refresh_checkbox,
                self.browser_mode_group,
            ],
            spacing=10,
        )
        self._login_area = ft.Column(controls=[login_row1, login_row2], spacing=5, visible=True)
        
        self.autodl_devices_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("备注")),
                ft.DataColumn(ft.Text("设备名称")),
                ft.DataColumn(ft.Text("状态")),
                ft.DataColumn(ft.Text("规格")),
                ft.DataColumn(ft.Text("释放时间")),
                ft.DataColumn(ft.Text("操作")),
            ],
            rows=[],
            column_spacing=20,
        )
        table_container = ft.Container(
            content=ft.Column([self.autodl_devices_table], scroll=ft.ScrollMode.AUTO),
            expand=True,
            border=ft.border.all(1, ft.colors.OUTLINE),
            border_radius=5,
        )
        
        self.autodl_refresh_button = ft.ElevatedButton("刷新并检测GPU", on_click=self.autodl_refresh_devices, disabled=True)
        open_list_btn = ft.ElevatedButton("打开设备列表网页", on_click=lambda e: webbrowser.open('https://www.autodl.com/console/instance/list'))
        self.autodl_renew_button = ft.ElevatedButton("一键续费", on_click=self._on_renew_click, disabled=True, tooltip="逐台开机再关机，防止机器被销毁")
        self.autodl_shutdown_all_button = ft.ElevatedButton("一键关机", on_click=self._on_shutdown_all_click, disabled=True, tooltip="关闭所有运行中的设备")
        batch_row = ft.Row(
            controls=[self.autodl_refresh_button, open_list_btn, self.autodl_renew_button, self.autodl_shutdown_all_button],
            spacing=10,
        )
        
        left_column = ft.Column(
            controls=[
                title_status_row,
                self._login_area,
                table_container,
                batch_row,
            ],
            spacing=10,
            expand=True,
        )
        
        body = ft.Row(
            controls=[
                ft.Container(
                    content=left_column,
                    expand=2,
                    padding=10,
                    border_radius=10,
                    border=ft.border.all(1, ft.colors.OUTLINE),
                    bgcolor=ft.colors.SURFACE_VARIANT
                ),
                ft.Container(
                    content=right_column,
                    expand=1,
                    padding=10,
                    border_radius=10,
                    border=ft.border.all(1, ft.colors.OUTLINE),
                    bgcolor=ft.colors.SURFACE_VARIANT
                ),
            ],
            expand=True,
            spacing=10,
        )
        
        self.root = ft.Container(
            content=ft.Column(
                controls=[
                    title_container,
                    body,
                ],
                expand=True,
            ),
            bgcolor=ft.colors.SURFACE,
            border_radius=12,
            shadow=ft.BoxShadow(blur_radius=28, color=ft.colors.with_opacity(0.6, ft.colors.BLACK), offset=ft.Offset(0, 8)),
            expand=True,
        )
        
        # 绑定偏好保存
        self.remember_password_checkbox.on_change = self._persist_login_prefs
        self.show_autodl_password_checkbox.on_change = self._on_show_password_change
        self.auto_login_checkbox.on_change = self._persist_login_prefs
        self.silent_refresh_checkbox.on_change = self._persist_login_prefs
        self.browser_mode_group.on_change = self._persist_login_prefs

        # Add root container to page
        self.page.add(self.root)


    # ---------- UI 更新 ----------
    def _on_show_password_change(self, e):
        self.autodl_password_input.password = not self.show_autodl_password_checkbox.value
        self.autodl_password_input.update()
        self._persist_login_prefs(e)

    def _toggle_login_area(self, e=None):
        """折叠/展开登录区域"""
        collapsed = self._login_area.visible
        self._login_area.visible = not collapsed
        self._login_collapse_btn.icon = ft.Icons.EXPAND_MORE if collapsed else ft.Icons.EXPAND_LESS
        self._login_collapse_btn.tooltip = "展开登录区" if collapsed else "折叠登录区"
        self.safe_update()
        self._persist_login_prefs()

    def _init_file_logging(self):
        """初始化不覆盖的本地日志记录"""
        try:
            log_dir = os.path.join(self.config_dir, 'logs')
            os.makedirs(log_dir, exist_ok=True)
            log_filename = f"log_{time.strftime('%Y%m%d')}.txt"
            self.log_file_path = os.path.join(log_dir, log_filename)
            with open(self.log_file_path, 'a', encoding='utf-8') as f:
                f.write(f"\n{'='*50}\n")
                f.write(f"程序启动于: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"{'='*50}\n")
        except Exception as e:
            print(f"初始化日志文件失败: {e}")
            self.log_file_path = None

    def _log_to_file(self, message):
        if hasattr(self, 'log_file_path') and self.log_file_path:
            try:
                with open(self.log_file_path, 'a', encoding='utf-8') as f:
                    f.write(message + "\n")
            except:
                pass

    def _append_log(self, full_msg):
        # 1. 如果程序已停止或页面不存在，绝对不要继续
        if not self.running or self.page is None:
            return
        
        # 2. 将整个控件创建和添加过程包裹在 try 块中
        # 报错 Traceback 显示错误发生在创建 ft.Text 时
        try:
            # 颜色逻辑
            log_color = None  # None = 跟随主题默认色
            if "[SSH]" in full_msg:
                log_color = "blue700"
            elif "[AutoDL]" in full_msg:
                log_color = "green700"
                
            msg_lower = full_msg.lower()
            if any(k in msg_lower for k in ["失败", "错误", "异常", "error", "fail", "exception"]):
                log_color = "red600"
            elif any(k in msg_lower for k in ["成功", "完成", "已连接", "已运行", "success", "done"]):
                if "[SSH]" in full_msg: log_color = "blue900"
                else: log_color = "green900"
            elif any(k in msg_lower for k in ["正在", "等待", "准备", "waiting", "preparing"]):
                log_color = "orange800"

            # 创建控件
            log_entry = ft.Text(full_msg, size=12, color=log_color, weight="w500" if log_color else None)
            
            # 添加到列表
            if self.log_listview and self.log_listview.controls is not None:
                self.log_listview.controls.append(log_entry)
                if len(self.log_listview.controls) > 500:
                    self.log_listview.controls.pop(0)
            
            # 尝试刷新（带节流）
            now = time.time()
            if not hasattr(self, '_last_ui_update'): self._last_ui_update = 0
            if now - self._last_ui_update > 0.2:
                self.safe_update()
                self._last_ui_update = now

        except RuntimeError as e:
            # 捕获并忽略 shutdown 错误
            if "schedule new futures" in str(e) or "shutdown" in str(e):
                return
        except Exception:
            # 忽略其他错误，防止写日志本身导致崩溃
            pass

    def update_status(self, message):
        if not self.running:
            return
        timestamp = time.strftime('%H:%M:%S')
        full_msg = f'[{timestamp}] [SSH] {message}'
        self._log_to_file(full_msg)
        
        # 避免完全相同的连续日志
        if self.log_listview.controls and hasattr(self.log_listview.controls[-1], 'value') and self.log_listview.controls[-1].value == full_msg:
            return
            
        self._append_log(full_msg)

    def update_autodl_status(self, message):
        if not self.running:
            return
        timestamp = time.strftime('%H:%M:%S')
        full_msg = f'[{timestamp}] [AutoDL] {message}'
        self._log_to_file(full_msg)
        
        if self.log_listview.controls and hasattr(self.log_listview.controls[-1], 'value') and self.log_listview.controls[-1].value == full_msg:
            return
            
        self._append_log(full_msg)

    def update_connection_status(self, is_connected):
        if not self.running:
            return
        self.is_connected = is_connected
        if is_connected:
            self.status_label.value = "状态: 已连接"
            self.status_label.color = "green"
            self.connect_button.disabled = True
            self.disconnect_button.disabled = False
        else:
            self.status_label.value = "状态: 未连接"
            self.status_label.color = "grey"
            self.connect_button.disabled = False
            self.disconnect_button.disabled = True
        self.safe_update()

    def update_autodl_login_status(self, is_logged_in):
        if not self.running:
            return
        self.is_autodl_logged_in = is_logged_in
        if is_logged_in:
            self.autodl_status_label.value = "已登录"
            self.autodl_status_label.color = "green"
            self.autodl_login_button.disabled = True
            self.autodl_logout_button.disabled = False
            self.autodl_refresh_button.disabled = False
            self.autodl_renew_button.disabled = False
            self.autodl_shutdown_all_button.disabled = False
        else:
            self.autodl_status_label.value = "未登录"
            self.autodl_status_label.color = "grey"
            self.autodl_login_button.disabled = False
            self.autodl_logout_button.disabled = True
            self.autodl_refresh_button.disabled = True
            self.autodl_renew_button.disabled = True
            self.autodl_shutdown_all_button.disabled = True
        self.safe_update()

    def update_device_table(self, data_list):
        if not self.running:
            return
        rows = []
        for data in data_list:
            remark = data.get('remark', '')
            device_name = data.get('device_name', '未知设备')
            status = data.get('status', '未知状态')
            specs = data.get('specs', '')
            device_id = data.get('device_id', '')
            release_time = data.get('release_time', '')
            
            # 状态颜色（None = 跟随主题默认色）
            status_color = None
            if '运行中' in status or 'running' in status.lower():
                status_color = "amber"
            elif '已关机' in status or 'stopped' in status.lower():
                status_color = ft.colors.GREY
            
            status_cell = ft.DataCell(ft.Text(status, color=status_color, size=12))
            
            # 释放时间颜色（越近越红，其余跟主题走）
            release_color = None
            if release_time:
                import re as _re
                day_match = _re.search(r'(\d+)\s*天', release_time)
                days = int(day_match.group(1)) if day_match else 99
                if days <= 3:
                    release_color = "red"
                elif days <= 7:
                    release_color = "orange"
            release_cell = ft.DataCell(ft.Text(release_time, color=release_color, size=12))
            
            # 操作按钮
            actions_cell = self._create_action_cells(device_id, remark, status, specs, device_name)
            
            row = ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(remark, size=12)),
                    ft.DataCell(ft.Text(device_name, size=12)),
                    status_cell,
                    ft.DataCell(ft.Text(specs, size=12)),
                    release_cell,
                    ft.DataCell(actions_cell),
                ]
            )
            rows.append(row)
        self.autodl_devices_table.rows = rows
        self.safe_update()

    def _create_action_cells(self, device_id, remark, status, specs, device_name):
        if '已关机' in status or '关机' in status or 'stopped' in status.lower():
            start_btn = ft.ElevatedButton("开机", on_click=lambda e, d=device_id, r=remark: self.autodl_start_only(d, r))
            smart_btn = ft.ElevatedButton("开机并连接", on_click=lambda e, d=device_id, r=remark: self.autodl_start(d, r))
            setup_btn = ft.ElevatedButton("设置连接信息", on_click=lambda e, d=device_id, r=remark, g=specs, l=device_name: self._open_device_config_dialog(d, r, g, l))
            nogpu_btn = ft.ElevatedButton("无卡开机", on_click=lambda e, d=device_id, r=remark: self.autodl_start_nogpu(d, r))
            if self._gpu_insufficient(status, specs):
                start_btn.disabled = True
                smart_btn.disabled = True
                start_btn.tooltip = "GPU配额不足，无法开机"
                smart_btn.tooltip = "GPU配额不足，无法开机"
            action_row = ft.Row(controls=[start_btn, smart_btn, setup_btn, nogpu_btn], spacing=5)
            return action_row
        elif '运行中' in status or 'running' in status.lower():
            stop_btn = ft.ElevatedButton("关机", on_click=lambda e, d=device_id, r=remark: self.autodl_stop(d, r))
            forward_btn = ft.ElevatedButton("转发", on_click=lambda e, d=device_id, r=remark: self.autodl_forward_only(d, r))
            connect_btn = ft.ElevatedButton("启动并连接", on_click=lambda e, d=device_id, r=remark: self.autodl_connect_device(d, r))
            jupyter_btn = ft.ElevatedButton("JupyterLab", on_click=lambda e, d=device_id, r=remark: self.autodl_click_jupyterlab(d, r))
            autopanel_btn = ft.ElevatedButton("AutoPanel", on_click=lambda e, d=device_id, r=remark: self.autodl_click_autopanel(d, r))
            setup_btn = ft.ElevatedButton("设置连接信息", on_click=lambda e, d=device_id, r=remark, g=specs, l=device_name: self._open_device_config_dialog(d, r, g, l))
            action_row = ft.Row(controls=[stop_btn, forward_btn, connect_btn, jupyter_btn, autopanel_btn, setup_btn], spacing=5)
            return action_row
        else:
            return ft.Row()

    # ---------- 对话框辅助 ----------
    def show_message(self, title, message):
        dlg = ft.AlertDialog(
            title=ft.Text(title),
            content=ft.Text(message),
            actions=[ft.TextButton("确定", on_click=lambda e: self.close_dialog(dlg))],
        )
        self.page.dialog = dlg
        dlg.open = True
        self.safe_update()

    def confirm_dialog(self, title, message, on_confirm):
        dlg = ft.AlertDialog(
            title=ft.Text(title),
            content=ft.Text(message),
            actions=[
                ft.TextButton("是", on_click=lambda e: self._on_confirm(dlg, on_confirm)),
                ft.TextButton("否", on_click=lambda e: self.close_dialog(dlg)),
            ],
        )
        self.page.dialog = dlg
        dlg.open = True
        self.safe_update()

    def input_dialog(self, title, message, on_ok):
        txt = ft.TextField(label=message)
        dlg = ft.AlertDialog(
            title=ft.Text(title),
            content=txt,
            actions=[
                ft.TextButton("确定", on_click=lambda e: self._on_input_ok(dlg, txt, on_ok)),
                ft.TextButton("取消", on_click=lambda e: self.close_dialog(dlg)),
            ],
        )
        self.page.dialog = dlg
        dlg.open = True
        self.safe_update()

    def close_dialog(self, dlg):
        dlg.open = False
        self.safe_update()

    def _on_confirm(self, dlg, callback):
        self.close_dialog(dlg)
        callback()

    def _on_input_ok(self, dlg, txt, callback):
        self.close_dialog(dlg)
        callback(txt.value)

    # ---------- 配置管理 ----------
    def save_config(self, e=None):
        ssh_info = self.ssh_info_input.value.strip()
        remote_port = self.remote_port_input.value.strip()
        password = self.password_input.value
        auto_open = self.auto_open_browser_checkbox.value

        if not ssh_info:
            self.show_message("输入错误", "请输入SSH连接信息")
            return
        if not remote_port:
            self.show_message("输入错误", "请输入远程端口")
            return
        try:
            port_num = int(remote_port)
            if port_num <= 0 or port_num > 65535:
                raise ValueError()
        except ValueError:
            self.show_message("输入错误", "请输入有效的端口号（1-65535）")
            return

        def on_input(config_name):
            if not config_name:
                return
            if not re.match(r'^[\w\-\_]+$', config_name):
                self.show_message("名称错误", "配置名称只能包含字母、数字、下划线和连字符")
                return
            config_data = {
                'ssh_info': ssh_info,
                'remote_port': remote_port,
                'password': password,
                'auto_open_browser': auto_open,
                'saved_at': time.strftime('%Y-%m-%d %H:%M:%S')
            }
            if password:
                if self.encryption_enabled:
                    enc = _win_dpapi_encrypt(password)
                    if enc:
                        config_data['password'] = enc
                else:
                    if not self.encryption_prompted:
                        def on_encryption_confirm():
                            self.encryption_enabled = True
                            self._set_encryption_pref(True)
                            enc = _win_dpapi_encrypt(password)
                            if enc:
                                config_data['password'] = enc
                            self._set_encryption_prompted(True)
                            self._do_save_config(config_name, config_data)
                        def on_encryption_cancel():
                            self._set_encryption_prompted(True)
                            self._do_save_config(config_name, config_data)
                        self.confirm_dialog("启用密码加密", "是否启用密码加密并以加密形式保存？（仅首次提示）", on_encryption_confirm)
                        return
            self._do_save_config(config_name, config_data)
        self.input_dialog("保存配置", "请输入配置名称:", on_input)

    def _do_save_config(self, config_name, config_data):
        config_file = os.path.join(self.config_dir, f'{config_name}.json')
        if os.path.exists(config_file):
            def on_confirm():
                try:
                    with open(config_file, 'w', encoding='utf-8') as f:
                        json.dump(config_data, f, ensure_ascii=False, indent=2)
                    self.show_message("保存成功", f'配置 "{config_name}" 已成功保存')
                    self.load_config_list()
                    self.config_combo.value = config_name
                    self.safe_update()
                except Exception as e:
                    self.show_message("保存失败", f'保存配置时出错: {str(e)}')
            self.confirm_dialog("确认覆盖", f'配置 "{config_name}" 已存在，是否覆盖？', on_confirm)
        else:
            try:
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(config_data, f, ensure_ascii=False, indent=2)
                self.show_message("保存成功", f'配置 "{config_name}" 已成功保存')
                self.load_config_list()
                self.config_combo.value = config_name
                self.safe_update()
            except Exception as e:
                self.show_message("保存失败", f'保存配置时出错: {str(e)}')

    def delete_config(self, e=None):
        config_key = self.config_combo.value
        if not config_key:
            self.show_message("选择错误", "请先选择要删除的配置")
            return
        config_name = config_key
        display_name = self.config_combo.selected_option.text if self.config_combo.selected_option else config_name
        def on_confirm():
            config_file = os.path.join(self.config_dir, f'{config_name}.json')
            if os.path.exists(config_file):
                try:
                    os.remove(config_file)
                    self.show_message("删除成功", f'配置 "{display_name}" 已删除')
                    self.load_config_list()
                    self.ssh_info_input.value = ""
                    self.remote_port_input.value = ""
                    self.password_input.value = ""
                    self.safe_update()
                except Exception as e:
                    self.show_message("删除失败", f'删除配置时出错: {str(e)}')
            else:
                self.show_message("文件不存在", "配置文件不存在或已被删除")
                self.load_config_list()
        self.confirm_dialog("确认删除", f'确定要删除配置 "{display_name}" 吗？\n此操作不可撤销。', on_confirm)

    def delete_all_configs(self, e=None):
        if not self.config_dir or not os.path.exists(self.config_dir):
            self.show_message("无配置", "配置目录不存在")
            return
        def on_confirm():
            for f in os.listdir(self.config_dir):
                if f.endswith('.json'):
                    try:
                        os.remove(os.path.join(self.config_dir, f))
                    except:
                        pass
            try:
                if os.path.exists(self.device_map_file):
                    os.remove(self.device_map_file)
            except:
                pass
            self.load_config_list()
            self.show_message("已删除", "已删除全部保存的连接信息")
        self.confirm_dialog("确认删除", "确定要删除全部保存的连接信息吗？此操作不可撤销。", on_confirm)

    def load_config_list(self):
        self.config_combo.options = [ft.dropdown.Option(key="", text="当前输入配置")]
        if not self.config_dir or not os.path.exists(self.config_dir):
            return
        try:
            config_files = [f for f in os.listdir(self.config_dir) if f.endswith('.json') and f != 'device_map.json' and f != 'autodl_credentials.json' and f != 'theme.json']
            for fname in sorted(config_files):
                config_name = os.path.splitext(fname)[0]
                display_name = config_name
                try:
                    with open(os.path.join(self.config_dir, fname), 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if isinstance(data, dict) and data.get('remark'):
                            display_name = data.get('remark')
                except:
                    pass
                self.config_combo.options.append(ft.dropdown.Option(key=config_name, text=display_name))
            self.safe_update()
        except Exception as e:
            self.update_status_signal.emit(f'加载配置列表时出错: {str(e)}')

    def load_selected_config(self, e=None):
        config_key = self.config_combo.value
        if not config_key:
            return
        config_file = os.path.join(self.config_dir, f'{config_key}.json')
        if not os.path.exists(config_file):
            self.show_message("文件不存在", f'配置文件不存在: {config_key}')
            self.load_config_list()
            return
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            self.ssh_info_input.value = str(config_data.get('ssh_info', ''))
            self.remote_port_input.value = str(config_data.get('remote_port', ''))
            pwd = str(config_data.get('password', ''))
            dec = _win_dpapi_decrypt(pwd)
            if dec is not None:
                pwd = dec
            self.password_input.value = pwd
            self.auto_open_browser_checkbox.value = bool(config_data.get('auto_open_browser', True))
            saved_time = config_data.get('saved_at', '未知')
            remark = str(config_data.get('remark', config_key))
            self.update_status_signal.emit(f'已加载配置: {remark} (保存时间: {saved_time})')
            self.safe_update()
        except Exception as e:
            self.show_message("加载失败", f'加载配置时出错: {str(e)}')

    def on_config_combo_change(self, e):
        self.load_selected_config()
        self.update_delete_button_state()

    def update_delete_button_state(self):
        self.delete_config_button.disabled = (self.config_combo.value == "")

    # ---------- 密码显示切换 ----------
    def toggle_password_visibility(self, e):
        self.password_input.password = not self.password_input.password
        self.safe_update()

    def toggle_autodl_password_visibility(self, e):
        self.autodl_password_input.password = not self.autodl_password_input.password
        self.safe_update()

    # ---------- SSH 连接 ----------
    def auto_parse_ssh_info(self, e):
        ssh_info = self.ssh_info_input.value.strip()
        if ssh_info:
            port_pattern = r'-L\s+(\d+):localhost:\d+'
            match = re.search(port_pattern, ssh_info)
            if match and not self.remote_port_input.value:
                self.remote_port_input.value = match.group(1)
                self.safe_update()

    def toggle_connection(self, e):
        if not self.is_connected:
            self.connect()

    def parse_ssh_info(self, ssh_info):
        try:
            clean_info = ssh_info.strip()
            tokens = shlex.split(clean_info)
            port = '22'
            user = None
            host = None

            for i, t in enumerate(tokens):
                if t == '-p' and i + 1 < len(tokens):
                    if re.match(r'^\d{1,5}$', tokens[i+1]):
                        port = tokens[i+1]
                if '@' in t and not user and not host:
                    u, h = t.split('@', 1)
                    if u and h:
                        user = u
                        host = h

            if not user or not host:
                m = re.search(r'([\w.-]+)@([\w.-]+)', clean_info)
                if m:
                    user = m.group(1)
                    host = m.group(2)

            if user and host:
                return host, port, user
        except Exception as e:
            self.update_status_signal.emit(f'解析SSH信息时出错: {str(e)}')

        return None, None, None

    def connect(self):
        if self.is_connected:
            self.update_status_signal.emit('已连接，忽略重复连接请求')
            return
        if self.is_connecting:
            self.update_status_signal.emit('正在连接中，请稍候')
            return
        ssh_info = self.ssh_info_input.value.strip()
        remote_port_text = self.remote_port_input.value.strip()
        password = self.password_input.value

        if not ssh_info:
            self.show_message("输入错误", "请输入SSH连接信息")
            return
        if not remote_port_text:
            self.show_message("输入错误", "请输入远程端口")
            return
        try:
            remote_port = int(remote_port_text)
            if remote_port <= 0 or remote_port > 65535:
                raise ValueError()
        except ValueError:
            self.show_message("输入错误", "请输入有效的端口号")
            return

        host, port, username = self.parse_ssh_info(ssh_info)
        if not host or not username:
            self.show_message("输入错误", "无法解析SSH连接信息，请检查格式\n例如: ssh -p 53372 root@region-41.seetacloud.com")
            return

        host = host.split()[0]

        self.is_connecting = True
        self.forward_thread = threading.Thread(
            target=self._connect_thread,
            args=(host, port, username, password, remote_port)
        )
        self.forward_thread.daemon = True
        self.forward_thread.start()

    def _connect_thread(self, host, port, username, password, remote_port):
        try:
            self.stop_event.clear()
            self.update_status_signal.emit(f'正在连接到 {username}@{host}:{port}...')
            self._last_connect_args = (host, port, username, password, remote_port)

            logging.getLogger('paramiko').setLevel(logging.WARNING)

            self.ssh_client = paramiko.SSHClient()
            self.update_status_signal.emit('自动接受主机密钥（相当于输入yes）')
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            self.update_status_signal.emit('正在进行密码认证...')
            self.ssh_client.connect(
                hostname=host,
                port=int(port),
                username=username,
                password=password,
                look_for_keys=False,
                allow_agent=False,
                timeout=30
            )

            self.update_status_signal.emit('SSH连接成功')

            transport = self.ssh_client.get_transport()
            if not transport:
                raise Exception('无法获取SSH传输通道')
            try:
                transport.set_keepalive(30)
            except Exception:
                pass

            self.update_status_signal.emit(f'正在设置端口转发: 本地端口 {remote_port} -> 远程端口 {remote_port}')

            self.connection_status_signal.emit(True)
            self.is_connected = True
            self.is_connecting = False

            try:
                server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server_socket.bind(('127.0.0.1', remote_port))
                server_socket.listen(5)
                server_socket.settimeout(1)
                self.update_status_signal.emit(f'本地监听器已启动在端口 {remote_port}')
                self.server_socket = server_socket
            except Exception as e:
                self.update_status_signal.emit(f'本地端口监听失败: 端口可能被占用或权限不足: {str(e)}')
                self.connection_status_signal.emit(False)
                return

            if self.auto_open_browser_checkbox.value:
                self.port_forwarding_setup = True
                self.update_status_signal.emit('等待端口转发完全建立...')
                ready = False
                start_t = time.time()
                attempt = 0
                while (time.time() - start_t < 300) and (not self.stop_event.is_set()) and self.is_connected:
                    try:
                        t = self.ssh_client.get_transport()
                        if t and t.is_active():
                            try:
                                ch = t.open_channel('direct-tcpip', ('127.0.0.1', remote_port), ('127.0.0.1', 0))
                                if ch:
                                    ch.close()
                                    ready = True
                                    break
                            except Exception:
                                pass
                    except Exception:
                        pass
                    attempt += 1
                    sleep_interval = 0.5 + min(attempt * 0.25, 2.0)
                    time.sleep(sleep_interval)
                if ready:
                    url = f'http://127.0.0.1:{remote_port}'
                    self.update_status_signal.emit(f'正在打开浏览器: {url}')
                    try:
                        success = webbrowser.open(url)
                        if success:
                            self.update_status_signal.emit(f'浏览器已成功打开: {url}')
                        else:
                            self.update_status_signal.emit('无法打开浏览器，请手动访问: ' + url)
                    except Exception as e:
                        self.update_status_signal.emit(f'打开浏览器时出错: {str(e)}，请手动访问: ' + url)
                else:
                    if not self.stop_event.is_set() and self.is_connected:
                        self.update_status_signal.emit('端口转发尚未可用，未打开浏览器')
                self.port_forwarding_setup = False

            if self.is_connected and not self.stop_event.is_set():
                self.update_status_signal.emit('端口转发已设置，连接保持活跃中...')

            browser_opened = False
            if self.auto_open_browser_checkbox.value:
                if ready:
                    browser_opened = True
            last_browser_try = 0.0
            while self.is_connected and not self.stop_event.is_set():
                try:
                    tcur = self.ssh_client.get_transport()
                    if (not tcur) or (not tcur.is_active()):
                        okr = self._reconnect_in_place()
                        if not okr:
                            time.sleep(1.0)
                            continue
                        tcur = self.ssh_client.get_transport()
                        if not tcur or not tcur.is_active():
                            time.sleep(1.0)
                            continue
                    if self.auto_open_browser_checkbox.value and not browser_opened:
                        now = time.time()
                        if now - last_browser_try >= 3.0:
                            last_browser_try = now
                            try:
                                ch2 = tcur.open_channel('direct-tcpip', ('127.0.0.1', remote_port), ('127.0.0.1', 0))
                                if ch2:
                                    ch2.close()
                                    url2 = f'http://127.0.0.1:{remote_port}'
                                    try:
                                        okweb = webbrowser.open(url2)
                                        if okweb:
                                            self.update_status_signal.emit(f'浏览器已成功打开: {url2}')
                                        else:
                                            self.update_status_signal.emit('无法打开浏览器，请手动访问: ' + url2)
                                    except Exception as e:
                                        self.update_status_signal.emit(f'打开浏览器时出错: {str(e)}，请手动访问: ' + url2)
                                    browser_opened = True
                            except Exception:
                                pass
                    readable, _, _ = select.select([self.server_socket], [], [], 0.2)
                    if readable:
                        client_socket, addr = self.server_socket.accept()
                        try:
                            client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                        except Exception:
                            pass
                        client_thread = threading.Thread(
                            target=self._handle_client,
                            args=(client_socket, tcur, remote_port)
                        )
                        client_thread.daemon = True
                        client_thread.start()
                        self.client_threads.append(client_thread)
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.is_connected and not self.stop_event.is_set():
                        okreb = self._recreate_server_socket(remote_port)
                        if not okreb:
                            time.sleep(1.0)
                            continue
                        self.server_socket = self.server_socket

        except paramiko.AuthenticationException:
            self.update_status_signal.emit('认证失败: 用户名或密码错误')
            self.connection_status_signal.emit(False)
        except paramiko.SSHException as e:
            self.update_status_signal.emit(f'SSH错误: {str(e)}')
            self.connection_status_signal.emit(False)
        except Exception as e:
            self.update_status_signal.emit(f'连接错误: {str(e)}')
            self.connection_status_signal.emit(False)
        finally:
            self.is_connecting = False
            if 'server_socket' in locals():
                try:
                    self.server_socket.close()
                except:
                    pass

    def _handle_client(self, client_socket, transport, remote_port):
        try:
            tt = self.ssh_client.get_transport()
            if not tt or not tt.is_active():
                ok_re = self._reconnect_in_place()
                if ok_re:
                    tt = self.ssh_client.get_transport()
            if not tt or not tt.is_active():
                raise paramiko.SSHException('SSH session not active')
            channel = tt.open_channel(
                'direct-tcpip',
                ('127.0.0.1', remote_port),
                ('127.0.0.1', client_socket.getsockname()[1])
            )
            if not channel:
                self.update_status_signal.emit('无法创建到远程服务器的通道')
                client_socket.close()
                return

            # 仅在本地日志中记录通道建立，不在 UI 中频繁刷新，防止假死
            self._log_to_file(f"[{time.strftime('%H:%M:%S')}] [SSH] 已建立到远程端口 {remote_port} 的转发通道 (线程: {threading.current_thread().name})")

            while self.is_connected and not self.stop_event.is_set():
                try:
                    r, _, _ = select.select([client_socket, channel], [], [], 0.1)
                    if client_socket in r:
                        data = client_socket.recv(8192)
                        if not data: break
                        channel.sendall(data)

                    if channel in r:
                        data = channel.recv(8192)
                        if not data: break
                        client_socket.sendall(data)
                except (socket.error, paramiko.SSHException) as e:
                    self._log_to_file(f"[{time.strftime('%H:%M:%S')}] [SSH] 转发中断: {str(e)}")
                    break
                except Exception as e:
                    self._log_to_file(f"[{time.strftime('%H:%M:%S')}] [SSH] 转发异常: {str(e)}")
                    break

        except Exception:
            pass
        finally:
            try:
                client_socket.close()
            except: pass
            try:
                channel.close()
            except: pass
            self._log_to_file(f"[{time.strftime('%H:%M:%S')}] [SSH] 客户端连接已关闭")

    def _reconnect_in_place(self, max_retries=10):
        try:
            if self.stop_event.is_set():
                return False
            if self.reconnecting:
                return False
            args = getattr(self, '_last_connect_args', None)
            if not args or len(args) != 5:
                return False
            self.reconnecting = True
            host, port, username, password, remote_port = args
            attempt = 0
            while attempt < max_retries:
                if self.stop_event.is_set():
                    break
                
                # 只有在第3次及以后的重试时才检查设备状态，避免频繁调用 Selenium
                if attempt >= 3 and self._detect_device_shutdown_for_reconnect():
                    self.update_status_signal.emit('检测到设备已关机，停止重连')
                    self.reconnecting = False
                    return False
                
                if attempt > 0:
                    wait = min(2 ** attempt, 30) # 缩短最大等待时间，提高响应感
                    self.update_status_signal.emit(f'重连尝试 ({attempt}/{max_retries})，{wait}秒后重试...')
                    time.sleep(wait)
                
                c = paramiko.SSHClient()
                c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                try:
                    c.connect(
                        hostname=host,
                        port=int(port),
                        username=username,
                        password=password,
                        look_for_keys=False,
                        allow_agent=False,
                        timeout=20
                    )
                    t = c.get_transport()
                    if t:
                        try:
                            t.set_keepalive(30)
                        except Exception:
                            pass
                    self.ssh_client = c
                    self.update_status_signal.emit('重连成功')
                    self.reconnecting = False
                    return True
                except Exception as e:
                    attempt += 1
                    wait = min(2 ** attempt, 60)
                    self.update_status_signal.emit(f'重连失败 ({attempt}/{max_retries})，{wait}秒后重试...')
                    if self.stop_event.is_set():
                        break
                    time.sleep(wait)
            self.update_status_signal.emit('达到最大重试次数，放弃连接')
            self.disconnect()
            self.reconnecting = False
            return False
        except Exception:
            self.reconnecting = False
            return False

    def _detect_device_shutdown_for_reconnect(self):
        try:
            if not self.autodl_driver or not self.is_autodl_logged_in:
                return False
            did = self.await_running_device_id
            rem = self.await_running_remark
            if not did and not rem:
                return False
            self._goto_instance_list()
            r = None
            if did:
                try:
                    r = self._find_row_by_device_id(did)
                except:
                    r = None
            if r is None and rem:
                try:
                    r = self._find_row_by_remark(rem)
                except:
                    r = None
            if r:
                return self._is_stopped_row(r)
            return False
        except Exception:
            return False

    def _recreate_server_socket(self, remote_port):
        try:
            if self.server_socket:
                self.server_socket.close()
                self.server_socket = None
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('127.0.0.1', remote_port))
            s.listen(5)
            s.settimeout(1)
            self.server_socket = s
            self.update_status_signal.emit(f'本地监听器已重建在端口 {remote_port}')
            return True
        except Exception as e:
            self.update_status_signal.emit(f'本地监听器重建失败: {str(e)}')
            return False

    def disconnect(self, e=None):
        self.update_status_signal.emit('正在断开连接...')
        self.is_connected = False
        self.stop_event.set()
        time.sleep(0.5)

        try:
            if self.server_socket:
                self.server_socket.close()
                self.server_socket = None
                self.update_status_signal.emit('端口监听已关闭')
        except:
            pass

        if self.ssh_client:
            try:
                self.ssh_client.close()
                self.update_status_signal.emit('SSH连接已关闭')
            except Exception as e:
                self.update_status_signal.emit(f'关闭SSH连接时出错: {str(e)}')
            self.ssh_client = None

        self.forward_thread = None
        self.client_threads = []
        self.connection_status_signal.emit(False)
        self.update_status_signal.emit('连接已完全断开')
        self.stop_event.clear()

    # ---------- AutoDL 核心 ----------
    def autodl_login(self, headless=None):
        if not SELENIUM_AVAILABLE:
            if not self._ensure_autodl_dependencies():
                self.show_message('依赖缺失', '自动安装 selenium 失败，请手动安装')
                return
        username = self.autodl_username_input.value.strip()
        password = self.autodl_password_input.value
        if headless is None:
            headless = (self.browser_mode_group.value == 'headless')
        
        # 移除这里的 "开始登录流程..." 提示，让子函数决定提示语
        def login_thread():
            try:
                self._login_via_list_tag(username, password, headless)
            except Exception as e:
                self.autodl_status_signal.emit(f'登录异常: {str(e)}')
        threading.Thread(target=login_thread, daemon=True).start()

    def _login_via_list_tag(self, username, password, headless):
        try:
            # 增加驱动存活检查，避免重复初始化
            is_driver_alive = False
            if self.autodl_driver:
                try:
                    # 尝试获取标题，如果成功说明驱动还在
                    _ = self.autodl_driver.title
                    is_driver_alive = True
                except Exception:
                    is_driver_alive = False
            
            if not is_driver_alive:
                self.autodl_status_signal.emit('正在初始化浏览器环境...')
                if not self.init_autodl_driver(headless=headless):
                    return
            else:
                self.autodl_status_signal.emit('重用已开启的浏览器...')
            self.autodl_status_signal.emit('正在访问AutoDL...')
            list_url = 'https://www.autodl.com/console/instance/list'
            try:
                self.autodl_driver.get(list_url)
            except Exception:
                pass
            time.sleep(1)
            cu = ''
            try:
                cu = self.autodl_driver.current_url
            except Exception:
                cu = ''
            if 'login' in cu:
                self.autodl_status_signal.emit('检测到登录页面，准备登录...')
                if not password:
                    self.autodl_status_signal.emit('请输入密码进行登录')
                    return
                pw = None
                try:
                     WebDriverWait(self.autodl_driver, 10).until(EC.presence_of_element_located((By.XPATH, "//input[@type='password']")))
                     pws = self.autodl_driver.find_elements(By.XPATH, "//input[@type='password']")
                     if pws: pw = pws[0]
                except Exception:
                    pass
                un = None
                try:
                    cands = self.autodl_driver.find_elements(By.XPATH, "//input[@type='text'] | //input[@type='tel']")
                    if cands:
                        un = cands[-1]
                except Exception:
                    un = None
                if un and username:
                    try:
                        self.autodl_status_signal.emit('正在输入用户名...')
                        un.clear()
                        un.send_keys(username)
                    except Exception:
                        pass
                if pw and password:
                    try:
                        self.autodl_status_signal.emit('正在输入密码...')
                        pw.clear()
                        pw.send_keys(password)
                    except Exception:
                        pass
                btn = None
                for xp in [
                    ".//button[contains(normalize-space(),'登录')]",
                    "//button[contains(normalize-space(),'登录')]",
                    "//*[contains(@class,'el-button--primary')]",
                ]:
                    try:
                        btn = self.autodl_driver.find_element(By.XPATH, xp)
                        break
                    except Exception:
                        continue
                if btn:
                    try:
                        self.autodl_status_signal.emit('正在点击登录按钮...')
                        self.autodl_driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                        time.sleep(0.5)
                        try:
                            btn.click()
                        except:
                            self.autodl_driver.execute_script('arguments[0].click();', btn)
                    except Exception:
                        pass
                self.autodl_status_signal.emit('等待登录跳转...')
                time.sleep(2)
                try:
                    WebDriverWait(self.autodl_driver, 5).until(lambda d: 'login' not in d.current_url)
                except:
                    pass
            try:
                self.autodl_driver.get(list_url)
            except Exception:
                pass
            time.sleep(1)
            final_url = ''
            try:
                final_url = self.autodl_driver.current_url
            except:
                pass
            if 'login' in final_url:
                self.autodl_status_signal.emit('登录失败：未能进入控制台，请检查账号密码')
                self.autodl_login_signal.emit(False)
            else:
                self.autodl_login_signal.emit(True)
                self.is_autodl_logged_in = True
                self.autodl_status_signal.emit('登录成功')
                # 登录成功后自动刷新
                self.autodl_refresh_devices_quick()
        except Exception as e:
            self.autodl_status_signal.emit(f'登录过程出错: {str(e)}')

    def autodl_logout(self, e=None):
        try:
            if self.autodl_driver:
                self.autodl_driver.get('https://www.autodl.com/logout')
                self.autodl_login_signal.emit(False)
                self.autodl_status_signal.emit('已登出')
                try:
                    self.autodl_driver.quit()
                except Exception:
                    pass
                self.autodl_driver = None
        except Exception as e:
            self.autodl_status_signal.emit(f'登出出错: {str(e)}')

    def _ensure_driver_alive(self):
        """确保 WebDriver 实例存活且未失效"""
        if not self.autodl_driver:
            return False
        try:
            # 尝试一个轻量级操作来检测 Driver 是否有效
            _ = self.autodl_driver.title
            return True
        except Exception:
            self.autodl_status_signal.emit('检测到浏览器会话失效，尝试重新初始化...')
            try:
                self.autodl_driver.quit()
            except:
                pass
            self.autodl_driver = None
            self.is_autodl_logged_in = False
            # 尝试静默重新登录
            username = self.autodl_username_input.value.strip()
            password = self.autodl_password_input.value
            headless = (self.browser_mode_group.value == 'headless')
            if username and password:
                return self._login_via_list_tag(username, password, headless)
            return False

    def init_autodl_driver(self, headless=True):
        if self.is_autodl_initializing:
            return False
        self.is_autodl_initializing = True
        try:
            self._log_to_file("--- 开始初始化 WebDriver ---")
            # 1. 极速清理，增加超时保护
            try:
                self._log_to_file("正在清理旧进程...")
                subprocess.run(['taskkill', '/F', '/IM', 'chromedriver.exe', '/T'], 
                               capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
                self._log_to_file("进程清理完成")
            except subprocess.TimeoutExpired:
                self._log_to_file("清理进程超时，跳过")
            except Exception as e:
                self._log_to_file(f"清理进程异常: {e}")
            
            self.autodl_status_signal.emit('准备环境...')
            driver_path_file = os.path.join(self.config_dir, 'chromedriver.path')
            
            # 2. 尝试极速重用
            if self.autodl_driver:
                try:
                    self._log_to_file("尝试重用驱动...")
                    _ = self.autodl_driver.title
                    self.autodl_status_signal.emit('重用已开启的浏览器...')
                    return True
                except:
                    self._log_to_file("旧驱动已失效")
                    self.autodl_driver = None

            # 3. 准备启动参数
            self._log_to_file("正在准备启动参数...")
            chrome_options = Options()
            if headless:
                chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--disable-software-rasterizer')
            chrome_options.add_argument('--remote-debugging-port=0') # 强制使用随机端口
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            
            # 4. 本地驱动极速探测
            local_exe = os.path.join(self.config_dir, 'chromedriver.exe')
            if os.path.exists(local_exe):
                try:
                    self._log_to_file(f"尝试加载本地备份驱动: {local_exe}")
                    service = Service(executable_path=local_exe)
                    if os.name == 'nt':
                        service.creation_flags = subprocess.CREATE_NO_WINDOW
                    
                    # 给 Chrome 启动本身加一个超时尝试
                    self.autodl_driver = webdriver.Chrome(service=service, options=chrome_options)
                    self._log_to_file("本地驱动加载成功")
                    self.autodl_status_signal.emit('本地驱动秒开成功')
                    return True
                except Exception as e:
                    self._log_to_file(f"本地备份驱动启动失败: {e}")
                    try: os.remove(local_exe)
                    except: pass

            # 5. 如果本地失效，才尝试 WDM
            self._log_to_file("进入 WDM 联网检查流程...")
            self.autodl_status_signal.emit('正在同步驱动(仅需一次)...')
            try:
                os.environ['WDM_LOG_LEVEL'] = '0'
                path = ChromeDriverManager().install()
                self._log_to_file(f"WDM 下载/获取路径成功: {path}")
                
                service = Service(executable_path=path)
                if os.name == 'nt':
                    service.creation_flags = subprocess.CREATE_NO_WINDOW
                
                self._log_to_file("正在通过 WDM 路径启动浏览器...")
                self.autodl_driver = webdriver.Chrome(service=service, options=chrome_options)
                self._log_to_file("浏览器启动成功")
                
                # 下载成功后立即备份到本地，确保下次秒开
                try:
                    import shutil
                    os.makedirs(self.config_dir, exist_ok=True)
                    shutil.copy2(path, local_exe)
                    with open(driver_path_file, 'w', encoding='utf-8') as f:
                        f.write(path)
                except: pass
                
                self.autodl_status_signal.emit('同步完成，已开启浏览器')
                return True
            except Exception as e:
                self.autodl_status_signal.emit(f'驱动初始化失败: {str(e)}')
                return False

            try:
                self.autodl_driver.set_page_load_timeout(8)
            except Exception:
                pass
            try:
                self.autodl_driver.implicitly_wait(0)
            except Exception:
                pass
            self.autodl_driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            self.autodl_status_signal.emit('浏览器启动成功')
            return True
        except Exception as e:
            msg = str(e)
            try:
                import tempfile
                # 修改：使用系统临时目录而不是 config_dir，避免污染用户文件夹
                tmp_dir = tempfile.mkdtemp(prefix='chrometmp-')
                fallback_options = Options()
                if headless:
                    fallback_options.add_argument('--headless=new')
                    fallback_options.add_argument('--window-size=1366,900')
                else:
                    fallback_options.add_argument('--window-size=1366,900')
                fallback_options.add_argument('--no-sandbox')
                fallback_options.add_argument('--disable-dev-shm-usage')
                fallback_options.add_argument('--disable-extensions')
                fallback_options.add_argument('--no-first-run')
                fallback_options.add_argument('--no-default-browser-check')
                fallback_options.add_argument('--remote-debugging-port=0')
                fallback_options.add_argument(f'--user-data-dir={tmp_dir}')
                fallback_options.add_argument('--profile-directory=Default')
                fallback_options.add_experimental_option("excludeSwitches", ["enable-automation"])
                fallback_options.add_experimental_option('useAutomationExtension', False)
                fallback_options.add_experimental_option("prefs", {"credentials_enable_service": True, "profile.password_manager_enabled": True})
                
                self.autodl_driver = None
                if driver_path:
                    try:
                        service = Service(executable_path=driver_path)
                        self.autodl_driver = webdriver.Chrome(service=service, options=fallback_options)
                    except Exception:
                        self.autodl_driver = None
                if not self.autodl_driver:
                    try:
                        os.environ['WDM_LOCAL'] = '1'
                        path = ChromeDriverManager().install()
                        service = Service(executable_path=path)
                        self.autodl_driver = webdriver.Chrome(service=service, options=fallback_options)
                    except Exception:
                        try:
                            os.environ['WDM_LOCAL'] = '0'
                            path = ChromeDriverManager().install()
                            service = Service(executable_path=path)
                            self.autodl_driver = webdriver.Chrome(service=service, options=fallback_options)
                        except Exception:
                             self.autodl_driver = webdriver.Chrome(options=fallback_options)
                try:
                    self.autodl_driver.set_page_load_timeout(8)
                except: pass
                try:
                    self.autodl_driver.implicitly_wait(0)
                except: pass
                return True
            except Exception as e2:
                if headless:
                    try:
                        visible_options = Options()
                        visible_options.add_argument('--window-size=1366,900')
                        visible_options.add_argument('--no-first-run')
                        visible_options.add_argument('--no-default-browser-check')
                        visible_options.add_argument('--remote-debugging-port=0')
                        try:
                            profile_dir2 = os.path.join(self.config_dir, 'chrome_profile_visible')
                            os.makedirs(profile_dir2, exist_ok=True)
                            visible_options.add_argument(f'--user-data-dir={profile_dir2}')
                            visible_options.add_argument('--profile-directory=Default')
                        except Exception:
                            pass
                        visible_options.add_experimental_option("prefs", {"credentials_enable_service": True, "profile.password_manager_enabled": True})
                        try:
                            self.autodl_driver = webdriver.Chrome(options=visible_options)
                        except Exception:
                            service = Service(ChromeDriverManager().install())
                            self.autodl_driver = webdriver.Chrome(service=service, options=visible_options)
                        return True
                    except Exception:
                        pass
                self.autodl_status_signal.emit(f'Chrome浏览器初始化失败: {msg}')
                return False
        finally:
            self.is_autodl_initializing = False

    def _cleanup_chrome_profile(self, profile_dir):
        """清理 Chrome 配置文件中的锁文件，防止崩溃"""
        try:
            # 基础锁文件
            lock_files = ['SingletonLock', 'SingletonCookie', 'SingletonSharedMemory', 'SingletonSocket', 'lockfile']
            for name in lock_files:
                p = os.path.join(profile_dir, name)
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except Exception:
                    pass
            
            # 递归清理 Default 目录下的锁
            default_dir = os.path.join(profile_dir, 'Default')
            if os.path.exists(default_dir):
                for name in lock_files:
                    p = os.path.join(default_dir, name)
                    try:
                        if os.path.exists(p):
                            os.remove(p)
                    except Exception:
                        pass
        except Exception:
            pass
            
    def safe_update(self):
        """安全地更新页面，暴力忽略所有退出时的错误"""
        # 1. 极速检查：如果页面已销毁或程序已停止，直接返回
        if not self.running or self.page is None:
            return
            
        try:
            self.page.update()
        except RuntimeError as e:
            # 2. 核心修复：这是你遇到的那个具体错误
            # 只要包含 "schedule new futures" 或 "shutdown"，直接忽略
            if "schedule new futures" in str(e) or "shutdown" in str(e):
                return
        except Exception:
            # 3. 忽略其他所有更新错误
            pass

    def cleanup(self, e=None):
        """清理资源"""
        # 1. 立即标记停止
        self.running = False
        
        # 2. 立即切断 UI 引用
        # 这是为了让所有后台线程的 _append_log 和 safe_update 里的
        # `if self.page is None` 检查立刻生效
        self.page = None
        
        self.stop_event.set()
        
        self._log_to_file("--- 执行清理流程 ---")

        # 2. 关闭 SSH 客户端
        if self.ssh_client:
            try:
                self.ssh_client.close()
                self._log_to_file("SSH 客户端已关闭")
            except: pass
            self.ssh_client = None
            
        # 3. 关闭本地监听 Socket
        if self.server_socket:
            try:
                self.server_socket.close()
                self._log_to_file("本地监听 Socket 已关闭")
            except: pass
            self.server_socket = None
            
        # 4. 退出 Selenium WebDriver
        if self.autodl_driver:
            try:
                self._log_to_file("正在退出浏览器驱动...")
                self.autodl_driver.quit()
                self._log_to_file("浏览器驱动已安全退出")
            except Exception as ex:
                self._log_to_file(f"退出驱动失败: {ex}")
            finally:
                self.autodl_driver = None
        
        # 5. 强制杀掉可能的残留进程
        self._force_kill_zombie_chrome()
        self._log_to_file("--- 清理流程结束 ---")

    def _force_kill_zombie_chrome(self):
        """非阻塞式清理僵尸进程"""
        try:
            import subprocess
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            # 使用 TASKKILL 强制清理，但不等待其完成，避免阻塞
            subprocess.Popen(['taskkill', '/F', '/IM', 'chromedriver.exe', '/T'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, startupinfo=startupinfo)
            subprocess.Popen(['taskkill', '/F', '/IM', 'chrome.exe', '/T'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, startupinfo=startupinfo)
        except:
            pass

    def autodl_refresh_devices(self, e=None, initial=False):
        if not self.autodl_driver:
            self.autodl_status_signal.emit('浏览器未初始化')
            return
        if self.autodl_busy:
            self.autodl_status_signal.emit('正在执行任务，请稍候...')
            return
        if self.refreshing:
            self.autodl_status_signal.emit('正在刷新中，请稍候...')
            return
        if self.autodl_refresh_lock and not self.autodl_refresh_lock.acquire(blocking=False):
            self.autodl_status_signal.emit('正在刷新中，请稍候...')
            return
        self.refreshing = True
        self.autodl_busy = True
        def refresh_thread():
            try:
                self.autodl_status_signal.emit('正在刷新设备列表...')
                target_url = 'https://www.autodl.com/console/instance/list'
                current_url = self.autodl_driver.current_url
                try:
                    if target_url in current_url:
                        self._click_refresh_btn()
                    else:
                        self.autodl_driver.get(target_url)
                except TimeoutException:
                    self.autodl_status_signal.emit('页面加载超时，尝试继续读取...')
                rows, empty = self._wait_rows_or_empty(timeout=(12 if initial else 8), interval=0.2)
                gpu_devices = self.autodl_detect_gpu_devices()
                if gpu_devices:
                    rows = []
                    for device in gpu_devices:
                        if 'row_element' in device:
                            rows.append(device['row_element'])
                        elif 'container_element' in device:
                            rows.append(device['container_element'])
                    table_data = self._format_rows_for_table(rows)
                    current_hash = self._compute_device_hash(table_data)
                    self.update_device_table_signal.emit(table_data)
                    if current_hash != self.last_device_hash:
                        self.autodl_status_signal.emit(f'刷新成功，找到 {len(rows)} 台设备')
                        self.last_device_hash = current_hash
                    try:
                        self.load_config_list()
                    except Exception:
                        pass
                else:
                    if empty:
                        table_data = []
                        current_hash = self._compute_device_hash(table_data)
                        self.update_device_table_signal.emit(table_data)
                        if current_hash != self.last_device_hash:
                            self.autodl_status_signal.emit('列表为空')
                            self.last_device_hash = current_hash
                        return
                    self.autodl_status_signal.emit('未检测到设备 (可能页面结构变更或无实例)')
            except Exception as e:
                self.autodl_status_signal.emit(f'刷新失败: {str(e)}')
            finally:
                try:
                    self.refreshing = False
                    if self.autodl_refresh_lock.locked():
                        self.autodl_refresh_lock.release()
                except:
                    self.refreshing = False
                try:
                    self.autodl_busy = False
                except:
                    pass
                self.autodl_status_signal.emit('刷新任务完成')
        threading.Thread(target=refresh_thread, daemon=True).start()

    def autodl_refresh_devices_quick(self, silent=False):
        if not self.autodl_driver or not self.is_autodl_logged_in:
            if not silent:
                self.autodl_status_signal.emit('请先登录AutoDL')
            return
        if self.autodl_busy:
            if not silent:
                self.autodl_status_signal.emit('正在执行任务，请稍候')
            return
        if self.refreshing:
            if not silent:
                self.autodl_status_signal.emit('正在刷新中，请稍候')
            return
        if self.autodl_refresh_lock and not self.autodl_refresh_lock.acquire(blocking=False):
            if not silent:
                self.autodl_status_signal.emit('正在刷新中，请稍候')
            return
        self.refreshing = True
        def refresh_thread():
            try:
                if not silent:
                    self.autodl_status_signal.emit('正在刷新设备列表...')
                target_url = 'https://www.autodl.com/console/instance/list'
                try:
                    cu = self.autodl_driver.current_url
                except Exception:
                    cu = ''
                if '/console/instance/list' not in cu:
                    try:
                        self.autodl_driver.get(target_url)
                    except Exception:
                        pass
                else:
                    try:
                        self._click_refresh_btn()
                    except Exception:
                        pass
                rows, empty = self._wait_rows_or_empty(timeout=3, interval=0.2)
                table_data = self._format_rows_for_table(rows)
                current_hash = self._compute_device_hash(table_data)
                self.update_device_table_signal.emit(table_data)
                if self.await_running_device_id or self.await_running_remark:
                    target_id = self.await_running_device_id
                    target_rem = self.await_running_remark
                    found_running = False
                    for d in table_data:
                        id_ = (d.get('device_id') or '').strip()
                        rem_ = (d.get('remark') or '').strip()
                        st_ = (d.get('status') or '').strip()
                        sl_ = st_.lower()
                        if ((target_id and id_ and target_id in id_) or (target_rem and rem_ and target_rem in rem_)) and (('运行中' in st_) or ('running' in sl_)):
                            found_running = True
                            break
                    if found_running:
                        self.await_running_device_id = None
                        self.await_running_remark = None
                if not silent and current_hash != self.last_device_hash:
                    self.autodl_status_signal.emit(f'设备列表刷新完成，共找到 {len(rows)} 台设备')
                    self.last_device_hash = current_hash
                elif silent:
                    self.last_auto_refresh_time = time.time()
                    self.autodl_status_label.value = '已自动刷新'
                    self.safe_update()
                try:
                    self.load_config_list()
                except Exception:
                    pass
            except TimeoutException:
                if not silent:
                    self.autodl_status_signal.emit('刷新设备列表超时')
            except Exception as e:
                if not silent:
                    self.autodl_status_signal.emit(f'刷新设备列表失败: {str(e)}')
            finally:
                try:
                    self.refreshing = False
                    if self.autodl_refresh_lock.locked():
                        self.autodl_refresh_lock.release()
                except:
                    self.refreshing = False
                if not silent:
                    self.autodl_status_signal.emit('刷新任务完成')
        threading.Thread(target=refresh_thread, daemon=True).start()

    def _auto_refresh_tick(self):
        # 增加 self.page 检查；续费等后台任务期间跳过自动刷新，避免 driver 竞争
        if not self.running or not self.page or not self.is_autodl_logged_in or self.refreshing or self.port_forwarding_setup or self.autodl_busy:
            return
        if self.silent_refresh_checkbox.value:
            self.autodl_refresh_devices_quick(True)
        else:
            self.autodl_refresh_devices_quick(False)

    def _update_refresh_time_label(self):
        if not self.running:
            return
        if self.last_auto_refresh_time > 0:
            diff = int(time.time() - self.last_auto_refresh_time)
            if diff >= 0:
                # 任务进行中时不覆盖任务状态标签
                if self.autodl_busy:
                    return
                self.autodl_status_label.value = f'已自动刷新 ({diff}秒前)'
                self.safe_update()

    def _wait_rows_or_empty(self, timeout=8, interval=0.2):
        rows = []
        empty = False
        start = time.time()
        while time.time() - start < timeout:
            try:
                rows = self.autodl_driver.find_elements(By.CSS_SELECTOR, '.el-table__body tr')
                if rows:
                    break
                empties = self.autodl_driver.find_elements(By.CSS_SELECTOR, '.el-table__empty-text')
                loading_masks = self.autodl_driver.find_elements(By.CSS_SELECTOR, '.el-loading-mask')
                if empties:
                    if not loading_masks:
                        empty = True
                        break
            except Exception:
                pass
            time.sleep(interval)
        return rows, empty

    def _debug_page_state(self, label=''):
        """记录页面状态到日志文件（仅在异常排查时使用）"""
        try:
            cu = self.autodl_driver.current_url if self.autodl_driver else ''
            rows_cnt = len(self.autodl_driver.find_elements(By.CSS_SELECTOR, '.el-table__body tr')) if self.autodl_driver else 0
            self._log_to_file(f"[页面状态] {label} url={cu} rows={rows_cnt}")
        except Exception:
            pass

    def autodl_detect_gpu_devices(self):
        if not self.autodl_driver:
            return []
        devices = []
        try:
            rows = self.autodl_driver.find_elements(By.CSS_SELECTOR, '.el-table__body tr')
            if not rows:
                rows = self.autodl_driver.find_elements(By.TAG_NAME, 'tr')
                if len(rows) > 0 and 'th' in rows[0].get_attribute('innerHTML').lower():
                    rows = rows[1:]
            for i, row in enumerate(rows):
                try:
                    if not row.is_displayed():
                        continue
                    text_content = row.text
                    import re
                    is_valid_row = False
                    if re.search(r'[a-f0-9]{4,}', text_content.lower()):
                        is_valid_row = True
                    elif any(k in text_content for k in ['运行中', '关机', '开机', 'GPU', '¥']):
                        is_valid_row = True
                    if is_valid_row:
                        cells = row.find_elements(By.TAG_NAME, 'td')
                        cell_texts = [c.text.strip() for c in cells]
                        devices.append({
                            'row_element': row,
                            'data': cell_texts,
                            'text': text_content
                        })
                except StaleElementReferenceException:
                    continue
                except Exception:
                    continue
            return devices
        except Exception as e:
            print(f"GPU 检测严重错误: {e}")
            return []

    def _format_rows_for_table(self, rows):
        data_list = []
        import re as _re
        for row in rows:
            try:
                device_name = '未知设备'
                device_id = ''
                remark = ''
                status = '未知状态'
                specs = ''
                try:
                    cells = row.find_elements(By.TAG_NAME, 'td')
                except Exception:
                    cells = []
                if cells:
                    cell_text = (cells[0].text or '').strip()
                    lines = [ln.strip() for ln in cell_text.split('\n') if ln.strip()]
                    device_name = lines[0] if lines else '未知设备'
                    id_line = ''
                    for ln in lines[1:]:
                        if _re.fullmatch(r'[a-fA-F0-9\-]{6,}', ln):
                            id_line = ln
                            break
                    device_id = id_line
                    for ln in lines[1:]:
                        if '-' in ln and _re.fullmatch(r'[a-fA-F0-9\-]{6,}', ln):
                            continue
                        remark = ln
                        break
                    if not remark and len(lines) >= 3:
                        remark = lines[2]
                    remark = (remark or '').replace('查看详情', '').strip()
                    status_text = (cells[1].text or '').strip() if len(cells) > 1 else '未知状态'
                    status_lines = [ln.strip() for ln in status_text.split('\n') if ln.strip()]
                    status_main = status_lines[0] if status_lines else '未知状态'
                    try:
                        pri = {'run':0,'boot':1,'stop':2,'other':3}
                        def weight(s):
                            sl = s.lower()
                            if ('运行中' in s) or ('running' in sl):
                                return pri['run']
                            if any(k in s for k in ['开机中','正在开机','启动中']) or any(k in sl for k in ['starting','booting']):
                                return pri['boot']
                            if ('已关机' in s) or ('stopped' in sl):
                                return pri['stop']
                            return pri['other']
                        status_main = min(status_lines or ['未知状态'], key=weight)
                    except Exception:
                        pass
                    gpu_line = next((ln for ln in status_lines if 'GPU' in ln), '')
                    status = status_main + (f" · {gpu_line}" if gpu_line else '')
                    specs = (cells[2].text or '').strip() if len(cells) > 2 else ''
                    specs = specs.replace('查看详情', '').strip()
                    # 列6: 释放时间 (格式: "14天23小时40分后释放\n设置定时关机")
                    release_time = ''
                    if len(cells) > 6:
                        release_text = (cells[6].text or '').strip()
                        release_lines = [ln.strip() for ln in release_text.split('\n') if ln.strip()]
                        for ln in release_lines:
                            if '后释放' in ln or '释放' in ln:
                                release_time = ln
                                break
                    st_low = (row.text or '').lower()
                    sp_low = specs.lower()
                    if ((('无卡' in row.text) or ('no gpu' in st_low)) or ('无卡' in specs) or ('no gpu' in sp_low)) and (('运行中' in status_main) or ('running' in status_main.lower())):
                        status = f"{status} · 无卡模式"
                else:
                    row_text = (getattr(row, 'text', '') or '').strip()
                    release_time = ''
                    if row_text:
                        lines = [ln.strip() for ln in row_text.split('\n') if ln.strip()]
                        device_name = lines[0] if lines else '未知设备'
                        id_line = ''
                        for ln in lines[1:]:
                            if _re.fullmatch(r'[a-fA-F0-9\-]{6,}', ln):
                                id_line = ln
                                break
                        device_id = id_line
                        for ln in lines[1:]:
                            if '-' in ln and _re.fullmatch(r'[a-fA-F0-9\-]{6,}', ln):
                                continue
                            remark = ln
                            break
                        if not remark and len(lines) >= 3:
                            remark = lines[2]
                        remark = (remark or '').replace('查看详情', '').strip()
                        status_lines = [ln for ln in lines[1:] if ln]
                        status_main = status_lines[0] if status_lines else '未知状态'
                        try:
                            pri = {'run':0,'boot':1,'stop':2,'other':3}
                            def weight2(s):
                                sl = s.lower()
                                if ('运行中' in s) or ('running' in sl):
                                    return pri['run']
                                if any(k in s for k in ['开机中','正在开机','启动中']) or any(k in sl for k in ['starting','booting']):
                                    return pri['boot']
                                if ('已关机' in s) or ('stopped' in sl):
                                    return pri['stop']
                                return pri['other']
                            status_main = min(status_lines or ['未知状态'], key=weight2)
                        except Exception:
                            pass
                        gpu_line = next((line for line in lines if 'GPU' in line), '')
                        status = status_main + (f" · {gpu_line}" if gpu_line else '')
                        specs = '\n'.join(lines[2:]) if len(lines) > 2 else specs
                        specs = specs.replace('查看详情', '').strip()
                        rt_low = row_text.lower()
                        sp_low = specs.lower()
                        if ((('无卡' in row_text) or ('no gpu' in rt_low)) or ('无卡' in specs) or ('no gpu' in sp_low)) and (('运行中' in status_main) or ('running' in status_main.lower())):
                            status = f"{status} · 无卡模式"
                data_list.append({'remark': remark, 'device_name': device_name, 'status': status, 'specs': specs, 'device_id': device_id, 'release_time': release_time})
            except Exception:
                continue
        return data_list

    def _compute_device_hash(self, table_data):
        try:
            pairs = []
            for d in table_data or []:
                id_ = (d.get('device_id') or d.get('device_name') or '').strip()
                st = (d.get('status') or '').strip()
                pairs.append(f"{id_}|{st}")
            pairs.sort()
            return '|#|'.join(pairs)
        except Exception:
            try:
                return str(len(table_data or []))
            except Exception:
                return '0'

    def autodl_start(self, device_id=None, remark=None):
        if self.autodl_busy:
            self.autodl_status_signal.emit('正在执行任务，请稍候...')
            return
        self.autodl_busy = True
        def start_thread():
            try:
                self.autodl_status_signal.emit(f'准备开机: device_id={device_id or "<空>"}, 备注={remark or "<空>"}')
                self._goto_instance_list()
                row = None
                if device_id and len(device_id) >= 6:
                    try:
                        row = self._find_row_by_device_id(device_id)
                    except Exception:
                        row = None
                if row is None and remark:
                    try:
                        row = self._find_row_by_remark(remark)
                    except Exception:
                        row = None
                if row is None:
                    raise NoSuchElementException('未定位到设备行')
                self.autodl_driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", row)
                time.sleep(0.3)
                did = device_id or self._extract_id_from_row(row)
                rem = remark or self._extract_remark_from_row(row)
                self.autodl_status_signal.emit('正在确认开机...')
                ok_click = self._start_by_row(row)
                if not ok_click:
                    raise Exception('开机点击失败')
                self.autodl_status_signal.emit('开机指令已发送')
                self.await_running_device_id = did
                self.await_running_remark = rem
                def wait_for_running(timeout=120, interval=4):
                    start_t = time.time()
                    fail_count = 0
                    while time.time() - start_t < timeout:
                        try:
                            # 只有在驱动正常时才刷新，如果驱动挂了，直接抛异常触发熔断
                            self.autodl_driver.title 
                            
                            self._goto_instance_list()
                            r = None
                            if did:
                                try:
                                    r = self._find_row_by_device_id(did)
                                except Exception:
                                    r = None
                            if r is None and rem:
                                try:
                                    r = self._find_row_by_remark(rem)
                                except Exception:
                                    r = None
                            
                            if r is None:
                                self.autodl_status_signal.emit('等待列表刷新...')
                                self.autodl_refresh_devices_quick(True)
                                time.sleep(interval)
                                continue
                            
                            tds2 = r.find_elements(By.TAG_NAME, 'td')
                            st = tds2[1].text if len(tds2) >= 2 else r.text
                            sl = st.lower()
                            
                            if ('运行中' in st) or ('running' in sl):
                                return True
                            
                            if any(k in st for k in ['开机中','正在开机','启动中','正在启动','starting','booting']):
                                self.autodl_status_signal.emit('设备正在开机中，请稍候...')
                                self.autodl_refresh_devices_quick(True)
                                time.sleep(interval)
                                continue
                                
                            # 其他状态（如关机中、已关机等）
                            self.autodl_refresh_devices_quick(True)
                            time.sleep(interval)
                            fail_count = 0 # 只要操作成功就重置错误计数
                        except Exception as e:
                            fail_count += 1
                            self._log_to_file(f"等待开机过程中出现异常({fail_count}/5): {str(e)}")
                            if fail_count >= 5:
                                self.autodl_status_signal.emit('驱动响应异常，开机确认任务强制中断')
                                break
                            time.sleep(interval)
                    return False
                ok = wait_for_running()
                if ok:
                    self.autodl_status_signal.emit('设备已运行')
                    if not self.is_connected and not self.is_connecting:
                        try:
                            self.autodl_status_signal.emit('正在点击JupyterLab...')
                            self.autodl_click_jupyterlab(did, rem)
                        except Exception:
                            pass
                        connected = False
                        try:
                            connected = bool(self._connect_using_device_config(did))
                        except Exception:
                            connected = False
                        if not connected:
                            try:
                                self.autodl_status_signal.emit('尝试从网页复制登录信息并连接...')
                                self._try_copy_and_connect(did, rem)
                            except Exception:
                                pass
                else:
                    self.autodl_status_signal.emit('开机状态未切换为运行中')
                self.autodl_refresh_devices_quick()
            except NoSuchElementException:
                self.autodl_status_signal.emit('开机失败：未找到开机按钮或设备行')
            except TimeoutException:
                self.autodl_status_signal.emit('确认开机超时')
            except Exception as e:
                self.autodl_status_signal.emit(f'开机失败: {str(e)}')
            finally:
                self.autodl_busy = False
                if 'ok' in locals() and ok:
                    self.autodl_status_signal.emit('开机任务完成')
        threading.Thread(target=start_thread, daemon=True).start()

    def autodl_start_only(self, device_id=None, remark=None):
        if self.autodl_busy:
            self.autodl_status_signal.emit('正在执行任务，请稍候...')
            return
        self.autodl_busy = True
        def start_thread():
            try:
                self.autodl_status_signal.emit(f'准备开机: device_id={device_id or "<空>"}, 备注={remark or "<空>"}')
                self._goto_instance_list()
                row = None
                if device_id and len(device_id) >= 6:
                    try:
                        row = self._find_row_by_device_id(device_id)
                    except Exception:
                        row = None
                if row is None and remark:
                    try:
                        row = self._find_row_by_remark(remark)
                    except Exception:
                        row = None
                if row is None:
                    raise NoSuchElementException('未定位到设备行')
                self.autodl_driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", row)
                time.sleep(0.3)
                did = device_id or self._extract_id_from_row(row)
                rem = remark or self._extract_remark_from_row(row)
                self.autodl_status_signal.emit('正在确认开机...')
                ok_click = self._start_by_row(row)
                if not ok_click:
                    raise Exception('开机点击失败')
                self.autodl_status_signal.emit('开机指令已发送')
                self.await_running_device_id = did
                self.await_running_remark = rem
                def wait_for_running(timeout=120, interval=4):
                    start_t = time.time()
                    fail_count = 0
                    while time.time() - start_t < timeout:
                        try:
                            self.autodl_driver.title
                            self._goto_instance_list()
                            r = None
                            if did:
                                try: r = self._find_row_by_device_id(did)
                                except: r = None
                            if r is None and rem:
                                try: r = self._find_row_by_remark(rem)
                                except: r = None
                            
                            if r is None:
                                self.autodl_refresh_devices_quick(True)
                                time.sleep(interval)
                                continue
                            
                            tds2 = r.find_elements(By.TAG_NAME, 'td')
                            st = tds2[1].text if len(tds2) >= 2 else r.text
                            sl = st.lower()
                            if ('运行中' in st) or ('running' in sl):
                                return True
                            
                            if any(k in st for k in ['开机中','正在开机','启动中','正在启动','starting','booting']):
                                self.autodl_refresh_devices_quick(True)
                                time.sleep(interval)
                                continue
                            
                            self.autodl_refresh_devices_quick(True)
                            time.sleep(interval)
                            fail_count = 0
                        except Exception as e:
                            fail_count += 1
                            if fail_count >= 5: break
                            time.sleep(interval)
                    return False
                ok = wait_for_running()
                if ok:
                    self.autodl_status_signal.emit('设备已运行')
                else:
                    self.autodl_status_signal.emit('开机状态未切换为运行中')
                self.autodl_refresh_devices_quick()
            except NoSuchElementException:
                self.autodl_status_signal.emit('开机失败：未找到开机按钮或设备行')
            except TimeoutException:
                self.autodl_status_signal.emit('确认开机超时')
            except Exception as e:
                self.autodl_status_signal.emit(f'开机失败: {str(e)}')
            finally:
                self.autodl_busy = False
                if 'ok' in locals() and ok:
                    self.autodl_status_signal.emit('开机任务完成')
        threading.Thread(target=start_thread, daemon=True).start()

    def autodl_start_nogpu(self, device_id=None, remark=None):
        if self.autodl_busy:
            self.autodl_status_signal.emit('正在执行任务，请稍候...')
            return
        self.autodl_busy = True
        def start_thread():
            try:
                self.autodl_status_signal.emit(f'准备无卡开机: device_id={device_id or "<空>"}, 备注={remark or "<空>"}')
                self._goto_instance_list()
                row = None
                if device_id and len(device_id) >= 6:
                    try:
                        row = self._find_row_by_device_id(device_id)
                    except Exception:
                        row = None
                if row is None and remark:
                    try:
                        row = self._find_row_by_remark(remark)
                    except Exception:
                        row = None
                if row is None:
                    raise NoSuchElementException('未定位到设备行')
                self.autodl_driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", row)
                time.sleep(0.2)
                did = device_id or self._extract_id_from_row(row)
                rem = remark or self._extract_remark_from_row(row)
                self.await_running_device_id = did
                self.await_running_remark = rem
                click_sent = False
                try:
                    click_sent = bool(self._start_nogpu_by_row(row))
                except Exception:
                    self.autodl_status_signal.emit('无卡开机点击动作异常，进入状态监控')
                
                try:
                    tds = row.find_elements(By.TAG_NAME, 'td')
                    st = tds[1].text if len(tds) >= 2 else row.text
                    sl = st.lower()
                    if any(k in st for k in ['开机中','正在开机','启动中','正在启动']) or any(k in sl for k in ['pending','starting','booting']):
                         click_sent = True
                         self.autodl_status_signal.emit(f'检测到设备状态变更: {st}')
                except Exception:
                    pass

                if click_sent:
                    self.autodl_status_signal.emit('无卡开机指令已发送')
                else:
                    self.autodl_status_signal.emit('未确认点击成功(可能已在开机中)，继续监控状态变化')
                r_run = self._wait_for_running_nogpu(device_id=did, remark=rem, timeout=300, interval=4)
                if r_run:
                    self.autodl_status_signal.emit('设备已运行（无卡模式）')
                    self.await_running_device_id = None
                    self.await_running_remark = None
                else:
                    self.autodl_status_signal.emit('无卡开机后状态未切换为运行中或未显示无卡模式')
                self.autodl_refresh_devices_quick(silent=True)
            except NoSuchElementException:
                self.autodl_status_signal.emit('无卡开机失败：未找到更多菜单或设备行')
            except TimeoutException:
                self.autodl_status_signal.emit('无卡开机确认超时')
            except Exception as e:
                self.autodl_status_signal.emit(f'无卡开机失败: {str(e)}')
            finally:
                self.autodl_busy = False
                self.autodl_status_signal.emit('开机任务完成')
        threading.Thread(target=start_thread, daemon=True).start()

    def autodl_stop(self, device_id=None, remark=None):
        if self.autodl_busy:
            self.autodl_status_signal.emit('正在执行任务，请稍候...')
            return
        self.autodl_busy = True
        def stop_thread():
            try:
                # 1. 确保 Driver 存活
                if not self._ensure_driver_alive():
                    # 如果 Driver 无效且无法自动恢复
                    if not self.autodl_driver:
                        self.autodl_status_signal.emit('浏览器未启动，请先登录')
                        return

                self.autodl_status_signal.emit(f'准备关机: device_id={device_id or "<空>"}, 备注={remark or "<空>"}')
                
                # 2. 尝试定位设备行，增加重试机制
                row = None
                for attempt in range(3): # 增加到 3 次重试
                    try:
                        self._goto_instance_list()
                        # 显式等待表格渲染完成，至少要有一行数据
                        WebDriverWait(self.autodl_driver, 10).until(
                            lambda d: len(d.find_elements(By.CSS_SELECTOR, ".el-table__body tr")) > 0 or d.find_elements(By.CSS_SELECTOR, ".el-table__empty-text")
                        )
                        
                        # 额外等待 0.5s 确保文本渲染
                        time.sleep(0.5)
                        
                        if device_id and len(device_id) >= 6:
                            row = self._find_row_by_device_id(device_id)
                        if row is None and remark:
                            row = self._find_row_by_remark(remark)
                        
                        if row:
                            break
                    except Exception as e:
                        if attempt < 2:
                            wait_t = 2 * (attempt + 1)
                            self.autodl_status_signal.emit(f'定位行失败，{wait_t}秒后刷新重试...')
                            self._click_refresh_btn()
                            time.sleep(wait_t)
                        else:
                            self._debug_page_state('关机定位失败现场')
                            raise e

                if row is None:
                    raise NoSuchElementException('未定位到设备行')

                # 3. 执行关机点击逻辑
                self.autodl_driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", row)
                time.sleep(0.3)
                
                did = device_id or self._extract_id_from_row(row)
                rem = remark or self._extract_remark_from_row(row)
                
                self.autodl_status_signal.emit('正在确认关机...')
                ok_click = self._stop_by_row(row)
                if not ok_click:
                    raise Exception('关机点击失败')
                
                self.autodl_status_signal.emit('关机指令已发送')
                def wait_for_stopped(timeout=120, interval=5):
                    start_t = time.time()
                    fail_count = 0
                    while time.time() - start_t < timeout:
                        try:
                            self.autodl_driver.title
                            self._goto_instance_list()
                            r = None
                            if did:
                                try: r = self._find_row_by_device_id(did)
                                except: r = None
                            if r is None and rem:
                                try: r = self._find_row_by_remark(rem)
                                except: r = None
                            
                            if r is None:
                                self.autodl_refresh_devices_quick(True)
                                time.sleep(interval)
                                continue
                            
                            tds2 = r.find_elements(By.TAG_NAME, 'td')
                            st = tds2[1].text if len(tds2) >= 2 else r.text
                            stl = st.lower()
                            if ('已关机' in st) or ('stopped' in stl):
                                return True
                            
                            if any(k in st for k in ['关机中','正在关机','停止中','关闭中']) or any(k in stl for k in ['shutting','stopping']):
                                self.autodl_refresh_devices_quick(True)
                                time.sleep(interval)
                                continue
                            self.autodl_refresh_devices_quick(True)
                            time.sleep(interval)
                            fail_count = 0
                        except Exception as e:
                            fail_count += 1
                            if fail_count >= 5: break
                            time.sleep(interval)
                    return False
                ok = wait_for_stopped()
                if ok:
                    self.autodl_status_signal.emit('设备已关机')
                    self.disconnect()
                else:
                    self.autodl_status_signal.emit('关机状态未切换为已关机')
                self.autodl_refresh_devices_quick()
            except NoSuchElementException:
                self.autodl_status_signal.emit('关机失败：未找到关机按钮或设备行')
            except TimeoutException:
                self.autodl_status_signal.emit('确认关机超时')
            except Exception as e:
                self.autodl_status_signal.emit(f'关机失败: {str(e)}')
            finally:
                self.autodl_busy = False
                if 'ok' in locals() and ok:
                    self.autodl_status_signal.emit('关机任务完成')
        threading.Thread(target=stop_thread, daemon=True).start()

    # ── 实时同步设备状态到UI ──
    def _sync_device_table_from_page(self):
        """从当前网页抓取设备表格数据并同步到UI，供后台任务调用"""
        try:
            rows = self.autodl_driver.find_elements(By.CSS_SELECTOR, '.el-table__body tr')
            if rows:
                table_data = self._format_rows_for_table(rows)
                self.update_device_table_signal.emit(table_data)
        except Exception:
            pass

    def _click_refresh_btn(self):
        """点击页面上的刷新按钮，等待数据真正刷新完成"""
        try:
            self.autodl_driver.execute_script("""
                var btn = document.querySelector('button.refresh-btn') ||
                          document.querySelector('i.el-icon-refresh-right');
                if (btn) {
                    if (btn.tagName === 'I') btn = btn.closest('button') || btn;
                    btn.click();
                }
            """)
            # 等待刷新完成：检测 loading 遮罩出现→消失，或短暂等待数据请求返回
            try:
                # 先等 loading 出现（最多0.5秒，可能很快闪过）
                WebDriverWait(self.autodl_driver, 0.5).until(
                    lambda d: d.find_elements(By.CSS_SELECTOR, '.el-loading-mask, .el-loading-spinner'))
            except Exception:
                pass
            # 再等 loading 消失 + 表格行存在（最多3秒）
            try:
                WebDriverWait(self.autodl_driver, 3).until(
                    lambda d: (
                        not d.find_elements(By.CSS_SELECTOR, '.el-loading-mask[style*="display: none"], .el-loading-spinner') or
                        not any(el.is_displayed() for el in d.find_elements(By.CSS_SELECTOR, '.el-loading-mask, .el-loading-spinner'))
                    ) and len(d.find_elements(By.CSS_SELECTOR, '.el-table__body tr')) > 0
                )
            except Exception:
                time.sleep(0.8)  # 兜底短等
        except Exception:
            pass

    # ── 任务状态栏 ──
    def _show_task_bar(self, msg=''):
        self._task_status_text.value = msg
        self._task_bar.visible = True
        self.safe_update()

    def _update_task_bar(self, msg):
        self._task_status_text.value = msg
        self.safe_update()

    def _hide_task_bar(self):
        self._task_bar.visible = False
        self.safe_update()

    # ── 一键关机 ──
    def _on_shutdown_all_click(self, e=None):
        """关闭所有运行中的设备，多标签页并行"""
        if self.autodl_busy:
            self.autodl_status_signal.emit('正在执行任务，请稍候...')
            return
        if not self.autodl_driver:
            self.autodl_status_signal.emit('浏览器未启动，请先登录')
            return
        self.autodl_busy = True
        self._renew_cancel = False
        self.autodl_shutdown_all_button.disabled = True
        self.autodl_renew_button.disabled = True
        self._show_task_bar('正在扫描运行中的设备...')

        def shutdown_thread():
            try:
                self._goto_instance_list()
                self._click_refresh_btn()
                time.sleep(0.5)
                rows = self.autodl_driver.find_elements(By.CSS_SELECTOR, '.el-table__body tr')
                self._sync_device_table_from_page()

                import re as _re
                running_list = []
                for row in rows:
                    try:
                        if not row.is_displayed():
                            continue
                        cells = row.find_elements(By.TAG_NAME, 'td')
                        if not cells:
                            continue
                        col1 = (cells[0].text or '').strip()
                        lines = [ln.strip() for ln in col1.split('\n') if ln.strip()]
                        name = lines[0] if lines else '未知'
                        dev_id = ''
                        for ln in lines[1:]:
                            if _re.fullmatch(r'[a-fA-F0-9\-]{6,}', ln):
                                dev_id = ln
                                break
                        if self._is_running_row(row):
                            running_list.append({'device_id': dev_id, 'name': name})
                    except StaleElementReferenceException:
                        continue
                    except Exception:
                        continue

                if not running_list:
                    self.autodl_status_signal.emit('没有运行中的设备')
                    self._update_task_bar('没有运行中的设备')
                    time.sleep(2)
                    self._finish_shutdown_all()
                    return

                self._log_to_file(f'一键关机: 发现 {len(running_list)} 台运行中')
                self._update_task_bar(f'正在关闭 {len(running_list)} 台设备...')

                if len(running_list) == 1:
                    # 只有一台，直接在当前标签页关
                    dev = running_list[0]
                    did = dev['device_id']
                    try:
                        self._goto_instance_list()
                        self._click_refresh_btn()
                        row = self._find_row_by_device_id(did)
                        if self._is_running_row(row):
                            self._update_task_bar(f'关机: {dev["name"]}')
                            self._stop_by_row(row)
                            r = self._renew_wait_stopped(did, timeout=120)
                            if r:
                                self.autodl_status_signal.emit(f'✓ {dev["name"]} 已关机')
                            else:
                                self.autodl_status_signal.emit(f'✗ {dev["name"]} 关机超时')
                    except Exception as ex:
                        self._log_to_file(f'一键关机异常: {ex}')
                        self.autodl_status_signal.emit(f'关机失败: {ex}')
                else:
                    # 多台：多标签页并行关机
                    self._do_shutdown_all_parallel(running_list)

                # 最终同步
                try:
                    self._goto_instance_list()
                    self._click_refresh_btn()
                    self._sync_device_table_from_page()
                except Exception:
                    pass

            except Exception as ex:
                self._log_to_file(f'一键关机异常: {ex}')
                self.autodl_status_signal.emit(f'一键关机失败: {ex}')
            finally:
                time.sleep(2)
                self._finish_shutdown_all()

        threading.Thread(target=shutdown_thread, daemon=True).start()

    def _do_shutdown_all_parallel(self, running_list):
        """多标签页并行关机"""
        main_handle = self.autodl_driver.current_window_handle
        target_url = 'https://www.autodl.com/console/instance/list'

        # JS: 只做关机→等关机
        shutdown_js = """
        (function(deviceId) {
            window.__sdResult = {phase:'init', status:'pending', error:'', log:[]};
            var POLL_MS = 3000, MAX_STOP = 120000;

            function addLog(msg) {
                window.__sdResult.log.push(new Date().toLocaleTimeString() + ' ' + msg);
            }
            function findRow() {
                var rows = document.querySelectorAll('.el-table__body tr');
                for (var i = 0; i < rows.length; i++) {
                    if (rows[i].textContent.indexOf(deviceId) >= 0) return rows[i];
                }
                return null;
            }
            function getStatus(row) {
                var tds = row.querySelectorAll('td');
                return tds.length >= 2 ? tds[1].textContent : '';
            }
            function isStopped(s) { return s.indexOf('已关机') >= 0 || s.toLowerCase().indexOf('stopped') >= 0; }
            function isRunning(s) { return s.indexOf('运行中') >= 0 || s.toLowerCase().indexOf('running') >= 0; }
            function findBtn(row, label) {
                var tds = row.querySelectorAll('td');
                var act = tds[tds.length - 1];
                var bs = act.querySelectorAll('button');
                for (var i = 0; i < bs.length; i++) {
                    if (bs[i].textContent.trim().indexOf(label) >= 0) return bs[i];
                }
                return null;
            }
            function clickDropdownItem(row, itemText, cb) {
                var tds = row.querySelectorAll('td');
                var act = tds[tds.length - 1];
                var trigger = act.querySelector('.el-dropdown') ||
                              act.querySelector('.el-icon-more') ||
                              act.querySelector('[class*="el-dropdown"]');
                if (!trigger) {
                    var spans = act.querySelectorAll('span, a, button');
                    for (var i = 0; i < spans.length; i++) {
                        if (spans[i].textContent.trim().indexOf('更多') >= 0) { trigger = spans[i]; break; }
                    }
                }
                if (!trigger) { addLog('未找到更多触发器'); cb(false); return; }
                var root = trigger.closest('button,.el-dropdown,[role="button"]') || trigger;
                root.click();
                var n = 0;
                var iv = setInterval(function() {
                    n++;
                    var menus = Array.from(document.querySelectorAll('.el-dropdown-menu,.el-popper')).filter(function(m){return m.offsetParent!==null;});
                    for (var mi = 0; mi < menus.length; mi++) {
                        var lis = menus[mi].querySelectorAll('li, *');
                        for (var li = 0; li < lis.length; li++) {
                            if (lis[li].textContent.trim().indexOf(itemText) >= 0) {
                                lis[li].click(); clearInterval(iv);
                                setTimeout(function(){ cb(true); }, 300); return;
                            }
                        }
                    }
                    if (n > 20) { clearInterval(iv); cb(false); }
                }, 200);
            }
            function clickConfirm(cb) {
                var n = 0;
                var iv = setInterval(function() {
                    n++;
                    var ds = document.querySelectorAll('.el-message-box, .el-dialog');
                    for (var i = 0; i < ds.length; i++) {
                        if (ds[i].offsetParent !== null) {
                            ds[i].querySelectorAll('input[type=checkbox]').forEach(function(c) { if(!c.checked) c.click(); });
                            var bs = ds[i].querySelectorAll('button');
                            for (var j = 0; j < bs.length; j++) {
                                var t = bs[j].textContent.trim();
                                if (t==='确定'||t==='确认'||/primary/.test(bs[j].className)) {
                                    addLog('点击确认: ' + t);
                                    bs[j].click(); clearInterval(iv);
                                    setTimeout(function(){ cb(true); }, 500); return;
                                }
                            }
                        }
                    }
                    if (n > 40) { clearInterval(iv); addLog('确认框超时'); cb(false); }
                }, 200);
            }
            function reloadAndWait(cb) {
                var refreshBtn = document.querySelector('button.refresh-btn') ||
                                 document.querySelector('i.el-icon-refresh-right');
                if (refreshBtn) {
                    if (refreshBtn.tagName === 'I') refreshBtn = refreshBtn.closest('button') || refreshBtn;
                    refreshBtn.click();
                } else { location.reload(); }
                setTimeout(function() {
                    var n = 0;
                    var iv = setInterval(function() {
                        n++;
                        if (document.querySelectorAll('.el-table__body tr').length > 0) {
                            clearInterval(iv); setTimeout(cb, 300);
                        } else if (n > 50) { clearInterval(iv); cb(); }
                    }, 200);
                }, 800);
            }
            function pollStopped(cb) {
                var t0 = Date.now();
                (function tick() {
                    reloadAndWait(function() {
                        var row = findRow();
                        if (!row) { addLog('轮询时找不到行'); cb(false); return; }
                        var s = getStatus(row);
                        var brief = s.split('\\n')[0];
                        window.__sdResult.lastStatus = brief;
                        addLog('等待关机: ' + brief);
                        if (isStopped(s)) { addLog('已关机'); cb(true); return; }
                        if (Date.now() - t0 > MAX_STOP) { addLog('关机超时'); cb(false); return; }
                        setTimeout(tick, POLL_MS);
                    });
                })();
            }
            function finish(status, error) {
                addLog('完成: ' + status + (error ? ' (' + error + ')' : ''));
                window.__sdResult = {phase:'done', status:status, error:error,
                    log: window.__sdResult.log, lastStatus: window.__sdResult.lastStatus || ''};
            }

            function begin() {
                var row = findRow();
                if (!row) { finish('error', 'row_not_found'); return; }
                var s = getStatus(row);
                var brief = s.split('\\n')[0];
                addLog('初始状态: ' + brief);
                if (isStopped(s)) { finish('ok', 'already_stopped'); return; }
                if (!isRunning(s)) { finish('skip', 'not_running: ' + brief); return; }
                // 点关机
                function afterStopClick() {
                    clickConfirm(function(ok) {
                        addLog('关机确认' + (ok ? '成功' : '失败/无需确认'));
                        window.__sdResult.phase = 'wait_stopped';
                        pollStopped(function(ok2) {
                            finish(ok2 ? 'ok' : 'stop_timeout', '');
                        });
                    });
                }
                var btn = findBtn(row, '关机');
                if (btn) {
                    addLog('点击关机按钮(直接)');
                    btn.scrollIntoView({block:'center'}); btn.click();
                    afterStopClick();
                } else {
                    addLog('直接关机按钮未找到，尝试更多菜单');
                    clickDropdownItem(row, '关机', function(ok) {
                        if (!ok) { finish('error', 'no_stop_btn'); return; }
                        afterStopClick();
                    });
                }
            }

            // 等表格加载后开始
            var n = 0;
            var iv = setInterval(function() {
                n++;
                if (document.querySelectorAll('.el-table__body tr').length > 0) {
                    clearInterval(iv); setTimeout(begin, 500);
                } else if (n > 60) {
                    clearInterval(iv); finish('error', 'table_timeout');
                }
            }, 200);
        })(arguments[0]);
        """

        tab_info = []  # [(device_id, handle, info)]
        for info in running_list:
            if self._renew_cancel:
                break
            did = info['device_id']
            self._update_task_bar(f'打开标签页: {info["name"]} ({len(tab_info)+1}/{len(running_list)})')
            try:
                self.autodl_driver.execute_script("window.open(arguments[0],'_blank');", target_url)
                all_h = self.autodl_driver.window_handles
                new_h = [h for h in all_h if h != main_handle and h not in [t[1] for t in tab_info]][-1]
                self.autodl_driver.switch_to.window(new_h)
                self.autodl_driver.execute_script(shutdown_js, did)
                tab_info.append((did, new_h, info))
            except Exception as ex:
                self._log_to_file(f"一键关机-开标签页异常 {did}: {ex}")

        # 切回主标签页
        try:
            self.autodl_driver.switch_to.window(main_handle)
        except Exception:
            pass

        # 轮询各标签页进度
        pending = {did: (h, info) for did, h, info in tab_info}
        results = {}
        poll_count = 0
        last_sync = 0
        while pending and not self._renew_cancel:
            poll_count += 1
            done_this = []
            for did, (h, info) in list(pending.items()):
                try:
                    self.autodl_driver.switch_to.window(h)
                    r = self.autodl_driver.execute_script("return window.__sdResult||{};")
                except Exception:
                    continue
                if r.get('phase') == 'done':
                    done_this.append(did)
                    st = r.get('status', 'fail')
                    results[did] = st
                    tag = '✓' if st == 'ok' else '✗'
                    self._log_to_file(f"一键关机 {tag} {info['name']}: {st}")
                    # 打印JS日志
                    for line in r.get('log', []):
                        self._log_to_file(f"  JS: {line}")

            for did in done_this:
                pending.pop(did, None)

            # 定期同步UI
            now = time.time()
            if now - last_sync > 6:
                try:
                    self.autodl_driver.switch_to.window(main_handle)
                    self._goto_instance_list()
                    self._click_refresh_btn()
                    self._sync_device_table_from_page()
                    last_sync = now
                except Exception:
                    pass

            if pending:
                ok_n = sum(1 for v in results.values() if v == 'ok')
                self._update_task_bar(f'关机中 已完成{ok_n} 剩余{len(pending)}台')
                time.sleep(3)

        # 关闭所有多余标签页
        try:
            for h in list(self.autodl_driver.window_handles):
                if h != main_handle:
                    try:
                        self.autodl_driver.switch_to.window(h)
                        self.autodl_driver.close()
                    except Exception:
                        pass
            self.autodl_driver.switch_to.window(main_handle)
        except Exception:
            try:
                self.autodl_driver.switch_to.window(main_handle)
            except Exception:
                pass

        # 汇总
        ok_n = sum(1 for v in results.values() if v == 'ok')
        fail_n = sum(1 for v in results.values() if v != 'ok')
        summary = f'一键关机完成: 成功{ok_n} 失败{fail_n} / 共{len(running_list)}台'
        self.autodl_status_signal.emit(summary)
        self._update_task_bar(summary)

    def _finish_shutdown_all(self):
        """一键关机结束清理"""
        self.autodl_busy = False
        self._renew_cancel = False
        self.autodl_shutdown_all_button.disabled = False
        self.autodl_renew_button.disabled = False
        self._hide_task_bar()
        # 恢复自动刷新标签显示
        if self.last_auto_refresh_time > 0:
            diff = int(time.time() - self.last_auto_refresh_time)
            self.autodl_status_label.value = f'已自动刷新 ({diff}秒前)'
        self.safe_update()

    # ── 一键续费 ──
    def _on_renew_click(self, e=None):
        """点击续费按钮 → 分析设备 → 直接执行（无确认框）"""
        if self.autodl_busy:
            self.autodl_status_signal.emit('正在执行任务，请稍候...')
            return
        if not self.autodl_driver:
            self.autodl_status_signal.emit('浏览器未启动，请先登录')
            return
        self.autodl_busy = True
        self._renew_cancel = False
        self.autodl_renew_button.disabled = True
        self.autodl_shutdown_all_button.disabled = True
        self._show_task_bar('正在分析设备状态...')

        def renew_thread():
            try:
                self._log_to_file('续费: 开始分析设备状态')
                self._goto_instance_list()
                try:
                    WebDriverWait(self.autodl_driver, 10).until(
                        lambda d: len(d.find_elements(By.CSS_SELECTOR, ".el-table__body tr")) > 0
                    )
                except Exception:
                    self._update_task_bar('等待设备列表加载...')
                    self._click_refresh_btn()
                    time.sleep(2)
                    WebDriverWait(self.autodl_driver, 10).until(
                        lambda d: len(d.find_elements(By.CSS_SELECTOR, ".el-table__body tr")) > 0
                    )
                time.sleep(1)
                rows = self.autodl_driver.find_elements(By.CSS_SELECTOR, '.el-table__body tr')
                self._sync_device_table_from_page()
                self._log_to_file(f'续费: 找到 {len(rows)} 行')
                gpu_list, nogpu_list, running_list, other_list = [], [], [], []
                import re as _re
                for row in rows:
                    try:
                        if not row.is_displayed():
                            continue
                        cells = row.find_elements(By.TAG_NAME, 'td')
                        if not cells:
                            continue
                        col1 = (cells[0].text or '').strip()
                        lines = [ln.strip() for ln in col1.split('\n') if ln.strip()]
                        name = lines[0] if lines else '未知'
                        dev_id = ''
                        for ln in lines[1:]:
                            if _re.fullmatch(r'[a-fA-F0-9\-]{6,}', ln):
                                dev_id = ln
                                break
                        status_text = (cells[1].text or '').strip() if len(cells) > 1 else ''
                        info = {'device_id': dev_id, 'name': name, 'status_text': status_text}
                        if self._is_running_row(row):
                            running_list.append(info)
                        elif self._is_stopped_row(row):
                            if 'GPU充足' in status_text:
                                gpu_list.append(info)
                            else:
                                nogpu_list.append(info)
                        else:
                            info['status_brief'] = status_text.split('\n')[0] if status_text else '未知'
                            other_list.append(info)
                    except StaleElementReferenceException:
                        continue
                    except Exception:
                        continue

                total = len(gpu_list) + len(nogpu_list) + len(running_list) + len(other_list)
                self._log_to_file(f'续费分类: 有卡={len(gpu_list)} 无卡={len(nogpu_list)} 运行={len(running_list)} 其他={len(other_list)}')
                self._update_task_bar(f'有卡{len(gpu_list)} 无卡{len(nogpu_list)} 运行{len(running_list)} — 开始续费')

                self._renew_plan = {
                    'gpu': gpu_list, 'nogpu': nogpu_list,
                    'running': running_list, 'other': other_list,
                }
                # 直接执行，不弹确认框
                self._do_renew_all()
            except Exception as e:
                self._log_to_file(f'续费异常: {str(e)}')
                self.autodl_status_signal.emit(f'续费失败: {str(e)}')
                self.autodl_busy = False
                self.autodl_renew_button.disabled = False
                self._hide_task_bar()
                self.safe_update()

        threading.Thread(target=renew_thread, daemon=True).start()


    def _on_renew_cancel(self, e=None):
        """取消续费"""
        self._renew_cancel = True
        self._update_task_bar('正在取消续费任务...')
        self.autodl_status_signal.emit('正在取消续费任务...')


    def _do_renew_all(self):
        """执行续费（后台线程）— 主标签页批量操作，不开多标签"""
        plan = getattr(self, '_renew_plan', None)
        if not plan:
            self.autodl_status_signal.emit('续费计划为空')
            self._finish_renew()
            return

        gpu_list = list(plan['gpu'])
        nogpu_list = list(plan['nogpu'])
        running_list = list(plan['running'])
        other_list = list(plan['other'])
        results = {}
        total = len(gpu_list) + len(nogpu_list) + len(running_list) + len(other_list)
        done_count = 0

        def _emit(msg):
            self.autodl_status_signal.emit(msg)
            self._update_task_bar(msg)

        def _refresh_and_sync():
            """刷新页面并同步UI，返回是否成功"""
            try:
                self._click_refresh_btn()
                self._sync_device_table_from_page()
                return True
            except Exception:
                return False

        def _ensure_on_list():
            """确保在实例列表页，仅在需要时导航"""
            try:
                cu = self.autodl_driver.current_url
                if '/console/instance/list' not in cu:
                    self._goto_instance_list()
            except Exception:
                self._goto_instance_list()

        try:
            _ensure_on_list()

            # ── 阶段0a: 过渡状态等待 ──
            if other_list and not self._renew_cancel:
                _emit(f'等待 {len(other_list)} 台过渡状态设备稳定...')
                for info in other_list:
                    if self._renew_cancel: break
                    did = info['device_id']
                    stable = False
                    for attempt in range(12):
                        if self._renew_cancel: break
                        try:
                            _refresh_and_sync()
                            row = self._find_row_by_device_id(did)
                            if self._is_running_row(row):
                                running_list.append(info)
                                stable = True
                                _emit(f'{info["name"]} → 运行中，归入关机队列')
                                break
                            elif self._is_stopped_row(row):
                                if self._gpu_insufficient('', info.get('status_text', '')):
                                    nogpu_list.append(info)
                                else:
                                    gpu_list.append(info)
                                stable = True
                                _emit(f'{info["name"]} → 已关机，归入开机队列')
                                break
                            else:
                                _emit(f'{info["name"]} 仍在过渡中 (第{attempt+1}次检查)')
                        except Exception:
                            pass
                        time.sleep(5)
                    if not stable:
                        results[did] = 'skip'
                        done_count += 1
                        _emit(f'{info["name"]} 状态不稳定，跳过')

            # ── 阶段0b: 关闭已运行设备（批量发指令→统一等待） ──
            if running_list and not self._renew_cancel:
                _emit(f'关闭 {len(running_list)} 台已运行设备...')
                # 先批量发送关机指令
                stop_pending = {}
                for i, info in enumerate(running_list):
                    if self._renew_cancel: break
                    did = info['device_id']
                    try:
                        _refresh_and_sync()
                        row = self._find_row_by_device_id(did)
                        if self._is_running_row(row):
                            _emit(f'关机指令 [{i+1}/{len(running_list)}]: {info["name"]}')
                            self._stop_by_row(row)
                            stop_pending[did] = info
                            time.sleep(0.5)
                        elif self._is_stopped_row(row):
                            _emit(f'{info["name"]} 已关机 ✓')
                            results[did] = 'ok'
                            done_count += 1
                    except Exception as e:
                        self._log_to_file(f"续费-关机指令失败 {did}: {e}")
                        _emit(f'关机指令失败: {info["name"]}')
                        stop_pending[did] = info  # 仍然等待，可能指令已发出

                # 统一轮询等待全部关机
                if stop_pending and not self._renew_cancel:
                    t0 = time.time()
                    timeout_stop0 = 120
                    while stop_pending and not self._renew_cancel:
                        if time.time() - t0 > timeout_stop0:
                            for did, info in stop_pending.items():
                                results[did] = 'ok'  # 超时也算ok，已经续费过了
                                done_count += 1
                                _emit(f'{info["name"]} 关机等待超时，视为已续费')
                            break
                        _refresh_and_sync()
                        done_this = []
                        for did, info in list(stop_pending.items()):
                            try:
                                row = self._find_row_by_device_id(did)
                                if self._is_stopped_row(row):
                                    done_this.append(did)
                                    results[did] = 'ok'
                                    done_count += 1
                                    _emit(f'{info["name"]} 已关机 ✓ ({done_count}/{total})')
                            except Exception:
                                pass
                        for did in done_this:
                            stop_pending.pop(did, None)
                        if stop_pending:
                            elapsed = int(time.time() - t0)
                            _emit(f'等待已运行设备关机: 剩余{len(stop_pending)}台 ({elapsed}s)')
                            time.sleep(3)

            # ── 阶段1: 有卡设备 — 批量有卡开机→等全部运行→批量关机→等全部关机 ──
            gpu_list = [info for info in gpu_list if info['device_id'] not in results]
            nogpu_list = [info for info in nogpu_list if info['device_id'] not in results]
            total = done_count + len(gpu_list) + len(nogpu_list)

            if gpu_list and not self._renew_cancel:
                _emit(f'[有卡] 批量开机 {len(gpu_list)} 台设备...')
                boot_sent = []
                _refresh_and_sync()
                for i, info in enumerate(gpu_list):
                    if self._renew_cancel: break
                    did = info['device_id']
                    _emit(f'[有卡] 开机 [{i+1}/{len(gpu_list)}] {info["name"]}')
                    try:
                        row = self._find_row_by_device_id(did)
                        if self._is_running_row(row):
                            _emit(f'{info["name"]} 已在运行中，跳过开机')
                            boot_sent.append(info)
                            continue
                        if not self._is_stopped_row(row):
                            _emit(f'{info["name"]} 状态异常，跳过')
                            results[did] = 'skip'
                            done_count += 1
                            continue
                        self._start_by_row(row)
                        boot_sent.append(info)
                        _emit(f'{info["name"]} 有卡开机指令已发送')
                        time.sleep(0.8)
                    except Exception as e:
                        self._log_to_file(f"续费-有卡开机异常 {did}: {e}")
                        _emit(f'{info["name"]} 有卡开机失败，转入无卡队列')
                        nogpu_list.append(info)
                        total = done_count + len([x for x in gpu_list if x['device_id'] not in results]) + len(nogpu_list)

                # Step B: 等待所有有卡设备运行中
                if boot_sent and not self._renew_cancel:
                    pending_boot = {info['device_id']: info for info in boot_sent}
                    _emit(f'[有卡] 等待 {len(pending_boot)} 台设备开机...')
                    t0 = time.time()
                    timeout_boot = 300
                    while pending_boot and not self._renew_cancel:
                        if time.time() - t0 > timeout_boot:
                            for did, info in list(pending_boot.items()):
                                _emit(f'{info["name"]} 开机超时，转入无卡队列')
                                nogpu_list.append(info)
                            break
                        _refresh_and_sync()
                        done_this = []
                        for did, info in list(pending_boot.items()):
                            try:
                                row = self._find_row_by_device_id(did)
                                if self._is_running_row(row):
                                    done_this.append(did)
                                    _emit(f'{info["name"]} 已运行 ✓')
                                elif self._is_stopped_row(row):
                                    elapsed = int(time.time() - t0)
                                    if elapsed > 30:
                                        done_this.append(did)
                                        _emit(f'{info["name"]} 开机失败（回到已关机），转入无卡队列')
                                        nogpu_list.append(info)
                            except Exception:
                                pass
                        for did in done_this:
                            pending_boot.pop(did, None)
                        if pending_boot:
                            elapsed = int(time.time() - t0)
                            names = ', '.join(info['name'] for info in pending_boot.values())
                            _emit(f'[有卡] 等待开机: 剩余{len(pending_boot)}台 ({elapsed}s) [{names}]')
                            time.sleep(3)

                # Step C: 批量关机有卡设备
                shutdown_list = [info for info in boot_sent if info['device_id'] not in results and info not in nogpu_list]
                if shutdown_list and not self._renew_cancel:
                    _emit(f'[有卡] 批量关机 {len(shutdown_list)} 台设备...')
                    _refresh_and_sync()
                    for i, info in enumerate(shutdown_list):
                        if self._renew_cancel: break
                        did = info['device_id']
                        try:
                            row = self._find_row_by_device_id(did)
                            if self._is_running_row(row):
                                _emit(f'[有卡] 关机 [{i+1}/{len(shutdown_list)}] {info["name"]}')
                                self._stop_by_row(row)
                                time.sleep(0.5)
                            elif self._is_stopped_row(row):
                                _emit(f'{info["name"]} 已关机 ✓')
                                results[did] = 'ok'
                                done_count += 1
                        except Exception as e:
                            self._log_to_file(f"续费-关机指令失败 {did}: {e}")
                            _emit(f'{info["name"]} 关机指令失败，刷新重试...')
                            try:
                                _refresh_and_sync()
                                row = self._find_row_by_device_id(did)
                                if self._is_running_row(row):
                                    self._stop_by_row(row)
                                    time.sleep(0.5)
                            except Exception:
                                pass

                # Step D: 等待有卡设备全部关机
                pending_stop = [info for info in shutdown_list if info['device_id'] not in results]
                if pending_stop and not self._renew_cancel:
                    _emit(f'[有卡] 等待 {len(pending_stop)} 台设备关机...')
                    t0 = time.time()
                    timeout_stop = 180
                    pending_stop_map = {info['device_id']: info for info in pending_stop}
                    while pending_stop_map and not self._renew_cancel:
                        if time.time() - t0 > timeout_stop:
                            for did, info in list(pending_stop_map.items()):
                                _emit(f'{info["name"]} 关机超时')
                                results[did] = 'fail'
                                done_count += 1
                            break
                        _refresh_and_sync()
                        done_this = []
                        for did, info in list(pending_stop_map.items()):
                            try:
                                row = self._find_row_by_device_id(did)
                                if self._is_stopped_row(row):
                                    done_this.append(did)
                                    results[did] = 'ok'
                                    done_count += 1
                                    _emit(f'{info["name"]} 已关机 ✓ ({done_count}/{total})')
                            except Exception:
                                pass
                        for did in done_this:
                            pending_stop_map.pop(did, None)
                        if pending_stop_map:
                            elapsed = int(time.time() - t0)
                            names = ', '.join(info['name'] for info in pending_stop_map.values())
                            _emit(f'[有卡] 等待关机: 剩余{len(pending_stop_map)}台 ({elapsed}s) [{names}]')
                            time.sleep(3)

            # ── 阶段2: 无卡设备 — 逐台串行：无卡开机→等运行→关机→等关机 ──
            nogpu_list = [info for info in nogpu_list if info['device_id'] not in results]
            if nogpu_list and not self._renew_cancel:
                _emit(f'[无卡] 串行续费 {len(nogpu_list)} 台设备...')
                for i, info in enumerate(nogpu_list):
                    if self._renew_cancel: break
                    did = info['device_id']
                    _emit(f'[无卡] [{i+1}/{len(nogpu_list)}] {info["name"]} — 无卡开机...')
                    try:
                        _refresh_and_sync()
                        row = self._find_row_by_device_id(did)
                        if self._is_running_row(row):
                            _emit(f'{info["name"]} 已在运行中，直接关机')
                        elif self._is_stopped_row(row):
                            self._start_nogpu_by_row(row)
                            _emit(f'{info["name"]} 无卡开机指令已发送，等待运行...')
                            # 等待运行中
                            t0 = time.time()
                            booted = False
                            while time.time() - t0 < 180 and not self._renew_cancel:
                                _refresh_and_sync()
                                try:
                                    row = self._find_row_by_device_id(did)
                                    if self._is_running_row(row):
                                        booted = True
                                        _emit(f'{info["name"]} 已运行 ✓')
                                        break
                                except Exception:
                                    pass
                                elapsed = int(time.time() - t0)
                                _emit(f'[无卡] {info["name"]} 等待开机 ({elapsed}s)')
                                time.sleep(3)
                            if not booted:
                                _emit(f'{info["name"]} 无卡开机超时')
                                results[did] = 'fail'
                                done_count += 1
                                continue
                        else:
                            _emit(f'{info["name"]} 状态异常，跳过')
                            results[did] = 'skip'
                            done_count += 1
                            continue

                        # 关机
                        _emit(f'[无卡] {info["name"]} 关机...')
                        _refresh_and_sync()
                        row = self._find_row_by_device_id(did)
                        if self._is_running_row(row):
                            self._stop_by_row(row)
                            time.sleep(0.5)
                        # 等待关机
                        t0 = time.time()
                        stopped = False
                        while time.time() - t0 < 120 and not self._renew_cancel:
                            _refresh_and_sync()
                            try:
                                row = self._find_row_by_device_id(did)
                                if self._is_stopped_row(row):
                                    stopped = True
                                    break
                            except Exception:
                                pass
                            elapsed = int(time.time() - t0)
                            _emit(f'[无卡] {info["name"]} 等待关机 ({elapsed}s)')
                            time.sleep(3)
                        results[did] = 'ok' if stopped else 'fail'
                        done_count += 1
                        _emit(f'{info["name"]} {"续费完成 ✓" if stopped else "关机超时 ✗"} ({done_count}/{total})')
                    except Exception as e:
                        self._log_to_file(f"续费-无卡串行异常 {did}: {e}")
                        _emit(f'{info["name"]} 无卡续费异常: {e}')
                        results[did] = 'fail'
                        done_count += 1

            # ── 最终同步 ──
            if not self._renew_cancel:
                try:
                    _refresh_and_sync()
                except Exception:
                    pass

            # 汇总
            ok_count = sum(1 for v in results.values() if v == 'ok')
            fail_count = sum(1 for v in results.values() if v == 'fail')
            skip_count = sum(1 for v in results.values() if v == 'skip')
            if self._renew_cancel:
                summary = f'续费已取消 (成功{ok_count} 失败{fail_count} 跳过{skip_count})'
            else:
                summary = f'续费完成: 成功{ok_count} 失败{fail_count} 跳过{skip_count} / 共{total}台'
            self.autodl_status_signal.emit(summary)
            self._update_task_bar(summary)

        except Exception as e:
            self.autodl_status_signal.emit(f'续费异常: {str(e)}')
            self._update_task_bar(f'续费异常: {str(e)}')
        finally:
            time.sleep(3)
            self._finish_renew()

    def _finish_renew(self):
        """续费结束清理"""
        self.autodl_busy = False
        self._renew_cancel = False
        self.autodl_renew_button.disabled = False
        self.autodl_shutdown_all_button.disabled = False
        self._hide_task_bar()
        # 恢复自动刷新标签显示
        if self.last_auto_refresh_time > 0:
            diff = int(time.time() - self.last_auto_refresh_time)
            self.autodl_status_label.value = f'已自动刷新 ({diff}秒前)'
        self.safe_update()

    def _renew_wait_running(self, device_id, timeout=180, interval=3):
        start_t = time.time()
        while time.time() - start_t < timeout:
            if self._renew_cancel:
                return None
            try:
                self._click_refresh_btn()
                self._sync_device_table_from_page()
                row = self._find_row_by_device_id(device_id)
                if self._is_running_row(row):
                    return row
            except Exception:
                pass
            time.sleep(interval)
        return None

    def _renew_wait_stopped(self, device_id, timeout=120, interval=3):
        start_t = time.time()
        while time.time() - start_t < timeout:
            if self._renew_cancel:
                return None
            try:
                self._click_refresh_btn()
                self._sync_device_table_from_page()
                row = self._find_row_by_device_id(device_id)
                if self._is_stopped_row(row):
                    return row
            except Exception:
                pass
            time.sleep(interval)
        return None

    def autodl_forward_only(self, device_id=None, remark=None):
        if self.autodl_busy:
            self.autodl_status_signal.emit('正在执行任务，请稍候...')
            return
        self.autodl_busy = True
        def forward_thread():
            try:
                if self.is_connected:
                    self.autodl_status_signal.emit('已连接，忽略重复连接请求')
                    return
                if self.is_connecting:
                    self.autodl_status_signal.emit('正在连接中，请稍候')
                    return
                did = device_id
                rem = remark
                connected = False
                try:
                    connected = bool(self._connect_using_device_config(did))
                except Exception:
                    connected = False
                if not connected:
                    try:
                        self.autodl_status_signal.emit('尝试从网页复制登录信息并连接...')
                        self._try_copy_and_connect(did, rem)
                    except Exception:
                        pass
            except Exception as e:
                self.autodl_status_signal.emit(f'连接失败: {str(e)}')
            finally:
                self.autodl_busy = False
                self.autodl_status_signal.emit('连接任务完成')
        threading.Thread(target=forward_thread, daemon=True).start()

    def autodl_connect_device(self, device_id=None, remark=None):
        if self.autodl_busy:
            self.autodl_status_signal.emit('正在执行任务，请稍候...')
            return
        self.autodl_busy = True
        def connect_thread():
            try:
                if self.is_connected:
                    self.autodl_status_signal.emit('已连接，忽略重复连接请求')
                    return
                if self.is_connecting:
                    self.autodl_status_signal.emit('正在连接中，请稍候')
                    return
                did = device_id
                rem = remark
                try:
                    self.autodl_status_signal.emit('正在点击JupyterLab...')
                    self.autodl_click_jupyterlab(did, rem)
                except Exception:
                    pass
                connected = False
                try:
                    connected = bool(self._connect_using_device_config(did))
                except Exception:
                    connected = False
                if not connected:
                    try:
                        self.autodl_status_signal.emit('尝试从网页复制登录信息并连接...')
                        self._try_copy_and_connect(did, rem)
                    except Exception:
                        pass
            except Exception as e:
                self.autodl_status_signal.emit(f'连接失败: {str(e)}')
            finally:
                self.autodl_busy = False
                self.autodl_status_signal.emit('连接任务完成')
        threading.Thread(target=connect_thread, daemon=True).start()

    def autodl_click_jupyterlab(self, device_id=None, remark=None):
        try:
            tries = 0
            ok = False
            url = ''
            while tries < 8:
                self._goto_instance_list()
                row = None
                if device_id and len(device_id) >= 6:
                    try:
                        row = self._find_row_by_device_id(device_id)
                    except Exception:
                        row = None
                if row is None and remark:
                    try:
                        row = self._find_row_by_remark(remark)
                    except Exception:
                        row = None
                if row is None:
                    time.sleep(1.0)
                    tries += 1
                    continue
                self.autodl_driver.execute_script("arguments[0].scrollIntoView({block:'center'});", row)
                time.sleep(0.3)
                try:
                    ok, url = self._click_jupyterlab_by_row(row)
                except Exception:
                    ok = False
                    url = ''
                if ok:
                    break
                time.sleep(1.0)
                tries += 1
            if not ok:
                self.autodl_status_signal.emit('JupyterLab点击失败')
                return False
            if url:
                self.autodl_status_signal.emit(f'正在打开浏览器: {url}')
                if self.auto_open_browser_checkbox.value:
                    try:
                        success = webbrowser.open(url)
                        if success:
                            self.autodl_status_signal.emit(f'浏览器已成功打开: {url}')
                        else:
                            self.autodl_status_signal.emit('无法打开浏览器，请手动访问: ' + url)
                    except Exception as e:
                        self.autodl_status_signal.emit(f'打开浏览器时出错: {str(e)}，请手动访问: ' + url)
            self.autodl_status_signal.emit('已点击JupyterLab')
            return True
        except Exception as e:
            self.autodl_status_signal.emit(f'点击JupyterLab失败: {str(e)}')
            return False

    def autodl_click_autopanel(self, device_id=None, remark=None):
        try:
            tries = 0
            ok = False
            url = ''
            while tries < 8:
                self._goto_instance_list()
                row = None
                if device_id and len(device_id) >= 6:
                    try:
                        row = self._find_row_by_device_id(device_id)
                    except Exception:
                        row = None
                if row is None and remark:
                    try:
                        row = self._find_row_by_remark(remark)
                    except Exception:
                        row = None
                if row is None:
                    time.sleep(1.0)
                    tries += 1
                    continue
                self.autodl_driver.execute_script("arguments[0].scrollIntoView({block:'center'});", row)
                time.sleep(0.3)
                try:
                    ok, url = self._click_autopanel_by_row(row)
                except Exception:
                    ok = False
                    url = ''
                if ok:
                    break
                time.sleep(1.0)
                tries += 1
            if not ok:
                self.autodl_status_signal.emit('AutoPanel点击失败')
                return False
            if url:
                self.autodl_status_signal.emit(f'正在打开浏览器: {url}')
                if self.auto_open_browser_checkbox.value:
                    try:
                        success = webbrowser.open(url)
                        if success:
                            self.autodl_status_signal.emit(f'浏览器已成功打开: {url}')
                        else:
                            self.autodl_status_signal.emit('无法打开浏览器，请手动访问: ' + url)
                    except Exception as e:
                        self.autodl_status_signal.emit(f'打开浏览器时出错: {str(e)}，请手动访问: ' + url)
            self.autodl_status_signal.emit('已点击AutoPanel')
            return True
        except Exception as e:
            self.autodl_status_signal.emit(f'点击AutoPanel失败: {str(e)}')
            return False

    def _click_jupyterlab_by_row(self, row):
        tds = row.find_elements(By.TAG_NAME, 'td')
        action_td = tds[-1] if tds else row
        btn = None
        got_url = ''
        candidates = [
            ".//a[contains(normalize-space(), 'JupyterLab')]",
            ".//a[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'jupyterlab')]",
            ".//button[.//span[contains(normalize-space(), 'JupyterLab')]]",
            ".//*[contains(@class,'el-button') and .//span[contains(normalize-space(),'JupyterLab')]]",
            ".//span[contains(@class,'el-button__text') and contains(normalize-space(),'JupyterLab')]",
            ".//*[@title][contains(translate(@title,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'jupyter')]",
            ".//*[@aria-label][contains(translate(@aria-label,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'jupyter')]",
            ".//a[contains(@href,'lab') or contains(@href,'jupyter') or contains(@href,'/lab') ]",
        ]
        for xp in candidates:
            try:
                btn = action_td.find_element(By.XPATH, xp)
                try:
                    href = btn.get_attribute('href')
                    if href:
                        got_url = href
                except Exception:
                    pass
                break
            except Exception:
                continue
        if btn is None:
            for xp in candidates:
                try:
                    btn = row.find_element(By.XPATH, xp)
                    try:
                        href = btn.get_attribute('href')
                        if href:
                            got_url = href
                    except Exception:
                        pass
                    break
                except Exception:
                    continue
        if btn is None:
            try:
                js_el = self.autodl_driver.execute_script(
                    "const row=arguments[0];\n"
                    "const r=row.getBoundingClientRect();\n"
                    "const all=[...document.querySelectorAll('a,button,[role=link],span,div')];\n"
                    "const cand=all.find(el=>{const t=(el.textContent||'').trim().toLowerCase();\n"
                    "  const href=(el.href||'').toLowerCase();\n"
                    "  const title=(el.getAttribute('title')||'').toLowerCase();\n"
                    "  const aria=(el.getAttribute('aria-label')||'').toLowerCase();\n"
                    "  const lab = t.includes('jupyter') || title.includes('jupyter') || aria.includes('jupyter') || href.includes('lab') || href.includes('jupyter');\n"
                    "  if(!lab) return false;\n"
                    "  const br=el.getBoundingClientRect();\n"
                    "  return br.top>=r.top-2 && br.bottom<=r.bottom+2;\n"
                    "});\n"
                    "return cand||null;",
                    row)
                if js_el:
                    btn = js_el
                    try:
                        href = btn.get_attribute('href')
                        if href:
                            got_url = href
                    except Exception:
                        pass
            except Exception:
                pass
        if btn is None and not got_url:
            try:
                frames = self.autodl_driver.find_elements(By.TAG_NAME, 'iframe')
                for fr in frames:
                    try:
                        if not fr.is_displayed():
                            continue
                        self.autodl_driver.switch_to.frame(fr)
                        cand_in_frame = None
                        for xp in [
                            "//a[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'jupyterlab')]",
                            "//a[contains(@href,'lab') or contains(@href,'jupyter')]",
                            "//button[.//span[contains(translate(normalize-space(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'jupyter')]]",
                        ]:
                            try:
                                cand_in_frame = self.autodl_driver.find_element(By.XPATH, xp)
                                break
                            except Exception:
                                continue
                        if cand_in_frame:
                            try:
                                href = cand_in_frame.get_attribute('href')
                                if href:
                                    got_url = href
                            except Exception:
                                pass
                        self.autodl_driver.switch_to.default_content()
                        break
                    except Exception:
                        self.autodl_driver.switch_to.default_content()
                        continue
            except Exception:
                pass
        if btn is None:
            trigger = None
            triggers = [
                ".//*[contains(@class,'el-dropdown')]",
                ".//*[contains(@class,'el-icon-more')]",
                ".//*[contains(normalize-space(),'更多')]",
            ]
            for tx in triggers:
                try:
                    trigger = action_td.find_element(By.XPATH, tx)
                    break
                except Exception:
                    continue
            if trigger:
                self.autodl_driver.execute_script("arguments[0].scrollIntoView({block:'center'});", trigger)
                try:
                    ActionChains(self.autodl_driver).move_to_element(trigger).click().perform()
                except Exception:
                    self.autodl_driver.execute_script('arguments[0].click();', trigger)
                menu_el = self.autodl_driver.execute_script(
                    "const t=arguments[0];const tr=t.getBoundingClientRect();\n"
                    "const menus=[...document.querySelectorAll('.el-dropdown-menu')].filter(m=>m.offsetParent!==null);\n"
                    "if(menus.length===0){return null;}\n"
                    "let best=null;\n"
                    "for(const m of menus){const r=m.getBoundingClientRect();const d=Math.hypot((r.left-tr.left),(r.top-tr.bottom));\n"
                    " if(!best||d<best.d){best={el:m,d:d};}}\n"
                    "return best?best.el:null;",
                    trigger)
                if menu_el:
                    found_href = self.autodl_driver.execute_script(
                        "const menu=arguments[0];\n"
                        "const items=[...menu.querySelectorAll('*')];\n"
                        "const target=items.find(n=>/jupyterlab/i.test((n.textContent||'').trim()));\n"
                        "let href='';\n"
                        "if(target){const a=target.closest('a')||target.querySelector('a'); if(a&&a.href){href=a.href;} target.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));}\n"
                        "return href;",
                        menu_el)
                    if isinstance(found_href, str) and found_href:
                        got_url = found_href
                    btn = None
        if btn is None and not got_url:
            raise NoSuchElementException('未找到JupyterLab按钮')
        self.autodl_driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
        ActionChains(self.autodl_driver).move_to_element(btn).pause(0.2).perform()
        try:
            WebDriverWait(self.autodl_driver, 5).until(EC.element_to_be_clickable(btn))
            handles_before = list(self.autodl_driver.window_handles)
            btn.click()
        except ElementClickInterceptedException:
            self.autodl_driver.execute_script('arguments[0].click();', btn)
            handles_before = list(self.autodl_driver.window_handles)
        time.sleep(0.5)
        handles_after = list(self.autodl_driver.window_handles)
        if len(handles_after) > len(handles_before):
            new_handles = [h for h in handles_after if h not in handles_before]
            for h in new_handles:
                try:
                    self.autodl_driver.switch_to.window(h)
                    cu = self.autodl_driver.current_url
                    if cu:
                        got_url = cu
                    self.autodl_driver.close()
                except Exception:
                    pass
            self.autodl_driver.switch_to.window(handles_before[0])
        return True, got_url

    def _click_autopanel_by_row(self, row):
        tds = row.find_elements(By.TAG_NAME, 'td')
        action_td = tds[-1] if tds else row
        btn = None
        got_url = ''
        candidates = [
            ".//a[contains(normalize-space(), 'AutoPanel')]",
            ".//a[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'autopanel')]",
            ".//button[.//span[contains(normalize-space(), 'AutoPanel')]]",
            ".//*[contains(@class,'el-button') and .//span[contains(normalize-space(),'AutoPanel')]]",
            ".//span[contains(@class,'el-button__text') and contains(normalize-space(),'AutoPanel')]",
            ".//*[@title][contains(translate(@title,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'autopanel')]",
            ".//*[@aria-label][contains(translate(@aria-label,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'autopanel')]",
            ".//a[contains(@href,'autopanel') or contains(@href,'/panel') ]",
        ]
        for xp in candidates:
            try:
                btn = action_td.find_element(By.XPATH, xp)
                try:
                    href = btn.get_attribute('href')
                    if href:
                        got_url = href
                except Exception:
                    pass
                break
            except Exception:
                continue
        if btn is None:
            for xp in candidates:
                try:
                    btn = row.find_element(By.XPATH, xp)
                    try:
                        href = btn.get_attribute('href')
                        if href:
                            got_url = href
                    except Exception:
                        pass
                    break
                except Exception:
                    continue
        if btn is None:
            try:
                js_el = self.autodl_driver.execute_script(
                    "const row=arguments[0];\n"
                    "const r=row.getBoundingClientRect();\n"
                    "const all=[...document.querySelectorAll('a,button,[role=link],span,div')];\n"
                    "const cand=all.find(el=>{const t=(el.textContent||'').trim().toLowerCase();\n"
                    "  const href=(el.href||'').toLowerCase();\n"
                    "  const title=(el.getAttribute('title')||'').toLowerCase();\n"
                    "  const aria=(el.getAttribute('aria-label')||'').toLowerCase();\n"
                    "  const lab = t.includes('autopanel') || title.includes('autopanel') || aria.includes('autopanel') || href.includes('autopanel');\n"
                    "  if(!lab) return false;\n"
                    "  const br=el.getBoundingClientRect();\n"
                    "  return br.top>=r.top-2 && br.bottom<=r.bottom+2;\n"
                    "});\n"
                    "return cand||null;",
                    row)
                if js_el:
                    btn = js_el
                    try:
                        href = btn.get_attribute('href')
                        if href:
                            got_url = href
                    except Exception:
                        pass
            except Exception:
                pass
        if btn is None:
            trigger = None
            triggers = [
                ".//*[contains(@class,'el-dropdown')]",
                ".//*[contains(@class,'el-icon-more')]",
                ".//*[contains(normalize-space(),'更多')]",
            ]
            for tx in triggers:
                try:
                    trigger = action_td.find_element(By.XPATH, tx)
                    break
                except Exception:
                    continue
            if trigger:
                self.autodl_driver.execute_script("arguments[0].scrollIntoView({block:'center'});", trigger)
                try:
                    ActionChains(self.autodl_driver).move_to_element(trigger).click().perform()
                except Exception:
                    self.autodl_driver.execute_script('arguments[0].click();', trigger)
                menu_el = self.autodl_driver.execute_script(
                    "const t=arguments[0];const tr=t.getBoundingClientRect();\n"
                    "const menus=[...document.querySelectorAll('.el-dropdown-menu')].filter(m=>m.offsetParent!==null);\n"
                    "if(menus.length===0){return null;}\n"
                    "let best=null;\n"
                    "for(const m of menus){const r=m.getBoundingClientRect();const d=Math.hypot((r.left-tr.left),(r.top-tr.bottom));\n"
                    " if(!best||d<best.d){best={el:m,d:d};}}\n"
                    "return best?best.el:null;",
                    trigger)
                if menu_el:
                    found_href = self.autodl_driver.execute_script(
                        "const menu=arguments[0];\n"
                        "const items=[...menu.querySelectorAll('*')];\n"
                        "const target=items.find(n=>/AutoPanel/i.test((n.textContent||'').trim()));\n"
                        "let href='';\n"
                        "if(target){const a=target.closest('a')||target.querySelector('a'); if(a&&a.href){href=a.href;} target.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));}\n"
                        "return href;",
                        menu_el)
                    if isinstance(found_href, str) and found_href:
                        got_url = found_href
                    btn = None
        if btn is None and not got_url:
            raise NoSuchElementException('未找到AutoPanel按钮')
        self.autodl_driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
        ActionChains(self.autodl_driver).move_to_element(btn).pause(0.2).perform()
        try:
            WebDriverWait(self.autodl_driver, 5).until(EC.element_to_be_clickable(btn))
            handles_before = list(self.autodl_driver.window_handles)
            btn.click()
        except ElementClickInterceptedException:
            self.autodl_driver.execute_script('arguments[0].click();', btn)
            handles_before = list(self.autodl_driver.window_handles)
        time.sleep(0.5)
        handles_after = list(self.autodl_driver.window_handles)
        if len(handles_after) > len(handles_before):
            new_handles = [h for h in handles_after if h not in handles_before]
            for h in new_handles:
                try:
                    self.autodl_driver.switch_to.window(h)
                    cu = self.autodl_driver.current_url
                    if cu:
                        got_url = cu
                    self.autodl_driver.close()
                except Exception:
                    pass
            self.autodl_driver.switch_to.window(handles_before[0])
        return True, got_url

    def _start_by_row(self, row):
        tds = row.find_elements(By.TAG_NAME, 'td')
        action_td = tds[-1] if tds else row
        btn = None
        candidates = [
            ".//button[.//span[contains(normalize-space(), '开机')]]",
            ".//a[contains(normalize-space(), '开机')]",
            ".//*[contains(@class,'el-button') and .//span[contains(normalize-space(),'开机')]]",
            ".//span[contains(@class,'el-button__text') and contains(normalize-space(),'开机')]",
        ]
        for xp in candidates:
            try:
                btn = action_td.find_element(By.XPATH, xp)
                break
            except Exception:
                continue
        if btn is None:
            trigger = None
            triggers = [
                ".//*[contains(@class,'el-dropdown')]",
                ".//*[contains(@class,'el-icon-more')]",
                ".//*[contains(normalize-space(),'更多')]",
            ]
            for tx in triggers:
                try:
                    trigger = action_td.find_element(By.XPATH, tx)
                    break
                except Exception:
                    continue
            if trigger:
                self.autodl_driver.execute_script("arguments[0].scrollIntoView({block:'center'});", trigger)
                try:
                    ActionChains(self.autodl_driver).move_to_element(trigger).click().perform()
                except Exception:
                    self.autodl_driver.execute_script('arguments[0].click();', trigger)
                menu_el = self.autodl_driver.execute_script(
                    "const t=arguments[0];const tr=t.getBoundingClientRect();\n"
                    "const menus=[...document.querySelectorAll('.el-dropdown-menu')].filter(m=>m.offsetParent!==null);\n"
                    "if(menus.length===0){return null;}\n"
                    "let best=null;\n"
                    "for(const m of menus){const r=m.getBoundingClientRect();const d=Math.hypot((r.left-tr.left),(r.top-tr.bottom));\n"
                    " if(!best||d<best.d){best={el:m,d:d};}}\n"
                    "return best?best.el:null;",
                    trigger)
                if menu_el:
                    self.autodl_driver.execute_script(
                        "const menu=arguments[0];\n"
                        "const items=[...menu.querySelectorAll('*')];\n"
                        "const target=items.find(n=>/开机/.test((n.textContent||'').trim()));\n"
                        "if(target){target.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));}",
                        menu_el)
                    btn = None
        if btn is None:
            raise NoSuchElementException('未找到开机按钮')
        self.autodl_driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
        ActionChains(self.autodl_driver).move_to_element(btn).pause(0.2).perform()
        try:
            WebDriverWait(self.autodl_driver, 5).until(EC.element_to_be_clickable(btn))
            btn.click()
        except ElementClickInterceptedException:
            self.autodl_driver.execute_script('arguments[0].click();', btn)
        # 增加对确认按钮的精准定位
        cands = [
            "//div[contains(@class,'el-message-box')]//button[.//span[contains(normalize-space(),'确定')]]",
            "//div[contains(@class,'el-dialog')]//button[.//span[contains(normalize-space(),'确定')]]",
            "//div[contains(@class,'el-popconfirm')]//button[.//span[contains(normalize-space(),'确定')]]",
            "//button[contains(@class, 'el-button--primary') and .//span[contains(normalize-space(),'确定')]]",
        ]
        btn2 = None
        # 尝试在页面上寻找可见的对话框
        try:
            dialog = WebDriverWait(self.autodl_driver, 5).until(
                lambda d: next((el for el in d.find_elements(By.XPATH, "//div[contains(@class,'el-message-box') or contains(@class,'el-dialog')]") if el.is_displayed()), None)
            )
            if dialog:
                for xp in [".//button[.//span[contains(normalize-space(),'确定')]]", ".//button[contains(@class,'primary')]"]:
                    try:
                        btn2 = dialog.find_element(By.XPATH, xp)
                        if btn2: break
                    except: continue
        except:
            pass

        if not btn2:
            for xp in cands:
                try:
                    btn2 = WebDriverWait(self.autodl_driver, 3).until(EC.element_to_be_clickable((By.XPATH, xp)))
                    if btn2.is_displayed():
                        break
                    else:
                        btn2 = None
                except:
                    continue
        
        if not btn2:
            raise TimeoutException('未找到关机确认按钮')
            
        try:
            self.autodl_driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn2)
            time.sleep(0.2)
            btn2.click()
        except Exception:
            self.autodl_driver.execute_script('arguments[0].click();', btn2)
        return True

    def _start_nogpu_by_row(self, row):
        tds = row.find_elements(By.TAG_NAME, 'td')
        action_td = tds[-1] if tds else row
        trigger = None
        triggers = [
            ".//*[contains(@class,'el-dropdown')]",
            ".//*[contains(@class,'el-icon-more')]",
            ".//*[contains(normalize-space(),'更多')]",
        ]
        for tx in triggers:
            try:
                trigger = action_td.find_element(By.XPATH, tx)
                break
            except Exception:
                continue
        if not trigger:
            for tx in triggers:
                try:
                    trigger = row.find_element(By.XPATH, tx)
                    break
                except Exception:
                    continue
        if not trigger:
            raise NoSuchElementException('未找到更多菜单触发器')
        self.autodl_driver.execute_script("arguments[0].scrollIntoView({block:'center'});", trigger)
        try:
            WebDriverWait(self.autodl_driver, 8).until(EC.element_to_be_clickable(trigger))
        except Exception:
            pass
        try:
            ActionChains(self.autodl_driver).move_to_element(trigger).pause(0.02).perform()
        except Exception:
            try:
                ActionChains(self.autodl_driver).move_to_element(trigger).click().perform()
            except Exception:
                pass
        try:
            self.autodl_driver.execute_script(
                """
                const t=arguments[0];
                const root=t.closest('button, .el-dropdown, [role=\"button\"]')||t;
                try{ root.click(); }
                catch(e){ root.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true})); }
                """,
                trigger
            )
        except Exception:
            self.autodl_driver.execute_script('arguments[0].click();', trigger)
        menu_el = self.autodl_driver.execute_script(
            "const t=arguments[0];const tr=t.getBoundingClientRect();\n"
            "const menus=[...document.querySelectorAll('.el-dropdown-menu')].filter(m=>m.offsetParent!==null);\n"
            "if(menus.length===0){return null;}\n"
            "let best=null;\n"
            "for(const m of menus){const r=m.getBoundingClientRect();const d=Math.hypot((r.left-tr.left),(r.top-tr.bottom));\n"
            " if(!best||d<best.d){best={el:m,d:d};}}\n"
            "return best?best.el:null;",
            trigger)
        if not menu_el:
            raise NoSuchElementException('未找到下拉菜单')
        item = None
        for xp in [
            "//ul[contains(@class,'el-dropdown-menu')]//li[.//span[contains(normalize-space(),'无卡模式开机')] or contains(normalize-space(),'无卡模式开机')]",
            "//div[contains(@class,'el-popper')]//li[.//span[contains(normalize-space(),'无卡模式开机')] or contains(normalize-space(),'无卡模式开机')]",
            "//*[contains(@class,'el-dropdown-menu') or contains(@class,'el-popper')]//li[contains(normalize-space(),'无卡模式开机')]",
        ]:
            try:
                cand = WebDriverWait(self.autodl_driver, 1).until(EC.presence_of_element_located((By.XPATH, xp)))
                if cand and cand.is_displayed():
                    item = cand
                    break
            except Exception:
                continue
        if item is None:
            try:
                lis = self.autodl_driver.find_elements(By.XPATH, "//*[contains(@class,'el-dropdown-menu') or contains(@class,'el-popper')]//li")
                for cand in lis:
                    try:
                        txt = (cand.text or '').strip()
                        low = (txt or '').lower()
                        if ('无卡' in txt) or ('no gpu' in low) or ('cpu' in low):
                            if cand.is_displayed():
                                item = cand
                                break
                    except Exception:
                        continue
            except Exception:
                pass
        clicked = False
        if item:
            for _ in range(6):
                try:
                    cls = (item.get_attribute('class') or '')
                    aria = (item.get_attribute('aria-disabled') or '')
                    if ('is-disabled' in cls) or (str(aria).lower() == 'true'):
                        time.sleep(0.5)
                        continue
                    WebDriverWait(self.autodl_driver, 2).until(EC.element_to_be_clickable(item))
                    break
                except Exception:
                    time.sleep(0.3)
            self.autodl_driver.execute_script("arguments[0].scrollIntoView({block:'center'});", item)
            try:
                ActionChains(self.autodl_driver).move_to_element(item).pause(0.02).click(item).perform()
                clicked = True
            except Exception:
                try:
                    self.autodl_driver.execute_script('arguments[0].click();', item)
                    clicked = True
                except Exception:
                    clicked = False
        if not clicked:
            try:
                clicked = self.autodl_driver.execute_script(
                    "const sels=['.el-dropdown-menu','.el-popper'];\n"
                    "const menus=sels.flatMap(s=>[...document.querySelectorAll(s)]).filter(m=>m.offsetParent!==null);\n"
                    "for(const menu of menus){const items=[...menu.querySelectorAll('*')];\n"
                    "  const target=items.find(n=>/(无卡模式开机)/.test((n.textContent||'').trim()));\n"
                    "  if(target){target.click(); return true;}}\n"
                    "return false;"
                )
            except Exception:
                clicked = False
        if not clicked:
            try:
                ok2 = self.autodl_driver.execute_script(
                    "const sels=['.el-dropdown-menu','.el-popper'];\n"
                    "const menus=sels.flatMap(s=>[...document.querySelectorAll(s)]).filter(m=>m.offsetParent!==null);\n"
                    "for(const menu of menus){const items=[...menu.querySelectorAll('*')];\n"
                    "  const target=items.find(n=>/(无卡模式开机)/.test((n.textContent||'').trim()));\n"
                    "  if(target){const r=target.getBoundingClientRect();\n"
                    "    const x=r.left + r.width/2, y=r.top + r.height/2;\n"
                    "    const el=document.elementFromPoint(x,y);\n"
                    "    if(el){el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true})); return true;}}}\n"
                    "return false;"
                )
                clicked = bool(ok2)
            except Exception:
                clicked = False
        if not clicked:
            raise NoSuchElementException('菜单中未找到无卡开机项')
        try:
            WebDriverWait(self.autodl_driver, 5).until(EC.presence_of_element_located((
                By.XPATH,
                "//div[contains(@class,'el-message') or contains(@class,'el-notification')]//*[contains(normalize-space(),'成功') or contains(normalize-space(),'已发送') or contains(normalize-space(),'操作成功')]"
            )))
        except Exception:
            pass
        cands = [
            "//div[contains(@class,'el-message-box')]//button[.//span[contains(normalize-space(),'确定')]]",
            "//div[contains(@class,'el-dialog__footer')]//button[.//span[contains(normalize-space(),'确定')]]",
            "//div[contains(@class,'el-popconfirm')]//button[.//span[contains(normalize-space(),'确定')]]",
            "//button[.//span[contains(normalize-space(),'确定')]]",
            "//*[contains(normalize-space(),'确定')]/ancestor::button",
            "//button[.//span[contains(normalize-space(),'确认')]]",
            "//*[contains(normalize-space(),'确认')]/ancestor::button",
            "//button[.//span[contains(normalize-space(),'开机')]]",
        ]
        btn2 = None
        for xp in cands:
            try:
                btn2 = WebDriverWait(self.autodl_driver, 6).until(EC.presence_of_element_located((By.XPATH, xp)))
                break
            except TimeoutException:
                continue
        if not btn2:
            if self._is_running_row(row):
                return True
            raise TimeoutException('未找到确认按钮')
        try:
            box = btn2.find_element(By.XPATH, "ancestor::div[contains(@class,'el-message-box') or contains(@class,'el-dialog') or contains(@class,'el-popconfirm')]")
        except Exception:
            box = None
        if box is not None:
            try:
                self.autodl_driver.execute_script(
                    "const box=arguments[0]; const cbs=[...box.querySelectorAll('input[type=checkbox], .el-checkbox')];\n"
                    "for(const c of cbs){ try{ if(c.tagName==='INPUT'){ if(!c.checked){ c.click(); } } else { const inp=c.querySelector('input'); if(inp && !inp.checked){ inp.click(); } } }catch(e){} }",
                    box
                )
                self.autodl_driver.execute_script(
                    "const box=arguments[0]; const rads=[...box.querySelectorAll('.el-radio')];\n"
                    "for(const r of rads){ const inp=r.querySelector('input[type=radio]');\n"
                    "  try{ if(inp && !inp.checked){ r.click(); break; } }catch(e){} }",
                    box
                )
                self.autodl_driver.execute_script(
                    "const box=arguments[0]; const sws=[...box.querySelectorAll('.el-switch')];\n"
                    "for(const s of sws){ try{ if(!(s.className||'').includes('is-checked')){ s.click(); } }catch(e){} }",
                    box
                )
            except Exception:
                pass
        try:
            self.autodl_driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn2)
            ActionChains(self.autodl_driver).move_to_element(btn2).pause(0.05).perform()
            WebDriverWait(self.autodl_driver, 5).until(EC.element_to_be_clickable(btn2))
            btn2.click()
        except ElementClickInterceptedException:
            self.autodl_driver.execute_script('arguments[0].click();', btn2)
        except Exception:
            self.autodl_driver.execute_script('arguments[0].click();', btn2)
        try:
            ok_toast = WebDriverWait(self.autodl_driver, 6).until(EC.presence_of_element_located((
                By.XPATH,
                "//div[contains(@class,'el-message') or contains(@class,'el-notification')]//*[contains(normalize-space(),'成功') or contains(normalize-space(),'已发送') or contains(normalize-space(),'操作成功') or contains(normalize-space(),'开机中') or contains(normalize-space(),'启动中')]"
            )))
            if ok_toast:
                return True
        except Exception:
            pass
        if self._is_running_row(row):
            return True
        return False

    def _stop_by_row(self, row):
        tds = row.find_elements(By.TAG_NAME, 'td')
        action_td = tds[-1] if tds else row
        btn = None
        candidates = [
            ".//button[.//span[contains(normalize-space(), '关机')]]",
            ".//a[contains(normalize-space(), '关机')]",
            ".//*[contains(@class,'el-button') and .//span[contains(normalize-space(),'关机')]]",
            ".//span[contains(@class,'el-button__text') and contains(normalize-space(),'关机')]",
        ]
        for xp in candidates:
            try:
                btn = action_td.find_element(By.XPATH, xp)
                break
            except Exception:
                continue
        if btn is None:
            trigger = None
            triggers = [
                ".//*[contains(@class,'el-dropdown')]",
                ".//*[contains(@class,'el-icon-more')]",
                ".//*[contains(normalize-space(),'更多')]",
            ]
            for tx in triggers:
                try:
                    trigger = action_td.find_element(By.XPATH, tx)
                    break
                except Exception:
                    continue
            if trigger:
                self.autodl_driver.execute_script("arguments[0].scrollIntoView({block:'center'});", trigger)
                try:
                    ActionChains(self.autodl_driver).move_to_element(trigger).click().perform()
                except Exception:
                    self.autodl_driver.execute_script('arguments[0].click();', trigger)
                menu_el = self.autodl_driver.execute_script(
                    "const t=arguments[0];const tr=t.getBoundingClientRect();\n"
                    "const menus=[...document.querySelectorAll('.el-dropdown-menu')].filter(m=>m.offsetParent!==null);\n"
                    "if(menus.length===0){return null;}\n"
                    "let best=null;\n"
                    "for(const m of menus){const r=m.getBoundingClientRect();const d=Math.hypot((r.left-tr.left),(r.top-tr.bottom));\n"
                    " if(!best||d<best.d){best={el:m,d:d};}}\n"
                    "return best?best.el:null;",
                    trigger)
                if menu_el:
                    self.autodl_driver.execute_script(
                        "const menu=arguments[0];\n"
                        "const items=[...menu.querySelectorAll('*')];\n"
                        "const target=items.find(n=>/关机/.test((n.textContent||'').trim()));\n"
                        "if(target){target.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));}",
                        menu_el)
                    btn = None
        if btn is None:
            raise NoSuchElementException('未找到关机按钮')
        self.autodl_driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
        ActionChains(self.autodl_driver).move_to_element(btn).pause(0.2).perform()
        try:
            WebDriverWait(self.autodl_driver, 5).until(EC.element_to_be_clickable(btn))
            btn.click()
        except ElementClickInterceptedException:
            self.autodl_driver.execute_script('arguments[0].click();', btn)
        cands = [
            "//div[contains(@class,'el-message-box')]//button[.//span[contains(normalize-space(),'确定')]]",
            "//div[contains(@class,'el-dialog__footer')]//button[.//span[contains(normalize-space(),'确定')]]",
            "//div[contains(@class,'el-popconfirm')]//button[.//span[contains(normalize-space(),'确定')]]",
            "//button[.//span[contains(normalize-space(),'确定')]]",
            "//*[contains(normalize-space(),'确定')]/ancestor::button",
        ]
        btn2 = None
        for xp in cands:
            try:
                btn2 = WebDriverWait(self.autodl_driver, 5).until(EC.presence_of_element_located((By.XPATH, xp)))
                break
            except TimeoutException:
                continue
        if not btn2:
            raise TimeoutException('未找到确认按钮')
        try:
            self.autodl_driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn2)
            ActionChains(self.autodl_driver).move_to_element(btn2).pause(0.1).perform()
            WebDriverWait(self.autodl_driver, 5).until(EC.element_to_be_clickable(btn2))
            btn2.click()
        except ElementClickInterceptedException:
            self.autodl_driver.execute_script('arguments[0].click();', btn2)
        except Exception:
            self.autodl_driver.execute_script('arguments[0].click();', btn2)
        return True

    def _click_and_get_clipboard(self, element):
        try:
            self.autodl_driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
            try:
                ActionChains(self.autodl_driver).move_to_element(element).click().perform()
            except Exception:
                self.autodl_driver.execute_script('arguments[0].click();', element)
            if pyperclip:
                prev = pyperclip.paste()
                start = time.time()
                while time.time() - start < 3:
                    txt = pyperclip.paste()
                    if txt and txt != prev:
                        return txt.strip()
                    time.sleep(0.1)
                return pyperclip.paste().strip()
            else:
                return ''
        except Exception:
            return ''

    def _copy_ssh_from_row(self, row):
        cmd = ''
        pwd = ''
        try:
            candidates_cmd = [
                ".//*[contains(normalize-space(),'登录命令')]/following::*[contains(@class,'copy') or contains(@class,'document')][1]",
                ".//*[contains(normalize-space(),'登录指令')]/following::*[contains(@class,'copy') or contains(@class,'document')][1]",
                ".//*[contains(normalize-space(),'SSH命令')]/following::*[contains(@class,'copy') or contains(@class,'document')][1]",
            ]
            for xp in candidates_cmd:
                try:
                    el = row.find_element(By.XPATH, xp)
                    cmd = self._click_and_get_clipboard(el)
                    if cmd:
                        break
                except Exception:
                    continue
        except Exception:
            pass
        try:
            candidates_pwd = [
                ".//*[contains(normalize-space(),'认证密码')]/following::*[contains(@class,'copy') or contains(@class,'document')][1]",
                ".//*[contains(normalize-space(),'SSH密码')]/following::*[contains(@class,'copy') or contains(@class,'document')][1]",
                ".//*[contains(normalize-space(),'密码')]/following::*[contains(@class,'copy') or contains(@class,'document')][1]",
            ]
            for xp in candidates_pwd:
                try:
                    el = row.find_element(By.XPATH, xp)
                    pwd = self._click_and_get_clipboard(el)
                    if pwd:
                        break
                except Exception:
                    continue
        except Exception:
            pass
        return cmd, pwd

    def _try_copy_and_connect(self, dev_id=None, remark=None):
        try:
            self._goto_instance_list()
            r = None
            if dev_id:
                try:
                    r = self._find_row_by_device_id(dev_id)
                except Exception:
                    r = None
            if r is None and remark:
                try:
                    r = self._find_row_by_remark(remark)
                except Exception:
                    r = None
            if r is None:
                return False
            self.autodl_driver.execute_script("arguments[0].scrollIntoView({block:'center'});", r)
            time.sleep(0.2)
            cmd, pwd = self._copy_ssh_from_row(r)
            if cmd:
                self.ssh_info_input.value = cmd
                self.auto_parse_ssh_info(None)
            if pwd:
                self.password_input.value = pwd
            if not self.remote_port_input.value.strip():
                self.remote_port_input.value = '7860'
            if self.ssh_info_input.value.strip() and self.password_input.value:
                self.connect()
                return True
            return False
        except Exception:
            return False

    def _connect_using_device_config(self, device_id):
        try:
            m = self._load_device_map()
            cfg_name = m.get(device_id)
            if not cfg_name:
                self.update_status_signal.emit('未找到该设备的配置，请在左侧填写并保存')
                return False
            cfg_path = os.path.join(self.config_dir, f'{cfg_name}.json')
            if not os.path.exists(cfg_path):
                self.update_status_signal.emit('配置文件不存在，请重新保存')
                return False
            with open(cfg_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            ssh_info = str(data.get('ssh_info', '')).strip()
            remote_port = str(data.get('remote_port', '')).strip()
            password = str(data.get('password', '')).strip()
            if not ssh_info or not remote_port or not password:
                self.update_status_signal.emit('配置未填写完整（SSH、端口、密码），请在左侧补全')
                return False
            self.ssh_info_input.value = ssh_info
            self.remote_port_input.value = remote_port
            self.password_input.value = password
            self.auto_open_browser_checkbox.value = bool(data.get('auto_open_browser', True))
            self.connect()
            return True
        except Exception as e:
            self.update_status_signal.emit(f'加载设备配置失败: {str(e)}')
            return False

    def _open_device_config_dialog(self, device_id, remark, gpu_specs, location_name):
        display_name = f"{remark}-{gpu_specs}-{location_name}".strip()
        display_name = self._sanitize_name(display_name)
        name_label = ft.Text(display_name)
        ssh_edit = ft.TextField(label="SSH 连接")
        port_edit = ft.TextField(label="远程端口")
        pwd_edit = ft.TextField(label="密码", password=True)
        open_cb = ft.Checkbox(label="连接成功后自动打开浏览器", value=True)
        m = self._load_device_map()
        cfg_name = m.get(device_id)
        if cfg_name:
            cfg_path = os.path.join(self.config_dir, f'{cfg_name}.json')
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
                    ssh_edit.value = existing.get('ssh_info', '')
                    port_edit.value = existing.get('remote_port', '')
                    pwd_edit.value = existing.get('password', '')
                    open_cb.value = existing.get('auto_open_browser', True)
        dlg = ft.AlertDialog(
            title=ft.Text("设置连接信息"),
            content=ft.Column(
                controls=[
                    ft.Text("显示名称:"),
                    name_label,
                    ssh_edit,
                    port_edit,
                    pwd_edit,
                    open_cb,
                ],
                tight=True,
            ),
            actions=[
                ft.TextButton("保存", on_click=lambda e: self._save_device_config(dlg, device_id, remark, display_name, ssh_edit.value, port_edit.value, pwd_edit.value, open_cb.value)),
                ft.TextButton("取消", on_click=lambda e: self.close_dialog(dlg)),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.dialog = dlg
        dlg.open = True
        self.safe_update()

    def _save_device_config(self, dlg, device_id, remark, display_name, ssh_info, remote_port, password, auto_open):
        if not ssh_info or not remote_port or not password:
            self.show_message("不完整", "请填写SSH、端口与密码")
            return
        safe_name = self._sanitize_name(display_name) or (device_id[-6:] if device_id else '设备')
        m = self._load_device_map()
        cfg_name = m.get(device_id)
        if not cfg_name:
            cfg_name = safe_name
            cfg_path = os.path.join(self.config_dir, f'{cfg_name}.json')
            if os.path.exists(cfg_path):
                try:
                    with open(cfg_path, 'r', encoding='utf-8') as f:
                        existing = json.load(f)
                    if existing.get('device_id') and existing.get('device_id') != device_id:
                        cfg_name = f"{safe_name}-{device_id[-6:]}"
                except:
                    cfg_name = f"{safe_name}-{device_id[-6:]}"
        data = {
            'ssh_info': ssh_info,
            'remote_port': remote_port,
            'password': password,
            'auto_open_browser': auto_open,
            'saved_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'device_id': device_id,
            'remark': display_name,
        }
        cfg_path = os.path.join(self.config_dir, f'{cfg_name}.json')
        try:
            with open(cfg_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            m[device_id] = cfg_name
            self._save_device_map(m)
            self.load_config_list()
            self.show_message("保存成功", "连接信息已保存")
            self.close_dialog(dlg)
        except Exception as e:
            self.show_message("错误", str(e))

    # ---------- 辅助方法 ----------
    def _load_device_map(self):
        try:
            if self.device_map_file and os.path.exists(self.device_map_file):
                with open(self.device_map_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data if isinstance(data, dict) else {}
        except Exception:
            pass
        return {}

    def _save_device_map(self, m):
        try:
            os.makedirs(self.config_dir, exist_ok=True)
            with open(self.device_map_file, 'w', encoding='utf-8') as f:
                json.dump(m, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _sanitize_name(self, s):
        try:
            base = (s or '').strip()
            if not base:
                return ''
            import re as _re
            base = _re.sub(r"[^\w\-\_\u4e00-\u9fa5]", '_', base)
            base = _re.sub(r"_+", '_', base)
            return base[:64]
        except Exception:
            return s or ''

    def _gpu_insufficient(self, status_text, specs_text):
        try:
            s = (status_text or '') + '\n' + (specs_text or '')
            if 'GPU充足' in s:
                return False
            return True
        except Exception:
            return True

    def _goto_instance_list(self):
        target_url = 'https://www.autodl.com/console/instance/list'
        try:
            cu = self.autodl_driver.current_url
        except Exception:
            cu = ''
        if '/console/instance/list' not in cu:
            try:
                self.autodl_driver.get(target_url)
            except Exception:
                pass
        try:
            WebDriverWait(self.autodl_driver, 4).until(lambda d: d.find_elements(By.CSS_SELECTOR, '.el-table__body tr') or d.find_elements(By.CSS_SELECTOR, '.el-table__empty-text'))
        except Exception:
            try:
                WebDriverWait(self.autodl_driver, 4).until(EC.presence_of_element_located((By.TAG_NAME, 'table')))
            except Exception:
                pass
        return True

    def _find_row_by_device_id(self, device_id):
        self._log_to_file(f"正在尝试定位 ID: {device_id}")
        # 获取所有行，手动遍历匹配文本
        rows = self.autodl_driver.find_elements(By.CSS_SELECTOR, ".el-table__body tr")
        for row in rows:
            try:
                txt = row.text
                if device_id in txt:
                    self._log_to_file(f"通过文本匹配找到设备行: {device_id}")
                    return row
            except:
                continue
        
        # 如果 CSS 选择器失败，尝试 XPath 兜底
        xpath = f"//*[contains(@class,'el-table__row')]//*[contains(normalize-space(.), '{device_id}')]"
        try:
            el = self.autodl_driver.find_element(By.XPATH, xpath)
            row = el.find_element(By.XPATH, "ancestor-or-self::tr[1]")
            return row
        except:
            pass
            
        raise NoSuchElementException(f"无法在页面中找到包含 ID {device_id} 的行")

    def _find_row_by_remark(self, remark_text):
        self._log_to_file(f"正在尝试定位备注: {remark_text}")
        rows = self.autodl_driver.find_elements(By.CSS_SELECTOR, ".el-table__body tr")
        for row in rows:
            try:
                txt = row.text
                if remark_text in txt:
                    self._log_to_file(f"通过文本匹配找到备注行: {remark_text}")
                    return row
            except:
                continue
        
        # 兜底
        xpath = f"//*[contains(@class,'el-table__row')]//*[contains(normalize-space(), '{remark_text}')]"
        try:
            el = self.autodl_driver.find_element(By.XPATH, xpath)
            row = el.find_element(By.XPATH, "ancestor-or-self::tr[1]")
            return row
        except:
            pass
            
        raise NoSuchElementException(f"无法在页面中找到包含备注 {remark_text} 的行")

    def _extract_id_from_row(self, r):
        import re as _re
        try:
            txt = r.text
            m = _re.search(r'[a-fA-F0-9\-]{6,}', txt)
            return m.group(0) if m else ''
        except Exception:
            return ''

    def _extract_remark_from_row(self, r):
        try:
            lines = [ln.strip() for ln in r.text.split('\n') if ln.strip()]
            import re as _re
            for ln in lines[1:]:
                if '-' in ln and _re.fullmatch(r'[a-fA-F0-9\-]{6,}', ln):
                    continue
                return ln.replace('查看详情', '').strip()
            val = lines[2] if len(lines) >= 3 else ''
            return val.replace('查看详情', '').strip()
        except Exception:
            return ''

    def _has_nogpu_mode(self, row):
        try:
            tds = row.find_elements(By.TAG_NAME, 'td')
            st = tds[1].text if len(tds) >= 2 else row.text
            specs = tds[2].text if len(tds) >= 3 else ''
            s = (st + "\n" + specs)
            sl = s.lower()
            if ('无卡模式' in s) or ('no gpu' in sl) or ('无gpu' in sl):
                return True
            return False
        except Exception:
            return False

    def _is_running_row(self, row):
        try:
            tds = row.find_elements(By.TAG_NAME, 'td')
            st = tds[1].text if len(tds) >= 2 else row.text
            op = tds[-1].text if len(tds) >= 1 else ''
            sl = st.lower()
            if ('运行中' in st) or ('running' in sl):
                return True
            return False
        except Exception:
            return False

    def _is_stopped_row(self, row):
        try:
            tds = row.find_elements(By.TAG_NAME, 'td')
            st = tds[1].text if len(tds) >= 2 else row.text
            sl = st.lower()
            if ('已关机' in st) or ('stopped' in sl):
                return True
            return False
        except Exception:
            return False

    def _wait_until_stopped(self, device_id=None, remark=None, timeout=240, interval=3):
        start_t = time.time()
        last = ''
        while time.time() - start_t < timeout:
            try:
                self._goto_instance_list()
                r = None
                if device_id:
                    try:
                        r = self._find_row_by_device_id(device_id)
                    except Exception:
                        r = None
                if r is None and remark:
                    try:
                        r = self._find_row_by_remark(remark)
                    except Exception:
                        r = None
                if r:
                    try:
                        tds = r.find_elements(By.TAG_NAME, 'td')
                        st = tds[1].text if len(tds) >= 2 else r.text
                        op_td = tds[-1] if len(tds) >= 1 else r
                        if st and st != last:
                            try:
                                self.autodl_status_signal.emit(f'当前状态: {st}')
                            except Exception:
                                pass
                            last = st
                        btn = None
                        for xp in [
                            ".//button[.//span[contains(normalize-space(), '开机')]]",
                            ".//a[contains(normalize-space(), '开机')]",
                            ".//*[contains(@class,'el-button') and .//span[contains(normalize-space(),'开机')]]",
                            ".//span[contains(@class,'el-button__text') and contains(normalize-space(),'开机')]",
                        ]:
                            try:
                                btn = op_td.find_element(By.XPATH, xp)
                                break
                            except Exception:
                                continue
                        stopped = self._is_stopped_row(r)
                        clickable = False
                        if btn is not None:
                            try:
                                WebDriverWait(self.autodl_driver, 2).until(EC.element_to_be_clickable(btn))
                                cls = (btn.get_attribute('class') or '')
                                dis = (btn.get_attribute('disabled') or '')
                                aria = (btn.get_attribute('aria-disabled') or '')
                                clickable = ('is-disabled' not in cls) and (dis == '' or dis is None) and (str(aria).lower() != 'true')
                            except Exception:
                                clickable = False
                        if stopped and clickable:
                            return r
                    except Exception:
                        pass
                self.autodl_refresh_devices_quick(True)
                time.sleep(interval)
            except Exception:
                self.autodl_refresh_devices_quick(True)
                time.sleep(interval)
        return None

    def _wait_for_running_nogpu(self, device_id=None, remark=None, timeout=300, interval=4):
        start_t = time.time()
        last = ''
        fail_count = 0
        while time.time() - start_t < timeout:
            try:
                # 健康检查
                self.autodl_driver.title
                
                self._goto_instance_list()
                r = None
                if device_id:
                    try:
                        r = self._find_row_by_device_id(device_id)
                    except Exception:
                        r = None
                if r is None and remark:
                    try:
                        r = self._find_row_by_remark(remark)
                    except Exception:
                        r = None
                if r and self._is_running_row(r) and self._has_nogpu_mode(r):
                    return r
                try:
                    if r:
                        tds = r.find_elements(By.TAG_NAME, 'td')
                        st = tds[1].text if len(tds) >= 2 else r.text
                        specs = tds[2].text if len(tds) >= 3 else ''
                        now = (st + " | " + specs).strip()
                        if now and now != last:
                            try:
                                self.autodl_status_signal.emit(f'当前状态列/规格详情: {now}')
                            except Exception:
                                pass
                            last = now
                        sl = st.lower()
                        if any(k in st for k in ['开机中','正在开机','启动中','正在启动']) or any(k in sl for k in ['pending','starting','booting']):
                            self.autodl_refresh_devices_quick(True)
                            time.sleep(interval)
                            continue
                except Exception:
                    pass
                self.autodl_refresh_devices_quick(True)
                time.sleep(interval)
                fail_count = 0
            except Exception as e:
                fail_count += 1
                if fail_count >= 5:
                    self._log_to_file(f"无卡开机监控因驱动异常中断: {str(e)}")
                    break
                time.sleep(interval)
        return None

    def apply_theme(self):
        if not self.running or not self.page:
            return
        try:
            if self.current_theme == 'dark':
                # 在赋值前后再次检查，并捕获可能的异步调度异常
                try: self.page.theme_mode = ft.ThemeMode.DARK
                except: pass
                self.theme_button.icon = ft.Icons.LIGHT_MODE
            else:
                try: self.page.theme_mode = ft.ThemeMode.LIGHT
                except: pass
                self.theme_button.icon = ft.Icons.DARK_MODE
            self.safe_update()
        except Exception as e:
            err_str = str(e).lower()
            if any(k in err_str for k in ["after shutdown", "closed", "event loop"]):
                pass
            else:
                self._log_to_file(f"apply_theme error: {e}")

    def toggle_theme(self, e=None):
        if self.page.theme_mode == ft.ThemeMode.LIGHT:
            self.current_theme = 'dark'
        else:
            self.current_theme = 'light'
        self._save_theme_pref()
        self.apply_theme()

    def open_readme(self, e=None):
        try:
            p = self.readme_path
            if not p or not os.path.exists(p):
                p = self._ensure_readme_file()
            if p and os.path.exists(p):
                os.startfile(p)
            else:
                self.show_message("提示", "未找到使用说明文件")
        except Exception as e:
            self.show_message("错误", f"打开说明文件失败: {str(e)}")

    def on_config_combo_change(self, e):
        self.load_selected_config(e)

    def _persist_login_prefs(self, e=None):
        try:
            if not os.path.exists(self.autodl_credentials_file):
                # 尝试创建空文件如果不存在
                pass

            credentials = {}
            try:
                if os.path.exists(self.autodl_credentials_file):
                    with open(self.autodl_credentials_file, 'r', encoding='utf-8') as f:
                        credentials = json.load(f)
            except Exception:
                pass

            credentials['auto_login'] = bool(self.auto_login_checkbox.value)
            credentials['show_password'] = bool(self.show_autodl_password_checkbox.value)
            credentials['silent_refresh'] = bool(self.silent_refresh_checkbox.value)
            credentials['browser_mode'] = self.browser_mode_group.value
            credentials['theme'] = getattr(self, 'current_theme', 'light')
            credentials['collapse_login'] = not self._login_area.visible
            
            if 'username' not in credentials or not credentials['username']:
                credentials['username'] = self.autodl_username_input.value.strip()
            else:
                # 更新用户名
                credentials['username'] = self.autodl_username_input.value.strip()

            # 如果选中记住密码，保存密码
            credentials['remember_password'] = bool(self.remember_password_checkbox.value)
            if credentials['remember_password']:
                pwd = self.autodl_password_input.value
                if pwd:
                    enc = _win_dpapi_encrypt(pwd)
                    if enc:
                        credentials['password'] = enc
            else:
                credentials['password'] = ''
            
            with open(self.autodl_credentials_file, 'w', encoding='utf-8') as f:
                json.dump(credentials, f, ensure_ascii=False, indent=2)
                
        except Exception:
            pass

    def load_autodl_credentials(self):
        try:
            if os.path.exists(self.autodl_credentials_file):
                with open(self.autodl_credentials_file, 'r', encoding='utf-8') as f:
                    credentials = json.load(f)
                try:
                    self.auto_login_checkbox.value = bool(credentials.get('auto_login', False))
                    self.show_autodl_password_checkbox.value = bool(credentials.get('show_password', False))
                    self.silent_refresh_checkbox.value = bool(credentials.get('silent_refresh', True))
                    self.browser_mode_group.value = credentials.get('browser_mode', 'visible')
                    # 恢复登录区折叠状态
                    if credentials.get('collapse_login', False):
                        self._login_area.visible = False
                        self._login_collapse_btn.icon = ft.Icons.EXPAND_MORE
                        self._login_collapse_btn.tooltip = "展开登录区"
                    theme = credentials.get('theme', None)
                    if not theme:
                        self.current_theme = 'light'
                    else:
                        self.current_theme = theme
                except Exception:
                    pass

                if credentials.get('remember_password', False):
                    username = credentials.get('username', '')
                    password = credentials.get('password', '')
                    if username:
                        self.autodl_username_input.value = username
                    if password:
                        try:
                            dec = _win_dpapi_decrypt(password)
                            if dec is not None:
                                password = dec
                        except Exception:
                            pass
                        self.autodl_password_input.value = password
                    self.remember_password_checkbox.value = True
                    return True
            
        except Exception as e:
            print(f"加载AutoDL凭据失败: {e}")
        
        return False

    def _ensure_autodl_dependencies(self):
        try:
            import selenium
            import webdriver_manager
            return True
        except ImportError:
            if not is_frozen():
                return _pip_install(['selenium', 'webdriver-manager'])
            return False

if __name__ == "__main__":
    app_instance = None

    def main(page: ft.Page):
        global app_instance
        app_instance = FletSSHPortForwarder(page)
        page.on_disconnect = app_instance.cleanup
        atexit.register(app_instance.cleanup)

    _install_asyncio_shutdown_silencer()

    try:
        ft.app(target=main)
    except (KeyboardInterrupt, SystemExit):
        print("\n正在强制退出...")
        if app_instance:
            app_instance.cleanup()
    except Exception as e:
        print(f"程序崩溃: {e}")
        if app_instance:
            app_instance.cleanup()
