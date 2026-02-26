"""
探测脚本：抓取 AutoDL 设备列表页面中每一行的完整文本和 HTML 结构，
找出"释放"/"销毁"/"到期"相关的信息在哪里。
"""
import time
import json
import os
import re
import logging
import base64
import ctypes
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger(__name__)

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

def run():
    user, pwd = get_credentials()
    driver = setup_driver()
    try:
        # 登录
        driver.get("https://www.autodl.com/login")
        time.sleep(2)
        if "login" in driver.current_url:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//input[@type='password']")))
            u_inputs = driver.find_elements(By.XPATH, "//input[@type='text'] | //input[@type='tel']")
            if u_inputs:
                u_inputs[-1].clear()
                u_inputs[-1].send_keys(user)
            p_input = driver.find_element(By.XPATH, "//input[@type='password']")
            p_input.clear()
            p_input.send_keys(pwd)
            btn = driver.find_element(By.XPATH, "//*[contains(@class,'el-button--primary')]")
            driver.execute_script("arguments[0].click();", btn)
            WebDriverWait(driver, 15).until(lambda d: 'login' not in d.current_url)
        log.info("登录成功")

        # 进入设备列表
        driver.get("https://www.autodl.com/console/instance/list")
        WebDriverWait(driver, 10).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, ".el-table__body tr")) > 0
        )
        time.sleep(1)

        # 抓取每一行的详细信息
        rows = driver.find_elements(By.CSS_SELECTOR, ".el-table__body tr")
        log.info(f"共 {len(rows)} 行")

        for i, row in enumerate(rows):
            log.info(f"\n{'='*60}")
            log.info(f"行 {i}:")
            
            # 完整文本
            text = row.text
            log.info(f"完整文本:\n{text}")
            
            # 逐列文本
            cells = row.find_elements(By.TAG_NAME, 'td')
            for j, cell in enumerate(cells):
                cell_text = cell.text.strip()
                log.info(f"  列{j}: {repr(cell_text)}")
            
            # 搜索释放/销毁/到期相关
            full_html = row.get_attribute('innerHTML')
            keywords = ['释放', '销毁', '到期', '过期', '天后', '小时后', 'release', 'expire', 'destroy', 'recycle']
            for kw in keywords:
                if kw in text or kw in full_html:
                    log.info(f"  ★ 发现关键词 '{kw}'")
            
            # 检查是否有 tooltip 或 title 属性
            elements_with_title = row.find_elements(By.XPATH, ".//*[@title]")
            for el in elements_with_title:
                title = el.get_attribute('title')
                if title:
                    log.info(f"  title属性: {repr(title)}")
            
            # 检查 hover 提示（el-tooltip）
            elements_with_tooltip = row.find_elements(By.XPATH, ".//*[contains(@class,'el-tooltip')]")
            for el in elements_with_tooltip:
                log.info(f"  el-tooltip元素: text={repr(el.text)}, aria-describedby={el.get_attribute('aria-describedby')}")

        # 额外：检查页面上所有包含"释放"/"销毁"的元素
        log.info(f"\n{'='*60}")
        log.info("全局搜索释放/销毁相关元素:")
        for kw in ['释放', '销毁', '到期', '回收']:
            els = driver.find_elements(By.XPATH, f"//*[contains(text(), '{kw}')]")
            for el in els:
                log.info(f"  [{kw}] tag={el.tag_name}, text={repr(el.text[:100])}, class={el.get_attribute('class')}")

        # 检查是否需要hover才能看到释放信息
        log.info(f"\n{'='*60}")
        log.info("尝试 hover 第一行查看是否有弹出信息:")
        if rows:
            from selenium.webdriver.common.action_chains import ActionChains
            first_row = rows[0]
            cells = first_row.find_elements(By.TAG_NAME, 'td')
            for j, cell in enumerate(cells):
                ActionChains(driver).move_to_element(cell).perform()
                time.sleep(0.5)
                # 检查是否出现了 popper/tooltip
                poppers = driver.find_elements(By.CSS_SELECTOR, ".el-popper, .el-tooltip__popper, [role='tooltip']")
                visible_poppers = [p for p in poppers if p.is_displayed()]
                if visible_poppers:
                    for p in visible_poppers:
                        log.info(f"  hover列{j}后出现tooltip: {repr(p.text[:200])}")

            # 也试试hover "查看详情" 链接
            detail_links = first_row.find_elements(By.XPATH, ".//*[contains(text(),'查看详情')]")
            for dl in detail_links:
                ActionChains(driver).move_to_element(dl).perform()
                time.sleep(1)
                poppers = driver.find_elements(By.CSS_SELECTOR, ".el-popper, .el-tooltip__popper, [role='tooltip']")
                visible_poppers = [p for p in poppers if p.is_displayed()]
                if visible_poppers:
                    for p in visible_poppers:
                        log.info(f"  hover查看详情后tooltip: {repr(p.text[:300])}")

        log.info("\n探测完成，10秒后关闭")
        time.sleep(10)
    finally:
        driver.quit()

if __name__ == '__main__':
    run()
