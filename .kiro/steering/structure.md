---
inclusion: always
---

# 项目结构与架构指南

## 目录布局

```
.
├── autodl启动器/                # 唯一的生产代码目录
│   ├── flet-v2.py              # 主应用单体文件（~5500行，单类架构）
│   ├── build_exe.py            # PyInstaller 打包脚本
│   ├── requirements.txt        # 生产依赖
│   ├── requirements_autodl.txt # 废弃的 PyQt5 依赖（禁止使用）
│   ├── configs/                # 运行时配置：ChromeDriver、chrome_profile/、JSON
│   ├── test_*.py               # 功能测试（pytest 单独运行）
│   ├── *.spec                  # PyInstaller spec 文件
│   ├── *.py.old                # 归档的旧入口（禁止修改）
│   └── dist/                   # 构建输出
├── assets/                     # icon.ico + make_icon.py
├── autodl_configs/             # 敏感文件：credentials.json、cookies.json（已 gitignore）
├── tests/                      # 集成/分析脚本（非标准 pytest 结构）
├── 项目的灵魂/                  # 项目记忆：规则、历史、状态
├── 历史版本/                    # 归档旧版本（只读参考）
├── 可用打包版本/                # 已发布的 .exe
└── .kiro/steering/             # AI 引导规则
```

## 架构概览

整个应用是单文件单体架构：`autodl启动器/flet-v2.py`。

- 主类 `FletSSHPortForwarder`：拥有全部状态、UI 和业务逻辑。
- 入口：文件底部 `ft.app(target=main)`，`main()` 实例化主类。
- 初始化流程：`__init__` → 配置路径 → 偏好加载 → `setup_ui()`。
- 辅助类：`Signal`（轻量回调/事件）、`_ColorsPatch`（颜色工具）。
- 顶层工具函数：`is_frozen()`、`_win_dpapi_encrypt/decrypt()`、`_pip_install()`、`_install_asyncio_shutdown_silencer()`。

## 核心子系统（均在 FletSSHPortForwarder 内部）

| 子系统 | 职责 | 关键方法 |
|--------|------|----------|
| SSH 隧道 | paramiko 连接、端口转发、断线重连 | `connect()`, `_connect_thread()`, `disconnect()`, `_reconnect_in_place()` |
| Selenium 自动化 | AutoDL 登录、设备抓取、按钮点击 | `autodl_login()`, `init_autodl_driver()`, `autodl_refresh_devices()` |
| 设备操作 | 开机/关机/续费、GPU 检测 | `autodl_start()`, `autodl_stop()`, `_do_renew_all()`, `_do_shutdown_all_parallel()` |
| 配置管理 | 保存/加载/删除 SSH 配置、设备映射 | `save_config()`, `load_config_list()`, `_load_device_map()` |
| UI 布局 | Flet 控件、对话框、主题、窗口状态 | `setup_ui()`, `apply_theme()`, `show_message()`, `safe_update()` |
| 凭据管理 | DPAPI 加密、登录偏好持久化 | `_win_dpapi_encrypt/decrypt()`, `load_autodl_credentials()` |

## 线程模型

- 所有并发使用 `threading.Thread`，不使用 async/await。
- 后台线程用于：SSH 连接、Selenium 自动化、设备轮询、窗口状态保存、自动刷新定时器。
- 从后台线程更新 UI 必须通过 `self.page.update()` 或 `safe_update()`。
- 不要引入 asyncio 或其他异步框架，保持现有线程模型一致。

## 编码规则

1. 所有改动进入 `flet-v2.py`，除非明确要求创建新模块。
2. 配置优先：禁止硬编码路径或凭据，使用 `configs/` 下的 JSON 文件或类属性。
3. 错误透明：禁止裸 `except: pass`，必须通过 `update_status()` 或 `_log_to_file()` 记录完整 traceback。
4. 确定性清理：所有 SSH 会话、socket、Selenium driver 必须在 `finally` 块中释放。
5. 状态集中：所有状态存放在 `FletSSHPortForwarder` 实例中，禁止跨模块或全局重复状态。
6. 关键操作必须有日志输出（`print()` / `_log_to_file()`），确保无 UI 时也能调试。
7. 打包模式下禁止运行 `pip install`（已有 `is_frozen()` 守卫）。
8. 禁止直接删除旧配置文件，改为重命名/归档。
9. 新增方法应放在对应子系统的方法群附近，保持逻辑分组。
10. UI 控件创建集中在 `setup_ui()` 中，事件处理方法与控件分离。

## 命名约定

- 私有方法以 `_` 前缀命名（如 `_connect_thread`、`_do_renew_all`）。
- 设备操作方法以 `autodl_` 前缀命名（如 `autodl_start`、`autodl_stop`）。
- 行级 Selenium 操作以 `_xxx_by_row` 命名（如 `_start_by_row`、`_stop_by_row`）。
- 配置路径方法以 `_xxx_path` 命名，返回文件路径字符串。
- 状态更新方法以 `update_` 前缀命名（如 `update_status`、`update_device_table`）。

## 测试

- `autodl启动器/test_*.py`：针对特定功能的测试（renew、refresh、detect、actions、logic）。
- `tests/`：集成和分析脚本，非标准 pytest 结构。
- 无统一测试运行器或 CI，单独运行：`python -m pytest autodl启动器/test_renew_v2.py`。
- 编写测试时遵循现有 `test_*.py` 的模式和风格。

## 构建

```bash
cd autodl启动器
python build_exe.py   # PyInstaller --onefile --windowed，打包 assets + icon
```

## 修改注意事项

- 文件很大（~5500行），修改前先用 `readCode` 定位目标方法的签名和位置。
- 修改某个子系统时，注意检查是否有其他方法依赖被修改的逻辑。
- Selenium 操作依赖 AutoDL 网页结构，CSS 选择器可能因网站更新而失效。
- 端口转发逻辑涉及多线程 socket，修改时注意线程安全和资源释放。
