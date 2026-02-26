"""测试：能不能找到并点击设备列表页面的刷新按钮"""
import time
import json
import os
import sys
import base64
import ctypes
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager

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

script_dir = os.path.dirname(os.path.abspath(__file__))
cfg = os.path.join(script_dir, 'configs', 'autodl_credentials.json')
with open(cfg, 'r', encoding='utf-8') as f:
    data = json.load(f)
user = data.get('username')
pwd = data.get('password')
try:
    dec = _win_dpapi_decrypt(pwd)
    if dec: pwd = dec
except: pass

opts = Options()
opts.page_load_strategy = 'eager'
opts.add_argument("--disable-blink-features=AutomationControlled")
opts.add_experimental_option("excludeSwitches", ["enable-automation"])
opts.add_argument("--window-size=1600,900")
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

try:
    # 登录
    driver.get("https://www.autodl.com/login")
    time.sleep(2)
    if "login" in driver.current_url:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.XPATH, "//input[@type='password']")))
        u_input = driver.find_elements(By.XPATH, "//input[@type='text'] | //input[@type='tel']")
        if u_input:
            u_input[-1].clear(); u_input[-1].send_keys(user)
        p_input = driver.find_element(By.XPATH, "//input[@type='password']")
        p_input.clear(); p_input.send_keys(pwd)
        for xp in ["//button[contains(normalize-space(),'登录')]", "//*[contains(@class,'el-button--primary')]"]:
            try:
                btn = driver.find_element(By.XPATH, xp)
                driver.execute_script("arguments[0].click();", btn); break
            except: continue
        WebDriverWait(driver, 15).until(lambda d: 'login' not in d.current_url)
    print("✓ 已登录")

    # 导航到设备列表
    driver.get("https://www.autodl.com/console/instance/list")
    WebDriverWait(driver, 10).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, ".el-table__body tr")) > 0
    )
    time.sleep(1)
    print("✓ 设备列表已加载")

    # 探测刷新按钮
    print("\n=== 探测刷新按钮 ===")

    # 方法1: 找 "批量续费" 旁边的图标按钮
    candidates = []

    # 看看 "批量续费" 附近的元素
    try:
        batch_btn = driver.find_element(By.XPATH, "//*[contains(normalize-space(),'批量续费')]")
        parent = batch_btn.find_element(By.XPATH, "./..")
        siblings = parent.find_elements(By.XPATH, "./*")
        print(f"'批量续费' 的父元素有 {len(siblings)} 个子元素:")
        for i, sib in enumerate(siblings):
            tag = sib.tag_name
            cls = sib.get_attribute('class') or ''
            txt = sib.text.strip()[:30]
            print(f"  [{i}] <{tag}> class='{cls}' text='{txt}'")
    except Exception as e:
        print(f"找 '批量续费' 失败: {e}")

    # 方法2: 找所有 icon 类的按钮/元素
    print("\n--- 搜索刷新图标 ---")
    for selector in [
        "i[class*='refresh']",
        "i[class*='reload']",
        "i[class*='sync']",
        "*[class*='el-icon-refresh']",
        "button[class*='refresh']",
        ".el-icon-refresh-right",
        ".el-icon-refresh",
    ]:
        els = driver.find_elements(By.CSS_SELECTOR, selector)
        if els:
            print(f"  ✓ '{selector}' 找到 {len(els)} 个")
            for el in els:
                tag = el.tag_name
                cls = el.get_attribute('class') or ''
                parent_tag = el.find_element(By.XPATH, "./..").tag_name
                parent_cls = el.find_element(By.XPATH, "./..").get_attribute('class') or ''
                print(f"    <{tag}> class='{cls}' parent=<{parent_tag}> class='{parent_cls}'")

    # 方法3: 用JS dump "批量续费" 附近的HTML
    print("\n--- '批量续费' 附近的HTML ---")
    html = driver.execute_script("""
        const el = [...document.querySelectorAll('*')].find(e => e.textContent.trim() === '批量续费');
        if (!el) return 'NOT FOUND';
        // 往上找到包含刷新按钮的容器
        let p = el.parentElement;
        for (let i = 0; i < 3 && p; i++) { p = p.parentElement; }
        return p ? p.outerHTML.substring(0, 2000) : el.parentElement.outerHTML.substring(0, 1000);
    """)
    print(html[:2000])

    # 方法4: 找那个 C 形刷新图标（可能是 SVG 或 icon font）
    print("\n--- 搜索所有小图标按钮 ---")
    icon_btns = driver.execute_script("""
        const results = [];
        // 找所有 i 标签或 svg 标签在 button 内的
        document.querySelectorAll('button i, button svg, button .el-icon, i.el-icon-refresh, i.el-icon-refresh-right').forEach(el => {
            const btn = el.closest('button') || el.parentElement;
            const rect = btn.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) {
                results.push({
                    tag: el.tagName,
                    class: el.className,
                    parentTag: btn.tagName,
                    parentClass: btn.className,
                    text: btn.textContent.trim().substring(0, 30),
                    x: Math.round(rect.x),
                    y: Math.round(rect.y),
                    w: Math.round(rect.width),
                    h: Math.round(rect.height),
                });
            }
        });
        return results;
    """)
    for item in icon_btns:
        print(f"  <{item['tag']}> class='{item['class']}' in <{item['parentTag']}> class='{item['parentClass']}' text='{item['text']}' pos=({item['x']},{item['y']}) size={item['w']}x{item['h']}")

    print("\n--- 尝试点击刷新 ---")
    # 尝试各种方式点击
    clicked = False
    for xp in [
        "//i[contains(@class,'el-icon-refresh')]",
        "//button[contains(@class,'el-icon-refresh')]",
        "//*[contains(@class,'refresh')]",
        "//i[contains(@class,'reload')]",
    ]:
        try:
            el = driver.find_element(By.XPATH, xp)
            print(f"  找到: {xp}")
            btn = el if el.tag_name == 'button' else el.find_element(By.XPATH, "ancestor::button")
            print(f"  按钮: <{btn.tag_name}> class='{btn.get_attribute('class')}'")
            ActionChains(driver).move_to_element(btn).pause(0.2).click().perform()
            print(f"  ✓ 已点击")
            clicked = True
            break
        except Exception as e:
            print(f"  ✗ {xp}: {e}")

    if not clicked:
        # 最后尝试：找 "批量续费" 同级的按钮
        try:
            result = driver.execute_script("""
                const tabs = document.querySelectorAll('.el-tabs__header, [role="tablist"]');
                for (const tab of tabs) {
                    const html = tab.parentElement.outerHTML.substring(0, 3000);
                    return html;
                }
                return 'NO TABS FOUND';
            """)
            print(f"\n--- Tabs区域HTML ---\n{result[:2000]}")
        except: pass

    time.sleep(3)
    print("\n完成，5秒后关闭")
    time.sleep(5)

finally:
    driver.quit()
