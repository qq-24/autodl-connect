#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试AutoDL设备列表页面结构分析"""

import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

def analyze_device_list_page():
    """分析设备列表页面结构"""
    print("开始分析AutoDL设备列表页面结构...")
    
    # 设置Chrome选项
    chrome_options = Options()
    chrome_options.add_argument('--window-size=1400,900')
    chrome_options.add_argument('--force-device-scale-factor=0.8')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    # 创建WebDriver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.execute_script("document.body.style.zoom='80%'")
    
    try:
        # 导航到登录页面
        print("导航到登录页面...")
        driver.get('https://www.autodl.com/login')
        time.sleep(3)
        
        # 执行登录
        print("执行登录...")
        username_input = driver.find_element(By.CSS_SELECTOR, 'input[placeholder="手机号"], input[type="tel"]')
        password_input = driver.find_element(By.CSS_SELECTOR, 'input[placeholder="密码"], input[type="password"]')
        
        username_input.clear()
        username_input.send_keys('13800138000')  # 测试账号
        password_input.clear()
        password_input.send_keys('test123456')   # 测试密码
        
        login_button = driver.find_element(By.CSS_SELECTOR, '.el-button--primary')
        login_button.click()
        
        time.sleep(5)  # 等待登录完成
        
        # 导航到设备列表页面
        print("导航到设备列表页面...")
        driver.get('https://www.autodl.com/console/instance/list')
        time.sleep(5)  # 等待页面加载
        
        # 分析页面结构
        print("分析页面结构...")
        
        # 1. 查找表格
        print("\n=== 表格分析 ===")
        tables = driver.find_elements(By.TAG_NAME, 'table')
        print(f"找到 {len(tables)} 个表格")
        
        for i, table in enumerate(tables):
            print(f"\n表格 {i+1}:")
            print(f"  类名: {table.get_attribute('class')}")
            print(f"  ID: {table.get_attribute('id')}")
            
            # 获取表头
            headers = table.find_elements(By.TAG_NAME, 'th')
            print(f"  表头数量: {len(headers)}")
            for j, header in enumerate(headers):
                print(f"    表头 {j+1}: {header.text.strip()}")
            
            # 获取行
            rows = table.find_elements(By.TAG_NAME, 'tr')
            print(f"  总行数: {len(rows)}")
            
            # 分析前几行
            for j, row in enumerate(rows[:3]):  # 只分析前3行
                print(f"\n  行 {j+1}:")
                print(f"    类名: {row.get_attribute('class')}")
                cells = row.find_elements(By.TAG_NAME, 'td')
                print(f"    单元格数量: {len(cells)}")
                
                for k, cell in enumerate(cells):
                    print(f"      单元格 {k+1}: '{cell.text.strip()}' (类名: {cell.get_attribute('class')})")
        
        # 2. 查找设备列表特定的元素
        print("\n=== 设备列表特定元素分析 ===")
        
        # 查找包含"实例"或"设备"关键词的元素
        keywords = ['实例', '设备', 'instance', 'device']
        for keyword in keywords:
            elements = driver.find_elements(By.XPATH, f"//*[contains(text(), '{keyword}')]")
            if elements:
                print(f"包含'{keyword}'的元素数量: {len(elements)}")
                for elem in elements[:3]:  # 只显示前3个
                    print(f"  标签: {elem.tag_name}, 文本: '{elem.text.strip()[:50]}...', 类名: {elem.get_attribute('class')}")
        
        # 3. 查找Vue.js相关的组件
        print("\n=== Vue.js组件分析 ===")
        vue_components = driver.find_elements(By.CSS_SELECTOR, '[class*="el-"], [class*="vue-"]')
        print(f"找到 {len(vue_components)} 个Vue.js相关元素")
        
        # 按类名分组
        vue_classes = {}
        for elem in vue_components:
            classes = elem.get_attribute('class')
            if classes:
                for cls in classes.split():
                    if 'el-' in cls or 'vue-' in cls:
                        if cls not in vue_classes:
                            vue_classes[cls] = 0
                        vue_classes[cls] += 1
        
        # 显示最常见的Vue类
        sorted_classes = sorted(vue_classes.items(), key=lambda x: x[1], reverse=True)
        print("最常见的Vue类名:")
        for cls, count in sorted_classes[:10]:
            print(f"  {cls}: {count} 次")
        
        # 4. 查找可能的设备容器
        print("\n=== 设备容器分析 ===")
        containers = driver.find_elements(By.CSS_SELECTOR, '[class*="instance"], [class*="device"], [class*="server"]')
        print(f"找到 {len(containers)} 个可能的设备容器")
        
        for i, container in enumerate(containers[:5]):
            print(f"\n容器 {i+1}:")
            print(f"  标签: {container.tag_name}")
            print(f"  类名: {container.get_attribute('class')}")
            print(f"  文本预览: {container.text.strip()[:100]}...")
        
        # 5. 尝试直接查找设备信息
        print("\n=== 直接设备信息查找 ===")
        
        # 查找状态相关的文本
        status_keywords = ['运行中', '已关机', '开机', '关机', 'pending', 'running', 'stopped']
        for status in status_keywords:
            status_elements = driver.find_elements(By.XPATH, f"//*[contains(text(), '{status}')]")
            if status_elements:
                print(f"状态为'{status}'的元素数量: {len(status_elements)}")
        
        print("\n页面结构分析完成！")
        
    except Exception as e:
        print(f"分析过程中出错: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        print("\n按Enter键关闭浏览器...")
        input()
        driver.quit()

if __name__ == '__main__':
    analyze_device_list_page()