# 空闲假死修复 Bugfix Design

## Overview

AutoDL 一键连接桌面应用在 SSH 端口转发建立后，用户离开 30 分钟至 1 小时后返回时 GUI 完全无响应（假死）。根因是 6 个并发缺陷叠加：重连逻辑同步阻塞转发线程、Signal 回调跨线程直接操作 UI 违反 Flet 线程安全约束、client_threads 列表无限增长、Selenium driver 无互斥保护导致竞态、临时 Chrome profile 目录泄漏。

修复策略：在 `autodl启动器/flet-v2.py` 单文件内进行最小化修改，保持现有 `threading.Thread` 线程模型不变，不引入 asyncio，不重构整体架构。

## Glossary

- **Bug_Condition (C)**: 触发假死的条件集合 — SSH 断线触发重连阻塞、后台线程通过 Signal 直接操作 UI、client_threads 无限增长、autodl_busy 竞态、临时 profile 泄漏
- **Property (P)**: 修复后的期望行为 — 重连异步非阻塞、Signal 回调线程安全、资源定期清理、Selenium 互斥访问
- **Preservation**: 修复不得影响的现有行为 — 正常端口转发、手动断开连接、设备操作、主题切换、配置加载、设备列表刷新
- **Signal**: `flet-v2.py` 中的轻量回调类，用于后台线程向 UI 发送状态更新
- **FletSSHPortForwarder**: 主类，拥有全部状态、UI 和业务逻辑
- **_reconnect_in_place()**: SSH 断线后的重连方法，当前在转发线程中同步阻塞执行
- **_connect_thread()**: SSH 连接主循环，包含端口转发的 accept 循环和 client_threads 管理
- **_handle_client()**: 单个客户端连接的数据转发线程
- **_detect_device_shutdown_for_reconnect()**: 重连过程中通过 Selenium 检测设备是否已关机
- **autodl_busy**: 普通布尔标志，用于防止 Selenium driver 并发访问，但非线程安全
- **init_autodl_driver()**: 初始化 Selenium WebDriver，创建临时 Chrome profile 目录

## Bug Details

### Fault Condition

应用在 SSH 隧道建立后的空闲期间，多个并发缺陷叠加导致 GUI 假死。核心触发路径：SSH 连接因网络波动断开 → `_reconnect_in_place()` 在转发线程中同步阻塞（最长 ~10 分钟）→ 期间 `Signal.emit()` 从后台线程直接调用 UI 回调 → Flet 线程安全约束被违反 → UI 事件循环损坏 → GUI 无响应。

**Formal Specification:**
```
FUNCTION isBugCondition(state)
  INPUT: state of type AppState (SSH连接状态、线程状态、资源状态)
  OUTPUT: boolean
  
  // 缺陷1+2: 重连阻塞 + Selenium 竞争
  cond_reconnect := state.ssh_disconnected
                     AND state._reconnect_in_place_running_in_forward_thread
                     AND state.forward_loop_blocked
  
  // 缺陷3: Signal 跨线程 UI 操作
  cond_signal := state.signal_emit_called_from_background_thread
                 AND state.callback_modifies_flet_controls
                 AND NOT state.callback_dispatched_to_main_thread
  
  // 缺陷4: client_threads 无限增长
  cond_threads := state.client_threads_count > 0
                  AND state.finished_threads_never_cleaned
  
  // 缺陷5: autodl_busy 竞态
  cond_busy := state.multiple_threads_access_selenium_driver
               AND state.autodl_busy_is_plain_bool (非互斥量)
  
  // 缺陷6: 临时 profile 泄漏
  cond_profile := state.init_autodl_driver_called
                  AND state.temp_chrome_profile_created
                  AND NOT state.temp_chrome_profile_cleaned_on_driver_close
  
  RETURN cond_reconnect OR cond_signal OR cond_threads OR cond_busy OR cond_profile
END FUNCTION
```

### Examples

