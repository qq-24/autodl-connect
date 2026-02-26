#!/usr/bin/env python3
"""
AutoDL自动开机工具启动脚本
"""

import subprocess
import sys
import os

def check_and_install_requirements():
    """检查并安装依赖"""
    print("正在检查依赖...")
    
    try:
        import selenium
        import PyQt5
        print("依赖已安装，跳过安装步骤")
        return True
    except ImportError as e:
        print(f"缺少依赖: {e}")
        print("正在安装依赖...")
        
        try:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', 'requirements_autodl.txt'])
            print("依赖安装完成")
            return True
        except subprocess.CalledProcessError as e:
            print(f"依赖安装失败: {e}")
            return False

def main():
    """主函数"""
    print("=== AutoDL自动开机工具 ===")
    print("正在启动...")
    
    # 检查依赖
    if not check_and_install_requirements():
        print("依赖安装失败，请手动安装依赖后重试")
        input("按回车键退出...")
        return
    
    # 导入主模块
    try:
        from autodl_auto_start import main as autodl_main
        print("正在启动AutoDL自动开机工具...")
        autodl_main()
    except Exception as e:
        print(f"启动失败: {e}")
        input("按回车键退出...")

if __name__ == '__main__':
    main()