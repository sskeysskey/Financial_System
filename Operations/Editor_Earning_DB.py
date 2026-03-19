import sys
import sqlite3
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QTableWidget, QTableWidgetItem, 
                             QVBoxLayout, QWidget, QDialog, QLabel, QLineEdit, 
                             QPushButton, QHBoxLayout, QMessageBox, QHeaderView)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent

USER_HOME = os.path.expanduser("~")

# 查询数据库，返回列名和记录数据
def query_database_data(db_file, table_name, condition, fields, include_condition):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    # 按照 date 和 name 排序，因为没有 id 了
    order_clause = "ORDER BY date DESC, name ASC"
    if include_condition and condition:
        query = f"SELECT {fields} FROM {table_name} WHERE {condition} {order_clause};"
    else:
        query = f"SELECT {fields} FROM {table_name} {order_clause};"
    cursor.execute(query)
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description] if rows else []
    conn.close()
    return columns, rows

# 更新记录：改为根据 date 和 name 定位
def update_record(db_file, table_name, old_date, old_name, new_values):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    # 动态拼接 set 部分
    set_clause = ", ".join([f"{col} = ?" for col in new_values.keys()])
    # 使用 date 和 name 作为唯一标识
    sql = f"UPDATE {table_name} SET {set_clause} WHERE date = ? AND name = ?"
    params = list(new_values.values()) + [old_date, old_name]
    cursor.execute(sql, params)
    conn.commit()
    conn.close()

# 删除记录：改为根据 date 和 name 定位
def delete_record(db_file, table_name, date, name):
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    sql = f"DELETE FROM {table_name} WHERE date = ? AND name = ?"
    cursor.execute(sql, (date, name))
    conn.commit()
    conn.close()

# --- 自定义删除对话框，支持左右键切换 ---
class DeleteConfirmDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("确认删除")
        self.setFixedSize(300, 150)
        
        layout = QVBoxLayout()
        layout.addWidget(QLabel("确定要删除该记录吗？"))
        
        btn_layout = QHBoxLayout()
        self.yes_btn = QPushButton("确定")
        self.no_btn = QPushButton("取消")
        
        btn_layout.addWidget(self.yes_btn)
        btn_layout.addWidget(self.no_btn)
        layout.addLayout(btn_layout)
        self.setLayout(layout)
        
        self.yes_btn.clicked.connect(self.accept)
        self.no_btn.clicked.connect(self.reject)
        
        # 默认焦点在“取消”上，防止误删
        self.no_btn.setFocus()

    def keyPressEvent(self, event: QKeyEvent):
        # 左右键切换焦点
        if event.key() == Qt.Key.Key_Left or event.key() == Qt.Key.Key_Right:
            if self.yes_btn.hasFocus():
                self.no_btn.setFocus()
            else:
                self.yes_btn.setFocus()
        # ESC 键关闭对话框
        elif event.key() == Qt.Key.Key_Escape:
            self.reject()
        else:
            super().keyPressEvent(event)

