#!/usr/bin/env python3
"""自动化测试 AutoDL 登录与开机流程"""

import os
import sys
import time
import webbrowser
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
    ElementClickInterceptedException,
)
from webdriver_manager.chrome import ChromeDriverManager

CONFIG_DIR = os.path.join(os.path.expanduser('~'), '.autodl_auto_starter', 'configs')
COOKIES_FILE = os.path.join(CONFIG_DIR, 'cookies.json')
CREDS_FILE = os.path.join(CONFIG_DIR, 'credentials.json')

def setup_driver(headless=False):
    print('[Test] 初始化Chrome...')
    chrome_options = Options()
    if headless:
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1400,900')
    chrome_options.add_argument('--force-device-scale-factor=0.9')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-plugins')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    # 禁用密码管理器与保存密码气泡
    chrome_options.add_experimental_option('prefs', {
        'credentials_enable_service': False,
        'profile.password_manager_enabled': False,
    })
    chrome_options.add_argument('--disable-features=PasswordManagerEnabled,AutofillSaveCardBubble')
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    print('[Test] Chrome 启动成功')
    return driver

def save_cookies(driver):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        import json
        cookies = driver.get_cookies()
        with open(COOKIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        print(f'[Test] 已保存 {len(cookies)} 个 cookies')
    except Exception as e:
        print(f'[Test] 保存cookies失败: {e}')

def load_cookies(driver):
    try:
        import json, time as _t
        if not os.path.exists(COOKIES_FILE):
            return False
        with open(COOKIES_FILE, 'r', encoding='utf-8') as f:
            cookies = json.load(f)
        valid = []
        now = int(_t.time())
        for c in cookies:
            try:
                if 'expiry' in c and c['expiry'] and c['expiry'] < now:
                    continue
                clean = {k: v for k, v in c.items() if k in ('name','value','domain','path','secure','httpOnly','expiry')}
                valid.append(clean)
            except Exception:
                continue
        driver.get('https://www.autodl.com/')
        for c in valid:
            try:
                driver.add_cookie(c)
            except Exception:
                pass
        print(f'[Test] 已加载 {len(valid)} 个有效cookies')
        return len(valid) > 0
    except Exception as e:
        print(f'[Test] 加载cookies失败: {e}')
        return False

def read_credentials():
    user = os.environ.get('AUTODL_USER', '')
    pwd = os.environ.get('AUTODL_PASS', '')
    if user and pwd:
        return user, pwd
    try:
        import json
        if os.path.exists(CREDS_FILE):
            with open(CREDS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data.get('remember_password'):
                return data.get('username',''), data.get('password','')
    except Exception:
        pass
    return user, pwd

def login(driver):
    print('[Test] 尝试使用cookies登录...')
    cookies_ok = False
    try:
        driver.get('https://www.autodl.com')
        cookies_ok = load_cookies(driver)
        if cookies_ok:
            driver.get('https://www.autodl.com/console/instance/list')
            time.sleep(2)
            if 'login' not in driver.current_url:
                print('[Test] 使用cookies登录成功')
                return True
            else:
                print('[Test] cookies已失效，转账号登录')
    except Exception as e:
        print(f'[Test] cookies登录失败: {e}')

    user, pwd = read_credentials()
    if not user or not pwd:
        print('[Test] 缺少登录凭据（环境变量 AUTODL_USER/AUTODL_PASS 或 credentials.json）')
        return False

    print('[Test] 正在进行账号密码登录...')
    driver.get('https://www.autodl.com/login')
    wait = WebDriverWait(driver, 20)
    # 模仿主程序选择器：第3个 text 输入为手机号
    all_text_inputs = wait.until(lambda d: d.find_elements(By.XPATH, "//input[@type='text']"))
    if len(all_text_inputs) < 3:
        print('[Test] 未找到手机号文本输入框')
        return False
    username_input = all_text_inputs[2]
    password_input = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@type='password']")))
    username_input.clear(); password_input.clear()
    username_input.send_keys(user)
    password_input.send_keys(pwd)
    # 关闭保存密码气泡
    try:
        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    except Exception:
        pass
    # 登录按钮按 Element UI 主按钮类名
    login_button = driver.find_element(By.CSS_SELECTOR, '.el-button--primary')
    driver.execute_script('arguments[0].scrollIntoView({block:"center"});', login_button)
    time.sleep(0.5)
    clickable = WebDriverWait(driver, 10).until(EC.element_to_be_clickable(login_button))
    clickable.click()
    time.sleep(3)
    # 登录成功判定
    if 'login' not in driver.current_url:
        save_cookies(driver)
        print('[Test] 登录成功并已保存cookies')
        return True
    print('[Test] 登录失败：仍在登录页')
    return False

def goto_instance_list(driver):
    print('[Test] 进入实例列表页面...')
    driver.get('https://www.autodl.com/console/instance/list')
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, 'table')))
    print('[Test] 列表表格已出现')
    # 滚动把表格置中，避免顶部导航遮挡
    driver.execute_script('window.scrollBy(0, 200);')
    return True

