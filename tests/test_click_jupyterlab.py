#!/usr/bin/env python3
import argparse
import time
import os
import json
import webbrowser
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException


def init_driver(headless=False):
    chrome_options = Options()
    if headless:
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    driver = webdriver.Chrome(options=chrome_options)
    try:
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    except Exception:
        pass
    try:
        driver.set_window_size(1366, 900)
    except Exception:
        pass
    return driver


def login(driver, username, password):
    driver.get('https://www.autodl.com/login')
    wait = WebDriverWait(driver, 20)
    wait.until(lambda d: d.execute_script('return document.readyState') in ['interactive','complete'])
    text_inputs = wait.until(lambda d: d.find_elements(By.XPATH, "//input[@type='text']"))
    if len(text_inputs) >= 3:
        username_input = text_inputs[2]
    else:
        username_input = wait.until(EC.presence_of_element_located((By.NAME, 'username')))
    password_input = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@type='password']")))
    username_input.clear(); username_input.send_keys(username)
    password_input.clear(); password_input.send_keys(password)
    try:
        login_button = driver.find_element(By.CSS_SELECTOR, '.el-button--primary')
    except Exception:
        login_button = driver.find_element(By.XPATH, "//button[@type='submit']")
    driver.execute_script("arguments[0].scrollIntoView(true);", login_button)
    time.sleep(0.5)
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable(login_button)).click()
    WebDriverWait(driver, 15).until(lambda d: 'login' not in d.current_url)


def goto_list(driver):
    list_url = 'https://www.autodl.com/console/instance/list'
    driver.get(list_url)
    WebDriverWait(driver, 20).until(lambda d: d.execute_script('return document.readyState') in ['interactive','complete'])
    try:
        cu = driver.current_url
        if '/console/instance/list' not in cu:
            driver.get(list_url)
            WebDriverWait(driver, 20).until(lambda d: d.execute_script('return document.readyState') in ['interactive','complete'])
    except Exception:
        pass
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, '.el-table')))
    except TimeoutException:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'table')))
    try:
        WebDriverWait(driver, 15).until(lambda d: (
            len(d.find_elements(By.CSS_SELECTOR, '.el-table__body tbody tr'))>0 or
            len(d.find_elements(By.CSS_SELECTOR, '.el-table__row'))>0
        ))
    except Exception:
        pass
    driver.execute_script("document.body.style.zoom='70%'")


def find_row_by_id(driver, device_id):
    try:
        row = driver.find_element(By.XPATH, f"//*[contains(normalize-space(.), '{device_id}')]//ancestor::tr[.//td][1]")
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", row)
        time.sleep(0.3)
        return row
    except Exception:
        try:
            rows = []
            selectors = [
                '.el-table__body-wrapper tbody tr',
                '.el-table__body tbody tr',
                'tbody tr',
                '.el-table__row',
            ]
            for sel in selectors:
                try:
                    rows = driver.find_elements(By.CSS_SELECTOR, sel)
                    if rows:
                        break
                except Exception:
                    continue
            print('候选行数:', len(rows))
            seg = []
            for r in rows[:6]:
                try:
                    seg.append(r.text.strip()[:32])
                except Exception:
                    pass
            if seg:
                print('候选行片段:', ' | '.join(seg))
            for r in rows:
                txt = r.text.lower()
                if device_id and device_id.lower() in txt:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", r)
                    time.sleep(0.2)
                    return r
        except Exception:
            pass
        return None


def find_row_by_remark(driver, remark):
    try:
        rows = []
        selectors = [
            '.el-table__body-wrapper tbody tr',
            '.el-table__body tbody tr',
            'tbody tr',
            '.el-table__row',
        ]
        for sel in selectors:
            try:
                rows = driver.find_elements(By.CSS_SELECTOR, sel)
                if rows:
                    break
            except Exception:
                continue
        print('候选行数:', len(rows))
        seg = []
        for r in rows[:6]:
            try:
                seg.append(r.text.strip()[:32])
            except Exception:
                pass
        if seg:
            print('候选行片段:', ' | '.join(seg))
        for r in rows:
            if remark and remark.lower() in r.text.lower():
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", r)
                time.sleep(0.2)
                return r
    except Exception:
        pass
    try:
        row = driver.find_element(By.XPATH, f"//*[contains(normalize-space(.), '{remark}')]//ancestor::tr[.//td][1]")
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", row)
        time.sleep(0.2)
        return row
    except Exception:
        return None


