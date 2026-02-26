#!/usr/bin/env python3
"""测试完整的AutoDL登录流程"""

import sys
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

def test_complete_login_flow():
    """测试完整的登录流程"""
    print("=== 测试完整AutoDL登录流程 ===")
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
        
        print("1. 访问登录页面...")
        driver.get('https://www.autodl.com/login')
        time.sleep(3)
        
        print(f"当前URL: {driver.current_url}")
        print(f"页面标题: {driver.title}")
        
        # 等待页面加载
        wait = WebDriverWait(driver, 15)
        
        print("2. 查找手机号输入框...")
        # 查找所有文本输入框
        all_text_inputs = wait.until(lambda driver: driver.find_elements(By.XPATH, "//input[@type='text']"))
        print(f"找到 {len(all_text_inputs)} 个文本输入框")
        
        if len(all_text_inputs) >= 3:
            username_input = all_text_inputs[2]  # 第3个是手机号输入框
            print("✓ 找到手机号输入框")
        else:
            raise Exception("手机号输入框数量不足")
        
        print("3. 查找密码输入框...")
        password_input = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@type='password']")))
        print("✓ 找到密码输入框")
        
        print("4. 输入测试凭据...")
        # 输入测试用户名
        username_input.clear()
        username_input.send_keys('13800138000')  # 测试手机号
        print("✓ 输入测试手机号")
        
        # 输入测试密码
        password_input.clear()
        password_input.send_keys('test123456')
        print("✓ 输入测试密码")
        
        print("5. 查找并点击登录按钮...")
        # 使用CSS选择器找到主按钮
        login_button = driver.find_element(By.CSS_SELECTOR, '.el-button--primary')
        print(f"找到登录按钮: '{login_button.text.strip()}'")
        
        # 确保按钮在视图中
        driver.execute_script("arguments[0].scrollIntoView(true);", login_button)
        time.sleep(0.5)
        
        # 等待按钮可点击
        wait = WebDriverWait(driver, 10)
        clickable_button = wait.until(EC.element_to_be_clickable(login_button))
        
        print("6. 点击登录按钮...")
        clickable_button.click()
        print("✓ 登录按钮点击成功")
        
        print("7. 等待登录结果...")
        # 等待页面跳转
        time.sleep(5)
        
        final_url = driver.current_url
        print(f"最终URL: {final_url}")
        
        # 检查登录结果
        if 'login' not in final_url:
            print("✓ 登录成功！页面已跳转")
            # 尝试访问实例列表
            driver.get('https://www.autodl.com/console/instance/list')
            time.sleep(3)
            print(f"实例列表页面标题: {driver.title}")
        else:
            print("✗ 登录失败，仍在登录页面")
            # 检查错误信息
            try:
                error_elements = driver.find_elements(By.XPATH, "//*[contains(text(), '错误') or contains(text(), '失败') or contains(text(), '账号') or contains(text(), '密码')]")
                if error_elements:
                    print(f"错误信息: {error_elements[0].text}")
            except:
                pass
        
        driver.quit()
        print("\n=== 测试完成 ===")
        return True
        
    except Exception as e:
        print(f"测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_complete_login_flow()
    sys.exit(0 if success else 1)