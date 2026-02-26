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
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import ctypes
import base64

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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

CONFIG_FILE = os.path.join('configs', 'autodl_credentials.json')
def get_credentials():
    if not os.path.exists(CONFIG_FILE): return None, None
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
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
    opts.add_argument("--window-size=1600,900") # Wider window to show buttons
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    return driver

def run_test():
    user, pwd = get_credentials()
    driver = setup_driver()
    
    try:
        # Login
        logger.info("Logging in...")
        driver.get("https://www.autodl.com/login")
        time.sleep(2)
        if "login" in driver.current_url:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "input")))
            driver.find_element(By.CSS_SELECTOR, "input[type='tel'], input[placeholder*='手机']").send_keys(user)
            driver.find_element(By.CSS_SELECTOR, "input[type='password']").send_keys(pwd)
            driver.find_element(By.CSS_SELECTOR, "button.el-button--primary").click()
            WebDriverWait(driver, 15).until(EC.url_contains("console"))
        
        logger.info("Login success. Going to list...")
        driver.get("https://www.autodl.com/console/instance/list")
        
        # Wait specifically for table rows
        try:
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".el-table__body tr")))
            logger.info("Table rows detected.")
        except:
            logger.warning("Timeout waiting for rows. Trying refresh...")
            driver.refresh()
            time.sleep(5)
        
        # Parse Rows
        rows = driver.find_elements(By.CSS_SELECTOR, ".el-table__body tr")
        if not rows:
             # Try finding any tr
             rows = driver.find_elements(By.TAG_NAME, "tr")
             logger.info(f"Fallback found {len(rows)} TR elements")

        logger.info(f"Found {len(rows)} rows.")
        
        target_device = None
        
        for i, row in enumerate(rows):
            # Skip header row if picked up by generic tr
            if "th" in row.get_attribute("innerHTML"): continue
            
            logger.info(f"--- Row {i} ---")
            tds = row.find_elements(By.TAG_NAME, "td")
            if not tds: 
                logger.info("No TDs in this row")
                continue
            
            # Column 1 Analysis
            col1_text = tds[0].text
            lines = [l.strip() for l in col1_text.split('\n') if l.strip()]
            logger.info(f"Col 1 Lines: {lines}")
            
            name = lines[0] if len(lines) > 0 else ""
            dev_id = lines[1] if len(lines) > 1 else ""
            remark = lines[2] if len(lines) > 2 else ""
            
            logger.info(f"Parsed -> Name: {name}, ID: {dev_id}, Remark: {remark}")
            
            # Check Links (Jupyter/AutoPanel)
            # Dump all links in row to see what's available
            links = row.find_elements(By.TAG_NAME, "a")
            for lnk in links:
                logger.info(f"Link found: '{lnk.text}' -> {lnk.get_attribute('href')}")

            # Check Buttons
            btns = row.find_elements(By.TAG_NAME, "button")
            for btn in btns:
                logger.info(f"Button found: '{btn.text}'")

            # Try to find row by ID (Validation)
            if dev_id:
                try:
                    # Robust ID search
                    xpath_id = f"//*[contains(text(), '{dev_id}')]/ancestor::tr"
                    found_row = driver.find_element(By.XPATH, xpath_id)
                    logger.info(f"Row lookup by ID '{dev_id}': SUCCESS")
                    target_device = {'id': dev_id, 'name': name}
                except Exception as e:
                    logger.error(f"Row lookup by ID '{dev_id}' FAILED: {e}")


        if target_device:
            logger.info(f"Testing Action on {target_device['name']} ({target_device['id']})...")
            
            # Re-find row strictly by ID
            row = driver.find_element(By.XPATH, f"//*[contains(text(), '{target_device['id']}')]/ancestor::tr")
            
            # Test Stop Button Finding
            try:
                stop_btn = row.find_element(By.XPATH, ".//button[contains(., '关机')]")
                logger.info("Stop button found directly.")
            except:
                logger.info("Stop button not found directly. Checking 'More' menu...")
                # Find More
                try:
                    triggers = [".//*[contains(@class,'el-dropdown')]", ".//*[contains(@class,'el-icon-more')]", ".//*[contains(.,'更多')]"]
                    trigger = None
                    tds = row.find_elements(By.TAG_NAME, 'td')
                    action_td = tds[-1] if tds else row
                    for tx in triggers:
                        try:
                            trigger = action_td.find_element(By.XPATH, tx)
                            break
                        except: continue
                    
                    if trigger:
                        logger.info("More button found.")
                        # Just checking existence, not clicking to avoid side effects in this test run unless needed
                    else:
                        logger.error("More button NOT found.")
                except Exception as ex:
                    logger.error(f"More button check error: {ex}")

    except Exception as e:
        logger.error(f"Test failed: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    run_test()
