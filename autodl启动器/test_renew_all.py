"""
续费测试脚本：遍历所有设备，逐个开机再关机，防止机器被销毁。
逻辑：
  1. 登录 AutoDL
  2. 获取所有设备行
  3. 对每台已关机的设备：
     - 先尝试有卡开机，GPU不足则无卡开机
     - 无卡开机同时只能一台，所以串行：开机 → 等运行 → 关机 → 等关机
  4. 已运行的设备直接关机
  5. 最终确保全部关机
"""
import time
import json
import os
import re
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (
    NoSuchElementException, TimeoutException,
    ElementClickInterceptedException, StaleElementReferenceException
)
from webdriver_manager.chrome import ChromeDriverManager
import ctypes
import base64

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger(__name__)

# ── 凭据 ──
def _win_dpapi_decrypt(ciphertext):
    try:
        if not isinstance(ciphertext, str) or not ciphertext.startswith("enc:"):
            return None
        raw = base64.b64decode(ciphertext[4:])
        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", ctypes.c_uint), ("pbData", ctypes.c_void_p)]
        fn = ctypes.windll.crypt32.CryptUnprotectData
        fn.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.POINTER(ctypes.c_wchar_p),
                       ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p,
                       ctypes.c_uint, ctypes.POINTER(DATA_BLOB)]
        fn.restype = ctypes.c_bool
        in_blob = DATA_BLOB(len(raw), ctypes.cast(ctypes.create_string_buffer(raw), ctypes.c_void_p))
        out_blob = DATA_BLOB()
        if not fn(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
            return None
        buf = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)
        return buf.decode('utf-8')
    except Exception:
        return None

def get_credentials():
    cfg = os.path.join('configs', 'autodl_credentials.json')
    if not os.path.exists(cfg):
        return None, None
    with open(cfg, 'r', encoding='utf-8') as f:
        data = json.load(f)
    user = data.get('username')
    pwd = data.get('password')
    try:
        dec = _win_dpapi_decrypt(pwd)
        if dec: pwd = dec
    except: pass
    return user, pwd

# ── 浏览器 ──
def setup_driver():
    opts = Options()
    opts.page_load_strategy = 'eager'
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1600,900")
    # opts.add_argument("--headless=new")  # 调试时注释掉
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    return driver

def safe_click(driver, el):
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    time.sleep(0.2)
    try:
        ActionChains(driver).move_to_element(el).pause(0.2).perform()
    except: pass
    try:
        WebDriverWait(driver, 2).until(EC.element_to_be_clickable(el))
        el.click()
    except:
        driver.execute_script("arguments[0].click();", el)

# ── 登录 ──
def login(driver, user, pwd):
    log.info("正在登录...")
    driver.get("https://www.autodl.com/login")
    time.sleep(2)
    if "login" not in driver.current_url:
        log.info("已登录，跳过")
        return True
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//input[@type='password']")))
    u_input = driver.find_elements(By.XPATH, "//input[@type='text'] | //input[@type='tel']")
    if u_input:
        u_input[-1].clear()
        u_input[-1].send_keys(user)
    p_input = driver.find_element(By.XPATH, "//input[@type='password']")
    p_input.clear()
    p_input.send_keys(pwd)
    for xp in ["//button[contains(normalize-space(),'登录')]", "//*[contains(@class,'el-button--primary')]"]:
        try:
            btn = driver.find_element(By.XPATH, xp)
            safe_click(driver, btn)
            break
        except: continue
    WebDriverWait(driver, 15).until(lambda d: 'login' not in d.current_url)
    log.info("登录成功")
    return True

# ── 导航到设备列表 ──
def goto_list(driver):
    target = 'https://www.autodl.com/console/instance/list'
    if '/console/instance/list' not in (driver.current_url or ''):
        driver.get(target)
    try:
        WebDriverWait(driver, 10).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, ".el-table__body tr")) > 0
        )
    except:
        driver.refresh()
        time.sleep(3)
        WebDriverWait(driver, 10).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, ".el-table__body tr")) > 0
        )
    time.sleep(0.5)