def find_row_by_any(driver, device_id, remark):
    row = None
    try:
        if device_id:
            row = find_row_by_id(driver, device_id)
    except Exception:
        row = None
    if row is None and remark:
        try:
            row = find_row_by_remark(driver, remark)
        except Exception:
            row = None
    return row


def click_jupyterlab_in_row(driver, row, open_local=True):
    candidates = [
        ".//a[contains(normalize-space(), 'JupyterLab')]",
        ".//a[contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'jupyterlab')]",
        ".//button[.//span[contains(normalize-space(), 'JupyterLab')]]",
        ".//span[contains(@class,'el-button__text') and contains(normalize-space(),'JupyterLab')]",
        ".//a[contains(@href,'lab') or contains(@href,'jupyter') or contains(@href,'/lab') ]",
    ]
    btn = None; href = ''
    for xp in candidates:
        try:
            btn = row.find_element(By.XPATH, xp)
            href = btn.get_attribute('href') or ''
            break
        except Exception:
            continue
    if btn is None:
        try:
            js_el = driver.execute_script(
                "const row=arguments[0];\n"
                "const r=row.getBoundingClientRect();\n"
                "const links=[...document.querySelectorAll('a')];\n"
                "const cand=links.find(a=>{const t=(a.textContent||'').trim().toLowerCase();\n"
                "  if(!(t.includes('jupyterlab'))) return false;\n"
                "  const br=a.getBoundingClientRect();\n"
                "  return br.top>=r.top-2 && br.bottom<=r.bottom+2 && br.left>=r.left-2 && br.right<=r.right+2;\n"
                "});\n"
                "return cand||null;",
                row)
            if js_el:
                btn = js_el
                href = btn.get_attribute('href') or ''
        except Exception:
            pass
    if btn is None:
        tds = row.find_elements(By.TAG_NAME, 'td')
        action_td = tds[-1] if tds else row
        trigger = None
        for tx in [
            ".//*[contains(@class,'el-dropdown')]",
            ".//*[contains(@class,'el-icon-more')]",
            ".//*[contains(normalize-space(),'更多')]",
        ]:
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
                if isinstance(found_href, str) and found_href:
                    href = found_href
        if btn is None:
            raise NoSuchElementException('未找到JupyterLab按钮')
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
    ActionChains(driver).move_to_element(btn).pause(0.1).perform()
    try:
        WebDriverWait(driver, 5).until(EC.element_to_be_clickable(btn))
        handles_before = list(driver.window_handles)
        btn.click()
    except ElementClickInterceptedException:
        driver.execute_script('arguments[0].click();', btn)
        handles_before = list(driver.window_handles)
    time.sleep(0.5)
    handles_after = list(driver.window_handles)
    if len(handles_after) > len(handles_before):
        new_handles = [h for h in handles_after if h not in handles_before]
        for h in new_handles:
            try:
                driver.switch_to.window(h)
                cu = driver.current_url
                if cu:
                    href = cu
                driver.close()
            except Exception:
                pass
        try:
            driver.switch_to.window(handles_before[0])
        except Exception:
            pass
    if open_local and href:
        try:
            webbrowser.open(href)
        except Exception:
            pass
    return href


def is_running(row):
    try:
        tds = row.find_elements(By.TAG_NAME, 'td')
        st = tds[1].text if len(tds) >= 2 else row.text
        op = tds[-1].text if len(tds) >= 1 else ''
        st_low = st.lower()
        if (
            ('运行中' in st) or ('running' in st_low) or ('关机' in op)
        ):
            return True
        return False
    except Exception:
        return False


def is_stopped(row):
    try:
        tds = row.find_elements(By.TAG_NAME, 'td')
        st = tds[1].text if len(tds) >= 2 else row.text
        op = tds[-1].text if len(tds) >= 1 else ''
        stl = st.lower()
        if ('已关机' in st) or ('stopped' in stl) or ('开机' in op):
            return True
        return False
    except Exception:
        return False


def has_nogpu_mode(row):
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


