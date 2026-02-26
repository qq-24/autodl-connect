import json
import os
import time
import sys
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import PyQt5.QtCore as QtCore
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTextEdit, QMessageBox, QGroupBox, QCheckBox,
    QComboBox, QInputDialog, QFormLayout, QSplitter, QSizePolicy,
    QGraphicsDropShadowEffect, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView
)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QCoreApplication, QTimer
from PyQt5.QtGui import QFont, QPalette, QColor, QPainter, QBrush, QPen, QFontDatabase


class AutoDLAutoStarter(QMainWindow):
    update_status_signal = pyqtSignal(str)
    login_status_signal = pyqtSignal(bool)
    
    def __init__(self):
        super().__init__()
        self.driver = None
        self.is_logged_in = False
        self.config_dir = os.path.join(os.path.expanduser('~'), '.autodl_auto_starter', 'configs')
        self.cookies_file = os.path.join(self.config_dir, 'cookies.json')
        self.devices_file = os.path.join(self.config_dir, 'devices.json')
        self._init_config_directory()
        self.setup_ui()
        self.setup_event_handlers()
        self.load_saved_configs()
        print("AutoDL自动开机工具初始化完成")
    
    def _init_config_directory(self):
        """初始化配置目录"""
        try:
            if not os.path.exists(self.config_dir):
                os.makedirs(self.config_dir, exist_ok=True)
                self.update_status_signal.emit(f'配置目录已创建: {self.config_dir}')
        except Exception as e:
            self.update_status_signal.emit(f'警告: 无法创建配置目录: {str(e)}')
            self.config_dir = os.path.join(os.getcwd(), 'autodl_configs')
            os.makedirs(self.config_dir, exist_ok=True)
    
    def setup_ui(self):
        """设置用户界面"""
        self.setWindowTitle('AutoDL 自动开机工具')
        self.setObjectName('AutoDLWindow')
        self.setMinimumSize(1000, 700)
        self.setGeometry(200, 200, 1200, 800)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.oldPos = self.pos()
        
        # 设置字体
        import platform
        system = platform.system().lower()
        if 'darwin' in system:
            ui_font = QFont('PingFang SC', 12)
        elif 'windows' in system:
            ui_font = QFont('Microsoft YaHei UI', 11)
        else:
            ui_font = QFont('Noto Sans CJK SC', 11)
        
        # 创建中央部件
        central = QWidget()
        central.setObjectName('central')
        central.setAttribute(Qt.WA_TranslucentBackground)
        self.setCentralWidget(central)
        
        # 设置样式
        self.setStyleSheet('''
            QMainWindow#AutoDLWindow { background: transparent; }
            
            #contentCard {
                background: #ffffff;
                border: 1px solid #cfd6dd;
                border-radius: 12px;
            }
            
            #titleBar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                          stop:0 #f9fbfd, stop:1 #f1f5f9);
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
                border-bottom: 1px solid #e6ebf1;
            }
            
            QLabel { color: #1f2328; }
            QLineEdit, QComboBox {
                border: 1.5px solid #d0d7de;
                border-radius: 8px;
                background: #ffffff;
                color: #24292e;
                padding: 8px 12px;
                font-size: 11pt;
            }
            QLineEdit:focus, QComboBox:focus {
                border-color: #0969da;
                background: #f0f7ff;
            }
            
            QPushButton {
                border: none;
                font-weight: 600;
                font-size: 12pt;
                border-radius: 8px;
                padding: 8px 16px;
            }
            
            QPushButton#loginBtn {
                background: #0969da; color: #ffffff;
            }
            QPushButton#loginBtn:hover { background: #0550ae; }
            QPushButton#loginBtn:disabled { background: #d0d7de; color: #8c959f; }
            
            QPushButton#startBtn {
                background: #2ea043; color: #ffffff;
            }
            QPushButton#startBtn:hover { background: #238636; }
            QPushButton#startBtn:disabled { background: #d0d7de; color: #8c959f; }
            
            QPushButton#refreshBtn {
                background: #656d76; color: #ffffff;
            }
            QPushButton#refreshBtn:hover { background: #495057; }
            
            QTextEdit {
                font-family: "SFMono-Regular", "JetBrains Mono", "Consolas", "Menlo", monospace;
                font-size: 10pt;
                border: 1px solid #d0d7de;
                border-radius: 8px;
                background: #f6f8fa;
            }
            
            QTableWidget {
                border: 1px solid #d0d7de;
                border-radius: 8px;
                background: #ffffff;
                alternate-background-color: #f6f8fa;
            }
            QHeaderView::section {
                background: #f1f5f9;
                border: none;
                border-bottom: 1px solid #d0d7de;
                padding: 8px;
                font-weight: 600;
            }
        ''')
        
        # 创建主布局
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(0)
        
        # 内容卡片
        content_card = QWidget()
        content_card.setObjectName('contentCard')
        card_layout = QVBoxLayout(content_card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)
        
        # 添加阴影效果
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 8)
        content_card.setGraphicsEffect(shadow)
        
        # 标题栏
        title_bar = self.create_title_bar()
        card_layout.addWidget(title_bar)
        
        # 主要内容区域
        main_content = self.create_main_content()
        card_layout.addWidget(main_content, 1)
        
        root_layout.addWidget(content_card, 1)
        
        # 连接信号
        self.update_status_signal.connect(self.update_status)
        self.login_status_signal.connect(self.update_login_status)
    
    def create_title_bar(self):
        """创建标题栏"""
        title_bar = QWidget()
        title_bar.setObjectName('titleBar')
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(14, 10, 10, 10)
        title_layout.setSpacing(8)
        
        title_label = QLabel('AutoDL 自动开机工具')
        title_label.setStyleSheet('font-size: 18px; font-weight: 700; color: #1f2328;')
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        
        close_btn = QPushButton('✕')
        close_btn.setFixedSize(32, 32)
        close_btn.setStyleSheet('''
            QPushButton { background: #eaeef2; border: none; border-radius: 16px; color: #586069; font-weight: bold; }
            QPushButton:hover { background: #d8dee4; color: #24292e; }
            QPushButton:pressed { background: #c9d1d9; }
        ''')
        close_btn.clicked.connect(self.close)
        title_layout.addWidget(close_btn)
        
        return title_bar
    
    def create_main_content(self):
        """创建主要内容区域"""
        main_widget = QWidget()
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(16, 14, 16, 16)
        main_layout.setSpacing(10)
        
        # 创建标签页
        tab_widget = QTabWidget()
        
        # 登录配置页
        login_tab = self.create_login_tab()
        tab_widget.addTab(login_tab, "登录配置")
        
        # 设备管理页
        devices_tab = self.create_devices_tab()
        tab_widget.addTab(devices_tab, "设备管理")
        
        # 日志页
        log_tab = self.create_log_tab()
        tab_widget.addTab(log_tab, "运行日志")
        
        main_layout.addWidget(tab_widget)
        
        return main_widget
    
    def create_login_tab(self):
        """创建登录配置标签页"""
        login_widget = QWidget()
        login_layout = QVBoxLayout(login_widget)
        login_layout.setSpacing(15)
        
        # 登录表单
        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)
        form_layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form_layout.setHorizontalSpacing(12)
        form_layout.setVerticalSpacing(15)
        
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText('请输入AutoDL用户名/邮箱')
        self.username_input.setFixedHeight(40)
        
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText('请输入密码')
        self.password_input.setFixedHeight(40)
        
        form_layout.addRow(QLabel('用户名:'), self.username_input)
        form_layout.addRow(QLabel('密码:'), self.password_input)
        
        login_layout.addWidget(form_widget)
        
        # 登录按钮
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        self.login_button = QPushButton('登录')
        self.login_button.setObjectName('loginBtn')
        self.login_button.setFixedHeight(42)
        self.login_button.setMinimumWidth(120)
        self.login_button.clicked.connect(self.login_autodl)
        
        self.logout_button = QPushButton('登出')
        self.logout_button.setFixedHeight(42)
        self.logout_button.setMinimumWidth(120)
        self.logout_button.clicked.connect(self.logout_autodl)
        self.logout_button.setEnabled(False)
        
        button_layout.addWidget(self.login_button)
        button_layout.addWidget(self.logout_button)
        button_layout.addStretch()
        
        login_layout.addLayout(button_layout)
        login_layout.addStretch()
        
        return login_widget
    
    def create_devices_tab(self):
        """创建设备管理标签页"""
        devices_widget = QWidget()
        devices_layout = QVBoxLayout(devices_widget)
        devices_layout.setSpacing(10)
        
        # 控制按钮
        control_layout = QHBoxLayout()
        control_layout.setSpacing(10)
        
        self.refresh_button = QPushButton('刷新设备列表')
        self.refresh_button.setObjectName('refreshBtn')
        self.refresh_button.setFixedHeight(40)
        self.refresh_button.clicked.connect(self.refresh_devices)
        
        self.start_selected_button = QPushButton('开机选中设备')
        self.start_selected_button.setObjectName('startBtn')
        self.start_selected_button.setFixedHeight(40)
        self.start_selected_button.clicked.connect(self.start_selected_devices)
        
        control_layout.addWidget(self.refresh_button)
        control_layout.addWidget(self.start_selected_button)
        control_layout.addStretch()
        
        devices_layout.addLayout(control_layout)
        
        # 设备表格
        self.devices_table = QTableWidget()
        self.devices_table.setColumnCount(6)
        self.devices_table.setHorizontalHeaderLabels([
            '选择', '设备名称', '设备ID', '状态', '规格', '操作'
        ])
        self.devices_table.horizontalHeader().setStretchLastSection(True)
        self.devices_table.setAlternatingRowColors(True)
        self.devices_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        
        devices_layout.addWidget(self.devices_table)
        
        return devices_widget
    
    def create_log_tab(self):
        """创建日志标签页"""
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.setSpacing(10)
        
        # 状态标签
        self.status_label = QLabel('状态: 未登录')
        self.status_label.setStyleSheet('font-weight: 700; color: #656d76; font-size: 12pt;')
        log_layout.addWidget(self.status_label)
        
        # 日志文本框
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(300)
        log_layout.addWidget(self.log_text)
        
        # 清除日志按钮
        clear_button = QPushButton('清除日志')
        clear_button.setFixedHeight(35)
        clear_button.clicked.connect(self.clear_log)
        log_layout.addWidget(clear_button)
        
        return log_widget
    
    def setup_event_handlers(self):
        """设置事件处理程序"""
        pass
    
    def update_status(self, message):
        """更新状态日志"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.log_text.append(f'[{timestamp}] {message}')
        self.log_text.verticalScrollBar().setValue(self.log_text.verticalScrollBar().maximum())
    
    def update_login_status(self, is_logged_in):
        """更新登录状态"""
        self.is_logged_in = is_logged_in
        if is_logged_in:
            self.status_label.setText('状态: 已登录')
            self.status_label.setStyleSheet('font-weight: 700; color: #2ea043; font-size: 12pt;')
            self.login_button.setEnabled(False)
            self.logout_button.setEnabled(True)
            self.refresh_button.setEnabled(True)
            self.start_selected_button.setEnabled(True)
        else:
            self.status_label.setText('状态: 未登录')
            self.status_label.setStyleSheet('font-weight: 700; color: #656d76; font-size: 12pt;')
            self.login_button.setEnabled(True)
            self.logout_button.setEnabled(False)
            self.refresh_button.setEnabled(False)
            self.start_selected_button.setEnabled(False)
    
    def clear_log(self):
        """清除日志"""
        self.log_text.clear()
    
    def init_driver(self):
        """初始化Chrome驱动"""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            # 尝试加载已保存的cookies
            if os.path.exists(self.cookies_file):
                chrome_options.add_argument(f'--user-data-dir={os.path.dirname(self.cookies_file)}')
            
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            self.update_status_signal.emit('Chrome浏览器初始化成功')
            return True
        except Exception as e:
            self.update_status_signal.emit(f'Chrome浏览器初始化失败: {str(e)}')
            return False
    
    def save_cookies(self):
        """保存cookies"""
        try:
            if self.driver:
                cookies = self.driver.get_cookies()
                with open(self.cookies_file, 'w', encoding='utf-8') as f:
                    json.dump(cookies, f, ensure_ascii=False, indent=2)
                self.update_status_signal.emit('登录状态已保存')
        except Exception as e:
            self.update_status_signal.emit(f'保存登录状态失败: {str(e)}')
    
    def login_autodl(self):
        """登录AutoDL"""
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        
        if not username or not password:
            QMessageBox.warning(self, '输入错误', '请输入用户名和密码')
            return
        
        if not self.init_driver():
            return
        
        try:
            self.update_status_signal.emit('正在访问AutoDL登录页面...')
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
                self.save_cookies()
                self.login_status_signal.emit(True)
                self.update_status_signal.emit('登录成功！')
                # 自动跳转到实例列表页面
                self.driver.get('https://www.autodl.com/console/instance/list')
                time.sleep(2)
                self.refresh_devices()
            else:
                self.update_status_signal.emit('登录失败，请检查用户名和密码')
                QMessageBox.warning(self, '登录失败', '用户名或密码错误')
                
        except TimeoutException:
            self.update_status_signal.emit('登录超时，请检查网络连接')
            QMessageBox.warning(self, '登录超时', '连接超时，请检查网络')
        except Exception as e:
            self.update_status_signal.emit(f'登录过程出错: {str(e)}')
            QMessageBox.critical(self, '登录错误', f'登录过程出错: {str(e)}')
    
    def logout_autodl(self):
        """登出AutoDL"""
        try:
            if self.driver:
                self.driver.get('https://www.autodl.com/logout')
                time.sleep(1)
                self.login_status_signal.emit(False)
                self.update_status_signal.emit('已登出')
                # 清除cookies文件
                if os.path.exists(self.cookies_file):
                    os.remove(self.cookies_file)
        except Exception as e:
            self.update_status_signal.emit(f'登出出错: {str(e)}')
    
    def refresh_devices(self):
        """刷新设备列表"""
        if not self.driver or not self.is_logged_in:
            QMessageBox.warning(self, '未登录', '请先登录AutoDL')
            return
        
        try:
            self.update_status_signal.emit('正在刷新设备列表...')
            self.driver.get('https://www.autodl.com/console/instance/list')
            time.sleep(3)
            
            # 等待表格加载
            wait = WebDriverWait(self.driver, 10)
            table = wait.until(EC.presence_of_element_located((By.TAG_NAME, 'table')))
            
            # 获取所有行
            rows = table.find_elements(By.TAG_NAME, 'tr')[1:]  # 跳过表头
            
            self.devices_table.setRowCount(len(rows))
            
            for i, row in enumerate(rows):
                # 获取设备信息
                cells = row.find_elements(By.TAG_NAME, 'td')
                if len(cells) >= 7:
                    # 设备名称和ID
                    name_cell = cells[0]
                    device_name = name_cell.text.split('\n')[0]  # 第一行是名称
                    device_id = name_cell.text.split('\n')[1] if len(name_cell.text.split('\n')) > 1 else ''
                    
                    # 状态
                    status = cells[1].text
                    
                    # 规格
                    specs = cells[2].text
                    
                    # 操作按钮
                    operation_cell = cells[-1]  # 最后一列是操作
                    
                    # 添加复选框
                    checkbox = QCheckBox()
                    self.devices_table.setCellWidget(i, 0, checkbox)
                    
                    # 添加设备信息
                    self.devices_table.setItem(i, 1, QTableWidgetItem(device_name))
                    self.devices_table.setItem(i, 2, QTableWidgetItem(device_id))
                    self.devices_table.setItem(i, 3, QTableWidgetItem(status))
                    self.devices_table.setItem(i, 4, QTableWidgetItem(specs))
                    
                    # 添加开机按钮（如果设备已关机）
                    if '已关机' in status:
                        start_button = QPushButton('开机')
                        start_button.setObjectName('startBtn')
                        start_button.setFixedHeight(30)
                        start_button.clicked.connect(lambda checked, r=row: self.start_single_device(r))
                        self.devices_table.setCellWidget(i, 5, start_button)
            
            self.update_status_signal.emit(f'设备列表刷新完成，共找到 {len(rows)} 个设备')
            
        except TimeoutException:
            self.update_status_signal.emit('刷新设备列表超时')
            QMessageBox.warning(self, '刷新超时', '获取设备列表超时，请重试')
        except Exception as e:
            self.update_status_signal.emit(f'刷新设备列表失败: {str(e)}')
            QMessageBox.critical(self, '刷新失败', f'获取设备列表失败: {str(e)}')
    
    def start_single_device(self, row_element):
        """启动单个设备"""
        try:
            # 找到开机按钮并点击
            start_button = row_element.find_element(By.XPATH, './/a[contains(text(), "开机")]')
            start_button.click()
            
            self.update_status_signal.emit('正在确认开机...')
            time.sleep(1)
            
            # 等待确认对话框
            wait = WebDriverWait(self.driver, 5)
            confirm_button = wait.until(EC.element_to_be_clickable((By.XPATH, '//button[contains(text(), "确定")]')))
            confirm_button.click()
            
            self.update_status_signal.emit('开机指令已发送')
            time.sleep(2)
            self.refresh_devices()
            
        except TimeoutException:
            self.update_status_signal.emit('确认开机超时')
        except Exception as e:
            self.update_status_signal.emit(f'开机失败: {str(e)}')
    
    def start_selected_devices(self):
        """启动选中的设备"""
        selected_rows = []
        for i in range(self.devices_table.rowCount()):
            checkbox = self.devices_table.cellWidget(i, 0)
            if checkbox and checkbox.isChecked():
                selected_rows.append(i)
        
        if not selected_rows:
            QMessageBox.information(self, '提示', '请先选择要开机的设备')
            return
        
        reply = QMessageBox.question(self, '确认开机', 
                                   f'确定要开机选中的 {len(selected_rows)} 个设备吗？',
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply != QMessageBox.Yes:
            return
        
        # 这里需要重新获取页面元素，因为表格中的行元素可能已经失效
        try:
            self.driver.get('https://www.autodl.com/console/instance/list')
            time.sleep(3)
            
            table = self.driver.find_element(By.TAG_NAME, 'table')
            rows = table.find_elements(By.TAG_NAME, 'tr')[1:]
            
            success_count = 0
            for row_index in selected_rows:
                if row_index < len(rows):
                    try:
                        self.start_single_device(rows[row_index])
                        success_count += 1
                        time.sleep(1)  # 等待一下再处理下一个
                    except Exception as e:
                        self.update_status_signal.emit(f'设备 {row_index + 1} 开机失败: {str(e)}')
            
            self.update_status_signal.emit(f'批量开机完成，成功 {success_count}/{len(selected_rows)} 个设备')
            
        except Exception as e:
            self.update_status_signal.emit(f'批量开机过程出错: {str(e)}')
    
    def closeEvent(self, event):
        """窗口关闭时清理资源"""
        try:
            if self.driver:
                self.driver.quit()
                self.driver = None
            self.update_status_signal.emit('程序已退出')
        except Exception as e:
            print(f'关闭浏览器时出错: {str(e)}')
        event.accept()
    
    def load_saved_configs(self):
        """加载保存的配置"""
        try:
            # 加载设备配置
            if os.path.exists(self.devices_file):
                with open(self.devices_file, 'r', encoding='utf-8') as f:
                    devices_config = json.load(f)
                    # 这里可以恢复设备选择状态
        except Exception as e:
            self.update_status_signal.emit(f'加载配置失败: {str(e)}')


def main():
    """主函数"""
    try:
        print("启动AutoDL自动开机工具...")
        
        app = QApplication(sys.argv)
        app.setApplicationName("AutoDL自动开机工具")
        app.setApplicationVersion("1.0")
        app.setStyle('Fusion')
        
        # 设置全局字体
        import platform
        system = platform.system().lower()
        if 'darwin' in system:
            app.setFont(QFont('PingFang SC', 12))
        elif 'windows' in system:
            app.setFont(QFont('Microsoft YaHei UI', 11))
        else:
            app.setFont(QFont('Noto Sans CJK SC', 11))
        
        window = AutoDLAutoStarter()
        window.show()
        
        sys.exit(app.exec_())
        
    except Exception as e:
        print(f'应用程序启动失败: {str(e)}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()