# ── 解析所有设备行 ──
def parse_all_devices(driver):
    """返回 [{row, device_id, name, status, has_gpu}]"""
    rows = driver.find_elements(By.CSS_SELECTOR, ".el-table__body tr")
    devices = []
    for row in rows:
        try:
            if not row.is_displayed():
                continue
            text = row.text
            if not text.strip():
                continue
            cells = row.find_elements(By.TAG_NAME, 'td')
            if not cells:
                continue

            # 第一列：设备名 + ID + 备注
            col1 = (cells[0].text or '').strip()
            lines = [ln.strip() for ln in col1.split('\n') if ln.strip()]
            name = lines[0] if lines else '未知'
            dev_id = ''
            for ln in lines[1:]:
                if re.fullmatch(r'[a-fA-F0-9\-]{6,}', ln):
                    dev_id = ln
                    break

            # 第二列：状态
            status_text = (cells[1].text or '').strip() if len(cells) > 1 else ''
            status_lines = [ln.strip() for ln in status_text.split('\n') if ln.strip()]
            status = status_lines[0] if status_lines else '未知'

            # GPU 是否充足（从状态列检测）
            full_status = status_text.lower()
            has_gpu = 'gpu充足' in status_text or ('gpu' in full_status and '不足' not in full_status and '无' not in full_status)

            devices.append({
                'row': row,
                'device_id': dev_id,
                'name': name,
                'status': status,
                'has_gpu': has_gpu,
                'full_text': text,
            })
        except StaleElementReferenceException:
            continue
        except Exception as e:
            log.warning(f"解析行失败: {e}")
            continue
    return devices

def find_row_by_id(driver, device_id):
    rows = driver.find_elements(By.CSS_SELECTOR, ".el-table__body tr")
    for row in rows:
        try:
            if device_id in row.text:
                return row
        except: continue
    raise NoSuchElementException(f"找不到设备 {device_id}")

def is_running(row):
    try:
        cells = row.find_elements(By.TAG_NAME, 'td')
        st = cells[1].text if len(cells) >= 2 else row.text
        return ('运行中' in st) or ('running' in st.lower())
    except: return False

def is_stopped(row):
    try:
        cells = row.find_elements(By.TAG_NAME, 'td')
        st = cells[1].text if len(cells) >= 2 else row.text
        return ('已关机' in st) or ('stopped' in st.lower())
    except: return False

# ── 开机（有卡） ──
def start_by_row(driver, row):
    """点击开机按钮 + 确认对话框，返回 True/False"""
    cells = row.find_elements(By.TAG_NAME, 'td')
    action_td = cells[-1] if cells else row
    btn = None
    for xp in [
        ".//button[.//span[contains(normalize-space(), '开机')]]",
        ".//a[contains(normalize-space(), '开机')]",
        ".//*[contains(@class,'el-button') and .//span[contains(normalize-space(),'开机')]]",
    ]:
        try:
            btn = action_td.find_element(By.XPATH, xp)
            break
        except: continue

    if btn is None:
        # 尝试从"更多"菜单找
        trigger = _find_more_trigger(driver, action_td, row)
        if trigger:
            _click_dropdown_item(driver, trigger, '开机')
            # 开机可能通过菜单点击完成，btn 设为 None 表示已通过菜单处理
            btn = None  # 已通过菜单点击
        else:
            raise NoSuchElementException('未找到开机按钮')

    if btn is not None:
        safe_click(driver, btn)

    # 处理确认对话框
    _handle_confirm_dialog(driver)
    return True

