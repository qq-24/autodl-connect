#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试AutoDL设备列表页面结构分析 - 使用已知有效的选择器"""

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
        
        # 执行登录 - 使用已知有效的选择器
        print("执行登录...")
        wait = WebDriverWait(driver, 10)
        
        # 等待输入框出现
        username_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[placeholder="手机号"]')))
        password_input = driver.find_element(By.CSS_SELECTOR, 'input[placeholder="密码"]')
        
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
        
        # 1. 查找表格 - 使用更通用的方法
        print("\n=== 表格分析 ===")
        
        # 等待表格加载
        try:
            table = wait.until(EC.presence_of_element_located((By.TAG_NAME, 'table')))
            print("找到主表格")
            
            # 获取表头
            headers = table.find_elements(By.TAG_NAME, 'th')
            print(f"表头数量: {len(headers)}")
            for j, header in enumerate(headers):
                print(f"  表头 {j+1}: '{header.text.strip()}'")
            
            # 获取所有行
            rows = table.find_elements(By.TAG_NAME, 'tr')
            print(f"总行数: {len(rows)}")
            
            # 分析前5行数据行（跳过表头）
            data_rows = [row for row in rows if row.find_elements(By.TAG_NAME, 'td')]
            print(f"数据行数: {len(data_rows)}")
            
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
                            for sub_elem in sub_elements[:3]:
                                print(f"        {sub_elem.tag_name}: '{sub_elem.text.strip()[:30]}'")
            
        except TimeoutException:
            print("表格加载超时")
        
        # 2. 查找Vue.js相关的表格组件
        print("\n=== Vue.js表格组件分析 ===")
        
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
                        print(f"        单元格 {k+1}: '{cell.text.strip()[:30]}'")
        
        # 3. 查找状态相关的元素
        print("\n=== 设备状态分析 ===")
        status_keywords = ['运行中', '已关机', '开机', '关机', 'pending', 'running', 'stopped', 'active', 'inactive']
        
        for status in status_keywords:
            status_elements = driver.find_elements(By.XPATH, f"//*[contains(text(), '{status}')]")
            if status_elements:
                print(f"状态为'{status}'的元素数量: {len(status_elements)}")
                
                # 显示前几个元素的上文
                for elem in status_elements[:3]:
                    parent = elem.find_element(By.XPATH, '..')
                    print(f"  上下文: '{parent.text.strip()[:60]}...'")
        
        # 4. 查找设备名称或ID
        print("\n=== 设备标识分析 ===")
        
        # 查找可能包含设备名称的元素
        name_indicators = driver.find_elements(By.CSS_SELECTOR, '[class*="name"], [class*="id"], [class*="title"]')
        print(f"找到 {len(name_indicators)} 个可能的设备标识元素")
        
        for i, elem in enumerate(name_indicators[:5]):
            print(f"设备标识 {i+1}:")
            print(f"  标签: {elem.tag_name}")
            print(f"  类名: {elem.get_attribute('class')}")
            print(f"  文本: '{elem.text.strip()[:40]}'")
        
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