- **缺陷1 示例**: SSH 连接因网络波动断开，`_reconnect_in_place()` 在转发线程中以指数退避重试 10 次，`time.sleep()` 最长 60 秒，整个转发循环阻塞约 10 分钟，期间无法 accept 新连接也无法响应 `stop_event`
- **缺陷2 示例**: 重连第 3 次时调用 `_detect_device_shutdown_for_reconnect()` 操作 Selenium driver，同时 `_auto_refresh_tick()` 触发 `autodl_refresh_devices_quick()` 也在操作 driver，两个线程同时调用 `driver.get()` 导致 driver 状态损坏
- **缺陷3 示例**: `_connect_thread` 中调用 `self.update_status_signal.emit('重连成功')`，`Signal.emit()` 直接在转发线程中执行 `self.update_status()` 回调，该回调修改 `self.status_label.value` 并调用 `self.safe_update()`，违反 Flet 线程安全约束
- **缺陷4 示例**: 用户通过 JupyterLab 工作 8 小时，每次打开 notebook/终端/文件都创建新的 WebSocket 连接，`client_threads` 列表累积数百个已完成的 Thread 对象，内存持续增长
- **缺陷5 示例**: `_auto_refresh_tick()` 检查 `self.autodl_busy == False` 后进入刷新，同时 `_reconnect_in_place()` 中的 `_detect_device_shutdown_for_reconnect()` 也在操作 driver，两者都未设置 `autodl_busy`，产生竞态
- **缺陷6 示例**: 每次调用 `init_autodl_driver()` 通过 `tempfile.mkdtemp(prefix='autodl_chrome_')` 创建临时目录，driver 关闭后目录未删除，多次初始化后磁盘空间持续泄漏

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- SSH 连接正常时，端口转发的数据传输不受影响（3.1）
- 用户手动点击断开连接，正常关闭 SSH 连接、server socket 和所有客户端线程（3.2）
- AutoDL 设备操作（开机/关机/续费/刷新）通过 Selenium 正确执行并在 UI 反馈（3.3）
- 深色/浅色主题切换正确更新所有 UI 控件（3.4）
- 应用启动时正确加载和显示已保存的设备配置（3.5）
- 登录 AutoDL 后正确抓取设备状态、GPU 可用性和备注（3.6）

**Scope:**
所有不涉及以下场景的输入应完全不受影响：
- SSH 断线重连流程
- Signal.emit() 的调度机制
- client_threads 的生命周期管理
- Selenium driver 的并发访问控制
- 临时 Chrome profile 的创建和清理

## Hypothesized Root Cause

基于代码分析，6 个缺陷的根因如下：

1. **重连同步阻塞（缺陷1）**: `_reconnect_in_place()` 在 `_connect_thread()` 的转发循环中被同步调用（第 1672 行 `okr = self._reconnect_in_place()`），整个 while 循环在重连期间无法执行 `select.select()` 接受新连接。`time.sleep(wait)` 不可被 `stop_event` 中断，用户点击断开也无法快速响应。

2. **Selenium 竞态（缺陷2）**: `_detect_device_shutdown_for_reconnect()` 在转发线程中直接调用 Selenium driver 方法（`_goto_instance_list()`、`_find_row_by_device_id()` 等），没有任何锁保护。同时 `_auto_refresh_tick()` 可能在定时器线程中触发 `autodl_refresh_devices_quick()`，两者并发操作同一个 driver 实例。

3. **Signal 线程不安全（缺陷3）**: `Signal.emit()` 实现为 `if self.callback: self.callback(*args)`，直接在调用线程中执行回调。当从 `_connect_thread` 等后台线程调用时，回调（如 `update_status`）直接修改 Flet 控件属性并调用 `safe_update()`，违反 Flet 的线程安全模型。

4. **client_threads 泄漏（缺陷4）**: `_connect_thread()` 的转发循环中 `self.client_threads.append(client_thread)` 只增不减。`disconnect()` 中 `self.client_threads = []` 只在断开时清理，长时间连接期间列表无限增长。

5. **autodl_busy 非原子（缺陷5）**: `autodl_busy` 是普通布尔值，`_auto_refresh_tick()` 中的 `if ... self.autodl_busy:` 检查和后续操作之间存在 TOCTOU 竞态。`_detect_device_shutdown_for_reconnect()` 完全不检查也不设置 `autodl_busy`。

6. **临时 profile 泄漏（缺陷6）**: `init_autodl_driver()` 中 `tempfile.mkdtemp(prefix='autodl_chrome_')` 创建临时目录并赋值给 `self._tmp_chrome_profile`，但 `cleanup()` 中关闭 driver 后未调用 `shutil.rmtree()` 清理该目录。`_cleanup_old_sessions()` 只清理 `chrometmp-` 前缀的目录，不清理 `autodl_chrome_` 前缀的。

## Correctness Properties

Property 1: Fault Condition - 重连非阻塞

_For any_ SSH 断线事件触发重连时，修复后的 `_reconnect_in_place()` SHALL 在独立线程中异步执行，不阻塞转发循环的 `select.select()` 调用，且每次 sleep 期间可被 `stop_event` 在 1 秒内中断。

