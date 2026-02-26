# AutoDL 一键连接

Windows 桌面工具，将「登录 AutoDL → 开机 → 复制 SSH → 建隧道 → 打开端口」压缩为一键操作。

面向使用 AutoDL 云 GPU 的深度学习 / AI 开发者。

## 功能

- 一键开机并自动建立 SSH 端口转发
- Selenium 自动登录 AutoDL 控制台，Cookie 持久化免重复登录
- 设备列表实时展示状态、GPU 余量、备注、释放时间
- 一键续费（逐台开关机防止实例被回收）
- 一键关机所有运行中设备
- 快捷打开 JupyterLab / AutoPanel
- 深色 / 浅色主题切换
- 窗口位置与大小记忆
- 凭据 DPAPI 加密存储

## 截图

> TODO: 添加应用截图

## 快速开始

### 直接使用（推荐）

从 [Releases](../../releases) 下载最新的 `AutoDL一键连接.exe`，双击运行即可。

### 从源码运行

```bash
# 安装依赖
pip install -r autodl启动器/requirements.txt

# 运行
python autodl启动器/flet-v2.py
```

### 从源码打包

```bash
# 生成图标（可选）
python assets/make_icon.py

# 打包
cd autodl启动器
python build_exe.py
# 产物在 autodl启动器/dist/AutoDL一键连接.exe
```

## 使用流程

1. 启动应用，在左侧面板输入 AutoDL 账号密码并登录
2. 点击「刷新并检测GPU」查看设备列表
3. 对目标设备点击「开机并连接」，自动完成开机 → SSH 隧道 → 打开浏览器
4. 也可单独使用右侧面板，粘贴 SSH 命令手动建立端口转发

## 依赖

- Python 3.11+
- Windows 10/11
- Chrome 浏览器（Selenium 自动化需要）

核心 Python 包：

| 包 | 用途 |
|---|---|
| flet | GUI 框架 |
| paramiko | SSH 连接与端口转发 |
| selenium | 浏览器自动化 |
| webdriver_manager | ChromeDriver 管理 |
| pyperclip | 剪贴板操作 |

## 项目结构

```
autodl启动器/
├── flet-v2.py          # 主程序（单文件架构）
├── build_exe.py        # 打包脚本
├── requirements.txt    # 依赖
└── configs/            # 运行时配置（自动生成）
assets/
└── icon.ico            # 应用图标
```

## 许可证

本项目供个人学习与使用，未经授权不得用于商业用途。
