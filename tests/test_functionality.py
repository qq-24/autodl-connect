#!/usr/bin/env python3
"""
测试程序密码保存和GPU检测功能
"""

import os
import json
import time

def test_password_save():
    """测试密码保存功能"""
    print("=== 测试密码保存功能 ===")
    
    # 检查配置文件是否存在
    config_dir = os.path.join(os.path.expanduser('~'), '.autodl_auto_starter', 'configs')
    credentials_file = os.path.join(config_dir, 'credentials.json')
    cookies_file = os.path.join(config_dir, 'cookies.json')
    
    print(f"配置目录: {config_dir}")
    print(f"凭据文件: {credentials_file}")
    print(f"Cookies文件: {cookies_file}")
    
    # 检查凭据文件
    if os.path.exists(credentials_file):
        try:
            with open(credentials_file, 'r', encoding='utf-8') as f:
                credentials = json.load(f)
            
            print("凭据文件内容:")
            print(f"  用户名: {credentials.get('username', '未找到')}")
            print(f"  记住密码: {credentials.get('remember_password', False)}")
            print(f"  保存时间: {credentials.get('saved_at', '未找到')}")
            print(f"  密码长度: {len(credentials.get('password', ''))} 字符")
            
        except Exception as e:
            print(f"读取凭据文件失败: {e}")
    else:
        print("凭据文件不存在")
    
    # 检查cookies文件
    if os.path.exists(cookies_file):
        try:
            with open(cookies_file, 'r', encoding='utf-8') as f:
                cookies = json.load(f)
            
            print(f"Cookies文件包含 {len(cookies)} 个cookies")
            
            # 检查cookie是否过期
            current_time = time.time()
            valid_cookies = 0
            for cookie in cookies:
                if 'expiry' in cookie and cookie['expiry']:
                    if cookie['expiry'] > current_time:
                        valid_cookies += 1
                    else:
                        print(f"Cookie {cookie.get('name', 'unknown')} 已过期")
                else:
                    valid_cookies += 1
            
            print(f"有效cookies数量: {valid_cookies}")
            
        except Exception as e:
            print(f"读取cookies文件失败: {e}")
    else:
        print("Cookies文件不存在")

def test_gpu_detection_script():
    """测试GPU检测脚本"""
    print("\n=== 测试GPU检测脚本 ===")
    
    # 检查测试脚本是否存在
    test_script = 'test_gpu_detection.py'
    if os.path.exists(test_script):
        print(f"GPU检测脚本存在: {test_script}")
        
        # 检查是否有之前的调试输出文件
        debug_files = [
            'gpu_detection_debug.json',
            'autodl_page_screenshot.png'
        ]
        
        for debug_file in debug_files:
            if os.path.exists(debug_file):
                print(f"找到调试文件: {debug_file}")
                if debug_file.endswith('.json'):
                    try:
                        with open(debug_file, 'r', encoding='utf-8') as f:
                            debug_data = json.load(f)
                        print(f"  调试数据: {debug_data}")
                    except Exception as e:
                        print(f"  读取调试数据失败: {e}")
            else:
                print(f"调试文件不存在: {debug_file}")
    else:
        print(f"GPU检测脚本不存在: {test_script}")

def main():
    """主测试函数"""
    print("开始测试SSH端口转发工具功能...")
    print("=" * 60)
    
    test_password_save()
    test_gpu_detection_script()
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("\n建议:")
    print("1. 运行主程序 main.py 测试实际登录功能")
    print("2. 使用 '检测GPU' 按钮测试GPU识别功能")
    print("3. 检查程序日志输出以验证功能是否正常工作")

if __name__ == '__main__':
    main()