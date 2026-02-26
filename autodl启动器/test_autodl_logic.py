import sys
import time
import json
import os
import re
import ctypes
import base64
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- DPAPI ---
def _win_dpapi_decrypt(ciphertext):
    try:
        if not isinstance(ciphertext, str): return None
        if not ciphertext.startswith("enc:"): return None
        raw = base64.b64decode(ciphertext[4:])
        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", ctypes.c_uint), ("pbData", ctypes.c_void_p)]
        CryptUnprotectData = ctypes.windll.crypt32.CryptUnprotectData
        CryptUnprotectData.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.POINTER(ctypes.c_wchar_p), ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.POINTER(DATA_BLOB)]
        CryptUnprotectData.restype = ctypes.c_bool
        in_blob = DATA_BLOB(len(raw), ctypes.cast(ctypes.create_string_buffer(raw), ctypes.c_void_p))
        out_blob = DATA_BLOB()
        if not CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
            return None
        buf = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)
        return buf.decode('utf-8')
    except Exception:
        return None

# --- Config ---
CONFIG_FILE = os.path.join('configs', 'autodl_credentials.json')

def get_credentials():
    if not os.path.exists(CONFIG_FILE):
        logger.error(f"Config file not found: {CONFIG_FILE}")
        return None, None
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
        user = data.get('username')
        pwd = data.get('password')
        try:
            dec = _win_dpapi_decrypt(pwd)
            if dec: pwd = dec
        except: pass
        return user, pwd

# --- Driver ---
def setup_driver():
    opts = Options()
    opts.page_load_strategy = 'eager'
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1366,900")
    # opts.add_argument("--headless=new") # Comment out for visible debugging
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    return driver

# --- Logic Helpers ---
def safe_click(driver, element):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        time.sleep(0.2)
        try:
            ActionChains(driver).move_to_element(element).pause(0.2).perform()
        except: pass
        try:
            WebDriverWait(driver, 1).until(EC.element_to_be_clickable(element))
            element.click()
            return
        except: pass
        driver.execute_script("arguments[0].click();", element)
    except Exception as e:
        logger.error(f"Safe click failed: {e}")
        raise

def parse_rows(driver):
    rows = driver.find_elements(By.CSS_SELECTOR, ".el-table__body tr")
    data = []
    for row in rows:
        try:
            full_text = row.text
            lines = [ln.strip() for ln in full_text.split('\n') if ln.strip()]
            
            dev_id = ""
            status = "未知"
            remark = "未知"
            instance_name = "未知"
            
            # 1. ID
            id_line_idx = -1
            for i, line in enumerate(lines):
                if re.search(r'[a-fA-F0-9\-]{8,}', line):
                    dev_id = line
                    id_line_idx = i
                    break
            
            # 2. Status
            status_keywords = ["运行中", "Running", "已关机", "Shutdown", "开机中", "Starting", "关机中", "Stopping", "Creating"]
            status_lines = [l for l in lines if any(k in l for k in status_keywords)]
            if status_lines:
                status = status_lines[0] # Simplified for test
            
            if "无卡" in full_text:
                if "无卡" not in status: status += " (无卡)"

            # 3. Name/Remark
            remaining = []
            for i, line in enumerate(lines):
                if i == id_line_idx: continue
                if line == status: continue
                if any(k in line for k in status_keywords): continue
                if "CPU" in line and len(line) > 20: continue
                remaining.append(line)
            
            if len(remaining) > 0: instance_name = remaining[0]
            if len(remaining) > 1: remark = remaining[-1]
            
            data.append({'id': dev_id, 'name': instance_name, 'status': status, 'remark': remark})
        except: pass
    return data