**Validates: Requirements 2.1**

Property 2: Fault Condition - Selenium 互斥访问

_For any_ 需要访问 Selenium driver 的操作（重连设备检测、自动刷新、手动刷新、设备操作），修复后的代码 SHALL 通过 `threading.Lock` 确保同一时刻只有一个线程操作 driver，消除竞态条件。

**Validates: Requirements 2.2, 2.5**

Property 3: Fault Condition - Signal 线程安全调度

_For any_ 后台线程调用 `Signal.emit()` 时，修复后的 `Signal` 类 SHALL 将回调调度到 Flet 主线程执行（通过检测当前线程是否为主线程，非主线程时使用 `page` 的线程安全调度机制），确保 UI 操作不违反 Flet 线程安全约束。

**Validates: Requirements 2.3**

Property 4: Fault Condition - client_threads 定期清理

_For any_ 端口转发运行期间，修复后的转发循环 SHALL 定期（每次 accept 循环迭代时）清理 `client_threads` 列表中 `is_alive() == False` 的已完成线程对象，防止内存无限增长。

**Validates: Requirements 2.4**

Property 5: Fault Condition - 临时 Chrome profile 清理

_For any_ Selenium driver 被关闭或重新初始化时，修复后的代码 SHALL 通过 `shutil.rmtree()` 清理 `self._tmp_chrome_profile` 指向的临时目录，释放磁盘空间。

**Validates: Requirements 2.6**

Property 6: Preservation - 正常功能不受影响

_For any_ 不涉及 SSH 断线重连、Signal 调度、client_threads 管理、Selenium 并发访问、临时 profile 清理的操作，修复后的代码 SHALL 产生与原始代码完全相同的行为，保持端口转发、手动断开、设备操作、主题切换、配置加载、设备列表刷新等功能不变。

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

## Fix Implementation

### Changes Required

所有改动进入 `autodl启动器/flet-v2.py`，不创建新模块。

**File**: `autodl启动器/flet-v2.py`


**修复1: Signal 类线程安全改造（缺陷3）**

**Class**: `Signal`（第 184 行）

**Specific Changes**:
1. 为 `Signal` 类增加可选的 `page` 引用参数
2. 修改 `emit()` 方法：检测当前线程是否为主线程，若非主线程且 `page` 可用，则通过 Flet 的线程安全机制调度回调；若为主线程或无 `page`，则直接执行回调
3. Flet 0.21+ 中，从后台线程安全更新 UI 的方式是直接修改控件属性后调用 `page.update()`（Flet 内部会处理线程调度），但 `Signal.emit()` 的问题在于回调可能触发复杂的 UI 操作链。修复方案：在 `emit()` 中使用 `threading.main_thread()` 判断，非主线程时将回调包装后通过 `page.run_thread_safe()` 或简单的线程安全队列调度

```python
class Signal:
    def __init__(self, callback=None, page=None):
        self.callback = callback
        self.page = page
    def connect(self, callback):
        self.callback = callback
    def emit(self, *args):
        if self.callback:
            if self.page and threading.current_thread() is not threading.main_thread():
                # 非主线程：通过 page 调度到主线程
                cb = self.callback
                def _run():
                    try:
                        cb(*args)
                    except Exception:
                        pass
                try:
                    self.page.run_thread_safe(_run)
                except Exception:
                    # fallback: 直接调用
                    self.callback(*args)
            else:
                self.callback(*args)
```

注意：需要在 `__init__` 中创建 Signal 时传入 `page` 引用，并在 `cleanup()` 中将 Signal 的 `page` 置为 None 以避免悬挂引用。如果 Flet 版本不支持 `run_thread_safe`，则 fallback 为直接调用（保持现有行为）。

**修复2: _reconnect_in_place 异步化（缺陷1）**

**Function**: `_reconnect_in_place()`（第 1756 行）及 `_connect_thread()` 中的调用点

**Specific Changes**:
1. 将 `_connect_thread()` 转发循环中对 `_reconnect_in_place()` 的同步调用改为启动独立线程
2. 在 `_reconnect_in_place()` 内部，将 `time.sleep(wait)` 替换为 `stop_event.wait(wait)`，使 sleep 可被 `stop_event` 中断
3. 重连成功后通过标志位通知转发循环恢复工作
4. 转发循环在重连进行中时继续运行 `select.select()` 以保持响应性，但跳过需要 transport 的操作

