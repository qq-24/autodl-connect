#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试Cookie保存和加载功能"""

import json
import time
import os
from datetime import datetime, timedelta

def test_cookie_functionality():
    """测试cookie保存和加载功能"""
    
    # 创建测试cookie数据
    test_cookies = [
        {
            'name': 'session_id',
            'value': 'test_session_12345',
            'domain': '.autodl.com',
            'path': '/',
            'expiry': int((datetime.now() + timedelta(days=7)).timestamp()),
            'secure': True,
            'httpOnly': True
        },
        {
            'name': 'user_token',
            'value': 'test_token_abcdef',
            'domain': '.autodl.com',
            'path': '/',
            'expiry': int((datetime.now() + timedelta(days=30)).timestamp()),
            'secure': True,
            'httpOnly': False
        },
        {
            'name': 'expired_cookie',
            'value': 'expired_value',
            'domain': '.autodl.com',
            'path': '/',
            'expiry': int((datetime.now() - timedelta(days=1)).timestamp()),  # 已过期
            'secure': False,
            'httpOnly': False
        }
    ]
    
    # 测试保存
    test_file = 'test_cookies.json'
    print("=== 测试Cookie保存 ===")
    try:
        with open(test_file, 'w', encoding='utf-8') as f:
            json.dump(test_cookies, f, ensure_ascii=False, indent=2)
        print(f"成功保存 {len(test_cookies)} 个cookies到文件")
    except Exception as e:
        print(f"保存cookies失败: {e}")
        return
    
    # 测试加载和验证
    print("\n=== 测试Cookie加载和验证 ===")
    try:
        if os.path.exists(test_file):
            with open(test_file, 'r', encoding='utf-8') as f:
                loaded_cookies = json.load(f)
            
            print(f"从文件加载了 {len(loaded_cookies)} 个cookies")
            
            # 检查cookies是否过期
            valid_cookies = []
            current_time = time.time()
            
            for cookie in loaded_cookies:
                try:
                    # 检查cookie是否过期
                    if 'expiry' in cookie and cookie['expiry']:
                        if cookie['expiry'] < current_time:
                            print(f"Cookie {cookie.get('name', 'unknown')} 已过期 (过期时间: {datetime.fromtimestamp(cookie['expiry'])})")
                            continue
                    
                    # 清理cookie字典，只保留必要的字段
                    clean_cookie = {k: v for k, v in cookie.items() 
                                  if k in ['name', 'value', 'domain', 'path', 'expiry']}
                    valid_cookies.append(clean_cookie)
                    print(f"有效cookie: {clean_cookie['name']} (过期时间: {datetime.fromtimestamp(clean_cookie.get('expiry', current_time + 86400))})")
                    
                except Exception as cookie_error:
                    print(f"处理cookie失败: {cookie_error}")
                    continue
            
            print(f"最终有效cookies数量: {len(valid_cookies)}")
            
            # 模拟添加到浏览器
            print("\n=== 模拟添加到浏览器 ===")
            for cookie in valid_cookies:
                try:
                    # 模拟添加cookie到浏览器
                    print(f"添加cookie: {cookie['name']} = {cookie['value'][:10]}...")
                except Exception as add_error:
                    print(f"添加cookie失败: {add_error}")
                    continue
            
            print("Cookie测试完成！")
            
    except Exception as e:
        print(f"加载cookies失败: {e}")
    
    finally:
        # 清理测试文件
        if os.path.exists(test_file):
            os.remove(test_file)
            print(f"\n已清理测试文件: {test_file}")

if __name__ == '__main__':
    test_cookie_functionality()