def find_row_by_device_id(driver, device_id):
    # 兼容 tr 与 el-table__row
    xpath = f"//*[contains(normalize-space(.), '{device_id}')]"
    el = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, xpath)))
    try:
        row = el.find_element(By.XPATH, 'ancestor::tr[1]')
    except Exception:
        row = el.find_element(By.XPATH, "ancestor::*[contains(@class,'el-table__row')][1]")
    return row

def find_row_by_remark(driver, remark_text):
    xpath = f"//*[contains(normalize-space(), '{remark_text}')]"
    el_list = driver.find_elements(By.XPATH, xpath)
    for el in el_list:
        try:
            try:
                row = el.find_element(By.XPATH, 'ancestor::tr[1]')
            except Exception:
                row = el.find_element(By.XPATH, "ancestor::*[contains(@class,'el-table__row')][1]")
            return row
        except Exception:
            continue
    raise NoSuchElementException('未找到包含备注的设备行')

def start_by_row(driver, row):
    # 只在最后一列查找“开机”
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
        # 下拉菜单触发器
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
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", trigger)
            try:
                ActionChains(driver).move_to_element(trigger).click().perform()
            except Exception:
                driver.execute_script('arguments[0].click();', trigger)
            # 仅使用与当前触发器最近的下拉菜单，避免误点其他行
            menu_el = driver.execute_script(
                "const t=arguments[0];const tr=t.getBoundingClientRect();\n"
                "const menus=[...document.querySelectorAll('.el-dropdown-menu')].filter(m=>m.offsetParent!==null);\n"
                "if(menus.length===0){return null;}\n"
                "let best=null;\n"
                "for(const m of menus){const r=m.getBoundingClientRect();const d=Math.hypot((r.left-tr.left),(r.top-tr.bottom));\n"
                " if(!best||d<best.d){best={el:m,d:d};}}\n"
                "return best?best.el:null;"
            , trigger)
            if menu_el:
                # 在目标菜单中找“开机”项并点击
                driver.execute_script(
                    "const menu=arguments[0];\n"
                    "const items=[...menu.querySelectorAll('*')];\n"
                    "const target=items.find(n=>/开机/.test((n.textContent||'').trim()));\n"
                    "if(target){target.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));}"
                , menu_el)
                # 确认弹窗将由后续逻辑处理
                btn = None
    if btn is None:
        raise NoSuchElementException('未找到开机按钮')
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
    ActionChains(driver).move_to_element(btn).pause(0.2).perform()
    try:
        WebDriverWait(driver, 5).until(EC.element_to_be_clickable(btn))
        btn.click()
    except ElementClickInterceptedException:
        driver.execute_script('arguments[0].click();', btn)
    # 确认：兼容多种弹层（MessageBox/Dialog/Popconfirm）
    def click_confirm():
        candidates = [
            "//div[contains(@class,'el-message-box')]//button[.//span[contains(normalize-space(),'确定')]]",
            "//div[contains(@class,'el-dialog__footer')]//button[.//span[contains(normalize-space(),'确定')]]",
            "//div[contains(@class,'el-popconfirm')]//button[.//span[contains(normalize-space(),'确定')]]",
            "//button[.//span[contains(normalize-space(),'确定')]]",
            "//*[contains(normalize-space(),'确定')]/ancestor::button"
        ]
        btn = None
        for xp in candidates:
            try:
                btn = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, xp)))
                break
            except TimeoutException:
                continue
        if not btn:
            raise TimeoutException('未找到确认按钮')
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            ActionChains(driver).move_to_element(btn).pause(0.1).perform()
            WebDriverWait(driver, 5).until(EC.element_to_be_clickable(btn))
            btn.click()
        except ElementClickInterceptedException:
            driver.execute_script('arguments[0].click();', btn)
        except Exception:
            driver.execute_script('arguments[0].click();', btn)
        return True
    click_confirm()
    return True