```python
# _connect_thread 中的调用点改为:
if (not tcur) or (not tcur.is_active()):
    if not self.reconnecting:
        threading.Thread(
            target=self._reconnect_in_place,
            daemon=True
        ).start()
    time.sleep(1.0)
    continue

# _reconnect_in_place 中的 sleep 改为:
# 替换: time.sleep(wait)
# 改为: self.stop_event.wait(wait)  # 可被 stop_event.set() 立即中断
```

**修复3: Selenium driver 互斥锁（缺陷2 + 缺陷5）**

**Function**: `__init__()`、`_detect_device_shutdown_for_reconnect()`、`_auto_refresh_tick()`、`autodl_refresh_devices_quick()` 等所有操作 Selenium driver 的方法

**Specific Changes**:
1. 在 `__init__()` 中新增 `self.selenium_lock = threading.Lock()` 替代 `self.autodl_busy` 布尔值
2. 保留 `self.autodl_busy` 作为向后兼容的只读属性（通过 `selenium_lock.locked()` 实现），或直接替换所有 `autodl_busy` 的读写为 `selenium_lock` 的 acquire/release
3. `_detect_device_shutdown_for_reconnect()` 中使用 `selenium_lock.acquire(blocking=False)` 尝试获取锁，获取失败则跳过检测
4. `autodl_refresh_devices_quick()` 中用 `selenium_lock` 替代 `autodl_busy` 检查
5. 所有长时间持有 driver 的操作（续费、关机、开机等）在入口处 acquire 锁，在 finally 中 release

```python
# __init__ 中:
self.selenium_lock = threading.Lock()

# _detect_device_shutdown_for_reconnect 中:
def _detect_device_shutdown_for_reconnect(self):
    if not self.selenium_lock.acquire(blocking=False):
        return False  # 其他操作正在使用 driver，跳过检测
    try:
        # ... 原有逻辑 ...
    finally:
        self.selenium_lock.release()

# autodl_refresh_devices_quick 中:
# 替换 if self.autodl_busy: 为 if self.selenium_lock.locked():
```

**修复4: client_threads 定期清理（缺陷4）**

**Function**: `_connect_thread()`（转发循环部分）

**Specific Changes**:
1. 在转发循环的每次迭代中（`select.select()` 返回后），清理 `client_threads` 中已完成的线程
2. 使用列表推导式过滤 `is_alive()` 为 True 的线程，替换原列表

```python
# 在转发循环中 select.select() 之后、accept 之前添加:
self.client_threads = [t for t in self.client_threads if t.is_alive()]
```

**修复5: 临时 Chrome profile 清理（缺陷6）**

**Function**: `cleanup()`（第 2583 行）、`init_autodl_driver()`（第 2298 行）

**Specific Changes**:
1. 在 `cleanup()` 中，`autodl_driver.quit()` 之后添加 `shutil.rmtree(self._tmp_chrome_profile)` 清理临时目录
2. 在 `init_autodl_driver()` 中，重新初始化 driver 前（步骤2"尝试重用"失败后），清理旧的 `_tmp_chrome_profile`
3. 在 `_cleanup_old_sessions()` 中，增加清理 `autodl_chrome_` 前缀的临时目录（系统临时目录中）
4. 清理操作使用 `shutil.rmtree(path, ignore_errors=True)` 防止因文件锁定导致异常

```python
# cleanup() 中 driver.quit() 之后:
if getattr(self, '_tmp_chrome_profile', None):
    try:
        import shutil
        shutil.rmtree(self._tmp_chrome_profile, ignore_errors=True)
        self._log_to_file(f"已清理临时 Chrome profile: {self._tmp_chrome_profile}")
    except Exception:
        pass
    self._tmp_chrome_profile = None

# init_autodl_driver() 中重新创建 driver 前:
old_profile = getattr(self, '_tmp_chrome_profile', None)
if old_profile and os.path.isdir(old_profile):
    try:
        import shutil
        shutil.rmtree(old_profile, ignore_errors=True)
    except Exception:
        pass
```

## Testing Strategy

### Validation Approach

测试策略分两阶段：首先在未修复代码上复现缺陷（探索性测试），然后验证修复的正确性和回归防护。由于本项目是 GUI 应用且依赖 Selenium/paramiko 等外部资源，测试以 mock 为主的单元测试和属性测试为核心。

### Exploratory Fault Condition Checking

**Goal**: 在未修复代码上复现缺陷，确认根因分析正确。如果复现失败，需要重新分析。

