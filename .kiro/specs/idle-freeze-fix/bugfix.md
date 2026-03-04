# Bugfix Requirements Document

## Introduction

AutoDL 一键连接桌面应用在 SSH 端口转发建立后，用户离开 30 分钟至 1 小时后返回时，GUI 完全无响应（假死），所有按钮点击无反应，必须强制关闭进程。根因是多个并发缺陷叠加：重连逻辑同步阻塞、Signal 回调跨线程直接操作 UI、client_threads 无限增长、Selenium driver 竞争访问、临时 Chrome profile 泄漏。

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN SSH 连接断开后 `_reconnect_in_place()` 被调用 THEN 系统在转发线程中以指数退避同步阻塞重试最多 10 次（每次 sleep 最长 60 秒），期间整个转发循环停滞，无法处理新连接或响应断开请求

1.2 WHEN `_reconnect_in_place()` 重试次数 ≥ 3 THEN 系统在转发线程中同步调用 `_detect_device_shutdown_for_reconnect()` 操作 Selenium driver，可能与自动刷新或其他 Selenium 操作产生竞争，导致 driver 状态损坏或死锁

1.3 WHEN 后台线程（`_connect_thread` 等）通过 `update_status_signal.emit()` 更新 UI THEN `Signal.emit()` 直接在调用线程中执行回调，回调操作 Flet UI 控件时违反 Flet 线程安全约束，导致 UI 状态损坏或死锁

1.4 WHEN 端口转发接受新的客户端连接 THEN 系统创建新线程并 append 到 `self.client_threads` 列表，已完成的线程从不清理，列表无限增长导致内存持续泄漏

1.5 WHEN `autodl_busy` 标志被多个线程同时读写 THEN 由于 `autodl_busy` 是普通布尔值而非线程安全互斥量，自动刷新定时器和重连中的设备检测可能同时操作 Selenium driver，导致竞态条件

1.6 WHEN `init_autodl_driver()` 被调用创建新浏览器实例 THEN 系统通过 `tempfile.mkdtemp()` 创建临时 Chrome profile 目录，但在 driver 关闭后从不执行 `shutil.rmtree()` 清理，导致磁盘空间持续泄漏

### Expected Behavior (Correct)

2.1 WHEN SSH 连接断开后触发重连 THEN 系统 SHALL 在独立线程中异步执行重连逻辑，不阻塞转发循环主线程，且每次 sleep 期间可被 `stop_event` 中断以快速响应用户断开操作

2.2 WHEN 重连过程中需要检测设备状态 THEN 系统 SHALL 通过线程安全的互斥机制（如 `threading.Lock`）保护 Selenium driver 访问，避免与自动刷新或其他操作产生竞争

2.3 WHEN 后台线程需要更新 UI 状态 THEN `Signal.emit()` SHALL 将回调调度到 Flet 主线程执行（通过 `page.run_thread_safe` 或等效机制），确保 UI 操作的线程安全

2.4 WHEN 端口转发的客户端连接关闭或线程完成 THEN 系统 SHALL 定期清理 `self.client_threads` 列表中已完成的线程对象，防止内存无限增长

2.5 WHEN 多个线程需要访问 Selenium driver THEN 系统 SHALL 使用 `threading.Lock` 或等效互斥机制替代普通布尔值 `autodl_busy`，确保同一时刻只有一个线程操作 driver

2.6 WHEN Selenium driver 被关闭或重新初始化 THEN 系统 SHALL 通过 `shutil.rmtree()` 清理之前创建的临时 Chrome profile 目录，释放磁盘空间

### Unchanged Behavior (Regression Prevention)

3.1 WHEN SSH 连接正常且未断开 THEN 系统 SHALL CONTINUE TO 正常转发所有端口流量，客户端连接的建立和数据传输不受影响

3.2 WHEN 用户手动点击断开连接 THEN 系统 SHALL CONTINUE TO 正常关闭 SSH 连接、server socket 和所有客户端线程

3.3 WHEN 用户执行 AutoDL 设备操作（开机/关机/续费/刷新） THEN 系统 SHALL CONTINUE TO 通过 Selenium 正确执行操作并在 UI 中反馈结果

3.4 WHEN 用户切换深色/浅色主题 THEN 系统 SHALL CONTINUE TO 正确更新所有 UI 控件的颜色和样式

3.5 WHEN 应用启动并加载已保存的设备配置 THEN 系统 SHALL CONTINUE TO 正确读取和显示配置列表

3.6 WHEN 用户登录 AutoDL 并刷新设备列表 THEN 系统 SHALL CONTINUE TO 正确抓取设备状态、GPU 可用性和备注信息