def stop_by_row(driver, row):
    try:
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
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", trigger)
                try:
                    ActionChains(driver).move_to_element(trigger).click().perform()
                except Exception:
                    driver.execute_script('arguments[0].click();', trigger)
                menu_el = driver.execute_script(
                    "const t=arguments[0];const tr=t.getBoundingClientRect();\n"
                    "const menus=[...document.querySelectorAll('.el-dropdown-menu')].filter(m=>m.offsetParent!==null);\n"
                    "if(menus.length===0){return null;}\n"
                    "let best=null;\n"
                    "for(const m of menus){const r=m.getBoundingClientRect();const d=Math.hypot((r.left-tr.left),(r.top-tr.bottom));\n"
                    " if(!best||d<best.d){best={el:m,d:d};}}\n"
                    "return best?best.el:null;",
                    trigger)
                if menu_el:
                    driver.execute_script(
                        "const menu=arguments[0];\n"
                        "const items=[...menu.querySelectorAll('*')];\n"
                        "const target=items.find(n=>/关机/.test((n.textContent||'').trim()));\n"
                        "if(target){target.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));}",
                        menu_el)
                    btn = None
        if btn is None:
            return False
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
        ActionChains(driver).move_to_element(btn).pause(0.2).perform()
        try:
            WebDriverWait(driver, 5).until(EC.element_to_be_clickable(btn))
            btn.click()
        except ElementClickInterceptedException:
            driver.execute_script('arguments[0].click();', btn)
        def click_confirm():
            candidates = [
                "//div[contains(@class,'el-message-box')]//button[.//span[contains(normalize-space(),'确定')]]",
                "//div[contains(@class,'el-dialog__footer')]//button[.//span[contains(normalize-space(),'确定')]]",
                "//div[contains(@class,'el-popconfirm')]//button[.//span[contains(normalize-space(),'确定')]]",
                "//button[.//span[contains(normalize-space(),'确定')]]",
                "//*[contains(normalize-space(),'确定')]/ancestor::button"
            ]
            btn2 = None
            for xp in candidates:
                try:
                    btn2 = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, xp)))
                    break
                except TimeoutException:
                    continue
            if not btn2:
                return False
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn2)
                ActionChains(driver).move_to_element(btn2).pause(0.1).perform()
                WebDriverWait(driver, 5).until(EC.element_to_be_clickable(btn2))
                btn2.click()
            except ElementClickInterceptedException:
                driver.execute_script('arguments[0].click();', btn2)
            except Exception:
                driver.execute_script('arguments[0].click();', btn2)
            return True
        click_confirm()
        return True
    except Exception:
        return False

def verify_running(driver, row):
    # 刷新列表并读取状态列
    driver.get('https://www.autodl.com/console/instance/list')
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, 'table')))
    try:
        tds = row.find_elements(By.TAG_NAME, 'td')
        status_text = tds[1].text if len(tds) >= 2 else row.text
    except StaleElementReferenceException:
        status_text = ''
    # 宽松判断
    return ('运行中' in status_text) or ('开机' in status_text.lower())

