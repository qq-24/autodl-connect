"""
续费测试脚本 v2：并行有卡 + 串行无卡
流程：
  1. 登录 → 解析设备 → 分类
  2. 阶段0: 先把所有已运行的关掉（刚关的不用再开关了，直接算ok）
  3. 阶段1: 有卡设备 — 每台开一个标签页，JS跑完整 开机→等运行→关机→等关机
  4. 阶段2: 无卡设备 — 单标签页串行 开机→等运行→关机→等关机
  5. 最终检查
"""
import time
import json
import os
import re
import sys
import logging
import base64
import ctypes
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

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger(__name__)

# ═══════════════════════════════════════════
#  基础工具（复用自 test_renew_all.py）
# ═══════════════════════════════════════════

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
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cfg = os.path.join(script_dir, 'configs', 'autodl_credentials.json')
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

def setup_driver():
    opts = Options()
    opts.page_load_strategy = 'eager'
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1600,900")
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

def click_refresh_btn(driver):
    """点击页面上的刷新按钮，等待数据真正刷新完成"""
    try:
        driver.execute_script("""
            var btn = document.querySelector('button.refresh-btn') ||
                      document.querySelector('i.el-icon-refresh-right');
            if (btn) {
                if (btn.tagName === 'I') btn = btn.closest('button') || btn;
                btn.click();
            }
        """)
        # 等 loading 出现再消失
        try:
            WebDriverWait(driver, 0.5).until(
                lambda d: d.find_elements(By.CSS_SELECTOR, '.el-loading-mask, .el-loading-spinner'))
        except: pass
        try:
            WebDriverWait(driver, 3).until(
                lambda d: (
                    not any(el.is_displayed() for el in d.find_elements(By.CSS_SELECTOR, '.el-loading-mask, .el-loading-spinner'))
                ) and len(d.find_elements(By.CSS_SELECTOR, '.el-table__body tr')) > 0
            )
        except:
            time.sleep(0.8)
    except:
        pass

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

def parse_all_devices(driver):
    rows = driver.find_elements(By.CSS_SELECTOR, ".el-table__body tr")
    devices = []
    for row in rows:
        try:
            if not row.is_displayed(): continue
            cells = row.find_elements(By.TAG_NAME, 'td')
            if not cells: continue
            col1 = (cells[0].text or '').strip()
            lines = [ln.strip() for ln in col1.split('\n') if ln.strip()]
            name = lines[0] if lines else '未知'
            dev_id = ''
            for ln in lines[1:]:
                if re.fullmatch(r'[a-fA-F0-9\-]{6,}', ln):
                    dev_id = ln; break
            status_text = (cells[1].text or '').strip() if len(cells) > 1 else ''
            has_gpu = 'GPU充足' in status_text
            devices.append({
                'row': row, 'device_id': dev_id, 'name': name,
                'status': status_text.split('\n')[0],
                'has_gpu': has_gpu, 'full_status': status_text,
            })
        except StaleElementReferenceException: continue
        except Exception as e:
            log.warning(f"解析行失败: {e}"); continue
    return devices

# ═══════════════════════════════════════════
#  串行操作工具（无卡用）— 复用原脚本的 Selenium 方式
# ═══════════════════════════════════════════

def _find_more_trigger(driver, action_td, row):
    for xp in [".//*[contains(@class,'el-dropdown')]",
               ".//*[contains(@class,'el-icon-more')]",
               ".//*[contains(normalize-space(),'更多')]"]:
        try: return action_td.find_element(By.XPATH, xp)
        except: continue
    for xp in [".//*[contains(@class,'el-dropdown')]",
               ".//*[contains(@class,'el-icon-more')]",
               ".//*[contains(normalize-space(),'更多')]"]:
        try: return row.find_element(By.XPATH, xp)
        except: continue
    return None