# ── 无卡开机 ──
def start_nogpu_by_row(driver, row):
    """点击更多 → 无卡模式开机 → 确认。完整复刻主程序逻辑。"""
    cells = row.find_elements(By.TAG_NAME, 'td')
    action_td = cells[-1] if cells else row
    trigger = _find_more_trigger(driver, action_td, row)
    if not trigger:
        raise NoSuchElementException('未找到更多菜单触发器')

    # ── 第一步：点击"更多"触发器，打开下拉菜单 ──
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", trigger)
    time.sleep(0.3)
    try:
        WebDriverWait(driver, 5).until(EC.element_to_be_clickable(trigger))
    except: pass
    # 先 hover
    try:
        ActionChains(driver).move_to_element(trigger).pause(0.1).perform()
    except: pass
    # 再 JS click（和主程序一致）
    try:
        driver.execute_script(
            """const t=arguments[0];
            const root=t.closest('button, .el-dropdown, [role="button"]')||t;
            try{ root.click(); } catch(e){ root.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true})); }""",
            trigger)
    except:
        driver.execute_script('arguments[0].click();', trigger)

    # ── 第二步：用 JS proximity 算法找到最近的可见下拉菜单 ──
    time.sleep(0.8)  # 等菜单动画
    menu_el = driver.execute_script(
        """const t=arguments[0]; const tr=t.getBoundingClientRect();
        const menus=[...document.querySelectorAll('.el-dropdown-menu')].filter(m=>m.offsetParent!==null);
        if(menus.length===0) return null;
        let best=null;
        for(const m of menus){const r=m.getBoundingClientRect();const d=Math.hypot((r.left-tr.left),(r.top-tr.bottom));
         if(!best||d<best.d){best={el:m,d:d};}}
        return best?best.el:null;""",
        trigger)

    if not menu_el:
        # 菜单没出来，再试一次点击
        log.warning("  第一次点击更多后菜单未出现，重试...")
        time.sleep(0.5)
        try:
            ActionChains(driver).move_to_element(trigger).click().perform()
        except:
            driver.execute_script('arguments[0].click();', trigger)
        time.sleep(1)
        menu_el = driver.execute_script(
            """const menus=[...document.querySelectorAll('.el-dropdown-menu')].filter(m=>m.offsetParent!==null);
            return menus.length>0 ? menus[menus.length-1] : null;""")

    if not menu_el:
        raise NoSuchElementException('点击更多后未找到下拉菜单')

    # ── 第三步：在菜单中找"无卡模式开机"项 ──
    # 先打印菜单内容帮助调试
    menu_text = driver.execute_script("return arguments[0].innerText;", menu_el)
    log.info(f"  下拉菜单内容: {repr(menu_text)}")

    item = None
    # 方法1：在找到的菜单元素内部搜索
    for xp in [
        ".//li[contains(normalize-space(),'无卡模式开机')]",
        ".//li[.//span[contains(normalize-space(),'无卡模式开机')]]",
        ".//*[contains(normalize-space(),'无卡模式开机')]",
    ]:
        try:
            cand = menu_el.find_element(By.XPATH, xp)
            if cand and cand.is_displayed():
                item = cand
                break
        except: continue

    # 方法2：全局搜索所有可见菜单
    if item is None:
        for xp in [
            "//*[contains(@class,'el-dropdown-menu') or contains(@class,'el-popper')]//li[contains(normalize-space(),'无卡模式开机')]",
        ]:
            try:
                cand = WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.XPATH, xp)))
                if cand and cand.is_displayed():
                    item = cand
                    break
            except: continue

    # 方法3：遍历所有 li 做文本匹配
    if item is None:
        try:
            lis = driver.find_elements(By.XPATH, "//*[contains(@class,'el-dropdown-menu') or contains(@class,'el-popper')]//li")
            for cand in lis:
                try:
                    txt = (cand.text or '').strip()
                    if '无卡' in txt and cand.is_displayed():
                        item = cand
                        log.info(f"  通过文本遍历找到: '{txt}'")
                        break
                except: continue
        except: pass

    # ── 第四步：点击菜单项 ──
    clicked = False
    if item:
        # 等待 disabled 消失
        for _ in range(6):
            cls = (item.get_attribute('class') or '')
            aria = (item.get_attribute('aria-disabled') or '')
            if ('is-disabled' in cls) or (str(aria).lower() == 'true'):
                time.sleep(0.5)
                continue
            break
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", item)
        try:
            ActionChains(driver).move_to_element(item).pause(0.05).click(item).perform()
            clicked = True
        except:
            try:
                driver.execute_script('arguments[0].click();', item)
                clicked = True
            except: pass

    # JS 兜底
    if not clicked:
        clicked = bool(driver.execute_script(
            """const sels=['.el-dropdown-menu','.el-popper'];
            const menus=sels.flatMap(s=>[...document.querySelectorAll(s)]).filter(m=>m.offsetParent!==null);
            for(const menu of menus){const items=[...menu.querySelectorAll('*')];
              const target=items.find(n=>/(无卡模式开机)/.test((n.textContent||'').trim()));
              if(target){target.click(); return true;}}
            return false;"""))

    if not clicked:
        raise NoSuchElementException('菜单中未找到无卡开机项')

    # ── 第五步：处理确认对话框 ──
    time.sleep(0.5)
    try:
        _handle_confirm_dialog(driver, timeout=6)
    except:
        pass
    return True