**Test Plan**: 编写测试模拟各缺陷的触发条件，在未修复代码上运行观察失败模式。

**Test Cases**:
1. **Signal 线程安全测试**: 从后台线程调用 `Signal.emit()`，验证回调是否在调用线程中直接执行（将在未修复代码上确认回调在非主线程执行）
2. **重连阻塞测试**: mock paramiko 连接失败，调用 `_reconnect_in_place()`，验证调用线程是否被阻塞（将在未修复代码上确认阻塞）
3. **client_threads 增长测试**: 模拟多次客户端连接后检查 `client_threads` 长度（将在未修复代码上确认只增不减）
4. **autodl_busy 竞态测试**: 从两个线程同时检查和设置 `autodl_busy`，验证是否存在 TOCTOU 窗口（将在未修复代码上确认竞态）
5. **临时 profile 泄漏测试**: mock `init_autodl_driver()` 后检查临时目录是否在 cleanup 后仍存在（将在未修复代码上确认泄漏）

**Expected Counterexamples**:
- Signal 回调在后台线程中直接执行，而非主线程
- `_reconnect_in_place()` 阻塞调用线程数十秒
- `client_threads` 列表在连接关闭后仍保留已完成的 Thread 对象
- 两个线程同时通过 `autodl_busy` 检查进入 Selenium 操作
- `cleanup()` 后临时 Chrome profile 目录仍存在于磁盘

### Fix Checking

**Goal**: 验证修复后，所有缺陷条件下的行为符合预期。

**Pseudocode:**
```
FOR ALL state WHERE isBugCondition(state) DO
  result := fixedFunction(state)
  ASSERT expectedBehavior(result)
END FOR
```

具体验证：
- Signal.emit() 从后台线程调用时，回调被调度到主线程执行
- _reconnect_in_place() 在独立线程中运行，不阻塞转发循环
- stop_event.set() 后 _reconnect_in_place() 在 1 秒内退出
- client_threads 列表长度在清理后不超过活跃线程数
- selenium_lock 确保同一时刻只有一个线程操作 driver
- cleanup() 后临时 Chrome profile 目录被删除

### Preservation Checking

**Goal**: 验证修复不影响正常功能。

**Pseudocode:**
```
FOR ALL state WHERE NOT isBugCondition(state) DO
  ASSERT originalFunction(state) = fixedFunction(state)
END FOR
```

**Testing Approach**: 属性测试适合保全检查，因为它能自动生成大量测试用例覆盖非缺陷输入空间，捕获手动测试可能遗漏的边界情况。

**Test Plan**: 先在未修复代码上观察正常功能的行为，然后编写属性测试确保修复后行为一致。

**Test Cases**:
1. **端口转发保全**: 验证正常 SSH 连接下，数据转发行为不变
2. **断开连接保全**: 验证手动断开连接后，所有资源正确释放
3. **设备操作保全**: 验证 Selenium 设备操作（开机/关机/续费/刷新）在加锁后仍正确执行
4. **Signal 主线程保全**: 验证从主线程调用 Signal.emit() 时，回调仍直接执行（无额外调度开销）

### Unit Tests

- 测试 `Signal.emit()` 从主线程调用时直接执行回调
- 测试 `Signal.emit()` 从后台线程调用时通过 page 调度
- 测试 `_reconnect_in_place()` 可被 `stop_event` 中断
- 测试 `client_threads` 清理逻辑正确过滤已完成线程
- 测试 `selenium_lock` 的 acquire/release 在正常和异常路径下都正确
- 测试临时 Chrome profile 在 cleanup 后被删除
- 测试 `init_autodl_driver()` 重新初始化时清理旧 profile

### Property-Based Tests

- 生成随机的 Signal.emit() 调用序列（主线程/后台线程混合），验证所有回调最终都被执行且参数正确
- 生成随机的 client_threads 状态（alive/dead 混合），验证清理后列表只包含 alive 线程
- 生成随机的 selenium_lock acquire/release 序列，验证不会死锁且互斥性成立
- 生成随机的 stop_event 时机，验证 _reconnect_in_place() 总能在 timeout 内退出

### Integration Tests

- 测试完整的 SSH 断线 → 异步重连 → 重连成功 → 恢复转发流程
- 测试重连进行中用户点击断开 → 重连被中断 → 资源正确释放
- 测试自动刷新和手动设备操作的并发场景下 selenium_lock 的正确性
- 测试应用退出时所有资源（SSH、socket、driver、临时目录）的完整清理