def _click_dropdown_item(driver, trigger, item_text):
    """点击下拉菜单触发器，然后用JS proximity找到最近菜单并点击指定项"""
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", trigger)
    try:
        ActionChains(driver).move_to_element(trigger).pause(0.02).perform()
    except: pass
    try:
        driver.execute_script(
            "const t=arguments[0];"
            "const root=t.closest('button,.el-dropdown,[role=\"button\"]')||t;"
            "try{root.click();}catch(e){root.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));}", trigger)
    except:
        driver.execute_script('arguments[0].click();', trigger)
    time.sleep(0.3)
    # JS proximity 找最近菜单
    clicked = driver.execute_script(
        "const t=arguments[0]; const label=arguments[1];"
        "const tr=t.getBoundingClientRect();"
        "const menus=[...document.querySelectorAll('.el-dropdown-menu')].filter(m=>m.offsetParent!==null);"
        "if(!menus.length) return false;"
        "let best=null;"
        "for(const m of menus){const r=m.getBoundingClientRect();const d=Math.hypot(r.left-tr.left,r.top-tr.bottom);"
        " if(!best||d<best.d) best={el:m,d:d};}"
        "if(!best) return false;"
        "const items=[...best.el.querySelectorAll('li')];"
        "const target=items.find(n=>n.textContent.trim().indexOf(label)>=0);"
        "if(target){target.click(); return true;}"
        "return false;", trigger, item_text)
    return clicked

def _handle_confirm_dialog(driver, timeout=8):
    """等待并点击确认对话框"""
    try:
        dialog = WebDriverWait(driver, timeout).until(
            lambda d: next((el for el in d.find_elements(By.XPATH,
                "//div[contains(@class,'el-message-box') or contains(@class,'el-dialog')]")
                if el.is_displayed()), None))
        if not dialog: return False
        # 勾选checkbox/radio/switch
        for js in [
            "const b=arguments[0];b.querySelectorAll('input[type=checkbox]').forEach(c=>{if(!c.checked)c.click()});",
            "const b=arguments[0];const r=[...b.querySelectorAll('.el-radio')];for(const x of r){const i=x.querySelector('input');if(i&&!i.checked){x.click();break;}}",
            "const b=arguments[0];b.querySelectorAll('.el-switch').forEach(s=>{if(!s.className.includes('is-checked'))s.click()});",
        ]:
            try: driver.execute_script(js, dialog)
            except: pass
        # 点确定
        for xp in [".//button[.//span[contains(normalize-space(),'确定')]]",
                    ".//button[contains(@class,'primary')]",
                    ".//button[.//span[contains(normalize-space(),'确认')]]"]:
            try:
                btn = dialog.find_element(By.XPATH, xp)
                safe_click(driver, btn)
                return True
            except: continue
    except: pass
    return False

def stop_by_row(driver, row):
    """点击关机按钮"""
    cells = row.find_elements(By.TAG_NAME, 'td')
    action_td = cells[-1] if cells else row
    btn = None
    for xp in [".//button[.//span[contains(normalize-space(),'关机')]]",
               ".//*[contains(@class,'el-button') and .//span[contains(normalize-space(),'关机')]]"]:
        try: btn = action_td.find_element(By.XPATH, xp); break
        except: continue
    if not btn:
        raise NoSuchElementException('未找到关机按钮')
    safe_click(driver, btn)
    _handle_confirm_dialog(driver)

def start_nogpu_by_row(driver, row):
    """无卡模式开机"""
    cells = row.find_elements(By.TAG_NAME, 'td')
    action_td = cells[-1] if cells else row
    trigger = _find_more_trigger(driver, action_td, row)
    if not trigger:
        raise NoSuchElementException('未找到更多菜单触发器')
    clicked = _click_dropdown_item(driver, trigger, '无卡模式开机')
    if not clicked:
        # fallback: 全局JS搜索
        clicked = driver.execute_script(
            "const menus=[...document.querySelectorAll('.el-dropdown-menu,.el-popper')].filter(m=>m.offsetParent!==null);"
            "for(const m of menus){const items=[...m.querySelectorAll('*')];"
            "  const t=items.find(n=>/无卡模式开机/.test(n.textContent.trim()));"
            "  if(t){t.click();return true;}} return false;")
    if not clicked:
        raise NoSuchElementException('菜单中未找到无卡开机项')
    _handle_confirm_dialog(driver, timeout=8)

