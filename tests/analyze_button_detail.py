#!/usr/bin/env python3
"""详细分析AutoDL登录按钮结构"""

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

def analyze_button_detail():
    """详细分析登录按钮结构"""
    print("正在详细分析AutoDL登录按钮结构...")
    try:
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        print("访问登录页面...")
        driver.get('https://www.autodl.com/login')
        time.sleep(5)  # 等待页面完全加载
        
        print(f"页面标题: {driver.title}")
        
        # 获取所有按钮的详细信息
        print("\n=== 所有按钮详细信息 ===")
        all_buttons = driver.find_elements(By.TAG_NAME, 'button')
        for i, button in enumerate(all_buttons):
            print(f"按钮 {i+1}:")
            print(f"  文本内容: '{button.text}'")
            print(f"  文本长度: {len(button.text)}")
            print(f"  HTML: {button.get_attribute('outerHTML')[:200]}...")
            print(f"  类型: {button.get_attribute('type')}")
            print(f"  类名: {button.get_attribute('class')}")
            print(f"  是否显示: {button.is_displayed()}")
            print(f"  是否启用: {button.is_enabled()}")
            print()
        
        # 尝试不同的按钮查找方法
        print("\n=== 尝试不同查找方法 ===")
        
        # 方法1: 通过类名查找
        try:
            buttons_by_class = driver.find_elements(By.CLASS_NAME, 'el-button--primary')
            print(f"通过主按钮类名找到 {len(buttons_by_class)} 个按钮")
            for btn in buttons_by_class:
                print(f"  文本: '{btn.text}'")
        except Exception as e:
            print(f"类名查找失败: {e}")
        
        # 方法2: 通过CSS选择器
        try:
            primary_button = driver.find_element(By.CSS_SELECTOR, '.el-button--primary')
            print(f"CSS选择器找到主按钮: '{primary_button.text}'")
        except Exception as e:
            print(f"CSS选择器查找失败: {e}")
        
        # 方法3: 通过部分文本匹配
        try:
            login_btn_partial = driver.find_element(By.XPATH, "//button[contains(translate(text(), '登录', '登录'), '登录')]")
            print(f"部分文本匹配找到按钮: '{login_btn_partial.text}'")
        except Exception as e:
            print(f"部分文本匹配失败: {e}")
        
        # 方法4: 获取按钮父元素
        print("\n=== 按钮父元素结构 ===")
        try:
            primary_button = driver.find_element(By.CSS_SELECTOR, '.el-button--primary')
            parent = primary_button.find_element(By.XPATH, '..')
            print(f"按钮父元素HTML: {parent.get_attribute('outerHTML')[:300]}...")
        except Exception as e:
            print(f"获取父元素失败: {e}")
        
        # 尝试点击第一个主按钮
        print("\n=== 尝试点击主按钮 ===")
        try:
            primary_button = driver.find_element(By.CSS_SELECTOR, '.el-button--primary')
            print(f"准备点击按钮: '{primary_button.text}'")
            
            # 滚动到元素可见
            driver.execute_script("arguments[0].scrollIntoView(true);", primary_button)
            time.sleep(1)
            
            # 等待元素可点击
            wait = WebDriverWait(driver, 10)
            clickable_button = wait.until(EC.element_to_be_clickable(primary_button))
            
            print("按钮已可点击，执行点击...")
            clickable_button.click()
            print("✓ 按钮点击成功!")
            
            time.sleep(3)
            print(f"点击后URL: {driver.current_url}")
            
        except Exception as e:
            print(f"按钮点击失败: {e}")
        
        driver.quit()
        print("\n分析完成!")
        return True
        
    except Exception as e:
        print(f"错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    print("=== AutoDL登录按钮详细分析 ===")
    success = analyze_button_detail()
    sys.exit(0 if success else 1)