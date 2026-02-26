#!/usr/bin/env python3
"""分析AutoDL登录页面结构"""

import sys
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

def analyze_login_page():
    """分析登录页面结构"""
    print("正在分析AutoDL登录页面结构...")
    try:
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        print("访问登录页面...")
        driver.get('https://www.autodl.com/login')
        time.sleep(5)  # 等待页面完全加载
        
        print(f"页面标题: {driver.title}")
        print(f"当前URL: {driver.current_url}")
        
        # 获取完整的页面源代码
        page_source = driver.page_source
        print("\n=== 页面源代码 ===")
        print(page_source[:2000])  # 显示前2000字符
        
        # 尝试找到所有的输入框和按钮
        print("\n=== 查找所有输入元素 ===")
        all_inputs = driver.find_elements(By.TAG_NAME, 'input')
        for i, input_elem in enumerate(all_inputs):
            print(f"输入框 {i+1}:")
            print(f"  类型: {input_elem.get_attribute('type')}")
            print(f"  名称: {input_elem.get_attribute('name')}")
            print(f"  ID: {input_elem.get_attribute('id')}")
            print(f"  占位符: {input_elem.get_attribute('placeholder')}")
            print()
        
        print("\n=== 查找所有按钮 ===")
        all_buttons = driver.find_elements(By.TAG_NAME, 'button')
        for i, button in enumerate(all_buttons):
            print(f"按钮 {i+1}:")
            print(f"  文本: {button.text}")
            print(f"  类型: {button.get_attribute('type')}")
            print(f"  ID: {button.get_attribute('id')}")
            print(f"  类名: {button.get_attribute('class')}")
            print()
        
        # 尝试使用不同的选择器
        print("\n=== 尝试不同选择器 ===")
        
        # 尝试通过占位符文本查找
        try:
            username_by_placeholder = driver.find_element(By.XPATH, "//input[@placeholder='用户名']")
            print("✓ 通过占位符找到用户名输入框")
        except:
            print("✗ 通过占位符未找到用户名输入框")
        
        try:
            username_by_placeholder2 = driver.find_element(By.XPATH, "//input[@placeholder='请输入用户名']")
            print("✓ 通过占位符2找到用户名输入框")
        except:
            print("✗ 通过占位符2未找到用户名输入框")
        
        # 尝试通过类型查找
        try:
            username_by_type = driver.find_element(By.XPATH, "//input[@type='text']")
            print(f"✓ 通过类型找到文本输入框: {username_by_type.get_attribute('name')} / {username_by_type.get_attribute('id')}")
        except:
            print("✗ 通过类型未找到文本输入框")
        
        # 尝试通过包含文本的按钮查找
        try:
            login_btn = driver.find_element(By.XPATH, "//button[contains(text(), '登录')]")
            print(f"✓ 通过文本找到登录按钮: {login_btn.text}")
        except:
            print("✗ 通过文本未找到登录按钮")
        
        driver.quit()
        print("\n分析完成!")
        return True
        
    except Exception as e:
        print(f"错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    print("=== AutoDL登录页面分析 ===")
    success = analyze_login_page()
    sys.exit(0 if success else 1)