def pick_first_stopped_row(driver):
    # 选择第一条“已关机”
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, 'table')))
    # 优先用 tr
    rows = driver.find_elements(By.XPATH, '//table//tr')
    if len(rows) <= 1:
        rows = driver.find_elements(By.XPATH, "//*[contains(@class,'el-table__row')]")
    for r in rows[1:]:
        try:
            tds = r.find_elements(By.TAG_NAME, 'td')
            status = tds[1].text if len(tds) >= 2 else r.text
            if '已关机' in status or 'stopped' in status.lower():
                return r
        except Exception:
            continue
    raise NoSuchElementException('未找到已关机设备行')

def click_jupyterlab_by_row(driver, row, open_local=True, verify=True):
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
            js_el = driver.execute_script(
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
    if btn is None:
        try:
            js_el2 = driver.execute_script(
                "const row=arguments[0];\n"
                "const r=row.getBoundingClientRect();\n"
                "const anchors=[...document.querySelectorAll('a')].filter(a=>{const href=(a.href||'').toLowerCase();\n"
                "  return href.includes('lab')||href.includes('jupyter');});\n"
                "let best=null;\n"
                "for(const a of anchors){const br=a.getBoundingClientRect();\n"
                "  const dv=Math.abs((br.top+br.bottom)/2 - (r.top+r.bottom)/2);\n"
                "  if(br.bottom>=r.top-2 && br.top<=r.bottom+2){\n"
                "    if(!best||dv<best.dv){best={el:a,dv:dv};}\n"
                "  }\n"
                "}\n"
                "return best?best.el:null;",
                row)
            if js_el2:
                btn = js_el2
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
            frames = driver.find_elements(By.TAG_NAME, 'iframe')
        except Exception:
            frames = []
        for fr in frames:
            try:
                if not fr.is_displayed():
                    continue
            except Exception:
                pass
            ok_switched = False
            try:
                driver.switch_to.frame(fr)
                ok_switched = True
            except Exception:
                ok_switched = False
            if not ok_switched:
                continue
            try:
                cand_in_frame = None
                for xp in [
                    "//a[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'jupyterlab')]",
                    "//a[contains(@href,'lab') or contains(@href,'jupyter')]",
                    "//button[.//span[contains(translate(normalize-space(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'jupyter')]]",
                ]:
                    try:
                        cand_in_frame = driver.find_element(By.XPATH, xp)
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
            except Exception:
                pass
            try:
                driver.switch_to.default_content()
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
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", trigger)
            try:
                ActionChains(driver).move_to_element(trigger).click().perform()
            except Exception:
                driver.execute_script('arguments[0].click();', trigger)
            menu_el = driver.execute_script(
                "const t=arguments[0];const tr=t.getBoundingClientRect();\n"
                "const menus=[...document.querySelectorAll('.el-dropdown-menu')].filter(m=>m.offsetParent!==null);\n"
                "if(menus.length===0){return null;}\n"
                "let best=null;\n"
                "for(const m of menus){const r=m.getBoundingClientRect();const d=Math.hypot((r.left-tr.left),(r.top-tr.bottom));\n"
                " if(!best||d<best.d){best={el:m,d:d};}}\n"
                "return best?best.el:null;",
                trigger)
            if menu_el:
                found_href = driver.execute_script(
                    "const menu=arguments[0];\n"
                    "const items=[...menu.querySelectorAll('*')];\n"
                    "const target=items.find(n=>/jupyterlab/i.test((n.textContent||'').trim()));\n"
                    "let href='';\n"
                    "if(target){const a=target.closest('a')||target.querySelector('a'); if(a&&a.href){href=a.href;} target.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));}\n"
                    "return href;",
                    menu_el)
                try:
                    if isinstance(found_href, str) and found_href:
                        got_url = found_href
                except Exception:
                    pass
                btn = None
    if btn is None:
        raise NoSuchElementException('未找到JupyterLab按钮')
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
    ActionChains(driver).move_to_element(btn).pause(0.2).perform()
    try:
        WebDriverWait(driver, 5).until(EC.element_to_be_clickable(btn))
        handles_before = list(driver.window_handles)
        btn.click()
    except ElementClickInterceptedException:
        driver.execute_script('arguments[0].click();', btn)
        handles_before = list(driver.window_handles)
    time.sleep(0.5)
    handles_after = list(driver.window_handles)
    opened_in_webdriver = False
    if len(handles_after) > len(handles_before):
        new_handles = [h for h in handles_after if h not in handles_before]
        for h in new_handles:
            try:
                driver.switch_to.window(h)
                opened_in_webdriver = True
                try:
                    cu = driver.current_url
                    if cu:
                        got_url = cu
                except Exception:
                    pass
                if verify:
                    try:
                        WebDriverWait(driver, 10).until(lambda d: d.execute_script('return document.readyState') in ['interactive','complete'])
                    except Exception:
                        pass
                    try:
                        ttl = driver.title
                        print('[Test] JupyterLab页面标题:', ttl)
                    except Exception:
                        pass
                    try:
                        bodytxt = driver.find_element(By.TAG_NAME, 'body').text
                        if bodytxt:
                            print('[Test] JupyterLab页面文本采样:', bodytxt[:80])
                    except Exception:
                        pass
                    try:
                        driver.save_screenshot('jupyterlab_opened.png')
                    except Exception:
                        pass
                time.sleep(2)
                try:
                    driver.close()
                except Exception:
                    pass
            except Exception:
                pass
        try:
            driver.switch_to.window(handles_before[0])
        except Exception:
            pass
    elif got_url and verify:
        try:
            handles_before = list(driver.window_handles)
            driver.execute_script('window.open(arguments[0])', got_url)
            time.sleep(0.5)
            handles_after = list(driver.window_handles)
            if len(handles_after) > len(handles_before):
                h = [x for x in handles_after if x not in handles_before][0]
                driver.switch_to.window(h)
                opened_in_webdriver = True
                try:
                    WebDriverWait(driver, 10).until(lambda d: d.execute_script('return document.readyState') in ['interactive','complete'])
                except Exception:
                    pass
                try:
                    ttl = driver.title
                    print('[Test] JupyterLab页面标题:', ttl)
                except Exception:
                    pass
                try:
                    driver.save_screenshot('jupyterlab_opened.png')
                except Exception:
                    pass
                time.sleep(2)
                try:
                    driver.close()
                except Exception:
                    pass
                try:
                    driver.switch_to.window(handles_before[0])
                except Exception:
                    pass
        except Exception:
            pass
    if open_local and got_url:
        try:
            webbrowser.open(got_url)
        except Exception:
            pass
    return got_url

def run_test(device_id=None, remark_text=None):
    driver = setup_driver(headless=False)
    try:
        if not login(driver):
            print('[Test] 登录失败，终止')
            return False
        ok = goto_instance_list(driver)
        if not ok:
            print('[Test] 进入列表失败')
            return False
        print('[Test] 开始选择设备...')
        row = None
        if device_id:
            print(f'[Test] 指定设备ID: {device_id}')
            try:
                row = find_row_by_device_id(driver, device_id)
            except Exception:
                row = None
        if row is None and remark_text:
            print(f'[Test] 尝试按备注定位: {remark_text}')
            try:
                row = find_row_by_remark(driver, remark_text)
            except Exception:
                row = None
        if row is None:
            print('[Test] 未提供或未找到指定设备，选择第一台已关机设备')
            row = pick_first_stopped_row(driver)
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", row)
        time.sleep(0.3)
        def extract_id_from_row(r):
            import re as _re
            try:
                txt = r.text
                m = _re.search(r'[a-fA-F0-9\-]{6,}', txt)
                return m.group(0) if m else ''
            except Exception:
                return ''
        def extract_remark_from_row(r):
            try:
                lines = [ln.strip() for ln in r.text.split('\n') if ln.strip()]
                import re as _re
                for ln in lines[1:]:
                    if '-' in ln and _re.fullmatch(r'[a-fA-F0-9\-]{6,}', ln):
                        continue
                    return ln
                return lines[2] if len(lines) >= 3 else ''
            except Exception:
                return ''
        did = device_id or extract_id_from_row(row)
        remark = remark_text or extract_remark_from_row(row)
        if verify_running(driver, row):
            print('[Test] 设备已运行，跳过开机')
        else:
            print('[Test] 已定位到设备行，准备点击开机')
            r_try = None
            for _ in range(3):
                try:
                    goto_instance_list(driver)
                    r_try = None
                    if did:
                        try:
                            r_try = find_row_by_device_id(driver, did)
                        except Exception:
                            r_try = None
                    if r_try is None and remark:
                        try:
                            r_try = find_row_by_remark(driver, remark)
                        except Exception:
                            r_try = None
                    target_row = r_try or row
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_row)
                    time.sleep(0.3)
                    ok = start_by_row(driver, target_row)
                    if ok:
                        break
                except Exception:
                    time.sleep(0.5)
            else:
                print('[Test] 开机点击失败，可能当前已运行或按钮在菜单内未可见')
                time.sleep(1)
            time.sleep(2)
        print('[Test] 等待状态切换为运行中...')
        
        def wait_for_running(drv, dev_id, remark_text, timeout=120, interval=5):
            start_t = time.time()
            while time.time() - start_t < timeout:
                try:
                    goto_instance_list(drv)
                    r = None
                    if dev_id:
                        try:
                            r = find_row_by_device_id(drv, dev_id)
                        except Exception:
                            r = None
                    if r is None and remark_text:
                        try:
                            r = find_row_by_remark(drv, remark_text)
                        except Exception:
                            r = None
                    if r is None:
                        print('[Test] 未定位到目标设备行，继续等待...')
                        time.sleep(interval)
                        continue
                    tds = r.find_elements(By.TAG_NAME, 'td')
                    st = tds[1].text if len(tds) >= 2 else r.text
                    op = tds[-1].text if len(tds) >= 1 else ''
                    norm = lambda s: ''.join(s.split())
                    if ('运行中' in st) or ('running' in st.lower()) or ('关机' in op):
                        print(f"[Test] 当前状态: {st} | 操作列: {op} → 判定运行中")
                        return True
                    if any(k in st for k in ['开机中','正在开机','启动中','正在启动','starting','booting']):
                        print(f"[Test] 当前状态: {st} → 仍在启动，继续等待...")
                        time.sleep(interval)
                        continue
                    if '已关机' in st or 'stopped' in st.lower() or ('开机' in op):
                        print(f"[Test] 当前状态: {st} | 操作列: {op} → 仍为关机，继续等待...")
                        time.sleep(interval)
                        continue
                    print(f"[Test] 当前状态: {st} | 操作列: {op} → 未识别，继续等待...")
                    time.sleep(interval)
                except Exception:
                    print('[Test] 获取状态失败，重试...')
                    time.sleep(interval)
            return False
        if wait_for_running(driver, did, remark):
            print('[Test] 验证成功：设备已运行')
            goto_instance_list(driver)
            try:
                r2 = find_row_by_device_id(driver, did)
            except Exception:
                r2 = find_row_by_remark(driver, remark)
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", r2)
            time.sleep(0.3)
            print('[Test] 尝试点击JupyterLab...')
            opened = False
            jl_url = ''
            for _ in range(8):
                try:
                    jl_url = click_jupyterlab_by_row(driver, r2, open_local=True, verify=True)
                    if jl_url:
                        opened = True
                        break
                except Exception as e:
                    time.sleep(1.0)
                    goto_instance_list(driver)
                    try:
                        r2 = find_row_by_device_id(driver, did)
                    except Exception:
                        r2 = find_row_by_remark(driver, remark)
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", r2)
                    time.sleep(0.3)
            if opened:
                print(f"[Test] JupyterLab URL: {jl_url}")
            else:
                print("[Test] 多次尝试后仍未获取到 JupyterLab URL")
            # 开机成功后执行关机流程
            print('[Test] 准备执行关机流程...')
            # 重新定位同一设备行
            goto_instance_list(driver)
            try:
                r2 = find_row_by_device_id(driver, did)
            except Exception:
                r2 = find_row_by_remark(driver, remark)
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", r2)
            time.sleep(0.3)
            ok2 = stop_by_row(driver, r2)
            if not ok2:
                print('[Test] 关机点击失败')
                return False
            print('[Test] 等待状态切换为已关机...')
            def wait_for_stopped(drv, dev_id, remark_text, timeout=120, interval=5):
                start_t = time.time()
                while time.time() - start_t < timeout:
                    try:
                        goto_instance_list(drv)
                        rr = None
                        if dev_id:
                            try:
                                rr = find_row_by_device_id(drv, dev_id)
                            except Exception:
                                rr = None
                        if rr is None and remark_text:
                            try:
                                rr = find_row_by_remark(drv, remark_text)
                            except Exception:
                                rr = None
                        if rr is None:
                            print('[Test] 未定位到目标设备行，继续等待...')
                            time.sleep(interval)
                            continue
                        tds = rr.find_elements(By.TAG_NAME, 'td')
                        st = tds[1].text if len(tds) >= 2 else rr.text
                        op = tds[-1].text if len(tds) >= 1 else ''
                        if ('已关机' in st) or ('stopped' in st.lower()) or ('开机' in op):
                            print(f"[Test] 当前状态: {st} | 操作列: {op} → 判定已关机")
                            return True
                        print(f"[Test] 当前状态: {st} | 操作列: {op} → 仍在关闭过程中，继续等待...")
                        time.sleep(interval)
                    except Exception:
                        time.sleep(interval)
                return False
            if wait_for_stopped(driver, did, remark):
                print('[Test] 验证成功：设备已关机')
                return True
            print('[Test] 验证失败：状态未切换为已关机')
            return False
        print('[Test] 验证失败：状态未切换为运行中')
        return False
    except Exception as e:
        print(f'[Test] 运行出错: {e}')
        import traceback
        traceback.print_exc()
        return False
    finally:
        try:
            driver.quit()
        except Exception:
            pass

