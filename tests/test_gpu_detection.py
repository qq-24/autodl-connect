#!/usr/bin/env python3
"""
AutoDL GPU设备识别测试脚本
用于分析和测试如何正确识别可用显卡数量
"""

import time
import json
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

def test_gpu_detection():
    """测试GPU设备检测功能"""
    
    # 设置Chrome选项
    chrome_options = Options()
    chrome_options.add_argument('--window-size=1400,900')
    chrome_options.add_argument('--force-device-scale-factor=0.8')  # 浏览器缩放
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    
    driver = None
    try:
        print("正在初始化Chrome浏览器...")
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        
        # 首先访问主页
        print("访问AutoDL主页...")
        driver.get('https://www.autodl.com')
        time.sleep(2)
        
        # 加载cookies（如果存在）
        cookies_file = 'autodl_cookies.json'
        try:
            if os.path.exists(cookies_file):
                with open(cookies_file, 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
                
                for cookie in cookies:
                    try:
                        driver.add_cookie(cookie)
                    except Exception as e:
                        print(f"添加cookie失败: {e}")
                
                print(f"已加载 {len(cookies)} 个cookies")
                # 重新访问页面以应用cookies
                driver.get('https://www.autodl.com/console/instance/list')
                time.sleep(3)
            else:
                print("未找到cookies文件，需要手动登录")
                return
        except Exception as e:
            print(f"加载cookies失败: {e}")
            return
        
        # 设置网页缩放为70%以显示更多内容
        print("设置网页缩放为70%...")
        driver.execute_script("document.body.style.zoom='70%'")
        time.sleep(1)
        
        # 获取页面基本信息
        page_title = driver.title
        current_url = driver.current_url
        print(f"页面标题: {page_title}")
        print(f"当前URL: {current_url}")
        
        # 等待页面加载完成
        print("等待页面加载完成...")
        wait = WebDriverWait(driver, 15)
        
        # 统一按“滚动+分页的行解析”统计设备
        gpu_devices = []

        def scroll_collect_rows(el_table):
            rows_collected = []
            try:
                try:
                    wrapper = el_table.find_element(By.CSS_SELECTOR, '.el-table__body-wrapper')
                except Exception:
                    wrapper = el_table
                prev = -1
                stable = 0
                for _ in range(30):
                    body = el_table.find_element(By.CSS_SELECTOR, '.el-table__body')
                    rows = body.find_elements(By.TAG_NAME, 'tr')
                    count = len(rows)
                    if count == prev:
                        stable += 1
                    else:
                        stable = 0
                    prev = count
                    rows_collected = rows
                    try:
                        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollTop + arguments[0].clientHeight;", wrapper)
                    except Exception:
                        pass
                    time.sleep(0.25)
                    if stable >= 3:
                        break
            except Exception as e:
                print(f"滚动收集行失败: {e}")
            return rows_collected
        
        print("\n=== 方法1: 查找标准HTML表格 ===")
        try:
            # 查找所有表格
            tables = driver.find_elements(By.TAG_NAME, 'table')
            print(f"找到 {len(tables)} 个表格")
            
            for table_index, table in enumerate(tables):
                print(f"\n分析表格 {table_index + 1}:")
                rows = table.find_elements(By.TAG_NAME, 'tr')
                print(f"  表格有 {len(rows)} 行")
                
                # 分析表头
                headers = table.find_elements(By.TAG_NAME, 'th')
                if headers:
                    header_texts = [h.text.strip() for h in headers]
                    print(f"  表头: {header_texts}")
                
                # 分析数据行
                for row_index, row in enumerate(rows):
                    cells = row.find_elements(By.TAG_NAME, 'td')
                    if cells:
                        cell_texts = [cell.text.strip() for cell in cells]
                        print(f"  行 {row_index + 1}: {cell_texts}")
                        
                        # 检查是否包含GPU相关信息
                        for cell_text in cell_texts:
                            if any(gpu_keyword in cell_text.lower() for gpu_keyword in ['gpu', '显卡', '显存', 'cuda']):
                                gpu_devices.append({
                                    'table_index': table_index,
                                    'row_index': row_index,
                                    'data': cell_texts
                                })
                                break
        except Exception as e:
            print(f"标准表格查找失败: {e}")
        
        print("\n=== 方法2: 查找Element UI表格（滚动+分页） ===")
        try:
            el_tables = driver.find_elements(By.CSS_SELECTOR, '.el-table')
            print(f"找到 {len(el_tables)} 个Element UI表格")

            pager_pages = []
            try:
                pagination = driver.find_element(By.CSS_SELECTOR, '.el-pagination')
                pager_pages = pagination.find_elements(By.CSS_SELECTOR, '.el-pager .number')
                print(f"分页页码数: {len(pager_pages)}")
            except Exception:
                pass

            def parse_rows(rows, table_index=0):
                for row_index, row in enumerate(rows):
                    cells = row.find_elements(By.TAG_NAME, 'td')
                    cell_texts = [c.text.strip() for c in cells] if cells else []
                    gpu_devices.append({
                        'table_type': 'el-table',
                        'table_index': table_index,
                        'row_index': row_index,
                        'data': cell_texts
                    })

            if pager_pages:
                for p_i, p in enumerate(pager_pages):
                    try:
                        driver.execute_script("arguments[0].scrollIntoView(true);", p)
                        p.click()
                        time.sleep(0.8)
                        for t_i, t in enumerate(el_tables):
                            rows = scroll_collect_rows(t)
                            parse_rows(rows, table_index=t_i)
                    except Exception as e:
                        print(f"点击分页 {p_i+1} 失败: {e}")
            else:
                for t_i, t in enumerate(el_tables):
                    rows = scroll_collect_rows(t)
                    parse_rows(rows, table_index=t_i)
        except Exception as e:
            print(f"Element UI表格查找失败: {e}")
        
        print("\n=== 方法3: 查找设备卡片/容器 ===")
        try:
            # 查找可能的设备容器
            containers = driver.find_elements(By.CSS_SELECTOR, 
                '[class*="instance"], [class*="device"], [class*="server"], [class*="gpu"]')
            print(f"找到 {len(containers)} 个设备容器")
            
            for container_index, container in enumerate(containers):
                container_text = container.text.strip()
                if container_text:
                    print(f"容器 {container_index + 1}: {container_text[:100]}...")
                    
                    # 检查是否包含GPU相关信息
                    if any(gpu_keyword in container_text.lower() for gpu_keyword in ['gpu', '显卡', '显存', 'cuda']):
                        gpu_devices.append({
                            'container_type': 'device',
                            'container_index': container_index,
                            'data': container_text
                        })
        except Exception as e:
            print(f"设备容器查找失败: {e}")
        
        print("\n=== 方法4: 查找特定GPU相关元素 ===")
        try:
            # 查找包含GPU关键字的元素
            gpu_elements = driver.find_elements(By.XPATH, 
                "//*[contains(text(), 'GPU') or contains(text(), '显卡') or contains(text(), '显存') or contains(text(), 'CUDA')]")
            print(f"找到 {len(gpu_elements)} 个包含GPU关键字的元素")
            
            for element_index, element in enumerate(gpu_elements):
                element_text = element.text.strip()
                print(f"GPU元素 {element_index + 1}: {element_text}")
                
                # 获取父元素信息
                parent = element.find_element(By.XPATH, '..')
                parent_text = parent.text.strip()
                print(f"  父元素内容: {parent_text[:200]}...")
        except Exception as e:
            print(f"GPU元素查找失败: {e}")
        
        print("\n=== 方法5: 分析页面结构 ===")
        try:
            # 获取页面完整文本内容
            page_text = driver.find_element(By.TAG_NAME, 'body').text
            lines = page_text.split('\n')
            
            print(f"页面共有 {len(lines)} 行文本")
            
            # 查找包含GPU相关信息的行
            gpu_lines = []
            for line_index, line in enumerate(lines):
                if any(gpu_keyword in line.lower() for gpu_keyword in ['gpu', '显卡', '显存', 'cuda']):
                    gpu_lines.append((line_index, line.strip()))
            
            print(f"找到 {len(gpu_lines)} 行包含GPU信息:")
            for line_index, line_text in gpu_lines[:10]:  # 只显示前10个
                print(f"  行 {line_index}: {line_text}")
        except Exception as e:
            print(f"页面结构分析失败: {e}")
        
        print(f"\n=== 总结 ===")
        print(f"总共找到 {len(gpu_devices)} 台设备")
        
        if gpu_devices:
            print("\nGPU设备详情:")
            for device in gpu_devices:
                print(f"  {device}")
        
        # 保存调试信息到文件
        debug_info = {
            'page_title': page_title,
            'current_url': current_url,
            'gpu_devices_found': len(gpu_devices),
            'gpu_devices': gpu_devices,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        }
        
        with open('gpu_detection_debug.json', 'w', encoding='utf-8') as f:
            json.dump(debug_info, f, ensure_ascii=False, indent=2)
        
        print(f"\n调试信息已保存到 gpu_detection_debug.json")
        
        # 尝试截图保存当前页面状态
        try:
            driver.save_screenshot('autodl_page_screenshot.png')
            print("页面截图已保存到 autodl_page_screenshot.png")
        except Exception as e:
            print(f"截图失败: {e}")
        
        return gpu_devices
        
    except Exception as e:
        print(f"测试过程中出错: {e}")
        import traceback
        traceback.print_exc()
        return []
        
    finally:
        if driver:
            print("关闭浏览器...")
            driver.quit()

if __name__ == '__main__':
    import os
    print("开始AutoDL GPU设备识别测试...")
    print("=" * 50)
    
    gpu_devices = test_gpu_detection()
    
    print("\n" + "=" * 50)
    print("测试完成！")
    print(f"识别到的GPU设备数量: {len(gpu_devices)}")