#!/usr/bin/env python3
"""
AutoDL自动开机工具 - 命令行版本
适合需要脚本化或定时任务的场景
"""

import json
import os
import time
import argparse
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException


class AutoDLCLI:
    def __init__(self, headless=True):
        self.driver = None
        self.headless = headless
        self.config_dir = os.path.join(os.path.expanduser('~'), '.autodl_auto_starter', 'configs')
        self.cookies_file = os.path.join(self.config_dir, 'cookies.json')
        self._init_config_directory()
    
    def _init_config_directory(self):
        """初始化配置目录"""
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir, exist_ok=True)
    
    def init_driver(self):
        """初始化Chrome驱动"""
        try:
            chrome_options = Options()
            if self.headless:
                chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return True
        except Exception as e:
            print(f"Chrome浏览器初始化失败: {str(e)}")
            return False
    
    def login(self, username, password):
        """登录AutoDL"""
        if not self.init_driver():
            return False
        
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在访问AutoDL登录页面...")
            self.driver.get('https://www.autodl.com/login')
            
            # 等待页面加载
            wait = WebDriverWait(self.driver, 10)
            
            # 填写用户名
            username_input = wait.until(EC.presence_of_element_located((By.NAME, 'username')))
            username_input.clear()
            username_input.send_keys(username)
            
            # 填写密码
            password_input = self.driver.find_element(By.NAME, 'password')
            password_input.clear()
            password_input.send_keys(password)
            
            # 点击登录按钮
            login_button = self.driver.find_element(By.XPATH, '//button[@type="submit"]')
            login_button.click()
            
            # 等待登录成功
            time.sleep(3)
            
            # 检查是否登录成功
            if 'login' not in self.driver.current_url:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 登录成功！")
                return True
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] 登录失败，请检查用户名和密码")
                return False
                
        except TimeoutException:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 登录超时，请检查网络连接")
            return False
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 登录过程出错: {str(e)}")
            return False
    
    def get_devices(self):
        """获取设备列表"""
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在获取设备列表...")
            self.driver.get('https://www.autodl.com/console/instance/list')
            time.sleep(3)
            
            # 等待表格加载
            wait = WebDriverWait(self.driver, 10)
            table = wait.until(EC.presence_of_element_located((By.TAG_NAME, 'table')))
            
            # 获取所有行
            rows = table.find_elements(By.TAG_NAME, 'tr')[1:]  # 跳过表头
            
            devices = []
            for i, row in enumerate(rows):
                cells = row.find_elements(By.TAG_NAME, 'td')
                if len(cells) >= 7:
                    # 设备名称和ID
                    name_cell = cells[0]
                    device_info = name_cell.text.split('\n')
                    device_name = device_info[0] if device_info else ''
                    device_id = device_info[1] if len(device_info) > 1 else ''
                    
                    # 状态
                    status = cells[1].text
                    
                    # 规格
                    specs = cells[2].text
                    
                    # 检查是否有开机按钮
                    has_start_button = False
                    try:
                        start_button = row.find_element(By.XPATH, './/a[contains(text(), "开机")]')
                        has_start_button = True
                    except:
                        pass
                    
                    devices.append({
                        'index': i,
                        'name': device_name,
                        'id': device_id,
                        'status': status,
                        'specs': specs,
                        'can_start': has_start_button,
                        'element': row
                    })
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 找到 {len(devices)} 个设备")
            return devices
            
        except TimeoutException:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 获取设备列表超时")
            return []
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 获取设备列表失败: {str(e)}")
            return []
    
    def start_device(self, device):
        """启动单个设备"""
        try:
            device_name = device['name']
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在启动设备: {device_name}")
            
            # 找到开机按钮并点击
            start_button = device['element'].find_element(By.XPATH, './/a[contains(text(), "开机")]')
            start_button.click()
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 等待确认对话框...")
            time.sleep(1)
            
            # 等待确认对话框
            wait = WebDriverWait(self.driver, 5)
            confirm_button = wait.until(EC.element_to_be_clickable((By.XPATH, '//button[contains(text(), "确定")]')))
            confirm_button.click()
            
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 设备 {device_name} 开机指令已发送")
            return True
            
        except TimeoutException:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 确认开机超时")
            return False
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 启动设备失败: {str(e)}")
            return False
    
    def start_devices_by_name(self, device_names):
        """根据设备名称启动设备"""
        devices = self.get_devices()
        if not devices:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 没有找到设备")
            return
        
        # 查找匹配的设备
        target_devices = []
        for name in device_names:
            for device in devices:
                if name in device['name'] or name in device['id']:
                    if device['can_start']:
                        target_devices.append(device)
                        break
        
        if not target_devices:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 没有找到可开机的设备")
            return
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 找到 {len(target_devices)} 个需要开机的设备")
        
        # 启动设备
        success_count = 0
        for device in target_devices:
            if self.start_device(device):
                success_count += 1
                time.sleep(2)  # 等待一下再处理下一个
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 批量开机完成，成功 {success_count}/{len(target_devices)} 个设备")
    
    def list_devices(self):
        """列出所有设备"""
        devices = self.get_devices()
        if not devices:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 没有找到设备")
            return
        
        print("\n设备列表:")
        print("-" * 80)
        print(f"{'序号':<4} {'设备名称':<20} {'状态':<10} {'规格':<20}")
        print("-" * 80)
        
        for device in devices:
            can_start = "✓" if device['can_start'] else "✗"
            print(f"{device['index']+1:<4} {device['name']:<20} {device['status']:<10} {device['specs']:<20} {can_start}")
        
        print("-" * 80)
        print(f"总计: {len(devices)} 个设备")
    
    def close(self):
        """关闭浏览器"""
        if self.driver:
            self.driver.quit()
            self.driver = None


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='AutoDL自动开机工具 - 命令行版本')
    parser.add_argument('--username', '-u', required=True, help='AutoDL用户名/邮箱')
    parser.add_argument('--password', '-p', required=True, help='AutoDL密码')
    parser.add_argument('--devices', '-d', nargs='+', help='要开机的设备名称（支持模糊匹配）')
    parser.add_argument('--list', '-l', action='store_true', help='仅列出设备，不开机')
    parser.add_argument('--headless', action='store_true', default=True, help='无头模式（默认开启）')
    parser.add_argument('--no-headless', action='store_true', help='显示浏览器窗口')
    
    args = parser.parse_args()
    
    print("=== AutoDL自动开机工具 (命令行版) ===")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始执行...")
    
    # 确定是否使用无头模式
    headless = not args.no_headless if args.no_headless else args.headless
    
    # 创建工具实例
    tool = AutoDLCLI(headless=headless)
    
    try:
        # 登录
        if not tool.login(args.username, args.password):
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 登录失败，程序退出")
            return 1
        
        # 列出设备
        if args.list:
            tool.list_devices()
        elif args.devices:
            # 启动指定设备
            tool.start_devices_by_name(args.devices)
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 未指定操作，使用 --help 查看帮助")
        
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 操作完成")
        return 0
        
    except KeyboardInterrupt:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 用户中断操作")
        return 1
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 执行出错: {str(e)}")
        return 1
    finally:
        tool.close()


if __name__ == '__main__':
    sys.exit(main())