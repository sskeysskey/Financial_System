import json
import sys
import time
import subprocess
import pyperclip
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                            QListWidget, QMessageBox, QInputDialog, QAction)
from PyQt5.QtCore import Qt
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
        script = '''
        tell application "System Events"
            keystroke "c" using {command down}
        end tell
        '''
        subprocess.run(['osascript', '-e', script], check=True)
        # 给系统一点时间来完成复制操作
        time.sleep(0.5)
        return True
    except subprocess.CalledProcessError:
        return False

def get_stock_symbol(default_symbol=""):
    """获取股票代码"""
    app = QApplication.instance() or QApplication(sys.argv)
    
    input_dialog = QInputDialog()
    input_dialog.setWindowTitle("输入股票代码")
    input_dialog.setLabelText("请输入股票代码:")
    input_dialog.setTextValue(default_symbol)
    
    # 设置窗口标志，确保窗口始终在最前面
    input_dialog.setWindowFlags(
        Qt.WindowTitleHint | 
        Qt.CustomizeWindowHint | 
        Qt.WindowCloseButtonHint
    )
    
    # 显示并激活窗口
    input_dialog.show()
    input_dialog.activateWindow()
    input_dialog.raise_()
    
    # 强制获取焦点
    input_dialog.setFocus(Qt.OtherFocusReason)
    
    if input_dialog.exec_() == QInputDialog.Accepted:
        # 直接将输入转换为大写
        return input_dialog.textValue().strip().upper()
    return None

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
        if init_symbol:
            self.process_symbol(init_symbol)
        else:
            self.process_clipboard()
            
        # 设置焦点到输入框
        QApplication.processEvents()  # 确保UI已经完全加载
        self.new_tag_input.setFocus()
    
    def show(self):
        """重写 show 方法，确保窗口显示时properly激活"""
        super().show()
        self.activateWindow()
        self.raise_()
        # 确保输入框获得焦点
        self.new_tag_input.setFocus(Qt.OtherFocusReason)

    def showEvent(self, event):
        """重写showEvent以确保窗口显示后输入框获得焦点"""
        super().showEvent(event)
        # 使用Timer确保在窗口完全显示后设置焦点
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(100, self.new_tag_input.setFocus)
        
    def process_symbol(self, symbol):
        """处理指定的symbol"""
        if symbol:
            category, item = self.find_symbol(symbol)
            if item:
                self.current_category = category
                self.current_item = item
                self.update_ui(item)
            else:
                # messagebox.showinfo("提示", f"未找到Symbol: {symbol}")
                QMessageBox.information(self, "提示", f"未找到Symbol: {symbol}")

    def load_json_data(self):
        try:
            with open(self.json_file_path, 'r', encoding='utf-8') as file:
                self.data = json.load(file)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"加载JSON文件失败: {str(e)}")
            self.data = {"stocks": [], "etfs": []}

    def save_json_data(self):
        try:
            with open(self.json_file_path, 'w', encoding='utf-8') as file:
                json.dump(self.data, file, ensure_ascii=False, indent=2)
            # 创建一个消息框并连接其按钮点击事件
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Information)
            msg_box.setText("保存成功！")
            msg_box.setWindowTitle("成功")
            msg_box.setStandardButtons(QMessageBox.Ok)
            
            # 连接按钮点击事件
            msg_box.buttonClicked.connect(lambda _: self.close_application())
            
            msg_box.exec_()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"保存失败: {str(e)}")

    def close_application(self):
        """关闭应用程序"""
        QApplication.quit()
        
    def init_ui(self):
        # Symbol显示
        self.symbol_label = QLabel("Symbol: ")
        self.layout.addWidget(self.symbol_label)
        
        # Tags列表
        self.tags_list = QListWidget()
        self.tags_list.itemDoubleClicked.connect(self.on_double_click)
        
        # 移动按钮布局
        move_buttons_layout = QHBoxLayout()
        up_button = QPushButton("↑")
        down_button = QPushButton("↓")
        up_button.clicked.connect(self.move_tag_up)
        down_button.clicked.connect(self.move_tag_down)
        
        move_buttons_layout.addWidget(up_button)
        move_buttons_layout.addWidget(down_button)
        move_buttons_layout.addWidget(self.tags_list)
        
        self.layout.addLayout(move_buttons_layout)
        
        # 新标签输入
        input_layout = QHBoxLayout()
        self.new_tag_input = QLineEdit()
        self.new_tag_input.returnPressed.connect(self.add_tag)
        input_layout.addWidget(self.new_tag_input)
        
        # 按钮
        add_button = QPushButton("添加新标签")
        delete_button = QPushButton("删除标签")
        save_button = QPushButton("保存更改")
        
        add_button.clicked.connect(self.add_tag)
        delete_button.clicked.connect(self.delete_tag)
        save_button.clicked.connect(self.save_changes)
        
        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(add_button)
        buttons_layout.addWidget(delete_button)
        buttons_layout.addWidget(save_button)
        
        self.layout.addLayout(input_layout)
        self.layout.addLayout(buttons_layout)

    def on_double_click(self, item):
        """处理双击编辑事件"""
        if not item:
            return
            
        row = self.tags_list.row(item)
        old_tag = item.text()
        
        new_tag, ok = QInputDialog.getText(
            self,
            "编辑标签",
            "请输入新标签:",
            QLineEdit.Normal,
            old_tag
        )
        
        if ok and new_tag.strip() and new_tag != old_tag:
            self.current_item['tag'][row] = new_tag.strip()
            item.setText(new_tag.strip())

    def move_tag_up(self):
        """将选中的tag向上移动"""
        current_row = self.tags_list.currentRow()
        if current_row > 0:
            # 移动数据
            tag = self.current_item['tag'].pop(current_row)
            self.current_item['tag'].insert(current_row - 1, tag)
            # 移动列表项
            item = self.tags_list.takeItem(current_row)
            self.tags_list.insertItem(current_row - 1, item)
            self.tags_list.setCurrentRow(current_row - 1)

    def move_tag_down(self):
        """将选中的tag向下移动"""
        current_row = self.tags_list.currentRow()
        if current_row < self.tags_list.count() - 1:
            # 移动数据
            tag = self.current_item['tag'].pop(current_row)
            self.current_item['tag'].insert(current_row + 1, tag)
            # 移动列表项
            item = self.tags_list.takeItem(current_row)
            self.tags_list.insertItem(current_row + 1, item)
            self.tags_list.setCurrentRow(current_row + 1)

    # [之前的其他方法保持不变...]
    def find_symbol(self, symbol):
        """查找symbol对应的数据"""
        for category in ['stocks', 'etfs']:
            for item in self.data[category]:
                if item['symbol'] == symbol:
                    return category, item
        return None, None

    def process_clipboard(self):
        """处理剪贴板内容"""
        try:
            clipboard_text = pyperclip.paste().strip()
            if clipboard_text:
                category, item = self.find_symbol(clipboard_text)
                if item:
                    self.current_category = category
                    self.current_item = item
                    self.update_ui(item)
                else:
                    # messagebox.showinfo("提示", f"未找到Symbol: {clipboard_text}")
                    QMessageBox.information(self, "提示", f"未找到Symbol: {clipboard_text}")
            else:
                # messagebox.showinfo("提示", "剪贴板为空")
                QMessageBox.information(self, "提示", "剪贴板为空")
        except Exception as e:
            # messagebox.showerror("Error", f"剪贴板读取失败: {str(e)}")
            QMessageBox.information(self, "Error", f"剪贴板读取失败: {str(e)}")

    def update_ui(self, item):
        """更新UI显示"""
        self.symbol_label.setText(f"Symbol: {item['symbol']}")
        self.tags_list.clear()
        for tag in item['tag']:
            self.tags_list.addItem(tag)

    def add_tag(self):
        """添加新tag"""
        new_tag = self.new_tag_input.text().strip()
        if new_tag and hasattr(self, 'current_item'):
            if new_tag not in self.current_item['tag']:
                self.current_item['tag'].append(new_tag)
                self.tags_list.addItem(new_tag)
                self.new_tag_input.clear()
            else:
                QMessageBox.information(self, "提示", "该标签已存在")

    def delete_tag(self):
        """删除选中的tag"""
        current_item = self.tags_list.currentItem()
        if current_item and hasattr(self, 'current_item'):
            tag = current_item.text()
            self.current_item['tag'].remove(tag)
            self.tags_list.takeItem(self.tags_list.row(current_item))

    def save_changes(self):
        """保存更改到JSON文件"""
        if hasattr(self, 'current_item'):
            self.save_json_data()
        else:
            # messagebox.showinfo("提示", "没有可保存的更改")
            QMessageBox.information(self, "提示", "没有可保存的更改")

def main():
    app = QApplication(sys.argv)
    
    # 检查命令行参数
    init_symbol = None
    if len(sys.argv) > 1:
        init_symbol = sys.argv[1].upper()
    
    if not init_symbol:
        initial_content = get_clipboard_content()
        if not copy2clipboard():
            return
        
        new_content = get_clipboard_content()
        if initial_content == new_content:
            init_symbol = get_stock_symbol(new_content)
            if init_symbol is None:
                return
        else:
            # init_symbol = get_stock_symbol(new_content)
            init_symbol = new_content
            if init_symbol is None:
                return
    
    editor = TagEditor(init_symbol)
    editor.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()