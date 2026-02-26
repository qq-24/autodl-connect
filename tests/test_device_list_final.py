#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试AutoDL设备列表页面结构分析 - 基于main.py的有效实现"""

import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException
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
        
        # 执行登录 - 使用main.py中的有效方法
        print("执行登录...")
        wait = WebDriverWait(driver, 20)
        
        # 等待用户名输入框出现 - 使用占位符文本 (基于main.py的有效实现)
        all_text_inputs = wait.until(lambda driver: driver.find_elements(By.XPATH, "//input[@type='text']"))
        if len(all_text_inputs) >= 3:
            username_input = all_text_inputs[2]  # 第3个是手机号输入框
            print("找到手机号输入框")
        else:
            raise Exception("无法找到手机号输入框")
        
        # 查找密码输入框
        password_input = wait.until(EC.presence_of_element_located((By.XPATH, "//input[@type='password']")))
        print("找到密码输入框")
        
        # 填写用户名
        username_input.clear()
        username_input.send_keys('13800138000')  # 测试账号
        print("输入手机号")
        
        # 填写密码
        password_input.clear()
        password_input.send_keys('test123456')   # 测试密码
        print("输入密码")
        
        # 点击登录按钮 - 使用CSS类名选择器
        login_button = driver.find_element(By.CSS_SELECTOR, '.el-button--primary')
        
        # 确保按钮在视图中并可点击
        driver.execute_script("arguments[0].scrollIntoView(true);", login_button)
        time.sleep(0.5)
        
        # 等待按钮可点击
        clickable_button = wait.until(EC.element_to_be_clickable(login_button))
        clickable_button.click()
        print("点击登录按钮成功")
        
        # 等待登录结果
        time.sleep(5)
        
        # 检查是否登录成功
        current_url = driver.current_url
        print(f"登录后URL: {current_url}")
        
        if 'login' not in current_url:
            print("登录成功！")
        else:
            print("登录可能失败，继续分析页面...")
        
        # 导航到设备列表页面
        print("导航到设备列表页面...")
        driver.get('https://www.autodl.com/console/instance/list')
        time.sleep(5)  # 等待页面加载
        
        # 分析页面结构
        print("分析页面结构...")
        
        # 1. 查找表格 - 使用main.py中的方法
        print("\n=== 表格分析 ===")
        
        try:
            # 等待表格加载
            wait = WebDriverWait(driver, 10)
            table = wait.until(EC.presence_of_element_located((By.TAG_NAME, 'table')))
            print("找到表格")
            
            # 获取所有行
            rows = table.find_elements(By.TAG_NAME, 'tr')
            print(f"总行数: {len(rows)}")
            
            # 分析数据行（跳过表头）
            data_rows = rows[1:] if len(rows) > 1 else rows
            print(f"数据行数: {len(data_rows)}")
            
            # 分析前5行
            for i, row in enumerate(data_rows[:5]):
                print(f"\n数据行 {i+1}:")
                cells = row.find_elements(By.TAG_NAME, 'td')
                print(f"  单元格数量: {len(cells)}")
                
                for j, cell in enumerate(cells):
                    cell_text = cell.text.strip()
                    print(f"    单元格 {j+1}: '{cell_text[:50]}{'...' if len(cell_text) > 50 else ''}'")
                    
                    # 如果单元格内容复杂，进一步分析
                    if len(cell_text) > 20:
                        # 查找子元素
                        sub_elements = cell.find_elements(By.XPATH, './/*')
                        if sub_elements:
                            print(f"      子元素数量: {len(sub_elements)}")
                            for sub_elem in sub_elements[:2]:
                                sub_text = sub_elem.text.strip()
                                if sub_text:
                                    print(f"        {sub_elem.tag_name}: '{sub_text[:30]}'")
            
        except TimeoutException:
            print("表格加载超时")
        
        # 2. 查找Element UI表格组件
        print("\n=== Element UI表格组件分析 ===")
        
        # 查找Element UI表格
        el_tables = driver.find_elements(By.CSS_SELECTOR, '.el-table')
        print(f"找到 {len(el_tables)} 个Element UI表格")
        
        for i, table in enumerate(el_tables):
            print(f"\nElement UI表格 {i+1}:")
            print(f"  类名: {table.get_attribute('class')}")
            
            # 查找表格体
            table_body = table.find_elements(By.CSS_SELECTOR, '.el-table__body')
            print(f"  表格体数量: {len(table_body)}")
            
            if table_body:
                body_rows = table_body[0].find_elements(By.TAG_NAME, 'tr')
                print(f"  数据行数量: {len(body_rows)}")
                
                # 分析前几行
                for j, row in enumerate(body_rows[:3]):
                    print(f"    行 {j+1}:")
                    cells = row.find_elements(By.TAG_NAME, 'td')
                    print(f"      单元格数量: {len(cells)}")
                    
                    for k, cell in enumerate(cells):
                        cell_text = cell.text.strip()
                        print(f"        单元格 {k+1}: '{cell_text[:30]}'")
        
        # 3. 查找状态相关的元素
        print("\n=== 设备状态分析 ===")
        status_keywords = ['运行中', '已关机', '开机', '关机', 'pending', 'running', 'stopped', 'active', 'inactive']
        
        for status in status_keywords:
            status_elements = driver.find_elements(By.XPATH, f"//*[contains(text(), '{status}')]")
            if status_elements:
                print(f"状态为'{status}'的元素数量: {len(status_elements)}")
                
                # 显示前几个元素的上文
                for elem in status_elements[:2]:
                    parent = elem.find_element(By.XPATH, '..')
                    parent_text = parent.text.strip()
                    if parent_text and len(parent_text) > 10:
                        print(f"  上下文: '{parent_text[:60]}...'")
        
        # 4. 查找设备名称或ID
        print("\n=== 设备标识分析 ===")
        
        # 查找可能包含设备名称的元素
        name_indicators = driver.find_elements(By.CSS_SELECTOR, '[class*="name"], [class*="id"], [class*="title"]')
        print(f"找到 {len(name_indicators)} 个可能的设备标识元素")
        
        for i, elem in enumerate(name_indicators[:5]):
            elem_text = elem.text.strip()
            if elem_text and len(elem_text) > 3:
                print(f"设备标识 {i+1}:")
                print(f"  标签: {elem.tag_name}")
                print(f"  类名: {elem.get_attribute('class')}")
                print(f"  文本: '{elem_text[:40]}'")
        
        # 5. 尝试获取当前页面截图用于分析
        print("\n=== 页面截图 ===")
        try:
            driver.save_screenshot('autodl_device_list.png')
            print("页面截图已保存为 'autodl_device_list.png'")
        except Exception as e:
            print(f"截图失败: {e}")
        
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