# ── 关机 ──
def stop_by_row(driver, row):
    """点击关机按钮 + 确认"""
    cells = row.find_elements(By.TAG_NAME, 'td')
    action_td = cells[-1] if cells else row
    btn = None
    for xp in [
        ".//button[.//span[contains(normalize-space(), '关机')]]",
        ".//a[contains(normalize-space(), '关机')]",
        ".//*[contains(@class,'el-button') and .//span[contains(normalize-space(),'关机')]]",
    ]:
        try:
            btn = action_td.find_element(By.XPATH, xp)
            break
        except: continue

    if btn is None:
        trigger = _find_more_trigger(driver, action_td, row)
        if trigger:
            _click_dropdown_item(driver, trigger, '关机')
        else:
            raise NoSuchElementException('未找到关机按钮')
    else:
        safe_click(driver, btn)

    _handle_confirm_dialog(driver)
    return True

# ── 辅助：找"更多"触发器 ──
def _find_more_trigger(driver, action_td, row):
    triggers_xp = [
        ".//*[contains(@class,'el-dropdown')]",
        ".//*[contains(@class,'el-icon-more')]",
        ".//*[contains(normalize-space(),'更多')]",
    ]
    for xp in triggers_xp:
        try:
            return action_td.find_element(By.XPATH, xp)
        except: continue
    for xp in triggers_xp:
        try:
            return row.find_element(By.XPATH, xp)
        except: continue
    return None

# ── 辅助：通过下拉菜单点击指定项 ──
def _click_dropdown_item(driver, trigger, item_text):
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", trigger)
    try:
        ActionChains(driver).move_to_element(trigger).click().perform()
    except:
        driver.execute_script('arguments[0].click();', trigger)
    time.sleep(0.5)
    # 找到最近的可见菜单
    menu_el = driver.execute_script(
        """const t=arguments[0];const tr=t.getBoundingClientRect();
        const menus=[...document.querySelectorAll('.el-dropdown-menu')].filter(m=>m.offsetParent!==null);
        if(menus.length===0) return null;
        let best=null;
        for(const m of menus){const r=m.getBoundingClientRect();const d=Math.hypot((r.left-tr.left),(r.top-tr.bottom));
         if(!best||d<best.d){best={el:m,d:d};}}
        return best?best.el:null;""",
        trigger)
    if menu_el:
        driver.execute_script(
            f"""const menu=arguments[0];
            const items=[...menu.querySelectorAll('*')];
            const target=items.find(n=>/{item_text}/.test((n.textContent||'').trim()));
            if(target){{target.dispatchEvent(new MouseEvent('click',{{bubbles:true,cancelable:true}}));}}""",
            menu_el)
    time.sleep(0.3)

# ── 辅助：处理确认对话框 ──
def _handle_confirm_dialog(driver, timeout=5):
    cands = [
        "//div[contains(@class,'el-message-box')]//button[.//span[contains(normalize-space(),'确定')]]",
        "//div[contains(@class,'el-dialog')]//button[.//span[contains(normalize-space(),'确定')]]",
        "//div[contains(@class,'el-popconfirm')]//button[.//span[contains(normalize-space(),'确定')]]",
        "//button[contains(@class,'el-button--primary') and .//span[contains(normalize-space(),'确定')]]",
        "//button[.//span[contains(normalize-space(),'确认')]]",
    ]
    btn = None
    # 先尝试找到对话框容器
    try:
        dialog = WebDriverWait(driver, timeout).until(
            lambda d: next((el for el in d.find_elements(By.XPATH,
                "//div[contains(@class,'el-message-box') or contains(@class,'el-dialog')]")
                if el.is_displayed()), None)
        )
        if dialog:
            # 勾选对话框里的 checkbox（如果有）
            driver.execute_script(
                """const box=arguments[0];
                const cbs=[...box.querySelectorAll('input[type=checkbox], .el-checkbox')];
                for(const c of cbs){ try{ if(c.tagName==='INPUT'){ if(!c.checked) c.click(); }
                else { const inp=c.querySelector('input'); if(inp && !inp.checked) inp.click(); } }catch(e){} }""",
                dialog)
            for xp in [".//button[.//span[contains(normalize-space(),'确定')]]",
                       ".//button[contains(@class,'primary')]"]:
                try:
                    btn = dialog.find_element(By.XPATH, xp)
                    if btn: break
                except: continue
    except: pass

    if not btn:
        for xp in cands:
            try:
                btn = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, xp)))
                if btn and btn.is_displayed():
                    break
                btn = None
            except:
                continue

    if btn:
        safe_click(driver, btn)
        time.sleep(0.5)
    # 没找到确认按钮也不一定是错误（有些操作不需要确认）

