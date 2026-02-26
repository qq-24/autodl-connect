import os
import subprocess
import sys

def build():
    print("Building AutoDL Helper...")
    
    # Check for icon (relative to project root)
    icon_path = os.path.join('..', 'assets', 'icon.ico')
    if not os.path.exists(icon_path):
        print(f"Warning: Icon not found at {icon_path}. Building with default icon.")
        icon_arg = []
    else:
        print(f"Using icon: {icon_path}")
        icon_arg = [f'--icon={icon_path}']

    # PyInstaller arguments
    args = [
        'pyinstaller',
        '--noconfirm',
        '--onefile',
        '--windowed',
        '--name=AutoDL一键连接',
        '--clean',
        '--add-data=../assets;assets',
        '--hidden-import=engineio.async_drivers.threading', # Common missing import
    ] + icon_arg + ['flet-v2.py']

    print(f"Running: {' '.join(args)}")
    try:
        subprocess.check_call(args)
        print("\nBuild successful! Executable is in 'dist' folder.")
    except subprocess.CalledProcessError as e:
        print(f"\nBuild failed: {e}")

if __name__ == "__main__":
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller not installed. Installing...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'pyinstaller'])
    
    build()