def wait_for_running_nogpu(driver, device_id, remark='', timeout=300, interval=4):
    start_t = time.time()
    last = ''
    while time.time() - start_t < timeout:
        try:
            goto_list(driver)
            r = find_row_by_any(driver, device_id, remark)
            if r and is_running(r) and has_nogpu_mode(r):
                return r
            # 打印当前列文本以便调试
            try:
                tds = r.find_elements(By.TAG_NAME, 'td') if r else []
                st = tds[1].text if len(tds) >= 2 else (r.text if r else '')
                specs = tds[2].text if len(tds) >= 3 else ''
                now = (st + " | " + specs).strip()
                if now and now != last:
                    print('当前状态列/规格详情:', now[:160])
                    last = now
                # 过渡态继续等
                if any(k in st for k in ['开机中','正在开机','启动中','正在启动']) or any(k in st.lower() for k in ['pending','starting','booting']):
                    time.sleep(interval)
                    continue
            except Exception:
                pass
            time.sleep(interval)
        except Exception:
            time.sleep(interval)
    return None


def wait_until_stopped(driver, device_id, remark='', timeout=240, interval=3):
    start_t = time.time()
    last = ''
    while time.time() - start_t < timeout:
        try:
            goto_list(driver)
            r = find_row_by_any(driver, device_id, remark)
            if r:
                try:
                    tds = r.find_elements(By.TAG_NAME, 'td')
                    st = tds[1].text if len(tds) >= 2 else r.text
                    op_td = tds[-1] if len(tds) >= 1 else r
                    if st and st != last:
                        print('当前状态:', st)
                        last = st
                    # 同时要求出现可点击的“开机”按钮
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
                    stopped = is_stopped(r)
                    clickable = False
                    if btn is not None:
                        try:
                            WebDriverWait(driver, 2).until(EC.element_to_be_clickable(btn))
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
            time.sleep(interval)
        except Exception:
            time.sleep(interval)
    return None

def stop_by_row(driver, row):
    try:
        tds = row.find_elements(By.TAG_NAME, 'td')
        action_td = tds[-1] if tds else row
        btn = None
        for xp in [
            ".//button[.//span[contains(normalize-space(), '关机')]]",
            ".//a[contains(normalize-space(), '关机')]",
            ".//*[contains(@class,'el-button') and .//span[contains(normalize-space(),'关机')]]",
            ".//span[contains(@class,'el-button__text') and contains(normalize-space(),'关机')]",
        ]:
            try:
                btn = action_td.find_element(By.XPATH, xp)
                break
            except Exception:
                continue
        if btn is None:
            trigger = None
            for tx in [
                ".//*[contains(@class,'el-dropdown')]",
                ".//*[contains(@class,'el-icon-more')]",
                ".//*[contains(normalize-space(),'更多')]",
            ]:
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
        ActionChains(driver).move_to_element(btn).pause(0.1).perform()
        try:
            WebDriverWait(driver, 5).until(EC.element_to_be_clickable(btn))
            btn.click()
        except ElementClickInterceptedException:
            driver.execute_script('arguments[0].click();', btn)
        btn2 = None
        for xp in [
            "//div[contains(@class,'el-message-box')]//button[.//span[contains(normalize-space(),'确定')]]",
            "//div[contains(@class,'el-dialog__footer')]//button[.//span[contains(normalize-space(),'确定')]]",
            "//div[contains(@class,'el-popconfirm')]//button[.//span[contains(normalize-space(),'确定')]]",
            "//button[.//span[contains(normalize-space(),'确定')]]",
            "//*[contains(normalize-space(),'确定')]/ancestor::button",
        ]:
            try:
                btn2 = WebDriverWait(driver, 6).until(EC.presence_of_element_located((By.XPATH, xp)))
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
        return True
    except Exception:
        return False


