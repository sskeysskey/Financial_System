import json
import sys
import time
import subprocess
import pyperclip
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                            QListWidget, QMessageBox, QInputDialog, QAction)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QKeySequence

def get_clipboard_content():
    """获取剪贴板内容，包含错误处理"""
    try:
        content = pyperclip.paste()
        return content.strip() if content else ""
    except Exception:
        return ""

def copy2clipboard():
    """执行复制操作并等待复制完成"""
    try:
        # 此脚本适用于macOS
        script = '''
        tell application "System Events"
            keystroke "c" using {command down}
        end tell
        '''
        subprocess.run(['osascript', '-e', script], check=True)
        # 给系统一点时间来完成复制操作
        time.sleep(0.5)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        # FileNotFoundError on non-macOS systems
        return False

def get_stock_symbol(default_symbol=""):
    """获取股票代码，如果用户取消则返回None"""
    # 确保QApplication实例存在
    app = QApplication.instance() or QApplication(sys.argv)
    
    input_dialog = QInputDialog()
    input_dialog.setWindowTitle("输入股票代码")
    input_dialog.setLabelText("请输入股票代码:")
    input_dialog.setTextValue(default_symbol)
    
    # 设置窗口标志，确保窗口始终在最前面
    input_dialog.setWindowFlags(input_dialog.windowFlags() | Qt.WindowStaysOnTopHint)
    
    if input_dialog.exec_() == QInputDialog.Accepted:
        return input_dialog.textValue().strip()
    return None # 用户点击了取消或关闭按钮