# ── 等待设备变为运行中 ──
def wait_running(driver, device_id, timeout=180, interval=5):
    log.info(f"  等待 {device_id} 变为运行中 (最长{timeout}s)...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            goto_list(driver)
            row = find_row_by_id(driver, device_id)
            if is_running(row):
                log.info(f"  ✓ {device_id} 已运行")
                return row
            cells = row.find_elements(By.TAG_NAME, 'td')
            st = cells[1].text if len(cells) >= 2 else '?'
            log.info(f"  当前状态: {st}")
        except Exception as e:
            log.warning(f"  轮询异常: {e}")
        time.sleep(interval)
    log.warning(f"  ✗ {device_id} 等待运行超时")
    return None

# ── 等待设备变为已关机 ──
def wait_stopped(driver, device_id, timeout=120, interval=5):
    log.info(f"  等待 {device_id} 变为已关机 (最长{timeout}s)...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            goto_list(driver)
            row = find_row_by_id(driver, device_id)
            if is_stopped(row):
                log.info(f"  ✓ {device_id} 已关机")
                return row
            cells = row.find_elements(By.TAG_NAME, 'td')
            st = cells[1].text if len(cells) >= 2 else '?'
            log.info(f"  当前状态: {st}")
        except Exception as e:
            log.warning(f"  轮询异常: {e}")
        time.sleep(interval)
    log.warning(f"  ✗ {device_id} 等待关机超时")
    return None

# ══════════════════════════════════════
#  主流程
# ══════════════════════════════════════
def renew_all(driver, auto_confirm=False):
    goto_list(driver)
    devices = parse_all_devices(driver)
    log.info(f"共发现 {len(devices)} 台设备")
    for d in devices:
        log.info(f"  [{d['device_id']}] {d['name']} | 状态={d['status']} | GPU={'充足' if d['has_gpu'] else '不足/无'}")

    if not devices:
        log.error("没有设备，退出")
        return

    results = {}  # device_id -> 'ok' / 'fail' / 'skip'

    # 分类
    gpu_devices = []    # GPU充足，可以批量开
    nogpu_devices = []  # GPU不足，需要串行无卡开
    running_devices = []  # 已经在运行的
    other_devices = []  # 开机中/关机中等过渡状态

    for dev in devices:
        did = dev['device_id']
        goto_list(driver)
        try:
            row = find_row_by_id(driver, did)
        except:
            results[did] = 'skip'
            continue
        if is_running(row):
            running_devices.append(dev)
        elif is_stopped(row):
            cells = row.find_elements(By.TAG_NAME, 'td')
            status_text = cells[1].text if len(cells) >= 2 else ''
            if 'GPU充足' in status_text:
                gpu_devices.append(dev)
            else:
                nogpu_devices.append(dev)
        else:
            other_devices.append(dev)

    # ── 确认提示 ──
    log.info(f"\n{'='*50}")
    log.info("续费计划:")
    log.info(f"  有卡批量开机: {len(gpu_devices)} 台")
    for d in gpu_devices:
        log.info(f"    - {d['name']} ({d['device_id']})")
    log.info(f"  无卡串行开机: {len(nogpu_devices)} 台")
    for d in nogpu_devices:
        log.info(f"    - {d['name']} ({d['device_id']})")
    if running_devices:
        log.info(f"  已运行(将直接关机): {len(running_devices)} 台")
        for d in running_devices:
            log.info(f"    - {d['name']} ({d['device_id']})")
    if other_devices:
        log.info(f"  过渡状态(等待后处理): {len(other_devices)} 台")
        for d in other_devices:
            log.info(f"    - {d['name']} ({d['device_id']}) [{d['status']}]")
    log.info(f"{'='*50}")

    if not auto_confirm:
        ans = input("\n确认开始续费? (y/n): ").strip().lower()
        if ans not in ('y', 'yes', ''):
            log.info("用户取消")
            return

    # ══════════════════════════════════════
    #  阶段0：处理已运行 + 过渡状态的设备
    # ══════════════════════════════════════
    # 过渡状态的设备先等它稳定下来
    if other_devices:
        log.info(f"\n{'='*50}")
        log.info(f"阶段0a: 等待 {len(other_devices)} 台过渡状态设备稳定")
        log.info(f"{'='*50}")
        for dev in other_devices:
            did = dev['device_id']
            log.info(f"  等待 {dev['name']}({did}) 状态稳定...")
            # 等最多60秒看它变成运行或关机
            stable = False
            for _ in range(12):
                try:
                    goto_list(driver)
                    row = find_row_by_id(driver, did)
                    if is_running(row):
                        log.info(f"    → 已运行，加入关机队列")
                        running_devices.append(dev)
                        stable = True
                        break
                    elif is_stopped(row):
                        log.info(f"    → 已关机，加入无卡开机队列")
                        nogpu_devices.append(dev)
                        stable = True
                        break
                except: pass
                time.sleep(5)
            if not stable:
                log.warning(f"    → 状态仍不稳定，跳过")
                results[did] = 'skip'

    if running_devices:
        log.info(f"\n{'='*50}")
        log.info(f"阶段0b: 关闭 {len(running_devices)} 台已运行设备")
        log.info(f"{'='*50}")
        for dev in running_devices:
            did = dev['device_id']
            try:
                goto_list(driver)
                row = find_row_by_id(driver, did)
                if is_running(row):
                    log.info(f"  关机: {dev['name']}({did})")
                    stop_by_row(driver, row)
            except Exception as e:
                log.error(f"  关机指令发送失败 {did}: {e}")
        # 等全部关机
        for dev in running_devices:
            did = dev['device_id']
            r = wait_stopped(driver, did, timeout=120)
            results[did] = 'ok' if r else 'fail'

    # ══════════════════════════════════════
    #  阶段1：批量有卡开机 → 等全部运行 → 批量关机
    # ══════════════════════════════════════
    if gpu_devices:
        log.info(f"\n{'='*50}")
        log.info(f"阶段1: 批量有卡开机 {len(gpu_devices)} 台")
        log.info(f"{'='*50}")

        # 1a. 逐个发送开机指令（不等运行）
        gpu_started = []
        for dev in gpu_devices:
            did = dev['device_id']
            for attempt in range(2):  # 最多重试1次
                try:
                    goto_list(driver)
                    time.sleep(0.5)
                    row = find_row_by_id(driver, did)
                    if is_running(row):
                        log.info(f"  {dev['name']}({did}) 已经在运行了，跳过开机")
                        gpu_started.append(dev)  # 加入等待队列，后面统一关
                        break
                    if not is_stopped(row):
                        log.info(f"  {dev['name']}({did}) 不再是关机状态，跳过")
                        results[did] = 'skip'
                        break
                    log.info(f"  发送开机: {dev['name']}({did})")
                    start_by_row(driver, row)
                    gpu_started.append(dev)
                    time.sleep(0.5)  # 短暂间隔避免请求过快
                    break
                except Exception as e:
                    if attempt == 0:
                        log.warning(f"  有卡开机第1次失败({e})，重试...")
                        time.sleep(1)
                    else:
                        log.error(f"  有卡开机重试仍失败，降级到无卡队列")
                        nogpu_devices.append(dev)

        # 1b. 等待全部运行
        if gpu_started:
            log.info(f"  等待 {len(gpu_started)} 台设备全部运行...")
            for dev in gpu_started:
                did = dev['device_id']
                r = wait_running(driver, did, timeout=180)
                if not r:
                    log.error(f"  {did} 开机超时")
                    results[did] = 'fail'

        # 1c. 批量发送关机指令
        gpu_to_stop = []
        for dev in gpu_started:
            did = dev['device_id']
            if results.get(did) == 'fail':
                continue
            for attempt in range(2):
                try:
                    goto_list(driver)
                    row = find_row_by_id(driver, did)
                    if is_stopped(row):
                        log.info(f"  {dev['name']}({did}) 已经关机了")
                        results[did] = 'ok'
                        break
                    if is_running(row):
                        log.info(f"  发送关机: {dev['name']}({did})")
                        stop_by_row(driver, row)
                        gpu_to_stop.append(dev)
                        time.sleep(0.5)
                        break
                    # 其他状态等一下再试
                    time.sleep(3)
                except Exception as e:
                    if attempt == 0:
                        log.warning(f"  关机第1次失败({e})，重试...")
                        time.sleep(2)
                    else:
                        log.error(f"  关机指令发送失败 {did}: {e}")
                        results[did] = 'fail'

        # 1d. 等待全部关机
        for dev in gpu_to_stop:
            did = dev['device_id']
            r = wait_stopped(driver, did, timeout=120)
            results[did] = 'ok' if r else 'fail'

    # ══════════════════════════════════════
    #  阶段2：串行无卡开机（一个一个来）
    # ══════════════════════════════════════
    if nogpu_devices:
        log.info(f"\n{'='*50}")
        log.info(f"阶段2: 串行无卡开机 {len(nogpu_devices)} 台")
        log.info(f"{'='*50}")

        for i, dev in enumerate(nogpu_devices):
            did = dev['device_id']
            log.info(f"\n  [{i+1}/{len(nogpu_devices)}] {dev['name']}({did})")
            try:
                goto_list(driver)
                time.sleep(0.5)
                row = find_row_by_id(driver, did)

                # 如果已经在运行（比如之前开机了没关），直接关
                if is_running(row):
                    log.info(f"    已在运行，直接关机...")
                    stop_by_row(driver, row)
                    r = wait_stopped(driver, did, timeout=120)
                    results[did] = 'ok' if r else 'fail'
                    continue

                if not is_stopped(row):
                    # 等一下看能不能稳定
                    log.info(f"    状态不是关机，等待稳定...")
                    time.sleep(10)
                    goto_list(driver)
                    row = find_row_by_id(driver, did)
                    if not is_stopped(row):
                        log.info(f"    仍不是关机状态，跳过")
                        results[did] = 'skip'
                        continue

                log.info(f"    无卡开机...")
                start_nogpu_by_row(driver, row)

                row = wait_running(driver, did, timeout=180)
                if not row:
                    log.error(f"    开机超时")
                    results[did] = 'fail'
                    continue

                log.info(f"    开机成功，关机...")
                time.sleep(1)
                goto_list(driver)
                row = find_row_by_id(driver, did)
                stop_by_row(driver, row)
                r = wait_stopped(driver, did, timeout=120)
                results[did] = 'ok' if r else 'fail'

            except Exception as e:
                log.error(f"    处理异常: {e}")
                results[did] = 'fail'

    # ── 最终确认：全部关机 ──
    log.info(f"\n{'='*50}")
    log.info("最终检查：确保所有设备已关机")
    log.info(f"{'='*50}")
    goto_list(driver)
    time.sleep(1)
    final_devices = parse_all_devices(driver)
    for dev in final_devices:
        if is_running(dev['row']):
            log.warning(f"  {dev['name']}({dev['device_id']}) 仍在运行，尝试关机...")
            try:
                stop_by_row(driver, dev['row'])
                wait_stopped(driver, dev['device_id'], timeout=60)
            except Exception as e:
                log.error(f"  最终关机失败: {e}")

    # ── 汇总 ──
    log.info(f"\n{'='*50}")
    log.info("续费结果汇总:")
    for did, result in results.items():
        tag = {'ok': '✓', 'fail': '✗', 'skip': '⊘'}.get(result, '?')
        log.info(f"  {tag} {did}: {result}")
    ok_count = sum(1 for v in results.values() if v == 'ok')
    log.info(f"成功: {ok_count}/{len(results)}")

if __name__ == '__main__':
    import sys
    auto = '--yes' in sys.argv or '-y' in sys.argv

    user, pwd = get_credentials()
    if not user or not pwd:
        log.error("未找到凭据，请检查 configs/autodl_credentials.json")
        exit(1)

    driver = setup_driver()
    try:
        login(driver, user, pwd)
        renew_all(driver, auto_confirm=auto)
    except Exception as e:
        log.error(f"致命错误: {e}", exc_info=True)
    finally:
        log.info("5秒后关闭浏览器...")
        time.sleep(5)
        driver.quit()