# --- Main Test Flow ---
def run_test():
    user, pwd = get_credentials()
    if not user or not pwd:
        logger.error("No credentials")
        return

    driver = setup_driver()
    try:
        # 1. Login
        logger.info("Step 1: Login")
        driver.get("https://www.autodl.com/login")
        time.sleep(2)
        if "login" in driver.current_url:
            try:
                # Fill User
                u_input = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='tel'], input[placeholder*='手机']")))
                u_input.clear()
                u_input.send_keys(user)
                
                # Fill Pwd
                p_input = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
                p_input.clear()
                p_input.send_keys(pwd)
                
                # Click Login
                btn = driver.find_element(By.CSS_SELECTOR, "button.el-button--primary")
                safe_click(driver, btn)
            except Exception as e:
                logger.error(f"Login failed: {e}")
                return
        
        # Wait for dashboard
        WebDriverWait(driver, 15).until(EC.url_contains("console"))
        logger.info("Login Successful")

        # 2. List
        logger.info("Step 2: List Devices")
        driver.get("https://www.autodl.com/console/instance/list")
        time.sleep(2)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".el-table__body tr")))
        
        devices = parse_rows(driver)
        for d in devices:
            logger.info(f"Found: {d}")
        
        if not devices:
            logger.error("No devices found!")
            return

        # 3. Pick Target
        target = None
        # Prefer Shutdown for Boot Test
        for d in devices:
            if "关机" in d['status'] or "Shutdown" in d['status']:
                target = d
                break
        
        if not target:
            logger.warning("No shutdown devices found. Will try to find a running one to test Connect info.")
            for d in devices:
                if "运行" in d['status']:
                    target = d
                    break
            if target:
                logger.info(f"Testing Connect Info for {target['id']}")
                # Extract SSH info logic test...
                return
            else:
                logger.error("No suitable device found.")
                return

        logger.info(f"Target for Boot Test: {target['id']} ({target['name']})")
        
        # 4. Boot Flow (No GPU)
        logger.info("Step 4: Start No-GPU Boot")
        
        # Re-find row
        xpath = f"//*[contains(text(), '{target['id']}')]/ancestor::tr"
        row = driver.find_element(By.XPATH, xpath)
        
        # Find More
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", row)
        time.sleep(1)
        
        # Try finding "More"
        triggers = [".//*[contains(@class,'el-dropdown')]", ".//*[contains(@class,'el-icon-more')]", ".//*[contains(.,'更多')]"]
        trigger = None
        tds = row.find_elements(By.TAG_NAME, 'td')
        action_td = tds[-1] if tds else row
        for tx in triggers:
            try:
                trigger = action_td.find_element(By.XPATH, tx)
                break
            except: continue
            
        if not trigger:
            logger.error("Could not find 'More' button")
            return
            
        # Click More
        ActionChains(driver).move_to_element(trigger).click().perform()
        time.sleep(1)
        
        # Find Menu
        menu_el = driver.execute_script(
            "const t=arguments[0];const tr=t.getBoundingClientRect();"
            "const menus=[...document.querySelectorAll('.el-dropdown-menu')].filter(m=>m.offsetParent!==null);"
            "if(menus.length===0){return null;}"
            "let best=null;"
            "for(const m of menus){const r=m.getBoundingClientRect();const d=Math.hypot((r.left-tr.left),(r.top-tr.bottom));"
            " if(!best||d<best.d){best={el:m,d:d};}}"
            "return best?best.el:null;",
            trigger)
            
        if not menu_el:
            logger.error("Menu not found in body")
            return
        
        logger.info("Menu found!")
        
        # Find Item
        clicked = False
        try:
            item = menu_el.find_element(By.XPATH, ".//li[contains(., '无卡模式开机')]")
            safe_click(driver, item)
            clicked = True
        except:
            # JS click
            clicked = driver.execute_script(
                "const menu=arguments[0];"
                "const items=[...menu.querySelectorAll('*')];"
                "const target=items.find(n=>/无卡模式开机/.test((n.textContent||'').trim()));"
                "if(target){target.click(); return true;} return false;",
                menu_el)
        
        if not clicked:
            logger.error("Item '无卡模式开机' not found/clicked")
            return
            
        logger.info("Clicked No-GPU Boot")
        
        # Handle Dialog (Logic ported exactly from main.py _start_nogpu_by_row)
        try:
            # Wait for any success message first (in case it started immediately without dialog)
            try:
                WebDriverWait(driver, 2).until(EC.presence_of_element_located((
                    By.XPATH,
                    "//div[contains(@class,'el-message') or contains(@class,'el-notification')]//*[contains(normalize-space(),'成功') or contains(normalize-space(),'已发送') or contains(normalize-space(),'操作成功')]"
                )))
                logger.info("Success message detected immediately!")
                return
            except: pass

            # Find Confirm Button Candidates
            cands = [
                "//div[contains(@class,'el-message-box')]//button[.//span[contains(normalize-space(),'确定')]]",
                "//div[contains(@class,'el-dialog__footer')]//button[.//span[contains(normalize-space(),'确定')]]",
                "//div[contains(@class,'el-popconfirm')]//button[.//span[contains(normalize-space(),'确定')]]",
                "//button[.//span[contains(normalize-space(),'确定')]]",
                "//*[contains(normalize-space(),'确定')]/ancestor::button",
                "//button[.//span[contains(normalize-space(),'确认')]]",
                "//*[contains(normalize-space(),'确认')]/ancestor::button",
                "//button[.//span[contains(normalize-space(),'开机')]]",
            ]
            
            btn2 = None
            for xp in cands:
                try:
                    btn2 = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.XPATH, xp)))
                    break
                except: continue
            
            if not btn2:
                logger.warning("Confirm button not found!")
                # Check if already running
                if "运行" in row.text:
                    logger.info("Device already running!")
                    return
                raise Exception("Confirm button missing")

            # Handle Checkboxes in the dialog box containing the button
            try:
                box = btn2.find_element(By.XPATH, "ancestor::div[contains(@class,'el-message-box') or contains(@class,'el-dialog') or contains(@class,'el-popconfirm')]")
                if box:
                    driver.execute_script(
                        "const box=arguments[0]; const cbs=[...box.querySelectorAll('input[type=checkbox], .el-checkbox')];"
                        "for(const c of cbs){ try{ if(c.tagName==='INPUT'){ if(!c.checked){ c.click(); } } else { const inp=c.querySelector('input'); if(inp && !inp.checked){ inp.click(); } } }catch(e){} }",
                        box
                    )
                    # Also handle radios/switches just in case
                    driver.execute_script(
                         "const box=arguments[0]; const rads=[...box.querySelectorAll('.el-radio')];"
                         "for(const r of rads){ const inp=r.querySelector('input[type=radio]');"
                         "  try{ if(inp && !inp.checked){ r.click(); break; } }catch(e){} }",
                         box
                    )
            except: pass

            # Click Confirm
            logger.info(f"Clicking Confirm Button: {btn2.text}")
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn2)
            time.sleep(0.5)
            
            try:
                ActionChains(driver).move_to_element(btn2).pause(0.2).perform()
                WebDriverWait(driver, 2).until(EC.element_to_be_clickable(btn2))
                btn2.click()
                logger.info("Clicked via standard click")
            except:
                driver.execute_script("arguments[0].click();", btn2)
                logger.info("Clicked via JS click")
            
            # Wait for Toast
            try:
                toast = WebDriverWait(driver, 5).until(EC.presence_of_element_located((
                    By.XPATH,
                    "//div[contains(@class,'el-message') or contains(@class,'el-notification')]//*[contains(normalize-space(),'成功') or contains(normalize-space(),'已发送') or contains(normalize-space(),'操作成功') or contains(normalize-space(),'开机中') or contains(normalize-space(),'启动中')]"
                )))
                logger.info(f"Toast detected: {toast.text}")
            except:
                logger.warning("No success toast detected")

        except Exception as e:
            logger.info(f"Dialog handling error: {e}")

        # Wait Loop
        logger.info("Step 5: Wait for Running")
        start_time = time.time()
        running = False
        while time.time() - start_time < 120:
            try:
                driver.refresh()
                time.sleep(3)
                row = driver.find_element(By.XPATH, f"//*[contains(text(), '{target['id']}')]/ancestor::tr")
                txt = row.text
                logger.info(f"Status: {txt.splitlines()}")
                if "运行" in txt or "Running" in txt:
                    running = True
                    break
            except: pass
            time.sleep(2)
            
        if running:
            logger.info("Device is RUNNING!")
            # RESTORE: Shutdown
            logger.info("Step 6: Restore (Shutdown)")
            
            # Find Shutdown btn (usually visible when running)
            # Or "More" -> Shutdown if needed
            try:
                # Re-find row
                row = driver.find_element(By.XPATH, f"//*[contains(text(), '{target['id']}')]/ancestor::tr")
                try:
                    btn = row.find_element(By.XPATH, ".//button[contains(., '关机')]")
                    safe_click(driver, btn)
                except:
                    # Try More -> Shutdown logic
                    # (Simulate finding trigger again...)
                    pass
                
                # Confirm shutdown
                time.sleep(1)
                try:
                    confirm = driver.find_element(By.CSS_SELECTOR, ".el-message-box__btns .el-button--primary")
                    safe_click(driver, confirm)
                    logger.info("Shutdown confirmed")
                except: pass
                
            except Exception as e:
                logger.error(f"Shutdown failed: {e}")
        else:
            logger.error("Device failed to start within timeout")

    except Exception as e:
        logger.error(f"Test failed: {e}")
    finally:
        logger.info("Test finished. Closing driver in 5s...")
        time.sleep(5)
        driver.quit()

if __name__ == "__main__":
    run_test()