def start_by_row(driver, row):
    try:
        tds = row.find_elements(By.TAG_NAME, 'td')
        action_td = tds[-1] if tds else row
        btn = None
        for xp in [
            ".//button[.//span[contains(normalize-space(), '开机并连接')]]",
            ".//a[contains(normalize-space(), '开机并连接')]",
            ".//button[.//span[contains(normalize-space(), '开机')]]",
            ".//a[contains(normalize-space(), '开机')]",
            ".//*[contains(@class,'el-button') and .//span[contains(normalize-space(),'开机')]]",
            ".//span[contains(@class,'el-button__text') and contains(normalize-space(),'开机')]",
        ]:
            try:
                btn = action_td.find_element(By.XPATH, xp)
                break
            except Exception:
                continue
        if btn is None:
            trigger = None
            for tx in [
                ".//*[contains(@class,'el-dropdown')]",
                ".//*[contains(@class,'el-icon-more')]",
                ".//*[contains(normalize-space(),'更多')]",
            ]:
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
                        "const target=items.find(n=>/开机/.test((n.textContent||'').trim()));\n"
                        "if(target){target.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));}",
                        menu_el)
                    btn = None
        if btn is None:
            return False
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
        ActionChains(driver).move_to_element(btn).pause(0.1).perform()
        try:
            WebDriverWait(driver, 5).until(EC.element_to_be_clickable(btn))
            btn.click()
        except ElementClickInterceptedException:
            driver.execute_script('arguments[0].click();', btn)
        btn2 = None
        for xp in [
            "//div[contains(@class,'el-message-box')]//button[.//span[contains(normalize-space(),'确定')]]",
            "//div[contains(@class,'el-dialog__footer')]//button[.//span[contains(normalize-space(),'确定')]]",
            "//div[contains(@class,'el-popconfirm')]//button[.//span[contains(normalize-space(),'确定')]]",
            "//button[.//span[contains(normalize-space(),'确定')]]",
            "//*[contains(normalize-space(),'确定')]/ancestor::button",
        ]:
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
        return True
    except Exception:
        return False