def wait_running(driver, device_id, timeout=180, interval=3):
    t0 = time.time()
    goto_list(driver)  # 确保在正确页面
    while time.time() - t0 < timeout:
        try:
            click_refresh_btn(driver)
            row = find_row_by_id(driver, device_id)
            cells = row.find_elements(By.TAG_NAME, 'td')
            st = cells[1].text if len(cells) >= 2 else ''
            log.debug(f"  [{device_id}] 当前状态: {st.split(chr(10))[0]}")
            if is_running(row): return row
        except: pass
        time.sleep(interval)
    return None

def wait_stopped(driver, device_id, timeout=120, interval=3):
    t0 = time.time()
    goto_list(driver)  # 确保在正确页面
    while time.time() - t0 < timeout:
        try:
            click_refresh_btn(driver)
            row = find_row_by_id(driver, device_id)
            cells = row.find_elements(By.TAG_NAME, 'td')
            st = cells[1].text if len(cells) >= 2 else ''
            log.debug(f"  [{device_id}] 当前状态: {st.split(chr(10))[0]}")
            if is_stopped(row): return row
        except: pass
        time.sleep(interval)
    return None

# ═══════════════════════════════════════════
#  JS 生命周期脚本（注入到每个标签页，完整跑 开机→等运行→关机→等关机）
# ═══════════════════════════════════════════