# --- 主窗口类 ---
class MainWindow(QMainWindow):
    def __init__(self, db_info):
        super().__init__()
        self.db_info = db_info
        self.setWindowTitle("数据库查询与编辑")
        self.resize(900, 600)
        
        self.table_widget = QTableWidget()
        self.setCentralWidget(self.table_widget)
        self.table_widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_widget.doubleClicked.connect(self.on_double_click)
        
        self.refresh_table()

    def refresh_table(self):
        cols, rows = query_database_data(self.db_info['path'], self.db_info['table'], 
                                         self.db_info['condition'], self.db_info['fields'], 
                                         self.db_info['include_condition'])
        self.table_widget.setColumnCount(len(cols))
        self.table_widget.setHorizontalHeaderLabels(cols)
        self.table_widget.setRowCount(len(rows))
        
        for r_idx, row in enumerate(rows):
            for c_idx, val in enumerate(row):
                self.table_widget.setItem(r_idx, c_idx, QTableWidgetItem(str(val)))
        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def on_double_click(self):
        row = self.table_widget.currentRow()
        if row < 0: return
        
        # 获取当前行数据
        record = [self.table_widget.item(row, i).text() for i in range(self.table_widget.columnCount())]
        columns = [self.table_widget.horizontalHeaderItem(i).text() for i in range(self.table_widget.columnCount())]
        
        self.open_edit_window(record, columns)

    def open_edit_window(self, record, columns):
        edit_win = QDialog(self)
        edit_win.setWindowTitle("编辑记录")
        
        # 重写编辑窗口的 ESC 事件
        def edit_win_keyPressEvent(event):
            if event.key() == Qt.Key.Key_Escape:
                edit_win.close()
            else:
                QDialog.keyPressEvent(edit_win, event)
        edit_win.keyPressEvent = edit_win_keyPressEvent
        
        layout = QVBoxLayout()
        
        date_idx = columns.index("date")
        name_idx = columns.index("name")
        old_date = record[date_idx]
        old_name = record[name_idx]
        
        inputs = {}
        for i, col in enumerate(columns):
            h_layout = QHBoxLayout()
            h_layout.addWidget(QLabel(col))
            line_edit = QLineEdit(record[i])
            if col in ["date", "name"]:
                line_edit.setReadOnly(True)
            h_layout.addWidget(line_edit)
            layout.addLayout(h_layout)
            inputs[col] = line_edit
            
        def save():
            new_vals = {col: inputs[col].text() for col in columns if col not in ["date", "name"]}
            try:
                update_record(self.db_info['path'], self.db_info['table'], old_date, old_name, new_vals)
                edit_win.accept()
                self.refresh_table()
            except Exception as e:
                QMessageBox.critical(self, "错误", str(e))
                
        def delete():
            dialog = DeleteConfirmDialog(self)
            if dialog.exec():
                try:
                    delete_record(self.db_info['path'], self.db_info['table'], old_date, old_name)
                    edit_win.accept() # 关闭编辑窗口
                    self.refresh_table()
                    # 关键：强制焦点回到主窗口
                    self.activateWindow()
                    self.setFocus()
                except Exception as e:
                    QMessageBox.critical(self, "错误", str(e))

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("保存")
        del_btn = QPushButton("删除")
        save_btn.clicked.connect(save)
        del_btn.clicked.connect(delete)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(del_btn)
        layout.addLayout(btn_layout)
        
        edit_win.setLayout(layout)
        edit_win.exec()

    def keyPressEvent(self, event: QKeyEvent):
        # ESC 键退出程序
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        # BackSpace 键删除记录
        elif event.key() == Qt.Key.Key_Backspace:
            row = self.table_widget.currentRow()
            if row >= 0:
                # 复用刚才的删除逻辑
                dialog = DeleteConfirmDialog(self)
                if dialog.exec():
                    cols = [self.table_widget.horizontalHeaderItem(i).text() for i in range(self.table_widget.columnCount())]
                    date_val = self.table_widget.item(row, cols.index("date")).text()
                    name_val = self.table_widget.item(row, cols.index("name")).text()
                    delete_record(self.db_info['path'], self.db_info['table'], date_val, name_val)
                    self.refresh_table()
                    self.activateWindow()
                    self.setFocus()
        else:
            super().keyPressEvent(event)

# --- 入口逻辑 ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # 模拟获取 symbol 的逻辑
    db_path = os.path.join(USER_HOME, 'Coding/Database/Finance.db')
    table_name = 'Earning'
    current_symbol = sys.argv[1].upper() if len(sys.argv) > 1 else None
    
    # 这里为了演示，简单处理一下初始化逻辑
    # 实际应用中建议将输入 symbol 的逻辑放在启动页
    db_info = {
        'path': db_path,
        'table': table_name,
        'condition': f"name = '{current_symbol}'" if current_symbol else "",
        'fields': '*',
        'include_condition': True if current_symbol else False
    }
    
    window = MainWindow(db_info)
    window.show()
    sys.exit(app.exec())