def start_nogpu_by_row(driver, row):
    try:
        tds = row.find_elements(By.TAG_NAME, 'td')
        action_td = tds[-1] if tds else row
        trigger = None
        for tx in [
            ".//button[.//span[contains(normalize-space(),'更多')]]",
            ".//a[.//span[contains(normalize-space(),'更多')]]",
            ".//*[contains(@class,'el-icon-more')]",
            ".//*[contains(@class,'el-dropdown')]",
            ".//*[contains(@class,'el-dropdown__caret-button')]",
            ".//*[contains(normalize-space(),'更多')]",
        ]:
            try:
                trigger = action_td.find_element(By.XPATH, tx)
                break
            except Exception:
                continue
        if not trigger:
            try:
                js_trigger = driver.execute_script(
                    "const row=arguments[0];\n"
                    "const rr=row.getBoundingClientRect();\n"
                    "const all=[...document.querySelectorAll('.el-icon-more, .el-dropdown, [class*=\"el-icon-more\"], [class*=\"dropdown\"], button, a, span')];\n"
                    "const inRow=all.filter(el=>{const r=el.getBoundingClientRect(); return r.top>=rr.top-2 && r.bottom<=rr.bottom+2;});\n"
                    "let cand=inRow.find(el=>{const t=(el.textContent||'').trim(); const c=(el.className||'')+''; return /更多/.test(t)||/(dropdown|icon-more)/i.test(c);});\n"
                    "return cand||inRow[0]||null;",
                    row)
                trigger = js_trigger if js_trigger else None
            except Exception:
                trigger = None
        if not trigger:
            return False
        print('找到更多触发器')
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", trigger)
        # 等待“更多”变为可点击（避免关机未完成导致禁用）
        try:
            WebDriverWait(driver, 8).until(EC.element_to_be_clickable(trigger))
        except Exception:
            pass
        try:
            ActionChains(driver).move_to_element(trigger).pause(0.02).perform()
        except Exception:
            try:
                ActionChains(driver).move_to_element(trigger).click().perform()
            except Exception:
                pass
        # 使用 JS 找到可点击根节点并点击
        try:
            driver.execute_script(
                """
                const t=arguments[0];
                const root=t.closest('button, .el-dropdown, [role=\"button\"]')||t;
                try{ root.click(); }
                catch(e){ root.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true})); }
                """,
                trigger
            )
        except Exception:
            driver.execute_script('arguments[0].click();', trigger)
        # 双步点击：再次悬停后直接定位首个可视菜单项并点击
        item = None
        try:
            ActionChains(driver).move_to_element(trigger).pause(0.02).perform()
            item = WebDriverWait(driver, 1).until(EC.presence_of_element_located((By.XPATH, "(//ul[contains(@class,'el-dropdown-menu')]//li | //div[contains(@class,'el-popper')]//li)[1]")))
        except Exception:
            item = None
        clicked = False
        if item and item.is_displayed():
            try:
                ActionChains(driver).move_to_element(item).pause(0.02).click(item).perform()
                clicked = True
            except Exception:
                try:
                    driver.execute_script('arguments[0].click();', item)
                    clicked = True
                except Exception:
                    clicked = False
        # 如果菜单尚未可见，快速重复尝试打开
        try:
            vis_count = driver.execute_script("return [...document.querySelectorAll('.el-dropdown-menu,.el-popper')].filter(m=>m.offsetParent!==null).length")
            if not vis_count:
                try:
                    ActionChains(driver).move_to_element(trigger).click().pause(0.02).click().pause(0.02).perform()
                except Exception:
                    driver.execute_script('arguments[0].click(); arguments[0].click();', trigger)
        except Exception:
            pass
        # 等待可视菜单节点
        menu_selector = "//ul[contains(@class,'el-dropdown-menu')]|//div[contains(@class,'el-popper') and .//li]"
        try:
            WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.XPATH, menu_selector)))
        except Exception:
            pass
        # 键盘兜底：快速选择首项并回车
        try:
            ActionChains(driver).pause(0.02).send_keys(Keys.ARROW_DOWN).pause(0.02).send_keys(Keys.ENTER).perform()
        except Exception:
            pass
        # 打印菜单文本用于调试
        try:
            items_text = driver.execute_script(
                "return [...document.querySelectorAll('.el-dropdown-menu,.el-popper')].filter(m=>m.offsetParent!==null).map(m=>[...m.querySelectorAll('*')].map(n=>((n.textContent||'').trim())).filter(t=>t));"
            )
            if items_text:
                try:
                    print('下拉菜单条目(部分):', items_text[0][:8])
                except Exception:
                    pass
        except Exception:
            pass
        # 查找“无卡模式开机”菜单项（可见项）
        item = None
        for xp in [
            "//ul[contains(@class,'el-dropdown-menu')]//li[.//span[contains(normalize-space(),'无卡模式开机')] or contains(normalize-space(),'无卡模式开机')]",
            "//div[contains(@class,'el-popper')]//li[.//span[contains(normalize-space(),'无卡模式开机')] or contains(normalize-space(),'无卡模式开机')]",
            "//*[contains(@class,'el-dropdown-menu') or contains(@class,'el-popper')]//li[contains(normalize-space(),'无卡模式开机')]",
        ]:
            try:
                cand = WebDriverWait(driver, 1).until(EC.presence_of_element_located((By.XPATH, xp)))
                if cand and cand.is_displayed():
                    item = cand
                    break
            except Exception:
                continue
        clicked = False
        # 如果找到了目标菜单项，但处于禁用，等待其启用
        if item:
            for _ in range(6):
                try:
                    cls = (item.get_attribute('class') or '')
                    aria = (item.get_attribute('aria-disabled') or '')
                    if ('is-disabled' in cls) or (str(aria).lower() == 'true'):
                        time.sleep(0.5)
                        continue
                    WebDriverWait(driver, 2).until(EC.element_to_be_clickable(item))
                    break
                except Exception:
                    time.sleep(0.3)
        # 优先极限快捷点击：打开菜单后立即点击第一项（按你的描述第一项就是无卡模式开机）
        if not item and trigger:
            try:
                fast_clicked = driver.execute_script(
                    "const t=arguments[0];\n"
                    "const tr=t.getBoundingClientRect();\n"
                    "const menus=[...document.querySelectorAll('.el-dropdown-menu,.el-popper')].filter(m=>m.offsetParent!==null);\n"
                    "if(menus.length===0){return false;}\n"
                    "let best=null;\n"
                    "for(const m of menus){const r=m.getBoundingClientRect(); const d=Math.hypot(r.left-tr.left, r.top-tr.bottom); if(!best||d<best.d){best={el:m,d:d};}}\n"
                    "const menu=best?best.el:null; if(!menu){return false;}\n"
                    "const items=[...menu.querySelectorAll('li')].filter(el=>el.offsetParent!==null); if(items.length===0){return false;}\n"
                    "const first=items[0]; const txt=(first.textContent||'').trim();\n"
                    "if(!/(无卡|无卡模式)/.test(txt)){ const t2=items.find(n=>/(无卡|无卡模式)/.test((n.textContent||'').trim())); if(t2){t2.click(); return true;}}\n"
                    "first.click(); return true;",
                    trigger
                )
                if fast_clicked:
                    clicked = True
            except Exception:
                pass
        # 坐标点选首项：在触发器下方 24px 处点击一次
        if not clicked:
            try:
                ActionChains(driver).move_to_element(trigger).pause(0.08).move_by_offset(8, 24).click().perform()
                clicked = True
            except Exception:
                try:
                    ActionChains(driver).move_to_element(trigger).move_by_offset(10, 30).click().perform()
                    clicked = True
                except Exception:
                    pass
        if item:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", item)
            try:
                ActionChains(driver).move_to_element(item).pause(0.02).click(item).perform()
                clicked = True
            except Exception:
                try:
                    driver.execute_script('arguments[0].click();', item)
                    clicked = True
                except Exception:
                    clicked = False
        if not clicked and trigger:
            # 快速 JS 悬停+点击：在菜单自动隐藏之前完成点击
            try:
                clicked = driver.execute_script(
                    "const t=arguments[0];\n"
                    "t.dispatchEvent(new MouseEvent('mouseenter',{bubbles:true,cancelable:true}));\n"
                    "t.dispatchEvent(new MouseEvent('mouseover',{bubbles:true,cancelable:true}));\n"
                    "try{t.click();}catch(e){}\n"
                    "const near=(root)=>{const tr=root.getBoundingClientRect();\n"
                    "  const ms=[...document.querySelectorAll('.el-dropdown-menu,.el-popper')].filter(m=>m.offsetParent!==null);\n"
                    "  if(ms.length===0){return null;}\n"
                    "  let best=null;\n"
                    "  for(const m of ms){const r=m.getBoundingClientRect(); const d=Math.hypot(r.left-tr.left,r.top-tr.bottom);\n"
                    "    if(!best||d<best.d){best={el:m,d:d};}} return best?best.el:null;};\n"
                    "const menu=near(t); if(!menu){return false;}\n"
                    "const items=[...menu.querySelectorAll('*')];\n"
                    "const li=items.find(n=>/(无卡模式开机)/.test((n.textContent||'').trim()));\n"
                    "if(!li){return false;}\n"
                    "li.dispatchEvent(new MouseEvent('mouseenter',{bubbles:true,cancelable:true}));\n"
                    "li.dispatchEvent(new MouseEvent('mouseover',{bubbles:true,cancelable:true}));\n"
                    "try{li.click(); return true;}catch(e){\n"
                    "  li.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true})); return true;}\n"
                , trigger)
            except Exception:
                clicked = False
        if not clicked:
            # JS 兜底：尝试通过文本匹配触发 click
            try:
                clicked = driver.execute_script(
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
            # 坐标兜底：在目标文本元素的中心点触发原生点击
            try:
                ok2 = driver.execute_script(
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
        if not clicked and trigger:
            # 直接在 trigger 下方扫描，找到含“无卡”文本的节点并点击
            try:
                ok3 = driver.execute_script(
                    "const t=arguments[0]; const r=t.getBoundingClientRect();\n"
                    "for(let dy=6; dy<=120; dy+=6){\n"
                    "  const el=document.elementFromPoint(r.left+12, r.bottom+dy);\n"
                    "  if(el){const txt=(el.textContent||'').trim(); if(/(无卡|无卡模式|no\s*gpu)/i.test(txt)){\n"
                    "    try{el.click();}catch(e){el.dispatchEvent(new MouseEvent('click',{bubbles:true,cancelable:true}));}\n"
                    "    return true;}}}\n"
                    "return false;",
                    trigger
                )
                clicked = bool(ok3)
            except Exception:
                clicked = False
        if not clicked:
            # 全页面兜底：直接找“无卡模式开机”文本节点并点击
            try:
                el = WebDriverWait(driver,1).until(EC.presence_of_element_located((By.XPATH, "//*[contains(normalize-space(),'无卡模式开机') or contains(normalize-space(),'无卡开机') or contains(normalize-space(),'无卡') ]")))
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                try:
                    ActionChains(driver).move_to_element(el).pause(0.02).click(el).perform()
                    clicked = True
                except Exception:
                    driver.execute_script('arguments[0].click();', el)
                    clicked = True
            except Exception:
                clicked = False
        print('点击无卡项结果:', clicked)
        # 等待成功toast（如果有）
        try:
            WebDriverWait(driver, 5).until(EC.presence_of_element_located((
                By.XPATH,
                "//div[contains(@class,'el-message') or contains(@class,'el-notification')]//*[contains(normalize-space(),'成功') or contains(normalize-space(),'已发送') or contains(normalize-space(),'操作成功')]"
            )))
        except Exception:
            pass
        if not clicked:
            return False
        print('已点击无卡模式开机菜单项')
        # 预处理弹窗中的必选项（如需勾选的复选框）
        try:
            box = WebDriverWait(driver, 3).until(EC.presence_of_element_located((
                By.XPATH,
                "//*[contains(@class,'el-message-box') or contains(@class,'el-dialog') or contains(@class,'el-popconfirm')]"
            )))
            try:
                driver.execute_script(
                    "const box=arguments[0]; const cbs=[...box.querySelectorAll('input[type=checkbox], .el-checkbox')];\n"
                    "for(const c of cbs){ try{ if(c.tagName==='INPUT'){ if(!c.checked){ c.click(); } } else { const inp=c.querySelector('input'); if(inp && !inp.checked){ inp.click(); } } }catch(e){} }",
                    box
                )
                driver.execute_script(
                    "const box=arguments[0]; const rads=[...box.querySelectorAll('.el-radio')];\n"
                    "for(const r of rads){ const inp=r.querySelector('input[type=radio]');\n"
                    "  try{ if(inp && !inp.checked){ r.click(); break; } }catch(e){} }",
                    box
                )
                driver.execute_script(
                    "const box=arguments[0]; const sws=[...box.querySelectorAll('.el-switch')];\n"
                    "for(const s of sws){ try{ if(!(s.className||'').includes('is-checked')){ s.click(); } }catch(e){} }",
                    box
                )
            except Exception:
                pass
        except Exception:
            pass
        btn2 = None
        for xp in [
            "//div[contains(@class,'el-message-box')]//button[.//span[contains(normalize-space(),'确定')]]",
            "//div[contains(@class,'el-dialog__footer')]//button[.//span[contains(normalize-space(),'确定')]]",
            "//div[contains(@class,'el-popconfirm')]//button[.//span[contains(normalize-space(),'确定')]]",
            "//button[.//span[contains(normalize-space(),'确定')]]",
            "//*[contains(normalize-space(),'确定')]/ancestor::button",
        ]:
            try:
                btn2 = WebDriverWait(driver, 6).until(EC.presence_of_element_located((By.XPATH, xp)))
                break
            except TimeoutException:
                continue
        if not btn2:
            return False
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn2)
            ActionChains(driver).move_to_element(btn2).pause(0.05).perform()
            WebDriverWait(driver, 5).until(EC.element_to_be_clickable(btn2))
            btn2.click()
        except ElementClickInterceptedException:
            driver.execute_script('arguments[0].click();', btn2)
        except Exception:
            driver.execute_script('arguments[0].click();', btn2)
        print('已点击确认按钮')
        return True
    except Exception:
        return False


def wait_for_running(driver, device_id, remark='', timeout=240, interval=4):
    start_t = time.time()
    last = ''
    while time.time() - start_t < timeout:
        try:
            goto_list(driver)
            r = find_row_by_any(driver, device_id, remark)
            if r and is_running(r):
                return r
            # 检查过渡状态，继续等待
            try:
                tds = r.find_elements(By.TAG_NAME, 'td') if r else []
                st = tds[1].text if len(tds) >= 2 else (r.text if r else '')
                if st and st != last:
                    print('当前状态:', st)
                    last = st
                if any(k in st for k in ['开机中','正在开机','启动中','正在启动','pending','starting','booting']):
                    time.sleep(interval)
                    continue
            except Exception:
                pass
            time.sleep(interval)
        except Exception:
            time.sleep(interval)
    return None


def load_credentials():
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        cred_path = os.path.join(base_dir, 'autodl_configs', 'credentials.json')
        if os.path.exists(cred_path):
            with open(cred_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            u = str(data.get('username', '')).strip()
            p = str(data.get('password', '')).strip()
            if u and p:
                return u, p
    except Exception:
        pass
    u = os.environ.get('AUTODL_USERNAME', '')
    p = os.environ.get('AUTODL_PASSWORD', '')
    return u, p


def main():
    parser = argparse.ArgumentParser(description='测试设备操作：开机/无卡开机/JupyterLab')
    parser.add_argument('--device-id', '-d', help='设备ID（如 2c4c...）')
    parser.add_argument('--remark', '-r', help='设备备注（例如 comfyui-3）')
    parser.add_argument('--headless', action='store_true', default=False, help='无头浏览器')
    parser.add_argument('--no-open', action='store_true', help='不在本地打开浏览器')
    parser.add_argument('--nogpu-start', action='store_true', help='使用无卡模式开机（更多菜单）')
    parser.add_argument('--wait-running', action='store_true', help='无卡开机后等待状态切换为运行中')
    parser.add_argument('--wait-time-secs', type=int, default=300, help='等待切换为运行中的最长秒数')
    args = parser.parse_args()
    username, password = load_credentials()
    if not username or not password:
        print('缺少用户名或密码：使用 --username/--password 或设置环境变量 AUTODL_USERNAME/AUTODL_PASSWORD')
        return 1

    driver = init_driver(headless=args.headless)
    try:
        login(driver, username, password)
        goto_list(driver)
        row = None
        if args.device_id:
            row = find_row_by_id(driver, args.device_id)
        if not row and args.remark:
            row = find_row_by_remark(driver, args.remark)
        if not row:
            try:
                rows = driver.find_elements(By.CSS_SELECTOR, '.el-table__body tr')
                if not rows:
                    rows = driver.find_elements(By.XPATH, "//*[contains(@class,'el-table__row')]")
                if not rows:
                    table = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'table')))
                    rows = [r for r in table.find_elements(By.TAG_NAME, 'tr') if r.find_elements(By.TAG_NAME, 'td')]
                print('候选行数:', len(rows))
                cand = None
                for r in rows:
                    tx = r.text
                    # 简要输出前两个候选行文本调试
                    try:
                        if not cand:
                            print('候选行片段:', tx[:80])
                    except Exception:
                        pass
                    if ('已关机' in tx) or ('stopped' in tx.lower()) or ('开机' in tx):
                        cand = r; break
                if not cand and rows:
                    cand = rows[0]
                if cand:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", cand)
                row = cand
            except Exception:
                row = None
        if not row:
            print('未找到设备行，且无法自动选择，请提供 --device-id 或 --remark')
            return 2
        if args.nogpu_start:
            # 保证关机态
            if not is_stopped(row):
                ok_stop = stop_by_row(driver, row)
                if ok_stop:
                    # 等待已关机
                    s_t = time.time()
                    while time.time() - s_t < 90:
                        try:
                            goto_list(driver)
                            r2 = find_row_by_any(driver, args.device_id or '', args.remark or '')
                            if r2 and is_stopped(r2):
                                row = r2
                                break
                        except Exception:
                            pass
                        time.sleep(3)
                else:
                    print('预关机失败，继续尝试无卡开机')
            # 多次快速尝试点击无卡开机
            ok = False
            tries = 0
            while tries < 3 and not ok:
                ok = start_nogpu_by_row(driver, row)
                tries += 1
                if ok:
                    break
                time.sleep(0.8)
            if not ok:
                print('无卡开机点击失败')
                return 3
            if args.wait_running:
                row2 = wait_for_running_nogpu(driver, args.device_id or '', args.remark or '', timeout=args.wait_time_secs)
                if not row2:
                    print('无卡开机后状态未切换为运行中且未显示无卡模式')
                    return 4
                print('无卡开机成功')
            else:
                print('无卡模式开机点击成功（未等待状态切换）')
        else:
            if not is_running(row):
                ok = start_by_row(driver, row)
                if not ok:
                    print('开机点击失败')
                    return 3
                row = wait_for_running(driver, args.device_id)
                if not row:
                    print('开机状态未切换为运行中')
                    return 4
            url = click_jupyterlab_in_row(driver, row, open_local=(not args.no_open))
            print('JupyterLab URL:', url or '<未获取>')
        return 0
    except Exception as e:
        print('测试失败:', e)
        return 3
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == '__main__':
    raise SystemExit(main())