class TagEditor(QMainWindow):
    def __init__(self, init_symbol=None):
        super().__init__()        
        self.json_file_path = "/Users/yanzhang/Documents/Financial_System/Modules/description.json"
        self.load_json_data()
        
        self.setWindowTitle("Tag Editor")
        self.setGeometry(100, 100, 500, 600)
        
        # 创建主窗口部件和布局
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        # 添加 ESC 键关闭窗口的功能
        self.shortcut_close = QKeySequence("Esc")
        self.quit_action = QAction("Quit", self)
        self.quit_action.setShortcut(self.shortcut_close)
        self.quit_action.triggered.connect(self.close)
        self.addAction(self.quit_action)
        
        self.init_ui()
        
        # 处理初始化数据
        # 如果init_symbol是None或空，process_symbol会处理并可能关闭窗口
        self.process_symbol(init_symbol)
            
        # 设置焦点到输入框
        self.new_tag_input.setFocus()

        # 确保tags_list可以接收键盘焦点
        self.tags_list.setFocusPolicy(Qt.StrongFocus)
    
    def edit_current_tag(self):
        """编辑当前选中的标签"""
        current_item = self.tags_list.currentItem()
        if not current_item:
            return
            
        row = self.tags_list.row(current_item)
        old_tag = current_item.text()
        
        new_tag, ok = QInputDialog.getText(
            self, "编辑标签", "请输入新标签:", QLineEdit.Normal, old_tag
        )
        
        if ok and new_tag.strip() and new_tag != old_tag:
            self.current_item['tag'][row] = new_tag.strip()
            current_item.setText(new_tag.strip())

    def delete_current_tag(self):
        """删除当前选中的标签"""
        current_item = self.tags_list.currentItem()
        if current_item and hasattr(self, 'current_item'):
            row = self.tags_list.row(current_item)
            self.tags_list.takeItem(row)
            del self.current_item['tag'][row]

    def keyPressEvent(self, event):
        """处理键盘事件"""
        if self.tags_list.hasFocus() and self.tags_list.currentItem():
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.edit_current_tag()
                event.accept()
                return
            elif event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                self.delete_current_tag()
                event.accept()
                return
        
        super().keyPressEvent(event)

    def show(self):
        """重写 show 方法，确保窗口显示时properly激活"""
        super().show()
        self.activateWindow()
        self.raise_()
        self.new_tag_input.setFocus(Qt.OtherFocusReason)

    def showEvent(self, event):
        """重写showEvent以确保窗口显示后输入框获得焦点"""
        super().showEvent(event)
        QTimer.singleShot(100, self.new_tag_input.setFocus)
        
    def process_symbol(self, symbol):
        """
        处理指定的symbol。如果找不到，则提示用户输入。如果用户取消，则关闭窗口。
        """
        # 如果传入的symbol是None或空字符串，直接弹窗
        if not symbol:
            new_symbol = get_stock_symbol()
            if new_symbol:
                self.process_symbol(new_symbol)
            else:
                # 用户在第一次输入时就取消了，关闭窗口
                QTimer.singleShot(0, self.close)
            return
            
        original_symbol = symbol
        category, item = self.find_symbol(original_symbol)
        
        # 如果没找到，尝试大写形式
        if not item:
            uppercase_symbol = original_symbol.upper()
            if uppercase_symbol != original_symbol:
                category, item = self.find_symbol(uppercase_symbol)

        # 找到了就更新 UI
        if item:
            self.current_category = category
            self.current_item = item
            self.update_ui(item)
        else:
            # ★★★ BUG修复点 ★★★
            # 没找到，弹输入框让用户重新输入
            new_symbol = get_stock_symbol(default_symbol=original_symbol)
            if new_symbol:
                # 用户输入了新的symbol，递归处理
                self.process_symbol(new_symbol)
            else:
                # 用户在二次输入时点击了取消或关闭(ESC)，此时必须关闭窗口
                # 因为窗口已经创建但无法正确初始化数据
                QTimer.singleShot(0, self.close)

    def load_json_data(self):
        try:
            with open(self.json_file_path, 'r', encoding='utf-8') as file:
                self.data = json.load(file)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"加载JSON文件失败: {str(e)}")
            self.data = {"stocks": [], "etfs": []}
            # 如果JSON加载失败，可能需要直接退出
            QTimer.singleShot(0, self.close)

    def save_json_data(self):
        """保存数据到JSON文件"""
        try:
            with open(self.json_file_path, 'w', encoding='utf-8') as file:
                json.dump(self.data, file, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Error", f"保存失败: {str(e)}")
            return False

    def init_ui(self):
        self.symbol_label = QLabel("Symbol: ")
        self.layout.addWidget(self.symbol_label)
        
        self.tags_list = QListWidget()
        self.tags_list.itemDoubleClicked.connect(self.on_double_click)
        
        move_buttons_layout = QHBoxLayout()
        up_button = QPushButton("↑")
        down_button = QPushButton("↓")
        up_button.clicked.connect(self.move_tag_up)
        down_button.clicked.connect(self.move_tag_down)
        
        v_button_layout = QVBoxLayout()
        v_button_layout.addStretch()
        v_button_layout.addWidget(up_button)
        v_button_layout.addWidget(down_button)
        v_button_layout.addStretch()

        move_buttons_layout.addLayout(v_button_layout)
        move_buttons_layout.addWidget(self.tags_list)
        
        self.layout.addLayout(move_buttons_layout)
        
        input_layout = QHBoxLayout()
        self.new_tag_input = QLineEdit()
        self.new_tag_input.setPlaceholderText("在此输入新标签后按Enter或点击按钮")
        self.new_tag_input.returnPressed.connect(self.add_tag)
        add_button = QPushButton("添加新标签")
        add_button.clicked.connect(self.add_tag)
        input_layout.addWidget(self.new_tag_input)
        input_layout.addWidget(add_button)
        
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        delete_button = QPushButton("删除选中标签")
        save_button = QPushButton("保存并退出")
        delete_button.clicked.connect(self.delete_tag)
        save_button.clicked.connect(self.save_changes)
        buttons_layout.addWidget(delete_button)
        buttons_layout.addWidget(save_button)
        
        self.layout.addLayout(input_layout)
        self.layout.addLayout(buttons_layout)

    def on_double_click(self, item):
        """处理双击编辑事件"""
        self.edit_current_tag()

    def move_tag_up(self):
        current_row = self.tags_list.currentRow()
        if current_row > 0:
            tag = self.current_item['tag'].pop(current_row)
            self.current_item['tag'].insert(current_row - 1, tag)
            item = self.tags_list.takeItem(current_row)
            self.tags_list.insertItem(current_row - 1, item)
            self.tags_list.setCurrentRow(current_row - 1)

    def move_tag_down(self):
        current_row = self.tags_list.currentRow()
        if 0 <= current_row < self.tags_list.count() - 1:
            tag = self.current_item['tag'].pop(current_row)
            self.current_item['tag'].insert(current_row + 1, tag)
            item = self.tags_list.takeItem(current_row)
            self.tags_list.insertItem(current_row + 1, item)
            self.tags_list.setCurrentRow(current_row + 1)

    def find_symbol(self, symbol):
        """在 'stocks' 和 'etfs' 中查找symbol对应的数据"""
        for category in ['stocks', 'etfs']:
            for item in self.data.get(category, []):
                if item.get('symbol') == symbol:
                    return category, item
        return None, None

    def update_ui(self, item):
        self.symbol_label.setText(f"Symbol: <b>{item['symbol']}</b>")
        self.tags_list.clear()
        if 'tag' in item and item['tag']:
            self.tags_list.addItems(item['tag'])

    def add_tag(self):
        if not hasattr(self, 'current_item'):
            QMessageBox.warning(self, "警告", "没有加载任何项目，无法添加标签。")
            return
        new_tag = self.new_tag_input.text().strip()
        if new_tag:
            if new_tag not in self.current_item['tag']:
                self.current_item['tag'].append(new_tag)
                self.tags_list.addItem(new_tag)
                self.new_tag_input.clear()
            else:
                QMessageBox.information(self, "提示", "该标签已存在。")
        self.new_tag_input.setFocus()

    def delete_tag(self):
        self.delete_current_tag()

    def save_changes(self):
        if hasattr(self, 'current_item'):
            if self.save_json_data():
                self.close() # 保存成功后关闭
        else:
            QMessageBox.information(self, "提示", "没有可保存的更改。")
            self.close() # 没有更改也直接关闭

    def closeEvent(self, event):
        reply = QMessageBox.Yes
        if hasattr(self, 'current_item'):
            # 可以在这里比较当前状态和初始状态，判断是否有未保存的更改
            # 为简化，我们总是询问或自动保存
            if self.save_json_data():
                event.accept()
            else:
                reply = QMessageBox.question(
                    self, '保存失败', "数据保存失败，是否仍要关闭程序？",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No
                )
        if reply == QMessageBox.Yes:
            event.accept()
        else:
            event.ignore()

def main():
    app = QApplication(sys.argv)
    
    init_symbol = None
    if len(sys.argv) > 1:
        init_symbol = sys.argv[1]
    
    if not init_symbol:
        pyperclip.copy('')
        if not copy2clipboard():
            # 在非macOS或有权限问题时，直接弹出输入框
            init_symbol = get_stock_symbol()
        else:
            time.sleep(0.1) # 等待剪贴板更新
            new_content = get_clipboard_content()
            if not new_content:
                init_symbol = get_stock_symbol()
            else:
                init_symbol = new_content

    # 如果在所有尝试后，init_symbol仍然是None或空字符串，则退出
    if not init_symbol:
        return # 优雅退出

    editor = TagEditor(init_symbol)
    # 如果窗口在初始化过程中被关闭（例如，用户取消输入），exec_会立即返回
    if not editor.isVisible():
        editor.show()
        sys.exit(app.exec_())

if __name__ == "__main__":
    main()