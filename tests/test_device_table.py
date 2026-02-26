#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试设备列表解析功能"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication, QTableWidget, QTableWidgetItem, QCheckBox, QPushButton
from PyQt5.QtCore import Qt
import threading
import time

class MockWebElement:
    """模拟WebElement用于测试"""
    def __init__(self, tag_name, text, class_name=None):
        self.tag_name = tag_name
        self.text_content = text
        self.class_name = class_name or ''
        self.children = []
    
    @property
    def text(self):
        return self.text_content
    
    def get_attribute(self, name):
        if name == 'class':
            return self.class_name
        return None
    
    def find_elements(self, by, value):
        """模拟查找子元素"""
        if self.tag_name == 'table' and by == 'tag name' and value == 'tr':
            return self.children
        elif self.tag_name == 'tr' and by == 'tag name' and value == 'td':
            return self.children
        return []

def test_device_table_update():
    """测试设备表格更新功能"""
    app = QApplication(sys.argv)
    
    # 创建测试表格
    table = QTableWidget()
    table.setColumnCount(5)
    table.setHorizontalHeaderLabels(['选择', '设备名称', '状态', '规格', '操作'])
    table.setRowCount(0)
    
    # 创建模拟数据
    mock_rows = []
    
    # 模拟标准表格行
    row1 = MockWebElement('tr', '')
    cell1_1 = MockWebElement('td', 'GPU服务器-001\nID: gpu-001')
    cell1_2 = MockWebElement('td', '运行中')
    cell1_3 = MockWebElement('td', 'RTX 3090, 24GB, 8核')
    row1.children = [cell1_1, cell1_2, cell1_3]
    
    row2 = MockWebElement('tr', '')
    cell2_1 = MockWebElement('td', 'GPU服务器-002\nID: gpu-002')
    cell2_2 = MockWebElement('td', '已关机')
    cell2_3 = MockWebElement('td', 'RTX 3080, 10GB, 6核')
    row2.children = [cell2_1, cell2_2, cell2_3]
    
    # 模拟Element UI容器
    container1 = MockWebElement('div', 'GPU服务器-003\n运行中\nRTX 4080, 16GB, 12核', 'el-table__row')
    container2 = MockWebElement('div', 'GPU服务器-004\n已关机\nRTX 4070, 12GB, 8核', 'el-table__row')
    
    mock_rows = [row1, row2, container1, container2]
    
    print("开始测试设备表格更新...")
    print(f"模拟数据行数: {len(mock_rows)}")
    
    # 模拟update_device_table功能
    table.setRowCount(len(mock_rows))
    device_count = 0
    
    for i, row in enumerate(mock_rows):
        try:
            device_name = '未知设备'
            device_id = ''
            status = '未知状态'
            specs = ''
            
            # 方法1: 如果是表格行，获取单元格
            if row.tag_name.lower() == 'tr':
                cells = row.children  # 使用模拟的子元素
                if cells:
                    # 设备名称和ID（通常在第一列）
                    name_cell = cells[0]
                    cell_text = name_cell.text.strip()
                    lines = cell_text.split('\n')
                    device_name = lines[0] if lines and lines[0] else '未知设备'
                    device_id = lines[1] if len(lines) > 1 else ''
                    
                    # 状态（通常在第二列）
                    status = cells[1].text.strip() if len(cells) > 1 else '未知状态'
                    
                    # 规格（通常在第三列）
                    specs = cells[2].text.strip() if len(cells) > 2 else ''
            
            # 方法2: 如果是容器元素，直接解析文本
            else:
                row_text = row.text.strip()
                if row_text:
                    # 尝试从文本中提取信息
                    lines = row_text.split('\n')
                    if lines:
                        device_name = lines[0]
                        # 查找状态关键词
                        for line in lines[1:]:
                            line = line.strip()
                            if any(keyword in line for keyword in ['运行中', '已关机', '开机', '关机', 'running', 'stopped']):
                                status = line
                                break
                        # 合并剩余行作为规格
                        specs = '\n'.join(lines[1:]) if len(lines) > 1 else ''
            
            # 确保有关键信息才添加为有效设备
            if device_name != '未知设备' or status != '未知状态':
                print(f"处理设备 {i+1}: {device_name}, 状态: {status}, 规格: {specs}")
                
                # 添加复选框
                checkbox = QCheckBox()
                checkbox.setStyleSheet("margin-left: 10px;")
                table.setCellWidget(i, 0, checkbox)
                
                # 添加设备信息
                table.setItem(i, 1, QTableWidgetItem(device_name))
                table.setItem(i, 2, QTableWidgetItem(status))
                table.setItem(i, 3, QTableWidgetItem(specs))
                
                # 添加操作按钮
                if '已关机' in status or '关机' in status or 'stopped' in status.lower():
                    start_button = QPushButton('开机')
                    start_button.setStyleSheet('background: #2ea043; color: white; font-size: 8pt; padding: 2px 6px;')
                    table.setCellWidget(i, 4, start_button)
                elif '运行中' in status or '开机' in status or 'running' in status.lower():
                    stop_button = QPushButton('关机')
                    stop_button.setStyleSheet('background: #da3633; color: white; font-size: 8pt; padding: 2px 6px;')
                    table.setCellWidget(i, 4, stop_button)
                
                device_count += 1
                
        except Exception as row_error:
            print(f"处理第{i}行时出错: {row_error}")
            continue
    
    # 调整表格行数到实际设备数量
    table.setRowCount(device_count)
    print(f"测试完成，共处理 {device_count} 个有效设备")
    
    # 显示表格
    table.resize(800, 400)
    table.setWindowTitle('设备列表测试')
    table.show()
    
    print("测试表格已显示，请查看界面效果")
    print("按Enter键退出测试...")
    
    # 等待用户查看
    import threading
    def wait_for_input():
        input()
        app.quit()
    
    input_thread = threading.Thread(target=wait_for_input)
    input_thread.daemon = True
    input_thread.start()
    
    sys.exit(app.exec_())

if __name__ == '__main__':
    test_device_table_update()