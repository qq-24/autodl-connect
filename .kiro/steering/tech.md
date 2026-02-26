---
inclusion: always
---

# 技术栈与开发指南

## 语言与运行时

- Python 3.11+，仅限 Windows 平台
- 标准库线程模型（`threading.Thread`），禁止引入 asyncio
- 使用 Windows DPAPI（`ctypes.windll.crypt32`）加密凭据，不可移植到其他 OS

## 核心依赖

| 包名 | 最低版本 | 用途 |
|------|---------|------|
| flet | 0.21.0 | GUI 框架（基于 Flutter 的 Python UI） |
| paramiko | 2.7.0 | SSH2 连接与端口转发 |
| selenium | 4.0.0 | 浏览器自动化（AutoDL 控制台操作） |
| webdriver_manager | 3.8.0 | ChromeDriver 自动下载与版本管理 |
| pyperclip | 1.8.0 | 剪贴板读写（解析 SSH 命令） |

修改依赖时同步更新 `autodl启动器/requirements.txt`。禁止引入 PyQt5 或其他 GUI 框架。

## 构建与打包

```bash
# 安装依赖
pip install -r autodl启动器/requirements.txt

# 生成图标（打包前可选）
python assets/make_icon.py

# 构建单文件 exe
cd autodl启动器
python build_exe.py
```

- `build_exe.py` 调用 PyInstaller，参数为 `--onefile --windowed`，自动打包 assets 和 icon
- 输出目录：`autodl启动器/dist/`
- 打包后的 exe 中禁止调用 `pip install`（通过 `is_frozen()` 守卫）

## 测试

- 测试文件位于 `autodl启动器/test_*.py`，使用 pytest 单独运行
- `tests/` 目录为集成/分析脚本，非标准 pytest 结构
- 无统一测试运行器或 CI，逐个运行：
  ```bash
  python -m pytest autodl启动器/test_renew_v2.py
  ```
- 新增测试时遵循现有 `test_*.py` 的命名和组织风格

## 配置文件约定

| 文件 | 位置 | 说明 |
|------|------|------|
| SSH/设备配置 | `configs/*.json`（相对于 exe） | 运行时自动创建 |
| ChromeDriver | `configs/chromedriver.exe` | webdriver_manager 缓存 |
| 浏览器配置 | `configs/chrome_profile/` | Selenium Chrome 用户数据 |
| 凭据 | `autodl_configs/credentials.json` | 可能经 DPAPI 加密，已 gitignore |
| Cookies | `autodl_configs/cookies.json` | Selenium 登录态持久化，已 gitignore |

- 所有配置为 JSON 格式
- 配置路径优先使用程序目录，回退到用户主目录
- 禁止硬编码路径，通过类属性或 `_xxx_path` 方法获取

## Selenium 注意事项

- AutoDL 网页结构可能随时变化，CSS 选择器需要定期验证
- ChromeDriver 版本必须与用户本地 Chrome 版本匹配，由 webdriver_manager 自动处理
- 支持 headless 和可见浏览器两种模式
- 浏览器实例必须在 `finally` 块中通过 `driver.quit()` 释放

## 安全约束

- 凭据文件（`credentials.json`）必须经 DPAPI 加密存储，禁止明文
- `autodl_configs/` 目录已加入 `.gitignore`，禁止提交敏感数据
- 不要在日志或 UI 中输出密码、token 等敏感信息
