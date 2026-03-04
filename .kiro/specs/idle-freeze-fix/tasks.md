# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Fault Condition** - 空闲假死多缺陷复现
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the 6 bugs exist
  - **Scoped PBT Approach**: 针对每个缺陷编写具体的属性测试，scope 到确定性的触发条件
  - Test file: `autodl启动器/test_idle_freeze.py`
  - 使用 `hypothesis` 库编写属性测试
  - **属性 1a - Signal 线程安全**: 从后台线程调用 `Signal.emit()`，断言回调在主线程中执行（未修复代码中回调在调用线程直接执行，测试将 FAIL）
  - **属性 1b - 重连非阻塞**: mock paramiko 连接失败，在独立线程中调用 `_reconnect_in_place()`，断言调用在 2 秒内返回且 `stop_event.wait()` 可中断（未修复代码中 `time.sleep()` 不可中断，测试将 FAIL）
  - **属性 1c - client_threads 清理**: 模拟多次客户端连接后，断言 `client_threads` 中已完成线程被清理（未修复代码中只增不减，测试将 FAIL）
  - **属性 1d - Selenium 互斥**: 从两个线程同时尝试操作 Selenium driver，断言通过 Lock 互斥（未修复代码中 `autodl_busy` 是普通布尔值，测试将 FAIL）
  - **属性 1e - 临时 profile 清理**: 调用 `cleanup()` 后断言临时 Chrome profile 目录已被删除（未修复代码中不清理，测试将 FAIL）
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bugs exist)
  - Document counterexamples found to understand root cause
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - 正常功能行为保全
  - **IMPORTANT**: Follow observation-first methodology
  - Test file: `autodl启动器/test_idle_freeze.py`（追加到同一文件）
  - 使用 `hypothesis` 库编写属性测试
  - **观察阶段**: 在未修复代码上运行以下场景，记录实际输出
  - **属性 2a - Signal 主线程直接执行**: 从主线程调用 `Signal.emit()`，观察回调直接在主线程执行，断言修复后行为一致（无额外调度开销）
  - **属性 2b - 端口转发数据传输**: mock SSH transport 正常时，验证 `_handle_client()` 正确转发数据，断言修复后行为一致
  - **属性 2c - 断开连接资源释放**: 调用 `disconnect()` 后，验证 SSH 连接、server socket、client_threads 正确清理，断言修复后行为一致
  - **属性 2d - Selenium 设备操作**: 验证加锁后 Selenium 设备操作（刷新设备列表等）仍正确执行并返回结果
  - Verify tests pass on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 3. Fix for 空闲假死多缺陷修复

  - [x] 3.1 修复 Signal 类线程安全调度（缺陷3）
    - 为 `Signal` 类增加可选的 `page` 引用参数
    - 修改 `emit()` 方法：非主线程时通过 `page.run_thread_safe()` 调度回调到主线程
    - 主线程调用时保持直接执行（保全属性 2a）
    - 在 `FletSSHPortForwarder.__init__()` 中创建 Signal 时传入 `page` 引用
    - 在 `cleanup()` 中将 Signal 的 `page` 置为 None 避免悬挂引用
    - _Bug_Condition: state.signal_emit_called_from_background_thread AND NOT state.callback_dispatched_to_main_thread_
    - _Expected_Behavior: Signal.emit() 从后台线程调用时，回调被调度到 Flet 主线程执行_
    - _Preservation: 主线程调用 Signal.emit() 时回调直接执行，无额外开销_
    - _Requirements: 2.3_

  - [x] 3.2 修复 _reconnect_in_place 异步化（缺陷1）
    - 将 `_connect_thread()` 转发循环中对 `_reconnect_in_place()` 的同步调用改为启动独立 daemon 线程
    - 添加 `self.reconnecting` 标志位，防止重复启动重连线程
    - 将 `_reconnect_in_place()` 内部的 `time.sleep(wait)` 替换为 `self.stop_event.wait(wait)`
    - 转发循环在重连进行中时继续运行 `select.select()` 保持响应性
    - _Bug_Condition: state.ssh_disconnected AND state._reconnect_in_place_running_in_forward_thread AND state.forward_loop_blocked_
    - _Expected_Behavior: 重连在独立线程中异步执行，不阻塞转发循环，sleep 可被 stop_event 在 1 秒内中断_
    - _Preservation: SSH 连接正常时端口转发不受影响_
    - _Requirements: 2.1_

  - [x] 3.3 修复 Selenium driver 互斥锁（缺陷2 + 缺陷5）
    - 在 `__init__()` 中新增 `self.selenium_lock = threading.Lock()`
    - 将所有 `self.autodl_busy` 的读写替换为 `selenium_lock` 的 acquire/release
    - `_detect_device_shutdown_for_reconnect()` 使用 `selenium_lock.acquire(blocking=False)`，获取失败则跳过
    - `autodl_refresh_devices_quick()` 用 `selenium_lock` 替代 `autodl_busy` 检查
    - 所有长时间持有 driver 的操作在入口 acquire，finally 中 release
    - _Bug_Condition: state.multiple_threads_access_selenium_driver AND state.autodl_busy_is_plain_bool_
    - _Expected_Behavior: threading.Lock 确保同一时刻只有一个线程操作 driver_
    - _Preservation: Selenium 设备操作在加锁后仍正确执行_
    - _Requirements: 2.2, 2.5_

  - [x] 3.4 修复 client_threads 定期清理（缺陷4）
    - 在 `_connect_thread()` 转发循环的每次迭代中，清理 `client_threads` 中 `is_alive() == False` 的已完成线程
    - 使用列表推导式 `self.client_threads = [t for t in self.client_threads if t.is_alive()]`
    - _Bug_Condition: state.client_threads_count > 0 AND state.finished_threads_never_cleaned_
    - _Expected_Behavior: 每次 accept 循环迭代时清理已完成线程，列表长度不超过活跃线程数_
    - _Preservation: 正常端口转发和断开连接行为不受影响_
    - _Requirements: 2.4_

  - [x] 3.5 修复临时 Chrome profile 清理（缺陷6）
    - 在 `cleanup()` 中 `autodl_driver.quit()` 之后添加 `shutil.rmtree(self._tmp_chrome_profile, ignore_errors=True)`
    - 在 `init_autodl_driver()` 重新初始化 driver 前清理旧的 `_tmp_chrome_profile`
    - 清理后将 `self._tmp_chrome_profile` 置为 None
    - _Bug_Condition: state.init_autodl_driver_called AND state.temp_chrome_profile_created AND NOT state.temp_chrome_profile_cleaned_on_driver_close_
    - _Expected_Behavior: driver 关闭或重新初始化时通过 shutil.rmtree() 清理临时目录_
    - _Preservation: Selenium driver 初始化和关闭流程不受影响_
    - _Requirements: 2.6_

  - [x] 3.6 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - 空闲假死多缺陷已修复
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bugs are fixed)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 3.7 Verify preservation tests still pass
    - **Property 2: Preservation** - 正常功能行为保全
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)

- [x] 4. Checkpoint - Ensure all tests pass
  - 运行 `python -m pytest autodl启动器/test_idle_freeze.py -v` 确保所有测试通过
  - 运行现有测试确保无回归：`python -m pytest autodl启动器/test_autodl_actions.py autodl启动器/test_autodl_logic.py -v`
  - Ensure all tests pass, ask the user if questions arise.