def test_chrome_init():
    """测试Chrome初始化"""
    print("正在初始化Chrome浏览器...")
    try:
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-plugins')
        chrome_options.add_argument('--disable-images')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        print("Chrome浏览器初始化成功!")
        print(f"Chrome版本: {driver.capabilities['browserVersion']}")
        print(f"ChromeDriver版本: {driver.capabilities['chrome']['chromedriverVersion']}")
        
        # 测试访问AutoDL登录页面
        print("正在访问AutoDL登录页面...")
        driver.get('https://www.autodl.com/login')
        time.sleep(3)
        
        print(f"当前URL: {driver.current_url}")
        print(f"页面标题: {driver.title}")
        
        # 检查是否能找到登录表单
        try:
            wait = WebDriverWait(driver, 10)
            username_input = wait.until(EC.presence_of_element_located((By.NAME, 'username')))
            print("✓ 找到用户名输入框")
            
            password_input = driver.find_element(By.NAME, 'password')
            print("✓ 找到密码输入框")
            
            login_button = driver.find_element(By.XPATH, '//button[@type="submit"]')
            print("✓ 找到登录按钮")
            
            # 测试输入
            username_input.clear()
            username_input.send_keys('test_user')
            print("✓ 成功输入测试用户名")
            
        except TimeoutException:
            print("✗ 超时: 无法找到登录表单元素")
            print("页面源代码:")
            print(driver.page_source[:500] + "...")
        
        driver.quit()
        print("测试完成!")
        return True
        
    except Exception as e:
        print(f"错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='AutoDL 开机自动化测试')
    parser.add_argument('--device', dest='device_id', default=os.environ.get('DEVICE_ID',''))
    parser.add_argument('--remark', dest='remark', default=os.environ.get('DEVICE_REMARK',''))
    args = parser.parse_args()
    print('=== AutoDL 开机自动化测试 ===')
    success = run_test(device_id=args.device_id or None, remark_text=args.remark or None)
    sys.exit(0 if success else 1)