LIFECYCLE_JS = """
(function(deviceId) {
    window.__lcResult = {phase:'init', status:'pending', error:'', log:[]};
    var POLL_MS = 3000, MAX_BOOT = 180000, MAX_STOP = 120000;

    function addLog(msg) {
        window.__lcResult.log.push(new Date().toLocaleTimeString() + ' ' + msg);
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
    function isRunning(s) { return s.indexOf('运行中') >= 0 || s.toLowerCase().indexOf('running') >= 0; }
    function isStopped(s) { return s.indexOf('已关机') >= 0 || s.toLowerCase().indexOf('stopped') >= 0; }
    function findBtn(row, label) {
        var tds = row.querySelectorAll('td');
        var act = tds[tds.length - 1];
        var bs = act.querySelectorAll('button');
        for (var i = 0; i < bs.length; i++) {
            if (bs[i].textContent.trim().indexOf(label) >= 0) return bs[i];
        }
        return null;
    }
    /* 点击"更多"下拉菜单中的指定项（如"开机"藏在更多里时） */
    function clickDropdownItem(row, itemText, cb) {
        var tds = row.querySelectorAll('td');
        var act = tds[tds.length - 1];
        /* 找"更多"触发器 */
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
        addLog('点击更多触发器');
        var root = trigger.closest('button,.el-dropdown,[role="button"]') || trigger;
        root.click();
        /* 等菜单出现并点击目标项 */
        var n = 0;
        var iv = setInterval(function() {
            n++;
            var menus = Array.from(document.querySelectorAll('.el-dropdown-menu,.el-popper')).filter(function(m){return m.offsetParent!==null;});
            for (var mi = 0; mi < menus.length; mi++) {
                var lis = menus[mi].querySelectorAll('li, *');
                for (var li = 0; li < lis.length; li++) {
                    if (lis[li].textContent.trim().indexOf(itemText) >= 0) {
                        addLog('菜单中找到: ' + itemText);
                        lis[li].click();
                        clearInterval(iv);
                        setTimeout(function(){ cb(true); }, 300);
                        return;
                    }
                }
            }
            if (n > 20) { clearInterval(iv); addLog('菜单项超时: ' + itemText); cb(false); }
        }, 200);
    }
    function clickConfirm(cb) {
        var n = 0;
        var iv = setInterval(function() {
            n++;
            var ds = document.querySelectorAll('.el-message-box, .el-dialog');
            for (var i = 0; i < ds.length; i++) {
                if (ds[i].offsetParent !== null) {
                    // 勾选所有checkbox
                    ds[i].querySelectorAll('input[type=checkbox]').forEach(function(c) { if(!c.checked) c.click(); });
                    var bs = ds[i].querySelectorAll('button');
                    for (var j = 0; j < bs.length; j++) {
                        var t = bs[j].textContent.trim();
                        if (t==='确定' || t==='确认' || /el-button--primary/.test(bs[j].className)) {
                            addLog('点击确认: ' + t);
                            bs[j].click();
                            clearInterval(iv);
                            setTimeout(function() { cb(true); }, 500);
                            return;
                        }
                    }
                }
            }
            if (n > 40) { clearInterval(iv); addLog('确认框超时'); cb(false); }
        }, 200);
    }
    function reloadAndWait(cb) {
        addLog('点击刷新按钮...');
        var refreshBtn = document.querySelector('button.refresh-btn') ||
                         document.querySelector('i.el-icon-refresh-right');
        if (refreshBtn) {
            if (refreshBtn.tagName === 'I') refreshBtn = refreshBtn.closest('button') || refreshBtn;
            refreshBtn.click();
        } else {
            addLog('未找到刷新按钮，用location.reload');
            location.reload();
        }
        // 等表格内容刷新（短暂延迟让请求发出，再等表格行出现）
        setTimeout(function() {
            var n = 0;
            var iv = setInterval(function() {
                n++;
                if (document.querySelectorAll('.el-table__body tr').length > 0) {
                    clearInterval(iv); setTimeout(cb, 300);
                } else if (n > 60) { clearInterval(iv); addLog('刷新等待超时'); cb(); }
            }, 200);
        }, 800);
    }
    function pollStatus(checkFn, timeout, phaseName, cb) {
        var t0 = Date.now();
        (function tick() {
            reloadAndWait(function() {
                var row = findRow();
                if (!row) { addLog('轮询时找不到行'); cb(false); return; }
                var s = getStatus(row);
                var brief = s.split('\\n')[0];
                window.__lcResult.lastStatus = brief;
                addLog(phaseName + ': ' + brief);
                if (checkFn(s)) { addLog(phaseName + ' 完成'); cb(true); return; }
                if (Date.now() - t0 > timeout) { addLog(phaseName + ' 超时'); cb(false); return; }
                setTimeout(tick, POLL_MS);
            });
        })();
    }

    function begin() {
        var row = findRow();
        if (!row) { finish('error', 'row_not_found'); return; }
        var s = getStatus(row);
        var brief = s.split('\\n')[0];
        addLog('初始状态: ' + brief);
        if (isStopped(s)) { doBoot(row); }
        else if (isRunning(s)) { doStop(); }
        else { finish('skip', 'state=' + brief); }
    }
    function doBoot(row) {
        window.__lcResult.phase = 'booting';
        var btn = findBtn(row, '开机');
        function afterBootClick() {
            clickConfirm(function(ok) {
                addLog('开机确认' + (ok ? '成功' : '失败/无需确认'));
                window.__lcResult.phase = 'wait_running';
                pollStatus(isRunning, MAX_BOOT, '等待运行', function(ok2) {
                    if (!ok2) { finish('boot_timeout', ''); return; }
                    doStop();
                });
            });
        }
        if (btn) {
            addLog('点击开机按钮(直接)');
            btn.scrollIntoView({block:'center'}); btn.click();
            afterBootClick();
        } else {
            addLog('直接开机按钮未找到，尝试更多菜单');
            clickDropdownItem(row, '开机', function(ok) {
                if (!ok) { finish('error', 'no_boot_btn_anywhere'); return; }
                afterBootClick();
            });
        }
    }
    function doStop() {
        window.__lcResult.phase = 'stopping';
        reloadAndWait(function() {
            var row = findRow();
            if (!row) { finish('error', 'row_gone_stop'); return; }
            var s = getStatus(row);
            if (isStopped(s)) { finish('ok', 'already_stopped'); return; }
            function afterStopClick() {
                clickConfirm(function(ok) {
                    addLog('关机确认' + (ok ? '成功' : '失败/无需确认'));
                    window.__lcResult.phase = 'wait_stopped';
                    pollStatus(isStopped, MAX_STOP, '等待关机', function(ok2) {
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
                    if (!ok) { finish('error', 'no_stop_btn_anywhere'); return; }
                    afterStopClick();
                });
            }
        });
    }
    function finish(status, error) {
        addLog('完成: ' + status + (error ? ' (' + error + ')' : ''));
        window.__lcResult = {phase:'done', status:status, error:error,
            log: window.__lcResult.log, lastStatus: window.__lcResult.lastStatus || ''};
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

# ═══════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════

def renew_all(driver, auto_confirm=False):
    goto_list(driver)
    devices = parse_all_devices(driver)
    log.info(f"共发现 {len(devices)} 台设备")
    for d in devices:
        log.info(f"  [{d['device_id']}] {d['name']} | 状态={d['status']} | GPU={'充足' if d['has_gpu'] else '不足/无'}")

    if not devices:
        log.error("没有设备"); return

    # 分类
    gpu_list, nogpu_list, running_list, other_list = [], [], [], []
    for dev in devices:
        did = dev['device_id']
        goto_list(driver)
        try:
            row = find_row_by_id(driver, did)
        except:
            log.warning(f"  找不到 {did}，跳过"); continue
        if is_running(row):
            running_list.append(dev)
        elif is_stopped(row):
            if dev['has_gpu']:
                gpu_list.append(dev)
            else:
                nogpu_list.append(dev)
        else:
            other_list.append(dev)

    log.info(f"\n{'='*60}")
    log.info(f"分类: 有卡={len(gpu_list)} 无卡={len(nogpu_list)} 运行={len(running_list)} 过渡={len(other_list)}")
    log.info(f"{'='*60}")

    if not auto_confirm:
        ans = input("\n确认开始续费? (y/n): ").strip().lower()
        if ans not in ('y', 'yes', ''): log.info("取消"); return

    results = {}  # device_id -> 'ok'/'fail'/'skip'

    # ══════════════════════════════════════
    #  阶段0a: 过渡状态等待
    # ══════════════════════════════════════
    if other_list:
        log.info(f"\n{'='*60}")
        log.info(f"阶段0a: 等待 {len(other_list)} 台过渡状态设备稳定")
        for dev in other_list:
            did = dev['device_id']
            stable = False
            for _ in range(12):
                try:
                    goto_list(driver)
                    click_refresh_btn(driver)
                    row = find_row_by_id(driver, did)
                    if is_running(row):
                        log.info(f"  {dev['name']} → 已运行"); running_list.append(dev); stable = True; break
                    elif is_stopped(row):
                        log.info(f"  {dev['name']} → 已关机"); nogpu_list.append(dev); stable = True; break
                except: pass
                time.sleep(5)
            if not stable:
                log.warning(f"  {dev['name']} 仍不稳定，跳过"); results[did] = 'skip'

    # ══════════════════════════════════════
    #  阶段0b: 关闭所有已运行设备（刚关的算ok，不用再开关）
    # ══════════════════════════════════════
    if running_list:
        log.info(f"\n{'='*60}")
        log.info(f"阶段0b: 关闭 {len(running_list)} 台已运行设备")
        for dev in running_list:
            did = dev['device_id']
            try:
                goto_list(driver)
                click_refresh_btn(driver)
                row = find_row_by_id(driver, did)
                if is_running(row):
                    log.info(f"  关机: {dev['name']}")
                    stop_by_row(driver, row)
                else:
                    log.info(f"  {dev['name']} 已不在运行")
            except Exception as e:
                log.error(f"  关机指令失败 {did}: {e}")
        for dev in running_list:
            did = dev['device_id']
            r = wait_stopped(driver, did, timeout=120)
            if r:
                log.info(f"  ✓ {dev['name']} 已关机 (算续费完成)")
                results[did] = 'ok'  # 刚关的不用再开关了
            else:
                log.error(f"  ✗ {dev['name']} 关机超时")
                results[did] = 'fail'

    # ══════════════════════════════════════
    #  阶段1: 有卡设备 — 多标签页并行（JS生命周期）
    # ══════════════════════════════════════
    if gpu_list:
        log.info(f"\n{'='*60}")
        log.info(f"阶段1: 并行处理 {len(gpu_list)} 台有卡设备")
        log.info(f"{'='*60}")

        main_handle = driver.current_window_handle
        target_url = 'https://www.autodl.com/console/instance/list'
        tab_info = []  # [(device_id, handle, dev)]

        # 快速开标签页 + 注入JS
        for dev in gpu_list:
            did = dev['device_id']
            log.info(f"  开标签页: {dev['name']} ({did})")
            try:
                driver.execute_script("window.open(arguments[0],'_blank');", target_url)
                all_h = driver.window_handles
                new_h = [h for h in all_h if h != main_handle and h not in [t[1] for t in tab_info]][-1]
                driver.switch_to.window(new_h)
                driver.execute_script(LIFECYCLE_JS, did)
                tab_info.append((did, new_h, dev))
                log.debug(f"    标签页已开: handle={new_h}")
            except Exception as e:
                log.error(f"  开标签页失败 {did}: {e}")
                nogpu_list.append(dev)

        # 切回主标签页
        try: driver.switch_to.window(main_handle)
        except: pass

        # 轮询各标签页进度
        pending = {did: (h, dev) for did, h, dev in tab_info}
        poll_count = 0
        while pending:
            poll_count += 1
            done_this = []
            for did, (h, dev) in list(pending.items()):
                try:
                    driver.switch_to.window(h)
                    r = driver.execute_script("return window.__lcResult || {};")
                except Exception as e:
                    log.debug(f"  [{did}] 读取失败: {e}")
                    continue

                phase = r.get('phase', '?')
                status = r.get('status', '?')
                last_st = r.get('lastStatus', '')
                js_log = r.get('log', [])

                if phase == 'done':
                    done_this.append(did)
                    # 打印JS端的完整日志
                    log.info(f"  ── {dev['name']} ({did}) 完成: {status} ──")
                    for line in js_log:
                        log.info(f"    JS: {line}")
                    if status == 'ok':
                        results[did] = 'ok'
                        log.info(f"  ✓ {dev['name']} 续费成功")
                    elif status == 'boot_timeout':
                        log.warning(f"  {dev['name']} 有卡开机超时，降级到无卡")
                        nogpu_list.append(dev)
                    elif status == 'skip':
                        results[did] = 'skip'
                        log.info(f"  ⊘ {dev['name']} 跳过: {r.get('error','')}")
                    else:
                        results[did] = 'fail'
                        log.error(f"  ✗ {dev['name']} 失败: {status} {r.get('error','')}")
                else:
                    if poll_count % 5 == 0:  # 每15秒打印一次进度
                        phase_cn = {'init':'初始化','booting':'开机中','wait_running':'等运行',
                                    'stopping':'关机中','wait_stopped':'等关机'}.get(phase, phase)
                        log.info(f"  [{dev['name']}] {phase_cn} {last_st}")

            for did in done_this:
                pending.pop(did, None)

            if pending:
                remaining_names = [pending[d][1]['name'] for d in pending]
                log.debug(f"  轮询#{poll_count} 剩余{len(pending)}台: {', '.join(remaining_names)}")
                time.sleep(3)

        # 关闭所有多余标签页
        log.info("  关闭并行标签页...")
        try:
            for h in list(driver.window_handles):
                if h != main_handle:
                    try: driver.switch_to.window(h); driver.close()
                    except: pass
            driver.switch_to.window(main_handle)
        except:
            try: driver.switch_to.window(main_handle)
            except: pass

    # ══════════════════════════════════════
    #  阶段2: 无卡设备 — 串行（一个一个来）
    # ══════════════════════════════════════
    # 去重：已经处理过的不再重复
    nogpu_list = [d for d in nogpu_list if d['device_id'] not in results]
    if nogpu_list:
        log.info(f"\n{'='*60}")
        log.info(f"阶段2: 串行无卡开机 {len(nogpu_list)} 台")
        log.info(f"{'='*60}")

        for i, dev in enumerate(nogpu_list):
            did = dev['device_id']
            log.info(f"\n  [{i+1}/{len(nogpu_list)}] {dev['name']} ({did})")
            try:
                goto_list(driver)
                click_refresh_btn(driver)
                row = find_row_by_id(driver, did)

                if is_running(row):
                    log.info(f"    已运行，直接关机")
                    stop_by_row(driver, row)
                    r = wait_stopped(driver, did, timeout=120)
                    results[did] = 'ok' if r else 'fail'
                    continue

                if not is_stopped(row):
                    log.info(f"    不是关机状态，等10秒...")
                    time.sleep(10)
                    click_refresh_btn(driver)
                    row = find_row_by_id(driver, did)
                    if not is_stopped(row):
                        log.warning(f"    仍不是关机，跳过")
                        results[did] = 'skip'; continue

                log.info(f"    无卡开机...")
                start_nogpu_by_row(driver, row)
                r = wait_running(driver, did, timeout=180)
                if not r:
                    log.error(f"    开机超时"); results[did] = 'fail'; continue

                log.info(f"    ✓ 已运行，关机...")
                time.sleep(1)
                goto_list(driver)
                click_refresh_btn(driver)
                row = find_row_by_id(driver, did)
                stop_by_row(driver, row)
                r = wait_stopped(driver, did, timeout=120)
                results[did] = 'ok' if r else 'fail'
                if r: log.info(f"    ✓ 已关机")
                else: log.error(f"    ✗ 关机超时")

            except Exception as e:
                log.error(f"    异常: {e}")
                results[did] = 'fail'

    # ══════════════════════════════════════
    #  最终检查
    # ══════════════════════════════════════
    log.info(f"\n{'='*60}")
    log.info("最终检查：确保所有设备已关机")
    goto_list(driver)
    click_refresh_btn(driver)
    final_devices = parse_all_devices(driver)
    for dev in final_devices:
        if is_running(dev['row']):
            log.warning(f"  {dev['name']} 仍在运行，关机...")
            try:
                stop_by_row(driver, dev['row'])
                wait_stopped(driver, dev['device_id'], timeout=60)
            except Exception as e:
                log.error(f"  最终关机失败: {e}")

    # 汇总
    log.info(f"\n{'='*60}")
    log.info("续费结果汇总:")
    for did, result in results.items():
        tag = {'ok': '✓', 'fail': '✗', 'skip': '⊘'}.get(result, '?')
        name = next((d['name'] for d in devices if d['device_id'] == did), did)
        log.info(f"  {tag} {name} ({did}): {result}")
    ok = sum(1 for v in results.values() if v == 'ok')
    fail = sum(1 for v in results.values() if v == 'fail')
    skip = sum(1 for v in results.values() if v == 'skip')
    total = len(devices)
    log.info(f"成功={ok} 失败={fail} 跳过={skip} / 共{total}台")
    log.info(f"{'='*60}")


if __name__ == '__main__':
    auto = '--yes' in sys.argv or '-y' in sys.argv

    user, pwd = get_credentials()
    if not user or not pwd:
        log.error("未找到凭据，请检查 configs/autodl_credentials.json")
        sys.exit(1)

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
